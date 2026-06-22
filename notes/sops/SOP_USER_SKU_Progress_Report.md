---
tipo: sop
audiencia: usuario
modulo: M28
modulo_nombre: SKU Progress Report
seccion: Account Health
version: 1.0
fecha: 2026-06-21
autor: lenin-acosta
estado: activo
fuente_verdad: modules/pages/sku_progress_report.py (_SOP_MD)
---

### SKU Progress Report — cómo usarlo

Trackea la evolución semanal de tus SKUs por cliente (sesiones, unidades, conversión) y guarda un log de las optimizaciones que vas haciendo. Todo queda guardado en la nube y lo ve el equipo.

**Input:** CSV semanal de Amazon *'Detail Page Sales and Traffic By Child Item'*.

**Paso a paso (uso semanal):**
1. Elegí el **cliente** en el desplegable de arriba. Si es nuevo, tocá *Cliente nuevo* y poné el nombre.
2. **Cargá los SKUs** (la primera vez): tocá *Agregar SKU*, completá SKU + ASIN (y datos del producto si querés). Repetí por cada SKU. Aparecen como pestañas arriba.
3. **Importá la semana**: pestaña *Importar CSV* → subí el CSV *'Detail Page Sales and Traffic By Child Item'* bajado de Seller Central. Detecta la semana del nombre del archivo y avisa si ese snapshot ya estaba cargado (no duplica).
4. **Revisá KPIs y gráficos**: entrá a la pestaña de cada SKU. Si recién lo creaste y no subiste CSV, dice *'Sin datos semanales todavía'* — es normal hasta el primer import.
5. **Registrá una optimización**: en la pestaña del SKU → *Registrar optimización*, anotá qué cambiaste. Queda en el log histórico para medir impacto después.
6. **Exportá**: *Excel completo* baja el tracker multi-hoja (un tab por SKU).

**Admin** (pestaña *Admin*): borrar un snapshot cargado por error o borrar un SKU. *Borrar cliente* elimina todo lo de ese cliente en este módulo.

**Tips:**
- Tiene que ser el **CSV**, no XLSX. Si Excel te lo reguarda como .xlsx, el uploader lo rechaza.
- Todo se guarda en la nube: no se pierde al reiniciar la app ni al cambiar de compu.
