_BR_OPTIONAL_COLS = [
    "Sessions - Total", "Sessions - Total - B2B", "Session Percentage - Total",
    "Page Views - Total", "Page Views - Total - B2B", "Featured Offer Percentage",
    "Units Ordered", "Units Ordered - B2B", "Unit Session Percentage",
    "Ordered Product Sales", "Ordered Product Sales - B2B",
    "Total Order Items", "Refund Rate", "Shipped Product Sales", "Units Shipped",
]

# Los destinos del riel, derivados de su unica fuente. Antes era una copia a
# mano y habia derivado: cinco entradas tenian otro emoji o otro nombre que el
# boton real, y dos modulos habian quedado afuera hasta 2c34d1f.
from core.navigation import all_pages as _all_pages

_PAGES = _all_pages()
