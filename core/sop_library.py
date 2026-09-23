"""The AM SOP library: a versioned catalog of Drive links plus the rules the page applies to it.

The catalog lives in code, not under data/: in production data/ is a volume seeded with
`cp -rn`, so an edited catalog there would never replace the copy already on the volume.
"""
from __future__ import annotations

import unicodedata
from datetime import date

CATEGORIES: tuple[str, ...] = (
    "Lanzamiento",
    "Onboarding",
    "Listings",
    "PPC",
    "Reporting",
    "Operaciones",
)

ALL_CATEGORIES = "Todas"

NEW_DAYS = 14
REVIEW_DAYS = 90

REQUIRED_FIELDS: tuple[str, ...] = (
    "id", "title", "description", "category", "url", "owner", "added", "last_reviewed",
)

# To add a SOP: copy one block below and fill in every field.
# `id` must be unique, `category` must be one of CATEGORIES, and `url` must start with https://.
# `added` drives the "Nuevo" badge (NEW_DAYS); bump `last_reviewed` whenever the doc is
# re-checked, or it gets the "Revisar" badge after REVIEW_DAYS.
SOPS: tuple[dict, ...] = (
    {
        "id": "sop-lanzamiento",
        "title": "SOP Maestro — Lanzamiento de producto",
        "description": "Proceso estándar para lanzar un producto nuevo en Amazon.",
        "category": "Lanzamiento",
        "url": "https://docs.google.com/document/d/1opEPYOObU4ArV_g9M31M87cZOqmJIAtL/edit",
        "owner": "Equipo AM",
        "added": date(2026, 9, 23),
        "last_reviewed": date(2026, 9, 23),
    },
)

_DOC_TYPES: tuple[tuple[str, str, str, str], ...] = (
    ("docs.google.com/document", "doc", "Doc", ":material/description:"),
    ("docs.google.com/spreadsheets", "sheet", "Sheet", ":material/table_chart:"),
    ("docs.google.com/presentation", "slides", "Slides", ":material/slideshow:"),
    ("drive.google.com/drive/folders", "folder", "Carpeta", ":material/folder:"),
    ("loom.com", "video", "Loom", ":material/play_circle:"),
    ("drive.google.com/file", "pdf", "Archivo", ":material/picture_as_pdf:"),
)
_PDF_TYPE = {"key": "pdf", "label": "Archivo", "icon": ":material/picture_as_pdf:"}
_LINK_TYPE = {"key": "link", "label": "Link", "icon": ":material/link:"}


def detect_doc_type(url: str) -> dict:
    lowered = (url or "").lower()
    for fragment, key, label, icon in _DOC_TYPES:
        if fragment in lowered:
            return {"key": key, "label": label, "icon": icon}
    if lowered.split("?")[0].split("#")[0].endswith(".pdf"):
        return dict(_PDF_TYPE)
    return dict(_LINK_TYPE)


def badges(sop: dict, today: date) -> list[str]:
    found = []
    if (today - sop["added"]).days <= NEW_DAYS:
        found.append("new")
    if (today - sop["last_reviewed"]).days > REVIEW_DAYS:
        found.append("review")
    return found


def filter_sops(sops, query: str, category: str | None) -> list:
    needle = _normalize(query or "")
    matches = []
    for sop in sops:
        if category not in (None, ALL_CATEGORIES) and sop["category"] != category:
            continue
        haystack = _normalize(
            " ".join(str(sop[field]) for field in ("title", "description", "owner", "category"))
        )
        if needle and needle not in haystack:
            continue
        matches.append(sop)
    return matches


def validate_catalog(sops) -> list[str]:
    errors = []
    seen_ids = set()
    for position, sop in enumerate(sops, start=1):
        sop_ref = sop.get("id") or f"#{position}"
        missing = [field for field in REQUIRED_FIELDS if sop.get(field) in (None, "")]
        if missing:
            errors.append(f"{sop_ref}: faltan campos {', '.join(missing)}")
        sop_id = sop.get("id")
        if sop_id:
            if sop_id in seen_ids:
                errors.append(f"{sop_id}: id duplicado")
            seen_ids.add(sop_id)
        category = sop.get("category")
        if category and category not in CATEGORIES:
            errors.append(f"{sop_ref}: categoría '{category}' no está en CATEGORIES")
        url = sop.get("url")
        if url and not str(url).startswith("https://"):
            errors.append(f"{sop_ref}: la url no empieza con https://")
    return errors


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(letter for letter in decomposed if not unicodedata.combining(letter))
