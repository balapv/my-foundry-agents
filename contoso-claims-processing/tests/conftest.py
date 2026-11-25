"""Shared fixtures and helpers for the Contoso Claims Processing tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EVIDENCE_DIR = ROOT / "evidence"
HERO_EVIDENCE_DIR = EVIDENCE_DIR / "CLM-10482"
SOURCE_DIR = EVIDENCE_DIR / "source"
HERO_SOURCE_DIR = SOURCE_DIR / "CLM-10482"

# Keys that would encode a conclusion the claims review agent must reach itself.
FORBIDDEN_KEYS = {
    "recommended_decision",
    "manual_review_required",
    "suspicious",
    "anomaly",
    "fraud_risk",
    "unsupported_item",
    "evidence_mismatch",
}
# Any key containing one of these fragments (case- and separator-insensitive) is also rejected.
FORBIDDEN_KEY_FRAGMENTS = (
    "recommend",
    "decision",
    "manualreview",
    "suspic",
    "anomal",
    "fraud",
    "risk",
    "score",
    "unsupported",
    "mismatch",
    "discrepan",
    "flag",
    "verdict",
    "approv",
    "deny",
    "denial",
    "eligib",
    "covered",
    "likelihood",
)


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def forbidden_keys_in(obj, path: str = "$") -> list[str]:
    """Return the paths of every dictionary key that names an assessment or conclusion."""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = normalize_key(key)
            if key in FORBIDDEN_KEYS or any(fragment in normalized for fragment in FORBIDDEN_KEY_FRAGMENTS):
                found.append(f"{path}.{key}")
            found.extend(forbidden_keys_in(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            found.extend(forbidden_keys_in(item, f"{path}[{index}]"))
    return found


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def data() -> dict:
    """All data files, indexed by ID."""

    def index(file_name: str, list_key: str, id_key: str) -> dict:
        return {r[id_key]: r for r in load_json(DATA_DIR / file_name)[list_key]}

    return {
        "customers": index("customers.json", "customers", "customerId"),
        "policies": index("policies.json", "policies", "policyId"),
        "vehicles": index("vehicles.json", "vehicles", "vehicleId"),
        "claims": index("claims.json", "claims", "claimId"),
        "archived": index("claim-history.json", "archivedClaims", "claimId"),
        "facilities": index("repair-facilities.json", "repairFacilities", "repairFacilityId"),
    }


@pytest.fixture(scope="session")
def raw_files() -> dict[str, dict]:
    return {path.name: load_json(path) for path in sorted(DATA_DIR.glob("*.json"))}
