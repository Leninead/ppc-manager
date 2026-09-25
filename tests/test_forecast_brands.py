"""Forecast por marca (EBG Fase 1): metadata de cliente, selector Grupo → Cuenta,
importador del histórico por marca, carga mensual por prefijo de SKU y tarjetas
de order items.

Los fixtures sintéticos (`tests/fixtures/forecast_brands/`) corren en CI. Los
reales (`tests/fixtures/real/ebg/`) son datos de clientes y están gitignored:
esos tests hacen skip cuando faltan.
"""

from __future__ import annotations

import copy
import math
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from modules.pages import revenue_forecast as rf

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SYNTH = _REPO_ROOT / "tests" / "fixtures" / "forecast_brands"
_REAL = _REPO_ROOT / "tests" / "fixtures" / "real" / "ebg"

_SYNTH_HISTORY = _SYNTH / "brand_history_sample.csv"
_SYNTH_CHILD = _SYNTH / "child_item_sku_sample.csv"
_REAL_SAMPLE = _REAL / "sample_child_item_sku.csv"

_OPTS = {"horizon": 6, "momWindow": 3, "blend": 50, "useSeasonality": True}

_BASE_CARD_LABELS_TAIL = [
    "Revenue YoY", "Sessions", "Unit Session %", "Units Sold", "AOV",
    "Sales Velocity", "Buy Box %",
]


def _old_client(cid: str, name: str, mkt: str = "US") -> dict:
    """Cliente persistido antes de EBG: sin ninguna key de marca."""
    c = rf._new_client(name=name, marketplace=mkt, client_id=cid)
    for k in ("group", "seller_account", "brand", "brand_prefixes"):
        c.pop(k, None)
    return c


def _brand_client(cid, brand, account, prefixes, group="EBG") -> dict:
    return rf._new_client(
        name=brand, client_id=cid, group=group, seller_account=account,
        brand=brand, brand_prefixes=list(prefixes),
    )


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — metadata del cliente
# ─────────────────────────────────────────────────────────────────────────────

def test_new_client_has_empty_brand_meta_by_default():
    c = rf._new_client(name="Acme")
    assert c["group"] is None
    assert c["seller_account"] is None
    assert c["brand"] is None
    assert c["brand_prefixes"] == []


def test_new_client_accepts_brand_meta():
    c = _brand_client("bl", "Blossom", "Cuenta 1", ["BL", "BLG"])
    assert (c["group"], c["seller_account"], c["brand"]) == ("EBG", "Cuenta 1", "Blossom")
    assert c["brand_prefixes"] == ["BL", "BLG"]


def test_brand_meta_reads_old_client_with_defaults():
    old = _old_client("acme", "Acme")
    assert rf._brand_meta(old) == {
        "group": None, "seller_account": None, "brand": None, "brand_prefixes": [],
    }


@pytest.mark.parametrize("text, expected", [
    ("BL, BLG", ["BL", "BLG"]),
    ("  bl ,, BLG ,", ["bl", "BLG"]),
    ("BL, bl, BLG", ["BL", "BLG"]),
    ("", []),
    (None, []),
])
def test_parse_brand_prefixes(text, expected):
    assert rf._parse_brand_prefixes(text) == expected


def test_set_brand_meta_writes_fields_and_blank_is_none():
    c = _old_client("acme", "Acme")
    before = copy.deepcopy(c)
    rf._set_brand_meta(c, group=" EBG ", seller_account="Cuenta 1",
                       brand="Blossom", prefixes_text="BL, BLG")
    assert rf._brand_meta(c) == {
        "group": "EBG", "seller_account": "Cuenta 1", "brand": "Blossom",
        "brand_prefixes": ["BL", "BLG"],
    }
    rf._set_brand_meta(c, group="", seller_account="  ", brand="", prefixes_text="")
    assert rf._brand_meta(c)["group"] is None
    assert rf._brand_meta(c)["brand"] is None
    # Nada más del cliente se tocó.
    for k, v in before.items():
        assert c[k] == v


def test_old_client_hydrates_exactly_as_stored(monkeypatch):
    old = _old_client("acme", "Acme", "MX")
    old["historical"] = [{"date": "2026-01-01", "revenue": 10.0, "units": 1,
                          "sessions": 5, "cvr": 20.0, "spend": 3.0, "ventasPPC": None}]
    stored = copy.deepcopy(old)
    monkeypatch.setattr(rf, "_list_forecast_clients", lambda a, m: ["acme", "_meta"])
    monkeypatch.setattr(
        rf, "_load_forecast_client",
        lambda a, c, m, n: copy.deepcopy(stored) if c == "acme" else {"active_client_id": "acme"},
    )
    state: dict = {}
    rf._hydrate_clients(state=state)
    assert state[rf._K_CLIENTS] == [stored]
    assert "group" not in state[rf._K_CLIENTS][0]


def test_brand_meta_persists_roundtrip(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(
        rf, "_save_forecast_client",
        lambda config, area, cliente, modulo, name: store.__setitem__((cliente, name), copy.deepcopy(config)),
    )
    monkeypatch.setattr(rf, "_list_forecast_clients", lambda a, m: sorted({k[0] for k in store}))
    monkeypatch.setattr(rf, "_load_forecast_client",
                        lambda a, c, m, n: copy.deepcopy(store.get((c, n))))
    c = _old_client("acme", "Acme")
    rf._set_brand_meta(c, group="EBG", seller_account="Cuenta 1",
                       brand="Blue Cross", prefixes_text="BC")
    state = {rf._K_CLIENTS: [c], rf._K_ACTIVE_CLIENT_ID: "acme"}
    rf._persist_clients(state=state)

    fresh: dict = {}
    rf._hydrate_clients(state=fresh)
    assert rf._brand_meta(fresh[rf._K_CLIENTS][0]) == {
        "group": "EBG", "seller_account": "Cuenta 1", "brand": "Blue Cross",
        "brand_prefixes": ["BC"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — selector Grupo → Cuenta → Marca
# ─────────────────────────────────────────────────────────────────────────────

def _catalog() -> list[dict]:
    return [
        _old_client("acme", "Acme", "MX"),
        _brand_client("bl", "Blossom", "Cuenta 1", ["BL", "BLG"]),
        _brand_client("bc", "Blue Cross", "Cuenta 1", ["BC"]),
        _brand_client("sv", "SEVEN", "Cuenta 2", ["SV"]),
        _brand_client("ot", "Otra", "Cuenta 9", ["OT"], group="Otro grupo"),
    ]


def test_client_labels_without_groups_match_legacy_format():
    clients = [_old_client("a", "Acme", "MX"), _old_client("b", "Beta")]
    assert rf._client_labels(clients) == {"Acme (MX)": "a", "Beta (US)": "b"}
    assert not rf._has_groups(clients)


def test_client_labels_show_brand_and_account_for_grouped_clients():
    labels = rf._client_labels(_catalog())
    assert labels["Blossom · Cuenta 1"] == "bl"
    assert labels["SEVEN · Cuenta 2"] == "sv"
    assert labels["Acme (MX)"] == "acme"
    assert rf._has_groups(_catalog())


def test_client_labels_disambiguate_duplicates():
    clients = [_brand_client("x1", "Nimbus", "Cuenta 1", ["N"]),
               _brand_client("x2", "Nimbus", "Cuenta 1", ["NB"])]
    labels = rf._client_labels(clients)
    assert len(labels) == 2
    assert set(labels.values()) == {"x1", "x2"}


def test_group_and_account_options():
    clients = _catalog()
    assert rf._group_options(clients) == [rf._ALL_GROUPS, "EBG", "Otro grupo"]
    assert rf._account_options(clients, "EBG") == [rf._ALL_ACCOUNTS, "Cuenta 1", "Cuenta 2"]
    assert rf._account_options(clients, rf._ALL_GROUPS) == [rf._ALL_ACCOUNTS]


def test_filter_clients():
    clients = _catalog()
    ids = lambda cs: [c["id"] for c in cs]  # noqa: E731
    assert ids(rf._filter_clients(clients, rf._ALL_GROUPS, rf._ALL_ACCOUNTS)) == [
        "acme", "bl", "bc", "sv", "ot"]
    assert ids(rf._filter_clients(clients, "EBG", rf._ALL_ACCOUNTS)) == ["bl", "bc", "sv"]
    assert ids(rf._filter_clients(clients, "EBG", "Cuenta 1")) == ["bl", "bc"]


_SELECTOR_APP = """
import sys, copy
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

clients = []
for cid, name, mkt, meta in __CLIENTS__:
    c = rf._new_client(name=name, marketplace=mkt, client_id=cid, **meta)
    if not meta:
        for k in ("group", "seller_account", "brand", "brand_prefixes"):
            c.pop(k, None)
    clients.append(c)
st.session_state.setdefault(rf._K_CLIENTS, clients)
st.session_state.setdefault(rf._K_ACTIVE_CLIENT_ID, clients[0]["id"])
st.session_state[rf._K_ACCOUNT_MANAGERS] = []
visible = rf._render_client_filters(st.session_state[rf._K_CLIENTS])
st.session_state["selected"] = rf._pick_client(visible)
"""


def _run_selector(clients_spec) -> AppTest:
    script = (_SELECTOR_APP.replace("__REPO_ROOT__", str(_REPO_ROOT))
              .replace("__CLIENTS__", repr(clients_spec)))
    at = AppTest.from_string(script)
    at.run()
    return at


def test_selector_without_groups_is_the_legacy_single_selectbox():
    at = _run_selector([("a", "Acme", "MX", {}), ("b", "Beta", "US", {})])
    assert not at.exception
    assert [s.label for s in at.selectbox] == ["Cliente"]
    assert list(at.selectbox[0].options) == ["Acme (MX)", "Beta (US)"]
    assert at.session_state["selected"] == "a"


def test_selector_with_groups_filters_by_group_and_account():
    ebg = lambda b, a: {"group": "EBG", "seller_account": a, "brand": b}  # noqa: E731
    at = _run_selector([
        ("acme", "Acme", "MX", {}),
        ("bl", "Blossom", "US", ebg("Blossom", "Cuenta 1")),
        ("sv", "SEVEN", "US", ebg("SEVEN", "Cuenta 2")),
    ])
    assert not at.exception
    assert [s.label for s in at.selectbox] == ["Grupo", "Cuenta", "Cliente"]
    assert list(at.selectbox[2].options) == ["Acme (MX)", "Blossom · Cuenta 1", "SEVEN · Cuenta 2"]

    at.selectbox[0].select("EBG").run()
    at.selectbox[1].select("Cuenta 2").run()
    assert not at.exception
    assert list(at.selectbox[2].options) == ["SEVEN · Cuenta 2"]
    assert at.session_state["selected"] == "sv"


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3 — importador del histórico por marca
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_brand_history_csv_shape():
    rows = rf._parse_brand_history_csv(_SYNTH_HISTORY.read_bytes())
    assert len(rows) == 14
    assert rows[0] == {
        "date": "2025-01-01", "revenue": 1000.0, "units": 100.0,
        "sessions": 2000.0, "cvr": 5.0, "orders": 90.0,
    }
    assert rows[-1]["date"] == "2026-02-01"
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)


def test_parse_brand_history_csv_without_orders_omits_the_key():
    data = b"mes,revenue,units,sessions\n2026-01,100,10,0\n"
    rows = rf._parse_brand_history_csv(data)
    assert rows == [{"date": "2026-01-01", "revenue": 100.0, "units": 10.0,
                     "sessions": 0.0, "cvr": 0.0}]


def test_parse_brand_history_csv_rejects_missing_columns():
    with pytest.raises(ValueError, match="sessions"):
        rf._parse_brand_history_csv(b"mes,revenue,units\n2026-01,1,1\n")


def test_parse_brand_history_csv_rejects_bad_month():
    with pytest.raises(ValueError, match="13/2026"):
        rf._parse_brand_history_csv(b"mes,revenue,units,sessions\n13/2026,1,1,1\n")


def test_import_brand_history_preserves_manual_spend():
    c = _brand_client("bl", "Blossom", "Cuenta 1", ["BL"])
    c["historical"] = [{"date": "2025-02-01", "revenue": 1.0, "units": 1.0,
                        "sessions": 1.0, "cvr": 100.0, "spend": 77.0, "ventasPPC": 150.0}]
    added, updated = rf._import_brand_history(c, _SYNTH_HISTORY.read_bytes())
    assert (added, updated) == (13, 1)
    feb = next(r for r in c["historical"] if r["date"] == "2025-02-01")
    assert feb["revenue"] == 1100.0 and feb["orders"] == 100.0
    assert feb["spend"] == 77.0 and feb["ventasPPC"] == 150.0


def test_engine_runs_on_imported_history_without_page_views_or_buy_box():
    rows = rf._parse_brand_history_csv(_SYNTH_HISTORY.read_bytes())
    hist, _, _ = rf._merge_historical([], rows)
    season = rf.auto_detect_seasonality(hist) or {"enabled": False, "indices": [1.0] * 12}
    fc = rf.generate_forecast(_OPTS, hist, season, "auto")
    assert len(fc) == 6
    assert all(math.isfinite(f["revenue"]) and f["revenue"] > 0 for f in fc)

    cards = rf._build_quick_stats(hist)
    assert next(c for c in cards if c["label"] == "Buy Box %")["value"] == "—"
    assert len(rf._build_history_df(hist)) == 14


@pytest.mark.skipif(not _REAL.exists(), reason="fixtures reales EBG gitignored")
@pytest.mark.parametrize("brand, months", [
    ("blossom", 24), ("blue_cross", 24), ("mented_cosmetics", 24),
    ("beauty_bakerie", 24), ("seven", 24), ("simply_organic", 24),
    ("arete", 15), ("oandm", 15),
])
def test_real_brand_histories_import_and_forecast(brand, months):
    rows = rf._parse_brand_history_csv((_REAL / f"{brand}.csv").read_bytes())
    assert len(rows) == months
    assert rows[-1]["date"] == "2026-08-01"
    season = rf.auto_detect_seasonality(rows) or {"enabled": False, "indices": [1.0] * 12}
    fc = rf.generate_forecast(_OPTS, rows, season, "auto")
    assert fc and all(math.isfinite(f["revenue"]) for f in fc)


# ─────────────────────────────────────────────────────────────────────────────
# PASO 4 — carga mensual por prefijo de SKU
# ─────────────────────────────────────────────────────────────────────────────

_AURORA = {"id": "au", "brand": "Aurora", "prefixes": ["AUR", "AURX"]}
_ZENITH = {"id": "ze", "brand": "Zenith", "prefixes": ["zen"]}


def test_match_brand_prefix_case_insensitive_and_longest_prefix():
    assert rf._match_brand_prefix("aurx-ser-60", [_AURORA, _ZENITH]) == [("au", "AURX")]
    assert rf._match_brand_prefix("AUR-CRM-01", [_AURORA, _ZENITH]) == [("au", "AUR")]
    assert rf._match_brand_prefix("ZEN-LIP-01", [_AURORA, _ZENITH]) == [("ze", "zen")]
    assert rf._match_brand_prefix("MISC", [_AURORA, _ZENITH]) == []
    assert rf._match_brand_prefix("", [_AURORA, _ZENITH]) == []


def test_split_by_brand_synthetic():
    split = rf._split_by_brand(_SYNTH_CHILD.read_bytes(), [_AURORA, _ZENITH])
    au, ze = split["brands"]["au"], split["brands"]["ze"]
    assert au == {"brand": "Aurora", "revenue": 8450.5, "units": 280.0,
                  "sessions": 2500.0, "orders": 263.0, "skus": 3}
    assert ze == {"brand": "Zenith", "revenue": 2550.0, "units": 250.0,
                  "sessions": 1200.0, "orders": 225.0, "skus": 2}
    assert [u["sku"] for u in split["unassigned"]] == ["MISC-KIT-9", ""]
    assert [u["revenue"] for u in split["unassigned"]] == [250.0, 99.95]
    assert split["conflicts"] == []
    assert split["totals"] == pytest.approx({"revenue": 11350.45, "units": 545.0,
                                             "sessions": 3850.0, "orders": 502.0})


def _reconciles(split) -> None:
    for field in ("revenue", "units", "sessions", "orders"):
        assigned = sum(b[field] for b in split["brands"].values())
        rest = sum(u[field] for u in split["unassigned"] + split["conflicts"])
        assert assigned + rest == pytest.approx(split["totals"][field])


def test_split_by_brand_reconciles_synthetic():
    _reconciles(rf._split_by_brand(_SYNTH_CHILD.read_bytes(), [_AURORA, _ZENITH]))


def test_split_by_brand_conflict_is_not_assigned():
    other = {"id": "ot", "brand": "Otra", "prefixes": ["AUR-SER"]}
    split = rf._split_by_brand(_SYNTH_CHILD.read_bytes(), [_AURORA, other])
    assert [c["sku"] for c in split["conflicts"]] == ["AUR-SER-30"]
    assert sorted(split["conflicts"][0]["brands"]) == ["Aurora", "Otra"]
    assert split["brands"]["au"]["skus"] == 2
    assert split["brands"]["ot"]["skus"] == 0
    _reconciles(split)


def test_split_by_brand_requires_sku_column():
    data = b"(Child) ASIN,Units Ordered,Ordered Product Sales\nC1,1,$1.00\n"
    with pytest.raises(ValueError, match="SKU"):
        rf._split_by_brand(data, [_AURORA])


@pytest.mark.skipif(not _REAL_SAMPLE.exists(), reason="muestra real gitignored")
def test_split_by_brand_real_sample_reconciles():
    brands = [{"id": p, "brand": p, "prefixes": [p]}
              for p in ("fvnt_", "fcrt_", "scrt_", "3pck_")]
    split = rf._split_by_brand(_REAL_SAMPLE.read_bytes(), brands)
    _reconciles(split)
    assert split["unassigned"] == [] and split["conflicts"] == []

    partial = rf._split_by_brand(_REAL_SAMPLE.read_bytes(), brands[:1] + brands[2:3])
    _reconciles(partial)
    assert partial["unassigned"]


def test_month_options_default_is_last_closed_month():
    opts = rf._month_options(date(2026, 9, 24))
    assert opts[0] == "2026-08"
    assert opts[1] == "2026-07"
    assert len(opts) == 24
    assert rf._month_options(date(2026, 1, 1))[0] == "2025-12"


def test_account_brands():
    brands = rf._account_brands(_catalog(), "EBG", "Cuenta 1")
    assert brands == [
        {"id": "bl", "brand": "Blossom", "prefixes": ["BL", "BLG"]},
        {"id": "bc", "brand": "Blue Cross", "prefixes": ["BC"]},
    ]


def test_apply_month_by_brand_merges_into_each_brand_client():
    au = _brand_client("au", "Aurora", "Cuenta 1", ["AUR", "AURX"])
    ze = _brand_client("ze", "Zenith", "Cuenta 1", ["zen"])
    ze["historical"] = [{"date": "2026-08-01", "revenue": 1.0, "units": 1.0,
                         "sessions": 1.0, "cvr": 100.0, "spend": 40.0, "ventasPPC": 90.0}]
    split = rf._split_by_brand(_SYNTH_CHILD.read_bytes(), [_AURORA, _ZENITH])

    applied = rf._apply_month_by_brand([au, ze], "2026-08", split)

    assert applied == {"au": "added", "ze": "updated"}
    assert au["historical"] == [{
        "date": "2026-08-01", "revenue": 8450.5, "units": 280.0, "sessions": 2500.0,
        "cvr": 280.0 / 2500.0 * 100.0, "orders": 263.0, "spend": None, "ventasPPC": None,
    }]
    assert ze["historical"][0]["revenue"] == 2550.0
    assert ze["historical"][0]["spend"] == 40.0


def test_apply_month_by_brand_skips_brands_without_skus():
    au = _brand_client("au", "Aurora", "Cuenta 1", ["AUR"])
    ghost = _brand_client("gh", "Ghost", "Cuenta 1", ["NOPE"])
    split = rf._split_by_brand(_SYNTH_CHILD.read_bytes(),
                               [{"id": "au", "brand": "Aurora", "prefixes": ["AUR"]},
                                {"id": "gh", "brand": "Ghost", "prefixes": ["NOPE"]}])
    applied = rf._apply_month_by_brand([au, ghost], "2026-08", split)
    assert applied == {"au": "added"}
    assert ghost["historical"] == []


# ─────────────────────────────────────────────────────────────────────────────
# PASO 5 — tarjetas Order items y AOP
# ─────────────────────────────────────────────────────────────────────────────

def _hist(orders: bool) -> list[dict]:
    rows = []
    for i, (u, o) in enumerate([(100.0, 80.0), (120.0, 96.0)]):
        r = {"date": f"2026-0{i + 1}-01", "revenue": u * 10, "units": u,
             "sessions": 1000.0, "cvr": u / 10}
        if orders:
            r["orders"] = o
        rows.append(r)
    return rows


def test_quick_stats_add_order_cards_when_orders_exist():
    cards = {c["label"]: c for c in rf._build_quick_stats(_hist(orders=True))}
    assert cards["Order items"]["value"] == "96"
    assert cards["Order items"]["delta"] == pytest.approx(20.0)
    assert cards["AOP"]["value"] == "1.25"


def test_quick_stats_unchanged_without_orders():
    labels = [c["label"] for c in rf._build_quick_stats(_hist(orders=False))]
    assert labels == ["Revenue Febrero 2026", *_BASE_CARD_LABELS_TAIL]


# ─────────────────────────────────────────────────────────────────────────────
# Humo de UI (AppTest): página sin grupos intacta + previa de la carga mensual
# ─────────────────────────────────────────────────────────────────────────────

_RENDER_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

c = rf._new_client(name="Acme", marketplace="MX", client_id="acme")
for k in ("group", "seller_account", "brand", "brand_prefixes"):
    c.pop(k, None)
c["historical"] = [
    {"date": "2026-%02d-01" % (i + 1), "revenue": 1000.0 + i, "units": 10, "sessions": 300,
     "cvr": 3.3, "buyBox": 90, "pageViews": 400, "revenueB2B": 0, "spend": None, "ventasPPC": None}
    for i in range(6)
]
st.session_state.setdefault(rf._K_CLIENTS, [c])
st.session_state.setdefault(rf._K_ACTIVE_CLIENT_ID, "acme")
st.session_state.setdefault(rf._K_ACCOUNT_MANAGERS, [])
rf.render()
"""


class _FakeUpload:
    """UploadedFile mínimo: AppTest no puede subir archivos en Streamlit 1.43."""
    name = "report.csv"

    def __init__(self, path: Path):
        self._data = path.read_bytes()

    def getvalue(self) -> bytes:
        return self._data


def _no_persist(monkeypatch) -> None:
    # AppTest runs in-process: patch through monkeypatch so nothing leaks into later tests.
    monkeypatch.setattr(rf, "_try_persist", lambda *a, **k: True)


def test_render_without_groups_shows_no_brand_sections(monkeypatch):
    _no_persist(monkeypatch)
    at = AppTest.from_string(_RENDER_APP.replace("__REPO_ROOT__", str(_REPO_ROOT)),
                             default_timeout=60)
    at.run()
    assert not at.exception
    assert "Grupo" not in [s.label for s in at.selectbox]
    text = " ".join(m.value for m in at.markdown)
    assert "Importar histórico" not in text
    assert "Cargar mes por cuenta" not in text
    assert [c["label"] for c in rf._build_quick_stats(
        at.session_state[rf._K_CLIENTS][0]["historical"])][-1] == "Buy Box %"


_MONTH_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

if rf._K_CLIENTS not in st.session_state:
    au = rf._new_client(name="Aurora", client_id="au", group="G", seller_account="Cuenta 1",
                        brand="Aurora", brand_prefixes=["AUR", "AURX"])
    ze = rf._new_client(name="Zenith", client_id="ze", group="G", seller_account="Cuenta 1",
                        brand="Zenith", brand_prefixes=["zen"])
    st.session_state[rf._K_CLIENTS] = [au, ze]
clients = st.session_state[rf._K_CLIENTS]
rf._render_brand_meta_popover(clients[0])
rf._render_brand_history_import(clients[0])
rf._render_month_by_account(clients[0], clients)
"""


def test_month_by_account_preview_and_confirm(monkeypatch):
    import streamlit

    _no_persist(monkeypatch)
    monkeypatch.setattr(streamlit, "file_uploader",
                        lambda *a, **k: _FakeUpload(_SYNTH_CHILD))
    script = _MONTH_APP.replace("__REPO_ROOT__", str(_REPO_ROOT))
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception
    preview = at.dataframe[0].value
    assert list(preview["Marca"]) == ["Aurora", "Zenith"]
    assert list(preview["Estado"]) == ["Mes nuevo", "Mes nuevo"]
    assert any("SKUs sin marca" in w.value for w in at.warning)

    period = at.selectbox[1].value
    confirm = next(b for b in at.button if b.label.startswith("Confirmar carga"))
    confirm.click().run()
    assert not at.exception
    au, ze = at.session_state[rf._K_CLIENTS]
    assert [r["date"] for r in au["historical"]] == [f"{period}-01"]
    assert au["historical"][0]["revenue"] == 8450.5
    assert ze["historical"][0]["orders"] == 225.0


# ─────────────────────────────────────────────────────────────────────────────
# Caption de reconciliación: los "$" van escapados (si no, Markdown los toma
# como LaTeX)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("currency", ["USD", "MXN"])
def test_reconciliation_caption_escapes_every_dollar(currency):
    split = rf._split_by_brand(_SYNTH_CHILD.read_bytes(), [_AURORA, _ZENITH])
    text = rf._reconciliation_caption(split, currency)
    assert "\$" in text
    assert text.count("$") == text.count("\$") == 4
    for amount in ("11,350.45", "11,000.50", "349.95", "0.00"):
        assert f"\\${amount}" in text
