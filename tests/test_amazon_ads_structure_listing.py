"""Whether an account's SP listing can be read: when each family was listed, or why not. No network."""
import csv
import io
from datetime import date, datetime, timezone

import pytest
import requests

from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.structure_listing import family_listing, read_keyword_listing
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    CAMPAIGN,
    KEYWORD,
    ROW_COLUMNS,
    StructureProvider,
)

DAY = date(2026, 9, 28)
LISTED = "2026-09-28T06:00:00+00:00"
FINISHED = "2026-09-28T07:30:00+00:00"
PROFILE = ProfileOption.from_row({"profile_id": "p-1", "cliente": "Luna", "country_code": "US",
                                  "currency_code": "USD", "account_type": "seller"})


def _row(entity, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "campaign_id": "1", "state": "ENABLED", "metrics_known": "f",
                "listed_at": LISTED})
    row.update(values)
    return row


CAMPAIGN_ROW = _row(CAMPAIGN, entity_id="1")
AD_GROUP_ROW = _row(AD_GROUP, ad_group_id="10", entity_id="10")
KEYWORD_ROW = _row(KEYWORD, ad_group_id="10", entity_id="k1", target_text="luna pajamas", match_type="EXACT")


def _job(kind, *, warning="") -> dict:
    return {"id": 7, "integration_slug": "amazon_ads", "job_kind": kind, "trigger": "scheduled_daily",
            "external_account_id": "p-1", "status": "completed", "warning": warning, "finished_at": FINISHED,
            "created_at": FINISHED}


class _FakeRest:
    def __init__(self, rows=(), jobs=(), *, structure_fails_with=None, jobs_fail_with=None):
        self._rows, self._jobs = list(rows), list(jobs)
        self._structure_fails_with, self._jobs_fail_with = structure_fails_with, jobs_fail_with
        self.job_kinds_read: list[str] = []

    def rpc_csv(self, name, args, *, timeout_s=8):
        assert name == "sp_structure_between"
        if self._structure_fails_with is not None:
            raise self._structure_fails_with
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(ROW_COLUMNS))
        writer.writeheader()
        writer.writerows(self._rows)
        return buffer.getvalue().encode("utf-8")

    def select(self, table, params):
        assert table == "integration_sync_jobs"
        if self._jobs_fail_with is not None:
            raise self._jobs_fail_with
        kind = params["job_kind"].removeprefix("eq.")
        self.job_kinds_read.append(kind)
        return [dict(job) for job in self._jobs if job["job_kind"] == kind][:1]


def _http_error(status: int, body: bytes) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response._content = body
    return requests.HTTPError(response=response)


def _structure(rest):
    return StructureProvider(rest).sp_structure(PROFILE, DAY, DAY, entities=(CAMPAIGN, AD_GROUP, KEYWORD))


def test_a_family_with_rows_was_listed_at_its_newest_row_and_asks_no_job():
    rest = _FakeRest([CAMPAIGN_ROW])

    listing = family_listing(rest, _structure(rest), CAMPAIGN)

    assert listing.listed_at == datetime(2026, 9, 28, 6, tzinfo=timezone.utc)
    assert rest.job_kinds_read == []


def test_a_family_without_rows_was_listed_when_its_listing_job_completed():
    rest = _FakeRest([CAMPAIGN_ROW], [_job("sp_targets")])

    listing = family_listing(rest, _structure(rest), KEYWORD)

    assert (listing.listed_at, listing.refusal) == (datetime(2026, 9, 28, 7, 30, tzinfo=timezone.utc), "")
    assert rest.job_kinds_read == ["sp_targets"]


def test_a_listing_amazon_refused_completes_with_its_warning_and_no_listing_time():
    rest = _FakeRest([CAMPAIGN_ROW], [_job("sp_targets", warning="sin permiso para leer keywords y targets")])

    listing = family_listing(rest, _structure(rest), KEYWORD)

    assert (listing.listed_at, listing.refusal) == (None, "sin permiso para leer keywords y targets")


def test_a_family_never_listed_has_no_time_and_no_refusal():
    rest = _FakeRest([CAMPAIGN_ROW])

    listing = family_listing(rest, _structure(rest), AD_GROUP)

    assert (listing.listed_at, listing.refusal) == (None, "")
    assert rest.job_kinds_read == ["sp_ad_groups"]


def test_a_failed_job_lookup_is_a_read_error():
    rest = _FakeRest([CAMPAIGN_ROW], jobs_fail_with=requests.ConnectionError("rest-gateway down"))

    with pytest.raises(ReportReadError):
        family_listing(rest, _structure(rest), KEYWORD)


def test_the_listing_is_known_with_its_rows_once_campaigns_and_keywords_were_listed():
    listing = read_keyword_listing(_FakeRest([CAMPAIGN_ROW, AD_GROUP_ROW, KEYWORD_ROW]), PROFILE, DAY)

    assert listing.known
    assert list(listing.rows["entity"]) == [CAMPAIGN, AD_GROUP, KEYWORD]
    assert listing.listed_at == datetime(2026, 9, 28, 6, tzinfo=timezone.utc)
    assert listing.ad_groups_listed


def test_ad_groups_never_listed_leave_their_states_unknown_but_the_keywords_known():
    listing = read_keyword_listing(_FakeRest([CAMPAIGN_ROW, KEYWORD_ROW]), PROFILE, DAY)

    assert listing.known
    assert not listing.ad_groups_listed


def test_keywords_never_listed_make_the_listing_unknown():
    listing = read_keyword_listing(_FakeRest([CAMPAIGN_ROW]), PROFILE, DAY)

    assert not listing.known
    assert (listing.rows, listing.refusal) == (None, "")


def test_an_unknown_listing_carries_amazons_refusal():
    rest = _FakeRest([CAMPAIGN_ROW], [_job("sp_targets", warning="sin permiso para leer keywords y targets")])

    listing = read_keyword_listing(rest, PROFILE, DAY)

    assert not listing.known
    assert listing.refusal == "sin permiso para leer keywords y targets"


def test_without_migration_018_the_listing_is_unknown_not_an_error():
    failure = _http_error(404, b'{"code":"PGRST202","message":"Could not find the function"}')

    listing = read_keyword_listing(_FakeRest(structure_fails_with=failure), PROFILE, DAY)

    assert not listing.known


def test_a_structure_read_that_fails_is_a_read_error():
    with pytest.raises(ReportReadError):
        read_keyword_listing(_FakeRest(structure_fails_with=requests.ConnectionError("down")), PROFILE, DAY)
