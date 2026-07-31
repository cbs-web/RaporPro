# Dosya: RaporPro/ui_rapor_bilgileri.py
"""Parsel ve Word raporu bilgileri icin proje bazli duzenleme penceresi."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import Toplevel, messagebox, ttk

from rapor_parsel_bilgileri import (
    DURUM_SECENEKLERI,
    PARSEL_TIPI_SECENEKLERI,
    rapor_bilgileri_eksikleri,
    rapor_bilgilerini_normalize_et,
)
from sabitler import (
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_BOLD,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)


class RaporBilgileriMixin:
    def rapor_bilgileri_ozeti(self):
        data = rapor_bilgilerini_normalize_et(getattr(self, "veri", {}))
        missing = rapor_bilgileri_eksikleri(getattr(self, "veri", {}))
        ready = []
        if data.get("ilgili_idare"):
            ready.append(data["ilgili_idare"])
        if data.get("rapor_tarihi"):
            ready.append(data["rapor_tarihi"])
        if data.get("plan_adi"):
            ready.append(data["plan_adi"])
        if missing:
            detail = ", ".join(missing[:3])
            if len(missing) > 3:
                detail += f" ve {len(missing) - 3} alan daha"
            return "warning", f"Parsel raporu: {len(missing)} eksik · {detail}"
        return "ok", "Parsel raporu bilgileri hazır" + (
            f" · {' · '.join(ready[:2])}" if ready else ""
        )

    def rapor_bilgileri_durum_guncelle(self):
        state, text = self.rapor_bilgileri_ozeti()
        if hasattr(self, "rapor_bilgileri_durum_var"):
            self.rapor_bilgileri_durum_var.set(text)
        if hasattr(self, "rapor_bilgileri_durum_label"):
            self.rapor_bilgileri_durum_label.configure(
                foreground=COLOR_SUCCESS if state == "ok" else COLOR_WARNING
            )
        return state, text

    def rapor_bilgileri_penceresi(self):
        current = rapor_bilgilerini_normalize_et(getattr(self, "veri", {}))
        win = Toplevel(self.root)
        self.pencere_hazirla(
            win,
            "Parsel ve Rapor Bilgileri",
            "980x760",
            (760, 560),
            modal=True,
        )
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        notebook = ttk.Notebook(win)
        notebook.grid(row=0, column=0, sticky="nsew", padx=SPACE_MD, pady=(SPACE_MD, SPACE_XS))

        tab_specs = (
            ("Genel", "general"),
            ("Parsel ve İmar", "parcel"),
        )
        forms = {}
        for title, key in tab_specs:
            tab = ttk.Frame(notebook)
            form, _canvas = self.scrollable_page(tab, padding=(16, 12))
            form.columnconfigure(1, weight=1)
            notebook.add(tab, text=title)
            forms[key] = form

        entries = {}
        text_widgets = {}

        def add_entry(form, row, label, key, width=52):
            ttk.Label(form, text=label).grid(
                row=row,
                column=0,
                sticky="e",
                padx=(0, SPACE_SM),
                pady=SPACE_XS,
            )
            entry = ttk.Entry(form, width=width)
            entry.grid(row=row, column=1, sticky="ew", pady=SPACE_XS)
            entry.insert(0, current.get(key, ""))
            entries[key] = entry
            return row + 1

        def add_combo(form, row, label, key, values):
            ttk.Label(form, text=label).grid(
                row=row,
                column=0,
                sticky="e",
                padx=(0, SPACE_SM),
                pady=SPACE_XS,
            )
            combo = ttk.Combobox(form, values=values, state="readonly")
            combo.grid(row=row, column=1, sticky="ew", pady=SPACE_XS)
            value = current.get(key, values[0])
            combo.set(value if value in values else values[0])
            entries[key] = combo
            return row + 1

        def add_text(form, row, label, key, height=3):
            ttk.Label(form, text=label).grid(
                row=row,
                column=0,
                sticky="ne",
                padx=(0, SPACE_SM),
                pady=SPACE_XS,
            )
            text = tk.Text(
                form,
                height=height,
                wrap="word",
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 10),
            )
            text.grid(row=row, column=1, sticky="ew", pady=SPACE_XS)
            text.insert("1.0", current.get(key, ""))
            text_widgets[key] = text
            return row + 1

        general = forms["general"]
        row = 0
        row = add_entry(general, row, "Proje adı", "proje_adi")
        row = add_entry(general, row, "Yapı sahibi / işveren", "yapi_sahibi")
        row = add_entry(general, row, "İlgili idare", "ilgili_idare")
        row = add_entry(general, row, "Rapor tarihi", "rapor_tarihi", width=24)
        row = add_entry(general, row, "Rapor no", "rapor_no", width=24)
        ttk.Label(
            general,
            text="Künye bilgileri ayrı tutulur; bu alanlar yalnız rapor kimliğini belirler.",
            foreground=COLOR_TEXT_MUTED,
        ).grid(row=row, column=1, sticky="w", pady=(0, SPACE_SM))

        parcel = forms["parcel"]
        row = 0
        row = add_entry(parcel, row, "Parsel alanı (m²)", "parsel_alani_m2")
        row = add_combo(parcel, row, "Parsel tipi", "parsel_tipi", PARSEL_TIPI_SECENEKLERI)
        row = add_text(parcel, row, "Yol ve cephe durumu", "yol_cepheleri")
        row = add_text(parcel, row, "Komşu parseller", "komsu_parseller")
        row = add_text(parcel, row, "Yakındaki mevcut yapılar", "mevcut_yapilar")
        row = add_text(parcel, row, "Mevcut kullanım", "mevcut_kullanim", height=2)
        row = add_entry(parcel, row, "Bitki örtüsü", "bitki_ortusu")
        row = add_text(parcel, row, "Altyapı durumu", "altyapi_durumu")
        row = add_text(parcel, row, "Drenaj durumu", "drenaj_durumu", height=2)
        row = add_text(parcel, row, "Ulaşım durumu", "ulasim_durumu", height=2)
        row = add_text(parcel, row, "Çevre ek açıklaması", "cevre_ek_aciklama")
        ttk.Separator(parcel).grid(row=row, column=0, columnspan=2, sticky="ew", pady=SPACE_SM)
        row += 1
        row = add_entry(parcel, row, "İmar planı / plan notu", "plan_adi")
        row = add_entry(parcel, row, "Plan onay tarihi", "plan_onay_tarihi")
        row = add_entry(parcel, row, "Karar no", "plan_karar_no")
        row = add_entry(parcel, row, "Planı onaylayan idare", "plan_onay_idaresi")
        row = add_combo(parcel, row, "Afete Maruz Bölge", "afete_maruz_bolge", DURUM_SECENEKLERI)
        row = add_combo(parcel, row, "Yapı yasağı", "yapi_yasagi", DURUM_SECENEKLERI)
        row = add_entry(parcel, row, "İmar belgesi ek no", "imar_ek_no")
        add_text(parcel, row, "İmar ek açıklaması", "imar_ek_aciklama")

        def kunye_degerlerini_al():
            kunye = self.veri.get("kunye", {}) if isinstance(self.veri, dict) else {}
            legacy_name = str(kunye.get("sahibi") or "").strip()
            if legacy_name:
                for key in ("proje_adi", "yapi_sahibi"):
                    entries[key].delete(0, tk.END)
                    entries[key].insert(0, legacy_name)
            ayarlar = self.veri.get("ayarlar", {}) if isinstance(self.veri, dict) else {}
            idare = str(ayarlar.get("taahhut_ilgili_idare") or "").strip()
            if idare:
                entries["ilgili_idare"].delete(0, tk.END)
                entries["ilgili_idare"].insert(0, idare)

        def save():
            updated = copy.deepcopy(current)
            for key, entry in entries.items():
                updated[key] = entry.get().strip()
            for key, text in text_widgets.items():
                value = text.get("1.0", "end-1c").strip()
                updated[key] = value
            self.veri["rapor_bilgileri"] = updated
            self.rapor_bilgileri_durum_guncelle()
            if hasattr(self, "rapor_durum_guncelle"):
                self.rapor_durum_guncelle()
            if hasattr(self, "ozet_yenile"):
                self.ozet_yenile(collect=False)
            if getattr(self, "aktif_dosya_yolu", None):
                self.veri_kaydet()
            self.set_status("Parsel ve rapor bilgileri güncellendi.", level="success")
            win.destroy()

        footer = ttk.Frame(win, padding=(SPACE_MD, SPACE_XS, SPACE_MD, SPACE_MD))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.modern_button(
            footer,
            "Künyeden Doldur",
            command=kunye_degerlerini_al,
            role="secondary",
            outline=True,
        ).grid(row=0, column=0, sticky="w")
        self.modern_button(
            footer,
            "Vazgeç",
            command=win.destroy,
            role="secondary",
            outline=True,
        ).grid(row=0, column=1, padx=(SPACE_SM, SPACE_XS))
        self.modern_button(
            footer,
            "Kaydet",
            command=save,
            role="success",
        ).grid(row=0, column=2)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.bind("<Control-s>", lambda _event: save())


__all__ = ["RaporBilgileriMixin"]
