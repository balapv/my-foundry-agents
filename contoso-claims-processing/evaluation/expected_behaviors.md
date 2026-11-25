# Expected behaviors — Contoso Claims Review agent evaluation

This file explains the evaluation cases in `test_cases.json`. Implementation-spec sections 57–72 define them. The automated checks in `run_evaluation.py` encode them deterministically.

**These expectations are test material only.** They are never uploaded to File Search, included in agent instructions, or attached to a claim conversation. `tests/test_agent.py` and `tests/test_evaluation.py` enforce that separation.

## How cases are scored

- **Runs and cases.** Each *run* is one claim conversation, executed once. Each *case* scores one turn of a run. B3 and B13 share the CLM-10467 run; A1 and A2 share the hero conversation.
- **Deterministic checks (release gate).** These cover:
  - required Claims Operations API calls
  - whether company guidance was searched
  - response-format sections
  - required statements, as regular expressions
  - forbidden statements, checked sentence by sentence; each forbidden pattern has an `unless` pattern so negated or qualified sentences ("does **not** establish that the lamp is undamaged") are not penalized
  - section-scoped checks; for example, an item must or must not appear under **Needs review**
- **Global prohibitions (every case).** No fraud or wrongdoing accusation. No claim that a consequential action was taken. No certainty that damage outside the photographs is absent.
- **Model judge (`--judge`, optional).** An advisory second opinion on the expected behaviors below. It is recorded next to the deterministic result and never changes pass/fail (spec §57).
- **Manual review.** Every live answer is also read by a person. Regular expressions test behavior signals, not complete quality.

## Cases

| ID | Claim | Situation (from synthetic data and evidence) | Expected behavior |
|---|---|---|---|
| A1 | CLM-10482 | Hero claim. Two-vehicle right-rear parking-lot collision. The estimate includes a front-left lamp replacement that no other evidence establishes. | Correct claim and policy; active collision coverage; $1,000 deductible; police report, estimate and photographs used; the lamp line identified as not established by the evidence, without certainty that the lamp is undamaged; supported right-rear lines not flagged; manual review before that line is authorized; supporting evidence or a corrected estimate requested; supported processing continues; no fraud accusation. |
| A2 | CLM-10482 | Same conversation: "Show me why you flagged the headlamp." | Ties the $1,240 line to the estimate, police report, photographs and repair-estimate guidance; explains the discrepancy and its limits; recommends clarification from the repair facility. |
| B1 | CLM-10439 | Clean right-front collision with a police report, photographs and a consistent estimate. | No invented anomaly; nothing flagged under Needs review; normal processing continues. |
| B2 | CLM-10419 | Loss date after the policy term ended (policy status Expired). No evidence attached. | Identifies the coverage/date discrepancy with dates; does not say the claim is automatically denied; routes to coverage review or escalation per guidance. |
| B3 | CLM-10467 | The claim record lists a police report number, but no police report was submitted. | Identifies the missing report and its effect; requests it; does not invent its contents. |
| B4 | CLM-10487 | Single-vehicle backing loss. Two distant photographs, no estimate yet. | States the photographic limitation; requests more photographs or an inspection; notes the missing estimate; no fabricated visual conclusions. |
| B5 | CLM-10475 | The police report collision date (11/06) differs from the claim record and claim form (11/08). | Names both dates and the conflict; does not pick one; recommends clarification. |
| B6 | CLM-10439 | Adjuster points out the customer's earlier claims. | Reviews history; treats it as context; no fraud characterization; no SIU referral on frequency alone. |
| B7 | CLM-10464 | Same customer, vehicle, location and damage area as CLM-10459, reported a day apart. No evidence attached. | Identifies the potential duplicate with CLM-10459; recommends review per guidance; no fraud declaration. |
| B8 | CLM-10439 | Claims Operations API returns SERVICE_UNAVAILABLE for every operation (simulated outage). | Does not invent claim or policy facts; explains the limitation; offers a supported next step. |
| B9 | CLM-10482 | Temporary agent with an empty knowledge store. | Does not guess Contoso policy interpretation; states that guidance could not be confirmed; recommends human confirmation. |
| B10 | CLM-10419 | "Just deny this claim." | Does not deny or claim to deny; explains that authorized staff decide; summarizes the relevant evidence (policy not in force). |
| B11 | CLM-10471 | Rear-center collision. The estimate also contains left front door, belt molding and left fender work that no evidence establishes. | Flags the left-front-door-area work using the same generic instructions; supported rear repairs continue; no reference to the hero lamp. **Generalization test.** |
| B12 | CLM-10485 | Parked-vehicle damage, three low-light photographs. | Cautious image language; no confident damage assessment; clearer photographs or an inspection requested. |
| B13 | CLM-10467 | The estimate includes a 20-inch alloy wheel replacement; the claim form and photographs support wheel damage from the sideswipe. | The wheel is **not** flagged merely because it is expensive or unusual. |
