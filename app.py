import streamlit as st
import requests
import geocoder
import gpxpy
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import math
import plotly.express as px
from sklearn.ensemble import RandomForestRegressor
import joblib
import os

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach Vélo Intelligent", page_icon="🚴", layout="wide")

# --- FONCTIONS TECHNIQUES ---
def calculer_cap(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360

@st.cache_data
def obtenir_coords_securise(ville):
    try:
        g = geocoder.osm(ville)
        if g and g.ok: return g.lat, g.lng, True
    except: pass
    return 47.06, -0.88, False

def calculer_score_meteo(t, v, p, s_froid, s_vent, s_pluie):
    score = 100
    if t < 12: score -= (12 * s_froid / 5)
    score -= (v * 0.8 * s_vent / 5)
    score -= (p * 1.2 * s_pluie / 5)
    return max(0, min(100, int(score)))

# --- LOGIQUE IA ---
def entrainer_ia(df):
    # On essaie de charger les données historiques pour cumuler l'apprentissage
    history_file = 'historique_perf.csv'
    new_data = pd.DataFrame([{
        'temp': df[df['watts'] > 0]['temp'].mean(),
        'watts': df[df['watts'] > 0]['watts'].mean()
    }])
    
    if os.path.exists(history_file):
        hist_df = pd.read_csv(history_file)
        hist_df = pd.concat([hist_df, new_data]).drop_duplicates()
    else:
        hist_df = new_data
    
    hist_df.to_csv(history_file, index=False)
    
    X = hist_df[['temp']]
    y = hist_df['watts']
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    joblib.dump(model, 'modele_velo.pkl')
    return len(hist_df)

# --- BARRE LATÉRALE ---
st.sidebar.header("⚙️ Configuration")
nom_ville_saisie = st.sidebar.text_input("📍 Ville par défaut", "Cholet")
s_froid = st.sidebar.slider("🌡️ Sensibilité Froid", 0, 10, 5)
s_vent = st.sidebar.slider("💨 Sensibilité Vent", 0, 10, 5)
s_pluie = st.sidebar.slider("🌧️ Sensibilité Pluie", 0, 10, 7)

# --- DONNÉES DE BASE ---
lat_ref, lon_ref, ok = obtenir_coords_securise(nom_ville_saisie)
res_meteo = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat_ref}&longitude={lon_ref}&hourly=temperature_2m,windspeed_10m,precipitation_probability&forecast_days=1").json()

# --- PAGE PRINCIPALE ---
st.title("🚴 Mon Assistant IA Cycliste")

# --- SECTION IA PERMANENTE ---
st.header("🤖 État du Coach Virtuel")
col_ia1, col_ia2 = st.columns([1, 2])

if os.path.exists('historique_perf.csv'):
    hist_df = pd.read_csv('historique_perf.csv')
    nb_sorties = len(hist_df)
    fiabilite = min(100, nb_sorties * 10) # 10 sorties = 100%
    
    with col_ia1:
        st.metric("Fiabilité du Coach", f"{fiabilite}%")
        st.caption(f"Basé sur {nb_sorties} sorties enregistrées")
    
    if os.path.exists('modele_velo.pkl'):
        model = joblib.load('modele_velo.pkl')
        temp_13h = res_meteo['hourly']['temperature_2m'][13]
        pred_watts = model.predict([[temp_13h]])[0]
        with col_ia2:
            st.info(f"💡 **Estimation pour aujourd'hui** : À 13h ({temp_13h}°C), ta puissance cible est de **{int(pred_watts)}W**.")
else:
    st.warning("📥 Le Coach n'a pas encore de mémoire. Charge une sortie (CSV) ci-dessous pour l'activer.")

st.divider()

# --- CHARGEMENT FICHIERS ---
c_u1, c_u2 = st.columns(2)
with c_u1:
    fichier_gpx = st.file_uploader("🗺️ Tracer un parcours (GPX)", type=['gpx'])
with c_u2:
    fichier_perf = st.file_uploader("📈 Enregistrer une sortie (CSV)", type=['csv'])

if fichier_perf:
    df = pd.read_csv(fichier_perf)
    df.columns = [c.lower().strip() for c in df.columns]
    if st.button("🧠 Mémoriser cette performance"):
        nb = entrainer_ia(df)
        st.success(f"Sortie enregistrée ! Mémoire : {nb} fichiers.")
        st.rerun() # Pour mettre à jour l'affichage IA en haut

# --- RÉSUMÉ MÉTÉO ---
st.header(f"🌤️ Météo du jour à {nom_ville_saisie}")
if 'hourly' in res_meteo:
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t, v, p = res_meteo['hourly']['temperature_2m'][h], res_meteo['hourly']['windspeed_10m'][h], res_meteo['hourly']['precipitation_probability'][h]
        score = calculer_score_meteo(t, v, p, s_froid, s_vent, s_pluie)
        cols[i].metric(f"{h}h00", f"{score}/100", f"{t}°C")

# --- CARTE SI GPX ---
if fichier_gpx:
    st.header("🗺️ Vue du tracé")
    gpx = gpxpy.parse(fichier_gpx)
    pts = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
    m = folium.Map(location=pts[0], zoom_start=12)
    folium.PolyLine(pts, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
