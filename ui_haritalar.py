# Dosya: RaporPro/ui_haritalar.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sabitler import COLOR_BG, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD, PROJE_KLASORU
from performans import perf_tracked
from harita_referans import kml_koordinatlari_oku
from harita_resim_cache import display_image_read
from resim_isaretleyici import ResimIsaretleyici
from tkgm_kml import tkgm_parsel_kml_olustur
from yerbuldurur_motoru import YerbuldururMotoru


class HaritalarSekmesiMixin:
    def p_haritalar(self, p):
        outer = ttk.Frame(p, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Haritalar", font=("Segoe UI", 15, "bold"), foreground=COLOR_PRIMARY).pack(side="left")
        self.lbl_harita_kml = ttk.Label(header, text="")
        self.lbl_harita_kml.pack(side="right")

        setup = ttk.LabelFrame(outer, text="Hazırlık", padding=12)
        setup.pack(fill="x", pady=(0, 10))

        kml_row = ttk.Frame(setup)
        kml_row.pack(fill="x", pady=4)
        ttk.Label(kml_row, text="KML Sınır", width=18, font=FONT_BOLD).pack(side="left", padx=(0, 8))
        self.lbl_harita_kml_detay = ttk.Label(kml_row, text="-", foreground="#555555")
        self.lbl_harita_kml_detay.pack(side="left", fill="x", expand=True)
        self.modern_button(kml_row, text="KML Seç", command=self.kml_sec, role="neutral", outline=True, width=16).pack(side="right")

        self.modern_button(kml_row, text="TKGM'den Al", command=self.tkgm_kml_al, role="accent", outline=True, width=16).pack(side="right", padx=(0, 6))

        form_frame = ttk.Frame(setup)
        form_frame.pack(fill="x", pady=4)
        ttk.Label(form_frame, text="Formasyon", width=18, font=FONT_BOLD).pack(side="left", padx=(0, 8))
        self.cmb_formasyon = ttk.Combobox(
            form_frame,
            values=[
                "Qal (Alüvyon)",
                "Tmal (Alçıtepe Üyesi)",
                "Tmçd (Çamrakdere Üyesi)",
                "Tmki (Kirazlı Üyesi)",
                "Tmçk (Çanakkale Formasyonu)",
            ],
            width=30,
            state="readonly",
        )
        self.cmb_formasyon.pack(side="left", fill="x", expand=True)
        self.cmb_formasyon.current(0)

        actions = ttk.LabelFrame(outer, text="Çizim", padding=12)
        actions.pack(fill="x", pady=(0, 10))
        action_grid = ttk.Frame(actions)
        action_grid.pack(fill="x")

        cards = []
        for title, status_attr, color, command in [
            ("Vaziyet Planı", "lbl_harita_vaziyet", "#3498DB", lambda: self.harita_cizici_ac("vaziyet")),
            ("Müh. Jeoloji", "lbl_harita_jeoloji", "#E67E22", lambda: self.harita_cizici_ac("jeoloji")),
            ("Yerbuldurur", "lbl_harita_yerbuldurur", "#9B59B6", self.yerbuldurur_ac),
        ]:
            card = ttk.Frame(action_grid, padding=6)
            self.modern_button(card, text=title, role=self._role_from_color(color, "accent"), pady=12, command=command).pack(fill="x")
            status = ttk.Label(card, text="-", foreground="#555555", anchor="center")
            status.pack(fill="x", pady=(6, 0))
            setattr(self, status_attr, status)
            cards.append(card)
        self.responsive_widget_grid(action_grid, cards, min_width=210, max_cols=3, padx=6, pady=4)

        self.harita_durum_yenile()

    def harita_durum_yenile(self):
        kml_path = getattr(self, "kml_path", None)
        kml_secili = bool(kml_path)
        kml_ok = bool(kml_secili and os.path.exists(kml_path))
        if kml_ok:
            kml_text = os.path.basename(kml_path)
            kml_color = COLOR_SUCCESS
        elif kml_secili:
            kml_text = f"{os.path.basename(kml_path)} (bulunamadı)"
            kml_color = COLOR_WARNING
        else:
            kml_text = "KML seçilmedi"
            kml_color = "red"
        for attr in ("lbl_harita_kml", "lbl_harita_kml_detay"):
            if hasattr(self, attr):
                getattr(self, attr).config(text=kml_text, foreground=kml_color)

        harita_cizimleri = self.veri.get("harita_cizimleri", {}) if isinstance(self.veri, dict) else {}
        yerbuldurur_empty = "KML bekliyor" if not kml_secili else ("KML dosyası bulunamadı" if not kml_ok else "Çizim yok")
        status_map = [
            ("lbl_harita_vaziyet", bool(harita_cizimleri.get("vaziyet") or getattr(self, "word_img_sondaj", None)), "Hazır", "Çizim yok"),
            ("lbl_harita_jeoloji", bool(harita_cizimleri.get("jeoloji") or getattr(self, "img_mjh", None)), "Hazır", "Çizim yok"),
            ("lbl_harita_yerbuldurur", bool(harita_cizimleri.get("yerbuldurur") or getattr(self, "img_yer", None)), "Hazır", yerbuldurur_empty),
        ]
        for attr, ok, ok_text, empty_text in status_map:
            if hasattr(self, attr):
                getattr(self, attr).config(text=ok_text if ok else empty_text, foreground=COLOR_SUCCESS if ok else COLOR_WARNING)

    def tkgm_kml_al(self):
        self.guncelle_veri_objesi()
        kunye = dict(self.veri.get("kunye", {}))
        missing = []
        if not (kunye.get("il") or "").strip():
            missing.append("İl")
        if not (kunye.get("ilce") or "").strip():
            missing.append("İlçe")
        if not (kunye.get("mah") or "").strip():
            missing.append("Mahalle/Köy")
        if not (kunye.get("par") or "").strip():
            missing.append("Parsel")
        if missing:
            messagebox.showwarning(
                "TKGM KML",
                "TKGM'den KML alabilmek için Künye sekmesinde şu alanlar dolu olmalı:\n- "
                + "\n- ".join(missing),
            )
            return

        output_dir = self._tkgm_kml_output_dir()
        progress = tk.Toplevel(self.root)
        self.pencere_hazirla(progress, "TKGM KML", "380x130", (360, 120), modal=False)
        ttk.Label(progress, text="TKGM Parsel Sorgu'dan KML alınıyor...", font=FONT_BOLD).pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(progress, text=f"{kunye.get('il', '')} / {kunye.get('ilce', '')} / {kunye.get('mah', '')}", foreground="#555555").pack(anchor="w", padx=14, pady=(0, 8))
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=14, pady=(0, 12))
        bar.start(12)

        def worker():
            return tkgm_parsel_kml_olustur(kunye, output_dir)

        def success(result):
            if progress.winfo_exists():
                progress.destroy()
            self._tkgm_kml_sonuc_isle(result)

        def error(exc):
            if progress.winfo_exists():
                progress.destroy()
            messagebox.showerror("TKGM KML", f"KML alınamadı:\n{exc}")

        self.arka_plan_gorevi_baslat(
            "TKGM KML al",
            worker,
            status_start="TKGM KML alınıyor.",
            status_success="TKGM KML alındı.",
            status_error="TKGM KML alınamadı: {error}",
            on_success=success,
            on_error=error,
        )

    def _tkgm_kml_output_dir(self):
        active_path = getattr(self, "aktif_dosya_yolu", None)
        if active_path:
            return os.path.join(os.path.dirname(active_path), "03_Haritalar")
        return os.path.join(PROJE_KLASORU, "TKGM_KML")

    def _tkgm_kml_sonuc_isle(self, result):
        path = result.get("path")
        if not path:
            messagebox.showerror("TKGM KML", "TKGM KML dosya yolu oluşturulamadı.")
            return

        self.kml_path = path
        self.veri.setdefault("dosyalar", {})["kml_path"] = path

        center = result.get("center")
        if center and hasattr(self, "e_arazi"):
            lat, lon = center
            for key, value in (("alan_y", lat), ("alan_x", lon)):
                entry = self.e_arazi.get(key)
                if entry is not None and not entry.get().strip():
                    entry.delete(0, tk.END)
                    entry.insert(0, f"{value:.8f}")
                    self.veri.setdefault("arazi", {})[key] = f"{value:.8f}"

        self.kml_etiket_guncelle()
        self.harita_durum_yenile()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        if hasattr(self, "otomatik_kaydet"):
            self.otomatik_kaydet()
        self.set_status(f"TKGM KML bağlandı: {os.path.basename(path)}", level="success")
        messagebox.showinfo("TKGM KML", f"KML oluşturuldu ve projeye bağlandı:\n{path}")

    @perf_tracked("map.image_marker_open")
    def harita_cizici_ac(self, harita_tipi):
        self.guncelle_veri_objesi()
        map_data = {
            "sondaj": [{"no": s.get("no", ""), "y": s.get("y", "-"), "x": s.get("x", "-")} for s in self.veri["sondaj"]],
            "ss": [{"ad": s.get("ad", ""), "coords": s.get("coords", ["-"] * 6)} for s in self.veri["jeofizik"]["ss_list"]],
            "mt": [{"no": m.get("no", ""), "y": m.get("y", "-"), "x": m.get("x", "-")} for m in self.veri["jeofizik"]["mt_list"]],
        }
        harita_data = self.veri.get("harita_cizimleri", {}).get(harita_tipi, {})
        img_path = harita_data.get("img_path", "")

        if img_path and os.path.exists(img_path):
            cevap = messagebox.askyesno(
                "Kayıtlı Çizim Bulundu",
                f"Bu proje için daha önceden kaydedilmiş {harita_tipi.upper()} çizimi bulundu.\nKaldığınız yerden devam etmek ister misiniz?",
            )
            if not cevap:
                img_path = filedialog.askopenfilename(title="Yeni Altlık Resmini Seçin", filetypes=[("Resim Dosyaları", "*.jpg;*.png;*.jpeg")])
                harita_data = None
        else:
            img_path = filedialog.askopenfilename(title="Altlık Resmini Seçin", filetypes=[("Resim Dosyaları", "*.jpg;*.png;*.jpeg")])
            harita_data = None

        if img_path:
            formasyon_kod = self.cmb_formasyon.get().split(" ")[0]
            self.harita_altlik_hazirla_ve_ac(harita_tipi, img_path, map_data, formasyon_kod, harita_data)

    def harita_altlik_hazirla_ve_ac(self, harita_tipi, img_path, map_data, formasyon_kod, harita_data):
        progress = tk.Toplevel(self.root)
        self.pencere_hazirla(progress, "Harita Altlığı", "360x120", (340, 110), modal=False)
        ttk.Label(progress, text="Harita altlığı hazırlanıyor...", font=FONT_BOLD).pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(progress, text=os.path.basename(img_path), foreground="#555555").pack(anchor="w", padx=14, pady=(0, 8))
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=14, pady=(0, 12))
        bar.start(12)

        def worker():
            display_image_read(img_path)
            return kml_koordinatlari_oku(getattr(self, "kml_path", None))

        def open_marker(kml_points):
            if progress.winfo_exists():
                progress.destroy()
            ResimIsaretleyici(
                self.root,
                img_path=img_path,
                map_data=map_data,
                harita_tipi=harita_tipi,
                formasyon=formasyon_kod,
                kml_points=kml_points,
                word_callback=self.harita_word_aktar,
                save_callback=lambda data: self.harita_cizim_kaydet(harita_tipi, data),
                saved_state=harita_data,
            )

        def show_error(exc):
            if progress.winfo_exists():
                progress.destroy()
            messagebox.showerror("Harita Altlığı", f"Harita altlığı hazırlanamadı:\n{exc}")

        self.arka_plan_gorevi_baslat(
            "Harita altlığı hazırla",
            worker,
            status_start="Harita altlığı arka planda hazırlanıyor.",
            status_success="Harita altlığı hazırlandı.",
            status_error="Harita altlığı hazırlanamadı: {error}",
            on_success=open_marker,
            on_error=show_error,
        )

    def harita_cizim_kaydet(self, harita_tipi, data):
        if "harita_cizimleri" not in self.veri:
            self.veri["harita_cizimleri"] = {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}}
        self.veri["harita_cizimleri"][harita_tipi] = data
        self.harita_durum_yenile()
        self.veri_kaydet()
        self.set_status(f"{harita_tipi.upper()} çizim verileri projeye kaydedildi.", level="success")

    def harita_word_aktar(self, path_son=None, path_jeo=None, path_mjh=None, harita_tipi="vaziyet"):
        if path_mjh:
            self.img_mjh = path_mjh
            if hasattr(self, "lbl_mjh"):
                self.lbl_mjh.config(text=os.path.basename(path_mjh), foreground=COLOR_SUCCESS)
            self.harita_durum_yenile()
            self.veri_kaydet()
            self.set_status("Mühendislik jeolojisi haritası RESIM:MJH için hafızaya alındı.", level="success")
            return
        if path_son:
            self.word_img_sondaj = path_son
        if path_jeo:
            self.word_img_jeofizik = path_jeo
        self.harita_durum_yenile()
        self.veri_kaydet()
        self.set_status("Sondaj ve Jeofizik haritaları Word raporu için hafızaya alındı.", level="success")

    @perf_tracked("map.yerbuldurur_open")
    def yerbuldurur_ac(self):
        if not self.kml_path or not os.path.exists(self.kml_path):
            messagebox.showerror("Hata", "Lütfen önce üst menüden bir KML Sınır Dosyası seçin!")
            return

        harita_data = self.veri.get("harita_cizimleri", {}).get("yerbuldurur", {})
        YerbuldururMotoru(self.root, kml_path=self.kml_path, saved_state=harita_data, save_callback=self.yerbuldurur_kaydet)

    def yerbuldurur_kaydet(self, state, img_path):
        if "harita_cizimleri" not in self.veri:
            self.veri["harita_cizimleri"] = {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}}
        self.veri["harita_cizimleri"]["yerbuldurur"] = state
        self.img_yer = img_path
        if hasattr(self, "lbl_yer"):
            self.lbl_yer.config(text=os.path.basename(img_path), foreground=COLOR_SUCCESS)
        self.harita_durum_yenile()
        self.veri_kaydet()
        self.set_status("Yerbuldurur haritası projeye kaydedildi ve Rapor sekmesine aktarıldı.", level="success")
