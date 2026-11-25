# Troubleshooting during a live demo

**Rule: one quick fix, then use the fallback.** Don't debug on stage. The fallback is
[fallback-transcript.md](fallback-transcript.md) plus the screenshots in [assets/](assets/). Each is a
*validated previous run*; say so.

Transition line:
> "Live model calls sometimes slow down. Here's the same review from a validated previous run."

All commands run from `contoso-claims-processing/` in PowerShell (`$py = ".\.venv\Scripts\python.exe"`).

| Symptom | One quick fix | Then |
|---|---|---|
| **Foundry authentication failure** (card: "could not complete this request" or "not configured correctly"; readiness "Azure sign-in" fails) | Off-screen: `az login` (correct tenant), then `az account set --subscription <id>`. Restart the app server. | Fallback screenshots and transcript. |
| **Agent/version mismatch** (About this workspace shows a version other than 3; readiness says the version isn't the baseline) | Set `FOUNDRY_AGENT_VERSION=3` in `.env` and restart the server. Confirm version 3 on the Foundry agent page. **Never create or publish a new version on stage.** | If version 3 isn't in Foundry, use the fallback and repair afterwards. |
| **Claims Operations API unavailable** (answer says records couldn't be retrieved; readiness check "Claims API" fails) | Off-screen: `curl <TOOLS_API_BASE_URL>/health`. Make sure `CLAIMS_API_SIMULATE_OUTAGE` is empty. If the Container App was scaled to zero, the first call may take about 30 s. | Fallback. Optionally note: "the agent tells you what it couldn't verify instead of guessing." |
| **Evidence hash mismatch** (card: "evidence package for this claim could not be verified"; readiness "baseline" fails) | **Don't bypass it.** It means evidence files differ from the validated package. | Fallback now. Afterwards: `git status`/`git diff evidence/` and restore with `git checkout -- evidence/`. |
| **Initial review is slow** | Normal is **42–58 s**. Keep narrating the status line (see the [demo script](demo-script.md)). After 60 s the app shows "This is taking longer than usual. The agent is still working"; that's expected. | **Keep waiting up to about 75 s.** After that, or on any error card, switch to the fallback. |
| **Rate limiting** (card: "The review agent could not complete this request. Please try again." with a `CR-…` reference; the log shows the rate limit) | **Don't retry repeatedly.** At most one retry, and only if you're ahead of time. | Fallback: `04-hero-recommendation.png`, then `05-…png` for the evidence moment. |
| **Follow-up fails or is slow** (over about 30 s) | None on stage. | `05-headlamp-evidence-comparison.png`, or turn 2 of the transcript. |
| **Source link fails** | Open the item directly from the **evidence panel** (left side): repair estimate, police report, photographs. | Continue narrating. |
| **Unexpected answer** (wrong emphasis, missing headlamp point) | **Don't edit instructions or publish a new agent version on stage.** Don't rerun hoping for different wording. | "Here's the validated run": use the transcript and screenshots. Investigate afterwards. |
| **Application server or session failure** (page won't load; "review no longer available") | Press **New review**. If the page is dead: stop the server (Ctrl+C), run `& $py scripts\reset_demo.py --offline`, then restart `& $py -m uvicorn webapp.backend.app:create_app --factory --port 8010` and reload. | If it isn't back within about 30 s, use the fallback. |

## Before the next presentation

```powershell
& $py scripts\reset_demo.py                 # fresh state; verifies evidence and agent version
& $py scripts\validate_demo.py --quick      # must end CLAIMS DEMO READY
```

Server log for a failed turn (by its `CR-…` reference): `webapp\.logs\claims-review.log`
(`review.turn_failed`). It contains no answer text, prompts or evidence content.
