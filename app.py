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

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach IA Cyclisme", page_icon="🚴", layout="wide")

# Connexion sécurisée au Google Sheet
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("⚠️ Erreur de connexion aux Secrets Google Sheets.")

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

# --- BARRE LATÉRALE : CONFIGURATION ---
st.sidebar.header("⚙️ Configuration")
nom_ville = st.sidebar.text_input("📍 Ville", "Cholet")
sf = st.sidebar.slider("🌡️ Sensibilité Froid", 0, 10, 5)
sv = st.sidebar.slider("💨 Sensibilité Vent", 0, 10, 5)
sp = st.sidebar.slider("🌧️ Sensibilité Pluie", 0, 10, 7)

# Récupération Météo
lat, lon, ok_coords = obtenir_coords(nom_ville)
api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,windspeed_10m,relative_humidity_2m,precipitation_probability&forecast_days=1"
try:
    data_m = requests.get(api_url).json()
except:
    data_m = {}

# --- BARRE LATÉRALE : IDENTIFICATION ---
st.sidebar.divider()
st.sidebar.header("👤 Compte")
user_pseudo = st.sidebar.text_input("Pseudo unique", help="Choisis un pseudo qui t'appartient.").strip()

# Initialisation des données
df_all = pd.DataFrame(columns=['user', 'temp', 'wind', 'hum', 'watts', 'date'])

# --- LOGIQUE PRINCIPALE ---
st.title("🚴 Assistant Cycliste Intelligent")

if user_pseudo:
    st.header(f"🤖 Espace IA de {user_pseudo}")
    
    # Chargement des données depuis Google Sheets
    try:
        df_all = conn.read(worksheet="Performances").dropna(how='all')
        df_user = df_all[df_all['user'] == user_pseudo]
    except:
        df_user = pd.DataFrame()

    col_ia1, col_ia2 = st.columns([1, 2])
    nb_sorties = len(df_user)
    
    if nb_sorties >= 3:
        # Entraînement de l'IA personnelle
        X = df_user[['temp', 'wind', 'hum']]
        y = df_user['watts']
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        
        # Prédiction pour 13h00
        t13 = data_m['hourly']['temperature_2m'][13]
        v13 = data_m['hourly']['windspeed_10m'][13]
        h13 = data_m['hourly']['relative_humidity_2m'][13]
        pred = model.predict([[t13, v13, h13]])[0]
        
        with col_ia1:
            st.metric("Sorties enregistrées", f"{nb_sorties}")
            st.info("Profil IA actif ✅")
        with col_ia2:
            st.success(f"🎯 **Estimation à 13h** : **{int(pred)} Watts**")
    else:
        with col_ia1:
            st.metric("Sorties", f"{nb_sorties}/3")
        with col_ia2:
            st.warning(f"🚀 Encore {3 - nb_sorties} sorties pour activer ton IA.")

    # Zone d'enregistrement avec vérification du pseudo
    with st.expander("📥 Enregistrer une nouvelle sortie"):
        f_csv = st.file_uploader("Fichier CSV de performance", type=['csv'], key="csv_up")
        if f_csv and st.button(f"Sauvegarder pour {user_pseudo}"):
            
            pseudos_existants = df_all['user'].unique() if not df_all.empty else []
            
            # Vérification : Si le pseudo existe déjà mais n'est pas celui de l'utilisateur actuel
            if user_pseudo in pseudos_existants and nb_sorties == 0:
                st.error(f"❌ Le pseudo '{user_pseudo}' appartient déjà à quelqu'un. Choisis-en un autre !")
            else:
                with st.spinner("Envoi au Cloud..."):
                    df_new = pd.read_csv(f_csv)
                    df_new.columns = [c.lower().strip() for c in df_new.columns]
                    
                    w_moy = df_new[df_new['watts']>0]['watts'].mean()
                    t_moy = df_new[df_new['watts']>0]['temp'].mean() if 'temp' in df_new.columns else data_m['hourly']['temperature_2m'][12]
                    
                    nouvelle_ligne = pd.DataFrame([{
                        'user': user_pseudo,
                        'temp': t_moy,
                        'wind': data_m['hourly']['windspeed_10m'][12],
                        'hum': data_m['hourly']['relative_humidity_2m'][12],
                        'watts': w_moy,
                        'date': datetime.now().strftime("%Y-%m-%d")
                    }])
                    
                    df_final = pd.concat([df_all, nouvelle_ligne], ignore_index=True)
                    conn.update(worksheet="Performances", data=df_final)
                    
                    st.balloons()
                    st.success("Données synchronisées !")
                    st.cache_data.clear()
                    st.rerun()

    if not df_user.empty:
        with st.expander("📂 Voir mon historique"):
            st.dataframe(df_user[['date', 'temp', 'watts']].sort_values(by='date', ascending=False))

else:
    st.info("👈 Indique un pseudo dans la barre latérale pour accéder à tes fonctions IA.")

st.divider()

# --- SECTION MÉTÉO ---
st.header(f"🌤️ Score de sortie : {nom_ville}")
if data_m and 'hourly' in data_m:
    cols = st.columns(4)
    for i, h in enumerate([10, 13, 16, 19]):
        t = data_m['hourly']['temperature_2m'][h]
        v = data_m['hourly']['windspeed_10m'][h]
        p = data_m['hourly']['precipitation_probability'][h]
        score = calculer_score_meteo(t, v, p, sf, sv, sp)
        with cols[i]:
            color = "green" if score > 75 else "orange" if score > 45 else "red"
            st.markdown(f"**{h}h00**")
            st.markdown(f"<h2 style='color:{color};'>{score}/100</h2>", unsafe_allow_html=True)
            st.caption(f"{t}°C | {v}km/h")

st.divider()

# --- SECTION PARCOURS ---
st.header("🗺️ Visualisation GPX")
f_gpx = st.file_uploader("Charger un parcours", type=['gpx'])
if f_gpx:
    gpx = gpxpy.parse(f_gpx)
    pts = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
    m = folium.Map(location=pts[0], zoom_start=12)
    folium.PolyLine(pts, color="blue", weight=4).add_to(m)
    st_folium(m, width=1000, height=400)
    
