"""Per-recording state and bounded, serial inference independent of capture."""

import threading
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass, field
from queue import Full


@dataclass
class DictationSession:
    token: int
    auto_paste: bool
    copy_to_clipboard: bool
    worker: object = None
    future: Future | None = None
    texts: list[str] = field(default_factory=list)
    remainder: list[str] = field(default_factory=list)
    audio_filename: str | None = None
    stopped: bool = False
    cancelled: bool = False
    writer_id: str | None = None
    writer_binding: Future | None = None
    review: dict | None = None

    def cancel(self):
        self.cancelled = True
        if self.worker is not None:
            self.worker.cancel()
        if self.future is not None:
            self.future.cancel()


class SerialWorker:
    """One daemon worker; canceled queued jobs are pruned before accepting more."""

    def __init__(self, capacity=20):
        self.capacity = capacity
        self._condition = threading.Condition()
        self._tasks = deque()
        self._closed = False
        self.thread = threading.Thread(target=self._run, daemon=True, name="dictation-worker")
        self.thread.start()

    def submit(self, function):
        future = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError("The dictation worker has stopped")
            self._tasks = deque(item for item in self._tasks if not item[0].cancelled())
            if len(self._tasks) >= self.capacity:
                raise Full("Transcription queue is full; wait for pending recordings")
            self._tasks.append((future, function))
            self._condition.notify()
        return future

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._tasks)
                if self._closed:
                    return
                future, function = self._tasks.popleft()
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(function())
                except BaseException as error:
                    future.set_exception(error)

    def shutdown(self):
        with self._condition:
            self._closed = True
            for future, _ in self._tasks:
                future.cancel()
            self._tasks.clear()
            self._condition.notify()
