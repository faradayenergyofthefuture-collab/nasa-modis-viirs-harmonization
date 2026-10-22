
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from io import BytesIO
import zipfile
from datetime import timedelta

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

# El análisis necesita archivos para ejecutar todas sus fases.
if not archivos:
    st.info("Cargá archivos NASA FIRMS para iniciar el estudio en Uruguay.")
    st.stop()

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

    if not tablas:
        st.error("No se encontraron tablas CSV válidas.")
        st.stop()

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

        # Recorte preliminar por extensión territorial aproximada.
        # NO equivale al contorno administrativo exacto de Uruguay.
        total_cargado = len(datos)
        datos = datos.loc[
            datos["latitude"].between(-35.2, -30.0)
            & datos["longitude"].between(-58.6, -53.0)
        ].copy().reset_index(drop=True)
        st.caption(
            "Filtro preliminar Uruguay: latitudes -35.2 a -30.0 y "
            "longitudes -58.6 a -53.0. Es un rectángulo aproximado, "
            "no una frontera administrativa exacta."
        )
        st.write(f"Registros fuera del recorte aproximado: {total_cargado - len(datos)}")
        if datos.empty:
            st.error("No hay detecciones dentro del recorte geográfico de Uruguay.")
            st.stop()

        # Fecha UTC única y consistente para todas las fases.
        if {"acq_date", "acq_time"}.issubset(datos.columns):
            hora = (datos["acq_time"].astype(str)
                    .str.replace(r"\.0$", "", regex=True).str.zfill(4))
            datos["fecha_hora_utc"] = pd.to_datetime(
                datos["acq_date"].astype(str) + " "
                + hora.str[:2] + ":" + hora.str[2:],
                errors="coerce", utc=True
            )
        else:
            st.error("Los archivos requieren acq_date y acq_time para comparar satélites.")
            st.stop()

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

    st.caption("Definí el área dentro del recorte aproximado de Uruguay. "
               "Podés estudiar un departamento o una zona más pequeña.")
    nombre_caso = st.text_input(
        "Nombre del área o caso de estudio",
        value="Área seleccionada de Uruguay",
        key="nombre_caso_uy"
    )
    min_lat_d, max_lat_d = float(datos.latitude.min()), float(datos.latitude.max())
    min_lon_d, max_lon_d = float(datos.longitude.min()), float(datos.longitude.max())
    lat_min = st.number_input("Latitud mínima", min_value=-35.2,
                              max_value=-30.0, value=max(-35.2, min_lat_d - 0.01),
                              format="%.4f")
    lat_max = st.number_input("Latitud máxima", min_value=-35.2,
                              max_value=-30.0, value=min(-30.0, max_lat_d + 0.01),
                              format="%.4f")
    lon_min = st.number_input("Longitud mínima", min_value=-58.6,
                              max_value=-53.0, value=max(-58.6, min_lon_d - 0.01),
                              format="%.4f")
    lon_max = st.number_input("Longitud máxima", min_value=-58.6,
                              max_value=-53.0, value=min(-53.0, max_lon_d + 0.01),
                              format="%.4f")
    if lat_min >= lat_max or lon_min >= lon_max:
        st.error("El rango geográfico no es válido.")
        st.stop()
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


# Crear fecha y hora UTC a partir de los datos NASA FIRMS
if {"acq_date", "acq_time"}.issubset(region_filtrada.columns):
    fecha = region_filtrada["acq_date"].astype(str)
    hora = (region_filtrada["acq_time"].astype(str)
            .str.replace(r"\.0$", "", regex=True).str.zfill(4))

    region_filtrada["fecha_hora_utc"] = pd.to_datetime(
        fecha + " " + hora.str[:2] + ":" + hora.str[2:],
        format="%Y-%m-%d %H:%M",
        utc=True,
        errors="coerce"
    )

if not columnas_necesarias.issubset(region_filtrada.columns):
    faltantes = sorted(
        columnas_necesarias - set(region_filtrada.columns)
    )

    st.warning(
        "Faltan columnas necesarias para realizar la comparación."
    )

    st.write("Columnas faltantes:", faltantes)
    st.write(
        "Columnas disponibles:",
        list(region_filtrada.columns)
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

# ============================================================
# FASE 2D - EVALUACION DE CORRESPONDENCIAS UNICAS
# ============================================================

import numpy as np

st.divider()
st.header("Fase 2D - Evaluación de correspondencias")
st.write(
    "Análisis de detecciones únicas, correspondencias candidatas "
    "y sensibilidad a los límites espaciales y temporales."
)

st.info(
    "Los resultados son exploratorios. Una correspondencia "
    "entre satélites no confirma por sí sola un incendio."
)

# Parámetros independientes para esta fase
col_d1, col_d2 = st.columns(2)

with col_d1:
    limite_km_2d = st.slider(
        "Distancia máxima 2D (km)",
        min_value=0.1,
        max_value=10.0,
        value=2.0,
        step=0.1,
        key="distancia_2d"
    )

with col_d2:
    limite_min_2d = st.slider(
        "Diferencia temporal máxima 2D (minutos)",
        min_value=10,
        max_value=720,
        value=180,
        step=10,
        key="tiempo_2d"
    )

def distancia_haversine_km(lat1, lon1, lat2, lon2):
    radio = 6371.0088
    lat1, lon1, lat2, lon2 = np.radians(
        [lat1, lon1, lat2, lon2]
    )
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * radio * np.arcsin(np.sqrt(a))

def preparar_fechas_2d(tabla):
    tabla = tabla.copy()

    if {"acq_date", "acq_time"}.issubset(tabla.columns):
        fecha = tabla["acq_date"].astype(str)
        hora = (tabla["acq_time"].astype(str)
                .str.replace(r"\.0$", "", regex=True).str.zfill(4))

        tabla["fecha_2d"] = pd.to_datetime(
            fecha + " " + hora.str[:2] + ":" + hora.str[2:],
            format="%Y-%m-%d %H:%M",
            utc=True,
            errors="coerce"
        )

    elif "fecha_hora_utc" in tabla.columns:
        tabla["fecha_2d"] = pd.to_datetime(
            tabla["fecha_hora_utc"],
            utc=True,
            errors="coerce"
        )

    else:
        tabla["fecha_2d"] = pd.NaT

    return tabla

columnas_base_2d = {
    "latitude", "longitude", "producto"
}

if not columnas_base_2d.issubset(region_filtrada.columns):
    st.warning(
        "Faltan columnas de coordenadas o producto "
        "para realizar la Fase 2D."
    )

else:
    base_2d = preparar_fechas_2d(region_filtrada)

    base_2d["latitude"] = pd.to_numeric(
        base_2d["latitude"], errors="coerce"
    )
    base_2d["longitude"] = pd.to_numeric(
        base_2d["longitude"], errors="coerce"
    )

    base_2d = base_2d.dropna(
        subset=["latitude", "longitude", "fecha_2d"]
    )

    # Conservar los índices originales para identificar registros
    modis_2d = base_2d[
        base_2d["producto"].astype(str).str.upper().str.contains("MODIS")
    ]

    viirs_2d = base_2d[
        base_2d["producto"].astype(str).str.upper().str.contains("VIIRS")
    ]

    pares_2d = []

    for indice_m, m in modis_2d.iterrows():
        for indice_v, v in viirs_2d.iterrows():

            distancia = distancia_haversine_km(
                m["latitude"], m["longitude"],
                v["latitude"], v["longitude"]
            )

            diferencia = abs(
                (m["fecha_2d"] - v["fecha_2d"]).total_seconds()
            ) / 60

            if (
                distancia <= limite_km_2d
                and diferencia <= limite_min_2d
            ):
                pares_2d.append({
                    "MODIS_indice": indice_m,
                    "VIIRS_indice": indice_v,
                    "Satélite_VIIRS": v["producto"],
                    "Distancia_km": round(float(distancia), 3),
                    "Diferencia_min": round(float(diferencia), 1)
                })

    tabla_pares_2d = pd.DataFrame(
        pares_2d,
        columns=[
            "MODIS_indice", "VIIRS_indice",
            "Satélite_VIIRS", "Distancia_km",
            "Diferencia_min"
        ]
    )

    modis_total = len(modis_2d)
    viirs_total = len(viirs_2d)

    modis_unicos = tabla_pares_2d["MODIS_indice"].nunique()
    viirs_unicos = tabla_pares_2d["VIIRS_indice"].nunique()

    st.subheader("Resultados de detecciones únicas")

    c1, c2, c3 = st.columns(3)

    c1.metric("MODIS con correspondencia", modis_unicos)
    c2.metric("VIIRS con correspondencia", viirs_unicos)
    c3.metric("Pares candidatos", len(tabla_pares_2d))

    c4, c5 = st.columns(2)

    c4.metric(
        "MODIS sin correspondencia",
        modis_total - modis_unicos
    )

    c5.metric(
        "VIIRS sin correspondencia",
        viirs_total - viirs_unicos
    )

    porcentaje_modis = (
        100 * modis_unicos / modis_total
        if modis_total else 0
    )
    porcentaje_viirs = (
        100 * viirs_unicos / viirs_total
        if viirs_total else 0
    )

    st.subheader("Cobertura de correspondencias")

    resumen_2d = pd.DataFrame({
        "Instrumento": ["MODIS", "VIIRS"],
        "Detecciones totales": [modis_total, viirs_total],
        "Con correspondencia": [modis_unicos, viirs_unicos],
        "Sin correspondencia": [
            modis_total - modis_unicos,
            viirs_total - viirs_unicos
        ],
        "Porcentaje (%)": [
            round(porcentaje_modis, 2),
            round(porcentaje_viirs, 2)
        ]
    })

    st.dataframe(resumen_2d, use_container_width=True)

    if not tabla_pares_2d.empty:

        st.subheader("Repeticiones de detecciones")

        rep_modis = (
            tabla_pares_2d.groupby("MODIS_indice")
            .size()
            .rename("Pares candidatos")
            .reset_index()
            .sort_values("Pares candidatos", ascending=False)
        )

        st.write(
            "Cantidad de pares candidatos asociados "
            "a cada detección MODIS."
        )
        st.dataframe(rep_modis, use_container_width=True)

        st.subheader("Correspondencia más cercana por MODIS")

        cercanas_2d = (
            tabla_pares_2d.sort_values(
                ["Distancia_km", "Diferencia_min"]
            )
            .drop_duplicates(subset=["MODIS_indice"])
        )

        st.dataframe(
            cercanas_2d,
            use_container_width=True
        )

        st.caption(
            "La correspondencia más cercana es una selección "
            "exploratoria por distancia. No garantiza una "
            "asociación única ni identifica incendios confirmados."
        )

    else:
        st.warning(
            "No se encontraron pares candidatos "
            "con los límites seleccionados."
        )

    st.caption(
        "Los porcentajes representan cobertura de correspondencias "
        "en la muestra analizada. No representan precisión, "
        "sensibilidad ni validación independiente del algoritmo."
    )

# ============================================================
# FASE 2E - ANALISIS AUTOMATICO DE SENSIBILIDAD
# ============================================================

import numpy as np

st.divider()
st.header("Fase 2E - Analisis de sensibilidad")

st.write(
    "Evaluacion de la estabilidad de las correspondencias "
    "MODIS-VIIRS ante diferentes limites espaciales y temporales."
)

st.info(
    "Este analisis mide correspondencias candidatas. "
    "No mide precision ni confirma incendios."
)

# Trabajar sobre la region seleccionada
base_2e = region_filtrada.copy()

columnas_2e = {
    "latitude", "longitude", "producto",
    "fecha_hora_utc"
}

if not columnas_2e.issubset(base_2e.columns):
    st.warning(
        "Faltan columnas para realizar el analisis de sensibilidad."
    )

else:
    base_2e["fecha_hora_utc"] = pd.to_datetime(
        base_2e["fecha_hora_utc"],
        utc=True,
        errors="coerce"
    )

    for columna in ["latitude", "longitude"]:
        base_2e[columna] = pd.to_numeric(
            base_2e[columna],
            errors="coerce"
        )

    base_2e = base_2e.dropna(
        subset=[
            "latitude", "longitude",
            "fecha_hora_utc", "producto"
        ]
    )

    modis_2e = base_2e[
        base_2e["producto"].astype(str)
        .str.upper().str.contains("MODIS")
    ].copy()

    viirs_2e = base_2e[
        base_2e["producto"].astype(str)
        .str.upper().str.contains("VIIRS")
    ].copy()

    if modis_2e.empty or viirs_2e.empty:
        st.warning(
            "Se necesitan detecciones MODIS y VIIRS "
            "para realizar la comparacion."
        )

    else:
        # Conservar identificadores de las filas originales
        modis_2e = modis_2e.reset_index(drop=True)
        viirs_2e = viirs_2e.reset_index(drop=True)

        # Distancias geograficas mediante Haversine
        radio_tierra_km = 6371.0088

        lat_m = np.radians(
            modis_2e["latitude"].to_numpy()
        )[:, None]

        lon_m = np.radians(
            modis_2e["longitude"].to_numpy()
        )[:, None]

        lat_v = np.radians(
            viirs_2e["latitude"].to_numpy()
        )[None, :]

        lon_v = np.radians(
            viirs_2e["longitude"].to_numpy()
        )[None, :]

        dlat = lat_v - lat_m
        dlon = lon_v - lon_m

        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(lat_m)
            * np.cos(lat_v)
            * np.sin(dlon / 2) ** 2
        )

        a = np.clip(a, 0, 1)

        distancias = (
            2 * radio_tierra_km
            * np.arcsin(np.sqrt(a))
        )

        # Diferencia absoluta de tiempo en minutos
        tiempos_m = modis_2e[
            "fecha_hora_utc"
        ].to_numpy()[:, None]

        tiempos_v = viirs_2e[
            "fecha_hora_utc"
        ].to_numpy()[None, :]

        diferencias_min = (
            np.abs(tiempos_m - tiempos_v)
            / np.timedelta64(1, "m")
        )

        # Escenarios exploratorios
        limites_km = [0.5, 1.0, 2.0]
        limites_min = [30, 60, 180]

        resultados_2e = []

        for distancia_max in limites_km:
            for tiempo_max in limites_min:

                mascara = (
                    (distancias <= distancia_max)
                    & (diferencias_min <= tiempo_max)
                )

                pares = int(mascara.sum())

                modis_con = int(
                    mascara.any(axis=1).sum()
                )

                viirs_con = int(
                    mascara.any(axis=0).sum()
                )

                resultados_2e.append({
                    "Distancia_km": distancia_max,
                    "Tiempo_min": tiempo_max,
                    "Pares_candidatos": pares,
                    "MODIS_con": modis_con,
                    "VIIRS_con": viirs_con,
                    "Cobertura_MODIS_pct": round(
                        100 * modis_con / len(modis_2e), 2
                    ),
                    "Cobertura_VIIRS_pct": round(
                        100 * viirs_con / len(viirs_2e), 2
                    )
                })

        tabla_2e = pd.DataFrame(resultados_2e)

        st.subheader("Comparacion de los nueve escenarios")

        st.dataframe(
            tabla_2e,
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Evolucion de pares candidatos")

        grafico_2e = tabla_2e.pivot(
            index="Tiempo_min",
            columns="Distancia_km",
            values="Pares_candidatos"
        )

        grafico_2e.columns = [
            f"{col} km" for col in grafico_2e.columns
        ]

        st.line_chart(grafico_2e)

        st.caption(
            "Cada curva representa una distancia maxima. "
            "El eje horizontal representa la ventana temporal "
            "en minutos."
        )

        csv_2e = tabla_2e.to_csv(
            index=False,
            sep=";",
            decimal=","
        ).encode("utf-8-sig")

        st.download_button(
            "Descargar analisis de sensibilidad CSV",
            data=csv_2e,
            file_name="sensibilidad_modis_viirs.csv",
            mime="text/csv"
        )

        st.success(
            "Analisis de sensibilidad completado."
        )

# ============================================================
# FASE 3 - RESULTADOS Y CONCLUSIONES DINÁMICOS
# Se alimenta de la región filtrada y los resultados de Fase 2E.
# ============================================================

st.divider()
st.header("Fase 3 - Resultados y conclusiones")
st.info("Las asociaciones son candidatas, no incendios confirmados ni validación independiente.")

st.subheader(f"Caso de estudio: {nombre_caso.strip() or 'Área seleccionada'}, Uruguay")
base_fase3 = region_filtrada.copy()
base_fase3["fecha_hora_utc"] = pd.to_datetime(
    base_fase3["fecha_hora_utc"], utc=True, errors="coerce"
)
base_fase3 = base_fase3.dropna(subset=["fecha_hora_utc"])

if base_fase3.empty:
    st.warning("No hay registros con fecha válida en la región seleccionada.")
    st.stop()

fecha_min = base_fase3["fecha_hora_utc"].min()
fecha_max = base_fase3["fecha_hora_utc"].max()
st.write(f"Período observado en los datos filtrados (UTC): "
         f"{fecha_min:%d/%m/%Y %H:%M} a {fecha_max:%d/%m/%Y %H:%M}.")
st.caption("Este período corresponde a registros presentes en los archivos; "
           "no necesariamente al período completo solicitado a NASA FIRMS.")

conteo = base_fase3["producto"].value_counts()
c1, c2, c3, c4 = st.columns(4)
c1.metric("MODIS", int(conteo.get("MODIS", 0)))
c2.metric("VIIRS NOAA-20", int(conteo.get("VIIRS NOAA-20", 0)))
c3.metric("VIIRS S-NPP", int(conteo.get("VIIRS S-NPP", 0)))
c4.metric("Total regional", len(base_fase3))
st.caption("Se cuentan anomalías térmicas detectadas, no incendios individuales.")

st.subheader("Comparación de escenarios calculada")
if "tabla_2e" in globals() and not tabla_2e.empty and not modis_2e.empty and not viirs_2e.empty:
    resumen_fase3 = tabla_2e.copy()
    st.dataframe(resumen_fase3, use_container_width=True, hide_index=True)
    st.caption("Los nueve escenarios se recalculan con la región y los ZIP/CSV cargados.")
else:
    resumen_fase3 = pd.DataFrame()
    st.warning("No hay comparación MODIS–VIIRS disponible para este caso. "
               "Se requieren registros válidos de ambos sensores.")

st.subheader("Interpretación científica")
st.markdown("""
- MODIS y VIIRS pueden observar una misma zona en horarios y posiciones distintos.
- Aumentar las tolerancias espacial y temporal puede incrementar los pares candidatos.
- Una detección puede participar en varios pares: no son asociaciones uno a uno.
- Sin referencia externa de incendios reales no se puede medir precisión, sensibilidad
  ni tasa de falsos positivos.
""")

st.subheader("Estado de validación")
estado_fase3 = pd.DataFrame([
    {"Actividad": "Lectura y filtrado de datos NASA FIRMS", "Estado": "Completada"},
    {"Actividad": "Visualización geográfica", "Estado": "Completada"},
    {"Actividad": "Comparación espacial y temporal", "Estado": "Completada si hay ambos sensores"},
    {"Actividad": "Análisis de sensibilidad", "Estado": "Completada si hay ambos sensores"},
    {"Actividad": "Segundo caso de estudio", "Estado": "Pendiente de prueba"},
    {"Actividad": "Validación independiente", "Estado": "Pendiente"},
])
st.dataframe(estado_fase3, use_container_width=True, hide_index=True)

st.subheader("Conclusión del estudio")
if not resumen_fase3.empty:
    base_1km_60 = resumen_fase3.loc[
        (resumen_fase3["Distancia_km"] == 1.0) &
        (resumen_fase3["Tiempo_min"] == 60)
    ]
    pares_referencia = int(base_1km_60.iloc[0]["Pares_candidatos"])
    conclusion_fase3 = (
        f"En {nombre_caso.strip() or 'el área seleccionada'} se analizaron "
        f"{len(base_fase3)} detecciones térmicas. Con límites de 1 km y 60 minutos "
        f"se encontraron {pares_referencia} pares candidatos MODIS–VIIRS. "
        "El número de asociaciones depende de los límites espaciales y temporales. "
        "Estos resultados son exploratorios y no identifican incendios confirmados."
    )
else:
    conclusion_fase3 = (
        f"En {nombre_caso.strip() or 'el área seleccionada'} se analizaron "
        f"{len(base_fase3)} detecciones térmicas. No se pudo calcular una comparación "
        "entre MODIS y VIIRS con los datos disponibles."
    )
st.success(conclusion_fase3)

st.subheader("Descargar informe")
informe_fase3 = (
    "NASA MODIS–VIIRS HARMONIZATION\n"
    "INFORME EXPLORATORIO DINÁMICO – URUGUAY\n\n"
    f"Caso: {nombre_caso.strip() or 'Área seleccionada'}, Uruguay\n"
    f"Región: lat {lat_min:.4f} a {lat_max:.4f}; "
    f"lon {lon_min:.4f} a {lon_max:.4f}\n"
    f"Período observado (UTC): {fecha_min} a {fecha_max}\n"
    f"MODIS: {int(conteo.get('MODIS', 0))}\n"
    f"VIIRS NOAA-20: {int(conteo.get('VIIRS NOAA-20', 0))}\n"
    f"VIIRS S-NPP: {int(conteo.get('VIIRS S-NPP', 0))}\n"
    f"Total regional: {len(base_fase3)}\n\n"
    "ESCENARIOS CALCULADOS\n"
    + (resumen_fase3.to_string(index=False) if not resumen_fase3.empty
       else "No disponibles")
    + "\n\nCONCLUSIÓN\n" + conclusion_fase3
    + "\n\nLIMITACIONES\n"
      "Recorte nacional rectangular aproximado, no frontera exacta.\n"
      "Correspondencias candidatas; no incendios confirmados.\n"
      "No existe validación independiente.\n"
)
st.download_button(
    "Descargar informe del estudio",
    data=informe_fase3.encode("utf-8-sig"),
    file_name="informe_modis_viirs_uruguay.txt",
    mime="text/plain"
)
st.caption("Prototipo exploratorio de investigación NASA Space Apps Challenge 2026.")
