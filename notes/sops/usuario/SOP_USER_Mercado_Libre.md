---
tipo: sop
audiencia: usuario
modulo: M36
modulo_nombre: Mercado Libre
seccion: Marketplaces
version: 1.0
fecha: 2026-07-25
autor: lenin-acosta
estado: activo
fuente_verdad: modules/mercado_libre/main.py (_SOP_MD)
---

### Mercado Libre — cómo usarlo

Concentra la operación de las cuentas de Mercado Libre en tres frentes: seguimiento del impacto de los cambios en publicaciones, sugerencia de reposición de stock y alertas de campañas de Product Ads. Multi-cuenta, todo guardado en la nube.

**Inputs (tres reportes de Mercado Libre):**
- **Rendimiento** — Mercado Libre → Métricas → Publicaciones → Descargar reporte
- **Publicaciones** — Mercado Libre → Publicaciones → Modificar masivamente → Descargar
- **Ads** — Mercado Libre Ads → Reportes → Reporte por anuncios

**Paso a paso:**

1. Elegí la **cuenta** en el desplegable de arriba. Si es nueva, tocá *Cuenta nueva* y poné el nombre.
2. **Importá los reportes**: pestaña *Importar* → subí cada uno de los tres Excel en su bloque. Se pueden cargar por separado. Cada reporte se guarda como un snapshot con su período; subir el mismo dos veces lo sobrescribe, no lo duplica.
3. **Stock**: la pestaña *Stock* muestra qué reponer, ordenado por facturación. Mirá primero las de urgencia 🔴 Crítico (7 días o menos de cobertura). Cargá los envíos en camino con *Registrar tránsito* + su fecha estimada de llegada, así la sugerencia no recomienda de más.
4. **Ads**: la pestaña *Ads* marca en 🔴 rojo y 🟡 amarillo las campañas y anuncios con problemas de rentabilidad. Revisá primero los que gastaron sin generar ingresos. Las tablas de *Sin impresiones* y *Pocos clics* son revisiones aparte (puja/presupuesto, no rentabilidad).
5. **Cambios**: cada vez que modifiques una publicación, registrala en *Registrar cambio* con su fecha real. El módulo la compara contra los reportes anterior y posterior para medir si funcionó (sobre visitas y conversión).

**Admin** (pestaña *Admin*): borrar un snapshot cargado por error, por cada uno de los tres módulos.

**Tips:**
- El seguimiento de cambios necesita **al menos dos reportes de rendimiento** cargados para comparar. Con uno solo, los cambios aparecen como *pendiente de evaluación* — es normal hasta la segunda carga.
- El reporte de rendimiento se baja cada 14 días. Un cambio hecho al final de un período recién se puede medir dos reportes después.
- Las publicaciones con menos de 30 visitas se marcan *sin datos suficientes*: con tan poco tráfico una sola venta distorsiona la conversión y no es medible.
- Todo se guarda en la nube: no se pierde al reiniciar ni al cambiar de compu.
