---
fecha: 2026-05-15
tipo: knowledge
modulo: M27
tags: [flat-file, amazon-feedtype, 113-vs-256, apparel, marcos]
---

# M27 Strategy 3.5 Structured (feedType 113 → 256)

## Problema descubierto

Marcos mandó 2 flat files reales para validar M27 (caso Apparel/Coat USA):
- OLD: `ALRBB093.p USA 2026.xlsm` — feedType **113** (legacy fptcustom)
- NEW: `COAT (4).xlsm` — feedType **256** (sistema Listings nuevo)

No es un cambio de versión, es **cambio de schema completo** entre 2 sistemas
distintos de Amazon. M27 v1 (5 estrategias: exact → normalized → alias → base
→ header) daba 41% de cobertura y fallaba `standard_price` y `quantity` porque
en 256 son subfields anidados:

- `standard_price` → `purchasable_offer[marketplace_id=ATVPDKIKX0DER][audience=ALL]#1.our_price#1.schedule#1.value_with_tax`
- `quantity` → `fulfillment_availability#1.quantity`

El normalizador del módulo eliminaba `[brackets]` y `#N.field` pero dejaba
los subfields anidados intermedios — los `_ALIASES` simples no llegaban.

## Solución: Strategy 3.5 Structured

Agregada entre Strategy 3 (alias) y Strategy 4 (base):

```python
# Constante nueva:
_STRUCTURED_ALIASES = {
    "standard_price": ("purchasable_offer", r"audience=ALL.*our_price.*value_with_tax"),
    "quantity":       ("fulfillment_availability", r"\.quantity$"),
    # ...40 entradas totales (precio, inventario, dimensiones, peso, imágenes)
}

# Lógica:
# Para cada old field plano que esté en _STRUCTURED_ALIASES:
#   1. Buscar en new field_ids un attr cuya RAÍZ (antes del primer [ o #) coincida
#   2. Y cuyo full attr matchee el regex de subfield
```

## Resultado validado

- Cobertura: **41% → 50.7%** (+22 matches, 115/227)
- Críticos: **7/9 → 9/9 ✓**
- Strategy 3.5 aporta 24 matches estructurados precisos

## Limitaciones explícitas

- Tabla `_STRUCTURED_ALIASES` está validada solo para **Apparel/Coat USA**
- Otras categorías (electrónica, comida, beauty) tienen otros nombres en 256
  → habría que agregar entradas a la tabla
- Full robusto (todos los ~250 productTypes de Amazon) NO es alcance hoy:
  serían 1-2 semanas de trabajo

## Cuándo extender

Solo cuando aparezca un caso real de otro productType. Patrón:
1. Cliente reporta caso 113→256 en otra categoría
2. Lenin inspecciona los 2 archivos con script offline (ver
   `tests/test_m27_v2_structured.py` como plantilla)
3. Agregar entradas faltantes a `_STRUCTURED_ALIASES`
4. Test fixture nueva + commit + actualizar este knowledge

## Archivos relacionados

- `modules/pages/flat_file_migrator.py` — código del módulo
- `tests/test_m27_v2_structured.py` — test offline E2E
- `tests/fixtures/m27/old_apparel_113.xlsm` — fixture OLD
- `tests/fixtures/m27/new_apparel_256.xlsm` — fixture NEW

## Wikilinks

[[STATE-agencia]] · [[CLAUDE]] · [[2026-05-15]]
