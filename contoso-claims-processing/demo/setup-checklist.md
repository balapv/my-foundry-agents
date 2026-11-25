# Setup checklist (15–30 minutes before presenting)

Run from `contoso-claims-processing/` in PowerShell. Tick each box; if one fails, see
[troubleshooting.md](troubleshooting.md).

## Repository

- [ ] Correct repo and branch (`git status -sb`); you're on the tagged baseline `claims-processing-v1` or a descendant of it
- [ ] Working tree clean, or only expected local files (`.env`, `.venv/`, `webapp/.logs/`, `evaluation/results/` are git-ignored)
- [ ] `.env` exists; `FOUNDRY_AGENT_VERSION=3` (or empty with `.foundry-state.json` recording version 3)
- [ ] `.\scripts\setup.ps1` passes (Python, venv, Node, `.env`, Azure sign-in, quick readiness)

## Azure / Foundry

- [ ] Signed in: `az account show` shows the subscription that holds the Foundry project
- [ ] Foundry portal open on the correct project
- [ ] `contoso-claims-review-agent` **version 3** visible (model `gpt-6.1-sol`, File Search, OpenAPI tool)
- [ ] Guidance vector store available (readiness check: "File Search vector store")
- [ ] Claims Operations API healthy (readiness check: "Claims API"); optional `curl <TOOLS_API_BASE_URL>/health` off-screen

## Application

- [ ] `.\.venv\Scripts\python.exe scripts\reset_demo.py` ends `DEMO RESET COMPLETE`
- [ ] Backend starts: `.\.venv\Scripts\python.exe -m uvicorn webapp.backend.app:create_app --factory --port 8010`
- [ ] `http://127.0.0.1:8010/` opens; CLM-10482 loads (Jordan Lee · 2024 Contoso Trailstar · In Review · $7,850 · $1,000)
- [ ] **Eight** evidence items appear (claim form, police report, repair estimate, five photographs)
- [ ] PDF viewer opens the repair estimate; photo viewer opens a right-rear photograph
- [ ] **About this workspace** shows agent version **3**
- [ ] After the smoke run below, a source/citation link opens the cited evidence
- [ ] **New review** clears the conversation

## Validation

- [ ] `.\.venv\Scripts\python.exe scripts\validate_demo.py --quick --live` ends `CLAIMS DEMO READY` (one live hero review plus follow-up, about 1 minute)
- [ ] One hero review in the browser shows the left-headlamp manual-review recommendation
- [ ] One follow-up ("Show me why you flagged the headlamp.") answers in the same conversation
- [ ] Press **New review** (or restart the server) so the demo starts with **no stale conversation**

## Browser preparation

- [ ] Tab 1: Claims Review, CLM-10482, fresh review
- [ ] Tab 2: Foundry agent page (version 3)
- [ ] Tab 3: Foundry traces/conversations for the agent
- [ ] Tab 4: code view (`agent/create_agent.py`, `webapp/backend/foundry.py`)
- [ ] Tab 5: `demo/assets/architecture.png`
- [ ] Zoom 110–125%; window sized for the projector
- [ ] Notifications, chat and email suppressed
- [ ] No secrets, `.env`, endpoints, subscription IDs or terminal history on screen

## Fallback (open in a background window)

- [ ] `demo/assets/04-hero-recommendation.png`: completed recommendation
- [ ] `demo/assets/05-headlamp-evidence-comparison.png`: evidence comparison
- [ ] [fallback-transcript.md](fallback-transcript.md): validated previous run (all four turns)
- [ ] `demo/assets/01-…` to `03-…`: workspace, evidence and in-progress states
