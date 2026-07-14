import os
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

from jeofizik_sheet_motoru import jeofizik_sheet_ozeti, jeofizik_sheet_var_mi
from cikti_kalite import (
    cikti_dosyalari_denetle,
    kalite_manifestosu_yaz,
    proje_parmak_izi,
)
from kalite_kontrol import build_preflight_report
from performans import log_exception, perf_tracked
from proje_motoru import proje_saglik_ozeti
from sabitler import COLOR_BG, COLOR_DANGER, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD
from yardimcilar import safe_float


class KontrolPaneliMixin:
    @perf_tracked("preflight.summary")
    def ozet_on_kontrol(self):
        self.guncelle_veri_objesi()
        self.last_preflight_report = build_preflight_report(self)
        self.ozet_yenile(collect=False)
        errors = len(self.last_preflight_report.get("errors", []))
        warnings = len(self.last_preflight_report.get("warnings", []))
        if errors:
            self.set_status(f"Özet ön kontrol {errors} hata buldu.", level="error")
        elif warnings:
            self.set_status(f"Özet ön kontrol {warnings} uyarı buldu.", level="warning")
        else:
            self.set_status("Özet ön kontrol temiz.", level="success")

    @perf_tracked("summary.refresh")
    def ozet_yenile(self, collect=True):
        if not hasattr(self, "ozet_metric_labels"):
            return
        if collect and hasattr(self, "e_kunye"):
            try:
                self.guncelle_veri_objesi()
            except Exception:
                pass

        kunye = self.veri.get("kunye", {})
        sondajlar = self.veri.get("sondaj", [])
        jeofizik = self.veri.get("jeofizik", {})
        ss_list = jeofizik.get("ss_list", [])
        mt_list = jeofizik.get("mt_list", [])
        jeo_sheet_summary = jeofizik_sheet_ozeti(self.veri)
        jeo_sheet_ok = bool(jeo_sheet_summary.get("ready"))

        total_depth = sum(safe_float(s.get("der")) for s in sondajlar)
        lit_count = sum(1 for s in sondajlar if s.get("litoloji"))
        spt_count = sum(len(s.get("spt", [])) for s in sondajlar)
        pmt_count = sum(len(s.get("pmt", [])) for s in sondajlar)
        kaya_count = sum(len(s.get("kaya", [])) for s in sondajlar)
        layer_count = sum(len(s.get("layers", [])) for s in ss_list)

        proje_adi = str(kunye.get("sahibi") or "").strip()
        self._ozet_set("proje", proje_adi or "Adsız proje", ok=bool(proje_adi))
        konum_parts = [kunye.get("il"), kunye.get("ilce"), kunye.get("mah")]
        konum_text = " / ".join([str(p).strip() for p in konum_parts if str(p or "").strip()])
        konum_ok = bool(str(kunye.get("il") or "").strip() and str(kunye.get("ilce") or "").strip())
        self._ozet_set("konum", konum_text or "Konum girilmemiş", ok=konum_ok)
        self._ozet_set("sondaj", f"{len(sondajlar)} adet, toplam {total_depth:.2f} m", ok=len(sondajlar) > 0 and total_depth > 0)
        self._ozet_set("litoloji", f"{lit_count}/{len(sondajlar)} sondajda litoloji var", ok=lit_count == len(sondajlar) and len(sondajlar) > 0)
        self._ozet_set("deney", f"SPT: {spt_count} | PMT: {pmt_count} | Kaya: {kaya_count}", ok=(spt_count + pmt_count + kaya_count) > 0)
        if jeo_sheet_ok:
            self._ozet_set("jeofizik", f"Sheet: {jeo_sheet_summary['serim']} serim | Tabaka: {jeo_sheet_summary['layers']}", ok=True)
        else:
            self._ozet_set("jeofizik", f"SS: {len(ss_list)} | MT: {len(mt_list)} | Tabaka: {layer_count}", ok=(len(ss_list) + len(mt_list)) > 0)

        file_map = {
            "word_path": self.word_path,
            "lab_excel_path": self.lab_excel_path,
            "jeo_excel_path": self.jeo_excel_path,
            "kml_path": self.kml_path,
            "img_yer": self.img_yer,
            "img_tkgm": self.img_tkgm,
            "img_pga": self.img_pga,
            "img_mjh": getattr(self, "img_mjh", None),
            "word_img_sondaj": self.word_img_sondaj,
            "word_img_jeofizik": self.word_img_jeofizik,
        }
        image_ready = sum(1 for path in [self.img_yer, self.img_tkgm, self.img_pga, getattr(self, "img_mjh", None) or self.img_yer or self.img_tkgm, self.word_img_sondaj, self.word_img_jeofizik] if path and os.path.exists(path))
        self._ozet_set("harita", f"{image_ready}/6 görsel hazır", ok=image_ready > 0)

        label_keys = {
            "word_path": "word", "lab_excel_path": "lab", "jeo_excel_path": "jeo", "kml_path": "kml",
            "img_yer": "yer", "img_tkgm": "tkgm", "img_pga": "pga", "img_mjh": "mjh",
            "word_img_sondaj": "sondaj_img", "word_img_jeofizik": "jeo_img",
        }
        lab_sheet_ready = self._lab_sheet_ready()
        for raw_key, path in file_map.items():
            if raw_key == "lab_excel_path" and lab_sheet_ready:
                rows = self.veri.get("lab_sheet", {}).get("rows", [])
                status = f"LAB Sheet hazır: {len(rows)} satır"
                self._ozet_file_set(label_keys[raw_key], status, True)
                continue
            if raw_key == "jeo_excel_path" and jeo_sheet_ok:
                status = f"Jeofizik Sheet hazır: {jeo_sheet_summary['serim']} serim"
                self._ozet_file_set(label_keys[raw_key], status, True)
                continue
            status, ok = self._dosya_durumu(path)
            self._ozet_file_set(label_keys[raw_key], status, ok)

        health = proje_saglik_ozeti(self.veri, file_map)
        self._saglik_paneli_guncelle(health)
        self._workflow_paneli_guncelle(health)
        self._final_dashboard_guncelle(health)
        self._ozet_preflight_guncelle()

    def _ozet_set(self, key, text, ok=True):
        label = self.ozet_metric_labels.get(key)
        color = COLOR_SUCCESS if ok else COLOR_WARNING
        bg = "#F3FBF6" if ok else "#FFF4E5"
        card = getattr(self, "ozet_metric_cards", {}).get(key)
        title = getattr(self, "ozet_metric_title_labels", {}).get(key)
        if card:
            card.config(bg=bg, highlightbackground=color, highlightcolor=color, highlightthickness=1)
        if title:
            title.config(bg=bg, fg=COLOR_PRIMARY)
        if label:
            label.config(text=text, fg=color, bg=bg)

    def _ozet_file_set(self, key, text, ok=True):
        label = self.ozet_file_labels.get(key)
        display_text = self._ozet_file_text_compact(text)
        if ok:
            color = COLOR_SUCCESS
            bg = "#F3FBF6"
        elif str(text).startswith("Bulunamadı"):
            color = COLOR_DANGER
            bg = "#FDEDEC"
        else:
            color = COLOR_WARNING
            bg = "#FFF4E5"
        card = getattr(self, "ozet_file_cards", {}).get(key)
        title = getattr(self, "ozet_file_title_labels", {}).get(key)
        if card:
            card.config(bg=bg, highlightbackground=color, highlightcolor=color, highlightthickness=1)
        if title:
            title.config(bg=bg, fg=COLOR_PRIMARY)
        if label:
            label.config(text=display_text, fg=color, bg=bg)

    def _ozet_file_text_compact(self, text, max_name_len=36):
        text = str(text or "")
        for prefix in ("Hazır: ", "Bulunamadı: ", "HazÄ±r: ", "BulunamadÄ±: "):
            if text.startswith(prefix):
                name = text[len(prefix):]
                if len(name) > max_name_len:
                    name = name[: max_name_len - 3] + "..."
                return prefix + name
        return text

    def _lab_sheet_ready(self):
        rows = self.veri.get("lab_sheet", {}).get("rows", []) if isinstance(getattr(self, "veri", None), dict) else []
        return any(any(str(cell).strip() for cell in row) for row in rows or [])

    def _jeofizik_sheet_ready(self):
        return jeofizik_sheet_var_mi(getattr(self, "veri", {})) and jeofizik_sheet_ozeti(getattr(self, "veri", {})).get("ready", False)

    def _dosya_durumu(self, path):
        if path and os.path.exists(path):
            return f"Hazır: {os.path.basename(path)}", True
        if path:
            return f"Bulunamadı: {os.path.basename(path)}", False
        return "Seçilmedi", False

    def _saglik_paneli_guncelle(self, health):
        if not hasattr(self, "health_status_label"):
            return
        score = health.get("score", 0)
        state = health.get("state", "-")
        color = COLOR_SUCCESS if score >= 85 else (COLOR_WARNING if score >= 60 else COLOR_DANGER)
        self.health_status_label.config(text=f"{state} - %{score}", fg=color)
        self.health_tag_actions = {}
        self.health_detail_text.config(state="normal")
        self.health_detail_text.delete("1.0", tk.END)
        self.health_detail_text.tag_configure("ok", foreground=COLOR_SUCCESS)
        self.health_detail_text.tag_configure("missing", foreground=COLOR_DANGER)
        self.health_detail_text.tag_configure("clickable", foreground="#1F618D", underline=True)
        for item in health.get("items", []):
            idx = len(self.health_tag_actions)
            row_tag = f"health_item_{idx}"
            mark = "OK" if item.get("ok") else "EKSİK"
            status_tag = "ok" if item.get("ok") else "missing"
            start = self.health_detail_text.index(tk.END)
            self.health_detail_text.insert(tk.END, f"{mark:<6} ", (status_tag, row_tag))
            self.health_detail_text.insert(tk.END, f"{item.get('label')}: ", ("clickable", row_tag))
            self.health_detail_text.insert(tk.END, f"{item.get('detail')}", (row_tag,))
            suggestion = item.get("suggestion")
            if suggestion and not item.get("ok"):
                self.health_detail_text.insert(tk.END, f" -> {suggestion}", ("clickable", row_tag))
            self.health_detail_text.insert(tk.END, "\n", (row_tag,))
            end = self.health_detail_text.index(tk.END)
            self.health_detail_text.tag_add(row_tag, start, end)
            self.health_tag_actions[row_tag] = item
        self.health_detail_text.config(state="disabled")

    def _health_detail_click(self, event):
        if not hasattr(self, "health_detail_text"):
            return
        tags = self.health_detail_text.tag_names(f"@{event.x},{event.y}")
        for tag in tags:
            if tag in getattr(self, "health_tag_actions", {}):
                self._health_item_git(self.health_tag_actions[tag])
                return "break"

    def _health_detail_motion(self, event):
        tags = self.health_detail_text.tag_names(f"@{event.x},{event.y}")
        cursor = "hand2" if any(tag in getattr(self, "health_tag_actions", {}) for tag in tags) else ""
        self.health_detail_text.config(cursor=cursor)

    def _health_item_git(self, item):
        target = item.get("target", "ozet")
        tab_map = {
            "ozet": "tab_ozet",
            "kunye": "tab_kunye",
            "bina": "tab_bina",
            "arazi": "tab_arazi",
            "sondaj": "tab_sondaj",
            "jeofizik": "tab_jeofizik",
            "rapor": "tab_rapor",
            "haritalar": "tab_haritalar",
        }
        tab_attr = tab_map.get(target)
        if tab_attr and hasattr(self, tab_attr):
            self.nb.select(getattr(self, tab_attr))
            self.set_status(f"{item.get('label')} için ilgili sekmeye gidildi.", level="info")
        elif target == "preflight":
            self.ozet_on_kontrol()
        else:
            self.set_status(item.get("suggestion") or item.get("detail") or "Sağlık kalemi seçildi.", level="info")

    def _preflight_target_for_message(self, message):
        text = str(message or "").lower()
        if any(key in text for key in ("proje adi", "il ", "ilce", "mahalle", "kunye", "kü nye", "künye")):
            return "kunye"
        if any(key in text for key in ("sondaj", "litoloji", "spt", "pmt", "kaya", "koordinat", "kuyu", "kesit")):
            return "sondaj"
        if any(key in text for key in ("jeofizik", "sismik", "mikrotremor", "masw", " vp", " vs", " mt", " ss")):
            return "jeofizik"
        if any(key in text for key in ("kml", "harita", "gorsel", "görsel", "resim", "yerbuldurur", "tkgm", "pga")):
            return "haritalar"
        if any(key in text for key in ("word", "sablon", "şablon", "lab excel", "excel")):
            return "rapor"
        return "ozet"

    def _insert_clickable_report(self, text_widget, report):
        text_widget.config(state="normal")
        text_widget.delete("1.0", tk.END)
        text_widget.tag_configure("section", foreground=COLOR_PRIMARY, font=("Consolas", 10, "bold"))
        text_widget.tag_configure("error", foreground=COLOR_DANGER)
        text_widget.tag_configure("warning", foreground=COLOR_WARNING)
        text_widget.tag_configure("info", foreground="#1F618D")
        text_widget.tag_configure("clickable", underline=True)
        action_map = {}
        counter = 0
        text_widget.insert(tk.END, "RAPOR ÖN KONTROL\n", "section")
        text_widget.insert(tk.END, "=" * 18 + "\n\n")
        structured_findings = report.get("findings")
        for title, key, tag in (("HATALAR", "errors", "error"), ("UYARILAR", "warnings", "warning"), ("BILGI", "info", "info")):
            text_widget.insert(tk.END, f"{title}\n", "section")
            if structured_findings is not None:
                items = [item for item in structured_findings if item.get("level") == tag]
            else:
                items = report.get(key, [])
            if not items:
                text_widget.insert(tk.END, "- Yok\n\n")
                continue
            for item in items:
                row_tag = f"preflight_item_{counter}"
                counter += 1
                if isinstance(item, dict):
                    category = item.get("category", "Kontrol")
                    label = item.get("label", "Bulgu")
                    detail = item.get("detail", "")
                    display = f"[{category}] {label}: {detail}"
                    action = dict(item)
                    action.setdefault("message", detail)
                else:
                    display = str(item)
                    action = {"message": item, "target": self._preflight_target_for_message(item)}
                start = text_widget.index(tk.END)
                text_widget.insert(tk.END, f"- {display}\n", (tag, "clickable", row_tag))
                end = text_widget.index(tk.END)
                text_widget.tag_add(row_tag, start, end)
                action_map[row_tag] = action
            text_widget.insert(tk.END, "\n")
        text_widget._preflight_action_map = action_map
        text_widget.bind("<Button-1>", self._preflight_text_click)
        text_widget.bind("<Double-Button-1>", self._preflight_text_click)
        text_widget.bind("<Motion>", self._preflight_text_motion)
        text_widget.config(state="disabled")

    def _preflight_text_click(self, event):
        widget = event.widget
        action_map = getattr(widget, "_preflight_action_map", {})
        for tag in widget.tag_names(f"@{event.x},{event.y}"):
            if tag in action_map:
                self._preflight_item_git(action_map[tag])
                return "break"

    def _preflight_text_motion(self, event):
        widget = event.widget
        action_map = getattr(widget, "_preflight_action_map", {})
        cursor = "hand2" if any(tag in action_map for tag in widget.tag_names(f"@{event.x},{event.y}")) else ""
        widget.config(cursor=cursor)

    def _preflight_item_git(self, action):
        target = action.get("target", "ozet")
        if target == "workbook":
            self.veri_giris_workbook_tksheet_ac(
                initial_sheet=action.get("sheet") or None,
                initial_sondaj=action.get("entity") or None,
                initial_field=action.get("field") or None,
                initial_row=action.get("row"),
            )
        elif target == "kesit":
            self.kesit_secim_penceresi()
        elif target == "cikti":
            self.cikti_merkezi_penceresi()
        elif target == "preflight":
            self.rapor_on_kontrol()
        else:
            self._workflow_git(target)
            field = action.get("field")
            entry_maps = {
                "kunye": getattr(self, "e_kunye", {}),
                "bina": getattr(self, "e_bina", {}),
                "arazi": getattr(self, "e_arazi", {}),
            }
            entry = entry_maps.get(target, {}).get(field) if field else None
            if entry is not None:
                try:
                    entry.focus_set()
                    entry.selection_range(0, tk.END)
                except Exception:
                    pass
        self.set_status(action.get("message") or action.get("detail") or "Ön kontrol kalemi seçildi.", level="info")

    def on_kontrol_merkezi_penceresi(self, report):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Çıktı Ön Kontrol Merkezi", "1120x680", (900, 560), modal=False)

        report_holder = {"value": report}
        summary_var = tk.StringVar()
        filter_var = tk.StringVar(value="Sorunlar")
        search_var = tk.StringVar()
        detail_var = tk.StringVar(value="Bir bulgu seçtiğinizde önerilen işlem burada görünür.")

        header = ttk.Frame(win, padding=(12, 10, 12, 6))
        header.pack(fill="x")
        tk.Label(
            header,
            text="Çıktı Ön Kontrol Merkezi",
            bg=COLOR_BG,
            fg=COLOR_PRIMARY,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")
        summary_label = tk.Label(header, textvariable=summary_var, bg=COLOR_BG, font=FONT_BOLD)
        summary_label.pack(side="right")

        controls = ttk.Frame(win, padding=(12, 0, 12, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="Göster").pack(side="left", padx=(0, 4))
        filter_combo = ttk.Combobox(
            controls,
            textvariable=filter_var,
            values=("Sorunlar", "Tümü", "Hatalar", "Uyarılar", "Bilgi"),
            state="readonly",
            width=13,
        )
        filter_combo.pack(side="left", padx=(0, 12))
        ttk.Label(controls, text="Ara").pack(side="left", padx=(0, 4))
        search_entry = ttk.Entry(controls, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True)

        tree_frame = ttk.Frame(win, padding=(12, 0, 12, 6))
        tree_frame.pack(fill="both", expand=True)
        columns = ("level", "category", "label", "entity", "detail")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "level": "Seviye",
            "category": "Kategori",
            "label": "Kontrol",
            "entity": "Kayıt",
            "detail": "Açıklama",
        }
        widths = {"level": 80, "category": 150, "label": 170, "entity": 90, "detail": 520}
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], minwidth=70, stretch=column == "detail")
        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        tree.tag_configure("error", foreground=COLOR_DANGER)
        tree.tag_configure("warning", foreground="#A65E00")
        tree.tag_configure("info", foreground="#1F618D")
        tree.tag_configure("ok", foreground=COLOR_SUCCESS)

        detail_frame = ttk.LabelFrame(win, text="Önerilen İşlem", padding=(10, 6))
        detail_frame.pack(fill="x", padx=12, pady=(0, 8))
        detail_label = ttk.Label(detail_frame, textvariable=detail_var, wraplength=1040, justify="left")
        detail_label.pack(fill="x")

        action_map = {}

        def current_findings():
            current = report_holder["value"] or {}
            findings = current.get("findings")
            if findings is not None:
                return list(findings)
            converted = []
            for level, key in (("error", "errors"), ("warning", "warnings"), ("info", "info")):
                for detail in current.get(key, []) or []:
                    converted.append({
                        "level": level,
                        "category": "Kontrol",
                        "label": "Bulgu",
                        "detail": str(detail),
                        "target": self._preflight_target_for_message(detail),
                    })
            return converted

        def update_summary():
            current = report_holder["value"] or {}
            errors = len(current.get("errors", []) or [])
            warnings = len(current.get("warnings", []) or [])
            infos = len(current.get("info", []) or [])
            score = current.get("score")
            score_text = f" | Hazırlık %{score}" if score is not None else ""
            summary_var.set(f"{errors} hata | {warnings} uyarı | {infos} bilgi{score_text}")
            summary_label.config(fg=COLOR_DANGER if errors else (COLOR_WARNING if warnings else COLOR_SUCCESS))

        def populate(*_args):
            tree.delete(*tree.get_children())
            action_map.clear()
            choice = filter_var.get()
            level_filter = {
                "Hatalar": {"error"},
                "Uyarılar": {"warning"},
                "Bilgi": {"info"},
                "Sorunlar": {"error", "warning"},
                "Tümü": {"error", "warning", "info", "ok"},
            }.get(choice, {"error", "warning"})
            query = search_var.get().strip().casefold()
            marks = {"error": "HATA", "warning": "UYARI", "info": "BİLGİ", "ok": "OK"}
            visible = 0
            for idx, finding in enumerate(current_findings()):
                level = finding.get("level", "info")
                if level not in level_filter:
                    continue
                haystack = " ".join(
                    str(finding.get(key, ""))
                    for key in ("category", "label", "entity", "detail", "suggestion")
                ).casefold()
                if query and query not in haystack:
                    continue
                iid = f"finding_{idx}"
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        marks.get(level, level.upper()),
                        finding.get("category", "Kontrol"),
                        finding.get("label", "Bulgu"),
                        finding.get("entity", ""),
                        finding.get("detail", ""),
                    ),
                    tags=(level,),
                )
                action_map[iid] = finding
                visible += 1
            if not visible:
                tree.insert("", "end", iid="empty", values=("OK", "Kontrol", "Gösterilecek bulgu yok", "", "Seçili filtre temiz."), tags=("ok",))
            update_summary()

        def selected_action():
            selection = tree.selection()
            return action_map.get(selection[0]) if selection else None

        def on_select(_event=None):
            action = selected_action()
            if not action:
                detail_var.set("Bir bulgu seçtiğinizde önerilen işlem burada görünür.")
                return
            suggestion = action.get("suggestion") or "İlgili kaydı kontrol edin."
            detail_var.set(f"{action.get('detail', '')}\n{suggestion}")

        def go_selected(_event=None):
            action = selected_action()
            if action:
                self._preflight_item_git(action)
            return "break"

        def copy_selected():
            action = selected_action()
            if not action:
                return
            text = f"{action.get('label', 'Bulgu')}: {action.get('detail', '')}"
            if action.get("suggestion"):
                text += f"\nÖneri: {action['suggestion']}"
            win.clipboard_clear()
            win.clipboard_append(text)
            self.set_status("Ön kontrol bulgusu panoya kopyalandı.", level="success")

        def refresh():
            try:
                self.guncelle_veri_objesi(silent=True)
            except Exception as exc:
                log_exception("preflight.center.collect", exc_value=exc)
            refreshed = build_preflight_report(self)
            report_holder["value"] = refreshed
            self.last_preflight_report = refreshed
            populate()
            self.ozet_yenile(collect=False)

        filter_combo.bind("<<ComboboxSelected>>", populate)
        search_var.trace_add("write", populate)
        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<Double-Button-1>", go_selected)
        tree.bind("<Return>", go_selected)

        buttons = ttk.Frame(win, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Yenile", command=refresh).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="İlgili Yere Git", command=go_selected).pack(side="left", padx=5)
        ttk.Button(buttons, text="Kopyala", command=copy_selected).pack(side="left", padx=5)
        ttk.Button(buttons, text="Kapat", command=win.destroy).pack(side="right")

        populate()
        search_entry.focus_set()
        return win

    def _ozet_preflight_guncelle(self):
        if not hasattr(self, "ozet_preflight_text"):
            return
        if self.last_preflight_report:
            errors = len(self.last_preflight_report.get("errors", []) or [])
            warnings = len(self.last_preflight_report.get("warnings", []) or [])
            infos = len(self.last_preflight_report.get("info", []) or [])
            if errors:
                summary = f"{errors} hata, {warnings} uyarı"
                color = COLOR_DANGER
                role = "danger"
            elif warnings:
                summary = f"0 hata, {warnings} uyarı"
                color = COLOR_WARNING
                role = "warning"
            else:
                summary = f"Temiz | {infos} bilgi"
                color = COLOR_SUCCESS
                role = "success"
            if hasattr(self, "ozet_preflight_summary_label"):
                self.ozet_preflight_summary_label.config(text=summary, fg=color)
            if hasattr(self, "ozet_preflight_action_button"):
                self.configure_modern_button(self.ozet_preflight_action_button, text="Yenile", role=role, outline=True)
            self._insert_clickable_report(self.ozet_preflight_text, self.last_preflight_report)
        else:
            if hasattr(self, "ozet_preflight_summary_label"):
                self.ozet_preflight_summary_label.config(text="Ön kontrol bekliyor", fg="#555555")
            if hasattr(self, "ozet_preflight_action_button"):
                self.configure_modern_button(self.ozet_preflight_action_button, text="Çalıştır", role="warning", outline=True)
            self.ozet_preflight_text.config(state="normal")
            self.ozet_preflight_text.delete("1.0", tk.END)
            self.ozet_preflight_text.insert("1.0", "Ön kontrol henüz çalıştırılmadı.")
            self.ozet_preflight_text.config(state="disabled")

    @perf_tracked("final_control.build")
    def final_kontrol_raporu_olustur(self):
        if hasattr(self, "e_kunye"):
            try:
                self.guncelle_veri_objesi(silent=True)
            except Exception as exc:
                log_exception("final_control.collect", exc_value=exc)

        preflight = build_preflight_report(self)
        self.last_preflight_report = preflight
        health = proje_saglik_ozeti(self.veri, self._dosya_map())
        items = []
        represented = set()

        for check in preflight.get("checks", []):
            level = "ok" if check.get("ok") else check.get("failure_level", "warning")
            item = {
                "id": check.get("id"),
                "category": check.get("category", "Kontrol"),
                "label": check.get("label", "Kontrol"),
                "level": level,
                "detail": check.get("detail", ""),
                "target": check.get("target", "ozet"),
                "suggestion": check.get("suggestion", ""),
                "entity": check.get("entity", ""),
                "field": check.get("field", ""),
                "sheet": check.get("sheet", ""),
            }
            items.append(item)
            represented.add((item["id"], item["detail"]))

        for finding in preflight.get("findings", []):
            identity = (finding.get("id"), finding.get("detail", ""))
            if identity in represented:
                continue
            items.append({
                "id": finding.get("id"),
                "category": finding.get("category", "Kontrol"),
                "label": finding.get("label", "Bulgu"),
                "level": finding.get("level", "info"),
                "detail": finding.get("detail", ""),
                "target": finding.get("target", "ozet"),
                "suggestion": finding.get("suggestion", ""),
                "entity": finding.get("entity", ""),
                "field": finding.get("field", ""),
                "sheet": finding.get("sheet", ""),
                "row": finding.get("row"),
            })

        output_quality = getattr(self, "last_output_quality_report", None)
        output_errors = 0
        output_warnings = 0
        if output_quality:
            output_findings = list(output_quality.get("findings", []) or [])
            if (
                output_quality.get("project_fingerprint")
                and output_quality.get("project_fingerprint") != proje_parmak_izi(self.veri)
            ):
                output_findings.append({
                    "id": "cikti.guncellik",
                    "category": "Çıktı kalitesi",
                    "label": "Güncelliğini yitirmiş çıktı",
                    "level": "warning",
                    "detail": "Proje verisi son çıktı kalite denetiminden sonra değişmiş.",
                    "target": "cikti",
                    "suggestion": "Çıktıları güncel proje verisiyle yeniden oluşturun.",
                })
            for finding in output_findings:
                level = finding.get("level", "info")
                output_errors += int(level == "error")
                output_warnings += int(level == "warning")
                items.append({
                    "id": finding.get("id"),
                    "category": finding.get("category", "Çıktı kalitesi"),
                    "label": finding.get("label", "Çıktı denetimi"),
                    "level": level,
                    "detail": finding.get("detail", ""),
                    "target": finding.get("target", "cikti"),
                    "suggestion": finding.get("suggestion", ""),
                    "entity": "",
                    "field": "",
                    "sheet": "",
                })

        level_order = {"error": 0, "warning": 1, "info": 2, "ok": 3}
        items.sort(key=lambda item: (
            str(item.get("category", "")),
            level_order.get(item.get("level"), 9),
            str(item.get("entity", "")),
            str(item.get("label", "")),
        ))
        error_count = len(preflight.get("errors", []) or []) + output_errors
        warning_count = len(preflight.get("warnings", []) or []) + output_warnings
        state = "HATALAR VAR" if error_count else ("UYARILAR VAR" if warning_count else preflight.get("state", "HAZIR"))
        return {
            "state": state,
            "score": preflight.get("score", 0),
            "errors": error_count,
            "warnings": warning_count,
            "items": items,
            "health": health,
            "preflight": preflight,
        }

    def final_kontrol_penceresi(self):
        existing = getattr(self, "_tamamlama_merkezi_win", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                refresh_callback = getattr(self, "_tamamlama_merkezi_refresh", None)
                if refresh_callback:
                    refresh_callback()
                return existing
        except Exception:
            pass

        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Proje Tamamlama Merkezi", "1040x700", (820, 540), modal=False)
        self._tamamlama_merkezi_win = win

        header = ttk.Frame(win, padding=(12, 10, 12, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Proje Tamamlama Merkezi", font=("Segoe UI", 14, "bold")).pack(side="left")
        status_var = tk.StringVar(value="Kontrol hazırlanıyor...")
        status_label = tk.Label(header, textvariable=status_var, bg=COLOR_BG, fg="#333333", font=("Segoe UI", 10, "bold"), anchor="e")
        status_label.pack(side="right", fill="x", expand=True, padx=(12, 0))

        steps = ttk.LabelFrame(win, text="Tamamlama Adımları", padding=8)
        steps.pack(fill="x", padx=12, pady=(0, 8))
        steps_inner = ttk.Frame(steps)
        steps_inner.pack(fill="x")

        body = ttk.Frame(win, padding=(12, 0, 12, 8))
        body.pack(fill="both", expand=True)
        txt = tk.Text(body, wrap="word", font=("Consolas", 10), bg="#FAFAFA")
        scroll = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        report_holder = {"value": None}

        def refresh():
            report = self.final_kontrol_raporu_olustur()
            report_holder["value"] = report
            color = COLOR_SUCCESS if report["errors"] == 0 and report["warnings"] == 0 else (COLOR_WARNING if report["errors"] == 0 else COLOR_DANGER)
            status_label.config(fg=color)
            status_var.set(f"{report['state']} - %{report['score']} | {report['errors']} hata, {report['warnings']} uyarı")
            self.final_kontrol_text_doldur(txt, report)
            self.ozet_yenile(collect=False)

        def audit_outputs():
            if self.cikti_kalite_dosyalari_sec(parent=win):
                refresh()

        def first_issue():
            report = report_holder.get("value") or self.final_kontrol_raporu_olustur()
            items = report.get("items", [])
            item = next((row for row in items if row.get("level") == "error"), None)
            if item is None:
                item = next((row for row in items if row.get("level") == "warning"), None)
            if item:
                self.final_kontrol_item_git(item)
            else:
                self.set_status("Tamamlama kontrolünde gidilecek hata veya uyarı yok.", level="success")

        self.responsive_button_row(
            steps_inner,
            [
                ("1. Kontrolü Yenile", refresh, COLOR_WARNING, "Proje verisini yeniden denetle"),
                ("İlk Eksik Alana Git", first_issue, COLOR_PRIMARY, "İlk hata veya uyarının bulunduğu alana git"),
                ("2. Raporu Oluştur", self.raporla, COLOR_SUCCESS, "Word raporunu oluştur"),
                ("3. Çıktıları Topla", self.cikti_merkezi_penceresi, "#117A65", "Log, kesit ve görselleri çıktı klasöründe topla"),
                ("4. Çıktıyı Denetle", audit_outputs, "#5B6B7A", "Hazır dosyaların çıktı kalitesini denetle"),
            ],
            min_width=175,
            max_cols=5,
            pady=2,
        )

        footer = ttk.Frame(win, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        self.modern_button(footer, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")

        def clear_window_ref(event=None):
            if event is None or event.widget is win:
                self._tamamlama_merkezi_win = None
                self._tamamlama_merkezi_refresh = None

        win.bind("<Destroy>", clear_window_ref, add="+")
        self._tamamlama_merkezi_refresh = refresh
        refresh()
        return win

    def tamamlama_merkezi_penceresi(self):
        """Yeni adla tek giriş noktası; eski final kontrol çağrıları çalışmaya devam eder."""
        return self.final_kontrol_penceresi()

    def cikti_kalite_dosyalari_sec(self, parent=None):
        paths = filedialog.askopenfilenames(
            parent=parent,
            title="Denetlenecek çıktıları seçin",
            filetypes=[
                ("Desteklenen çıktılar", "*.docx *.pdf *.jpg *.jpeg *.png *.xlsx *.xlsm *.svg"),
                ("Tüm dosyalar", "*.*"),
            ],
        )
        if not paths:
            return None
        report = cikti_dosyalari_denetle(paths, veri=self.veri)
        self.last_output_quality_report = report
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(paths[0])), "RaporPro_Cikti_Kalite.json")
        kalite_manifestosu_yaz(manifest_path, report, veri=self.veri)
        errors = len(report.get("errors", []))
        warnings = len(report.get("warnings", []))
        message = (
            f"Denetlenen dosya: {len(report.get('files', []))}\n"
            f"Hata: {errors} | Uyarı: {warnings}\n\n"
            f"Kalite manifestosu:\n{manifest_path}"
        )
        if errors or warnings:
            messagebox.showwarning("Çıktı Kalite Denetimi", message, parent=parent)
        else:
            messagebox.showinfo("Çıktı Kalite Denetimi", message, parent=parent)
        return report

    def final_kontrol_text_doldur(self, text_widget, report):
        text_widget.config(state="normal")
        text_widget.delete("1.0", tk.END)
        text_widget.tag_configure("header", foreground=COLOR_PRIMARY, font=("Consolas", 11, "bold"))
        text_widget.tag_configure("ok", foreground=COLOR_SUCCESS)
        text_widget.tag_configure("warning", foreground=COLOR_WARNING)
        text_widget.tag_configure("error", foreground=COLOR_DANGER)
        text_widget.tag_configure("clickable", underline=True)
        action_map = {}
        counter = 0

        text_widget.insert(tk.END, "PROJE TAMAMLAMA MERKEZİ\n", "header")
        text_widget.insert(tk.END, "=" * 26 + "\n")
        text_widget.insert(tk.END, f"Durum: {report['state']} | Puan: %{report['score']} | Hata: {report['errors']} | Uyarı: {report['warnings']}\n\n")

        current_category = None
        marks = {"ok": "OK", "warning": "UYARI", "error": "HATA", "info": "BİLGİ"}
        for item in report.get("items", []):
            category = item.get("category", "Kontrol")
            if category != current_category:
                current_category = category
                text_widget.insert(tk.END, f"\n{category}\n", "header")
            row_tag = f"final_control_item_{counter}"
            counter += 1
            level = item.get("level", "info")
            mark = marks.get(level, "BİLGİ")
            start = text_widget.index(tk.END)
            text_widget.insert(tk.END, f"{mark:<6} ", (level, row_tag))
            text_widget.insert(tk.END, f"{item.get('label')}: ", ("clickable", row_tag))
            text_widget.insert(tk.END, f"{item.get('detail')}", (row_tag,))
            if item.get("suggestion") and level != "ok":
                text_widget.insert(tk.END, f" -> {item.get('suggestion')}", ("clickable", row_tag))
            text_widget.insert(tk.END, "\n", (row_tag,))
            end = text_widget.index(tk.END)
            text_widget.tag_add(row_tag, start, end)
            action_map[row_tag] = item

        text_widget._final_control_action_map = action_map
        text_widget.bind("<Button-1>", self.final_kontrol_text_click)
        text_widget.bind("<Double-Button-1>", self.final_kontrol_text_click)
        text_widget.bind("<Motion>", self.final_kontrol_text_motion)
        text_widget.config(state="disabled")

    def final_kontrol_text_click(self, event):
        widget = event.widget
        action_map = getattr(widget, "_final_control_action_map", {})
        for tag in widget.tag_names(f"@{event.x},{event.y}"):
            if tag in action_map:
                self.final_kontrol_item_git(action_map[tag])
                return "break"

    def final_kontrol_text_motion(self, event):
        widget = event.widget
        action_map = getattr(widget, "_final_control_action_map", {})
        cursor = "hand2" if any(tag in action_map for tag in widget.tag_names(f"@{event.x},{event.y}")) else ""
        widget.config(cursor=cursor)

    def final_kontrol_item_git(self, item):
        self._preflight_item_git(item)
