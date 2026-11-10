"""Local Writer transport, isolated from Qt's Python and arbitrary keyboard input."""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import uuid
from concurrent.futures import Future
from pathlib import Path


class WriterError(Exception):
    pass


class WriterBridge:
    def __init__(self, python="", office="", profile=None, headless=False):
        self.python = python
        self.office = office
        self.profile = profile
        self.headless = headless
        self.process = None
        self._lock = threading.Lock()
        self._responses = queue.Queue()
        self._closed = False
        self.pipe_name = "turbo_whisper_" + uuid.uuid4().hex

    def _environment(self):
        environment = dict(os.environ)
        for key in (
            "PYTHONPATH",
            "PYTHONHOME",
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "LD_LIBRARY_PATH",
        ):
            environment.pop(key, None)
        environment["PYTHONUTF8"] = "1"
        return environment

    def _start(self):
        candidates = (
            [self.python]
            if self.python
            else [
                sys.executable,
                "/usr/bin/python3",
                "/Applications/LibreOffice.app/Contents/Resources/python",
                str(
                    Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
                    / "LibreOffice/program/python.exe"
                ),
            ]
        )
        interpreter = None
        for candidate in candidates:
            try:
                if (
                    subprocess.run(
                        [candidate, "-c", "import uno"],
                        timeout=3,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=self._environment(),
                    ).returncode
                    == 0
                ):
                    interpreter = candidate
                    break
            except (OSError, subprocess.TimeoutExpired):
                continue
        office = self.office or shutil.which("libreoffice") or shutil.which("soffice")
        if not office:
            for candidate in [
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                str(
                    Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
                    / "LibreOffice/program/soffice.exe"
                ),
            ]:
                if Path(candidate).is_file():
                    office = candidate
                    break
        if not interpreter or not office:
            raise WriterError("Install LibreOffice and Python UNO support to use Writer mode")
        self.process = subprocess.Popen(
            [interpreter, str(Path(__file__).with_name("writer_helper.py"))],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=self._environment(),
        )
        process = self.process

        def receive():
            try:
                for line in process.stdout:
                    try:
                        self._responses.put(json.loads(line))
                    except ValueError:
                        self._responses.put({"error": "Invalid Writer response"})
            finally:
                self._responses.put({"error": "Writer connection closed; text retained for review"})

        threading.Thread(target=receive, daemon=True, name="writer-responses").start()
        self._send(
            {
                "office": office,
                "pipe": self.pipe_name,
                "profile": self.profile,
                "headless": self.headless,
            }
        )
        self._read()

    def _send(self, request):
        try:
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError, AttributeError) as error:
            raise WriterError("Writer connection closed; text retained for review") from error

    def _read(self):
        try:
            result = self._responses.get(timeout=10)
        except queue.Empty as error:
            self._closed = True
            self.process.terminate()
            raise WriterError(
                "Writer timed out; inspect the document and Review before retrying"
            ) from error
        if "error" in result:
            raise WriterError(result["error"])
        return result

    def call(self, operation, **arguments):
        with self._lock:
            if self._closed:
                raise WriterError("Writer connection unavailable; restart Turbo Whisper")
            if self.process is None:
                self._start()
            self._send({"op": operation, **arguments})
            return self._read()

    def begin(self, identifier):
        future = Future()

        def bind():
            try:
                future.set_result(self.call("begin", id=identifier))
            except Exception as error:
                future.set_exception(error)

        threading.Thread(target=bind, daemon=True, name="writer-bind").start()
        return future

    def close(self):
        self._closed = True
        if self.process is not None and self.process.poll() is None:
            try:
                self._send({"op": "close"})
            except WriterError:
                pass

            # Allow the helper to remove its acceptor without blocking Qt exit.
            def reap():
                try:
                    self.process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self.process.terminate()

            threading.Thread(target=reap, daemon=True).start()
