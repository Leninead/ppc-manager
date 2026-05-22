---
tipo: sop
modulo: notebooklm
version: v1.0
fecha: 2026-05-22
autor: Lenin Acosta
audiencia: equipo-capybaras
estado: activo
tags: [sop, notebooklm, google-workspace, ia, knowledge-management, capybaras, 2026, onboarding, sales, training]
---

# 🦫 SOP — NotebookLM para Capybaras Agency

**Versión:** v1.0 — Mayo 2026
**Dev:** Lenin Acosta
**Plataforma:** notebooklm.google.com (Workspace Capybaras)
**Motor:** Gemini 3 (desde abril 2026)
**Plan:** NotebookLM Plus incluido en Workspace Business+

---

## 📌 TL;DR

NotebookLM es **research grounded en tus fuentes** — no busca en la web, solo sintetiza lo que vos subís y cita el origen exacto. Para Capybaras es valioso en 5 frentes operativos:

1. **Onboarding de cliente nuevo** — pasar de 3-4 hs de lectura manual a 30 min de setup
2. **Sales prep para M29** — borrador de pitch + mind map de positioning
3. **Knowledge base interna** — vault Obsidian queryable conversacionalmente
4. **Research competitivo profundo** — landscape estructurado a partir de exports
5. **Training del equipo** — Quiz + Audio Overview + Flashcards de SOPs

**NO reemplaza:** PPC Manager Streamlit, M29 Proposal Studio, ni Claude. Es una capa más en el stack.

---

## ÍNDICE

| # | Sección |
|---|---------|
| 1 | Por qué importa para Capybaras |
| 2 | Setup en Workspace Capybaras |
| 3 | Anatomía: 3 columnas + Studio |
| 4 | Use cases priorizados (5 escenarios) |
| 5 | Workflow operativo semanal |
| 6 | Patrones de prompting que funcionan |
| 7 | Límites duros y reglas de seguridad |
| 8 | Integración con stack Capybaras |
| 9 | Roadmap de adopción 60 días |
| A | Apéndice — Comandos rápidos |
| B | Apéndice — Trampas conocidas |
| C | Apéndice — Plantillas de fuentes por use case |

---

## 1. Por qué importa para Capybaras

### 1.1 El problema que resuelve

Capybaras acumula **conocimiento disperso**: vault Obsidian (`notes/`) con 100+ archivos, Drive con PDFs de contratos y reports, Slack con decisiones operativas, Gmail con negociaciones con clientes, exports de Helium 10/Atom 11/Amazon Ads en carpetas locales. Cuando aparece una pregunta concreta — "¿qué pasó con Bulk 8 de LTD?", "¿cuál fue la última política de pricing de Dermaglos?", "¿qué casos de éxito aplican al prospect de skincare?" — la búsqueda es manual y consume tiempo de director.

NotebookLM convierte ese corpus disperso en una **capa queryable conversacional** con citas verificables.

### 1.2 Diferencial vs otras IAs

| Capacidad | NotebookLM | Claude | Gemini app | ChatGPT |
|-----------|------------|--------|------------|---------|
| Grounded en tus fuentes (no web) | ✅ exclusivo | parcial (con uploads) | parcial | parcial |
| Cita origen exacto | ✅ con link | ✅ | parcial | parcial |
| Hasta 500K palabras por fuente | ✅ | limitado por contexto | limitado | limitado |
| Audio Overview podcast | ✅ | ❌ | ❌ | ❌ |
| Video Overview narrado | ✅ | ❌ | ❌ | ❌ |
| Mind Map interactivo | ✅ | ❌ | ❌ | ❌ |
| Quiz + Flashcards | ✅ | ❌ | ❌ | parcial |
| Política: no entrena con tu data | ✅ declarado | ✅ declarado | parcial | parcial |
| Razonamiento libre / código | ❌ | ✅ | ✅ | ✅ |

**Conclusión:** NotebookLM es el ganador claro cuando el output depende de fuentes específicas que tenés a mano. Claude sigue siendo el motor para arquitectura, código y conversación libre.

### 1.3 Cuándo NO usar NotebookLM

- Generación de código → Claude Code en el repo
- Análisis cuantitativo de bulks PPC → PPC Manager Streamlit
- Conversación creativa sin fuentes → Claude o Gemini
- Output de propuestas customizadas a cliente → M29 Proposal Studio
- Decisiones operativas en tiempo real durante upload de bulks → directo en Campaign Manager

---

## 2. Setup en Workspace Capybaras

### 2.1 Acceso

- **URL:** `notebooklm.google.com`
- **Login:** cuenta corporativa @capybaras
- **Plan:** NotebookLM Plus (incluido en Workspace Business+)
- **Límites del plan Plus:** 100+ notebooks, 50 fuentes por notebook, 500K palabras por fuente, 200MB por archivo

### 2.2 Convención de nombres de notebooks

Misma lógica del vault — kebab-case con slug de cliente o tema:

| Tipo | Patrón de nombre | Ejemplo |
|------|------------------|---------|
| Onboarding cliente | `onboarding-{cliente}-{aaaa-mm}` | `onboarding-ltd-2026-05` |
| Sales prep prospect | `sales-{prospect}-{aaaa-mm}` | `sales-acme-skincare-2026-05` |
| Brand knowledge base | `brand-kb-{cliente}` | `brand-kb-dermaglos` |
| Research competitivo | `comp-research-{cliente}-{categoria}` | `comp-research-ltd-baby-sleep` |
| Training equipo | `training-{tema}-{aaaa}` | `training-bulk-upload-2026` |
| Inteligencia agencia | `intel-{tema}-{q}` | `intel-rufus-ai-q2-2026` |

**Slugs de cliente válidos** (mismos que en `cierre-meta.md`): `dermaglos`, `ltd`, `setex`.

### 2.3 Carpetas en Drive Capybaras

Crear y mantener en Drive Capybaras:

```
/Capybaras/NotebookLM/
  ├── 01-clientes/
  │   ├── ltd/
  │   ├── dermaglos/
  │   └── setex/
  ├── 02-sales-prep/
  │   └── {prospect}/
  ├── 03-knowledge-agencia/
  │   ├── sops/
  │   ├── brand-notes/
  │   └── inteligencia/
  └── 04-training-equipo/
```

**Regla de oro:** Cuando creás un notebook, mantené las fuentes mirroreadas en Drive. Un notebook puede perderse o corromperse; las fuentes en Drive con su propio backup, no.

### 2.4 Roles y permisos sugeridos

| Persona | Rol | Acceso |
|---------|-----|--------|
| Lenin (director) | Owner | edit en todos |
| Edu (AM Dermaglos + Setex) | Editor | edit en `dermaglos/`, `setex/`, view en agencia |
| Agustín (AM LTD ops) | Editor | edit en `ltd/`, view en agencia |
| Adam (LTD Sales Director) | Viewer | view en `ltd/sales-*` |
| Ramiro (técnico) | Editor | edit en agencia, view en clientes |
| Freddy (CEO) | Viewer | view en `02-sales-prep/`, `03-knowledge-agencia/` |

---

## 3. Anatomía: 3 columnas + Studio

### 3.1 Columna izquierda — Fuentes (Sources)

**Tipos soportados (mayo 2026):**
- Google Docs / Slides
- PDFs
- Markdown / texto plano (`.md`, `.txt`)
- URLs web (cualquier página pública)
- YouTube URLs (con transcripción automática)
- Audio files (`.mp3`, `.wav`)
- EPUB
- Texto pegado directo

**Reglas operativas:**
- Hasta 50 fuentes por notebook (Plus)
- Cada fuente puede tener hasta 500K palabras o 200MB
- Si una fuente excede el límite → splittearla en partes
- Las fuentes NO se actualizan automáticamente — hay que hacer refresh manual cuando cambia el doc original

### 3.2 Columna central — Chat

- Cada respuesta cita la fuente con número clickeable
- Si la respuesta no está en las fuentes, NotebookLM lo declara explícitamente ("No encuentro información sobre eso en las fuentes")
- La conversación se guarda y persiste por notebook
- Soporta artefactos (gráficos, tablas) directamente en chat

### 3.3 Columna derecha — Studio

Genera múltiples outputs por tipo (cambio importante desde enero 2026: ya no es "uno por notebook"). Podés tener 3 Audio Overviews en distintos idiomas, 2 Mind Maps con foco diferente, etc., en el mismo notebook.

**Outputs disponibles y cuándo usarlos en Capybaras:**

| Output | Mejor caso de uso en agencia |
|--------|------------------------------|
| **Audio Overview** | Training del equipo en el commute, briefing pre-call |
| **Video Overview** (Brief / Explainer / Cinematic) | Demo interno, training visual, onboarding de gente nueva |
| **Mind Map** | Diagnóstico inicial de catálogo o landscape competitivo |
| **Slide Deck** | Borrador de pitch — después pasa a M29 |
| **Infographic** | Reporte ejecutivo visual para el cliente |
| **Data Table** | Extracción estructurada de PDFs (reports, contratos) |
| **Flashcards** | Training de certificaciones Amazon, repaso de SOPs |
| **Quiz** | Validar comprensión del equipo en SOPs nuevos |
| **Briefing Doc** | Handoff para AM, resumen pre-call con cliente |

**Modo interactivo Audio Overview:** Mientras escuchás el podcast, podés tocar "Join" y hacerle preguntas a los hosts AI en vivo. Útil para training: dejás al AM nuevo escuchando el Audio Overview del onboarding del cliente y que pregunte dudas en tiempo real.

---

## 4. Use cases priorizados Capybaras

### 4.1 [PRIORIDAD 1] Onboarding de cliente nuevo

**Problema actual.** Cuando entra un cliente, el director (Lenin) pasa 3-4 horas leyendo: PDF del contrato, listing inicial, últimos reports, emails de negociación, brand book si tiene. Luego el AM (Edu, Agustín) tarda otras 2-3 horas en agarrar la cuenta porque el conocimiento sigue disperso en Drive + Slack + email.

**Solución con NotebookLM.**

1. Crear notebook `onboarding-{cliente}-{aaaa-mm}` (ejemplo: `onboarding-ltd-2026-05`)
2. Subir como fuentes:
   - PDF del contrato (con redacción de cláusulas confidenciales si va a compartir afuera del owner)
   - Listing actual exportado desde Helium 10 o como PDF del listing live
   - Últimos 3 Business Reports
   - Últimos 3 SQPs
   - STR de 90 días
   - Bulk export del Campaign Manager
   - Brand note del vault (`notes/brands/{cliente}/*.md`)
   - Hilo de email relevante exportado como PDF
3. Generar:
   - **Audio Overview** de 15-20 min — para escuchar en el commute
   - **Mind Map** — overview visual del estado de cuenta
   - **Briefing Doc** — handoff document para el AM (1000-1500 palabras)
4. Compartir notebook con el AM responsable
5. AM hace queries específicas mientras se familiariza:
   - "¿Cuál es el top 5 ASIN por revenue del último trimestre?"
   - "¿Qué bid rules tiene activas en Atom 11?"
   - "¿Cuáles son las negativas más relevantes del último STR?"
   - "¿Qué deuda técnica del listing quedó documentada?"

**Tiempo estimado:** 30 min de setup + 20 min escuchando Audio + 30 min de queries = ~1.5 hs vs 6-7 hs del flujo manual.

**Owner del notebook:** Lenin. AM como editor. Cliente NO accede.

---

### 4.2 [PRIORIDAD 1] Sales prep para M29 Proposal Studio

**Problema actual.** Cuando llega un prospect, hay que cruzar info de Capybaras (Why, casos, capabilities) con info del prospect (listing audit, categoría, competencia) para armar la propuesta. Hoy esto pasa abriendo 8 tabs distintos.

**Solución con NotebookLM.**

1. Crear notebook `sales-{prospect}-{aaaa-mm}` (ejemplo: `sales-acme-skincare-2026-05`)
2. Subir fuentes (mix Capybaras + prospect):
   - **Capybaras**: catálogo M29 (`data/sales/_catalog.json` exportado a PDF), Why Capybaras v3, casos relevantes (Tattoo Care, Wamery, Shapermint, AimZone Games, Challenge Me, Dermaglos), Master Deck si existe
   - **Prospect**: listing exportado (Helium 10), reviews exportadas, top 5 competidores en su categoría (Cerebro / Reverse ASIN), screenshots del A+ y video presence
3. Generar:
   - **Slide Deck draft** — borrador de pitch que después se pulea en M29 Proposal Studio
   - **Mind Map** — positioning del prospect vs competencia
   - **Audio Overview** — para que Lenin/Freddy revisen el contexto antes de la call
4. Queries útiles:
   - "¿Qué pilar de Why Capybaras resuena más con los gaps del prospect?"
   - "¿Qué caso de éxito del catálogo es más análogo a su categoría y por qué?"
   - "¿Cuáles son las 3 brechas críticas del listing del prospect vs el top 1 competidor?"
   - "¿Qué módulos del M29 catalog deberían entrar en esta propuesta?"

**Output esperado:** materia prima de la propuesta. El render final sigue siendo M29 → HTML + PDF.

**Importante:** En este notebook va info comercial sensible. NUNCA compartir con el prospect — es herramienta interna de prep.

---

### 4.3 [PRIORIDAD 2] Knowledge base interna de agencia

**Problema actual.** Cuando hace falta una decisión rápida ("¿qué pasó cuando subimos Bulk 8 con archived campaigns?", "¿cuál fue el threshold de Bid Optimizer para Dermaglos?", "¿quién es el contacto de compliance en LTD?"), hay que buscar en daily notes + STATE files + prompts library. El vault está en Obsidian — no es queryable conversacionalmente desde fuera.

**Solución con NotebookLM.**

1. Crear notebook `intel-agencia-q{n}-{aaaa}` (ejemplo: `intel-agencia-q2-2026`)
2. Subir como fuentes:
   - Todo el contenido de `notes/sops/` (zippearlo y subir como folder en Drive, después linkear)
   - `notes/Biblioteca.md`
   - `notes/state/STATE-agencia.md`
   - `INTELLIGENCE-INDEX.md`
   - Las últimas 50 daily notes (priorizar daily de incidentes y decisiones, no las de checkpoint rutinario)
   - `CLAUDE.md` del repo
   - Notas de inteligencia relevantes de `notes/knowledge/`
3. Refresh trimestral con últimas adiciones
4. Queries:
   - "¿Qué reglas tenemos sobre Bulk Sheet Export con archived campaigns?"
   - "¿Cuál es el threshold de bid de Bid Optimizer para skincare LATAM?"
   - "¿Qué decisiones tomamos en 2026 sobre Atom 11 vs Perpetua?"
   - "¿Cuál es el flujo aprobado para subir Bulk 4 si el primer intento falla?"

**Beneficio:** Onboarding de Ramiro, futuros AMs o devs se acelera 10x. También sirve a Lenin para no perder tiempo buscando decisiones viejas.

**Refresh sugerido:** mensual los primeros 90 días, trimestral después de validar adopción.

---

### 4.4 [PRIORIDAD 2] Research competitivo profundo

**Problema actual.** El research competitivo es manual y disperso. Helium 10 da data pero no conclusiones estructuradas. Hoy esto se hace en spreadsheets ad-hoc que se pierden.

**Solución con NotebookLM.**

1. Crear notebook `comp-research-{cliente}-{categoria}` (ejemplo: `comp-research-ltd-baby-sleep`)
2. Subir fuentes:
   - Exports de Helium 10: Xray del cliente, Cerebro de las top 20 KW, Reverse ASIN de top 5 competidores
   - Screenshots del listing de cada competidor (PDF combinado)
   - Reviews scraped de los top 5 (export Helium 10 o Jungle Scout)
   - SQP del cliente
3. Generar:
   - **Mind Map** — landscape competitivo (eje X: precio, eje Y: rating; clusters por positioning)
   - **Data Table** — comparativa estructurada: ASIN | Brand | Precio | Rating | # Reviews | Tipo de A+ | Tiene video | KW principal
   - **Briefing Doc** — recomendaciones de gap a llenar (3-5 prioritarias)
4. Queries:
   - "¿Qué bullet del competidor #1 NO aparece en nuestro listing?"
   - "¿Qué patrón de review negativo se repite en los top 3 competidores que podemos explotar?"
   - "¿Hay un slot de precio sin cubrir en la categoría?"

**Output destino:** alimenta el SOP de Listing Optimization (Fase 1 — Research) y el plan de Campaign Builder.

---

### 4.5 [PRIORIDAD 3] Training del equipo

**Problema actual.** Cuando hay un SOP nuevo o se actualiza uno existente, el equipo lo lee y la mitad se olvida en 2 semanas. No hay forma de validar comprensión sin tomar tiempo de director.

**Solución con NotebookLM.**

1. Crear notebook `training-{tema}-{aaaa}` (ejemplo: `training-bulk-upload-2026`)
2. Subir fuentes: el SOP relevante + 2-3 daily notes con incidentes reales que ilustren la regla
3. Generar:
   - **Quiz** — 10 preguntas con opciones múltiples para validar comprensión
   - **Flashcards** — repaso rápido (formato: concepto → definición)
   - **Audio Overview** — versión podcast de 15 min para el commute
4. Flujo de adopción:
   - Lenin comparte el notebook con el AM responsable
   - AM hace el Quiz, screenshots del resultado al canal de equipo
   - Si pasa con 8/10 o más → certificado en ese SOP
   - Si no → lectura adicional + retry en 7 días

**Use cases iniciales sugeridos:**
- Training Bulk Upload Amazon Ads (reglas críticas)
- Training Listing Optimization (Fases 1-3)
- Training Atom 11 Rules Builder
- Training proceso de cierre semanal (LTD → Dermaglos → Setex → Viernes consolidación)

---

## 5. Workflow operativo semanal

### Lunes — Setup semanal
- Review notebooks activos en `/01-clientes/`
- Refresh fuentes si hay reports nuevos del fin de semana (SQP semanal de Brand Analytics)
- Crear notebooks nuevos si entró cliente o prospect durante el weekend

### Martes a jueves — Use cases ad-hoc
- Onboarding: crear notebook el mismo día que el cliente firma
- Sales prep: crear notebook cuando se agenda la call (mínimo 48 hs antes)
- Knowledge base: query libre cuando aparece la duda

### Viernes — Cierre + archive
- Notebooks de prospects no cerrados → mover a archive folder
- Notebooks de clientes activos → refresh con data semanal y check de fuentes obsoletas
- Update mensual de `intel-agencia-q{n}` con últimas decisiones del mes

### Cuándo NO crear un notebook
- Queries one-off de 1 fuente → mejor usar Claude / Gemini directo
- Conversaciones que necesitan creatividad libre → NotebookLM es muy "literal", restringido a fuentes
- Análisis numérico crudo de bulks PPC → PPC Manager Streamlit
- Decisiones que no requieren rastreo de fuente → ChatGPT/Claude más rápidos

---

## 6. Patrones de prompting que funcionan

NotebookLM corre Gemini 3 (mayo 2026), pero está grounded en fuentes. El estilo de prompt cambia respecto a Claude/ChatGPT — hay que ser más directivo sobre QUÉ fuentes usar y cómo estructurar la salida.

### 6.1 Forzar citas explícitas

> "Listame los 3 hallazgos principales del último SQP, citando la fuente exacta de cada uno con número de página o sección."

### 6.2 Comparar fuentes entre sí

> "¿Hay contradicciones entre el STR de mayo y el SQP de mayo en cuanto a la query top performer? Mostrá ambas posturas con citas."

### 6.3 Síntesis estructurada en tabla

> "Armá una tabla con columnas: ASIN | Revenue | ACoS | Bid Rule activa | Recomendación. Solo usá data del Business Report y del export de Atom 11 que subí."

### 6.4 Quiz para validar

> "Hacé un quiz de 10 preguntas sobre las reglas de bulk upload del SOP que subí. Cada pregunta con 4 opciones (A/B/C/D), marcando la correcta al final y citando la sección del SOP donde está la justificación."

### 6.5 Salida para otro pipeline

> "Generá un briefing doc de 800 palabras para que un AM nuevo entienda el estado de la cuenta LTD. Incluí: stock crítico, campañas archived, decisiones del último mes, contactos clave. Estructura: 1) Contexto, 2) Estado actual, 3) Riesgos, 4) Próximos pasos."

### 6.6 Detectar lo que NO está

> "¿Qué temas críticos para gestionar una cuenta de Amazon Ads NO están cubiertos en las fuentes que subí? Listalos como gaps de documentación."

### 6.7 Pre-call con cliente

> "Soy el AM de Dermaglos y tengo call con Edu el viernes para revisar performance. Generá una lista de 10 preguntas que probablemente me haga, con respuestas basadas en los reports que subí."

### 6.8 Anti-patrones — qué NO hacer

- ❌ Preguntas abiertas sin direccionamiento ("¿qué pensás del listing?") — devuelve respuestas tibias
- ❌ Pedir creatividad pura ("inventame un eslogan") — NotebookLM se restringe a las fuentes
- ❌ Cálculos numéricos complejos ("calculá ROAS proyectado a 90 días con estos supuestos") — exportá la tabla y procesá en Pandas
- ❌ Pedirle que busque en internet ("buscá información sobre la categoría") — no tiene web access activo

---

## 7. Límites duros y reglas de seguridad

### 7.1 ⚠️ NUNCA subir a un notebook compartido externamente

- Bulk files con Customer IDs visibles del cliente
- PDFs de contratos sin redactar precios o cláusulas confidenciales
- Emails con info de márgenes Capybaras o pricing strategy interna
- Cualquier archivo con credenciales (API keys, login MFA, etc.)
- Información de proyectos personales o no relacionados con el cliente

**Regla operativa:** Antes de compartir un notebook fuera del owner, hacer un audit de fuentes. Si alguna tiene info confidencial → moverla a notebook separado solo-owner.

### 7.2 Privacy declarada por Google (verificar trimestralmente)

Google declara que NotebookLM **no entrena sus modelos con tu data**. Los términos pueden cambiar — verificar en `notebooklm.google.com` la política vigente cada trimestre y dejar registro en `notes/state/STATE-agencia.md`.

### 7.3 Límites técnicos vigentes (mayo 2026)

- 50 fuentes por notebook (Plus)
- 500K palabras por fuente
- 200MB por archivo
- Si una fuente excede → splittear en partes con sufijo `_parte1`, `_parte2`
- Los Studio outputs (Audio, Video, Mind Map) tardan entre 30 segundos y 5 minutos en generarse según complejidad

### 7.4 NotebookLM NO es sistema de record

- NotebookLM es **inferencia + síntesis** de tus fuentes
- El sistema de record sigue siendo el vault Obsidian (`notes/`) + Drive
- Una decisión documentada debe ir al vault como daily note o STATE update — no quedar solo en chat de NotebookLM
- Los chats no se exportan limpio — si una conversación tiene valor, copiar manualmente lo relevante al vault

### 7.5 Cliente acceso — regla por defecto

Por defecto **el cliente NO accede a notebooks de Capybaras**. Excepciones requieren aprobación de Lenin + Freddy, y solo se comparten notebooks ad-hoc creados con fuentes específicamente preparadas para ese share (sin info interna, sin emails internos, sin pricing).

---

## 8. Integración con stack Capybaras

### 8.1 Con PPC Manager (Streamlit en `C:\proyectos\ppc-manager`)

- PPC Manager genera bulks, reports, audits → **exportar PDF** → cargar a NotebookLM para narrativa
- NotebookLM **NO reemplaza** al PPC Manager — el Streamlit hace el análisis cuantitativo, NotebookLM aporta la capa de síntesis narrativa
- **Patrón ganador:** después de un audit M16, exportar PDF + cargar a notebook del cliente + generar Briefing Doc para handoff a AM

### 8.2 Con vault Obsidian (`notes/`)

- El vault es la **fuente de verdad estructurada** — sigue siendo el sistema de record
- NotebookLM es la **capa queryable conversacional**
- **Flujo recomendado:**
  1. Decisión / hallazgo → daily note en Obsidian
  2. Daily note → sincronizada a Drive (manual o vía script)
  3. Drive → fuente refrescable en NotebookLM `intel-agencia-q{n}`
  4. Refresh mensual del notebook

### 8.3 Con Claude (chat) y Claude Code

- **Claude (chat):** arquitectura, código, análisis estratégico abierto, planning
- **Claude Code:** ejecución técnica en el repo
- **NotebookLM:** research grounded en fuentes específicas, síntesis multimedia
- **Patrón ganador:** usar NotebookLM para extraer hallazgos (Mind Map + Briefing Doc) → llevar el output a Claude para diseñar la acción concreta (prompt para CC, bulk a generar, decisión arquitectural)

### 8.4 Con M29 Proposal Studio

- Slide Deck de NotebookLM = **borrador inicial / materia prima**
- Pasa a M29 → editor estructurado de propuesta → render HTML/PDF final con branding Capybaras
- NotebookLM NO reemplaza M29; aporta el primer draft que se pulea en el editor

### 8.5 Con Atom 11

- Cuando Neha pasa cambios de rules de Atom 11 → cargar el export a `brand-kb-{cliente}` como fuente
- Útil para queries históricas: "¿desde cuándo está activa la regla X y cuándo se modificó?"

---

## 9. Roadmap de adopción 60 días

### Días 1-7 — Pilot personal (solo Lenin)

- Crear notebook `intel-agencia-q2-2026` con vault completo
- Hacer 20 queries reales y medir tiempo ahorrado vs búsqueda manual
- Documentar 5 prompts ganadores en `notes/prompts/notebooklm/`
- Decisión Go/No-Go preliminar al día 7

### Días 8-21 — Onboarding 1 cliente real

- Crear notebook de LTD con onboarding completo (4.1)
- Compartir con Agustín (AM) y Adam (Sales Director)
- Pedir feedback estructurado:
  - ¿Qué consultas hicieron?
  - ¿Cuáles funcionaron, cuáles no?
  - ¿Qué fuente faltaba?
  - ¿El Audio Overview fue útil?
- Iterar plantilla de fuentes obligatorias en Apéndice C

### Días 22-42 — Sales prep en producción

- Próximo prospect que entre → crear notebook (4.2)
- Comparar tiempo de prep vs proceso anterior
- Si la propuesta se cierra → comparar quality del pitch vs propuestas previas
- Documentar caso en daily note

### Días 43-60 — Training del equipo

- Generar Audio + Quiz para el SOP de Bulk Upload (4.5)
- Compartir con Edu y Agustín
- Medir comprensión post-quiz
- Si funciona → expandir a SOPs de Listing Optimization y Atom 11

### Día 60 — Decisión Go/No-Go formal

- Si ROI claro (>2 hs ahorradas por semana sostenido) → integrar como capa permanente del workflow + asignar tiempo de mantenimiento (1 hr/semana)
- Si ROI parcial → mantener solo para Onboarding (caso de uso más fuerte)
- Si no hay ROI → archivar como experimento documentado y no expandir

---

## A. Apéndice — Comandos rápidos

| Acción | Cómo |
|--------|------|
| Crear notebook | `notebooklm.google.com` → "Crear cuaderno" |
| Subir múltiples fuentes | Drag & drop en panel izquierdo, o botón "Añadir fuentes" |
| Sincronizar carpeta de Drive | Botón "Drive" en uploader → seleccionar carpeta/archivos |
| Compartir notebook | Botón "Compartir" (esquina superior derecha) |
| Cambiar idioma de output | Configuración → "Output language" → seleccionar |
| Modo interactivo Audio | Reproducir Audio Overview → botón "Join" |
| Refrescar fuente actualizada | Click en fuente → ⋮ → "Refresh" |
| Exportar Slide Deck | Studio → Slide Deck → ⋮ → "Export to PPTX" |
| Eliminar conversación | Chat → menú superior → "Clear conversation" |

---

## B. Apéndice — Trampas conocidas

1. **NotebookLM no actualiza fuentes automáticamente.** Si modificás un Google Doc fuera del notebook, hay que dar clic en refresh manualmente en la fuente. Si no, el chat sigue usando la versión vieja.

2. **No hace cálculos confiables sobre números grandes.** Para análisis cuantitativo, exportar la tabla y procesar en Pandas o Excel. NotebookLM puede equivocarse en sumas/promedios con > 100 filas.

3. **Las URLs web se congelan al snapshot del momento de carga.** Si subís una URL y la página cambia, el notebook tiene la versión vieja. Para páginas que cambian seguido, mejor exportar como PDF y recargar.

4. **YouTube — la transcripción depende del video.** Videos con buenos captions oficiales = mejor; con captions auto-generados = ruido. Si el contenido es crítico, transcribir manualmente.

5. **EPUB > PDF cuando podés elegir.** Para libros / docs largos, EPUB indexa mejor que PDF escaneado.

6. **Cuidado con archivos OCR pobre.** Si el PDF es un scan con OCR malo, NotebookLM va a alucinar respuestas. Verificar siempre que el texto sea seleccionable antes de subir.

7. **El chat tiene límite diario.** En Plus el límite es alto pero existe — si vas a hacer training intensivo, distribuirlo en varios días.

8. **Los Studio outputs antiguos no se regeneran solos si cambia la fuente.** Hay que generar nuevos manualmente. Importante para reports que cambian semanalmente.

9. **NO hay versionado nativo.** Si modificás un Briefing Doc, la versión anterior se pierde. Si necesitás versionado, exportar a Drive con sufijo `_v1`, `_v2`.

10. **El Slide Deck export a PPTX pierde algo de formato.** Esperar pulir el formato final en PowerPoint o en M29 Proposal Studio.

---

## C. Apéndice — Plantillas de fuentes por use case

### C.1 Onboarding cliente — fuentes obligatorias

- [ ] PDF del contrato
- [ ] Listing actual (PDF o export Helium 10)
- [ ] Business Reports últimos 3 meses
- [ ] SQPs últimas 4 semanas
- [ ] STR últimos 90 días
- [ ] Bulk export Campaign Manager
- [ ] Brand note del vault (`notes/brands/{cliente}/`)
- [ ] Hilo email negociación (PDF)
- [ ] Inventory Report actual
- [ ] Atom 11 rules export (si aplica)

### C.2 Sales prep prospect — fuentes obligatorias

- [ ] Catálogo M29 export
- [ ] Why Capybaras v3 (PDF)
- [ ] 3-5 casos de éxito relevantes del catálogo
- [ ] Master Deck Capybaras (si existe)
- [ ] Listing prospect exportado
- [ ] Reviews prospect (export)
- [ ] Top 5 competidores — Cerebro + Reverse ASIN
- [ ] SQP de la categoría (si Brand Analytics disponible)
- [ ] Screenshots A+ y video del prospect

### C.3 Knowledge base agencia — fuentes obligatorias

- [ ] `notes/sops/` completo (zip)
- [ ] `notes/Biblioteca.md`
- [ ] `notes/state/STATE-agencia.md`
- [ ] `INTELLIGENCE-INDEX.md`
- [ ] Daily notes con incidentes (últimas 50)
- [ ] `CLAUDE.md` del repo
- [ ] Notas críticas de `notes/knowledge/`

### C.4 Research competitivo — fuentes obligatorias

- [ ] Helium 10 Xray del cliente
- [ ] Cerebro de top 20 KW
- [ ] Reverse ASIN de top 5 competidores
- [ ] Screenshots listings competidores (PDF combinado)
- [ ] Reviews scraped top 5 (export)
- [ ] SQP del cliente
- [ ] BSR histórico (si disponible)

### C.5 Training equipo — fuentes obligatorias

- [ ] SOP relevante (markdown del vault)
- [ ] 2-3 daily notes con incidentes reales que ilustren la regla
- [ ] Versión anterior del SOP (si hubo cambio significativo) — para contraste

---

## 📚 Fuentes consultadas para este SOP

- Google Workspace Updates blog (workspaceupdates.googleblog.com) — actualizaciones marzo 2026
- Google Blog (blog.google) — Video Overviews + Studio upgrades enero 2026
- Workspace Google (workspace.google.com/products/notebooklm) — feature list mayo 2026
- DigitalOcean — guía 2026
- KDnuggets — NotebookLM for Creative Architect abril 2026
- Medium — guía completa octubre 2025

---

## 🏷️ Tags

`#sop` `#notebooklm` `#google-workspace` `#ia` `#knowledge-management` `#capybaras` `#2026` `#onboarding` `#sales` `#training` `#m29` `#agency-os`

---

**Próximo review:** 2026-08-22 (90 días desde creación) — validar features vigentes, ROI medido, ajustes de roadmap.
