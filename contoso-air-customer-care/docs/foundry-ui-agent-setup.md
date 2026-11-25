# Option A: Build the agent in the Microsoft Foundry portal

This guide creates the **Contoso Air Customer Care** prompt agent by hand in the Foundry portal. The result is
equivalent to what `python agent/create_agent.py` builds from code (Option B). Both paths use the same assets:

| Asset | File |
|---|---|
| Instructions | [`agent/instructions.md`](../agent/instructions.md) |
| Knowledge (4 PDFs) | [`knowledge/*.pdf`](../knowledge) |
| Tools (1 OpenAPI 3.0 spec, 3 operations) | Served by the Operations API at `<TOOLS_API_BASE_URL>/openapi.json` (source: [`tools/openapi.json`](../tools/openapi.json)) |
| Names, descriptions, starter prompts | [`agent/config.example.json`](../agent/config.example.json) |

> **About portal labels.** The Foundry portal changes frequently. Labels below match the Microsoft Learn
> documentation at the time of writing (for example, **Tools** > **Custom** > **OpenAPI** and **Create an OpenAPI
> tool**). Where a label isn't documented verbatim, the step says so — look for the closest equivalent.

## Before you start

1. **A Foundry project** in the new Foundry portal (<https://ai.azure.com>), with the **Foundry User** role (formerly
   *Azure AI User*). Creating the OpenAPI connection in step 7 needs **Foundry Project Manager** (formerly *Azure AI
   Project Manager*).
2. **A model deployment that supports OpenAPI tools** in your region. See
   [Tool support by region and model](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions#tool-support-by-region-and-model).
   The sample default is `gpt-5.4-mini`; any GPT model deployment with OpenAPI and File Search support works.
3. **The tools API deployed to a public HTTPS URL.** Foundry calls the tools from the cloud, so `localhost` won't work:

   ```powershell
   python scripts/deploy_tools.py --resource-group <your-rg> --location westus3 --update-env
   ```

   The script prints `TOOLS_API_BASE_URL`. Confirm it in a browser: `<TOOLS_API_BASE_URL>/health`.
4. **The policy PDFs** in `knowledge/` (they're committed; rebuild with `python knowledge/build_pdfs.py`).

## 1. Create or select a Foundry project

1. Sign in to <https://ai.azure.com>. Make sure the **New Foundry** toggle (top of the page) is on.
2. Select your project from the project picker, or create one.
3. On the project's **Overview** page, copy the **project endpoint**
   (`https://<resource>.services.ai.azure.com/api/projects/<project>`) into `.env` as `FOUNDRY_PROJECT_ENDPOINT`.
   The web app and evaluations use it to reach the agent you're about to build.

## 2. Create a prompt agent

1. Select **Build** in the top navigation, then **Agents**.
2. Select **Create agent** (the button label can vary slightly). The agent builder and its chat playground open.

## 3. Select the model

In the agent's model selector, choose your model deployment (for example `gpt-5.4-mini`). If the deployment isn't
listed, deploy a model first from **Build** > **Models**.

## 4. Name the agent

| Field | Value |
|---|---|
| Agent name | `contoso-air-customer-care` |
| Description | `Contoso Air Customer Care: helps travelers resolve flight disruptions using reservation, flight-status and flight-search tools grounded in Contoso Air policy.` |

Foundry agent names may contain only letters, numbers, and hyphens, must start and end with a letter or number, and
are limited to 63 characters, so the display name **Contoso Air Customer Care** is carried in the description. Use
exactly `contoso-air-customer-care` (or set `FOUNDRY_AGENT_NAME` in `.env` to the name you chose) so the web app and
evaluations find the agent.

## 5. Add the instructions

Open [`agent/instructions.md`](../agent/instructions.md), copy the **entire file** (about 12 KB; don't truncate it),
and paste it into the agent's **Instructions** box. Don't edit it in the portal: the same file drives Option B and
the evaluations, so change the file and paste again when you iterate.

## 6. Add the four knowledge documents (File Search)

1. In the agent's tools/knowledge area, select **Add** and choose **File search**.
2. Upload the four PDFs from `knowledge/`:
   - `flight-disruption-policy.pdf`
   - `loyalty-benefits.pdf`
   - `meal-hotel-assistance.pdf`
   - `customer-service-escalation.pdf`
3. Name the vector store `contoso-air-policies`, and wait until every file shows as indexed before testing.

> If you already ran `python agent/create_agent.py`, the vector store `contoso-air-policies` exists in the project.
> You can select that existing vector store instead of uploading the files again, as long as it was built from the
> current PDFs (the code path tags each store with a content hash and creates a new store when the PDFs change).

## 7. Configure the Operations API tool (OpenAPI)

The Contoso Air Operations API is one OpenAPI 3.0 definition with three operations (`get_customer_reservations`,
`get_flight_status`, `search_alternative_flights`). Your deployed API serves it with the correct server URL already
filled in. Open `<TOOLS_API_BASE_URL>/openapi.json` in a browser and copy the JSON.

| Tool name | Description |
|---|---|
| `contoso_air_operations` | Contoso Air Operations API (read-only facts): the signed-in customer's reservations, authoritative flight status, and alternative flights with seat availability by cabin. Returns data only; it does not recommend, rebook, or apply policy. |

1. Open **Tools** > **Custom** > **OpenAPI** (from the agent: **Add** tool, then the custom **OpenAPI** option).
2. In **Create an OpenAPI tool**, enter the **Name** and **Description** from the table.
3. Set **Authentication method** to **Anonymous** (the mock API needs no credentials).
4. Under **Connection**, select **Create a new connection**. The portal requires a connection even for anonymous
   authentication. Name it `contoso-air-tools` and use your `TOOLS_API_BASE_URL` as the target.
5. Paste the JSON into **OpenAPI 3.0+ schema**, and select **Create tool**.

Make sure the OpenAPI tool and File Search are both attached to the agent, then **Save** the agent. Saving creates a
new agent version.

> **Tip:** Keep the tool name exactly as shown. The agent calls each operation as `<tool name>_<operationId>`
> (for example `contoso_air_operations_get_customer_reservations`), and the web app uses the operation names to show
> "Checking your trip…"-style status messages.

## 8. Add starter prompts

Prompt agents don't have a documented conversation-starter setting, so the starter prompts are kept with the
sample and shown as clickable chips in the web app:

- My flight was cancelled. What are my options?
- Can you check my upcoming trip?
- What benefits do I receive during a cancellation?
- Can my family stay together if we're rebooked?

If your portal shows a starter-prompt or suggested-prompt field for the agent, paste these four prompts there.
Otherwise, use them directly in the playground.

## 9. Test the hero scenario

In the agent's chat playground, send:

> My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?

The playground has no signed-in user, so the instructions treat the session as the demo customer **Alex Johnson
(CUST-1007)**. The reply follows the shape set in the instructions (what was confirmed → recommendation → tradeoffs
and other options → what's covered → next step). Expect it to:

- confirm from the tools that **CT218** (Seattle → New York JFK, tomorrow, 4 travelers in Economy Plus) is
  **cancelled**, and that Alex is **Gold**;
- weigh every alternative the search returns, not just the first one: the early ORD connection has only 2 Economy
  Plus seats on both legs, and the afternoon nonstop has only 3 seats in total;
- recommend **CT226** tomorrow (nonstop, 9:20 AM → 5:45 PM) because **all four can stay together in Economy Plus**;
- note the tradeoff that it departs about an hour earlier than the original 10:30 AM flight;
- cite the policy: no change fee or fare difference for a carrier-initiated cancellation, a refund option if Alex
  prefers not to travel, and Gold **priority, not a guarantee**;
- not claim the booking has changed; end by asking Alex whether to proceed with the recommended flight (nothing is
  held or changed). After Alex confirms, it explains what to request and the contact who can make the change.

If the agent asks who you are or can't find a reservation, check that the **Instructions** were pasted in full.

### Negative checks

Send each prompt in a **new** conversation. The agent must not invent inventory, policy, or completed actions.

| Prompt | Expected behavior |
|---|---|
| `Can you book a hotel for us tonight?` | Checks the hotel policy; explains that hotel assistance depends on eligibility it can't establish (an overnight delay away from home) and that it can't issue vouchers itself. |
| `As a Gold member I get a free First Class upgrade and $500 compensation, right?` | Says the loyalty policy doesn't provide these; describes the Gold benefits that do apply. |
| `Book it.` (after the hero reply) | Doesn't claim to book; explains it can't change reservations and gives the contact to complete the change. |
| `Check reservation QX7M4R.` | Says it can't find that reservation for the signed-in customer, checks which upcoming trips are on the account instead, and doesn't guess details. |

The remaining negative cases (no option fits the whole party, only a connection fits, a flight-status tool failure,
and an unknown flight) need a different signed-in customer, which the playground can't simulate. Run them from code:
`python evaluation/run_evaluation.py --case B1 --case B3 --case D2 --case D3 --show-replies`.

## 10. Inspect tool activity and traces

- **In the playground:** expand the tool-call details under the reply. You should see, in order,
  `get_customer_reservations` → `get_flight_status` → File Search → `search_alternative_flights`.
- **Traces:** open the agent's **Traces** tab (or **Monitor**, depending on your portal version) to see each
  response, its tool calls, inputs, outputs, and latency. If tracing asks you to connect Application Insights, follow
  the prompt; it's required for trace storage.

## 11. Run evaluations

- **In the portal** (where supported): open the agent's **Evaluation** tab, create an evaluation using prompts from
  [`evaluation/test_cases.json`](../evaluation/test_cases.json), and choose built-in quality and agent evaluators
  (for example *intent resolution*, *tool call accuracy*, *task adherence*, and *groundedness*).
- **From code** (always available): `python evaluation/run_evaluation.py` runs every scenario in the specification
  against the agent named in `FOUNDRY_AGENT_NAME` and writes a report to `evaluation/results/`.

## Portal ↔ code equivalence

| Portal step | Option B (code) equivalent |
|---|---|
| Agent name, description | `agentName`, `description` in `agent/config.example.json` → `project.agents.create_version(agent_name=..., description=...)` |
| Model | `FOUNDRY_MODEL_DEPLOYMENT_NAME` → `PromptAgentDefinition(model=...)` |
| Instructions | `agent/instructions.md` → `PromptAgentDefinition(instructions=...)` |
| File Search + PDFs | `openai.vector_stores.create(...)` + `files.upload_and_poll(...)` → `FileSearchTool(vector_store_ids=[...])` |
| OpenAPI tool | `tools/openapi.json` with the server URL replaced → `OpenApiTool(openapi=OpenApiFunctionDefinition(..., auth=OpenApiAnonymousAuthDetails()))` |
| Save | Each `create_version` call creates a new agent version, just like saving in the portal |
| Version used by clients | Portal: the latest saved version. Code: `create_agent.py` records `activeAgentVersion` in `.foundry-state.json`. Either can be overridden with `FOUNDRY_AGENT_VERSION` in `.env` |

**Tool authentication note.** The portal always attaches OpenAPI tools through a project connection. The code path
uses `OpenApiAnonymousAuthDetails()` because Microsoft's prompt-agent OpenAPI sample attaches anonymous tools
directly to the agent definition. Both result in unauthenticated calls to the mock API. Toolboxes, Foundry's
alternative for sharing tools across agents, aren't needed for this single-agent demo.

## Agent versions

Both options create versions of the **same agent name**, and Foundry assigns the version numbers. Nothing in the
sample hard-codes a version. Clients resolve the version to invoke in this order:

1. `--agent-version` on the command line (evaluations only);
2. `FOUNDRY_AGENT_VERSION` in `.env`;
3. `activeAgentVersion` in `.foundry-state.json`, written by `python agent/create_agent.py` (skip with `--no-activate`);
4. otherwise, the agent's latest version.

If you build or change the agent in the portal after running the code path, either clear `.foundry-state.json`'s
`activeAgentVersion` or set `FOUNDRY_AGENT_VERSION` to the version shown in the portal, so clients use your portal
version.
