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

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Coach IA Cyclisme", page_icon="🚴", layout="wide")

# Initialisation des variables de session
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- 2. RÉSERVE POUR LE TITRE (Pour qu'il s'affiche en haut mais avec la bonne ville) ---
titre_placeholder = st.empty()

# --- 3. LOGIQUE DE DÉTECTION GPX (PRIORITÉ) ---
st.sidebar.header("🌍 Localisation & Parcours")
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'])

pts_gpx = None
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts_gpx:
        try:
            # On détecte Soullans ici
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_gpx = g_inv.city if g_inv.city else g_inv.town
            if ville_gpx and ville_gpx != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_gpx
                st.rerun() 
        except:
            pass

# Champ de saisie manuel (qui suit la session)
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

# --- 4. AUTHENTIFICATION ---
st.sidebar.divider()
st.sidebar.header("🔐 Accès Membre")
if not st.session_state.logged_in:
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Connexion"):
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            user_key = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
            if user_key in df_all['user'].astype(str).values:
                st.session_state.logged_in = True
                st.session_state.user_id = user_key
                st.session_state.display_name = u
                st.rerun()
        except: st.sidebar.error("Erreur connexion GSheets")
else:
    st.sidebar.write(f"✅ Connecté : **{st.session_state.display_name}**")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

# Paramètres de sensibilité
sf = st.sidebar.slider("🌡️ Sens. Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sens. Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sens. Pluie", 0, 10, 7)

# --- 5. CALCULS (MÉTÉO & IA) ---
@st.cache_data
def obtenir_coords(ville):
    g = geocoder.osm(ville)
    return (g.lat, g.lng) if g and g.ok else (47.06, -0.88)

lat, lon = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- 6. REMPLISSAGE DU TITRE (L'astuce est ici) ---
titre_placeholder.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

# --- 7. AFFICHAGE MÉTEO ---
st.header(f"🌤️ Prévisions à {st.session_state.nom_ville}")
if 'hourly' in data_m:
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t, v, p = data_m['hourly']['temperature_2m'][h], data_m['hourly']['windspeed_10m'][h], data_m['hourly']['precipitation_probability'][h]
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        with cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**\n<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h")

st.divider()

# --- 8. SECTION IA (COMPLÈTE) ---
if st.session_state.logged_in:
    st.header(f"🤖 Analyse Performance : {st.session_state.display_name}")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        df_user = df_all[(df_all['user'].astype(str) == st.session_state.user_id) & (df_all['date'] != 'INIT')]
        
        if len(df_user) >= 3:
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
            t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
            pred = model.predict([[t13, v13, h13]])[0]
            st.success(f"🎯 Estimation puissance à 13h : **{int(pred)} Watts**")
        else:
            st.info(f"Besoin de 3 sorties (actuellement : {len(df_user)}) pour activer l'IA.")

        with st.expander("📥 Ajouter une sortie CSV"):
            f_csv = st.file_uploader("Fichier CSV (Watts)", type=['csv'])
            if f_csv and st.button("Sauvegarder"):
                df_new = pd.read_csv(f_csv)
                df_new.columns = [c.lower().strip() for c in df_new.columns]
                w_moy = df_new[df_new['watts']>0]['watts'].mean()
                nouvelle_ligne = pd.DataFrame([{'user': st.session_state.user_id, 'temp': data_m['hourly']['temperature_2m'][12], 'wind': data_m['hourly']['windspeed_10m'][12], 'hum': data_m['hourly']['relative_humidity_2m'][12], 'watts': w_moy, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df_all, nouvelle_ligne], ignore_index=True))
                st.rerun()
    except: st.warning("Impossible de charger les données IA.")
else:
    st.info("👋 Connectez-vous pour voir vos prédictions de puissance.")

st.divider()

# --- 9. SECTION CARTE ---
if pts_gpx:
    st.header(f"🗺️ Tracé : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
    
