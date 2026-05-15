# Catálogo de Fuentes de Datos — SaludMX Analytics Pipeline

> Generado desde investigación Deep Research DGIS/SSA. Actualizado: 2026-05-11.
> Referencia oficial: [SINAIS](http://www.dgis.salud.gob.mx)

---

## Mapa de Fuentes → Star Schema

```
SAEH (microdato/egreso)  ──────────────────────────→  fact_egresos_hospitalarios
       │
       ├── clues ─────────→  CLUES (catálogo)  ──────→  dim_clues
       │                           │
       │                       SINERHIAS  ────────────→  dim_clues (capacidad)
       │
       ├── diagnostico ───→  CIE-10 CEMECE  ──────────→  dim_cie10
       ├── sexo / edad  ────────────────────────────────→  dim_sexo / fact (deg.)
       ├── fecha_ingreso / egreso  ─────────────────────→  dim_fecha
       ├── entidad_id / municipio_id  ──────────────────→  dim_geografia
       └── tipo_ingreso / egreso / procedencia  ─────────→  dim_tipo_*
```

---

## Resumen ejecutivo de fuentes

| Fuente | URL | Formato | Encoding | Cobertura | Microdato | Prog. |
|--------|-----|---------|----------|-----------|-----------|-------|
| **SAEH** | [dgis.salud.gob.mx/...egresoshosp](http://www.dgis.salud.gob.mx/contenidos/basesdedatos/da_egresoshosp_gobmx.html) | ZIP→CSV/DBF | `latin-1` | 2004–2026 | ✅ | ✅ |
| **CLUES** | [dgis.salud.gob.mx/...clues](http://www.dgis.salud.gob.mx/contenidos/intercambio/clues_gobmx.html) | XLSX/CSV | `latin-1` | Diario | ✅ | ⚠️ |
| **SINERHIAS** | [dgis.salud.gob.mx/...sinerhias](http://www.dgis.salud.gob.mx/contenidos/sinais/s_sinerhias.html) | XLSX/CSV | `latin-1` | Anual (abril) | ✅ | ❌ |
| **CIE-10 CEMECE** | [dgis.salud.gob.mx/...diagnostico](http://www.dgis.salud.gob.mx/contenidos/intercambio/diagnostico_gobmx.html) | ZIP→XLSX | `latin-1` | 2024 | Ref. | ⚠️ |
| **COVID/SISVER** | [gob.mx/salud/...datos-abiertos-152127](https://www.gob.mx/salud/documentos/datos-abiertos-152127) | CSV | `UTF-8` | 2020–2026 | ✅ | ✅ |
| **SINAVE** | [sinave.gob.mx](https://www.sinave.gob.mx/) | CSV (mesa) | `latin-1` | 2010–2026 | ✅ | ❌ |

---

## Fuente 1 — SAEH (tabla de hechos principal)

### Especificaciones técnicas para Python

```python
pd.read_csv(
    path,
    encoding="latin-1",   # o "cp1252" si latin-1 falla
    dtype=str,             # TODO a string — tipos se limpian en transform
    low_memory=False,      # previene DtypeWarning en columnas mixtas
    sep=","                # delimitador; verificar con head() antes de asumir
)
```

### Columnas críticas para el modelo predictivo

| Columna en SAEH | Nombre alternativo | Tipo SSA | Mapeo DW | Notas |
|---|---|---|---|---|
| `CLUES` | `CVE_CLUES` | `str` | `clues_establecimiento_id` | Preservar mayúsculas, sin trim |
| `AFECPRIN` | `DIAG_PRI`, `CAUSA` | `str` | `diagnostico_principal_cie10` | **Nombre varía por año** — verificar layout |
| `FECEGR` | `FECHA_EGRESO` | `str` | `fecha_egreso_id` | Multiformato: DD/MM/YYYY, YYYYMMDD, int |
| `FECINGR` | `FECHA_INGRESO` | `str` | `fecha_ingreso_id` | Mismo riesgo |
| `SEXO` | — | `str` | `sexo_id` | 1=M, 2=F, 9=NE |
| `EDAD` | `EDADANOS` | `str` | `edad_anios` | Puede estar en años, meses o días |
| `TIPINGR` | `TIPO_INGR` | `str` | `tipo_ingreso_id` | 1=Programado, 2=Urgencias, 9=NE |
| `TIPALTA` | `TIPEGR` | `str` | `tipo_egreso_id` | 1=Curado, 2=Mejora, 3=Defunción, 4=Traslado |
| `DIAS_ESTAN` | `DIASEST` | `str` | `dias_estancia` | 0 = <24h, **no eliminar** → `estancia_corta=True` |
| `PROCED` | `PROCEDENCIA` | `str` | `procedencia_id` | Origen del paciente |
| `CVE_ENT` | `ENTIDAD` | `str` | `entidad_id` | zfill(2) |
| `CVE_MUN` | `MUNICIPIO` | `str` | `municipio_id` | zfill(3) |

> [!WARNING]
> Los **nombres de columnas cambian entre años**. El archivo `Descriptor` o `Layout` que acompaña cada ZIP es **obligatorio**. Siempre descargarlo junto con el archivo de datos.

### Nulos implícitos SSA — tabla canónica

| Patrón encontrado | Acción en pipeline |
|---|---|
| `'9'` en campos categoriales (sexo, tipo) | → `NULL` |
| `'99'` en campos numéricos | → `NULL` |
| `'NE'` | → `NULL` |
| `'  /  /    '` (fecha en blanco) | → `NULL` |
| Estancia `0` días | ⚠️ **Mantener** + flag `estancia_corta=True` |
| `''` (string vacío) | → `NULL` |

### Calidad de datos — riesgos documentados

| Riesgo | Impacto | Mitigación en pipeline |
|--------|---------|------------------------|
| Duplicados en carga por lotes (SESA) | Infla fact table | Dedup por `(fecha, edad, sexo, clues, diagnostico)` |
| IMSS/ISSSTE sin diagnósticos secundarios | Modelo incompleto | Columnas opcionales, no FK |
| Cambio de layout entre años | Crash en carga | Resolver columnas por `layout_<año>.xlsx` |
| DBF años 2000-2003 | `pd.read_csv` falla | Usar `dbfread` |
| Caída de calidad post-2019 (transición SINBA) | Registros <40% completos en algunos estados | Validar cobertura por entidad/año |

---

## Fuente 2 — CLUES (dim_clues)

### Especificaciones técnicas

```python
# Opción A: CSV
pd.read_csv(path, encoding="latin-1", dtype=str, low_memory=False)

# Opción B: Excel multihojas
pd.read_excel(path, sheet_name="CLUES", dtype=str, engine="openpyxl")
```

**Volumen:** ~35,000–40,000 establecimientos activos  
**Coordenadas:** Lat/Lon como strings — requieren `pd.to_numeric(..., errors='coerce')`  
**AppClues:** Servicios web de consulta individual (útil para actualizaciones puntuales)

---

## Fuente 3 — SINERHIAS (enriquece dim_clues)

**Acceso:** Solo manual desde el portal  
**Granularidad:** Nivel de establecimiento (CLUES) — join directo con SAEH  
**Variables clave:**
- `camas_censables` — generan los egresos hospitalarios
- `camas_no_censables` — urgencias, recuperación
- `quirofanos`, `consultorios_especialidad`
- Personal por categoría y tipo de plaza

---

## Fuente 4 — CIE-10 CEMECE (dim_cie10)

**Estructura:**
- `CODIGO` — clave primaria (ej. `A09X`, `J18.9`)
- `DESCRIPCION` — texto en español
- `GRUPO` — agrupación diagnóstica
- `CAPITULO` — capítulo CIE-10 (I–XXII)

**Nota:** CEMECE publica revisiones anuales — verificar si el código del SAEH usa la versión con o sin punto (ej. `J189` vs `J18.9`)

---

## Fuente 5 — COVID-19 / SISVER

> [!NOTE]
> Excepción al patrón de encoding: estos archivos son **UTF-8**.  
> Variables adicionales útiles: `INTUBADO`, `UCI`, comorbilidades binarias (diabetes, hipertensión, obesidad).

---

## Checklist de descarga para el PoC (año 2023)

```
data_raw/
├── saeh/
│   └── 2023/
│       ├── BASEDEDATOS2023.zip     ← microdatos (~100-150 MB)
│       ├── Descriptor2023.pdf/xlsx ← ⚠️ OBLIGATORIO para mapeo de columnas
│       └── Catalogos2023.zip       ← catálogos de valores (sexo, procedencia...)
├── clues/
│   └── CLUES_<fecha>.xlsx o .csv
├── cie10/
│   └── CIE10_CEMECE_2024.zip
└── sinerhias/
    └── SINERHIAS_2023.xlsx         ← descarga manual
```

---

## Acceso programático — estrategia recomendada

```python
import requests
from bs4 import BeautifulSoup
import re

BASE_URL = "http://www.dgis.salud.gob.mx/contenidos/basesdedatos/da_egresoshosp_gobmx.html"

resp = requests.get(BASE_URL, timeout=30)
soup = BeautifulSoup(resp.content, "lxml")

# Extraer todos los links de descarga .zip / .rar
links = [
    a["href"] for a in soup.find_all("a", href=True)
    if re.search(r"\.(zip|rar)$", a["href"], re.IGNORECASE)
]

# Filtrar por año con regex
year_links = {
    re.search(r"(20\d{2})", link).group(1): link
    for link in links
    if re.search(r"20\d{2}", link)
}
```

> [!CAUTION]
> Los permalinks de **datos.gob.mx** pueden cambiar con cada actualización. 
> Usar el portal SINAIS como fuente primaria y datos.gob.mx solo como descubrimiento.
