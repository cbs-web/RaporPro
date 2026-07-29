# Dosya: RaporPro/ui_hidrojeoloji.py
import os
import tkinter as tk
from tkinter import messagebox, ttk

from hidrojeoloji_cevre import (
    CevreAnaliziHatasi,
    cevre_analizi_guncel_mi,
    cevre_analizi_kayit_ozeti,
    cevre_analizi_yap,
)
from hidrojeoloji_raporu import (
    DERE_DURUM_SECENEKLERI,
    TASKIN_DURUM_SECENEKLERI,
    YASS_DURUM_SECENEKLERI,
    YON_SECENEKLERI,
    hidrojeoloji_varsayilanlari,
)
from sabitler import SPACE_SM, SPACE_XS
from ui_hidrojeoloji_analiz import HidrojeolojiAnalizPenceresi
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

        label("İnceleme yarıçapı", 4, 0)
        combo(
            "inceleme_yaricapi",
            ("250", "500", "1000", "2000", "5000"),
            4,
            1,
            width=12,
        )
        self.hidrojeoloji_analiz_button = ttk.Button(
            panel,
            text="Çevreyi Otomatik Analiz Et",
            command=self.hidrojeoloji_cevre_analizi_baslat,
        )
        self.hidrojeoloji_analiz_button.grid(
            row=4,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=(SPACE_SM, 0),
            pady=SPACE_XS,
        )
        self.hidrojeoloji_analiz_durum_var = tk.StringVar(value="Henüz analiz edilmedi")
        ttk.Label(
            panel,
            textvariable=self.hidrojeoloji_analiz_durum_var,
            wraplength=340,
        ).grid(
            row=4,
            column=4,
            columnspan=2,
            sticky="w",
            padx=(SPACE_SM, 0),
            pady=SPACE_XS,
        )

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
        self.hidrojeoloji_cevre_analizi_durumunu_guncelle()
        self.hidrojeoloji_navigasyon = navigation
        return navigation

    def hidrojeoloji_cevre_analizi_baslat(self):
        veri = getattr(self, "veri", {}) or {}
        kml_path = getattr(self, "kml_path", None)
        if not kml_path:
            kml_path = veri.get("dosyalar", {}).get("kml_path")
        if not kml_path or not os.path.isfile(kml_path):
            messagebox.showwarning(
                "Hidrojeoloji",
                "Otomatik çevre analizi için önce projeye ait parsel KML dosyasını seçin.",
                parent=getattr(self, "root", None),
            )
            return

        if not getattr(self, "_hidrojeoloji_acik_veri_onayi", False):
            approved = messagebox.askyesno(
                "Açık Veri Sorgusu",
                "Analiz sırasında parselin merkez koordinatı OpenStreetMap/Overpass "
                "servisine gönderilecektir. Parsel geometrisinin tamamı gönderilmez.\n\n"
                "Sorguya devam edilsin mi?",
                parent=getattr(self, "root", None),
            )
            if not approved:
                return
            self._hidrojeoloji_acik_veri_onayi = True

        radius_widget = getattr(self, "e_hidrojeoloji", {}).get("inceleme_yaricapi")
        radius = radius_widget.get().strip() if radius_widget is not None else "1000"
        try:
            radius_number = float(radius.replace(",", "."))
        except (TypeError, ValueError):
            messagebox.showwarning(
                "Hidrojeoloji",
                "İnceleme yarıçapı sayısal olmalıdır.",
                parent=getattr(self, "root", None),
            )
            return

        button = getattr(self, "hidrojeoloji_analiz_button", None)
        if button is not None:
            button.configure(state="disabled")
        self.hidrojeoloji_analiz_durum_var.set("Analiz sürüyor...")

        def success(result):
            current = self.hidrojeoloji_verisini_topla()
            previous = current.get("cevre_analizi")
            summary = cevre_analizi_kayit_ozeti(result)
            if isinstance(previous, dict) and previous.get("kml_kimligi") == summary.get("kml_kimligi"):
                if isinstance(previous.get("uygulanan_degerler"), dict):
                    summary["uygulanan_degerler"] = dict(previous["uygulanan_degerler"])
            current["cevre_analizi"] = summary
            self.hidrojeoloji_cevre_analizi_durumunu_guncelle()
            HidrojeolojiAnalizPenceresi(
                getattr(self, "root", None),
                result,
                self.hidrojeoloji_cevre_sonucunu_uygula,
            )

        def error(exc):
            self.hidrojeoloji_analiz_durum_var.set("Analiz tamamlanamadı")
            detail = str(exc)
            if not isinstance(exc, CevreAnaliziHatasi):
                detail = f"Beklenmeyen hata: {detail}"
            messagebox.showerror(
                "Hidrojeoloji Çevre Analizi",
                detail,
                parent=getattr(self, "root", None),
            )

        def done():
            if button is not None:
                button.configure(state="normal")

        self.arka_plan_gorevi_baslat(
            "Hidrojeoloji çevre analizi",
            cevre_analizi_yap,
            kml_path,
            radius_number,
            on_success=success,
            on_error=error,
            on_done=done,
            status_start="Parsel çevresindeki kıyı ve su yolları inceleniyor.",
            status_success="Hidrojeoloji çevre analizi tamamlandı.",
            status_error="Hidrojeoloji çevre analizi tamamlanamadı: {error}",
            with_context=True,
            cancellable=True,
            resource="hidrojeoloji-cevre",
        )

    @staticmethod
    def _hidrojeoloji_widget_degeri_yaz(widget, value):
        if widget is None:
            return
        if isinstance(widget, ttk.Combobox):
            widget.set(str(value or ""))
            return
        old_state = str(widget.cget("state"))
        if old_state == "disabled":
            widget.configure(state="normal")
        widget.delete(0, tk.END)
        widget.insert(0, str(value or ""))
        if old_state == "disabled":
            widget.configure(state="disabled")

    def hidrojeoloji_cevre_sonucunu_uygula(self, result, selection):
        widgets = getattr(self, "e_hidrojeoloji", {})
        applied = {}
        sea = result.get("deniz") or {}
        if selection.get("deniz_uygula") and sea.get("bulundu"):
            self._hidrojeoloji_widget_degeri_yaz(
                widgets.get("deniz_mesafe"),
                f"{float(sea.get('mesafe_m', 0)):.1f}",
            )
            applied["deniz_mesafe"] = widgets["deniz_mesafe"].get().strip()

        for prefix, selection_key, no_key in (
            ("akar_dere", "akar_aday", "akar_yok"),
            ("kuru_dere", "kuru_aday", "kuru_yok"),
        ):
            candidate = selection.get(selection_key)
            if candidate:
                self._hidrojeoloji_widget_degeri_yaz(widgets.get(prefix), "Var")
                self.hidrojeoloji_dere_alanlarini_guncelle()
                self._hidrojeoloji_widget_degeri_yaz(
                    widgets.get(f"{prefix}_mesafe"),
                    f"{float(candidate.get('mesafe_m', 0)):.1f}",
                )
                self._hidrojeoloji_widget_degeri_yaz(
                    widgets.get(f"{prefix}_yon"),
                    candidate.get("yon", ""),
                )
                applied[prefix] = "Var"
                applied[f"{prefix}_aday_id"] = candidate.get("id", "")
            elif selection.get(no_key):
                self._hidrojeoloji_widget_degeri_yaz(widgets.get(prefix), "Yok")
                self._hidrojeoloji_widget_degeri_yaz(widgets.get(f"{prefix}_mesafe"), "")
                self._hidrojeoloji_widget_degeri_yaz(widgets.get(f"{prefix}_yon"), "")
                applied[prefix] = "Yok"

        self.hidrojeoloji_dere_alanlarini_guncelle()
        current = self.hidrojeoloji_verisini_topla()
        summary = cevre_analizi_kayit_ozeti(result)
        summary["uygulanan_degerler"] = applied
        current["cevre_analizi"] = summary
        self.hidrojeoloji_cevre_analizi_durumunu_guncelle()
        if hasattr(self, "arazi_durum_guncelle"):
            self.arazi_durum_guncelle()
        if hasattr(self, "set_status"):
            self.set_status(
                "Onaylanan hidrojeoloji çevre bulguları projeye uygulandı.",
                level="success",
            )

    def hidrojeoloji_cevre_analizi_durumunu_guncelle(self):
        status_var = getattr(self, "hidrojeoloji_analiz_durum_var", None)
        if status_var is None:
            return
        veri = getattr(self, "veri", {}) or {}
        kml_path = getattr(self, "kml_path", None)
        if not kml_path:
            kml_path = veri.get("dosyalar", {}).get("kml_path")
        if not kml_path or not os.path.isfile(kml_path):
            status_var.set("KML seçilmedi")
            return
        analysis = veri.get("arazi", {}).get("hidrojeoloji", {}).get("cevre_analizi")
        if not isinstance(analysis, dict) or not analysis:
            status_var.set("Henüz analiz edilmedi")
            return
        if not cevre_analizi_guncel_mi(analysis, kml_path):
            analysis["gecersiz"] = True
            status_var.set("KML değişti; analizi yenileyin")
            return
        analysis.pop("gecersiz", None)
        source = str(analysis.get("kaynak") or "sayısal veri")
        status_var.set(f"Güncel analiz: {source}")

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
