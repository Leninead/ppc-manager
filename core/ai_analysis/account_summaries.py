"""The last stored Search Term analysis of every Amazon Ads account, as one chat document.

It lets the app-wide chat answer about a client the AM did not open in this session.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.ai_analysis.chat_context import analysis_summary_text
from core.ai_analysis.store import AiAnalysisStore, StoredAnalysis
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, account_labels
from core.integrations.store import _Rest

MODULE = "str"
# A quarter of the provider's 400,000-character context, so shared analyses and the conversation still fit.
SUMMARIES_MAX_CHARS = 100_000


@dataclass(frozen=True)
class AccountAnalysis:
    profile: ProfileOption
    label: str
    analysis: StoredAnalysis


def latest_account_analyses(rest: _Rest) -> list[AccountAnalysis]:
    """Accounts with data and a finished analysis, labelled against every synced account."""
    profiles = ReportProvider(rest).profiles()
    labels = account_labels(profiles)
    with_data = [profile for profile in profiles if profile.data_through is not None]
    by_profile = {analysis.subject_id: analysis for analysis in
                  AiAnalysisStore(rest).latest_by_subject(MODULE, [p.profile_id for p in with_data])}
    return [AccountAnalysis(profile, labels[profile.profile_id], by_profile[profile.profile_id])
            for profile in with_data if profile.profile_id in by_profile]


def account_summaries_document(accounts: list[AccountAnalysis], max_chars: int = SUMMARIES_MAX_CHARS) -> dict | None:
    """Newest analyses first, as many as fit; the accounts left out are named so the chat knows they exist."""
    if not accounts:
        return None
    newest_first = sorted(accounts, reverse=True, key=lambda account: (
        account.analysis.finished_at.timestamp() if account.analysis.finished_at else 0.0))
    blocks, left_out, used = [], [], 0
    for account in newest_first:
        block = f"Cuenta: {account.label}\n" + analysis_summary_text(account.analysis, account.profile.currency_code)
        if used + len(block) > max_chars:
            left_out.append(account.label)
            continue
        blocks.append(block)
        used += len(block) + 2
    if left_out:
        blocks.append(f"No entraron {len(left_out)} cuentas más con análisis guardado: {', '.join(left_out)}.")
    return {"title": f"Últimos análisis de Search Terms guardados por cuenta ({len(accounts) - len(left_out)} "
                     f"de {len(accounts)})",
            "content": "\n\n".join(blocks)}

