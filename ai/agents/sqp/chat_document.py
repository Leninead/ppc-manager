"""The SQP agent's answer as text for the app chat, each opinion next to the query it judges.

The figures stay in the agent's own "Señales por query" document; this text carries the judgement.
"""
from ai.agents import make_ids
from ai.agents.sqp.context import QUERY_PREFIX
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict, records: list) -> str:
    """records are the rows the analysis was built from, in the order their row_ids were given."""
    lines = [synthesis_text(result.get("synthesis") or {})]
    opinions = {opinion.get("row_id"): opinion for opinion in result.get("queries") or []}
    rows = [(row_id, record, opinions[row_id])
            for row_id, record in zip(make_ids(QUERY_PREFIX, len(records)), records) if row_id in opinions]
    if rows:
        lines += ["", "Lectura por query (row_id · query → tipo · diagnóstico · precio · acción · confianza):"]
        lines += [_query_line(row_id, record, opinion) for row_id, record, opinion in rows]
    return "\n".join(lines)


def _query_line(row_id: str, record: dict, opinion: dict) -> str:
    warning = f" · advertencia: {opinion['warning']}" if opinion.get("warning") else ""
    return (f"{row_id} · {str(record.get('query', '')).strip()} → {opinion.get('query_type', '')} · "
            f"{opinion.get('funnel_diagnosis', '')} · {opinion.get('price_causality', '')} · "
            f"{opinion.get('action', '')} · {opinion.get('confidence', '')}: {opinion.get('reasoning', '')}{warning}")
