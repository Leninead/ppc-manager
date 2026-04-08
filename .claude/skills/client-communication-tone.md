# Skill: Client Communication Tone
## Propósito
Estandarizar el tono, estructura y formato de toda comunicación generada por el Agency OS: reportes ejecutivos, changelogs técnicos, mensajes de Slack y emails a clientes. Se activa cuando cualquier agente genera texto que será leído por un cliente o por el equipo interno.

## Tono general Capybaras
- Profesional pero accesible — no somos consultora Big4, somos agencia boutique
- Datos primero, opinión después — siempre respaldar con números
- Directo y conciso — el AM tiene 15 minutos para revisar, no 1 hora
- Positivo pero honesto — celebrar wins, no ocultar problemas

## Estructura de reporte ejecutivo (Weekly Client Report)

Resumen ejecutivo (3-4 oraciones)

Frase apertura: "Esta semana [resultado principal]"
Dato clave con delta: "Sales $X,XXX (+XX.X% WoW)"
Highlight positivo más importante
Si hay alerta: "Punto de atención: [issue]"


KPIs principales (tabla o cards)

Siempre con delta WoW
Siempre con semáforo visual


Acciones realizadas (bullet list corta)

Qué se hizo, no cómo se hizo
"Negativizamos 12 search terms sin conversión ($45 recuperados)"
NO: "Fuimos a la tab de STR, filtramos por clicks>10..."


Próximos pasos (2-3 items max)

Acción concreta + fecha esperada




## Estructura de changelog técnico (para equipo interno)
📋 Cambios realizados — [Marca] — [Fecha]
CAMPAÑAS MODIFICADAS:

[Nombre campaña] — [qué se cambió] — [motivo]
Ejemplo: "DG | B0CYLMJJJC | US | RANKING-KW | Exact | vitamin a"
→ Bid $0.45 → $0.62 (CVR subió a 14.2%, bid estaba 30% bajo sugerido)

KEYWORDS NEGATIVIZADAS:

 términos negativizados en [Y] campañas
Top 3 por spend: "term1" ($12.40), "term2" ($8.90), "term3" ($6.20)
Spend recuperado estimado: $XX.XX/semana

CAMPAÑAS NUEVAS:

[Nombre] — [tipo] — [match] — [# keywords] — budget $X/día

PRÓXIMA REVISIÓN: [fecha]

## Formato mensaje Slack
🦫 [Marca] — Update [Fecha]
📊 KPIs semana:

Sales: $X,XXX (↑XX%)
ACoS: XX.X% (↓X.X pp)
TACoS: XX.X%

✅ Acciones:

[acción 1]
[acción 2]

⚠️ Atención: [si hay algo]
📎 Reporte completo adjunto

## Reglas por mercado
### Amazon México (MX)
- Moneda: MXN o pesos, no USD
- Festivos: usar calendario MX (ver _FESTIVOS_MX en Account Pulse)
- Tono: más cercano, tuteo natural
- Ejemplo: "Esta semana las ventas subieron 12% — el Hot Sale empieza a notarse"

### Amazon USA (US)
- Moneda: USD
- Festivos: Prime Day, Black Friday, Q4 (Oct-Dec)
- Tono: profesional, data-driven
- Ejemplo: "Revenue increased 12% WoW driven by improved CVR on top 3 ASINs"

## Idioma — Toggle ES/EN
El Weekly Client Report tiene toggle de idioma. Las reglas:
- ES: todo en español, métricas con nombre en español
- EN: todo en inglés, métricas con nombre estándar Amazon
- Nunca mezclar idiomas en un mismo reporte
- El toggle afecta: Executive Summary, headers de tabla, labels de Excel

## Alarmas — cómo comunicarlas
| Severidad | Formato | Ejemplo |
|-----------|---------|---------|
| Crítica | 🔴 ACCIÓN INMEDIATA | "BuyBox perdido en hero ASIN — revisar precio HOY" |
| Alta | 🟡 ATENCIÓN | "ACoS subió a 45% esta semana — revisar bids top 5 campañas" |
| Info | ℹ️ NOTA | "Campaña nueva en warm-up — no optimizar hasta 14 días" |

## Números en comunicación
- Siempre redondear para legibilidad: "$1,234" no "$1,234.56" en Slack
- En Excel mantener 2 decimales
- Deltas siempre con signo: "+12.3%" o "-5.1%"
- Porcentajes: 1 decimal max en comunicación ("22.7%")
- Ordenes/clicks: sin decimales ("45 órdenes", no "45.0")

## Qué NO hacer
- Nunca enviar datos sin contexto — "ACoS 35%" no dice nada solo; "ACoS 35% (target 25%, subió 5pp)" sí
- Nunca usar jerga técnica con el cliente sin explicar — "negativizamos terms" → "eliminamos búsquedas irrelevantes que gastaban presupuesto"
- Nunca reportar números de una sola semana como tendencia — mínimo 2 semanas para hablar de tendencia
- Nunca ocultar malas noticias — mejor "ACoS subió pero detectamos la causa y ya ajustamos" que silencio
- Nunca enviar reporte sin revisión de números — verificar que los totales cuadren antes de enviar
