"""The DataDive agent's answer as text for the app chat, with the keyword behind every row_id.

The figures stay in the agent's own keyword and competitor documents; this text carries the judgement.
"""
from ai.agents import make_ids
from ai.agents.datadive.context import KW_PREFIX
from ai.agents.synthesis_text import synthesis_text


def reading_text(result: dict, records: list) -> str:
    """records are the keywords the analysis was built from, in the order their row_ids were given."""
    by_id = dict(zip(make_ids(KW_PREFIX, len(records)), records))
    lines = [synthesis_text(result.get("synthesis") or {})]
    clusters = result.get("clusters") or []
    if clusters:
        lines += ["", "Clusters de intención, en orden de ataque:"]
        lines += [_cluster_line(position, cluster, by_id) for position, cluster in enumerate(clusters, 1)]
    gaps = [gap for gap in result.get("gaps") or [] if gap.get("row_id") in by_id]
    if gaps:
        lines += ["", "Gaps, en orden de prioridad (row_id · keyword → vía · confianza):"]
        lines += [_gap_line(gap, by_id[gap["row_id"]]) for gap in gaps]
    return "\n".join(lines)


def _cluster_line(position: int, cluster: dict, by_id: dict) -> str:
    # Ids the page cannot show are left out, as the page's own cluster table does.
    rows = [row_id for row_id in cluster.get("row_ids") or [] if row_id in by_id]
    volume = sum(by_id[row_id]["sv"] for row_id in rows)
    keywords = ", ".join(f"{row_id} ({_term(by_id[row_id])})" for row_id in rows)
    return (f"{position}. {cluster.get('nombre', '')} · prioridad {cluster.get('prioridad', '')} · "
            f"{cluster.get('match_type', '')} · {len(rows)} keywords, SV {volume:,}: "
            f"{cluster.get('racional', '')} Keywords: {keywords}")


def _gap_line(gap: dict, record: dict) -> str:
    warning = f" · advertencia: {gap['advertencia']}" if gap.get("advertencia") else ""
    return (f"{gap['row_id']} · {_term(record)} → {gap.get('via', '')} · {gap.get('confianza', '')}: "
            f"{gap.get('razon', '')}{warning}")


def _term(record: dict) -> str:
    return str(record.get("term", "")).strip()
