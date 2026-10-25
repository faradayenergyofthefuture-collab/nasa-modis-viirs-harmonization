"""Fase 6 IGNIS. Biblioteca de casos revisados, independiente del motor científico."""
import io
import json
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

RUTA = Path(__file__).resolve().parent / "biblioteca_ignis" / "casos.json"
CAMPOS = ("id", "nombre", "departamento", "fecha_inicio_utc", "fecha_fin_utc", "modis", "viirs_noaa20", "viirs_snpp", "total", "pares_1km_60min", "lat_min", "lat_max", "lon_min", "lon_max", "conclusion")


def _leer_casos():
    if not RUTA.exists():
        return [], "No existe biblioteca_ignis/casos.json."
    try:
        casos = json.loads(RUTA.read_text(encoding="utf-8"))
        if not isinstance(casos, list) or len(casos) > 6:
            raise ValueError("Se espera una lista de hasta seis casos")
        ids = set()
        for caso in casos:
            if not isinstance(caso, dict) or any(c not in caso for c in CAMPOS):
                raise ValueError("Hay un caso incompleto")
            if str(caso["id"]) in ids:
                raise ValueError("Identificador duplicado")
            ids.add(str(caso["id"]))
            for c in ("modis", "viirs_noaa20", "viirs_snpp", "total"):
                if int(caso[c]) < 0:
                    raise ValueError("Conteo negativo")
            if sum(int(caso[c]) for c in ("modis", "viirs_noaa20", "viirs_snpp")) != int(caso["total"]):
                raise ValueError("Los conteos no suman el total")
        return casos, None
    except (OSError, ValueError, TypeError, KeyError) as e:
        return [], f"No se pudo leer la biblioteca: {e}"


def _texto(x):
    return escape(str(x if x is not None else "No disponible"))


def _pdf_historico(casos):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm,
                            title="IGNIS - Biblioteca histórica", author="Equipo IGNIS")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="IgnisTit", parent=styles["Title"], fontSize=20, leading=25, textColor=colors.HexColor("#183852"), spaceAfter=18))
    styles.add(ParagraphStyle(name="IgnisBody", parent=styles["BodyText"], fontSize=9, leading=14, spaceAfter=10))
    styles.add(ParagraphStyle(name="IgnisHead", parent=styles["Heading2"], textColor=colors.HexColor("#183852"), spaceBefore=13))
    story = [Paragraph("IGNIS | Biblioteca histórica", styles["IgnisTit"]),
             Paragraph("Informe comparativo de detecciones térmicas MODIS–VIIRS · Uruguay", styles["IgnisBody"]),
             Paragraph(f"Casos documentados: {len(casos)}", styles["IgnisBody"]),
             Paragraph("Resumen y alcance", styles["IgnisHead"]),
             Paragraph("Este informe reúne estudios guardados por el equipo. Los recuentos son registros de anomalías térmicas en los archivos y recortes de cada caso; no equivalen al número de incendios. Las coincidencias son pares candidatos y pueden ser muchos-a-muchos.", styles["IgnisBody"])]
    data = [["Caso", "MODIS", "NOAA-20", "S-NPP", "Total", "Pares*"]]
    for c in casos:
        data.append([Paragraph(_texto(c["nombre"]), styles["IgnisBody"]), str(c["modis"]), str(c["viirs_noaa20"]), str(c["viirs_snpp"]), str(c["total"]), _texto(c["pares_1km_60min"])])
    t = Table(data, colWidths=[6.2*cm, 1.7*cm, 2.1*cm, 1.7*cm, 1.7*cm, 2.3*cm], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0), colors.HexColor("#183852")), ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("VALIGN",(0,0),(-1,-1),"TOP"), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#edf3f8")]), ("GRID",(0,0),(-1,-1),.25,colors.lightgrey), ("FONTSIZE",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story += [t, Spacer(1,.25*cm), Paragraph("* Pares candidatos con tolerancias de 1 km y 60 minutos, si el análisis estuvo disponible. No deben sumarse como incendios.", styles["IgnisBody"])]
    for i,c in enumerate(casos, 1):
        story.append(Paragraph(f"{i}. {_texto(c['nombre'])}", styles["IgnisHead"]))
        story.append(Paragraph(f"Departamento: {_texto(c['departamento'])}. Período observado (UTC): {_texto(c['fecha_inicio_utc'])} a {_texto(c['fecha_fin_utc'])}.", styles["IgnisBody"]))
        story.append(Paragraph(f"Recorte rectangular: latitud {_texto(c['lat_min'])} a {_texto(c['lat_max'])}; longitud {_texto(c['lon_min'])} a {_texto(c['lon_max'])}.", styles["IgnisBody"]))
        story.append(Paragraph(f"Interpretación: {_texto(c['conclusion'])}", styles["IgnisBody"]))
    story += [Paragraph("Limitaciones y reproducibilidad", styles["IgnisHead"]), Paragraph("Los casos pueden abarcar períodos y áreas diferentes: sus conteos brutos no permiten comparar tasas de incendios ni rendimiento instrumental sin controlar cobertura y exposición. El recorte rectangular no equivale a una frontera departamental. La validación independiente requiere registros de campo u otras fuentes. Para reproducir cada estudio deben conservarse los CSV/ZIP originales, la versión del código y los parámetros utilizados.", styles["IgnisBody"]), Paragraph("Fuente de datos: NASA FIRMS, productos MODIS y VIIRS suministrados para cada estudio. Herramienta: IGNIS, proyecto NASA Space Apps Challenge 2026.", styles["IgnisBody"])]
    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.7*cm, 1.1*cm, "IGNIS · Biblioteca histórica")
        canvas.drawRightString(A4[0]-1.7*cm, 1.1*cm, f"Página {document.page}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def mostrar_biblioteca(contexto):
    st.divider()
    st.header("Fase 6 - Biblioteca histórica IGNIS")
    st.write("Estudios históricos revisados por el equipo. Se conservan en el repositorio, no en la sesión temporal de Streamlit.")
    st.subheader("Preparar ficha del análisis actual")
    try:
        df = contexto["base_fase3"]
        conteo = contexto["conteo"]
        tabla = contexto["resumen_fase3"]
        pares = None
        if not tabla.empty:
            fila = tabla.loc[(tabla["Distancia_km"] == 1.0) & (tabla["Tiempo_min"] == 60)]
            if not fila.empty:
                pares = int(fila.iloc[0]["Pares_candidatos"])
        ficha = {
            "id": "caso-pendiente", "nombre": str(contexto["nombre_caso"]).strip() or "Área seleccionada",
            "departamento": "Por verificar", "fecha_inicio_utc": str(contexto["fecha_min"]),
            "fecha_fin_utc": str(contexto["fecha_max"]),
            "modis": int(conteo.get("MODIS",0)), "viirs_noaa20": int(conteo.get("VIIRS NOAA-20",0)),
            "viirs_snpp": int(conteo.get("VIIRS S-NPP",0)), "total": int(len(df)),
            "pares_1km_60min": pares,
            "lat_min": float(contexto["lat_min"]), "lat_max": float(contexto["lat_max"]),
            "lon_min": float(contexto["lon_min"]), "lon_max": float(contexto["lon_max"]),
            "conclusion": str(contexto["conclusion_fase3"]),
        }
        st.download_button("📥 Descargar ficha JSON del análisis actual", json.dumps(ficha, ensure_ascii=False, indent=2).encode("utf-8"), file_name="ignis_ficha_para_revision.json", mime="application/json", key="ignis_f6_ficha")
        st.caption("La ficha no se guarda automáticamente. Revisá el nombre, departamento, fechas y límites; incorporala a casos.json mediante GitHub después de validarla.")
    except (KeyError, ValueError, TypeError) as e:
        st.warning(f"No se pudo preparar la ficha: {e}")
    st.subheader("Consultar casos publicados")
    casos, error = _leer_casos()
    if error:
        st.error(error)
        return
    if not casos:
        st.info("La biblioteca está preparada, pero todavía no hay estudios publicados. Primero debemos procesar y revisar los casos reales.")
        return
    st.metric("Estudios disponibles", f"{len(casos)} / 6")
    st.dataframe(pd.DataFrame([{"Caso":c["nombre"], "Departamento":c["departamento"], "MODIS":c["modis"], "VIIRS NOAA-20":c["viirs_noaa20"], "VIIRS S-NPP":c["viirs_snpp"], "Total":c["total"]} for c in casos]), use_container_width=True, hide_index=True)
    elegido = st.selectbox("Consultar expediente", options=range(len(casos)), format_func=lambda i: casos[i]["nombre"], key="ignis_f6_selector")
    c = casos[elegido]
    st.write(c["conclusion"])
    st.caption(f"Período observado (UTC): {c['fecha_inicio_utc']} a {c['fecha_fin_utc']}. Recorte rectangular: {c['lat_min']} a {c['lat_max']} lat.; {c['lon_min']} a {c['lon_max']} lon.")
    st.download_button("📄 Descargar informe histórico comparativo (PDF)", _pdf_historico(casos), file_name="IGNIS_biblioteca_historica.pdf", mime="application/pdf", key="ignis_f6_pdf")
    st.caption("Comparación descriptiva. Los conteos no están normalizados por cobertura satelital ni representan incendios confirmados.")
