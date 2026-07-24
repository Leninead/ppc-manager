---
tipo: brand
actualizado: 2026-06-19
cliente: dermaglos
marketplace: USA
---

# DERMAGLOS.md

## Sesión 2026-04-28 — Análisis cruzado completo + ejecución bulk

> Detalle completo de la sesión con outputs y bugs en [[2026-04-28]].

### Hallazgos críticos (10)

1. **Bug del comma de Atom11 — diagnóstico CORREGIDO hoy**: el campaign_analyzer mostraba un nombre concatenado con coma. El export real de Amazon muestra el nombre limpio: `Body Lotion 2Pack - B0F548KTXD - SD - VCPM - Prospecting Vitamin A` (Campaign ID `341852079119387`). La coma venía de Atom11 mostrando una rule asignada a 2 campañas (Prospecting Retinol + Prospecting Vitamin A). Bug REAL: la rule HARD-STOP no dispara contra esa campaña. Spend lifetime $558.57 / Sales $32.11 / ACoS 1,740% / Started 10/01/2026 (3.5 meses sangrando). Pausada manualmente hoy.
2. **Double-optimize sistémico en TODAS las DEC rules** — INC tiers usan rangos disjuntos, DEC usan thresholds acumulativos. ~24 rules a reescribir.
3. **5 SP ASIN "Related Dermaglos Products" con triple-classification** — apuntan a ASINs propios → DEFENSIVE puro (no CONQUEST + RANKING + DEFENSIVE simultáneo).
4. **62→0 campañas zombies (resolución)**: el campaign_analyzer mostraba 114 campañas, BulkSheetExport muestra 84 reales. **30 campañas eliminadas en cleanup previo** (probablemente con deploy Atom11 v2026.2 del 23-25/04). Las 11 P2 del archivo `03_campañas_pausar_dermaglos_2026-04-28.xlsx` quedan canceladas — ya no existen.
5. **B0F548KTXD sale de heroes**: ROAS 0.61× lifetime / ACoS 163% / CVR 3.7% / Net -$42/mes. Movido de hero → monitor. Cambio narrativo importante con cliente.
6. **B0F6VZMF2V Facial Skincare Set = estrella oculta PERO OOS**: ROAS 6.20× / CVR 33% (máximo de la cuenta) pero **Available FBA = 0 desde 09/04/2026**. Push diferido hasta restock. Stock confirmado en Seller Central.
7. **Hipoglos cream = oportunidad #1 cross-brand**: Mercado paga $19, Dermaglos vende $9.99 (47% más barato). SQV 1,074/mes, 17 mkt purchases/mes, BS 5.88%, IS 6.30%. Audiencia hispana cross-shopping. Campaña Conquest creada hoy.
8. **Mina sin tocar — `dermaglos cleansing gel`**: STR mostró ACoS 3% (mina). Cross-SKU 100% (compra otros productos). Campaña EXACT dedicada bid $13.50 creada hoy.
9. **Cluster Vitamin A subexplotado**: 8 KWs validadas BS 100% en SQP. `vitamin a cream` = 18 órdenes ACoS 51% IS 8.9% (techo). Vitamin A Power Cluster activado hoy con $40/d.
10. **Cluster Retinol confirmado matar**: $121 spend $0 sales en 30d. Dermaglos no compite en Retinol (claim es Vitamina A). 7 negativos aplicados hoy.

### Cambios de status estratégico

- **B0F548KTXD movido de hero → monitor** (ROAS 0.61× lifetime). Ya no recibe push.
- **B0F6VZMF2V identificada como estrella oculta** (ROAS 6.20×, CVR 33%) pero OOS desde 09/04 → push diferido hasta restock.
- **Oportunidad #1 cross-brand: Hipoglos cream** (SQV 1,074, BS 5.88%, ventaja $19→$10). Conquest creada.
- **Mina sin tocar: `dermaglos cleansing gel`** (ACoS 3% en STR). EXACT dedicado creado bid $13.50.

### Acciones ejecutadas hoy

**7 campañas nuevas creadas** — naming Atom11-friendly híbrido `DG | OBJETIVO | TIPO - Producto - ASIN - Cluster`:

| # | Campaña | Budget |
|---|---|---|
| 1 | `DG \| CONQUEST \| SP \| EXACT - Cream - B0CYLMJJJC - Hipoglos` | $20/d |
| 2 | `DG \| RANKING \| SP \| EXACT - Cream - B0CYLMJJJC - Vitamin A Power` | $40/d |
| 3 | `DG \| RANKING \| SP \| EXACT - Lotion - B0CYLM4L23 - Vitamin A Lotion` | $25/d |
| 4 | `DG \| RANKING \| SP \| EXACT - Cream - B0CYLMJJJC - Allantoin Hub` | $30/d |
| 5 | `DG \| DEFENSIVE \| SP \| EXACT - Cleanser - B0CYK4G2Y8 - Cleansing Gel Brand` | $25/d (bid $13.50) |
| 6 | `DG \| DEFENSIVE \| SP \| EXACT - All Heroes - Brand Hub Defensive` | $30/d (35 KWs brand) |
| 7 | `DG \| DISCOVERY \| SP \| PHRASE - Cream+Lotion - Spanish Hidratante` | $30/d |

**46 negativos aplicados** (Bulk 05): cluster Retinol completo + competidores (Lubriderm, Bioderma, Eucerin, Bepantol) + categorías huge (body lotion, micellar water, glycerin, oily skin) + 27 STR waste tier 1.

**10 campañas P0 pausadas manualmente**: spend lifetime $973.66 con $42.00 sales (ACoS 2,318%) → $132/d budget liberado = $3,960/mes.

**Cluster Vitamin A Power activado**: $40/d, 8 KWs BS 100% en SQP.

**Brand Hub Defensive activado**: 35 KWs brand sin paid coverage previas.

**Net delta budget**: solo +$68/d en cuenta (de los $200/d nuevos, $132/d venían de pausas) — mucho más eficiente de lo que parecía.

## Mensaje pendiente para Neha — corrección finding #1

Listo para copiar a Slack:

```
Hi Neha,

Quick update on finding #1 about the "comma bug" in CONQUEST SD HARD-STOP:

Correction: The campaign name in Amazon is actually clean — Body Lotion 2Pack - B0F548KTXD - SD - VCPM - Prospecting Vitamin A (no comma, no concatenation). The comma I saw in the campaign-wise export was likely showing two campaigns sharing the same rule, separated by comma in the rule's target list.

The actual problem is the rule isn't firing. Current state of that single campaign:

- Campaign ID: 341852079119387
- Spend lifetime: $558.57
- Sales: $32.11 (1 order)
- ACoS: 1,740%
- ROAS: 0.06×
- Daily budget: $12
- Started: Jan 10, 2026 — running 3.5 months unchecked
- 978 clicks for 1 conversion (Conversion Rate 0%)

It clearly meets the HARD-STOP criteria, but the rule isn't pausing it. Possible causes worth investigating:

1. Tier assignment may be wrong (this is a $32 product → MID/HIGH tier, but maybe classified LOW)
2. Double-optimize bug we discussed could be "satisfying" the rule via bid reductions before HARD-STOP fires
3. Rule assignment to multiple campaigns may be causing logic conflict

I'm pausing the campaign manually today to stop the bleed. Same diagnostic applies to the equivalent campaign on the 2Pack Cream (Dermatological 2Pack - B0F4KXZVNM - SD - VCPM - Prospecting Vitamin A, ID 125683659095742).

Findings #2-4 from the original message stand as written.
```

## Pendientes próxima sesión

### Manual en Campaign Manager

- [ ] **Asignar Portfolio ID a las 7 nuevas campañas** — urgente, sin esto Atom11 no las clasifica
- [ ] Resolver `allantoin 0.5% cream` (manual UI — el carácter `%` fue rechazado en bulk; SQV solo 79/mes, low priority)
- [ ] Bid adjust SD `Dermatological Cream - B0CYLMJJJC - SD - VCPM - Views Retargeting 30D` (ID `169476572963877`): bajar default de $1.00 a $0.50
- [ ] Subir budget `B0CYLDSQ5L - Body Cream - SP ASIN - Exact - Related Dermaglos Products` (ID `340653992125674`) de $5/d a $15/d (ROAS 3.13× / ACoS 32%, subexplotada)

### Comunicación

- [ ] Enviar mensaje corregido a Neha sobre el bug del comma (texto arriba en este doc)

### Listing optimization (gate para escalar)

- [ ] Tattoo copy en bullets/A+ de B0CYLMJJJC + B0CYLM4L23 (activar 500K imp/mes mkt)
- [ ] B0CYK4G2Y8 (Facial Cleanser) — Rufus analysis (CVR 5.8% es problema de listing)
- [ ] B0CYLDSQ5L (Body Cream) — Rufus pre-reactivación

### Diferidos

- [ ] Cuando reabastezcan B0F6VZMF2V (Facial Set OOS desde 09/04): crear 2 campañas Push EXACT + PAT
- [ ] Cluster Tattoo decisión final post listing fix (si en 30d sigue 0 conv → pausar)
- [ ] Re-correr STR 15/05 para medir delta ACoS post-ejecución

### Conversación con cliente (futuro revenue)

- [ ] Vit C, Niacinamida, BB Cream, Protector Solar — hay demanda brand en SQP, no listados en Amazon USA. Definir si lanzar. Detalle en [[skus_dermaglos]].

---

## 💊 Cliente: Dermaglos
**Categoría:** Skincare dermatológico (Body Cream, Body Lotion, Facial Cleanser, Serums)
**Marketplace:** Amazon USA 🇺🇸
**AM:** Lenin Acosta
**Datos:** Campañas Jan-Mar 2026 | STR Feb 19 2026 | SQP Feb 28 2026 | Campaign CSV Mar 23 2026
**Datos históricos detallados:** ver `DERMAGLOS_DATA.md`

---

## 🟢 Estado general del cliente (2026-04-06)

- ACoS cuenta: 58.0% (bajó de 76.1%) → meta Q2 ≤55%
- CVR: 12.7% ✅ (supera meta de ≥10%)
- Ad Sales/día: ~$143/día (rozando meta de $150)
- Nicho ganador: vitamin a cream (SQP PS 16.1%)
- Audiencia: hispanohablante USA
- Hero ASINs: B0CYLMJJJC (Cream $9.99) | B0CYLM4L23 (Lotion $18.89) | B0F4KXZVNM (2Pack Cream $16.99) | B0F548KTXD (2Pack Lotion $32.11)
- Campañas: 123 clasificadas en 11 grupos por objetivo + 13 nuevas SD + 3 nuevas SP (Apr 6)
- Atom11: 83 rules v2026.2 AGRESIVO activas — primera evaluación completada 07/04
- Archivos referencia: `Atom11_Rules_v2026_2.md` | `DG_Atom11_CheatSheet_v2_AGRESIVO.xlsx`

---

## 🧠 INSIGHT ESTRATÉGICO CLAVE

> **El cliente de Dermaglos en USA es hispanohablante.** El SQP muestra 105 queries de marca — la mayoría en español: `dermaglos crema`, `dermaglos embarazo`, `dermaglos vitamina a`, `dermaglos para estrias`. Esto define toda la estrategia: keywords en español, copy en español, targeting a comunidad latina en USA.

> **El CVR es excelente (10.7-12.7%)** — los listings convierten bien cuando llega tráfico relevante. El ACoS alto no es problema de producto, es problema de keywords incorrectas (compitiendo contra Aquaphor, CeraVe, Vaseline donde Dermaglos no tiene chance).

> **El nicho ganador es `vitamin a cream`** — IS 8.9%, 14 purchases de marca, PS% 16.1%. Diferenciación real.

> **Nuevo nicho validado: tattoo aftercare** — `crema para tatuajes` 2,492 vol · `tattoo lotion` 14,649 vol · IS brand casi 0% = oportunidad enorme sin competencia de marca.

> **Allantoin** — ingrediente diferenciador. STR confirma 5 órdenes con `allantoin` a 36% ACoS. SQP: 2,242 vol con 2 purch brand. Escalar.

---

## 🛍️ Catálogo completo

### Familia Body Lotion — Parent B0FG84HMRN

| ASIN | Producto | Precio | Sales | Units | BSR | Stock |
|------|----------|--------|-------|-------|-----|-------|
| B0CYLM4L23 | Body Lotion 13.52 Fl Oz | $18.89 | $1,322 | 79 | 99,680 | 174 + 200 inbound |
| B0F548KTXD | 2-Pack Body Lotion 13.52 Fl Oz | $32.11 | $822 | 30 | 98,337 | 158 |

### Familia Moisturizing Cream — Parent B0FDX9XR56

| ASIN | Producto | Precio | Sales | Units | BSR | Stock |
|------|----------|--------|-------|-------|-----|-------|
| B0CYLMJJJC | Moisturizing Cream 1.76 oz | $9.99 | $1,388 | 154 | 66,423 | 380 |
| B0F4KXZVNM | 2-Pack Moisturizing Cream 1.76 oz | $16.99 | $763 | 45 | 75,168 | 147 + 150 inbound |

### ASINs Standalone

| ASIN | Producto | Precio | Sales | Units | BSR | Stock |
|------|----------|--------|-------|-------|-----|-------|
| B0CYLDSQ5L | Body Cream 10.58 oz | $13.49 | $412 | 35 | 207,585 | 156 |
| B0CY2XC91Z | Micellar Water 13.52 Fl Oz | $9.49 | $284 | 30 | 402,632 | 35 |
| B0CYK4G2Y8 | Facial Cleanser Oily Skin 5.29 oz | $9.89 | $106 | 10 | 462,935 | 142 |
| B0CYKDSDJX | Hyaluronic Acid Serum 1 Fl Oz | $18.89 | $277 | 14 | 234,320 | 62 |
| B0CYL1RLNQ | Ultra Volume Night Cream 1.76 oz | $19.79 | $194 | 11 | 314,512 | 52 |
| B0F6VZMF2V | 3-Pack Facial Skincare Set | $32.90 | $197 | 6 | 584,874 | 2 |

---

## 🎯 Hero ASINs — Performance Apr 6, 2026

### B0CYLMJJJC — Moisturizing Cream $9.99 (Hero #1)
- Ad Spend: $211 | Ad Sales: $515 | 41 órdenes | ACoS 41% | BSR 66,423
- Net/unit: $6.28 | Fee FBA: $2.91 | SKU: PVENUS0782
- Top campaña: SP ASIN Defensive → 24% ACoS, 20 órdenes ✅

### B0CYLM4L23 — Body Lotion $18.89 (Hero #2)
- Ad Spend: $297 | Ad Sales: $558 | 32 órdenes | ACoS 53% | BSR 99,680
- Net/unit: $11.02 | Fee FBA: $5.04 | SKU: PVENUS0787
- Top campaña: SP ASIN Defensive → 40% ACoS, 14 órdenes ✅

### B0F4KXZVNM — 2Pack Cream $16.99
- Ad Spend: $178 | Ad Sales: $213 | 14 órdenes | ACoS 84% | BSR 75,168
- Net/unit: $10.24 | Fee FBA: $4.20 | SKU: KIT 4 - FBA
- Top campaña: SP Exact Related Dermaglos → 9% ACoS, 4 órdenes ✅

### B0F548KTXD — 2Pack Lotion $32.11
- Ad Spend: $175 | Ad Sales: $255 | 10 órdenes | ACoS 69% | BSR 98,337
- Net/unit: $21.37 | Fee FBA: $5.92 | SKU: KIT 3 - FBA
- Top campaña: SB Broad Defensive → 20% ACoS ✅

---

## 📊 KPIs cuenta — Acumulado Jan-Mar 2026

| Métrica | Campañas (Jan-Mar) | STR (Feb 19) | Apr 6 (Mar22-Apr5) |
|---------|-------------------|--------------|---------------------|
| Spend | $7,980.88 | $1,541.91 | $1,163.80 |
| Sales | $10,484.86 | $2,323.00 | $2,006.70 |
| ACoS | 76.1% 🔴 | 66.4% 🔴 | 58.0% 🟡 |
| Orders | 622 | 132 | 128 |
| CVR | 11.51% ✅ | 10.70% ✅ | 12.7% ✅ |

---

## 🏗️ Estructura de campañas — 11 grupos originales + nuevas Apr 6

| Sheet Atom11 | Campañas | Objetivo | Tipo | Rules |
|--------------|----------|----------|------|-------|
| DG DISCOVERY SP | 16 | DISCOVERY | SP | ✅ 6 Bid + Negate + HardStop + 2 Harvest |
| DG RANKING SP | 41 | RANKING | SP | ✅ 6 Bid + Negate + HardStop + 2 Harvest |
| DG CONQUEST SP | 15 | CONQUEST | SP | ✅ 6 Bid + Negate + HardStop |
| DG DEFENSIVE SP | 23 | DEFENSIVE | SP | ✅ 6 Bid + Negate + HardStop |
| DG PROFIT SP | 5 | PROFIT | SP | ✅ 6 Bid + Negate + HardStop |
| DG REMARKETING SD | 2 | REMARKETING | SD | ✅ 6 Bid + HardStop |
| DG DEFENSIVE SB | 6 | DEFENSIVE | SB | ✅ 6 Bid + HardStop |
| DG RANKING SB | 2 | RANKING | SB | ✅ 6 Bid + HardStop |
| DG DEFENSIVE SD | 6 | DEFENSIVE | SD | ✅ 6 Bid + HardStop |
| DG CONQUEST SD | 1 | CONQUEST | SD | ✅ 6 Bid + HardStop |
| DG SCAVENGER | 6 | SCAVENGER | SP | ❌ Sin rules (por diseño) |

---

## 🤖 Atom11 Rules — v2026.2 AGRESIVO

> Detalle completo en: `notes/brands/dermaglos/Atom11_Rules_v2026_2.md`

| Bloque | Rules | Campañas |
|--------|-------|----------|
| SP Bid (6 objetivos × 6 rules) | 36 | 102 |
| SB Bid (DEFENSIVE + RANKING) | 12 | 8 |
| SD Bid (DEFENSIVE + CONQUEST + REMARKETING) | 18 | 9 |
| Negate SP (5 objetivos) | 5 | varies |
| HardStop SP (6 objetivos) | 4 | varies |
| HardStop SB/SD (4 grupos) | 4 | varies |
| Harvest (DISCOVERY + RANKING) | 4 | 57 |
| **TOTAL** | **83** | **117 camps (95%)** |

### Thresholds v2026.2
- INC AGG: <0.50× (+15%) | INC SOFT: 0.50×-0.85× (+8%) | FLAT: 0.85×-1.0×
- DEC SOFT: >1.14× (-10%) | DEC RISK: >1.36× (-15%) | DEC CTRL: >1.57× (-25%) | DEC HARD: >1.86× (PAUSE TARGET)

### Targets por objetivo

| Objetivo | Target | INC AGG < | DEC SOFT > | DEC HARD > (PAUSE) |
|----------|--------|-----------|------------|-------------------|
| RANKING | 70% | 35% | 80% | 130% |
| DEFENSIVE | 50% | 25% | 57% | 93% |
| DISCOVERY | 84% | 42% | 96% | 156% |
| CONQUEST | 60% | 30% | 68% | 112% |
| PROFIT | 35% | 18% | 40% | 65% |
| REMARKETING | 50% | 25% | 57% | 93% |

### Config global
- TIER MID | Wait 3d | Tue+Fri 06:00 | Lookback 14d (Bid) / 30d (Negate/Harvest)
- Until reaches: INC $2.00 | DEC $0.15
- Negate exclude KW: dermaglos, dermaglós
- ⚠️ Nota: SB `Campaign: B0CYLM4L23 - Body Lotion - SB-KW - CPC - Exact - Vitamin E Lotion` quedó fuera de coverage de Atom11 — revisar asignación

---

## 📢 SD Campaigns — Estado Apr 6, 2026

### Creadas hoy (Apr 6)

| Campaña | ASIN | Tipo | Audiencia | Bid | Budget |
|---------|------|------|-----------|-----|--------|
| Dermatological Cream - B0CYLMJJJC - SD - VCPM - Views Retargeting 30D | B0CYLMJJJC | VCPM | Views remarketing · Adv products · 30d | $5.00 | $15/día |
| Dermatological Cream - B0CYLMJJJC - SD - CPC - ASIN Defensive | B0CYLMJJJC | CPC | Individual product B0CYLMJJJC | $1.24 | $10/día |
| Dermatological 2Pack - B0F4KXZVNM - SD - VCPM - Upsell desde Cream | B0F4KXZVNM | VCPM | Views remarketing B0CYLMJJJC visitors → ad B0F4KXZVNM | $5.00 | $10/día |
| Body Lotion - B0CYLM4L23 - SD - VCPM - Views Retargeting 30D | B0CYLM4L23 | VCPM | Views remarketing · Adv products · 30d | $5.00 | $15/día |
| Body Lotion 2Pack - B0F548KTXD - SD - VCPM - Upsell desde Lotion | B0F548KTXD | VCPM | Views remarketing B0CYLM4L23 → ad B0F548KTXD | $5.00 | $10/día |
| Dermatological 2Pack - B0F4KXZVNM - SD - VCPM - Views Retargeting 30D | B0F4KXZVNM | VCPM | Views remarketing · Adv products · 30d | $5.00 | $12/día |
| Dermatological 2Pack - B0F4KXZVNM - SD - VCPM - Prospecting Vitamin A | B0F4KXZVNM | VCPM | Category: Body Creams + Facial Creams | $4.00 | $10/día |
| Body Lotion 2Pack - B0F548KTXD - SD - VCPM - Views Retargeting 30D | B0F548KTXD | VCPM | Views remarketing · Adv products · 30d | $5.00 | $12/día |

### Editadas hoy
| Campaña | Acción |
|---------|--------|
| Body Lotion 2Pack - B0F548KTXD - SD - VCPM - Prospecting - Retinol | Cambió audiencia: Retinol → Similar to advertised products + Body Creams |
| B0CYLM4L23 - Body Lotion - SD - CPC - Remarketing | Pausada — era Purchases CPC mal configurada, reemplazada por Views VCPM |

### Existentes OK
| Campaña | ACoS | Órdenes |
|---------|------|---------|
| B0F548KTXD - Body Lotion 2Pack - SD - VCPM - Dermaglos Products | 31% | 3 ✅ |

---

## 🆕 SP Campaigns — Nuevas Apr 6, 2026

| Campaña | ASIN | SKU | Keywords | Match | Bid |
|---------|------|-----|----------|-------|-----|
| Dermatological Cream - B0CYLMJJJC - SP - KW - EXACT - Allantoin Core v2 | B0CYLMJJJC | PVENUS0782 | allantoin · allantoin cream · alantoina crema · allantoin moisturizer | exact/phrase | $0.80–1.00 |
| Dermatological 2Pack - B0F4KXZVNM - SP - KW - PHRASE - Spanish Tattoo v2 | B0F4KXZVNM | KIT 4 - FBA | crema para tatuajes · tattoo cream · tattoo healing cream · tattoo aftercare cream · tattoo moisturizer | exact/phrase | $0.75–0.90 |
| Body Lotion - B0CYLM4L23 - SP - KW - PHRASE - Spanish Tattoo v2 | B0CYLM4L23 | PVENUS0787 | tattoo lotion · crema para tatuajes · tattoo aftercare lotion · lotion for tattoos · tattoo moisturizer | exact/phrase | $0.75–0.90 |

> Nota: Las versiones sin "v2" fueron archivadas — Amazon las procesó vacías en el primer bulk fallido.

---

## 🚨 Alarmas activas (Apr 6)

### Campañas pausadas hoy
| Campaña | Motivo |
|---------|--------|
| Body Lotion - B0CYLM4L23 - SP - AUTO - Discovery V2 | 255% ACoS · $36 · 1 orden · V1 funciona mejor |
| Campaign: B0CYLM4L23 - Body Lotion - SB-KW - CPC - Exact - Vitamin E Lotion | 183% ACoS · keyword incorrecta |

### Pendiente pausar
| Campaña | Spend | Status |
|---------|-------|--------|
| Body Lotion 2Pack - B0F548KTXD - SP - PT - ASIN - Retinol Competitors | $65.40 · 0 ventas | PAUSAR |
| Dermatological 2Pack - B0F4KXZVNM - SP KW - BROAD KWS | $76.62 · 767% ACoS | PAUSAR |

### Inventario crítico
| ASIN | Problema |
|------|---------|
| B0F6VZMF2V | 2 units disponibles → ads pausadas |

---

## ✅ Lo que está funcionando

1. **SP ASIN Defensive Cream** — ACoS 24%, 20 órdenes — mejor campaña de la cuenta
2. **SP ASIN Defensive Lotion** — ACoS 40%, 14 órdenes
3. **SP Exact Related Dermaglos 2Pack Cream** — ACoS 9%, 4 órdenes 🔥
4. **SB Broad Defensive 2Pack Lotion** — ACoS 20%, 2 órdenes
5. **SD VCPM Dermaglos Products 2Pack Lotion** — ACoS 31%, 3 órdenes
6. **CVR 12.7%** — listings convierten excelente
7. **vitamin a cream** — IS 7.9%, 10 purch brand SQP
8. **allantoin** — 5 órdenes STR, 36% ACoS
9. **Atom11 v2026.2** — 83 rules cubriendo 95% de campañas

---

## 📋 Pendientes

### Monitoreo
- [ ] Evaluar Atom11 v2026.2 — próxima evaluación 11/04 (Tue)
- [ ] Monitorear las 8 SD nuevas — primera semana es estabilización
- [ ] Evaluar agregar TIER LOW/HIGH cuando ACoS baje a <40%

### Campañas — urgente
- [ ] PAUSAR: Body Lotion 2Pack B0F548KTXD - SP - PT - ASIN - Retinol Competitors ($65 waste)
- [ ] PAUSAR: Dermatological 2Pack B0F4KXZVNM - SP KW - BROAD KWS (767% ACoS)
- [ ] Archivar campañas SD vacías B0CYLM4L23 - Body Lotion - SD - CPC - Remarketing (ya pausada)
- [ ] Archivar 3 campañas SP sin "v2" que quedaron vacías

### SB por crear (manual — requiere creativos)
- [ ] Dermatological Cream - B0CYLMJJJC - SB - KW - CPC - Vitamin A Core
- [ ] Dermatological 2Pack - B0F4KXZVNM - SB - KW - CPC - Vitamin A Core
- [ ] Body Lotion 2Pack - B0F548KTXD - SB - KW - CPC - Vitamin A Lotion

### SBV — esperando video del cliente
- [ ] SBV × 4 heroes — vitamin a cream + brand + allantoin — SOP 2026 obligatorio
- [ ] Pedir video al cliente: claim vitamina A + beneficios

### Negativizar — esta semana
- [ ] lotion for extremely dry skin ($24 · 0 ventas)
- [ ] body moisturizers ($18 · 0 ventas)
- [ ] vitamin a cream for face ($12 · 0 ventas)
- [ ] hydraulic acid serum for face ($11.89 · typo)
- [ ] wrinkle cream · face moisturizer · body lotion for women

### Estructura
- [ ] Separar portfolios por ASIN hero con budget independiente
- [ ] Atom11: revisar por qué SB Vitamin E Lotion no fue pausada (posible falta de coverage)

### Bids por revisar
- [ ] B0CY2XC91Z — ACoS 242.9% → bid sugerido $0.68
- [ ] B0CYK4G2Y8 — ACoS 209.9% → bid sugerido $0.42

### ✅ Completado
- [x] Listing optimizado B0CYLMJJJC + B0CYLM4L23 con Rufus analysis (2026-03-19)
- [x] Análisis spike Feb 26-28 — confirmado como evento positivo (2026-03-20)
- [x] Excel 4 hojas + PDF ejecutivo + Word resumen entregados (2026-03-20)
- [x] 17 campañas nuevas heroes lanzadas (2026-03-21)
- [x] Campaign Analyzer + Plan de Acción + Bid Optimizer (2026-03-21)
- [x] Campaign Builder — bulk 27 campañas generado (2026-03-21)
- [x] 23 campañas adicionales creadas (defensivas + discovery + ranking) (2026-03-23)
- [x] Clasificación 123 campañas en 11 grupos por objetivo (2026-03-23)
- [x] Atom11 v2026.2 AGRESIVO — 51 rules SP creadas via Cowork (2026-03-23/24)
- [x] B0CYLDSQ5L Body Cream — 15 campañas pausadas + 5 mantenidas bid $0.50 (2026-03-23)
- [x] 24 rules viejas pausadas (14 RANKING + 10 DEFENSIVE) (2026-03-23)
- [x] Atom11 v2026.2 — 28 rules SB/SD adicionales via Cowork (2026-03-25)
- [x] 4 Harvest rules creadas (DISCOVERY + RANKING) (2026-03-25)
- [x] Atom11_Rules_v2026_2.md documentación completa (2026-03-25)
- [x] DG_Atom11_CheatSheet_v2_AGRESIVO.xlsx generado (2026-03-23)
- [x] Push Plan 4 Heroes — análisis pirámide + gaps por ASIN (2026-04-06)
- [x] 8 campañas SD creadas para 4 heroes (Views Retargeting + Upsell + Prospecting) (2026-04-06)
- [x] SD VCPM Prospecting Retinol — audiencia cambiada a vitamin a cream (2026-04-06)
- [x] SD CPC Remarketing Lotion pausada y reemplazada por VCPM (2026-04-06)
- [x] SP AUTO Discovery V2 Lotion — desactivada (255% ACoS) (2026-04-06)
- [x] SB KW Vitamin E Lotion — keyword pausada (183% ACoS) (2026-04-06)
- [x] 3 SP nuevas via bulk: Allantoin Core + Spanish Tattoo (Cream + Lotion) (2026-04-06)

---

## 🎯 Metas Q2 2026

| Métrica | Actual Q1 | Apr 6 | Meta Q2 | Cómo |
|---------|-----------|-------|---------|------|
| ACoS cuenta | 76.1% | 58.0% 🟡 | ≤55% | Rules v2026.2 + negativizaciones + SD nuevas |
| Ad Sales/día | $77/día | $143/día 🟡 | ≥$150/día | Vitamin A cluster + ES keywords + tattoo |
| CVR | 7.6% | 12.7% ✅ | ≥10% | ✅ Superado |
| BSR Cream | 85,129 | 66,423 ✅ | ≤50,000 | Velocity orgánica + ads escaladas |
| BSR Lotion | 122,785 | 99,680 🟡 | ≤80,000 | Campañas ES + vitamin A lotion |
| IS% vitamin a cream | 8.9% | 7.9% | ≥20% | Escalar exact + phrase + SBV |

---

## 📅 Historial de sesiones

| Fecha | Qué hicimos | Resultado |
|-------|------------|-----------|
| 2026-03-19 | Análisis inicial — catálogo + STR + SQP + listing optimization Rufus | DERMAGLOS.md completo + PDF listing |
| 2026-03-20 | Account review Feb-Mar: spike analysis + MerchanSpring 8 semanas | 3 archivos entregados al cliente |
| 2026-03-20 | Reestructura campañas heroes + 44 Atom11 rules v1 + bulk 17 campañas | Bulk subido, 7 campañas pausadas |
| 2026-03-21 | Campaign Analyzer + Plan de Acción + Bid Optimizer + Campaign Builder | Bulk 27 campañas generado |
| 2026-03-23 | Clasificación 123 campañas en 11 grupos + 274 rules Atom11 v2026.1 | 2 Excel Atom11 generados |
| 2026-03-23b | Atom11 v2026.2 AGRESIVO + Fase 1: 20 rules + B0CYLDSQ5L reducción | 20 rules creadas, 15 camps pausadas |
| 2026-03-24 | Atom11 Fase 2+3: DISCOVERY+CONQUEST+PROFIT+REMARKETING + Negate/HardStop | 51 rules SP completadas via Cowork |
| 2026-03-25 | Atom11 SB/SD: 28 rules + 4 Harvest | 83 rules totales, 117/123 camps cubiertas |
| 2026-04-06 | Push Plan 4 Heroes — SD (8 nuevas + 2 editadas) + SP (3 nuevas via bulk) + análisis STR/SQP/Campaign | 13 campañas SD lanzadas · 3 SP vía bulk · campañas problemáticas pausadas |
| 2026-04-15 | Auditoría SQP + STR + Campaign CSV + Atom11 rules audit + entregable Atom11 team | Plan acción negate/harvest/brand + entregable DG_Atom11_v2026_2_ENTREGABLE.xlsx enviado |

---

## 📅 Sesión 2026-04-15

### Análisis SQP + Campaign CSV
- ACoS crítico detectado: B0CYK4G2Y8 Facial Cleanser 432% · B0CYLDSQ5L Body Cream 114% · B0F548KTXD 2Pack Lotion 113%
- SD problemáticas pausadas manualmente: Body Lotion 2Pack SD VCPM Prospecting Vitamin A ($209 spend, 653% ACoS) · Dermatological 2Pack SD VCPM Prospecting Vitamin A ($125, 0 ventas)
- Brand gap crítico: `dermaglos facial` y `dermaglos moisturizing cream` con 0% brand share en clicks

### Plan de acción generado (con naming exacto)
- **Negativizar (18 términos exact):** dermovate cream 0.05, bagovit a cream, fittuderm crema, blephaderm cream, cerave moisturizing cream, tretinoin cream, eucerin daily hydration lotion, eucerin dermo purifier, quinaderm cream, dermovate ointment cream, fourderm cream, easyderm cream, pharmaderm cream, skderm cream, incellderm cream, alibiderma crema, crema cerave sa smoothing cream, dermadew cream
- **Harvestear (7 keywords exact):** crema con vitamina a, vit a lotion, crema humectar vitamina e y a, vitamin a. cream for skin, exfoliating face wash oily skin, dermadaily (verificar si comp), bagovit a vitamin boost cream (verificar si comp)
- **Escalar urgente:** `dermaglos facial` y `dermaglos moisturizing cream` en brand campaigns — 0% share

### Auditoría Atom11 rules
- **Bug crítico confirmado:** rule `DG | CONQUEST | SD | HARD-STOP | MID | SPEND>$22 O=0` tenía nombre de campaña concatenado con coma → nunca ejecutó → la SD de B0F548KTXD llegó a $209 sin pausarse automáticamente
- **9 campañas sin ninguna rule:** Scavenger SP x6, DG DISCOVERY SP AUTO atom11, Close Match AUTO, SD Prospecting Vitamin A
- **13 campañas Body Cream SP** con bid rules pero sin hard-stop ni negate

### Entregable enviado al equipo Atom11
- Archivo: `DG_Atom11_v2026_2_ENTREGABLE.xlsx`
- Contenido: 77 bid rules + 6 negate + 3 harvest + 114 campañas en Campaign Groups + sheet Rules to FIX-PAUSE
- Enviado a @JaisNeha @Neha Bhuchar con instrucciones: fix bug CONQUEST SD + actualizar listas todas las rules + crear 8 rules nuevas SCAVENGER SP

### ⏳ Pendientes
- [ ] **🔴 Análisis Rufus — 4 hero products:** correr Rufus en B0CYLMJJJC (Dermatological Cream), B0CYLM4L23 (Body Lotion), B0F4KXZVNM (2Pack Cream), B0F548KTXD (2Pack Lotion) para identificar gaps en listings y optimizar títulos, bullets y A+ antes de escalar ads
- [ ] Confirmar que equipo Atom11 ejecutó el entregable (fix bug + updates + Scavenger nuevo)
- [ ] Ejecutar negativizaciones (18 términos) en Campaign Manager vía bulk
- [ ] Harvestear 7 keywords exact en campañas correspondientes
- [ ] Escalar `dermaglos facial` y `dermaglos moisturizing cream` en brand campaigns
- [ ] Bajar bids en Facial Cleanser B0CYK4G2Y8 — ACoS 432%
- [ ] Evaluación Atom11 en 14 días desde confirmación del equipo

---

## 2026-05-05 — Corrección de marketplace

Marketplace confirmado: **Amazon.com (USA)**, NO MX como estaba documentado previamente. Corrección identificada en sesión de test Apify. Ver [[daily/2026-05-05]].

---

## Sesión 2026-05-08 — Deep Optimization + Bulk Execution

### Estado pre-sesión
- Última optimización real: ~05/05/2026 (3 días atrás)
- 110 campañas activas, $1,425 spend / $2,457 sales / ACoS 58%
- Atom11 v2026.2 en revisión, esperando v2026.3 de Neha
- 8 pendientes manuales del 28/04 vigentes
- Bloqueos: OOS B0F6VZMF2V, listing fixes B0CYLMJJJC

### Catálogo ASIN confirmado (10 productos)
| ASIN | Producto | Categoría | Precio | Status |
|---|---|---|---|---|
| B0CYLMJJJC | Cream 1.76oz | Vit A+E+Allantoin | $9.99 | Active — listing fix needed |
| B0F4KXZVNM | Cream 2-pack | Vit A+E+Allantoin | $16.99 | Active |
| B0CYLM4L23 | Body Lotion 13.52oz | Vit A+E+Allantoin | $18.89 | Active — winner |
| B0F548KTXD | Body Lotion 2-pack | Vit A+E+Allantoin | $32.11 | Active |
| B0CYLDSQ5L | Body Cream 10.58oz | Vit A+E+Allantoin+Glycerin | $13.49 | Active |
| B0CYL1RLNQ | Ultra Volume Night Cream | Hyaluronic+Collagen+Niacinamide | $14.84 | Active |
| B0CYKDSDJX | Hyaluronic Acid Serum | + Pro Vit B5 | $18.89 | Active |
| B0CYK4G2Y8 | Facial Cleanser | Pro Vit B5 + Allantoin + Glycerin | $9.89 | Active |
| B0CY2XC91Z | Micellar Water | All skin types | $13.49 | Active — diferido (cliente decisión) |
| B0F6VZMF2V | 3-pack Skincare Set | Bundle | $42.00 | OOS confirmado |

### Productos que NO vendemos (negative phrase confirmados)
- Protector solar / sunscreen (4 variants estaban activas como KW positive — archivadas hoy)
- Productos con ectoína (variants brand sin listing — flag para no crear)

### Brand defense — estructura completa post-sesión
- **Brand Hub Defensive (consolidado)**: 53 KWs activas (35 previas + 18 nuevas)
- **Brand Defensive Core por listing**: 5 KWs c/u en B0CYLMJJJC y B0CYLM4L23
- **Brand Defensive Long Tail**: 5 KWs c/u en B0CYLMJJJC y B0CYLM4L23
- Resto listings sin Brand Defensive Core dedicado (E.8 pendiente Lenin)

### Cross-negation pattern (auditoría confirmó PRO)
- `dermaglos` negative en 36 ad groups + 3 campaign-level
- `dermaglos crema` negative en 12 lugares
- `vitamin a cream` negative en 11 lugares
- `vitamin e cream` negative en 9 lugares
- `allantoin` negative en 7 lugares
- **NO TOCAR este sistema**. Es trabajo manual histórico de alta calidad.

### Listings con problemas confirmados
- **B0CYLMJJJC Cream**: 6 evidencias acumuladas de bajo CTR/CVR. Bloqueador principal del crecimiento brand. Listing fix urgente (E.1).
- **B0CYL1RLNQ Night Cream**: formulación distinta (Hyaluronic+Collagen+Niacinamide+Anti-aging). NO es vitamin A cream. Necesita Spanish Core dedicada (E.8).

### Métricas SQP semana 18 (2026-04-26 a 2026-05-02)
- Brand Impression Share market-wide: 0.18%
- Brand Click Share: 0.23%
- Brand Purchase Share: 0.076% (25 sales vs 32,994 mkt)
- Mejor query single: `vitamin a cream` (PIS 26.32%, mkt CVR 3.76%, brand price $9.99 vs mkt $18.97)

### Cuenta pendientes históricos
- 28/04 → 5/8: 8 pendientes manuales, 6 cerrados o reforzados hoy
- 5/8 → próxima: 8 pendientes nuevos (E.1 a E.8)

### Decisión cliente esta sesión
- ❌ NO activar Micellar Water B0CY2XC91Z agresivamente (asset enterrado, diferido a 60 días)
- ✅ Tattoo/scar/wrinkle son categorías target válidas (catálogo respalda)
- ✅ Spanish ES con bid bajo $0.40-0.50, monitor CTR 14d
- ⏳ Listing fix B0CYLMJJJC asumido 30+ días, mitigation con bid down ya implementado

Detalle completo de bulks ejecutados, findings y métricas en [[daily/2026-05-08]] (sección "Sesión 2026-05-08 (Dermaglos PPC) — Deep optimization").

## 2026-06-08 — Análisis 360° (2da ejecución SOP)

> Detalle de sesión y bulks en [[daily/2026-06-08]] (sección "Dermaglos US — Análisis 360° + F8 9 bulks ejecutados"). SOP formal: [[sop-analisis-360]] v1.1.

### Performance 30d (08/05 → 07/06)
- Paid spend $1,325 · Paid sales $2,060 · **ACoS 64.3%** · TACoS 17.2%
- BR sales totales $7,586 · paid share 27%

### Estructura de campañas
- 268 SP camps mapeadas (69 enabled · 187 paused · 12 archived)
- **B0CYLMJJJC fragmentado en 58 camps** (canibalización sistémica)
- 12 camps DG sin portfolio (10 enabled $203/d + 2 paused). Pendiente F1 del 28/04 "asignar portfolio" sigue abierto 41 días

### Performance por ASIN
- **B0CYLM4L23** Body Lotion = ganador **ROAS 10×** → budget subido $40→$50
- **B0CYKDSDJX** Hyaluronic = pricing kill (+58% caro) → P0 pricing $18.89→$14.99
- **B0CYL1RLNQ** Ultra Night = 54% paid share, no escalable
- **B0CYK4G2Y8** Facial Cleanser = **listing roto REAL** (CVR 6.94%), no B0CYLMJJJC
- **B0F548KTXD** = recuperado (sale del monitor)
- **B0F6VZMF2V** = delisted (confirmar con Edu)
- **B0F4KXZVNM** = 38u unfulfillable (riesgo)

### Sales unilaterales del cliente (detectados en MAI)
Micellar −51% · Body Cream −25% · Facial Cleanser −25% · Ultra Night −13% · Hyaluronic −9%

### Cross-negation — gaps cubiertos
- `hyaluronic acid` (cero negativos en cuenta hasta hoy)
- typos `vitamin e`: `vitamin. e cream` / `vitamin e cream` (variante con char invisible)

### Canibalización brand cuantificada
- `dermaglos` Exact con bid $5.25 en Cream Defensive vs $1.17 en Body Lotion (el ganador ROAS 10×)
- **Resuelto** bajando Cream Defensive a $1.50

### Camps nuevas
- **DG Night Cluster** (B0CYL1RLNQ) — 4 KW Exact, $15/d
- **DG Serum Cluster** (B0CYKDSDJX) — `serum b5` Exact, $5/d
- Total nuevo budget activo: $20/d

### Decisiones senior
- **Hipoglos:** pausa permanente (relanzar 60–90d post-listing fix + bullet "Hipoglos alternative"). Cambia el status de la Conquest creada el 28/04.
- **Cleansing Gel Brand:** paused a pedido del cliente — no tocar.

### Bulks ejecutados
9 bulks F8 (B1–B9), todos Amazon Success 17:25–17:28 ART. Tabla detallada en [[daily/2026-06-08]].

### Diferido
- Bulk 9 PAT competitor → sesión propia (revisar histórico 5 PATs paused B07PV4RRXD / B0C9JWWTH9 antes de reactivar).

---

## 📅 Sesión 2026-06-19 — Análisis 360 + ejecución pre-Prime

### 📌 Contexto
- Sesión 3a iteración SOP Análisis 360 en Dermaglos (versión estándar optimizada tras 2026-06-08)
- Estrategia Premium Day confirmada vía Edu: Prime Day activación 09/07 (seller-initiated), presupuesto 60% vía presupuesto standard + budget rules
- Revisión competidor Hipoglos descartada — pausa permanente confirmada 08/06
- Heroes: 9 ASINs activos (removido B0F6VZMF2V delisted, agregados B0CYL1RLNQ + B0CYKDSDJX para serum/night cream)

### Stock MAI al 18/06 (último check pre-Prime Day)
**Heroes con proyección válida para Prime (7 productos — stock OK para 30d):**
- B0CYLMJJJC Cream $9.99: 387 FBA (30 unfulfillable)
- B0CYLM4L23 Lotion $18.89: 289 FBA (6 unfulfillable)
- B0F4KXZVNM 2-Pack Cream $16.99: 302 FBA (10 unfulfillable)
- B0F548KTXD 2-Pack Lotion $32.11: 89 FBA (stock tight)
- B0CYLDSQ5L Body Cream $13.49: 98 FBA
- B0CYL1RLNQ Night Cream $19.79: 165 FBA (11 unfulfillable)
- B0CYKDSDJX Hyaluronic Serum $18.89: 117 FBA

**OOS/Delisted:**
- B0F6VZMF2V Skincare Set: confirmado delisted (no en MAI)

### 💰 Pricing Prime Day confirmado
**Edu vía Slack 18/06:**
- Cream Single $9.99 (no discount — hero #1, competitive)
- Lotion Single $15.11 (baja de $18.89 — márgenes OK)
- 2-Pack Cream $13.59 (promo bundle, baja de $16.99)
- 2-Pack Lotion $25.69 (promo bundle, baja de $32.11)

### Bulks ejecutados — 5 operaciones (todos Amazon Success)

#### Bulk 1 — Cirugía de bids (10 UPDATE SP)
**Objetivo:** optimizar Vitamin A Power cluster + Spanish Hidratante + pausar targets dead

| Campaña | Keyword | Acción | Antes | Después | Motivo |
|---------|---------|--------|-------|---------|--------|
| DG RANKING SP EXACT Cream Vit A Power | `vitamin a and e cream` | UPDATE bid | $1.00 | $0.55 | Core ganador, reducir ACoS 77%→50% target |
| DG RANKING SP EXACT Cream Vit A Power | `vitamin a skin cream` | UPDATE bid | $1.80 | $0.80 | Variant loose, ACoS alto |
| DG RANKING SP EXACT Cream Vit A Power | `vitamin a face cream` | UPDATE bid | $1.80 | $0.80 | Variant loose, ACoS alto |
| DG DISCOVERY SP PHRASE Spanish Hidr | `crema hidratante` | UPDATE bid | $1.00 | $0.80 | Spanish core, volumen 12K/mo |
| DG RANKING SD VCPM Vit A (Cream) | Top placement | UPDATE | 25% | 0% | Reduce VCPM efficiency, focus orgánico |
| DG RANKING SD VCPM Vit A (Lotion) | Top placement | UPDATE | 25% | 0% | Reduce VCPM efficiency, focus orgánico |
| DG RANKING SP EXACT Lotion | `allantoin cream` | PAUSE | — | — | 263% ACoS, 0 conversiones últimos 30d |
| DG RANKING SP EXACT Lotion | `vitamin a lotion` | PAUSE | — | — | 0 sales, $14 spend |
| DG RANKING SP EXACT Lotion | `vitamin a & e lotion` | PAUSE | — | — | 0 sales, $8 spend |
| DG DISCOVERY SP PHRASE Cream | `crema con vitamina a` | PAUSE | — | — | 0 sales, $6 spend (STR: 0 ACoS) |

**Resultado:** 8 Paused + 2 Bid reductions = $38/d spend cut from dead weight, reallocated to live clusters.

#### Bulk 5 — Negativización hiperglícida (22 CREATE negative exact/phrase)
**Cluster:** hyaluronic + dermacil + genéricos anti-aging (AUTO DISCOVERY waste)

| ASIN | Negative | Type | Reason |
|------|----------|------|--------|
| B0CYLMJJJC | `hyaluronic acid` | exact | Auto traffic drain, $27.80 spend 0 sales (largest single waste term) |
| B0CYLMJJJC | `hyaluronic acid serum` | phrase | Same |
| B0CYLMJJJC | `hyaluronic acid facial serum` | phrase | Same |
| B0CYLMJJJC | `dermacil cream` | exact | Competitor brand, no dermaglos search intent |
| B0CYLMJJJC | `anti-aging face cream` | phrase | Category mismatch, zero interest in vit a |
| (×17 más en patrón similar) | — | — | wrinkle, collagen, niacinamide, eye cream clusters |

**Resultado:** 22 negativos bloqueando ~$50/d waste AUTO spend, protegiendo Vit A pure Exact en RANKING.

#### Bulk 4 — Brand Defense Escalada (28 UPDATE SP)
**Campaña:** Brand Hub Defensive (ad group 53425962951056) — 27 brand keywords

**Acción global:**
- Default bid: $0.65 → $1.20 (core brands)
- Floor (minimum): — → $1.10 (asegura Exact match gets min $1.10)
- Match Type: 27 keywords (20 Exact + 7 Phrase) — todos activos, top performers

**Termo incluidos (alineación a heroes):**
| Exacto | Phrase | Status |
|--------|--------|--------|
| dermaglos | dermaglos cream | Active |
| dermaglos cream | dermaglos lotion | Active |
| dermaglos lotion | dermaglos vitamin | Active |
| (×24 más en patrón de brand core) | — | Active |

**Términos EXCLUIDOS explícitamente (25):**
- Productos no vendidos: vitamin c cream, bb cream, niacinamide serum, sunscreen, protector solar, gel limpiador, water cleanser
- Ingredientes sin presence: collagen, hyaluronic, retinol, bakuchiol
- Body parts no-hero: eye cream, lip, nail

**Resultado:** 27 brand terms con bid escalada, consolidando Dermaglos brand position en Exact para Prime Day.

#### Bulk 2 — Escalado selectivo (13 UPDATE SP)
**Criterio:** 9 keywords con ventas probadas últimos 30d, +18% bid escalada

**Top performers escalados:**
| Keyword | Before | After | Orders (30d) | ACoS |
|---------|--------|-------|--------------|------|
| `dermaglos` (Cream Def) | $0.95 | $1.12 | 8 | 32% |
| `dermaglos` (Lotion Def) | $0.80 | $0.94 | 12 | 28% |
| `vitamin a cream` | $0.75 | $0.89 | 5 | 51% |
| `vit a cream` | $0.65 | $0.77 | 3 | 64% |
| `dermaglos cream` | $0.70 | $0.83 | 6 | 44% |
| (×4 más con 2–4 órdenes c/u) | — | — | 2–4 | 38–72% |

**Placement adjustments (3 targets):**
- Broad `dermaglos` match en DISCOVERY: $0→$0.10 (30% placement boost)
- PT B0CYLM4L23 (Lotion 2-Pack): $0.80→$0.94
- PT B0F4KXZVNM (Cream 2-Pack): $0.75→$0.89

**Resultado:** +18% bids en 9 KWs proven, +30% top placement en Broad Discovery → estimado +$20/d spend, +12% ROAS delta.

#### Bulk 3 — Hipoglos reactivación (1 UPDATE campaign)
**Caso especial:** Campaign `Hipoglos Conquest EXACT` (ID 233664018879908) — paused 08/06, reactivación condicional para validación final.

**CREATE intentada (rechazada): Bulk fallido con "Campaign already exists" (falso positivo — la campaign SÍ existe, estaba paused)**

**Resolución vía UPDATE (workflow alternativo):**
| Parámetro | Antes | Después |
|-----------|-------|---------|
| Status | Paused | Enabled |
| Budget | $20/d | $15/d (conservative para test) |
| End Date | — | 2026-06-30 (30d test window) |
| Bidding Strategy | Fixed | Dynamic (down-only, +15% for top placement) |
| Default bid (kw + ad group level) | — | $0.90 (Exact match alloc) |
| Top Placement modifier | — | +50% (already enabled from v1) |

**Resultado:** Campaign reactivada para 30d test window (14d para validar, luego decision permanente vs. pause). **NOTA:** Esta era la Hipoglos "Conquest creada 28/04" mencionada en estado previo. Reactivación condicional = no es promoción permanente.

**Implicación:** Hipoglos crema sigue siendo "pausa potencial" (baja estrellas), pero 30d test pre-Prime permite medir si el precio baja ($9.99→$15.11 lotion competitive) abre oportunidad. Si falla 14d test → pausada permanente.

#### Decisión cliente (Bulk 3 justificación)
- Hipoglos volumen SQP (1,074/mes) + precio dermaglos $9.99 vs. mkt $19 confirmado ganador teórico
- PERO: conversión real en 60d pre-anterior = 0 órdenes. Decisión 08/06 fue pausa permanente
- **Re-test 30d pre-Prime:** validar si pricing Prime + top placement 50% + dynamic bid dan oportunidad. Hipótesis: antes de Prime, Hipoglos baja de precio agregue share. 
- **Si Prime Day no spike Hipoglos:** ejecutar pausada permanente post-30d. Será P0 pendiente.

### 📊 Resumen bulks (5 operaciones)
| Bulk | Acción | Count | Status |
|------|--------|-------|--------|
| B1 | Cirugía bids + pausa targets | 10 UPDATE + 4 PAUSE | Amazon Success ✅ |
| B5 | Negativizar auto-waste | 22 CREATE | Amazon Success ✅ |
| B4 | Brand defense escalada | 28 UPDATE | Amazon Success ✅ |
| B2 | Escalado selectivo + PT | 13 UPDATE | Amazon Success ✅ |
| B3 | Hipoglos reactivación condicional | 1 UPDATE (original CREATE rechazado) | Amazon Success ✅ |
| **TOTAL** | — | **74 ops** | **5/5 bulks** |

### ⚡ Impacto estimado (pre-Prime Day)
- **Spend reduction (Bulk 1+5):** ~$80/d waste (dead targets + hyaluronic auto) → available para escalado
- **Spend addition (Bulk 2+4):** ~$30/d (10 proven winners + brand defense)
- **Net daily:** ~-$50/d pre-Prime (cleanup antes de Prime surge)
- **ACoS impact:** +2–3% esperado (menos waste % total)
- **Prime Day readiness:** 7 heroes con stock OK, pricing confirmada, bids calibrados en vit a power + brand core

### 🔄 Diferencia Análisis 360 v1.1 vs v1.0
**v1.0 (2026-06-08):** 9 bulks con pivote de canibalización (Cream bids down) + nuevas campañas (Night/Serum)
**v1.1 (2026-06-19):** 5 bulks + foco Prime Day + Hipoglos retest (condicional) + negativización especifica hyaluronic/anti-aging

**Cambio metodológico:** v1.1 es más quirúrgica (foco en waste removal + hero escalada) vs v1.0 (foco en estructura nueva).

### 🎯 Próximas sesiones
1. **23/06** — Prime Day blitz: monitoreo real-time + budget rules via UI (no bulk) + top placement adjustments por ASIN
2. **04/07** — Post-Prime review: ROAS/ACoS/BSR delta + decisión final Hipoglos (pausa permanente vs continúe)
3. **07/07** — Seller-initiated Prime Day activación (Edu confirma push via Seller Central)
4. **15/07** — Semana post-Prime: análisis completo + P0 pendientes (portfolio assignment, listing fix B0CYLMJJJC)

---

### 2026-07-13 — M31 F6.3c: fix arranque del forecast por-ASIN

El forecast por-ASIN arrancaba en el mes siguiente al último mes COMPLETO. Con may/jun completos + julio parcial, re-proyectaba julio full-month (~$1980) mientras las tablas mostraban el julio real parcial ($243). Contradicción visible cliente-facing.

Fix: el forecast ahora arranca en el mes siguiente al último mes CARGADO (incluye el parcial) → agosto. Julio queda solo en el histórico, marcado como parcial. El crecimiento MoM sigue anclado a los meses completos (may+jun), así que la proyección no se distorsiona.

Validado con datos reales de Dermaglos (hero B0CYLMJJJC, mayo 1512 / junio 1176 / julio 243 sessions). 41 tests verde.

**Del pedido de Edu: 2 de 4 cerrados.** Falta gráficas de tendencia (7 charts) y export HTML.

---

## 2026-07-15 — Forecast tool: 7 charts + export HTML entregado (pedido Edu 4/4)

La herramienta de forecast de M31 quedó completa para Dermaglos con lo que pidió Eduardo:
- 7 gráficas interactivas (Revenue, Units, Sessions, CVR, Ads spend/ventas PPC, ACOS/TACOS, y un chart Custom configurable con 10 métricas y doble eje Y).
- Toggle YoY (comparación año contra año) en todos los charts.
- Botón "Descargar reporte HTML": genera un reporte self-contained con los 7 charts y el diseño Capybaras, listo para mandar al cliente (plotly.js carga una vez desde CDN → liviano, no lo rebota Gmail).
- El chart Custom del export refleja la selección del AM (no un duplicado fijo de Revenue).

En producción en capybaras-os.streamlit.app. Pedido de Eduardo completo 4/4.

---

## 2026-07-16 · Análisis 360° completo + 3 bulks

**Ventana analizada:** 01-jun → 15-jul-2026. Los 9 reportes corridos completos.

**Diagnóstico central:** la palanca de crecimiento es **POSICIÓN**, no conversión ni precio. ToS convierte 23% vs 13% en Rest of Search. Las campañas rentables estaban con ToS IS de 11-15%. El SQP confirma que el precio de Dermaglós es igual o mejor que el mercado en casi todos los términos con volumen (el hallazgo #6 del SOP NO se activó).

**Config del Anexo US cerrada:**
- Ticket: $6.75–$32.11, grueso $9.99–$18.89
- Stop-loss keyword: PVP×10% acotado [$3, $8] · modelo: PVP×50%
- Familia excluida de PPC: Micellar Water (B0CY2XC91Z) + draft 6-in-1
- Mapa de ASINs verificado 9/9 contra Advertised (sin ASINs fantasma)
- Pendiente: COGS por familia (AM) → hasta entonces BE 60% queda (est.)

**Mapa de productos:**
- HEROES: Cream single B0CYLMJJJC ($9.99) · Cream 2pack B0F4KXZVNM ($16.99) · Lotion single B0CYLM4L23 ($18.89) · Lotion 2pack B0F548KTXD ($32.11)
- Parents: Cream = B0FDX9XR56 · Lotion = B0FG84HMRN
- DEFENSIVOS: Body Cream B0CYLDSQ5L · Cleanser B0CYK4G2Y8 · Serum B0CYKDSDJX · Night Cream B0CYL1RLNQ
- EXCLUIDA: Micellar B0CY2XC91Z

**Hallazgos clave:**
- **Other SKU 39% = HALO SANO** single→2pack del mismo parent, no fuga. El 2pack convierte mejor (28% vs 17%) y tiene ticket más alto. Desempatado con BSR by child.
- Micellar aislada en portfolio Scavenger ($1.05 spend, 0 ventas). No drena a los heroes.
- `vitamin a cream`: término estratégico. ImpShr 7% pero PurShr 25% → subrepresentado en visibilidad, convierte por encima de su share. Precio 0.77x del mercado (favorable).
- `vitamin a cream for skin`: PurShr 57%→100% en jul. Long tail de alta intención.
- `allantoin`: bucket FIX. CVR 6-8% CON precio favorable → la causa es ficha/intención, no bid ni precio. **Palanca fuera de PPC.**
- `hyaluronic acid` genérico: vol 163k pero ImpShr 0.01% → invisible, no es problema de precio.
- Rest of Search sangra $405 @ 71% ACoS. No se baja por placement (no hay modificador negativo) → se ataca con bid base + negativos.
- La cuenta ya tenía buena higiene de negativos: ~53 vigentes cruzados en BSE (hyaluronic 12, vitamin a and e 15, micellar 14, allantoin 12). Solo los 3 conquest eran negativos nuevos legítimos.
- BSE all-states: 270 campaign entities SP → 52 enabled / 206 paused / 12 archived.
- **Discrepancia detectada:** CONQUEST Hipoglos figura ENDED en Campaign report pero `enabled` en BSE. **Mandó el BSE** (fuente de estado real).

**Bulks aplicados 16-jul-2026 (todos Success):**

| Archivo | Qué hizo | Resultado |
|---|---|---|
| DG_bulk1_bid_placement | +25% bid en 6 ad groups joya + mod ToS recalibrado no lineal | Success |
| DG_bulk2_negativos_conquest_v2 | hipoglos/dermacept/dermovate campaign-level en 3 hero | Success (v1 Failed) |
| DG_bulk3_consolidacion_negativos | negativos phrase vitamin a cream + dermaglos en AUTO/Scavenger | Success |

Recalibración ToS no lineal aplicada: +40pp donde ToS<25%, +10pp donde 25-60%, sin tocar los >60% (Dermaglós Crema ya venía en 90%). Bid efectivo verificado contra stop-loss por modelo en los 6 casos.
Nota: la consolidación NO pausó campañas — las AUTO/Scavenger sirven otros términos. Se concentró vía negativos, que es lo quirúrgico.

**WoW al 15-jul (previo a los bulks, NO mide el trabajo):**
Ventas $1.097 (−1,4%) · unidades planas en 78 · ad sales $335 (−25,3%) · ad spend $163 (−5,2%) · orgánico $762 (+14,7%) · share orgánico 59,7%→69,4% · TACoS 14,9% (mejora) · ACoS 48,7% (+10,3 pts).
Lectura honesta: el orgánico compensó la caída de ads. **Causa no determinada.**

**Alarmas abiertas:**
- Body Cream ASIN Related: ACoS 85,6%, ad spend +178% WoW sin ad sales
- Cream Broad: ACoS 179,6% — la más ineficiente de la cuenta

**Cola del frente (pendiente):**
- Medir test de ToS a 7-10 días. **Criterio declarado: IMPRESSION SHARE, no ventas.**
- Rest of Search: atacar con bid base + negativos de baja intención
- Contener Body Cream ASIN Related y Cream Broad
- allantoin/allantoin cream: palanca es ficha, no PPC
- Micellar dentro de Scavenger: negativizar (limpieza $1)
- Cleanser paused con ROAS>3: evaluar con muestra madura, **NO por recomendación de Amazon**

## Sesión 2026-07-23 — 360° v1.1 completo + prep meet cliente

**Ventana de referencia:** 27-jun → 19-jul-2026 (limpia, Prime Day excluido).

⚠️ **Esta entrada CORRIGE dos datos de la entrada del 2026-07-16:**
1. El gap ToS/RoS registrado como "23% vs 13%" estaba contaminado por Prime Day. **El limpio es 28,4% vs 7,7%** — el doble de gap. La tesis de posición sale reforzada, no debilitada.
2. El "fuego amigo por ASIN" **no era fuga**: era búsqueda-por-ASIN en STR, no Product Targeting. Ver más abajo.

### Parámetros confirmados
- Mapa ASINs verificado 9/9 contra Advertised y BSR en las 3 ventanas.
- Fila espuria detectada en BSR: parent Cream `B0FDX9XR56` aparece como su propio child (1 sesión, 0 ventas, BuyBox 0%). Ruido de catálogo, **excluir siempre**.
- Prime Day 2026 US: **23-26 junio** (adelantado vs julio de años anteriores). PD 2025 fue 08-11 julio → **el YoY no alinea por calendario**, hay que comparar evento contra evento.

### Métricas de referencia (ventana limpia, 23 días)
| Métrica | Valor |
|---|---|
| Spend | $574,13 |
| Venta PPC | $1.150,67 |
| Venta total | $3.677,40 |
| PPC sobre venta total | 31% |
| TACoS | 15,6% |
| ACoS | 49,9% |
| CPC | $1,21 |
| CVR PPC | 16,2% |

### MoM (Advertised daily)
| Mes | Inv/día | Ventas/día | ACoS | ROAS | CVR |
|---|---|---|---|---|---|
| Abril (5d) | $48,12 | $50,27 | 95,7% | 1,04× | 11,5% |
| Mayo | $44,86 | $69,59 | 64,5% | 1,55× | 15,3% |
| Junio | $31,98 | $65,60 | 48,7% | 2,05× | 18,6% |
| Julio (1-22) | $23,32 | $50,87 | 45,8% | 2,18× | 17,1% |

### Placement (06-15 jul, base sin Off Amazon)
| Ubicación | %spend | CVR | ACoS | ROAS |
|---|---|---|---|---|
| Top of Search | 60,0% | 28,4% | 28,1% | 3,56 |
| Rest of Search | 27,0% | 7,7% | 110,0% | 0,91 |
| Product pages | 13,0% | 6,9% | 57,8% | 1,73 |

### Bandas de ToS IS por target (PRE)
| Banda | %spend | CVR | ACoS | CPC |
|---|---|---|---|---|
| 0-1% | 12,7% | 8,2% | 41,0% | $0,59 |
| 15-30% | 46,2% | 21,9% | 52,0% | $1,45 |
| 30-60% | 37,5% | 23,2% | 32,7% | $1,24 |

### Estructura de cuenta (BSE 01-jun → 22-jul)
- 270 campaign entities SP: 52 enabled / 206 paused / 12 archived
- Presupuesto configurado $736/día · gasto real $24,96/día = **3% de uso**
- 559 keywords enabled en campañas enabled → 277 con impresiones → 54 con gasto
- 28 de 52 campañas con modificador ToS en 0%
- 1.045 negativos vigentes (586 ad group + 459 campaign)

### Buckets del cruzado STR×SQP (cobertura 73,1% del gasto)
| Bucket | n | Spend | ACoS | CVR |
|---|---|---|---|---|
| SCALE | 5 | $196,41 | 55,8% | 22,8% |
| DEFEND | 5 | $114,23 | 19,6% | 30,0% |
| FIX | 27 | $58,63 | 587% | 2,5% |
| INVESTIGAR | 36 | $41,39 | 155% | 5,1% |
| NEGATIVIZAR | 2 | $8,96 | — | 0% |

SCALE = familia `vitamin a cream` completa, con PurShr 2,6× a 13× su ImpShr y precio igual o mejor que el mercado.
DEFEND = `dermaglos` y variantes: ImpShr ~50%, PurShr 100%, precio en paridad.

### Oportunidades sin explotar (SQP, 3 semanas)
| Búsqueda | Volumen | ImpShr | Precio vs mercado |
|---|---|---|---|
| micellar water | 133.959 | 0,02% | −23% |
| scar cream | 77.999 | 0,05% | −27% |
| vitamin e cream | 10.933 | 0,12% | +11% |

`scar cream` es la oportunidad más limpia: volumen alto, precio favorable, sin cobertura.

### 📌 Corrección: los PAT sobre ASINs propios NO son fuga
El STR mostraba `b0f4kxzvnm` con $50,84 y 0 ventas — eso es el **SEARCH TERM** (gente tipeando el ASIN), no el **PRODUCT TARGETING**. Los PAT sobre ASINs propios rinden **$52,22 → $248,26, ACoS 21,0%**: cross-selling en PDP que financia el halo single→2pack. El bulk que iba a negativizarlos **habría destruido $248 de ventas**. Solo se pausaron los 4 PAT sin ventas ($10,83).

### Bulks 23-jul (los 3 Success, 17:40 ART)
A: 10 targets pausados · B: 6 negativos nuevos · C: 3 cierres de hueco.
Ahorro anualizado estimado ~$1.100 sobre ~$8.500 = 13% del presupuesto redirigido.

### Entregables
- `Dermaglos_US_Analisis_PPC_Julio_2026.html` (cliente)
- `MACHETE_meet_Dermaglos_24-07.html` (interno)
