"""Run live voice sessions against the Contoso Air Customer Care VOICE agent (Demo 1B, Phase V1).

Each scenario in voice/evaluation/test_cases.json is one live Foundry voice session. By default every
user turn is real speech: the text is synthesized with Azure Speech (Microsoft Entra sign-in, no keys)
and streamed into the session as PCM16 audio, so server-side turn detection and speech-to-text run
exactly as they would for a microphone. --input text sends typed turns instead.

    python voice/agent/run_session.py --list
    python voice/agent/run_session.py --scenario V1-hero
    python voice/agent/run_session.py --all
    python voice/agent/run_session.py --scenario V1-hero --input text --version 3

Per run, voice/results/<timestamp>-<scenario>/ (git-ignored) receives transcript.md, summary.json,
events.jsonl (audio elided) and per-turn WAV files of what the caller said and what the agent said.

This script is a channel/harness only. It never interprets policy, ranks flights or decides anything for
the customer; the Foundry voice agent does all of that. The checks it prints are deterministic
assertions on what the agent said and which tools it called.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_common import (  # noqa: E402
    VOICE_DIR,
    ConfigError,
    load_voice_config,
    resolve_voice_agent_version,
    voice_settings,
)

from agent.foundry_common import configure_console  # noqa: E402
from evaluation.run_evaluation import GUARDS  # noqa: E402  (Demo 1A guard phrases, reused read-only)

TEST_CASES_FILE = VOICE_DIR / "evaluation" / "test_cases.json"
RESULTS_DIR = VOICE_DIR / "results"
SAMPLE_RATE = 24_000  # PCM16 mono, the voice session's default audio format
BYTES_PER_MS = SAMPLE_RATE * 2 // 1000
CALLER_VOICE = "en-US-AndrewNeural"
AUDIO_DELTA_TYPES = {"response.output_audio.delta", "response.audio.delta"}
NOISY_DELTA_TYPES = AUDIO_DELTA_TYPES | {
    "response.output_audio_transcript.delta", "response.audio_transcript.delta",
    "response.mcp_call_arguments.delta", "response.function_call_arguments.delta",
}


# --------------------------------------------------------------------------- scenarios


def load_scenarios(path: Path = TEST_CASES_FILE) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["scenarios"]


def short_tool_name(name: str) -> str:
    """contoso_air_operations___get_flight_status -> get_flight_status; File Search keeps its tool name."""
    return name.split("___")[-1] if name else name


# --------------------------------------------------------------------------- caller audio


class CallerVoice:
    """Synthesizes the caller's lines with Azure Speech on the same Foundry resource (Entra auth)."""

    def __init__(self, project_endpoint: str, credential: Any) -> None:
        import azure.cognitiveservices.speech as speechsdk
        from urllib.parse import urlparse

        host = urlparse(project_endpoint).hostname
        config = speechsdk.SpeechConfig(token_credential=credential, endpoint=f"https://{host}/")
        config.speech_synthesis_voice_name = CALLER_VOICE
        config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm)
        self._sdk = speechsdk
        self._synth = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)

    def speak(self, text: str) -> bytes:
        result = self._synth.speak_text_async(text).get()
        if result.reason != self._sdk.ResultReason.SynthesizingAudioCompleted:
            details = result.cancellation_details.error_details if result.cancellation_details else result.reason
            raise RuntimeError(f"Caller speech synthesis failed: {details}")
        return bytes(result.audio_data)


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


# --------------------------------------------------------------------------- session recording


@dataclass
class TurnRecord:
    index: int
    user_text: str
    input_mode: str
    label: str | None = None  # "4b" for the caller's answer to a clarifying question asked in turn 4
    user_transcription: str | None = None
    interrupted_previous: dict[str, Any] | None = None
    agent_segments: list[dict[str, Any]] = field(default_factory=list)
    audio_items: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    timings_ms: dict[str, Any] = field(default_factory=dict)
    agent_audio: bytearray = field(default_factory=bytearray)
    caller_audio_ms: int | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.label or str(self.index)

    @property
    def agent_text(self) -> str:
        return "\n".join(s["text"] for s in self.agent_segments if s.get("text"))

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index, "label": self.label, "userText": self.user_text, "inputMode": self.input_mode,
            "userTranscription": self.user_transcription, "interruptedPrevious": self.interrupted_previous,
            "agentSegments": self.agent_segments, "audioItems": self.audio_items, "toolCalls": self.tool_calls,
            "errors": self.errors, "timingsMs": self.timings_ms, "agentAudioMs": len(self.agent_audio) // BYTES_PER_MS,
            "callerAudioMs": self.caller_audio_ms, "metrics": self.metrics, "checks": self.checks,
        }


class SessionRunner:
    def __init__(self, conn: Any, events_file: Any, idle_seconds: float, turn_timeout: float) -> None:
        self.conn = conn
        self.events_file = events_file
        self.idle_seconds = idle_seconds
        self.turn_timeout = turn_timeout
        self.session_info: dict[str, Any] = {}
        self.conversation_id: str | None = None
        self.last_agent_audio_item: dict[str, Any] | None = None  # {"item_id", "audio_ms"}
        self._t0 = time.monotonic()
        self._buffer: deque[tuple[float, dict[str, Any]]] = deque()

    # ---- event plumbing

    def _read(self, timeout: float) -> tuple[float, dict[str, Any]] | None:
        try:
            event = self.conn.recv(timeout=timeout)
        except TimeoutError:
            return None
        arrived = time.monotonic()
        data = event if isinstance(event, dict) else event.as_dict()
        if data.get("type", "") not in NOISY_DELTA_TYPES:
            logged = json.loads(json.dumps(data, default=str))
            self.events_file.write(json.dumps({"t": round(arrived - self._t0, 3), **logged}) + "\n")
        return arrived, data

    def _recv(self, timeout: float) -> tuple[float, dict[str, Any]] | None:
        """Next event with its arrival time; events drained while streaming audio keep their real arrival time."""
        return self._buffer.popleft() if self._buffer else self._read(timeout)

    def drain(self) -> None:
        while (got := self._read(timeout=0.001)) is not None:
            self._buffer.append(got)

    @staticmethod
    def _audio_bytes(delta: Any) -> bytes:
        if isinstance(delta, (bytes, bytearray)):
            return bytes(delta)
        return base64.b64decode(delta) if delta else b""

    def _note_session(self, data: dict[str, Any]) -> None:
        session = dict(data.get("session") or {})
        session.pop("instructions", None)
        session.pop("tools", None)
        self.session_info = {k: session.get(k) for k in ("id", "model", "output_modalities", "audio", "voice",
                                                          "turn_detection", "input_audio_transcription")
                             if session.get(k) is not None}

    # ---- turn processing

    def pump(self, turn: TurnRecord | None, start: float) -> None:
        """Process events until the agent is idle (no response or tool call in flight for idle_seconds)."""
        item_first_audio: dict[str, int] = {}
        item_audio: dict[str, int] = {}
        try:
            self._pump(turn, start, item_first_audio, item_audio)
        finally:
            if turn is not None:
                turn.audio_items = [{"itemId": item_id, "firstAudioMs": first,
                                     "audioMs": item_audio.get(item_id, 0) // BYTES_PER_MS}
                                    for item_id, first in item_first_audio.items()]

    def _pump(self, turn: TurnRecord | None, start: float, item_first_audio: dict[str, int],
              item_audio: dict[str, int]) -> None:
        active_responses: set[str] = set()
        pending_calls: dict[str, dict[str, Any]] = {}
        saw_response = False
        quiet_since: float | None = None
        deadline = start + self.turn_timeout

        def ms(at: float) -> int:
            return int((at - start) * 1000)

        while True:
            now = time.monotonic()
            if now > deadline:
                if turn:
                    turn.errors.append({"type": "harness_timeout", "message": f"turn exceeded {self.turn_timeout}s"})
                return
            busy = bool(active_responses or pending_calls)
            if saw_response and not busy:
                quiet_since = quiet_since or now
                if now - quiet_since >= self.idle_seconds:
                    return
            else:
                quiet_since = None
            got = self._recv(timeout=0.5)
            if got is None:
                continue
            now, data = got
            etype = data.get("type", "")

            if etype in ("session.created", "session.updated"):
                self._note_session(data)
            elif etype == "response.created":
                saw_response = True
                response = data.get("response") or {}
                active_responses.add(response.get("id", ""))
                self.conversation_id = response.get("conversation_id") or self.conversation_id
                if turn is not None:
                    turn.timings_ms.setdefault("firstResponseCreated", ms(now))
            elif etype == "response.done":
                response = data.get("response") or {}
                active_responses.discard(response.get("id", ""))
                if turn is not None:
                    turn.timings_ms.setdefault("responsesDone", []).append(ms(now))
                    if response.get("status") not in ("completed", None):
                        turn.errors.append({"type": "response_" + str(response.get("status")),
                                            "details": response.get("status_details")})
            elif etype in AUDIO_DELTA_TYPES:
                chunk = self._audio_bytes(data.get("delta"))
                item_id = data.get("item_id", "")
                item_audio[item_id] = item_audio.get(item_id, 0) + len(chunk)
                item_first_audio.setdefault(item_id, ms(now))
                if turn is not None:
                    turn.timings_ms.setdefault("firstAgentAudio", ms(now))
                    turn.agent_audio.extend(chunk)
            elif etype in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
                item_id = data.get("item_id", "")
                if turn is not None:
                    turn.agent_segments.append({"atMs": ms(now), "itemId": item_id, "text": data.get("transcript", "")})
                if item_audio.get(item_id):
                    self.last_agent_audio_item = {"item_id": item_id,
                                                  "audio_ms": item_audio[item_id] // BYTES_PER_MS}
            elif etype == "conversation.item.input_audio_transcription.completed":
                if turn is not None:
                    turn.user_transcription = data.get("transcript", "").strip()
                    turn.timings_ms.setdefault("userTranscriptionCompleted", ms(now))
            elif etype == "input_audio_buffer.speech_started" and turn is not None:
                turn.timings_ms.setdefault("speechStarted", ms(now))
            elif etype == "input_audio_buffer.speech_stopped" and turn is not None:
                turn.timings_ms.setdefault("speechStopped", ms(now))
            elif etype == "response.mcp_call.in_progress":
                pending_calls[data.get("item_id", "")] = {"startedMs": ms(now)}
            elif etype == "response.output_item.done" and (data.get("item") or {}).get("type") == "mcp_call":
                item = data["item"]
                started = pending_calls.pop(item.get("id", ""), {}).get("startedMs")
                if turn is not None:
                    try:
                        arguments = json.loads(item.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = item.get("arguments")
                    turn.tool_calls.append({
                        "tool": short_tool_name(item.get("name", "")),
                        "fullName": item.get("name"),
                        "server": item.get("server_label"),
                        "arguments": arguments,
                        "startedMs": started,
                        "completedMs": ms(now),
                        "ok": not item.get("error"),
                        "error": item.get("error"),
                        "output": item.get("output"),
                    })
            elif etype == "error" and turn is not None:
                turn.errors.append({"type": "server_error", "error": data.get("error")})

    # ---- user input

    def send_text(self, text: str) -> float:
        self.conn.conversation.item.create(item={
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]})
        self.conn.response.create()
        return time.monotonic()

    def send_audio(self, pcm: bytes, chunk_ms: int = 100, pace: float = 1.0, trailing_silence_ms: int = 1500) -> float:
        """Stream speech then trailing silence at real-time pace, as a microphone would.

        Server turn detection ends the turn and creates the response itself. Events that arrive while
        streaming are buffered with their arrival time. Returns the time the caller finished speaking.
        """
        step = chunk_ms * BYTES_PER_MS
        for offset in range(0, len(pcm), step):
            self.conn.input_audio_buffer.append(audio=base64.b64encode(pcm[offset:offset + step]).decode("ascii"))
            time.sleep(chunk_ms / 1000 * pace)
            self.drain()
        end_of_speech = time.monotonic()
        silence = b"\x00" * step
        for _ in range(trailing_silence_ms // chunk_ms):
            self.conn.input_audio_buffer.append(audio=base64.b64encode(silence).decode("ascii"))
            time.sleep(chunk_ms / 1000 * pace)
            self.drain()
        return end_of_speech

    def interrupt_playback(self, after_ms: int) -> dict[str, Any] | None:
        """Barge-in as a playing client would: truncate the agent's last spoken item where the caller cut in."""
        item = self.last_agent_audio_item
        if not item or item["audio_ms"] <= after_ms:
            return None
        self.conn.conversation.item.truncate(item_id=item["item_id"], content_index=0, audio_end_ms=after_ms)
        return {"itemId": item["item_id"], "agentAudioMs": item["audio_ms"], "heardMs": after_ms}


# --------------------------------------------------------------------------- checks


def _arguments_match(actual: Any, expected: dict[str, Any]) -> bool:
    return isinstance(actual, dict) and all(
        str(actual.get(k, "")).strip().upper() == str(v).strip().upper() for k, v in expected.items())


def evaluate_expectations(tool_calls: list[dict[str, Any]], reply: str, timings_ms: dict[str, Any],
                          expect: dict[str, Any], guards: list[str] = ()) -> list[dict[str, Any]]:
    """Deterministic checks: tools called, tool arguments, what the agent said and guard phrases."""
    checks: list[dict[str, Any]] = []
    called = [c["tool"] for c in tool_calls]
    reply = normalize_text(reply)
    for guard in guards:
        match = next((m for p in GUARDS[guard] if (m := re.search(p, reply, re.IGNORECASE))), None)
        checks.append({"check": f"guard {guard}", "passed": match is None,
                       "found": match.group(0) if match else None})
    for tool in expect.get("toolsCalled", []):
        checks.append({"check": f"calls {tool}", "passed": tool in called})
    for tool in expect.get("toolsNotCalled", []):
        checks.append({"check": f"does not call {tool}", "passed": tool not in called})
    for spec in expect.get("toolArguments", []):
        ok = any(c["tool"] == spec["tool"] and _arguments_match(c["arguments"], spec["arguments"])
                 for c in tool_calls)
        checks.append({"check": f"{spec['tool']} called with {spec['arguments']}", "passed": ok})
    for spec in expect.get("forbiddenToolArguments", []):
        bad = any(c["tool"] == spec["tool"] and _arguments_match(c["arguments"], spec["arguments"])
                  for c in tool_calls)
        checks.append({"check": f"never calls {spec['tool']} with {spec['arguments']}", "passed": not bad,
                       "why": spec.get("why")})
    for rule in expect.get("replyMustMatch", []):
        checks.append({"check": f"says /{rule['pattern']}/", "why": rule.get("why"),
                       "passed": bool(re.search(rule["pattern"], reply, re.IGNORECASE))})
    for rule in expect.get("replyMustNotMatch", []):
        match = re.search(rule["pattern"], reply, re.IGNORECASE)
        checks.append({"check": f"never says /{rule['pattern']}/", "why": rule.get("why"),
                       "passed": match is None, "found": match.group(0) if match else None})
    if expect.get("maxFirstAudioMs") and "firstAgentAudio" in timings_ms:
        checks.append({"check": f"first agent audio within {expect['maxFirstAudioMs']} ms",
                       "passed": timings_ms["firstAgentAudio"] <= expect["maxFirstAudioMs"]})
    return checks


def evaluate_turn(turn: TurnRecord, expect: dict[str, Any], guards: list[str] = ()) -> list[dict[str, Any]]:
    return evaluate_expectations(turn.tool_calls, turn.agent_text, turn.timings_ms, expect, guards)


# A clarifying question about WHICH flight or WHAT the caller meant. Offers such as "Would you like the
# details?" are deliberately not clarifications.
CLARIFICATION_PATTERN = (r"\b(?:do|did) you mean\b|\bwhich (?:one|flight|option)\b|\bare you (?:asking|referring|"
                         r"talking) about\b|\bjust to (?:make sure|confirm|be sure|be clear|double[- ]check)\b|"
                         r"\byou mean the\b|\bis that the\b|\bthe one (?:at|that|leaving)\b")


def normalize_text(text: str) -> str:
    return (text or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u2011", "-").replace("\u2013", "-")


def is_clarification(text: str, pattern: str | None = None) -> bool:
    """True when one of the agent's questions asks the caller which thing they meant."""
    questions = re.findall(r"[^.!?\n]*\?", normalize_text(text))
    return any(re.search(pattern or CLARIFICATION_PATTERN, q, re.IGNORECASE) for q in questions)


_SPELLING = {"canceled": "cancelled", "ok": "okay"}


def transcription_similarity(script: str, heard: str | None) -> float | None:
    """Word-level similarity (0-1) between what the caller said and the service's speech-to-text."""
    if heard is None:
        return None
    import difflib

    def words(text: str) -> list[str]:
        return [_SPELLING.get(w, w) for w in re.findall(r"[a-z0-9']+", normalize_text(text).lower())]

    return round(difflib.SequenceMatcher(None, words(script), words(heard)).ratio(), 3)


def compute_turn_metrics(turn: TurnRecord, recommendation_pattern: str | None = None) -> dict[str, Any]:
    """Latency and verbosity measures for one turn, in ms from the end of the caller's speech.

    Arrival times say when audio reached the client. "Heard" times model a client that plays every agent
    audio item in order without gaps or overlap, which is what a listener experiences: an item can't be
    heard before the previous one has finished playing.
    """
    cursor = None
    heard: dict[str, tuple[int, int]] = {}
    for item in turn.audio_items:
        begin = item["firstAudioMs"] if cursor is None else max(item["firstAudioMs"], cursor)
        cursor = begin + item["audioMs"]
        heard[item["itemId"]] = (begin, cursor)
    for seg in turn.agent_segments:
        item = next((i for i in turn.audio_items if i["itemId"] == seg.get("itemId")), None)
        if item:
            seg["firstAudioMs"], seg["audioMs"] = item["firstAudioMs"], item["audioMs"]
            seg["heardStartMs"], seg["heardEndMs"] = heard[item["itemId"]]

    spoken = [s for s in turn.agent_segments if s.get("text") and s.get("audioMs")]
    first_result = min((c["completedMs"] for c in turn.tool_calls if c.get("completedMs") is not None), default=None)
    meaningful = next((s for s in spoken if first_result is not None and s["firstAudioMs"] >= first_result), None)
    if first_result is None and spoken:
        meaningful = spoken[0]
    recommendation = None
    if recommendation_pattern:
        recommendation = next((s for s in spoken if re.search(recommendation_pattern, normalize_text(s["text"]),
                                                               re.IGNORECASE)), None)
    answer = recommendation or (spoken[-1] if spoken else None)
    metrics = {
        "firstAudioMs": turn.timings_ms.get("firstAgentAudio"),
        "firstMeaningfulMs": meaningful["firstAudioMs"] if meaningful else None,
        "firstMeaningfulHeardMs": meaningful["heardStartMs"] if meaningful else None,
        "progressUtterances": spoken.index(answer) if answer in spoken else 0,
        "segmentsAfterAnswer": len(spoken) - 1 - spoken.index(answer) if answer in spoken else 0,
        "spokenSegments": len(spoken),
        "agentAudioMs": sum(i["audioMs"] for i in turn.audio_items),
        "agentSpeechEndHeardMs": cursor,
        "callerAudioMs": turn.caller_audio_ms,
        "transcriptionSimilarity": (transcription_similarity(turn.user_text, turn.user_transcription)
                                    if turn.input_mode == "audio" else None),
        "toolCalls": len(turn.tool_calls),
        "toolFailures": sum(1 for c in turn.tool_calls if not c.get("ok")),
    }
    if recommendation_pattern:
        metrics["recommendationMs"] = recommendation["firstAudioMs"] if recommendation else None
        metrics["recommendationHeardMs"] = recommendation["heardStartMs"] if recommendation else None
    return metrics


def clarification_checks(asked: bool, expected: str) -> list[dict[str, Any]]:
    if expected == "required":
        return [{"check": "asks which flight the caller means", "passed": asked}]
    if expected == "forbidden":
        return [{"check": "answers without an unnecessary clarifying question", "passed": not asked}]
    return []


def progress_checks(metrics: dict[str, Any], expect: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    limit = expect.get("maxProgressUtterances")
    if limit is not None:
        checks.append({"check": f"at most {limit} progress utterances before the answer",
                       "passed": metrics.get("progressUtterances", 0) <= limit,
                       "found": metrics.get("progressUtterances")})
    limit = expect.get("maxSegmentsAfterAnswer")
    if limit is not None:
        checks.append({"check": f"at most {limit} spoken segments after the answer (no restated answer)",
                       "passed": metrics.get("segmentsAfterAnswer", 0) <= limit,
                       "found": metrics.get("segmentsAfterAnswer")})
    return checks


def evaluate_session(turns: list[TurnRecord], expect: dict[str, Any]) -> list[dict[str, Any]]:
    """Expectations that may be met in any turn (for example, which tools the whole call used)."""
    calls = [c for t in turns for c in t.tool_calls]
    reply = "\n".join(t.agent_text for t in turns)
    return [{**c, "check": "session: " + c["check"]} for c in evaluate_expectations(calls, reply, {}, expect)]


# --------------------------------------------------------------------------- output


def write_transcript(path: Path, scenario: dict[str, Any], meta: dict[str, Any], turns: list[TurnRecord],
                     session_checks: list[dict[str, Any]] = ()) -> None:
    lines = [f"# {scenario['id']}: {scenario['title']}", "",
             f"- Agent: `{meta['agent']}` version `{meta['agentVersion']}` ({meta['versionSource']})",
             f"- Model: `{meta.get('model')}`; input: {meta['inputMode']}; customer_id: `{scenario['customerId']}`",
             f"- Started: {meta['startedUtc']}; total: {meta['totalSeconds']} s", ""]
    if meta.get("greeting"):
        lines += ["**Agent (greeting):** " + meta["greeting"], ""]
    for turn in turns:
        lines.append(f"## Turn {turn.name}" + (" (caller answers the clarifying question)" if turn.label else ""))
        if turn.interrupted_previous:
            lines.append(f"_Caller barged in after {turn.interrupted_previous['heardMs']} ms of "
                         f"{turn.interrupted_previous['agentAudioMs']} ms of agent audio (client truncated playback)._")
        lines.append(f"**Caller (script):** {turn.user_text}")
        if turn.input_mode == "audio":
            lines.append(f"**Caller (speech-to-text):** {turn.user_transcription or '(no transcription received)'}")
        for call in turn.tool_calls:
            status = "ok" if call["ok"] else "FAILED"
            lines.append(f"- tool `{call['tool']}` {json.dumps(call['arguments'])} -> {status} "
                         f"({call['startedMs']}-{call['completedMs']} ms)")
        for seg in turn.agent_segments:
            heard = f", heard {seg['heardStartMs']}-{seg['heardEndMs']} ms" if seg.get("heardStartMs") is not None else ""
            lines.append(f"**Agent ({seg['atMs']} ms{heard}):** {seg['text']}")
        timing, m = turn.timings_ms, turn.metrics
        lines.append(f"_Timings (ms from end of caller speech): server speech-stopped {timing.get('speechStopped')}, "
                     f"first agent audio {timing.get('firstAgentAudio')}, responses done {timing.get('responsesDone')}_")
        if m:
            extra = (f", recommendation arrives {m['recommendationMs']} / heard {m['recommendationHeardMs']}"
                     if "recommendationMs" in m else "")
            lines.append(f"_Metrics: progress utterances {m['progressUtterances']}, first meaningful heard "
                         f"{m['firstMeaningfulHeardMs']}{extra}, agent audio {m['agentAudioMs']} ms, speech ends "
                         f"(heard) {m['agentSpeechEndHeardMs']}, transcription similarity "
                         f"{m['transcriptionSimilarity']}_")
        for err in turn.errors:
            lines.append(f"- ERROR: {json.dumps(err)[:400]}")
        for check in turn.checks:
            lines.append(f"- [{'PASS' if check['passed'] else 'FAIL'}] {check['check']}"
                         + (f" (found: {check['found']!r})" if check.get("found") else ""))
        lines.append("")
    if session_checks:
        lines.append("## Whole-call checks")
        lines += [f"- [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}" for c in session_checks]
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- main


def converse(runner: SessionRunner, turn: TurnRecord, out_dir: Path, caller: CallerVoice | None,
             recommendation_pattern: str | None = None) -> None:
    """Say one caller utterance, record the agent's whole reply and compute the turn's metrics."""
    stem = f"turn-{turn.index:02d}{'b' if turn.label else ''}"
    print(f"  caller ({turn.name}): {turn.user_text}")
    if turn.input_mode == "audio":
        pcm = caller.speak(turn.user_text)
        turn.caller_audio_ms = len(pcm) // BYTES_PER_MS
        write_wav(out_dir / f"{stem}-caller.wav", pcm)
        start = runner.send_audio(pcm)
    else:
        start = runner.send_text(turn.user_text)
    runner.pump(turn, start)
    turn.metrics = compute_turn_metrics(turn, recommendation_pattern)
    if turn.user_transcription:
        print(f"  (heard): {turn.user_transcription}")
    for call in turn.tool_calls:
        print(f"    tool {call['tool']} {json.dumps(call['arguments'])} -> {'ok' if call['ok'] else 'FAILED'}")
    for seg in turn.agent_segments:
        print(f"  agent: {seg['text']}")
    if turn.agent_audio:
        write_wav(out_dir / f"{stem}-agent.wav", bytes(turn.agent_audio))


def check_exchange(turn: TurnRecord, answer: TurnRecord, spec: dict[str, Any], guards: list[str],
                   asked: bool) -> list[dict[str, Any]]:
    """Checks for one scripted caller turn, including the caller's answer to a clarifying question.

    Guards cover every word the agent said in the exchange; tool expectations cover every call made in it;
    reply patterns apply to the agent's final answer (after any clarification).
    """
    expect = spec.get("expect", {})
    exchange = [turn] if answer is turn else [turn, answer]
    checks = evaluate_expectations([], "\n".join(t.agent_text for t in exchange), {}, {}, guards)
    checks += clarification_checks(asked, (spec.get("clarification") or {}).get("expected", "allowed"))
    checks += evaluate_expectations([c for t in exchange for c in t.tool_calls], answer.agent_text,
                                    turn.timings_ms, expect)
    checks += progress_checks(turn.metrics, expect)
    return checks


def run_metrics(turns: list[TurnRecord]) -> dict[str, Any]:
    """Whole-call measures for the reliability report."""
    first = turns[0].metrics if turns else {}
    similarities = [t.metrics.get("transcriptionSimilarity") for t in turns
                    if t.metrics.get("transcriptionSimilarity") is not None]
    return {
        "turn1": {k: first.get(k) for k in ("firstAudioMs", "firstMeaningfulHeardMs", "recommendationMs",
                                            "recommendationHeardMs", "progressUtterances", "agentAudioMs",
                                            "agentSpeechEndHeardMs")},
        "conversationMs": sum((t.caller_audio_ms or 0) + (t.metrics.get("agentSpeechEndHeardMs") or 0)
                              for t in turns),
        "agentAudioMs": sum(t.metrics.get("agentAudioMs") or 0 for t in turns),
        "transcriptionIssues": [{"turn": t.name, "said": t.user_text, "heard": t.user_transcription,
                                 "similarity": t.metrics.get("transcriptionSimilarity")} for t in turns
                                if t.metrics.get("transcriptionSimilarity") is not None
                                and t.metrics["transcriptionSimilarity"] < 0.85],
        "minTranscriptionSimilarity": min(similarities) if similarities else None,
        "toolFailures": sum(t.metrics.get("toolFailures") or 0 for t in turns),
        "sessionErrors": [e for t in turns for e in t.errors],
        "clarifyingQuestions": [t.index for t in turns if t.label],
    }


def run_scenario(project: Any, credential: Any, settings: dict[str, str], scenario: dict[str, Any],
                 version: str | None, version_source: str, input_mode: str, idle_seconds: float,
                 turn_timeout: float, caller: CallerVoice | None, run: int = 1, runs: int = 1) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / (f"{stamp}-{scenario['id']}" + (f"-r{run}" if runs > 1 else ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    extra_query = {"agent_version_override": version} if version else None
    turns: list[TurnRecord] = []
    started = time.monotonic()
    greeting = ""
    print(f"\n=== {scenario['id']}: {scenario['title']} (customer_id {scenario['customerId']}, {input_mode}"
          + (f", run {run}/{runs})" if runs > 1 else ")"))
    with open(out_dir / "events.jsonl", "w", encoding="utf-8") as events_file, \
            project.voice_agents.realtime.connect(
                agent_name=settings["agent_name"],
                structured_inputs={"customer_id": scenario["customerId"]},
                extra_query=extra_query,
            ) as conn:
        runner = SessionRunner(conn, events_file, idle_seconds, turn_timeout)
        greeting_turn = TurnRecord(index=0, user_text="", input_mode="none")
        runner.pump(greeting_turn, time.monotonic())
        greeting = greeting_turn.agent_text
        print(f"  agent (greeting): {greeting}")
        for index, spec in enumerate(scenario["turns"], start=1):
            spec = spec if isinstance(spec, dict) else {"say": spec}
            turn = TurnRecord(index=index, user_text=spec["say"], input_mode=input_mode)
            if spec.get("interruptAfterMs") is not None:
                turn.interrupted_previous = runner.interrupt_playback(int(spec["interruptAfterMs"]))
            converse(runner, turn, out_dir, caller, spec.get("recommendationPattern"))
            turns.append(turn)

            clarify = spec.get("clarification") or {}
            asked = is_clarification(turn.agent_text, clarify.get("pattern"))
            answer = turn
            if asked and clarify.get("reply"):
                answer = TurnRecord(index=index, label=f"{index}b", user_text=clarify["reply"], input_mode=input_mode)
                converse(runner, answer, out_dir, caller, spec.get("recommendationPattern"))
                turns.append(answer)
            turn.checks = check_exchange(turn, answer, spec, scenario.get("guards", []), asked)
            for check in turn.checks:
                print(f"    [{'PASS' if check['passed'] else 'FAIL'}] {check['check']}")
        session_info = runner.session_info
        conversation_id = runner.conversation_id

    meta = {
        "scenario": scenario["id"], "agent": settings["agent_name"], "agentVersion": version or "latest",
        "versionSource": version_source, "model": session_info.get("model"), "inputMode": input_mode,
        "customerId": scenario["customerId"], "startedUtc": stamp, "conversationId": conversation_id,
        "totalSeconds": round(time.monotonic() - started, 1), "greeting": greeting, "session": session_info,
    }
    session_checks = evaluate_session(turns, scenario.get("sessionExpect", {}))
    for check in session_checks:
        print(f"    [{'PASS' if check['passed'] else 'FAIL'}] {check['check']}")
    checks = [c for t in turns for c in t.checks] + session_checks
    errors = [e for t in turns for e in t.errors]
    summary = {**meta, "passed": all(c["passed"] for c in checks) and not errors,
               "checksPassed": sum(c["passed"] for c in checks), "checksTotal": len(checks),
               "failedChecks": [c["check"] for c in checks if not c["passed"]],
               "run": run, "runs": runs, "metrics": run_metrics(turns),
               "sessionChecks": session_checks, "turns": [t.to_json() for t in turns]}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_transcript(out_dir / "transcript.md", scenario, meta, turns, session_checks)
    verdict = "PASS" if summary["passed"] else "FAIL"
    print(f"  => {verdict}: {summary['checksPassed']}/{summary['checksTotal']} checks, {len(errors)} errors, "
          f"{meta['totalSeconds']} s. Results: voice/results/{out_dir.name}/")
    return summary


def _fmt(value: Any) -> str:
    return "-" if value is None else str(value)


def _distribution(values: list[Any]) -> str:
    values = sorted(v for v in values if v is not None)
    if not values:
        return "-"
    median = values[len(values) // 2] if len(values) % 2 else (values[len(values) // 2 - 1] + values[len(values) // 2]) // 2
    return f"min {values[0]} / median {median} / max {values[-1]} (n={len(values)})"


def summarize_results(version: str | None = None, since: str | None = None,
                      scenario_ids: list[str] | None = None, results_dir: Path = RESULTS_DIR) -> str:
    """Markdown report of every recorded run (failures included), grouped by scenario."""
    runs = []
    for path in sorted(results_dir.glob("*/summary.json")):
        if since and path.parent.name < since:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if version and str(data.get("agentVersion")) != str(version):
            continue
        if scenario_ids and data.get("scenario") not in scenario_ids:
            continue
        runs.append((path.parent.name, data))
    lines = [f"# Voice run report ({len(runs)} runs; version filter {_fmt(version)}; since {_fmt(since)})", ""]
    for scenario in sorted({d.get("scenario") for _, d in runs}):
        group = [(name, d) for name, d in runs if d.get("scenario") == scenario]
        passed = sum(1 for _, d in group if d.get("passed"))
        lines += [f"## {scenario}: {passed}/{len(group)} passed", "",
                  "| Run | Version | Result | Checks | T1 first audio | T1 progress | T1 recommendation heard "
                  "| T1 agent audio | Conversation | Min STT similarity | Tool failures | Session errors | Failed checks |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for name, d in group:
            m = d.get("metrics") or {}
            t1 = m.get("turn1") or {}
            lines.append("| " + " | ".join([
                name, _fmt(d.get("agentVersion")), "PASS" if d.get("passed") else "FAIL",
                f"{d.get('checksPassed')}/{d.get('checksTotal')}", _fmt(t1.get("firstAudioMs")),
                _fmt(t1.get("progressUtterances")), _fmt(t1.get("recommendationHeardMs")),
                _fmt(t1.get("agentAudioMs")), _fmt(m.get("conversationMs")),
                _fmt(m.get("minTranscriptionSimilarity")), _fmt(m.get("toolFailures")),
                _fmt(len(m.get("sessionErrors") or []) if m else d.get("error")),
                "; ".join(d.get("failedChecks") or ([d["error"]] if d.get("error") else [])).replace("|", "/") or "-",
            ]) + " |")
        metrics = [(d.get("metrics") or {}).get("turn1") or {} for _, d in group]
        lines += ["", f"- T1 first audio (ms): {_distribution([m.get('firstAudioMs') for m in metrics])}",
                  f"- T1 first meaningful progress heard (ms): "
                  f"{_distribution([m.get('firstMeaningfulHeardMs') for m in metrics])}",
                  f"- T1 recommendation heard (ms): {_distribution([m.get('recommendationHeardMs') for m in metrics])}",
                  f"- T1 progress utterances: {_distribution([m.get('progressUtterances') for m in metrics])}",
                  f"- T1 agent audio (ms): {_distribution([m.get('agentAudioMs') for m in metrics])}",
                  f"- Whole-call agent audio (ms): "
                  f"{_distribution([(d.get('metrics') or {}).get('agentAudioMs') for _, d in group])}", ""]
    return "\n".join(lines)


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", action="append", help="scenario id (repeatable)")
    parser.add_argument("--all", action="store_true", help="run every scenario")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    parser.add_argument("--repeat", type=int, default=1, help="run each selected scenario N times")
    parser.add_argument("--summarize", action="store_true",
                        help="print a report of recorded runs (filter with --version, --since, --scenario) and exit")
    parser.add_argument("--since", help="with --summarize: only result folders named at or after this "
                                        "timestamp prefix, for example 20261126-0900")
    parser.add_argument("--input", choices=["audio", "text"], default="audio",
                        help="audio: synthesized caller speech (default); text: typed turns")
    parser.add_argument("--version", help="voice agent version (default: FOUNDRY_VOICE_AGENT_VERSION, "
                                          "then activeAgentVersion in voice/.voice-state.json)")
    parser.add_argument("--idle-seconds", type=float, default=4.0,
                        help="quiet time with no response or tool call in flight that ends a turn")
    parser.add_argument("--turn-timeout", type=float, default=150.0)
    args = parser.parse_args()

    if args.summarize:
        report = summarize_results(args.version, args.since, args.scenario)
        print(report)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / f"report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
        out.write_text(report, encoding="utf-8")
        print(f"\nSaved to voice/results/{out.name}")
        return 0

    scenarios = load_scenarios()
    if args.list:
        for s in scenarios:
            print(f"{s['id']:24s} {s['title']} ({len(s['turns'])} turns, customer_id {s['customerId']})")
        return 0
    selected = scenarios if args.all else [s for s in scenarios if s["id"] in set(args.scenario or [])]
    if not selected:
        print("Choose --scenario ID (see --list) or --all.", file=sys.stderr)
        return 2

    config = load_voice_config()
    settings = voice_settings(config)
    if not settings["project_endpoint"]:
        print("Configuration error: FOUNDRY_PROJECT_ENDPOINT is not set (.env).", file=sys.stderr)
        return 2
    version, version_source = resolve_voice_agent_version(settings, args.version)
    print(f"Voice agent {settings['agent_name']} version {version or 'latest'} ({version_source})")

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    summaries = []
    with DefaultAzureCredential() as credential, \
            AIProjectClient(endpoint=settings["project_endpoint"], credential=credential) as project:
        caller = CallerVoice(settings["project_endpoint"], credential) if args.input == "audio" else None
        for scenario in selected:
            for run in range(1, max(args.repeat, 1) + 1):
                try:
                    summaries.append(run_scenario(project, credential, settings, scenario, version, version_source,
                                                  args.input, args.idle_seconds, args.turn_timeout, caller,
                                                  run, max(args.repeat, 1)))
                except (ConfigError, RuntimeError, OSError) as exc:
                    print(f"  => ERROR: {type(exc).__name__}: {exc}")
                    summaries.append({"scenario": scenario["id"], "passed": False, "error": str(exc)})
    passed = sum(1 for s in summaries if s.get("passed"))
    print(f"\n{passed}/{len(summaries)} scenarios passed.")
    return 0 if passed == len(summaries) else 1


if __name__ == "__main__":
    sys.exit(main())
