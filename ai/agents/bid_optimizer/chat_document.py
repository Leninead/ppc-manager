"""The Bid Optimizer agent's answer as text for the app chat, with the ASIN behind every row_id.

The figures stay in the agent's own ASIN and campaign documents; this text carries the judgement.
"""
from ai.agents import make_ids
from ai.agents.bid_optimizer.context import ASIN_PREFIX
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict, records: list) -> str:
    """records are the ASIN rows the analysis was built from, in the order their row_ids were given."""
    by_id = dict(zip(make_ids(ASIN_PREFIX, len(records)), records))
    lines = [synthesis_text(result.get("synthesis") or {})]
    bids = [bid for bid in result.get("bids") or [] if bid.get("row_id") in by_id]
    if bids:
        lines += ["", "Bids, en orden de prioridad (row_id · ASIN → veredicto · confianza):"]
        lines += [_bid_line(bid, by_id[bid["row_id"]]) for bid in bids]
    return "\n".join(lines)


def _bid_line(bid: dict, record: dict) -> str:
    warning = f" · advertencia: {bid['advertencia']}" if bid.get("advertencia") else ""
    return (f"{bid['row_id']} · {str(record.get('asin', '')).strip()} "
            f"(bid sugerido {record.get('bid_base', 0)}, ACoS {record.get('acos', 0)}%) → "
            f"{bid.get('veredicto', '')} · {bid.get('confianza', '')}: {bid.get('razon', '')}{warning}")
