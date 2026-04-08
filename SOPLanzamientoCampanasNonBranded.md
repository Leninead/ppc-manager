# 🦫 SOP — Lanzamiento de Campañas Non-Branded
## Capybaras Agency · Metodología validada con M&B 07/04/2026

---

## Cuándo usar este SOP

Cuando una marca tiene estructura PPC 100% branded/defensive y queremos expandir a non-branded para capturar tráfico genérico de categoría. Aplica cuando:

- ACoS actual < break-even ACoS (hay margen para invertir)
- Las campañas Broad/Auto ya están capturando conversiones non-branded en el STR
- El cliente aprobó inversión incremental

---

## Archivos necesarios ANTES de arrancar

| # | Archivo | Dónde bajarlo | Período |
|---|---------|--------------|---------|
| 1 | STR (Search Term Report) | Amazon Ads → Reports → SP Search Term | 60 días |
| 2 | Campaign CSV | Campaign Manager → Export (todas las métricas) | Mismo período |
| 3 | SQP (Search Query Performance) | Brand Analytics → Search Query Performance | Último mes |
| 4 | Helium 10 Cerebro | Cerebro → ASIN parent + competidores | Current |
| 5 | DataDive MKL | DataDive → Niche → Keywords (si hay corrida) | Última disponible |

**Filtros para Cerebro:** Search Volume Min 100, Word Count Min 2. Exportar todo — el filtrado fino se hace en el PPC Manager.

**Competidores para Cerebro:** 2-3 ASINs de la misma categoría que NO sean de la marca. Buscar en Amazon la keyword principal del nicho y tomar los top 3 orgánicos.

---

## PASO 1 — STR Analysis (módulo Search Term Report)

**Objetivo:** Identificar keywords non-branded que ya convirtieron.

**Configuración:**
- Target ACoS: el de la cuenta o el target para non-branded
- Brand terms: todas las variaciones de la marca (separadas por coma)
- Precio promedio: precio real del producto
- Clicks mínimos para CVR: 15

**Acciones:**
1. Tab "Vista General" → revisar KPIs generales, distribución Brand vs Generic vs Long-tail
2. Tab "Harvest Candidates" → subir Campaign CSV para anti-canibalización
3. Filtrar vista "Winners" → scrollear pasando los branded → anotar los non-branded con 2+ orders
4. Tab "Sin ventas" → identificar non-branded con spend alto y 0 ventas (candidatos a negativizar)
5. Tab "Por Campaña" → ver qué campañas Broad/Auto generan las conversiones non-branded

**Output:** Lista de keywords non-branded validadas por ventas reales + ACoS.

---

## PASO 2 — Campaign Analyzer (módulo Bulk Campañas)

**Objetivo:** Diagnosticar estado actual de las campañas antes de agregar nuevas.

**Configuración:**
- Target ACoS: el de la cuenta
- Spend mínimo para pausar: $20
- Mínimo órdenes para escalar: 2

**Acciones:**
1. Identificar campañas 🔴 PAUSAR (spend sin ventas) → pausar antes de lanzar
2. Identificar campañas 🟡 REVISAR (ACoS > target × 2) → bajar bids
3. Identificar campañas ✅ ESCALAR → oportunidad de subir budget
4. Confirmar qué campañas Broad/Auto son la fuente del harvest non-branded
5. Exportar diagnóstico

**Output:** Campañas limpias + lista de acciones de housekeeping.

---

## PASO 3 — Helium 10 Analyzer (módulo Helium 10)

**Objetivo:** Encontrar keywords de alto volumen que los competidores rankean y nosotros no.

**Acciones:**
1. Tab "Cerebro Reverse ASIN" → subir Cerebro del parent
2. Filtrar SV > 100, revisar columna "Oportunidad PPC" (orgánico sin ads)
3. Identificar keywords women/product-relevant con alto SV
4. Cruzar mentalmente con la lista del STR → las que aparecen en AMBOS = prioridad máxima

**Output:** Keywords de alto volumen del Cerebro + señal de cuáles ya convirtieron en STR.

---

## PASO 4 — Análisis Cruzado STR vs SQP

**Objetivo:** Detectar gaps entre lo que pagamos (STR) y lo que busca el mercado (SQP).

**Configuración:**
- Brand terms: mismos que en el STR

**Acciones:**
1. Tab "Análisis Cruzado" → revisar "Solo en SQP" (oportunidades)
2. Tab "Plan de Acción" → filtrar por acción ESCALAR y AGREGAR
3. Filtrar solo non-branded
4. Descargar Plan de Acción bulk

**Output:** Plan de Acción con keywords priorizadas por mercado.

---

## PASO 5 — Compilar lista final de keywords

**Objetivo:** Cruzar las 3 fuentes (STR + Cerebro + SQP) y armar la lista definitiva.

**Criterios de priorización:**

| Prioridad | Criterio | Capa |
|-----------|----------|------|
| 🔴 Máxima | Aparece en STR con ventas + Cerebro con SV alto | Capa 1 — Exact Ranking |
| 🟡 Alta | Solo en Cerebro con SV > 10K, relevante al producto | Capa 2 — Phrase Discovery |
| 🟢 Media | ASIN competidor con ventas en el nicho | Capa 3 — PAT Competitor |

**Reglas:**
- Máximo 5 keywords por campaña (regla Capybaras 2026)
- No incluir keywords que ya estén en Exact activo con buen ACoS
- Separar V-Neck de Crew, Men de Women, etc. — cada producto es un set de campañas

---

## PASO 6 — Estructura de campañas (3 capas)

### Capa 1 — SP Exact Ranking
- **Keywords:** validadas por STR (2+ orders) + confirmadas en Cerebro
- **Match type:** Exact
- **Bid strategy:** Fixed bid
- **Placements:** Top of Search +50%
- **Budget:** $10/día por campaña
- **Objetivo:** Rankear en las keywords que ya sabemos que convierten

### Capa 2 — SP Phrase Discovery
- **Keywords:** alto SV en Cerebro, relevantes al producto, sin historial en STR
- **Match type:** Phrase
- **Bid strategy:** Dynamic bids - down only
- **Placements:** Top of Search +10%
- **Budget:** $8/día por campaña
- **Bid:** 20-25% menor que Capa 1 (conservador, sin historial)
- **Objetivo:** Descubrir long-tail variations que conviertan

### Capa 3 — SP PAT Competitor
- **Targets:** ASINs de competidores directos (del Cerebro)
- **Entity:** Product Targeting
- **Bid strategy:** Fixed bid
- **Placements:** Product Page +50%
- **Budget:** $8/día por campaña
- **Objetivo:** Capturar shoppers que miran competidores

---

## PASO 7 — Generar bulk y subir a Amazon

**Usar el Campaign Builder del PPC Manager** o generar manualmente siguiendo la guía `Amazon_Bulk_Upload_Guide.md`.

**Reglas críticas del bulk:**
- Campaign ID = Campaign Name (para linkear filas)
- Ad Group ID = Ad Group Name
- Start Date formato yyyyMMdd
- Bidding Strategy: "Fixed bid" o "Dynamic bids - down only"
- 1 sola hoja "Sponsored Products Campaigns"
- Sin filas vacías

**Naming convention:**
```
[MARCA] | [CHILD ASIN] | [MKT] | [TIPO] | [MATCH] | [CLUSTER] [LETRA]
```
Ejemplo: `MB | B0F6LDGCDS | US | SP-KW | EXACT | NB RANKING VN A`

**Post-upload:**
- Asignar portfolios manualmente en Campaign Manager
- Verificar que todas las campañas aparezcan como Scheduled/Enabled

---

## PASO 8 — Evaluación día 14

**Fecha:** 14 días después del lanzamiento.

**Métricas a revisar por campaña:**

| Métrica | Acción si buena | Acción si mala |
|---------|----------------|----------------|
| ACoS < target | Escalar budget +50% | — |
| ACoS > target × 1.5 | — | Bajar bids 30% |
| ACoS > target × 2 | — | Pausar campaña |
| 0 impresiones | Subir bid +25% | Revisar keyword relevance |
| Impresiones sin clicks | Revisar ad copy/imagen | — |
| Clicks sin ventas | Negativizar terms basura del STR | — |

**Capa 1 (Exact Ranking):** Si funciona → mantener y escalar. Si no → revisar bids, no pausar rápido.
**Capa 2 (Phrase Discovery):** Si no convierte → bajar bids 50%. Si sigue sin convertir semana 3 → pausar.
**Capa 3 (PAT Competitor):** Si no convierte → pausar y reasignar budget a Capa 1.

**Harvest:** Keywords de Capa 2 que conviertan → crear Exact en Capa 1.

---

## Checklist rápido — Resumen del flujo

```
□ Bajar archivos: STR 60d, Campaign CSV, SQP, Cerebro, DataDive
□ PPC Manager → STR → harvest non-branded winners
□ PPC Manager → Bulk Campañas → diagnosticar campañas activas
□ PPC Manager → Helium 10 → Cerebro keywords alto SV
□ PPC Manager → Análisis Cruzado → gaps STR vs SQP
□ Compilar lista: STR winners + Cerebro SV + SQP gaps
□ Armar campañas: Capa 1 Exact + Capa 2 Phrase + Capa 3 PAT
□ Generar bulk (Campaign Builder o manual)
□ Subir a Amazon → verificar portfolios
□ Día 14 → evaluar y optimizar
```

---

## Historial de uso

| Fecha | Marca | Campañas | Budget | Resultado |
|-------|-------|----------|--------|-----------|
| 07/04/2026 | M&B Women (V-Neck + Crew) | 7 | $72/día | Pendiente eval 22/04 |

---

**Validado:** 07 abril 2026
**Agencia:** Capybaras Agency | **Dev:** Lenin Acosta

#sop #ppc #non-branded #lanzamiento #campañas #capybaras #2026
