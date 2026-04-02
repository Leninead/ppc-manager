# CHANGELOG — Auditor PPC

Registro de cambios, mejoras y decisiones de diseño del template de auditoría.

---

## v1.2 — 19 Mar 2026
**Modificaciones al template base (Sección 1 y Sección 3)**

### Cambiado
- **Sección 1 · KPI #5:** reemplazado ROAS por **Impressions Totales** con desglose % SP / SB / SD
- **Sección 3 · Top ASINs por Revenue:** columna `Sessions` reemplazada por `Ad Spend`
  - Ad Spend se calcula cruzando ASIN del nombre de campaña con spend de SP + SB + SD
- **Sección 3 · Bottom ASINs por CVR:** ídem, columna `Sessions` → `Ad Spend`

### Motivo
Más útil ver la inversión real por ASIN que las sessions (disponibles en el Business Report de todas formas). Las impressions reemplazan al ROAS para tener una métrica de awareness además de las de eficiencia.

---

## v1.1 — 16 Mar 2026
**Primera ejecución sobre cuenta real (Pouchera / Tattoo Care)**

### Aprendizajes
- Bulk files > 10MB: recomendar guardar como .xlsb o eliminar hojas vacías antes de subir
- SD con tactic VCPM tiene CTR muy bajo (0.09%) — normal para ese modelo de compra, no confundir con error
- Cuando hay pocos ASINs (< 5 en BR), la tabla Bottom CVR puede quedar con filas vacías — agregar nota explicativa

### Prompt para compañeros
Ver archivo `PROMPT_auditoria_ppc.md` — versión lista para copiar y pegar en cualquier conversación de Claude.

---

## v1.0 — 11 Mar 2026
**Template inicial creado sobre cuenta Wamery (Feb 2026)**

### Estructura definida
- Sección 1: 6 KPIs (Revenue · Orgánico · TACoS · ACoS · ROAS · PPC Spend/Sales)
- Sección 2: 3 cards de auditoría (Mixed Match · Target WAS · ST WAS)
- Sección 3: grilla 2×2 (Top WAS · Top Performance · Top Revenue · Bottom CVR)
- Sección 4: tabla de performance por segmento (SP / SB / SD con todos los sub-segmentos)

### Decisiones de diseño
- Fuentes: Barlow Condensed (títulos) + Barlow (cuerpo) — Google Fonts
- Paleta neutra cálida (#f4f1eb de fondo) con accents SP azul / SB violeta / SD verde
- ACoS coloreado: verde ≤30% / amarillo 31-55% / rojo >55%
- HTML standalone sin dependencias externas (excepto Google Fonts CDN)
- Procesamiento siempre en Python antes de generar HTML

### Lógica de AUTO targets
- Identificar campañas AUTO por `Targeting Type = "Auto"` en Entity = Campaign
- Clasificar por sub-tipo leyendo `Product Targeting Expression` del SP Search Term Report
- Valores: `close-match / loose-match / substitutes / complements`

---

## Próximas mejoras (backlog)

- [ ] Agregar gráfico de distribución de spend por tipo (SP/SB/SD) con barras visuales
- [ ] Sección de Negative Keywords: mostrar los top 10 términos candidatos a negative con mayor spend sin ventas
- [ ] Comparativa entre períodos si se suben dos bulk files
- [ ] Detección automática de campañas con presupuesto agotado (budget capped)
- [ ] Calcular Break-Even ACoS estimado si se provee el margen del producto
- [ ] Agregar sección de Bid Recommendations por segmento basada en ACoS target

