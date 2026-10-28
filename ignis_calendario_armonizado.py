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
    st.subheader('Serie histórica disponible · por mes UTC')
    st.bar_chart(meses.set_index('Mes UTC')[['Celdas-día únicas']])
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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    font='Helvetica'
    fp=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if fp.exists():
        try: pdfmetrics.registerFont(TTFont('IGNISDejaVu',str(fp)));font='IGNISDejaVu'
        except Exception: pass
    ss=getSampleStyleSheet()
    ss.add(ParagraphStyle(name='IgnisTitleX',fontName=font,fontSize=16,leading=22,spaceAfter=12,textColor=colors.HexColor('#183650')))
    ss.add(ParagraphStyle(name='IgnisBodyX',fontName=font,fontSize=8.7,leading=13,spaceAfter=8))
    ss.add(ParagraphStyle(name='IgnisHeadX',fontName=font,fontSize=11,leading=16,spaceBefore=12,spaceAfter=7,textColor=colors.HexColor('#174D70')))
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=1.7*cm,leftMargin=1.7*cm,topMargin=1.7*cm,bottomMargin=1.6*cm)
    story=[]
    def p(t):story.append(Paragraph(str(t),ss['IgnisBodyX']))
    def h(t):story.append(Paragraph(str(t),ss['IgnisHeadX']))
    def tabla(rows,widths=None):
        t=Table([[Paragraph(str(v),ss['IgnisBodyX']) for v in r] for r in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCECF5')),('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#CBD5E1')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)]))
        story.append(t)
    story.append(Paragraph('IGNIS UY - Informe de integración MODIS-VIIRS',ss['IgnisTitleX']))
    p('NASA Space Apps Challenge 2026 | Informe reproducible de los datos cargados | Región: '+str(region))
    h('1. Objetivo y alcance')
    p('Integrar observaciones térmicas NASA FIRMS MODIS y VIIRS en una representación espacial y temporal común para examinar la actividad histórica disponible. No se clasifican incendios confirmados ni se estima probabilidad de incendio.')
    h('2. Datos y método')
    p(f'Los registros se agrupan por día UTC y celdas espaciales aproximadas de {celda_km:g} km, calculadas mediante una proyección equirectangular local. Cada celda-día se cuenta una vez en la unión MODIS-VIIRS. La coincidencia en una celda-día es más amplia que el criterio de pares 1 km/60 min de la biblioteca histórica y NO debe confundirse con él.')
    if not diario.empty:
        h('3. Calendario conjunto y períodos críticos observados')
        p(f"Registros originales: {int(diario['Registros originales'].sum())}. Celdas-día únicas: {int(diario['Celdas-día únicas'].sum())}. Celdas-día con ambas familias: {int(diario['Celdas con MODIS y VIIRS'].sum())}.")
        meses=resumen_periodos(diario)
        rows=[['Mes UTC','Celdas-día','Días con registros','Ambas familias']]
        for _,r in meses.iterrows():rows.append([r['Mes UTC'],int(r['Celdas-día únicas']),int(r['Días con detecciones']),int(r['Celdas con ambos sensores'])])
        tabla(rows,[3*cm,3.5*cm,4.5*cm,4.5*cm])
        pico=diario.loc[diario['Celdas-día únicas'].idxmax()]
        p(f"Máximo diario dentro de los archivos cargados: {pico['Fecha UTC']:%Y-%m-%d}, con {int(pico['Celdas-día únicas'])} celdas-día. Es un máximo observado, no una anomalía validada.")
        if diario['Fecha UTC'].dt.year.nunique()<2:p('No es posible evaluar anomalías interanuales ni tendencias históricas con los archivos de un solo año.')
    else:p('No se cargaron datos NASA FIRMS de la región; el calendario conjunto no pudo evaluarse.')
    h('4. Correspondencias históricas y contraste documental')
    if casos is not None and not casos.empty:
        p(f"La biblioteca incluye {len(casos)} expedientes y {int(casos['Pares candidatos (1 km, 60 min)'].sum())} pares candidatos al umbral de 1 km y 60 min. Estos resultados son de recortes históricos precalculados, no necesariamente del mismo rango que los ZIP actuales.")
        tabla([['Expediente','Pares','Estado documental']]+[[str(r['Región']),int(r['Pares candidatos (1 km, 60 min)']),str(r['Estado prensa'])] for _,r in casos.iterrows()],[6.5*cm,2*cm,7*cm])
    else:p('Biblioteca histórica no disponible para este informe.')
    h('5. Límites científicos')
    p('Los sensores tienen distinta resolución, cobertura y oportunidades de observación. La unión de celdas-día evita sumar duplicados dentro de la grilla, pero NO calibra las diferencias instrumentales ni permite comparar tasas de incendios entre años. Una detección térmica no equivale a un incendio; la ausencia de noticias tampoco demuestra ausencia de incendio. Los reportes periodísticos aportan contexto regional y temporal, no validación por píxel.')
    h('6. Matriz de verificación del objetivo')
    tabla([['Elemento','Estado verificable'],['Lectura MODIS y VIIRS','Implementada con archivos FIRMS cargados'],['Calendario común espacial-temporal','Implementado: unión de celdas-día'],['Patrones por mes y picos','Descriptivos para período disponible'],['Anomalías históricas interanuales','No verificadas sin serie plurianual comparable'],['Corrección por oportunidades de observación','No implementada'],['Trazabilidad y exportación','CSV del calendario y biblioteca de expedientes'],['Validación de incendios','No implementada a nivel de evento']],[7*cm,9*cm])
    h('7. Conclusión')
    p('IGNIS integra los registros disponibles en una representación común reproducible, conserva el contraste de correspondencias históricas y explicita sus límites. El producto es un prototipo exploratorio; no acredita una armonización radiométrica ni una calibración completa de cobertura orbital. Para un análisis histórico robusto se requiere ampliar los años y evaluar diferencias instrumentales y cobertura.')
    p('Fuente primaria: NASA FIRMS (MODIS y VIIRS). Fuente de contraste: biblioteca documental IGNIS UY. El informe se genera a partir de los datos y parámetros disponibles en la sesión.')
    def footer(c,d):c.setFont('Helvetica',8);c.drawRightString(A4[0]-1.7*cm,1.0*cm,f'IGNIS UY | Página {d.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
