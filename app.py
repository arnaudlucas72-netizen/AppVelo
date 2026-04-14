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
if 'pts_gpx' not in st.session_state:
    st.session_state.pts_gpx = None
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- 2. BARRE LATÉRALE ---
st.sidebar.header("🌍 Configuration")

# Widget de téléchargement
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="gpx_uploader")

# --- 3. VÉRIFICATION ET CHARGEMENT COMPLET ---
# On bloque ici : si un fichier est présent, on ne fait RIEN d'autre tant qu'il n'est pas lu
if f_gpx is not None:
    try:
        # On lit le contenu brut pour s'assurer qu'il est chargé
        gpx_data = f_gpx.getvalue()
        gpx_parsed = gpxpy.parse(gpx_data)
        
        # Extraction des points
        pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
        
        if pts and (st.session_state.pts_gpx is None or pts != st.session_state.pts_gpx):
            # Le fichier est valide et nouveau -> On traite la ville
            st.session_state.pts_gpx = pts
            g_inv = geocoder.osm([pts[0][0], pts[0][1]], method='reverse')
            if g_inv and g_inv.ok:
                ville_detectee = g_inv.city if g_inv.city else g_inv.town
                if ville_detectee:
                    st.session_state.nom_ville = ville_detectee
                    st.rerun() # On relance pour que le titre s'actualise avec la ville
    except Exception as e:
        st.sidebar.error("Fichier GPX corrompu ou incomplet")

# Champ manuel pour ajuster la ville
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

# --- 4. AUTHENTIFICATION ---
st.sidebar.divider()
if not st.session_state.logged_in:
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
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
        except: pass
else:
    st.sidebar.write(f"✅ {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

# --- 5. CALCULS MÉTÉO (Basés sur la ville validée) ---
@st.cache_data(ttl=3600)
def obtenir_meteo(ville):
    g = geocoder.osm(ville)
    if not g or not g.ok: g = geocoder.osm("Cholet")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={g.lat}&longitude={g.lng}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    return requests.get(url).json()

weather_data = obtenir_meteo(st.session_state.nom_ville)

# --- 6. AFFICHAGE FINAL ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

if weather_data and 'hourly' in weather_data:
    st.header(f"🌤️ Prévisions : {st.session_state.nom_ville}")
    cols = st.columns(4)
    sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
    sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
    sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)
    
    for i, h in enumerate([10, 13, 16, 19]):
        t = weather_data['hourly']['temperature_2m'][h]
        v = weather_data['hourly']['windspeed_10m'][h]
        p = weather_data['hourly']['precipitation_probability'][h]
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        cols[i].metric(f"{h}h00", f"{score}/100", f"{t}°C")

st.divider()

# --- 7. CARTE ---
if st.session_state.pts_gpx:
    st.header(f"🗺️ Tracé détecté")
    m = folium.Map(location=st.session_state.pts_gpx[0], zoom_start=12)
    folium.PolyLine(st.session_state.pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400, key="map_final")
