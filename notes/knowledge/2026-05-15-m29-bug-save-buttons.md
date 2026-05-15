---
fecha: 2026-05-15
tipo: knowledge
modulo: M29
tags: [bug, streamlit, ui, proposal-studio, regresion]
estado: activo-sin-resolver
---

# Bug M29 — Botones "💾 Guardar V1" y "💾 Guardar V2" no disparan handler

## Síntomas confirmados (smoke test 2026-05-15)

- Click en "💾 Guardar V2" en editor V2_category_overview → cero efecto
- Click en "💾 Guardar V1" en editor V1_brand_overview → cero efecto (regresión!)
- Network panel del browser: cero requests al servidor Streamlit al click
- Console JS: vacía, sin errores
- Conteo de archivos en `data/sales/proposals/` NO incrementa

## Historia

- **14/05**: V1 guardaba END-TO-END con verificación real (v40.json, v41.json,
  v44.json creados con `brand_name` distintos)
- **15/05**: bug apareció DESPUÉS del cierre del 14/05, durante sesión
  Bloque B3-c
- **Commit sospechoso primario**: `9a3eaad` — "checkpoint pre-B3-c" que en
  realidad contenía Bloque 1 + 2A + 2B (tocó código compartido entre V1 y V2
  antes del editor V2 propiamente dicho)

## Por qué los tests no lo agarraron

42/42 tests pytest verdes ejercitan API directa:
- `save_proposal()` recibiendo payload normalizado
- Payload normalization de copy_overrides
- Schemas de validación

NO ejercitan:
- UI rendering
- Dispatch de botones de Streamlit
- Session state lifecycle entre reruns
- AppTest E2E (deuda documentada mediano plazo)

## Hipótesis a investigar (prioridad)

1. **Colisión de keys** entre botón "Volver" del top bar y botones Guardar
   V1/V2 del editor de blocks
2. **st.expander envolviendo** el editor durante el B3-c que rompe scope
3. **Container scope cambiado** entre 14/05 y 15/05 que invalida los keys
4. **st.markdown con unsafe_allow_html="<button>"** emulando botón (HTML
   estático que NO dispara handler)
5. **try/except Exception: pass** swallower silencioso
6. **st.rerun() en helper que corre cada rerun** (loop infinito silencioso)

## Auditoría forense ejecutada

Prompt forense de 6 pasos lanzado en chat paralelo el 15/05.
Output pendiente de leer al inicio de próxima sesión.
Scope estricto: SOLO diagnóstico, no toca código.

## Plan de fix (después de leer auditoría)

1. Leer output de auditoría
2. Identificar hipótesis con evidencia concreta
3. Si es colisión de keys → fix de 1 línea, riesgo bajo
4. Si es scope de container → fix de 5-10 líneas, riesgo medio
5. Smoke test: ambos botones V1 y V2 deben funcionar post-fix
6. Si toma >2h sin progreso → mensaje preventivo a Slack ajustando deadline

## Lecciones (preliminares)

- **CC no garantiza no-regresión**: 42 tests verdes pero V1 se rompió
- **Necesidad de tests AppTest E2E**: cada vez más urgente, no opcional
- **El smoke test manual sigue siendo crítico** para UI Streamlit
- **Commits "checkpoint" peligrosos**: el `9a3eaad` tocaba más que B3-c

## Archivos involucrados

- `modules/pages/proposal_studio.py` (~1500-1800 LOC post-B3-c)
- `core/proposal_persistence.py`
- `core/proposal_paths.py`
- `tests/test_proposal_persistence.py`

## Wikilinks

[[STATE-agencia]] · [[2026-05-15]] · [[2026-05-14]] · [[M29-Plan-D]]
