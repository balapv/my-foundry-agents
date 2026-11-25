# Voice demo setup checklist

Use this 15–30 minutes before presenting. Commands are PowerShell, run from the `contoso-air-customer-care` folder
with the virtual environment active (`.\.venv\Scripts\Activate.ps1`) and `$env:PYTHONIOENCODING="utf-8"` set. On
macOS/Linux, use `source .venv/bin/activate`.

## Repository

- [ ] Correct repository and branch checked out. `git status` shows nothing you don't expect.
- [ ] The validated voice version is configured: `voice/.voice-state.json` → `activeAgentVersion` (or
      `FOUNDRY_VOICE_AGENT_VERSION` in `.env`). The readiness check below prints it.
- [ ] Demo 1A fallback present (the readiness check confirms its files).

## Azure / Foundry

One command checks the sign-in, project, voice agent and version, model/voice/barge-in settings, the portal
playground identity default, the toolbox (Operations API + File Search), the indexed policy knowledge, the
Operations API and the shared data:

- [ ] `python voice\scripts\validate_voice_demo.py` reports **VOICE DEMO READY**.
- [ ] If sign-in fails: `az login`, then `az account set --subscription <name>`, and run it again.
- [ ] Note any **Newer version exists** warning: the portal playground opens the agent's *latest* version. If the
      latest isn't the validated one, select the validated version in the portal before **Start session**.

## Browser and audio

- [ ] Microsoft Edge or Google Chrome, current version.
- [ ] A **close-talk microphone**: a wired or USB headset mic, or a lapel mic. **Never the laptop's built-in
      microphone with speakers on**: the agent hears its own voice, transcribes it as you, and answers itself.
      Avoid switching Bluetooth devices after this point.
- [ ] Windows **Settings** → **System** → **Sound**: **Input** is the close-talk mic; the level moves when you
      speak.
- [ ] **Output**: for a room audience, the room audio (HDMI/conference system) at a moderate volume, with the mic
      pointed away from the speakers; for a remote presentation, share the tab or system audio and listen on the
      headset.
- [ ] The Foundry portal tab has **microphone permission** (the padlock/site icon in the address bar → Microphone →
      Allow) and uses the headset.
- [ ] In the voice agent's playground, **Start session** connects and plays the greeting. Then end the session.

## Validation

- [ ] `python voice\scripts\validate_voice_demo.py --live` reports **VOICE DEMO READY** (one scripted hero call,
      about 2 minutes). One failed wording check is not a blocker; read the transcript it names and confirm the facts
      (see [demo-script.md](demo-script.md#what-a-good-call-looks-like)).
- [ ] **One real spoken test in the portal**: say the opening request, then "Yes, tell me the details.", then
      interrupt with "Wait, what about the connecting flight?"
  - [ ] It recommends the **9:20 nonstop (CT226)** in Economy Plus for all four.
  - [ ] When you interrupt, it **stops and answers the new question**.
- [ ] End the session. Start a **fresh session** only when you're on stage.
- [ ] Open the agent's **Traces** (or **Monitor**) tab. If your test session appears with its tool calls, use it at
      3:45. If not, open the newest `voice\results\<timestamp>-V2-hero*\transcript.md` from the `--live` call instead.

## Presentation

- [ ] Foundry: the `contoso-air-customer-care-voice` agent page, with the **voice**, **instructions**, knowledge and
      **toolbox** settings visible without scrolling. Its playground is ready to **Start session**.
- [ ] Traces (or the recorded transcript) open in a tab.
- [ ] Architecture visual open: [assets/voice-architecture.svg](assets/voice-architecture.svg).
- [ ] Code view open at `voice/agent/voice_common.py` → `build_voice_definition` (around line 180).
- [ ] Unneeded tabs closed. Nothing on screen shows subscription IDs, keys or endpoints (`.env` and
      `voice/.voice-state.json` closed).
- [ ] Notifications off (Windows: **Do not disturb**). Browser zoom about 125%.
- [ ] [demo-script.md](demo-script.md) and [troubleshooting.md](troubleshooting.md) to hand.

## Fallback ready, but not visible

Demo 1A is not shown unless voice fails. Prepare it in a **separate, minimized window**:

- [ ] `python scripts\validate_demo.py` reports **DEMO READY**.
- [ ] Web app running (`python -m uvicorn server:app --app-dir webapp/backend --port 8080`). In
      `http://localhost:8080`, send the Demo 1A hero prompt and wait for the CT226 answer. Don't restart the server.
- [ ] [../../demo/fallback-transcript.md](../../demo/fallback-transcript.md) open in the same background window.
- [ ] You know the transition line in [demo-script.md](demo-script.md#fallback-to-demo-1a).
