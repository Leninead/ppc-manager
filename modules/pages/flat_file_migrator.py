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
