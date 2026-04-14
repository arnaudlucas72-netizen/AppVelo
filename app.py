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

# 1. INITIALISATION DES VARIABLES
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

# --- LOGIQUE GPX : PLACÉE AU DESSUS DE TOUT ---
# On crée le widget de chargement tout en haut de la sidebar
st.sidebar.header("🌍 Localisation & Parcours")
f_gpx = st.sidebar.file_uploader("📂 Importer un GPX (Détection auto)", type=['gpx'], key="main_gpx")

pts_gpx = None
if f_gpx:
    # On parse le fichier immédiatement
    gpx_parsed = gpxpy.parse(f_gpx)
    pts_gpx = [[p.latitude, p.longitude] for t in gpx_parsed.tracks for s in t.segments for p in s.points]
    
    if pts_gpx:
        try:
            # On détecte la ville du point de départ (ex: Soullans)
            g_inv = geocoder.osm([pts_gpx[0][0], pts_gpx[0][1]], method='reverse')
            ville_trouvee = g_inv.city if g_inv.city else g_inv.town
            
            # FORCE : Si la ville GPX est différente, on met à jour et on stoppe tout pour relancer proprement
            if ville_trouvee and ville_trouvee != st.session_state.nom_ville:
                st.session_state.nom_ville = ville_trouvee
                st.rerun() 
        except:
            pass

# Le widget de texte suit la session_state (qui peut être modifiée par le GPX au dessus)
ville_a_afficher = st.sidebar.text_input("📍 Ville active", value=st.session_state.nom_ville, key="ville_widget")

# Si l'utilisateur change manuellement la ville dans le champ texte
if ville_a_afficher != st.session_state.nom_ville:
    st.session_state.nom_ville = ville_a_afficher
    st.rerun()

# --- PARAMÈTRES ET AUTHENTIFICATION ---
st.sidebar.divider()
sf = st.sidebar.slider("🌡️ Sens. Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sens. Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sens. Pluie", 0, 10, 7)

st.sidebar.divider()
st.sidebar.header("🔐 Accès Membre")
if not st.session_state.logged_in:
    input_pseudo = st.sidebar.text_input("Pseudo").strip()
    input_password = st.sidebar.text_input("Mot de passe", type="password").strip()
    if st.sidebar.button("Connexion"):
        df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
        user_key = f"{input_pseudo}_{hacher_password(input_password)}"
        if user_key in df_all['user'].astype(str).values:
            st.session_state.logged_in = True
            st.session_state.user_id = user_key
            st.session_state.display_name = input_pseudo
            st.rerun()
else:
    st.sidebar.success(f"Connecté : {st.session_state.display_name}")
    if st.sidebar.button("Déconnexion"):
        st.session_state.logged_in = False
        st.rerun()

# --- RÉCUPÉRATION MÉTEO ---
lat, lon, _ = obtenir_coords(st.session_state.nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
data_m = requests.get(api_url).json()

# --- PAGE PRINCIPALE ---
st.title(f"🚴 Coach IA : {st.session_state.nom_ville}")

# 1. MÉTÉO (Source de vérité : st.session_state.nom_ville)
st.header(f"🌤️ Conditions pour {st.session_state.nom_ville}")
if 'hourly' in data_m:
    m_cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = data_m['hourly']['temperature_2m'][h]
        v = data_m['hourly']['windspeed_10m'][h]
        p = data_m['hourly']['precipitation_probability'][h]
        score = max(0, min(100, int(100 - (12-t if t<12 else 0)*sf/5 - v*0.8*sv/5 - p*1.2*sp/5)))
        with m_cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**\n<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h")

st.divider()

# 2. IA
if st.session_state.logged_in:
    st.header(f"🤖 Analyse de {st.session_state.display_name}")
    df_all = conn.read(worksheet="Performances", ttl=0).dropna(how='all')
    df_user = df_all[(df_all['user'].astype(str) == st.session_state.user_id) & (df_all['date'] != 'INIT')]
    
    if len(df_user) >= 3:
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(df_user[['temp', 'wind', 'hum']], df_user['watts'])
        t13, v13, h13 = data_m['hourly']['temperature_2m'][13], data_m['hourly']['windspeed_10m'][13], data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t13, v13, h13]])[0]
        st.success(f"🎯 Puissance estimée à 13h : **{int(pred)} Watts**")
    else:
        st.info("Ajoutez 3 sorties CSV pour activer l'IA.")
    
    with st.expander("📥 Ajouter une sortie CSV"):
        f_csv = st.file_uploader("Fichier CSV", type=['csv'], key="csv_up")
        if f_csv and st.button("Enregistrer"):
            df_new = pd.read_csv(f_csv)
            df_new.columns = [c.lower().strip() for c in df_new.columns]
            w_moy = df_new[df_new['watts']>0]['watts'].mean()
            nouvelle_ligne = pd.DataFrame([{'user': st.session_state.user_id, 'temp': data_m['hourly']['temperature_2m'][12], 'wind': data_m['hourly']['windspeed_10m'][12], 'hum': data_m['hourly']['relative_humidity_2m'][12], 'watts': w_moy, 'date': datetime.now().strftime("%Y-%m-%d")}])
            conn.update(worksheet="Performances", data=pd.concat([df_all, nouvelle_ligne], ignore_index=True))
            st.rerun()
else:
    st.info("👋 Connectez-vous pour vos prédictions de puissance.")

st.divider()

# 3. CARTE
if pts_gpx:
    st.header(f"🗺️ Parcours : {st.session_state.nom_ville}")
    m = folium.Map(location=pts_gpx[0], zoom_start=12)
    folium.PolyLine(pts_gpx, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
    
