"""Run a claim review conversation against the Contoso Claims Review agent.

The first turn attaches the selected claim's evidence package (the PDFs and photographs listed in
evidence/<claim>/evidence-manifest.json) with an evidence index, then asks the adjuster's question.
Follow-up questions are sent in the same Foundry conversation, so the agent keeps the evidence and
its earlier tool results.

Usage:
  python agent/run_claim_review.py --claim CLM-10482
  python agent/run_claim_review.py --claim CLM-10482 --follow-up "Show me why you flagged the headlamp."
  python agent/run_claim_review.py --claim CLM-10482 --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402


def run_conversation(oai, agent_name: str, version: str, claim_id: str, prompts: list[str],
                     include_evidence: bool = True, image_detail: str = "high", echo: bool = True) -> dict:
    """Run prompts[0] with the evidence attached, then each follow-up, in one conversation."""
    conversation = oai.conversations.create(metadata={"claim": claim_id, "demo": "contoso-claims-processing"})
    turns = []
    for index, prompt in enumerate(prompts):
        message = common.evidence_message(claim_id, prompt, image_detail, include_evidence) if index == 0 else prompt
        started = time.perf_counter()
        error = None
        response = None
        try:
            response = oai.responses.create(
                conversation=conversation.id,
                input=[message] if index == 0 else message,
                include=["file_search_call.results"],
                extra_body=common.agent_reference(agent_name, version),
            )
        except Exception as exc:  # report the failure; a failed turn is not persisted by the service
            error = f"{type(exc).__name__}: {exc}"
        elapsed = round(time.perf_counter() - started, 1)
        turn = {"prompt": prompt, "seconds": elapsed,
                "input": common.describe_message(message) if index == 0 else {"role": "user", "content": prompt}}
        if response is not None:
            turn.update({"answer": common.final_text(response), "trace": common.trace(response)})
        else:
            turn.update({"answer": None, "error": error})
        turns.append(turn)
        if echo:
            print_turn(index, turn)
        if response is None:
            break
    return {"claimId": claim_id, "agent": {"name": agent_name, "version": version},
            "conversationId": conversation.id, "turns": turns}


def print_turn(index: int, turn: dict) -> None:
    print("=" * 100)
    print(f"Turn {index + 1}: {turn['prompt']}  ({turn['seconds']} s)")
    if index == 0:
        attached = [p.get("filename") or p["type"] for p in turn["input"]["content"] if p["type"] != "input_text"]
        print(f"Attached: {len(attached)} items -> {', '.join(attached)}")
    print("-" * 100)
    if turn.get("error"):
        print(f"ERROR: {turn['error']}")
        return
    print(turn["answer"])
    print("-" * 100)
    t = turn["trace"]
    for call in t["apiCalls"]:
        print(f"API   {call['operation']} {json.dumps(call['arguments'])}"
              + (f"  -> error {call['errorCode']}" if call["errorCode"] else ""))
    for search in t["fileSearches"]:
        files = sorted({r["file"] for r in search["results"]})
        print(f"SEARCH {search['queries']} -> {len(search['results'])} results from {files}")
    print(f"Repeated identical API calls: {t['repeatedApiCalls']} | usage: {t['usage']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--claim", required=True, help="Claim ID with an evidence package under evidence/.")
    parser.add_argument("--prompt", default=common.HERO_PROMPT)
    parser.add_argument("--follow-up", action="append", default=[], help="Follow-up question (repeatable).")
    parser.add_argument("--agent", help="Agent name (default: agentName from config).")
    parser.add_argument("--version", help="Agent version (default: the version in .foundry-state.json).")
    parser.add_argument("--no-evidence", action="store_true", help="Do not attach the claim evidence package.")
    parser.add_argument("--json", metavar="PATH", help="Also write the transcript and trace to PATH.")
    return parser.parse_args(argv)


def resolve_version(project, name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    recorded = common.load_state()["agents"].get(name, {}).get("version")
    if recorded:
        return recorded
    return str(project.agents.get(agent_name=name).versions["latest"].version)


def main(argv: list[str] | None = None) -> int:
    common.configure_console()
    args = parse_args(argv)
    config = common.load_config()
    try:
        settings = common.load_settings(require_tools_url=False)
        common.claim_evidence(args.claim) if not args.no_evidence else None
    except common.ConfigurationError as exc:
        print(exc, file=sys.stderr)
        if not args.no_evidence and str(exc).startswith("No evidence package"):
            print("Use --no-evidence to review a claim from its claims records only.", file=sys.stderr)
        return 2
    project = common.project_client(settings)
    name = args.agent or config["agentName"]
    version = resolve_version(project, name, args.version)
    result = run_conversation(project.get_openai_client(), name, version, args.claim,
                              [args.prompt, *args.follow_up], not args.no_evidence, config["imageDetail"])
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if all(turn.get("answer") for turn in result["turns"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
