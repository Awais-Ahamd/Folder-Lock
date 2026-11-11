"""Run engine work off the GUI thread and deliver results back on it."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Any, Callable

from utils.error_handler import OperationCancelled, friendly_message


class TaskRunner:
    """One background task at a time. Callbacks always run on the Tk main thread."""

    def __init__(self, root: tk.Misc):
        self._root = root
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._queue: queue.Queue = queue.Queue()

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self, fn: Callable[[Callable, Callable[[], bool]], Any], *,
            on_progress: Callable[[str, int, int], None] | None = None,
            on_success: Callable[[Any], None] | None = None,
            on_error: Callable[[BaseException, str], None] | None = None) -> None:
        if self.busy:
            raise RuntimeError("a task is already running")
        self._cancel = threading.Event()
        q: queue.Queue = queue.Queue()
        self._queue = q
        cancel_flag = self._cancel

        def progress(phase: str, done: int, total: int) -> None:
            q.put(("progress", (phase, done, total)))

        def target() -> None:
            try:
                q.put(("ok", fn(progress, cancel_flag.is_set)))
            except BaseException as exc:  # noqa: BLE001 - everything is reported to the UI
                q.put(("err", exc))

        self._thread = threading.Thread(target=target, daemon=True, name="folderlock-worker")
        self._thread.start()
        self._poll(q, on_progress, on_success, on_error)

    def _poll(self, q, on_progress, on_success, on_error) -> None:
        last_progress = None
        finished = None
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "progress":
                    last_progress = payload
                else:
                    finished = (kind, payload)
                    break
        except queue.Empty:
            pass
        try:
            if last_progress and on_progress:
                on_progress(*last_progress)
            if finished:
                kind, payload = finished
                if kind == "ok":
                    if on_success:
                        on_success(payload)
                elif on_error:
                    on_error(payload, friendly_message(payload))
                return
            self._root.after(60, self._poll, q, on_progress, on_success, on_error)
        except tk.TclError:
            return           # the screen was closed while the task ran

    def wait(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


def is_cancel(exc: BaseException) -> bool:
    return isinstance(exc, OperationCancelled)
