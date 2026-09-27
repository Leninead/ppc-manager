"""The feeds Radar Amazon reads. Catalog only, no I/O.

Every feed_url answered 200 with a parseable feed in the 2026-09-25 discovery. Left out on purpose: BetterAMS'
site (does not connect), Bobsled's blog (no feed) and a Kevin King YouTube channel that could not be confirmed
as his. Quiet feeds stay in: the 7-day window drops them on their own.

`fallback_link` is where an item without its own <link> points, so it always leads somewhere real.
"""
from __future__ import annotations

KINDS: tuple[str, ...] = ("youtube", "podcast", "blog", "official")
REQUIRED_FIELDS: tuple[str, ...] = ("id", "name", "person", "kind", "feed_url", "fallback_link", "is_official")

_YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
_YOUTUBE_CHANNEL = "https://www.youtube.com/channel/{}"


def _youtube(source_id: str, name: str, person: str, channel_id: str) -> dict:
    return {"id": source_id, "name": name, "person": person, "kind": "youtube",
            "feed_url": _YOUTUBE_FEED.format(channel_id), "fallback_link": _YOUTUBE_CHANNEL.format(channel_id),
            "is_official": False}


def _feed(source_id: str, name: str, person: str, kind: str, feed_url: str, fallback_link: str,
          is_official: bool = False) -> dict:
    return {"id": source_id, "name": name, "person": person, "kind": kind, "feed_url": feed_url,
            "fallback_link": fallback_link, "is_official": is_official}


SOURCES: tuple[dict, ...] = (
    _youtube("chris-rawlings-yt", "Chris Rawlings (YouTube)", "Chris Rawlings", "UCQWVg5Q0-rsYAuRg5BLv_Sg"),
    _youtube("my-amazon-guy-yt", "My Amazon Guy (YouTube)", "Steven Pope", "UClUSEsDS2sdgNJfCcCM_5Uw"),
    _feed("my-amazon-guy-blog", "My Amazon Guy (blog)", "Steven Pope", "blog",
          "https://myamazonguy.com/feed/", "https://myamazonguy.com/"),
    _feed("my-amazon-guy-podcast", "My Amazon Guy (podcast)", "Steven Pope", "podcast",
          "https://rss.buzzsprout.com/915508.rss", "https://myamazonguy.com/"),
    _youtube("trivium-yt", "Trivium Group (YouTube)", "Mina Elias", "UCW7qjIMBvEnTyXmPU7-stdw"),
    _feed("trivium-blog", "Trivium (blog)", "Mina Elias", "blog",
          "https://triviumco.com/feed/", "https://triviumco.com/"),
    _feed("amazon-blueprint-podcast", "The Amazon Blueprint (podcast)", "Mina Elias", "podcast",
          "https://feeds.zencastr.com/f/GvH2pV5i.rss", "https://triviumco.com/"),
    _youtube("ad-badger-yt", "Ad Badger (YouTube)", "Michael Erickson Facchin", "UCSsWYJQZT32uUsjBKg9r1qA"),
    _feed("ad-badger-blog", "Ad Badger (blog)", "Michael Erickson Facchin", "blog",
          "https://www.adbadger.com/feed/", "https://www.adbadger.com/"),
    _feed("ppc-den-podcast", "The PPC Den (podcast)", "Michael Erickson Facchin", "podcast",
          "https://anchor.fm/s/6fd74c8/podcast/rss", "https://www.adbadger.com/"),
    _youtube("junglr-yt", "Junglr (YouTube)", "Elizabeth Greene", "UCFRGUdfAUxoOes2bJQkjz6g"),
    _feed("junglr-blog", "Junglr (blog)", "Elizabeth Greene", "blog",
          "https://junglr.com/feed/", "https://junglr.com/"),
    _feed("ask-junglr-podcast", "#AskJunglr (podcast)", "Elizabeth Greene", "podcast",
          "https://rss.buzzsprout.com/2329920.rss", "https://junglr.com/"),
    _feed("better-advertising-podcast", "Better Advertising with BTR Media (podcast)", "Destaney Wishon", "podcast",
          "https://api.riverside.fm/hosting/Xu0fApI9.rss", "https://www.btrmedia.com/"),
    _youtube("kiri-masters-yt", "Kiri Masters (YouTube)", "Kiri Masters", "UCkapGOaXU_uvHxDXYgQmafA"),
    _feed("retail-media-breakfast-club-podcast", "Retail Media Breakfast Club (podcast)", "Kiri Masters", "podcast",
          "https://feeds.transistor.fm/retail-media-breakfast-club", "https://www.kirimasters.com/"),
    _feed("kiri-masters-substack", "Kiri Masters (Substack)", "Kiri Masters", "blog",
          "https://kirimasters.substack.com/feed", "https://kirimasters.substack.com/"),
    _feed("billion-dollar-sellers-podcast", "Billion Dollar Sellers (podcast)", "Kevin King", "podcast",
          "https://feed.podbean.com/billiondollarsellers/feed.xml", "https://billiondollarsellers.podbean.com/"),
    _feed("billion-dollar-sellers-beehiiv", "Billion Dollar Sellers (beehiiv)", "Kevin King", "podcast",
          "https://rss.beehiiv.com/podcasts/019df0ee-e7e9-73fb-a618-52e0254d2949.xml",
          "https://www.billiondollarsellers.com/"),
    _youtube("helium10-yt", "Helium 10 (YouTube)", "Bradley Sutton", "UCzIPWCc0K9ss1sfVMtrdpsQ"),
    _feed("serious-sellers-podcast", "Serious Sellers Podcast", "Bradley Sutton", "podcast",
          "https://feed.podbean.com/helium10/feed.xml", "https://helium10.podbean.com/"),
    _feed("am-pm-podcast", "AM/PM Podcast", "Helium 10", "podcast",
          "https://feed.podbean.com/ampmpodcast/feed.xml", "https://ampmpodcast.podbean.com/"),
    _feed("amazon-ads-api-release-notes", "Amazon Ads API release notes", "Amazon", "official",
          "https://d3a0d0y2hgofx6.cloudfront.net/rss/en-us/ad-api-rss.xml",
          "https://advertising.amazon.com/API/docs/en-us/release-notes/index", is_official=True),
)

SOURCES_BY_ID: dict[str, dict] = {source["id"]: source for source in SOURCES}


def validate_sources(sources: tuple[dict, ...] = SOURCES) -> list[str]:
    """Every problem with the catalog, empty when it is valid."""
    errors: list[str] = []
    seen: set[str] = set()
    for position, source in enumerate(sources):
        label = source.get("id") or f"#{position}"
        missing = [name for name in REQUIRED_FIELDS if name not in source]
        if missing:
            errors.append(f"{label}: faltan campos {missing}")
            continue
        if source["id"] in seen:
            errors.append(f"{label}: id duplicado")
        seen.add(source["id"])
        for name in ("id", "name", "person", "feed_url", "fallback_link"):
            if not str(source[name]).strip():
                errors.append(f"{label}: {name} vacío")
        for name in ("feed_url", "fallback_link"):
            if not str(source[name]).startswith("https://"):
                errors.append(f"{label}: {name} no es https")
        if source["kind"] not in KINDS:
            errors.append(f"{label}: kind {source['kind']!r} no es uno de {KINDS}")
        if not isinstance(source["is_official"], bool):
            errors.append(f"{label}: is_official no es bool")
        if source["is_official"] != (source["kind"] == "official"):
            errors.append(f"{label}: is_official no coincide con kind")
    return errors
