import streamlit as st
import pandas as pd
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

# === Initialize Session States ===
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

# === Serialize Time and Timedelta ===
def serialize_time(obj):
    if isinstance(obj, time):
        return obj.strftime('%H:%M:%S')
    elif isinstance(obj, timedelta):
        total_seconds = int(obj.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    raise TypeError(f"Type {type(obj)} not serializable")

# === Load from JSON ===
st.sidebar.markdown("---")
st.sidebar.markdown("### Lanjutkan dari JSON")
uploaded_json = st.sidebar.file_uploader("Upload file JSON", type="json")
if uploaded_json is not None:
    if st.sidebar.button("Load Pengaturan JSON"):
        progress = json.load(uploaded_json)
        df = pd.DataFrame(progress["data"])
        st.session_state.kcp_custom_colors = progress.get("kcp_custom_colors", {})
        st.session_state.enable_cluster = progress.get("enable_cluster", False)
        for i in range(1, 4):
            st.session_state[f"radius_{i}_enabled"] = progress.get(f"radius_{i}_enabled", False)
            st.session_state[f"radius_{i}_distance"] = progress.get(f"radius_{i}_distance", 1.0)
            st.session_state[f"radius_{i}_color"] = progress.get(f"radius_{i}_color", "red")
            st.session_state[f"radius_{i}_target"] = progress.get(f"radius_{i}_target", "blue")
        st.session_state.saved_df = df
        st.success("Data dan pengaturan berhasil dimuat dari JSON.")

if uploaded_file is not None:
    df = load_data(uploaded_file)

    st.subheader("Pilih Kolom Latitude, Longitude, dan Nama Titik")
    col_lat = st.selectbox("Pilih Kolom Latitude", df.columns, index=None)
    col_lon = st.selectbox("Pilih Kolom Longitude", df.columns, index=None)
    name_column = st.selectbox("Pilih Kolom Nama Titik", df.columns, index=None)

    if not col_lat or not col_lon or not name_column:
        st.warning("Silakan pilih ketiga kolom terlebih dahulu.")
        st.stop()

    df = df.rename(columns={col_lat: "Latitude", col_lon: "Longitude", name_column: "NamaTitik"})
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df.dropna(subset=["Latitude", "Longitude"], inplace=True)

    # === Sidebar Filters - Cascading ===
    st.sidebar.title("Filter Lokasi")
    filtered_df = df.copy()
    filter_hierarchy = ["Wilayah", "Region", "Lokasi pengiriman"]

    for col in filter_hierarchy:
        if col in filtered_df.columns:
            unique_vals = sorted(filtered_df[col].dropna().unique())
            multiselect_vals = st.sidebar.multiselect(f"Pilih {col}", ["Pilih Semua"] + unique_vals, default=["Pilih Semua"])
            if "Pilih Semua" not in multiselect_vals:
                filtered_df = filtered_df[filtered_df[col].isin(multiselect_vals)]

    if filtered_df.empty:
        st.warning("Tidak ada data setelah filter diterapkan.")
        st.stop()

    # === Sidebar Warna ===
    st.sidebar.markdown("---")
    st.sidebar.subheader("Pilih Warna Untuk Titik Tertentu")
    warna_column = st.sidebar.selectbox("Pilih Kolom Referensi Warna", df.columns, index=None)
    if warna_column:
        name_list = sorted(df[warna_column].dropna().unique())
        selected_names = st.sidebar.multiselect("Pilih Nilai dari Kolom Warna", name_list)
        color_choice = st.sidebar.selectbox("Pilih Warna", available_folium_colors)
        if selected_names:
            if st.sidebar.button("Tandai Nilai dengan Warna Ini"):
                for val in selected_names:
                    st.session_state.kcp_custom_colors[val] = color_choice

    if st.sidebar.button("Reset Semua Warna"):
        st.session_state.kcp_custom_colors = {}

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
    st.session_state.enable_cluster = st.sidebar.checkbox("Aktifkan Cluster Marker", value=st.session_state.enable_cluster)

    # === Save Progress ===
    st.sidebar.markdown("---")
    progress = {
        "data": df.to_dict(orient="records"),
        "kcp_custom_colors": st.session_state.kcp_custom_colors,
        "enable_cluster": st.session_state.enable_cluster,
    }
    for i in range(1, 4):
        progress.update({
            f"radius_{i}_enabled": st.session_state.get(f"radius_{i}_enabled", False),
            f"radius_{i}_distance": st.session_state.get(f"radius_{i}_distance", 1.0),
            f"radius_{i}_color": st.session_state.get(f"radius_{i}_color", "red"),
            f"radius_{i}_target": st.session_state.get(f"radius_{i}_target", "blue"),
        })
    json_bytes = json.dumps(progress, default=serialize_time).encode("utf-8")
    st.sidebar.download_button("Simpan Progress (JSON)", data=json_bytes, file_name="saved_progress.json", mime="application/json")

    # === Main Map ===
    lat_center = filtered_df["Latitude"].mean()
    lon_center = filtered_df["Longitude"].mean()
    m = folium.Map(location=[lat_center, lon_center], zoom_start=6)
    plugins.Draw(export=True).add_to(m)

    marker_group = folium.FeatureGroup(name="Markers")
    marker_cluster = plugins.MarkerCluster() if st.session_state.enable_cluster else None

    for _, row in filtered_df.iterrows():
        lat, lon = row["Latitude"], row["Longitude"]
        warna = "blue"
        ref_value = row.get(warna_column)
        if ref_value in st.session_state.kcp_custom_colors:
            warna = st.session_state.kcp_custom_colors[ref_value]
        elif "Warna" in row and pd.notna(row["Warna"]):
            warna = row["Warna"]

        marker = folium.Marker(
            location=[lat, lon],
            popup=row["NamaTitik"],
            icon=folium.Icon(color=warna if warna in available_folium_colors else "blue", icon="info-sign")
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

    if st.session_state.enable_cluster:
        marker_cluster.add_to(m)
    else:
        marker_group.add_to(m)

    # === Legenda Peta ===
    legend_colors = {
        "Perwakilan": "red", "Lokasi": "blue"}
    legend_items = "".join([
        f"<div style='display: flex; align-items: center; margin-bottom: 4px;'>"
        f"<div style='width: 12px; height: 12px; border-radius: 50%; background: {c}; {'border:1px solid #ccc;' if c == 'white' else ''} margin-right: 6px;'></div> {l}</div>"
        for l, c in legend_colors.items()
    ])
    legend_html = f"""
    <div style="position: absolute; bottom: 10px; right: 10px; z-index: 9999; background-color: white;
        padding: 10px; border: 2px solid #ccc; border-radius: 8px; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
        font-size: 14px; max-width: 160px;">
        <b>Legenda:</b><br><div style="margin-top: 5px;">{legend_items}</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st_data = st_folium(m, use_container_width=True, height=700)

    # === Export Data ===
    df_export = filtered_df.copy()
    def get_final_color(row):
        ref_val = row.get(warna_column)
        if ref_val in st.session_state.kcp_custom_colors:
            return st.session_state.kcp_custom_colors[ref_val]
        elif "Warna" in row and pd.notna(row["Warna"]):
            return row["Warna"]
        return "blue"

    df_export["Warna_Akhir"] = df_export.apply(get_final_color, axis=1)
    buffer = BytesIO()
    df_export.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)
    st.download_button("Download Seluruh Data (Excel)", data=buffer, file_name="seluruh_data_dengan_warna.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Silakan upload file Excel untuk memulai.")
    if "saved_df" in st.session_state:
        df = st.session_state.saved_df
        st.success("Menampilkan data yang dimuat dari JSON sebelumnya.")
        st.write(df.head())
