"""Tests de core/supply/indices.py — M37 B2.1b, cálculo de la tabla de índices.

Contraparte de `core/supply/seasonality.py` (B2.1a, ya en producción): aquel CONSUME una
tabla de índices, este la CALCULA desde historia de ventas.

Los invariantes que se defienden acá:

- **El jueves manda.** Una semana ISO puede caer a caballo entre dos meses, e
  incluso entre dos años. La regla ISO 8601 asigna la semana al año/mes de su
  jueves, que es el día que garantiza que la mayoría de la semana cae del mismo
  lado. Sin una regla fija, la misma historia produce índices distintos según
  quién la agregue.
- **Evidencia insuficiente no produce índice.** Un grupo con pocos meses va a
  `descartados` con su razón, no a la tabla con huecos rellenados. Es lo mismo
  que hace `demanda_corregida` con `minimo_dias`.
- **El origen del índice viaja con el índice.** `resolver_indice` devuelve
  `(valor, origen)` para que el consumidor pueda distinguir un índice medido de
  un fallback neutro. Un 1.0 puede significar "este mes es promedio" o "no
  tengo idea", y son cosas muy distintas.
- **`corregido_por_quiebres` es False y se declara.** La plataforma no tiene
  fuente de inventario histórico (verificado 2026-09-14). El flag existe para
  que nadie use estos índices creyendo que están corregidos.

Contexto: `notes/supply-chain/hallazgos-tablas-indices.md` documenta por qué NO
se heredan las tablas de Fede y sirven solo como caso de prueba.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from core.supply.indices import (
    agregar_a_mensual,
    calcular_indices,
    indices_por_sku,
    resolver_indice,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — construcción de historia sintética
# ─────────────────────────────────────────────────────────────────────────────

def _semana_de(anio: int, mes: int) -> int:
    """Primera semana ISO cuyo JUEVES cae en (anio, mes).

    Se elige por el jueves y no por el lunes para que la semana generada quede
    inequívocamente asignada a ese mes bajo la misma regla que usa el módulo.
    """
    for semana in range(1, 54):
        try:
            jueves = date.fromisocalendar(anio, semana, 4)
        except ValueError:
            continue
        if jueves.year == anio and jueves.month == mes:
            return semana
    raise AssertionError(f"sin semana ISO para {anio}-{mes:02d}")


def _filas_anio(sku: str, category: str, anio: int, unidades: list[int]) -> list[dict]:
    """Un año completo: 12 filas, UNA semana por mes.

    Una sola semana por mes hace que el total mensual sea exactamente el valor
    que se pasa, sin que la aritmética del test dependa de cuántas semanas trae
    cada mes calendario.
    """
    return [
        {
            "period": f"{anio}-W{_semana_de(anio, mes):02d}",
            "sku": sku,
            "category": category,
            "units_ordered": unidades[mes - 1],
        }
        for mes in range(1, 13)
    ]


def _historia(*grupos: list[dict]) -> pd.DataFrame:
    """Arma el DataFrame con el shape que persiste M28."""
    filas: list[dict] = []
    for grupo in grupos:
        filas.extend(grupo)
    return pd.DataFrame(filas, columns=["period", "sku", "category", "units_ordered"])


def _historia_vacia() -> pd.DataFrame:
    return pd.DataFrame(columns=["period", "sku", "category", "units_ordered"])


def _plano(valor: int = 100) -> list[int]:
    """Doce meses idénticos: sin estacionalidad."""
    return [valor] * 12


def _con_pico_diciembre(base: int, diciembre: int) -> list[int]:
    return [base] * 11 + [diciembre]


def _fila(df: pd.DataFrame, anio: int, mes: int) -> pd.Series:
    """La única fila de un (anio, mes) en la salida mensual."""
    sel = df[(df["anio"] == anio) & (df["mes"] == mes)]
    assert len(sel) == 1, f"esperaba 1 fila para {anio}-{mes:02d}, hay {len(sel)}"
    return sel.iloc[0]


def _resultado(tablas: dict[str, list[float]], agrupado_por: str = "category") -> dict:
    """Arma a mano el shape de retorno, para los tests de `resolver_indice`."""
    return {
        "tablas": tablas,
        "descartados": {},
        "meses_estimados": {},
        "meta": {
            "corregido_por_quiebres": False,
            "grupos_con_indice": len(tablas),
            "meses_cubiertos": 12,
            "agrupado_por": agrupado_por,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# agregar_a_mensual — la regla del jueves
# ─────────────────────────────────────────────────────────────────────────────

def test_semana_entera_dentro_de_un_mes():
    """2026-W16 va del 13 al 19 de abril: no hay ambigüedad que resolver."""
    df = agregar_a_mensual(_historia([
        {"period": "2026-W16", "sku": "A", "category": "gorros", "units_ordered": 50},
    ]))
    fila = _fila(df, 2026, 4)
    assert fila["units_ordered"] == 50


def test_semana_a_caballo_la_decide_el_jueves():
    """2026-W14 arranca el 30-mar y termina el 5-abr. Jueves 2-abr -> ABRIL.

    Si se asignara por el lunes, esta semana caería en marzo y el índice de
    ambos meses saldría corrido.
    """
    df = agregar_a_mensual(_historia([
        {"period": "2026-W14", "sku": "A", "category": "gorros", "units_ordered": 70},
    ]))
    assert len(df) == 1
    assert int(df.iloc[0]["mes"]) == 4
    assert int(df.iloc[0]["anio"]) == 2026


def test_semana_a_caballo_en_la_otra_direccion():
    """2026-W44 va del 26-oct al 1-nov. Jueves 29-oct -> OCTUBRE, no noviembre."""
    df = agregar_a_mensual(_historia([
        {"period": "2026-W44", "sku": "A", "category": "gorros", "units_ordered": 10},
    ]))
    assert int(df.iloc[0]["mes"]) == 10


def test_semana_1_arranca_el_anio_anterior_pero_es_enero():
    """2026-W01 empieza el 29-dic-2025. Su jueves es el 1-ene-2026 -> enero 2026.

    El caso que rompe cualquier implementación que parsee el año del string y
    después use el lunes: la semana pertenece al año 2026 aunque cinco de sus
    días caigan en 2025.
    """
    df = agregar_a_mensual(_historia([
        {"period": "2026-W01", "sku": "A", "category": "gorros", "units_ordered": 33},
    ]))
    assert int(df.iloc[0]["anio"]) == 2026
    assert int(df.iloc[0]["mes"]) == 1


def test_semana_53_termina_el_anio_siguiente_pero_es_diciembre():
    """Espejo del anterior: 2026-W53 termina el 3-ene-2027, jueves 31-dic-2026."""
    df = agregar_a_mensual(_historia([
        {"period": "2026-W53", "sku": "A", "category": "gorros", "units_ordered": 44},
    ]))
    assert int(df.iloc[0]["anio"]) == 2026
    assert int(df.iloc[0]["mes"]) == 12


@pytest.mark.parametrize(
    "period",
    ["basura", "", "2026-14", "W14", "2026-W99", "2026-W00", "2025-W53", "abril"],
)
def test_period_invalido_se_descarta_sin_romper(period):
    """Un period roto pierde esa fila, no la corrida entera.

    '2025-W53' entra acá a propósito: es sintácticamente válido pero 2025 no
    tiene 53 semanas ISO.
    """
    df = agregar_a_mensual(_historia([
        {"period": period, "sku": "A", "category": "gorros", "units_ordered": 10},
    ]))
    assert len(df) == 0


def test_filas_invalidas_no_arrastran_a_las_validas():
    df = agregar_a_mensual(_historia([
        {"period": "basura", "sku": "A", "category": "gorros", "units_ordered": 999},
        {"period": "2026-W16", "sku": "A", "category": "gorros", "units_ordered": 50},
    ]))
    assert len(df) == 1
    assert df.iloc[0]["units_ordered"] == 50


def test_suma_las_semanas_del_mismo_mes():
    """W02, W03 y W04 caen todas en enero 2026: una fila con la suma."""
    df = agregar_a_mensual(_historia([
        {"period": "2026-W02", "sku": "A", "category": "gorros", "units_ordered": 10},
        {"period": "2026-W03", "sku": "A", "category": "gorros", "units_ordered": 20},
        {"period": "2026-W04", "sku": "A", "category": "gorros", "units_ordered": 30},
    ]))
    assert _fila(df, 2026, 1)["units_ordered"] == 60


def test_no_mezcla_skus_distintos():
    df = agregar_a_mensual(_historia([
        {"period": "2026-W16", "sku": "A", "category": "gorros", "units_ordered": 10},
        {"period": "2026-W16", "sku": "B", "category": "gorros", "units_ordered": 20},
    ]))
    assert len(df) == 2
    assert set(df["sku"]) == {"A", "B"}


def test_columnas_de_salida():
    df = agregar_a_mensual(_historia([
        {"period": "2026-W16", "sku": "A", "category": "gorros", "units_ordered": 10},
    ]))
    assert set(df.columns) == {"anio", "mes", "sku", "category", "units_ordered"}


def test_historia_vacia_devuelve_df_vacio():
    df = agregar_a_mensual(_historia_vacia())
    assert len(df) == 0


# ─────────────────────────────────────────────────────────────────────────────
# calcular_indices — forma de la tabla
# ─────────────────────────────────────────────────────────────────────────────

def test_doce_meses_planos_dan_indices_neutros():
    """Sin estacionalidad real, ningún mes corrige nada."""
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert r["tablas"]["gorros"] == pytest.approx([1.0] * 12)


def test_pico_estacional_da_indice_mayor_a_uno():
    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 300)))
    )
    tabla = r["tablas"]["gorros"]
    assert tabla[11] > 1.0, "diciembre es el pico"
    assert all(v < 1.0 for v in tabla[:11]), "el resto queda por debajo del promedio"


def test_la_tabla_suma_doce():
    """Media 1.0: es el contrato que espera `indice_mes` de B2.1a."""
    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 300)))
    )
    assert sum(r["tablas"]["gorros"]) == pytest.approx(12.0)


def test_la_tabla_tiene_doce_valores():
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert len(r["tablas"]["gorros"]) == 12


def test_agrupa_por_categoria_sumando_sus_skus():
    """Dos SKUs de la misma categoría producen UNA tabla, no dos."""
    r = calcular_indices(_historia(
        _filas_anio("A", "gorros", 2026, _plano(100)),
        _filas_anio("B", "gorros", 2026, _plano(50)),
    ))
    assert list(r["tablas"]) == ["gorros"]


def test_categorias_distintas_tablas_distintas():
    r = calcular_indices(_historia(
        _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 300)),
        _filas_anio("B", "bufandas", 2026, _plano()),
    ))
    assert set(r["tablas"]) == {"gorros", "bufandas"}
    assert r["tablas"]["bufandas"] == pytest.approx([1.0] * 12)
    assert r["tablas"]["gorros"][11] > 1.0


# ─────────────────────────────────────────────────────────────────────────────
# calcular_indices — evidencia insuficiente
# ─────────────────────────────────────────────────────────────────────────────

def test_grupo_con_pocos_meses_va_a_descartados():
    """6 meses no alcanzan para un perfil de 12: descartado, no completado."""
    filas = _filas_anio("A", "gorros", 2026, _plano())[:6]
    r = calcular_indices(_historia(filas))

    assert "gorros" not in r["tablas"]
    assert "gorros" in r["descartados"]
    assert r["descartados"]["gorros"], "el descarte tiene que explicar la razón"


def test_descarte_no_contamina_a_los_grupos_sanos():
    r = calcular_indices(_historia(
        _filas_anio("A", "gorros", 2026, _plano())[:6],
        _filas_anio("B", "bufandas", 2026, _plano()),
    ))
    assert "bufandas" in r["tablas"]
    assert "gorros" in r["descartados"]


def test_minimo_meses_configurable():
    """Bajar el mínimo habilita un grupo que con el default se descartaba."""
    filas = _filas_anio("A", "gorros", 2026, _plano())[:6]
    assert "gorros" in calcular_indices(_historia(filas), minimo_meses=6)["tablas"]


def test_historia_vacia_no_rompe():
    r = calcular_indices(_historia_vacia())
    assert r["tablas"] == {}
    assert r["descartados"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# calcular_indices — ponderación por año
# ─────────────────────────────────────────────────────────────────────────────

def test_ponderacion_sesenta_cuarenta_con_dos_anios():
    """Dos años del mismo mes: el reciente pesa 0.6, el anterior 0.4.

    Diciembre: 200 en 2026 (reciente) y 100 en 2025 -> 0.6*200 + 0.4*100 = 160.
    Resto de los meses: 100 en ambos -> 100.
    Promedio de los 12 = (11*100 + 160)/12 = 105, y el índice es valor/promedio.
    """
    r = calcular_indices(_historia(
        _filas_anio("A", "gorros", 2025, _con_pico_diciembre(100, 100)),
        _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 200)),
    ))
    tabla = r["tablas"]["gorros"]

    assert tabla[11] == pytest.approx(160 / 105)
    assert tabla[0] == pytest.approx(100 / 105)
    assert sum(tabla) == pytest.approx(12.0)


def test_el_anio_reciente_pesa_mas_que_el_viejo():
    """Invertir los años cambia el resultado: la ponderación no es simétrica."""
    reciente_alto = calcular_indices(_historia(
        _filas_anio("A", "g", 2025, _con_pico_diciembre(100, 100)),
        _filas_anio("A", "g", 2026, _con_pico_diciembre(100, 200)),
    ))["tablas"]["g"]
    viejo_alto = calcular_indices(_historia(
        _filas_anio("A", "g", 2025, _con_pico_diciembre(100, 200)),
        _filas_anio("A", "g", 2026, _con_pico_diciembre(100, 100)),
    ))["tablas"]["g"]

    assert reciente_alto[11] > viejo_alto[11]


def test_un_solo_anio_renormaliza_los_pesos():
    """Con un año hay un solo peso disponible y vale 1.0, no 0.6.

    Si no se renormalizara, la serie entera quedaría escalada por 0.6 — cosa que
    la normalización final taparía, pero que rompería el promedio ponderado en
    cuanto un mes tuviera menos años que otro.
    """
    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 200)))
    )
    tabla = r["tablas"]["gorros"]

    promedio = (11 * 100 + 200) / 12
    assert tabla[11] == pytest.approx(200 / promedio)
    assert sum(tabla) == pytest.approx(12.0)


def test_tres_anios_con_dos_pesos_descarta_el_mas_viejo():
    """Sobran años -> se quedan los más recientes, el resto no aporta.

    2024 trae un diciembre de 1000 que, si entrara, movería el índice. El
    resultado tiene que ser idéntico al de los mismos dos años recientes solos.
    """
    con_tres = calcular_indices(_historia(
        _filas_anio("A", "gorros", 2024, _con_pico_diciembre(100, 1000)),
        _filas_anio("A", "gorros", 2025, _con_pico_diciembre(100, 100)),
        _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 200)),
    ))["tablas"]["gorros"]

    assert con_tres[11] == pytest.approx(160 / 105)


def test_pesos_configurables():
    """Con pesos 50/50 el diciembre ponderado es 150, no 160."""
    r = calcular_indices(
        _historia(
            _filas_anio("A", "gorros", 2025, _con_pico_diciembre(100, 100)),
            _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 200)),
        ),
        pesos_anios=(0.5, 0.5),
    )
    promedio = (11 * 100 + 150) / 12
    assert r["tablas"]["gorros"][11] == pytest.approx(150 / promedio)


# ─────────────────────────────────────────────────────────────────────────────
# calcular_indices — meta
# ─────────────────────────────────────────────────────────────────────────────

def test_corregido_por_quiebres_siempre_false():
    """No hay fuente de inventario histórico: el flag lo declara explícito."""
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert r["meta"]["corregido_por_quiebres"] is False


def test_meta_declara_el_agrupamiento():
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert r["meta"]["agrupado_por"] == "category"


def test_meta_cuenta_los_grupos_con_indice():
    r = calcular_indices(_historia(
        _filas_anio("A", "gorros", 2026, _plano()),
        _filas_anio("B", "bufandas", 2026, _plano()),
        _filas_anio("C", "medias", 2026, _plano())[:3],
    ))
    assert r["meta"]["grupos_con_indice"] == 2


def test_meta_cuenta_los_meses_cubiertos():
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert r["meta"]["meses_cubiertos"] == 12


def test_las_cuatro_claves_de_meta():
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert set(r["meta"]) == {
        "corregido_por_quiebres",
        "grupos_con_indice",
        "meses_cubiertos",
        "agrupado_por",
    }


def test_las_cuatro_claves_del_retorno():
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert set(r) == {"tablas", "descartados", "meses_estimados", "meta"}


# ─────────────────────────────────────────────────────────────────────────────
# calcular_indices — meses sin datos dentro de un grupo que sí califica
# ─────────────────────────────────────────────────────────────────────────────

def test_mes_sin_datos_queda_neutro_y_se_reporta():
    """Un grupo puede calificar por cantidad de meses y aun así no tener los 12.

    Julio sin una sola venta (lanzamiento a mitad de año, o producto que ese mes
    no se vendió) no puede inventar un índice: queda en 1.0 neutro. Pero, a
    diferencia del v3 de Fede —donde el 1.0 de relleno quedaba mudo y
    después nadie sabía si era medido— acá se REPORTA en `meses_estimados`.
    """
    filas = _filas_anio("A", "gorros", 2026, _plano())
    sin_julio = [f for f in filas if f["period"] != filas[6]["period"]]

    r = calcular_indices(_historia(sin_julio), minimo_meses=11)

    assert r["tablas"]["gorros"][6] == pytest.approx(1.0), "julio es el índice 6"
    assert r["meses_estimados"]["gorros"] == [7], "julio es el mes 7"


def test_grupo_completo_no_reporta_meses_estimados():
    r = calcular_indices(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert r["meses_estimados"].get("gorros", []) == []


def test_tabla_con_meses_rellenados_sigue_sumando_doce():
    """El relleno va ANTES de normalizar: si fuera al revés, la tabla se rompe.

    Con un pico en diciembre y julio sin datos, los 11 meses medidos aportan sus
    índices y julio aporta 1.0 — y el total tiene que seguir dando 12.
    """
    filas = _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 300))
    sin_julio = [f for f in filas if f["period"] != filas[6]["period"]]

    r = calcular_indices(_historia(sin_julio), minimo_meses=11)
    tabla = r["tablas"]["gorros"]

    assert sum(tabla) == pytest.approx(12.0)
    assert tabla[6] == pytest.approx(1.0)
    assert tabla[11] > 1.0, "diciembre sigue siendo el pico"


def test_varios_meses_rellenados_se_reportan_todos():
    filas = _filas_anio("A", "gorros", 2026, _plano())
    periods_fuera = {filas[1]["period"], filas[6]["period"]}  # febrero y julio
    recortada = [f for f in filas if f["period"] not in periods_fuera]

    r = calcular_indices(_historia(recortada), minimo_meses=10)

    assert r["meses_estimados"]["gorros"] == [2, 7]
    assert r["tablas"]["gorros"][1] == pytest.approx(1.0)
    assert r["tablas"]["gorros"][6] == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# indices_por_sku
# ─────────────────────────────────────────────────────────────────────────────

def test_indices_por_sku_agrupa_por_sku():
    """Dos SKUs de la MISMA categoría dan dos tablas, una por SKU."""
    r = indices_por_sku(_historia(
        _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 300)),
        _filas_anio("B", "gorros", 2026, _plano()),
    ))
    assert set(r["tablas"]) == {"A", "B"}


def test_indices_por_sku_separa_estacionalidades():
    """El punto de tener índice propio: dos SKUs de la misma categoría pueden
    tener temporadas distintas, y agrupar por categoría lo promediaría."""
    r = indices_por_sku(_historia(
        _filas_anio("A", "gorros", 2026, _con_pico_diciembre(100, 300)),
        _filas_anio("B", "gorros", 2026, _plano()),
    ))
    assert r["tablas"]["A"][11] > 1.0
    assert r["tablas"]["B"] == pytest.approx([1.0] * 12)


def test_indices_por_sku_declara_el_agrupamiento():
    r = indices_por_sku(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert r["meta"]["agrupado_por"] == "sku"


def test_indices_por_sku_mismo_shape_de_retorno():
    r = indices_por_sku(_historia(_filas_anio("A", "gorros", 2026, _plano())))
    assert set(r) == {"tablas", "descartados", "meses_estimados", "meta"}
    assert r["meta"]["corregido_por_quiebres"] is False


def test_indices_por_sku_descarta_igual():
    r = indices_por_sku(_historia(_filas_anio("A", "gorros", 2026, _plano())[:4]))
    assert "A" in r["descartados"]
    assert r["tablas"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# resolver_indice — la cascada
# ─────────────────────────────────────────────────────────────────────────────

def _tablas_cascada() -> dict:
    """SKU 'A' con tabla propia; categoría 'gorros' con la suya."""
    propia = [0.5] * 11 + [6.5]
    de_categoria = [2.0] * 11 + [-10.0]  # valores absurdos a propósito
    return {
        "sku": _resultado({"A": propia}, agrupado_por="sku"),
        "category": _resultado({"gorros": de_categoria}),
    }


def test_sku_con_tabla_propia_gana():
    indice, origen = resolver_indice(_tablas_cascada(), "A", "gorros", 12)
    assert origen == "sku"
    assert indice == pytest.approx(6.5)


def test_sku_sin_tabla_cae_a_su_categoria():
    indice, origen = resolver_indice(_tablas_cascada(), "SIN_TABLA", "gorros", 1)
    assert origen == "category"
    assert indice == pytest.approx(2.0)


def test_sin_sku_ni_categoria_cae_a_neutro():
    """El fallback nunca es cero: sin índice, el mes no corrige."""
    indice, origen = resolver_indice(_tablas_cascada(), "SIN_TABLA", "SIN_CAT", 6)
    assert origen == "neutro"
    assert indice == 1.0


def test_neutro_con_tablas_vacias():
    vacias = {"sku": _resultado({}), "category": _resultado({})}
    assert resolver_indice(vacias, "A", "gorros", 3) == (1.0, "neutro")


def test_resolver_respeta_el_mes():
    tablas = {
        "sku": _resultado({"A": [float(m) for m in range(1, 13)]}, agrupado_por="sku"),
        "category": _resultado({}),
    }
    for mes in range(1, 13):
        indice, origen = resolver_indice(tablas, "A", "gorros", mes)
        assert origen == "sku"
        assert indice == pytest.approx(float(mes))


@pytest.mark.parametrize("mes", [0, 13, -1, 100])
def test_resolver_con_mes_invalido_lanza(mes):
    with pytest.raises(ValueError):
        resolver_indice(_tablas_cascada(), "A", "gorros", mes)


def test_resolver_devuelve_tupla_de_dos():
    resultado = resolver_indice(_tablas_cascada(), "A", "gorros", 5)
    assert isinstance(resultado, tuple)
    assert len(resultado) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Integración — recuperar una estacionalidad conocida
# ─────────────────────────────────────────────────────────────────────────────

def test_recupera_una_estacionalidad_sembrada():
    """Serie con diciembre vendiendo 3x el promedio -> índice de diciembre 3.0.

    Los números están elegidos para que el índice dé 3.0 EXACTO: con 11 meses de
    300 y diciembre en 1100, el promedio mensual es 4400/12 = 366.67 y
    1100/366.67 = 3.0. Ojo: 3.0 es justo el techo del clamp, así que este test
    solo no distingue "lo calculó" de "lo recortó" — por eso va acompañado del
    test siguiente, con un pico por debajo del techo.
    """
    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, _con_pico_diciembre(300, 1100)))
    )
    tabla = r["tablas"]["gorros"]

    assert tabla[11] == pytest.approx(3.0)
    assert tabla[0] == pytest.approx(300 / (4400 / 12))
    assert sum(tabla) == pytest.approx(12.0)


def test_recupera_un_pico_por_debajo_del_clamp():
    """Mismo ejercicio con un pico que no toca el techo: el valor sale del cálculo.

    11 meses de 400 y diciembre en 1000 -> promedio 450, índice 1000/450 = 2.22.
    """
    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, _con_pico_diciembre(400, 1000)))
    )
    tabla = r["tablas"]["gorros"]

    assert tabla[11] == pytest.approx(1000 / 450)
    assert tabla[11] < 3.0, "este pico no puede estar tocando el clamp"
    assert tabla[0] == pytest.approx(400 / 450)


def test_un_valle_tambien_se_recupera():
    """El mes flojo tiene que quedar por debajo de 1, no aplanado.

    NO BAJAR EL 50. El valle está elegido para quedar por encima del piso del
    clamp: con 50 el índice da 0.5217, holgado sobre el 0.25 de CLAMP_DEFAULT.
    Con un valle de 20 el índice daría 0.2143, el clamp lo recortaría a 0.25 y
    el test pasaría a medir el clamp en vez del cálculo — que es justamente lo
    que no queremos acá, porque el clamp ya tiene sus propios tests en
    test_supply_seasonality.py. Es el espejo exacto de
    test_recupera_un_pico_por_debajo_del_clamp, del lado del valle.
    """
    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, [100] * 11 + [50]))
    )
    tabla = r["tablas"]["gorros"]
    promedio = (11 * 100 + 50) / 12

    assert tabla[11] == pytest.approx(50 / promedio)
    assert tabla[11] > 0.25, "este valle no puede estar tocando el piso del clamp"
    assert tabla[11] < 1.0


def test_la_tabla_calculada_la_consume_b2_1a():
    """Contrato con core/supply/seasonality.py: lo que sale de acá entra allá.

    Es el handshake entre los dos bloques: `indice_mes` tiene que poder leer una
    tabla recién calculada sin ninguna conversión intermedia.
    """
    from core.supply.seasonality import indice_mes, validar_tabla

    r = calcular_indices(
        _historia(_filas_anio("A", "gorros", 2026, _con_pico_diciembre(400, 1000)))
    )

    assert indice_mes(r["tablas"], "gorros", 12) == pytest.approx(1000 / 450)
    assert validar_tabla(r["tablas"])["largo_invalido"] == []
    assert validar_tabla(r["tablas"])["sin_normalizar"] == []
