# Voice demo validation record (Phase V3)

The evidence behind promoting the voice agent to the primary Customer Service demo. The earlier V1 and V2
history is in [foundation-notes.md](foundation-notes.md); the human rubric is in
[v2-human-review.md](v2-human-review.md).

## Validated configuration

| Setting | Value |
|---|---|
| Agent | `contoso-air-customer-care-voice`, **version 11** |
| Kind | Foundry voice-based prompt agent |
| Model | `gpt-realtime-2.1` (managed) |
| Voice | `en-US-AvaNeural` |
| Turn detection | Azure semantic VAD, interruption (barge-in) on |
| Tools | one toolbox: Contoso Air Operations API (3 operations) + File Search over the 4 policy documents |
| Instructions | [`../agent/instructions.md`](../agent/instructions.md) (unchanged since version 10) |
| Customer context | `customer_id` structured input; demo-only default `CUST-1007` so the portal playground can connect |

Version 11 has the same instructions as version 10. The only difference is the portal default for `customer_id`.
`python voice\scripts\validate_voice_demo.py` checks every row of this table against the deployed agent.

## v11 hero smoke runs

Six complete `V2-hero` calls (`python voice\agent\run_session.py --scenario V2-hero --repeat 3 --version 11`, run
twice). Each call is the full hero conversation: the opening request, details, a barge-in about the connecting
flight, "what time does it leave again?", "something later", and "book that one". The run folders are
git-ignored under `voice/results/`.

Times are in seconds from the end of the caller's Turn 1 speech.

| Run | Checks | First audio | Recommendation heard | Progress lines | Turn 1 audio | Turn 1 speech ends | Call total |
|---|---|---|---|---|---|---|---|
| 1 | 43/44 | 1.4 | 14.6 | 2 | 25.8 | 27.2 | 106.7 |
| 2 | **44/44** | 1.1 | 11.9 | 1 | 19.2 | 24.4 | 105.8 |
| 3 | 43/44 | 1.5 | 15.9 | 2 | 40.7 | 42.2 | 105.7 |
| 4 | **44/44** | 1.5 | 10.7 | 1 | 17.2 | 22.4 | 108.7 |
| 5 | **44/44** | 1.3 | 17.0 | 2 | 27.2 | 28.5 | 101.1 |
| 6 | **44/44** | 1.4 | 11.4 | 1 | 19.0 | 24.4 | 99.6 |
| **Median** | 4/6 strict | **1.4** | **13.3** | 1.5 | **22.5** | **25.8** | **105.8** |

"Call total" is the harness wall-clock time for the whole scripted call (six caller turns), including speech
synthesis of the caller's audio.

**In all six runs:**

- the demo customer context was used (`CUST-1007`, Alex Johnson), and the tools were called with the right
  arguments: reservation, CT218 status on 2026-11-25, alternatives for SEA→JFK, 4 passengers, Economy Plus;
- the agent confirmed the cancellation, searched the policy knowledge and recommended the **9:20 nonstop, CT226,
  in Economy Plus**, for keeping all four together;
- the connecting option (7:10 via Chicago) was explained as not fitting four in Economy Plus, with Main Cabin as a
  downgrade; the 3:45 flight was explained as not fitting all four;
- "What time does it leave again?" and "book that one" got a "which flight?" clarification, and the agent then said
  it can't book or change the reservation and gave a phone number;
- no fees, amounts, meal/hotel or priority claims in Turn 1, no "guarantee", no claim that anything was booked,
  held or changed;
- no tool failures and no session errors.

**Failed checks (not hidden):**

- **Run 1, Turn 3:** the connection answer didn't say how much longer the trip takes (the check expects "longer"
  or an amount). The facts given were correct. v10 hero run 4 had the same wording gap.
- **Run 3, Turn 1:** the agent spoke its Turn 1 answer **twice** (identical text, about 13 s of extra audio, so
  Turn 1 ran 42 s). The content was correct. Version 9 showed the same duplicate once in 4 hero runs; v10 showed
  it 0 times in 5. It's occasional model behavior, not a change in v11. On stage, the presenter can talk over it
  or simply say "Yes, tell me the details." to move on (barge-in stops it).

**Other observations:**

- **Speech-to-text:** the caller line "The nonstop at nine twenty." is transcribed as "The nonstop at 920." in
  every run (similarity 0.67 is a formatting difference). The agent understood it each time. All other caller
  lines transcribed exactly.
- **Contact number:** 5 runs gave the Gold line (1-800-555-0157). Run 3 gave the General Customer Care line
  (1-800-555-0142), which is a valid line but not the Gold one. v10 showed this once (action run 1).
- **Audio:** no truncated or garbled agent audio in the recordings. Flight numbers are sometimes spelled out ("C T
  two twenty-six").

**Compared with v10 (median of 5 hero runs):** first audio 1.4 s vs 1.1 s; recommendation heard 13.3 s vs 11.5 s;
Turn 1 audio 22.5 s vs 19.4 s. These are within run-to-run variance: v10's runs ranged 11.0–16.6 s
(recommendation heard) and 18.4–27.9 s (Turn 1 audio); v11's ranged 10.7–17.0 s and 17.2–27.2 s, apart from the
duplicated answer in run 3. The behavior is the same. **No material regression.**

## Earlier repeated runs (v10, same instructions)

16/17 across the V2 scenarios: hero 4/5, follow-up 3/3, action 3/3, interruption 2/2, identity 2/2, outage 2/2.
Details are in [foundation-notes.md](foundation-notes.md#v10-repeated-runs).

## Real microphone (Foundry portal, v11)

| Check | Result |
|---|---|
| Session connects in the portal playground | Pass (after the portal-default fix that created v11) |
| Barge-in with a real voice | Pass: interrupted twice, the agent stopped and listened both times |
| Human rubric | All dimensions Good or Acceptable; see [v2-human-review.md](v2-human-review.md) |
| Final V3 rehearsal of the full script | Pass with a close-talk microphone (attempt 2); attempt 1 failed on echo from built-in speakers |

### Final rehearsal (Phase V3 §2)

**Attempt 1: laptop built-in speakers and microphone.** Not usable. The agent kept answering things nobody had
asked. The playground transcript showed user messages that were echoes of the agent's own sentences, so the
microphone was transcribing the agent's speech as the caller. This is an audio-setup problem (echo), not an agent
defect. The setup checklist now requires a close-talk microphone, and the troubleshooting guide covers the symptom.

**Attempt 2: close-talk microphone, fresh v11 session.** Passed. The presenter followed the full script:

| Step | Result |
|---|---|
| Opening request | Recommended the 9:20 nonstop (CT226) |
| "Wait, what about the connecting flight?" (interrupting) | The agent stopped and answered about the connection; context kept |
| "What time does it leave again?" | Asked which flight |
| "Okay, book that one." | Asked which flight, then said it can't book and gave a phone number (which line was not recorded) |
| Audio | No echo with the close-talk microphone |

## Timed dry run (Phase V3 §16)

The presenter's dry run took **under 5 minutes** in total, with **about 2–3 minutes** of live conversation,
within the [demo script](demo-script.md) timeline. No awkward waits or audio problems were reported with the
close-talk microphone. The Demo 1A fallback was confirmed ready (`python scripts\validate_demo.py`: **DEMO
READY**).

## Promotion decision

The v11 smoke runs showed no material regression from v10, and the real-microphone rehearsal passed with the
correct audio setup. **Demo 1B Voice is the primary Customer Service demo; Demo 1A Text is the validated fallback.**

## Automated validation at promotion

| Check | Result |
|---|---|
| Voice offline tests (`python -m pytest voice/tests`) | 46 passed |
| Demo 1A offline tests (`python -m pytest`) | 111 passed |
| Synthetic data (`python data/generate_data.py --check`) | Current and valid |
| Policy PDFs (`python knowledge/build_pdfs.py --check`) | Present and within page targets |
| Voice readiness (`python voice/scripts/validate_voice_demo.py`) | VOICE DEMO READY, 0 failures, 0 warnings |
| Demo 1A readiness (`python scripts/validate_demo.py`) | DEMO READY, 0 failures, 0 warnings |
| Secret scan (GUIDs, Azure endpoints, keys, local paths) over all new and changed files | No matches |
