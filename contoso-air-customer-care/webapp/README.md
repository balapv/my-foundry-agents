# Contoso Air Travel Assistant (sample web app)

A lightweight, customer-facing page that talks to the **same Foundry prompt agent** you built in the Foundry
portal or with `agent/create_agent.py`. The web app is a **channel**: the Foundry agent owns the reasoning.

```
Browser (webapp/frontend)  ──►  FastAPI relay (webapp/backend/server.py)
                                   │  Responses API on one Foundry conversation per chat
                                   │  agent_reference = FOUNDRY_AGENT_NAME + resolved version
                                   ▼
                     Foundry prompt agent ──► Policy knowledge (File Search) + Contoso Air Operations API
```

## What the page shows

- A **Contoso Air** header and a **Travel Assistant** page.
- A greeting and an **upcoming trip** card for the simulated signed-in customer: the route (Seattle → New York),
  date, flight number and flight status. The backend reads these from the Operations API for display only.
- A chat area. The hero question is the first, highlighted suggestion, followed by the starter prompts from
  `agent/config.example.json`.
- Friendly progress while the agent works: *Checking your trip…*, *Checking flight status…*,
  *Checking Contoso Air policies…*, *Finding alternative flights…*, *Reviewing your options…*.

The browser never receives tool names, operation IDs, arguments, outputs, reasoning or citation markers.

## What the backend does (and does not do)

| Does | Does not |
| --- | --- |
| Uses the demo sign-in and passes the customer ID to the agent as application context in a developer message | Let the chat request choose the customer; a `customerId` in the request body is rejected |
| Resolves the agent version once per chat session and uses it for every turn | Decide rebooking options, eligibility, fees, hotels or escalation |
| Keeps one Foundry conversation per chat, so follow-up questions keep their context | Call the flight-search or policy tools for the chat itself |
| Turns tool-call stream events into friendly progress messages | Show tool traces, stack traces or Azure details to customers |
| Streams the agent's text to the browser as server-sent events | Store conversations beyond process memory |

### Agent version

The backend never hard-codes a version. For each new chat session it uses:

1. `FOUNDRY_AGENT_VERSION`, if set.
2. Otherwise, `activeAgentVersion` from `.foundry-state.json`, recorded by `agent/create_agent.py`.
3. Otherwise, the agent's latest version.

The version is logged for each session and reported by `GET /api/health`.

### Demo sign-in

There is no real sign-in. The "signed-in" customer is `DEMO_CUSTOMER_ID` (default `CUST-1007`, Alex Johnson), and
the page footnote says so. A real application would take the customer ID from its own authenticated session and
pass it the same way. The customer ID is never taken from chat input.

### Errors

If something fails, the customer sees a short, friendly message with a reference code, for example
"Reference: 3f9a1c2e". Timeouts and busy-service errors get their own messages. The server log records the
reference with the error category, session, conversation and agent version. The browser never shows stack traces,
resource IDs, credentials or internal details. If the trip card can't load, chat still works.

## Run it

Prerequisites:

- The agent exists (README, Option A or B).
- The Operations API is deployed.
- `.env` is filled in.
- You are signed in with `az login` as a user with the **Foundry User** role on the project.

From the `contoso-air-customer-care` folder:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m uvicorn server:app --app-dir webapp/backend --port 8080
```

```bash
# macOS / Linux
source .venv/bin/activate
python -m uvicorn server:app --app-dir webapp/backend --port 8080
```

Open <http://localhost:8080> and click the suggested question:

> My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?

Then try *Why is that better than the connection?*, *Do I qualify for a hotel?* and *Book it.* Use **New
conversation** to start over with a fresh Foundry conversation.

## Configuration

| Setting (`.env`) | Purpose |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint |
| `FOUNDRY_AGENT_NAME` | Agent to invoke (default `contoso-air-customer-care`) |
| `FOUNDRY_AGENT_VERSION` | Optional: pin the agent version |
| `TOOLS_API_BASE_URL` | Operations API, used only for the greeting and trip card |
| `DEMO_CUSTOMER_ID` | Simulated signed-in customer (default `CUST-1007`) |
| `WEBAPP_TURN_TIMEOUT_SECONDS` | Optional: maximum seconds for one agent turn (default 180) |

The backend authenticates to Foundry with `DefaultAzureCredential`.

## Validate

Offline tests use a fake Foundry client. They cover:

- the session and trip card;
- version resolution;
- the demo sign-in;
- progress mapping;
- conversation reuse;
- friendly errors;
- the frontend having no tool names or customer logic.

```powershell
python -m pytest tests/test_webapp.py tests/test_validate_webapp.py
```

The end-to-end check starts the web app, then runs the hero question and the three follow-ups through it against
the live agent:

```powershell
python scripts/validate_webapp.py                     # starts the server on a free port
python scripts/validate_webapp.py --base-url http://localhost:8080
python scripts/validate_webapp.py --transcript web-transcript.md
```

## Sample limitations

This is a demo, not a production airline site:

- Sign-in is simulated with `DEMO_CUSTOMER_ID`.
- Sessions live in process memory, so run a single instance.
- The page runs locally with your developer credentials. A hosted version would use a managed identity with the
  Foundry User role and its own authentication for customers.
- The agent cannot book or change reservations. It tells the customer how to complete a change.
