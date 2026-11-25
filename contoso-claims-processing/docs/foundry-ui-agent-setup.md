# Create the Contoso Claims Review agent in the Foundry portal

This guide builds the same prompt agent that `agent/create_agent.py` builds in code: the same instructions, model, knowledge and Claims Operations API tool. Differences between the two paths are listed at the end.

> Portal labels change often. The steps follow the Microsoft Foundry documentation as verified for Phase 2. If a label differs, look for the equivalent control.

## Prerequisites

| Requirement | Notes |
|---|---|
| A Microsoft Foundry project | You need **Foundry User** to create and run agents and **Foundry Project Manager** to create the OpenAPI connection. |
| A deployment of the model | Use the same model as the code path (`FOUNDRY_MODEL_DEPLOYMENT_NAME`). Phase 2 was validated with **gpt-6.1-sol**, a multimodal model that accepts PDF and image input. |
| The Claims Operations API, deployed at a public `https://` URL | Foundry calls the API from the cloud, so `localhost` does not work. `python scripts/deploy_tools.py` deploys it to Azure Container Apps and prints the URL. |
| This repository | You need four files from it: `agent/instructions.md`, `tools/openapi.json` and the four PDFs in `knowledge/`. |

## 1. Create the agent

1. Open the project in the [Foundry portal](https://ai.azure.com), go to **Agents**, and create a new agent.
2. Name it `contoso-claims-review-agent`, or any name. Pass that name to `run_claim_review.py --agent` later.
3. Select the model deployment.
4. Paste the **entire** contents of `agent/instructions.md` into **Instructions**. Do not shorten or edit it; the code path uses the file verbatim.

## 2. Add the company guidance (File Search)

1. Under **Tools** (or **Knowledge**), add **File search**.
2. Create a new vector store, for example `contoso-insurance-claims-guidance`, and upload exactly these four files:
   - `knowledge/claims-handling-guidelines.pdf`
   - `knowledge/auto-coverage-guidance.pdf`
   - `knowledge/repair-estimate-review.pdf`
   - `knowledge/claims-escalation-guidance.pdf`
3. Wait until all four files show as processed.

**Upload nothing else.** In particular, never upload any of these:

- claim evidence (`evidence/CLM-*`)
- build provenance (`evidence/source/**`, including `photos.json`, which holds image-generation prompts)
- `docs/IMPLEMENTATION-SPEC.md`
- anything under `evaluation/`

Claim evidence is supplied per conversation; see step 5.

## 3. Add the Claims Operations API (OpenAPI tool)

1. Make an editable copy of `tools/openapi.json` and set its `servers` entry to the deployed API:

   ```json
   "servers": [{ "url": "https://<your-claims-operations-api>", "description": "Claims Operations API" }]
   ```

   Change nothing else. The code path makes the same single substitution (`common.openapi_spec`).

2. Go to **Tools** > **Custom** > **OpenAPI** and create the tool:

   | Field | Value |
   |---|---|
   | Name | `claims_operations` |
   | Description | `Contoso Insurance Claims Operations API: factual claim, policy, claim-history and vehicle records.` |
   | Authentication method | **Anonymous** |
   | Connection | Select **Create a new connection**: an OpenAPI connection with no authentication (`authType: None`) whose target is the API URL. The portal requires a connection even for anonymous APIs. |
   | OpenAPI 3.0+ schema | Paste the edited copy of the spec |

3. Confirm that the tool lists four operations: `get_claim`, `get_policy`, `get_customer_claim_history` and `get_vehicle`.
4. Attach the tool to the agent and save. Saving creates an agent version.

The tool name must be `claims_operations`. The instructions refer to it by that name.

## 4. Check the setup in the playground

In the agent playground, ask a question that needs only the API and the guidance, for example:

> What is the status and deductible for claim CLM-10439's policy, and what does Contoso guidance say about deductibles?

You should see `claims_operations_get_claim` and `claims_operations_get_policy` calls and a File Search call that cites the coverage guidance.

## 5. Review a claim with its evidence

A claim review attaches that claim's evidence package to the first message of a conversation. The package is the claim form, police report and estimate PDFs plus the photographs, listed in `evidence/<claim>/evidence-manifest.json` and verified by hash. The playground documentation does not describe attaching images or PDFs to an agent message, so use the repository runner against the portal-created agent:

```powershell
python agent/run_claim_review.py --agent contoso-claims-review-agent --claim CLM-10482 `
    --follow-up "Show me why you flagged the headlamp."
```

Without `--version`, the runner uses the agent's latest version, which is the one the portal just saved. Both turns run in one Foundry conversation, so the follow-up keeps the attached evidence and the earlier tool results. To run the evaluation suite against the portal agent, set `"agentName"` in a local `agent/config.json`, which is git-ignored.

The Contoso Claims Review application ([webapp/README.md](../webapp/README.md)) uses the same runtime path. To point it at the portal-created agent, set `FOUNDRY_AGENT_NAME` (and optionally `FOUNDRY_AGENT_VERSION`) in `.env`.

## Equivalence with the code path

| Aspect | Portal (this guide) | Code (`agent/create_agent.py`) | Effect |
|---|---|---|---|
| Instructions | `agent/instructions.md`, pasted | `agent/instructions.md`, read verbatim | Same |
| Model | Selected deployment | `FOUNDRY_MODEL_DEPLOYMENT_NAME` | Same if the same deployment is chosen |
| Knowledge | The four PDFs in one vector store | The same four PDFs in one vector store (reused while unchanged) | Same |
| File Search result count | Portal default | `max_num_results = 8` (`config.example.json`) | Minor. Set the same value if the portal exposes it. |
| OpenAPI spec | `tools/openapi.json` with `servers` replaced | Same substitution | Same |
| OpenAPI authentication | Anonymous, through a project connection with `authType: None` (required by the portal) | `OpenApiAnonymousAuthDetails()` attached directly to the prompt agent, as in the documented Python prompt-agent sample; no connection | Both call the API without credentials. Validated live for the code path only. |
| Claim evidence | Attached per conversation by `run_claim_review.py --agent <name>` | Same runner | Same; the playground is not used for evidence |
| Agent metadata | None | `instructions_sha256`, `knowledge`, `demo` tags | Informational only |

## Clean up

Delete the agent, its vector store and the OpenAPI connection in the portal. Agents created in code are deleted with `python agent/create_agent.py --name <agent> --delete`.
