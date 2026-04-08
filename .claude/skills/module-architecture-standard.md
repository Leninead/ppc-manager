# Skill: Module Architecture Standard
## Propósito
Estandarizar la estructura de todos los módulos Streamlit del Agency OS. Se activa cuando cualquier agente crea un módulo nuevo o modifica uno existente en modules/pages/.

## Estructura de un módulo
```python
"""
Módulo: [Nombre]
Sección: [PPC | Research | Account | Knowledge]
Input: [archivos requeridos]
Output: [qué produce — tabs, Excel, charts]
"""
import streamlit as st
import pandas as pd
import io
# imports adicionales según necesidad

# ── Constants ────────────────────────────────────────────────
_COLORES = {...}  # si el módulo necesita colores específicos

# ── Parsers (siempre con cache) ──────────────────────────────
@st.cache_data
def _parse_xxx(raw_bytes: bytes, filename: str) -> dict | pd.DataFrame:
    """Parser del input principal. Siempre recibe bytes, no file object."""
    ...

# ── Helpers privados ─────────────────────────────────────────
def _helper_name(args):
    """Prefijo _ obligatorio para funciones internas."""
    ...

# ── Excel export (FUERA de render) ───────────────────────────
def _build_xxx_excel(df, kpis, client_name="") -> bytes:
    """Genera Excel con branding Capybaras. Retorna bytes."""
    ...

# ── Render principal ─────────────────────────────────────────
def render():
    """Punto de entrada del módulo. Llamado por app.py."""
    # 1. Header
    # 2. File uploaders
    # 3. Empty state si no hay archivos
    # 4. Parse + tabs
    # 5. Export buttons
```

## Header estándar
```python
st.markdown(
    "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
    "<span style='font-size:2rem;'>📊</span>"
    "<div><div style='font-size:1.3rem;font-weight:700;'>[Nombre del Módulo]</div>"
    "<div style='font-size:0.82rem;color:#888;'>"
    "[Subtítulo descriptivo corto]</div>"
    "</div></div>",
    unsafe_allow_html=True,
)
st.divider()
```

## Empty state estándar
```python
st.markdown(
    "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
    "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
    "<div style='font-size:1.5rem;'>📂</div>"
    "<div style='font-weight:600;margin-top:0.5rem;'>Subí [nombre del archivo]</div>"
    "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
    "[Instrucciones de dónde descargarlo en Amazon/herramienta]</div>"
    "</div>",
    unsafe_allow_html=True,
)
return  # ← CRÍTICO: siempre return después de empty state
```

## Tabs — patrón correcto
```python
tab1, tab2, tab3 = st.tabs(["📊 Tab Name", "🔍 Tab Name", "📥 Export"])

with tab1:
    # contenido tab 1
    ...

with tab2:
    # contenido tab 2
    ...
# NUNCA poner return dentro de un with tab — rompe las tabs siguientes
```

## Session state — convenciones
- Prefix por módulo: `str_`, `sqp_`, `audit_`, `bid_`, `cb_`, etc.
- File uploaders: `key="str_file_upload"` (único globalmente)
- Download buttons: `key="str_dl_excel"` (único globalmente)
- Nunca reutilizar keys entre módulos

## Parsers — reglas
- Siempre decorar con `@st.cache_data`
- Input: `raw_bytes: bytes` (nunca UploadedFile directo)
- Llamar con: `_parse_xxx(file.getvalue(), file.name)`
- Numericizar métricas: `pd.to_numeric(df[col], errors="coerce")`
- Detectar columnas por nombre parcial, no índice

## Download buttons
```python
buf = io.BytesIO()
# ... escribir Excel en buf ...
st.download_button(
    "⬇️ Descargar [nombre] (Excel)",
    data=buf.getvalue(),
    file_name=f"[prefijo]_{client_name or 'export'}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key="[modulo]_dl_[tipo]",  # key ÚNICO
)
```

## Conexión al router (app.py)
Al crear un módulo nuevo, siempre agregar:
1. Import: `from modules.pages import nuevo_modulo`
2. Sidebar button en la sección correcta (PPC/Research/Account/Knowledge)
3. Routing: `elif st.session_state["selected_page"] == "Nombre": nuevo_modulo.render()`
4. Actualizar `core/constants.py` → `_PAGES`

## Checklist pre-commit de un módulo
- [ ] py_compile pasa sin errores
- [ ] Header con emoji + título + subtítulo
- [ ] Empty state con instrucciones claras
- [ ] Parsers con @st.cache_data
- [ ] _build_*_excel() fuera de render()
- [ ] Keys de download_button únicos
- [ ] Sin return dentro de with tab
- [ ] Conectado en app.py (import + sidebar + routing)

## Qué NO hacer
- Nunca poner return dentro de un bloque `with tab:` — rompe tabs posteriores
- Nunca usar st.cache_resource para DataFrames — solo st.cache_data
- Nunca pasar UploadedFile a un parser — pasar .getvalue() (bytes)
- Nunca crear funciones Excel dentro de render() — bug openpyxl
- Nunca hardcodear nombres de columnas sin fallback — Amazon cambia headers entre reportes
- Nunca dejar un file_uploader sin key único — causa conflictos entre módulos
