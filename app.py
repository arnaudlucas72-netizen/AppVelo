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
        return r.json() if r.status_code == 200 else None
    except: return None

# --- 2. BARRE LATÉRALE ---
st.sidebar.header("📍 1. Météo Locale")
ville_choisie = st.sidebar.text_input("Ville active", value="Cholet", key="v_input_final")

st.sidebar.divider()
st.sidebar.header("📂 2. Analyse Parcours")
f_gpx = st.sidebar.file_uploader("Importer un GPX", type=['gpx'], key="gpx_uploader")

st.sidebar.divider()
st.sidebar.header("🔓 3. Espace Membre")
membre_on = st.sidebar.checkbox("Accès Membre")

# --- 3. ZONE HAUTE : SCORES (AVEC ROUE DE SECOURS) ---
st.title(f"🚴 Coach IA : {ville_choisie}")

g_local = geocoder.osm(ville_choisie)
if g_local and g_local.ok:
    lat_l, lon_l = g_local.lat, g_local.lng
else:
    lat_l, lon_l = 47.06, -0.88 # Cholet par défaut
    st.sidebar.warning("⚠️ Géoloc locale indisponible (Mode secours)")

w_local = obtenir_meteo(lat_l, lon_l)

if w_local and 'hourly' in w_local:
    st.subheader(f"🌤️ Scores de confort à {ville_choisie}")
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = w_local['hourly']['temperature_2m'][h]
        v = w_local['hourly']['windspeed_10m'][h]
        p = w_local['hourly']['precipitation_probability'][h]
        
        score = int(max(0, min(100, 100 - ((12-t)*5 if t<12 else 0) - v - (p/2))))
        couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
        
        with cols[i]:
            st.markdown(f"""
            <div style="text-align: center; border: 1px solid #ddd; padding: 20px; border-radius: 15px; background-color: #fcfcfc;">
                <h3 style="margin:0; color: #555;">{h}h00</h3>
                <h1 style="color:{couleur}; margin:15px 0; font-size: 2.5em;">{score}/100</h1>
                <p style="margin:5px 0;">🌡️ <b>{t}°C</b></p>
                <p style="margin:0; color: #666; font-size: 0.8em;">💨 {v} km/h | 🌧️ {p}%</p>
            </div>
            """, unsafe_allow_html=True)

st.divider()

# --- 4. ZONE BASSE : GPX + RETOUR DU NOM (SOULLANS) ---
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    
    if pts:
        lat_s, lon_s = pts[0][0], pts[0][1]
        
        # ON RÉCUPÈRE LE NOM DE LA VILLE DU GPX
        g_s = geocoder.osm([lat_s, lon_s], method='reverse')
        ville_gpx = g_s.city or g_s.town or g_s.village or "Lieu du parcours"
        
        st.header(f"🗺️ Analyse du Parcours : {ville_gpx}")
        
        w_gpx = obtenir_meteo(lat_s, lon_s)
        if w_gpx and 'hourly' in w_gpx:
            st.info(f"📊 Météo au départ de **{ville_gpx}**")
            m_cols = st.columns(4)
            for i, h in enumerate([10, 13, 16, 19]):
                tg, vg = w_gpx['hourly']['temperature_2m'][h], w_gpx['hourly']['windspeed_10m'][h]
                m_cols[i].metric(f"{h}h00", f"{tg}°C", f"{vg} km/h")
        
        m = folium.Map(location=[lat_s, lon_s], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key=f"map_{ville_gpx}")

# --- 5. ESPACE MEMBRE ---
if membre_on:
    if st.sidebar.button("➕ Créer ce compte", key="btn_create"):
        u, p = st.session_state.get('u_field',''), st.session_state.get('p_field','')
        if u and p:
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                new_data = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_data], ignore_index=True))
                st.sidebar.success("Compte créé !")
            except: st.sidebar.error("Erreur GSheets")

    st.sidebar.text_input("Pseudo", key="u_field")
    st.sidebar.text_input("Pass", type="password", key="p_field")
    
