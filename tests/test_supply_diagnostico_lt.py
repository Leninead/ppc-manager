"""Tests de `diagnosticar_lead_time` — M37, por que una OC no mide.

`core/supply/metrics.py::diagnosticar_lead_time(eventos) -> {'dias', 'motivo'}`
es la version explicada de `_muestra_lead_time`: mismas reglas de calculo, pero
en vez de un `None` mudo devuelve el motivo.

De donde sale: el lead time de 54 dias que reporto Fede sobre una OC de Tarik
cuyo ciclo real fue de ~30/35. El calculo estaba bien — 54 era el delta correcto
entre las fechas CARGADAS. El problema es que hay dos `st.date_input` en
pantallas distintas (el avance de estado y la recepcion) y se backdateo uno y no
el otro, sin que nada mostrara el numero resultante antes de guardar.

Y hay un caso peor, silencioso: hoy una OC con dos EMITIDA, o con una fecha que
no parsea, devuelve `None` y simplemente DESAPARECE de la mediana del proveedor.
Nadie se entera. Eso es lo que estos motivos vuelven visible.

Las reglas de calculo se portan tal cual de `_muestra_lead_time`: gana el PRIMER
EMITIDA por posicion, cierra el PRIMER evento de LT_HASTA que este despues por
POSICION (no por fecha), y `dias` es `.days` del delta.

La precedencia de los motivos es parte del contrato:
    sin_eventos > sin_emitida > emitida_duplicada > fecha_ilegible >
    sin_recepcion > fechas_invertidas > ok

Logica pura: los eventos entran como lista de dicts, no como DataFrame. Nada de
disco, nada de Streamlit.
"""

from __future__ import annotations

from pathlib import Path

from core.supply.metrics import diagnosticar_lead_time


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _ev(evento: str, fecha) -> dict:
    """Un evento del log, con lo minimo que mira la funcion."""
    return {"evento": evento, "fecha": fecha}


# ─────────────────────────────────────────────────────────────────────────────
# El caso que mide
# ─────────────────────────────────────────────────────────────────────────────


class TestCasoNormal:
    def test_emision_y_cierre(self):
        eventos = [_ev("EMITIDA", "2026-07-20"), _ev("CERRADA", "2026-08-25")]
        assert diagnosticar_lead_time(eventos) == {"dias": 36, "motivo": "ok"}

    def test_toma_la_primera_recepcion(self):
        # La parcial cierra la ventana; el CERRADA posterior ya no la mueve.
        # Con la ultima habria dado 55 (07-20 -> 09-13).
        eventos = [
            _ev("EMITIDA", "2026-07-20"),
            _ev("RECIBIDA_PARCIAL", "2026-08-25"),
            _ev("CERRADA", "2026-09-13"),
        ]
        assert diagnosticar_lead_time(eventos) == {"dias": 36, "motivo": "ok"}

    def test_mismo_dia(self):
        eventos = [_ev("EMITIDA", "2026-07-20"), _ev("CERRADA", "2026-07-20")]
        assert diagnosticar_lead_time(eventos) == {"dias": 0, "motivo": "ok"}

    def test_claves_extra_no_rompen(self):
        eventos = [
            {
                "oc_id": "OC-TAR-2609-01",
                "evento": "EMITIDA",
                "fecha": "2026-07-20",
                "quien": "fede",
                "ts": "2026-09-16T15:26:52",
            },
            {
                "oc_id": "OC-TAR-2609-01",
                "evento": "CERRADA",
                "fecha": "2026-08-25",
                "quien": "fede",
                "ts": "2026-09-16T15:31:10",
            },
        ]
        assert diagnosticar_lead_time(eventos) == {"dias": 36, "motivo": "ok"}

    def test_fecha_con_hora_trunca(self):
        # VERIFICADO: da 35, no 36. El delta crudo es 35 days, 13:30:00 y .days
        # trunca. Pasa cuando el evento se registro sin fecha explicita: el
        # default del log es _now_iso(), que trae hora, mientras que una fecha
        # backdateada desde el date_input llega a medianoche.
        eventos = [
            _ev("EMITIDA", "2026-07-20T10:30:00"),
            _ev("CERRADA", "2026-08-25"),
        ]
        assert diagnosticar_lead_time(eventos) == {"dias": 35, "motivo": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Falta algo
# ─────────────────────────────────────────────────────────────────────────────


class TestSinDatos:
    def test_lista_vacia(self):
        assert diagnosticar_lead_time([]) == {"dias": None, "motivo": "sin_eventos"}

    def test_sin_emitida(self):
        eventos = [_ev("PROPUESTA", "2026-07-01"), _ev("APROBADA", "2026-07-05")]
        assert diagnosticar_lead_time(eventos) == {"dias": None, "motivo": "sin_emitida"}

    def test_sin_recepcion(self):
        eventos = [_ev("EMITIDA", "2026-07-20")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "sin_recepcion",
        }

    def test_duplicada_gana_sobre_sin_recepcion(self):
        # Precedencia: emitida_duplicada se chequea antes que sin_recepcion.
        eventos = [_ev("EMITIDA", "2026-09-15"), _ev("EMITIDA", "2026-07-20")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "emitida_duplicada",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Dos EMITIDA — el caso que hoy desaparece en silencio
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitidaDuplicada:
    def test_recargada_con_la_fecha_corregida(self):
        # El AM emitio con la fecha de hoy por error y volvio a emitir con la
        # real. `_muestra_lead_time` devuelve None acá — no porque falte un
        # dato, sino porque mide contra el PRIMER EMITIDA (09-15) y el delta
        # con el cierre (08-25) da negativo. La OC desaparece de la mediana del
        # proveedor y nadie se entera. Este motivo es exactamente eso, dicho.
        eventos = [
            _ev("EMITIDA", "2026-09-15"),
            _ev("EMITIDA", "2026-07-20"),
            _ev("CERRADA", "2026-08-25"),
        ]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "emitida_duplicada",
        }

    def test_se_reporta_aunque_el_calculo_diera_un_numero(self):
        # Con el primer EMITIDA (07-20) el delta seria 36, perfectamente valido.
        # Igual se reporta la duplicacion: el AM tiene que saber que el log
        # tiene dos emisiones antes de confiar en el numero.
        eventos = [
            _ev("EMITIDA", "2026-07-20"),
            _ev("EMITIDA", "2026-09-15"),
            _ev("CERRADA", "2026-08-25"),
        ]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "emitida_duplicada",
        }

    def test_tres_emitida(self):
        eventos = [
            _ev("EMITIDA", "2026-07-20"),
            _ev("EMITIDA", "2026-08-01"),
            _ev("EMITIDA", "2026-09-15"),
            _ev("CERRADA", "2026-09-20"),
        ]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "emitida_duplicada",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Orden y signo
# ─────────────────────────────────────────────────────────────────────────────


class TestFechasInvertidas:
    def test_cierre_escrito_antes_de_la_emision(self):
        # Por POSICION no hay nada de LT_HASTA despues del EMITIDA, asi que el
        # motivo es la falta de recepcion, no el orden de las fechas.
        eventos = [_ev("CERRADA", "2026-08-25"), _ev("EMITIDA", "2026-07-20")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "sin_recepcion",
        }

    def test_delta_negativo(self):
        eventos = [_ev("EMITIDA", "2026-08-25"), _ev("CERRADA", "2026-07-20")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "fechas_invertidas",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Fechas que no parsean
# ─────────────────────────────────────────────────────────────────────────────


class TestFechaIlegible:
    def test_emitida_en_formato_latino(self):
        eventos = [_ev("EMITIDA", "20/07/2026"), _ev("CERRADA", "2026-08-25")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "fecha_ilegible",
        }

    def test_emitida_con_fecha_vacia(self):
        eventos = [_ev("EMITIDA", ""), _ev("CERRADA", "2026-08-25")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "fecha_ilegible",
        }

    def test_emitida_con_fecha_none(self):
        eventos = [_ev("EMITIDA", None), _ev("CERRADA", "2026-08-25")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "fecha_ilegible",
        }

    def test_recepcion_ilegible_con_emitida_sana(self):
        eventos = [_ev("EMITIDA", "2026-07-20"), _ev("CERRADA", "20/08/2026")]
        assert diagnosticar_lead_time(eventos) == {
            "dias": None,
            "motivo": "fecha_ilegible",
        }

    def test_nan_y_nat(self):
        # Lo que deja pandas cuando el parquet trae un nulo.
        for basura in ("nan", "NaT"):
            eventos = [_ev("EMITIDA", basura), _ev("CERRADA", "2026-08-25")]
            assert diagnosticar_lead_time(eventos) == {
                "dias": None,
                "motivo": "fecha_ilegible",
            }, f"fecha {basura!r}"


# ─────────────────────────────────────────────────────────────────────────────
# El caso real
# ─────────────────────────────────────────────────────────────────────────────


class TestCasoDeFede:
    def test_los_54_dias_de_tarik(self):
        # Ciclo real: ~30/35 dias. El maestro mostro 54.
        #
        # 54 es CORRECTO para estas fechas: 07-20 + 54 = 09-12. El calculo
        # nunca estuvo mal. Lo que fallo es la carga: la emision se backdateo a
        # mano y la recepcion quedo con el default `date.today()`, porque son
        # dos date_input en pantallas distintas (_bloque_avance y
        # _bloque_recepcion) y editar uno no edita el otro.
        #
        # Por eso este motivo es 'ok': el diagnostico NO puede detectar esto.
        # Un dato mal cargado es indistinguible de uno bueno. Lo que lo evita es
        # mostrarle el numero al AM ANTES de guardar, que es el punto 1 del
        # frente, no este.
        eventos = [_ev("EMITIDA", "2026-07-20"), _ev("CERRADA", "2026-09-12")]
        assert diagnosticar_lead_time(eventos) == {"dias": 54, "motivo": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Pureza
# ─────────────────────────────────────────────────────────────────────────────


class TestPureza:
    def test_el_modulo_sigue_sin_streamlit(self):
        fuente = (
            Path(__file__).resolve().parents[1] / "core" / "supply" / "metrics.py"
        ).read_text(encoding="utf-8")
        assert "import streamlit" not in fuente
