"""Run Radar Amazon by hand.

    python -m core.radar.run --dry-run   fetch and verify only: no AI, no database; prints what would go in
    python -m core.radar.run --no-save   also asks the AI; prints the topics, writes nothing
    python -m core.radar.run             full run: saves the week's topics in radar_items

The full run writes as the analysis worker's role: SUPABASE_URL and AI_WORKER_JWT, the same pair as ads-ai-worker.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

from core.radar import feeds, store
from core.radar.pipeline import RunResult, run
from core.radar.sources import SOURCES_BY_ID, validate_sources

JWT_ENV = "AI_WORKER_JWT"
CONFIG_ERROR_EXIT = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.radar.run", description="Radar Amazon, corrida manual.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="solo lectura de feeds y verificación: sin IA ni base")
    mode.add_argument("--no-save", action="store_true", help="con IA, sin escribir en la base")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    problems = validate_sources()
    if problems:
        print("El catálogo de fuentes tiene errores:\n- " + "\n- ".join(problems), file=sys.stderr)
        return CONFIG_ERROR_EXIT

    save = None
    if not (args.dry_run or args.no_save):
        rest = _worker_rest()
        if rest is None:
            print(f"Falta SUPABASE_URL o {JWT_ENV}: usá --no-save o --dry-run para correr sin base.", file=sys.stderr)
            return CONFIG_ERROR_EXIT
        save = lambda rows: store.save_rows(rest, rows)  # noqa: E731

    ai_ask = None
    if not args.dry_run:
        from ai import client  # deferred: a dry run never calls the provider
        ai_ask = client.ask

    result = run(datetime.now(timezone.utc), http_get=feeds._default_get, ai_ask=ai_ask, save=save)
    print(_report(result))
    if not args.dry_run:
        print(_topics(result))
        if save is not None:
            print(f"Guardados {len(result.rows)} temas en {store.TABLE} (semana {result.week_start}).")
    return 0


def _worker_rest():
    from core.integrations.store import _Rest

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get(JWT_ENV, "").strip()
    return _Rest(url, key) if (url and key) else None


def _report(result: RunResult) -> str:
    lines = [f"Radar Amazon, semana del {result.week_start}", "",
             f"{'fuente':<40} {'leídos':>7} {'7 días':>7} {'link ok':>8} {'a IA':>5}"]
    for entry in result.report:
        lines.append(f"{entry.source_id:<40} {entry.fetched:>7} {entry.in_window:>7} {entry.link_ok:>8} "
                     f"{entry.sent:>5}")
    totals = [sum(getattr(entry, name) for entry in result.report)
              for name in ("fetched", "in_window", "link_ok", "sent")]
    lines.append(f"{'TOTAL':<40} {totals[0]:>7} {totals[1]:>7} {totals[2]:>8} {totals[3]:>5}")
    lines += ["", f"Items que pasarían ({len(result.items)}):"]
    for entry in result.items:
        person = SOURCES_BY_ID[entry.source["id"]]["person"]
        lines.append(f"- {entry.item.published_at.date().isoformat()} · {person} · {entry.item.title[:80]}"
                     f" · {entry.http_status} · {entry.item.link}")
    return "\n".join(lines)


def _topics(result: RunResult) -> str:
    lines = ["", f"Temas ({len(result.rows)}, descartados por validación: {result.dropped_topics}):"]
    for row in result.rows:
        lines += [f"{row['rank']}. [{row['confidence']}] {row['title_es']}",
                  f"   {row['summary_es']}",
                  f"   Qué significa para nosotros: {row['implications_es']}"]
        lines += [f"   - {source['person']} · {source['published_at'][:10]} · {source['link']}"
                  for source in row["sources"]]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
