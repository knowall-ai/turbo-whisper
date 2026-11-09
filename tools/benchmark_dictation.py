"""Synthetic, local speech-to-editor benchmark. Run only inside isolated Xvfb.

Requires existing espeak-ng, ffmpeg, paplay, pactl, xdotool and GPU/model runtime.
Never reads user recordings, sends audio remotely, or prints whole transcripts.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

CORPUS = {
    "tuning": [
        "Please keep the first word and the last word.",
        "I am testing local voice dictation.",
        "The final marker is sunset.",
    ],
    "confirmation": [
        "Blue lanterns line the garden path.",
        "Send the complete message to the editor after a brief pause.",
        "The final marker is cedar.",
    ],
    "continuous": [
        "First we open the notebook and describe the weather outside. "
        "Next we list the materials needed to build a wooden bookshelf. "
        "The shelf needs careful measurements and a smooth painted finish. "
        "Now we record another sentence to check that the middle is preserved. "
        "There is still more to say before this recording is complete. "
        "We must keep every sentence instead of returning only a short summary. "
        "Finally the last marker is sunset."
    ],
}
CORPUS["minute"] = [CORPUS["continuous"][0] + " " + CORPUS["continuous"][0]]


def generate(root, synthesizer):
    root.mkdir(parents=True, exist_ok=True)
    for name, sentences in CORPUS.items():
        target = root / f"{name}.wav"
        if target.exists():
            continue
        frames = []
        for index, text in enumerate(sentences):
            source = root / f"{name}-{index}-source.wav"
            converted = root / f"{name}-{index}.wav"
            subprocess.run(
                [synthesizer, "-w", str(source), "-s", "155", text],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(converted),
                ],
                check=True,
            )
            with wave.open(str(converted)) as audio:
                frames.append(audio.readframes(audio.getnframes()))
            if index < len(sentences) - 1:
                frames.append(b"\0\0" * 16000)  # Known one-second phrase pause.
        with wave.open(str(target), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(frames))


def words(text):
    return re.findall(r"\w+", text.lower())


def word_errors(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        row = [i]
        for j, actual in enumerate(hypothesis, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual)))
        previous = row
    return previous[-1]


def run(args):
    if os.environ.get("TURBO_WHISPER_TEST_X11") != "1":
        raise SystemExit("Run under isolated xvfb-run with TURBO_WHISPER_TEST_X11=1")
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("An isolated X11 display is required")
    import hashlib

    from PyQt6.QtWidgets import QApplication, QPlainTextEdit

    from turbo_whisper.config import Config
    from turbo_whisper.main import RecordingWindow, TurboWhisper
    from turbo_whisper.typer import Typer

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["TURBO_WHISPER_CONFIG"] = str(output / "profile" / "config.json")
    generate(args.inputs, args.synthesizer)
    fixture = args.inputs / f"{args.workload}.wav"
    data = fixture.read_bytes()
    with wave.open(io.BytesIO(data)) as audio:
        audio_seconds = audio.getnframes() / audio.getframerate()
    reference = words(" ".join(CORPUS[args.workload]))
    config = Config(
        transcription_backend="whisper_cpp",
        whisper_cpp_model=str(args.model.resolve()),
        whisper_cpp_timeout=120,
        auto_paste=True,
        copy_to_clipboard=False,
        store_recordings=False,
        claude_integration=False,
    )
    # Also works against the preserved baseline whose Config lacks the new key.
    config.live_transcription = args.mode == "live"
    config.typing_delay_ms = 5
    app = QApplication.instance() or QApplication([])
    sink = "turbo_benchmark_" + str(os.getpid())
    module = subprocess.check_output(
        [
            "pactl",
            "load-module",
            "module-null-sink",
            "sink_name=" + sink,
            "rate=16000",
            "channels=1",
        ],
        text=True,
    ).strip()
    config.input_device_index = sink + ".monitor"
    controller = None
    editor = QPlainTextEdit()
    editor.setWindowTitle("Synthetic dictation benchmark")
    editor.resize(820, 420)
    rows = []
    try:
        # Keep hotkeys, activation, uinput and native desktop discovery out of this
        # isolated test. Actual typing uses xdotool against the Xvfb editor.
        with (
            patch.object(Config, "load", classmethod(lambda cls: config)),
            patch.object(TurboWhisper, "_setup_activation_server", lambda self: None),
            patch.object(Typer, "_setup_linux", lambda self: None),
            patch.object(
                RecordingWindow,
                "_populate_mic_dropdown",
                lambda self: self.mic_combo.addItem("Synthetic monitor", sink + ".monitor"),
            ),
        ):
            controller = TurboWhisper()
        controller.window_detector.get_focused_window_name = lambda: "Synthetic editor"
        for index in range(args.runs):
            editor.clear()
            editor.show()
            editor.activateWindow()
            editor.setFocus()
            app.processEvents()
            subprocess.run(["xdotool", "windowfocus", str(int(editor.winId()))], check=True)
            clocks = {}
            playback_done = threading.Event()
            original_level = controller._on_audio_level

            def level_callback(level, buffer):
                clocks.setdefault("first_capture", time.monotonic())
                if level > 0.01:
                    clocks.setdefault("signal_onset", time.monotonic())
                original_level(level, buffer)

            controller._on_audio_level = level_callback
            start = time.monotonic()
            controller._start_recording()

            def play():
                time.sleep(0.2)
                clocks["play_start"] = time.monotonic()
                result = subprocess.run(
                    ["paplay", "--device=" + sink, str(fixture)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                clocks["play_returncode"] = result.returncode
                clocks["speech_end"] = time.monotonic()
                time.sleep(0.15)
                playback_done.set()

            playback = threading.Thread(target=play, daemon=True)
            playback.start()
            stopped = False
            first_text = None
            completion_seen = None
            deadline = start + audio_seconds + 125
            while time.monotonic() < deadline:
                app.processEvents()
                if editor.toPlainText() and first_text is None:
                    first_text = time.monotonic()
                    editor.grab().save(str(output / f"{index}-first-text.png"))
                    controller.window.grab().save(str(output / f"{index}-recording.png"))
                if playback_done.is_set() and not stopped:
                    clocks["stop"] = time.monotonic()
                    controller._stop_recording()
                    stopped = True
                if stopped and not controller.is_transcribing:
                    # xdotool returning only proves events were sent. Let Qt
                    # consume them before checking usable text or starting again.
                    if completion_seen is None:
                        completion_seen = time.monotonic()
                    if config.history and editor.toPlainText() == config.history[0]["text"]:
                        break
                    if time.monotonic() - completion_seen > 0.5:
                        break
                time.sleep(0.002)
            end = time.monotonic()
            playback.join(timeout=1)
            controller._on_audio_level = original_level
            if controller.is_recording or controller.is_transcribing:
                raise RuntimeError("Dictation did not finish before the benchmark timeout")
            if clocks.get("play_returncode") != 0 or not config.history:
                raise RuntimeError("Synthetic playback or transcription failed")
            result = config.history[0]["text"]
            inserted = editor.toPlainText()
            with wave.open(io.BytesIO(controller.recorder.stop())) as captured:
                captured_seconds = captured.getnframes() / captured.getframerate()
            row = {
                "run": index,
                "mode": args.mode,
                "workload": args.workload,
                "model_state": "process-cold" if index == 0 else "repeated-session",
                "audio_sha256": hashlib.sha256(data).hexdigest(),
                "audio_seconds": audio_seconds,
                "captured_seconds": captured_seconds,
                "first_capture_seconds": clocks["first_capture"] - start,
                "signal_onset_delay_seconds": clocks["signal_onset"] - clocks["play_start"],
                "first_usable_text_seconds": (
                    first_text - clocks["play_start"] if first_text else None
                ),
                "text_before_stop": first_text < clocks["stop"] if first_text else False,
                "final_from_speech_end_seconds": end - clocks["speech_end"],
                "final_from_stop_seconds": end - clocks["stop"],
                "reference_words": len(reference),
                "transcript_words": len(words(result)),
                "word_errors": word_errors(reference, words(result)),
                "inserted_matches_transcript": inserted == result,
                "first_marker": words(result)[:1] == reference[:1],
                "last_marker": words(result)[-1:] == reference[-1:],
            }
            editor.grab().save(str(output / f"{index}-final-text.png"))
            rows.append(row)
            (output / "timings.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            app.processEvents()
    finally:
        if controller:
            if getattr(controller, "_live_session", None):
                controller._live_session.cancel()
            if hasattr(controller.client, "close"):
                controller.client.close()
            controller.recorder.cleanup()
            controller.window.settings_panel.close()
            controller.window.close()
            controller.tray.hide()
            controller._waveform_timer.stop()
        editor.close()
        subprocess.run(["pactl", "unload-module", module], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--mode", choices=["batch", "live"], required=True)
    parser.add_argument("--workload", choices=CORPUS, default="tuning")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=Path(".latency-bench/workloads"))
    parser.add_argument("--synthesizer", default=shutil.which("espeak-ng") or "espeak-ng")
    run(parser.parse_args())
