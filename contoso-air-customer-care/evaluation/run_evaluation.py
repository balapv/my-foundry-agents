"""Evaluate the Contoso Air Customer Care agent against the scenario test cases.

Each case in evaluation/test_cases.json runs as a fresh Foundry conversation for its
signed-in customer (the same authenticated-session pattern the web app uses). The
runner then scores the result in two ways:

1. Deterministic checks: required tool usage, tool arguments, and lenient text
   checks such as "recommends CT226" or "does not claim a completed booking".
2. An LLM judge (the judge model deployment, default: the agent's model) that
   scores the seven criteria in test_cases.json against the tool outputs and
   the approved policy text.

Usage (from the repository root):

    python evaluation/run_evaluation.py                 # all runnable cases
    python evaluation/run_evaluation.py --case A1 --case E1
    python evaluation/run_evaluation.py --no-judge      # deterministic checks only
    python evaluation/run_evaluation.py --list          # show cases without running
    python evaluation/run_evaluation.py --cloud         # also submit a Foundry cloud evaluation

Results are written to evaluation/results/ (git-ignored). The process exits with
code 1 when any case fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.foundry_common import (  # noqa: E402
    ConfigError,
    ToolCall,
    TurnResult,
    ask_agent,
    clean_customer_text,
    configure_console,
    create_conversation,
    get_settings,
    project_client,
    resolve_agent_version,
    session_context_text,
)

CASES_FILE = EVAL_DIR / "test_cases.json"
RESULTS_DIR = EVAL_DIR / "results"
POLICY_DIR = REPO_ROOT / "knowledge" / "source"

CRITERIA = (
    "task_completion",
    "groundedness",
    "tool_correctness",
    "policy_adherence",
    "recommendation_quality",
    "hallucination_avoidance",
    "communication_quality",
)
CRITERIA_ABBREVIATIONS = ("TC", "GR", "TO", "PA", "RQ", "HA", "CQ")
# Minimum judge score (1-5) per criterion. Truthfulness criteria require 4.
JUDGE_THRESHOLDS = {name: 3 for name in CRITERIA} | {
    "groundedness": 4,
    "policy_adherence": 4,
    "hallucination_avoidance": 4,
}
KNOWN_TOOL_CATEGORIES = {"reservation", "flight_status", "flight_search", "knowledge"}

# Phrases that claim an action was completed. The agent has no action tools, so any of
# these is a false claim. Patterns are deliberately narrow to avoid flagging negations
# such as "your seats are not held".
GUARDS: dict[str, list[str]] = {
    "no_completed_action_claim": [
        r"\b(?:I|we)(?:'ve| have)\s+(?:now\s+|successfully\s+|already\s+|gone ahead and\s+)?"
        r"(?:re)?(?:booked|changed|moved|switched|held|reserved|secured|transferred|processed|issued|upgraded|placed)\b",
        r"\byou(?:'re| are)\s+(?:now|all set|successfully)\b[^.\n]{0,30}\b(?:booked|rebooked|confirmed)\b",
        r"\b(?:has|have) been (?:successfully )?(?:re)?booked\b",
        r"\b(?:has|have) been (?:moved|switched|transferred) to (?:flight )?CT\s?\d{3}",
        r"(?<!\bno )\bseats? (?:is|are|has been|have been) (?:now )?(?:held|reserved|secured|locked in)\b",
    ],
}


# --------------------------------------------------------------------------- loading cases


class CaseError(ValueError):
    """The test-case file is malformed."""


def load_cases(path: Path = CASES_FILE) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        raise CaseError(f"{path} must contain a non-empty 'cases' list")
    seen: set[str] = set()
    for case in cases:
        validate_case(case)
        if case["id"] in seen:
            raise CaseError(f"Duplicate case id {case['id']}")
        seen.add(case["id"])
    return cases


def validate_case(case: dict[str, Any]) -> None:
    case_id = case.get("id") or "<missing id>"
    for key in ("id", "title", "category", "customerId", "turns", "expect"):
        if not case.get(key):
            raise CaseError(f"Case {case_id} is missing '{key}'")
    if not all(isinstance(t, str) and t.strip() for t in case["turns"]):
        raise CaseError(f"Case {case_id}: every turn must be a non-empty string")
    expect = case["expect"]
    unknown = set(expect.get("tools", [])) - KNOWN_TOOL_CATEGORIES
    for spec in expect.get("toolArguments", []):
        unknown |= {spec.get("category")} - KNOWN_TOOL_CATEGORIES
        if not isinstance(spec.get("arguments"), dict) or not spec["arguments"]:
            raise CaseError(f"Case {case_id}: toolArguments entries need an 'arguments' object")
    if unknown:
        raise CaseError(f"Case {case_id}: unknown tool categories {sorted(map(str, unknown))}")
    for key in ("replyMustMatch", "replyMustNotMatch"):
        for rule in expect.get(key, []):
            try:
                re.compile(rule["pattern"])
            except (KeyError, re.error) as exc:
                raise CaseError(f"Case {case_id}: invalid {key} pattern: {exc}") from exc
    for guard in expect.get("guards", []):
        if guard not in GUARDS:
            raise CaseError(f"Case {case_id}: unknown guard '{guard}'")
    if not expect.get("behaviors"):
        raise CaseError(f"Case {case_id}: list the expected behaviors for the judge")


def is_runnable(case: dict[str, Any]) -> bool:
    return case.get("status", "active") == "active"


def select_cases(cases: list[dict[str, Any]], ids: list[str] | None, include_future: bool = False) -> list[dict[str, Any]]:
    if ids:
        wanted = {i.upper() for i in ids}
        missing = wanted - {c["id"].upper() for c in cases}
        if missing:
            raise CaseError(f"Unknown case id(s): {', '.join(sorted(missing))}")
        return [c for c in cases if c["id"].upper() in wanted]
    return [c for c in cases if include_future or is_runnable(c)]


# --------------------------------------------------------------------------- deterministic checks


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def normalize(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


def all_calls(turns: list[TurnResult]) -> list[ToolCall]:
    return [call for turn in turns for call in turn.tool_calls]


def _find_values(obj: Any, key: str) -> list[Any]:
    """Every value stored under `key` (case-insensitive) anywhere in a nested structure."""
    found: list[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).casefold() == key.casefold():
                found.append(v)
            found.extend(_find_values(v, key))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_find_values(v, key))
    return found


def _values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return False
    return str(actual).strip().casefold() == str(expected).strip().casefold()


def arguments_match(arguments: Any, expected: dict[str, Any]) -> bool:
    if isinstance(arguments, str):
        # Unparsed arguments: fall back to a textual key/value search.
        return all(re.search(rf"{re.escape(k)}\W+{re.escape(str(v))}\b", arguments, re.I) for k, v in expected.items())
    return all(any(_values_equal(v, want) for v in _find_values(arguments, key)) for key, want in expected.items())


def describe_calls(calls: list[ToolCall]) -> str:
    return "; ".join(f"{c.category or c.name}({json.dumps(c.arguments, default=str)[:120]})" for c in calls) or "none"


def run_checks(case: dict[str, Any], turns: list[TurnResult]) -> list[Check]:
    expect = case["expect"]
    checks: list[Check] = []
    calls = all_calls(turns)
    replies = [normalize(clean_customer_text(t.text)) for t in turns]
    final = replies[-1] if replies else ""

    checks.append(Check("reply:not-empty", bool(final.strip()), "" if final.strip() else "final reply was empty"))

    used = {c.category for c in calls if c.category}
    for category in expect.get("tools", []):
        checks.append(Check(f"tool:{category}", category in used, f"tools used: {sorted(used) or 'none'}"))

    for spec in expect.get("toolArguments", []):
        category, wanted = spec["category"], spec["arguments"]
        candidates = [c for c in calls if c.category == category]
        ok = any(arguments_match(c.arguments, wanted) for c in candidates)
        checks.append(Check(f"args:{category}", ok, f"expected {wanted}; got {describe_calls(candidates)}"))

    for rule in expect.get("replyMustMatch", []):
        ok = re.search(rule["pattern"], final, re.IGNORECASE) is not None
        checks.append(Check(f"reply:{rule.get('why') or rule['pattern']}", ok, f"/{rule['pattern']}/ not found in final reply" if not ok else ""))

    for rule in expect.get("replyMustNotMatch", []):
        hits = [m.group(0) for r in replies for m in [re.search(rule["pattern"], r, re.IGNORECASE)] if m]
        checks.append(Check(f"avoid:{rule.get('why') or rule['pattern']}", not hits, f"found: {hits[0]!r}" if hits else ""))

    for guard in expect.get("guards", []):
        plain = [r.replace("*", "") for r in replies]
        hits = [m.group(0) for p in GUARDS[guard] for r in plain for m in [re.search(p, r, re.IGNORECASE)] if m]
        checks.append(Check(f"guard:{guard}", not hits, f"found: {hits[0]!r}" if hits else ""))

    return checks


# --------------------------------------------------------------------------- LLM judge

JUDGE_INSTRUCTIONS = """You are a strict quality evaluator for Contoso Air's customer-care AI agent.

You receive one evaluation case: the expected behaviors, the conversation (customer messages, the agent's tool calls with their outputs, and the agent's replies), and the approved Contoso Air policy documents.

Source of truth:
- Tool outputs are the only source of truth for customers, reservations, flight status and seat availability.
- The policy documents are the only source of truth for fees, benefits, assistance, refunds, contacts and escalation.
- The agent has NO tools that change reservations. Any claim that a booking, hold, change, voucher, upgrade or credit was completed is a false claim.

Score each criterion from 1 (very poor) to 5 (excellent):
- task_completion: Did the agent help resolve the customer's problem as far as its tools and policy allow?
- groundedness: Is every factual claim supported by the tool outputs or the policy documents?
- tool_correctness: Did the agent call the appropriate tools with appropriate inputs (customer, flight, date, route, passenger count, cabin)? Retrieval of policy (file search) counts as a tool.
- policy_adherence: Did the reply follow Contoso Air policy, including escalation procedures and the limits of the digital assistant's authority?
- recommendation_quality: Did any recommendation account for passenger count, route, verified availability, nonstop versus connection and timing? If the case calls for no recommendation, score how appropriately the agent avoided or deferred one.
- hallucination_avoidance: Did the agent avoid inventing records, availability, policy, amounts, phone numbers or completed actions?
- communication_quality: Was the reply concise, clear, professional, empathetic and customer-friendly, without internal jargon such as tool names or error codes?

Judge behavior, not wording. Score a criterion 2 or lower when an expected behavior that it covers is clearly missing or contradicted. Ignore citation markers.

Return only a JSON object:
{"scores": {"task_completion": n, "groundedness": n, "tool_correctness": n, "policy_adherence": n, "recommendation_quality": n, "hallucination_avoidance": n, "communication_quality": n}, "issues": ["short description of each problem found"], "rationale": "two or three sentences"}"""

MAX_TOOL_OUTPUT_CHARS = 6000


def load_policies(policy_dir: Path = POLICY_DIR) -> str:
    docs = sorted(policy_dir.glob("*.md"))
    if not docs:
        raise ConfigError(f"No policy sources found in {policy_dir}")
    return "\n\n".join(f"===== {p.name} =====\n{p.read_text(encoding='utf-8').strip()}" for p in docs)


def _short(value: Any, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


def transcript_text(case: dict[str, Any], turns: list[TurnResult]) -> str:
    lines = [session_context_text(case["customerId"])]
    for number, (message, turn) in enumerate(zip(case["turns"], turns), start=1):
        lines.append(f"\n--- Turn {number} ---\nCUSTOMER: {message}")
        for call in turn.tool_calls:
            if call.category == "knowledge":
                lines.append(f"TOOL CALL file_search (policy retrieval) queries={_short(call.arguments, 400)}")
                continue
            lines.append(f"TOOL CALL {call.name or call.type} arguments={_short(call.arguments, 400)}")
            lines.append(f"TOOL OUTPUT {_short(call.output)}")
        lines.append(f"AGENT REPLY:\n{clean_customer_text(turn.text)}")
    return "\n".join(lines)


def judge_prompt(case: dict[str, Any], turns: list[TurnResult], policies: str) -> str:
    behaviors = "\n".join(f"- {b}" for b in case["expect"]["behaviors"])
    return (
        f"CASE {case['id']}: {case['title']} ({case['category']})\n\n"
        f"EXPECTED BEHAVIORS:\n{behaviors}\n\n"
        f"CONVERSATION:\n{transcript_text(case, turns)}\n\n"
        f"APPROVED CONTOSO AIR POLICIES:\n{policies}\n\n"
        "Score the conversation and respond with the JSON object described in your instructions."
    )


def parse_judge_output(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("judge returned no JSON object")
    data = json.loads(match.group(0))
    scores = data.get("scores") or {}
    clean: dict[str, int] = {}
    for name in CRITERIA:
        value = scores.get(name)
        if not isinstance(value, (int, float)) or not 1 <= value <= 5:
            raise ValueError(f"judge score for {name} is missing or out of range: {value!r}")
        clean[name] = int(round(value))
    return {"scores": clean, "issues": [str(i) for i in data.get("issues") or []], "rationale": str(data.get("rationale", ""))}


def judge_passed(scores: dict[str, int]) -> bool:
    return all(scores[name] >= JUDGE_THRESHOLDS[name] for name in CRITERIA)


def judge_case(openai_client: Any, model: str, case: dict[str, Any], turns: list[TurnResult], policies: str) -> dict[str, Any]:
    response = openai_client.responses.create(
        model=model,
        instructions=JUDGE_INSTRUCTIONS,
        input=judge_prompt(case, turns, policies),
        text={"format": {"type": "json_object"}},
    )
    verdict = parse_judge_output(getattr(response, "output_text", "") or "")
    verdict["passed"] = judge_passed(verdict["scores"])
    return verdict


# --------------------------------------------------------------------------- running cases


@dataclass
class CaseResult:
    id: str
    title: str
    category: str
    status: str  # passed | failed | error | skipped
    checks: list[Check] = field(default_factory=list)
    judge: dict[str, Any] | None = None
    transcript: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0

    @property
    def checks_passed(self) -> int:
        return sum(c.passed for c in self.checks)


def _turn_record(message: str, turn: TurnResult) -> dict[str, Any]:
    return {
        "customer": message,
        "reply": clean_customer_text(turn.text),
        "responseId": turn.response_id,
        "toolCalls": [
            {"category": c.category, "name": c.name, "arguments": c.arguments, "status": c.status}
            for c in turn.tool_calls
        ],
    }


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Seconds to wait before retrying: the service's Retry-After hint when present, else exponential backoff."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        hinted = float(headers.get("retry-after", ""))
    except (TypeError, ValueError):
        hinted = 0.0
    return min(90.0, max(hinted, 10.0 * 2 ** (attempt - 1)))


def _with_retry(fn: Callable[[], Any], attempts: int = 5) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retry only throttling and transient server errors
            status = getattr(exc, "status_code", None)
            if attempt == attempts or not (status == 429 or (isinstance(status, int) and status >= 500)):
                raise
            time.sleep(_retry_delay(exc, attempt))
    raise AssertionError("unreachable")


def run_case(openai_client: Any, case: dict[str, Any], agent_name: str, agent_version: str | None,
             judge_model: str | None, policies: str | None) -> CaseResult:
    result = CaseResult(case["id"], case["title"], case["category"], status="failed")
    if not is_runnable(case):
        result.status = "skipped"
        result.error = case.get("skipReason", "Case is not active.")
        return result
    started = time.monotonic()
    turns: list[TurnResult] = []
    try:
        handle = _with_retry(lambda: create_conversation(openai_client, case["customerId"]))
        for message in case["turns"]:
            turn = _with_retry(lambda m=message: ask_agent(openai_client, handle, m, agent_name, agent_version))
            turns.append(turn)
            result.transcript.append(_turn_record(message, turn))
        result.checks = run_checks(case, turns)
        if judge_model and policies is not None:
            try:
                result.judge = _with_retry(lambda: judge_case(openai_client, judge_model, case, turns, policies))
            except Exception as exc:  # noqa: BLE001 - a judge failure is reported, not fatal
                result.judge = {"error": f"{type(exc).__name__}: {exc}", "passed": False}
        checks_ok = all(c.passed for c in result.checks)
        judge_ok = result.judge is None or bool(result.judge.get("passed"))
        result.status = "passed" if checks_ok and judge_ok else "failed"
    except Exception as exc:  # noqa: BLE001 - record and continue with the remaining cases
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
    result.seconds = round(time.monotonic() - started, 1)
    return result


# --------------------------------------------------------------------------- reporting


def summary_table(results: list[CaseResult]) -> str:
    header = f"{'Case':<5} {'Result':<8} {'Checks':<7} {'Judge ' + ' '.join(CRITERIA_ABBREVIATIONS):<27} {'Time':>6}  Title"
    rows = [header, "-" * len(header)]
    for r in results:
        checks = f"{r.checks_passed}/{len(r.checks)}" if r.checks else "-"
        if r.judge and "scores" in r.judge:
            judge = "      " + "  ".join(str(r.judge["scores"][c]) for c in CRITERIA)
        elif r.judge:
            judge = "      error"
        else:
            judge = "      -"
        rows.append(f"{r.id:<5} {r.status.upper():<8} {checks:<7} {judge:<27} {r.seconds:>5.0f}s  {r.title}")
    counts = {s: sum(r.status == s for r in results) for s in ("passed", "failed", "error", "skipped")}
    rows.append("")
    rows.append(" | ".join(f"{k}: {v}" for k, v in counts.items()))
    rows.append("Judge criteria: " + ", ".join(f"{a}={c}" for a, c in zip(CRITERIA_ABBREVIATIONS, CRITERIA)))
    return "\n".join(rows)


def failure_details(results: list[CaseResult]) -> str:
    lines = []
    for r in results:
        if r.status in ("passed", "skipped"):
            continue
        lines.append(f"\n[{r.id}] {r.title}")
        if r.error:
            lines.append(f"  error: {r.error}")
        for c in r.checks:
            if not c.passed:
                lines.append(f"  check failed: {c.name} - {c.detail}")
        if r.judge:
            if "error" in r.judge:
                lines.append(f"  judge error: {r.judge['error']}")
            elif not r.judge.get("passed"):
                low = [f"{c}={s}" for c, s in r.judge["scores"].items() if s < JUDGE_THRESHOLDS[c]]
                lines.append(f"  judge below threshold: {', '.join(low)}")
                for issue in r.judge.get("issues", []):
                    lines.append(f"    - {issue}")
    return "\n".join(lines)


def write_results(results: list[CaseResult], meta: dict[str, Any], out_dir: Path = RESULTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"meta": meta, "results": [asdict(r) for r in results]}
    path = out_dir / f"evaluation-{stamp}.json"
    text = json.dumps(payload, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    (out_dir / "latest.json").write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- Foundry cloud evaluation


CLOUD_EVALUATORS = ("builtin.task_adherence", "builtin.intent_resolution", "builtin.task_completion")


def cloud_dataset_rows(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Single-turn runnable cases as Foundry evaluation dataset rows."""
    return [
        {"case_id": c["id"], "query": c["turns"][0], "session_context": session_context_text(c["customerId"])}
        for c in cases
        if is_runnable(c) and len(c["turns"]) == 1
    ]


def run_cloud_evaluation(project: Any, openai_client: Any, cases: list[dict[str, Any]], agent_name: str,
                         agent_version: str | None, judge_model: str, wait: bool = True) -> dict[str, Any]:
    """Submit the single-turn cases as a Foundry cloud evaluation that targets the agent.

    Results appear in the Foundry portal under Evaluations. Multi-turn cases (E1) are
    covered only by the local runner.
    """
    import tempfile

    rows = cloud_dataset_rows(cases)
    if not rows:
        raise CaseError("No single-turn runnable cases to submit")
    with tempfile.TemporaryDirectory() as tmp:
        data_file = Path(tmp) / "contoso-air-eval.jsonl"
        data_file.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        dataset = project.datasets.upload_file(
            name=f"{agent_name}-eval", version=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"), file_path=str(data_file)
        )

    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": name.removeprefix("builtin."),
            "evaluator_name": name,
            "initialization_parameters": {"deployment_name": judge_model},
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_items}}"},
        }
        for name in CLOUD_EVALUATORS
    ]
    evaluation = openai_client.evals.create(
        name=f"{agent_name} scenario evaluation",
        data_source_config={
            "type": "custom",
            "item_schema": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}, "query": {"type": "string"}, "session_context": {"type": "string"}},
                "required": ["query", "session_context"],
            },
            "include_sample_schema": True,
        },
        testing_criteria=testing_criteria,
    )
    target: dict[str, Any] = {"type": "azure_ai_agent", "name": agent_name}
    if agent_version:
        target["version"] = str(agent_version)
    run = openai_client.evals.runs.create(
        eval_id=evaluation.id,
        name=f"{agent_name} {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        data_source={
            "type": "azure_ai_target_completions",
            "source": {"type": "file_id", "id": dataset.id},
            "input_messages": {
                "type": "template",
                "template": [
                    {"type": "message", "role": "developer", "content": {"type": "input_text", "text": "{{item.session_context}}"}},
                    {"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}},
                ],
            },
            "target": target,
        },
    )
    while wait and run.status not in ("completed", "failed", "canceled", "cancelled"):
        time.sleep(10)
        run = openai_client.evals.runs.retrieve(run_id=run.id, eval_id=evaluation.id)
    return {
        "evalId": evaluation.id,
        "runId": run.id,
        "status": run.status,
        "reportUrl": getattr(run, "report_url", None),
        "resultCounts": _plain(getattr(run, "result_counts", None)),
        "perCriteria": _plain(getattr(run, "per_testing_criteria_results", None)),
    }


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


# --------------------------------------------------------------------------- CLI


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the Contoso Air Customer Care agent.")
    parser.add_argument("--case", action="append", dest="cases", metavar="ID", help="Run only this case (repeatable).")
    parser.add_argument("--list", action="store_true", help="List the cases and exit.")
    parser.add_argument("--no-judge", action="store_true", help="Skip the LLM judge; run deterministic checks only.")
    parser.add_argument("--agent-version", help="Agent version to evaluate (default: FOUNDRY_AGENT_VERSION, then "
                                                "activeAgentVersion in .foundry-state.json, then latest).")
    parser.add_argument("--parallel", type=int, default=2,
                        help="Cases to run concurrently (default: 2). Higher values can hit model token-rate limits (HTTP 429).")
    parser.add_argument("--show-replies", action="store_true", help="Print every agent reply.")
    parser.add_argument("--cloud", action="store_true", help="Also submit the single-turn cases as a Foundry cloud evaluation.")
    parser.add_argument("--cases-file", type=Path, default=CASES_FILE, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)
    try:
        cases = load_cases(args.cases_file)
        selected = select_cases(cases, args.cases)
    except (CaseError, ValueError) as exc:
        print(f"Invalid test cases: {exc}", file=sys.stderr)
        return 2

    if args.list:
        for c in cases:
            marker = "" if is_runnable(c) else f"  [{c.get('status')}]"
            print(f"{c['id']:<4} {c['category']:<20} {c['title']}{marker}")
        print(f"\n{sum(map(is_runnable, cases))} runnable of {len(cases)} cases")
        return 0

    try:
        settings = get_settings()
        settings.require("project_endpoint", "agent_name")
        judge_model = None if args.no_judge else settings.judge_deployment
        if not args.no_judge and not judge_model:
            raise ConfigError("Set FOUNDRY_JUDGE_DEPLOYMENT_NAME or FOUNDRY_MODEL_DEPLOYMENT_NAME, or pass --no-judge.")
        policies = None if args.no_judge else load_policies()
        project = project_client(settings)
        openai_client = project.get_openai_client()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    agent_version, version_source = resolve_agent_version(settings, args.agent_version)
    version_label = agent_version or "latest"
    print(f"Evaluating agent '{settings.agent_name}' version {version_label} (from {version_source}) on "
          f"{len(selected)} case(s); judge: {judge_model or 'off'}\n")

    def _run(case: dict[str, Any]) -> CaseResult:
        r = run_case(openai_client, case, settings.agent_name, agent_version, judge_model, policies)
        print(f"  {r.id:<4} {r.status.upper():<8} {r.seconds:>5.0f}s  {r.title}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        results = list(pool.map(_run, selected))

    if args.show_replies:
        for r in results:
            for i, t in enumerate(r.transcript, start=1):
                print(f"\n=== {r.id} turn {i} ===\nCUSTOMER: {t['customer']}\nAGENT: {t['reply']}")

    print("\n" + summary_table(results))
    details = failure_details(results)
    if details:
        print(details)

    meta = {
        "agentName": settings.agent_name,
        "agentVersion": version_label,
        "judgeModel": judge_model,
        "thresholds": JUDGE_THRESHOLDS,
        "startedCases": [c["id"] for c in selected],
        "finishedAt": datetime.now(timezone.utc).isoformat(),
    }
    if args.cloud:
        print("\nSubmitting Foundry cloud evaluation (single-turn cases)...")
        try:
            meta["cloud"] = run_cloud_evaluation(project, openai_client, selected, settings.agent_name,
                                                 agent_version, settings.judge_deployment)
            print(f"Cloud evaluation {meta['cloud']['status']}: {meta['cloud'].get('reportUrl') or meta['cloud']['runId']}")
        except Exception as exc:  # noqa: BLE001 - the local results are still valid
            meta["cloud"] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"Cloud evaluation failed: {exc}", file=sys.stderr)

    path = write_results(results, meta)
    print(f"\nDetailed results: {path.relative_to(REPO_ROOT)}")
    return 0 if all(r.status in ("passed", "skipped") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
