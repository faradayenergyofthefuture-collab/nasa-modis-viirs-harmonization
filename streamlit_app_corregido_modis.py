
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

# Identidad visual IGNIS: portada únicamente
from pathlib import Path
logo_ignis = Path(__file__).resolve().parent / "logo_ignis.png"
if logo_ignis.exists():
    _, columna_logo, _ = st.columns([2, 1, 2])
    with columna_logo:
        st.image(str(logo_ignis), use_container_width=True)
    st.markdown('**IGNIS — Equipo del proyecto**')

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
    st.info("Podés consultar la biblioteca histórica sin cargar archivos NASA FIRMS.")
    from ignis_biblioteca import mostrar_biblioteca
    mostrar_biblioteca(None)
    st.stop()

def leer_archivo(archivo):
    if archivo.name.lower().endswith(".csv"):
        return [(pd.read_csv(archivo), archivo.name)]

    tablas = []
    with zipfile.ZipFile(BytesIO(archivo.getvalue())) as z:
        for nombre in z.namelist():
            if nombre.lower().endswith(".csv"):
                with z.open(nombre) as f:
                    tablas.append((pd.read_csv(f), nombre))
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
            for tabla, nombre_origen in leer_archivo(archivo):
                if not {"latitude", "longitude"}.issubset(tabla.columns):
                    st.warning(
                        f"{archivo.name}: faltan coordenadas."
                    )
                    continue

                # El nombre del CSV interno identifica el producto FIRMS.
                # Se prioriza sobre cualquier etiqueta previa para evitar
                # atribuir registros MODIS a VIIRS S-NPP.
                producto_detectado = identificar_producto(nombre_origen)
                if producto_detectado == "Sin identificar":
                    st.warning(f"{nombre_origen}: nombre no reconocido; se omite.")
                    continue
                tabla["producto"] = producto_detectado
                # Comprobación independiente con metadatos del sensor.
                if "instrument" in tabla.columns:
                    instrumento = tabla["instrument"].astype(str).str.upper().str.strip()
                    es_modis = instrumento.eq("MODIS")
                    if es_modis.any():
                        tabla.loc[es_modis, "producto"] = "MODIS"
                    if es_modis.any() and producto_detectado != "MODIS":
                        st.warning(f"{nombre_origen}: el nombre y el instrumento no coinciden; se priorizó MODIS.")
                st.caption(f"CSV leído: {nombre_origen} — {len(tabla)} registros — {tabla['producto'].value_counts().to_dict()}")

                if tabla["producto"].eq("Sin identificar").any():
                    st.warning(f"{nombre_origen}: producto no identificado; se omite para evitar mezclar sensores.")
                    continue
                tabla["archivo_origen"] = nombre_origen
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
    # Evita ejecutar las fases 2 y 3 sin datos cargados.
    st.stop()

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


# ============================================================
# FASE 4 - CALENDARIO DINAMICO DE ACTIVIDAD TERMICA
# Pegar al final de streamlit_app.py, despues de la Fase 3.
# ============================================================

import calendar
from datetime import date

st.divider()
st.header("Fase 4 - Calendario de actividad termica")
st.write(
    "Calendario de detecciones termicas NASA FIRMS dentro de la region "
    "seleccionada en la Fase 2B. Cada casilla muestra la cantidad de "
    "registros de ese dia (UTC)."
)
st.info(
    "Los colores representan cantidad de detecciones satelitales, "
    "no cantidad de incendios confirmados. Un dia sin registros "
    "no demuestra ausencia de incendios."
)

base_cal = region_filtrada.copy()
base_cal["fecha_hora_utc"] = pd.to_datetime(
    base_cal["fecha_hora_utc"], errors="coerce", utc=True
)
base_cal = base_cal.dropna(subset=["fecha_hora_utc", "producto"])

if base_cal.empty:
    st.warning("No hay detecciones con fecha valida en la region seleccionada.")
else:
    base_cal["dia_utc"] = base_cal["fecha_hora_utc"].dt.date
    base_cal["anio_cal"] = base_cal["fecha_hora_utc"].dt.year
    base_cal["mes_cal"] = base_cal["fecha_hora_utc"].dt.month

    anios_cal = sorted(base_cal["anio_cal"].unique().tolist())
    c_anio, c_mes = st.columns(2)
    with c_anio:
        anio_elegido = st.selectbox(
            "Anio", anios_cal, index=len(anios_cal) - 1,
            key="fase4_anio"
        )
    with c_mes:
        meses_presentes = sorted(
            base_cal.loc[base_cal["anio_cal"] == anio_elegido, "mes_cal"]
            .unique().tolist()
        )
        nombres_meses = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]
        mes_elegido = st.selectbox(
            "Mes", meses_presentes,
            format_func=lambda m: nombres_meses[m - 1],
            key="fase4_mes"
        )

    mes_cal = base_cal.loc[
        (base_cal["anio_cal"] == anio_elegido)
        & (base_cal["mes_cal"] == mes_elegido)
    ].copy()
    conteo_diario = mes_cal.groupby("dia_utc").size()
    max_diario = int(conteo_diario.max()) if not conteo_diario.empty else 0

    def color_calendario(n, maximo):
        if n == 0:
            return "#f1f5f9"
        fraccion = n / maximo if maximo else 0
        if fraccion <= 0.25:
            return "#fde68a"
        if fraccion <= 0.50:
            return "#fdba74"
        if fraccion <= 0.75:
            return "#fb923c"
        return "#ef4444"

    semanas_cal = calendar.monthcalendar(anio_elegido, mes_elegido)
    html_cal = (
        '<table style="width:100%;border-collapse:separate;'
        'border-spacing:4px;table-layout:fixed;text-align:center">'
        '<thead><tr>'
        + ''.join(
            f'<th style="padding:8px">{d}</th>'
            for d in ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        )
        + '</tr></thead><tbody>'
    )
    for semana in semanas_cal:
        html_cal += '<tr>'
        for numero_dia in semana:
            if numero_dia == 0:
                html_cal += '<td style="height:70px"></td>'
            else:
                fecha_celda = date(anio_elegido, mes_elegido, numero_dia)
                cantidad = int(conteo_diario.get(fecha_celda, 0))
                fondo = color_calendario(cantidad, max_diario)
                tinta = "#ffffff" if cantidad and cantidad / max_diario > 0.75 else "#172033"
                html_cal += (
                    f'<td style="background:{fondo};color:{tinta};'
                    'border-radius:8px;height:70px;padding:5px">'
                    f'<div style="font-weight:bold">{numero_dia}</div>'
                    f'<div style="font-size:12px">{cantidad} det.</div>'
                    '</td>'
                )
        html_cal += '</tr>'
    html_cal += '</tbody></table>'
    st.markdown(html_cal, unsafe_allow_html=True)
    st.caption(
        "Escala relativa al maximo diario del mes mostrado. "
        "Gris: 0; amarillo: baja; naranja: intermedia; rojo: maxima "
        "actividad registrada. Los dias en gris pueden carecer de cobertura "
        "satelital en los archivos cargados."
    )

    total_mes = len(mes_cal)
    dias_activos = int((conteo_diario > 0).sum())
    pico_dia = conteo_diario.idxmax()
    c_a, c_b, c_c = st.columns(3)
    c_a.metric("Detecciones del mes", total_mes)
    c_b.metric("Dias con detecciones", dias_activos)
    c_c.metric("Maximo diario", max_diario)
    st.caption(f"Dia de mayor registro: {pico_dia:%d/%m/%Y} (UTC).")

    st.subheader("Detalle de un dia")
    fechas_disponibles = sorted(conteo_diario.index.tolist())
    dia_elegido = st.selectbox(
        "Selecciona un dia con detecciones", fechas_disponibles,
        format_func=lambda d: d.strftime("%d/%m/%Y"),
        key="fase4_dia"
    )
    detalle_dia = mes_cal.loc[mes_cal["dia_utc"] == dia_elegido].copy()
    desglose_dia = (
        detalle_dia["producto"].value_counts()
        .rename_axis("Sensor").reset_index(name="Detecciones")
    )
    st.dataframe(desglose_dia, use_container_width=True, hide_index=True)
    st.caption(
        f"Region: {nombre_caso.strip() or 'Area seleccionada'}; "
        f"latitud {lat_min:.4f} a {lat_max:.4f}; "
        f"longitud {lon_min:.4f} a {lon_max:.4f}."
    )

    st.subheader("Evolucion diaria por sensor")
    resumen_cal = (
        mes_cal.groupby(["dia_utc", "producto"]).size()
        .unstack(fill_value=0)
    )
    # Completar los dias del mes con cero para una linea temporal continua.
    primer_dia = date(anio_elegido, mes_elegido, 1)
    ultimo_dia = date(
        anio_elegido, mes_elegido,
        calendar.monthrange(anio_elegido, mes_elegido)[1]
    )
    dias_mes = pd.date_range(primer_dia, ultimo_dia, freq="D")
    resumen_cal.index = pd.to_datetime(resumen_cal.index)
    resumen_cal = resumen_cal.reindex(dias_mes, fill_value=0)
    st.bar_chart(resumen_cal)

    exportar_cal = resumen_cal.copy()
    exportar_cal.index.name = "Fecha_UTC"
    exportar_cal["Total"] = exportar_cal.sum(axis=1)
    st.download_button(
        "Descargar calendario mensual CSV",
        data=exportar_cal.to_csv().encode("utf-8-sig"),
        file_name=f"calendario_modis_viirs_{anio_elegido}_{mes_elegido:02d}.csv",
        mime="text/csv",
        key="fase4_descarga"
    )
    st.caption(
        "Los recuentos corresponden solo a los datos NASA FIRMS cargados "
        "y a la region seleccionada. No se corrige por cobertura, "
        "sobrepasos satelitales ni duplicacion entre sensores."
    )


# ============================================================
# FASE 5 - INFORME CIENTIFICO PDF (IGNIS)
# Complemento independiente: no altera los calculos anteriores.
# ============================================================

st.divider()
st.header("Fase 5 - Informe científico en PDF")
st.write(
    "Generá un informe descargable con la metodología, los resultados "
    "del área seleccionada, la sensibilidad y el calendario mensual."
)


def construir_informe_pdf_ignis():
    from io import BytesIO as _BytesIO
    from xml.sax.saxutils import escape as _escape
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether, Image as RLImage
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.units import cm
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    buf = _BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        title="IGNIS - Informe MODIS-VIIRS", author="Equipo IGNIS"
    )
    azul = colors.HexColor("#17324f")
    gris = colors.HexColor("#566373")
    claro = colors.HexColor("#edf3f8")
    fuente = "Helvetica"
    fuente_bold = "Helvetica-Bold"
    # Fuente Unicode opcional: si no está, se usa Helvetica y texto normalizado.
    fuentes_posibles = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, negrita in fuentes_posibles:
        if Path(regular).exists() and Path(negrita).exists():
            pdfmetrics.registerFont(TTFont("IgnisSans", regular))
            pdfmetrics.registerFont(TTFont("IgnisSansBold", negrita))
            pdfmetrics.registerFontFamily("IgnisSans", normal="IgnisSans", bold="IgnisSansBold")
            fuente, fuente_bold = "IgnisSans", "IgnisSansBold"
            break

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="IgnisTitulo", fontName=fuente_bold,
        fontSize=20, leading=27, textColor=azul, alignment=TA_CENTER, spaceAfter=12))
    styles.add(ParagraphStyle(name="IgnisSubtitulo", fontName=fuente,
        fontSize=11, leading=16, textColor=gris, alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="IgnisSeccion", fontName=fuente_bold,
        fontSize=12, leading=16, textColor=azul, spaceBefore=13, spaceAfter=7))
    styles.add(ParagraphStyle(name="IgnisTexto", fontName=fuente,
        fontSize=9, leading=14, spaceAfter=7))
    styles.add(ParagraphStyle(name="IgnisCelda", fontName=fuente,
        fontSize=7.3, leading=10))
    styles.add(ParagraphStyle(name="IgnisCeldaBold", fontName=fuente_bold,
        fontSize=7.3, leading=10))
    styles.add(ParagraphStyle(name="IgnisNota", fontName=fuente,
        fontSize=8, leading=12, textColor=gris, spaceAfter=6))
    story = []

    def p(texto, estilo="IgnisTexto"):
        return Paragraph(_escape(str(texto)), styles[estilo])

    def seccion(titulo):
        story.append(p(titulo, "IgnisSeccion"))

    def tabla(columnas, filas, anchuras=None):
        celdas = [[p(v, "IgnisCeldaBold") for v in columnas]]
        celdas += [[p(v, "IgnisCelda") for v in fila] for fila in filas]
        t = Table(celdas, colWidths=anchuras, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), azul),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, claro]),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        # El fondo azul requiere texto blanco también en las celdas Paragraph.
        for c in celdas[0]:
            c.style = ParagraphStyle(name="CabeceraIgnis", parent=styles["IgnisCeldaBold"], textColor=colors.white)
        story.append(t)
        story.append(Spacer(1, .3*cm))

    logo_path = Path(__file__).resolve().parent / "logo_ignis.png"
    if logo_path.exists():
        try:
            logo = RLImage(str(logo_path))
            proporcion = float(logo.imageHeight) / max(float(logo.imageWidth), 1)
            logo.drawWidth = 5.0 * cm
            logo.drawHeight = 5.0 * cm * proporcion
            logo.hAlign = "CENTER"
            story.append(logo)
            story.append(Spacer(1, .45*cm))
        except Exception:
            pass

    story.append(p("IGNIS | Armonización MODIS–VIIRS", "IgnisTitulo"))
    story.append(p("Informe científico exploratorio · NASA Space Apps Challenge 2026", "IgnisSubtitulo"))
    story.append(p(f"Caso de estudio: {nombre_caso.strip() or 'Área seleccionada de Uruguay'}", "IgnisSubtitulo"))
    story.append(Spacer(1, .4*cm))

    seccion("1. Resumen del estudio")
    story.append(p(
        f"Se analizaron {len(base_fase3)} registros de anomalías térmicas de NASA FIRMS "
        f"en el área seleccionada. El período observado en los registros válidos "
        f"abarca del {fecha_min:%d/%m/%Y %H:%M} al {fecha_max:%d/%m/%Y %H:%M} (UTC). "
        "Las coincidencias MODIS–VIIRS son asociaciones candidatas, no incendios confirmados."
    ))
    seccion("2. Fuente de datos y área geográfica")
    story.append(p("Fuente: archivos CSV o ZIP NASA FIRMS aportados por quien utiliza la aplicación. "
        "Se realiza primero un recorte rectangular aproximado de Uruguay; "
        "el área de estudio se define mediante coordenadas geográficas."))
    tabla(["Parámetro", "Valor"], [
        ["Latitud mínima / máxima", f"{lat_min:.4f} / {lat_max:.4f}"],
        ["Longitud mínima / máxima", f"{lon_min:.4f} / {lon_max:.4f}"],
        ["Período observado (UTC)", f"{fecha_min:%d/%m/%Y %H:%M} a {fecha_max:%d/%m/%Y %H:%M}"],
        ["Registros en región", str(len(base_fase3))],
    ], [6*cm, 10.9*cm])
    seccion("3. Distribución por instrumento")
    tabla(["Producto satelital", "Detecciones"], [
        ["MODIS", str(int(conteo.get("MODIS", 0)))],
        ["VIIRS NOAA-20", str(int(conteo.get("VIIRS NOAA-20", 0)))],
        ["VIIRS S-NPP", str(int(conteo.get("VIIRS S-NPP", 0)))],
        ["Total regional", str(len(base_fase3))],
    ], [10*cm, 6.9*cm])

    seccion("4. Metodología de correspondencias")
    story.append(p(
        "Se comparan detecciones MODIS y VIIRS por distancia geodésica aproximada "
        "(fórmula de Haversine, radio terrestre de 6371,0088 km) y diferencia "
        "absoluta de tiempo de adquisición en UTC. Un par candidato cumple "
        "simultáneamente los umbrales espacial y temporal elegidos. "
        "Una detección puede participar en varios pares; no se exige correspondencia uno a uno."
    ))
    story.append(p(
        f"Parámetros interactivos de la Fase 2C: distancia ≤ {distancia_maxima:.1f} km "
        f"y diferencia temporal ≤ {tiempo_maximo} minutos. "
        f"Fase 2D: distancia ≤ {limite_km_2d:.1f} km "
        f"y diferencia temporal ≤ {limite_min_2d} minutos."
    ))
    if "resultados_2c" in globals():
        story.append(p(f"Pares candidatos en la Fase 2C: {len(resultados_2c)}."))
    if "tabla_pares_2d" in globals():
        story.append(p(
            f"Fase 2D: {len(tabla_pares_2d)} pares candidatos; "
            f"{modis_unicos} detecciones MODIS y {viirs_unicos} detecciones VIIRS "
            "participan en al menos un par."
        ))

    seccion("5. Análisis de sensibilidad")
    if not resumen_fase3.empty:
        filas = []
        for _, r in resumen_fase3.iterrows():
            filas.append([
                f"{float(r['Distancia_km']):g}", str(int(r["Tiempo_min"])),
                str(int(r["Pares_candidatos"])),
                str(int(r["MODIS_con"])), str(int(r["VIIRS_con"])),
                f"{float(r['Cobertura_MODIS_pct']):.2f}%",
                f"{float(r['Cobertura_VIIRS_pct']):.2f}%"
            ])
        tabla(["km", "min", "Pares", "MODIS con", "VIIRS con", "Cob. MODIS", "Cob. VIIRS"],
              filas, [1.4*cm, 1.4*cm, 2.0*cm, 2.7*cm, 2.7*cm, 3.35*cm, 3.35*cm])
        story.append(p(
            "Los nueve escenarios usan 0,5, 1 y 2 km combinados con 30, 60 y "
            "180 minutos. La cobertura indica proporción de detecciones con al menos "
            "un par candidato, no precisión ni sensibilidad diagnóstica.", "IgnisNota"
        ))
    else:
        story.append(p("No se pudo calcular sensibilidad: se requieren detecciones válidas de ambos sensores."))

    seccion("6. Calendario de actividad térmica")
    if "mes_cal" in globals() and "anio_elegido" in globals() and "mes_elegido" in globals():
        story.append(p(
            f"Mes seleccionado en la Fase 4: {mes_elegido:02d}/{anio_elegido}. "
            f"Detecciones registradas: {len(mes_cal)}. "
            f"Días con al menos una detección: {int((conteo_diario > 0).sum())}. "
            f"Máximo diario: {int(conteo_diario.max()) if not conteo_diario.empty else 0}."
        ))
        diarios = mes_cal.groupby(["dia_utc", "producto"]).size().unstack(fill_value=0)
        diarios["Total"] = diarios.sum(axis=1)
        filas = []
        for dia, r in diarios.iterrows():
            filas.append([
                dia.strftime("%d/%m/%Y"),
                str(int(r.get("MODIS", 0))),
                str(int(r.get("VIIRS NOAA-20", 0))),
                str(int(r.get("VIIRS S-NPP", 0))),
                str(int(r["Total"]))
            ])
        tabla(["Fecha UTC", "MODIS", "NOAA-20", "S-NPP", "Total"],
              filas, [4.1*cm, 2.7*cm, 3.4*cm, 3.4*cm, 3.3*cm])
    else:
        story.append(p("No hay calendario disponible para la región seleccionada."))
    story.append(p("Un día sin registros no demuestra ausencia de incendios; "
        "la cobertura satelital y la disponibilidad de archivos pueden variar.", "IgnisNota"))

    seccion("6A. Serie diaria completa del período analizado (UTC)")
    diario_completo = base_fase3.copy()
    diario_completo["_dia_utc"] = pd.to_datetime(diario_completo["fecha_hora_utc"], utc=True).dt.strftime("%Y-%m-%d")
    diario_completo = diario_completo.groupby(["_dia_utc", "producto"]).size().unstack(fill_value=0).sort_index()
    filas_diarias = []
    for fecha_dia, r in diario_completo.iterrows():
        m, n, v = (int(r.get(k, 0)) for k in ("MODIS", "VIIRS NOAA-20", "VIIRS S-NPP"))
        filas_diarias.append([fecha_dia, str(m), str(n), str(v), str(m+n+v)])
    if filas_diarias:
        tabla(["Día UTC", "MODIS", "NOAA-20", "S-NPP", "Total"], filas_diarias,
              [4.1*cm, 2.7*cm, 3.4*cm, 3.4*cm, 3.3*cm])
        story.append(p("La tabla contiene todos los días con detecciones en los archivos analizados, no solamente el mes elegido en pantalla. Los días omitidos no tienen registros en la muestra.", "IgnisNota"))
    else:
        story.append(p("No hay registros diarios válidos."))

    seccion("6B. Patrones temporales y períodos destacados")
    from ignis_biblioteca import analizar_actividad_diaria, _resumen_actividad
    datos_patrones = base_fase3.copy()
    datos_patrones["_dia_utc"] = pd.to_datetime(datos_patrones["fecha_hora_utc"], utc=True).dt.strftime("%Y-%m-%d")
    conteos_patrones = datos_patrones.groupby(["_dia_utc", "producto"]).size().unstack(fill_value=0)
    ficha_patrones = {"diario_utc": [
        {"fecha": str(dia), "modis": int(r.get("MODIS", 0)),
         "viirs_noaa20": int(r.get("VIIRS NOAA-20", 0)),
         "viirs_snpp": int(r.get("VIIRS S-NPP", 0))}
        for dia, r in conteos_patrones.iterrows()],
        "modis": int(conteo.get("MODIS", 0)),
        "viirs_noaa20": int(conteo.get("VIIRS NOAA-20", 0)),
        "viirs_snpp": int(conteo.get("VIIRS S-NPP", 0))}
    story.append(p(_resumen_actividad(ficha_patrones)))
    story.append(p("Estos indicadores describen registros de los archivos cargados, no intensidad de fuego ni incendios confirmados.", "IgnisNota"))

    seccion("6C. Trazabilidad de archivos y calidad de los datos")
    if "archivo_origen" in base_fase3.columns:
        fuentes = base_fase3.groupby(["archivo_origen", "producto"]).size().reset_index(name="n")
        tabla(["Archivo CSV original", "Producto", "Registros en región"],
              [[str(r["archivo_origen"]), str(r["producto"]), str(int(r["n"]))] for _,r in fuentes.iterrows()],
              [7.4*cm, 5.5*cm, 4.0*cm])
    story.append(p("Los valores de FRP, brillo, confianza y otras propiedades FIRMS dependen del producto y de las columnas disponibles; no se interpretan como equivalentes entre MODIS y VIIRS sin calibración.", "IgnisNota"))
    seccion("7. Conclusiones")
    story.append(p(conclusion_fase3))
    seccion("8. Limitaciones y alcance")
    for linea in [
        "El recorte nacional es rectangular y no representa la frontera administrativa exacta.",
        "Las anomalías térmicas no equivalen a incendios individuales confirmados.",
        "Los pares son candidatos y pueden incluir relaciones muchos-a-muchos.",
        "No se dispone de validación independiente para estimar precisión o falsos positivos.",
        "Las estadísticas dependen de los archivos cargados, los filtros y la cobertura satelital.",
    ]:
        story.append(p("• " + linea))
    seccion("9. Referencia de datos y herramienta")
    story.append(p("Datos: NASA FIRMS (Fire Information for Resource Management System), "
        "productos MODIS y VIIRS, según los archivos suministrados. "
        "Herramienta: IGNIS, prototipo exploratorio de armonización MODIS–VIIRS, "
        "NASA Space Apps Challenge 2026."))

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#ccd7e1"))
        canvas.line(1.8*cm, 1.35*cm, A4[0]-1.8*cm, 1.35*cm)
        canvas.setFont(fuente, 7)
        canvas.setFillColor(gris)
        canvas.drawString(1.8*cm, 1.0*cm, "IGNIS | Informe exploratorio MODIS–VIIRS")
        canvas.drawRightString(A4[0]-1.8*cm, 1.0*cm, f"Página {documento.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()


try:
    pdf_ignis = construir_informe_pdf_ignis()
    st.download_button(
        "📄 Descargar informe científico completo (PDF)",
        data=pdf_ignis,
        file_name="IGNIS_informe_MODIS_VIIRS.pdf",
        mime="application/pdf",
        key="ignis_pdf_fase5"
    )
    st.caption("El informe refleja los archivos, la región y los parámetros actuales de la aplicación.")
except Exception as error_pdf:
    st.error(f"No se pudo generar el PDF: {error_pdf}")
    st.info("Verificá que 'reportlab' esté incluido en requirements.txt.")


# ============================================================
# FASE 6 - BIBLIOTECA HISTÓRICA IGNIS
# ============================================================
from ignis_biblioteca import mostrar_biblioteca
mostrar_biblioteca({
    "base_fase3": base_fase3,
    "conteo": conteo,
    "resumen_fase3": resumen_fase3,
    "nombre_caso": nombre_caso,
    "fecha_min": fecha_min,
    "fecha_max": fecha_max,
    "lat_min": lat_min,
    "lat_max": lat_max,
    "lon_min": lon_min,
    "lon_max": lon_max,
    "conclusion_fase3": conclusion_fase3,
})
