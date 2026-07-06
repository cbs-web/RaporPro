# Dosya: RaporPro/arayuz_ozet.py
import tkinter as tk
from tkinter import ttk

from sabitler import *


class ArayuzOzetMixin:
    def p_ozet(self, p):
        outer = ttk.Frame(p, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="Proje Özeti", font=("Segoe UI", 13, "bold")).pack(side="left")
        self.modern_button(top, text="Yenile", command=self.ozet_yenile, role="secondary", outline=True).pack(side="right")

        hero = ttk.Frame(outer)
        hero.pack(fill="x", pady=(0, 6))
        hero.columnconfigure(0, weight=2)
        hero.columnconfigure(1, weight=1)

        dashboard = tk.Frame(hero, bg="#FFFFFF", bd=1, relief="solid", padx=10, pady=7)
        dashboard.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        dashboard.columnconfigure(0, weight=1)
        dashboard.columnconfigure(1, weight=0)
        tk.Label(
            dashboard,
            text="Bugünkü Durum",
            bg="#FFFFFF",
            fg=COLOR_PRIMARY,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        status_row = tk.Frame(dashboard, bg="#FFFFFF")
        status_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        status_row.columnconfigure(0, weight=1)
        status_row.columnconfigure(1, weight=0)
        self.final_dashboard_status_label = tk.Label(
            status_row,
            text="Proje durumu hazırlanıyor...",
            bg="#FFFFFF",
            fg="#333333",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
            justify="left",
        )
        self.final_dashboard_status_label.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        score_box = tk.Frame(status_row, bg="#F8FAFC", bd=1, relief="solid", padx=9, pady=4)
        score_box.grid(row=0, column=1, sticky="ne")
        tk.Label(score_box, text="Hazırlık", bg="#F8FAFC", fg="#555555", font=("Segoe UI", 7, "bold")).pack(anchor="e")
        self.ozet_score_label = tk.Label(
            score_box,
            text="%0",
            bg="#F8FAFC",
            fg=COLOR_DANGER,
            font=("Segoe UI", 14, "bold"),
            anchor="e",
        )
        self.ozet_score_label.pack(anchor="e")
        self.ozet_score_progress = ttk.Progressbar(dashboard, orient="horizontal", mode="determinate", maximum=100)
        self.ozet_score_progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self.ozet_counts_label = tk.Label(
            dashboard,
            text="Eksik: - | Uyarı: - | Hata: -",
            bg="#FFFFFF",
            fg="#555555",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self.ozet_counts_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self.final_dashboard_detail_label = tk.Label(
            dashboard,
            text="Final kontrol, veri sağlığı ve ön kontrol sonuçları burada özetlenir.",
            bg="#FFFFFF",
            fg="#555555",
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.final_dashboard_detail_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self.ozet_missing_labels = []
        missing_frame = ttk.Frame(dashboard)
        missing_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        for idx in range(1):
            lbl = tk.Label(missing_frame, text="-", bg="#FFFFFF", fg="#555555", anchor="w", justify="left", font=("Segoe UI", 8))
            lbl.pack(fill="x", pady=0)
            self.ozet_missing_labels.append(lbl)
        dashboard.bind(
            "<Configure>",
            lambda event: self.final_dashboard_detail_label.config(wraplength=max(260, event.width - 40)),
        )

        next_card = tk.Frame(hero, bg="#FFFFFF", bd=1, relief="solid", padx=10, pady=7)
        next_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        next_card.columnconfigure(0, weight=1)
        tk.Label(next_card, text="Sıradaki İş", bg="#FFFFFF", fg=COLOR_PRIMARY, font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        self.ozet_next_action_label = tk.Label(
            next_card,
            text="Proje durumu hesaplanıyor...",
            bg="#FFFFFF",
            fg="#333333",
            font=("Segoe UI", 9, "bold"),
            anchor="nw",
            justify="left",
            wraplength=300,
        )
        self.ozet_next_action_label.grid(row=1, column=0, sticky="nsew", pady=(5, 5))
        self.ozet_next_action_button = self.modern_button(
            next_card,
            text="Final Kontrol",
            command=self.final_kontrol_penceresi,
            role="warning",
            pady=2,
        )
        self.ozet_next_action_button.grid(row=2, column=0, sticky="ew")
        self.workflow_widgets = {}

        hero_layout_state = {"mode": None}

        def layout_hero(event=None):
            width = hero.winfo_width()
            if width <= 1 and event is not None:
                width = event.width
            mode = "stack" if width and width < 900 else "split"
            if hero_layout_state["mode"] == mode:
                return
            hero_layout_state["mode"] = mode
            dashboard.grid_forget()
            next_card.grid_forget()
            if mode == "stack":
                hero.columnconfigure(0, weight=1)
                hero.columnconfigure(1, weight=0)
                dashboard.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 8))
                next_card.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
            else:
                hero.columnconfigure(0, weight=2)
                hero.columnconfigure(1, weight=1)
                dashboard.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
                next_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)

        hero.bind("<Configure>", layout_hero)
        self.root.after_idle(layout_hero)

        quick = ttk.LabelFrame(outer, text="Kısa Yollar", padding=7)
        quick.pack(fill="x", pady=(0, 6))
        quick_buttons = ttk.Frame(quick)
        quick_buttons.pack(fill="x")
        self.responsive_button_row(quick_buttons, [
            ("Workbook", self.veri_giris_workbook_tksheet_ac, "#D6EAF8"),
            ("SPT Merkezi", self.spt_okuma_merkezi_ac, "#A3E4D7"),
            ("Kesit", self.kesit_secim_penceresi, "#E8DAEF"),
            ("Haritalar", lambda: self._workflow_git("haritalar"), "#D6EAF8"),
            ("Final Kontrol", self.final_kontrol_penceresi, "#F5B7B1"),
            ("Rapor Oluştur", self.raporla, COLOR_SUCCESS),
        ], min_width=155, max_cols=6, pady=2)

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body_layout_state = {"mode": None}

        def layout_summary_body(event=None):
            width = body.winfo_width()
            if width <= 1 and event is not None:
                width = event.width
            mode = "stack" if width and width < 980 else "split"
            if body_layout_state["mode"] == mode:
                return
            body_layout_state["mode"] = mode
            for child in (left, right):
                child.grid_forget()
            if mode == "stack":
                body.columnconfigure(0, weight=1)
                body.columnconfigure(1, weight=0)
                left.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
                right.grid(row=1, column=0, sticky="nsew")
            else:
                body.columnconfigure(0, weight=4)
                body.columnconfigure(1, weight=1)
                left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
                right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
            body.rowconfigure(0, weight=1)
            body.rowconfigure(1, weight=1 if mode == "stack" else 0)

        body.bind("<Configure>", layout_summary_body)
        self.root.after_idle(layout_summary_body)

        left.rowconfigure(0, weight=1)
        left.rowconfigure(1, weight=0)
        left.columnconfigure(0, weight=1)

        left_top = ttk.Frame(left)
        left_top.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        left_top.columnconfigure(0, weight=4)
        left_top.columnconfigure(1, weight=2)
        left_top.rowconfigure(0, weight=1)

        self.ozet_metric_labels = {}
        self.ozet_metric_cards = {}
        self.ozet_metric_title_labels = {}
        metrics_frame = ttk.LabelFrame(left_top, text="Veri Durumu", padding=12)
        metrics_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        metrics = [
            ("proje", "Proje"),
            ("konum", "Konum"),
            ("sondaj", "Sondaj"),
            ("litoloji", "Litoloji"),
            ("deney", "Arazi deneyleri"),
            ("jeofizik", "Jeofizik"),
            ("harita", "Harita/görsel"),
        ]
        metric_cols = 4
        for col in range(metric_cols):
            metrics_frame.columnconfigure(col, weight=1, uniform="summary_metric")
        for row in range(2):
            metrics_frame.rowconfigure(row, weight=1, uniform="summary_metric_row")
        for idx, (key, label) in enumerate(metrics):
            row = idx // metric_cols
            col = idx % metric_cols
            card = tk.Frame(metrics_frame, bg="#FFFFFF", bd=1, relief="solid", padx=8, pady=5)
            card.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            card.columnconfigure(0, weight=1)
            card.rowconfigure(1, weight=1)
            title = tk.Label(card, text=label, bg="#FFFFFF", fg=COLOR_PRIMARY, font=("Segoe UI", 8, "bold"), anchor="w")
            title.grid(row=0, column=0, sticky="ew")
            value = tk.Label(
                card,
                text="-",
                bg="#FFFFFF",
                fg="#333333",
                anchor="nw",
                justify="left",
                font=("Segoe UI", 8),
                wraplength=210,
            )
            value.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
            self.ozet_metric_cards[key] = card
            self.ozet_metric_title_labels[key] = title
            self.ozet_metric_labels[key] = value

        health_frame = ttk.LabelFrame(left_top, text="Proje Sağlığı", padding=8)
        health_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.health_status_label = tk.Label(health_frame, text="-", bg=COLOR_BG, fg="#333333", font=("Segoe UI", 10, "bold"), anchor="w")
        self.health_status_label.pack(fill="x")
        health_text_wrap = ttk.Frame(health_frame)
        health_text_wrap.pack(fill="both", expand=True, pady=(5, 0))
        self.health_detail_text = tk.Text(health_text_wrap, height=7, wrap="word", font=("Consolas", 8), bg="#FAFAFA")
        health_scroll = ttk.Scrollbar(health_text_wrap, orient="vertical", command=self.health_detail_text.yview)
        self.health_detail_text.configure(yscrollcommand=health_scroll.set)
        self.health_detail_text.pack(side="left", fill="both", expand=True)
        health_scroll.pack(side="right", fill="y")
        self.health_detail_text.config(state="disabled")
        self.health_tag_actions = {}
        self.health_detail_text.bind("<Button-1>", self._health_detail_click)
        self.health_detail_text.bind("<Motion>", self._health_detail_motion)

        self.ozet_file_labels = {}
        self.ozet_file_cards = {}
        self.ozet_file_title_labels = {}
        files_frame = ttk.LabelFrame(left, text="Dosya Bağlantıları", padding=6)
        files_frame.grid(row=1, column=0, sticky="ew")
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
        file_cols = 5
        for col in range(file_cols):
            files_frame.columnconfigure(col, weight=1, uniform="summary_file")
        for idx, (key, label) in enumerate(files):
            row = idx // file_cols
            col = idx % file_cols
            card = tk.Frame(files_frame, bg="#FFFFFF", bd=1, relief="solid", padx=7, pady=4)
            card.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            card.columnconfigure(0, weight=1)
            title = tk.Label(card, text=label, bg="#FFFFFF", fg=COLOR_PRIMARY, font=("Segoe UI", 8, "bold"), anchor="w")
            title.grid(row=0, column=0, sticky="ew")
            value = tk.Label(
                card,
                text="-",
                bg="#FFFFFF",
                fg="#333333",
                anchor="nw",
                justify="left",
                font=("Segoe UI", 7),
                height=2,
                wraplength=185,
            )
            value.grid(row=1, column=0, sticky="nsew", pady=(1, 0))
            self.ozet_file_cards[key] = card
            self.ozet_file_title_labels[key] = title
            self.ozet_file_labels[key] = value

        preflight_frame = ttk.LabelFrame(right, text="Son Ön Kontrol", padding=8)
        preflight_frame.pack(fill="both", expand=True)
        preflight_top = ttk.Frame(preflight_frame)
        preflight_top.pack(fill="x", pady=(0, 6))
        self.ozet_preflight_summary_label = tk.Label(
            preflight_top,
            text="Ön kontrol bekliyor",
            bg=COLOR_BG,
            fg="#555555",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.ozet_preflight_summary_label.pack(side="left", fill="x", expand=True)
        self.ozet_preflight_action_button = self.modern_button(
            preflight_top,
            text="Çalıştır",
            command=self.ozet_on_kontrol,
            role="warning",
            outline=True,
        )
        self.ozet_preflight_action_button.pack(side="right", padx=(6, 0))
        self.ozet_preflight_text = tk.Text(preflight_frame, wrap="word", font=("Consolas", 8), height=6, width=38, bg="#FAFAFA")
        preflight_scroll = ttk.Scrollbar(preflight_frame, orient="vertical", command=self.ozet_preflight_text.yview)
        self.ozet_preflight_text.configure(yscrollcommand=preflight_scroll.set)
        self.ozet_preflight_text.pack(side="left", fill="both", expand=True)
        preflight_scroll.pack(side="right", fill="y")
        self.ozet_preflight_text.insert("1.0", "Ön kontrol henüz çalıştırılmadı.")
        self.ozet_preflight_text.config(state="disabled")

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
            action = "Final Kontrol ile kalan uyarıları temizlemek iyi olur."
        else:
            title = "Veri girişi tamamlandıkça proje hazır hale gelecek"
            color = COLOR_DANGER
            action = "İş Akışı kartları sıradaki eksik alana götürür."

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
                    label.config(text="", fg="#555555")

        if hasattr(self, "ozet_next_action_label") and hasattr(self, "ozet_next_action_button"):
            missing_items = [item for item in health.get("items", []) if not item.get("ok")]
            if error_count:
                next_text = f"Ön kontrolde {error_count} hata var. Önce hatalı maddeleri temizleyelim."
                btn_text = "Hataları Aç"
                btn_color = COLOR_DANGER
                btn_command = self.final_kontrol_penceresi
            elif missing_items:
                first = missing_items[0]
                suggestion = first.get("suggestion") or first.get("detail") or "Eksik bilgiyi tamamlayın."
                next_text = f"{first.get('label')}: {suggestion}"
                btn_text = "İlgili Sekmeye Git"
                btn_color = COLOR_WARNING
                btn_command = lambda target=first.get("target", "ozet"): self._workflow_git(target)
            elif warning_count:
                next_text = f"Ön kontrolde {warning_count} uyarı var. Son kontrolü açıp karar verelim."
                btn_text = "Final Kontrol"
                btn_color = COLOR_WARNING
                btn_command = self.final_kontrol_penceresi
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
