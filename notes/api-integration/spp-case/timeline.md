# Timeline — Caso SPP Submission

## 2026-04-14 · Decisión arquitectura inicial

- Arvin (dev externo) propone camino Solution Provider público (1-4 semanas, papeleo)
- Lenin corrige a Private Developer (formulario online, gratis, 10 min)
- Documentado en `capybaras_api_pipeline_internal.html`
- **Decisión cambiada después**: Freddy pidió camino completo Solution Provider Profile

## 2026-05-14 18:48 ART · Pedido inicial Slack

- Freddy pide ayuda a Lenin con sección Security Controls del formulario SPP
- 7 preguntas Yes/No que requieren respaldo documental

## 2026-05-15 15:00-18:00 ART · Decision Pack v1

Output completo de la sesión:

- `Capybaras_SPP_Decision_Pack_15May2026.html` (68KB, 1899 LOC)
- `notes/sops/incident-response-plan.md` (400+ líneas, alineado DPP §2.5 + NIST 800-61)
- Auditoría git history con regex sobre keys/tokens/passwords → repo limpio
- 2 textareas Privacy listas para copy-paste

Decisiones cerradas:

- 5 roles solicitados: Product Listing, Pricing, Selling Partner Insights, Brand Analytics, Inventory & Order Tracking
- NO Restricted Roles (evita architecture review)
- IMPOC Opción C: Freddy Primary + Lenin Technical Lead, escalation 2h
- Approved Users: solo Freddy + Lenin
- Higiene pendiente (no afecta SPP): rotar password `Capybaras2026!` documentado en commits

## 2026-05-18 · Form Companion PDF

- Output: `Capybaras_SPP_Form_Completed_18May2026.html`
- Replica visualmente el formulario online con respuestas precompletadas
- Agrega: Primary business activity textarea (500 char) + Use Cases textarea (5000 char)
- Mantiene los 5 roles del Decision Pack

## 2026-05-20 mañana · Doc Word de Freddy

- Freddy envía a Lenin el doc Word con las textareas que va a pegar al formulario
- **Cambios respecto Decision Pack 15/05**:
  - 8 roles (agregó Finance and Accounting, Amazon Fulfillment, Buyer Communication)
  - Outside parties: agregó MerchantSpring, sacó Atom11
  - Use Cases textarea con 8 bullets (uno por role)

## 2026-05-20 ~17:30 ART · Revisión Lenin

- Lenin detecta escalación de scope vs Decision Pack 15/05
- Análisis cruzado contra docs oficiales Amazon SP-API
- 4 puntos cuestionados: 3 roles nuevos + Atom11 missing en external sources
- Mensaje preparado para Freddy con 4 preguntas Sí/No

## 2026-05-20 ~17:45 ART · Lenin recalibra

- Freddy responde que TODAS las áreas operativas son posibles en Capybaras
- Lenin retira la alerta sobre roles "innecesarios"
- 12 roles son defendibles porque cubren áreas operativas reales o aspiracionales

## 2026-05-20 17:51 ART · Submit

- Screenshot de Freddy muestra 12 roles marcados (4 más que el doc Word)
- Roles extra agregados al marcar: Buyer Solicitation, Sustainability Certification, Amazon Logistics, AWD
- Freddy saca correctamente las 2 de Open Banking EU (requieren orgID PSDGB-FCA-XXXXX)

## 2026-05-20 17:55 ART · Gap detectado

- Lenin detecta mismatch: 12 roles marcados vs 8 use cases en textarea
- 4 bullets de amendment redactados preventivamente para uso reactivo

## 2026-05-20 18:02 ART · Confirmación Freddy

- Freddy confirma: "ya está, esperemos que dicen (dudo que lo lean)"
- Decisión Lenin: NO insistir con amendment proactivo
- Guardar bullets para respuesta reactiva si Amazon pide aclaración

## Estado al cierre de 2026-05-20

- ✅ Submission enviada
- ✅ Bullets de amendment listos en amendment-bullets.md
- ⏳ Esperando respuesta Amazon (días-semanas típicamente)
- ⏳ Próxima acción: monitoring del email freddy@capybaras.agency por updates del case
