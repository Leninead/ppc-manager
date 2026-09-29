"""Splits each chat latency battery turn into steps: provider setup, model calls and tool calls.

Reads the turns scripts/chat_latency_battery.py saved in RUN_DIR and joins three sources:
- this app's AI log (data/ai/log), for the provider request id;
- the provider's container log, for when each MCP session opened and when the CLI launched;
- the provider's Claude Code transcript of the session, for every model call and tool result.

For each turn it writes <turn>.timeline.json next to it, plus summary.json, and prints one row
per turn. Run it on the same machine as the battery, before the provider container is recreated:
the transcripts live inside the container.

Usage:
    python scripts/chat_latency_timeline.py RUN_DIR
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys

APP_LOG = pathlib.Path(__file__).resolve().parent.parent / "data" / "ai" / "log"
PROVIDER = "capybaras-ai-provider"
ANSWER_TOOL = "StructuredOutput"


def _epoch(iso: str) -> float:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _app_log_entry(started_ts: float) -> dict:
    for path in sorted(APP_LOG.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("tag") == "orchestrator-chat" and abs(entry["ts"] - started_ts) < 5:
                return entry
    return {}


def _provider_setup(request_id: str, started_ts: float) -> dict:
    """Seconds from the question to each setup step the provider logs for this request."""
    since = dt.datetime.fromtimestamp(started_ts - 5, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = subprocess.run(["docker", "logs", "--timestamps", "--since", since, PROVIDER],
                         capture_output=True, text=True).stdout
    # The Amazon Ads session is held across requests: ready is when this request got it, open or already open.
    steps = {"amazon_ads_open": "amazon_ads.session_ready", "mcp_session_opened": "mcp.session_opened",
             "cli_launch": "Using bundled Claude Code CLI"}
    found = {}
    for line in log.splitlines():
        if request_id not in line:
            continue
        stamp = line.split(" ", 1)[0]
        for step, marker in steps.items():
            if marker in line and step not in found:
                found[step] = round(_epoch(stamp[:26] + "Z") - started_ts, 2)
    return found


def _transcript(session_id: str) -> list[dict]:
    path = subprocess.run(["docker", "exec", PROVIDER, "sh", "-c",
                           f"find /home/provider/.claude/projects -name '{session_id}.jsonl' | head -1"],
                          capture_output=True, text=True).stdout.strip()
    if not path:
        return []
    raw = subprocess.run(["docker", "exec", PROVIDER, "cat", path], capture_output=True, text=True).stdout
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _result_chars(block: dict) -> int:
    content = block.get("content")
    if isinstance(content, list):
        return sum(len(part.get("text", "")) if isinstance(part, dict) else len(str(part)) for part in content)
    return len(str(content or ""))


def _steps(transcript: list[dict], started_ts: float, ended_ts: float) -> dict:
    """Model calls (one per API message, whatever blocks it streamed) and tool calls, in seconds from the question."""
    # The turns of one chat share its session: only what happened while this turn ran belongs to it.
    stamped = [entry for entry in transcript
               if entry.get("timestamp") and started_ts - 1 <= _epoch(entry["timestamp"]) <= ended_ts + 1]
    calls: dict[str, dict] = {}
    tools, asked = [], {}
    last_input = None
    for entry in stamped:
        at = _epoch(entry["timestamp"])
        message = entry.get("message") or {}
        blocks = message.get("content") if isinstance(message.get("content"), list) else []
        if entry["type"] == "user":
            for block in blocks:
                if block.get("type") != "tool_result":
                    continue
                use = asked.pop(block.get("tool_use_id"), {})
                tools.append({"name": use.get("name", "?"), "input": use.get("input"),
                              "latency_s": round(at - use["at"], 2) if use else None,
                              "result_chars": _result_chars(block), "is_error": bool(block.get("is_error"))})
            last_input = at
        elif entry["type"] == "assistant":
            call = calls.setdefault(message.get("id") or entry.get("uuid"),
                                    {"start": last_input, "end": at, "usage": {}, "tool_uses": []})
            call["end"] = at
            call["usage"] = message.get("usage") or call["usage"]
            for block in blocks:
                if block.get("type") == "tool_use":
                    call["tool_uses"].append(block.get("name"))
                    asked[block.get("id")] = {"name": block.get("name"), "input": block.get("input"), "at": at}
    model_calls = []
    for call in calls.values():
        usage = call["usage"]
        model_calls.append({
            "latency_s": round(call["end"] - call["start"], 2) if call["start"] else None,
            "prompt_tokens": sum(usage.get(k) or 0 for k in
                                 ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            "cache_read": usage.get("cache_read_input_tokens"), "cache_write": usage.get("cache_creation_input_tokens"),
            "output_tokens": usage.get("output_tokens"), "tool_uses": call["tool_uses"]})
    return {"cli_ready_s": round(_epoch(stamped[0]["timestamp"]) - started_ts, 2) if stamped else None,
            "model_calls": model_calls, "tools": tools}


def _summary_row(name: str, turn: dict) -> dict:
    calls = turn.get("model_calls", [])
    data_tools = [tool for tool in turn.get("tools", []) if tool["name"] != ANSWER_TOOL]
    return {"turn": name, "wall_s": turn["wall_s"], "setup": turn["provider_setup"],
            "cli_ready_s": turn.get("cli_ready_s"), "model_calls": len(calls),
            "model_s": round(sum(call["latency_s"] or 0 for call in calls), 1),
            "last_call_s": calls[-1]["latency_s"] if calls else None,
            "tool_calls": len(data_tools), "tool_s": round(sum(tool["latency_s"] or 0 for tool in data_tools), 1),
            "tool_result_chars": sum(tool["result_chars"] for tool in data_tools),
            "output_tokens": sum(call["output_tokens"] or 0 for call in calls),
            "max_prompt_tokens": max((call["prompt_tokens"] for call in calls), default=0),
            "cost_usd": turn["cost_usd"], "error": turn["error"]}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    run_dir = pathlib.Path(sys.argv[1])
    rows = []
    for path in sorted(run_dir.glob("q*__*.json")):
        if path.name.endswith(".timeline.json"):
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        entry = _app_log_entry(run["started_ts"])
        response = entry.get("response") or {}
        session_id = (run.get("reply") or {}).get("session_id") or response.get("session_id")
        turn = {"qid": run["qid"], "effort": run["effort"], "question": run["question"], "wall_s": run["wall_s"],
                "error": run["error"], "request_id": entry.get("request_id"), "session_id": session_id,
                "sdk_duration_s": (response.get("duration_ms") or 0) / 1000, "num_turns": response.get("num_turns"),
                "cost_usd": response.get("total_cost_usd"), "answer": (run.get("reply") or {}).get("text"),
                "provider_setup": _provider_setup(entry["request_id"], run["started_ts"]) if entry else {},
                **(_steps(_transcript(session_id), run["started_ts"], run["started_ts"] + run["wall_s"]) if session_id else {})}
        (run_dir / f"{path.stem}.timeline.json").write_text(json.dumps(turn, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
        rows.append(_summary_row(path.stem, turn))
    (run_dir / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'turno':28s} {'total':>6} {'ads':>5} {'cli':>5} {'modelo':>6} {'última':>6} "
          f"{'tools':>5} {'t_s':>5} {'k chars':>7} {'salida':>7} {'ctx máx':>7}")
    for row in rows:
        print(f"{row['turn']:28s} {row['wall_s']:>6.0f} {row['setup'].get('amazon_ads_open') or 0:>5.1f} "
              f"{row['cli_ready_s'] or 0:>5.1f} {row['model_s']:>6.0f} {row['last_call_s'] or 0:>6.0f} "
              f"{row['tool_calls']:>5} {row['tool_s']:>5.0f} {row['tool_result_chars'] / 1000:>7.0f} "
              f"{row['output_tokens']:>7} {row['max_prompt_tokens'] / 1000:>6.0f}k")


if __name__ == "__main__":
    main()
