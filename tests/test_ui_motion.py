# Dosya: RaporPro/tests/test_ui_motion.py

import tkinter as tk

import pytest

from ui_motion import (
    UIMotionMixin,
    blend_hex,
    clamp01,
    ease_in_out_cubic,
    ease_out_cubic,
    toplevel_hareketi_hazirla,
)


class _FakeScheduler:
    def __init__(self):
        self.jobs = {}
        self.cancelled = []
        self.counter = 0

    def winfo_exists(self):
        return True

    def after(self, _delay, callback):
        self.counter += 1
        self.jobs[self.counter] = callback
        return self.counter

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)
        self.jobs.pop(after_id, None)


class _MotionHost(UIMotionMixin):
    def __init__(self, enabled=True):
        self.root = _FakeScheduler()
        self.ui_motion_setup(enabled=enabled)


def test_motion_easing_sinirlari_korur():
    assert clamp01(-2) == 0
    assert clamp01(2) == 1
    assert ease_out_cubic(0) == 0
    assert ease_out_cubic(1) == 1
    assert ease_in_out_cubic(0) == 0
    assert ease_in_out_cubic(1) == 1
    assert ease_in_out_cubic(0.5) == pytest.approx(0.5)


def test_motion_renkleri_duzgun_karistirir():
    assert blend_hex("#000000", "#FFFFFF", 0) == "#000000"
    assert blend_hex("#000000", "#FFFFFF", 1) == "#FFFFFF"
    assert blend_hex("#000000", "#FFFFFF", 0.5) == "#808080"
    assert blend_hex("#0F766E", "#FFFFFF", 0.25) == "#4B9892"


def test_motion_kapaliyken_deger_aninda_tamamlanir():
    host = _MotionHost(enabled=False)
    values = []
    completed = []

    result = host.ui_motion_tween(
        "instant",
        1,
        9,
        values.append,
        complete=lambda: completed.append(True),
    )

    assert result is None
    assert values == [9]
    assert completed == [True]
    assert host.root.jobs == {}


def test_motion_ayni_anahtardaki_onceki_zamanlayiciyi_iptal_eder():
    host = _MotionHost()
    host.ui_motion_tween("shared", 0, 1, lambda _value: None)
    first_job = next(iter(host.root.jobs))

    host.ui_motion_tween("shared", 1, 2, lambda _value: None)

    assert first_job in host.root.cancelled
    assert len(host.root.jobs) == 1


def test_saydamlik_desteklenmezse_pencere_guvenle_kapanir():
    host = _MotionHost()
    finished = []

    class Window:
        def winfo_exists(self):
            return True

        def attributes(self, *_args):
            raise tk.TclError("alpha unsupported")

    host.ui_motion_window_close(Window(), callback=lambda: finished.append(True))

    assert finished == [True]


def test_hazirlanan_pencerede_destroy_cikis_gecisini_kullanir():
    host = _MotionHost(enabled=False)

    class Window:
        def __init__(self):
            self.master = host.root
            self.destroyed = 0
            self.protocol_callback = None

        def winfo_exists(self):
            return True

        def attributes(self, *_args):
            return 1.0

        def after_idle(self, callback):
            callback()

        def protocol(self, _name, callback):
            self.protocol_callback = callback

        def destroy(self):
            self.destroyed += 1

    window = Window()
    toplevel_hareketi_hazirla(window, host.root)
    window.destroy()

    assert window.destroyed == 1
    assert callable(window.protocol_callback)
