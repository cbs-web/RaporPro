# Dosya: RaporPro/ui_motion.py
"""Tkinter arayüzü için hafif, iptal edilebilir hareket yardımcıları."""

from __future__ import annotations

import os
import time
import tkinter as tk


MOTION_FRAME_MS = 16
MOTION_FAST_MS = 120
MOTION_NORMAL_MS = 180
MOTION_SLOW_MS = 240


def clamp01(value):
    return max(0.0, min(1.0, float(value)))


def ease_out_cubic(value):
    value = clamp01(value)
    return 1.0 - (1.0 - value) ** 3


def ease_in_out_cubic(value):
    value = clamp01(value)
    if value < 0.5:
        return 4.0 * value**3
    return 1.0 - ((-2.0 * value + 2.0) ** 3) / 2.0


def _hex_rgb(value):
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        raise ValueError(f"Geçersiz renk: {value}")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def blend_hex(start, end, progress):
    """İki HEX rengi verilen ilerleme oranında karıştır."""
    left = _hex_rgb(start)
    right = _hex_rgb(end)
    progress = clamp01(progress)
    rgb = tuple(round(a + (b - a) * progress) for a, b in zip(left, right))
    return "#" + "".join(f"{part:02X}" for part in rgb)


def _truthy(value, default=True):
    if value is None:
        return bool(default)
    return str(value).strip().casefold() not in {"", "0", "false", "hayır", "hayir", "off", "no"}


class UIMotionMixin:
    """Ortak arayüz hareketlerini tek bir güvenli zamanlayıcıdan yönetir."""

    def ui_motion_setup(self, enabled=True):
        self.ui_motion_enabled = bool(enabled)
        self._ui_motion_jobs = {}
        self._ui_motion_tokens = {}
        root = getattr(self, "root", None)
        if root is not None:
            root._ui_motion_controller = self

    def ui_motion_apply_settings(self):
        settings = getattr(self, "veri", {}).get("ayarlar", {}) if isinstance(getattr(self, "veri", None), dict) else {}
        self.ui_motion_set_enabled(_truthy(settings.get("ui_animasyon", "1")))

    def ui_motion_set_enabled(self, enabled):
        self.ui_motion_enabled = bool(enabled)
        if not self.ui_motion_enabled:
            self.ui_motion_shutdown()
            for window in (getattr(self, "root", None),):
                if window is not None:
                    self._ui_motion_make_opaque(window)

    def ui_motion_cancel(self, key):
        job = getattr(self, "_ui_motion_jobs", {}).pop(key, None)
        getattr(self, "_ui_motion_tokens", {}).pop(key, None)
        if not job:
            return
        scheduler, after_id = job
        try:
            scheduler.after_cancel(after_id)
        except Exception:
            pass

    def ui_motion_shutdown(self):
        for key in list(getattr(self, "_ui_motion_jobs", {})):
            self.ui_motion_cancel(key)

    @staticmethod
    def _ui_widget_exists(widget):
        try:
            return bool(widget.winfo_exists())
        except Exception:
            return False

    @staticmethod
    def _ui_motion_windows_layered(window, enabled):
        """Windows'ta fade için kullanılan katmanlı pencere stilini değiştir."""
        if os.name != "nt":
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = int(window.winfo_id())
            parent = int(user32.GetParent(hwnd))
            if parent:
                hwnd = parent
            gwl_exstyle = -20
            ws_ex_layered = 0x00080000
            style = int(user32.GetWindowLongW(hwnd, gwl_exstyle))
            target = style | ws_ex_layered if enabled else style & ~ws_ex_layered
            if target != style:
                user32.SetWindowLongW(hwnd, gwl_exstyle, target)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            pass

    def _ui_motion_make_opaque(self, window):
        try:
            window.attributes("-alpha", 1.0)
        except Exception:
            return
        self._ui_motion_windows_layered(window, False)

    def ui_motion_tween(
        self,
        key,
        start,
        end,
        update,
        *,
        duration=MOTION_NORMAL_MS,
        easing=ease_out_cubic,
        complete=None,
        scheduler=None,
    ):
        """Sayısal bir değeri 60 FPS hedefiyle güvenli biçimde değiştir."""
        scheduler = scheduler or getattr(self, "root", None)
        self.ui_motion_cancel(key)
        if scheduler is None or not self._ui_widget_exists(scheduler):
            return None
        if not getattr(self, "ui_motion_enabled", True) or int(duration) <= 0:
            update(end)
            if callable(complete):
                complete()
            return None

        token = object()
        self._ui_motion_tokens[key] = token
        started = time.perf_counter()
        delta = float(end) - float(start)

        def tick():
            if getattr(self, "_ui_motion_tokens", {}).get(key) is not token:
                return
            if not self._ui_widget_exists(scheduler):
                self._ui_motion_jobs.pop(key, None)
                self._ui_motion_tokens.pop(key, None)
                return
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            progress = clamp01(elapsed_ms / max(1, int(duration)))
            try:
                update(float(start) + delta * easing(progress))
            except (tk.TclError, RuntimeError):
                self._ui_motion_jobs.pop(key, None)
                self._ui_motion_tokens.pop(key, None)
                return
            if progress >= 1.0:
                self._ui_motion_jobs.pop(key, None)
                self._ui_motion_tokens.pop(key, None)
                if callable(complete):
                    complete()
                return
            try:
                after_id = scheduler.after(MOTION_FRAME_MS, tick)
            except (tk.TclError, RuntimeError):
                self._ui_motion_jobs.pop(key, None)
                self._ui_motion_tokens.pop(key, None)
                return
            self._ui_motion_jobs[key] = (scheduler, after_id)

        after_id = scheduler.after(0, tick)
        self._ui_motion_jobs[key] = (scheduler, after_id)
        return key

    def _ui_color_hex(self, widget, option):
        value = widget.cget(option)
        try:
            _hex_rgb(value)
            return str(value)
        except (ValueError, tk.TclError):
            red, green, blue = widget.winfo_rgb(value)
            return f"#{red // 257:02X}{green // 257:02X}{blue // 257:02X}"

    def ui_motion_color(self, widget, option, target, *, key=None, duration=MOTION_FAST_MS, complete=None):
        if not self._ui_widget_exists(widget):
            return None
        try:
            start = self._ui_color_hex(widget, option)
            _hex_rgb(target)
        except (ValueError, tk.TclError):
            try:
                widget.configure(**{option: target})
            except Exception:
                pass
            return None
        motion_key = key or f"color:{id(widget)}:{option}"

        def update(progress):
            widget.configure(**{option: blend_hex(start, target, progress)})

        return self.ui_motion_tween(
            motion_key,
            0.0,
            1.0,
            update,
            duration=duration,
            complete=complete,
            scheduler=getattr(self, "root", widget),
        )

    def ui_motion_progress(self, widget, target, *, key=None, duration=MOTION_SLOW_MS):
        try:
            start = float(widget["value"])
        except Exception:
            start = 0.0

        def update(value):
            widget["value"] = value

        return self.ui_motion_tween(
            key or f"progress:{id(widget)}",
            start,
            float(target),
            update,
            duration=duration,
            easing=ease_in_out_cubic,
            scheduler=getattr(self, "root", widget),
        )

    def ui_motion_page_enter(self, page, distance=8, duration=MOTION_NORMAL_MS):
        if not self._ui_widget_exists(page):
            return
        try:
            page.configure(padding=(0, int(distance), 0, 0))
        except tk.TclError:
            return

        def update(value):
            page.configure(padding=(0, max(0, round(value)), 0, 0))

        self.ui_motion_tween(
            f"page:{id(page)}",
            float(distance),
            0.0,
            update,
            duration=duration,
            scheduler=getattr(self, "root", page),
        )

    def ui_motion_window_enter(self, window, duration=MOTION_NORMAL_MS):
        if not self._ui_widget_exists(window) or getattr(window, "_ui_motion_entered", False):
            return
        window._ui_motion_entered = True
        if not getattr(self, "ui_motion_enabled", True):
            return
        try:
            window.attributes("-alpha", 0.0)
        except tk.TclError:
            return

        def begin():
            if not self._ui_widget_exists(window):
                return
            self.ui_motion_tween(
                f"window:{id(window)}",
                0.0,
                1.0,
                lambda value: window.attributes("-alpha", clamp01(value)),
                duration=duration,
                complete=lambda: self._ui_motion_make_opaque(window),
                scheduler=window,
            )

        try:
            window.after_idle(begin)
        except tk.TclError:
            pass

    def ui_motion_window_close(self, window, *, callback=None, duration=MOTION_FAST_MS):
        if not self._ui_widget_exists(window) or getattr(window, "_ui_motion_closing", False):
            return
        window._ui_motion_closing = True

        def finish():
            if callable(callback):
                callback()
            elif self._ui_widget_exists(window):
                window.destroy()

        if not getattr(self, "ui_motion_enabled", True):
            finish()
            return
        self._ui_motion_windows_layered(window, True)
        try:
            start = float(window.attributes("-alpha"))
            window.attributes("-alpha", start)
        except (tk.TclError, TypeError, ValueError):
            finish()
            return
        self.ui_motion_tween(
            f"window:{id(window)}",
            start,
            0.0,
            lambda value: window.attributes("-alpha", clamp01(value)),
            duration=duration,
            complete=finish,
            scheduler=window,
        )

    def ui_motion_prepare_window(self, window):
        window._ui_motion_controller = self
        self.ui_motion_window_enter(window)
        close = lambda: self.ui_motion_window_close(window)
        window._ui_motion_close = close
        try:
            window.protocol("WM_DELETE_WINDOW", close)
        except tk.TclError:
            pass
        return window

    def ui_motion_close_command(self, command):
        owner = getattr(command, "__self__", None)
        name = getattr(command, "__name__", "")
        close = getattr(owner, "_ui_motion_close", None)
        if name == "destroy" and callable(close):
            return close
        return command

    def ui_motion_bind_hover(self, widget, normal, hover, option="background"):
        if not self._ui_widget_exists(widget):
            return widget

        def enter(_event=None):
            try:
                if "state" in widget.keys() and str(widget.cget("state")) == "disabled":
                    return
            except tk.TclError:
                return
            self.ui_motion_color(
                widget,
                option,
                hover,
                key=f"hover:{id(widget)}:{option}",
            )

        def leave(_event=None):
            self.ui_motion_color(
                widget,
                option,
                normal,
                key=f"hover:{id(widget)}:{option}",
            )

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")
        return widget


__all__ = [
    "MOTION_FAST_MS",
    "MOTION_NORMAL_MS",
    "MOTION_SLOW_MS",
    "UIMotionMixin",
    "blend_hex",
    "clamp01",
    "ease_in_out_cubic",
    "ease_out_cubic",
]
