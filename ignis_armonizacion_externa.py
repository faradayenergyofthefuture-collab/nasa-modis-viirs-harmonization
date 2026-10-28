"""IGNIS Fase 8: comparación exploratoria entre registros FIRMS y prensa.
No modifica ni calibra el motor de correspondencias MODIS–VIIRS.
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent / "biblioteca_ignis"
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



def construir_correspondencias_historicas():
    """Cruce por ID, no por nombres. Los escenarios proceden de la biblioteca ya calculada."""
    casos = json.loads((BASE / 'casos.json').read_text(encoding='utf-8'))
    evidencias = {c['id']: c for c in cargar_catalogo()['casos']}
    sensibilidad = pd.read_csv(BASE / 'sensibilidad_seis_casos.csv')
    validacion = pd.read_csv(BASE / 'validacion_seis_casos.csv')
    filas = []
    escenarios = []
    for c in casos:
        e = evidencias.get(c['id'])
        if e is None:
            raise ValueError(f"Falta evidencia/catalogación para {c['id']}")
        s = sensibilidad[sensibilidad['caso'] == c['nombre']].copy()
        v = validacion[validacion['caso'] == c['nombre']]
        if len(s) != 9 or len(v) != 1:
            raise ValueError(f"Escenarios/validación incompletos para {c['nombre']}")
        central = s[(s['distancia_km'] == 1.0) & (s['tiempo_min'] == 60)]
        if len(central) != 1:
            raise ValueError(f"No hay escenario central para {c['nombre']}")
        r = central.iloc[0]
        total_modis = int(c['modis'])
        total_viirs = int(c['viirs_noaa20']) + int(c['viirs_snpp'])
        pares = int(r['pares_candidatos'])
        if pares != int(c['pares_1km_60min']) or pares != int(v.iloc[0]['pares_recalculados']):
            raise ValueError(f"Inconsistencia en correspondencias: {c['nombre']}")
        fuentes = len(e.get('fuentes', []))
        filas.append({
            'ID': c['id'], 'Región': e['nombre'],
            'Estado prensa': 'Con reporte regional/temporal' if fuentes else 'Sin reporte localizado',
            'Fuentes': fuentes,
            'Detecciones históricas': int(c['total']),
            'Detecciones guía Fase 7': sum(e['esperados'].values()),
            'MODIS histórico': total_modis, 'VIIRS histórico': total_viirs,
            'Pares candidatos (1 km, 60 min)': pares,
            'MODIS con pareja': int(r['modis_con']),
            'VIIRS con pareja': int(r['viirs_con']),
            '% MODIS con pareja': round(100 * int(r['modis_con']) / total_modis, 1) if total_modis else None,
            '% VIIRS con pareja': round(100 * int(r['viirs_con']) / total_viirs, 1) if total_viirs else None,
            'Pares mínimo (9 escenarios)': int(s['pares_candidatos'].min()),
            'Pares máximo (9 escenarios)': int(s['pares_candidatos'].max()),
        })
        for _, escenario in s.iterrows():
            escenarios.append({
                'Región': e['nombre'], 'Estado prensa': filas[-1]['Estado prensa'],
                'Distancia (km)': float(escenario['distancia_km']),
                'Tiempo (min)': int(escenario['tiempo_min']),
                'Pares candidatos': int(escenario['pares_candidatos']),
                'MODIS con pareja': int(escenario['modis_con']),
                'VIIRS con pareja': int(escenario['viirs_con']),
                '% MODIS con pareja': round(100 * int(escenario['modis_con']) / total_modis, 1) if total_modis else None,
                '% VIIRS con pareja': round(100 * int(escenario['viirs_con']) / total_viirs, 1) if total_viirs else None,
            })
    return pd.DataFrame(filas), pd.DataFrame(escenarios)


def construir_contraste_documental():
    """Contraste descriptivo a nivel de expediente; no entrenamiento ni verdad-terreno."""
    resumen, _ = construir_correspondencias_historicas()
    d = resumen.copy()
    d['Grupo documental'] = d['Estado prensa'].map(
        lambda x: 'Con reporte en catálogo' if x.startswith('Con reporte') else 'Sin reporte localizado'
    )
    d['Pares por detección (descriptivo)'] = (
        d['Pares candidatos (1 km, 60 min)'] / d['Detecciones históricas']
    ).round(3)
    d['% MODIS con pareja'] = d['% MODIS con pareja'].astype(float)
    d['% VIIRS con pareja'] = d['% VIIRS con pareja'].astype(float)
    indicadores = ['% MODIS con pareja', '% VIIRS con pareja',
                   'Pares por detección (descriptivo)']
    grupos = d.groupby('Grupo documental', as_index=False).agg(
        casos=('ID', 'count'),
        **{col: (col, 'mean') for col in indicadores}
    )
    for col in indicadores:
        grupos[col] = grupos[col].round(2)
    return d, grupos


def mostrar_contraste_documental():
    import streamlit as st
    st.divider()
    st.subheader('Cruce interpretativo: patrones satelitales y prensa')
    st.write('**Aquí cruzamos efectivamente los indicadores de correspondencia MODIS–VIIRS con la evidencia documental.** La unidad de análisis es el expediente histórico completo, no un píxel ni un incendio individual.')
    casos, grupos = construir_contraste_documental()
    indicadores = ['Región', 'Grupo documental', 'MODIS histórico', 'VIIRS histórico',
                   '% MODIS con pareja', '% VIIRS con pareja',
                   'Pares candidatos (1 km, 60 min)', 'Pares por detección (descriptivo)']
    st.dataframe(casos[indicadores], use_container_width=True, hide_index=True)
    st.caption('Los porcentajes se calculan por familia de sensores: MODIS y VIIRS (NOAA-20 + S-NPP). “Pares por detección” es una densidad descriptiva que puede superar 1 porque el emparejamiento es muchos-a-muchos; NO es una probabilidad.')
    st.write('**Comparación de los dos grupos documentales (promedios por expediente, sin ponderar):**')
    st.dataframe(grupos, use_container_width=True, hide_index=True)
    st.caption('Se comparan pocos expedientes y las noticias tienen cobertura desigual. Estos promedios no permiten inferir precisión, sensibilidad, falsos positivos ni clasificar automáticamente incendios.')
    st.subheader('Lectura de cada caso')
    region = st.selectbox('Elegí una región para interpretar sus sensores y la prensa', casos['Región'].tolist(), key='fase8_lectura_region')
    r = casos.loc[casos['Región'] == region].iloc[0]
    st.write(f"**{region}:** {int(r['MODIS histórico'])} detecciones MODIS y {int(r['VIIRS histórico'])} VIIRS. "
             f"En el criterio de 1 km / 60 min, {r['% MODIS con pareja']:.1f}% de MODIS y "
             f"{r['% VIIRS con pareja']:.1f}% de VIIRS tienen al menos una pareja candidata. "
             f"Se obtuvieron {int(r['Pares candidatos (1 km, 60 min)'])} pares candidatos. "
             f"**Evidencia externa:** {r['Grupo documental'].lower()}.")
    if r['Grupo documental'] == 'Con reporte en catálogo':
        st.success('Interpretación documental: existe un incendio reportado en la región y período; las coincidencias satelitales son compatibles con actividad térmica, pero no verifican individualmente cada detección.')
    else:
        st.warning('Interpretación documental: no hay fuente coincidente incorporada en el catálogo actual. Es un caso sin corroboración localizada, NO un incendio descartado ni un falso positivo confirmado.')
    st.info('Conclusión operativa: IGNIS identifica coincidencias espacio-temporales entre MODIS y VIIRS y las contrasta con fuentes periodísticas. Con estos seis casos no es defendible declarar un sensor “más preciso” ni asignar un porcentaje de probabilidad de incendio. Para una clasificación automática validada faltan incendios y controles negativos georreferenciados independientemente.')
    st.download_button('Descargar contraste satélite–prensa (CSV)', casos[indicadores].to_csv(index=False).encode('utf-8-sig'), 'IGNIS_fase8_contraste_documental.csv', 'text/csv', key='fase8_contraste_csv')


def mostrar_correspondencias_historicas():
    import streamlit as st
    st.divider()
    st.subheader('Armonización exploratoria · correspondencias entre sensores')
    st.write('Se cruzan por identificador los seis expedientes de la biblioteca histórica (Fase 6) con el catálogo documental (Fase 7). Los pares MODIS–VIIRS se calcularon previamente usando distancia geográfica y diferencia temporal; **no son incendios únicos ni observaciones independientes**.')
    try:
        resumen, escenarios = construir_correspondencias_historicas()
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        st.error(f'No se pudieron cargar los resultados históricos: {exc}')
        return
    a, b, c = st.columns(3)
    a.metric('Casos históricos', len(resumen))
    b.metric('Pares candidatos (1 km / 60 min)', int(resumen['Pares candidatos (1 km, 60 min)'].sum()))
    c.metric('Escenarios examinados', len(escenarios))
    st.dataframe(resumen.drop(columns=['ID']), use_container_width=True, hide_index=True)
    st.download_button('Descargar armonización histórica (CSV)', resumen.to_csv(index=False).encode('utf-8-sig'), 'IGNIS_fase8_correspondencias_historicas.csv', 'text/csv', key='fase8_historica_csv')
    st.caption('“% con pareja” significa proporción de detecciones del sensor con al menos una correspondencia candidata. NO mide cobertura orbital, sensibilidad, precisión ni tasa de incendios. Un registro puede participar en varios pares.')
    st.subheader('Correspondencias según la evidencia periodística')
    graf = resumen[['Región', 'Pares candidatos (1 km, 60 min)']].set_index('Región')
    st.bar_chart(graf)
    st.write('La etiqueta documental permite comparar casos con reportes y sin fuentes localizadas; **no convierte a estos últimos en controles negativos confirmados**. Un número alto de pares tampoco demuestra por sí solo que hubo incendio.')
    st.subheader('Sensibilidad espacial y temporal · nueve escenarios por caso')
    nombres = resumen['Región'].tolist()
    elegido = st.selectbox('Seleccioná el expediente histórico', nombres, key='fase8_caso_sensibilidad')
    detalle = escenarios[escenarios['Región'] == elegido].copy()
    st.dataframe(detalle.drop(columns=['Región', 'Estado prensa']), use_container_width=True, hide_index=True)
    pivote = detalle.pivot(index='Distancia (km)', columns='Tiempo (min)', values='Pares candidatos')
    pivote.index.name = 'Distancia (km)'
    st.write('Pares candidatos según distancia (filas) y tiempo (columnas):')
    st.dataframe(pivote, use_container_width=True)
    st.download_button('Descargar 54 escenarios (CSV)', escenarios.to_csv(index=False).encode('utf-8-sig'), 'IGNIS_fase8_sensibilidad_54_escenarios.csv', 'text/csv', key='fase8_sensibilidad_csv')
    diferencias = resumen[resumen['Detecciones históricas'] != resumen['Detecciones guía Fase 7']]
    if not diferencias.empty:
        st.warning(f'{len(diferencias)} casos tienen un recorte histórico más amplio que la guía de fechas seleccionadas de Fase 7. Los pares y porcentajes se calculan SOLO con el expediente histórico; no se mezclan denominadores con la guía ni con los ZIP.')
    st.subheader('Interpretación y límites')
    st.write('**Resultado reproducible:** en los seis expedientes se registran ' + str(int(resumen['Pares candidatos (1 km, 60 min)'].sum())) + ' pares candidatos al criterio 1 km / 60 min, con variación según los nueve umbrales ensayados. Los casos con reportes aportan contexto externo de incendios en la región y período; no certifican cada píxel. La ausencia de una noticia en el catálogo no demuestra ausencia de incendio. Este análisis es una armonización exploratoria de coincidencias y trazabilidad, **no una calibración probabilística de detección**.')
    st.info('Próximo nivel de validación (fuera del alcance actual): perímetros o partes oficiales georreferenciados, controles negativos verificados y ajuste por oportunidad de observación de cada satélite.')

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
    mostrar_correspondencias_historicas()
    mostrar_contraste_documental()
    if datos is None:
        st.warning('Vista histórica: cargá los ZIP FIRMS en la portada para contrastar los registros originales con la guía.')
    elif matriz['Registros en ZIP'].notna().any():
        diferencias = matriz[matriz['Registros en ZIP'] != matriz['Total (guía)']]
        if not diferencias.empty:
            st.warning(f'{len(diferencias)} expediente(s) no reproducen el conteo de la guía con los archivos actuales. Revisá fechas, límites y archivos antes de sacar conclusiones.')

