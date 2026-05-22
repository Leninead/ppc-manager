---
tipo: sop
actualizado: 2026-05-22
categoria: amazon-ads
creado_por: sesion 2026-05-22 (Lenin ad hoc M&B asistiendo Agustín)
primera_implementacion: MB Mott & Bow 22/05/2026
---

# 🔗 Amazon Attribution — Setup de tags para tráfico externo

## Cuándo usar este SOP

Cuando un AM pida trackear ventas que vienen de canales externos (Meta FB/IG,
Google Ads, Email, Influencers, TikTok) hacia Amazon, para:
- Validar ROAS real de canales externos vs lo que reportan ellos (Meta suele
  inflarlo)
- Recuperar 10% rebate vía Brand Referral Bonus (BRB) sobre ventas atribuidas
- Atribuir spikes de tráfico al canal correcto (caso MB Marzo 2026 — $13K
  incremental sin attribution)

## Pre-requisitos del cliente

Antes de generar tags confirmar con AM:

1. Brand Registry activo en Amazon — sin esto no hay Attribution ni BRB
2. Brand Referral Bonus enrollment — separado de Attribution. Sin esto trackea
   pero no recupera el 10%. Activar en advertising console → BRB program
3. Lista de canales externos activos (Meta, Email, Google, etc.)
4. ASINs prioritarios a trackear — recomendado top 3-6 hero por revenue
5. Listado real de campañas del cliente en su Ads Manager (opcional V0,
   necesario V1 para granularizar)

## ⚠️ Decisión clave — Manual vs Bulk

**RECOMENDADO: Create manually.**

El bulk Beta de Amazon Attribution es FRÁGIL — procesa Campaign + Ad Groups +
Products pero NO genera los Ads/Tags. Status reportado "PRODUCTS_ADDED" es
engañoso. Resultado: cáscaras vacías sin URLs trackeables. Ver Gotcha #5 abajo.

Usar bulk SOLO si:
- Tenés 20+ tags que crear (manual sería inviable)
- Estás dispuesto a debuguear el flujo si falla

Para 6-12 tags: manual es más rápido y CONFIABLE.

## Flow Manual paso a paso (RECOMENDADO)

### Pre-flight check
1. Loguear en advertising.amazon.com con la cuenta del cliente correcto
2. VALIDAR advertiser correcto: en seller info top-right debe decir el cliente.
   Confirmar con un ASIN + precio típico del catálogo (ej: M&B = t-shirts $40)
3. Navegar: Measurement and Reporting → Amazon Attribution → Create campaign

### Crear Campaign + Ad Groups en 1 flujo
4. Click "Create manually" (NO bulk)
5. Llenar Campaign settings:
   - Name: `{CLIENTE}-{MERCADO}-{CANAL}-{Q+AÑO}` (ej: MB-US-META-2026Q2)
   - External ID: misma raíz sin guiones (ej: MBMETA2026Q2)
6. Agregar productos en sección Products:
   - Buscar por ASIN exacto (child ASINs, no parents)
   - Click "Add" en cada uno
   - Validar "X products" en columna derecha
7. Llenar Ad group 1:
   - Ad group name: `{FAMILIA}-{ABREV}-{VARIANTE}` (ej: A-CR-Black-M)
   - Publisher: Facebook (o Instagram, Google Ads, Other según canal)
   - Channel: Social (o Email, Search, Display)
   - Click-through URL: PDP del child ASIN (ej: https://www.amazon.com/dp/B0F6LDG3NK)
8. Click "+ Add new ad group" para cada ASIN adicional
9. Repetir paso 7 para cada Ad Group (1 Ad Group = 1 Tag único)
10. Click "Create" (botón negro arriba a la derecha)

### Post-create
11. Pantalla "Congratulations" + tabla con los tags generados
12. Click "Download all tags in CSV file" → archivo con columnas:
    Campaigns | Ad group | Publisher | Channel | Attribution tags | Click-through URL
13. La columna "Attribution tags" tiene las URLs trackeables (con `maas=...`
    parameters) — esas son las que el cliente reemplaza en sus ads

## Estructura del bulk file (si insistís con bulk — NO recomendado)

10 columnas obligatorias en orden exacto:

| Col | Campo | Ejemplo |
|---|---|---|
| A | Campaign ID | `MBMETA2026Q2` (alfanumérico, sin guiones recomendado) |
| B | Campaign Name | `MB-US-META-2026Q2` (legible, con guiones OK) |
| C | Campaign Objective | `Brand Awareness` |
| D | Ad Set ID | `ACRBLACKW` (alfanumérico único) |
| E | Ad Set Name | `A-CR-BLACK-WOMEN` |
| F | Link | `https://www.amazon.com/dp/B0F6LDG3NK` (PDP child ASIN) |
| G | Publisher Platforms | `facebook, instagram` |
| H | Ad ID | `ACRBLKM` (alfanumérico único por fila) |
| I | Ad Name | `A-CR-Black-M` |
| J | Creative Type | `Link Page Post Ad` |

Jerarquía: 1 Campaign > N Ad Sets > N Ads.

Riesgo bulk: Campaign + Ad Groups + Products se crean OK, pero Ads/Tags pueden
quedar sin generar (status engañoso "PRODUCTS_ADDED"). Si pasa, NO se pueden
agregar Ads manualmente al bulk roto — hay que crear todo nuevo en flow manual.

## Naming convention Capybaras

- **Campaign Name**: `{CLIENTE}-{MERCADO}-{CANAL}-{Q+AÑO}` — ej `MB-US-META-2026Q2`
- **Ad Group / Ad Name**: `{FAMILIA}-{ABREV}-{VARIANTE}` — ej `A-CR-Black-M`
- **IDs alfanuméricos** (sin guiones): `MBMETA2026Q2v2`, `ACRBLKM`

Si la Campaign falla y hay que recrear: sufijar con `-v2`, `-v3` (las Campaigns
de Attribution NO se pueden eliminar — solo archivar). Ver Gotcha #6.

## Gotchas críticos

### Gotcha 1 — Multi-cuenta riesgo
Antes de descargar template o crear campaign, validar advertiser activo en
top-right. Confirmar con ASIN + precio típico del catálogo del cliente.

### Gotcha 2 — Template Attribution ≠ Template SP
NO confundir con el bulk de Sponsored Products. Gotchas distintos. Ver
[[amazon-bulk-upload-guide]] para SP, este SOP para Attribution.

### Gotcha 3 — Template vacío rebota
Si subís el template Attribution sin llenar, Amazon usa las 3 filas ejemplo
(abc322, abc224, abc834) y tira "Campaign already exists in a different
advertiser". Limpiar antes de subir.

### Gotcha 4 — Publisher difference Bulk vs Manual
- Bulk: dropdown "Facebook / Instagram" (combinado, 1 entrada)
- Manual: solo "Facebook" o solo "Instagram" (separado, 2 ad groups distintos
  para trackear ambos)

### Gotcha 5 ⭐ CRÍTICO — Bulk Beta no completa jerarquía
El bulk file procesa Campaign + Ad Groups + Products pero NO genera Ads/Tags.
Status "PRODUCTS_ADDED" es engañoso. Síntomas:
- Tab "Attribution tags" muestra "No Rows To Show"
- Tab "Channels/Publishers" muestra "No Rows To Show"
- CSV "Download all tags" sale vacío (solo headers)
- "New ad" dentro del Ad Group manda a crear campaign nueva
- NO se pueden agregar Ads manualmente al bulk roto

Solución: descartar la Campaign rota (queda zombie), crear nueva en Create
manually con sufijo -v2.

### Gotcha 6 — Campaigns Attribution permanentes
No se pueden eliminar. Solo archivar/pausar. Si una sale rota, crear nueva
con sufijo (-v2, -v3) y dejar la rota como zombie en la lista.

### Gotcha 7 — Parents rechazados
Amazon Attribution rechaza variation parents. Usar siempre child ASINs
específicos (ej: B0F6LDG3NK CR M Black, no parent B0F84637MJ).

### Gotcha 8 — Modelo cambia en 2026
Amazon migra de "last-touch puro" a "shopping-signal weighted" durante 2026.
Meta va a recibir menos crédito que en self-reported. Avisar al cliente
antes que compare ROAS Meta vs Amazon Attribution.

### Gotcha 9 — Productos no eligibles
Productos sin stock, sin foto, o sin precio no son elegibles para measurement.
Validar listings antes.

## Después de generar los tags

1. Descargar CSV con "Download all tags in CSV file"
2. Pasarle URLs trackeables al AM por Slack
3. Cliente reemplaza el link directo (amazon.com/dp/XXX) por la URL completa
   de attribution en sus ads de Meta
4. Validar 24-48hs post-deployment:
   - Campaign Attribution debería mostrar clicks en al menos 1 ad group
   - Si todo en 0 después de 48hs → cliente no deployó los links
5. Reportar semanalmente clicks + ATC + purchases atribuidas por canal

## Plan V0 → V1 → V2

**V0 (genérico):** 1 tag por ASIN por canal. Suficiente para validar flujo y
ver volumen por canal. Tiempo: ~20 min para 6 tags.

**V1 (granular):** 1 tag por ASIN por ad set específico del cliente (LAL 1%
vs LAL 5% vs Retargeting 30d vs Cold prospecting). Requiere que cliente pase
listado real de su Ads Manager o nos dé acceso lectura. Tiempo: ~1-2hs para
20-40 tags.

**V2 (multi-canal):** replicar V1 para Email, Google, TikTok, Influencers.
Cada canal = bloque nuevo de tags. Tiempo: variable según canales activos.

## Brand Referral Bonus (BRB)

Programa SEPARADO de Attribution. Requiere:
- Brand Registry activo (pre-requisito)
- Tags Attribution generados (este SOP)
- Enrollment manual en BRB program (advertising.amazon.com → Programs → BRB)
- Amazon rebate hasta 10% del sale price sobre ventas atribuidas
- Crédito aparece en cuenta del seller

Sin BRB enrollment, las ventas se trackean pero el cliente deja el 10% sobre
la mesa. Para volúmenes Meta típicos, esto puede ser $5-15K/mes.

## Referencias

- [[MB]] — primera implementación documentada (2026-05-22)
- [[amazon-bulk-upload-guide]] — gotchas del OTRO bulk (Sponsored Products),
  NO confundir
- [[STATE-agencia]] — registro de uso por cliente
- [[MB_Impacto_Trafico_Externo_Marzo2026]] — caso de negocio que motivó este
  setup (M&B push externo 27-29/03 = $13K sin atribuir)

## Histórico

- **2026-05-22** — creado en sesión ad hoc M&B (Lenin asistiendo Agustín).
  6 tags Meta Facebook generados como V0. Primer intento via bulk Beta falló
  parcialmente (Gotcha #5 descubierto). Recreado vía Create manually
  exitosamente. Pendientes para próxima ronda: bulk Instagram + Email + BRB
  enrollment cliente + V1 granular.
