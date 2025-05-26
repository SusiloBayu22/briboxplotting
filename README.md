# 🗺️ Dynamic Map Viewer For PLOTTING MAP

**Dynamic Map Viewer** adalah aplikasi interaktif berbasis Streamlit yang memungkinkan pengguna untuk memvisualisasikan titik-titik lokasi dari file Excel pada peta menggunakan Folium. Aplikasi ini menyediakan fitur filter bertingkat, penyesuaian warna marker, klasterisasi, penggambaran radius, serta ekspor dan impor data konfigurasi.

---

## 🚀 Fitur Utama

✅ Upload file Excel berisi data lokasi  
✅ Filter data secara dinamis berdasarkan hierarki kolom  
✅ Atur warna marker berdasarkan nilai kolom  
✅ Tambahkan lingkaran radius di sekitar titik tertentu  
✅ Aktifkan/Nonaktifkan klasterisasi marker  
✅ Simpan dan muat konfigurasi peta dalam format JSON  
✅ Ekspor hasil filter dan warna akhir ke file Excel  

---

## 🧪 Contoh Kolom Data Excel

| NamaTitik     | Latitude | Longitude | Warna | Zona   | Nama Provinsi | Nama Kab/Kota | Nama KC Induk |
|---------------|----------|-----------|-------|--------|----------------|----------------|----------------|
| KCP Jakarta   | -6.2000  | 106.8167  | red   | Barat  | DKI Jakarta    | Jakarta Pusat  | KC Jakarta     |
| Unit Bandung  | -6.9147  | 107.6098  | green | Barat  | Jawa Barat     | Bandung        | KC Bandung     |
| KC Surabaya   | -7.2575  | 112.7521  | blue  | Timur  | Jawa Timur     | Surabaya       | KC Surabaya    |

Kolom `Warna` bersifat opsional. Jika tidak ada, maka marker akan diberi warna default (biru).  
Kolom tambahan seperti `Zona`, `Nama Provinsi`, dll akan otomatis menjadi filter bertingkat di sidebar.

---

## 📦 Instalasi

### 1. Clone Repo

```bash
git clone https://github.com/USERNAME/dynamic-map-viewer.git
cd dynamic-map-viewer
