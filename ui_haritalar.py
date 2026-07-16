# Dosya: RaporPro/ui_haritalar.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from harita_motoru import DEFAULT_TILE_SERVER, TILE_SERVERS
from harita_referans import kml_koordinatlari_oku, ss_harita_etiketi
from harita_resim_cache import display_image_read
from performans import perf_timer, perf_tracked
from resim_isaretleyici import ResimIsaretleyici
from sabitler import (
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_BOLD,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    PROJE_KLASORU,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from tkgm_kml import tkgm_parsel_kml_olustur
from yerbuldurur_motoru import YerbuldururMotoru


class HaritalarSekmesiMixin:
    @staticmethod
    def harita_koordinat_ozeti(veri):
        """Harita için kullanılabilir koordinat kayıtlarının sayısını döndür."""

        def number(value):
            try:
                return float(str(value).strip().replace(",", "."))
            except (TypeError, ValueError):
                return 0.0

        def pair_ready(y, x):
            return bool(number(y) and number(x))

        veri = veri if isinstance(veri, dict) else {}
        arazi = veri.get("arazi", {}) if isinstance(veri.get("arazi"), dict) else {}
        sondajlar = veri.get("sondaj", []) if isinstance(veri.get("sondaj"), list) else []
        jeofizik = veri.get("jeofizik", {}) if isinstance(veri.get("jeofizik"), dict) else {}
        ss_list = jeofizik.get("ss_list", []) if isinstance(jeofizik.get("ss_list"), list) else []
        mt_list = jeofizik.get("mt_list", []) if isinstance(jeofizik.get("mt_list"), list) else []

        sondaj_ready = sum(pair_ready(item.get("y"), item.get("x")) for item in sondajlar if isinstance(item, dict))
        ss_ready = 0
        for item in ss_list:
            coords = item.get("coords", []) if isinstance(item, dict) else []
            if len(coords) >= 6 and pair_ready(coords[0], coords[1]) and pair_ready(coords[4], coords[5]):
                ss_ready += 1
        mt_ready = sum(pair_ready(item.get("y"), item.get("x")) for item in mt_list if isinstance(item, dict))
        area_ready = int(pair_ready(arazi.get("alan_y"), arazi.get("alan_x")))

        total = 1 + len(sondajlar) + len(ss_list) + len(mt_list)
        ready = area_ready + sondaj_ready + ss_ready + mt_ready
        return {
            "alan": (area_ready, 1),
            "sondaj": (sondaj_ready, len(sondajlar)),
            "ss": (ss_ready, len(ss_list)),
            "mt": (mt_ready, len(mt_list)),
            "ready": ready,
            "total": total,
        }

    @staticmethod
    def harita_dosya_durumu(path, empty_text="Oluşturulmadı"):
        """Harita dosyasının durum seviyesini ve kısa metnini döndür."""
        if path and os.path.isfile(path):
            return "ok", os.path.basename(path)
        if path:
            return "warning", "Dosya bulunamadı"
        return "empty", empty_text

    def p_haritalar(self, p):
        page, _canvas = self.scrollable_page(p, padding=(16, 12))
        page.columnconfigure(0, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Haritalar", style="PageTitle.TLabel").pack(anchor="w")
        self.harita_durum_var = tk.StringVar(value="Harita hazırlığı kontrol ediliyor")
        self.lbl_harita_durum = ttk.Label(title_area, textvariable=self.harita_durum_var, style="Muted.TLabel")
        self.lbl_harita_durum.pack(anchor="w", pady=(2, 0))
        self.modern_button(
            header,
            "Yenile",
            command=self.harita_durum_yenile,
            role="secondary",
            outline=True,
            padx=8,
            pady=4,
        ).grid(row=0, column=1, sticky="e")

        setup = ttk.LabelFrame(page, text="Altlık ve Sınır", padding=(12, 10))
        setup.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        setup.columnconfigure(1, weight=1)

        ttk.Label(setup, text="KML sınırı", font=FONT_UI_BODY_BOLD).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, SPACE_SM),
            pady=SPACE_XS,
        )
        self.lbl_harita_kml_detay = ttk.Label(setup, text="-", style="Muted.TLabel")
        self.lbl_harita_kml_detay.grid(row=0, column=1, sticky="ew", pady=SPACE_XS)
        kml_actions = ttk.Frame(setup)
        kml_actions.grid(row=0, column=2, sticky="e", pady=SPACE_XS)
        self.modern_button(
            kml_actions,
            "KML Seç",
            command=self.kml_sec,
            role="secondary",
            outline=True,
            padx=7,
            pady=4,
        ).pack(side="left", padx=(0, SPACE_XS))
        self.modern_button(
            kml_actions,
            "TKGM'den Al",
            command=self.tkgm_kml_al,
            role="accent",
            outline=True,
            padx=7,
            pady=4,
        ).pack(side="left")

        option_row = ttk.Frame(setup)
        option_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=SPACE_XS)
        option_row.columnconfigure(1, weight=1)
        option_row.columnconfigure(3, weight=1)
        ttk.Label(option_row, text="Uydu altlığı", font=FONT_UI_BODY_BOLD).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, SPACE_SM),
        )
        current_tile = self.veri.get("ayarlar", {}).get("harita_altlik", DEFAULT_TILE_SERVER)
        if current_tile not in TILE_SERVERS:
            current_tile = DEFAULT_TILE_SERVER
        self.harita_altlik_var = tk.StringVar(value=current_tile)
        self.cmb_harita_altlik = ttk.Combobox(
            option_row,
            textvariable=self.harita_altlik_var,
            values=list(TILE_SERVERS.keys()),
            state="readonly",
            width=28,
        )
        self.cmb_harita_altlik.grid(row=0, column=1, sticky="ew", padx=(0, SPACE_MD))
        self.cmb_harita_altlik.bind("<<ComboboxSelected>>", self.harita_altlik_secildi)
        ttk.Label(option_row, text="Jeoloji formasyonu", font=FONT_UI_BODY_BOLD).grid(
            row=0,
            column=2,
            sticky="w",
            padx=(0, SPACE_SM),
        )
        self.cmb_formasyon = ttk.Combobox(
            option_row,
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
        self.cmb_formasyon.grid(row=0, column=3, sticky="ew")
        self.cmb_formasyon.current(0)

        coordinates = ttk.LabelFrame(page, text="Çalışma Noktaları", padding=(12, 10))
        coordinates.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_SM))
        coord_header = ttk.Frame(coordinates)
        coord_header.pack(fill="x", pady=(0, SPACE_XS))
        self.lbl_harita_koordinat_ozet = ttk.Label(coord_header, text="-", font=FONT_UI_BODY_BOLD)
        self.lbl_harita_koordinat_ozet.pack(side="left")
        self.modern_button(
            coord_header,
            "Tüm Koordinatları Seç",
            command=self.toplu_harita_ac,
            role="primary",
            padx=8,
            pady=4,
        ).pack(side="right")

        coord_grid = ttk.Frame(coordinates)
        coord_grid.pack(fill="x")
        self.harita_coord_labels = {}
        coord_cards = []
        for key, title in (
            ("alan", "Çalışma Alanı"),
            ("sondaj", "Sondajlar"),
            ("ss", "Sismik Serimler"),
            ("mt", "Mikrotremör"),
        ):
            card = tk.Frame(
                coord_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_MD,
                pady=SPACE_SM,
            )
            tk.Label(
                card,
                text=title,
                bg=COLOR_SURFACE,
                fg=COLOR_PRIMARY,
                font=FONT_UI_BODY_BOLD,
            ).pack(anchor="w")
            status = tk.Label(
                card,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
            )
            status.pack(anchor="w", pady=(2, 0))
            self.harita_coord_labels[key] = status
            coord_cards.append(card)
        self.responsive_widget_grid(coord_grid, coord_cards, min_width=180, max_cols=4, padx=4, pady=4)

        actions = ttk.LabelFrame(page, text="Harita Çizimi", padding=(12, 10))
        actions.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_SM))
        action_grid = ttk.Frame(actions)
        action_grid.pack(fill="x")

        cards = []
        for title, status_attr, role, command in [
            ("Araştırma Noktaları Vaziyet Planı", "lbl_harita_vaziyet", "accent", lambda: self.harita_cizici_ac("vaziyet")),
            ("Mühendislik Jeolojisi", "lbl_harita_jeoloji", "warning", lambda: self.harita_cizici_ac("jeoloji")),
            ("Yerbuldurur Haritası", "lbl_harita_yerbuldurur", "primary", self.yerbuldurur_ac),
        ]:
            card = tk.Frame(
                action_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_SM,
                pady=SPACE_SM,
            )
            self.modern_button(card, text=title, role=role, pady=9, command=command).pack(fill="x")
            status = tk.Label(
                card,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
                anchor="center",
            )
            status.pack(fill="x", pady=(6, 0))
            setattr(self, status_attr, status)
            cards.append(card)
        self.responsive_widget_grid(action_grid, cards, min_width=230, max_cols=3, padx=4, pady=4)

        outputs = ttk.LabelFrame(page, text="Rapor Çıktıları", padding=(12, 10))
        outputs.grid(row=4, column=0, sticky="ew")
        output_header = ttk.Frame(outputs)
        output_header.pack(fill="x", pady=(0, SPACE_XS))
        self.lbl_harita_cikti_ozet = ttk.Label(output_header, text="-", font=FONT_UI_BODY_BOLD)
        self.lbl_harita_cikti_ozet.pack(side="left")
        self.modern_button(
            output_header,
            "Rapor Sekmesine Git",
            command=lambda: self.nb.select(self.tab_rapor),
            role="secondary",
            outline=True,
            padx=7,
            pady=4,
        ).pack(side="right")

        output_grid = ttk.Frame(outputs)
        output_grid.pack(fill="x")
        self.harita_output_labels = {}
        output_cards = []
        for key, title in (
            ("sondaj", "Sondaj Lokasyon"),
            ("jeofizik", "Jeofizik Lokasyon"),
            ("mjh", "Mühendislik Jeolojisi"),
            ("yer", "Yerbuldurur"),
        ):
            card = tk.Frame(
                output_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_MD,
                pady=SPACE_SM,
            )
            tk.Label(
                card,
                text=title,
                bg=COLOR_SURFACE,
                fg=COLOR_PRIMARY,
                font=FONT_UI_BODY_BOLD,
            ).pack(anchor="w")
            status = tk.Label(
                card,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
                anchor="w",
                justify="left",
            )
            status.pack(fill="x", pady=(2, 0))
            self.harita_output_labels[key] = status
            output_cards.append(card)
        self.responsive_widget_grid(output_grid, output_cards, min_width=190, max_cols=4, padx=4, pady=4)

        self.harita_durum_yenile()

    def harita_durum_yenile(self):
        kml_path = getattr(self, "kml_path", None)
        kml_state, kml_text = self.harita_dosya_durumu(kml_path, "KML seçilmedi")
        status_colors = {"ok": COLOR_SUCCESS, "warning": COLOR_WARNING, "empty": COLOR_DANGER}
        kml_color = status_colors[kml_state]
        if hasattr(self, "lbl_harita_kml_detay"):
            self.lbl_harita_kml_detay.config(text=kml_text, foreground=kml_color)

        tile_name = self.veri.get("ayarlar", {}).get("harita_altlik", DEFAULT_TILE_SERVER)
        if tile_name not in TILE_SERVERS:
            tile_name = DEFAULT_TILE_SERVER
        if hasattr(self, "harita_altlik_var") and self.harita_altlik_var.get() != tile_name:
            self.harita_altlik_var.set(tile_name)
        if hasattr(self, "lbl_harita_altlik"):
            self.lbl_harita_altlik.config(text=f"Seçili: {tile_name}", foreground=COLOR_SUCCESS)

        coord_summary = self.harita_koordinat_ozeti(getattr(self, "veri", {}))
        coord_ready = coord_summary["ready"]
        coord_total = coord_summary["total"]
        coord_all_ready = bool(coord_total and coord_ready == coord_total)
        if hasattr(self, "lbl_harita_koordinat_ozet"):
            self.lbl_harita_koordinat_ozet.config(
                text=f"Koordinatlar: {coord_ready}/{coord_total} hazır",
                foreground=COLOR_SUCCESS if coord_all_ready else COLOR_WARNING,
            )
        for key, label in getattr(self, "harita_coord_labels", {}).items():
            ready, total = coord_summary[key]
            if total == 0:
                text, color = "Kayıt yok", COLOR_TEXT_MUTED
            else:
                text = f"{ready}/{total} hazır"
                color = COLOR_SUCCESS if ready == total else COLOR_WARNING
            label.config(text=text, foreground=color)

        harita_cizimleri = self.veri.get("harita_cizimleri", {}) if isinstance(self.veri, dict) else {}
        drawing_map = (
            (
                "lbl_harita_vaziyet",
                "vaziyet",
                getattr(self, "word_img_sondaj", None) or getattr(self, "word_img_jeofizik", None),
                "Çizim yok",
            ),
            ("lbl_harita_jeoloji", "jeoloji", getattr(self, "img_mjh", None), "Çizim yok"),
            (
                "lbl_harita_yerbuldurur",
                "yerbuldurur",
                getattr(self, "img_yer", None),
                "KML bekliyor" if kml_state != "ok" else "Çizim yok",
            ),
        )
        for attr, key, output_path, empty_text in drawing_map:
            if not hasattr(self, attr):
                continue
            state = harita_cizimleri.get(key, {}) if isinstance(harita_cizimleri.get(key), dict) else {}
            state_path = state.get("img_path")
            if state_path and os.path.isfile(state_path):
                text, color = "Düzenleme kaydı hazır", COLOR_SUCCESS
            elif output_path and os.path.isfile(output_path):
                text = "Rapor çıktısı hazır" if not state else "Rapor çıktısı hazır · altlık eksik"
                color = COLOR_SUCCESS if not state else COLOR_WARNING
            elif state:
                text, color = "Altlık dosyası bulunamadı", COLOR_WARNING
            else:
                text, color = empty_text, COLOR_WARNING
            getattr(self, attr).config(text=text, foreground=color)

        output_paths = {
            "sondaj": getattr(self, "word_img_sondaj", None),
            "jeofizik": getattr(self, "word_img_jeofizik", None),
            "mjh": getattr(self, "img_mjh", None),
            "yer": getattr(self, "img_yer", None),
        }
        output_ready = 0
        for key, label in getattr(self, "harita_output_labels", {}).items():
            state, text = self.harita_dosya_durumu(output_paths.get(key))
            if state == "ok":
                output_ready += 1
            label.config(text=text, foreground=status_colors[state])
        if hasattr(self, "lbl_harita_cikti_ozet"):
            self.lbl_harita_cikti_ozet.config(
                text=f"Word için hazır: {output_ready}/{len(output_paths)}",
                foreground=COLOR_SUCCESS if output_ready == len(output_paths) else COLOR_WARNING,
            )

        if hasattr(self, "harita_durum_var"):
            kml_summary = "KML hazır" if kml_state == "ok" else "KML eksik"
            self.harita_durum_var.set(
                f"{kml_summary} · Koordinatlar {coord_ready}/{coord_total} · Rapor çıktıları {output_ready}/{len(output_paths)}"
            )
            self.lbl_harita_durum.configure(
                foreground=COLOR_SUCCESS
                if kml_state == "ok" and coord_all_ready and output_ready == len(output_paths)
                else COLOR_WARNING
            )

    def harita_altlik_secildi(self, _event=None):
        self.harita_altlik_kaydet(self.harita_altlik_var.get(), notify=True)

    def harita_altlik_kaydet(self, name, notify=False):
        if name not in TILE_SERVERS:
            name = DEFAULT_TILE_SERVER
        self.veri.setdefault("ayarlar", {})["harita_altlik"] = name
        if hasattr(self, "harita_altlik_var") and self.harita_altlik_var.get() != name:
            self.harita_altlik_var.set(name)
        if hasattr(self, "lbl_harita_altlik"):
            self.lbl_harita_altlik.config(text=f"Seçili: {name}", foreground=COLOR_SUCCESS)
        if notify:
            self.set_status(f"Harita altlığı seçildi: {name}", level="success")

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

    def harita_cizici_ac(self, harita_tipi):
        with perf_timer("map.image_marker_data_prepare", harita_tipi):
            self.guncelle_veri_objesi()
            map_data = {
                "sondaj": [{"no": s.get("no", ""), "y": s.get("y", "-"), "x": s.get("x", "-")} for s in self.veri["sondaj"]],
                "ss": [
                    {"ad": ss_harita_etiketi(s.get("ad", ""), idx), "coords": s.get("coords", ["-"] * 6)}
                    for idx, s in enumerate(self.veri["jeofizik"]["ss_list"])
                ],
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
            with perf_timer("map.kml_reference_read", os.path.basename(str(getattr(self, "kml_path", "") or ""))):
                return kml_koordinatlari_oku(getattr(self, "kml_path", None))

        def open_marker(kml_points):
            if progress.winfo_exists():
                progress.destroy()
            with perf_timer("map.image_marker_window_open", harita_tipi):
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
