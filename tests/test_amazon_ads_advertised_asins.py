"""The ASINs each SP ad group advertises, as the page, the analysis worker and the MCP read them."""
import pytest
import requests

from core.amazon_ads.ad_entities import PRODUCT_ADS_TABLE
from core.amazon_ads.advertised_asins import load_ad_group_asins
from core.amazon_ads.report_provider import ReportProvider, ReportReadError


class _FakeRest:
    def __init__(self, rows=(), error=None):
        self.rows = list(rows)
        self.error = error
        self.selects = []

    def select(self, table, params):
        self.selects.append((table, params))
        if self.error is not None:
            raise self.error
        return list(self.rows)


def test_every_asin_an_ad_group_advertised_is_kept_under_that_ad_group():
    rest = _FakeRest([{"ad_group_id": "21", "asin": "b0demo0001"}, {"ad_group_id": "21", "asin": "B0DEMO0002"},
                      {"ad_group_id": "22", "asin": "B0DEMO0001"}, {"ad_group_id": "", "asin": "B0DEMO0003"}])

    mapping = load_ad_group_asins(rest, "555")

    assert mapping == {"21": frozenset({"B0DEMO0001", "B0DEMO0002"}), "22": frozenset({"B0DEMO0001"})}
    [(table, params)] = rest.selects
    assert table == PRODUCT_ADS_TABLE
    assert (params["profile_id"], params["asin"]) == ("eq.555", "neq.")


def test_a_read_that_fails_reaches_the_page_as_a_report_read_error():
    provider = ReportProvider(_FakeRest(error=requests.ConnectionError("gateway down")))

    with pytest.raises(ReportReadError):
        provider.advertised_asins("555")
