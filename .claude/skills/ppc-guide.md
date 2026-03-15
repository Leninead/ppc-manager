# PPC Manager – Guía de uso

## Cómo correr la app

```bash
streamlit run app.py
```

Si es la primera vez, instalá las dependencias:

```bash
pip install streamlit pandas openpyxl
```

La app abre en `http://localhost:8501` por defecto.

---

## Tabs y archivos esperados

### Tab 1 – Search Term Report (STR)

**Archivo:** Descargarlo desde Amazon Ads → Reports → Search Term Report.

**Columnas requeridas para las métricas:**
| Columna | Descripción |
|---------|-------------|
| `Spend` | Gasto total en publicidad |
| `Sales` | Ventas atribuidas a los anuncios |

**Columnas comunes adicionales:**
`Customer Search Term`, `Impressions`, `Clicks`, `Orders`, `Match Type`, `Campaign Name`, `Ad Group Name`

**Métricas calculadas:**
- **Total Spend** – suma de `Spend`
- **Total Sales** – suma de `Sales`
- **ACoS** – `(Spend / Sales) * 100`
- **Términos únicos** – cantidad de filas del archivo

---

### Tab 2 – Search Query Performance (SQP)

**Archivo:** Descargarlo desde Seller Central → Brand Analytics → Search Query Performance.

**Columnas comunes:**
`Search Query`, `Search Query Score`, `Impressions`, `Clicks`, `Cart Adds`, `Purchases`, `Brand`

Solo muestra la tabla. No realiza cálculos.

---

### Tab 3 – Bulk Campaigns File

**Archivo:** Descargarlo desde Amazon Ads → Bulk Operations → descargar el archivo bulk de campañas.

**Columnas comunes:**
`Record Type`, `Campaign Name`, `Ad Group Name`, `Keyword`, `Match Type`, `Bid`, `Status`, `Impressions`, `Clicks`, `Spend`, `Sales`

Solo muestra la tabla. No realiza cálculos.

---

### Tab 4 – Business Report

**Archivo:** Descargarlo desde Seller Central → Reports → Business Reports → By ASIN.

**Columnas comunes:**
`ASIN`, `Title`, `Sessions`, `Units Ordered`, `Ordered Product Sales`, `Unit Session Percentage`, `Buy Box Percentage`

Solo muestra la tabla. No realiza cálculos.

---

## Notas

- Todos los tabs aceptan `.xlsx` y `.csv`.
- Los nombres de columnas deben coincidir exactamente con los exports de Amazon (en inglés).
- No hay persistencia de datos entre sesiones; cada carga es independiente.
