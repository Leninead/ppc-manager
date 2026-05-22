"""B7 Importer — extractor puro HTML → BlockDraft + ImportReport.

Parsea HTML con la convención data-proposal-* del contrato Importer B7 v1.0
(notes/sales/contrato-importer-b7-v1.md) y devuelve un report con los
bloques extraídos + warnings + errors.

Sin side effects: NO toca disk, NO toca UI, NO toca propuestas existentes.
El caller decide si aplicar report.blocks como overwrite o no
(condicional a report.ok).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ImportWarning:
    code: str  # 'array_empty' | 'field_unknown' | 'enum_unknown'
               # | 'required_missing' | 'coercion_failed'
               # | 'duplicate_module_id_in_html'  (extract)
               # | 'block_not_in_target' | 'duplicate_module_id'  (merge)
    block_index: int
    module_id: str | None
    field_path: str
    message: str


@dataclass
class ImportError:
    code: str  # 'no_blocks' | 'module_id_unknown'
               # | 'contract_version_major_mismatch'  (extract)
               # | 'report_not_ok' | 'target_proposal_malformed'  (merge)
    block_index: int | None
    module_id: str | None
    message: str


@dataclass
class BlockDraft:
    module_id: str
    data: dict
    block_index: int
    contract_version: str


@dataclass
class ImportReport:
    blocks: list[BlockDraft] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)
    errors: list[ImportError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass
class MergeResult:
    proposal_updated: dict
    applied_blocks: list[str] = field(default_factory=list)  # module_ids overwriteados
    skipped_blocks: list[tuple[str, str]] = field(default_factory=list)  # (module_id, reason)
    warnings: list[ImportWarning] = field(default_factory=list)
    errors: list[ImportError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Constantes — convención §3 del contrato
# ---------------------------------------------------------------------------

_SUPPORTED_MAJOR = 1  # B7 v1.x soporta contract-version major == 1


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _load_html(source: str | bytes) -> BeautifulSoup:
    """Devuelve BS parseado con html.parser (stdlib, no requiere lxml)."""
    return BeautifulSoup(source, "html.parser")


def _extract_value(element) -> str:
    """Extrae el valor de un elemento según §3 del contrato.

    Orden de prioridad:
        1. atributo data-proposal-value (override total, sin trim).
        2. tag == 'a' → href trimeado.
        3. tag == 'img' → data-src o src.
        4. default → textContent trimeado.
    """
    override = element.get("data-proposal-value")
    if override is not None:
        return override

    tag = element.name.lower() if element.name else ""
    if tag == "a":
        return (element.get("href") or "").strip()
    if tag == "img":
        return element.get("data-src") or element.get("src") or ""

    return element.get_text(strip=True)


def _resolve_contract_version(block_el, soup: BeautifulSoup) -> str:
    """Devuelve la contract-version del primer ancestor que la declare.

    Falla suavemente a "1.0" si nadie la declara (default §3 del contrato).
    """
    cur = block_el
    while cur is not None and getattr(cur, "name", None):
        v = cur.get("data-proposal-contract-version") if hasattr(cur, "get") else None
        if v:
            return str(v).strip()
        cur = cur.parent
    # fallback: el root del documento puede ser <html> con el attr
    root = soup.find(attrs={"data-proposal-contract-version": True})
    if root is not None:
        v = root.get("data-proposal-contract-version")
        if v:
            return str(v).strip()
    return "1.0"


def _parse_major(version: str) -> int | None:
    """Devuelve el major de un string semver-ish ('1.0' → 1). None si falla."""
    try:
        return int(str(version).strip().split(".")[0])
    except (ValueError, AttributeError, IndexError):
        return None


def _find_module_in_catalog(catalog: dict, module_id: str) -> dict | None:
    """Busca el dict del módulo en catalog['modules'] por module_id."""
    for mod in catalog.get("modules", []):
        if mod.get("module_id") == module_id:
            return mod
    return None


def _closest_block_ancestor(element, block_el):
    """Verifica que el ancestro [data-proposal-block] más cercano sea block_el.

    Sirve para descartar fields/arrays que viven dentro de un block anidado.
    """
    cur = element.parent
    while cur is not None and getattr(cur, "name", None):
        if cur.has_attr("data-proposal-block") if hasattr(cur, "has_attr") else False:
            return cur is block_el
        cur = cur.parent
    return False


def _is_inside_item(element, block_el) -> bool:
    """True si el elemento está dentro de un [data-proposal-item] que pertenece
    al block_el (no más allá del block).
    """
    cur = element.parent
    while cur is not None and getattr(cur, "name", None):
        if cur is block_el:
            return False
        if hasattr(cur, "has_attr") and cur.has_attr("data-proposal-item"):
            return True
        cur = cur.parent
    return False


# ---------------------------------------------------------------------------
# Coerción + validación contra items_schema
# ---------------------------------------------------------------------------


def _coerce_scalar(
    raw: str,
    schema: dict,
    block_index: int,
    module_id: str,
    field_path: str,
) -> tuple[Any, list[ImportWarning]]:
    """Coerciona un valor escalar según el dtype declarado en schema.

    Devuelve (valor_coercionado, warnings). El value puede ser None si la
    coerción numérica falla (regla §6.8) o "unknown" si está fuera del enum
    (regla §6.6).
    """
    warnings: list[ImportWarning] = []
    dtype = schema.get("dtype", "string")
    enum = schema.get("enum")

    if dtype == "string":
        value: Any = str(raw) if raw is not None else ""
    elif dtype == "integer":
        try:
            value = int(str(raw).strip())
        except (ValueError, TypeError):
            warnings.append(ImportWarning(
                code="coercion_failed",
                block_index=block_index,
                module_id=module_id,
                field_path=field_path,
                message=f"No se pudo coercionar {raw!r} a integer; se asigna null.",
            ))
            value = None
    elif dtype == "number":
        try:
            value = float(str(raw).strip())
        except (ValueError, TypeError):
            warnings.append(ImportWarning(
                code="coercion_failed",
                block_index=block_index,
                module_id=module_id,
                field_path=field_path,
                message=f"No se pudo coercionar {raw!r} a number; se asigna null.",
            ))
            value = None
    else:
        # dtype desconocido — pasa el string crudo.
        value = str(raw) if raw is not None else ""

    # Enum check (después de la coerción).
    if enum is not None and value is not None and value != "":
        # Comparación contra enum hecha con string para tolerar value coerced.
        if str(value) not in {str(x) for x in enum}:
            warnings.append(ImportWarning(
                code="enum_unknown",
                block_index=block_index,
                module_id=module_id,
                field_path=field_path,
                message=(
                    f"Valor {value!r} fuera del set permitido {enum}; "
                    f"se asigna 'unknown'."
                ),
            ))
            value = "unknown"

    return value, warnings


def _validate_item(
    item_dict: dict,
    raw_items: dict,
    items_schema: dict,
    block_index: int,
    module_id: str,
    array_key: str,
    item_idx: int,
) -> tuple[dict, list[ImportWarning]]:
    """Aplica coerción + warnings sobre un item ya extraído como strings.

    Args:
        item_dict: dict {field_name: raw_value_str} extraído del HTML.
        raw_items: alias de item_dict (compat con caller).
        items_schema: schema del array según _catalog.json.
        block_index, module_id, array_key, item_idx: contexto para field_path.

    Returns:
        (item_coercionado, warnings).
    """
    warnings: list[ImportWarning] = []
    out: dict = {}

    # Pasada 1: coerción + enum + field_unknown.
    for field_name, raw_value in item_dict.items():
        if field_name in items_schema:
            field_schema = items_schema[field_name]
            field_path = f"{array_key}[{item_idx}].{field_name}"
            coerced, coerce_warnings = _coerce_scalar(
                raw_value, field_schema, block_index, module_id, field_path,
            )
            warnings.extend(coerce_warnings)
            out[field_name] = coerced
        else:
            warnings.append(ImportWarning(
                code="field_unknown",
                block_index=block_index,
                module_id=module_id,
                field_path=f"{array_key}[{item_idx}].{field_name}",
                message=(
                    f"Field {field_name!r} no está declarado en items_schema "
                    f"de {array_key}; se ignora en el output."
                ),
            ))

    # Pasada 2: required_missing.
    for field_name, field_schema in items_schema.items():
        if not field_schema.get("required"):
            continue
        v = out.get(field_name)
        if v is None or v == "":
            warnings.append(ImportWarning(
                code="required_missing",
                block_index=block_index,
                module_id=module_id,
                field_path=f"{array_key}[{item_idx}].{field_name}",
                message=(
                    f"Field requerido {field_name!r} ausente o vacío en item."
                ),
            ))

    return out, warnings


# ---------------------------------------------------------------------------
# Extractor de bloque
# ---------------------------------------------------------------------------


def _extract_block_data(
    block_el,
    catalog: dict,
    block_index: int,
    contract_version: str,
) -> tuple[BlockDraft | None, list[ImportWarning], list[ImportError]]:
    """Convierte un [data-proposal-block] a BlockDraft + warnings + errors."""
    warnings: list[ImportWarning] = []
    errors: list[ImportError] = []

    module_id = block_el.get("data-proposal-block") or ""
    module_id = module_id.strip()

    if not module_id:
        errors.append(ImportError(
            code="module_id_unknown",
            block_index=block_index,
            module_id=None,
            message="Atributo data-proposal-block sin valor.",
        ))
        return None, warnings, errors

    mod_def = _find_module_in_catalog(catalog, module_id)
    if mod_def is None:
        errors.append(ImportError(
            code="module_id_unknown",
            block_index=block_index,
            module_id=module_id,
            message=f"module_id {module_id!r} no existe en _catalog.json.",
        ))
        return None, warnings, errors

    schema = mod_def.get("schema", {}) or {}
    data: dict = {}

    # --- Escalares a nivel block ---------------------------------------------------
    # Fields que cuelgan del block (no dentro de un item).
    scalar_fields = block_el.find_all(attrs={"data-proposal-field": True})
    for el in scalar_fields:
        # Solo si su ancestro [data-proposal-block] más cercano es block_el.
        if not _closest_block_ancestor(el, block_el):
            continue
        # Y NO está dentro de un [data-proposal-item] (esos son del item).
        if _is_inside_item(el, block_el):
            continue

        field_name = el.get("data-proposal-field", "").strip()
        if not field_name:
            continue
        raw_value = _extract_value(el)

        if field_name in schema:
            coerced, coerce_warnings = _coerce_scalar(
                raw_value, schema[field_name], block_index, module_id, field_name,
            )
            warnings.extend(coerce_warnings)
            data[field_name] = coerced
        else:
            # Field no declarado a nivel block — lo pasamos como string crudo.
            # No warneamos porque el schema a nivel block de M29 es laxo en v1
            # (mucho dtype "object" / "array<object>" sin items_schema).
            data[field_name] = raw_value

    # --- Arrays ---------------------------------------------------------------------
    array_containers = block_el.find_all(attrs={"data-proposal-array": True})
    for arr_el in array_containers:
        if not _closest_block_ancestor(arr_el, block_el):
            continue
        if _is_inside_item(arr_el, block_el):
            # Array anidado dentro de un item — fuera de scope v1.
            continue

        array_key = arr_el.get("data-proposal-array", "").strip()
        if not array_key:
            continue

        # Items del array.
        item_elements = arr_el.find_all(attrs={"data-proposal-item": True})
        # Solo los que pertenecen a este array (no a un sub-array anidado).
        own_items = []
        for it in item_elements:
            # Buscar el ancestro [data-proposal-array] más cercano y verificar
            # que sea arr_el (no un array anidado).
            cur = it.parent
            owner = None
            while cur is not None and getattr(cur, "name", None):
                if hasattr(cur, "has_attr") and cur.has_attr("data-proposal-array"):
                    owner = cur
                    break
                if cur is block_el:
                    break
                cur = cur.parent
            if owner is arr_el:
                own_items.append(it)

        items_list: list[dict] = []
        array_schema = schema.get(array_key, {}) or {}
        items_schema = array_schema.get("items_schema")

        for item_idx, item_el in enumerate(own_items):
            # Field-by-field dentro del item.
            raw_item: dict = {}
            item_field_els = item_el.find_all(
                attrs={"data-proposal-item-field": True}
            )
            for fel in item_field_els:
                # Verificar que el item ancestor más cercano sea item_el.
                cur = fel.parent
                owner_item = None
                while cur is not None and getattr(cur, "name", None):
                    if hasattr(cur, "has_attr") and cur.has_attr("data-proposal-item"):
                        owner_item = cur
                        break
                    if cur is arr_el:
                        break
                    cur = cur.parent
                if owner_item is not item_el:
                    continue

                fname = fel.get("data-proposal-item-field", "").strip()
                if not fname:
                    continue
                raw_item[fname] = _extract_value(fel)

            if items_schema:
                coerced_item, item_warnings = _validate_item(
                    raw_item,
                    raw_item,
                    items_schema,
                    block_index,
                    module_id,
                    array_key,
                    item_idx,
                )
                warnings.extend(item_warnings)
                items_list.append(coerced_item)
            else:
                # Sin items_schema (V5/V6 actuales) → pasar items como strings.
                items_list.append(raw_item)

        # array_empty warning si el array está declarado en schema y vino vacío.
        if array_key in schema and len(items_list) == 0:
            warnings.append(ImportWarning(
                code="array_empty",
                block_index=block_index,
                module_id=module_id,
                field_path=array_key,
                message=(
                    f"Array {array_key!r} declarado en schema pero llegó vacío "
                    f"en el HTML."
                ),
            ))

        data[array_key] = items_list

    draft = BlockDraft(
        module_id=module_id,
        data=data,
        block_index=block_index,
        contract_version=contract_version,
    )
    return draft, warnings, errors


# ---------------------------------------------------------------------------
# Entry point público
# ---------------------------------------------------------------------------


def extract_blocks(html_source: str | bytes, catalog: dict) -> ImportReport:
    """Parsea HTML B7 y devuelve report con blocks extraídos + warnings/errors.

    Args:
        html_source: HTML crudo (str o bytes).
        catalog: contenido parseado de data/sales/_catalog.json.

    Returns:
        ImportReport. Si report.errors no está vacío, NO usar report.blocks
        para overwrite (data potencialmente inválida).
    """
    report = ImportReport()
    soup = _load_html(html_source)

    block_elements = soup.find_all(attrs={"data-proposal-block": True})

    if not block_elements:
        report.errors.append(ImportError(
            code="no_blocks",
            block_index=None,
            module_id=None,
            message="HTML sin bloques M29 reconocibles (data-proposal-block).",
        ))
        return report

    seen_module_ids: dict[str, int] = {}

    for block_index, block_el in enumerate(block_elements):
        contract_version = _resolve_contract_version(block_el, soup)
        major = _parse_major(contract_version)
        if major is None or major > _SUPPORTED_MAJOR:
            module_id_attr = (block_el.get("data-proposal-block") or "").strip() or None
            report.errors.append(ImportError(
                code="contract_version_major_mismatch",
                block_index=block_index,
                module_id=module_id_attr,
                message=(
                    f"Contrato {contract_version!r} no soportado; B7 actual "
                    f"soporta hasta v{_SUPPORTED_MAJOR}.x."
                ),
            ))
            continue

        draft, warnings, errors = _extract_block_data(
            block_el, catalog, block_index, contract_version,
        )
        report.warnings.extend(warnings)
        report.errors.extend(errors)

        if draft is None:
            continue

        # Detección de module_id duplicado en el mismo HTML.
        # No bloqueante (warning, no error): el primer bloque gana, los
        # subsiguientes se ignoran. Coherente con el manejo de duplicate_module_id
        # en merge_blocks (también es warning).
        if draft.module_id in seen_module_ids:
            first_index = seen_module_ids[draft.module_id]
            report.warnings.append(ImportWarning(
                code="duplicate_module_id_in_html",
                block_index=block_index,
                module_id=draft.module_id,
                field_path=f"blocks[{block_index}]",
                message=(
                    f"module_id {draft.module_id!r} aparece múltiples veces en "
                    f"el HTML; se procesa el primer bloque (index {first_index}) "
                    f"y se ignoran los duplicados subsiguientes."
                ),
            ))
            continue

        seen_module_ids[draft.module_id] = block_index
        report.blocks.append(draft)

    return report


# ---------------------------------------------------------------------------
# Merge layer — capa 2: aplica un ImportReport sobre un proposal target
# ---------------------------------------------------------------------------


def merge_blocks(
    report: ImportReport,
    target_proposal: dict,
    catalog: dict,
) -> MergeResult:
    """Merge B7 blocks en target_proposal. Función pura, sin I/O.

    Reglas (contrato B7 §6):
    - Overwrite TOTAL del data del bloque target (sin merge field-by-field).
    - Si module_id del HTML no existe en target_proposal.blocks →
      skip + ImportWarning code='block_not_in_target'.
    - Si target_proposal tiene 2+ bloques con mismo module_id →
      updatear el primero + ImportWarning code='duplicate_module_id'.
    - Si report.ok == False → MergeResult con ImportError, sin merge.
    - Si target_proposal no tiene key 'blocks' o no es lista →
      ImportError code='target_proposal_malformed'.

    El merge sólo afecta block['data']. Los campos id, module_id, proposal_id,
    is_fixed, copy_overrides se preservan intactos. Esto es coherente con
    §6 del contrato B7 ('overwrite del data del bloque target') — no
    'overwrite del block entero'.

    Args:
        report: salida de extract_blocks. Debe ser ok.
        target_proposal: dict de proposal cargado del disco.
        catalog: contenido de _catalog.json (no utilizado en v1 del merge,
            queda como signature por si v1.1 agrega validación cruzada
            módulo → arquetipo de la propuesta).

    Returns:
        MergeResult. proposal_updated es una COPIA modificada
        (deepcopy del input). No muta target_proposal.
    """
    # Caso early: report con errores → no se hace merge.
    if not report.ok:
        return MergeResult(
            proposal_updated=copy.deepcopy(target_proposal),
            errors=[
                ImportError(
                    code="report_not_ok",
                    block_index=None,
                    module_id=None,
                    message=(
                        f"ImportReport tiene {len(report.errors)} error(es); "
                        f"merge abortado. Codes: "
                        f"{sorted({e.code for e in report.errors})}"
                    ),
                ),
            ],
        )

    # Validación shape mínimo de target_proposal.
    blocks = target_proposal.get("blocks") if isinstance(target_proposal, dict) else None
    if not isinstance(blocks, list):
        return MergeResult(
            proposal_updated=copy.deepcopy(target_proposal) if isinstance(target_proposal, dict) else {},
            errors=[
                ImportError(
                    code="target_proposal_malformed",
                    block_index=None,
                    module_id=None,
                    message=(
                        "target_proposal.blocks ausente o no es una lista; "
                        "merge abortado."
                    ),
                ),
            ],
        )

    # Deepcopy: cero side effects sobre target_proposal.
    updated = copy.deepcopy(target_proposal)
    updated_blocks: list = updated["blocks"]

    result = MergeResult(proposal_updated=updated)

    for draft in report.blocks:
        # Buscar TODOS los blocks del target con el module_id del draft.
        matches = [
            (idx, blk) for idx, blk in enumerate(updated_blocks)
            if isinstance(blk, dict) and blk.get("module_id") == draft.module_id
        ]

        if not matches:
            result.skipped_blocks.append((draft.module_id, "block_not_in_target"))
            result.warnings.append(ImportWarning(
                code="block_not_in_target",
                block_index=draft.block_index,
                module_id=draft.module_id,
                field_path=f"blocks[?].{draft.module_id}",
                message=(
                    f"module_id {draft.module_id!r} viene en el HTML pero no "
                    f"existe en target_proposal.blocks; bloque skipeado."
                ),
            ))
            continue

        # Duplicate module_id en el target → usar el primero, warnear.
        if len(matches) > 1:
            dup_indices = [str(idx) for idx, _ in matches]
            result.warnings.append(ImportWarning(
                code="duplicate_module_id",
                block_index=draft.block_index,
                module_id=draft.module_id,
                field_path=f"blocks[{matches[0][0]}]",
                message=(
                    f"target_proposal.blocks tiene {len(matches)} bloques con "
                    f"module_id {draft.module_id!r} (indices {','.join(dup_indices)}); "
                    f"se actualiza el primero (idx {matches[0][0]}). Cleanup manual "
                    f"queda a cargo del operador."
                ),
            ))

        # Overwrite quirúrgico: SOLO el campo 'data'. id/module_id/proposal_id/
        # is_fixed/copy_overrides se preservan intactos.
        target_idx, _ = matches[0]
        updated_blocks[target_idx]["data"] = copy.deepcopy(draft.data)
        result.applied_blocks.append(draft.module_id)

    return result
