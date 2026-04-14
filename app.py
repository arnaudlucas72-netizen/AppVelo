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
import math

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach IA Multi-User", page_icon="🚴", layout="wide")

# Connexion au Google Sheet
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("⚠️ Connexion Google Sheets non configurée dans les Secrets.")

# --- FONCTIONS TECHNIQUES ---
@st.cache_data
def obtenir_coords(ville):
    try:
        g = geocoder.osm(ville)
        if g and g.ok: return g.lat, g.lng, True
    except: pass
    return 47.06, -0.88, False

def calculer_score_meteo(t, v, p, sf, sv, sp):
    score = 100
    if t < 12: score -= (12 * sf / 5)
    score -= (v * 0.8 * sv / 5)
    score -= (p * 1.2 * sp / 5)
    return max(0, min(100, int(score)))

# --- RÉCUPÉRATION MÉTÉO (VISIBLE PAR TOUS) ---
st.sidebar.header("⚙️ Configuration")
nom_ville = st.sidebar.text_input("📍 Ville", "Cholet")
sf, sv, sp = st.sidebar.slider("🌡️ Sens. Froid", 0,10,5), st.sidebar.slider("💨 Sens. Vent", 0,10,5), st.sidebar.slider("🌧️ Sens. Pluie", 0,10,7)

lat, lon, ok_coords = obtenir_coords(nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- PAGE PRINCIPALE ---
st.title("🚴 Assistant Cycliste & IA")

# --- 1. SECTION IA (CONDITIONNELLE AU NOM) ---
st.sidebar.divider()
user_name = st.sidebar.text_input("👤 Ton Prénom (pour l'IA)", "").strip().capitalize()

if user_name:
    st.header(f"🤖 Espace IA de {user_name}")
    
    # Chargement des données
    try:
        df_all = conn.read(worksheet="Performances")
        df_user = df_all[df_all['user'] == user_name]
    except:
        df_user = pd.DataFrame()

    col_ia1, col_ia2 = st.columns([1, 2])
    
    # Calcul Fiabilité
    fiabilite = 0
    if not df_user.empty and len(df_user) >= 3:
        t_bins = pd.cut(df_user['temp'], bins=[-10, 10, 22, 50], labels=['Froid', 'Bon', 'Chaud'])
        w_bins = pd.cut(df_user['wind'], bins=[0, 15, 100], labels=['Calme', 'Venté'])
        nb_remplies = len(df_user.groupby([t_bins, w_bins], observed=False).size().reset_index(name='c').query('c > 0'))
        fiabilite = min(100, int((nb_remplies / 6) * 100))
        
        # Entraînement & Prédiction
        X = df_user[['temp', 'wind', 'hum']]
        y = df_user['watts']
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        
        t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t13, v13, h13]])[0]
        
        with col_ia1:
            st.metric("Ta Fiabilité IA", f"{fiabilite}%")
            st.progress(fiabilite / 100)
        with col_ia2:
            st.success(f"🎯 **Estimation à 13h** : **{int(pred)} Watts**")
    else:
        st.info("💡 L'IA s'activera après avoir enregistré au moins 3 sorties avec ton prénom.")

    # Zone d'enregistrement
    with st.expander("📥 Enregistrer une nouvelle sortie dans ton profil"):
        f_csv = st.file_uploader("Charger CSV", type=['csv'], key="csv_upload")
        if f_csv and st.button(f"Mémoriser pour {user_name}"):
            df_new = pd.read_csv(f_csv)
            df_new.columns = [c.lower().strip() for c in df_new.columns]
            nouvelle_ligne = pd.DataFrame([{
                'user': user_name,
                'temp': df_new[df_new['watts']>0]['temp'].mean(),
                'wind': data_m['hourly']['windspeed_10m'][12],
                'hum': data_m['hourly']['relative_humidity_2m'][12],
                'watts': df_new[df_new['watts']>0]['watts'].mean(),
                'date': datetime.now().strftime("%Y-%m-%d")
            }])
            df_final = pd.concat([df_all, nouvelle_ligne], ignore_index=True)
            conn.update(worksheet="Performances", data=df_final)
            st.success("Donnée enregistrée !")
            st.cache_data.clear()
            st.rerun()
else:
    st.info("👈 Entre ton prénom dans la barre latérale pour activer ton coach IA personnel.")

st.divider()

# --- 2. PRÉVISIONS MÉTÉO (TOUJOURS VISIBLES) ---
st.header(f"🌤️ Prévisions Météo : {nom_ville}")
if 'hourly' in data_m:
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t, v, p = data_m['hourly']['temperature_2m'][h], data_m['hourly']['windspeed_10m'][h], data_m['hourly']['precipitation_probability'][h]
        score = calculer_score_meteo(t, v, p, sf, sv, sp)
        with cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**")
            st.markdown(f"<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h | {p}% pluie")

st.divider()

# --- 3. CARTE GPX ---
f_gpx = st.file_uploader("🗺️ Tracer un parcours (GPX)", type=['gpx'])
if f_gpx:
    gpx = gpxpy.parse(f_gpx)
    pts = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
    m = folium.Map(location=pts[0], zoom_start=12)
    folium.PolyLine(pts, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
