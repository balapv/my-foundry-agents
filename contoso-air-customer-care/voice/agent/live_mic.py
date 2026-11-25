"""Talk to the Contoso Air voice agent with a real microphone and speakers.

This is the real-microphone check for Demo 1B: you speak, the agent answers out loud, and you can
interrupt it mid-sentence (barge-in). It connects to the same published voice agent version as
run_session.py, with the same customer_id structured input; no instructions or tools are sent.

When the service detects you speaking while the agent is talking, the client:
  1. stops local playback immediately and discards the rest of the agent's buffered audio, and
  2. truncates the agent's audio item at the point you actually heard, so the agent's memory of
     what it said matches what you heard.

Use a headset. Laptop speakers feed the agent's own voice back into the microphone and can trigger
false interruptions.

Everything is recorded under voice/results/<stamp>-live-mic/ (gitignored): events.jsonl,
caller.wav, agent.wav, transcript.md and summary.json, including every barge-in.

Usage (from contoso-air-customer-care, with the virtual environment active):
    python voice/agent/live_mic.py                       # Alex Johnson (CUST-1007), active version
    python voice/agent/live_mic.py --customer-id CUST-1021 --version 9
    python voice/agent/live_mic.py --list-devices
Press Ctrl+C to end the call.
"""

from __future__ import annotations

import argparse
import base64
import json
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_common import ConfigError, load_voice_config, resolve_voice_agent_version, voice_settings  # noqa: E402
from run_session import (  # noqa: E402
    AUDIO_DELTA_TYPES, BYTES_PER_MS, NOISY_DELTA_TYPES, RESULTS_DIR, SAMPLE_RATE, short_tool_name, write_wav,
)
from agent.foundry_common import configure_console  # noqa: E402

CHUNK_MS = 50


class PlaybackBuffer:
    """Agent audio waiting to be played, tracked per item so a barge-in can truncate precisely.

    The audio callback thread calls read(); the main loop calls add() and clear().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[list[Any]] = []  # [item_id, bytearray]
        self.played_bytes: dict[str, int] = {}
        self.current_item: str | None = None

    def add(self, item_id: str, pcm: bytes) -> None:
        with self._lock:
            if self._queue and self._queue[-1][0] == item_id:
                self._queue[-1][1].extend(pcm)
            else:
                self._queue.append([item_id, bytearray(pcm)])

    def read(self, nbytes: int) -> bytes:
        out = bytearray()
        with self._lock:
            while len(out) < nbytes and self._queue:
                item_id, pcm = self._queue[0]
                take = pcm[:nbytes - len(out)]
                del pcm[:len(take)]
                out.extend(take)
                self.played_bytes[item_id] = self.played_bytes.get(item_id, 0) + len(take)
                self.current_item = item_id
                if not pcm:
                    self._queue.pop(0)
        return bytes(out) + b"\x00" * (nbytes - len(out))

    @property
    def pending_ms(self) -> int:
        with self._lock:
            return sum(len(pcm) for _, pcm in self._queue) // BYTES_PER_MS

    def clear(self) -> dict[str, Any] | None:
        """Drop unplayed audio. Returns the interrupted item and how much of it was heard, if any was playing."""
        with self._lock:
            if not self._queue:
                return None
            item_id = self._queue[0][0]
            discarded = sum(len(pcm) for _, pcm in self._queue)
            self._queue.clear()
        return {"itemId": item_id, "heardMs": self.played_bytes.get(item_id, 0) // BYTES_PER_MS,
                "discardedMs": discarded // BYTES_PER_MS}


@dataclass
class CallLog:
    started: float = field(default_factory=time.monotonic)
    lines: list[dict[str, Any]] = field(default_factory=list)
    barge_ins: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    response_latencies_ms: list[int] = field(default_factory=list)

    def at(self) -> float:
        return round(time.monotonic() - self.started, 2)

    def say(self, who: str, text: str, **extra: Any) -> None:
        self.lines.append({"atS": self.at(), "who": who, "text": text, **extra})
        label = {"agent": "agent", "caller": "you (heard)", "tool": "  tool", "barge-in": "  >> barge-in"}[who]
        print(f"[{self.at():6.1f}s] {label}: {text}")


def write_call_transcript(path: Path, meta: dict[str, Any], log: CallLog) -> None:
    out = [f"# Live microphone call: {meta['startedUtc']}", "",
           f"- Agent: `{meta['agent']}` version {meta['agentVersion']} ({meta['versionSource']})",
           f"- customer_id: `{meta['customerId']}`", f"- Duration: {meta['totalSeconds']} s",
           f"- Barge-ins: {len(log.barge_ins)}", ""]
    for line in log.lines:
        who = {"agent": "**Agent**", "caller": "**Caller (heard)**", "tool": "Tool", "barge-in": "**Barge-in**"}
        out.append(f"- `{line['atS']:.1f}s` {who[line['who']]}: {line['text']}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def run_call(project: Any, settings: dict[str, str], customer_id: str, version: str | None, version_source: str,
             max_minutes: float, input_device: Any, output_device: Any) -> dict[str, Any]:
    import sounddevice as sd

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / f"{stamp}-live-mic"
    out_dir.mkdir(parents=True, exist_ok=True)
    mic: queue.Queue[bytes] = queue.Queue()
    playback = PlaybackBuffer()
    log = CallLog()
    caller_pcm, agent_pcm = bytearray(), bytearray()
    truncated_items: set[str] = set()
    speech_stopped_at: float | None = None
    awaiting_first_audio = False
    frames = SAMPLE_RATE * CHUNK_MS // 1000

    def on_mic(indata: Any, _frames: int, _time: Any, status: Any) -> None:
        mic.put(bytes(indata))

    def on_speaker(outdata: Any, nframes: int, _time: Any, status: Any) -> None:
        outdata[:] = playback.read(nframes * 2)

    extra_query = {"agent_version_override": version} if version else None
    print(f"Connecting to {settings['agent_name']} version {version or 'latest'} as {customer_id}. "
          "Speak when the agent finishes its greeting. Ctrl+C ends the call.\n")
    with open(out_dir / "events.jsonl", "w", encoding="utf-8") as events_file, \
            project.voice_agents.realtime.connect(agent_name=settings["agent_name"],
                                                  structured_inputs={"customer_id": customer_id},
                                                  extra_query=extra_query) as conn, \
            sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frames,
                              device=input_device, callback=on_mic), \
            sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frames,
                               device=output_device, callback=on_speaker):
        deadline = time.monotonic() + max_minutes * 60
        try:
            while time.monotonic() < deadline:
                while not mic.empty():
                    chunk = mic.get_nowait()
                    caller_pcm.extend(chunk)
                    conn.input_audio_buffer.append(audio=base64.b64encode(chunk).decode("ascii"))
                try:
                    event = conn.recv(timeout=0.02)
                except TimeoutError:
                    continue
                data = event if isinstance(event, dict) else event.as_dict()
                etype = data.get("type", "")
                if etype not in NOISY_DELTA_TYPES:
                    events_file.write(json.dumps({"t": log.at(), **json.loads(json.dumps(data, default=str))}) + "\n")

                if etype in AUDIO_DELTA_TYPES:
                    item_id = data.get("item_id", "")
                    if item_id in truncated_items:
                        continue
                    delta = data.get("delta")
                    pcm = bytes(delta) if isinstance(delta, (bytes, bytearray)) else base64.b64decode(delta or "")
                    if awaiting_first_audio and speech_stopped_at is not None:
                        log.response_latencies_ms.append(int((time.monotonic() - speech_stopped_at) * 1000))
                        awaiting_first_audio = False
                    agent_pcm.extend(pcm)
                    playback.add(item_id, pcm)
                elif etype == "input_audio_buffer.speech_started":
                    cut = playback.clear()
                    if cut:
                        truncated_items.add(cut["itemId"])
                        conn.conversation.item.truncate(item_id=cut["itemId"], content_index=0,
                                                        audio_end_ms=cut["heardMs"])
                        log.barge_ins.append({"atS": log.at(), **cut})
                        log.say("barge-in", f"stopped agent audio after {cut['heardMs']} ms "
                                            f"({cut['discardedMs']} ms not played)")
                elif etype == "input_audio_buffer.speech_stopped":
                    speech_stopped_at, awaiting_first_audio = time.monotonic(), True
                elif etype == "conversation.item.input_audio_transcription.completed":
                    log.say("caller", data.get("transcript", "").strip())
                elif etype in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
                    item_id = data.get("item_id", "")
                    text = data.get("transcript", "")
                    if item_id in truncated_items:
                        heard = next(b["heardMs"] for b in log.barge_ins if b["itemId"] == item_id)
                        log.say("agent", text, interruptedAtMs=heard)
                    else:
                        log.say("agent", text)
                elif etype == "response.output_item.done" and (data.get("item") or {}).get("type") == "mcp_call":
                    item = data["item"]
                    call = {"atS": log.at(), "tool": short_tool_name(item.get("name", "")),
                            "arguments": item.get("arguments"), "ok": not item.get("error")}
                    log.tool_calls.append(call)
                    log.say("tool", f"{call['tool']} {call['arguments']} -> {'ok' if call['ok'] else 'error'}")
                elif etype == "error":
                    log.errors.append(data.get("error"))
                    print(f"  ! error: {data.get('error')}")
        except KeyboardInterrupt:
            print("\nCall ended.")
        while playback.pending_ms and time.monotonic() < deadline:
            time.sleep(0.05)

    meta = {"scenario": "live-mic", "agent": settings["agent_name"], "agentVersion": version or "latest",
            "versionSource": version_source, "customerId": customer_id, "startedUtc": stamp,
            "totalSeconds": log.at()}
    summary = {**meta, "bargeIns": log.barge_ins, "toolCalls": log.tool_calls, "errors": log.errors,
               "responseLatencyMs": log.response_latencies_ms, "lines": log.lines,
               "callerAudioMs": len(caller_pcm) // BYTES_PER_MS, "agentAudioMs": len(agent_pcm) // BYTES_PER_MS}
    write_wav(out_dir / "caller.wav", bytes(caller_pcm))
    write_wav(out_dir / "agent.wav", bytes(agent_pcm))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_call_transcript(out_dir / "transcript.md", meta, log)
    print(f"\n{len(log.barge_ins)} barge-in(s), {len(log.tool_calls)} tool call(s), {len(log.errors)} error(s). "
          f"Results: voice/results/{out_dir.name}/")
    return summary


def _device(value: str | None) -> Any:
    return int(value) if value and value.isdigit() else value


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customer-id", default="CUST-1007", help="signed-in customer (default: CUST-1007)")
    parser.add_argument("--version", help="voice agent version (default: the active version)")
    parser.add_argument("--max-minutes", type=float, default=10.0)
    parser.add_argument("--input-device", help="microphone index or name (see --list-devices)")
    parser.add_argument("--output-device", help="speaker/headset index or name (see --list-devices)")
    parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    args = parser.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        print("sounddevice is not installed: pip install -r voice/requirements.txt", file=sys.stderr)
        return 2
    if args.list_devices:
        print(sd.query_devices())
        return 0

    try:
        settings = voice_settings(load_voice_config())
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if not settings["project_endpoint"]:
        print("Configuration error: FOUNDRY_PROJECT_ENDPOINT is not set (.env).", file=sys.stderr)
        return 2
    version, version_source = resolve_voice_agent_version(settings, args.version)

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with DefaultAzureCredential() as credential, \
            AIProjectClient(endpoint=settings["project_endpoint"], credential=credential) as project:
        summary = run_call(project, settings, args.customer_id, version, version_source, args.max_minutes,
                           _device(args.input_device), _device(args.output_device))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
