# Voice demo troubleshooting

Optimized for recovering a **live presentation**, not for diagnosis. Rule of thumb: **one quick fix, then fall
back.** The transition line and fallback order are in [demo-script.md](demo-script.md#fallback-to-demo-1a).

Before the session, run `python voice\scripts\validate_voice_demo.py`; each failure it prints includes a fix.

## Microphone not detected

**Symptom:** the playground can't start the microphone, or the agent never reacts when you speak.

1. Check the headset is plugged in and selected as the input (Windows **Settings** → **System** → **Sound**).
2. In the browser's site settings for the Foundry tab, choose the headset microphone. End the session and **Start
   session** again.

Still nothing: fall back.

## Browser permission blocked

**Symptom:** a blocked-microphone icon in the address bar, or no permission prompt.

1. Click the padlock/site icon → **Microphone** → **Allow**.
2. Reload the page, then **Start session**.

If the browser policy blocks the microphone entirely, fall back; don't change browser settings on stage.

## No agent audio

**Symptom:** the session connects (the transcript shows text) but you hear nothing.

1. Check the output device and volume (Windows volume mixer: the browser isn't muted).
2. Check the browser tab isn't muted (right-click the tab).

If the audience can't hear it within about 20 seconds, fall back.

## Voice session fails to connect

**Symptom:** "Failed to connect to the voice agent", or **Start session** spins.

- **Wrong version selected.** Sessions on versions without a demo default identity are rejected by the playground
  (the playground can't send `customer_id`). Select the validated version, which the readiness check reported.
- Sign-in expired: reload the portal (and `az login` for the scripts).
- Run `python voice\scripts\validate_voice_demo.py` after the presentation if it's not obvious.

On stage: one retry of **Start session**, then fall back.

## Toolbox or Operations API unavailable

**Symptom:** the agent says it can't look up your trip or flight, or the answer has no flight details.

- Quick check (in a terminal, off screen): `python voice\scripts\validate_voice_demo.py`. The **Operations API**
  section checks `/health` and the hero data; the **Foundry voice agent** section checks the toolbox.
- The Operations API runs on Azure Container Apps and can take up to about 30 seconds to wake from idle. Running the
  readiness check before the presentation wakes it.

On stage: don't wait for a redeploy. Fall back to the prepared Demo 1A conversation or the fallback transcript.

## Slow response

A short progress sentence ("I'll check your reservation first…") followed by silence is normal while it calls the
systems. The interim message *"Thanks for waiting. I'm still checking."* plays if a step takes more than 3.5 seconds.

| Silence after you stop speaking | Action |
|---|---|
| Up to 15 s | Keep waiting; narrate what it's checking. |
| 15–30 s | "It's checking several systems; let's give it a moment." |
| More than 30 s | Fall back. |

## Transcription misunderstanding

**Symptom:** the agent answers a different question, or asks you to repeat.

Repeat naturally once, a little more slowly. If it still misunderstands something that changes the decision (the
date, the number of travelers, which flight), end the session and start a fresh one, or fall back. Don't argue with
the agent on stage.

## Agent answers without being asked

**Symptom:** the agent keeps talking or answers questions nobody asked, as if following a script. The playground
transcript shows user messages you didn't say, often echoes of the agent's own sentences.

**Cause:** echo. The microphone picks up the agent's voice from the speakers, transcribes it as you, and the agent
replies to it. Most common with built-in laptop speakers and microphone.

1. End the session.
2. Switch the input to a close-talk mic (headset or lapel), or put on a headset, and lower the room volume.
3. **Start session** again.

If no headset is available, fall back. Don't keep talking over the echo.

## Barge-in doesn't work

**Symptom:** the agent keeps talking when you interrupt.

Don't troubleshoot it on stage. Let it finish, then ask "What about the connecting flight?" as a normal turn; the
grounded answer still makes the point. Mention the interruption only if it worked. If the audio is unusable
(echo, the agent interrupting itself), switch to a headset if one is at hand, otherwise fall back.

## Unexpected agent response

**Symptom:** the wrong customer, flight or date; it claims the booking was changed or held; it recommends a flight
that can't seat all four together in Economy Plus; it invents a policy amount.

**Don't live-edit the instructions, and don't publish a new version.** Say "Let me show you a validated run" and
fall back. After the presentation, save the session transcript and compare it with
[validation-record.md](validation-record.md) and [../evaluation/expected_behaviors.md](../evaluation/expected_behaviors.md).

Wording differences, letter-by-letter flight numbers ("C T two twenty-six") or leaving out how much longer the
connection takes are **known, acceptable variations**, not failures.

## 429 or service failure

**Symptom:** "too many requests", "service busy", HTTP 429 or 5xx, or the session drops mid-call.

Don't retry repeatedly; repeated attempts make throttling worse. Fall back straight away, and retry the voice call
once later only if the agenda allows.
