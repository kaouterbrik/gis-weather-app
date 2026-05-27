import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.graph_objects as go
import requests

st.set_page_config(page_title="GIS Weather App – Laâyoune-Sakia El Hamra", page_icon="🌍", layout="wide")

st.markdown("""
<style>
    .main-title { font-size: 2rem; font-weight: 700; color: #1a5276; text-align: center; margin-bottom: 0.2rem; }
    .sub-title { text-align: center; color: #555; margin-bottom: 1.5rem; font-size: 0.95rem; }
    .info-box { background-color: #eaf4fb; border-left: 4px solid #2e86c1; padding: 0.6rem 1rem; border-radius: 4px; margin-bottom: 0.8rem; font-size: 0.9rem; }
    .section-header { font-size: 1.1rem; font-weight: 600; color: #1a5276; border-bottom: 2px solid #d6eaf8; padding-bottom: 0.3rem; margin-bottom: 0.8rem; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🌍 Application GIS – Prévisions Météo</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Région : <strong>Laâyoune-Sakia El Hamra</strong> · Navigation administrative + Météo 15 jours</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CHARGEMENT SHAPEFILES
# ─────────────────────────────────────────────
@st.cache_data
def load_shapefiles():
    regions   = gpd.read_file("data/Decoupage_HCP_WGS84/Regions_WGS84.shp")
    provinces = gpd.read_file("data/Decoupage_HCP_WGS84/Provinces_WGS84.shp")
    communes  = gpd.read_file("data/Decoupage_HCP_WGS84/communes_WGS84.shp")
    # Convertir les colonnes texte
    regions["libelle_fr"]   = regions["libelle_fr"].astype(str)
    provinces["libelle_fr"] = provinces["libelle_fr"].astype(str)
    communes["FIRST_com_"]  = communes["FIRST_com_"].astype(str)
    communes["FIRST_prov"]  = communes["FIRST_prov"].astype(str)
    return regions, provinces, communes

try:
    regions_gdf, provinces_gdf, communes_gdf = load_shapefiles()
except Exception as e:
    st.error(f"❌ Impossible de charger les shapefiles : {e}")
    st.stop()

# ─────────────────────────────────────────────
# RÉGION (code_reg = 11)
# ─────────────────────────────────────────────
CODE_REGION = 11.0
region_row  = regions_gdf[regions_gdf["code_reg"] == CODE_REGION]
if region_row.empty:
    st.error("❌ Région introuvable.")
    st.stop()
region_name = region_row["libelle_fr"].iloc[0]

# ─────────────────────────────────────────────
# PROVINCES (code_reg == 11)
# ─────────────────────────────────────────────
provinces_region = provinces_gdf[provinces_gdf["code_reg"] == CODE_REGION].copy()
province_list    = sorted(provinces_region["libelle_fr"].unique().tolist())

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🗂️ Navigation administrative")
    st.info(f"📍 Région fixée : **{region_name}**")

    selected_province = st.selectbox("🏛️ Province / Préfecture", province_list)

    prov_row  = provinces_region[provinces_region["libelle_fr"] == selected_province]
    prov_geom = prov_row.geometry.iloc[0]

    # Communes filtrées par nom de province dans FIRST_prov
    communes_prov = communes_gdf[communes_gdf["FIRST_prov"] == selected_province].copy()

    # Si pas de résultat direct, faire un spatial join
    if communes_prov.empty:
        @st.cache_data
        def get_communes_spatial(_prov_geom, _communes_gdf):
            joined = gpd.sjoin(
                _communes_gdf[["FIRST_com_", "geometry"]],
                gpd.GeoDataFrame(geometry=[_prov_geom], crs=_communes_gdf.crs),
                how="inner", predicate="intersects"
            )
            return sorted(joined["FIRST_com_"].dropna().unique().tolist())
        commune_list = get_communes_spatial(prov_geom, communes_gdf)
        communes_prov = communes_gdf[communes_gdf["FIRST_com_"].isin(commune_list)]
    else:
        commune_list = sorted(communes_prov["FIRST_com_"].unique().tolist())

    if not commune_list:
        st.warning("Aucune commune trouvée.")
        st.stop()

    selected_commune = st.selectbox("🏘️ Commune", commune_list)

    st.markdown("---")
    st.markdown("### 📊 Paramètre météo")
    meteo_param = st.radio("Choisir le paramètre :", ["🌡️ Température (°C)", "🌧️ Précipitations (mm)"])

# ─────────────────────────────────────────────
# DONNÉES ACTIVES
# ─────────────────────────────────────────────
commune_row  = communes_gdf[communes_gdf["FIRST_com_"] == selected_commune]
commune_geom = commune_row.geometry.iloc[0]
centroid     = commune_geom.centroid
lat, lon     = centroid.y, centroid.x

# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────
col_map, col_weather = st.columns([3, 2], gap="medium")

# ══════════════════════════════════════════════
# CARTE FOLIUM
# ══════════════════════════════════════════════
with col_map:
    st.markdown('<div class="section-header">🗺️ Carte interactive</div>', unsafe_allow_html=True)
    st.markdown(f"""<div class="info-box">
        📍 <strong>Région :</strong> {region_name} &nbsp;|&nbsp;
        <strong>Province :</strong> {selected_province} &nbsp;|&nbsp;
        <strong>Commune :</strong> {selected_commune}
    </div>""", unsafe_allow_html=True)

    m = folium.Map(location=[lat, lon], zoom_start=10, control_scale=True, tiles=None)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", overlay=False, control=True).add_to(m)
    folium.TileLayer(
        tiles="https://tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="© OpenTopoMap (CC-BY-SA)", name="Relief (OpenTopoMap)",
        overlay=True, control=True, opacity=0.6,
    ).add_to(m)

    folium.GeoJson(region_row.__geo_interface__, name="Région",
        style_function=lambda _: {"color": "#1a5276", "weight": 2.5, "fillOpacity": 0.0, "dashArray": "6 4"},
        tooltip=folium.GeoJsonTooltip(fields=["libelle_fr"], aliases=["Région :"]),
    ).add_to(m)

    folium.GeoJson(prov_row.__geo_interface__, name="Province",
        style_function=lambda _: {"color": "#1e8449", "weight": 2, "fillOpacity": 0.05, "fillColor": "#27ae60"},
        tooltip=folium.GeoJsonTooltip(fields=["libelle_fr"], aliases=["Province :"]),
    ).add_to(m)

    folium.GeoJson(commune_row.__geo_interface__, name="Commune",
        style_function=lambda _: {"color": "#c0392b", "weight": 2.5, "fillOpacity": 0.12, "fillColor": "#e74c3c"},
        tooltip=folium.GeoJsonTooltip(fields=["FIRST_com_"], aliases=["Commune :"]),
    ).add_to(m)

    folium.Marker(location=[lat, lon],
        popup=f"<b>{selected_commune}</b><br>Lat: {lat:.4f} | Lon: {lon:.4f}",
        icon=folium.Icon(color="red", icon="map-marker", prefix="fa"),
    ).add_to(m)

    m.get_root().html.add_child(folium.Element("""
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
        padding:10px 14px;border-radius:8px;border:1px solid #ccc;font-size:13px;
        line-height:1.7;box-shadow:2px 2px 6px rgba(0,0,0,0.2);">
        <b>Légende</b><br>
        <span style="color:#1a5276;">━━</span> Région<br>
        <span style="color:#1e8449;">━━</span> Province<br>
        <span style="color:#c0392b;">━━</span> Commune
    </div>"""))

    m.get_root().html.add_child(folium.Element(f"""
    <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:1000;
        background:rgba(255,255,255,0.92);padding:6px 16px;border-radius:6px;
        font-size:14px;font-weight:600;color:#1a5276;box-shadow:1px 1px 4px rgba(0,0,0,0.15);">
        {selected_commune} · {selected_province} · {region_name}
    </div>"""))

    bounds = commune_row.total_bounds
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    folium.LayerControl(collapsed=False).add_to(m)
    st_folium(m, width=None, height=520, returned_objects=[])

# ══════════════════════════════════════════════
# MÉTÉO
# ══════════════════════════════════════════════
with col_weather:
    st.markdown('<div class="section-header">🌤️ Prévisions météo – 15 jours</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=3600)
    def fetch_weather(lat, lon):
        try:
            resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "Africa/Casablanca", "forecast_days": 15,
            }, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except:
            return None

    with st.spinner("Récupération des données météo..."):
        weather_data = fetch_weather(lat, lon)

    if weather_data is None:
        st.error("❌ Impossible de récupérer les données météo.")
    else:
        daily = weather_data.get("daily", {})
        df = pd.DataFrame({
            "Date":           pd.to_datetime(daily.get("time", [])),
            "Temp Max":       daily.get("temperature_2m_max", []),
            "Temp Min":       daily.get("temperature_2m_min", []),
            "Précipitations": daily.get("precipitation_sum", []),
        })
        df["Date_str"] = df["Date"].dt.strftime("%d/%m/%Y")

        if not df.empty:
            k1, k2, k3 = st.columns(3)
            k1.metric("🌡️ Temp. max", f"{df['Temp Max'].iloc[0]:.1f} °C")
            k2.metric("🌡️ Temp. min", f"{df['Temp Min'].iloc[0]:.1f} °C")
            k3.metric("🌧️ Précip.",   f"{df['Précipitations'].iloc[0]:.1f} mm")

        st.markdown("---")

        if "Température" in meteo_param:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["Date_str"], y=df["Temp Max"], mode="lines+markers",
                name="Temp. Max", line=dict(color="#e74c3c", width=2.5), marker=dict(size=6),
                hovertemplate="%{x}<br>Max: %{y:.1f} °C<extra></extra>"))
            fig.add_trace(go.Scatter(x=df["Date_str"], y=df["Temp Min"], mode="lines+markers",
                name="Temp. Min", line=dict(color="#2e86c1", width=2.5), marker=dict(size=6),
                hovertemplate="%{x}<br>Min: %{y:.1f} °C<extra></extra>",
                fill="tonexty", fillcolor="rgba(174,214,241,0.25)"))
            fig.update_layout(title=f"Température – {selected_commune}",
                xaxis_title="Date", yaxis_title="Température (°C)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified", plot_bgcolor="white", height=370,
                margin=dict(t=50, b=40, l=50, r=20))
        else:
            colors = ["#2e86c1" if p > 0 else "#d5dbdb" for p in df["Précipitations"]]
            fig = go.Figure(go.Bar(x=df["Date_str"], y=df["Précipitations"],
                marker_color=colors, name="Précipitations",
                hovertemplate="%{x}<br>%{y:.1f} mm<extra></extra>"))
            fig.update_layout(title=f"Précipitations – {selected_commune}",
                xaxis_title="Date", yaxis_title="Précipitations (mm)",
                plot_bgcolor="white", height=370, margin=dict(t=50, b=40, l=50, r=20))

        fig.update_xaxes(tickangle=-45, showgrid=True, gridcolor="#eee")
        fig.update_yaxes(showgrid=True, gridcolor="#eee")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 Tableau des données brutes"):
            df_d = df[["Date_str","Temp Max","Temp Min","Précipitations"]].copy()
            df_d.columns = ["Date","Temp. Max (°C)","Temp. Min (°C)","Précip. (mm)"]
            st.dataframe(df_d, use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("<small>Sources : shapefiles HCP Maroc · "
    "<a href='https://open-meteo.com' target='_blank'>Open-Meteo API</a> · "
    "<a href='https://opentopomap.org' target='_blank'>OpenTopoMap</a> · "
    "GIS Programming 2025-2026 · EHTP</small>", unsafe_allow_html=True)