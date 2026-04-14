import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import geocoder
import gpxpy
import folium
from streamlit_folium import st_folium
from datetime import datetime
import hashlib
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Coach IA Cyclisme", layout="wide", page_icon="🚴")

@st.cache_data(ttl=600)
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability,relative_humidity_2m&forecast_days=1"
    try:
        r = requests.get(url, timeout=5)
        return r.json() if r.status_code == 200 else None
    except: return None

def geocoder_robuste(query, reverse=False):
    try:
        g = geocoder.arcgis(query, method='reverse' if reverse else 'geocode')
        if g and g.ok: return g
    except: pass
    return None

def afficher_blocs_score(data_meteo, titre_section):
    if data_meteo and 'hourly' in data_meteo:
        st.subheader(titre_section)
        cols = st.columns(4)
        for i, h in enumerate([10, 13, 16, 19]):
            t = data_meteo['hourly']['temperature_2m'][h]
            v = data_meteo['hourly']['windspeed_10m'][h]
            p = data_meteo['hourly']['precipitation_probability'][h]
            
            malus = ((12 - t) * 5 if t < 12 else 0) + v + (p / 2)
            score = int(max(0, min(100, 100 - malus)))
            couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
            
            with cols[i]:
                st.markdown(f"""
                <div style="text-align: center; border: 1px solid #ddd; padding: 15px; border-radius: 12px; background-color: #fcfcfc;">
                    <h4 style="margin:0; color: #666;">{h}h00</h4>
                    <h2 style="color:{couleur}; margin:10px 0;">{score}/100</h2>
                    <p style="margin:0; font-size: 0.9em;">🌡️ <b>{t}°C</b> | 💨 {v} km/h</p>
                </div>
                """, unsafe_allow_html=True)
        return data_meteo['hourly']
    return None

# --- 2. BARRE LATÉRALE ---
st.sidebar.header("📍 1. Météo Locale")
ville_choisie = st.sidebar.text_input("Ville active", value="Cholet", key="v_input")

st.sidebar.divider()
st.sidebar.header("📂 2. Analyse Parcours")
f_gpx = st.sidebar.file_uploader("Importer un tracé (GPX)", type=['gpx'], key="gpx_up")

st.sidebar.divider()
st.sidebar.header("🔓 3. Espace Membre")
membre_on = st.sidebar.checkbox("Accès Membre")

# --- 3. ZONE HAUTE : SCORES VILLE ---
st.title(f"🚴 Coach IA : {ville_choisie}")
g_local = geocoder_robuste(ville_choisie)
lat_l, lon_l = (g_local.lat, g_local.lng) if g_local else (47.06, -0.88)
w_local_data = obtenir_meteo(lat_l, lon_l)
w_local_h = afficher_blocs_score(w_local_data, f"🌤️ Scores de confort à {ville_choisie}")

st.divider()

# --- 4. ZONE BASSE : PARCOURS ---
lat_p, lon_p, v_p = None, None, "Soullans"
w_p_h = None
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts:
        lat_p, lon_p = pts[0][0], pts[0][1]
        g_p = geocoder_robuste([lat_p, lon_s], reverse=True) if 'lon_s' in locals() else geocoder_robuste([lat_p, pts[0][1]], reverse=True)
        v_p = getattr(g_p, 'city', None) or "Soullans"
        st.header(f"🗺️ Analyse du Parcours : {v_p}")
        w_p_h = afficher_blocs_score(obtenir_meteo(lat_p, pts[0][1]), f"📊 Scores sur le parcours ({v_p})")
        m = folium.Map(location=[lat_p, pts[0][1]], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key=f"map_{v_p}")

# --- 5. ENREGISTREMENT & IMPORT DONNÉES (CSV) ---
if membre_on:
    u = st.sidebar.text_input("Pseudo", key="u_f")
    p = st.sidebar.text_input("Pass", type="password", key="p_f")
    
    if u and p:
        st.divider()
        st.header("📝 Enregistrer une activité")
        
        tab1, tab2 = st.tabs(["Saisie Manuelle", "Import de fichier (CSV/FIT)"])
        
        with tab1:
            c1, c2, c3 = st.columns(3)
            with c1: w_in = st.number_input("Watts Moyens", min_value=0, value=200)
            with c2: hr_in = st.number_input("Cardio Moyen", min_value=0, value=140)
            with c3: h_idx = st.selectbox("Heure de la sortie", [10, 13, 16, 19], key="h_man")
        
        with tab2:
            f_data = st.file_uploader("Importer vos données (Cardio, Power...)", type=['csv', 'fit', 'tcx'], key="data_up")
            if f_data:
                st.success(f"Fichier {f_data.name} prêt pour l'analyse d'efficacité.")
                # Ici on pourra parser le CSV pour extraire auto les watts/cardio
        
        if st.button("💾 Sauvegarder dans l'historique"):
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                
                # Météo référente
                target_w = w_p_h if f_gpx and w_p_h else w_local_h
                
                new_entry = {
                    'user': u_id,
                    'temp': target_w['temperature_2m'][h_idx],
                    'wind': target_w['windspeed_10m'][h_idx],
                    'hum': target_w['relative_humidity_2m'][h_idx],
                    'watts': w_in,
                    'cardio': hr_in,
                    'date': datetime.now().strftime("%Y-%m-%d")
                }
                
                updated_df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
                conn.update(worksheet="Performances", data=updated_df)
                st.success("Activité enregistrée avec succès !")
            except Exception as e:
                st.error(f"Erreur : {e}")
