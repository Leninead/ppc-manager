"""E2E smoke: round-trip every persisted table against the self-hosted PostgREST.

Run inside the app container (it has the code, the supabase env, and network to the
gateway):  docker exec -w /app ppc-manager python /tmp/e2e_selfhosted_db.py
Drives the real backend objects (same transport the app uses), not the cached wrappers.
"""

import sys
import traceback
import uuid

import pandas as pd

import core.persistence as P
import core.forecast_persistence as F
import core.innovation_persistence as I
import core.proposal_persistence as PP

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

passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"\n=== E2E SELF-HOSTED DB: {passed}/{total} checks passed ===")
sys.exit(0 if passed == total and total >= 13 else 1)
