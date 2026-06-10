"""Capa de persistencia del sistema Sales Proposals.

Diseñada para migrar a Supabase sin tocar consumidores. La clase abstracta
`ProposalStorage` define el contrato; `LocalJsonStorage` implementa Fase 1
(JSON local + Parquet append-only para votes).

Cuando aparezca `SupabaseStorage`, el swap es transparente — solo cambia
`_default_storage()`.

API pública (11 helpers):
    load_catalog() -> dict
    list_proposals(client_filter, status_filter, archetype_filter) -> list[dict]
    get_proposal(proposal_id, version=None) -> dict | None
    save_proposal(proposal) -> dict
    delete_proposal(proposal_id, hard_delete=False) -> bool
    list_templates() -> list[dict]
    get_template(archetype) -> dict | None
    instantiate_proposal_from_template(archetype, client_name, language, sales_director) -> dict
    log_interested_vote(module_id, voter_name, proposal_id=None) -> dict
    get_module_vote_count(module_id) -> int
    get_seed_proposal(seed_id) -> dict | None

Reglas duras:
- Cero lógica de negocio acá. Solo CRUD y validación contra el schema.
- Auto-versionado: cada save_proposal incrementa la version del id.
- Soft delete: archivar = status='archived', no borra archivos.
- Validación obligatoria en save_proposal: 8 FIXED presentes, FK enforcement.
"""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.proposal_paths import (
    CATALOG_FILE,
    PROPOSALS_DIR,
    SEED_DIR,
    TEMPLATES_DIR,
    VOTES_LOG_FILE,
    ensure_dirs,
    proposal_file,
    seed_file,
    template_file,
)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Abstract storage contract
# ─────────────────────────────────────────────────────────────────────────────


class ProposalStorage(ABC):
    """Contrato de almacenamiento. Implementar para cambiar backend (local/SQLite/Supabase)."""

    # — Proposals —
    @abstractmethod
    def write_proposal(self, proposal: dict) -> Path | str: ...

    @abstractmethod
    def read_proposal(self, proposal_id: str, version: int) -> dict | None: ...

    @abstractmethod
    def list_proposal_files(self) -> Iterable[dict]:
        """Itera todas las propuestas. Cada elemento es el dict completo."""
        ...

    @abstractmethod
    def max_version_for(self, proposal_id: str) -> int:
        """Devuelve la version más alta para un id. 0 si no existe."""
        ...

    # — Votes —
    @abstractmethod
    def append_vote(self, vote_row: dict) -> None: ...

    @abstractmethod
    def read_votes(self) -> pd.DataFrame: ...


class LocalJsonStorage(ProposalStorage):
    """Fase 1: JSON local + Parquet append-only para votes."""

    # — Proposals —

    def write_proposal(self, proposal: dict) -> Path:
        ensure_dirs()
        path = proposal_file(proposal["id"], proposal["version"])
        _write_json(path, proposal)
        return path

    def read_proposal(self, proposal_id: str, version: int) -> dict | None:
        return _read_json(proposal_file(proposal_id, version))

    def list_proposal_files(self) -> Iterable[dict]:
        if not PROPOSALS_DIR.exists():
            return
        for f in sorted(PROPOSALS_DIR.glob("*__v*.json")):
            data = _read_json(f)
            if data is not None:
                yield data

    def max_version_for(self, proposal_id: str) -> int:
        if not PROPOSALS_DIR.exists():
            return 0
        max_v = 0
        for f in PROPOSALS_DIR.glob(f"{proposal_id}__v*.json"):
            stem = f.stem  # '<id>__v<N>'
            try:
                v_str = stem.split("__v")[-1]
                v = int(v_str)
                if v > max_v:
                    max_v = v
            except (ValueError, IndexError):
                continue
        return max_v

    # — Votes —

    def append_vote(self, vote_row: dict) -> None:
        ensure_dirs()
        new_df = pd.DataFrame([vote_row])
        if VOTES_LOG_FILE.exists():
            existing = pd.read_parquet(VOTES_LOG_FILE)
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df
        combined.to_parquet(VOTES_LOG_FILE, compression="snappy", index=False)

    def read_votes(self) -> pd.DataFrame:
        if not VOTES_LOG_FILE.exists():
            return pd.DataFrame(
                columns=["id", "module_id", "voter_name", "voted_at", "proposal_id"]
            )
        return pd.read_parquet(VOTES_LOG_FILE)


# ─────────────────────────────────────────────────────────────────────────────
# Supabase storage (Fase 2) — PostgREST vía requests (sin SDK)
# ─────────────────────────────────────────────────────────────────────────────

_PROPOSALS_TABLE = "proposals"
_VOTES_TABLE = "proposal_votes"
_VOTE_COLUMNS = ["id", "module_id", "voter_name", "voted_at", "proposal_id"]


class _RequestsTransport:
    """Transport HTTP por defecto sobre la API PostgREST de Supabase.

    Aislado en su propia clase para que `SupabaseStorage` sea testeable sin red:
    los tests inyectan un transport en memoria con la misma interfaz (get/post).
    No se importa `requests` a nivel módulo (solo al instanciar) para no pagar el
    import si el backend activo es el local.
    """

    def __init__(self, url: str, key: str):
        import requests  # import diferido: solo si se usa el backend Supabase

        self._requests = requests
        self._base = url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def get(self, table: str, params: dict) -> list[dict]:
        r = self._requests.get(
            f"{self._base}/{table}", params=params, headers=self._headers, timeout=30
        )
        r.raise_for_status()
        return r.json()

    def post(self, table: str, rows: list[dict], upsert: bool = False) -> list[dict]:
        headers = dict(self._headers)
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        headers["Prefer"] = prefer
        r = self._requests.post(
            f"{self._base}/{table}", json=rows, headers=headers, timeout=30
        )
        r.raise_for_status()
        return r.json()


class SupabaseStorage(ProposalStorage):
    """Fase 2: persistencia en Supabase vía PostgREST (REST puro, sin SDK).

    Esquema SQL (ejecutar una vez en el proyecto Supabase antes de wirear):

        create table if not exists proposals (
            id          text        not null,
            version     integer     not null,
            client_name text,
            status      text,
            archetype   text,
            updated_at  text,
            data        jsonb       not null,
            primary key (id, version)
        );
        create index if not exists proposals_id_idx on proposals (id);

        create table if not exists proposal_votes (
            id          text        primary key,
            module_id   text        not null,
            voter_name  text,
            voted_at    text,
            proposal_id text
        );

    El JSON completo de la propuesta vive en `data` (jsonb); las columnas
    client_name/status/archetype/updated_at se denormalizan solo para acelerar
    filtros futuros (hoy `list_proposals` filtra en Python sobre `data`).

    `transport` es inyectable (default: PostgREST sobre requests) → los tests
    pasan un fake en memoria sin tocar la red.
    """

    def __init__(self, url: str = "", key: str = "", transport=None):
        self._t = transport if transport is not None else _RequestsTransport(url, key)

    # — Proposals —

    def write_proposal(self, proposal: dict) -> str:
        row = {
            "id": proposal["id"],
            "version": proposal["version"],
            "client_name": proposal.get("client_name", ""),
            "status": proposal.get("status", ""),
            "archetype": proposal.get("archetype", ""),
            "updated_at": proposal.get("updated_at", ""),
            "data": proposal,
        }
        # upsert por PK (id, version): idempotente si se reintenta el mismo save.
        self._t.post(_PROPOSALS_TABLE, [row], upsert=True)
        return f"{proposal['id']}__v{proposal['version']}"

    def read_proposal(self, proposal_id: str, version: int) -> dict | None:
        rows = self._t.get(
            _PROPOSALS_TABLE,
            {
                "id": f"eq.{proposal_id}",
                "version": f"eq.{version}",
                "select": "data",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return rows[0]["data"]

    def list_proposal_files(self) -> Iterable[dict]:
        rows = self._t.get(_PROPOSALS_TABLE, {"select": "data"})
        for r in rows:
            data = r.get("data")
            if data is not None:
                yield data

    def max_version_for(self, proposal_id: str) -> int:
        rows = self._t.get(
            _PROPOSALS_TABLE,
            {
                "id": f"eq.{proposal_id}",
                "select": "version",
                "order": "version.desc",
                "limit": "1",
            },
        )
        if not rows:
            return 0
        return int(rows[0]["version"])

    # — Votes —

    def append_vote(self, vote_row: dict) -> None:
        self._t.post(_VOTES_TABLE, [vote_row])

    def read_votes(self) -> pd.DataFrame:
        rows = self._t.get(_VOTES_TABLE, {"select": "*"})
        if not rows:
            return pd.DataFrame(columns=_VOTE_COLUMNS)
        return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Default storage selector
# ─────────────────────────────────────────────────────────────────────────────


_STORAGE: ProposalStorage | None = None


def _storage_config() -> tuple[str, str] | None:
    """Credenciales Supabase si están configuradas; None → backend local.

    Orden: variables de entorno (SUPABASE_URL/SUPABASE_KEY) primero, luego
    `st.secrets["supabase"]` (Streamlit Cloud). El acceso a st.secrets va con
    import diferido + try/except para no romper fuera de un runtime Streamlit
    (tests, scripts) ni acoplar este módulo a streamlit.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return url, key
    try:
        import streamlit as st

        sb = st.secrets.get("supabase")
        if sb and sb.get("url") and sb.get("key"):
            return sb["url"], sb["key"]
    except Exception:
        pass
    return None


def _default_storage() -> ProposalStorage:
    global _STORAGE
    if _STORAGE is None:
        cfg = _storage_config()
        _STORAGE = SupabaseStorage(*cfg) if cfg else LocalJsonStorage()
    return _STORAGE


def _set_storage_for_testing(storage: ProposalStorage) -> None:
    """Permite a los tests inyectar un storage alternativo. NO usar en producción."""
    global _STORAGE
    _STORAGE = storage


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo y templates (lectura solamente — son versionados en git)
# ─────────────────────────────────────────────────────────────────────────────


def load_catalog() -> dict:
    """Lee el catálogo canónico. Lanza FileNotFoundError si no existe."""
    data = _read_json(CATALOG_FILE)
    if data is None:
        raise FileNotFoundError(f"Catálogo no encontrado en {CATALOG_FILE}")
    return data


def _catalog_module_index() -> dict[str, dict]:
    """Construye un dict {module_id: module_def} para lookups rápidos."""
    catalog = load_catalog()
    return {m["module_id"]: m for m in catalog["modules"]}


def list_templates() -> list[dict]:
    """Lista todos los templates disponibles ordenados por archetype."""
    if not TEMPLATES_DIR.exists():
        return []
    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        data = _read_json(f)
        if data is not None:
            templates.append(data)
    return templates


def get_template(archetype: str) -> dict | None:
    """Lee un template por arquetipo. Devuelve None si no existe (ej. archetype='custom')."""
    try:
        path = template_file(archetype)
    except ValueError:
        return None
    return _read_json(path)


# ─────────────────────────────────────────────────────────────────────────────
# Propuestas — CRUD
# ─────────────────────────────────────────────────────────────────────────────


def _validate_proposal(proposal: dict) -> None:
    """Valida estructura mínima + reglas FK. Lanza ValueError con mensaje claro."""
    required_top = {
        "id",
        "version",
        "client_name",
        "client_industry",
        "language",
        "archetype",
        "status",
        "created_by",
        "created_at",
        "updated_at",
        "blocks",
    }
    missing = required_top - proposal.keys()
    if missing:
        raise ValueError(f"Faltan campos en Proposal: {sorted(missing)}")

    if proposal["language"] not in {"en", "es"}:
        raise ValueError(f"language inválido: {proposal['language']}")

    valid_archetypes = {"launch", "scale_seo", "defense", "cvr", "custom"}
    if proposal["archetype"] not in valid_archetypes:
        raise ValueError(f"archetype inválido: {proposal['archetype']}")

    valid_statuses = {"draft", "ready_for_review", "sent", "won", "lost", "archived"}
    if proposal["status"] not in valid_statuses:
        raise ValueError(f"status inválido: {proposal['status']}")

    blocks = proposal["blocks"]
    if not isinstance(blocks, list):
        raise ValueError("blocks debe ser una lista")

    # FK enforcement: cada module_id de cada block debe existir en el catálogo.
    catalog_index = _catalog_module_index()
    fixed_ids_required = {
        mid
        for mid, mod in catalog_index.items()
        if mod.get("tier") == "fixed"
    }
    block_module_ids = []
    for i, block in enumerate(blocks):
        for k in ("id", "module_id", "proposal_id", "is_fixed", "data"):
            if k not in block:
                raise ValueError(f"Block #{i}: falta campo '{k}'")
        if block["proposal_id"] != proposal["id"]:
            raise ValueError(
                f"Block #{i}: proposal_id ({block['proposal_id']}) no matchea con Proposal.id ({proposal['id']})"
            )
        mid = block["module_id"]
        if mid not in catalog_index:
            raise ValueError(
                f"Block #{i}: module_id '{mid}' no existe en el catálogo"
            )
        catalog_tier = catalog_index[mid].get("tier")
        if block["is_fixed"] and catalog_tier != "fixed":
            raise ValueError(
                f"Block #{i}: is_fixed=True pero catalog.tier='{catalog_tier}' (no fixed) para module_id '{mid}'"
            )
        # copy_overrides solo puede tener keys 'en' y 'es'
        overrides = block.get("copy_overrides", {})
        if overrides:
            bad_keys = set(overrides.keys()) - {"en", "es"}
            if bad_keys:
                raise ValueError(
                    f"Block #{i}: copy_overrides tiene keys inválidos {sorted(bad_keys)}; permitidos: en, es"
                )
        block_module_ids.append(mid)

    # Regla: todos los FIXED deben estar presentes
    fixed_in_proposal = {
        mid for mid in block_module_ids if catalog_index[mid].get("tier") == "fixed"
    }
    missing_fixed = fixed_ids_required - fixed_in_proposal
    if missing_fixed:
        raise ValueError(
            f"Proposal debe incluir todos los módulos FIXED. Faltantes: {sorted(missing_fixed)}"
        )


def save_proposal(proposal: dict) -> dict:
    """Guarda una propuesta con auto-versionado.

    - Si proposal['id'] no existe en disco → escribe con version=1.
    - Si existe → escribe con version=(max_actual+1).
    - Actualiza updated_at automáticamente.
    - Valida estructura y FK antes de escribir.

    Returns:
        El dict tal como fue persistido (con version e updated_at actualizados).
    """
    storage = _default_storage()

    proposal = dict(proposal)  # shallow copy para no mutar al caller

    if not proposal.get("id"):
        proposal["id"] = _new_uuid()

    if not proposal.get("created_at"):
        proposal["created_at"] = _now_iso()

    # Auto-version: max existente + 1
    current_max = storage.max_version_for(proposal["id"])
    proposal["version"] = current_max + 1
    proposal["updated_at"] = _now_iso()

    _validate_proposal(proposal)
    storage.write_proposal(proposal)
    return proposal


def get_proposal(proposal_id: str, version: int | None = None) -> dict | None:
    """Lee una propuesta. Si version es None, devuelve la versión más alta."""
    storage = _default_storage()
    if version is None:
        version = storage.max_version_for(proposal_id)
        if version == 0:
            return None
    return storage.read_proposal(proposal_id, version)


def list_proposals(
    client_filter: str | None = None,
    status_filter: str | None = None,
    archetype_filter: str | None = None,
) -> list[dict]:
    """Lista todas las propuestas con filtros opcionales.

    Devuelve solo la última versión de cada id (no muestra historial completo).
    """
    storage = _default_storage()
    latest_by_id: dict[str, dict] = {}
    for prop in storage.list_proposal_files():
        pid = prop.get("id")
        if not pid:
            continue
        prev = latest_by_id.get(pid)
        if prev is None or prop.get("version", 0) > prev.get("version", 0):
            latest_by_id[pid] = prop

    results = list(latest_by_id.values())

    if client_filter:
        results = [p for p in results if p.get("client_name") == client_filter]
    if status_filter:
        results = [p for p in results if p.get("status") == status_filter]
    if archetype_filter:
        results = [p for p in results if p.get("archetype") == archetype_filter]

    return sorted(results, key=lambda p: p.get("updated_at", ""), reverse=True)


def delete_proposal(proposal_id: str, hard_delete: bool = False) -> bool:
    """Borra (soft o hard) una propuesta.

    - hard_delete=False (default): marca status='archived' en la versión más alta.
      Lanza una versión nueva con status='archived'.
    - hard_delete=True: borra TODOS los archivos de versiones de ese proposal_id del disco.

    Returns:
        True si la operación se realizó. False si el proposal_id no existe.
    """
    if hard_delete:
        if not PROPOSALS_DIR.exists():
            return False
        deleted_any = False
        for f in PROPOSALS_DIR.glob(f"{proposal_id}__v*.json"):
            f.unlink()
            deleted_any = True
        return deleted_any

    # Soft delete
    current = get_proposal(proposal_id)
    if current is None:
        return False
    archived = dict(current)
    archived["status"] = "archived"
    save_proposal(archived)  # bumpea version y persiste
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Template instantiation
# ─────────────────────────────────────────────────────────────────────────────


def instantiate_proposal_from_template(
    archetype: str,
    client_name: str,
    language: str,
    sales_director: str,
) -> dict:
    """Crea (en memoria, NO persiste) una Proposal a partir del template del arquetipo.

    Returns:
        dict Proposal listo para editar y luego guardar con save_proposal().

    Raises:
        ValueError si archetype no tiene template (ej. 'custom').
    """
    template = get_template(archetype)
    if template is None:
        raise ValueError(
            f"No hay template para archetype='{archetype}'. "
            f"Para arquetipo 'custom', construir la propuesta manualmente."
        )

    catalog_index = _catalog_module_index()
    proposal_id = _new_uuid()
    now = _now_iso()

    blocks = []
    for module_id in template["default_blocks"]:
        if module_id not in catalog_index:
            raise ValueError(
                f"Template '{archetype}' referencia module_id inexistente: '{module_id}'"
            )
        module_def = catalog_index[module_id]
        blocks.append(
            {
                "id": _new_uuid(),
                "module_id": module_id,
                "proposal_id": proposal_id,
                "is_fixed": module_def["tier"] == "fixed",
                "data": {},
                "copy_overrides": {},
            }
        )

    return {
        "id": proposal_id,
        "version": 1,
        "client_name": client_name,
        "client_industry": "",
        "language": language,
        "archetype": archetype,
        "status": "draft",
        "created_by": sales_director,
        "created_at": now,
        "updated_at": now,
        "blocks": blocks,
        "meta": {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Votes — log append-only
# ─────────────────────────────────────────────────────────────────────────────


def log_interested_vote(
    module_id: str,
    voter_name: str,
    proposal_id: str | None = None,
) -> dict:
    """Registra un voto 'Marcar como interesado' en el log append-only.

    Returns:
        El dict de la fila persistida.

    Raises:
        ValueError si module_id no existe en el catálogo.
    """
    catalog_index = _catalog_module_index()
    if module_id not in catalog_index:
        raise ValueError(f"module_id '{module_id}' no existe en el catálogo")

    row = {
        "id": _new_uuid(),
        "module_id": module_id,
        "voter_name": voter_name,
        "voted_at": _now_iso(),
        "proposal_id": proposal_id or "",
    }
    _default_storage().append_vote(row)
    return row


def get_module_vote_count(module_id: str) -> int:
    """Cuenta cuántos votos tiene un module_id en el log."""
    df = _default_storage().read_votes()
    if df.empty or "module_id" not in df.columns:
        return 0
    return int((df["module_id"] == module_id).sum())


# ─────────────────────────────────────────────────────────────────────────────
# Seed proposals (referencia histórica)
# ─────────────────────────────────────────────────────────────────────────────


def get_seed_proposal(seed_id: str) -> dict | None:
    """Lee una propuesta semilla por su id (ej: 'sunny_zebra'). Solo referencia interna."""
    return _read_json(seed_file(seed_id))
