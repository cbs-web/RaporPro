# Dosya: RaporPro/ui_hidrojeoloji.py
import tkinter as tk
from tkinter import ttk

from hidrojeoloji_raporu import (
    DERE_DURUM_SECENEKLERI,
    TASKIN_DURUM_SECENEKLERI,
    YASS_DURUM_SECENEKLERI,
    YON_SECENEKLERI,
    hidrojeoloji_varsayilanlari,
)
from sabitler import SPACE_SM, SPACE_XS
from widgets import UndoRedoEntry


class HidrojeolojiUIMixin:
    def hidrojeoloji_paneli_olustur(self, parent, row=2):
        panel = ttk.LabelFrame(parent, text="Hidrojeoloji", padding=(14, 10))
        panel.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(SPACE_SM, 0))
        for column in (1, 3, 5):
            panel.columnconfigure(column, weight=1)

        self.e_hidrojeoloji = {}
        navigation = []

        def label(text, grid_row, column):
            ttk.Label(panel, text=text).grid(
                row=grid_row,
                column=column,
                sticky="e",
                padx=(SPACE_SM if column else 0, SPACE_XS),
                pady=SPACE_XS,
            )

        def combo(key, values, grid_row, column, width=20):
            widget = ttk.Combobox(panel, values=values, state="readonly", width=width)
            widget.grid(row=grid_row, column=column, sticky="ew", pady=SPACE_XS)
            self.e_hidrojeoloji[key] = widget
            navigation.append(widget)
            return widget

        def entry(key, grid_row, column, width=18):
            widget = UndoRedoEntry(panel, width=width)
            widget.grid(row=grid_row, column=column, sticky="ew", pady=SPACE_XS)
            self.e_hidrojeoloji[key] = widget
            navigation.append(widget)
            return widget

        label("YASS değerlendirmesi", 0, 0)
        combo("yass_durumu", YASS_DURUM_SECENEKLERI, 0, 1)
        label("Denize uzaklık (m)", 0, 2)
        entry("deniz_mesafe", 0, 3)
        label("Taşkın riski", 0, 4)
        combo("taskin_riski", TASKIN_DURUM_SECENEKLERI, 0, 5)

        label("Akar dere", 1, 0)
        akar_combo = combo("akar_dere", DERE_DURUM_SECENEKLERI, 1, 1)
        label("Mesafe (m)", 1, 2)
        entry("akar_dere_mesafe", 1, 3)
        label("Yön", 1, 4)
        combo("akar_dere_yon", YON_SECENEKLERI, 1, 5)

        label("Kuru dere", 2, 0)
        kuru_combo = combo("kuru_dere", DERE_DURUM_SECENEKLERI, 2, 1)
        label("Mesafe (m)", 2, 2)
        entry("kuru_dere_mesafe", 2, 3)
        label("Yön", 2, 4)
        combo("kuru_dere_yon", YON_SECENEKLERI, 2, 5)

        label("Ek açıklama", 3, 0)
        note = entry("ek_aciklama", 3, 1, width=70)
        note.grid(columnspan=5)

        defaults = hidrojeoloji_varsayilanlari()
        for key, widget in self.e_hidrojeoloji.items():
            value = defaults.get(key, "")
            if isinstance(widget, ttk.Combobox):
                widget.set(value)
            elif value:
                widget.insert(0, value)
        akar_combo.bind(
            "<<ComboboxSelected>>",
            self.hidrojeoloji_dere_alanlarini_guncelle,
            add="+",
        )
        kuru_combo.bind(
            "<<ComboboxSelected>>",
            self.hidrojeoloji_dere_alanlarini_guncelle,
            add="+",
        )
        self.hidrojeoloji_dere_alanlarini_guncelle()
        self.hidrojeoloji_navigasyon = navigation
        return navigation

    def hidrojeoloji_dere_alanlarini_guncelle(self, event=None):
        widgets = getattr(self, "e_hidrojeoloji", {})
        for prefix in ("akar_dere", "kuru_dere"):
            active = widgets.get(prefix) is not None and widgets[prefix].get() == "Var"
            distance = widgets.get(f"{prefix}_mesafe")
            direction = widgets.get(f"{prefix}_yon")
            if distance is not None:
                distance.configure(state="normal" if active else "disabled")
            if direction is not None:
                direction.configure(state="readonly" if active else "disabled")

    def hidrojeoloji_verisini_topla(self):
        current = self.veri.setdefault("arazi", {}).get("hidrojeoloji", {})
        current = dict(current) if isinstance(current, dict) else {}
        for key, widget in getattr(self, "e_hidrojeoloji", {}).items():
            current[key] = widget.get().strip()
        self.veri["arazi"]["hidrojeoloji"] = current
        return current

    def hidrojeoloji_verisini_yukle(self):
        defaults = hidrojeoloji_varsayilanlari()
        source = self.veri.get("arazi", {}).get("hidrojeoloji", {})
        source = source if isinstance(source, dict) else {}
        for prefix in ("akar_dere", "kuru_dere"):
            distance = getattr(self, "e_hidrojeoloji", {}).get(f"{prefix}_mesafe")
            direction = getattr(self, "e_hidrojeoloji", {}).get(f"{prefix}_yon")
            if distance is not None:
                distance.configure(state="normal")
            if direction is not None:
                direction.configure(state="readonly")
        for key, widget in getattr(self, "e_hidrojeoloji", {}).items():
            value = source.get(key, defaults.get(key, ""))
            if isinstance(widget, ttk.Combobox):
                widget.set(value)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, value)
        self.hidrojeoloji_dere_alanlarini_guncelle()

    def hidrojeoloji_form_durumu(self):
        widgets = getattr(self, "e_hidrojeoloji", {})
        values = {key: widget.get().strip() for key, widget in widgets.items()}
        warnings = []
        numeric_keys = ("deniz_mesafe", "akar_dere_mesafe", "kuru_dere_mesafe")
        invalid = []
        for key in numeric_keys:
            value = values.get(key, "")
            if not value:
                continue
            if not self._form_sayi_mi(value) or float(value.replace(",", ".")) < 0:
                invalid.append(key)
        if invalid:
            warnings.append("Hidrojeoloji mesafelerini kontrol edin")

        for key in numeric_keys:
            widget = widgets.get(key)
            if widget is not None:
                widget.configure(style="Warning.TEntry" if key in invalid else "Valid.TEntry")

        meaningful = 0
        defaults = hidrojeoloji_varsayilanlari()
        for key, value in values.items():
            if value and value != defaults.get(key, ""):
                meaningful += 1
        return meaningful, len(values), warnings


__all__ = ["HidrojeolojiUIMixin"]
