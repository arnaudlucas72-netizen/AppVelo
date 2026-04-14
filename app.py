import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import geocoder
import gpxpy
import folium
from streamlit_folium import st_folium
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
import hashlib

# --- 1. CONFIGURATION & INITIALISATION ---
st.set_page_config(page_title="Coach IA Cyclisme", page_icon="🚴", layout="wide")

if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- 2. GESTION DU GPX (PRIORITÉ ABSOLUE) ---
st.sidebar.header("🌍 Configuration Parcours")
f_gpx = st.sidebar.file_uploader("📂 Importer un fichier GPX", type=['gpx'], key="main_uploader")

pts_gpx = None
if f_gpx is not None:
    try:
        # Lecture complète du fichier
        gpx_parsed = gpxpy.parse(f_gpx.getvalue())
        pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
        
        if pts_gpx:
            # Détection de la ville par coordonnées
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_detectee = g_inv.city if g_inv.city else g_inv.town
            
            # Mise à jour de la session si changement
            if ville_detectee and ville_detectee != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_detectee
                st.rerun()
    except Exception as e:
        st.sidebar.error("Erreur de lecture GPX")

# Champ de saisie manuel (synchronisé)
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

# --- 3. RÉCUPÉRATION MÉTÉO (FONCTION CACHÉE) ---
@st.cache_data(ttl=3600)
def fetch_weather_and_coords(ville):
    g = geocoder.osm(ville)
    if not g or not g.ok: 
        g = geocoder.osm("Cholet")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={g.lat}&longitude={g.lng}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    return (g.lat, g.lng), requests.get(url).json()

coords, weather = fetch_weather_and_coords(st.session_state.nom_ville)

# --- 4. BARRE LATÉRALE : ACCÈS ET RÉGLAGES ---
st.sidebar.divider()
st.sidebar.header("🔐 Espace Membre")

if not st.session_state.logged_in:
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Connexion"):
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_auth = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            u_key = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
            if u_key in df_auth['user'].astype(str).values:
                st.session_state.logged_in = True
                st.session_state.user_id = u_key
                st.session_state.display_name = u
                st.rerun()
        except: st.sidebar.error("Lien Google Sheets indisponible")
else:
    st.sidebar.success(f"Connecté : {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

st.sidebar.divider()
st.sidebar.header("⚙️ Sensibilité")
sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)

# --- 5. AFFICHAGE PRINCIPAL ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

# Section Météo
if weather and 'hourly' in weather:
    st.header(f"🌤️ Prévisions détaillées à {st.session_state.nom_ville}")
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = weather['hourly']['temperature_2m'][h]
        v = weather['hourly']['windspeed_10m'][h]
        p = weather['hourly']['precipitation_probability'][h]
        # Calcul du score de confort
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        with cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**\n<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"🌡️ {t}°C | 💨 {v}km/h | 💧 {p}%")

st.divider()

# Section IA & Performance
if st.session_state.logged_in:
    st.header(f"🤖 Analyse Performance : {st.session_state.display_name}")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        df_u = df_all[df_all['user'].astype(str) == st.session_state.user_id]
        
        if len(df_u) >= 3:
            # Entraînement express du modèle
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(df_u[['temp', 'wind', 'hum']], df_u['watts'])
            
            # Prédiction pour 13h
            t13, v13, h13 = weather['hourly']['temperature_2m'][13], weather['hourly']['windspeed_10m'][13], weather['hourly']['relative_humidity_2m'][13]
            pred = model.predict([[t13, v13, h13]])[0]
            st.success(f"🎯 Puissance estimée pour ta sortie à 13h : **{int(pred)} Watts**")
        else:
            st.info(f"Encore {3 - len(df_u)} sortie(s) à enregistrer pour activer l'IA.")

        with st.expander("📤 Importer une nouvelle performance (CSV)"):
            f_csv = st.file_uploader("Fichier CSV de puissance", type=['csv'])
            if f_csv and st.button("Valider l'enregistrement"):
                df_new = pd.read_csv(f_csv)
                df_new.columns = [c.lower().strip() for c in df_new.columns]
                w_moy = df_new[df_new['watts']>0]['watts'].mean()
                
                new_row = pd.DataFrame([{
                    'user': st.session_state.user_id,
                    'temp': weather['hourly']['temperature_2m'][12],
                    'wind': weather['hourly']['windspeed_10m'][12],
                    'hum': weather['hourly']['relative_humidity_2m'][12],
                    'watts': w_moy,
                    'date': datetime.now().strftime("%Y-%m-%d")
                }])
                conn.update(worksheet="Performances", data=pd.concat([df_all, new_row], ignore_index=True))
                st.rerun()
    except:
        st.warning("IA en attente de données...")
else:
    st.info("👋 Connectez-vous dans la barre latérale pour accéder à l'analyse de puissance IA.")

# Section Carte
if pts_gpx:
    st.header(f"🗺️ Parcours détecté : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=450, key="map_final")
