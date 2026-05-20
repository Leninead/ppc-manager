---
tipo: prompt-arranque-cliente
cliente: optipet
nivel: cargado
actualizado: 2026-05-19
proxima_actualizacion: cierre próxima sesión OPTIPET
parent_asin: B0H12ZXVPF
flavorboost_parent_asin: B0H16N6SHP
status_catalogo: Adult variation family 100% operativa (65u FBA, Buy Box). FlavorBoost: 3 children creados al 2026-05-19 — Hígado Inactive (compliance, peso corregido 297g), Pollo en review 48h (B0H2CFM37X), Pulmón con ASIN viejo heredado (B00ZCVB3Z8, requiere investigación)
status_ppc: sin historial al 2026-05-14 — agregar cuando se inicien campañas
status_compliance: Hígado bloqueado por política GRLKLZ6WQ9R259LC Pet Consumables MX — esperando docs cliente
status_upcs_flavorboost: Pool ADAM REQUEST: 951536+934935 CONTAMINADOS en GS1 (8541 con Cat Treats Inactive). 663064+848478 funcionaron parcialmente: 848478→Pollo limpio, 663064→Pulmón heredó ASIN viejo. Pendiente investigación B00ZCVB3Z8.
---

# Arranque Sesión — OPTIPET

> Prompt customizado para arrancar cualquier sesión del cliente personal OPTIPET.
> Pegar el bloque XML del primer code block en chat nuevo de Claude.ai.
> Se actualiza al cierre de cada sesión con el delta — el bloque que se pega
> es estable; el delta vive en las secciones de "Estado actual" y "Pendientes".

---

## 🚀 Bloque para pegar al chat (estable)

```xml
<arranque_sesion cliente="optipet">

Hola Claude. Soy Lenin. Vengo a trabajar sesión OPTIPET — cliente personal mío, gestión directa fuera de cualquier agencia.

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, conectado a GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto Claude.
Cliente: OPTIPET — Amazon MX, suplementos alimenticios premium para perros adultos.
Relación: cliente personal directo (no es cuenta de agencia, no aplica workflow Capybaras).
PPC: sin historial al 2026-05-08 — agregar cuando se inicien campañas.
</contexto_proyecto>

<lectura_obligatoria_en_orden>
1. notes/clients/optipet/optipet.md (brand note: catálogo, hitos, pendientes activos)
2. notes/knowledge/2026-05-08-variation-builder-flat-file-format.md (formato flat file + caso de éxito OPTIPET)
3. notes/clients/optipet/flat-files/ (listar archivos disponibles para auditoría rápida)
4. El daily más reciente que mencione OPTIPET (buscar en notes/daily/ por "OPTIPET" o por fecha del último hito)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_optipet>

## Variation Family activa (creada 2026-05-08)

| Rol | ASIN | SKU | Sabor | Estado |
|---|---|---|---|---|
| Parent | B0H12ZXVPF | OPTIPET_ADULT_PARENT | (referente) | Asignado por Amazon post-feed |
| Child | B0G6VWT7RB | OPTIPETVITALITY | Vitality | OOS · 24u inbound |
| Child | B0G6TW7G12 | OPTIPETSKINCOAT | Skin and Coat | OOS · 24u inbound |
| Child | B0G6TPVT2G | OPTIPETHEALTHYGUT | Healthy Gut | OOS · 24u inbound |

- Theme variation: Sabor con valores custom en inglés (validado en MX).
- Browse node: 11601177001 (suplementos en polvo).
- Stock total FBA: 0 disponibles · 72u inbound.
- FBM zombi apagado pre-feed: OPTIPETSKINCOATFBA (compartía ASIN B0G6TW7G12).

## Reglas duras del catálogo OPTIPET

- SKUs FBA-only por política del cliente. Si aparece un FBM nuevo compartiendo ASIN con un child, apagar antes de cualquier cambio en variations.
- Parent NO comprable: solo referente. Children mantienen sus ASINs originales y son los que venden.
- Reviews y BSR se consolidan a nivel parent post-agrupación (monitorear cuando lleguen ventas).
- Theme `Sabor` (col 39 `flavor_name`) acepta valores custom en inglés sin warnings.

## PPC: sin historial al 2026-05-08 — agregar cuando se inicien campañas

</conocimiento_operativo_optipet>

<flujo_de_arranque>
Una vez leído todo el contexto:

1. Confirmá brevemente que entendiste:
   - Estado actual de la Variation Family (parent + children, stock, OOS).
   - Hitos completados de la última sesión (qué se hizo y cuándo).
   - Pendientes activos del cliente (los que están en optipet.md).
   - Si hay flat files nuevos planeados o cambios de catálogo en pipeline.

2. Recordame correr antes de cualquier trabajo:
   - `cd C:\proyectos\ppc-manager && git status && git pull`
   - `git add . && git commit -m "checkpoint: antes de [tarea de hoy]"`

3. Preguntame qué queremos atacar hoy. NO arranques trabajo nuevo sin esa confirmación.

4. Si la tarea de hoy involucra un flat file nuevo → revisar primero notes/knowledge/2026-05-08-variation-builder-flat-file-format.md (gotchas + caso de éxito) y aplicar la regla "1 ASIN ≠ 2 children" antes de generar nada.

5. Si la tarea es PPC (primera vez) → tratar como greenfield: definir naming convention propia, decidir arquitectura (campañas por child vs apuntando al parent), y NO copiar convenciones de otras cuentas sin validar que apliquen a este catálogo.
</flujo_de_arranque>

<rituales_obligatorios>
Al final de cada sesión, recordame ejecutar (en este orden estricto):

1. Update de los archivos del cliente:
   - notes/clients/optipet/optipet.md (catálogo, hitos, pendientes)
   - notes/clients/optipet/flat-files/ (si se subió un flat file nuevo, agregar snapshot)
   - notes/daily/YYYY-MM-DD.md (resumen de la sesión)

2. Update de este mismo archivo: notes/prompts/sesion/clientes/arranque-optipet.md
   - Sección "Estado actual"
   - Sección "Pendientes activos"
   - Sección "Próxima evaluación"
   - Sección "Historial de actualizaciones"

3. Git commit + push:
   - `git add .`
   - `git commit -m "feat/fix/improve/docs: optipet [descripción concreta]"`
   - `git push`

4. Refresh manual en proyecto Claude (si aplica):
   - Ir al proyecto en claude.ai
   - "Add content from GitHub" → seleccionar archivos modificados
   - Sincronizar

5. Generar prompt de arranque para próxima sesión (si quedó algo a medias).

Si saltás cualquier paso de los 3 primeros, el próximo chat lee data stale y todo se rompe.
</rituales_obligatorios>

</arranque_sesion>
```

---

## 📊 Estado actual del cliente

> Esta sección se actualiza al cierre de cada sesión.

### Snapshot al cierre 2026-05-14

#### Variation Family #1 — Adult (creada 2026-05-08, 100% operativa)
| Child | ASIN | Stock FBA | Estado |
|---|---|---|---|
| Vitality | B0G6VWT7RB | 22u | Active, Buy Box ganado |
| Skin and Coat | B0G6TW7G12 | 22u | Active, Buy Box ganado |
| Healthy Gut | B0G6TPVT2G | 21u | Active, Buy Box ganado |

Total 65u FBA · Precio MXN $649 · Parent B0H12ZXVPF (OPTIPET_ADULT_PARENT)

⚠️ FBM zombi OPTIPETSKINCOATFBA reapareció Active el 2026-05-06 (15u, mismo ASIN B0G6TW7G12) — pendiente apagar con Close listing real.

#### Variation Family #2 — Flavor Boost (iniciada 2026-05-09, ESPERANDO LOCK UPC)
| SKU | ASIN | Estado |
|---|---|---|
| OPTIPET_FLAVORBOOST_PARENT | B0H16N6SHP | Inactive (consecuencia compliance del Hígado) |
| OPTIPETFLAVORHIGADO (Hígado y Espirulina) | B0H16T5H18 | Inactive — Review blocked reason (compliance MAVERiCK MX) — track separado |
| OPTIPETFLAVORPULMON (Pulmón y Melena de León) | — | Sin crear — UPC nuevo disponible en pool, esperando lock Mario |
| OPTIPETFLAVORPOLLO (Pollo y Cúrcuma) | — | Sin crear — UPC nuevo disponible en pool, esperando lock Mario |

**Pool de UPCs nuevos disponibles** (master sheet rows 21-24, al 2026-05-14):
- 610655663064 (codebars en Drive folder asignado)
- 610655848478
- 610655951536
- 610655934935

Codebars físicos: Drive folder "ADAM CODEBARS" (4 formatos × 4 UPCs, generados por Mario 18 sept 2025).

Compliance issue activo:
- Policy: `GRLKLZ6WQ9R259LC` Pet Consumables: Food and Product Safety Issues
- Fecha violación: 2026-05-10
- Estado: Listing removed, esperando upload de docs vía panel "Add Compliance" en Safety & Compliance tab del listing

---

## ⏰ Pendientes activos

> Esta sección se actualiza al cierre de cada sesión.

### Bloqueantes — estado al 2026-05-19

1. **B00ZCVB3Z8 (Pulmón) requiere investigación** — UPC 663064 ya estaba en catálogo Amazon vinculado a otro producto. Si es OPTIPET cerrable → cerrar + reintentar. Si es otro seller → pedir UPC fresco a Mario.
2. **Pollo B0H2CFM37X en review 48h** — esperar hasta ~2026-05-21 22:00 para confirmar Active.
3. **URLs TBD persisten en backend** (gotcha 17) — sobreescribir cuando lleguen URLs públicas reales.

### Bloqueantes del lado cliente (sin cambio)

5. **Compliance docs Hígado** — esperando del cliente:
   - COA del producto
   - Etiqueta física alta resolución (frente + dorso de los 3 sabores)
   - Ficha técnica con análisis garantizado
   - Status regulatorio (¿desregulado clase III o código SAGARPA 8 dígitos?)
   - Certificación Non-GMO formal (sin esto, sacar claim del título)

### Operativos no bloqueantes

6. **Imágenes Flavor Boost en URLs públicas**: re-hostear desde Drive a host directo (.jpg/.png)
7. **OPTICAT roadmap Amazon**: Mario manda fotos 14/05; decidir si entra al pipeline
8. **FBM zombi OPTIPETSKINCOATFBA**: Close listing real (reapareció 2026-05-06)
9. **Variation Family Adult**: fecha launch oficial, hero del variation, A+ Content por child, Brand Store
10. **PPC greenfield**: sin historial al 2026-05-14, definir naming convention + arquitectura

---

## ⏭️ Próximas evaluaciones

- **+24h (2026-05-20)**: investigar B00ZCVB3Z8 en amazon.com.mx, decidir destrabe Pulmón
- **+48h (2026-05-21)**: verificar Pollo B0H2CFM37X salió de review
- **Cuando responda Mario al mensaje del 2026-05-14** → confirmar asignación UPC final, generar v5 flat file local, subir a Amazon
- **+24-72h post upload v5** → verificar ASINs asignados a OPTIPETFLAVORPULMON + OPTIPETFLAVORPOLLO en Seller Central
- **Cuando lleguen fotos OPTICAT** (Mario, esperadas 14/05) → revisar y decidir si entra al pipeline Amazon
- **Cuando lleguen docs compliance Hígado** (cliente) → upload al panel "Add Compliance" del listing OPTIPETFLAVORHIGADO
- **48h sin respuesta de Mario** → follow-up vía Adam o directo

---

## 🎯 Prompt para la próxima sesión

> Esta sección la actualiza Claude al cierre. El próximo chat la lee como parte del archivo al arrancar.

**Estado al arrancar**: post sesión 2026-05-19 (v5 + v6 uploads). Pollo creado limpio (B0H2CFM37X en review 48h). Pulmón con ASIN viejo heredado (B00ZCVB3Z8, requiere chequeo). Hígado peso corregido 297g, sigue Inactive por compliance. UPCs 951536/934935 contaminados en GS1 — descartados. UPC 848478 limpio. UPC 663064 contaminado por linkage previo en catálogo Amazon.

**Contexto previo (mensaje 2026-05-14 a Mario)**: esperando respuesta de Mario (PETSA) al mensaje enviado 2026-05-14 al chat INASA. El mensaje tiene 3 preguntas abiertas sobre:

1. Preferencia de asignación UPC → sabor (de 4 UPCs nuevos disponibles en pool ADAM REQUEST master sheet rows 21-24)
2. Estado actual de cajas físicas Flavor Boost (información necesaria para coordinar inbound)
3. Confirmación de update GS1 + master sheet rows 13/15 una vez locked la asignación

### Cuando Mario responda — flujo previsto

1. **Si Mario tiene preferencia de asignación UPC→sabor** → tomar esa.
   **Si dice que son intercambiables** → asignación sugerida (queda a decisión Lenin al momento):
   - `610655663064` → OPTIPETFLAVORPULMON (Pulmón y Melena de León)
   - `610655848478` → OPTIPETFLAVORPOLLO (Pollo y Cúrcuma)
   - Pool sobrante (ADAM REQUEST): `610655951536` + `610655934935`

2. **Generar v5 flat file** en local con estos cambios respecto al v4:
   - UPCs nuevos asignados a Pulmón y Pollo
   - `package_weight = 297 GR` (era `360 GR` en v4 — confirmado por master sheet col 31)
   - Resto idéntico al v4 (Hígado se omite — ya creado, sigue su propio track de compliance)
   - Guardar snapshot en `notes/clients/optipet/flat-files/OPTIPET_FlavorBoost_2026-05-XX_v5.txt`

3. **Subir v5 a Amazon** vía panel "Add Products via Upload" (mismo flujo que v1-v4).

4. **+24-72h post upload** → verificar ASINs asignados a Pulmón y Pollo. Capturar y agregar como hito a `optipet.md` + caso de éxito completo al knowledge `2026-05-08-variation-builder-flat-file-format.md`.

5. **Coordinar inbound** según respuesta de Mario sobre estado de cajas.

### Información clave que necesita estar a mano

- **4 UPCs nuevos en pool**: 610655663064, 610655848478, 610655951536, 610655934935
- **Codebars físicos**: Drive folder "ADAM CODEBARS" (4 formatos × 4 UPCs)
- **Peso bruto paquete**: 297g (confirmado master sheet col 31, rows 13-15)
- **Peso neto producto**: 270g
- **Dimensiones**: 9.26 × 9.26 × 9.46 cm
- **Pricing**: $349 MXN Amazon (sin IVA $303.48)
- **Parent existente**: OPTIPET_FLAVORBOOST_PARENT · ASIN B0H16N6SHP
- **Sabores reales (master sheet)**: "lung y melena de leon" / "Chicken y curcuma"
- **UPCs viejos colisionantes** (reservados permanentemente a Cat Treats Inactive): 613365694298 (Tuna Bites B0GPPR1ZGC) + 613365971085 (Chicken Bites B0GPPXWPB1)

### Reglas duras heredadas (no romper)

- **NO asumir nada que no haya dicho Mario explícitamente** (decisión epistemológica 2026-05-14). En particular: no asumir estado de cajas físicas, no asumir asignación de UPC, no asumir timing de inbound. Preguntar primero.
- **NO esperar Hígado compliance** para subir Pulmón y Pollo — tracks separados.
- **Subir v5 a Amazon es seguro sin esperar update GS1** — Amazon no valida la asociación producto-específica de GS1 en tiempo real. El update GS1 corre en paralelo.

### Trigger para arrancar la próxima sesión

- Llegó respuesta de Mario al WhatsApp / chat INASA, **o**
- Pasaron 48h sin respuesta y hay que hacer follow-up

---

## 🧠 Conocimiento operativo permanente

> Esta sección NO se actualiza por cierre de sesión. Es estable.
> Cambios solo si se redefine algo estructural.

### Relación comercial
- Cliente personal directo de Lenin Acosta — gestión 1:1 sin equipo intermedio.
- No aplica workflow de agencia (briefings, status calls, equipos compartidos).
- Decisiones operativas se toman directo entre Lenin y el cliente.

### Reglas duras del catálogo
- **1 ASIN ≠ 2 children**: si producto tiene FBA + FBM mismo ASIN, elegir UNO. Apagar el otro con `Close listing` antes de cualquier feed.
- **SKUs FBA-only** por política del cliente. FBMs nuevos compartiendo ASIN con un child → apagar antes de tocar variations.
- **Browse node validado**: `11601177001` para suplementos en polvo OPTIPET.
- **Theme `Sabor` con custom values**: válido en MX, sin warnings.
- **Política compliance Amazon MX para suplementos pet**: `GRLKLZ6WQ9R259LC`. URL: https://sellercentral.amazon.com/help/hub/reference/GRLKLZ6WQ9R259LC. Amazon requiere docs específicos del producto (no solo del fabricante) antes de permitir venta.
- **Master Sheet INASA es fuente de verdad** para datos físicos de producto. SKU naming interno ≠ Amazon (master usa OP-FLB-*, Amazon usa OPTIPETFLAVOR*).
- **Línea OPTICAT existe en master sheet** pero NO lanzada en Amazon al 2026-05-12. 3 SKUs: OPTICAT_CHICKEN, OPTICAT_LIVER, OPTICAT_TUNA.

### Histórico de operaciones
- **2026-05-08**: Variation Family Adult creada (3 children FBA bajo parent `B0H12ZXVPF`).

---

## 📜 Historial de actualizaciones

> Una línea por sesión. Más reciente arriba.

- **2026-05-19**: Uploads v5 + v6 FlavorBoost. Pollo creado limpio (B0H2CFM37X review 48h), Pulmón con ASIN viejo heredado (B00ZCVB3Z8 requiere investigación), Hígado peso 297g aplicado. Descubiertas 4 gotchas nuevas (unit_count+unit_count_type petfood MX 2026, PartialUpdate variation child requiere flavor_name, UPCs pueden venir contaminados de GS1, campos vacíos no nulean). Template version 2026.0508 actualizada.
- **2026-05-14**: respuesta Mario (4 UPCs nuevos en pool ADAM REQUEST master sheet rows 21-24, codebars físicos en Drive folder ADAM CODEBARS), peso bruto paquete CONFIRMADO 297g (resuelve pendiente vs 360g v4), mensaje a Mario enviado en formato pregunta abierta (no asumir estado cajas), decisión epistemológica "no asumir nada", hallazgo lateral UPC duplicado VITALPET. Esperando respuesta Mario sobre asignación UPC + estado packaging.
- **2026-05-12**: diagnóstico compliance Hígado (policy GRLKLZ6WQ9R259LC), análisis Innasa Master Sheet (ingredientes reales confirmados, pricing oficial $349, línea OPTICAT identificada), comunicación con Adam (escribe directo a chat INASA, esperando framing). Adult variation 100% operativa con 65u FBA. FBM zombi reapareció. Cat Treats Inactive NO se eliminan por decisión del cliente.
- **2026-05-08** (creación inicial): post operación puntual de Variation Family. 3 children FBA agrupados bajo parent `OPTIPET_ADULT_PARENT` (`B0H12ZXVPF`). Theme `Sabor` con valores custom en inglés. Feed batch `50059020581` 4/4 successful. Pre-flight cleanup: FBM zombi `OPTIPETSKINCOATFBA` apagado. Stock FBA 0 disponibles · 72u inbound.

---

## 🔗 Referencias cruzadas

- `[[optipet]]` — brand note principal con catálogo + hitos + pendientes activos
- `[[2026-05-08-variation-builder-flat-file-format]]` — formato flat file + caso de éxito #2 OPTIPET + gotchas
- `[[2026-05-08]]` — daily de la sesión inicial
- `[[CLAUDE]]` — instrucciones generales del vault
