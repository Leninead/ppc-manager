"""E2E smoke: round-trip every persisted table against the self-hosted PostgREST.

Run inside the app container (it has the code, the supabase env, and network to the
gateway):  docker exec -w /app ppc-manager python /tmp/e2e_selfhosted_db.py
Drives the real backend objects (same transport the app uses), not the cached wrappers.
"""

import os
import sys
import traceback
import uuid
from datetime import date

import pandas as pd
import requests

import core.persistence as P
import core.forecast.persistence as F
import core.innovation.persistence as I
import core.proposals.persistence as PP
from core.integrations.store import _Rest, _rest_credentials
from core.seller_reports import columns as seller_columns
from core.seller_reports.periods import SqpPeriod, sqp_week
from core.seller_reports.store import SellerReportRejected, SellerReportStore

results = []


def check(name, cond, detail=""):
    ok = bool(cond)
    results.append((name, ok))
    print(("OK  " if ok else "FAIL") + f" | {name} | {detail}")


AREA, CLI, MOD = "account-health", "e2e-test", "selfhost-check"

# ── Account Health: ah_snapshots, ah_configs, ah_logs, ah_client_configs ──────
try:
    ah = P._get_backend()
    print("AH backend:", type(ah).__name__)

    df = pd.DataFrame({"sku": ["A1", "B2"], "units": [3, 5]})
    ah.save_snapshot(df, AREA, CLI, MOD, "2026-08")
    got = ah.load_snapshot(AREA, CLI, MOD, "2026-08")
    check("ah_snapshots", got is not None and list(got["sku"]) == ["A1", "B2"],
          f"rows={0 if got is None else len(got)}")

    ah.save_config({"k": "v", "n": 1}, AREA, MOD, "e2e-cfg", 1)
    cfg = ah.load_config(AREA, MOD, "e2e-cfg", 1)
    check("ah_configs", cfg.get("k") == "v", str(cfg))

    ah.append_log({"evt": "hello", "timestamp": "2026-08-15T00:00:00"}, AREA, CLI, MOD, "events")
    ah.append_log({"evt": "world"}, AREA, CLI, MOD, "events")
    log = ah.load_log(AREA, CLI, MOD, "events")
    check("ah_logs (append+order)", len(log) >= 2 and list(log["evt"])[:2] == ["hello", "world"],
          f"rows={len(log)}")

    ah.save_client_config({"tracked": ["A1"]}, AREA, CLI, MOD, "tracked-skus")
    cc = ah.load_client_config(AREA, CLI, MOD, "tracked-skus")
    check("ah_client_configs", cc.get("tracked") == ["A1"], str(cc))
except Exception as e:
    check("account-health block", False, f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ── Forecast: forecast_clients ────────────────────────────────────────────────
try:
    fc = F._get_backend()
    print("Forecast backend:", type(fc).__name__)
    fc.save_client_config({"clientName": "E2E", "meses": 12}, AREA, CLI, "revenue-forecast", "E2E")
    got = fc.load_client_config(AREA, CLI, "revenue-forecast", "E2E")
    check("forecast_clients", got.get("clientName") == "E2E", str(got))
except Exception as e:
    check("forecast block", False, f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ── Innovation: ideas, votos, comentarios, prototipos ─────────────────────────
try:
    inn = I._get_backend()
    print("Innovation backend:", type(inn).__name__)
    idea_id = inn.create_idea({"titulo": "E2E idea", "autor": "tester"})
    idea = inn.get_idea(idea_id)
    check("innovation_ideas", idea.get("titulo") == "E2E idea", f"id={idea_id}")
    inn.upsert_voto(idea_id, "tester", 1, "good")
    check("innovation_votos", len(inn.list_votos(idea_id)) >= 1)
    inn.add_comentario(idea_id, "tester", "nice")
    check("innovation_comentarios", len(inn.list_comentarios(idea_id)) >= 1)
    inn.add_prototipo(idea_id, "proto1", "<h1>hi</h1>", "tester")
    check("innovation_prototipos", len(inn.list_prototipos(idea_id)) >= 1)
    inn.update_idea(idea_id, {"estado": "revisada"})  # PATCH path
    check("innovation PATCH (update_idea)", inn.get_idea(idea_id).get("estado") == "revisada")
except Exception as e:
    check("innovation block", False, f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ── Proposals: proposals, proposal_votes ──────────────────────────────────────
try:
    st = PP._default_storage()
    print("Proposal storage:", type(st).__name__)
    prop = {"id": "e2e-prop", "version": 1, "client_name": "E2E", "status": "draft",
            "archetype": "x", "updated_at": "2026-08-15", "modules": []}
    st.write_proposal(prop)
    got = st.read_proposal("e2e-prop", 1)
    check("proposals", got is not None and got.get("client_name") == "E2E", str(got and got.get("id")))
    vote_id = f"e2e-vote-{uuid.uuid4().hex[:8]}"  # append-only: unique id so re-runs don't conflict
    st.append_vote({"id": vote_id, "module_id": "m-x", "voter_name": "tester",
                    "voted_at": "2026-08-15", "proposal_id": "e2e-prop"})
    votes = st.read_votes()
    check("proposal_votes", (not votes.empty) and bool((votes["id"] == vote_id).any()),
          f"rows={len(votes)}")
except Exception as e:
    check("proposals block", False, f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ── DELETE path (ah_snapshots.delete_snapshot) ────────────────────────────────
try:
    ah = P._get_backend()
    ah.save_snapshot(pd.DataFrame({"x": [1]}), AREA, CLI, MOD, "9999-del")
    assert ah.load_snapshot(AREA, CLI, MOD, "9999-del") is not None
    ah.delete_snapshot(AREA, CLI, MOD, "9999-del")
    check("ah_snapshots DELETE", ah.load_snapshot(AREA, CLI, MOD, "9999-del") is None)
except Exception as e:
    check("delete block", False, f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ── Seller Central (023): the write path the app and the SP-API worker share ──
# It creates its own Amazon Ads account with the worker's JWT and removes everything it created at the end, so it
# leaves nothing behind. Without INTEGRATIONS_WORKER_JWT it is skipped.
def seller_central_checks(url: str, app_key: str, worker_key: str) -> None:
    app_rest, worker_rest = _Rest(url, app_key), _Rest(url, worker_key)
    app, worker = SellerReportStore(app_rest), SellerReportStore(worker_rest)
    suffix = uuid.uuid4().hex[:10].upper()
    entity_id, profile_id = f"AE2E{suffix}", f"e2e-{suffix.lower()}"
    worker_rest.insert("integration_accounts", {
        "integration_slug": "amazon_ads", "cuenta_externa_id": entity_id, "nombre_externo": "E2E seller reports",
        "tipo": "seller", "region": "NA", "marketplaces": ["MX"],
        "profiles": [{"profile_id": profile_id, "marketplace_id": "A1AM78C64UM0Y8", "country_code": "MX"}]})
    account = None
    try:
        account = app.account_for_ads_profile(profile_id, "e2e")
        check("seller_accounts (from the Ads profile)",
              account.marketplace_id == "A1AM78C64UM0Y8" and account.selling_partner_id is None, str(account))

        days = [{"day": "2026-09-01", "units_ordered": 10, "sessions": 100},
                {"day": "2026-09-02", "units_ordered": 12.0, "sessions": 110}]
        preview = app.upload_sales_traffic_daily(account.id, days, preview=True, loaded_by="e2e", file_name="e2e.csv")
        stored = app_rest.select("seller_sales_traffic_daily",
                                 {"select": "day", "seller_account_id": f"eq.{account.id}"})
        check("upload preview writes nothing",
              [c.status for c in preview.changes] == ["inserted", "inserted"] and not stored)
        first = app.upload_sales_traffic_daily(account.id, days, loaded_by="e2e", file_name="e2e.csv")
        check("upload inserts", [c.status for c in first.changes] == ["inserted", "inserted"] and first.load_id)
        again = app.upload_sales_traffic_daily(account.id, days, loaded_by="e2e", file_name="e2e.csv")
        check("the same file twice is unchanged",
              [c.status for c in again.changes] == ["unchanged", "unchanged"] and again.load_id is None)
        api = worker.save_sales_traffic_daily(account.id, [{"day": "2026-09-02", "units_ordered": 13, "sessions": 111}],
                                              loaded_by="e2e worker")
        check("SP-API replaces a manual day",
              [(c.status, c.existing_source) for c in api.changes] == [("replaced", "manual")])
        held = app.upload_sales_traffic_daily(account.id, days, loaded_by="e2e", file_name="e2e.csv")
        check("the hand over SP-API data asks first",
              [c.status for c in held.changes] == ["unchanged", "conflict"] and held.load_id is None)
        confirmed = app.upload_sales_traffic_daily(account.id, days, replace_api_data=True, loaded_by="e2e",
                                                   file_name="e2e.csv")
        check("confirmed, the file replaces it", [c.status for c in confirmed.changes] == ["unchanged", "replaced"])
        undone = app.revert_load(confirmed.load_id, reverted_by="e2e")
        units = [row["units_ordered"] for row in app_rest.select(
            "seller_sales_traffic_daily",
            {"select": "units_ordered", "seller_account_id": f"eq.{account.id}", "order": "day.asc"})]
        check("undoing the load brings the SP-API day back",
              [c.status for c in undone.changes] == ["restored"] and units == [10, 13], str(units))

        week = sqp_week(date(2026, 9, 16))
        sqp = app.upload_search_query_performance(
            account.id, seller_columns.BRAND_VIEW, "E2E Brand", week,
            [{"search_query": "e2e query", "total_click_count": 10, "own_click_count": 2}], loaded_by="e2e")
        check("SQP Brand View of an Amazon week", [c.status for c in sqp.changes] == ["inserted"])
        try:
            app.upload_search_query_performance(account.id, seller_columns.BRAND_VIEW, "E2E Brand",
                                                SqpPeriod("week", date(2026, 9, 14), date(2026, 9, 20)),
                                                [{"search_query": "e2e query"}])
            check("a week not on Sunday is refused", False, "it was accepted")
        except SellerReportRejected as exc:
            check("a week not on Sunday is refused", exc.code == "week_not_on_sunday", exc.code)
        by_asin = app.upload_sales_traffic_by_asin(account.id, date(2026, 9, 1), date(2026, 9, 14),
                                                   [{"child_asin": "B0E2ETEST1", "units_ordered": 5}], loaded_by="e2e")
        check("By Child of an exact range", [c.status for c in by_asin.changes] == ["inserted"])

        try:
            app_rest.insert("seller_sales_traffic_daily", {"seller_account_id": account.id, "day": "2026-09-03"})
            check("the app cannot write a table directly", False, "the insert went through")
        except requests.HTTPError as exc:
            check("the app cannot write a table directly", exc.response.status_code in (401, 403),
                  str(exc.response.status_code))

        deleted = app.delete_periods(account.id, seller_columns.SALES_TRAFFIC_DAILY, "", date(2026, 9, 1),
                                     date(2026, 9, 30), replace_api_data=True, deleted_by="e2e")
        restored = app.revert_load(deleted.load_id, reverted_by="e2e")
        check("a delete is undone", [c.status for c in deleted.changes] == ["deleted", "deleted"]
              and [c.status for c in restored.changes] == ["restored", "restored"])
    finally:
        if account is not None:
            everything = (date(2000, 1, 1), date(2100, 1, 1))
            for dataset, brand_or_asin in ((seller_columns.SALES_TRAFFIC_DAILY, ""),
                                           (seller_columns.SALES_TRAFFIC_BY_ASIN, ""),
                                           (seller_columns.SQP_BRAND_VIEW, "E2E Brand")):
                app.delete_periods(account.id, dataset, brand_or_asin, *everything, replace_api_data=True)
            check("the test account is deleted with its loads and history", app.delete_account(account.id))
        requests.delete(f"{url.rstrip('/')}/rest/v1/integration_accounts",
                        params={"cuenta_externa_id": f"eq.{entity_id}"},
                        headers={"apikey": worker_key, "Authorization": f"Bearer {worker_key}"},
                        timeout=10).raise_for_status()


try:
    credentials = _rest_credentials()
    worker_jwt = os.environ.get("INTEGRATIONS_WORKER_JWT", "")
    if credentials is None or not worker_jwt:
        print("SKIP | seller central | needs SUPABASE_URL, SUPABASE_KEY and INTEGRATIONS_WORKER_JWT")
    else:
        seller_central_checks(credentials[0], credentials[1], worker_jwt)
except Exception as e:
    check("seller central block", False, f"{type(e).__name__}: {e}")
    traceback.print_exc()

passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"\n=== E2E SELF-HOSTED DB: {passed}/{total} checks passed ===")
sys.exit(0 if passed == total and total >= 13 else 1)
