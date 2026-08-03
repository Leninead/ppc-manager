---
tipo: sop
actualizado: 2026-05-25
version: v1.0
---

# SOP — Ciclo de vida de features

Define cómo nace, vive y muere cada feature/módulo del Agency OS en el sistema
de arranques por feature.

## Propósito

Garantizar que toda feature activa tenga un arranque cargado y actualizado en
`notes/prompts/sesion/features/`, de modo que:
- Lenin pueda abrir N chats paralelos sin armar prompts manuales
- El contexto sesión-a-sesión no se pierda
- Las features nuevas nazcan con su arranque desde un template

## Cuándo aplica

- Al **crear un módulo nuevo** en `core/constants.py` `_PAGES` (Mxx)
- Al **iniciar una feature compleja** que vaya a tomar más de 2 sesiones
  (ej: B7 importer, refactor mayor)
- Al **cerrar cada sesión** que toque una feature existente
- Al **shippear una feature** (mover arranque a estado `shipped`)
- Al **archivar una feature** (módulo discontinuado o consolidado en otro)

## Flujo

### 1. Nacimiento de feature

Cuando se agrega entry nuevo a `core/constants.py` `_PAGES`, en el mismo commit
o en el siguiente:

1. Copiar `notes/prompts/sesion/features/_template.md` →
   `notes/prompts/sesion/features/arranque-M{##}.md`
2. Llenar el frontmatter: `feature_slug`, `feature_status: activa`, `modulo_id`
3. Poblar el bloque XML estable con: descripción funcional, ubicación del código,
   decisiones arquitectónicas si ya las hay
4. Dejar secciones dinámicas vacías o con placeholders `<<<rellenar próxima
   sesión>>>` — se llenan en el primer cierre que toque la feature

### 2. Vida de feature — al cierre de cada sesión

El `cierre-meta` detecta automáticamente las features tocadas y genera prompts
sop-writer que actualizan:
- Estado actual del módulo
- Pendientes activos
- Próxima sesión propuesta
- Historial (append)

No tocar manualmente el bloque XML estable salvo si hubo decisión arquitectónica
nueva cerrada en la sesión.

### 3. Ship de feature

Cuando la feature se considera entregada al usuario final (módulo en producción,
sub-agente activo, etc):

1. Actualizar frontmatter: `feature_status: shipped`
2. Mover sección "Próxima sesión propuesta" → "Maintenance backlog"
3. Mover archivo a `notes/prompts/sesion/features/_shipped/arranque-M{##}.md`
4. El arranque sigue vigente para sesiones de bugfix o mejora menor
5. Actualizar `STATE-agencia.md` reflejando el ship

### 4. Archivado de feature

Cuando la feature se discontinúa o se consolida en otra:

1. Actualizar frontmatter: `feature_status: archivada`
2. Append al historial: "YYYY-MM-DD — archivada. Razón: <<<...>>>"
3. Mover archivo a `notes/prompts/sesion/features/_archived/`
4. Si fue consolidada en otra feature, agregar wikilink desde el arranque destino

## Convenciones de slug

- Módulos: `m{##}` en lowercase (ej: `m27`, `m29`)
- Features sin número de módulo: kebab-case descriptivo (ej: `b7-importer`,
  `dataDive-refactor`)
- El slug del archivo debe matchear el slug del frontmatter

## Reglas duras

- Nunca crear un arranque desde cero — siempre desde `_template.md`
- Nunca tocar el bloque XML estable de un arranque sin haber leído antes el
  contexto histórico del módulo (commits + dailies + STATE)
- Nunca borrar arranques de features shippeadas o archivadas — quedan como
  histórico
- Wikilinks a otros arranques siempre con `[[arranque-{slug}]]`

## Estructura final esperada

```
notes/prompts/sesion/features/
├── _template.md                  # template base, no tocar
├── _shipped/                     # arranques de features ya shippeadas
│   └── arranque-M28.md          # ejemplo: M28 SKU Progress Report (shipped 09/05)
├── _archived/                    # arranques de features discontinuadas
└── arranque-M{##}.md             # arranques de features activas
```

## Referencias cruzadas

- [[CLAUDE]] (vault) — convenciones generales
- [[cierre-meta]] — meta-prompt de cierre que dispara el update automático
- [[arranque-libre]] — fallback cuando la sesión no toca ninguna feature concreta
- [[prompts-arranque-sesion]] — SOP general de arranques (cliente + libre + continuar)
