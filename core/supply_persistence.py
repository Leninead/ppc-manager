"""Capa de persistencia del módulo Supply Chain (M37).

Diseñada para migrar a Supabase sin tocar consumidores. La clase abstracta
`SupplyStorage` define el contrato; `LocalJsonStorage` implementa Fase 1
(JSON local + Parquet append-only para el log de eventos).

Cuando aparezca `SupabaseStorage`, el swap es transparente — solo cambia
`_default_storage()`.

API pública (10 helpers):
    list_proveedores(incluir_inactivos=False) -> list[dict]
    get_proveedor(prov_id) -> dict | None
    save_proveedor(prov) -> dict
    archivar_proveedor(prov_id) -> bool
    list_ocs(proveedor_id=None, estado=None) -> list[dict]
    get_oc(oc_id) -> dict | None
    save_oc(oc) -> dict
    anular_oc(oc_id) -> bool
    registrar_evento(oc_id, evento, fecha=None, quien="") -> dict
    leer_eventos(oc_id=None) -> pd.DataFrame
    (+ _set_storage_for_testing, solo para tests)

Reglas duras:
- Cero lógica de negocio acá. Solo CRUD y validación de forma.
- El lead time medido, el fill rate y la secuencia de códigos de OC NO viven
  en este archivo: van en `core/supply_metrics.py`.
- Soft delete: archivar proveedor = activo=False; anular OC = estado='ANULADA'.
  Nunca se borra un archivo.
- El `id` de la OC lo trae el caller (lo genera supply_metrics). Acá solo se
  valida que venga.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.supply_paths import (
    EVENTOS_LOG_FILE,
    OCS_DIR,
    PROVEEDORES_FILE,
    ensure_dirs,
    oc_file,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constantes de dominio (referencia; la transición la valida supply_metrics)
# ─────────────────────────────────────────────────────────────────────────────

ESTADOS_OC = (
    "PROPUESTA",
    "APROBADA",
    "OK_FIN",
    "EMITIDA",
    "RECIBIDA_PARCIAL",
    "CERRADA",
    "ANULADA",
)
"""Estados válidos de una orden de compra. Este archivo solo valida pertenencia
al conjunto (validación de forma); qué transición es legal lo decide supply_metrics."""

_EVENTO_COLUMNS = ["oc_id", "evento", "fecha", "quien", "ts"]


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _slugify(nombre: str) -> str:
    """Slug de id a partir del nombre: minúsculas, espacios → guiones."""
    return re.sub(r"\s+", "-", nombre.strip().lower())


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict | list) -> None:
    """Escritura atómica: archivo temporal + os.replace (no deja JSON truncado)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract storage contract
# ─────────────────────────────────────────────────────────────────────────────


class SupplyStorage(ABC):
    """Contrato de almacenamiento. Implementar para cambiar backend (local/SQLite/Supabase)."""

    # — Proveedores —
    @abstractmethod
    def read_proveedores(self) -> list[dict]:
        """Devuelve la lista completa de proveedores (incluye inactivos). [] si no hay."""
        ...

    @abstractmethod
    def write_proveedores(self, proveedores: list[dict]) -> None: ...

    # — Órdenes de compra —
    @abstractmethod
    def write_oc(self, oc: dict) -> Path | str: ...

    @abstractmethod
    def read_oc(self, oc_id: str) -> dict | None: ...

    @abstractmethod
    def list_oc_files(self) -> Iterable[dict]:
        """Itera todas las OC. Cada elemento es el dict completo."""
        ...

    # — Eventos —
    @abstractmethod
    def append_evento(self, evento_row: dict) -> None: ...

    @abstractmethod
    def read_eventos(self) -> pd.DataFrame: ...


class LocalJsonStorage(SupplyStorage):
    """Fase 1: JSON local + Parquet append-only para el log de eventos."""

    # — Proveedores —

    def read_proveedores(self) -> list[dict]:
        data = _read_json(PROVEEDORES_FILE)
        if not isinstance(data, list):
            return []
        return data

    def write_proveedores(self, proveedores: list[dict]) -> None:
        ensure_dirs()
        _write_json(PROVEEDORES_FILE, proveedores)

    # — Órdenes de compra —

    def write_oc(self, oc: dict) -> Path:
        ensure_dirs()
        path = oc_file(oc["id"])
        _write_json(path, oc)
        return path

    def read_oc(self, oc_id: str) -> dict | None:
        data = _read_json(oc_file(oc_id))
        if not isinstance(data, dict):
            return None
        return data

    def list_oc_files(self) -> Iterable[dict]:
        if not OCS_DIR.exists():
            return
        for f in sorted(OCS_DIR.glob("*.json")):
            data = _read_json(f)
            if isinstance(data, dict):
                yield data

    # — Eventos —

    def append_evento(self, evento_row: dict) -> None:
        """Append atomico: escribe a .tmp y os.replace (igual que _write_json).

        Un corte durante to_parquet no puede dejar el log a medio escribir: el
        archivo real solo se reemplaza cuando el temporal quedo completo. Importa
        porque este log es la fuente del lead time medido.
        """
        ensure_dirs()
        new_df = pd.DataFrame([evento_row])
        if EVENTOS_LOG_FILE.exists():
            existing = pd.read_parquet(EVENTOS_LOG_FILE)
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df
        tmp = EVENTOS_LOG_FILE.with_suffix(EVENTOS_LOG_FILE.suffix + ".tmp")
        combined.to_parquet(tmp, compression="snappy", index=False)
        os.replace(tmp, EVENTOS_LOG_FILE)

    def read_eventos(self) -> pd.DataFrame:
        """Devuelve siempre el mismo shape: _EVENTO_COLUMNS, en ese orden.

        Exista o no el parquet, y le falten o no columnas, el consumidor recibe
        las 5 columnas canonicas. Las que falten se agregan vacias.
        """
        if not EVENTOS_LOG_FILE.exists():
            return pd.DataFrame(columns=_EVENTO_COLUMNS)
        df = pd.read_parquet(EVENTOS_LOG_FILE)
        for col in _EVENTO_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        return df[_EVENTO_COLUMNS]


# ─────────────────────────────────────────────────────────────────────────────
# Default storage selector
# ─────────────────────────────────────────────────────────────────────────────


_STORAGE: SupplyStorage | None = None


def _default_storage() -> SupplyStorage:
    global _STORAGE
    if _STORAGE is None:
        _STORAGE = LocalJsonStorage()
    return _STORAGE


def _set_storage_for_testing(storage: SupplyStorage) -> None:
    """Permite a los tests inyectar un storage alternativo. NO usar en producción."""
    global _STORAGE
    _STORAGE = storage


# ─────────────────────────────────────────────────────────────────────────────
# Proveedores — CRUD
# ─────────────────────────────────────────────────────────────────────────────


def _validate_proveedor(prov: dict) -> None:
    """Valida FORMA solamente. Lanza ValueError con mensaje claro."""
    nombre = str(prov.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("Proveedor: 'nombre' es obligatorio y no puede estar vacío")

    # Lead times: si vienen, tienen que ser números y respetar min <= tip <= max.
    lts: dict[str, float] = {}
    for k in ("lt_min", "lt_tip", "lt_max"):
        v = prov.get(k)
        if v is None or v == "":
            continue
        try:
            lts[k] = float(v)
        except (TypeError, ValueError):
            raise ValueError(
                f"Proveedor '{nombre}': '{k}' debe ser numérico (recibido: {v!r})"
            )

    for lo, hi in (("lt_min", "lt_tip"), ("lt_tip", "lt_max"), ("lt_min", "lt_max")):
        if lo in lts and hi in lts and lts[lo] > lts[hi]:
            raise ValueError(
                f"Proveedor '{nombre}': {lo} ({lts[lo]}) no puede ser mayor que {hi} ({lts[hi]})"
            )

    rev = prov.get("revision_dias")
    if rev is not None and rev != "":
        try:
            rev_f = float(rev)
        except (TypeError, ValueError):
            raise ValueError(
                f"Proveedor '{nombre}': 'revision_dias' debe ser numérico (recibido: {rev!r})"
            )
        if rev_f <= 0:
            raise ValueError(
                f"Proveedor '{nombre}': 'revision_dias' debe ser > 0 (recibido: {rev_f})"
            )


def save_proveedor(prov: dict) -> dict:
    """Crea o actualiza un proveedor en el maestro (upsert por id).

    - Si no trae 'id', lo genera como slug del nombre (minúsculas, espacios → guiones).
    - Si el id ya existe, actualiza esa entrada; si no, la agrega al final.
    - Setea campos de sistema: creado_en (solo al crear) y actualizado_en.
    - 'activo' arranca en True si no viene.

    Returns:
        El dict tal como fue persistido.
    """
    storage = _default_storage()

    prov = dict(prov)  # shallow copy para no mutar al caller
    _validate_proveedor(prov)

    if not prov.get("id"):
        prov["id"] = _slugify(str(prov["nombre"])) or _new_uuid()

    if "activo" not in prov:
        prov["activo"] = True

    proveedores = storage.read_proveedores()
    idx = next(
        (i for i, p in enumerate(proveedores) if p.get("id") == prov["id"]), None
    )

    if idx is None:
        prov["creado_en"] = prov.get("creado_en") or _now_iso()
        prov["actualizado_en"] = _now_iso()
        proveedores.append(prov)
    else:
        prov["creado_en"] = proveedores[idx].get("creado_en") or _now_iso()
        prov["actualizado_en"] = _now_iso()
        proveedores[idx] = prov

    storage.write_proveedores(proveedores)
    return prov


def get_proveedor(prov_id: str) -> dict | None:
    """Lee un proveedor por id. None si no existe (busca también entre inactivos)."""
    for p in _default_storage().read_proveedores():
        if p.get("id") == prov_id:
            return p
    return None


def list_proveedores(incluir_inactivos: bool = False) -> list[dict]:
    """Lista los proveedores del maestro, ordenados por nombre.

    Por defecto oculta los archivados (activo=False).
    """
    proveedores = _default_storage().read_proveedores()
    if not incluir_inactivos:
        proveedores = [p for p in proveedores if p.get("activo", True)]
    return sorted(proveedores, key=lambda p: str(p.get("nombre", "")).lower())


def archivar_proveedor(prov_id: str) -> bool:
    """Soft delete: marca activo=False. No borra nada.

    Returns:
        True si el proveedor existía y quedó archivado. False si no existe.
    """
    storage = _default_storage()
    proveedores = storage.read_proveedores()
    for p in proveedores:
        if p.get("id") == prov_id:
            p["activo"] = False
            p["actualizado_en"] = _now_iso()
            storage.write_proveedores(proveedores)
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Órdenes de compra — CRUD
# ─────────────────────────────────────────────────────────────────────────────


def _validate_oc(oc: dict) -> None:
    """Valida FORMA solamente. Lanza ValueError con mensaje claro."""
    oc_id = str(oc.get("id") or "").strip()
    if not oc_id:
        raise ValueError(
            "OC: falta 'id'. El código de OC lo genera el caller (core/supply_metrics.py)."
        )

    if not str(oc.get("proveedor_id") or "").strip():
        raise ValueError(
            f"OC '{oc_id}': 'proveedor_id' es obligatorio y no puede estar vacío"
        )

    if oc.get("estado") not in ESTADOS_OC:
        raise ValueError(
            f"OC '{oc_id}': estado inválido '{oc.get('estado')}'. Válidos: {list(ESTADOS_OC)}"
        )

    lineas = oc.get("lineas")
    if not isinstance(lineas, list) or not lineas:
        raise ValueError(f"OC '{oc_id}': 'lineas' debe ser una lista no vacía")

    for i, linea in enumerate(lineas):
        if not isinstance(linea, dict):
            raise ValueError(f"OC '{oc_id}' línea #{i}: cada línea debe ser un dict")
        if not str(linea.get("sku") or "").strip():
            raise ValueError(f"OC '{oc_id}' línea #{i}: falta 'sku'")
        try:
            qty = float(linea.get("qty"))
        except (TypeError, ValueError):
            raise ValueError(
                f"OC '{oc_id}' línea #{i}: 'qty' debe ser numérico "
                f"(recibido: {linea.get('qty')!r})"
            )
        if qty <= 0:
            raise ValueError(
                f"OC '{oc_id}' línea #{i}: 'qty' debe ser > 0 (recibido: {qty})"
            )


def save_oc(oc: dict) -> dict:
    """Guarda una orden de compra (un archivo por OC).

    - El 'id' lo trae el caller: el código de OC lo genera supply_metrics, no acá.
    - 'estado' arranca en 'PROPUESTA' si no viene.
    - Cada línea sin 'recibido' arranca en 0.
    - Setea campos de sistema: creado_en (solo al crear) y actualizado_en.
    - Valida forma antes de escribir.

    Returns:
        El dict tal como fue persistido.
    """
    storage = _default_storage()

    oc = dict(oc)  # shallow copy para no mutar al caller
    oc.setdefault("estado", "PROPUESTA")

    if isinstance(oc.get("lineas"), list):
        oc["lineas"] = [
            {**ln, "recibido": ln.get("recibido", 0)} if isinstance(ln, dict) else ln
            for ln in oc["lineas"]
        ]

    _validate_oc(oc)

    existing = storage.read_oc(oc["id"])
    if existing is None:
        oc["creado_en"] = oc.get("creado_en") or _now_iso()
    else:
        oc["creado_en"] = existing.get("creado_en") or oc.get("creado_en") or _now_iso()
    oc["actualizado_en"] = _now_iso()

    storage.write_oc(oc)
    return oc


def get_oc(oc_id: str) -> dict | None:
    """Lee una orden de compra por id. None si no existe."""
    return _default_storage().read_oc(oc_id)


def list_ocs(proveedor_id: str | None = None, estado: str | None = None) -> list[dict]:
    """Lista las órdenes de compra con filtros opcionales.

    Ordenadas por actualizado_en descendente (la más reciente primero).
    """
    results = list(_default_storage().list_oc_files())

    if proveedor_id:
        results = [o for o in results if o.get("proveedor_id") == proveedor_id]
    if estado:
        results = [o for o in results if o.get("estado") == estado]

    return sorted(
        results, key=lambda o: str(o.get("actualizado_en", "")), reverse=True
    )


def anular_oc(oc_id: str) -> bool:
    """Soft delete: marca estado='ANULADA'. No borra el archivo.

    Returns:
        True si la OC existía y quedó anulada. False si no existe.
    """
    current = get_oc(oc_id)
    if current is None:
        return False
    anulada = dict(current)
    anulada["estado"] = "ANULADA"
    save_oc(anulada)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Eventos — log append-only
# ─────────────────────────────────────────────────────────────────────────────


def registrar_evento(
    oc_id: str,
    evento: str,
    fecha: str | None = None,
    quien: str = "",
) -> dict:
    """Registra un cambio de estado de una OC en el log append-only.

    `fecha` es la fecha de negocio del evento (default: ahora); `ts` es el momento
    en que se escribió la fila. Se separan a propósito: el lead time medido se
    calcula sobre `fecha`, que el AM puede backdatear.

    Returns:
        El dict de la fila persistida.
    """
    if not str(oc_id or "").strip():
        raise ValueError("registrar_evento: 'oc_id' es obligatorio")
    if not str(evento or "").strip():
        raise ValueError(f"registrar_evento (OC '{oc_id}'): 'evento' es obligatorio")

    row = {
        "oc_id": oc_id,
        "evento": evento,
        "fecha": fecha or _now_iso(),
        "quien": quien,
        "ts": _now_iso(),
    }
    _default_storage().append_evento(row)
    return row


def leer_eventos(oc_id: str | None = None) -> pd.DataFrame:
    """Lee el log de eventos, completo o filtrado por oc_id.

    Devuelve un DataFrame vacío con las columnas correctas si todavía no hay log.
    """
    df = _default_storage().read_eventos()
    if oc_id is None:
        return df
    if df.empty or "oc_id" not in df.columns:
        return pd.DataFrame(columns=_EVENTO_COLUMNS)
    return df[df["oc_id"] == oc_id].reset_index(drop=True)
