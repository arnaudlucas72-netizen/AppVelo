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
st.set_page_config(page_title="Coach IA Cyclisme", layout="wide")

if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'coords' not in st.session_state:
    st.session_state.coords = (47.06, -0.88) # Cholet par défaut

# --- 2. LOGIQUE GPX ---
st.sidebar.header("🌍 Configuration")
f_gpx = st.sidebar.file_uploader("📂 Importer GPX", type=['gpx'])

pts_gpx = None
if f_gpx:
    try:
        gpx_parsed = gpxpy.parse(f_gpx.getvalue())
        pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
        if pts_gpx:
            # Sécurité 1 : On récupère les coordonnées réelles du fichier
            st.session_state.coords = (pts_gpx[0][0], pts_gpx[0][1])
            
            # On tente de trouver le nom pour le titre
            g_inv = geocoder.osm(st.session_state.coords, method='reverse')
            if g_inv and g_inv.ok:
                ville_detectee = g_inv.city if g_inv.city else g_inv.town
                if ville_detectee:
                    st.session_state.nom_ville = ville_detectee
            st.rerun()
    except: pass

# Champ manuel pour changer de ville
ville_input = st.sidebar.text_input("📍 Ville / Lieu", value=st.session_state.nom_ville)
if ville_input != st.session_state.nom_ville:
    g = geocoder.osm(ville_input)
    if g and g.ok:
        st.session_state.coords = (g.lat, g.lng)
        st.session_state.nom_ville = ville_input
        st.rerun()

# --- 3. RÉCUPÉRATION MÉTÉO (BASÉE SUR COORDS) ---
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url)
        return r.json() if r.status_code == 200 else None
    except:
        return None

weather = obtenir_meteo(st.session_state.coords[0], st.session_state.coords[1])

# --- 4. RÉGLAGES ---
st.sidebar.divider()
sf = st.sidebar.slider("🌡️ Sensibilité Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sensibilité Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sensibilité Pluie", 0, 10, 7)

# --- 5. AFFICHAGE ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

if weather and 'hourly' in weather:
    st.subheader(f"🌤️ Prévisions et Scores")
    cols = st.columns(4)
    heures = [10, 13, 16, 19]
    
    for i, h in enumerate(heures):
        temp = weather['hourly']['temperature_2m'][h]
        vent = weather['hourly']['windspeed_10m'][h]
        pluie = weather['hourly']['precipitation_probability'][h]
        
        # Calcul du score
        malus_froid = (12 - temp) * sf if temp < 12 else 0
        malus_vent = vent * (sv / 5)
        malus_pluie = pluie * (sp / 5)
        score = int(max(0, min(100, 100 - malus_froid - malus_vent - malus_pluie)))
        
        couleur = "green" if score > 75 else "orange" if score > 45 else "red"
        with cols[i]:
            st.markdown(f"""
            <div style="text-align: center; border: 1px solid #ddd; padding: 15px; border-radius: 10px; background-color: #f9f9f9;">
                <h3 style="margin:0; color: #333;">{h}h00</h3>
                <h1 style="color:{couleur}; margin:10px 0;">{score}/100</h1>
                <p style="margin:0; font-size: 1.1em;">🌡️ <b>{temp}°C</b></p>
                <p style="margin:0; color: #666;">💨 {vent} km/h | 🌧️ {pluie}%</p>
            </div>
            """, unsafe_allow_html=True)
else:
    st.error("⚠️ Impossible de charger la météo. L'API est peut-être saturée.")

st.divider()

# --- 6. SECTION IA (GSheets) ---
if st.sidebar.checkbox("🔓 Espace Membre"):
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
    if u and p:
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Performances", ttl=0)
            u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
            user_data = df[df['user'].astype(str) == u_id]
            
            if not user_data.empty:
                st.success(f"Cycliste : {u}")
                if len(user_data) >= 3:
                    model = RandomForestRegressor(n_estimators=100).fit(user_data[['temp', 'wind', 'hum']], user_data['watts'])
                    t13, v13, h13 = weather['hourly']['temperature_2m'][13], weather['hourly']['windspeed_10m'][13], weather['hourly']['relative_humidity_2m'][13]
                    pred = model.predict([[t13, v13, h13]])[0]
                    st.metric("🎯 Puissance estimée (13h)", f"{int(pred)} Watts")
        except: pass

# --- 7. CARTE ---
if pts_gpx:
    st.subheader("🗺️ Tracé du parcours")
    m = folium.Map(location=st.session_state.coords, zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
    
