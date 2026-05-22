# Porting Sources — HTMLs de origen

Carpeta de inbox para HTMLs standalone que se portean a módulos
Streamlit del Agency OS via el agente `html-to-streamlit-porter`.

## Política

- Los archivos `.html` viven acá pero NO se versionan en git
  (privacidad de los datos del compañero + tamaño del repo).
- Este `_README.md` SÍ se versiona como inventario de trazabilidad:
  qué HTML se porteó, cuándo, a qué módulo del repo, en qué commit.

## Inventario de portings

| HTML fuente | Origen | Fecha port | Módulo destino | Commit |
|---|---|---|---|---|
| flat-file-migrator.html | Marcos (Capybaras) | 2026-05-07 | M27 modules/pages/flat_file_migrator.py | fd192c8 |

## Próximos portings planeados

- sku-progress-report.html → M28 (HTML con persistencia simple, requiere
  coordinación con data-persistence-specialist Caso 2)
- pricing-dashboard.html → M29 (HTML complejo con scoring multi-fuente,
  1-2 días de trabajo. Bug heredado conocido: 30 vs 37 días en
  restock_alert)
