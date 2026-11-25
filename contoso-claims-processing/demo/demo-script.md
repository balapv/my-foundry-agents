# Contoso Claims Review: five-minute demo script

A glance guide, not a speech. **Bold** lines are the points to land; say them in your own words.

| Before you start | |
|---|---|
| Readiness | `.\.venv\Scripts\python.exe scripts\validate_demo.py --quick` ends `CLAIMS DEMO READY` |
| Fresh state | `.\.venv\Scripts\python.exe scripts\reset_demo.py`, then start the app (fresh Foundry conversation) |
| Tabs, in order | 1 Claims Review `http://127.0.0.1:8010/` · 2 Foundry agent page (version 3) · 3 Foundry traces · 4 code (`agent/create_agent.py`, `webapp/backend/foundry.py`) · 5 `demo/assets/architecture.png` |
| Fallback ready | `demo/assets/` screenshots and [fallback-transcript.md](fallback-transcript.md) open in a background window |

Full checklist: [setup-checklist.md](setup-checklist.md). Recovery: [troubleshooting.md](troubleshooting.md).

---

## 0:00–0:25 · The claims problem

**Show:** the Claims Review tab, CLM-10482 loaded. Don't click anything yet.

**Say:**
- **An adjuster never gets one clean source of truth.**
- They reconcile claim records, policy coverage, a police report, a repair estimate, photographs, prior history and company guidance.
- That reconciliation is the slow, error-prone part of the job.

## 0:25–0:55 · The Foundry prompt agent

**Show:** Foundry tab, `contoso-claims-review-agent`, **version 3**. Point to, don't scroll:
model (`gpt-6.1-sol`) · instructions (top lines only) · File Search knowledge · Claims Operations API (OpenAPI tool).

**Say:**
- **One managed agent, created in the Foundry UI or from code. Same definition either way.**
- **Reusable company guidance** lives in File Search.
- **Structured claim facts** come from the business system through the Claims Operations API.
- **This claim's evidence** (PDFs, photographs) is attached at runtime by the application. That's why we run the review there and not in the playground.

**Don't:** read the instructions, open tool JSON, or try the hero claim in the playground (it can't attach evidence).

## 0:55–2:40 · Hero review in the Claims Review application

**Show:** Claims Review tab. Orient in about 15 seconds, pointing as you go:

- Jordan Lee · 2024 Contoso Trailstar · collision · **In Review**
- Estimate **$7,850** · deductible **$1,000**
- Evidence: claim form, police report, repair estimate, **five photographs**

**Click:** the suggested prompt **"Review this claim and tell me what I should do next."**

**Wait point: expect 42–58 s.** The status line shows what's actually happening. Narrate what it shows:

| Status line says | You can say |
|---|---|
| Verifying / sending the claim and its evidence | "The application checked each document against its fingerprint and attached the three PDFs and five photographs to the agent." |
| Checking claims records… | "It's pulling the structured claim and policy records from the claims system." |
| Searching company guidance… | "Now it's consulting company guidance, which is separate from this claim's evidence." |
| Preparing the response… | "It has to reconcile all of that across different sources." |

Filler if needed: **"Notice the application has no claims-decision logic. It shows facts and evidence; the review comes from the agent."**

**When it arrives (don't read it all):** point to the **Recommendation** card.

- **"Supported right-rear repairs continue through normal review. One line, the $1,240 left-headlamp replacement, goes to manual review."**
- Glance at **What checks out** (green) vs **Needs review** (amber). That contrast is the story.

**Cut if behind:** skip the "What checks out" glance.
**Fallback:** if there's no answer by about 75 s, or the app shows the retry/rate-limit card, say *"Live models have bad days. Here's the same review from a validated run,"* and show `04-hero-recommendation.png`. Then ask the follow-up live in a **New review**, or use `05-…png`.

## 2:40–3:35 · Evidence hero moment (do not cut)

**Type, in the same conversation:** **"Show me why you flagged the headlamp."** (about 10–15 s)

**Show** with the citation buttons or the "Evidence referenced in this answer" panel:

1. **Repair estimate, line 1:** the LT LED headlamp, $1,240
2. **Police report:** impact at the right rear
3. **Claim form:** damage described as rear bumper, right-rear quarter panel, right tail lamp
4. **Right-rear photographs** (DOC-10482-02, -03)
5. **Front/left overview photograph** (DOC-10482-06): oblique, distant
6. **Repair Estimate Review Guidelines** (citation chip)

**Land it slowly:**
> **"The evidence does not currently establish that the headlamp replacement belongs to this collision. That does not prove the headlamp was undamaged."**

That distinction is the point of the demo: no false certainty in either direction.

## 3:35–4:05 · Human control

**Say:**
> **"The agent didn't deny the claim, accuse anyone of fraud, or authorize a repair. It found the narrow evidence question, recommended the next step, and left the decision with the adjuster."**

**Optional, only if time permits:** ask **"Can you deny the claim based on this?"** (about 6–10 s). Point to the first line: *it can't deny; that decision belongs to authorized claims staff.*

## 4:05–4:30 · Observability

**Show:** Foundry tab, the agent's traces/conversations. Pick the newest run, or search for the `conversationId` from `webapp/.logs/claims-review.log`.

**Point to, don't open raw JSON:**
- Claims API calls (`get_claim`, `get_policy`, `get_vehicle`, `get_customer_claim_history`)
- File Search calls over the guidance
- The multimodal evidence on the first turn
- The follow-up in the **same conversation**, with no evidence re-sent

**Cut if behind:** say one sentence ("Every run is traced in Foundry: tool calls, File Search, the conversation") and move on.

## 4:30–4:50 · UI or code, and architecture

**Show:** `architecture.png`. Optionally flash `agent/create_agent.py` (the agent definition) and `webapp/backend/foundry.py` (it invokes the agent by name and version, attaching the evidence).

**Say:**
- **UI or code can create the agent. The application invokes that same managed agent.**
- **The UI doesn't reproduce claims logic.**
- **Business records, company guidance and claim evidence stay separate sources.**

**Cut first if behind:** the code view.

## 4:50–5:00 · Close

> **"The agent didn't replace the adjuster. It did the investigative work that focused the adjuster on the one part of the claim that actually needed judgment."**

> **"Build the agent in Foundry, ground it in company knowledge, connect it to business systems, give it the evidence for the current case, and bring it into the workflow where people already work."**

---

## Running behind? Cut in this order

1. Shorten the opening to one sentence.
2. Reduce the Foundry configuration segment to "model, guidance, API, evidence at runtime."
3. Skip the code view.
4. Reduce observability to one sentence.
5. Show `04-hero-recommendation.png` as "a review I ran before the session" and run **only the headlamp follow-up live** (it still needs a live first turn; use a fresh **New review** started before you go on stage, or the screenshot `05-…png`).

**Never cut the evidence-comparison moment.**

## Don't explain unless asked

- Evidence hashing/manifest mechanics, the OpenAPI "errors as HTTP 200" convention, token usage
- How the photographs were generated (they're synthetic; say so if asked)
- Evaluation cases and scoring
- Internal endpoints, environment values, resource names

## Fallback transition (say it once, plainly)

> "Live model calls sometimes slow down or get rate-limited. Rather than make you wait, here's the same review from a validated previous run."

Never present a screenshot or the saved transcript as live.

## Optional Q&A

| Question | Short answer |
|---|---|
| Does it detect fraud? | No. It's told not to make fraud findings. A single unsupported line goes to ordinary manual review, not SIU, per the escalation guidance. |
| Is there OCR or computer vision? | No separate service. The model reads the attached PDFs and photographs directly. |
| Can it approve or pay? | No. It recommends; authorized staff decide. The API is read-only. |
| Why not the playground? | The playground can't attach a claim's documents and photographs. The agent definition is the same; the app supplies the evidence. |
| What if the API is down? | The API returns a readable error and the agent says what it couldn't verify. Demo: `CLAIMS_API_SIMULATE_OUTAGE` (see the root README). |
| Is the data real? | No. All customers, claims, documents and photographs are synthetic. |
| Does it work for other claims? | Yes. Six more evaluation claims have evidence packages (`?claim=CLM-10439`, …). The hero is just the most illustrative. |
| How long does a review take? | First turn about 42–58 s in our runs; follow-ups about 6–15 s. |
