import math
import os
import re
import tkinter as tk
from tkinter import Frame, Listbox, Toplevel, filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from harita_referans import kml_koordinatlari_oku
from kesit_kalite import build_section_quality_report, format_section_quality_report
from motor import GeoEngine
from performans import perf_tracked
from sabitler import COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD
from yardimcilar import safe_float


def _temiz_dosya_adi(text):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r'[<>:"/\\|?*]+', "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Kesit"


def _sondaj_adi_token(no):
    text = re.sub(r"\s+", "", str(no or "").strip())
    match = re.match(r"^([A-Za-zÇĞİÖŞÜçğıöşü]+)[-_]?0*(\d+)$", text)
    if match:
        return f"{match.group(1).upper()}{int(match.group(2))}", match.group(1).upper(), int(match.group(2))
    return _temiz_dosya_adi(text), None, None


def kesit_kayit_dosya_adi(sondajlar):
    names = []
    for item in sondajlar or []:
        if isinstance(item, dict):
            name = item.get("no") or item.get("ad") or ""
        else:
            name = item
        if str(name or "").strip():
            names.append(name)
    if not names:
        return "Kesit"

    parsed = [_sondaj_adi_token(name) for name in names]
    prefixes = {prefix for _, prefix, number in parsed if prefix is not None and number is not None}
    if len(prefixes) == 1 and all(prefix is not None and number is not None for _, prefix, number in parsed):
        prefix = parsed[0][1]
        numbers = [number for _, _, number in parsed]
        unique_numbers = sorted(set(numbers))
        if len(unique_numbers) == len(numbers) and unique_numbers == list(range(unique_numbers[0], unique_numbers[-1] + 1)):
            return _temiz_dosya_adi(f"Kesit {prefix}{unique_numbers[0]}-{unique_numbers[-1]}")
        return _temiz_dosya_adi("Kesit " + "-".join(f"{prefix}{number}" for number in numbers))

    return _temiz_dosya_adi("Kesit " + "-".join(token for token, _, _ in parsed))


def kesit_hatti_sondaj_sirasi(sondajlar, start, end, max_offset=10.0):
    start_y, start_x = safe_float(start[0]), safe_float(start[1])
    end_y, end_x = safe_float(end[0]), safe_float(end[1])
    if not start_y or not start_x or not end_y or not end_x:
        raise ValueError("Kesit hattı başlangıç/bitiş koordinatları geçersiz.")

    lat0_rad = math.radians(start_y)
    meters_per_lat = 111320.0
    meters_per_lon = 111320.0 * math.cos(lat0_rad)

    def to_local(y, x):
        return (x - start_x) * meters_per_lon, (y - start_y) * meters_per_lat

    end_lx, end_ly = to_local(end_y, end_x)
    line_len = math.hypot(end_lx, end_ly)
    if line_len <= 0.01:
        raise ValueError("Kesit hattı başlangıç ve bitiş noktaları aynı olamaz.")
    ux, uy = end_lx / line_len, end_ly / line_len
    tolerance = safe_float(max_offset)

    results = []
    for idx, sondaj in enumerate(sondajlar or []):
        y, x = safe_float(sondaj.get("y")), safe_float(sondaj.get("x"))
        if not y or not x:
            continue
        px, py = to_local(y, x)
        station = px * ux + py * uy
        offset = px * (-uy) + py * ux
        if tolerance > 0:
            if abs(offset) > tolerance:
                continue
            if station < -tolerance or station > line_len + tolerance:
                continue
        results.append({
            "index": idx,
            "no": sondaj.get("no", f"SK-{idx + 1}"),
            "station": station,
            "offset": offset,
        })
    return sorted(results, key=lambda item: (item["station"], item["no"]))


class KesitCizimMixin:
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
            selected_key,
            norm_float(options.get("vertical_exaggeration", 1.0)),
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
        ttk.Radiobutton(opt, text="Kesit hattı (Strater tarzı station/offset)", variable=mode_var, value="line_projection").grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Radiobutton(opt, text="Gerçek mesafe (seçilen sıraya göre)", variable=mode_var, value="true_distance").grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Radiobutton(opt, text="Şematik (eşit aralık)", variable=mode_var, value="schematic").grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(opt, text="Düşey abartı").grid(row=3, column=0, sticky="e", padx=5, pady=4)
        e_ve = ttk.Entry(opt, width=12); e_ve.insert(0, saved_kesit.get("vertical_exaggeration", "1.0")); e_ve.grid(row=3, column=1, sticky="w", padx=5, pady=4)
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
        ttk.Label(opt, text="Tarama").grid(row=10, column=0, sticky="e", padx=5, pady=4)
        pattern_frame = ttk.Frame(opt)
        pattern_frame.grid(row=10, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(pattern_frame, text="Genel").pack(side="left")
        e_pattern_density = ttk.Entry(pattern_frame, width=5); e_pattern_density.insert(0, saved_kesit.get("section_pattern_density", "6.0")); e_pattern_density.pack(side="left", padx=(2, 5))
        ttk.Label(pattern_frame, text="Kum").pack(side="left")
        e_sand_pattern = ttk.Entry(pattern_frame, width=5); e_sand_pattern.insert(0, saved_kesit.get("sand_pattern_density", "")); e_sand_pattern.pack(side="left", padx=(2, 5))
        ttk.Label(pattern_frame, text="Çakıl").pack(side="left")
        e_gravel_pattern = ttk.Entry(pattern_frame, width=5); e_gravel_pattern.insert(0, saved_kesit.get("gravel_pattern_density", "")); e_gravel_pattern.pack(side="left", padx=(2, 5))
        ttk.Label(pattern_frame, text="Lej.").pack(side="left")
        e_legend_pattern = ttk.Entry(pattern_frame, width=5); e_legend_pattern.insert(0, saved_kesit.get("legend_pattern_density", "6.0")); e_legend_pattern.pack(side="left", padx=(2, 0))
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
            set_entry(e_pattern_density, preset.get("section_pattern_density", "6.0"))
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
                "preset": preset_var.get(),
                "vertical_exaggeration": e_ve.get(),
                "corr_tolerance": e_tol.get(),
                "dx_default": e_dx.get(),
                "consistency_label_min_height": e_label_min.get(),
                "show_consistency_labels": show_consistency_var.get(),
                "well_width": e_well_width.get(),
                "legend_scale": e_legend_scale.get(),
                "legend_columns": e_legend_cols.get(),
                "section_pattern_density": e_pattern_density.get(),
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
            self.kesit_onizle(selected_sondajlar, options)
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

    @perf_tracked("section.preview")
    def kesit_onizle(self, sondajlar, options=None):
        options = dict(options or {})
        if not options.get("selected_sondajlar"):
            options["selected_sondajlar"] = [s.get("no", "") for s in sondajlar or []]
        options["section_signature"] = options.get("section_signature") or self._kesit_section_signature(options)
        saved_kesit = self.veri.get("kesit_ayarlari", {}) or {}
        active_manual_edits = self._kesit_manual_edits_for_options(saved_kesit, options)
        if active_manual_edits:
            options["manual_edits"] = active_manual_edits
        else:
            options.pop("manual_edits", None)
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Kesit Önizleme", "1200x800", (980, 640))
        f = Frame(win)
        f.pack(fill="both", expand=True)
        top_bar = tk.Frame(f, bg="#333", height=40)
        top_bar.pack(fill="x")
        edit_status_var = tk.StringVar(value="Değişen: 0 | Kayıtlı: 0 | Geri: 0 | İleri: 0")

        def on_draw_warning(msg, level="info"):
            self.root.after(0, lambda: self.set_status(msg, level))

        GeoEngine.reset_warnings()
        fig, _ = GeoEngine.kesit_ciz_interaktif(sondajlar, log_callback=on_draw_warning, options=options)
        chart = FigureCanvasTkAgg(fig, master=f)
        chart.get_tk_widget().pack(fill="both", expand=True)
        quality_report = build_section_quality_report(sondajlar, options)
        if quality_report.get("errors"):
            self.set_status(f"Kesit kalite kontrol: {len(quality_report.get('errors', []))} hata var.", level="error")
        elif quality_report.get("warnings"):
            self.set_status(f"Kesit kalite kontrol: {len(quality_report.get('warnings', []))} uyarı var.", level="warning")

        def section_tool():
            return getattr(fig, "_geo_tool", None)

        def section_polygons():
            tool = section_tool()
            return [
                poly for poly in getattr(tool, "polygons", []) or []
                if getattr(poly, "_geo_poly_kind", "section") != "well"
                and getattr(poly, "_geo_edit_id", None)
            ]

        def option_as_bool(name, default=False):
            value = options.get(name, default)
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "evet", "yes", "on")
            return bool(value)

        def normalize_manual_xy(raw):
            if isinstance(raw, dict):
                raw = raw.get("vertices") or raw.get("xy")
            if not isinstance(raw, list) or len(raw) < 3:
                return None
            xy = []
            for point in raw:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    return None
                xy.append([safe_float(point[0]), safe_float(point[1])])
            return xy if len(xy) >= 3 else None

        def manual_edit_hidden(raw):
            return isinstance(raw, dict) and bool(raw.get("hidden"))

        def set_poly_visibility(poly, visible):
            if poly is None:
                return
            visible = bool(visible)
            try:
                poly._geo_hidden = not visible
                poly.set_visible(visible)
                for artist in getattr(poly, "_geo_pattern_artists", []) or []:
                    artist.set_visible(visible)
            except Exception:
                pass

        def get_saved_manual_edits():
            saved_options = self.veri.setdefault("kesit_ayarlari", {})
            return self._kesit_manual_edits_for_options(saved_options, options)

        def set_saved_manual_edits(all_edits):
            saved_options = self.veri.setdefault("kesit_ayarlari", {})
            signature = options.get("section_signature") or self._kesit_section_signature(options)
            options["section_signature"] = signature
            by_section = saved_options.get("manual_edits_by_section")
            by_section = dict(by_section) if isinstance(by_section, dict) else {}
            if all_edits:
                options["manual_edits"] = all_edits
                by_section[signature] = all_edits
            else:
                options.pop("manual_edits", None)
                by_section.pop(signature, None)
            saved_options.update(options)
            saved_options["manual_section_signature"] = signature
            if all_edits:
                saved_options["manual_edits"] = all_edits
            else:
                saved_options.pop("manual_edits", None)
            if by_section:
                saved_options["manual_edits_by_section"] = by_section
            else:
                saved_options.pop("manual_edits_by_section", None)

        def current_section_edit_ids():
            ids = set()
            for poly in section_polygons():
                edit_id = getattr(poly, "_geo_edit_id", None)
                if edit_id:
                    ids.add(edit_id)
            return ids

        def capture_section_edits():
            edits = {}
            for poly in section_polygons():
                edit_id = getattr(poly, "_geo_edit_id", None)
                if not edit_id:
                    continue
                try:
                    current_xy = [[round(float(x), 4), round(float(y), 4)] for x, y in poly.get_xy()]
                    default_xy = [[round(float(x), 4), round(float(y), 4)] for x, y in getattr(poly, "_geo_default_xy", [])]
                    hidden = bool(getattr(poly, "_geo_hidden", False)) or (hasattr(poly, "get_visible") and not poly.get_visible())
                    if current_xy == default_xy and not hidden:
                        continue
                    if hidden:
                        edits[edit_id] = {"vertices": current_xy, "hidden": True}
                    else:
                        edits[edit_id] = current_xy
                except Exception:
                    pass
            return edits

        def update_edit_status(tool=None):
            try:
                tool = tool or section_tool()
                undo_count, redo_count = tool.history_counts() if tool is not None and hasattr(tool, "history_counts") else (0, 0)
                saved_ids = current_section_edit_ids().intersection(get_saved_manual_edits().keys())
                edit_status_var.set(
                    f"Değişen: {len(capture_section_edits())} | Kayıtlı: {len(saved_ids)} | "
                    f"Geri: {undo_count} | İleri: {redo_count}"
                )
            except Exception:
                edit_status_var.set("Düzenleme durumu okunamadı")

        def save_section_edits(show_status=True):
            current_ids = current_section_edit_ids()
            edits = capture_section_edits()
            all_edits = get_saved_manual_edits()
            for edit_id in current_ids:
                all_edits.pop(edit_id, None)
            all_edits.update(edits)
            set_saved_manual_edits(all_edits)
            if self.aktif_dosya_yolu:
                self.veri_kaydet()
            if show_status:
                self.set_status(f"Bu kesit için {len(edits)} manuel polygon kaydedildi.", level="success")
            update_edit_status()
            return edits

        def apply_poly_xy(poly, xy, record=False):
            if poly is None or not xy:
                return False
            tool = section_tool()
            before_xy = tool.poly_xy(poly) if record and tool is not None and hasattr(tool, "poly_xy") else None
            try:
                poly.set_xy(xy)
                if tool is not None and hasattr(tool, "refresh_pattern"):
                    tool.refresh_pattern(poly)
                if record and tool is not None and hasattr(tool, "record_history"):
                    tool.record_history(poly, before_xy)
                return True
            except Exception:
                return False

        def refresh_section_canvas():
            tool = section_tool()
            if tool is not None and hasattr(tool, "refresh_same_unit_seams"):
                tool.refresh_same_unit_seams()
            if tool is not None and hasattr(tool, "draw_markers"):
                tool.draw_markers()
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            update_edit_status(tool)

        def reset_section_edits():
            if not messagebox.askyesno("Kesit", "Kayıtlı manuel kesit düzenlemeleri silinsin mi?"):
                return
            current_ids = current_section_edit_ids()
            all_edits = get_saved_manual_edits()
            removed = 0
            for edit_id in current_ids:
                if edit_id in all_edits:
                    removed += 1
                    all_edits.pop(edit_id, None)
            set_saved_manual_edits(all_edits)
            for poly in section_polygons():
                default_xy = getattr(poly, "_geo_default_xy", None)
                if default_xy and getattr(poly, "_geo_edit_id", None) in current_ids:
                    set_poly_visibility(poly, True)
                    apply_poly_xy(poly, default_xy, record=True)
            if self.aktif_dosya_yolu:
                self.veri_kaydet()
            refresh_section_canvas()
            self.set_status(f"Bu kesite ait {removed} kayıtlı manuel düzenleme sıfırlandı.", level="info")

        def restore_saved_section_edits():
            saved_edits = get_saved_manual_edits()
            changed = 0
            for poly in section_polygons():
                edit_id = getattr(poly, "_geo_edit_id", None)
                raw_edit = saved_edits.get(edit_id) if edit_id in saved_edits else None
                xy = normalize_manual_xy(raw_edit) if raw_edit is not None else None
                set_poly_visibility(poly, not manual_edit_hidden(raw_edit))
                if xy is None:
                    xy = getattr(poly, "_geo_default_xy", None)
                if xy and apply_poly_xy(poly, xy, record=True):
                    changed += 1
            refresh_section_canvas()
            self.set_status(f"Kesit kayıtlı hale döndürüldü: {changed} polygon kontrol edildi.", level="info")

        def select_poly_in_editor(poly):
            tool = section_tool()
            if tool is None or poly is None:
                return
            if hasattr(tool, "select_polygon"):
                tool.select_polygon(poly)
            else:
                tool.edit_mode = True
                tool.selected_poly = poly
                tool.draw_markers()
            self.set_status("Seçili polygon düzenleme moduna alındı.", level="info")

        def remove_saved_edit(edit_id):
            if not edit_id:
                return
            all_edits = get_saved_manual_edits()
            if edit_id in all_edits:
                all_edits.pop(edit_id, None)
                set_saved_manual_edits(all_edits)
                if self.aktif_dosya_yolu:
                    self.veri_kaydet()

        def open_edit_list():
            rows = []
            dialog = Toplevel(win)
            dialog.title("Kesit Düzenleme Listesi")
            dialog.geometry("680x420")
            dialog.transient(win)
            list_frame = ttk.Frame(dialog, padding=10)
            list_frame.pack(fill="both", expand=True)
            ttk.Label(list_frame, text="Polygonlar").pack(anchor="w")
            listbox = Listbox(list_frame, height=14)
            listbox.pack(fill="both", expand=True, pady=(4, 8))

            def reload_rows():
                rows.clear()
                listbox.delete(0, tk.END)
                saved_edits = get_saved_manual_edits()
                active_edits = capture_section_edits()
                for idx, poly in enumerate(section_polygons(), start=1):
                    edit_id = getattr(poly, "_geo_edit_id", "")
                    unit_code = str(getattr(poly, "_geo_unit_code", "?")).upper()
                    if bool(getattr(poly, "_geo_hidden", False)) or (hasattr(poly, "get_visible") and not poly.get_visible()):
                        status = "gizli"
                    elif edit_id in active_edits:
                        status = "değişti"
                    elif edit_id in saved_edits:
                        status = "kayıtlı"
                    else:
                        status = "varsayılan"
                    rows.append(poly)
                    listbox.insert(tk.END, f"{idx:02d} | {unit_code:<10} | {status:<10} | {edit_id}")

            def get_selected_poly():
                selection = listbox.curselection()
                if not selection:
                    return None
                idx = selection[0]
                return rows[idx] if idx < len(rows) else None

            def reset_selected_poly():
                poly = get_selected_poly()
                if poly is None:
                    return
                edit_id = getattr(poly, "_geo_edit_id", None)
                default_xy = getattr(poly, "_geo_default_xy", None)
                if default_xy and apply_poly_xy(poly, default_xy, record=True):
                    remove_saved_edit(edit_id)
                    refresh_section_canvas()
                    reload_rows()
                    self.set_status("Seçili polygon varsayılana alındı.", level="info")

            listbox.bind("<Double-Button-1>", lambda event=None: select_poly_in_editor(get_selected_poly()))
            button_row = ttk.Frame(list_frame)
            button_row.pack(fill="x")
            ttk.Button(button_row, text="Seç", command=lambda: select_poly_in_editor(get_selected_poly())).pack(side="left", padx=(0, 5))
            ttk.Button(button_row, text="Seçileni Sıfırla", command=reset_selected_poly).pack(side="left", padx=5)
            ttk.Button(button_row, text="Yenile", command=reload_rows).pack(side="left", padx=5)
            ttk.Button(button_row, text="Kapat", command=dialog.destroy).pack(side="right")
            reload_rows()

        def is_lens_poly(poly):
            edit_id = str(getattr(poly, "_geo_edit_id", "") or "")
            return edit_id.startswith("lens:") or edit_id.startswith("half-lens:")

        def lens_polygons():
            return [poly for poly in section_polygons() if is_lens_poly(poly)]

        def selected_lens_poly(show_warning=True):
            tool = section_tool()
            poly = getattr(tool, "selected_poly", None) if tool is not None else None
            if poly is not None and is_lens_poly(poly):
                return poly
            if show_warning:
                messagebox.showwarning("Mercek", "Önce kesitte veya Mercek listesinden bir mercek seçin.")
            return None

        def adjust_lens_poly(poly, x_factor=1.0, y_factor=1.0, closure_delta=0.0):
            tool = section_tool()
            if poly is None or tool is None:
                return False
            before_xy = tool.poly_xy(poly) if hasattr(tool, "poly_xy") else None
            if not before_xy:
                return False
            closed = len(before_xy) > 2 and before_xy[0] == before_xy[-1]
            pts = [list(point) for point in (before_xy[:-1] if closed else before_xy)]
            if len(pts) < 3:
                return False
            cx = sum(point[0] for point in pts) / len(pts)
            cy = sum(point[1] for point in pts) / len(pts)
            for point in pts:
                point[0] = cx + (point[0] - cx) * x_factor
                point[1] = cy + (point[1] - cy) * y_factor

            edit_id = str(getattr(poly, "_geo_edit_id", "") or "")
            tip_indices = []
            if edit_id.startswith("lens:") and len(pts) >= 4:
                tip_indices = [0, 3]
            elif edit_id.startswith("half-lens:"):
                parts = edit_id.split(":")
                direction = parts[3] if len(parts) > 3 else ""
                tip_indices = [2] if direction == "right" and len(pts) > 2 else [0]

            if closure_delta:
                factor = max(0.35, 1.0 + closure_delta)
                for tip_idx in tip_indices:
                    if 0 <= tip_idx < len(pts):
                        pts[tip_idx][0] = cx + (pts[tip_idx][0] - cx) * factor

            if closed:
                pts.append(list(pts[0]))
            if apply_poly_xy(poly, pts, record=True):
                refresh_section_canvas()
                return True
            return False

        def set_selected_lens_visible(visible):
            poly = selected_lens_poly()
            if poly is None:
                return
            set_poly_visibility(poly, visible)
            refresh_section_canvas()
            self.set_status("Mercek görünürlüğü güncellendi.", level="info")

        def open_lens_controls():
            rows = []
            dialog = Toplevel(win)
            dialog.title("Mercek Kontrolü")
            dialog.geometry("760x430")
            dialog.transient(win)
            body = ttk.Frame(dialog, padding=10)
            body.pack(fill="both", expand=True)
            ttk.Label(body, text="Mercekler").pack(anchor="w")
            listbox = Listbox(body, height=10)
            listbox.pack(fill="both", expand=True, pady=(4, 8))

            def reload_rows():
                rows.clear()
                listbox.delete(0, tk.END)
                for idx, poly in enumerate(lens_polygons(), start=1):
                    edit_id = str(getattr(poly, "_geo_edit_id", "") or "")
                    unit_code = str(getattr(poly, "_geo_unit_code", "?")).upper()
                    hidden = bool(getattr(poly, "_geo_hidden", False)) or (hasattr(poly, "get_visible") and not poly.get_visible())
                    rows.append(poly)
                    listbox.insert(tk.END, f"{idx:02d} | {unit_code:<8} | {'gizli' if hidden else 'görünür'} | {edit_id}")
                if not rows:
                    listbox.insert(tk.END, "Bu kesitte otomatik mercek bulunamadı.")

            def get_selected_poly():
                selection = listbox.curselection()
                if not selection or selection[0] >= len(rows):
                    return None
                return rows[selection[0]]

            def select_from_list():
                poly = get_selected_poly()
                if poly is None:
                    return
                if bool(getattr(poly, "_geo_hidden", False)) or (hasattr(poly, "get_visible") and not poly.get_visible()):
                    set_poly_visibility(poly, True)
                select_poly_in_editor(poly)
                refresh_section_canvas()
                reload_rows()

            listbox.bind("<Double-Button-1>", lambda event=None: select_from_list())

            actions = ttk.Frame(body)
            actions.pack(fill="x")
            ttk.Button(actions, text="Seç", command=select_from_list).grid(row=0, column=0, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Yatay +", command=lambda: adjust_lens_poly(selected_lens_poly(), x_factor=1.12)).grid(row=0, column=1, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Yatay -", command=lambda: adjust_lens_poly(selected_lens_poly(), x_factor=0.90)).grid(row=0, column=2, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Düşey +", command=lambda: adjust_lens_poly(selected_lens_poly(), y_factor=1.12)).grid(row=0, column=3, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Düşey -", command=lambda: adjust_lens_poly(selected_lens_poly(), y_factor=0.90)).grid(row=0, column=4, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Kapanma +", command=lambda: adjust_lens_poly(selected_lens_poly(), closure_delta=0.14)).grid(row=1, column=1, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Kapanma -", command=lambda: adjust_lens_poly(selected_lens_poly(), closure_delta=-0.14)).grid(row=1, column=2, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Gizle", command=lambda: (set_selected_lens_visible(False), reload_rows())).grid(row=1, column=3, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Göster", command=lambda: (set_selected_lens_visible(True), reload_rows())).grid(row=1, column=4, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Yenile", command=reload_rows).grid(row=1, column=0, padx=3, pady=3, sticky="ew")
            ttk.Button(actions, text="Kapat", command=dialog.destroy).grid(row=1, column=5, padx=3, pady=3, sticky="ew")
            for col in range(6):
                actions.columnconfigure(col, weight=1)
            reload_rows()

        def undo_section_edit():
            tool = section_tool()
            if tool is not None and hasattr(tool, "undo") and tool.undo():
                update_edit_status(tool)
                return
            self.set_status("Geri alınacak kesit düzenlemesi yok.", level="info")

        def redo_section_edit():
            tool = section_tool()
            if tool is not None and hasattr(tool, "redo") and tool.redo():
                update_edit_status(tool)
                return
            self.set_status("İleri alınacak kesit düzenlemesi yok.", level="info")

        def current_ax():
            return fig.axes[0] if fig.axes else None

        def set_live_group_visible(group, visible):
            ax = current_ax()
            if ax is None:
                return
            for artist in ax.get_children():
                live_group = getattr(artist, "_geo_live_group", None)
                export_group = getattr(artist, "_geo_export_group", None)
                if live_group == group or (group == "legend" and export_group == "legend"):
                    try:
                        artist.set_visible(bool(visible))
                    except Exception:
                        pass

        def set_station_labels_visible(show_station):
            ax = current_ax()
            if ax is None:
                return
            for text in ax.texts:
                if not hasattr(text, "_geo_save_text"):
                    continue
                if show_station:
                    text.set_text(getattr(text, "_geo_full_text", text.get_text()))
                    text.set_fontsize(getattr(text, "_geo_full_fontsize", text.get_fontsize()))
                else:
                    text.set_text(text._geo_save_text)
                    text.set_fontsize(getattr(text, "_geo_save_fontsize", text.get_fontsize()))

        def set_title_live(title_mode):
            ax = current_ax()
            if ax is None:
                return
            title_mode = str(title_mode or "full").lower()
            if title_mode == "none":
                ax.set_title("")
            elif title_mode == "simple":
                ax.set_title(getattr(ax, "_geo_title_simple", "Jeolojik Kesit"), fontsize=12, fontweight="bold")
            else:
                ax.set_title(getattr(ax, "_geo_title_full", ax.get_title()), fontsize=12, fontweight="bold")

        def set_same_unit_seams_live(hide_seams):
            ax = current_ax()
            if ax is None:
                return
            fig._geo_hide_same_unit_seams = bool(hide_seams)
            if hide_seams:
                tool = section_tool()
                if tool is not None and hasattr(tool, "refresh_same_unit_seams"):
                    tool.refresh_same_unit_seams()
            else:
                for artist in list(getattr(ax, "_geo_same_unit_seam_masks", [])):
                    try:
                        artist.remove()
                    except Exception:
                        pass
                ax._geo_same_unit_seam_masks = []

        def apply_live_preview_settings(config):
            options.update(config)
            set_station_labels_visible(config.get("show_station_offset_labels", True))
            set_live_group_visible("well_elevation", config.get("show_well_elevation_labels", True))
            set_live_group_visible("layer_depth", config.get("show_layer_depth_labels", True))
            set_live_group_visible("distance", config.get("show_distance_labels", True))
            set_live_group_visible("legend", config.get("show_legend", True))
            set_live_group_visible("consistency", config.get("show_consistency_labels", True))
            yass_visible = config.get("show_yass", True)
            set_live_group_visible("yass", yass_visible)
            set_live_group_visible("yass_label", yass_visible and config.get("show_yass_labels", True))
            set_same_unit_seams_live(config.get("hide_same_unit_seams", True))
            set_title_live(config.get("title_mode", "full"))
            self._kesit_ayarlari_kaydet(options.copy())
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            self.set_status("Kesit önizleme ayarları uygulandı.", level="success")

        def open_preview_settings():
            dialog = Toplevel(win)
            dialog.title("Kesit Önizleme Ayarları")
            dialog.transient(win)
            dialog.grab_set()
            body = ttk.Frame(dialog, padding=12)
            body.pack(fill="both", expand=True)

            live_frame = ttk.LabelFrame(body, text="Canlı Görünüm", padding=10)
            live_frame.pack(fill="x")
            redraw_frame = ttk.LabelFrame(body, text="Yeniden Çizim Gerektiren Ayarlar", padding=10)
            redraw_frame.pack(fill="x", pady=(10, 0))

            station_var = tk.BooleanVar(value=option_as_bool("show_station_offset_labels", True))
            elevation_var = tk.BooleanVar(value=option_as_bool("show_well_elevation_labels", True))
            depth_var = tk.BooleanVar(value=option_as_bool("show_layer_depth_labels", True))
            distance_var = tk.BooleanVar(value=option_as_bool("show_distance_labels", True))
            legend_var = tk.BooleanVar(value=option_as_bool("show_legend", True))
            yass_var = tk.BooleanVar(value=option_as_bool("show_yass", True))
            yass_label_var = tk.BooleanVar(value=option_as_bool("show_yass_labels", True))
            consistency_var = tk.BooleanVar(value=option_as_bool("show_consistency_labels", True))
            seams_var = tk.BooleanVar(value=option_as_bool("hide_same_unit_seams", True))
            title_var = tk.StringVar(value=str(options.get("title_mode", "full")))

            live_checks = [
                ("Sta/Off", station_var),
                ("Kot", elevation_var),
                ("Tabaka derinliği", depth_var),
                ("Mesafe", distance_var),
                ("Lejant", legend_var),
                ("YASS", yass_var),
                ("YASS etiketi", yass_label_var),
                ("Sıkılık/kıvam", consistency_var),
                ("Aynı birim çizgisini gizle", seams_var),
            ]
            for idx, (label, var) in enumerate(live_checks):
                ttk.Checkbutton(live_frame, text=label, variable=var).grid(row=idx // 3, column=idx % 3, sticky="w", padx=6, pady=3)
            ttk.Label(live_frame, text="Başlık").grid(row=3, column=0, sticky="w", padx=6, pady=(8, 3))
            ttk.Combobox(live_frame, textvariable=title_var, values=("full", "simple", "none"), width=10, state="readonly").grid(row=3, column=1, sticky="w", padx=6, pady=(8, 3))

            entries = {}
            redraw_fields = [
                ("Düşey abartı", "vertical_exaggeration", "1.0"),
                ("Eşleşme toleransı", "corr_tolerance", "3.0"),
                ("Şematik aralık", "dx_default", "25.0"),
                ("Kuyu genişliği", "well_width", "2.0"),
                ("Mercek max. kalınlık", "lens_max_thickness", "2.0"),
                ("Mercek kapanma", "lens_closure_ratio", "0.58"),
                ("Genel tarama", "section_pattern_density", "6.0"),
                ("Kum tarama", "sand_pattern_density", ""),
                ("Çakıl tarama", "gravel_pattern_density", ""),
                ("Lejant tarama", "legend_pattern_density", "6.0"),
            ]
            for idx, (label, key, default) in enumerate(redraw_fields):
                ttk.Label(redraw_frame, text=label).grid(row=idx, column=0, sticky="e", padx=5, pady=3)
                entry = ttk.Entry(redraw_frame, width=12)
                entry.insert(0, str(options.get(key, default)))
                entry.grid(row=idx, column=1, sticky="w", padx=5, pady=3)
                entries[key] = entry

            auto_lens_var = tk.BooleanVar(value=option_as_bool("auto_lens", True))
            two_well_lens_var = tk.BooleanVar(value=option_as_bool("two_well_lens", True))
            avoid_label_var = tk.BooleanVar(value=option_as_bool("avoid_label_collisions", True))
            ttk.Checkbutton(redraw_frame, text="Mercekleri otomatik çiz", variable=auto_lens_var).grid(row=0, column=2, sticky="w", padx=12, pady=3)
            ttk.Checkbutton(redraw_frame, text="İki sondajda yarım mercek", variable=two_well_lens_var).grid(row=1, column=2, sticky="w", padx=12, pady=3)
            ttk.Checkbutton(redraw_frame, text="Yazı çakışmasını azalt", variable=avoid_label_var).grid(row=2, column=2, sticky="w", padx=12, pady=3)

            def live_config():
                return {
                    "show_station_offset_labels": station_var.get(),
                    "show_well_elevation_labels": elevation_var.get(),
                    "show_layer_depth_labels": depth_var.get(),
                    "show_distance_labels": distance_var.get(),
                    "show_legend": legend_var.get(),
                    "show_yass": yass_var.get(),
                    "show_yass_labels": yass_label_var.get(),
                    "show_consistency_labels": consistency_var.get(),
                    "hide_same_unit_seams": seams_var.get(),
                    "title_mode": title_var.get(),
                }

            def apply_live():
                apply_live_preview_settings(live_config())

            def redraw():
                new_options = dict(options)
                new_options.update(live_config())
                for key, entry in entries.items():
                    new_options[key] = entry.get()
                new_options["auto_lens"] = auto_lens_var.get()
                new_options["two_well_lens"] = two_well_lens_var.get()
                new_options["avoid_label_collisions"] = avoid_label_var.get()
                new_options["section_signature"] = self._kesit_section_signature(new_options)
                save_section_edits(show_status=False)
                self._kesit_ayarlari_kaydet(new_options.copy())
                dialog.destroy()
                win.destroy()
                self.kesit_onizle(sondajlar, new_options)

            buttons = ttk.Frame(body)
            buttons.pack(fill="x", pady=(10, 0))
            ttk.Button(buttons, text="Canlı Uygula", command=apply_live).pack(side="left")
            ttk.Button(buttons, text="Uygula ve Yeniden Çiz", command=redraw).pack(side="left", padx=8)
            ttk.Button(buttons, text="Kapat", command=dialog.destroy).pack(side="right")

        def export_settings_dialog():
            dialog = Toplevel(win)
            dialog.title("Kesit Kaydetme Ayarları")
            dialog.transient(win)
            dialog.grab_set()
            body = ttk.Frame(dialog, padding=12)
            body.pack(fill="both", expand=True)

            fmt_var = tk.StringVar(value=str(options.get("export_format", "JPG")).upper())
            if fmt_var.get() not in ("JPG", "PNG", "PDF", "SVG"):
                fmt_var.set("JPG")
            dpi_var = tk.StringVar(value=str(int(safe_float(options.get("export_dpi", 300)) or 300)))
            title_var = tk.StringVar(value=str(options.get("export_title_mode", "simple")))
            if title_var.get() not in ("simple", "full", "none"):
                title_var.set("simple")
            legend_var = tk.BooleanVar(value=option_as_bool("export_show_legend", True))
            result = {"config": None}

            ttk.Label(body, text="Format").grid(row=0, column=0, sticky="w", pady=4)
            ttk.Combobox(body, textvariable=fmt_var, values=("JPG", "PNG", "PDF", "SVG"), width=12, state="readonly").grid(row=0, column=1, sticky="ew", pady=4)
            ttk.Label(body, text="DPI").grid(row=1, column=0, sticky="w", pady=4)
            ttk.Entry(body, textvariable=dpi_var, width=14).grid(row=1, column=1, sticky="ew", pady=4)
            ttk.Label(body, text="Başlık").grid(row=2, column=0, sticky="w", pady=4)
            ttk.Combobox(body, textvariable=title_var, values=("simple", "full", "none"), width=12, state="readonly").grid(row=2, column=1, sticky="ew", pady=4)
            ttk.Label(body, text="Sta/Off kayitta gizlenir.").grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
            ttk.Checkbutton(body, text="Lejantı göster", variable=legend_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
            body.columnconfigure(1, weight=1)

            def accept():
                try:
                    dpi = int(float(dpi_var.get().replace(",", ".")))
                except Exception:
                    dpi = 300
                dpi = max(72, min(600, dpi))
                result["config"] = {
                    "format": fmt_var.get(),
                    "dpi": dpi,
                    "title_mode": title_var.get(),
                    "show_station": False,
                    "show_legend": bool(legend_var.get()),
                }
                options["export_format"] = result["config"]["format"]
                options["export_dpi"] = result["config"]["dpi"]
                options["export_title_mode"] = result["config"]["title_mode"]
                options["export_show_station"] = False
                options["export_show_legend"] = result["config"]["show_legend"]
                dialog.destroy()

            btns = ttk.Frame(body)
            btns.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
            ttk.Button(btns, text="Kaydet", command=accept).pack(side="left")
            ttk.Button(btns, text="Vazgeç", command=dialog.destroy).pack(side="right")
            dialog.wait_window()
            return result["config"]

        def save_kesit():
            export_config = export_settings_dialog()
            if not export_config:
                return
            fmt = export_config["format"].lower()
            ext = ".jpg" if fmt == "jpg" else f".{fmt}"
            default_name = kesit_kayit_dosya_adi(options.get("selected_sondajlar") or sondajlar)
            path = filedialog.asksaveasfilename(
                defaultextension=ext,
                initialfile=f"{default_name}{ext}",
                filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            )
            if not path:
                return
            ax = fig.axes[0] if fig.axes else None
            old_title = ax.get_title() if ax else ""
            tool = section_tool()
            info_text = getattr(tool, "info_text", None)
            vertex_markers = getattr(tool, "vertex_markers", None)
            old_info_visible = info_text.get_visible() if info_text is not None else None
            old_marker_visible = vertex_markers.get_visible() if vertex_markers is not None else None
            well_labels = [text for text in ax.texts if hasattr(text, "_geo_save_text")] if ax else []
            old_well_label_states = [(text, text.get_text(), text.get_fontsize()) for text in well_labels]
            legend_artists = [
                artist for artist in ax.get_children()
                if hasattr(artist, "get_visible") and getattr(artist, "_geo_export_group", None) == "legend"
            ] if ax else []
            old_legend_states = [(artist, artist.get_visible()) for artist in legend_artists]
            try:
                save_section_edits(show_status=False)
                if ax:
                    if export_config["title_mode"] == "none":
                        ax.set_title("")
                    elif export_config["title_mode"] == "full":
                        ax.set_title(old_title, fontsize=12, fontweight='bold')
                    else:
                        ax.set_title("Jeolojik Kesit", fontsize=12, fontweight='bold')
                if not export_config.get("show_station", False):
                    for text in well_labels:
                        text.set_text(text._geo_save_text)
                        text.set_fontsize(getattr(text, "_geo_save_fontsize", text.get_fontsize()))
                if not export_config["show_legend"]:
                    for artist in legend_artists:
                        artist.set_visible(False)
                if tool is not None and hasattr(tool, "refresh_same_unit_seams"):
                    tool.refresh_same_unit_seams()
                if info_text is not None:
                    info_text.set_visible(False)
                if vertex_markers is not None:
                    vertex_markers.set_visible(False)
                fig.savefig(path, dpi=export_config["dpi"], bbox_inches='tight')
                messagebox.showinfo("Başarılı", "Kesit kaydedildi.")
            finally:
                if ax:
                    ax.set_title(old_title, fontsize=12, fontweight='bold')
                for text, old_text, old_fontsize in old_well_label_states:
                    text.set_text(old_text)
                    text.set_fontsize(old_fontsize)
                for artist, old_visible in old_legend_states:
                    artist.set_visible(old_visible)
                if info_text is not None and old_info_visible is not None:
                    info_text.set_visible(old_info_visible)
                if vertex_markers is not None and old_marker_visible is not None:
                    vertex_markers.set_visible(old_marker_visible)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        tool = section_tool()
        if tool is not None and hasattr(tool, "set_history_callback"):
            tool.set_history_callback(update_edit_status)
        update_edit_status(tool)

        tk.Button(top_bar, text="Kesiti Kaydet", bg=COLOR_WARNING, fg="white", font=FONT_BOLD, command=save_kesit).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Düzenlemeyi Kaydet", bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD, command=save_section_edits).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Sıfırla", bg=COLOR_DANGER, fg="white", font=FONT_BOLD, command=reset_section_edits).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Geri Al", bg="#D6EAF8", fg="#111", font=FONT_BOLD, command=undo_section_edit).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="İleri Al", bg="#D5F5E3", fg="#111", font=FONT_BOLD, command=redo_section_edit).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Ayarlar", bg="#AED6F1", fg="#111", font=FONT_BOLD, command=open_preview_settings).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Mercek", bg="#D7BDE2", fg="#111", font=FONT_BOLD, command=open_lens_controls).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Liste", bg="#FAD7A0", fg="#111", font=FONT_BOLD, command=open_edit_list).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Kalite", bg="#F9E79F", fg="#111", font=FONT_BOLD, command=lambda: self.kesit_kalite_penceresi(win, sondajlar, options)).pack(side="left", padx=3, pady=5)
        tk.Button(top_bar, text="Kayıtlı Hale Dön", bg="#E8DAEF", fg="#111", font=FONT_BOLD, command=restore_saved_section_edits).pack(side="left", padx=3, pady=5)
        tk.Label(top_bar, textvariable=edit_status_var, bg="#333", fg="white", font=("Arial", 9, "bold")).pack(side="right", padx=8)
