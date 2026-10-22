
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from io import BytesIO
import zipfile

st.set_page_config(
    page_title="NASA MODIS–VIIRS",
    page_icon="🛰️",
    layout="wide"
)

st.title("🛰️ Armonización MODIS–VIIRS")
st.subheader("NASA Space Apps Challenge 2026")
st.info(
    "Prototipo exploratorio de detecciones térmicas. "
    "Una detección satelital no confirma por sí sola un incendio."
)

archivos = st.file_uploader(
    "Arrastrá los archivos CSV o ZIP de NASA FIRMS",
    type=["csv", "zip"],
    accept_multiple_files=True
)

def leer_archivo(archivo):
    if archivo.name.lower().endswith(".csv"):
        return [pd.read_csv(archivo)]

    tablas = []
    with zipfile.ZipFile(BytesIO(archivo.getvalue())) as z:
        for nombre in z.namelist():
            if nombre.lower().endswith(".csv"):
                with z.open(nombre) as f:
                    tablas.append(pd.read_csv(f))
    return tablas

def identificar_producto(nombre):
    nombre = nombre.lower()
    if "j1v" in nombre or "noaa20" in nombre:
        return "VIIRS NOAA-20"
    if "sv" in nombre or "snpp" in nombre:
        return "VIIRS S-NPP"
    if "m-c61" in nombre or "modis" in nombre:
        return "MODIS"
    return "Sin identificar"

if archivos:
    tablas = []

    for archivo in archivos:
        try:
            for tabla in leer_archivo(archivo):
                if not {"latitude", "longitude"}.issubset(tabla.columns):
                    st.warning(
                        f"{archivo.name}: faltan coordenadas."
                    )
                    continue

                if "producto" not in tabla.columns:
                    tabla["producto"] = identificar_producto(
                        archivo.name
                    )

                tablas.append(tabla)

        except Exception as e:
            st.error(f"Error en {archivo.name}: {e}")

    if tablas:
        datos = pd.concat(tablas, ignore_index=True)
        datos["latitude"] = pd.to_numeric(
            datos["latitude"], errors="coerce"
        )
        datos["longitude"] = pd.to_numeric(
            datos["longitude"], errors="coerce"
        )
        datos = datos.dropna(
            subset=["latitude", "longitude"]
        )

        st.success("Archivos procesados correctamente.")

        c1, c2 = st.columns(2)
        c1.metric("Detecciones térmicas", len(datos))
        c2.metric(
            "Productos identificados",
            datos["producto"].nunique()
        )

        st.subheader("Detecciones por producto")
        st.dataframe(
            datos["producto"].value_counts()
            .rename_axis("Producto")
            .reset_index(name="Detecciones"),
            use_container_width=True
        )

        st.subheader("Mapa interactivo")

        centro = [
            datos["latitude"].mean(),
            datos["longitude"].mean()
        ]

        mapa = folium.Map(
            location=centro,
            zoom_start=9,
            tiles=None
        )

        folium.TileLayer(
            tiles=(
                "https://server.arcgisonline.com/"
                "ArcGIS/rest/services/World_Street_Map/"
                "MapServer/tile/{z}/{y}/{x}"
            ),
            attr="Tiles © Esri"
        ).add_to(mapa)

        colores = {
            "MODIS": "red",
            "VIIRS NOAA-20": "blue",
            "VIIRS S-NPP": "green"
        }

        for producto, grupo in datos.groupby("producto"):
            capa = folium.FeatureGroup(
                name=str(producto)
            )

            for _, fila in grupo.iterrows():
                folium.CircleMarker(
                    location=[
                        fila["latitude"],
                        fila["longitude"]
                    ],
                    radius=5,
                    color=colores.get(
                        producto, "orange"
                    ),
                    fill=True,
                    fill_opacity=0.8,
                    popup=str(producto)
                ).add_to(capa)

            capa.add_to(mapa)

        folium.LayerControl().add_to(mapa)

        st_folium(
            mapa,
            width=None,
            height=520,
            returned_objects=[]
        )

        st.subheader("Datos procesados")
        st.dataframe(
            datos,
            use_container_width=True
        )

        st.download_button(
            "Descargar CSV unificado",
            datos.to_csv(index=False).encode("utf-8"),
            file_name="datos_unificados.csv",
            mime="text/csv"
        )

        st.caption(
            "Próxima etapa: correspondencias espaciales, "
            "temporales y calendario de actividad."
        )

else:
    st.write(
        "👆 Cargá los archivos originales NASA FIRMS "
        "para comenzar."
    )

# ==================================================
# FASE 2A - COMPARACION TEMPORAL MODIS / VIIRS
# ==================================================

if archivos:
    st.divider()
    st.header("Fase 2A - Comparacion temporal")

    comparacion = datos.copy()

    if {"acq_date", "acq_time", "producto"}.issubset(comparacion.columns):

        comparacion["hora_texto"] = (
            comparacion["acq_time"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.zfill(4)
        )

        comparacion["fecha_hora_utc"] = pd.to_datetime(
            comparacion["acq_date"].astype(str)
            + " "
            + comparacion["hora_texto"].str[:2]
            + ":"
            + comparacion["hora_texto"].str[2:],
            errors="coerce",
            utc=True
        )

        comparacion = comparacion.dropna(
            subset=["fecha_hora_utc"]
        )

        st.subheader("Detecciones por fecha y satelite")

        resumen = (
            comparacion.groupby(
                [comparacion["fecha_hora_utc"].dt.date, "producto"]
            )
            .size()
            .unstack(fill_value=0)
        )

        st.dataframe(resumen, use_container_width=True)
        st.bar_chart(resumen)

        st.caption(
            "Los registros corresponden a detecciones "
            "termicas satelitales, no necesariamente "
            "a incendios diferentes. "
            "La comparacion temporal no implica "
            "observaciones simultaneas."
        )
    else:
        st.warning(
            "Faltan columnas necesarias para "
            "realizar la comparacion temporal."
        )

# ==========================================
# FASE 2B - SELECCION GEOGRAFICA
# ==========================================

if archivos:
    st.divider()
    st.header("Fase 2B - Seleccion geografica")

    st.write(
        "Selecciona los limites geograficos para "
        "analizar las detecciones termicas."
    )

    lat_min = st.number_input(
        "Latitud minima",
        value=-33.46,
        format="%.4f"
    )

    lat_max = st.number_input(
        "Latitud maxima",
        value=-33.28,
        format="%.4f"
    )

    lon_min = st.number_input(
        "Longitud minima",
        value=-56.75,
        format="%.4f"
    )

    lon_max = st.number_input(
        "Longitud maxima",
        value=-56.44,
        format="%.4f"
    )

    if lat_min >= lat_max or lon_min >= lon_max:
        st.error("Revisa los limites geograficos.")
    else:
        region_filtrada = datos.loc[
            datos["latitude"].between(lat_min, lat_max)
            & datos["longitude"].between(lon_min, lon_max)
        ].copy()

        st.metric(
            "Detecciones en la region",
            len(region_filtrada)
        )

        st.subheader("Detecciones por producto")

        if region_filtrada.empty:
            st.warning(
                "No hay detecciones en esta region."
            )
        else:
            conteo_region = (
                region_filtrada["producto"]
                .value_counts()
                .rename_axis("Producto")
                .reset_index(name="Detecciones")
            )

            st.dataframe(
                conteo_region,
                use_container_width=True
            )
