# Skill: PPC Reporting Standard
## Propósito
Estandarizar el formato visual y numérico de todos los reportes, KPIs, tablas y exports Excel del Agency OS. Se activa cuando cualquier agente necesita mostrar métricas PPC, generar Excel con branding, o renderizar KPIs en Streamlit.

## Paleta de colores Capybaras
| Token | Hex | Uso |
|-------|-----|-----|
| Naranja primario | #E84000 | Headers, títulos, botones activos |
| Naranja secundario | #FF6B00 | Hover, badges |
| Naranja pálido | #FFF3E0 | Background kpi_card |
| Borde kpi_card | #FFD9B3 | Border de cards |
| Negro | #1F1F1F | Texto principal, sidebar bg |
| Blanco roto | #FAFAFA | Background general |
| Gris texto | #888888 | Captions, subtítulos |
| Verde | #1B6B2F / #E8F5E9 | Positivo, subir, bueno |
| Rojo | #B71C1C / #FFEBEE | Negativo, bajar, alerta |
| Amarillo | #F57F17 / #FFF8E1 | Warning, revisar |
| Azul SP | #1d4b8f | Headers SP en PPC Audit |
| Violeta SB | #6b2d8f | Headers SB en PPC Audit |
| Verde SD | #2a6e4e | Headers SD en PPC Audit |

## Componente kpi_card (Streamlit)
Usar siempre `kpi_card()` de `core/helpers.py`. Nunca usar `st.metric` para KPIs principales.
```python
# Firma
kpi_card(label: str, value: str, delta: float = None, delta_good: bool = True) -> str

# Render con:
st.markdown(kpi_card("ACoS", "22.7%", delta=-3.2, delta_good=True), unsafe_allow_html=True)
```
- Background: #FFF3E0, border: 1px solid #FFD9B3, border-radius: 12px
- Delta con flechas: ↑ (positivo) / ↓ (negativo) / → (sin cambio)
- Color delta: verde si delta_good=True y delta>0, rojo si delta_good=True y delta<0
- Invertir lógica para métricas donde bajar es bueno (ACoS, CPC, WAS)

## Semáforo ACoS (tablas y Excel)
| Rango | Color | Hex bg | Hex text |
|-------|-------|--------|----------|
| ≤ 30% | Verde | #E8F5E9 | #1B5E20 |
| 31-55% | Amarillo | #FFF8E1 | #F57F17 |
| > 55% | Rojo | #FFEBEE | #B71C1C |

Aplicar en todas las tablas que muestren ACoS. En Excel usar PatternFill con estos colores.

## Semáforo diagnóstico de campañas
| Estado | Emoji | Condición |
|--------|-------|-----------|
| PAUSAR | 🔴 | Spend > threshold AND orders = 0 |
| REVISAR | 🟡 | ACoS > target × 2 |
| ESCALAR | ✅ | ACoS < target × 0.5 con órdenes |
| FANTASMA | ⚫ | 0 impresiones activas |
| OK | 🟢 | Dentro de rangos normales |

## Fórmulas PPC estándar
| Métrica | Fórmula | Formato |
|---------|---------|---------|
| ACoS | Spend / Sales × 100 | XX.X% |
| ROAS | Sales / Spend | X.XX |
| TACoS | Ad Spend / Total Revenue × 100 | XX.X% |
| CVR | Orders / Clicks × 100 | XX.X% |
| CPC | Spend / Clicks | $X.XX |
| CTR | Clicks / Impressions × 100 | XX.XX% |
| Bid sugerido | (CVR/100) × precio × (target_ACoS/100) | $X.XX |

## Formato numérico
| Tipo | Formato | Ejemplo |
|------|---------|---------|
| Moneda | $X,XXX.XX | $1,234.56 |
| Porcentaje | XX.X% | 22.7% |
| Enteros grandes | X,XXX | 45,230 |
| Delta % | +XX.X% / -XX.X% | +12.3% |
| Score | XX/100 | 78/100 |

## Excel — Branding Capybaras
### Portada (hoja 1 de cada export)
- Fila 1: merge A1:F1, fondo #E84000, texto blanco bold 14pt, título del reporte
- Fila 2: merge A2:F2, fondo #1F1F1F, texto blanco 11pt, "Capybaras Agency — [fecha]"
- Fila 3: vacía (separador)
- Fila 4+: contenido

### Headers de tabla en Excel
- Fondo: #1F1F1F (negro), texto: blanco, bold, 11pt
- Alignment: center para números, left para texto
- Row height: 20px

### Autofit de columnas
Siempre llamar `_autofit(ws)` después de llenar datos. Min width 8, max width 40.

### Función _build_*_excel() — Regla arquitectónica
SIEMPRE definir la función de export Excel FUERA de render(). Nunca dentro.
Patrón: `def _build_str_excel(df, kpis, ...): ...` → se llama desde render() al click del botón.
Esto evita el bug "At least one sheet must be visible" de openpyxl dentro del runtime de Streamlit.

## Terminología ES/EN
| Español | English | Usar en |
|---------|---------|---------|
| Gasto publicitario | Ad Spend | Reportes bilingües |
| Ventas totales | Total Revenue | Weekly Report |
| Ventas orgánicas | Organic Sales | Account Pulse |
| Costo por click | Cost Per Click | Bid Optimizer |
| Tasa de conversión | Conversion Rate | Todos |
| Despericio publicitario | Wasted Ad Spend | STR, Audit |

## Benchmarks de referencia (Capybaras 2026)
| Métrica | Excelente | Bueno | Aceptable | Malo |
|---------|-----------|-------|-----------|------|
| ACoS | < 20% | 20-35% | 35-55% | > 55% |
| TACoS | < 10% | 10-20% | 20-30% | > 30% |
| CTR | > 0.5% | 0.3-0.5% | 0.18-0.3% | < 0.18% |
| CVR | > 15% | 10-15% | 5-10% | < 5% |
| BuyBox | > 95% | 90-95% | 80-90% | < 80% |

## Qué NO hacer
- Nunca usar st.metric para KPIs principales — siempre kpi_card
- Nunca hardcodear colores inline — usar los tokens de la paleta
- Nunca generar Excel sin portada naranja Capybaras
- Nunca mostrar ACoS sin semáforo de color
- Nunca mostrar delta sin flecha direccional (↑↓→)
- Nunca redondear moneda a menos de 2 decimales
- Nunca mostrar porcentajes con más de 1 decimal (excepto CTR que usa 2)
