# DISEÑO — Reporte HTML Amazon Advertising

## Tipografía
- **Títulos y labels:** Barlow Condensed · pesos 700 y 800 · letter-spacing amplio en labels pequeños
- **Cuerpo y datos:** Barlow · pesos 300 / 400 / 500 / 600
- Importar desde Google Fonts: `https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=Barlow:wght@300;400;500;600&display=swap`

## Paleta de colores
```css
--bg: #f4f1eb          /* fondo general */
--surface: #ffffff      /* cards y tablas */
--border: #ddd8cc       /* bordes suaves */
--text: #1a1714         /* texto principal */
--muted: #9a9288        /* texto secundario, labels */

/* Accents */
--red: #c8402a
--green: #2a6e4e
--yellow: #c07a1a

/* Lights (backgrounds de chips/tags) */
--red-light: #fbeae7
--green-light: #e6f4ed
--yellow-light: #fdf3e3

/* Por tipo de campaña */
--sp: #1d4b8f           /* Sponsored Products */
--sb: #6b2d8f           /* Sponsored Brands */
--sd: #2a6e4e           /* Sponsored Display */
--sp-light: #e8f0fb
--sb-light: #f3ecfb
--sd-light: #e6f4ed
```

## Indicadores de ACoS
| Rango | Color | CSS class |
|-------|-------|-----------|
| ≤ 30% | Verde `--green` | `.acos-g` |
| 31–55% | Amarillo `--yellow` | `.acos-y` |
| > 55% | Rojo `--red` | `.acos-r` |
| Sin ventas | Muted + guión | `.zero` |

## Header del reporte
- Fondo `--text` (casi negro)
- Borde inferior de 4px en color accent (puede variar por marca — usar amarillo `--yellow` como default o el color más representativo de la cuenta)
- Izquierda: nombre de marca en Barlow Condensed 800 38px uppercase + subtítulo "Amazon Advertising Performance Report"
- Derecha: período del reporte + fecha de generación

## Cards KPI (Sección 1)
- Grid 3 columnas
- Borde superior de 3px en color accent (SP azul, verde, rojo, amarillo según el KPI)
- Padding 22px 24px
- Sombra suave `0 2px 12px rgba(26,23,20,0.07)`
- Hover: translateY(-2px) + sombra más pronunciada
- Label en Barlow Condensed 700 11px uppercase letter-spacing 0.18em color muted
- Valor en Barlow Condensed 800 40px
- Subtexto 12px color muted con datos de detalle
- Breakdown tags al pie: chips pequeños con color por tipo (SP/SB/SD)

## Cards de Auditoría (Sección 2)
- Grid 3 columnas
- Sin borde superior de color (bordes neutros)
- Header de card: título en uppercase + badge alineado a la derecha
- Badges: `OK` en verde · `REVISAR` en rojo · `CRÍTICO` en rojo con fondo más saturado
- Filas internas con borde separador sutil
- Alert boxes al pie: fondo light del color correspondiente, texto en color accent, font-weight 600

## Tablas de la grilla 2×2 (Sección 3)
- Grid 2 columnas, gap 16px
- Header de tabla: padding 14px 20px, borde inferior, título uppercase + badge opcional
- Thead: fondo #faf9f6, texto muted, 11px uppercase, letter-spacing 0.12em
- Tbody: hover por fila en #faf9f6, borde inferior entre filas `#f0ece4`
- Última fila sin borde inferior
- Columna de target: alineada izquierda, chips de tipo SP/SB + match type en segunda línea pequeña
- Columnas numéricas: alineadas derecha, Barlow Condensed 600 14px

### Chips de tipo y match type
```html
<!-- Tipo de campaña -->
<span class="type-chip chip-sp">SP</span>
<span class="type-chip chip-sb">SB</span>
<span class="type-chip chip-sd">SD</span>

<!-- Match type (fondo neutro) -->
<span class="type-chip" style="background:#f0ece4;color:var(--muted);font-size:9px;">Exact</span>
```

## Tabla de Performance (Sección 4)
- Un bloque por tipo (SP / SB / SD), separados visualmente
- Header de bloque: fondo light del color del tipo, borde inferior 2px del color del tipo, título en color del tipo
- Columna de segmento: alineada izquierda con indent de 28px para sub-segmentos
- Todas las columnas numéricas: alineadas derecha, Barlow Condensed 500
- **Filas TOTAL:** fondo #faf9f6, font-weight 800 en segmento, border-top y border-bottom 2px, no indent
- Hover en filas no-total: fondo #faf9f6
- Mini barra de spend: elemento visual de 44px ancho junto al porcentaje de spend
- Segmentos sin datos: mostrar guiones en muted, no omitir la fila

## Footer
- Fondo `--text`
- Texto muted 11px centrado
- Contenido: Marca · Tipo de reporte · Período · Fuente de datos · Fecha de generación

## Estructura general del archivo HTML
```
<!DOCTYPE html>
<html lang="es">
<head>
  [meta charset, viewport, title, Google Fonts link]
  <style>[todo el CSS inline — sin archivos externos]</style>
</head>
<body>
  <header class="report-header">...</header>
  <div class="container">
    [Sección 1 — KPIs]
    [Sección 2 — Auditoría]
    [Sección 3 — Top Targets & ASINs]
    [Sección 4 — Performance Table]
  </div>
  <footer class="report-footer">...</footer>
</body>
</html>
```

## Responsive
- Breakpoint en 900px: KPI grid pasa a 2 columnas, audit y quad grids a 1 columna, padding reducido
- Header en mobile: flex-direction column

## Convenciones de formato en los datos
- Importes: `$8,654` (con signo y separador de miles, sin decimales si > $100)
- Importes pequeños: `$74.96` (con decimales si < $100)
- Porcentajes: `47.9%` (un decimal)
- Sessions / Impressions grandes: `1.1k`, `182.5k` (una decimal en k)
- ACoS sin ventas: `—` (guión largo)
- CVR: `11.6%`
