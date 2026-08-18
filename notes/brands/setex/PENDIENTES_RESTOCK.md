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
