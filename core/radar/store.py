"""radar_items through PostgREST: the run writes a week's topics, the home reads the latest ones."""
from __future__ import annotations

from core.integrations.store import _Rest

TABLE = "radar_items"
CONFLICT_COLUMNS = "week_start,primary_link"
_READ_WINDOW = 50


def save_rows(rest: _Rest, rows: list[dict]) -> None:
    """Idempotent: running the same week again rewrites its topics instead of adding copies."""
    for row in rows:
        rest.upsert(TABLE, row, on_conflict=CONFLICT_COLUMNS)


def latest_topics(rest: _Rest, limit: int = 5) -> list[dict]:
    """The top `limit` topics of the latest run of the latest week with data, by rank."""
    rows = rest.select(TABLE, {
        "select": "week_start,title_es,summary_es,implications_es,confidence,sources,rank,created_at",
        "order": "week_start.desc,created_at.desc",
        "limit": str(_READ_WINDOW),
    })
    if not rows:
        return []
    # A second run in the same week may pick fewer topics; the first run's leftovers are not part of it.
    latest = rows[0]
    current = [row for row in rows
               if row["week_start"] == latest["week_start"] and row["created_at"] == latest["created_at"]]
    return sorted(current, key=lambda row: row["rank"])[:limit]
