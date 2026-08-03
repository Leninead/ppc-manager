---
tipo: sop
audiencia: usuario
modulo: M30
modulo_nombre: Pricing Dashboard
seccion: Account Health
version: 1.0
fecha: 2026-06-21
autor: lenin-acosta
estado: activo
fuente_verdad: modules/pages/pricing_dashboard.py (_SOP_MD)
---

### Pricing Dashboard — cómo usarlo

Analiza el pricing semanal de cada SKU cruzando varias fuentes y clasifica cada producto en **subir / bajar / liquidar / mantener**, con precio sugerido. Guarda el histórico en la nube.

**Inputs (archivos de la semana):**
- FBA (CSV) · Fees (CSV) · AWD (CSV)
- PL / Price List (XLSX) · Maestro (XLSX) · Izzi (XLSX)
- Opcional: importar histórico (JSON)

**Paso a paso (uso semanal):**
1. Elegí el **cliente**.
2. **Subí los archivos** de la semana en sus uploaders. No hace falta tenerlos todos para correr, pero cuantos más, más completo el scoring.
3. **Corré el análisis**: el dashboard clasifica cada SKU y da precio sugerido.
4. **Revisá por vista** (pestañas internas):
   - *Resumen*: SKU / status / stock, vista general.
   - *Principal*: tabla completa con scoring y clasificación.
   - *AWD/FBA*: stock y restock.
   - *Liquidar*: los que conviene liquidar.
   - *Sin margen*: los que no dan margen para bajar.
   - *AIS*: recargo por inventario añejo (Aged Inventory Surcharge).
   - *Histórico*: evolución semana a semana.
5. **Exportá**: botón de *Resumen* (global) + export por vista (Principal / Liquidar / Sin margen / AIS) en XLSX.

**Notas:**
- La vista *AWD/FBA* puede mostrar datos parciales (el procesamiento de AWD/Izzi está en ajuste). El resto funciona completo.
- Los nombres de estado de Amazon ('Excess', 'Low stock', etc.) se leen literales — respetá el formato de cada archivo tal cual sale de la fuente.
- El histórico se guarda en la nube: no se pierde al reiniciar.
