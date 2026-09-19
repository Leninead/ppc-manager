"""Test de integracion end-to-end de core/supply/metrics.py (M37 B1).

Data root temporal VIRGEN: shenzhen tiene exactamente 1 OC, asi n_ocs==1 es
verificable. Todo el circuito pasa por la API publica -- ningun evento se
inyecta a mano con registrar_evento.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP_ROOT = Path(tempfile.mkdtemp(prefix="supply_e2e_"))
os.environ["AGENCY_OS_DATA_DIR"] = str(TMP_ROOT)

# Raiz del repo derivada de la ubicacion del script (scripts/ -> repo).
# No hardcodear el worktree: este archivo tambien vive en main tras el merge.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.supply.persistence import (  # noqa: E402
    get_oc,
    get_proveedor,
    leer_eventos,
    save_oc,
    save_proveedor,
)
from core.supply.metrics import (  # noqa: E402
    cambiar_estado_oc,
    fill_rate,
    generar_codigo_oc,
    lead_time_medido,
    resumen_proveedor,
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


print("")
print("=== E2E. Circuito real de una OC, de punta a punta ===")
print("    data root virgen: " + str(TMP_ROOT))

# ---------------------------------------------------------------- paso 1
print("")
print("--- paso 1: alta del proveedor ---")
prov = save_proveedor({"nombre": "Shenzhen Tools", "id": "shenzhen",
                       "lt_min": 25, "lt_tip": 35, "lt_max": 50})
check("proveedor guardado", get_proveedor("shenzhen") is not None)
check("lt_tip del maestro = 35", prov["lt_tip"] == 35, prov.get("lt_tip"))

# ---------------------------------------------------------------- paso 2
print("")
print("--- paso 2: codigo + alta de la OC ---")
oc_id = generar_codigo_oc("shenzhen")
print("    codigo generado: " + oc_id)
check("primera OC del proveedor -> NN=01", oc_id.endswith("-01"), oc_id)
check("token de proveedor = SHE", oc_id.startswith("OC-SHE-"), oc_id)
check("generar_codigo_oc no creo nada", get_oc(oc_id) is None)

QTY_A, QTY_B = 120, 80
save_oc({
    "id": oc_id,
    "proveedor_id": "shenzhen",
    "estado": "PROPUESTA",
    "lineas": [{"sku": "SKU-A", "qty": QTY_A}, {"sku": "SKU-B", "qty": QTY_B}],
})
check("OC persistida en PROPUESTA", get_oc(oc_id)["estado"] == "PROPUESTA")
check("2 lineas guardadas", len(get_oc(oc_id)["lineas"]) == 2)
check("recibido arranca en 0",
      all(ln["recibido"] == 0 for ln in get_oc(oc_id)["lineas"]))
check("log de eventos todavia vacio", leer_eventos(oc_id).empty)

# ---------------------------------------------------------------- paso 3
print("")
print("--- paso 3: avance SOLO con cambiar_estado_oc ---")
cambiar_estado_oc(oc_id, "APROBADA", quien="lenin", fecha="2026-09-01")
check("PROPUESTA -> APROBADA", get_oc(oc_id)["estado"] == "APROBADA")

cambiar_estado_oc(oc_id, "OK_FIN", quien="edu", fecha="2026-09-02")
check("APROBADA -> OK_FIN", get_oc(oc_id)["estado"] == "OK_FIN")

cambiar_estado_oc(oc_id, "EMITIDA", quien="lenin", fecha="2026-09-03")
check("OK_FIN -> EMITIDA", get_oc(oc_id)["estado"] == "EMITIDA")

# La UI carga lo recibido antes de marcar la recepcion.
REC_A, REC_B = 100, 60
oc = get_oc(oc_id)
oc["lineas"][0]["recibido"] = REC_A
oc["lineas"][1]["recibido"] = REC_B
save_oc(oc)
check("recibido cargado en las lineas",
      [ln["recibido"] for ln in get_oc(oc_id)["lineas"]] == [REC_A, REC_B])

cambiar_estado_oc(oc_id, "RECIBIDA_PARCIAL", quien="juli", fecha="2026-09-30")
check("EMITIDA -> RECIBIDA_PARCIAL", get_oc(oc_id)["estado"] == "RECIBIDA_PARCIAL")

log = leer_eventos(oc_id)
print("")
print("    log de eventos generado por el circuito (nada inyectado a mano):")
for _, fila in log.iterrows():
    print("      " + str(fila["fecha"])[:10] + "  " + str(fila["evento"]).ljust(18)
          + "  quien=" + str(fila["quien"]))
check("4 eventos, uno por transicion", len(log) == 4, len(log))
check("secuencia de eventos correcta",
      list(log["evento"]) == ["APROBADA", "OK_FIN", "EMITIDA", "RECIBIDA_PARCIAL"],
      list(log["evento"]))
check("fechas de negocio respetadas",
      list(log["fecha"]) == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-30"],
      list(log["fecha"]))
check("ts (escritura) != fecha (negocio)",
      all(log.iloc[i]["ts"] != log.iloc[i]["fecha"] for i in range(len(log))))

# ---------------------------------------------------------------- paso 4
print("")
print("--- paso 4: metricas sobre el circuito real ---")
lt = lead_time_medido("shenzhen")
print("    EMITIDA 2026-09-03 -> RECIBIDA_PARCIAL 2026-09-30")
print("    lead_time_medido = " + repr(lt) + "   (lt_tip del maestro: 35)")
check("lead_time_medido == 27.0", lt == 27.0, lt)
check("es float", isinstance(lt, float), type(lt).__name__)

qty_total = QTY_A + QTY_B
rec_total = REC_A + REC_B
esperado = rec_total / qty_total
fr = fill_rate("shenzhen")
print("    fill_rate = " + repr(fr) + "   ("
      + str(rec_total) + "/" + str(qty_total) + " = " + str(esperado) + ")")
check("fill_rate == recibido_total/qty_total", fr == esperado, fr)

res = resumen_proveedor("shenzhen")
print("    resumen_proveedor = " + repr(res))
check("resumen.lt_medido == 27.0", res["lt_medido"] == 27.0, res["lt_medido"])
check("resumen.n_ocs == 1", res["n_ocs"] == 1, res["n_ocs"])
check("resumen.fill_rate correcto", res["fill_rate"] == esperado, res["fill_rate"])
check("resumen.n_ocs_cerradas == 0 (sigue parcial)", res["n_ocs_cerradas"] == 0)
check("resumen.proveedor_id", res["proveedor_id"] == "shenzhen")

# ---------------------------------------------------------------- paso 5
print("")
print("--- paso 5: retroceso ilegal RECIBIDA_PARCIAL -> PROPUESTA ---")
estado_antes = get_oc(oc_id)["estado"]
log_antes = len(leer_eventos(oc_id))
lineas_antes = [dict(ln) for ln in get_oc(oc_id)["lineas"]]

try:
    cambiar_estado_oc(oc_id, "PROPUESTA", quien="lenin", fecha="2026-10-01")
    check("retroceso lanza ValueError", False, "no lanzo")
except ValueError as e:
    msg = str(e)
    print("    ValueError: " + msg)
    check("retroceso lanza ValueError", True)
    check("mensaje nombra RECIBIDA_PARCIAL", "RECIBIDA_PARCIAL" in msg)
    check("mensaje nombra PROPUESTA", "PROPUESTA" in msg)

check("estado intacto", get_oc(oc_id)["estado"] == estado_antes, get_oc(oc_id)["estado"])
check("log intacto", len(leer_eventos(oc_id)) == log_antes)
check("lineas intactas", [dict(ln) for ln in get_oc(oc_id)["lineas"]] == lineas_antes)
check("lead_time_medido sin cambios", lead_time_medido("shenzhen") == 27.0)
check("fill_rate sin cambios", fill_rate("shenzhen") == esperado)

print("")
print("=" * 62)
print("RESULTADO E2E: " + str(PASS) + " passed, " + str(FAIL) + " failed")
print("=" * 62)

shutil.rmtree(TMP_ROOT, ignore_errors=True)
print("cleanup: " + ("root eliminado OK" if not TMP_ROOT.exists()
                     else "QUEDO BASURA en " + str(TMP_ROOT)))

sys.exit(1 if FAIL else 0)
