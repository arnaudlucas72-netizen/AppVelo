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
st.set_page_config(page_title="Coach IA Cyclisme", layout="wide", page_icon="🚴")

# Initialisation persistante
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'coords' not in st.session_state:
    st.session_state.coords = (47.06, -0.88)
if 'pts_gpx' not in st.session_state:
    st.session_state.pts_gpx = None

# --- 2. BARRE LATÉRALE : ACTIONS PRIORITAIRES ---
st.sidebar.header("🚀 Actions")

# BOUTON CRÉATION DE COMPTE (Toujours en haut, visible partout)
if st.sidebar.button("➕ CRÉER UN COMPTE", help="Crée un profil avec le pseudo/pass saisis plus bas"):
    if "u_id_calc" in st.session_state:
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            if st.session_state.u_id_calc in df['user'].astype(str).values:
                st.sidebar.warning("Compte déjà existant.")
            else:
                new_row = pd.DataFrame([{'user': st.session_state.u_id_calc, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_row], ignore_index=True))
                st.sidebar.success("Compte créé !")
        except:
            st.sidebar.error("Erreur de base de données.")
    else:
        st.sidebar.info("Saisissez un Pseudo et Pass en bas d'abord.")

st.sidebar.divider()

# IMPORT GPX
f_gpx = st.sidebar.file_uploader("📂 Importer GPX", type=['gpx'])

if f_gpx is not None:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts and pts != st.session_state.pts_gpx:
        st.session_state.pts_gpx = pts
        st.session_state.coords = (pts[0][0], pts[0][1])
        g_inv = geocoder.osm(st.session_state.coords, method='reverse')
        if g_inv and g_inv.ok:
            st.session_state.nom_ville = g_inv.city if g_inv.city else g_inv.town
        st.rerun()

# --- 3. LOGIQUE MÉTÉO ---
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url)
        return r.json() if r.status_code == 200 else None
    except: return None

weather = obtenir_meteo(st.session_state.coords[0], st.session_state.coords[1])

# --- 4. AFFICHAGE PRINCIPAL ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

if weather and 'hourly' in weather:
    st.subheader(f"🌤️ Prévisions à {st.session_state.nom_ville}")
    cols = st.columns(4)
    heures = [10, 13, 16, 19]
    for i, h in enumerate(heures):
        t, v, p = weather['hourly']['temperature_2m'][h], weather['hourly']['windspeed_10m'][h], weather['hourly']['precipitation_probability'][h]
        # Score simplifié pour le test
        score = int(max(0, min(100, 100 - (12-t)*2 - v)))
        with cols[i]:
            st.markdown(f'<div style="text-align:center; border:1px solid #ddd; padding:20px; border-radius:15px; background:#fcfcfc;"><h3>{h}h00</h3><h1 style="color:#28a745;">{score}/100</h1><p>{t}°C | {v}km/h</p></div>', unsafe_allow_html=True)

st.divider()

# --- 5. ESPACE MEMBRE ---
st.sidebar.divider()
if st.sidebar.checkbox("🔓 Accès Membre"):
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
    if u and p:
        u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
        st.session_state.u_id_calc = u_id # Stocké pour le bouton en haut
        
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            user_data = df[df['user'].astype(str) == u_id]
            if not user_data.empty:
                st.sidebar.success(f"Connecté : {u}")
                if len(user_data) >= 3:
                    model = RandomForestRegressor(n_estimators=100).fit(user_data[['temp', 'wind', 'hum']], user_data['watts'])
                    pred = model.predict([[weather['hourly']['temperature_2m'][13], weather['hourly']['windspeed_10m'][13], weather['hourly']['relative_humidity_2m'][13]]])[0]
                    st.metric("🎯 Puissance estimée", f"{int(pred)} W")
            else:
                st.sidebar.warning("Inconnu. Cliquez sur + en haut.")
        except: pass

# --- 6. CARTE ---
if st.session_state.pts_gpx:
    st.subheader("🗺️ Tracé du parcours")
    m = folium.Map(location=st.session_state.coords, zoom_start=12)
    folium.PolyLine(st.session_state.pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1200, height=500, key="map_final")
    
