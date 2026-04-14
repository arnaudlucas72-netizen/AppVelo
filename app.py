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

# --- 2. LOGIQUE GPX PRIORITAIRE (AVANT TOUT) ---
# On place le widget dans la sidebar tout de suite
st.sidebar.header("🌍 Localisation & Parcours")
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX", type=['gpx'], key="main_gpx")

# Valeur par défaut
ville_finale = "Cholet"
pts_gpx = None

if f_gpx:
    try:
        # On parse le fichier immédiatement
        gpx_parsed = gpxpy.parse(f_gpx)
        pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
        
        if pts_gpx:
            # On détecte la ville du fichier (Soullans)
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_trouvee = g_inv.city if g_inv.city else g_inv.town
            if ville_trouvee:
                ville_finale = ville_trouvee
    except:
        pass

# On synchronise la session avec ce qu'on vient de trouver
st.session_state.nom_ville = ville_finale

# --- 3. BARRE LATÉRALE (SUITE) ---
# Le champ texte affiche la ville finale (Soullans si GPX, sinon Cholet)
ville_input = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_input
    st.rerun()

st.sidebar.divider()
st.sidebar.header("🔐 Accès Membre")
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

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
    st.sidebar.write(f"✅ Membre : {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

sf = st.sidebar.slider("🌡️ Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Pluie", 0, 10, 7)

# --- 4. CALCULS MÉTÉO ---
@st.cache_data
def obtenir_coords(ville):
    g = geocoder.osm(ville)
    return (g.lat, g.lng) if g and g.ok else (47.06, -0.88)

lat, lon = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- 5. AFFICHAGE (TITRE ENFIN SYNCHRONISÉ) ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

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

# --- 6. SECTION IA ---
if st.session_state.logged_in:
    st.header(f"🤖 Analyse Performance")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        df_user = df_all[df_all['user'].astype(str) == st.session_state.user_id]
        if len(df_user) >= 3:
            model = RandomForestRegressor(n_estimators=100)
            model.fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
            pred = model.predict([[data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]]])[0]
            st.success(f"🎯 Puissance estimée : **{int(pred)} Watts**")
    except: pass

# --- 7. SECTION CARTE ---
if pts_gpx:
    st.header(f"🗺️ Parcours : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
