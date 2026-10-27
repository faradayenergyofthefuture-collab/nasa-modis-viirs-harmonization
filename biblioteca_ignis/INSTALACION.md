# Integrar evidencia externa en IGNIS

Archivos incluidos:
- `ignis_validacion.py` → copiar en la raíz del repositorio, al lado de `streamlit_app.py` e `ignis_biblioteca.py`.
- `biblioteca_ignis/fuentes_externas.json` → copiar a la carpeta existente `biblioteca_ignis/`, sin reemplazar `casos.json`.

## 1. En `ignis_biblioteca.py`

Dentro de `mostrar_biblioteca`, localizar las líneas:

```python
    c = casos[elegido]
    st.write(c["conclusion"])
```

Inmediatamente después de `st.write(c["conclusion"])`, agregar:

```python
    from ignis_validacion import mostrar_evidencia_caso
    mostrar_evidencia_caso(c)
```

De esta forma se ven las fuentes revisadas incluso si el visitante NO cargó un ZIP.

## 2. En `streamlit_app.py`

**Al final del archivo** (fuera del argumento de `mostrar_biblioteca({...})`), agregar:

```python
from ignis_validacion import mostrar_validacion_zip
mostrar_validacion_zip(base_fase3)
```

De esta forma los usuarios que carguen ZIP o CSV pueden revisar cuántos registros caen dentro de las cajas de los casos documentados Y en los días que tienen un reporte histórico compatible.

**Este cruce es preliminar**: BBOX + día UTC; NO confirma que cada píxel sea fuego ni calcula una tasa de acierto. El archivo `casos.json` original permanece intacto. Los recortes espaciales de los casos no son polígonos de incendio.

## 3. Para subir a GitHub

Agregar los 2 archivos, realizar esas inserciones y hacer commit. Si Streamlit Cloud apunta a `streamlit_app.py`, se actualizará al desplegar el commit.

## 4. Para alcanzar validación rigurosa

Registrar fuentes con geolocalización más precisa (coordenadas de foco / polígono quemado), fecha/hora del evento local y UTC, nivel de incertidumbre, publicación, enlace original y evidencia del origen. Calcular distancia Haversine a polígonos y solapamiento temporal para cada observación (y analizar sensores por separado). Agregar episodios no detectados para estudiar falsos negativos; una muestra completa de eventos reales es necesaria para precisión/sensibilidad.

Fuentes: NASA FIRMS (https://firms.modaps.eosdis.nasa.gov/) y referencias históricas en `fuentes_externas.json`.
