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

def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url)
        return r.json() if r.status_code == 200 else None
    except: return None

# --- 2. BARRE LATÉRALE ---
st.sidebar.header("📍 1. Météo Locale")
# Changement de la clé pour forcer le rafraîchissement du texte
ville_active = st.sidebar.text_input("Ville active", value="Cholet", key="v_active_unique")

st.sidebar.divider()
st.sidebar.header("📂 2. Analyse Parcours")
f_gpx = st.sidebar.file_uploader("Importer un GPX", type=['gpx'], key="gpx_fix")

st.sidebar.divider()
st.sidebar.header("🔓 3. Espace Membre")
membre_on = st.sidebar.checkbox("Accès Membre", key="m_check")

# --- 3. ZONE HAUTE : SCORES (DÉBLOQUÉS) ---
st.title(f"🚴 Coach IA : {ville_active}")
g_local = geocoder.osm(ville_active)

if g_local and g_local.ok:
    w_local = obtenir_meteo(g_local.lat, g_local.lng)
    if w_local:
        st.subheader(f"🌤️ Prévisions et Scores à {ville_active}")
        cols = st.columns(4)
        heures = [10, 13, 16, 19]
        for i, h in enumerate(heures):
            t = w_local['hourly']['temperature_2m'][h]
            v = w_local['hourly']['windspeed_10m'][h]
            p = w_local['hourly']['precipitation_probability'][h]
            
            # Calcul du score avec affichage couleur
            score = int(max(0, min(100, 100 - ((12-t)*5 if t<12 else 0) - v)))
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

# --- 4. ZONE BASSE : GPX ---
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    
    if pts:
        lat_s, lon_s = pts[0][0], pts[0][1]
        # REVERSE GEOCODING FORCÉ
        g_s = geocoder.osm([lat_s, lon_s], method='reverse')
        ville_gpx = "Lieu inconnu"
        if g_s and g_s.ok:
            ville_gpx = g_s.city if g_s.city else (g_s.town if g_s.town else g_s.address)
        
        st.header(f"🗺️ Parcours au départ de : {ville_gpx}")
        
        w_gpx = obtenir_meteo(lat_s, lon_s)
        if w_gpx:
            st.info(f"📊 Météo au point de départ ({ville_gpx})")
            m_cols = st.columns(4)
            for i, h in enumerate([10, 13, 16, 19]):
                m_cols[i].metric(f"{h}h00", f"{w_gpx['hourly']['temperature_2m'][h]}°C", f"{w_gpx['hourly']['windspeed_10m'][h]} km/h")
        
        m = folium.Map(location=[lat_s, lon_s], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key=f"map_{ville_gpx}")

# --- 5. ESPACE MEMBRE & BOUTON + ---
if membre_on:
    u = st.sidebar.text_input("Pseudo", key="u_name")
    p = st.sidebar.text_input("Pass", type="password", key="u_pass")
    
    # BOUTON CRÉER : Toujours visible si Accès Membre est coché
    if st.sidebar.button("➕ Créer ce compte", key="btn_create_final"):
        if u and p:
            try:
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                new_row = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_row], ignore_index=True))
                st.sidebar.success("Compte créé avec succès !")
            except: st.sidebar.error("Erreur de connexion GSheets")
        else:
            st.sidebar.warning("Saisissez un pseudo et un mot de passe.")
            
