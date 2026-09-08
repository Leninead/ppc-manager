"""Verifica que los helpers de formato de supply_proveedores.py nunca dejen
pasar un None/NaN a pantalla. No levanta streamlit: solo importa el modulo y
ejercita las funciones puras.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP_ROOT = Path(tempfile.mkdtemp(prefix="supply_ui_"))
os.environ["AGENCY_OS_DATA_DIR"] = str(TMP_ROOT)
# Raiz del repo derivada de la ubicacion del script (scripts/ -> repo).
# No hardcodear el worktree: este archivo tambien vive en main tras el merge.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.pages import supply_proveedores as ui  # noqa: E402

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
print("=== import del modulo ===")
check("importa sin runtime de streamlit", ui.MODULE_SLUG == "supply-proveedores")
check("render existe y no toma argumentos",
      callable(ui.render) and ui.render.__code__.co_argcount == 0)

print("")
print("=== _fmt_num ===")
check("None -> ''", ui._fmt_num(None) == "", repr(ui._fmt_num(None)))
check("'' -> ''", ui._fmt_num("") == "")
check("NaN -> ''", ui._fmt_num(float("nan")) == "")
check("10.0 -> '10'", ui._fmt_num(10.0) == "10", ui._fmt_num(10.0))
check("7 -> '7'", ui._fmt_num(7) == "7")
check("10.5 -> '10.5'", ui._fmt_num(10.5) == "10.5")
check("texto no numerico no explota", ui._fmt_num("abc") == "abc")

print("")
print("=== _fmt_lt_declarado ===")
check("los tres cargados",
      ui._fmt_lt_declarado({"lt_min": 7, "lt_tip": 10, "lt_max": 14}) == "7 / 10 / 14 d",
      ui._fmt_lt_declarado({"lt_min": 7, "lt_tip": 10, "lt_max": 14}))
check("dict vacio -> '—'", ui._fmt_lt_declarado({}) == "—")
check("todos None -> '—'",
      ui._fmt_lt_declarado({"lt_min": None, "lt_tip": None, "lt_max": None}) == "—")
check("parcial usa '·'",
      ui._fmt_lt_declarado({"lt_tip": 10}) == "· / 10 / · d",
      ui._fmt_lt_declarado({"lt_tip": 10}))

print("")
print("=== _fmt_lt_medido (el caso None es el critico) ===")
t, d, c = ui._fmt_lt_medido(None, 35)
check("sin muestras -> '—'", t == "—", t)
check("sin muestras: delta vacio", d == "")
check("sin muestras: nada es None", t is not None and d is not None and c is not None)

t, d, c = ui._fmt_lt_medido(27.0, 35)
check("27 vs 35 -> '27 d'", t == "27 d", t)
check("llega antes: delta negativo", d == "-8 vs 35", d)
check("llega antes: color verde", c == ui._VERDE)

t, d, c = ui._fmt_lt_medido(42.0, 35)
check("tarda mas: delta positivo", d == "+7 vs 35", d)
check("tarda mas: color rojo", c == ui._ROJO)

t, d, c = ui._fmt_lt_medido(35.0, 35)
check("igual al declarado -> 'en linea'", d == "en linea", d)

t, d, c = ui._fmt_lt_medido(27.0, None)
check("medido sin lt_tip declarado no explota", t == "27 d" and d == "", (t, d))

print("")
print("=== _fmt_fill_rate ===")
t, c = ui._fmt_fill_rate(None)
check("None -> '—'", t == "—", t)
check("None -> color gris", c == ui._GRIS)
check("0.8 -> '80%'", ui._fmt_fill_rate(0.8)[0] == "80%", ui._fmt_fill_rate(0.8)[0])
check("1.0 -> '100%' verde",
      ui._fmt_fill_rate(1.0) == ("100%", ui._VERDE), ui._fmt_fill_rate(1.0))
check("0.5 -> rojo", ui._fmt_fill_rate(0.5)[1] == ui._ROJO)
check("0.0 -> '0%' (no se confunde con None)",
      ui._fmt_fill_rate(0.0)[0] == "0%", ui._fmt_fill_rate(0.0)[0])

print("")
print("=== ningun helper devuelve None ===")
salidas = [
    ui._fmt_num(None), ui._fmt_lt_declarado({}),
    *ui._fmt_lt_medido(None, None), *ui._fmt_fill_rate(None),
    ui._celda("x"),
]
check("todas las salidas son str",
      all(isinstance(s, str) for s in salidas),
      [type(s).__name__ for s in salidas])

print("")
print("=" * 62)
print("RESULTADO: " + str(PASS) + " passed, " + str(FAIL) + " failed")
print("=" * 62)

shutil.rmtree(TMP_ROOT, ignore_errors=True)
print("cleanup: " + ("OK" if not TMP_ROOT.exists() else "QUEDO BASURA"))
sys.exit(1 if FAIL else 0)
