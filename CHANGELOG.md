# CHANGELOG — Agency OS Capybaras

Registro de cambios, mejoras y decisiones de diseño del PPC Manager.

---

## [Unreleased]

### Added — El chat consulta Amazon Ads en vivo: presupuesto, productos, cambios, bids, benchmark, facturas y Store (2026-10-01)

**Por qué.** Amazon calcula datos que la app no guarda y que el AM pregunta: cuánto se pierde por quedarse sin
presupuesto, qué ASIN anunciado está sin stock, qué cambió en una campaña, qué bid sugiere y qué share de impresiones
tiene la cuenta en cada keyword. El MCP de Amazon no tiene ninguno de estos endpoints, y todos responden al momento:
medidos con 15 cuentas reales, de 0,3 a 2,5 s.

**Qué cambia.** El MCP de ppc-manager suma 7 herramientas `live_*` (`services/mcp_server/tools/amazon_live.py`) que
leen una cuenta por llamada con `core/amazon_ads/live_reads.py`:
- `live_budget`: presupuesto sugerido, % del tiempo con presupuesto, ventas, clics e impresiones perdidas (7 días), uso
  de hoy, reglas de presupuesto y uso de portfolios.
- `live_products`: stock, precio, BSR y elegibilidad de los ASINs anunciados.
- `live_change_history`: historial de cambios con valor anterior y nuevo.
- `live_keyword_bids`: bid sugerido por target, y share y rank de impresiones por keyword.
- `live_category_benchmark`: la marca contra su categoría en SB.
- `live_invoices`: facturas, también el detalle por campaña.
- `live_store`: métricas de la Store.

**Errores y reintentos.**
- 5 s por intento y 2 reintentos ante 429, 5xx o caídas de red, con espera de 2 s como máximo (`AdsApiClient` ganó
  `max_retry_after_s`).
- Cada falla llega al chat como una frase.
- Si falla una parte, el resto responde igual y la parte fallida va en `errors`.
- Bids y keywords de SP se reusan hasta 6 horas, porque Amazon los limita mucho.

**Para activarlo en la VPS.** Agregar `ADS_TOKENS_JWT` al `.env`, con el JWT del rol `integ_provider` (el mismo del
AI provider, o uno nuevo con `sh scripts/mint_jwt.sh integ_provider`). Sin esa variable, el MCP arranca igual, sin las
herramientas `live_*`. El contenedor corre ahora como uid 10001, monta la clave de sellado en sólo lectura e instala
`cryptography`.

### Fixed — PPC Insights por ASIN de Análisis Cruzado muestra ACoS, CVR y sesiones sin seis decimales (2026-10-01)

La tabla de la pestaña «📊 PPC Insights por ASIN» mostraba «ACoS %», «CVR %» y «Sessions (BR)» con seis decimales
(8.600000, 5.500000, 2900.000000): la tabla pasa por un Styler para colorear el ACoS, y Streamlit imprime así toda
columna numérica sin formato propio. Ahora ACoS y CVR van con un decimal y su % (8.6%, 5.5%) y las sesiones sin
decimales y con separador de miles (2,900). El color del ACoS no cambia, y un ACoS, CVR o sesiones sin dato siguen
vacíos, nunca 0.

### Fixed — El chat ya no pierde la pregunta al cambiar de módulo mientras responde (2026-09-30)

**Por qué.** Si el AM cambiaba de módulo (o la página se relanzaba) antes de que llegara la respuesta, Streamlit cortaba
la corrida y se perdían la pregunta y la respuesta: en producción, tres envíos seguidos de la misma pregunta nunca
llegaron a `chat_turns`.

**Qué cambia.** `core/chat/panel.py` responde en un hilo propio y guarda la respuesta aparte; el chat la levanta
cuando llega, esté el AM en el módulo que esté. Mientras responde, el botón Enviar queda deshabilitado. El chat ofrece
3 ideas para preguntar en lugar de 5.

### Changed — La cuenta y el país de Amazon Ads se mantienen entre módulos (2026-09-30)

La cuenta y el país que el AM elige en un picker de Amazon Ads (Search Term Report, Bid Optimizer, Bulk Campañas,
Funnel, Cruzado, PPC Insights, PPC Audit, SBH y el bloque de cuenta de Forecast, Account Pulse y Weekly Client Report)
quedan elegidos al abrir cualquier otro módulo. Sólo viaja lo que el AM elige, no la cuenta que un picker muestra por
defecto (`follow_shared_profile` / `share_user_choice` en `modules/pages/search_term_source.py`).

### Added — Tablas de Seller Central con una sola escritura para la carga manual y la SP-API (IT-59, 2026-09-29)

**Por qué.** Los AMs vuelven a subir el mismo Business Report y el mismo SQP en cada módulo, y nada queda guardado.
Los datos de Amazon Ads ya se sincronizan; los de Seller Central no. Esta es la base para guardarlos, vengan de un
archivo o de la SP-API cuando Amazon apruebe la app.

**Qué hay.** Migración `023_seller_reports.sql` y `core/seller_reports/`. Las decisiones están en
`docs/seller-central-data.md`.
- Una cuenta de Seller Central es la cuenta de Amazon Ads de un marketplace. Su `selling_partner_id` queda nulo hasta
  que la SP-API lo confirme o alguien lo cargue a mano. Solo cuentas seller.
- Guarda tres cosas: el BR por día, el BR por ASIN hijo sobre su rango exacto, y el SQP (Brand View y ASIN View) por
  semana de domingo a sábado o por mes. Las columnas llevan los nombres de la SP-API; un nulo quiere decir que el
  export no traía esa columna; shares, tasas y CVR se calculan al leer.
- Hay una sola escritura: el app sube como `manual` y el worker guarda como `sp_api`. El mismo contenido no escribe
  nada, la SP-API reemplaza lo manual, y lo manual encima de la SP-API pide confirmación.
- Toda escritura tiene vista previa (lo que hay y lo que pasaría con cada período). Cada carga se puede volver atrás,
  y borrar también se deshace.
- `web_user` no escribe ninguna tabla directo: todo pasa por funciones `security definer`. Las tablas nuevas están en
  el smoke, y `e2e_selfhosted_db.py` prueba el camino entero por PostgREST y borra lo que crea.

### Changed — La subida manual vuelve como fallback en los cinco módulos que la habían perdido con la API de Amazon Ads (2026-09-29)

**Por qué.** Al pasar a la API, Search Term Report, Bulk Campañas, Análisis de Funnel, Bid Optimizer, PPC Insights y PPC
Audit conservaron la subida manual como alternativa, pero Análisis Cruzado, SBH Recommendation, PPC Forecast, Account
Pulse y Weekly Client Report la perdieron: sin una cuenta conectada y sincronizada no había forma de usarlos. El criterio
quedaba distinto según el módulo.

**Ahora, un solo criterio.** Todo módulo que lee Amazon Ads sigue la cuenta por defecto y ofrece la subida a mano:
- Sin cuentas conectadas, el uploader con la pista para conectar la cuenta.
- Con cuentas, «Subir archivo manualmente» en todos los estados de la tarjeta de la cuenta (sin elegir, lectura caída,
  sin sincronizar, primera carga, al día). El modo manual muestra la nota, «Volver a datos de Amazon Ads» (con la cuenta
  elegida intacta) y el uploader, y no lee nada de Amazon Ads.
- Lo que el archivo no dice (días, cuenta, moneda, atribución) se dice en pantalla y al agente IA; nunca se inventa. La
  firma de la pestaña IA incluye el archivo, así que un archivo nuevo es un análisis pendiente, no uno viejo.

**Por módulo.**
- **Análisis Cruzado: Bulk File.** `core/cross_analysis/bulk_file.py` lo convierte en lo mismo que da la cuenta: search
  terms canónicos con sus IDs (Auto negativizable, product targeting no), las Exact habilitadas de la hoja de campañas
  (sin esa hoja, «♻️ Ya en Exact» queda sin dato) y todos los ASINs de cada ad group. Las cuatro pestañas y los dos
  exports funcionan igual.
- **SBH Recommendation: Bulk File o export de keywords SP** para marcar «En SP». Del Bulk usa la misma regla que el
  listado (keyword, campaña y ad group habilitados, sin negativas). Un Campaign CSV de nivel campaña, que el uploader
  viejo dejaba vacío sin avisar, ahora da un error claro.
- **PPC Forecast, Account Pulse y Weekly Client Report: Campaign CSV**, una sola vez en el bloque compartido
  (`ad_account_block.py` + `core/amazon_ads/campaign_file.py`). Lee el export de Campaign Manager (y los headers viejos),
  suma todas las campañas sea cual sea su estado, limpia montos con cualquier prefijo («MX$5,796.55»), toma la moneda si
  el archivo la dice y rechaza un Bulk File (sumarlo contaría dos veces). Como el archivo no trae días, se compara con
  todos los días del BR (`file_split`) y la pantalla pide que se exporte con ese mismo rango. Forecast: desglose y
  spend estimado. Account Pulse: ACoS y TACoS del período del archivo, sin comparar semanas, y la hoja Campañas.
  Weekly: la hoja Advertising, también sin BR diario (entonces sin TACoS); portfolios y NTB sólo si el archivo los trae.
- **Search Term Report, Bid Optimizer, PPC Insights y Análisis de Funnel** ya tenían la subida manual, pero el picker del
  STR no la ofrecía en tres estados: lectura de search terms caída, cuenta que pide reautorizar sin datos todavía, y
  lista de cuentas caída con datos en pantalla. Ahora la ofrece también ahí (sólo con `allow_manual`: Análisis Cruzado
  y PPC Audit dibujan su propio botón).

**Archivos que no son lo que parecen.** Ningún lector deja pasar un traceback: un .xlsx cifrado, un .xls renombrado o
un zip que no es un workbook dan un error que nombra el archivo. El Campaign CSV rechaza cualquier Bulk (hoja de
campañas SP, SB o SD, o columna `Entity`, también guardado como CSV) y un archivo con dos monedas; un Campaign ID que
Excel reescribió en notación científica ya no funde campañas distintas; un NTB en `-` o vacío queda sin dato, no 0.
SBH lee CSV con `;` (Excel en español), usa `State` para el estado y `Status` como estado de entrega (una campaña
pausada no marca «En SP»), y rechaza la columna `Targeting` de una grilla de campañas (Manual/Automatic). El Bulk de
Análisis Cruzado conserva los términos «nan», «null» o «n/a», y la ayuda pide destildar *Campaign items with zero
impressions* (Amazon los excluye por defecto y sin ellos «♻️ Ya en Exact» no ve las keywords sin impresiones).
Weekly muestra «—» (no 0) para impresiones, clicks u órdenes que el archivo no trae, y Account Pulse pone el ACoS/TACoS
del archivo en su propia sección del Excel, no bajo «This Week».

### Added — Órdenes de Compra recibe una OC desde planilla (2026-09-29)

**Por qué.** Fede tiene una OC Emitida de 109 líneas y la recepción manual pide cargarlas de a una.

**Ahora.**
- En el detalle de una OC Emitida o Recibida parcial, «📄 Cargar desde planilla» baja una plantilla con las líneas de
  la OC: `SKU | Pedidas | Ya recibidas | Cantidad recibida (acumulado)`. Solo la última columna dice «cantidad», así
  el lector no toma lo pedido como recibido.
- La planilla trae el total ACUMULADO por SKU, igual que la pantalla manual: subirla dos veces no duplica nada. Lo
  que no llegó se deja vacío y no aparece como error.
- Se lee con el mismo motor que el alta masiva (`core/supply/oc_import.py`, sin cambios). El cruce contra la OC vive
  en `core/supply/recepcion_import.py`, capa pura.
- Un SKU que no está en la OC se rechaza con motivo y no se agrega. Uno que difiere solo en mayúsculas se rechaza y
  muestra el SKU de la OC. Un SKU repetido dentro de la OC se rechaza por ambiguo. Las líneas que no vienen en la
  planilla no se tocan.
- Recibir más de lo pedido se registra con aviso. Bajar lo ya recibido también, marcado en la vista previa.
- Vista previa antes de registrar: qué se aplica (pedidas, antes, después), qué se rechaza y por qué, las filas que
  no se pudieron leer, y el lead time que va a quedar con el mismo bloqueo de fecha anterior a la emisión.
- Una sola fecha para toda la carga. Si la planilla trae una fecha, se propone; si trae varias, se avisa.
- La casilla «Recepción completa» viene tildada cuando con la planilla llega todo. Si se tilda con faltantes, avisa
  que la OC se cierra igual.

### Added — Weekly Client Report muestra el stock por ASIN del último snapshot del Pricing Dashboard (2026-09-29)

**Por qué.** Punto 3 del pedido de Supply (Freddy): el reporte semanal no mostraba stock, y la única fuente de stock
de Amazon que la plataforma guarda es el snapshot del Pricing Dashboard (M30), con `fba_available`, `awd_available`,
`izzi_available` y `total_stock` por SKU.

**Ahora.**
- Selector «Stock del Pricing Dashboard» debajo del nombre del cliente, con los clientes del Pricing Dashboard.
  Por defecto «(sin stock)»: el reporte sale como antes.
- Con un cliente, la hoja «WoW Comparison» suma un grupo STOCK al final, después de TACoS, con una sola columna FBA
  y la fecha del snapshot en el encabezado. Cada ASIN suma sus SKUs. La fila CUENTA TOTAL suma el FBA de todo el
  snapshot.
- AWD e Izzi quedan afuera: el Pricing Dashboard todavía no los integra y los guarda en 0, que no es un dato. La nota
  al pie lo dice. Las columnas del grupo se declaran en un solo lugar (`REPORT_COLUMNS` de
  `core/weekly_report/stock.py`) para sumarlas cuando el Pricing las guarde de verdad.
- Un dato que el snapshot no trae queda «—», nunca 0. Un 0 del snapshot se muestra como 0: es un quiebre real.
- La nota al pie dice de dónde sale el stock, de qué fecha es y cuántos SKUs sin ASIN quedaron afuera. Si el snapshot
  es anterior a la semana del reporte, lo avisa con los días. La pantalla muestra el mismo texto.
- Sin snapshots guardados para ese cliente, el grupo dice «STOCK (sin snapshot)» y las celdas «—».
- El catálogo de clientes del Pricing Dashboard pasa a `core/pricing_clients.py` para que lo compartan los dos módulos.

**Límite.** El stock es el del último «Guardar snapshot» del Pricing Dashboard, no el de la semana del reporte.

### Changed — PPC Insights lee las campañas del listado de Sponsored Products de la cuenta en lugar del Campaign CSV (2026-09-29)

**Por qué.** La parte «estructura de campañas» del health score (15 de 100 puntos) salía de un Campaign CSV subido a
mano: contaba las campañas habilitadas cuyo nombre contenía el ASIN y adivinaba los tipos por palabras del nombre
(«auto», «exact»…). Una cuenta que no pone el ASIN en el nombre daba 0 campañas y funnel incompleto aunque tuviera Auto y
Exact, y un nombre con «EXACT» contaba como Exact aunque la campaña no tuviera keywords. Medido en la base local sobre los
últimos 7 días de 5 cuentas: la regla por nombre y la del listado discrepan en el funnel de 8 de 27 ASINs (26% del gasto
de las cards), y 7 ASINs tenían 0 campañas por nombre. En Tattoo Care US, las tres campañas habilitadas de B0CXTRC44X con
«EXACT» en el nombre no tienen ningún keyword habilitado.

**Ahora.**
- Con datos de Amazon Ads, el bloque «Campañas de la cuenta» lee el listado diario de Sponsored Products de la misma
  cuenta del picker. Una campaña cuenta para un ASIN si está habilitada y tiene un ad group habilitado con un anuncio
  habilitado de ese ASIN, o si su nombre lo lleva (la etiqueta de familia, como la atribución de los search terms). Los
  tipos salen de lo que corre: Auto por el tipo de targeting, Broad/Phrase/Exact por sus keywords habilitados y PAT por
  sus product targets.
- El Campaign CSV sigue: «Subir Campaign CSV a mano» (y «Volver a datos de Amazon Ads»), o directo cuando la cuenta no
  está listada, Amazon rechazó el listado o no se pudo leer. Con un STR subido a mano, el uploader de siempre. Con el CSV
  la regla es la de antes, por nombre.
- El análisis IA guardado y la herramienta `asin_health` del chat leen el mismo listado, así la pantalla, la IA y el chat
  dan el mismo score (`campaign_structure` en el chat, o `campaign_structure_note` con el motivo si no hay listado).
- Migración 022: el worker de análisis (`ai_worker`) puede leer `sp_structure_between` y las tablas que nombra. Los
  análisis guardados de PPC Insights cambian de huella y ofrecen «Recalcular».

### Added — Filtro «Estado de campaña» en Search Term Report, Bulk Campañas y Bid Optimizer (2026-09-29)

**Por qué.** Pedido de Lenin: el selector de campaña del Search Term Report traía todas las campañas del período, en
cualquier estado, y no había forma de quedarse con las activas, las pausadas o las archivadas, como con el filtro
Active status de Campaign Manager. Bulk Campañas tenía reglas fijas (escondía las archivadas) y el Bid Optimizer sugería
placements y budget a cualquier campaña del período.

**Qué cambia.**
- Un solo filtro reusable: la regla en `core/amazon_ads/campaign_status.py` (`StatusFilter`, `status_mask`,
  `filter_by_status`) y el selector en `modules/pages/campaign_status_filter.py`. Opciones: Todas, Todas menos
  archivadas, Activas, Pausadas y Archivadas. **Arranca en Activas** en todos los módulos.
- **En los dos idiomas:** sus textos están en `core/ui/i18n.py` (`campaign_status.*` y, para los mensajes de Bulk
  Campañas, `bulk_campaigns.*`); en inglés usa los nombres de Campaign Manager (Active status, All, All but archived,
  Enabled, Paused, Archived). La elección se mantiene al cambiar de idioma. El resto de esas páginas sigue sólo en
  español: nunca se migraron al catálogo.
- **Search Term Report:** en Vista General → Filtros, antes del selector de campaña (lo recorta junto con la tabla), y
  en Por Campana (su tabla, sus KPIs, la distribución por tipo de término y el Excel). Cada pestaña tiene su propio filtro.
- **Bulk Campañas:** al lado de Producto, sobre Vista General y el Campaign Analyzer, que sigue diagnosticando sólo las
  activas y ahora dice por qué queda vacío. Las campañas SP archivadas llegan aparte en `CampaignSource.archived` (de la
  misma lectura) y se suman sólo cuando el filtro las pide. El chat se entera del estado elegido, como del producto.
- **Bid Optimizer:** arriba de «Placements sugeridos por campaña»: la lista, sus KPIs, el budget estimado y el export.
- El estado de un search term es el `_campaign_status` que ya trae el reporte sincronizado (el mismo que usa el bulk de
  negativos); en Bulk Campañas, el `State` de las campañas. Con un STR subido a mano el filtro queda deshabilitado y lo
  dice; un Campaign CSV subido a mano sí lo usa, con su columna State.

**Qué no cambia.** Los análisis IA (del Search Term Report, de Bulk Campañas y del Bid Optimizer), las herramientas del
chat y los KPIs de arriba de Vista General del Search Term Report leen lo mismo que antes: el filtro sólo recorta lo que
se lista, así un análisis guardado sigue encontrándose por su huella.

**Límites.** En Sponsored Brands y Display no hay archivadas: el sync lista sólo habilitadas y pausadas. El estado es
el de la última sincronización y las métricas son las del período: una campaña archivada ayer aparece con su gasto de
la semana.

**Verificación de la fuente del estado.** En producción (29/09, últimos 30 días de search terms) el estado del reporte
coincide con el del último listado de campañas en las 4.399 campañas: 4.348 habilitadas, 50 pausadas y 1 archivada.

### Changed — Search Term Report → Por Campana: top de campañas por gasto en lugar de la card «Mayor Spend» (2026-09-29)

La card «Mayor Spend» mostraba el nombre de la campaña de más gasto cortado a 35 caracteres, y los nombres de la
naming convention pasan de 80 (la de Dermaglós US del 15 al 21/09 tiene 85). La pestaña queda con 3 cards (Total,
Brand, No Brand) y un bloque «Top campañas por gasto»: hasta 5 campañas con gasto, con el nombre completo, el monto, su
parte del gasto de las campañas de la vista (con una barra a escala) y el ACoS, o «Sin ventas» si no vendió. Lo dibuja
un componente nuevo y reusable, `core/ui/ranking.py` (`RankingRow`, `render_ranking`), con los colores de las cards;
en un teléfono el monto baja debajo del nombre. Respeta el filtro «Estado de campaña» de la pestaña.

### Fixed — La marca del SQP se detecta también en los CSV (2026-09-29)

`extract_sqp_brand` nunca leía la marca de un SQP en CSV: tomaba el nombre de la primera columna, que con
`header=None` es el número 0, y el error quedaba tragado. Search Query Performance, Análisis Cruzado y SBH
Recommendation pedían la marca a mano (o seguían sin ella) aunque el archivo la traía en `Brand=[...]`. Ahora lee la
primera celda de la fila de metadata en CSV y XLSX, deja el archivo al principio para que `read_sqp` lea el header, y
un archivo que no se puede leer queda en el log en vez de pasar en silencio.

### Changed — Análisis Cruzado lee la cuenta de Amazon Ads en lugar del Bulk File, exporta el plan que lee Campaign Builder y suma Análisis IA; el bulk de negativos del Search Term Report lee el listado SP (IT-51, 2026-09-28)

**Por qué.** Análisis Cruzado pedía el Bulk File completo: su hoja de search terms para el cruce y su hoja de campañas
para el ASIN de cada ad group (Tab 3) y las keywords Exact activas (INV-11.2). Esas dos cosas no salen de un reporte de
métricas, que sólo trae lo que tuvo clicks. Además la Tab 3 le daba el ad group entero a su primer ASIN (en la base
local, 4.835 de 4.952 ad groups de Shapermint US anuncian más de uno), «♻️ Ya en Exact» sólo llegaba a las queries con
search term, y el export, un bulk de Amazon válido, ya no traía las columnas que lee Campaign Builder. El bulk de
negativos del Search Term Report tenía el mismo hueco: sus controles de Exact activas y keywords propias sólo veían las
keywords con clicks, y no verificaba el estado del ad group.

**Ahora.**
- **Sin Bulk File.** Análisis Cruzado usa el picker de Amazon Ads (cuenta, país y período) y el SQP de la marca. Las
  keywords Exact habilitadas salen del listado diario de Sponsored Products de la cuenta y el ASIN de cada ad group de
  sus productos anunciados, con la regla de PPC Insights: nunca se reparte ni se toma el primero. Sin cuenta conectada la
  página lo dice; ya no hay carga manual.
- **Guardas.** «♻️ Ya en Exact» se calcula sobre cada query del SQP contra todas las Exact habilitadas, tengan o no
  clicks; sin listado no se muestra y se dice por qué. Los términos de campañas Auto ya no figuran como «🛑 No
  negativizable» (INV-11.1), y un portfolio sin nombre sincronizado cuenta como protegido, como en el Search Term Report.
- **Dos exports.** El bulk para Bulk Operations no vuelve a crear keywords que ya existen como Exact habilitada, y sólo
  cambia bids de términos que llegaron por una keyword: cada keyword una sola vez y con su propio texto. Antes, dos
  términos que llegaban por la misma Broad daban dos Updates del mismo Keyword ID, cada uno con el texto del search term
  (visto en Mott & Bow US con la base local). El plan para Campaign Builder vuelve a traer `Keyword` /
  `Acción sugerida` / `Purchases mercado` / `Brand Share %` en su primera hoja, sin las queries que ya corren como Exact.
- **Tab 3.** El Business Report by ASIN cruza por el ASIN hijo (antes tomaba el padre y casi nunca cruzaba), los montos
  van en la moneda de la cuenta y los ASINs se ordenan por gasto.
- **Análisis IA.** Pestaña nueva con el agente `cross_analysis`: qué acciones del plan tomar primero, cuáles esperar o
  investigar, sin cambiar la acción del módulo ni proponer bids. Corre sólo con «Analizar con IA» y se comparte con el
  chat con la cuenta.
- **Search Term Report.** El bulk de negativos lee del mismo listado las Exact habilitadas, las keywords propias de cada
  ad group y el estado del ad group: un ad group pausado o archivado deja afuera sus negativos. Sin listado sigue como
  antes y lo avisa. `search_term_candidates` del chat da el mismo veredicto.
- **Arreglos en el camino.** La Tab 1 ya no se rompe cuando hay una sola query «solo en SQP», y sin precio el bulk dice
  que falta el precio en vez de culpar a los IDs. 🔍 INVESTIGAR se dispara: el Opportunity Score del plan pasa a 0-100,
  la escala de la Tab 1 y la de su regla (antes iba de 0 a 1 y ninguna query llegaba a 40).

### Changed — PPC Audit Pro lee la cuenta de Amazon Ads, audita también lo que no tuvo tráfico y suma Análisis IA y la herramienta `ppc_audit` del chat (IT-44, 2026-09-28)

**Por qué.** La auditoría sólo leía un Bulk File de cinco hojas subido a mano; la estructura sincronizada de la cuenta
no le llegaba. Y un reporte sólo trae lo que tuvo actividad: medido en producción el 22/09 (IT-50), el 85,2% de los
keywords y targets SP habilitados no tiene ninguna fila de `spTargeting` en 60 días, justo lo que Target Graduation
tiene que encontrar. Además varios checks contaban mal: Match Types Mixtos, Duplicación y SKAG agrupaban por nombre de
campaña, SKAG contaba sólo targets con gasto e incluía las campañas automáticas, y el porcentaje de Target WAS dejaba
afuera el gasto de SD.

**Ahora.**
- **Cuenta en lugar de archivo.** El picker del Search Term Report elige cuenta, país y período, y el bloque «Estructura
  de las campañas» lee esa misma cuenta y ventana: la estructura SP del listado diario (campañas con sus placements, ad
  groups, keywords, product targets y product ads, con o sin tráfico y con el bid efectivo), las campañas SB y SD (una
  archivada que gastó en el período suma en los KPIs), los keywords SB, los targets SD y los search terms SB. El bloque
  dice cuándo se listó la cuenta, qué trae y hasta qué día llegan las métricas cuando terminan antes que el período. Sin
  cuentas conectadas, o con «Subir Bulk File a mano», audita el Bulk File como antes.
- **Lo que falta no es cero.** Si la fuente no tiene una parte (la cuenta sin listar, el targeting sin sincronizar, los
  search terms SB pendientes), la página, la IA y el chat dicen por qué en su lugar; nunca muestran 0 ni «Sin targets
  huérfanos». Las campañas sin métricas (SB del formato anterior, reportes pendientes) no suman en los KPIs y se cuentan
  aparte.
- **Los checks cuentan lo que corre.** Match Types Mixtos, Duplicación y SKAG cuentan los keywords y targets habilitados
  de campañas y ad groups habilitados, agrupados por Campaign ID; SKAG vs Bolsa mira las campañas manuales. Target WAS
  suma SD al denominador. Target Graduation deja afuera los ad groups pausados o archivados. AUTO sale de los grupos de
  targeting automático, con todo su tráfico, y con la API los segmentos suman el TOTAL SP (medido en la base local, Mott
  & Bow US: $4,683.43 de $4,683.43). El Top 5 calcula el ACoS de spend y sales, los ASINs propios salen también de los
  product ads de la cuenta y Bid Adjustments cuenta las campañas habilitadas con los nombres de Campaign Manager.
- **Análisis IA.** Pestaña nueva con el agente `ppc_audit`: lee las campañas con match types mixtos, las top, los
  targets duplicados, Target Graduation accionable y los search terms sin ventas (filas `U01…`), y dice ACTUAR, ESPERAR
  o INVESTIGAR con su confianza, sin recalcular cifras ni proponer bids. Corre sólo con «Analizar con IA» y se comparte
  con el chat.
- **Chat.** La página le pasa al chat la cuenta, las fechas, los brand terms y la llamada. La herramienta nueva
  `ppc_audit` del MCP da cualquier sección de la auditoría (segmentos, match mixto, duplicados, graduation, search terms
  sin ventas, top campañas, tipos de target, placements y SKAG) con las mismas lecturas y reglas, más las cifras de la
  cuenta (`summary`) y lo que falta (`missing`).
- **Tablas legibles.** Segmentos, tipos de target y Target Graduation muestran montos y porcentajes con dos decimales
  (antes, seis) y los conteos sin decimales; donde no hay dato, «—».
- Las reglas pasaron de la página a `core/ppc_audit/checks.py`, que leen la página, el Excel, la IA y el MCP. Medido en
  la base local con Mott & Bow US: 1.671 search terms en 0,39 s, 4.403 filas de estructura en 0,54 s y la auditoría en
  0,04 s.

**Search terms de Sponsored Brands.** Dos reportes nuevos por cuenta con SB (migración 021, aditiva): `sb_search_terms`
(Reporting v3 `sbSearchTerm`) y `sb_legacy_search_terms` (v2 `/v2/hsa/keywords/report` por query, un día por reporte),
para las campañas del formato anterior que v3 deja afuera; un término nunca cuenta dos veces. Cargan 60 días de historia
una vez y después los últimos 14 cada noche, como los otros reportes SB, y el v2 sólo si la cuenta tiene campañas del
formato anterior. Cualquier módulo los lee con `ProductProvider.sb_search_terms(...)`. **Probados contra la API real
el 29/09 (sólo lectura):** Amazon aceptó los dos pedidos, devolvió exactamente los campos pedidos y el parser leyó
todas las filas. v3 en Mott & Bow US del 15 al 21/09: 31 términos con 39 clicks y $44.67, lo mismo que sus 11
campañas SB esos días; Amazon tardó ~21 minutos en entregarlo (el worker espera hasta 3 h 20 min). v2 en Shapermint US
del 20/09: 2.051 términos en ~41 s; en sus 28 campañas del formato anterior suman $1,764.74 contra $1,764.76 de
gasto de esas campañas. El v2 trae también las del formato nuevo (191 campañas, $3,429.47): por eso el día guarda del
v2 sólo las del formato anterior. Si Amazon rechaza un pedido, el job falla con su mensaje en el Registro de
solicitudes, la cuenta queda con la alerta y PPC Audit muestra los search terms SB «sin dato».

**Qué queda afuera.** Los negativos: ningún check los usa y una cuenta grande tiene cientos de miles.

**Deploy.** Migración 021, aditiva: una tabla y dos funciones nuevas, nada existente cambia, y la imagen anterior
funciona sobre ella. Jenkins levanta la imagen antes de «DB migrate», en el mismo pipeline: un job de search terms SB
que guarde en esa ventana falla y se reintenta a los 5 minutos, y PPC Audit muestra los search terms SB «sin dato» por
falta de la migración. Si hay que volver a la imagen anterior con la 021 ya aplicada, cancelar antes los jobs de
`sb_search_terms` y `sb_legacy_search_terms` en cola: la imagen anterior no conoce esos tipos, los marca fallidos y cada
cuenta queda con una alerta por 24 h. El smoke de la base prueba `ads_sb_search_term_daily`. La imagen del MCP copia
`core/ppc_audit/` sin `analysis.py`.

### Changed — Account Pulse y Weekly Client Report leen la publicidad de la cuenta de Amazon Ads y suman Análisis IA (IT-45, 2026-09-28)

**Por qué.** Los dos pedían un «Campaign CSV» subido a mano. En Account Pulse el TACoS dividía el spend de ese CSV (el
rango que exportara el AM, 14 días según la instrucción) por las ventas de los últimos 7 días del BR, y ni el ACoS ni el
TACoS tenían semana anterior. En el Weekly el CSV era la única fuente de la hoja Advertising: sin él, la hoja salía vacía.

**Ahora.**
- **Cuenta en lugar de archivo.** Los dos montan el bloque de cuenta de PPC Forecast, ahora compartido
  (`modules/pages/ad_account_block.py`): Cuenta y País sin valor por defecto (el BR no dice de quién es) y los reportes
  de campaña sincronizados, SP, SB y SD como los cuenta Campaign Manager, sobre los días del BR diario. Si las ventas de
  ads superan las del BR se avisa que la cuenta o el país no son los del BR.
- **Account Pulse.** ACoS y TACoS de esta semana y de la anterior, cada uno sobre sus propios días del BR con datos de
  ads, con variación en la tarjeta y en la hoja Resumen. La hoja Campañas sale de la cuenta, con la columna Producto, y
  una campaña sin ventas muestra «—» en vez de un ACoS de 0%. Los montos van en la moneda de la cuenta.
- **Weekly Client Report.** La hoja Advertising (KPIs, top 15 campañas, alarmas, portfolios) sale de la cuenta sobre los
  días del BR diario, en su moneda y con una línea que dice de dónde salen las cifras. New-to-brand viene de Sponsored
  Brands y Display, los productos cuyos reportes lo acreditan; las vistas de la página de detalle no se sincronizan y
  quedan en «—». Las alarmas suman las campañas que gastaron sin vender. Sin BR diario, la hoja dice que falta.
- **Análisis IA.** Pestañas nuevas con los agentes `account_pulse` y `weekly_report`: una lectura por tema (ventas,
  tráfico y conversión, publicidad, Buy Box) con veredicto ACTUAR, VIGILAR u OK y la síntesis, sin recalcular cifras. El
  del Weekly reemplaza al botón «Generar análisis IA» (`core.ai_analyze`) y escribe el borrador del resumen para el
  cliente, que se copia o se descarga como antes. Corren sólo con «Analizar con IA» y se comparten con el chat.
- `paid_split` pasó a `core/business_report/` y el formato de moneda del Excel a
  `core.currency_format.excel_money_format`, sin cambios de comportamiento.

### Changed — El chat contesta las preguntas generales sobre todas las cuentas, con el cruce ya hecho por el MCP (IT-57, 2026-09-28)

**Por qué.** En Profundo, una pregunta del chat tardaba entre 81 y 304 s. En una pregunta general («¿qué campañas se
quedan sin presupuesto?») el modelo paginaba `accounts_overview` y `list_analyses` para elegir cuentas, abría 3 a 7 de a
una con la misma herramienta y armaba el ranking razonando, y terminaba diciendo «revisé 3 de las 52 cuentas».

**Ahora.**
- **`all_accounts=true`** en `campaign_health`, `search_term_candidates`, `metrics_by_group`, `funnel_coverage`,
  `bid_suggestions` y `asin_health`: la herramienta corre en todas las cuentas sincronizadas, cada una con sus
  parámetros guardados, y devuelve las filas rankeadas juntas, una lista por moneda, con los conteos sumados y qué
  cuentas no tuvieron filas o no tienen datos. `asin_health` ordena también del peor health score al mejor.
- **`breakdown` pasa a llamarse `metrics_by_group`** y, por search term, dice si la cuenta ya lo tiene en exact
  (`exact_in_account`, `without_running_exact`): «términos que venden sin exact» sale en una llamada.
- **`accounts_overview` trae un `summary`** de todas las cuentas: cuántas gastaron, cuántas subieron o bajaron contra
  el período anterior, las que más se movieron y los totales de cada moneda. Las cuentas que gastaron van primero.
- **`account_action_plan`**: qué hacer en una cuenta con las reglas de Bulk Campañas y del Search Term Report, en una
  llamada.
- **La conversación abre con el directorio de cuentas** y la ventana del último análisis guardado de cada módulo.
- **El prompt** manda las preguntas generales a una sola llamada con `all_accounts`.
- **Medido** (21 preguntas sugeridas, Profundo, una corrida cada una): 2798 → 1964 s (−30%), junto con los cambios del
  provider; las respuestas generales cubren las 52 cuentas.

### Changed — PPC Forecast lee las ventas de ads de la cuenta de Amazon Ads, cuenta el fin de semana una vez y suma Análisis IA (IT-47, 2026-09-25)

**Por qué.** El desglose orgánico vs paid y el spend estimado salían de un «Campaign CSV» subido a mano, que el AM tenía
que exportar con el mismo rango que el BR; sin archivo, el spend estimado mostraba $0.00. Y la proyección contaba el fin
de semana dos veces: cuatro semanas idénticas (hábiles 100, fines de semana 60) terminadas en domingo se proyectaban en
$986.02 para los 14 días siguientes en vez de $1,240.00.

**Ahora.**
- **Cuenta en lugar de archivo.** «Ventas de ads de la cuenta» elige Cuenta y País (arranca sin cuenta: el BR no dice de
  quién es) y lee los reportes de campaña sincronizados, SP, SB y SD como los cuenta Campaign Manager, sobre los mismos
  días del BR. No se usan los search terms: son sólo SP, y en la base local SB+SD eran hasta el 18,5% del spend y el 29%
  de las ventas de ads de una cuenta.
- **Días en común.** Si la cuenta sincronizó sólo una parte del BR, el desglose va sobre esos días y lo dice; sin días
  en común no hay desglose. Sin datos de ads el spend estimado es «—», y si las ventas de ads superan las del BR se avisa
  que la cuenta o el país no son los del BR.
- **Proyección.** La tendencia y la diferencia de fin de semana se ajustan juntas. En un backtest con ventas diarias
  reales de ads de 12 cuentas, el sesgo mediano del total a 14 días pasó de +7,7% a +0,3%; el error por día no cambió.
- **«Generar Forecast» deja el resultado en pantalla** mientras no cambien el BR, el horizonte o el crecimiento; elegir
  la cuenta actualiza el desglose sin volver a generar.
- **Análisis IA.** Pestaña nueva con el agente `ppc_forecast`: dice qué tanto confiar en la proyección y en el spend
  estimado y qué hacer esta semana, sin recalcular cifras. Corre sólo con «Analizar con IA» y se comparte con el chat.

### Changed — SBH Recommendation marca «En SP» con la cuenta de Amazon Ads y suma Análisis IA (IT-49, 2026-09-25)

**Por qué.** Para saber qué keywords ya corren en Sponsored Products había que subir un «Campaign CSV» a mano, y su
parser buscaba «Keyword Text» o «Targeting»: con un Campaign CSV de verdad el set quedaba vacío sin avisar, y sin
archivo la columna decía ❌ para todo. El search term report sincronizado no alcanzaba para reemplazarlo: sólo trae
keywords con clicks (en la base local, 49 de las 519 keywords activas de Mott & Bow US en 60 días).

**Ahora.**
- **Cuenta en lugar de archivo.** «Keywords activas en Sponsored Products» elige Cuenta y País (arranca sin cuenta:
  el MKL y el SQP no dicen de quién son) y lee el listado diario de estructura SP (migración 018): una keyword corre si
  ella y su campaña están habilitadas y su ad group no está pausado. El bloque dice cuándo se listó y cuántas corren.
- **«Sin dato» no es «no».** Sin cuenta, sin listado o con la lectura caída, «En SP» muestra «—» y la leyenda lo explica;
  la prioridad sigue tratándolas como no en SP, como antes sin archivo.
- **Análisis IA.** Pestaña nueva con el agente `sbh`: ordena hasta 10 clusters para lanzar como campaña SBH (LANZAR,
  PROBAR o DESCARTAR), propone un headline de hasta 50 caracteres y cierra con la síntesis; no recalcula prioridades ni
  propone bids. Corre sólo con «Analizar con IA» y se comparte con el chat de la app.
- Las reglas (prioridad, clusters, headline) pasaron sin cambios a `core/sbh/targets.py`, con tests por primera vez.

### Added — El chat compara períodos, filtra por métrica, arma series por semana o mes y busca niches por ASIN (2026-09-25)

**Por qué.** Lo que un AM pide de una, el chat lo armaba a mano, llamada por llamada: una serie de 10 semanas eran 11
llamadas, una comparación con el mes anterior restaba totales, «las campañas con ACoS arriba de 50 y más de 10 clicks»
se filtraba leyendo páginas, saber si la cuenta ya pauta 20 keywords eran 20 llamadas y los niches de DataDive de un
ASIN se buscaban abriendo niche por niche.

**Ahora.**
- **Cuenta por nombre.** Todas las herramientas aceptan `account` (parte del nombre) en lugar de `profile_id`. Si el
  nombre alcanza a varias cuentas, vuelven `candidates` con el gasto de cada una en la ventana, para elegir.
- **Comparar con otro período.** `breakdown`, `campaign_health` y `accounts_overview` aceptan `compare=previous` (el
  período del mismo largo justo antes) o `compare_from`/`compare_to` (días exactos, como los mismos días del mes
  anterior). Cada fila trae `delta_spend_pct`, `delta_sales_pct`, `delta_orders_pct`, `delta_acos_pp`,
  `previous_spend`, `previous_sales` y el cambio absoluto de la métrica que ordena (`delta_<métrica>`); `status` marca
  las filas nuevas (`new`) y las que dejaron de gastar (`gone`, con sus cifras en cero), y `compare_counts` las cuenta.
  `totals` trae el total anterior (`previous`), `order_by_change` ordena por el cambio y `leaders` da la mayor suba y
  la mayor baja.
- **Series por semana o mes.** `daily_metrics` acepta `granularity=week|month` y `periods`: semanas de lunes a domingo
  y meses de calendario, hasta 60 días, 26 semanas o 12 meses. Cada fila dice `period_start`, `period_end`,
  `days_with_data` y si el período está completo (`complete`), y `data_since` desde cuándo hay datos. `breakdown` con
  `by_period=week|month` da la serie de gasto y ACoS de los primeros `series_groups` grupos (10 por defecto) y su
  tendencia entre los dos últimos períodos completos, con la regla de `*_vs_previo` (subió, bajó o igual). `activity`
  dice el primer día con clicks y con gasto, desde cuándo corre la racha actual y si llega al primer día leído.
- **Campañas.** `campaign` (un nombre o un id), `campaigns` (una lista), `state` y `portfolio` eligen campañas igual en
  `breakdown`, `campaign_health`, `daily_metrics` y `campaign_structure`: primero el nombre exacto, después el id y
  recién después las que lo contienen. `matched_campaigns` dice cuáles tomó y `campaigns_not_found` las de la lista que
  no están. `daily_metrics` da la serie de las campañas elegidas, y `by_campaign` cuando son varias. Las filas de
  `by=campaign` traen `campaign_id`, `product`, `portfolio`, `state` y `daily_budget`; las de `campaign_search_term`,
  su `ad_group` y en qué otras campañas corre el término (`other_campaigns`).
- **Filtros.** Un solo objeto `filters` (`min_`/`max_` de spend, sales, orders, clicks, impressions, acos, cvr, roas,
  cpc y bid_gap, `without_sales` y `combine`, `all` o `any`) reemplaza los parámetros sueltos de `breakdown`
  (`min_orders`, `max_acos`, `min_spend`, `without_sales`) y de `campaign_structure` (`min_clicks`, `min_spend`,
  `min_acos`, `without_sales`), y llega a `campaign_health`. `sort_order=asc` ordena de menor a mayor, con los vacíos
  al final. `match_type` separa el product targeting por ASIN y por categoría.
- **Métricas por fila.** Cada fila trae `roas` y `cpc`; `ctr` y `aov` van en los totales y sirven de `sort_by`.
- **Campañas sin actividad.** `breakdown` ya no cuenta como filas las campañas sin impresiones, clicks, gasto ni ventas
  en la ventana (los reportes les guardan una fila en cero): «73 campañas con actividad» contaba 24 que no sirvieron
  nada, y una campaña que dejó de servir no salía como `gone`.
- **Keywords y targets.** `campaign_structure` con `targets` (hasta 50 keywords o ASINs) devuelve una fila por término:
  si la cuenta lo tiene (`found`), si corre (`running`), sus match types y en qué campañas está, con su bid. Keywords y
  product targets traen `cpc`, `bid_gap` (el bid menos el cpc) y `top_of_search_share`. Con `product=SB` o `SD` lista
  los keywords y targets de Sponsored Brands y Display, con `cost_type`: en una campaña VCPM el bid es por mil
  impresiones visibles y no tiene `bid_gap`.
- **Atribución por ASIN.** `breakdown` por ASIN y `asin_health` dicen cómo se atribuyó el gasto de cada ASIN
  (`attributed_by`) y en cuántas campañas se anuncia y cuántas corren (`advertised_in`); los totales traen lo que no se
  pudo atribuir (`unattributed_spend`, `unattributed_sales`). `attribution_days` va por producto.
- **New-to-brand de SB y SD.** `accounts_overview`, `breakdown`, `campaign_health` y `daily_metrics` traen
  `ntb_orders`, `ntb_sales` y `ntb_sales_share` de SB y SD. El sync de SD pide ahora las columnas new-to-brand de su
  reporte; los valores de SD guardados hasta hoy, que eran 0 porque no se pedían, pasan a vacíos: no se midieron.
- **Bid Optimizer.** `bid_suggestions` con `compare_previous` trae el precio y el bid base del tramo anterior de cada
  ASIN.
- **Análisis guardados.** `get_analysis` acepta `where` (columna → valor) y devuelve sólo esas filas, contadas.
- **DataDive** (en capybaras-ai-provider): `niches_for_asins` dice en qué niches de la organización están unos ASINs o
  una marca; `get_niche_competitors` y `get_niche_keywords` marcan los ASINs propios.
- **Prompts.** El del orquestador pide a estas herramientas las comparaciones, las series y las listas de términos, y
  el de DataDive busca los niches por ASIN antes que por nombre. Si el nombre de campaña que dijo el AM coincide con
  varias, el chat contesta por cada una en lugar de elegir una en silencio.
- **Base.** La migración `019_chat_campaign_reads.sql` agrega el catálogo de campañas, los totales por campaña, los
  keywords y targets de SB y SD y el new-to-brand de los totales. Jenkins la corre después de levantar los
  contenedores: hasta entonces, la elección de campañas usa sólo las que tuvieron actividad, y los keywords de SB y SD
  y la serie de una campaña avisan que falta la migración.

### Changed — Las herramientas del MCP entregan el dato ya calculado, para que el chat no dependa del esfuerzo (2026-09-23)

**Por qué.** Con esfuerzo `low`, las respuestas del chat fallaban donde el modelo tenía que contar, comparar o armar
una lista a ojo: repetía un conteo de la síntesis de un análisis, daba por hecho que un término ya corría en exact, o
armaba «las 10 peores» con un corte que sus filas no seguían. `xhigh` lo reducía, pero cada respuesta tarda casi el
doble.

**Ahora.**
- `get_analysis` trae `row_summary`: cuántas filas de cada grupo toman cada valor de sus categorías (diagnóstico,
  estado, prioridad), sus métricas sumadas y, por cada métrica guardada con su tramo anterior, cuántas subieron,
  bajaron o no tienen tramo previo (`*_vs_previo`), sobre todas las filas. `group`, `offset` y `limit` piden cualquier
  página de las filas, que antes quedaban cortadas.
- `search_term_candidates` dice por cada candidato a harvest si la cuenta ya lo tiene en exact —una keyword exact o,
  si el término es un ASIN, un product target `asin="…"`— (`exact_in_account`: corre, no corre o no está) y dónde
  corre, y `counts` lo cuenta; `without_running_exact` deja sólo los que no corren. Cada candidato dice si su término
  es un ASIN que la cuenta anuncia (`own_asin`), sin abrir sus product ads.
- `list_accounts` filtra por `account` (parte del nombre, sin mirar mayúsculas, espacios ni guiones): la cuenta de un
  cliente sale en una llamada, en vez de paginar la lista.
- `breakdown` da la parte de cada grupo en el total (`spend_share`, `sales_share`, `orders_share`, `clicks_share`), lo
  que gastaron sus términos sin ventas (`spend_without_sales`, desde search terms) y agrupa cada término dentro de su
  campaña (`by=campaign_search_term`).
- `campaign_health` cuenta y lista las campañas que tocaron su presupuesto algún día (`budget_capped`), cada señal por
  diagnóstico (`signal_counts`) y cada diagnóstico por producto (`diagnosis_by_product`), antes de filtrar, y filtra
  por `min_budget_capped_days`.
- `campaign_structure` cuenta los ASINs y SKUs distintos de los product ads (`distinct`): cada fila es un anuncio.
- `daily_metrics` dice el día de la semana de cada fila y, cuando la serie suma varias campañas, que cada día las suma.
- `asin_health` da en `spend_without_sales` todo lo que gastaron los términos sin órdenes de cada ASIN; lo que antes
  llevaba ese nombre, los 10 términos más caros sin órdenes, pasa a `top_unsold_terms_spend`.
- `breakdown` trae `leaders` (el de más gasto, ventas, órdenes y clicks, y el de ACoS más bajo y más alto, sobre
  todos los grupos) y filtra por `min_orders`, `max_acos`, `min_spend` y `without_sales`.
- `campaign_structure` ordena por métrica (`sort_by`) y filtra por `running_only`, `min_clicks`, `min_spend`,
  `min_acos` y `without_sales` en campañas, keywords y product targets.
- `daily_metrics` trae `before_window`: el día más alto y el más bajo de cada métrica en los 60 días sincronizados
  anteriores a la ventana, para decir «nunca» o «desde» contra la historia.
- El prompt del orquestador manda pedir las listas por criterio con esos filtros, y los líderes y conteos a
  `leaders` y `row_summary`.

### Fixed — El chat contesta con las cifras de cada cuenta y arranca con preguntas sugeridas (2026-09-23)

**Por qué.** En producción, 74 preguntas vagas de un AM (77 turnos, las de cobertura total y parcial) dieron 46 bien y
28 mal, contrastadas con SQL. Las fallas: preguntar «¿US o MX?» cuando una sola de las cuentas gastó (20 casos), dar
como total de la cuenta uno que sumaba menos, cuantificar («todas», «sólo», «sus 12») sobre una página de filas,
repetir la cantidad de una síntesis sin contar sus filas, dar como de la competencia un ASIN propio, fechar un cambio
con la foto del día o comparar meses restando totales. Además, el panel arrancaba chico y crecía al abrirse.

**Ahora.**
- **Preguntas generales y particulares.** El prompt del orquestador separa dos modos. Una pregunta general (sin cuenta
  en la pregunta, la pantalla ni la conversación) se contesta sobre todas las cuentas con `accounts_overview` y
  `list_analyses`, y el detalle se abre en hasta tres, diciendo con qué criterio y cuántas quedaron afuera. Una
  particular usa la cuenta de la pantalla o de la conversación sin preguntar; si no hay, pregunta una vez proponiendo
  una con su razón. Entre cuentas homónimas elige la única que gastó y nombra las otras.
- **Cifras.** Cada cantidad lleva su denominador y su filtro y se cuenta sobre filas traídas enteras, nunca sobre el
  texto de una síntesis; una cantidad chica va con sus filas nombradas; el titular se escribe desde las filas y dice
  sólo lo que cumplen todas; un «empezó» o «dejó de» necesita los días de antes; la atribución se nombra por producto
  (7 días en SP para un seller, 14 en SB y SD); el share de top of search es de impresiones, no de ventas; cada parte
  de la pregunta tiene su respuesta; un pedido de redactar da el borrador con corchetes para lo que no se ve.
- **DataDive.** Los niches del cliente se buscan por cada producto y por las palabras de sus campañas, se abren todos
  los que devuelve la búsqueda, se cruzan todos los ASINs de sus product ads y la conclusión se dice sobre los niches
  abiertos dentro de la primera oración, la que contesta: ninguna herramienta busca niches por ASIN.
- **Esfuerzo.** Los ocho agentes corren con `effort: xhigh` (antes `high`). Se midió en el chat: sobre las 10
  preguntas que fallaron en la última pasada, `xhigh` contestó bien 8 y `high` 7; `xhigh` no tuvo ningún desliz de
  conteo, `high` tuvo 3. La respuesta tarda más: 201 s de promedio contra 107 s en esas 10. El costo no se midió, y en
  los análisis de los módulos el cambio no se midió. Los tests ya no fijan el esfuerzo de ningún agente.
- **Herramientas del MCP.** `accounts_overview`, `daily_metrics` y `breakdown` aceptan `date_from`/`date_to` (el mismo
  período exacto para todas las cuentas, sin restar totales); `accounts_overview` y `list_accounts` paginan;
  `campaign_health` trae `signal_rules`; `campaign_structure` filtra con `target` keywords, product targets, negativos
  y product ads por ASIN o SKU (saber si un ASIN es propio es una llamada), primero los que son exactamente ese texto
  (`exact_matches` dice cuántos), y da el estado de la campaña
  (`campaign_state`) en todo lo que cuelga de ella; `list_analyses` y `get_analysis` avisan que las cantidades de la
  situación y la síntesis se comprueban contando filas; `daily_metrics` con `campaign` aclara que las campañas que
  nombra son las que figuran en los reportes del período.
- **Panel.** Arranca con «Capybaras Assistant», un saludo y preguntas sugeridas que se envían con un click, sacadas de
  un pool de 21 (las de la pantalla primero) y distintas en cada conversación. El escenario tiene el mismo alto en
  todos los estados (`min(52vh, 480px)`): no salta al abrirse ni mientras llega la respuesta.

**Resultado.** Con las mismas 74 preguntas, en local: 60, 62 y 64 bien en tres pasadas completas con `high`. Las 10 que
fallaron en la última se re-corrieron con `xhigh` y contestan bien, contrastadas contra la base local, las herramientas
del MCP y DataDive en vivo. No se hizo otra pasada completa con `xhigh`.

**Reglas compartidas.** El repaso contra las herramientas antes de escribir, traer las páginas que faltan de un
listado y la cuenta propuesta con su razón están en `ai/agents/_shared/chat.md`, así que valen para el chat de todos
los módulos. Eso y el esfuerzo cambian el `agent_version` de todos los agentes: los análisis guardados figuran de la
versión anterior del prompt hasta su próxima corrida. El resto de las reglas va en el prompt del orquestador.

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
