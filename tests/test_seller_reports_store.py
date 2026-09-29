"""core/seller_reports/store: what goes to the Seller Central functions of 023 and what comes back.

ZERO network: PostgREST is a fake session behind the real transport.
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import numpy as np
import pytest
import requests

from core.integrations.store import _Rest
from core.seller_reports import store as seller_store
from core.seller_reports.columns import BRAND_VIEW, SALES_TRAFFIC_DAILY
from core.seller_reports.periods import sqp_week
from core.seller_reports.store import SellerAccount, SellerReportRejected, SellerReportStore

ACCOUNT_ROW = {"id": 4, "ads_entity_id": "A2EXAMPLE0SELL", "marketplace_id": "A1AM78C64UM0Y8", "country_code": "MX",
               "account_name": "Dermaglós", "selling_partner_id": None, "selling_partner_id_source": "",
               "created_by": "ana", "updated_by": "ana", "created_at": "2026-09-29T22:00:00+00:00",
               "updated_at": "2026-09-29T22:00:00+00:00"}


class _FakeSession:
    def __init__(self, *responses: requests.Response):
        self.posts: list[dict] = []
        self._responses = list(responses)

    def post(self, url, json=None, params=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        return self._responses.pop(0)


def _response(status: int, body) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return response


def _store(*responses: requests.Response) -> tuple[SellerReportStore, _FakeSession]:
    session = _FakeSession(*responses)
    return SellerReportStore(_Rest("http://rest-gateway", "jwt", session=session)), session


def _change(**overrides) -> dict:
    change = {"period_start": "2026-09-01", "period_end": "2026-09-01", "brand_or_asin": "", "status": "inserted",
              "row_count": 1, "existing_source": None, "existing_row_count": None, "existing_loaded_by": None,
              "existing_loaded_at": None, "existing_file_name": None, "load_id": None}
    return change | overrides


def test_an_upload_sends_its_rows_and_options_to_the_app_function_without_a_source():
    store, session = _store(_response(200, [_change(), _change(period_start="2026-09-02",
                                                              period_end="2026-09-02")]))

    store.upload_sales_traffic_daily(
        3, [{"day": date(2026, 9, 1), "units_ordered": 12.0, "ordered_product_sales": Decimal("199.90"),
             "sessions": float("nan"), "buy_box_percentage": 97.5, "currency_code": "MXN"},
            {"day": datetime(2026, 9, 2), "units_ordered": np.int64(7), "sessions": np.float64(110.0)}],
        preview=True, loaded_by="ana", file_name="BusinessReport.csv")

    call = session.posts[0]
    assert call["url"] == "http://rest-gateway/rest/v1/rpc/upload_seller_sales_traffic_daily"
    assert call["json"] == {
        "p_account_id": 3,
        "p_rows": [{"day": "2026-09-01", "units_ordered": 12, "ordered_product_sales": "199.90", "sessions": None,
                    "buy_box_percentage": 97.5, "currency_code": "MXN"},
                   {"day": "2026-09-02T00:00:00", "units_ordered": 7, "sessions": 110}],
        "p_replace_api_data": False, "p_preview": True, "p_loaded_by": "ana", "p_file_name": "BusinessReport.csv"}
    assert call["timeout"] == 60


def test_the_worker_writes_as_sp_api():
    store, session = _store(_response(200, [_change(status="replaced", existing_source="manual", load_id=9)]))

    result = store.save_sales_traffic_daily(3, [{"day": "2026-09-02", "units_ordered": 13}], loaded_by="spapi")

    call = session.posts[0]
    assert call["url"] == "http://rest-gateway/rest/v1/rpc/save_seller_sales_traffic_daily"
    assert call["json"]["p_source"] == "sp_api"
    assert call["json"]["p_loaded_by"] == "spapi"
    assert result.load_id == 9


def test_a_by_child_upload_sends_its_exact_range():
    store, session = _store(_response(200, [_change(period_end="2026-09-14", row_count=2)]))

    store.upload_sales_traffic_by_asin(3, date(2026, 9, 1), date(2026, 9, 14),
                                       [{"child_asin": "B0CYLMJJJC", "title": "Crema, 1,76 oz", "units_ordered": 141}])

    call = session.posts[0]
    assert call["url"] == "http://rest-gateway/rest/v1/rpc/upload_seller_sales_traffic_by_asin"
    assert (call["json"]["p_range_start"], call["json"]["p_range_end"]) == ("2026-09-01", "2026-09-14")
    assert call["json"]["p_rows"] == [{"child_asin": "B0CYLMJJJC", "title": "Crema, 1,76 oz", "units_ordered": 141}]


def test_a_sqp_upload_sends_its_view_brand_and_amazon_week():
    store, session = _store(_response(200, [_change(period_start="2026-09-13", period_end="2026-09-19",
                                                    brand_or_asin="Mott & Bow")]))

    result = store.upload_search_query_performance(3, BRAND_VIEW, "Mott & Bow", sqp_week(date(2026, 9, 16)),
                                                   [{"search_query": "t shirt men", "own_click_count": 30}])

    args = session.posts[0]["json"]
    assert session.posts[0]["url"] == "http://rest-gateway/rest/v1/rpc/upload_seller_search_query_performance"
    assert (args["p_view"], args["p_brand_or_asin"]) == ("brand", "Mott & Bow")
    assert (args["p_period_type"], args["p_period_start"]) == ("week", "2026-09-13")
    assert result.changes[0].brand_or_asin == "Mott & Bow"


def test_the_answer_is_one_change_per_period_with_what_was_there_before():
    store, _ = _store(_response(200, [
        _change(status="unchanged", existing_source="manual", existing_row_count=1, existing_loaded_by="ana",
                existing_loaded_at="2026-09-29T22:08:36.611+00:00", existing_file_name="BusinessReport.csv"),
        _change(period_start="2026-09-02", period_end="2026-09-02", status="conflict", existing_source="sp_api",
                existing_row_count=1, existing_loaded_by="spapi", existing_loaded_at="2026-09-29T06:00:00+00:00")]))

    result = store.upload_sales_traffic_daily(3, [{"day": "2026-09-01"}, {"day": "2026-09-02"}])

    unchanged, conflict = result.changes
    assert (unchanged.period_start, unchanged.status, unchanged.existing_loaded_by) == (
        date(2026, 9, 1), "unchanged", "ana")
    assert unchanged.existing_loaded_at == datetime(2026, 9, 29, 22, 8, 36, 611000, tzinfo=timezone.utc)
    assert result.conflicts == (conflict,)
    assert result.load_id is None


def test_the_load_id_is_the_one_the_write_created():
    store, _ = _store(_response(200, [_change(status="unchanged"), _change(period_start="2026-09-02",
                                                                          status="replaced", load_id=11)]))

    assert store.upload_sales_traffic_daily(3, [{"day": "2026-09-01"}, {"day": "2026-09-02"}]).load_id == 11


def test_a_refusal_of_the_database_is_a_rejection_with_its_code_and_detail():
    store, _ = _store(_response(400, {"code": "P0001", "message": "seller_report.week_not_on_sunday",
                                      "details": "2026-09-14", "hint": None}))

    with pytest.raises(SellerReportRejected) as refused:
        store.upload_search_query_performance(3, BRAND_VIEW, "Mott & Bow", sqp_week(date(2026, 9, 16)),
                                              [{"search_query": "t shirt"}])

    assert (refused.value.code, refused.value.detail) == ("week_not_on_sunday", "2026-09-14")


def test_any_other_failure_stays_an_http_error():
    store, _ = _store(_response(403, {"code": "42501",
                                      "message": "permission denied for function save_seller_sales_traffic_daily"}))

    with pytest.raises(requests.HTTPError):
        store.save_sales_traffic_daily(3, [{"day": "2026-09-02"}])


def test_a_value_the_database_cannot_read_fails_before_anything_is_sent():
    store, session = _store()

    with pytest.raises(TypeError, match="cannot carry a object"):
        store.upload_sales_traffic_daily(3, [{"day": "2026-09-01", "units_ordered": object()}])

    assert session.posts == []


def test_the_account_of_a_profile_comes_back_whole():
    store, session = _store(_response(200, ACCOUNT_ROW))

    account = store.account_for_ads_profile("279177258676903", actor="ana")

    assert session.posts[0]["url"] == "http://rest-gateway/rest/v1/rpc/seller_account_for_ads_profile"
    assert session.posts[0]["json"] == {"p_profile_id": "279177258676903", "p_actor": "ana"}
    assert account == SellerAccount(id=4, ads_entity_id="A2EXAMPLE0SELL", marketplace_id="A1AM78C64UM0Y8",
                                    country_code="MX", account_name="Dermaglós", selling_partner_id=None,
                                    selling_partner_id_source="")


def test_the_seller_id_is_set_by_hand_or_cleared_with_none():
    store, session = _store(_response(200, ACCOUNT_ROW | {"selling_partner_id": "A2EXAMPLE0SELL",
                                                          "selling_partner_id_source": "manual"}),
                            _response(200, ACCOUNT_ROW))

    assert store.set_selling_partner_id(4, "A2EXAMPLE0SELL", actor="admin").selling_partner_id_source == "manual"
    assert store.set_selling_partner_id(4, None, actor="admin").selling_partner_id is None
    assert session.posts[1]["json"] == {"p_account_id": 4, "p_selling_partner_id": None, "p_actor": "admin"}


def test_deleting_an_account_says_whether_it_was_there():
    store, session = _store(_response(200, True), _response(200, False))

    assert store.delete_account(4) is True
    assert store.delete_account(4) is False
    assert session.posts[0]["url"] == "http://rest-gateway/rest/v1/rpc/delete_seller_account"


def test_delete_and_undo_send_their_arguments_and_read_the_same_answer():
    store, session = _store(_response(200, [_change(status="deleted", row_count=0, existing_source="sp_api",
                                                    load_id=12)]),
                            _response(200, [_change(status="restored", existing_source=None, load_id=12)]))

    deleted = store.delete_periods(3, SALES_TRAFFIC_DAILY, "", date(2026, 9, 1), date(2026, 9, 30),
                                   replace_api_data=True, deleted_by="ana")
    restored = store.revert_load(deleted.load_id, reverted_by="ana")

    assert session.posts[0]["json"] == {"p_account_id": 3, "p_dataset": "sales_traffic_daily", "p_brand_or_asin": "",
                                        "p_first_day": "2026-09-01", "p_last_day": "2026-09-30",
                                        "p_replace_api_data": True, "p_preview": False, "p_deleted_by": "ana"}
    assert session.posts[1]["url"] == "http://rest-gateway/rest/v1/rpc/revert_seller_report_load"
    assert session.posts[1]["json"] == {"p_load_id": 12, "p_preview": False, "p_reverted_by": "ana"}
    assert [change.status for change in restored.changes] == ["restored"]


def test_an_undo_already_done_answers_nothing():
    store, _ = _store(_response(200, []))

    result = store.revert_load(12)

    assert result.changes == () and result.load_id is None


def test_without_a_database_there_is_no_store(monkeypatch):
    monkeypatch.setattr(seller_store, "_rest_credentials", lambda: None)
    assert seller_store.open_seller_report_store() is None

    monkeypatch.setattr(seller_store, "_rest_credentials", lambda: ("http://rest-gateway", "jwt"))
    assert isinstance(seller_store.open_seller_report_store(), SellerReportStore)
