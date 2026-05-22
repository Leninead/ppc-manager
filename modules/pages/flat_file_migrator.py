"""
Módulo: Flat File Migrator (M27)
Fuente: porteado de .claude/porting-sources/flat-file-migrator.html
Sección: Account Health
Versión: v1
Autor original: compañero PPC (HTML standalone)
Porteado: 2026-05-06

Migra datos de un flat file Amazon viejo a un template nuevo, mapeando
columnas por field_id (estrategia exact → normalized → alias → base → header).
Soporta 5 marketplaces: USA · Germany · Italy · France · Spain.
Stateless por diseño — sin persistencia.
"""
from __future__ import annotations

import io
import re
from typing import Optional

import streamlit as st
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter

from core.helpers import kpi_card


# ── Constants ───────────────────────────────────────────────────────────

MODULE_SLUG = "flat_file_migrator"
AREA = "Account Health"

# Marketplaces y sus sheet names esperados (en orden de búsqueda)
_MARKETPLACES = [
    {"suffix": "us", "label": "🇺🇸 USA — Template",     "sheets": ["Template"]},
    {"suffix": "de", "label": "🇩🇪 Germany — Vorlage",  "sheets": ["Vorlage", "Template"]},
    {"suffix": "it", "label": "🇮🇹 Italy — Modello",     "sheets": ["Modello", "Template"]},
    {"suffix": "fr", "label": "🇫🇷 France — Modèle",     "sheets": ["Modèle", "Template"]},
    {"suffix": "es", "label": "🇪🇸 Spain — Plantilla",  "sheets": ["Plantilla", "Template"]},
]

# Palabras clave que indican que una row es header de flat file Amazon
# (multi-idioma EN/DE/IT/FR/ES + Category Listing variants)
# Replicado literal del HTML L764-778
_HEADER_KEYWORDS = {
    # Internal field IDs
    "sku", "item_sku", "product_id", "asin", "item_name", "feed_product_type",
    "brand_name", "manufacturer", "part_number", "update_delete",
    # EN
    "seller sku", "product type", "brand", "title", "update / delete", "standard product id",
    # DE
    "verkäufer-sku", "produkttyp", "marke", "titel", "aktualisieren / löschen", "hersteller",
    # IT
    "sku venditore", "tipo di prodotto", "marchio", "titolo", "aggiornamento - eliminazione", "produttore",
    # FR
    "référence vendeur", "type de produit", "marque", "titre", "mettre à jour / supprimer", "fabricant",
    # ES
    "sku del vendedor", "tipo de producto", "marca", "título", "actualizar / eliminar", "fabricante",
    # Category Listing common
    "status",
}

# Tipos de ejemplo que Amazon mete como first data row (para skip)
# Replicado literal del HTML L812
_AMAZON_EXAMPLE_TYPES = {
    "SHIRT", "SHOES", "LUGGAGE", "HANDBAG", "WATCH", "PANTS", "DRESS", "JACKET",
    "COAT", "SHORTS", "SKIRT", "SWEATER", "SUIT", "SWIMWEAR", "UNDERWEAR",
    "ACCESSORY", "BAG", "BELT", "GLOVES", "HAT", "SCARF", "SOCKS", "TIE",
    "WALLET", "BACKPACK", "UMBRELLA", "SUNGLASSES",
}

# Aliases bidireccionales entre nombres viejos y nuevos de fields
# Copia literal de ALIASES del HTML L881-912
_ALIASES = {
    "contribution_sku": ["item_sku"], "item_sku": ["contribution_sku"],
    "child_parent_sku_relationship": ["parent_sku"], "parent_sku": ["child_parent_sku_relationship"],
    "product_type": ["feed_product_type"], "feed_product_type": ["product_type"],
    "brand": ["brand_name"], "brand_name": ["brand"],
    "parentage_level": ["parent_child"], "parent_child": ["parentage_level"],
    "amzn1.volt.ca.product_id_type": ["external_product_id_type"],
    "external_product_id_type": ["amzn1.volt.ca.product_id_type"],
    "amzn1.volt.ca.product_id_value": ["external_product_id"],
    "external_product_id": ["amzn1.volt.ca.product_id_value"],
    "item_type_keyword": ["item_type_name", "item_type"],
    "item_type_name": ["item_type_keyword", "item_type"],
    "item_type": ["item_type_keyword", "item_type_name"],
    "model": ["model_number"], "model_number": ["model"],
    "closure": ["closure_type"], "closure_type": ["closure"],
    "generic_keyword": ["generic_keywords"], "generic_keywords": ["generic_keyword"],
    "update_delete": ["::record_action"], "::record_action": ["update_delete"],
    "main_product_image_locator": ["main_image_url"],
    "main_image_url": ["main_product_image_locator"],
    "other_product_image_locator_1": ["other_image_url1"],
    "other_product_image_locator_2": ["other_image_url2"],
    "other_product_image_locator_3": ["other_image_url3"],
    "other_product_image_locator_4": ["other_image_url4"],
    "other_product_image_locator_5": ["other_image_url5"],
    "other_product_image_locator_6": ["other_image_url6"],
    "other_product_image_locator_7": ["other_image_url7"],
    "other_product_image_locator_8": ["other_image_url8"],
    "swatch_product_image_locator": ["swatch_image_url"],
    "swatch_image_url": ["swatch_product_image_locator"],
    "target_audience_keyword": ["target_audience_keywords"],
    "target_audience_keywords": ["target_audience_keyword"],
    "style": ["style_name"], "style_name": ["style"],
    "size": ["size_name"], "size_name": ["size"],
    "color": ["color_name"], "color_name": ["color"],
    "occasion": ["occasion_type"], "occasion_type": ["occasion"],
    "manufacturer_minimum_age": ["mfg_minimum"], "mfg_minimum": ["manufacturer_minimum_age"],
    "manufacturer_maximum_age": ["mfg_maximum"], "mfg_maximum": ["manufacturer_maximum_age"],
    "sub_brand": ["sub_brand_name"], "sub_brand_name": ["sub_brand"],
    "supplier_declared_dg_hz_regulation": [
        "supplier_declared_dg_hz_regulation1", "supplier_declared_dg_hz_regulation2",
        "supplier_declared_dg_hz_regulation3", "supplier_declared_dg_hz_regulation4",
        "supplier_declared_dg_hz_regulation5",
    ],
    "batteries_required": ["batteries_required"],
    "batteries_included": ["are_batteries_included"],
    "are_batteries_included": ["batteries_included"],
    "outer_material_type": ["material"], "material_type": ["material"],
    "material": ["outer_material_type", "material_type"],
    "seasons": ["seasons1", "seasons2", "seasons3", "seasons4", "seasons5"],
}

# Cross-schema label aliases: labels que cambiaron entre fptcustom (old) y PTD (new).
# Formato: {label_old_normalizado: label_new_normalizado}.
# Match es bidireccional — el helper _build_field_map lo aplica en ambas direcciones.
# Mantener corto y conservador: solo agregar aliases que hayan sido empíricamente
# observados, no especular.
_LABEL_ALIASES: dict[str, str] = {
    "seller sku": "sku",                 # old "Seller SKU" → new "SKU"
    "update delete": "listing action",   # old "Update Delete" → new "Listing Action"
    "product name": "item name",         # old "Product Name" → new "Item Name"
}

# Regex para strippear sufijo de categoría en labels de la hoja 'Valid Values'.
# Match ' - [ CATEGORIA ]' al final del label, incluso con corchetes vacíos
# (ej. ' - [  ]', observado empíricamente en COAT__5_.xlsm).
_VALID_VALUES_SUFFIX_RE = re.compile(r"\s*-\s*\[\s*[^\]]*\s*\]\s*$")

# Mapping de valid values entre schemas para enums cross-schema.
# Estructura: {old_label: {"new_label": str, "values": {old_val: new_val_or_None}}}
#
# Decisión de scope (2026-05-19): conservador. Values sin mapping 1:1
# identidad o rewording confirmado quedan como None — B5 row migrator los
# flagea como "value deprecated, requiere revisión manual" en vez de
# adivinar mapping. Esto previene meter data potencialmente incorrecta al
# listing en Amazon.
#
# Cobertura actual: 3 enums críticos. Otros enums con <=10 values en
# Valid Values (ver _parse_valid_values) son candidatos para expansión
# iterativa cuando aparezca un caso real que los requiera.
_ENUM_VALUE_MAP: dict[str, dict] = {
    "Update Delete": {
        "new_label": "Listing Action",
        "values": {
            "Delete": "Delete",
            "Partial Update": "Edit (Partial Update)",
            "Full Update": "Create or Replace (Full Update)",
        },
    },
    "Parentage": {
        "new_label": "Parentage Level",
        "values": {
            "Parent": "Parent",
            "Child": "Child",
        },
    },
    "Product ID Type": {
        "new_label": "Product Id Type",
        "values": {
            "EAN": "EAN",
            "GTIN": "GTIN",
            "UPC": "UPC",
            "ASIN": "ASIN",
            "ISBN": None,  # deprecated en PTD; Capybaras no maneja books
            "GCID": None,  # deprecated en PTD; fallback row-level vive en B5
        },
    },
}

# Fields OLD enteros que NO tienen contraparte en PTD schema.
# B5 detecta estos y emite diagnóstico "schema gap, manual review" en
# vez del genérico "unknown value". Documentado en hallazgos discovery
# 2026-05-19.
_DEPRECATED_OLD_ENUMS: frozenset[str] = frozenset({
    "Relationship Type",  # PTD usa child_parent_sku_relationship + components
    "Variation Theme",    # PTD usa variation_theme_name + structured components
})

# Tabla de fallback con header structure conocida por schema.
# Usada si la auto-detección no converge. Documentado empíricamente
# 2026-05-19: fptcustom data starts row 4, PTD data starts row 6.
# Rows son 1-indexed (consistente con openpyxl).
_TEMPLATE_HEADER_FALLBACK: dict[str, dict[str, int | None]] = {
    "fptcustom": {
        "display_row": 2,
        "field_id_row": 3,
        "data_start_row": 4,
        "group_banner_row": None,  # fptcustom no tiene group banners
    },
    "ptd": {
        "display_row": 4,
        "field_id_row": 5,
        "data_start_row": 6,
        "group_banner_row": 3,  # PTD tiene Listing Identity / Variations / etc
    },
}


# ── Helpers — sheet/row inspection (porteados de las funciones JS) ──────

def _detect_schema(wb) -> str:
    """Detecta el schema del template Amazon a partir de la hoja Template.

    Heurística sobre el valor de la celda A1 de la hoja 'Template':
    - "fptcustom": substring 'TemplateType=fptcustom' presente
    - "ptd": substring 'feedType=256' presente (Product Type Definition schema)
    - "unknown": ninguna firma reconocida, hoja 'Template' ausente, o A1 vacío

    Args:
        wb: openpyxl Workbook ya abierto. Caller responsable de abrir/cerrar.

    Returns:
        Uno de: "fptcustom", "ptd", "unknown".
    """
    if "Template" not in wb.sheetnames:
        return "unknown"
    a1 = wb["Template"].cell(row=1, column=1).value
    if not a1:
        return "unknown"
    a1_str = str(a1)
    if "TemplateType=fptcustom" in a1_str:
        return "fptcustom"
    if "feedType=256" in a1_str:
        return "ptd"
    return "unknown"


def _parse_data_definitions(wb) -> dict[str, dict[str, str]]:
    """Parsea la hoja 'Data Definitions' del template Amazon.

    Funciona idéntico para fptcustom y PTD porque ambos schemas usan la misma
    estructura: row 2 con headers, row 3+ con filas que pueden ser separadores
    de grupo (solo 'Group Name' lleno) o fields (con 'Field Name' lleno).

    Args:
        wb: openpyxl Workbook ya abierto. Caller responsable de abrir/cerrar.

    Returns:
        Dict {field_name: {"label": str, "group": str, "example": str,
        "required": str}}.
        - field_name: valor crudo de columna 'Field Name' (puede tener namespaces).
        - label: valor de 'Local Label Name'.
        - group: el último separador de grupo visto, asignado en cascada.
        - example: valor de 'Example' (puede ser '' si la cell está vacía).
        - required: valor de 'Required?' si la columna existe; '' si no existe
          (caso fptcustom old que no tiene esa columna).

        Devuelve dict vacío si la hoja 'Data Definitions' no existe en el workbook.
    """
    if "Data Definitions" not in wb.sheetnames:
        return {}
    ws = wb["Data Definitions"]

    all_rows = list(ws.iter_rows(values_only=True))
    if len(all_rows) < 3:
        return {}

    # Row 2 (index 1): header → col_map con header lowercased+stripped → col_idx 0-based.
    header_row = all_rows[1]
    col_map: dict[str, int] = {}
    for col_idx, cell in enumerate(header_row):
        if cell is None:
            continue
        key = str(cell).strip().lower()
        if key and key not in col_map:
            col_map[key] = col_idx

    required_keys = ("group name", "field name", "local label name", "example")
    if not all(k in col_map for k in required_keys):
        # header mismatch: retorna vacío para que caller decida fallback
        return {}

    c_group = col_map["group name"]
    c_field = col_map["field name"]
    c_label = col_map["local label name"]
    c_example = col_map["example"]
    c_required = col_map.get("required?")  # opcional (fptcustom old no la tiene)

    def _safe(row: tuple, col_idx: int | None) -> str:
        if col_idx is None or col_idx >= len(row):
            return ""
        v = row[col_idx]
        return str(v).strip() if v is not None else ""

    out: dict[str, dict[str, str]] = {}
    current_group = ""
    blank_streak = 0
    for row in all_rows[2:]:
        group_val = _safe(row, c_group)
        field_val = _safe(row, c_field)
        if not group_val and not field_val:
            blank_streak += 1
            if blank_streak >= 3:
                break
            continue
        blank_streak = 0
        if group_val and not field_val:
            current_group = group_val
            continue
        if field_val:
            out[field_val] = {
                "label": _safe(row, c_label),
                "group": current_group,
                "example": _safe(row, c_example),
                "required": _safe(row, c_required),
            }
    return out


def _normalize_label(label: str) -> str:
    """Normaliza un Local Label Name para matching cross-schema.

    Lowercased, stripped, espacios internos colapsados, paréntesis y su contenido
    eliminados (ej: "Price (USD)" → "price").

    No reutiliza _normalize_field_id (opera sobre field IDs Amazon con brackets/
    hash/sufijos numéricos) ni _ALIASES (mapea field_names, no labels humanos).

    Args:
        label: valor crudo de la columna 'Local Label Name' (puede ser None).

    Returns:
        String normalizado. "" si label es falsy.
    """
    if not label:
        return ""
    s = str(label)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _build_field_map(
    old_dd: dict[str, dict[str, str]],
    new_dd: dict[str, dict[str, str]],
) -> tuple[dict[str, str], list[str]]:
    """Construye mapping {old_field_name: new_field_name} match por Local Label Name.

    Estrategia:
    1. Indexar new_dd por _normalize_label(label) → list[new_field_name].
       Lista porque puede haber colisión (ej. los "Other Image URL" 1..N que
       comparten label).
    2. Para cada old_field: normalizar su label, probar match directo, luego
       _LABEL_ALIASES en ambas direcciones.
    3. Si hay >1 candidato → tomar el primero y agregar warning de colisión.
       Si no hay match → agregar warning "sin correspondencia".

    Args:
        old_dd: output de _parse_data_definitions sobre el workbook OLD.
        new_dd: output de _parse_data_definitions sobre el workbook NEW.

    Returns:
        (mapping, warnings):
        - mapping: dict {old_field_name: new_field_name}. Solo entries con match.
        - warnings: list[str] human-readable.
    """
    new_by_label: dict[str, list[str]] = {}
    for new_field, info in new_dd.items():
        nl = _normalize_label(info.get("label", ""))
        if not nl:
            continue
        new_by_label.setdefault(nl, []).append(new_field)

    mapping: dict[str, str] = {}
    warnings: list[str] = []

    for old_field, old_info in old_dd.items():
        old_label = old_info.get("label", "")
        old_label_norm = _normalize_label(old_label)
        if not old_label_norm:
            warnings.append(f"old field '{old_field}' tiene label vacío, skip")
            continue

        candidates: list[str] = []
        # (a) match directo por label normalizado
        if old_label_norm in new_by_label:
            candidates = new_by_label[old_label_norm]
        else:
            # (b) old → new via alias forward
            aliased = _LABEL_ALIASES.get(old_label_norm)
            if aliased and aliased in new_by_label:
                candidates = new_by_label[aliased]
            else:
                # (c) inverse: encontrar key cuyo valor sea old_label_norm,
                # luego buscar la key en new_by_label
                for k, v in _LABEL_ALIASES.items():
                    if v == old_label_norm and k in new_by_label:
                        candidates = new_by_label[k]
                        break

        if not candidates:
            warnings.append(
                f"old field '{old_field}' (label='{old_label}') sin correspondencia en new"
            )
            continue

        mapping[old_field] = candidates[0]
        if len(candidates) > 1:
            extras = ", ".join(candidates[1:])
            warnings.append(
                f"colisión: old field '{old_field}' (label='{old_label}') matchea "
                f"contra {len(candidates)} new fields, se usó '{candidates[0]}' "
                f"(otros: {extras})"
            )

    return mapping, warnings


def _parse_valid_values(wb) -> dict[str, list[str]]:
    """Parsea la hoja 'Valid Values' del workbook a {label: [values]}.

    Schema-agnostic: mismo formato wide en fptcustom y PTD. Las rows con
    solo col0 poblada son section separators (skipped). Las rows de field
    tienen label en col1 con sufijo categoría (ej. ' - [ COAT ]' o
    ' - [ coat ]'), que se strippea con _VALID_VALUES_SUFFIX_RE.

    Args:
        wb: openpyxl Workbook abierto (caller-managed lifecycle).

    Returns:
        dict de {clean_label: [valid_value, ...]} con label sin sufijo y
        values stringified+stripped, sin None ni vacíos.

    Raises:
        KeyError si la hoja 'Valid Values' no existe en el workbook.
    """
    ws = wb["Valid Values"]
    result: dict[str, list[str]] = {}
    for row in ws.iter_rows(values_only=True):
        col1 = row[1] if len(row) > 1 else None
        if not isinstance(col1, str) or not col1.strip():
            continue
        clean_label = _VALID_VALUES_SUFFIX_RE.sub("", col1).strip()
        values = [
            str(v).strip()
            for v in row[2:]
            if v is not None and str(v).strip()
        ]
        result[clean_label] = values
    return result


def _build_value_map(
    old_vv: dict[str, list[str]],
    new_vv: dict[str, list[str]],
) -> tuple[dict[str, dict[str, str | None]], list[str]]:
    """Cruza _ENUM_VALUE_MAP con valid values reales para sanity-check + build translator.

    Para cada entry de _ENUM_VALUE_MAP valida que:
    - El old_label existe en old_vv (= aparece en hoja Valid Values del template old).
    - Cada old_value declarado existe en old_vv[old_label].
    - El new_label existe en new_vv.
    - Cada new_value no-None declarado existe en new_vv[new_label].

    Acumula warnings para todas las divergencias (no raisea), permitiendo
    que el caller decida si proceder o abortar.

    Args:
        old_vv: output de _parse_valid_values(old_wb).
        new_vv: output de _parse_valid_values(new_wb).

    Returns:
        Tupla (mapping, warnings):
        - mapping: {old_label: {old_value: new_value_or_None}} flatten para uso
          directo en B5 row migrator. Solo incluye entries que pasaron sanity
          check. Si una entry falla validación al nivel de old_label o new_label,
          se omite del mapping y se logea como warning.
        - warnings: list[str] de divergencias detectadas, formato human-readable.
    """
    mapping: dict[str, dict[str, str | None]] = {}
    warnings: list[str] = []

    for old_label, spec in _ENUM_VALUE_MAP.items():
        new_label = spec["new_label"]
        declared_values = spec["values"]

        if old_label not in old_vv:
            warnings.append(
                f"_ENUM_VALUE_MAP declara old_label {old_label!r} pero no aparece "
                f"en old Valid Values — entry omitida"
            )
            continue
        if new_label not in new_vv:
            warnings.append(
                f"_ENUM_VALUE_MAP declara new_label {new_label!r} (para old "
                f"{old_label!r}) pero no aparece en new Valid Values — entry omitida"
            )
            continue

        old_actual = set(old_vv[old_label])
        new_actual = set(new_vv[new_label])
        entry: dict[str, str | None] = {}

        for old_val, new_val in declared_values.items():
            if old_val not in old_actual:
                warnings.append(
                    f"{old_label!r}: declared old_value {old_val!r} no existe en "
                    f"old Valid Values (presentes: {sorted(old_actual)})"
                )
                continue
            if new_val is not None and new_val not in new_actual:
                warnings.append(
                    f"{old_label!r} → {new_label!r}: declared new_value {new_val!r} "
                    f"no existe en new Valid Values (presentes: {sorted(new_actual)})"
                )
                continue
            entry[old_val] = new_val

        # Detectar values old reales NO cubiertos por el map (= candidate
        # custom values del cliente que B5 va a flaggear).
        uncovered = old_actual - set(declared_values.keys())
        if uncovered:
            warnings.append(
                f"{old_label!r}: values en old Valid Values NO mapeados: "
                f"{sorted(uncovered)} — B5 va a flaggear unknown enum si aparecen en rows"
            )

        mapping[old_label] = entry

    return mapping, warnings


def _looks_like_field_id(s: str) -> bool:
    """Heurística: el string parece un field_id interno Amazon.

    True si: prefix '::', bracketed path '[...=...]', dot/hash indexing
    ('#' o '.value'), o snake_case puro (lowercase + underscore + sin espacios).
    False en cualquier otro caso (incluyendo None, vacío, Title Case).
    """
    if not isinstance(s, str):
        return False
    s = s.strip()
    if not s:
        return False
    if s.startswith("::"):
        return True
    if "[" in s and "]" in s:
        return True
    if "#" in s or ".value" in s:
        return True
    if " " not in s and "_" in s and s.islower():
        return True
    return False


def _looks_like_display_label(s: str) -> bool:
    """Heurística: el string parece un display label Title Case.

    True si NO matchea _looks_like_field_id Y tiene espacios (multi-word)
    O empieza con uppercase (Title Case / acronym). False si None/vacío.
    """
    if not isinstance(s, str):
        return False
    s = s.strip()
    if not s:
        return False
    if _looks_like_field_id(s):
        return False
    if " " in s:
        return True
    return s[0].isupper()


def _locate_template_headers(wb) -> dict[str, int | None]:
    """Identifica las rows estructurales de la hoja 'Template'.

    Estrategia D1+fallback:
    1. Auto-detección row-by-row buscando patterns de field_id internos
       (snake_case, bracketed marketplace paths, :: prefix).
    2. Si auto-detección converge Y los field_ids matchean al menos
       parcialmente con Data Definitions (B2), retorna ese mapping.
       NOTA: si _parse_data_definitions retorna dict vacío (hoja Data
       Definitions ausente o malformada), la cross-validation matches>=3
       falla closed → cae a fallback por schema. Decisión by-design: si
       no podemos cruzar con B2, el fallback hardcoded es más seguro que
       confiar solo en heurísticas string-pattern.
    3. Si no, cae a _TEMPLATE_HEADER_FALLBACK indexado por schema
       (detectado con _detect_schema).

    Args:
        wb: openpyxl Workbook abierto (caller-managed lifecycle).

    Returns:
        dict con keys:
        - 'display_row' (int, 1-indexed): row con display labels
        - 'field_id_row' (int, 1-indexed): row con field IDs internos
        - 'data_start_row' (int, 1-indexed): primera row de data real
        - 'group_banner_row' (int | None): row con group banners
          (solo PTD), None si no aplica
        - 'detection_method' (str): 'auto' o 'fallback'

    Raises:
        KeyError si la hoja 'Template' no existe.
        ValueError si auto-detección Y fallback ambos fallan (schema
          desconocido en _TEMPLATE_HEADER_FALLBACK).
    """
    ws = wb["Template"]

    # Cachear primeras 8 rows (suficiente; soporta read_only mode).
    rows_data: list[tuple] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= 8:
            break
        rows_data.append(row)

    def _at(row_1idx: int, col_1idx: int):
        r = row_1idx - 1
        c = col_1idx - 1
        if r < 0 or r >= len(rows_data):
            return None
        row = rows_data[r]
        if c < 0 or c >= len(row):
            return None
        return row[c]

    # Heurística 1: scan rows 1..8 contando field_id-like strings en cols 1..16.
    max_row_to_scan = min(8, len(rows_data))
    field_id_row: int | None = None
    max_fid_score = 0
    for r in range(1, max_row_to_scan + 1):
        fid_count = 0
        for c in range(1, 17):
            v = _at(r, c)
            if isinstance(v, str) and _looks_like_field_id(v):
                fid_count += 1
        if fid_count >= 5 and fid_count > max_fid_score:
            max_fid_score = fid_count
            field_id_row = r

    schema = _detect_schema(wb)
    auto_ok = False
    display_row: int | None = None

    if field_id_row is not None:
        # Cross-validation con B2: al menos 3 de los primeros 5 field_ids
        # detectados deben aparecer como keys en _parse_data_definitions.
        dd = _parse_data_definitions(wb)
        dd_keys = set(dd.keys())
        sample_ids: list[str] = []
        for c in range(1, 17):
            v = _at(field_id_row, c)
            if isinstance(v, str):
                s = v.strip()
                if _looks_like_field_id(s):
                    sample_ids.append(s)
            if len(sample_ids) >= 5:
                break
        matches = sum(1 for f in sample_ids if f in dd_keys)

        if matches >= 3:
            # display_row: walk up desde field_id_row - 1 hasta encontrar row
            # con >=5 Title Case strings.
            cand = field_id_row - 1
            while cand >= 1:
                disp_score = 0
                for c in range(1, 17):
                    v = _at(cand, c)
                    if isinstance(v, str) and _looks_like_display_label(v):
                        disp_score += 1
                if disp_score >= 5:
                    display_row = cand
                    break
                cand -= 1
            if display_row is not None:
                auto_ok = True

    if auto_ok:
        # group_banner_row: solo PTD. Walk up desde display_row - 1; banner
        # tiene Title Case strings pero menos densamente que display_row.
        group_banner_row: int | None = None
        if schema == "ptd":
            for r in range(display_row - 1, 1, -1):  # r >= 2: skip row 1 settings/banner
                non_empty = 0
                title_count = 0
                for c in range(1, 30):
                    v = _at(r, c)
                    if isinstance(v, str) and v.strip():
                        non_empty += 1
                        if _looks_like_display_label(v):
                            title_count += 1
                if title_count >= 1 and non_empty <= 15:
                    group_banner_row = r
                    break

        return {
            "display_row": display_row,
            "field_id_row": field_id_row,
            "data_start_row": field_id_row + 1,
            "group_banner_row": group_banner_row,
            "detection_method": "auto",
        }

    # Fallback
    if schema not in _TEMPLATE_HEADER_FALLBACK:
        raise ValueError(f"Schema desconocido {schema!r} sin fallback definido")
    fb = _TEMPLATE_HEADER_FALLBACK[schema]
    return {**fb, "detection_method": "fallback"}


def _extract_template_rows(
    wb,
    headers: dict[str, int | None],
) -> tuple[list[dict[str, str]], list[str]]:
    """Extrae rows de data de la hoja 'Template' como dicts {field_id: value}.

    Lee la hoja 'Template' entre headers['data_start_row'] y ws.max_row,
    filtra rows internas/banners/placeholders, y devuelve cada row de data
    real como dict sparse {field_id: value_str}. Una row por SKU real del
    cliente. _parse_data_definitions(wb) se llama UNA VEZ para validar
    fields Required vacíos.

    Filtrado de rows (D1, defensivo en B5-b — NO refactor del legacy
    _is_amazon_internal_row). Una row se descarta si CUALQUIERA:
      (a) _is_amazon_internal_row(row_as_list) retorna True.
      (b) Banner PTD: col 1 es string que empieza con emoji unicode
          (codepoint >= 0x2600) Y cols 2+ todas vacías. Detectado
          empíricamente 2026-05-20: row 7 PTD COAT__5_.xlsm =
          ["      ✅ We've prefilled a", '', '', '', ''].
      (c) Placeholder esparso: cells no vacías < 3 en las primeras 10
          cols. Detectado empíricamente: row 8 PTD = ['', 'COAT', '', '', ''].
      (d) Row completamente vacía → skip silencioso (no warning).
      (e) Placeholder PTD Amazon: "(Default)" string en alguna de las
          primeras 10 cols. Valid value contractual del dropdown Amazon
          para field ::record_action ("(Default) Create or Replace" /
          "(Default) Patch"). Empírico discovery 2026-05-20: row 6 PTD
          COAT__5_.xlsm = ['ABC123', 'SHIRT', '(Default) Create or Replace', ...].
          Nota: _AMAZON_EXAMPLE_TYPES (constante L797) NO se usa aquí
          porque colisiona con feed_product_type/product_type legítimos
          (caso real: cliente Gamboa coat). Si Amazon introduce nuevos
          placeholder markers no-default en el futuro, agregar señales
          adicionales por discovery, no por especulación.

    Validación Required (D3, igualdad exacta — NO `in`):
      Para cada row no filtrada y cada field_id en field_id_row,
      `dd.get(fid, {}).get('required', '').strip().lower() == 'required'`.
      Si la cell está vacía → 1 warning por (field_id, row).

      Fields con required='Conditionally Required' / 'Optional' /
      'Recommended' / 'Preferred' NO disparan warning. Limitación conocida
      v1: 'Conditionally Required' es deuda futura (discovery 2026-05-20:
      PTD tiene 78 fields con ese estado).

    Si headers['detection_method'] == 'fallback', el primer warning de la
    list es informativo sobre el riesgo del fallback (puede haber
    desalineación si la hoja Template cambió estructura).

    Args:
        wb: openpyxl Workbook abierto (caller-managed lifecycle, NO se cierra).
        headers: output de _locate_template_headers(wb). Keys leídas:
                 'field_id_row', 'data_start_row', 'detection_method'.

    Returns:
        (rows, warnings):
        - rows: list de dicts SPARSE. Cada dict tiene como keys los
          field_ids no vacíos del field_id_row; valores son str (cells
          vacías → ""). Una entry por data row real (post-filtrado).
        - warnings: list[str] por Required field vacío.

    Notes:
        Conversión de tipos de cell value:
        - None → ""
        - str → v.strip()
        - int / float / datetime / Decimal → str(v) raw (sin format)

        El helper retorna dict[str, str] por contrato. Formateo
        específico (ISO 8601 para datetimes, fixed precision para
        Decimals) queda como responsabilidad del caller (B6 UI o
        exporter futuro). No invocar isoformat() ni format spec acá
        para mantener el contrato str estable.

    Raises:
        KeyError si la hoja 'Template' no existe en wb.
    """
    ws = wb["Template"]
    fid_row_1idx = headers["field_id_row"]
    data_start_1idx = headers["data_start_row"]

    # Cargar todas las rows una sola vez (soporta read_only mode).
    all_rows = list(ws.iter_rows(values_only=True))

    # field_ids del field_id_row (1-indexed). Cells sin valor → "" → se
    # excluyen del dict resultado.
    field_ids: list[str] = []
    if 0 < fid_row_1idx <= len(all_rows):
        for v in all_rows[fid_row_1idx - 1]:
            if v is None:
                field_ids.append("")
            else:
                s = str(v).strip()
                field_ids.append(s if s else "")

    # F1 mitigación (audit dcfdc9d): warning explícito si el field_id_row
    # quedó vacío o sin field_ids válidos. Previene fail-silent cuando
    # _locate_template_headers retorna un row corrupto (ej. fallback con
    # schema no documentado todavía). Sin esto, el helper procedería con
    # field_ids=[] → rows=[{}, ...] silencioso.
    non_empty_fids = sum(1 for f in field_ids if f)
    if non_empty_fids == 0:
        warnings: list[str] = [
            f"field_id_row {fid_row_1idx} sin field_ids válidos — "
            f"no se puede extraer data. Verificar headers o schema."
        ]
        return [], warnings

    # Parse Data Definitions UNA VEZ (no por row).
    dd = _parse_data_definitions(wb)

    warnings: list[str] = []

    # Warning informativo si detection fallback.
    if headers.get("detection_method") == "fallback":
        schema = _detect_schema(wb)
        warnings.append(
            f"header detection fallback activo (schema={schema}), "
            f"validación Required puede tener desalineación si la hoja "
            f"Template cambió estructura"
        )

    rows: list[dict[str, str]] = []

    for r_idx in range(data_start_1idx, len(all_rows) + 1):
        row_values = list(all_rows[r_idx - 1])

        # (d) Row completamente vacía → skip silencioso.
        non_empty_count = sum(
            1 for v in row_values
            if v is not None and str(v).strip() != ""
        )
        if non_empty_count == 0:
            continue

        # (a) Filtro Amazon internal row (legacy helper).
        if _is_amazon_internal_row(row_values):
            continue

        # (b) Banner PTD: col 1 string que empieza con emoji unicode
        # (codepoint >= 0x2600) Y cols 2+ todas vacías.
        if row_values:
            first_cell = row_values[0]
            if isinstance(first_cell, str):
                first_str = first_cell.strip()
                if first_str and ord(first_str[0]) >= 0x2600:
                    rest_empty = all(
                        v is None or str(v).strip() == ""
                        for v in row_values[1:]
                    )
                    if rest_empty:
                        continue

        # (c) Placeholder esparso: <3 cells no vacías en las primeras 10 cols.
        first_10 = row_values[:10]
        non_empty_first_10 = sum(
            1 for v in first_10
            if v is not None and str(v).strip() != ""
        )
        if non_empty_first_10 < 3:
            continue

        # Filtro (e) — Placeholder row PTD Amazon.
        # Señal: "(Default)" string en alguna cell de las primeras 10 cols.
        # Justificación: "(Default) Create or Replace" / "(Default) Patch"
        # son valid values contractuales del dropdown Amazon para el field
        # ::record_action. Aparecen literal en rows placeholder del template
        # PTD (ej. row 6 COAT__5_.xlsm = ['ABC123', 'SHIRT',
        # '(Default) Create or Replace', ...]) y NUNCA en data real de
        # cliente. Discovery 2026-05-20.
        #
        # Nota: NO chequear _AMAZON_EXAMPLE_TYPES en data rows: la constante
        # contiene categorías ("COAT", "SHIRT", "DRESS", etc.) que colisionan
        # con feed_product_type/product_type legítimos del cliente.
        first_10_str = [
            str(c).strip() if c is not None else ""
            for c in row_values[:10]
        ]
        if any("(Default)" in c for c in first_10_str):
            continue

        # Construir row_dict sparse: una key por field_id no vacío.
        row_dict: dict[str, str] = {}
        for c_idx, fid in enumerate(field_ids):
            if not fid:
                continue
            v = row_values[c_idx] if c_idx < len(row_values) else None
            if v is None:
                row_dict[fid] = ""
            elif isinstance(v, str):
                row_dict[fid] = v.strip()
            else:
                # int/float/date → str(v) sin strip (preservar valor numérico).
                row_dict[fid] = str(v)

        # Validación Required (igualdad exacta).
        for fid, val in row_dict.items():
            required_val = dd.get(fid, {}).get("required", "").strip().lower()
            if required_val == "required" and val == "":
                warnings.append(
                    f"Required field '{fid}' vacío en row {r_idx}"
                )

        rows.append(row_dict)

    return rows, warnings


def _extract_old_rows(
    wb,
    headers: dict[str, int | None],
    dd: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict]]:
    """Extrae rows de data del Template old + valida Required (B5-b).

    Helper del flujo cross-schema OLD→NEW. A diferencia de
    _extract_template_rows() (que aplica filtrado defensivo de banners y
    placeholders Amazon sobre el Template NEW), este helper procesa el
    Template del OLD file con un end-of-data guard simple (2 blank rows
    consecutivas → break) y emite diagnósticos estructurados (dicts), no
    strings.

    El caller debe haber invocado _parse_data_definitions(wb) UNA VEZ y
    pasarlo como argumento `dd` (evita re-parse por row).

    Args:
        wb: openpyxl Workbook abierto (caller-managed lifecycle).
        headers: output de _locate_template_headers(wb). Usa keys
            'field_id_row' (1-indexed) y 'data_start_row' (1-indexed).
        dd: output de _parse_data_definitions(wb). Usa key 'required' por
            field para validación. Si la schema OLD no tiene columna
            Required (caso fptcustom), todos los fields salen con
            required="" → NUNCA emite warning (el filtro
            `.lower() in {"yes", "required"}` lo cubre naturalmente).

    Returns:
        Tupla (rows, diagnostics):
        - rows: list[dict[field_id, value_str]]. Una entrada por row real
          de data (post end-of-data guard). Cells None → "". Cells no-str
          (datetime, Decimal, int, float) → str(v).strip(). Sparse: sólo
          incluye keys cuyas cols del field_id_row tenían field_id no
          vacío.
        - diagnostics: list[dict] con shape {row_index, level, field,
          code, message}. row_index es 1-indexed real del Template
          (data_start_row + offset). Si field_id_row no tiene field_ids
          útiles → retorna ([], [{level:"error", code:"no_field_ids", ...}])
          en vez de raisear.

    Raises:
        KeyError si la hoja 'Template' no existe en wb.
        ValueError si headers['field_id_row'] o headers['data_start_row']
            es None (defensa contra B5-a corrupto; en práctica no debería
            ocurrir porque _locate_template_headers cae a fallback antes).
    """
    field_id_row = headers.get("field_id_row")
    data_start_row = headers.get("data_start_row")
    if field_id_row is None or data_start_row is None:
        raise ValueError(
            f"headers requiere field_id_row y data_start_row no-None "
            f"(got field_id_row={field_id_row!r}, "
            f"data_start_row={data_start_row!r})"
        )

    ws = wb["Template"]

    # Paso 1: mapear col_idx (0-based) → field_id desde field_id_row.
    field_id_row_cells = next(
        ws.iter_rows(
            min_row=field_id_row,
            max_row=field_id_row,
            values_only=True,
        ),
        None,
    )

    # P1-2: distinguir row inexistente (None) de row sin field_ids ([]).
    # Si next() devolvió None, field_id_row está fuera de ws.max_row.
    if field_id_row_cells is None:
        return [], [{
            "row_index": field_id_row,
            "level": "error",
            "field": "",
            "code": "field_id_row_out_of_range",
            "message": (
                f"field_id_row={field_id_row} excede ws.max_row del sheet "
                f"'Template' — header locator devolvió row inexistente"
            ),
        }]

    col_to_fid: dict[int, str] = {}
    if field_id_row_cells:
        for c_idx, v in enumerate(field_id_row_cells):
            if v is None:
                continue
            s = str(v).strip()
            if s:
                col_to_fid[c_idx] = s

    if not col_to_fid:
        return [], [{
            "row_index": field_id_row,
            "level": "error",
            "field": "",
            "code": "no_field_ids",
            "message": (
                f"field_id_row {field_id_row} sin field_ids útiles — "
                f"no se puede extraer data del Template old"
            ),
        }]

    # Pasos 2-4: iterar rows de data con end-of-data guard + validación.
    rows: list[dict[str, str]] = []
    diagnostics: list[dict] = []
    blank_streak = 0

    for offset, row_values in enumerate(
        ws.iter_rows(min_row=data_start_row, values_only=True)
    ):
        # Normalizar cells: None → "", no-str → str(v).strip().
        normalized: list[str] = []
        for v in row_values:
            if v is None:
                normalized.append("")
            elif isinstance(v, str):
                normalized.append(v.strip())
            else:
                normalized.append(str(v).strip())

        # End-of-data guard: 2 blank rows consecutivas → break.
        # P2-3: emit diagnostic informativo al activar guard (observabilidad).
        if all(s == "" for s in normalized):
            blank_streak += 1
            if blank_streak >= 2:
                diagnostics.append({
                    "row_index": data_start_row + offset,
                    "level": "info",
                    "field": "",
                    "code": "end_of_data_reached",
                    "message": (
                        f"end-of-data guard activado en row "
                        f"{data_start_row + offset} tras 2 blank rows "
                        f"consecutivas — extracción detenida"
                    ),
                })
                break
            continue
        blank_streak = 0

        # Construir row_dict por col_to_fid (sparse).
        row_dict: dict[str, str] = {}
        for c_idx, fid in col_to_fid.items():
            if c_idx < len(normalized):
                row_dict[fid] = normalized[c_idx]
            else:
                row_dict[fid] = ""

        # Validación Required (row_index 1-indexed real del Template).
        row_index_1idx = data_start_row + offset
        for fid, value in row_dict.items():
            required_val = (
                dd.get(fid, {}).get("required", "").strip().lower()
            )
            if required_val in {"yes", "required"} and value == "":
                diagnostics.append({
                    "row_index": row_index_1idx,
                    "level": "warning",
                    "field": fid,
                    "code": "missing_required_in_old",
                    "message": (
                        f"Required field {fid!r} vacío en row {row_index_1idx}"
                    ),
                })

        rows.append(row_dict)

    return rows, diagnostics


def _migrate_row(
    old_row: dict[str, str],
    field_map: dict[str, str],
    value_map: dict[str, dict[str, str | None]],
    old_dd: dict[str, dict[str, str]],
    new_dd: dict[str, dict[str, str]],
) -> tuple[dict[str, str], list[dict]]:
    """Migra una row OLD a row NEW aplicando field_map + value_map (B5-c).

    Toma una row del output de _extract_old_rows() (B5-b) y la traduce al
    schema NEW usando:
    - field_map (B3): {old_field: new_field} — qué columna del NEW recibe
      cada valor del OLD.
    - value_map (B4b): {old_label: {old_value: new_value_or_None}} — para
      enums cross-schema, qué valor NEW corresponde a cada valor OLD.
    - _DEPRECATED_OLD_ENUMS: enums OLD sin contraparte en PTD.

    No filtra placeholders ni banners (a diferencia de _extract_template_rows
    sobre el NEW); confía en que el caller ya filtró si era necesario.

    5 diagnostic codes emitidos:
    - "unmapped_field": old_field no está en field_map (data se pierde).
    - "deprecated_enum_no_target": old_label en _DEPRECATED_OLD_ENUMS
      (Relationship Type, Variation Theme) → revisión manual.
    - "deprecated_value": value mapea a None en value_map (ej. ISBN/GCID
      en Product ID Type) → revisión manual.
    - "unknown_enum_value": value no está en value_map[old_label] →
      pasthrough crudo al NEW (decisión: preservar data > silenciar).
    - "missing_required_in_new": new_field es Required en PTD pero no se
      migró valor.

    Args:
        old_row: una entrada de _extract_old_rows()[0]. Dict
            {old_field_id: value_str}. Cells vacías ya vienen como "".
        field_map: output de _build_field_map(old_dd, new_dd)[0]. Sólo
            entries con match cross-schema.
        value_map: output de _build_value_map(old_vv, new_vv)[0]. Dict de
            enum translators con shape {old_label: {old_val: new_val|None}}.
        old_dd: output de _parse_data_definitions(old_wb). Para resolver
            old_label por field (índice del value_map).
        new_dd: output de _parse_data_definitions(new_wb). Para validar
            Required en el schema NEW post-migración.

    Returns:
        Tupla (new_row, diagnostics):
        - new_row: dict {new_field_id: value_str}. Sparse: sólo incluye
          fields que recibieron valor. Fields NEW no escritos quedan
          implícitamente vacíos (caller los rellena con "" al armar el
          output Excel).
        - diagnostics: list[dict] con shape {level, field, code, message}.
          NO incluye row_index — el caller lo agrega cuando ensambla el
          batch (B5-b ya devuelve row_index por separado).
    """
    new_row: dict[str, str] = {}
    diagnostics: list[dict] = []

    # P1-1: early-exit si field_map vacío (evita ~N warnings ruidosos
    # unmapped_field si B3 no encontró matches). Diagnostic único informa
    # la causa raíz.
    if not field_map:
        diagnostics.append({
            "level": "error",
            "field": "",
            "code": "empty_field_map",
            "message": (
                "field_map vacío — _build_field_map no encontró matches "
                "cross-schema. Imposible migrar ninguna row."
            ),
        })
        return new_row, diagnostics

    # Paso 1: migración field-by-field.
    for old_field, value in old_row.items():
        # Skip vacíos sin diagnostic.
        if value == "":
            continue

        # Unmapped field.
        if old_field not in field_map:
            diagnostics.append({
                "level": "warning",
                "field": old_field,
                "code": "unmapped_field",
                "message": (
                    f"old field {old_field!r} sin correspondencia en new "
                    f"schema — data se pierde"
                ),
            })
            continue

        new_field = field_map[old_field]
        old_label = old_dd.get(old_field, {}).get("label", "")

        # (a) Deprecated enum sin target (Relationship Type, Variation Theme).
        if old_label in _DEPRECATED_OLD_ENUMS:
            diagnostics.append({
                "level": "warning",
                "field": old_field,
                "code": "deprecated_enum_no_target",
                "message": (
                    f"old field {old_field!r} (label={old_label!r}) es un "
                    f"enum deprecated en PTD — value {value!r} requiere "
                    f"revisión manual"
                ),
            })
            continue  # NO escribir en new_row

        # (b) Enum cross-schema con mapping.
        if old_label in value_map:
            old_to_new = value_map[old_label]
            if value in old_to_new:
                new_val = old_to_new[value]
                if new_val is None:
                    diagnostics.append({
                        "level": "warning",
                        "field": old_field,
                        "code": "deprecated_value",
                        "message": (
                            f"old value {value!r} en field {old_field!r} "
                            f"mapea a None (deprecated) — requiere revisión "
                            f"manual"
                        ),
                    })
                    # NO escribir en new_row
                else:
                    new_row[new_field] = new_val
            else:
                # Pasthrough con flag (decisión: preservar data > silenciar).
                diagnostics.append({
                    "level": "warning",
                    "field": old_field,
                    "code": "unknown_enum_value",
                    "message": (
                        f"old value {value!r} en field {old_field!r} "
                        f"(label={old_label!r}) no está en _ENUM_VALUE_MAP — "
                        f"pasthrough crudo a new schema"
                    ),
                })
                new_row[new_field] = value
            continue

        # (c) Pasthrough no-enum.
        new_row[new_field] = value

    # Paso 2: validación Required del NEW schema.
    for new_field, info in new_dd.items():
        required_val = info.get("required", "").strip().lower()
        if required_val not in {"yes", "required"}:
            continue
        if new_row.get(new_field, "") == "":
            diagnostics.append({
                "level": "warning",
                "field": new_field,
                "code": "missing_required_in_new",
                "message": (
                    f"new field {new_field!r} es Required en PTD pero no se "
                    f"migró valor (no había old_field mapeado o value vacío)"
                ),
            })

    return new_row, diagnostics


def _cell_value_or_blank(ws, row_idx_0: int, col_idx_0: int):
    """Devuelve el valor de la celda en posición 0-indexed, '' si vacía. Equivalente a sheet[encode_cell({r,c})]."""
    cell = ws.cell(row=row_idx_0 + 1, column=col_idx_0 + 1)
    val = cell.value
    return val if val is not None else ""


def _ws_max_row_col(ws) -> tuple[int, int]:
    """Devuelve (max_row, max_col) en 1-indexed. Equivalente a XLSX.utils.decode_range(sheet['!ref']).e."""
    return ws.max_row or 1, ws.max_column or 1


def _detect_header_row(ws) -> int:
    """
    Detecta el header row escaneando las primeras 11 rows (0-indexed result).
    Replicado de detectHeaderRow() del HTML L754-794.
    Estrategia: row con más celdas no vacías + alguna keyword típica de Amazon header.
    Si ninguna row tiene typical headers, fallback a row con más celdas no vacías.
    """
    max_row, max_col = _ws_max_row_col(ws)
    end_row_0 = min(10, max_row - 1)  # primeras 11 rows max

    best_row = 0
    best_count = 0

    for r in range(0, end_row_0 + 1):
        count = 0
        has_typical_header = False
        for c in range(max_col):
            val = _cell_value_or_blank(ws, r, c)
            sval = str(val).strip()
            if sval == "":
                continue
            count += 1
            if sval.lower() in _HEADER_KEYWORDS:
                has_typical_header = True
        if has_typical_header and count > best_count:
            best_count = count
            best_row = r

    if best_count == 0:
        # Fallback: row con más celdas no vacías
        for r in range(0, end_row_0 + 1):
            count = 0
            for c in range(max_col):
                val = _cell_value_or_blank(ws, r, c)
                if str(val).strip() != "":
                    count += 1
            if count > best_count:
                best_count = count
                best_row = r

    return best_row


def _get_headers(ws, header_row_0: int) -> list[str]:
    """Extrae headers de una row 0-indexed. Replica getHeaders() del HTML."""
    _, max_col = _ws_max_row_col(ws)
    headers: list[str] = []
    for c in range(max_col):
        val = _cell_value_or_blank(ws, header_row_0, c)
        headers.append(str(val).strip() if val != "" else "")
    return headers


def _is_amazon_internal_row(row: list) -> bool:
    """
    Detecta filas internas Amazon a filtrar.
    Replicado de isAmazonInternalRow() del HTML L806-817.
    """
    sample = [v for v in row if v is not None and str(v).strip() != ""]
    if len(sample) == 0:
        return True

    s = " ".join(str(v) for v in sample)
    if re.search(r"marketplace_id=", s):
        return True
    if re.search(r"amzn1\.volt\.", s):
        return True
    if re.search(r"#\d+\.value", s):
        return True
    if re.search(r"\[language_tag=", s):
        return True

    first_val = str(sample[0]).strip()
    if first_val in _AMAZON_EXAMPLE_TYPES:
        # Detección extra: 2+ valores con ", " (ejemplo de Amazon)
        with_comma = sum(1 for v in sample if ", " in str(v))
        if with_comma >= 2:
            return True

    return False


def _get_data_rows(ws, header_row_0: int) -> tuple[list[list], int]:
    """
    Lee data rows desde header_row_0 + 1 hasta el final.
    Salta vacías y filas internas Amazon. Devuelve (rows, skipped_internal).
    Replicado de getDataRows() del HTML L819-836.
    """
    max_row, max_col = _ws_max_row_col(ws)
    rows: list[list] = []
    skipped_internal = 0

    for r in range(header_row_0 + 1, max_row):
        row = []
        has_data = False
        for c in range(max_col):
            val = _cell_value_or_blank(ws, r, c)
            row.append(val if val != "" else "")
            if val != "" and str(val).strip() != "":
                has_data = True
        if not has_data:
            continue
        if _is_amazon_internal_row(row):
            skipped_internal += 1
            continue
        rows.append(row)

    return rows, skipped_internal


def _detect_file_type(ws) -> dict:
    """
    Clasifica el archivo como 'Flat File' o 'Category Listing'.
    Replicado de detectFileType() del HTML L838-867.
    """
    max_row, max_col = _ws_max_row_col(ws)
    header_row = _detect_header_row(ws)
    field_id_row = header_row + 1

    has_field_ids = False
    field_id_format = "simple"

    end_col = min(15, max_col - 1)
    for c in range(end_col + 1):
        val = _cell_value_or_blank(ws, field_id_row, c)
        if val == "":
            continue
        sval = str(val).strip()
        if re.search(r"[a-z_]{3,}", sval):
            has_field_ids = True
        if (re.search(r"marketplace_id=", sval)
                or re.search(r"\[language_tag=", sval)
                or re.search(r"contribution_sku", sval)):
            field_id_format = "qualified"

    col_count = 0
    for c in range(max_col):
        val = _cell_value_or_blank(ws, header_row, c)
        if val != "" and str(val).strip() != "":
            col_count += 1

    data_start = header_row + (2 if has_field_ids else 1)
    data_rows = 0
    for r in range(data_start, max_row):
        hd = False
        end_c = min(5, max_col - 1)
        for c in range(end_c + 1):
            val = _cell_value_or_blank(ws, r, c)
            if val != "" and str(val).strip() != "":
                hd = True
                break
        if hd:
            data_rows += 1

    is_cl = (field_id_format == "qualified") or (header_row >= 3)
    return {
        "type": "Category Listing" if is_cl else "Flat File",
        "type_class": "cat-listing" if is_cl else "flat-file",
        "header_row": header_row + 1,  # 1-indexed para mostrar al usuario
        "field_id_row": field_id_row + 1 if has_field_ids else None,
        "col_count": col_count,
        "data_rows": data_rows,
        "has_field_ids": has_field_ids,
    }


def _normalize_field_id(fid: str) -> dict:
    """
    Normaliza un field ID eliminando brackets, hash, sufijos numéricos.
    Replicado de normalizeFieldId() del HTML L869-879.
    """
    if not fid:
        return {"base": "", "num": None}

    base = re.sub(r"\[.*?\]", "", fid)
    hash_match = re.search(r"#(\d+)", base)
    hash_num = int(hash_match.group(1)) if hash_match else None

    base = re.sub(r"#\d+\.\w+$", "", base)
    base = re.sub(r"#\d*$", "", base)

    suffix_match = re.match(r"^(.+?)(\d+)$", base)
    suffix_num = int(suffix_match.group(2)) if suffix_match else None
    base_name = re.sub(r"_$", "", suffix_match.group(1)) if suffix_match else base

    return {
        "base": base_name.lower(),
        "num": hash_num if hash_num is not None else suffix_num,
    }


def _looks_like_field_ids(ids: list[str]) -> bool:
    """
    Heurística: la fila tiene field_ids si los primeros 10 valores no vacíos
    tienen formato a-z_#\\d[].:= y al menos uno tiene 3+ letras lowercase.
    Replicado de looksLikeFieldIds() del HTML L1005.
    """
    non_empty = [v for v in ids if v]
    if not non_empty:
        return False
    sample_first10 = " ".join(non_empty[:10])
    sample = " ".join(non_empty)
    return (
        bool(re.match(r"^[a-z_#\d\[\]\.:=\s]+$", sample_first10, re.IGNORECASE))
        and bool(re.search(r"[a-z_]{3,}", sample))
    )


def _norm_header(s: str) -> str:
    """Normaliza header: lowercase + sin spaces/underscores/dashes."""
    return re.sub(r"[\s_\-]+", "", s.lower())


# ── Matching de columnas (5 estrategias en orden de prioridad) ──────────

def _match_columns(
    old_field_ids: list[str],
    new_field_ids: list[str],
    old_headers: list[str],
    new_headers: list[str],
    has_old_fids: bool,
    has_new_fids: bool,
) -> dict:
    """
    Aplica las 5 estrategias de matching. Devuelve dict con:
    - mapping: {ni: oi} — index del new column → index del old column
    - methods: {ni: 'exact'|'normalized'|'alias'|'base'|'header'}
    - matched: list[str] — columnas migradas (display names)
    - not_in_new: list[str] — columnas del old no encontradas en el new
    - only_in_new: list[str] — columnas del new sin equivalente en el old

    Replicado del bloque btnMigrate.click del HTML L990-1056.
    """
    mapping: dict[int, int] = {}
    methods: dict[int, str] = {}
    matched: list[str] = []
    not_in_new: list[str] = []
    only_in_new: list[str] = []

    if has_old_fids and has_new_fids:
        new_exact: dict[str, int] = {}
        new_by_norm: dict[str, int] = {}
        new_by_base: dict[str, int] = {}

        for ni, fid in enumerate(new_field_ids):
            if not fid:
                continue
            new_exact.setdefault(fid.lower(), ni)
            n = _normalize_field_id(fid)
            nk = n["base"] + "|" + (str(n["num"]) if n["num"] is not None else "")
            new_by_norm.setdefault(nk, ni)
            new_by_base.setdefault(n["base"], ni)

        claimed_new: set[int] = set()
        matched_old: set[int] = set()

        # Strategy 1: Exact
        for oi, fid in enumerate(old_field_ids):
            if not fid:
                continue
            ni = new_exact.get(fid.lower())
            if ni is not None and ni not in claimed_new:
                mapping[ni] = oi
                methods[ni] = "exact"
                claimed_new.add(ni)
                matched_old.add(oi)

        # Strategy 2: Normalized
        for oi, fid in enumerate(old_field_ids):
            if not fid or oi in matched_old:
                continue
            n = _normalize_field_id(fid)
            key = n["base"] + "|" + (str(n["num"]) if n["num"] is not None else "")
            ni = new_by_norm.get(key)
            if ni is not None and ni not in claimed_new:
                mapping[ni] = oi
                methods[ni] = "normalized"
                claimed_new.add(ni)
                matched_old.add(oi)

        # Strategy 3: Aliases
        for oi, fid in enumerate(old_field_ids):
            if not fid or oi in matched_old:
                continue
            n = _normalize_field_id(fid)
            alias_list = _ALIASES.get(n["base"], [])
            for alias in alias_list:
                key = alias + "|" + (str(n["num"]) if n["num"] is not None else "")
                ni = new_by_norm.get(key)
                if ni is not None and ni not in claimed_new:
                    mapping[ni] = oi
                    methods[ni] = "alias"
                    claimed_new.add(ni)
                    matched_old.add(oi)
                    break
                ni = new_by_base.get(alias)
                if ni is not None and ni not in claimed_new:
                    mapping[ni] = oi
                    methods[ni] = "alias"
                    claimed_new.add(ni)
                    matched_old.add(oi)
                    break

        # Strategy 4: Base only
        for oi, fid in enumerate(old_field_ids):
            if not fid or oi in matched_old:
                continue
            n = _normalize_field_id(fid)
            ni = new_by_base.get(n["base"])
            if ni is not None and ni not in claimed_new:
                mapping[ni] = oi
                methods[ni] = "base"
                claimed_new.add(ni)
                matched_old.add(oi)

        # Strategy 5: Header
        nh_lookup: dict[str, int] = {}
        for ni, h in enumerate(new_headers):
            if not h or ni in claimed_new:
                continue
            k = _norm_header(h)
            nh_lookup.setdefault(k, ni)
        for oi, h in enumerate(old_headers):
            if not h or oi in matched_old:
                continue
            k = _norm_header(h)
            ni = nh_lookup.get(k)
            if ni is not None and ni not in claimed_new:
                mapping[ni] = oi
                methods[ni] = "header"
                claimed_new.add(ni)
                matched_old.add(oi)
                # Eliminar de nh_lookup para evitar que otra old reclame el mismo new
                del nh_lookup[k]

        # Construir listas de display
        for ni, fid in enumerate(new_field_ids):
            if not fid and not new_headers[ni]:
                continue
            display = new_headers[ni] or fid
            if ni in mapping:
                matched.append(display)
            else:
                only_in_new.append(display)
        for oi, fid in enumerate(old_field_ids):
            if not fid and not old_headers[oi]:
                continue
            display = old_headers[oi] or fid
            if oi not in matched_old:
                not_in_new.append(display)
    else:
        # Fallback: matching solo por headers normalizados
        old_norm = [_norm_header(h) for h in old_headers]
        new_norm = [_norm_header(h) for h in new_headers]
        for ni, nh in enumerate(new_headers):
            if not nh:
                continue
            try:
                oi = old_norm.index(new_norm[ni])
            except ValueError:
                oi = -1
            if oi != -1 and old_headers[oi]:
                mapping[ni] = oi
                methods[ni] = "header"
                matched.append(nh)
            else:
                only_in_new.append(nh)
        for oi, oh in enumerate(old_headers):
            if not oh:
                continue
            if _norm_header(oh) not in new_norm:
                not_in_new.append(oh)

    return {
        "mapping": mapping,
        "methods": methods,
        "matched": matched,
        "not_in_new": not_in_new,
        "only_in_new": only_in_new,
    }


# ── Workbook parser (cached) ────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _parse_workbook(file_bytes: bytes, file_name: str, sheet_names: tuple[str, ...]) -> dict:
    """
    Parsea un workbook (xlsx/xls/xlsm). Busca el sheet correcto y devuelve
    su contenido + metadata de detección. Cacheado por bytes hash.
    """
    bio = io.BytesIO(file_bytes)
    # data_only=True devuelve valores calculados de fórmulas
    wb = load_workbook(bio, data_only=True, read_only=False)

    # Buscar sheet: 1) match exacto lowercase, 2) contains, 3) primer sheet
    sheet_name = None
    available = wb.sheetnames

    for name in sheet_names:
        for s in available:
            if s.lower().strip() == name.lower():
                sheet_name = s
                break
        if sheet_name:
            break

    if not sheet_name:
        for name in sheet_names:
            for s in available:
                if name.lower() in s.lower():
                    sheet_name = s
                    break
            if sheet_name:
                break

    if not sheet_name:
        sheet_name = available[0] if available else None

    if not sheet_name:
        raise ValueError("El archivo no tiene hojas válidas")

    ws = wb[sheet_name]
    detection = _detect_file_type(ws)
    expected_found = any(s.lower() == sheet_name.lower() for s in sheet_names)

    return {
        "sheet_name": sheet_name,
        "available_sheets": available,
        "expected_found": expected_found,
        "detection": detection,
        "file_name": file_name,
        "wb_bytes": file_bytes,  # Para volver a abrir en migración (cache hit ok)
    }


def _open_ws(parsed: dict):
    """Reabre el workbook desde bytes y devuelve el worksheet seleccionado."""
    bio = io.BytesIO(parsed["wb_bytes"])
    wb = load_workbook(bio, data_only=True, read_only=False)
    return wb[parsed["sheet_name"]], wb


# ── TSV/XLSX builders (fuera de render()) ───────────────────────────────

def _build_migrated_xlsx(output_rows: list[list], sheet_name: str) -> bytes:
    """Construye un .xlsx con las output rows. Devuelve bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_name or "Template")[:31]  # max 31 chars Excel
    for row in output_rows:
        # Convertir a tipos compatibles openpyxl (str/int/float/None)
        clean_row = []
        for v in row:
            if v == "" or v is None:
                clean_row.append(None)
            else:
                clean_row.append(v)
        ws.append(clean_row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.read()


def _build_migrated_tsv(output_rows: list[list]) -> bytes:
    """
    Construye TSV con BOM UTF-8.
    Replica `XLSX.utils.sheet_to_csv(sheet, {FS:'\\t'})` con BOM como en HTML L1124.
    """
    lines = []
    for row in output_rows:
        cells = []
        for v in row:
            if v == "" or v is None:
                cells.append("")
            else:
                # Reemplazar tabs y newlines en valores para que no rompan el TSV
                s = str(v).replace("\t", " ").replace("\n", " ").replace("\r", "")
                cells.append(s)
        lines.append("\t".join(cells))
    text = "\n".join(lines)
    return ("﻿" + text).encode("utf-8")


# ── Migration core (orchestración) ──────────────────────────────────────

def _run_migration(
    old_parsed: dict,
    new_parsed: dict,
    user_old_header_row_1: int,
    user_new_header_row_1: int,
    skip_example: bool,
) -> dict:
    """
    Ejecuta la migración completa.
    Replica el handler btnMigrate.click del HTML L990-1100.
    Devuelve dict con: stats, output_rows, sheet_name, methods_count,
    matched, not_in_new, only_in_new, dropped_example, skipped_internal, data_rows_count.
    """
    old_ws, _ = _open_ws(old_parsed)
    new_ws, _ = _open_ws(new_parsed)

    auto_old = _detect_header_row(old_ws)
    auto_new = _detect_header_row(new_ws)

    # Lógica original del HTML L997-998:
    # si user_value == 1 AND auto_value > 0 → usar auto_value
    # si user_value valido (>=0) → usar user_value (1-indexed → 0-indexed)
    user_old_0 = user_old_header_row_1 - 1
    user_new_0 = user_new_header_row_1 - 1

    if user_old_0 >= 0:
        if user_old_header_row_1 == 1 and auto_old > 0:
            old_header_row = auto_old
        else:
            old_header_row = user_old_0
    else:
        old_header_row = auto_old

    if user_new_0 >= 0:
        if user_new_header_row_1 == 1 and auto_new > 0:
            new_header_row = auto_new
        else:
            new_header_row = user_new_0
    else:
        new_header_row = auto_new

    old_headers = _get_headers(old_ws, old_header_row)
    new_headers = _get_headers(new_ws, new_header_row)
    old_field_ids = _get_headers(old_ws, old_header_row + 1)
    new_field_ids = _get_headers(new_ws, new_header_row + 1)

    has_old_fids = _looks_like_field_ids(old_field_ids)
    has_new_fids = _looks_like_field_ids(new_field_ids)

    old_data_start = old_header_row + (2 if has_old_fids else 1)
    new_data_start = new_header_row + (2 if has_new_fids else 1)

    old_rows, skipped_internal = _get_data_rows(old_ws, old_data_start - 1)

    match_result = _match_columns(
        old_field_ids, new_field_ids, old_headers, new_headers,
        has_old_fids, has_new_fids,
    )
    mapping = match_result["mapping"]

    # Construir output preservando rows pre-data del new template
    new_max_row, new_max_col = _ws_max_row_col(new_ws)
    output_rows: list[list] = []
    for r in range(0, new_data_start):
        row = []
        for c in range(new_max_col):
            row.append(_cell_value_or_blank(new_ws, r, c))
        output_rows.append(row)

    # Fila vacía separadora (replica HTML L1067)
    output_rows.append([""] * len(new_headers))

    # Skip example row si user lo pidió
    dropped_example = 0
    if skip_example and len(old_rows) > 0:
        old_rows = old_rows[1:]
        dropped_example = 1

    # Mapear cada old row a new row según mapping
    for old_row in old_rows:
        new_row = [""] * len(new_headers)
        for ni, oi in mapping.items():
            if oi < len(old_row):
                val = old_row[oi]
                new_row[ni] = val if val != "" else ""
        output_rows.append(new_row)

    methods_count: dict[str, int] = {}
    for m in match_result["methods"].values():
        methods_count[m] = methods_count.get(m, 0) + 1

    return {
        "output_rows": output_rows,
        "sheet_name": new_parsed["sheet_name"],
        "methods_count": methods_count,
        "matched": match_result["matched"],
        "not_in_new": match_result["not_in_new"],
        "only_in_new": match_result["only_in_new"],
        "dropped_example": dropped_example,
        "skipped_internal": skipped_internal,
        "data_rows_count": len(old_rows),
        "old_header_row_used": old_header_row + 1,
        "new_header_row_used": new_header_row + 1,
        "has_old_fids": has_old_fids,
        "has_new_fids": has_new_fids,
    }


# ── UI helpers ──────────────────────────────────────────────────────────

def _header():
    """Header estándar Account Health con emoji 🏥."""
    st.markdown("## 🏥 Flat File Migrator")
    st.caption(
        "📥 Inputs: Old Flat File · New Flat File (Template) · "
        "5 marketplaces (US · DE · IT · FR · ES)"
    )
    st.divider()


def _empty_state():
    """Empty state Account Health pattern."""
    st.markdown(
        "<div style='border: 2px dashed #FFD9B3; border-radius: 12px; padding: 32px;"
        " text-align: center; background: #FFF8F0;'>"
        "<h3 style='color: #E84000; margin-top: 0;'>📂 Subí los flat files para arrancar</h3>"
        "<p style='color: #6B7280; margin: 0;'>Old File (datos viejos) + New File (template nuevo de Amazon)</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.markdown("**Old Flat File** — flat file viejo con tus datos de productos")
    st.caption("📍 Dónde bajarlo: lo que tengas guardado de tus uploads anteriores a Amazon")
    st.markdown("**New Flat File** — template nuevo descargado de Seller Central")
    st.caption(
        "📍 Dónde bajarlo: Seller Central → Catalog → Add Products via Upload → "
        "Download Template (por categoría)"
    )


def _file_detection_badge(detection: dict, sheet_name: str, expected_found: bool, file_name: str) -> str:
    """Construye HTML de badge con tipo de archivo + sheet detectado + cols/rows."""
    ftype = detection["type"]
    if ftype == "Flat File":
        bg, color = "#FEE2E2", "#B91C1C"  # Naranja/rojo del skill
    else:
        bg, color = "#F0FDF4", "#166534"  # Verde Category Listing
    found_note = "" if expected_found else " <span style='color:#A16207;'>(sheet esperado no encontrado)</span>"
    field_id_note = (
        f" · Field IDs: row {detection['field_id_row']}"
        if detection["has_field_ids"] else ""
    )
    return (
        f"<div style='font-size:0.78rem; line-height:1.5; padding:8px 12px; "
        f"background:#FAFAFA; border-radius:8px; margin-top:8px;'>"
        f"<span style='display:inline-block; padding:2px 8px; border-radius:100px; "
        f"font-family:monospace; font-size:0.7rem; letter-spacing:1px; "
        f"text-transform:uppercase; background:{bg}; color:{color}; "
        f"font-weight:600;'>{ftype}</span><br>"
        f"<span style='color:#6B7280;'>"
        f"📄 {file_name} → \"{sheet_name}\"{found_note}<br>"
        f"Headers: row {detection['header_row']}{field_id_note} · "
        f"{detection['col_count']} cols · {detection['data_rows']} rows</span></div>"
    )


# ── Render por marketplace ──────────────────────────────────────────────

def _render_marketplace(suffix: str, sheet_names: list[str]):
    """Render de la UI para un marketplace específico. Toda la lógica vive acá."""
    k = lambda name: f"ffm_{suffix}_{name}"  # noqa: E731 — key builder local

    # Header config
    cfg_l, cfg_r, cfg_skip = st.columns([1, 1, 2])
    with cfg_l:
        old_header_row = st.number_input(
            "Header row (old file)",
            min_value=1, max_value=20, value=1, step=1,
            key=k("old_header_row"),
            help="1 = auto-detección. Otro valor = forzar esa fila como header.",
        )
    with cfg_r:
        new_header_row = st.number_input(
            "Header row (new file)",
            min_value=1, max_value=20, value=1, step=1,
            key=k("new_header_row"),
            help="1 = auto-detección. Otro valor = forzar esa fila como header.",
        )
    with cfg_skip:
        skip_example = st.checkbox(
            "Saltar primera data row (example row de Amazon)",
            value=True,
            key=k("skip_example"),
        )

    st.markdown("")

    # File uploaders side by side
    col_old, col_new = st.columns(2)

    with col_old:
        st.markdown("**📦 Step 1 — Old Flat File**")
        file_old = st.file_uploader(
            "Old file uploader",
            type=["xlsx", "xls", "xlsm", "tsv", "csv", "txt"],
            key=k("file_old"),
            label_visibility="collapsed",
        )

    with col_new:
        st.markdown("**✨ Step 2 — New Flat File**")
        file_new = st.file_uploader(
            "New file uploader",
            type=["xlsx", "xls", "xlsm", "tsv", "csv", "txt"],
            key=k("file_new"),
            label_visibility="collapsed",
        )

    # Parseo + detección de tipos
    old_parsed = None
    new_parsed = None
    sheet_names_t = tuple(sheet_names)

    if file_old is not None:
        try:
            old_parsed = _parse_workbook(file_old.getvalue(), file_old.name, sheet_names_t)
            with col_old:
                st.markdown(
                    _file_detection_badge(
                        old_parsed["detection"], old_parsed["sheet_name"],
                        old_parsed["expected_found"], file_old.name,
                    ),
                    unsafe_allow_html=True,
                )
        except Exception as e:
            with col_old:
                st.error(f"Error al leer el archivo: {e}")

    if file_new is not None:
        try:
            new_parsed = _parse_workbook(file_new.getvalue(), file_new.name, sheet_names_t)
            with col_new:
                st.markdown(
                    _file_detection_badge(
                        new_parsed["detection"], new_parsed["sheet_name"],
                        new_parsed["expected_found"], file_new.name,
                    ),
                    unsafe_allow_html=True,
                )
        except Exception as e:
            with col_new:
                st.error(f"Error al leer el archivo: {e}")

    st.markdown("")

    # Botón migrar
    can_migrate = old_parsed is not None and new_parsed is not None
    btn_clicked = st.button(
        "Migrar Data →",
        disabled=not can_migrate,
        type="primary",
        key=k("btn_migrate"),
        use_container_width=False,
    )

    # Format select (xlsx/tsv)
    output_format = st.radio(
        "Formato de salida",
        options=["XLSX", "TSV"],
        index=0,
        horizontal=True,
        key=k("format"),
    )

    if not btn_clicked:
        return

    if not can_migrate:
        st.warning("Subí ambos archivos antes de migrar.")
        return

    # Ejecutar migración
    try:
        result = _run_migration(
            old_parsed=old_parsed,
            new_parsed=new_parsed,
            user_old_header_row_1=int(old_header_row),
            user_new_header_row_1=int(new_header_row),
            skip_example=skip_example,
        )
    except Exception as e:
        st.error(f"Error en migración: {e}")
        return

    # Resultados
    st.markdown("### 📊 Resultados de migración")

    matched_n = len(result["matched"])
    only_new_n = len(result["only_in_new"])
    not_in_new_n = len(result["not_in_new"])
    rows_n = result["data_rows_count"]
    skipped = result["skipped_internal"]
    methods_str = ", ".join(f"{m}: {c}" for m, c in result["methods_count"].items()) or "headers"

    # 4 KPIs principales
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Columnas migradas", matched_n), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Solo en nuevo", only_new_n), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("No migradas", not_in_new_n), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Filas migradas", rows_n), unsafe_allow_html=True)

    # KPIs secundarios (skipped + example + match methods)
    extras = []
    if result["dropped_example"] > 0:
        extras.append(("Example row saltada", result["dropped_example"]))
    if skipped > 0:
        extras.append(("Filas Amazon filtradas", skipped))
    extras.append(("Match por método", methods_str))

    if extras:
        cols_extra = st.columns(len(extras))
        for col, (label, val) in zip(cols_extra, extras):
            with col:
                # Para el método: usar valor pequeño (es string largo)
                st.markdown(kpi_card(label, val), unsafe_allow_html=True)

    # Detalle de columnas (collapsable)
    with st.expander("Ver detalle de columnas", expanded=False):
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown(f"**✓ Migradas ({matched_n})**")
            if result["matched"]:
                st.markdown(
                    "<div style='max-height:240px; overflow-y:auto; "
                    "background:#F0FDF4; border:1px solid #86EFAC; "
                    "border-radius:6px; padding:8px; font-family:monospace; "
                    "font-size:0.78rem; color:#166534;'>"
                    + "<br>".join(result["matched"])
                    + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("—")
        with d2:
            st.markdown(f"**✗ No encontradas en nuevo ({not_in_new_n})**")
            if result["not_in_new"]:
                st.markdown(
                    "<div style='max-height:240px; overflow-y:auto; "
                    "background:#FEE2E2; border:1px solid #FCA5A5; "
                    "border-radius:6px; padding:8px; font-family:monospace; "
                    "font-size:0.78rem; color:#B91C1C;'>"
                    + "<br>".join(result["not_in_new"])
                    + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("—")
        with d3:
            st.markdown(f"**● Solo en nuevo ({only_new_n})**")
            if result["only_in_new"]:
                st.markdown(
                    "<div style='max-height:240px; overflow-y:auto; "
                    "background:#FEF3C7; border:1px solid #FCD34D; "
                    "border-radius:6px; padding:8px; font-family:monospace; "
                    "font-size:0.78rem; color:#D97706;'>"
                    + "<br>".join(result["only_in_new"])
                    + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("—")

    # Download
    st.markdown("")
    base_name = (new_parsed["file_name"] or "migrated")
    base_name = re.sub(r"\.[^.]+$", "", base_name)

    if output_format == "TSV":
        data = _build_migrated_tsv(result["output_rows"])
        file_name = f"{base_name}_migrated.tsv"
        mime = "text/tab-separated-values"
    else:
        data = _build_migrated_xlsx(result["output_rows"], result["sheet_name"])
        file_name = f"{base_name}_migrated.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    st.download_button(
        label=f"⬇️ Descargar archivo migrado ({output_format})",
        data=data,
        file_name=file_name,
        mime=mime,
        key=k("dl_migrated"),
    )
    st.caption(
        "El archivo preserva la estructura del template nuevo (rows pre-data) "
        "con los datos del old transferidos según el mapeo de columnas."
    )


# ── Render principal ────────────────────────────────────────────────────

def render():
    _header()

    st.markdown(
        "Transferí los datos de tu flat file viejo al template nuevo de Amazon en segundos. "
        "Soporta `.xlsx`, `.xls`, `.xlsm`, `.tsv`, `.csv`, `.txt`."
    )

    # Ayuda rápida (always-visible expander)
    with st.expander("ℹ️ Cómo funciona", expanded=False):
        st.markdown(
            "1. **Subí el flat file viejo** (con tus datos de productos)\n"
            "2. **Subí el template nuevo** descargado de Seller Central → Catalog → Add Products via Upload\n"
            "3. **Migrar Data →** mapea columnas usando 5 estrategias en cascada:\n"
            "   - Match exacto de field IDs (lowercase)\n"
            "   - Match normalizado (sin brackets, hash, sufijos numéricos)\n"
            "   - Aliases bidireccionales (~40 mappings: `item_sku ↔ contribution_sku`, "
            "`brand ↔ brand_name`, `main_image_url ↔ main_product_image_locator`, etc.)\n"
            "   - Match por base name del field ID\n"
            "   - Match por header normalizado (fallback)\n"
            "4. **Filtra filas internas Amazon** (`marketplace_id=`, `[language_tag=`, etc.)\n"
            "5. **Skip example row**: la primera data row del old (ejemplo Amazon) se saltea por default\n"
            "6. **Descargá** el resultado en `.xlsx` o `.tsv`"
        )

    st.markdown("")

    # Empty state si ningún uploader fue tocado en ningún tab.
    # (cada tab tiene su propio empty state implícito en sus uploaders.)
    # Solo lo mostramos si literalmente ningún archivo fue subido en ningún MP.
    no_files_anywhere = all(
        st.session_state.get(f"ffm_{m['suffix']}_file_old") is None
        and st.session_state.get(f"ffm_{m['suffix']}_file_new") is None
        for m in _MARKETPLACES
    )
    if no_files_anywhere:
        _empty_state()
        st.markdown("")

    # 5 tabs por marketplace
    tab_labels = [m["label"] for m in _MARKETPLACES]
    tabs = st.tabs(tab_labels)

    for tab, mp in zip(tabs, _MARKETPLACES):
        with tab:
            _render_marketplace(mp["suffix"], mp["sheets"])
