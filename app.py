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

# --- 2. BARRE LATÉRALE (CONTRÔLES) ---
st.sidebar.header("📍 1. Météo Locale")
ville_choisie = st.sidebar.text_input("Ville active", value="Cholet")

st.sidebar.divider()
st.sidebar.header("📂 2. Analyse Parcours")
f_gpx = st.sidebar.file_uploader("Importer un GPX", type=['gpx'])

st.sidebar.divider()
st.sidebar.header("🔓 3. Espace Membre")
membre_on = st.sidebar.checkbox("Accès Membre")

# --- 3. ZONE HAUTE : MÉTÉO DE LA VILLE ---
st.title(f"🚴 Coach IA : {ville_choisie}")
g_local = geocoder.osm(ville_choisie)

if g_local and g_local.ok:
    w_local = obtenir_meteo(g_local.lat, g_local.lng)
    if w_local:
        st.subheader(f"🌤️ Prévisions locales à {ville_choisie}")
        cols = st.columns(4)
        heures = [10, 13, 16, 19]
        for i, h in enumerate(heures):
            t = w_local['hourly']['temperature_2m'][h]
            v = w_local['hourly']['windspeed_10m'][h]
            p = w_local['hourly']['precipitation_probability'][h]
            
            # Score fixe pour la zone haute
            score = int(max(0, min(100, 100 - (12-t)*5 if t<12 else 100 - v)))
            couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
            
            with cols[i]:
                st.markdown(f"""
                <div style="text-align: center; border: 1px solid #ddd; padding: 15px; border-radius: 10px; background: #f9f9f9;">
                    <h4 style="margin:0;">{h}h00</h4>
                    <h2 style="color:{couleur};">{score}/100</h2>
                    <p style="font-size:0.9em;"><b>{t}°C</b> | {v} km/h</p>
                </div>
                """, unsafe_allow_html=True)

st.divider()

# --- 4. ZONE BASSE : ANALYSE GPX (Indépendante) ---
if f_gpx:
    st.header("🗺️ Analyse du Parcours")
    gpx_parsed = gpxpy.parse(f_gpx.getvalue())
    pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    
    if pts:
        lat_start, lon_start = pts[0][0], pts[0][1]
        g_start = geocoder.osm([lat_start, lon_start], method='reverse')
        ville_gpx = g_start.city if (g_start and g_start.city) else "Départ parcours"
        
        st.info(f"📍 Point de départ détecté : **{ville_gpx}**")
        
        # Météo spécifique au GPX
        w_gpx = obtenir_meteo(lat_start, lon_start)
        if w_gpx:
            st.write(f"📊 Météo sur le parcours ({ville_gpx}) :")
            m_cols = st.columns(4)
            for i, h in enumerate([10, 13, 16, 19]):
                t_g = w_gpx['hourly']['temperature_2m'][h]
                v_g = w_gpx['hourly']['windspeed_10m'][h]
                m_cols[i].metric(f"{h}h00", f"{t_g}°C", f"{v_g} km/h", delta_color="inverse")
        
        # Carte
        m = folium.Map(location=[lat_start, lon_start], zoom_start=12)
        folium.PolyLine(pts, color="blue", weight=4).add_to(m)
        st_folium(m, width=1100, height=400, key="map_gpx")
else:
    st.write("ℹ️ Chargez un fichier GPX dans la barre latérale pour analyser un parcours spécifique.")

# --- 5. LOGIQUE MEMBRE & BOUTON CRÉATION ---
if membre_on:
    st.sidebar.divider()
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
    
    if u and p:
        u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
        
        # Le bouton Créer est toujours là si les champs sont remplis
        if st.sidebar.button("➕ Créer ce compte"):
            try:
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                new_row = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_row], ignore_index=True))
                st.sidebar.success("Compte créé !")
            except: st.sidebar.error("Erreur GSheets")

        # IA (Utilise la météo de la VILLE ACTIVE du haut)
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            user_data = df[df['user'].astype(str) == u_id]
            if not user_data.empty:
                st.sidebar.success(f"Connecté : {u}")
                if len(user_data) >= 3 and w_local:
                    model = RandomForestRegressor(n_estimators=100).fit(user_data[['temp', 'wind', 'hum']], user_data['watts'])
                    pred = model.predict([[w_local['hourly']['temperature_2m'][13], w_local['hourly']['windspeed_10m'][13], w_local['hourly']['relative_humidity_2m'][13]]])[0]
                    st.metric("🎯 Puissance estimée", f"{int(pred)} W")
        except: pass
            
