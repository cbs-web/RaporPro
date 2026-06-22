import datetime
import functools
import os
import sys
import threading
import time
import traceback
from contextlib import contextmanager


APP_DIR = os.path.dirname(os.path.abspath(__file__))
PERF_LOG_PATH = os.path.join(APP_DIR, "logs", "performance.log")
ERROR_LOG_PATH = os.path.join(APP_DIR, "logs", "error.log")
_PERF_LOCK = threading.Lock()
_ERROR_LOCK = threading.Lock()


def perf_log(name, seconds=None, detail=""):
    try:
        os.makedirs(os.path.dirname(PERF_LOG_PATH), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = "" if seconds is None else f"{seconds:.4f}s"
        detail = str(detail or "").replace("\n", " ").replace("\r", " ")
        with _PERF_LOCK:
            with open(PERF_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{stamp}\t{name}\t{elapsed}\t{detail}\n")
    except Exception:
        pass


@contextmanager
def perf_timer(name, detail=""):
    start = time.perf_counter()
    try:
        yield
    finally:
        perf_log(name, time.perf_counter() - start, detail)


def perf_tracked(name=None):
    def decorator(func):
        label = name or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with perf_timer(label):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def log_exception(name, exc_type=None, exc_value=None, exc_tb=None):
    try:
        if exc_type is None and exc_value is not None:
            exc_type = type(exc_value)
        if exc_type is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
        os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        with _ERROR_LOCK:
            with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n[{stamp}] {name}\n{formatted}\n")
    except Exception:
        pass


def install_exception_logging():
    original_hook = sys.excepthook

    def excepthook(exc_type, exc_value, exc_tb):
        log_exception("sys.excepthook", exc_type, exc_value, exc_tb)
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        original_thread_hook = threading.excepthook

        def thread_hook(args):
            log_exception(f"thread:{getattr(args.thread, 'name', '')}", args.exc_type, args.exc_value, args.exc_traceback)
            original_thread_hook(args)

        threading.excepthook = thread_hook
