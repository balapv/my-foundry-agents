"""Repository hygiene: no secrets, no real personal data, no local paths, phase boundaries."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfReader

from conftest import ROOT

EXCLUDED_DIRS = {".venv", "venv", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".json", ".md", ".txt", ".ini", ".example", ".gitignore", ".gitattributes", ".ps1", ".sh", "",
                 ".html", ".js", ".mjs", ".css", ".svg"}

SECRET_PATTERNS = {
    "storage account key": re.compile(r"AccountKey=[A-Za-z0-9+/]{20,}"),
    "SAS signature": re.compile(r"[?&]sig=[A-Za-z0-9%]{20,}"),
    "shared access signature": re.compile(r"SharedAccessSignature\s+sr="),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE" + r" KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "instrumentation key": re.compile(r"InstrumentationKey=[0-9a-fA-F-]{36}"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "credential assignment": re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
    ),
}
LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\+Users\\+[A-Za-z]"),
    re.compile(r"/Users/[A-Za-z][\w.-]*/"),
    re.compile(r"/home/[a-z][\w.-]*/"),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE = re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[-.])(\d{3})[-.](\d{4})\b")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
VIN_LIKE = re.compile(r"\b(?=[A-HJ-NPR-Z0-9]{17}\b)(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-HJ-NPR-Z0-9]{17}\b")


# Local, git-ignored state that Phase 2 and Phase 3 tooling legitimately creates. Never committed.
LOCAL_STATE = (".env", ".foundry-state.json", "agent/config.json", ".deploy/", "evaluation/results/", "webapp/.logs/")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def project_files() -> list[Path]:
    """Every file that would be committed: tracked plus untracked files not excluded by .gitignore."""
    listed = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", ".")
    assert listed.returncode == 0, listed.stderr
    files = [ROOT / name for name in listed.stdout.split("\0") if name]
    return sorted(p for p in files if p.is_file() and not EXCLUDED_DIRS.intersection(p.relative_to(ROOT).parts))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES


def readable_text(path: Path) -> str | None:
    """Text content of a source file, or the extracted text of a PDF."""
    if is_text(path):
        return path.read_text(encoding="utf-8")
    if path.suffix == ".pdf":
        reader = PdfReader(path)
        meta = " ".join(str(v) for v in (reader.metadata or {}).values())
        return "\n".join(page.extract_text() for page in reader.pages) + "\n" + meta
    return None


FILES = project_files()
TEXT_FILES = [(rel(p), readable_text(p)) for p in FILES if readable_text(p) is not None]


def test_every_project_file_is_a_known_kind():
    unknown = [rel(p) for p in FILES if not is_text(p) and p.suffix not in {".pdf", ".jpg"}
               and not (p.suffix == ".png" and rel(p).startswith("demo/assets/"))]
    assert unknown == []
    assert any(name.endswith(".pdf") for name, _ in TEXT_FILES)


def test_text_files_are_utf8_without_bom():
    for path in FILES:
        if is_text(path):
            raw = path.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf"), rel(path)
            raw.decode("utf-8")


@pytest.mark.parametrize("name", list(SECRET_PATTERNS))
def test_no_secrets(name):
    pattern = SECRET_PATTERNS[name]
    hits = [file for file, text in TEXT_FILES if pattern.search(text)]
    assert hits == [], f"{name} found in {hits}"


def test_no_local_paths_in_text_documents_or_images():
    for path in FILES:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="ignore")
        for pattern in LOCAL_PATH_PATTERNS:
            assert not pattern.search(text), f"{rel(path)}: {pattern.pattern}"
    for file, text in TEXT_FILES:
        for pattern in LOCAL_PATH_PATTERNS:
            assert not pattern.search(text), f"{file}: {pattern.pattern}"


def test_env_example_holds_no_values_and_local_state_is_never_committable():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            assert value == "", f".env.example sets a value for {key}"
    committable = {rel(p) for p in FILES}
    for entry in LOCAL_STATE:
        probe = entry + "probe.json" if entry.endswith("/") else entry
        assert git("check-ignore", "-q", "--no-index", probe).returncode == 0, f"{entry} is not git-ignored"
        assert not any(name == entry or (entry.endswith("/") and name.startswith(entry)) for name in committable), f"{entry} would be committed"
    tracked = git("ls-files", "--cached", "--", *LOCAL_STATE).stdout.split()
    assert tracked == [], f"local state is tracked: {tracked}"


def test_gitignore_covers_local_configuration():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for required in (".env", ".venv/", "__pycache__/", ".pytest_cache/", ".foundry-state.json", "evaluation/results/", ".deploy/",
                     "webapp/.logs/"):
        assert required in lines, required


def test_contact_details_use_reserved_fictional_ranges():
    for file, text in TEXT_FILES:
        for match in EMAIL.finditer(text):
            assert match.group(1).lower() in {"example.com", "example.org", "example.net"}, f"{file}: {match.group(0)}"
        for match in PHONE.finditer(text):
            exchange, line = match.groups()
            assert exchange == "555" and line.startswith("01"), f"{file}: {match.group(0)}"
        assert not SSN.search(text), f"{file}: SSN-like value {SSN.search(text).group(0)}"


def test_vehicle_identification_numbers_are_synthetic():
    for file, text in TEXT_FILES:
        for match in VIN_LIKE.finditer(text):
            assert match.group(0).startswith("0"), f"{file}: {match.group(0)} looks like a real VIN"


def test_phase_boundaries():
    names = {rel(p) for p in FILES}
    # Phase 3 is the Claims Review application under webapp/; there is no second application.
    assert not any(name.startswith("app/") for name in names), "unexpected second application folder"
    # Phase 4 presentation media (screenshots, architecture visual) live only in demo/assets/; no video or animation.
    media = re.compile(r"(?i)\.(png|gif|mp4|mov|webm)$")
    assert [n for n in names if media.search(n) and not (n.startswith("demo/assets/") and n.endswith(".png"))] == []
    # The browser application loads only its own assets (no CDNs or external fonts/scripts).
    for file, text in TEXT_FILES:
        if file.startswith("webapp/frontend/") and file.endswith((".html", ".js", ".css")):
            assert not re.search(r"(?i)\b(src|href)\s*=\s*[\"']?(https?:)?//|@import\s+url\(\s*[\"']?https?:|\bimport\b[^;\n]*[\"']https?:", text), file
    # The Claims Operations API stays a plain factual service: no model or agent SDKs.
    tools_requirements = (ROOT / "tools" / "requirements.txt").read_text(encoding="utf-8").lower()
    for package in ("azure-ai", "openai", "azure-identity"):
        assert package not in tools_requirements, package
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower() + tools_requirements
    for package in ("semantic-kernel", "langchain", "autogen", "agent-framework", "opencv", "pytesseract", "azure-ai-vision"):
        assert package not in requirements, package
    other_demo = ("contoso" + "-air", "contoso" + "_air")
    for file, text in TEXT_FILES:
        if file.endswith(".py"):
            assert not any(name in text for name in other_demo), f"{file} depends on the Contoso Air demo"


def test_demo_package_is_complete_and_committable():
    """Phase 4: every presenter document and fallback asset named in demo/baseline.json ships with the repository."""
    import json

    names = {rel(p) for p in FILES}
    base = json.loads((ROOT / "demo" / "baseline.json").read_text(encoding="utf-8"))
    expected = base["demoDocuments"] + base["fallbackAssets"] + [
        "scripts/setup.ps1", "scripts/setup.sh", "scripts/validate_demo.py", "scripts/reset_demo.py"]
    assert [name for name in expected if name not in names] == []
    transcript = (ROOT / "demo" / "fallback-transcript.md").read_text(encoding="utf-8").lower()
    assert "validated previous run" in transcript


def test_demo_baseline_fingerprints_match_the_validated_files():
    """demo/baseline.json pins the files the validated agent version was tested against."""
    import hashlib
    import json

    base = json.loads((ROOT / "demo" / "baseline.json").read_text(encoding="utf-8"))
    changed = [name for name, digest in base["sha256"].items()
               if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    assert changed == []


def test_presenter_tooling_never_changes_foundry_or_azure_resources():
    """Setup, readiness and reset are read-only toward Foundry and Azure."""
    forbidden = re.compile(r"create_version|\.delete\(|vector_stores\.(create|delete)|files\.(create|delete)|"
                           r"create_agent\.py[^\n]*--(delete|publish)|az\s+(group|containerapp|acr)\s+delete")
    for name in ("scripts/demo_readiness.py", "scripts/validate_demo.py", "scripts/reset_demo.py",
                 "scripts/setup.ps1", "scripts/setup.sh"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not forbidden.search(text), name
