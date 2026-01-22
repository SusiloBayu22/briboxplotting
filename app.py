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

# ================= JSON SAFE SERIALIZER (FIX JSON dumps) =================
def json_safe(obj):
    """Make objects JSON-serializable (handles numpy/pandas/time/timedelta)."""
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
    if obj is None:
        return None
    try:
        # NaN / NaT
        if isinstance(obj, float) and np.isnan(obj):
            return None
    except Exception:
        pass
    return str(obj)

# === Helpers untuk normalisasi tampilan nilai (angka & campur tipe) ===
def normalize_display(v):
    """Kembalikan string display yang stabil untuk angka & non-angka.
       - 1 dan 1.0 -> '1'
       - 1.50 -> '1.5'
       - selain angka -> str(v)
    """
    # Tangani NaN awal
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
            else:
                s = ('%f' % f).rstrip('0').rstrip('.')
                return s
        else:
            return str(v)

    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return s
        try:
            f = float(s)
            if np.isfinite(f):
                if f.is_integer():
                    return str(int(f))
                else:
                    return ('%f' % f).rstrip('0').rstrip('.')
        except Exception:
            pass
        return s
    return str(v)

def build_display_map(series: pd.Series):
    """Buat peta: display_string -> list[nilai_asli], untuk handle 1 vs 1.0."""
    display_map = {}
    for v in pd.unique(series.dropna()):
        key = normalize_display(v)
        if key is None:
            continue
        display_map.setdefault(key, []).append(v)
    return display_map

# === Initialize Session States ===
def init_session_state():
    defaults = {
        "kcp_custom_colors": {},
        "enable_cluster": False,
        "legend_column": "(Tidak ada)",

        # --- Resume helpers (auto-restore last session) ---
        "col_lat_saved": None,
        "col_lon_saved": None,
        "name_column_saved": None,
        "warna_column_saved": None,

        # filter state
        "filter_selections": {},               # {"Propinsi": [...], "Kota": [...], ...}
        "additional_filter_cols_saved": [],    # [colA, colB, ...]
        "additional_filter_values": {}         # {"colA": [...], ...}
    }
    for i in range(1, 4):
        defaults.update({
            f"radius_{i}_enabled": False,
            f"radius_{i}_distance": 1.0,
            f"radius_{i}_color": "red",
            f"radius_{i}_target": "blue"
        })
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()

# === Available Colors ===
available_folium_colors = [
    "red", "blue", "green", "purple", "orange", "darkred", "lightred",
    "beige", "darkblue", "darkgreen", "cadetblue", "darkpurple",
    "white", "pink", "lightblue", "lightgreen", "gray", "black", "lightgray"
]


# === Normalisasi warna folium (handle typo / case) ===
COLOR_ALIASES = {
    "darkklue": "darkblue",
    "darkblu": "darkblue",
    "darkbue": "darkblue",
    "lightgren": "lightgreen",
    "ligtgreen": "lightgreen",
    "purpel": "purple",
}

def normalize_folium_color(c):
    if c is None:
        return None
    s = str(c).strip().lower()
    if s in COLOR_ALIASES:
        s = COLOR_ALIASES[s]
    return s

# ================= LOAD from JSON (backward compatible) =================
st.sidebar.markdown("---")
st.sidebar.markdown("### Lanjutkan dari JSON")
uploaded_json = st.sidebar.file_uploader("Upload file JSON", type="json")
if uploaded_json is not None:
    if st.sidebar.button("Load Pengaturan JSON"):
        progress = json.load(uploaded_json)

        # Backward compatible: old format had settings at root
        if isinstance(progress, dict) and "settings" in progress:
            settings = progress.get("settings", {})
            df = pd.DataFrame(progress.get("data", []))
        else:
            settings = progress
            df = pd.DataFrame(progress.get("data", [])) if isinstance(progress, dict) else pd.DataFrame()

        st.session_state.kcp_custom_colors = {
            str(k): v for k, v in settings.get("kcp_custom_colors", {}).items()
        }
        st.session_state.enable_cluster = settings.get("enable_cluster", False)
        st.session_state.legend_column = settings.get("legend_column", "(Tidak ada)")
        # restore last UI selections (optional)
        st.session_state.col_lat_saved = settings.get("col_lat_saved")
        st.session_state.col_lon_saved = settings.get("col_lon_saved")
        st.session_state.name_column_saved = settings.get("name_column_saved")
        st.session_state.warna_column_saved = settings.get("warna_column_saved")

        st.session_state.filter_selections = settings.get("filter_selections", {})
        st.session_state.additional_filter_cols_saved = settings.get("additional_filter_cols_saved", [])
        st.session_state.additional_filter_values = settings.get("additional_filter_values", {})

        radius_cfg = settings.get("radius", {})
        for i in range(1, 4):
            cfg = radius_cfg.get(str(i), radius_cfg.get(i, {}))
            st.session_state[f"radius_{i}_enabled"] = cfg.get("enabled", False)
            st.session_state[f"radius_{i}_distance"] = float(cfg.get("distance", 1.0))
            st.session_state[f"radius_{i}_color"] = cfg.get("color", "red")
            st.session_state[f"radius_{i}_target"] = cfg.get("target", "blue")

        st.session_state.saved_df = df
        st.success("Data dan pengaturan berhasil dimuat dari JSON.")

# ================= MAIN: Load Excel OR from saved_df =================
if uploaded_file is not None:
    df = load_data(uploaded_file)
elif "saved_df" in st.session_state:
    df = st.session_state.saved_df
    st.success("Menampilkan data yang dimuat dari JSON sebelumnya.")
else:
    st.info("Silakan upload file Excel untuk memulai.")
    st.stop()

# ================= Pilih Kolom Latitude/Longitude/Nama =================
st.subheader("Pilih Kolom Latitude, Longitude, dan Nama Titik")
# auto-select jika pernah disimpan dari JSON / session sebelumnya
def _idx_or_none(cols, value):
    try:
        return list(cols).index(value) if value in list(cols) else None
    except Exception:
        return None

col_lat_default = _idx_or_none(df.columns, st.session_state.get("col_lat_saved"))
col_lon_default = _idx_or_none(df.columns, st.session_state.get("col_lon_saved"))
name_col_default = _idx_or_none(df.columns, st.session_state.get("name_column_saved"))

col_lat = st.selectbox("Pilih Kolom Latitude", df.columns, index=col_lat_default)
col_lon = st.selectbox("Pilih Kolom Longitude", df.columns, index=col_lon_default)
name_column = st.selectbox("Pilih Kolom Nama Titik", df.columns, index=name_col_default)

# simpan pilihan
st.session_state.col_lat_saved = col_lat
st.session_state.col_lon_saved = col_lon
st.session_state.name_column_saved = name_column

if not col_lat or not col_lon or not name_column:
    st.warning("Silakan pilih ketiga kolom terlebih dahulu.")
    st.stop()

# --- Rename kolom utama ---
df = df.rename(columns={col_lat: "Latitude", col_lon: "Longitude", name_column: "NamaTitik"})

# --- SANITASI & VALIDASI LAT/LON (tetap simpan baris rusak) ---
# 1) Ganti koma menjadi titik untuk angka desimal yang ditulis dengan koma
df["Latitude"]  = df["Latitude"].astype(str).str.replace(",", ".", regex=False)
df["Longitude"] = df["Longitude"].astype(str).str.replace(",", ".", regex=False)

# 2) Konversi ke numerik (yang gagal -> NaN) -> baris tetap ada
df["Latitude"]  = pd.to_numeric(df["Latitude"], errors="coerce")
df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

# 3) Mask valid untuk kebutuhan MAP saja (df tidak dipangkas)
mask_valid = (
    pd.notna(df["Latitude"]) & pd.notna(df["Longitude"]) &
    np.isfinite(df["Latitude"]) & np.isfinite(df["Longitude"]) &
    df["Latitude"].between(-90, 90, inclusive="both") &
    df["Longitude"].between(-180, 180, inclusive="both")
)

invalid_count = int((~mask_valid).sum())
if invalid_count > 0:
    st.toast(f"{invalid_count} titik tidak bisa ditampilkan karena koordinat tidak valid", icon="⚠️")

# ================= Sidebar Filters - Cascading (robust untuk angka) =================
st.sidebar.title("Filter Lokasi")
filtered_df = df.copy()
filter_hierarchy = ["Propinsi", "Kota", "Kanwil"]

for col in filter_hierarchy:
    if col in filtered_df.columns:
        disp_map = build_display_map(filtered_df[col])
        options = ["Pilih Semua"] + sorted(disp_map.keys(), key=str.lower)
        # restore default selection jika ada
        _saved = st.session_state.get("filter_selections", {}).get(col, ["Pilih Semua"])
        # pastikan hanya option yang valid
        _saved = [v for v in _saved if v in options]
        if not _saved:
            _saved = ["Pilih Semua"]

        selected_displays = st.sidebar.multiselect(
            f"Pilih {col}",
            options,
            default=_saved,
            key=f"filter_{col}"
        )
        # simpan pilihan untuk resume
        st.session_state.filter_selections[col] = selected_displays

        if "Pilih Semua" not in selected_displays:
            selected_originals = []
            for disp in selected_displays:
                selected_originals.extend(disp_map.get(disp, []))
            filtered_df = filtered_df[filtered_df[col].isin(selected_originals)]

if filtered_df.empty:
    st.warning("Tidak ada data setelah filter diterapkan.")
    st.stop()

# === Filter Tambahan Dinamis (robust untuk angka & campur tipe) ===
st.sidebar.markdown("### Filter Tambahan (Opsional)")
additional_filter_columns = [
    col for col in filtered_df.columns
    if col not in filter_hierarchy + ["Latitude", "Longitude", "NamaTitik"]
]
# restore kolom tambahan terakhir (jika ada)
_saved_cols = st.session_state.get("additional_filter_cols_saved", [])
_saved_cols = [c for c in _saved_cols if c in additional_filter_columns]

selected_additional_filters = st.sidebar.multiselect(
    "Pilih Kolom Untuk Ditambahkan sebagai Filter",
    additional_filter_columns,
    default=_saved_cols,
    key="additional_filter_cols"
)
st.session_state.additional_filter_cols_saved = selected_additional_filters

for col in selected_additional_filters:
    disp_map = build_display_map(filtered_df[col])
    options = ["Pilih Semua"] + sorted(disp_map.keys(), key=str.lower)
    # restore default selection untuk filter tambahan
    _saved_vals = st.session_state.get("additional_filter_values", {}).get(col, ["Pilih Semua"])
    _saved_vals = [v for v in _saved_vals if v in options]
    if not _saved_vals:
        _saved_vals = ["Pilih Semua"]

    selected_displays = st.sidebar.multiselect(
        f"Filter Nilai untuk {col}",
        options,
        default=_saved_vals,
        key=f"additional_filter_{col}"
    )
    # simpan untuk resume
    st.session_state.additional_filter_values[col] = selected_displays

    if "Pilih Semua" not in selected_displays:
        selected_originals = []
        for disp in selected_displays:
            selected_originals.extend(disp_map.get(disp, []))
        filtered_df = filtered_df[filtered_df[col].isin(selected_originals)]
        if filtered_df.empty:
            st.warning(f"Tidak ada data setelah filter '{col}' diterapkan.")
            st.stop()

# === Sidebar Warna ===
st.sidebar.markdown("---")
st.sidebar.subheader("Pilih Warna Untuk Titik Tertentu")
warna_default = _idx_or_none(df.columns, st.session_state.get("warna_column_saved"))
warna_column = st.sidebar.selectbox("Pilih Kolom Referensi Warna", df.columns, index=warna_default)
st.session_state.warna_column_saved = warna_column

if warna_column:
    name_list = sorted(
        pd.Series(df[warna_column].dropna().map(normalize_display)).dropna().unique(),
        key=lambda s: s.lower()
    )
    selected_names = st.sidebar.multiselect("Pilih Nilai dari Kolom Warna", name_list)
    color_choice = st.sidebar.selectbox("Pilih Warna", available_folium_colors)
    if selected_names:
        if st.sidebar.button("Tandai Nilai dengan Warna Ini"):
            for disp in selected_names:
                st.session_state.kcp_custom_colors[str(disp)] = color_choice

if st.sidebar.button("Reset Semua Warna"):
    st.session_state.kcp_custom_colors = {}

# === Legenda Dinamis ===
st.sidebar.markdown("---")
st.sidebar.subheader("Legenda Peta (Dinamis)")
legend_options = ["(Tidak ada)"] + [c for c in df.columns if c not in ["Latitude", "Longitude"]]
default_legend = st.session_state.get("legend_column", "(Tidak ada)")
if default_legend not in legend_options:
    default_legend = "(Tidak ada)"
legend_column = st.sidebar.selectbox(
    "Pilih Kolom untuk Legenda",
    legend_options,
    index=legend_options.index(default_legend)
)
st.session_state.legend_column = legend_column


# === Radius Bertingkat (3 Tingkat) ===
st.sidebar.markdown("---")
st.sidebar.subheader("Radius Bertingkat (Maks. 3 Lingkaran)")
for i in range(1, 4):
    with st.sidebar.expander(f"Radius #{i}", expanded=(i == 1)):
        enabled = st.checkbox(f"Aktifkan Radius #{i}", key=f"radius_{i}_enabled")
        if enabled:
            st.number_input(f"Jarak Radius #{i} (km)", min_value=0.0, step=0.5, key=f"radius_{i}_distance")
            st.selectbox(f"Warna Lingkaran #{i}", available_folium_colors, key=f"radius_{i}_color")
            st.selectbox(f"Warna Target Titik #{i}", available_folium_colors, key=f"radius_{i}_target")

st.sidebar.markdown("---")
st.session_state.enable_cluster = st.sidebar.checkbox(
    "Aktifkan Cluster Marker",
    value=st.session_state.enable_cluster
)

# === Save Progress (JSON) ===
st.sidebar.markdown("---")
progress = {
    "version": 1,
    "data": df.to_dict(orient="records"),
    "settings": {
        "kcp_custom_colors": st.session_state.kcp_custom_colors,
        "enable_cluster": st.session_state.enable_cluster,
        "legend_column": st.session_state.get("legend_column", "(Tidak ada)"),
        # resume state
        "col_lat_saved": st.session_state.get("col_lat_saved"),
        "col_lon_saved": st.session_state.get("col_lon_saved"),
        "name_column_saved": st.session_state.get("name_column_saved"),
        "warna_column_saved": st.session_state.get("warna_column_saved"),
        "filter_selections": st.session_state.get("filter_selections", {}),
        "additional_filter_cols_saved": st.session_state.get("additional_filter_cols_saved", []),
        "additional_filter_values": st.session_state.get("additional_filter_values", {}),

        "radius": {
            i: {
                "enabled": st.session_state.get(f"radius_{i}_enabled", False),
                "distance": st.session_state.get(f"radius_{i}_distance", 1.0),
                "color": st.session_state.get(f"radius_{i}_color", "red"),
                "target": st.session_state.get(f"radius_{i}_target", "blue"),
            }
            for i in range(1, 4)
        }
    }
}

json_bytes = json.dumps(progress, default=json_safe, ensure_ascii=False, indent=2).encode("utf-8")
st.sidebar.download_button(
    "Simpan Progress (JSON)",
    data=json_bytes,
    file_name="saved_progress.json",
    mime="application/json"
)

# ================= MAIN MAP (gunakan df_map agar NaN tidak bikin crash) =================
df_map = filtered_df[mask_valid.reindex(filtered_df.index, fill_value=False)].copy()

# Center map: kalau tidak ada titik valid, fallback Indonesia
if not df_map.empty:
    lat_center = float(df_map["Latitude"].mean())
    lon_center = float(df_map["Longitude"].mean())
else:
    lat_center, lon_center = -2.5489, 118.0149

m = folium.Map(location=[lat_center, lon_center], zoom_start=6)
plugins.Draw(export=True).add_to(m)

marker_group = folium.FeatureGroup(name="Markers")
marker_cluster = plugins.MarkerCluster() if st.session_state.enable_cluster else None

# Helper: resolve warna marker sesuai aturan asli (custom -> kolom "Warna" -> default blue)
def resolve_marker_color(row):
    """Tentukan warna marker secara konsisten.
    Prioritas:
    1) Custom mapping (berdasarkan warna_column yang dipilih)
    2) Kolom Warna_Akhir (jika ada & tidak kosong)
    3) Kolom Warna (jika ada & tidak kosong)
    4) Default 'blue'
    """
    # default
    warna = "blue"

    # 1) custom mapping (opsional, hanya jika warna_column dipilih)
    try:
        ref_value = row.get(warna_column) if warna_column else None
    except Exception:
        ref_value = None

    disp_key = None
    if ref_value is not None and not pd.isna(ref_value):
        disp_key = normalize_display(ref_value)

    if disp_key and disp_key in st.session_state.kcp_custom_colors:
        return normalize_folium_color(st.session_state.kcp_custom_colors[disp_key])

    # 2) prefer Warna_Akhir jika tersedia (mis. hasil export sebelumnya)
    if "Warna_Akhir" in row.index and pd.notna(row.get("Warna_Akhir")):
        warna_akhir = str(row.get("Warna_Akhir")).strip()
        if warna_akhir:
            return normalize_folium_color(warna_akhir)

    # 3) fallback Warna
    if "Warna" in row.index and pd.notna(row.get("Warna")):
        warna_col = str(row.get("Warna")).strip()
        if warna_col:
            return normalize_folium_color(warna_col)

    return normalize_folium_color(warna)

for _, row in df_map.iterrows():
    lat, lon = row["Latitude"], row["Longitude"]
    warna = resolve_marker_color(row)

    marker = folium.Marker(
        location=[lat, lon],
        popup=row.get("NamaTitik", ""),
        icon=folium.Icon(color=normalize_folium_color(warna) if normalize_folium_color(warna) in available_folium_colors else "blue", icon="info-sign")
    )

    if st.session_state.enable_cluster:
        marker_cluster.add_child(marker)
    else:
        marker.add_to(marker_group)

    # Tambahkan Lingkaran Bertingkat
    for i in range(1, 4):
        if st.session_state.get(f"radius_{i}_enabled"):
            target = st.session_state.get(f"radius_{i}_target")
            if warna == target:
                radius_km = st.session_state.get(f"radius_{i}_distance", 1.0)
                circle_color = st.session_state.get(f"radius_{i}_color", "red")
                folium.Circle(
                    radius=radius_km * 1000,
                    location=[lat, lon],
                    color=circle_color,
                    fill=True,
                    fill_opacity=0.2
                ).add_to(m)

if st.session_state.enable_cluster and marker_cluster is not None:
    marker_cluster.add_to(m)
else:
    marker_group.add_to(m)

# === Legenda Peta (Dinamis) ===
if st.session_state.get("legend_column", "(Tidak ada)") != "(Tidak ada)":
    legend_col = st.session_state.get("legend_column")
    if legend_col in df_map.columns:
        from collections import defaultdict, Counter

        # hitung warna paling sering untuk setiap label legenda
        color_counter = defaultdict(Counter)
        for _, r in df_map.iterrows():
            v = r.get(legend_col)
            if v is None or pd.isna(v):
                continue
            label = normalize_display(v)
            if label is None or label == "":
                continue
            c = resolve_marker_color(r)
            color_counter[label][c] += 1

        legend_colors = {
            label: cnt.most_common(1)[0][0]
            for label, cnt in color_counter.items()
        }

        # batasi agar legend tidak terlalu panjang
        legend_labels_sorted = sorted(legend_colors.keys(), key=lambda s: str(s).lower())
        max_items = 25
        if len(legend_labels_sorted) > max_items:
            legend_labels_sorted = legend_labels_sorted[:max_items] + ["..."]

        legend_items = ""
        for l in legend_labels_sorted:
            if l == "...":
                legend_items += "<div style='margin-top:6px; color:#666;'>...</div>"
                continue
            c = legend_colors.get(l, "blue")
            legend_items += (
                "<div style='display:flex;align-items:center;margin-bottom:4px;'>"
                f"<div style='width:12px;height:12px;border-radius:50%;background:{c};"
                f"{'border:1px solid #ccc;' if c == 'white' else ''}"
                "margin-right:6px;'></div>"
                f"{l}</div>"
            )

        legend_html = f"""
        <div style="position:absolute; bottom:10px; right:10px; z-index:9999; background-color:white;
            padding:10px; border:2px solid #ccc; border-radius:8px; box-shadow:2px 2px 5px rgba(0,0,0,0.3);
            font-size:14px; max-width:220px; max-height:240px; overflow:auto;">
            <b>Legenda ({legend_col}):</b><br>
            <div style="margin-top:5px;">{legend_items}</div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

st_folium(m, use_container_width=True, height=700)

# === Export Data (tetap pakai filtered_df agar baris rusak tetap ikut export) ===
df_export = filtered_df.copy()

def get_final_color(row):
    # konsisten dengan warna di peta
    return resolve_marker_color(row)

df_export["Warna_Akhir"] = df_export.apply(get_final_color, axis=1)

buffer = BytesIO()
df_export.to_excel(buffer, index=False, engine="openpyxl")
buffer.seek(0)
st.download_button(
    "Download Seluruh Data (Excel)",
    data=buffer,
    file_name="seluruh_data_dengan_warna.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
