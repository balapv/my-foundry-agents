# Cleanup

Nothing in this sample deletes Azure resources automatically. `scripts/reset_demo.py` resets local
state between presentations; it never touches Azure. Everything under **Optional Azure cleanup** is a
deliberate, manual step. Do it only when you're finished with the demo, and only for resources you
created for it.

## Local cleanup (safe)

| What | How | Notes |
|---|---|---|
| Application runtime state | Stop the server (Ctrl+C), then `python scripts/reset_demo.py` | Review sessions are in server memory only; stopping the server ends them. |
| Local logs | `reset_demo.py` removes `webapp/.logs/` when the app isn't running | Git-ignored. |
| Disposable results | `python scripts/reset_demo.py --results` removes `evaluation/results/` | Git-ignored smoke/evaluation output. |
| Test caches | `reset_demo.py` removes `.pytest_cache/` | |
| Virtual environment (optional) | `Remove-Item -Recurse -Force .venv` (macOS/Linux: `rm -rf .venv`) | Recreate with `scripts/setup.ps1` / `setup.sh`. |

Keep `.env`, `.foundry-state.json`, `agent/config.json` and `.deploy/` while you still want to present.
They're git-ignored and hold your environment's configuration and Foundry IDs.

## Optional Azure cleanup (deliberate, manual)

First list what's actually there, and confirm each item belongs to this demo:

```powershell
az resource list -g <your-resource-group> -o table
```

| Resource | Created by | Remove with |
|---|---|---|
| Agent `contoso-claims-review-agent` (all versions) **and** its guidance vector store and uploaded files | `agent/create_agent.py` | `python agent/create_agent.py --name contoso-claims-review-agent --delete` (deletes the vector store only if it was created for this agent, per `.foundry-state.json`) |
| Individual older agent versions | `create_agent.py` reruns | Foundry portal: agent, then **Versions**, then delete. **Don't delete the validated version 3.** |
| Claims Operations API Container App (`contoso-claims-tools` by default) | `scripts/deploy_tools.py` | `az containerapp delete -n <app> -g <rg>` |
| Container Apps environment | `az containerapp up` (via `deploy_tools.py`) | `az containerapp env delete -n <env> -g <rg>`, only if nothing else uses it |
| Container registry | `az containerapp up --source` | `az acr delete -n <registry> -g <rg>`, only if nothing else uses it |
| Log Analytics workspace | `az containerapp up` | `az monitor log-analytics workspace delete -n <ws> -g <rg>`, only if nothing else uses it |
| Resource group | `deploy_tools.py` (if it didn't exist) | `az group delete -n <rg>`, **only** if it was created solely for this demo |

Never delete:

- the Foundry project or its model deployment, unless you created them only for this demo;
- shared registries, environments or workspaces;
- anything you can't positively attribute to this sample.

Deleting the agent, its vector store or the Claims Operations API breaks the validated demo. Redeploying
means running `deploy_tools.py` and `create_agent.py` again, and re-running the evaluation and
readiness checks before presenting.
