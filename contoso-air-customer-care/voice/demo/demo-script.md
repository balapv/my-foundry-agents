# Five-minute voice demo script (primary Customer Service demo)

**Demo 1B Voice is the primary Customer Service demo. Demo 1A Text is the validated fallback.**

**Story:** a customer with a cancelled flight just talks to Contoso Air → a Foundry voice agent combines customer
context, company policy and live business systems → it recommends the right flight in a natural, interruptible
conversation → the same enterprise agent is observable, and can be built in the UI or with code.

> **Do not show Demo 1A in the normal presentation.** No web app, no text hero prompt, no text and voice versions
> back to back. Demo 1A is the recovery path ([Fallback](#fallback-to-demo-1a)), the reference implementation and a
> repository sample.

**What you will say to the agent** (the customer never gives an ID, confirmation code, flight, tier or cabin):

1. "Hi. My flight tomorrow was cancelled, and I'm traveling with my wife and two kids. Can you help?"
2. "Yes, tell me the details."
3. **Interrupt** while it's answering: "Wait, what about the connecting flight?"

Use your own natural wording. The agent is not reading a script, and its wording varies between calls.

## Before you go on stage (15–30 minutes)

Work through [setup-checklist.md](setup-checklist.md). It ends with one real spoken test call. Keep
[troubleshooting.md](troubleshooting.md) to hand, and keep Demo 1A ready in a background window (not on screen).

## Timeline

| Time | Segment | Screen |
|---|---|---|
| 0:00–0:25 | The customer problem | Title slide |
| 0:25–0:55 | The Foundry voice agent | Foundry: `contoso-air-customer-care-voice` agent page |
| 0:55–3:15 | Live voice conversation (with interruption) | Foundry voice playground, **Start session** |
| 3:15–3:45 | What just happened | Same screen (the conversation transcript) |
| 3:45–4:15 | Observability | Tool activity: Traces, or the recorded call transcript |
| 4:15–4:40 | UI or code, and the architecture | `voice/agent/voice_common.py` → [voice architecture](assets/voice-architecture.svg) |
| 4:40–5:00 | Close | Architecture visual |

### 0:00–0:25: The customer problem

**Say:** "A customer doesn't care how many systems an airline runs behind the scenes. Alex's flight tomorrow has
just been cancelled, he's traveling with his wife and two kids, and he simply wants help. So he calls Contoso Air."

Keep it to two sentences.

### 0:25–0:55: The Foundry voice agent

**Click:** the pre-opened agent page in the Foundry portal (**Build** → **Agents** →
`contoso-air-customer-care-voice`). Point, without scrolling:

1. **Voice:** realtime speech model (`gpt-realtime-2.1`) and the `en-US-AvaNeural` voice, with semantic turn
   detection, so the caller can interrupt.
2. **Instructions:** voice-native customer-service rules. Show the top few lines only.
3. **Knowledge:** the four Contoso Air policy documents.
4. **Toolbox:** the Contoso Air Operations API: reservations, flight status, alternative flights.

**Say:** "This is a native Foundry voice agent. It uses the same company policies and connects to the same
business systems as any other agent we build. It can be configured right here in Foundry, or represented in code."

**Don't explain:** Voice Live internals, audio formats, VAD settings or the toolbox OpenAPI details.

### 0:55–3:15: Live voice conversation

**Click:** **Start session** in the playground (it opens the agent's latest version, the validated one; see the
checklist). Wait for the greeting: *"Hi, you've reached Contoso Air Customer Care…"*

**Say to the agent:** "Hi. My flight tomorrow was cancelled, and I'm traveling with my wife and two kids. Can you
help?"

**Then stop talking.** The agent says one short progress sentence while it works, then answers (normally the
recommendation is heard about 10–15 seconds after you finish speaking). Don't talk over it. Expect:

- it confirms the **Seattle to New York flight tomorrow is cancelled**;
- it **recommends the 9:20 nonstop in Economy Plus**, because it has seats for all four of you together;
- it offers the details.

**Say:** "Yes, tell me the details."

Expect flight **CT226**, nonstop, **9:20 AM → 5:45 PM**, a bit earlier than the original departure, and, if it's
treated as a carrier reaccommodation, no change fee or fare difference.

**The hero moment.** While it's still describing CT226, **interrupt**: "Wait, what about the connecting flight?"

Expect it to **stop speaking**, then answer the new question: the **7:10 connection through Chicago** leaves
earlier, but the family **can't stay together in Economy Plus**. They'd fit together only in **Main Cabin**, a
downgrade that needs their agreement. So the nonstop remains the better fit.

**Say to the audience:** "I just interrupted it, and it stopped, listened and answered the new question. This isn't
a recording or a written answer being read aloud."

**Only if you're ahead of time:** "Okay, book that one." It asks which flight you mean, then explains that it can't
book or change the reservation on this call and gives the Gold service line. It never claims anything was changed.

**Wording varies between calls.** That's expected. Judge the facts, not the phrasing (see
[What a good call looks like](#what-a-good-call-looks-like)).

### 3:15–3:45: What just happened

**Say:** "Notice what I never told it: no customer ID, no confirmation number, no flight number, no loyalty tier, no
cabin, no airline policy and no list of alternatives.

The agent combined my signed-in customer context, my reservation, the live flight status, Contoso Air's policies
and the available alternatives, and turned them into a recommendation in a natural conversation. And CT226 wasn't
just the first search result: the system lists the 7:10 connection first. The agent chose the option that keeps
the whole family together."

### 3:45–4:15: Observability

**Click:** the agent's **Traces** tab (some portal versions call it **Monitor**) and open the session you just had,
**if the setup check confirmed that voice sessions appear there**. Otherwise, open the `transcript.md` from your
pre-show validation call (`voice/results/<timestamp>-V2-hero*/transcript.md`), which lists each tool call with its
inputs and timing.

**Say:** "This voice conversation is still an enterprise agent interaction. We can see which systems it called,
with what inputs, and what policy it searched. It's not a black box."

**Don't:** open individual spans, walk through JSON or show any endpoint.

### 4:15–4:40: UI or code, and the architecture

**Click:** `voice/agent/voice_common.py` → `build_voice_definition` (around line 180: model, instructions, voice,
turn detection, the `customer_id` input and the toolbox), for no more than 10 seconds.

**Say:** "The same agent can be configured in the Foundry portal, as you saw, or defined in code with the Foundry
SDK. Either way it's the same agent version."

**Click:** the [voice architecture visual](assets/voice-architecture.svg).

**Say:** "One Foundry voice agent, grounded in policy knowledge and connected to the operations systems. The speech
handling is part of the Foundry agent. There's no separate speech pipeline to build."

### 4:40–5:00: Close

**Say:** "This isn't interesting because AI can speak. It's interesting because a grounded enterprise agent can
combine customer context, company policy and live business systems inside a natural, real-time conversation.

Build with Foundry, connect your knowledge and business systems, evaluate and observe, and bring the agent into the
experiences where your users already work."

## What a good call looks like

Recorded in Phases V2 and V3 (no service-level guarantee). The facts are stable; the wording is not.

| Step | Must be true | Typical timing |
|---|---|---|
| Opening request | CT218 tomorrow is cancelled; recommends the 9:20 nonstop (CT226) in Economy Plus for all four; no fee, refund or Gold talk yet | First audio about 1–2 s; recommendation heard about 10–15 s; about 20–30 s of speech |
| Details | CT226, nonstop, 9:20 → 5:45, earlier than the original | About 20 s of speech |
| Interruption | Stops; 7:10 via Chicago; can't keep all four in Economy Plus; Main Cabin fits (a downgrade) | Answers within about 3 s |
| "Book that one" (optional) | Asks which flight if unclear; says it can't book; gives a contact line (usually the Gold line 1-800-555-0157, occasionally the General line 1-800-555-0142) | About 10–25 s |

**Known variations, all acceptable:** the agent may say "C T two twenty-six" letter by letter; it may not say how much
longer the connection takes; the "I confirmed your flight is cancelled" sentence is nearly identical on every call.
Occasionally (1 in 6 v11 smoke runs) it **repeats its Turn 1 answer**: say "Yes, tell me the details." over the
repeat to move on.

**Not acceptable** (switch to the fallback): it names the wrong customer, flight or date; claims the booking was
changed or held; recommends the connection or the 3:45 flight for all four in Economy Plus; or makes up a policy
amount.

## Latency guidance

| Time since you stopped speaking | Action |
|---|---|
| Up to 15 s | Normal. A short progress sentence plays first; let it finish. |
| 15–30 s | Slow but plausible. Say: "It's checking several systems; let's give it a moment." |
| More than 30 s of silence, or the session drops | Abnormal. Use [troubleshooting.md](troubleshooting.md) once, at most. Then fall back. |
| Error, "busy" or HTTP 429 | Don't retry repeatedly. Fall back. |

## Fallback to Demo 1A

Use this when the microphone, audio, browser, voice session or service fails, or when an answer is wrong. Don't debug
on stage.

**Say:** "Rather than spend time troubleshooting the live audio session, let me show you the same grounded
customer-service workflow through the validated text experience."

**Then switch** to the Demo 1A window you prepared in the checklist, and continue with the Demo 1A script from its
hero segment ([../../demo/demo-script.md](../../demo/demo-script.md), 1:15). In order of preference:

1. **The prepared Contoso Air web conversation** (`http://localhost:8080`), which already shows the CT226 answer.
2. **The Demo 1A text agent in the Foundry playground**, with the text hero prompt.
3. **[../../demo/fallback-transcript.md](../../demo/fallback-transcript.md)**, a validated run, if the service itself is
   down. Say so honestly: "Here's the same request from a run earlier today."

The message stays the same: the same policies, the same Operations API and the same grounded reasoning, through a
different experience. Return to the voice script's 3:15 segment ("what just happened") and close as normal.

## Running behind

Cut in this order:

1. Shorten 0:00 to one sentence.
2. Skip the code view (4:15); just say "it can also be defined in code", and show the architecture visual.
3. Skip observability (3:45).
4. Skip the optional "book that one".

Never cut the interruption or the closing line.

## Q&A notes

- **Is the speech handled by a separate service I'd have to build?** No. This is a Foundry voice-based prompt agent:
  the realtime model, voice, turn detection and transcription are part of the agent definition.
- **Where does the data come from?** Synthetic, deterministic data served by the small Contoso Air Operations API,
  the same one Demo 1A uses. No real airline system is connected.
- **Does the API pick CT226?** No. It returns facts in departure order. The recommendation, policy interpretation and
  trade-offs come from the agent.
- **Who is the caller?** Authentication is simulated. A real app passes the signed-in `customer_id` when it opens the
  session; the caller can't change it by speaking. The portal playground can't send it, so the demo version has a
  demo-only default customer.
- **Can it actually rebook?** No. It has read-only tools, says so and gives the right contact.
- **How is it tested?** Offline tests (`python -m pytest voice/tests`), scripted spoken calls with deterministic
  checks (`python voice/agent/run_session.py --scenario V2-hero --repeat 3`), and a human review rubric. See
  [validation-record.md](validation-record.md).
- **Teams or Microsoft 365 Copilot?** The agent is published from Foundry like any other agent; this sample doesn't
  include those integrations.
