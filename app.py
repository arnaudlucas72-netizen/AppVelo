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

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach IA Cyclisme", page_icon="🚴", layout="wide")

# 1. INITIALISATION CRITIQUE
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"

# Connexion Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("⚠️ Erreur de connexion au Cloud.")

# --- FONCTIONS TECHNIQUES ---
def hacher_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

@st.cache_data
def obtenir_coords(ville):
    try:
        g = geocoder.osm(ville)
        if g and g.ok: return g.lat, g.lng, True
    except: pass
    return 47.06, -0.88, False

# --- BARRE LATÉRALE ---
st.sidebar.header("🔐 Accès Membre")
# ... (Logique de connexion identique)
input_pseudo = st.sidebar.text_input("Pseudo").strip()
input_password = st.sidebar.text_input("Mot de passe", type="password").strip()
if st.sidebar.button("Connexion"):
    if input_pseudo and input_password:
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        user_key = f"{input_pseudo}_{hacher_password(input_password)}"
        if user_key in df_all['user'].astype(str).str.strip().values:
            st.session_state.logged_in = True
            st.session_state.user_id = user_key
            st.session_state.display_name = input_pseudo
            st.rerun()

st.sidebar.divider()
st.sidebar.header("🌍 Localisation & GPX")

# CHARGEMENT GPX
f_gpx = st.sidebar.file_uploader("📂 Charger un GPX", type=['gpx'], key="gpx_loader")

pts_gpx = None
if f_gpx:
    # On parse le GPX immédiatement
    gpx_data = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_data.tracks for s in t.segments for p in s.points]
    
    if pts_gpx:
        # On cherche la ville de départ (Soullans)
        try:
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_detectee = g_inv.city if g_inv.city else g_inv.town
            
            if ville_detectee and ville_detectee != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_detectee
                st.rerun() # Relance immédiate pour mettre à jour le titre et la météo
        except:
            pass

# Widget Ville (Source de vérité : st.session_state.nom_ville)
ville_saisie = st.sidebar.text_input("📍 Ville", value=st.session_state.nom_ville)

# Si l'utilisateur change la ville à la main
if ville_saisie != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_saisie
    st.rerun()

sf = st.sidebar.slider("🌡️ Sens. Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sens. Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sens. Pluie", 0, 10, 7)

# --- CALCULS ---
lat, lon, _ = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- AFFICHAGE PRINCIPAL ---
# ICI LE TITRE QUI DOIT CHANGER
st.title(f"🚴 Coach IA & Météo : {st.session_state.nom_ville}")

st.header(f"🌤️ Prévisions à {st.session_state.nom_ville}")
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

# ... (Le reste du code IA et Carte reste identique)
if pts_gpx:
    st.subheader(f"🗺️ Tracé à {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
