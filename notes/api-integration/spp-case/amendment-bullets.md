# Amendment Bullets — Roles 9-12 Use Cases

**Para uso reactivo solamente.** Mandar como comment al case de Amazon SI
piden justificación específica de Buyer Solicitation, Sustainability
Certification, Amazon Logistics, o AWD.

**Cómo mandarlos**: en el case que Amazon abra, hay sección de Comments.
Pegar el bullet correspondiente al role consultado. Si preguntan por los 4,
pegar los 4 con un párrafo intro corto.

## Párrafo intro (si se mandan los 4 juntos)

"During internal review post-submission, we identified that the Use Cases
section of our original submission described 8 of the 12 roles requested.
The following are the descriptions for the remaining 4 roles, in the same
format and tone as the original Use Cases textarea."

## Bullet 9 — Buyer Solicitation

**9. Review and feedback solicitation (Buyer Solicitation role)** — Where
authorized by the client, we will use the Solicitations API (specifically
the createProductReviewAndSellerFeedbackSolicitation operation) to send
Amazon-approved review and feedback solicitations on a per-order basis, in
compliance with the applicable Communication Guidelines. Solicitations are
sent exclusively through Amazon-approved templates; no buyer contact data
is retained, exported, or used for marketing or any purpose beyond the
immediate solicitation.

## Bullet 10 — Sustainability Certification

**10. Product sustainability data (Sustainability Certification role)** —
For clients with products that carry sustainability claims or
eco-certifications, we will use the relevant SP-API endpoints to view and
submit product sustainability certifications on behalf of the Authorized
User. This replaces the manual submission workflow in Seller Central and
helps the client maintain compliance with Amazon's Climate Pledge Friendly
and related sustainability programs.

## Bullet 11 — Amazon Logistics

**11. Shipping operations with Amazon as carrier (Amazon Logistics role)** —
For clients that use Amazon Shipping as their fulfillment carrier, we will
use the Amazon Logistics endpoints to track shipments, reconcile shipping
costs, and monitor delivery performance. We do not access buyer PII through
this role; we use only aggregated shipping and tracking data for operational
reporting to the Authorized User.

## Bullet 12 — Amazon Warehousing and Distribution

**12. Amazon Warehousing and Distribution monitoring (Amazon Warehousing
and Distribution role)** — For clients that use the AWD service, we will
use the AWD-related SP-API endpoints to monitor inbound shipments,
inventory levels at AWD facilities, and replenishment flows from AWD to FBA.
This data feeds into the operational dashboards and troubleshooting
workflows we deliver to the Authorized User; we do not share AWD inventory
data with any third party.

## Métricas

- Total caracteres adicionales: ~1,800
- Si se suman al textarea original (4,300 char): final ~6,100 char
- ⚠️ EXCEDE el límite 5000 si se agregan al textarea Use Cases original
- ✅ Como comment al case, NO hay límite duro de caracteres

## Notas adicionales

Cada bullet termina con la misma fórmula defensiva del doc Word original:

- "no PII access"
- "no third-party sharing"
- "exclusively for the Authorized User"

Es el lenguaje que Amazon valida en review.
