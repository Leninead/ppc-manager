"""The last stored Search Term analysis of each Amazon Ads account, read for the app chat."""
from datetime import datetime, timezone

from core.ai_analysis.account_summaries import (
    AccountAnalysis,
    account_summaries_document,
    latest_account_analyses,
)
from core.ai_analysis.store import AiAnalysisStore, StoredAnalysis
from core.amazon_ads.report_provider import ProfileOption, account_labels


class _PostgrestFake:
    """PostgREST over ai_analyses and ads_profile_sync: eq/in filters, finished_at desc order, limit,
    and a select list projected like the server does, `alias:column->key` included."""

    def __init__(self, analyses, profiles=()):
        self.analyses = analyses
        self.profiles = list(profiles)
        self.reads = []

    def select(self, table, params):
        self.reads.append((table, dict(params)))
        if table == "ads_profile_sync":
            return [dict(row) for row in self.profiles if row["status"] != "inactive"]
        rows = [row for row in self.analyses if self._matches(row, params)]
        rows.sort(key=lambda row: (row["finished_at"], row["id"]), reverse=True)
        if "limit" in params:
            rows = rows[:int(params["limit"])]
        return [self._project(row, params["select"]) for row in rows]

    @staticmethod
    def _matches(row, params):
        for column in ("module", "status", "subject_id", "id"):
            if column not in params:
                continue
            operator, _, expected = params[column].partition(".")
            if operator == "eq" and str(row[column]) != expected:
                return False
            if operator == "in" and str(row[column]) not in expected.strip("()").split(","):
                return False
        return True

    @staticmethod
    def _project(row, select):
        projected = {}
        for field in select.split(","):
            alias, _, path = field.rpartition(":")
            column, _, key = path.partition("->")
            projected[alias or column] = row[column][key] if key else row[column]
        return projected


def _stored(analysis_id, subject_id, finished_at, situation="s", status="done", records=None):
    return {"id": analysis_id, "module": "str", "subject_id": subject_id, "status": status,
            "window_start": "2026-08-16", "window_end": "2026-09-14", "lang": "es",
            "params": {"target_acos": 30, "brand_terms": ["luna"]}, "finished_at": finished_at,
            "negative_records": records or [], "harvest_records": [], "records": [], "usage": {"tokens": 9},
            "result": {"negativos": [{"row_id": "N01"}], "synthesis": {"situation": situation}}}


def _profile_row(profile_id, cliente, country, currency="USD", account_type="seller", data_through="2026-09-14"):
    return {"profile_id": profile_id, "account_id": 1, "cliente": cliente, "account_name": cliente,
            "country_code": country, "currency_code": currency, "account_type": account_type,
            "timezone": "UTC", "status": "active", "data_from": None, "data_through": data_through,
            "refreshed_on": None, "last_success_at": None, "last_error": ""}


def test_one_read_gives_the_newest_analysis_of_each_account_with_its_synthesis_and_rows():
    rows = [{"Search Term": "brita filter"}]
    rest = _PostgrestFake([_stored(1, "111", "2026-09-10T10:00:00+00:00", "vieja"),
                           _stored(2, "111", "2026-09-14T10:00:00+00:00", "nueva", records=rows),
                           _stored(3, "222", "2026-09-12T10:00:00+00:00", "otra cuenta"),
                           _stored(4, "222", "2026-09-15T10:00:00+00:00", "falló", status="failed")])

    latest = AiAnalysisStore(rest).latest_by_subject("str", ["222", "111", "333"])

    assert [(analysis.subject_id, analysis.id) for analysis in latest] == [("222", 3), ("111", 2)]
    assert latest[1].result == {"synthesis": {"situation": "nueva"}}
    assert (latest[1].params, latest[1].window_end.isoformat(), latest[1].negative_records) == (
        {"target_acos": 30, "brand_terms": ["luna"]}, "2026-09-14", rows)
    assert [params["select"] for _, params in rest.reads] == [
        "id,module,subject_id,window_start,window_end,lang,params,finished_at,synthesis:result->synthesis",
        "id,negative_records,harvest_records,records"]


def test_an_account_whose_newest_analysis_did_not_fit_the_first_read_is_read_on_its_own():
    busy = [_stored(index, "111", f"2026-09-{index:02d}T10:00:00+00:00") for index in range(1, 10)]
    quiet = _stored(50, "222", "2026-08-01T10:00:00+00:00", "la cuenta tranquila")
    rest = _PostgrestFake(busy + [quiet])

    latest = AiAnalysisStore(rest).latest_by_subject("str", ["111", "222"])

    assert [(analysis.subject_id, analysis.id) for analysis in latest] == [("111", 9), ("222", 50)]
    assert rest.reads[1][1]["subject_id"] == "eq.222"


def test_no_accounts_means_no_read():
    rest = _PostgrestFake([])

    assert AiAnalysisStore(rest).latest_by_subject("str", []) == []
    assert rest.reads == []


def test_accounts_without_data_are_not_read_and_the_synthesis_carries_the_term_behind_each_row_id():
    beta = dict(_stored(7, "222", "2026-09-14T10:00:00+00:00", "Negativizar N01 esta semana",
                        records=[{"Search Term": "brita filter"}]))
    acme = _stored(8, "111", "2026-09-14T11:00:00+00:00", "síntesis de Acme")
    rest = _PostgrestFake([beta, acme],
                          [_profile_row("222", "Beta", "MX", currency="MXN"), _profile_row("111", "Acme", "US"),
                           _profile_row("333", "Nueva", "US", data_through=None)])

    accounts = latest_account_analyses(rest)
    document = account_summaries_document(accounts)

    assert [(account.profile.profile_id, account.label) for account in accounts] == [
        ("111", "Acme · US"), ("222", "Beta · MX")]
    assert rest.reads[1][1]["subject_id"] == "in.(111,222)"
    assert document["title"] == "Últimos análisis de Search Terms guardados por cuenta (2 de 2)"
    blocks = document["content"].split("\n\n")
    assert blocks[0].startswith("Cuenta: Acme · US\nPeríodo: 16/08/2026 a 14/09/2026")
    assert "Situación: Negativizar «brita filter» esta semana" in blocks[1]


def test_a_client_with_two_profiles_in_one_country_keeps_the_account_type_even_when_one_is_left_out():
    profiles = [ProfileOption.from_row(_profile_row("1", "Luna", "US", account_type="seller")),
                ProfileOption.from_row(_profile_row("2", "Luna", "US", account_type="vendor")),
                ProfileOption.from_row(_profile_row("3", "Luna", "MX"))]

    assert account_labels(profiles) == {"1": "Luna · US · seller", "2": "Luna · US · vendor", "3": "Luna · MX"}


def _account(profile_id, label, finished_hour, situation):
    profile = ProfileOption.from_row(_profile_row(profile_id, label, "US"))
    analysis = StoredAnalysis.from_row({**_stored(int(profile_id), profile_id, "", situation),
                                        "finished_at": datetime(2026, 9, 15, finished_hour,
                                                                tzinfo=timezone.utc).isoformat()})
    return AccountAnalysis(profile, label, analysis)


def test_the_newest_analyses_fill_the_budget_and_the_accounts_left_out_are_named():
    accounts = [_account("1", "Vieja", 9, "a" * 400), _account("2", "Nueva", 12, "b" * 400),
                _account("3", "Media", 10, "c" * 400)]

    document = account_summaries_document(accounts, max_chars=1_500)

    assert document["title"] == "Últimos análisis de Search Terms guardados por cuenta (2 de 3)"
    blocks = document["content"].split("\n\n")
    assert [block.splitlines()[0] for block in blocks[:2]] == ["Cuenta: Nueva", "Cuenta: Media"]
    assert blocks[-1] == "No entraron 1 cuentas más con análisis guardado: Vieja."


def test_without_accounts_there_is_no_document():
    assert account_summaries_document([]) is None
