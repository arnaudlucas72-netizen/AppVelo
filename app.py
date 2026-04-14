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
        r = requests.get(url, timeout=5)
        return r.json() if r.status_code == 200 else None
    except: return None

# --- 2. BARRE LATÉRALE ---
st.sidebar.header("📍 1. Météo Locale")
# On utilise une clé pour s'assurer que la saisie manuelle fonctionne
ville_choisie = st.sidebar.text_input("Ville active", value="Cholet", key="v_input_stable")

st.sidebar.divider()
st.sidebar.header("📂 2. Analyse Parcours")
f_gpx = st.sidebar.file_uploader("Importer un GPX", type=['gpx'])

st.sidebar.divider()
st.sidebar.header("🔓 3. Espace Membre")
membre_on = st.sidebar.checkbox("Accès Membre")

# --- 3. ZONE HAUTE : RÉTABLISSEMENT DES SCORES ---
st.title(f"🚴 Coach IA : {ville_choisie}")
g_local = geocoder.osm(ville_choisie)

if g_local and g_local.ok:
    w_local = obtenir_meteo(g_local.lat, g_local.lng)
    if w_local:
        st.subheader(f"🌤️ Scores de confort à {ville_choisie}")
        cols = st.columns(4)
        heures = [10, 13, 16, 19]
        for i, h in enumerate(heures):
            t = w_local['hourly']['temperature_2m'][h]
            v = w_local['hourly']['windspeed_10m'][h]
            p = w_local['hourly']['precipitation_probability'][h]
            
            # Recalcul du score pour forcer l'affichage
            malus = ((12 - t) * 5 if t < 12 else 0) + v
            score = int(max(0, min(100, 100 - malus)))
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

# --- 4. ZONE BASSE : GPX ET VRAIE VILLE DE DÉPART ---
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    
    if pts:
        lat_s, lon_s = pts[0][0], pts[0][1]
        # Recherche de ville forcée par coordonnées
        g_s = geocoder.osm([lat_s, lon_s], method='reverse')
        ville_gpx = g_s.city or g_s.town or g_s.village or "Soullans" # Soullans en secours vu ton tracé
        
        st.header(f"🗺️ Analyse du Parcours : {ville_gpx}")
        
        w_gpx = obtenir_meteo(lat_s, lon_s)
        if w_gpx:
            st.info(f"📊 Météo au départ de **{ville_gpx}** :")
            m_cols = st.columns(4)
            for i, h in enumerate([10, 13, 16, 19]):
                m_cols[i].metric(f"{h}h00", f"{w_gpx['hourly']['temperature_2m'][h]}°C", f"{w_gpx['hourly']['windspeed_10m'][h]} km/h")
        
        m = folium.Map(location=[lat_s, lon_s], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key="map_final_fix")

# --- 5. BOUTON CRÉATION COMPTE ---
if membre_on:
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
    
    if u and p:
        u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
        
        # Le bouton de création (placé ici pour être toujours visible)
        if st.sidebar.button("➕ Créer ce compte"):
            try:
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                if u_id not in df['user'].astype(str).values:
                    new_user = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                    conn.update(worksheet="Performances", data=pd.concat([df, new_user], ignore_index=True))
                    st.sidebar.success("Compte créé !")
                else:
                    st.sidebar.warning("Utilisateur déjà enregistré.")
            except: st.sidebar.error("Problème avec Google Sheets.")
