---
tipo: prompt-arranque-cliente
cliente: ltd
nivel: cargado
actualizado: 2026-04-25
proxima_actualizacion: cierre próxima sesión LTD
heroes_oficiales:
  - B0F8P9GBZN
  - B09MG1PM6L
  - B0F8PCWD6J
  - B09MG28M9D
  - B0F8PB4NHX
  - B005ULUZIQ
  - B0DT6MS7TK
  - B0DT6CMR7B
  - B0081GJ038
  - B0CK2KCBLS
status_atom11: <<<rellenar próxima sesión>>>
---

# Arranque Sesión — LTD (Love To Dream)

> Prompt customizado para arrancar cualquier sesión del cliente LTD.
> Pegar el bloque XML del primer code block en chat nuevo de Claude.ai.
> Se actualiza al cierre de cada sesión con el delta.
>
> ⚠️ STUB — Esta nota está parcialmente poblada con contexto de la sesión 25/04.
> Completar al final de la próxima sesión LTD con el formato del arranque-dermaglos.

---

## 🚀 Bloque para pegar al chat (estable)

```xml
<arranque_sesion cliente="ltd">

Hola Claude. Soy Lenin, Capybaras Agency. Vengo a trabajar sesión LTD.

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, conectado a GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto Claude.
Cliente: LTD (Love To Dream) — Amazon México (MXN), baby swaddle y sleep products.
Equipo interno: Adam (Sales Director), Agustín (Account Manager), Aaron (compliance contact).
</contexto_proyecto>

<lectura_obligatoria_en_orden>
1. notes/CLAUDE.md (estado general agencia)
2. notes/state/STATE-agencia.md (qué cambió + bloqueos abiertos)
3. notes/brands/ltd/LTD.md (sesiones recientes, fases ejecutadas, pendientes)
4. notes/brands/ltd/skus_ltd.md (si existe — mapeo SKU/ASIN)
5. notes/brands/ltd/atom11-rules.md (si existe — rules en producción)
6. notes/daily/ (último daily LTD disponible)
7. notes/sops/amazon-bulk-upload-guide.md (gotchas de bulk format)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_ltd>

## Heroes oficiales (snapshot 25/04 — Fase 4 Push)
Familia Swaddle Up (SU) por etapa:
- **SU-NB (recién nacidos 0-3m)**: B0F8P9GBZN (OAT S), B09MG1PM6L (OLV S), B0F8PCWD6J (OAT NB)
- **SU-M (6-12m)**: B09MG28M9D (DBL M), B0F8PB4NHX (OAT M), B005ULUZIQ (GR M)
- **SU-T (transición 12-18m)**: B0DT6MS7TK (DOL Trans M), B0DT6CMR7B (DOL Trans L)
- **SU-S family completa**: B0F8P9GBZN, B09MG1PM6L, B0081GJ038, B0CK2KCBLS

## ASINs con flag
- **B0CK2C1ZJ5 (DOL M)** — perdido del plan, no aparece en export del seller. Reemplazado por dupla M heroes vivos.
- **B0081GIZ52 (GR M Transition)** — confirmado OOS. Reemplazado por DOL Transition M+L vivos.
- **B005ULUZIQ** — flag 16/04 aparenta resuelto: listing Active, 423u stock, BuyBox visible. Adam pendiente confirmación con Aaron compliance.
- **B0F8PCWD6J (OAT NB)** — HERO ADICIONAL identificado 25/04 ($11,107 sales 30d, 90u stock).
- **B09MG1J3LC** — stockout, ETA pendiente con cliente vía Agustín.

## Fases ejecutadas
- ✅ Fase 1, 3, 4, 5 cerradas (sesiones 1+2 del 25/04)
- ⏳ Fase 6 delegada a equipo:
  - Adam: status flag B005ULUZIQ con Aaron
  - Agustín: ETA restock B09MG1J3LC + summary cliente + lista heroes 3ra solicitud
- ⏳ Auditoría sistémica match producto/KW pendiente (sin owner asignado)

## Atom11 status
<<<rellenar próxima sesión LTD>>>

## Naming convention LTD vigente
Patrón observado en bulk Fase 4:
`SU-[FAMILIA] | MX | SP | KWS | EXACT | RANK | M4 [keyword corta]`
Ejemplos:
- `SU-NB | MX | SP | KWS | EXACT | RANK | M4 swaddle 0-3`
- `SU-M | MX | SP | KWS | EXACT | RANK | M4 saquito 6-12`
- `SU-T | MX | SP | KWS | EXACT | RANK | M4 saquito 12-18`
- `SU-S | MX | SP | KWS | EXACT | RANK | M4 swaddle`

⚠️ Verificar si LTD migró a naming híbrido tipo `LTD | OBJETIVO |` o sigue con el formato Fase 4.

## Bid strategy LTD (snapshot 25/04)
- Type: SP Manual · Bidding: Fixed bid · Placement: ToS +50%
- Bids EXACT RANK: $3.00-4.00 según prioridad
- Match: Exact · Targeting: MANUAL
- Mercado: MXN

## Portfolios LTD vigentes
- Swaddle UP para recién nacidos (0-3 meses)
- Swaddle UP para bebés de 6-12 meses
- Sacos de transición con un toque de diseño
- SU | MX | CORE | 0-12M | CATEGORY

</conocimiento_operativo_ltd>

<bugs_y_gotchas_bulk_format>
Aplican los 8 learnings de la sesión Dermaglos 28/04. Ver sección completa en notes/sops/amazon-bulk-upload-guide.md "Learnings 2026-04-28".

Resumen para LTD:
1. Negative Keyword vs Campaign Negative Keyword (entities distintas)
2. Campaign IDs numéricos para campañas existentes (Download campaigns antes)
3. Start Date como TEXTO no float
4. Google Sheets corrompe IDs numéricos largos
5. Caracteres especiales en KWs pueden ser rechazados
6. Campaign Analyzer puede mostrar zombies (cruzar con BulkSheetExport)
7. SD bulk schema diferente de SP
8. Hoja única "Sponsored Products Campaigns"
</bugs_y_gotchas_bulk_format>

<flujo_de_arranque>
Una vez leído todo el contexto:

1. Confirmá brevemente que entendiste:
   - Última sesión LTD (fecha + qué se hizo)
   - Status Fase 6 delegada (Adam + Agustín)
   - Pendientes activos del cliente
   - Bloqueos vigentes

2. Recordame correr antes de cualquier trabajo:
   - `cd C:\proyectos\ppc-manager && git status && git pull`
   - `git add . && git commit -m "checkpoint: antes de [tarea de hoy]"`

3. Preguntame qué queremos atacar hoy. NO arranques trabajo nuevo sin esa confirmación.

4. Si la tarea involucra bulks → revisar gotchas ANTES de generar archivos.
</flujo_de_arranque>

<rituales_obligatorios>
Al cierre, ejecutar en orden estricto:

1. 3 prompts del sop-writer (daily + brand notes + STATE quirúrgico)
2. Update de este archivo (notes/prompts/sesion/clientes/arranque-ltd.md)
3. Git commit + push
4. Refresh manual en proyecto Claude
5. Generar prompt arranque próxima sesión si quedó algo a medias
</rituales_obligatorios>

</arranque_sesion>
```

---

## 📊 Estado actual del cliente (snapshot 2026-04-25)

> ⚠️ STUB — Última sesión registrada: 25/04. Actualizar con la próxima sesión LTD.

### Plan ejecutado (25/04/2026 — Fase 4 Push Heroes)
- 5 campañas creadas vía bulk Excel (Batch UUID `10d5a6ef-4ec9-4899-a0d9-6e9e2ea56a33`, Success al primer intento)
- +$200/d budget adicional ($6,000 MXN/mes)
- 12 SKUs únicos targeteados / 9 ASINs únicos
- Brand Defense expandido a 5 ad groups

### KPIs actuales vs target
<<<rellenar próxima sesión LTD>>>

---

## ⏰ Pendientes activos (al 2026-04-25)

### Delegados al equipo (Fase 6)
1. Adam con Aaron — confirmar status flag B005ULUZIQ
2. Agustín con cliente — ETA restock B09MG1J3LC + session summary + heroes 3ra solicitud

### Sin owner asignado
3. Auditoría sistémica match producto/KW en RANK campaigns

### Diferidos
<<<rellenar próxima sesión LTD>>>

---

## 📅 Próxima evaluación

<<<rellenar próxima sesión LTD>>>

---

## 🧠 Conocimiento operativo permanente

> Sección estable. Cambios solo si se redefine algo estructural.

### Contactos cliente / equipo

| Contacto | Rol | Notas |
|---|---|---|
| Adam | Sales Director (interno) | Maneja compliance + escalations |
| Agustín | Account Manager (interno) | Maneja conversaciones cliente día a día |
| Aaron | Compliance contact | Conversación abierta sobre B005ULUZIQ |

### Reglas Capybaras específicas para LTD

- Mercado: MXN (Amazon México)
- Bulk Excel obligatorio cuando volumen > 5 campañas
- Portfolio ID dejar VACÍO (asignar manual post-upload)
- 31 columnas Capybaras 2026 (incluye Sites)
- Match: EXACT priorizado en RANK campaigns
- Bidding: Fixed bid + Placement ToS +50% para EXACT RANK

### Decisiones de bid strategy históricas

<<<rellenar con detalle del setup vigente>>>

### Listings con flag

<<<rellenar próxima sesión LTD>>>

---

## 📜 Historial de actualizaciones

- **2026-04-28**: stub creado con contexto de la sesión 25/04 (Fase 4 cerrada). Estructura lista, pero secciones marcadas con `<<<rellenar>>>` esperan la próxima sesión LTD para poblar.

---

## 🔗 Referencias cruzadas

- `[[LTD]]` — brand note principal (si existe)
- `[[skus_ltd]]` — mapeo ASIN/SKU (si existe)
- `[[atom11-rules]]` LTD — rules en producción (si existe)
- `[[2026-04-25]]` — último daily LTD
- `[[amazon-bulk-upload-guide]]` — gotchas bulk format
- `[[STATE-agencia]]` — estado global agencia
