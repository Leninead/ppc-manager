"""The account directory a conversation opens with: what the chat read list_accounts and list_analyses for."""
from datetime import date

from core.ai_analysis.store import SavedWindow
from core.amazon_ads.report_provider import ProfileOption
from core.chat import account_directory


def _profile(profile_id: str, client: str, country: str, currency: str, data_through=date(2026, 9, 21)):
    return ProfileOption(profile_id=profile_id, account_id=1, cliente=client, account_name=client,
                         country_code=country, currency_code=currency, account_type="seller", timezone="",
                         status="active", data_from=None, data_through=data_through, refreshed_on=None,
                         last_success_at=None, last_error="")


PROFILES = [_profile("2", "wamery", "MX", "MXN"), _profile("1", "dermaglos", "US", "USD"),
            _profile("3", "nueva", "US", "USD", data_through=None)]
SAVED = [SavedWindow("str", "1", date(2026, 9, 16), date(2026, 9, 22)),
         SavedWindow("bulk_campaigns", "1", date(2026, 9, 15), date(2026, 9, 21))]


def test_one_line_per_account_with_data_by_name_with_its_saved_analyses():
    lines = account_directory.directory_lines(PROFILES, SAVED)

    assert lines == [
        "dermaglos · US | 1 | USD | datos hasta 2026-09-21 | análisis: bulk_campaigns 2026-09-15 a 2026-09-21, "
        "str 2026-09-16 a 2026-09-22",
        "wamery · MX | 2 | MXN | datos hasta 2026-09-21 | análisis: ninguno"]


def test_the_document_says_what_each_field_is_and_that_the_list_is_complete(monkeypatch):
    monkeypatch.setattr(account_directory, "_read_directory", lambda: ["dermaglos · US | 1 | USD"])

    document = account_directory.directory_document()

    assert document["title"] == account_directory.TITLE
    assert document["content"].splitlines() == [account_directory.HEADER, "dermaglos · US | 1 | USD"]
    assert "list_accounts" in account_directory.HEADER


def test_without_accounts_to_read_the_conversation_opens_without_a_directory(monkeypatch):
    monkeypatch.setattr(account_directory, "_read_directory", lambda: [])

    assert account_directory.directory_document() is None
