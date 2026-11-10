"""Exercise real UNO ranges in an isolated, disposable Writer profile/document."""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import uno

from turbo_whisper.writer import WriterBridge, WriterError
from turbo_whisper.writer_helper import WriterRanges


def check():
    profile = Path(tempfile.mkdtemp(prefix="turbo-whisper-writer-test-")).as_uri()
    gui = os.environ.get("TURBO_WHISPER_WRITER_GUI") == "1"
    bridge = WriterBridge(office="libreoffice", profile=profile, headless=not gui)
    desktop = None
    checks = []
    try:
        bridge.call("open")
        context = uno.getComponentContext()
        resolver = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", context
        )
        remote = resolver.resolve(
            "uno:pipe,name=" + bridge.pipe_name + ";urp;StarOffice.ComponentContext"
        )
        desktop = remote.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", remote
        )
        document = desktop.getCurrentComponent()
        document.Text.String = "Prefix.  Suffix."
        caret = document.CurrentController.ViewCursor
        caret.gotoStart(False)
        caret.goRight(8, False)
        bridge.begin("first").result(timeout=15)
        bridge.call("append", id="first", text="She go to work.")
        assert document.Text.String == "Prefix. She go to work. Suffix."
        checks.append("live-before-stop")
        bridge.call("append", id="first", text=" Because the train was delayed.")
        bridge.call(
            "replace",
            id="first",
            text="She goes to work. Because the train was delayed.",
            message="Unfinished sentence — provisional; review in Turbo Whisper",
        )
        expected = "Prefix. She goes to work. Because the train was delayed. Suffix."
        assert document.Text.String == expected
        fields = document.TextFields.createEnumeration()
        annotations = []
        while fields.hasMoreElements():
            item = fields.nextElement()
            if item.supportsService("com.sun.star.text.TextField.Annotation"):
                annotations.append(item.Content)
        assert len(annotations) == 1 and "Unfinished sentence" in annotations[0]
        checks.append("full-result-and-visible-provisional-tail")
        bridge.call(
            "replace",
            id="first",
            text="She goes to work because the train was delayed.",
            message="",
        )
        assert (
            document.Text.String
            == "Prefix. She goes to work because the train was delayed. Suffix."
        )
        checks.append("review-applies-once-with-surroundings-preserved")
        # Outside edits shift the tracked range without joining it.
        before = document.Text.createTextCursor()
        document.Text.insertString(before, "Outside. ", False)
        bridge.call("replace", id="first", text="She goes to work.", message="")
        assert document.Text.String == "Outside. Prefix. She goes to work. Suffix."
        checks.append("outside-edits-preserved")
        # A caret move changes neither the owned range nor the replacement target.
        caret.gotoEnd(False)
        bridge.call("replace", id="first", text="She goes to work!", message="")
        assert document.Text.String == "Outside. Prefix. She goes to work! Suffix."
        checks.append("caret-movement-does-not-retarget")
        # Directly changing the owned words blocks replacement.
        search = document.createSearchDescriptor()
        search.SearchString = "She goes to work!"
        found = document.findFirst(search)
        found.String = "User edited these words."
        snapshot = document.Text.String
        try:
            bridge.call("replace", id="first", text="Must never overwrite edits.", message="")
            raise AssertionError("Changed range was overwritten")
        except WriterError:
            assert document.Text.String == snapshot
        checks.append("user-edits-block-overwrite")
        caret.gotoStart(False)
        caret.goRight(7, True)
        try:
            bridge.begin("selection").result(timeout=5)
            raise AssertionError("Existing selection was accepted for replacement")
        except WriterError:
            assert document.Text.String == snapshot
        caret.collapseToEnd()
        checks.append("existing-selection-is-preserved")

        bridge.call("open")
        second = desktop.getCurrentComponent()
        second.Text.String = ""
        bridge.begin("queued-a").result(timeout=5)
        bridge.begin("queued-b").result(timeout=5)
        bridge.call("append", id="queued-a", text="First phrase.")
        bridge.call("replace", id="queued-a", text="First phrase!", message="")
        bridge.call("append", id="queued-b", text="Second phrase.")
        bridge.call("replace", id="queued-b", text="Second phrase!", message="")
        assert second.Text.String == "First phrase! Second phrase!"
        assert document.Text.String == snapshot
        checks.append("queued-sessions-in-order-without-overlap")

        second.CurrentController.ViewCursor.gotoEnd(False)
        bridge.begin("overlap-a").result(timeout=5)
        bridge.call("append", id="overlap-a", text="Third")
        bridge.begin("overlap-b").result(timeout=5)
        bridge.call("append", id="overlap-a", text=" phrase.")
        bridge.call("replace", id="overlap-a", text="Third phrase!", message="")
        bridge.call("append", id="overlap-b", text="Fourth phrase.")
        assert second.Text.String.endswith("Third phrase! Fourth phrase.")
        checks.append("restart-while-previous-tail-and-polish-are-pending")

        # Unicode is replaced as a range, with no character-count/backspace math.
        second.CurrentController.ViewCursor.gotoEnd(False)
        bridge.begin("unicode").result(timeout=5)
        bridge.call("append", id="unicode", text="Maya 🙂 is ready.")
        bridge.call("replace", id="unicode", text="Maya 🙂 is ready!", message="")
        assert second.Text.String.endswith("Maya 🙂 is ready!")
        checks.append("unicode-round-trip")

        search = second.createSearchDescriptor()
        search.SearchString = "Maya"
        second.findFirst(search).CharWeight = 150
        snapshot_second = second.Text.String
        try:
            bridge.call("replace", id="unicode", text="Maya 🙂 is ready.", message="")
            raise AssertionError("Mixed formatting was replaced")
        except WriterError:
            assert second.Text.String == snapshot_second
        checks.append("mixed-formatting-requires-review")
        second.close(True)
        try:
            bridge.call("replace", id="unicode", text="Never another document.", message="")
            raise AssertionError("Closed range accepted replacement")
        except WriterError:
            assert document.Text.String == snapshot
        checks.append("closed-document-does-not-retarget")
        bridge.call("open")
        disposable = desktop.getCurrentComponent()
        ranges = WriterRanges(desktop)
        for index in range(60):
            ranges.begin(str(index))
            ranges.mark(str(index), "Cancelled empty capture")
        assert len(ranges.sessions) <= 40
        assert all(session["previous"] is None for session in ranges.sessions.values())
        assert disposable.Text.String == ""
        checks.append("repeated-empty-sessions-release-range-chains")
        # Unaccept invalidates proxies on that connection. Observe through a
        # separate test-only acceptor to distinguish disconnect from document loss.
        observer_name = "tw_observer_" + uuid.uuid4().hex
        observer_url = "pipe,name=" + observer_name + ";urp;StarOffice.ComponentContext"
        subprocess.run(
            [
                "libreoffice",
                "-env:UserInstallation=" + profile,
                "--nodefault",
                "--accept=" + observer_url,
            ]
            + ([] if gui else ["--headless"]),
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        bridge.close()
        bridge.process.wait(timeout=5)
        assert not list(Path("/tmp").glob("*" + bridge.pipe_name + "*"))
        # PyUNO aliases identical remote objects across connections in one
        # process; disconnect can invalidate those aliases too. A fresh observer
        # proves that the office/documents, not merely local proxies, survive.
        observer_code = """
import sys, uno
context=uno.getComponentContext()
resolver=context.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',context)
remote=resolver.resolve('uno:pipe,name='+sys.argv[1]+';urp;StarOffice.ComponentContext')
desktop=remote.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',remote)
try:
    assert desktop.getCurrentComponent().Text.String == ''
    components=desktop.getComponents().createEnumeration()
    documents=[]
    while components.hasMoreElements():
        documents.append(components.nextElement())
    assert len(documents) >= 2
finally:
    # These are disposable fixtures. Avoid a GUI save dialog during test cleanup.
    components=desktop.getComponents().createEnumeration()
    documents=[]
    while components.hasMoreElements():
        documents.append(components.nextElement())
    for document in documents:
        document.setModified(False)
        document.close(True)
    desktop.terminate()
"""
        observed = subprocess.run(
            [sys.executable, "-c", observer_code, observer_name],
            timeout=10,
            capture_output=True,
            text=True,
        )
        desktop = None
        assert observed.returncode == 0, observed.stderr
        checks.append("private-acceptor-cleanup-leaves-documents-open")
        return checks
    finally:
        bridge.close()
        if desktop is not None:
            try:
                components = desktop.getComponents().createEnumeration()
                documents = []
                while components.hasMoreElements():
                    documents.append(components.nextElement())
                for document in documents:
                    document.setModified(False)
                    document.close(True)
                desktop.terminate()  # Only our disposable profile, never the user's office.
            except Exception:
                pass


if __name__ == "__main__":
    print(json.dumps({"checks": check()}))
