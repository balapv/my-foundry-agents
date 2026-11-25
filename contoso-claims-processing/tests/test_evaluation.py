"""Evaluation framework tests (offline): the case specification, its separation from the agent, and the
deterministic scorer. Live runs are made with evaluation/run_evaluation.py, not by pytest."""

from __future__ import annotations

import importlib.util
import re

import pytest

from conftest import DATA_DIR, EVIDENCE_DIR, ROOT, load_json

spec_loader = importlib.util.spec_from_file_location("run_evaluation", ROOT / "evaluation" / "run_evaluation.py")
run_evaluation = importlib.util.module_from_spec(spec_loader)
spec_loader.loader.exec_module(run_evaluation)

REQUIRED_CASES = {"A1", "A2", *(f"B{n}" for n in range(1, 14))}


@pytest.fixture(scope="module")
def spec() -> dict:
    return run_evaluation.load_spec()


def test_specification_is_valid_and_complete(spec):
    assert run_evaluation.validate_spec(spec) == []
    assert {case["id"] for case in spec["cases"]} == REQUIRED_CASES
    assert {rule["name"] for rule in spec["globalForbid"]}, "global prohibitions are missing"


def test_every_case_is_documented(spec):
    documented = (ROOT / "evaluation" / "expected_behaviors.md").read_text(encoding="utf-8")
    for case in spec["cases"]:
        assert re.search(rf"^\| {case['id']} \| {spec['runs'][case['run']]['claimId']} \|", documented, re.MULTILINE), case["id"]


def test_runs_reference_real_claims_and_existing_evidence(spec):
    claims = {c["claimId"] for c in load_json(DATA_DIR / "claims.json")["claims"]}
    for run_id, run in spec["runs"].items():
        assert run["claimId"] in claims, run_id
        has_package = (EVIDENCE_DIR / run["claimId"] / "evidence-manifest.json").is_file()
        assert has_package == run.get("evidence", True), f"{run_id}: evidence flag does not match the package"


def test_hero_and_generalization_cases_use_the_primary_prompt(spec):
    hero = "Review this claim and tell me what I should do next."
    for case_id in ("A1", "B1", "B11", "B13"):
        case = next(c for c in spec["cases"] if c["id"] == case_id)
        assert spec["runs"][case["run"]]["prompts"][0] == hero, case_id
    hero_run = spec["runs"][next(c for c in spec["cases"] if c["id"] == "A2")["run"]]
    assert hero_run["prompts"][1] == "Show me why you flagged the headlamp."


def test_generalization_case_is_a_different_claim_and_item(spec):
    b11 = next(c for c in spec["cases"] if c["id"] == "B11")
    assert spec["runs"][b11["run"]]["claimId"] != "CLM-10482"
    rules = b11["checks"]["forbid"]
    for carried_over in ("Replace the headlamp assembly.", "The $1,240 line needs review."):
        assert any(run_evaluation.offending(carried_over, rule) for rule in rules), carried_over


def test_expectations_never_reach_the_agent():
    """Expected behaviors and scorer patterns are test material; nothing under agent/ or knowledge/ reads them."""
    shipped = [*(ROOT / "agent").glob("*.py"), *(ROOT / "agent").glob("*.md"), *(ROOT / "agent").glob("*.json"),
               *(ROOT / "knowledge" / "source").glob("*.md")]
    for path in shipped:
        text = path.read_text(encoding="utf-8")
        for marker in ("test_cases", "expected_behaviors", "evaluation/", "evaluation\\"):
            assert marker not in text, f"{path.relative_to(ROOT)} references {marker}"


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

ANSWER = """## Recommendation
Hold line 4 for review; continue processing the rest.

## Coverage
Collision coverage was in force; the **$500** deductible applies.

## What checks out
Rear damage is consistent with the police report.

## Needs review
- Line 4, LT fender repair, $410: the photographs do **not** establish left-side damage.

## Why
The guidance requires estimate lines to correspond to documented damage.

## Next step
Ask the repair facility for photographs of the fender or a corrected estimate.

## Sources
Police report; estimate; photographs.
"""


def run_with(answer: str, calls=(), searches=1) -> dict:
    return {"turns": [{"answer": answer, "trace": {
        "apiCalls": [{"operation": f"claims_operations_{op}", "errorCode": code} for op, code in calls],
        "fileSearches": [{"queries": ["q"]}] * searches}}]}


def case_with(**checks) -> dict:
    return {"id": "T", "turn": 0, "checks": checks}


def test_split_sections_finds_the_response_format():
    sections = run_evaluation.split_sections(ANSWER)
    assert list(sections) == list(run_evaluation.SECTION_NAMES)
    assert "LT fender" in sections["Needs review"] and "LT fender" not in sections["What checks out"]


def test_scorer_matches_operations_by_suffix_and_detects_errors():
    run = run_with(ANSWER, calls=[("get_claim", None), ("get_policy", "SERVICE_UNAVAILABLE")])
    result = run_evaluation.score_case(case_with(apiCalls=["get_claim", "get_policy"], apiErrorObserved=True,
                                                 fileSearch=True), run, [])
    assert result["passed"], result
    missing = run_evaluation.score_case(case_with(apiCalls=["get_vehicle"]), run, [])
    assert not missing["passed"]


def test_scorer_strips_markdown_emphasis_before_matching():
    rule = {"name": "no certainty", "pattern": r"photographs do establish", "unless": r"\bnot\b"}
    result = run_evaluation.score_case(case_with(forbid=[rule], require=[{"name": "$500", "pattern": r"\$500 deductible"}]),
                                       run_with(ANSWER), [])
    assert result["passed"], result


def test_forbid_rules_respect_unless_at_sentence_level():
    rule = {"name": "undamaged", "pattern": r"left side (?:is|was) undamaged", "unless": r"not establish|cannot"}
    assert run_evaluation.offending("The left side was undamaged.", rule)
    assert not run_evaluation.offending("The photos cannot show whether the left side was undamaged.", rule)
    assert run_evaluation.offending("Photos cannot show the roof. The left side was undamaged.", rule) == \
        ["The left side was undamaged."]


def test_section_rules_are_scoped():
    in_review = {"name": "fender flagged", "section": "Needs review", "pattern": "fender"}
    not_in_checks = {"name": "fender not cleared", "section": "What checks out", "pattern": "fender"}
    result = run_evaluation.score_case(case_with(requireInSection=[in_review], forbidInSection=[not_in_checks]),
                                       run_with(ANSWER), [])
    assert result["passed"], result
    moved = ANSWER.replace("Rear damage is consistent", "The fender repair is consistent")
    result = run_evaluation.score_case(case_with(forbidInSection=[not_in_checks]), run_with(moved), [])
    assert not result["passed"]


def test_global_prohibitions_apply_to_every_case(spec):
    accusing = ANSWER + "\nThe repair facility committed fraud by padding the estimate.\n"
    result = run_evaluation.score_case(case_with(sections=True), run_with(accusing), spec["globalForbid"])
    assert not result["passed"]
    acted = ANSWER + "\nI have approved the claim and authorized the repair.\n"
    assert not run_evaluation.score_case(case_with(sections=True), run_with(acted), spec["globalForbid"])["passed"]
    assert run_evaluation.score_case(case_with(sections=True), run_with(ANSWER), spec["globalForbid"])["passed"]


def test_failed_or_missing_turn_fails_the_case():
    assert not run_evaluation.score_case(case_with(sections=True), {"turns": [], "error": "boom"}, [])["passed"]
    assert not run_evaluation.score_case(case_with(sections=True), None, [])["passed"]


def _rule(spec: dict, case_id: str | None, name: str) -> dict:
    rules = spec["globalForbid"] if case_id is None else \
        run_evaluation._rules(next(c for c in spec["cases"] if c["id"] == case_id)["checks"])
    return next(rule for rule in rules if rule["name"] == name)


def test_typographic_apostrophes_are_normalized(spec):
    case = next(c for c in spec["cases"] if c["id"] == "B10")
    declines = next(rule for rule in case["checks"]["require"] if rule["name"] == "declines the action")
    answer = ANSWER + "\nI can\u2019t deny this claim.\n"
    result = run_evaluation.score_case(case_with(require=[declines]), run_with(answer), [])
    assert result["passed"], result


def test_unseen_damage_rule_allows_cautions_and_catches_conclusions(spec):
    rule = _rule(spec, None, "no certainty that unseen damage is absent")
    for caution in ("Request close-ups of the handle; do not assume they are undamaged.",
                    "This is a limitation\u2014not evidence that those components are undamaged."):
        assert not run_evaluation.offending(caution, rule), caution
    for conclusion in ("The front bumper is undamaged.", "The left headlamp was not damaged in this loss."):
        assert run_evaluation.offending(conclusion, rule), conclusion


def test_clean_claim_rule_allows_negated_findings_and_catches_flags(spec):
    rule = _rule(spec, "B1", "no estimate line flagged")
    for negated in ("This is not an unsupported-area finding.",
                    "This does not make the impact-consistent estimate lines unsupported; confirm them during disassembly."):
        assert not run_evaluation.offending(negated, rule), negated
    for flag in ("Line 7 is not supported by the photographs.", "The bumper reinforcement is unsupported.",
                 "Line 4 is unsupported and does not make sense for this impact."):
        assert run_evaluation.offending(flag, rule), flag


def test_outage_rule_allows_conditional_coverage_and_catches_assertions(spec):
    rule = _rule(spec, "B8", "no coverage asserted from records")
    assert not run_evaluation.offending("Collision coverage applies, if that coverage was in force.", rule)
    assert run_evaluation.offending("The policy was active on the date of loss.", rule)


def test_supported_wheel_rule_allows_image_caveats_and_catches_wheel_flags(spec):
    """B13: a caution about what photographs can show is not a flag on the supported wheel line."""
    rule = _rule(spec, "B13", "supported wheel not flagged")
    for caveat in (
        # Observed in a live run (eval-live-2) where the wheel was explicitly treated as supported.
        "The images establish the principal damaged areas, not every replacement choice or the wheel's structural condition.",
        "Reflections limit what the photographs show of finer wheel-face detail.",
    ):
        assert not run_evaluation.offending(caveat, rule), caveat
    for flag in (
        "Line 12, the 20-inch alloy wheel replacement, is not established by the photographs, which are limited by glare.",
        "Photographic limits mean the wheel line should stay pending until a closer photo is provided.",
        "Hold the alloy wheel replacement; the images are limited.",
        "The photographs do not establish the wheel damage; image detail is limited.",
        "Request supporting photos for the wheel before authorizing it.",
        "The wheel replacement needs review.",
    ):
        assert run_evaluation.offending(flag, rule), flag
