"""Verifica que los dialogos de supply_proveedores.py sobrevivan al rerun.

El bug que cubre: abrir un dialogo desde `if st.button(...): _dialog(...)` lo deja
vivo un solo run. En el rerun que trae lo que el usuario tipeo, el boton devuelve
False, el dialogo no se re-renderiza, y Streamlit lo marca stale y borra el estado
de sus widgets. El fix es anclar el dialogo en session_state y renderizarlo al
final de render().

A diferencia de smoke_supply_ui_fmt.py (funciones puras), este SI levanta el
script runner de Streamlit via AppTest, que es la unica forma de observar el
rerun. Escribe en un data root temporal y lo limpia al final.

LIMITACION DE AppTest EN 1.43.2 — verificada en un probe minimo sin codigo de
este repo: AppTest no refleja el `st.rerun()` lanzado DESDE DENTRO de un dialogo.
Tras el click que cierra, la bandera de session_state baja bien y los efectos en
disco ocurren, pero el element tree sigue mostrando los widgets del dialogo, y el
`.run()` siguiente revienta con KeyError sobre ese widget stale. Por eso el cierre
se verifica por BANDERA + DISCO (que si son observables y son lo que importa) y
nunca contando elementos ni encadenando otro run sobre la misma instancia: lo que
va despues de un cierre arranca con un AppTest nuevo.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP_ROOT = Path(tempfile.mkdtemp(prefix="supply_dlg_"))
os.environ["AGENCY_OS_DATA_DIR"] = str(TMP_ROOT)
# Raiz del repo derivada de la ubicacion del script (scripts/ -> repo).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamlit.testing.v1 import AppTest  # noqa: E402

from core.supply.paths import PROVEEDORES_FILE, ensure_dirs  # noqa: E402
from core.supply.persistence import (  # noqa: E402
    get_proveedor,
    list_proveedores,
    save_proveedor,
)
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


def _app() -> None:
    """Entrypoint que AppTest ejecuta: solo la pantalla, sin app.py ni auth."""
    from modules.pages import supply_proveedores

    supply_proveedores.render()


def _fresh(timeout: int = 60) -> "AppTest":
    """AppTest nuevo -> session_state limpio. Un test, una instancia."""
    return AppTest.from_function(_app, default_timeout=timeout).run()


def _reset_disco() -> None:
    """Borra el maestro para que cada bloque arranque desde un estado conocido."""
    if PROVEEDORES_FILE.exists():
        PROVEEDORES_FILE.unlink()


ensure_dirs()


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T0. la pantalla levanta ===")
_reset_disco()
at = _fresh()
check("sin excepciones en el primer run", not at.exception, [str(e) for e in at.exception])
check("boton de alta presente", len(at.button(key="supply_prov_btn_alta")) == 1
      if hasattr(at.button(key="supply_prov_btn_alta"), "__len__")
      else at.button(key="supply_prov_btn_alta") is not None)
check("sin proveedores: 0 text_input en la pagina base", len(at.text_input) == 0,
      len(at.text_input))


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T1. ALTA: el dialogo sobrevive al rerun (el bug) ===")
_reset_disco()
at = _fresh()
at.button(key="supply_prov_btn_alta").click().run()
check("se abre: aparecen los campos", len(at.text_input) >= 2, len(at.text_input))
check("bandera de alta en session_state",
      at.session_state[ui._KEY_ALTA_ABIERTA] is True
      if ui._KEY_ALTA_ABIERTA in at.session_state else False)

at.text_input[0].input("Shenzhen Tools").run()
check("SIGUE ABIERTO tras tipear (el rerun no lo mata)", len(at.text_input) >= 2,
      f"quedaron {len(at.text_input)} inputs")
check("el nombre tipeado sobrevive",
      len(at.text_input) >= 1 and at.text_input[0].value == "Shenzhen Tools",
      at.text_input[0].value if len(at.text_input) else "sin inputs")

# Un segundo rerun, ahora sobre un number_input: el estado tiene que aguantar
# tambien lo ya tipeado en otro widget.
at.number_input[1].set_value(10).run()
check("sigue abierto tras tocar un number_input", len(at.text_input) >= 2,
      len(at.text_input))
check("el nombre sobrevive al segundo rerun",
      len(at.text_input) >= 1 and at.text_input[0].value == "Shenzhen Tools",
      at.text_input[0].value if len(at.text_input) else "sin inputs")
check("el LT tipico sobrevive",
      len(at.number_input) >= 2 and at.number_input[1].value == 10,
      at.number_input[1].value if len(at.number_input) >= 2 else "sin inputs")

at.button(key="supply_prov_alta_confirm").click().run()
_guardado = [p for p in list_proveedores() if p.get("nombre") == "Shenzhen Tools"]
check("guarda el proveedor con lo tipeado", len(_guardado) == 1, list_proveedores())
check("guarda el LT tipico elegido, no el default",
      bool(_guardado) and _guardado[0].get("lt_tip") == 10,
      _guardado[0].get("lt_tip") if _guardado else None)
check("al guardar baja la bandera (= se cierra)",
      ui._KEY_ALTA_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_ALTA_ABIERTA])


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T2. ALTA: cancelar cierra y no guarda ===")
_reset_disco()
at = _fresh()
at.button(key="supply_prov_btn_alta").click().run()
at.text_input[0].input("Descartable").run()
at.button(key="supply_prov_alta_cancel").click().run()
check("cancelar baja la bandera (= se cierra)",
      ui._KEY_ALTA_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_ALTA_ABIERTA])
check("cancelar no guarda nada", list_proveedores() == [], list_proveedores())

# Reabrir arranca limpio: sin key en los widgets, no hay valor pegado. Instancia
# nueva porque no se puede encadenar otro run despues de un cierre (ver cabecera).
at = _fresh()
at.button(key="supply_prov_btn_alta").click().run()
check("reabrir arranca con el nombre vacio",
      len(at.text_input) >= 1 and at.text_input[0].value == "",
      at.text_input[0].value if len(at.text_input) else "sin inputs")


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T3. EDITAR: precarga, sobrevive al rerun y guarda ===")
_reset_disco()
save_proveedor({"nombre": "Acme SA", "pais": "China", "lt_min": 5, "lt_tip": 10,
                "lt_max": 20, "revision_dias": 7})
_pid = list_proveedores()[0]["id"]

at = _fresh()
at.button(key=f"supply_prov_edit_{_pid}").click().run()
check("se abre el editar", len(at.text_input) >= 2, len(at.text_input))
check("precarga el nombre",
      len(at.text_input) >= 1 and at.text_input[0].value == "Acme SA",
      at.text_input[0].value if len(at.text_input) else "sin inputs")
check("precarga el pais",
      len(at.text_input) >= 2 and at.text_input[1].value == "China",
      at.text_input[1].value if len(at.text_input) >= 2 else "sin inputs")
check("precarga el LT tipico",
      len(at.number_input) >= 2 and at.number_input[1].value == 10,
      at.number_input[1].value if len(at.number_input) >= 2 else "sin inputs")
check("la bandera lleva el prov_id",
      at.session_state[ui._KEY_EDITAR_ABIERTA] == _pid
      if ui._KEY_EDITAR_ABIERTA in at.session_state else False)

at.text_input[1].input("Vietnam").run()
check("SIGUE ABIERTO tras tipear", len(at.text_input) >= 2, len(at.text_input))
check("el pais tipeado sobrevive",
      len(at.text_input) >= 2 and at.text_input[1].value == "Vietnam",
      at.text_input[1].value if len(at.text_input) >= 2 else "sin inputs")
check("el nombre precargado no se pierde",
      len(at.text_input) >= 1 and at.text_input[0].value == "Acme SA",
      at.text_input[0].value if len(at.text_input) else "sin inputs")

at.number_input[2].set_value(25).run()
check("sigue abierto tras cambiar el LT maximo", len(at.text_input) >= 2,
      len(at.text_input))
check("el pais sobrevive al segundo rerun",
      len(at.text_input) >= 2 and at.text_input[1].value == "Vietnam",
      at.text_input[1].value if len(at.text_input) >= 2 else "sin inputs")

at.button(key=f"supply_prov_edit_confirm_{_pid}").click().run()
_p = get_proveedor(_pid)
check("guarda el pais editado", _p and _p.get("pais") == "Vietnam",
      _p.get("pais") if _p else None)
check("guarda el LT maximo editado", _p and _p.get("lt_max") == 25,
      _p.get("lt_max") if _p else None)
check("no duplica: sigue habiendo 1 proveedor", len(list_proveedores()) == 1,
      len(list_proveedores()))
check("conserva el id", _p and _p.get("id") == _pid)
check("al guardar baja la bandera (= se cierra)",
      ui._KEY_EDITAR_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_EDITAR_ABIERTA])


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T4. EDITAR: cancelar no persiste el cambio ===")
_reset_disco()
save_proveedor({"nombre": "Bravo Ltd", "pais": "India", "revision_dias": 7})
_pid = list_proveedores()[0]["id"]

at = _fresh()
at.button(key=f"supply_prov_edit_{_pid}").click().run()
at.text_input[1].input("Peru").run()
at.button(key=f"supply_prov_edit_cancel_{_pid}").click().run()
check("cancelar baja la bandera (= se cierra)",
      ui._KEY_EDITAR_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_EDITAR_ABIERTA])
check("cancelar no persiste el pais", get_proveedor(_pid).get("pais") == "India",
      get_proveedor(_pid).get("pais"))


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T5. ARCHIVAR: sobrevive al rerun y archiva ===")
_reset_disco()
save_proveedor({"nombre": "Charlie Co", "revision_dias": 7})
_pid = list_proveedores()[0]["id"]

at = _fresh()
at.button(key=f"supply_prov_arch_{_pid}").click().run()
check("se abre el confirmar",
      len(at.button(key=f"supply_prov_arch_confirm_{_pid}")) == 1
      if hasattr(at.button(key=f"supply_prov_arch_confirm_{_pid}"), "__len__")
      else at.button(key=f"supply_prov_arch_confirm_{_pid}") is not None)
check("la bandera lleva el prov_id",
      at.session_state[ui._KEY_ARCHIVAR_ABIERTA] == _pid
      if ui._KEY_ARCHIVAR_ABIERTA in at.session_state else False)

# Un rerun cualquiera de la pagina (el checkbox de archivados) no debe matarlo.
at.checkbox(key="supply_prov_ver_inactivos").check().run()
check("SIGUE ABIERTO tras un rerun de la pagina",
      ui._KEY_ARCHIVAR_ABIERTA in at.session_state
      and at.session_state[ui._KEY_ARCHIVAR_ABIERTA] == _pid)

at.button(key=f"supply_prov_arch_confirm_{_pid}").click().run()
check("archiva: activo=False", get_proveedor(_pid).get("activo") is False,
      get_proveedor(_pid).get("activo"))
check("no lo borra: sigue en disco", get_proveedor(_pid) is not None)
check("desaparece de la lista por defecto", list_proveedores() == [],
      list_proveedores())
check("aparece con incluir_inactivos", len(list_proveedores(incluir_inactivos=True)) == 1)
check("al archivar baja la bandera",
      ui._KEY_ARCHIVAR_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_ARCHIVAR_ABIERTA])


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T6. ARCHIVAR: cancelar deja el proveedor activo ===")
_reset_disco()
save_proveedor({"nombre": "Delta SRL", "revision_dias": 7})
_pid = list_proveedores()[0]["id"]

at = _fresh()
at.button(key=f"supply_prov_arch_{_pid}").click().run()
at.button(key=f"supply_prov_arch_cancel_{_pid}").click().run()
check("cancelar no archiva", get_proveedor(_pid).get("activo") is not False,
      get_proveedor(_pid).get("activo"))
check("cancelar baja la bandera",
      ui._KEY_ARCHIVAR_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_ARCHIVAR_ABIERTA])


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T7. un solo dialogo por run (Streamlit no admite dos) ===")
_reset_disco()
save_proveedor({"nombre": "Echo SA", "revision_dias": 7})
_pid = list_proveedores()[0]["id"]

at = _fresh()
at.button(key=f"supply_prov_edit_{_pid}").click().run()
check("editar abierto", at.session_state[ui._KEY_EDITAR_ABIERTA] == _pid
      if ui._KEY_EDITAR_ABIERTA in at.session_state else False)
check("alta NO abierta a la vez", ui._KEY_ALTA_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_ALTA_ABIERTA])
check("archivar NO abierto a la vez", ui._KEY_ARCHIVAR_ABIERTA not in at.session_state
      or not at.session_state[ui._KEY_ARCHIVAR_ABIERTA])
check("sin excepciones con un dialogo abierto", not at.exception,
      [str(e) for e in at.exception])


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T8. lista vacia: el alta sigue funcionando (sin early-return) ===")
_reset_disco()
at = _fresh()
check("empty state: sin proveedores", list_proveedores() == [])
at.button(key="supply_prov_btn_alta").click().run()
check("el dialogo de alta abre con la lista vacia", len(at.text_input) >= 2,
      len(at.text_input))
at.text_input[0].input("Primero").run()
check("sobrevive al rerun con la lista vacia", len(at.text_input) >= 2,
      len(at.text_input))
check("el nombre sobrevive",
      len(at.text_input) >= 1 and at.text_input[0].value == "Primero",
      at.text_input[0].value if len(at.text_input) else "sin inputs")
at.button(key="supply_prov_alta_confirm").click().run()
check("crea el primer proveedor desde el empty state",
      len(list_proveedores()) == 1, list_proveedores())


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T9. validacion: el dialogo NO se cierra si el guardado falla ===")
_reset_disco()
at = _fresh()
at.button(key="supply_prov_btn_alta").click().run()
# Nombre vacio -> _guardar devuelve False y hay que quedarse en el modal.
at.button(key="supply_prov_alta_confirm").click().run()
check("sin nombre no guarda", list_proveedores() == [], list_proveedores())
check("el dialogo sigue abierto para corregir", len(at.text_input) >= 2,
      len(at.text_input))
check("muestra el error", any("nombre" in str(e.value).lower() for e in at.error),
      [str(e.value) for e in at.error])

# Y desde ahi se puede corregir sin reabrir.
at.text_input[0].input("Corregido").run()
at.button(key="supply_prov_alta_confirm").click().run()
check("corregir y guardar funciona", len(list_proveedores()) == 1,
      list_proveedores())


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=== T10. LT invalido: error del persistence sin cerrar el modal ===")
_reset_disco()
at = _fresh()
at.button(key="supply_prov_btn_alta").click().run()
at.text_input[0].input("Invalido SA").run()
at.number_input[0].set_value(20).run()   # lt_min
at.number_input[1].set_value(5).run()    # lt_tip < lt_min -> ValueError
at.button(key="supply_prov_alta_confirm").click().run()
check("no guarda con LT incoherente", list_proveedores() == [], list_proveedores())
check("el dialogo sigue abierto", len(at.text_input) >= 2, len(at.text_input))
check("muestra el error del persistence", len(at.error) >= 1,
      [str(e.value) for e in at.error])


# ─────────────────────────────────────────────────────────────────────────
print("")
print("=" * 62)
print(f"RESULTADO DIALOGOS: {PASS} passed, {FAIL} failed")
print("=" * 62)

shutil.rmtree(TMP_ROOT, ignore_errors=True)
print("cleanup: root eliminado OK" if not TMP_ROOT.exists() else "cleanup: FALLO")

sys.exit(1 if FAIL else 0)
