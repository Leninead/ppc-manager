---
tipo: sop
actualizado: 2026-06-08
---

# SOP — Análisis 360° de cuenta PPC

Proceso end-to-end para una sesión de optimización completa de una cuenta de cliente, manual (sin depender del software del Agency OS) o asistido. Pensado para cuentas maduras donde una pasada superficial no alcanza.

## Cuándo aplica

- Sesión programada de revisión profunda de un cliente (cadencia típica: cada 14 días o D+7 post-bulks).
- Cuando hay señales de deterioro (ACoS subiendo, paid share desbalanceado, canibalización sospechada).
- Cuando los módulos del software (M2/M3/M4/M6) tienen bugs pendientes y el trabajo de cliente no puede esperar — el 360° manual entrega calidad equivalente o superior.

## Inputs mínimos (5 fuentes obligatorias)

El análisis 360° NO arranca sin las 5 fuentes. Si falta una, pedirla antes de empezar.

1. **STR** (Search Term Report) — términos de búsqueda con spend/sales/orders.
2. **SQP** (Search Query Performance) — mensual + semanal de la última semana cerrada. Market share (IS/CS/PS) por query.
3. **BR** (Business Report) by ASIN — ventas totales, sessions, CVR, paid vs orgánico.
4. **MAI** (Manage All Inventory, live Seller Central) — stock real, unfulfillable, delistings, runway.
5. **BSE** (Bulk Sheet Export) — config de todas las campañas (enabled/paused/archived).

> El **ACoS del BSE viene roto** — recalcular siempre desde Spend/Sales antes de tomar decisiones.

## Pasos (fases F)

- **F1 — Pre-flight / validación de inputs.** Confirmar las 5 fuentes. Validar que el BSE tiene filas y que no es de otro marketplace. Recalcular ACoS desde Spend/Sales.
- **F2 — KPIs cuenta.** ACoS real, TACoS, paid share, Brand IS. Comparar contra sesiones previas (tendencia, no foto).
- **F3 — Mapa de estructura.** Contar camps por estado (enabled/paused/archived). Detectar fragmentación (un ASIN en demasiadas camps = canibalización sistémica) y camps sin portfolio.
- **F4 — Cruce STR × SQP (× BSE).** Clasificar queries en buckets: ESCALAR, AGREGAR EXACT, HARVEST AUTO→PHRASE, BAJAR BID, NEGATIVAR, FUNNEL BREAK, etc. Aplicar los 7-checks antes de aprobar un AGREGAR EXACT.
- **F5 — Performance por ASIN.** Identificar ganadores (escalar), pricing kills, listings rotos, OOS/unfulfillable, delistings.
- **F6 — Decisiones de bid/pausa.** Bid up heroes, bid down degradados, pausar zombies y bleeders.
- **F7 — Construcción de bulks.** Negativos, graduaciones a Exact, camps nuevas por cluster. Naming Capybaras/Atom11-friendly.
- **F8 — Ejecución de bulks en Amazon.** Subir a Bulk Operations, confirmar Success por bulk, registrar UUID/hora.
- **Cierre** — daily + brand note + STATE + flags/P0 al AM.

## Ejemplo

Dermaglos US 2026-06-08 (2da ejecución): 5 inputs procesados → cruce 3-vías 1,211 queries / 9 buckets → 9 bulks F8 (B1–B9) todos Success → 5 P0 a Edu. ACoS 64.3%. Ver [[daily/2026-06-08]] + [[DERMAGLOS]].

## Excepciones conocidas

- Si los módulos de software están con bugs, correr el 360° 100% manual — no bloquea.
- Cuentas sin Atom11 (MX manuales) saltan la verificación de rules.
- `AGREGAR EXACT = 0` por varias sesiones consecutivas → tesis de cuenta estructuralmente cosechada; pausar el bucket Crear EXACT hasta SQP fresco post-optimización.

---

## v1.1 (2026-06-08)

Cambios sobre v1.0, extraídos de la 2da ejecución del SOP (Dermaglos):

- **Nuevo step F4 obligatorio — validación cruzada con Campaign Manager export (US) ANTES de subir bulks.** El BSE puede listar camps en `state=ENDED` que aparecen como enabled en el histórico del BSE. Cruzar contra el export live evita actuar sobre camps muertas.

- **Nuevo step F6.5 — decisiones pause/keep entre camps duplicadas cruzan performance LIVE del Manager.** Para AUTOs paralelas o una misma KW Exact en múltiples camps, cruzar cost / sales / ACoS / ROAS de los últimos 30d del Manager (el BSE solo muestra config, no performance).
  - **Caso de aprendizaje (08/06):** estuve a punto de pausar una AUTO de atom11 (ACoS 34.5% / ROAS 2.9×) y mantener la canónica (ACoS 171%) porque el BSE no las diferencia. El Manager export evitó el error.

- **Nueva regla anti-canibalización en F7 — antes de CREATE de una KW Exact nueva, verificar contra el BSE TODOS los estados (enabled/paused/archived) y TODOS los match types (Exact/Phrase/Broad):**
  - Existe Exact paused en camp paused → **safe** crear nueva en camp activa (no dispara "already exists").
  - Existe Exact enabled en otra camp activa → **canibalización potencial**; evaluar consolidación de bid en lugar de crear nueva.

- **Validación de archivos Campaign Manager export — detectar:**
  - (a) prefijo de moneda `MX$` = se exportó la cuenta MX por error.
  - (b) archivos vacíos (solo header + summary row con NaN).
  - El operador debe re-exportar con **marketplace US + Select All rows**.

- **Filtros correctos del Campaign Manager export:** marketplace US · status All (enabled + paused + archived) · Type SP mínimo · fechas Last 30 days.
