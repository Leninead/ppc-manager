---
tipo: sop
actualizado: 2026-07-22
version: v1.1
tags: [streamlit, apptest, testing, gotchas]
---

# SOP — Gotchas Streamlit (Agency OS)

Catálogo de trampas conocidas de Streamlit / AppTest en el Agency OS. Numeración
correlativa: al agregar un gotcha nuevo, continuá la secuencia — NO reinicies.

---

## 1. `AppTest.from_function` se rompe bajo pytest

La extracción de fuente (`inspect.getsourcelines`) sobre una función de un módulo
reescrito por el assertion-rewriting de pytest produce un script vacío: la app
renderiza 0 elementos SIN lanzar excepción. `at.exception` vacío y
`len(at.tabs) == 0` — falso negativo silencioso. Standalone funciona; solo falla
dentro de pytest.

**Fix:** usar `AppTest.from_string(SCRIPT)` con el script como string literal.

---

## 2. AppTest 1.43.2 no expone `download_button`

Ni como accesor propio (`at.download_button` → AttributeError) ni dentro de
`at.button`. Para validar que un bloque con download corrió, usar otras señales del
mismo bloque (markdown o botón regular) + `at.exception` vacío.

---

## 3. `st.file_uploader` reemite el archivo en cada rerun

Sin guarda, cada rerun re-inserta el mismo upload. Fix: firma
`f"{name}:{len(bytes)}"` en session_state, y procesar solo si cambió.

---

## 4. `st.text_area` exige `height >= 68px`

Un valor menor (ej. 60) lanza `StreamlitAPIException` en runtime. No lo detecta
`py_compile` — solo aparece al renderizar o en AppTest.

---

## 5. Selectbox con `on_change` no sirve si el cambio necesita confirmación

`on_change` persiste inmediatamente; un flujo que requiere un paso intermedio
(ej. razón obligatoria antes de aplicar) necesita comparar el valor seleccionado
contra el actual y decidir en el CUERPO del render, no en el callback. Patrón mixto
válido: `on_change` para los cambios directos, comparación + botón de confirmación
para los que necesitan validación.

---

## 6. Jitter en scatter Plotly: función determinista del índice, no `random`

Con `random`, cada rerun de Streamlit mueve los puntos. Fórmula estable:
`((i * 37) % 11 - 5) / 25.0`.
