# Phase V2 human-review rubric — hero call

> **Status: reviewed.** The coding agent drafted these ratings from the five
> v10 `V2-hero` harness transcripts. The demo owner reviewed the draft after a
> live v11 portal call, accepted it, and rated pronunciation, which the
> transcripts can't show (see sign-off below).

- Agent: `contoso-air-customer-care-voice`, version 10. Version 11 uses the same
  instructions and only adds the portal default for `customer_id`.
- Runs reviewed: `20261125-032241-V2-hero-r1` through `20261125-032923-V2-hero-r5`.
- Live evidence: in the reviewer's portal-playground call on v11, the reviewer
  interrupted twice and the agent stopped and listened both times.
- Scale: Good / Acceptable / Needs improvement.

| Dimension | Draft rating | Notes |
|---|---|---|
| Naturalness | Acceptable | Warm openers ("Absolutely.", "Of course."). The answer sentence is nearly identical in every run ("Alex, I confirmed your Seattle to New York flight tomorrow is cancelled."), which sounds scripted. Some odd phrasing: a "Tradeoff:" label (r1 T2), "about nearly three hours" (r5 T3), "on this call in this version" (r1 T6b). |
| Brevity | Good | Turn 1 agent audio: median 19.4 s (v6 baseline: 37.2 s). The recommendation is heard at a median of 11.5 s (v6: 23.8 s). Follow-ups mostly run 14–20 s. The action turn (T6b) runs 18–24 s, which is acceptable because it carries the flight, the limitation and a phone number. |
| Clarity | Acceptable | The recommendation comes first, then one reason; times include "morning"/"afternoon". The later-flight answer (T5) clearly says why 3:45 doesn't work. Weakness: r4 T3 said the connection "can't keep all four of you together in your booked cabin" without saying the party could travel together in Main Cabin; the other four runs did. Four runs gave the extra time as an amount (about 2 h 45 m, or "about three hours"); r4 said only "longer". |
| Progress behavior | Good | Turn 1 had 1 progress line in 4 runs and 2 in r5, all before the tools finished, with no restated answer after the recommendation. One unnecessary filler in r5 T5 ("Let me think through the options we already found") when no lookup was needed. |
| Pronunciation | Acceptable (reviewer) | Reviewer, after the live v11 portal call: "not too bad". The model's transcript shows "C T 226" and "C T two twenty-six", so flight numbers are spelled out as letters. Phone numbers appear as digits. Needs a listen to confirm "C T two twenty-six", "nine twenty", "1-800-555-0157" and "Chicago" sound natural. |
| Turn-taking | Good | The scripted barge-in at 2.5 s into T2 was handled in 5/5 runs. The reviewer's portal call confirmed two live interruptions. First audio arrives about 1.1–1.3 s after the caller stops in Turn 1 and 0.5–3 s in follow-ups. |
| Context | Good | The reservation is never fetched again after Turn 1. Ambiguous "it" (T4) and "that one" (T6) got "which flight?" in 5/5 runs, and described references ("the connecting flight", "something later") were answered directly in 5/5. The T6 clarification lists slightly different candidate sets across runs, but always plausible ones. |
| Trust | Good | Says "I confirmed" only for facts verified by tools; the fee waiver is attributed to policy ("based on policy… for an eligible alternative"); it never claims a booking happened; it states the can't-book limitation and gives the Gold line from the escalation guide. No invented times, seats or benefits. |

## Overall (draft)

The call is usable for a demo. Turn 1 is about twice as fast to the
recommendation as V1, and the agent handles interruptions and ambiguity well.
The main improvement areas are: (1) when explaining the connection, always
say that Main Cabin keeps everyone together and give the extra time as an
amount (r4 did neither); (2) vary the wording of the answer sentence;
(3) confirm pronunciation by listening.

## Reviewer sign-off

- Reviewer: demo owner, 2026-11-24, after a live v11 portal-playground call.
- Adjustments: the draft ratings were accepted as written. Pronunciation was
  rated Acceptable ("not too bad").
