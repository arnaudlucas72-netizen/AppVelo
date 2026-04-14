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
import joblib
import os

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach IA Multi-User", page_icon="🚴", layout="wide")

# Connexion au Google Sheet
conn = st.connection("gsheets", type=GSheetsConnection)

# --- IDENTIFICATION ---
st.sidebar.header("👤 Connexion")
user_name = st.sidebar.text_input("Ton Prénom / Pseudo", "").strip().capitalize()

if not user_name:
    st.info("👋 Bienvenue ! Entre ton prénom dans la barre latérale pour accéder à ton espace personnel.")
    st.stop()

# --- CHARGEMENT DES DONNÉES UTILISATEUR ---
@st.cache_data(ttl=600)
def charger_donnees_user(name):
    try:
        df = conn.read(worksheet="Performances")
        return df[df['user'] == name]
    except:
        return pd.DataFrame(columns=['user', 'temp', 'wind', 'hum', 'watts', 'date'])

df_user = charger_donnees_user(user_name)

# --- LOGIQUE IA ---
def analyser_diversite_pro(df):
    if len(df) < 3: return 0
    t_bins = pd.cut(df['temp'], bins=[-10, 10, 22, 50], labels=['Froid', 'Bon', 'Chaud'])
    w_bins = pd.cut(df['wind'], bins=[0, 15, 100], labels=['Calme', 'Venté'])
    # On simplifie à 6 combinaisons pour le début (3T x 2V)
    nb_remplies = len(df.groupby([t_bins, w_bins], observed=False).size().reset_index(name='c').query('c > 0'))
    return min(100, int((nb_remplies / 6) * 100))

def entrainer_ia_user(df_hist):
    if len(df_hist) >= 3:
        X = df_hist[['temp', 'wind', 'hum']]
        y = df_hist['watts']
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        return model
    return None

# --- INTERFACE ---
st.title(f"🚴 Coach IA : Espace de {user_name}")

# Calcul météo actuelle pour prédiction
lat, lon = 47.06, -0.88 # Cholet par défaut
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m&forecast_days=1"
data_m = requests.get(api_url).json()

# Header IA
col_ia1, col_ia2 = st.columns([1, 2])
fiabilite = analyser_diversite_pro(df_user)
model_user = entrainer_ia_user(df_user)

with col_ia1:
    st.metric("Ta Fiabilité IA", f"{fiabilite}%")
    st.progress(fiabilite / 100)

with col_ia2:
    if model_user:
        t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
        pred = model_user.predict([[t13, v13, h13]])[0]
        st.success(f"🎯 **Estimation pour ta sortie de 13h** : **{int(pred)} Watts**")
    else:
        st.warning("IA en apprentissage... Charge au moins 3 sorties pour activer les prédictions.")

st.divider()

# --- ACTIONS ---
c1, c2 = st.columns(2)
with c1:
    f_csv = st.file_uploader("📈 Enregistrer une nouvelle sortie (CSV)", type=['csv'])

if f_csv and user_name:
    df_new = pd.read_csv(f_csv)
    df_new.columns = [c.lower().strip() for c in df_new.columns]
    
    if st.button(f"💾 Sauvegarder dans mon profil {user_name}"):
        # Préparation de la ligne
        nouvelle_ligne = pd.DataFrame([{
            'user': user_name,
            'temp': df_new[df_new['watts']>0]['temp'].mean(),
            'wind': data_m['hourly']['windspeed_10m'][12],
            'hum': data_m['hourly']['relative_humidity_2m'][12],
            'watts': df_new[df_new['watts']>0]['watts'].mean(),
            'date': datetime.now().strftime("%Y-%m-%d")
        }])
        
        # Mise à jour du Google Sheet
        df_complet = conn.read(worksheet="Performances")
        df_final = pd.concat([df_complet, nouvelle_ligne], ignore_index=True)
        conn.update(worksheet="Performances", data=df_final)
        
        st.success("Données envoyées au cloud ! Ton profil est à jour.")
        st.cache_data.clear() # Force le rechargement
        st.rerun()

# --- RÉSUMÉ HISTORIQUE ---
if not df_user.empty:
    with st.expander("📂 Voir mon historique de performances"):
        st.dataframe(df_user[['date', 'temp', 'wind', 'watts']].sort_values(by='date', ascending=False))
