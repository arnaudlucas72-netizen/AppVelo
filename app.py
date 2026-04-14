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

# --- 2. GESTION DU GPX ET DE LA VILLE (AVANT TOUT) ---
# On récupère le fichier tout de suite
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="gpx_master")

# Logique de détermination de la ville
if f_gpx is not None:
    # Si un GPX est là, il écrase TOUT
    gpx_parsed = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
    ville_trouvee = g_inv.city if g_inv.city else g_inv.town
    st.session_state.ville_active = ville_trouvee
    st.session_state.parcours = pts_gpx
elif 'ville_active' not in st.session_state:
    # Ville par défaut UNIQUEMENT s'il n'y a pas de session
    st.session_state.ville_active = "Cholet"
    st.session_state.parcours = None

# --- 3. BARRE LATÉRALE ---
st.sidebar.header("🌍 Localisation")
# Champ texte synchronisé
nouveau_nom = st.sidebar.text_input("📍 Ville active", value=st.session_state.ville_active)
if nouveau_nom != st.session_state.ville_active:
    st.session_state.ville_active = nouveau_nom
    st.rerun()

st.sidebar.divider()
# Paramètres météo
sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)

# --- 4. CALCULS ---
@st.cache_data
def get_weather(ville):
    g = geocoder.osm(ville)
    if not g or not g.ok: return None
    url = f"https://api.open-meteo.com/v1/forecast?latitude={g.lat}&longitude={g.lng}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    return requests.get(url).json()

data_m = get_weather(st.session_state.ville_active)

# --- 5. AFFICHAGE (TITRE DYNAMIQUE) ---
st.title(f"🚴 Coach IA : {st.session_state.ville_active}")

st.header(f"🌤️ Prévisions à {st.session_state.ville_active}")

if data_m and 'hourly' in data_m:
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

# --- 6. SECTION CARTE ---
if st.session_state.parcours:
    st.divider()
    st.header(f"🗺️ Parcours : {st.session_state.ville_active}")
    m = folium.Map(location=st.session_state.parcours[0], zoom_start=12)
    folium.PolyLine(st.session_state.parcours, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400, key="map_unique")

# --- 7. CONNEXION & IA (Remise à la fin pour ne pas bloquer le titre) ---
st.sidebar.divider()
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.sidebar.expander("🔐 Connexion Membre"):
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
        
