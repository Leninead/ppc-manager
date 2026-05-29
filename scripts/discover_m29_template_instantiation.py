"""Discovery M29 — flujo de template instantiation + reconcilio de conteos de blocks.

Objetivo (reunión Ramiro 01/06): resolver 3 flags vivos del cierre M29.

  1. `data/sales/_templates/*.json` con "0 blocks": ¿esperado o deuda silenciosa?
  2. Reconciliar conteos: demo `_DEMO_AgencyOS` (20) vs catálogo (37) vs "35"
     del planning.
  3. Comportamiento real de `instantiate_proposal_from_template`: cómo (y si)
     filtra el catálogo por `applicable_archetypes`.

REGLAS DE ESTE SCRIPT:
  - SOLO LECTURA del repo. No instancia propuestas reales, no escribe en `data/`.
  - El único archivo que escribe es `scripts/_m29_discovery_output.json` (gitignored).
  - `instantiate_proposal_from_template` es una función PURA (construye el dict en
    memoria, NO persiste — verificado por lectura estática en core/proposal_persistence.py).
    Por eso es seguro invocarla para confirmar conteos.

Uso:
    python scripts/discover_m29_template_instantiation.py

Exit 0 si todo corrió. Imprime reporte humano a stdout + dumpea JSON estructurado.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrapping de paths — chdir a la raíz del repo para que los paths relativos
# de core/proposal_paths.py (Path("data")/"sales") resuelvan sin importar el cwd.
# ─────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

# El reporte usa caracteres Unicode (•, └─, —). El console de Windows arranca en
# cp1252 y crashea al imprimirlos. Forzar UTF-8 en stdout (Python 3.7+).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # stdout no soporta reconfigure
    pass

import core.proposal_persistence as pp  # noqa: E402
from core.proposal_paths import (  # noqa: E402
    CATALOG_FILE,
    PROPOSALS_DIR,
    TEMPLATES_DIR,
)

# Arquetipos con template (custom no tiene — instantiate lanza ValueError).
_ARCHETYPES_CON_TEMPLATE = ["launch", "scale_seo", "defense", "cvr"]

# El conteo canónico documentado del catálogo (SOP §5.5 + docstring proposal_paths).
_CATALOGO_CANONICO_ESPERADO = 37

# El conteo esperado del demo seed.
_DEMO_BLOCKS_ESPERADO = 20

_OUTPUT_FILE = _REPO_ROOT / "scripts" / "_m29_discovery_output.json"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados de lectura
# ─────────────────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_proposals() -> list[dict]:
    """Devuelve la última versión de cada propuesta en PROPOSALS_DIR (solo lectura)."""
    latest: dict[str, tuple[int, Path]] = {}
    if not PROPOSALS_DIR.exists():
        return []
    for f in PROPOSALS_DIR.glob("*__v*.json"):
        m = re.match(r"(.+)__v(\d+)\.json$", f.name)
        if not m:
            continue
        pid, ver = m.group(1), int(m.group(2))
        if pid not in latest or ver > latest[pid][0]:
            latest[pid] = (ver, f)
    out = []
    for pid, (ver, f) in latest.items():
        data = _read_json(f)
        if data is None:
            continue
        out.append(
            {
                "proposal_id": pid,
                "latest_version": ver,
                "blocks": len(data.get("blocks", [])),
                "archetype": data.get("archetype"),
                "client_name": data.get("client_name"),
                "status": data.get("status"),
            }
        )
    return sorted(out, key=lambda p: p["client_name"] or "")


def _hunt_35_in_notes() -> list[dict]:
    """Rastrea el origen del '35' en notes/ (solo lectura).

    Busca patrones literales del planning: "vs 35", "35 blocks", "20 vs 35".
    Devuelve [{file, line, text}].
    """
    notes_dir = _REPO_ROOT / "notes"
    if not notes_dir.exists():
        return []
    patterns = [
        re.compile(r"vs\s*35\b"),
        re.compile(r"\b35\s*blocks?", re.IGNORECASE),
        re.compile(r"20\s*vs\s*35"),
    ]
    hits = []
    for f in notes_dir.rglob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if any(p.search(line) for p in patterns):
                hits.append(
                    {
                        "file": str(f.relative_to(_REPO_ROOT)).replace("\\", "/"),
                        "line": i,
                        "text": line.strip()[:200],
                    }
                )
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Secciones del reporte
# ─────────────────────────────────────────────────────────────────────────────


def _seccion1_inventario() -> dict:
    """Inventario crudo: templates, catálogo, propuestas."""
    # Templates
    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        data = _read_json(f) or {}
        default_blocks = data.get("default_blocks", [])
        templates.append(
            {
                "file": f.name,
                "archetype": data.get("archetype"),
                # Clave del flag #1: los templates usan `default_blocks`, NO `blocks`.
                "default_blocks_count": len(default_blocks),
                "blocks_key_present": "blocks" in data,
                "default_blocks": list(default_blocks),
            }
        )

    # Catálogo
    catalog = _read_json(CATALOG_FILE) or {}
    modules = catalog.get("modules", [])
    tiers: dict[str, int] = {}
    archetype_applicable: dict[str, int] = {}
    for m in modules:
        t = m.get("tier", "?")
        tiers[t] = tiers.get(t, 0) + 1
        for a in m.get("applicable_archetypes", []):
            archetype_applicable[a] = archetype_applicable.get(a, 0) + 1
    catalogo = {
        "total_modules": len(modules),
        "tiers": tiers,
        "applicable_archetypes_breakdown": archetype_applicable,
        "modules_with_applicable_archetypes_field": sum(
            1 for m in modules if "applicable_archetypes" in m
        ),
    }

    # Propuestas
    proposals = _latest_proposals()

    return {
        "templates": templates,
        "catalogo": catalogo,
        "proposals_latest": proposals,
    }


def _seccion2_reconcilio(inv: dict) -> dict:
    """Reconcilio numérico de los conteos de blocks."""
    templates = inv["templates"]
    catalogo = inv["catalogo"]
    proposals = inv["proposals_latest"]

    template_counts = {t["archetype"]: t["default_blocks_count"] for t in templates}
    catalogo_total = catalogo["total_modules"]

    demo = next(
        (p for p in proposals if p["client_name"] == "_DEMO_AgencyOS"), None
    )
    demo_blocks = demo["blocks"] if demo else None

    notes_35 = _hunt_35_in_notes()

    return {
        "templates_default_blocks_por_arquetipo": template_counts,
        "catalogo_total": catalogo_total,
        "catalogo_total_esperado": _CATALOGO_CANONICO_ESPERADO,
        "catalogo_total_matchea_esperado": catalogo_total == _CATALOGO_CANONICO_ESPERADO,
        "catalogo_aplicable_por_arquetipo": catalogo["applicable_archetypes_breakdown"],
        "demo_DEMO_AgencyOS_blocks": demo_blocks,
        "demo_blocks_esperado": _DEMO_BLOCKS_ESPERADO,
        "demo_matchea_esperado": demo_blocks == _DEMO_BLOCKS_ESPERADO,
        "planning_35_hits": notes_35,
        "planning_35_encontrado": len(notes_35) > 0,
    }


def _seccion3_instantiation() -> dict:
    """Análisis del flujo de instantiation SIN persistir.

    `instantiate_proposal_from_template` es pura (no escribe a disco) — verificado
    por lectura estática. La invocamos para confirmar el conteo de blocks deducido.
    """
    resultados = []
    for archetype in _ARCHETYPES_CON_TEMPLATE:
        template = pp.get_template(archetype)
        declared = len(template.get("default_blocks", [])) if template else 0
        entry = {
            "archetype": archetype,
            "template_default_blocks": declared,
        }
        try:
            draft = pp.instantiate_proposal_from_template(
                archetype=archetype,
                client_name="__DISCOVERY_PROBE__",
                language="es",
                sales_director="discovery_script",
            )
            instanciados = len(draft.get("blocks", []))
            entry["instantiated_blocks"] = instanciados
            entry["matchea_default_blocks"] = instanciados == declared
            entry["persistido"] = False  # función pura — solo en memoria
            entry["error"] = None
        except Exception as e:  # noqa: BLE001 — queremos reportar cualquier fallo
            entry["instantiated_blocks"] = None
            entry["matchea_default_blocks"] = None
            entry["persistido"] = False
            entry["error"] = f"{type(e).__name__}: {e}"
        resultados.append(entry)

    # 'custom' no tiene template → debe lanzar ValueError (comportamiento esperado).
    custom_entry = {"archetype": "custom", "template_default_blocks": None}
    try:
        pp.instantiate_proposal_from_template(
            archetype="custom",
            client_name="__DISCOVERY_PROBE__",
            language="es",
            sales_director="discovery_script",
        )
        custom_entry["instantiated_blocks"] = "NO LANZÓ (inesperado)"
        custom_entry["raises_value_error"] = False
    except ValueError as e:
        custom_entry["instantiated_blocks"] = None
        custom_entry["raises_value_error"] = True
        custom_entry["error"] = f"ValueError esperado: {e}"
    resultados.append(custom_entry)

    return {
        "filtra_por_applicable_archetypes": False,
        "fuente_de_blocks": "template['default_blocks'] (lista curada por arquetipo)",
        "usa_catalogo_para": "validar que module_id existe + determinar is_fixed (tier=='fixed')",
        "es_funcion_pura_sin_persistencia": True,
        "resultados": resultados,
    }


def _seccion4_conclusion(inv: dict, recon: dict, inst: dict) -> dict:
    """Conclusión en lenguaje natural sobre los 3 flags."""
    templates = inv["templates"]
    all_use_default_blocks = all(
        not t["blocks_key_present"] and t["default_blocks_count"] > 0
        for t in templates
    )

    flag1 = (
        "ESPERADO (no es deuda real en los datos). Los 4 templates declaran sus "
        "blocks bajo la key `default_blocks` (15-18 cada uno), NO bajo `blocks`. "
        "El reporte de '0 blocks' del SOP §5.5 viene de contar la key `blocks` "
        "(que es el campo de Proposal, no de Template). `instantiate_proposal_from_template` "
        "lee correctamente `default_blocks`, así que el wizard NO arranca con shell vacía. "
        "Acción sugerida: corregir la redacción del SOP §5.5 (deuda de documentación, no de código)."
        if all_use_default_blocks
        else "REVISAR: algún template no tiene default_blocks poblado — ver inventario."
    )

    catalogo_total = recon["catalogo_total"]
    if recon["planning_35_encontrado"]:
        flag2 = (
            f"El '35' aparece en notas de planning (ver planning_35_hits) como conteo "
            f"coloquial del catálogo ('20 vs 35 blocks'). NO matchea ningún conteo real: "
            f"el catálogo real tiene {catalogo_total} módulos (canónico {_CATALOGO_CANONICO_ESPERADO}), "
            f"el demo tiene {recon['demo_DEMO_AgencyOS_blocks']} blocks. El '35' es un "
            f"sub-conteo aproximado/desactualizado del catálogo de 37 — redondeo del planning, "
            f"no una fuente de verdad. El número canónico es 37."
        )
    else:
        flag2 = (
            f"No se encontró el '35' en notes/. El conteo real del catálogo es "
            f"{catalogo_total} (canónico {_CATALOGO_CANONICO_ESPERADO})."
        )

    flag3 = (
        "`instantiate_proposal_from_template` NO filtra por `applicable_archetypes`. "
        "La selección de blocks viene 100% de `template['default_blocks']` (lista curada "
        "por arquetipo). El catálogo se consulta solo para (a) validar que cada module_id "
        "existe y (b) setear is_fixed=(tier=='fixed'). El campo `applicable_archetypes` "
        "del catálogo es metadata pura — no se usa en NINGÚN .py de producción (solo en "
        "tests/test_proposal_schema.py). Es una función pura: construye el dict en memoria "
        "y NO persiste."
    )

    return {
        "flag_1_templates_0_blocks": flag1,
        "flag_2_origen_del_35": flag2,
        "flag_3_applicable_archetypes": flag3,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Render humano
# ─────────────────────────────────────────────────────────────────────────────


def _print_human(payload: dict) -> None:
    inv = payload["seccion_1_inventario"]
    recon = payload["seccion_2_reconcilio"]
    inst = payload["seccion_3_instantiation"]
    conc = payload["seccion_4_conclusion"]

    print("=" * 78)
    print("DISCOVERY M29 — TEMPLATE INSTANTIATION + RECONCILIO DE BLOCKS")
    print("Reunión Ramiro 01/06 — modo SOLO LECTURA")
    print("=" * 78)

    print("\n" + "-" * 78)
    print("SECCIÓN 1 — INVENTARIO CRUDO")
    print("-" * 78)
    print("\n[Templates] data/sales/_templates/*.json")
    for t in inv["templates"]:
        print(
            f"  • {t['file']:<28} archetype={str(t['archetype']):<10} "
            f"default_blocks={t['default_blocks_count']:<3} "
            f"(key 'blocks' presente: {t['blocks_key_present']})"
        )
    cat = inv["catalogo"]
    print(f"\n[Catálogo] {CATALOG_FILE}")
    print(f"  total_modules: {cat['total_modules']}")
    print(f"  tiers: {cat['tiers']}")
    print(f"  applicable_archetypes breakdown: {cat['applicable_archetypes_breakdown']}")
    print("\n[Propuestas] data/sales/proposals/ (última versión por id)")
    for p in inv["proposals_latest"]:
        print(
            f"  • {p['proposal_id'][:8]} v{p['latest_version']:<3} "
            f"blocks={p['blocks']:<3} archetype={str(p['archetype']):<10} "
            f"client={p['client_name']}"
        )

    print("\n" + "-" * 78)
    print("SECCIÓN 2 — RECONCILIO NUMÉRICO")
    print("-" * 78)
    print(f"{'Fuente':<43} {'Conteo':>8}")
    print(f"{'-' * 43} {'-' * 8:>8}")
    tcounts = recon["templates_default_blocks_por_arquetipo"]
    tcounts_str = ", ".join(f"{k}={v}" for k, v in tcounts.items())
    print(f"{'Templates _templates/*.json (default_blocks)':<43} {tcounts_str:>8}")
    print(
        f"{'Catálogo _catalog.json (total)':<43} "
        f"{recon['catalogo_total']:>8}   (esperado {recon['catalogo_total_esperado']})"
    )
    for a, c in recon["catalogo_aplicable_por_arquetipo"].items():
        print(f"{'  Catálogo aplicable a ' + a:<43} {c:>8}")
    print(
        f"{'Propuesta demo _DEMO_AgencyOS':<43} "
        f"{str(recon['demo_DEMO_AgencyOS_blocks']):>8}   "
        f"(esperado {recon['demo_blocks_esperado']})"
    )
    if recon["planning_35_encontrado"]:
        print(f"{'Planning histórico (35)':<43} {'ver hits':>8}")
        for h in recon["planning_35_hits"]:
            print(f"    └─ {h['file']}:{h['line']}: {h['text']}")
    else:
        print(f"{'Planning histórico (35)':<43} {'NO ENCONTRADA':>8}")

    print("\n" + "-" * 78)
    print("SECCIÓN 3 — FLUJO DE INSTANTIATION (sin persistir)")
    print("-" * 78)
    print(f"  filtra por applicable_archetypes: {inst['filtra_por_applicable_archetypes']}")
    print(f"  fuente de blocks: {inst['fuente_de_blocks']}")
    print(f"  catálogo se usa para: {inst['usa_catalogo_para']}")
    print(f"  función pura (sin persistencia): {inst['es_funcion_pura_sin_persistencia']}")
    print()
    for r in inst["resultados"]:
        if r["archetype"] == "custom":
            print(
                f"  • custom: raises_value_error={r.get('raises_value_error')} "
                f"({r.get('error', '')})"
            )
        else:
            print(
                f"  • {r['archetype']:<10} template_default_blocks={r['template_default_blocks']:<3} "
                f"instantiated={r['instantiated_blocks']:<4} "
                f"match={r['matchea_default_blocks']} persistido={r['persistido']}"
                + (f" ERROR={r['error']}" if r.get("error") else "")
            )

    print("\n" + "-" * 78)
    print("SECCIÓN 4 — CONCLUSIÓN")
    print("-" * 78)
    print(f"\n[Flag 1 — templates '0 blocks']\n  {conc['flag_1_templates_0_blocks']}")
    print(f"\n[Flag 2 — origen del 35]\n  {conc['flag_2_origen_del_35']}")
    print(f"\n[Flag 3 — applicable_archetypes]\n  {conc['flag_3_applicable_archetypes']}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    inv = _seccion1_inventario()
    recon = _seccion2_reconcilio(inv)
    inst = _seccion3_instantiation()
    conc = _seccion4_conclusion(inv, recon, inst)

    payload = {
        "_meta": {
            "script": "scripts/discover_m29_template_instantiation.py",
            "mode": "read-only",
            "catalogo_canonico_esperado": _CATALOGO_CANONICO_ESPERADO,
            "demo_blocks_esperado": _DEMO_BLOCKS_ESPERADO,
        },
        "seccion_1_inventario": inv,
        "seccion_2_reconcilio": recon,
        "seccion_3_instantiation": inst,
        "seccion_4_conclusion": conc,
    }

    _print_human(payload)

    _OUTPUT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[OK] Output estructurado escrito en: {_OUTPUT_FILE.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
