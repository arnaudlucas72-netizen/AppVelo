import streamlit as st
import requests
import geocoder
import gpxpy
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import math
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach Vélo Intégral", page_icon="🚴", layout="wide")

# --- FONCTIONS TECHNIQUES ---
def calculer_cap(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def evaluation_vent(cap_cycliste, dir_vent):
    diff = abs(cap_cycliste - dir_vent)
    if diff > 180: diff = 360 - diff
    return diff

@st.cache_data
def obtenir_coords_securise(ville):
    try:
        g = geocoder.osm(ville)
        if g and g.ok: return g.lat, g.lng, True
    except: pass
    return 47.06, -0.88, False

def calculer_score_meteo(t, v, raf, hum, p, sens_f, sens_v, sens_p):
    score = 100
    if t < 10 and hum > 80: score -= (20 * sens_f / 5) 
    elif t < 5: score -= (35 * sens_f / 5)
    elif t < 12: score -= (12 * sens_f / 5)
    impact_vent = (v * 0.6) + (raf * 1.4)
    score -= (impact_vent * (sens_v / 5) * 0.9)
    score -= (p * (sens_p / 5) * 1.5)
    return max(0, min(100, int(score)))

def obtenir_donnees_soleil(lat, lon):
    try:
        url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0"
        res = requests.get(url).json()
        sunrise = datetime.fromisoformat(res['results']['sunrise']).astimezone()
        sunset = datetime.fromisoformat(res['results']['sunset']).astimezone()
        return sunrise, sunset
    except: return None, None

# --- BARRE LATÉRALE ---
st.sidebar.header("⚙️ Configuration")
nom_ville_saisie = st.sidebar.text_input("📍 Ville par défaut", "Cholet")
s_froid = st.sidebar.slider("🌡️ Sensibilité Froid", 0, 10, 5)
s_vent = st.sidebar.slider("💨 Sensibilité Vent", 0, 10, 5)
s_pluie = st.sidebar.slider("🌧️ Sensibilité Pluie", 0, 10, 7)

# --- LOGIQUE DE POSITION ---
lat_ref, lon_ref, ok = obtenir_coords_securise(nom_ville_saisie)

# --- PAGE PRINCIPALE ---
st.title("🚴 Mon Assistant Cycliste")

col_u1, col_u2 = st.columns(2)
with col_u1:
    fichier_gpx = st.file_uploader("🗺️ Charger tracé GPX", type=['gpx'])
with col_u2:
    fichier_perf = st.file_uploader("📈 Charger données Streams (CSV)", type=['csv'])

st.divider()

# --- RÉCUPÉRATION MÉTÉO ---
url_meteo = f"https://api.open-meteo.com/v1/forecast?latitude={lat_ref}&longitude={lon_ref}&hourly=temperature_2m,windspeed_10m,wind_gusts_10m,winddirection_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
res_meteo = requests.get(url_meteo).json()
sunrise, sunset = obtenir_donnees_soleil(lat_ref, lon_ref)

# --- 1. PERFORMANCE & DÉNIVELÉ ---
if fichier_perf:
    st.header("📈 Analyse de la Sortie")
    df = pd.read_csv(fichier_perf)
    df.columns = [c.lower().strip() for c in df.columns]
    
    c1, c2, c3, c4 = st.columns(4)
    if 'watts' in df.columns:
        c1.metric("Puissance Moy", f"{int(df['watts'].mean())} W")
    if 'velocity_smooth' in df.columns:
        v_kmh = df['velocity_smooth'].mean() * 3.6
        c2.metric("Vitesse Moy", f"{v_kmh:.1f} km/h")
    if 'altitude' in df.columns:
        diffs = df['altitude'].diff().fillna(0)
        d_plus = int(diffs[diffs > 0].sum())
        c3.metric("Dénivelé Positif (D+)", f"{d_plus} m")
        c4.metric("Altitude Max", f"{int(df['altitude'].max())} m")
        
        fig = px.area(df, y='altitude', title="Profil Altitométrique", color_discrete_sequence=['#ef4444'])
        st.plotly_chart(fig, use_container_width=True)

# --- 2. CARTE GPX ---
if fichier_gpx:
    st.header("🗺️ Direction du vent sur le tracé")
    gpx = gpxpy.parse(fichier_gpx)
    pts = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
    h_now = datetime.now().hour
    v_dir = res_meteo['hourly']['winddirection_10m'][h_now]
    
    m = folium.Map(location=pts[0], zoom_start=12)
    folium.PolyLine(pts, color="blue", weight=4).add_to(m)
    folium.Marker(location=pts[0], icon=folium.Icon(color='red', icon='arrow-up', angle=v_dir)).add_to(m)
    st_folium(m, width=1000, height=400)

# --- 3. PRÉVISIONS MÉTÉO COMPLÈTES ---
st.divider()
st.header(f"🌤️ Prévisions Météo : {nom_ville_saisie}")

if 'hourly' in res_meteo:
    creneaux = [10, 13, 16, 19]
    cols = st.columns(4)
    
    for i, h in enumerate(creneaux):
        t = res_meteo['hourly']['temperature_2m'][h]
        v = res_meteo['hourly']['windspeed_10m'][h]
        raf = res_meteo['hourly']['wind_gusts_10m'][h]
        hum = res_meteo['hourly']['relative_humidity_2m'][h]
        p = res_meteo['hourly']['precipitation_probability'][h]
        
        score = calculer_score_meteo(t, v, raf, hum, p, s_froid, s_vent, s_pluie)
        
        with cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"### {h}h00")
            st.markdown(f"<h1 style='color:{color};'>{score}</h1>", unsafe_allow_html=True)
            # Retour des infos détaillées
            st.write(f"🌡️ **{t}°C**")
            st.write(f"💨 **{v} km/h** (Raf. {raf})")
            st.write(f"🌧️ **{p}%** pluie")
            st.progress(score/100)

# --- 4. EPHEMERIDE ---
if sunset:
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.write(f"🌅 Lever du soleil : **{sunrise.strftime('%H:%M')}**")
    col2.write(f"🌇 Coucher du soleil : **{sunset.strftime('%H:%M')}**")
    if datetime.now().astimezone() > (sunset - timedelta(hours=1)):
        col3.warning("⚠️ Visibilité en baisse bientôt !")

st.divider()
with st.expander("ℹ️ À propos de cette application"):
    with open("README.md", "r", encoding="utf-8") as f:
        st.markdown(f.read())
        
