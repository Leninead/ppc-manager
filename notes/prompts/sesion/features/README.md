---
tipo: prompt-readme
actualizado: 2026-05-25
---

# Arranques de sesión por feature

> Prompts customizados para arrancar sesiones específicas por feature/módulo.
> Cada archivo tiene un bloque XML estable + secciones dinámicas que se
> actualizan automáticamente al cierre de cada sesión vía `cierre-meta`.

## Índice de features activas

| Feature | Archivo | Slug | Status | Última sesión |
|---|---|---|---|---|
| M27 Flat File Migrator v1.1 | `arranque-m27.md` | `m27` | activa (87%) | 2026-05-22 |
| M29 Proposal Studio | `arranque-m29.md` | `m29` | activa (ship 28/05) | 2026-05-22 |

## Features shippeadas (en `_shipped/`)

> Vacío por ahora. Cuando M29 y M27 se shipeen, sus arranques se mueven acá.

## Features archivadas (en `_archived/`)

> Vacío por ahora.

## Por qué existen estos archivos

Cada feature tiene contexto operativo único que se repite sesión tras sesión:
arquitectura, decisiones cerradas, gotchas históricos, deuda blanda, sub-agentes
validados. En lugar de re-explicar todo cada vez que se abre un chat, el arranque
embebe ese contexto y se actualiza automáticamente al cierre.

## Cómo se usa

### Al arrancar una sesión

1. Abrir chat nuevo en Claude.ai (proyecto `ppc-manager` conectado)
2. Abrir el arranque de la feature correspondiente
3. Copiar SOLO el contenido del code block `<role>...</task>` (el prompt XML)
4. Pegarlo como primer mensaje en el chat
5. Confirmar que Claude leyó el contexto antes de arrancar trabajo

### Al cerrar una sesión

El `cierre-meta` detecta automáticamente qué features se tocaron y genera
los prompts sop-writer correspondientes para actualizar:
- Estado actual del módulo
- Pendientes activos
- Próxima sesión propuesta
- Historial (append-only)

NO se tocan manualmente las secciones del arranque — todo pasa por cierre-meta.

### Al crear una feature nueva

Ver SOP completo: [[feature-lifecycle]]

Resumen: copiar `_template.md` → `arranque-{slug}.md` → poblar frontmatter +
bloque XML estable. Las secciones dinámicas se llenan en el primer cierre.

## Convención de slug

- Módulos: `m{##}` lowercase (ej: `m27`, `m29`)
- Features sin número: kebab-case descriptivo

## Referencias

- [[_template]] — template base para arranques nuevos
- [[feature-lifecycle]] — SOP del ciclo de vida
- [[cierre-meta]] — meta-prompt de cierre que dispara el update
- [[../clientes/README]] — README de arranques por cliente (estructura paralela)
- [[arranque-libre]] — fallback sin feature ni cliente
