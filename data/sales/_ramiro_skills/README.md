# Ramiro Skills — Integración con Proposal Studio

Skills de Claude desarrolladas por Ramiro Folgueras (Director &
Strategy Manager de Capybaras Agency) que generan análisis de marca
pre-propuesta. Estos análisis alimentan los bloques editables del
Proposal Studio.

## Skills entregadas (2026-05-15)

### amazon-brand-audit
Analiza ASIN del lead en Data Dive (revenue, sales, share) + nicho
competitivo + listing completo.

- Archivo: `amazon-brand-audit/amazon-brand-audit.skill`
- Sample: `amazon-brand-audit/samples/amazon-audit-SAFEKO-*.html`

### digital-presence-audit
Analiza presencia digital de la marca: Instagram, Facebook, Walmart,
Shopify/website. Output HTML con grading A-F por canal + detección
de competidores con Meta ads activos.

- Archivo: `digital-presence-audit/digital-presence-audit.skill`
- Sample: `digital-presence-audit/samples/digital-audit-safeko-2026-05-13.html`

### capybaras-lead-deck
Skill unificadora que toma los outputs de las 2 skills anteriores y
arma un PPTX de propuesta comercial.

- Carpeta: `capybaras-lead-deck/` (extraído del ZIP)
- Estructura: SKILL.md + references/ + assets/
- Brand style canónico: `capybaras-lead-deck/references/brand-style.md`

## Brand style canónico (extraído de capybaras-lead-deck/SKILL.md)

| Token | Hex | Uso |
|-------|-----|-----|
| Black | `#0E0E0E` | Backgrounds dark (cover, dividers, closing) |
| Orange | `#FF3300` | Accent principal, líneas divisorias, callouts |
| Light orange | `#E85B03` | Accent secundario, gradients |
| White | `#FFFFFF` | Texto sobre dark, backgrounds content slides |
| Light gray | `#A0A0A0` | Texto muted sobre dark |
| Mid gray | `#666666` | Texto muted sobre light |

Font: **Blauer Nue** (Bold headers, Regular body). Sizes: titles
36-44pt, section headers 20-24pt, body 14-16pt, captions 10-12pt.

## Team estándar (de capybaras-lead-deck/SKILL.md)

**Standard (siempre, 4):**
- Agustin Favano — Account Manager
- Lenin Acosta — PPC Expert
- Marcos Callorda — Catalog Specialist
- Jeremias Orcajo — Graphic Designer

**Cross-Support (siempre, 3):**
- Freddy Neuman — Founder & CEO
- Guille Neuman — Advertising Manager
- Ramiro Folgueras — Director & Strategy Manager

**DTC (condicional, +2 cuando aplica):**
- Angeles — Shopify Expert
- Magali — Meta Ads Expert

## Reglas de inclusión DTC (de capybaras-lead-deck/SKILL.md)

Incluir sección DTC si:
- Meta Ads grade D/F AND competidor corre Meta ads
- Website grade D/F (signal de Shopify rebuild)
- Brand sin store DTC + categoría con demanda DTC clara
- Ramiro lo pide explícitamente

Excluir DTC si:
- Lead es Amazon-only (manufacturer o 1P→3P sin DTC)
- Meta Ads grade C+ AND Website grade C+
- Ramiro pide Amazon-only

## Integración planificada en Proposal Studio

**S4 — Parser HTML → JSON**:
  Drag-and-drop de HTMLs en el Proposal Studio → parser extrae datos
  estructurados → autocompleta bloques del catálogo (V1, V2, V3, V4...).

**S5 — Renderer HTML modular**:
  En lugar de generar PPTX, el Proposal Studio genera HTML interactivo
  + PDF via Playwright, usando mismos assets (logos, decorative,
  team_photos) que la skill.

## Mapeo HTML output → bloques del catálogo (hipótesis inicial)

A confirmar en S4 con los samples reales:

| Output HTML | Bloque del catálogo | Confianza |
|-------------|---------------------|-----------|
| amazon-brand-audit | V2_category_overview (data) | alta |
| amazon-brand-audit | V4_listing_improvements_current_state | alta |
| amazon-brand-audit | V3_seo_opportunity (parcial) | media |
| digital-presence-audit | V21_meta_ads_growth (existe) | alta |
| digital-presence-audit | V20_shopify_d2c_channel (existe) | alta |
| digital-presence-audit | Bloques nuevos para Walmart/IG/FB | n/a (crear) |
