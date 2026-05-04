---
tipo: prompt-arranque-cliente
cliente: mb
nivel: cargado
actualizado: 2026-05-04
proxima_actualizacion: cierre próxima sesión MB
heroes_oficiales: B0F6LCGH2L (CR M White) · B0F6LDGCDS (VN M Crimson)
status_atom11: activa (siempre tuvo — corregido 2026-05-04)
---

# Arranque Sesión — MB (Mott & Bow)

> Prompt customizado para arrancar cualquier sesión del cliente MB.
> Pegar el bloque XML del primer code block en chat nuevo de Claude.ai.
> Se actualiza al cierre de cada sesión con el delta.
>
> ⚠️ STUB — Esta nota está parcialmente poblada con contexto de marzo/abril.
> Completar al final de la próxima sesión MB con el formato del arranque-dermaglos.

---

## 🚀 Bloque para pegar al chat (estable)

```xml
<arranque_sesion cliente="mb">

Hola Claude. Soy Lenin, Capybaras Agency. Vengo a trabajar sesión MB (Mott & Bow).

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, conectado a GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto Claude.
Cliente: Mott & Bow — Amazon US, apparel premium.
</contexto_proyecto>

<lectura_obligatoria_en_orden>
1. notes/CLAUDE.md (estado general agencia)
2. notes/state/STATE-agencia.md (qué cambió + bloqueos abiertos)
3. notes/brands/mb/MB.md (sesiones recientes, fases ejecutadas, pendientes)
4. notes/brands/mb/skus_mb.md (si existe — mapeo SKU/ASIN)
5. notes/brands/mb/atom11-rules.md (si existe — rules en producción)
6. notes/daily/ (último daily MB disponible)
7. notes/sops/amazon-bulk-upload-guide.md (gotchas de bulk format)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_mb>

## Heroes oficiales
- CR M White: B0F6LCGH2L (Crew Neck Hero)
- VN M Crimson: B0F6LDGCDS (V-Neck Hero)
- Sleeper en observación: línea Black Women (~$3K+/sem orgánico, futuro hero candidato)

## Status Fase 2 (snapshot 2026-05-04)
🔥 BLOQUEADA hace 7 días — ventana 26-30 abril vencida sin lanzamientos.

- White Tee ($30/d) + Premium Cotton ($10/d) **NO lanzados**
- Bloqueo: Brand Store Women actualizado + video SBV (cliente, sin ETA)
- **Mensaje gate AM Fase 2 — pendiente desde 27/04 — PRIMERA TAREA próxima sesión**
- Pregunta cerrada al AM: "Brand Store Women + video SBV listos sí/no, fecha estimada"

## Análisis de tráfico externo (Marzo 2026)
- Push detectado 27-29/03: sesiones +134% vs fines de semana normales
- Sales día más alto del mes: $13,086 (sábado)
- Patrón: tráfico externo (redes sociales / email / influencer) sin aviso a la agencia

## Atom11 status
✅ Activa (corregido 2026-05-04 — M&B siempre tuvo Atom11, el STATE histórico estaba mal). Coverage exacto, rules activas y portfolios bajo Atom11 — TBD próxima sesión con datos del cliente.

## Naming convention MB
**Mixto** — coexisten:
- Legacy con paréntesis de dispositivo: `MTC - B0F844CHFY | SP - PR | EXACT | DEFEND | BRAND ASINS`
- Capybaras nuevo (las 5 NB HW + Premium del 21-27/04): `MB | B0F6LDGCDS | US | SP-KW | EXACT | NB CR HW A`

Auditoría de unificación naming pendiente — bloqueante para que Atom11 Rules Builder (M11) clasifique todas las campañas correctamente.

## Bid strategy MB
TBD — definir en próxima sesión M&B. Datos para el análisis:
- CPC promedio cuenta TW: $0.75
- Las 5 nuevas con bid $0.80-$1.10 NO impresionan → bid floor apparel Women US > $1.50
- DEFEND brand sigue eficiente: BROAD M `+mott +bow` ACoS 12.2%, EXACT defenders ACoS 6-15%

</conocimiento_operativo_mb>

<bugs_y_gotchas_bulk_format>
Aplican los 8 learnings de la sesión Dermaglos 28/04. Ver sección completa en notes/sops/amazon-bulk-upload-guide.md "Learnings 2026-04-28".
</bugs_y_gotchas_bulk_format>

<flujo_de_arranque>
1. Confirmá brevemente entendimiento de:
   - Última sesión MB (fecha + qué se hizo)
   - Status Fase 2 (¿White Tee + Premium Cotton lanzados?)
   - Pendientes activos
   - Bloqueos vigentes (Brand Store Women / video SBV)

2. Recordame git status + git pull + checkpoint commit

3. Preguntame qué atacamos hoy antes de trabajo nuevo

4. Si involucra bulks → gotchas primero
</flujo_de_arranque>

<rituales_obligatorios>
Al cierre: 3 prompts sop-writer + update este archivo + git commit/push + refresh proyecto Claude.
</rituales_obligatorios>

</arranque_sesion>
```

---

## 📊 Estado actual del cliente

> ⚠️ STUB — Actualizar con la próxima sesión MB.

### Última actividad documentada
- **Marzo 2026**: análisis de impacto tráfico externo (push 27-29/03 detectado)
- **Pre-2026-04-15**: Fase 2 bloqueada esperando Brand Store Women actualizado + video SBV

### KPIs
<<<rellenar próxima sesión MB>>>

---

## ⏰ Pendientes activos

### Bloqueos
1. Brand Store Women actualizado (cliente)
2. Video SBV (cliente)
3. Verificar si White Tee ($30/d) + Premium Cotton ($10/d) se lanzaron en ventana 26-30 abril

### Diferidos
<<<rellenar próxima sesión MB>>>

---

## 📅 Próxima evaluación

<<<rellenar próxima sesión MB>>>

---

## 🧠 Conocimiento operativo permanente

### Contactos cliente / equipo

<<<rellenar próxima sesión MB>>>

### Reglas Capybaras específicas para MB

- Mercado: USA
- Apparel category — gestionar variations (sizes, colors)
- Atención a tráfico externo (cliente puede pushear sin aviso, ver análisis Marzo 2026)

### Decisiones de bid strategy históricas

<<<rellenar próxima sesión MB>>>

### Listings con flag

<<<rellenar próxima sesión MB>>>

---

## 📜 Historial de actualizaciones

- **2026-05-04**: STUBs poblados con datos reales del análisis WoW (PW 19-25 abr / TW 26 abr-2 may). Heroes confirmados (CR M White B0F6LCGH2L + VN M Crimson B0F6LDGCDS). Atom11 corregido a activa. Naming mixto documentado. Status Fase 2 actualizado a bloqueada hace 7 días. Bid strategy datos para análisis incluidos.
- **2026-04-28**: stub creado con contexto disponible (Fase 2 bloqueada + análisis tráfico externo Marzo). Secciones marcadas con `<<<rellenar>>>` esperan la próxima sesión MB.

---

## 🔗 Referencias cruzadas

- `[[MB]]` — brand note principal (si existe)
- `[[MB_Impacto_Trafico_Externo_Marzo2026]]` — análisis tráfico externo
- `[[amazon-bulk-upload-guide]]` — gotchas bulk format
- `[[STATE-agencia]]` — estado global agencia
