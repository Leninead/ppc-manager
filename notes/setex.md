# 🏢 Setex Technologies — Amazon MX

**Account Manager:** Tatiana Velasquez  
**Tomada por agencia:** Marzo 2026 (venían de Perpetua)  
**Marketplace:** Amazon México  
**Categoría:** Accesorios para anteojos (nose pads, temple tips, ear hooks)

---

## 📦 Productos principales

| ASIN | Producto | Ventas período | BuyBox% |
|------|----------|---------------|---------|
| B081GB8F89 | 1mm nose pads (top seller) | MX$33,360 | 99.41% |
| B09HVXDH7M | 1.8mm nose pads | MX$8,120 | 100% |
| B08PZF22R1 | 0.6mm nose pads | MX$7,540 | 99.58% |
| B0B94KBY8H | Temple Tips | MX$4,590 | 100% |
| B0C7WPFVGV | Temple Tip Grips | MX$1,350 | 96.23% ⚠️ |
| B0F63LTD92 | Ear Hook Grips | MX$2,320 | 100% |
| B08SNXF8HP | Nose pads (variante) | MX$1,590 | 91.18% 🔴 |

---

## 🎯 Estructura PPC

### Campañas antiguas (Perpetua — heredadas)
- 43 campañas activas desde Jul–May 2025
- Naming: `[Producto] - Advanced MX - [fecha] - Perpetua - SP - [tipo]`
- Performance acumulada: 1,392 compras | MX$411,950 ventas | ACoS ~27%
- Top performer: `10mm Manual` (212 compras, ACoS 22.8%)
- Top performer: `10mm PAT` (166 compras, ACoS 30.1%)

### Campañas nuevas (Lenin — lanzadas 13/03/2026)
- 53 campañas | Naming: `Setex [Producto] | SP-[tipo] | [match] | [cluster] | [kw/target]`
- Performance a 4 días (al 17/03): 9 compras | MX$2,540 ventas | ACoS ~34%
- Top: `Setex 1mm SKC almohadillas para lentes` — 4 compras, ACoS 21.9% 🟢
- Top: `Setex Temple PAT MATCH AA` — 2 compras, ACoS 17.0% 🟢

---

## 🧠 Insights detectados

- **Fines de semana caen ~60%** vs días de semana — patrón histórico normal confirmado
- **Keywords en inglés NO funcionan en MX** — 0 impresiones después de 4 días
- **Keywords en español que convierten:** almohadillas para lentes, antideslizante para lentes, gomas para lentes
- **PAT y Branded Pat** son los tipos de campaña con mejor performance
- **Festivos MX** afectan ventas del fin de semana previo (confirmado 17/03 Juárez)

---

## 📋 Decisiones tomadas

| Fecha | Decisión | Motivo |
|-------|----------|--------|
| 17/03/26 | No pausar campañas nuevas Setex | Caída sáb-dom fue estacional + festivo Juárez, no PPC |
| 17/03/26 | Monitorear B08SNXF8HP | BuyBox 91.18% — único ASIN con pérdida real |
| 17/03/26 | No optimizar bids aún | Campañas en warm-up, esperar 2 semanas |

---

## ⏳ Pendientes

- [ ] Evaluar pausar KW en inglés — revisión 27/03 (si siguen en 0 impresiones)
- [ ] Revisión general campañas Setex al cumplir 2 semanas — 27/03/2026
- [ ] Resolver BuyBox B08SNXF8HP — Tatiana revisa precio en Seller Central
- [ ] Optimizar bid Setex 1mm PAT MATCH AA (ACoS 54.6%) — post warm-up

---

## 📊 Reportes generados

### Account Pulse — 17/03/2026
**Archivos fuente:**
- `Campaign_Mar_17_2026.csv` — 96 campañas (43 Perpetua + 53 nuevas Setex)
- `BusinessReport-3-17-26.csv` — BR by ASIN (20 productos, BuyBox, sesiones)
- `BusinessReport-3-17-26__1_.csv` — BR Daily (43 días feb-mar 2026)

**Output generado:** `AccountPulse_Setex_v3.xlsx`

**Estructura del Excel (4 hojas):**
- `Resumen Ejecutivo` — portada light con capybara mascota, KPIs, diagnóstico automático, mensaje para Slack
- `Ventas Diarias` — 43 días con color por tipo (laboral/finde/festivo), totales con fórmulas
- `BuyBox & ASINs` — ordenado por impacto económico (ventas perdidas estimadas)
- `Campañas` — separadas NUEVA (verde) vs PERPETUA (azul), ACoS semáforo, warm-up detectado

---

## 🎨 Especificaciones del Excel Account Pulse

### Paleta de colores
| Variable | Hex | Uso |
|----------|-----|-----|
| Naranja primario | `E84000` | Headers sección, barras, acentos |
| Naranja secundario | `FF6B00` | Agencia nombre, título |
| Naranja pálido | `FFF3E0` | Zona hero portada, mensaje cliente |
| Negro | `1F1F1F` | Headers de tabla |
| Blanco roto | `FAFAFA` | Zona agencia portada |
| Gris tabla | `F7F7F7` | Filas alternas |
| Verde | `1B6B2F` / bg `E8F5E9` | OK, excelente, campañas nuevas |
| Rojo | `B71C1C` / bg `FFEBEE` | Urgente, ACoS crítico, BuyBox bajo |
| Amarillo | `7A4F00` / bg `FFF8E1` | Monitorear, fin de semana |
| Azul | `0D47A1` / bg `E3F2FD` | Info, campañas Perpetua, festivos |

### Estructura portada (3 zonas)
1. **Franja naranja top** — 6px, color `E84000`
2. **Zona agencia** — fondo `FAFAFA`, logo píldoras col B + texto "Capybaras Agency" col C
3. **Zona hero** — fondo `FFF3E0`, título "Account Pulse", metadatos, capybara mascota col H

### Imágenes usadas
- `capybara_mascota` — `1__2_.png` recortada (bg negro → transparente), 200×188px, columna H zona hero
- `logo_píldoras` — `8__2_.png` recortada (bg negro → transparente), 48×40px, columna B zona agencia

### Procesamiento de imágenes (Python/Pillow)
```python
# Remover fondo negro → transparente
img = Image.open('source.png').convert('RGBA')
data = np.array(img)
mask = (data[:,:,0] < 40) & (data[:,:,1] < 40) & (data[:,:,2] < 40)
data[mask, 3] = 0
result = Image.fromarray(data)
result = result.resize((200, 188), Image.LANCZOS)
result.save('output.png')
```

### Lógica de diagnóstico automático
```python
# Clasificación de días
_FESTIVOS_MX = {
    (1,1):"Año Nuevo", (2,3):"Constitución", (3,17):"Juárez",
    (5,1):"Día del Trabajo", (9,16):"Independencia",
    (11,2):"Día de Muertos", (11,18):"Revolución", (12,25):"Navidad",
}
# weekday >= 5 → fin de semana
# (month, day) in _FESTIVOS_MX → festivo
# else → laboral

# Severidades de diagnóstico
# BuyBox < 95% + sessions > 30 → URGENTE (rojo)
# BuyBox 95–98%               → MONITOREAR (amarillo)
# Caída + es_finde/festivo    → INFO (verde — descartado)
# Camp nueva + ACoS > 40%     → warm-up (no alarmar)
```

---

## 💬 Historial de conversaciones

### 17/03/2026 — Análisis caída ventas sáb-dom + desarrollo Account Pulse
**Pregunta Tatiana:** Impresiones/clicks subieron desde viernes, ventas bajaron sábado y domingo.

**Conclusión:** Patrón estacional confirmado + festivo 17/03 (Juárez). No fue problema PPC.

**Análisis realizado:**
- Caída sáb 14/03: MX$1,310 (vs promedio semana MX$3,200) — esperado
- Caída dom 15/03: MX$2,290 — esperado
- BuyBox promedio: 98.9% — OK excepto B08SNXF8HP (91.18%)
- Campañas nuevas 4 días: 9 compras, ACoS 34% — dentro de warm-up normal

**Output enviado a Tatiana:** Informe HTML + Excel `AccountPulse_Setex_v3.xlsx`

**Archivos analizados:**
- `Campaign_Mar_17_2026.csv`
- `BusinessReport-3-17-26.csv`
- `BusinessReport-3-17-26__1_.csv`