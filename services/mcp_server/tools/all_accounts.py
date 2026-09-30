"""A per-account tool answered for every synced account at once.

A general question — which campaigns run out of budget, what to negate, which ASIN is worst — used to cost the chat
a lap around the accounts: it paged the overview to pick the ones with the most spend, opened each one with the same
tool, and ranked what came back by reasoning over it. Here that lap is code. The tool runs on every account in
parallel, each with its own saved parameters and its own window, and its rows come back ranked the way the tool ranks
them, one list per currency: amounts in different currencies are never compared.

Each account already returns its rows in the tool's order, so the first `offset + limit` rows of every account are
enough to build the exact page of the ranking that starts at `offset`.
"""
from __future__ import annotations

import functools
import inspect
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from core.amazon_ads.report_provider import ProfileOption, ReportProvider, account_labels
from services.mcp_server.limits import MAX_ROWS, rows_within_chars, serialized_chars
from services.mcp_server.tools.metric_filters import sort_rows

log = logging.getLogger(__name__)

MAX_WORKERS = 8
DEFAULT_ROWS_PER_CURRENCY = 15
# The provider cuts a tool result at 20,000 characters; the whole answer stays under it.
MAX_PAYLOAD_CHARS = 19_000
ADDITIVE_TOTALS = ("spend", "sales", "orders", "clicks", "impressions", "spend_without_sales")
ALL_ACCOUNTS_NOTE = (
    "Es la misma consulta en cada cuenta sincronizada, con sus propios parámetros guardados y su propia ventana "
    "(windows dice cuáles y en cuántas cuentas). by_currency separa las filas por moneda y cada lista viene rankeada "
    "como la herramienta rankea una cuenta: nunca compares ni sumes montos de monedas distintas. counts suma los "
    "conteos de todas las cuentas. Para el detalle de una cuenta, llamá sin all_accounts con su profile_id.")

RankRows = Callable[[list[dict], dict], list[dict]]


@dataclass
class AccountResult:
    profile: ProfileOption
    label: str
    payload: dict = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    total: int = 0
    skipped: str = ""
    failed: str = ""


def answers_all_accounts(*, what: str, rank: RankRows):
    """Adds `all_accounts` to a per-account tool: with it, the tool runs on every synced account and ranks the rows.

    `rank` orders rows the way the tool orders one account's, given the call's arguments; `what` names the rows.
    """
    def decorate(tool):
        signature = inspect.signature(tool, eval_str=True)

        @functools.wraps(tool)
        def run(rest, *, all_accounts: bool = False, **call):
            if not all_accounts:
                return tool(rest, **call)
            if str(call.get("profile_id") or "").strip() or str(call.get("account") or "").strip():
                raise ValueError("all_accounts corre en todas las cuentas: pedilo sin profile_id ni account.")
            first_row = max(0, int(call.pop("offset", 0) or 0))
            if first_row >= MAX_ROWS:
                raise ValueError(f"Con all_accounts cada moneda llega hasta la fila {MAX_ROWS}: para seguir, pedí el "
                                 "detalle de una cuenta sin all_accounts, con su profile_id.")
            wanted = max(1, min(int(call.pop("limit", DEFAULT_ROWS_PER_CURRENCY)), MAX_ROWS - first_row))
            for per_account in ("profile_id", "account"):
                call.pop(per_account, None)

            def run_account(profile_id: str, offset: int, limit: int) -> dict:
                return tool(rest, **call, profile_id=profile_id, offset=offset, limit=limit)

            return run_on_all_accounts(rest, run_account, rank=lambda rows: rank(rows, call),
                                       rows_per_currency=wanted, what=what, offset=first_row)

        flag = inspect.Parameter("all_accounts", inspect.Parameter.KEYWORD_ONLY, default=False, annotation=bool)
        run.__signature__ = signature.replace(parameters=[*signature.parameters.values(), flag])
        return run
    return decorate


def rank_by_sort_arguments(rows: list[dict], call: dict) -> list[dict]:
    """The order of the tools that take sort_by, sort_order and order_by_change."""
    metric = call.get("sort_by") or "spend"
    if call.get("order_by_change"):
        metric = f"delta_{metric}"
    return sort_rows(rows, metric, call.get("sort_order") or "desc")


def run_on_all_accounts(rest, run_account: Callable[[str, int, int], dict], *,
                        rank: Callable[[list[dict]], list[dict]], rows_per_currency: int, what: str,
                        offset: int = 0) -> dict:
    """Every synced account through `run_account`, merged: the ranked rows per currency from `offset`, the summed
    counts, and which accounts had rows, had none, had no data or failed. No account is dropped without saying so."""
    started = time.monotonic()
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    rows_per_account = offset + rows_per_currency
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="all-accounts") as pool:
        results = list(pool.map(
            lambda profile: _account_result(run_account, profile, labels[profile.profile_id], rows_per_account),
            profiles))
    answered = [result for result in results if result.payload]
    log.info("all_accounts %s: %d accounts, %d with rows, %d skipped, %d failed in %.1fs", what, len(results),
             sum(1 for result in answered if result.total), sum(1 for result in results if result.skipped),
             sum(1 for result in results if result.failed), time.monotonic() - started)
    ranked = _ranked_by_currency(answered, rank, rows_per_currency, offset)
    payload = {
        "scope": "all_accounts",
        "total": sum(result.total for result in answered),
        "by_currency": [group for group, _ in ranked],
        "counts": _summed_counts(result.payload.get("counts") for result in answered),
        "windows": _windows(answered),
        "accounts": {
            "asked": len(results),
            "with_rows": [{"account": result.label, "profile_id": result.profile.profile_id, "rows": result.total}
                          for result in sorted(answered, key=lambda r: -r.total) if result.total],
            "without_rows": [result.label for result in answered if not result.total],
            "without_data": [{"account": result.label, "reason": result.skipped}
                             for result in results if result.skipped],
            "failed": [{"account": result.label, "error": result.failed} for result in results if result.failed],
        },
        "note": (f"Hay {sum(result.total for result in answered)} {what} en "
                 f"{sum(1 for result in answered if result.total)} cuentas; cada moneda trae hasta "
                 f"{rows_per_currency}{f' desde la fila {offset + 1}' if offset else ''}. {ALL_ACCOUNTS_NOTE}"),
    }
    _fill_rows(payload, ranked, rows_per_currency)
    return payload


def _account_result(run_account, profile: ProfileOption, label: str, wanted: int) -> AccountResult:
    if profile.data_through is None:
        return AccountResult(profile, label, skipped="Todavía no tiene datos sincronizados.")
    try:
        payload = run_account(profile.profile_id, 0, wanted)
        rows = list(payload.get("rows") or [])
        total = int(payload.get("total") or len(rows))
        # A page cut by size holds fewer rows than asked: the next ones come from the following offset.
        while len(rows) < min(wanted, total):
            more = run_account(profile.profile_id, len(rows), wanted - len(rows)).get("rows") or []
            if not more:
                break
            rows += more
    except ValueError as exc:
        return AccountResult(profile, label, skipped=str(exc))
    except Exception as exc:  # noqa: BLE001 — one broken account must not hide the other fifty
        log.exception("all_accounts: profile %s failed", profile.profile_id)
        return AccountResult(profile, label, failed=f"{type(exc).__name__}: {exc}")
    return AccountResult(profile, label, payload=payload, rows=rows, total=total)


def _ranked_by_currency(answered: list[AccountResult], rank, rows_per_currency: int,
                        offset: int) -> list[tuple[dict, list]]:
    """Each currency's header and its ranked rows from `offset`: the currency with the most accounts first, then the
    most rows."""
    groups: dict[str, list[AccountResult]] = {}
    for result in answered:
        if result.total:
            currency = str(result.payload.get("currency") or result.profile.currency_code or "")
            groups.setdefault(currency, []).append(result)
    ranked = []
    for currency, results in sorted(groups.items(),
                                    key=lambda item: (-len(item[1]), -sum(r.total for r in item[1]), item[0])):
        rows = [{"account": result.label, "profile_id": result.profile.profile_id, **row}
                for result in results for row in result.rows]
        header = {"currency": currency, "accounts": len(results), "total": sum(result.total for result in results),
                  "showing": 0, "offset": offset,
                  "totals": _summed_totals(result.payload.get("totals") for result in results), "rows": []}
        ranked.append((header, rank(rows)[offset:offset + rows_per_currency]))
    return ranked


def _fill_rows(payload: dict, ranked: list[tuple[dict, list]], rows_per_currency: int) -> None:
    """Rows into each currency in proportion to how many it has, within what the provider lets through whole."""
    budget = max(0, MAX_PAYLOAD_CHARS - serialized_chars(payload))
    weight = sum(header["total"] for header, _ in ranked) or 1
    for header, rows in ranked:
        header["rows"] = rows_within_chars(rows, budget * header["total"] // weight)
    # Every currency keeps its first row even when its share is smaller: trim the longest list until it all fits.
    while serialized_chars(payload) > MAX_PAYLOAD_CHARS:
        longest = max((header for header, _ in ranked), key=lambda header: len(header["rows"]), default=None)
        if longest is None or len(longest["rows"]) < 2:
            break
        longest["rows"].pop()
    for header, rows in ranked:
        header["showing"] = len(header["rows"])
        following = header["offset"] + header["showing"]
        if following >= header["total"]:
            continue
        header["next_offset"] = following
        if header["showing"] < min(header["total"] - header["offset"], rows_per_currency):
            header["note"] = (f"Esta moneda muestra {header['showing']} de {header['total']} filas para que la "
                              f"respuesta entre entera: seguí con offset={following}, o acotá la consulta.")
        else:
            header["note"] = (f"Esta moneda tiene {header['total']} filas y trae de la {header['offset'] + 1} a la "
                              f"{following}: seguí con offset={following}.")


def _windows(answered: list[AccountResult]) -> list[dict]:
    """The windows the accounts were read in, with how many accounts each: they differ when data runs to other days."""
    counted: dict[tuple, int] = {}
    for result in answered:
        window = result.payload.get("window") or {}
        if window.get("from") and window.get("to"):
            key = (window["from"], window["to"])
            counted[key] = counted.get(key, 0) + 1
    return [{"from": start, "to": end, "accounts": accounts}
            for (start, end), accounts in sorted(counted.items(), key=lambda item: -item[1])]


def _summed_counts(counts_per_account) -> dict:
    """Every count every account reported, added up; lists and text are left out, since they do not add."""
    summed: dict = {}
    for counts in counts_per_account:
        _add_counts(summed, counts or {})
    return summed


def _add_counts(into: dict, counts: dict) -> None:
    for key, value in counts.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            into[key] = round(into.get(key, 0) + value, 2)
        elif isinstance(value, dict):
            _add_counts(into.setdefault(key, {}), value)


def _summed_totals(totals_per_account) -> dict:
    """The additive totals of the accounts in one currency; ratios such as ACoS do not add and are left out."""
    summed: dict = {}
    for totals in totals_per_account:
        for key in ADDITIVE_TOTALS:
            value = (totals or {}).get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                summed[key] = round(summed.get(key, 0) + value, 2)
    return summed
