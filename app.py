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

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach IA Cyclisme", page_icon="🚴", layout="wide")

# Connexion au Google Sheet
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("⚠️ Erreur de connexion au Cloud.")

# --- FONCTIONS TECHNIQUES ---
def hacher_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

@st.cache_data
def obtenir_coords(ville):
    try:
        g = geocoder.osm(ville)
        if g and g.ok: return g.lat, g.lng, True
    except: pass
    return 47.06, -0.88, False

# --- BARRE LATÉRALE : IDENTIFICATION ---
st.sidebar.header("🔐 Accès Membre")
pseudo = st.sidebar.text_input("Pseudo").strip()
password = st.sidebar.text_input("Mot de passe", type="password").strip()

# Variables de session pour maintenir la connexion
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None

col_auth1, col_auth2 = st.sidebar.columns(2)

# Bouton CONNEXION
if col_auth1.button("Connexion"):
    if pseudo and password:
        df_all = conn.read(worksheet="Performances").dropna(how='all')
        user_key = f"{pseudo}_{hacher_password(password)}"
        if user_key in df_all['user'].values:
            st.session_state.logged_in = True
            st.session_state.user_id = user_key
            st.session_state.display_name = pseudo
            st.sidebar.success(f"C'est parti {pseudo} !")
        else:
            st.sidebar.error("Pseudo ou code inconnu.")
    else:
        st.sidebar.warning("Remplis les champs.")

# Bouton CRÉER COMPTE
if col_auth2.button("Créer compte"):
    if pseudo and password:
        df_all = conn.read(worksheet="Performances").dropna(how='all')
        # On vérifie si le pseudo est déjà pris (même avec un autre pass)
        if any(u.startswith(f"{pseudo}_") for u in df_all['user'].unique()):
            st.sidebar.error("Ce pseudo est déjà pris.")
        else:
            # Création d'une ligne "init" pour réserver le pseudo
            user_key = f"{pseudo}_{hacher_password(password)}"
            init_row = pd.DataFrame([{'user': user_key, 'date': 'INIT', 'watts': 0, 'temp': 0, 'wind': 0, 'hum': 0}])
            df_final = pd.concat([df_all, init_row], ignore_index=True)
            conn.update(worksheet="Performances", data=df_final)
            st.sidebar.success("Compte créé ! Clique sur Connexion.")
    else:
        st.sidebar.warning("Remplis les champs.")

if st.sidebar.button("Déconnexion"):
    st.session_state.logged_in = False
    st.rerun()

# --- MÉTÉO (Toujours visible) ---
st.sidebar.divider()
nom_ville = st.sidebar.text_input("📍 Ville", "Cholet")
lat, lon, _ = obtenir_coords(nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m&forecast_days=1"
data_m = requests.get(api_url).json()

# --- PAGE PRINCIPALE ---
st.title("🚴 Coach IA & Performance")

if st.session_state.logged_in:
    st.header(f"Bienvenue {st.session_state.display_name}")
    
    # Lecture des données de l'utilisateur
    df_all = conn.read(worksheet="Performances").dropna(how='all')
    df_user = df_all[(df_all['user'] == st.session_state.user_id) & (df_all['date'] != 'INIT')]
    
    nb_sorties = len(df_user)
    
    # --- IA ET PRÉDICTION ---
    c1, c2 = st.columns([1, 2])
    if nb_sorties >= 3:
        model = RandomForestRegressor(n_estimators=100).fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
        t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t13, v13, h13]])[0]
        c1.metric("Sorties", nb_sorties)
        c2.success(f"🎯 Estimation à 13h : **{int(pred)} Watts**")
    else:
        c2.info(f"Besoin de {3-nb_sorties} sorties pour activer l'IA.")

    # --- ENREGISTREMENT ---
    with st.expander("📥 Ajouter une sortie"):
        f_csv = st.file_uploader("Fichier CSV", type=['csv'])
        if f_csv and st.button("Sauvegarder dans mon cloud"):
            df_new = pd.read_csv(f_csv)
            df_new.columns = [c.lower().strip() for c in df_new.columns]
            
            nouvelle_ligne = pd.DataFrame([{
                'user': st.session_state.user_id,
                'temp': df_new[df_new['watts']>0]['temp'].mean() if 'temp' in df_new.columns else 20,
                'wind': data_m['hourly']['windspeed_10m'][12],
                'hum': data_m['hourly']['relative_humidity_2m'][12],
                'watts': df_new[df_new['watts']>0]['watts'].mean(),
                'date': datetime.now().strftime("%Y-%m-%d")
            }])
            
            df_final = pd.concat([df_all, nouvelle_ligne], ignore_index=True)
            conn.update(worksheet="Performances", data=df_final)
            st.balloons()
            st.cache_data.clear()
            st.rerun()

else:
    st.info("👋 Connecte-toi ou crée un compte pour accéder à ton suivi de puissance.")

# Affichage des prévisions météo pour tous
st.divider()
st.subheader(f"Météo du jour à {nom_ville}")
if 'hourly' in data_m:
    m_cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t, v = data_m['hourly']['temperature_2m'][h], data_m['hourly']['windspeed_10m'][h]
        m_cols[i].write(f"**{h}h** : {t}°C | {v}km/h")
        
