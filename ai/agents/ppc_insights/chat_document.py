"""The PPC Insights agent's answer as text for the app chat, with the ASIN behind every row_id.

The figures stay in the agent's own ASIN document; this text carries the judgement.
"""
from ai.agents import make_ids
from ai.agents.ppc_insights.context import ASIN_PREFIX
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict, records: list) -> str:
    """records are the ASIN rows the analysis was built from, in the order their row_ids were given."""
    by_id = dict(zip(make_ids(ASIN_PREFIX, len(records)), records))
    lines = [synthesis_text(result.get("synthesis") or {})]
    opinions = [opinion for opinion in result.get("asins") or [] if opinion.get("row_id") in by_id]
    if opinions:
        lines += ["", "ASINs, en orden de prioridad (row_id · ASIN → foco · confianza):"]
        lines += [_opinion_line(opinion, by_id[opinion["row_id"]]) for opinion in opinions]
    return "\n".join(lines)


def _opinion_line(opinion: dict, record: dict) -> str:
    warning = f" · advertencia: {opinion['advertencia']}" if opinion.get("advertencia") else ""
    return (f"{opinion['row_id']} · {str(record.get('asin', '')).strip()} "
            f"(health score {record.get('health_score', '')}) → "
            f"{opinion.get('foco', '')} · {opinion.get('confianza', '')}: {opinion.get('razon', '')}{warning}")
