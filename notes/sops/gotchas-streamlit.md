---
tipo: sop
actualizado: 2026-07-21
version: v1.0
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
