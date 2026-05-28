---
tipo: module-spec
modulo: M29
estado: draft-para-ramiro
fecha: 2026-05-30
autor: lenin-acosta
---

# M29 · V5 Listing Comparison — Propuesta de shape de assets

Borrador para la reunión con Ramiro del 30/05. **Esto no es contrato cerrado**:
es una propuesta concreta para que la sync deje de ser abstracta y termine con
una shape aprobada (o ajustada) lista para entrar al contrato v2 del importer.

---

## 1) Problema

La shape interna de los assets dentro de `comparison_groups` no está formalizada
en ningún lado del repo. El discovery del 28/05 confirmó tres puntos de divergencia
que conviene resolver antes de construir el editor manual de V5:

- **El catálogo (`data/sales/_catalog.json`)** declara `V5_listing_comparison_competitor.schema.comparison_groups`
  como `dtype: array<object>` pero **sin `items_schema`**. La forma del objeto solo
  vive en lenguaje natural dentro del campo `description`. Compárese con V3 y V4,
  que declaran `items_schema` con field-name + dtype + required.
- **El renderer (`modules/pages/proposal_studio.py::_render_v5_asset_list`, L2187-2226)**
  acepta tres shapes mutuamente excluyentes por elemento dentro del mismo array:
  `str` (URL pelada) | `dict` con alguna de las keys `url | image_url | href` y
  opcional caption desde `caption | alt | note` | cualquier otra cosa cae a
  `st.json` fallback. Es defensivo por diseño, no por contrato.
- **La data real en disco** (la única propuesta poblada,
  `01fbf5c2-1fd9-44dd-9806-742e5deb8f71__v12.json`) ejercita las tres ramas en la
  misma propuesta: group 0 (`main_image`) usa strings, group 1 (`infographics`) usa
  dict `{url, caption}`, group 2 (`a_plus`) usa dict `{url}` sin caption. No hay
  un patrón único — está mezclado.
- **El propio renderer admite que esto queda diferido**. Cita literal del banner
  que se le muestra al Sales Director (L2127-2128):

  > *"Nota: V5 está fuera del contrato B7 v1.0 — la shape definitiva de los assets
  > se cierra en contrato v2 (post-reunión 22/05)."*

  La fecha de la cita (22/05) refleja la planificación previa; la reunión real
  pasó al 30/05 y este doc es el insumo.

Mientras la shape esté abierta, no hay manera honesta de construir un editor
manual: cualquier shape que asumamos en los widgets terminará rompiendo cuando
v2 quede cerrada con una shape distinta.

---

## 2) Shape propuesta

Recomendación: **un dict uniforme con keys explícitas, mismo shape para client_assets
y competitor_assets, mismo shape para los tres tipos de grupo (`main_image` /
`infographics` / `a_plus`)**.

### Asset (objeto único, sin variantes)

```json
{
  "url": "string (requerido)",
  "caption": "string | null",
  "alt": "string | null"
}
```

Reglas mínimas que sugiero llevar a la reunión:

- `url` es requerido. Sin URL el asset no aporta nada renderizable.
- `caption` es opcional. Es el texto humano debajo del asset (lo que hoy aparece
  como link label en el renderer cuando hay caption).
- `alt` es opcional. Texto alternativo accesible y/o para SEO interno del PDF.

### Comparison group completo con assets normalizados

```json
{
  "type": "main_image",
  "commentary": "Competidor usa fondo blanco saturado con texto overlay grande; nuestro main image queda más limpio pero pierde claim de producto.",
  "client_assets": [
    {
      "url": "https://m.media-amazon.com/images/I/client-main.jpg",
      "caption": "Main image actual",
      "alt": null
    }
  ],
  "competitor_assets": [
    {
      "url": "https://m.media-amazon.com/images/I/competitor-main.jpg",
      "caption": "Main image competidor principal",
      "alt": null
    }
  ]
}
```

### Por qué dict uniforme y no permitir strings sueltos

- **Editor manual viable.** Un editor Streamlit que tiene que ofrecer "agregar
  asset" necesita tres inputs (`url`, `caption`, `alt`) en algún momento. Si la
  shape acepta strings sueltos en paralelo, el editor termina con dos modos
  (string vs dict) o convirtiendo silenciosamente. Más sencillo cerrar el contrato.
- **Validación posible.** Con shape uniforme se puede declarar `items_schema` en
  `_catalog.json` (como V3 / V4) y enchufar las validaciones que ya hace el
  importer B7: `required_missing`, `field_unknown`, `coercion_failed`, `enum_unknown`.
  Sin items_schema, esos warnings nunca se emiten para V5.
- **Mata el triple-fallback.** El renderer puede simplificarse a "este asset
  tiene `url` y opcionalmente `caption` / `alt`" — se borran las ramas que
  manejan str pelado y las que prueban `image_url` / `href` / `note`.
- **Compat con el render actual.** El renderer ya soporta dict con `url` + caption
  (rama del medio en `_render_v5_asset_list`), así que la shape propuesta NO
  rompe nada visualmente — solo deja de ejercitar dos de las tres ramas.

---

## 3) Impacto y migración

### Render
Cero impacto visual. El renderer actual ya pinta correctamente `dict {url, caption}`.
La normalización solo elimina el code path "string suelto" y "dict sin url"; ambos
pasan a ser estados imposibles si el editor garantiza la shape.

### Data existente
Una sola propuesta tiene V5 poblada hoy
(`01fbf5c2-1fd9-44dd-9806-742e5deb8f71__v12.json`). Casos a migrar:

| Estado actual | Acción de migración |
|---|---|
| Asset `str` (URL pelada) | Envolver en `{url: <str>, caption: null, alt: null}` |
| Asset `dict {url, caption}` | Agregar `alt: null`, dejar el resto |
| Asset `dict {url}` sin caption | Agregar `caption: null, alt: null` |
| Asset con `image_url` / `href` | Renombrar a `url`. (No se observó en data real, pero el renderer lo aceptaba; cubrir defensivamente.) |
| Asset con `alt` o `note` ya presentes | Mover `note` → `caption` si caption no existe; preservar `alt`. |

Estimación: script de normalización de ~20 LOC en una sola pasada sobre
`data/sales/proposals/*.json`, idempotente. Una sola propuesta hoy → el riesgo de
romper data del cliente es esencialmente cero.

### Catálogo
Agregar `items_schema` al campo `comparison_groups` (no presente hoy) con la shape
propuesta. Coherente con el patrón de V3 y V4.

---

## 4) Preguntas abiertas para Ramiro

1. **¿`alt` es necesario o redundante con `caption`?** Caption es lo que se muestra
   en pantalla; alt es accesibilidad / SEO interno del PDF. Si la propuesta sale
   solo como deck visual, alt puede no aportar y simplifica el editor (dos inputs
   en vez de tres).
2. **¿Los assets necesitan un campo "tipo" (imagen / video / GIF)?** Hoy todos los
   assets observados son imágenes estáticas. Si las skills de audit empiezan a
   adjuntar grabaciones o GIFs, hay que reservar el slot ahora.
3. **¿El editor manual de V5 vive en contrato v2 o queda como Plan D aparte
   (igual que V6)?** Si la skill de audit autohidrata V5 vía B7 v2, el editor
   manual queda solo como fallback raro. Si la skill no cubre V5, el editor manual
   es la única vía y el contrato v2 puede ser más laxo.
4. **¿Min / max de assets por grupo y por lado?** Hoy el renderer acepta `[]`
   (caso real: `client_assets: []` en el grupo `a_plus` de la propuesta seed).
   ¿Tiene sentido un mínimo para que el grupo aporte (ej: al menos 1 asset en
   cualquiera de los dos lados)? ¿Máximo para evitar slides infinitas en el PDF?

---

## 5) Alcance del editor V5 (post-v2, solo si Ramiro confirma)

Una vez cerrada la shape, el editor manual sería un `_render_v5_listing_comparison_editor`
paralelo a los de V1 / V2, con:

- Por grupo (sobre los 3 fijos `main_image` / `infographics` / `a_plus`):
  - `st.text_area` para `commentary`.
  - Dos columnas (Cliente / Competidor) con la misma sub-UI:
    - Lista de assets cargados, renderizada como cards editables.
    - Por asset: `text_input(url)`, `text_input(caption)`, opcional `text_input(alt)`.
    - Botón "Quitar este asset" por fila.
  - Botón "Agregar asset (Cliente)" y "Agregar asset (Competidor)".
- Validación pre-guardar:
  - `url` no vacía y matchea regex razonable de URL (sin verificar resolución).
  - Warning suave si un grupo termina con 0 assets en ambos lados (sin bloquear).
- Buffer mutable en `st.session_state` siguiendo el patrón Plan D ya en uso para
  V1 / V2 (`_ensure_block_buffer` + commit explícito + invalidate).
- Save con auto-bump de versión, mismo path que el resto de los editores.
- No tocar `id` / `module_id` / `proposal_id` / `is_fixed` / `copy_overrides`
  (regla §6 del contrato B7 sigue aplicando).

Estimación gruesa: una sesión completa de implementación + tests, después de tener
la shape v2 firmada.

---

**Próximo paso**: llevar este doc a la reunión, marcar respuestas al lado de las
preguntas, y volver con un draft de `_catalog.json` actualizado y el script de
normalización de la propuesta seed.
