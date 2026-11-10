"""Private JSON-lines adapter, run by LibreOffice's UNO-capable Python.

Only command results reach stdout. Exceptions/document contents never reach logs.
The helper opens no files and never saves or terminates the user's office process.
"""

import json
import subprocess
import sys
import time


class WriterFault(Exception):
    pass


class WriterRanges:
    def __init__(self, desktop):
        self.desktop = desktop
        self.sessions = {}

    def begin(self, identifier):
        document = self.desktop.getCurrentComponent()
        if document is None or not document.supportsService("com.sun.star.text.TextDocument"):
            raise WriterFault("Open a Writer document and place the caret before dictating")
        if document.isReadonly():
            raise WriterFault("The Writer document is read-only")
        caret = document.CurrentController.ViewCursor
        if not caret.isCollapsed():
            raise WriterFault("Place the Writer caret without selecting existing text")
        # Keep a model cursor: edits outside this range shift it naturally.
        span = caret.Text.createTextCursorByRange(caret)
        previous = None
        for prior in reversed(list(self.sessions.values())):
            if prior["document"] == document and prior["text"] == caret.Text:
                if caret.Text.compareRegionEnds(prior["span"].End, caret.End) == 0:
                    previous = prior
                break
        self.sessions[identifier] = {
            "document": document,
            "text": caret.Text,
            "span": span,
            "expected": "",
            "separator": "",
            "annotation": None,
            "previous": previous,
            "finished": False,
        }
        # At most 20 pending captures plus 20 recent review bindings.
        for key in list(self.sessions):
            if len(self.sessions) <= 40:
                break
            if self.sessions[key]["finished"]:
                del self.sessions[key]
        return {}

    def _checked(self, identifier):
        session = self.sessions.get(identifier)
        if session is None:
            raise WriterFault("This Writer session is unavailable; copy reviewed text instead")
        document = session["document"]
        try:
            unchanged = not document.isReadonly() and session["span"].String == session["expected"]
        except Exception as error:
            session["finished"] = True
            session["previous"] = None
            raise WriterFault("Writer document unavailable; result retained for review") from error
        if not unchanged:
            session["finished"] = True
            session["previous"] = None
            raise WriterFault("Dictated text was edited in Writer; automatic replacement stopped")
        return session

    def _note(self, session, message):
        note = session["annotation"]
        if not message:
            if note is not None:
                try:
                    session["text"].removeTextContent(note)
                except Exception:
                    pass  # The user or range replacement may have removed this field.
                session["annotation"] = None
        elif note is not None:
            try:
                note.Content = message
            except Exception:
                session["annotation"] = None
                self._note(session, message)
        else:
            note = session["document"].createInstance("com.sun.star.text.TextField.Annotation")
            note.Author = "Turbo Whisper"
            note.Content = message
            session["text"].insertTextContent(session["span"].End, note, False)
            session["annotation"] = note

    def append(self, identifier, addition):
        session = self._checked(identifier)
        document, text, span = session["document"], session["text"], session["span"]
        if not session["expected"]:
            previous = session["previous"]
            if previous is not None:
                if previous["span"].String != previous["expected"]:
                    raise WriterFault("Earlier dictation was edited; review this result")
                span.gotoRange(previous["span"].End, False)
            session["previous"] = None
            before = text.createTextCursorByRange(span.Start)
            before.goLeft(1, True)
            if before.String and not before.String[-1].isspace() and addition[:1].isalnum():
                session["separator"] = " "
            addition = session["separator"] + addition
        caret = document.CurrentController.ViewCursor
        follow = (
            caret.Text == text
            and caret.isCollapsed()
            and text.compareRegionEnds(caret.End, span.End) == 0
        )
        end = text.createTextCursorByRange(span.End)
        text.insertString(end, addition, True)
        if not session["expected"]:
            span.gotoRange(end.Start, False)
        span.gotoRange(end.End, True)
        session["expected"] += addition
        if span.String != session["expected"]:
            raise WriterFault("Writer did not retain the expected dictation range; review required")
        self._note(session, "Live dictation — provisional until recording stops")
        if follow:
            caret.gotoRange(span.End, False)
        return {}

    def replace(self, identifier, replacement, message=""):
        session = self._checked(identifier)
        document, text, span = session["document"], session["text"], session["span"]
        value = session["separator"] + replacement
        caret = document.CurrentController.ViewCursor
        follow = (
            caret.Text == text
            and caret.isCollapsed()
            and text.compareRegionEnds(caret.End, span.End) == 0
        )
        undo = document.UndoManager
        for property_name in (
            "CharStyleName",
            "CharWeight",
            "CharPosture",
            "CharUnderline",
            "CharHeight",
            "CharColor",
            "ParaStyleName",
        ):
            if span.getPropertyState(property_name).value == "AMBIGUOUS_VALUE":
                raise WriterFault("Dictation has mixed formatting; review and edit it in Writer")
        undo.enterUndoContext("Polish dictation")
        try:
            self._note(session, "")
            self._checked(identifier)
            # A single Writer call replaces the verified range atomically. Avoid
            # setString(), which removes styles. Mixed formatting requires review.
            text.insertString(span, value, True)
            if span.String != value:
                raise WriterFault("Writer range changed during replacement; review required")
            session["expected"] = value
            session["finished"] = True
            self._note(session, message)
            if follow:
                caret.gotoRange(span.End, False)
        finally:
            undo.leaveUndoContext()
        return {}

    def mark(self, identifier, message):
        session = self._checked(identifier)
        session["finished"] = True
        session["previous"] = None
        if session["expected"]:
            self._note(session, message)
        return {}


def serve():
    import uno

    options = json.loads(sys.stdin.readline())
    accept = "pipe,name=" + options["pipe"] + ";urp;StarOffice.ComponentContext"
    command = [options["office"]]
    if options.get("profile"):
        command.append("-env:UserInstallation=" + options["profile"])
    command += ["--norestore", "--nodefault", "--nologo"]
    if options.get("headless"):
        command.append("--headless")
    subprocess.Popen(
        command + ["--accept=" + accept], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    context = uno.getComponentContext()
    resolver = context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", context
    )
    remote = None
    for _ in range(100):
        try:
            remote = resolver.resolve("uno:" + accept)
            break
        except Exception:
            time.sleep(0.05)
    if remote is None:
        print(json.dumps({"error": "Could not connect to Writer"}), flush=True)
        return
    desktop = remote.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", remote)
    ranges = WriterRanges(desktop)
    print(json.dumps({"ready": True}), flush=True)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                operation = request["op"]
                if operation == "close":
                    break
                if operation == "open":
                    document = desktop.loadComponentFromURL(
                        "private:factory/swriter", "_blank", 0, ()
                    )
                    document.CurrentController.Frame.activate()
                    desktop.setActiveFrame(document.CurrentController.Frame)
                    result = {}
                elif operation == "begin":
                    result = ranges.begin(request["id"])
                elif operation == "append":
                    result = ranges.append(request["id"], request["text"])
                elif operation == "replace":
                    result = ranges.replace(
                        request["id"], request["text"], request.get("message", "")
                    )
                elif operation == "mark":
                    result = ranges.mark(request["id"], request["message"])
                else:
                    raise WriterFault("Unsupported Writer operation")
                print(json.dumps({"ok": True, **result}), flush=True)
            except WriterFault as error:
                print(json.dumps({"error": str(error)}), flush=True)
            except Exception:
                print(
                    json.dumps(
                        {"error": "Writer document unavailable; result retained for review"}
                    ),
                    flush=True,
                )
    finally:
        # Remove only our private acceptor, leaving all documents/office running.
        try:
            desktop.getComponents()
            subprocess.run(
                command + ["--unaccept=" + accept],
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


if __name__ == "__main__":
    try:
        serve()
    except Exception:
        print(json.dumps({"error": "LibreOffice Python UNO support is unavailable"}), flush=True)
