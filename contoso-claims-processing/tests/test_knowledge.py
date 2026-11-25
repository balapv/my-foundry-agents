"""Knowledge corpus tests: the four Contoso Insurance guidance documents uploaded to File Search.

The guidance must read as reusable company policy. It must not mention any synthetic claim,
customer, vehicle or repair facility, and it must not encode the hero scenario's answer.
"""

from __future__ import annotations

import importlib.util
import re

import pytest
from pypdf import PdfReader

from conftest import ROOT

KNOWLEDGE_DIR = ROOT / "knowledge"
SOURCE_DIR = KNOWLEDGE_DIR / "source"

EXPECTED = {
    "claims-handling-guidelines": ("Auto Claims Handling Guidelines", "CI-CLM-GL-101"),
    "auto-coverage-guidance": ("Personal Auto Coverage Guidance", "CI-CLM-CV-204"),
    "repair-estimate-review": ("Repair Estimate Review Guidelines", "CI-CLM-ER-310"),
    "claims-escalation-guidance": ("Claims Escalation and Special Investigation Guidance", "CI-CLM-SI-420"),
}

# Topics the guidance must establish (document, description, pattern over whitespace-normalized text).
REQUIRED_TOPICS = [
    ("claims-handling-guidelines", "date-of-loss validation", r"date-of-loss validation"),
    ("auto-coverage-guidance", "active policy on the date of loss", r"date of loss is on or after the term effective date"),
    ("auto-coverage-guidance", "deductible handling", r"How deductibles apply"),
    ("claims-handling-guidelines", "evidence requirements", r"Evidence requirements"),
    ("repair-estimate-review", "estimate and evidence consistency", r"Estimate and evidence consistency"),
    ("claims-handling-guidelines", "supplemental evidence", r"Requests for supplemental evidence"),
    ("repair-estimate-review", "items the evidence does not establish", r"Line items not established by the current evidence"),
    ("repair-estimate-review", "corrected or revised estimate", r"corrected or revised estimate"),
    ("repair-estimate-review", "photographic limitations", r"Limits of photographic evidence"),
    ("claims-handling-guidelines", "absence in a photo is not proof", r"not proof that minor or concealed damage does not exist"),
    ("repair-estimate-review", "continue supported processing", r"Continuing supported processing"),
    ("claims-escalation-guidance", "ordinary manual review", r"Ordinary manual review"),
    ("claims-escalation-guidance", "special investigations criteria", r"Criteria for a Special Investigations referral"),
    ("claims-escalation-guidance", "ordinary review versus special investigation", r"Ordinary review compared with Special Investigations"),
    ("claims-handling-guidelines", "human decision authority", r"They do not approve, deny, authorize or pay claims"),
    ("claims-escalation-guidance", "no unsupported fraud accusations", r"do not accuse customers, claimants, repair facilities or other parties of fraud"),
]

# Hero-specific content that would leak the expected answer into reusable guidance.
HERO_LEAKS = re.compile(
    r"CLM-10482|Jordan\s+Lee|1,240|\b1240\b|head\s?lamp|front[- ]left|left[- ]front|Trailstar|Harborline|EST-HL"
    r"|PAP-4471920|VEH-58213|CUST-24817|MHPD|Casey\s+Morgan",
    re.IGNORECASE,
)
# Build provenance or evaluation material must never be part of the agent's knowledge.
PROVENANCE = re.compile(r"IMPLEMENTATION-SPEC|hero|expected behavio|test case|evaluation scenario|image[- ]generation|prompt", re.IGNORECASE)
RECORD_ID = re.compile(r"(?<!CI-)\b(?:CLM|CUST|PAP|VEH|RF|EST|DOC)-[A-Z]{0,3}-?\d{2,}")


def load_builder():
    spec = importlib.util.spec_from_file_location("build_pdfs", KNOWLEDGE_DIR / "build_pdfs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return load_builder()


def normalized(text: str) -> str:
    return " ".join(text.split())


def markdown(name: str) -> str:
    return (SOURCE_DIR / f"{name}.md").read_text(encoding="utf-8")


def pdf_text(name: str) -> str:
    return normalized(" ".join(page.extract_text() for page in PdfReader(KNOWLEDGE_DIR / f"{name}.pdf").pages))


def test_exactly_the_four_documents_are_present(builder):
    assert set(builder.DOCUMENTS) == set(EXPECTED)
    assert {p.stem for p in SOURCE_DIR.glob("*.md")} == set(EXPECTED)
    assert {p.stem for p in KNOWLEDGE_DIR.glob("*.pdf")} == set(EXPECTED)


def test_pdfs_are_current_deterministic_and_within_page_targets(builder):
    assert builder.check() == []
    for name in EXPECTED:
        assert builder.render_pdf(name) == builder.render_pdf(name) == (KNOWLEDGE_DIR / f"{name}.pdf").read_bytes()


@pytest.mark.parametrize("name", list(EXPECTED))
def test_document_metadata(name, builder):
    title, doc_id = EXPECTED[name]
    meta = builder.document_meta(markdown(name))
    assert meta["Title"] == title and meta["Document ID"] == doc_id
    assert re.fullmatch(r"\d+\.\d+", meta["Version"])
    assert meta["Effective date"] and meta["Policy owner"] and meta["Approved by"]
    latest = re.search(r"^\|\s*(\d+\.\d+)\s*\|", markdown(name).split("## Revision history")[1], re.MULTILINE).group(1)
    assert latest == meta["Version"], "revision history does not start with the current version"
    info = PdfReader(KNOWLEDGE_DIR / f"{name}.pdf").metadata
    assert info.title == title and doc_id in info.subject


@pytest.mark.parametrize("name", list(EXPECTED))
def test_pdf_contains_every_heading_and_footer(name):
    text = pdf_text(name)
    for heading in re.findall(r"^#{1,3} (.+)$", markdown(name), re.MULTILINE):
        assert normalized(heading.replace("**", "")) in text, heading
    assert "Synthetic demo content" in text


@pytest.mark.parametrize("name", list(EXPECTED))
def test_sections_are_numbered_sequentially(name):
    numbers = [int(n) for n in re.findall(r"^## (\d+)\. ", markdown(name), re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1))


def test_cross_references_resolve():
    ids = {doc_id for _, doc_id in EXPECTED.values()}
    for name in EXPECTED:
        for ref in re.findall(r"CI-CLM-[A-Z]{2}-\d{3}", markdown(name)):
            assert ref in ids, (name, ref)
        for ref, section in re.findall(r"(CI-CLM-[A-Z]{2}-\d{3})[^.\n]{0,40}?Section (\d+)", markdown(name)):
            target = next(n for n, (_, d) in EXPECTED.items() if d == ref)
            assert re.search(rf"^## {section}\. ", markdown(target), re.MULTILINE), (name, ref, section)


@pytest.mark.parametrize("name, description, pattern", REQUIRED_TOPICS, ids=[t[1] for t in REQUIRED_TOPICS])
def test_required_topic_is_established(name, description, pattern):
    assert re.search(pattern, normalized(markdown(name)), re.IGNORECASE), description
    assert re.search(pattern, pdf_text(name), re.IGNORECASE), f"{description} (PDF)"


@pytest.mark.parametrize("name", list(EXPECTED))
def test_guidance_does_not_encode_the_hero_scenario(name):
    for text in (markdown(name), pdf_text(name)):
        assert HERO_LEAKS.findall(text) == [], HERO_LEAKS.findall(text)
        assert PROVENANCE.findall(text) == [], PROVENANCE.findall(text)
        assert RECORD_ID.findall(text) == [], RECORD_ID.findall(text)


def test_guidance_names_no_synthetic_customer_or_facility(data):
    corpus = " ".join(markdown(name) + " " + pdf_text(name) for name in EXPECTED)
    for customer in data["customers"].values():
        assert customer["fullName"] not in corpus, customer["customerId"]
    for facility in data["facilities"].values():
        assert facility["name"] not in corpus, facility["repairFacilityId"]
