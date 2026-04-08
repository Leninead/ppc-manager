# Prompt para Claude Code — Actualizar MB.md

Abrir el archivo C:\proyectos\ppc-manager\notes\MB.md

Agregar al FINAL del archivo (después del último bloque de historial), ANTES de los pendientes, esta nueva entrada de historial:

---INICIO DEL CONTENIDO A AGREGAR---

### 07/04/2026 — Lanzamiento Non-Branded Women (V-Neck + Crew Neck)

**Research completo ejecutado con PPC Manager:**
- STR 60 días → 2,460 terms, 44 non-branded con ventas (109 orders, $4,296 sales)
- Campaign Analyzer → 62 campañas diagnosticadas, cuenta sana ACoS 10%, $203 waste total
- Helium 10 Cerebro → Reverse ASIN B0F84474KS (V-Neck) + B0F84637MJ (Crew) + 6 competidores
- DataDive → Nicho $4M, 19 competidores, median price $8.99, M&B premium a $40
- Análisis Cruzado STR vs SQP → 1,292 oportunidades, 521 women-relevant
- Cruce Cerebro × STR → keywords priorizadas por volumen + conversión confirmada

**7 campañas non-branded lanzadas (3 capas):**

| Campaña | Tipo | Match | KWs | Budget | Portfolio |
|---------|------|-------|-----|--------|-----------|
| NB RANKING VN A | Exact Ranking | exact | 5 | $10/día | WTV |
| NB RANKING VN B | Exact Ranking | exact | 5 | $10/día | WTV |
| NB RANKING CR A | Exact Ranking | exact | 5 | $10/día | WTC |
| NB DISCOVERY VN A | Phrase Discovery | phrase | 4 | $8/día | WTV |
| NB DISCOVERY CR A | Phrase Discovery | phrase | 4 | $8/día | WTC |
| NB CONQUEST VN A | PAT Competitor | targeting | 4 | $8/día | WTV |
| NB CONQUEST CR A | PAT Competitor | targeting | 4 | $8/día | WTC |

**Inversión:** $72/día (~$2,160/mes) | **Break-even ACoS:** 52% | **Target ACoS:** 30%

**ASINs en los ads (1 child hero por parent):**
- V-Neck → B0F6LDGCDS (M Crimson) — SKU: fvnt_marc_crim_vn-m
- Crew Neck → B0F6LCGH2L (M White) — SKU: fcrt_marc_whit_vn-m

**Top keywords non-branded Capa 1 (validadas por STR):**
- v neck t shirts for women (15 orders, 6.8% ACoS, SV 6,668)
- short sleeve shirts for women (12 orders, 26.0% ACoS, SV 13,710)
- womens t shirts (6 orders, 24.6% ACoS, SV 108,304)
- french fashion t shirts for women (6 orders, 2.3% ACoS)
- womens short sleeve t shirts (5 orders, 5.3% ACoS)
- womens tops (3 orders, 4.9% ACoS, SV 618,038)
- white tshirts shirts for women (3 orders, 6.3% ACoS, SV 41,104)

**Competidores PAT targeteados:**
- VN: True Classic (B0BJZ9GT1J, B0CCT3YV2K), Cotton Basic Women (B0CXJHCVHZ), Trendy Queen (B0CYC56DYP)
- CR: Polo RL (B07GBW8QYP), Gildan (B093121LW9, B0787PB6ZZ), CRZ Yoga (B0DQ3QCCMM)

**Bugs fixeados en PPC Manager:**
- analisis_cruzado.py → NaN check en lambda Tipo Marca/Genérica
- campaign_builder.py → 7 fixes: Campaign ID linkeo, date yyyyMMdd, bid strategy string, 30 columnas Amazon, PAT expression, filas vacías

---FIN DEL CONTENIDO A AGREGAR---

Luego, en la sección de Pendientes, actualizar:

CAMBIAR:
- [ ] **Estrategia Non-Branded Marcy (WTV)** — propuesta enviada a Agustín, esperando aprobación del cliente para ejecutar research (STR + Helium 10 + DataDive) y lanzar campañas nuevas

POR:
- [x] **Estrategia Non-Branded Marcy (WTV + WTC)** — ✅ LANZADA 07/04. 7 campañas, $72/día. Evaluación día 14: 22/04/2026

AGREGAR a pendientes:
- [ ] **22/04 — Evaluación non-branded día 14:** revisar ACoS, orders, impressions de las 7 campañas. Si Exact Ranking funciona → escalar budget. Si Phrase Discovery no convierte → bajar bids 50%. Si PAT Conquest no convierte → pausar.
- [ ] Agregar más childs como ads si el equipo lo decide
- [ ] Mover campañas PAUSAR detectadas: WTC shirts KWS HV ($70.7), WTC Casual tshirts KWS ($86.2), WTV HIGHER PRICED ($24.2), MTC SD REMARKETING PURCHASES ($21.9)
- [ ] Bajar bids campañas REVISAR: WTV shirts KWS HV (ACoS 81.5%), WTC SD REMARKETING VIEWS (78.7%), WTC SBV t shirts KWS HV (108.6%), MTC Cotton tshirts KWS (89.6%)

No tocar ningún otro archivo. Confirmar que el archivo fue escrito y decir cuántas líneas tiene.
