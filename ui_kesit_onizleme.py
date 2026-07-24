# Dosya: RaporPro/ui_kesit_onizleme.py
import copy
import tkinter as tk
from tkinter import Frame, Listbox, Toplevel, filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from kesit_kalite import build_section_quality_report
from kesit_korelasyon import correlation_relation_id, section_layer_id
from motor import GeoEngine
from performans import perf_tracked
from sabitler import COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD
from ui_kesit_yardimci import kesit_kayit_dosya_adi
from yardimcilar import safe_float


class KesitOnizlemeMixin:
    def kesit_onizle_options_hazirla(self, sondajlar, options=None):
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
        return options

    @perf_tracked("section.preview.prepare")
    def kesit_onizle_figuru_uret(self, sondajlar, options):
        warnings = []

        def collect_warning(msg, level="info"):
            warnings.append((msg, level))

        GeoEngine.reset_warnings()
        fig, result = GeoEngine.kesit_ciz_interaktif(sondajlar, log_callback=collect_warning, options=options)
        quality_report = build_section_quality_report(sondajlar, options)
        return {
            "sondajlar": sondajlar,
            "options": options,
            "fig": fig,
            "result": result,
            "warnings": warnings,
            "quality_report": quality_report,
        }

    def kesit_onizle_async(self, sondajlar, options=None, parent=None):
        options = self.kesit_onizle_options_hazirla(sondajlar, options)
        worker_sondajlar = copy.deepcopy(list(sondajlar or []))
        worker_options = copy.deepcopy(options)
        parent = parent or self.root
        progress = Toplevel(parent)
        self.pencere_hazirla(progress, "Kesit Önizleme", "380x130", (360, 120), modal=False)
        ttk.Label(progress, text="Kesit çizimi hazırlanıyor...", font=FONT_BOLD).pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(progress, text="Büyük kesitlerde bu işlem birkaç saniye sürebilir.", foreground="#555555").pack(anchor="w", padx=14)
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=14, pady=(10, 12))
        bar.start(12)

        def done(result):
            if progress.winfo_exists():
                progress.destroy()
            for msg, level in result.get("warnings", []):
                self.set_status(msg, level=level)
            self.kesit_onizle(
                result["sondajlar"],
                result["options"],
                prebuilt=(result["fig"], result.get("result"), result.get("quality_report")),
            )

        def failed(exc):
            if progress.winfo_exists():
                progress.destroy()
            messagebox.showerror("Kesit", f"Kesit çizimi hazırlanamadı:\n{exc}")

        self.arka_plan_gorevi_baslat(
            "Kesit önizleme hazırla",
            self.kesit_onizle_figuru_uret,
            worker_sondajlar,
            worker_options,
            resource="render",
            status_start="Kesit önizleme arka planda hazırlanıyor.",
            status_success="Kesit önizleme hazırlandı.",
            status_error="Kesit önizleme hazırlanamadı: {error}",
            on_success=done,
            on_error=failed,
        )

    @perf_tracked("section.preview")
    def kesit_onizle(self, sondajlar, options=None, prebuilt=None):
        options = self.kesit_onizle_options_hazirla(sondajlar, options)
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Kesit Önizleme", "1200x800", (980, 640))
        f = Frame(win)
        f.pack(fill="both", expand=True)
        top_bar = tk.Frame(f, bg="#333")
        top_bar.pack(fill="x")
        primary_bar = tk.Frame(top_bar, bg="#333")
        primary_bar.pack(fill="x")
        tool_bar = tk.Frame(top_bar, bg="#444")
        tool_bar.pack(fill="x")
        edit_status_var = tk.StringVar(value="Değişen: 0 | Kayıtlı: 0 | Geri: 0 | İleri: 0")

        def on_draw_warning(msg, level="info"):
            self.root.after(0, lambda: self.set_status(msg, level))

        GeoEngine.reset_warnings()
        if prebuilt:
            fig = prebuilt[0]
            quality_report = prebuilt[2] if len(prebuilt) > 2 and prebuilt[2] else build_section_quality_report(sondajlar, options)
        else:
            fig, _ = GeoEngine.kesit_ciz_interaktif(sondajlar, log_callback=on_draw_warning, options=options)
            quality_report = build_section_quality_report(sondajlar, options)
        chart = FigureCanvasTkAgg(fig, master=f)
        chart.get_tk_widget().pack(fill="both", expand=True)
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
            return (
                edit_id.startswith("lens:")
                or edit_id.startswith("half-lens:")
                or edit_id.startswith("semantic-lens:")
            )

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
            elif edit_id.startswith("semantic-lens:"):
                tip_indices = list(getattr(poly, "_geo_lens_tip_indices", []) or [])

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

        def open_correlation_editor():
            if str(getattr(fig, "_geo_section_engine", "v1")).lower() != "v2":
                messagebox.showinfo(
                    "Korelasyon",
                    "Korelasyon düzenleyicisi V2 motorunda kullanılabilir.\n"
                    "Ayarlar bölümünden Kesit Motoru V2'yi seçip yeniden çizin.",
                )
                return

            links = list(getattr(fig, "_geo_correlation_links", []) or [])
            if not links:
                messagebox.showwarning("Korelasyon", "Düzenlenecek sondaj çifti bulunamadı.")
                return

            dialog = Toplevel(win)
            self.pencere_hazirla(
                dialog,
                "Kesit Korelasyon Düzenleyicisi",
                "980x620",
                (860, 520),
                modal=True,
            )
            body = ttk.Frame(dialog, padding=10)
            body.pack(fill="both", expand=True)
            overrides = copy.deepcopy(options.get("correlation_overrides") or {})
            dirty_var = tk.StringVar(value="Otomatik korelasyonlar gösteriliyor.")

            pair_labels = [
                f"{link.get('left_no', 'SK')} → {link.get('right_no', 'SK')}"
                for link in links
            ]
            pair_var = tk.StringVar(value=pair_labels[0])
            header = ttk.Frame(body)
            header.pack(fill="x")
            ttk.Label(header, text="Sondaj çifti", font=FONT_BOLD).pack(side="left")
            pair_combo = ttk.Combobox(
                header,
                textvariable=pair_var,
                values=pair_labels,
                width=28,
                state="readonly",
            )
            pair_combo.pack(side="left", padx=8)
            ttk.Label(header, textvariable=dirty_var, foreground="#8A5A00").pack(side="right")

            relation_frame = ttk.LabelFrame(body, text="Mevcut ve bekleyen bağlantılar", padding=8)
            relation_frame.pack(fill="both", expand=True, pady=(10, 8))
            relation_list = Listbox(relation_frame, height=13, font=("Consolas", 9))
            relation_list.pack(fill="both", expand=True)
            relation_rows = []

            editor = ttk.LabelFrame(body, text="Manuel korelasyon", padding=8)
            editor.pack(fill="x")
            left_var = tk.StringVar()
            right_var = tk.StringVar()
            kind_var = tk.StringVar(value="Aynı birim")
            ttk.Label(editor, text="Sol tabaka").grid(row=0, column=0, sticky="w", padx=4, pady=3)
            left_combo = ttk.Combobox(editor, textvariable=left_var, state="readonly", width=42)
            left_combo.grid(row=1, column=0, sticky="ew", padx=4, pady=3)
            ttk.Label(editor, text="Sağ tabaka").grid(row=0, column=1, sticky="w", padx=4, pady=3)
            right_combo = ttk.Combobox(editor, textvariable=right_var, state="readonly", width=42)
            right_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=3)
            ttk.Label(editor, text="Bağlantı türü").grid(row=0, column=2, sticky="w", padx=4, pady=3)
            ttk.Combobox(
                editor,
                textvariable=kind_var,
                values=("Aynı birim", "Fasiyes geçişi"),
                width=18,
                state="readonly",
            ).grid(row=1, column=2, sticky="ew", padx=4, pady=3)
            editor.columnconfigure(0, weight=1)
            editor.columnconfigure(1, weight=1)

            layer_state = {"left": [], "right": []}

            def current_link():
                try:
                    idx = pair_labels.index(pair_var.get())
                except ValueError:
                    idx = 0
                return links[idx]

            def layer_label(layer):
                return (
                    f"{safe_float(layer.get('top')):.2f}-{safe_float(layer.get('bot')):.2f} m | "
                    f"{layer.get('detail_name') or layer.get('text') or layer.get('code') or '-'}"
                )

            def pair_override(link):
                key = link.get("pair_key") or f"{link.get('left_no')}::{link.get('right_no')}"
                value = overrides.get(key)
                if not isinstance(value, dict):
                    value = {"blocked": [], "forced": []}
                    overrides[key] = value
                value.setdefault("blocked", [])
                value.setdefault("forced", [])
                return key, value

            def reload_relations():
                relation_rows.clear()
                relation_list.delete(0, tk.END)
                link = current_link()
                _, override = pair_override(link)
                forced_ids = {
                    correlation_relation_id(item.get("left_id"), item.get("right_id"))
                    for item in override.get("forced", [])
                    if isinstance(item, dict)
                }
                current_ids = set()
                for relation in link.get("relations", []):
                    relation_id = relation.get("relation_id") or correlation_relation_id(
                        relation.get("left_id"),
                        relation.get("right_id"),
                    )
                    current_ids.add(relation_id)
                    source = "MANUEL" if relation.get("source") == "manual" else "OTOMATİK"
                    kind = "AYNI BİRİM" if relation.get("kind") == "match" else "FASİYES"
                    if relation.get("kind") == "match":
                        name = relation.get("detail_name") or "-"
                    else:
                        name = f"{relation.get('left_name') or '-'} → {relation.get('right_name') or '-'}"
                    confidence = safe_float(relation.get("confidence")) * 100
                    relation_rows.append({"type": "relation", "value": relation})
                    relation_list.insert(
                        tk.END,
                        f"{source:<8} | {kind:<11} | %{confidence:>3.0f} | {name}",
                    )

                for forced in override.get("forced", []):
                    if not isinstance(forced, dict):
                        continue
                    relation_id = correlation_relation_id(forced.get("left_id"), forced.get("right_id"))
                    if relation_id in current_ids:
                        continue
                    relation_rows.append({"type": "forced", "value": forced})
                    relation_list.insert(
                        tk.END,
                        f"BEKLİYOR | {'AYNI BİRİM' if forced.get('kind') == 'match' else 'FASİYES':<11} | --- | yeniden çizilecek",
                    )

                for relation_id in override.get("blocked", []):
                    relation_rows.append({"type": "blocked", "value": relation_id})
                    relation_list.insert(tk.END, f"ENGELLİ  | BAĞLANTI KESİK | --- | {relation_id}")

                if not relation_rows:
                    relation_list.insert(tk.END, "Bu sondaj çifti arasında korelasyon bulunamadı.")

            def reload_layers(event=None):
                link = current_link()
                layer_state["left"] = list(link.get("layers1", []) or [])
                layer_state["right"] = list(link.get("layers2", []) or [])
                left_values = [layer_label(layer) for layer in layer_state["left"]]
                right_values = [layer_label(layer) for layer in layer_state["right"]]
                left_combo.configure(values=left_values)
                right_combo.configure(values=right_values)
                left_var.set(left_values[0] if left_values else "")
                right_var.set(right_values[0] if right_values else "")
                reload_relations()

            def selected_layer(side, combo):
                layers = layer_state.get(side, [])
                idx = combo.current()
                return layers[idx] if 0 <= idx < len(layers) else None

            def add_forced_relation():
                link = current_link()
                left_layer = selected_layer("left", left_combo)
                right_layer = selected_layer("right", right_combo)
                if left_layer is None or right_layer is None:
                    messagebox.showwarning("Korelasyon", "Sol ve sağ tabakayı seçin.", parent=dialog)
                    return
                left_id = section_layer_id(link.get("left_no"), left_layer)
                right_id = section_layer_id(link.get("right_no"), right_layer)
                relation_id = correlation_relation_id(left_id, right_id)
                _, override = pair_override(link)
                forced = [
                    item for item in override.get("forced", [])
                    if isinstance(item, dict)
                    and item.get("left_id") != left_id
                    and item.get("right_id") != right_id
                ]
                requested_kind = "match" if kind_var.get() == "Aynı birim" else "facies"
                same_identity = left_layer.get("code") == right_layer.get("code")
                if requested_kind == "match" and not same_identity:
                    requested_kind = "facies"
                    kind_var.set("Fasiyes geçişi")
                    self.set_status(
                        "Farklı ana birimler fasiyes geçişi olarak kaydedildi.",
                        level="info",
                    )
                forced.append({
                    "left_id": left_id,
                    "right_id": right_id,
                    "kind": requested_kind,
                })
                override["forced"] = forced
                override["blocked"] = [
                    item for item in override.get("blocked", [])
                    if item != relation_id
                ]
                dirty_var.set("Manuel bağlantı bekliyor; yeniden çizerek uygulanacak.")
                reload_relations()

            def block_selected_relation():
                selection = relation_list.curselection()
                if not selection or selection[0] >= len(relation_rows):
                    messagebox.showwarning("Korelasyon", "Kesilecek bağlantıyı seçin.", parent=dialog)
                    return
                row = relation_rows[selection[0]]
                link = current_link()
                _, override = pair_override(link)
                if row["type"] == "blocked":
                    return
                value = row["value"]
                relation_id = value.get("relation_id") if isinstance(value, dict) else ""
                if not relation_id and isinstance(value, dict):
                    relation_id = correlation_relation_id(value.get("left_id"), value.get("right_id"))
                if not relation_id:
                    return
                if relation_id not in override["blocked"]:
                    override["blocked"].append(relation_id)
                override["forced"] = [
                    item for item in override.get("forced", [])
                    if correlation_relation_id(item.get("left_id"), item.get("right_id")) != relation_id
                ]
                dirty_var.set("Bağlantı kesilecek; yeniden çizerek uygulanacak.")
                reload_relations()

            def remove_selected_override():
                selection = relation_list.curselection()
                if not selection or selection[0] >= len(relation_rows):
                    messagebox.showwarning("Korelasyon", "Kaldırılacak manuel kararı seçin.", parent=dialog)
                    return
                row = relation_rows[selection[0]]
                link = current_link()
                _, override = pair_override(link)
                if row["type"] == "blocked":
                    override["blocked"] = [
                        item for item in override.get("blocked", [])
                        if item != row["value"]
                    ]
                else:
                    value = row["value"]
                    relation_id = value.get("relation_id") if isinstance(value, dict) else ""
                    if not relation_id and isinstance(value, dict):
                        relation_id = correlation_relation_id(value.get("left_id"), value.get("right_id"))
                    source = value.get("source") if isinstance(value, dict) else ""
                    if source != "manual" and relation_id not in {
                        correlation_relation_id(item.get("left_id"), item.get("right_id"))
                        for item in override.get("forced", [])
                        if isinstance(item, dict)
                    }:
                        messagebox.showinfo(
                            "Korelasyon",
                            "Otomatik bağlantıyı kaldırmak için 'Bağlantıyı Kes' kullanın.",
                            parent=dialog,
                        )
                        return
                    override["forced"] = [
                        item for item in override.get("forced", [])
                        if correlation_relation_id(item.get("left_id"), item.get("right_id")) != relation_id
                    ]
                dirty_var.set("Manuel karar kaldırıldı; yeniden çizerek uygulanacak.")
                reload_relations()

            def apply_and_redraw():
                cleaned = {}
                for key, value in overrides.items():
                    if not isinstance(value, dict):
                        continue
                    blocked = list(dict.fromkeys(value.get("blocked", []) or []))
                    forced = list(value.get("forced", []) or [])
                    if blocked or forced:
                        cleaned[key] = {"blocked": blocked, "forced": forced}
                if cleaned:
                    options["correlation_overrides"] = cleaned
                else:
                    options.pop("correlation_overrides", None)
                save_section_edits(show_status=False)
                self._kesit_ayarlari_kaydet(options.copy())
                if self.aktif_dosya_yolu:
                    self.veri_kaydet()
                dialog.destroy()
                win.destroy()
                self.kesit_onizle_async(sondajlar, options)

            pair_combo.bind("<<ComboboxSelected>>", reload_layers)
            actions = ttk.Frame(body)
            actions.pack(fill="x", pady=(0, 8))
            ttk.Button(actions, text="Bağla / Kilitle", command=add_forced_relation).pack(side="left")
            ttk.Button(actions, text="Bağlantıyı Kes", command=block_selected_relation).pack(side="left", padx=6)
            ttk.Button(actions, text="Manuel Kararı Kaldır", command=remove_selected_override).pack(side="left")
            ttk.Button(actions, text="Uygula ve Yeniden Çiz", command=apply_and_redraw).pack(side="right")
            ttk.Button(actions, text="Vazgeç", command=dialog.destroy).pack(side="right", padx=6)
            reload_layers()

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
            set_live_group_visible(
                "detailed_lithology",
                config.get("show_detailed_lithology_labels", False),
            )
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
            detailed_lithology_var = tk.BooleanVar(
                value=option_as_bool(
                    "show_detailed_lithology_labels",
                    str(options.get("section_engine", "v1")).lower() == "v2",
                )
            )
            seams_var = tk.BooleanVar(value=option_as_bool("hide_same_unit_seams", True))
            title_var = tk.StringVar(value=str(options.get("title_mode", "full")))
            engine_var = tk.StringVar(
                value="V2 (Deneysel)"
                if str(options.get("section_engine", "v1")).lower() == "v2"
                else "V1 (Stabil)"
            )

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
                ("Birim adlarını göster", detailed_lithology_var),
            ]
            for idx, (label, var) in enumerate(live_checks):
                ttk.Checkbutton(live_frame, text=label, variable=var).grid(row=idx // 3, column=idx % 3, sticky="w", padx=6, pady=3)
            ttk.Label(live_frame, text="Başlık").grid(row=4, column=0, sticky="w", padx=6, pady=(8, 3))
            ttk.Combobox(live_frame, textvariable=title_var, values=("full", "simple", "none"), width=10, state="readonly").grid(row=4, column=1, sticky="w", padx=6, pady=(8, 3))
            ttk.Label(redraw_frame, text="Kesit motoru").grid(row=0, column=3, sticky="e", padx=5, pady=3)
            engine_combo = ttk.Combobox(
                redraw_frame,
                textvariable=engine_var,
                values=("V1 (Stabil)", "V2 (Deneysel)"),
                width=16,
                state="readonly",
            )
            engine_combo.grid(row=0, column=4, sticky="w", padx=5, pady=3)
            engine_combo.bind(
                "<<ComboboxSelected>>",
                lambda event=None: detailed_lithology_var.set(engine_var.get().startswith("V2")),
            )

            entries = {}
            redraw_fields = [
                ("Düşey abartı", "vertical_exaggeration", "1.0"),
                ("Eşleşme toleransı", "corr_tolerance", "3.0"),
                ("Şematik aralık", "dx_default", "25.0"),
                ("Kuyu genişliği", "well_width", "2.0"),
                ("Mercek max. kalınlık", "lens_max_thickness", "2.0"),
                ("Mercek kapanma", "lens_closure_ratio", "0.58"),
                ("Genel tarama", "section_pattern_density", "10.0"),
                ("Kil tarama", "clay_pattern_density", ""),
                ("Silt tarama", "silt_pattern_density", ""),
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
                    "show_detailed_lithology_labels": detailed_lithology_var.get(),
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
                new_options["section_engine"] = "v2" if engine_var.get().startswith("V2") else "v1"
                new_options["section_signature"] = self._kesit_section_signature(new_options)
                save_section_edits(show_status=False)
                self._kesit_ayarlari_kaydet(new_options.copy())
                dialog.destroy()
                win.destroy()
                self.kesit_onizle_async(sondajlar, new_options)

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

        tk.Button(primary_bar, text="Kesiti Kaydet", bg=COLOR_WARNING, fg="white", font=FONT_BOLD, command=save_kesit).pack(side="left", padx=3, pady=4)
        tk.Button(primary_bar, text="Düzenlemeyi Kaydet", bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD, command=save_section_edits).pack(side="left", padx=3, pady=4)
        tk.Button(primary_bar, text="Geri Al", bg="#D6EAF8", fg="#111", font=FONT_BOLD, command=undo_section_edit).pack(side="left", padx=3, pady=4)
        tk.Button(primary_bar, text="İleri Al", bg="#D5F5E3", fg="#111", font=FONT_BOLD, command=redo_section_edit).pack(side="left", padx=3, pady=4)
        tk.Label(primary_bar, textvariable=edit_status_var, bg="#333", fg="white", font=("Arial", 9, "bold")).pack(side="right", padx=8)
        tk.Button(tool_bar, text="Ayarlar", bg="#AED6F1", fg="#111", font=FONT_BOLD, command=open_preview_settings).pack(side="left", padx=3, pady=4)
        tk.Button(tool_bar, text="Korelasyon", bg="#C7E9F1", fg="#111", font=FONT_BOLD, command=open_correlation_editor).pack(side="left", padx=3, pady=4)
        tk.Button(tool_bar, text="Mercek", bg="#D7BDE2", fg="#111", font=FONT_BOLD, command=open_lens_controls).pack(side="left", padx=3, pady=4)
        tk.Button(tool_bar, text="Liste", bg="#FAD7A0", fg="#111", font=FONT_BOLD, command=open_edit_list).pack(side="left", padx=3, pady=4)
        tk.Button(tool_bar, text="Kalite", bg="#F9E79F", fg="#111", font=FONT_BOLD, command=lambda: self.kesit_kalite_penceresi(win, sondajlar, options)).pack(side="left", padx=3, pady=4)
        tk.Button(tool_bar, text="Sıfırla", bg=COLOR_DANGER, fg="white", font=FONT_BOLD, command=reset_section_edits).pack(side="left", padx=3, pady=4)
        tk.Button(tool_bar, text="Kayıtlı Hale Dön", bg="#E8DAEF", fg="#111", font=FONT_BOLD, command=restore_saved_section_edits).pack(side="left", padx=3, pady=4)
