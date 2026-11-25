# Five-minute demo script

**Story:** build the agent visually or with code → ground it in policy and connect it to operational systems → watch
it reason → observe it → reuse the same agent in a customer-facing app → publish it anywhere.

**Hero prompt** (copy it before you start):

```text
My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?
```

## Before you go on stage (10–15 minutes)

Work through [setup-checklist.md](setup-checklist.md). The two preparation steps that matter most:

1. **Prepare the web conversation.** Start the web app, open `http://localhost:8080`, send the hero prompt and wait
   for the CT226 recommendation. Leave the tab open and **don't restart the server**: conversations live in server
   memory. Section 3:45 continues this conversation with one live follow-up, so the audience doesn't wait for a
   second hero turn.
2. **Open a new chat in the Foundry playground** for the agent, so the live hero turn starts with no history.

Keep [fallback-transcript.md](fallback-transcript.md) and the screenshots in [assets/](assets/) open in a background
tab. See [Latency and fallback](#latency-and-fallback).

## Timeline

| Time | Segment | Screen |
|---|---|---|
| 0:00–0:30 | Customer problem | Title slide or the Contoso Air web app |
| 0:30–1:15 | Build visually or with code | Foundry agent page → `agent/create_agent.py` |
| 1:15–3:15 | Hero scenario (live) | Foundry playground |
| 3:15–3:45 | Observability | Tool-call details / Traces |
| 3:45–4:30 | Same agent, customer experience | Contoso Air web app (prepared conversation) |
| 4:30–5:00 | Anywhere | Architecture visual |

### 0:00–0:30: Customer problem

**Say:** "A Contoso Air customer's flight has just been cancelled. He's traveling with his wife and two kids, and he
needs to know what to do next. Let's see how an agent built in Microsoft Foundry handles that."

**Don't explain:** the synthetic data, the API design or the model choice.

### 0:30–1:15: Build visually or with code

**Click:** the pre-created agent in the Foundry portal (**Agents** → `contoso-air-customer-care`). Point at four
things without scrolling:

1. **Model**: the deployment the agent uses.
2. **Instructions**: customer-service rules. Show the top few lines only.
3. **Knowledge**: four Contoso Air policy documents (File Search).
4. **Tools**: one OpenAPI tool for the Contoso Air Operations API: reservations, flight status, alternative flights.

**Say:** "I built this prompt agent directly in the Foundry UI. I gave it customer-service instructions, grounded it
in Contoso Air policies and connected it to our operational systems."

**Click:** `agent/foundry_common.py` (`build_agent_definition`, around line 192: the model, instructions,
`FileSearchTool` and `OpenApiTool`), then `agent/create_agent.py` (`create_version`, around line 169).

**Say:** "The same agent can also be created and managed through code: same instructions, same knowledge, same
tool. **Build visually or build with code.**"

**Don't explain:** vector store hashing, version resolution or the `.foundry-state.json` file. Keep the code on
screen for no more than 10 seconds.

### 1:15–3:15: Hero scenario (live)

**Click:** the Foundry playground → paste the hero prompt → send.

**While it works** (normally 25–45 seconds): narrate what the agent is designed to do. Point at tool activity only
when it actually appears on screen.

- "Notice what the customer didn't give it: no confirmation code, no flight number, no loyalty tier."
- "It starts by finding the customer's trip in the reservation system…"
- "…then checks the live status of that flight…"
- "…looks up Contoso Air's disruption and loyalty policies…"
- "…and searches for alternatives. Then it must decide which option actually works for **all four** travelers."

**When the answer arrives, highlight:**

- **Facts it confirmed:** CT218 Seattle → New York JFK tomorrow is **cancelled**; four travelers in **Economy Plus**;
  the customer is **Gold**.
- **Recommendation: CT226**, nonstop, 9:20 AM → 5:45 PM, because **all four can stay together in Economy Plus**.
- **Tradeoff:** it leaves about an hour earlier than the original 10:30 AM flight.
- **Why the others lose** (wording varies): the early Chicago connection can't keep all four in Economy Plus, and
  the afternoon nonstop can't seat all four.
- **Policy, not guesswork:** no change fee for a carrier cancellation, a refund option, Gold priority (not a
  guarantee).
- **No false promises:** it hasn't changed the booking; it asks the customer to confirm before anything happens.

**Say:** "CT226 wasn't even the first search result. The API returns options in departure order, and the agent
worked out which one fits the family using the customer's booking, live inventory and policy."

**Don't explain:** the instruction wording, prompt engineering or the evaluation suite (save it for Q&A).

### 3:15–3:45: Observability

**Click:** expand the tool-call details under the reply. If time allows, open the agent's **Traces** tab (some
portal versions call it **Monitor**).

**Say:** "Every step is observable: which operations it called, with which inputs, and what came back. We can
understand what the agent did rather than treating it as a black box."

**Don't:** open individual spans or walk through JSON.

### 3:45–4:30: Same agent, customer experience

**Click:** the Contoso Air web app tab with the prepared conversation.

**Say:** "But the customer doesn't need to come to Foundry. This is the Contoso Air Travel Assistant. It's the same
Foundry agent and version; the web app only relays messages. It holds no customer-service logic of its own."

**Type:** `Why is that better than the connection?` (normally answers in 5–10 seconds)

**Say, as it answers:** "It remembers the conversation, so it compares CT226 with the Chicago connection: the
connection can't keep the family together in Economy Plus. Same agent, a different experience, and no duplicated
customer-service intelligence."

### 4:30–5:00: Anywhere

**Click:** the architecture visual ([architecture.md](architecture.md), or
[assets/architecture.svg](assets/architecture.svg)).

**Say:** "Foundry is where this agent is built, managed, evaluated and observed. Today you saw it in the Foundry
playground and in our own app. The same agent can be published to Teams, Microsoft 365 Copilot and other
applications. This sample doesn't include those integrations, but nothing about the agent would change."

**Close:** "Build it visually or with code. Ground it in your enterprise knowledge. Connect it to your business
systems. Evaluate and observe it in Foundry. Then bring the same agent into the experiences where your users
already work."

## Latency and fallback

Observed in validation runs (no service-level guarantee):

| Turn | Observed | Expect on screen |
|---|---|---|
| Hero prompt | 24–44 s | Web app status line: *Working on it…*, then *Checking your trip…* → *Checking flight status…* → *Checking Contoso Air policies…* → *Finding alternative flights…* → *Reviewing your options…*, then the answer streams. Steps can repeat. |
| Follow-up | 5–10 s | *Working on it…*, then the answer |

The playground shows tool-call details once the reply is ready. Its timing is similar but wasn't measured
separately.

**What to do while waiting** (up to about 60 seconds): keep narrating the steps above. Don't apologize, refresh or
resend.

| Time since sending | Action |
|---|---|
| Up to 60 s | Normal. Keep narrating. |
| 60–90 s | Slow but plausible. "It's checking several systems; let's give it a moment." |
| More than 90 s | Treat it as abnormal. Switch to the fallback below; don't wait for the web app's 180-second timeout. |
| Error or "very busy" (HTTP 429) | Don't resend straight away; repeated requests make throttling worse. Switch to the fallback, then retry once after a minute if time allows. |

**Fallback**, in order:

1. **The prepared web conversation** already shows the full CT226 answer. Switch to it and continue from 3:45.
2. **[fallback-transcript.md](fallback-transcript.md)** or
   [assets/hero-completed.png](assets/hero-completed.png): a validated run of the same scenario.

Be honest about it: "The service is slow right now, so here's the same request from a run earlier today."

## Running behind

Cut in this order:

1. Shorten the 0:00 introduction to one sentence.
2. Skip the code view; just say "the same agent can be created with code".
3. Skip **Traces** and show only the tool-call details (or skip 3:15 entirely).
4. In the web app, show the prepared answer without the live follow-up.

Never cut the hero answer or the closing line.

## Q&A notes

- **Where does the data come from?** It's synthetic, deterministic data served by a small FastAPI service deployed
  to Azure Container Apps. The agent calls it as one OpenAPI tool with three read-only operations.
- **Does the API pick CT226?** No. It returns facts (seats per cabin, times, status) in departure order. The
  recommendation, policy interpretation and tradeoffs all come from the agent.
- **Is the portal agent the same as the code agent?** Yes. Both use `agent/instructions.md`, the same four PDFs and
  `tools/openapi.json`. Saving in either creates a new numbered version; clients resolve the version from
  configuration, never a hard-coded number.
- **Can it actually rebook?** No. This sample has no booking tool. The agent says so and gives the next step instead
  of claiming that a change happened.
- **How is it tested?** 110 offline tests, scripted live evaluations
  (`python evaluation/run_evaluation.py --no-judge`), and an end-to-end web check
  (`python scripts/validate_webapp.py`).
- **Who is signed in?** The web app simulates sign-in as the demo customer and passes the customer ID as
  application context. The customer can't change it in chat.
