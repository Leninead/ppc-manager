---
title: Walmart Connect — Preguntas abiertas (sesión 2)
type: research/open-questions
platform: walmart
sub-platform: walmart-connect
related: notes/walmart/seller-central-audit.md
date: 2026-06-08
status: pending — esperando sesión 2 del scan (Claude Chrome sobre advertising.walmart.com)
---

# Walmart Connect — Preguntas abiertas para sesión 2

Lista de items que quedaron sin resolver en la sesión 1 (Seller Central) y dependen específicamente de Walmart Connect / Ad Center.

## Preguntas críticas — bloqueantes para diseño del módulo

### 1. Ad spend deduction mechanic
**Pregunta**: ¿el spend de ads se descuenta net-off del payout (vía Marketplace Wallet / Statements de Payments) o se cobra como cargo separado a una tarjeta de crédito de billing?
**Por qué importa**: define si el módulo de reconciliación financiera cruza Payments Statement vs Ads Statement como dos fuentes o las trata como flujo único.
**Hipótesis de trabajo**: Walmart probablemente net-off (a diferencia de Amazon que cobra ads aparte). A confirmar.

### 2. Search Term Reports equivalente al de Amazon Ads
**Pregunta**: ¿Walmart Connect entrega reportes query-level con impresiones, clicks, conversiones por search term (lo que Amazon llama Search Term Report)?
**Por qué importa**: es la ÚNICA fuente de keyword intelligence en Walmart (no hay equivalente orgánico tipo SQP). Define todo el playbook de keyword harvesting.
**Hipótesis de trabajo**: sí existe en Walmart Connect, formato CSV. A confirmar columnas y granularidad.

### 3. Formatos de ad disponibles
**Pregunta**: confirmar oferta de Sponsored Products (Search, Item Buybox, Item Carousel), Sponsored Brands, Sponsored Videos, Sponsored Display, DSP/Trade Desk integration.
**Por qué importa**: define qué módulos de campaign management son aplicables para portar.

### 4. Bidding strategies
**Pregunta**: ¿qué bid strategies expone Walmart Connect — manual fijo, automated bidding, multipliers (placement / device / day-parting), modifiers?
**Por qué importa**: si Walmart tiene equivalente a Amazon "Dynamic bids - down only" / "Dynamic bids - up and down" / "Fixed bids", el módulo de bid management se puede portar con cambios menores.

### 5. Bulk Files / Bulk Operations
**Pregunta**: ¿existe equivalente a los Bulk Sheets de Amazon Ads (XLSX template para crear/modificar/pausar campañas en bulk)?
**Por qué importa**: M-Setex y los workflows actuales de bulk operations dependen enteramente del Bulk Sheet pattern. Si Walmart no lo tiene, hay que rediseñar el workflow para client-by-client UI work.

### 6. Ad eligibility — confirmación literal
**Pregunta**: ¿Walmart afirma explícitamente que Buy Box + Listing Quality Score + PCS condicionan la elegibilidad para ads? Capturar texto literal.
**Por qué importa**: en sesión 1 vimos pistas pero no confirmación literal. Si está confirmado, el módulo Account Health Walmart tiene que bloquear gasto en ads cuando los gates están en rojo.

## Preguntas secundarias — informativas

### 7. Walmart Connect Ad Hub
**Pregunta**: ¿el Ad Hub mencionado en Search Insights es solo educación o también herramienta operativa? ¿Cómo se integra con Search Insights de Seller Central?
**Por qué importa**: si es educativo solamente, lo dejamos pasar; si es operativo, lo mapeamos.

### 8. WCPN Partner Program
**Pregunta**: ¿qué requisitos tiene Walmart Connect Partner Network para una agencia entrar como Solution Provider?
**Por qué importa**: alternativa al acceso client-level. Si WCPN es accesible para Capybaras, abre la puerta a Connect Ads API directo (single source para múltiples clientes).
**Contexto previo**: ver investigación en chat anterior sobre Walmart Connect API US-only + WCPN requirements.

### 9. Brand Portal — ad assets desbloqueados
**Pregunta**: ¿qué ad assets/brand shops desbloquea Acting Brand Owner (ABO) status?
**Por qué importa**: si ABO desbloquea Sponsored Brands Stores equivalente al Amazon Brand Store, es palanca clave para Pura Vida Moringa una vez aprobada la marca.

### 10. Walmart Connect API (US-only) — credenciales
**Pregunta**: ¿cómo se obtienen las credenciales de Walmart Connect Ads API (distintas a las de Marketplace API)?
**Por qué importa**: integración real futura. Marketplace API se gestiona desde Seller Center (`/settings/api/consumer-id-and-private-keys`). Ads API tiene flujo distinto (WCPN o client-level connection).

## Preguntas secundarias — operativas

### 11. Walmart Connect reports retention period
**Pregunta**: ¿cuánto tiempo quedan disponibles para download los reportes generados? ¿Hay diferencia entre Seller Center Reports (sesión 1 no confirmó retention) y Walmart Connect reports?
**Por qué importa**: define si el módulo necesita storage propio o puede confiar en Walmart como source of truth.

### 12. Brand Analytics-equivalente en Connect
**Pregunta**: ¿existe en Walmart Connect algún análogo a Brand Analytics Demographics / Repeat Purchase / Market Basket? Search Insights de Seller Center confirmó que no en el lado orgánico.

### 13. Tipos de bid placements
**Pregunta**: ¿Walmart Connect tiene placement bidding (Top of Search / Item Buybox / Item Carousel multipliers) similar a Amazon?

### 14. Campaign types y targeting
**Pregunta**: keyword targeting (broad/phrase/exact)? Auto vs Manual? Product targeting? Category targeting? Audience targeting (Walmart Connect DSP)?

### 15. Reporting de attribution
**Pregunta**: window de attribution (Walmart usa 30 días vs 14 días de Amazon?). Click-attributed vs view-attributed split.

## Dominios externos pendientes

### 16. marketplace.walmart.com/walmart-fulfillment-services-pricing
WFS Public Pricing Calculator. Releva cuando necesitemos modelar fees WFS vs FBA para unit economics.

### 17. developer.walmart.com
- Marketplace API docs.
- Walmart Connect Ads API docs (US-only).
- OAuth 2.0 flow + Client ID / Secret + Consumer ID / Private Keys.

### 18. brandportal.walmart.com
Brand Portal — AR / ABO registration flow + brand assets management.

## Notas para arrancar sesión 2

- Mega-prompt para Claude Chrome debe arrancar pidiendo navegación a `advertising.walmart.com` (NO a `seller.walmart.com/advertising/home` que es solo el link de entry).
- Mantener el mismo modo "Ask before acting" para no tocar campaigns activas.
- Si la cuenta auditada de Pura Vida Moringa no tiene Walmart Connect activado todavía (probable, dado que los SKUs siguen sin publicar), buscar acceso a otra cuenta para sesión 2. Sino, scan será de empty state otra vez.
- Replicar pattern de captura: URL, sub-secciones, KPIs, columnas, formatos, schedulable.
- Output esperado: schema completo de Walmart Connect equivalente a este audit de Seller Central.
