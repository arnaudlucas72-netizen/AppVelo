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

# --- 2. INITIALISATION ET DÉTECTION GPX (AVANT TOUT AFFICHAGE) ---
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# On crée le téléchargeur de fichier tout de suite pour intercepter la ville
# On le met dans la sidebar mais on traite le résultat ICI
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="gpx_detector")

pts_gpx = None
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts_gpx:
        try:
            # Recherche de la ville du point de départ (Soullans)
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_gpx = g_inv.city if g_inv.city else g_inv.town
            
            # SI LA VILLE DÉTECTÉE EST DIFFÉRENTE : ON ÉCRASE ET ON RELANCE
            if ville_gpx and ville_gpx != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_gpx
                st.rerun() # Le script repart du haut avec la nouvelle ville
        except:
            pass

# --- 3. BARRE LATÉRALE (SUITE) ---
st.sidebar.divider()
st.sidebar.header("🌍 Localisation")

# Le champ texte affiche la ville de la session (Cholet ou Soullans si GPX chargé)
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

st.sidebar.divider()
st.sidebar.header("🔐 Accès Membre")
if not st.session_state.logged_in:
    input_pseudo = st.sidebar.text_input("Pseudo").strip()
    input_password = st.sidebar.text_input("Mot de passe", type="password").strip()
    if st.sidebar.button("Connexion"):
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            user_key = f"{input_pseudo}_{hashlib.sha256(str.encode(input_password)).hexdigest()}"
            if user_key in df_all['user'].astype(str).values:
                st.session_state.logged_in = True
                st.session_state.user_id = user_key
                st.session_state.display_name = input_pseudo
                st.rerun()
        except:
            st.sidebar.error("Erreur de connexion.")
else:
    st.sidebar.write(f"✅ Membre : {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)

# --- 4. CALCULS MÉTEO ---
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

# --- 5. AFFICHAGE DE LA PAGE ---

# LE TITRE UTILISE MAINTENANT LA VARIABLE MISE À JOUR PAR LE GPX EN HAUT
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

# SECTION IA
if st.session_state.logged_in:
    st.header(f"🤖 Analyse Performance : {st.session_state.display_name}")
    # (Logique IA ici...)
    st.info("Statistiques et prédictions basées sur votre historique.")
else:
    st.info("👋 Connectez-vous pour activer l'analyse IA de vos Watts.")

st.divider()

# SECTION CARTE
if pts_gpx:
    st.header(f"🗺️ Parcours détecté : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
