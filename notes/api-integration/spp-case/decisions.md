# Decisiones cerradas — Caso SPP

## D1 · 15/05 · Camino registration

**Decisión**: Private Solution Provider (no público)
**Por qué**: Capybaras opera la plataforma internamente para sus propios
clientes autorizados. NO distribuye/revende la aplicación a terceros.
**Implicancia**: review más ágil de Amazon vs. camino público.

## D2 · 15/05 · NO Restricted Roles

**Decisión**: No solicitar ningún role marcado (Restricted)
**Por qué**: Restricted Roles disparan architecture review con Amazon
Solutions Architect (proceso 2-3 meses). Capybaras no necesita PII de
buyers para servicios PPC ni para los roles operativos solicitados.
**Implicancia**: si en futuro se necesita Direct-to-Consumer Shipping o
Tax Invoicing, requerirá resubmit del Developer Profile + architecture
review.

## D3 · 15/05 · IMPOC Opción C

**Decisión**: Freddy Primary + Lenin Technical Lead suplente, escalation 2h
**Por qué**: Freddy es contact registered con Amazon; Lenin maneja el
ppc-manager y la integración técnica.
**Implicancia**: rotación a 24h en caso de licencia/viaje.

## D4 · 15/05 · Approved Users

**Decisión**: Solo Freddy + Lenin acceden a SP-API y al código que la usa
**Por qué**: principle of least privilege según DPP §2.6
**Implicancia**: Adam, Agustín, Edu, Marcos no tienen acceso al refresh
token ni a credenciales SP-API. Acceden a outputs procesados solamente.

## D5 · 20/05 · Escalación 5 → 12 roles

**Decisión**: marcar 12 non-Restricted roles (todos los que Capybaras
podría usar operativamente)
**Por qué**: Freddy confirmó que todas las áreas operativas listadas son
posibles o están en roadmap. Pedir non-Restricted preventivamente es
defendible y evita resubmit futuro.
**Implicancia**: cada role aprobado es compromiso auditable. Capybaras
debe estar preparada para justificar uso real en auditoría futura.

## D6 · 20/05 · No insistir con amendment proactivo

**Decisión**: NO mandar comment al case con los 4 bullets faltantes antes
de que Amazon pregunte
**Por qué**: Freddy cerró el loop con "ya está, esperemos que dicen".
Probabilidad de scrutiny de Amazon sobre Private Developer non-Restricted
es baja. Mandar amendment no solicitado puede confundir el review.
**Implicancia**: si Amazon SÍ pregunta, los bullets están listos en
amendment-bullets.md para respuesta reactiva.

## D7 · 20/05 · MerchantSpring redacción

**Decisión**: NO modificar la redacción ambigua de MerchantSpring en
"outside parties" del submission
**Por qué**: submission ya enviada. Modificación post-submit requiere
abrir case especifico.
**Implicancia**: si Amazon pregunta, aclarar que MerchantSpring es
co-authorized vía OAuth directa del cliente, no es sharing de Capybaras.

## D8 · 20/05 · Atom11 en external sources

**Decisión**: NO modificar el missing de Atom11 en external sources
**Por qué**: submission ya enviada. Atom11 corre vía Ads API no SP-API;
defendible si Amazon pregunta. Más limpio declararla pero no crítico.
**Implicancia**: si Amazon escanea conexiones de clientes y ve Atom11,
pedir comment al case para declararla.
