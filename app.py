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

# Initialisation silencieuse
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- 2. LE TITRE (DYNAMIQUE) ---
# On affiche le titre tout de suite, il sera mis à jour par le rerun si besoin
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

# --- 3. BARRE LATÉRALE ET LOGIQUE GPX ---
st.sidebar.header("🌍 Localisation & Parcours")

# Widget de téléchargement
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="gpx_uploader")

pts_gpx = None
if f_gpx:
    # Lecture du fichier
    gpx_parsed = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    
    if pts_gpx:
        try:
            # On extrait la ville du point de départ
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_gpx = g_inv.city if g_inv.city else g_inv.town
            
            # FORCE : Si la ville GPX (Soullans) est différente de la ville en session (Cholet)
            if ville_gpx and ville_gpx != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_gpx
                st.rerun() # On relance TOUT le script pour que le titre en haut change
        except:
            pass

# Champ de saisie manuel (synchronisé)
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

st.sidebar.divider()

# --- 4. AUTHENTIFICATION ---
st.sidebar.header("🔐 Accès Membre")
if not st.session_state.logged_in:
    u = st.sidebar.text_input("Pseudo").strip()
    p = st.sidebar.text_input("Mot de passe", type="password").strip()
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
            else:
                st.sidebar.error("Identifiants incorrects")
        except:
            st.sidebar.error("Erreur de connexion GSheets")
else:
    st.sidebar.success(f"Connecté : {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

# Réglages météo
sf = st.sidebar.slider("🌡️ Sens. Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sens. Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sens. Pluie", 0, 10, 7)

# --- 5. CALCULS MÉTÉO ---
@st.cache_data
def obtenir_coords(ville):
    g = geocoder.osm(ville)
    return (g.lat, g.lng) if g and g.ok else (47.06, -0.88)

lat, lon = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
try:
    data_m = requests.get(api_url).json()
except:
    data_m = {}

# --- 6. AFFICHAGE DES PRÉVISIONS ---
st.header(f"🌤️ Prévisions pour {st.session_state.nom_ville}")
if 'hourly' in data_m:
    m_cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = data_m['hourly']['temperature_2m'][h]
        v = data_m['hourly']['windspeed_10m'][h]
        p = data_m['hourly']['precipitation_probability'][h]
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        with m_cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**\n<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h")

st.divider()

# --- 7. SECTION IA ---
if st.session_state.logged_in:
    st.header(f"🤖 Analyse de {st.session_state.display_name}")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        df_user = df_all[(df_all['user'].astype(str) == st.session_state.user_id) & (df_all['date'] != 'INIT')]
        
        if len(df_user) >= 3:
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
            t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
            pred = model.predict([[t13, v13, h13]])[0]
            st.success(f"🎯 Puissance estimée à 13h : **{int(pred)} Watts**")
        else:
            st.info(f"Ajoutez {3 - len(df_user)} sortie(s) supplémentaire(s) pour activer l'IA.")

        with st.expander("📥 Ajouter une sortie CSV"):
            f_csv = st.file_uploader("Fichier CSV", type=['csv'], key="csv_up")
            if f_csv and st.button("Enregistrer"):
                df_new = pd.read_csv(f_csv)
                df_new.columns = [c.lower().strip() for c in df_new.columns]
                w_moy = df_new[df_new['watts']>0]['watts'].mean()
                nouvelle_ligne = pd.DataFrame([{'user': st.session_state.user_id, 'temp': data_m['hourly']['temperature_2m'][12], 'wind': data_m['hourly']['windspeed_10m'][12], 'hum': data_m['hourly']['relative_humidity_2m'][12], 'watts': w_moy, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df_all, nouvelle_ligne], ignore_index=True))
                st.rerun()
    except:
        st.warning("Données IA temporairement indisponibles.")
else:
    st.info("Connectez-vous pour voir vos prédictions Watts.")

st.divider()

# --- 8. SECTION CARTE ---
if pts_gpx:
    st.header(f"🗺️ Parcours : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400, key="map_final")
    
