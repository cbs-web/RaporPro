import copy
import datetime
import os
import shutil
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

import matplotlib.pyplot as plt

from cikti_kalite import cikti_dosyalari_denetle, kalite_manifestosu_yaz
from kalite_kontrol import build_preflight_report
from motor import GeoEngine
from performans import perf_tracked
from raporlama import raporla as rapor_olustur
from sabitler import (
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    FONT_UI_SECTION,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from taahhutname import tum_taahhutnameleri_olustur
from task_engine import TaskCancelledError
from tutanaklar import tutanak_dosya_adi, tutanaklari_olustur
from ekler import EK_SET_ARAZI_DENEYLI, EK_SET_NORMAL, ek_icerik_haritasi, ek_pdf_dosya_adi, ekler_pdf_olustur
from tutarlilik_ortak import koordinat_durumu, sayi_veya_none


CIKTI_GRUPLARI = (
    ("report", "00", "Ana Rapor", "Word raporu ve kalite manifestosu"),
    ("logs", "01", "Sondaj Logları", "Her sondaj için çok sayfalı log çıktıları"),
    ("section", "02", "Jeolojik Kesit", "Seçili sondajlardan güncel kesit çizimi"),
    ("maps", "03", "Lokasyon Haritaları", "Sondaj ve jeofizik lokasyon haritaları"),
    ("report_images", "04", "Rapor Görselleri", "Yerbuldurur, TKGM, PGA ve MJH görselleri"),
    ("taahhutnameler", "05", "Taahhütnameler", "Jeoloji ve jeofizik mühendisi taahhütnameleri"),
    ("ekler", "06", "Tutanak ve Ekler", "Otomatik tutanak ile birleştirilmiş Ekler PDF"),
)


def cikti_merkezi_hazirlik_durumlari(veri, paths=None, preflight=None):
    """Çıktı kartları için arayüzden bağımsız hazırlık durumlarını üret."""
    veri = veri if isinstance(veri, dict) else {}
    paths = paths if isinstance(paths, dict) else {}
    preflight = preflight if isinstance(preflight, dict) else {}
    sondajlar = [item for item in veri.get("sondaj", []) or [] if isinstance(item, dict)]

    log_ready = sum(
        1
        for item in sondajlar
        if (sayi_veya_none(item.get("der")) or 0) > 0 and bool(item.get("litoloji"))
    )
    if not sondajlar:
        log_state, log_detail = "danger", "Sondaj kaydı yok"
    elif log_ready < len(sondajlar):
        log_state, log_detail = "warning", f"{log_ready}/{len(sondajlar)} sondaj log için hazır"
    else:
        log_state, log_detail = "success", f"{log_ready} sondaj log için hazır"

    selected_names = set((veri.get("kesit_ayarlari", {}) or {}).get("selected_sondajlar") or [])
    section_items = [item for item in sondajlar if not selected_names or item.get("no") in selected_names]
    section_coord_ready = sum(koordinat_durumu(item.get("y"), item.get("x"))[0] for item in section_items)
    if len(section_items) < 2:
        section_state, section_detail = "danger", "Kesit için en az iki sondaj gerekli"
    elif section_coord_ready < 2:
        section_state, section_detail = "warning", "Kesit sondaj koordinatları eksik"
    else:
        section_state, section_detail = "success", f"{len(section_items)} sondaj kesite dahil"

    map_paths = list(paths.get("maps", []) or [])
    map_ready = sum(bool(path and os.path.isfile(path)) for path in map_paths)
    map_state = "success" if map_paths and map_ready == len(map_paths) else "warning"
    map_detail = f"{map_ready}/{len(map_paths) or 2} harita hazır"

    image_paths = list(paths.get("report_images", []) or [])
    image_ready = sum(bool(path and os.path.isfile(path)) for path in image_paths)
    image_state = "success" if image_paths and image_ready == len(image_paths) else "warning"
    image_detail = f"{image_ready}/{len(image_paths) or 4} görsel hazır"

    blocking = len(preflight.get("blocking", []) or [])
    warnings = len(preflight.get("warnings", []) or [])
    if blocking:
        report_state, report_detail = "danger", f"{blocking} kritik bulgu raporu engelliyor"
    elif warnings:
        report_state, report_detail = "warning", f"Üretilebilir · {warnings} kontrol uyarısı"
    else:
        report_state, report_detail = "success", "Ön kontrol temiz"

    kunye = veri.get("kunye", {}) if isinstance(veri.get("kunye"), dict) else {}
    taahhut_missing = [
        label
        for key, label in (("sahibi", "proje adı"), ("il", "il"), ("ilce", "ilçe"))
        if not str(kunye.get(key) or "").strip()
    ]
    if taahhut_missing:
        taahhut_state = "warning"
        taahhut_detail = "Eksik: " + ", ".join(taahhut_missing)
    else:
        taahhut_state, taahhut_detail = "success", "Jeoloji ve jeofizik belgeleri hazır"

    ek_state = "success" if sondajlar else "warning"
    ek_detail = (
        f"{len(sondajlar)} sondaj için tutanak üretilebilir"
        if sondajlar
        else "Tutanak için sondaj kaydı gerekli"
    )
    return {
        "report": (report_state, report_detail),
        "logs": (log_state, log_detail),
        "section": (section_state, section_detail),
        "maps": (map_state, map_detail),
        "report_images": (image_state, image_detail),
        "taahhutnameler": (taahhut_state, taahhut_detail),
        "ekler": (ek_state, ek_detail),
    }


def cikti_merkezi_tahmini_dosya_sayisi(veri, selections, map_count=2, image_count=4):
    """Seçilen teslim grupları için asgari çıktı dosyası sayısını hesapla."""
    veri = veri if isinstance(veri, dict) else {}
    selections = selections if isinstance(selections, dict) else {}
    total = 0
    if selections.get("report"):
        total += 1
    if selections.get("logs"):
        total += len(veri.get("sondaj", []) or [])
    if selections.get("section"):
        total += 1
    if selections.get("maps"):
        total += max(0, int(map_count or 0))
    if selections.get("report_images"):
        total += max(0, int(image_count or 0))
    if selections.get("taahhutnameler"):
        total += 2
    if selections.get("ekler"):
        total += 2
    return total


class CiktiMerkeziMixin:
    @perf_tracked("outputs.center_dialog")
    def cikti_merkezi_penceresi(self):
        self.guncelle_veri_objesi(silent=True)
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("cikti_merkezi_klasor") or ayarlar.get("varsayilan_cikti_klasor") or ""
        if not initialdir and self.aktif_dosya_yolu:
            initialdir = os.path.dirname(self.aktif_dosya_yolu)

        preflight_holder = {"report": build_preflight_report(self)}
        if hasattr(self, "on_kontrol_raporunu_sakla"):
            self.on_kontrol_raporunu_sakla(preflight_holder["report"])

        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Çıktı Merkezi", "1020x760", (760, 580), modal=True)

        folder_var = tk.StringVar(value=initialdir if initialdir and os.path.isdir(initialdir) else "")
        fmt_default = str(ayarlar.get("cikti_merkezi_format", "JPG")).upper()
        if fmt_default not in ("JPG", "PNG", "PDF", "SVG"):
            fmt_default = "JPG"
        fmt_var = tk.StringVar(value=fmt_default)
        dpi_var = tk.StringVar(value=str(ayarlar.get("cikti_merkezi_dpi", "300") or "300"))
        saved_selections = ayarlar.get("cikti_merkezi_secimler", {})
        if not isinstance(saved_selections, dict):
            saved_selections = {}
        selection_vars = {
            key: tk.BooleanVar(value=bool(saved_selections.get(key, True)))
            for key, _number, _title, _description in CIKTI_GRUPLARI
        }
        taahhut_format_default = str(ayarlar.get("cikti_taahhut_format", "Excel") or "Excel")
        if taahhut_format_default not in ("Excel", "PDF"):
            taahhut_format_default = "Excel"
        taahhut_format_var = tk.StringVar(value=taahhut_format_default)

        footer = ttk.Frame(win, padding=(SPACE_LG, SPACE_SM, SPACE_LG, SPACE_MD))
        footer.pack(side="bottom", fill="x")
        footer.columnconfigure(0, weight=1)
        selection_summary_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=selection_summary_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        page, _canvas = self.scrollable_page(win, padding=(SPACE_LG, SPACE_MD))
        page.columnconfigure(0, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_MD))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Çıktı Merkezi", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Rapor, çizim ve resmi belgeleri tek bir denetimli teslim klasöründe toplayın.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(SPACE_XS, 0))
        readiness_var = tk.StringVar(value="Hazırlık denetleniyor")
        readiness_label = ttk.Label(header, textvariable=readiness_var, style="Muted.TLabel")
        readiness_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=(SPACE_MD, 0))

        destination = self.ui_surface_frame(page, padding=SPACE_MD)
        destination.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_MD))
        destination.columnconfigure(1, weight=1)
        tk.Label(
            destination,
            text="Teslim Klasörü",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, SPACE_SM))
        ttk.Label(destination, text="Ana klasör").grid(row=1, column=0, sticky="w")
        ttk.Entry(destination, textvariable=folder_var).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(SPACE_MD, SPACE_SM),
        )

        def choose_folder():
            opts = {"initialdir": folder_var.get()} if folder_var.get() and os.path.isdir(folder_var.get()) else {}
            path = filedialog.askdirectory(title="Çıktı klasörünü seçin", **opts)
            if path:
                folder_var.set(path)

        self.modern_button(
            destination,
            text="Klasör Seç",
            command=choose_folder,
            role="neutral",
            outline=True,
            padx=8,
            pady=4,
        ).grid(row=1, column=2, sticky="e")
        tk.Label(
            destination,
            text="Seçilen gruplar numaralı alt klasörlere ayrılır; kalite özeti ana klasöre yazılır.",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(SPACE_SM, 0))
        quick_settings = tk.Frame(destination, bg=COLOR_SURFACE)
        quick_settings.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(SPACE_MD, 0))
        tk.Label(
            quick_settings,
            text="Çizim formatı",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=FONT_UI_BODY,
        ).pack(side="left")
        ttk.Combobox(
            quick_settings,
            textvariable=fmt_var,
            values=("JPG", "PNG", "PDF", "SVG"),
            width=8,
            state="readonly",
        ).pack(side="left", padx=(SPACE_SM, SPACE_LG))
        tk.Label(
            quick_settings,
            text="DPI",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=FONT_UI_BODY,
        ).pack(side="left")
        ttk.Entry(quick_settings, textvariable=dpi_var, width=8).pack(side="left", padx=(SPACE_SM, SPACE_LG))
        tk.Label(
            quick_settings,
            text="Taahhütname",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=FONT_UI_BODY,
        ).pack(side="left")
        ttk.Combobox(
            quick_settings,
            textvariable=taahhut_format_var,
            values=("Excel", "PDF"),
            width=8,
            state="readonly",
        ).pack(side="left", padx=(SPACE_SM, 0))

        section_header = ttk.Frame(page)
        section_header.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_SM))
        section_header.columnconfigure(0, weight=1)
        ttk.Label(section_header, text="Teslim Paketi", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")

        cards_host = ttk.Frame(page)
        cards_host.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_MD))
        card_widgets = {}
        cards = []

        def create_output_card(key, number, title, description):
            card = tk.Frame(
                cards_host,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_MD,
                pady=SPACE_MD,
            )
            card.columnconfigure(1, weight=1)
            number_label = tk.Label(
                card,
                text=number,
                bg=COLOR_SURFACE_ALT,
                fg=COLOR_PRIMARY,
                font=("Segoe UI", 12, "bold"),
                width=3,
                padx=4,
                pady=4,
            )
            number_label.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, SPACE_SM))
            ttk.Checkbutton(
                card,
                text=title,
                variable=selection_vars[key],
                command=lambda: update_selection_summary(),
            ).grid(row=0, column=1, sticky="w")
            tk.Label(
                card,
                text=description,
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
                anchor="w",
                justify="left",
                wraplength=340,
            ).grid(row=1, column=1, sticky="ew", pady=(SPACE_XS, SPACE_SM))
            status = tk.Label(
                card,
                text="Kontrol ediliyor",
                bg=COLOR_SURFACE_ALT,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY_BOLD,
                anchor="w",
                padx=8,
                pady=4,
            )
            status.grid(row=2, column=0, columnspan=2, sticky="ew")
            card_widgets[key] = {"card": card, "status": status, "description": description}
            cards.append(card)
            return card

        for card_info in CIKTI_GRUPLARI:
            create_output_card(*card_info)
        win._cikti_output_cards = cards
        win._cikti_cards_host = cards_host

        layout_state = {"columns": None}

        def layout_cards(event=None):
            width = event.width if event is not None else cards_host.winfo_width()
            columns = 1 if width and width < 760 else 2
            if layout_state["columns"] == columns:
                return
            layout_state["columns"] = columns
            for card in cards:
                card.grid_forget()
            for column in range(2):
                cards_host.columnconfigure(column, weight=0)
            for column in range(columns):
                cards_host.columnconfigure(column, weight=1, uniform="output_cards")
            for idx, card in enumerate(cards):
                row, column = divmod(idx, columns)
                card.grid(
                    row=row,
                    column=column,
                    sticky="nsew",
                    padx=(0, SPACE_SM) if column == 0 and columns > 1 else (SPACE_SM, 0) if columns > 1 else 0,
                    pady=(0, SPACE_SM),
                )

        cards_host.bind("<Configure>", layout_cards)
        self.root.after_idle(layout_cards)

        preflight_button = self.modern_button(
            section_header,
            text="Ön Kontrolü Aç",
            command=lambda: self.on_kontrol_penceresi(preflight_holder["report"]),
            role="warning",
            outline=True,
            padx=8,
            pady=4,
        )
        preflight_button.grid(row=0, column=1, sticky="e")

        def start():
            base_folder = folder_var.get().strip()
            if not base_folder:
                messagebox.showwarning("Çıktı Merkezi", "Lütfen ana çıktı klasörü seçin.")
                return
            selections = {key: bool(var.get()) for key, var in selection_vars.items()}
            if not any(selections.values()):
                messagebox.showwarning("Çıktı Merkezi", "En az bir çıktı türü seçin.")
                return
            try:
                dpi = int(float(dpi_var.get().replace(",", ".")))
                if dpi < 72 or dpi > 1200:
                    raise ValueError
            except Exception:
                messagebox.showwarning("Çıktı Merkezi", "DPI değeri 72 ile 1200 arasında bir sayı olmalı.")
                return
            report = preflight_holder["report"]
            if selections.get("report") and report.get("blocking"):
                messagebox.showwarning(
                    "Çıktı Merkezi",
                    f"Ana raporu engelleyen {len(report['blocking'])} kritik bulgu var.\n\n"
                    "Bulguları düzeltin veya yalnızca diğer çıktıları üretmek için Ana Rapor seçimini kaldırın.",
                    parent=win,
                )
                self.on_kontrol_penceresi(report)
                return
            config = {
                "base_folder": base_folder,
                "format": fmt_var.get().strip().lower(),
                "dpi": dpi,
                **selections,
                "taahhut_format": taahhut_format_var.get(),
            }
            if selections.get("report"):
                config["report_context"] = self.rapor_arka_plan_context()
            ayarlar["cikti_merkezi_klasor"] = base_folder
            ayarlar["cikti_merkezi_format"] = fmt_var.get().strip().upper()
            ayarlar["cikti_merkezi_dpi"] = str(dpi)
            ayarlar["cikti_taahhut_format"] = taahhut_format_var.get()
            ayarlar["cikti_merkezi_secimler"] = selections
            if not ayarlar.get("varsayilan_cikti_klasor"):
                ayarlar["varsayilan_cikti_klasor"] = base_folder
            win.destroy()
            self.cikti_merkezi_baslat(config)

        start_button = self.modern_button(
            footer,
            text="Teslim Paketini Oluştur",
            command=start,
            role="success",
            padx=12,
            pady=6,
        )
        start_button.grid(row=0, column=2, sticky="e", padx=(SPACE_SM, 0))
        self.modern_button(
            footer,
            text="Kapat",
            command=win.destroy,
            role="neutral",
            outline=True,
            padx=10,
            pady=6,
        ).grid(row=0, column=1, sticky="e")

        def output_paths():
            return {
                "maps": [source for _label, source in self.cikti_merkezi_harita_kaynaklari()],
                "report_images": [source for _label, source in self.cikti_merkezi_rapor_gorselleri()],
            }

        def refresh_readiness():
            try:
                self.guncelle_veri_objesi(silent=True)
            except Exception:
                pass
            report = build_preflight_report(self)
            preflight_holder["report"] = report
            if hasattr(self, "on_kontrol_raporunu_sakla"):
                self.on_kontrol_raporunu_sakla(report)
            states = cikti_merkezi_hazirlik_durumlari(self.veri, output_paths(), report)
            ready_count = 0
            for key, (state, detail) in states.items():
                color, soft = self.ui_status_palette(state)
                widgets = card_widgets[key]
                widgets["card"].configure(highlightbackground=color)
                widgets["status"].configure(text=detail, fg=color, bg=soft)
                if state == "success":
                    ready_count += 1
            blockers = len(report.get("blocking", []) or [])
            warnings = len(report.get("warnings", []) or [])
            readiness_var.set(f"{ready_count}/{len(CIKTI_GRUPLARI)} grup hazır · {blockers} kritik · {warnings} uyarı")
            readiness_label.configure(
                foreground=COLOR_DANGER if blockers else (COLOR_WARNING if warnings else COLOR_SUCCESS)
            )
            update_selection_summary()

        def update_selection_summary():
            selections = {key: bool(var.get()) for key, var in selection_vars.items()}
            selected_count = sum(selections.values())
            estimated = cikti_merkezi_tahmini_dosya_sayisi(
                self.veri,
                selections,
                map_count=len(self.cikti_merkezi_harita_kaynaklari()),
                image_count=len(self.cikti_merkezi_rapor_gorselleri()),
            )
            selection_summary_var.set(
                f"{selected_count}/{len(CIKTI_GRUPLARI)} grup seçili · en az {estimated} teslim dosyası"
            )
            start_button.configure(state="normal" if selected_count else "disabled")

        self.modern_button(
            header,
            text="Yenile",
            command=refresh_readiness,
            role="secondary",
            outline=True,
            padx=8,
            pady=4,
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(SPACE_SM, 0))

        refresh_readiness()

    def cikti_merkezi_baslat(self, config):
        config = dict(config)
        config["veri_snapshot"] = copy.deepcopy(self.veri)
        config["map_sources"] = list(self.cikti_merkezi_harita_kaynaklari())
        config["report_image_sources"] = list(self.cikti_merkezi_rapor_gorselleri())
        total = 0
        if config.get("report"):
            total += 1
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
        self.pencere_hazirla(progress_win, "Çıktı Merkezi", "680x330", (560, 280), modal=True)
        status_var = tk.StringVar(value="Hazırlanıyor...")
        detail_var = tk.StringVar(value=f"0 / {total}")
        progress_var = tk.DoubleVar(value=0)
        cancel_state = {"cancelled": False}
        task_handle = {"value": None}

        body = ttk.Frame(progress_win, padding=SPACE_LG)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        status_label = ttk.Label(header, textvariable=status_var, font=FONT_UI_SECTION)
        status_label.grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=detail_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Progressbar(body, maximum=total, variable=progress_var).pack(fill="x", pady=(0, SPACE_MD))
        result_text = tk.Text(
            body,
            height=8,
            wrap="word",
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            font=FONT_UI_BODY,
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        result_text.pack(fill="both", expand=True)
        result_text.insert("1.0", "Seçilen teslim dosyaları sırayla hazırlanıyor.")
        result_text.configure(state="disabled")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(SPACE_MD, 0))

        def cancel():
            cancel_state["cancelled"] = True
            handle = task_handle.get("value")
            if handle is not None:
                engine = getattr(self, "task_engine", None)
                if engine is not None:
                    engine.cancel(handle.task_id)
                else:
                    handle.cancel()
            status_var.set("İptal ediliyor...")
            cancel_btn.config(state="disabled")

        open_btn = self.modern_button(
            buttons,
            text="Klasörü Aç",
            command=lambda: self.cikti_merkezi_klasoru_ac(config.get("base_folder")),
            role="secondary",
            outline=True,
            state="disabled",
        )
        open_btn.pack(side="left")
        control_btn = self.modern_button(
            buttons,
            text="Kalite Sonucu",
            command=self.tamamlama_merkezi_penceresi,
            role="warning",
            outline=True,
            state="disabled",
        )
        control_btn.pack(side="left", padx=SPACE_SM)
        cancel_btn = self.modern_button(
            buttons,
            text="İptal",
            command=cancel,
            role="neutral",
            outline=True,
        )
        cancel_btn.pack(side="right")
        progress = {
            "window": progress_win,
            "status": status_var,
            "status_label": status_label,
            "detail": detail_var,
            "value": progress_var,
            "button": cancel_btn,
            "open_button": open_btn,
            "control_button": control_btn,
            "result_text": result_text,
            "base_folder": config.get("base_folder"),
            "total": total,
        }
        progress_win.protocol("WM_DELETE_WINDOW", cancel)
        self.set_status("Çıktı Merkezi başlatıldı.", level="info")
        task_handle["value"] = self.arka_plan_gorevi_baslat(
            "Çıktı Merkezi",
            self.cikti_merkezi_threaded,
            config,
            progress,
            cancel_state,
            with_context=True,
            resource="render",
            status_start="Çıktı Merkezi arka planda başlatıldı.",
            status_success="Çıktı Merkezi işlemi bitti.",
            status_error="Çıktı Merkezi tamamlanamadı: {error}",
            status_cancel="Çıktı Merkezi iptal edildi.",
            on_cancel=lambda: self.cikti_merkezi_bitti(
                progress,
                progress.get("cancel_message", "Çıktı Merkezi iptal edildi."),
                "warning",
            ),
            on_error=lambda exc: self.cikti_merkezi_bitti(progress, str(exc), "error"),
        )

    def cikti_merkezi_progress(self, progress, done, text):
        task_context = progress.get("task_context") if progress else None
        if task_context is not None:
            task_context.report(done, progress.get("total", 0), text)

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
                color = COLOR_SUCCESS
            elif level == "warning":
                color = COLOR_WARNING
            else:
                color = COLOR_DANGER
            status_label = progress.get("status_label") if progress else None
            if status_label:
                status_label.configure(foreground=color)
            result_text = progress.get("result_text") if progress else None
            if result_text:
                result_text.configure(state="normal")
                result_text.delete("1.0", tk.END)
                result_text.insert("1.0", message)
                result_text.configure(state="disabled")
            open_button = progress.get("open_button") if progress else None
            if open_button:
                open_button.configure(state="normal")
            control_button = progress.get("control_button") if progress else None
            if control_button and getattr(self, "last_output_quality_report", None):
                control_button.configure(state="normal")

        self.root.after(0, apply_finish)

    def cikti_merkezi_klasoru_ac(self, path):
        if not path or not os.path.isdir(path):
            messagebox.showwarning("Çıktı Merkezi", "Çıktı klasörü bulunamadı.")
            return
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Çıktı Merkezi", f"Klasör açılamadı:\n{exc}")

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

    def cikti_merkezi_kesit_sondajlari(self, veri=None):
        veri = veri if isinstance(veri, dict) else self.veri
        options = dict(veri.get("kesit_ayarlari", {}) or {})
        sondajlar = veri.get("sondaj", [])
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
    def cikti_merkezi_threaded(self, config, progress, cancel_state, task_context=None):
        done = 0
        saved_files = []
        errors = []
        base_folder = config["base_folder"]
        veri_snapshot = config.get("veri_snapshot")
        if not isinstance(veri_snapshot, dict):
            veri_snapshot = copy.deepcopy(self.veri)
        map_sources = config.get("map_sources")
        if not isinstance(map_sources, list):
            map_sources = list(self.cikti_merkezi_harita_kaynaklari())
        report_image_sources = config.get("report_image_sources")
        if not isinstance(report_image_sources, list):
            report_image_sources = list(self.cikti_merkezi_rapor_gorselleri())
        fmt = config.get("format", "jpg")
        ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
        dpi = config.get("dpi", 300)
        progress["task_context"] = task_context

        def is_cancelled():
            return bool(
                cancel_state.get("cancelled")
                or (task_context is not None and task_context.cancelled)
            )

        try:
            folders = {
                "report": os.path.join(base_folder, "00_Rapor"),
                "logs": os.path.join(base_folder, "01_Loglar"),
                "sections": os.path.join(base_folder, "02_Kesitler"),
                "maps": os.path.join(base_folder, "03_Haritalar"),
                "report_images": os.path.join(base_folder, "04_Rapor_Gorselleri"),
                "taahhutnameler": os.path.join(base_folder, "05_Taahhutnameler"),
                "ekler": os.path.join(base_folder, "06_Ekler"),
            }
            os.makedirs(base_folder, exist_ok=True)
            selected_folders = {
                "report": config.get("report"),
                "logs": config.get("logs"),
                "sections": config.get("section"),
                "maps": config.get("maps"),
                "report_images": config.get("report_images"),
                "taahhutnameler": config.get("taahhutnameler"),
                "ekler": config.get("ekler"),
            }
            for key, enabled in selected_folders.items():
                if enabled:
                    os.makedirs(folders[key], exist_ok=True)

            if config.get("report") and not is_cancelled():
                self.cikti_merkezi_progress(progress, done, "Ana Word raporu hazırlanıyor...")
                context = config.get("report_context")
                if context is None:
                    errors.append("Ana Rapor: rapor üretim bağlamı hazırlanamadı")
                else:
                    proje_adi = context.veri.get("kunye", {}).get("sahibi") or "Proje"
                    safe_name = self._guvenli_dosya_adi(proje_adi, "Proje")
                    report_path = os.path.join(
                        folders["report"],
                        f"Zemin_Etut_Raporu_{safe_name[:60]}.docx",
                    )
                    try:
                        success, message = rapor_olustur(context, final_path=report_path, autosave=False)
                        if success:
                            saved_files.append(report_path)
                        else:
                            errors.append(f"Ana Rapor: {message}")
                    except Exception as exc:
                        errors.append(f"Ana Rapor: {exc}")
                done += 1
                self.cikti_merkezi_progress(progress, done, "Ana rapor adımı tamamlandı")

            if config.get("logs"):
                for idx, sondaj in enumerate(veri_snapshot.get("sondaj", []), start=1):
                    if is_cancelled():
                        break
                    sondaj_no = sondaj.get("no") or f"SK-{idx}"
                    self.cikti_merkezi_progress(progress, done, f"Log hazırlanıyor: {sondaj_no}")
                    figures = []
                    try:
                        figures = GeoEngine.ciz_profesyonel_log(sondaj, veri_snapshot)
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

            if config.get("section") and not is_cancelled():
                self.cikti_merkezi_progress(progress, done, "Kesit hazırlanıyor...")
                selected, options = self.cikti_merkezi_kesit_sondajlari(veri_snapshot)
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

            if config.get("maps") and not is_cancelled():
                for label, source in map_sources:
                    if is_cancelled():
                        break
                    self.cikti_merkezi_progress(progress, done, f"Harita kopyalanıyor: {label}")
                    try:
                        saved_files.append(self.cikti_merkezi_kopyala(source, folders["maps"], label))
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                    done += 1
                    self.cikti_merkezi_progress(progress, done, f"Harita adımı tamamlandı: {label}")

            if config.get("report_images") and not is_cancelled():
                for label, source in report_image_sources:
                    if is_cancelled():
                        break
                    self.cikti_merkezi_progress(progress, done, f"Rapor görseli kopyalanıyor: {label}")
                    try:
                        saved_files.append(self.cikti_merkezi_kopyala(source, folders["report_images"], label))
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                    done += 1
                    self.cikti_merkezi_progress(progress, done, f"Görsel adımı tamamlandı: {label}")

            if config.get("taahhutnameler") and not is_cancelled():
                self.cikti_merkezi_progress(progress, done, "Taahhütnameler hazırlanıyor...")
                taahhut_ext = ".pdf" if config.get("taahhut_format") == "PDF" else ".xlsx"
                taahhut_label = "PDF" if taahhut_ext == ".pdf" else "Excel"
                try:
                    saved_files.extend(tum_taahhutnameleri_olustur(veri_snapshot, folders["taahhutnameler"], taahhut_ext))
                except Exception as exc:
                    errors.append(f"Taahhütnameler {taahhut_label}: {exc}")
                done += 1
                self.cikti_merkezi_progress(progress, done, "Taahhütname adımı tamamlandı")

            if config.get("ekler") and not is_cancelled():
                self.cikti_merkezi_progress(progress, done, "Ekler PDF hazırlanıyor...")
                try:
                    tutanak_path = os.path.join(folders["ekler"], tutanak_dosya_adi(veri_snapshot, ".docx"))
                    sondaj_haritasi = dict(map_sources).get("Sondaj_Haritasi")
                    tutanaklari_olustur(veri_snapshot, tutanak_path, sondaj_haritasi)
                    saved_files.append(tutanak_path)
                    abs_tutanak = os.path.normcase(os.path.abspath(tutanak_path))
                    for set_key in (EK_SET_NORMAL, EK_SET_ARAZI_DENEYLI):
                        files = ek_icerik_haritasi(veri_snapshot, set_key).setdefault("10", [])
                        existing = {os.path.normcase(os.path.abspath(item)) for item in files if item}
                        if abs_tutanak not in existing:
                            files.append(tutanak_path)
                    ek_path = os.path.join(folders["ekler"], ek_pdf_dosya_adi(veri_snapshot))
                    info = ekler_pdf_olustur(veri_snapshot, ek_path)
                    saved_files.append(info["path"])
                    for warning in info.get("warnings", []):
                        errors.append(f"Ekler: {warning}")
                except Exception as exc:
                    errors.append(f"Ekler: {exc}")
                done += 1
                self.cikti_merkezi_progress(progress, done, "Ekler adımı tamamlandı")

            quality_report = cikti_dosyalari_denetle(saved_files, veri=veri_snapshot)
            quality_manifest = os.path.join(base_folder, "RaporPro_Cikti_Kalite.json")
            kalite_manifestosu_yaz(quality_manifest, quality_report, veri=veri_snapshot)
            self.last_output_quality_report = quality_report
            saved_files.append(quality_manifest)
            for finding in quality_report.get("errors", []) + quality_report.get("warnings", []):
                file_name = os.path.basename(finding.get("path") or "")
                prefix = f"{file_name}: " if file_name else ""
                errors.append(f"Kalite {finding.get('level', 'uyarı')}: {prefix}{finding.get('detail', '')}")

            cancelled = is_cancelled()
            summary_path = self.cikti_merkezi_ozet_yaz(base_folder, saved_files, errors, cancelled)
            if cancelled:
                msg = (
                    "Çıktı Merkezi iptal edildi.\n\n"
                    f"Kaydedilen dosya: {len(saved_files)}\n"
                    f"Özet: {summary_path}"
                )
                progress["cancel_message"] = msg
                raise TaskCancelledError("Çıktı Merkezi kullanıcı tarafından iptal edildi.")
            elif errors:
                preview = "\n".join(f"- {item}" for item in errors[:8])
                suffix = f"\n- ... ve {len(errors) - 8} bulgu daha" if len(errors) > 8 else ""
                msg = (
                    "Teslim paketi oluşturuldu, kontrol edilmesi gereken bulgular var.\n\n"
                    f"Kaydedilen dosya: {len(saved_files)}\n"
                    f"Uyarı/Hata: {len(errors)}\n"
                    f"Özet: {summary_path}\n\n"
                    f"İlk bulgular:\n{preview}{suffix}"
                )
                self.cikti_merkezi_bitti(progress, msg, "warning")
                self.set_status(f"Çıktı Merkezi tamamlandı: {len(saved_files)} dosya, {len(errors)} uyarı/hata.", level="warning")
            else:
                msg = (
                    "Teslim paketi hazır.\n\n"
                    f"Klasör: {base_folder}\n"
                    f"Kaydedilen dosya: {len(saved_files)}\n"
                    f"Kalite denetimi: temiz\n"
                    f"Özet: {summary_path}"
                )
                self.cikti_merkezi_bitti(progress, msg, "success")
                self.set_status(f"Çıktı Merkezi tamamlandı: {len(saved_files)} dosya.", level="success")
        except TaskCancelledError:
            raise
        except Exception as exc:
            self.cikti_merkezi_bitti(progress, str(exc), "error")
            self.set_status(f"Çıktı Merkezi hatası: {exc}", level="error")
