"""Contoso Claims Review web application (FastAPI).

Run from contoso-claims-processing/:
    .venv\\Scripts\\python.exe -m uvicorn webapp.backend.app:create_app --factory --port 8010

Routes return display facts, evidence files listed in the claim's manifest, and the Foundry agent's
answers. They never return Foundry conversation/response IDs, tool names, endpoints, file-system
paths or evidence hashes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import claims
from .claims import ClaimsFacts, EvidenceIntegrityError, NotFound
from .config import FRONTEND_DIR, Settings, load_dotenv_file, load_settings
from .errors import configure_logging, log_event, new_reference, public_error
from .foundry import FoundryRuntime
from .sessions import MAX_MESSAGE_CHARS, ReviewService, SessionBusy, SessionNotFound

APP_NAME = "Contoso Claims Review"
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml"}
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
                                "frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; "
                                "frame-ancestors 'self'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "SAMEORIGIN",
}
ABOUT = (
    "The Contoso Claims Review agent is a Microsoft Foundry prompt agent. It can be created and inspected in the "
    "Foundry portal, or created from code with the same definition. This workspace calls that same Foundry-managed "
    "agent through the Foundry SDK so it can attach the claim's documents and photographs, which the Foundry "
    "playground cannot do for a specific claim. The workspace shows claim facts and evidence; the agent does the review."
)


class CreateReview(BaseModel):
    claimId: str = Field(min_length=1, max_length=20)


class SendMessage(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


def static_files() -> dict[str, Path]:
    """Allowlisted frontend assets (frontend tests are never served)."""
    files = {}
    for path in FRONTEND_DIR.rglob("*"):
        relative = path.relative_to(FRONTEND_DIR)
        if path.is_file() and path.suffix in STATIC_TYPES and relative.parts[0] != "tests":
            files[relative.as_posix()] = path
    return files


def create_app(settings: Settings | None = None, runtime: FoundryRuntime | None = None,
               facts: ClaimsFacts | None = None, run_in_thread: bool = True) -> FastAPI:
    if settings is None:
        load_dotenv_file()
        settings = load_settings()
    configure_logging(settings.log_dir)
    facts = facts or ClaimsFacts(settings.claims_api_base_url)
    runtime = runtime or FoundryRuntime(settings)

    def claim_exists(claim_id: str) -> bool:
        if claims.has_evidence_package(claim_id):
            return True
        try:
            facts.fetch("get_claim", claim_id)
            return True
        except claims.FactsUnavailable:
            return False

    reviews = ReviewService(settings, runtime, claim_exists, run_in_thread=run_in_thread)
    assets = static_files()

    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.reviews, app.state.runtime, app.state.facts = settings, reviews, runtime, facts

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        is_pdf = response.headers.get("content-type", "").startswith("application/pdf")
        for name, value in SECURITY_HEADERS.items():
            # A document CSP disables the browser's built-in PDF viewer; X-Frame-Options still limits framing.
            if is_pdf and name == "Content-Security-Policy":
                continue
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    def not_found() -> HTTPException:
        return HTTPException(status_code=404, detail="Not found")

    # -- pages and assets ----------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(assets["index.html"], media_type=STATIC_TYPES[".html"], headers={"Cache-Control": "no-cache"})

    @app.get("/ui/{asset:path}", include_in_schema=False)
    def asset(asset: str) -> FileResponse:
        path = assets.get(asset)
        if path is None:
            raise not_found()
        return FileResponse(path, media_type=STATIC_TYPES[path.suffix], headers={"Cache-Control": "no-cache"})

    # -- claim workspace -----------------------------------------------------------------------

    @app.get("/api/about")
    def about() -> dict[str, Any]:
        return {"application": APP_NAME, "agentName": settings.agent_name,
                "agentVersion": runtime.configured_version(), "defaultClaimId": settings.default_claim_id,
                "about": ABOUT}

    @app.get("/api/claims/{claim_id}")
    def claim(claim_id: str) -> dict[str, Any]:
        try:
            return claims.claim_workspace(facts, claim_id)
        except NotFound:
            raise not_found() from None
        except EvidenceIntegrityError as exc:
            reference = new_reference()
            log_event("claim.manifest_invalid", reference=reference, claim=claim_id, detail=str(exc))
            return JSONResponse(status_code=500, content={"error": public_error("evidence_validation", reference)})

    @app.get("/api/claims/{claim_id}/evidence/{document_id}")
    def evidence(claim_id: str, document_id: str, download: bool = False) -> Response:
        try:
            content, media_type, file_name = claims.read_evidence(claim_id, document_id)
        except NotFound:
            raise not_found() from None
        except EvidenceIntegrityError as exc:
            reference = new_reference()
            log_event("evidence.integrity_failed", reference=reference, claim=claim_id, document=document_id,
                      detail=str(exc))
            return JSONResponse(status_code=409, content={"error": public_error("evidence_validation", reference)})
        disposition = "attachment" if download else "inline"
        return Response(content, media_type=media_type, headers={
            "Content-Disposition": f'{disposition}; filename="{document_id}{Path(file_name).suffix}"',
            "Cache-Control": "private, max-age=300"})

    @app.get("/api/guidance/{guidance_id}")
    def guidance(guidance_id: str) -> Response:
        try:
            content, _ = claims.read_guidance(guidance_id)
        except NotFound:
            raise not_found() from None
        return Response(content, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{guidance_id}.pdf"', "Cache-Control": "private, max-age=300"})

    # -- reviews -------------------------------------------------------------------------------

    @app.post("/api/reviews", status_code=201)
    def create_review(body: CreateReview) -> dict[str, Any]:
        try:
            session = reviews.create(body.claimId)
        except NotFound:
            raise not_found() from None
        return {"sessionId": session.session_id, "claimId": session.claim_id,
                "evidencePackage": claims.has_evidence_package(session.claim_id)}

    @app.post("/api/reviews/{session_id}/messages", status_code=202)
    def send_message(session_id: str, body: SendMessage) -> dict[str, Any]:
        try:
            return reviews.send(session_id, body.text).public()
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="This review has ended. Start a new review.") from None
        except SessionBusy:
            raise HTTPException(status_code=409, detail="The agent is still working on the previous message.") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/api/reviews/{session_id}/turns/{turn_id}")
    def get_turn(session_id: str, turn_id: str) -> dict[str, Any]:
        try:
            return reviews.turn(session_id, turn_id).public()
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="This review has ended. Start a new review.") from None

    @app.delete("/api/reviews/{session_id}", status_code=204)
    def delete_review(session_id: str) -> Response:
        try:
            reviews.delete(session_id)
        except SessionNotFound:
            pass  # already gone: a reset is idempotent
        return Response(status_code=204)

    return app
