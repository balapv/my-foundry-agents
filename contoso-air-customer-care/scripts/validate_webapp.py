"""Validate the Contoso Air web app end to end against the live Foundry agent.

Runs the hero scenario and three follow-ups in ONE web chat session, exactly as a customer would
through the browser (POST /api/session, then POST /api/chat server-sent event streams):

    1. Hero prompt (from agent/config.json heroPrompt)
    2. "Why is that better than the connection?"
    3. "Do I qualify for a hotel?"
    4. "Book it."

It checks the customer-visible output only (progress messages and reply text). The checks are
lenient pattern checks for the factual outcome, not exact wording. Requires a configured .env and
a deployed agent and Operations API.

Usage (from the repository root):

    python scripts/validate_webapp.py                       # starts the web app on a free port
    python scripts/validate_webapp.py --base-url http://127.0.0.1:8080
    python scripts/validate_webapp.py --transcript web-transcript.md

Exits with code 1 when any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from agent.foundry_common import STATUS_MESSAGES, configure_console, load_config  # noqa: E402
from evaluation.run_evaluation import GUARDS  # noqa: E402

FOLLOW_UPS = ("Why is that better than the connection?", "Do I qualify for a hotel?", "Book it.")
INTERNALS = re.compile(r"contoso_air_operations|operationId|openapi|file_search|get_customer_reservations|"
                       r"get_flight_status|search_alternative_flights|Traceback|vs_[A-Za-z0-9]", re.I)
COMPLETED_ACTION = [re.compile(p, re.I) for p in GUARDS["no_completed_action_claim"]]
# The shared guards do not recognise "nothing has been booked or held" as a negation. Clauses that start with
# "nothing" are removed before the guards run, so a correct "nothing has been booked" is not counted as a claim.
NEGATED_CLAUSE = re.compile(r"\bnothing (?:has|have|is|was) (?:been |yet )?[^.,;:!?\n]*", re.I)


def normalize(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


@dataclass
class Turn:
    prompt: str
    statuses: list[str] = field(default_factory=list)
    reply: str = ""
    error: str | None = None
    seconds: float = 0.0
    checks: list[tuple[str, bool]] = field(default_factory=list)

    def check(self, name: str, passed: bool) -> None:
        self.checks.append((name, bool(passed)))

    @property
    def passed(self) -> bool:
        return self.error is None and all(ok for _, ok in self.checks)


def has(pattern: str) -> Callable[[str], bool]:
    regex = re.compile(pattern, re.I)
    return lambda text: bool(regex.search(text))


def common_checks(turn: Turn) -> None:
    turn.check("no error shown", turn.error is None)
    turn.check("no internal tool names or traces in the browser", not INTERNALS.search(turn.reply + " ".join(turn.statuses)))
    affirmative = NEGATED_CLAUSE.sub("", turn.reply)
    turn.check("does not claim a completed booking, hold or change",
               not any(p.search(affirmative) for p in COMPLETED_ACTION))


def check_hero(turn: Turn) -> None:
    text = turn.reply
    for key, label in (("reservation", "reservation retrieved"), ("flight_status", "flight status verified"),
                       ("knowledge", "policy consulted"), ("flight_search", "alternatives searched")):
        turn.check(f"{label} (progress: {STATUS_MESSAGES[key]})", STATUS_MESSAGES[key] in turn.statuses)
    turn.check("cancellation acknowledged", has(r"cancel")(text))
    turn.check("CT226 recommended", has(r"CT\s?226")(text))
    turn.check("CT232 not recommended (not bolded)", not has(r"\*\*[^*\n]*CT\s?232[^*\n]*\*\*")(text))
    turn.check("all four travelers kept together", has(r"\b(all four|all 4|four (of you|travel|passeng|seat)|4 (travel|passeng|seat)|together)")(text))
    turn.check("Economy Plus retained", has(r"Economy Plus")(text))
    turn.check("nonstop advantage recognized", has(r"non-?stop")(text))
    turn.check("departure-time tradeoff explained", has(r"earlier|departs? (at )?\d{1,2}:\d{2}|\d{1,2}:\d{2}\s?(AM|PM)")(text))
    turn.check("policy benefit explained (fees/fare difference waived)", has(r"waiv|(no|without) (a )?(change )?fees?|at no (additional )?cost|no charge")(text))
    turn.check("confirmation requested", has(r"\?\s*$|would you like|shall I|do you want|confirm")(text))


def check_follow_up_a(turn: Turn) -> None:
    restarted = all(STATUS_MESSAGES[k] in turn.statuses for k in ("reservation", "flight_search"))
    turn.check("does not restart the whole investigation", not restarted)
    turn.check("explains nonstop vs connection", has(r"non-?stop|connect|layover|change planes")(turn.reply))
    turn.check("explains seating/cabin tradeoff", has(r"together|Economy Plus|seat|cabin")(turn.reply))


def check_follow_up_b(turn: Turn) -> None:
    text = turn.reply
    turn.check("no hotel promise",
               not has(r"(?:we|I|Contoso Air)(?: will|'ll) (?:provide|book|arrange|cover|pay for|reimburse)[^.\n]{0,20}hotel")(text))
    turn.check("no unsupported hotel eligibility claim",
               not has(r"you(?:'re| are) (?:eligible|entitled) (?:for|to)[^.\n]{0,20}hotel")(text))
    turn.check("addresses hotel eligibility with policy context",
               has(r"home (airport|city)|Seattle|not (eligible|provided|typically)|don't qualify|do not qualify|wouldn't qualify|not qualify")(text))


def check_follow_up_c(turn: Turn) -> None:
    text = turn.reply
    turn.check("says it cannot complete the booking here",
               has(r"can(?:'t|not)|unable|not able|don't have the ability|isn't something I can")(text))
    turn.check("gives a contact to complete the change", has(r"1-800-555-01\d\d")(text))
    turn.check("summarizes what to request (CT226)", has(r"CT\s?226")(text))


CHECKS = (check_hero, check_follow_up_a, check_follow_up_b, check_follow_up_c)


# --------------------------------------------------------------------------- web client


def read_sse(response: httpx.Response):
    event, data = "message", []
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            yield event, json.loads("\n".join(data))
            event, data = "message", []


def send(client: httpx.Client, session_id: str, prompt: str) -> Turn:
    turn = Turn(prompt)
    started = time.monotonic()
    streamed = ""
    with client.stream("POST", "/api/chat", json={"sessionId": session_id, "message": prompt}) as response:
        response.raise_for_status()
        for event, data in read_sse(response):
            if event == "status":
                turn.statuses.append(data["message"])
            elif event == "delta":
                streamed += data["text"]
            elif event == "done":
                turn.reply = normalize(data.get("text") or streamed)
            elif event == "error":
                turn.error = data.get("message")
    turn.seconds = time.monotonic() - started
    return turn


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--app-dir", "webapp/backend", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=REPO_ROOT,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit("The web app exited during startup. Run it directly to see the error.")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.5)
    process.terminate()
    raise SystemExit("The web app did not start within 60 seconds.")


def render(trip_line: str, version: str, turns: list[Turn]) -> str:
    lines = ["# Contoso Air web app validation", "", f"- Agent version used by the web app: {version}",
             f"- Trip card: {trip_line}", ""]
    for number, turn in enumerate(turns, 1):
        lines += [f"## Turn {number}: {turn.prompt}", "",
                  f"Progress shown: {' → '.join(turn.statuses) or '(none)'}  ",
                  f"Time: {turn.seconds:.1f}s", "", "**Travel Assistant:**", ""]
        lines += [f"> {line}" if line else ">" for line in (turn.error or turn.reply).splitlines()]
        lines += ["", "| Check | Result |", "|---|---|"]
        lines += [f"| {name} | {'PASS' if ok else 'FAIL'} |" for name, ok in turn.checks]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="URL of a running web app. When omitted, the script starts one locally.")
    parser.add_argument("--transcript", type=Path, help="Write a Markdown transcript to this file.")
    args = parser.parse_args()

    process = None
    base_url = args.base_url
    if not base_url:
        port = free_port()
        process = start_server(port)
        base_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=httpx.Timeout(300, connect=10)) as client:
            version = client.get("/api/health").json().get("agentVersion", "?")
            session = client.post("/api/session").json()
            trip = session.get("trip") or {}
            segment = (trip.get("segments") or [{}])[0]
            trip_line = (f"{segment.get('originCity')} → {segment.get('destinationCity')}, {segment.get('date')}, "
                         f"{segment.get('flightNumber')}, {segment.get('flightStatus')}")
            print(f"Agent version: {version}\nTrip card: {trip_line}\n")
            prompts = [session.get("heroPrompt") or load_config()["heroPrompt"], *FOLLOW_UPS]
            turns = []
            for prompt, check in zip(prompts, CHECKS):
                print(f"> {prompt}")
                turn = send(client, session["sessionId"], prompt)
                common_checks(turn)
                check(turn)
                turns.append(turn)
                print(f"  progress: {' → '.join(turn.statuses) or '(none)'} ({turn.seconds:.1f}s)")
                for name, ok in turn.checks:
                    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
                print()
            client.delete(f"/api/session/{session['sessionId']}")
    finally:
        if process:
            process.terminate()
            process.wait(timeout=15)

    if args.transcript:
        args.transcript.write_text(render(trip_line, version, turns), encoding="utf-8")
        print(f"Transcript written to {args.transcript}")
    failed = [name for turn in turns for name, ok in turn.checks if not ok]
    print(f"{'PASSED' if not failed else 'FAILED'}: {sum(len(t.checks) for t in turns) - len(failed)} of "
          f"{sum(len(t.checks) for t in turns)} checks passed across {len(turns)} turns.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
