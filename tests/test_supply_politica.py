"""Tests de core/supply_politica.py — M37 punto 2, política de stock (R, s, S).

Port del motor del Laboratorio de Compras de Fede. Fuente de verdad:
`notes/supply-chain/originales/laboratorio-compras-2026-08-17.html` L302-365
(`zInv`, `poissonQ`, `computeABC`, `calcPolicy`). Los valores esperados de estos
tests se derivan de esas fórmulas al pie de la letra — ninguno es un número
"razonable" elegido a ojo.

Los invariantes que se defienden acá:

- **Paridad numérica con el HTML.** `_z_inv` es Acklam con los coeficientes
  exactos del HTML y `_poisson_inv` el mismo acumulado con tope 3000. Sin scipy:
  el entorno no lo tiene y no se va a instalar.
- **ABC por ACUMULADO INCLUSIVO.** Se suma el revenue del SKU al acumulado ANTES
  de comparar contra el corte (`cum <= total*corte`). Es la paridad con
  laboratorio-compras-2026-08-17.html L328:
  `cum+=o.r;o.s.abc=cum<=tot*0.80?'A':cum<=tot*0.95?'B':'C'`.
  Consecuencia intencional: el último SKU del ranking siempre es 'C', aunque sea
  el único.
- **El orden de evaluación importa.** Régimen: fluido (dw >= 2) antes que
  espaciado (dw > 0.05); dw == 0.05 exacto es 'sin demanda'. Diagnóstico:
  'sin demanda' se evalúa antes que COMPRAR.
- **Todo redondea hacia arriba.** ss, rop y S pasan por ceil, como en el HTML.
- **Sin dato de inventario no hay diagnóstico.** `posicion_actual=None` devuelve
  None, no una señal calculada contra cero.
- **Lógica pura.** Cero disco, cero Streamlit, cero `supply_persistence`.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.supply_politica import (
    _poisson_inv,
    _z_inv,
    calcular_politica,
    clasificar_abc,
    diagnosticar_posicion,
)


# ─────────────────────────────────────────────────────────────────────────────
# _z_inv — inversa de la Normal estándar (Acklam, HTML L302-309)
# ─────────────────────────────────────────────────────────────────────────────


class TestZInv:
    def test_clamp_en_los_extremos(self):
        assert _z_inv(0) == -8
        assert _z_inv(1) == 8

    def test_clamp_fuera_de_rango(self):
        assert _z_inv(-0.5) == -8
        assert _z_inv(1.5) == 8

    def test_mediana_es_cero(self):
        assert abs(_z_inv(0.5)) < 1e-9

    def test_nivel_servicio_clase_a(self):
        assert _z_inv(0.97) == pytest.approx(1.8807936, abs=1e-5)

    def test_nivel_servicio_clase_b(self):
        assert _z_inv(0.94) == pytest.approx(1.5547735, abs=1e-5)

    def test_simetria(self):
        assert _z_inv(0.9) == pytest.approx(-_z_inv(0.1), abs=1e-6)

    def test_rama_baja(self):
        # p=0.01 < p_low=0.02425 -> rama con coeficientes c/d
        z = _z_inv(0.01)
        assert math.isfinite(z)
        assert z < 0

    def test_rama_alta(self):
        # p=0.99 > 1-p_low -> rama con coeficientes c/d, signo invertido
        z = _z_inv(0.99)
        assert math.isfinite(z)
        assert z > 0


# ─────────────────────────────────────────────────────────────────────────────
# _poisson_inv — cuantil de Poisson (HTML L310)
# ─────────────────────────────────────────────────────────────────────────────


class TestPoissonInv:
    def test_lambda_cero(self):
        assert _poisson_inv(0.94, 0) == 0

    def test_lambda_negativo(self):
        assert _poisson_inv(0.94, -1) == 0

    @pytest.mark.parametrize("ns, lam", [(0.91, 0.5), (0.94, 1), (0.97, 5), (0.94, 10)])
    def test_resultado_entero_no_negativo(self, ns, lam):
        k = _poisson_inv(ns, lam)
        assert isinstance(k, int)
        assert k >= 0

    def test_monotono_en_lambda(self):
        ks = [_poisson_inv(0.94, lam) for lam in (1, 5, 10)]
        assert ks == sorted(ks)

    def test_monotono_en_nivel_servicio(self):
        ks = [_poisson_inv(ns, 5) for ns in (0.91, 0.94, 0.97)]
        assert ks == sorted(ks)


# ─────────────────────────────────────────────────────────────────────────────
# clasificar_abc — Pareto por acumulado inclusivo (HTML L324-328)
# ─────────────────────────────────────────────────────────────────────────────


class TestClasificarAbc:
    def test_dict_vacio(self):
        assert clasificar_abc({}) == {}

    def test_un_solo_sku_con_revenue_es_c(self):
        # total = 100. El SKU suma al acumulado ANTES de comparar: cum = 100.
        # 100 <= 100*0.80 (80) es falso; 100 <= 100*0.95 (95) es falso -> 'C'.
        # El ultimo SKU del ranking SIEMPRE es 'C': su cum == total y total > total*0.95. Con un solo SKU, ese SKU es primero y ultimo a la vez. NO es un bug, no 'arreglar' este test.
        assert clasificar_abc({"x": 100.0}) == {"x": "C"}

    def test_un_solo_sku_sin_revenue_es_a(self):
        # total = 0 -> se usa 1 como divisor. cum = 0 tras sumar el SKU.
        # 0 <= 1*0.80 es verdadero -> 'A'. Es el único caso donde el último SKU
        # no es 'C': sin revenue, total*0.95 no queda por debajo de cum.
        assert clasificar_abc({"x": 0.0}) == {"x": "A"}

    def test_todos_revenue_cero_no_explota(self):
        resultado = clasificar_abc({"x": 0.0, "y": 0.0, "z": 0.0})
        assert set(resultado) == {"x", "y", "z"}
        assert all(letra in {"A", "B", "C"} for letra in resultado.values())

    def test_caso_claro(self):
        # total 100: a cum 80 <= 80 -> A; b cum 95 <= 95 -> B; c cum 100 -> C
        assert clasificar_abc({"a": 80.0, "b": 15.0, "c": 5.0}) == {
            "a": "A",
            "b": "B",
            "c": "C",
        }

    def test_corte_inclusivo_en_80(self):
        # total 100: a cum 50 -> A; b lleva el acumulado a EXACTAMENTE 80 -> A
        # (la condición es <=); c cum 100 -> C
        resultado = clasificar_abc({"a": 50.0, "b": 30.0, "c": 20.0})
        assert resultado["b"] == "A"

    def test_una_entrada_por_sku(self):
        revenues = {"s1": 10.0, "s2": 0.0, "s3": 250.0, "s4": 42.5}
        assert set(clasificar_abc(revenues)) == set(revenues)

    @pytest.mark.parametrize(
        "revenues",
        [
            {"p": 70.0, "q": 30.0},
            {"s1": 120.5, "s2": 3.25, "s3": 980.0, "s4": 45.0, "s5": 610.0},
            {
                "k01": 1500.0, "k02": 12.4, "k03": 830.0, "k04": 77.0, "k05": 2310.9,
                "k06": 5.5, "k07": 440.0, "k08": 999.0, "k09": 63.2, "k10": 1200.0,
            },
        ],
        ids=["2-skus", "5-skus", "10-skus"],
    )
    def test_propiedad_el_de_menor_revenue_siempre_es_c(self, revenues):
        # Regla intencional del acumulado inclusivo: el SKU de menor revenue es el
        # último del ranking, llega con cum == total, y total > total*0.95 cuando
        # total > 0. Los dicts no tienen empates en el mínimo a propósito.
        menor = min(revenues, key=revenues.get)
        assert clasificar_abc(revenues)[menor] == "C"


# ─────────────────────────────────────────────────────────────────────────────
# calcular_politica — régimen (HTML L348-350)
# ─────────────────────────────────────────────────────────────────────────────


def _politica(dw, sw=1.0, lead_time=(7, 10, 14), **kwargs):
    return calcular_politica(
        demanda_semanal=dw, desvio_semanal=sw, lead_time=lead_time, **kwargs
    )


class TestRegimenes:
    def test_dos_exacto_es_fluido(self):
        assert _politica(2.0)["regimen"] == "fluido"

    def test_apenas_bajo_dos_es_espaciado(self):
        assert _politica(1.99)["regimen"] == "espaciado"

    def test_cero_cinco_exacto_es_sin_demanda(self):
        # La condición es dw > 0.05, no >=
        assert _politica(0.05)["regimen"] == "sin demanda"

    def test_apenas_sobre_cero_cinco_es_espaciado(self):
        assert _politica(0.06)["regimen"] == "espaciado"

    def test_cero_es_sin_demanda_con_ss_cero(self):
        politica = _politica(0)
        assert politica["regimen"] == "sin demanda"
        assert politica["ss"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# calcular_politica — cálculo (HTML L340-352)
# ─────────────────────────────────────────────────────────────────────────────


def _es_entero(valor) -> bool:
    return isinstance(valor, int) or (isinstance(valor, float) and valor.is_integer())


class TestCalculoPolitica:
    def test_sigma_lt_desde_el_rango(self):
        assert _politica(14, lead_time=(7, 10, 14))["sigma_lt"] == pytest.approx(1.75)

    def test_sigma_lt_cero_sin_rango(self):
        assert _politica(14, lead_time=(10, 10, 10))["sigma_lt"] == pytest.approx(0.0)

    def test_periodo_proteccion(self):
        assert _politica(14, lead_time=(7, 10, 14))["periodo_proteccion"] == 17
        assert (
            _politica(14, lead_time=(7, 10, 14), periodo_revision=14)["periodo_proteccion"]
            == 24
        )

    @pytest.mark.parametrize("dw", [14.0, 1.0, 0.0])
    def test_ss_rop_s_enteros_y_ss_no_negativo(self, dw):
        politica = _politica(dw)
        assert _es_entero(politica["ss"])
        assert _es_entero(politica["rop"])
        assert _es_entero(politica["objetivo_s"])
        assert politica["ss"] >= 0

    @pytest.mark.parametrize(
        "dw, sw, lead_time, kwargs",
        [
            (14.0, 7.0, (7, 10, 14), {}),
            (1.0, 0.5, (25, 35, 45), {"nivel_servicio": 0.97}),
            (0.5, 0.3, (7, 10, 14), {"periodo_revision": 14, "nivel_servicio": 0.91}),
        ],
    )
    def test_rop_nunca_supera_objetivo(self, dw, sw, lead_time, kwargs):
        politica = _politica(dw, sw=sw, lead_time=lead_time, **kwargs)
        assert politica["rop"] <= politica["objetivo_s"]

    def test_indice_estacional_escala_dfwd(self):
        base = _politica(14, indice_estacional=1.0)["dfwd"]
        doble = _politica(14, indice_estacional=2.0)["dfwd"]
        assert doble == pytest.approx(2 * base)

    def test_sin_demanda_cobertura_objetivo_infinita(self):
        assert math.isinf(_politica(0)["dias_cobertura_objetivo"])

    def test_caso_fluido_numeros_fijos(self):
        # dw=14, sw=7, lead_time=(7,10,14), R=7, NS=0.94, idx=1.0
        #   sigma_lt = (14-7)/4          = 1.75
        #   d_des    = 14/7              = 2.0
        #   sigma_d  = 7/sqrt(7)         = sqrt(7) -> sigma_d^2 = 7
        #   dfwd     = 2.0 * 1.0         = 2.0
        #   P        = 10 + 7            = 17
        #   dw=14 >= 2 -> fluido
        #   radicando = P*sigma_d^2 + dfwd^2*sigma_lt^2
        #             = 17*7 + 4*3.0625 = 119 + 12.25 = 131.25
        #   sqrt(131.25)                 = 11.4564392...
        #   _z_inv(0.94)                 = 1.5547736...
        #   ss crudo = 1.5547736 * 11.4564392 = 17.8121692... -> ceil = 18
        #   rop = ceil(18 + 2.0*10)      = 38
        #   S   = ceil(18 + 2.0*17)      = 52
        #   dias_cobertura_objetivo = 52 / 2.0 = 26.0
        # Control: si se usara sigma_d = sw (sin /sqrt(7)), el radicando sería
        # 17*49 + 12.25 = 845.25 y ss = ceil(45.2...) = 46. Por eso el 18 detecta
        # ese error.
        politica = _politica(14.0, sw=7.0, lead_time=(7, 10, 14))
        assert politica["regimen"] == "fluido"
        assert politica["ss"] == 18
        assert politica["rop"] == 38
        assert politica["objetivo_s"] == 52
        assert politica["dias_cobertura_objetivo"] == pytest.approx(26.0)


# ─────────────────────────────────────────────────────────────────────────────
# diagnosticar_posicion — señal (HTML L353-361)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def politica_fluida():
    # Mismo caso que test_caso_fluido_numeros_fijos: ss=18, rop=38, S=52, dfwd=2.0
    # Umbral de EXCESO = S + max(2*dfwd*R, 0.15*S) = 52 + max(28, 7.8) = 80
    return _politica(14.0, sw=7.0, lead_time=(7, 10, 14))


class TestDiagnostico:
    def test_sin_dato_de_inventario_devuelve_none(self, politica_fluida):
        assert diagnosticar_posicion(politica_fluida, None) is None

    def test_sin_demanda_y_sin_stock(self):
        diag = diagnosticar_posicion(_politica(0), 0)
        assert diag["senal"] == "—"

    def test_sin_demanda_con_stock(self):
        diag = diagnosticar_posicion(_politica(0), 10)
        assert diag["senal"] == "SIN DEMANDA"

    def test_posicion_igual_a_rop_compra(self, politica_fluida):
        # La condición es pos <= rop. need = max(1, 52 - 38) = 14
        diag = diagnosticar_posicion(politica_fluida, 38)
        assert diag["senal"] == "COMPRAR"
        assert diag["need"] == 14

    def test_posicion_cero_compra(self, politica_fluida):
        diag = diagnosticar_posicion(politica_fluida, 0)
        assert diag["senal"] == "COMPRAR"
        assert diag["need"] >= 1

    def test_entre_rop_y_umbral_de_exceso_es_ok(self, politica_fluida):
        # 39 > rop (38) y 39 <= umbral de exceso (80)
        diag = diagnosticar_posicion(politica_fluida, 39)
        assert diag["senal"] == "OK"

    def test_muy_por_encima_es_exceso(self, politica_fluida):
        # 81 > umbral de exceso (80)
        diag = diagnosticar_posicion(politica_fluida, 81)
        assert diag["senal"] == "EXCESO"

    def test_need_minimo_uno_cuando_s_menos_pos_no_es_positivo(self):
        # dw=0.07, sw=0, lead_time=(10,10,10), R=7, NS=0.94, idx=1.0
        #   sigma_lt = 0 ; d_des = dfwd = 0.01 ; P = 17
        #   0.05 < 0.07 < 2 -> espaciado
        #   lam = 0.01 * (17 + 0) = 0.17
        #   _poisson_inv(0.94, 0.17): p0 = exp(-0.17) = 0.8437 < 0.94
        #     k=1: p = 0.8437*0.17 = 0.1434, cum = 0.9871 >= 0.94 -> k = 1
        #   ss crudo = max(0, 1 - 0.17) = 0.83 -> ceil = 1
        #   rop = ceil(1 + 0.01*10) = ceil(1.10) = 2
        #   S   = ceil(1 + 0.01*17) = ceil(1.17) = 2
        # pos = 2: pos <= rop -> COMPRAR, y S - pos = 0 -> need = max(1, 0) = 1
        politica = _politica(0.07, sw=0.0, lead_time=(10, 10, 10))
        assert politica["rop"] == 2
        assert politica["objetivo_s"] == 2
        diag = diagnosticar_posicion(politica, 2)
        assert diag["senal"] == "COMPRAR"
        assert diag["need"] == 1

    def test_cobertura_infinita_sin_demanda(self):
        diag = diagnosticar_posicion(_politica(0), 10)
        assert math.isinf(diag["cobertura_dias"])

    # Política con R=14 para los dos tests de R. dw=14, sw=7, lead_time=(7,10,14),
    # NS=0.94, idx=1.0:
    #   sigma_lt = 1.75 ; dfwd = 2.0 ; sigma_d^2 = 7 ; P = 10 + 14 = 24
    #   radicando = 24*7 + 4*3.0625 = 168 + 12.25 = 180.25 -> sqrt = 13.4257216
    #   ss crudo = 1.5547736 * 13.4257216 = 20.8739574 -> ceil = 21
    #   rop = ceil(21 + 2.0*10) = 41 ; S = ceil(21 + 2.0*24) = 69
    # Umbral de EXCESO = S + max(2*dfwd*R, 0.15*S):
    #   con R=14 -> 69 + max(56, 10.35) = 125
    #   con R=7  -> 69 + max(28, 10.35) = 97
    # pos=100 discrimina: OK con R=14 (41 < 100 <= 125), EXCESO con R=7 (100 > 97).

    def test_default_usa_el_r_de_la_politica(self):
        politica = _politica(14.0, sw=7.0, lead_time=(7, 10, 14), periodo_revision=14)
        diag = diagnosticar_posicion(politica, 100)
        assert diag["senal"] == "OK"

    def test_override_de_r_cambia_el_umbral(self):
        politica = _politica(14.0, sw=7.0, lead_time=(7, 10, 14), periodo_revision=14)
        diag = diagnosticar_posicion(politica, 100, periodo_revision=7)
        assert diag["senal"] == "EXCESO"


# ─────────────────────────────────────────────────────────────────────────────
# Pureza — el módulo no toca disco, Streamlit ni dependencias fuera de stdlib
# ─────────────────────────────────────────────────────────────────────────────


class TestPureza:
    def test_modulo_sin_io_ni_dependencias_prohibidas(self):
        fuente = (
            Path(__file__).resolve().parents[1] / "core" / "supply_politica.py"
        ).read_text(encoding="utf-8")
        for prohibido in (
            "import streamlit",
            "supply_persistence",
            "open(",
            "pd.read",
            "scipy",
            "numpy",
        ):
            assert prohibido not in fuente, f"core/supply_politica.py contiene {prohibido!r}"
