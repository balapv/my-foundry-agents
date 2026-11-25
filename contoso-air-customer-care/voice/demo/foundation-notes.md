# Voice foundation notes: behavior and timings (Phases V1 and V2)

This is an engineering record of what the voice agent actually did in Phases V1 and V2. It is meant for planning, not presenting.
- It is **not** a presenter script.
- Demo 1A (text) remains the stable demo.
- The V1 sections below describe **version 6**. The Phase V2 results are in [Phase V2 hardening results](#phase-v2-hardening-results) at the end.

V1 runs used:
- agent `contoso-air-customer-care-voice` **version 6**;
- managed `gpt-realtime-2.1`;
- spoken caller input, synthesized with Azure Speech and streamed as 24 kHz PCM16;
- server semantic VAD and `azure-speech` transcription.

Each run's results are written to `voice/results/` (git-ignored).

## Version history

| Agent version | Toolbox version | Outcome |
|---|---|---|
| 1 | 1 | Failed: the toolbox ignored `nullable: true`, so `loyaltyNumber: null` failed response validation |
| 2 | 2 | Failed: the toolbox's OpenAPI 3.0 validator rejected JSON Schema type arrays |
| 3 | 3 | Tools worked: the spec copy is OpenAPI 3.1.0 with `type: [T, "null"]`. **The instruction examples leaked the hero answer.** |
| 4 | 3 | Tighter turn length. Hero 31/33 and outage 5/6. **Leaked.** |
| 5 | 3 | Progressive disclosure. 4/4 scenarios after harness regex fixes. **Leaked.** |
| 6 | 3 | Neutral examples (found by `test_instructions_do_not_leak_hero_answers`). **4/4 scenarios passed on the first run.** |

What the leak was:
- Versions 3 to 5 had spoken-style examples in `instructions.md` that used the hero's flight number and times, and described the hero outcome.
- Results from those versions cannot be counted as evidence of reasoning, which is why only version 6 results are reported.
- Versions 1 to 5 still exist in the project. Use the active version in `voice/.voice-state.json`.

## Observed latency (version 6)

Timings are measured from the end of the caller's speech (the last audio frame sent).

| Run / turn | Server end-of-speech | First agent audio | Final response done |
|---|---|---|---|
| Hero T1 (4 tool calls) | 429 ms | 1,710 ms (progress line) | 13,763 ms |
| Hero T2 (no tools) | 432 ms | 1,986 ms | 4,542 ms |
| Hero T3 (after barge-in) | 429 ms | 2,549 ms | 3,987 ms |
| Hero T4 | 210 ms | 1,303 ms | 1,522 ms |
| Hero T5 | 538 ms | 2,363 ms | 4,199 ms |
| Hero T6 | -116 ms | 1,194 ms | 3,649 ms |
| Identity override | 429 ms | 1,633 ms | 3,099 ms |
| Status outage (3 tool calls) | 535 ms | 1,935 ms | 8,628 ms |
| No reservation (1 tool call) | 427 ms | 1,414 ms | 4,747 ms |

- **The caller first hears audio 1.2 to 2.5 s after they stop speaking.** That includes about 0.2 to 0.5 s of turn detection.
- **Hero turn-1 tool chain** (relative to the end of caller speech):

  | Tool | Window |
  |---|---|
  | Reservations | 1.8–2.4 s |
  | Flight status | 3.5–4.0 s |
  | File Search (5 queries) | 5.6–8.4 s |
  | Alternative search | 10.0–10.6 s |

  The final answer starts at about 13.8 s. File Search is the longest single step, at 2.8 s.
- The tools run one after another, because each lookup depends on the previous result. The agent fills the gaps with spoken progress lines.
- The audio lengths below are the WAV durations in each run's results folder. Audio is generated faster than real time, so the call took 87.2 s in total, not the full listening time.

  | Turn | Agent audio |
  |---|---|
  | T1 | 46.4 s |
  | T2 | 24.8 s |
  | T3 | 16.2 s |
  | T4 | 5.2 s |
  | T5 | 18.5 s |
  | T6 | 27.8 s |

## Behavior observations (version 6 hero)

**What worked**
- **Turn 1:** the agent made all four lookups in the right order, using the trusted identity. It never asked for an ID or confirmation code, or for the tier or cabin.
- **Policy grounded:** the File Search queries covered the carrier-cancellation rebooking and fee waiver, Gold disruption benefits, meal and hotel assistance, and escalation.
- **Progressive disclosure:** turn 1 stated the cancellation and the policy outcome, then asked "Would you like the details?". It did not read out the whole itinerary.
- **Turn 2** gave CT226 (09:20 → 17:45, on time, enough Economy Plus seats for four). It mentioned that it leaves earlier, and offered the later option along with its seat caveat.
- **Turn 3 (after the barge-in):**
  - It answered the new question directly and did not repeat its earlier answer.
  - It correctly said that the connection has 2 Economy Plus seats, against 4 in Main Cabin, so it cannot keep the family together in their cabin.
- **Turn 5:** it correctly said that the later nonstop at 3:45 has 1 Economy Plus seat, and that no later option fits the whole party.
- **Turn 6:** it said clearly that it cannot book. It gave grounded handoff details: both phone numbers appear in `knowledge/source/`, and the request covers all four passengers in Economy Plus. It never claimed that an action happened.
- Across the whole call, it made no fare or dollar claims and no guarantees.

**What hardening should address**
1. **Turn 1 is verbose.**
   - The agent spoke four progress lines, one before each lookup. The instructions intend one or two.
   - The progress lines make up more than half of the 46-second first reply.
   - Options are to raise the interim-response latency threshold, or to tighten the instructions so that one progress line covers the whole chain.
2. **Turn 3 leaves out tradeoffs.**
   - The connection also departs earlier (07:10) and takes longer than CT226. The agent didn't say so.
   - It ended with "I'd need to confirm downgrade rules before recommending it".
     - The hedge is honest: the turn-1 File Search returned the definition of a downgrade (§3.11), but not the downgrade-handling rules in §10.4.
     - It should have run a quick follow-up policy search rather than leaving the question open.
3. **"What time does it leave again?" is resolved to the most recent subject.**
   - The agent answered 7:10 for the connection, which is a defensible reading of "it" after turn 3.
   - The demo story usually means the recommended nonstop.
   - For presenting, say "What time does the nonstop leave again?" to avoid the ambiguity. Alternatively, the instructions could ask the agent to confirm which option when the reference is unclear.
4. **"Book that one" is not clarified.**
   - The agent assumed the 9:20 nonstop, the one it recommended. After turn 5, the most recently mentioned flight was the 3:45.
   - The refusal itself is correct, and no action was taken. A short "the 9:20 nonstop, right?" would be safer once booking tools exist.
5. **Identity-override wording.** "…the account you're signed in with for this call, which is the current session" is accurate but awkward.
6. **The outage reply offers no next step.** It correctly declined to state the flight status, but it didn't offer to try again later or give the escalation route.
7. **Gold status is used, but only implicitly.**
   - The agent retrieved the Gold priority-reaccommodation clause (loyalty policy §6.1) and gave the Gold service line.
   - It never told the caller that Gold members are prioritized in rebooking.
   - Progressive disclosure keeps benefits for later turns, and the caller never asked. Still, this is a benefit worth one sentence in the details turn.

## Implementation findings

- **The toolbox validates OpenAPI responses as strict JSON Schema.** Two effects:
  - The 3.0 keyword `nullable` is ignored, and the 3.0 validator rejects type arrays.
  - The working combination is an OpenAPI **3.1.0** copy with `type: [T, "null"]`, plus `null` added to nullable enums.

  `voice_common.toolbox_compatible_spec()` builds this copy at creation time, and `--export-openapi` writes it for the portal. The shared `tools/openapi.json` is unchanged.
- **Tool events** arrive as `response.output_item.done` items of type `mcp_call`, named `contoso_air_operations___<operationId>`.
  - An API-level error, such as the 503 from CT655 fault injection, still shows as a successful MCP call. The error is in the payload.
  - In the outage run, the agent retried once and then reported the outage. It did not invent a status.
- **Model availability (East US resource).** These managed models are accepted:
  - `gpt-realtime-2.1`
  - `gpt-realtime-2.1-mini`
  - `gpt-realtime-1.5`

  `gpt-realtime`, `gpt-realtime-mini` and `azure-realtime` returned "not supported in this region". Re-check whenever you use a different resource.
- **Barge-in is simulated from the client.** Synthesized caller audio streams faster than real time, so the agent's reply finishes generating before a real caller could interrupt it.
  - The harness models the interruption by keeping only the first 2.5 s of playback and sending `conversation.item.truncate`.
  - The server then sees only what the caller "heard".
  - Server-side `interrupt_response` with a real microphone is still to be tested.
- **Identity:** `customer_id` is a required structured input that is rendered into the instructions once per session. In the identity-override scenario, the agent refused to look up another customer and made no tool call.
- **Harness checks** are deterministic regex and tool-call assertions in `evaluation/test_cases.json`.
  - Early false positives (version 3) came from overly narrow phrase lists. These were fixed in the harness, not by changing the agent.
  - The checks are a smoke test. They do not judge spoken quality.

## Presenter tips

- After Phase V2, "it" and "that one" make the agent ask "which flight?". That is intended. Answer with a description, such as "the nonstop".
- Expect about 11 seconds before the recommendation is heard in Turn 1, with one progress line before it.
- Mention that booking is intentionally unavailable; the agent says so itself.
- To use the portal playground, publish with `--portal-default`.

## Phase V2 hardening results

Phase V2 used the `V2-*` scenarios in `evaluation/test_cases.json`.
- They are scored by the same harness, which adds Turn 1 metrics, clarification checks and checks for a restated answer.
- The V1 baseline (version 6) was re-run against the stricter V2 hero scenario for comparison.

### V2 version history

| Agent version | Instruction change | V2-hero result |
|---|---|---|
| 6 | V1 baseline | FAIL 36/42 |
| 7 | First V2 rewrite: shorter Turn 1 with the recommendation first, clearer comparisons, ambiguity guidance | FAIL 37/42: duplicate answer after a late policy result, weak connection comparison, asked whether to check policy, no T4 clarification |
| 8 | Answer once after all lookups; the connection comparison names the city and the extra time; pronouns are ambiguous once two or more flights are discussed; never ask whether to check policy | FAIL 39/43: T1 said "current cabin", T4 answered 7:10 without clarifying, T6 assumed 9:20 |
| 9 | New non-negotiable "Ask which flight" rule with neutral worked examples; "book that one" is clarified, then confirmed by flight number and time; the Turn 1 headline names the cabin | PASS 43/43 once, then **10/16** in the repeat batch (hero 0/4) |
| 10 | Described references are answered directly; at most one extra policy search, never after the answer; the turn ends once answered; comparisons give the time difference and name the cabin; action turns are statements, not yes/no questions, with the phone number | **16/17** in the repeat batch (hero 4/5) |
| 11 | v10 instructions plus `--portal-default` so the portal playground can connect | Same instructions as v10; used for the live portal call. Phase V3 smoke: 4/6 strict, facts correct in 6/6 ([validation-record.md](validation-record.md)) |

Version 9's repeat failures:
- the agent over-clarified "the connecting flight";
- it gave no comparative "longer";
- it left out the 3:45 time;
- it gave a duplicate answer after a second policy search;
- it asked "…yes?" instead of stating the limitation.

Version 10's instruction changes targeted each of these.

### Turn 1: V1 compared with V2

Times are from the end of the caller's speech.

| Metric | v6 (V1) | v10 median of 5 |
|---|---|---|
| Progress utterances before the answer | 3 | 1 |
| Recommendation heard at | 23.8 s | 11.5 s |
| Turn 1 agent audio | 37.2 s | 19.4 s |
| First agent audio | 1.6 s | 1.1 s |

### v10 repeated runs

The summary is in `results/report-20261125-034104.md` (git-ignored).

| Scenario | Passed |
|---|---|
| V2-hero | 4/5 |
| V2-followup | 3/3 |
| V2-action | 3/3 |
| V2-interruption | 2/2 |
| V2-identity | 2/2 |
| V2-outage | 2/2 |

- The only failure was hero r4, Turn 3. The connection answer said "can't keep all four of you together in your booked cabin" without naming Main Cabin, and gave only "longer" with no amount.
- Ambiguity handling in the hero runs:
  - "it" (T4) and "that one" (T6) got "which flight?" in 5/5 runs.
  - The described reference "the connecting flight" (T3) was answered directly in 5/5 runs.

### Portal and live microphone

- **Portal finding:** the playground sends no structured inputs. Any version where `customer_id` is required and has no default returns HTTP 400 at connect time ("Failed to connect to the voice agent").
  - Fix: `create_agent.py --portal-default` makes `customer_id` optional, defaulting to the demo customer.
  - Version 11 was published this way.
- **Live barge-in:** the reviewer made a live portal-playground call on v11 and interrupted twice. The agent stopped and listened both times.
- **Human rubric:** see [`v2-human-review.md`](v2-human-review.md). Ratings:

  | Dimension | Rating |
  |---|---|
  | Naturalness | Acceptable |
  | Brevity | Good |
  | Clarity | Acceptable |
  | Progress behavior | Good |
  | Pronunciation | Acceptable |
  | Turn-taking | Good |
  | Context | Good |
  | Trust | Good |
