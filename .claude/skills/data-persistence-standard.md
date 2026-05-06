---
name: data-persistence-standard
description: Decisiones bloqueadas y patrones de persistencia para módulos Streamlit del Agency OS de Capybaras. Cubre estructura de paths, formato de archivos, schemas evolutivos, helpers de I/O y migration path local→cloud.
applies_to: cualquier módulo que necesite guardar/leer datos entre sesiones del usuario
version: v1
created: 2026-05-06
---

# Skill — Data Persistence Standard

Convenciones obligatorias para persistir datos en módulos del Agency OS. Aplican a TODO módulo que necesite recordar algo entre sesiones de Streamlit (snapshots semanales, logs de optimizaciones, eventos por SKU, historial de pricing, etc.).

Este skill es la fuente de verdad. Si un módulo se aparta de estas reglas, debe documentar explícitamente por qué en su CLAUDE.md de módulo.

---

## 🎯 Filosofía

Streamlit es stateless por diseño: `st.session_state` se borra al cerrar pestaña. Para que el Agency OS funcione como herramienta operativa real, los datos viven en disco bajo `data/` con un patrón único, predecible y portable.

Tres principios bloqueados:

1. **Mismo patrón para todos los módulos.** Si M27 Pricing y M28 SKU Progress guardan datos, lo hacen con la misma estructura de paths, los mismos helpers, las mismas convenciones de naming. Cero excepciones.
2. **Local-first hoy, cloud-ready mañana.** Toda I/O pasa por helpers (`_load_history`, `_save_snapshot`, `_append_log`). Migrar de Parquet local a SQLite local a Postgres cloud cambia la implementación de los helpers, no la lógica de negocio de los módulos.
3. **Lectura barata, escritura honesta.** Las lecturas se cachean con `@st.cache_data`. Las escrituras invalidan el cache explícitamente. Nadie adivina si un dato está fresco.

---

## 📁 Estructura de paths obligatoria

### Patrón canónico

````
data/<area>/<cliente>/<modulo>/<artefacto>.<extensión>
````

Donde:
- `<area>` = sección del sidebar en kebab-case: `account-health`, `ppc`, `supply-chain`, `disenio`, `rrhh`, `sales`, `marketplaces`, `direccion-general`
- `<cliente>` = slug del cliente en kebab-case: `gamboa`, `dermaglos`, `ltd`, `setex`, `mb`, `pura-vida-moringa`, `360essentials`
- `<modulo>` = slug del módulo en kebab-case: `pricing`, `sku-progress`, `flat-file-migrator`, `weekly-report`
- `<artefacto>` = identificador único del archivo (ver convenciones de naming abajo)
- `<extensión>` = `.parquet` (default), `.json` (configs/schemas), `.csv` (input raw del usuario antes de procesar)

### Ejemplos correctos

````
data/account-health/gamboa/pricing/2026-W18.parquet           ← snapshot semanal
data/account-health/gamboa/pricing/_history.parquet           ← agregador cross-week
data/account-health/gamboa/sku-progress/2026-W18.parquet      ← snapshot semanal
data/account-health/gamboa/sku-progress/optimizations.parquet ← log append-only
data/account-health/gamboa/sku-progress/events.parquet        ← log append-only
data/account-health/_examples/fba-inventory-sample.csv        ← data sintética para testing
data/_schemas/pricing-v1.json                                 ← schema de columnas
````

### Excepción — módulos client-agnostic

Si el módulo no es por cliente (ej. Flat File Migrator que opera sobre cualquier template Amazon), se omite el nivel cliente:

````
data/account-health/flat-file-migrator/aliases-v1.json        ← config global
data/account-health/flat-file-migrator/_examples/sample.txt
````

### Excepción — patrón histórico ya en uso

Estos paths existen desde antes de este skill y NO se renombran:
- `data/business_report/` → se mantiene como está. Cuando se construya un módulo Account Health que reuse estos archivos, lee desde ahí sin moverlos.
- `data/listing_snapshots/snapshots.json` → se mantiene como está hasta el próximo refactor de M15 Listing Monitor.

Cualquier path nuevo creado a partir de hoy debe seguir el patrón canónico.

---

## 📛 Convenciones de naming

### Archivos de snapshot (datos cambiantes en el tiempo)

Formato `YYYY-WW.parquet` o `YYYY-MM.parquet` o `YYYY-MM-DD.parquet` según frecuencia natural del dato:

| Frecuencia natural | Formato | Ejemplo |
|---|---|---|
| Semanal (pricing, SKU progress, weekly reports) | `YYYY-WW.parquet` | `2026-W18.parquet` |
| Mensual (product line, COGS) | `YYYY-MM.parquet` | `2026-04.parquet` |
| Diaria (BR diario, listing snapshots) | `YYYY-MM-DD.parquet` | `2026-05-06.parquet` |

`WW` es la semana ISO (1-53). Usar `pd.Timestamp.isocalendar().week` para obtenerla. NUNCA usar week of month ni numeración arbitraria.

### Archivos agregadores (queries cross-período)

Prefijo `_history.parquet` o `_aggregate.parquet`:

````
data/account-health/gamboa/pricing/_history.parquet
data/account-health/gamboa/sku-progress/_history.parquet
````

Contienen TODAS las semanas concatenadas con columna `_period` agregada. Permiten WoW queries en una sola lectura sin loop sobre N archivos.

### Archivos append-only (logs de eventos)

Sin sufijo de fecha, nombre semántico:

````
data/account-health/gamboa/sku-progress/optimizations.parquet  ← cada fila = 1 optimización aplicada
data/account-health/gamboa/sku-progress/events.parquet         ← cada fila = 1 evento (lanzamiento, restock, etc.)
data/account-health/gamboa/pricing/decisions-log.parquet       ← cada fila = 1 cambio de precio aplicado
````

### Archivos de configuración

Sufijo de versión obligatorio:

````
data/_schemas/pricing-v1.json
data/account-health/flat-file-migrator/aliases-v1.json
data/account-health/flat-file-migrator/subcat-fee-avg-v2.json
````

Versionar configs es la única forma de cambiarlas sin romper datos viejos.

### Reglas duras de naming

- ✅ `kebab-case` para todo (cliente, módulo, artefacto)
- ✅ ASCII only (sin tildes, ñ, espacios)
- ✅ Underscores `_` reservados como prefijo para archivos especiales: `_history`, `_schemas`, `_examples`, `_README`
- ❌ NUNCA `CamelCase`, `snake_case`, espacios, mayúsculas
- ❌ NUNCA fechas en formato `DD-MM-YYYY` o `DD/MM/YY` — siempre ISO 8601

---

## 💾 Formato de archivos — Parquet por default

### Por qué Parquet sobre CSV

| Atributo | Parquet | CSV |
|---|---|---|
| Tamaño en disco | ~5-10x más chico | Plano |
| Velocidad de lectura | ~10x más rápido | Lento con archivos grandes |
| Tipos de datos | Preservados (int, float, datetime, bool) | Todo string, hay que parsear |
| Schema | Embebido en el archivo | Implícito, frágil |
| Compresión | Snappy default, transparente | Manual con gzip |

Parquet es default para datos tabulares persistidos. CSV solo se permite para:
1. Inputs raw del usuario antes de procesar (ej: el FBA Inventory que sube en el `st.file_uploader`)
2. Archivos de ejemplo en `_examples/` para hacer demos legibles

### Cómo escribir Parquet

```python
import pandas as pd
from pathlib import Path

def _save_snapshot(df: pd.DataFrame, area: str, cliente: str, modulo: str, period: str) -> Path:
    """Guarda un snapshot semanal/mensual en disco. Crea carpetas si no existen.

    Args:
        df: DataFrame a guardar.
        area: 'account-health', 'ppc', etc.
        cliente: slug del cliente.
        modulo: slug del módulo.
        period: '2026-W18', '2026-04', etc.

    Returns:
        Path al archivo guardado.
    """
    base = Path("data") / area / cliente / modulo
    base.mkdir(parents=True, exist_ok=True)
    out = base / f"{period}.parquet"
    df.to_parquet(out, compression="snappy", index=False)
    return out
```

### Cómo leer Parquet con cache

```python
@st.cache_data(show_spinner=False)
def _load_snapshot(area: str, cliente: str, modulo: str, period: str) -> pd.DataFrame | None:
    """Lee un snapshot. Devuelve None si no existe."""
    p = Path("data") / area / cliente / modulo / f"{period}.parquet"
    if not p.exists():
        return None
    return pd.read_parquet(p)
```

### Cuándo invalidar cache

Después de toda escritura, invalidar manualmente:

```python
_save_snapshot(df, "account-health", "gamboa", "pricing", "2026-W18")
_load_snapshot.clear()  # invalida TODO el cache de la función
```

⚠️ `st.cache_data.clear()` (sin función específica) invalida el cache global y rompe performance de todos los módulos. Solo `<funcion_cacheada>.clear()`.

---

## 🧬 Schema evolutivo

### El problema

La semana 18 guardás un Parquet con columnas `[sku, price, score]`. La semana 19 agregás columna `margin_net`. Cuando intentás leer la semana 18 desde un módulo que espera `margin_net`, falla.

### La solución — schemas versionados en JSON

Cada módulo que persiste datos tiene un archivo schema en `data/_schemas/<modulo>-v<N>.json`:

```json
{
  "module": "pricing",
  "version": 1,
  "created": "2026-05-06",
  "columns": {
    "sku": {"dtype": "string", "required": true, "description": "Identificador SKU"},
    "price": {"dtype": "float64", "required": true, "description": "Precio sugerido en USD"},
    "score": {"dtype": "int64", "required": true, "description": "Score -100 a +100"},
    "margin_net": {"dtype": "float64", "required": false, "description": "Margen neto, agregado en v2"}
  },
  "primary_key": ["sku"],
  "period_column": "_period"
}
```

### Reglas de evolución

- **Agregar columna nueva opcional** → bump versión del schema, columna `required: false`. Datos viejos leen con `NaN` en esa columna.
- **Agregar columna nueva obligatoria** → backfill de datos viejos antes de bump. Sin backfill, los datos viejos no son válidos para la nueva versión.
- **Renombrar columna** → bump versión + función de migration que renombra al leer. Nunca borrar la columna vieja del archivo viejo.
- **Borrar columna** → no se borra. Se marca `deprecated: true` en el schema y se ignora en lectura.
- **Cambiar tipo de columna** → es schema break. Se trata como módulo nuevo (`pricing-v2`), no como evolución.

### Helper de validación

```python
def _validate_against_schema(df: pd.DataFrame, modulo: str, version: int) -> list[str]:
    """Devuelve lista de errores. Vacía si todo OK."""
    schema = json.loads(Path(f"data/_schemas/{modulo}-v{version}.json").read_text())
    errors = []
    for col, spec in schema["columns"].items():
        if spec["required"] and col not in df.columns:
            errors.append(f"Falta columna obligatoria: {col}")
        if col in df.columns and not _matches_dtype(df[col], spec["dtype"]):
            errors.append(f"Tipo incorrecto en {col}: esperado {spec['dtype']}")
    return errors
```

---

## 📜 Patrón append-only para logs

### Cuándo usar append-only

Logs donde cada fila es un evento histórico inmutable:
- Optimizaciones aplicadas a un SKU (cambio de imagen, título, A+)
- Eventos de marca (lanzamiento, restock, BSR badge confirmado)
- Decisiones de pricing aplicadas (qué precio, qué fecha, qué SKU)
- Bulk uploads ejecutados (qué batch, cuántas filas, qué resultado)

Estos logs NUNCA se reemplazan ni se editan. Se agrega. Si un evento fue mal cargado, se agrega un evento de corrección, no se borra el original.

### Helper de append

```python
def _append_log(row: dict, area: str, cliente: str, modulo: str, log_name: str) -> Path:
    """Agrega 1 fila a un log append-only. Crea el archivo si no existe.

    Args:
        row: dict con la fila a agregar. Debe incluir 'timestamp' (ISO 8601).
        log_name: nombre del log sin extensión (ej: 'optimizations', 'events').

    Returns:
        Path al archivo del log.
    """
    base = Path("data") / area / cliente / modulo
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / f"{log_name}.parquet"

    if "timestamp" not in row:
        row["timestamp"] = pd.Timestamp.now().isoformat()

    new_row_df = pd.DataFrame([row])

    if log_path.exists():
        existing = pd.read_parquet(log_path)
        combined = pd.concat([existing, new_row_df], ignore_index=True)
    else:
        combined = new_row_df

    combined.to_parquet(log_path, compression="snappy", index=False)
    return log_path
```

### Helper de lectura con filtros

```python
@st.cache_data(show_spinner=False)
def _load_log(area: str, cliente: str, modulo: str, log_name: str,
              filters: dict | None = None) -> pd.DataFrame:
    """Lee un log y opcionalmente filtra por columnas.

    Ejemplo: _load_log('account-health', 'gamboa', 'sku-progress', 'optimizations',
                      filters={'sku': 'demarpa0001s56'})
    """
    p = Path("data") / area / cliente / modulo / f"{log_name}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if filters:
        for col, val in filters.items():
            df = df[df[col] == val]
    return df
```

---

## 🚫 Versionado en git

### Lo que NO se versiona

Todo lo que sea data del cliente. Va en `.gitignore`:

```gitignore
# Datos operativos privados (cliente-sensible)
data/account-health/*/
data/ppc/*/
data/supply-chain/*/
# ... un patrón por sección

# Excepciones: estructura del directorio sí
!data/account-health/_examples/
!data/account-health/_README.md
```

### Lo que SÍ se versiona

- `data/_schemas/*.json` — los schemas
- `data/_README.md` — instrucciones del directorio
- `data/<area>/_examples/*.csv` — datos sintéticos para testing
- `data/<area>/_README.md` — instrucciones por sección
- Configs de módulo agnósticas: `data/account-health/flat-file-migrator/aliases-v1.json`

### Por qué no versionar datos

1. Privacidad: ventas, costos y márgenes reales del cliente no van a un repo.
2. Tamaño: los Parquet crecen semanalmente. A 6 meses, repo bloated.
3. Sync con Claude.ai: el proyecto Claude.ai sincroniza el repo. Datos versionados terminan en el contexto de chat.
4. Migration path: cuando pasemos a SQLite/Postgres, igual no se versiona. Decisión consistente con el futuro.

---

## 🛣️ Migration path — local hoy, cloud después

Toda lectura/escritura va por los helpers de este skill (`_save_snapshot`, `_load_snapshot`, `_append_log`, `_load_log`). Eso permite que el código de los módulos no cambie cuando migramos.

### Fase 1 — local Parquet (estado actual)

- Storage: archivos Parquet en `data/`
- Sync: ninguno, single-user
- Backup: manual a Drive cada viernes

### Fase 2 — local SQLite (cuando aparezca un 2do usuario)

- Storage: `data/agencyos.db` con tablas equivalentes a los Parquet
- Sync: vía Drive o git LFS
- Migration: rewriteo de los 4 helpers para usar `sqlalchemy`. La signature no cambia. Los módulos no se tocan.

### Fase 3 — Postgres cloud (Supabase/Neon/Render)

- Storage: DB remota
- Sync: real-time, multi-usuario nativo
- Migration: rewriteo de los 4 helpers para usar `sqlalchemy` con connection string. Mismas signatures. Módulos no se tocan.

### Disparadores de migración

| Disparador | Migrar a |
|---|---|
| Marcos sigue siendo el único usuario operando | Quedarse en Fase 1 |
| Aparece 2do usuario operando en paralelo desde otra máquina | Fase 2 |
| Equipo 3+ personas o requerimiento de dashboards live al cliente | Fase 3 |
| Volumen > 500 MB en `data/` | Considerar Fase 2 antes |
| Necesidad de queries WoW cross-cliente complejas | Considerar Fase 3 directo |

---

## 🧰 Helpers obligatorios — `core/persistence.py`

Todo módulo que persiste datos importa de un único archivo `core/persistence.py`. NO se reescriben helpers en cada módulo.

API mínima del archivo:

```python
# core/persistence.py

def _save_snapshot(df, area, cliente, modulo, period) -> Path: ...
def _load_snapshot(area, cliente, modulo, period) -> pd.DataFrame | None: ...
def _load_history(area, cliente, modulo) -> pd.DataFrame: ...  # lee _history.parquet
def _rebuild_history(area, cliente, modulo) -> Path: ...       # reconstruye _history desde snapshots
def _append_log(row, area, cliente, modulo, log_name) -> Path: ...
def _load_log(area, cliente, modulo, log_name, filters=None) -> pd.DataFrame: ...
def _save_config(config, area, modulo, name, version) -> Path: ...
def _load_config(area, modulo, name, version) -> dict: ...
def _list_periods(area, cliente, modulo) -> list[str]: ...     # lista snapshots disponibles
def _validate_against_schema(df, modulo, version) -> list[str]: ...
```

Si necesitás una función nueva genérica de I/O, va en `core/persistence.py`. Si es específica del módulo (ej. cómo serializar un objeto `PricingResult` particular), va en el módulo.

---

## ✅ Checklist al construir un módulo con persistencia

Antes de mergear un módulo nuevo que persiste datos:

- [ ] Toda I/O va por `core/persistence.py` — sin `pd.read_parquet`/`to_parquet` directo en el módulo
- [ ] Path sigue patrón `data/<area>/<cliente>/<modulo>/`
- [ ] Naming de archivos sigue `YYYY-WW.parquet` o equivalente ISO
- [ ] Schema versionado existe en `data/_schemas/<modulo>-v<N>.json`
- [ ] Logs append-only se llaman semánticamente (`optimizations.parquet`, no `data.parquet`)
- [ ] `.gitignore` cubre el path de datos del módulo
- [ ] Lecturas usan `@st.cache_data`, escrituras invalidan cache con `<funcion>.clear()`
- [ ] No hay lógica de negocio en los helpers de persistencia (solo I/O)
- [ ] Hay archivo `_examples/` con datos sintéticos para testing y demo

---

## 🚨 Anti-patterns que rompen este skill

- ❌ Usar `pickle` — no es portable, no es schema-aware, breaking change de Python lo rompe
- ❌ Usar `localStorage` o cualquier mecanismo client-side — Streamlit es server-side
- ❌ Versionar datos de cliente en git
- ❌ Reescribir helpers de I/O en cada módulo en lugar de usar `core/persistence.py`
- ❌ Hardcodear paths en los módulos en lugar de pasar `area/cliente/modulo` como argumentos
- ❌ Mezclar schema con datos en el mismo archivo (ej: primer fila del CSV es metadata)
- ❌ Borrar archivos de datos viejos automáticamente — eso lo decide el usuario, no la app
- ❌ Cambiar formato de path "porque tiene más sentido en este caso" — los casos especiales matan el patrón

---

## 🔗 Referencias

- Skill complementario: `module-architecture-standard.md` (patrones generales de módulos Streamlit)
- Skill complementario: `account-health-standard.md` (convenciones específicas de la sección)
- Agente que opera sobre este skill: `data-persistence-specialist.md`
- Decisiones cliente: `notes/sops/PPC-SOP-Manager.md` para naming de clientes existentes
