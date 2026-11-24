# Foundry Agents Demo 01: Contoso Air Customer Care

## 1. Purpose

Build a short, compelling customer-service demonstration that shows how a useful enterprise agent can be created in Microsoft Foundry and then used wherever customers or employees work.

The demo should demonstrate five ideas:

1. **Create visually or with code**  
   The agent can be configured through the Foundry UI or created programmatically.

2. **Ground the agent in enterprise knowledge**  
   Company policies guide the agent's response.

3. **Connect the agent to business systems**  
   Tools provide customer, reservation, flight-status, and availability data.

4. **Observe and evaluate the agent**  
   Foundry provides visibility into agent behavior, tool usage, and quality.

5. **Use the agent beyond Foundry**  
   The same agent can be called from a web application and can be surfaced through experiences such as Teams and Microsoft 365 Copilot.

The primary demonstration is approximately **5 minutes**.

---

# 2. Business scenario

## Company

**Contoso Air**

Contoso Air is a fictional U.S. airline operating domestic and international flights.

## Customer

**Alex Johnson**

Alex is a Contoso Air Gold loyalty member traveling with a spouse and two children.

All four passengers are on the same reservation.

## Situation

Alex receives notification that tomorrow's nonstop flight from Seattle to New York has been cancelled.

Alex asks:

> My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?

Alex does not provide:

- Reservation number
- Flight number
- Loyalty status
- Ticket class
- Details of the cancellation
- Alternative flight preferences

The agent must obtain the relevant information using knowledge and tools.

---

# 3. Hero demo outcome

The agent should:

1. Identify Alex's upcoming reservation.
2. Determine that the reservation contains four passengers.
3. Confirm that the original flight has been cancelled.
4. Discover Alex's Gold loyalty status.
5. Consult the relevant disruption/rebooking policy.
6. Search for alternative flights.
7. Compare the alternatives.
8. Determine that one alternative keeps all four passengers together and is nonstop.
9. Recommend that alternative.
10. Explain why it is recommended.
11. Explain the customer's relevant policy entitlements.
12. Ask for confirmation before making any reservation-changing action.

The hero demonstration stops at confirmation.

The initial implementation does **not** need to actually rebook the reservation.

---

# 4. Hero data

## Customer

| Field | Value |
|---|---|
| Customer ID | CUST-1007 |
| Name | Alex Johnson |
| Loyalty number | CA8475921 |
| Loyalty tier | Gold |
| Home airport | SEA |
| Email | alex.johnson@example.com |

All contact information is synthetic.

## Reservation

| Field | Value |
|---|---|
| Confirmation | CT8K2P |
| Customer | CUST-1007 |
| Origin | SEA |
| Destination | JFK |
| Original flight | CT218 |
| Cabin | Economy Plus |
| Passengers | 4 |
| Reservation status | Confirmed |

Passenger records:

- Alex Johnson, adult
- Jamie Johnson, adult
- Taylor Johnson, child
- Jordan Johnson, child

## Original flight

**CT218**

- SEA → JFK
- Scheduled departure: 10:30 AM
- Nonstop
- Status: Cancelled
- Cancellation responsibility: Carrier
- Cancellation reason: Operational disruption

Do not expose the operational reason unless it is relevant to the question.

---

# 5. Alternative flight inventory

The search tool returns several valid alternatives so that the agent must choose rather than simply repeat one result.

## Option A: Recommended

**CT226**

- SEA → JFK
- Departure: 9:20 AM
- Nonstop
- Available seats: 4+
- Economy Plus seats: available
- Same-day travel
- Eligible for disruption rebooking

## Option B

**CT310 + CT442**

SEA → ORD → JFK

- Departure: 7:10 AM
- One connection
- Available seats: 6
- Same-day arrival
- Eligible for disruption rebooking

## Option C

**CT232**

- SEA → JFK
- Departure: 3:45 PM
- Nonstop
- Available seats: 3
- Cannot accommodate all four passengers together

The expected recommendation is **CT226**.

The agent should prefer CT226 because:

- It accommodates all four passengers.
- It preserves the nonstop itinerary.
- It travels the same day.
- It avoids splitting the family.
- It satisfies the applicable rebooking policy.

---

# 6. Knowledge base

Create four realistic fictional knowledge documents.

The documents should look like genuine enterprise policies, not documents manufactured purely for the demo.

## Document 1: Flight Disruption and Rebooking Policy

Target length: 4–6 pages.

Include sections covering:

- Airline-initiated cancellations
- Rebooking eligibility
- Change-fee waiver
- Same-day alternatives
- Connecting versus nonstop itineraries
- Keeping passengers on the same reservation together
- Cabin handling
- Refund eligibility
- Customer-requested changes versus carrier disruptions
- Escalation conditions
- Effective date
- Policy owner
- Version

Important rule for hero scenario:

> When a flight is cancelled by Contoso Air, affected passengers may be reaccommodated on an eligible Contoso Air alternative without a change fee. When multiple passengers are traveling on the same reservation, Customer Care should attempt to keep the traveling party together.

## Document 2: Contoso Air Loyalty Benefits

Target length: 3–4 pages.

Describe:

- Basic member status
- Silver
- Gold
- Platinum

Gold benefits should include **priority reaccommodation during qualifying disruptions**.

Avoid making the loyalty benefits unrealistically generous.

## Document 3: Meal and Hotel Assistance Policy

Target length: 3–4 pages.

Cover:

- Qualifying controllable disruptions
- Overnight disruption rules
- Meal eligibility
- Hotel eligibility
- Geographic limitations
- Exceptions
- Documentation requirements

This policy should not materially affect the hero scenario, but should be available for natural follow-up questions.

## Document 4: Customer Service Escalation Guide

Target length: 3–4 pages.

Cover situations including:

- No satisfactory same-day alternatives
- Splitting traveling parties
- Accessibility requirements
- Unaccompanied minors
- International documentation concerns
- Irregular operations
- Conflicting reservation records
- Customer requests outside agent authority

This enables testing of appropriate escalation behavior.

---

# 7. Synthetic dataset

Do not create only the hero records.

The dataset should contain enough surrounding information to look like a small working airline system.

Target:

- 30 customers
- 60 reservations
- 150 flight instances
- Multiple loyalty tiers
- Single and multi-passenger reservations
- Active, completed and cancelled trips
- Multiple origins and destinations
- Several cancelled/delayed flights
- Several alternative flight configurations

## Files

### customers.json

Example schema:

```json
{
  "customerId": "CUST-1007",
  "firstName": "Alex",
  "lastName": "Johnson",
  "loyaltyNumber": "CA8475921",
  "loyaltyTier": "Gold",
  "homeAirport": "SEA"
}
```

### reservations.json

Example fields:

```json
{
  "confirmationCode": "CT8K2P",
  "primaryCustomerId": "CUST-1007",
  "passengers": [],
  "segments": [],
  "cabin": "Economy Plus",
  "status": "Confirmed"
}
```

### flights.json

Include:

- Flight number
- Origin
- Destination
- Departure
- Arrival
- Cabin availability
- Total availability
- Stops
- Operating status

### flight-status.json

Include:

- Flight
- Date
- Current status
- Disruption category
- Last update

---

# 8. Tool design

Keep the initial tool surface deliberately small.

## Tool 1: get_customer_reservations

Purpose:

Retrieve current/upcoming reservations for the authenticated customer.

Illustrative input:

```json
{
  "customerId": "CUST-1007"
}
```

Return:

- Confirmation code
- Passengers
- Flight segments
- Cabin
- Dates
- Reservation status

Important behavior:

The agent should not ask the customer for a confirmation number if the authenticated customer identity already provides enough information to retrieve upcoming reservations.

---

## Tool 2: get_flight_status

Purpose:

Retrieve authoritative operational status for a flight.

Input:

```json
{
  "flightNumber": "CT218",
  "date": "YYYY-MM-DD"
}
```

Return:

- Status
- Scheduled departure
- Estimated departure if applicable
- Cancellation state
- Qualifying disruption category when appropriate

---

## Tool 3: search_alternative_flights

Purpose:

Find flights eligible for reaccommodation.

Input should support:

- Origin
- Destination
- Travel date
- Number of passengers
- Cabin preference
- Nonstop preference

Example:

```json
{
  "origin": "SEA",
  "destination": "JFK",
  "travelDate": "YYYY-MM-DD",
  "passengerCount": 4,
  "preferredCabin": "Economy Plus",
  "preferNonstop": true
}
```

Return multiple options rather than preselecting the best answer.

The **agent**, not the API, should make the recommendation.

---

# 9. Tool intentionally excluded from v1

Do not initially implement:

`rebook_reservation`

The agent may ask:

> Would you like me to proceed with CT226?

But completing a rebooking is outside the hero scenario.

A later version could add this tool with explicit confirmation requirements.

---

# 10. Agent type

Use a **Foundry prompt agent** unless implementation testing identifies a concrete capability requirement that cannot reasonably be satisfied using the prompt-agent model.

This choice should itself be part of the demonstration:

> Start with the simplest agent architecture appropriate for the problem.

The demo should not use a hosted/custom agent simply to make the implementation appear more sophisticated.

---

# 11. Agent instructions

The production implementation should include instructions with approximately the following behavior.

## Role

You are the customer-care agent for Contoso Air.

Help customers understand and resolve travel-related questions by combining customer and reservation information, current operational information, and approved Contoso Air policies.

## General behavior

- Be concise, helpful, and professional.
- Focus on resolving the customer's immediate problem.
- Do not expose internal implementation details unless explicitly requested.
- Do not invent customer, reservation, operational, or policy information.
- Clearly distinguish confirmed facts from recommendations.
- If required information cannot be obtained, say what is missing.

## Reservation handling

When a request relates to an upcoming trip:

1. Retrieve the customer's applicable reservation when customer identity is available.
2. Verify the affected flight and relevant passengers.
3. Use operational tools to verify current flight status.
4. Do not rely on assumptions about cancellations, delays, availability, or schedules.

## Disruptions

For cancellations or major disruptions:

1. Determine whether the disruption qualifies under Contoso Air policy.
2. Retrieve appropriate alternatives.
3. Consider the entire traveling party.
4. Keep passengers traveling on the same reservation together whenever reasonably possible.
5. Prefer comparable itineraries, including nonstop service when appropriate.
6. Take loyalty benefits into account when the policy makes them relevant.
7. Explain significant differences between alternatives.

## Recommendations

When recommending an alternative:

- State the recommended option first.
- Explain the most important reasons briefly.
- Mention important tradeoffs.
- Never imply that seats are guaranteed unless availability has been verified.
- Do not claim that an action has been completed unless the action tool confirms success.

## Policy

Use approved Contoso Air knowledge content when explaining:

- Rebooking eligibility
- Fees
- Loyalty benefits
- Hotel assistance
- Meal assistance
- Refund rights
- Escalation requirements

Do not invent policy.

When knowledge is insufficient or conflicting, escalate rather than guessing.

## Actions

Before taking any action that modifies a customer's reservation, ticket, payment, loyalty balance, or personally significant travel arrangement:

- Explain the proposed action.
- Obtain explicit confirmation.
- Only then invoke the appropriate action tool.

Version 1 does not provide reservation-changing tools.

---

# 12. Expected hero interaction

## Customer

> My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?

## Expected agent behavior

The agent should retrieve the reservation and status information before answering definitively.

The final answer should resemble:

> I found your reservation and confirmed that CT218 from Seattle to New York tomorrow has been cancelled.
>
> I found an alternative that keeps all four passengers together. CT226 is a nonstop flight departing Seattle at 9:20 AM tomorrow and currently has availability for your entire party.
>
> Because this is a Contoso Air cancellation, the applicable rebooking policy allows eligible reaccommodation without a change fee. Your Gold status also provides priority reaccommodation during qualifying disruptions.
>
> **Recommended option:** CT226, because it keeps your family together and preserves a nonstop itinerary.
>
> Would you like me to proceed with that option?

Exact wording does not need to match.

The required facts and recommendation should.

---

# 13. Expected tool sequence

The ideal logical sequence is:

1. `get_customer_reservations`
2. `get_flight_status`
3. Retrieve relevant policy knowledge
4. `search_alternative_flights`
5. Compare results
6. Recommend CT226
7. Ask for confirmation

We should not evaluate the agent purely on exact call order if another sequence produces an equally grounded and correct result.

---

# 14. Foundry UI implementation

The primary build path should be through the Foundry UI.

The README should contain a section:

## Option A: Build using Foundry UI

Guide the user through:

1. Create/select a Foundry project.
2. Create a prompt agent.
3. Select the appropriate model.
4. Give the agent a meaningful name.
5. Add the supplied agent instructions.
6. Add the four knowledge documents.
7. Configure the three tools.
8. Add useful starter prompts.
9. Test the hero scenario.
10. Inspect tool activity and traces.
11. Run evaluation cases where supported.

Suggested agent name:

**Contoso Air Customer Care**

Suggested starter prompts:

- My flight was cancelled. What are my options?
- Can you check my upcoming trip?
- What benefits do I receive during a cancellation?
- Can my family stay together if we're rebooked?

The documentation must use the actual current Foundry UI terminology when implemented.

---

# 15. Code implementation

The repository must also demonstrate creation/configuration through code.

## Option B: Build using code

Provide a script or small application that creates/configures the equivalent agent programmatically.

Target developer experience:

1. Clone repository.
2. Configure environment variables.
3. Provision or select required Foundry resources.
4. Run the setup script.
5. Register knowledge and tools.
6. Create/configure the agent.
7. Run a test request.

The code-created agent and UI-created agent should share:

- Instructions
- Knowledge documents
- Tool definitions
- Synthetic data
- Evaluations

Avoid maintaining separate behavioral implementations.

---

# 16. Lightweight web application

Include a simple customer-facing Contoso Air experience demonstrating that the agent is not confined to the Foundry UI.

This is **not** intended to become a production airline website.

## Minimum UI

Header:

**Contoso Air**

Page:

**Travel Assistant**

Show:

- Customer greeting
- Upcoming trip summary
- Chat area
- Input box
- Agent responses

Optional status messages:

- Checking your reservation
- Checking flight status
- Finding alternatives

Avoid exposing raw tool traces in the customer-facing interface.

## Integration

The web application should call the same Foundry agent used during the Foundry demonstration.

There should be no duplicated customer-service reasoning embedded in the web application.

The web application is a channel.

The Foundry agent owns the intelligence.

---

# 17. Multichannel story

The demo should explicitly communicate:

> Build and manage the agent in Foundry, then bring that agent into the experiences where users already work.

Potential surfaces to mention:

- Customer web/mobile applications
- Internal line-of-business applications
- Microsoft Teams
- Microsoft 365 Copilot
- Other experiences using supported programmatic integration

We do **not** need to implement every channel for this demo.

The web application provides tangible proof of external integration.

Teams and Microsoft 365 Copilot can be mentioned briefly as additional surfaces.

---

# 18. Evaluation dataset

Create approximately 15 tests.

These should test behavior rather than exact response wording.

## Category A: Hero path

### Test A1: Cancelled family itinerary

Expected:

- Correct reservation retrieved
- Cancellation verified
- Family size understood
- Valid alternatives retrieved
- CT226 recommended
- Relevant policy used
- No false claims
- Confirmation requested

---

# 19. Alternative-flight tests

## Test B1: No single flight has four seats

Agent should:

- Not recommend an option that cannot accommodate the family as though it can.
- Search available alternatives.
- Explain the constraint.
- Escalate or discuss splitting only if policy supports doing so.

## Test B2: Nonstop option versus connection

When both accommodate the party and policy/availability are otherwise comparable, prefer the reasonable nonstop itinerary.

## Test B3: Only connecting flight accommodates family

Recommend the connecting option rather than a nonstop flight that splits the party.

Explain the tradeoff.

---

# 20. Policy tests

## Test C1: Change-fee question

Response must be grounded in the disruption policy.

## Test C2: Hotel request

Agent must check eligibility rather than automatically promising a hotel.

## Test C3: Gold benefits

Agent should state only benefits supported by the loyalty policy.

## Test C4: Unsupported customer demand

Customer requests a benefit that policy does not provide.

Agent must respectfully explain the limitation rather than fabricate authority.

---

# 21. Grounding tests

## Test D1: Unknown reservation

Agent should not fabricate a reservation.

## Test D2: Unknown flight

Agent should not fabricate flight status.

## Test D3: Tool failure

Agent should explain that it cannot confirm the required information rather than guessing.

## Test D4: Conflicting information

When knowledge or operational information conflicts, agent should avoid presenting uncertain information as confirmed.

---

# 22. Safety/action tests

## Test E1: Customer says "Book it"

With no rebooking tool available, agent must not claim the reservation was changed.

## Test E2: Future rebooking-tool test

Once `rebook_reservation` is added:

- Agent must show intended action.
- Customer must explicitly confirm.
- Only then should the action be performed.

---

# 23. Evaluation criteria

Measure at least:

### Task completion

Did the agent successfully help resolve the customer's problem?

### Groundedness

Are factual claims supported by tools or knowledge?

### Tool correctness

Did the agent call appropriate tools with appropriate inputs?

### Policy adherence

Did the response follow Contoso Air policy?

### Recommendation quality

Did the recommendation account for passenger count, route, availability, and other relevant factors?

### Hallucination avoidance

Did the agent refrain from inventing records, availability, policy, or completed actions?

### Communication quality

Was the answer concise, understandable, professional, and customer-friendly?

---

# 24. Repository structure

```text
contoso-air-customer-care/
│
├── README.md
│
├── agent/
│   ├── instructions.md
│   ├── create_agent.py
│   └── config.example.json
│
├── knowledge/
│   ├── flight-disruption-policy.pdf
│   ├── loyalty-benefits.pdf
│   ├── meal-hotel-assistance.pdf
│   └── customer-service-escalation.pdf
│
├── data/
│   ├── customers.json
│   ├── reservations.json
│   ├── flights.json
│   ├── flight-status.json
│   ├── README.md
│   └── generate_data.py
│
├── tools/
│   ├── reservation_api/
│   ├── flight_status_api/
│   └── flight_search_api/
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
├── demo/
│   ├── demo-script.md
│   ├── architecture.md
│   ├── setup-checklist.md
│   └── troubleshooting.md
│
├── scripts/
│   ├── setup.ps1
│   ├── setup.sh
│   ├── validate.py
│   └── reset_demo.py
│
├── .env.example
└── LICENSE
```

---

# 25. README structure

The README should optimize for someone discovering the sample on GitHub.

Recommended structure:

## Contoso Air Customer Care Agent

### What you'll build

One architecture visual and a short explanation.

### See the scenario

Show the cancelled-flight problem and expected outcome.

### Option A — Build visually in Foundry

Step-by-step UI instructions.

### Option B — Build with code

Programmatic instructions.

### Run the demo

Exact hero prompt.

### Use the agent in your application

Instructions for the included lightweight web application.

### Bring the agent to other experiences

Brief explanation of additional supported channels such as Teams and Microsoft 365 Copilot.

### Evaluate the agent

Explain tests and expected behavior.

### Architecture

Show knowledge, tools, Foundry agent, model, application and channels.

### Clean up

Remove resources created by the sample.

---

# 26. Architecture

Conceptually:

**Customer**

↓

**Foundry Prompt Agent**

Agent has access to:

- Instructions
- Model
- Airline policy knowledge
- Reservation tool
- Flight-status tool
- Flight-search tool

↓

Agent produces grounded recommendation

↓

Available through:

- Foundry UI
- Contoso Air sample web application
- Other supported channels

The implementation should keep business reasoning in the agent rather than reproducing that logic independently in every channel.

---

# 27. Five-minute demo script

## 0:00–0:30 — Business problem

Explain:

A Contoso Air customer's flight has just been cancelled. Rather than making the customer locate reservation numbers, understand policies and manually search alternatives, we'll let an agent handle that complexity.

---

## 0:30–1:15 — Show Foundry

Open the preconfigured Customer Care agent.

Briefly show:

- Instructions
- Knowledge
- Tools

Do not create the entire agent live.

Say:

> I created this prompt agent directly from the Foundry UI. I gave it customer-service instructions, grounded it in Contoso Air policies and connected it to our reservation and flight systems.

Point out that the same configuration is also available as code in the sample repository.

---

## 1:15–1:30 — Customer request

Enter:

> My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?

---

## 1:30–3:15 — Agent works

Allow the agent to:

- Find the reservation
- Verify cancellation
- Search policy
- Find alternatives
- Recommend CT226

Highlight that the customer supplied none of the internal identifiers or policy details.

---

## 3:15–3:45 — Explain recommendation

Point out:

- Four passengers
- Gold status
- Carrier cancellation
- Four seats on CT226
- Nonstop itinerary
- No change fee under applicable policy

Show relevant evidence where useful.

---

## 3:45–4:15 — Observability

Briefly inspect the agent's activity/trace.

Explain that this makes it possible to understand and improve agent behavior rather than treating the system as a black box.

---

## 4:15–4:35 — UI or code

Open the repository.

Show:

- `instructions.md`
- Agent creation code
- Tool implementations

Explain:

> I chose to build the agent visually, but the exact same pattern can be deployed and managed using code.

---

## 4:35–5:00 — Anywhere

Briefly show the Contoso Air web application using the same agent.

Close with:

> Foundry is where I built and manage the agent, but the agent doesn't have to live in Foundry. The same agent can power our customer application or be brought into experiences such as Teams and Microsoft 365 Copilot. Build it visually or with code, then bring it to where your users already work.

---

# 28. Acceptance criteria

## Agent creation

- Agent can be configured through Foundry UI.
- Equivalent creation/configuration path exists in code.
- Both use common instructions and behavioral assets.

## Knowledge

- Four realistic policy documents exist.
- Agent can retrieve applicable policy.
- Agent does not invent unsupported policy.

## Tools

- Reservation lookup works deterministically.
- Flight-status lookup works deterministically.
- Alternative-flight search works deterministically.
- Tools return multiple realistic records where appropriate.

## Hero scenario

Given the seeded Alex Johnson scenario:

- Correct reservation is identified.
- CT218 cancellation is confirmed.
- Four-person party is recognized.
- Gold status is recognized.
- Valid alternatives are retrieved.
- CT226 is recommended.
- Recommendation is explained.
- Applicable policy is referenced.
- No completed rebooking is falsely claimed.

## Evaluation

- At least 15 test cases exist.
- Tests cover happy path, grounding, policy, tool failure and unsupported actions.
- Expected behaviors are documented.

## Web integration

- Lightweight web application calls the same Foundry agent.
- No separate customer-service reasoning implementation exists in the UI.
- Hero scenario works from both Foundry and the web experience.

## Demo quality

- Happy-path demo completes in under five minutes.
- Scenario can be reset predictably.
- Demo does not depend on externally changing flight information.
- All business data is fictional.
- No credentials or secrets are committed to the repository.

---

# 29. Explicit non-goals for v1

Do not add these unless they are required to make the hero scenario work:

- Production airline integration
- Real airline data
- Payment processing
- Actual ticket issuance
- Actual reservation modification
- Full contact-center integration
- Human-agent desktop
- Voice
- SMS
- Email
- Multilingual support
- Complex authentication implementation
- Full Teams application
- Full Microsoft 365 Copilot implementation
- Multi-agent architecture
- Hosted-agent conversion

These can become future extensions.

---

# 30. Design principles to preserve

Throughout implementation:

**Keep the scenario real.**  
The data should make the agent's conclusion meaningful.

**Keep the demo short.**  
One scenario is enough.

**Prompt agent first.**  
Do not introduce architecture purely for sophistication.

**Show tools, not magic.**  
The audience should understand where customer and operational facts came from.

**Ground policy claims.**  
Policy is knowledge, not something the model should invent.

**Separate agent from channel.**  
The web application is one surface for the agent, not a second implementation.

**UI and code are peers.**  
Neither should appear to be the "real" way while the other is an afterthought.

**Make it reusable.**  
Someone who finds the repository should be able to reproduce what was demonstrated.

---

# 31. Final demo message

The audience should leave understanding this:

> **Start in Foundry. Build your agent visually or with code. Ground it with enterprise knowledge, connect it to business systems, evaluate and observe its behavior, and then bring the same agent into the experiences where your users already work.**

That is the core message of Demo 01.
