import tkinter as tk
from tkinter import Listbox, Toplevel, messagebox, ttk

from harita_referans import kml_koordinatlari_oku
from kesit_kalite import build_section_quality_report, format_section_quality_report
from ui_kesit_yardimci import kesit_hatti_sondaj_sirasi, kesit_kayit_dosya_adi
from ui_kesit_onizleme import KesitOnizlemeMixin
from sabitler import COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD
from yardimcilar import safe_float


class KesitCizimMixin(KesitOnizlemeMixin):
    def _kesit_section_signature(self, options):
        def norm(value):
            text = str(value or "").strip()
            return text if text else "-"

        def norm_float(value):
            parsed = safe_float(value)
            return f"{parsed:.4f}" if parsed else "0"

        selected = options.get("selected_sondajlar") or []
        selected_key = "|".join(norm(item) for item in selected)
        mode = norm(options.get("mode", "schematic"))
        geometry_parts = [
            mode,
            norm(options.get("section_engine", "v1")),
            selected_key,
            norm_float(options.get("vertical_exaggeration", 1.0)),
            norm(options.get("print_scale_enabled", False)),
            norm(options.get("print_page_size", "A4 Yatay")),
            norm_float(options.get("horizontal_scale", 500.0)),
            norm_float(options.get("vertical_scale", 100.0)),
            norm_float(options.get("corr_tolerance", 0.0)),
            norm_float(options.get("dx_default", 25.0)),
            norm_float(options.get("well_width", 2.0)),
            norm(options.get("auto_lens", True)),
            norm(options.get("two_well_lens", True)),
            norm_float(options.get("lens_max_thickness", 2.0)),
            norm_float(options.get("lens_closure_ratio", 0.58)),
        ]
        if mode == "line_projection":
            geometry_parts.extend([
                norm(options.get("line_start_no")),
                norm(options.get("line_end_no")),
                norm_float(options.get("line_start_y")),
                norm_float(options.get("line_start_x")),
                norm_float(options.get("line_end_y")),
                norm_float(options.get("line_end_x")),
            ])
        return "::".join(geometry_parts)

    def _kesit_manual_edits_for_options(self, saved_kesit, options):
        signature = options.get("section_signature") or self._kesit_section_signature(options)
        by_section = saved_kesit.get("manual_edits_by_section")
        if isinstance(by_section, dict):
            return dict(by_section.get(signature) or {})
        legacy = saved_kesit.get("manual_edits") or options.get("manual_edits") or {}
        return dict(legacy) if isinstance(legacy, dict) else {}

    def _kesit_ayarlari_kaydet(self, options):
        saved = dict(self.veri.get("kesit_ayarlari") or {})
        by_section = saved.get("manual_edits_by_section")
        if isinstance(by_section, dict):
            by_section = dict(by_section)
        else:
            by_section = {}
        saved.update(options)
        if by_section:
            saved["manual_edits_by_section"] = by_section
        else:
            saved.pop("manual_edits_by_section", None)
        if "manual_edits" not in options:
            saved.pop("manual_edits", None)
        self.veri["kesit_ayarlari"] = saved
        return saved

    def kesit_kalite_penceresi(self, parent, sondajlar, options=None):
        report = build_section_quality_report(sondajlar, options or {})
        win = Toplevel(parent or self.root)
        self.pencere_hazirla(win, "Kesit Kalite Kontrol", "820x560", (720, 460), modal=True)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        summary = ttk.Label(
            frame,
            text=f"{len(report.get('errors', []))} hata | {len(report.get('warnings', []))} uyarı | {len(report.get('info', []))} bilgi",
            font=FONT_BOLD,
        )
        summary.pack(anchor="w", pady=(0, 6))
        txt = tk.Text(frame, wrap="word", font=("Consolas", 9))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", format_section_quality_report(report))
        txt.config(state="disabled")
        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Kapat", command=win.destroy).pack(side="right")
        level = "success"
        if report.get("errors"):
            level = "error"
        elif report.get("warnings"):
            level = "warning"
        self.set_status(
            f"Kesit kalite kontrol: {len(report.get('errors', []))} hata, {len(report.get('warnings', []))} uyarı.",
            level=level,
        )
        return report

    def kesit_secim_penceresi(self):
        self.sondaj_verilerini_kaydet()
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Kesit Seçimi", "780x740", (740, 620), modal=True)
        saved_kesit = self.veri.get("kesit_ayarlari", {})

        section_nb = ttk.Notebook(win)
        section_nb.pack(fill="both", expand=True, padx=10, pady=(8, 3))
        tab_sondajlar = ttk.Frame(section_nb, padding=8)
        tab_ayarlar = ttk.Frame(section_nb, padding=8)
        tab_hat = ttk.Frame(section_nb, padding=8)
        section_nb.add(tab_sondajlar, text="Sondajlar")
        section_nb.add(tab_ayarlar, text="Çizim / Etiket / Export")
        section_nb.add(tab_hat, text="Kesit Hattı")

        top = ttk.LabelFrame(tab_sondajlar, text="Sondajlar", padding=10)
        top.pack(fill="both", expand=True)
        lb = Listbox(top, selectmode=tk.MULTIPLE, height=5, exportselection=False)
        lb.pack(fill="both", expand=True)
        sondaj_labels = [s.get("no", "Isimsiz") for s in self.veri["sondaj"]]
        for s in self.veri["sondaj"]:
            lb.insert(tk.END, s.get("no", "Isimsiz"))
        select_btns = ttk.Frame(top)
        select_btns.pack(fill="x", pady=(6, 0))

        def tum_sondajlari_sec():
            lb.selection_set(0, tk.END)

        def secimi_temizle():
            lb.selection_clear(0, tk.END)

        def son_kullanilani_sec():
            lb.selection_clear(0, tk.END)
            saved_selected = set(saved_kesit.get("selected_sondajlar") or [])
            if not saved_selected:
                self.set_status("Kayıtlı kesit sondaj seçimi yok.", level="info")
                return
            count = 0
            for idx, label in enumerate(sondaj_labels):
                if label in saved_selected:
                    lb.selection_set(idx)
                    count += 1
            self.set_status(f"Son kullanılan kesit seçimi yüklendi: {count} sondaj.", level="info")

        ttk.Button(select_btns, text="Son Kullanılanı Seç", command=son_kullanilani_sec).pack(side="left", padx=(0, 5))
        ttk.Button(select_btns, text="Tümünü Seç", command=tum_sondajlari_sec).pack(side="left", padx=5)
        ttk.Button(select_btns, text="Temizle", command=secimi_temizle).pack(side="left", padx=5)

        opt = ttk.LabelFrame(tab_ayarlar, text="Kesit Ayarları", padding=10)
        opt.pack(fill="both", expand=True)
        mode_var = tk.StringVar(value=saved_kesit.get("mode", "line_projection"))
        section_engine_value = str(saved_kesit.get("section_engine", "v1") or "v1").lower()
        section_engine_var = tk.StringVar(
            value="V2 (Deneysel)" if section_engine_value == "v2" else "V1 (Stabil)"
        )
        ttk.Radiobutton(opt, text="Kesit hattı (Strater tarzı station/offset)", variable=mode_var, value="line_projection").grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Radiobutton(opt, text="Gerçek mesafe (seçilen sıraya göre)", variable=mode_var, value="true_distance").grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Radiobutton(opt, text="Şematik (eşit aralık)", variable=mode_var, value="schematic").grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(opt, text="Kesit motoru").grid(row=0, column=2, sticky="w", padx=5, pady=(2, 0))
        cmb_section_engine = ttk.Combobox(
            opt,
            textvariable=section_engine_var,
            values=("V1 (Stabil)", "V2 (Deneysel)"),
            width=16,
            state="readonly",
        )
        cmb_section_engine.grid(row=1, column=2, sticky="w", padx=5, pady=(0, 2))
        ttk.Label(opt, text="Düşey abartı").grid(row=3, column=0, sticky="e", padx=5, pady=4)
        e_ve = ttk.Entry(opt, width=12); e_ve.insert(0, saved_kesit.get("vertical_exaggeration", "1.0")); e_ve.grid(row=3, column=1, sticky="w", padx=5, pady=4)
        print_scale_var = tk.BooleanVar(value=saved_kesit.get("print_scale_enabled", False))
        print_page_var = tk.StringVar(value=saved_kesit.get("print_page_size", "A4 Yatay"))
        horizontal_scale_var = tk.StringVar(value=str(saved_kesit.get("horizontal_scale", "500")))
        vertical_scale_var = tk.StringVar(value=str(saved_kesit.get("vertical_scale", "100")))
        print_frame = ttk.LabelFrame(opt, text="Gerçek Baskı Ölçeği", padding=7)
        print_frame.grid(row=0, column=3, rowspan=6, sticky="nw", padx=(14, 5), pady=2)
        ttk.Checkbutton(
            print_frame,
            text="Baskı ölçeğini kullan",
            variable=print_scale_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(print_frame, text="Sayfa").grid(row=1, column=0, sticky="e", padx=(0, 5), pady=3)
        ttk.Combobox(
            print_frame,
            textvariable=print_page_var,
            values=("A4 Yatay", "A3 Yatay"),
            width=12,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(print_frame, text="Yatay 1/").grid(row=2, column=0, sticky="e", padx=(0, 5), pady=3)
        horizontal_scale_combo = ttk.Combobox(
            print_frame,
            textvariable=horizontal_scale_var,
            values=("100", "200", "250", "500", "1000", "2000"),
            width=10,
        )
        horizontal_scale_combo.grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(print_frame, text="Düşey 1/").grid(row=3, column=0, sticky="e", padx=(0, 5), pady=3)
        vertical_scale_combo = ttk.Combobox(
            print_frame,
            textvariable=vertical_scale_var,
            values=("50", "100", "200", "250", "500"),
            width=10,
        )
        vertical_scale_combo.grid(row=3, column=1, sticky="w", pady=3)
        print_ratio_label = ttk.Label(print_frame, text="")
        print_ratio_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))

        def sync_print_scale(event=None):
            horizontal = safe_float(horizontal_scale_var.get()) or 500.0
            vertical = safe_float(vertical_scale_var.get()) or 100.0
            ratio = horizontal / max(vertical, 1.0)
            print_ratio_label.configure(text=f"Düşey abartı: x{ratio:g}")
            if print_scale_var.get():
                e_ve.delete(0, tk.END)
                e_ve.insert(0, f"{ratio:g}")

        horizontal_scale_combo.bind("<<ComboboxSelected>>", sync_print_scale)
        horizontal_scale_combo.bind("<FocusOut>", sync_print_scale)
        vertical_scale_combo.bind("<<ComboboxSelected>>", sync_print_scale)
        vertical_scale_combo.bind("<FocusOut>", sync_print_scale)
        print_scale_var.trace_add("write", lambda *_: sync_print_scale())
        sync_print_scale()
        ttk.Label(opt, text="Eşleşme toleransı (m)").grid(row=4, column=0, sticky="e", padx=5, pady=4)
        e_tol = ttk.Entry(opt, width=12); e_tol.insert(0, saved_kesit.get("corr_tolerance", "3.0")); e_tol.grid(row=4, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(opt, text="Şematik aralık (m)").grid(row=5, column=0, sticky="e", padx=5, pady=4)
        e_dx = ttk.Entry(opt, width=12); e_dx.insert(0, saved_kesit.get("dx_default", "25.0")); e_dx.grid(row=5, column=1, sticky="w", padx=5, pady=4)
        show_consistency_var = tk.BooleanVar(value=saved_kesit.get("show_consistency_labels", True))
        ttk.Checkbutton(opt, text="Sıkılık/kıvam etiketlerini göster", variable=show_consistency_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(opt, text="Etiket min. kalınlık (m)").grid(row=7, column=0, sticky="e", padx=5, pady=4)
        e_label_min = ttk.Entry(opt, width=12); e_label_min.insert(0, saved_kesit.get("consistency_label_min_height", "0.9")); e_label_min.grid(row=7, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(opt, text="Kuyu genişliği").grid(row=8, column=0, sticky="e", padx=5, pady=4)
        e_well_width = ttk.Entry(opt, width=12); e_well_width.insert(0, saved_kesit.get("well_width", "2.0")); e_well_width.grid(row=8, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(opt, text="Lejant ölçeği / kolon").grid(row=9, column=0, sticky="e", padx=5, pady=4)
        e_legend_scale = ttk.Entry(opt, width=7); e_legend_scale.insert(0, saved_kesit.get("legend_scale", "1.0")); e_legend_scale.grid(row=9, column=1, sticky="w", padx=5, pady=4)
        e_legend_cols = ttk.Entry(opt, width=5); e_legend_cols.insert(0, saved_kesit.get("legend_columns", "0")); e_legend_cols.grid(row=9, column=1, sticky="w", padx=(70, 5), pady=4)
        ttk.Label(opt, text="Tarama sıklığı").grid(row=10, column=0, sticky="e", padx=5, pady=4)
        pattern_frame = ttk.Frame(opt)
        pattern_frame.grid(row=10, column=1, sticky="w", padx=5, pady=4)
        def add_pattern_entry(row, col, label, key, default=""):
            ttk.Label(pattern_frame, text=label).grid(row=row, column=col * 2, sticky="e", padx=(0 if col == 0 else 8, 2), pady=1)
            entry = ttk.Entry(pattern_frame, width=5)
            entry.insert(0, saved_kesit.get(key, default))
            entry.grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 4), pady=1)
            return entry

        e_pattern_density = add_pattern_entry(0, 0, "Genel", "section_pattern_density", "10.0")
        e_clay_pattern = add_pattern_entry(0, 1, "Kil", "clay_pattern_density", "")
        e_silt_pattern = add_pattern_entry(0, 2, "Silt", "silt_pattern_density", "")
        e_sand_pattern = add_pattern_entry(1, 0, "Kum", "sand_pattern_density", "")
        e_gravel_pattern = add_pattern_entry(1, 1, "Çakıl", "gravel_pattern_density", "")
        e_legend_pattern = add_pattern_entry(1, 2, "Lej.", "legend_pattern_density", "6.0")
        ttk.Label(opt, text="Export DPI").grid(row=11, column=0, sticky="e", padx=5, pady=4)
        e_export_dpi = ttk.Entry(opt, width=12); e_export_dpi.insert(0, saved_kesit.get("export_dpi", "300")); e_export_dpi.grid(row=11, column=1, sticky="w", padx=5, pady=4)
        title_mode_var = tk.StringVar(value=saved_kesit.get("title_mode", "full"))
        ttk.Label(opt, text="Başlık").grid(row=12, column=0, sticky="e", padx=5, pady=4)
        ttk.Combobox(opt, textvariable=title_mode_var, values=["full", "simple", "none"], width=10, state="readonly").grid(row=12, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(opt, text="Mercek max. kalınlık (m)").grid(row=13, column=0, sticky="e", padx=5, pady=4)
        e_lens_max = ttk.Entry(opt, width=12); e_lens_max.insert(0, saved_kesit.get("lens_max_thickness", "2.0")); e_lens_max.grid(row=13, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(opt, text="Mercek kapanma oranı").grid(row=14, column=0, sticky="e", padx=5, pady=4)
        e_lens_ratio = ttk.Entry(opt, width=12); e_lens_ratio.insert(0, saved_kesit.get("lens_closure_ratio", "0.58")); e_lens_ratio.grid(row=14, column=1, sticky="w", padx=5, pady=4)
        show_station_var = tk.BooleanVar(value=saved_kesit.get("show_station_offset_labels", True))
        show_elevation_var = tk.BooleanVar(value=saved_kesit.get("show_well_elevation_labels", True))
        show_depth_var = tk.BooleanVar(value=saved_kesit.get("show_layer_depth_labels", True))
        show_distance_var = tk.BooleanVar(value=saved_kesit.get("show_distance_labels", True))
        show_legend_var = tk.BooleanVar(value=saved_kesit.get("show_legend", True))
        show_yass_var = tk.BooleanVar(value=saved_kesit.get("show_yass", True))
        show_yass_labels_var = tk.BooleanVar(value=saved_kesit.get("show_yass_labels", True))
        show_detailed_lithology_var = tk.BooleanVar(
            value=saved_kesit.get("show_detailed_lithology_labels", section_engine_value == "v2")
        )
        cmb_section_engine.bind(
            "<<ComboboxSelected>>",
            lambda event=None: show_detailed_lithology_var.set(section_engine_var.get().startswith("V2")),
        )
        avoid_label_var = tk.BooleanVar(value=saved_kesit.get("avoid_label_collisions", True))
        hide_seams_var = tk.BooleanVar(value=saved_kesit.get("hide_same_unit_seams", True))
        auto_lens_var = tk.BooleanVar(value=saved_kesit.get("auto_lens", True))
        two_well_lens_var = tk.BooleanVar(value=saved_kesit.get("two_well_lens", True))
        ttk.Checkbutton(opt, text="Yazı çakışmasını azalt", variable=avoid_label_var).grid(row=4, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Sta/Off", variable=show_station_var).grid(row=6, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Kot", variable=show_elevation_var).grid(row=7, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Tabaka derinliği", variable=show_depth_var).grid(row=8, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Mesafe", variable=show_distance_var).grid(row=9, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Lejant", variable=show_legend_var).grid(row=10, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Aynı birim çizgisini gizle", variable=hide_seams_var).grid(row=11, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="YASS", variable=show_yass_var).grid(row=12, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="YASS etiketi", variable=show_yass_labels_var).grid(row=13, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="Mercekleri otomatik çiz", variable=auto_lens_var).grid(row=14, column=2, sticky="w", padx=5)
        ttk.Checkbutton(opt, text="İki sondajda yarım mercek", variable=two_well_lens_var).grid(row=15, column=2, sticky="w", padx=5)
        ttk.Checkbutton(
            opt,
            text="Birim adlarını göster",
            variable=show_detailed_lithology_var,
        ).grid(row=16, column=2, sticky="w", padx=5)

        kesit_presets = {
            "Strater": {"mode": "line_projection", "vertical_exaggeration": "1.0", "corr_tolerance": "3.0", "dx_default": "25.0", "max_offset": "10.0", "show_consistency_labels": True, "consistency_label_min_height": "0.9", "show_yass": True, "show_yass_labels": True, "auto_lens": True, "two_well_lens": True, "lens_max_thickness": "2.0", "lens_closure_ratio": "0.58"},
            "Strater - Sık Etiket": {"mode": "line_projection", "vertical_exaggeration": "1.0", "corr_tolerance": "4.0", "dx_default": "25.0", "max_offset": "15.0", "show_consistency_labels": True, "consistency_label_min_height": "0.45", "show_yass": True, "show_yass_labels": True, "auto_lens": True, "two_well_lens": True, "lens_max_thickness": "2.0", "lens_closure_ratio": "0.58"},
            "Sade Kesit": {"mode": "line_projection", "vertical_exaggeration": "1.0", "corr_tolerance": "3.0", "dx_default": "25.0", "max_offset": "10.0", "show_consistency_labels": False, "consistency_label_min_height": "0.9", "show_yass": True, "show_yass_labels": False, "auto_lens": True, "two_well_lens": True, "lens_max_thickness": "2.0", "lens_closure_ratio": "0.58"},
            "Gerçek Mesafe": {"mode": "true_distance", "vertical_exaggeration": "1.0", "corr_tolerance": "3.0", "dx_default": "25.0", "max_offset": "10.0", "show_consistency_labels": True, "consistency_label_min_height": "0.9", "show_yass": True, "show_yass_labels": True, "auto_lens": True, "two_well_lens": True, "lens_max_thickness": "2.0", "lens_closure_ratio": "0.58"},
            "Şematik": {"mode": "schematic", "vertical_exaggeration": "1.0", "corr_tolerance": "3.0", "dx_default": "30.0", "max_offset": "10.0", "show_consistency_labels": True, "consistency_label_min_height": "0.9", "show_yass": True, "show_yass_labels": True, "auto_lens": True, "two_well_lens": True, "lens_max_thickness": "2.0", "lens_closure_ratio": "0.58"},
        }
        preset_var = tk.StringVar(value=saved_kesit.get("preset", "Strater"))
        ttk.Label(opt, text="Ayar sablonu").grid(row=15, column=0, sticky="e", padx=5, pady=4)
        cmb_preset = ttk.Combobox(opt, textvariable=preset_var, values=list(kesit_presets.keys()), width=22, state="readonly")
        cmb_preset.grid(row=15, column=1, sticky="w", padx=5, pady=4)

        def set_entry(entry, value):
            entry.delete(0, tk.END)
            entry.insert(0, str(value))

        def apply_kesit_preset(event=None):
            preset = kesit_presets.get(preset_var.get())
            if not preset:
                return
            mode_var.set(preset["mode"])
            set_entry(e_ve, preset["vertical_exaggeration"])
            set_entry(e_tol, preset["corr_tolerance"])
            set_entry(e_dx, preset["dx_default"])
            set_entry(e_offset, preset["max_offset"])
            set_entry(e_label_min, preset["consistency_label_min_height"])
            set_entry(e_well_width, preset.get("well_width", "2.0"))
            set_entry(e_legend_scale, preset.get("legend_scale", "1.0"))
            set_entry(e_legend_cols, preset.get("legend_columns", "0"))
            set_entry(e_pattern_density, preset.get("section_pattern_density", "10.0"))
            set_entry(e_clay_pattern, preset.get("clay_pattern_density", ""))
            set_entry(e_silt_pattern, preset.get("silt_pattern_density", ""))
            set_entry(e_sand_pattern, preset.get("sand_pattern_density", ""))
            set_entry(e_gravel_pattern, preset.get("gravel_pattern_density", ""))
            set_entry(e_legend_pattern, preset.get("legend_pattern_density", "6.0"))
            set_entry(e_lens_max, preset.get("lens_max_thickness", "2.0"))
            set_entry(e_lens_ratio, preset.get("lens_closure_ratio", "0.58"))
            title_mode_var.set(preset.get("title_mode", "full"))
            show_consistency_var.set(bool(preset["show_consistency_labels"]))
            show_yass_var.set(bool(preset.get("show_yass", True)))
            show_yass_labels_var.set(bool(preset.get("show_yass_labels", True)))
            avoid_label_var.set(bool(preset.get("avoid_label_collisions", True)))
            auto_lens_var.set(bool(preset.get("auto_lens", True)))
            two_well_lens_var.set(bool(preset.get("two_well_lens", True)))

        tk.Button(opt, text="Uygula", command=apply_kesit_preset, bg="#D6EAF8").grid(row=15, column=2, sticky="w", padx=5, pady=4)
        cmb_preset.bind("<<ComboboxSelected>>", apply_kesit_preset)

        line_opt = ttk.LabelFrame(tab_hat, text="Kesit Hattı", padding=10)
        line_opt.pack(fill="x", padx=4, pady=4)
        ttk.Label(line_opt, text="Başlangıç sondajı").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        cmb_start = ttk.Combobox(line_opt, values=sondaj_labels, width=20, state="readonly")
        cmb_start.grid(row=0, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(line_opt, text="Bitiş sondajı").grid(row=1, column=0, sticky="e", padx=5, pady=4)
        cmb_end = ttk.Combobox(line_opt, values=sondaj_labels, width=20, state="readonly")
        cmb_end.grid(row=1, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(line_opt, text="Hat dışı tolerans (m)").grid(row=2, column=0, sticky="e", padx=5, pady=4)
        e_offset = ttk.Entry(line_opt, width=12); e_offset.insert(0, saved_kesit.get("max_offset", "10.0")); e_offset.grid(row=2, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(line_opt, text="Not: Station değeri bu hatta dik izdüşümle hesaplanır.").grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(4, 0))
        if sondaj_labels:
            start_no = saved_kesit.get("line_start_no")
            end_no = saved_kesit.get("line_end_no")
            cmb_start.current(sondaj_labels.index(start_no) if start_no in sondaj_labels else 0)
            cmb_end.current(sondaj_labels.index(end_no) if end_no in sondaj_labels else (len(sondaj_labels) - 1 if len(sondaj_labels) > 1 else 0))

        map_line_state = {"start": None, "end": None, "ordered_indices": []}

        def has_map_line():
            return bool(map_line_state.get("start") and map_line_state.get("end"))

        def line_endpoint_indices():
            if mode_var.get() != "line_projection":
                return []
            start_idx = cmb_start.current()
            end_idx = cmb_end.current()
            indices = []
            for idx in (start_idx, end_idx):
                if idx >= 0 and idx not in indices:
                    indices.append(idx)
            return indices

        def selected_with_line_endpoints(selected):
            selected = list(selected or [])
            if mode_var.get() == "line_projection" and has_map_line():
                selected_set = set(selected)
                ordered = [idx for idx in map_line_state.get("ordered_indices", []) if idx in selected_set]
                extras = [idx for idx in selected if idx not in ordered]
                return ordered + extras
            if mode_var.get() == "line_projection" and len(selected) < 2:
                for idx in line_endpoint_indices():
                    if idx not in selected:
                        selected.append(idx)
                        try:
                            lb.selection_set(idx)
                        except Exception:
                            pass
            return sorted(selected)

        def line_endpoints_to_selection():
            added = 0
            for idx in line_endpoint_indices():
                if idx not in lb.curselection():
                    added += 1
                try:
                    lb.selection_set(idx)
                except Exception:
                    pass
            if added:
                self.set_status("Kesit hattı başlangıç/bitiş sondajları seçime eklendi.", level="info")

        ttk.Button(line_opt, text="Uçları Seçime Ekle", command=line_endpoints_to_selection).grid(row=4, column=0, columnspan=2, sticky="ew", padx=5, pady=(8, 0))

        def open_map_line_selector():
            try:
                import tkintermapview
            except Exception as exc:
                messagebox.showerror("Kesit Haritası", f"Harita modülü açılamadı:\n{exc}")
                return

            valid_wells = []
            for idx, sondaj in enumerate(self.veri.get("sondaj", [])):
                y, x = safe_float(sondaj.get("y")), safe_float(sondaj.get("x"))
                if y and x:
                    valid_wells.append((idx, sondaj, y, x))
            if len(valid_wells) < 2:
                messagebox.showwarning("Kesit Haritası", "Haritadan kesit hattı çizmek için koordinatlı en az iki sondaj olmalı.")
                return

            mode_var.set("line_projection")
            dialog = Toplevel(win)
            dialog.title("Haritadan Kesit Hattı Çiz")
            dialog.geometry("1180x760")
            dialog.transient(win)

            top_info = tk.Frame(dialog, bg="#2C3E50")
            top_info.pack(fill="x")
            status_var = tk.StringVar(value="Haritada iki nokta tıklayın. Program hatta yakın sondajları baştan sona seçecek.")
            tk.Label(top_info, textvariable=status_var, bg="#2C3E50", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=10, pady=8)
            ttk.Label(top_info, text="Tolerans (m)", background="#2C3E50", foreground="white").pack(side="right", padx=(6, 4))
            tol_var = tk.StringVar(value=e_offset.get() or "10.0")
            ttk.Entry(top_info, textvariable=tol_var, width=8).pack(side="right", padx=(4, 10), pady=6)

            body = ttk.Frame(dialog)
            body.pack(fill="both", expand=True)
            map_frame = ttk.Frame(body)
            map_frame.pack(side="left", fill="both", expand=True)
            side = ttk.Frame(body, padding=8)
            side.pack(side="right", fill="y")

            map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=0)
            map_widget.pack(fill="both", expand=True)
            map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}", max_zoom=22)

            selected_list = Listbox(side, width=34, height=18)
            selected_list.pack(fill="both", expand=True)
            ttk.Label(side, text="Seçilecek sondajlar station sırasıyla görünür.").pack(fill="x", pady=(6, 4))

            all_points = []
            kml_points = kml_koordinatlari_oku(getattr(self, "kml_path", None), max_points=600)
            if len(kml_points) >= 3:
                kml_path = [(float(p["lat"]), float(p["lon"])) for p in kml_points]
                try:
                    map_widget.set_polygon(kml_path, outline_color="#F1C40F", fill_color=None, border_width=4, name="KML Sınırı")
                    all_points.extend(kml_path)
                except Exception:
                    pass

            for idx, sondaj, y, x in valid_wells:
                no = sondaj.get("no") or f"SK-{idx + 1}"
                map_widget.set_marker(
                    y, x, text=no,
                    marker_color_circle="#E74C3C",
                    marker_color_outside="#FFFFFF",
                    text_color="#FFFFFF",
                    font=("Arial", 11, "bold"),
                )
                all_points.append((y, x))

            if all_points:
                center_y = sum(p[0] for p in all_points) / len(all_points)
                center_x = sum(p[1] for p in all_points) / len(all_points)
                map_widget.set_position(center_y, center_x)
                span = max(max(p[0] for p in all_points) - min(p[0] for p in all_points), max(p[1] for p in all_points) - min(p[1] for p in all_points))
                map_widget.set_zoom(18 if span < 0.003 else 17 if span < 0.01 else 15 if span < 0.03 else 13)

            line_points = []
            drawn_objects = []

            def clear_line():
                for obj in list(drawn_objects):
                    try:
                        obj.delete()
                    except Exception:
                        pass
                drawn_objects.clear()
                line_points.clear()
                map_line_state.update({"start": None, "end": None, "ordered_indices": []})
                selected_list.delete(0, tk.END)
                status_var.set("Haritada iki nokta tıklayın.")

            def draw_and_select():
                if len(line_points) != 2:
                    return
                try:
                    ordered = kesit_hatti_sondaj_sirasi(self.veri.get("sondaj", []), line_points[0], line_points[1], tol_var.get())
                except Exception as exc:
                    messagebox.showwarning("Kesit Haritası", str(exc), parent=dialog)
                    return
                selected_list.delete(0, tk.END)
                lb.selection_clear(0, tk.END)
                for item in ordered:
                    selected_list.insert(tk.END, f"{item['no']} | Sta {item['station']:.1f} m | Off {item['offset']:+.1f} m")
                    lb.selection_set(item["index"])
                map_line_state["start"] = line_points[0]
                map_line_state["end"] = line_points[1]
                map_line_state["ordered_indices"] = [item["index"] for item in ordered]
                e_offset.delete(0, tk.END)
                e_offset.insert(0, str(tol_var.get()))
                status_var.set(f"{len(ordered)} sondaj seçildi. Az/çok geldiyse toleransı değiştirip 'Yakınları Seç' deyin.")

            def on_map_click(coords):
                if len(line_points) >= 2:
                    clear_line()
                line_points.append((float(coords[0]), float(coords[1])))
                label = "Hat Baş" if len(line_points) == 1 else "Hat Son"
                drawn_objects.append(map_widget.set_marker(line_points[-1][0], line_points[-1][1], text=label, marker_color_circle="#F1C40F", marker_color_outside="#111111"))
                if len(line_points) == 2:
                    drawn_objects.append(map_widget.set_path(line_points, color="#FFFFFF", width=7))
                    drawn_objects.append(map_widget.set_path(line_points, color="#8E44AD", width=4))
                    draw_and_select()
                else:
                    status_var.set("Başlangıç seçildi. Bitiş noktasını tıklayın.")

            def accept():
                if not has_map_line() or len(map_line_state.get("ordered_indices", [])) < 2:
                    messagebox.showwarning("Kesit Haritası", "Kesite eklenecek en az iki sondaj bulunmalı.", parent=dialog)
                    return
                dialog.destroy()
                section_nb.select(tab_sondajlar)
                self.set_status(f"Haritadan kesit hattı seçildi: {len(map_line_state['ordered_indices'])} sondaj.", level="success")

            map_widget.add_left_click_map_command(on_map_click)
            ttk.Button(side, text="Yakınları Seç", command=draw_and_select).pack(fill="x", pady=(8, 4))
            ttk.Button(side, text="Hattı Temizle", command=clear_line).pack(fill="x", pady=4)
            ttk.Button(side, text="Kullan", command=accept).pack(fill="x", pady=(12, 4))
            ttk.Button(side, text="Kapat", command=dialog.destroy).pack(fill="x", pady=4)

        ttk.Button(line_opt, text="Haritadan Hat Çiz", command=open_map_line_selector).grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=(6, 0))

        def collect_options(selected, require_line=False):
            options = {
                "mode": mode_var.get(),
                "section_engine": "v2" if section_engine_var.get().startswith("V2") else "v1",
                "preset": preset_var.get(),
                "vertical_exaggeration": e_ve.get(),
                "print_scale_enabled": print_scale_var.get(),
                "print_page_size": print_page_var.get(),
                "horizontal_scale": horizontal_scale_var.get(),
                "vertical_scale": vertical_scale_var.get(),
                "print_auto_fit": True,
                "corr_tolerance": e_tol.get(),
                "dx_default": e_dx.get(),
                "consistency_label_min_height": e_label_min.get(),
                "show_consistency_labels": show_consistency_var.get(),
                "well_width": e_well_width.get(),
                "legend_scale": e_legend_scale.get(),
                "legend_columns": e_legend_cols.get(),
                "section_pattern_density": e_pattern_density.get(),
                "clay_pattern_density": e_clay_pattern.get(),
                "silt_pattern_density": e_silt_pattern.get(),
                "sand_pattern_density": e_sand_pattern.get(),
                "gravel_pattern_density": e_gravel_pattern.get(),
                "legend_pattern_density": e_legend_pattern.get(),
                "auto_lens": auto_lens_var.get(),
                "two_well_lens": two_well_lens_var.get(),
                "lens_max_thickness": e_lens_max.get(),
                "lens_closure_ratio": e_lens_ratio.get(),
                "export_dpi": e_export_dpi.get(),
                "title_mode": title_mode_var.get(),
                "show_station_offset_labels": show_station_var.get(),
                "show_well_elevation_labels": show_elevation_var.get(),
                "show_layer_depth_labels": show_depth_var.get(),
                "show_distance_labels": show_distance_var.get(),
                "show_legend": show_legend_var.get(),
                "show_yass": show_yass_var.get(),
                "show_yass_labels": show_yass_labels_var.get(),
                "show_detailed_lithology_labels": show_detailed_lithology_var.get(),
                "avoid_label_collisions": avoid_label_var.get(),
                "hide_same_unit_seams": hide_seams_var.get(),
                "selected_sondajlar": [self.veri["sondaj"][i].get("no", "") for i in selected],
            }
            if mode_var.get() == "line_projection":
                start_idx = cmb_start.current()
                end_idx = cmb_end.current()
                if start_idx < 0 or end_idx < 0 or start_idx == end_idx:
                    if require_line and not has_map_line():
                        messagebox.showwarning("Kesit", "Kesit hattı için farklı iki başlangıç/bitiş sondajı seçin.")
                        return None
                else:
                    try:
                        start_s = self.veri["sondaj"][start_idx]
                        end_s = self.veri["sondaj"][end_idx]
                    except Exception:
                        if require_line and not has_map_line():
                            messagebox.showwarning("Kesit", "Kesit hattı sondajları okunamadı.")
                            return None
                    else:
                        if require_line and not has_map_line():
                            start_y, start_x = safe_float(start_s.get("y")), safe_float(start_s.get("x"))
                            end_y, end_x = safe_float(end_s.get("y")), safe_float(end_s.get("x"))
                            if not start_y or not start_x or not end_y or not end_x:
                                messagebox.showwarning("Kesit", "Kesit hattı için başlangıç ve bitiş sondaj koordinatları dolu olmalı.")
                                return None
                            if abs(start_y - end_y) < 1e-9 and abs(start_x - end_x) < 1e-9:
                                messagebox.showwarning("Kesit", "Kesit hattı başlangıç ve bitiş koordinatları aynı olamaz.")
                                return None
                        options.update({
                            "line_start_no": start_s.get("no", "Baslangic"),
                            "line_start_y": start_s.get("y", ""),
                            "line_start_x": start_s.get("x", ""),
                            "line_end_no": end_s.get("no", "Bitis"),
                            "line_end_y": end_s.get("y", ""),
                            "line_end_x": end_s.get("x", ""),
                            "max_offset": e_offset.get(),
                        })
                if has_map_line():
                    start_y, start_x = map_line_state["start"]
                    end_y, end_x = map_line_state["end"]
                    options.update({
                        "line_start_no": "Harita Baslangic",
                        "line_start_y": f"{start_y:.8f}",
                        "line_start_x": f"{start_x:.8f}",
                        "line_end_no": "Harita Bitis",
                        "line_end_y": f"{end_y:.8f}",
                        "line_end_x": f"{end_x:.8f}",
                        "max_offset": e_offset.get(),
                    })
            options["section_signature"] = self._kesit_section_signature(options)
            current_saved = self.veri.get("kesit_ayarlari", saved_kesit) or {}
            manual_edits = self._kesit_manual_edits_for_options(current_saved, options)
            if manual_edits:
                options["manual_edits"] = manual_edits
            return options

        def kalite_kontrol():
            selected = selected_with_line_endpoints(lb.curselection())
            if len(selected) < 2:
                messagebox.showwarning("Kesit", "Kontrol için en az iki sondaj seçin.")
                return
            selected_sondajlar = [self.veri["sondaj"][i] for i in selected]
            options = collect_options(selected)
            if options is not None:
                self.kesit_kalite_penceresi(win, selected_sondajlar, options)

        def ciz():
            selected = selected_with_line_endpoints(lb.curselection())
            if len(selected) < 2:
                messagebox.showwarning("Kesit", "Kesit için en az iki sondaj seçin.")
                return
            options = collect_options(selected, require_line=True)
            if options is None:
                return
            selected_sondajlar = [self.veri["sondaj"][i] for i in selected]
            quality_report = build_section_quality_report(selected_sondajlar, options)
            if quality_report.get("errors"):
                self.kesit_kalite_penceresi(win, selected_sondajlar, options)
                if not messagebox.askyesno("Kesit Kalite Kontrol", f"{len(quality_report['errors'])} hata bulundu. Yine de kesit çizilsin mi?"):
                    self.set_status("Kesit cizimi kalite kontrol nedeniyle iptal edildi.", level="warning")
                    return
            elif quality_report.get("warnings"):
                self.set_status(f"Kesit kalite kontrol {len(quality_report['warnings'])} uyarı buldu.", level="warning")
            self._kesit_ayarlari_kaydet(options.copy())
            self.kesit_onizle_async(selected_sondajlar, options)
            win.destroy()

        def ayari_kaydet():
            selected = selected_with_line_endpoints(lb.curselection())
            options = collect_options(selected)
            if options is None:
                return
            self._kesit_ayarlari_kaydet(options.copy())
            self.set_status(f"Kesit ayarı kaydedildi: {preset_var.get()}", level="success")

        btns = ttk.Frame(win)
        btns.pack(side="bottom", fill="x", padx=10, pady=(5, 10))
        try:
            btns.pack_configure(before=section_nb)
        except tk.TclError:
            pass
        tk.Button(btns, text="Ayarı Kaydet", command=ayari_kaydet, bg="#D6EAF8", fg="#111", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(btns, text="Kontrol Et", command=kalite_kontrol, bg="#FAD7A0", fg="#111", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(btns, text="Çiz", command=ciz, bg="#5D4037", fg="white", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=(4, 0))
