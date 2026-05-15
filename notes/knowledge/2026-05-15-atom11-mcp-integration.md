---
fecha: 2026-05-15
tipo: knowledge
tags: [atom11, mcp, integration, claude, ppc-tooling]
estado: discovery-pendiente
---

# Atom11 MCP Integration — Discovery diferido

## Update de Cuki (Slack 15/05)

Atom11 publicó integración MCP nativa con Claude:
- **URL**: `https://api.atom11.co/mcp`
- **Setup**: ~2 min via guía oficial en Notion
- **25 tools custom** disponibles del MCP

## Estado actual en la agencia

- **Gregorio**: conectado y usando activamente
- **Cuki**: recomienda adopción a todo el equipo
- **Lenin**: conectado con "Always allow", sin uso operativo todavía
- **Resto del equipo**: pendiente

## 25 tools disponibles (catálogo)

Por entidad, cada una con variantes `base / _compare / _graph`:
- `get_ad_groups` + compare + graph
- `get_audiences` + compare + graph
- `get_campaigns` + compare + graph
- `get_keywords` + compare + graph
- `get_placements` + compare + graph
- `get_product_ads` + compare + graph
- `get_product_targets` + compare + graph
- `get_search_terms` + compare + graph

Más:
- `get_my_profiles`
- `get_manager_query_capabilities`
- `get_negative_targets`

## Estado Atom11 por cliente (snapshot)

Ver STATE-agencia.md sección Atom11. 5/6 clientes con cuenta Atom11 activa.
Pendiente confirmar cuál cuenta usó Lenin para conectar el MCP (multi-cliente
vs single).

## Plan de discovery (semana 18-25/05, sesión dedicada ~45 min)

### Paso 1 — Discovery (10 min)
- `get_my_profiles` → ver qué cuentas/profiles tiene visibles Claude
- `get_manager_query_capabilities` → entender qué filtros/sorts/graphs soporta

### Paso 2 — Caso de uso real con Dermaglos (20 min)
Dermaglos es el cliente Atom11 más maduro de Capybaras. Probar query típica
del workflow semanal: "Top 10 search terms de la semana W19 con CTR > 0.5%
y orders > 0, comparados con W18".

### Paso 3 — Decisión arquitectónica (15 min)
- ¿Documentar workflows MCP en `notes/knowledge/atom11-workflows/`?
- ¿Reemplaza algo de M14 Weekly Client Report?
- ¿Vale módulo M30 Streamlit server-side usando MCP?

## Hipótesis previas al discovery (a validar)

1. **MCP NO reemplaza M14**: M14 tiene persistencia histórica + decomposición
   orgánico vs paid + Excel deliverables. MCP es real-time conversacional, no
   reemplaza eso.
2. **Lo más probable**: documentar workflows MCP en `notes/knowledge/` sin
   tocar repo de código. Es agencia layer, no producto.
3. **Módulo M30 server-side NO**: la potencia está en chat conversacional,
   no en re-empacarlo en Streamlit.

## Preguntas abiertas

1. ¿Con qué cuenta de Atom11 se conectó Lenin? (multi-cliente vs single)
2. Riesgo de cross-contamination si una cuenta ve múltiples perfiles —
   toda sesión debe ser explícita sobre qué profile consulta
3. ¿Cuál es el costo de tokens? (cada query consume ventana)

## Por qué se difiere (no se trabajó hoy)

- M29 tiene compromiso público Slack 12/05 (fases 3+4 esta semana,
  vence domingo 18/05)
- M27 tenía closing loop con Marcos pendiente
- Atom11 no bloquea ningún cliente urgente — workflow actual con Atom11 UI
  funciona

## Wikilinks

[[STATE-agencia]] · [[atom11-rules]] · [[DERMAGLOS_DATA]] · [[2026-05-15]]
