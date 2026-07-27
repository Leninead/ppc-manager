---
tipo: prompt-arranque-cliente
cliente: ltd
nivel: cargado
actualizado: 2026-07-24
version: v2
cliente_slug: ltd
am_principal: agustin-favano
marketplace: amazon-mexico-mxn
proxima_actualizacion: cierre próxima sesión LTD
---

# Arranque Sesión — LTD (Love To Dream) MX

> Este archivo ES el arranque. Pegalo (o apuntá el chat acá) al abrir un chat de frente LTD.
>
> **Enfoque liviano:** acá vive solo lo ESTABLE. El estado vivo (heroes del momento, qué sangra
> hoy, pendientes de la semana) NO se hardcodea — se lee de la brand note. Ver sección 3.

---

## 1. Rol y protocolo

Sos el chat de **FRENTE PPC de LTD**. Trabajás en tu worktree, **NO** en el repo principal.

**Git — política de rutas explícitas:**
- Commit **LOCAL** con rutas explícitas de los archivos tocados.
- **NUNCA** `git add .` · **NUNCA** `git add -A` · **NUNCA** `git add modules/` ni `git add notes/`.
- **NUNCA pusheás.** El push lo hace exclusivamente el chat consolidador.
- **NO tocás** `notes/state/STATE-agencia.md`, `notes/daily/`, ni `CLAUDE.md`. Eso es del consolidador.

**Pre-flight obligatorio antes de cualquier operación git:**
```bash
pwd
git branch --show-current
git status
git log -1 --oneline
```

**Al cerrar la sesión:** cola accionable + bulks para el consolidador vía
`notes/prompts/sesion/cierre-acotado.md` (NO `cierre-meta`).

**Tono:** factual, conciso, español rioplatense. No inventes ASINs, keywords, métricas ni
decisiones. Si la data no alcanza, decilo.

---

## 2. Método — el 360°

Corré el 360° siguiendo **`notes/sops/SOP-PPC-360-de-reporte-a-decision.md` v1.4**
(PARTE A CORE + **PARTE C — ANEXO MX · LTD / Love To Dream**).

**Son 9 reportes** (no el método viejo de 4-5 fuentes):

```
STR → SQP → cruzado STR×SQP → BSR by child → Campaign → Advertised → Placement → Targeting → BSE
```

**Las 4 reglas previas** — se aplican ANTES de mirar un número:
1. **D-3** — ventana de atribución: los últimos 3 días no son evaluables para conversión.
2. **Cluster / canibalización** — agregá close variants antes de calcular CVR o ACoS.
3. **Censo / mapa de ASINs** — ningún archivo es censo; verificá el mapa contra el Advertised.
4. **Runway de stock antes de escalar** — `<15d` no escalar · `15-25d` con cuidado · `>25d`
   escalable · `>300d` clearance. Toda alerta de stock se registra con destinatario,
   controlador y fecha de control.

**Learnings críticos vigentes (SOP v1.2–v1.4):**
- ⚠️ **`Top-of-search Impression Share` del Targeting report viene en FRACCIÓN DECIMAL**
  (`0.077` = 7.7%). Parsearlo como porcentaje da "ToS IS 0%" falso en todas las filas e
  **invierte el diagnóstico** (parece "no aparecemos arriba" cuando la realidad es
  "aparecemos y perdemos la subasta" — acciones opuestas).
- ⚠️ **Nunca heredar datos de ASIN entre WoW.** Cuando llega un WoW nuevo, todo dato de ASIN
  se recalcula contra el archivo fresco. **Caso real de esta cuenta (jul-2026): 3 de 4 ASINs
  mostraban crecimiento (+507%, +198%, +100%) cuando en realidad habían caído
  (−60%, −11,5%, −4,6%).** Se detectó en revisión antes de enviar al cliente.
- ⚠️ **Cruzar candidatos a negativo contra el BSE ANTES de generar** — para no duplicar negativos
  vigentes y, sobre todo, para no negativizar ASINs propios (ver near-miss abajo).

**Cierre obligatorio — paso 13:** resumen semanal al canal interno de la marca según
`notes/sops/plantilla-resumen-semanal-slack.md`. Los 4 campos son obligatorios:
1. **Objetivo general de optimización** (el para qué, antes del qué).
2. **Limpieza de WAS** — si se hizo, cuándo, y con **grado**: profunda (auditoría completa de
   toda la cuenta, sale del 360°) o no profunda (ajuste puntual sobre las que sangraban).
3. **Campañas lanzadas** — reportar **los dos números**: budget configurado $/día **y** consumo
   esperado ~$/mes según histórico. Reportar solo el configurado infla la cifra.
4. **📣 El emoji `:mega:` va siempre en el mensaje.**

---

## 3. Estado vivo — LEER, no hardcodear

Antes de arrancar, leé en este orden para el estado real de la cuenta:

1. `notes/brands/ltd/LTD.md` — **última entrada** + la sección canónica
   **🦸 Heroes oficiales LTD MX** al inicio del archivo (fuente única de verdad de heroes;
   NO usar listas de sesiones viejas). De acá salen: heroes del momento, stock, qué sangra hoy,
   bulks aplicados, alarmas abiertas, pendientes con fecha.
2. La sección **LTD** de `notes/state/STATE-agencia.md`.
3. El daily más reciente que mencione LTD en `notes/daily/`.
4. `notes/sops/amazon-bulk-upload-guide.md` — si la tarea involucra bulks.

**No asumas nada de esta sección desde memoria.** Heroes, stock, tests en curso, estado de
Atom11 y pendientes cambian semana a semana.

---

## 4. Contexto ESTABLE de la cuenta

### Marketplace y aritmética

**Amazon.com.mx (MX).** IVA 16% incluido en el precio.

```
Neto_LTD = PVP / 1.16
```

Validación del `/1.16`: ✅ confirmada a nivel estructural con data real de MX (una venta
reportada rinde ~0,85 del PVP lista). Para el clavado exacto (0,862), tomar una venta de una
sola unidad a precio lista y verificar `Sales / PVP`.

Anexo aplicable: **PARTE C — ANEXO MX · LTD** del SOP.

### Config del Anexo MX-LTD

| Parámetro | Valor |
|---|---|
| Ticket | $809 – $1.069 MXN · **modal/grueso $859** (familia Swaddle UP regular) |
| Neto típico | `859 / 1,16` = **$740,5 MXN** |
| BE ACoS | sin COGS → **estimación etiquetada**. Proxy de trabajo: target ACoS de cuenta ~25-30% (**NO** es BE rentable) |
| BE CPC | `740,5 × 0,30 × CVR_cluster` — siempre `(est. — sin COGS)` |
| Stop-loss por KEYWORD | `neto × 10%` ≈ **$74 MXN**, acotado **[$60, $150] MXN** |
| Stop-loss por MODELO | `neto × 0,28` ≈ **$207 MXN** (banda media) |

Transition ($1.040–1.069) es volumen bajo — no arrastra el modal.

### Categoría y equipo

**Categoría:** sacos de dormir para bebé (familia **Swaddle UP**). Tomada por la agencia en
marzo 2026.

| Contacto | Rol |
|---|---|
| **Agustín (Favano)** | **Account Manager — AM de la cuenta**, maneja la conversación con cliente |
| Adam | Sales Director (interno) — escalations |
| Aaron | Compliance — directivas de inventario y compliance |

### 🔑 El hallazgo central de esta cuenta — el umbral de precio ≤1.2x

**LTD necesita estar a ≤1.2x del precio de mercado para convertir en genéricos.**

Validado dos veces y por dos caminos que convergen (BE CPC → cae bajo el piso de subasta ·
piso/SQP → ImpShr decente con PurShr cero). El 16-jul se **reprodujo con precio real, no proxy**:
el SQP Brand View trae `Clicks: Price (Median)` vs `Clicks: Brand Price (Median)` → ratio directo.

| Query | Vol/mes | ImpShr | PurShr | Ratio |
|---|---|---|---|---|
| swaddle up | 94 | 77,3% | 100% | 1,00x |
| love to dream swaddle | 508 | 92,7% | 100% | 1,00x |
| swaddle | 1.509 | 33,0% | 50% | 1,18x |
| swaddle para bebe 0-3 | 2.178 | 26,5% | 35,3% | 1,23x |
| **— umbral ≈ 1.2x —** | | | | |
| costalito para dormir bebe | 572 | 11,6% | **0%** | 1,41x |
| bolsa de dormir bebe | 291 | 13,7% | **0%** | 1,44x |
| saco de dormir bebe | 4.748 | 8,4% | **0%** | 1,75x |
| saco para dormir bebe | 10.666 | 8,5% | 1,7% | 1,80x |

**El corte es limpio, sin casos intermedios que rompan la regla:** hasta 1,23x convierte,
desde 1,41x no.

**Consecuencia operativa:** no tiene sentido pujar en genéricos con gap > 1,2x. No es problema
de bid ni de copy — **es precio**. Cualquier decisión futura de bids sobre genéricos depende de
este umbral. LTD gana en producto diferenciado (`swaddle`, `swaddle up`, nichos recién nacido).

Corolario ya aplicado: las EXACT RANK sobre genéricos tipo `saco de dormir` son
**price-traps sistémicos** — el umbral explica por qué la auditoría RANK (abierta desde abril)
quedó resuelta.

### Mapa de ASINs

**Fuente única de verdad:** sección **🦸 Heroes oficiales LTD MX (canónico)** al inicio de
`notes/brands/ltd/LTD.md` — **35 ASINs activos**. Supera la progresión histórica 10 → 19 y el
snapshot de marzo. **NO consultar listas de sesiones previas.**

Estructura del catálogo por etapa (familias Swaddle UP):
- **SU-NB** — recién nacido 0-3m
- **SU-S** — small
- **SU-M** — 6-12m
- **SU-T** — transición 12-18m

**🔴 `B09MG1PM6L` (OLV S) — hero con hold vigente.** El hold sigue, pero **el motivo cambió**:
- Origen (9-jul): 2 unidades de stock y directiva del cliente de **NO restock**.
- Ahora (WoW 05–18 jul): se suma un desplome de CVR **con tráfico intacto** —
  **846 sesiones, CVR 0,12%** ($1.619 spend → $809 venta), cuando en el 360° era ROAS 5,5 y
  #1 en gasto.

**Investigar la causa (stock / precio / ficha) ANTES de resolver el hold.** Y usar BSE fresco:
el borrador de pausa armado en julio quedó stale (los Ad IDs pueden haber cambiado).

**Nota de directiva:** el cliente dijo **NO hay restock** — el foco va a SKUs con stock profundo.
El detalle vivo de stock por ASIN está en la brand note, no acá.

### ⚠️ Near-miss documentado — ASINs propios entre candidatos a negativizar

`B0CLCBQQN2` y `B09MFZVWYH` aparecían en el STR como candidatos legítimos a
Negative Product Targeting (gasto sin conversión). **Son ASINs propios de LTD.**
Solo el cruce contra el BSE / mapa los detectó. Negativizarlos habría bloqueado tráfico al
propio catálogo.

**Regla derivada (aplica siempre):** antes de negativizar cualquier cosa que parezca un ASIN,
cruzar contra el BSE y contra el mapa de ASINs propios.

### ⚠️ Regla crítica de la cuenta — cruzar STR con campañas activas antes de subir bulk

Antes de subir cualquier bulk de negativos, cruzar el STR contra las campañas/keywords
sembradas activas. Hay negativos vigentes en el BSE (`saco para dormir bebe`,
`saco de dormir bebe`, `cobijas`, `baby`) que **siguen apareciendo con gasto en el STR** —
hipótesis: negativo phrase sin cobertura completa de ad groups, o entran variantes.
La auditoría ad-group por ad-group está abierta.

### Naming convention — heterogéneo por diseño histórico

LTD **no migró** a un naming híbrido único. Conviven tres patrones, todos vigentes:

```
SU-[FAMILIA] | MX | SP | KWS | EXACT | RANK | M4 [keyword corta]
LTD | MX | SP - KWS | BRAND - DEFENSE [descriptor]
SU-[FAMILIA] | MX | SP | PT | DEFENSIVE | OWN
```

Ejemplos reales:
- `SU-NB | MX | SP | KWS | EXACT | RANK | M4 swaddle 0-3`
- `SU-M | MX | SP | KWS | EXACT | RANK | M4 saquito 6-12`
- `LTD | MX | SP - KWS | BRAND - DEFENSE ALL PRODUCTS NEW`
- `SU-M | MX | SP | PT | DEFENSIVE | OWN`

**No reescribir naming legacy.** La clasificación por objetivo se hace a mano en esta cuenta.

### Portfolios vigentes

- Swaddle UP para recién nacidos (0-3 meses)
- Swaddle UP para bebés de 6-12 meses
- Sacos de transición con un toque de diseño
- `SU | MX | CORE | 0-12M | CATEGORY`
- LTD Brand Defense
- Scavenger

### Gotchas de bulk — puntero + los específicos de MX/LTD

Fuente de verdad: **`notes/sops/amazon-bulk-upload-guide.md`**. Aplican los 8 base
(entities de negativos, IDs numéricos desde BSE, Start Date como texto, Google Sheets corrompe
IDs, caracteres especiales, zombies del Campaign Analyzer, schema SD ≠ SP, hoja única).

**Los que mordieron en esta cuenta:**

- **IDs numéricos leídos como float.** pandas agrega `.0` a los IDs y el bulk falla.
  Normalizar con `.astype("Int64").astype(str)` o `str(v).split('.')[0]` + formato de celda `@`.
  (La v1 del biddown del 03/07 falló exactamente por esto.)
- **UPDATE hace ROLLBACK TOTAL ante un error; CREATE procesa fila a fila.** Filtrar
  `State != 'archived'` y campañas `ENDED` **antes** de generar cualquier UPDATE.
- **Filas `Entity = Campaign` con `Start Date` o `State` vacíos se leen como "0" → upload Failed.**
  Poblarlas con el valor REAL aunque no se cambien: `Start Date` como TEXTO `yyyyMMdd`,
  `State` con el estado actual. **Aplica también a los updates de budget** (son filas
  `Entity = Campaign`).
- **Budget Rules: por UI, no por bulk.** La hoja "Budget Rules" del BSE viene vacía y los enums
  no son confiables → riesgo de Failed. Por UI son 60 segundos y auto-revierte.
- **"Failed" ≠ fallo total.** Leer siempre el Processing Summary. `already exists` en un CREATE
  no es falla real — es duplicado preexistente, se descarta.
- **Negative Product Targeting es ad-group-level** — requiere Ad Group ID.
- **ASINs son marketplace-specific** — un ASIN de US no existe necesariamente en MX. Validar el
  marketplace antes de generar PAT contra competidores.

### Reglas Capybaras específicas

- Bulk Excel obligatorio cuando el volumen supera 5 campañas.
- **Portfolio ID vacío** en los bulks — asignar manual post-upload.
- 31 columnas Capybaras 2026 (incluye `Sites`; ojo: `"amazon.com.mx"` como valor es inválido).
- Match: **EXACT priorizado** en campañas RANK.
- Bidding: Fixed bid + Placement ToS +50% para EXACT RANK.
- **Placement solo sube, nunca baja** — no existe modificador negativo (rango 0% a +900%).
- Criterio de éxito de un test de ToS = **impression share, no ventas**. Declararlo ANTES
  de correr el test.

---

## 🔗 Referencias cruzadas

- `[[LTD]]` — brand note principal (**el estado vivo y los heroes canónicos salen de acá**)
- `[[SOP-PPC-360-de-reporte-a-decision]]` — método v1.4 (CORE + Anexo MX-LTD)
- `[[plantilla-resumen-semanal-slack]]` — paso 13 obligatorio
- `[[amazon-bulk-upload-guide]]` — gotchas de bulk format
- `[[STATE-agencia]]` — estado global (lectura; **no se escribe desde el frente**)
- `[[cierre-acotado]]` — cierre multi-frente
- `[[CLAUDE]]` — convenciones del vault

---

## ✅ Validación del prompt

Validado en sesión completa LTD del 2026-05-20 (análisis 360°, generación de bulks correctivos,
cruzamiento de hallazgos, detección de bleeders/winners — todo funcional). Las 4 mejoras
detectadas entonces ya están incorporadas arriba: validar marketplace antes de PAT contra
competidores · validación cruzada de KWs sembradas antes de negativos · placeholders de ID
para bulks CREATE · filtrar archived/ENDED antes de UPDATE.
