import threading
from queue import Full

import pytest

from turbo_whisper.sessions import SerialWorker


def test_serial_worker_orders_jobs_bounds_backlog_and_prunes_cancelled_jobs():
    worker = SerialWorker(capacity=2)
    entered, release = threading.Event(), threading.Event()
    results = []

    def blocked():
        entered.set()
        assert release.wait(2)
        results.append(1)

    try:
        first = worker.submit(blocked)
        assert entered.wait(1)
        cancelled = worker.submit(lambda: results.append("cancelled"))
        last = worker.submit(lambda: results.append(2))
        with pytest.raises(Full):
            worker.submit(lambda: None)
        assert cancelled.cancel()
        final = worker.submit(lambda: results.append(3))
        release.set()
        first.result(timeout=1)
        last.result(timeout=1)
        final.result(timeout=1)
        assert results == [1, 2, 3]
    finally:
        release.set()
        worker.shutdown()
        worker.thread.join(timeout=2)
        assert not worker.thread.is_alive()


def test_worker_failure_does_not_prevent_next_session():
    worker = SerialWorker()

    def fail():
        raise RuntimeError("Synthetic inference failure")

    try:
        failed = worker.submit(fail)
        following = worker.submit(lambda: "next")
        with pytest.raises(RuntimeError, match="Synthetic"):
            failed.result(timeout=1)
        assert following.result(timeout=1) == "next"
    finally:
        worker.shutdown()
        worker.thread.join(timeout=1)


def test_shutdown_cancels_queued_jobs_and_refuses_new_work():
    worker = SerialWorker()
    entered, release = threading.Event(), threading.Event()

    def blocked():
        entered.set()
        assert release.wait(2)

    try:
        first = worker.submit(blocked)
        assert entered.wait(1)
        queued = worker.submit(lambda: pytest.fail("Cancelled job ran"))
        worker.shutdown()
        assert queued.cancelled()
        with pytest.raises(RuntimeError, match="stopped"):
            worker.submit(lambda: None)
        release.set()
        first.result(timeout=1)
    finally:
        release.set()
        worker.shutdown()
        worker.thread.join(timeout=1)
