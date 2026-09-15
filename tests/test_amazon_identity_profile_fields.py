"""Discovery keeps each profile's timezone and currency, which the search term sync plans days and money with."""
from __future__ import annotations

from core.integrations import amazon_identity
from core.integrations.amazon_identity import AdsProfile, _parse_profile, group_accounts


def _raw_profile(**overrides) -> dict:
    raw = {
        "profileId": 1234567890,
        "countryCode": "mx",
        "currencyCode": "mxn",
        "timezone": "America/Los_Angeles",
        "accountInfo": {
            "marketplaceStringId": "A1AM78C64UM0Y8",
            "id": "ENTITY123",
            "type": "Seller",
            "name": "Demo Seller",
        },
    }
    raw.update(overrides)
    return raw


def test_parse_profile_reads_timezone_and_upper_cases_currency():
    profile = _parse_profile(_raw_profile(), "NA", amazon_identity.ACCESS_EDIT)

    assert profile.timezone == "America/Los_Angeles"
    assert profile.currency_code == "MXN"
    assert profile.country_code == "MX"
    assert profile.account_type == "seller"


def test_parse_profile_without_timezone_or_currency_defaults_to_empty():
    raw = _raw_profile()
    del raw["timezone"]
    raw["currencyCode"] = None

    profile = _parse_profile(raw, "NA", amazon_identity.ACCESS_VIEW)

    assert profile.timezone == ""
    assert profile.currency_code == ""


def test_as_row_carries_timezone_and_currency():
    row = _parse_profile(_raw_profile(), "NA", amazon_identity.ACCESS_EDIT).as_row()

    assert row == {
        "profile_id": "1234567890",
        "country_code": "MX",
        "marketplace_id": "A1AM78C64UM0Y8",
        "access": "edit",
        "timezone": "America/Los_Angeles",
        "currency_code": "MXN",
    }


def test_profiles_built_without_the_new_fields_still_work():
    profile = AdsProfile(profile_id="1", region="EU", country_code="UK", marketplace_id="M", account_type="vendor",
                         account_name="Demo Vendor", entity_id="E", access="view")

    assert profile.as_row()["timezone"] == ""
    assert profile.as_row()["currency_code"] == ""


def test_grouped_accounts_store_the_fields_in_profiles_json():
    us = _parse_profile(_raw_profile(profileId=1, countryCode="US", currencyCode="USD"), "NA", "edit")
    mx = _parse_profile(_raw_profile(profileId=2), "NA", "edit")

    (account,) = group_accounts((us, mx))

    assert [(row["country_code"], row["currency_code"], row["timezone"]) for row in account.profiles] == [
        ("US", "USD", "America/Los_Angeles"),
        ("MX", "MXN", "America/Los_Angeles"),
    ]
