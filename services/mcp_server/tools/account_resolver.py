"""Which Amazon Ads account a tool reads: the one its profile_id names, or the one whose name the chat gave."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from core.amazon_ads import campaign_totals
from core.amazon_ads.campaign_provider import campaign_sync_view
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, account_labels
from core.amazon_ads.sync_planner import CAMPAIGNS_KIND
from core.integrations.sync_jobs import SyncJobStore
from services.mcp_server.tools.windows import clipped_window, requested_dates, window_for, window_payload


def name_key(name: str) -> str:
    """A name compared by its letters and digits alone, without accents: «Dermaglós & Co» finds dermaglos-co."""
    return "".join(character for character in unicodedata.normalize("NFKD", name.casefold())
                   if character.isalnum())


def matching_profiles(profiles: list[ProfileOption], account: str) -> list[ProfileOption]:
    """The accounts whose name holds `account`; the ones whose client name is exactly it, when there are any."""
    wanted = name_key(account)
    labels = account_labels(profiles)
    found = [profile for profile in profiles if wanted in name_key(labels[profile.profile_id])]
    exact = [profile for profile in found
             if wanted in (name_key(profile.label), name_key(labels[profile.profile_id]))]
    return exact or found


@dataclass(frozen=True)
class AccountChoice:
    """The account a tool reads, or every account a name matched when it matched more than one."""

    profile_id: str = ""
    account: str = ""
    candidates: tuple[dict, ...] = ()

    def as_payload(self) -> dict:
        return {"rows": [], "total": 0, "showing": 0, "offset": 0, "candidates": list(self.candidates),
                "note": (f"«{self.account}» coincide con {len(self.candidates)} cuentas: volvé a llamar con el "
                         "profile_id de una de candidates, o con un account que nombre una sola. spend es lo que "
                         "gastaron sus campañas en la ventana pedida, cada una en su moneda.")}


def choose_account(rest, profile_id: str, account: str, *, days: int, date_from: str = "",
                   date_to: str = "") -> AccountChoice:
    """The account a per-account tool reads: `profile_id` when given, else the one whose name holds `account`."""
    if profile_id.strip():
        return AccountChoice(profile_id=profile_id.strip())
    if not name_key(account):
        raise ValueError("Pasá profile_id o account (parte del nombre del cliente, como en list_accounts).")
    profiles = ReportProvider(rest).profiles()
    found = matching_profiles(profiles, account)
    if not found:
        raise ValueError(f"Ninguna cuenta tiene «{account}» en el nombre; list_accounts da los nombres de todas.")
    if len(found) == 1:
        return AccountChoice(profile_id=found[0].profile_id)
    labels = account_labels(profiles)
    jobs = SyncJobStore(rest)
    candidates = [_candidate(rest, jobs, profile, labels[profile.profile_id], days, date_from, date_to)
                  for profile in found]
    candidates.sort(key=lambda row: (row["spend"] is not None, row["spend"] or 0), reverse=True)
    return AccountChoice(account=account, candidates=tuple(candidates))


def _candidate(rest, jobs: SyncJobStore, profile: ProfileOption, label: str, days: int, date_from: str,
               date_to: str) -> dict:
    """One account a name matched, with what its campaigns spent in the window the tool was asked for."""
    row = {"account": label, "country": profile.country_code, "profile_id": profile.profile_id,
           "currency": profile.currency_code, "spend": None}
    synced = campaign_sync_view(profile, jobs.latest_completed_for_profile(profile.profile_id, CAMPAIGNS_KIND))
    if synced.data_through is None:
        return {**row, "window_note": "Todavía no tiene campañas sincronizadas."}
    if date_from or date_to:
        clipped = clipped_window(synced, *requested_dates(date_from, date_to))
        if clipped is None:
            return {**row, "window_note": "No tiene datos en las fechas pedidas."}
        start, end, _ = clipped
    else:
        start, end = window_for(synced, days)
    series = campaign_totals.daily_totals(rest, synced, start, end)
    return {**row, "spend": round(float(campaign_totals.series_total(series).spend), 2),
            "window": window_payload(start, end)}


def profile_by_id(rest, profile_id: str) -> ProfileOption:
    """The account as the search-term sync sees it; raises when it is unknown or has no data yet."""
    for profile in ReportProvider(rest).profiles():
        if profile.profile_id == profile_id:
            if profile.data_through is None:
                raise ValueError(f"La cuenta {profile_id} todavía no tiene datos sincronizados.")
            return profile
    raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {profile_id}.")


def campaign_profile(rest, profile_id: str, *, search_terms_hint: bool = False) -> ProfileOption:
    """La cuenta como la ve la sincronización de campañas: los días que guarda, hasta su última corrida completa."""
    for profile in ReportProvider(rest).profiles():
        if profile.profile_id == profile_id:
            view = campaign_sync_view(
                profile, SyncJobStore(rest).latest_completed_for_profile(profile_id, CAMPAIGNS_KIND))
            if view.data_through is None:
                hint = (" Sus cifras de Sponsored Products sumadas de los search terms están con source=search_terms."
                        if search_terms_hint and profile.data_through is not None else "")
                raise ValueError(f"La cuenta {profile_id} todavía no tiene campañas sincronizadas.{hint}")
            return view
    raise ValueError(f"No hay ninguna cuenta sincronizada con profile_id {profile_id}.")
