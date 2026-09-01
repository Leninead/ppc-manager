"""Genera un Bulk File sintético con la estructura del export real de Amazon.

    python tests/fixtures/make_bulk_fixture.py

Salida: tests/fixtures/bulk_sintetico.xlsx — 2 hojas.

DATOS 100% INVENTADOS. Marca ficticia "Nordic Sleep", ASINs B0TEST000NN,
IDs numéricos armados a mano. Nunca meter datos de clientes reales acá.

Lo que el fixture reproduce a propósito (no "arreglar"):

  - `Campaign ID` / `Ad Group ID` sin nulos  -> pandas los lee como int64.
  - `Keyword ID` con nulos (filas PT)        -> pandas los lee como float64,
    y un float64 de 15 dígitos se imprime en notación científica
    (4.091515e+14). Amazon rechaza eso. El parser tiene que normalizarlo.
  - `Product Targeting ID` con nulos (filas KW) -> idem.
  - Un `Match Type` en minúscula ("broad", fila 14): Amazon no es consistente
    en el casing, y INV-5.3 exige Title Case.

Mapa de filas del STR (ver docstring de cada bloque abajo):
   1 Exact + RANKING, 0 orders      -> INV-11.1 lo excluye (viene de Exact)
   2 Phrase + DISCOVERY, 0 orders   -> negativizable; su CST además existe
                                       como Exact enabled -> dispara INV-11.2
   3 Broad, 12 clicks               -> bajo threshold de INV-3
   4 Product Targeting manual       -> INV-11.1 lo excluye
   5 Phrase + RANKING, 0 orders     -> INV-11.3 lo protege
   6 Broad, harvest regla principal (orders>=3, ACoS<=25%)
   7 Broad, harvest por CVR alto (CVR>=10%, clicks>=15)
   8 Phrase, harvest por volumen (orders>=5) con ACoS 140% -> INV-4 sin techo
   9 Broad, CTR bajo (3000 imp, CTR 0.10%)
  10 Phrase, ACoS 95% con 2 orders -> Regla 4 -> INV-11.4 dice bajar bid
  11 Auto (close-match), CST que es un ASIN
  12 Broad, mismo CST que la fila 2 pero en otra campaña
  13 Spend > 0 con Clicks == 0 -> degenerado, división por cero
  14 Campaña con espacios extra y acentos en el nombre
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "bulk_sintetico.xlsx"

SHEET_STR = "SP Search Term Report"
SHEET_CAMPAIGNS = "Sponsored Products Campaigns"

# ── Orden exacto de las 27 columnas de la hoja STR ────────────────────
STR_COLS = [
    "Product",
    "Campaign ID",
    "Ad Group ID",
    "Keyword ID",
    "Product Targeting ID",
    "Campaign Name (Informational only)",
    "Ad Group Name (Informational only)",
    "Portfolio Name (Informational only)",
    "State",
    "Campaign State (Informational only)",
    "Bid",
    "Keyword Text",
    "Match Type",
    "Product Targeting Expression",
    "Resolved Product Targeting Expression (Informational only)",
    "Customer Search Term",
    "Impressions",
    "Clicks",
    "Click-through Rate",
    "Spend",
    "Sales",
    "Orders",
    "Units",
    "Conversion Rate",
    "ACOS",
    "CPC",
    "ROAS",
]

# ── 26 columnas de la hoja de campañas (INV-5.5) ──────────────────────
CAMP_COLS = [
    "Product",
    "Entity",
    "Operation",
    "Campaign ID",
    "Ad Group ID",
    "Portfolio ID",
    "Ad ID",
    "Keyword ID",
    "Product Targeting ID",
    "Campaign Name",
    "Ad Group Name",
    "Portfolio Name (Informational only)",
    "Start Date",
    "End Date",
    "Targeting Type",
    "State",
    "Daily Budget",
    "SKU",
    "ASIN",
    "Ad Group Default Bid",
    "Bid",
    "Keyword Text",
    "Match Type",
    "Bidding Strategy",
    "Placement",
    "Percentage",
]

# ── Campañas (IDs de 15 dígitos, inventados) ──────────────────────────
C1 = 132313349237695  # RANKING  — manual, keywords Exact
C2 = 214785693021447  # DISCOVERY — manual, Phrase/Broad
C3 = 398021456778312  # CONQUEST — manual, Product Targeting
C4 = 471209865533104  # DISCOVERY — auto
C5 = 556677889900112  # PROFIT   — nombre con espacios y acentos
C6 = 667788990011223  # DISCOVERY — campaña con 0 clicks

CAMPAIGNS = {
    C1: ("Nordic Sleep - B0TEST00001 - SP - KW - EXACT - Core", "RANKING", "Manual"),
    C2: ("Nordic Sleep - B0TEST00001 - SP - KW - PHRASE - Discovery", "DISCOVERY", "Manual"),
    C3: ("Nordic Sleep - B0TEST00002 - SP - PT - ASIN - Conquest", "CONQUEST", "Manual"),
    C4: ("Nordic Sleep - B0TEST00002 - SP - AUTO - Discovery", "DISCOVERY", "Auto"),
    # Espacios extra al principio/final + acentos (fila 14)
    C5: ("  Nordic Sleep — Crémá Nocturna  ", "PROFIT", "Manual"),
    C6: ("Nordic Sleep - B0TEST00003 - SP - KW - BROAD - Zero", "DISCOVERY", "Manual"),
}

# Ad Group IDs de 15 dígitos, uno por campaña
AG = {
    C1: 900000000000101,
    C2: 900000000000202,
    C3: 900000000000303,
    C4: 900000000000404,
    C5: 900000000000505,
    C6: 900000000000606,
}

# Keyword / Product Targeting IDs de 15 dígitos
KW_ID = 409151500000000  # base; se le suma el índice de fila
PT_ID = 715151500000000

# El CST de la fila 2, que también existe como keyword Exact enabled.
# Es el caso que dispara el guard INV-11.2.
CST_CON_EXACT_ACTIVA = "sleep sack winter"


def _fila_str(
    *,
    campaign: int,
    keyword_id: float | None,
    pt_id: float | None,
    keyword_text: str,
    match_type: str,
    pt_expression: str,
    cst: str,
    impressions: int,
    clicks: int,
    spend: float,
    sales: float,
    orders: int,
    bid: float = 0.75,
) -> dict:
    """Arma una fila del STR calculando las métricas derivadas."""
    nombre, portfolio, _ = CAMPAIGNS[campaign]
    ctr = (clicks / impressions * 100) if impressions else 0.0
    cvr = (orders / clicks * 100) if clicks else 0.0
    acos = (spend / sales * 100) if sales else 0.0
    cpc = (spend / clicks) if clicks else 0.0
    roas = (sales / spend) if spend else 0.0

    return {
        "Product": "Sponsored Products",
        "Campaign ID": campaign,
        "Ad Group ID": AG[campaign],
        "Keyword ID": keyword_id,
        "Product Targeting ID": pt_id,
        "Campaign Name (Informational only)": nombre,
        "Ad Group Name (Informational only)": f"AG - {portfolio.lower()}",
        "Portfolio Name (Informational only)": portfolio,
        "State": "enabled",
        "Campaign State (Informational only)": "enabled",
        "Bid": bid,
        "Keyword Text": keyword_text,
        "Match Type": match_type,
        "Product Targeting Expression": pt_expression,
        "Resolved Product Targeting Expression (Informational only)": pt_expression,
        "Customer Search Term": cst,
        "Impressions": impressions,
        "Clicks": clicks,
        "Click-through Rate": round(ctr, 4),
        "Spend": round(spend, 2),
        "Sales": round(sales, 2),
        "Orders": orders,
        "Units": orders,
        "Conversion Rate": round(cvr, 4),
        "ACOS": round(acos, 2),
        "CPC": round(cpc, 2),
        "ROAS": round(roas, 2),
    }


def _kw(idx: int) -> float:
    """Keyword ID de 15 dígitos para una fila de keyword."""
    return float(KW_ID + idx)


def _pt(idx: int) -> float:
    """Product Targeting ID de 15 dígitos para una fila de PT."""
    return float(PT_ID + idx)


def build_str_df() -> pd.DataFrame:
    """Las 14 filas del STR sintético."""
    filas = [
        # 1 — Exact en portfolio RANKING, 40 clicks sin órdenes.
        #     INV-11.1: viene de Exact, no es candidato a negativo.
        _fila_str(
            campaign=C1, keyword_id=_kw(1), pt_id=np.nan,
            keyword_text="nordic sleep bag", match_type="Exact",
            pt_expression="", cst="nordic sleep bag",
            impressions=2200, clicks=40, spend=28.40, sales=0.0, orders=0,
        ),
        # 2 — Phrase en DISCOVERY, 45 clicks sin órdenes: negativizable por
        #     INV-3... salvo que su CST existe como Exact enabled (INV-11.2).
        _fila_str(
            campaign=C2, keyword_id=_kw(2), pt_id=np.nan,
            keyword_text="sleep sack", match_type="Phrase",
            pt_expression="", cst=CST_CON_EXACT_ACTIVA,
            impressions=3100, clicks=45, spend=33.75, sales=0.0, orders=0,
        ),
        # 3 — Broad con 12 clicks: por debajo del threshold de INV-3.
        _fila_str(
            campaign=C2, keyword_id=_kw(3), pt_id=np.nan,
            keyword_text="baby sleep", match_type="Broad",
            pt_expression="", cst="baby sleeping bag 0 6 months",
            impressions=900, clicks=12, spend=8.40, sales=0.0, orders=0,
        ),
        # 4 — Product Targeting manual: Keyword ID vacío, PT ID lleno.
        #     INV-11.1 lo excluye de negativos.
        _fila_str(
            campaign=C3, keyword_id=np.nan, pt_id=_pt(4),
            keyword_text="", match_type="",
            pt_expression='asin="B0TEST00042"', cst="b0test00042",
            impressions=1500, clicks=30, spend=24.00, sales=0.0, orders=0,
        ),
        # 5 — Phrase en RANKING, 50 clicks sin órdenes.
        #     INV-11.3: default seguro, no se negativiza salvo desmarque.
        _fila_str(
            campaign=C1, keyword_id=_kw(5), pt_id=np.nan,
            keyword_text="merino swaddle", match_type="Phrase",
            pt_expression="", cst="merino wool swaddle blanket",
            impressions=4100, clicks=50, spend=41.00, sales=0.0, orders=0,
        ),
        # 6 — Harvest regla principal: orders>=3 AND ACoS<=25%.
        _fila_str(
            campaign=C2, keyword_id=_kw(6), pt_id=np.nan,
            keyword_text="sleep sack", match_type="Broad",
            pt_expression="", cst="organic cotton sleep sack",
            impressions=1800, clicks=20, spend=18.00, sales=120.00, orders=5,
        ),
        # 7 — Harvest por CVR alto: CVR 11.1% con 18 clicks (>=15).
        _fila_str(
            campaign=C2, keyword_id=_kw(7), pt_id=np.nan,
            keyword_text="sleep bag", match_type="Broad",
            pt_expression="", cst="toddler sleep bag 2 tog",
            impressions=1100, clicks=18, spend=15.30, sales=59.98, orders=2,
        ),
        # 8 — Harvest por volumen: orders>=5 con ACoS 140%.
        #     INV-4 dice explícitamente que esta regla NO tiene techo.
        _fila_str(
            campaign=C2, keyword_id=_kw(8), pt_id=np.nan,
            keyword_text="winter sleep sack", match_type="Phrase",
            pt_expression="", cst="winter sleep sack baby 12 months",
            impressions=5200, clicks=60, spend=252.00, sales=180.00, orders=6,
        ),
        # 9 — CTR bajo: 3000 impresiones, CTR 0.10% (< 0.18%), 0 órdenes.
        _fila_str(
            campaign=C2, keyword_id=_kw(9), pt_id=np.nan,
            keyword_text="blanket", match_type="Broad",
            pt_expression="", cst="picnic blanket waterproof",
            impressions=3000, clicks=3, spend=2.10, sales=0.0, orders=0,
        ),
        # 10 — ACoS 95% con 2 órdenes -> Regla 4.
        #      INV-11.4: la acción es bajar bid, NO negativizar.
        _fila_str(
            campaign=C2, keyword_id=_kw(10), pt_id=np.nan,
            keyword_text="sleep sack newborn", match_type="Phrase",
            pt_expression="", cst="sleep sack newborn 0 3 months",
            impressions=2400, clicks=30, spend=57.00, sales=60.00, orders=2,
        ),
        # 11 — Campaña Auto: en el bulk real los términos de Auto son filas de
        #      product targeting (close-match), no de keyword. El CST es un ASIN.
        _fila_str(
            campaign=C4, keyword_id=np.nan, pt_id=_pt(11),
            keyword_text="", match_type="",
            pt_expression="close-match", cst="b0test00099",
            impressions=1300, clicks=25, spend=19.75, sales=29.99, orders=1,
        ),
        # 12 — Mismo CST que la fila 2, en otra campaña.
        _fila_str(
            campaign=C5, keyword_id=_kw(12), pt_id=np.nan,
            keyword_text="sack", match_type="Broad",
            pt_expression="", cst=CST_CON_EXACT_ACTIVA,
            impressions=1400, clicks=22, spend=16.50, sales=29.99, orders=1,
        ),
        # 13 — Degenerado: gastó sin registrar clicks. División por cero.
        #      Única fila de C6, así que esa campaña queda con 0 clicks totales.
        _fila_str(
            campaign=C6, keyword_id=_kw(13), pt_id=np.nan,
            keyword_text="sleep", match_type="Broad",
            pt_expression="", cst="sleep aid adults",
            impressions=500, clicks=0, spend=3.50, sales=0.0, orders=0,
        ),
        # 14 — Campaña con espacios extra y acentos en el nombre.
        #      Match Type en minúscula a propósito: Amazon no es consistente.
        _fila_str(
            campaign=C5, keyword_id=_kw(14), pt_id=np.nan,
            keyword_text="crema nocturna", match_type="broad",
            pt_expression="", cst="crema nocturna bebé",
            impressions=800, clicks=15, spend=11.25, sales=45.00, orders=2,
        ),
    ]
    return pd.DataFrame(filas, columns=STR_COLS)


def _fila_camp(**kw) -> dict:
    """Fila de la hoja de campañas: arranca vacía y se sobreescribe."""
    base = {c: "" for c in CAMP_COLS}
    base["Product"] = "Sponsored Products"
    base["Operation"] = ""
    base["Ad Group ID"] = np.nan
    base["Keyword ID"] = np.nan
    base["Product Targeting ID"] = np.nan
    base.update(kw)
    return base


def build_campaigns_df() -> pd.DataFrame:
    """Hoja de campañas: 6 Campaign + 5 Keyword + 2 Product Ad."""
    filas = []

    # ── 6 filas Entity="Campaign" ────────────────────────────────────
    for cid, (nombre, portfolio, targeting) in CAMPAIGNS.items():
        filas.append(_fila_camp(
            Entity="Campaign",
            **{
                "Campaign ID": cid,
                "Campaign Name": nombre,
                "Portfolio Name (Informational only)": portfolio,
                "Targeting Type": targeting,
                "State": "enabled",
                "Daily Budget": 25.00,
                "Start Date": "20260801",
                "Bidding Strategy": "Dynamic bids - down only",
            },
        ))

    # ── 4 filas Entity="Keyword", Exact, enabled ─────────────────────
    # La primera tiene el mismo texto que el CST de la fila 2 del STR:
    # es la que activa el guard INV-11.2.
    exact_activas = [
        CST_CON_EXACT_ACTIVA,
        "  Merino Wool Swaddle  ",   # espacios + mayúsculas: se normaliza
        "organic cotton sleep sack",
        "nordic sleep bag",
    ]
    for i, texto in enumerate(exact_activas, start=1):
        filas.append(_fila_camp(
            Entity="Keyword",
            **{
                "Campaign ID": C1,
                "Ad Group ID": float(AG[C1]),
                "Keyword ID": float(KW_ID + 900 + i),
                "Campaign Name": CAMPAIGNS[C1][0],
                "Ad Group Name": "AG - ranking",
                "Portfolio Name (Informational only)": "RANKING",
                "State": "enabled",
                "Bid": 1.10,
                "Keyword Text": texto,
                "Match Type": "Exact",
            },
        ))

    # ── 1 fila Entity="Keyword", Exact, PAUSED -> NO activa el guard ──
    filas.append(_fila_camp(
        Entity="Keyword",
        **{
            "Campaign ID": C1,
            "Ad Group ID": float(AG[C1]),
            "Keyword ID": float(KW_ID + 999),
            "Campaign Name": CAMPAIGNS[C1][0],
            "Ad Group Name": "AG - ranking",
            "Portfolio Name (Informational only)": "RANKING",
            "State": "paused",
            "Bid": 0.90,
            "Keyword Text": "picnic blanket waterproof",
            "Match Type": "Exact",
        },
    ))

    # ── 2 filas Entity="Product Ad" ──────────────────────────────────
    for cid, asin, sku in ((C1, "B0TEST00001", "NS-SACK-001"),
                           (C3, "B0TEST00002", "NS-SACK-002")):
        filas.append(_fila_camp(
            Entity="Product Ad",
            **{
                "Campaign ID": cid,
                "Ad Group ID": float(AG[cid]),
                "Ad ID": float(880000000000000 + cid % 1000),
                "Campaign Name": CAMPAIGNS[cid][0],
                "Ad Group Name": "AG - ads",
                "Portfolio Name (Informational only)": CAMPAIGNS[cid][1],
                "State": "enabled",
                "SKU": sku,
                "ASIN": asin,
            },
        ))

    return pd.DataFrame(filas, columns=CAMP_COLS)


def main() -> None:
    df_str = build_str_df()
    df_camp = build_campaigns_df()

    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        df_str.to_excel(writer, sheet_name=SHEET_STR, index=False)
        df_camp.to_excel(writer, sheet_name=SHEET_CAMPAIGNS, index=False)

    print(f"OK -> {OUT}")
    print(f"  {SHEET_STR}: {len(df_str)} filas x {len(df_str.columns)} cols")
    print(f"  {SHEET_CAMPAIGNS}: {len(df_camp)} filas x {len(df_camp.columns)} cols")

    # Chequeo de dtypes al releer: es el punto del fixture.
    rel = pd.read_excel(OUT, sheet_name=SHEET_STR)
    print("  dtypes al releer la hoja STR:")
    for c in ("Campaign ID", "Ad Group ID", "Keyword ID", "Product Targeting ID"):
        print(f"    {c:<22} {rel[c].dtype}")


if __name__ == "__main__":
    main()
