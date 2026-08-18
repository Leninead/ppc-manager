---
tipo: playbook
cliente: setex
status: activo
trigger: confirmación restock FBA en Seller Central
actualizado: 2026-08-13
---

# PENDIENTES RESTOCK — Setex MX
> Última actualización: 2026-08-13 (snapshot Manage Inventory 11/08)

## 🔴 ALERTA GLOBAL: INBOUND = 0 EN LOS 63 LISTINGS
Ni un solo ASIN con unidades en tránsito. Alertado el 03/08 y el 11/08. Sin respuesta reflejada en stock.

| ASIN | Producto | Disp. | Runway | Rol | Estado |
|---|---|---|---|---|---|
| `B0DWBYSBQZ` | Nano 15p | 4 | ~30d | menor | 🔴 crítico |
| `B0B94KBY8H` | Temple negro | 81 | 31d | 3º en ventas | 🔴 |
| `B09HVXDH7M` | Thick transp | 55 | 32d | mejor ACoS de la cuenta (5,0%) | 🔴 |
| `B0F63LTD92` | Ear Hook | 121 | 51d | alarma de ACoS | 🟠 |
| `B08C2T72ND` | 1mm negro | 293 | 53d | #2 facturación, 100% orgánico | 🟠 |
| `B09HW4VWQR` | Thick negro | 0 | OOS | — | 🔴 desde 17/07 |

## Owner y control (regla del 24/07)
- Destinatario del pedido: Tatiana Velasquez
- Responsable de follow-up: Lenin Acosta
- Fecha de control: 18/08/2026
- Pedidos enviados: 17/07 (hero + Thick negro) · 03/08 · 11/08

## Por qué importa `B08C2T72ND`
2º en facturación ($41.037 en julio), vende con cero pauta, CVR sesión 18,11%. Si se quiebra no hay reemplazo en la familia. Precedente: en julio se quebró `B081GB8F89` y sus ventas cayeron −49% en una semana ($31.530 → $16.078), CVR 11,49% → 5,72%. El ranking orgánico no se recupera solo cuando vuelve el stock.

## Zona clearance (sobrestock)
| ASIN | Disp. | Runway | Nota |
|---|---|---|---|
| `B08PZF22R1` | 1.162 | ~420d | mejoró desde 682d (17/07). Destino natural de escala |
| `B081GB8F89` | 1.061 | ~140d | post-restock 23/07, sano |
| Kids (3 ASINs) | 105 | ver setex.md | bloqueado por precio del 15p |
| Thumbsticks | ~350 | — | casi sin venta |

## Playbook de reactivación condicional
Se activa SOLO con confirmación de restock FBA en Seller Central (no por mensaje). Al confirmarse:
1. Verificar `Available` > 0 y `Inbound` reflejado
2. Reactivar campañas del ASIN en estado `paused` por stock
3. Aplicar Regla 4 antes de escalar: <15d no escalar · 15–25d cuidado · >25d escalable · >300d clearance
4. Registrar en setex.md con fecha

---

## Playbook detallado de reactivación (archivado 2026-04-29)

> Recuperado de la versión previa de este archivo (commit `1e4a633`) tras la reescritura del 13/08. El estado de stock vigente es el de arriba; esto queda como **referencia operativa**: los bulks de reactivación, las keywords de harvest, el protocolo de monitoreo y los casos edge siguen siendo válidos cuando se confirme un restock. Verificar antes de usar que las campañas listadas sigan existiendo (Amazon archiva las pausadas a los 90d).

> Playbook de activación condicional. Las acciones se ejecutan SOLO cuando se confirme reposición FBA de Temple Tips o Ear Hooks. Hasta entonces, todo queda diferido para preservar runway y rank.

### 🎯 Trigger de activación

Confirmación de Tati de:
- ETA reposición FBA Temple Tips (B0C7WPFVGV grises + B0B94KBY8H negros), **o**
- ETA reposición FBA Ear Hooks (B0F63LTD92), **o**
- Recepción confirmada en Amazon FBA (Inventory disponible > 0)

### 📋 Bloque A — Reactivación Temple Tips

#### Pre-requisitos
- ✅ Stock confirmado en Seller Central (al menos 50u entre los 2 SKUs)
- ✅ Listings activos (ningún flag/suppression)

#### Paso 1: Reactivar 16 campañas pausadas en Bulk #1 (UUID 7096ec9c-9528-4c22-a18f-328d56cb2a29)

| Campaign Name | Acción | Bid action |
|---|---|---|
| Setex Temple Tips \| MX \| SP-KWS \| EXACT \| SQP \| accesorio lentes | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-KWS \| EXACT \| SQP \| patitas para lentes | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-KWS \| EXACT \| SQP \| gomas para patas de lentes | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-KWS \| BROAD \| DISCOVERY \| Sujetador ES | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-AUTO \| CLOSE \| discovery | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-AUTO \| COMPLEMENTS \| discovery | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-AUTO \| SUBSTITUTES \| discovery | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-AUTO \| LOOSE \| discovery | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-KWS \| PHRASE \| SQP \| sujetador de lentes | enabled | bid actual +25% |
| Setex Temple Tips \| MX \| SP-KWS \| PHRASE \| SQP \| sujetadores de lentes | enabled | bid actual +25% |
| Setex Temple \| SP-KW \| EXACT \| ESCALAR \| sujetador para lentes | enabled | bid actual +30% |
| Setex Temple \| SP-PT \| DEFENSIVE \| OWN Temple PDPs | enabled | bid actual +25% |
| Setex Temple \| SP-PT \| PAT \| MATCH A \| ZYHSLZ | enabled | bid actual +30% |
| Setex Temple \| SP-PT \| PAT \| MATCH AA \| Slzhds+ZENSUKYE | enabled | bid actual +30% |
| Setex Temple \| SP-KW \| EXACT \| ESCALAR \| almohadillas para lentes orejas | enabled | bid actual +25% |
| Setex Temple \| SP-PT \| PAT \| MATCH AAA \| MOCOFLY | enabled | bid actual +25% |

**Razón del bid up +25-30%**: durante el OOS, Amazon degradó rank orgánico (page views B0B94KBY8H 652 → 551 = -15%). El bid up acelera la recuperación de visibilidad.

#### Paso 2: Crear 3 campañas Temple nuevas (diferidas del 29/04)

| # | Campaign Name | Match | Budget | Hero | KWs |
|---|---|---|---|---|---|
| 1 | Setex \| RANKING \| SP \| EXACT - Temple - B0B94KBY8H - Patillas | EXACT | $5/d | B0B94KBY8H (negro) | patillas para lentes, gomas para patillas, terminales de lentes, terminales para patillas |
| 2 | Setex \| RANKING \| SP \| EXACT - Temple - B0B94KBY8H - Sujetador | EXACT | $5/d | B0B94KBY8H | sujetador para lentes que se caen, sujetador para lentes deportivos, agarrador para lentes |
| 3 | Setex \| DEFENSIVE \| SP \| EXACT - Temple - B0B94KBY8H - Brand Defense | EXACT | $4/d | B0B94KBY8H | setex temple tips, setex patillas, setex gecko temple |

#### Paso 3: Aplicar 7 keywords harvest Temple

| Keyword | Match | Campaña destino | Bid sugerido |
|---|---|---|---|
| terminales de lentes | exact | (nueva #1 Patillas) | $1.80 |
| sujetador para lentes que se caen | exact | (nueva #2 Sujetador) | $2.20 |
| sujetador para lentes deportivos | exact | (nueva #2 Sujetador) | $2.00 |
| agarrador para lentes | exact | (nueva #2 Sujetador) | $1.50 |
| antideslizantes para patillas | exact | Setex Temple ESCALAR sujetador | $1.80 |
| seguros para lentes | exact | Setex Temple ESCALAR sujetador | $1.50 |
| protectores para lentes orejas | exact | Setex Temple ESCALAR almohadillas | $1.80 |

### 📋 Bloque B — Reactivación Ear Hooks

#### Pre-requisitos
- ✅ Stock confirmado en Seller Central (al menos 30u en B0F63LTD92)
- ✅ Listing activo

#### Paso 1: Revertir budgets reducidos en Bulk #1 (3 campañas)

| Campaign Name | Budget actual | Revertir a |
|---|---|---|
| Setex Ear Hook Grips \| MX \| SP-AUTO \| CLOSE \| discovery | $30 | $50 |
| Setex Ear Hook Grips \| MX \| SP-AUTO \| SUBSTITUTES \| discovery | $30 | $50 |
| Setex Ear Hook Grips \| MX \| SP-KWS \| EXACT \| SQP \| retenedores de lentes | $36 | $60 |

#### Paso 2: Reactivar 7 campañas Ear Hook pausadas en Bulk #1

| Campaign Name | Acción | Bid action |
|---|---|---|
| Setex Ear Hook Grips \| MX \| SP-KWS \| EXACT \| SQP \| sujeta lentes | enabled | bid actual +30% |
| Setex Ear Hook Grips \| MX \| SP-KWS \| EXACT \| SQP \| soporte de lentes | enabled | bid actual +30% |
| Setex Ear Hook Grips \| MX \| SP-KWS \| EXACT \| SQP \| sujetadores de lentes | enabled | bid actual +30% |
| Setex Ear Hook Grips \| MX \| SP-KWS \| EXACT \| SQP \| sostenedor de lentes | enabled | bid actual +30% |
| Setex Ear Hook Grips \| MX \| SP-AUTO \| COMPLEMENTS \| discovery | enabled | bid actual +25% |
| Setex Ear Hook Grips \| MX \| SP-KWS \| BROAD \| DISCOVERY \| Retenedor ES | enabled | bid actual +30% |
| Setex Ear Hook Grips \| MX \| SP-AUTO \| LOOSE \| discovery | enabled | bid actual +25% |

#### Paso 3: Crear 2 campañas Ear Hook nuevas

| # | Campaign Name | Match | Budget | Hero | KWs |
|---|---|---|---|---|---|
| 1 | Setex \| RANKING \| SP \| EXACT - Ear Hook - B0F63LTD92 - Retenedor | EXACT | $5/d | B0F63LTD92 | retenedor de lentes, ganchos para anteojos, ganchos para lentes, ganchos antideslizantes lentes |
| 2 | Setex \| RANKING \| SP \| EXACT - Ear Hook - B0F63LTD92 - Soporte | EXACT | $4/d | B0F63LTD92 | soporte para anteojos, soporte para lentes deportivos, fijador para lentes |

#### Paso 4: Aplicar 5 keywords harvest Ear Hook

| Keyword | Match | Campaña destino | Bid sugerido |
|---|---|---|---|
| ganchos para anteojos | exact | (nueva #1 Retenedor) | $2.20 |
| ganchos antideslizantes lentes | exact | (nueva #1 Retenedor) | $2.00 |
| fijador para lentes | exact | (nueva #2 Soporte) | $1.80 |
| soporte para lentes deportivos | exact | (nueva #2 Soporte) | $2.00 |
| evita que se caigan los lentes | exact | Setex Ear Hook ESCALAR sujeta lentes (post-reactivada) | $2.20 |

### 🛡️ Protocolo de monitoreo post-reactivación

#### Día 1-3 post-restock
- ✅ Verificar inventory disponible no caiga abruptamente
- ✅ Chequear que no se reactive el flag B086H3TZ6B (child Best Seller con 1u)
- ✅ Monitor BuyBox de los 3 ASINs reactivados

#### Día 7 post-restock
- Review impressions: deben recuperarse al ~80% del nivel pre-OOS
- Review CVR: si cayó >20% vs pre-OOS, revisar listing health
- Review ACoS: bid up acelera recuperación pero también ACoS — esperar ACoS 2-3pp arriba del normal por las primeras 2 semanas
- Decidir si bajar bids al nivel previo o mantener +25-30% otras 2 semanas

#### Día 14 post-restock
- Si rank orgánico no recuperado al 90% del nivel pre-OOS → bid up extender otras 2 semanas
- Si recuperado → revertir bids a niveles pre-OOS, mantener campañas nuevas

### 📊 Métricas a trackear

| Métrica | Pre-OOS baseline | Target día 14 post-restock |
|---|---|---|
| Temple Tips daily sales | ~$200/d | ~$220/d (+10% por bid up) |
| Temple Tips daily orders | ~1.5/d | ~1.7/d |
| Temple Tips sales rank (B0B94KBY8H) | 24,660 | <30,000 |
| Ear Hooks daily sales | ~$330/d | ~$370/d |
| Ear Hooks daily orders | ~1.1/d | ~1.3/d |
| Ear Hooks sales rank (B0F63LTD92) | 6,261 | <8,000 |

### 🚨 Casos edge

#### Si el restock es parcial (solo 1 SKU de Temple, no los 2)
- Reactivar SOLO las campañas pertinentes a ese SKU
- Si es ambiguo (campañas no son SKU-específicas), priorizar reactivar AUTO + EXACT que más históricamente convirtieron
- B0B94KBY8H (negros) es el bestseller histórico — priorizar si solo viene 1

#### Si el restock se demora >14 días
- Revisar si campañas pausadas siguen vigentes en Amazon (las archivan después de 90d)
- Si archivadas, hay que recrearlas — usar el bulk preparado en el plan original

#### Si Best Seller badge se pierde durante OOS prolongado
- Re-priorizar B086H3TZ6B (child Best Seller con 1u)
- Pausar las 9 campañas nuevas del 29/04 hasta recuperar badge (no tiene sentido pagar tráfico sin badge multiplier)

### 🔗 Referencias cruzadas

- [[setex]] — brand note principal
- [[2026-04-29]] — daily de la sesión donde se decidieron estos diferidos
- [[2026-04-29-WoW-organic-vs-paid-decomp]] — análisis que originó el playbook
- Bulk #1 UUID `7096ec9c-9528-4c22-a18f-328d56cb2a29` — pausas originales

### 📜 Historial de actualizaciones

- **2026-04-29**: playbook creado — 5 campañas + 12 KWs preparadas para reactivación con bid +25-30% post-restock. Disparadores definidos.

### 2026-07-17 — Alerta stock post-360°

- 🔴 **B081GB8F89 (motor #1, 30% de la cuenta): 3 días de runway.** Escala cancelada a propósito (excluido del BULK3), pauta contenida. Reposición URGENTE — mensaje enviado a Tatiana 17/07. Si no repone en la ventana, cae ~30% de la facturación de Setex.
- 🔴 B09HW4VWQR (Thick negro): 3d. Pauta ya bajada.
- 🟠 B0B94KBY8H (Sujetador): 14d. No escalar.
- 🟢 B08PZF22R1 (Thin): overstock 682d — clearance pendiente.

### 2026-07-24 — 🔴 QUIEBRE CONSUMADO B081GB8F89

La alerta del 17/07 (3d de runway) **se materializó**: ventas −49% ($31,530 → $16,078), CVR 11.49% → 5.72% con el mismo tráfico. Sin reposición en 7 días.

- **Pedido a:** Tatiana (mensaje 17/07)
- **Estado:** sin respuesta reflejada en stock al 24/07
- **Costo corriendo:** cada semana sin stock erosiona ranking orgánico. El ranking NO se recupera solo cuando entra el stock.
- ⚠️ **Falta definir: quién controla el follow-up y con qué frecuencia.** La alerta del 17/07 no tenía owner de seguimiento — ese es el motivo por el que pasó una semana sin control.
- También pendiente: B09HW4VWQR (Thick negro).
