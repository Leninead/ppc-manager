---
title: Walmart Seller Central — Audit completo (Sesión 1)
type: research/audit
platform: walmart
sub-platform: seller-central
date: 2026-06-08
status: sesión 1 cerrada — sesión 2 (Walmart Connect) pendiente
account_audited: Pura Vida Moringa (cuenta verificada, sin ventas, 4 SKUs en Pending Review WFS Compliance)
tools_used: Claude Chrome (Opus 4.8) — modo Ask before acting
sessions: 8 reportes de exploración + 1 consolidado final
---

# Walmart Seller Central — Audit completo (Sesión 1)

## Resumen ejecutivo

- **11 secciones de contenido** en sidebar + **Settings como overlay** separado. "Unlock" es toggle de colapsar, no sección.
- **Arquitectura multi-gate vs ODR-centric**: Walmart evalúa salud y elegibilidad de ads cruzando 5 gates secuenciales (Compliance → Publish → Buy Box → LQS → Account Health Standards → Pro Seller → Ad Eligibility). Amazon condensa todo en ODR + Buy Box. Esto define la arquitectura del módulo Walmart como pipeline de validación, no como dashboard agregado.
- **Single export format = Zip(CSV)** para los 24 reportes nativos. Simplifica brutalmente el parser vs el universo Amazon que mezcla CSV/XLSX/JSON Lines.
- **Scheduling nativo en la UI**: el módulo puede delegar la programación a Walmart y solo consumir downloads. Sin necesidad de cron propio.
- **Sin SQP / Brand Analytics equivalente**: Search Insights es rank-based, no query-based. Todo el keyword research migra a Walmart Connect (sesión 2). Para cliente recién entrando a Walmart, esto significa primeros 60-90 días con ad spend cumpliendo doble función (ventas + research).
- **Calendario fiscal Walmart** (Q1=Feb-Apr, Q2=May-Jul, Q3=Aug-Oct, Q4=Nov-Jan) — bug-trap conocido para comparativas cross-platform.
- **24 reportes exportables** categorizados en 5 grupos. Pricing insight (~46 cols) + Item sales (con LQS embebido) + Catalog Item (~55 cols) son la base del módulo.
- **Repricer nativo** integrado al template de creación de ítems (cols 128-131): un seller puede enrolar al Repricer en el mismo XLSX de creación. Amazon configura aparte.
- **Marketplace Wallet con J.P. Morgan** como capa intermedia de payouts. Diferencia operativa real vs depósito directo de Amazon.
- **Ecosistema de Apps completamente disjunto del de Amazon**: cero overlap con Helium 10, Jungle Scout, DataDive, Pacvue, Skai, Perpetua, Teikametrics, Stackline, MerchantSpring. Solo sellerboard sobrevive. Universo dominado por ERPs cross-border chinos.

## Estado de la cuenta auditada

- **Cuenta**: Pura Vida Moringa (US Marketplace)
- **Status**: verificada, approved to sell, sin ventas históricas
- **Catálogo**: 4 SKUs cargados vía WFS, todos en **Pending Review → WFS Compliance → Action Needed**
  - `00655043998410` MoringaExtract — Moringa Leaf Extract Liquid Drops 2oz
  - `00198168805862` MORINGAOIL4oz — Moringa Seed Oil 4oz
  - `00655043998427` MoringaPowderTub — Moringa Leaf Powder 8oz
  - `00794168665910` MoringaCapsules1 — Moringa Capsules 500mg 120ct
- **Razón del block (literal)**: *"This item may contain chemical. Please review the value of the attribute for accuracy."* — Walmart enhanced vetting program disparado por categoría Herbal Supplements.
- **SLA de review**: 3 días hábiles tras corrección + resubmit.
- **Onboarding WFS**: pasos 1-2 (settings + billing) Done; pasos 3-4 (catalog WFS + send inventory) pendientes — el panel WFS está gated hasta primer shipment.
- **Buy Box win rate**: 0% (catálogo no publicado).
- **PCS (Price Competitiveness Score)**: N/A — insufficient pricing/traffic data.
- **LQS**: 0% / Poor (no hay items publicados que evaluar).
- **Account Health Standards**: todos "Not available" / "--" pero estado declarado limpio: "You're up to date! No action required".
- **Pro Seller Badge**: no elegible aún (falta volumen + antigüedad + standards en verde).
- **Marketplace Wallet**: J.P. Morgan, sin banco linkeado, balance $0.
- **API credenciales**: no generadas (vivirían en `/settings/api/consumer-id-and-private-keys`).

## Diagrama de gates secuenciales — diferencia arquitectónica vs Amazon

```
COMPLIANCE (WFS Pending Review / Trust & Safety)
        ↓ destrabar
PUBLISH (Catalog → ítem publicado + in-stock)
        ↓ habilita
BUY BOX (win the Buy Box vía precio + stock + fulfillment performance)
        ↓ alimenta
LISTING QUALITY SCORE (5 componentes ponderados)
        ↓ correlaciona con
ACCOUNT HEALTH STANDARDS (8 métricas independientes)
        ↓ gate de
PRO SELLER BADGE (multi-criterio sostenido)
        ↓ desbloquea
AD ELIGIBILITY + ORGANIC RANKING LIFT
        ↓ se mide en
ANALYTICS (Sales Insights + Search Insights rank-based)
```

**Implicancia para Agency OS**: el módulo Account Health Walmart NO puede usar el modelo single-score de Amazon. Tiene que modelar los 5 gates como pipeline secuencial, donde el fallo de un gate temprano bloquea todo lo downstream. El módulo debe alertar al gate más temprano que esté en rojo, no al output agregado.

## Account Health Walmart — schema completo (8 standards)

Los thresholds vienen de Settings > Account > Health and Compliance (no del scorecard principal de Performance, que es solo visualización).

| Métrica | Threshold | Ventana | Bucket | Equivalente Amazon |
|---|---|---|---|---|
| On-time delivery (OTD) | ≥90% | 30d rolling | Fulfillment | On-Time Delivery Rate |
| Cancellations (seller-initiated) | ≤2% | 30d rolling | Fulfillment | Cancellation Rate |
| Valid tracking | ≥99% | 30d rolling | Fulfillment | Valid Tracking Rate (VTR) |
| Late shipment (LSR) | ≤5% | 30d rolling | Fulfillment | Late Shipment Rate |
| Seller response | ≥95% | 30d rolling | Customer Service | Contact Response Time |
| Negative feedback | ≤2% | 60d rolling | Post-sale | Seller Feedback Negative |
| Returns | ≤6% | 60d rolling | Post-sale | (Amazon no lo formaliza) |
| Item not received (INR) | ≤2% | 60d rolling | Post-sale | A-to-z / INR claims |

**Trampas conocidas para el módulo:**
- **No hay score agregado único.** Si el cliente espera un "AHR equivalente", lo componemos nosotros con fórmula propia.
- **OTD trae desglose accountable vs non-accountable.** Solo accountable cuenta al score. Drivers accountable: Carrier delays, Late shipment, Carrier method mismatch, Ship location mismatch. Drivers non-accountable: Carrier exceptions, Miscellaneous, Weather delays. **Filtrar antes de calcular** o tirás falsos positivos.
- **Ventanas mixtas 30d/60d** — el módulo necesita dos timestamps de evaluación por SKU.
- **Returns es standard formal en Walmart**, no informativo. El cap 6% es hard.

## Listing Quality Score — schema completo (5 componentes)

URL: `/growth/listing-quality`. Walmart NO publica pesos numéricos, solo bandas.

| Componente | Qué pondera (literal) | Fuente del dato |
|---|---|---|
| Content quality | Completitud y exactitud de atributos (name, description, key features, images) | Cruzar listing vs spec template |
| Ratings & Reviews | Cantidad recibida × positividad | Performance > Ratings & Reviews |
| Price competitiveness | % impresiones con precio competitivo en últimos 7d, impression-weighted. **Incentivos Walmart-funded NO suben PCS** | Pricing insights + Walmart funded incentives report (excluir) |
| Shipping | % zip codes US mainland cubiertos en 3-day free. **WFS = 100% automático**. Items >50lb o ≤$10 → N/A | Shipping configuration |
| Published and in-stock | Binario publish status + inventory | Catalog + Inventory report |

**Bandas de color**:
- 🔴 Poor: 0–59%
- 🟡 Good: 60–79%
- 🟢 Excellent: 80–100%

**Decisión de diseño para el módulo**: NO calcular LQS sintético propio (no tenemos pesos). Pullear el score que Walmart ya calculó vía la columna `Listing_Quality_Score` que viene embebida en el reporte `Item sales`. Reverse-engineer de pesos vía regresión queda en backlog para cuando tengamos 50+ items con score real.

## Top 5 features distintivas — Walmart-only

1. **Listing Quality Score con 5 componentes públicos y bandas explícitas** (Growth › `/growth/listing-quality`). Amazon tiene Listing Quality Dashboard pero más oculto y sin score numérico unificado. → Implementable directamente como columna en módulo Account Health.

2. **Price Competitiveness Score (PCS) impression-weighted con benchmark Pro Seller 75%** (Pricing). Mide % impresiones con precio competitivo en últimos 7d. Items de alto tráfico pesan más. Walmart-funded incentives están explícitamente excluidos del cálculo. → Sin equivalente en Amazon. Gate previo a ads efectivos.

3. **Pro Seller Badge + Reduced Referral Fees Incentives** (Growth + Pricing). Programa de tiers con badge visible al cliente + cofinanciación: Walmart baja su comisión si el seller baja precio. → Sin equivalente en Amazon. Palanca de margen real.

4. **Marketplace Wallet con J.P. Morgan + Capital + Multi-currency partners (Payoneer, WorldFirst, LianLian, PingPong, Airwallex)** (Payments + Apps). Capa financiera integrada, no depósito directo a banco. → Diferencia operativa material en el módulo de reconciliación financiera.

5. **WFS auto-100% Shipping en LQS + Review Accelerator (Vine-equivalent + Sampling)** (Growth). Dos palancas accionables directas para subir LQS sin tocar contenido: enrolar en WFS → 100% Shipping automático; enrolar en Review Accelerator → genera reviews programáticamente. → Sin equivalente combinado en Amazon.

## Top 5 gaps — Amazon-only en Marketplace 3P

1. **Search Query Performance (SQP) granular query-level** — (c) existe con forma distinta. Walmart tiene Search Insights (`/analytics/search-insights`) pero es **rank-based a nivel ítem** (Impressions Rank, Clicks Rank, Added to Cart Rank, Sales Rank), no query-level. Las query insights se entregan por newsletter mensual no exportable. Análogo real probablemente vive en Walmart Connect (sesión 2).

2. **Brand Analytics suite completo** (Top Search Terms, Demographics, Repeat Purchase, Market Basket) — (b) no existe en Seller Central. Posible parcialmente en Walmart Connect.

3. **Campaign Manager / Sponsored Products / Bulk Files** — (a) en Walmart Connect (`advertising.walmart.com`), out of scope esta sesión.

4. **Amazon Vine** — (c) existe con otro nombre: Review Accelerator (`/growth/review-accelerator`) con sub-programas Post-Purchase Reviews + Recognized Reviewer (sampling).

5. **Brand Registry** — (c) existe con otra forma: Brand Manager (`/growth/brand-manager`) → registro AR (Authorized Reseller) o ABO (Acting Brand Owner) vía Brand Portal (dominio aparte `brandportal.walmart.com`). Walmart afirma literal que aprobación de marca da "higher content ranking".

**Mención extra**: export multi-formato. Amazon ofrece CSV/XLSX/TSV según reporte. Walmart Reports exporta exclusivamente Zip(CSV). Ventaja desde el punto de vista del parser, limitación si el cliente espera output en XLSX directo.

## Inventario de reportes — ranking de prioridad para automatización

Categorización por valor recurrente y dependencia con módulos existentes.

### TIER 1 — Core (implementar primero)

| Reporte | URL | Razón |
|---|---|---|
| Pricing insight | `/reports/pricing-reports` | ~46 cols: Buybox Win %, competitor URL/price/ship/lastFetched, repricer suggested min/max, PCS, GMV30, Traffic, Inventory, Promo. Reemplaza casi por completo lo que en Amazon requiere cruzar 3-4 reportes. |
| Buy box | `/reports/pricing-reports` (tab Buy box) | Buy Box win rate dedicado por ítem |
| Item sales | `/reports/sales-reports/item-sales` | GMV/units/orders/conversion + columna `Listing_Quality_Score` embebida (clave para Account Health) |
| Catalog › Item | `/reports/catalog-reports/item` | ~55 cols: publish/lifecycle, Buy Box eligible, repricer status, competitor, WFS restriction, reviews. Snapshot maestro del catálogo. |

### TIER 2 — Operations

| Reporte | URL | Razón |
|---|---|---|
| Inventory | `/reports/catalog-reports/inventory` | Stock AvailToSell por ship node × SKU |
| Order | `/reports/orders-reports/order` | Línea de orden con PII de cliente — tratar con cuidado en logs |
| Cancellation | `/reports/fulfillment-reports` (tab Cancellation) | Account Health standard ≤2% |
| Delivery defect | `/reports/fulfillment-reports` (tab Delivery defect) | Salud de fulfillment |
| Return override | `/reports/orders-reports/return-override` | Lo más cercano a un Returns report |
| Lagtime | `/reports/fulfillment-reports` (tab Lagtime) | Fulfillment lag, feeds Account Health |

### TIER 3 — Promo/Incentive analytics

| Reporte | URL |
|---|---|
| Promotions / Discounts / Incentives | `/reports/pricing-reports` (tabs respectivos) |
| Incentives enrollment | `/reports/pricing-reports` |
| Walmart funded incentives | `/reports/pricing-reports` |

**Crítico**: Walmart funded incentives es excluido del cálculo PCS. El módulo tiene que cruzar este reporte vs Pricing insight para entender el PCS "limpio" del seller.

### TIER 4 — Edge cases

Item group, Add-on services item, Delete Sku, Shipping program, Ship with Walmart carrier reconciliation, Shipping configuration, Preorder & backorder inventory.

### Lo que NO está en Reports

- **Tax 1099-K**: vive en `/settings/partner-profile/taxes`.
- **Listing Quality dashboard granular**: vive en `/growth/listing-quality` (el score por SKU está embebido en Item sales).
- **Ratings & reviews detallado**: vive en `/performance/ratings-and-reviews/item-reviews`.

### Mecánica de Reports (común a todos)

- Formato único: **Zip(CSV)** comprimido.
- Mecánica: **request → job async → notification → download**. Preview snapshot disponible mientras se genera.
- **Scheduling nativo**: tab "Scheduled reports" por categoría, con frecuencia configurable.
- **Log de downloads**: en `/reports/overview`.
- Sin retention period numérico confirmado (queda como pregunta abierta).
- Vía API: `developer.walmart.com` + credenciales en `/settings/api/consumer-id-and-private-keys`.

## Plan de remediación — Pura Vida Moringa (4 SKUs)

Plan accionable para destrabar PPC. Orden de ejecución obligatorio.

### Paso 1 — Bulk fix de los 4 SKUs

Usar el spec template ya descargado (`omni-marketplacewfs-en-external-5_0_20260330-14_47_14.xlsx`, categoría Herbal Supplements). Para cada SKU:

- Setear `electronicsIndicator` = No
- Setear `isChemical` (col 16) = **Yes** (Moringa Oil = aceite vegetal técnicamente es químico, Liquid Drops = glicerina/alcohol, Capsules = excipientes). Es la corrección clave del block. → Adjuntar Safety Data Sheet por SKU (`safetyDataSheet`, col 21).
- Completar `vitamin_and_supplement_type` (col 57) con valor de la closed list correspondiente
- Completar `isProp65WarningRequired` (col 49) + `prop65WarningText` (col 71) si aplica
- Completar `fsma_section_204_traceability` (col 54)
- Completar `food_and_drug_fact_label_type` (col 97) — Supplement Facts label
- Completar nutrition block (cols 94-104): nutrient amount/name/% DV, serving size, servings per container
- Adjuntar General Certificate of Conformity (GCC) en certification section
- Completar dimensions en sheet "Trade Item Configurations": country of origin, width, height, depth, weight

### Paso 2 — Submit + esperar review

- Upload del XLSX corregido via `/catalog/add-items/bulk` (Update with file).
- SLA Walmart: hasta 3 días hábiles.
- Si quedan en "In Review" > 3 días → contactar Partner Support.

### Paso 3 — Configurar Repricer desde el mismo template

El template incluye cols 128-131 para Repricer config en creación:
- `msrp` (col 128) — precio sugerido al público
- `minimumSellerAllowedPrice` (col 129) — piso (margin protection)
- `maximumSellerAllowedPrice` (col 131) — cap (anti-flip)
- `repricerStrategy` (col 130) — elegir AI vs Rule-based

### Paso 4 — Setup WFS

- Completar paso 4 del onboarding WFS: send inventory.
- Esto desbloquea: panel WFS completo, inventory dashboard, inbound shipments, WFS reports.
- Cambio automático en LQS: +100% Shipping score para los 4 SKUs.

### Paso 5 — Configurar Marketplace Wallet

- Link banco al wallet (`/payments/wallet`).
- Hasta que esto no se complete, no hay payouts efectivos.

### Paso 6 — Activar Review Accelerator (opcional, paid)

- Enrolar en Post-Purchase Reviews o Recognized Reviewer (sampling).
- Sube el componente Ratings & Reviews del LQS.

### Paso 7 — Solicitar Brand Manager AR/ABO via Brand Portal

- Solicitar Acting Brand Owner status para Pura Vida Moringa en `brandportal.walmart.com`.
- Desbloquea: higher content ranking declarado por Walmart, brand shops, ad assets.

### Paso 8 — Recién acá: arrancar PPC

- Pre-condiciones: SKUs publicados + Buy Box win rate > 0% + PCS razonable + Account Health limpio.
- Esta es la primera oportunidad de Walmart Connect (sesión 2 del scan).

**Estimación de tiempo total para llegar a paso 8**: 3-4 semanas asumiendo el cliente proporciona Safety Data Sheets + GCC + completa información nutricional sin trabas.

## URL map completo

### Top-level del sidebar (11 secciones + Settings)

```
Home                /home
Catalog             /catalog/list-items
Pricing             /pricing/insights
Orders              /orders/manage-orders          [skip sesión 1]
WFS                 /wfs/wfs-onboarding            [gated hasta primer shipment]
Payments            /payments/statements
Performance         /performance/order-and-fulfillment
Analytics           /analytics/overview
Growth              /growth/success-hub
Advertising         /advertising/home              [= Walmart Connect, sesión 2 — vive DENTRO de Seller Center]
Reports             /reports/overview
Apps                /apps/app-listings
Settings (overlay)  /settings → /settings/account/personal-info
```

### Sub-secciones Catalog
```
List Items                  /catalog/list-items
Unpublished Items           /catalog/unpublished-items
Pending Review              /catalog/pending-review  [tabs: WFS Compliance / Trust And Safety / Potential duplicates]
Media Library               /catalog/media-library
Activity Feed               /catalog/activity-feed   [Uploads / Downloads]
GTIN Exemptions             /catalog/gtin-exemptions
Walmart+ Seller Fulfilled   /catalog/walmart-plus
Add Items                   /catalog/add-items
Add Items (Bulk)            /catalog/add-items/bulk
Spec Download               /catalog/spec-download
```

### Sub-secciones Pricing
```
Insights            /pricing/insights
Automate pricing    /pricing/automate-pricing   [AI repricer / Rule-based]
Incentives          /pricing/incentives
Promotions          /pricing/promotions
Deals               /pricing/deals
```

### Sub-secciones Payments
```
Statements          /payments/statements
Transactions        /payments/transactions
Capital             /payments/capital
Marketplace Wallet  /payments/wallet              [J.P. Morgan]
```

### Sub-secciones Performance
```
Order & Fulfillment     /performance/order-and-fulfillment
Ratings and Reviews     /performance/ratings-and-reviews/item-reviews
Health and Compliance   /settings/account/health-compliance  [vive técnicamente en Settings]
```

### Sub-secciones Analytics
```
Executive Dashboard     /analytics/overview/executive-dashboard
Sales Insights          /analytics/sales-insights/account-sales
                                tabs: Account Sales / Item Sales / Sales by Department
Search Insights         /analytics/search-insights  [rank-based, NO query-based]
```

### Sub-secciones Growth (7 sub-items)
```
Success Hub             /growth/success-hub
Assortment Growth       /growth/assortment-growth/assortment-explorer
Exclusive Programs      /growth/exclusive-programs
Listing Quality         /growth/listing-quality
Pro Seller              /growth/seller-tiering/overview      [label/URL mismatch]
Review Accelerator      /growth/review-accelerator
Brand Manager           /growth/brand-manager                [→ brandportal.walmart.com]
```

### Sub-secciones Reports (5 categorías + Overview)
```
Overview                /reports/overview                [Saved + Scheduled + Downloaded log]
Sales                   /reports/sales-reports
  ├── Item sales        /reports/sales-reports/item-sales
Catalog                 /reports/catalog-reports
  ├── Item              /reports/catalog-reports/item
  ├── Item group        /reports/catalog-reports
  ├── Add-on services   /reports/catalog-reports
  ├── Delete Sku        /reports/catalog-reports
  ├── Inventory         /reports/catalog-reports/inventory
  └── Preorder/backorder /reports/catalog-reports
Pricing                 /reports/pricing-reports
  ├── Pricing insight   /reports/pricing-reports
  ├── Buy box           /reports/pricing-reports
  ├── Promotions        /reports/pricing-reports
  ├── Discounts         /reports/pricing-reports
  ├── Incentives        /reports/pricing-reports
  ├── Incentives enrollment /reports/pricing-reports
  └── Walmart funded incentives /reports/pricing-reports
Orders                  /reports/orders-reports
  ├── Order             /reports/orders-reports/order
  └── Return override   /reports/orders-reports/return-override
Fulfillment             /reports/fulfillment-reports
  ├── Shipping program  /reports/fulfillment-reports/shipping-program
  ├── Ship with Walmart carrier reconciliation /reports/fulfillment-reports
  ├── Lagtime           /reports/fulfillment-reports
  ├── Shipping configuration /reports/fulfillment-reports
  ├── Cancellation      /reports/fulfillment-reports
  └── Delivery defect   /reports/fulfillment-reports
```

### Sub-secciones Apps
```
Apps store      /apps/app-listings
Connected Apps  /apps/connected-apps   [URL inferida, a verificar]
```

### Sub-secciones Advertising (Walmart Connect) — preview de sesión 2
```
Sponsored Search                /advertising/home                [vive dentro de Seller Center, NO en dominio aparte]
Display and Brand Shop          [URL a confirmar sesión 2]
Search Engine Marketing         [URL a confirmar sesión 2]
Sales Rewards and Attribution   [URL a confirmar sesión 2]
```

### Sub-secciones Settings (overlay)
```
Account
  ├── My Profile             /settings/account/personal-info
  ├── Notification Settings  /settings/account/notification-settings
  └── Health and Compliance  /settings/account/health-compliance

Partner Profile
  ├── Company Info           /settings/partner-profile  [URL específica a verificar]
  ├── Manage Contacts        /settings/partner-profile  [URL específica a verificar]
  ├── Taxes                  /settings/partner-profile/taxes
  └── Business Information   /settings/partner-profile  [URL específica a verificar]

Shipping Profile
  ├── Seller Fulfillment              [a verificar URLs]
  ├── Shipping Info
  ├── Simplified Shipping Settings
  ├── Shipping Templates
  ├── Ship with Walmart
  ├── Returns
  └── Walmart Imports

Administrator Options
  ├── People and Permissions
  ├── 2-Step Verification
  ├── Message Templates
  ├── Agreements
  └── Seller Certification

Financial Settings
  ├── Billing Services
  ├── Payment Info
  └── Marketplace Wallet

API
  └── Consumer ID and Private Keys   /settings/api/consumer-id-and-private-keys
```

### Dominios separados (app-drawer ::: arriba izquierda)
```
Brand Portal           brandportal.walmart.com         [Brand Manager AR/ABO]
Developer Portal       developer.walmart.com           [Marketplace API + Connect Ads API]
Marketplace Learn      [URL a verificar]               [Education]
Support Hub            seller.walmart.com/supporthub/  [Cases]
WFS Public Pricing     marketplace.walmart.com/walmart-fulfillment-services-pricing/
Walmart Connect        seller.walmart.com/advertising/home   [vive dentro de Seller Center — corrección descubierta al cierre de sesión 1]
                       advertising.walmart.com               [dominio público marketing, NO operativo]
```

## Próximos pasos

1. **Sesión 2 del scan**: Walmart Connect / Advertising. Foco en Search Term Reports, bidding strategies, ad eligibility confirmation, ad spend deduction mechanics. Ver `notes/walmart/open-questions-walmart-connect.md`.
2. **Sesión 3**: diseño formal del módulo `walmart-manager` para Agency OS (sitemap + reportes + Account Health + Repricer integration).
3. **Spec template snapshot**: ver `notes/walmart/spec-template-herbal-supplements.md` para el schema detallado de 131 columnas.
4. **Decisión comercial**: evaluar si el plan de remediación Pura Vida Moringa (sección "Plan de remediación") se entrega como auditoría facturable.
