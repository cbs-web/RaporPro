# Dosya: RaporPro/ui_evrak_okuma.py
"""İmar ve zemin durum belgelerinden kontrollü veri aktarımı arayüzü."""

from __future__ import annotations

import datetime
import os
import re
import unicodedata
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from evrak_okuma import EvrakOkumaHatasi, evrak_klasorunu_oku
from jeoloji_raporu import (
    DURUM_ALUVYON,
    JEOLOJI_BIRIM_KATALOGU,
    KONUM_INCELEME_ALANI,
    jeoloji_birimleri,
)
from sabitler import COLOR_SUCCESS, COLOR_TEXT_MUTED, COLOR_WARNING


def _deger_anahtari(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


class EvrakOkumaMixin:
    """Evrak klasörünü tarar, bulunan değerleri onayla birlikte uygular."""

    def _evrak_baslangic_klasoru(self):
        saved = (
            self.veri.get("evrak_aktarimi", {}).get("son_klasor", "")
            if isinstance(getattr(self, "veri", None), dict)
            else ""
        )
        candidates = [saved]
        active_path = getattr(self, "aktif_dosya_yolu", None)
        if active_path:
            project_dir = os.path.dirname(os.path.abspath(active_path))
            candidates.extend(
                (
                    os.path.join(project_dir, "EVRAKLAR"),
                    os.path.join(project_dir, "Evraklar"),
                    project_dir,
                )
            )
        candidates.append(os.getcwd())
        return next(
            (path for path in candidates if path and os.path.isdir(path)),
            os.getcwd(),
        )

    def evraklardan_veri_oku(self):
        folder = filedialog.askdirectory(
            title="İmar ve Zemin Durum Belgelerinin Bulunduğu Klasörü Seçin",
            initialdir=self._evrak_baslangic_klasoru(),
            mustexist=True,
        )
        if not folder:
            return

        button = getattr(self, "kunye_evrak_button", None)
        if button is not None:
            try:
                button.configure(state="disabled")
            except tk.TclError:
                pass

        def restore_button():
            if button is not None:
                try:
                    button.configure(state="normal")
                except tk.TclError:
                    pass

        def show_error(error):
            title = "Evraklardan Veri Oku"
            if isinstance(error, EvrakOkumaHatasi):
                messagebox.showwarning(title, str(error), parent=self.root)
            else:
                messagebox.showerror(
                    title,
                    f"Evraklar okunurken beklenmeyen bir hata oluştu:\n\n{error}",
                    parent=self.root,
                )

        self.arka_plan_gorevi_baslat(
            "İmar ve zemin belgelerini oku",
            evrak_klasorunu_oku,
            folder,
            on_success=self.evrak_okuma_sonuc_penceresi,
            on_error=show_error,
            on_done=restore_button,
            status_start="İmar ve zemin durum belgeleri okunuyor...",
            status_success="Evrak okuma tamamlandı; aktarılacak alanları seçin.",
            status_error="Evrak okuma tamamlanamadı: {error}",
            with_context=True,
            cancellable=True,
            resource="evrak_ocr",
        )

    def _evrak_mevcut_deger(self, field):
        section = field.get("bolum", "")
        key = field.get("anahtar", "")
        stores = {
            "kunye": getattr(self, "e_kunye", {}),
            "bina": getattr(self, "e_bina", {}),
            "arazi": getattr(self, "e_arazi", {}),
        }
        widget = stores.get(section, {}).get(key)
        if widget is not None:
            try:
                return widget.get().strip()
            except tk.TclError:
                pass
        if section == "jeoloji":
            for record in jeoloji_birimleri(self.veri):
                if record.get("kod") == key:
                    name = record.get("ad", "")
                    return f"{name} ({key})" if name else key
            return ""
        return str(self.veri.get(section, {}).get(key, "") or "").strip()

    def _evrak_widgete_yaz(self, section, key, value):
        stores = {
            "kunye": getattr(self, "e_kunye", {}),
            "bina": getattr(self, "e_bina", {}),
            "arazi": getattr(self, "e_arazi", {}),
        }
        widget = stores.get(section, {}).get(key)
        if widget is None:
            return
        if isinstance(widget, ttk.Combobox):
            widget.set(value)
            return
        widget.delete(0, tk.END)
        widget.insert(0, value)

    def _evrak_jeoloji_birimi_ekle(self, code):
        if any(record.get("kod") == code for record in jeoloji_birimleri(self.veri)):
            return False
        catalog = JEOLOJI_BIRIM_KATALOGU.get(code, {})
        self.veri.setdefault("jeoloji", {}).setdefault("birimler", []).append(
            {
                "kod": code,
                "ad": catalog.get("ad", ""),
                "yas": catalog.get("yas", ""),
                "konum": KONUM_INCELEME_ALANI,
                "durum": DURUM_ALUVYON if code == "Qal" else "belirtilmedi",
                "kesitte_kullan": True,
                "ozel_aciklama": "",
            }
        )
        return True

    def _evrak_alani_uygula(self, field):
        section = field.get("bolum", "")
        key = field.get("anahtar", "")
        value = str(field.get("deger", "") or "").strip()
        if not section or not key or not value:
            return False
        if section == "jeoloji":
            return self._evrak_jeoloji_birimi_ekle(key)
        self._evrak_widgete_yaz(section, key, value)
        self.veri.setdefault(section, {})[key] = value
        return True

    def _evrak_secimleri_uygula(self, window, result, selections):
        selected = [field for variable, field in selections if variable.get()]
        if not selected:
            messagebox.showinfo(
                "Evraklardan Veri Aktar",
                "Aktarılacak bir alan seçilmedi.",
                parent=window,
            )
            return

        applied = []
        for field in selected:
            if self._evrak_alani_uygula(field):
                applied.append(field)

        if not applied:
            messagebox.showinfo(
                "Evraklardan Veri Aktar",
                "Seçilen bilgiler projede zaten aynı değerlerle bulunuyor.",
                parent=window,
            )
            return

        self.guncelle_veri_objesi(silent=True)
        self.veri["evrak_aktarimi"] = {
            "son_klasor": result.get("klasor", ""),
            "son_tarih": datetime.datetime.now().isoformat(timespec="seconds"),
            "belgeler": result.get("belgeler", []),
            "uygulanan_alanlar": [
                {
                    "bolum": field.get("bolum", ""),
                    "anahtar": field.get("anahtar", ""),
                    "deger": field.get("deger", ""),
                    "kaynak": field.get("kaynak", ""),
                }
                for field in applied
            ],
        }
        self.otomatik_kaydet()
        self.kunye_durum_guncelle()
        self.bina_durum_guncelle()
        self.arazi_durum_guncelle()
        if any(field.get("bolum") == "jeoloji" for field in applied):
            self.jeolojik_birimler_kaydedildi()
        elif hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        self.set_status(
            f"Evraklardan {len(applied)} alan projeye aktarıldı.",
            level="success",
        )
        window.destroy()
        messagebox.showinfo(
            "Evraklardan Veri Aktar",
            f"{len(applied)} alan projeye aktarıldı.\n\n"
            "Dolu ve farklı alanlar yalnızca özellikle seçildiyse değiştirildi.",
            parent=self.root,
        )

    def evrak_okuma_sonuc_penceresi(self, result):
        fields = result.get("alanlar", [])
        if not fields:
            messagebox.showwarning(
                "Evraklardan Veri Oku",
                "Belgelerde aktarılabilecek bir alan bulunamadı.",
                parent=self.root,
            )
            return

        window = tk.Toplevel(self.root)
        self.pencere_hazirla(
            window,
            "Evraklardan Veri Aktar",
            "1220x760",
            (860, 560),
            modal=True,
        )
        window.columnconfigure(0, weight=1)
        window.rowconfigure(2, weight=1)

        header = ttk.Frame(window, padding=(16, 12, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="İmar ve Zemin Durum Belgesi Sonuçları",
            style="PageTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        document_names = ", ".join(
            document.get("ad", "") for document in result.get("belgeler", [])
        )
        ttk.Label(
            header,
            text=f"Okunan belgeler: {document_names}",
            style="Muted.TLabel",
            wraplength=1050,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        warnings = result.get("uyarilar", [])
        if warnings:
            ttk.Label(
                window,
                text="  ".join(warnings),
                foreground=COLOR_WARNING,
                wraplength=1120,
                padding=(16, 0, 16, 8),
            ).grid(row=1, column=0, sticky="ew")

        table_host = ttk.Frame(window)
        table_host.grid(row=2, column=0, sticky="nsew", padx=12)
        inner, _canvas = self.scrollable_page(table_host, padding=(4, 4))
        column_weights = (0, 1, 2, 2, 2, 0)
        for column, weight in enumerate(column_weights):
            inner.columnconfigure(column, weight=weight)

        headers = ("Aktar", "Alan", "Mevcut değer", "Evraktan okunan", "Kaynak", "Güven")
        for column, text in enumerate(headers):
            ttk.Label(
                inner,
                text=text,
                style="SectionTitle.TLabel",
                padding=(6, 7),
            ).grid(row=0, column=column, sticky="ew")

        selections = []
        for row, field in enumerate(fields, start=1):
            current = self._evrak_mevcut_deger(field)
            proposed = str(field.get("deger", "") or "").strip()
            same = bool(current) and _deger_anahtari(current) == _deger_anahtari(proposed)
            conflict = bool(current) and not same
            variable = tk.BooleanVar(value=not current)
            selections.append((variable, field))

            background = "#FFF4E5" if conflict else ("#F3F6F7" if same else "#EDF8F1")
            row_frame = tk.Frame(inner, bg=background, bd=0)
            row_frame.grid(
                row=row,
                column=0,
                columnspan=6,
                sticky="nsew",
                pady=(0, 2),
            )
            for column, weight in enumerate(column_weights):
                row_frame.columnconfigure(column, weight=weight)

            tk.Checkbutton(
                row_frame,
                variable=variable,
                bg=background,
                activebackground=background,
                selectcolor="white",
                bd=0,
            ).grid(row=0, column=0, padx=8, pady=8)
            tk.Label(
                row_frame,
                text=field.get("etiket", ""),
                bg=background,
                anchor="w",
                justify="left",
                wraplength=170,
            ).grid(row=0, column=1, sticky="ew", padx=6, pady=8)
            current_text = current or "Boş"
            if conflict:
                current_text += "\n(Mevcut değer korunuyor)"
            elif same:
                current_text += "\n(Zaten aynı)"
            tk.Label(
                row_frame,
                text=current_text,
                bg=background,
                fg=COLOR_WARNING if conflict else COLOR_TEXT_MUTED,
                anchor="w",
                justify="left",
                wraplength=230,
            ).grid(row=0, column=2, sticky="ew", padx=6, pady=8)
            alternative_text = ""
            alternatives = field.get("alternatifler", []) or []
            if alternatives:
                alternative_text = f"\nDiğer okuma: {', '.join(alternatives)}"
            tk.Label(
                row_frame,
                text=proposed + alternative_text,
                bg=background,
                fg=COLOR_SUCCESS if not conflict else "#222222",
                anchor="w",
                justify="left",
                wraplength=250,
            ).grid(row=0, column=3, sticky="ew", padx=6, pady=8)
            tk.Label(
                row_frame,
                text=field.get("kaynak", ""),
                bg=background,
                fg=COLOR_TEXT_MUTED,
                anchor="w",
                justify="left",
                wraplength=240,
            ).grid(row=0, column=4, sticky="ew", padx=6, pady=8)
            tk.Label(
                row_frame,
                text=f"%{round(float(field.get('guven', 0.0)) * 100)}",
                bg=background,
                anchor="center",
            ).grid(row=0, column=5, padx=8, pady=8)

        footer = ttk.Frame(window, padding=(12, 10))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            text="Yeşil satırlar boş alanları, turuncu satırlar mevcut değerle farkı gösterir.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")

        def select_empty():
            for variable, field in selections:
                variable.set(not bool(self._evrak_mevcut_deger(field)))

        def select_all():
            for variable, _field in selections:
                variable.set(True)

        self.modern_button(
            footer,
            "Boş Alanları Seç",
            command=select_empty,
            role="neutral",
            padx=9,
            pady=5,
        ).grid(row=0, column=1, padx=(6, 0))
        self.modern_button(
            footer,
            "Tümünü Seç",
            command=select_all,
            role="warning",
            padx=9,
            pady=5,
        ).grid(row=0, column=2, padx=(6, 0))
        self.modern_button(
            footer,
            "Vazgeç",
            command=window.destroy,
            role="neutral",
            padx=9,
            pady=5,
        ).grid(row=0, column=3, padx=(6, 0))
        self.modern_button(
            footer,
            "Seçilenleri Aktar",
            command=lambda: self._evrak_secimleri_uygula(
                window,
                result,
                selections,
            ),
            role="success",
            padx=10,
            pady=5,
        ).grid(row=0, column=4, padx=(6, 0))
        try:
            window.grab_set()
        except tk.TclError:
            pass


__all__ = ["EvrakOkumaMixin"]
