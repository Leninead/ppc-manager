"""M31 F6.2 + F6.3 — Tests del forecast por-ASIN + helpers de tabla/totales.

Cubre las funciones PURAS de F6.3 (`_period_to_date`, `_asin_history_to_engine_rows`,
`_forecast_single_asin`) y los helpers PUROS de F6.2 (`_build_asin_child_df`,
`_build_asin_parent_df`, `_asin_account_totals`). NO tocan Streamlit — sólo lógica.

Los tests reales reusan los 3 fixtures Dermaglos may/jun/jul 2026 (gitignored,
mismo skip guard que test_forecast_asin_accumulate.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures reales (gitignored — skip si falta alguno)
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures" / "real"
_CSVS = {p: _FIXTURES / f"dermaglos_asin_bychild_{p}.csv"
         for p in ("2026-05", "2026-06", "2026-07")}

_skip_no_fixtures = pytest.mark.skipif(
    not all(f.exists() for f in _CSVS.values()),
    reason="fixtures reales multi-mes gitignored ausentes")


def _load_model():
    snaps = [rf._parse_asin_report(str(_CSVS[p]), p)
             for p in ("2026-05", "2026-06", "2026-07")]
    return rf._accumulate_asin_snapshots(snaps)


_HERO = "B0CYLMJJJC"


# ─────────────────────────────────────────────────────────────────────────────
# Puros (sin fixtures)
# ─────────────────────────────────────────────────────────────────────────────

def test_period_to_date():
    assert rf._period_to_date("2026-05") == "2026-05-01"


def test_history_to_engine_rows_shape():
    history = [
        {"period": "2026-06", "revenue": 200.0, "units": 20.0,
         "sessions": 100.0, "unit_session_pct": 20.0},
        {"period": "2026-05", "revenue": 100.0, "units": 10.0,
         "sessions": 50.0, "unit_session_pct": 20.0},
    ]
    rows = rf._asin_history_to_engine_rows(history)
    # Ordenado asc por date (mayo antes que junio pese al orden de entrada).
    assert [r["date"] for r in rows] == ["2026-05-01", "2026-06-01"]
    for src, r in zip(sorted(history, key=lambda h: h["period"]), rows):
        assert set(r.keys()) == {"date", "revenue", "units", "sessions", "cvr"}
        assert r["cvr"] == src["unit_session_pct"]   # cvr == unit_session_pct


def test_forecast_single_asin_insufficient():
    history = [{"period": "2026-07", "revenue": 100.0, "units": 10.0,
                "sessions": 50.0, "unit_session_pct": 20.0}]
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    assert rf._forecast_single_asin(history, opts) == []


# ─────────────────────────────────────────────────────────────────────────────
# Reales (@_skip_no_fixtures)
# ─────────────────────────────────────────────────────────────────────────────

@_skip_no_fixtures
def test_forecast_single_asin_hero_real():
    model = _load_model()
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc = rf._forecast_single_asin(model[_HERO]["history"], opts)
    assert len(fc) == opts["horizon"]
    for row in fc:
        assert "revenue" in row
        assert "date" in row


@_skip_no_fixtures
def test_build_asin_child_df_real():
    model = _load_model()
    df = rf._build_asin_child_df(model)
    assert len(df) == 9                       # 9 ASINs
    assert df.isna().sum().sum() == 0         # sin NaN tras relleno con ''


@_skip_no_fixtures
def test_asin_account_totals_real():
    model = _load_model()
    totals = rf._asin_account_totals(model)
    assert [t["period"] for t in totals] == ["2026-05", "2026-06", "2026-07"]
    # Revenue del período más reciente > 0.
    assert totals[-1]["revenue"] > 0
    # Los totales sumados coinciden con la suma manual del model.
    manual_rev_jul = sum(
        h["revenue"] for node in model.values() for h in node["history"]
        if h["period"] == "2026-07"
    )
    assert totals[-1]["revenue"] == pytest.approx(manual_rev_jul)


@_skip_no_fixtures
def test_forecast_single_asin_partial_july():
    snaps = [rf._parse_asin_report(str(_CSVS[p]), p)
             for p in ("2026-05", "2026-06", "2026-07")]
    model = rf._accumulate_asin_snapshots(
        snaps, partial_periods={"2026-07": {"days_covered": 10}})
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    # El flag partial/days_covered NO debe romper el mapeo a engine rows
    # (el motor sólo usa date/revenue/units/sessions/cvr).
    fc = rf._forecast_single_asin(model[_HERO]["history"], opts)
    assert len(fc) == opts["horizon"]


# ─────────────────────────────────────────────────────────────────────────────
# F6.3b — exclusión de meses parciales del motor
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_excludes_partial_month():
    """Un mes partial=True NO debe influir en los VALORES del forecast: [A,B] y
    [A,B,C-partial] con A,B idénticos producen la MISMA secuencia de revenue (el
    crecimiento se ancla a los completos). Post-F6.3c las FECHAS sí difieren: el
    parcial corre el cursor un mes (fc_abc arranca un mes después que fc_ab)."""
    A = {"period": "2026-05", "revenue": 1000.0, "units": 100.0,
         "sessions": 500.0, "unit_session_pct": 20.0}
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    C_partial = {"period": "2026-07", "revenue": 300.0, "units": 30.0,
                 "sessions": 150.0, "unit_session_pct": 20.0, "partial": True}
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc_ab = rf._forecast_single_asin([A, B], opts)
    fc_abc = rf._forecast_single_asin([A, B, C_partial], opts)
    assert fc_ab, "control [A,B] no debería estar vacío"
    # Valores idénticos: el parcial no altera el crecimiento MoM.
    assert [r["revenue"] for r in fc_abc] == [r["revenue"] for r in fc_ab]
    # F6.3c: el parcial corre el cursor → fc_ab arranca jul, fc_abc arranca ago.
    assert [r["date"] for r in fc_ab] == ["2026-07-01", "2026-08-01", "2026-09-01"]
    assert [r["date"] for r in fc_abc] == ["2026-08-01", "2026-09-01", "2026-10-01"]


def test_forecast_partial_leaves_under_two_complete():
    """[B completo, C partial=True] → solo 1 completo → devuelve []."""
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    C_partial = {"period": "2026-07", "revenue": 300.0, "units": 30.0,
                 "sessions": 150.0, "unit_session_pct": 20.0, "partial": True}
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    assert rf._forecast_single_asin([B, C_partial], opts) == []


# ─────────────────────────────────────────────────────────────────────────────
# F6.3c — arranque en el mes siguiente al último CARGADO (incluye parcial)
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_starts_after_last_loaded_including_partial():
    """F6.3c: con un mes parcial al final, el forecast arranca en el mes SIGUIENTE
    al parcial (no re-proyecta el parcial ni el último completo)."""
    A = {"period": "2026-05", "revenue": 1000.0, "units": 100.0,
         "sessions": 500.0, "unit_session_pct": 20.0}
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    C_partial = {"period": "2026-07", "revenue": 300.0, "units": 30.0,
                 "sessions": 150.0, "unit_session_pct": 20.0, "partial": True}
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc = rf._forecast_single_asin([A, B, C_partial], opts)
    assert fc, "debería proyectar con may+jun completos"
    assert fc[0]["date"] == "2026-08-01"   # mes sig al último cargado (jul parcial)
    assert [f["date"] for f in fc] == ["2026-08-01", "2026-09-01", "2026-10-01"]


def test_forecast_no_partial_starts_after_last_complete():
    """F6.3c no-op: sin meses parciales, el forecast arranca en el mes siguiente
    al último completo (idéntico al comportamiento pre-F6.3c)."""
    A = {"period": "2026-05", "revenue": 1000.0, "units": 100.0,
         "sessions": 500.0, "unit_session_pct": 20.0}
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    opts = {"horizon": 2, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc = rf._forecast_single_asin([A, B], opts)
    assert fc[0]["date"] == "2026-07-01"   # sin parcial → mes sig a junio
    assert [f["date"] for f in fc] == ["2026-07-01", "2026-08-01"]


def test_generate_forecast_start_from_none_is_noop():
    """El MVP global NO pasa start_from → el motor arranca en el mes siguiente a
    rows[-1] como siempre. Blindaje anti-regresión del path MVP."""
    rows = [
        {"date": "2026-05-01", "revenue": 1000.0, "units": 100.0, "sessions": 500.0, "cvr": 20.0},
        {"date": "2026-06-01", "revenue": 1100.0, "units": 110.0, "sessions": 550.0, "cvr": 20.0},
    ]
    seas = {"enabled": False, "indices": [1.0] * 12}
    opts = {"horizon": 2, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc_default = rf.generate_forecast(opts, rows, seas, "auto")
    fc_explicit_none = rf.generate_forecast(opts, rows, seas, "auto", start_from=None)
    assert fc_default[0]["date"] == "2026-07-01"
    assert [f["date"] for f in fc_default] == [f["date"] for f in fc_explicit_none]
    assert [f["revenue"] for f in fc_default] == [f["revenue"] for f in fc_explicit_none]


@_skip_no_fixtures
def test_forecast_hero_real_stable_not_crashing():
    """F6.3c: con julio marcado partial, el crecimiento MoM se ancla a may+jun
    completos (1818→1897, +~4%), pero el forecast ARRANCA en el mes siguiente al
    último CARGADO (julio parcial) → 2026-08, NO en julio (que las tablas ya
    muestran como real parcial). Revenue del primer mes sigue >1500 (~2066), no el
    ~287 desplomado que producía el parcial pre-F6.3b."""
    snaps = [rf._parse_asin_report(str(_CSVS[p]), p)
             for p in ("2026-05", "2026-06", "2026-07")]
    model = rf._accumulate_asin_snapshots(
        snaps, partial_periods={"2026-07": {"days_covered": 10}})
    fc = rf._forecast_single_asin(
        model[_HERO]["history"],
        {"horizon": 3, "momWindow": 2, "blend": 50})
    assert fc, "el hero debería proyectar con may+jun completos"
    assert fc[0]["date"] == "2026-08-01"   # F6.3c: mes sig al último CARGADO (jul parcial) → agosto
    assert fc[0]["revenue"] > 1500         # crecimiento sigue anclado a may+jun; solo se corre el cursor


# ─────────────────────────────────────────────────────────────────────────────
# _build_asin_parent_df — título del parent (E5)
# ─────────────────────────────────────────────────────────────────────────────
#
# Un parent agrupa varios childs con títulos distintos. La regla es: usar el
# título del child cuyo asin == parent_asin (el padre real del catálogo); si ese
# child no está en el modelo, caer al primer título no vacío del grupo.

def _node(parent: str, title: str, rev_by_period: dict) -> dict:
    """Nodo del modelo con el shape que produce el merge por-ASIN."""
    return {
        "parent_asin": parent,
        "title": title,
        "history": [
            {"period": p, "revenue": r, "units": 1.0, "sessions": 10.0,
             "unit_session_pct": 10.0}
            for p, r in sorted(rev_by_period.items())
        ],
    }


def _parent_row(df, parent_asin: str) -> dict:
    rows = df[df["parent_asin"] == parent_asin]
    assert len(rows) == 1, f"esperaba 1 fila para {parent_asin}, hay {len(rows)}"
    return rows.iloc[0].to_dict()


def test_build_asin_parent_df_has_title_column_first():
    """La columna title existe y va primera después de parent_asin (como Child)."""
    model = {"P1": _node("P1", "Padre uno", {"2026-06": 100.0})}
    df = rf._build_asin_parent_df(model, ["2026-06"])
    assert "title" in df.columns
    assert list(df.columns)[:2] == ["parent_asin", "title"]


def test_build_asin_parent_df_uses_real_parent_title():
    """Caso 1: existe el child cuyo asin == parent_asin → gana ESE título."""
    model = {
        # El padre real, presente en el catálogo con su propio título.
        "P1": _node("P1", "TITULO DEL PADRE", {"2026-06": 10.0}),
        "C1": _node("P1", "Variante roja", {"2026-06": 20.0}),
        "C2": _node("P1", "Variante azul", {"2026-06": 30.0}),
    }
    df = rf._build_asin_parent_df(model, ["2026-06"])
    row = _parent_row(df, "P1")
    assert row["title"] == "TITULO DEL PADRE"
    # El agregado sigue sumando los 3 childs.
    assert row["2026-06"] == pytest.approx(60.0)


def test_build_asin_parent_df_falls_back_to_first_child_title():
    """Caso 2: ningún child_asin == parent_asin → primer título no vacío."""
    model = {
        "C1": _node("P9", "Variante roja", {"2026-06": 20.0}),
        "C2": _node("P9", "Variante azul", {"2026-06": 30.0}),
    }
    df = rf._build_asin_parent_df(model, ["2026-06"])
    row = _parent_row(df, "P9")
    assert row["title"] == "Variante roja"
    assert row["2026-06"] == pytest.approx(50.0)


def test_build_asin_parent_df_fallback_skips_empty_titles():
    """El fallback ignora títulos vacíos / whitespace y toma el primero real."""
    model = {
        "C0": _node("P9", "   ", {"2026-06": 5.0}),
        "C1": _node("P9", "", {"2026-06": 5.0}),
        "C2": _node("P9", "Titulo real", {"2026-06": 10.0}),
    }
    df = rf._build_asin_parent_df(model, ["2026-06"])
    assert _parent_row(df, "P9")["title"] == "Titulo real"


def test_build_asin_parent_df_real_parent_wins_over_earlier_child():
    """El padre real gana aunque aparezca DESPUÉS de un child en el dict."""
    model = {
        "C1": _node("P1", "Variante roja", {"2026-06": 20.0}),
        "P1": _node("P1", "TITULO DEL PADRE", {"2026-06": 10.0}),
    }
    assert _parent_row(rf._build_asin_parent_df(model, ["2026-06"]), "P1")["title"]         == "TITULO DEL PADRE"


def test_build_asin_parent_df_no_title_anywhere_is_empty_string():
    """Sin ningún título → '' (nunca NaN, que rompería Arrow)."""
    model = {"C1": _node("P9", "", {"2026-06": 5.0})}
    df = rf._build_asin_parent_df(model, ["2026-06"])
    assert _parent_row(df, "P9")["title"] == ""
    assert df.isna().sum().sum() == 0


def test_build_asin_parent_df_missing_period_is_empty_not_nan():
    """Períodos sin dato quedan como '' — mismo contrato que la tabla Child."""
    model = {"P1": _node("P1", "Padre", {"2026-06": 10.0})}
    df = rf._build_asin_parent_df(model, ["2026-05", "2026-06"])
    row = _parent_row(df, "P1")
    assert row["2026-05"] == ""
    assert row["2026-06"] == pytest.approx(10.0)
    assert df.isna().sum().sum() == 0


# ─────────────────────────────────────────────────────────────────────────────
# E6 — gating del forecast por-ASIN (botón explícito + cache por ASIN)
# ─────────────────────────────────────────────────────────────────────────────
#
# El render del bloque es UI inline y no se testea acá. Lo que SÍ se testea es
# la lógica pura que sostiene el gating: la key de cache (que sea POR ASIN, o
# el AM vería el forecast del ASIN anterior) y el texto de parámetros (que
# describa lo realmente usado). El flujo de clic se valida en app.

_E6_OPTS = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}


def test_asin_fc_cache_key_is_per_asin():
    """Dos ASINs del MISMO cliente no comparten cache.

    Si la key no incluyera el asin, cambiar de ASIN mostraría el forecast del
    anterior como si fuera del nuevo.
    """
    k1 = rf._asin_fc_cache_key("c1", "B00AAA")
    k2 = rf._asin_fc_cache_key("c1", "B00BBB")
    assert k1 != k2
    assert "B00AAA" in k1 and "B00BBB" in k2


def test_asin_fc_cache_key_is_per_client():
    """El mismo ASIN en dos clientes distintos tampoco comparte cache."""
    assert rf._asin_fc_cache_key("c1", "B00AAA") != rf._asin_fc_cache_key("c2", "B00AAA")


def test_asin_fc_cache_key_is_stable():
    """Misma entrada → misma key (si no, el cache nunca haría hit)."""
    assert rf._asin_fc_cache_key("c1", "B00AAA") == rf._asin_fc_cache_key("c1", "B00AAA")


def test_fc_params_caption_reflects_opts():
    """El caption transcribe los 3 valores, no textos hardcodeados."""
    txt = rf._fc_params_caption({"horizon": 6, "momWindow": 4, "blend": 70,
                                 "useSeasonality": False})
    assert "horizonte 6 meses" in txt
    assert "ventana MoM 4" in txt
    assert "mezcla 70% MoM" in txt


def test_fc_params_caption_seasonality_off_has_no_suffix():
    txt = rf._fc_params_caption({**_E6_OPTS, "useSeasonality": False})
    assert "estacionalidad" not in txt


def test_fc_params_caption_seasonality_on_adds_suffix():
    txt = rf._fc_params_caption({**_E6_OPTS, "useSeasonality": True})
    assert txt.endswith("· estacionalidad ON")


def test_fc_params_caption_uses_defaults_when_opts_incomplete():
    """opts vacío no revienta — cae a los defaults del módulo (3/3/50)."""
    txt = rf._fc_params_caption({})
    assert "horizonte 3 meses" in txt
    assert "ventana MoM 3" in txt
    assert "mezcla 50% MoM" in txt


def test_forecast_single_asin_two_complete_months_is_not_empty():
    """Precondición del flujo E6: con 2 meses COMPLETOS sí proyecta.

    El caso contrario (1 mes → []) ya está en
    `test_forecast_single_asin_insufficient`. El happy path sólo estaba
    cubierto por los tests de fixtures reales, que SKIPEAN cuando los CSV
    gitignored no están — así que sin este test el gating quedaba sin piso
    verificable en una corrida limpia.
    """
    history = [
        {"period": "2026-05", "revenue": 1000.0, "units": 10.0,
         "sessions": 100.0, "unit_session_pct": 10.0},
        {"period": "2026-06", "revenue": 1200.0, "units": 12.0,
         "sessions": 110.0, "unit_session_pct": 10.9},
    ]
    fc = rf._forecast_single_asin(history, _E6_OPTS)
    assert fc, "2 meses completos deberían alcanzar para proyectar"
    assert len(fc) == _E6_OPTS["horizon"]
    assert all("date" in r and "revenue" in r for r in fc)


# ─────────────────────────────────────────────────────────────────────────────
# E7 pieza 2 — key del modelo por-ASIN + invariante de invalidación
# ─────────────────────────────────────────────────────────────────────────────
#
# El modelo por-ASIN se persiste en session_state para que el export lo lea
# (corre después, mismo run). Es DATO: un modelo rancio manda un deliverable con
# ASINs que ya no están cargados. El contrato es "se borra al ENTRAR a la
# sección, se escribe sólo en el camino feliz".
#
# El pop/set vive inline en el render y no se puede ejercitar sin AppTest (la
# sección arranca con un st.file_uploader, que AppTest 1.43.2 no expone como
# widget interactivo). Lo que SÍ se puede blindar es el invariante estructural
# que hace correcto al fix: que el pop esté antes de todo `return`. Si alguien lo
# mueve debajo de un return temprano, el bug vuelve en silencio — y este test lo
# caza.

def test_k_asin_model_is_per_client():
    assert rf._k_asin_model("c1") != rf._k_asin_model("c2")


def test_k_asin_model_is_stable():
    assert rf._k_asin_model("c1") == rf._k_asin_model("c1")


def test_k_asin_model_uses_module_prefix():
    """Namespaced con el prefijo del módulo: nunca colisiona con otro módulo."""
    assert rf._k_asin_model("c1").startswith(rf._STATE_PREFIX)
    assert "c1" in rf._k_asin_model("c1")


def _asin_section_src():
    import inspect
    return inspect.getsource(rf._render_asin_section)


def test_asin_section_invalidates_model_before_any_return():
    """LOAD-BEARING. El pop tiene que estar ANTES del primer `return`.

    La sección tiene seis return tempranos (sin archivos, período inválido,
    períodos duplicados, archivo no-By-Child, fallo de parseo, modelo vacío). Si
    el pop queda debajo de cualquiera de ellos, un run que corta deja el modelo
    del run anterior vivo y el export se lo lleva.
    """
    src = _asin_section_src()
    pop_at = src.find("st.session_state.pop(_k_asin_model(")
    assert pop_at != -1, "no se encontró el pop de invalidación"

    import re
    first_return = re.search(r"^\s+return\b", src, re.M)
    assert first_return, "esperaba al menos un return temprano en la sección"
    assert pop_at < first_return.start(), (
        "el pop de invalidación quedó DESPUÉS de un return temprano: "
        "un run que corta dejaría el modelo rancio para el export"
    )


def test_asin_section_persists_model_after_empty_guard():
    """El set va después del guard `if not model`, para no persistir {}."""
    src = _asin_section_src()
    guard_at = src.find("No se acumuló ningún ASIN")
    set_at = src.find("st.session_state[_k_asin_model(")
    assert guard_at != -1 and set_at != -1
    assert set_at > guard_at, (
        "el modelo se persiste antes del guard de modelo vacío"
    )


def test_asin_section_pop_and_set_appear_once_each():
    """Un solo punto de invalidación y uno de escritura — sin caminos alternos."""
    src = _asin_section_src()
    assert src.count("st.session_state.pop(_k_asin_model(") == 1
    assert src.count("st.session_state[_k_asin_model(") == 1
