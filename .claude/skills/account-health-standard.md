---
name: account-health-standard
description: Convenciones de diseño, tono, terminología y reglas operativas para módulos de la sección Account Health del Agency OS de Capybaras. Equivalente al ppc-reporting-standard pero para Catalog/Seller Central health.
applies_to: módulos de la sección Account Health (pricing, SKU progress, flat file migration, listing monitor, listing compliance, gamboa generator, variation builder, weekly report)
version: v1
created: 2026-05-06
---

# Skill — Account Health Standard

Convenciones obligatorias para módulos de la sección Account Health del Agency OS. Cubre los aspectos que el `ppc-reporting-standard` no cubre porque pertenecen a otro dominio operativo: catálogo, listings, pricing, inventory health, compliance.

Si estás construyendo un módulo PPC, leé `ppc-reporting-standard`. Si es Account Health, leé este. Si toca ambos (ej: weekly report), aplican los dos y este toma precedencia en lo específico de catálogo.

---

## 🎯 Filosofía

Account Health es la otra mitad del negocio Amazon: mientras PPC ataca el tráfico pago, Account Health gobierna lo orgánico, lo estructural y lo que mantiene la cuenta viva. Un cliente puede ganar mucho en PPC y perder más en una violación de policy, un Buy Box perdido, un listing degradado o un SKU que entró en aged inventory surcharge.

Tres principios bloqueados:

1. **Datos del cliente son la fuente de verdad.** Las reglas de scoring, los umbrales, las clasificaciones — todas se calibran contra cómo opera el cliente real, no contra ideales teóricos. Cuando hay duda, ganan los datos.
2. **Lenguaje deliberado.** Los términos Amazon en inglés no se traducen. La terminología de procesos internos se elige para reflejar la operatoria real, no para sonar más formal.
3. **Severidad explícita.** Toda alerta, toda clasificación, todo flag tiene severidad visible: 🔴 crítico, 🟠 importante, 🟡 menor, 🟢 saludable. Sin severidad, todo parece urgente y nada lo es.

---

## 🌐 Terminología — bilingüismo natural

### Términos Amazon NO se traducen

Lista no exhaustiva — ante duda, mantener el inglés:

`FBA` · `AWD` · `IZZI` · `DoS` (Days of Supply) · `ASIN` · `SKU` · `MSKU` · `GTIN` · `UPC` · `EAN` · `parent ASIN` · `child ASIN` · `parent-child` · `variation theme` · `Buy Box` · `Featured Offer` · `Buy Box price` · `BSR` (Best Sellers Rank) · `A+ Content` · `Brand Store` · `Brand Registry` · `flat file` · `Browse Node` · `Item Type Keyword` · `bullet points` · `backend search terms` · `Seller Central` · `Vendor Central` · `Sponsored Products` · `Sponsored Brands` · `Sponsored Display` · `inventory report` · `Fee Preview` · `Product Line` · `Maestro` · `Health Check` · `aged inventory` · `Aged Inventory Surcharge` · `AIS` · `sell-through` · `stockout` · `low stock` · `Out of stock` · `Excess` · `restock alert` · `replenishment` · `auto-replenishment` · `sales rank` · `revenue leakage` · `policy violation` · `hijacker` · `GPSR` (compliance EU) · `weighted product` · `pesticide compliance`

### Términos de proceso interno — elegidos deliberadamente

| ✅ Usar | ❌ NO usar | Por qué |
|---|---|---|
| Descargar inventory report | Solicitar master file | Refleja que el archivo se baja directo de Seller Central, no se le pide a alguien |
| Rutina de reuniones | Cadencia de reuniones | "Cadencia" es jerga consultora vacía; "rutina" es lo que realmente es |
| Scope of Work | Carriles paralelos | Comunica formalidad y compromiso |
| Drive Maestro | Master spreadsheet | Es el nombre del artefacto interno, no se traduce |
| Onboarding plan | Plan de bienvenida | "Onboarding" tiene significado técnico específico en Amazon |
| Health check | Diagnóstico de salud | "Health check" es el término operativo del equipo |
| Bajar / Subir / Mantener / Liquidar | Reducir / Aumentar / Conservar / Vender | Verbos directos, sin academicismo |
| Mover X unidades a FBA | Reabastecer / Replenisar | Acción concreta, no proceso abstracto |

### Acrónimos obligatorios al primer uso

Al primer uso en un módulo, expandir el acrónimo entre paréntesis. Después usar solo el acrónimo:

> "El sistema calcula DoS (Days of Supply) por ubicación. DoS FBA aplica a la decisión de bajar precio."

Excepción: ASIN, SKU, FBA, AWD se asumen conocidos por todo usuario del Agency OS.

---

## 🎨 Paleta cromática — Account Health

### Colores principales (compartidos con Capybaras Agency OS)

````
Naranja brand:       #E84000   ← acento principal, headers, botones primarios
Negro UI:            #1A1A1A   ← sidebar, texto principal
Blanco roto:         #FAFAFA   ← fondos de cards
Gris medio:          #6B7280   ← texto secundario, labels
Gris claro:          #E5E7EB   ← borders, dividers
````

### Colores de severidad — semáforo unificado

Usar siempre los mismos hex codes para que un usuario que pasa de M27 Pricing a M28 SKU Progress reconozca instantáneamente las severidades.

| Severidad | Bg | Border | Text | Emoji |
|---|---|---|---|---|
| 🔴 **Crítico** (bajar, liquidar, alerta urgente) | `#FEE2E2` | `#FCA5A5` | `#B91C1C` | 🔴 |
| 🟠 **Importante** (subir, atención requerida) | `#FEF3C7` | `#FCD34D` | `#D97706` | 🟠 |
| 🟢 **Saludable** (mantener, OK) | `#F0FDF4` | `#86EFAC` | `#166534` | 🟢 |
| 🟡 **Menor** (revisar, no urgente) | `#FEFCE8` | `#FDE047` | `#A16207` | 🟡 |
| 🔵 **Informativo** (event, log entry) | `#EFF6FF` | `#93C5FD` | `#1E40AF` | 🔵 |
| 🟣 **AWD/Logística** (move stock, restock) | `#F5F3FF` | `#C4B5FD` | `#6D28D9` | 📦 |

### Cuándo usar cada severidad

- **🔴 Crítico**: pérdida activa de dinero (margen negativo, AIS pagándose, stockout en producto top), acción que no admite postergación
- **🟠 Importante**: oportunidad clara o degradación que va a escalar si no se actúa esta semana (oportunidad de subir precio en producto rotando, aging 181-365)
- **🟢 Saludable**: estado normal, no requiere acción
- **🟡 Menor**: vale la pena mirar pero no esta semana (precio ligeramente alto vs subcategoría)
- **🔵 Informativo**: registro de evento sin valoración (un cambio que se aplicó, una optimización loggeada)
- **🟣 Logístico**: acciones de movimiento de stock (AWD→FBA, IZZI→FBA), fuera del eje de pricing

### Anti-patterns cromáticos

- ❌ Inventar colores nuevos por módulo. Si necesitás un 7mo estado, primero argumentá por qué los 6 existentes no alcanzan.
- ❌ Usar verde para "subir precio". Subir precio es 🟠 importante (oportunidad), no saludable.
- ❌ Usar rojo para "saludable". Aunque suene obvio, ya pasó: alguien usó `#FF0000` para "alerta de oportunidad". Romper el contrato cromático rompe la legibilidad de toda la sección.

---

## 📊 Patrones de UI obligatorios

### Header del módulo

Usar el patrón del `module-architecture-standard` con un ajuste específico Account Health: incluir un mini-resumen de qué fuentes consume.

```python
def _header(modulo_nombre: str, fuentes: list[str]):
    st.markdown(f"## 🏥 {modulo_nombre}")
    st.caption(f"📥 Inputs: {' · '.join(fuentes)}")
    st.divider()
```

Ejemplo en módulo Pricing:

```python
_header("Pricing Dashboard", ["FBA Inventory", "Fee Preview", "Product Line", "Maestro", "AWD", "IZZI"])
```

El emoji 🏥 (hospital) es el indicador visual de la sección Account Health en headers. Reservado para esta sección.

### KPI cards — usar `kpi_card()` de `core.helpers`

Idem `ppc-reporting-standard`. Nunca `st.metric` directo.

KPIs que aparecen recurrentes en Account Health:

| KPI | Formato | Color condicional |
|---|---|---|
| Stock total (FBA+AWD+IZZI) | int con separador | `#1A1A1A` siempre |
| DoS Total | int + " días" | 🔴 si <14, 🟠 14-30, 🟢 30-90, 🟡 >90 |
| Margen bruto | percent 1 decimal | 🔴 <15%, 🟠 15-25%, 🟢 >25% |
| AIS proyectado | currency USD | 🔴 si >0, 🟢 si =0 |
| Sell-through | float 2 decimales | 🟢 >2, 🟡 0.5-2, 🔴 <0.5 |
| Aging 366+ | int | 🔴 si >0, 🟢 si =0 |
| SKUs en clasificación X | int + " SKUs" | color según severidad de la clasificación |

### Empty states

Cuando el módulo todavía no recibió input, mostrar un empty state que liste los archivos esperados con su origen exacto:

```python
def _empty_state(fuentes_detalle: list[dict]):
    st.markdown("""
    <div style='border: 2px dashed #FFD9B3; border-radius: 12px; padding: 32px;
                text-align: center; background: #FFF8F0;'>
        <h3 style='color: #E84000; margin-top: 0;'>📂 Subí los archivos para arrancar</h3>
    </div>
    """, unsafe_allow_html=True)

    for f in fuentes_detalle:
        st.markdown(f"**{f['nombre']}** — {f['descripcion']}")
        st.caption(f"📍 Dónde bajarlo: {f['origen']}")
```

Ejemplo:
```python
_empty_state([
    {"nombre": "FBA Inventory",
     "descripcion": "CSV con stock, ventas T7/T30/T90, aging, AIS",
     "origen": "Seller Central → Reports → Fulfillment → Manage FBA Inventory → Download"},
])
```

Decir al usuario *exactamente* dónde se baja cada archivo es una decisión bloqueada del compañero Marcos basada en su SOP. NO simplificar a "subí los archivos necesarios".

### Tabs con `flex-wrap`

Si el módulo tiene 4+ tabs, asegurarse que `st.tabs` use el CSS de wrap para que en pantallas chicas no se rompa horizontalmente. Patrón ya documentado en `ppc-reporting-standard`.

### Tablas con color de fila por severidad

Pandas styler con color condicional. Función helper estándar:

```python
def _style_by_severity(row, severity_col: str = "_severity"):
    """Aplica color de fila según severity. Severities válidas: 'critical', 'important', 'healthy', 'minor', 'info', 'logistic'."""
    SEVERITY_BG = {
        "critical":  "#FEE2E2",
        "important": "#FEF3C7",
        "healthy":   "#F0FDF4",
        "minor":     "#FEFCE8",
        "info":      "#EFF6FF",
        "logistic":  "#F5F3FF",
    }
    sev = row.get(severity_col, "healthy")
    bg = SEVERITY_BG.get(sev, "#FFFFFF")
    return [f"background-color: {bg}"] * len(row)
```

Cada módulo agrega columna `_severity` calculada antes de mostrar la tabla. La columna `_severity` se oculta del display pero impulsa el styling.

---

## 🏥 Conceptos operativos del dominio

### Las 3 ubicaciones de stock — modelo Gamboa

Modelo aplicable a cualquier cliente con esta estructura. NO asumir que aplica a todos los clientes — confirmar antes.

| Ubicación | Qué es | Reglas duras |
|---|---|---|
| **FBA** (Fulfillment by Amazon) | Stock listo para venta inmediata | Target operativo: 30-45 DoS para evitar stockout y aged surcharge |
| **AWD** (Amazon Warehousing & Distribution) | Almacén mayorista de Amazon | NO se vende directo. Reposición a FBA es manual (auto-replenishment APAGADO en Gamboa) |
| **IZZI** | 3PL externo | Solo aplica a categorías específicas — verificar por cliente. En Gamboa solo sombreros |

### Has backup — concepto crítico

Variable que cambia la interpretación de DoS bajo:

```python
has_backup = (awd_available > 0) or (izzi_stock > 0)
```

Cuando `has_backup = True`, un DoS FBA bajo NO debe interpretarse como "subir precio" — es una alerta de **inventario** ("mover unidades a FBA"), no de pricing. Esta distinción es la diferencia entre un sistema operativo serio y uno que genera falsos positivos.

### Health status — vocabulario fijo Amazon

Valores que devuelve el FBA Inventory en columna `fba-inventory-level-health-status`:

- `Excess` → demasiado stock, aged surcharge en camino
- `Low stock` → riesgo de stockout
- `Out of stock` → stockout activo, perdiendo BSR y conversion
- `Healthy` → estado deseado

NO traducir estos valores en UI. Mostrarlos tal cual los devuelve Amazon, con su badge de color.

### Aging buckets — semántica obligatoria

Buckets reales del FBA Inventory (no agrupar diferente):

````
inv-age-0-to-90-days        ← rotación normal
inv-age-91-to-180-days      ← atención
inv-age-181-to-270-days     ← AIS empieza a aplicar
inv-age-271-to-365-days     ← AIS escalando
inv-age-366-to-455-days     ← AIS pesado, considerar liquidación
inv-age-456-plus-days       ← AIS máximo, liquidar urgente
````

Agregaciones canónicas para módulos:
- `aging_0_180` = 0-90 + 91-180 (rotación + atención)
- `aging_181_270` = 181-270 (AIS empezando)
- `aging_271_365` = 271-365 (AIS escalando)
- `aging_366plus` = 366-455 + 456-plus (AIS pesado, candidato a liquidar)

### AIS — Aged Inventory Surcharge

Costo punitivo que Amazon cobra por inventario viejo en FBA. Se acumula a partir del bucket 181+ días.

Suma canónica del módulo:

```python
def compute_ais(row):
    return sum([
        row.get("estimated-ais-181-210-days", 0),
        row.get("estimated-ais-211-240-days", 0),
        row.get("estimated-ais-241-270-days", 0),
        row.get("estimated-ais-271-300-days", 0),
        row.get("estimated-ais-301-330-days", 0),
        row.get("estimated-ais-331-365-days", 0),
        row.get("estimated-ais-366-455-days", 0),
        row.get("estimated-ais-456-plus-days", 0),
    ])
```

**AIS > 0 dispara siempre alerta 🔴.** Es dinero que el cliente está perdiendo en este momento.

---

## 📤 Excel exports — Account Health

Diferencias respecto al `ppc-reporting-standard`:

### Portada del Excel

Cada Excel exportado por un módulo Account Health lleva una portada con:

- Logo Capybaras + título del módulo
- Cliente y período (semana ISO o mes según frecuencia)
- Resumen ejecutivo: 4-6 KPIs principales con su severidad
- Disclaimer pie de página: "Datos al snapshot del [fecha]. Inventario y precios cambian en tiempo real."

### Hojas estándar mínimas

Cualquier Excel de Account Health tiene al menos 2 hojas:

1. **Resumen** — KPIs + tabla maestra con severidades por SKU
2. **Detalle** — todas las columnas crudas del análisis para drilldown

Hojas adicionales según módulo (ej: Pricing tiene Bajar / Subir / Mantener / Liquidar / AWD→FBA como hojas independientes; SKU Progress tiene una hoja por SKU monitoreado).

### Naming del archivo

````
{Cliente}_{Modulo}_{YYYY-WW-o-YYYY-MM}.xlsx
````

Ejemplos:
- `Gamboa_Pricing_2026-W18.xlsx`
- `Gamboa_SKU-Progress_2026-W18.xlsx`
- `Dermaglos_Listing-Compliance_2026-04.xlsx`

NO incluir hora ni timezone en el nombre — el snapshot semanal/mensual ya identifica unívocamente.

---

## ✉️ Tono de comunicación al cliente

Aplican las reglas del `client-communication-tone` skill, con estos refuerzos específicos Account Health:

### Lo que va al cliente

- Severidades visibles con emoji
- Acciones concretas: "mover X unidades de AWD a FBA esta semana"
- Plazos: "antes del lunes 13/05" no "lo antes posible"
- Impacto en USD cuando sea calculable: "esto está costando ~$340 USD/mes en AIS"

### Lo que NO va al cliente

- Detalles técnicos del scoring (-50 / +20 / -8 puntos off-season). Esto es interno.
- Nombres de columnas Amazon raw (`featuredoffer-price`, `unit-session-percentage`)
- Dudas internas del equipo: "habría que revisar el threshold pero..."
- Discrepancias entre fuentes (ej: "el script da 30 días, la macro da 37")

### Excepciones para reportes técnicos compartidos

Cuando el cliente es técnico (Eduardo en Gamboa, por ejemplo), los detalles del scoring sí pueden ir, en una sección "Metodología" al final del reporte. NUNCA en el cuerpo principal.

---

## 🚫 Anti-patterns — Account Health

- ❌ Mezclar pricing y advertising en un mismo módulo. Si necesitás cruzar, hacelo por export+merge externo, no en código.
- ❌ Asumir 3 ubicaciones de stock para todos los clientes. Validar primero.
- ❌ Inventar buckets de aging propios. Los de Amazon son los que son.
- ❌ Calcular AIS de forma diferente a la suma de los 8 buckets canónicos.
- ❌ Mostrar al cliente el score numérico (-50, +20). Es interno.
- ❌ Decir "Buy Box winner price" cuando el campo se llama `featuredoffer-price`. Mantener el nombre técnico cuando se documenta el código, mantener el término de UI ("Buy Box price") cuando se muestra al usuario.
- ❌ Procesar SKUs sin stock. Filtro `available > 0` siempre antes de cualquier análisis de pricing.
- ❌ Olvidar el flag `_est = true` cuando los fees son fallback. La trazabilidad de "este margen es real vs estimado" es clave para decisiones reproducibles.

---

## ✅ Checklist al construir un módulo Account Health

Antes de mergear:

- [ ] Header usa `_header()` con emoji 🏥 y lista de fuentes
- [ ] Empty state lista archivos con su origen exacto en Seller Central
- [ ] Severidades usan los 6 colores canónicos, sin variantes
- [ ] KPIs cumplen con el rango de color condicional definido arriba
- [ ] Términos Amazon en inglés sin traducir
- [ ] Términos de proceso usan vocabulario deliberado (descargar, no solicitar; rutina, no cadencia)
- [ ] Has-backup considerado antes de cualquier alerta de DoS bajo
- [ ] AIS calculado con la suma canónica de los 8 buckets
- [ ] Flag `_est` propagado cuando los fees son fallback
- [ ] Excel export tiene portada + Resumen + Detalle como mínimo
- [ ] Naming del export es `{Cliente}_{Modulo}_{Periodo}.xlsx`
- [ ] Persistencia (si aplica) usa helpers de `core/persistence.py` y sigue `data-persistence-standard`
- [ ] Output al cliente respeta lo que va vs lo que NO va

---

## 🔗 Referencias

- Skill complementario: `module-architecture-standard.md`
- Skill complementario: `data-persistence-standard.md`
- Skill complementario: `client-communication-tone.md`
- Skill PPC: `ppc-reporting-standard.md` (para módulos que crucen ambos dominios)
- Convenciones cliente: `notes/brands/<cliente>/` y `notes/sops/PPC-SOP-Manager.md`
- Decisiones bloqueadas: `notes/state/STATE-agencia.md`
