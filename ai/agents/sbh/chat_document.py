"""The SBH Recommendation agent's answer as text for the app chat, with the cluster behind every row_id.

The figures stay in the agent's own documents; this text carries the judgement and the proposed headlines.
"""
from ai.agents import make_ids
from ai.agents.sbh.context import ROW_PREFIX
from ai.agents.synthesis_text import synthesis_text


def row_item(record: dict) -> str:
    """What a row is about: its cluster."""
    return str(record.get("cluster") or "").strip()


def reading_text(result: dict, records: list) -> str:
    """records are the clusters the analysis was built from, in the order their row_ids were given."""
    by_id = dict(zip(make_ids(ROW_PREFIX, len(records)), records))
    lines = [synthesis_text(result.get("synthesis") or {})]
    items = [item for item in result.get("clusters") or [] if item.get("row_id") in by_id]
    if items:
        lines += ["", "Clusters, en orden de lanzamiento (row_id · cluster → veredicto · confianza):"]
        lines += [_row_line(item, by_id[item["row_id"]]) for item in items]
    return "\n".join(lines)


def _row_line(item: dict, record: dict) -> str:
    headline = f" · headline propuesto: «{item['headline']}»" if item.get("headline") else ""
    warning = f" · advertencia: {item['advertencia']}" if item.get("advertencia") else ""
    return (f"{item['row_id']} · {row_item(record)} → {item.get('veredicto', '')} · {item.get('confianza', '')}: "
            f"{item.get('razon', '')}{headline}{warning}")
