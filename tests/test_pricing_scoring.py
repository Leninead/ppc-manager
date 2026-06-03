"""Characterization tests para M30 F3.3 — scoring engine + orchestrator.

Port verbatim del HTML (.claude/porting-sources/pricing-dashboard.html):
    computeAIS    (L934-940)  -> _compute_ais
    computeScore  (L998-1155) -> _compute_score
    enrichRecord  (L925)      -> _enrich_record
    runAnalysis   (L800-924)  -> _run_analysis

Estos tests CONGELAN el comportamiento verbatim (incluida la asimetría de umbrales
y el bug 30-vs-37). NO son specs de "lo correcto": son specs de "lo que hace el HTML".
"""

import pytest

from modules.pages.pricing_dashboard import _compute_ais, _compute_score

CONFIG6 = {"current_month": 6}  # determinístico para isOffSeason


# =====================================================================
# B5 — _compute_ais (Aged Inventory Surcharge, 8 buckets)
# =====================================================================
_AIS_KEYS = [
    "estimated-ais-181-210-days",
    "estimated-ais-211-240-days",
    "estimated-ais-241-270-days",
    "estimated-ais-271-300-days",
    "estimated-ais-301-330-days",
    "estimated-ais-331-365-days",
    "estimated-ais-366-455-days",
    "estimated-ais-456-plus-days",
]


class TestComputeAis:
    def test_suma_de_los_8_buckets(self):
        rec = {k: float(i + 1) for i, k in enumerate(_AIS_KEYS)}  # 1..8
        assert _compute_ais(rec) == 36.0  # 1+2+...+8

    def test_suma_valores_mixtos(self):
        rec = dict.fromkeys(_AIS_KEYS, 0)
        rec[_AIS_KEYS[0]] = 12.5
        rec[_AIS_KEYS[7]] = 7.5
        assert _compute_ais(rec) == 20.0

    def test_buckets_ausentes_son_cero(self):
        # solo 2 de los 8 presentes; el resto ausente -> 0 (parseFloat(r[c]||0)||0)
        rec = {_AIS_KEYS[2]: 10, _AIS_KEYS[5]: 5}
        assert _compute_ais(rec) == 15.0

    def test_buckets_none_son_cero(self):
        rec = dict.fromkeys(_AIS_KEYS, None)
        rec[_AIS_KEYS[0]] = 9
        assert _compute_ais(rec) == 9.0

    def test_todos_en_cero(self):
        rec = dict.fromkeys(_AIS_KEYS, 0)
        assert _compute_ais(rec) == 0.0

    def test_record_vacio(self):
        assert _compute_ais({}) == 0.0


# =====================================================================
# B6 — _compute_score (20+ reglas, umbrales asimétricos)
# =====================================================================
def _base() -> dict:
    """Record neutro: ninguna regla dispara -> score 0, classification 'mantener'."""
    return {
        "Temporada": "Verano",
        "fba_dos": 50,
        "total_dos": 100,
        "has_backup": False,
        "total_stock": 100,
        "fba_available": 100,
        "t7": 2,
        "t30": 10,
        "sell_through": 1.0,
        "aging_181_270": 0,
        "aging_271_365": 0,
        "aging_366plus": 0,
        "health": "",
        "ais_total": 0,
        "no_sale_6m": "0",
        "price": 20,
        "buybox_price": 0,
        "subcat_avg": None,
        "gross_margin": None,
        "cogs": None,
        "daily_rate": 1.0,
        "awd_available": 0,
        "izzi_available": 0,
    }


class TestComputeScore:
    def test_baseline_score_cero_mantener(self):
        r = _compute_score(_base(), CONFIG6)
        assert r["score"] == 0
        assert r["classification"] == "mantener"
        assert r["is_liquidar"] is False
        assert r["restock_alert"] is None

    # --- reglas puntuales (delta del score) ---
    def test_dos_fba_180_resta_30(self):
        rec = _base()
        rec["fba_dos"] = 200
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -30
        assert "DoS FBA 200d" in r["reasons_down"]

    def test_health_excess_resta_20(self):
        rec = _base()
        rec["health"] = "Excess"
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -20
        assert "FBA Excess" in r["reasons_down"]

    def test_health_out_of_stock_suma_30(self):
        rec = _base()
        rec["health"] = "Out of stock"
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == 30
        assert "Out of stock" in r["reasons_up"]

    def test_ais_resta_15_y_reason_tofixed(self):
        rec = _base()
        rec["ais_total"] = 5
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -15
        assert "AIS $5.00" in r["reasons_down"]  # toFixed(2)

    # --- umbral asimétrico BAJAR (score <= -50) en el borde exacto ---
    def test_umbral_bajar_menos_49_es_mantener(self):
        # DoS120(-18) + off-season(-8) + AIS(-15) + T7↓(-8) = -49
        rec = _base()
        rec.update({"Temporada": "Invierno", "fba_dos": 150, "total_dos": 200,
                    "ais_total": 5, "t7": 0, "t30": 10})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -49
        assert r["classification"] == "mantener"  # -49 > -50

    def test_umbral_bajar_menos_50_es_bajar(self):
        # DoS180(-30) + Excess(-20) = -50 (borde inclusive)
        rec = _base()
        rec.update({"fba_dos": 200, "total_dos": 300, "health": "Excess"})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -50
        assert r["classification"] == "bajar"  # <= -50

    def test_umbral_bajar_menos_51_es_bajar(self):
        # DoS120(-18) + off(-8) + aging181(-10) + AIS(-15) = -51
        rec = _base()
        rec.update({"Temporada": "Invierno", "fba_dos": 150, "total_dos": 200,
                    "aging_181_270": 5, "ais_total": 5, "t7": 2, "t30": 10})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -51
        assert r["classification"] == "bajar"

    # --- umbral asimétrico SUBIR (score >= 20) en el borde ---
    # Nota: con los pesos enteros del HTML, score 19 y 21 exacto no son
    # construibles limpiamente; se usa 18 (mantener) / 20 (subir) / 21 (subir)
    # para probar la inclusividad del >= 20 sin off-by-one.
    def test_umbral_subir_18_es_mantener(self):
        # ST alto(+10) + margen>=40(+8) = 18
        rec = _base()
        rec.update({"sell_through": 2.5, "gross_margin": 45})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == 18
        assert r["classification"] == "mantener"  # 18 < 20

    def test_umbral_subir_20_es_subir(self):
        # Low stock(+20) (borde inclusive)
        rec = _base()
        rec["health"] = "Low stock"
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == 20
        assert r["classification"] == "subir"  # >= 20

    def test_umbral_subir_21_es_subir(self):
        # Low stock(+20) + subcat<-15%(+8) + margen>=40(+8) + AIS(-15) = 21
        rec = _base()
        rec.update({"health": "Low stock", "subcat_avg": 30, "gross_margin": 45,
                    "ais_total": 5})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == 21
        assert r["classification"] == "subir"

    # --- is_liquidar precede a la clasificación por score ---
    def test_is_liquidar_precede_a_subir(self):
        # score >= 20 (Low stock +20 + ST>3 +20 - aging366 -20 = 20) PERO is_liquidar
        rec = _base()
        rec.update({"health": "Low stock", "sell_through": 4.0,
                    "aging_366plus": 5, "t30": 2, "t7": 0})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == 20            # daría 'subir' por score
        assert r["is_liquidar"] is True    # aging366>0 and t30<=3
        assert r["classification"] == "liquidar"  # liquidar gana

    # --- margin_block bloquea 'bajar' -> 'mantener' ---
    def test_margin_block_bloquea_bajar(self):
        # -50 (DoS180 + Excess) pero gross 10 (<15) -> 'mantener'
        rec = _base()
        rec.update({"fba_dos": 200, "total_dos": 300, "health": "Excess",
                    "gross_margin": 10})
        r = _compute_score(rec, CONFIG6)
        assert r["score"] == -50
        assert r["classification"] == "mantener"
        assert "⚠ Bloqueado: margen bajo" in r["reasons_down"]

    # --- PATH-30 (restock dentro de computeScore): guard + disparo ---
    def test_path30_guard_no_pisa_restock_existente(self):
        # condiciones de path-30 se cumplen, pero restock_alert ya viene seteado
        rec = _base()
        rec.update({"fba_dos": 20, "total_dos": 100, "has_backup": True,
                    "daily_rate": 1.0, "fba_available": 10,
                    "awd_available": 25, "izzi_available": 0,
                    "restock_alert": "PREEXISTENTE"})
        r = _compute_score(rec, CONFIG6)
        assert r["restock_alert"] == "PREEXISTENTE"  # guard !restock_alert

    def test_path30_dispara_cuando_restock_none(self):
        # mismo caso pero restock_alert None -> path-30 arma el mensaje "desde"
        rec = _base()
        rec.update({"fba_dos": 20, "total_dos": 100, "has_backup": True,
                    "daily_rate": 1.0, "fba_available": 10,
                    "awd_available": 25, "izzi_available": 0})
        r = _compute_score(rec, CONFIG6)
        # round(1.0*30)=30 ; 30-10=20 ; min(20,25)=20 ; awd>=20 -> AWD
        assert r["restock_alert"] == "Mover 20u desde AWD"  # PATH-30: "desde" (no "a FBA")
