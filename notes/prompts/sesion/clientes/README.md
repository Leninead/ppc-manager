---
tipo: prompt-readme
actualizado: 2026-04-28
---

# Arranques de sesión por cliente

> Prompts customizados para arrancar sesiones específicas por cliente.
> Cada archivo tiene un bloque XML estable + secciones de estado que se
> actualizan al cierre de cada sesión.

---

## 📚 Índice

| Cliente | Archivo | Slug | Mercado | Última sesión |
|---|---|---|---|---|
| Dermaglos | `arranque-dermaglos.md` | `dermaglos` | Amazon USA | 2026-04-28 ✅ poblado |
| Love To Dream | `arranque-ltd.md` | `ltd` | Amazon México | 2026-04-25 (stub parcial) |
| Mott & Bow | `arranque-mb.md` | `mb` | Amazon USA | 2026-03 (stub mínimo) |
| Setex | `arranque-setex.md` | `setex` | Amazon | (stub mínimo) |

---

## 🎯 Por qué existen estos archivos

El `arranque-cliente.md` genérico de la carpeta padre (`notes/prompts/sesion/`)
sirve como fallback. Pero cada cliente tiene contexto operativo único que se
repite sesión tras sesión: heroes, naming, bid strategy, contactos, gotchas
históricos.

Esta subcarpeta tiene la versión **cargada por cliente** — pega el bloque XML
y Claude arranca con TODO el contexto del cliente ya en cabeza, sin que tengas
que explicarlo cada vez.

---

## 🔄 Cómo se usa

### Al arrancar una sesión

1. Abrir chat nuevo en Claude.ai (proyecto `ppc-manager` conectado)
2. Abrir el archivo del cliente correspondiente (ej: `arranque-dermaglos.md`)
3. Copiar SOLO el contenido del primer code block (el `<arranque_sesion>` XML)
4. Pegarlo como primer mensaje en el chat
5. Confirmar que Claude leyó el contexto antes de arrancar trabajo

### Al cerrar una sesión

El sop-writer del ritual de cierre debería hacer 4 cosas:

1. Daily de la sesión (`notes/daily/YYYY-MM-DD.md`)
2. Brand notes update (`notes/brands/{cliente}/*.md`)
3. STATE-agencia quirúrgico (`notes/state/STATE-agencia.md`)
4. **Update de este arranque** (`notes/prompts/sesion/clientes/arranque-{cliente}.md`)

Las secciones de este archivo que se actualizan al cierre son:

- `## 📊 Estado actual del cliente` — snapshot del momento (KPIs, plan ejecutado)
- `## ⏰ Pendientes activos` — todo lo que quedó abierto
- `## 📅 Próxima evaluación` — milestones con fechas
- `## 📜 Historial de actualizaciones` — una línea con la fecha + resumen

Las secciones que NO se tocan en el cierre normal:

- El bloque XML `## 🚀 Bloque para pegar al chat (estable)` — sólo cambia si se redefine algo estructural (naming convention nuevo, cambio de proceso)
- `## 🧠 Conocimiento operativo permanente` — sólo si hay decisión nueva permanente

---

## 📐 Estructura de cada arranque (Nivel C cargado)

Todos los arranques siguen la misma plantilla:

```
1. Frontmatter YAML (cliente, status_atom11, heroes_oficiales)
2. Bloque XML estable para pegar al chat
   ├── <contexto_proyecto>
   ├── <lectura_obligatoria_en_orden>
   ├── <conocimiento_operativo_{cliente}>
   ├── <bugs_y_gotchas_bulk_format>
   ├── <flujo_de_arranque>
   └── <rituales_obligatorios>
3. Estado actual del cliente (se actualiza al cierre)
4. Pendientes activos (se actualiza al cierre)
5. Próxima evaluación (se actualiza al cierre)
6. Conocimiento operativo permanente (estable)
7. Historial de actualizaciones (append-only)
8. Referencias cruzadas (wikilinks Obsidian)
```

---

## ➕ Cómo agregar un cliente nuevo

Cuando llegue cliente número 5+:

1. Copiar `arranque-dermaglos.md` (es el más completo, sirve de plantilla)
2. Renombrar a `arranque-{slug}.md` (kebab-case)
3. Reemplazar bloque por bloque el contenido del cliente nuevo
4. Marcar secciones desconocidas con `<<<rellenar próxima sesión {cliente}>>>`
5. Agregar entrada a la tabla del índice de este README
6. Actualizar el `.gitignore` si es necesario (la subcarpeta `clientes/` ya tiene
   exception, no debería ser necesario tocar nada)
7. Commit con mensaje `docs: agregar arranque-{cliente} prompt customizado`

---

## ⚠️ Reglas de mantenimiento

- **Frontmatter `actualizado`** debe coincidir con la fecha de la última sesión
- **`heroes_oficiales`** y **`status_atom11`** en el frontmatter son los datos
  más críticos — mantenerlos sincronizados con el contenido del archivo
- **Wikilinks** a `[[DERMAGLOS]]`, `[[skus_dermaglos]]`, etc. — verificar que los
  archivos referenciados existan después de cualquier reorganización del vault
- **Sección `Conocimiento operativo permanente`** — sólo agregar; si hay que
  cambiar algo, agregar un comentario `[deprecated YYYY-MM-DD]` antes de borrar
- **Stubs con `<<<rellenar>>>`** — son señales para el sop-writer de la próxima
  sesión. Cuando se complete una sección, borrar los `<<<>>>` literalmente.

---

## 🔗 Referencias

- `[[arranque-cliente]]` — fallback genérico (carpeta padre)
- `[[arranque-libre]]` — sesión sin cliente
- `[[arranque-continuar]]` — continuación de sesión a medias
- `[[arranque-reporte-semanal]]` — reporting weekly
- `[[cierre-meta]]` — ritual de cierre estandarizado
- `[[Biblioteca]]` — índice global del vault
- `[[CLAUDE]]` — instrucciones generales repo
