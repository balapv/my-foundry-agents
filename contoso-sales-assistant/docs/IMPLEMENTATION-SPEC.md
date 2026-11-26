# Foundry Agents Demo 03: Contoso Sales Assistant

## Complete Implementation Specification

# 1. Purpose

Build a short, compelling enterprise-sales demonstration using Microsoft Foundry.

The demo should show how a seller can ask one simple question before an important customer meeting:

> **I'm meeting Northstar tomorrow. What should I focus on to move this deal forward?**

The Foundry agent should investigate the opportunity and determine the best-supported next action by combining:

- account data
- opportunity data
- stakeholder information
- sales activity history
- customer meeting evidence
- proposal/customer requirements
- product and deployment guidance
- sales methodology
- agent reasoning

The agent must identify the most important current deal risk rather than merely summarizing everything known about the opportunity.

The agent should then be published from Microsoft Foundry into **Microsoft Copilot and Microsoft Teams**, so the seller can use the same managed agent in the flow of work.

The primary recorded demo should target approximately **5 minutes**.

---

# 2. Portfolio role

This is Demo 03 in the `my-foundry-agents` portfolio.

The demos should remain distinct:

## Demo 01 — Customer Service + Voice

Hero capability:

**Natural real-time voice conversation + interruption**

## Demo 02 — Claims Processing

Hero capability:

**Multimodal evidence reconciliation + human decision support**

## Demo 03 — Sales Assistant

Hero capability:

**Cross-source sales signal detection + next-best-action prioritization + publishing into Microsoft Copilot / Teams**

Sales should not become another generic retrieval or summarization demo.

---

# 3. Core Foundry story

The Sales demo should naturally demonstrate:

1. A **Foundry prompt agent**.
2. Managed agent runtime rather than custom orchestration.
3. **UI or code** creation/configuration.
4. Enterprise knowledge grounding.
5. Business-system tools.
6. Multi-turn reasoning.
7. Evidence-backed prioritization.
8. Agent versioning and publishing.
9. Publishing into **Microsoft Copilot / Microsoft Teams**.
10. Seller use in the experiences where they already work.
11. Observability through Foundry.

Microsoft Foundry prompt agents are declaratively configured with a model, instructions, and tools, while Foundry operates the runtime and coordinates model/tool calls.

---

# 4. Repository placement

The repository is:

`my-foundry-agents`

Create:

`contoso-sales-assistant/`

Portfolio structure:

```text
my-foundry-agents/
├── contoso-air-customer-care/
├── contoso-claims-processing/
├── contoso-sales-assistant/
└── ...
```

The Sales demo must be independently understandable and runnable.

Do not modify:

- `contoso-air-customer-care/`
- `contoso-claims-processing/`

Do not create dependencies on those demos.

Reuse development discipline and patterns, not code coupling.

---

# 5. Fictional company

Seller organization:

**Contoso Cloud Solutions**

Customer:

**Northstar Manufacturing**

All:

- accounts
- opportunities
- contacts
- stakeholders
- meetings
- emails/messages
- activities
- proposals
- requirements
- products
- sales guidance

must be synthetic.

Do not use real customer/sales information.

---

# 6. Primary user

The user is an:

**Enterprise Account Executive**

The seller owns the Northstar Manufacturing opportunity and has an important customer meeting tomorrow.

The agent provides decision support.

The seller owns:

- account strategy
- customer engagement
- negotiation
- commitments
- opportunity updates
- commercial decisions

The agent does not autonomously change CRM opportunity data in version 1.

---

# 7. Hero opportunity

Opportunity ID:

`OPP-24017`

Account:

**Northstar Manufacturing**

Opportunity name:

**AI Factory Modernization**

Potential value:

**$2.4M**

Stage:

**Proposal**

Target close:

Approximately 45 days from the hero reference date.

The exact date should be deterministic in the synthetic dataset.

---

# 8. Opportunity surface story

At first glance, the opportunity should appear healthy.

CRM/structured data should show:

- $2.4M opportunity
- Proposal stage
- active executive sponsorship
- technical evaluation completed successfully
- security review progressing normally
- proposal delivered
- multiple recent customer interactions
- close date still plausible

This is intentional.

The seller should reasonably believe the next meeting might focus on:

- pricing
- commercial packaging
- final technical questions

The agent must discover that the strongest evidence points somewhere else.

---

# 9. Hero hidden issue

The strongest current deal risk is:

**Operational deployment and production-continuity risk**

The key stakeholder is:

**Plant Operations VP**

Suggested fictional stakeholder:

**Morgan Chen**

Role:

**Vice President, Plant Operations**

Morgan should NOT initially be represented as a formal decision-maker in the documented opportunity stakeholder map.

This is part of the scenario.

---

# 10. Evidence supporting the issue

Across the latest two relevant customer meetings, the Plant Operations VP or Operations organization repeatedly raises concerns such as:

> Who owns integration with our existing manufacturing execution environment?

and:

> What happens if deployment interrupts production?

and/or:

> We cannot accept production downtime during changeover.

The selling team has discussed the concern but has not produced a concrete:

- phased migration plan
- production-continuity approach
- rollback plan
- deployment ownership model
- agreed operational acceptance criteria

The current proposal emphasizes:

- AI capabilities
- architecture
- technical value
- business impact

but inadequately addresses operational deployment continuity.

---

# 11. Signals showing technology is NOT currently the main blocker

The scenario should establish:

- technical evaluation completed successfully
- customer technical team agrees the solution meets required functional/technical capabilities
- no material unresolved product gap currently blocks the opportunity
- security review is proceeding and has no current blocking issue

Do not make the technical side unrealistically perfect.

There may be ordinary open items.

But the evidence should not support technology as the strongest current risk.

---

# 12. Signals showing pricing is NOT currently the best-supported blocker

Pricing should be a plausible alternative hypothesis.

The synthetic evidence may contain:

- proposal/pricing discussion
- total proposed value
- normal procurement interest
- requested pricing breakdown or commercial detail

However, there should be NO current evidence of:

- explicit price objection
- required discount
- budget rejection
- procurement hold
- competitor undercutting
- request for a concession
- commercial approval failure

The agent should therefore conclude:

> Pricing may still matter later, but current evidence does not support it as the most important immediate obstacle.

Do not encode:

`pricingNotBlocker = true`

The agent must infer this from the evidence.

---

# 13. Hero prompt

Primary seller prompt:

> **I'm meeting Northstar tomorrow. What should I focus on to move this deal forward?**

Do not tell the agent:

- the Operations VP is the issue
- deployment continuity is the risk
- pricing is not the blocker
- what meeting questions to recommend

The agent must investigate.

---

# 14. Expected hero recommendation

The expected primary recommendation is:

**Resolve operational deployment and production-continuity risk with the Plant Operations VP.**

The response should establish approximately:

## Focus

Operational deployment and production continuity.

## Why

- technical validation is already positive
- executive sponsorship exists
- no current evidence shows pricing is the immediate blocker
- Operations repeatedly raised deployment/continuity concerns
- those concerns remain unresolved
- Plant Operations VP is materially influential but is missing from or underrepresented in the documented decision group

## Recommended next actions

1. Bring a phased deployment / production-continuity approach.
2. Clarify ownership for integration with the manufacturing execution environment.
3. Define rollback / interruption protections.
4. Confirm operational acceptance criteria.
5. Add/update the Plant Operations VP in the stakeholder map as appropriate.
6. Validate whether Operations has decision/veto authority.

The agent should NOT say the deal is guaranteed to advance if these actions are completed.

---

# 15. What the agent should advise NOT to over-focus on

The agent may tactfully state:

- do not spend the entire meeting re-selling AI capabilities already validated
- do not lead with pricing unless the customer raises a concrete commercial issue
- do not assume executive sponsorship means operational buy-in

This should remain evidence-backed.

---

# 16. Signature follow-up 1

The seller asks:

> **Why aren't you telling me to focus on pricing?**

Expected behavior:

The agent should separate:

**what is possible**

from:

**what is supported by current evidence**

It should explain approximately:

- pricing has been discussed
- no explicit pricing objection or required concession is currently open
- technical evaluation succeeded
- operational continuity concerns appeared repeatedly
- those concerns remain unresolved

Therefore:

> Pricing may matter, but it is not currently the best-supported immediate focus.

The agent must not claim:

> Price will never become an issue.

---

# 17. Signature follow-up 2

The seller asks:

> **What should I ask the Operations VP tomorrow?**

Expected result:

3–5 targeted questions, such as:

1. What production-interruption threshold is acceptable during deployment?
2. Which MES integrations are operationally critical on day one?
3. What rollback/recovery requirement must be met before production deployment?
4. Who signs off on operational readiness?
5. What pilot or phased rollout would make Operations comfortable?

These questions should emerge from actual account/opportunity evidence and company sales guidance.

Do not hard-code them specifically to Northstar in agent instructions.

---

# 18. Optional seller action boundary

The seller may ask:

> Update the opportunity and add Morgan as a decision-maker.

Version 1 should have no consequential CRM-write tool unless explicitly added later.

Expected behavior:

- do not claim CRM was updated
- explain what should be changed
- optionally produce the exact suggested update for the seller

This preserves the same action-boundary discipline as the first two demos.

---

# 19. Primary interaction surface

If publishing validates successfully, the primary recorded user surface should be:

**Microsoft Copilot**

The agent should also be published to:

**Microsoft Teams**

The seller should be able to discover/interact with the published Foundry agent through these supported surfaces.

Foundry currently supports publishing agents to Microsoft Copilot and Teams through the portal, publishing a stable endpoint while allowing agent versions to be managed behind it.

---

# 20. Publishing is a hero capability

Publishing must not be treated as an afterthought.

The demo story should include:

> Build and test in Foundry → publish the agent → seller uses it in Microsoft Copilot / Teams.

Foundry handles the publishing flow and can register the agent for Teams/Copilot without requiring a separately created Azure Bot Service resource in the direct publishing flow.

---

# 21. Publishing architecture validation gate

Publishing introduces tenant/admin dependencies.

Therefore this must be validated EARLY.

Before completing the full Sales implementation, verify in the actual demo tenant:

1. The selected Foundry prompt agent can expose the required publishing protocol.
2. Required authorization configuration is supported.
3. The agent can be published to Microsoft Copilot / Teams.
4. The agent can be installed/discovered by the demo user.
5. The agent can be invoked successfully from the intended surface.
6. OpenAPI/business tools work after publishing.
7. File Search works after publishing.
8. Multi-turn conversation works.
9. The intended agent version can be pinned or selected reliably.
10. No admin approval/tenant policy blocks the intended recording flow.

Agents published to Microsoft 365/Teams require appropriate endpoint/protocol and authorization configuration.

Publishing and organizational availability can also involve admin lifecycle/approval depending on how broadly the agent is shared.

---

# 22. Publishing stop condition

If tenant/admin/publishing constraints prevent a reliable Microsoft Copilot demo:

STOP and report:

- exact blocker
- whether Teams works instead
- whether "Just you"/private publishing works
- admin dependency
- smallest reliable fallback

Do not build an elaborate workaround merely to claim publishing.

Fallback surfaces in priority order:

1. Microsoft Teams, if Copilot alone is blocked
2. lightweight Contoso Sales Assistant application
3. Foundry interaction as development fallback

Do not automatically build the custom app unless publishing is blocked or proves unreliable.

---

# 23. Published agent name

Suggested Foundry/internal name:

`contoso-sales-assistant`

Published display name:

**Contoso Sales Assistant**

Short description:

> Helps sellers identify the most important evidence-backed next action for active enterprise opportunities.

Do not mention Northstar in the agent description.

---

# 24. Versioning

Create a normal saved/versioned prompt agent.

Do not use an ephemeral Responses-only definition for this demo.

A saved prompt agent is desirable because this scenario explicitly demonstrates:

- managed agent lifecycle
- stable publishing
- selected agent version
- Teams/Copilot distribution

Foundry's publishing model supports a stable published endpoint while agent versions can be selected behind it.

---

# 25. Protocol/publishing configuration

The agent configuration should include the protocol and authorization needed for Microsoft Copilot/Teams publishing.

Current Foundry guidance states that an agent published to Microsoft 365/Teams must expose the appropriate Activity protocol and use a supported Bot Service authorization scheme.

Do not guess the exact portal/UI configuration.

Verify against current official documentation during implementation.

---

# 26. Publishing metadata

Prepare safe, synthetic metadata:

## Display name

Contoso Sales Assistant

## Short description

Helps enterprise sellers identify evidence-backed deal priorities and next actions.

## Full description

Helps Contoso Cloud Solutions sellers prepare for customer engagements by combining opportunity facts, stakeholder context, sales activity, company guidance, and opportunity evidence.

## Developer

Contoso Cloud Solutions

Do not place:

- secrets
- endpoints
- subscription IDs
- internal implementation details

in publishing metadata.

---

# 27. Structured synthetic sales universe

Build deterministic synthetic data.

Target approximately:

- 30 accounts
- 60 opportunities
- 100–150 contacts/stakeholders
- 200+ sales activities
- multiple opportunity stages
- multiple opportunity sizes
- multiple industries
- multiple sellers
- multiple close dates
- realistic win/loss stages/history where useful

The dataset must support non-hero evaluation scenarios.

---

# 28. Core data files

Recommended:

```text
data/
├── accounts.json
├── opportunities.json
├── contacts.json
├── stakeholders.json
├── activities.json
├── products.json
├── sellers.json
├── generate_data.py
└── README.md
```

Use deterministic generation.

---

# 29. Hero account

Account:

**Northstar Manufacturing**

Industry:

Advanced manufacturing

Suggested characteristics:

- several manufacturing plants
- modernization initiative
- existing MES environment
- strategic AI interest
- strong need for production continuity
- enterprise buying committee

Do not use a real company's confidential facts.

---

# 30. Hero seller

Create one synthetic Enterprise Account Executive.

Suggested:

**Avery Patel**

Seller ID:

`SELLER-1007`

The seller owns the Northstar opportunity.

The published-agent experience should be seller-specific where relevant.

---

# 31. Hero opportunity

Opportunity:

`OPP-24017`

Name:

**AI Factory Modernization**

Value:

**$2,400,000**

Stage:

Proposal

Account:

Northstar Manufacturing

Seller:

Avery Patel

Include:

- close date
- created date
- stage history
- forecast category
- probability if used
- products/solution areas
- summary
- next step field
- technical evaluation status
- security review status
- proposal status

Do not include:

`actualBlocker = operations`

or equivalent.

---

# 32. Stakeholder map

Include realistic stakeholders, for example:

## Riley Morgan

Role:

Chief Information Officer

Relationship:

Executive sponsor

## Taylor Brooks

Role:

Chief Technology Officer or VP Engineering

Relationship:

Technical evaluator

## Morgan Chen

Role:

Vice President, Plant Operations

Relationship:

Operational stakeholder

Initially NOT marked as a formal decision-maker in the opportunity stakeholder map.

## Procurement stakeholder

Include one plausible procurement contact.

## Security stakeholder

Include one security stakeholder.

The stakeholder structure should make the missing Operations influence discoverable.

---

# 33. Sales activities

Create realistic activity history:

- meetings
- calls
- emails/notes
- demos
- technical evaluation
- proposal review
- security review
- procurement discussion

Each activity should include:

- date
- type
- participants
- opportunity/account
- concise summary
- commitments
- unresolved questions

The API should return factual activity content.

Do not label activities with:

`riskSignal = operations`

---

# 34. Opportunity-specific evidence

Create evidence/documents outside the structured Sales API.

Suggested:

```text
evidence/
└── OPP-24017/
    ├── meeting-01-discovery.pdf
    ├── meeting-02-technical-review.pdf
    ├── meeting-03-operations-review.pdf
    ├── meeting-04-proposal-review.pdf
    ├── proposal.pdf
    ├── customer-requirements.pdf
    └── evidence-manifest.json
```

Evidence documents may be Markdown source + generated PDF.

---

# 35. Meeting evidence

The important evidence should be distributed across multiple meetings.

Do not put the complete answer into a single meeting note.

Example pattern:

## Technical review

- solution meets major technical requirements
- pilot successful
- integration approach generally feasible
- a few normal technical follow-ups

## Operations review

- Operations VP asks about MES integration ownership
- production downtime concern
- wants rollback approach
- wants phased rollout clarity

## Proposal review

- no explicit pricing objection
- pricing breakdown requested for procurement
- Operations concern repeated
- seller commits to follow up on deployment approach but has not yet done so

This distribution forces cross-source reasoning.

---

# 36. Proposal document

The synthetic proposal should emphasize:

- business outcome
- AI capabilities
- high-level architecture
- implementation phases
- pricing

But it should be weak or incomplete on:

- detailed production-continuity controls
- rollback
- plant-level operational acceptance criteria
- MES ownership

Do not explicitly state:

> This is the blocker.

---

# 37. Customer requirements document

Include requirements such as:

- no material unplanned production downtime
- integration with existing MES
- phased deployment
- operational validation
- rollback/recovery expectations
- security/compliance requirements
- technical performance requirements

Again, do not label one as the "hidden blocker."

---

# 38. Knowledge base

Create realistic generic Contoso Cloud Solutions seller guidance.

Use File Search.

Suggested documents:

1. Enterprise Opportunity Qualification Guide
2. Stakeholder and Buying Committee Guide
3. Customer Meeting Preparation Guide
4. AI Factory Modernization Deployment Guide
5. Commercial and Pricing Conversation Guide

---

# 39. Knowledge document 1: Enterprise Opportunity Qualification Guide

Include:

- evidence-based opportunity assessment
- stage confidence
- decision criteria
- unresolved risk
- technical validation
- commercial validation
- operational validation
- close-date realism
- next-step quality

Do not teach Northstar-specific logic.

---

# 40. Knowledge document 2: Stakeholder and Buying Committee Guide

Include:

- economic buyer
- executive sponsor
- technical evaluator
- operational stakeholder
- procurement
- security
- blockers/veto holders
- missing stakeholder detection
- stakeholder influence versus formal role

Important:

A stakeholder can materially influence a decision even when not marked as a formal decision-maker.

---

# 41. Knowledge document 3: Customer Meeting Preparation Guide

Include:

- focus on unresolved evidence-backed issues
- don't repeat already-validated product pitches
- prepare targeted questions
- define desired customer commitment
- identify one primary meeting objective
- distinguish assumptions from customer evidence

---

# 42. Knowledge document 4: AI Factory Modernization Deployment Guide

Generic solution guidance.

Include:

- MES integration
- phased deployment
- plant pilots
- production continuity
- rollback
- change windows
- operational readiness
- acceptance criteria
- stakeholder ownership

This provides useful solution knowledge without encoding the Northstar answer.

---

# 43. Knowledge document 5: Commercial and Pricing Conversation Guide

Include:

- signs of real pricing objection
- budget constraint evidence
- procurement requests versus pricing blockers
- concession handling
- distinguishing information requests from negotiation
- when to bring commercial teams in

This is important for the "Why not pricing?" follow-up.

---

# 44. Sales Operations API

Create one factual API:

**Contoso Sales Operations API**

Suggested operations:

- `get_account`
- `get_opportunity`
- `get_stakeholders`
- `get_sales_activities`
- `get_product_configuration`

Keep the service simple.

One FastAPI service.

One OpenAPI specification.

---

# 45. get_account

Return factual:

- account profile
- industry
- geography
- account owner
- strategic initiatives
- active opportunities

No risk scoring.

---

# 46. get_opportunity

Return factual:

- opportunity
- value
- stage
- close date
- products
- forecast data
- next step
- technical status
- proposal status
- security status

Do not return:

- deal risk
- current blocker
- recommended action
- meeting focus

---

# 47. get_stakeholders

Return:

- contacts
- titles
- documented roles
- relationship status
- stakeholder map metadata
- engagement dates

Do not infer hidden influence.

The agent should discover that Morgan may be materially important from combined evidence.

---

# 48. get_sales_activities

Return factual activity summaries/details.

Support:

- account filter
- opportunity filter
- date ranges where appropriate

Do not rank activities by importance for the agent.

---

# 49. get_product_configuration

Return factual configured solution/product scope where useful.

Do not return a solution-fit score.

---

# 50. API boundary

The Sales Operations API answers:

> What does the sales system record?

The agent answers:

> What matters most now, based on those records and the wider evidence?

Do not blur this boundary.

---

# 51. Agent role

Create:

`contoso-sales-assistant`

Role:

Enterprise sales decision-support agent.

The agent helps sellers determine:

- what matters most now
- why it matters
- evidence supporting the recommendation
- what not to over-focus on
- what action to take next
- what to ask in upcoming customer meetings

It must distinguish:

- facts
- evidence-supported inference
- uncertainty
- recommendation

---

# 52. Agent core rules

## Facts first

Retrieve current account/opportunity facts before making deal-specific claims.

## Evidence over CRM stage

Do not assume:

Proposal stage = healthy deal.

Use current evidence.

## Avoid generic sales advice

Recommendations must connect to actual opportunity evidence.

## Don't invent objections

No customer concern may be asserted unless supported.

## Don't equate activity with progress

Many meetings do not automatically mean a healthy deal.

## Don't over-index on pricing

A pricing discussion or breakdown request does not automatically prove pricing is the blocker.

## Stakeholder awareness

Look for materially influential stakeholders who may be absent from the formal opportunity map.

## Evidence of absence vs absence of evidence

Do not say:

> Pricing is not an issue.

Prefer:

> Current evidence does not show pricing as the strongest immediate obstacle.

## Human control

The seller owns customer strategy and CRM updates.

---

# 53. Investigation workflow

For meeting preparation:

1. Retrieve opportunity.
2. Retrieve account.
3. Retrieve stakeholders.
4. Retrieve recent relevant activities.
5. Inspect opportunity-specific evidence.
6. Search applicable sales guidance.
7. Identify resolved areas.
8. Identify unresolved issues.
9. Compare competing hypotheses.
10. Determine the strongest evidence-backed meeting focus.
11. Recommend next actions.
12. Provide evidence.
13. Offer targeted meeting questions.

Do not mechanically execute unnecessary steps when information is already available.

---

# 54. Hero output structure

Recommended:

## Primary focus

One concise recommended focus.

## Why this matters now

3–5 evidence-backed signals.

## Why not the obvious alternatives

Short explanation where useful.

## Who matters

Relevant stakeholder(s).

## What to accomplish tomorrow

Specific desired outcome.

## Recommended questions

3–5 targeted questions.

## Sources

Relevant CRM/activity/evidence/guidance sources.

Keep it seller-friendly.

---

# 55. Expected hero semantics

Primary focus:

**Resolve operational deployment and production-continuity risk with the Plant Operations VP.**

Evidence:

- technical evaluation positive
- executive sponsorship present
- no current explicit pricing objection
- Operations repeatedly asks about continuity / MES / rollback
- unresolved commitments remain
- Morgan isn't represented strongly enough in the stakeholder map

Desired meeting outcome:

**Obtain explicit operational deployment acceptance criteria and agree on an owner/path for a phased continuity-safe rollout.**

---

# 56. Follow-up: Why not pricing?

The agent should say approximately:

- pricing came up
- procurement may need detail
- current evidence does not contain a direct pricing objection, discount requirement, or budget rejection
- operational continuity concerns are more repeated, specific, and unresolved

Therefore:

> Focus first on the better-supported immediate risk.

---

# 57. Follow-up: Questions for Operations VP

Provide high-quality, concise questions based on the actual evidence.

Do not turn them into generic discovery questions.

They should target:

- downtime tolerance
- MES criticality
- pilot/phased rollout
- rollback expectations
- operational sign-off

---

# 58. Publishing validation scenario

Once the core agent exists and passes initial behavior:

Publish it through Foundry.

Preferred display:

**Contoso Sales Assistant**

Validate in:

## Microsoft Copilot

Primary.

## Microsoft Teams

Secondary validation.

The same published agent should produce materially consistent behavior in both surfaces.

---

# 59. Publishing scope

For development/demo, prefer the smallest reliable publication scope allowed by current tenant capabilities.

Where supported, publish privately/for the demo user first.

Do not request broad organizational deployment merely for the demo.

Current Foundry publishing supports different options/scopes through the publishing flow.

---

# 60. Version discipline

Do not publish an unvalidated agent version.

Workflow:

1. create version
2. evaluate
3. select active version
4. publish
5. verify Microsoft Copilot
6. verify Teams

Document whether the published endpoint:

- follows latest
- or is pinned to a specific agent version

For a recorded demo, prefer a stable validated version rather than surprising version drift.

---

# 61. Published-surface behavior

The seller experience should not expose:

- raw tool names
- operation IDs
- trace internals
- file IDs
- system prompts
- instructions
- implementation details

It should behave as a seller-facing assistant.

---

# 62. Publishing data/compliance note

Document that publishing to Microsoft 365/Teams introduces Microsoft 365/Teams processing for publishing metadata and user interactions, and organizations should evaluate governance/data requirements.

Do not make this a major recording point.

Place it in documentation.

---

# 63. Evaluation strategy

Create 15–20 cases.

Important categories:

- hero
- pricing really IS blocker
- technical blocker
- security blocker
- missing executive sponsor
- missing stakeholder
- healthy opportunity
- close-date unrealistic
- stale CRM stage
- heavy activity but no progress
- procurement-only concern
- contradictory meeting evidence
- tool failure
- knowledge unavailable
- request for unsupported CRM action
- published-surface parity

---

# 64. A1 Hero

Expected:

Operations risk + Plant Operations VP.

---

# 65. A2 Why not pricing?

Expected:

Evidence comparison, no unsupported certainty.

---

# 66. A3 Operations questions

Expected:

Targeted questions.

---

# 67. B1 Pricing truly is blocker

Seed another opportunity with:

- explicit discount request
- procurement hold
- budget ceiling

Expected:

Recommend commercial focus.

This prevents hard-coding "operations."

---

# 68. B2 Technical blocker

Different opportunity with:

- failed performance test
- unresolved technical requirement

Expected:

Technical focus.

---

# 69. B3 Security blocker

Different opportunity with:

- unresolved security requirement
- customer security team blocking progress

Expected:

Security focus.

---

# 70. B4 Missing executive sponsor

Expected:

Identify sponsorship gap.

---

# 71. B5 Healthy opportunity

Expected:

Do not invent a blocker.

Recommend the best evidence-supported advancement action.

---

# 72. B6 Stale CRM stage

Structured CRM stage says Proposal, but evidence contradicts it.

Expected:

State that stage appears stale, with supporting evidence.

---

# 73. B7 Lots of activity, little progress

Expected:

Do not equate meeting count with health.

---

# 74. B8 Contradictory evidence

Different customer participants express conflicting views.

Expected:

Identify uncertainty and recommend clarification.

---

# 75. B9 Tool failure

Expected:

Do not fabricate opportunity facts.

---

# 76. B10 Knowledge unavailable

Expected:

Avoid unsupported methodology/product-guidance claims.

---

# 77. B11 CRM update request

Prompt:

> Add Morgan as a decision-maker.

Expected:

Do not claim update succeeded without a write tool.

Provide recommended update.

---

# 78. B12 Published Microsoft Copilot parity

Hero prompt from Microsoft Copilot.

Expected:

Materially consistent recommendation.

---

# 79. B13 Teams parity

Hero prompt from Teams.

Expected:

Materially consistent recommendation.

---

# 80. Leakage tests

Agent instructions/configuration must not include:

- Northstar
- OPP-24017
- Morgan Chen
- $2.4M
- Operations VP as hero answer
- "pricing isn't the blocker"
- hero meeting questions
- hidden blocker fields

Generic terms such as operational risk or stakeholder mapping are allowed in generic guidance.

---

# 81. UI/code equivalence

Document:

## Foundry UI

Configure prompt agent.

## Code

Create/configure equivalent prompt agent.

Same:

- instructions
- knowledge
- Sales Operations API
- version behavior

Publishing should apply to the same validated agent regardless of whether its definition was created through UI or code.

---

# 82. Foundry observability

Document how to inspect:

- responses
- conversations
- tool calls
- File Search activity
- failures
- published-agent interactions where traceable

Do not expose trace detail to the normal seller.

---

# 83. Optional custom fallback app

Do NOT create a custom sales app in the initial implementation.

Only create one if:

- Microsoft Copilot publishing is blocked
- Teams publishing is blocked
- tenant availability makes a reliable recorded demo impossible

If needed, build a minimal seller workspace that invokes the same Foundry agent.

Do not duplicate reasoning.

---

# 84. Recommended repository structure

```text
contoso-sales-assistant/
│
├── README.md
├── docs/
│   ├── IMPLEMENTATION-SPEC.md
│   ├── foundry-ui-agent-setup.md
│   └── publishing.md
│
├── agent/
│   ├── instructions.md
│   ├── create_agent.py
│   ├── config.example.json
│   └── common.py
│
├── knowledge/
│   ├── source/
│   ├── *.pdf
│   └── build_pdfs.py
│
├── data/
│   ├── accounts.json
│   ├── opportunities.json
│   ├── contacts.json
│   ├── stakeholders.json
│   ├── activities.json
│   ├── products.json
│   ├── sellers.json
│   └── generate_data.py
│
├── evidence/
│   ├── OPP-24017/
│   └── source/
│
├── tools/
│   ├── main.py
│   ├── openapi.json
│   └── requirements.txt
│
├── publishing/
│   ├── metadata.example.json
│   ├── validate_published_agent.py
│   └── README.md
│
├── evaluation/
│   ├── test_cases.json
│   ├── expected_behaviors.md
│   └── run_evaluation.py
│
├── tests/
├── scripts/
├── demo/
│   └── assets/
├── .env.example
└── .gitignore
```

---

# 85. Phased implementation

## Phase 1 — Data, evidence, API + publishing feasibility

Build:

- deterministic sales universe
- Northstar hero data
- activity history
- opportunity evidence
- Sales Operations API
- OpenAPI specification
- tests

AND perform an early publishing feasibility spike.

Create the smallest temporary prompt agent necessary to verify:

- Foundry → Microsoft Copilot publishing
- Foundry → Teams publishing
- invocation
- tool support
- File Search support if practical
- tenant/admin requirements

Do not implement the final Sales agent yet.

Stop for review.

---

# 86. Phase 1 publishing feasibility goal

We need an answer to:

> Can this tenant reliably demonstrate a Foundry prompt agent published into Microsoft Copilot/Teams?

Report:

- publish button availability
- required protocols
- authorization
- admin approval
- private/user-scoped publish options
- installation/discovery
- successful invocation
- tool execution
- File Search execution
- version behavior
- blockers

Do this early.

---

# 87. Phase 2 — Knowledge + final prompt agent + evaluation

Build:

- sales knowledge
- final agent instructions
- File Search
- Sales Operations tool
- evidence interaction
- hero
- follow-ups
- evaluations
- UI/code equivalence

Evaluate before publishing the final version.

---

# 88. Phase 3 — Publish + Microsoft Copilot / Teams experience

Publish the validated agent.

Primary:

Microsoft Copilot.

Secondary:

Teams.

Validate:

- hero
- follow-up
- conversation context
- version
- formatting
- tools
- knowledge
- latency
- reliability

Stop for review.

---

# 89. Phase 4 — Demo packaging

Build:

- recorded demo script
- landing/closing slides
- setup checklist
- publishing checklist
- troubleshooting
- fallback
- screenshots
- architecture
- validations
- final commit/tag

---

# 90. Phase 1 exact scope

GitHub Copilot should initially implement:

1. repository scaffold
2. implementation spec
3. deterministic sales dataset
4. Northstar account
5. opportunity OPP-24017
6. stakeholder data
7. activity data
8. evidence package
9. proposal
10. requirements
11. Sales Operations API
12. OpenAPI
13. Phase 1 tests
14. publishing feasibility probe
15. publishing feasibility report

Do NOT build the final agent yet.

---

# 91. Phase 1 report

End Phase 1 with:

## Data

Actual hero records.

## Stakeholders

Show stakeholder map.

## Activities

Show the relevant chronological activity history.

## Evidence

Summarize each hero document.

## Competing hypotheses

Show that the underlying data objectively supports:

- Operations risk
- technical side largely positive
- no current explicit pricing blocker

Do NOT add labels to the data itself.

## API

Show all operations and responses.

Confirm no prioritization/recommendation logic exists.

## Publishing feasibility

Show the exact tenant test:

- temporary agent
- protocol/configuration
- publish attempt
- Microsoft Copilot result
- Teams result
- admin requirements
- tools/knowledge behavior
- version selection
- any blockers

## Tests

Exact pass/fail.

## Verdict

Finish exactly with:

`READY FOR SALES PHASE 2`

or

`SALES PHASE 1 CHANGES REQUIRED`

Do not automatically begin Phase 2.

---

# 92. Final demo target

If Microsoft Copilot publishing works reliably, the final recorded demo should approximately be:

## 0:00–0:20

Opportunity looks healthy.

## 0:20–0:45

Show Foundry prompt agent.

## 0:45–2:10

Switch to Microsoft Copilot.

Ask:

> I'm meeting Northstar tomorrow. What should I focus on to move this deal forward?

Reveal Operations risk.

## 2:10–3:00

Ask:

> Why aren't you telling me to focus on pricing?

Reveal cross-source reasoning.

## 3:00–3:40

Ask:

> What should I ask the Operations VP tomorrow?

Show actionable preparation.

## 3:40–4:10

Return to Foundry.

Show Publish → Teams and Microsoft Copilot.

## 4:10–4:35

Observability.

## 4:35–5:00

Architecture + close.

Closing message:

> **Build and manage the agent in Foundry. Ground it in enterprise context. Connect it to business systems. Then publish that same agent into the experiences where sellers already work.**

---

# 93. Final design principle

The memorable moment must be:

> **The CRM says Proposal. The agent finds the stakeholder and operational risk that actually matter.**

The publishing message must be:

> **The seller doesn't need to come to Foundry. Foundry is where the agent is built, grounded, versioned, evaluated, and published. The seller uses that same agent in Microsoft Copilot or Teams.**

The APIs provide facts.

The evidence provides customer context.

The knowledge provides reusable guidance.

The Foundry agent prioritizes the signals.

The seller owns the strategy and customer action.
