# Contrato Importer B7 — HTML → M29 Blocks v1

**Versión:** 1.0
**Fecha:** 2026-05-19
**Owner técnico:** Lenin Acosta (Capybaras Agency)
**Counterpart:** Ramiro
**Status:** Draft pre-reunión 22/05 15:00
**Schema canónico:** commit `757292d` en `ppc-manager`

---

## 1. Objetivo

El importer B7 del módulo M29 Proposal Studio parsea HTMLs generados por
skills de auditoría (`amazon-brand-audit`, `digital-presence-audit`) y
autohidrata bloques V*-readonly dentro de propuestas existentes vía
drag-drop. El presente documento define el contrato técnico de attributes
`data-*` que las skills deben emitir para que B7 mapee cada elemento del
HTML al schema canónico de M29 sin ambigüedad.

Fuera de scope v1: edición manual de bloques (eso lo cubren los editores
Plan D V1/V2), bloques no-readonly, y bloques V5+ (todavía no implementados).

---

## 2. Bloques cubiertos en v1

| module_id | Skill productora | Status M29 |
|---|---|---|
| `V3_seo_opportunity` | `amazon-brand-audit` | readonly implementado (commit `a80b676`) |
| `V4_listing_improvements_current_state` | `digital-presence-audit` | readonly implementado (commit `2f436a0`) |

Schema canónico: `data/sales/_catalog.json` (campos + `items_schema` formal)
+ `data/_schemas/proposal-v1.json` (convención general). Commit de referencia:
`757292d`.

---

## 3. Convención `data-*` attributes

### Namespace
Todos los attributes del contrato usan prefijo **`data-proposal-*`**.
Cualquier otro `data-*` que la skill emita (estilo, debug, uso propio) es
ignorado por B7.

### Attributes definidos en v1

| Attribute | Aplica a | Valor esperado |
|---|---|---|
| `data-proposal-block` | Root del fragmento del bloque | `module_id` exacto del schema. Ej: `V4_listing_improvements_current_state` |
| `data-proposal-field` | Elementos con valor escalar | Nombre del campo plano del schema. Ej: `current_state_url` |
| `data-proposal-array` | Container de lista | Nombre del campo `array<object>` del schema. Ej: `items` |
| `data-proposal-item` | Cada item dentro de un array | Sin valor (presencia booleana). Marca el delimitador del objeto. |
| `data-proposal-item-field` | Hijos de cada item | Nombre del campo del item según `items_schema`. Ej: `status`, `notes` |
| `data-proposal-contract-version` | (Opcional, recomendado) Root del HTML | Versión del contrato. Ej: `"1.0"`. B7 rechaza HTMLs con versión mayor a la soportada. |

### Múltiples bloques por HTML
**El contrato soporta N bloques en un solo HTML.** B7 itera todos los
elementos con `data-proposal-block` que encuentre. Una skill puede emitir:

- **Un solo HTML con varios bloques** (recomendado para auditorías completas: V3+V4 en un drag-drop).
- **Un HTML con un solo bloque** (para re-imports puntuales o updates parciales).

No hay diferencia desde el lado del importer.

### Extracción de valor
B7 lee el **`textContent` trimeado** del elemento, salvo en estos casos:

- Si el elemento es `<a>`, lee `href`.
- Si el elemento es `<img>`, lee `src` (o `data-src` si existe, prioriza este).
- Si el elemento tiene `data-proposal-value="..."`, ese override gana sobre todo lo anterior.

---

## 4. Ejemplo concreto — V4_listing_improvements_current_state

```html
<section data-proposal-block="V4_listing_improvements_current_state"
         data-proposal-contract-version="1.0">
  <h2>Listing Current State — ASIN B0CK2KCBLS</h2>

  <a data-proposal-field="current_state_url"
     href="https://m.media-amazon.com/images/I/example-screenshot.jpg">
    Ver screenshot del listing actual
  </a>

  <table data-proposal-array="items">
    <tbody>
      <tr data-proposal-item>
        <td data-proposal-item-field="name">Main image</td>
        <td data-proposal-item-field="status">present</td>
        <td data-proposal-item-field="notes">1500x1500, white bg OK</td>
      </tr>
      <tr data-proposal-item>
        <td data-proposal-item-field="name">Infographics</td>
        <td data-proposal-item-field="status">weak</td>
        <td data-proposal-item-field="notes">Only 2 of 7 slots used</td>
      </tr>
      <tr data-proposal-item>
        <td data-proposal-item-field="name">A+ content</td>
        <td data-proposal-item-field="status">missing</td>
        <td data-proposal-item-field="notes"></td>
      </tr>
    </tbody>
  </table>
</section>
```

**Resultado del parser:**

```json
{
  "module_id": "V4_listing_improvements_current_state",
  "data": {
    "current_state_url": "https://m.media-amazon.com/images/I/example-screenshot.jpg",
    "items": [
      {"name": "Main image", "status": "present", "notes": "1500x1500, white bg OK"},
      {"name": "Infographics", "status": "weak", "notes": "Only 2 of 7 slots used"},
      {"name": "A+ content", "status": "missing", "notes": ""}
    ]
  }
}
```

---

## 5. Ejemplo concreto — V3_seo_opportunity + V4 en un solo HTML

Caso real: auditoría completa de un ASIN combina SEO + listing checklist.
La skill puede emitirlos en un solo HTML:

```html
<div data-proposal-contract-version="1.0">

  <section data-proposal-block="V3_seo_opportunity">
    <h2>SEO Opportunity — ASIN B0CK2KCBLS</h2>

    <table data-proposal-array="missing_keywords">
      <tbody>
        <tr data-proposal-item>
          <td data-proposal-item-field="keyword">swaddle blanket newborn</td>
          <td data-proposal-item-field="sv">12400</td>
          <td data-proposal-item-field="current_rank">18</td>
          <td data-proposal-item-field="opportunity_score">0.78</td>
        </tr>
        <tr data-proposal-item>
          <td data-proposal-item-field="keyword">saco para dormir bebe</td>
          <td data-proposal-item-field="sv">46836</td>
          <td data-proposal-item-field="current_rank"></td>
          <td data-proposal-item-field="opportunity_score">0.92</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section data-proposal-block="V4_listing_improvements_current_state">
    <h2>Listing Current State</h2>
    <!-- ... ver Sección 4 ... -->
  </section>

</div>
```

**Tipos numéricos:** B7 parsea según `items_schema` del campo. `sv` declarado
como `integer` → B7 hace `int(text)` o, si vacío/no numérico, queda `null`
(porque `nullable: true`). `opportunity_score` declarado como `number` → `float`.
`current_rank` con texto vacío → `null` (no `0`). Ver Sección 6 para el
detalle de coerciones.

---

## 6. Reglas de validación del importer

B7 aplica estas reglas al parsear. Cualquier violación se reporta al
usuario en el UI antes de persistir.

### Errores que bloquean el import

1. **HTML no contiene ningún `data-proposal-block`** → "HTML sin bloques M29 reconocibles".
2. **`module_id` no existe en `_catalog.json`** → "Bloque `{id}` desconocido".
3. **`data-proposal-contract-version` mayor a la soportada** → "Contrato {x.y} no soportado, B7 actual soporta hasta {a.b}".

### Warnings que NO bloquean

4. **`data-proposal-array` sin items hijos** → log warning, el campo queda como `[]`. No sobrescribe data existente con vacío salvo confirmación del usuario.
5. **`data-proposal-item-field` con nombre no presente en `items_schema`** → log warning, campo ignorado en ese item.
6. **Valor de enum fuera del set permitido** (ej. `status="critical"` cuando el schema acepta `missing|present|weak`) → log warning, el item se importa con valor `"unknown"`. El operador puede revisar y corregir desde el editor manual si el bloque tiene editor; para readonly queda como flag visible para próxima auditoría.
7. **Campo escalar requerido del schema ausente en el HTML** → log warning, default según tipo: `""` para strings, `null` para numéricos con `nullable: true`, `[]` para arrays.
8. **Coerción numérica falla** (campo declarado `integer` y el texto no parsea) → log warning, valor queda `null` si `nullable: true`, sino `0`.

### Comportamiento sobre bloques existentes

- B7 hace **overwrite total** del campo `data` del bloque target. NO hace merge parcial. Esto preserva determinismo: el HTML ES la fuente de verdad para el bloque que toca.
- Si la propuesta tiene 2 bloques con el mismo `module_id` (caso patológico), B7 actualiza el primero y emite warning. Cleanup queda a cargo del operador.
- Antes de overwrite, B7 muestra **diff visual** de qué campos cambian (planeado v1.1, ver Sección 9 D3).

---

## 7. Out of scope v1

- **V1_brand_overview y V2_category_overview**: editores manuales Plan D. Si la skill emite estos bloques, B7 los ignora con warning.
- **V5+ bloques**: no implementados en M29 al 2026-05-19. Se cubrirán en una v2 del contrato cuando los respectivos readonly estén en repo.
- **Multi-idioma (`copy_overrides`)**: ni V3 ni V4 declaran `copy_overrides_schema`. Si un bloque readonly futuro lo declara, el contrato se extiende con `data-proposal-copy-override-lang` y `data-proposal-copy-override-field`.
- **Imágenes embebidas en base64**: el contrato v1 solo acepta URLs en campos URL/image. Para upload de imágenes la skill usa otro canal (S3/CDN) y pasa URL al HTML.
- **Diff preview pre-overwrite**: planeado v1.1, ver D3 abajo.

---

## 8. Timeline

| Fecha | Hito |
|---|---|
| 2026-05-19 | Schema extendido con `items_schema` formal (commit `757292d`). Draft v1 contrato (este doc). |
| 2026-05-22 15:00 | Reunión Ramiro: review + ajustes + lock contrato v1. |
| 2026-05-22 → fecha TBD | Ramiro refactoriza emisión HTML en skills `amazon-brand-audit` + `digital-presence-audit` con attributes `data-proposal-*`. |
| Sprint paralelo | Lenin implementa B7 importer en M29 (módulo nuevo `modules/pages/b7_importer.py` o tab dentro de proposal_studio.py — TBD). |
| TBD | Smoke E2E: skill genera HTML → drag-drop en M29 → bloque V4 readonly muestra data sin edición manual. |

---

## 9. Decisiones para la reunión 22/05

Items que requieren input de Ramiro o decisión conjunta:

- **D1 — RESUELTO.** ¿Uno o varios HTMLs por skill? → Contrato soporta N
  bloques por HTML. Skill decide caso por caso. Sin restricción.

- **D2.** ¿El HTML debe incluir `data-proposal-target-id` para validar a
  qué propuesta inyectar, o B7 pregunta al usuario en el drag-drop?
  **Voto inicial:** B7 pregunta — más flexible, evita acoplar HTMLs a
  propuestas específicas. El UX es: drag-drop → modal "¿En qué propuesta
  inyectar?" → confirmar.

- **D3.** ¿Soporte para diff preview (mostrar qué campos cambia B7 antes
  de overwrite)?
  **Voto inicial:** sí en v1.1, no en v1.0 — first ship, then iterate.
  El warning de overwrite total queda como salvaguarda mínima en v1.0.

- **D4 — CONFIRMADO.** Versionado del contrato vía
  `data-proposal-contract-version="1.0"` en el root. B7 rechaza versiones
  futuras incompatibles. Costo bajo, ahorra dolor a futuro.

- **D5 (NUEVO).** ¿Cuándo Ramiro puede entregar el primer HTML con
  attributes `data-proposal-*` para smoke E2E? Bloqueante para B7
  shippeable. Sugerencia: HTML mock manual de 1 bloque V4 con 3 items
  para validar el parser, antes de refactor masivo de las skills.

- **D6 (NUEVO).** Si una skill emite ambigüedad (ej. dos `<table data-proposal-array="items">`
  dentro del mismo `data-proposal-block`), ¿B7 toma el primero, mergea, o
  rechaza? **Voto inicial:** toma el primero + warning. Mergear introduce
  complejidad que no necesitamos en v1.

---

## 10. Schema canónico de referencia

Vive en el repo `ppc-manager` en dos archivos:

- `data/sales/_catalog.json` — declara cada módulo del catálogo con su `schema`
  por campo (`dtype`, `required`, `nullable`, `description`, `items_schema`
  recursivo, `enum` cuando aplica).
- `data/_schemas/proposal-v1.json` — define entidades del sistema (Proposal,
  Block, CatalogModule, Template, InterestedVote) y documenta la convención
  general en `entities.catalog_module.fields.schema.description`.

**Commit de referencia para el contrato:** `757292d` (feat(M29): items_schema
formal para V3+V4 en catalog + convención en proposal-v1).

Snippet relevante del schema V4:

```json
"items": {
  "dtype": "array<object>",
  "required": true,
  "min_items": 0,
  "items_schema": {
    "name":   {"dtype": "string", "required": true},
    "status": {"dtype": "string", "required": true, "enum": ["missing", "present", "weak"]},
    "notes":  {"dtype": "string", "required": false, "nullable": true}
  }
}
```

Snippet relevante del schema V3 (`missing_keywords`):

```json
"missing_keywords": {
  "dtype": "array<object>",
  "required": true,
  "items_schema": {
    "keyword":           {"dtype": "string",  "required": true},
    "sv":                {"dtype": "integer", "required": false, "nullable": true},
    "current_rank":      {"dtype": "integer", "required": false, "nullable": true},
    "opportunity_score": {"dtype": "number",  "required": false, "nullable": true}
  }
}
```

B7 lee estos schemas en runtime y los usa para validar/coercionar valores
del HTML. Si una skill emite valores fuera del enum, B7 aplica el fallback
de Sección 6 regla 6 (`"unknown"`). Si emite tipos no parseables, aplica
regla 8.

---

## 11. Apéndice — protocolo de versionado del contrato

- **v1.0** (este doc, 2026-05-19): primer contrato, V3+V4, attributes core, N blocks por HTML.
- **v1.1** (planeado): diff preview pre-overwrite + reglas de merge si la skill envía bloques duplicados.
- **v2.0** (especulativo): multi-idioma vía `data-proposal-copy-override-*`, bloques V5+, upload de imágenes embebidas.

Cualquier cambio breaking incrementa MAJOR (v2.0). Adiciones retrocompatibles
incrementan MINOR (v1.1, v1.2). B7 lee `data-proposal-contract-version` y
rechaza MAJOR superior al soportado.
