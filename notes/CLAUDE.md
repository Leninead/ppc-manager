# CLAUDE.md — Vault de Capybaras Agency

Guía para que Claude Code use este vault como memoria persistente de la agencia. Aplica siempre que trabajés desde la carpeta notes/ o cualquier subcarpeta.

## Propósito del vault

Este vault es el cerebro operativo de Capybaras Agency. Acá vive:

- SOPs y procesos operativos.
- Estado actual de cada cliente activo.
- Diario de sesiones de trabajo.
- Knowledge base de research, tendencias Amazon/eCommerce, learnings del equipo.
- Prompts reutilizables.

Existe en paralelo al repo de código (C:\proyectos\ppc-manager). El CLAUDE.md de la raíz del repo cubre la app Streamlit; este cubre el vault.

## Estructura de carpetas

Archivos en la raíz de notes/: README.md (homepage / puerta de entrada), CLAUDE.md (este doc), Biblioteca.md (índice histórico, archivado), _cheat-sheet-diario.md.

Carpetas (14):
- _archive/ — histórico del vault fuera de circulación (no borrar, trazabilidad)
- api-integration/ — casos de integración con APIs (ej. SPP)
- brands/ — una carpeta por cliente activo
- daily/ — resúmenes por sesión, nombre YYYY-MM-DD.md
- decisiones/ — ADRs (decisiones de arquitectura)
- knowledge/ — research, tendencias, hallazgos
- meetings/ — notas de reunión
- modules/ — planes de implementación por módulo (M27–M36)
- personal/ — contenido personal de Lenin (LinkedIn, etc.)
- prompts/ — prompts maestros reutilizables (arranques en prompts/sesion/)
- sales/ — contratos y specs del área Sales
- sops/ — procesos operativos, separados en dev/ · usuario/ · agencia/
- state/ — estado actual (STATE-agencia + STATE por cliente)
- walmart/ — research de expansión a Walmart Connect

## Reglas de escritura

### Convenciones de nombre

- Archivos nuevos: kebab-case (dermaglos-q2-2026.md, no DermaglosQ22026.md).
- Dailies: YYYY-MM-DD.md (2026-04-24.md).
- Knowledge dated: YYYY-MM-DD-slug.md (2026-03-21-amazon-ads-mcp-server.md).
- Archivos existentes con MAYÚSCULAS o espacios (DERMAGLOS.md, PPC-SOP-Manager.md) se dejan como están. No renombrar.

### Frontmatter mínimo obligatorio

Toda nota nueva empieza con un bloque YAML al inicio:

- tipo: uno de (state, sop, daily, knowledge, brand, prompt, personal)
- actualizado: YYYY-MM-DD
- cliente: opcional — solo si la nota es de un cliente específico (dermaglos, ltd, setex, mb, pura-vida-moringa, 360essentials)

Sin otros campos salvo razón específica.

### Wikilinks para conectar notas

Claude usa wikilinks estilo Obsidian al referenciar otras notas:

- Bien: ver [[DERMAGLOS_DATA]] para el detalle histórico
- Bien: aplicamos la regla de [[atom11-template]] con ajustes
- Mal: usar links markdown con rutas relativas

Los wikilinks no necesitan ruta completa ni extensión .md — Obsidian los resuelve por nombre único.

### Notas atómicas

Una idea = una nota. Si estás escribiendo sobre dos temas distintos, son dos notas conectadas por wikilink. Excepción: STATE y brand notes son agregadores por definición.

## Acciones que Claude Code debe ejecutar sin pedir permiso

### 1. Al iniciar una sesión de trabajo

Leer en este orden:

1. notes/Biblioteca.md — índice maestro.
2. notes/state/STATE-agencia.md — estado general.
3. Si hay cliente específico en la tarea: notes/state/STATE-[cliente].md + notes/brands/[cliente]/*.
4. Último daily en notes/daily/ — qué se hizo en la sesión previa.

Responder al usuario con un resumen de 3-5 bullets de dónde quedó el trabajo y cuál es el siguiente paso lógico.

### 2. Al cerrar una sesión de trabajo

Crear o actualizar:

1. Daily de hoy en notes/daily/YYYY-MM-DD.md con: tareas completadas, decisiones tomadas, bloqueos, próximos pasos. Si ya existe el archivo, agregar al final (no pisar).
2. STATE relevante (agencia o cliente específico) si cambió algo sustancial.

Es parte del flujo estándar, no requiere que el usuario lo pida explícitamente.

### 3. Al descubrir un concepto nuevo reutilizable

Crear nota atómica en notes/knowledge/YYYY-MM-DD-slug.md con frontmatter, explicación, ejemplo, y wikilinks a conceptos relacionados si ya existen.

### 4. Al escribir un SOP nuevo

Crear en notes/sops/slug.md. Estructura mínima: propósito, cuándo aplica, pasos numerados, ejemplo, excepciones conocidas.

## Reglas duras

- Nunca pisar un archivo sin leerlo primero. Especialmente STATE y brand notes.
- Nunca crear duplicados. Antes de crear una nota, buscar si ya existe usando Grep/Glob sobre notes/. Si existe, actualizar la existente.
- Validar con git diff --stat antes de anunciar cambios. Regla que aplicamos en código, aplica igual acá.
- Nunca hacer push automático ni `git add .`. Los commits se hacen durante la sesión con rutas explícitas (ver **Flujo git — política de rutas explícitas** abajo); el push sale exclusivamente del chat consolidador.

## Flujo git — política de rutas explícitas

- `git add .` está PROHIBIDO. También `git add modules/`. En sesiones multi-frente arrastran worktrees, vault y archivos de otros frentes.
- `git add` va SIEMPRE con rutas explícitas de los archivos tocados. Ejemplo:
  ```bash
  git add app.py notes/daily/2026-07-02.md
  ```
- Commit local en chats de frente; el push sale EXCLUSIVAMENTE del chat consolidador.
- Pre-flight guard obligatorio al inicio de cada sesión de CC:
  ```bash
  pwd / git remote -v / git branch --show-current / git status / git log -1
  ```
- Cada worktree de feature vive en su propia carpeta (C:\proyectos\ppc-manager-{slug}); todos comparten el .venv de C:\proyectos\ppc-manager\.venv.
- Después de `git push`: ir al proyecto de Claude → "Add content from GitHub" → refrescar los archivos modificados (si no, el próximo chat arranca ciego).
- Si algo se rompe: `git diff <archivo>` antes de deshacer; `git checkout <archivo>` para descartar ese archivo puntual (no `git checkout .`).

## Excepciones y casos especiales

- Untitled.md — si Obsidian crea uno, eliminarlo inmediatamente, son basura.
- .env y .gitignore dentro de notes/ — no tocar, son config del vault.
- .obsidian/ — no tocar, es config de Obsidian.
- Archivos fuera de las 14 carpetas definidas en "Estructura de carpetas" — reportar antes de crear nada nuevo en raíz. La raíz de notes/ solo tiene los .md listados en esa sección + archivos de sistema.

## Reglas LTD MX (actualizado 02/06)

- **Heroes LTD oficial**: 35 ASINs activos (actualizado de 10). Fuente única de verdad: `notes/brands/ltd/LTD.md` sección 🦸 **Heroes oficiales (canónico)** al inicio. NO consultar listas viejas en sesiones previas.
- **Brand notes path canónico**: `notes/brands/{slug}/{BRAND}.md` (subcarpeta), nunca flat `notes/brands/{slug}.md`. Bug detectado 02/06: el path flat causó duplicado de marca LTD.

## Reglas operacionales bulk sheets Amazon (actualizado 02/06)

- **Antes de cualquier bulk Negative PT/KW**: validar dtype de Ad Group ID con `.astype("Int64").astype(str)` o cross-check fallará silenciosamente. Ver `notes/knowledge/2026-06-02-gotcha-bulk-export-adgroup-id-float.md`.
- **Amazon "already exists" en CREATE**: no es falla real, es duplicado preexistente, descartar. Ver `notes/knowledge/2026-06-02-amazon-bulk-error-already-exists.md`.
- **CREATE vs UPDATE rollback**: CREATE procesa row-a-row (falla aislada); UPDATE rollback completo si una row falla. Filtrar `State != archived` antes de UPDATE bulks.
- **Filas Entity=Campaign — `Start Date` y `State` vacíos se leen como "0" → upload Failed** (LTD 17/06): poblarlas con el valor REAL aunque no se cambien — `Start Date` como TEXTO `yyyyMMdd`, `State` con el estado actual. Aplica también a updates de budget (son filas Entity=Campaign).
- **Budget Rules: por UI, no por bulk** (LTD 17/06): hacerlas en UI (Add budget rule → Schedule → date range → % increase). La hoja "Budget Rules" del BSE viene vacía y los enums (Budget Rule Type / Recurrence Type / Increase By Type) no son confiables → riesgo Failed. UI = 60 seg, confiable, auto-revert.

## Protocolo de cierre — arranque-{slug}.md (institucionalizado 02/06)

Cada cierre de sesión de marca/cliente o feature genera un arranque `arranque-{slug}.md` (slug = nombre kebab-case: `ltd`, `setex`, `dermaglos`, `m29`, etc.). Ubicación según tipo:
- **Marcas/clientes** → `notes/prompts/sesion/clientes/arranque-{slug}.md`
- **Features/módulos** → `notes/prompts/sesion/features/arranque-{slug}.md`

Ambas carpetas están versionadas por la whitelist `!notes/prompts/**` del `.gitignore` — no hace falta tocar gitignore por marca/feature nueva. NO crear arranques sueltos en la raíz de `notes/`: quedarían gitignoreados en silencio (la regla `notes/*` ignora todo lo no whitelisteado).

**Estructura mínima del arranque:**

```yaml
---
brand: <Nombre completo>
marketplace: <Amazon US/MX/etc>
tipo: arranque-sesion
last_updated: YYYY-MM-DD
last_session: YYYY-MM-DD
status_arranque: <descripción corta>
---
```

Secciones requeridas:
1. **Contexto** — 1-2 frases describiendo dónde quedamos
2. **Leé en este orden** — paths exactos a state, brand note, daily, CLAUDE.md
3. **Prioridades de esta sesión (en orden)** — 3-8 items concretos
4. **Inputs que el chat debe pedirme antes de empezar** — qué datasets/CSVs necesita
5. **Bloqueos pendientes (escalación con AM)** — issues abiertos con cliente
6. **Sesión técnica programada** — si aplica (fix de módulos, syncs con team, etc.)

**Posición en el protocolo de cierre** (después de los pasos existentes):
1. sop-writer daily
2. sop-writer brand note
3. Mega-prompt CC consolidación (STATE + knowledge + modules + CLAUDE.md)
4. **Mega-prompt CC arranque-{slug}.md (NUEVO paso fijo)**
5. git commit principal + push
6. Refresh proyecto Claude

El arranque-{slug}.md puede ir en el mismo commit principal o en uno separado (`docs({slug}): arranque sesión próxima — <fecha o contexto>`). Preferir commit separado si el principal ya quedó grande.

**Beneficios documentados (sesión 02/06):**
- Elimina dependencia de Sticky Notes paralelo
- Versionado = trazabilidad entre sesiones
- Próximo chat lee directamente del repo, no depende de pegar prompt manualmente
- Fuente única de verdad por marca

## Walmart research — notes/walmart/

Folder de research dedicado a Walmart (Marketplace Seller Central + Walmart Connect). Auditorías de plataforma para diseño futuro del módulo `walmart-manager` en Agency OS.

Estado actual:
- Sesión 1 (Seller Central): completa — ver `notes/walmart/seller-central-audit.md`
- Sesión 2 (Walmart Connect): pendiente — ver `notes/walmart/open-questions-walmart-connect.md`
- Sesión 3 (diseño módulo): pendiente — depende de sesión 2

Archivos clave:
- `notes/walmart/seller-central-audit.md` — sitemap, schemas (Account Health + LQS), URL map, plan remediación Pura Vida Moringa
- `notes/walmart/spec-template-herbal-supplements.md` — schema técnico del template de bulk listings WFS, 131 cols
- `notes/walmart/open-questions-walmart-connect.md` — backlog para sesión 2

Cuenta de auditoría: Pura Vida Moringa (US Marketplace, 4 SKUs en WFS Pending Review). Evaluar si convertir el research en auditoría facturable para el cliente.

Diferencia arquitectónica clave vs Amazon: Walmart usa multi-gate (5 gates secuenciales) en lugar de single-score ODR. El módulo Walmart NO debe portar el dashboard agregado de Amazon — debe modelar pipeline de validación secuencial con alerta al gate más temprano en rojo.

Bug-traps conocidos:
- Calendario fiscal Walmart (Q1=Feb-Apr, no Q1=Jan-Mar) — normalizar fechas en comparativas cross-platform.
- OTD desglose accountable vs non-accountable — filtrar antes de calcular.
- LQS Price Competitiveness excluye Walmart-funded incentives — cruzar reportes para PCS limpio.
- Spec template versionado por Walmart — re-snapshot cuando bumpee.