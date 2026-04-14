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
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Coach IA Cyclisme", layout="wide", page_icon="🚴")

@st.cache_data(ttl=600)
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url, timeout=5)
        return r.json() if r.status_code == 200 else None
    except: return None

def geocoder_robuste(query, reverse=False):
    """Utilise ArcGIS pour éviter les blocages de géolocalisation"""
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
            # Calcul du score : Malus si froid, malus si vent, malus si pluie
            malus = ((12 - t) * 5 if t < 12 else 0) + (v * 1.2) + (p / 2)
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

u, p, apprentissage_total = "", "", 0
if membre_on:
    u = st.sidebar.text_input("Pseudo", key="u_f")
    p = st.sidebar.text_input("Pass", type="password", key="p_f")
    
    if u and p:
        try:
            u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_full = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            user_data = df_full[df_full['user'] == u_id]
            
            if not user_data.empty:
                # LOGIQUE D'APPRENTISSAGE BASÉE SUR LA DIVERSITÉ
                s_vol = min(len(user_data) * 2, 25) # Volume (25%)
                s_meteo = min((user_data['temp'].max() - user_data['temp'].min()) * 2, 40) # Delta Temp (40%)
                s_vent = min((user_data['wind'].max() - user_data['wind'].min()) * 2, 20) # Delta Vent (20%)
                s_geo = 15 if len(user_data) > 5 else 5 # Geo (15%)
                
                apprentissage_total = int(min(100, s_vol + s_meteo + s_vent + s_geo))
                st.sidebar.divider()
                st.sidebar.write(f"🧠 **Fiabilité de l'IA : {apprentissage_total}%**")
                st.sidebar.progress(apprentissage_total / 100)
                st.sidebar.caption(f"{len(user_data)} sorties enregistrées")
        except: pass

    if st.sidebar.button("➕ Créer ce compte"):
        if u and p:
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                new_u = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'cardio': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_u], ignore_index=True))
                st.sidebar.success("Compte créé !")
            except: st.sidebar.error("Erreur GSheets")

# --- 3. ZONE PRINCIPALE : SCORES VILLE ---
st.title(f"🚴 Coach IA : {ville_choisie}")
g_local = geocoder_robuste(ville_choisie)
lat_l, lon_l = (g_local.lat, g_local.lng) if g_local else (47.06, -0.88)
w_local_h = afficher_blocs_score(obtenir_meteo(lat_l, lon_l), f"🌤️ Scores de confort à {ville_choisie}")

st.divider()

# --- 4. ZONE PARCOURS ---
lat_p, lon_p, w_p_h = None, None, None
if f_gpx:
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    if pts:
        lat_p, lon_p = pts[0][0], pts[0][1]
        g_p = geocoder_robuste([lat_p, lon_p], reverse=True)
        v_p = getattr(g_p, 'city', None) or "Soullans"
        st.header(f"🗺️ Analyse du Parcours : {v_p}")
        w_p_h = afficher_blocs_score(obtenir_meteo(lat_p, lon_p), f"📊 Scores sur le parcours ({v_p})")
        m = folium.Map(location=[lat_p, lon_p], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key=f"map_{v_p}")

# --- 5. ZONE ENREGISTREMENT & ANALYSE CSV ---
if membre_on and u and p:
    st.divider()
    st.header("📝 Enregistrer une activité")
    t1, t2 = st.tabs(["Saisie Manuelle", "Analyse de fichier (CSV)"])
    val_watts, val_hr = 200, 140

    with t2:
        f_csv = st.file_uploader("Importer vos données (.csv)", type=['csv'])
        if f_csv:
            try:
                data_df = pd.read_csv(f_csv)
                col_w = [c for c in data_df.columns if any(x in c.lower() for x in ['watt', 'power'])]
                col_h = [c for c in data_df.columns if any(x in c.lower() for x in ['heart', 'hr', 'puls'])]
                if col_w: val_watts = int(data_df[col_w[0]].mean())
                if col_h: val_hr = int(data_df[col_h[0]].mean())
                st.success(f"✅ Données détectées : {val_watts}W | {val_hr} BPM")
            except: st.error("Erreur de lecture du fichier.")

    with t1:
        c1, c2, c3 = st.columns(3)
        w_in = c1.number_input("Watts Moyens", min_value=0, value=val_watts)
        hr_in = c2.number_input("Cardio Moyen", min_value=0, value=val_hr)
        h_idx = c3.selectbox("Heure de la sortie", [10, 13, 16, 19])
        
        if st.button("💾 Sauvegarder dans l'historique"):
            try:
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                target_w = w_p_h if w_p_h else w_local_h
                new_entry = {
                    'user': u_id, 'temp': target_w['temperature_2m'][h_idx],
                    'wind': target_w['windspeed_10m'][h_idx],
                    'hum': target_w.get('relative_humidity_2m', [50]*24)[h_idx],
                    'watts': w_in, 'cardio': hr_in, 'date': datetime.now().strftime("%Y-%m-%d")
                }
                conn.update(worksheet="Performances", data=pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True))
                st.success("Activité enregistrée !")
                st.rerun()
            except Exception as e: st.error(f"Erreur : {e}")
