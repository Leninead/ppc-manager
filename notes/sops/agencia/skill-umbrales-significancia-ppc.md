# Skill — Umbrales de significancia PPC (derivados de break-even)

> Criterio para decidir CUÁNDO una fila (keyword/target/campaña) tiene data
> suficiente para actuar. Complementa `sop-analisis-360.md` y
> `SOP-PPC-360-de-reporte-a-decision.md`.
> Origen: sesión Dermaglós 2026-08-11 (correcciones de criterio en vivo).

## Principio central

Los umbrales NO son números fijos. Se derivan del **break-even** de cada
producto. Un umbral absoluto ("pausar a 10 clicks") es arbitrario y falla:
es demasiado lento para productos de margen fino y demasiado rápido para los
de margen grueso.

## Las 3 fórmulas

**1. Break-even ACoS = margen de contribución %**
```
BE_ACoS = (precio - FBA_fee - referral(15%) - COGS) / precio
```
Arriba de BE_ACoS, cada venta publicitaria pierde plata.

**2. Break-even CVR** (qué CVR necesita una keyword para ser rentable a su CPC)
```
BE_CVR = CPC / (contribution_margin_$)
```

**3. Umbral de clicks-sin-orden para PAUSAR** (significancia estadística)
```
clicks_pausa ≈ 3 × (1 / BE_CVR) = 3 × (CM$ / CPC)
```
Regla práctica binomial: con ~3×N clicks sin conversión se descarta con
~95% de confianza que la CVR real llega al break-even (N = 1/BE_CVR).

## Tabla de decisión (instanciar BE_ACoS por producto)

| Decisión | Criterio |
|---|---|
| **Escalar** (subir puja) | ACoS < BE_ACoS × 0.6 **y** ≥3-5 órdenes de señal |
| **Optimizar** (bajar puja, no matar) | ACoS entre BE_ACoS y BE_ACoS × 1.5 |
| **Cortar/comprimir agresivo** | ACoS > BE_ACoS × 1.5 sostenido con volumen |
| **Pausar/negativizar** | clicks sin orden ≥ 3×(1/BE_CVR) |
| **Observar (no tocar)** | todo lo que no cruza umbral |

## Tabla instanciada — Dermaglós (COGS ESTIMADO ~28%, REEMPLAZAR con real)

⚠️ Margen estimado. Pedir COGS real por ASIN a Edu/Adam y recalcular.

| ASIN | Precio | CM$ | BE_ACoS | Umbral pausa (clicks/0-órd) |
|---|---|---|---|---|
| B0CYLMJJJC crema single | $9.99 | $2.68 | 27% | ~7 |
| B0CYLM4L23 loción single | $18.89 | $5.55 | 29% | ~14 |
| B0F548KTXD loción 2pack | $32.11 | $12.17 | 38% | ~30 |
| B0F4KXZVNM crema 2pack | $16.99 | $5.33 | 31% | ~13 |

## Reglas duras (independientes del break-even)

1. **Nunca decidir sobre ACoS agregado.** Siempre desagregar a nivel
   target/keyword antes de pausar. Un ACoS de campaña alto puede esconder
   un target sano. (Caso 2026-08-11: campaña AUTO con ACoS agregado 164%
   escondía target `substitutes` con ACoS 22% / 6 órdenes — pausar la
   campaña habría matado el ganador.)

2. **STR (search-term) ≠ Targeting report (target).** Un search-term que
   quema NO implica que el target madre sea malo. Cruzar niveles antes de
   negativizar. (Caso: `vitamin a cream` parecía basura por search-term
   suelto en STR, pero como TARGET convertía 34 órdenes → era bajar puja,
   no negativizar.)

3. **Campaña nueva/fría: no juzgar por ACoS los primeros 7-10 días.**
   Sin historial arranca cara; necesita acumular clicks para significancia.

4. **El umbral de gasto se calibra al CPC de la cuenta.** No usar valores
   absolutos entre cuentas de CPC distinto.

## Casos de referencia (sesión 2026-08-11)

- ❌ Error evitado: pausar `close-match` con 2 clicks. Umbral real era 7-14.
  Sin data. Frenado a tiempo.
- ✅ Correcto: bajar puja `vitamin a cream` (ACoS 67% = 2.5× BE_ACoS 27%,
  pero 34 órdenes = mucha señal → comprimir, no matar).
- ⚠️ Hallazgo: crema single B0CYLMJJJC tiene BE_CVR 45% al CPC actual pero
  convierte ~18% en PPC → su PPC pierde en el margen (ACoS 54% > BE_ACoS 27%).
  Palanca: bajar CPC o subir margen. Pendiente próxima sesión.
