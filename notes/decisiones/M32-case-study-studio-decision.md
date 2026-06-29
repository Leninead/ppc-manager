# M32 · Case Study Studio — Decisión arquitectónica + Plan de build

**Frente:** ANÁLISIS (discovery + decisión, SIN worktree)
**Fecha:** discovery cerrado
**Estado:** decisión tomada · gate Ramiro **CERRADO** 25/06 · Fase 0 (andamiaje) commiteada (f097aaf, worktree `feat/m32-case-study`) · Fase 1+ pendiente
**Autor:** Lenin Acosta — Capybaras Agency

---

## 0. Gate previo (BLOQUEANTE — leer primero)

> **CONFIRMADO 25/06:** Ramiro pidió la herramienta generadora (no solo el bloque de
> inserción en propuestas). Cita textual: "que puedan generar casos sin redactarlo, responden
> preguntas y se genera". El gate de Ramiro queda **CERRADO** — se construye la herramienta
> generadora completa.

Este `.md` es además el **artefacto para presentarle a Ramiro** y cerrar la ambigüedad.

---

## 1. Decisión

**Opción elegida: 3 — Híbrido.**
Módulo propio **M32 Case Study Studio** (Sales Director, hermano de M29) **+ importer**
que inyecta el caso como bloque **V7_case_study** dentro de una propuesta de M29.

### Por qué (no las otras dos)
- **No opción 1 (solo bloque en M29):** el export WordPress self-contained solo tiene sentido
  si el caso vive *fuera* de la propuesta (publicación en sitio, reutilización). Un bloque
  embebido no necesitaría ese feature. El export WP es la señal dura de "vida propia".
- **No opción 2 (módulo separado puro):** dejaría sin resolver el pedido futuro previsible
  ("meté el caso X en la propuesta del cliente Y"). El puente cuesta poco extra sobre el módulo.
- **Sí opción 3 (híbrido):** el shape JSON mapea casi 1:1 contra el patrón de bloques import-only
  ya existente en M29 (V3-V6). El importer es **un mapper más**, no arquitectura nueva.

---

## 2. Decisiones de diseño cerradas

| Punto | Decisión | Justificación |
|---|---|---|
| Numeración | **M32**, módulo propio | Vida propia + export WP lo separan de M29 |
| Sección | **Sales Director** (no Account Health) | M29 es Sales Director; AH es solo M27/M28/M30 |
| Persistencia | **SÍ** — biblioteca de casos reutilizables | El importer a M29 exige que el caso persista y se referencie |
| Backend persistencia | **Reusa `core/persistence.py`** (capa client-config) | `save/load/list_client_config` ya cubren el caso de uso; cero backend nuevo |
| Export WordPress | **SÍ en v1**, dentro de M32 | Es el feature que justificó el módulo separado |
| Bloque en M29 | **V7_case_study, readonly import-only** | Consistencia con V3-V6 + preserva la regla dura de métricas |

### 2.1 Por qué el bloque V7 es readonly import-only (no editable)
El valor central del Case Study Studio es que **Claude no inventa números** (regla dura:
`metrics` vacío si las notas no traen cifras). Si el bloque fuera editable dentro de la
propuesta, esa garantía se rompe en el punto exacto donde más importa — frente al cliente.
Un caso es un artefacto con integridad propia, como una auditoría B7: se importa, no se edita.
Retoques cosméticos → se hacen en M32 y se reimporta (una sola verdad). Ajustes de "no entra
en la página" → se resuelven en render/CSS del bloque, no editando contenido (mismo criterio
que V3-V6).

---

## 3. Shape JSON (fuente: HTML standalone, líneas 415-421)

```json
{
  "headline": "results-forward title, max ~9 words",
  "subhead": "one sentence positioning line",
  "metrics": [{"value": "2%", "label": "short metric label"}],
  "challenge": "paragraph (40-90 words)",
  "approach": "paragraph (40-90 words)",
  "approach_steps": [{"title": "3-5 word bold lead", "text": "one sentence move + payoff"}],
  "results": "paragraph (40-90 words)"
}
```

Reglas duras heredadas del HTML (preservar tal cual):
- **Métricas:** 0-4 items, SOLO números que aparecen en las notas. Sin cifras → array vacío,
  results queda cualitativo. NUNCA fabricar.
- **Anonimización:** toggle marca OFF → referir al cliente por categoría, nunca inventar nombre.
- **Voz:** Approach en primera persona plural ("we", "our team").
- **Doble llamada Claude:** escribe EN → localiza ES (ambos se guardan juntos).

---

## 4. Mapeo shape M32 → bloque V7_case_study (M29)

Patrón de referencia: V3-V6 son readonly, alimentados por mapper desde fuente externa
(`modules/sales/mappers/datadive_to_v3.py`, `modules/sales/b7_importer.py`).

| Campo M32 (shape HTML) | V7 block.data | Notas |
|---|---|---|
| `headline` | `headline` | — |
| `subhead` | `subhead` | — |
| `metrics[]` (0-4 `{value,label}`) | `metrics[]` | band numérica; regla dura preservada |
| `challenge` | `challenge` | párrafo |
| `approach` | `approach` | párrafo |
| `approach_steps[]` | `steps[]` | opcional, 0-4 |
| `results` | `results` | párrafo |
| `meta.mention_brand` | flag anonimización | controla render del nombre |

`module_id = "V7_case_study"` · render `_render_v7_case_study_readonly(block, proposal, lang)`
· dispatch en `_render_block_editor` (proposal_studio.py L1152) · `lang` ya existe → EN/ES directo.

---

## 5. Persistencia — tabla `cs_case_studies`

Reusa el patrón `ah_client_configs` (PK compuesta + `data` jsonb, sin versión, sin serie temporal).
**No requiere backend nuevo:** M32 llama `_save_client_config` / `_load_client_config` /
`_list_clientes` con `area="sales-director"`, `modulo="case-study"`.

> **[VERIFICAR EN PORTING]** Confirmar que la capa client-config de `core/persistence.py`
> rutea bien con `area="sales-director"` (hasta hoy solo se usó con `area="account-health"`).
> El código es agnóstico al valor de `area`, pero validar en el chat de porting.

```sql
-- Ejecutar UNA vez en capybaras-os-prod ANTES del swap. Este código NO crea tablas.
create table if not exists cs_case_studies (
    area      text  not null,           -- 'sales-director'
    cliente   text  not null,           -- slug del cliente del caso
    modulo    text  not null,           -- 'case-study'
    name      text  not null,           -- slug del caso (ej. 'dermaglos-prime-day-2026')
    data      jsonb not null,           -- shape completo: {en:{...}, es:{...}, meta:{...}}
    primary key (area, cliente, modulo, name)
);
alter table cs_case_studies disable row level security;
```

> **[STANDING STEP — Supabase DDL]** El `disable row level security` por DDL NO es confiable.
> Verificar SIEMPRE post-create:
> ```sql
> select relname, relrowsecurity from pg_class where relname = 'cs_case_studies';
> ```
> `relrowsecurity` debe ser `false`. (401 en POST = error de RLS, no de auth.)

Estructura del `data` jsonb:
```json
{
  "en": { "...shape completo en inglés..." },
  "es": { "...shape completo en español..." },
  "meta": {
    "brand": "...",
    "mention_brand": true,
    "marketplace": "US",
    "images": [{"src": "...", "caption": "..."}]
  }
}
```

---

## 6. Navegación — dónde entra M32

Bajo el expander existente `📋 SALES DIRECTOR` (app.py L272), hermano de Proposal Studio:

```python
# app.py ~L48 — import
from modules.pages.case_study_studio import render as render_case_study_studio

# app.py ~L273 — dentro del expander SALES DIRECTOR
st.button("📊 Case Study Studio", use_container_width=True, on_click=_nav,
          args=("📊 Case Study Studio",), key="nav_📊 Case Study Studio")

# app.py ~L400 — router
if selected == "📊 Case Study Studio":
    render_case_study_studio()
```

---

## 7. Plan de build (para el chat de porting con worktree)

> Cada fase = un commit local en el worktree. Push solo desde el consolidador.
> Pre-flight guard antes de cada prompt a CC. Nunca `git add .` — paths explícitos.

**Worktree:** `C:\proyectos\ppc-manager-case-study` · branch `feat/m32-case-study`

### Fase 0 — Andamiaje del módulo
- `modules/pages/case_study_studio.py` con `render()` mínimo (título + SOP expander).
- Registrar en `app.py` (import + botón + router) — los 3 hooks de la sección 6.
- Smoke: la app levanta, el botón navega, render no rompe.

### Fase 1 — Form de input + doble llamada Claude
- Inputs: marca (+toggle mención), marketplace, 3 textos (problema/proceso/resultado),
  imágenes opcionales con epígrafe.
- `buildPrompt()` (EN, 3 actos, voz "we", regla dura métricas) → `buildTranslate()` (ES).
- Llamada Claude API (la integración ya existe en el stack).
- Parse robusto del JSON (strip de fences, try/except).
- **Validación manual previa:** correr 3-5 casos reales en chat antes de codear el prompt,
  confirmar que la regla dura de métricas se respeta. (Principio: validar antes de automatizar.)

### Fase 2 — Persistencia (biblioteca de casos)
- Crear tabla `cs_case_studies` en Supabase + verificar RLS (sección 5).
- Wire `_save_client_config` / `_load_client_config` / `_list_clientes` con
  `area="sales-director"`, `modulo="case-study"`.
- UI: guardar caso, listar casos guardados, recargar uno.

### Fase 3 — Exports
- PDF (xhtml2pdf, consistente con M29 — NO html2canvas+jsPDF del HTML original).
  Revisar quirks conocidos: `<td>` wrapper para fondos, `align="right"` HTML attr, px no em.
- Copy texto plano (port directo de la lógica del HTML, L556-561).
- Bloque HTML self-contained WordPress (`.capybaras-cs` + WP_CSS inline, L620+).

### Fase 4 — Importer a M29 (el puente híbrido)
- `modules/sales/mappers/case_study_to_v7.py` — mapea shape M32 → V7 block.data (sección 4).
- Render `_render_v7_case_study_readonly(block, proposal, lang)` en proposal_studio.py.
- Sumar `module_id == "V7_case_study"` al dispatch de `_render_block_editor` (L1152).
- UI en M29: importar caso desde la biblioteca M32 (selector por cliente/nombre).

### Fase 5 — SOP + cierre
- `_SOP_MD` en M32 (constante + `st.expander("📘 Cómo usar este módulo")`).
- Actualizar SOP de M29: V7 es import-only (consistente con V3-V6).
- Actualizar `CLAUDE.md` (arquitectura + roadmap).
- Tests: persistencia (con transport fake en memoria, sin red), mapper, parse JSON.

### Flujo del video (referencia de implementación para Fase 1+)
- **Toggle "ask the director":** permite activar/desactivar una etapa donde el generador hace
  preguntas al usuario antes de redactar el caso.
- **Initial scenario:** el usuario describe el escenario inicial del caso (cliente, problema,
  contexto) como punto de partida del generador.
- **Few-shot de casos de otras agencias como referencia:** DECISIÓN DE DISEÑO 25/06 → modelo
  **HÍBRIDO**. Los ejemplos few-shot son **CARGABLES** (archivos que sube Lenin, leídos desde
  un directorio dedicado), con un **FALLBACK** de 1-2 ejemplos hardcodeados mínimos para que el
  módulo funcione desde el primer commit aunque no haya archivos cargados. El directorio de
  ejemplos cargables va **GITIGNOREADO** (mismo patrón que los CSV de clientes reales: material
  sensible de otras agencias, no versionar). Pendiente de implementación en Fase 1+, NO se
  construye hoy (M32 sigue en Fase 0).

---

## 8. Riesgos / notas

- **[PENDIENTE RAMIRO]** Gate de la sección 0 — bloquea todo.
- **[VERIFICAR]** `area="sales-director"` en la capa client-config (sección 5).
- **Reutilización de imágenes:** el HTML original las maneja como base64 inline. Definir en
  porting si se persisten en el jsonb (pesado) o se referencian por URL (requiere storage).
  → recomendación: v1 sin imágenes persistidas o solo URL; base64 inline solo para export.
- **Paleta:** el HTML usa `#FF3300`; M29 usa `#E84000` (primary Capybaras). Unificar a la
  paleta de M29 en el render del bloque V7 (el export WP puede mantener su propia identidad).
- **PDF:** NO portar html2canvas+jsPDF. Usar xhtml2pdf como M29 para consistencia y porque
  el entorno ya lo tiene resuelto.

---

## 9. Próximo paso

1. Presentar este `.md` a Ramiro → cerrar el gate de la sección 0.
2. Con gate cerrado: abrir chat de porting con worktree `feat/m32-case-study`.
3. Ejecutar fases 0-5 en orden, commit local por fase, push desde consolidador.
