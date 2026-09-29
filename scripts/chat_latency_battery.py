"""Chat latency battery: fixed questions sent to the provider exactly as the chat panel sends them.

Each question runs once per effort, one turn at a time, as a new conversation from the home page. With --pool
the questions are the chat's own starter questions, each from its page, and a question that the chat answers
by proposing an account gets a second turn that accepts it, in the same conversation.
Turns never overlap, so none of them waits in the provider's queue. Each turn is saved as
<question>__<effort>.json; scripts/chat_latency_timeline.py then splits it into steps.

The answers carry client figures, so OUT_DIR must be outside the repo (e.g.
../copilot-eval/latency/<date>). Needs the local stack running in Docker: the provider, the
MCP server and the PostgREST gateway. Unset connection settings are read from the
`ppc-manager` container, the same way the agency-os-e2e-bridged-macos entry in
.claude/launch.json does it.

Usage:
    python scripts/chat_latency_battery.py OUT_DIR [--efforts xhigh,low] [--only q1_overview,q4_search_terms]
    python scripts/chat_latency_battery.py OUT_DIR --pool --efforts xhigh [--only q02,q12]
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import warnings

REPO = pathlib.Path(__file__).resolve().parent.parent

QUESTIONS = {
    "q1_overview": "¿Cómo vienen los ads de todas las cuentas esta semana?",
    "q2_keywords": "¿Qué keywords me están quemando plata en Dermaglos?",
    "q3_budget": "¿Qué campañas de Shapermint US se están quedando sin presupuesto?",
    "q4_search_terms": "¿Qué search terms venden y todavía no tengo en exact en Tattoo Care USA?",
    "q5_spend_growth": "¿Qué cliente aumentó más el gasto este último mes?",
}
HOME_PAGE = "🏠 Inicio"
# The pool question that leaves the account to the AM gets the AM's yes as its second turn.
POOL_FOLLOW_UPS = {"q12": "Sí, armalo sobre esa cuenta."}


def _container_env(name: str) -> str:
    out = subprocess.run(["docker", "inspect", "ppc-manager", "--format",
                          "{{range .Config.Env}}{{println .}}{{end}}"],
                         capture_output=True, text=True, check=True).stdout
    return next((line.split("=", 1)[1] for line in out.splitlines() if line.startswith(name + "=")), "")


def _bridge_to_local_stack() -> None:
    """Runs before the app modules are imported: they read these settings at import time."""
    os.environ.setdefault("AGENCY_OS_LOCAL_MODE", "1")
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:3002")
    os.environ.setdefault("CLAUDE_PROVIDER_URL", "http://127.0.0.1:3111")
    for name in ("CLAUDE_PROVIDER_SECRET", "SUPABASE_KEY"):
        if not os.environ.get(name):
            os.environ[name] = _container_env(name)


def _pool_questions() -> dict[str, tuple[str, str]]:
    """The chat's starter questions by qid, the ones every page offers first: (question, page it is asked from)."""
    import unicodedata

    from core.chat.starter_questions import STARTER_QUESTIONS

    def slug(text: str) -> str:
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
        return "_".join([word for word in "".join(c if c.isalnum() else " " for c in plain).split()
                         if len(word) > 2][:5])

    ordered = sorted(STARTER_QUESTIONS, key=lambda starter: bool(starter.pages))
    return {f"q{number:02d}_{slug(starter.text['es'])}": (starter.text["es"],
                                                          starter.pages[0] if starter.pages else HOME_PAGE)
            for number, starter in enumerate(ordered, start=1)}


def _opening_documents() -> list[dict]:
    """What the panel sends with the turn that opens a conversation when no analysis is shared."""
    from core.chat import account_directory

    directory = account_directory.directory_document()
    return [directory] if directory else []


def _home_page_turn():
    """The Amazon Ads scope and note a new conversation on the home page is sent with."""
    from core.chat import ads_scope, app_chat
    from core.integrations.store import open_stores

    _, connections, _ = open_stores()
    vehicles = ads_scope.build_vehicles(connections.accounts_by_integration_slug().get(ads_scope.SLUG, []),
                                        connections.by_integration_slug().get(ads_scope.SLUG, []))
    vehicle = ads_scope.pick_vehicle(vehicles, None)
    if vehicle is None:
        sys.exit("No hay cuentas de Amazon Ads conectadas en el stack local.")
    scope = {"account_id": vehicle.account_id, "profile_id": vehicle.profile_id,
             "requested_by": "chat-latency-battery", "dynamic": True}
    return scope, app_chat.turn_note(HOME_PAGE, {}, {})


def _run_turn(question: str, effort: str, scope: dict, note: str, documents: list | None = None,
              session_id: str | None = None) -> dict:
    from ai import runtime

    started = time.time()
    events, reply, error = [], None, None
    try:
        for event in runtime.stream_followup("orchestrator", session_id, question, ads_scope=scope,
                                             context_docs=list(documents or []), note=note, thread=[],
                                             effort=effort):
            at_s = round(time.time() - started, 3)
            if event["type"] != "reply":
                events.append({**event, "at_s": at_s})
                continue
            answer = event["reply"]
            reply = {"text": answer.text, "tool_calls": list(answer.tool_calls), "session_id": answer.session_id,
                     "failed_tools": list(answer.failed_tools), "model": answer.model,
                     "cost_usd": answer.cost_usd, "at_s": at_s}
    except Exception as e:  # noqa: BLE001 — a failed turn is a result too
        error = f"{type(e).__name__}: {e}"
    return {"question": question, "effort": effort, "started_ts": started,
            "wall_s": round(time.time() - started, 3), "note": note, "ads_scope": scope,
            "events": events, "reply": reply, "error": error}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out_dir", type=pathlib.Path)
    parser.add_argument("--efforts", default="xhigh,low")
    parser.add_argument("--only", default="", help="qids, or qid prefixes with --pool (q02,q12)")
    parser.add_argument("--pool", action="store_true", help="the chat's starter questions instead of QUESTIONS")
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    if out_dir.is_relative_to(REPO):
        sys.exit(f"{out_dir} está dentro del repo: las respuestas traen datos de clientes.")

    warnings.filterwarnings("ignore")
    sys.path.insert(0, str(REPO))
    _bridge_to_local_stack()
    scope, _ = _home_page_turn()
    from core.chat import app_chat

    questions = _pool_questions() if args.pool else {qid: (text, HOME_PAGE) for qid, text in QUESTIONS.items()}
    wanted = [prefix for prefix in args.only.split(",") if prefix]
    selected = [qid for qid in questions if not wanted or any(qid.startswith(prefix) for prefix in wanted)]
    if not selected:
        sys.exit(f"Ninguna pregunta coincide con {args.only}")
    documents = _opening_documents()

    out_dir.mkdir(parents=True, exist_ok=True)
    for qid in selected:
        question, page = questions[qid]
        note = app_chat.turn_note(page, {}, {})
        for effort in args.efforts.split(","):
            target = out_dir / f"{qid}__{effort}.json"
            if target.exists():
                print(f"{target.name}: ya existe, se saltea")
                continue
            run = {"qid": qid, "page": page, **_run_turn(question, effort, scope, note, documents)}
            target.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{qid} {effort}: {run['wall_s']} s, {len(run['events'])} eventos, error={run['error']}", flush=True)
            follow_up = next((text for prefix, text in POOL_FOLLOW_UPS.items() if qid.startswith(prefix)), None)
            if args.pool and follow_up and run["reply"]:
                second = {"qid": f"{qid}_b", "page": page,
                          **_run_turn(follow_up, effort, scope, note, session_id=run["reply"]["session_id"])}
                (out_dir / f"{qid}_b__{effort}.json").write_text(json.dumps(second, ensure_ascii=False, indent=1),
                                                                 encoding="utf-8")
                print(f"{qid}_b {effort}: {second['wall_s']} s, error={second['error']}", flush=True)


if __name__ == "__main__":
    main()
