"""Cross-platform, timeout-bounded helpers for subprocess pipes."""

from __future__ import annotations

import queue
import threading
from typing import TextIO


def readline_with_timeout(stream: TextIO, timeout: float) -> str | None:
    """Read one line without relying on POSIX ``select`` for pipe handles.

    Windows cannot use ``select.select`` with anonymous subprocess pipes.  A
    daemon reader lets both platforms enforce the same wall-clock timeout.  A
    timed-out caller must terminate the owning process so the reader is
    released and no second reader is started on the same stream.
    """

    output: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            output.put(stream.readline())
        except BaseException as exc:  # pragma: no cover - platform pipe failures
            output.put(exc)

    thread = threading.Thread(target=read, name="nexus-pipe-reader", daemon=True)
    thread.start()
    try:
        value = output.get(timeout=max(0.01, float(timeout)))
    except queue.Empty:
        return None
    if isinstance(value, BaseException):
        raise OSError(str(value)) from value
    return value
