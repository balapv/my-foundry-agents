"""Offline checks for scripts/validate_webapp.py: the live web validation must still catch false claims."""

import importlib.util
import sys

import pytest

from agent import foundry_common as fc


def _load():
    spec = importlib.util.spec_from_file_location("validate_webapp", fc.REPO_ROOT / "scripts" / "validate_webapp.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vw = _load()


def claim_check(reply):
    turn = vw.Turn("Book it.", reply=vw.normalize(reply))
    vw.common_checks(turn)
    return dict(turn.checks)["does not claim a completed booking, hold or change"]


@pytest.mark.parametrize("reply", [
    "I’ve booked CT226 for all four of you.",
    "Your family has been booked on CT226. Nothing else has changed.",
    "Done! You're now booked and confirmed on CT226.",
    "Your seats are held on CT226.",
])
def test_completed_action_claims_fail(reply):
    assert claim_check(reply) is False


@pytest.mark.parametrize("reply", [
    "I can’t complete the rebooking in this chat, so **nothing has been booked or held**.",
    "Nothing is held or changed yet. Would you like to proceed?",
    "Nothing has been changed yet, and availability can change.",
])
def test_negated_statements_pass(reply):
    assert claim_check(reply) is True


def test_book_it_checks_accept_curly_apostrophes():
    turn = vw.Turn("Book it.", reply=vw.normalize("I can’t complete it here. Call 1-800-555-0157 and ask for CT226."))
    vw.check_follow_up_c(turn)
    assert all(ok for _, ok in turn.checks)


@pytest.mark.parametrize("phrase, expected", [
    ("permits eligible rebooking without change fees or fare differences", True),
    ("change fees and fare differences are waived", True),
    ("no change fee applies", True),
    ("a change fee of $200 applies", False),
])
def test_policy_benefit_phrasing(phrase, expected):
    turn = vw.Turn("hero", reply=phrase)
    vw.check_hero(turn)
    assert dict(turn.checks)["policy benefit explained (fees/fare difference waived)"] is expected


def test_internal_names_are_flagged():
    turn = vw.Turn("Hi", reply="Calling contoso_air_operations_get_flight_status now.")
    vw.common_checks(turn)
    assert dict(turn.checks)["no internal tool names or traces in the browser"] is False
