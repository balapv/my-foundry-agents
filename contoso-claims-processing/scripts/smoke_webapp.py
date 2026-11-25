"""Live smoke test of the Contoso Claims Review application (Phase 3).

Drives the application's own HTTP API (the same endpoints the browser uses) against the deployed
Foundry agent, then scores each turn with the Phase 2 evaluation checks in
evaluation/test_cases.json. Every run is recorded, including failures; nothing is retried.

Default plan (the Phase 3 smoke set):
  hero x3   CLM-10482 initial review (A1) + "Show me why you flagged the headlamp." (A2) in the
            same conversation
  B11  x2   CLM-10471 different unsupported repair item
  B12  x2   CLM-10485 ambiguous image evidence
  B13  x2   CLM-10467 unusual repair item that is supported

Results (git-ignored) are written to evaluation/results/webapp-smoke/.

Usage:
  python scripts/smoke_webapp.py
  python scripts/smoke_webapp.py --hero 1 --repeat 0      # one hero conversation only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import run_evaluation  # noqa: E402  (adds agent/ and scripts/ to sys.path)
from fastapi.testclient import TestClient  # noqa: E402

import common  # noqa: E402
from webapp.backend import errors  # noqa: E402
from webapp.backend.app import create_app  # noqa: E402
from webapp.backend.config import load_dotenv_file, load_settings  # noqa: E402

RESULTS_DIR = ROOT / "evaluation" / "results" / "webapp-smoke"
OTHER_CASES = ("B11", "B12", "B13")


class Capture(logging.Handler):
    """Keeps the application's structured turn events (server-side only)."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.events: dict[tuple[str, str], dict[str, Any]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, "fields", None)
        if record.getMessage() in ("review.turn_completed", "review.turn_failed") and fields:
            self.events[(fields.get("session", ""), fields.get("turn", ""))] = {"event": record.getMessage(), **fields}


def wait_for_turn(client: TestClient, session_id: str, turn_id: str, limit: float) -> dict[str, Any]:
    deadline = time.monotonic() + limit
    while True:
        turn = client.get(f"/api/reviews/{session_id}/turns/{turn_id}").json()
        if turn["status"] != "running" or time.monotonic() > deadline:
            return turn
        time.sleep(1)


def run_conversation(client: TestClient, capture: Capture, traces: dict[str, Any], claim_id: str,
                     prompts: list[str], limit: float) -> dict[str, Any]:
    created = client.post("/api/reviews", json={"claimId": claim_id})
    created.raise_for_status()
    session_id = created.json()["sessionId"]
    log_id = hashlib.sha256(session_id.encode()).hexdigest()[:10]
    turns = []
    for prompt in prompts:
        sent = client.post(f"/api/reviews/{session_id}/messages", json={"text": prompt})
        if sent.status_code != 202:
            turns.append({"prompt": prompt, "answer": None, "error": f"HTTP {sent.status_code}"})
            break
        turn = wait_for_turn(client, session_id, sent.json()["turnId"], limit)
        event = capture.events.get((log_id, turn["turnId"]), {})
        trace = traces.get(event.get("responseId", ""), {})
        turns.append({
            "prompt": prompt,
            "status": turn["status"],
            "answer": turn["answer"],
            "error": turn["error"],
            "latencySeconds": turn["elapsedSeconds"],
            "stagesSeen": turn["stagesSeen"],
            "evidenceAttached": turn["evidenceAttached"],
            "conversationId": event.get("conversationId"),
            "responseId": event.get("responseId"),
            "agent": f"{event.get('agent')} v{event.get('agentVersion')}",
            "trace": trace,
            "fileSearchFiles": event.get("fileSearchFiles", []),
            "failureDetail": event.get("detail"),
        })
        if turn["status"] != "completed":
            break
    client.delete(f"/api/reviews/{session_id}")
    conversations = {t.get("conversationId") for t in turns if t.get("conversationId")}
    return {"claimId": claim_id, "turns": turns, "sameConversation": len(conversations) <= 1,
            "evidenceResent": any(t.get("evidenceAttached") for t in turns[1:])}


def summarize_turn(turn: dict[str, Any], score: dict[str, Any] | None) -> dict[str, Any]:
    trace = turn.get("trace") or {}
    return {
        "passed": bool(score and score["passed"]),
        "latencySeconds": turn.get("latencySeconds"),
        "apiCalls": [c["operation"].removeprefix("claims_operations_") + (f" ({c['errorCode']})" if c.get("errorCode") else "")
                     for c in trace.get("apiCalls", [])],
        "repeatedApiCalls": trace.get("repeatedApiCalls", []),
        "fileSearches": len(trace.get("fileSearches", [])),
        "fileSearchFiles": turn.get("fileSearchFiles", []),
        "evidenceAttached": turn.get("evidenceAttached"),
        "failedChecks": [f"{c['check']}: {c['detail']}" for c in (score or {}).get("checks", []) if not c["passed"]],
        "error": turn.get("error"),
    }


def write_markdown(path: Path, results: list[dict[str, Any]]) -> None:
    lines = ["# Claims Review application live smoke", "",
             "| Run | Case | Pass | Latency (s) | API calls | File Search | Evidence attached | Failed checks / errors |",
             "|---|---|---|---|---|---|---|---|"]
    for result in results:
        for item in result["scored"]:
            s = item["summary"]
            attached = s["evidenceAttached"]
            attached_text = f"{attached['documents']} PDFs + {attached['photos']} photos" if attached else "none (follow-up)"
            problems = "; ".join(s["failedChecks"] + ([s["error"]["code"]] if s["error"] else [])) or "-"
            lines.append(f"| {result['runId']} | {item['case']} | {'PASS' if s['passed'] else 'FAIL'} | {s['latencySeconds']} | "
                         f"{', '.join(s['apiCalls']) or 'none'} | {s['fileSearches']} ({', '.join(s['fileSearchFiles']) or '-'}) | "
                         f"{attached_text} | {problems.replace('|', '/')} |")
    lines.append("")
    for result in results:
        lines += [f"## {result['runId']} ({result['claimId']})", "",
                  f"Same conversation: {result['sameConversation']}; evidence resent on follow-up: {result['evidenceResent']}", ""]
        for index, turn in enumerate(result["turns"], 1):
            lines += [f"### Turn {index}: {turn['prompt']}", "", turn.get("answer") or f"_No answer: {turn.get('error')}_", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    common.configure_console()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hero", type=int, default=3, help="Hero conversations (initial review + headlamp follow-up).")
    parser.add_argument("--repeat", type=int, default=2, help="Runs of each of B11, B12 and B13.")
    args = parser.parse_args(argv)

    spec = run_evaluation.load_spec()
    cases = {case["id"]: case for case in spec["cases"]}
    plan = [(f"hero-{i}", "hero", ["A1", "A2"]) for i in range(1, args.hero + 1)]
    plan += [(f"{case_id.lower()}-{i}", cases[case_id]["run"], [case_id])
             for case_id in OTHER_CASES for i in range(1, args.repeat + 1)]

    traces: dict[str, Any] = {}
    original_trace = common.trace

    def capturing_trace(response: Any) -> dict[str, Any]:
        details = original_trace(response)
        traces[details["responseId"]] = details
        return details

    common.trace = capturing_trace
    capture = Capture()
    load_dotenv_file()
    settings = load_settings()
    client = TestClient(create_app(settings))  # background turns, exactly as served to the browser
    logging.getLogger(errors.LOGGER_NAME).addHandler(capture)
    limit = settings.turn_timeout_seconds + 60

    results = []
    for run_id, spec_run, case_ids in plan:
        run = spec["runs"][spec_run]
        prompts = run["prompts"][: max(cases[c]["turn"] for c in case_ids) + 1]
        print(f"\n### {run_id}: {run['claimId']} ({', '.join(case_ids)})", flush=True)
        try:
            result = run_conversation(client, capture, traces, run["claimId"], prompts, limit)
        except Exception as exc:  # record the failure and continue with the next run
            result = {"claimId": run["claimId"], "turns": [], "sameConversation": None, "evidenceResent": None,
                      "error": f"{type(exc).__name__}: {exc}"}
        result["runId"] = run_id
        result["scored"] = []
        for case_id in case_ids:
            score = run_evaluation.score_case(cases[case_id], result, spec["globalForbid"])
            turn = result["turns"][cases[case_id]["turn"]] if cases[case_id]["turn"] < len(result["turns"]) else {}
            summary = summarize_turn(turn, score)
            result["scored"].append({"case": case_id, "score": score, "summary": summary})
            print(f"  {case_id} {'PASS' if summary['passed'] else 'FAIL'}  {summary['latencySeconds']}s  "
                  f"api={summary['apiCalls']}  fileSearches={summary['fileSearches']}  attached={summary['evidenceAttached']}",
                  flush=True)
            for problem in summary["failedChecks"]:
                print(f"     x {problem}", flush=True)
        results.append(result)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    (RESULTS_DIR / f"smoke-{stamp}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(RESULTS_DIR / f"smoke-{stamp}.md", results)
    scored = [item for result in results for item in result["scored"]]
    passed = sum(item["summary"]["passed"] for item in scored)
    print(f"\n{passed}/{len(scored)} scored turns passed. Results: evaluation/results/webapp-smoke/smoke-{stamp}.(json|md)")
    return 0 if passed == len(scored) else 1


if __name__ == "__main__":
    raise SystemExit(main())
