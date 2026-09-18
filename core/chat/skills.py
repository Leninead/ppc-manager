"""Skills del chat: las que sube un admin desde Sistema, guardadas por la app.

Una skill es conocimiento que el modelo lee sólo cuando decide que aplica: el
formato de un reporte, cómo se lee una métrica, qué hace la agencia cuando un
cliente discute el ACoS. Vive acá y no en el repo del provider porque la escribe
quien sabe del tema, y porque cambiarla no debería necesitar un deploy.

Todo el registro es UN documento de config (`data/ai/chat-skills/registry-v1.json`)
a través de `core.persistence`. Un documento y no uno por skill porque la
pantalla las lista siempre juntas y cada turno de chat manda las prendidas: dos
lecturas cacheadas en vez de N.

La validación de acá es un espejo deliberado de la del provider
(`app/skills_store.py`). Duplicarla es a propósito: el provider tiene que
rechazar lo que le llegue venga de donde venga, y esta pantalla tiene que poder
decirle a un humano qué está mal ANTES de guardarlo, no después de un 422 en
mitad de una conversación.

Lo que NO hace este módulo: decidir si una skill es buena. Una skill es texto que
el modelo obedece, así que quien la sube está cambiando cómo le contesta el chat
a todos los AMs. Por eso la pantalla es sólo para admin, guarda quién la subió y
cuándo, y muestra el texto tal cual quedó.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.persistence import _load_config, _save_config

AREA = "ai"
MODULO = "chat-skills"
REGISTRY = "registry"
REGISTRY_VERSION = 1

ENTRY_FILE = "SKILL.md"

# Espejo de app/skills_store.py: el nombre termina siendo un directorio y una
# regla de permiso, así que se lo ata a lo que los dos aceptan sin comillas.
_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Nombres que ya usa Amazon: una skill subida no puede taparlos.
RESERVED = frozenset({"ads-reporting", "ama-account-context-identifiers"})

MAX_SKILLS = 8
MAX_FILES = 12
MAX_CHARS = 40_000


class SkillRejected(ValueError):
    """Lo que subieron no puede guardarse, y el motivo se le muestra a la persona."""


@dataclass
class Skill:
    name: str
    description: str
    files: list[dict] = field(default_factory=list)   # [{"path", "content"}]
    enabled: bool = True
    uploaded_by: str = ""
    uploaded_at: str = ""

    @property
    def chars(self) -> int:
        return sum(len(f.get("content") or "") for f in self.files)

    def payload(self) -> dict:
        """Lo que viaja al provider: nombre y archivos, nada del registro."""
        return {"name": self.name,
                "files": [{"path": f["path"], "content": f["content"]} for f in self.files]}


def parse_front_matter(text: str) -> dict:
    """`name` y `description` del encabezado. Vacío si no hay encabezado.

    El SDK dispara una skill por su `name`, y decide si aplica leyendo su
    `description`: son los dos campos que hacen que una skill exista o no.
    """
    if not text.startswith("---"):
        return {}
    head, sep, _ = text[3:].partition("\n---")
    if not sep:
        return {}
    meta: dict = {}
    for line in head.strip().splitlines():
        key, colon, value = line.partition(":")
        if colon:
            meta[key.strip()] = value.strip()
    return meta


def _validate(skill: Skill) -> None:
    if not _NAME.match(skill.name or ""):
        raise SkillRejected(
            f"El nombre «{skill.name}» no sirve: sólo minúsculas, números y guiones, "
            "sin empezar ni terminar con guion.")
    if skill.name in RESERVED:
        raise SkillRejected(f"«{skill.name}» es el nombre de una skill de Amazon.")
    if not skill.description:
        raise SkillRejected(
            "Falta `description` en el encabezado. Es el único texto que el chat lee "
            "para saber si esta skill aplica: sin eso no se usa nunca.")
    if not skill.files:
        raise SkillRejected("El archivo llegó vacío.")
    if len(skill.files) > MAX_FILES:
        raise SkillRejected(f"Son más de {MAX_FILES} archivos.")

    seen = set()
    for item in skill.files:
        path = str(item.get("path") or "")
        parts = path.split("/")
        if len(parts) < 2 or parts[0] != skill.name:
            raise SkillRejected(f"«{path}» tiene que colgar de la carpeta {skill.name}/.")
        for segment in parts:
            if not _SEGMENT.match(segment):
                raise SkillRejected(f"«{path}» tiene un tramo de ruta que no se puede usar.")
        if path in seen:
            raise SkillRejected(f"«{path}» aparece dos veces.")
        seen.add(path)

    if f"{skill.name}/{ENTRY_FILE}" not in seen:
        raise SkillRejected(f"Falta {skill.name}/{ENTRY_FILE}, que es el archivo principal.")
    if skill.chars > MAX_CHARS:
        raise SkillRejected(
            f"Son {skill.chars:,} caracteres y el tope es {MAX_CHARS:,}. "
            "Una skill que no entra probablemente tendría que ser dos.")


def from_markdown(filename: str, text: str) -> Skill:
    """Una skill de un solo archivo. El nombre sale del encabezado, no del archivo."""
    meta = parse_front_matter(text)
    name = meta.get("name") or ""
    if not name:
        raise SkillRejected(
            "El archivo no tiene encabezado con `name`. Un SKILL.md arranca con "
            "--- name: … / description: … --- y recién ahí el texto.")
    skill = Skill(name=name, description=meta.get("description", ""),
                  files=[{"path": f"{name}/{ENTRY_FILE}", "content": text}])
    _validate(skill)
    return skill


def from_zip(data: bytes) -> Skill:
    """Una skill con archivos hermanos. La carpeta de arriba es el nombre."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillRejected("Ese .zip no se puede abrir.") from exc

    files: list[dict] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = info.filename.replace("\\", "/").lstrip("./")
        if not path or "__MACOSX" in path:
            continue
        if info.file_size > MAX_CHARS:
            raise SkillRejected(f"«{path}» solo ya pasa el tope de {MAX_CHARS:,} caracteres.")
        try:
            content = archive.read(info).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillRejected(f"«{path}» no es texto UTF-8.") from exc
        files.append({"path": path, "content": content})

    if not files:
        raise SkillRejected("El .zip no trae archivos.")
    roots = {f["path"].split("/")[0] for f in files}
    if len(roots) != 1:
        raise SkillRejected(
            "El .zip tiene que traer UNA carpeta arriba de todo, con el nombre de la skill.")
    name = roots.pop()
    entry = next((f for f in files if f["path"] == f"{name}/{ENTRY_FILE}"), None)
    if entry is None:
        raise SkillRejected(f"Falta {name}/{ENTRY_FILE} adentro del .zip.")
    meta = parse_front_matter(entry["content"])
    declared = meta.get("name") or ""
    if declared and declared != name:
        raise SkillRejected(
            f"La carpeta se llama «{name}» y el encabezado dice «{declared}». "
            "Tienen que ser iguales o la skill no se dispara nunca.")
    skill = Skill(name=name, description=meta.get("description", ""), files=files)
    _validate(skill)
    return skill


def parse_upload(filename: str, data: bytes) -> Skill:
    """Una skill desde lo que la persona arrastró: un .md o un .zip."""
    lower = (filename or "").lower()
    if lower.endswith(".zip"):
        return from_zip(data)
    try:
        return from_markdown(filename, data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise SkillRejected("El archivo no es texto UTF-8.") from exc


# ── registro ───────────────────────────────────────────────────────────────
def _read() -> dict:
    return _load_config(AREA, MODULO, REGISTRY, REGISTRY_VERSION) or {}


def _write(skills: dict[str, Skill]) -> None:
    _save_config({"version": REGISTRY_VERSION,
                  "skills": {name: {"name": s.name, "description": s.description,
                                    "files": s.files, "enabled": s.enabled,
                                    "uploaded_by": s.uploaded_by,
                                    "uploaded_at": s.uploaded_at}
                             for name, s in skills.items()}},
                 AREA, MODULO, REGISTRY, REGISTRY_VERSION)


def load() -> dict[str, Skill]:
    """Todas las skills subidas, por nombre. Una entrada rota no tumba el resto."""
    out: dict[str, Skill] = {}
    for name, raw in (_read().get("skills") or {}).items():
        if not isinstance(raw, dict):
            continue
        out[name] = Skill(name=raw.get("name") or name,
                          description=raw.get("description", ""),
                          files=list(raw.get("files") or []),
                          enabled=bool(raw.get("enabled", True)),
                          uploaded_by=raw.get("uploaded_by", ""),
                          uploaded_at=raw.get("uploaded_at", ""))
    return out


def save(skill: Skill, *, uploaded_by: str = "") -> None:
    """Guarda o reemplaza. Reemplazar conserva si estaba prendida."""
    _validate(skill)
    current = load()
    if skill.name not in current and len(current) >= MAX_SKILLS:
        raise SkillRejected(
            f"Ya hay {MAX_SKILLS} skills. Apagá o borrá una antes de subir otra.")
    if skill.name in current:
        skill.enabled = current[skill.name].enabled
    skill.uploaded_by = uploaded_by
    skill.uploaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    current[skill.name] = skill
    _write(current)


def set_enabled(name: str, enabled: bool) -> None:
    current = load()
    if name in current:
        current[name].enabled = enabled
        _write(current)


def remove(name: str) -> None:
    current = load()
    if current.pop(name, None) is not None:
        _write(current)


def enabled_payload() -> list[dict]:
    """Lo que se manda con un turno de chat. Nunca levanta: un registro roto
    tiene que costar una skill, no la conversación."""
    try:
        return [s.payload() for s in load().values() if s.enabled]
    except Exception:  # noqa: BLE001 — ver el docstring
        return []
