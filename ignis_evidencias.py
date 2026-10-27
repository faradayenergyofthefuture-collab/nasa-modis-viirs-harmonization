"""IGNIS - Fase 7: evidencia geográfica y periodística complementaria.

Módulo independiente; NO modifica el motor de armonización de MODIS/VIIRS.

Integración (streamlit_app.py):
  - Ruta sin ZIP: mostrar_evidencias() antes de st.stop().
  - Con ZIP: mostrar_evidencias(datos) luego de mostrar_biblioteca(...).

IMPORTANTE: coincidencia de fecha/recorte y una noticia NO validan píxeles
individuales. El catálogo solo ofrece fuentes contextuales auditables.
"""
from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

BASE = Path(__file__).resolve().parent
RUTA_CATALOGO = BASE / "biblioteca_ignis" / "evidencias.json"
HUSO_LOCAL = ZoneInfo("America/Montevideo")
COLUMNAS = {"latitude", "longitude", "fecha_hora_utc"}


def cargar_catalogo(ruta: Path = RUTA_CATALOGO) -> dict:
    """Lee solo el catálogo revisado; no usa búsqueda web automática."""
    ruta = Path(ruta)
    salida = json.loads(ruta.read_text(encoding="utf-8"))
    if len(salida.get("casos", [])) != 6:
        raise ValueError("Se esperan exactamente los seis casos de estudio")
    return salida


def preparar_datos(datos: pd.DataFrame | None) -> pd.DataFrame | None:
    """Normaliza para comparación. No se deducen fechas ni coordenadas ausentes."""
    if datos is None:
        return None
    if not isinstance(datos, pd.DataFrame) or not COLUMNAS.issubset(datos.columns):
        return None
    df = datos.copy()
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["_ignis_utc"] = pd.to_datetime(df["fecha_hora_utc"], errors="coerce", utc=True)
    df = df.dropna(subset=["latitude", "longitude", "_ignis_utc"]).copy()
    df["_ignis_fecha_utc"] = df["_ignis_utc"].dt.strftime("%Y-%m-%d")
    df["_ignis_fecha_local"] = df["_ignis_utc"].dt.tz_convert(HUSO_LOCAL).dt.strftime("%Y-%m-%d")
    df["_ignis_hora_local"] = df["_ignis_utc"].dt.tz_convert(HUSO_LOCAL).dt.strftime("%d/%m/%Y %H:%M")
    return df


def detecciones_caso(df: pd.DataFrame | None, caso: dict) -> pd.DataFrame | None:
    """Recorte geográfico + fechas UTC de la guía (no evento inferido)."""
    if df is None:
        return None
    lat_min, lat_max, lon_min, lon_max = caso["bbox"]
    mascara = (
        df["latitude"].between(lat_min, lat_max, inclusive="both")
        & df["longitude"].between(lon_min, lon_max, inclusive="both")
        & df["_ignis_fecha_utc"].isin(caso["fechas_utc"])
    )
    return df.loc[mascara].copy()


def resumir_casos(df: pd.DataFrame | None, catalogo: dict) -> list[dict]:
    """Cantidad de registros compatibles en archivos cargados, nunca % de precisión."""
    filas = []
    for caso in catalogo["casos"]:
        encontrados = detecciones_caso(df, caso)
        n_archivo = None if encontrados is None else len(encontrados)
        esperados = sum(caso["esperados"].values())
        filas.append({
            "id": caso["id"],
            "Caso": caso["nombre"],
            "Fechas guía (UTC)": ", ".join(caso["fechas_utc"]),
            "Conteo guía": esperados,
            "Registros ZIP en recorte/fecha": n_archivo,
            "Fuentes externas": len(caso["fuentes"]),
            "Estado documental": (
                "Coincidencia regional/temporal; sin validar cada píxel"
                if caso["fuentes"] else "Pendiente de corroboración externa"
            ),
        })
    return filas


def relacion_fuente(caso: dict, fuente: dict, df_caso: pd.DataFrame | None) -> tuple[str, int | None]:
    """Evalúa únicamente fechas locales; no infiere la huella del incendio."""
    if df_caso is None:
        return "Consulta bibliográfica (no se cargaron ZIP)", None
    f = df_caso["_ignis_fecha_local"]
    n = int(f.between(fuente["hecho_fecha_desde_local"], fuente["hecho_fecha_hasta_local"]).sum())
    if n:
        return "Coincidencia de fecha local y recorte (NO píxeles validados)", n
    return "Sin coincidencia temporal para esta fuente en los ZIP actuales", 0


def mostrar_evidencias(datos: pd.DataFrame | None = None) -> None:
    """Panel Streamlit. Instalable sin nuevas dependencias de requirements.txt."""
    import streamlit as st

    st.divider()
    st.header("Fase 7 · Evidencia externa y trazabilidad")
    st.write(
        "Contrastá los recortes de NASA FIRMS con fuentes oficiales, prensa histórica "
        "y la guía cartográfica del equipo. Cada enlace permite revisar qué se informó."
    )
    st.info(
        "Una noticia demuestra que se reportó un evento, no que cada punto de calor "
        "sea un incendio real. Las coincidencias se muestran por región y fecha."
    )

    try:
        catalogo = cargar_catalogo()
    except (OSError, ValueError, json.JSONDecodeError) as e:
        st.error(f"No se pudo leer biblioteca_ignis/evidencias.json: {e}")
        return

    datos_validos = preparar_datos(datos)
    if datos is not None and datos_validos is None:
        st.warning("Los ZIP aún no contienen columnas válidas de latitud, longitud y fecha/hora UTC.")

    filas = resumir_casos(datos_validos, catalogo)
    if datos_validos is not None:
        st.subheader("Cruce automático con los archivos cargados")
        st.dataframe(
            pd.DataFrame(filas).drop(columns="id"),
            use_container_width=True, hide_index=True
        )
        st.caption(
            "'Conteo guía' corresponde solo a los días seleccionados del PDF. "
            "Si difiere de los ZIP cargados, comprobá fechas, productos, duplicados "
            "y el mismo BBOX; no significa que los satélites sean incorrectos."
        )
        st.download_button(
            "Descargar matriz de trazabilidad (CSV)",
            data=pd.DataFrame(filas).to_csv(index=False).encode("utf-8-sig"),
            file_name="IGNIS_trazabilidad_ZIP_fuentes.csv", mime="text/csv",
            key="ignis_evidencias_csv"
        )
    else:
        st.caption("Podés explorar las fuentes de los seis expedientes sin cargar ZIP.")

    st.subheader("Evidencias por caso")
    casos = catalogo["casos"]
    opciones = [c["id"] for c in casos]
    seleccionado = st.selectbox(
        "Elegí un expediente", options=opciones,
        format_func=lambda ident: next(c["nombre"] for c in casos if c["id"] == ident),
        key="ignis_evidencias_selector",
    )
    caso = next(c for c in casos if c["id"] == seleccionado)
    recorte = detecciones_caso(datos_validos, caso)
    st.markdown(f"**{caso['nombre']} — {caso['etiqueta']}**")
    st.write(caso["resumen"])
    lat_min, lat_max, lon_min, lon_max = caso["bbox"]
    st.caption(
        f"Guía, página {caso['igm_pagina']} · Fechas UTC: {', '.join(caso['fechas_utc'])} · "
        f"BBOX: lat [{lat_min}, {lat_max}], lon [{lon_min}, {lon_max}]."
    )
    g = caso["esperados"]
    a,b,c = st.columns(3)
    a.metric("MODIS · guía",g["MODIS"])
    b.metric("VIIRS S-NPP · guía",g["VIIRS S-NPP"])
    c.metric("VIIRS NOAA-20 · guía",g["VIIRS NOAA-20"])
    if recorte is not None:
        n = len(recorte)
        st.write(f"**{n} registros** encontrados en el recorte y fecha UTC de la guía, según tus ZIP cargados.")
        if "producto" in recorte.columns and n:
            actual = recorte["producto"].value_counts()
            comparacion = pd.DataFrame([
                {"Producto": k, "Guía": v, "ZIP": int(actual.get(k, 0))}
                for k, v in g.items()
            ])
            st.dataframe(comparacion, hide_index=True, use_container_width=True)
        if n:
            st.dataframe(
                recorte[[k for k in ["producto", "latitude", "longitude", "_ignis_utc", "_ignis_hora_local"] if k in recorte]],
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("No aparecen registros para este expediente y sus fechas UTC en los ZIP actuales.")

    if caso["fuentes"]:
        for i, fuente in enumerate(caso["fuentes"],1):
            etiqueta, n = relacion_fuente(caso, fuente, recorte)
            with st.expander(f"Fuente {i} · {fuente['medio']} ({fuente['fecha_publicacion']})", expanded=(i == 1)):
                st.markdown(f"**{fuente['titulo']}**")
                st.write(f"Tipo: {fuente['tipo']} · Lugar: {fuente['lugar']}")
                st.caption(f"Fecha(s) del evento reportado, hora local: {fuente['hecho_fecha_desde_local']} a {fuente['hecho_fecha_hasta_local']}")
                st.write(f"**Alcance:** {fuente['alcance']}")
                st.write(f"**Observación:** {fuente['notas']}")
                st.write(f"**Comparación con datos cargados:** {etiqueta}" + (f" ({n} registros)" if n is not None else ""))
                st.link_button("Abrir fuente original", fuente["url"])
    else:
        st.warning("No hay una fuente histórica externa suficientemente localizada para este expediente. No se presume que no ocurrió un incendio.")

    st.subheader("Documento geográfico y metodología")
    doc = BASE / catalogo["referencia_cartografica"]["archivo"]
    if doc.is_file():
        st.download_button(
            "Descargar guía geográfica IGNIS–IGM (PDF)",
            data=doc.read_bytes(),
            file_name=doc.name,
            mime="application/pdf",
            key="ignis_evidencia_pdf_igm",
        )
    else:
        st.caption("Guía PDF opcional no incluida en el despliegue; podés agregarla en docs/.")
    st.caption(
        "Las capturas del IGM fueron recopiladas por el equipo: localizan centros de recorte "
        "pero no son certificaciones oficiales ni validación administrativa de cada punto."
    )
    st.link_button("Consultar notas metodológicas de NASA FIRMS", catalogo["fuente_nasa"])
    st.download_button(
        "Descargar catálogo completo de fuentes (JSON)",
        data=json.dumps(catalogo, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="IGNIS_evidencias_y_fuentes.json", mime="application/json",
        key="ignis_evidencias_json",
    )
