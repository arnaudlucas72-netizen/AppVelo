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

# --- 1. CONFIGURATION & STYLE COMPACT ---
st.set_page_config(page_title="Coach IA", layout="wide", page_icon="🚴")

# CSS pour supprimer les marges blanches inutiles
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 0rem; padding-left: 2rem; padding-right: 2rem;}
        h1 {margin-top: -1rem; font-size: 1.8rem !important;}
        h2 {font-size: 1.4rem !important;}
        h3 {font-size: 1.1rem !important;}
        .stTabs [data-baseweb="tab-list"] {gap: 2px;}
        .stTabs [data-baseweb="tab"] {padding: 4px 10px;}
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=600)
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url, timeout=5)
        return r.json() if r.status_code == 200 else None
    except: return None

def geocoder_robuste(query, reverse=False):
    try:
        g = geocoder.arcgis(query, method='reverse' if reverse else 'geocode')
        return g if g and g.ok else None
    except: return None

def afficher_blocs_score(data_meteo, titre, s_froid, s_vent, s_pluie):
    if data_meteo and 'hourly' in data_meteo:
        st.markdown(f"**{titre}**")
        cols = st.columns(4)
        for i, h in enumerate([10, 13, 16, 19]):
            t, v, p = data_meteo['hourly']['temperature_2m'][h], data_meteo['hourly']['windspeed_10m'][h], data_meteo['hourly']['precipitation_probability'][h]
            malus = ((12 - t) * s_froid if t < 12 else 0) + (v * (s_vent / 10)) + (p * (s_pluie / 10))
            score = int(max(0, min(100, 100 - malus)))
            couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
            with cols[i]:
                st.markdown(f"""
                <div style="text-align: center; border: 1px solid #eee; padding: 8px; border-radius: 8px; background: #f9f9f9; line-height:1.2;">
                    <b style="font-size:0.8em; color:#666;">{h}h</b><br>
                    <b style="color:{couleur}; font-size:1.1rem;">{score}/100</b><br>
                    <span style="font-size:0.75em;">{t}° | {v}k | {p}%</span>
                </div>
                """, unsafe_allow_html=True)
        return data_meteo['hourly']
    return None

# --- 2. BARRE LATÉRALE (Paramètres) ---
with st.sidebar:
    st.header("📍 Configuration")
    ville_choisie = st.text_input("Ville", value="Cholet", key="v_input")
    
    with st.expander("⚙️ Sensibilité", expanded=False):
        s_froid = st.slider("Froid", 1, 10, 5)
        s_vent = st.slider("Vent", 1, 20, 10)
        s_pluie = st.slider("Pluie", 1, 10, 5)
    
    f_gpx = st.file_uploader("Tracé GPX", type=['gpx'])
    
    membre_on = st.checkbox("Espace Membre")
    u, p, user_data = "", "", None
    if membre_on:
        u = st.text_input("Pseudo")
        p = st.text_input("Pass", type="password")
        if u and p:
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df_full = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                user_data = df_full[df_full['user'] == u_id]
                if not user_data.empty:
                    sc_ia = int(min(100, (len(user_data)*2) + (user_data['temp'].max()-user_data['temp'].min())*2))
                    st.write(f"🧠 Fiabilité IA : {sc_ia}%")
                    st.progress(sc_ia/100)
            except: pass

# --- 3. MISE EN PAGE PRINCIPALE ---
col_left, col_right = st.columns([1, 1]) # Divise l'écran en deux

with col_left:
    st.title(f"🚴 Coach IA : {ville_choisie}")
    g_local = geocoder_robuste(ville_choisie)
    lat_l, lon_l = (g_local.lat, g_local.lng) if g_local else (47.06, -0.88)
    w_local_h = afficher_blocs_score(obtenir_meteo(lat_l, lon_l), f"Météo {ville_choisie}", s_froid, s_vent, s_pluie)

    if membre_on and u and p:
        st.markdown("---")
        t1, t2 = st.tabs(["Saisie", "CSV"])
        v_w, v_h = 200, 140
        with t2:
            f_csv = st.file_uploader("Fichier CSV", type=['csv'], label_visibility="collapsed")
            if f_csv: 
                try:
                    d = pd.read_csv(f_csv)
                    cw = [c for c in d.columns if 'watt' in c.lower() or 'power' in c.lower()]
                    if cw: v_w = int(d[cw[0]].mean())
                    st.caption(f"Détecté: {v_w}W")
                except: pass
        with t1:
            cx = st.columns(3)
            w_in = cx[0].number_input("Watts", 0, 1000, v_w)
            hr_in = cx[1].number_input("Cardio", 0, 250, v_h)
            h_idx = cx[2].selectbox("Heure", [10, 13, 16, 19])
            if st.button("💾 Sauver"):
                # ... (Logique de sauvegarde identique) ...
                st.success("OK")

with col_right:
    if f_gpx:
        gpx_parsed = gpxpy.parse(f_gpx.getvalue())
        pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
        if pts:
            lat_p, lon_p = pts[0][0], pts[0][1]
            g_p = geocoder_robuste([lat_p, lon_p], reverse=True)
            v_p = getattr(g_p, 'city', None) or "Parcours"
            
            # Scores du parcours condensés sous la carte ou au dessus
            w_p_h = afficher_blocs_score(obtenir_meteo(lat_p, pts[0][1]), f"Météo sur parcours ({v_p})", s_froid, s_vent, s_pluie)
            
            m = folium.Map(location=[lat_p, pts[0][1]], zoom_start=11)
            folium.PolyLine(pts, color="blue", weight=3).add_to(m)
            st_folium(m, width=500, height=350, key="map_compact")
    else:
        st.info("💡 Importez un GPX pour voir la carte et les scores ici.")
