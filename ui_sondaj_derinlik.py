# Dosya: RaporPro/ui_sondaj_derinlik.py
import copy
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sondaj_derinlik_foyu import sondaj_derinligi_foy_dosya_adi, sondaj_derinligi_foyu_olustur
from sondaj_derinlik import (
    gerilme_yuzde_on_derinlik_hesapla,
    gerilme_yuzde_on_ozet_metni,
    sondaj_derinligi_kontrol_sonucu,
    sondaj_derinligi_ozet_metni,
)


class SondajDerinlikHesabiMixin:
    def sondaj_derinlik_hesabi_penceresi(self):
        self.guncelle_veri_objesi(silent=True)
        stress_settings = self.veri.setdefault("sondaj_derinlik_hesabi", {})
        stress_defaults = {
            "temel_uzunlugu": "",
            "temel_genisligi": "",
            "temel_derinligi": "",
            "temel_taban_gerilmesi": "",
            "yass": "",
            "dogal_bha": "",
            "doygun_bha": "",
            "target_ratio": "0.10",
            "round_step": "1.00",
            "max_depth": "200",
            "hesap_yontemi": "en_elverissiz",
        }
        for key, value in stress_defaults.items():
            stress_settings.setdefault(key, value)
        result = sondaj_derinligi_kontrol_sonucu(self.veri)

        win = tk.Toplevel(self.root)
        self.pencere_hazirla(win, "Sondaj Derinliği Hesabı", "940x680", (760, 540), modal=False)

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Sondaj Derinliği Hesabı", font=("Segoe UI", 14, "bold")).pack(side="left")
        summary_label = ttk.Label(
            header,
            text=f"Önerilen minimum: {result['onerilen_sondaj_derinligi']:.2f} m",
            foreground="#C0392B" if result.get("eksik_sondajlar") else "#1E8449",
            font=("Segoe UI", 11, "bold"),
        )
        summary_label.pack(side="right")

        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        stress_tab = ttk.Frame(notebook, padding=10)
        control_tab = ttk.Frame(notebook, padding=10)
        notebook.add(stress_tab, text="Gerilme %10 Hesabı")
        notebook.add(control_tab, text="Proje Ön Kontrolü")

        form = ttk.LabelFrame(stress_tab, text="Elle Girilecek Değerler", padding=10)
        form.pack(fill="x", pady=(0, 8))
        entries = {}
        specs = [
            ("Temel uzunluğu L (m)", "temel_uzunlugu", "Örn. 24"),
            ("Temel genişliği B (m)", "temel_genisligi", "Örn. 12"),
            ("Temel taban derinliği Df (m)", "temel_derinligi", "Örn. 3.0"),
            ("Temel taban gerilmesi", "temel_taban_gerilmesi", "Örn. 20 t/m²"),
            ("YASS (m)", "yass", "Zeminden itibaren; yüzeydeyse 0"),
            ("Doğal BHA", "dogal_bha", "Temel taban gerilmesiyle uyumlu birim"),
            ("Doygun BHA", "doygun_bha", "Su BHA birime göre otomatik alınır"),
            ("Hedef oran", "target_ratio", "0.10"),
            ("Hesap adımı / yuvarlama (m)", "round_step", "1.00"),
            ("Maks. arama derinliği (m)", "max_depth", "200"),
        ]
        for idx, (label, key, tip) in enumerate(specs):
            row, col = divmod(idx, 2)
            col *= 3
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="e", padx=5, pady=4)
            entry = ttk.Entry(form, width=16)
            entry.grid(row=row, column=col + 1, sticky="w", padx=5, pady=4)
            entry.insert(0, str(stress_settings.get(key, stress_defaults.get(key, "")) or ""))
            entries[key] = entry
            hint = ttk.Label(form, text=tip, foreground="#777777")
            hint.grid(row=row, column=col + 2, sticky="w", padx=(0, 12), pady=4)
        for col in range(6):
            form.columnconfigure(col, weight=1 if col in (2, 5) else 0)

        method_labels = {
            "En elverişsiz sonuç": "en_elverissiz",
            "Boussinesq": "boussinesq",
            "Westergaard": "westergaard",
            "Yaklaşık yöntem (1/2)": "yaklasik",
        }
        current_method = str(stress_settings.get("hesap_yontemi", "en_elverissiz") or "en_elverissiz")
        current_method_label = next(
            (label for label, code in method_labels.items() if code == current_method),
            "En elverişsiz sonuç",
        )
        method_var = tk.StringVar(value=current_method_label)
        ttk.Label(form, text="Belirleyici hesap yöntemi").grid(row=5, column=0, sticky="e", padx=5, pady=4)
        ttk.Combobox(
            form,
            textvariable=method_var,
            values=list(method_labels),
            state="readonly",
            width=22,
        ).grid(row=5, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(
            form,
            text="Varsayılan seçim üç yöntemin en derin sonucudur.",
            foreground="#777777",
        ).grid(row=5, column=2, columnspan=4, sticky="w", padx=(0, 12), pady=4)

        stress_text = tk.Text(stress_tab, wrap="word", font=("Consolas", 10), padx=10, pady=10)
        stress_text.pack(fill="both", expand=True)

        control_text = tk.Text(control_tab, wrap="word", font=("Consolas", 10), padx=10, pady=10)
        control_text.pack(fill="both", expand=True)

        def set_text(widget, value):
            widget.config(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
            widget.config(state="disabled")

        def current_params():
            params = {key: entry.get().strip() for key, entry in entries.items()}
            params["hesap_yontemi"] = method_labels.get(method_var.get(), "en_elverissiz")
            return params

        def refresh_control_text():
            control = sondaj_derinligi_kontrol_sonucu(self.veri)
            summary_label.config(
                text=f"Önerilen minimum: {control['onerilen_sondaj_derinligi']:.2f} m",
                foreground="#C0392B" if control.get("eksik_sondajlar") else "#1E8449",
            )
            if control.get("hesap_tipi") == "gerilme_10":
                stress = control.get("gerilme_hesabi", {})
                set_text(
                    control_text,
                    "Proje kontrolünde gerilme %10 hesabı esas alınıyor.\n\n"
                    f"Önerilen minimum sondaj derinliği: {control['onerilen_sondaj_derinligi']:.2f} m\n"
                    f"Temel tabanı altı Z: {stress.get('z_solution', 0):.2f} m\n"
                    f"Mevcut en derin sondaj: {control['mevcut_en_derin']:.2f} m\n\n"
                    + ("\n".join(f"- {item['sondaj']}: {item['derinlik']:.2f} m, eksik {item['eksik']:.2f} m" for item in control.get("eksik_sondajlar", [])) or "Mevcut sondajlar önerilen derinliği sağlıyor veya sondaj verisi henüz girilmedi."),
                )
            else:
                set_text(control_text, sondaj_derinligi_ozet_metni(self.veri))

        def calculate():
            params = current_params()
            result = gerilme_yuzde_on_derinlik_hesapla(params)
            if not result.get("ok"):
                messagebox.showwarning("Sondaj Derinliği Hesabı", "\n".join(result.get("errors", [])), parent=win)
                set_text(stress_text, gerilme_yuzde_on_ozet_metni(params))
                return
            self.veri["sondaj_derinlik_hesabi"] = params
            set_text(stress_text, gerilme_yuzde_on_ozet_metni(params))
            refresh_control_text()
            self.set_status(f"Gerilme %10 sondaj derinliği: {result['sondaj_derinligi_yuvarlatilmis']:.2f} m", level="success")

        def export_foy(ext):
            params = current_params()
            result = gerilme_yuzde_on_derinlik_hesapla(params)
            if not result.get("ok"):
                messagebox.showwarning("Sondaj Derinliği Hesabı", "\n".join(result.get("errors", [])), parent=win)
                set_text(stress_text, gerilme_yuzde_on_ozet_metni(params))
                return
            self.veri["sondaj_derinlik_hesabi"] = params
            self.guncelle_veri_objesi(silent=True)
            self.veri["sondaj_derinlik_hesabi"] = params
            ayarlar = self.veri.setdefault("ayarlar", {})
            initialdir = ayarlar.get("varsayilan_cikti_klasor", "")
            opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
            ext = ".pdf" if ext == ".pdf" else ".docx"
            path = filedialog.asksaveasfilename(
                title="Sondaj derinliği hesap föyü kaydet",
                initialfile=sondaj_derinligi_foy_dosya_adi(self.veri, ext),
                defaultextension=ext,
                filetypes=[("PDF", "*.pdf")] if ext == ".pdf" else [("Word", "*.docx")],
                **opts,
            )
            if not path:
                return
            ayarlar["varsayilan_cikti_klasor"] = os.path.dirname(path)
            veri = copy.deepcopy(self.veri)

            def done(info):
                self.set_status(f"Sondaj derinliği hesap föyü hazır: {os.path.basename(info['path'])}", level="success")
                messagebox.showinfo("Sondaj Derinliği", f"Hesap föyü hazırlandı:\n{info['path']}", parent=win)

            self.arka_plan_gorevi_baslat(
                "Sondaj derinliği föyü",
                sondaj_derinligi_foyu_olustur,
                veri,
                path,
                status_start="Sondaj derinliği hesap föyü hazırlanıyor.",
                status_success="Sondaj derinliği hesap föyü hazırlandı.",
                status_error="Sondaj derinliği hesap föyü oluşturulamadı: {error}",
                on_success=done,
                on_error=lambda exc: messagebox.showerror("Sondaj Derinliği", str(exc), parent=win),
            )

        def reset_defaults():
            for key, value in stress_defaults.items():
                if key == "hesap_yontemi":
                    method_var.set("En elverişsiz sonuç")
                    continue
                entries[key].delete(0, tk.END)
                entries[key].insert(0, value)
            set_text(stress_text, "Değerleri girip Hesapla düğmesine basın.")

        initial = gerilme_yuzde_on_derinlik_hesapla(stress_settings)
        if initial.get("ok"):
            set_text(stress_text, gerilme_yuzde_on_ozet_metni(stress_settings))
        else:
            set_text(stress_text, "Temel uzunluğu, temel genişliği, temel taban derinliği, temel taban gerilmesi, YASS, doğal BHA ve doygun BHA değerlerini girip Hesapla düğmesine basın.")
        refresh_control_text()

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        self.modern_button(btns, text="Hesapla", command=calculate, role="success").pack(side="left")
        self.modern_button(btns, text="Varsayılan", command=reset_defaults, role="warning", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Word Föyü", command=lambda: export_foy(".docx"), role="primary", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="PDF Föyü", command=lambda: export_foy(".pdf"), role="accent", outline=True).pack(side="left")
        self.modern_button(btns, text="Bina Bilgilerine Git", command=lambda: self._workflow_git("bina"), role="primary", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Sondajlara Git", command=lambda: self._workflow_git("sondaj"), role="accent", outline=True).pack(side="left")
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")
