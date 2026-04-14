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

# --- INITIALISATION SESSION ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = None

# --- BARRE LATÉRALE : ACCÈS ---
st.sidebar.header("🔐 Accès Membre")
input_pseudo = st.sidebar.text_input("Pseudo").strip()
input_password = st.sidebar.text_input("Mot de passe", type="password").strip()

col_auth1, col_auth2 = st.sidebar.columns(2)

# Bouton CONNEXION
if col_auth1.button("Connexion"):
    if input_pseudo and input_password:
        # Forcer la relecture pour avoir les derniers comptes créés
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        user_key = f"{input_pseudo}_{hacher_password(input_password)}"
        
        # Comparaison sécurisée (on force tout en texte et on enlève les espaces invisibles)
        if user_key in df_all['user'].astype(str).str.strip().values:
            st.session_state.logged_in = True
            st.session_state.user_id = user_key
            st.session_state.display_name = input_pseudo
            st.sidebar.success(f"Bonjour {input_pseudo} !")
            st.rerun()
        else:
            st.sidebar.error("Identifiants incorrects.")
    else:
        st.sidebar.warning("Remplis les deux champs.")

# Bouton CRÉER COMPTE
if col_auth2.button("Créer compte"):
    if input_pseudo and input_password:
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        
        # Vérification si le pseudo existe déjà (indépendamment du mot de passe)
        pseudos_pris = [u.split('_')[0] for u in df_all['user'].astype(str).unique()]
        
        if input_pseudo in pseudos_pris:
            st.sidebar.error("Ce pseudo est déjà utilisé.")
        else:
            with st.spinner("Création..."):
                user_key = f"{input_pseudo}_{hacher_password(input_password)}"
                init_row = pd.DataFrame([{
                    'user': user_key, 
                    'date': 'INIT', 
                    'watts': 0, 'temp': 0, 'wind': 0, 'hum': 0
                }])
                df_final = pd.concat([df_all, init_row], ignore_index=True)
                conn.update(worksheet="Performances", data=df_final)
                st.sidebar.success("Compte créé ! Connecte-toi.")
    else:
        st.sidebar.warning("Champs vides.")

if st.session_state.logged_in:
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.rerun()

# --- MÉTÉO ---
st.sidebar.divider()
nom_ville = st.sidebar.text_input("📍 Ville", "Cholet")
lat, lon, _ = obtenir_coords(nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m&forecast_days=1"
data_m = requests.get(api_url).json()

# --- PAGE PRINCIPALE ---
st.title("🚴 Coach IA & Performance")

if st.session_state.logged_in:
    st.header(f"Tableau de bord de {st.session_state.display_name}")
    
    # Lecture des données (ttl=0 pour éviter le cache et voir sa sortie direct)
    df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
    # Filtrage précis sur l'ID de session
    df_user = df_all[(df_all['user'].astype(str).str.strip() == st.session_state.user_id) & (df_all['date'] != 'INIT')]
    
    nb_sorties = len(df_user)
    
    c1, c2 = st.columns([1, 2])
    if nb_sorties >= 3:
        # IA
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
        
        t13 = data_m['hourly']['temperature_2m'][13]
        v13 = data_m['hourly']['windspeed_10m'][13]
        h13 = data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t13, v13, h13]])[0]
        
        c1.metric("Sorties", nb_sorties)
        c2.success(f"🎯 Estimation à 13h : **{int(pred)} Watts**")
    else:
        c1.metric("Sorties", f"{nb_sorties}/3")
        c2.info(f"Ajoute encore {3-nb_sorties} sorties pour activer l'IA.")

    # Enregistrement
    with st.expander("📥 Ajouter une sortie CSV"):
        f_csv = st.file_uploader("Fichier CSV", type=['csv'])
        if f_csv and st.button("Sauvegarder la sortie"):
            df_new = pd.read_csv(f_csv)
            df_new.columns = [c.lower().strip() for c in df_new.columns]
            
            w_moy = df_new[df_new['watts']>0]['watts'].mean()
            # On prend la température du CSV si elle existe, sinon celle de la météo à 12h
            t_moy = df_new[df_new['watts']>0]['temp'].mean() if 'temp' in df_new.columns else data_m['hourly']['temperature_2m'][12]
            
            nouvelle_ligne = pd.DataFrame([{
                'user': st.session_state.user_id,
                'temp': t_moy,
                'wind': data_m['hourly']['windspeed_10m'][12],
                'hum': data_m['hourly']['relative_humidity_2m'][12],
                'watts': w_moy,
                'date': datetime.now().strftime("%Y-%m-%d")
            }])
            
            df_final = pd.concat([df_all, nouvelle_ligne], ignore_index=True)
            conn.update(worksheet="Performances", data=df_final)
            st.balloons()
            st.rerun()

    if not df_user.empty:
        st.write("### Historique")
        st.dataframe(df_user[['date', 'temp', 'watts']].sort_values(by='date', ascending=False))
else:
    st.info("👋 Connecte-toi ou crée un compte pour voir tes données.")

# Météo publique
st.divider()
st.subheader(f"Météo à {nom_ville}")
if 'hourly' in data_m:
    m_cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t, v = data_m['hourly']['temperature_2m'][h], data_m['hourly']['windspeed_10m'][h]
        m_cols[i].write(f"**{h}h** : {t}°C | {v}km/h")
