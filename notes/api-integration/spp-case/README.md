# Caso SPP — Amazon Solution Provider Portal Submission

**Estado actual**: SUBMITTED · 20/05/2026 17:51 ART · Esperando review Amazon
**Owner**: Lenin Acosta (technical lead) · Freddy Neuman (primary contact, registered with Amazon)
**Tipo de developer**: Private Solution Provider
**URL portal**: https://solutionproviderportal.amazon.com/developer/register

## Resumen ejecutivo

Capybaras aplicó a Amazon SPP como Private Solution Provider para acceso programático
a SP-API. Submission realizada el 20/05 con 12 non-Restricted roles. NO se solicitaron
Restricted Roles (línea roja del Decision Pack 15/05 mantenida) — esto evita architecture
review con Solutions Architect (proceso típico 2-3 meses).

## Roles solicitados

Marcados en el formulario (12 total, todos non-Restricted):

1. Product Listing
2. Pricing
3. Amazon Fulfillment
4. Buyer Communication
5. Buyer Solicitation
6. Selling Partner Insights
7. Finance and Accounting
8. Inventory and Order Tracking
9. Sustainability Certification
10. Amazon Logistics
11. Amazon Warehousing and Distribution
12. Brand Analytics

NO solicitados (por decisión):
- Account Information Service Provider (Open Banking EU - requiere orgID PSDGB-FCA)
- Payment Initiation Service Provider (Open Banking EU - requiere orgID PSDGB-FCA)
- Direct-to-Consumer Shipping (Restricted - dispara architecture review)
- Tax Invoicing (Restricted - dispara architecture review)
- Tax Remittance (Restricted)
- Professional Services (Restricted)

## Gap identificado

Use Cases textarea del submission tiene 8 bullets descritos (roles 1-8).
**Faltan 4 bullets** para los roles 9, 10, 11, 12 (Buyer Solicitation,
Sustainability Certification, Amazon Logistics, AWD).

Mitigación: bullets de amendment guardados en `amendment-bullets.md` listos
para mandar como comment al case si Amazon pregunta por justificación de
esos 4 roles. Probabilidad de scrutiny: media-baja (Private Developer +
non-Restricted suelen pasar con poca revisión).

## Archivos del caso

- `README.md` — este archivo
- `timeline.md` — eventos cronológicos completos
- `amendment-bullets.md` — los 4 bullets faltantes listos para uso reactivo
- `decisions.md` — decisiones cerradas y justificación

## Artefactos relacionados (fuera de esta carpeta)

- `notes/sops/incident-response-plan.md` — IRP formal alineado DPP §2.5
- `Capybaras_SPP_Decision_Pack_15May2026.html` — análisis inicial (root del repo)
- `Capybaras_SPP_Form_Completed_18May2026.html` — form companion visual (root del repo)

## Próximos pasos posibles

| Escenario | Acción | Probabilidad |
|---|---|---|
| Amazon aprueba pasivo, sin preguntas | Activar OAuth flow, generar refresh tokens primer cliente | Alta |
| Amazon pide aclaración sobre roles 9-12 | Mandar amendment-bullets.md como comment al case | Media |
| Amazon pide aclaración general | Responder con referencia al Decision Pack 15/05 | Baja |
| Amazon rechaza algún role específico | Resubmit profile sin ese role o con justificación expandida | Muy baja |
