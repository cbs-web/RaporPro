# Dosya: RaporPro/arayuz_ozet.py
import tkinter as tk
from tkinter import ttk

from sabitler import *


class ArayuzOzetMixin:
    def p_ozet(self, p):
        outer, self.ozet_scroll_canvas = self.scrollable_page(p, padding=SPACE_MD)
        self.ozet_content_frame = outer

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, SPACE_SM))
        ttk.Label(top, text="Proje Özeti", style="PageTitle.TLabel").pack(side="left")
        self.modern_button(
            top,
            text="Yenile",
            command=self.ozet_yenile,
            role="secondary",
            outline=True,
            padx=10,
            pady=4,
        ).pack(side="right")

        hero = ttk.Frame(outer)
        self.ozet_hero_frame = hero
        hero.pack(fill="x", pady=(0, SPACE_MD))

        dashboard = self.ui_surface_frame(hero, padding=SPACE_MD)
        self.ozet_dashboard_card = dashboard
        dashboard.columnconfigure(0, weight=1)
        tk.Label(
            dashboard,
            text="Bugünkü Durum",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_BODY_BOLD,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        score_box = tk.Frame(
            dashboard,
            bg=COLOR_SURFACE_ALT,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=8,
            pady=3,
        )
        score_box.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(SPACE_MD, 0))
        tk.Label(score_box, text="Hazırlık", bg=COLOR_SURFACE_ALT, fg=COLOR_TEXT_MUTED, font=FONT_UI_SMALL).pack(anchor="e")
        self.ozet_score_label = tk.Label(
            score_box,
            text="%0",
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_DANGER,
            font=("Segoe UI", 15, "bold"),
            anchor="e",
        )
        self.ozet_score_label.pack(anchor="e")
        self.final_dashboard_status_label = tk.Label(
            dashboard,
            text="Proje durumu hazırlanıyor...",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            justify="left",
        )
        self.final_dashboard_status_label.grid(row=1, column=0, sticky="ew", pady=(SPACE_SM, 0))
        self.ozet_score_progress = ttk.Progressbar(
            dashboard,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            style="Dashboard.Horizontal.TProgressbar",
        )
        self.ozet_score_progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(SPACE_SM, 0))
        self.ozet_counts_label = tk.Label(
            dashboard,
            text="Eksik: - | Uyarı: - | Hata: -",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY_BOLD,
            anchor="w",
        )
        self.ozet_counts_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(SPACE_SM, 0))
        self.final_dashboard_detail_label = tk.Label(
            dashboard,
            text="Final kontrol, veri sağlığı ve ön kontrol sonuçları burada özetlenir.",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.final_dashboard_detail_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(SPACE_XS, 0))
        self.ozet_missing_labels = []
        missing_frame = tk.Frame(dashboard, bg=COLOR_SURFACE)
        missing_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(SPACE_XS, 0))
        missing_label = tk.Label(
            missing_frame,
            text="-",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            anchor="w",
            justify="left",
            font=FONT_UI_BODY,
        )
        missing_label.pack(fill="x")
        self.ozet_missing_labels.append(missing_label)
        dashboard.bind(
            "<Configure>",
            lambda event: self.final_dashboard_detail_label.config(wraplength=max(220, event.width - 36)),
        )

        next_card = self.ui_surface_frame(hero, padding=SPACE_MD)
        self.ozet_next_card = next_card
        next_card.columnconfigure(0, weight=1)
        tk.Label(
            next_card,
            text="Sıradaki İş",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_BODY_BOLD,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.ozet_next_action_label = tk.Label(
            next_card,
            text="Proje durumu hesaplanıyor...",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=FONT_UI_BODY_BOLD,
            anchor="nw",
            justify="left",
            wraplength=300,
        )
        self.ozet_next_action_label.grid(row=1, column=0, sticky="nsew", pady=(SPACE_SM, SPACE_MD))
        self.ozet_next_action_button = self.modern_button(
            next_card,
            text="Tamamlama Merkezi",
            command=self.tamamlama_merkezi_penceresi,
            role="warning",
            pady=4,
        )
        self.ozet_next_action_button.grid(row=2, column=0, sticky="ew")
        next_card.bind(
            "<Configure>",
            lambda event: self.ozet_next_action_label.config(wraplength=max(180, event.width - 36)),
        )
        self.workflow_widgets = {}

        hero_layout_state = {"mode": None}

        def layout_hero(event=None):
            width = event.width if event is not None else hero.winfo_width()
            mode = "stack" if width and width < 1050 else "split"
            if hero_layout_state["mode"] == mode:
                return
            hero_layout_state["mode"] = mode
            dashboard.grid_forget()
            next_card.grid_forget()
            for col in range(2):
                hero.columnconfigure(col, weight=0)
            if mode == "stack":
                hero.columnconfigure(0, weight=1)
                dashboard.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
                next_card.grid(row=1, column=0, sticky="ew")
            else:
                hero.columnconfigure(0, weight=5)
                hero.columnconfigure(1, weight=2)
                dashboard.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_SM))
                next_card.grid(row=0, column=1, sticky="nsew", padx=(SPACE_SM, 0))

        hero.bind("<Configure>", layout_hero)
        self.root.after_idle(layout_hero)

        quick = ttk.Frame(outer)
        quick.pack(fill="x", pady=(0, SPACE_MD))
        self.ui_section_title(quick, "Kısa Yollar").pack(anchor="w", pady=(0, SPACE_XS))
        quick_buttons = ttk.Frame(quick)
        self.ozet_quick_buttons_frame = quick_buttons
        quick_buttons.pack(fill="x")
        quick_specs = [
            ("Workbook", self.veri_giris_workbook_tksheet_ac, "accent"),
            ("SPT Merkezi", self.spt_okuma_merkezi_ac, "secondary"),
            ("Kesit", self.kesit_secim_penceresi, "secondary"),
            ("Haritalar", lambda: self._workflow_git("haritalar"), "accent"),
            ("Tamamlama Merkezi", self.tamamlama_merkezi_penceresi, "warning"),
        ]
        quick_widgets = [
            self.modern_button(
                quick_buttons,
                text=text,
                command=command,
                role=role,
                outline=True,
                padx=10,
                pady=5,
            )
            for text, command, role in quick_specs
        ]
        self.responsive_widget_grid(quick_buttons, quick_widgets, min_width=165, max_cols=5, padx=4, pady=2)

        summary_grid = ttk.Frame(outer)
        self.ozet_summary_grid = summary_grid
        summary_grid.pack(fill="both", expand=True, pady=(0, SPACE_MD))

        metrics_section = ttk.Frame(summary_grid)
        self.ozet_metrics_section = metrics_section
        self.ui_section_title(metrics_section, "Veri Durumu").pack(anchor="w", pady=(0, SPACE_XS))
        metrics_frame = ttk.Frame(metrics_section)
        metrics_frame.pack(fill="both", expand=True)
        self.ozet_metric_labels = {}
        self.ozet_metric_cards = {}
        self.ozet_metric_title_labels = {}
        self.ozet_metric_accents = {}
        metrics = [
            ("proje", "Proje"),
            ("konum", "Konum"),
            ("sondaj", "Sondaj"),
            ("litoloji", "Litoloji"),
            ("deney", "Arazi deneyleri"),
            ("jeofizik", "Jeofizik"),
            ("harita", "Harita/görsel"),
        ]
        metric_widgets = []
        for key, label in metrics:
            card = tk.Frame(
                metrics_frame,
                bg=COLOR_SURFACE,
                bd=0,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
            )
            card.columnconfigure(1, weight=1)
            accent = tk.Frame(card, bg=COLOR_TEXT_MUTED, width=4)
            accent.grid(row=0, column=0, sticky="ns")
            accent.grid_propagate(False)
            content = tk.Frame(card, bg=COLOR_SURFACE, padx=SPACE_SM, pady=SPACE_SM)
            content.grid(row=0, column=1, sticky="nsew")
            content.columnconfigure(0, weight=1)
            title = tk.Label(content, text=label, bg=COLOR_SURFACE, fg=COLOR_PRIMARY, font=FONT_UI_BODY_BOLD, anchor="w")
            title.grid(row=0, column=0, sticky="ew")
            value = tk.Label(
                content,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT,
                anchor="nw",
                justify="left",
                font=FONT_UI_BODY,
                wraplength=220,
            )
            value.grid(row=1, column=0, sticky="nsew", pady=(SPACE_XS, 0))
            card.bind("<Configure>", lambda event, target=value: target.config(wraplength=max(110, event.width - 28)))
            self.ozet_metric_cards[key] = card
            self.ozet_metric_title_labels[key] = title
            self.ozet_metric_labels[key] = value
            self.ozet_metric_accents[key] = accent
            metric_widgets.append(card)
        self.responsive_widget_grid(metrics_frame, metric_widgets, min_width=205, max_cols=3, padx=4, pady=4)

        health_frame = self.ui_surface_frame(summary_grid, padding=SPACE_SM)
        self.ozet_health_frame = health_frame
        health_header = tk.Frame(health_frame, bg=COLOR_SURFACE)
        health_header.pack(fill="x", pady=(0, SPACE_SM))
        tk.Label(
            health_header,
            text="Proje Sağlığı",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
            anchor="w",
        ).pack(side="left")
        self.health_status_label = tk.Label(
            health_header,
            text="-",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=FONT_UI_BODY_BOLD,
            anchor="e",
        )
        self.health_status_label.pack(side="right")
        health_text_wrap = tk.Frame(health_frame, bg=COLOR_SURFACE)
        health_text_wrap.pack(fill="both", expand=True)
        self.health_detail_text = tk.Text(
            health_text_wrap,
            height=11,
            width=38,
            wrap="word",
            font=FONT_UI_BODY,
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=8,
            pady=6,
        )
        health_scroll = ttk.Scrollbar(health_text_wrap, orient="vertical", command=self.health_detail_text.yview)
        self.health_detail_text.configure(yscrollcommand=health_scroll.set)
        self.health_detail_text.pack(side="left", fill="both", expand=True)
        health_scroll.pack(side="right", fill="y")
        self.health_detail_text.config(state="disabled")
        self.health_tag_actions = {}
        self.health_detail_text.bind("<Button-1>", self._health_detail_click)
        self.health_detail_text.bind("<Motion>", self._health_detail_motion)

        preflight_frame = self.ui_surface_frame(summary_grid, padding=SPACE_SM)
        self.ozet_preflight_frame = preflight_frame
        preflight_top = tk.Frame(preflight_frame, bg=COLOR_SURFACE)
        preflight_top.pack(fill="x", pady=(0, SPACE_SM))
        preflight_heading = tk.Frame(preflight_top, bg=COLOR_SURFACE)
        preflight_heading.pack(side="left", fill="x", expand=True)
        tk.Label(
            preflight_heading,
            text="Son Ön Kontrol",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
            anchor="w",
        ).pack(anchor="w")
        self.ozet_preflight_summary_label = tk.Label(
            preflight_heading,
            text="Ön kontrol bekliyor",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY_BOLD,
            anchor="w",
        )
        self.ozet_preflight_summary_label.pack(anchor="w", pady=(2, 0))
        self.ozet_preflight_action_button = self.modern_button(
            preflight_top,
            text="Çalıştır",
            command=self.ozet_on_kontrol,
            role="warning",
            outline=True,
            padx=8,
            pady=4,
        )
        self.ozet_preflight_action_button.pack(side="right", padx=(SPACE_SM, 0))
        preflight_text_wrap = tk.Frame(preflight_frame, bg=COLOR_SURFACE)
        preflight_text_wrap.pack(fill="both", expand=True)
        self.ozet_preflight_text = tk.Text(
            preflight_text_wrap,
            wrap="word",
            font=FONT_UI_BODY,
            height=11,
            width=32,
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=8,
            pady=6,
        )
        preflight_scroll = ttk.Scrollbar(preflight_text_wrap, orient="vertical", command=self.ozet_preflight_text.yview)
        self.ozet_preflight_text.configure(yscrollcommand=preflight_scroll.set)
        self.ozet_preflight_text.pack(side="left", fill="both", expand=True)
        preflight_scroll.pack(side="right", fill="y")
        self.ozet_preflight_text.insert("1.0", "Ön kontrol henüz çalıştırılmadı.")
        self.ozet_preflight_text.config(state="disabled")

        summary_layout_state = {"mode": None}

        def layout_summary(event=None):
            width = event.width if event is not None else summary_grid.winfo_width()
            mode = "stack" if width and width < 820 else ("two" if width < 1250 else "three")
            if summary_layout_state["mode"] == mode:
                return
            summary_layout_state["mode"] = mode
            for child in (metrics_section, health_frame, preflight_frame):
                child.grid_forget()
            for col in range(3):
                summary_grid.columnconfigure(col, weight=0)
            if mode == "stack":
                summary_grid.columnconfigure(0, weight=1)
                metrics_section.grid(row=0, column=0, sticky="nsew", pady=(0, SPACE_SM))
                health_frame.grid(row=1, column=0, sticky="nsew", pady=SPACE_SM)
                preflight_frame.grid(row=2, column=0, sticky="nsew", pady=(SPACE_SM, 0))
            elif mode == "two":
                summary_grid.columnconfigure(0, weight=3)
                summary_grid.columnconfigure(1, weight=2)
                metrics_section.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_SM), pady=(0, SPACE_SM))
                health_frame.grid(row=0, column=1, sticky="nsew", padx=(SPACE_SM, 0), pady=(0, SPACE_SM))
                preflight_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(SPACE_SM, 0))
            else:
                summary_grid.columnconfigure(0, weight=5)
                summary_grid.columnconfigure(1, weight=4)
                summary_grid.columnconfigure(2, weight=3)
                metrics_section.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_SM))
                health_frame.grid(row=0, column=1, sticky="nsew", padx=SPACE_SM)
                preflight_frame.grid(row=0, column=2, sticky="nsew", padx=(SPACE_SM, 0))

        summary_grid.bind("<Configure>", layout_summary)
        self.root.after_idle(layout_summary)

        files_section = ttk.Frame(outer)
        files_section.pack(fill="x")
        self.ui_section_title(files_section, "Dosya Bağlantıları").pack(anchor="w", pady=(0, SPACE_XS))
        files_frame = ttk.Frame(files_section)
        self.ozet_files_frame = files_frame
        files_frame.pack(fill="x")
        self.ozet_file_labels = {}
        self.ozet_file_cards = {}
        self.ozet_file_title_labels = {}
        self.ozet_file_accents = {}
        files = [
            ("word", "Word şablonu"),
            ("lab", "Lab Excel"),
            ("jeo", "Jeofizik Excel"),
            ("kml", "KML sınır"),
            ("yer", "Yerbuldurur"),
            ("tkgm", "TKGM"),
            ("pga", "PGA"),
            ("mjh", "MJH"),
            ("sondaj_img", "Sondaj haritası"),
            ("jeo_img", "Jeofizik haritası"),
        ]
        file_widgets = []
        for key, label in files:
            card = tk.Frame(
                files_frame,
                bg=COLOR_SURFACE,
                bd=0,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
            )
            card.columnconfigure(1, weight=1)
            accent = tk.Frame(card, bg=COLOR_TEXT_MUTED, width=4)
            accent.grid(row=0, column=0, sticky="ns")
            accent.grid_propagate(False)
            content = tk.Frame(card, bg=COLOR_SURFACE, padx=SPACE_SM, pady=SPACE_SM)
            content.grid(row=0, column=1, sticky="nsew")
            content.columnconfigure(0, weight=1)
            title = tk.Label(content, text=label, bg=COLOR_SURFACE, fg=COLOR_PRIMARY, font=FONT_UI_BODY_BOLD, anchor="w")
            title.grid(row=0, column=0, sticky="ew")
            value = tk.Label(
                content,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT,
                anchor="nw",
                justify="left",
                font=FONT_UI_SMALL,
                wraplength=210,
            )
            value.grid(row=1, column=0, sticky="nsew", pady=(SPACE_XS, 0))
            card.bind("<Configure>", lambda event, target=value: target.config(wraplength=max(110, event.width - 28)))
            self.ozet_file_cards[key] = card
            self.ozet_file_title_labels[key] = title
            self.ozet_file_labels[key] = value
            self.ozet_file_accents[key] = accent
            file_widgets.append(card)
        self.responsive_widget_grid(files_frame, file_widgets, min_width=205, max_cols=5, padx=4, pady=4)

    def ozet_rapora_git(self):
        if hasattr(self, "nb") and hasattr(self, "tab_rapor"):
            self.nb.select(self.tab_rapor)

    def _workflow_git(self, target):
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
            self.set_status(f"{target} sekmesine gidildi.", level="info")

    def _workflow_set(self, key, text, level):
        widget = getattr(self, "workflow_widgets", {}).get(key, {}).get("status")
        if not widget:
            return
        colors = {"ok": COLOR_SUCCESS, "warn": COLOR_WARNING, "bad": COLOR_DANGER, "info": "#333333"}
        widget.config(text=text, fg=colors.get(level, "#333333"))

    def _workflow_paneli_guncelle(self, health):
        if not hasattr(self, "workflow_widgets"):
            return
        items = {item.get("label"): item for item in health.get("items", [])}
        def ok(label):
            return bool(items.get(label, {}).get("ok"))

        project_ok = ok("Proje bilgisi")
        data_ok = ok("Sondaj kaydı") and ok("Litoloji") and ok("Arazi deneyleri")
        control_ok = health.get("score", 0) >= 85 and not (self.last_preflight_report or {}).get("errors")
        control_warn = health.get("score", 0) >= 60
        visual_ok = ok("Sondaj koordinatları") and bool(self.veri.get("kesit_ayarlari", {}).get("selected_sondajlar") or self.veri.get("sondaj"))
        report_ok = ok("Word şablonu") and control_warn

        self._workflow_set("project", "TAMAM" if project_ok else "EKSİK", "ok" if project_ok else "bad")
        self._workflow_set("data", "TAMAM" if data_ok else "VERİ GEREKLİ", "ok" if data_ok else "warn")
        self._workflow_set("control", "TAMAM" if control_ok else ("UYARI VAR" if control_warn else "KONTROL GEREKLİ"), "ok" if control_ok else "warn")
        self._workflow_set("visual", "HAZIR" if visual_ok else "KOORDİNAT/KESİT GEREKLİ", "ok" if visual_ok else "warn")
        self._workflow_set("report", "RAPORA HAZIR" if report_ok else "ŞABLON/KONTROL GEREKLİ", "ok" if report_ok else "warn")

    def _final_dashboard_guncelle(self, health):
        if not hasattr(self, "final_dashboard_status_label"):
            return
        score = health.get("score", 0)
        preflight = self.last_preflight_report or {}
        error_count = len(preflight.get("errors", []) or [])
        warning_count = len(preflight.get("warnings", []) or [])
        missing = [item.get("label", "") for item in health.get("items", []) if not item.get("ok")]
        try:
            score_value = max(0, min(100, int(score)))
        except Exception:
            score_value = 0
        if hasattr(self, "ozet_score_label"):
            self.ozet_score_label.config(text=f"%{score_value}", fg=COLOR_SUCCESS if score_value >= 85 else (COLOR_WARNING if score_value >= 60 else COLOR_DANGER))
        if hasattr(self, "ozet_score_progress"):
            self.ozet_score_progress["value"] = score_value
            if score_value >= 85:
                self.ozet_score_progress.configure(style="Success.Horizontal.TProgressbar")
            elif score_value >= 60:
                self.ozet_score_progress.configure(style="Warning.Horizontal.TProgressbar")
            else:
                self.ozet_score_progress.configure(style="Danger.Horizontal.TProgressbar")
        if hasattr(self, "ozet_counts_label"):
            self.ozet_counts_label.config(
                text=f"Eksik: {len(missing)} | Uyarı: {warning_count} | Hata: {error_count}",
                fg=COLOR_DANGER if error_count else (COLOR_WARNING if warning_count or missing else COLOR_SUCCESS),
            )
        if error_count:
            title = f"Rapor ön kontrolünde {error_count} hata var"
            color = COLOR_DANGER
            action = "Eksikleri Göster ile hata satırlarına gidebilirsiniz."
        elif score >= 85 and warning_count == 0:
            title = "Proje rapor almaya hazır görünüyor"
            color = COLOR_SUCCESS
            action = "Raporu Oluştur veya Çıktı Merkezi ile son çıktıları alabilirsiniz."
        elif score >= 60:
            title = "Proje iyi durumda, son kontroller gerekiyor"
            color = COLOR_WARNING
            action = "Tamamlama Merkezi ile kalan uyarıları temizlemek iyi olur."
        else:
            title = "Veri girişi tamamlandıkça proje hazır hale gelecek"
            color = COLOR_DANGER
            action = "Sıradaki iş alanı ilk tamamlanması gereken bölüme götürür."

        details = [f"Proje sağlığı: %{score}"]
        if warning_count:
            details.append(f"Ön kontrol uyarısı: {warning_count}")
        if missing:
            details.append("Eksik görünenler: " + ", ".join(missing[:4]))
            if len(missing) > 4:
                details[-1] += f" ve {len(missing) - 4} kalem daha"
        details.append(action)
        self.final_dashboard_status_label.config(text=title, fg=color)
        self.final_dashboard_detail_label.config(text=" | ".join(details))

        if hasattr(self, "ozet_missing_labels"):
            missing_items = [item for item in health.get("items", []) if not item.get("ok")]
            for idx, label in enumerate(self.ozet_missing_labels):
                if idx < len(missing_items):
                    item = missing_items[idx]
                    text = f"- {item.get('label')}: {item.get('detail')}"
                    label.config(text=text, fg=COLOR_DANGER)
                elif idx == 0:
                    label.config(text="- Kritik eksik görünmüyor.", fg=COLOR_SUCCESS)
                else:
                    label.config(text="", fg=COLOR_TEXT_MUTED)

        if hasattr(self, "ozet_next_action_label") and hasattr(self, "ozet_next_action_button"):
            missing_items = [item for item in health.get("items", []) if not item.get("ok")]
            if error_count:
                next_text = f"Ön kontrolde {error_count} hata var. Önce hatalı maddeleri temizleyelim."
                btn_text = "Hataları Aç"
                btn_color = COLOR_DANGER
                btn_command = self.tamamlama_merkezi_penceresi
            elif missing_items:
                first = missing_items[0]
                suggestion = first.get("suggestion") or first.get("detail") or "Eksik bilgiyi tamamlayın."
                next_text = f"{first.get('label')}: {suggestion}"
                btn_text = "İlgili Sekmeye Git"
                btn_color = COLOR_WARNING
                btn_command = lambda target=first.get("target", "ozet"): self._workflow_git(target)
            elif warning_count:
                next_text = f"Ön kontrolde {warning_count} uyarı var. Son kontrolü açıp karar verelim."
                btn_text = "Tamamlama Merkezi"
                btn_color = COLOR_WARNING
                btn_command = self.tamamlama_merkezi_penceresi
            else:
                next_text = "Eksik görünmüyor. Raporu oluşturabilir veya çıktı merkezinden son dosyaları toplayabilirsiniz."
                btn_text = "Raporu Oluştur"
                btn_color = COLOR_SUCCESS
                btn_command = self.raporla
            self.ozet_next_action_label.config(text=next_text, fg=btn_color)
            self.configure_modern_button(
                self.ozet_next_action_button,
                text=btn_text,
                command=btn_command,
                role=self._role_from_color(btn_color),
            )
