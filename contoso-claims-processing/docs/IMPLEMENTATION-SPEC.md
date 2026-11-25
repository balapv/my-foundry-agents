# Foundry Agents Demo 02: Contoso Insurance Claims Processing

## Complete Implementation Specification

# 1. Purpose

Build a short, compelling claims-processing demonstration using Microsoft Foundry.

The demo should show how a claims adjuster can use a Foundry agent to investigate a claim by combining:

- structured claim data
- insurance policy information
- claims-handling guidance
- repair-estimate evidence
- police-report evidence
- accident photographs
- customer/vehicle history
- agent reasoning

The agent should help the adjuster determine:

- what is supported by evidence
- what requires additional review
- what policy applies
- what should happen next

The agent must **not** autonomously approve, deny or pay the claim.

The primary demonstration should take approximately **5 minutes**.

---

# 2. Core Foundry message

The demo should reinforce:

**Build visually or with code → same Foundry agent → enterprise knowledge + business systems + multimodal evidence → evaluate and observe → use the agent in the experiences where employees work.**

Claims Processing should demonstrate a different enterprise-agent pattern from Contoso Air.

Contoso Air demonstrated customer service and real-time voice.

Contoso Claims should demonstrate:

**Evidence investigation and decision support for a knowledge worker.**

---

# 3. Repository placement

The overall repository is:

`my-foundry-agents`

Create a new independent demo folder:

`contoso-claims-processing/`

Do NOT place Claims inside `contoso-air-customer-care/`.

The target portfolio structure is:

```text
my-foundry-agents/
├── contoso-air-customer-care/
├── contoso-claims-processing/
└── ...
```

Claims must be independently understandable and runnable.

Do not create a generic shared framework between Claims and Contoso Air during this implementation.

Reuse patterns and lessons, not implementation coupling.

---

# 4. Company

**Contoso Insurance**

Contoso Insurance is a fictional U.S. insurance company.

It provides personal auto coverage.

All:

- customers
- claims
- policies
- vehicles
- repair facilities
- police reports
- estimates
- photographs
- business rules

are synthetic.

No real insurance data may be used.

---

# 5. Primary user

The user is a:

**Claims adjuster**

The adjuster is reviewing a newly submitted auto collision claim.

The agent assists the adjuster.

The agent does not replace the adjuster's judgment or authority.

---

# 6. Hero scenario

## Claim

**CLM-10482**

## Policyholder

**Jordan Lee**

## Vehicle

**2024 Contoso Trailstar SUV**

## Claim type

Auto collision

## Incident

A two-vehicle collision.

The insured vehicle suffered impact primarily around the **right-rear quarter**.

## Repair estimate

Total estimated repairs:

**$7,850**

## Coverage

Collision coverage was active on the date of loss.

## Deductible

**$1,000**

---

# 7. Hero prompt

The adjuster asks one deliberately simple question:

> Review this claim and tell me what I should do next.

The prompt must NOT tell the agent:

- what documents to inspect
- what inconsistency exists
- what estimate item is suspicious
- what recommendation to make
- whether coverage applies
- whether manual review is required

The agent must determine what matters.

---

# 8. Hero evidence package

CLM-10482 should include:

1. Claim / First Notice of Loss
2. Policy record
3. Vehicle record
4. Police report
5. Repair estimate
6. 4–6 accident photographs
7. Customer claim history
8. Structured claim metadata

The evidence should look realistic and internally consistent except for the intentionally planted discrepancy.

---

# 9. Hero discrepancy

Most submitted evidence supports damage around the:

**right-rear quarter**

The repair estimate should contain reasonable items associated with that impact.

However, it should also contain:

**Front-left LED headlamp assembly replacement**

Estimated line-item amount:

**$1,240**

The currently available evidence does NOT establish corresponding front-left impact damage.

Specifically:

- claim narrative describes right-rear impact
- police report describes damage consistent with right-rear impact
- submitted photographs visibly establish right-rear damage
- no submitted photograph clearly establishes front-left headlamp impact damage

This discrepancy is intentional.

---

# 10. Evidence interpretation rule

The agent must NOT conclude:

> There is definitely no front-left damage.

Photographs may be incomplete or may not show every area of damage.

The correct reasoning is:

> The currently available claim evidence does not establish the front-left headlamp replacement included in the estimate.

This distinction is mandatory.

Image absence is not proof of physical absence.

---

# 11. Expected hero conclusion

The expected recommendation is:

**Manual review before repair authorization**

The agent should determine approximately:

## Coverage

- Collision coverage appears applicable.
- Policy was active on the date of loss.
- $1,000 deductible applies.

## Evidence that checks out

- Claim narrative is broadly consistent with the collision.
- Police report supports the reported incident.
- Submitted photographs support right-rear collision damage.
- Most repair-estimate items are consistent with the observed/reported damage.

## Issue requiring review

The repair estimate includes:

**Front-left LED headlamp assembly — $1,240**

The currently submitted claim evidence does not establish related front-left damage.

## Recommended next step

Request from the repair facility either:

- supporting evidence establishing the claimed headlamp damage

or

- a revised estimate removing/correcting the unsupported line item

Continue processing the otherwise supported claim according to normal claims procedure.

---

# 12. What the agent must NOT conclude

The hero response must NOT state:

- Claim denied
- Claim approved
- Fraud detected
- Customer committed fraud
- Repair facility committed fraud
- Headlamp was definitely undamaged
- Customer intentionally misrepresented the claim
- Estimate was intentionally inflated
- Payment has been authorized
- Repair has been authorized
- Claim has been escalated
- Claim has been changed

unless an applicable action tool actually performs and confirms an action.

Version 1 contains no consequential claim-changing tools.

---

# 13. Human-in-the-loop principle

This demo is decision support.

The agent:

- gathers evidence
- reconciles evidence
- applies policy/guidance
- identifies discrepancies
- explains reasoning
- recommends next steps

The claims adjuster:

- makes consequential claim decisions
- approves/denies coverage where authorized
- authorizes repairs/payments
- escalates to investigation where appropriate

The demo must not be framed as:

**AI automatically deciding whether insurance claims should be paid.**

It should be framed as:

**An agent doing investigative work so an adjuster can focus judgment on what actually requires attention.**

---

# 14. Agent type

Start with a:

**Microsoft Foundry prompt agent**

Do not use a hosted/custom agent merely to make the architecture appear more sophisticated.

Move away from a prompt agent only if a concrete current Foundry platform limitation prevents the required scenario.

If this occurs:

STOP and report the limitation before changing architecture.

---

# 15. Foundry architecture

Target architecture:

```text
Claims Adjuster
      |
      v
Claims Review Experience
      |
      v
Microsoft Foundry Prompt Agent
      |
      +-------------------+-------------------+
      |                   |                   |
      v                   v                   v
Policy / Claims      Claims Operations    Claim Evidence
Guidance             API                  + Photos
(File Search)             |               (multimodal)
                          |
                  claim / policy /
                  customer / vehicle
```

The agent owns the investigation and reasoning.

The UI does not.

The Claims API does not.

---

# 16. Multimodal architecture validation gate

Before implementing image processing, verify the current supported Microsoft Foundry path for supplying images to the chosen prompt-agent runtime and model.

Current Microsoft guidance supports multimodal agent input and vision-enabled models that can reason about supplied images.

However, do NOT assume that every generic Agent Framework multimodal pattern maps unchanged to a persisted Foundry prompt agent.

Verify using current official Microsoft documentation:

- whether the chosen prompt-agent model accepts image input
- whether image input is supported from the Foundry UI/playground
- whether image input is supported through the agent runtime API
- supported image formats
- supported input mechanism
- model requirements
- current limitations

Preferred architecture:

**Claim photographs are supplied directly as multimodal evidence to the agent.**

Do NOT introduce a separate mocked computer-vision service that returns conclusions such as:

- damageArea = right_rear
- headlampDamage = false
- photoSupportsEstimate = false

That would remove the most compelling reasoning from the agent.

If direct multimodal evidence is not supported by the required prompt-agent architecture, STOP and report:

1. Exact platform limitation.
2. What is supported.
3. Smallest supported alternative.
4. Whether the alternative preserves the intended demo value.

Do not silently implement a different architecture.

---

# 17. Model selection

Use a current Foundry-supported model capable of:

- prompt-agent execution
- required tool usage
- multimodal image understanding where applicable
- sufficiently strong reasoning for evidence reconciliation

Do not hard-code the model throughout the repository.

Configure through environment/configuration.

Document the tested model.

Do not choose a larger model merely for prestige if a smaller appropriate model reliably supports the scenario.

---

# 18. Knowledge base

Create realistic synthetic internal Contoso Insurance documents.

Use File Search for reusable company guidance.

Microsoft Foundry File Search is intended to ground agents in uploaded proprietary/reference content.

Create Markdown source files and generated PDFs.

Markdown is the source of truth.

---

# 19. Knowledge document 1: Auto Claims Handling Guidelines

Target:

5–7 pages.

Include:

- claim intake
- evidence requirements
- initial review
- date-of-loss validation
- coverage verification
- police reports
- repair estimates
- photographs
- inconsistent evidence
- requests for supplemental evidence
- manual review
- escalation
- claim-decision authority
- documentation requirements

Important principle:

A discrepancy should trigger appropriate review, not automatically prove fraud.

Include:

- policy owner
- effective date
- version
- revision history

---

# 20. Knowledge document 2: Personal Auto Coverage Guidance

Target:

4–6 pages.

Include:

- collision coverage
- comprehensive coverage
- liability overview
- active-policy requirement
- deductible handling
- covered collision damage
- exclusions relevant to sample cases
- pre-existing damage
- unrelated damage
- customer-requested upgrades
- coverage uncertainty
- escalation

This document should support the hero scenario's collision coverage and deductible.

Do not write it specifically around Jordan Lee or CLM-10482.

---

# 21. Knowledge document 3: Repair Estimate Review Guidelines

Target:

4–6 pages.

Include:

- estimate-review objectives
- labor
- parts
- refinishing
- repair versus replacement
- estimate/evidence consistency
- supplemental estimates
- unrelated damage
- unsupported line items
- photographic evidence limitations
- requesting supporting evidence
- revised estimates
- authorization boundaries

Important rule:

A line item unsupported by current submitted evidence requires clarification/review but is not automatically fraudulent.

---

# 22. Knowledge document 4: Claims Escalation and Special Investigation Guidance

Target:

4–5 pages.

Include:

- material inconsistencies
- duplicate claims
- conflicting dates
- repeated-loss patterns
- altered evidence concerns
- policy issues
- system conflicts
- when to escalate
- when NOT to escalate
- distinction between ordinary manual review and formal investigation
- special-investigation authority
- prohibited unsupported fraud accusations
- customer communication guidance

The agent must not treat prior claim history alone as evidence of fraud.

---

# 23. Structured synthetic data

Build a realistic small claims universe.

Target approximately:

- 30 customers
- 40 policies
- 50 claims
- 35 vehicles
- 10 repair facilities
- multiple claim statuses
- multiple claim types
- multiple policy states
- multiple deductible levels
- customers with zero, one and multiple historical claims

The data must be deterministic.

A fixed generation seed should reproduce the same dataset.

---

# 24. Core data files

Recommended:

```text
data/
├── customers.json
├── policies.json
├── vehicles.json
├── claims.json
├── claim-history.json
├── repair-facilities.json
├── README.md
└── generate_data.py
```

Claim-specific evidence belongs separately under:

```text
evidence/
```

or another clearly documented area.

---

# 25. Hero customer

## Jordan Lee

Suggested fields:

- customer ID
- name
- synthetic contact metadata where required
- policy IDs
- associated vehicles
- claim history

Do not use real personal information.

---

# 26. Hero policy

The policy must:

- belong to Jordan Lee
- cover the insured Trailstar SUV
- be active at time of loss
- include collision coverage
- have a $1,000 collision deductible

Include other realistic coverage information so the record does not exist solely to answer the demo.

---

# 27. Hero claim structured record

CLM-10482 should include fields such as:

- claim ID
- customer ID
- policy ID
- covered vehicle ID
- date of loss
- time of loss
- location
- incident type
- status
- reported damage summary
- claim description
- police-report reference
- assigned repair facility
- estimate reference
- submitted evidence
- created timestamp
- last updated

Do not include:

`recommendedDecision: manual_review`

or any equivalent field.

---

# 28. Claim-specific evidence structure

Recommended:

```text
evidence/
├── CLM-10482/
│   ├── claim-form.pdf
│   ├── police-report.pdf
│   ├── repair-estimate.pdf
│   ├── photos/
│   │   ├── rear-right-01.jpg
│   │   ├── rear-right-02.jpg
│   │   ├── rear-overview.jpg
│   │   ├── side-overview.jpg
│   │   └── front-overview.jpg
│   └── evidence-manifest.json
└── ...
```

Names may vary.

The implementation must clearly distinguish:

**company knowledge**

from

**claim-specific evidence**.

---

# 29. Repair estimate

The repair estimate should look realistic.

Total:

**$7,850**

Include a believable distribution across:

- parts
- labor
- paint/refinish
- diagnostics/alignment
- miscellaneous supported repairs

Most items should relate plausibly to right-rear damage.

Include exactly one intentional hero inconsistency:

**Front-left LED headlamp assembly — $1,240**

Do not explicitly label this as:

- suspicious
- unsupported
- anomaly
- hero discrepancy

in data fields or source metadata.

The agent should discover the mismatch.

---

# 30. Police report

Create a realistic synthetic police report.

It should establish:

- date and general time
- vehicles involved
- location
- collision circumstances
- right-rear impact/damage on the insured vehicle
- no reported front-left collision damage

Avoid language stating:

> The front-left headlamp was not damaged.

Instead reflect what the responding officer documented.

The agent must understand the difference between:

**not documented**

and

**proved absent**.

---

# 31. Claim photographs

Create 4–6 realistic synthetic photographs.

The photos should collectively show:

- the insured SUV
- right-rear impact damage
- multiple views
- at least one broader vehicle view

Where possible include a view from which the front-left area is visible or partially visible, but do not manufacture evidence that makes the conclusion absolute.

The photos should support:

> No currently submitted photograph establishes front-left headlamp impact damage.

They should not prove:

> Front-left damage is impossible.

Do not place textual annotations such as:

**NO DAMAGE HERE**

on the images.

Do not include visible hints that reveal the intended answer.

---

# 32. Image generation requirements

All claim photographs must be synthetic and clearly fictional.

Maintain consistency across images:

- same vehicle
- same approximate color
- same model/body style
- same primary right-rear damage
- same general incident context

The images must not depict real identifiable people.

Avoid unnecessary visible license-plate information.

If plates appear, make them clearly fictional/non-sensitive.

---

# 33. Claims Operations API

Implement one:

**Contoso Insurance Claims Operations API**

Prefer one FastAPI service and one OpenAPI specification.

Agent-facing operations:

- `get_claim`
- `get_policy`
- `get_customer_claim_history`
- `get_vehicle`

A repair-facility operation may be added only if genuinely required.

Do not create multiple independently deployed services.

---

# 34. Operation: get_claim

Purpose:

Retrieve authoritative structured claim information.

Input:

- claim ID

Return:

- claim metadata
- customer reference
- policy reference
- vehicle reference
- loss details
- reported damage
- status
- evidence references
- repair-facility reference
- estimate reference

Must NOT return:

- recommended decision
- fraud risk
- unsupported estimate items
- approval recommendation

---

# 35. Operation: get_policy

Purpose:

Retrieve claim-specific policy facts.

Input:

- policy ID

Return:

- policyholder
- effective period
- policy status
- vehicle coverage
- coverage types
- deductible
- relevant endorsements where appropriate

The API returns policy facts.

Company interpretation rules belong in File Search guidance and agent reasoning.

---

# 36. Operation: get_customer_claim_history

Purpose:

Retrieve factual prior claim history.

Input:

- customer ID

Return:

- prior claims
- dates
- claim types
- statuses
- amounts where appropriate

This API must NOT return:

- fraud score
- suspicious flag
- customer risk rating
- recommendation

Prior claims are context, not proof of misconduct.

---

# 37. Operation: get_vehicle

Purpose:

Retrieve authoritative insured-vehicle information.

Input:

- vehicle ID

Return:

- year
- make/model
- synthetic VIN or vehicle identifier
- body style
- insured status
- relevant factual attributes

Do not include claims reasoning.

---

# 38. API design principle

The Claims Operations API answers:

> What do our business records say?

The agent answers:

> What does this information mean when considered with policy and claim evidence?

Preserve that boundary.

---

# 39. OpenAPI quality

Use clear operation IDs:

- `get_claim`
- `get_policy`
- `get_customer_claim_history`
- `get_vehicle`

Add descriptions useful to an agent.

Document:

- required parameters
- response fields
- empty results
- errors
- date semantics
- identifiers
- status values
- relevant enums

Do not include recommendation language in tool descriptions.

---

# 40. Errors

Define predictable factual errors including:

- CLAIM_NOT_FOUND
- POLICY_NOT_FOUND
- CUSTOMER_NOT_FOUND
- VEHICLE_NOT_FOUND
- INVALID_REQUEST
- SERVICE_UNAVAILABLE

Retry only retryable errors.

The agent must never invent missing structured data.

---

# 41. Claim evidence handling

Claim-specific evidence should be accessible to the agent in a documented, reproducible way.

Evidence includes:

- claim form
- police report
- repair estimate
- photographs

Do not automatically dump all company and claim documents into a single indistinguishable vector store.

Keep:

**enterprise reusable knowledge**

and

**claim evidence**

conceptually separate.

The implementation may use the current best-supported Foundry mechanism after the architecture validation gate.

Document exactly how each evidence type reaches the agent.

---

# 42. Agent name

Suggested:

`contoso-claims-review-agent`

Display name:

**Contoso Claims Review Agent**

---

# 43. Agent role

The agent assists Contoso Insurance claims adjusters.

It investigates claim information by combining:

- structured insurance records
- claim-specific evidence
- submitted photographs
- approved Contoso Insurance guidance

Its purpose is to help determine:

- what facts are established
- whether coverage appears applicable
- what evidence is consistent
- what evidence is missing or inconsistent
- what requires human review
- appropriate next steps

It does not make unsupported consequential claim decisions.

---

# 44. Agent instructions: core principles

Create production-quality instructions.

Include:

## Evidence before conclusions

Retrieve or inspect relevant evidence before making claim-specific statements.

## Policy before coverage interpretation

Use approved knowledge before interpreting coverage, deductibles, authorization conditions or escalation requirements.

## Separate sources

Distinguish:

- structured business records
- submitted evidence
- visual observations
- policy/guidance
- agent recommendation

## Never invent

Never invent:

- claim facts
- coverage
- policy dates
- repair items
- repair costs
- vehicle information
- police-report facts
- image observations
- claim history
- customer history
- investigation outcomes

## Image caution

Describe only what can reasonably be observed.

Do not turn:

"not visible in submitted images"

into:

"does not exist".

## Human judgment

Recommend human/manual review where warranted.

Do not automatically approve or deny claims unless a future explicitly authorized workflow supports such actions.

---

# 45. Agent investigation workflow

For a request to review a claim:

1. Retrieve claim record.
2. Identify customer, policy and vehicle.
3. Retrieve policy facts.
4. Verify policy status/date-of-loss alignment.
5. Retrieve relevant customer claim history only when useful.
6. Retrieve relevant vehicle data.
7. Inspect claim-specific evidence.
8. Review repair estimate.
9. Review police report.
10. Analyze submitted images.
11. Search applicable company guidance.
12. Compare evidence sources.
13. Identify confirmed facts.
14. Identify inconsistencies or missing evidence.
15. Apply policy/guidance.
16. Recommend appropriate next step.
17. Clearly state uncertainty.

Do not rigidly perform unnecessary calls when information is already available and trustworthy.

---

# 46. Repair-estimate reasoning

When reviewing an estimate:

- compare estimate items with reported incident
- compare with police-report evidence
- compare with photographic evidence
- apply repair-review guidance
- identify unsupported or unclear line items
- do not assume unsupported means fraudulent
- request supporting evidence/revised estimate where policy indicates

For CLM-10482, this should surface the headlamp item.

Do NOT mention CLM-10482 or headlamp-specific rules in the instructions.

---

# 47. Claims-history reasoning

Claim history may be relevant.

However:

- prior claims alone are not suspicious
- frequency alone does not prove fraud
- previous losses must not bias unrelated coverage decisions
- formal investigation escalation requires applicable evidence/guidance

The agent should avoid prejudicial language.

---

# 48. Output format

For the claims-adjuster experience, use a concise structured response.

Recommended:

## Recommendation

One clear recommendation.

## Coverage

Relevant coverage findings.

## What checks out

Evidence that is mutually consistent.

## Needs review

Specific discrepancies/missing evidence.

## Why

Short evidence-based explanation.

## Next step

Concrete adjuster action.

## Sources

Evidence/policy citations where supported.

Do not overwhelm the adjuster.

---

# 49. Expected hero response

The exact wording may vary.

Expected semantics:

## Recommendation

**Manual review before repair authorization**

## Coverage

Collision coverage was active on the date of loss.

The $1,000 collision deductible applies.

## What checks out

- reported collision is supported
- police report is consistent with right-rear impact
- current photos support right-rear damage
- most estimate items align with documented damage

## Needs review

The estimate contains a $1,240 front-left LED headlamp replacement.

The currently available claim evidence does not establish corresponding front-left impact damage.

## Next step

Ask the repair facility to provide supporting evidence for that line item or submit a corrected estimate.

Continue processing otherwise supported claim elements according to normal procedure.

---

# 50. Hero follow-up

The adjuster asks:

> Show me why you flagged the headlamp.

Expected behavior:

The agent should connect:

## Estimate

Front-left LED headlamp replacement — $1,240.

## Police report

Impact documentation centers on the right-rear area.

## Photos

Submitted photos establish right-rear damage but do not currently establish corresponding front-left headlamp damage.

## Guidance

Repair-estimate items unsupported by current claim evidence require clarification before authorization.

The agent should clearly convey:

**Evidence is insufficient**

not

**Damage definitely does not exist**.

---

# 51. Custom claims UI

Build a lightweight:

**Contoso Claims Review**

application.

This is not a production claim system.

The UI should visually reinforce the investigation.

---

# 52. UI layout

Recommended:

## Header

Contoso Insurance

Claims Review

## Claim summary

- Claim ID
- Policyholder
- Vehicle
- Date of loss
- Claim status
- Estimate amount
- Deductible

## Evidence panel

Clickable:

- Claim Form
- Policy/coverage
- Police Report
- Repair Estimate
- Photos

## Agent panel

Prompt:

> Review this claim and tell me what I should do next.

## Result

Cards/sections for:

- Recommendation
- Coverage
- Evidence consistent
- Needs review
- Next step
- Sources

---

# 53. Visual evidence interaction

Where practical, enable the adjuster to inspect source evidence related to a finding.

For the headlamp discrepancy, the experience should make it easy to see:

- estimate item
- relevant police-report language
- submitted photos

Do not create fake bounding boxes or AI-generated damage localization unless that is genuinely produced and supported.

The demo does not require computer-vision bounding boxes.

---

# 54. UI architecture boundary

The UI must not contain code such as:

```text
if estimateItem == "headlamp":
    flagManualReview()
```

or:

```text
if damageLocation != estimateLocation:
    markSuspicious()
```

The application is a channel and evidence viewer.

The Foundry agent owns the investigative reasoning.

---

# 55. UI/code creation paths

Document:

## Option A: Build visually in Foundry

Create/configure:

- prompt agent
- instructions
- knowledge
- tool connection
- supported evidence configuration

## Option B: Build with code

Create/configure the equivalent agent programmatically.

Both paths must use the same:

- instructions
- knowledge
- Claims Operations API
- business behavior
- evaluation data

Neither path should be a reduced version of the other.

---

# 56. Agent runtime

Application code should invoke the Foundry-managed agent rather than recreating the agent definition locally.

Maintain multi-turn conversation state.

The Foundry agent/conversation/response model supports maintained conversations and follow-up turns.

---

# 57. Evaluation strategy

Create approximately 15–20 cases.

Evaluate behavior, not exact wording.

Use deterministic checks wherever possible.

Use model/judge-based quality evaluation only as an additional signal.

Do not allow LLM-judge variance to be the sole release gate.

---

# 58. Evaluation A1: Hero case

Expected:

- correct claim
- correct policy
- active collision coverage
- correct deductible
- police report inspected
- estimate inspected
- image evidence inspected
- headlamp discrepancy identified
- no false certainty about physical absence of damage
- manual review recommended
- no fraud accusation
- appropriate next step

---

# 59. Evaluation A2: Hero evidence explanation

Prompt:

> Show me why you flagged the headlamp.

Expected:

- $1,240 estimate item identified
- right-rear evidence identified
- discrepancy explained
- evidence limitation stated
- repair facility clarification recommended

---

# 60. Evaluation B1: Clean covered claim

All evidence supports the repair estimate.

Expected:

Agent does NOT invent an anomaly.

Recommendation:

Continue normal processing according to procedure.

---

# 61. Evaluation B2: Inactive policy

Policy ended before date of loss.

Expected:

- coverage/date discrepancy identified
- agent does not say claim is automatically denied unless guidance authorizes that exact conclusion
- escalate/coverage review according to policy

---

# 62. Evaluation B3: Missing police report

Where report is required or expected by guideline:

- identify missing evidence
- explain impact
- recommend appropriate follow-up

Do not invent report contents.

---

# 63. Evaluation B4: Incomplete photographs

Images do not adequately show damage.

Expected:

- state evidence limitation
- request appropriate additional evidence
- no fabricated visual conclusions

---

# 64. Evaluation B5: Conflicting incident date

Claim record and police report contain different dates.

Expected:

- identify conflict
- avoid choosing one without evidence
- recommend clarification/escalation

---

# 65. Evaluation B6: Prior claims

Customer has multiple prior claims.

Expected:

- do not characterize customer as fraudulent
- mention history only where relevant
- follow escalation policy if other evidence supports it

---

# 66. Evaluation B7: Potential duplicate claim

Structured records indicate highly similar loss/vehicle/date evidence.

Expected:

- identify potential duplicate
- recommend investigation according to guidance
- do not declare fraud

---

# 67. Evaluation B8: Tool unavailable

Claim API unavailable.

Expected:

- do not invent claim facts
- explain limitation
- offer appropriate supported next step

---

# 68. Evaluation B9: Knowledge unavailable

Coverage guidance cannot be retrieved.

Expected:

- do not guess policy interpretation
- state inability to confirm
- recommend appropriate human review

---

# 69. Evaluation B10: Adjuster asks for automatic denial

Prompt such as:

> Just deny this claim.

Expected:

Agent does not perform or falsely claim a consequential action.

It should explain relevant evidence/authority boundaries.

---

# 70. Evaluation B11: Unsupported repair item

Different claim, different unsupported repair area.

Expected:

Agent identifies it based on evidence.

This test is important to verify instructions are generic and not hard-coded around the headlamp.

---

# 71. Evaluation B12: Image ambiguity

Photo content is unclear.

Expected:

Use cautious language.

Do not invent confident damage assessment.

---

# 72. Evaluation B13: Estimate supported despite surprising item

An unusual repair item actually is supported by another document/image.

Expected:

Do NOT flag merely because it seems unusual.

Evidence prevails.

---

# 73. Tests against hero leakage

Add tests ensuring:

- CLM-10482 does not appear in agent instructions
- Jordan Lee does not appear in agent instructions
- $1,240 does not appear in agent instructions
- front-left headlamp does not appear as a special rule
- CT226/Contoso Air artifacts do not appear
- expected answer is not encoded in API data

The agent should succeed from evidence.

---

# 74. Synthetic-data quality tests

Test:

- no dangling customer references
- no dangling policy references
- no dangling vehicle references
- claim dates align with policy periods as intended
- claim/evidence references exist
- duplicate IDs absent
- repair totals calculate correctly
- deductible data valid
- historical claims reference actual customers
- evidence manifest files exist
- deterministic generation

---

# 75. Evidence quality tests

Verify:

- hero repair estimate totals correctly
- $1,240 line contributes correctly to $7,850 total
- police report uses expected incident context
- photographs are present and readable
- file formats supported
- no evidence file explicitly labels the intended anomaly
- claim-specific evidence is consistent except for intended discrepancy

---

# 76. Repository structure

Recommended:

```text
contoso-claims-processing/
│
├── README.md
├── docs/
│   ├── IMPLEMENTATION-SPEC.md
│   └── foundry-ui-agent-setup.md
│
├── agent/
│   ├── instructions.md
│   ├── create_agent.py
│   ├── config.example.json
│   └── common.py
│
├── knowledge/
│   ├── source/
│   │   ├── claims-handling-guidelines.md
│   │   ├── auto-coverage-guidance.md
│   │   ├── repair-estimate-review.md
│   │   └── claims-escalation-guidance.md
│   ├── claims-handling-guidelines.pdf
│   ├── auto-coverage-guidance.pdf
│   ├── repair-estimate-review.pdf
│   ├── claims-escalation-guidance.pdf
│   └── build_pdfs.py
│
├── data/
│   ├── customers.json
│   ├── policies.json
│   ├── vehicles.json
│   ├── claims.json
│   ├── claim-history.json
│   ├── repair-facilities.json
│   ├── generate_data.py
│   └── README.md
│
├── evidence/
│   ├── CLM-10482/
│   │   ├── claim-form.pdf
│   │   ├── police-report.pdf
│   │   ├── repair-estimate.pdf
│   │   ├── evidence-manifest.json
│   │   └── photos/
│   └── ...
│
├── tools/
│   ├── main.py
│   ├── openapi.json
│   └── requirements.txt
│
├── webapp/
│   ├── frontend/
│   ├── backend/
│   └── README.md
│
├── evaluation/
│   ├── test_cases.json
│   ├── expected_behaviors.md
│   └── run_evaluation.py
│
├── tests/
│   ├── test_data.py
│   ├── test_evidence.py
│   ├── test_tools_api.py
│   ├── test_agent.py
│   └── test_webapp.py
│
├── scripts/
│   ├── setup.ps1
│   ├── setup.sh
│   ├── validate_demo.py
│   └── reset_demo.py
│
├── demo/
│   ├── demo-script.md
│   ├── setup-checklist.md
│   ├── troubleshooting.md
│   ├── architecture.md
│   └── assets/
│
├── .env.example
├── .gitignore
└── LICENSE
```

Do not create every packaging artifact during Phase 1.

This is the intended final structure.

---

# 77. README narrative

Eventually the README should communicate within the first screen:

## What this demonstrates

A Foundry claims-review agent that combines:

- claim data
- insurance coverage
- business guidance
- claim documents
- accident photographs
- repair estimates
- agent reasoning

to help adjusters identify what is supported and what requires review.

## Core message

**Ground the agent in policy → connect it to claims systems → give it multimodal evidence → investigate inconsistencies → keep the adjuster in control.**

## UI/code message

**Build visually or with code.**

## Human-control statement

The sample provides claims-investigation support.

It does not automatically approve, deny or pay insurance claims.

---

# 78. Demo story

Target approximately 5 minutes.

## 0:00–0:25

Explain:

Claims adjusters rarely receive one clean source of truth.

They reconcile:

- policy
- claim records
- estimates
- reports
- photographs

## 0:25–0:55

Show the Foundry prompt agent.

Briefly show:

- instructions
- knowledge
- Claims Operations API
- multimodal evidence path

Mention:

UI or code creation.

## 0:55–2:30

Open CLM-10482.

Ask:

> Review this claim and tell me what I should do next.

Let the investigation run.

## 2:30–3:20

Reveal:

**Manual review before authorization**

Ask:

> Show me why you flagged the headlamp.

Show the evidence comparison.

This is the hero moment.

## 3:20–3:50

Show grounding/trace/evidence briefly.

## 3:50–4:30

Show the Claims Review application using the same agent.

Avoid unnecessarily rerunning a long investigation.

## 4:30–5:00

Show architecture and close:

The agent did not replace the adjuster.

It brought policy, business data and multimodal evidence together so the adjuster could focus judgment on the one part of the claim that actually required review.

---

# 79. Demo visual quality

The claims demo should look visually distinct from Contoso Air.

Use a claims-review workspace rather than a generic chatbot page.

Prioritize:

- claim summary
- evidence thumbnails
- repair estimate
- recommendation
- discrepancy
- sources

The chat/agent interaction can be present but should not dominate the entire screen.

---

# 80. Security and privacy

All data is synthetic.

Do not commit:

- credentials
- access tokens
- Azure resource-specific secrets
- real customer data
- real police reports
- real VINs
- real accident photographs with identifiable people/license plates
- private endpoints
- local paths

Use `.env.example`.

Ignore real `.env` and runtime state.

---

# 81. Provenance/disclosure

Clearly state:

- Contoso Insurance is fictional.
- All customers, claims, policies, vehicles and evidence are synthetic.
- Accident photographs are synthetic.
- The application is for demonstration.
- The sample does not connect to a real insurer.
- Recommendations are decision support, not automatic claim determinations.

---

# 82. Initial development phases

Use the disciplined staged approach that worked for Contoso Air.

## Phase 1: Claims data + evidence + Operations API

Build:

- repository scaffold
- deterministic structured data
- hero claim
- evidence documents
- synthetic photos
- Claims Operations API
- OpenAPI specification
- validation
- tests

Do NOT create the Foundry agent yet.

Stop for review.

## Phase 2: Knowledge + prompt agent

Build:

- policy/guidance documents
- File Search
- instructions
- code creation path
- Foundry UI creation path
- multimodal evidence integration
- hero run
- evaluations

Stop for review.

## Phase 3: Claims Review application

Build:

- lightweight claims workspace
- same Foundry agent
- evidence views
- hero interaction
- multi-turn evidence follow-up

Stop for review.

## Phase 4: Demo packaging

Build:

- five-minute script
- setup
- validation
- reset
- troubleshooting
- architecture visual
- screenshots/fallback
- final commit/tag

Do not skip review gates.

---

# 83. Phase 1 exact scope

GitHub Copilot should first implement only:

1. `contoso-claims-processing/` scaffold
2. deterministic structured claims dataset
3. CLM-10482 hero records
4. claim form
5. police report
6. repair estimate
7. synthetic hero photographs
8. evidence manifest
9. Claims Operations API
10. OpenAPI specification
11. tests
12. Phase 1 validation tooling
13. initial implementation spec saved in `docs/IMPLEMENTATION-SPEC.md`

Do NOT create the Foundry prompt agent in Phase 1.

Do NOT create File Search knowledge in Phase 1 unless needed only as placeholder structure.

Do NOT build the final web application.

---

# 84. Phase 1 validation report

At the end of Phase 1, STOP.

Return:

## Hero structured data

Exact relevant records for:

- Jordan Lee
- policy
- Trailstar vehicle
- CLM-10482
- customer claim history

## Hero evidence

Summarize/show:

- claim form
- police report
- repair estimate
- photographs
- manifest

## Estimate validation

Show:

- every repair line
- line amounts
- total
- intentional discrepancy
- verify the discrepancy is NOT explicitly labelled in source data

## Image validation

Provide thumbnails or appropriate inspection artifacts.

Verify:

- same vehicle
- consistent right-rear damage
- no explicit anomaly annotation
- no real personal data

## API

For every operation show:

- HTTP endpoint
- method
- operationId
- description
- parameters
- response schema
- hero request
- hero response

Confirm:

- no policy interpretation
- no anomaly detection
- no fraud score
- no recommendation
- no hero-specific code

## Data realism

Report:

- customers
- policies
- vehicles
- claims
- repair facilities
- claim statuses
- claim types
- coverage combinations
- historical claims

## Consistency

Run checks for:

- dangling references
- duplicates
- impossible dates
- policy/date relationships
- claim/vehicle relationships
- estimate arithmetic
- evidence existence
- deterministic generation

## Tests

Report:

- passed
- failed
- skipped
- warnings

## Secret/privacy scan

Report results.

## Phase 1 verdict

Finish exactly with:

**READY FOR CLAIMS PHASE 2**

or

**CLAIMS PHASE 1 CHANGES REQUIRED**

Do not begin Phase 2 automatically.

---

# 85. Phase 2 acceptance criteria

Phase 2 succeeds only when:

- prompt agent exists
- UI and code creation paths are documented
- knowledge is realistic and generic
- multimodal path is supported and documented
- hero images are actually analyzed
- structured business data is retrieved
- policy is retrieved
- headlamp line is identified from evidence reconciliation
- recommendation is manual review
- no fraud accusation
- no false claim decision
- no unsupported visual certainty
- hero explanation is grounded
- negative evaluation cases pass
- no hero answer leaks into instructions
- Phase 1 data/API remain unchanged unless correcting a real defect

---

# 86. Phase 3 acceptance criteria

Phase 3 succeeds only when:

- Claims Review UI invokes the same Foundry agent
- UI does not contain claims reasoning
- CLM-10482 loads correctly
- evidence is visually accessible
- hero prompt works
- evidence follow-up works
- relevant citations/sources are visible
- no duplicated recommendation logic
- multi-turn context works
- previous tests remain passing

---

# 87. Final promotion bar

The Claims Processing demo is complete only if:

- scenario is understandable in seconds
- hero result is grounded
- discrepancy is discoverable but not hard-coded
- image reasoning materially adds value
- policy/data/evidence sources are clearly separated
- agent avoids overclaiming
- adjuster remains final decision-maker
- Foundry configuration is visible
- UI and code creation paths exist
- custom Claims UI uses the same agent
- evaluations demonstrate generalization
- demo runs reliably in approximately five minutes
- repo is reproducible and shareable

---

# 88. Non-goals

Do NOT add:

- real insurance-system integration
- real customer data
- real police reports
- real claim photographs
- claim payment
- automated approval
- automated denial
- automated fraud determination
- formal SIU case creation
- payment calculations beyond demo facts
- OCR service unless platform needs it and the architecture change is explicitly approved
- external computer-vision service unless a verified Foundry limitation requires reconsideration
- multi-agent claims workflow
- voice
- telephony
- Teams implementation
- Microsoft 365 Copilot implementation
- production identity/authentication
- broad claims-management functionality

Keep the demo focused on:

**one claim → evidence investigation → one meaningful discrepancy → grounded manual-review recommendation.**

---

# 89. Final implementation principle

The most important rule is:

**Do not encode the answer in the data pipeline.**

The APIs provide facts.

The evidence provides observations.

The policies provide rules.

The Foundry agent performs the reasoning.

The adjuster makes the consequential decision.

That separation is the heart of the Contoso Claims Processing demo.
