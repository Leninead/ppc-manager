"""E2E tests del flujo UI de M29 Proposal Studio (Sesión B7 D5 / E5).

Cierra la deuda dejada por el incidente "edits fantasma" del 2026-05-25: pytest
unit cubría extract_blocks + merge_blocks + datadive_to_v3_block como funciones
puras, pero NO el path UI que conecta esas funciones con los botones
"Aplicar merge" / "Confirmar aplicación" + el flag de session_state
`ps_b7_confirm_apply_{pid}` + el save con auto-bump de versión.

Tres tests:
  1. B7 importer happy path — apply 2-clicks con b7_sample_v3v4.html,
     valida flag, merge sobre block['data'], version bumpeada, archivo en disco.
  2. B7 importer warning path — b7_sample_duplicate.html, valida que el warning
     duplicate_module_id_in_html sale visible y el botón "Aplicar merge" sigue
     habilitado (warnings no bloquean).
  3. DataDive → V3 — text_input ASIN + apply 2-clicks, valida que el V3 queda
     prefilled con las missing keywords del DataFrame y la version bumpea.

Decisiones de testing
---------------------
- AppTest 1.43.2 NO expone `file_uploader` como widget interactivo.
  Monkeypatcheamos `streamlit.file_uploader` para devolver un fake con
  `.getvalue()` + `.name`. Sigue siendo E2E: extract_blocks / merge_blocks /
  save_proposal corren reales (no se mockean), y los botones se clickean
  vía AppTest. La única costura es la inyección de bytes del archivo.
- PROPOSALS_DIR se patchea en ambos namespaces (proposal_paths y
  proposal_persistence) para redirigir el save a tmp_path. LocalJsonStorage
  lee la constante a call-time, así que no hace falta re-instanciar storage.
- El banner verde "vN → vN+1" se renderea ANTES de `st.rerun()` en
  `_execute_b7_merge_and_save`. Tras `.run()` el estado final refleja el rerun
  (el banner se "pisa"). Se valida indirectamente: el archivo v(N+1) con el
  merge correcto + el flag limpiado prueban que `_execute_b7_merge_and_save`
  corrió completo (incluido el render del banner).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROPOSAL_PATH = (
    REPO_ROOT / "data" / "sales" / "proposals"
    / "01fbf5c2-1fd9-44dd-9806-742e5deb8f71__v12.json"
)
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeUploadedFile:
    """Stub de UploadedFile.

    Solo necesitamos `.getvalue()` (lo usa el importer B7) y `.name` (lo usa
    DataDive cache key). NO replicamos el resto de la API real porque ningún
    consumidor del flow lo toca.
    """

    def __init__(self, data: bytes, name: str) -> None:
        self._data = data
        self.name = name

    def getvalue(self) -> bytes:
        return self._data


def _isolated_proposals_dir(monkeypatch, tmp_path: Path) -> Path:
    """Redirige PROPOSALS_DIR a tmp para no contaminar data/sales/proposals/."""
    new_dir = tmp_path / "proposals"
    new_dir.mkdir(parents=True, exist_ok=True)
    # Ambos bindings: el modulo paths y el binding importado en persistence.
    monkeypatch.setattr("core.proposal_paths.PROPOSALS_DIR", new_dir)
    monkeypatch.setattr("core.proposal_persistence.PROPOSALS_DIR", new_dir)
    return new_dir


def _seed_demo(proposals_dir: Path) -> dict:
    """Copia el demo proposal v12 al dir aislado y devuelve el dict cargado."""
    dst = proposals_dir / DEMO_PROPOSAL_PATH.name
    shutil.copy(DEMO_PROPOSAL_PATH, dst)
    return json.loads(dst.read_text(encoding="utf-8"))


def _patch_file_uploader(monkeypatch, fake: _FakeUploadedFile) -> None:
    """Cualquier llamada a `st.file_uploader(...)` devuelve `fake`."""
    monkeypatch.setattr("streamlit.file_uploader", lambda *a, **kw: fake)


def _find_button(at: AppTest, label_contains: str):
    """Devuelve el primer botón cuyo label contenga `label_contains`."""
    for b in at.button:
        if label_contains in (b.label or ""):
            return b
    labels = [b.label for b in at.button]
    raise AssertionError(
        f"No se encontró botón con label conteniendo {label_contains!r}. "
        f"Botones presentes: {labels}"
    )


def _has_warning_code_in_dataframe(at: AppTest, code: str) -> bool:
    """True si algún `st.dataframe` rendereado contiene `code` en col 'code'."""
    for el in at.dataframe:
        df = el.value
        if isinstance(df, pd.DataFrame) and "code" in df.columns:
            if (df["code"] == code).any():
                return True
        elif isinstance(df, list):
            # st.dataframe acepta list[dict]; AppTest lo normaliza a DataFrame
            # en .value, pero defensivamente cubrimos el caso.
            for row in df:
                if isinstance(row, dict) and row.get("code") == code:
                    return True
    return False


# ---------------------------------------------------------------------------
# Test 1 — Importer B7 happy path
# ---------------------------------------------------------------------------


def test_b7_importer_apply_happy_path(monkeypatch, tmp_path):
    """B7: subir v3v4 → 2-clicks apply → V3 data overwriteado + v12→v13."""
    iso_dir = _isolated_proposals_dir(monkeypatch, tmp_path)
    proposal = _seed_demo(iso_dir)
    pid = proposal["id"]
    v_before = proposal["version"]
    assert v_before == 12, "fixture seed cambió: ajustar test"

    fixture_bytes = (FIXTURES_DIR / "b7_sample_v3v4.html").read_bytes()
    _patch_file_uploader(monkeypatch, _FakeUploadedFile(fixture_bytes, "v3v4.html"))

    # AppTest.from_function serializa la función como script standalone:
    # los closures se pierden. Pasamos `proposal` vía args para que viaje
    # como argumento real a la app.
    def app(proposal_arg) -> None:
        from modules.pages.proposal_studio import _render_b7_importer_section
        _render_b7_importer_section(proposal_arg)

    at = AppTest.from_function(app, args=(proposal,))
    at.run()
    assert not at.exception, f"Excepción durante render inicial: {at.exception}"

    # El botón "Aplicar merge" debe estar habilitado (n_will_apply > 0:
    # el fixture v3v4 incluye V3 y V4, ambos están en el demo).
    apply_btn = _find_button(at, "Aplicar merge")
    assert apply_btn.disabled is False, "el botón apply estaba disabled"

    # Click #1: setea el flag y muta el botón.
    apply_btn.click().run()
    assert not at.exception, f"Excepción tras click apply: {at.exception}"

    flag_key = f"ps_b7_confirm_apply_{pid}"
    assert flag_key in at.session_state, (
        f"el flag {flag_key!r} no aparece en session_state tras Click #1"
    )
    assert at.session_state[flag_key] is True, (
        "el flag ps_b7_confirm_apply_{pid} no se seteó tras Click #1"
    )

    # Tras el click el botón debe haber mutado a "Confirmar aplicación".
    confirm_btn = _find_button(at, "Confirmar aplicación")

    # Click #2: ejecuta merge + save + flag=False + rerun.
    confirm_btn.click().run()
    assert not at.exception, f"Excepción tras click confirmar: {at.exception}"

    # Post-éxito: el flag debe estar limpiado.
    assert at.session_state[flag_key] is False, (
        "flag debió quedar en False tras éxito; "
        f"valor actual = {at.session_state[flag_key]!r}"
    )

    # File on disk: <id>__v13.json existe en el dir aislado.
    v_after = v_before + 1
    saved_path = iso_dir / f"{pid}__v{v_after}.json"
    assert saved_path.exists(), (
        f"esperaba archivo {saved_path.name} en {iso_dir}; "
        f"contenido del dir: {[p.name for p in iso_dir.iterdir()]}"
    )

    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved["version"] == v_after, (
        f"version del archivo guardado = {saved['version']}, esperaba {v_after}"
    )

    # V3 data fue overwriteado con el data del fixture (primer keyword conocido).
    v3 = next(b for b in saved["blocks"] if b.get("module_id") == "V3_seo_opportunity")
    mk = v3["data"].get("missing_keywords", [])
    assert len(mk) >= 1, "V3 missing_keywords debería tener al menos 1 item tras merge"
    assert mk[0]["keyword"] == "moringa powder organic", (
        "V3 data NO se overwriteó con la fixture; "
        f"primer kw = {mk[0].get('keyword')!r}"
    )

    # Identity fields preservados (contrato §6: merge solo afecta block['data']).
    v3_demo = next(
        b for b in proposal["blocks"]
        if b.get("module_id") == "V3_seo_opportunity"
    )
    assert v3["id"] == v3_demo["id"]
    assert v3["proposal_id"] == v3_demo["proposal_id"]
    assert v3["module_id"] == v3_demo["module_id"]
    assert v3["is_fixed"] == v3_demo["is_fixed"]
    assert v3.get("copy_overrides") == v3_demo.get("copy_overrides")


# ---------------------------------------------------------------------------
# Test 2 — Importer B7 warning path (duplicate module_id en HTML)
# ---------------------------------------------------------------------------


def test_b7_importer_duplicate_warning_does_not_break(monkeypatch, tmp_path):
    """B7 con HTML duplicate: warning visible, apply habilitado, sin crash."""
    iso_dir = _isolated_proposals_dir(monkeypatch, tmp_path)
    proposal = _seed_demo(iso_dir)

    fixture_bytes = (FIXTURES_DIR / "b7_sample_duplicate.html").read_bytes()
    _patch_file_uploader(monkeypatch, _FakeUploadedFile(fixture_bytes, "dup.html"))

    def app(proposal_arg) -> None:
        from modules.pages.proposal_studio import _render_b7_importer_section
        _render_b7_importer_section(proposal_arg)

    at = AppTest.from_function(app, args=(proposal,))
    at.run()

    # 1. Render no crashea (covers el riesgo del incidente 2026-05-25).
    assert not at.exception, f"Excepción durante render: {at.exception}"

    # 2. Warning duplicate_module_id_in_html sale en el dataframe de warnings.
    assert _has_warning_code_in_dataframe(at, "duplicate_module_id_in_html"), (
        "no se encontró el warning 'duplicate_module_id_in_html' en ningún "
        "dataframe rendereado por el importer"
    )

    # 3. Apply sigue habilitado (warnings NO bloquean — solo errors).
    apply_btn = _find_button(at, "Aplicar merge")
    assert apply_btn.disabled is False, (
        "el botón apply quedó disabled con un warning duplicate; debería "
        "estar habilitado porque warnings no bloquean"
    )


# ---------------------------------------------------------------------------
# Test 3 — DataDive → V3 apply path
# ---------------------------------------------------------------------------


def test_datadive_v3_apply_path(monkeypatch, tmp_path):
    """DataDive: text_input ASIN + apply 2-clicks → V3 prefilled + v12→v13."""
    iso_dir = _isolated_proposals_dir(monkeypatch, tmp_path)
    proposal = _seed_demo(iso_dir)
    pid = proposal["id"]
    v_before = proposal["version"]

    client_asin = "B0CLIENT01"

    # Hand-built MKL: dos kws que deberían entrar en missing_keywords.
    # - rank None  → entra (cliente no rankea)
    # - rank 50    → entra (rank > 30 = débil)
    fake_mkl_df = pd.DataFrame([
        {"Search Term": "missing kw alpha", "SV": 1000,
         "Launch Score": 7.5, client_asin: None},
        {"Search Term": "missing kw beta", "SV": 500,
         "Launch Score": 6.0, client_asin: 50},
    ])
    competitor_asins = [client_asin]

    # Sustituimos el parser cacheado por uno determinista: devuelve el
    # DataFrame y la lista de ASINs sin pasar por openpyxl.
    monkeypatch.setattr(
        "modules.pages.proposal_studio._dd_parse_mkl_cached",
        lambda data, name: (fake_mkl_df, competitor_asins),
    )

    # File uploader fake (los bytes no se usan porque el parser está
    # monkeypatched, pero el uploader debe devolver un objeto truthy).
    _patch_file_uploader(
        monkeypatch,
        _FakeUploadedFile(b"\x00\x01ignored", "mkl.xlsx"),
    )

    def app(proposal_arg) -> None:
        from modules.pages.proposal_studio import (
            _render_datadive_importer_section,
        )
        _render_datadive_importer_section(proposal_arg)

    at = AppTest.from_function(app, args=(proposal,))
    at.run()
    assert not at.exception, f"Excepción durante render inicial: {at.exception}"

    # Primer run: default_asin del demo puede no matchear el regex,
    # con lo cual la sección se cierra con st.info antes del uploader.
    # Seteamos el text_input al ASIN válido y volvemos a correr.
    assert len(at.text_input) >= 1, (
        "esperaba al menos un text_input (ASIN del cliente)"
    )
    at.text_input[0].set_value(client_asin).run()
    assert not at.exception, f"Excepción tras set ASIN: {at.exception}"

    # Ahora el gate pasó, el uploader rindió el FakeUF, el parser fake
    # devolvió el df y el apply flow está visible.
    apply_btn = _find_button(at, "Aplicar merge")
    assert apply_btn.disabled is False, (
        "apply estaba disabled — verificá que V3 esté en el target_proposal"
    )

    # Click #1: setea flag.
    apply_btn.click().run()
    assert not at.exception, f"Excepción tras click apply: {at.exception}"

    flag_key = f"ps_b7_confirm_apply_{pid}"
    assert flag_key in at.session_state and at.session_state[flag_key] is True

    # Click #2: ejecuta merge + save.
    confirm_btn = _find_button(at, "Confirmar aplicación")
    confirm_btn.click().run()
    assert not at.exception, f"Excepción tras confirmar: {at.exception}"

    # File on disk con version bumpeada.
    v_after = v_before + 1
    saved_path = iso_dir / f"{pid}__v{v_after}.json"
    assert saved_path.exists(), (
        f"esperaba {saved_path.name}; "
        f"contenido del dir: {[p.name for p in iso_dir.iterdir()]}"
    )

    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved["version"] == v_after

    # V3 prefilled con las missing keywords del DataFrame.
    v3 = next(b for b in saved["blocks"] if b.get("module_id") == "V3_seo_opportunity")
    mk = v3["data"].get("missing_keywords", [])
    kws = {m.get("keyword") for m in mk}
    assert "missing kw alpha" in kws, (
        f"'missing kw alpha' (rank None) debería estar en V3.data; "
        f"keywords presentes: {sorted(kws)}"
    )
    assert "missing kw beta" in kws, (
        f"'missing kw beta' (rank 50 > 30) debería estar en V3.data; "
        f"keywords presentes: {sorted(kws)}"
    )
