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

# --- 2. INITIALISATION ---
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'key_v' not in st.session_state:
    st.session_state.key_v = 0
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- 3. DÉTECTION GPX (AVANT TOUT AFFICHAGE) ---
st.sidebar.header("🌍 Localisation & Parcours")
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="gpx_loader")

pts_gpx = None
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts_gpx:
        try:
            # On géolocalise le départ (ex: Soullans)
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_gpx = g_inv.city if g_inv.city else g_inv.town
            
            if ville_gpx and ville_gpx != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_gpx
                st.session_state.key_v += 1 # On change la clé pour forcer le refresh du widget texte
                st.rerun() 
        except:
            pass

# --- 4. BARRE LATÉRALE ---
# On utilise la clé dynamique pour que le champ texte s'écrase lors d'un import GPX
ville_input = st.sidebar.text_input(
    "📍 Ville active", 
    value=st.session_state.nom_ville, 
    key=f"input_v_{st.session_state.key_v}"
)

if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

st.sidebar.divider()
st.sidebar.header("🔐 Accès Membre")
# ... (Logique de connexion habituelle)
if not st.session_state.logged_in:
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
    if st.sidebar.button("Connexion"):
        st.session_state.logged_in = True
        st.session_state.display_name = u
        st.rerun()

sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)

# --- 5. CALCULS MÉTÉO ---
@st.cache_data
def obtenir_coords(ville):
    g = geocoder.osm(ville)
    return (g.lat, g.lng) if g and g.ok else (47.06, -0.88)

lat, lon = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- 6. PAGE PRINCIPALE ---
# Ici, on utilise la variable de session qui a été mise à jour par le GPX
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

st.header(f"🌤️ Prévisions à {st.session_state.nom_ville}")
if 'hourly' in data_m:
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = data_m['hourly']['temperature_2m'][h]
        v = data_m['hourly']['windspeed_10m'][h]
        p = data_m['hourly']['precipitation_probability'][h]
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        with cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**\n<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h")

st.divider()

# --- 7. SECTION CARTE ---
if pts_gpx:
    st.header(f"🗺️ Parcours : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400, key="map_gpx")
