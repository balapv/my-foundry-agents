"""Knowledge asset checks: the policy PDFs exist, meet the spec's page targets and contain key rules."""

import re
from pathlib import Path

import pytest
from pypdf import PdfReader

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"
TARGETS = {
    "flight-disruption-policy": (4, 6),
    "loyalty-benefits": (3, 4),
    "meal-hotel-assistance": (3, 4),
    "customer-service-escalation": (3, 4),
}


def _text(name: str) -> str:
    reader = PdfReader(str(KNOWLEDGE / f"{name}.pdf"))
    return re.sub(r"\s+", " ", " ".join(page.extract_text() for page in reader.pages))


@pytest.mark.parametrize("name", TARGETS)
def test_pdf_page_count_within_target(name):
    low, high = TARGETS[name]
    pages = len(PdfReader(str(KNOWLEDGE / f"{name}.pdf")).pages)
    assert low <= pages <= high


@pytest.mark.parametrize("name", TARGETS)
def test_pdf_has_governance_metadata(name):
    text = _text(name)
    for field in ("Document ID", "Version", "Effective date", "Policy owner"):
        assert field in text


def test_disruption_policy_contains_hero_rule_and_sections():
    text = _text("flight-disruption-policy")
    assert ("affected passengers may be reaccommodated on an eligible Contoso Air alternative "
            "without a change fee") in text
    assert "Customer Care should attempt to keep the traveling party together" in text
    for heading in ("Rebooking Eligibility", "Change-Fee Waiver", "Same-Day Alternatives",
                    "Connecting Versus Nonstop", "Cabin Handling", "Refund Eligibility", "Escalation Conditions"):
        assert heading in text


def test_loyalty_gold_has_priority_reaccommodation_without_guarantee():
    text = _text("loyalty-benefits")
    assert "Priority reaccommodation during qualifying disruptions" in text
    assert "does not guarantee" in text


def test_escalation_guide_covers_required_situations():
    text = _text("customer-service-escalation").lower()
    for topic in ("accessibility", "unaccompanied minor", "international", "conflicting", "irregular operations",
                  "special circumstances"):
        assert topic in text


def test_disruption_policy_defines_cabin_level_availability():
    text = _text("flight-disruption-policy")
    assert "Comparable cabin" in text
    assert "Seat availability is assessed by cabin" in text
    assert "lowest number available in that cabin on any flight in the itinerary" in text


SOURCES = sorted((KNOWLEDGE / "source").glob("*.md"))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.stem)
def test_policies_are_generic_not_written_for_the_demo(path):
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"\bCT\d{3}\b|CT8K2P|Alex Johnson|CUST-\d{4}", text)


def test_four_policy_sources_back_the_pdfs():
    assert {p.stem for p in SOURCES} == set(TARGETS)
