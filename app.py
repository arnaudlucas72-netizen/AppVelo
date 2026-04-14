import streamlit as st
import requests
import geocoder
import gpxpy
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime
import math
import plotly.express as px
from sklearn.ensemble import RandomForestRegressor
import joblib
import os

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach Vélo IA Pro", page_icon="🚴", layout="wide")

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

# --- LOGIQUE IA & DIVERSITÉ ---
def analyser_diversite(df):
    if df.empty: return 0
    # On crée des catégories pour vérifier la couverture des conditions
    t_bins = pd.cut(df['temp'], bins=[-10, 10, 22, 50], labels=['Froid', 'Bon', 'Chaud'])
    w_bins = pd.cut(df['wind'], bins=[0, 15, 100], labels=['Calme', 'Venté'])
    h_bins = pd.cut(df['hum'], bins=[0, 50, 100], labels=['Sec', 'Humide'])
    
    # Calcul du nombre de combinaisons uniques explorées
    combis = df.groupby([t_bins, w_bins, h_bins], observed=False).size()
    nb_remplies = (combis > 0).sum()
    
    # Score de fiabilité : 12 combinaisons possibles (3x2x2)
    score = int((nb_remplies / 12) * 100)
    return min(100, score)

def entrainer_ia_evoluee(df_nouveau, t_ext, v_ext, h_ext):
    history_file = 'historique_perf.csv'
    
    # Préparation de la nouvelle donnée
    stats_sortie = {
        'temp': df_nouveau[df_nouveau['watts'] > 0]['temp'].mean() if 'temp' in df_nouveau.columns else t_ext,
        'wind': v_ext,
        'hum': h_ext,
        'watts': df_nouveau[df_nouveau['watts'] > 0]['watts'].mean()
    }
    new_entry = pd.DataFrame([stats_sortie])
    
    if os.path.exists(history_file):
        hist_df = pd.read_csv(history_file)
        hist_df = pd.concat([hist_df, new_entry]).drop_duplicates()
    else:
        hist_df = new_entry
        
    hist_df.to_csv(history_file, index=False)
    
    # Entraînement sur les 3 facteurs
    X = hist_df[['temp', 'wind', 'hum']]
    y = hist_df['watts']
    
    if len(hist_df) > 1:
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        joblib.dump(model, 'modele_velo_v2.pkl')
    return hist_df

# --- RÉCUPÉRATION MÉTÉO ---
nom_ville = st.sidebar.text_input("📍 Ville", "Cholet")
sf, sv, sp = st.sidebar.slider("🌡️ Sens. Froid", 0,10,5), st.sidebar.slider("💨 Sens. Vent", 0,10,5), st.sidebar.slider("🌧️ Sens. Pluie", 0,10,7)

lat, lon, _ = obtenir_coords(nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- INTERFACE IA (TOUJOURS VISIBLE) ---
st.title("🚴 Coach IA : Analyse & Prédiction")

hist_file = 'historique_perf.csv'
col_info1, col_info2 = st.columns([1, 2])

if os.path.exists(hist_file):
    df_hist = pd.read_csv(hist_file)
    fiabilite = analyser_diversite(df_hist)
    
    with col_info1:
        st.metric("Fiabilité IA (Diversité)", f"{fiabilite}%")
        st.progress(fiabilite / 100)
        st.caption(f"Basé sur {len(df_hist)} conditions météo distinctes.")

    if os.path.exists('modele_velo_v2.pkl'):
        model = joblib.load('modele_velo_v2.pkl')
        t_13, v_13, h_13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t_13, v_13, h_13]])[0]
        with col_info2:
            st.success(f"🎯 **Estimation IA pour 13h** ({t_13}°C, {v_13}km/h vent) : **{int(pred)} Watts**")
            if fiabilite < 70:
                st.info("💡 Pour augmenter la fiabilité, enregistrez des sorties sous d'autres météos (froid, vent fort, etc).")
else:
    st.warning("🤖 L'IA est en attente de données. Chargez un CSV pour l'initialiser.")

st.divider()

# --- ZONE DE CHARGEMENT ---
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_gpx = st.file_uploader("🗺️ Charger un tracé (GPX)", type=['gpx'])
with col_f2:
    f_csv = st.file_uploader("📈 Mémoriser une sortie (CSV)", type=['csv'])

if f_csv:
    df_new = pd.read_csv(f_csv)
    df_new.columns = [c.lower().strip() for c in df_new.columns]
    if st.button("🧠 Enregistrer cette expérience"):
        # On utilise la météo actuelle pour le vent/humidité si non présents dans le CSV
        t_now = data_m['hourly']['temperature_2m'][12]
        v_now = data_m['hourly']['windspeed_10m'][12]
        h_now = data_m['hourly']['relative_humidity_2m'][12]
        entrainer_ia_evoluee(df_new, t_now, v_now, h_now)
        st.rerun()

# --- RÉSUMÉ MÉTÉO & CARTOGRAPHIE ---
st.header(f"🌤️ Prévisions à {nom_ville}")
c_met = st.columns(4)
for i, h in enumerate([10, 13, 16, 19]):
    t, v, p = data_m['hourly']['temperature_2m'][h], data_m['hourly']['windspeed_10m'][h], data_m['hourly']['precipitation_probability'][h]
    sc = calculer_score_meteo(t, v, p, sf, sv, sp)
    c_met[i].metric(f"{h}h00", f"{sc}/100", f"{t}°C | {v}km/h")

if f_gpx:
    gpx = gpxpy.parse(f_gpx)
    pts = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
    m = folium.Map(location=pts[0], zoom_start=12)
    folium.PolyLine(pts, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
