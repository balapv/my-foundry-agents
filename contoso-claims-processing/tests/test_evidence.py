"""Evidence package tests: estimate arithmetic, PDFs, photographs and the manifest."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
from decimal import Decimal

import pytest
from PIL import Image
from pypdf import PdfReader

from conftest import EVIDENCE_DIR, HERO_EVIDENCE_DIR, HERO_SOURCE_DIR, SOURCE_DIR, forbidden_keys_in

# Wording that would label the scenario or pre-empt the reviewer's conclusion. The photo
# provenance file (photos.json) is deliberately excluded: it records generation prompts.
LABELLING_WORDS = re.compile(
    r"suspic|anomal|unsupported|mismatch|discrepan|fraud|inconsisten|no damage|not damaged|undamaged|unrelated",
    re.IGNORECASE,
)


def load_builder():
    spec = importlib.util.spec_from_file_location("build_evidence", EVIDENCE_DIR / "build_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return load_builder()


@pytest.fixture(scope="module")
def sources():
    return {
        name: json.loads((HERO_SOURCE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("claim-form", "police-report", "repair-estimate", "photos")
    }


@pytest.fixture(scope="module")
def manifest():
    return json.loads((HERO_EVIDENCE_DIR / "evidence-manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def estimate(builder, sources, data):
    return builder.compute_estimate(sources["repair-estimate"], data["facilities"]["RF-104"])


def pdf_text(file_name: str) -> list[str]:
    reader = PdfReader(HERO_EVIDENCE_DIR / file_name)
    return [" ".join(page.extract_text().split()) for page in reader.pages]


def amount(value) -> str:
    return f"{Decimal(str(value)):,.2f}"


# ---------------------------------------------------------------------------
# Repair estimate arithmetic
# ---------------------------------------------------------------------------


def test_estimate_lines_and_total(estimate, sources, data):
    facility = data["facilities"]["RF-104"]
    rates = facility["laborRates"]
    labor_rate = {"Body": rates["bodyPerHour"], "Mech": rates["mechanicalPerHour"], "Frame": rates["framePerHour"]}
    source_lines = sources["repair-estimate"]["lines"]
    assert len(estimate["lines"]) == len(source_lines) == 31
    refinish_hours = Decimal("0")
    total = Decimal("0")
    for line, src in zip(estimate["lines"], source_lines):
        price = Decimal(str(src["unitPrice"])) * src["quantity"]
        labor = Decimal(str(src["laborHours"])) * Decimal(str(labor_rate[src["laborType"]])) if src["laborHours"] else Decimal(0)
        refinish = Decimal(str(src["refinishHours"])) * Decimal(str(rates["refinishPerHour"]))
        assert line["amount"] == (price + labor + refinish).quantize(Decimal("0.01")), line["line"]
        refinish_hours += Decimal(str(src["refinishHours"]))
        total += line["amount"]
    paint_materials = (refinish_hours * Decimal(str(rates["paintMaterialsPerRefinishHour"]))).quantize(Decimal("0.01"))
    assert estimate["paintMaterials"] == paint_materials == Decimal("588.80")
    assert estimate["tax"] == Decimal("0.00")
    assert total + paint_materials == estimate["grandTotal"] == Decimal("7850.00")
    category_sum = (
        estimate["parts"] + sum(estimate["laborAmounts"].values()) + estimate["refinishAmount"]
        + estimate["paintMaterials"] + estimate["sublet"] + estimate["materials"] + estimate["tax"]
    )
    assert category_sum == Decimal("7850.00")
    assert Decimal(str(data["claims"]["CLM-10482"]["estimate"]["grossAmount"])) == Decimal("7850.00")


def test_estimate_includes_the_left_headlamp_line_as_an_ordinary_line(estimate, sources):
    first = estimate["lines"][0]
    assert first["section"] == "FRONT LAMPS"
    assert first["description"] == "Headlamp assy LT, LED"
    assert first["amount"] == Decimal("1240.00")
    # Every line carries the same keys: nothing distinguishes this line from the others.
    assert {frozenset(line) for line in sources["repair-estimate"]["lines"]} == {frozenset(source_line) for source_line in sources["repair-estimate"]["lines"][:1]}
    others = [line for line in estimate["lines"][1:] if "LT" in line["description"].split() or "front" in line["section"].lower()]
    assert others == [], "only the headlamp line refers to the front or left side"


def test_estimate_rejects_a_misstated_total(builder, sources, data):
    altered = json.loads(json.dumps(sources["repair-estimate"]))
    altered["statedGrandTotal"] = 7850.01
    with pytest.raises(builder.BuildError):
        builder.compute_estimate(altered, data["facilities"]["RF-104"])


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def test_every_pdf_page_carries_the_synthetic_footer(builder, manifest):
    for doc in manifest["documents"]:
        if doc["mediaType"] == "application/pdf":
            for number, text in enumerate(pdf_text(doc["fileName"]), start=1):
                assert builder.SYNTHETIC_FOOTER in text, f"{doc['fileName']} page {number}"


def test_claim_form_matches_the_claim_record(data, sources):
    claim = data["claims"]["CLM-10482"]
    text = " ".join(pdf_text("claim-form.pdf"))
    narrative = next(s["paragraph"] for s in sources["claim-form"]["sections"] if "paragraph" in s)
    assert " ".join(narrative.split()) in text
    assert claim["description"] == narrative
    for token in ("CLM-10482", "Jordan Lee", "PAP-4471920", "0CTTS2UA9RM318057", "MHPD-26-018734", "Casey Morgan",
                  "Rear bumper; Right rear quarter panel; Right tail lamp"):
        assert token in text, token
    assert claim["reportedDamage"]["summary"] in text


def test_police_report_records_the_collision(data):
    text = " ".join(pdf_text("police-report.pdf"))
    claim = data["claims"]["CLM-10482"]
    for token in (claim["policeReport"]["reportNumber"], claim["policeReport"]["agency"], "0CTTS2UA9RM318057",
                  "Jordan Lee", "Casey Morgan", "11/12/2026", "unsafe backing"):
        assert token in text, token
    assert re.search(r"right rear", text, re.IGNORECASE)


def test_repair_estimate_pdf_shows_every_line_and_the_total(estimate):
    text = " ".join(pdf_text("repair-estimate.pdf"))
    for token in ("EST-HL-26-3391", "CLM-10482", "0CTTS2UA9RM318057", "Harborline", "Headlamp assy LT, LED"):
        assert token in text, token
    for line in estimate["lines"]:
        assert amount(line["amount"]) in text, f"line {line['line']} amount {line['amount']}"
    assert "7,850.00" in text and "1,240.00" in text and "588.80" in text


def test_documents_do_not_label_the_scenario(manifest):
    for doc in manifest["documents"]:
        if doc["mediaType"] == "application/pdf":
            hits = LABELLING_WORDS.findall(" ".join(pdf_text(doc["fileName"])))
            assert hits == [], (doc["fileName"], hits)
    for name in ("claim-form.json", "police-report.json", "repair-estimate.json"):
        text = (HERO_SOURCE_DIR / name).read_text(encoding="utf-8")
        assert LABELLING_WORDS.findall(text) == [], name
    assert LABELLING_WORDS.findall((HERO_EVIDENCE_DIR / "evidence-manifest.json").read_text(encoding="utf-8")) == []
    assert forbidden_keys_in(manifest) == []


def test_pdf_metadata_is_generic():
    for name in ("claim-form.pdf", "police-report.pdf", "repair-estimate.pdf"):
        meta = PdfReader(HERO_EVIDENCE_DIR / name).metadata or {}
        values = " ".join(str(v) for v in meta.values())
        assert "Users" not in values and "\\" not in values, (name, values)


# ---------------------------------------------------------------------------
# Manifest and photographs
# ---------------------------------------------------------------------------


def test_manifest_matches_the_claim_document_index(manifest, data):
    claim = data["claims"]["CLM-10482"]
    assert manifest["claimId"] == "CLM-10482" and manifest["synthetic"] is True
    assert [d["documentId"] for d in manifest["documents"]] == [d["documentId"] for d in claim["documents"]]
    for entry, doc in zip(manifest["documents"], claim["documents"]):
        for key in ("documentType", "title", "source", "receivedAt"):
            assert entry[key] == doc[key], (entry["documentId"], key)


def test_manifest_files_exist_and_match(manifest):
    listed = set()
    for entry in manifest["documents"]:
        path = HERO_EVIDENCE_DIR / entry["fileName"]
        assert path.is_file(), entry["fileName"]
        content = path.read_bytes()
        assert len(content) == entry["bytes"], entry["fileName"]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"], entry["fileName"]
        if entry["mediaType"] == "application/pdf":
            assert content.startswith(b"%PDF-")
            assert len(PdfReader(io.BytesIO(content)).pages) == entry["pageCount"]
        listed.add(path.relative_to(HERO_EVIDENCE_DIR).as_posix())
    on_disk = {p.relative_to(HERO_EVIDENCE_DIR).as_posix() for p in HERO_EVIDENCE_DIR.rglob("*") if p.is_file()}
    assert on_disk == listed | {"evidence-manifest.json"}, "evidence folder contains unlisted or missing files"


def test_photographs_are_clean_jpegs(manifest):
    photos = [e for e in manifest["documents"] if e["documentType"] == "Photograph"]
    assert len(photos) == 5
    for entry in photos:
        content = (HERO_EVIDENCE_DIR / entry["fileName"]).read_bytes()
        with Image.open(io.BytesIO(content)) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
            assert image.size == (entry["widthPx"], entry["heightPx"]) == (1536, 1024)
            assert not image.getexif(), f"{entry['fileName']} carries EXIF metadata"
            assert "comment" not in image.info and "xmp" not in image.info
        assert b"Exif" not in content[:4096] and b"http://ns.adobe.com/xap" not in content


def test_photo_provenance_matches_manifest(sources, manifest):
    provenance = sources["photos"]
    assert provenance["synthetic"] is True
    by_id = {e["documentId"]: e for e in manifest["documents"]}
    for photo in provenance["photos"]:
        assert by_id[photo["documentId"]]["fileName"] == photo["fileName"]
        assert by_id[photo["documentId"]]["title"] == photo["title"]
        assert re.fullmatch(r"[0-9a-f]{64}", photo["sourceSha256"])
    assert "photos.json" not in {e["fileName"] for e in manifest["documents"]}


def test_every_claim_document_reference_resolves_for_claims_with_evidence(data):
    folders = {p.name for p in EVIDENCE_DIR.iterdir() if p.is_dir() and p.name.startswith("CLM-")}
    assert folders == {p.name for p in SOURCE_DIR.iterdir() if p.is_dir()}
    for claim_id in folders:
        assert claim_id in data["claims"]


def test_evidence_build_is_current_and_deterministic(builder):
    assert builder.main(["--check"]) == 0
    first = builder.build_claim(HERO_SOURCE_DIR, builder.load_data(), None)
    second = builder.build_claim(HERO_SOURCE_DIR, builder.load_data(), None)
    assert first == second
    for path, content in first.items():
        assert path.read_bytes() == content, path.name


# ---------------------------------------------------------------------------
# Every evidence package (hero and evaluation claims)
# ---------------------------------------------------------------------------

PACKAGE_IDS = sorted(p.name for p in SOURCE_DIR.iterdir() if p.is_dir())


def load_package(claim_id: str) -> tuple[dict, dict]:
    source_dir = SOURCE_DIR / claim_id
    sources = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(source_dir.glob("*.json"))}
    manifest = json.loads((EVIDENCE_DIR / claim_id / "evidence-manifest.json").read_text(encoding="utf-8"))
    return sources, manifest


def test_evaluation_packages_exist_alongside_the_hero():
    assert "CLM-10482" in PACKAGE_IDS and len(PACKAGE_IDS) >= 2


@pytest.mark.parametrize("claim_id", PACKAGE_IDS)
def test_package_manifest_matches_index_and_files(claim_id, data):
    _, manifest = load_package(claim_id)
    claim = data["claims"][claim_id]
    folder = EVIDENCE_DIR / claim_id
    assert manifest["claimId"] == claim_id and manifest["synthetic"] is True
    assert [d["documentId"] for d in manifest["documents"]] == [d["documentId"] for d in claim["documents"]]
    listed = set()
    for entry, doc in zip(manifest["documents"], claim["documents"]):
        for key in ("documentType", "title", "source", "receivedAt"):
            assert entry[key] == doc[key], (entry["documentId"], key)
        content = (folder / entry["fileName"]).read_bytes()
        assert len(content) == entry["bytes"] and hashlib.sha256(content).hexdigest() == entry["sha256"], entry["fileName"]
        if entry["mediaType"] == "application/pdf":
            assert len(PdfReader(io.BytesIO(content)).pages) == entry["pageCount"]
        listed.add(entry["fileName"])
    on_disk = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    assert on_disk == listed | {"evidence-manifest.json"}


@pytest.mark.parametrize("claim_id", PACKAGE_IDS)
def test_package_estimate_arithmetic(claim_id, builder, data):
    sources, _ = load_package(claim_id)
    claim = data["claims"][claim_id]
    if "repair-estimate" not in sources:
        assert not any(d["documentType"] == "Repair estimate" for d in claim["documents"])
        return
    facility = data["facilities"][claim["estimate"]["repairFacilityId"]]
    rates = facility["laborRates"]
    labor_rate = {"Body": rates["bodyPerHour"], "Mech": rates["mechanicalPerHour"], "Frame": rates["framePerHour"]}
    result = builder.compute_estimate(sources["repair-estimate"], facility)
    total = Decimal("0")
    for line, src in zip(result["lines"], sources["repair-estimate"]["lines"], strict=True):
        price = Decimal(str(src["unitPrice"])) * src["quantity"]
        labor = Decimal(str(src["laborHours"])) * Decimal(str(labor_rate[src["laborType"]])) if src["laborHours"] else Decimal(0)
        refinish = Decimal(str(src["refinishHours"])) * Decimal(str(rates["refinishPerHour"]))
        assert line["amount"] == (price + labor + refinish).quantize(Decimal("0.01")), (claim_id, line["line"])
        total += line["amount"]
    assert total + result["paintMaterials"] + result["tax"] == result["grandTotal"]
    assert result["grandTotal"] == Decimal(str(claim["estimate"]["grossAmount"]))
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(EVIDENCE_DIR / claim_id / "repair-estimate.pdf").pages)
    assert amount(result["grandTotal"]) in text and claim["estimate"]["estimateId"] in text
    printed = re.search(r"Subtotal ([\d,]+\.\d\d) Sales tax \(.*?\) ([\d.]+)% ([\d,]+\.\d\d)", text)
    assert printed, claim_id
    subtotal, rate, tax = (Decimal(g.replace(",", "")) for g in printed.groups())
    assert (subtotal * rate / 100).quantize(Decimal("0.01")) == tax, "printed tax rate must reproduce the printed tax"

@pytest.mark.parametrize("claim_id", PACKAGE_IDS)
def test_package_content_is_synthetic_and_unlabelled(claim_id, builder):
    sources, manifest = load_package(claim_id)
    for name, source in sources.items():
        if name != "photos":
            assert LABELLING_WORDS.findall(json.dumps(source)) == [], (claim_id, name)
            assert forbidden_keys_in(source) == [], (claim_id, name)
    assert LABELLING_WORDS.findall(json.dumps(manifest)) == [] and forbidden_keys_in(manifest) == []
    for entry in manifest["documents"]:
        if entry["mediaType"] == "application/pdf":
            reader = PdfReader(EVIDENCE_DIR / claim_id / entry["fileName"])
            for page in reader.pages:
                text = " ".join(page.extract_text().split())
                assert builder.SYNTHETIC_FOOTER in text, entry["fileName"]
                assert LABELLING_WORDS.findall(text) == [], (entry["fileName"], LABELLING_WORDS.findall(text))
            meta = " ".join(str(v) for v in (reader.metadata or {}).values())
            assert "Users" not in meta and "\\" not in meta


@pytest.mark.parametrize("claim_id", PACKAGE_IDS)
def test_package_photographs_are_clean_and_traceable(claim_id):
    sources, manifest = load_package(claim_id)
    provenance = sources["photos"]
    assert provenance["claimId"] == claim_id and provenance["synthetic"] is True
    by_id = {e["documentId"]: e for e in manifest["documents"]}
    photo_entries = [e for e in manifest["documents"] if e["documentType"] == "Photograph"]
    assert {p["documentId"] for p in provenance["photos"]} == {e["documentId"] for e in photo_entries}
    rejected = {r["sourceSha256"] for r in provenance["generation"]["rejectedCandidates"]}
    used = [p["sourceSha256"] for p in provenance["photos"]]
    assert len(set(used)) == len(used) and not rejected & set(used)
    for photo in provenance["photos"]:
        entry = by_id[photo["documentId"]]
        assert entry["fileName"] == photo["fileName"] and entry["title"] == photo["title"]
        assert re.fullmatch(r"[0-9a-f]{64}", photo["sourceSha256"]) and photo["prompt"].strip()
        content = (EVIDENCE_DIR / claim_id / photo["fileName"]).read_bytes()
        with Image.open(io.BytesIO(content)) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
            assert image.size == (entry["widthPx"], entry["heightPx"]) == (1536, 1024)
            assert not image.getexif() and "comment" not in image.info and "xmp" not in image.info
    assert "photos.json" not in {e["fileName"] for e in manifest["documents"]}


@pytest.mark.parametrize("claim_id", PACKAGE_IDS)
def test_package_build_is_deterministic(claim_id, builder):
    data = builder.load_data()
    first = builder.build_claim(SOURCE_DIR / claim_id, data, None)
    assert first == builder.build_claim(SOURCE_DIR / claim_id, data, None)
    for path, content in first.items():
        assert path.read_bytes() == content, path.name
