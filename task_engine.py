# Dosya: RaporPro/task_engine.py
from __future__ import annotations

import itertools
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

from performans import log_exception, perf_log


class TaskCancelledError(RuntimeError):
    """Kullanici tarafindan iptal edilen ortak arka plan gorevini belirtir."""


@dataclass(frozen=True)
class TaskInfo:
    task_id: int
    name: str
    state: str
    completed: float = 0
    total: float = 0
    message: str = ""
    elapsed: float = 0
    cancellable: bool = True
    error: str = ""


@dataclass
class TaskSnapshot:
    active_count: int
    completed_count: int
    failed_count: int
    last_task: str = ""
    cancelled_count: int = 0
    active_tasks: tuple[TaskInfo, ...] = ()


class TaskContext:
    """Worker fonksiyonlarina ortak ilerleme ve iptal denetimi saglar."""

    def __init__(self, task_id: int, progress_callback: Callable, cancellable: bool = True):
        self.task_id = task_id
        self._cancel_event = threading.Event()
        self._progress_callback = progress_callback
        self.cancellable = bool(cancellable)

    @property
    def cancelled(self):
        return self._cancel_event.is_set()

    def cancel(self):
        if self.cancellable:
            self._cancel_event.set()

    def check_cancelled(self):
        if self.cancelled:
            raise TaskCancelledError("Gorev kullanici tarafindan iptal edildi.")

    def report(self, completed=None, total=None, message=""):
        self._progress_callback(
            self.task_id,
            completed=completed,
            total=total,
            message=message,
        )


@dataclass
class TaskHandle:
    task_id: int
    name: str
    future: Any
    started_at: float
    context: TaskContext
    state: str = "queued"
    completed: float = 0
    total: float = 0
    message: str = ""
    finished_at: float = 0
    error: str = ""
    resource: str = ""

    @property
    def cancellable(self):
        return self.context.cancellable

    def cancel(self):
        self.context.cancel()
        try:
            self.future.cancel()
        except Exception:
            pass
        return True


class TkTaskEngine:
    """Tkinter arayuzunu kilitlemeden arka plan isleri calistiran ortak motor."""

    def __init__(
        self,
        root,
        status_callback: Optional[Callable[[str, str], None]] = None,
        state_callback: Optional[Callable[[TaskSnapshot], None]] = None,
        max_workers: int = 2,
        log_failures: bool = True,
        history_limit: int = 30,
    ):
        self.root = root
        self.status_callback = status_callback
        self.state_callback = state_callback
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="RaporProTask")
        self._counter = itertools.count(1)
        self._lock = threading.Lock()
        self._active = {}
        self._history = []
        self._resource_locks = {}
        self._completed = 0
        self._failed = 0
        self._cancelled = 0
        self._closed = False
        self.log_failures = bool(log_failures)
        self.history_limit = max(5, int(history_limit))

    def _handle_info(self, handle, now=None):
        now = now or time.perf_counter()
        end = handle.finished_at or now
        return TaskInfo(
            task_id=handle.task_id,
            name=handle.name,
            state=handle.state,
            completed=handle.completed,
            total=handle.total,
            message=handle.message,
            elapsed=max(0, end - handle.started_at),
            cancellable=handle.cancellable and handle.state in {"queued", "waiting", "running", "cancelling"},
            error=handle.error,
        )

    def snapshot(self, last_task: str = ""):
        with self._lock:
            active_tasks = tuple(
                self._handle_info(handle)
                for handle in sorted(self._active.values(), key=lambda item: item.task_id)
            )
            return TaskSnapshot(
                active_count=len(active_tasks),
                completed_count=self._completed,
                failed_count=self._failed,
                last_task=last_task,
                cancelled_count=self._cancelled,
                active_tasks=active_tasks,
            )

    def list_tasks(self, include_finished=True):
        with self._lock:
            handles = list(self._active.values())
            if include_finished:
                handles.extend(self._history)
            return [
                self._handle_info(handle)
                for handle in sorted(handles, key=lambda item: item.task_id, reverse=True)
            ]

    def active_task_names(self):
        with self._lock:
            return [handle.name for handle in self._active.values()]

    def cancel(self, task_id):
        with self._lock:
            handle = self._active.get(int(task_id))
            if handle is None or not handle.cancellable:
                return False
            handle.state = "cancelling"
            handle.message = "Iptal istegi alindi"
        handle.cancel()
        self._notify_state(handle.name)
        return True

    def cancel_all(self):
        with self._lock:
            task_ids = [
                task_id
                for task_id, handle in self._active.items()
                if handle.cancellable
            ]
        return sum(1 for task_id in task_ids if self.cancel(task_id))

    def _resource_lock(self, name):
        if not name:
            return None
        with self._lock:
            lock = self._resource_locks.get(name)
            if lock is None:
                lock = threading.Lock()
                self._resource_locks[name] = lock
            return lock

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

    def _progress_update(self, task_id, completed=None, total=None, message=""):
        with self._lock:
            handle = self._active.get(task_id)
            if handle is None:
                return
            if completed is not None:
                try:
                    handle.completed = float(completed)
                except (TypeError, ValueError):
                    pass
            if total is not None:
                try:
                    handle.total = max(0, float(total))
                except (TypeError, ValueError):
                    pass
            if message:
                handle.message = str(message)
        self._notify_state(handle.name)

    def _archive_handle(self, task_id, state, error=""):
        with self._lock:
            handle = self._active.pop(task_id, None)
            if handle is None:
                return None
            handle.state = state
            handle.error = str(error or "")
            handle.finished_at = time.perf_counter()
            self._history.insert(0, handle)
            del self._history[self.history_limit:]
            if state == "completed":
                self._completed += 1
            elif state == "cancelled":
                self._cancelled += 1
            else:
                self._failed += 1
            return handle

    def run(
        self,
        name: str,
        func: Callable,
        *args,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
        status_start: Optional[str] = None,
        status_success: Optional[str] = None,
        status_error: Optional[str] = None,
        status_cancel: Optional[str] = None,
        with_context: bool = False,
        cancellable: Optional[bool] = None,
        resource: Optional[str] = None,
        **kwargs,
    ) -> TaskHandle:
        if self._closed:
            raise RuntimeError("Task engine kapali")

        task_id = next(self._counter)
        started_at = time.perf_counter()
        task_name = str(name or f"Gorev {task_id}")
        effective_cancellable = bool(with_context) if cancellable is None else bool(cancellable)
        context = TaskContext(task_id, self._progress_update, cancellable=effective_cancellable)
        start_gate = threading.Event()
        resource_name = str(resource or "")
        resource_lock = self._resource_lock(resource_name)

        def worker():
            start_gate.wait()
            context.check_cancelled()
            if resource_lock is not None:
                self._progress_update(task_id, message=f"Kaynak bekleniyor: {resource_name}")
                with self._lock:
                    handle = self._active.get(task_id)
                    if handle is not None:
                        handle.state = "waiting"
                resource_lock.acquire()
            try:
                context.check_cancelled()
                with self._lock:
                    handle = self._active.get(task_id)
                    if handle is not None:
                        handle.state = "running"
                        if not handle.message or handle.message.startswith("Kaynak bekleniyor"):
                            handle.message = "Calisiyor"
                self._notify_state(task_name)
                if with_context:
                    return func(*args, task_context=context, **kwargs)
                return func(*args, **kwargs)
            except TaskCancelledError:
                raise
            except Exception as exc:
                if self.log_failures:
                    log_exception(f"task_engine.{task_name}", exc_value=exc)
                raise
            finally:
                if resource_lock is not None:
                    resource_lock.release()

        future = self.executor.submit(worker)
        handle = TaskHandle(
            task_id=task_id,
            name=task_name,
            future=future,
            started_at=started_at,
            context=context,
            resource=resource_name,
        )
        with self._lock:
            self._active[task_id] = handle
        start_gate.set()

        self._set_status(status_start or f"Arka plan gorevi basladi: {task_name}", "info")
        self._notify_state(task_name)

        def finish(done_future):
            elapsed = time.perf_counter() - started_at
            try:
                result = done_future.result()
            except (TaskCancelledError, CancelledError):
                perf_log(f"task.{task_name}", elapsed, "cancelled")
                self._archive_handle(task_id, "cancelled")

                def cancelled_ui():
                    if self.status_callback:
                        self.status_callback(status_cancel or f"Arka plan gorevi iptal edildi: {task_name}", "warning")
                    if on_cancel:
                        on_cancel()
                    if on_done:
                        on_done()
                    if self.state_callback:
                        self.state_callback(self.snapshot(task_name))

                self._ui_call(cancelled_ui)
                return
            except Exception as exc:
                perf_log(f"task.{task_name}", elapsed, "error")
                self._archive_handle(task_id, "failed", error=exc)

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
            self._archive_handle(task_id, "completed")

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


__all__ = [
    "TaskCancelledError",
    "TaskContext",
    "TaskHandle",
    "TaskInfo",
    "TaskSnapshot",
    "TkTaskEngine",
]
