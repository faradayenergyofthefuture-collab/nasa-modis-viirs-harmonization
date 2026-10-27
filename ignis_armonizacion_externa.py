"""IGNIS Fase 8: comparación exploratoria entre registros FIRMS y prensa.
No modifica ni calibra el motor de correspondencias MODIS–VIIRS.
"""
from __future__ import annotations
import pandas as pd
from ignis_evidencias import cargar_catalogo, preparar_datos, detecciones_caso


def construir_matriz(datos=None):
    catalogo = cargar_catalogo()
    df = preparar_datos(datos)
    filas = []
    for caso in catalogo['casos']:
        recorte = detecciones_caso(df, caso)
        fuentes = caso.get('fuentes', [])
        conteo = caso['esperados']
        esperado = sum(conteo.values())
        actual = None if recorte is None else len(recorte)
        por_sensor = {} if recorte is None or 'producto' not in recorte else recorte['producto'].value_counts().to_dict()
        filas.append({
            'Región': caso['nombre'],
            'Fechas FIRMS (UTC)': ', '.join(caso['fechas_utc']),
            'MODIS (guía)': conteo.get('MODIS', 0),
            'VIIRS S-NPP (guía)': conteo.get('VIIRS S-NPP', 0),
            'VIIRS NOAA-20 (guía)': conteo.get('VIIRS NOAA-20', 0),
            'Total (guía)': esperado,
            'Registros en ZIP': actual,
            'MODIS en ZIP': None if recorte is None else int(por_sensor.get('MODIS', 0)),
            'S-NPP en ZIP': None if recorte is None else int(por_sensor.get('VIIRS S-NPP', 0)),
            'NOAA-20 en ZIP': None if recorte is None else int(por_sensor.get('VIIRS NOAA-20', 0)),
            'Fuentes periodísticas': len(fuentes),
            'Clasificación documental': 'Con reporte regional/temporal' if fuentes else 'Sin reporte localizado en el catálogo',
            'Alcance': caso.get('etiqueta', ''),
            'Enlaces': ' | '.join(f['url'] for f in fuentes),
        })
    return pd.DataFrame(filas)


def mostrar_armonizacion_externa(datos=None):
    import streamlit as st
    st.header('Fase 8 · Armonización satélite–prensa')
    st.write('Comparación exploratoria de los seis expedientes NASA FIRMS con los reportes externos recopilados en la Fase 7.')
    st.info('Con reporte = noticia asociada a región y período, no confirmación de cada píxel. Sin reporte localizado = ausencia de fuente en el catálogo actual, no prueba de ausencia de incendio.')
    try:
        matriz = construir_matriz(datos)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f'No se pudo construir la matriz: {exc}')
        return
    con = int((matriz['Fuentes periodísticas'] > 0).sum())
    a, b, c = st.columns(3)
    a.metric('Expedientes', len(matriz))
    b.metric('Con reportes en catálogo', con)
    c.metric('Sin reporte localizado', len(matriz) - con)
    st.dataframe(matriz.drop(columns=['Enlaces']), use_container_width=True, hide_index=True)
    st.download_button('Descargar matriz Fase 8 (CSV)', matriz.to_csv(index=False).encode('utf-8-sig'), 'IGNIS_fase8_satellite_prensa.csv', 'text/csv', key='fase8_csv')
    st.subheader('Comparación descriptiva')
    graf = matriz[['Región', 'MODIS (guía)', 'VIIRS S-NPP (guía)', 'VIIRS NOAA-20 (guía)']].set_index('Región')
    st.bar_chart(graf)
    st.caption('Los recuentos corresponden a observaciones térmicas, no a incendios únicos. La distinta resolución y frecuencia de paso de los sensores impide interpretar sus recuentos como medidas directamente equivalentes.')
    st.subheader('Lectura científica')
    st.write('Esta fase permite identificar qué episodios tienen respaldo periodístico y comparar su actividad térmica. No estima sensibilidad, especificidad, tasa de falsos positivos ni probabilidades de incendio: para ello se necesitarían etiquetas independientes por evento y controles negativos verificados.')
    if datos is None:
        st.warning('Vista histórica: cargá los ZIP FIRMS en la portada para contrastar los registros originales con la guía.')
    elif matriz['Registros en ZIP'].notna().any():
        diferencias = matriz[matriz['Registros en ZIP'] != matriz['Total (guía)']]
        if not diferencias.empty:
            st.warning(f'{len(diferencias)} expediente(s) no reproducen el conteo de la guía con los archivos actuales. Revisá fechas, límites y archivos antes de sacar conclusiones.')
