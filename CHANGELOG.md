# CHANGELOG — Agency OS Capybaras

Registro de cambios, mejoras y decisiones de diseño del PPC Manager.

---

## [Unreleased]

### Changed — Los agentes de IA usan Claude Opus 5.5 (2026-09-23)

**Por qué.** Opus 5.5 es el Opus que sucede a Opus 5, y hasta ahora no se podía pedir: el provider traía Claude Code
2.1.251 y la API contesta 400 a `claude-opus-5-5` desde cualquier Claude Code anterior al 2.1.280.

**Ahora.** Los ocho agentes de `ai/agents/` (Search Term Report, Search Query Performance, Bid Optimizer, Bulk
Campañas, Análisis de Funnel, PPC Insights, DataDive y el chat) piden `claude-opus-5-5`. El effort sigue explícito en
`high`: en Opus 5.5 el valor por defecto bajó a `medium`. Necesita desplegado antes el provider con `claude-agent-sdk`
0.2.158 (Claude Code 2.1.280); contra el anterior, las pestañas de IA y el chat fallan con ese 400.

### Added — La estructura de las campañas SP sale de los listados de Amazon Ads (ad groups, placements y negativos), para cualquier módulo y el chat (2026-09-22)

**Por qué.** Un reporte sólo trae lo que tuvo actividad, y la estructura de una cuenta es también lo que no corre.
Medido en producción el 22/09: el 85,2% de los keywords y targets SP habilitados de la lista no tiene ninguna fila de
`spTargeting` en 60 días (el 98,9% de los pausados), y de las campañas SP no aparecen en `spCampaigns` el 0,4% de las
habilitadas y el 93,5% de las pausadas. Ese mismo día, en la última lista de cada cuenta, 15.339 de 146.004 targets SP
habilitados o pausados (el 10,5%) se listaban sin bid propio: usan el de su ad group, que no se guardaba. Atom11, PPC Audit y Análisis Cruzado necesitan
la estructura entera.

**Ahora.** La estructura sale de los listados de Amazon Ads, una foto por día, y las métricas siguen saliendo de los
reportes. Dos solicitudes nuevas por cuenta y por día, desde las 03:00 como las otras listas (migración 018, aditiva):
`sp_ad_groups` guarda cada ad group con su estado y su bid por defecto, y `sp_negatives` los negativos de keyword y de
producto, de campaña y de ad group (cuatro listados). La foto de campañas que ya se bajaba guarda además los ajustes
por placement (top of search, páginas de producto, resto de la búsqueda y Amazon Business): 0 es sin ajuste, vacío es
que no se sabe. El bid efectivo —el propio del keyword o target o, si no tiene, el default de su ad group— se calcula
en un solo lugar, la vista `ads_target_bid`. Target Graduation, en Bulk Campañas y en `idle_targets` del chat, usa ese
bid y deja afuera los targets de ad groups SP listados como pausados; un ad group que nunca se listó cuenta como
habilitado, y la leyenda de la página lo dice sólo cuando la cuenta ya tiene ad groups SP guardados. Cualquier módulo
lee la estructura con `StructureProvider(rest).sp_structure(...)`: `rows` con los nombres de la base, `frame` con los
headers del Bulk File (Placement queda con el código de la API: no hay una descarga real con que compararlo) y
`listed_at` con la hora del último listado de cada tipo; `campaign_ids` la acota a esas campañas (`p_campaign_ids`
en la RPC), y `sp_structure_counts(...)` cuenta cada tipo sin traer las filas. El chat la consulta con
`campaign_structure`: campañas con presupuesto, estrategia y placements, ad groups, keywords y product targets con su
bid efectivo (también los que no tuvieron tráfico), product ads y negativos, con la hora del último listado; los
conteos salen de la base, un tipo que se listó sin filas cuenta 0 en vez de leerse como sin sincronizar, y con una
campaña se lee sólo lo de esa campaña. Los listados registran su duración real en el Registro de solicitudes: antes
figuraban con ~0 s.

**Negativos por partes.** Una cuenta grande no entra en un tick: medido el 22/09 contra la API real, Shapermint US tiene
371.407 negativos SP en 374 páginas de 1000 (311 de negativos de keyword de ad group, 49 de campaña, 11 de producto de
ad group y 3 de campaña), a 0,95 s por página: unos 6 minutos de una vez, con la alerta de worker callado a los 5,
~285 MB en un worker de 768 MB, y el listado de una vez se corta a las 200 páginas. Dermaglós US tiene 1.181 en 4
pedidos. `sp_negatives` los lista entonces por partes: 40 páginas por tick entre todas las cuentas, cada página guardada
apenas llega y el job anotando dónde quedó (`integration_sync_jobs.progress`), con lo guardado hasta ahí a la vista en
el Registro de solicitudes; Shapermint US necesita al menos 10 partes. Una corrida a medias conserva su lugar en la
cola y retoma en el tick siguiente antes que lo planificado después. Cuando termina el cuarto listado,
`ads_listing_snapshot` guarda la corrida, y recién ahí lo que no vio deja de contar: mientras corre se sigue viendo la
anterior, con su hora, y antes de la primera la cuenta figura sin negativos sincronizados. Un 429 la deja en su última
parte guardada; cualquier otro fallo, o una página que devuelve el token que se le mandó, la hace empezar de nuevo en el
reintento. Una sola corrida por cuenta a la vez: un reintento mientras otra está a medias cierra sin listar. El chat no
lee enteros los negativos de una cuenta grande: pasados 5000 en el alcance los pide de a una campaña, y la respuesta
trae el conteo y cómo acotar. Con esa respuesta el chat ya no le pregunta al AM por dónde cortar: elige lo activo que
más pesa en el período (la campaña habilitada con más gasto), dice qué criterio usó y cuánto quedó afuera. Es una regla
nueva de las compartidas del chat (`ai/agents/_shared/chat.md`), así que vale en todos los agentes para cualquier
herramienta que vuelva sin filas, sólo con el conteo y un pedido de acotar; entre las del PPC Manager, hoy la única que
lo hace es la de negativos. Una respuesta paginada, que sí trae filas, sigue la regla de los listados: el chat muestra
lo que llegó y dice dónde cortó.

**Páginas que entran en el chat.** El provider de IA corta cada respuesta de las herramientas del PPC Manager a los
20.000 caracteres (`PPC_TOOL_RESULT_MAX_CHARS`, sin override también en producción), y las filas iban primero. Medido el
23/09: la página por defecto de `campaign_structure` pasaba ese corte en campañas, keywords, product targets y negativos
(de 22.000 a 34.000 caracteres), y `campaign_health`, que ya estaba en producción, en 32.679. El chat veía entre el 60% y
el 95% de las filas y perdía el total, la nota de paginación y el contexto: de una página de 50 negativos listaba 47, sin
saber cuántos había ni desde dónde seguir. Ahora cada página (`services/mcp_server/limits.py`) lleva sólo las filas que
entran en 14.000 caracteres, medidas como las escribe el SDK, con `showing` y el offset siguiente exactos, y el total y
la nota van antes de las filas. Vale para todas las herramientas: después del cambio la página más grande medida fue de
15.327 caracteres, y el chat pagina los negativos de a 30 sin saltearse ninguno.

**Costo, estimado el 22/09 (no medido).** `sp_ad_groups`: ≈ 52-66 POST por día entre las 52 cuentas (1 página cada
1000 ad groups en las 27 con ad groups SP, y 1 pedido vacío en las otras 25). `sp_negatives`: 208 POST por día como
mínimo, 4 listados por cuenta, y sólo Shapermint US suma 374 (medido). Los placements no suman pedidos y no hay
reportes nuevos: el cupo de 3 en vuelo no se toca. Medido el 22-23/09 en local contra la API real (sólo lectura): la
corrida de negativos de Shapermint US fueron 10 partes y 342 s, con 371.482 negativos y 45 MB de memoria como máximo, y
`sp_structure_counts` tarda 0,45 s en esa cuenta. La duración en producción se ve en el Registro de solicitudes después
de la primera noche.

**Qué queda afuera.** SB y SD; los ad groups, targets, anuncios y negativos archivados, que no se listan (las campañas
archivadas sí); y los consumidores: Atom11, PPC Audit y Análisis Cruzado todavía no la leen, son IT-42, IT-44 e IT-51.

**Deploy.** La foto de campañas ya escribe las columnas de placement y los listados nuevos sus tablas. Jenkins levanta
la imagen antes de «DB migrate», en el mismo pipeline: lo que corra en esa ventana sin la 018 falla y se reintenta a los
5 minutos. Es aditiva y la imagen anterior funciona sobre ella. Si hay que volver a la imagen anterior con la 018 ya
aplicada, cancelar antes los jobs de `sp_ad_groups` y `sp_negatives` en cola: la imagen anterior no conoce esos tipos, los
marca fallidos y cada cuenta queda con una alerta por 24 h. Los reportes y los análisis IA no dependen de la
columna nueva de los jobs: sólo un listado pausado la escribe al cerrar. El smoke de la base prueba `ads_ad_group`,
`ads_negative`, `ads_listing_snapshot`, `ads_campaign.placement_top_pct` e `integration_sync_jobs.progress`.

### Changed — Las campañas SP piden la última semana cada noche y 60 días los domingos (2026-09-22)

**Por qué.** Cada noche se volvían a pedir los 65 días de campañas SP de cada cuenta: 3 reportes por cuenta, 156 con
las 52 cuentas desde las 22 nuevas del 21/09, por un cupo de 3 reportes en vuelo compartido por todas las regiones. El
22/09 Amazon tardó de 16 a 26 minutos por reporte y a las 13:53 de Argentina quedaban 54 reportes de 18 cuentas de
Norteamérica: Bulk Campañas y el Funnel mostraban sus campañas hasta el 20/09 mientras el STR ya llegaba al 21/09.

**Ahora.** La primera vez se cargan los 65 días; después cada noche pide los últimos 7 días (1 reporte) y el domingo,
cuando nadie trabaja, los 60 días que el picker puede mostrar (2 reportes). Son 52 reportes por noche de lunes a
sábado en vez de 156, y 104 los domingos.
Una cuenta tiene su historial si una solicitud de 60 días o más terminó en los últimos 15 días: las cuentas que ya
estaban no lo vuelven a cargar, y una que pasó dos semanas sin domingo lo carga de nuevo. El período de Bulk
Campañas, el Funnel, el análisis IA y el MCP sale de los 65 días hacia atrás desde el último día sincronizado, no de
la ventana de la última solicitud, así que no se achica a una semana.

### Added — Análisis de Funnel con datos de Amazon Ads, y el chat recuerda lo que el AM miró en cada módulo (2026-09-21)

**Funnel sin archivos.** El Search Term Report y las campañas llegan de Amazon Ads con una sola elección de cuenta,
país y período: el picker del STR elige y `render_campaigns_for` lee las campañas de esa misma cuenta y ventana, con
su propia frescura. El STR y el Campaign CSV subidos a mano quedan como respaldo. Con datos de la API el cruce va por
Campaign ID (una campaña renombrada en el período ya no se parte en «activa sin tráfico» y «no encontrada») y cubre
sólo Sponsored Products, también con archivo: el reporte de search terms no trae términos de SB ni de SD, que antes
salían como campañas activas sin tráfico. Las columnas se detectan como en M2, así que Harvesting ya no se corta en
cuentas vendor (atribución de 14 días) y el archivo acepta el CSV nuevo de la consola. La página pasa a cuatro tabs
(Cobertura, Campañas sugeridas, Harvesting, Análisis IA); las campañas sugeridas traen clicks, gasto, órdenes y ventas
y van por gasto; en Harvesting el CVR se recalcula del total del término, en vez de sumar los porcentajes de sus filas,
y la columna «En campaña activa» dice si el término todavía corre en alguna campaña habilitada.

**Análisis IA del Funnel.** Agente nuevo `ai/agents/funnel` (filas `F01…` en una sola numeración para harvest,
términos de campañas inactivas y campañas activas sin tráfico): corre en memoria, a pedido, y se comparte con el chat
con la cuenta y el país. Sus Parámetros traen las órdenes y ventas de los search terms de campañas activas y de las
pausadas o inexistentes: en la prueba local, sin ese reparto, la IA afirmó que casi todo lo vendido salía de campañas
apagadas cuando la mayor parte venía de una activa.

**Picker en el teléfono.** El encabezado de los bloques (`band_header_html`) y la fila de acciones del picker bajan
de línea a 375px en vez de pisarse o empujar «Subir archivo manualmente» fuera de la pantalla; cuando entran en una
línea se ven como antes. Afecta a todas las páginas con el picker, a Cuentas conectadas y al Registro de solicitudes.

**El chat recuerda la navegación.** Cada módulo publica lo que tiene seleccionado —cuenta, fechas, fuente, valores y
la llamada al MCP que trae sus cifras— y la nota de cada pregunta lleva la de la pantalla abierta y las de los últimos
módulos visitados (`core/chat/screen_selection.py`). No entra en la clave de sesión: cambiar de cuenta o de período no
reinicia la conversación. Publican su selección el Funnel, el Search Term Report, el Bid Optimizer, PPC Insights,
Bulk Campañas, SQP y DataDive. El Registro de solicitudes toma la cuenta de esa selección cuando la página no comparte
un análisis: antes, una pregunta en PPC Insights, en Bulk Campañas o en el Bid Optimizer con otro target quedaba sin
cuenta. Los chips de `campaign_health` e `idle_targets` dicen qué leyeron («Diagnóstico de campañas», «Targets sin
impresiones») y un test exige etiqueta para toda herramienta nueva del MCP.

**El MCP expone lo que calcula cada módulo, con sus mismas reglas.** Herramientas nuevas: `funnel_coverage`,
`search_term_candidates`, `bid_suggestions` y `asin_health`; `campaign_health` e `idle_targets` aceptan
`date_from`/`date_to`, y `campaign_health` los umbrales de la pantalla. Con fechas, los días provisorios siguen
siendo los últimos sincronizados de la cuenta: una ventana que termina antes no tiene ninguno. Una suite de 30
preguntas al chat mostró lo que el modelo deducía mal y ahora le llega como dato: el estado de la campaña de cada
search term (lo sacaba del nombre, que puede ser viejo), los totales de cada lista (los sumaba), la regla con sus
umbrales de cada diagnóstico de Bulk Campañas (la reconstruía al revés), el día de hoy en la zona de cada cuenta (usaba
el UTC del servidor y decía que faltaban días) y si los parámetros son los guardados o los valores por defecto. Cada
negativo de `search_term_candidates` dice además si entra al bulk del Search Term Report y, si no, la razón del
módulo, con `totals_in_bulk` para lo que suma el bulk: el chat prometía liberar el gasto de negativos que la página
nunca sube (de una campaña pausada, de la keyword propia del ad group o de una keyword Exact). Las filas del STR de
`get_analysis` traen el estado que su campaña tiene hoy, y `finished_at` sale en la hora de la cuenta. El
prompt del chat suma reglas para no armar cocientes ni juicios sin referencia. Para que la imagen del MCP pueda leer esas
reglas sin agentes ni openpyxl, se separaron del armado de los payloads IA sin cambiar ningún resultado
(`core/search_term/candidates.py`, `core/bid_optimizer/bids.py`, los parámetros de PPC Insights en `asin_health.py`,
el límite de texto de negativos en `core/bulk/keyword_text.py`); un test fija la huella de los payloads de STR, Bid
Optimizer y PPC Insights para que los análisis guardados se sigan encontrando.

### Added — PPC Insights con datos de Amazon Ads: picker, ASIN por producto anunciado, análisis IA y chat (2026-09-21)

PPC Insights deja de pedir el Search Term Report a mano: lo toma del picker de Amazon Ads (cuenta, país y período),
con la carga manual como alternativa, que se sigue leyendo con el parser propio del módulo. SQP, BR y Campaign CSV
quedan como uploaders opcionales. "Generar Insights" ahora conserva los resultados mientras no cambian los datos, los
montos van en la moneda de la cuenta y el target y el precio se cargan de los parámetros guardados de la cuenta.

El reporte de search terms de la API no trae el ASIN anunciado. Una solicitud nueva, `sp_product_ads`, guarda
`/sp/productAds/list` en `ads_product_ad` (migración 017), y cada término toma el ASIN de su ad group cuando anuncia
uno solo; si anuncia varios, o el listado no vio el ad group, el del nombre de la campaña aunque el ad group no lo
anuncie (las cuentas que nombran por familia ponen el ASIN de la familia en el nombre y anuncian los hijos). Nunca se
reparte gasto entre ASINs: lo que queda sin ASIN se muestra aparte, el KPI de gasto dice «Spend en cards: X de Y» y
una card tomada del nombre de campaña en ad groups de varios ASINs dice cuántos agrupa. Medido en la base local el
21/09, la cuenta de mayor gasto pasa de 0% (una sola fila con la cuenta entera) a 87,8% del gasto atribuido a un ASIN.

La nueva pestaña Análisis IA usa un agente propio (`ai/agents/ppc_insights`, filas `P01…`): con datos de la API el
análisis se guarda, lo pide el AM y lo corre el worker (nunca se planifica solo), con «Recalcular» cuando lo que está
en pantalla no es lo analizado; con archivo corre en memoria. Se comparte con el chat, y el MCP suma `ppc_insights` a
`list_analyses`/`get_analysis` y un `breakdown` por ASIN. La lógica por ASIN se movió sin cambios a `core/ppc_insights/`.

### Changed — Dashboard Global, Case Study Studio y Proposal Studio pasan a sus paquetes en `core/` (2026-09-19)

Lote 5 de la reorganización de `core/` por feature. Solo cambian rutas: `core/agency_dashboard.py`,
`agency_dashboard_export.py` y `agency_dashboard_format.py` → `core/agency_dashboard/` (`dashboard`, `export`,
`format`); `core/case_study_html.py` → `core/case_studies/renderer.py` y `core/case_study_pdf.py` →
`core/case_studies/pdf.py`; y los cuatro `core/proposal_*.py` → `core/proposals/` (`paths`, `pdf`, `persistence`,
`renderer`). El HTML del case study queda como `renderer.py` y no `html.py` porque el archivo hace `import html` de
la stdlib. Un ajuste para que nada cambie de comportamiento: `_REPO_ROOT` de `core/proposals/renderer.py` sube un
nivel más desde `__file__`, así los templates de `templates/proposal_modules/` y el catálogo de `data/sales/` se
siguen resolviendo contra la raíz del repo. No hay shims en las rutas viejas: se actualizaron los imports, los scripts
de M29 (`inject_v*_demo`, `parse_seed_proposals`, `discover_m29_template_instantiation`), el E2E de la base
self-hosted y los docs y comentarios que nombraban los archivos. Ninguna imagen de `services/` copia estos archivos.

### Changed — `core/chat/ads_account_picker.py` pasa a llamarse `core/chat/ads_scope.py` (2026-09-19)

El nombre decía "picker", pero el módulo no elige nada en la UI (su docstring lo aclara): resuelve con qué credencial
y en qué región abre sesión cada turno del chat contra Amazon Ads, y `request_scope()` devuelve el `ads_scope` del
turno. Queda en `core/chat/` porque su único consumidor es `core/chat/app_chat.py`, y además usa Streamlit y
`ai.config`, que no van en `core/amazon_ads/` (el lado worker, que se copia entero a la imagen del MCP). Solo cambian
el nombre y los imports.

### Changed — Bid Optimizer, Bulk Campañas, Business Report, DataDive, forecast, innovación y supply pasan a sus paquetes en `core/` (2026-09-18)

Lotes 2 a 4 de la reorganización de `core/` por feature. Solo cambian rutas: `core/bid_analysis.py` →
`core/bid_optimizer/analysis.py`, `core/campaign_analysis.py` → `core/bulk_campaigns/analysis.py`,
`core/business_report.py` → `core/business_report/parser.py`, `core/datadive.py` → `core/datadive/client.py`,
`core/ads_account_picker.py` → `core/chat/ads_account_picker.py` (lo usa sólo el chat),
`core/forecast_persistence.py` → `core/forecast/persistence.py`, `core/innovation_persistence.py` →
`core/innovation/persistence.py`, y los siete `core/supply_*.py` → `core/supply/` (`paths`, `persistence`, `oc_import`,
`metrics`, `politica`, `seasonality`, `indices`). Dos ajustes para que nada cambie de comportamiento: `_BIZ_DIR` sube un
nivel más desde `__file__`, así sigue apuntando a `data/business_report` en la raíz del repo; y los tests que leen el
código de `oc_import` y `politica` ahora prohíben el texto `persistence` en lugar de `supply_persistence`, así siguen
atrapando ese import con el nombre nuevo. Ninguna imagen de `services/` copia estos archivos, y las huellas de los
análisis no dependen de la ruta del módulo.

### Changed — Search terms y Bulk File pasan a sus paquetes en `core/` (2026-09-18)

Primer lote de la reorganización de `core/` por feature. Solo cambian rutas: `core/search_term_frame.py`,
`search_term_file.py`, `search_term_analysis.py` y `search_term_negatives.py` → `core/search_term/`
(`frame`, `file`, `analysis`, `negatives`), y `core/bulk_export.py` / `core/bulk_parser.py` → `core/bulk/`
(`export`, `parser`). No hay shims en las rutas viejas: se actualizaron los imports, los `mock.patch` de los tests y el
`COPY` del Dockerfile del MCP, que ahora copia `core/search_term/` con su `__init__.py`. Las huellas de los análisis
no dependen de la ruta del módulo, así que no se re-encola ningún análisis.

### Added — Cada turno del chat queda guardado en la base (2026-09-18)

Cada pregunta al chat de la app deja una fila en `chat_turns` (migración 016): la fecha, el usuario, la página, la
cuenta de Amazon Ads que esa página tenía cargada, la pregunta, la respuesta tal como la leyó el AM (o el error, si
el turno falló), las herramientas que llamó el modelo, el modelo pedido y el costo que informa el provider. Los turnos
de una misma sesión del navegador comparten `conversation_id`. La app sólo puede insertar: no lee, no modifica ni
borra esas filas, y el smoke de la base lo verifica en cada deploy. Se leen por SQL en la VPS. Arranca vacía: lo que
ya estaba en el log de la app no se carga.

La cuenta es la de la página, no la que consultó el modelo: el chat elige la cuenta en cada llamada a Amazon Ads y la
app no ve ese argumento. El modelo es el que la app pide; si el provider cae a otro, la fila no lo muestra. El costo es
la estimación a precio de API del SDK.

Qué cambia en el código: todo el chat pasa a `core/chat/` — `core/ai_chat.py` → `core/chat/panel.py`,
`core/app_chat.py` → `core/chat/app_chat.py`, `core/chat_components/` → `core/chat/components/`,
`core/chat_skills.py` → `core/chat/skills.py` — más `core/chat/turns.py` (nuevo, la escritura en la base).
`floating_chat(on_turn_finished=)` avisa cada turno terminado, `ChatReply` suma `model` y `cost_usd`,
`mount_app_chat(page, username)` recibe el usuario que resuelve `app.py`, y Bid Optimizer le pasa al chat el
`profile_id` de su cuenta, como ya hacían STR y Bulk Campañas.

### Fixed — Lo que encontraron el E2E de #19 en producción y los archivos manuales de Love To Dream MX (2026-09-18)

**Shapermint AU sin SB.** El E2E en producción de #19 encontró el pedido `sb_entities` de Shapermint AU fallido
después de 3 intentos: Amazon responde a `/sb/targets/list` con 400 "Marketplace A39IBJ37TRP1C6 do not have access to
Sponsored Brands product targeting functionality". Al fallar la lista entera, la cuenta quedaba sin sus campañas SB y
sin sus reportes. Ahora una función de SB que el marketplace no ofrece (targets o themes) se lista vacía y el resto
de la lista se guarda; cualquier otro 400 sigue fallando el pedido.

**El Campaign CSV manual en pesos (o en otra moneda con prefijo) ya no da gasto y ventas en cero.** Venía de antes
de la API: M6 limpiaba los montos quitando sólo `$` y `,`, así que "MX$5,796.55" (el export de Love To Dream MX) no
se leía como número y quedaba en 0. Con ese CSV no había ninguna campaña en PAUSAR y el gasto recuperable daba 0;
ahora el mismo archivo da MX$13.823,97 de gasto, MX$86.208,83 de ventas y 9 campañas en PAUSAR. Vale para "CA$",
"£" y "€". Los datos de la API no pasaban por ese problema porque llegan como números.

**La estrategia de puja con los nombres del Campaign CSV.** Con datos de la API, SP mostraba «Dynamic bids - down
only» y «Dynamic bids - up and down» (los nombres del bulk) y SB manual «Custom bid adjustments»; el Campaign CSV que
M6 leía a mano escribe «Dynamic bidding (down only)», «Dynamic bidding (up and down)» y, en SB manual, «Fixed bids»
(Love To Dream MX: 41, 1 y 2 campañas). Ahora la API muestra esos. SB con puja automática y SD siguen con sus
nombres: el export de LTD no tiene ese caso de SB, y en SD escribe «Dynamic bidding (up and down)» en campañas que
optimizan para conversiones, con dos campañas no alcanza para saber la regla. El análisis IA de campañas lee estos
nombres, así que se regenera una vez en cada cuenta.

**`breakdown` por producto desde search terms.** El chat en producción pidió `breakdown` por producto con
`source=search_terms` para comparar SP entre las dos fuentes, y la herramienta lo rechazaba. Ahora devuelve un solo
grupo, Sponsored Products, sumado de los search terms, y la respuesta por producto de siempre dice cómo pedirlo.

### Added — Bulk Campañas, su análisis IA y el chat suman Sponsored Brands, Sponsored Display y Target Graduation desde la API (2026-09-18)

**SB y SD en la misma tabla.** Con datos de Amazon Ads, M6 muestra las campañas de Sponsored Brands y Sponsored
Display junto a las de Sponsored Products, con la columna Type y un filtro por producto que alcanza a la Vista
General y al Campaign Analyzer. Las compras y ventas de SB y SD son las de Campaign Manager (14 días, clicks o
vistas), como con el CSV; las columnas «(clicks)» muestran lo comparable con SP.

**Las campañas SB del formato anterior tienen métricas.** Los reportes v3 de SB están en preview y no traen las
campañas con isMultiAdGroupsEnabled=false (en Shapermint US, 51 de 736 y el 31% del gasto de SB del 16/09). Las trae
el reporte v2 de SB (`/v2/hsa/campaigns/report`), que se pide un día por reporte sólo para las cuentas que las tienen:
medido el 16/09, sus cifras coinciden con las de v3 en las 587 campañas que tienen los dos. Hasta que carga su
historia, esas campañas se listan aparte y nunca se diagnostican como fantasmas. Sus targets siguen sin reporte, así
que quedan fuera de Target Graduation.

**Estrategia de puja con los nombres de Campaign Manager.** SP muestra «Dynamic bids - down only», «Dynamic bids - up
and down» o «Fixed bids» en vez del código de la API; SB, «Automated bidding» o «Custom bid adjustments»; SD, la
optimización de sus ad groups («Optimize for page visits», «conversions», «reach»).

**Target Graduation vuelve con la API.** Los targets habilitados, de campañas habilitadas, sin una impresión en el
período, de los tres productos, con su campaña, texto, tipo, match type y bid. Con el filtro por producto, el
«N de M» cuenta sólo los targets de ese producto.

**El análisis IA cubre los tres productos.** Un análisis por cuenta, como el Campaign Analyzer en «Todos»: cada fila
dice su producto y trae las ventas sólo por clicks para comparar SB y SD con SP. Espera a que cierren también los
pedidos de campañas SB y SD, y se vuelve a pedir cuando terminan. Una cuenta sólo con SP lee lo mismo que antes.

**El chat también.** `campaign_health` trae las campañas de los tres productos y filtra por `product`;
`idle_targets` (nueva) da Target Graduation; `daily_metrics`, `breakdown` (por campaña, portfolio y el nuevo
«producto») y `accounts_overview` suman SP, SB y SD de los reportes de campaña. Las cifras de SP sumadas de los
search terms, que es lo que daban antes, siguen con `source=search_terms`: sólo traen términos con clicks, así que
tienen muchas menos impresiones (Shapermint US, del 11 al 17/09: 8.916.572 contra 16.781.001 de los reportes de
campaña; gasto, clicks, ventas y órdenes a menos de 0,5%). Cada respuesta dice de qué fuente salen sus cifras y cómo
pedir la otra, y el chat da las dos cuando le preguntan por impresiones o CTR de SP o lo comparan con el Search Term
Report. `breakdown` por tipo de match o search term sigue en los search terms de SP.

**Sincronización.** Tres listas diarias (keywords y targets SP; campañas, keywords, targets y themes SB; campañas, ad
groups y targets SD) y seis reportes: spTargeting, sbCampaigns, sbTargeting, sdCampaigns, sdTargeting y el v2 de SB.
Cada reporte carga su historia una vez (65 días; 60 en SB, lo que Amazon guarda) y después pide los últimos 14 días
cada noche. Los de SB y SD sólo se piden si la lista del día encontró campañas de ese producto, y el v2 sólo si
encontró campañas del formato anterior.

**Deploy.** Migración 015, aditiva: tablas nuevas y funciones nuevas; lo de SP no cambia. Da al worker de análisis
(ai_worker) lectura de las campañas SB y SD. Entre "Deploy" y "DB migrate" M6 muestra sólo SP, las listas nuevas
fallan y se reintentan solas, y las herramientas del chat que suman campañas contestan con error.

### Fixed — Un ajuste negativo de Amazon ya no tumba la sincronización de una cuenta (2026-09-18)

**Shapermint US se quedó sin métricas de campañas** el día del deploy de #18: el reporte de un mes traía una fila con
-2 impresiones (campaña pausada, 30/07, todo lo demás en 0) y el parser rechazaba el tramo entero, así que el pedido
fallaba y volvía a fallar cada noche mientras ese día siguiera dentro de los 65 sincronizados. Amazon descuenta tráfico
inválido de días ya reportados (hasta 30 días después) y en un día sin nada más el neto puede quedar bajo cero.

Ahora un valor bajo cero en una métrica sumable se guarda como 0 (el día no tuvo actividad) y queda en el log del
worker; el presupuesto del día o el share bajo cero quedan como desconocidos. Lo que no es un número finito sigue
rechazando el reporte. Vale para campañas y search terms. Guardar el negativo tal cual rompía una docena de lecturas
que suman estos valores como conteos (un fantasma pasaba a OK, un costo negativo daba ESCALAR).

### Added — Bulk Campañas con análisis IA, señales y lectura desde el chat (2026-09-18)

**Pestaña "Análisis IA" en M6.** Con datos de Amazon Ads, el worker de análisis genera solo el análisis de los
últimos 7 días de cada cuenta con sus parámetros guardados (target ACoS, gasto para pausar, órdenes para escalar), como
el del STR: la IA explica o pone en duda el diagnóstico de hasta 12 campañas con una causa, un veredicto
(actuar, esperar, investigar) y su confianza, y escribe la síntesis de la cuenta. Nunca cambia el diagnóstico. Con
archivo manual la pestaña lo explica y no llama a la IA.

**Señales aparte del semáforo.** El Campaign Analyzer suma la columna «Señales»: "Limitada por presupuesto" (vende
dentro del target y se quedó sin presupuesto 3 días o más), "Nueva" (menos de 14 días) y "Baja visibilidad" (menos
de 10% de Top of Search en una campaña para pausar o revisar). Los últimos 2 días del período se marcan provisorios.
El reporte de campañas ahora pide el presupuesto del día y el share de Top of Search.

**El chat ve las campañas.** `campaign_health` (MCP) devuelve las campañas de una cuenta clasificadas como en M6,
incluidas las que no tuvieron clicks, que `breakdown` no ve. El análisis guardado se lee con `list_analyses` y
`get_analysis` (filas `C01…`).

**Una sola regla.** El semáforo pasó a `core/amazon_ads/campaign_analyzer.py`, sin cambiar sus resultados: lo usan la
página, el worker y el MCP.

**Deploy.** Migración 014 (columnas `budget_amount` y `top_of_search_is`, `campaigns_between` con las entradas de las
señales, `bulk_campaigns` en la lista de módulos con análisis, permiso de lectura de campañas para el worker de
análisis). Si sale en el mismo deploy que la 013, "DB migrate" las aplica en orden y vale la nota de la 013. Si sale
después, en los segundos entre "Deploy" y "DB migrate" la página no muestra señales, el worker de análisis registra un
error al planificar campañas (todavía no puede leerlas) y los días que guarde el sincronizador quedan sin share de Top
of Search hasta la noche siguiente, que reescribe los 65 días.

### Changed — El chat ya no recibe las cuentas pegadas: las lee por el MCP (2026-09-18)

**Cada sesión del chat deja de cargar la síntesis de todas las cuentas.** El documento "Últimos análisis de Search
Terms guardados por cuenta" (unos 34.000 caracteres con 11 cuentas, con tope de 100.000 y creciendo con cada una)
sale del flujo, sin respaldo: el turno lleva sólo el análisis que el AM tiene en pantalla y el resto se lee por el
servidor MCP cuando la pregunta lo pide. Sale también la lectura de la base que se hacía en cada turno
(`core/ai_analysis/account_summaries.py`).

**Cruzar cuentas es una llamada.** `accounts_overview` (nuevo) da los totales en vivo de todas las cuentas, cada una
en su moneda; `list_analyses` suma la situación, el target de ACoS y el tipo y urgencia de cada riesgo de cada
análisis; `get_analysis` da cada fila con su row_id y la síntesis con el término al lado de cada id.

### Added — Bulk Campañas lee las campañas de la cuenta de Amazon Ads (2026-09-17)

**M6 sin Campaign CSV.** Bulk Campañas muestra las campañas de Sponsored Products de la cuenta conectada con sus
métricas del período elegido (7, 14, 30 o 60 días, o un rango). Salen de dos solicitudes nuevas del sincronizador,
una vez por día y por perfil desde las 03:00 de su hora: la foto de campañas (`/sp/campaigns/list`: nombre, estado,
presupuesto, estrategia, portfolio) y las métricas diarias del reporte `spCampaigns` de los últimos 65 días, en 3
tramos. Una campaña sin actividad aparece igual, en cero: el universo sale de la foto, no del reporte. El archivo
manual queda como alternativa.

**Frescura con día y hora.** El selector usa los controles del STR y su pill sale de las solicitudes de campañas
("Al día · actualizado hoy HH:MM", "Primera carga en curso", "Sin datos todavía"). El Registro de solicitudes muestra
"Campañas" y "Métricas de campañas", con los tramos del reporte en el detalle.

**Diferencias con el CSV.** Estado de hasta el día anterior, métricas hasta ayer, 65 días sincronizados (el período
llega a 60), solo Sponsored Products, archivadas afuera y 17 columnas en la Vista General.

**Deploy.** El pipeline aplica la migración 013 en "DB migrate", segundos después de levantar la imagen nueva: los
ticks del sincronizador de esa ventana fallan en el pedido de reportes y en los pasos de campañas, y se recuperan solos
(las solicitudes de campañas reintentan a los 5 min). Nunca correr la imagen vieja y la nueva del sincronizador a la
vez: la vieja toma tramos sin mirar su tipo.

### Added — El chat lee la app por MCP y grafica solo (2026-09-17)

**El chat consulta la app en vez de recibirla pegada.** Un servidor MCP de sólo lectura (`services/mcp_server`,
servicio `mcp-server` con imagen propia) expone qué cuentas hay, qué análisis de IA están guardados y qué dicen,
los search terms de mayor gasto, la serie diaria de una cuenta o campaña (`daily_metrics`, migración 012) y los
totales agrupados por campaña, portfolio, tipo de match o término (`breakdown`). El provider lo abre por la red
privada; cualquier cliente MCP con el token también puede usarlo.

**Tortas, barras y tendencias con datos reales.** Nuevo componente `pie` (de 2 a 6 partes; el porcentaje lo
calcula el panel). La guía prefiere un gráfico a una tabla de cifras cuando el gráfico las muestra, y la tendencia
sale de la serie diaria, no sólo de valores que tipea el AM. Medido con dos baterías de 24 preguntas: 23/24 en la
de cuentas y wording distintos.

**Los chips dicen de dónde salió el dato y qué falló.** "Serie diaria · Agency OS", "Desglose · Agency OS"… y una
fuente cuyas consultas fallaron todas se marca "· falló" (por ejemplo, un "unauthorized" de Amazon Ads).

**Depende del provider.** Necesita capybaras-ai-provider con el puente `ppc_manager` y el evento `tool_result`:
se despliega antes. En la VPS: `MCP_TOKEN` en el `.env` de ppc-manager y `PPC_MCP_URL` / `PPC_MCP_TOKEN` en el
del provider.

### Added — El chat responde con componentes, y la IA corre en Opus 5 (2026-09-17)

**Las respuestas del chat se dibujan.** El modelo contesta con una lista de componentes que el panel dibuja en orden:
texto, tarjetas de indicadores, tabla, barras, tendencia, alerta y acción. Lee un catálogo con para qué sirve cada
uno, cómo se ve y sus límites, y elige cuáles usar; el provider lo obliga a responder en esa forma. Mientras
trabaja, el panel muestra qué fuentes está leyendo (Campañas · Amazon Ads, Keywords · DataDive…). Una respuesta
que no llega en componentes se sigue mostrando como prosa.

**Los análisis y el chat pasan a Claude Opus 5 con esfuerzo alto.** Search Term Report, Search Query Performance,
DataDive y el chat de la app dejan `claude-fable-5-1` con esfuerzo `low`; la espera de 3600 s no cambia.

**Depende del provider.** Necesita la rama `feat/chat-components` de capybaras-ai-provider (deja pasar la salida
estructurada en un turno con herramientas y avisa cada herramienta que el modelo pide): se despliega antes.

Qué cambia en el código: `core/chat_components/` (nuevo: un módulo por componente; `CATALOG` genera el schema y
la guía), `ai/runtime.stream_followup` y `ChatReply`, `ai/client.ask_stream`, `core/ai_chat.py` (dibuja los
componentes y los chips en vivo), `ai/agents/_shared/chat.md` y el encabezado de los cuatro agentes.

### Added — Un chat IA en toda la app (2026-09-15)

**El chat está en todas las pantallas, desde Inicio.** Una sola burbuja, para todos los usuarios, con un hilo que
acompaña al AM de una pantalla a otra. Reemplaza a los tres chats que tenían Search Term Report, Search Query
Performance y DataDive. Con `AI_ENABLED=0` no aparece.

**Elige la fuente según la pregunta.** Lo atiende un agente nuevo (`ai/agents/orchestrator/`) que tiene a mano los
análisis de la app, las herramientas del MCP de Amazon Ads (estructura de las cuentas en vivo) y las de DataDive.
De cada análisis abierto en la sesión recibe los documentos que leyó su agente y la lectura de la IA, unida por
row_id; además, la síntesis del último análisis de Search Terms guardado de cada cuenta de Amazon Ads conectada,
para contestar sobre un cliente que el AM no abrió. Sabe qué pantalla está abierta y si un análisis está
desactualizado, generándose o falló, y un análisis que termina mientras el AM está en otra pantalla le llega igual.
Cuando cambian los análisis del AM abre otra sesión con el provider y le pasa la conversación visible, así no
olvida lo que ya se habló; el análisis guardado nuevo de otra cuenta no la reinicia. Las filas se citan con su
término: en las síntesis sin tabla el row_id se reemplaza por el término, y cada respuesta queda anotada con los
análisis del momento, así navegar a otro cliente no le pega términos ajenos.

**Arreglos que venían en el camino.** El chat de DataDive nunca anotaba el término detrás de un K12 (leía la clave
de sesión equivocada); SQP con un archivo sin las columnas de impresiones, sin filas analizables o con la IA apagada
tiraba `UnboundLocalError`; el CSS del panel del chat cambiaba el aspecto de todos los popovers de la app.

Qué cambia en el código: `core/app_chat.py` (nuevo), `ai/agents/orchestrator/`, `ai/agents/synthesis_text.py`,
`ai/agents/row_annotation.py` (`annotate_row_ids` sale de `core/ai_tab`, que lo reexporta),
`ai/agents/{sqp,datadive}/chat_document.py`, `core/ai_analysis/account_summaries.py`,
`AiAnalysisStore.latest_by_subject` (y `history` trae los records), `core/ai_tab.publish_analysis_to_chat`
(reemplaza a `mount_analysis_chat`), `ai/runtime.ask_followup(note=, thread=)`,
`core/ai_chat.floating_chat(session_key=, turn=)` (el turno se arma al enviar, no en cada render) sin los
parámetros del chat por módulo, y el montaje al final de `app.py`. Sin migraciones ni cambios en el provider.

### Added — El Search Term Report se actualiza solo desde Amazon Ads (2026-09-14)

**M2 lee los search terms por API.** Con cuentas de Amazon Ads conectadas, el módulo arranca con el bloque "Datos de
Amazon Ads": cuenta, país y período, un indicador de qué tan frescos están los datos y el botón "Actualizar ahora".
Subir el archivo sigue estando, detrás de "Subir archivo manualmente", y ahora también entiende el CSV nuevo de la
consola ("Total cost", varias cuentas en un archivo, una cuenta con filas en dos monedas separada por moneda). La
moneda es un indicador (la del perfil de Amazon o la del archivo), sin conversión.

**Refresco todos los días, con reintentos el mismo día.** El servicio `ads-sync-worker` corre siempre prendido y cada
minuto avanza las solicitudes guardadas en la base: diaria de 14 días a las 03:00 de la hora del perfil, 42 días los
domingos, carga inicial de 65 días apenas aparece una cuenta (también las ya conectadas al deployar) y reintentos
hasta las 23:00 del perfil. Los reportes se piden en tramos de 14 días (7 en perfiles muy grandes), se retoman por
`reportId` después de un corte,
cada día se reemplaza en una sola transacción con guarda anti-vaciado, y el crudo queda 180 días en el volumen
`ads_raw`. Los portfolios se resuelven de id a nombre.

**Registro de solicitudes (Sistema, sólo admin).** Historial de cada pedido a las cuentas conectadas con su estado,
detalle de intentos y errores, Reintentar/Cancelar (también solicitudes trabadas), y alertas (fallas, primera carga
fallida, datos atrasados, worker sin latido, autorizaciones rechazadas o por vencer) con punto en el menú. Es genérico
por proveedor.

**Bulk de negativos con IDs reales.** Con datos de API, Negatives Mining exporta el bulk a nivel ad group con los IDs
de campaña y ad group. Las reglas se alinearon a los invariantes del SOP: R4 pasa a "Bajar bid", R1 a "Revisar
manualmente", nada con órdenes (7 o 14 días) se negativiza, y quedan afuera (con motivo) origen Exact o Product
Targeting en el ad group, Exact activos, keywords propias, frases que bloquearían un término que convierte, texto que
Amazon rechaza, términos ASIN y campañas no habilitadas. Los portfolios RANKING y los sin nombre quedan afuera y se
liberan término por término. Con moneda distinta de USD el precio arranca vacío y el bulk espera a que se cargue.
Los `.xlsx` guardan los términos como texto. Pendiente de validación de PPC.

**M2 aguanta cuentas grandes.** Con 30 días de una cuenta grande (177.843 términos) la página se caía: el estilo de
pandas no dibuja más de 262.144 celdas, y además tardaba más de 3 minutos en armarse. Ahora las tablas muestran las 1.000 filas
más relevantes (con aviso y el Excel completo), el gráfico de dispersión los 2.000 términos de mayor gasto, y los Excel
de más de 5.000 filas se arman cuando se piden ("Preparar el archivo"). La clasificación de estados, harvest y las
guardas del bulk se calculan por columnas; el resultado es idéntico al anterior sobre datos reales. Con datos más
nuevos disponibles, cambiar el período ya no muestra filas nuevas con la etiqueta de la versión anterior: el selector
pasa a la versión nueva, así el Excel preparado y el análisis IA no quedan viejos.

**El análisis IA queda guardado y ligado a los datos.** Con datos de Amazon Ads, el análisis de M2 se genera
solo cuando llegan datos nuevos (servicio `ads-ai-worker`) y se guarda. Todos los usuarios ven el mismo, sin
esperar, y no se vuelve a generar mientras los datos y los parámetros no cambien. Si alguien cambia
parámetros, período o idioma, la pestaña no muestra un análisis viejo: ofrece "Generar análisis IA" y esos
parámetros quedan guardados para la cuenta. El chat arranca con el análisis vigente y los últimos tres de la
cuenta. Con archivo manual el análisis sigue en memoria y nunca llega a la base. Las cuentas en otra moneda
sin precio cargado también tienen análisis: sin la Regla 3 (gasto sin conversión) ni bids sugeridos, y la
pestaña lo avisa. El "Bid Sugerido" de harvest respeta el techo de INV-1 (nunca más que precio × target ACoS).

**Puente con la VPS.** `scripts/amazon_ads_bridge.py` re-sella en la VPS las autorizaciones de Amazon para la clave
local y las importa en el stack local, sin túnel ni URL nueva en Amazon.

Qué cambia en el código: migración `009_amazon_ads_sync.sql` (`integration_sync_jobs`, `ads_report_requests`,
`ads_profile_sync`, `ads_search_term_daily`, `ads_portfolios`, `integration_worker_heartbeats` y sus funciones),
migración `010_ai_analyses.sql` (`ai_analyses`, `ai_analysis_settings`, rol `ai_worker`, `claim_ai_jobs`,
`request_ai_analysis`, `save_ai_analysis_settings`), `ai/agent_call.py`, `core/search_term_analysis.py`,
`core/ai_analysis/`,
`core/amazon_ads/`, `core/integrations/{sync_jobs,sync_alerts}.py`, `core/{search_term_frame,search_term_file,
search_term_negatives,currency_format}.py`, `modules/pages/{search_term_source,request_log}.py`. Deploy:
`deploy/integrations/DEPLOY.md` §5c.

### Added — Los chats consultan el MCP oficial de Amazon Ads (2026-09-09)

**Cualquier persona con un chat en la app puede preguntarle a Amazon Ads.** En la barra
lateral aparece **Cuenta Amazon Ads**: un selector con las cuentas de clientes descubiertas
por el portal, una opción por marketplace, sólo las que cuelgan de una autorización activa.
Con una elegida, los chats de STR, SQP y DataDive reciben herramientas read-only del MCP
oficial de Amazon (campañas, ad groups, targets, presupuestos, estado, cuentas y reportes)
fijadas a esa cuenta y ese perfil. Sin cuenta elegida el chat sigue como antes, y el agente
sabe decir que falta elegirla.

**Las credenciales no salen del portal; quien las usa es el AI provider.** La app manda
sólo `ads_scope = {account_id, profile_id, requested_by}` y el secreto compartido
`CLAUDE_PROVIDER_SECRET` (header `X-Provider-Token`). `capybaras-ai-provider` lee el portal
con su propio rol `integ_provider` (migración 008: SELECT acotado por columna sobre cuentas,
autorizaciones y la credencial; UPDATE de `estado/last_error`; INSERT en auditoría), abre el
refresh token y el client secret con la clave de sellado del worker montada de sólo lectura,
acuña el access token de Login with Amazon y abre la sesión con el MCP de Amazon de la región
de la cuenta. Ni la app ni el subproceso de Claude ven un token. Si Amazon da por muerto el
grant, el provider marca la autorización `needs_reauth` y el chat lo dice en una línea.

**Qué cambia en el código.** `core/ads_account_picker.py` (opciones puras + selector de la
barra lateral, con caché de 2 min), `ai/runtime.usable_tools()` (Amazon Ads sólo con cuenta
elegida), `ai/client.ask(ads_scope=)` con el header, `core/ai_tab` → `core/ai_chat` pasan el
scope en cada turno; los agentes `str` y `sqp` declaran `tools: amazon_ads` y `datadive`
suma el perfil; cada prompt explica cuándo usar las herramientas, que `query_campaign`
exige `adProductFilter`, que los reportes son asincrónicos y que nada se modifica desde ahí.
Deploy: `deploy/integrations/DEPLOY.md` §2b (local) y §5b (VPS).

### Added — Amazon Ads entra al portal de integraciones (2026-09-09)

**El segundo proveedor del portal, con las mismas dos pantallas.** El admin carga el LwA
Client ID y el Client Secret en Integraciones, con la URL de autorización pre-cargada. En
Cuentas conectadas aparece la banda de Amazon Ads. Sin ingesta de reportes: este cambio es
sólo la autorización y el descubrimiento de cuentas.

**Quien autoriza es el empleado, no el cliente.** Confirmado con un AM: a cada persona de
Capybaras la invitan con su correo a Seller Central y a Ads de cada cliente. Un solo
consentimiento del empleado, con su usuario de Amazon, alcanza todas las cuentas de clientes
que ese usuario ve, en NA, EU y FE. Por eso Amazon separa dos cosas que en Mercado Libre
coinciden: la **autorización** (del empleado, con su token, su fecha de consentimiento y su
vencimiento) sigue en `integration_connections`; la **cuenta del cliente** (una por entidad
de Amazon, con región, países y tipo) vive en la tabla nueva `integration_accounts`
(migración 006). La pantalla muestra primero las autorizaciones y debajo las cuentas.

**Lo que Login with Amazon hace distinto, como datos del catálogo y no como `if slug ==`.**
`refresh_rotates=False`: el refresh devuelve siempre el mismo token y puede omitirlo, y el
worker lo conserva en vez de fallar. `refresh_token_lifetime_days=365`: los consentimientos
vencen a fecha fija; la pantalla avisa desde 45 días antes con el botón Reautorizar en la
fila, y `worker refresh` marca `needs_reauth` los vencidos. `discovers_accounts=True`: el
worker resuelve la identidad con un registro por proveedor (`/users/me` para Mercado Libre;
`/user/profile` más `/v2/profiles` en tres regiones para Amazon) en lugar de la rama
`slug == "mercado_libre"` que dejaba a cualquier otro proveedor con `cuenta_externa_id`
vacío, pisando la cuenta anterior en cada canje.

**El sellado pasa a v2 antes del primer token de Amazon.** `crypto.seal` era RSA-OAEP directo,
que con 4096 bits acepta 446 bytes de texto plano: entra un token de Mercado Libre (40
caracteres) y no uno de Amazon (450 típicos, 2048 según la doc). El fallo llegaba con el
code ya gastado. Ahora una clave AES-256-GCM aleatoria cifra el secreto y RSA envuelve la
clave; las filas `v1:` siguen abriéndose sin re-sellar nada.

**Tres cosas alrededor que este despliegue iba a pisar.** El punto ámbar del menú se pinta
también sobre Cuentas conectadas, que es donde está Reautorizar y donde entran los no-admin.
El diálogo de conectar abre un grant nuevo en cada click en vez de reutilizar un `state` ya
gastado en la segunda cuenta de la sesión. El receptor deja registrada en el grant una
negación o un `unknown scope` en vez de dejarlo vencer en silencio; para eso la migración
007 le da a `web_user` UPDATE sobre la columna `error`, que 002 no incluía y respondía 403 (lo
mostró el E2E). Y el cron de `grants` pasa a `*/2`, porque un code de Amazon vive 5 minutos.
Comando nuevo `worker discover` para que un cliente que invitó al empleado aparezca sin
reautorizar.

**Probado contra Amazon de verdad el 2026-09-09**, en el stack local con un túnel HTTPS
al callback: credencial sellada en v2, consentimiento con `advertising::campaign_management`
más `profile:user_id`, canje, 30 perfiles descubiertos en NA/EU/FE agrupados en 15 cuentas
de clientes, refresh sin rotación, `discover`, vencimiento a 45 y 365 días, reautorización
sobre la misma fila, y la negación registrada como `fallido`.

### Changed — El host de autorización de Mercado Libre sale de la credencial, no del código (2026-09-09)

**Una cuenta CBT no se podía conectar, y el error no decía por qué.** El catálogo tenía
`auth.mercadolibre.com.ar` clavado para todos. Mercado Libre no tiene un host único: es por
sitio, y Global Selling (CBT) ni siquiera es un sitio — autoriza en `global-selling.mercadolibre.com`,
otro host y otro path. Una agencia que opera cross-border armaba un link de consentimiento que
no llevaba a ningún lado.

**El país no se puede descubrir antes de consentir, y eso decide dónde va el dato.** `/users/me`
devuelve el `site_id`, pero necesita el token que el consentimiento produce; `/applications/$APP_ID`
también pide token; y `/sites`, que la documentación linkea como público, hoy responde 403. Como
Mercado Libre sólo acepta `authorization_code` y `refresh_token`, no hay forma de conseguir un token
sin que alguien autorice primero. Así que el host no es un atributo del vendedor: es de la app que
registró la agencia — exactamente lo que guarda la credencial del sistema, una vez, no por cuenta.

**El diálogo de conectar sigue sin pedir un solo campo.** El host lo elige el admin al cargar la
credencial, con las dos formas explicadas en el help. Una credencial guardada antes de que el campo
existiera sigue funcionando: si viene vacío, cae al valor del catálogo.

### Changed — Conectar una cuenta de Mercado Libre ya trae los datos, sin esperar a las 23:30 (2026-09-09)

**Conectar y ver eran dos momentos separados por hasta un día.** El canje del grant dejaba
la cuenta `Activa` y completamente vacía, porque los datos los traía únicamente el `ingest`
nocturno. El operador conectaba, entraba al módulo, y no había nada: una conexión que
funcionaba perfecto y no mostraba absolutamente nada hasta la mañana siguiente. Ahora la
misma corrida de `worker grants` que canjea el code sincroniza esa cuenta en el acto —
items, visitas, ventas y ads — y el módulo queda utilizable enseguida.

**Tenía que vivir en el worker y en ningún otro lado.** La tentación era dispararlo desde la
app al apretar Conectar, pero ni Streamlit ni el receptor tienen la clave privada de
sellado: viven fuera del volumen que la guarda, y esa separación es justamente lo que hace
que comprometer la app no entregue las credenciales de ningún cliente. Lo más que podrían
hacer es dejar una nota en una cola que este mismo worker tendría que drenar igual. El
primer sync corre donde ya está la clave.

**Un primer sync que falla no ensucia el canje.** Corre después de canjear todos los grants
de esa corrida y su error se loguea sin mover el exit code: la cuenta ya quedó conectada, y
hacer que el cron reporte como rota una conexión que anda porque un catálogo tardó era
mandar a alguien a arreglar algo que no estaba roto. El `ingest` de las 23:30 sigue siendo
el refresco diario y, ahora también, el reintento automático.

**La espera que queda es el intervalo del cron de `grants`**, no la noche entera. Con `*/5`
son minutos; bajarlo a `* * * * *` lo vuelve inmediato y sale barato, porque sin
autorizaciones pendientes el comando corta al toque sin tocar la API ni cargar el pipeline
de ingest.

### Added — Portal de integraciones: credenciales del sistema (M38) y cuentas de cliente (M37) (2026-09-03)

**Dos pantallas, porque son dos permisos y dos radios de impacto.**
- **`modules/pages/integrations.py` — `⚙️ Sistema → Integraciones`, sólo admin.** La
  *credencial del sistema*: una por integración, la API key de la agencia o el
  `client_id`/`client_secret` de la app OAuth. Si falla, se cae la integración para todos
  los clientes. Lista en bandas ordenadas por urgencia (`SIN PODER CONFIRMAR` ·
  `REQUIERE ATENCIÓN` · `SE PUEDE CARGAR` · `EN SERVICIO`); una banda sin filas no se
  dibuja, su ausencia es el mensaje. Arriba, un veredicto de dos líneas que contesta si
  hay algo roto y a qué cliente le pega.
- **`modules/pages/accounts.py` — `⚙️ Sistema → Cuentas conectadas`, todos los empleados.**
  La *cuenta conectada*: una por cliente, la autoriza el vendedor. Si falla, se cae ese
  cliente nada más. Vive en Sistema y no dentro de Mercado Libre justamente porque la
  autorización es transversal: cuando entre Amazon o Walmart se suman como bandas acá, y
  no hay que ir a buscarlas al módulo de cada marketplace.

**El permiso se comunica por ausencia.** Al usuario sin rol admin no le aparece un botón
deshabilitado: no le aparece el botón. Y ningún bloqueo se descubre después de tipear un
secreto — si falta la base o falta el sellado, eso es el estado visible de la fila.

**Conectar una cuenta no pide ningún campo.** El link de consentimiento se arma al abrir el
diálogo, y el nombre y el país de la cuenta los completa el worker desde `/users/me` de
Mercado Libre al cerrar el grant. Pedirle el slug de la agencia a quien conecta era pedirle
un dato que el proveedor ya sabe.

**Nunca se muestra un secreto enmascarado.** Un `sk-••••3f2a` insinúa que la app lo tiene y
no lo enseña, y eso es falso: va la huella de seis caracteres, que alcanza para que dos
personas confirmen que hablan de la misma clave.

- **`core/integrations/crypto.py`** — sellado asimétrico RSA-4096-OAEP-SHA256 con prefijo
  de versión. La app sella con la pública y no puede volver a abrir; la privada la genera
  `worker keys` en su primera corrida y vive en el volumen del worker. Nadie la tipea.
- **`deploy/db/migrations/002_integrations.sql`** — cuatro tablas con GRANTs por columna:
  `web_user` puede INSERT/UPDATE sobre las columnas selladas y no las tiene en ningún
  SELECT. Arranca con un `revoke` explícito porque `deploy/db/schema.sql:143` le da CRUD
  sobre toda tabla futura a la app.
- **`core/integrations/{catalog,roles,store,oauth,worker,lookup,notice}.py`** — catálogo
  estático (sumar una integración es una entrada de datos, no código), resolución de rol
  que **no** confía en `AGENCY_OS_LOCAL_MODE`, store PostgREST que escribe con
  `Prefer: return=minimal` (pedir la representación fuerza un SELECT y devuelve 403), y
  flujo OAuth con PKCE S256.
- **`services/integrations_receiver/`** — callback OAuth y webhooks MELI en un FastAPI
  aparte, detrás de Caddy en `/oauth/*` y `/notifications`. Sella el code y lo deja en la
  base; nunca abre nada. Streamlit no ve un code y el receptor no ve en qué página estaba
  el usuario.
- **DataDive lee del portal** — `core/datadive.py` resuelve la key en orden env → portal →
  `st.secrets`, así que cargarla desde la pantalla la pone en uso sin tocar `.env`.

### Added — Puente con la API de Mercado Libre (M36) (2026-09-03)
- **`core/meli_api/{transport,ingest,worker}.py`** — cliente con retry/backoff que honra
  `Retry-After`, refresca el token ante un 401 y no reintenta lo que no corresponde;
  ingesta de items, visitas, órdenes y métricas de ads; y un worker con CLI
  (`ingest [--client=SLUG]`) pensado para cron.
- **`modules/mercado_libre/api_bridge.py`** — el módulo M36 pasa a leer de la base en vez
  de esperar un Excel subido a mano, sin cambiar sus tres vistas.
- **Migraciones `003_meli_api.sql` y `004_meli_ads_unique.sql`** — identidades, corridas de
  ingesta, snapshots de publicaciones, serie diaria de rendimiento y de ads.
- **Cron de ingesta 1 vez al día a las 23:30** — las métricas del día quedan firmes cuando
  MELI cierra su ventana, así que el AM abre el módulo a la mañana con el día anterior
  completo.

### Added — Sistema de diseño e idioma unificados (`core/ui/`) (2026-09-03)
- **`core/ui/palette.py`** — única fuente de la paleta y de los parciales de CSS que usan
  las pantallas nuevas y el sidebar. Antes cada página repetía sus propios hex y un cambio
  de color había que rastrearlo archivo por archivo; ahora se toca en un lugar. Las dos
  pantallas de esta feature no tienen un solo hex propio.
- **`core/ui/sidebar.py`** — el CSS del riel oscuro sale de `app.py` (548 → 328 líneas) a un
  `string.Template` que sustituye las constantes de la paleta.
- **`core/ui/i18n.py`** — catálogo es/en de 168 claves con plurales y slots de formato
  verificados por paridad. El toggle del sidebar ahora **cambia la interfaz**, no sólo el
  idioma de salida de los tabs IA: pantallas migradas, sidebar completo y shell. `t()`
  nunca levanta excepción — una clave desconocida se devuelve tal cual.
- **El toggle se reseteaba solo, y la causa no era el catálogo.** Streamlit arma el id de un
  widget con sus propios argumentos: `radio.py:323` mete `label`, las `options` pasadas por
  `format_func` y `help` en el hash. El toggle traducía los tres, así que en el rerun
  siguiente al click —el primero cuyo sidebar ya está en inglés— el radio se registraba con
  otro id, perdía su valor guardado y caía al default, escribiendo `"Español"` encima de la
  elección. Se veía como la interfaz en inglés y el check en español. Ahora el widget es
  invariante al idioma (label constante y colapsado, opciones en endónimo, sin `help`) y la
  etiqueta traducida se dibuja al lado. `tests/test_language_toggle.py` fija las dos mitades:
  el comportamiento y el invariante del id — verificado que los 3 tests fallan contra la
  construcción vieja y pasan contra la nueva.

### Fixed — Deploy: lo que habría roto el primer push a main (2026-09-03)
- **El container `app` cargaba secretos que no le tocan.** `env_file: .env` inyectaba el
  archivo entero, así que Streamlit —el único servicio expuesto a internet— tenía
  `POSTGRES_PASSWORD`, `PGRST_JWT_SECRET` y `INTEGRATIONS_WORKER_JWT`. Con el secreto de
  firma, quien comprometa la app puede firmarse un token `role=integ_worker` y leer las
  columnas selladas: el sellado asimétrico dejaba de proteger nada. Ahora cada servicio
  nombra sólo sus variables y `.env` no lo monta nadie. Verificado dentro del container:
  los tres ausentes, y presentes las que la app sí necesita.
- **`.env.integrations` no era una fuente de interpolación.** Compose lee `${...}` sólo de
  `.env`, pero el instructivo mandaba a poner ahí variables declaradas `${VAR:?}` — el
  stack no arrancaba. Queda un solo archivo (`deploy/integrations/env.example`), y el orden
  de instalación de DEPLOY.md dejó de pedir el paso 3 antes del 4 que lo habilita.
- **El CD nunca reconstruía `integrations-receiver`.** Tenía `build:` sin `image:`, así que
  se quedaba con un nombre implícito estable y `up -d` lo daba por al día. Reproducido:
  `up -d --build` construyó la imagen nueva y dejó corriendo la vieja. Como el receptor
  copia `core/integrations/`, eso es deriva de versión silenciosa contra la app. Ahora
  lleva `image: ppc-manager-receiver:${IMAGE_TAG}` y CI construye las dos imágenes con el
  mismo tag.
- **Los webhooks de MELI se perdían en silencio** (`005_notifications_insert.sql`). `003`
  dejó a `web_user` con sólo `select` sobre `meli_notifications` y el receptor corre con
  ese rol: PostgREST devolvía 403, el receptor lo logueaba y le contestaba 200 a MELI
  igual. Reproducido y arreglado con un GRANT por columna. De paso, el duplicado legítimo
  se detecta por status 409 y no por texto de excepción, que con `return=minimal` nunca
  llega.
- **`migrate.sh` no lo llamaba nadie** — nueva etapa `DB migrate` entre `Deploy` y
  `Health gate`. Y su guardia era un falso positivo: `docker compose ps --status running`
  sale 0 aunque el servicio no exista, así que en un host sin overlay de base no se
  salteaba, fallaba.
- **El smoke de base podía pasar sin base.** Salía 0 si no había `SUPABASE_URL`, incluso en
  un deploy que sí declara el overlay. Ahora acepta `--require` y el pipeline se lo pasa
  cuando el compose tiene `postgrest`. Cubre las 10 tablas nuevas pidiendo la PK y no `*`:
  un `select *` sobre una tabla con columna sellada devuelve 403 por diseño.
- **El health gate miraba un solo container** — ahora exige `ppc-manager` y
  `integrations-receiver` sanos, así que un callback OAuth roto rompe el deploy en vez de
  reportar verde mientras cada consentimiento devuelve 502.
- **El `/health` documentado era un falso verde** — Caddy sólo rutea `/oauth/*` y
  `/notifications` al receptor, así que ese curl lo contestaba Streamlit. El chequeo pasa
  a `docker inspect`.
- **`pgadmin` iba a producción** — quedó bajo `profiles: ["dev"]`. Verificado: 6 servicios
  en el perfil por defecto.
- **El backup no incluía el volumen `integrations_keys`** — con la clave privada perdida,
  ninguna credencial sellada se puede volver a abrir. Agregado con su propia rotación.

### Added — Análisis IA en STR (M2) y SQP (M3) sobre la plataforma `ai/` (2026-09-01)
- **M2 STR — tab Análisis IA sobre `core/ai_tab`** — reemplaza el botón legacy con `core/ai_analyze` por la plataforma reusable: el análisis se dispara solo al cargar el archivo, se marca como desactualizado si cambian los parámetros y ofrece Reintentar si falla. El agente `ai/agents/str/` recibe los KPIs, el agregado por campaña (top 40 por spend, o por clicks si el export no trae costo), los candidatos a negativizar (Alta/Media, top 120) y a harvest (top 60) con los mismos valores de los tabs 1-3, y opina fila por fila (`razon`, `categoria`, `advertencia`) más diagnósticos por campaña y la síntesis canónica. Chat flotante de repreguntas sobre el mismo análisis. Exports de la consola nueva sin columna de costo: `cost_detected=False`, ranking por clicks y caveat declarado en la síntesis.
- **M3 SQP — señales deterministas + tab Análisis IA** — capa aditiva solo para la IA (`_compute_funnel_signals`, `_compute_account_rollup`): cascada de shares en 4 etapas con Cart Adds, índices marca-vs-mercado, brechas de precio por etapa con bandas fijas, gate de evidencia, visibilidad, gemas, defensa de marca (piso 80%), oportunidad en dólares sobre compras reales y pre-flags de riesgo. Las tabs 1-3 y sus cálculos no cambian. El agente `ai/agents/sqp/` diagnostica las 40 queries de mayor prioridad con taxonomías cerradas (`funnel_diagnosis`, `price_causality`, `action`, `confidence`) y emite la síntesis canónica con los riesgos exactamente iguales a los pre-flags. Input propio: brand terms (prefill con la marca detectada).
- **Toggle de idioma en el sidebar** (`app_lang`) — los textos impresos de los tabs IA se condicionan a Español/English.
- **Tests** — `tests/test_sqp_signals.py` (anti-placebo, bordes, oráculo de integridad contra los % del export, filas de display), `tests/test_sqp_ai_context.py` y `tests/test_str_ai_context.py` (contrato de cada agente, digest, runtime con transporte falso), `tests/test_agent_prompts.py` (reglas de lectura idénticas en los tres prompts). E2E headless contra el ai-provider real con los archivos reales de STR y SQP: cobertura 40/40, 2/2 y 4/4 filas, enums, síntesis, chat.

### Changed — Legibilidad de la salida IA (plataforma, afecta STR, SQP y DataDive)
- **Títulos de sección en la síntesis** — la lista numerada de acciones salía sin título y "Mediano plazo" no se distinguía del cuerpo; ahora cada bloque abre con un encabezado con horizonte explícito ("Acciones sugeridas para esta semana", "Mediano plazo · 2 a 4 semanas", "Riesgos") y el tooltip aclara que son sugerencias de la IA y el AM decide.
- **Nombres legibles en la prosa del SQP** — el prompt pedía "campo=valor" y el modelo copiaba nombres de columna (`pur_t`, `imp_b`, `is_invisible`: 200+ en 40 filas). Ahora lleva un glosario columna → nombre llano (es/en), formato de conteos con miles y shares con %, y una red determinista (`humanize_fields` + `_SQP_FIELD_NAMES`) por si el modelo se desliza. Medido en la corrida real: 0 nombres de columna.
- **Ids visibles y anotados** — la síntesis cita filas como N07, H59 o Q03 que la pantalla no mostraba. La tabla de opiniones imprime el id delante del término (N/H en STR, Q en SQP, K en los gaps de DataDive) y la prosa de síntesis, resumen ejecutivo y chat se anota con el término detrás del id ("H59 (press on nails short almond)"), primera mención por texto y sin duplicar cuando el modelo ya lo escribió.
- **Reglas de lectura compartidas en los tres prompts** — la situación se escribe para un AM junior: primera oración sin cifras ni tabla, conceptos técnicos traducidos, sin nombres internos del sistema (rollup, shares ponderados, etapa dominante de fuga, cobertura), una o dos cifras por oración; el resumen ejecutivo para Slack es la única excepción. La spec de `situation` del SQP pasó de enumerar siete cifras del rollup a tres oraciones con rol fijo (qué pasa, evidencia, tipo de problema).

### Added — Integración API DataDive + Análisis IA en M21 (2026-09-01)
- **`core/datadive.py`** — cliente REST read-only de la API de DataDive (`GET /v1/niches` paginado, `GET /v1/niches/{id}/keywords`, `GET /v1/quota`) con retry/backoff honrando `Retry-After` (espejo de la semántica de `core/ads_api`), errores tipados en español y `keywords_to_mkl_df()` que normaliza el JSON al shape canónico de `parse_mkl` (relevancy 0-1 → escala UI ×10, `suggestedBid.median` centavos → dólares, `asinRanks` null → NaN, Launch Score = 0.0 porque el endpoint no lo expone). La key se lee de `DATADIVE_API_KEY` (env) con fallback a `st.secrets["datadive"]`; sin key la feature queda apagada y el módulo es idéntico a antes.
- **M21 tab 1 — fuente API** — radio `Archivo | API DataDive` (solo con key configurada), selector de niche ordenado por `latestResearchDate` con label `nicheLabel · marketplace`, botón "Traer de DataDive" con refresh targeted del cache (`_api_mkl.clear(niche_id)`). Cache compartido de proceso `@st.cache_data(ttl=3600)`. El DataFrame entra al tab por las mismas variables que un archivo subido — filtros, gaps y export intactos.
- **Agente IA `ai/agents/datadive/`** — primer agente de la plataforma `ai/` en main. Analiza la MKL (clusters de intención, gaps priorizados, síntesis canónica) sobre el top 120 por SV vía `core/ai_tab`, con chat flotante de repreguntas (`core/ai_chat`) montado fuera de los tabs.
- **`scripts/smoke_datadive_api.py`** — smoke read-only con key real: quota, niches, contrato de /keywords con distribución de relevancy, y sondas a `/roots` y `/ranking-juices` (candidatos a Launch Score en fase posterior).

- **M21 tabs 2 y 5 — fuente API** — con Fuente en API DataDive, el tab Competitors carga automáticamente los competidores del niche traído en el tab 1 (`GET /v1/niches/{id}/competitors`, normalizado a los labels del export con `competitors_to_df`; validado 9/9 ASINs idénticos al xlsx real), y Competitor Intel compara dos niches elegidos por selector (`Traer ambos de DataDive`). El análisis IA del tab 1 suma un documento de competidores (con la mediana del niche) cuando hay datos, de cualquiera de las dos fuentes.
- **Launch Score sostenible sin vigilancia** — la réplica de la fórmula deja de ser un pasivo a monitorear, con tres redes: (1) `scripts/check_launch_score_drift.py` corre en CI —stage `Launch Score drift`, en cada build y por cron semanal que no deploya— y **no necesita credenciales** porque el bundle del frontend y el spec de DataDive son públicos; marca UNSTABLE, nunca rompe el build. (2) `_launch_score_of` usa el campo oficial (`launchScore`) apenas DataDive lo exponga, así el fix definitivo se aplica solo. (3) `launch_score_drifted` audita contra cada export por archivo que suba el AM (0 falsos positivos sobre las 419 filas del export real), como respaldo — con el modo API por default los archivos casi no se suben, así que no alcanza sola.
- **Launch Score vía API** — el endpoint no lo expone, pero la fórmula vive en el bundle público del frontend de DataDive: `round(SV × 0.003 / relevancy)` si relevancy ≥ 0.4 ("estimated weekly sales needed to reach page one"). `keywords_to_mkl_df` la replica (`_launch_score`, con el redondeo de `Math.round`): validada **419/419 exacta** contra el export real. El MKL por API queda idéntico al export en todas las columnas. Semántica corroborada por el KB oficial de DataDive (jul-2026); el smoke incluye un **tripwire de drift** (verifica la fórmula en el bundle vivo y si `launchScore` apareció en el spec oficial).
- **M21 tabs 3 y 4 — Rank Radar por API (fase 2)** — selector de rank radar (46 de la org) + rango 30/60/90 días → serie diaria de rank orgánico server-side vía `GET /v1/niches/rank-radars[/{id}]`, normalizada al shape de `parse_rank_radar` (`rank_radar_to_df`: Search Term/SV/Relevance/Median Rank + columnas fecha). Reemplaza el hack de snapshots en session_state; el tab 4 reusa el radar traído para volatilidad + cruce SQP.
- **Chat con tools MCP de DataDive (fase 3)** — el agente `datadive` declara `tools: datadive` en su frontmatter y las repreguntas del chat viajan con `tools:["datadive"]` + `max_turns 8` al ai-provider, que monta un MCP server in-process con 5 tools read-only (list_niches, get_niche_keywords, get_niche_competitors, list_rank_radars, get_quota) con resultados truncados. El análisis sigue determinista; solo el chat es agéntico. E2E verificado contra el provider vivo (niches y radars reales). Requiere capybaras-ai-provider ≥ rama `feat/datadive-mcp-tools` con `DATADIVE_API_KEY`.

### Fixed
- **Robustez ante uploads inválidos** — un .xlsx corrupto o un archivo renombrado ya no vuelca traceback: `_parse_upload` captura el error de cualquiera de los 5 uploaders (MKL, Competitors, Rank Radar ×2, Competitor Intel) y muestra un mensaje claro. Un export válido pero equivocado (p.ej. Competitors en el uploader de MKL) parsea 0 SV y dispara una advertencia en vez de mostrar una tabla vacía sin explicación. Casos verificados en la app real: archivo corrupto, archivo equivocado, mismo niche vs sí mismo en Competitor Intel, doble-click en Traer, niche/radar/competitors vacíos, radar recién creado sin datos.
- **`list_niches` dedupea** — el endpoint `/v1/niches` declara paginación pero devuelve el set completo en cada página (medido: 6 páginas idénticas de 287 niches): el cliente dedupea por `nicheId` y corta apenas una página no aporta ids nuevos (antes: 6 requests y 1.722 filas con duplicados).

### Changed
- **Análisis IA de DataDive — prompt, contrato de datos y schema reescritos** tras una auditoría del output real (niche Coffee Thermos, ASIN challenger real, cifras cruzadas fila por fila). Cambios y su efecto medido en una corrida real posterior:
  - `ai/agents/_shared/chat.md` ahora declara que sus reglas rigen **solo los turnos de chat**: se concatenaba también al system del análisis, así que sus topes ("máximo 100 palabras", "3 bullets", `**negrita**`) contaminaban los campos del schema — y esa negrita salía literal en pantalla. Afecta a los tres agentes.
  - `launch_score` documentado como **costo de entrada** (más alto = más caro rankear), no como puntaje; `relevance` con las anclas reales del dominio (alta ≥3,0, no ≥7,0); `sugg_bid` con prohibición explícita de inventar bids, ACoS o presupuestos sin conocer precio y CVR del cliente.
  - **Gaps redefinidos**: ahora incluyen las filas donde el ASIN rankea pero está enterrado fuera de página 1, no solo donde no aparece. Eran las más baratas de atacar y el schema las excluía por completo (verificado: 7 de 10 gaps de la corrida nueva son de este tipo; antes, 0).
  - **Prioridad de clusters = atacabilidad, no tamaño**, y el orden del array es el orden de ataque: se acabó la contradicción de marcar "alta" al bloque más grande mientras la síntesis decía no atacarlo. Todos los row_ids se asignan a exactamente un cluster (verificado 120/120, 0 duplicados) con un cluster explícito de ruido.
  - **Schema que obliga a la decisión de PPC**: `match_type` por cluster, `via` (PPC_AHORA / LISTING_PRIMERO / NO_ATACABLE) y `confianza` por gap, `urgency` como enum, y los topes que el prompt enunciaba ahora se hacen cumplir (`maxItems`). Las acciones de la semana pasaron de ser solo de listing a incluir qué llevar a campaña y con qué match type.
  - **Muestreo con cupo para la cola** (`select_keywords`: 90 por SV + 30 por relevancia bajo el corte): el corte puro por SV dejaba afuera el long-tail barato y sesgaba el juicio hacia "niche caro". En la corrida nueva, los tres gaps más accionables salieron de la cola.
  - **Caveat de calidad de datos**: un ASIN tipeado que no está en el dive dejaba `mi_rank` vacío en las 120 filas y el agente emitía gaps sobre evidencia inexistente; ahora eso se declara y los gaps van vacíos.
  - El render muestra las cifras que las razones citan (relevance, launch_score, mi_rank), numera los clusters por orden de ataque y pinta `match_type` y `via`.
- **El chat responde sin esperar al análisis** — un agente con tools (`tools:` en su frontmatter) ya no contesta el mensaje enlatado "el análisis todavía está corriendo": abre su propia sesión y responde de verdad, porque sus tools no necesitan el análisis (p.ej. "¿cuánta cuota queda?"). Cuando el análisis termina, la sesión del análisis toma el relevo para las repreguntas con contexto de filas. Los agentes sin tools mantienen el comportamiento anterior. Verificado en vivo: pregunta contestada en 7s con datos reales (`resumed=False` en el log) mientras el análisis seguía corriendo.
- **Caption del niche traído por API** — muestra fecha y hora (UTC) del último dive.

### Fixed
- **Tab 5 Competitor Intel crasheaba al subir ambos MKL** — `_parse_mkl` retorna una tupla y el tab la asignaba directo (`AttributeError` pre-existente; el tab nunca llegó a correr). Además la clasificación de Gap buscaba columnas "rank" que el shape MKL no tiene (todo daba "Ninguno"): ahora la presencia en cada niche la decide el indicador del outer join. El default del filtro de gap ya no explota cuando ese valor no está entre las opciones.

### Fixed
- **`parse_mkl` roto con exports frescos de DataDive** — el export actual (2026-08) insertó la columna "Type" y corrió todo el layout; el parser mapeaba por posición fija y dejaba SV=0 en todas las filas (tab 1 vacío con el filtro default). Ahora mapea columnas por nombre de header con fallback al layout posicional legacy, y lleva la relevancy fraccional 0-1 de los exports nuevos a la escala UI 0-10. Verificado E2E con el export real SEVEN_SERUM: 419 keywords parseadas (antes 0).

### Tooling — Account Health setup (2026-05-06)
- **Skills nuevos (2):**
  - `data-persistence-standard.md` — convenciones bloqueadas de persistencia para todo el Agency OS. Estructura paths `data/<area>/<cliente>/<modulo>/`, naming `YYYY-WW.parquet`, schemas evolutivos en `data/_schemas/`, API mínima de `core/persistence.py` con 10 helpers, migration path Parquet→SQLite→Postgres, `.gitignore` por defecto para datos cliente.
  - `account-health-standard.md` — convenciones nueva sección Account Health: paleta 6 severidades unificadas (crítico/importante/saludable/menor/info/logístico), terminología bilingüe Amazon (~40 términos en inglés sin traducir), conceptos has_backup/aging/AIS, header con emoji 🏥, naming Excel exports `{Cliente}_{Modulo}_{Periodo}.xlsx`.
- **Agentes nuevos (2):**
  - `data-persistence-specialist.md` (Opus 4.7, color violet) — dueño de `core/persistence.py` y `data/` schemas. NO construye módulos enteros, coordina con `html-to-streamlit-porter` o `ppc-module-builder`.
  - `html-to-streamlit-porter.md` (Opus 4.7, color cyan) — porter de HTMLs standalone a módulos Streamlit. 6 fases obligatorias: análisis estructural, mapeo HTML→Streamlit, coordinación con persistence specialist, implementación, integración router, validación end-to-end.
- **Model fixes — issue AGENT-001 cerrado:**
  - Promociones a Opus 4.7 (lógica pura): `ppc-module-builder`, `code-reviewer`, `atom11-specialist`.
  - Snapshot fix Sonnet 4.5 estable: `excel-export-builder`, `ui-designer`, `testing-agent`, `client-onboarding`.
  - Sin cambios (ya estaban correctos): `sop-writer`, `client-notes-updater`.
- **Convención de modelos del repo formalizada**: Opus alias estable para lógica pura, Sonnet snapshot fijo para implementación, Haiku snapshot fijo para markdown.
- **Setup motivado por integración futura**: 3 HTMLs del compañero Marcos (Pricing Dashboard v3, SKU Progress Report v4, Flat File Migrator) van a portearse a la sección Account Health en próximas sesiones, usando estos skills/agents como infra base.

### Added
- **Variation Builder (M26)** — módulo nuevo en Account Manager. Generador de flat files Amazon con variaciones (parent + N children). 913 líneas, parser dinámico soporta hasta 220 columnas. Agrupa por variation_theme (Sabor, Nombre del Tamano, Scent, FlavorName-SizeName, Tamano del Sabor, Nombre del Patron). Preserva macros VBA y 10 hojas del template. v1 solo MX (MXN). Tested end-to-end con Pet Food real.
- **Gamboa Generator (M25)** — módulo nuevo en Account Manager. Reportes HTML integrales combinando SQP mensual + BR semanal. Dashboard interactivo con filtros runtime, agregaciones por mes, comparación WoW. Categorización persistente de keywords por cliente. 5 archivos: `modules/gamboa/__init__.py`, `parsers.py` (421L), `generator.py` (278L), `template.html` (874L/64KB), `modules/pages/gamboa_generator.py` (383L).
- **Campaign Builder v2.0 — Sprint 1: SBV/SBH rewrite** — nuevo flujo 4-pasos para crear campañas Sponsored Brand 2026. Selector SBV (video) vs SBH (headline). Brand Entity ID obligatorio. Video Asset ID (SBV) / Brand Logo Asset ID + Logo Crop (SBH). 29 columnas bulk SB 2026. Validaciones estrictas bloqueantes. Nombre Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder). Parsing de Plan de Acción como input. Testing: SBV end-to-end ✅.

### Fixed
- **Bulk Amazon 2026 compliance** — incrementadas columnas de 30 a 31. Agregado helper `_fila_vacia_bulk()` en `campaign_builder.py` para generar filas con todos los campos. Validación en Batch ID `cee6c2f5-520f-45d2-b769-c70f49e95776` (21/04/2026, flujo asíncrono).
- **Streamlit Markdown LaTeX gotcha** — patrón `**${variable}**` en `st.info/markdown/error/warning/success` rompe render (Streamlit interpreta `$` como delimitador LaTeX). Fix: escapar con `\\$` o envolver negrita alrededor de frase completa. Aplicado en 3 líneas de `modules/pages/campaign_builder.py` (L245, L480, L896).

### Changed
- `modules/pages/campaign_builder.py` — rewrite `_render_sb()`: 864 → 1121 líneas (+257 netas). Nuevos helpers: `_SB_COLS_2026` (29 cols), `_sb_row_factory()`, `_build_sb_bulk_rows()`. Flujo SBV vs SBH con campos específicos por tipo.

### Documentation
- `CLAUDE.md` — Sesión 2026-04-23 documentada con detalle técnico de Sprint 1, bugs conocidos (sub-agent alucinaciones, LaTeX gotcha), decisiones de arquitectura.
- `modules/pages/CLAUDE.md` — M10 Campaign Builder reescrito con helpers SB 2026 y contrato con M11. M25 Gamboa Generator agregado.
- `SOP_Uso_AgencyOS.md` — v3.3: flujo M10 con Paso 0 selector SBV/SBH, campos específicos por tipo.
- `sopppcmanagerdefinitivo.md` — sección Campaign Builder con tabla de versiones, subsección SB v2.0 completa con 29 columnas y validaciones.

---

## v3.3 — 22 Apr 2026
**Gamboa Generator integrado + Sprint 1 Campaign Builder**

### Added
- Gamboa Generator — reportes HTML integrales
- Campaign Builder SBV/SBH (Sprint 1)
- 31 columnas bulk Amazon 2026

### Fixed
- LaTeX markdown gotcha (3 líneas)
- Bulk compliance validado

---

## v3.2 — 15 Apr 2026
**Deploy + Equipo onboarding**

### Added
- Deploy live en capybaras-os.streamlit.app
- 21 usuarios del equipo en secrets.toml
- Expanders de ayuda en 15/15 módulos
- Login con streamlit-authenticator

### Fixed
- Python 3.11 f-string backslash (weekly_client_report.py L917)
- requirements.txt: agregado requests + beautifulsoup4

---

## v3.1 — 09 Apr 2026
**Listing Monitor + module-architecture-standard mejorado**

### Added
- Listing Monitor (M23) — scraper Amazon + alertas precio/rating/stock
- 3 agentes v3 con frontmatter: ppc-module-builder, excel-export-builder, ui-designer

### Changed
- Sidebar colapsable con expanders por sección (PPC/Research/Account/Knowledge)

---

## v3.0 — 27 Mar 2026
**8 módulos Research/Account conectados + mejoras visuales**

### Added
- DataDive Analyzer (M11) — 4 tabs: MKL, Competitors matrix, Rank Radar, Volatility
- Helium 10 Analyzer (M12) — 3 tabs: Cerebro, KW Research, Competitor Gap
- SBH Recommendation (M13) — targets para Sponsored Brand Headline
- Knowledge Base (M22) — explorar + agregar notas .md
- PPC Insights (M14) — health score 0-100 por ASIN
- PPC Forecast (M15) — proyección ventas + estacionalidad
- PPC Audit (M16) — auditoría integral score 0-100
- Account Pulse (M17) — monitor salud diaria + festivos MX

### Changed
- 48 st.metric migrados a kpi_card helper
- 14 empty states reemplazados por visual cards
- 8 headers unificados con layout flex
- Color coding en 6 tablas (DataDive, H10, SBH, etc.)
- Inicio v3.0 — 22 módulos visualizados

### Documentation
- Agentes v2.0 creados (9 agentes Sonnet/Haiku/Opus con skills asignados)
- Skills core: ppc-reporting-standard.md, module-architecture-standard.md, client-communication-tone.md
- modules/pages/CLAUDE.md — 22 secciones por módulo

---

## v2.0 — 23 Mar 2026
**Atom11 Rules Builder v2026.2 AGRESIVO**

### Added
- Atom11 Rules Builder (M21) — módulo con 274 rules dinámicas
- Campaign classification en 11 grupos por objetivo (DISCOVERY/RANKING/etc.)
- Thresholds v2026.2 AGRESIVO (DEC HARD = PAUSE TARGET)

### Changed
- 6 rules RANKING SP creadas en Atom11 real (cliente Dermaglos)
- Rules viejas v1 pausadas (14 RANKING + 10 DEFENSIVE)

---

## v1.5 — 21 Mar 2026
**Campaign Builder + Bid Optimizer + UI rediseño**

### Added
- Campaign Builder (M10) — generador campañas con Plan de Acción input
- Bid Optimizer (M9) — calculadora bids con CVR × precio × target ACoS
- Plan de Acción tab en Análisis Cruzado (M4)
- Campaign Analyzer en Bulk Campañas (diagnóstico semáforo)

### Changed
- Sidebar rediseñado oscuro (#1A1A1A, naranja #E84000)
- Página Inicio rediseñada (9 áreas Agency OS, ownership, flujo PPC)

---

## v1.0 — 18 Mar 2026
**Arquitectura modularizada completa + 22 módulos**

### Modules
- 22 módulos en modules/pages/ (inicio, STR, SQP, Bulk, BR, Cruzado, Tendencia, Funnel, Atom11, MerchanSpring, Weekly, Bid Optimizer, Campaign Builder, Atom11 Rules)
- Sidebar categorizado: PPC (expanded) | Research | Account | Knowledge
- Router app.py minimal (~200 líneas)

---

## v0.5 — 01 Mar 2026
**Primeros 8 módulos + setup inicial**

### Added
- Stack: Python + Streamlit + Pandas + OpenPyXL + pdfplumber
- Setup CI/CD: no test suite, no linter (custom SOP)
- Primeros módulos: STR, SQP, Bulk, BR, Cruzado, Tendencia, Funnel, Atom11

---

**Formato:** Keep a Changelog (https://keepachangelog.com/)
**Agencia:** Capybaras Agency | **Dev:** Lenin Acosta | **Última actualización:** 2026-04-26
