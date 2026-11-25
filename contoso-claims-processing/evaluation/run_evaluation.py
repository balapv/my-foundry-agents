"""Behavioral evaluation of the Contoso Claims Review agent (Phase 2).

Cases live in evaluation/test_cases.json. Each case names a "run" (a claim conversation) and the
turn to score. Each run is executed once and scored by every case that uses it. Scoring is
deterministic: regular-expression checks over the answer and checks over the recorded tool trace.
An optional model judge (--judge) adds a secondary opinion and never decides pass/fail.

Expectations stay in this folder; they are never sent to the agent.

Usage:
  python evaluation/run_evaluation.py --list
  python evaluation/run_evaluation.py --all
  python evaluation/run_evaluation.py --case B11 --case B13
  python evaluation/run_evaluation.py --all --reuse hero=evaluation/results/hero-run-2.json
  python evaluation/run_evaluation.py --rescore evaluation/results/eval-<timestamp>.json

--all runs everything live, including the fault-injection runs: the "api-outage" run switches the
deployed API into simulated outage (scripts/deploy_tools.py --set-outage) and always switches it
back; the "no-knowledge" run creates a temporary agent with an empty vector store and deletes it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402

CASES_FILE = ROOT / "evaluation" / "test_cases.json"
RESULTS_DIR = ROOT / "evaluation" / "results"
SECTION_NAMES = ("Recommendation", "Coverage", "What checks out", "Needs review", "Why", "Next step", "Sources")
CHECK_KEYS = {"apiCalls", "apiErrorObserved", "fileSearch", "sections", "require", "forbid", "requireInSection", "forbidInSection"}
RUN_KEYS = {"claimId", "prompts", "evidence", "outage", "variant"}
VARIANTS = {"default", "empty-knowledge"}
FLAGS = re.IGNORECASE
TYPOGRAPHIC_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def load_spec(path: Path = CASES_FILE) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_spec(spec)
    if problems:
        raise ValueError("Invalid evaluation cases:\n  " + "\n  ".join(problems))
    return spec


def validate_spec(spec: dict[str, Any]) -> list[str]:
    """Structural validation: every case resolves to a run and every pattern compiles."""
    problems: list[str] = []
    runs = spec.get("runs", {})
    for run_id, run in runs.items():
        if set(run) - RUN_KEYS:
            problems.append(f"run {run_id}: unknown keys {sorted(set(run) - RUN_KEYS)}")
        if not re.fullmatch(r"CLM-\d{5}", run.get("claimId", "")):
            problems.append(f"run {run_id}: invalid claimId")
        if not run.get("prompts") or not all(isinstance(p, str) and p.strip() for p in run["prompts"]):
            problems.append(f"run {run_id}: prompts must be non-empty strings")
        if run.get("variant", "default") not in VARIANTS:
            problems.append(f"run {run_id}: unknown variant {run.get('variant')}")
    ids = [case.get("id") for case in spec.get("cases", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate case ids")
    for case in spec.get("cases", []):
        cid = case.get("id")
        run = runs.get(case.get("run"))
        if run is None:
            problems.append(f"case {cid}: unknown run {case.get('run')}")
        elif not 0 <= case.get("turn", -1) < len(run["prompts"]):
            problems.append(f"case {cid}: turn out of range")
        if not case.get("expected"):
            problems.append(f"case {cid}: expected behaviors missing")
        checks = case.get("checks") or {}
        if not checks:
            problems.append(f"case {cid}: no checks")
        if set(checks) - CHECK_KEYS:
            problems.append(f"case {cid}: unknown check keys {sorted(set(checks) - CHECK_KEYS)}")
        for rule in _rules(checks) + spec.get("globalForbid", []):
            for key in ("pattern", "unless"):
                if key in rule:
                    try:
                        re.compile(rule[key], FLAGS)
                    except re.error as exc:
                        problems.append(f"case {cid}: rule {rule.get('name')!r} {key} does not compile: {exc}")
            if rule.get("section") is not None and rule["section"] not in SECTION_NAMES:
                problems.append(f"case {cid}: unknown section {rule['section']!r}")
    return problems


def _rules(checks: dict[str, Any]) -> list[dict[str, Any]]:
    return [rule for key in ("require", "forbid", "requireInSection", "forbidInSection") for rule in checks.get(key, [])]


# ---------------------------------------------------------------------------
# Deterministic scoring
# ---------------------------------------------------------------------------


def split_sections(answer: str) -> dict[str, str]:
    """Map each '## Heading' of the agent's response format to its body."""
    sections: dict[str, str] = {}
    current = None
    for line in answer.splitlines():
        heading = re.match(r"^\s*#{1,4}\s*(.+?)\s*:?\s*$", line)
        if heading and heading.group(1).strip("* ").lower() in {name.lower() for name in SECTION_NAMES}:
            current = next(n for n in SECTION_NAMES if n.lower() == heading.group(1).strip("* ").lower())
            sections[current] = ""
        elif current:
            sections[current] += line + "\n"
    return sections


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def offending(text: str, rule: dict[str, Any]) -> list[str]:
    """Sentences matching a forbidden pattern that are not excused by the rule's 'unless' pattern."""
    hits = []
    for sentence in sentences(text):
        if re.search(rule["pattern"], sentence, FLAGS):
            if rule.get("unless") and re.search(rule["unless"], sentence, FLAGS):
                continue
            hits.append(sentence.strip())
    return hits


def score_case(case: dict[str, Any], run: dict[str, Any] | None, global_forbid: list[dict[str, Any]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    turn = (run or {}).get("turns", [])[case["turn"]] if run and case["turn"] < len(run.get("turns", [])) else None
    if turn is None or not turn.get("answer"):
        record("turn completed", False, (turn or {}).get("error") or "turn was not executed")
        return {"id": case["id"], "passed": False, "checks": checks}

    answer = re.sub(r"\*+|(?<!\w)_+|_+(?!\w)", "", turn["answer"])  # markdown emphasis would split phrases
    answer = answer.translate(TYPOGRAPHIC_QUOTES)  # so "can’t" matches patterns written with "can't"
    trace = turn.get("trace") or {}
    spec = case["checks"]
    operations = [call["operation"] for call in trace.get("apiCalls", [])]
    for operation in spec.get("apiCalls", []):
        # The runtime names calls <tool name>_<operationId>, e.g. claims_operations_get_claim.
        called = any(name == operation or name.endswith("_" + operation) for name in operations)
        record(f"called {operation}", called, ", ".join(operations) or "no API calls")
    if spec.get("apiErrorObserved"):
        codes = [c["errorCode"] for c in trace.get("apiCalls", []) if c.get("errorCode")]
        record("API error observed in trace", bool(codes), ", ".join(codes) or "no tool errors")
    if spec.get("fileSearch"):
        record("searched company guidance", bool(trace.get("fileSearches")), f"{len(trace.get('fileSearches', []))} searches")

    sections = split_sections(answer)
    if spec.get("sections"):
        missing = [name for name in SECTION_NAMES if name not in sections]
        record("response format sections", not missing, f"missing: {missing}" if missing else "all present")

    for rule in spec.get("require", []):
        match = re.search(rule["pattern"], answer, FLAGS)
        record(rule["name"], match, f"matched {match.group(0)!r}" if match else "no match")
    for rule in spec.get("requireInSection", []):
        body = sections.get(rule["section"], "")
        match = re.search(rule["pattern"], body, FLAGS)
        record(rule["name"], match, f"matched {match.group(0)!r}" if match else f"no match in {rule['section']}")
    for rule in spec.get("forbidInSection", []):
        hits = offending(sections.get(rule["section"], ""), rule)
        record(rule["name"], not hits, "; ".join(hits)[:400])
    for rule in spec.get("forbid", []) + global_forbid:
        hits = offending(answer, rule)
        record(rule["name"], not hits, "; ".join(hits)[:400])

    return {"id": case["id"], "passed": all(c["passed"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# Optional model judge (secondary signal only)
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are reviewing an insurance claims-review assistant's answer for a test.
For each expected behavior, decide whether the answer demonstrates it. Judge meaning, not wording.
Return only JSON: {{"items": [{{"expected": "...", "met": true|false, "reason": "short"}}]}}

Adjuster request: {prompt}

Expected behaviors:
{expected}

Answer:
{answer}
"""


def judge_case(oai, model: str, case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    turn = run["turns"][case["turn"]]
    prompt = JUDGE_PROMPT.format(prompt=turn["prompt"], expected="\n".join(f"- {e}" for e in case["expected"]),
                                 answer=turn["answer"])
    try:
        response = oai.responses.create(model=model, input=prompt, text={"format": {"type": "json_object"}})
        items = json.loads(response.output_text)["items"]
        return {"met": sum(bool(i.get("met")) for i in items), "total": len(items), "items": items}
    except Exception as exc:  # the judge is advisory; never fail the evaluation because of it
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Live execution
# ---------------------------------------------------------------------------


def execute_run(project, oai, config: dict[str, Any], run_id: str, run: dict[str, Any]) -> dict[str, Any]:
    import create_agent
    import deploy_tools
    from run_claim_review import resolve_version, run_conversation

    name = config["agentName"]
    temporary_agent = None
    outage = run.get("outage")
    try:
        if run.get("variant") == "empty-knowledge":
            temporary_agent = f"{name}-noknowledge"
            if create_agent.main(["--name", temporary_agent, "--empty-knowledge"]) != 0:
                raise RuntimeError("could not create the empty-knowledge agent")
            name = temporary_agent
        if outage:
            deploy_tools.main(["--set-outage", outage])
        version = resolve_version(project, name, None)
        print(f"\n### Run {run_id}: {run['claimId']} on {name} v{version}")
        return run_conversation(oai, name, version, run["claimId"], run["prompts"],
                                run.get("evidence", True), config["imageDetail"])
    finally:
        if outage:
            deploy_tools.main(["--set-outage", ""])
        if temporary_agent:
            create_agent.main(["--name", temporary_agent, "--delete"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Run and score every case.")
    selection.add_argument("--case", action="append", help="Case id to run and score (repeatable).")
    selection.add_argument("--rescore", metavar="PATH", help="Re-score a saved results file without calling Foundry.")
    selection.add_argument("--list", action="store_true", help="List the cases and exit.")
    parser.add_argument("--reuse", action="append", default=[], metavar="RUN=PATH",
                        help="Use a saved run_claim_review.py transcript for RUN instead of calling Foundry.")
    parser.add_argument("--judge", action="store_true", help="Add the advisory model-judge signal (extra model calls).")
    parser.add_argument("--output", metavar="PATH", help="Results file (default evaluation/results/eval-<UTC timestamp>.json).")
    return parser.parse_args(argv)


def print_summary(scores: list[dict[str, Any]], cases: dict[str, dict[str, Any]], judged: dict[str, Any]) -> None:
    print("\n" + "=" * 100)
    for score in scores:
        failed = [c for c in score["checks"] if not c["passed"]]
        judge = judged.get(score["id"], {})
        judge_note = f"  judge {judge['met']}/{judge['total']}" if "met" in judge else ""
        print(f"{score['id']:<4} {'PASS' if score['passed'] else 'FAIL'}  {cases[score['id']]['title']}{judge_note}")
        for check in failed:
            print(f"       x {check['check']}: {check['detail']}")
    passed = sum(s["passed"] for s in scores)
    print("=" * 100)
    print(f"{passed}/{len(scores)} cases passed")


def main(argv: list[str] | None = None) -> int:
    common.configure_console()
    args = parse_args(argv)
    spec = load_spec()
    cases = {case["id"]: case for case in spec["cases"]}
    if args.list:
        for case in spec["cases"]:
            run = spec["runs"][case["run"]]
            print(f"{case['id']:<4} {case['title']:<50} {run['claimId']}  run={case['run']} turn={case['turn']}")
        return 0

    if args.rescore:
        saved = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
        runs = saved["runs"]
        selected = [cases[s["id"]] for s in saved["scores"] if s["id"] in cases]
        judged = saved.get("judge", {})
    else:
        unknown = [c for c in args.case or [] if c not in cases]
        if unknown:
            print(f"Unknown case(s): {unknown}", file=sys.stderr)
            return 2
        selected = spec["cases"] if args.all else [cases[c] for c in args.case]
        reuse = dict(item.split("=", 1) for item in args.reuse)
        runs = {run_id: json.loads(Path(path).read_text(encoding="utf-8")) for run_id, path in reuse.items()}
        needed = [run_id for run_id in dict.fromkeys(c["run"] for c in selected) if run_id not in runs]
        judged = {}
        if needed or args.judge:
            config = common.load_config()
            settings = common.load_settings(require_tools_url=False)
            project = common.project_client(settings)
            oai = project.get_openai_client()
            for run_id in needed:
                started = time.perf_counter()
                try:
                    runs[run_id] = execute_run(project, oai, config, run_id, spec["runs"][run_id])
                except (Exception, SystemExit) as exc:  # score the run as failed; keep going
                    runs[run_id] = {"turns": [], "error": f"{type(exc).__name__}: {exc}"}
                runs[run_id]["wallSeconds"] = round(time.perf_counter() - started, 1)
            if args.judge:
                for case in selected:
                    run = runs.get(case["run"])
                    if run and case["turn"] < len(run.get("turns", [])) and run["turns"][case["turn"]].get("answer"):
                        judged[case["id"]] = judge_case(oai, settings["FOUNDRY_MODEL_DEPLOYMENT_NAME"], case, run)

    scores = [score_case(case, runs.get(case["run"]), spec["globalForbid"]) for case in selected]
    print_summary(scores, cases, judged)
    output = Path(args.output) if args.output else RESULTS_DIR / f"eval-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"scores": scores, "judge": judged, "runs": runs}, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"Results: {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    return 0 if all(s["passed"] for s in scores) else 1


if __name__ == "__main__":
    raise SystemExit(main())
