# Dosya: RaporPro/task_engine.py
from __future__ import annotations

import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

from performans import log_exception, perf_log


@dataclass
class TaskSnapshot:
    active_count: int
    completed_count: int
    failed_count: int
    last_task: str = ""


@dataclass
class TaskHandle:
    task_id: int
    name: str
    future: Any
    started_at: float


class TkTaskEngine:
    """Tkinter arayuzunu kilitlemeden arka plan isleri calistiran ortak motor."""

    def __init__(
        self,
        root,
        status_callback: Optional[Callable[[str, str], None]] = None,
        state_callback: Optional[Callable[[TaskSnapshot], None]] = None,
        max_workers: int = 2,
    ):
        self.root = root
        self.status_callback = status_callback
        self.state_callback = state_callback
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="RaporProTask")
        self._counter = itertools.count(1)
        self._lock = threading.Lock()
        self._active = {}
        self._completed = 0
        self._failed = 0
        self._closed = False

    def snapshot(self, last_task: str = ""):
        with self._lock:
            return TaskSnapshot(
                active_count=len(self._active),
                completed_count=self._completed,
                failed_count=self._failed,
                last_task=last_task,
            )

    def _ui_call(self, func, *args, **kwargs):
        try:
            if self._closed:
                return
            self.root.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def _set_status(self, message, level="info"):
        if self.status_callback:
            self._ui_call(self.status_callback, message, level)

    def _notify_state(self, last_task=""):
        if self.state_callback:
            self._ui_call(self.state_callback, self.snapshot(last_task))

    def run(
        self,
        name: str,
        func: Callable,
        *args,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
        status_start: Optional[str] = None,
        status_success: Optional[str] = None,
        status_error: Optional[str] = None,
        **kwargs,
    ) -> TaskHandle:
        if self._closed:
            raise RuntimeError("Task engine kapali")

        task_id = next(self._counter)
        started_at = time.perf_counter()
        task_name = str(name or f"Gorev {task_id}")

        def worker():
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                log_exception(f"task_engine.{task_name}", exc_value=exc)
                raise

        future = self.executor.submit(worker)
        handle = TaskHandle(task_id=task_id, name=task_name, future=future, started_at=started_at)
        with self._lock:
            self._active[task_id] = handle

        self._set_status(status_start or f"Arka plan gorevi basladi: {task_name}", "info")
        self._notify_state(task_name)

        def finish(done_future):
            elapsed = time.perf_counter() - started_at
            try:
                result = done_future.result()
            except Exception as exc:
                perf_log(f"task.{task_name}", elapsed, "error")
                with self._lock:
                    self._active.pop(task_id, None)
                    self._failed += 1

                def error_ui(exc=exc):
                    if self.status_callback and status_error:
                        self.status_callback(status_error.format(error=exc), "error")
                    elif self.status_callback:
                        self.status_callback(f"Arka plan gorevi hata verdi: {task_name} - {exc}", "error")
                    if on_error:
                        on_error(exc)
                    if on_done:
                        on_done()
                    if self.state_callback:
                        self.state_callback(self.snapshot(task_name))

                self._ui_call(error_ui)
                return

            perf_log(f"task.{task_name}", elapsed, "success")
            with self._lock:
                self._active.pop(task_id, None)
                self._completed += 1

            def success_ui():
                if self.status_callback and status_success:
                    self.status_callback(status_success, "success")
                elif self.status_callback:
                    self.status_callback(f"Arka plan gorevi tamamlandi: {task_name}", "success")
                if on_success:
                    on_success(result)
                if on_done:
                    on_done()
                if self.state_callback:
                    self.state_callback(self.snapshot(task_name))

            self._ui_call(success_ui)

        future.add_done_callback(finish)
        return handle

    def shutdown(self, wait: bool = False):
        self._closed = True
        try:
            self.executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            self.executor.shutdown(wait=wait)
