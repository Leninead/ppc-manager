"""Whether an account has each of a list of keywords or ASIN targets: one row per term, found or not, in one call."""
from __future__ import annotations

from typing import Literal

from services.mcp_server.tools.figures import _metrics

TargetMatch = Literal["exact", "contains"]
MAX_LOOKUP_TERMS = 50
MAX_CAMPAIGNS_PER_TERM = 10
LOOKUP_NOTE = ("Cada fila es uno de los términos pedidos: found dice si la cuenta lo tiene en el último listado, "
               "running si corre en alguna campaña (él y su campaña habilitados), match_types sus tipos de match o de "
               "target, y campaigns dónde está, con su bid; las métricas suman todas sus filas. Con match=exact un "
               "keyword es exactamente el término y un product target apunta exactamente a ese ASIN (asin=\"…\" o "
               "asin-expanded=\"…\"); con contains, el término está dentro del texto.")


def lookup_terms(rows: list[dict], terms: list[str], match: str) -> list[dict]:
    """One row per requested term: whether the listed keywords or targets have it, where, and their figures."""
    if match not in ("exact", "contains"):
        raise ValueError("match tiene que ser exact o contains.")
    wanted = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
    if not wanted:
        raise ValueError("targets tiene que traer al menos un término.")
    if len(wanted) > MAX_LOOKUP_TERMS:
        raise ValueError(f"targets acepta hasta {MAX_LOOKUP_TERMS} términos por llamada; se pidieron {len(wanted)}.")
    return [_term_row(term, [row for row in rows if _matches(row["target"], term, match)]) for term in wanted]


def _term_row(term: str, found: list[dict]) -> dict:
    if not found:
        return {"term": term, "found": False}
    places = [_place(row) for row in found]
    row = {"term": term, "found": True, "running": any(_runs(place) for place in places),
           "match_types": sorted({place["match_type"] for place in places if place["match_type"]}),
           "campaigns": places[:MAX_CAMPAIGNS_PER_TERM]}
    if len(places) > MAX_CAMPAIGNS_PER_TERM:
        row["campaigns_total"] = len(places)
    measured = [place for place in found if place.get("spend") is not None]
    if measured:
        row.update(_metrics(sum(place["spend"] for place in measured), sum(place["sales"] for place in measured),
                            sum(place["orders"] for place in measured), sum(place["clicks"] for place in measured),
                            sum(place["impressions"] for place in measured)))
    return row


def _place(row: dict) -> dict:
    """Where a found term sits, with its bid; an SB or SD bid comes with how its campaign pays."""
    place = {"campaign": row["campaign"], "campaign_id": row["campaign_id"], "state": row["state"],
             "campaign_state": row.get("campaign_state", ""), "bid": row.get("bid"),
             "match_type": row.get("match_type") or row.get("kind", "")}
    if "cost_type" in row:
        place["cost_type"] = row["cost_type"]
    return place


def _matches(text: str, term: str, match: str) -> bool:
    folded, wanted = str(text or "").casefold(), term.casefold()
    if match == "contains":
        return wanted in folded
    return folded == wanted or expression_value(folded) == wanted


def expression_value(expression: str) -> str:
    """The value a single-predicate targeting expression aims at: asin="b0xx" -> b0xx; any other text as it is."""
    name, sign, value = expression.partition("=")
    quoted = len(value) >= 2 and value.startswith('"') and value.endswith('"') and '"' not in value[1:-1]
    if not sign or " " in name.strip() or not quoted:
        return expression
    return value[1:-1]


def _runs(place: dict) -> bool:
    """A keyword or target runs only when it and its campaign are enabled."""
    campaign_state = str(place.get("campaign_state", "ENABLED")).upper()
    return str(place["state"]).upper() == "ENABLED" and campaign_state == "ENABLED"
