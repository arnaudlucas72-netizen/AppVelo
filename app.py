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

# --- 1. BOUTON DE SECOURS (A UTILISER SI CA BLOQUE) ---
if st.sidebar.button("♻️ RÉINITIALISER TOUT"):
    for key in st.session_state.keys():
        del st.session_state[key]
    st.rerun()

# --- 2. CONFIGURATION & ETAT ---
st.set_page_config(page_title="Coach IA Cyclisme", layout="wide", page_icon="🚴")

if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'coords' not in st.session_state:
    st.session_state.coords = (47.06, -0.88)
if 'pts_gpx' not in st.session_state:
    st.session_state.pts_gpx = None

# --- 3. LOGIQUE GPX ---
st.sidebar.header("🌍 Configuration")
f_gpx = st.sidebar.file_uploader("📂 Importer GPX", type=['gpx'])

if f_gpx is not None:
    try:
        gpx_parsed = gpxpy.parse(f_gpx.getvalue())
        pts = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
        if pts and pts != st.session_state.pts_gpx:
            st.session_state.pts_gpx = pts
            st.session_state.coords = (pts[0][0], pts[0][1])
            g_inv = geocoder.osm(st.session_state.coords, method='reverse')
            if g_inv and g_inv.ok:
                st.session_state.nom_ville = g_inv.city if g_inv.city else g_inv.town
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erreur GPX : {e}")

# SAISIE MANUELLE (Sans widget de session pour éviter le blocage)
ville_saisie = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville)
if ville_saisie != st.session_state.nom_ville:
    g = geocoder.osm(ville_saisie)
    if g and g.ok:
        st.session_state.coords = (g.lat, g.lng)
        st.session_state.nom_ville = ville_saisie
        st.rerun()

# --- 4. RÉCUPÉRATION MÉTÉO ---
def obtenir_meteo(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
    try:
        r = requests.get(url)
        return r.json() if r.status_code == 200 else None
    except: return None

weather = obtenir_meteo(st.session_state.coords[0], st.session_state.coords[1])

# --- 5. RÉGLAGES ---
st.sidebar.divider()
sf = st.sidebar.slider("🌡️ Sensibilité Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sensibilité Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sensibilité Pluie", 0, 10, 7)

# --- 6. AFFICHAGE PRINCIPAL ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

if weather and 'hourly' in weather:
    st.subheader(f"🌤️ Prévisions à {st.session_state.nom_ville}")
    cols = st.columns(4)
    heures = [10, 13, 16, 19]
    for i, h in enumerate(heures):
        temp, vent, pluie = weather['hourly']['temperature_2m'][h], weather['hourly']['windspeed_10m'][h], weather['hourly']['precipitation_probability'][h]
        # Algorithme original
        score = int(max(0, min(100, 100 - ((12-temp)*sf if temp<12 else 0) - (vent*(sv/5)) - (pluie*(sp/5)))))
        couleur = "#28a745" if score > 75 else "#fd7e14" if score > 45 else "#dc3545"
        with cols[i]:
            st.markdown(f"""
            <div style="text-align: center; border: 1px solid #ddd; padding: 20px; border-radius: 15px; background-color: #fcfcfc;">
                <h3 style="margin:0;">{h}h00</h3>
                <h1 style="color:{couleur}; font-size: 2.5em;">{score}/100</h1>
                <p>🌡️ <b>{temp}°C</b> | 💨 {vent} km/h</p>
            </div>
            """, unsafe_allow_html=True)

st.divider()

# --- 7. ESPACE MEMBRE & BOUTON COMPTE ---
if st.sidebar.checkbox("🔓 Accès Membre"):
    u = st.sidebar.text_input("Pseudo")
    p = st.sidebar.text_input("Pass", type="password")
    
    # LE BOUTON + (Positionné pour être inamovible)
    if st.sidebar.button("➕ Créer ce compte"):
        if u and p:
            try:
                conn = st.connection("gsheets", type=GSheetsConnection)
                df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
                u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
                new_user = pd.DataFrame([{'user': u_id, 'temp': 20, 'wind': 10, 'hum': 50, 'watts': 0, 'date': datetime.now().strftime("%Y-%m-%d")}])
                conn.update(worksheet="Performances", data=pd.concat([df, new_user], ignore_index=True))
                st.sidebar.success("Compte créé !")
            except Exception as e:
                st.sidebar.error("Erreur GSheets")
        else:
            st.sidebar.warning("Remplissez Pseudo/Pass")

    # Connexion IA
    if u and p:
        u_id = f"{u}_{hashlib.sha256(str.encode(p)).hexdigest()}"
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
            user_data = df[df['user'].astype(str) == u_id]
            if not user_data.empty:
                st.sidebar.success(f"Connecté : {u}")
                if len(user_data) >= 3:
                    model = RandomForestRegressor(n_estimators=100).fit(user_data[['temp', 'wind', 'hum']], user_data['watts'])
                    pred = model.predict([[weather['hourly']['temperature_2m'][13], weather['hourly']['windspeed_10m'][13], weather['hourly']['relative_humidity_2m'][13]]])[0]
                    st.metric("🎯 Puissance estimée", f"{int(pred)} W")
        except: pass

# --- 8. CARTE ---
if st.session_state.pts_gpx:
    st.subheader("🗺️ Tracé du parcours")
    m = folium.Map(location=st.session_state.coords, zoom_start=12)
    folium.PolyLine(st.session_state.pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1200, height=500, key="map_final")
    
