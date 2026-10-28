"""Calendario conjunto de celdas-dia observadas; no estima incendios ni corrige sobrepasos."""
from io import BytesIO
from datetime import date
import calendar
import numpy as np
import pandas as pd

PRODUCTOS = ['MODIS', 'VIIRS S-NPP', 'VIIRS NOAA-20']

def construir_calendario(datos, celda_km=1.0):
    requeridas = {'latitude','longitude','fecha_hora_utc','producto'}
    if datos is None or not requeridas.issubset(datos.columns):
        return pd.DataFrame(), pd.DataFrame()
    d = datos.copy()
    d['fecha_hora_utc'] = pd.to_datetime(d['fecha_hora_utc'], utc=True, errors='coerce')
    for c in ('latitude','longitude'):
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna(subset=['fecha_hora_utc','latitude','longitude','producto'])
    d = d[d['producto'].isin(PRODUCTOS)].copy()
    if d.empty:
        return pd.DataFrame(), pd.DataFrame()
    # Proyección equirectangular local para una grilla fija, válida como aproximación regional.
    lat0 = float(d['latitude'].median())
    d['celda_y'] = np.floor(d['latitude'] * 111.32 / celda_km).astype('int64')
    d['celda_x'] = np.floor(d['longitude'] * 111.32 * np.cos(np.deg2rad(lat0)) / celda_km).astype('int64')
    d['dia_utc'] = d['fecha_hora_utc'].dt.floor('D')
    # Una celda-día cuenta una vez en la unión aunque tenga varios sensores y sobrepasos.
    grupos = d.groupby(['dia_utc','celda_x','celda_y'])['producto'].agg(lambda s: frozenset(s)).reset_index()
    grupos['familias'] = grupos['producto'].map(lambda s: len({'MODIS' if x=='MODIS' else 'VIIRS' for x in s}))
    grupos['ambos'] = grupos['familias'].eq(2)
    filas = []
    for dia, g in grupos.groupby('dia_utc'):
        raw = d[d['dia_utc'].eq(dia)]
        filas.append({'Fecha UTC':dia, 'Registros originales':len(raw),
                     'Celdas-día únicas':len(g), 'Celdas con MODIS y VIIRS':int(g['ambos'].sum()),
                     'Celdas solo MODIS':int(g['producto'].map(lambda s:s==frozenset({'MODIS'})).sum()),
                     'Celdas solo VIIRS':int(g['producto'].map(lambda s: 'MODIS' not in s).sum()),
                     'MODIS registros':int(raw['producto'].eq('MODIS').sum()),
                     'VIIRS registros':int(raw['producto'].ne('MODIS').sum())})
    diario = pd.DataFrame(filas).sort_values('Fecha UTC').reset_index(drop=True)
    return diario, grupos

def resumen_periodos(diario):
    if diario.empty:
        return pd.DataFrame()
    d=diario.copy()
    d['Mes UTC']=d['Fecha UTC'].dt.strftime('%Y-%m')
    return d.groupby('Mes UTC',as_index=False).agg(
        **{'Celdas-día únicas':('Celdas-día únicas','sum'),
           'Días con detecciones':('Fecha UTC','nunique'),
           'Celdas con ambos sensores':('Celdas con MODIS y VIIRS','sum'),
           'Registros originales':('Registros originales','sum')})

def mostrar_calendario_armonizado(datos, clave='fase4'):
    import streamlit as st
    st.divider()
    st.subheader('Calendario conjunto MODIS–VIIRS · celdas-día')
    st.write('**Resultado central de integración:** ambos instrumentos se representan en una grilla espacial común y en días UTC. Cada celda se cuenta una sola vez por día, aunque contenga varias detecciones o registros de distintos satélites.')
    celda=st.selectbox('Tamaño aproximado de celda espacial', [1.0,2.0,5.0], index=0, format_func=lambda x:f'{x:g} km', key=f'{clave}_celda')
    diario, grupos=construir_calendario(datos,celda)
    if diario.empty:
        st.warning('No hay observaciones válidas para el calendario conjunto en la región seleccionada.')
        return diario, grupos
    a,b,c=st.columns(3)
    a.metric('Registros originales',int(diario['Registros originales'].sum()))
    b.metric('Celdas-día únicas',int(diario['Celdas-día únicas'].sum()))
    c.metric('Celdas-día con ambas familias',int(diario['Celdas con MODIS y VIIRS'].sum()))
    meses=resumen_periodos(diario)
    st.subheader('Actividad conjunta por día UTC')
    st.caption('Cada barra representa celdas-día distintas, no incendios. La categoría MODIS y VIIRS indica presencia de ambas familias en una misma celda y día; no exige simultaneidad dentro de 60 minutos.')
    grafico = diario[['Fecha UTC','Celdas con MODIS y VIIRS','Celdas solo MODIS','Celdas solo VIIRS']].copy()
    grafico['Fecha UTC'] = grafico['Fecha UTC'].dt.strftime('%d/%m/%Y')
    grafico = grafico.rename(columns={'Celdas con MODIS y VIIRS':'MODIS y VIIRS','Celdas solo MODIS':'Solo MODIS','Celdas solo VIIRS':'Solo VIIRS'})
    st.bar_chart(grafico.set_index('Fecha UTC'), stack=True, x_label='Fecha UTC', y_label='Celdas-día únicas')
    st.subheader('Resumen mensual de los datos disponibles')
    st.dataframe(meses,use_container_width=True,hide_index=True)
    st.subheader('Detalle diario conjunto')
    st.dataframe(diario.assign(**{'Fecha UTC':diario['Fecha UTC'].dt.strftime('%Y-%m-%d')}),use_container_width=True,hide_index=True)
    st.download_button('Descargar calendario armonizado diario (CSV)',diario.to_csv(index=False).encode('utf-8-sig'),f'IGNIS_calendario_conjunto_{celda:g}km.csv','text/csv',key=f'{clave}_csv')
    st.info('**Alcance:** se elimina la duplicación de conteo dentro de una misma celda y día, pero no se corrige por distinta resolución efectiva, nubes, frecuencia de paso ni cobertura de cada satélite. La grilla es aproximada; una celda-día no equivale a un incendio. Los días sin detección no son días verificados sin fuego.')
    if diario['Fecha UTC'].dt.year.nunique()<2:
        st.warning('Los archivos actuales no permiten estimar anomalías históricas interanuales ni tendencias de largo plazo: se necesita una serie de varios años con cobertura comparable. El pico del período cargado es descriptivo, no una anomalía estadísticamente validada.')
    else:
        st.caption('Comparar años exige además revisar cobertura y disponibilidad de sensores. No se interpreta una diferencia de recuentos como tendencia de incendios sin esa corrección.')
    return diario, grupos


def crear_informe_final_pdf(diario, casos, grupos, region, celda_km=1.0):
    """Informe académico reproducible basado en datos de sesión y biblioteca histórica."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    from xml.sax.saxutils import escape

    root=Path(__file__).resolve().parent
    font='Helvetica'; font_bold='Helvetica-Bold'
    for path in [Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]:
        if path.exists():
            name='IGNISRegular' if 'Bold' not in path.name else 'IGNISBold'
            try: pdfmetrics.registerFont(TTFont(name,str(path)))
            except Exception: pass
    if 'IGNISRegular' in pdfmetrics.getRegisteredFontNames(): font='IGNISRegular'
    if 'IGNISBold' in pdfmetrics.getRegisteredFontNames(): font_bold='IGNISBold'
    navy=colors.HexColor('#17344B'); blue=colors.HexColor('#245A79'); pale=colors.HexColor('#EDF4F7')
    ss=getSampleStyleSheet()
    ss.add(ParagraphStyle(name='IGTitle',fontName=font_bold,fontSize=17,leading=23,textColor=navy,spaceAfter=9))
    ss.add(ParagraphStyle(name='IGSub',fontName=font,fontSize=9,leading=14,textColor=blue,spaceAfter=14))
    ss.add(ParagraphStyle(name='IGHead',fontName=font_bold,fontSize=10.5,leading=15,textColor=navy,spaceBefore=13,spaceAfter=7,keepWithNext=True))
    ss.add(ParagraphStyle(name='IGBody',fontName=font,fontSize=8.6,leading=13,spaceAfter=8))
    ss.add(ParagraphStyle(name='IGSmall',fontName=font,fontSize=7.2,leading=10,spaceAfter=3))
    ss.add(ParagraphStyle(name='IGTableHead',fontName=font_bold,fontSize=7.2,leading=10,textColor=navy))
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=1.75*cm,leftMargin=1.75*cm,topMargin=1.8*cm,bottomMargin=1.8*cm,title='IGNIS UY | Informe técnico MODIS-VIIRS',author='Equipo IGNIS UY')
    width=A4[0]-3.5*cm
    story=[]
    def P(t,style='IGBody'):return Paragraph(escape(str(t)),ss[style])
    def p(t):story.append(P(t))
    def h(t):story.append(P(t,'IGHead'))
    def table(rows,weights,keep=False):
        widths=[width*x/sum(weights) for x in weights]
        data=[[P(v,'IGTableHead' if i==0 else 'IGSmall') for v in row] for i,row in enumerate(rows)]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT',splitByRow=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),pale),('LINEBELOW',(0,0),(-1,0),0.7,blue),('LINEBELOW',(0,1),(-1,-1),0.25,colors.HexColor('#D9E3EA')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6)]))
        story.append(KeepTogether([t]) if keep else t)
        story.append(Spacer(1,7))
    logo=root/'logo_ignis.png'
    if logo.is_file():
        from PIL import Image as PILImage
        try:
            with PILImage.open(logo) as im: iw,ih=im.size
            maxw,maxh=3.2*cm,2.8*cm
            ratio=min(maxw/iw,maxh/ih)
            story.append(Image(str(logo),width=iw*ratio,height=ih*ratio,hAlign='LEFT'))
            story.append(Spacer(1,10))
        except Exception: pass
    story.append(P('IGNIS UY | Integración exploratoria MODIS–VIIRS','IGTitle'))
    story.append(P('Informe técnico · NASA Space Apps Challenge 2026 · Prototipo de análisis satelital','IGSub'))
    table([['Ámbito de estudio','Configuración del análisis'],['Región',str(region)],['Unidad espacial',f'Celda aproximada de {celda_km:g} km'],['Unidad temporal','Día UTC'],['Fuentes','NASA FIRMS (MODIS, VIIRS S-NPP y VIIRS NOAA-20); biblioteca documental IGNIS UY']],[2.4,5.6],keep=True)
    h('Resumen')
    p('IGNIS UY integra registros de anomalías térmicas de NASA FIRMS en una grilla espacial y temporal común, y contrasta seis expedientes históricos con reportes periodísticos. Los resultados son exploratorios: ni los registros ni sus correspondencias constituyen incendios confirmados.')
    h('1. Objetivo y alcance')
    p('Construir un calendario conjunto MODIS–VIIRS para describir la actividad térmica observada, identificar coincidencias entre familias instrumentales y documentar las limitaciones de la interpretación. El prototipo no calcula probabilidades de incendio, tasas de falsos positivos ni tendencias interanuales validadas.')
    h('2. Datos y metodología')
    p(f'Los datos cargados se agrupan por fecha UTC y por celdas espaciales de tamaño aproximado {celda_km:g} km, utilizando una proyección equirectangular local. Una celda-día se contabiliza una vez aunque contenga varias observaciones. La coincidencia de MODIS y VIIRS en una celda-día no equivale a simultaneidad ni a identidad física del foco.')
    p('Por separado, la biblioteca histórica utiliza un emparejamiento de detecciones MODIS–VIIRS por distancia de hasta 1 km y diferencia temporal de hasta 60 minutos. El emparejamiento puede ser muchos-a-muchos; los pares no representan incendios únicos. Los recortes históricos no necesariamente coinciden con las fechas de los ZIP de la sesión.')
    h('3. Resultados del calendario conjunto')
    if diario is not None and not diario.empty:
        n=int(diario['Registros originales'].sum()); c=int(diario['Celdas-día únicas'].sum()); a=int(diario['Celdas con MODIS y VIIRS'].sum())
        p(f'Se procesaron {n} registros originales, agrupados en {c} celdas-día únicas; {a} celdas-día presentan observaciones de ambas familias.')
        meses=resumen_periodos(diario)
        table([['Mes UTC','Celdas-día','Días observados con registros','Ambas familias']]+[[r['Mes UTC'],str(int(r['Celdas-día únicas'])),str(int(r['Días con detecciones'])),str(int(r['Celdas con ambos sensores']))] for _,r in meses.iterrows()],[2,2,3.2,2.3])
        pico=diario.loc[diario['Celdas-día únicas'].idxmax()]
        p(f"El máximo diario dentro de los archivos cargados corresponde al {pico['Fecha UTC']:%d/%m/%Y}, con {int(pico['Celdas-día únicas'])} celdas-día. Es un máximo descriptivo, no una anomalía estadísticamente validada.")
        table([['Fecha UTC','Registros','Celdas-día','MODIS y VIIRS','Solo MODIS','Solo VIIRS']]+[[f"{r['Fecha UTC']:%d/%m/%Y}",str(int(r['Registros originales'])),str(int(r['Celdas-día únicas'])),str(int(r['Celdas con MODIS y VIIRS'])),str(int(r['Celdas solo MODIS'])),str(int(r['Celdas solo VIIRS']))] for _,r in diario.head(12).iterrows()],[2.3,1.4,1.6,2,1.6,1.6])
        if len(diario)>12:p('La tabla presenta los primeros doce días con registros. La serie completa está disponible mediante exportación CSV en la aplicación.')
    else:p('No hay registros válidos cargados para la región seleccionada.')
    h('4. Correspondencias históricas y evidencia documental')
    if casos is not None and not casos.empty:
        total=int(casos['Pares candidatos (1 km, 60 min)'].sum())
        p(f'En los {len(casos)} expedientes históricos se identifican {total} pares candidatos al criterio de 1 km y 60 minutos. El contraste periodístico aporta contexto regional y temporal, pero no valida cada píxel.')
        table([['Expediente','Pares candidatos','Estado documental']]+[[str(r['Región']),str(int(r['Pares candidatos (1 km, 60 min)'])),str(r['Estado prensa'])] for _,r in casos.iterrows()],[4.3,1.5,4.4],keep=True)
    else:p('No se dispone de la biblioteca histórica en esta ejecución.')
    h('5. Discusión y limitaciones')
    p('MODIS y VIIRS difieren en resolución efectiva, frecuencia de sobrepaso, condiciones de observación y cobertura. El conteo de celdas-día evita repetir una celda dentro del mismo día, pero no elimina todas las diferencias instrumentales ni corrige la cobertura orbital, las nubes o los cambios de oportunidad de observación.')
    p('Una detección térmica no equivale necesariamente a un incendio. La ausencia de una noticia localizada tampoco demuestra ausencia de fuego. No corresponde interpretar los porcentajes de emparejamiento como sensibilidad, precisión o probabilidad de incendio.')
    h('6. Matriz de verificación y tareas pendientes')
    table([['Componente','Estado'],['Lectura de datos MODIS y VIIRS','Implementada con archivos NASA FIRMS cargados'],['Calendario espacial-temporal común','Implementado mediante celdas-día'],['Máximos y períodos de actividad','Descriptivos del período disponible'],['Anomalías históricas interanuales','No verificadas sin una serie plurianual comparable'],['Corrección por oportunidades de observación','No implementada'],['Contraste documental','Contexto regional y temporal; no validación por píxel'],['Validación de incendios por evento','No implementada']],[4.4,5.6],keep=True)
    h('7. Conclusiones')
    p('IGNIS UY ofrece una integración exploratoria y reproducible de detecciones térmicas MODIS–VIIRS, complementada por correspondencias espaciotemporales históricas y evidencia periodística contextual. Para una validación científica de eventos y comparación instrumental robusta se requieren datos independientes georreferenciados, controles negativos y correcciones por cobertura y oportunidad de observación.')
    h('Fuentes y reproducibilidad')
    p('Fuente primaria: NASA Fire Information for Resource Management System (FIRMS), productos MODIS y VIIRS. Fuente complementaria: biblioteca histórica y catálogo de evidencias de IGNIS UY. Las cifras del calendario corresponden a la región y los archivos cargados al generar este informe; los pares históricos proceden de la biblioteca del proyecto.')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#D4E0E8'));canvas.line(1.75*cm,1.4*cm,A4[0]-1.75*cm,1.4*cm)
        canvas.setFont('Helvetica',8);canvas.setFillColor(blue)
        canvas.drawString(1.75*cm,1.08*cm,'IGNIS UY · Informe técnico')
        canvas.drawRightString(A4[0]-1.75*cm,1.08*cm,f'Página {doc.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
