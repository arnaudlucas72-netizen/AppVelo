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

# 1. INITIALISATION DES VARIABLES (Une seule fois)
if 'nom_ville' not in st.session_state:
    st.session_state.nom_ville = "Cholet"
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Connexion Google Sheets
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

# --- BARRE LATÉRALE : ACCÈS & GPX ---
st.sidebar.header("🔐 Accès Membre")
input_pseudo = st.sidebar.text_input("Pseudo").strip()
input_password = st.sidebar.text_input("Mot de passe", type="password").strip()

col_auth1, col_auth2 = st.sidebar.columns(2)
if col_auth1.button("Connexion"):
    if input_pseudo and input_password:
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        user_key = f"{input_pseudo}_{hacher_password(input_password)}"
        if user_key in df_all['user'].astype(str).str.strip().values:
            st.session_state.logged_in = True
            st.session_state.user_id = user_key
            st.session_state.display_name = input_pseudo
            st.rerun()
        else:
            st.sidebar.error("Identifiants incorrects.")

if col_auth2.button("Créer compte"):
    if input_pseudo and input_password:
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        pseudos_pris = [u.split('_')[0] for u in df_all['user'].astype(str).unique()]
        if input_pseudo in pseudos_pris:
            st.sidebar.error("Ce pseudo est déjà utilisé.")
        else:
            user_key = f"{input_pseudo}_{hacher_password(input_password)}"
            init_row = pd.DataFrame([{'user': user_key, 'date': 'INIT', 'watts': 0, 'temp': 0, 'wind': 0, 'hum': 0}])
            df_final = pd.concat([df_all, init_row], ignore_index=True)
            conn.update(worksheet="Performances", data=df_final)
            st.sidebar.success("Compte créé !")

if st.session_state.logged_in and st.sidebar.button("Déconnexion"):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.divider()
st.sidebar.header("🌍 Localisation & GPX")

# IMPORT GPX : Il doit être placé AVANT le widget de texte pour pouvoir le modifier
f_gpx = st.sidebar.file_uploader("📂 Charger un GPX (Auto-détection)", type=['gpx'])

pts_gpx = None
if f_gpx:
    gpx = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
    if pts_gpx:
        try:
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            if g_inv and g_inv.city:
                # MISE À JOUR RADICALE : Si la ville GPX est différente, on écrase et on rerun
                if st.session_state.nom_ville != g_inv.city:
                    st.session_state.nom_ville = g_inv.city
                    st.rerun() 
        except:
            pass

# Le widget ville utilise maintenant la variable de session mise à jour par le GPX
ville_intermediaire = st.sidebar.text_input("📍 Ville", value=st.session_state.nom_ville)
if ville_intermediaire != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_intermediaire
    st.rerun()

sf = st.sidebar.slider("🌡️ Sens. Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sens. Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sens. Pluie", 0, 10, 7)

# --- RÉCUPÉRATION MÉTEO ---
lat, lon, _ = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- PAGE PRINCIPALE ---
st.title(f"🚴 Coach IA & Météo : {st.session_state.nom_ville}")

# 1. Prévisions Météo
st.header(f"🌤️ Scores pour {st.session_state.nom_ville}")
if 'hourly' in data_m:
    m_cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = data_m['hourly']['temperature_2m'][h]
        v = data_m['hourly']['windspeed_10m'][h]
        p = data_m['hourly']['precipitation_probability'][h]
        
        score = 100
        if t < 12: score -= (12 * sf / 5)
        score -= (v * 0.8 * sv / 5)
        score -= (p * 1.2 * sp / 5)
        score = max(0, min(100, int(score)))
        
        with m_cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**")
            st.markdown(f"<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h")

st.divider()

# 2. IA & Performances (Si connecté)
if st.session_state.logged_in:
    st.header(f"🤖 Analyse de {st.session_state.display_name}")
    df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
    df_user = df_all[(df_all['user'].astype(str).str.strip() == st.session_state.user_id) & (df_all['date'] != 'INIT')]
    
    nb_sorties = len(df_user)
    if nb_sorties >= 3:
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
        t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t13, v13, h13]])[0]
        st.success(f"🎯 Estimation puissance à 13h : **{int(pred)} Watts**")
    else:
        st.info(f"Ajoute encore {3-nb_sorties} sorties CSV pour activer l'IA.")

    with st.expander("📥 Enregistrer une sortie CSV"):
        f_csv = st.file_uploader("Fichier CSV", type=['csv'], key="csv_unique")
        if f_csv and st.button("Sauvegarder"):
            df_new = pd.read_csv(f_csv)
            df_new.columns = [c.lower().strip() for c in df_new.columns]
            w_moy = df_new[df_new['watts']>0]['watts'].mean()
            nouvelle_ligne = pd.DataFrame([{
                'user': st.session_state.user_id,
                'temp': data_m['hourly']['temperature_2m'][12],
                'wind': data_m['hourly']['windspeed_10m'][12],
                'hum': data_m['hourly']['relative_humidity_2m'][12],
                'watts': w_moy,
                'date': datetime.now().strftime("%Y-%m-%d")
            }])
            df_final = pd.concat([df_all, nouvelle_ligne], ignore_index=True)
            conn.update(worksheet="Performances", data=df_final)
            st.balloons()
            st.rerun()
else:
    st.info("👋 Connecte-toi pour tes prédictions IA.")

st.divider()

# 3. Carte GPX
if pts_gpx:
    st.header("🗺️ Visualisation du parcours")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
