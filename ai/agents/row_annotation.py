"""The item behind each positional row id (N07, Q03, K12), written into AI prose."""
import re

from ai.agents import make_ids


def row_labels(prefix: str, records: list, item_field: str) -> dict:
    """{row_id: item} for the records an analysis was built from, in the order their ids were given."""
    return {row_id: str(record.get(item_field, "")).strip()
            for row_id, record in zip(make_ids(prefix, len(records or [])), records or [])}


def annotate_row_ids(text, labels_by_id: dict, max_len: int = 40) -> str:
    """Appends the item behind every row id the AI cites, so the prose reads
    without the table: "Frenar H59" -> "Frenar H59 (press on nails short)".
    Whole tokens only, first mention of each id per text. Skipped when the
    item already follows the id within a short window, which is how the model
    sometimes writes it itself."""
    if not text or not labels_by_id:
        return str(text or "")
    src = str(text)
    seen = set()

    def _sub(match):
        rid = match.group(1)
        full = str(labels_by_id[rid]).strip()
        if not full or rid in seen:
            return rid
        seen.add(rid)
        window = src[match.end():match.end() + len(full) + 24].lower()
        if full.lower() in window:
            return rid
        shown = full if len(full) <= max_len else \
            full[:max_len - 1].rstrip() + "…"
        return f"{rid} ({shown})"

    return _row_id_pattern(labels_by_id).sub(_sub, src)


def replace_row_ids(text, labels_by_id: dict) -> str:
    """Writes the item instead of every row id: for text read away from its table, where ids point nowhere."""
    if not text or not labels_by_id:
        return str(text or "")

    def _sub(match):
        item = str(labels_by_id[match.group(1)]).strip()
        return f"«{item}»" if item else match.group(1)

    return _row_id_pattern(labels_by_id).sub(_sub, str(text))


def _row_id_pattern(labels_by_id: dict) -> re.Pattern:
    ids = sorted(labels_by_id, key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(i) for i in ids) + r")(?!\w)")
