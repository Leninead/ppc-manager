"""Where each ASIN's search terms were attributed from, and in how many campaigns the ASIN itself is advertised.

A term takes the ASIN of its ad group when the group advertises only one, or the ASIN in its campaign's name
(core/amazon_ads/advertised_asins.py). The second way can hand a whole product family to one ASIN, so each ASIN says
which way carried most of its spend, and whether it has product ads of its own.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from core.amazon_ads.advertised_asins import FROM_AD_GROUP, FROM_CAMPAIGN_NAME, SEVERAL_ASINS, WITHOUT_ASIN
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.structure_provider import CAMPAIGN, PRODUCT_AD, StructureProvider
from core.ppc_insights.asin_health import FROM_FILE

ATTRIBUTION_LABELS = {FROM_AD_GROUP: "single_asin_ad_group", FROM_CAMPAIGN_NAME: "campaign_name",
                      FROM_FILE: "advertised_asin"}
UNATTRIBUTED_ORIGINS = (SEVERAL_ASINS, WITHOUT_ASIN)
ATTRIBUTION_NOTE = ("attributed_by dice de dónde salió la mayor parte del gasto del ASIN: single_asin_ad_group, de ad "
                    "groups que anuncian sólo ese ASIN; campaign_name, del ASIN escrito en el nombre de la campaña, que "
                    "puede sumar a toda una familia de productos. advertised_in cuenta las campañas donde el ASIN tiene "
                    "un product ad propio y cuántas corren (el anuncio y su campaña habilitados). "
                    "unattributed_spend y unattributed_sales, en totals, son lo que no se pudo atribuir a ningún ASIN.")


def attribution_by_asin(asins: pd.Series, origins: pd.Series, spend: pd.Series) -> dict[str, str]:
    """ASIN -> the way most of its spend was attributed; ties go to the ad group, the narrower way."""
    attributed = pd.DataFrame({"asin": asins, "origin": origins, "spend": spend})[asins.notna()]
    if attributed.empty:
        return {}
    by_origin = attributed.groupby(["asin", "origin"])["spend"].sum().reset_index()
    by_origin["narrower"] = by_origin["origin"].eq(FROM_AD_GROUP)
    top = by_origin.sort_values(["asin", "spend", "narrower"], ascending=[True, False, False]).drop_duplicates("asin")
    return {str(asin): ATTRIBUTION_LABELS.get(origin, str(origin)) for asin, origin in zip(top["asin"], top["origin"])}


def advertised_in(rest, profile: ProfileOption, start: date, end: date) -> dict[str, dict] | None:
    """ASIN -> in how many campaigns it has a product ad, and in how many that ad and its campaign are enabled.

    None when the product ads were never listed, or could not be read.
    """
    try:
        structure = StructureProvider(rest).sp_structure(profile, start, end, entities=(CAMPAIGN, PRODUCT_AD))
    except ReportReadError:
        return None
    if structure is None:
        return None
    rows = structure.rows
    ads = rows[rows["entity"].eq(PRODUCT_AD) & rows["asin"].ne("")]
    if ads.empty:
        return None
    campaign_states = dict(zip(rows.loc[rows["entity"].eq(CAMPAIGN), "campaign_id"],
                               rows.loc[rows["entity"].eq(CAMPAIGN), "state"].str.upper()))
    runs = ads["state"].str.upper().eq("ENABLED") & ads["campaign_id"].map(campaign_states).eq("ENABLED")
    counted = ads.assign(asin=ads["asin"].str.upper(), runs=runs)
    return {asin: {"campaigns": int(group["campaign_id"].nunique()),
                   "running_campaigns": int(group.loc[group["runs"], "campaign_id"].nunique())}
            for asin, group in counted.groupby("asin")}
