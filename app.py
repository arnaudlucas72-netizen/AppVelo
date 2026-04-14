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

# --- 1. CONFIGURATION & STYLE (BLOCS COMPACTS) ---
st.set_page_config(page_title="Coach IA", layout="wide", page_icon="🚴")

st.markdown("""
    <style>
        .main .block-container {
            max-width: 1000px;
            padding-top: 1rem;
        }
        /* Bloc de score forcé en largeur fixe pour éviter l'étalement */
        .score-card {
            width: 140px; 
            margin: auto;
            text-align: center; 
            border: 1px solid #eee; 
            padding: 10px; 
            border-radius: 12px; 
            background: #fdfdfd; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        h1 {font-size: 1.8rem !important;}
        h2 {font-size: 1.2rem !important; color: #444;}
        .stButton>button {height: 2.5em; border-radius: 8px;}
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
        st.markdown(f"### {titre}")
        # Utilisation de colonnes avec espacement pour centrer les blocs fixes
        cols = st.columns([1,1,1,1,2]) # La 5ème colonne absorbe le surplus de place
        for i, h in enumerate([10, 13, 16, 19]):
            t, v, p = data_meteo['hourly']['temperature_2m'][h], data_meteo['hourly']['windspeed_10m'][h], data_meteo['hourly']['precipitation_probability'][h]
            malus = ((12 - t) * s_froid if t < 12 else 0) + (v * (s_vent / 10)) + (p * (s_pluie / 10))
            score = int(max(0, min(100, 100 - malus)))
            couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
            with cols[i]:
                st.markdown(f"""
                <div class="score-card">
                    <b style="font-size:0.85em; color:#888;">{h}h00</b><br>
                    <b style="color:{couleur}; font-size:1.5rem;">{score}</b><br>
                    <div style="font-size:0.8em; line-height:1.4; margin-top:5px; border-top: 1px solid #f5f5f5; padding-top:5px;">
                        🌡️ <b>{t}°C</b><br>💨 {v}km/h<br>🌧️ {p}%
                    </div>
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
    
    st.divider()
    f_gpx = st.file_uploader("Tracé GPX", type=['gpx'])
    
    st.divider()
    membre_on = st.checkbox("Espace Membre", value=True)
    if membre_on:
        u = st.text_input("Pseudo", key="user_p")
        p = st.text_input("Pass", type="password", key="pass_p")
        
        c1, c2 = st.columns(2)
        if c1.button("➕ Créer"):
            if u and p:
                try:
                    u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                    conn = st.connection("gsheets", type=GSheetsConnection)
                    df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                    new_u = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'cardio': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                    conn.update(worksheet="Performances", data=pd.concat([df, new_u], ignore_index=True))
                    st.success("OK")
                except: st.error("Erreur")
        
        if u and p:
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df_f = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                ud = df_f[df_f['user'] == u_id]
                if not ud.empty:
                    sc = int(min(100, (len(ud)*2) + (ud['temp'].max()-ud['temp'].min())*2))
                    st.write(f"🧠 Fiabilité IA : {sc}%")
                    st.progress(sc/100)
            except: pass

# --- 3. CONTENU CENTRAL ---
st.title(f"🚴 Coach IA : {ville_choisie}")

# Météo Ville
g_local = geocoder_robuste(ville_choisie)
lat_l, lon_l = (g_local.lat, g_local.lng) if g_local else (47.06, -0.88)
w_local_h = afficher_blocs_score(obtenir_meteo(lat_l, lon_l), f"Météo {ville_choisie}", s_froid, s_vent, s_pluie)

# Météo Parcours
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
        st_folium(m, width=900, height=300, key="map_v")

# Enregistrement
if membre_on and u and p:
    st.divider()
    st.subheader("📝 Enregistrer une sortie")
    t1, t2 = st.tabs(["Saisie Manuelle", "Analyse CSV"])
    v_w, v_h = 200, 140
    
    with t2:
        f_csv = st.file_uploader("CSV", type=['csv'], label_visibility="collapsed")
        if f_csv:
            try:
                d = pd.read_csv(f_csv); cw = [c for c in d.columns if 'watt' in c.lower() or 'power' in c.lower()]
                if cw: v_w = int(d[cw[0]].mean())
                st.caption(f"Détecté : {v_w}W")
            except: pass
            
    with t1:
        c = st.columns([2, 2, 2, 1])
        w_in = c[0].number_input("Watts", 0, 1000, v_w)
        hr_in = c[1].number_input("Cardio", 0, 250, v_h)
        h_idx = c[2].selectbox("Heure", [10, 13, 16, 19])
        if c[3].button("💾"):
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                target = w_p_h if w_p_h else w_local_h
                new = {'user': u_id, 'temp': target['temperature_2m'][h_idx], 'wind': target['windspeed_10m'][h_idx], 'hum': 50, 'watts': w_in, 'cardio': hr_in, 'date': datetime.now().strftime("%Y-%m-%d")}
                conn.update(worksheet="Performances", data=pd.concat([df, pd.DataFrame([new])], ignore_index=True))
                st.success("OK"); st.rerun()
            except: st.error("Erreur")
