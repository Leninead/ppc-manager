"""Tests de core/supply_seasonality.py — M37 B2.1a, índices estacionales.

Los invariantes que se defienden acá, todos de la misma familia: **ausencia de
dato no es cero**.

- `dias_sin_stock=None` significa "no tengo observación de inventario", no
  "no hubo quiebres". Si se tratara como cero, un SKU sin dato de stock
  entraría al modelo como si hubiera estado disponible todo el período, y su
  demanda quedaría subestimada exactamente igual que en el bug que la
  corrección por quiebres viene a arreglar.
- Evidencia insuficiente (pocos días con stock) devuelve None, no un número
  inventado. Es la lección del `sw = 0.8 × dw` del Laboratorio de Fede: un SKU
  con una sola semana observada recibía un desvío fabricado.
- Una subcategoría sin índice cae a 1.0 (neutro), no a 0 ni a excepción. Mismo
  fallback que el JS del Lab (`IDX[s.sub] || new Array(12).fill(1)`).

Contexto y evidencia de las tablas reales: `notes/supply-chain/hallazgos-tablas-indices.md`.
"""

from __future__ import annotations

import pytest

from core.supply_seasonality import (
    demanda_corregida,
    desestacionalizar,
    indice_mes,
    normalizar_tabla,
    reestacionalizar,
    validar_tabla,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — datos reales, no sintéticos
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tabla_gamboa() -> dict[str, list[float]]:
    """Dos filas literales del Laboratorio de Compras de Fede (2026-08-17).

    Extraídas del JSON embebido `"idx"` del HTML original, copiado en
    `notes/supply-chain/originales/laboratorio-compras-2026-08-17.html`.

    - `Chinstrap Clasica` suma exactamente 12.000 → fila limpia y normalizada.
    - `Tela - bandera USA` suma 8.5 → quedó así porque el clamp [0.25, 3.0] se
      aplicó DESPUÉS de normalizar. Sus valores están EN el borde del clamp,
      no fuera: no debe marcarse como `fuera_de_clamp`.
    """
    return {
        "Chinstrap Clasica": [
            0.457, 0.501, 0.859, 1.439, 1.804, 1.877,
            2.081, 0.957, 0.692, 0.553, 0.388, 0.392,
        ],
        "Tela - bandera USA": [
            0.25, 0.25, 0.25, 0.25, 0.25, 3.0,
            3.0, 0.25, 0.25, 0.25, 0.25, 0.25,
        ],
    }


@pytest.fixture
def tabla_limpia(tabla_gamboa) -> dict[str, list[float]]:
    """Solo la fila sana: ningún problema que `validar_tabla` deba reportar."""
    return {"Chinstrap Clasica": tabla_gamboa["Chinstrap Clasica"]}


def _suma(valores: list[float]) -> float:
    """Azúcar para las aserciones de normalización."""
    return sum(valores)


# ─────────────────────────────────────────────────────────────────────────────
# demanda_corregida — sin dato de inventario
# ─────────────────────────────────────────────────────────────────────────────

def test_sin_dato_de_stock_devuelve_venta_cruda():
    """None = 'no hay observación de inventario' → no se corrige nada."""
    assert demanda_corregida(70, 7, None) == pytest.approx(10.0)


def test_sin_dato_de_stock_no_es_lo_mismo_que_cero_quiebres():
    """El caso que motiva que None y 0 sean ramas distintas.

    Con `None` no se evalúa el mínimo de días: no hay nada que evaluar. Con un
    0 explícito sí, y un período corto cae por debajo del mínimo.
    """
    assert demanda_corregida(10, 2, None) == pytest.approx(5.0)
    assert demanda_corregida(10, 2, 0) is None


def test_default_de_dias_periodo_es_semanal():
    """La serie del Laboratorio es semanal; el default lo refleja."""
    assert demanda_corregida(70) == pytest.approx(10.0)


# ─────────────────────────────────────────────────────────────────────────────
# demanda_corregida — con dato de inventario
# ─────────────────────────────────────────────────────────────────────────────

def test_quiebre_parcial_corrige_por_dias_con_stock():
    """7 días, 2 sin stock → 20 unidades sobre 5 días reales, no sobre 7."""
    assert demanda_corregida(20, 7, 2) == pytest.approx(4.0)


def test_quiebre_parcial_no_penaliza_como_si_no_hubiera_demanda():
    """La corrección siempre da >= que la venta cruda. Es el punto del ejercicio."""
    cruda = demanda_corregida(20, 7, None)
    corregida = demanda_corregida(20, 7, 2)
    assert corregida > cruda


def test_sin_quiebres_equivale_a_venta_cruda():
    assert demanda_corregida(20, 7, 0) == pytest.approx(demanda_corregida(20, 7, None))


def test_piso_acota_el_ratio_en_ventana_mensual():
    """El `max(10, 30 - dias_sin_stock)` del SCS, con sus parámetros.

    Un SKU con 27 de 30 días quebrado divide por 10, no por 3: sin el piso el
    ratio explota y el forecast pide de más.
    """
    assert demanda_corregida(20, 30, 27, piso=10, minimo_dias=1) == pytest.approx(2.0)


def test_sin_piso_el_ratio_explotaria():
    """Contraste explícito del test anterior: 20/3 vs 20/10."""
    con_piso = demanda_corregida(20, 30, 27, piso=10, minimo_dias=1)
    sin_piso = demanda_corregida(20, 30, 27, piso=1, minimo_dias=1)
    assert sin_piso == pytest.approx(20 / 3)
    assert con_piso < sin_piso


def test_con_defaults_el_piso_nunca_llega_a_actuar():
    """Con piso=3 y minimo_dias=4, todo caso que sobrevive al mínimo tiene
    dias_con_stock >= 4 > piso. El piso solo muerde con parámetros custom
    (ventana mensual estilo SCS). Queda pineado para que nadie lo toque
    creyendo que es dead code.
    """
    for dias_sin_stock in range(0, 4):  # dias_con_stock de 7 a 4
        dias_con_stock = 7 - dias_sin_stock
        assert demanda_corregida(28, 7, dias_sin_stock) == pytest.approx(28 / dias_con_stock)


# ─────────────────────────────────────────────────────────────────────────────
# demanda_corregida — evidencia insuficiente
# ─────────────────────────────────────────────────────────────────────────────

def test_por_debajo_del_minimo_de_dias_devuelve_none():
    """7 días con 5 quebrados = 2 días de evidencia. No alcanza: None, no un número."""
    resultado = demanda_corregida(20, 7, 5)
    assert resultado is None
    assert resultado != 0, "un 0 se leería como 'no vende', y el dato es 'no sé'"


def test_el_minimo_de_dias_es_inclusivo():
    """Frontera exacta: 4 días con stock alcanzan, 3 no."""
    assert demanda_corregida(20, 7, 3) == pytest.approx(5.0)   # 4 días con stock
    assert demanda_corregida(20, 7, 4) is None                  # 3 días con stock


def test_minimo_de_dias_configurable():
    """Bajar el mínimo habilita el caso que con el default se descartaba."""
    assert demanda_corregida(20, 7, 5) is None
    assert demanda_corregida(20, 7, 5, minimo_dias=2) is not None


def test_periodo_entero_quebrado_devuelve_none():
    assert demanda_corregida(0, 7, 7) is None


# ─────────────────────────────────────────────────────────────────────────────
# demanda_corregida — cero real vs ausencia
# ─────────────────────────────────────────────────────────────────────────────

def test_cero_unidades_con_stock_completo_es_cero_real():
    """Tuvo stock los 7 días y no vendió: eso es dato, no ausencia de dato."""
    resultado = demanda_corregida(0, 7, 0)
    assert resultado == 0.0
    assert resultado is not None


def test_cero_unidades_sin_dato_de_stock_tambien_es_cero():
    assert demanda_corregida(0, 7, None) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# demanda_corregida — inputs inválidos
# ─────────────────────────────────────────────────────────────────────────────

def test_dias_sin_stock_mayor_al_periodo_lanza():
    with pytest.raises(ValueError):
        demanda_corregida(10, 7, 8)


def test_dias_sin_stock_negativo_lanza():
    with pytest.raises(ValueError):
        demanda_corregida(10, 7, -1)


@pytest.mark.parametrize("dias_periodo", [0, -1, -7])
def test_periodo_no_positivo_lanza(dias_periodo):
    with pytest.raises(ValueError):
        demanda_corregida(10, dias_periodo, None)


# ─────────────────────────────────────────────────────────────────────────────
# indice_mes
# ─────────────────────────────────────────────────────────────────────────────

def test_indice_mes_enero_es_la_posicion_cero(tabla_gamboa):
    """mes=1 (enero) → índice 0 de la lista. El off-by-one es el bug obvio acá."""
    assert indice_mes(tabla_gamboa, "Chinstrap Clasica", 1) == pytest.approx(0.457)


def test_indice_mes_diciembre_es_la_posicion_once(tabla_gamboa):
    assert indice_mes(tabla_gamboa, "Chinstrap Clasica", 12) == pytest.approx(0.392)


def test_indice_mes_pico_de_temporada(tabla_gamboa):
    """Julio es el pico real de Chinstrap Clasica (2.081)."""
    assert indice_mes(tabla_gamboa, "Chinstrap Clasica", 7) == pytest.approx(2.081)


def test_indice_mes_recorre_los_doce(tabla_gamboa):
    esperados = tabla_gamboa["Chinstrap Clasica"]
    for mes in range(1, 13):
        assert indice_mes(tabla_gamboa, "Chinstrap Clasica", mes) == pytest.approx(
            esperados[mes - 1]
        )


def test_subcat_inexistente_cae_a_neutro(tabla_gamboa):
    """Fallback del JS del Lab: sin índice, el mes no corrige (×1.0). No lanza."""
    assert indice_mes(tabla_gamboa, "Subcat Que No Existe", 6) == 1.0


def test_subcat_inexistente_no_lanza_en_ningun_mes(tabla_gamboa):
    for mes in range(1, 13):
        assert indice_mes(tabla_gamboa, "Polaina", mes) == 1.0


def test_tabla_vacia_cae_a_neutro():
    assert indice_mes({}, "lo que sea", 1) == 1.0


def test_subcat_con_largo_invalido_cae_a_neutro():
    """Una lista de 5 meses no es una tabla estacional: neutro, no IndexError."""
    tabla = {"Rota": [1.0, 2.0, 3.0, 4.0, 5.0]}
    assert indice_mes(tabla, "Rota", 3) == 1.0


@pytest.mark.parametrize("mes", [0, 13, -1, 100])
def test_mes_fuera_de_rango_lanza(tabla_gamboa, mes):
    with pytest.raises(ValueError):
        indice_mes(tabla_gamboa, "Chinstrap Clasica", mes)


# ─────────────────────────────────────────────────────────────────────────────
# desestacionalizar / reestacionalizar
# ─────────────────────────────────────────────────────────────────────────────

def test_desestacionalizar_divide_por_el_indice():
    assert desestacionalizar(20.0, 2.0) == pytest.approx(10.0)


def test_reestacionalizar_multiplica_por_el_indice():
    assert reestacionalizar(10.0, 2.0) == pytest.approx(20.0)


def test_ida_y_vuelta_vuelve_al_original(tabla_gamboa):
    """Con índices reales, des→re tiene que ser identidad dentro de tolerancia."""
    demanda = 137.4
    for mes in range(1, 13):
        idx = indice_mes(tabla_gamboa, "Chinstrap Clasica", mes)
        base = desestacionalizar(demanda, idx)
        assert reestacionalizar(base, idx) == pytest.approx(demanda)


def test_indice_neutro_no_altera_la_demanda():
    assert desestacionalizar(42.0, 1.0) == pytest.approx(42.0)
    assert reestacionalizar(42.0, 1.0) == pytest.approx(42.0)


@pytest.mark.parametrize("indice", [0.0, -1.0, -0.5])
def test_desestacionalizar_con_indice_no_positivo_devuelve_none(indice):
    """Ni división por cero ni demanda negativa: None y que el caller decida."""
    assert desestacionalizar(20.0, indice) is None


def test_desestacionalizar_propaga_none():
    """Si la demanda ya venía sin evidencia, el resultado sigue sin evidencia."""
    assert desestacionalizar(None, 1.5) is None


def test_desestacionalizar_de_cero_es_cero():
    assert desestacionalizar(0.0, 1.5) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# normalizar_tabla
# ─────────────────────────────────────────────────────────────────────────────

def test_normalizar_lleva_la_suma_a_doce():
    """Media 1.0 ⇔ suma 12. Sin valores extremos, el clamp no interviene."""
    tabla = {"Suave": [2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3]}
    resultado = normalizar_tabla(tabla)
    assert _suma(resultado["Suave"]) == pytest.approx(12.0)


def test_normalizar_preserva_la_forma_relativa():
    """Escalar no puede cambiar qué mes es el pico ni la razón entre meses."""
    tabla = {"Suave": [2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3]}
    resultado = normalizar_tabla(tabla)["Suave"]
    assert resultado[6] / resultado[0] == pytest.approx(1.5)


def test_tabla_ya_normalizada_no_cambia(tabla_limpia):
    """`Chinstrap Clasica` ya suma 12: normalizar tiene que ser idempotente."""
    resultado = normalizar_tabla(tabla_limpia)
    assert _suma(resultado["Chinstrap Clasica"]) == pytest.approx(12.0)
    for antes, despues in zip(tabla_limpia["Chinstrap Clasica"], resultado["Chinstrap Clasica"]):
        assert despues == pytest.approx(antes)


def test_el_clamp_se_aplica_DESPUES_de_normalizar():
    """El invariante que explica las filas rotas de Fede.

    Un mes extremo que post-normalización supera 3.0 queda clampeado, y por eso
    la fila ya NO suma 12. Si el clamp se aplicara ANTES, el resultado seguiría
    sumando 12 y no habría forma de que existiera un `Tela - bandera USA`.
    """
    tabla = {"Extrema": [10.0] + [0.1] * 11}
    resultado = normalizar_tabla(tabla)["Extrema"]

    assert resultado[0] == pytest.approx(3.0), "el pico se clampea al techo"
    assert all(v == pytest.approx(0.25) for v in resultado[1:]), "el resto al piso"
    assert _suma(resultado) != pytest.approx(12.0), (
        "si sumara 12 el clamp se habría aplicado antes de normalizar"
    )


def test_clamp_configurable():
    tabla = {"Extrema": [10.0] + [0.1] * 11}
    resultado = normalizar_tabla(tabla, clamp=(0.5, 2.0))["Extrema"]
    assert resultado[0] == pytest.approx(2.0)
    assert all(v == pytest.approx(0.5) for v in resultado[1:])


def test_lista_de_ceros_queda_neutra():
    """Sin señal no se inventa estacionalidad: doce unos."""
    resultado = normalizar_tabla({"Muerta": [0.0] * 12})
    assert resultado["Muerta"] == [1.0] * 12


def test_lista_que_suma_cero_queda_neutra():
    resultado = normalizar_tabla({"Cancelada": [0] * 12})
    assert resultado["Cancelada"] == [1.0] * 12


def test_largo_invalido_se_saltea_sin_romper():
    """Una lista que no tiene 12 meses se deja como está; no aborta la tabla."""
    tabla = {
        "Rota": [1.0, 2.0, 3.0],
        "Sana": [2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3],
    }
    resultado = normalizar_tabla(tabla)
    assert resultado["Rota"] == [1.0, 2.0, 3.0]
    assert _suma(resultado["Sana"]) == pytest.approx(12.0)


def test_normalizar_no_muta_la_entrada(tabla_gamboa):
    """La tabla original tiene que quedar intacta: es dato de otro módulo."""
    copia = {k: list(v) for k, v in tabla_gamboa.items()}
    normalizar_tabla(tabla_gamboa)
    assert tabla_gamboa == copia


def test_normalizar_tabla_vacia():
    assert normalizar_tabla({}) == {}


def test_renormalizar_una_fila_clampeada_no_la_arregla(tabla_gamboa):
    """`normalizar_tabla` NO es idempotente sobre una fila ya clampeada.

    `Tela - bandera USA` suma 8.5. Al renormalizar, el factor es 12/8.5 = 1.412
    y el pico de 3.0 se va a 4.24 → el clamp lo baja otra vez a 3.0. Resultado:
    9.53, no 12. La fila no se recupera escalándola; hace falta el dato crudo.

    Vale la pena pinearlo porque la tentación obvia (correr `normalizar_tabla`
    sobre las tablas de Fede para "arreglarlas") no funciona.
    """
    resultado = normalizar_tabla({"USA": tabla_gamboa["Tela - bandera USA"]})["USA"]

    assert resultado[5] == pytest.approx(3.0), "el pico vuelve a chocar el techo"
    assert resultado[0] == pytest.approx(0.25 * 12 / 8.5)
    assert _suma(resultado) == pytest.approx(9.529411, abs=1e-5)
    assert _suma(resultado) < 12.0


# ─────────────────────────────────────────────────────────────────────────────
# validar_tabla
# ─────────────────────────────────────────────────────────────────────────────

def test_validar_tabla_limpia(tabla_limpia):
    """Fila real y sana: ok=True y las cuatro listas vacías."""
    r = validar_tabla(tabla_limpia)
    assert r["ok"] is True
    assert r["sin_normalizar"] == []
    assert r["con_meses_neutros"] == []
    assert r["fuera_de_clamp"] == []
    assert r["largo_invalido"] == []


def test_validar_devuelve_las_cinco_claves(tabla_limpia):
    r = validar_tabla(tabla_limpia)
    assert set(r) == {
        "ok",
        "sin_normalizar",
        "con_meses_neutros",
        "fuera_de_clamp",
        "largo_invalido",
    }


def test_validar_tabla_vacia_es_ok():
    r = validar_tabla({})
    assert r["ok"] is True


def test_detecta_sin_normalizar(tabla_gamboa):
    """`Tela - bandera USA` suma 8.5 → se aparta de 12 en mucho más que 0.01."""
    r = validar_tabla(tabla_gamboa)
    assert "Tela - bandera USA" in r["sin_normalizar"]
    assert "Chinstrap Clasica" not in r["sin_normalizar"]
    assert r["ok"] is False


def test_la_fila_clampeada_no_se_marca_fuera_de_clamp(tabla_gamboa):
    """0.25 y 3.0 están EN el borde, no fuera. El chequeo es estricto (<, >)."""
    r = validar_tabla(tabla_gamboa)
    assert "Tela - bandera USA" not in r["fuera_de_clamp"]


def test_la_fila_clampeada_no_tiene_meses_neutros(tabla_gamboa):
    """Ninguno de sus valores es exactamente 1.0."""
    r = validar_tabla(tabla_gamboa)
    assert "Tela - bandera USA" not in r["con_meses_neutros"]


def test_tolerancia_de_normalizacion_es_un_centesimo():
    """12.005 pasa, 12.02 no. Pinea el umbral de 0.01."""
    casi = {"Casi": [1.0] * 11 + [1.005]}          # suma 12.005
    lejos = {"Lejos": [1.0] * 11 + [1.02]}         # suma 12.02
    assert validar_tabla(casi)["sin_normalizar"] == []
    assert validar_tabla(lejos)["sin_normalizar"] == ["Lejos"]


def test_detecta_meses_neutros():
    """Un 1.0 exacto es la huella del mes descartado por disponibilidad < 70%."""
    tabla = {"Ruana": [1.0] * 8 + [2.1176, 1.0, 6.3529, 3.5294]}
    r = validar_tabla(tabla)
    assert "Ruana" in r["con_meses_neutros"]
    assert r["ok"] is False


def test_detecta_fuera_de_clamp_por_arriba():
    tabla = {"Picuda": [5.0] + [0.6363] * 11}
    r = validar_tabla(tabla)
    assert "Picuda" in r["fuera_de_clamp"]
    assert r["ok"] is False


def test_detecta_fuera_de_clamp_por_abajo():
    tabla = {"Plana": [0.1] + [1.0809] * 11}
    r = validar_tabla(tabla)
    assert "Plana" in r["fuera_de_clamp"]
    assert r["ok"] is False


def test_detecta_largo_invalido():
    tabla = {"Corta": [1.0, 1.0, 1.0]}
    r = validar_tabla(tabla)
    assert "Corta" in r["largo_invalido"]
    assert r["ok"] is False


def test_detecta_los_cuatro_problemas_a_la_vez():
    """Una tabla podrida tiene que reportar cada problema en su propia lista."""
    tabla = {
        "SinNormalizar": [2.0] * 12,                     # suma 24
        "ConNeutros": [1.0] + [1.0909] * 11,             # suma 13 → también sin normalizar
        "FueraDeClamp": [5.0] + [0.6363] * 11,           # pico 5.0
        "Corta": [1.0, 2.0],                             # 2 meses
        "Sana": [1.0] * 12,                              # ojo: doce 1.0 son neutros
    }
    r = validar_tabla(tabla)
    assert "SinNormalizar" in r["sin_normalizar"]
    assert "ConNeutros" in r["con_meses_neutros"]
    assert "FueraDeClamp" in r["fuera_de_clamp"]
    assert "Corta" in r["largo_invalido"]
    assert r["ok"] is False


def test_largo_invalido_no_se_cuela_en_las_otras_listas():
    """Una lista rota no se evalúa por suma ni por clamp: se reporta una vez."""
    r = validar_tabla({"Corta": [1.0, 2.0]})
    assert r["largo_invalido"] == ["Corta"]
    assert r["sin_normalizar"] == []
    assert r["fuera_de_clamp"] == []


def test_ok_es_false_si_hay_cualquier_problema():
    assert validar_tabla({"X": [2.0] * 12})["ok"] is False


def test_validar_no_muta_la_entrada(tabla_gamboa):
    copia = {k: list(v) for k, v in tabla_gamboa.items()}
    validar_tabla(tabla_gamboa)
    assert tabla_gamboa == copia


# ─────────────────────────────────────────────────────────────────────────────
# Integración de la capa: el flujo real de B2.1
# ─────────────────────────────────────────────────────────────────────────────

def test_flujo_completo_semana_quebrada(tabla_gamboa):
    """El camino que va a recorrer el motor: venta cruda → corregida → base.

    Julio (índice 2.081) con 2 días de quiebre: la demanda desestacionalizada
    tiene que quedar MUY por debajo de la venta diaria observada, porque julio
    es pico de temporada y no representa el nivel de base del SKU.
    """
    diaria = demanda_corregida(20, 7, 2)
    assert diaria == pytest.approx(4.0)

    idx_julio = indice_mes(tabla_gamboa, "Chinstrap Clasica", 7)
    base = desestacionalizar(diaria, idx_julio)
    assert base == pytest.approx(4.0 / 2.081)
    assert base < diaria

    proyectado_diciembre = reestacionalizar(base, indice_mes(tabla_gamboa, "Chinstrap Clasica", 12))
    assert proyectado_diciembre < diaria, "diciembre es valle, tiene que proyectar menos"


def test_flujo_completo_sin_evidencia_propaga_none(tabla_gamboa):
    """Sin días con stock suficientes, la cadena entera devuelve None."""
    diaria = demanda_corregida(20, 7, 6)
    assert diaria is None
    assert desestacionalizar(diaria, indice_mes(tabla_gamboa, "Chinstrap Clasica", 7)) is None
