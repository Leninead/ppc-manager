"""Tests del borrado de cuenta desde la pestaña Admin de M36.

Se inyecta un `st` falso (mismo patron que tests/test_ai_tab.py) porque lo que
importa acá no es como se ve sino QUE se borra y QUE se protege:

- una cuenta conectada por API no se ofrece para borrar, porque su entrada en el
  selector viene de `integration_connections` y borrar las filas locales la
  dejaria en pantalla: el boton pareceria roto;
- el borrado abarca los TRES modulos, no solo el que alimenta el selector, o el
  stock y los ads quedan huerfanos e inalcanzables;
- el slug seleccionado se limpia de session_state, porque si queda apuntando a
  una cuenta que ya no existe Streamlit revienta en el render siguiente.
"""

from __future__ import annotations

import pytest

from modules.mercado_libre import config, main


class _Col:
    def __init__(self, parent, name):
        self._parent = parent
        self._name = name

    def button(self, label, **kwargs):
        return self._parent._button(label, **kwargs)

    def markdown(self, *a, **k):
        pass

    def caption(self, *a, **k):
        pass


class _FakeSt:
    """Lo minimo de streamlit que tocan las funciones bajo prueba."""

    def __init__(self, button_returns=None, text_value=""):
        self.button_returns = button_returns or {}
        self.text_value = text_value
        self.session_state = {}
        self.markdowns = []
        self.infos = []
        self.captions = []
        self.successes = []
        self.buttons = []
        self.reruns = 0

    def _button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        return bool(self.button_returns.get(kwargs.get("key"), False))

    button = _button

    def markdown(self, text, *a, **k):
        self.markdowns.append(text)

    def caption(self, text, *a, **k):
        self.captions.append(text)

    def info(self, text, *a, **k):
        self.infos.append(text)

    def success(self, text, *a, **k):
        self.successes.append(text)

    def divider(self):
        pass

    def text_input(self, label, **kwargs):
        return self.text_value

    def columns(self, spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Col(self, f"c{i}") for i in range(n)]

    def rerun(self):
        self.reruns += 1


@pytest.fixture
def fake_st(monkeypatch):
    def _install(**kwargs):
        fake = _FakeSt(**kwargs)
        monkeypatch.setattr(main, "st", fake)
        return fake
    return _install


def _accounts(source):
    return [{"slug": "acme", "source": source, "marketplace": "MLA", "estado": "activo"}]


def test_una_cuenta_conectada_por_api_no_ofrece_el_boton(fake_st, monkeypatch):
    """Borrar las filas locales la dejaria en pantalla: el boton pareceria roto."""
    st = fake_st()
    monkeypatch.setattr(main, "_list_accounts", lambda: _accounts("oauth"))

    main._delete_account_section("acme")

    assert st.infos, "deberia explicar por que no se puede"
    assert "Cuentas conectadas" in st.infos[0]
    assert not [b for b in st.buttons if b.get("key") == "meli_del_account"]


def test_una_cuenta_manual_si_ofrece_el_boton(fake_st, monkeypatch):
    st = fake_st()
    monkeypatch.setattr(main, "_list_accounts", lambda: _accounts("local"))

    main._delete_account_section("acme")

    assert [b for b in st.buttons if b.get("key") == "meli_del_account"]
    assert not st.infos


def test_borra_los_tres_modulos_no_solo_el_del_selector(fake_st, monkeypatch):
    """Borrar solo rendimiento dejaria stock y ads huerfanos e invisibles."""
    st = fake_st(button_returns={"meli_del_account_ok": True}, text_value="acme")
    borrados = []
    monkeypatch.setattr(main, "_delete_cliente",
                        lambda area, cliente, modulo: borrados.append((area, cliente, modulo)) or True)

    main._delete_account_body("acme")

    assert {m for _, _, m in borrados} == {
        config.MODULO_RENDIMIENTO, config.MODULO_PUBLICACIONES, config.MODULO_ADS,
    }
    assert {c for _, c, _ in borrados} == {"acme"}


def test_limpia_el_slug_seleccionado(fake_st, monkeypatch):
    """Si queda apuntando a una cuenta borrada, el render siguiente revienta."""
    st = fake_st(button_returns={"meli_del_account_ok": True}, text_value="acme")
    st.session_state["meli_cuenta"] = "acme"
    monkeypatch.setattr(main, "_delete_cliente", lambda *a: True)

    main._delete_account_body("acme")

    assert "meli_cuenta" not in st.session_state


def test_el_boton_eliminar_esta_deshabilitado_si_el_nombre_no_coincide(fake_st, monkeypatch):
    """La confirmacion tipeada es la unica barrera ante un borrado irreversible."""
    st = fake_st(text_value="otra-cosa")
    monkeypatch.setattr(main, "_delete_cliente", lambda *a: True)

    main._delete_account_body("acme")

    ok = next(b for b in st.buttons if b.get("key") == "meli_del_account_ok")
    assert ok["disabled"] is True


def test_con_el_nombre_exacto_el_boton_se_habilita(fake_st, monkeypatch):
    st = fake_st(text_value="  acme  ")
    monkeypatch.setattr(main, "_delete_cliente", lambda *a: True)

    main._delete_account_body("acme")

    ok = next(b for b in st.buttons if b.get("key") == "meli_del_account_ok")
    assert ok["disabled"] is False


def test_sin_datos_que_borrar_avisa_en_vez_de_decir_que_borro(fake_st, monkeypatch):
    st = fake_st(button_returns={"meli_del_account_ok": True}, text_value="acme")
    monkeypatch.setattr(main, "_delete_cliente", lambda *a: False)

    main._delete_account_body("acme")

    assert st.infos and "no tenía datos" in st.infos[0]
    assert not st.successes
