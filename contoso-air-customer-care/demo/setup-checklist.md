# Setup checklist

Use this 15–30 minutes before presenting. Commands are PowerShell, run from the `contoso-air-customer-care` folder.
On macOS/Linux, use `./scripts/setup.sh` and `.venv/bin/python`.

## Environment

- [ ] Correct repository and branch checked out.
- [ ] `.\scripts\setup.ps1 -SkipInstall` reports **DEMO READY**. This checks the virtual environment, packages,
      `.env` and the Azure CLI sign-in.
- [ ] `az account show --query name -o tsv` shows the subscription that holds the Foundry project.
      If it doesn't: `az login`, then `az account set --subscription <name>`.

## Services

`python scripts\validate_demo.py` checks all of these:

- [ ] Operations API healthy.
- [ ] Foundry project reachable.
- [ ] Configured agent version exists, with matching instructions, tool and server URL.
- [ ] Knowledge: 4 documents indexed and matching `knowledge/*.pdf`.
- [ ] Web backend starts and the frontend is served.

## Validation

- [ ] `python scripts\validate_demo.py --hero` reports **DEMO READY** (one live hero turn, about 25–45 s).
- [ ] Start the web app and leave it running:
      `python -m uvicorn server:app --app-dir webapp/backend --port 8080`
- [ ] In `http://localhost:8080`, send the hero prompt, then **Why is that better than the connection?** Both
      answers arrive. Keep this tab open: it's the prepared conversation for 3:45. Don't restart the server.

## Browser preparation

- [ ] Foundry portal: the agent page for `contoso-air-customer-care`. You know where **Model**, **Instructions**,
      **Knowledge** and **Tools** are.
- [ ] Foundry playground: a **new chat**, with no history.
- [ ] The **Traces** (or **Monitor**) tab opens and shows recent runs.
- [ ] Web app tab with the prepared conversation.
- [ ] Architecture visual: [architecture.md](architecture.md) or [assets/architecture.svg](assets/architecture.svg).
- [ ] Code view open at `agent/create_agent.py`, with `agent/foundry_common.py` (`build_agent_definition`) nearby.

## Presentation

- [ ] Hero prompt copied:
      `My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure out what to do?`
- [ ] Browser zoom about 125%, so code and replies are readable.
- [ ] Unneeded tabs closed. Nothing on screen shows subscription IDs, keys or endpoints (`.env` closed).
- [ ] Notifications off (Windows: **Do not disturb**).
- [ ] Terminal cleared (`Clear-Host`). The web server can run in a minimized window.
- [ ] Fallback open in a background tab: [fallback-transcript.md](fallback-transcript.md) and
      [assets/hero-completed.png](assets/hero-completed.png).
- [ ] [demo-script.md](demo-script.md) and [troubleshooting.md](troubleshooting.md) to hand.
