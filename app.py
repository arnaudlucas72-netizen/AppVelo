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

# --- 1. CONFIGURATION & STYLE CONDENSÉ ---
st.set_page_config(page_title="Coach IA", layout="wide", page_icon="🚴")

st.markdown("""
    <style>
        .block-container {padding-top: 0.5rem; padding-bottom: 0rem;}
        h1 {font-size: 1.5rem !important; margin-bottom: 0.5rem;}
        h3 {font-size: 1rem !important; margin-bottom: 0.2rem;}
        .stButton>button {width: 100%; border-radius: 5px; height: 2em;}
        div[data-testid="stExpander"] {border: none !important; margin-bottom: -10px;}
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
        st.write(f"**{titre}**")
        cols = st.columns(4)
        for i, h in enumerate([10, 13, 16, 19]):
            t, v, p = data_meteo['hourly']['temperature_2m'][h], data_meteo['hourly']['windspeed_10m'][h], data_meteo['hourly']['precipitation_probability'][h]
            malus = ((12 - t) * s_froid if t < 12 else 0) + (v * (s_vent / 10)) + (p * (s_pluie / 10))
            score = int(max(0, min(100, 100 - malus)))
            couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
            with cols[i]:
                st.markdown(f"""
                <div style="text-align: center; border: 1px solid #eee; padding: 5px; border-radius: 8px; background: #f9f9f9; line-height:1.1;">
                    <b style="font-size:0.7em; color:#666;">{h}h</b><br>
                    <b style="color:{couleur}; font-size:1rem;">{score}/100</b><br>
                    <span style="font-size:0.7em;">{t}°|{v}k|{p}%</span>
                </div>
                """, unsafe_allow_html=True)
        return data_meteo['hourly']
    return None

# --- 2. BARRE LATÉRALE ---
with st.sidebar:
    st.header("📍 Config")
    ville_choisie = st.text_input("Ville", value="Cholet")
    
    with st.expander("⚙️ Sensibilité", expanded=False):
        s_froid = st.slider("Froid", 1, 10, 5)
        s_vent = st.slider("Vent", 1, 20, 10)
        s_pluie = st.slider("Pluie", 1, 10, 5)
    
    f_gpx = st.file_uploader("GPX", type=['gpx'])
    
    st.divider()
    membre_on = st.checkbox("Espace Membre", value=True)
    u, p = "", ""
    if membre_on:
        u = st.text_input("Pseudo", key="user_p")
        p = st.text_input("Pass", type="password", key="pass_p")
        
        # BOUTON CRÉATION TOUJOURS LÀ
        if st.button("➕ Créer compte"):
            if u and p:
                try:
                    u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                    conn = st.connection("gsheets", type=GSheetsConnection)
                    df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                    new_u = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'cardio': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                    conn.update(worksheet="Performances", data=pd.concat([df, new_u], ignore_index=True))
                    st.success("Compte OK")
                except: st.error("Erreur GSheets")
        
        if u and p:
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df_f = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                ud = df_f[df_f['user'] == u_id]
                if not ud.empty:
                    sc = int(min(100, (len(ud)*2) + (ud['temp'].max()-ud['temp'].min())*2))
                    st.write(f"🧠 Fiabilité : {sc}%")
                    st.progress(sc/100)
            except: pass

# --- 3. AFFICHAGE CENTRAL (VERTICAL COMPACT) ---
st.title(f"🚴 Coach IA : {ville_choisie}")

# Bloc Météo Ville
g_local = geocoder_robuste(ville_choisie)
lat_l, lon_l = (g_local.lat, g_local.lng) if g_local else (47.06, -0.88)
w_local_h = afficher_blocs_score(obtenir_meteo(lat_l, lon_l), f"Météo {ville_choisie}", s_froid, s_vent, s_pluie)

# Bloc Parcours (si GPX)
lat_p, lon_p, w_p_h = None, None, None
if f_gpx:
    st.divider()
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts:
        lat_p, lon_p = pts[0][0], pts[0][1]
        w_p_h = afficher_blocs_score(obtenir_meteo(lat_p, lon_p), "Météo sur le parcours", s_froid, s_vent, s_pluie)
        m = folium.Map(location=[lat_p, lon_p], zoom_start=11)
        folium.PolyLine(pts, color="blue", weight=3).add_to(m)
        st_folium(m, width=1000, height=250, key="map_v")

# Bloc Enregistrement
if membre_on and u and p:
    st.divider()
    t1, t2 = st.tabs(["📝 Saisie", "📊 CSV"])
    v_w, v_h = 200, 140
    with t2:
        f_csv = st.file_uploader("Fichier CSV", type=['csv'], label_visibility="collapsed")
        if f_csv:
            try:
                d = pd.read_csv(f_csv)
                cw = [c for c in d.columns if any(x in c.lower() for x in ['watt', 'power'])]
                if cw: v_w = int(d[cw[0]].mean())
                st.caption(f"Détecté : {v_w} Watts")
            except: pass
    with t1:
        c = st.columns(4)
        w_in = c[0].number_input("Watts", 0, 1000, v_w)
        hr_in = c[1].number_input("Cardio", 0, 250, v_h)
        h_idx = c[2].selectbox("Heure", [10, 13, 16, 19])
        if c[3].button("💾 Sauver"):
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                target = w_p_h if w_p_h else w_local_h
                new = {'user': u_id, 'temp': target['temperature_2m'][h_idx], 'wind': target['windspeed_10m'][h_idx], 'hum': 50, 'watts': w_in, 'cardio': hr_in, 'date': datetime.now().strftime("%Y-%m-%d")}
                conn.update(worksheet="Performances", data=pd.concat([df, pd.DataFrame([new])], ignore_index=True))
                st.success("Enregistré !")
                st.rerun()
            except: st.error("Erreur")
