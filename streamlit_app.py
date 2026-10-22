
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

# ============================================================
# FASE 2C - CORRESPONDENCIAS ESPACIALES Y TEMPORALES
# ============================================================

from math import radians, sin, cos, asin, sqrt

st.divider()
st.header("Fase 2C - Correspondencias espaciales y temporales")

st.write(
    "Comparación exploratoria entre detecciones MODIS y VIIRS "
    "mediante distancia geográfica y diferencia temporal."
)

def distancia_haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia entre dos coordenadas en km."""
    radio_tierra = 6371.0088

    lat1, lon1, lat2, lon2 = map(
        radians, [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 2 * radio_tierra * asin(min(1, sqrt(a)))


distancia_maxima = st.slider(
    "Distancia máxima entre detecciones (km)",
    min_value=0.5,
    max_value=20.0,
    value=2.0,
    step=0.5
)

tiempo_maximo = st.slider(
    "Diferencia temporal máxima (minutos)",
    min_value=15,
    max_value=1440,
    value=180,
    step=15
)

st.caption(
    "Los límites iniciales son exploratorios. "
    "No constituyen umbrales científicos validados."
)

columnas_necesarias = {
    "latitude", "longitude", "producto", "fecha_hora_utc"
}

if not columnas_necesarias.issubset(region_filtrada.columns):
    st.warning(
        "Faltan columnas necesarias para realizar la comparación."
    )

elif region_filtrada.empty:
    st.info("No hay detecciones en la región seleccionada.")

else:
    comparacion_2c = region_filtrada.copy()

    comparacion_2c["fecha_hora_utc"] = pd.to_datetime(
        comparacion_2c["fecha_hora_utc"],
        utc=True,
        errors="coerce"
    )

    comparacion_2c = comparacion_2c.dropna(
        subset=[
            "latitude",
            "longitude",
            "fecha_hora_utc",
            "producto"
        ]
    )

    modis = comparacion_2c[
        comparacion_2c["producto"]
        .astype(str)
        .str.upper()
        .str.contains("MODIS")
    ]

    viirs = comparacion_2c[
        comparacion_2c["producto"]
        .astype(str)
        .str.upper()
        .str.contains("VIIRS")
    ]

    coincidencias = []

    for indice_m, fila_m in modis.iterrows():
        for indice_v, fila_v in viirs.iterrows():

            distancia = distancia_haversine(
                fila_m["latitude"],
                fila_m["longitude"],
                fila_v["latitude"],
                fila_v["longitude"]
            )

            diferencia_min = abs(
                (
                    fila_m["fecha_hora_utc"]
                    - fila_v["fecha_hora_utc"]
                ).total_seconds()
            ) / 60

            if (
                distancia <= distancia_maxima
                and diferencia_min <= tiempo_maximo
            ):
                coincidencias.append({
                    "MODIS_indice": indice_m,
                    "VIIRS_indice": indice_v,
                    "Satélite_VIIRS": fila_v["producto"],
                    "Distancia_km": round(distancia, 3),
                    "Diferencia_min": round(diferencia_min, 1),
                    "Fecha_MODIS_UTC": fila_m["fecha_hora_utc"],
                    "Fecha_VIIRS_UTC": fila_v["fecha_hora_utc"],
                    "Lat_MODIS": fila_m["latitude"],
                    "Lon_MODIS": fila_m["longitude"],
                    "Lat_VIIRS": fila_v["latitude"],
                    "Lon_VIIRS": fila_v["longitude"]
                })

    resultados_2c = pd.DataFrame(coincidencias)

    st.subheader("Resultados de la comparación")

    col1, col2, col3 = st.columns(3)

    col1.metric("Detecciones MODIS", len(modis))
    col2.metric("Detecciones VIIRS", len(viirs))
    col3.metric(
        "Pares candidatos",
        len(resultados_2c)
    )

    if resultados_2c.empty:
        st.warning(
            "No se encontraron pares que cumplan ambos límites."
        )

    else:
        resultados_2c = resultados_2c.sort_values(
            ["Distancia_km", "Diferencia_min"]
        )

        st.dataframe(
            resultados_2c,
            use_container_width=True
        )

        st.download_button(
            "Descargar correspondencias CSV",
            data=resultados_2c.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="correspondencias_modis_viirs.csv",
            mime="text/csv"
        )

    st.info(
        "Los resultados representan pares candidatos, "
        "no incendios confirmados ni correspondencias únicas. "
        "Una misma detección puede aparecer en varios pares."
    )
