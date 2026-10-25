"""Fase 6 IGNIS. Biblioteca de casos revisados, independiente del motor científico."""
import io
import json
import calendar
from datetime import datetime, date
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether

RUTA = Path(__file__).resolve().parent / "biblioteca_ignis" / "casos.json"
LOGO = Path(__file__).resolve().parent / "logo_ignis.png"
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
            if "diario_utc" in caso:
                if not isinstance(caso["diario_utc"], list):
                    raise ValueError("El calendario debe ser una lista")
                suma = 0
                fechas = set()
                for d in caso["diario_utc"]:
                    fecha = str(d["fecha"])
                    datetime.strptime(fecha, "%Y-%m-%d")
                    if fecha in fechas:
                        raise ValueError("Fecha duplicada en el calendario")
                    fechas.add(fecha)
                    vals = [int(d.get(k, 0)) for k in ("modis", "viirs_noaa20", "viirs_snpp")]
                    if min(vals) < 0:
                        raise ValueError("Conteo diario negativo")
                    suma += sum(vals)
                if suma != int(caso["total"]):
                    raise ValueError("La suma del calendario no coincide con el total")
        return casos, None
    except (OSError, ValueError, TypeError, KeyError) as e:
        return [], f"No se pudo leer la biblioteca: {e}"


def _texto(x):
    return escape(str(x if x is not None else "No disponible"))


def _tabla_calendario(caso, anio, mes, estilos):
    """Calendario UTC de conteos, no calendario de incendios confirmados."""
    dias = {d["fecha"]: d for d in caso.get("diario_utc", [])}
    cal = calendar.Calendar(firstweekday=0)
    matriz = [["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]]
    for semana in cal.monthdayscalendar(anio, mes):
        fila = []
        for dia in semana:
            if not dia:
                fila.append("")
                continue
            fecha = f"{anio:04d}-{mes:02d}-{dia:02d}"
            d = dias.get(fecha)
            n = sum(int(d.get(k,0)) for k in ("modis", "viirs_noaa20", "viirs_snpp")) if d else 0
            fila.append(Paragraph(f"<b>{dia}</b><br/><font size=8>{n} reg.</font>", estilos["IgnisBody"]))
        matriz.append(fila)
    tabla = Table(matriz, colWidths=[2.30*cm]*7, rowHeights=[0.55*cm]+[1.05*cm]*(len(matriz)-1), hAlign="LEFT")
    tabla.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183852")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("ALIGN",(0,0),(-1,0),"CENTER"),
        ("VALIGN",(0,1),(-1,-1),"TOP"),
        ("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#d4dfe9")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f4f8fb")]),
        ("LEFTPADDING",(0,1),(-1,-1),6),
        ("TOPPADDING",(0,1),(-1,-1),5),
    ]))
    return tabla


def _meses_del_caso(caso):
    """Muestra enero y febrero de 2023 si pertenecen al estudio; otros meses si corresponden."""
    # Incluir todos los meses entre primera y última detección, incluso sin registros.
    try:
        inicio = pd.to_datetime(caso["fecha_inicio_utc"], utc=True)
        fin = pd.to_datetime(caso["fecha_fin_utc"], utc=True)
        if pd.isna(inicio) or pd.isna(fin) or fin < inicio:
            return []
        periodos = pd.period_range(inicio.tz_localize(None).to_period("M"),
                                   fin.tz_localize(None).to_period("M"), freq="M")
        if len(periodos) > 24:
            return []
        return [(x.year, x.month) for x in periodos]
    except (KeyError, ValueError, TypeError):
        return []


def _pdf_historico(casos):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.6*cm, rightMargin=1.6*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm,
                            title="IGNIS - Informe comparativo de la biblioteca histórica", author="Equipo IGNIS")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="IgnisTit", parent=styles["Title"], fontSize=21, leading=26,
                              textColor=colors.HexColor("#183852"), spaceAfter=16))
    styles.add(ParagraphStyle(name="IgnisBody", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=8))
    styles.add(ParagraphStyle(name="IgnisHead", parent=styles["Heading2"], fontSize=13,
                              textColor=colors.HexColor("#183852"), spaceBefore=12, spaceAfter=9))
    story = []
    if LOGO.exists():
        from reportlab.lib.utils import ImageReader
        im = ImageReader(str(LOGO))
        w,h = im.getSize()
        logo = Image(str(LOGO), width=5.1*cm, height=5.1*cm*h/w)
        logo.hAlign="CENTER"
        story += [Spacer(1,0.7*cm),logo,Spacer(1,0.6*cm)]
    story += [Paragraph("IGNIS | Biblioteca histórica",styles["IgnisTit"]),
              Paragraph("Informe científico comparativo · MODIS y VIIRS · Uruguay",styles["IgnisBody"]),
              Paragraph(f"Casos revisados y publicados: {len(casos)}",styles["IgnisBody"]),
              Paragraph("Alcance del estudio",styles["IgnisHead"]),
              Paragraph("Se comparan detecciones de anomalías térmicas registradas en los archivos NASA FIRMS y en las regiones definidas para cada caso. Una detección no demuestra por sí sola un incendio. Los pares MODIS–VIIRS son asociaciones candidatas y pueden ser muchos-a-muchos.",styles["IgnisBody"]),
              Paragraph("Metodología",styles["IgnisHead"]),
              Paragraph("Se conservan los recuentos por producto MODIS, VIIRS NOAA-20 y VIIRS S-NPP, el período observado en UTC y el recorte rectangular. Los pares candidatos usan tolerancias espaciales de 1 km y temporales de 60 minutos. Los calendarios presentan registros por día UTC, no focos de incendio confirmados.",styles["IgnisBody"]),
              PageBreak(),Paragraph("Comparación de casos",styles["IgnisHead"])]
    data=[["Caso", "MODIS", "NOAA-20", "S-NPP", "Total", "Pares*"]]
    for c in casos:
        data.append([Paragraph(_texto(c["nombre"]),styles["IgnisBody"]),str(c["modis"]),str(c["viirs_noaa20"]),str(c["viirs_snpp"]),str(c["total"]),_texto(c["pares_1km_60min"])])
    t=Table(data,colWidths=[6.1*cm,1.7*cm,2.1*cm,1.7*cm,1.7*cm,2.3*cm],repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183852")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#edf3f8")]),
        ("GRID",(0,0),(-1,-1),.3,colors.lightgrey),("FONTSIZE",(0,0),(-1,-1),8),
        ("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story += [t,Spacer(1,.2*cm),Paragraph("* Pares candidatos, no incendios independientes. Los conteos no están normalizados por cobertura ni frecuencia de observación.",styles["IgnisBody"])]
    for i,c in enumerate(casos,1):
        story += [PageBreak(),Paragraph(f"Caso {i}: {_texto(c['nombre'])}",styles["IgnisHead"]),
          Paragraph(f"Departamento: {_texto(c['departamento'])}. Período de detecciones (UTC): {_texto(c['fecha_inicio_utc'])} a {_texto(c['fecha_fin_utc'])}.",styles["IgnisBody"]),
          Paragraph(f"Recorte rectangular: latitudes {_texto(c['lat_min'])} a {_texto(c['lat_max'])}; longitudes {_texto(c['lon_min'])} a {_texto(c['lon_max'])}.",styles["IgnisBody"]),
          Paragraph(f"MODIS: {int(c['modis'])}; VIIRS NOAA-20: {int(c['viirs_noaa20'])}; VIIRS S-NPP: {int(c['viirs_snpp'])}; total: {int(c['total'])}; pares candidatos: {_texto(c['pares_1km_60min'])}.",styles["IgnisBody"]),
          Paragraph("Calendario de detecciones térmicas (UTC)",styles["IgnisHead"])]
        meses = _meses_del_caso(c)
        if meses:
            for anio,mes in meses:
                story += [Paragraph(f"{calendar.month_name[mes]} {anio}",styles["IgnisBody"]),
                          _tabla_calendario(c,anio,mes,styles),Spacer(1,.35*cm)]
            story.append(Paragraph("Cada celda indica registros satelitales en el día. Cero registros no demuestra ausencia de incendios; depende de la cobertura y de los archivos disponibles.",styles["IgnisBody"]))
        else:
            story.append(Paragraph("Calendario no disponible: este expediente es anterior a la incorporación de conteos diarios. Volvé a generar la ficha con la versión actualizada.",styles["IgnisBody"]))
        story += [Paragraph("Interpretación",styles["IgnisHead"]),Paragraph(_texto(c["conclusion"]),styles["IgnisBody"])]
    story += [PageBreak(),Paragraph("Conclusiones generales y limitaciones",styles["IgnisHead"]),
      Paragraph("Los recuentos describen únicamente los archivos, períodos y recortes definidos para cada estudio. No deben interpretarse como número de incendios ni compararse como tasas de ocurrencia sin normalizar cobertura satelital, extensión territorial y tiempo de observación.",styles["IgnisBody"]),
      Paragraph("Los recortes son rectangulares y no representan necesariamente límites administrativos. Las asociaciones entre sensores no implican detecciones independientes. La confirmación de incendios requiere evidencia externa de campo o fuentes oficiales.",styles["IgnisBody"]),
      Paragraph("Reproducibilidad y fuentes",styles["IgnisHead"]),
      Paragraph("Datos de origen: NASA FIRMS, productos MODIS y VIIRS de los archivos aportados. Para reproducir resultados, conservar los CSV/ZIP originales, sus fechas, el recorte geográfico, los parámetros y la versión del código IGNIS. Los casos incluidos son únicamente los revisados y publicados en biblioteca_ignis/casos.json.",styles["IgnisBody"])]
    def footer(canvas,document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd8e3"))
        canvas.line(1.6*cm,1.35*cm,A4[0]-1.6*cm,1.35*cm)
        canvas.setFont("Helvetica",8)
        canvas.drawString(1.6*cm,1.0*cm,"IGNIS · Biblioteca histórica MODIS–VIIRS")
        canvas.drawRightString(A4[0]-1.6*cm,1.0*cm,f"Página {document.page}")
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()


def mostrar_biblioteca(contexto):
    st.divider()
    st.header("Fase 6 - Biblioteca histórica IGNIS")
    st.write("Estudios históricos revisados por el equipo. Se conservan en el repositorio, no en la sesión temporal de Streamlit.")
    if contexto is not None:
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
            departamento = st.text_input("Departamento del estudio (para la ficha)", value="Maldonado" if "maldonado" in str(contexto["nombre_caso"]).lower() else "", key="ignis_f6_departamento")
            if not departamento.strip():
                st.warning("Completá el departamento antes de publicar la ficha histórica.")
            if float(contexto["lon_max"]) - float(contexto["lon_min"]) > 0.4 or float(contexto["lat_max"]) - float(contexto["lat_min"]) > 0.4:
                st.warning("El recorte geográfico abarca más de 0,4° en al menos un eje. Revisá los límites de la Fase 2B si buscás un evento localizado.")
            fechas = df["fecha_hora_utc"].dt.strftime("%Y-%m-%d")
            diario = df.assign(_fecha=fechas).groupby(["_fecha", "producto"]).size().unstack(fill_value=0)
            diario_utc = [{"fecha": str(fecha), "modis": int(r.get("MODIS", 0)),
                           "viirs_noaa20": int(r.get("VIIRS NOAA-20", 0)),
                           "viirs_snpp": int(r.get("VIIRS S-NPP", 0))}
                          for fecha, r in diario.sort_index().iterrows()]
            ficha = {
                "id": "caso-pendiente", "nombre": str(contexto["nombre_caso"]).strip() or "Área seleccionada",
                "departamento": departamento.strip() or "Por verificar", "diario_utc": diario_utc,
                "fecha_inicio_utc": str(contexto["fecha_min"]),
                "fecha_fin_utc": str(contexto["fecha_max"]),
                "modis": int(conteo.get("MODIS",0)), "viirs_noaa20": int(conteo.get("VIIRS NOAA-20",0)),
                "viirs_snpp": int(conteo.get("VIIRS S-NPP",0)), "total": int(len(df)),
                "pares_1km_60min": pares,
                "lat_min": float(contexto["lat_min"]), "lat_max": float(contexto["lat_max"]),
                "lon_min": float(contexto["lon_min"]), "lon_max": float(contexto["lon_max"]),
                "conclusion": str(contexto["conclusion_fase3"]),
            }
            st.subheader("Calendario del análisis actual (UTC)")
            meses = _meses_del_caso(ficha)
            indice = {d["fecha"]: d for d in diario_utc}
            for anio, mes in meses:
                st.markdown(f"**{calendar.month_name[mes]} {anio}**")
                filas = []
                for dia in range(1, calendar.monthrange(anio, mes)[1] + 1):
                    fecha_dia = f"{anio:04d}-{mes:02d}-{dia:02d}"
                    d = indice.get(fecha_dia, {})
                    m = int(d.get("modis", 0))
                    n = int(d.get("viirs_noaa20", 0))
                    v = int(d.get("viirs_snpp", 0))
                    filas.append({"Fecha UTC": fecha_dia, "MODIS": m,
                                  "VIIRS NOAA-20": n, "VIIRS S-NPP": v,
                                  "Total": m + n + v})
                st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
            st.caption("Cero significa que no hay registros en los archivos analizados para ese día; no confirma ausencia de incendios.")
            st.download_button("📥 Descargar ficha JSON del análisis actual", json.dumps(ficha, ensure_ascii=False, indent=2).encode("utf-8"), file_name="ignis_ficha_para_revision.json", mime="application/json", key="ignis_f6_ficha")
            st.caption("La ficha no se guarda automáticamente. Revisá el nombre, departamento, fechas y límites; incorporala a casos.json mediante GitHub después de validarla.")
            st.subheader("Informe PDF del análisis actual")
            st.caption("Vista previa individual: incluye logo, metodología, recuentos y calendario. No publica automáticamente el caso.")
            if not departamento.strip():
                st.warning("Indicá el departamento para habilitar el PDF individual.")
            else:
                try:
                    pdf_actual = _pdf_historico([ficha])
                    st.download_button("📄 Descargar informe histórico individual (PDF)",
                        data=pdf_actual, file_name="IGNIS_informe_historico_individual.pdf",
                        mime="application/pdf", key="ignis_f6_pdf_actual")
                except Exception as error:
                    st.error(f"No se pudo preparar el PDF individual: {error}")
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
    if c.get("diario_utc"):
        st.subheader("Calendario diario del expediente (UTC)")
        st.dataframe(pd.DataFrame(c["diario_utc"]), use_container_width=True, hide_index=True)
    st.caption(f"Período observado (UTC): {c['fecha_inicio_utc']} a {c['fecha_fin_utc']}. Recorte rectangular: {c['lat_min']} a {c['lat_max']} lat.; {c['lon_min']} a {c['lon_max']} lon.")
    try:
        st.download_button("📄 Descargar informe histórico comparativo (PDF)", _pdf_historico(casos), file_name="IGNIS_biblioteca_historica.pdf", mime="application/pdf", key="ignis_f6_pdf")
    except Exception as error:
        st.error(f"No se pudo generar el PDF comparativo: {error}")
    st.caption("Comparación descriptiva. Los conteos no están normalizados por cobertura satelital ni representan incendios confirmados.")
