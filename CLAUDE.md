# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PPC Manager** is a Streamlit web application for analyzing Amazon PPC (Pay-Per-Click) campaign data. It accepts Excel/CSV file uploads and displays metrics and tables.

## Running the App

```bash
streamlit run app.py
```

Install dependencies if needed:
```bash
pip install streamlit pandas openpyxl
```

There is no build step, test suite, or linter configured.

## Architecture

The entire application lives in `app.py` — a single Streamlit script with no module separation. The UI is structured as seven tabs:

- **Tab 1 – Search Term Report (STR)**: ACoS `(Spend / Sales * 100)`, total spend, total sales, unique term count. Requires `Spend` and `Sales` columns.
- **Tab 2 – Search Query Performance (SQP)**: Raw SQP dataframe. Uses `read_sqp()` helper (skips Amazon's metadata row via `skiprows=1`).
- **Tab 3 – Bulk Campaigns File**: Raw bulk dataframe.
- **Tab 4 – Business Report**: Raw dataframe.
- **Tab 5 – Análisis Cruzado STR vs SQP**: Crosses STR (`Customer Search Term`) with SQP (`Search Query`) to find opportunities (terms in SQP not in STR). Computes Opportunity Score (min-max normalized impressions + clicks + purchase rate). Filters by min impressions, Search Query Score, purchases, and keyword type. Classifies keywords as brand/generic via `extract_sqp_brand()`, which reads the `Brand=["..."]` metadata from SQP row 0.
- **Tab 6 – Tendencia Multi-Semana**: Uploads up to 4 weekly SQP files, pivots by `Search Query`, shows impression trend arrows (↑ >10%, ↓ >10%, → stable).
- **Tab 7 – Análisis de Funnel**: Uploads Bulk + STR, shows active campaigns/ad groups/keywords, crosses STR terms against active keywords to detect coverage gaps.

Each tab independently reads uploaded files. SQP files always go through `read_sqp()`. `extract_sqp_brand()` reads row 0 before skipping it to extract the brand name.

## Campaign Naming Convention

```
Producto - ASIN - Tipo - Match Type - Estrategia/KW
```

Example: `Body Lotion - B0CYLM4L23 - SP - KW - Phrase - Retinol Benefits`

- **Producto**: product name
- **ASIN**: Amazon ASIN (e.g. `B0CYLM4L23`)
- **Tipo**: campaign type — `SP` (Sponsored Products), `SB` (Sponsored Brands), `SD` (Sponsored Display)
- **Match Type**: `KW - Broad`, `KW - Phrase`, `KW - Exact`, or `PAT` (product targeting)
- **Estrategia/KW**: targeting theme or specific keyword

## Amazon Bulk File — Columnas relevantes

| Columna | Descripción |
|---------|-------------|
| `Status` | Estado del registro (`enabled`, `paused`, `archived`) |
| `Type` | Tipo de registro (`Campaign`, `Ad Group`, `Keyword`, `Product Targeting`, etc.) |
| `Portfolio name` | Portfolio al que pertenece la campaña |
| `Campaign bid strategy` | Estrategia de puja (`Dynamic bids - down only`, `Fixed bids`, etc.) |
| `Campaign budget amount` | Presupuesto diario de la campaña |
| `Impressions` | Impresiones totales |
| `Top-of-search impression share` | % de impresiones en la parte superior de búsqueda |
| `Clicks` | Clicks totales |
| `CTR` | Click-through rate (`Clicks / Impressions`) |
| `Total cost` | Gasto total (equivalente a `Spend`) |
| `CPC` | Costo por click promedio |
| `Purchases` | Unidades compradas atribuidas |
| `Sales` | Ventas atribuidas |
| `ACoS` | Advertising Cost of Sale (`Total cost / Sales * 100`) |
| `ROAS` | Return on Ad Spend (`Sales / Total cost`) |

## Key Conventions

- UI text and labels are in Spanish.
- Column names in uploaded files are expected in English (e.g., `Spend`, `Sales`) — matching Amazon's default export headers.
- No state is persisted between sessions; all data lives in uploaded files per session.
