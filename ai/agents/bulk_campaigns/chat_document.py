"""The Bulk Campañas agent's answer as text for the app chat, with the campaign behind every row_id.

The figures stay in the agent's own campaign document; this text carries the judgement.
"""
from ai.agents import make_ids
from ai.agents.bulk_campaigns.context import CAMPAIGN_PREFIX
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict, records: list) -> str:
    """records are the campaign rows the analysis was built from, in the order their row_ids were given."""
    by_id = dict(zip(make_ids(CAMPAIGN_PREFIX, len(records)), records))
    lines = [synthesis_text(result.get("synthesis") or {})]
    items = [item for item in result.get("campaigns") or [] if item.get("row_id") in by_id]
    if items:
        lines += ["", "Campañas, en orden de prioridad (row_id · campaña → veredicto · causa · confianza):"]
        lines += [_campaign_line(item, by_id[item["row_id"]]) for item in items]
    return "\n".join(lines)


def _campaign_line(item: dict, record: dict) -> str:
    warning = f" · advertencia: {item['advertencia']}" if item.get("advertencia") else ""
    acos = f"ACoS {record['acos']}%" if record.get("acos") is not None else "sin ventas"
    # Only an account with SB or SD carries the product; an SP-only one reads as it always did.
    product = f"{record['producto']} · " if record.get("producto") else ""
    return (f"{item['row_id']} · {str(record.get('campaign', '')).strip()} "
            f"({product}{record.get('diagnostico', '')}, gasto {record.get('spend', 0)}, {acos}) → "
            f"{item.get('veredicto', '')} · {item.get('causa', '')} · {item.get('confianza', '')}: "
            f"{item.get('razon', '')}{warning}")
