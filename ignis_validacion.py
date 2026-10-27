"""Panel de corroboración documental para IGNIS (no es certificación científica).

Compatible con biblioteca_ignis/casos.json y con base_fase3 de streamlit_app.py.
No realiza búsquedas web en tiempo de ejecución: solo utiliza fuentes revisadas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent
_CASOS = _ROOT / "biblioteca_ignis" / "casos.json"
_FUENTES = _ROOT / "biblioteca_ignis" / "fuentes_externas.json"


def _cargar(ruta: Path):
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
        if not isinstance(contenido, list):
            raise ValueError("La raíz del JSON debe ser una lista")
        return contenido
    except (OSError, ValueError, UnicodeError) as exc:
        st.warning(f"No se pudo abrir {ruta.name}: {exc}")
        return []


def _fuentes_por_id():
    return {str(x.get("caso_id")): x for x in _cargar(_FUENTES) if isinstance(x, dict)}


def mostrar_evidencia_caso(caso: dict):
    """Incluir dentro de ignis_biblioteca.py al mostrar el caso seleccionado."""
    cat = _fuentes_por_id().get(str(caso.get("id")))
    st.subheader("Evidencia externa del expediente")
    if not cat:
        st.info("Este caso todavía no tiene una ficha de evidencia externa revisada.")
        return

    st.write(f"**Estado documental:** {cat['estado']}")
    st.caption(cat.get("alcance", ""))
    a, b = st.columns(2)
    a.write("**Días con documentos compatibles (UTC):** " + ", ".join(cat.get("dias_con_evidencia_utc", [])) if cat.get("dias_con_evidencia_utc") else "**Días con documentos compatibles (UTC):** ninguno")
    b.write("**Días pendientes (UTC):** " + ", ".join(cat.get("dias_pendientes_utc", [])) if cat.get("dias_pendientes_utc") else "**Días pendientes (UTC):** ninguno en el catálogo")

    for item in cat.get("fuentes", []):
        with st.expander(f"{item['entidad']} · {item['fecha_publicacion']} · {item['titulo']}"):
            st.write(item.get("resumen", ""))
            st.caption("Tipo: " + item.get("tipo", "—") + " · Evento: " + item.get("fecha_evento", "—"))
            st.write("**Limitación:** " + item.get("limite", "No consta"))
            st.link_button("Abrir fuente original", item["url"])
    if not cat.get("fuentes"):
        st.info("No se inventan ni se sustituyen fuentes de otros años o departamentos.")
    st.caption("Esta sección verifica documentación contextual, NO la veracidad individual de los píxeles, el FRP ni los pares MODIS–VIIRS.")


def coincidir_registros_con_fuentes(registros: pd.DataFrame) -> pd.DataFrame:
    """Cuenta puntos en BBOX publicada y día UTC respaldado, sin inferir incendio.

    Cada conteo incluye solo las observaciones cargadas, nunca los registros históricos
    que no estén dentro del ZIP actual. No permite afirmar precisión o sensibilidad.
    """
    columnas = {"latitude", "longitude", "fecha_hora_utc"}
    if not isinstance(registros, pd.DataFrame) or not columnas.issubset(registros.columns):
        return pd.DataFrame()
    datos = registros.copy()
    datos["latitude"] = pd.to_numeric(datos["latitude"], errors="coerce")
    datos["longitude"] = pd.to_numeric(datos["longitude"], errors="coerce")
    datos["fecha_hora_utc"] = pd.to_datetime(datos["fecha_hora_utc"], errors="coerce", utc=True)
    datos = datos.dropna(subset=["latitude", "longitude", "fecha_hora_utc"])
    if datos.empty:
        return pd.DataFrame()
    fecha = datos["fecha_hora_utc"].dt.strftime("%Y-%m-%d")
    fuentes = _fuentes_por_id()
    filas = []
    for caso in _cargar(_CASOS):
        cat = fuentes.get(str(caso.get("id")))
        if not cat:
            continue
        dias = set(cat.get("dias_con_evidencia_utc", []))
        mascara_area = (
            datos["latitude"].between(float(caso["lat_min"]), float(caso["lat_max"])) &
            datos["longitude"].between(float(caso["lon_min"]), float(caso["lon_max"]))
        )
        n_area = int(mascara_area.sum())
        n_compatible = int((mascara_area & fecha.isin(dias)).sum()) if dias else 0
        if n_area:
            filas.append({
                "Caso": caso["nombre"],
                "Registros del ZIP en recorte": n_area,
                "Registros en días con noticia": n_compatible,
                "Días con noticia": ", ".join(sorted(dias)) if dias else "Ninguno",
                "Estado": cat["estado"],
            })
    return pd.DataFrame(filas)


def mostrar_validacion_zip(registros: pd.DataFrame):
    """Incluir al final de streamlit_app.py; recibe base_fase3 ya filtrada."""
    st.divider()
    st.header("Evidencia externa para los ZIP/CSV cargados")
    st.info(
        "Se cruza la posición y FECHA UTC de las detecciones cargadas con casos documentados "
        "del catálogo IGNIS. La coincidencia no certifica un incendio en cada píxel. "
        "Las noticias no sustituyen registros de Bomberos georreferenciados ni perímetros de área quemada."
    )
    tabla = coincidir_registros_con_fuentes(registros)
    if tabla.empty:
        st.warning("No hay coincidencias de recorte geográfico con los seis expedientes catalogados; esto NO implica ausencia de incendios.")
        return
    st.dataframe(tabla, use_container_width=True, hide_index=True)
    st.caption(
        "Importante: la fecha es la de adquisición del satélite en UTC. La prensa uruguaya "
        "suele indicar hora local UTC−3. Un conteo indica compatibilidad espacial por BBOX y día, "
        "no emparejamiento con el perímetro del incendio."
    )
    st.download_button(
        "Descargar cruce documental (CSV)",
        data=tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name="ignis_cruce_documental.csv",
        mime="text/csv",
        key="ignis_cruce_evidencia",
    )
