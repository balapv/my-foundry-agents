"""Claim facts and the evidence catalog shown in the workspace.

Everything here is display data: facts read from the Claims Operations API and metadata read from
the claim's evidence manifest. Nothing here interprets coverage, compares evidence or assesses an
estimate; the Foundry agent does that.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import common

CLAIM_ID = re.compile(r"^CLM-\d{5}$")
DOCUMENT_ID = re.compile(r"^DOC-\d{5}-\d{2}$")

# Claims Operations API routes used for the claim summary (tools/openapi.json).
ROUTES = {
    "get_claim": "/claims/{id}",
    "get_policy": "/policies/{id}",
    "get_vehicle": "/vehicles/{id}",
}


class NotFound(Exception):
    """The claim, document or guidance item does not exist (or the identifier is invalid)."""


class EvidenceIntegrityError(Exception):
    """An evidence file is missing, outside the claim folder, of an unexpected type, or fails its hash."""


class FactsUnavailable(Exception):
    """The Claims Operations API returned an error or could not be reached."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Claims Operations API client
# ---------------------------------------------------------------------------


class ClaimsFacts:
    """Reads business facts from the Claims Operations API.

    With a base URL (CLAIMS_API_BASE_URL, or TOOLS_API_BASE_URL) the facts come from the deployed API the
    agent also calls. Without one, the same API code (tools/main.py) is called in-process over the same
    synthetic data, which keeps local development and tests offline.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout

    @property
    def mode(self) -> str:
        return "http" if self.base_url else "in-process"

    def fetch(self, operation: str, record_id: str) -> dict[str, Any]:
        path = ROUTES[operation].format(id=urllib.parse.quote(record_id, safe=""))
        body = self._http(path) if self.base_url else self._local(operation, record_id)
        if not isinstance(body, dict):
            raise FactsUnavailable("INVALID_RESPONSE")
        if isinstance(body.get("error"), dict):
            raise FactsUnavailable(str(body["error"].get("code") or "ERROR"))
        return body

    def _http(self, path: str) -> Any:
        request = urllib.request.Request(self.base_url + path, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - configured https URL
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode("utf-8"))
            except (ValueError, OSError):
                raise FactsUnavailable(f"HTTP_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            raise FactsUnavailable("UNREACHABLE") from exc

    @staticmethod
    def _local(operation: str, record_id: str) -> Any:
        from tools import main as claims_api

        result = getattr(claims_api, operation)(record_id)
        if hasattr(result, "body"):  # an error JSONResponse
            return json.loads(bytes(result.body).decode("utf-8"))
        return result


# ---------------------------------------------------------------------------
# Evidence manifest and files
# ---------------------------------------------------------------------------


def claim_folder(claim_id: str) -> Path:
    if not CLAIM_ID.fullmatch(claim_id or ""):
        raise NotFound("invalid claim ID")
    return (Path(common.EVIDENCE_DIR) / claim_id).resolve()


def has_evidence_package(claim_id: str) -> bool:
    return (claim_folder(claim_id) / "evidence-manifest.json").is_file()


def load_manifest(claim_id: str) -> dict[str, Any] | None:
    """The claim's evidence manifest, or None when the claim has no evidence package."""
    path = claim_folder(claim_id) / "evidence-manifest.json"
    if not path.is_file():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("claimId") != claim_id:
        raise EvidenceIntegrityError(f"evidence-manifest.json for {claim_id} names {manifest.get('claimId')}")
    return manifest


def evidence_catalog(claim_id: str, manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Browser-safe metadata for each evidence item: no file names, paths or hashes."""
    items = []
    for entry in (manifest or {}).get("documents", []):
        is_pdf = entry["mediaType"] == "application/pdf"
        item = {
            "documentId": entry["documentId"],
            "documentType": entry["documentType"],
            "title": entry["title"],
            "source": entry.get("source"),
            "receivedAt": entry.get("receivedAt"),
            "kind": "pdf" if is_pdf else "photo",
            "url": f"/api/claims/{claim_id}/evidence/{entry['documentId']}",
        }
        if is_pdf:
            item["pageCount"] = entry.get("pageCount")
        else:
            item["widthPx"], item["heightPx"] = entry.get("widthPx"), entry.get("heightPx")
        items.append(item)
    return items


def read_evidence(claim_id: str, document_id: str) -> tuple[bytes, str, str]:
    """Bytes, media type and download name of one evidence item, looked up through the manifest only."""
    if not DOCUMENT_ID.fullmatch(document_id or ""):
        raise NotFound("invalid document ID")
    folder = claim_folder(claim_id)
    manifest = load_manifest(claim_id)
    entry = next((d for d in (manifest or {}).get("documents", []) if d.get("documentId") == document_id), None)
    if entry is None:
        raise NotFound("document not in manifest")
    path = (folder / entry["fileName"]).resolve()
    if folder not in path.parents:
        raise EvidenceIntegrityError(f"{document_id}: manifest file name resolves outside the claim folder")
    if entry["mediaType"] not in common.EVIDENCE_MEDIA_TYPES:
        raise EvidenceIntegrityError(f"{document_id}: unsupported media type {entry['mediaType']}")
    if not path.is_file():
        raise EvidenceIntegrityError(f"{document_id}: {entry['fileName']} is missing")
    content = path.read_bytes()
    if common.sha256(content) != entry["sha256"]:
        raise EvidenceIntegrityError(f"{document_id}: {entry['fileName']} does not match its manifest hash")
    return content, entry["mediaType"], path.name


# ---------------------------------------------------------------------------
# Company guidance (the same PDFs indexed by File Search)
# ---------------------------------------------------------------------------


def _guidance_title(slug: str) -> str:
    source = Path(common.KNOWLEDGE_DIR) / "source" / f"{slug}.md"
    if source.is_file():
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return slug.replace("-", " ").title()


def guidance_catalog() -> list[dict[str, str]]:
    return [{"guidanceId": Path(name).stem, "title": _guidance_title(Path(name).stem),
             "url": f"/api/guidance/{Path(name).stem}"} for name in common.KNOWLEDGE_FILES]


def read_guidance(guidance_id: str) -> tuple[bytes, str]:
    allowed = {Path(name).stem: name for name in common.KNOWLEDGE_FILES}
    if guidance_id not in allowed:
        raise NotFound("unknown guidance document")
    path = Path(common.KNOWLEDGE_DIR) / allowed[guidance_id]
    if not path.is_file():
        raise NotFound("guidance PDF not built")
    return path.read_bytes(), path.name


# ---------------------------------------------------------------------------
# Claim workspace
# ---------------------------------------------------------------------------


def _try(facts: ClaimsFacts, operation: str, record_id: str | None, unavailable: list[str]) -> dict[str, Any] | None:
    if not record_id:
        return None
    try:
        return facts.fetch(operation, record_id)
    except FactsUnavailable as exc:
        unavailable.append(exc.code)
        return None


def claim_workspace(facts: ClaimsFacts, claim_id: str) -> dict[str, Any]:
    """Claim summary, policy facts, evidence catalog and guidance list for one claim (display only)."""
    manifest = load_manifest(claim_id)
    unavailable: list[str] = []
    claim_body = _try(facts, "get_claim", claim_id, unavailable)
    if claim_body is None and manifest is None:
        if unavailable == ["CLAIM_NOT_FOUND"] or "INVALID_CLAIM_ID" in unavailable:
            raise NotFound("claim not found")
    claim = (claim_body or {}).get("claim") or {}
    policy_body = _try(facts, "get_policy", claim.get("policyId"), unavailable)
    vehicle_body = _try(facts, "get_vehicle", claim.get("vehicleId"), unavailable)
    policy = (policy_body or {}).get("policy") or {}
    vehicle = (vehicle_body or {}).get("vehicle") or {}
    listed = next((v for v in policy.get("vehicles", []) if v.get("vehicleId") == claim.get("vehicleId")), {})
    coverages = listed.get("coverages", [])
    collision = next((c for c in coverages if c.get("coverageCode") == "COLL"), None)
    estimate = claim.get("estimate") or {}
    facility = (claim_body or {}).get("repairFacility") or {}

    vehicle_text = None
    if vehicle:
        vehicle_text = " ".join(str(vehicle[k]) for k in ("year", "make", "model", "trim", "drivetrain") if vehicle.get(k))

    summary = {
        "claimId": claim_id,
        "policyholder": ((policy_body or {}).get("policyholder") or {}).get("fullName")
        or ((vehicle_body or {}).get("owner") or {}).get("fullName"),
        "vehicle": vehicle_text,
        "vehicleColor": vehicle.get("exteriorColor"),
        "lossDate": claim.get("lossDate"),
        "lossTime": claim.get("lossTime"),
        "lossTimeZone": claim.get("lossTimeZone"),
        "lossLocation": (claim.get("lossLocation") or {}).get("description"),
        "claimType": claim.get("claimType"),
        "causeOfLoss": claim.get("causeOfLoss"),
        "claimStatus": claim.get("status"),
        "repairFacility": facility.get("name"),
        "estimateId": estimate.get("estimateId"),
        "estimateTotal": estimate.get("grossAmount"),
        "collisionDeductible": collision.get("deductible") if collision else None,
        "policyId": claim.get("policyId"),
    }
    policy_view = None
    if policy:
        policy_view = {
            "policyId": policy.get("policyId"),
            "productName": policy.get("productName"),
            "policyStatus": policy.get("status"),
            "termEffectiveDate": policy.get("termEffectiveDate"),
            "termExpirationDate": policy.get("termExpirationDate"),
            "lossPayee": listed.get("lossPayee"),
            "vehicleCoverages": [_coverage(c) for c in coverages],
            "policyCoverages": [_coverage(c) for c in policy.get("policyCoverages", [])],
        }
    return {
        "claimId": claim_id,
        "recordsAsOf": (claim_body or {}).get("recordsAsOf"),
        "recordsAvailable": claim_body is not None and not unavailable,
        "summary": summary,
        "policy": policy_view,
        "evidence": evidence_catalog(claim_id, manifest),
        "guidance": guidance_catalog(),
    }


def _coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "coverageName": coverage.get("coverageName"),
        "deductible": coverage.get("deductible"),
        "limits": [{"limitType": l.get("limitType"), "amount": l.get("amount")} for l in coverage.get("limits") or []],
    }
