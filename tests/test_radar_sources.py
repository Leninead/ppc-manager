"""The Radar Amazon source catalog is valid and keeps out the feeds the discovery found broken."""
from core.radar.sources import SOURCES, validate_sources


def test_catalog_is_valid():
    assert validate_sources() == []


def test_the_official_source_is_the_ads_api_feed():
    official = [source for source in SOURCES if source["is_official"]]
    assert [source["id"] for source in official] == ["amazon-ads-api-release-notes"]


def test_my_amazon_guy_blog_keeps_the_trailing_slash():
    # Without it the site answers 301 to an HTML page, not the feed.
    blog = next(source for source in SOURCES if source["id"] == "my-amazon-guy-blog")
    assert blog["feed_url"] == "https://myamazonguy.com/feed/"


def test_no_linkedin_and_no_broken_sources():
    urls = " ".join(source["feed_url"] + source["fallback_link"] for source in SOURCES)
    assert "linkedin" not in urls.lower()
    assert "betterams.com" not in urls and "bobsledmarketing.com" not in urls


def test_validate_flags_duplicates_bad_kind_and_plain_http():
    good = dict(SOURCES[0])
    errors = validate_sources((good, dict(good), {**good, "id": "x", "kind": "tiktok"},
                               {**good, "id": "y", "feed_url": "http://example.com/feed"},
                               {"id": "z"}))
    assert any("id duplicado" in error for error in errors)
    assert any("kind" in error for error in errors)
    assert any("no es https" in error for error in errors)
    assert any("faltan campos" in error for error in errors)
