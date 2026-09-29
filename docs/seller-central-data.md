# Datos de Seller Central en agency-db

Dónde se guardan el Business Report y el Search Query Performance (SQP) de cada cuenta, subidos a mano o traídos
por la SP-API, y la única forma de escribirlos. Es la base de IT-60 a IT-69.

- Migración: `deploy/db/migrations/023_seller_reports.sql`
- Cliente Python: `core/seller_reports/` (`columns.py`, `periods.py`, `store.py`)

## La cuenta

- **Una cuenta de Seller Central es la cuenta de Amazon Ads de un marketplace.** `seller_accounts` guarda
  `ads_entity_id` (el `cuenta_externa_id` de `integration_accounts`) y `marketplace_id` (el del profile), únicos
  juntos. Se crea la primera vez que alguien la pide con `seller_account_for_ads_profile(profile_id)`.
- **Solo cuentas seller.** Una cuenta vendor se rechaza (`not_a_seller`): Vendor Central no tiene Business Report.
- **El `selling_partner_id` queda nulo hasta verificarlo.** Que sea igual al entity id de Ads no está documentado.
  IT-65 lo completa al conectar la SP-API:
  - plan A: la cuenta cuyo `ads_entity_id` coincide con el id que manda Amazon;
  - plan B: el admin elige la cuenta.
  
  `set_selling_partner_id` lo carga a mano o lo borra (vuelve a nulo). Es único por marketplace.
- **La SP-API no crea cuentas: se engancha a la de Ads.** Un cliente sin Amazon Ads conectado no puede guardar datos
  de Seller Central hasta conectar Ads.
- `delete_seller_account` borra una cuenta que ya no tiene datos, junto con sus cargas y su historial.

## Datasets y período

| `dataset` | A mano | SP-API | Tabla | Una fila por | Período |
|---|---|---|---|---|---|
| `sales_traffic_daily` | BR By Date, vista Día | `salesAndTrafficByDate` DAY | `seller_sales_traffic_daily` | cuenta · día | el día |
| `sales_traffic_by_asin` | BR By Child, con su rango | `salesAndTrafficByAsin` CHILD | `seller_sales_traffic_by_asin` | cuenta · rango · ASIN hijo | el rango exacto |
| `sqp_brand_view` | SQP Brand View | — | `seller_search_query_performance` | cuenta · marca · período · búsqueda | semana o mes |
| `sqp_asin_view` | SQP ASIN View | SQP (solo ASIN View), WEEK o MONTH | `seller_search_query_performance` | cuenta · ASIN · período · búsqueda | semana o mes |

- **By Date:** cada día es su propio período, así que un archivo pisa los días que trae (7 días pisan 7, 14 pisan
  14). Un BR exportado por semana o por mes no se puede partir en días sin inventar cuánto se vendió cada día:
  se pide el diario, que está en el mismo reporte.
- **By Child:** el archivo trae un solo total por ASIN para todo el rango y no dice qué pasó cada día. Solo se pisan
  dos cargas con el mismo rango exacto; rangos que se solapan conviven (un total del 1 al 14 y otro del 8 al 21 son
  dos datos distintos). La SP-API sí puede traerlo día por día (un rango de un día), y con días se arma cualquier
  rango: las cantidades se suman y los porcentajes se recalculan desde ellas (CVR = unidades / sesiones; Buy Box %
  ponderado por páginas vistas). Al leer (IT-64), el orden es:
  1. los días de la API, si cubren todo el rango;
  2. si no, el total manual de ese rango exacto;
  3. si no hay ninguno, se avisa que falta.

  Falta comprobar con datos reales que la suma de días da lo mismo que un archivo del mismo rango (IT-69).
- **SQP:** la semana va de domingo a sábado y el mes es el calendario (la base rechaza otras fechas de inicio;
  `periods.py` las calcula). Semana y mes conviven porque son datos distintos. Brand View va por marca (una cuenta
  puede tener varias) y ASIN View por ASIN. El trimestral queda afuera.
- **Días:** son los del marketplace, como los cuenta Seller Central. Falta comprobar que coinciden con los días de
  Amazon Ads antes de cruzarlos (IT-69).

## Qué se guarda

- **Nombres de columna:** son los de la SP-API en snake_case (`core/seller_reports/columns.py`). Un parser de archivo
  mapea sus encabezados a esos nombres; un documento de la SP-API se aplana a ellos.
- **Nulo quiere decir que el export no trajo esa columna, nunca 0.** El BR se exporta con columnas parciales (hay
  cuentas sin Buy Box).
- **SQP:** se guardan los conteos tal como vienen. No se guardan shares ni tasas, porque según el JSON schema oficial
  se calculan exactos:
  - share = propio / total;
  - tasa = total / volumen de búsqueda.

  `own_*` es la marca en Brand View y el ASIN en ASIN View; `total_*` es todo el mercado de esa búsqueda.
- **BR:** se guardan conteos, montos y solo los porcentajes que no se pueden recalcular: Buy Box %, y Session % y
  Page Views % por ASIN, que van contra el total de la cuenta. CVR, promedios y tasa de reembolso se calculan al leer.

Algunos encabezados verificados (el resto sigue el mismo patrón; los parsers de IT-60 e IT-61 lo confirman con
archivos reales):

| Encabezado del archivo | Columna |
|---|---|
| `(Child) ASIN` / `(Parent) ASIN` / `Title` | `child_asin` / `parent_asin` / `title` |
| `Sessions - Total` / `Sessions - Total - B2B` | `sessions` / `sessions_b2b` |
| `Session Percentage - Total` | `session_percentage` |
| `Page Views - Total` / `Page Views Percentage - Total` | `page_views` / `page_views_percentage` |
| `Featured Offer (Buy Box) Percentage` | `buy_box_percentage` |
| `Units Ordered` / `Ordered Product Sales` / `Total Order Items` | `units_ordered` / `ordered_product_sales` / `total_order_items` |
| `Unit Session Percentage` | no se guarda: `units_ordered / sessions` |
| `Search Query` / `Search Query Score` / `Search Query Volume` | `search_query` / `search_query_score` / `search_query_volume` |
| `Impressions: Total Count` / `Impressions: Brand Count` | `total_impression_count` / `own_impression_count` |
| `Clicks: Total Count` / `Clicks: Brand Count` | `total_click_count` / `own_click_count` |
| `Purchases: Total Count` / `Purchases: Brand Count` | `total_purchase_count` / `own_purchase_count` |
| `Purchases: Brand Share %` / `Purchases: Purchase Rate %` | no se guardan: se derivan |

## Escribir

- **Quién llama a qué:**
  - el app usa `upload_seller_sales_traffic_daily`, `upload_seller_sales_traffic_by_asin` y
    `upload_seller_search_query_performance`, con fuente `manual`;
  - el worker de SP-API usa `save_seller_*`, con fuente `sp_api`;
  - todas terminan en `seller_report_save`.

  En Python: `open_seller_report_store()` en el app; el worker arma `SellerReportStore` con su JWT.
- **Qué pasa con cada período:**
  - vacío: `inserted`;
  - mismo contenido: `unchanged`. No escribe ni crea una carga, aunque los montos vengan escritos distinto
    (`199.9` o `"199.90"`): se compara el hash de las filas ya convertidas a sus tipos. Una columna entera
    rechaza `12.0`; `SellerReportStore` manda como `12` los decimales enteros que deja pandas;
  - SP-API sobre cualquier cosa: `replaced`;
  - manual sobre manual: `replaced` (el archivo más nuevo gana);
  - manual sobre SP-API: `conflict`, salvo `p_replace_api_data = true`.
- **Un solo `conflict` sin confirmar frena toda la carga.** No se escribe nada y cada período dice qué pasaría.
  "Guardar solo lo que falta" es reenviar sin esos períodos.
- **Vista previa:** toda escritura acepta `p_preview = true`. En ese modo no escribe nada y devuelve, por período:
  - lo que hay hoy: fuente, quién lo subió, cuándo, archivo y filas;
  - qué pasaría con ese período.

  Es lo que muestra la modal de confirmación (IT-62).
- **Rechazos:** la base rechaza con el error `seller_report.<código>` y un detalle. `SellerReportStore` lo convierte
  en `SellerReportRejected(code, detail)`. Los códigos son:
  - de cuenta: `unknown_account`, `unknown_ads_profile`, `not_a_seller`, `profile_without_marketplace`,
    `invalid_selling_partner_id`, `selling_partner_id_in_use`, `account_has_data`;
  - de filas: `rows_not_an_array`, `no_rows`, `row_not_an_object`, `unknown_columns`, `invalid_value`,
    `missing_day`, `duplicate_day`, `invalid_asin`, `duplicate_asin`, `missing_search_query`,
    `duplicate_search_query`;
  - de período: `missing_range`, `reversed_range`, `future_period`, `missing_period`, `week_not_on_sunday`,
    `month_not_on_first_day`, `invalid_period_type`;
  - otros: `invalid_view`, `invalid_brand_or_asin`, `invalid_source`, `invalid_dataset`, `invalid_range`,
    `unknown_load`.
- **Concurrencia:** las escrituras de una misma cuenta se hacen de a una. Dos subidas simultáneas no se mezclan: la
  segunda espera y ve lo que dejó la primera.

## Volver atrás y borrar

- Cada escritura (guardar o borrar) es una fila de `seller_report_loads`. Cada cambio de un período guarda la versión
  que tenía antes (o que estaba vacío) en `seller_report_period_history`.
- **Volver atrás:** `revert_seller_report_load(load)` deja cada período que la carga todavía tiene como estaba antes
  de ella: vuelve a su versión anterior (`restored`) o queda vacío (`removed`).
  - Un período que otra carga cambió después no se toca (`skipped`).
  - Se puede volver atrás varias veces, en orden.
  - Repetirlo no hace nada.
  - Volver atrás no se puede deshacer.
- **Borrar:** `delete_seller_report_periods(cuenta, dataset, marca o ASIN, desde, hasta)` borra los períodos que caen
  enteros dentro del rango.
  - Es una carga más, así que se deshace igual.
  - Borrar datos de SP-API pide la misma confirmación que pisarlos.
- **Historial:** crece con cada cambio y hoy no se poda.

## Permisos

- Nadie escribe las tablas directamente. `web_user` e `integ_worker` solo las leen, y toda escritura pasa por
  funciones `security definer` con `search_path = public, pg_temp`.
- `web_user` puede llamar a:
  - los `upload_*`;
  - `delete_seller_report_periods` y `revert_seller_report_load`;
  - `seller_account_for_ads_profile`, `set_selling_partner_id` y `delete_seller_account`.
- `integ_worker` puede llamar a los `save_*` y a `seller_account_for_ads_profile`.

## Cómo se prueba

- `tests/test_seller_reports_*.py` corren sin Postgres: prueban el contrato del SQL, el cliente contra un PostgREST
  simulado y los períodos.
- `deploy/db/e2e_selfhosted_db.py`, con `INTEGRATIONS_WORKER_JWT`, recorre todo por PostgREST y al terminar borra lo
  que creó: subir, subir lo mismo, SP-API encima, conflicto, confirmar, volver atrás, borrar y deshacer el borrado.
  Sin ese JWT, el bloque se saltea.
- `deploy/db/smoke_readonly.py` incluye las siete tablas.

## Lo que sigue

- **IT-60 e IT-61:** parsers de BR y SQP que producen estas columnas y llaman a los `upload_*`.
- **IT-62:** el selector y la modal que muestra la vista previa, con volver atrás y borrar.
- **IT-63 e IT-64:** lecturas en los módulos y cálculo de shares, tasas y CVR.
- **IT-65:** completar `selling_partner_id` al conectar.
- **IT-66 e IT-67:** worker que escribe con los `save_*`.
- **IT-69:** verificar que el día coincide con el de Ads y que el By Child diario reconstruye un rango.
