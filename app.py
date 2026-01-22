import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from folium import plugins
from io import BytesIO
import json
from datetime import time, timedelta

st.set_page_config(page_title="Dynamic Map App", layout="wide")

st.title("Dynamic Map Viewer")
st.markdown("""
Upload file Excel berisi titik lokasi dengan kolom minimal: **Latitude**, **Longitude**.  
Jika ada kolom **Warna**, maka titik akan diberi warna sesuai.  
Filter otomatis akan muncul berdasarkan kolom dalam file.  
Pilih warna kustom untuk masing-masing titik jika diperlukan.
""")

uploaded_file = st.sidebar.file_uploader("Upload File Excel", type=["xlsx"])

@st.cache_data
def load_data(file):
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    return df

# ================= JSON SAFE SERIALIZER =================
def json_safe(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime("%H:%M:%S")
    if isinstance(obj, timedelta):
        return int(obj.total_seconds())
    if obj is None or (isinstance(obj, float) and np.isnan(obj)):
        return None
    return str(obj)

# ================= NORMALIZE DISPLAY =================
def normalize_display(v):
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass

    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        if np.isfinite(f):
            if f.is_integer():
                return str(int(f))
            return ('%f' % f).rstrip('0').rstrip('.')
        return str(v)

    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return s
        try:
            f = float(s)
            if f.is_integer():
                return str(int(f))
            return ('%f' % f).rstrip('0').rstrip('.')
        except Exception:
            return s

    return str(v)

def build_display_map(series: pd.Series):
    display_map = {}
    for v in pd.unique(series.dropna()):
        key = normalize_display(v)
        if key is None:
            continue
        display_map.setdefault(key, []).append(v)
    return display_map

# ================= SESSION STATE =================
def init_session_state():
    defaults = {
        "kcp_custom_colors": {},
        "enable_cluster": False
    }
    for i in range(1, 4):
        defaults.update({
            f"radius_{i}_enabled": False,
            f"radius_{i}_distance": 1.0,
            f"radius_{i}_color": "red",
            f"radius_{i}_target": "blue"
        })
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

available_folium_colors = [
    "red", "blue", "green", "purple", "orange", "darkred", "lightred",
    "beige", "darkblue", "darkgreen", "cadetblue", "darkpurple",
    "white", "pink", "lightblue", "lightgreen", "gray", "black", "lightgray"
]

# ================= LOAD JSON =================
st.sidebar.markdown("---")
st.sidebar.markdown("### Lanjutkan dari JSON")
uploaded_json = st.sidebar.file_uploader("Upload file JSON", type="json")

if uploaded_json and st.sidebar.button("Load Pengaturan JSON"):
    progress = json.load(uploaded_json)

    if "settings" in progress:
        settings = progress["settings"]
        df = pd.DataFrame(progress.get("data", []))
    else:
        settings = progress
        df = pd.DataFrame(progress.get("data", []))

    st.session_state.saved_df = df
    st.session_state.kcp_custom_colors = settings.get("kcp_custom_colors", {})
    st.session_state.enable_cluster = settings.get("enable_cluster", False)

    radius_cfg = settings.get("radius", {})
    for i in range(1, 4):
        cfg = radius_cfg.get(str(i), radius_cfg.get(i, {}))
        st.session_state[f"radius_{i}_enabled"] = cfg.get("enabled", False)
        st.session_state[f"radius_{i}_distance"] = float(cfg.get("distance", 1.0))
        st.session_state[f"radius_{i}_color"] = cfg.get("color", "red")
        st.session_state[f"radius_{i}_target"] = cfg.get("target", "blue")

    st.success("Data dan pengaturan berhasil dimuat dari JSON.")

# ================= LOAD EXCEL =================
if uploaded_file:
    df = load_data(uploaded_file)
elif "saved_df" in st.session_state:
    df = st.session_state.saved_df
else:
    st.info("Silakan upload file Excel untuk memulai.")
    st.stop()

# ================= PILIH KOLOM =================
st.subheader("Pilih Kolom Latitude, Longitude, dan Nama Titik")
col_lat = st.selectbox("Latitude", df.columns)
col_lon = st.selectbox("Longitude", df.columns)
col_name = st.selectbox("Nama Titik", df.columns)

df = df.rename(columns={col_lat: "Latitude", col_lon: "Longitude", col_name: "NamaTitik"})

# ================= SANITASI TANPA HAPUS DATA =================
df["Latitude"] = pd.to_numeric(
    df["Latitude"].astype(str).str.replace(",", ".", regex=False),
    errors="coerce"
)
df["Longitude"] = pd.to_numeric(
    df["Longitude"].astype(str).str.replace(",", ".", regex=False),
    errors="coerce"
)

# ================= DATA KHUSUS MAP (VALID SAJA) =================
df_map = df[
    pd.notna(df["Latitude"]) &
    pd.notna(df["Longitude"]) &
    df["Latitude"].between(-90, 90) &
    df["Longitude"].between(-180, 180)
].copy()

invalid_count = len(df) - len(df_map)
if invalid_count > 0:
    st.toast(f"{invalid_count} titik dilewati karena koordinat tidak valid", icon="⚠️")

# ================= SAVE JSON =================
st.sidebar.markdown("---")
st.sidebar.subheader("Simpan Progress")

safe_data = json.loads(json.dumps(df.to_dict(orient="records"), default=json_safe))

progress = {
    "version": 1,
    "data": safe_data,
    "settings": {
        "kcp_custom_colors": st.session_state.kcp_custom_colors,
        "enable_cluster": st.session_state.enable_cluster,
        "radius": {
            i: {
                "enabled": st.session_state[f"radius_{i}_enabled"],
                "distance": st.session_state[f"radius_{i}_distance"],
                "color": st.session_state[f"radius_{i}_color"],
                "target": st.session_state[f"radius_{i}_target"],
            }
            for i in range(1, 4)
        }
    }
}

json_bytes = json.dumps(progress, ensure_ascii=False, indent=2).encode("utf-8")

st.sidebar.download_button(
    "Simpan Progress (JSON)",
    data=json_bytes,
    file_name="saved_progress.json",
    mime="application/json"
)

# ================= MAP =================
if not df_map.empty:
    center_lat = df_map["Latitude"].mean()
    center_lon = df_map["Longitude"].mean()
else:
    center_lat, center_lon = -2.5489, 118.0149  # fallback Indonesia

m = folium.Map(location=[center_lat, center_lon], zoom_start=6)
plugins.MarkerCluster().add_to(m)

for _, row in df_map.iterrows():
    color = st.session_state.kcp_custom_colors.get(
        normalize_display(row.get("Warna")), "blue"
    )

    folium.Marker(
        [row["Latitude"], row["Longitude"]],
        popup=row["NamaTitik"],
        icon=folium.Icon(color=color if color in available_folium_colors else "blue")
    ).add_to(m)

st_folium(m, height=700, use_container_width=True)
