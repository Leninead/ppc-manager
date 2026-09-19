"""Capa de persistencia DEDICADA a M24 Innovation Board.

Sigue el mismo patrón que `core/forecast/persistence.py` (backend dormido
opt-in, transport HTTP inyectable, cache + invalidación), adaptado al dominio
del board de ideas: ideas + votos + comentarios + prototipos.

Identidad propia:
    - Flag de backend:     AGENCY_OS_INNOVATION_BACKEND
    - Tablas Supabase:     innovation_ideas / innovation_votos /
                           innovation_comentarios / innovation_prototipos
    - Layout local:        data/innovation/<entidad>.json
                           (ideas.json / votos.json / comentarios.json /
                            prototipos.json)

Infraestructura COMPARTIDA con el resto del Agency OS (a propósito):
    - Mismas env vars de credenciales: SUPABASE_URL / SUPABASE_KEY.
    - Mismo lugar de secrets: st.secrets["supabase"]["url" / "key"].
      Eso es infra (la instancia Supabase). Lo que NO se comparte es el flag
      de selección de backend ni las tablas destino.

API pública (helpers privados con _prefijo, snake_case, igual que el resto de
core/):
    _list_ideas(area=None, estado=None) -> list[dict]
    _get_idea(idea_id) -> dict
    _create_idea(payload) -> str            # devuelve idea_id
    _update_idea(idea_id, patch) -> None
    _list_votos(idea_id) -> list[dict]
    _upsert_voto(idea_id, votante, valor, razon) -> None   # 1 voto/persona, upsert
    _list_comentarios(idea_id) -> list[dict]
    _add_comentario(idea_id, autor, cuerpo) -> None
    _toggle_destacado(comentario_id, valor) -> None
    _list_prototipos(idea_id) -> list[dict]  # SIN html_content (liviano)
    _get_prototipo(prototipo_id) -> dict     # CON html_content
    _add_prototipo(idea_id, nombre, html_content, autor) -> None  # versiona

Reglas duras (heredadas del skill data-persistence-standard):
    - Cero lógica de negocio acá. Solo I/O.
    - Cero borrados automáticos. El usuario decide cuándo limpiar `data/`.
    - Lecturas cacheadas con @st.cache_data. Escrituras invalidan cache.
    - IDs: uuid4 en local; en Supabase deja que la DB genere el default.

Estado: el flag default es local. Supabase está DORMIDO hasta que:
    1) Se cree el schema (`scripts/sql/m24_innovation_schema.sql`) en Supabase.
    2) Se setee `AGENCY_OS_INNOVATION_BACKEND="supabase"` + creds en swap-day.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    # Permite usar este módulo en scripts standalone (testing) sin Streamlit.
    _HAS_STREAMLIT = False


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

from core.data_root import DATA_ROOT  # data root, configurable via AGENCY_OS_DATA_DIR

_INNOVATION_SUBDIR = "innovation"

_IDEAS_FILE = "ideas.json"
_VOTOS_FILE = "votos.json"
_COMENTARIOS_FILE = "comentarios.json"
_PROTOTIPOS_FILE = "prototipos.json"

_IDEAS_TABLE = "innovation_ideas"
_VOTOS_TABLE = "innovation_votos"
_COMENTARIOS_TABLE = "innovation_comentarios"
_PROTOTIPOS_TABLE = "innovation_prototipos"

_ESTADO_DEFAULT = "nueva"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _cache_data(func):
    """Aplica @st.cache_data si Streamlit está disponible. Si no, no-op."""
    if _HAS_STREAMLIT:
        return st.cache_data(show_spinner=False)(func)
    return func


def _invalidate(*funcs) -> None:
    """Limpia el cache de las funciones cacheadas dadas (no-op sin Streamlit)."""
    if not _HAS_STREAMLIT:
        return
    for f in funcs:
        if hasattr(f, "clear"):
            f.clear()


def _innovation_dir() -> Path:
    """Construye `data/innovation/` y lo crea si no existe."""
    base = DATA_ROOT / _INNOVATION_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Backend local — Fase 1 (JSON en disco bajo DATA_ROOT/innovation)
# ─────────────────────────────────────────────────────────────────────────────


class _LocalBackend:
    """Backend Fase 1: cuatro archivos JSON (uno por entidad) en disco local.

    NO cachea (el cacheo vive en los wrappers públicos). Lee el global
    DATA_ROOT en cada llamada para respetar el monkeypatch de tests.
    """

    def _read(self, fname: str) -> list[dict]:
        p = DATA_ROOT / _INNOVATION_SUBDIR / fname
        if not p.exists():
            return []
        return json.loads(p.read_text(encoding="utf-8"))

    def _write(self, fname: str, rows: list[dict]) -> None:
        base = _innovation_dir()
        (base / fname).write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── ideas ──────────────────────────────────────────────────────────────
    def list_ideas(self, area=None, estado=None) -> list[dict]:
        rows = self._read(_IDEAS_FILE)
        if area:
            rows = [r for r in rows if r.get("area") == area]
        if estado:
            rows = [r for r in rows if r.get("estado") == estado]
        return rows

    def get_idea(self, idea_id: str) -> dict:
        for r in self._read(_IDEAS_FILE):
            if r.get("id") == idea_id:
                return r
        return {}

    def create_idea(self, payload: dict) -> str:
        rows = self._read(_IDEAS_FILE)
        idea = dict(payload)
        idea["id"] = _new_id()
        idea.setdefault("estado", _ESTADO_DEFAULT)
        idea.setdefault("created_at", _now_iso())
        rows.append(idea)
        self._write(_IDEAS_FILE, rows)
        return idea["id"]

    def update_idea(self, idea_id: str, patch: dict) -> None:
        rows = self._read(_IDEAS_FILE)
        for r in rows:
            if r.get("id") == idea_id:
                r.update(patch)
                break
        self._write(_IDEAS_FILE, rows)

    # ── votos ──────────────────────────────────────────────────────────────
    def list_votos(self, idea_id: str) -> list[dict]:
        return [r for r in self._read(_VOTOS_FILE) if r.get("idea_id") == idea_id]

    def upsert_voto(self, idea_id, votante, valor, razon) -> None:
        rows = self._read(_VOTOS_FILE)
        for r in rows:
            if r.get("idea_id") == idea_id and r.get("votante") == votante:
                r["valor"] = valor
                r["razon"] = razon
                r["updated_at"] = _now_iso()
                self._write(_VOTOS_FILE, rows)
                return
        rows.append(
            {
                "id": _new_id(),
                "idea_id": idea_id,
                "votante": votante,
                "valor": valor,
                "razon": razon,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        )
        self._write(_VOTOS_FILE, rows)

    # ── comentarios ────────────────────────────────────────────────────────
    def list_comentarios(self, idea_id: str) -> list[dict]:
        return [
            r for r in self._read(_COMENTARIOS_FILE) if r.get("idea_id") == idea_id
        ]

    def add_comentario(self, idea_id, autor, cuerpo) -> None:
        rows = self._read(_COMENTARIOS_FILE)
        rows.append(
            {
                "id": _new_id(),
                "idea_id": idea_id,
                "autor": autor,
                "cuerpo": cuerpo,
                "destacado": False,
                "created_at": _now_iso(),
            }
        )
        self._write(_COMENTARIOS_FILE, rows)

    def toggle_destacado(self, comentario_id, valor) -> None:
        rows = self._read(_COMENTARIOS_FILE)
        for r in rows:
            if r.get("id") == comentario_id:
                r["destacado"] = bool(valor)
                break
        self._write(_COMENTARIOS_FILE, rows)

    # ── prototipos ─────────────────────────────────────────────────────────
    def list_prototipos(self, idea_id: str) -> list[dict]:
        out = []
        for r in self._read(_PROTOTIPOS_FILE):
            if r.get("idea_id") == idea_id:
                out.append({k: v for k, v in r.items() if k != "html_content"})
        return out

    def get_prototipo(self, prototipo_id: str) -> dict:
        for r in self._read(_PROTOTIPOS_FILE):
            if r.get("id") == prototipo_id:
                return r
        return {}

    def add_prototipo(self, idea_id, nombre, html_content, autor) -> None:
        rows = self._read(_PROTOTIPOS_FILE)
        existing = [
            r
            for r in rows
            if r.get("idea_id") == idea_id and r.get("nombre") == nombre
        ]
        version = max((r.get("version", 0) for r in existing), default=0) + 1
        rows.append(
            {
                "id": _new_id(),
                "idea_id": idea_id,
                "nombre": nombre,
                "version": version,
                "html_content": html_content,
                "autor": autor,
                "created_at": _now_iso(),
            }
        )
        self._write(_PROTOTIPOS_FILE, rows)


# ─────────────────────────────────────────────────────────────────────────────
# Backend Supabase — DORMIDO (cableado pero no encendido)
# ─────────────────────────────────────────────────────────────────────────────
#
# DDL en scripts/sql/m24_innovation_schema.sql. RLS ACTIVADA con policy
# permisiva para service_role. Encender recién en swap-day.


class _InnovationTransport:
    """Transport HTTP por defecto sobre la API PostgREST de Supabase.

    Aislado para que `_SupabaseBackend` sea testeable sin red: los tests
    inyectan un transport en memoria con la misma interfaz
    (get/post/patch/delete). `requests` se importa diferido (solo al
    instanciar) para no pagar el import si el backend activo es el local.
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

    def patch(self, table: str, params: dict, patch: dict) -> list[dict]:
        headers = dict(self._headers)
        headers["Prefer"] = "return=representation"
        r = self._requests.patch(
            f"{self._base}/{table}",
            params=params,
            json=patch,
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def delete(self, table: str, params: dict) -> list[dict]:
        headers = dict(self._headers)
        headers["Prefer"] = "return=representation"
        r = self._requests.delete(
            f"{self._base}/{table}", params=params, headers=headers, timeout=30
        )
        r.raise_for_status()
        return r.json()


class _SupabaseBackend:
    """Backend remoto Fase 2+: PostgREST sobre Supabase, SIN SDK.

    Dormido por default. Sólo se instancia desde `_get_backend()` cuando hay
    credenciales Y el flag `AGENCY_OS_INNOVATION_BACKEND` resuelto == "supabase".

    `transport` es inyectable (default: PostgREST sobre requests) → los tests
    pasan un fake en memoria sin tocar la red.
    """

    def __init__(self, url: str = "", key: str = "", transport=None):
        self._t = (
            transport if transport is not None else _InnovationTransport(url, key)
        )

    # ── ideas ──────────────────────────────────────────────────────────────
    def list_ideas(self, area=None, estado=None) -> list[dict]:
        params = {"select": "*", "order": "created_at.asc"}
        if area:
            params["area"] = f"eq.{area}"
        if estado:
            params["estado"] = f"eq.{estado}"
        return self._t.get(_IDEAS_TABLE, params)

    def get_idea(self, idea_id: str) -> dict:
        rows = self._t.get(
            _IDEAS_TABLE, {"id": f"eq.{idea_id}", "select": "*", "limit": "1"}
        )
        return rows[0] if rows else {}

    def create_idea(self, payload: dict) -> str:
        row = dict(payload)
        row.setdefault("estado", _ESTADO_DEFAULT)
        row.pop("id", None)  # id: la DB genera el default
        res = self._t.post(_IDEAS_TABLE, [row])
        return res[0]["id"] if res else ""

    def update_idea(self, idea_id: str, patch: dict) -> None:
        self._t.patch(_IDEAS_TABLE, {"id": f"eq.{idea_id}"}, dict(patch))

    # ── votos ──────────────────────────────────────────────────────────────
    def list_votos(self, idea_id: str) -> list[dict]:
        return self._t.get(
            _VOTOS_TABLE, {"idea_id": f"eq.{idea_id}", "select": "*"}
        )

    def upsert_voto(self, idea_id, votante, valor, razon) -> None:
        existing = self._t.get(
            _VOTOS_TABLE,
            {
                "idea_id": f"eq.{idea_id}",
                "votante": f"eq.{votante}",
                "select": "id",
                "limit": "1",
            },
        )
        if existing:
            self._t.patch(
                _VOTOS_TABLE,
                {"idea_id": f"eq.{idea_id}", "votante": f"eq.{votante}"},
                {"valor": valor, "razon": razon},
            )
        else:
            self._t.post(
                _VOTOS_TABLE,
                [
                    {
                        "idea_id": idea_id,
                        "votante": votante,
                        "valor": valor,
                        "razon": razon,
                    }
                ],
            )

    # ── comentarios ────────────────────────────────────────────────────────
    def list_comentarios(self, idea_id: str) -> list[dict]:
        return self._t.get(
            _COMENTARIOS_TABLE, {"idea_id": f"eq.{idea_id}", "select": "*"}
        )

    def add_comentario(self, idea_id, autor, cuerpo) -> None:
        self._t.post(
            _COMENTARIOS_TABLE,
            [
                {
                    "idea_id": idea_id,
                    "autor": autor,
                    "cuerpo": cuerpo,
                    "destacado": False,
                }
            ],
        )

    def toggle_destacado(self, comentario_id, valor) -> None:
        self._t.patch(
            _COMENTARIOS_TABLE,
            {"id": f"eq.{comentario_id}"},
            {"destacado": bool(valor)},
        )

    # ── prototipos ─────────────────────────────────────────────────────────
    def list_prototipos(self, idea_id: str) -> list[dict]:
        rows = self._t.get(
            _PROTOTIPOS_TABLE,
            {"idea_id": f"eq.{idea_id}", "select": "*", "order": "version.asc"},
        )
        return [{k: v for k, v in r.items() if k != "html_content"} for r in rows]

    def get_prototipo(self, prototipo_id: str) -> dict:
        rows = self._t.get(
            _PROTOTIPOS_TABLE,
            {"id": f"eq.{prototipo_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else {}

    def add_prototipo(self, idea_id, nombre, html_content, autor) -> None:
        existing = self._t.get(
            _PROTOTIPOS_TABLE,
            {"idea_id": f"eq.{idea_id}", "nombre": f"eq.{nombre}", "select": "version"},
        )
        version = max((r.get("version", 0) for r in existing), default=0) + 1
        self._t.post(
            _PROTOTIPOS_TABLE,
            [
                {
                    "idea_id": idea_id,
                    "nombre": nombre,
                    "version": version,
                    "html_content": html_content,
                    "autor": autor,
                }
            ],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Selector de backend — opt-in explícito (creds + flag), default local
# ─────────────────────────────────────────────────────────────────────────────


def _storage_config() -> "tuple[str, str] | None":
    """Credenciales Supabase si están configuradas; None → no hay creds.

    Orden: env (SUPABASE_URL/SUPABASE_KEY) primero, luego
    `st.secrets["supabase"]` (Streamlit Cloud). La infra Supabase es
    compartida (una instancia, varias tablas).
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


def _backend_flag() -> str:
    """Flag de selección de backend M24 Innovation Board (normalizado).

    Precedencia: env `AGENCY_OS_INNOVATION_BACKEND` GANA sobre secrets. Si la
    env no está seteada, lee el campo `innovation_backend` dentro de
    `[supabase]` en `st.secrets` — único lugar editable en swap-day sobre
    Streamlit Cloud.

    Nota: INDEPENDIENTE del flag de AH (`AGENCY_OS_AH_BACKEND`) y del de M31
    (`AGENCY_OS_FORECAST_BACKEND`).
    """
    env_flag = os.environ.get("AGENCY_OS_INNOVATION_BACKEND")
    if env_flag is not None:
        return env_flag.strip().lower()
    try:
        import streamlit as st

        sb = st.secrets.get("supabase")
        if sb:
            val = sb.get("innovation_backend")
            if val:
                return str(val).strip().lower()
    except Exception:
        pass
    return ""


def _innovation_opt_in() -> bool:
    """True solo si el operador habilitó explícitamente el backend Supabase.

    La mera presencia de credenciales NO activa el backend remoto. El swap
    productivo se hace seteando el flag a exactamente "supabase".
    """
    return _backend_flag() == "supabase"


_BACKEND: "_LocalBackend | _SupabaseBackend | None" = None


def _get_backend():
    """Devuelve el backend de persistencia activo (singleton por proceso).

    Selección opt-in explícito: devuelve `_SupabaseBackend` SOLO si hay
    credenciales (`_storage_config()`) Y el flag resuelto == "supabase"
    (`_innovation_opt_in()`). Si falta cualquiera de los dos → `_LocalBackend`.

    Consecuencia: al mergear a main sin flag, todo sigue local (cero regresión).
    """
    global _BACKEND
    if _BACKEND is None:
        if _innovation_opt_in():
            cfg = _storage_config()
            if cfg:
                _BACKEND = _SupabaseBackend(*cfg)
        if _BACKEND is None:
            _BACKEND = _LocalBackend()
    return _BACKEND


def _set_backend_for_testing(backend) -> None:
    """Inyecta un backend alternativo (tests). Pasar None resetea el singleton
    para que la próxima llamada a `_get_backend()` lo reconstruya."""
    global _BACKEND
    _BACKEND = backend


# ─────────────────────────────────────────────────────────────────────────────
# Migración defensiva de estados (en el punto de lectura, sin script aparte)
# ─────────────────────────────────────────────────────────────────────────────

# El estado "en revisión" (F2) pasó a llamarse "en debate" en F3. Se mapea al
# LEER, para no requerir un backfill en disco/DB. Los otros 3 estados viejos
# (nueva/aprobada/descartada) siguen siendo válidos.
_ESTADO_MIGRATION = {"en revisión": "en debate"}


def _migrate_estado(idea: dict) -> dict:
    """Mapea estados legacy a los actuales. Devuelve copia si hubo cambio."""
    if idea and idea.get("estado") in _ESTADO_MIGRATION:
        idea = dict(idea)
        idea["estado"] = _ESTADO_MIGRATION[idea["estado"]]
    return idea


# ─────────────────────────────────────────────────────────────────────────────
# API pública — wrappers con cache + invalidación
# ─────────────────────────────────────────────────────────────────────────────


@_cache_data
def _list_ideas(area=None, estado=None) -> list[dict]:
    """Lista ideas (estados migrados), filtradas opcionalmente por area/estado.

    El filtro de estado se aplica DESPUÉS de la migración para que una idea
    legacy ("en revisión" → "en debate") se filtre por su estado actual.
    """
    rows = [_migrate_estado(r) for r in _get_backend().list_ideas(area, None)]
    if estado:
        rows = [r for r in rows if r.get("estado") == estado]
    return rows


@_cache_data
def _get_idea(idea_id: str) -> dict:
    """Devuelve una idea por id (estado migrado), o {} si no existe."""
    return _migrate_estado(_get_backend().get_idea(idea_id))


def _create_idea(payload: dict) -> str:
    """Crea una idea nueva con los defaults de F3. Devuelve su idea_id."""
    payload = dict(payload)
    payload.setdefault("asignado_a", "")
    payload.setdefault("razon_descarte", "")
    payload.setdefault("estado_updated_at", _now_iso())
    idea_id = _get_backend().create_idea(payload)
    _invalidate(_list_ideas, _get_idea)
    return idea_id


def _update_idea(idea_id: str, patch: dict) -> None:
    """Aplica un patch parcial. Si toca 'estado', sella estado_updated_at.

    El sellado del timestamp NO se delega a la UI — vive acá para que cualquier
    cambio de estado quede fechado sí o sí.
    """
    patch = dict(patch)
    if "estado" in patch:
        patch["estado_updated_at"] = _now_iso()
    _get_backend().update_idea(idea_id, patch)
    _invalidate(_list_ideas, _get_idea)


@_cache_data
def _list_votos(idea_id: str) -> list[dict]:
    """Lista los votos de una idea."""
    return _get_backend().list_votos(idea_id)


def _upsert_voto(idea_id: str, votante: str, valor: int, razon: str) -> None:
    """Registra o actualiza el voto de una persona (1 voto/persona).

    La razón es OBLIGATORIA — un voto sin razón levanta ValueError.
    """
    if razon is None or not str(razon).strip():
        raise ValueError("La razón del voto es obligatoria.")
    _get_backend().upsert_voto(idea_id, votante, int(valor), razon)
    _invalidate(_list_votos)


@_cache_data
def _list_comentarios(idea_id: str) -> list[dict]:
    """Lista los comentarios de una idea."""
    return _get_backend().list_comentarios(idea_id)


def _add_comentario(idea_id: str, autor: str, cuerpo: str) -> None:
    """Agrega un comentario a una idea. Invalida cache de lecturas."""
    _get_backend().add_comentario(idea_id, autor, cuerpo)
    _invalidate(_list_comentarios)


def _toggle_destacado(comentario_id: str, valor: bool) -> None:
    """Marca/desmarca un comentario como destacado. Invalida cache."""
    _get_backend().toggle_destacado(comentario_id, valor)
    _invalidate(_list_comentarios)


@_cache_data
def _list_prototipos(idea_id: str) -> list[dict]:
    """Lista prototipos de una idea SIN html_content (liviano, para selector)."""
    return _get_backend().list_prototipos(idea_id)


@_cache_data
def _get_prototipo(prototipo_id: str) -> dict:
    """Devuelve un prototipo completo (CON html_content), o {} si no existe."""
    return _get_backend().get_prototipo(prototipo_id)


def _add_prototipo(idea_id: str, nombre: str, html_content: str, autor: str) -> None:
    """Agrega un prototipo. Si (idea_id, nombre) ya existe, versiona (max+1)."""
    _get_backend().add_prototipo(idea_id, nombre, html_content, autor)
    _invalidate(_list_prototipos)
