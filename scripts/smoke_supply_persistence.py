"""Smoke test de core/supply/persistence.py (M37 B1).

Corre contra un data root temporal (AGENCY_OS_DATA_DIR) y lo limpia al final.
Cubre la API publica completa + los 3 casos de robustez de esta iteracion.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# El data root se congela en import time -> setear ANTES de importar core.*
TMP_ROOT = Path(tempfile.mkdtemp(prefix="supply_smoke_"))
os.environ["AGENCY_OS_DATA_DIR"] = str(TMP_ROOT)

# Raiz del repo derivada de la ubicacion del script (scripts/ -> repo).
# No hardcodear el worktree: este archivo tambien vive en main tras el merge.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.supply.paths import EVENTOS_LOG_FILE, OCS_DIR, SUPPLY_ROOT  # noqa: E402
from core.supply.persistence import (  # noqa: E402
    _EVENTO_COLUMNS,
    anular_oc,
    archivar_proveedor,
    get_oc,
    get_proveedor,
    leer_eventos,
    list_ocs,
    list_proveedores,
    registrar_evento,
    save_oc,
    save_proveedor,
)

PASS, FAIL = 0, 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [OK]   " + label)
    else:
        FAIL += 1
        print("  [FAIL] " + label + ("  -> " + str(detail) if detail else ""))


# =====================================================================
print("")
print("=== T0. Data root recien creado, VACIO (caso 3) ===")
print("    root: " + str(TMP_ROOT))
check("SUPPLY_ROOT no existe todavia", not SUPPLY_ROOT.exists())
check("OCS_DIR no existe todavia", not OCS_DIR.exists())

try:
    ocs = list_ocs()
    check("list_ocs() no lanza y devuelve []", ocs == [], repr(ocs))
except Exception as e:
    check("list_ocs() no lanza y devuelve []", False, type(e).__name__ + ": " + str(e))

try:
    oc = get_oc("cualquiera")
    check("get_oc(inexistente) devuelve None", oc is None, repr(oc))
except Exception as e:
    check("get_oc(inexistente) devuelve None", False, type(e).__name__ + ": " + str(e))

try:
    df0 = leer_eventos()
    check("leer_eventos() vacio -> columnas canonicas",
          list(df0.columns) == _EVENTO_COLUMNS, list(df0.columns))
    check("leer_eventos() vacio -> 0 filas", len(df0) == 0, len(df0))
except Exception as e:
    check("leer_eventos() sobre root vacio", False, type(e).__name__ + ": " + str(e))

check("list_proveedores() -> []", list_proveedores() == [])
check("get_proveedor(inexistente) -> None", get_proveedor("x") is None)

# =====================================================================
print("")
print("=== T1. Proveedores CRUD ===")
p = save_proveedor({"nombre": "Fabrica Norte", "lt_min": 10, "lt_tip": 20, "lt_max": 30})
check("save_proveedor genera id slug", p["id"] == "fabrica-norte", p["id"])
check("activo=True por default", p["activo"] is True)
check("creado_en seteado", bool(p.get("creado_en")))

save_proveedor({"nombre": "Proveedor Sur"})
check("list_proveedores ordena por nombre",
      [x["nombre"] for x in list_proveedores()] == ["Fabrica Norte", "Proveedor Sur"])

p2 = save_proveedor({"id": "fabrica-norte", "nombre": "Fabrica Norte", "lt_tip": 25})
check("upsert por id no duplica", len(list_proveedores()) == 2)
check("upsert preserva creado_en", p2["creado_en"] == p["creado_en"])

check("archivar_proveedor -> True", archivar_proveedor("proveedor-sur") is True)
check("archivado no aparece por default", len(list_proveedores()) == 1)
check("archivado aparece con incluir_inactivos", len(list_proveedores(True)) == 2)
check("archivar inexistente -> False", archivar_proveedor("no-existe") is False)

casos_prov = [
    ({"nombre": "  "}, "nombre vacio"),
    ({"nombre": "X", "lt_min": 30, "lt_max": 10}, "lt_min > lt_max"),
    ({"nombre": "X", "lt_min": "abc"}, "lt no numerico"),
    ({"nombre": "X", "revision_dias": 0}, "revision_dias <= 0"),
]
for bad, label in casos_prov:
    try:
        save_proveedor(bad)
        check("rechaza " + label, False, "no lanzo ValueError")
    except ValueError:
        check("rechaza " + label, True)

# =====================================================================
print("")
print("=== T2. Ordenes de compra CRUD ===")
oc1 = save_oc({
    "id": "OC-2026-001", "proveedor_id": "fabrica-norte", "estado": "PROPUESTA",
    "lineas": [{"sku": "SKU-A", "qty": 100}, {"sku": "SKU-B", "qty": 50}],
})
check("save_oc persiste", get_oc("OC-2026-001") is not None)
check("recibido default 0", all(ln["recibido"] == 0 for ln in oc1["lineas"]))
check("get_oc inexistente -> None", get_oc("OC-NOPE") is None)

save_oc({"id": "OC-2026-002", "proveedor_id": "proveedor-sur", "estado": "EMITIDA",
         "lineas": [{"sku": "SKU-C", "qty": 5}]})
check("list_ocs devuelve 2", len(list_ocs()) == 2, len(list_ocs()))
check("filtro por proveedor_id", len(list_ocs(proveedor_id="fabrica-norte")) == 1)
check("filtro por estado", len(list_ocs(estado="EMITIDA")) == 1)

check("anular_oc -> True", anular_oc("OC-2026-001") is True)
check("estado quedo ANULADA", get_oc("OC-2026-001")["estado"] == "ANULADA")
check("archivo NO se borro", (OCS_DIR / "OC-2026-001.json").exists())
check("anular inexistente -> False", anular_oc("OC-NOPE") is False)

casos_oc = [
    ({"proveedor_id": "p", "estado": "PROPUESTA", "lineas": [{"sku": "A", "qty": 1}]}, "falta id"),
    ({"id": "X", "estado": "PROPUESTA", "lineas": [{"sku": "A", "qty": 1}]}, "falta proveedor_id"),
    ({"id": "X", "proveedor_id": "p", "estado": "INVENTADO",
      "lineas": [{"sku": "A", "qty": 1}]}, "estado invalido"),
    ({"id": "X", "proveedor_id": "p", "estado": "PROPUESTA", "lineas": []}, "lineas vacias"),
    ({"id": "X", "proveedor_id": "p", "estado": "PROPUESTA",
      "lineas": [{"sku": "A", "qty": 0}]}, "qty <= 0"),
    ({"id": "X", "proveedor_id": "p", "estado": "PROPUESTA",
      "lineas": [{"qty": 1}]}, "falta sku"),
]
for bad, label in casos_oc:
    try:
        save_oc(bad)
        check("rechaza " + label, False, "no lanzo ValueError")
    except ValueError:
        check("rechaza " + label, True)

# =====================================================================
print("")
print("=== T3. Eventos: 2 appends, releer, shape (caso 1) ===")
TMP_PARQUET = EVENTOS_LOG_FILE.with_suffix(EVENTOS_LOG_FILE.suffix + ".tmp")
check("parquet no existe antes del 1er evento", not EVENTOS_LOG_FILE.exists())

registrar_evento("OC-2026-001", "CREADA", quien="lenin")
check("1er append creo el parquet", EVENTOS_LOG_FILE.exists())
check("sin .tmp huerfano tras append #1", not TMP_PARQUET.exists())

registrar_evento("OC-2026-001", "APROBADA", fecha="2026-09-01", quien="edu")

df = leer_eventos()
check("2 eventos persistidos", len(df) == 2, len(df))
check("columnas EXACTAS y en orden", list(df.columns) == _EVENTO_COLUMNS, list(df.columns))
check("fecha backdateada respetada", df.iloc[1]["fecha"] == "2026-09-01", df.iloc[1]["fecha"])
check("ts != fecha (se separan a proposito)", df.iloc[1]["ts"] != df.iloc[1]["fecha"])
check("filtro por oc_id", len(leer_eventos("OC-2026-001")) == 2)
check("filtro oc_id inexistente -> vacio", len(leer_eventos("OC-NOPE")) == 0)
check("filtro vacio conserva columnas",
      list(leer_eventos("OC-NOPE").columns) == _EVENTO_COLUMNS)

casos_ev = [(("", "E"), "oc_id vacio"), (("OC-1", ""), "evento vacio")]
for args, label in casos_ev:
    try:
        registrar_evento(*args)
        check("rechaza " + label, False, "no lanzo ValueError")
    except ValueError:
        check("rechaza " + label, True)

# =====================================================================
print("")
print("=== T4. Append sobre parquet EXISTENTE (caso feliz) ===")
antes = len(leer_eventos())
registrar_evento("OC-2026-002", "EMITIDA", quien="juli")
df4 = leer_eventos()
check("append sumo exactamente 1 fila", len(df4) == antes + 1, str(antes) + " -> " + str(len(df4)))
check("filas previas intactas",
      list(df4["evento"])[:2] == ["CREADA", "APROBADA"], list(df4["evento"]))
check("columnas siguen canonicas", list(df4.columns) == _EVENTO_COLUMNS)
check("sin .tmp huerfano tras append sobre existente", not TMP_PARQUET.exists())

sobrantes = [f.name for f in SUPPLY_ROOT.rglob("*.tmp")]
check("cero archivos .tmp en todo el arbol", sobrantes == [], sobrantes)

# =====================================================================
print("")
print("=== T5. read_eventos normaliza parquet degradado (caso 2) ===")
# Parquet legacy: le falta 'quien' y tiene las columnas desordenadas.
degradado = pd.DataFrame([
    {"ts": "2026-09-01T10:00:00", "evento": "CREADA",
     "oc_id": "OC-LEGACY", "fecha": "2026-09-01"},
])
degradado.to_parquet(EVENTOS_LOG_FILE, compression="snappy", index=False)
check("parquet degradado escrito (4 cols, desordenadas)",
      list(pd.read_parquet(EVENTOS_LOG_FILE).columns) != _EVENTO_COLUMNS)

df5 = leer_eventos()
check("read_eventos rellena la columna faltante",
      list(df5.columns) == _EVENTO_COLUMNS, list(df5.columns))
check("la fila sobrevive", len(df5) == 1, len(df5))
check("quien quedo vacia (NA)", pd.isna(df5.iloc[0]["quien"]), repr(df5.iloc[0]["quien"]))
check("datos existentes intactos", df5.iloc[0]["oc_id"] == "OC-LEGACY")

# Parquet vacio del todo (0 filas, 0 columnas)
pd.DataFrame().to_parquet(EVENTOS_LOG_FILE, compression="snappy", index=False)
df6 = leer_eventos()
check("parquet 0x0 -> columnas canonicas", list(df6.columns) == _EVENTO_COLUMNS, list(df6.columns))
check("parquet 0x0 -> 0 filas", len(df6) == 0)

# El append sigue funcionando despues de haber normalizado
registrar_evento("OC-POST", "CERRADA", quien="lenin")
df7 = leer_eventos()
check("append post-normalizacion funciona", len(df7) == 1, len(df7))
check("columnas canonicas post-append", list(df7.columns) == _EVENTO_COLUMNS)

# =====================================================================
print("")
print("=" * 62)
print("RESULTADO: " + str(PASS) + " passed, " + str(FAIL) + " failed")
print("=" * 62)

shutil.rmtree(TMP_ROOT, ignore_errors=True)
print("cleanup: " + ("root eliminado OK" if not TMP_ROOT.exists()
                     else "QUEDO BASURA en " + str(TMP_ROOT)))

sys.exit(1 if FAIL else 0)
