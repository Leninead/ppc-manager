"""Smoke test de core/supply_metrics.py (M37 B1 - capa de logica).

Data root temporal (AGENCY_OS_DATA_DIR), limpiado al final.
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TMP_ROOT = Path(tempfile.mkdtemp(prefix="supply_metrics_smoke_"))
os.environ["AGENCY_OS_DATA_DIR"] = str(TMP_ROOT)

# Raiz del repo derivada de la ubicacion del script (scripts/ -> repo).
# No hardcodear el worktree: este archivo tambien vive en main tras el merge.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.supply_persistence import (  # noqa: E402
    get_oc,
    leer_eventos,
    list_ocs,
    save_oc,
    save_proveedor,
)
from core.supply_metrics import (  # noqa: E402
    LT_DESDE,
    LT_HASTA,
    TRANSICIONES,
    cambiar_estado_oc,
    fill_rate,
    generar_codigo_oc,
    lead_time_medido,
    resumen_proveedor,
    transicion_valida,
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


def crear_oc(oc_id, proveedor_id, lineas):
    return save_oc({"id": oc_id, "proveedor_id": proveedor_id,
                    "estado": "PROPUESTA", "lineas": lineas})


def avanzar(oc_id, ruta):
    """ruta = [(estado, fecha_negocio), ...]"""
    for estado, fecha in ruta:
        cambiar_estado_oc(oc_id, estado, quien="smoke", fecha=fecha)


# =====================================================================
print("")
print("=== T1. transicion_valida ===")
check("PROPUESTA -> APROBADA es True", transicion_valida("PROPUESTA", "APROBADA") is True)
check("PROPUESTA -> CERRADA es False", transicion_valida("PROPUESTA", "CERRADA") is False)
check("EMITIDA -> ANULADA es True", transicion_valida("EMITIDA", "ANULADA") is True)
check("CERRADA -> APROBADA es False", transicion_valida("CERRADA", "APROBADA") is False)
check("CERRADA -> ANULADA es False (terminal)", transicion_valida("CERRADA", "ANULADA") is False)
check("CERRADA -> CERRADA es False", transicion_valida("CERRADA", "CERRADA") is False)
check("ANULADA no habilita nada",
      not any(transicion_valida("ANULADA", e) for e in TRANSICIONES))
check("estado inexistente -> False", transicion_valida("INVENTADO", "APROBADA") is False)
check("RECIBIDA_PARCIAL -> RECIBIDA_PARCIAL True (varias tandas)",
      transicion_valida("RECIBIDA_PARCIAL", "RECIBIDA_PARCIAL") is True)
check("ruta feliz completa es legal", all(
    transicion_valida(a, b) for a, b in [
        ("PROPUESTA", "APROBADA"), ("APROBADA", "OK_FIN"),
        ("OK_FIN", "EMITIDA"), ("EMITIDA", "RECIBIDA_PARCIAL"),
        ("RECIBIDA_PARCIAL", "CERRADA")]))

# =====================================================================
print("")
print("=== T2. generar_codigo_oc ===")
save_proveedor({"nombre": "Shenzhen Tools", "id": "shenzhen"})
save_proveedor({"nombre": "Gina Miriam", "id": "gina-miriam"})
AAMM = datetime.now().strftime("%y%m")

cod1 = generar_codigo_oc("shenzhen")
check("primera del mes -> NN=01", cod1 == "OC-SHE-" + AAMM + "-01", cod1)
check("formato OC-<PROV>-<AAMM>-<NN>", cod1.count("-") == 3, cod1)
check("no crea la OC (sigue sin existir)", get_oc(cod1) is None)
check("llamar de nuevo sin guardar da lo mismo", generar_codigo_oc("shenzhen") == cod1)

crear_oc(cod1, "shenzhen", [{"sku": "SKU-A", "qty": 100}])
cod2 = generar_codigo_oc("shenzhen")
check("despues de crear la 01 -> NN=02", cod2 == "OC-SHE-" + AAMM + "-02", cod2)

crear_oc(cod2, "shenzhen", [{"sku": "SKU-B", "qty": 10}])
check("tercera -> NN=03", generar_codigo_oc("shenzhen") == "OC-SHE-" + AAMM + "-03")

cod_gina = generar_codigo_oc("gina-miriam")
check("guion no cuenta: gina-miriam -> GIN", cod_gina.startswith("OC-GIN-"), cod_gina)
check("otro proveedor NO comparte secuencia -> 01",
      cod_gina == "OC-GIN-" + AAMM + "-01", cod_gina)

save_proveedor({"nombre": "Ab Corp", "id": "ab"})
check("id corto se rellena: 'ab' -> ABX", generar_codigo_oc("ab").startswith("OC-ABX-"))

# Una OC con sufijo no numerico no debe romper la secuencia
crear_oc("OC-SHE-" + AAMM + "-XX", "shenzhen", [{"sku": "SKU-Z", "qty": 1}])
check("sufijo no numerico se ignora, sigue en 03",
      generar_codigo_oc("shenzhen") == "OC-SHE-" + AAMM + "-03")

# =====================================================================
print("")
print("=== T3. cambiar_estado_oc ===")
OC_T3 = "OC-T3-001"
crear_oc(OC_T3, "shenzhen", [{"sku": "SKU-A", "qty": 10}])

r = cambiar_estado_oc(OC_T3, "APROBADA", quien="lenin", fecha="2026-09-02")
check("salto legal devuelve la OC actualizada", r["estado"] == "APROBADA", r["estado"])
check("salto legal persiste el estado", get_oc(OC_T3)["estado"] == "APROBADA")

ev = leer_eventos(OC_T3)
check("salto legal escribio 1 evento", len(ev) == 1, len(ev))
check("evento = estado nuevo", ev.iloc[0]["evento"] == "APROBADA")
check("fecha de negocio respetada", ev.iloc[0]["fecha"] == "2026-09-02")
check("quien registrado", ev.iloc[0]["quien"] == "lenin")

estado_antes = get_oc(OC_T3)["estado"]
log_antes = len(leer_eventos(OC_T3))
try:
    cambiar_estado_oc(OC_T3, "CERRADA", quien="lenin")
    check("salto ilegal lanza ValueError", False, "no lanzo")
except ValueError as e:
    msg = str(e)
    check("salto ilegal lanza ValueError", True)
    check("mensaje nombra estado actual", "APROBADA" in msg, msg)
    check("mensaje nombra estado pedido", "CERRADA" in msg, msg)
    check("mensaje lista transiciones legales", "OK_FIN" in msg, msg)

check("salto ilegal NO modifico la OC", get_oc(OC_T3)["estado"] == estado_antes)
check("salto ilegal NO escribio en el log", len(leer_eventos(OC_T3)) == log_antes)

try:
    cambiar_estado_oc("OC-NO-EXISTE", "APROBADA")
    check("OC inexistente lanza ValueError", False, "no lanzo")
except ValueError:
    check("OC inexistente lanza ValueError", True)

# Terminal: desde ANULADA no se sale
cambiar_estado_oc(OC_T3, "ANULADA", quien="lenin")
check("se puede anular desde APROBADA", get_oc(OC_T3)["estado"] == "ANULADA")
try:
    cambiar_estado_oc(OC_T3, "OK_FIN")
    check("desde ANULADA no se sale", False, "no lanzo")
except ValueError:
    check("desde ANULADA no se sale", True)

# =====================================================================
print("")
print("=== T4. lead_time_medido ===")
print("    ventana: " + LT_DESDE + " -> " + LT_HASTA)
save_proveedor({"nombre": "Lead Time Co", "id": "leadtime"})

# OC-A: emitida 01/09, recibida 11/09 -> 10 dias
crear_oc("OC-LT-A", "leadtime", [{"sku": "S1", "qty": 10}])
avanzar("OC-LT-A", [("APROBADA", "2026-09-01"), ("OK_FIN", "2026-09-01"),
                    ("EMITIDA", "2026-09-01"), ("RECIBIDA_PARCIAL", "2026-09-11")])
# OC-B: emitida 01/09, recibida 21/09 -> 20 dias
crear_oc("OC-LT-B", "leadtime", [{"sku": "S2", "qty": 10}])
avanzar("OC-LT-B", [("APROBADA", "2026-09-01"), ("OK_FIN", "2026-09-01"),
                    ("EMITIDA", "2026-09-01"), ("RECIBIDA_PARCIAL", "2026-09-21")])

lt = lead_time_medido("leadtime")
check("mediana de [10, 20] = 15.0", lt == 15.0, lt)
check("devuelve float", isinstance(lt, float), type(lt).__name__)

# OC-C: 30 dias -> mediana impar [10, 20, 30] = 20.0
crear_oc("OC-LT-C", "leadtime", [{"sku": "S3", "qty": 10}])
avanzar("OC-LT-C", [("APROBADA", "2026-09-01"), ("OK_FIN", "2026-09-01"),
                    ("EMITIDA", "2026-09-01"), ("RECIBIDA_PARCIAL", "2026-10-01")])
check("mediana de [10, 20, 30] = 20.0", lead_time_medido("leadtime") == 20.0,
      lead_time_medido("leadtime"))

# Segunda recepcion (RECIBIDA_PARCIAL -> RECIBIDA_PARCIAL) no cambia la muestra:
# se toma la PRIMERA recepcion.
cambiar_estado_oc("OC-LT-A", "RECIBIDA_PARCIAL", fecha="2026-09-30")
check("2da recepcion no altera el LT (cuenta la 1ra)",
      lead_time_medido("leadtime") == 20.0, lead_time_medido("leadtime"))

# Proveedor emitido pero sin recibir -> None
save_proveedor({"nombre": "Sin Recepcion", "id": "sinrec"})
crear_oc("OC-SR-1", "sinrec", [{"sku": "S1", "qty": 5}])
avanzar("OC-SR-1", [("APROBADA", "2026-09-01"), ("OK_FIN", "2026-09-01"),
                    ("EMITIDA", "2026-09-01")])
check("emitida sin recibir -> None", lead_time_medido("sinrec") is None,
      lead_time_medido("sinrec"))

save_proveedor({"nombre": "Sin Nada", "id": "sinnada"})
check("proveedor sin OC -> None", lead_time_medido("sinnada") is None)

# OC con fecha malformada no explota
crear_oc("OC-SR-2", "sinrec", [{"sku": "S9", "qty": 1}])
avanzar("OC-SR-2", [("APROBADA", None), ("OK_FIN", None)])
cambiar_estado_oc("OC-SR-2", "EMITIDA", fecha="fecha-rota")
cambiar_estado_oc("OC-SR-2", "RECIBIDA_PARCIAL", fecha="2026-09-10")
try:
    check("fecha malformada no explota, no aporta muestra",
          lead_time_medido("sinrec") is None, lead_time_medido("sinrec"))
except Exception as e:
    check("fecha malformada no explota", False, type(e).__name__ + ": " + str(e))

# =====================================================================
print("")
print("=== T5. fill_rate ===")
save_proveedor({"nombre": "Fill Co", "id": "fillco"})

# qty 100+50=150, recibido 80+40=120 -> 0.8
crear_oc("OC-FR-1", "fillco", [{"sku": "A", "qty": 100}, {"sku": "B", "qty": 50}])
avanzar("OC-FR-1", [("APROBADA", None), ("OK_FIN", None), ("EMITIDA", None)])
oc = get_oc("OC-FR-1")
oc["lineas"][0]["recibido"] = 80
oc["lineas"][1]["recibido"] = 40
save_oc(oc)
cambiar_estado_oc("OC-FR-1", "RECIBIDA_PARCIAL", fecha="2026-09-10")

fr = fill_rate("fillco")
check("120/150 = 0.8", fr == 0.8, fr)
check("devuelve float en [0,1]", isinstance(fr, float) and 0.0 <= fr <= 1.0, fr)

# OC en PROPUESTA no aplica: no debe mover el numero
crear_oc("OC-FR-2", "fillco", [{"sku": "C", "qty": 1000}])
check("OC en PROPUESTA no entra al fill rate", fill_rate("fillco") == 0.8,
      fill_rate("fillco"))

# Proveedor sin OC aplicables -> None
save_proveedor({"nombre": "Solo Propuestas", "id": "soloprop"})
crear_oc("OC-SP-1", "soloprop", [{"sku": "A", "qty": 10}])
check("solo PROPUESTA -> None", fill_rate("soloprop") is None, fill_rate("soloprop"))
check("proveedor sin OC -> None", fill_rate("sinnada") is None)

# Recepcion completa -> 1.0
save_proveedor({"nombre": "Full Co", "id": "fullco"})
crear_oc("OC-FU-1", "fullco", [{"sku": "A", "qty": 20}])
avanzar("OC-FU-1", [("APROBADA", None), ("OK_FIN", None), ("EMITIDA", None)])
oc = get_oc("OC-FU-1")
oc["lineas"][0]["recibido"] = 20
save_oc(oc)
cambiar_estado_oc("OC-FU-1", "CERRADA", fecha="2026-09-15")
check("recepcion completa (CERRADA) -> 1.0", fill_rate("fullco") == 1.0, fill_rate("fullco"))

# Sobre-recepcion se recorta a 1.0
oc = get_oc("OC-FU-1")
oc["lineas"][0]["recibido"] = 25
save_oc(oc)
check("sobre-recepcion se recorta a 1.0", fill_rate("fullco") == 1.0, fill_rate("fullco"))

# =====================================================================
print("")
print("=== T6. resumen_proveedor ===")
res = resumen_proveedor("leadtime")
check("claves exactas",
      set(res) == {"proveedor_id", "lt_medido", "fill_rate", "n_ocs", "n_ocs_cerradas"},
      sorted(res))
check("proveedor_id correcto", res["proveedor_id"] == "leadtime")
check("lt_medido propagado", res["lt_medido"] == 20.0, res["lt_medido"])
check("n_ocs cuenta todas", res["n_ocs"] == len(list_ocs(proveedor_id="leadtime")))
check("n_ocs_cerradas = 0 (ninguna cerrada)", res["n_ocs_cerradas"] == 0)

vacio = resumen_proveedor("sinnada")
check("proveedor vacio: lt_medido None", vacio["lt_medido"] is None)
check("proveedor vacio: fill_rate None", vacio["fill_rate"] is None)
check("proveedor vacio: n_ocs 0", vacio["n_ocs"] == 0)
check("proveedor vacio: n_ocs_cerradas 0", vacio["n_ocs_cerradas"] == 0)

full = resumen_proveedor("fullco")
check("fullco: n_ocs_cerradas = 1", full["n_ocs_cerradas"] == 1, full["n_ocs_cerradas"])
check("fullco: fill_rate 1.0", full["fill_rate"] == 1.0)

# =====================================================================
print("")
print("=" * 62)
print("RESULTADO: " + str(PASS) + " passed, " + str(FAIL) + " failed")
print("=" * 62)

shutil.rmtree(TMP_ROOT, ignore_errors=True)
print("cleanup: " + ("root eliminado OK" if not TMP_ROOT.exists()
                     else "QUEDO BASURA en " + str(TMP_ROOT)))

sys.exit(1 if FAIL else 0)
