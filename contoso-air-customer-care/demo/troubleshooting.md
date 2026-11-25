# Troubleshooting

This guide is built for fast recovery during a live demo. Start with `python scripts\validate_demo.py`: it checks
every layer and prints a fix for anything that fails. During a presentation, **don't debug on stage**. Switch to
the fallback in [demo-script.md](demo-script.md#latency-and-fallback) and investigate afterwards.

The web app's error messages include a short reference, such as `Reference: 1a2b3c4d`. Find it in the web
server's terminal: the log line `Agent turn failed [ref=… category=…]` names the cause: `authentication`,
`timeout`, `busy`, `foundry_unavailable`, `configuration` or `agent_response_failed`.

## Foundry authentication failure

- **Symptoms:** `validate_demo.py` fails at **Sign-in and project**. The web app shows "the Travel Assistant is
  unavailable" and its log has `category=authentication`.
- **Likely cause:** the Azure CLI token has expired, or you're signed in to the wrong tenant or subscription.
- **Recovery:** run `az login` (add `--tenant <tenant>` if your account spans tenants), then
  `az account set --subscription <name>`. Restart the web server so it picks up the new credential, then rerun
  `python scripts\validate_demo.py`. A *forbidden* error means your account needs the **Foundry User** role on the
  project.

## Agent/version mismatch

- **Symptoms:** `validate_demo.py` fails at **Agent version**, or warns that the **Instructions** don't match
  `agent/instructions.md`. `/api/health` reports a version you didn't expect.
- **Check:** `validate_demo.py` prints the configured version and where it came from: `FOUNDRY_AGENT_VERSION`, then
  `.foundry-state.json`, then the latest version.
- **Recovery:** set `FOUNDRY_AGENT_VERSION=<version>` in `.env` to pin the validated version, then restart the web
  server. Don't create a new version right before presenting. If you saved changes in the portal, the latest
  version changed: pin the version you validated.

## Operations API unavailable

- **Symptoms:** `validate_demo.py` fails at **Operations API → Health**. The agent says it can't reach the
  reservation or flight system.
- **Check:** open `<TOOLS_API_BASE_URL>/health` in a browser. Then check the logs with
  `az containerapp logs show --name <app> --resource-group <rg> --tail 50`.
- **Recovery:** redeploy (this takes a few minutes and keeps the same URL):
  `python scripts\deploy_tools.py --resource-group <rg>`. If the URL changed, update `TOOLS_API_BASE_URL`. The
  agent's OpenAPI tool also points at that URL, so a changed URL needs a new agent version: update the tool's
  server URL in the portal, or run `create_agent.py`. Do this before the demo, not during it.

## Knowledge/vector store issue

- **Symptoms:** `validate_demo.py` fails or warns at **Knowledge** or **Knowledge content**. The agent answers
  policy questions vaguely or without citing a policy.
- **Check:** `python knowledge\build_pdfs.py --check` confirms the local PDFs. `validate_demo.py` confirms that the
  agent's vector store holds 4 completed files and that its content hash matches the local PDFs.
- **Recovery:** if the store is still indexing, wait and rerun the check. Only if the policy sources really
  changed, run `python agent\create_agent.py --refresh-knowledge`. That creates a new vector store **and a new agent
  version**, so do it well before presenting and rerun `validate_demo.py --hero`.

## 429/throttling

- **Symptoms:** the web app shows "The Travel Assistant is very busy right now…" (`category=busy`), or the
  playground reports a rate limit.
- **Recommended behavior:** don't resend straight away; rapid retries make throttling worse. Switch to the
  prepared web conversation or the fallback transcript and continue the story. If time allows, retry once after
  about a minute.
- **Afterwards:** check the model deployment's tokens-per-minute quota in the Foundry portal, and avoid running
  evaluations just before you present.

## Slow hero response

- **Normal:** 24–44 s in validation runs. Keep narrating (see the demo script).
- **Abnormal:** more than 90 s. Move to the fallback; don't wait for the web app's 180-second timeout.
- **Before the demo:** if `validate_demo.py --hero` is consistently slow, check the model deployment's load and
  quota.

## Web session expired

- **Symptoms:** "Your chat session expired, so we started a new conversation." Conversations are held in the web
  server's memory, so restarting the server clears them.
- **Recovery:** the page has already started a new session; resend the message. To start over deliberately, reload
  the page. `python scripts\reset_demo.py` checks that everything is ready again. The prepared conversation is
  lost when the server restarts; use the fallback transcript for the 3:45 segment.

## Web app cannot reach Foundry

1. Is the server terminal showing errors? Look for `category=` with the reference shown in the browser.
2. Open `http://localhost:8080/api/health`. It shows the agent name and version the server resolved.
3. Run `python scripts\validate_demo.py`. The **Configuration** and **Foundry agent** sections show what's wrong.
4. `authentication` → see Foundry authentication failure above. `foundry_unavailable` → check the network or VPN,
   and check `FOUNDRY_PROJECT_ENDPOINT` in `.env`.
5. After fixing `.env` or signing in again, restart the server:
   `python -m uvicorn server:app --app-dir webapp/backend --port 8080`.

## Unexpected agent answer

- **On stage:** don't tune the prompt or edit the instructions live, and don't resend the same prompt hoping for a
  better answer. Say "Let me show you a validated run of the same request," then move to the prepared web
  conversation or [fallback-transcript.md](fallback-transcript.md).
- **Afterwards:** save the conversation, check its tool calls in **Traces**, and run
  `python evaluation\run_evaluation.py --no-judge` to see whether the behavior reproduces. Compare the result with
  the validated version before you change anything.
