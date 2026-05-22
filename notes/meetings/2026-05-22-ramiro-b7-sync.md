---
tipo: meeting
actualizado: 2026-05-22
participantes: [lenin-acosta, ramiro-folgueras]
duracion: ~1hr
modulo: M29
proxima_sync: 2026-05-30
---

# Sync Ramiro — B7 Importer + roadmap V3/V5 (22/05/2026)

## Contexto
Sync semanal Capybaras-Ramiro. M29 Proposal Studio shipping target jueves 28/05.
Previo a la reunión: extractor + merge layer + fix D6 + cobertura pytest
implementados (4 commits del día).

## Acuerdos de dirección (NO lock contractual)

### V3 — SEO Opportunity
- **Decisión:** lógica de DataDive Analyzer como source principal
- Refactor del parser actual de Research → módulo compartido
- Capybaras refactoriza, no requiere skill nueva de Ramiro
- DataDive tiene fit perfecto: `_parse_mkl` output mapea a missing_keywords
  + sv + current_rank + opportunity_score

### V5 — Listing Comparison
- **Decisión:** buscar forma de traer imágenes automatizadas
- Opciones abiertas: SerpAPI, Helium 10, scraping propio, Chrome extension
- DataDive descartado para V5 (no extrae URLs de imágenes — audit confirmó)
- Pendiente investigar costos vs esfuerzo
- Mientras tanto: editor manual de URLs pareadas (~1-2hrs) como fallback

### V4 — Listing Improvements
- Sin cambios: sigue alimentándose vía B7 HTML de skill
  `digital-presence-audit` (ya cubierto por B7 v1.0)

## Lo NO cerrado hoy
- D2/D3/D5/D6 del contrato B7 v1.0 → sin lock explícito
- Contrato B7 v1.0 sigue **draft**
- Conversación fue alto nivel (dirección estratégica) más que técnico-contractual

## Próxima sync
**Viernes 30/05** con M29 shippeado el día anterior (28/05). Material concreto
para mostrar: extractor + merge + UI dispatcher + editor V5 manual + refactor
DataDive operativo.

## Items pendientes de la reunión
1. Capybaras evalúa opciones de imágenes V5 (no bloquea ship 28/05)
2. Ramiro evalúa si manda HTML mock real de audit skill antes del 28/05
3. D2-D6 lock se discute próxima sync con contexto operativo real

## Plan operativo Capybaras al 28/05

| Día | Trabajo |
|---|---|
| Lunes 25/05 | UI dispatcher B7 (V3+V4) |
| Martes 26/05 | Refactor DataDive parsers → V3 mapper |
| Miércoles 27/05 | Editor manual V5 + testing |
| Jueves 28/05 | E2E + bugfixing + ship |

Wikilinks: [[M29-proposal-studio]] [[contrato-importer-b7-v1]] [[STATE-agencia]]
[[2026-05-22]]
