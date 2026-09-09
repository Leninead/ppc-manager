# CHANGELOG — Agency OS Capybaras

Registro de cambios, mejoras y decisiones de diseño del PPC Manager.

---

## [Unreleased]

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
