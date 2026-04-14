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

@st.cache_data(ttl=600)
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None

# --- 2. BARRE LATÉRALE ---
st.sidebar.header("📍 1. Météo Locale")
ville_choisie = st.sidebar.text_input("Ville active", value="Cholet", key="v_stable")

st.sidebar.divider()
st.sidebar.header("📂 2. Analyse Parcours")
f_gpx = st.sidebar.file_uploader("Importer un GPX", type=['gpx'], key="gpx_drop")

st.sidebar.divider()
st.sidebar.header("🔓 3. Espace Membre")
membre_on = st.sidebar.checkbox("Accès Membre", key="m_on")

# --- 3. ZONE HAUTE : AFFICHAGE NATIF (SANS HTML) ---
st.title(f"🚴 Coach IA : {ville_choisie}")

g_local = geocoder.osm(ville_choisie)
if g_local and g_local.ok:
    data_w = obtenir_meteo(g_local.lat, g_local.lng)
    
    if data_w and 'hourly' in data_w:
        st.subheader(f"📊 Prévisions à {ville_choisie}")
        cols = st.columns(4)
        # On utilise les index directs de l'API pour 10h, 13h, 16h, 19h
        for i, h in enumerate([10, 13, 16, 19]):
            t = data_w['hourly']['temperature_2m'][h]
            v = data_w['hourly']['windspeed_10m'][h]
            p = data_w['hourly']['precipitation_probability'][h]
            
            # Calcul du score
            score = int(max(0, min(100, 100 - ((12-t)*5 if t<12 else 0) - v - (p/2))))
            
            with cols[i]:
                # Utilisation de metric (natif Streamlit) au lieu du HTML
                st.metric(label=f"🕒 {h}h00", value=f"{score}/100", delta=f"{t}°C")
                st.write(f"💨 {v} km/h | 🌧️ {p}%")
    else:
        st.warning("⚠️ Données météo indisponibles pour cette ville.")
else:
    st.error("📍 Ville non trouvée par le service de géolocalisation.")

st.divider()

# --- 4. ZONE BASSE : GPX ---
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts:
        lat_s, lon_s = pts[0][0], pts[0][1]
        g_s = geocoder.osm([lat_s, lon_s], method='reverse')
        v_gpx = g_s.city or g_s.town or "Soullans"
        
        st.header(f"🗺️ Analyse : {v_gpx}")
        w_g = obtenir_meteo(lat_s, lon_s)
        if w_g:
            mc = st.columns(4)
            for i, h in enumerate([10, 13, 16, 19]):
                mc[i].metric(f"{h}h00", f"{w_g['hourly']['temperature_2m'][h]}°C", f"{w_g['hourly']['windspeed_10m'][h]} km/h")
        
        m = folium.Map(location=[lat_s, lon_s], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key="map_v3")

# --- 5. ESPACE MEMBRE ---
if membre_on:
    if st.sidebar.button("➕ Créer ce compte", key="fix_btn"):
        u = st.session_state.get('u_f', '')
        p = st.session_state.get('p_f', '')
        if u and p:
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                new_row = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_row], ignore_index=True))
                st.sidebar.success("Compte créé !")
            except: st.sidebar.error("Erreur GSheets")
    
    st.sidebar.text_input("Pseudo", key="u_f")
    st.sidebar.text_input("Pass", type="password", key="p_f")

