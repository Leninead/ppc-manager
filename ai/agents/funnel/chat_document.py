"""The Análisis de Funnel agent's answer as text for the app chat, with the term or campaign behind every row_id.

The figures stay in the agent's own documents; this text carries the judgement.
"""
from ai.agents import make_ids
from ai.agents.funnel.context import ROW_PREFIX
from ai.agents.synthesis_text import synthesis_text


def row_item(record: dict) -> str:
    """What a row is about: its search term, or its campaign for an idle campaign."""
    return str(record.get("termino") or record.get("campana") or "").strip()


def reading_text(result: dict, records: list) -> str:
    """records are the rows the analysis was built from, in the order their row_ids were given."""
    by_id = dict(zip(make_ids(ROW_PREFIX, len(records)), records))
    lines = [synthesis_text(result.get("synthesis") or {})]
    items = [item for item in result.get("filas") or [] if item.get("row_id") in by_id]
    if items:
        lines += ["", "Filas, en orden de prioridad "
                      "(row_id · grupo · término o campaña → veredicto · confianza):"]
        lines += [_row_line(item, by_id[item["row_id"]]) for item in items]
    return "\n".join(lines)


def _row_line(item: dict, record: dict) -> str:
    warning = f" · advertencia: {item['advertencia']}" if item.get("advertencia") else ""
    return (f"{item['row_id']} · {record.get('grupo', '')} · {row_item(record)} → "
            f"{item.get('veredicto', '')} · {item.get('confianza', '')}: {item.get('razon', '')}{warning}")
