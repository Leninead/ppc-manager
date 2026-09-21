"""Tests de `previsualizar_lead_time` — M37, el lead time ANTES de confirmar.

`core/supply/metrics.py::previsualizar_lead_time(eventos, fecha_recepcion,
lt_min=None, lt_max=None) -> dict`

De donde sale: el lead time de 54 dias que reporto Fede sobre una OC de Tarik.
La emision se backdateo y la recepcion quedo con el default de hoy; el numero
era el delta correcto entre las fechas CARGADAS, y nadie lo vio hasta despues
de guardar. `diagnosticar_lead_time` no lo puede atajar (un dato mal cargado es
indistinguible de uno bueno). Lo ataja mostrarle al AM el numero que se va a
registrar, contra el rango declarado del proveedor, antes de confirmar.

Contrato:
- Simula: copia de los eventos + un RECIBIDA_PARCIAL hipotetico con
  `fecha_recepcion` AL FINAL, y pasa esa copia por `diagnosticar_lead_time`.
  'dias' y 'motivo' salen de ahi. Nunca muta la lista que recibe.
- 'ya_medido': en los eventos ACTUALES ya hay una recepcion despues (por
  posicion) del primer EMITIDA; esta recepcion no cierra la ventana.
- 'fecha_emision': fecha del PRIMER EMITIDA por posicion, 'YYYY-MM-DD'.
- 'fuera_de_rango': solo con motivo 'ok' y sin ya_medido. Bordes inclusivos.
- 'bloquear': recepcion (a nivel dia) anterior a la emision MAS TEMPRANA
  parseable. Se evalua siempre, este o no medido.

Logica pura: los eventos entran como lista de dicts. Nada de disco, nada de
Streamlit.
"""

from __future__ import annotations

import copy

import core.supply.metrics as metrics
from core.supply.metrics import previsualizar_lead_time


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_CLAVES = {
    "dias",
    "motivo",
    "ya_medido",
    "fecha_emision",
    "fuera_de_rango",
    "bloquear",
}


def _ev(evento: str, fecha) -> dict:
    """Un evento del log, con lo minimo que mira la funcion."""
    return {"evento": evento, "fecha": fecha}


def _emitida_0720() -> list[dict]:
    return [_ev("EMITIDA", "2026-07-20")]


# ─────────────────────────────────────────────────────────────────────────────
# El caso que mide
# ─────────────────────────────────────────────────────────────────────────────


class TestCasoNormal:
    def test_recepcion_normal_sin_rango(self):
        assert previsualizar_lead_time(_emitida_0720(), "2026-08-20") == {
            "dias": 31,
            "motivo": "ok",
            "ya_medido": False,
            "fecha_emision": "2026-07-20",
            "fuera_de_rango": None,
            "bloquear": False,
        }

    def test_mismo_dia(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-07-20")
        assert r["dias"] == 0
        assert r["motivo"] == "ok"
        assert r["bloquear"] is False

    def test_fecha_emision_con_hora_se_recorta_al_dia(self):
        eventos = [_ev("EMITIDA", "2026-07-20T10:30:00")]
        r = previsualizar_lead_time(eventos, "2026-08-20")
        assert r["fecha_emision"] == "2026-07-20"

    def test_devuelve_exactamente_las_seis_claves(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-20")
        assert set(r) == _CLAVES


# ─────────────────────────────────────────────────────────────────────────────
# Rango declarado del proveedor
# ─────────────────────────────────────────────────────────────────────────────


class TestRango:
    def test_dentro_del_rango(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-20", 25, 35)
        assert r["dias"] == 31
        assert r["fuera_de_rango"] is None

    def test_borde_superior_inclusivo(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-24", 25, 35)
        assert r["dias"] == 35
        assert r["fuera_de_rango"] is None

    def test_borde_inferior_inclusivo(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-14", 25, 35)
        assert r["dias"] == 25
        assert r["fuera_de_rango"] is None

    def test_arriba_del_rango(self):
        # El caso de Fede con Tarik: 54 contra un rango de 25-35. Con esto lo
        # veia antes de guardar.
        r = previsualizar_lead_time(_emitida_0720(), "2026-09-12", 25, 35)
        assert r["dias"] == 54
        assert r["fuera_de_rango"] == "arriba"

    def test_abajo_del_rango(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-05", 25, 35)
        assert r["dias"] == 16
        assert r["fuera_de_rango"] == "abajo"

    def test_sin_lt_max_nunca_arriba(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-09-12", 25, None)
        assert r["dias"] == 54
        assert r["fuera_de_rango"] is None

    def test_sin_lt_min_nunca_abajo(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-05", None, 35)
        assert r["dias"] == 16
        assert r["fuera_de_rango"] is None


# ─────────────────────────────────────────────────────────────────────────────
# La ventana ya estaba cerrada
# ─────────────────────────────────────────────────────────────────────────────


class TestYaMedido:
    def test_parcial_previa_cierra_la_ventana(self):
        # 36 esta fuera de rango, pero ya quedo registrado con la parcial del
        # 08-25: esta recepcion no lo cambia, asi que no es accionable aca.
        eventos = [
            _ev("EMITIDA", "2026-07-20"),
            _ev("RECIBIDA_PARCIAL", "2026-08-25"),
        ]
        r = previsualizar_lead_time(eventos, "2026-09-13", 25, 35)
        assert r["ya_medido"] is True
        assert r["dias"] == 36
        assert r["motivo"] == "ok"
        assert r["fuera_de_rango"] is None

    def test_cerrada_previa_cierra_la_ventana(self):
        eventos = [_ev("EMITIDA", "2026-07-20"), _ev("CERRADA", "2026-08-25")]
        r = previsualizar_lead_time(eventos, "2026-09-13")
        assert r["ya_medido"] is True

    def test_sin_recepcion_previa(self):
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-20")
        assert r["ya_medido"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Lo fisicamente imposible: recibir antes de emitir
# ─────────────────────────────────────────────────────────────────────────────


class TestBloqueo:
    def test_recepcion_antes_de_la_emision(self):
        eventos = [_ev("EMITIDA", "2026-08-25")]
        r = previsualizar_lead_time(eventos, "2026-07-20")
        assert r["motivo"] == "fechas_invertidas"
        assert r["dias"] is None
        assert r["bloquear"] is True

    def test_bloquea_aunque_ya_este_medido(self):
        # Recibir antes de emitir es imposible, este o no cerrada la ventana.
        eventos = [
            _ev("EMITIDA", "2026-08-25"),
            _ev("RECIBIDA_PARCIAL", "2026-09-01"),
        ]
        r = previsualizar_lead_time(eventos, "2026-07-01")
        assert r["ya_medido"] is True
        assert r["dias"] == 7
        assert r["motivo"] == "ok"
        assert r["bloquear"] is True

    def test_compara_contra_la_emision_mas_temprana(self):
        # Comparar contra la PRIMERA (09-15) le hubiera bloqueado una recepcion
        # legitima; la mas temprana es 07-20.
        eventos = [_ev("EMITIDA", "2026-09-15"), _ev("EMITIDA", "2026-07-20")]
        r = previsualizar_lead_time(eventos, "2026-08-25")
        assert r["motivo"] == "emitida_duplicada"
        assert r["bloquear"] is False

    def test_antes_de_todas_las_emisiones(self):
        eventos = [_ev("EMITIDA", "2026-09-15"), _ev("EMITIDA", "2026-07-20")]
        r = previsualizar_lead_time(eventos, "2026-07-01")
        assert r["bloquear"] is True

    def test_sin_emitida_no_bloquea(self):
        eventos = [_ev("PROPUESTA", "2026-07-01"), _ev("APROBADA", "2026-07-05")]
        r = previsualizar_lead_time(eventos, "2026-06-01")
        assert r["bloquear"] is False

    def test_emitida_ilegible_no_bloquea(self):
        eventos = [_ev("EMITIDA", "20/07/2026")]
        r = previsualizar_lead_time(eventos, "2026-06-01")
        assert r["bloquear"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Cuando no hay numero
# ─────────────────────────────────────────────────────────────────────────────


class TestSinMedicion:
    def test_sin_eventos(self):
        # El hipotetico hace que la copia nunca este vacia: el motivo es
        # sin_emitida, no sin_eventos.
        r = previsualizar_lead_time([], "2026-08-20")
        assert r["motivo"] == "sin_emitida"
        assert r["dias"] is None
        assert r["fecha_emision"] is None
        assert r["ya_medido"] is False
        assert r["bloquear"] is False

    def test_solo_estados_previos_a_emitir(self):
        eventos = [_ev("PROPUESTA", "2026-07-01"), _ev("APROBADA", "2026-07-05")]
        r = previsualizar_lead_time(eventos, "2026-08-20")
        assert r["motivo"] == "sin_emitida"

    def test_emision_con_fecha_ilegible(self):
        eventos = [_ev("EMITIDA", "20/07/2026")]
        r = previsualizar_lead_time(eventos, "2026-08-20")
        assert r["motivo"] == "fecha_ilegible"
        assert r["fecha_emision"] is None

    def test_emitida_duplicada_reporta_la_primera(self):
        eventos = [_ev("EMITIDA", "2026-09-15"), _ev("EMITIDA", "2026-07-20")]
        r = previsualizar_lead_time(eventos, "2026-10-01")
        assert r["motivo"] == "emitida_duplicada"
        assert r["fecha_emision"] == "2026-09-15"

    def test_fecha_recepcion_vacia(self):
        r = previsualizar_lead_time(_emitida_0720(), "")
        assert r["motivo"] == "fecha_ilegible"
        assert r["bloquear"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Pureza
# ─────────────────────────────────────────────────────────────────────────────


class TestPureza:
    def test_no_muta_la_lista_de_entrada(self):
        eventos = [
            _ev("EMITIDA", "2026-07-20"),
            _ev("RECIBIDA_PARCIAL", "2026-08-25"),
        ]
        antes = copy.deepcopy(eventos)
        previsualizar_lead_time(eventos, "2026-09-13", 25, 35)
        assert len(eventos) == len(antes)
        assert eventos == antes

    def test_no_toca_disco(self, monkeypatch):
        def _prohibido(*args, **kwargs):
            raise AssertionError("previsualizar_lead_time no debe leer disco")

        monkeypatch.setattr(metrics, "leer_eventos", _prohibido)
        monkeypatch.setattr(metrics, "list_ocs", _prohibido)
        r = previsualizar_lead_time(_emitida_0720(), "2026-08-20")
        assert r["dias"] == 31
        assert r["motivo"] == "ok"
