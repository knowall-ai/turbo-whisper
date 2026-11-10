"""Serialize complete, pause-delimited phrases without dropping captured audio."""

import io
import threading
import wave
from concurrent.futures import CancelledError

import numpy as np

from .api import WhisperAPIError


class PhraseTranscriber:
    # Endpoint hints only: quiet audio is retained and is always flushed on stop.
    PAUSE_SECONDS = 0.6
    QUIET_RMS = 0.004

    def __init__(self, client, sample_rate, channels, on_phrase, on_complete, on_error):
        self.client = client
        self.sample_rate = sample_rate
        self.channels = channels
        self.on_phrase = on_phrase
        self.on_complete = on_complete
        self.on_error = on_error
        self._condition = threading.Condition()
        self._pending = bytearray()
        self._boundary = 0
        self._quiet_frames = 0
        self._has_sound = False
        self._finished = False
        self._cancelled = False
        self._text = []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.future = None

    def start(self, executor=None):
        if executor is None:
            self.thread.start()
        else:
            self.future = executor.submit(self._run)

    def join(self, timeout=None):
        if self.future is None:
            self.thread.join(timeout)
        else:
            try:
                self.future.result(timeout=timeout)
            except CancelledError:
                pass

    def is_alive(self):
        return not self.future.done() if self.future is not None else self.thread.is_alive()

    def feed(self, pcm):
        # Called by the capture thread; never infer, type or wait here.
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
        quiet = float(np.sqrt(np.mean(samples * samples))) < self.QUIET_RMS
        with self._condition:
            if self._cancelled or self._finished:
                return
            self._pending.extend(pcm)
            if quiet:
                self._quiet_frames += len(pcm) // (2 * self.channels)
                if self._has_sound and self._quiet_frames >= self.sample_rate * self.PAUSE_SECONDS:
                    # If inference is busy, coalesce endpoints into one pending
                    # phrase. There is one worker and no queue of stale snapshots.
                    self._boundary = len(self._pending)
                    self._has_sound = False
                    self._condition.notify()
            else:
                self._has_sound = True
                self._quiet_frames = 0

    def finish(self):
        with self._condition:
            self._finished = True
            self._condition.notify()

    def cancel(self):
        with self._condition:
            self._cancelled = True
            self._pending.clear()
            self._condition.notify()
        if self.future is not None:
            self.future.cancel()

    def _wav(self, pcm):
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setparams((self.channels, 2, self.sample_rate, 0, "NONE", "not compressed"))
            audio.writeframes(pcm)
        return output.getvalue()

    def _run(self):
        try:
            with self._condition:
                if self._cancelled:
                    return
            self.client.prepare_live()
            while True:
                with self._condition:
                    self._condition.wait_for(
                        lambda: self._cancelled or self._finished or self._boundary
                    )
                    if self._cancelled:
                        return
                    length = len(self._pending) if self._finished else self._boundary
                    pcm = bytes(self._pending[:length])
                    del self._pending[:length]
                    self._boundary = 0
                    finished = self._finished
                # After an endpoint, an exactly-zero final tail contains no
                # speech. Re-inferencing it can hallucinate an extra word.
                # The recorder still retains it; never filter low-volume PCM.
                zero_tail = finished and self._text and not any(pcm)
                if pcm and not zero_tail:
                    text = self.client.transcribe_live_sync(self._wav(pcm)).strip()
                    with self._condition:
                        if self._cancelled:
                            return
                    if text:
                        self._text.append(text)
                        self.on_phrase(text)
                if finished:
                    self.on_complete(" ".join(self._text))
                    return
        except Exception as exc:
            with self._condition:
                if self._cancelled:
                    return
            self.on_error(
                str(exc) if isinstance(exc, WhisperAPIError) else "Local live transcription failed"
            )
