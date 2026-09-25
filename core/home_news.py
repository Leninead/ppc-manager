"""The news shown on the home page: a hand-kept catalog plus the rules the page applies to it.

The catalog lives in code, not in CHANGELOG.md: the changelog records every technical change,
while this lists only what a teammate would want to open.
"""
from __future__ import annotations

from datetime import date, timedelta

KINDS: tuple[str, ...] = ("new", "improvement")

REQUIRED_FIELDS: tuple[str, ...] = ("id", "title", "description", "date", "kind")

# To add a news item: copy one block and paste it ABOVE the others, so the newest stays first.
# `id` must be unique and `kind` one of KINDS. `page` is the exact routing key of a menu
# destination (`core.navigation.all_pages()`, emoji included) or None when there is no page to
# open; a key that isn't in the menu fails `validate_news` and its test.
NEWS: tuple[dict, ...] = (
    {
        "id": "forecast-por-marca",
        "title": "Forecast por marca",
        "description": "Un cliente con varias marcas en la misma cuenta de Seller Central ahora puede trabajarlas "
                       "como cuentas independientes: cada marca con su histórico, su forecast y un filtro "
                       "Grupo → Cuenta → Marca. La carga mensual usa el reporte Detail Page Sales and Traffic "
                       "By Child Item.",
        "date": date(2026, 9, 25),
        "kind": "new",
        "page": "📈 Monthly Forecast",
    },
    {
        "id": "sops-drive-ppc",
        "title": "SOPs / Drive PPC",
        "description": "Los SOPs y prompts del equipo PPC en un solo lugar: Launch SOP (Track A / Track B), "
                       "Prompt de Reporte Semanal WoW y los Skills y Prompts de Sophie Hub.",
        "date": date(2026, 9, 24),
        "kind": "new",
        "page": "📂 SOPs / Drive PPC",
    },
    {
        "id": "monthly-forecast-estacionalidad",
        "title": "Monthly Forecast",
        "description": "Estacionalidad sin doble conteo y aviso de sobre-proyección.",
        "date": date(2026, 9, 24),
        "kind": "improvement",
        "page": "📈 Monthly Forecast",
    },
    {
        "id": "chat-datos-cuentas",
        "title": "Chat de la app",
        "description": "Responde con datos de las cuentas y sugiere preguntas al abrir.",
        "date": date(2026, 9, 24),
        "kind": "improvement",
        "page": None,
    },
    {
        "id": "sops-drive-am",
        "title": "SOPs / Drive AM",
        "description": "Biblioteca de SOPs del equipo de Account Managers.",
        "date": date(2026, 9, 23),
        "kind": "new",
        "page": "📂 SOPs / Drive AM",
    },
    {
        "id": "oc-lead-time",
        "title": "Órdenes de Compra",
        "description": "Preview del lead time al recibir una OC.",
        "date": date(2026, 9, 23),
        "kind": "improvement",
        "page": "📦 Órdenes de Compra",
    },
)


def latest(news, n: int) -> list[dict]:
    """The `n` most recent items; `sorted` is stable, so a date tie keeps catalog order."""
    return sorted(news, key=lambda item: item["date"], reverse=True)[:n]


def count_since(news, today: date, days: int = 7) -> int:
    cutoff = today - timedelta(days=days)
    return sum(1 for item in news if item["date"] > cutoff)


def validate_news(news, pages) -> list[str]:
    errors = []
    known_pages = set(pages)
    seen_ids = set()
    for position, item in enumerate(news, start=1):
        item_ref = item.get("id") or f"#{position}"
        missing = [field for field in REQUIRED_FIELDS if item.get(field) in (None, "")]
        if missing:
            errors.append(f"{item_ref}: faltan campos {', '.join(missing)}")
        if "page" not in item:
            errors.append(f"{item_ref}: falta el campo page (None si no lleva a una página)")
        for field in ("title", "description"):
            value = item.get(field)
            if value is not None and not str(value).strip():
                errors.append(f"{item_ref}: {field} vacío")
        item_id = item.get("id")
        if item_id:
            if item_id in seen_ids:
                errors.append(f"{item_id}: id duplicado")
            seen_ids.add(item_id)
        kind = item.get("kind")
        if kind and kind not in KINDS:
            errors.append(f"{item_ref}: kind '{kind}' no está en KINDS")
        if item.get("date") is not None and not isinstance(item["date"], date):
            errors.append(f"{item_ref}: date no es una fecha")
        page = item.get("page")
        if page is not None and page not in known_pages:
            errors.append(f"{item_ref}: la página '{page}' no existe en el menú")
    return errors
