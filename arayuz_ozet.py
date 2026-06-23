# Dosya: RaporPro/arayuz_ozet.py
import tkinter as tk
from tkinter import ttk

from sabitler import *


class ArayuzOzetMixin:
    def p_ozet(self, p):
        outer = ttk.Frame(p, padding=14)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Proje Özeti", font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Button(top, text="Yenile", command=self.ozet_yenile, bg="#ECF0F1", fg="#111", relief="flat").pack(side="right")

        hero = ttk.Frame(outer)
        hero.pack(fill="x", pady=(0, 10))
        hero.columnconfigure(0, weight=2)
        hero.columnconfigure(1, weight=1)

        dashboard = tk.Frame(hero, bg="#FFFFFF", bd=1, relief="solid", padx=14, pady=12)
        dashboard.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        dashboard.columnconfigure(0, weight=1)
        tk.Label(
            dashboard,
            text="Bugünkü Durum",
            bg="#FFFFFF",
            fg=COLOR_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.final_dashboard_status_label = tk.Label(
            dashboard,
            text="Proje durumu hazırlanıyor...",
            bg="#FFFFFF",
            fg="#333333",
            font=("Segoe UI", 17, "bold"),
            anchor="w",
        )
        self.final_dashboard_status_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.final_dashboard_detail_label = tk.Label(
            dashboard,
            text="Final kontrol, veri sağlığı ve ön kontrol sonuçları burada özetlenir.",
            bg="#FFFFFF",
            fg="#555555",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.final_dashboard_detail_label.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.ozet_missing_labels = []
        missing_frame = ttk.Frame(dashboard)
        missing_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for idx in range(3):
            lbl = tk.Label(missing_frame, text="-", bg="#FFFFFF", fg="#555555", anchor="w", justify="left")
            lbl.pack(fill="x", pady=1)
            self.ozet_missing_labels.append(lbl)
        dashboard.bind(
            "<Configure>",
            lambda event: self.final_dashboard_detail_label.config(wraplength=max(260, event.width - 40)),
        )

        next_card = tk.Frame(hero, bg="#FFFFFF", bd=1, relief="solid", padx=14, pady=12)
        next_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        next_card.columnconfigure(0, weight=1)
        tk.Label(next_card, text="Sıradaki İş", bg="#FFFFFF", fg=COLOR_PRIMARY, font=("Segoe UI", 10, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        self.ozet_next_action_label = tk.Label(
            next_card,
            text="Proje durumu hesaplanıyor...",
            bg="#FFFFFF",
            fg="#333333",
            font=("Segoe UI", 11, "bold"),
            anchor="nw",
            justify="left",
            wraplength=300,
        )
        self.ozet_next_action_label.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        self.ozet_next_action_button = tk.Button(
            next_card,
            text="Final Kontrol",
            command=self.final_kontrol_penceresi,
            bg=COLOR_WARNING,
            fg="white",
            relief="flat",
            font=FONT_BOLD,
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

        quick = ttk.LabelFrame(outer, text="Kısa Yollar", padding=10)
        quick.pack(fill="x", pady=(0, 10))
        quick_buttons = ttk.Frame(quick)
        quick_buttons.pack(fill="x")
        self.responsive_button_row(quick_buttons, [
            ("Workbook", self.veri_giris_workbook_tksheet_ac, "#D6EAF8"),
            ("SPT Merkezi", self.spt_okuma_merkezi_ac, "#A3E4D7"),
            ("Kesit", self.kesit_secim_penceresi, "#E8DAEF"),
            ("Haritalar", lambda: self._workflow_git("haritalar"), "#D6EAF8"),
            ("Final Kontrol", self.final_kontrol_penceresi, "#F5B7B1"),
            ("Rapor Oluştur", self.raporla, COLOR_SUCCESS),
        ], min_width=155, max_cols=6)

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
                body.columnconfigure(0, weight=1)
                body.columnconfigure(1, weight=0)
                left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
                right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
            body.rowconfigure(0, weight=1)
            body.rowconfigure(1, weight=1 if mode == "stack" else 0)

        body.bind("<Configure>", layout_summary_body)
        self.root.after_idle(layout_summary_body)

        left_top = ttk.Frame(left)
        left_top.pack(fill="x", pady=(0, 10))
        left_top.columnconfigure(0, weight=3)
        left_top.columnconfigure(1, weight=2)

        self.ozet_metric_labels = {}
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
        for row, (key, label) in enumerate(metrics):
            ttk.Label(metrics_frame, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)
            value = tk.Label(metrics_frame, text="-", bg=COLOR_BG, fg="#333333", anchor="w", justify="left")
            value.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            self.ozet_metric_labels[key] = value
        metrics_frame.columnconfigure(1, weight=1)

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
        files_frame = ttk.LabelFrame(left, text="Dosya Bağlantıları", padding=6)
        files_frame.pack(fill="x", expand=False)
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
        for idx, (key, label) in enumerate(files):
            row = idx // 4
            base_col = (idx % 4) * 2
            ttk.Label(files_frame, text=label).grid(row=row, column=base_col, sticky="w", padx=(4, 3), pady=2)
            value = tk.Label(files_frame, text="-", bg=COLOR_BG, fg="#333333", anchor="w", justify="left", font=("Segoe UI", 8))
            value.grid(row=row, column=base_col + 1, sticky="ew", padx=(0, 8), pady=2)
            self.ozet_file_labels[key] = value
        files_frame.columnconfigure(1, weight=1)
        files_frame.columnconfigure(3, weight=1)
        files_frame.columnconfigure(5, weight=1)
        files_frame.columnconfigure(7, weight=1)

        preflight_frame = ttk.LabelFrame(right, text="Son Ön Kontrol", padding=8)
        preflight_frame.pack(fill="both", expand=True)
        self.ozet_preflight_text = tk.Text(preflight_frame, wrap="word", font=("Consolas", 8), height=8, width=46, bg="#FAFAFA")
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
            self.ozet_next_action_button.config(text=btn_text, bg=btn_color, fg="white", command=btn_command)

