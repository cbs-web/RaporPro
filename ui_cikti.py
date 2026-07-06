import datetime
import os
import shutil
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

import matplotlib.pyplot as plt

from motor import GeoEngine
from performans import perf_tracked
from sabitler import COLOR_SUCCESS, FONT_BOLD
from taahhutname import tum_taahhutnameleri_olustur
from tutanaklar import tutanak_dosya_adi, tutanaklari_olustur
from ekler import EK_SET_ARAZI_DENEYLI, EK_SET_NORMAL, ek_icerik_haritasi, ek_pdf_dosya_adi, ekler_pdf_olustur


class CiktiMerkeziMixin:
    @perf_tracked("outputs.center_dialog")
    def cikti_merkezi_penceresi(self):
        self.guncelle_veri_objesi(silent=True)
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("cikti_merkezi_klasor") or ayarlar.get("varsayilan_cikti_klasor") or ""
        if not initialdir and self.aktif_dosya_yolu:
            initialdir = os.path.dirname(self.aktif_dosya_yolu)

        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Çıktı Merkezi", "560x390", (520, 360), modal=True)

        folder_var = tk.StringVar(value=initialdir if initialdir and os.path.isdir(initialdir) else "")
        fmt_default = str(ayarlar.get("cikti_merkezi_format", "JPG")).upper()
        if fmt_default not in ("JPG", "PNG", "PDF", "SVG"):
            fmt_default = "JPG"
        fmt_var = tk.StringVar(value=fmt_default)
        dpi_var = tk.StringVar(value=str(ayarlar.get("cikti_merkezi_dpi", "300") or "300"))
        export_logs_var = tk.BooleanVar(value=True)
        export_section_var = tk.BooleanVar(value=True)
        export_maps_var = tk.BooleanVar(value=True)
        export_report_images_var = tk.BooleanVar(value=True)
        export_taahhut_var = tk.BooleanVar(value=True)
        export_ekler_var = tk.BooleanVar(value=True)
        taahhut_format_default = str(ayarlar.get("cikti_taahhut_format", "Excel") or "Excel")
        if taahhut_format_default not in ("Excel", "PDF"):
            taahhut_format_default = "Excel"
        taahhut_format_var = tk.StringVar(value=taahhut_format_default)

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Ana çıktı klasörü").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=folder_var).grid(row=0, column=1, sticky="ew", padx=8, pady=5)

        def choose_folder():
            opts = {"initialdir": folder_var.get()} if folder_var.get() and os.path.isdir(folder_var.get()) else {}
            path = filedialog.askdirectory(title="Çıktı klasörünü seçin", **opts)
            if path:
                folder_var.set(path)

        tk.Button(body, text="Seç", command=choose_folder, bg="#ECF0F1").grid(row=0, column=2, sticky="ew", pady=5)

        ttk.Label(body, text="Format").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(body, textvariable=fmt_var, values=("JPG", "PNG", "PDF", "SVG"), width=12, state="readonly").grid(row=1, column=1, sticky="w", padx=8, pady=5)
        ttk.Label(body, text="DPI").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=dpi_var, width=14).grid(row=2, column=1, sticky="w", padx=8, pady=5)

        opts_frame = ttk.LabelFrame(body, text="Üretilecek çıktılar", padding=10)
        opts_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        ttk.Checkbutton(opts_frame, text="01_Loglar - Sondaj logları", variable=export_logs_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="02_Kesitler - Jeolojik kesit", variable=export_section_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="03_Haritalar - Sondaj/jeofizik haritaları", variable=export_maps_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="04_Rapor_Gorselleri - Rapor görselleri", variable=export_report_images_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="05_Taahhütnameler - Jeoloji ve Jeofizik", variable=export_taahhut_var).pack(anchor="w", pady=2)
        taahhut_format_row = ttk.Frame(opts_frame)
        taahhut_format_row.pack(anchor="w", fill="x", pady=2)
        ttk.Label(taahhut_format_row, text="   Taahhütname formatı").pack(side="left", padx=(0, 8))
        ttk.Combobox(taahhut_format_row, textvariable=taahhut_format_var, values=("Excel", "PDF"), width=10, state="readonly").pack(side="left")
        ttk.Checkbutton(opts_frame, text="06_Ekler - Ekler PDF", variable=export_ekler_var).pack(anchor="w", pady=2)

        summary = ttk.Label(
            body,
            text="Seçilen klasör içinde otomatik alt klasörler oluşturulur.",
            foreground="#333333",
        )
        summary.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        btns = ttk.Frame(body)
        btns.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(18, 0))

        def start():
            base_folder = folder_var.get().strip()
            if not base_folder:
                messagebox.showwarning("Çıktı Merkezi", "Lütfen ana çıktı klasörü seçin.")
                return
            if not any([export_logs_var.get(), export_section_var.get(), export_maps_var.get(), export_report_images_var.get(), export_taahhut_var.get(), export_ekler_var.get()]):
                messagebox.showwarning("Çıktı Merkezi", "En az bir çıktı türü seçin.")
                return
            try:
                dpi = int(float(dpi_var.get().replace(",", ".")))
                if dpi < 72 or dpi > 1200:
                    raise ValueError
            except Exception:
                messagebox.showwarning("Çıktı Merkezi", "DPI değeri 72 ile 1200 arasında bir sayı olmalı.")
                return
            config = {
                "base_folder": base_folder,
                "format": fmt_var.get().strip().lower(),
                "dpi": dpi,
                "logs": bool(export_logs_var.get()),
                "section": bool(export_section_var.get()),
                "maps": bool(export_maps_var.get()),
                "report_images": bool(export_report_images_var.get()),
                "taahhutnameler": bool(export_taahhut_var.get()),
                "taahhut_format": taahhut_format_var.get(),
                "ekler": bool(export_ekler_var.get()),
            }
            ayarlar["cikti_merkezi_klasor"] = base_folder
            ayarlar["cikti_merkezi_format"] = fmt_var.get().strip().upper()
            ayarlar["cikti_merkezi_dpi"] = str(dpi)
            ayarlar["cikti_taahhut_format"] = taahhut_format_var.get()
            if not ayarlar.get("varsayilan_cikti_klasor"):
                ayarlar["varsayilan_cikti_klasor"] = base_folder
            win.destroy()
            self.cikti_merkezi_baslat(config)

        tk.Button(btns, text="Başlat", command=start, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=(5, 0))
        tk.Button(btns, text="Vazgeç", command=win.destroy, bg="#ECF0F1").pack(side="right", padx=5)

    def cikti_merkezi_baslat(self, config):
        total = 0
        if config.get("logs"):
            total += len(self.veri.get("sondaj", []))
        if config.get("section"):
            total += 1
        if config.get("maps"):
            total += len(self.cikti_merkezi_harita_kaynaklari())
        if config.get("report_images"):
            total += len(self.cikti_merkezi_rapor_gorselleri())
        if config.get("taahhutnameler"):
            total += 1
        if config.get("ekler"):
            total += 1
        total = max(total, 1)

        progress_win = Toplevel(self.root)
        self.pencere_hazirla(progress_win, "Çıktı Merkezi", "520x175", (460, 160), modal=True)
        status_var = tk.StringVar(value="Hazırlanıyor...")
        detail_var = tk.StringVar(value=f"0 / {total}")
        progress_var = tk.DoubleVar(value=0)
        cancel_state = {"cancelled": False}

        body = ttk.Frame(progress_win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, textvariable=status_var, font=FONT_BOLD).pack(anchor="w", pady=(0, 8))
        ttk.Progressbar(body, maximum=total, variable=progress_var).pack(fill="x", pady=6)
        ttk.Label(body, textvariable=detail_var).pack(anchor="w", pady=(4, 10))

        def cancel():
            cancel_state["cancelled"] = True
            status_var.set("İptal ediliyor...")
            cancel_btn.config(state="disabled")

        cancel_btn = tk.Button(body, text="İptal", command=cancel, bg="#ECF0F1")
        cancel_btn.pack(side="right")
        progress = {
            "window": progress_win,
            "status": status_var,
            "detail": detail_var,
            "value": progress_var,
            "button": cancel_btn,
            "total": total,
        }
        self.set_status("Çıktı Merkezi başlatıldı.", level="info")
        self.arka_plan_gorevi_baslat(
            "Çıktı Merkezi",
            self.cikti_merkezi_threaded,
            config,
            progress,
            cancel_state,
            status_start="Çıktı Merkezi arka planda başlatıldı.",
            status_success="Çıktı Merkezi işlemi bitti.",
            status_error="Çıktı Merkezi tamamlanamadı: {error}",
            on_error=lambda exc: self.cikti_merkezi_bitti(progress, str(exc), "error"),
        )

    def cikti_merkezi_progress(self, progress, done, text):
        def apply_update():
            try:
                win = progress.get("window")
                if not win or not win.winfo_exists():
                    return
                total = progress.get("total", 0)
                progress["value"].set(done)
                progress["status"].set(text)
                progress["detail"].set(f"{min(done, total)} / {total}")
            except Exception:
                pass

        self.root.after(0, apply_update)

    def cikti_merkezi_bitti(self, progress, message, level):
        def apply_finish():
            try:
                win = progress.get("window") if progress else None
                if win and win.winfo_exists():
                    progress["status"].set(message.split("\n", 1)[0])
                    progress["detail"].set("Tamamlandı")
                    progress["value"].set(progress.get("total", 0))
                    btn = progress.get("button")
                    if btn:
                        btn.config(text="Kapat", state="normal", command=win.destroy)
            except Exception:
                pass
            if level == "success":
                messagebox.showinfo("Çıktı Merkezi", message)
            elif level == "warning":
                messagebox.showwarning("Çıktı Merkezi", message)
            else:
                messagebox.showerror("Çıktı Merkezi", message)

        self.root.after(0, apply_finish)

    def cikti_merkezi_harita_kaynaklari(self):
        return [
            ("Sondaj_Haritasi", getattr(self, "word_img_sondaj", None)),
            ("Jeofizik_Haritasi", getattr(self, "word_img_jeofizik", None)),
        ]

    def cikti_merkezi_rapor_gorselleri(self):
        return [
            ("Yerbuldurur", getattr(self, "img_yer", None)),
            ("TKGM", getattr(self, "img_tkgm", None)),
            ("PGA", getattr(self, "img_pga", None)),
            ("MJH", getattr(self, "img_mjh", None)),
        ]

    def cikti_merkezi_kesit_sondajlari(self):
        options = dict(self.veri.get("kesit_ayarlari", {}) or {})
        sondajlar = self.veri.get("sondaj", [])
        selected_names = options.get("selected_sondajlar") or []
        selected = [s for s in sondajlar if s.get("no", "") in selected_names]
        if len(selected) < 2:
            selected = list(sondajlar)
        if len(selected) >= 2:
            options.setdefault("mode", "line_projection")
            options["selected_sondajlar"] = [s.get("no", "") for s in selected]
            if options.get("mode") == "line_projection":
                options.setdefault("line_start_no", selected[0].get("no", "Baslangic"))
                options.setdefault("line_start_y", selected[0].get("y", ""))
                options.setdefault("line_start_x", selected[0].get("x", ""))
                options.setdefault("line_end_no", selected[-1].get("no", "Bitis"))
                options.setdefault("line_end_y", selected[-1].get("y", ""))
                options.setdefault("line_end_x", selected[-1].get("x", ""))
                options.setdefault("max_offset", "10.0")
        return selected, options

    def cikti_merkezi_kopyala(self, source, target_folder, label):
        if not source or not os.path.exists(source):
            raise FileNotFoundError(f"{label} dosyası bulunamadı")
        ext = os.path.splitext(source)[1] or ".jpg"
        target = os.path.join(target_folder, f"{self._guvenli_dosya_adi(label)}{ext}")
        shutil.copy2(source, target)
        return target

    def cikti_merkezi_ozet_yaz(self, base_folder, saved_files, errors, cancelled):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = os.path.join(base_folder, f"Cikti_merkezi_ozeti_{timestamp}.txt")
        lines = [
            "RaporPro Çıktı Merkezi Özeti",
            f"Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            f"Klasor: {base_folder}",
            f"Durum: {'Iptal edildi' if cancelled else 'Tamamlandi'}",
            f"Kaydedilen dosya: {len(saved_files)}",
            f"Hata/Uyarı: {len(errors)}",
            "",
            "Kaydedilen dosyalar:",
        ]
        lines.extend(f"- {path}" for path in saved_files) if saved_files else lines.append("- Yok")
        lines.extend(["", "Hata ve uyarılar:"])
        lines.extend(f"- {err}" for err in errors) if errors else lines.append("- Yok")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return summary_path

    @perf_tracked("outputs.center_export")
    def cikti_merkezi_threaded(self, config, progress, cancel_state):
        done = 0
        saved_files = []
        errors = []
        base_folder = config["base_folder"]
        fmt = config.get("format", "jpg")
        ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
        dpi = config.get("dpi", 300)
        try:
            folders = {
                "logs": os.path.join(base_folder, "01_Loglar"),
                "sections": os.path.join(base_folder, "02_Kesitler"),
                "maps": os.path.join(base_folder, "03_Haritalar"),
                "report_images": os.path.join(base_folder, "04_Rapor_Gorselleri"),
                "taahhutnameler": os.path.join(base_folder, "05_Taahhutnameler"),
                "ekler": os.path.join(base_folder, "06_Ekler"),
            }
            os.makedirs(base_folder, exist_ok=True)
            for folder in folders.values():
                os.makedirs(folder, exist_ok=True)

            if config.get("logs"):
                for idx, sondaj in enumerate(self.veri.get("sondaj", []), start=1):
                    if cancel_state.get("cancelled"):
                        break
                    sondaj_no = sondaj.get("no") or f"SK-{idx}"
                    self.cikti_merkezi_progress(progress, done, f"Log hazırlanıyor: {sondaj_no}")
                    figures = []
                    try:
                        figures = GeoEngine.ciz_profesyonel_log(sondaj, self.veri)
                        safe_no = self._guvenli_dosya_adi(sondaj_no, f"SK_{idx}")
                        for page_idx, fig in enumerate(figures, start=1):
                            suffix = f"_Sayfa{page_idx}" if len(figures) > 1 else ""
                            path = os.path.join(folders["logs"], f"Log_{safe_no}{suffix}.{ext}")
                            fig.savefig(path, dpi=dpi, bbox_inches="tight", format=ext)
                            saved_files.append(path)
                    except Exception as exc:
                        errors.append(f"Log {sondaj_no}: {exc}")
                    finally:
                        for fig in figures:
                            try:
                                plt.close(fig)
                            except Exception:
                                pass
                    done += 1
                    self.cikti_merkezi_progress(progress, done, f"Log kaydedildi: {sondaj_no}")

            if config.get("section") and not cancel_state.get("cancelled"):
                self.cikti_merkezi_progress(progress, done, "Kesit hazırlanıyor...")
                selected, options = self.cikti_merkezi_kesit_sondajlari()
                if len(selected) < 2:
                    errors.append("Kesit: en az iki sondaj bulunamadı")
                else:
                    fig = None
                    try:
                        options = dict(options)
                        options["export_dpi"] = str(dpi)
                        fig, _ = GeoEngine.kesit_ciz_interaktif(selected, options=options)
                        path = os.path.join(folders["sections"], f"Jeolojik_Kesit.{ext}")
                        fig.savefig(path, dpi=dpi, bbox_inches="tight", format=ext)
                        saved_files.append(path)
                    except Exception as exc:
                        errors.append(f"Kesit: {exc}")
                    finally:
                        if fig is not None:
                            try:
                                plt.close(fig)
                            except Exception:
                                pass
                done += 1
                self.cikti_merkezi_progress(progress, done, "Kesit adımı tamamlandı")

            if config.get("maps") and not cancel_state.get("cancelled"):
                for label, source in self.cikti_merkezi_harita_kaynaklari():
                    if cancel_state.get("cancelled"):
                        break
                    self.cikti_merkezi_progress(progress, done, f"Harita kopyalanıyor: {label}")
                    try:
                        saved_files.append(self.cikti_merkezi_kopyala(source, folders["maps"], label))
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                    done += 1
                    self.cikti_merkezi_progress(progress, done, f"Harita adımı tamamlandı: {label}")

            if config.get("report_images") and not cancel_state.get("cancelled"):
                for label, source in self.cikti_merkezi_rapor_gorselleri():
                    if cancel_state.get("cancelled"):
                        break
                    self.cikti_merkezi_progress(progress, done, f"Rapor görseli kopyalanıyor: {label}")
                    try:
                        saved_files.append(self.cikti_merkezi_kopyala(source, folders["report_images"], label))
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                    done += 1
                    self.cikti_merkezi_progress(progress, done, f"Görsel adımı tamamlandı: {label}")

            if config.get("taahhutnameler") and not cancel_state.get("cancelled"):
                self.cikti_merkezi_progress(progress, done, "Taahhütnameler hazırlanıyor...")
                taahhut_ext = ".pdf" if config.get("taahhut_format") == "PDF" else ".xlsx"
                taahhut_label = "PDF" if taahhut_ext == ".pdf" else "Excel"
                try:
                    saved_files.extend(tum_taahhutnameleri_olustur(self.veri, folders["taahhutnameler"], taahhut_ext))
                except Exception as exc:
                    errors.append(f"Taahhütnameler {taahhut_label}: {exc}")
                done += 1
                self.cikti_merkezi_progress(progress, done, "Taahhütname adımı tamamlandı")

            if config.get("ekler") and not cancel_state.get("cancelled"):
                self.cikti_merkezi_progress(progress, done, "Ekler PDF hazırlanıyor...")
                try:
                    tutanak_path = os.path.join(folders["ekler"], tutanak_dosya_adi(self.veri, ".docx"))
                    tutanaklari_olustur(self.veri, tutanak_path, getattr(self, "word_img_sondaj", None))
                    saved_files.append(tutanak_path)
                    abs_tutanak = os.path.normcase(os.path.abspath(tutanak_path))
                    for set_key in (EK_SET_NORMAL, EK_SET_ARAZI_DENEYLI):
                        files = ek_icerik_haritasi(self.veri, set_key).setdefault("10", [])
                        existing = {os.path.normcase(os.path.abspath(item)) for item in files if item}
                        if abs_tutanak not in existing:
                            files.append(tutanak_path)
                    ek_path = os.path.join(folders["ekler"], ek_pdf_dosya_adi(self.veri))
                    info = ekler_pdf_olustur(self.veri, ek_path)
                    saved_files.append(info["path"])
                    for warning in info.get("warnings", []):
                        errors.append(f"Ekler: {warning}")
                except Exception as exc:
                    errors.append(f"Ekler: {exc}")
                done += 1
                self.cikti_merkezi_progress(progress, done, "Ekler adımı tamamlandı")

            cancelled = bool(cancel_state.get("cancelled"))
            summary_path = self.cikti_merkezi_ozet_yaz(base_folder, saved_files, errors, cancelled)
            if cancelled:
                msg = f"Çıktı Merkezi iptal edildi.\n\nKaydedilen dosya: {len(saved_files)}\nÖzet: {summary_path}"
                self.cikti_merkezi_bitti(progress, msg, "warning")
                self.set_status(f"Çıktı Merkezi iptal edildi: {len(saved_files)} dosya.", level="warning")
            elif errors:
                msg = f"Çıktı Merkezi tamamlandı, bazı uyarılar var.\n\nKaydedilen dosya: {len(saved_files)}\nUyarı/Hata: {len(errors)}\nÖzet: {summary_path}"
                self.cikti_merkezi_bitti(progress, msg, "warning")
                self.set_status(f"Çıktı Merkezi tamamlandı: {len(saved_files)} dosya, {len(errors)} uyarı/hata.", level="warning")
            else:
                msg = f"Çıktılar hazır:\n{base_folder}\n\nKaydedilen dosya: {len(saved_files)}\nÖzet: {summary_path}"
                self.cikti_merkezi_bitti(progress, msg, "success")
                self.set_status(f"Çıktı Merkezi tamamlandı: {len(saved_files)} dosya.", level="success")
        except Exception as exc:
            self.cikti_merkezi_bitti(progress, str(exc), "error")
            self.set_status(f"Çıktı Merkezi hatası: {exc}", level="error")
