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

# --- 2. TRAITEMENT PRIORITAIRE DU GPX ---
st.sidebar.header("🌍 Configuration")
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="gpx_uploader")

# On initialise avec None pour forcer le script à chercher
ville_detectee = None
pts_gpx = None

if f_gpx is not None:
    try:
        # Lecture immédiate
        data = f_gpx.getvalue()
        gpx = gpxpy.parse(data)
        pts_gpx = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
        
        if pts_gpx:
            # On cherche la ville par GPS
            g = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            if g and g.ok:
                ville_detectee = g.city if g.city else g.town
    except:
        pass

# --- 3. GESTION DE LA VILLE FINALE ---
# Si un GPX a donné une ville, on l'utilise. Sinon, on prend Cholet.
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"

if ville_detectee and ville_detectee != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_detectee
    st.rerun()

# Champ manuel qui peut écraser la détection
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

# --- 4. RÉCUPÉRATION MÉTÉO ---
@st.cache_data(ttl=3600)
def charger_meteo(ville):
    geo = geocoder.osm(ville)
    if not geo or not geo.ok: geo = geocoder.osm("Cholet")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={geo.lat}&longitude={geo.lng}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    return requests.get(url).json()

meteo = charger_meteo(st.session_state.nom_ville)

# --- 5. AFFICHAGE (Maintenant synchronisé) ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

if meteo and 'hourly' in meteo:
    st.header(f"🌤️ Prévisions à {st.session_state.nom_ville}")
    c1, c2, c3, c4 = st.columns(4)
    # Réglages sliders
    sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
    sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
    sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)
    
    for i, (col, h) in enumerate(zip([c1, c2, c3, c4], [10, 13, 16, 19])):
        t = meteo['hourly']['temperature_2m'][h]
        v = meteo['hourly']['windspeed_10m'][h]
        p = meteo['hourly']['precipitation_probability'][h]
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        col.metric(f"{h}h00", f"{score}/100", f"{t}°C")

st.divider()

# --- 6. CARTE ---
if pts_gpx:
    st.header(f"🗺️ Tracé : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400, key="map_soullans")

# --- 7. CONNEXION (Simplifiée pour ne pas bugger) ---
st.sidebar.divider()
if not st.session_state.get('logged_in', False):
    with st.sidebar.expander("🔐 Connexion"):
        u = st.text_input("Pseudo")
        p = st.text_input("Pass", type="password")
        if st.button("OK"):
            st.session_state.logged_in = True
            st.session_state.display_name = u
            st.rerun()
else:
    st.sidebar.success(f"Cycliste : {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()
