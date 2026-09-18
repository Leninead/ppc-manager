# CLAUDE.md — Módulos del Agency OS
## Contexto por módulo para agentes especializados
Última actualización: 2026-09-01

---

## Tab IA reusable — `core/ai_tab.py` (2026-09-01)

Capa intermedia entre el pipeline determinístico de un módulo y `ai/` (el
gateway al ai-provider): ciclo de vida del análisis (`decide_analysis_action`
pura + `resolve_analysis` con staleness de dos velocidades: archivo nuevo
re-dispara solo, cambio de parámetro pide click), polling (`render_analysis`),
kit de render localizado (`ai_labels`, `opinion_table_html`, `synthesis_html`,
`ai_chips_html`, `ai_notice_html`, `escape_ai_text`, `humanize_fields`,
`AI_CSS`) y la publicación al chat único de la app (`publish_analysis_to_chat`,
ver "Chat IA de la app" abajo).
`synthesis_html` titula cada bloque con `synthesis_section_title` (labels
`actions_title` "Acciones sugeridas para esta semana", `mid_term_title`
"Mediano plazo · 2 a 4 semanas", `risks_title`; los `*_hint` van como tooltip):
la lista numerada son sugerencias de corto plazo a validar por el AM, nunca
acciones ejecutadas. `humanize_fields(text, glossary)` es la red determinista
contra nombres técnicos de columna en la prosa de la IA (el módulo declara el
glosario es/en; ver M3). Las filas de `opinion_table_html` llevan `row_id`
(N07 / Q03 / K12) y la tabla lo imprime delante del ítem: la síntesis cita
esos ids y sin verlos el AM no puede ubicar la fila. Todo módulo que arme
filas de opinión pasa el id que ya usa para el join posicional. Además, la
prosa (síntesis, resumen ejecutivo y respuestas del chat) se anota de forma
determinista con el término detrás del id, primera mención por texto y sin
duplicar cuando el modelo ya lo escribió: `annotate_row_ids(text, {id: término})`
sobre `map_synthesis_text`, y `publish_analysis_to_chat(..., annotate=)` para el
chat. Cada módulo expone su mapa (`_str_row_labels`, `_sqp_row_labels`,
`_dd_row_labels`) a partir de los records guardados por digest.
Los records por digest los guarda `ai_tab.records_for_render(slug, analysis,
payload, records)` (un análisis STALE cruza contra SU payload; se conservan
los últimos 8 digests) y el idioma sale de `ai_tab.app_language()` (radio
`app_lang` del sidebar): ningún módulo reimplementa esas dos cosas. `make_ids`
vive una sola vez en `ai/agents/__init__.py` y cada `context.py` lo re-exporta.

### Chat IA de la app — `core/app_chat.py` (2026-09-15)

Un solo chat, montado una vez al final de `app.py` (`app_chat.mount_app_chat(selected)`),
en todas las pantallas y para todos los usuarios; con `AI_ENABLED=0` no se monta. Lo
atiende el agente `ai/agents/orchestrator/` (herramientas `amazon_ads, datadive`), que
elige la fuente según la pregunta: los análisis de la app, Amazon Ads o DataDive. Los
módulos ya no montan chats propios.

- **Qué lee.** Sólo lo que cada página comparte en la sesión, por módulo (`share_analysis`,
  `keep_current`, `mark_outdated`, `report_running`, `report_failed`, `withdraw_analysis`).
  Las otras cuentas no se pegan en el prompt (desde 2026-09-18): el modelo las lee por el
  servidor MCP de la app (`services/mcp_server`) cuando la pregunta lo pide —`list_analyses`
  trae la situación y el target de cada análisis guardado, `accounts_overview` los totales en
  vivo de todas las cuentas, `get_analysis` el detalle de una, `campaign_health` las campañas
  de una cuenta con el diagnóstico y las señales de M6—, así el contexto de cada turno no crece
  con cada cuenta nueva.
- **Row ids.** Donde viaja la tabla (el análisis en pantalla) los ids se anotan con su
  término (`annotate_row_ids`); en síntesis sin tabla (resúmenes por cuenta, análisis
  anteriores) cada id se reemplaza por «término» (`replace_row_ids`,
  `ai/agents/row_annotation.py`): los mismos N07 nombran otro término en pantalla. Cada
  respuesta se anota una vez, al llegar (`shown` en el historial), y así se muestra y se
  arrastra: navegar a otro análisis no la vuelve a anotar.
- **Qué comparte un tab con análisis en memoria** (`ai_tab.publish_analysis_to_chat`): los
  documentos que leyó su agente más `reading(result)`, la lectura de la IA como texto
  (`ai/agents/sqp/chat_document.py`, `ai/agents/datadive/chat_document.py`; STR con archivo
  reusa `chat_context.current_analysis_text` vía `in_memory_analysis`). Los títulos empiezan
  con `módulo · tema`. Se arman una vez por análisis; uno STALE queda marcado como
  desactualizado sin reconstruirse; uno corriendo guarda su digest y cómo armar sus
  documentos, y `mount_app_chat` lo termina desde cualquier página con `ai_runtime.get`.
- **STR con datos de API** (`_share_stored_analysis`) comparte el análisis guardado y los
  anteriores con el estado real de la pestaña: vigente, generándose, falló o sin análisis
  (`AnalysisState.MISSING`), que la nota distingue de "análisis disponible".
- **Sesión.** `context_key` depende sólo de los análisis que comparten las páginas del AM,
  nunca de la página ni de los resúmenes por cuenta (cambian con el análisis de cualquier
  cuenta y reiniciarían a todos). Al abrirse otra sesión, ese turno lleva la conversación
  visible (`runtime.conversation_document`: texto anotado, sin turnos fallidos, turnos
  enteros). La región de Amazon Ads se elige al abrir la sesión y se mantiene
  (`_session_country_hint`). La página y el estado de los análisis viajan en cada turno como
  nota (`turn_note`), fuera del hilo.
- **Dos funciones, no valores.** `floating_chat(session_key=, turn=)`: `app_chat.chat_session_key`
  corre en cada render de cada pantalla y es barata (sólo los análisis de la sesión, sin leer nada);
  `app_chat.chat_turn(page)` corre sólo al enviar, que es cuando hacen falta los documentos, la
  cuenta de Amazon Ads y la nota — y porque el cuerpo del chat es un fragmento: lo que la página
  calculó en su última corrida completa ya no sirve si un análisis terminó mientras tanto.
- **Sin `/health` al montar.** Las herramientas se resuelven al enviar; montado en todas las
  pantallas, consultarlas al montar trabaría cada pantalla con el provider caído.
- **Input del panel.** La clave del textarea cambia con cada turno: con `clear_on_submit` la
  pregunta enviada volvía a aparecer en la siguiente corrida completa (cualquier navegación).
- **CSS del panel.** El body del popover se matchea con `:has(.st-key-aichat_app_panel)`:
  el selector global anterior cambiaba el look de todos los popovers de la app.

**Anti-patterns.**
- ❌ NO montar un `floating_chat` desde un módulo: se superpone con el de la app en la misma posición.
- ❌ NO leer `ai.runtime._registry` para el chat: es de todo el proceso, con análisis de otros AMs.
- ❌ NO editar `ai/agents/_shared/chat.md` para el orquestador: entra en el `agent_version`
  de los análisis guardados y en la huella de los de memoria. Lo suyo va en su `prompt.md`.
- ❌ NO poner la página en la clave de sesión: cada navegación reiniciaría la conversación del modelo.

**Reglas de lectura compartidas (2026-09-02).** Los tres prompts (`str`, `sqp`,
`datadive`) llevan un bloque `<lectura>` idéntico: la primera oración de la
situación se entiende sin cifras ni tabla, los conceptos técnicos se traducen
la primera vez, los nombres internos del sistema (rollup, shares ponderados,
etapa dominante de fuga, cobertura, materialidad, gate, pre-flag) nunca se
escriben, una o dos cifras por oración, sin metáforas; el `executive_summary`
(texto para Slack, cifras primero) es la única excepción. El runtime solo
anexa `_shared/chat.md`, por eso el bloque se copia en cada prompt y
`tests/test_agent_prompts.py` exige que las tres copias sean idénticas. La spec
de `situation` del SQP pasó de "anclada en los shares ponderados y la etapa
dominante del rollup" (siete cifras en tres oraciones) a tres oraciones con rol
fijo: qué pasa, evidencia, tipo de problema. El contrato de uso
completo está en el docstring del módulo; tests en `tests/test_ai_tab.py`.
Keys de sesión: `<slug>_ai_*`. **Todo módulo con tab IA consume esta capa —
no implementa el wiring a mano.** Los primeros consumidores (STR y SQP) se
migran en sus propias ramas/tickets.

---

## M1 — Inicio
**Archivo:** modules/pages/inicio.py
**Sección sidebar:** —
**Session state prefix:** —

### Propósito
Dashboard de estado del Agency OS. Muestra 26 módulos agrupados por sección, Workflow Wizard piramidal (5 niveles), changelog y estado del Parent-Child map.

### Arquitectura
- 3 cards activas: PPC (10 módulos) + Account (7) + Research (7) + Intelligence (2)
- KB card full-width
- Flujo guiado 5 niveles: Subí datos → Analizá → Inteligencia → Ejecutá → Reportá
- Parent-Child map: detecta automáticamente si hay BR en data/business_report/

### Reglas de negocio
- No requiere uploads — es informativo
- Actualizar cada vez que se agrega un módulo nuevo

### Anti-patterns
- No agregar lógica de procesamiento de datos en inicio.py
- No hardcodear el conteo de módulos — leer de _PAGES

---

## M2 — Search Term Report (STR)
**Archivo:** modules/pages/search_term_report.py (~1,000 líneas)
**Sección sidebar:** PPC
**Session state prefix:** str_

### Propósito
Analizar search terms de campañas SP: negativizar, harvestear, clasificar por tipo y estado. Es el módulo más usado — punto de partida del flujo semanal.

### Arquitectura
5 tabs: Dashboard (12 KPIs + filtros + charts) | Negatives Mining (umbral dinámico por CVR) | Harvest Candidates (anti-canibalización) | Análisis IA (capa `core/ai_tab` + agente `ai/agents/str`) | Por Campaña (groupby)

### Fuente de datos (2026-09-14 — ingesta desde Amazon Ads API)
- El uploader dejó de estar en `render()`: los datos llegan de `render_source_picker()` (`modules/pages/search_term_source.py`), que devuelve un `SearchTermSource` (`core/search_term_frame.py`) o `None`. `df_raw = source.frame`; de ahí para abajo el módulo no sabe de dónde vino la tabla.
- **Con cuentas de Amazon Ads sincronizadas** el bloque "Datos de Amazon Ads" elige Cuenta, País (un perfil = una moneda) y Período (7/14/30/60 días o rango, tope 60), muestra el pill de frescura y ofrece "Actualizar ahora" (`request_manual_refresh`, 30 min de espera, nunca corre la ingesta en el render). Los datos cargados quedan fijados por perfil: una ingesta más nueva ofrece "Cargar datos nuevos" y recién ahí cambia `source.signature`, que es lo que re-dispara el análisis IA. La tabla guarda solo la versión más nueva de cada día, así que un rango que no está en memoria (otro período, o una carga que salió de la sesión) no se puede leer en la versión fijada: el selector fija la más nueva antes de leerlo. Si no, las filas nuevas llegarían con la firma vieja. Sin cuentas, sin base o con la lectura caída: el uploader de siempre.
- **Archivo manual** ("Subir archivo manualmente"): `core/search_term_file.py` reconoce el export viejo de la consola (se pasa tal cual) y el CSV nuevo de 2026 ("Search term", "Total cost", "Budget currency", IDs de cuenta/campaña/ad group) que traduce a las columnas canónicas calculando ACoS/CTR/CPC/CVR. Si el CSV trae varias cuentas de anunciante, se elige la cuenta del archivo; una cuenta que anuncia en varios marketplaces (filas en USD y en MXN, por ejemplo) se separa por moneda, nunca se suma. Los IDs vienen escritos como `="…"` para Excel y se limpian al leerlos. El archivo nunca se guarda ni se mezcla con la base.
- **Moneda: indicador, nunca selector ni conversión.** Sale del perfil de Amazon o de la columna de moneda del archivo; los montos se formatean con `core/currency_format.money()` (`MX$`, `CA$`, `¥` sin decimales; sin moneda conocida queda el `$` de siempre).
- Datos de API y archivo manual comparten la forma canónica (`console_columns()`), con los IDs ocultos al final (`_campaign_id`, `_ad_group_id`, `_keyword_id`, `_keyword_type`, `_origin_match_type`, ...). Ningún nombre oculto puede contener "portfolio", "sales", "click", etc.: `_detect_cols` toma la primera columna que matchea. Los tests de `core/search_term_frame.py` y del provider usan `_detect_cols` real como oráculo.
- El picker es un componente reutilizable: todas sus keys empiezan con `f"{key_prefix}_src_"` (M2 usa `str`). Otro módulo que quiera los mismos datos lo llama con su propio prefijo.
- Estados del picker: primera carga en curso, **primera carga fallida** (pill rojo, detalle saneado y botón «Subir archivo manualmente»; nunca apunta al Registro, que es admin), reintentando, al día y desactualizada. Si una lectura falla después de haber cargado datos del mismo perfil, muestra el error y deja los últimos datos buenos a la vista.
- Las elecciones (cuenta, país, período, cuenta del archivo) y los inputs de M2 sobreviven a un rerun donde el widget no se dibuja (`_park_inputs` / `_restore_parked_inputs`). El uploader de anti-canibalización de Tab 3 es la excepción: Streamlit no deja restaurar un `file_uploader`.

### Capa IA (2026-09-01 — consumidor de `core/ai_tab`; análisis guardados desde 2026-09-15)
- **Un solo constructor del payload**: `core/search_term_analysis.build_analysis_input(frame, cols, params, currency_code, lang)` arma `StrData` y los records, y lo usan M2 y el worker de análisis. Mismos datos + mismos parámetros → misma huella (`ai/agent_call.build_agent_call(...).input_digest`). Por eso el payload no lleva la fecha ni el Target ACoS de la pestaña 1, los brand terms van normalizados (minúsculas, sin repetidos, ordenados) y el proveedor desempata el orden de filas por IDs. `agent_version` (prompt, schema, modelo) va aparte: un cambio de prompt no invalida análisis de los mismos datos. Las tablas del payload se escriben con fin de línea `\n` fijo (`to_csv(lineterminator="\n")`): con el de pandas por defecto, la misma cuenta daba otra huella en Windows que en Linux.
- **Datos de Amazon Ads: análisis guardado** (`ai_analyses`, migración 010). El worker `ads-ai-worker` (`core/ai_analysis/`) lo genera solo para los últimos 30 días con los parámetros de la cuenta (`ai_analysis_settings`) cuando cambian los datos o los parámetros, y nunca paga dos veces la misma huella. La pestaña 4 busca el análisis de exactamente lo que está en pantalla: si existe lo muestra con SUS records y SUS brand terms; si se está generando muestra el estado y nunca un análisis anterior; si falló, el error y "Reintentar"; si no hay, "Generar análisis IA" (manual). Pedirlo guarda los parámetros como parámetros de la cuenta (`save_ai_analysis_settings`) y encola con `request_ai_analysis`. Al abrir una cuenta, los inputs se cargan con sus parámetros guardados (o los default de su moneda). El análisis cubre todos los portfolios aunque haya filtro, e ignora el Campaign CSV de anti-canibalización (es un archivo manual).
- **Archivo manual: en memoria, como antes** (`ai_tab.resolve_analysis`, auto-fire con archivo nuevo), pero con `show_previous=False`: un parámetro nuevo oculta el resultado anterior y ofrece el botón. Si falta un precio, `auto_fire=False`: el AM está en la pantalla que se lo pide, así que no se paga un análisis sin precio antes de que lo escriba; con los dos precios cargados se dispara solo. Nada de un archivo llega a la base: `web_user` no puede escribir `ai_analyses`.
- **Worker, casos de borde**: un pedido manual cuyos datos cambiaron desde que el AM lo pidió falla sin llamar a la IA (`DATA_CHANGED_ERROR`: la pantalla busca la huella de lo que el AM vio); uno programado cuyos parámetros de cuenta cambiaron se cierra sin llamar a la IA (`SUPERSEDED_WARNING`); una huella cuyo pedido ya falló no cuenta como "cubierta" sino como error del tick. La espera HTTP es el límite del provider más 60 s, para que llegue su propio 504.
- **Chat con datos de API**: la página comparte con el chat de la app (`_share_stored_analysis`) los documentos de `core/ai_analysis/chat_context.analysis_chat_documents`: el análisis vigente con cada opinión y su término, y la síntesis de los últimos 3 análisis de la cuenta, con el país del perfil para la región de Amazon Ads. Con archivo manual comparte vía `ai_tab.publish_analysis_to_chat`.
- El precio de harvest arranca vacío fuera de USD, como el de negativos. Sin precio el análisis se genera igual (decisión de Juan, 2026-09-15): sin precio de negativos no corre R3, sin precio de harvest no hay "Bid Sugerido"; Parámetros se lo dice al modelo (`_missing_price_notes`, vacío cuando hay precio, para no cambiar la huella de los análisis con precio) y la pestaña 4 lo avisa (`_missing_price_notice`). Nada inventa un precio: el que se escribe en M2 manda. Precio estimado con ventas/unidades o por moneda: pendiente de validación de Lenin.
- "Bid Sugerido" sigue INV-1 (`suggested_bid`): CVR hasta 100%, piso 0.10 y nunca más que precio × target ACoS. Antes no tenía techo: en Shapermint US 686 de 4.167 filas pasaban el techo ($63 contra $9).
- Payload `StrData` (`ai/agents/str/context.py`): KPIs de la cuenta, agregado por campaña (top 40 por spend, o por clicks sin columna de costo), negativos Alta/Media top 120, harvest top 60, parámetros, `cost_detected`. La IA nunca recalcula: opiniones por `row_id` posicional (`N01…`/`H01…`) sobre los MISMOS records serializados.
- Schema de salida: `negativos[]`/`harvest[]` (`razon` → `categoria` → `advertencia`), `campanas[]` y `synthesis` en la forma canónica de la plataforma `{situation, week_actions, mid_term, risks[{type, detail, urgency}]}`.
- Filas de display (`_str_ai_rows`, puras y testeadas): pills de métricas + campaña, badge de categoría y pista determinista "revisar categoría" cuando la categoría contradice los brand terms.
- Tests: `tests/test_str_ai_context.py` (contrato del agente, digest, runtime con fake transport, filas de display), `tests/test_search_term_analysis.py` (constructor y huella), `tests/test_str_analysis_job.py` (planificación, ejecución, worker), `tests/test_ai_analysis_chat_context.py` y los de pestaña 4 en `tests/test_search_term_source.py`.

### Reglas de negocio
- ACoS = Spend / Sales × 100
- Umbral de clicks para negativizar: `max(10, round(2 / CVR))` sobre el CVR del período (INV-3). Los tiers LOW/MID/HIGH por precio NO son de este módulo: viven en M11.
- Escalar: 3+ orders AND ACoS < 50% target
- Winners: 2+ orders
- Term type: Brand (contiene brand terms) / Generic / Long-tail (3+ palabras)
- Columna _estado: Escalar / OK / Reducir / Revisar / Negativa?
- Anti-canibalización: cruza con Campaign CSV, marca duplicados Exact activos

### Negatives Mining y bulk (2026-09-14 — alineado a `.claude/skills/ppc-business-invariants.md`)
- Las reglas viven en `core/search_term_negatives.py` (puro, testeado) y cada candidato lleva una **Acción**: R2/R3/R5 → `Negativo`; **R4 (ACoS > 70 con 1-4 órdenes) → `Bajar bid`**, nunca negativo (INV-2, INV-11.4); **R1 (pocos clicks sin venta) → `Revisar manualmente`**, nunca al bulk (INV-3). Un término con órdenes nunca es `Negativo`. Match types en Title Case (`Negative Exact`/`Negative Phrase`).
- **El bulk de negativos (nivel ad group) se habilita sólo con datos de API** (`source.bulk_ready`): `select_for_bulk(candidates, frame, released_ranking=...)` → `core.bulk_export.build_adgroup_negative` → `write_bulk_excel`. Quedan afuera, con el motivo en pantalla: el término aparece con origen Exact o Product Targeting en cualquier fila del mismo ad group (INV-11.1), campaña no habilitada, `*`, términos ASIN o ISBN, texto que Amazon rechaza (`negative_keyword_text_problem`: 80 caracteres, 4 palabras en Phrase, 10 en Exact, símbolos prohibidos), una Negative Phrase que bloquearía un término que convierte o una Exact activa del mismo ad group (plurales s/es cuentan igual), un negativo igual a una keyword propia del ad group, términos que ya corren como Exact activa (INV-11.2), duplicados, y términos con órdenes en cualquier ventana (7 o 14 días) en el mismo ad group.
- **INV-11.1 se aplica solo al bulk** (decisión de Juan, 2026-09-15, pendiente de validación de Lenin): con datos de API, los términos de origen Exact o Product Targeting siguen en la tabla de candidatos, en su Excel y en el payload de la IA con su Acción (`Negativo` si cumplen R2/R3/R5). El texto de INV-11.1 pide sacarlos antes; si Lenin lo confirma, el filtro va en `evaluate_candidates`.
- **Portfolios RANKING y portfolios sin nombre** (INV-11.3): quedan afuera por defecto y se liberan **uno por uno** con la casilla «Liberar» (`st.data_editor`); la clave es `negative_key(candidate)`. Sólo esas exclusiones son liberables (`BulkExclusion.releasable`).
- Guards **parciales**, dichos en pantalla: la Exact activa y las keywords propias sólo se ven si tuvieron clicks en el período, y el estado del ad group no se verifica (se toma el estado de la campaña de su fila más nueva).
- **Moneda distinta de USD**: el precio del producto arranca vacío (clave por moneda); mientras falte, R3 no corre, el bulk queda deshabilitado y el análisis IA se genera sin R3 ni bids sugeridos, con aviso.
- Sin órdenes en el período, R2 usa un CVR de referencia del 10% y la pantalla lo aclara; la IA recibe el CVR medido.
- Con archivo manual el bulk sigue deshabilitado: el export de la consola no trae el match type de origen que exigen esas reglas.
- Todo `.xlsx` que baja M2 pasa por `core.excel_text.force_text_cells`: un término que empieza con `=` queda como texto, no como fórmula.

### Cuentas grandes (2026-09-15)
Con datos de API una cuenta puede traer cientos de miles de términos (medido: 177.843 en 30 días).
- **Tablas**: se dibujan como máximo `TABLE_ROW_LIMIT` (1.000) filas con `_drawn_rows`, con el aviso de `_drawn_rows_caption`. El orden del recorte es el de la vista (por gasto en "Todos", prioridad y gasto en negativos, prioridad y órdenes en harvest). El Styler se aplica sobre el recorte: `st.dataframe(styler)` revienta pasadas las 262.144 celdas (`styler.render.max_elements`).
- **Scatter**: los `SCATTER_POINT_LIMIT` (2.000) términos de mayor gasto.
- **Excel**: `_xlsx_download` arma el archivo al vuelo hasta `EAGER_EXPORT_ROW_LIMIT` (5.000) filas; más grande, pide "Preparar el archivo" y lo guarda en sesión con un fingerprint de los filtros que lo afectan. Un filtro nuevo invalida el archivo preparado. Lo guarda antes de cerrar el spinner: un clic durante el armado corta la corrida en la siguiente llamada a `st`. Trae todas las filas de la vista; en harvest, `_harvest_export_rows` saca las que ya corren como Exact salvo que se pida incluirlas, y el aviso del recorte cuenta esas mismas filas.
- **Cálculo por columnas**: `_classify_statuses` (np.select), `_harvest_candidate_rows`, `_missing_data_reasons`; `ad_group_guards(frame)` se calcula una vez y se pasa a los dos `select_for_bulk`. Cambiar una regla es cambiarla ahí, no volver a `df.apply(axis=1)`.

### Inputs
- Datos de Amazon Ads (cuenta + país + período) o STR (.xlsx o .csv) subido a mano
- Campaign CSV (.csv) — opcional (Tab 3 anti-canibalización)
- Target ACoS (slider) + Precio — Tab 2
- Brand terms (texto) — detección manual

### Anti-patterns
- Negativizar sin cruzar contra Exact activo
- No usar thresholds fijos — usar fórmula dinámica por CVR
- ❌ NO convertir montos entre monedas ni sumar perfiles de países distintos
- ❌ NO leer `ads_search_term_daily` directo desde una página: se lee con `ReportProvider` (ver "Datos de Amazon Ads para otros módulos")
- ❌ NO disparar la ingesta desde el render: la página sólo pide `request_manual_refresh`; el worker hace el resto

---

## M3 — Search Query Performance (SQP)
**Archivo:** modules/pages/search_query_performance.py
**Sección sidebar:** PPC
**Session state prefix:** sqp_

### Propósito
Analizar el mercado total desde Brand Analytics: impression share, click share, purchase share por query.

### Arquitectura
4 tabs: Vista General | Market Share | Gap Analysis | Análisis IA (capa `core/ai_tab` + agente `ai/agents/sqp`)

### Capa IA (2026-09-01 — consumidor de `core/ai_tab`)
- Señales deterministas ADITIVAS solo para la IA: `_compute_funnel_signals(df, query_col, brand_terms)` (cascada de shares en 4 etapas con Cart Adds, índices marca-vs-mercado-sin-marca, gaps de precio por etapa con bandas fijas, gate de datos, `is_invisible`, gemas, breach de defensa BRANDED 80%, `opp_usd` sobre compras reales, prioridad) + `_compute_account_rollup` (agregados ponderados + pre-flags de riesgos). Las tabs 1-3 y `_compute_market_share`/`_compute_gaps` no las usan ni cambiaron. Spec de dominio: `notes/modules/m3-sqp-ai-signals-spec.md` (vault).
- Tab 4 consume la plataforma igual que M2: `resolve_analysis` → `render_analysis` → `_render_sqp_ai_result` → `publish_analysis_to_chat` (el chat anota con `_sqp_chat_annotation`: glosario + query detrás del row_id). Input propio: brand terms (prefill = marca detectada; en CSV puede venir vacío). Records top-40 guardados por digest en `sqp_ai_records_store`.
- Agente `ai/agents/sqp/`: `SqpData`, row_ids `Q01…`, taxonomías cerradas (`funnel_diagnosis` ×8 incl. MERCADO_DEBIL, `price_causality` ×4, `action` ×9, `confidence`) y `synthesis` canónica con `risks` = exactamente los pre-flags true + 2 standing.
- Nombres legibles (2026-09-02): el prompt lleva un bloque `<glosario>` (columna → nombre llano es/en, formato de conteos con miles y shares con %) y PROHÍBE nombres de columna en la prosa; los ejemplos del prompt ya no usan `imp_share`/`clk_b`. Red determinista: `_SQP_FIELD_NAMES` (es/en, cubre todo `_ROW_COLS`; test lo exige) viaja en `labels["field_names"]` y `_sqp_ai_rows`/`_humanize_synthesis` reescriben cualquier fuga con `core.ai_tab.humanize_fields` antes de imprimir. Medido en la corrida real previa al glosario: 200+ tokens crudos (`opp_usd`, `pur_t`, `is_invisible`…) en 40 filas.
- Tests: `tests/test_sqp_signals.py` (anti-placebo, bordes, oráculo de integridad vs los % del export, filas de display) + `tests/test_sqp_ai_context.py` (contrato, digest, runtime con fake transport).

### Reglas de negocio
- read_sqp() con skiprows=1
- Brand extraída con extract_sqp_brand() desde row 0 (frágil en CSV: puede devolver None)
- IS > 30% = Dominando | 10-30% = Competitivo | <10% = Oportunidad
- Gap: Total Impressions > 1000 AND Brand Impressions = 0
- CVR en las señales IA = purchases/impressions (≠ CVR por clicks del STR); purchases con ventana de atribución 24h

### Inputs
- SQP .xlsx/.csv (Brand View, Simple View semanal)
- Brand terms (input en tab IA)

### Anti-patterns
- No usar skiprows=1 → headers mal detectados
- NO volver al patrón botón + `core/ai_analyze._build_sqp_prompt` (legacy reemplazado; la función quedó dead code re-exportada por `core/__init__`)
- No mandar el `Revenue Potencial` (inflado por impresiones) al payload IA — la IA prioriza por `opp_usd`

---

## M4 — Análisis Cruzado STR vs SQP
**Archivo:** modules/pages/analisis_cruzado.py
**Sección sidebar:** PPC
**Session state prefix:** cruzado_

### Propósito
Cruzar STR (lo que capturan tus campañas) con SQP (lo que busca el mercado). Output: Plan de Acción bulk que es el input del Campaign Builder (M10).

### Arquitectura
3 tabs: Cruce (oportunidades) | Plan de Acción (ESCALAR/AGREGAR/HARVEST/BAJAR BID/MONITOREAR) | PPC Insights por ASIN (BR opcional)

### Reglas de negocio
- Opportunity Score = min-max de impresiones + clicks + purchase rate
- Acciones: ESCALAR (IS bajo + mercado comprando) | AGREGAR (solo en SQP) | HARVEST (en STR, buen ACoS) | BAJAR BID (ACoS > 2× target) | MONITOREAR
- Export bulk: formato Plan de Acción compatible con Campaign Builder

### Inputs
- STR (.xlsx, .csv) — requerido
- SQP (.xlsx) — requerido
- BR by ASIN (.csv, .xlsx) — opcional (Tab 3)

### Anti-patterns
- No detectar marca manualmente si SQP no la extrae automáticamente

---

## M5 — Tendencia Multi-Semana
**Archivo:** modules/pages/tendencia_multisemana.py
**Sección sidebar:** PPC
**Session state prefix:** tend_

### Propósito
Ver evolución de queries a lo largo de 2-4 semanas para detectar tendencias estacionales.

### Arquitectura
Upload hasta 4 SQPs → pivot por Search Query → clasificación ↑→↓

### Reglas de negocio
- ↑ >10% creciendo | → estable | ↓ >10% cayendo
- Bug histórico: KeyError al subir dos SQPs iguales — fix aplicado 2026-03-19

### Inputs
- 2-4 archivos SQP (.xlsx) — mismo formato, semanas distintas

### Anti-patterns
- Subir el mismo archivo dos veces — KeyError en pivot

---

## M6 — Bulk Campañas + Campaign Analyzer
**Archivo:** modules/pages/bulk_campanas.py
**Sección sidebar:** PPC
**Session state prefix:** bulk_

### Propósito
Visualizar el bulk de campañas y diagnosticar con semáforo automático (PAUSAR/REVISAR/ESCALAR/FANTASMA).

### Arquitectura
3 tabs: Vista General (raw) | Campaign Analyzer (diagnóstico semáforo con naming check y target graduation) |
Análisis IA (análisis guardado de la cuenta, agente `ai/agents/bulk_campaigns`).

### Reglas de negocio
- Filtro por State == "ENABLED"
- PAUSAR: spend > threshold AND orders = 0
- REVISAR: ACoS > target × 2
- ESCALAR: ACoS < target × 0.5 con órdenes
- FANTASMAS: 0 impresiones activas
- Las pausas se ejecutan MANUALMENTE en Campaign Manager — no desde este bulk
- **La regla vive en `core/amazon_ads/campaign_analyzer.py`** (`analyzer_frame`, `diagnose`, `with_diagnosis`,
  `with_signals`), no en la página: la usan M6, el worker de análisis y la herramienta `campaign_health` del MCP, que
  tienen que clasificar igual. La imagen del MCP sólo copia `core/amazon_ads/`, `core/ai_analysis/` y
  `core/integrations/`: por eso el módulo vive ahí y no importa nada de `modules/`.

### Señales (2026-09-18 — sólo con datos de Amazon Ads)
Columna «Señales» del Campaign Analyzer, aparte del diagnóstico (que no cambia):
- **Limitada por presupuesto**: presupuesto diario, días con gasto ≥ 95% del presupuesto ≥ min(3, días del período),
  con órdenes y ACoS ≤ target. Una campaña que vende bien y se queda sin plata no es para pausar.
- **Nueva**: menos de 14 días desde el inicio. Pocos datos todavía.
- **Baja visibilidad**: Top of Search share < 10% y diagnóstico PAUSAR o REVISAR.
- Los últimos 2 días del período se marcan como provisorios (Amazon todavía ajusta atribución).
- Salen de `campaigns_between` (migración 014): `budget_capped_days` (con el presupuesto del día si el reporte lo trajo,
  si no el de la foto), `days_with_impressions` y `top_of_search_is` ponderado por impresiones. El reporte
  `spCampaigns` ahora pide `campaignBudgetAmount` y `topOfSearchImpressionShare` (0-100, vacío si Amazon no lo reporta:
  queda desconocido, nunca 0). Sin la migración `signal_inputs` es `None` y la columna no aparece.
- Con archivo manual no hay señales: el CSV no trae presupuesto por día ni share.

### Capa IA (2026-09-18 — análisis guardado, igual que M2)
- **Sólo con datos de Amazon Ads.** El worker `ads-ai-worker` genera `ai_bulk_campaigns_analysis`
  (`core/ai_analysis/campaign_analysis_job.py`, spec sobre `AnalysisRunner`) para los últimos **7 días** con los
  parámetros guardados de la cuenta (`ai_analysis_settings`, módulo `bulk_campaigns`). La ventana y la frescura salen de
  la última solicitud `sp_campaigns` completada (`source_job_kind` + `data_view` del spec), nunca de `ads_profile_sync`.
- La pestaña 3 busca el análisis de exactamente lo que está en pantalla (misma huella): vigente, generándose, falló
  con "Reintentar" o "Generar análisis IA". Con archivo manual muestra una nota, como M9: no hay análisis en memoria.
- **Payload** (`core/campaign_analysis.build_analysis_input`): Parámetros + CSV de campañas habilitadas con `row_id`
  `C01…` (hasta 60: primero las marcadas —diagnóstico ≠ OK o con señal— y después por gasto). La IA opina sobre
  hasta 12 campañas: `causa` (9 cerradas), `veredicto` ACTUAR/ESPERAR/INVESTIGAR, `confianza`, `advertencia`, más la
  `synthesis` canónica. **Nunca cambia el diagnóstico**: lo explica o lo pone en duda.
- Se comparte con el chat vía `app_chat.share_analysis` (con `profile_id`), y el chat lo lee por
  `list_analyses` / `get_analysis` del MCP.
- **Chat en vivo**: `campaign_health` (MCP) devuelve las campañas habilitadas de una cuenta con diagnóstico, señales,
  conteos, gasto a pausar y los parámetros con su origen. Ve lo que `breakdown` no: campañas sin clicks.

### Fuente de datos (2026-09-17 — grano de campaña desde Amazon Ads API)
- Los datos llegan de `render_campaign_source("bulk")` (`modules/pages/campaign_source.py`), que devuelve un
  `CampaignInput(frame, currency_code)` o `None`. El frame tiene las 17 columnas del export de Campaign Manager
  (`FRAME_COLUMNS` en `core/amazon_ads/campaign_provider.py`); de ahí para abajo M6 no sabe de dónde vino.
- **Con cuentas sincronizadas** lo lee `CampaignProvider(rest).campaigns(option, desde, hasta)` sobre `campaigns_between`
  (migración 013): arranca en `ads_campaign` (la foto de `/sp/campaigns/list`) y suma `ads_campaign_daily` (reporte
  `spCampaigns` por día, 65 días) por left join, así que una campaña sin actividad es una fila en cero. Las archivadas
  quedan afuera. Sin cuentas, sin base o con "Subir archivo manualmente": el uploader de siempre (Bulk o Campaign CSV).
- **Frescura**: sale de las solicitudes `sp_campaigns` (la última y la última completada), nunca de `ads_profile_sync`,
  que es del STR. El pill reusa `freshness_pill` del STR (día y hora); el encabezado se refresca cada 30 s mientras hay
  una solicitud abierta y redibuja la página cuando se cierra.
- **Moneda**: la de la cuenta, con `money()` / `currency_symbol()`; con archivo manual queda el `$` de siempre.
- Diferencias con el CSV: estado de hasta el día anterior, métricas hasta ayer, período de hasta 60 días sobre los 65
  sincronizados, archivadas afuera, y las campañas SB del formato anterior sin métricas hasta que carga su historia
  v2 (ver abajo).

### SB, SD y Target Graduation (2026-09-18 — migración 015)
- `campaign_input.frame` sigue siendo sólo Sponsored Products (sus señales y su sincronización son de SP). SB y SD
  llegan aparte en `campaign_input.products` (`core/amazon_ads/product_provider.py`, RPC
  `product_campaigns_between`). `all_campaigns` los junta para mostrar y `campaigns_to_analyze` además saca las SB
  sin métricas: lo usan la página, el análisis IA y el MCP, así los tres diagnostican lo mismo.
- Compras y ventas de SB/SD = `purchases`/`sales` de Amazon (14 días, clicks o vistas), lo mismo que traía el CSV;
  `Purchases (clicks)`/`Sales (clicks)` son las comparables con SP.
- SB con `isMultiAdGroupsEnabled=false`: los reportes v3 de SB (preview) no las traen (medido: 0 de 31). Las trae el
  reporte v2 (`SbV2ReportFetcher`, pedido `sb_legacy_campaigns`, un día por reporte, `creativeType: all`); se guarda
  con `source = 'v2'` y el SQL deja entrar sólo las del formato anterior. Hasta que su historia v2 termina,
  `metrics_known` es falso: métricas vacías, `products.without_metrics`, afuera del analyzer y listadas aparte.
- Estrategia de puja: los nombres que escribe el Campaign CSV de Campaign Manager, lo que M6 mostraba con el archivo
  («Dynamic bidding (down only)», «Fixed bids»; `BID_STRATEGY_LABELS` en campaign_provider y product_provider). El
  bulk escribe otros («Dynamic bids - down only»): Campaign Builder, que arma bulks, usa esos.
  SD no la tiene en la campaña: sale de la optimización de sus ad groups (`/sd/adGroups`).
- El CSV de PostgREST escribe los booleanos como `t`/`f`, no `true`/`false`.
- Target Graduation con API: `campaign_input.idle_targets` (RPC `graduation_targets_between`): trae todos los
  targets habilitados de campañas habilitadas con sus impresiones, así el "N de M" sale por producto y una cuenta sin
  targets inactivos no se lee como "sin sincronizar". Sólo cuenta productos con métricas de targeting en el período.
- Análisis IA: un análisis por cuenta con los tres productos (columna `producto`, `sales_clicks`, `orders_clicks`
  sólo cuando hay SB o SD). El worker espera también a los pedidos de campañas SB/SD y replanifica cuando terminan;
  la página cachea SB/SD con la hora del último de esos pedidos en la clave, para que la huella coincida.
- Las listas se guardan con un único `seen_at`; las lecturas toman sólo la última lista (un target archivado deja de
  aparecer).
- Un marketplace sin una función de SB (AU no tiene product targeting) responde 400 "do not have access" a
  `/sb/targets/list`: esa parte se lista vacía (`_unless_not_offered`) para no dejar a la cuenta sin sus campañas SB.
- Chat (MCP): `daily_metrics`, `accounts_overview` y `breakdown` por campaña, portfolio o producto suman SP, SB y SD de
  los reportes de campaña (`core/amazon_ads/campaign_totals.py`, RPC `campaign_daily_totals` / `campaign_window_totals`).
  Con `source="search_terms"` devuelven SP sumado de los search terms (`ReportProvider.daily_totals` /
  `search_terms`), lo que daban antes: pocas impresiones, porque sólo traen términos con clicks. Cada respuesta trae
  `data_source`, `source` y, si SP existe en la otra fuente, `alternative` con cómo pedirla. `accounts_overview` nombra
  en `without_campaigns` las cuentas con search terms pero sin campañas sincronizadas todavía.

### Inputs
- Datos de Amazon Ads (cuenta + país + período) o Bulk / Campaign CSV subido a mano

### Anti-patterns
- Confundir bulk .xlsx (sin métricas) con Campaign CSV (con métricas)
- ❌ NO meter SB/SD en `campaign_input.frame`: las señales y la ventana de ese frame son de SP; juntarlos es cosa de
  `all_campaigns` / `campaigns_to_analyze`
- ❌ NO guardar las filas v2 de SB con la fuente v3: el reemplazo del día de v3 las borraría (y viceversa)
- ❌ NO leer una campaña SB sin métricas de la API como fantasma: Amazon no la reporta, no es que no entregó
- ❌ NO comparar un booleano leído por CSV con `"true"`/`"false"`: PostgREST manda `t`/`f` y la comparación falla callada
- ❌ NO armar la tabla solo con el reporte `spCampaigns`: trae únicamente campañas con actividad y los fantasmas desaparecen
- ❌ NO tomar la frescura de `ads_profile_sync`: la actualizan sólo las solicitudes de search terms
- ❌ NO copiar la regla del semáforo en la página ni en el MCP: se importa de `core/amazon_ads/campaign_analyzer.py`
- ❌ NO leer un share vacío como 0: Amazon no lo reporta si la campaña no calificó; 0 dispararía "Baja visibilidad"
- ❌ NO sacarle al chat las cifras de SP de los search terms al sumar los reportes de campaña: son dos datos que
  difieren en impresiones y el AM compara con los dos (`source` en las herramientas)

### Tests
`tests/test_campaign_analyzer.py` (regla y señales), `tests/test_campaign_analysis_job.py` (spec, ventana y payload,
también con SB/SD), `tests/test_mcp_campaign_health.py` (también `idle_targets`), `test_mcp_daily_metrics.py`,
`test_mcp_breakdown.py`, `test_mcp_accounts_overview.py`, `tests/test_campaign_source.py` (página con fake de
PostgREST), `tests/test_amazon_ads_campaign_rows.py` / `test_amazon_ads_campaign_provider.py` y los de
`product_provider`, `product_rows`, `ad_entities` y `report_fetcher` (v2).

---

## M7 — Business Report
**Archivo:** modules/pages/business_report.py
**Sección sidebar:** PPC
**Session state prefix:** br_

### Propósito
Analizar ventas, sesiones, CVR y BuyBox por ASIN desde el Business Report de Seller Central.

### Arquitectura
Visualizador raw. Punto de entrada del Parent-Child map (data/business_report/).

### Reglas de negocio
- Columnas requeridas: (Parent) ASIN, (Child) ASIN
- Auto-detect: Unit Session Percentage o Order Item Session Percentage

### Inputs
- BR by ASIN (.csv, .xlsx)

### Anti-patterns
- No precargar en data/business_report/ si no se quiere auto-load

---

## M8 — Análisis de Funnel
**Archivo:** modules/pages/analisis_funnel.py
**Sección sidebar:** PPC
**Session state prefix:** funnel_

### Propósito
Detectar brechas en el funnel Auto → Broad → Phrase → Exact por producto.

### Arquitectura
Inputs STR + Bulk → mapeo funnel → campañas sugeridas con naming convention

### Reglas de negocio
- Harvest a Phrase: 2+ órdenes AND ACoS ≤ target × 1.2
- Harvest a Exact: 3+ órdenes AND ACoS ≤ target

### Inputs
- STR (.xlsx, .csv) + Bulk (.csv)

### Anti-patterns
- Sin Bulk file → no puede detectar qué match types ya existen

---

## M9 — Bid Optimizer
**Archivo:** modules/pages/bid_optimizer.py
**Sección sidebar:** PPC
**Session state prefix:** bid_

### Propósito
Calcular bid óptimo por ASIN: bid = CVR × precio × target_ACoS. Export bulk con bids ajustados.

### Arquitectura
3 tabs: Bid Calculator (semáforo por CVR) | Placements & Budget (referencia SOP) | Análisis IA
(capa `core/ai_tab` + agente `ai/agents/bid_optimizer`).

### Fuente de datos (2026-09-17 — ingesta desde Amazon Ads API)
- El uploader del STR salió de `render()`: los datos llegan de `render_source_picker(key_prefix="bid_opt")`,
  el mismo componente que usa M2, con el fallback manual activo. `df = source.frame`.
- El Inventory Report sigue siendo un uploader propio y opcional (`bid_opt_inv`), para el precio de lista.
- **El frame canónico NO trae `Advertised ASIN`** (`console_columns()` no lo incluye y `spSearchTerm` no lo
  expone): `resolve_asin_column` usa la columna del archivo si existe y, si no, extrae `B0[A-Z0-9]{8}` del
  nombre de campaña. El origen del ASIN se muestra en pantalla y viaja al agente, porque cambia cuánto vale
  la agrupación. Sin ningún ASIN resoluble el módulo corta con `NO_ASIN_WARNING`, que explica la causa real
  en vez de culpar al archivo.
- **Moneda**: sale de `source.currency_code` y se formatea con `core/currency_format.money()`. Los budgets
  del SOP viajan como números (`budget_min`/`budget_max`) y se formatean en el render.

### Capa IA (2026-09-17 — consumidor de `core/ai_tab`)
- Agente `ai/agents/bid_optimizer/` (`BidData`, row_ids `A01…`, `MAX_ASINS=60`, `MAX_CAMPAIGNS=40`).
  Recibe Parámetros + bids por ASIN (top por spend) + placements por campaña, y emite `bids[]`
  (`veredicto` SUBIR/MANTENER/BAJAR/PAUSAR sobre el bid YA calculado) + la `synthesis` canónica.
- **La IA nunca recalcula el bid ni propone uno propio**: el módulo mantiene la matemática.
- Análisis en vivo con `auto_fire=False` (el AM pone el target ACoS y el Inventory Report en esta misma
  pantalla, así que no se paga un análisis antes del click) y `show_previous=False`.
- Se comparte con el chat de la app vía `publish_analysis_to_chat`.

### Reglas de negocio
- `bid_base = (CVR / 100) × precio × (target_ACoS / 100)`; sin órdenes no hay CVR medido y el bid queda en 0.
- Precio: Inventory Report si está; si no, ventas/órdenes del STR (ticket promedio, no precio de lista).
- Semáforo por CVR (`estado_por_cvr`): sin clicks → SIN DATA; CVR > 15 con más de 5 órdenes → ESCALAR;
  CVR 8-15 → OK; resto → REVISAR.
- Filas del mismo ASIN en distintas campañas se agrupan una sola vez.

### Inputs
- Datos de Amazon Ads (cuenta + país + período) o STR subido a mano
- Inventory Report (.txt, .csv) — opcional (precio de lista exacto)
- Target ACoS (slider)

### Tests
`tests/test_bid_optimizer_columns.py` (detección de columnas sobre el frame canónico, origen del ASIN,
matemática del bid, semáforo, placements) y `tests/test_bid_optimizer_agent.py` (documentos del agente,
row_ids, truncamiento, huellas, texto del chat).

### Anti-patterns
- ❌ NO asumir que el STR trae `Advertised ASIN` — con datos de API nunca viene.
- ❌ NO inventar un ASIN ni prorratear métricas entre los ASINs de un ad group: Amazon no reporta esa
  atribución, y un número inventado es peor que una fila sin ASIN.
- ❌ NO hardcodear `$` — la moneda sale de la cuenta (`money()` / `currency_symbol()`).
- ❌ NO llamar a `ai/runtime` directo — todo por `core/ai_tab`.
- Usar ACoS del STR sin filtrar por ENABLED — incluye términos de campañas pausadas

### Deuda documentada
La doc previa describía un semáforo SUBIR/OK/BAJAR/PAUSAR por comparación de bid actual contra sugerido,
que el código nunca implementó (siempre fue el semáforo por CVR de arriba). Queda anotado: si el AM espera
el semáforo por bid, es una feature a construir, no un bug a corregir.

## M10 — Campaign Builder
**Archivo:** modules/pages/campaign_builder.py (864 → 1121 líneas tras Sprint 1 2026-04-23)
**Sección sidebar:** PPC
**Session state prefix:** cb_ (SP) | cb_sb_v2_* (SB) | cb_sd_* (SD)

### Propósito
Generar bulk de nuevas campañas (SP/SB/SD) a partir del Plan de Acción. El naming Capybaras hardcoded es un contrato con M11 Atom11 Rules Builder — NO modificar.

### Arquitectura
Selector tipo (SP/SB/SD) con radio button → flujo en pasos (Paso 0-4 según tipo) → preview editable → validación estricta bloqueante → export bulk formato exacto Amazon

### Helpers principales
- `_generar_nombre_campana_sp()` — naming SP hardcoded (NO tocar — contrato con M11)
- `_generar_nombre_campana_sb()` — naming SB hardcoded (NO tocar — contrato con M11)
- `_SB_COLS_2026` — 29 columnas bulk Amazon Ads API 2026 (incluyendo `" Ad Group ID"` con espacio inicial — es correcto, es bug de Amazon documentado)
- `_sb_row_factory(**kwargs)` — builder de fila vacía para bulk SB
- `_build_sb_bulk_rows(...)` — genera 5 filas por campaña SB: Campaign → Bidding Adjustment → Ad Group → Ad → Keywords con bifurcación SBV/SBH
- `_render_sb()` — flujo completo SBV/SBH reescrito en Sprint 1 (2026-04-23)
- `_render_sd()` — flujo SD (preexistente)

### Reglas de negocio
- SP clustering: PAT / Spanish (prioridad) / Brand / Vitamin A / Discovery
- Max 5 keywords por campaña (regla Capybaras — NO negociable)
- SB Paso 0: selector SBV vs SBH (bifurca toda la lógica)
- SBV requiere: Brand Entity ID (obligatorio) + Video Asset ID (obligatorio) + Brand Name + Creative Headline + 3 ASINs creativos
- SBH requiere: Brand Entity ID (obligatorio) + Brand Logo Asset ID (obligatorio) + Logo Crop (Square/Rectangle) + Brand Name + Creative Headline + 3 ASINs creativos + Brand Logo URL (opcional)
- Brand Entity ID: obligatorio en Amazon Ads API 2026 — sin él el bulk es rechazado
- Validaciones estrictas bloqueantes: si falta cualquier campo requerido, muestra lista de errores en lugar del botón de descarga
- Naming SB: `[Marca] - [ASIN] - SB - KW - [Match] - [Cluster]` (ejemplo: `Dermaglos - B0CYLMJJJC - SB - KW - EXACT - Brand 1`)
- SD requiere: Product Targeting o Audience, bid optimization

### Gotcha crítico — Streamlit Markdown + LaTeX
- Patrón `**${variable}**` en st.info/st.markdown/st.error/st.warning rompe el render (Streamlit interpreta `$` como delimitador LaTeX)
- Fix: escapar con `\\$` o envolver negrita alrededor de frase completa: `**Precio: \\$X**`
- Afecta a cualquier string que combine `**` y `$` en el mismo bloque

### Inputs
- Plan de Acción bulk (de M4, .xlsx) — Paso 1
- Marca, ASIN, SKU, precio, CVR, target ACoS, budget — Paso 2
- Brand Entity ID — Paso 2 (requerido para SB)
- Video Asset ID (SBV) o Brand Logo Asset ID + Crop (SBH) — Paso 3

### Anti-patterns
- NO permitir bloques dinámicos de naming — rompen el contrato con M11 (Atom11 Rules Builder parsea Campaign Name para clasificar en DISCOVERY/RANKING/CONQUEST/etc)
- NO usar `**${var}**` en markdown de Streamlit — colisión con LaTeX
- No validar SKUs contra Inventory — Amazon rechaza ASIN en bulk SP
- No cruzar contra Exact activas — canibalización

### Sprint roadmap
| Sprint | Feature | Estado |
|--------|---------|--------|
| 1 | Rewrite `_render_sb()` con SBV + SBH + Brand Entity ID + 29 columnas 2026 | ✅ Completado 2026-04-23 |
| 2 | Modo B simplificado con XLSX custom + `st.data_editor` | Pendiente |
| 3 | DaypartingApp como módulo nuevo en Account Manager | Pendiente |

---

## M11 — Atom11 Rules Builder
**Archivo:** modules/pages/atom11_rules_builder.py
**Sección sidebar:** PPC
**Session state prefix:** atom11_

### Propósito
Generar 274 rules automáticas para importar en Atom11.

### Arquitectura
3 tabs: Config (marca, brand terms, ASINs + tiers), Campaign Groups (clasificación automática), Rules Generator (preview + export)

### Reglas de negocio
- Multi-marca: todo configurable
- Tiers: LOW (<$12, 18 clicks) | MID ($12-22, 22 clicks) | HIGH (>$22, 28 clicks)
- 6 objetivos: DISCOVERY (120% target) | RANKING (100%) | CONQUEST (86%) | DEFENSIVE (71%) | PROFIT (50%) | REMARKETING (71%)
- 274 rules = Bid Optimiser (126) + Placement (108) + Negate (18) + Hard-Stop (18) + Harvest (4)
- Thresholds v2026.2: DEC HARD > 1.86× target → PAUSE TARGET
- Parsea Campaign Name para clasificar objetivo — por eso el naming Capybaras en M10 es un contrato, NO un detalle cosmético

### Inputs
- Prefijo marca + brand terms + ASINs con precio
- Campaign CSV — clasificación automática

### Anti-patterns
- Hardcodear tiers sin pasarlos por editor
- Crear rules antes de 14 días de learning period

---

## M12 — Reportes Atom 11
**Archivo:** modules/pages/atom11.py
**Sección sidebar:** Account
**Session state prefix:** atom11_reports_

### Propósito
Parsear reportes Atom11 (WoW/MoM/DateRange) y generar Excel ejecutivo.

### Arquitectura
1 o 2 archivos → parsea automáticamente → 3-4 sheets Excel con branding

### Reglas de negocio
- Auto-detect: tipo reporte (ASIN, Portfolio, Keyword, etc.)
- Delta% coloreado: verde >0, rojo <0
- Parent Evolution: opcional si hay BR cargado

### Inputs
- Atom 11 .xlsx (1 o 2 archivos)
- Business Report — Tab "Parent Evolution"

### Anti-patterns
- Incluir campañas pausadas — Amazon retorna "Not Found"
- No confundir período: mismo WoW que en Weekly Report

---

## M13 — Reportes MerchanSpring
**Archivo:** modules/pages/merchanspring.py
**Sección sidebar:** Account
**Session state prefix:** merchanspring_

### Propósito
Parsear PDF o XLSX de MerchanSpring → Excel estructurado 4 hojas.

### Arquitectura
Detección automática PDF vs XLSX, parsers defensivos con try/except, export multi-sheet

### Reglas de negocio
- PDF: extrae 20+ secciones, robust contra cambios de formato
- XLSX: parsea Summary, Advertising, Inventory, WoW

### Inputs
- MerchanSpring .pdf o .xlsx

### Anti-patterns
- PDF con cambios de layout — agregar try/except nueva sección

---

## M14 — Weekly Client Report
**Archivo:** modules/pages/weekly_client_report.py
**Sección sidebar:** Account
**Session state prefix:** weekly_

### Propósito
Generar reporte semanal al cliente: WoW comparativo + Advertising + Changelog.

### Causa raíz que define el diseño
**El export "Detail Page Sales and Traffic By Child Item" de Amazon NO trae columna
de fecha**: es un único agregado del rango pedido. Por eso un solo by-Child no se
puede partir en dos semanas, y el período de esas columnas tiene que declararse
desde afuera. Ignorarlo produjo el bug de deuda técnica #24: los montos por ASIN
salían de 14 días bajo el encabezado "esta semana", ~2× lo real.

### Arquitectura
**5 inputs** → 4 sheets Excel con branding Capybaras.

| # | Input | Obligatorio | Notas |
|---|---|---|---|
| 1 | BR diario 14d (By Date) | sí | única fuente con fechas reales; de acá se derivan los períodos |
| 2 | BR by Child — esta semana | sí | sin fechas propias |
| 3 | BR by Child — semana anterior | **no** | sin este archivo NO hay WoW por producto |
| 4 | Atom 11 ASIN 14d | no | sí trae desglose diario: su split 7+7 es correcto |
| 5 | Campaign CSV | no | |

### Los dos modos
`_es_modo_wow(period_child_tw, period_child_pw)` es la única fuente de verdad y la
consultan tanto el Excel como la UI, para que no puedan discrepar.

- **MODO WOW** — exige DOS períodos by-Child de **7 días exactos**. Se mira `days`,
  no la presencia del dato: un período informado de 14d NO habilita el WoW.
  Rótulos "Esta semana / Semana anterior / Variación %", WoW por producto, TACoS
  por ASIN calculado.
- **MODO PERÍODO COMPLETO** — cualquier otro caso. SALES/UNITS/SESSIONS/CVR se
  rotulan "Período completo (Nd)", las columnas PW y de delta van a "—", la fila
  CUENTA TOTAL muestra el **mismo agregado** que los productos, y el TACoS por
  producto queda en "—". AD SALES y AD SPEND no cambian (vienen de Atom 11).

**Invariante:** una columna nunca mezcla períodos. Si los productos son de 14d, la
fila CUENTA TOTAL de esa columna también.

### Funciones clave
```python
_derivar_periodos(br_daily, hay_child_pw)  # -> (period_tw, period_pw). Extraido de render()
_periodo(fechas)                  # [ISO] -> {'start','end','days'} | None. days = fechas DISTINTAS
_es_modo_wow(p_tw, p_pw)          # única decisión de modo (7d + 7d)
_chequear_coherencia_child(...)   # suma del by-Child vs BR diario, tol 1%; avisa, NO bloquea
_calificar_trafico(se_d, cvr_d)   # cruza sesiones x conversión -> clave de texto
_trend_ejecutivo(s_d, u_d, se_d)  # 'pos'|'neg'|'flat'; las sesiones NO votan
_rango_legible(period, lang)      # '10–16 ago' / 'Aug 10–16'
_sufijo_periodo(...)              # sufijo del título con el período real
_L_EXEC                           # textos del ejecutivo, a NIVEL DE MÓDULO (testeable sin generar Excel)
```

### Reglas de negocio
- `_parse_br_wow` **consolida** filas del mismo (Child) ASIN: Amazon lista el mismo
  child bajo parents distintos tras merges de variaciones. Sessions/units/sales
  suman; CVR se recalcula del cociente de totales; BuyBox se pondera por sesiones.
  Metadata `_rows_merged` / `_parents` para trazabilidad.
- CVR de cuenta en el ejecutivo: **ponderado por sesiones** (`units/sessions`), en
  las DOS ramas (con BR diario y sin él). Nunca promedio simple por ASIN ni
  promedio de los porcentajes diarios — `br_daily["CVR_TW"]` es un `.mean()` de
  porcentajes y NO sirve para el total de cuenta (desvío medido: 8,22 puntos).
- El trend lo deciden ventas y unidades. Las sesiones son un input, no un resultado.
- Tráfico ↑ con CVR ↓ **no se felicita**: es diagnóstico de calidad de tráfico.
- BuyBox con 0 sesiones → ignorado.
- Toggle ES/EN para toda la redacción ejecutiva.

### Anti-patterns
- **Rotular una columna sin saber su período.** Todo rótulo temporal sale del modo.
- **Sumar filas de producto y llamarlas "esta semana"** sin BR diario ni MODO WOW.
- `result[asin] = {...}` en el loop de `_parse_br_wow` — pisa duplicados (last-wins).
- `br_pw={}` hardcodeado en el call site: era el origen del bug.
- Calificar una métrica en aislamiento, o dar dos causas distintas al mismo hecho.
- No validar date range — el by-Child debe cubrir el mismo rango que el BR diario
  (lo chequea `_chequear_coherencia_child`).

### Tests
`tests/test_m14_weekly_periodo.py` — 29 casos: dedup, contrato de período, WoW por
producto, coherencia, narrativa y encabezado.

---

## M15 — Listing Monitor
**Archivo:** modules/pages/listing_monitor.py (587 líneas)
**Sección sidebar:** Account Manager
**Session state prefix:** lm_

### Propósito
Monitorear ASINs de Amazon, alertar cambios precio/rating/stock/badges vs snapshot anterior. Scraping directo (sin API key).

### Arquitectura
3 tabs: Escanear ASINs | Ver Alertas | Historial con snapshots

### Reglas de negocio
- Scraper: requests + BeautifulSoup, delay configurable (8-10s por ASIN)
- Storage: JSON local `data/listing_snapshots/snapshots.json`
- Key: `{ASIN}_{MARKETPLACE}`
- Color alerts: 🔴 alerta | 🟡 info | 🟢 ok

### Inputs
- ASINs (texto libre, separados por salto)
- Marketplace selector (MX/COM/ES/BR/CA)
- Delay (segundos)

### Anti-patterns
- Amazon 503 bloqueo — aumentar delay a 10s mínimo
- Múltiples cargas → overwrite snapshot anterior (YAGNI por ahora)

---

## M17 — Account Pulse
**Archivo:** modules/pages/account_pulse.py (~430 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** pulse_

### Propósito
Monitor de salud diaria: ventas, units, sessions, CVR, ACoS con deltas WoW. Festivos MX integrados.

### Arquitectura
Upload BR diario + BR by Child + Campaign CSV → split PW/TW automático → Excel 4 hojas

### Reglas de negocio
- Festivos MX hardcoded: Año Nuevo, Constitución, Juárez, Trabajo, Independencia, Muertos, Revolución, Navidad
- Anomalía: caída >30% del promedio
- BuyBox ordenado por impacto económico
- Campañas: NUEVA (verde) vs HEREDADA (azul)
- Portada naranja con KPIs + diagnóstico + mensaje Slack

### Inputs
- BR Daily (.csv/.xlsx) — mínimo 14 días
- BR by Child (.csv/.xlsx) — opcional
- Campaign CSV (.csv) — opcional

### Anti-patterns
- BuyBox con 0 sesiones → ignorar (falso positivo)

---

## M18 — PPC Insights Engine
**Archivo:** modules/pages/ppc_insights.py (~530 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** insights_

### Propósito
Health score 0-100 por ASIN cruzando STR + SQP + BR + Campaign CSV. Identifica ASINs problemáticos.

### Arquitectura
Carga múltiples reports → cruza datos → score compuesto + cards por ASIN con expanders

### Reglas de negocio
- Health Score (0-100): CVR (25 pts) + BuyBox (20 pts) + ACoS vs target (25 pts) + Funnel completo (15 pts) + Impression Share (15 pts)
- Por ASIN: Top keywords, bleeders, wasted spend, top campaigns

### Inputs
- STR (.xlsx, .csv) — requerido
- SQP (.xlsx, .csv) — opcional
- BR by ASIN (.xlsx, .csv) — opcional
- Campaign CSV (.csv) — opcional

### Anti-patterns
- Cargar STR sin SQP — pierde contexto de mercado en score

---

## M19 — PPC Forecast
**Archivo:** modules/pages/ppc_forecast.py (~450 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** forecast_

### Propósito
Proyección de ventas con tendencia lineal + estacionalidad. Estima ventas futuras 7/14/30 días.

### Arquitectura
Input BR diario (mín 14d) → numpy polyfit → 3 escenarios (conservador/base/optimista) + gráfico + Excel

### Reglas de negocio
- Tendencia: numpy polyfit grado 1
- Estacionalidad: finde vs laboral, detección automática
- 3 escenarios con bandas de confianza

### Inputs
- BR Daily (.xlsx, .csv) — mínimo 14 días

### Anti-patterns
- Menos de 14 días → resultados no confiables
- Proyectar >30 días → pierde precisión

---

## M20 — PPC Audit Pro
**Archivo:** modules/pages/ppc_audit.py (~1,077 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** audit_

### Propósito
Auditoría integral desde Bulk File multi-hoja. Breakdown real SP/SB/SD, 10 segmentos, 5 deep checks.

### Arquitectura
Parser Bulk 5-hoja → 6 tabs Excel: KPIs, Auditoría Estructura, Performance Segmento, Deep Checks (5), Target Graduation, Export

### Reglas de negocio
- Parser: SP Campaigns, SB Campaigns, SD Campaigns, SP STR, SB STR
- Segmentación SP: 10 tipos (KW Exact/Phrase/Broad + PT ASIN/Category + AUTO Close/Loose/Substitutes/Complements)
- Match Type Mixto: >1 match por campaign → badge REVISAR
- Target WAS: spend>0, sales=0
- ACoS semáforo: verde ≤30%, amarillo 31-55%, rojo >55%

### Inputs
- Bulk File (.xlsx) — requerido (Campaign Manager → Bulk Operations)
- Business Report (.xlsx, .csv) — opcional (para TACoS, Revenue)
- Brand terms (texto) — clasificación targets

### Anti-patterns
- NO confundir Bulk File (.xlsx Campaign Manager) con Campaign CSV
- _build_audit_excel() DEBE estar fuera de render()

---

## M21 — DataDive Analyzer
**Archivo:** modules/pages/datadive_analyzer.py
**Sección sidebar:** Research
**Session state prefix:** widgets `dd_*` · IA `datadive_ai_*` (capa ai_tab)

### Propósito
Analizar niches de DataDive (keywords, competidores, rank radar) para detectar oportunidades de mercado. El tab 1 puede traer la MKL directo por API (sin export manual) y corre un análisis IA con chat de repreguntas.

### Arquitectura
5 tabs: MKL Keywords | Competitors | Rank Radar | Ranking Volatility+PPC IS | Competitor Intel.
Parsers puros en `modules/parsers/datadive.py` (shape canónico COL_*); cliente API en `core/datadive.py`; agente IA en `ai/agents/datadive/` consumido vía `core/ai_tab` (nunca wiring a mano).

### Fuente API — tabs 1-5 (2026-09-01)
- Gate: presencia de `DATADIVE_API_KEY` (env → `st.secrets["datadive"].api_key`). Sin key el módulo es idéntico al flujo solo-archivo.
- Tab 1: radio `API DataDive | Archivo` (API es el default con key) → selector de niche (label `nicheLabel · marketplace`, orden por `latestResearchDate` desc, key del widget = `nicheId`) + botón "Traer de DataDive" (refresh targeted `_api_mkl.clear(niche_id)`). Caption con fecha+hora UTC del último dive.
- Tab 2: carga automática de los competidores del MISMO niche traído en tab 1 (`competitors_to_df` → labels del export; benchmark → medianas). Validado 9/9 ASINs idénticos al xlsx real; la API suma columnas que el export no numericiza (Fulfillment, Outliers, TOS Ads) y NO trae "Strength".
- Tab 5: dos selectores de niche + "Traer ambos de DataDive"; el Gap se clasifica por el indicador del outer join (el shape MKL no tiene columnas "rank").
- Tabs 3-4: selector de rank radar + rango 30/60/90 días (`rank_radar_to_df` → Search Term/SV/Relevance/Median Rank + columnas fecha con el rank orgánico diario). El historial es server-side (el bloque de snapshots en session_state queda solo para archivos); el tab 4 reusa el radar traído en el 3. La API no trae las columnas PPC/SQ Score del export — el tab las guarda con `if col in df`.
- **`/v1/niches` devuelve el set completo en cada "página"** (paginación declarada pero no honrada, medido en vivo): `list_niches` dedupea por nicheId y corta cuando una página no aporta ids nuevos. Ante endpoints nuevos, asumir que la paginación puede mentir.
- `keywords_to_mkl_df()` produce el MISMO DataFrame canónico que `parse_mkl` — el resto del tab no distingue la fuente. **Launch Score no viene en ningún endpoint v1, pero se CALCULA** con la fórmula del frontend de DataDive (bundle público): `round(SV × 0.003 / relevancy)` si relevancy ≥ 0.4, si no 0 — replicada en `core/datadive.py::_launch_score` y validada 419/419 contra el export real. `rankingJuice` de /roots NO es el Launch Score (verificado 0/419).
- **Sostenibilidad del Launch Score, sin vigilancia manual** — la réplica se rompe en silencio si DataDive cambia su fórmula, así que hay tres redes, y la principal es automática:
  1. **CI, sin credenciales** (la red que no depende de nadie): `scripts/check_launch_score_drift.py` verifica que la fórmula siga en el bundle público y si `launchScore` apareció en el spec oficial. Corre en el stage `Launch Score drift` del Jenkinsfile — en cada build y por cron semanal (`H 6 * * 1`, que NO deploya porque el CD gatea en `SCMTrigger`). Marca el build UNSTABLE, nunca lo rompe: que un tercero recalibre una fórmula es una noticia, no un build roto.
  2. `_launch_score_of()` prefiere el campo oficial (`launchScore`/`launch_score`) si algún día aparece en el payload: el día que DataDive lo exponga, la réplica queda muerta sola, sin migración.
  3. `launch_score_drifted()` audita la fórmula contra cada export por archivo que suba el AM (el xlsx trae el valor verdadero) y avisa en el tab. Es red de respaldo: con el modo API por default los archivos casi no se suben, así que NO alcanza por sí sola.
  El fix permanente es que DataDive exponga el campo: no hay pedido público, y tienen canal de soporte y office hours.
- Los GET de DataDive no consumen tokens facturables (solo dives/rank radars/copywriter los gastan); el cache `st.cache_data(ttl=3600)` es compartido entre usuarios del proceso y el botón Traer fuerza fetch fresco.
- Smoke con key real: `scripts/smoke_datadive_api.py` (read-only; imprime distribución de relevancy y sondea /roots y /ranking-juices).

### Reglas de negocio
- Tab 1: SV, Relevance (escala UI 0-10), Launch Score, ranking competidores. Color: verde Rel ≥3, amarillo ≥2, rojo <2.
- **Relevancy es fracción 0-1 en la API Y en los exports frescos (2026-08+)** — parser y normalizer la llevan a 0-10 (×10). El parser solo rescala si TODO el archivo está en 0-1.
- **`parse_mkl` mapea columnas por nombre de header** (el export insertó "Type" en 2026-08 y rompió el layout posicional); el layout legacy queda como fallback.
- Tab 3: tracking orgánico diario, tendencia ↑→↓, PPC coverage
- Tab 4: volatilidad (std dev), clasifica ESTABLE/VOLÁTIL/MUY VOLÁTIL, flags riesgo/oportunidad
- Tab 5: tu MKL + competidor, clasifica Ambos/Solo yo/Solo comp/Ninguno

### Capa IA (tab 1)
- Agente `datadive` (primer agente de `ai/` en main): recibe Parámetros + top 120 keywords por SV (row_ids K01…) + opcionalmente los competidores del niche con su mediana (de la API o del archivo del tab 2), y emite clusters de intención, gaps priorizados y la síntesis canónica de `core/ai_tab`. El análisis se comparte con el chat de la app (`publish_analysis_to_chat`).
- **Contrato del agente (v2, auditado contra output real)**: `launch_score` es COSTO de entrada (alto = caro), no puntaje; `relevance` se ancla en los cortes del tab (alta ≥3,0 — el grueso del niche vive bajo 3); `sugg_bid` no habilita a declarar bids/ACoS/presupuesto (no hay precio ni CVR del cliente en el payload). Los **gaps incluyen el ASIN enterrado** (mi_rank fuera de P1), no solo el ausente — son los más baratos. La **prioridad de cluster es atacabilidad, no tamaño**, y el orden del array es el orden de ataque. `select_keywords` manda 90 por SV + 30 por relevancia (la cola barata sesgaba a "niche caro" si se cortaba solo por SV) y marca cada fila con `bloque`. Si el ASIN declarado no está en el dive, Parámetros lo declara como CALIDAD DE DATOS y los gaps van vacíos.
- **Chat con tools (fase 3)**: desde 2026-09-15 las herramientas de DataDive las usa el orquestador del chat de la app (su frontmatter declara `datadive`); el `tools:` del agente `datadive` se conserva. `runtime.ask_followup` manda `tools:["datadive"]` al provider, que expone 5 tools MCP read-only in-process (list_niches, get_niche_keywords, get_niche_competitors, list_rank_radars, get_quota; resultados truncados). Solo el CHAT es agéntico — el análisis nunca lleva tools. Server-side vive en capybaras-ai-provider (`app/datadive_tools.py`, rama feat/datadive-mcp-tools) con `DATADIVE_API_KEY` en su .env.
- La IA nunca recalcula cifras; el módulo joinea opiniones por row_id posicional contra los MISMOS records serializados.

### Inputs
- DataDive exports (.xlsx) o niche vía API (tab 1)

### Anti-patterns
- return-in-tabs bug — fijar con paréntesis en cada tab call
- NO parsear el MKL por posición de columna — DataDive re-layouta el export; headers son el contrato
- NO llamar a `ai/runtime` directo — todo por `core/ai_tab`
- NO llamar POSTs de DataDive (dives/redive/rank radars/copywriter) — consumen tokens reales de la organización

---

## M22 — Helium 10 Analyzer
**Archivo:** modules/pages/helium10_analyzer.py (350+ líneas)
**Sección sidebar:** Research
**Session state prefix:** h10_

### Propósito
Analizar exports Helium 10 Cerebro para reverse ASIN, research y competitor gap.

### Arquitectura
3 tabs: Cerebro Reverse ASIN | KW Research multi-competidor | Competitor Gap con export Plan de Acción

### Reglas de negocio
- Tab 1: SV, Organic Rank, Sponsored Rank, IQ Score. Flags: Oportunidad PPC (organic sin ads), Depende de Ads
- Tab 2: cruza 1-3 Cerebros competidores, Launch Priority Score = SV × (ranking comp/total) × (1/avg rank)
- Tab 3: tu Cerebro vs 1-2 competidores, detecta KWs donde rankean org y vos no. Botón "Exportar como Plan de Acción" para Campaign Builder

### Inputs
- Cerebro .xlsx: `US_AMAZON_cerebro_[ASIN]_[fecha].xlsx`

### Anti-patterns
- Cargar 1 archivo SQP en Cerebro parser → maneja "-" como NaN

---

## M23 — SBH Recommendation
**Archivo:** modules/pages/sbh_recommendation.py (230+ líneas)
**Sección sidebar:** Research
**Session state prefix:** sbh_

### Propósito
Recomendar targets para campañas Sponsored Brand Headline cruzando MKL + SQP + Campaign CSV.

### Arquitectura
Carga 3 inputs → prioriza por SV + IS + mercado comprando → clustering automático + headlines sugeridos

### Reglas de negocio
- Prioridad ALTA: SV ≥1000, IS <10%, mercado comprando, no en SP actual
- MEDIA: SV ≥500, IS <20%
- BAJA: SV ≥300
- Clustering: root words comunes
- Headline sugerido por cluster

### Inputs
- DataDive MKL (.xlsx) — requerido
- SQP (.xlsx, .csv) — requerido
- Campaign CSV (.xlsx, .csv) — opcional

### Anti-patterns
- Sin Campaign CSV → no puede detectar keywords ya en SP

---

## M24 — Knowledge Base
**Archivo:** modules/pages/knowledge_base.py (~180 líneas)
**Sección sidebar:** Knowledge
**Session state prefix:** kb_

### Propósito
Repositorio de notas y documentación del equipo. Buscar, filtrar y crear notas .md.

### Arquitectura
2 tabs: Explorar notas (upload + búsqueda texto + filtro tags/categorías) | Agregar nota (formulario + preview + descarga)

### Reglas de negocio
- Categorías: ppc, amazon, ai, strategy, client
- Parsea headers/tags/categorías/fecha del filename
- Búsqueda full-text case-insensitive
- Badges de categoría estilo naranja

### Inputs
- Archivos .md o .txt

### Anti-patterns
- No procesar archivos que no sean texto plano (.md, .txt)

---

## M25 — Gamboa Generator
**Archivo:** modules/pages/gamboa_generator.py (383 líneas)
**Módulos internos:** `modules/gamboa/{__init__, parsers, generator, template.html}`
**Sección sidebar:** Account
**Session state prefix:** gamboa_

### Propósito
Generador de reportes HTML integrales tipo dashboard interactivo. Cruza SQP mensual + BR semanal, reutilizable para cualquier cliente Capybaras. Listo para publicar en Hostinger o enviar al cliente por email/WhatsApp.

### Arquitectura
5 archivos: __init__ (marker) + parsers (421 líneas: `parse_sqp_multi`, `parse_br_multi`, `parse_inventory`, `load_categories`/`save_categories`) + generator (278 líneas: `enrich_sqp`, `enrich_br`, `build_raw_json`, `build_wow_json`, `generate_html`) + template.html (874 líneas, 64KB con 12 placeholders y JS runtime)

UI Streamlit: expander `_how_to_use()` + `_header()` + `_empty_state()` + `_info_box()`

### Reglas de negocio
- **Categorías persistentes:** `notes/brands/{cliente-slug}/gamboa_categories.csv` — reutiliza arquitectura existente de notas
- **SKU opcional con fallback ASIN:** robustez, funciona sin Inventory Report
- **Template HTML separado:** mantenible por separado, no hardcodear lógica
- **Score SQP defensivo:** lee columna "Search Query Score" con fallback 0 — defensivo ante cuentas sin Brand Analytics
- **SQP multi-upload:** auto-detecta mes por filename O columna "Reporting Range" — Amazon BA baja archivo por mes O por rango, ambos casos soportados

### Parsers cacheados
```python
@st.cache_data — todos: parse_sqp_multi(), parse_br_multi(), parse_inventory()
```

### Inputs
- **SQP multi-archivo (.xlsx)** — requerido. Auto-detecta mes por filename o "Reporting Range"
- **BR semanal by ASIN (.xlsx o .csv)** — requerido. Auto-detecta semana ISO
- **Inventory Report (.txt, .csv)** — opcional. Mapeo SKU ↔ ASIN. Sin esto usa ASIN como identificador
- **CSV categorías** — auto-plantilla descargable. Persistente entre sesiones en `notes/brands/{cliente-slug}/gamboa_categories.csv`

### Output
HTML standalone (~5-10 MB) listo para publicar. 2 paneles interactivos con JS runtime:
- **Panel SQP mensual:** 15 meses de queries, filtros por categoría, funnel conversión, cards por categoría, tabla filtrable, 7 charts de tendencia (Search Query Score, Impressions, Clicks, Cart Adds, Purchases, Click-Through Rate, Conversion Rate)
- **Panel WoW Category (semanal):** 68 semanas de KPIs WoW/YoY, category cards con deltas, tabla detalle con sparklines por SKU, modal de tendencia por SKU

### Pendientes condicionales (YAGNI — NO tocar hasta feedback del AM con data real)
- **SI** el AM reporta >20% queries en "Sin Categorizar" → evaluar refactor usando "Top Clicked ASIN" del SQP crudo para auto-clasificación
- **SI** hay problemas con mapeo de categorías → evaluar agregar columna `sqp_keywords` al CSV categorías para fuzzy match

### Anti-patterns
- Cargar SQP sin crear categorías CSV primero — template mostrará muchas "Sin Categorizar" (YAGNI: no auto-clasificar)
- BR antiguo (sem 1-2 meses) sin datos recientes — usar único de semana actual
- No validar que ASIN en BR coincida con ASIN del producto (cruce de cuentas)

---

## M26 — Variation Builder
**Archivo:** modules/pages/variation_builder.py (913 líneas)
**Sección sidebar:** Account Manager
**Session state prefix:** vb_

### Propósito
Generador de flat files Amazon con variaciones (parent + N children). Agrupa por variation_theme configurable, preserva macros VBA y 10 hojas del template. Parser dinámico soporta hasta 220 columnas. Listo para subir a Seller Central.

### Arquitectura
- Parser dinámico que detecta columnas del template (hasta 220)
- Agrupa children automáticamente por variation_theme seleccionado
- Genera parent_sku derivado del primer child con sufijo
- Escribe .xlsm con openpyxl + keep_vba=True (preserva macros)
- Mantiene las 10 hojas del template (Template, Data Definitions, Valid Values, etc.)

### Reglas de negocio
- 1 parent + N children por SKU group
- variation_theme define qué columnas varían entre children
- parent_sku derivado del primer child con sufijo
- relationship_type = "Variation" para children, vacío para parent
- Columnasrequeridas: una con "ASIN" en el nombre, una con "Parent" en nombre o configuración

### Themes soportados (v1)
- Sabor
- Nombre del Tamano
- Scent
- FlavorName-SizeName
- Tamano del Sabor
- Nombre del Patron

### Marketplaces (v1)
Solo MX (MXN). Futuro: multi-marketplace (COM, ES, BR, CA).

### Inputs
- **Template .xlsm** — Amazon Seller Central → Inventory → Add Products via Upload → Download Template
- **Variation theme selector** — Sabor, Nombre del Tamano, Scent, FlavorName-SizeName, Tamano del Sabor, Nombre del Patron

### Outputs
- **.xlsm listo para subir a Seller Central**
- Preserva macros VBA y 10 hojas del template
- Agrupación automática por variation_theme

### Testing realizado
- End-to-end con archivo real Pet Food: parent + 15 children, generado exitosamente
- py_compile: verde
- Archivos modificados: app.py (3 edits quirúrgicos), core/constants.py (1 edit)

### Anti-patterns
- NO modificar el archivo del módulo (913 líneas, ya validado y tested)
- NO usar pandas.to_excel solo (perdería macros) → usar openpyxl con keep_vba=True
- NO asumir 50 columnas — el template Pet Food tiene 220
- NO hardcodear marketplaces — v1 solo MX, futuro multi-MP
- NO duplicar SKUs entre parent y children
- NO cambiar nombre de hojas — Amazon rechaza si no son exactos

---

## M27 — Flat File Migrator
**Archivo:** modules/pages/flat_file_migrator.py
**Sección sidebar:** Account Health
**Session state prefix:** ffm_
**Fuente:** porteado de `.claude/porting-sources/flat-file-migrator.html` (2026-05-06)

### Propósito
Migrar datos de un flat file viejo de Amazon a un template nuevo, mapeando columnas automáticamente con 5 estrategias en cascada (exact field ID → normalized → alias → base → header). Soporta 5 marketplaces independientes en tabs (US/DE/IT/FR/ES). **Stateless por diseño** — sin persistencia, procesamiento puro in-memory.

### Arquitectura
- 1 tab por marketplace (5 tabs total). Toda la lógica vive en `_render_marketplace(suffix, sheet_names)` parametrizado.
- Parser cacheado `_parse_workbook(file_bytes, file_name, sheet_names)` con `@st.cache_data(show_spinner=False)`. Cache key = bytes hash.
- Builders fuera de `render()`: `_build_migrated_xlsx(rows, sheet_name) → bytes` y `_build_migrated_tsv(rows) → bytes` con BOM UTF-8.
- Helpers porteados literal del HTML: `_detect_header_row`, `_get_headers`, `_is_amazon_internal_row`, `_get_data_rows`, `_detect_file_type`, `_normalize_field_id`, `_looks_like_field_ids`, `_norm_header`, `_match_columns`.
- `_run_migration(...)` orquesta el flujo completo: detecta header rows, extrae field_ids, aplica las 5 estrategias, construye output preservando rows pre-data del template nuevo.

### Reglas de negocio (porteadas literal del HTML)
- **Header row detection**: escanea primeras 11 rows, prioriza row con keywords típicas Amazon (`sku`, `item_sku`, `feed_product_type`, `seller sku`, `verkäufer-sku`, `sku venditore`, `référence vendeur`, `sku del vendedor`, etc.). Multi-idioma EN/DE/IT/FR/ES.
- **5 estrategias de matching en orden estricto**:
  1. Exact field ID (lowercase)
  2. Normalized field ID (sin brackets, hash, sufijos)
  3. Aliases bidireccionales (~40 mappings: `item_sku ↔ contribution_sku`, `brand ↔ brand_name`, `main_image_url ↔ main_product_image_locator`, `other_image_urlN ↔ other_product_image_locator_N`, etc.)
  4. Base name only
  5. Header normalizado (lowercase, sin spaces/underscores/dashes) — fallback cuando no hay field IDs
- **Filtro de filas internas Amazon**: regex `marketplace_id=` · `amzn1\.volt\.` · `#\d+\.value` · `\[language_tag=` + heurística "tipo SHIRT/SHOES con commas"
- **Skip example row** (default ON): saltea la primera data row del old (ejemplo Amazon)
- **Preserva rows pre-data del template nuevo**: header rows, field IDs, separadores se copian tal cual; luego una row vacía separadora; luego data del old mapeada a posiciones del new
- **Output**: XLSX (openpyxl) o TSV con BOM UTF-8 (`﻿` prefix)
- **Sheet matching**: 1) match exacto lowercase contra `sheetNames` esperados, 2) contains, 3) primer sheet del workbook
- **Header row override quirky logic** (HTML L997-998): si user pone `1` y auto > 0 → usa auto. Si user pone otro valor → usa user. **Replicado tal cual.**

### Marketplaces v1
| Marketplace | Sheet names esperados (en orden) |
|---|---|
| 🇺🇸 USA | `Template` |
| 🇩🇪 Germany | `Vorlage`, `Template` |
| 🇮🇹 Italy | `Modello`, `Template` |
| 🇫🇷 France | `Modèle`, `Template` |
| 🇪🇸 Spain | `Plantilla`, `Template` |

Cada marketplace es totalmente independiente (state propio en widget keys con prefijo `ffm_{suffix}_`).

### Inputs
- **Old Flat File** (.xlsx, .xls, .xlsm, .tsv, .csv, .txt) — flat file viejo con datos
- **New Flat File** (.xlsx, .xls, .xlsm, .tsv, .csv, .txt) — template nuevo descargado de Seller Central → Catalog → Add Products via Upload → Download Template

### Outputs
- Stats: columnas migradas / solo en nuevo / no migradas / filas migradas / example row saltada / filas Amazon filtradas / match por método
- Listas color-coded en expander: 🟢 migradas · 🔴 no encontradas en nuevo · 🟠 solo en nuevo
- Download: `{base}_migrated.xlsx` o `{base}_migrated.tsv`

### Validación
- `py_compile` verde en `flat_file_migrator.py`, `app.py`, `core/constants.py`
- Stateless: no hay `st.session_state` para datos persistentes (solo widget keys)
- Empty state con borde dashed `#FFD9B3` y mensaje "📂 Subí los flat files para arrancar"
- Header `🏥 Flat File Migrator` con divider (patrón Account Health)

### Anti-patterns
- NO arreglar bugs del HTML original durante el porting (regla del Caso 1 del porter)
- NO inventar marketplaces nuevos — los 5 son los que el HTML original soporta
- NO usar `pd.read_excel` para parsear — openpyxl preserva mejor la estructura de rows pre-data
- NO usar `aoa_to_sheet` equivalent en pandas — openpyxl `Workbook()` + `ws.append()` es más fiel al output del HTML
- NO eliminar el "Skip example row" checkbox — es comportamiento esperado por el AM
- NO traducir las keywords del header detection — están en 5 idiomas a propósito
- NO modificar el dict `_ALIASES` — es copia literal del HTML, fiel al comportamiento del compañero
- NO omitir el BOM `﻿` en el TSV — el HTML lo agrega y Amazon Seller Central lo espera
- NO permitir output XLSM ni preservar macros del template (el template Amazon flat file no tiene macros relevantes — divergencia respecto a M26 Variation Builder por diseño)

### Deuda técnica heredada del HTML (NO arreglada por regla del Caso 1)
- **Header row override quirky** (L997-998): comportamiento contraintuitivo cuando user pone `1` y hay auto-detect. Documentado, no arreglado.
- **`looksLikeFieldIds` regex frágil** (L1005): falsos positivos posibles en headers cortos. Documentado, no arreglado.
- **`aoa_to_sheet` no preserva data validations / formulas / macros** del new template — solo column widths en HTML, ni eso en el porting Python (openpyxl no lo provee con la misma facilidad). Si el AM reporta pérdida de validations al subir el migrado, evaluar refactor con `keep_vba=True` + copiado de `data_validations` (pero NO durante el porting, sí como sesión separada).
- **Mensaje de error mezcla idiomas** (`'Error al leer el archivo: ' + err.message` en el HTML — alert en español, código en inglés). Replicado en español como `st.error("Error al leer el archivo: ...")`.

### Propuestas no implementadas — para sesiones futuras
- **Preview de los datos migrados** antes de descargar (primeras 20 rows) — útil para validar el mapping a ojo antes de comprometerse al download
- **Editor manual del mapping** post-detección automática: tabla `st.data_editor` para que el AM corrija mappings que el algoritmo no pudo resolver
- **Persistir mappings custom por marketplace** en `data/account_health/flat_file_mappings.parquet` — si el AM aprende que `mi_kw_custom` siempre debe mapear a `generic_keyword`, recordarlo entre sesiones (Caso 2 — requiere coordinación con `data-persistence-specialist`)
- **Soporte input TSV / CSV directo** — el HTML acepta `.tsv` y `.csv` en el `accept` pero `XLSX.read` los parsea con auto-detect. En el porting Python `openpyxl.load_workbook` solo abre Excel — los TSV/CSV no van a funcionar como input. Documentado como limitación del v1.
- **Diff visual entre old → new column mapping** con flechas/líneas (cosmético)
- **Multi-archivo batch**: subir 5 old files al mismo tiempo y migrar a 5 templates distintos en una sola pasada
- **Detección de Category Listing vs Flat File más estricta**: usar el campo `feed_product_type` para mapear automáticamente la categoría correcta y avisar si old y new son de categorías distintas

---

## M28 — SKU Progress Report
**Archivo:** modules/pages/sku_progress_report.py
**Sección sidebar:** Account Health
**Session state prefix:** sku_progress_
**Fuente:** porteado de `.claude/porting-sources/sku-progress-report.html` (2026-05-07)
**Schema:** `data/_schemas/sku-progress-v1.json` (commit d9fd787)
**Persistencia:** `data/account-health/<cliente>/sku-progress/`

### Propósito
Tracker semanal de progreso por SKU. Multi-cliente. Reemplaza el HTML legacy de Gamboa (data embedded) por una capa de persistencia centralizada vía `core.persistence`. Cruza CSVs de "Detail Page Sales and Traffic By Child Item" semanales con un log append-only de optimizaciones aplicadas (cambio de imágenes, A+ Content, etc.) para correlacionar acción → impacto en CVR / sessions / sales.

### Arquitectura
- **Multi-cliente** via `st.selectbox` al tope. El selector lista clientes que tengan carpeta en `data/account-health/<cliente>/sku-progress/`. Si no hay clientes → empty state + botón "➕ Cliente nuevo" que crea la carpeta y el `tracked-skus.json` vacío.
- **Tabs por SKU dentro del cliente seleccionado** + 2 tabs fijas: `📤 Importar CSV` y `⚙️ Admin`. Una tab por SKU recargable: hero (imagen + título + botones), badges de eventos, KPI cards (7), 1 chart cruzado (CVR + Avg Price + Sessions con anotaciones de eventos) + 4 charts en grid 2x2 (Plotly), tabla detallada.
- **Modals via `st.dialog()`**: agregar SKU, editar SKU, registrar/editar evento, confirmar borrado, agregar cliente nuevo.
- **Parser CSV cacheado**: `_parse_csv_bytes(raw, filename)` con `@st.cache_data(show_spinner=False)`. Replica literal de `parseCSV()` del HTML L3267-3332.
- **Consolidación variants**: `_consolidate_rows_by_sku()` replica `buildPreview()` L3433. Una row consolidada por SKU; CVR y avg_price recalculadas POST-consolidación. Decisión bloqueada en el schema (`consolidation_rule.additive_columns` + `derived_post_consolidation`).
- **Excel export**: `_build_sku_progress_excel()` fuera de `render()` (patrón openpyxl-bug-prevention). Hojas: Resumen, Detalle, Optimizaciones, una por SKU.

### Helpers principales
- `_list_clientes()` — escanea `data/account-health/*/sku-progress/`
- `_load_tracked_skus(cliente)` / `_save_tracked_skus(cliente, config)` — JSON per-cliente (excepción documentada abajo)
- `_period_str(year, week_iso)` — `"2026-W14"` canonical
- `_parse_period_str(period)` — inverse
- `_iso_week_dates(year, week_iso)` — devuelve (lunes, domingo)
- `_week_label_es(year, week_iso)` — `"Mar 29-Abr 4"` (ES)
- `_detect_week_from_filename(filename)` — soporta `2026-W14`, `W14`, `wk14`, `semana14`
- `_parse_csv_bytes` / `_split_csv_line` — replica literal del parser JS
- `_consolidate_rows_by_sku` — replica de buildPreview con consolidación de variants
- `_build_snapshot_df` — construye DataFrame con schema sku-progress-v1
- `_render_sku_tab` / `_render_import_tab` / `_render_admin_tab` — sub-renders
- `_dialog_add_sku` / `_dialog_edit_sku` / `_dialog_add_event` / `_dialog_confirm_delete_sku` / `_dialog_add_cliente` — modals via `@st.dialog`

### Reglas de negocio (porteadas literal del HTML)
- **CSV_PRIORITY**: priority list de headers (espejo HTML L3236) — `sessions - total > sessions`, `unit session percentage > order item session percentage`, etc.
- **CSV_IGNORE**: ~30 columnas descartadas siempre (splits B2B / Mobile / Browser, percentages no relevantes). Espejo HTML L3248.
- **Year=2026 hardcoded en v1** (decisión Lenin). El campo `year` es editable en el form de import por si el AM carga retro.
- **Una fila consolidada por SKU** en el snapshot. Variants se agregan ANTES de escribir Parquet — additive: sessions, page_views, units_ordered, total_order_items, ordered_product_sales. Derived post-consolidación: `unit_session_pct = units_ordered / sessions * 100` y `avg_price = ordered_product_sales / units_ordered`.
- **Match SKU**: equality case-insensitive primero, fallback a substring bidireccional (heredado del HTML — bug documentado abajo).
- **Eventos = log append-only**: cada evento es 1 row inmutable en `optimizations.parquet`. Editar/borrar eventos NO existe en v1 — el HTML sí los permitía pero el modelo append-only del agency OS lo prohíbe. Si se quiere "borrar" un evento, agregar uno nuevo con label `"REVERT: <label original>"` (deuda técnica documentada abajo).

### Inputs
- **CSV semanal "Detail Page Sales and Traffic By Child Item"** (Seller Central → Reports → Business Reports). UTF-8 con BOM o latin-1 fallback.
- **Cliente** (selectbox al tope) — auto-discover de `data/account-health/*/sku-progress/`.
- **SKU agregado vía modal**: SKU obligatorio, ASIN/title/image_url/link opcionales.
- **Evento agregado vía modal**: SKU + week (period) + label libre.

### Outputs
- **Snapshot Parquet semanal** en `data/account-health/<cliente>/sku-progress/<YYYY-WW>.parquet` validado contra schema sku-progress-v1.
- **Log Parquet append-only** en `optimizations.parquet`.
- **Excel multi-hoja** descargable: Resumen + Detalle + Optimizaciones + una hoja por SKU con su evolución completa.

### Excepción documentada — `tracked-skus.json` NO usa `_save_config` / `_load_config`

`core.persistence._save_config()` y `_load_config()` son **client-agnostic por diseño** (path: `data/<area>/<modulo>/<name>-v<version>.json`, sin nivel cliente). El config de SKUs trackeados de SKU Progress es **per-cliente** y debe vivir junto a los snapshots para que un borrado total del cliente sea atómico (carpeta única `data/account-health/<cliente>/sku-progress/`).

Por eso el módulo define helpers locales:
```python
_load_tracked_skus(cliente: str) -> dict        # lee data/account-health/<cliente>/sku-progress/tracked-skus.json
_save_tracked_skus(cliente: str, config: dict)  # escribe en el mismo path
```

**Regla del skill data-persistence-standard**: "los casos especiales matan el patrón". NO se promueve esta excepción a la API global hasta que aparezca un M30+ con la misma necesidad de config per-cliente. Si eso pasa, el `data-persistence-specialist` evalúa agregar `_save_client_config` / `_load_client_config` a `core/persistence.py`.

### Excepción 2 — `shutil.rmtree()` para borrar cliente entero

Helper privado `_delete_cliente()` en el módulo usa `shutil.rmtree()` directo sobre `data/account-health/<cliente>/`. NO se delegó a `core/persistence.py` porque:

- El skill `data-persistence-standard` tiene regla dura "cero borrados automáticos" (apunta al código corriendo solo, no al usuario clickeando un botón en UI).
- La acción está protegida por type-to-confirm en `_dialog_borrar_cliente`: el usuario debe escribir el slug exacto del cliente para habilitar el botón "Borrar definitivamente".
- El borrado es atómico (carpeta única `data/account-health/<cliente>/`) — todo el tracking del cliente se va de una vez, sin estados parciales.
- Counts pre-delete se muestran en el dialog para feedback explícito antes del confirmar.

Trigger de promoción a `core/persistence.py`: si aparece un 2do módulo Account Health con la misma necesidad de borrar cliente entero (ej: M29 Pricing Dashboard cuando se portee), promover a `_delete_cliente_data(area, cliente)` (~12 líneas, retrocompatible). Hasta entonces, vive como helper local del módulo M28.

### Validación end-to-end
- `py_compile` verde en `sku_progress_report.py`, `app.py`, `core/constants.py`
- No hay `pd.read_parquet` ni `pd.to_parquet` directo en el módulo (todo via `core.persistence`)
- No hay `pd.read_csv` en el módulo (parser custom byte-level porque el HTML usa parser JS custom — preserva paridad con el HTML legacy)
- El JSON de config se gestiona localmente con `json.loads/dumps` (excepción documentada arriba)
- Empty states correctos: sin clientes → mensaje + botón "Cliente nuevo"; cliente sin SKUs → mensaje + indicación dónde bajar el CSV
- Header `🏥 SKU Progress Report` con divider (patrón Account Health)
- Excel builder fuera de `render()` (patrón anti-bug openpyxl)
- 1 solo `return` dentro de `render()` — para early-exit cuando no hay clientes

### Deuda técnica heredada del HTML (NO arreglada por regla del Caso 2)
- **Match SKU substring bidireccional** (HTML L3444): el matching `id.includes(k.toUpperCase()) || k.toUpperCase().includes(id)` puede generar falsos positivos. Ej: SKU "ABC" matchea row del CSV con id "ABC123" (y viceversa). Documentado, no arreglado para preservar paridad. Si el AM reporta cruces incorrectos, escalar a sesión separada.
- **`splitCSVLine` no maneja escaped quotes** (HTML L3335): un campo con `""` adentro (escape de comilla) no se parsea correctamente. Limitación del parser JS replicada literal en Python. Mitigación: el CSV de Amazon "Detail Page Sales..." rara vez tiene quotes anidadas — si aparece, el AM verá warning de fila descartada.
- **`weekLabel` JS hardcodea año 2025** (HTML L3386): inconsistente con el contexto del módulo (2026). En el porting Python NO se replica — usamos `date.fromisocalendar(year, week_iso, 1)` que es correcto. Esta es la **única divergencia funcional** del porting (la otra es exportHTML, que se reemplaza por persistencia).
- **Subtítulo del header HTML hardcodea 2025** (L3563): no aplica al porting (no hay subtítulo dinámico).
- **`confirm()` browser native** (HTML L2991, L3052, L3069): UX inconsistente. En el porting se reemplaza por `st.dialog()` con botones explícitos (mejor UX, pero divergencia documentada).
- **Validación URL imagen** (HTML `onerror`/`onload`): en Streamlit `st.image()` muestra placeholder/error si la URL no carga, sin bloqueo del flow. Equivalente funcional.
- **No se permite editar/borrar eventos individuales** (divergencia con HTML que sí los permite): el modelo append-only del Agency OS los hace inmutables. El HTML usaba splice/index access que no es compatible con Parquet append-only. Documentado como deuda funcional.

### Propuestas no implementadas — para sesiones futuras
- **Migración de la data Gamboa actual del HTML legacy**: el HTML tiene 21 SKUs × 15 semanas (Ene-Abr 2026) + eventos ya cargados. La migración no se hace en esta sesión por decisión Lenin (validar primero módulo vacío). Plan: script `scripts/migrate_gamboa_sku_progress.py` que parsee el `DATA = {...}` const del HTML, construya 15 snapshots Parquet + N filas en optimizations.parquet + 1 tracked-skus.json. Sesión separada.
- **Edit/delete de eventos individuales**: hoy el log es append-only. Para "deshacer" un evento, agregar uno nuevo con label `"REVERT: <label original>"`. Mejor UX: agregar columna `_deleted: bool` al schema (v2) y filtrar en `_load_log` con flag `include_deleted=False`. Discutible si vale la pena romper la inmutabilidad.
- **Vista cross-SKU del cliente** (dashboard de salud agregado): hoy cada SKU es una tab; falta una vista "total cliente" con todos los SKUs en una matriz CVR×Sales. Útil cuando el cliente tenga >10 SKUs.
- **Filtro temporal en tabs SKU**: hoy se muestran todas las semanas con datos. Útil agregar slider "últimas N semanas" para vistas focalizadas.
- **Detección automática de week del CSV**: hoy detecta del filename con regex. Si falla, usa la semana actual. Mejora: parsear la columna "Reporting Range" del CSV (Amazon a veces la incluye).
- **Comparativa entre 2 clientes**: para detectar patterns cross-clientes (ej: "Gamboa y Dermaglos cayeron en CVR la misma semana — ¿problema Amazon?"). Requiere multi-cliente desktop view.
- **Heatmap de optimizaciones aplicadas**: vista calendario que muestra qué semanas tuvieron eventos y cuáles no. Útil para identificar gaps de actividad del AM.
- **Export PDF para cliente**: hoy solo Excel. Para presentaciones cliente-facing, un PDF con gráficos embebidos es mejor.

### Anti-patterns
- ❌ NO usar `pd.read_csv` directo — el parser custom byte-level (replicando JS) es deliberado para preservar paridad con el HTML legacy.
- ❌ NO promover `_load_tracked_skus`/`_save_tracked_skus` a `core/persistence.py` hasta que aparezca M30+ con la misma necesidad.
- ❌ NO arreglar bugs del HTML durante el porting (regla del Caso 2): match substring bidireccional, escape quotes, etc. Documentar, no fixear.
- ❌ NO replicar `exportHTML()`: los datos viven en `data/`. Cambio de UX deliberado, decisión bloqueada en daily 2026-05-06.
- ❌ NO hardcodear años (excepto YEAR_DEFAULT=2026 que es decisión bloqueada v1).
- ❌ NO usar `pd.read_parquet`/`pd.to_parquet` directo — todo I/O via `core.persistence`.
- ❌ NO permitir borrar/editar eventos via UI individual del badge (modelo append-only).
- ❌ NO usar `st.metric` — usar `kpi_card` de `core.helpers`.
- ❌ NO portar el CSS dark del HTML — el Agency OS es light theme.
- ❌ NO mezclar lógica I/O en `render()` — pasar todo por `_save_snapshot`/`_append_log`/`_rebuild_history` después de la acción del usuario.


---

## M30 — Pricing Dashboard
**Archivo:** modules/pages/pricing_dashboard.py
**Sección sidebar:** Account Health (label `💲 Pricing Dashboard`)
**Session state prefix:** m30_ (m30_resultados, m30_aviso_backup, m30_filtros)
**Fuente:** porteado de `.claude/porting-sources/pricing-dashboard.html` (Caso 2, port verbatim)
**Schema:** `data/_schemas/pricing-dashboard-v1.json` (47 col, 21 required, primary_key sku)
**Persistencia:** `data/account-health/<cliente>/pricing-dashboard/<YYYY-MM-DD>.parquet` + config `data/account-health/pricing-dashboard/<cliente>-v1.json`

### Propósito
Scoring de pricing semanal por SKU: clasifica cada SKU en bajar / subir / liquidar / mantener con precio sugerido y rationale, cruzando FBA inventory + fees + P&L (COGS) + maestro de productos. Espejo fiel del HTML standalone del compañero.

### Arquitectura (F3.1–F3.6)
- **F3.1** schema v1 + test persistencia. **F3.2** 6 parsers (`_parse_fba/_fee/_awd/_pl/_maestro/_izzi`, bytes→DataFrame, `@st.cache_data`) + 3 lookups (`_build_cogs/_fee/_maestro_lookup`). **F3.3** scoring (`_compute_ais`, `_compute_score` 20+ reglas umbrales asimétricos, `_enrich_record`, `_run_analysis`). **F3.4** UI: render() + selector cliente + 6 uploaders + `st.tabs` (Resumen/Principal/AWD-FBA/Liquidar/Sin Margen/AIS/Histórico) + styler + filtros + persistencia/import JSON. **F3.6** integración router.
- **Config per-cliente** vía `core.persistence._save_config/_load_config` (`_load_or_seed_config` seedea SUBCAT_FEE_AVG verbatim del HTML la primera vez; NUNCA persiste current_month).
- **Snapshots/histórico** vía `core.persistence` verbatim (`_save_snapshot/_load_history/_list_periods/_rebuild_history/_validate_against_schema`). `_build_snapshot_df` mapea record_key→schema_col (los nombres DIFIEREN: Modelo→modelo, fulfillment_fee→ff, suggestedPrice→suggested_price, reasons_* list→JSON string, etc.) y coacciona dtypes a las 47 col exactas.
- **Import JSON** (`_importar_historico_json`): array `{date, skus:{...}}` del HTML; 2-pasadas (build+valida todo en memoria, recién después persiste + rebuild) → all-or-nothing.

### Reglas de negocio (porteadas literal del HTML)
- **Umbrales asimétricos**: `score <= -50` → bajar; `score >= 20` → subir; is_liquidar PRECEDE a la clasificación por score.
- **Bug 30-vs-37 (heredado, NO arreglar)**: `_enrich_record` setea restock con PATH-37 (`round(daily_rate*37)`, msg "a FBA desde"); el PATH-30 de `_compute_score` (`*30`, "desde", guard `not restock_alert`) queda dead-code.
- **Rounding**: `_round_half_up` (=floor(x+0.5)) replica `Math.round` (NO `round()` nativo). `_to_fixed`/`_js_num` para strings.
- **Separador CSV** autodetectado (;/, en primera línea) + utf-8-sig; NO replica el parseCSV custom del HTML (trim/descarte <2 campos) — divergencia conocida congelada en `TestCsvDivergenciasHTML`.
- **current_month** desde config (fallback `date.today().month`) para isOffSeason determinístico.

### Deuda / gaps conocidos
- **AWD/Izzi sin builder**: `_parse_awd/_parse_izzi` devuelven DataFrame crudo; no hay builder df→lookup `{sku: unidades}`. La tab AWD/FBA es un panel pendiente (`st.warning`), backup stock = 0. Diferido (F3.2→F3.3 nunca lo construyó).
- **F3.5 (export XLSX) pendiente**.

### Anti-patterns / reglas
- ❌ NO tocar parsers/lookups/scoring de F3.2-F3.3 (cerrados, reviewer-aprobados).
- ❌ NO crear helpers de persistencia nuevos — todo I/O via `core.persistence` verbatim.
- ❌ NO normalizar strings de Amazon ('Excess','Invierno'...) — verbatim.
- ❌ NO usar `round()` nativo donde el HTML usa `Math.round` — usar `_round_half_up`.
- ❌ NO persistir current_month en el config.


---

## SOP in-app por módulo (convención, 2026-06-21)
Cada módulo de cara al usuario embebe su guía de uso como:
- Constante módulo-level `_SOP_MD` = string markdown triple-quoted, ubicada junto a las otras constantes del tope del archivo.
- En `render()`, apenas debajo del header del módulo: un `st.expander("📘 Cómo usar este módulo", expanded=False)` con `st.markdown(_SOP_MD)` adentro. TOP-LEVEL, nunca anidado dentro de otro expander/popover.
Aplicado en: sku_progress_report.py, pricing_dashboard.py, proposal_studio.py (commits 2607b4e + 797f7eb).
La copia de equipo (fuera de la app) vive en notes/sops/SOP_USER_*.md. El `_SOP_MD` del módulo es la fuente de verdad; los .md se mantienen en sync con él.

---

## M37 — Cuentas conectadas (`accounts.py`)

**Propósito.** El otro lado del portal: las cuentas de cliente que un vendedor autoriza por
OAuth. Vive en `⚙️ Sistema → Cuentas conectadas` y la ve **todo empleado**, no sólo admin.

**Por qué no está adentro de Mercado Libre.** La autorización es transversal: mañana entran
Amazon y Walmart y se suman como bandas acá. Si viviera en M36, la primera pantalla nueva
que necesite una cuenta de MELI tendría que ir a buscar la autenticación a otro módulo.
La divisoria con M38 es el permiso y el radio: credencial del sistema (una, admin, rompe a
todos) vs cuenta conectada (una por cliente, cualquiera, rompe a uno).

**Conectar no pide ningún campo.** El link de consentimiento se arma al abrir el diálogo, y
quién es la cuenta lo completa el worker al cerrar el grant con el **resolver de identidad
del proveedor** (`_IDENTITY_RESOLVERS` en `core/integrations/worker.py`: `/users/me` para
Mercado Libre, `core/integrations/amazon_identity.py` para Amazon). Pedirle el slug a quien
conecta era pedirle un dato que el proveedor ya sabe. Un proveedor sin resolver y sin
`user_id` en el token hace fallar el canje: antes se guardaba sobre `(slug, '')` y cada
cuenta pisaba la anterior.

**Dos formas de proveedor en la misma pantalla** (`Integration.discovers_accounts`).
- Mercado Libre: autoriza el vendedor; la conexión ES la cuenta del cliente, una fila.
- Amazon Ads: autoriza un **empleado de Capybaras** con su usuario de Amazon, al que cada
  cliente invitó a su cuenta. Una autorización alcanza N cuentas de clientes, en NA/EU/FE.
  La fila de `integration_connections` es la autorización (token, `consent_date`,
  vencimiento); las cuentas viven en `integration_accounts` (migración 006), una por
  entidad de Amazon, apuntando a la autorización que la vio por última vez. La banda
  muestra "Autorizaciones" y debajo "Cuentas de clientes", cuyo estado hereda de su
  autorización. `worker discover` re-lista las cuentas sin reautorizar.
- Los hechos del proveedor viajan en el catálogo: `refresh_rotates`,
  `refresh_token_lifetime_days`, `discovers_accounts`. NO agregar `if slug ==` en la
  pantalla ni en el worker: si hace falta distinguir, es un atributo del catálogo o un
  resolver.

**`expiring_soon` no existe en la base.** Se deriva en cada render de `consent_date` más
`refresh_token_lifetime_days` (`core/integrations/consent_expiry.py`), desde 45 días antes.
Pinta el pill "Vence en N días" y pone Reautorizar en la fila; el punto ámbar del menú
(`core/integrations/notice.py`) lo cuenta también, y se pinta en las dos pantallas de
Sistema porque Integraciones es admin-only y el botón está acá.

**Cada click en Conectar o Reautorizar abre un grant nuevo** (`_open_connect_dialog` limpia
el cache del link). El cache en `session_state` existe sólo para que los reruns del propio
diálogo no quemen un grant cada uno; un `state` ya canjeado no se vuelve a ofrecer.

**Reglas de negocio.**
- El grant se abre con un cliente provisorio `_pending_<state[:12]>`; el worker lo reemplaza
  cuando canjea. Si dos cuentas del mismo proveedor colisionan en slug, se desempata con el
  site (`MLA`, `MLM`).
- Una fila en `needs_reauth` muestra su propio botón **Reautorizar**: reabre el mismo flujo
  sobre la misma cuenta, y el cierre va por `upsert` con
  `on_conflict=integration_slug,cuenta_externa_id` — `insert` choca en 409 contra el unique.
- El estado de la conexión se espeja a `meli_auth_identities` (`_mirror_on_identity`): sin
  eso, el portal decía "requiere reautorizar" y la ingesta seguía intentando con la
  identidad marcada activa.

**Estilo.** Cero hex propios: todo sale de `core/ui/palette.py`. Los textos salen de
`core/ui/i18n.py` — el módulo no tiene literales de UI.

**Anti-patterns.**
- ❌ NO llamar a `st.rerun()` dentro de un `st.dialog`: cierra el diálogo. Para encadenar
  dos pasos va el patrón de señal en `session_state`, no un diálogo anidado (no existen).
- ❌ NO armar el link de consentimiento en el render de la fila: se arma al abrir el
  diálogo, una sola vez por `state`, o cada rerun quema un grant nuevo.
- ❌ NO leer el estado de la cuenta sólo de `integration_connections` sin mirar la identidad
  espejada — quedan en desacuerdo.
- ❌ NO poner texto de UI en el módulo: va al catálogo de `core/ui/i18n.py`, en las dos
  lenguas, o el toggle del sidebar deja la pantalla a medio traducir.

---

## M38 — Integraciones (`integrations.py`)

**Propósito.** Portal de credenciales de todas las integraciones, para dejar de editar `.env` por SSH en el VPS.

**Dos niveles, con cardinalidad y permisos distintos.**
- *Credencial del sistema*: una por integración. API key de la agencia, o `client_id`/`client_secret` de la app OAuth. Sólo admin.
- *Cuenta conectada*: N por integración, una por cliente. La autoriza el vendedor. Cualquier usuario puede conectar.

**Dos clases de almacenamiento, elegidas por quién consume la credencial.**
- `APP_READABLE`: la lee el propio proceso de Streamlit (DataDive). Cifrarla la volvería inutilizable.
- `SEALED`: cifrada con RSA-OAEP; sólo la abre el worker. Correcta para un `client_secret` que gobierna N cuentas.
- La pantalla nunca dice "sellada": dice **cifrada**. `sealed` es el nombre interno, no el del usuario.
- El test `test_lo_que_consume_la_app_no_puede_ser_sellado` blinda esa regla.

**Reglas de negocio.**
- El invariante "escribir sin leer" lo garantiza el GRANT por columna de `002_integrations.sql`, no el chequeo de rol en Python: `AGENCY_OS_LOCAL_MODE` puentea el login entero.
- Los writes van con `Prefer: return=minimal`. Pedir la representación fuerza un SELECT y PostgREST responde 403 — por eso este módulo no puede reusar el transporte de `core/persistence.py:431`.
- `guardar()` invalida y después inserta. Un upsert leería `excluded` sobre la columna sellada.

**El catálogo es una lista en bandas, no una grilla de tarjetas** (rediseño 2026-09-03).
- Arriba, un **veredicto** de dos líneas que contesta "¿hay algo roto y a qué cliente le pega?".
  Tres ramas y sólo tres: 0 rotas / 1 rota (nombra al cliente) / N rotas (cuenta, no nombra —
  los nombres bajan a las sub-líneas). No declara una hora: `last_sync_at` no lo escribe nada
  en el repo, así que una hora ahí sería inventada.
- Cuatro bandas en orden fijo (`SIN PODER CONFIRMAR` · `REQUIERE ATENCIÓN` · `SE PUEDE CARGAR`
  · `EN SERVICIO`). **Una banda sin filas no se dibuja** — su ausencia es el mensaje.
- Fila de 44px con siete celdas (`st.columns(_PESOS_FILA, vertical_alignment="center")`) dentro
  de `st.container(key=...)`. La `key` **sí** baja al DOM en 1.43.2 (`convertKeyToClassName` →
  `st-key-<key>`): todo el CSS cuelga de `.st-key-ig_lista`, sin un solo `:has()`.
- Prefijos de key: `ig_lista` · `ig_banda_<n>` · `ig_fila_<slug>` · `ig_att_<slug>` ·
  `ig_att_<slug>_<conexion.id>`. El prefijo `ig_att` es lo que pinta el riel naranja.
- La cuenta del cliente caída sube a **sub-línea propia** bajo su integración, con su propio
  botón `Reautorizar`. Tope de 4 más una fila `y N más`.
- `PROXIMAMENTE` **no es una fila**: es una oración al pie. Ese cambio de clase estructural es
  lo que lo separa de "Andando, fuera del portal" sin depender del color.
- `Contexto.lectura_ok` distingue "no hay nada cargado" de "no se pudo preguntar". Sin eso,
  PostgREST intermitente pintaba "Sin configurar" sobre credenciales que existen.
- `#F59E0B` salió del módulo: da **2,15:1** sobre blanco y ni llega al 3:1 de elemento no
  textual. El ámbar de atención es `#B02A00` (6,61:1).

**Estilo e idioma.** Cero hex propios: todo sale de `core/ui/palette.py`. Cero literales
de UI: salen de `core/ui/i18n.py`, en las dos lenguas.

**Anti-patterns.**
- ❌ NO agregar `secret_sealed` a ninguna lista de SELECT: tumba la página entera con un 403.
- ❌ NO meter texto que venga de la base en el HTML de una celda sin `html.escape`: `cliente` y
  `created_by` los tipea una persona y viajan hasta un `unsafe_allow_html`.
- ❌ NO dejar que una celda secundaria envuelva: estira esa fila y reaparece el escalón que la
  grilla tenía. Clase y Hecho se cortan en una línea, con el valor entero en el tooltip.
- ❌ NO usar `insert` para cerrar un grant OAuth: `integration_connections` declara
  `unique (integration_slug, cuenta_externa_id)` y reautorizar la misma cuenta choca en 409.
  Va `_Rest.upsert` con `Prefer: resolution=merge-duplicates`.
- ❌ NO mostrar un secreto enmascarado (`sk-••••3f2a`): insinúa que la app lo tiene y no lo muestra, lo cual es falso. Va la huella.
- ❌ NO renderizar un botón deshabilitado por falta de permiso: se omite el botón.
- ❌ NO tratar `AGENCY_OS_LOCAL_MODE` como admin — para eso está `AGENCY_OS_LOCAL_ADMIN`.
- ❌ NO ofrecer una acción que no puede funcionar: si falta la base o el worker, eso es el ESTADO de la tarjeta, no un error después de que alguien tipeó un secreto.
- ❌ NO pedirle al admin que genere la clave de cifrado desde la UI: la genera `worker keys` al instalar y publica sola la mitad pública.
- ❌ NO dejar que una falla de red llegue a pantalla como excepción — `_mensaje_error` la traduce y el detalle va al log.

---

## M39 — Registro de solicitudes (`request_log.py`)

**Propósito.** El historial de cada pedido de datos que el sistema hace a las cuentas conectadas y su estado
(en cola, pidiendo/esperando a Amazon, guardando, reintentando, completada, fallida, cancelada), con las alertas
arriba. Vive en `⚙️ Sistema → Registro de solicitudes` y es **sólo admin**.

**Admin-only en dos capas, como Integraciones y Skills.** La página está en `navigation.ADMIN_ONLY` (no aparece en
el riel ni en la búsqueda) y `render()` chequea `roles.is_admin` antes de abrir la base; los handlers de
Reintentar/Cancelar lo vuelven a chequear. La base no distingue admin de usuario (toda la app usa el JWT `web_user`):
lo que sí limita es que `web_user` sólo lee las tablas y escribe a través de tres funciones acotadas
(`request_manual_refresh`, `retry_sync_job`, `cancel_sync_job`).

**Genérico por proveedor.** Lee `integration_sync_jobs` (migración 009) con `core/integrations/sync_jobs.py`. Hoy
escribe ahí el worker de Amazon Ads; Mercado Libre entra cuando `core/meli_api/ingest.py::_start_run/_finish_run`
pasen a abrir y cerrar jobs en esta tabla, sin tocar la página.

**Alertas derivadas, sin tabla propia** (`core/integrations/sync_alerts.py`): falló hoy sin completarse después,
primera carga fallida (error, sin corte de 24 h, con Reintentar), trabada, datos que no llegaron a las 09:00 del
perfil, worker sin latido hace más de 5 min, autorización rechazada, consentimiento que vence en 45 días. De cada cuenta y tipo sólo se alerta la última falla, y no mientras haya una
solicitud más nueva de esa cuenta en cola, en curso o reintentando (por ejemplo, el reintento recién pedido). El punto del menú sale de `notice.sync_alert_counts()` (rojo con errores, ámbar
con avisos) y sólo se calcula para admins. Si la lectura falla, la página dice que no pudo leer: nunca "todo al día".

**Reglas.**
- Reintentar crea una solicitud nueva (`retry_of`) con la autorización actual del perfil y la fallida queda en el
  historial; no se puede reintentar si el perfil ya no está activo. Cancelar aplica a solicitudes en cola y a las que
  quedaron trabadas (en curso con el lease vencido); una en curso con lease vigente no se cancela.
- Las horas se muestran en hora de Argentina; los "días" de cada perfil (03:00, 09:00, ayer) son hora del perfil.
- `attempts` cuenta intentos fallidos: la pantalla muestra `attempts+1` mientras corre o cuando se completó.
- Las filas no se borran (~decenas de miles por año): no hay excepción a "sin borrados automáticos" acá.

**Anti-patterns.**
- ❌ NO mostrar `error_message` sin pasar por `sanitize_error` al escribirlo: una URL prefirmada de Amazon es una credencial.
- ❌ NO agregar el punto de alerta al título de la sección Sistema: cambiar el label de un `st.expander` resetea si está abierto.
- ❌ NO correr la ingesta desde la página: Reintentar sólo encola.

---

## Datos de Amazon Ads para otros módulos (capa compartida, 2026-09-14)

La ingesta del Search Term Report NO es de M2: el servicio `ads-sync-worker` (`python -m core.amazon_ads.worker run`)
baja los reportes una vez por perfil de Amazon y los guarda por día en `ads_search_term_daily`, con IDs de campaña /
ad group / keyword, `keyword_type`, match type, targeting, portfolio, moneda y las atribuciones de 7 y 14 días.
Cualquier módulo que hoy pide el STR a mano (Bid Optimizer, Análisis de Funnel, PPC Insights; Análisis Cruzado y PPC
Audit lo sacan del Bulk File) puede leer lo mismo sin tocar la ingesta.

**Cómo leer.**
- Selector listo para usar: `render_source_picker(key_prefix="<prefijo del módulo>", allow_manual=..., module_label=...)`
  (`modules/pages/search_term_source.py`) → `SearchTermSource` con la tabla canónica, la moneda y la firma.
- Sin UI: `ReportProvider(rest).profiles()` y `ReportProvider(rest).search_terms(option, desde, hasta)`
  (`core/amazon_ads/report_provider.py`, sin Streamlit). Devuelve las columnas del export de la consola
  (`core/search_term_frame.console_columns`) más los IDs ocultos al final.
- Vendors usan la atribución de 14 días y sellers la de 7, resuelto en el provider.

**Qué hay que agregar según el módulo.**
- Series por día (tendencias): una función SQL nueva sobre `ads_search_term_daily`; la tabla ya es diaria.
- Módulos que esperan los IDs con nombres del Bulk File (`Campaign ID`, `Ad Group ID`): un adaptador chico, no otra ingesta.
- Otro tipo de reporte de Amazon (targets, productos publicitados): un `ReportKind` nuevo en
  `core/amazon_ads/report_kinds.py` (su `job_kind`, su spec de reporte, su tabla y su normalizador, con topes
  propios de reportes en vuelo). La cola, los reintentos, el registro y las alertas son los mismos.

**Grano de campaña (2026-09-17).** Dos solicitudes diarias más por perfil, desde las 03:00: `campaign_entities`
(foto de `/sp/campaigns/list` en `ads_campaign`) y `sp_campaigns` (reporte `spCampaigns` de 65 días en 3 tramos,
reemplazado día por día en `ads_campaign_daily`). Tope compartido por todos los perfiles: 3 reportes en vuelo, 3
pedidos y 3 guardados por tick, y los search terms van primero en cada paso. Selector: `render_campaign_source(key_prefix)`
(`modules/pages/campaign_source.py`); sin UI: `CampaignProvider(rest).campaigns(option, desde, hasta)`. M8 puede
leerlo igual que M6.

**Operación.** Horarios: diaria de 14 días a las 03:00 del perfil (lunes a sábado), 42 días los domingos, carga
inicial de 65 días (la retención de `spSearchTerm`) apenas aparece una cuenta, reintentos hasta las 23:00 del perfil.
El crudo de cada reporte queda en el volumen `ads_raw` 180 días y se borra sólo desde `ads_report_requests` (excepción
documentada a "sin borrados automáticos": son copias secundarias; los datos normalizados nunca se borran solos).
Deploy, puente con la VPS y runbook: `deploy/integrations/DEPLOY.md`.
