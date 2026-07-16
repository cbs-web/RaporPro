import datetime
import copy
import os
import tkinter as tk
from tkinter import Canvas, Frame, Scrollbar, Toplevel, filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from cizim import VeriGirisPenceresi
from motor import GeoEngine
from pmt_excel_motoru import pmt_excel_dosyalarini_oku, pmt_kayitlarini_veriye_aktar
from performans import perf_timer, perf_tracked
from sabitler import *
from task_engine import TaskCancelledError
from karot_motoru import derinlik_baslangic
from yardimcilar import litoloji_yazim_uyarilari, safe_float, temizle_baslik
from widgets import UndoRedoEntry


# ============================================================================
from ui_spt_veri_penceresi import SPTVeriPenceresi


class SondajMixin:
    def sondaj_zebra_stillerini_hazirla(self):
        style = ttk.Style()
        specs = {
            ("ok", "even"): "#FFFFFF",
            ("ok", "odd"): "#F3F5F7",
            ("warning", "even"): "#FCF3CF",
            ("warning", "odd"): "#F8E9A8",
            ("error", "even"): "#FADBD8",
            ("error", "odd"): "#F6C9C4",
        }
        for (state, parity), color in specs.items():
            style_name = f"Sondaj{state.capitalize()}{parity.capitalize()}.TEntry"
            try:
                style.configure(style_name, fieldbackground=color)
            except Exception:
                pass

    def sondaj_entry_stili(self, state, parity):
        parity = "odd" if parity == "odd" else "even"
        names = {
            "ok": f"SondajOk{parity.capitalize()}.TEntry",
            "warning": f"SondajWarning{parity.capitalize()}.TEntry",
            "error": f"SondajError{parity.capitalize()}.TEntry",
        }
        return names.get(state, names["ok"])

    def sondaj_satir_vurgula(self, row_frame, active):
        try:
            selected = bool(getattr(row_frame, "_selected", False))
            row_frame.configure(
                highlightbackground=(
                    COLOR_ACCENT
                    if selected
                    else "#7FB3D5"
                    if active
                    else getattr(row_frame, "_normal_border", COLOR_BORDER)
                ),
                highlightthickness=2 if active or selected else 1,
            )
        except Exception:
            pass

    def p_sondaj(self, p):
        page = ttk.Frame(p, padding=(12, 10))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        self.sondaj_baslik_ozet_var = tk.StringVar(value="0 sondaj")
        self.sondaj_secili_index_var = tk.IntVar(value=0)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Sondajlar", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(title_area, textvariable=self.sondaj_baslik_ozet_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        header_actions = ttk.Frame(header)
        header_actions.grid(row=0, column=1, sticky="e")
        save_button = self.modern_button(
            header_actions,
            "Kaydet",
            command=self.sondaj_verilerini_kaydet,
            role="secondary",
            outline=True,
            padx=10,
            pady=5,
        )
        save_button.pack(side="left", padx=(0, SPACE_SM))
        self.tooltip_ekle(save_button, "Sondaj tablosundaki değişiklikleri belleğe alır")
        add_button = self.modern_button(
            header_actions,
            "Yeni Sondaj",
            command=self.sondaj_ekle,
            role="primary",
            padx=10,
            pady=5,
        )
        add_button.pack(side="left")
        self.tooltip_ekle(add_button, "Yeni bir sondaj satırı oluşturur")

        toolbar_shell = ttk.Frame(page)
        toolbar_shell.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        ttk.Separator(toolbar_shell).pack(fill="x", pady=(0, SPACE_XS))
        toolbar = ttk.Frame(toolbar_shell)
        toolbar.pack(fill="x")
        toolbar_specs = [
            ("Workbook", self.veri_giris_workbook_tksheet_ac, "Excel benzeri toplu veri girişini açar"),
            ("SPT Merkezi", self.spt_okuma_merkezi_ac, "Excel ve fotoğraf SPT okuma merkezini açar"),
            ("PMT Excel", self.pmt_excel_aktar, "Presiyometre Excel dosyalarından veri aktarır"),
            ("Karot TCR", self.karot_tcr_merkezi_ac, "Karot fotoğrafından TCR hesabı yapar"),
            ("Akıllı Tamamla", self.sondaj_akilli_tamamla, "Eksik temel sondaj alanlarını hazırlar"),
            ("Toplu Log", self.toplu_log_kaydet, "Tüm sondaj loglarını toplu kaydeder"),
            ("Kesit Çiz", self.kesit_secim_penceresi, "Sondajlardan jeolojik kesit hazırlar"),
        ]
        toolbar_buttons = []
        for text, command, tooltip in toolbar_specs:
            button = self.modern_button(
                toolbar,
                text,
                command=command,
                role="secondary",
                outline=True,
                padx=8,
                pady=4,
            )
            toolbar_buttons.append(button)
            self.tooltip_ekle(button, tooltip)
        self.responsive_widget_grid(toolbar, toolbar_buttons, min_width=132, max_cols=7, padx=3, pady=3)
        ttk.Separator(toolbar_shell).pack(fill="x", pady=(SPACE_XS, 0))

        table_header = ttk.Frame(page)
        table_header.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_XS))
        ttk.Label(table_header, text="Sondaj Listesi", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            table_header,
            text="Satırı seçerek ayrıntı işlemlerini aşağıdaki panelden açın",
            style="Muted.TLabel",
        ).pack(side="right")

        container = ttk.Frame(page)
        container.grid(row=3, column=0, sticky="nsew")
        canvas = tk.Canvas(container, bg=COLOR_BG, highlightthickness=0, bd=0)
        scrollbar_y = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar_x = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        self.sondaj_scroll_frame = ttk.Frame(canvas)
        self.sondaj_scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sondaj_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)
        self.sondaj_canvas = canvas

        self.sondaj_secili_panel = tk.Frame(
            page,
            bg=COLOR_SURFACE,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=SPACE_MD,
            pady=SPACE_SM,
        )
        self.sondaj_secili_panel.grid(row=4, column=0, sticky="ew", pady=(SPACE_SM, 0))
        self.sondaj_secili_panel.columnconfigure(0, weight=1)

        detail_header = tk.Frame(self.sondaj_secili_panel, bg=COLOR_SURFACE)
        detail_header.grid(row=0, column=0, sticky="ew")
        detail_header.columnconfigure(0, weight=1)
        detail_text = tk.Frame(detail_header, bg=COLOR_SURFACE)
        detail_text.grid(row=0, column=0, sticky="w")
        self.sondaj_secili_baslik_var = tk.StringVar(value="Seçili sondaj yok")
        self.sondaj_secili_ozet_var = tk.StringVar(value="Önce bir sondaj satırı seçin")
        tk.Label(
            detail_text,
            textvariable=self.sondaj_secili_baslik_var,
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
            anchor="w",
        ).pack(anchor="w")
        self.sondaj_secili_ozet_label = tk.Label(
            detail_text,
            textvariable=self.sondaj_secili_ozet_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
            anchor="w",
        )
        self.sondaj_secili_ozet_label.pack(anchor="w", pady=(2, 0))

        self.sondaj_secili_buttons = {}
        log_button = self.modern_button(
            detail_header,
            "Log Önizle",
            command=lambda: self.sondaj_secili_detay_ac("log"),
            role="secondary",
            outline=True,
            padx=9,
            pady=4,
        )
        log_button.grid(row=0, column=1, sticky="e", padx=(SPACE_SM, 0))
        self.tooltip_ekle(log_button, "Seçili sondajın log önizlemesini açar")
        self.sondaj_secili_buttons["log"] = log_button

        detail_actions = tk.Frame(self.sondaj_secili_panel, bg=COLOR_SURFACE)
        detail_actions.grid(row=1, column=0, sticky="ew", pady=(SPACE_SM, 0))
        detail_specs = [
            ("Litoloji", "litoloji"),
            ("SPT", "spt"),
            ("Numune", "numuneler"),
            ("PMT", "pmt"),
            ("Kaya", "kaya"),
        ]
        detail_buttons = []
        for text, tur in detail_specs:
            button = self.modern_button(
                detail_actions,
                text,
                command=lambda t=tur: self.sondaj_secili_detay_ac(t),
                role="secondary",
                outline=True,
                padx=8,
                pady=4,
            )
            self.sondaj_secili_buttons[tur] = button
            detail_buttons.append(button)
            self.tooltip_ekle(button, f"Seçili sondajın {text} verilerini açar")
        delete_button = self.modern_button(
            detail_actions,
            "Sondajı Sil",
            command=self.sondaj_secili_sil,
            role="danger",
            outline=True,
            padx=8,
            pady=4,
        )
        self.sondaj_secili_buttons["sil"] = delete_button
        detail_buttons.append(delete_button)
        self.tooltip_ekle(delete_button, "Seçili sondajı projeden siler")
        self.responsive_widget_grid(detail_actions, detail_buttons, min_width=145, max_cols=6, padx=3, pady=2)

        self.sondaj_headers = [("Sondaj No", "no"), ("Derinlik", "der"), ("Enlem", "y"), ("Boylam", "x"), ("Kot", "k"), ("Baş. Tarihi", "bas_tar"), ("Bit. Tarihi", "bit_tar"), ("YASS İlk", "yass_d1"), ("YASS T1", "yass_t1"), ("YASS Son", "yass_d2"), ("YASS T2", "yass_t2")]
        self.sondaj_column_widths = {
            "no": 10,
            "der": 9,
            "y": 13,
            "x": 13,
            "k": 8,
            "bas_tar": 11,
            "bit_tar": 11,
            "yass_d1": 9,
            "yass_t1": 11,
            "yass_d2": 9,
            "yass_t2": 11,
        }
        self.sondaj_tablosunu_ciz()

    @perf_tracked("pmt.excel_import")
    def pmt_excel_aktar(self):
        paths = filedialog.askopenfilenames(
            title="Presiyometre Excel Dosyalarını Seç",
            filetypes=[("Excel", "*.xlsm;*.xlsx"), ("Tüm dosyalar", "*.*")],
        )
        if not paths:
            return
        self.guncelle_veri_objesi(silent=True)
        result = pmt_excel_dosyalarini_oku(paths)
        apply_result = pmt_kayitlarini_veriye_aktar(self.veri, result.get("records", []), update_existing=True)
        self.sondaj_tablosunu_ciz()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        if hasattr(self, "otomatik_kaydet"):
            self.otomatik_kaydet()

        warnings = (result.get("warnings", []) or []) + (apply_result.get("warnings", []) or [])
        count_text = (
            f"{apply_result.get('imported', 0)} yeni PMT, "
            f"{apply_result.get('updated', 0)} güncelleme, "
            f"{apply_result.get('skipped', 0)} atlanan"
        )
        if result.get("records"):
            self.set_status(f"PMT Excel aktarımı tamamlandı: {count_text}.", level="success" if not warnings else "warning")
        else:
            self.set_status("PMT Excel aktarımı: okunabilir kayıt bulunamadı.", level="warning")
        if warnings:
            messagebox.showwarning("PMT Excel Aktarımı", count_text + "\n\n" + "\n".join(warnings[:12]))

    @perf_tracked("sondaj.table_redraw")
    def sondaj_tablosunu_ciz(self):
        self.sondaj_zebra_stillerini_hazirla()
        selected_before = self.sondaj_secili_index()
        for widget in self.sondaj_scroll_frame.winfo_children():
            widget.destroy()
        self.sondaj_ui_rows = []
        self.sondaj_ui_buttons = []
        self.sondaj_ui_row_frames = []
        self.sondaj_ui_status_widgets = []

        sondajlar = self.veri.get("sondaj", [])
        if sondajlar:
            selected_before = 0 if selected_before is None else min(selected_before, len(sondajlar) - 1)
        else:
            selected_before = None
        self.sondaj_secili_index_var.set(-1 if selected_before is None else selected_before)

        header_bg = "#E9EEF3"
        header_frame = tk.Frame(
            self.sondaj_scroll_frame,
            bg=header_bg,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            bd=0,
        )
        header_frame.pack(fill="x", pady=(1, 4), padx=2)
        tk.Frame(header_frame, width=5, bg=COLOR_BORDER_STRONG).pack(side="left", fill="y")
        tk.Label(header_frame, text="", width=2, bg=header_bg, font=FONT_BOLD).pack(side="left", padx=1)
        tk.Label(header_frame, text="#", width=3, bg=header_bg, fg=COLOR_PRIMARY, font=FONT_BOLD).pack(side="left", padx=1)
        for lbl, key in self.sondaj_headers:
            tk.Label(
                header_frame,
                text=lbl,
                width=self.sondaj_column_widths.get(key, 11),
                bg=header_bg,
                fg=COLOR_PRIMARY,
                font=FONT_BOLD,
            ).pack(side="left", padx=1, pady=5)
        tk.Label(
            header_frame,
            text="Durum",
            width=18,
            bg=header_bg,
            fg=COLOR_PRIMARY,
            font=FONT_BOLD,
            anchor="w",
        ).pack(side="left", padx=(8, 4))

        for idx, s_data in enumerate(sondajlar):
            parity = "odd" if idx % 2 else "even"
            row_bg = "#F3F5F7" if parity == "odd" else "#FFFFFF"
            status_state, status_text = self.sondaj_satir_genel_durumu(s_data)
            status_color = self.sondaj_durum_rengi(status_state)
            row_frame = tk.Frame(
                self.sondaj_scroll_frame,
                bg=row_bg,
                highlightbackground=COLOR_BORDER,
                highlightthickness=1,
                bd=0,
            )
            row_frame._normal_border = COLOR_BORDER
            row_frame._selected = idx == selected_before
            row_frame.pack(fill="x", pady=(0, 2), padx=2)

            status_strip = tk.Frame(row_frame, width=5, bg=status_color)
            status_strip.pack(side="left", fill="y")
            selector = tk.Radiobutton(
                row_frame,
                variable=self.sondaj_secili_index_var,
                value=idx,
                command=lambda i=idx: self.sondaj_secili_satir_ayarla(i),
                bg=row_bg,
                activebackground=row_bg,
                selectcolor=COLOR_SURFACE,
                bd=0,
                highlightthickness=0,
                padx=0,
                pady=0,
            )
            selector.pack(side="left", padx=(2, 0))
            row_number = tk.Label(
                row_frame,
                text=str(idx + 1),
                width=3,
                bg=row_bg,
                fg=COLOR_PRIMARY,
                font=FONT_BOLD,
                cursor="hand2",
            )
            row_number.pack(side="left", padx=1)
            row_number.bind("<Button-1>", lambda _event, i=idx: self.sondaj_secili_satir_ayarla(i))

            row_entries = {}
            for lbl, key in self.sondaj_headers:
                if key == "sondaj_turu":
                    e = ttk.Combobox(row_frame, values=("Zemin", "Kaya"), state="readonly", width=10)
                    e.set(self.sondaj_turu_degeri(s_data))
                elif key == "delgi_capi":
                    e = ttk.Combobox(row_frame, values=("76mm", "89mm"), state="readonly", width=10)
                    e.set(self.sondaj_delgi_capi_degeri(s_data))
                else:
                    e = UndoRedoEntry(row_frame, width=12)
                    e.insert(0, s_data.get(key, ""))
                e._sondaj_parity = parity
                e.configure(width=self.sondaj_column_widths.get(key, 11))
                e.pack(side="left", padx=1, pady=3)
                e.bind(
                    "<FocusIn>",
                    lambda event, rf=row_frame, i=idx: self.sondaj_satir_odaklandi(rf, i),
                    add="+",
                )
                e.bind("<FocusOut>", lambda event, rf=row_frame: self.sondaj_satir_vurgula(rf, False), add="+")
                row_entries[key] = e

            row_entries['bit_tar'].bind('<FocusOut>', lambda e, r_ents=row_entries: self.oto_yass_tarih(r_ents))
            for key, ent in row_entries.items():
                ent.bind("<Return>", lambda event, r=idx, k=key: self.sondaj_tablo_hucre_git(r + 1, k))
                ent.bind("<Down>", lambda event, r=idx, k=key: self.sondaj_tablo_hucre_git(r + 1, k))
                ent.bind("<Up>", lambda event, r=idx, k=key: self.sondaj_tablo_hucre_git(r - 1, k))

            def bit_tar_enter(event, r_ents=row_entries, r=idx, k="bit_tar"):
                self.oto_yass_tarih(r_ents)
                return self.sondaj_tablo_hucre_git(r + 1, k)

            row_entries['bit_tar'].bind('<Return>', bit_tar_enter)
            for key, ent in row_entries.items():
                ent.bind(
                    "<KeyRelease>",
                    lambda event, i=idx, r_ents=row_entries: self.sondaj_satir_canli_guncelle(i, r_ents),
                    add="+",
                )
                ent.bind(
                    "<FocusOut>",
                    lambda event, i=idx, r_ents=row_entries: self.sondaj_satir_canli_guncelle(i, r_ents),
                    add="+",
                )
                ent.bind(
                    "<<ComboboxSelected>>",
                    lambda event, i=idx, r_ents=row_entries: self.sondaj_satir_canli_guncelle(i, r_ents),
                    add="+",
                )

            status_area = tk.Frame(row_frame, bg=row_bg)
            status_area.pack(side="left", padx=(8, 4), pady=3)
            status_dot = tk.Frame(status_area, width=8, height=8, bg=status_color)
            status_dot.pack(side="left", padx=(0, 6))
            status_dot.pack_propagate(False)
            status_label = tk.Label(
                status_area,
                text=status_text,
                width=16,
                bg=row_bg,
                fg=COLOR_TEXT,
                font=FONT_UI_BODY,
                anchor="w",
            )
            status_label.pack(side="left")
            self.tooltip_ekle(status_label, status_text)

            self.sondaj_ui_rows.append(row_entries)
            self.sondaj_ui_buttons.append({})
            self.sondaj_ui_row_frames.append(row_frame)
            self.sondaj_ui_status_widgets.append(
                {"strip": status_strip, "dot": status_dot, "label": status_label}
            )
            self.sondaj_satirini_canli_dogrula(row_entries)

        if not sondajlar:
            tk.Label(
                self.sondaj_scroll_frame,
                text="Henüz sondaj eklenmedi. Sağ üstteki Yeni Sondaj düğmesini kullanın.",
                bg=COLOR_BG,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
                padx=SPACE_LG,
                pady=SPACE_XL,
            ).pack(fill="x")

        self.sondaj_baslik_ozet_guncelle()
        self.sondaj_secili_satir_ayarla(selected_before, save_current=False)

    def sondaj_secili_index(self):
        sondajlar = self.veri.get("sondaj", []) if hasattr(self, "veri") else []
        if not sondajlar:
            return None
        raw_index = getattr(self, "_sondaj_secili_index", None)
        if raw_index is None:
            try:
                raw_index = self.sondaj_secili_index_var.get()
            except Exception:
                raw_index = 0
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = 0
        return max(0, min(index, len(sondajlar) - 1))

    def sondaj_ui_satir_verisi(self, index):
        sondajlar = self.veri.get("sondaj", []) if hasattr(self, "veri") else []
        if not (0 <= index < len(sondajlar)):
            return {}
        data = dict(sondajlar[index])
        rows = getattr(self, "sondaj_ui_rows", [])
        if index < len(rows):
            for key, entry in rows[index].items():
                try:
                    data[key] = entry.get()
                except Exception:
                    pass
        return data

    def sondaj_satir_genel_durumu(self, sondaj):
        general_keys = ("no", "der", "y", "x", "k", "bas_tar", "bit_tar", "yass_d1", "yass_d2")
        detail_keys = ("litoloji", "spt", "numuneler", "pmt", "kaya")
        has_general = any(str(sondaj.get(key, "")).strip() for key in general_keys)
        has_detail = any(sondaj.get(key) for key in detail_keys)
        if not has_general and not has_detail:
            return "empty", "Veri yok"

        general_field_keys = (
            "no", "der", "y", "x", "k", "bas_tar", "bit_tar",
            "yass_d1", "yass_t1", "yass_d2", "yass_t2",
        )
        for key in general_field_keys:
            state, message = self.sondaj_hucre_durumu(key, sondaj.get(key, ""), row_has_data=True)
            if state in ("warning", "error"):
                return "warning", message

        if not str(sondaj.get("y", "")).strip() or not str(sondaj.get("x", "")).strip():
            return "warning", "Koordinat eksik"
        if not str(sondaj.get("k", "")).strip():
            return "warning", "Sondaj kotu eksik"

        lit_state, lit_message = self._sondaj_detay_durum(sondaj, "litoloji")
        if lit_state == "empty":
            return "warning", "Litoloji eksik"
        if lit_state == "warning":
            return "warning", lit_message

        for tur in ("spt", "pmt", "kaya"):
            if not sondaj.get(tur):
                continue
            state, message = self._sondaj_detay_durum(sondaj, tur)
            if state == "warning":
                return "warning", message
        return "ok", "Hazır"

    def sondaj_durum_rengi(self, state):
        return {
            "ok": COLOR_SUCCESS,
            "warning": COLOR_WARNING,
            "error": COLOR_DANGER,
            "empty": COLOR_TEXT_MUTED,
        }.get(state, COLOR_TEXT_MUTED)

    def sondaj_satir_durum_gorseli_guncelle(self, index, row_entries=None):
        widgets = getattr(self, "sondaj_ui_status_widgets", [])
        if not (0 <= index < len(widgets)):
            return
        data = self.sondaj_ui_satir_verisi(index)
        if row_entries:
            for key, entry in row_entries.items():
                try:
                    data[key] = entry.get()
                except Exception:
                    pass
        state, message = self.sondaj_satir_genel_durumu(data)
        color = self.sondaj_durum_rengi(state)
        status_widgets = widgets[index]
        status_widgets["strip"].configure(bg=color)
        status_widgets["dot"].configure(bg=color)
        status_widgets["label"].configure(text=message, fg=color if state != "empty" else COLOR_TEXT_MUTED)
        status_widgets["label"]._tooltip_text = message

    def sondaj_baslik_ozet_guncelle(self):
        variable = getattr(self, "sondaj_baslik_ozet_var", None)
        if variable is None:
            return
        sondajlar = self.veri.get("sondaj", []) if hasattr(self, "veri") else []
        total_depth = 0.0
        for index in range(len(sondajlar)):
            total_depth += max(0.0, safe_float(self.sondaj_ui_satir_verisi(index).get("der")))
        total_text = f"{total_depth:.2f}".replace(".", ",")
        variable.set(f"{len(sondajlar)} sondaj · toplam {total_text} m")

    def sondaj_satir_canli_guncelle(self, index, row_entries):
        self.sondaj_satirini_canli_dogrula(row_entries)
        self.sondaj_satir_durum_gorseli_guncelle(index, row_entries)
        self.sondaj_baslik_ozet_guncelle()
        if self.sondaj_secili_index() == index:
            self.sondaj_secili_paneli_guncelle()

    def sondaj_satir_odaklandi(self, row_frame, index):
        self.sondaj_secili_satir_ayarla(index)
        self.sondaj_satir_vurgula(row_frame, True)

    def sondaj_secim_gorselini_guncelle(self):
        selected = self.sondaj_secili_index()
        for index, row_frame in enumerate(getattr(self, "sondaj_ui_row_frames", [])):
            row_frame._selected = index == selected
            self.sondaj_satir_vurgula(row_frame, False)

    def sondaj_secili_satir_ayarla(self, index, save_current=True):
        current = getattr(self, "_sondaj_secili_index", None)
        if save_current and current is not None and index != current and getattr(self, "sondaj_ui_rows", []):
            self.sondaj_verilerini_kaydet(silent=True)

        sondajlar = self.veri.get("sondaj", []) if hasattr(self, "veri") else []
        if index is None or not sondajlar:
            self._sondaj_secili_index = None
            try:
                self.sondaj_secili_index_var.set(-1)
            except Exception:
                pass
        else:
            index = max(0, min(int(index), len(sondajlar) - 1))
            self._sondaj_secili_index = index
            try:
                self.sondaj_secili_index_var.set(index)
            except Exception:
                pass
        self.sondaj_secim_gorselini_guncelle()
        self.sondaj_secili_paneli_guncelle()

    def sondaj_detay_buton_metni(self, sondaj, tur, label):
        rows = [row for row in (sondaj.get(tur, []) or []) if self._satirda_veri_var(row)]
        state, message = self._sondaj_detay_durum(sondaj, tur)
        if not rows:
            detail = "Veri yok"
        elif state == "warning":
            detail = f"{len(rows)} kayıt · kontrol"
        else:
            detail = f"{len(rows)} kayıt"
        return f"{label} · {detail}", state, message

    def sondaj_secili_paneli_guncelle(self):
        buttons = getattr(self, "sondaj_secili_buttons", {})
        title_var = getattr(self, "sondaj_secili_baslik_var", None)
        summary_var = getattr(self, "sondaj_secili_ozet_var", None)
        if not buttons or title_var is None or summary_var is None:
            return

        index = self.sondaj_secili_index()
        if index is None:
            title_var.set("Seçili sondaj yok")
            summary_var.set("Önce bir sondaj satırı seçin")
            self.sondaj_secili_ozet_label.configure(fg=COLOR_TEXT_MUTED)
            for button in buttons.values():
                try:
                    button.configure(state="disabled")
                except Exception:
                    pass
            return

        sondaj = self.sondaj_ui_satir_verisi(index)
        no = str(sondaj.get("no", "")).strip() or f"{index + 1}. sondaj"
        depth = safe_float(sondaj.get("der"))
        depth_text = f"{depth:.2f} m".replace(".", ",") if depth > 0 else "Derinlik girilmedi"
        general_state, general_message = self.sondaj_satir_genel_durumu(sondaj)
        title_var.set(f"Seçili sondaj: {no}")
        summary_var.set(f"{depth_text} · {general_message}")
        self.sondaj_secili_ozet_label.configure(fg=self.sondaj_durum_rengi(general_state))

        labels = {
            "litoloji": "Litoloji",
            "spt": "SPT",
            "numuneler": "Numune",
            "pmt": "PMT",
            "kaya": "Kaya",
        }
        for tur, label in labels.items():
            button = buttons.get(tur)
            if button is None:
                continue
            text, state, tooltip = self.sondaj_detay_buton_metni(sondaj, tur, label)
            self.configure_modern_button(
                button,
                text=text,
                role=self.sondaj_islem_buton_rolu(state),
                outline=(state == "empty"),
            )
            button._tooltip_text = tooltip
            try:
                button.configure(state="normal")
            except Exception:
                pass

        log_button = buttons.get("log")
        if log_button is not None:
            log_state, log_tooltip = self._sondaj_detay_durum(sondaj, "log")
            self.configure_modern_button(
                log_button,
                text="Log Önizle",
                role=self.sondaj_islem_buton_rolu(log_state),
                outline=(log_state == "empty"),
            )
            log_button._tooltip_text = log_tooltip
            try:
                log_button.configure(state="normal")
            except Exception:
                pass

        delete_button = buttons.get("sil")
        if delete_button is not None:
            try:
                delete_button.configure(state="normal")
            except Exception:
                pass

    def sondaj_secili_detay_ac(self, tur):
        index = self.sondaj_secili_index()
        if index is None:
            self.set_status("Önce bir sondaj satırı seçin.", level="warning")
            return
        self.sondaj_verilerini_kaydet(silent=True)
        if tur == "log":
            self.satir_log_onizle(index)
            return
        columns = {
            "litoloji": ["Başlangıç", "Bitiş", "Tanım"],
            "spt": [],
            "numuneler": ["Derinlik/Aralık", "Türü/No"],
            "pmt": ["Der", "Em", "Pl"],
            "kaya": ["Derinlik", "TCR (%)", "SCR (%)", "RQD (%)"],
        }
        if tur in columns:
            self.satir_veri_ac(index, tur, columns[tur])

    def sondaj_secili_sil(self):
        index = self.sondaj_secili_index()
        if index is None:
            self.set_status("Silmek için bir sondaj satırı seçin.", level="warning")
            return
        self.sondaj_verilerini_kaydet(silent=True)
        self.sondaj_sil(index)

    def sondaj_tablo_hucre_git(self, row_idx, key):
        """Sondaj tablosunda belirtilen satır ve sütuna (key) odaklan."""
        if 0 <= row_idx < len(self.sondaj_ui_rows):
            entry = self.sondaj_ui_rows[row_idx].get(key)
            if entry:
                entry.focus_set()
                try:
                    entry.selection_range(0, tk.END)
                except Exception:
                    pass
        return "break"

    def sondaj_turu_degeri(self, sondaj):
        ayarlar = self.veri.get("ayarlar", {}) if hasattr(self, "veri") else {}
        text = str(ayarlar.get("sondaj_turu") or (sondaj or {}).get("sondaj_turu", "")).strip().lower()
        if text in ("kaya", "rock"):
            return "Kaya"
        if text in ("zemin", "soil"):
            return "Zemin"
        return "Kaya" if (sondaj or {}).get("kaya") else "Zemin"

    def sondaj_delgi_capi_degeri(self, sondaj, veri=None):
        kaynak = veri if isinstance(veri, dict) else (self.veri if hasattr(self, "veri") else {})
        ayarlar = kaynak.get("ayarlar", {})
        text = str(ayarlar.get("delgi_capi") or (sondaj or {}).get("delgi_capi") or "76mm").strip().replace(" ", "")
        if text.lower() in ("76", "76mm"):
            return "76mm"
        if text.lower() in ("89", "89mm"):
            return "89mm"
        return "76mm"

    def sondaj_log_verisi(self, sondaj, veri=None):
        kaynak = veri if isinstance(veri, dict) else self.veri
        proje = dict(kaynak)
        ayarlar = dict(proje.get("ayarlar", {}))
        ayarlar["delgi_capi"] = self.sondaj_delgi_capi_degeri(sondaj, kaynak)
        proje["ayarlar"] = ayarlar
        return proje

    def sondaj_satirini_canli_dogrula(self, row_entries):
        row_has_data = any(str(ent.get()).strip() for ent in row_entries.values())
        for key, ent in row_entries.items():
            state, message = self.sondaj_hucre_durumu(key, ent.get(), row_has_data)
            try:
                if ent.winfo_class() != "TCombobox":
                    ent.configure(style=self.sondaj_entry_stili(state, getattr(ent, "_sondaj_parity", "even")))
            except Exception:
                pass
            ent._validation_message = message

    def sondaj_hucre_durumu(self, key, value, row_has_data=True):
        text = str(value if value is not None else "").strip()
        if not row_has_data:
            return "ok", ""
        if key == "no":
            return ("ok", "") if text else ("warning", "Sondaj no eksik")
        if key == "der":
            if not text:
                return "warning", "Derinlik eksik"
            return ("ok", "") if safe_float(text) > 0 else ("error", "Derinlik pozitif olmalı")
        if key == "sondaj_turu":
            return ("ok", "") if text in ("Zemin", "Kaya") else ("warning", "Zemin/Kaya seçilmeli")
        if key == "delgi_capi":
            return ("ok", "") if text in ("76mm", "89mm") else ("warning", "76mm veya 89mm seçilmeli")
        if key in ("y", "x"):
            if not text:
                return "ok", ""
            value_num = safe_float(text)
            if key == "y" and -90 <= value_num <= 90 and value_num != 0:
                return "ok", ""
            if key == "x" and -180 <= value_num <= 180 and value_num != 0:
                return "ok", ""
            return "error", "Koordinat geçersiz"
        if key in ("k", "yass_d1", "yass_d2"):
            if not text:
                return "ok", ""
            return ("ok", "") if safe_float(text) >= 0 else ("error", "Sayısal değer beklenir")
        if key in ("bas_tar", "bit_tar", "yass_t1", "yass_t2"):
            if not text:
                return "ok", ""
            try:
                datetime.datetime.strptime(text, "%d.%m.%Y")
                return "ok", ""
            except ValueError:
                return "warning", "Tarih biçimi GG.AA.YYYY olmalı"
        return "ok", ""

    def _satirda_veri_var(self, row):
        return bool(row) and any(str(value if value is not None else "").strip() for value in row)

    def _sondaj_detay_durum(self, sondaj, tur):
        depth = safe_float(sondaj.get("der"))

        if tur == "log":
            if not sondaj.get("litoloji") and not sondaj.get("spt") and not sondaj.get("pmt") and not sondaj.get("kaya"):
                return "empty", "Log için veri yok"
            lit_state, lit_msg = self._sondaj_detay_durum(sondaj, "litoloji")
            if depth <= 0:
                return "warning", "Log için sondaj derinliği eksik"
            if lit_state != "ok":
                return "warning", f"Log uyarısı: {lit_msg}"
            return "ok", "Log verisi uyumlu"

        rows = [row for row in (sondaj.get(tur, []) or []) if self._satirda_veri_var(row)]
        if not rows:
            return "empty", "Veri girilmemiş"

        if tur == "litoloji":
            intervals = []
            for row in rows:
                if len(row) < 2:
                    return "warning", "Eksik litoloji aralığı"
                top, bot = safe_float(row[0]), safe_float(row[1])
                if bot <= top:
                    return "warning", "Başlangıç/bitiş derinliği uyumsuz"
                if depth > 0 and bot > depth + 0.05:
                    return "warning", "Litoloji sondaj derinliğini geçiyor"
                if len(row) > 2 and litoloji_yazim_uyarilari(row[2]):
                    return "warning", "Litoloji tanımında yazım uyarısı var"
                intervals.append((top, bot))
            intervals.sort()
            if intervals[0][0] > 0.05:
                return "warning", "Litoloji 0.00 m'den başlamıyor"
            prev_bot = intervals[0][1]
            for top, bot in intervals[1:]:
                if abs(top - prev_bot) > 0.05:
                    return "warning", "Litolojide boşluk veya çakışma var"
                prev_bot = max(prev_bot, bot)
            if depth > 0 and prev_bot < depth - 0.05:
                return "warning", "Litoloji kuyu sonuna kadar gitmiyor"
            return "ok", "Litoloji uyumlu"

        if tur in ("spt", "pmt", "kaya"):
            seen_depths = set()
            for row in rows:
                row_depth = derinlik_baslangic(row[0] if row else "")
                if row_depth <= 0:
                    return "warning", "Derinlik eksik veya geçersiz"
                if depth > 0 and row_depth > depth + 0.05:
                    return "warning", "Deney derinliği sondaj derinliğini geçiyor"
                depth_key = round(row_depth, 2)
                if depth_key in seen_depths:
                    return "warning", "Aynı derinlikte tekrar kayıt var"
                seen_depths.add(depth_key)
                if tur == "spt" and not any(str(value).strip() for value in row[1:5]):
                    return "warning", "SPT değeri eksik"
                if tur in ("pmt", "kaya") and not any(str(value).strip() for value in row[1:]):
                    return "warning", "Deney değeri eksik"
            return "ok", "Veri uyumlu"

        return "ok", "Veri girilmiş"

    def sondaj_islem_buton_stili(self, sondaj, tur):
        state, message = self._sondaj_detay_durum(sondaj, tur)
        if state == "ok":
            return COLOR_SUCCESS, "white", message
        if state == "warning":
            return COLOR_WARNING, "white", message
        return "#AAB7B8", "#111111", message

    def sondaj_islem_buton_rolu(self, state):
        if state == "ok":
            return "success"
        if state == "warning":
            return "warning"
        return "secondary"

    def oto_yass_tarih(self, row_entries):
        bit_tar_str = row_entries['bit_tar'].get().strip()
        try:
            dt = datetime.datetime.strptime(bit_tar_str, "%d.%m.%Y")
            t2_dt = dt + datetime.timedelta(days=10)
            row_entries['yass_t1'].delete(0, tk.END)
            row_entries['yass_t1'].insert(0, bit_tar_str)
            row_entries['yass_t2'].delete(0, tk.END)
            row_entries['yass_t2'].insert(0, t2_dt.strftime("%d.%m.%Y"))
        except ValueError: pass

    def sondaj_verilerini_kaydet(self, silent=False):
        for idx, row_ents in enumerate(self.sondaj_ui_rows):
            if idx < len(self.veri["sondaj"]):
                for key, ent in row_ents.items(): self.veri["sondaj"][idx][key] = ent.get()
        if not silent:
            self.sondaj_satir_durumlarini_yenile()
            self.set_status("Sondaj verileri hafızaya alındı.")

    def sondaj_satir_durumlarini_yenile(self):
        """Mevcut satırları yeniden oluşturmadan doğrulama ve düğme renklerini yenile."""
        for idx, row_entries in enumerate(getattr(self, "sondaj_ui_rows", [])):
            self.sondaj_satirini_canli_dogrula(row_entries)
            self.sondaj_satir_durum_gorseli_guncelle(idx, row_entries)
            if idx >= len(self.veri.get("sondaj", [])):
                continue
            row_buttons = (
                self.sondaj_ui_buttons[idx]
                if idx < len(getattr(self, "sondaj_ui_buttons", []))
                else {}
            )
            for tur, btn in row_buttons.items():
                state, tip = self._sondaj_detay_durum(self.veri["sondaj"][idx], tur)
                self.configure_modern_button(
                    btn,
                    role=self.sondaj_islem_buton_rolu(state),
                    outline=(state == "empty"),
                )
                btn._tooltip_text = tip
        self.sondaj_baslik_ozet_guncelle()
        self.sondaj_secili_paneli_guncelle()

    def sondaj_akilli_tamamla(self):
        self.sondaj_verilerini_kaydet(silent=True)
        changed = 0
        for idx, sondaj in enumerate(self.veri.get("sondaj", [])):
            depth = safe_float(sondaj.get("der")) or 15.0
            if not sondaj.get("no"):
                sondaj["no"] = f"SK-{idx + 1}"
                changed += 1
            if not sondaj.get("litoloji"):
                sondaj["litoloji"] = [[0, f"{depth:.2f}", "Kil"]]
                changed += 1
            existing_spt = {
                round(safe_float(row[0]), 2)
                for row in sondaj.get("spt", []) or []
                if row and safe_float(row[0]) > 0
            }
            new_spt = []
            d = 1.5
            while d <= depth + 0.01:
                if round(d, 2) not in existing_spt:
                    new_spt.append([f"{d:.2f}", "", "", "", ""])
                d += 1.5
            if new_spt:
                sondaj.setdefault("spt", []).extend(new_spt)
                changed += len(new_spt)
            if not sondaj.get("k"):
                sondaj["k"] = "100.00"
                changed += 1
        self.sondaj_tablosunu_ciz()
        self.ozet_yenile(collect=False)
        self.set_status(f"Akıllı tamamla tamamlandı: {changed} veri/satır hazırlandı.", level="success" if changed else "info")
    def sondaj_hizli_tablo_ac(self):
        self.sondaj_verilerini_kaydet()
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Sondaj Hızlı Tablo", "1180x620", (980, 560))

        focused_cell = {"row": 0, "col": 0}
        table_rows = []
        widths = {
            "no": 10, "der": 9, "y": 14, "x": 14, "k": 9,
            "bas_tar": 12, "bit_tar": 12, "yass_d1": 9, "yass_t1": 12,
            "yass_d2": 9, "yass_t2": 12,
        }

        top = ttk.Frame(win, padding=8)
        top.pack(fill="x")

        container = ttk.Frame(win)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(container, bg=COLOR_BG, highlightthickness=0)
        scroll_y = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_x = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        table = ttk.Frame(canvas)
        table.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=table, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)

        def yeni_sondaj_sablonu(idx):
            bugun = datetime.datetime.now()
            bugun_str = bugun.strftime("%d.%m.%Y")
            t2_str = (bugun + datetime.timedelta(days=10)).strftime("%d.%m.%Y")
            return {
                "no": f"SK-{idx+1}", "der": "15.0", "y": "", "x": "", "k": "",
                "bas_tar": bugun_str, "bit_tar": bugun_str,
                "yass_d1": "", "yass_t1": bugun_str, "yass_d2": "", "yass_t2": t2_str,
                "litoloji": [], "spt": [], "pmt": [], "kaya": [], "numuneler": []
            }

        def focus_cell(row_idx, col_idx):
            if row_idx >= len(table_rows):
                add_row(yeni_sondaj_sablonu(len(table_rows)))
            row_idx = max(0, min(row_idx, len(table_rows) - 1))
            col_idx = max(0, min(col_idx, len(self.sondaj_headers) - 1))
            key = self.sondaj_headers[col_idx][1]
            table_rows[row_idx]["entries"][key].focus_set()
            table_rows[row_idx]["entries"][key].selection_range(0, tk.END)
            return "break"

        def add_row(data=None):
            row_idx = len(table_rows)
            data = data or yeni_sondaj_sablonu(row_idx)
            ttk.Label(table, text=str(row_idx + 1), width=4, anchor="center").grid(row=row_idx + 1, column=0, padx=1, pady=2, sticky="nsew")
            entries = {}
            for col_idx, (label, key) in enumerate(self.sondaj_headers, start=1):
                ent = UndoRedoEntry(table, width=widths.get(key, 11))
                if key == "sondaj_turu":
                    value = data.get(key) or self.sondaj_turu_degeri(data)
                elif key == "delgi_capi":
                    value = data.get(key) or self.sondaj_delgi_capi_degeri(data)
                else:
                    value = data.get(key, "")
                ent.insert(0, value)
                ent.grid(row=row_idx + 1, column=col_idx, padx=1, pady=2, sticky="nsew")
                entries[key] = ent
                ent.bind("<FocusIn>", lambda event, r=row_idx, c=col_idx-1: focused_cell.update({"row": r, "col": c}))
                ent.bind("<Return>", lambda event, r=row_idx, c=col_idx-1: focus_cell(r + 1, c))
                ent.bind("<Control-Down>", lambda event, r=row_idx, c=col_idx-1: copy_down(r, c))
            table_rows.append({"entries": entries})
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

        def copy_down(row_idx, col_idx):
            if row_idx + 1 >= len(table_rows):
                add_row(yeni_sondaj_sablonu(len(table_rows)))
            key = self.sondaj_headers[col_idx][1]
            val = table_rows[row_idx]["entries"][key].get()
            target = table_rows[row_idx + 1]["entries"][key]
            target.delete(0, tk.END)
            target.insert(0, val)
            return focus_cell(row_idx + 1, col_idx)

        def satir_verisini_al(row):
            return {key: row["entries"][key].get().strip() for _, key in self.sondaj_headers}

        def apply_rows(close=False):
            yeni_liste = []
            for idx, row in enumerate(table_rows):
                data = satir_verisini_al(row)
                if idx < len(self.veri["sondaj"]):
                    sondaj = self.veri["sondaj"][idx].copy()
                else:
                    sondaj = yeni_sondaj_sablonu(idx)
                sondaj.update(data)
                for key in ("litoloji", "spt", "pmt", "kaya", "numuneler"):
                    if key not in sondaj:
                        sondaj[key] = []
                yeni_liste.append(sondaj)
            self.veri["sondaj"] = yeni_liste
            self.sondaj_tablosunu_ciz()
            self.ozet_yenile(collect=False)
            self.set_status(f"Hızlı tablodan {len(yeni_liste)} sondaj satırı uygulandı.", level="success")
            if close:
                win.destroy()

        def normalize_header(cell):
            text = str(cell).lower()
            for src, dst in {
                "ç": "c", "ğ": "g", "ı": "i", "i̇": "i", "ö": "o", "ş": "s", "ü": "u",
                "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u",
            }.items():
                text = text.replace(src, dst)
            return temizle_baslik(text)

        def header_map(cells):
            aliases = {
                "sondajno": "no", "sondaj": "no", "no": "no", "sk": "no",
                "derinlik": "der", "der": "der", "derinlikm": "der",
                "enlem": "y", "lat": "y", "latitude": "y", "y": "y",
                "boylam": "x", "lon": "x", "longitude": "x", "x": "x",
                "kot": "k", "k": "k",
                "bastarihi": "bas_tar", "baslangictarihi": "bas_tar", "bastar": "bas_tar",
                "bittarihi": "bit_tar", "bitistarihi": "bit_tar", "bittar": "bit_tar",
                "yassilk": "yass_d1", "yassd1": "yass_d1", "yass1": "yass_d1",
                "yasst1": "yass_t1", "yassilktarih": "yass_t1",
                "yassson": "yass_d2", "yassd2": "yass_d2", "yass2": "yass_d2",
                "yasst2": "yass_t2", "yasssontarih": "yass_t2",
            }
            mapped = []
            for cell in cells:
                mapped.append(aliases.get(normalize_header(cell)))
            return mapped if sum(1 for item in mapped if item) >= 2 else None

        def split_clipboard_line(line):
            if "\t" in line:
                return line.split("\t")
            if ";" in line:
                return line.split(";")
            return line.split()

        def paste_clipboard():
            try:
                raw = win.clipboard_get()
            except Exception as exc:
                messagebox.showerror("Pano", f"Pano okunamadı:\n{exc}")
                return
            rows = [split_clipboard_line(line.strip()) for line in raw.splitlines() if line.strip()]
            if not rows:
                return

            mapping = header_map(rows[0])
            start_row = focused_cell["row"]
            start_col = focused_cell["col"]

            if mapping:
                data_rows = rows[1:]
                for r_offset, cells in enumerate(data_rows):
                    target_row = start_row + r_offset
                    while target_row >= len(table_rows):
                        add_row(yeni_sondaj_sablonu(len(table_rows)))
                    for cell_idx, value in enumerate(cells):
                        if cell_idx >= len(mapping) or not mapping[cell_idx]:
                            continue
                        ent = table_rows[target_row]["entries"][mapping[cell_idx]]
                        ent.delete(0, tk.END)
                        ent.insert(0, value.strip())
            else:
                for r_offset, cells in enumerate(rows):
                    target_row = start_row + r_offset
                    while target_row >= len(table_rows):
                        add_row(yeni_sondaj_sablonu(len(table_rows)))
                    for c_offset, value in enumerate(cells):
                        target_col = start_col + c_offset
                        if target_col >= len(self.sondaj_headers):
                            continue
                        key = self.sondaj_headers[target_col][1]
                        ent = table_rows[target_row]["entries"][key]
                        ent.delete(0, tk.END)
                        ent.insert(0, value.strip())
            self.set_status(f"Panodan {len(rows) - 1 if mapping else len(rows)} satır hızlı tabloya aktarıldı.", level="success")

        for col_idx, (label, key) in enumerate([("#", "_idx")] + self.sondaj_headers):
            tk.Label(table, text=label, bg="#D5DBDB", font=FONT_BOLD, width=widths.get(key, 11)).grid(row=0, column=col_idx, padx=1, pady=2, sticky="nsew")

        for sondaj in self.veri["sondaj"]:
            add_row(sondaj)
        if not table_rows:
            add_row(yeni_sondaj_sablonu(0))

        tk.Button(top, text="Panodan Yapıştır", command=paste_clipboard, bg="#8E44AD", fg="white", font=FONT_BOLD).pack(side="left", padx=4)
        tk.Button(top, text="+ Satır", command=lambda: add_row(yeni_sondaj_sablonu(len(table_rows))), bg=COLOR_ACCENT, fg="white", font=FONT_BOLD).pack(side="left", padx=4)
        tk.Button(top, text="Uygula", command=lambda: apply_rows(False), bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=4)
        tk.Button(top, text="Uygula ve Kapat", command=lambda: apply_rows(True), bg=COLOR_PRIMARY, fg="white", font=FONT_BOLD).pack(side="right", padx=4)

    @perf_tracked("sondaj.detail_open")
    def satir_veri_ac(self, index, tur, cols):
        # Önce mevcut sondaj satırındaki genel bilgileri kaydet
        row_ents = self.sondaj_ui_rows[index]
        for key, ent in row_ents.items(): self.veri["sondaj"][index][key] = ent.get()

        def detay_kaydedildi():
            self.sondaj_tablosunu_ciz()
            self.ozet_yenile(collect=False)
        
        # Eğer açılmak istenen veri SPT ise özel sınıfı (SPTVeriPenceresi) çalıştır
        if tur == "spt":
            sondaj = self.veri["sondaj"][index]
            SPTVeriPenceresi(
                self.root,
                f"{sondaj.get('no','SK')} - SPT GİRİŞİ",
                sondaj["spt"],
                sondaj.setdefault("spt_kaynaklari", []),
                on_save=detay_kaydedildi,
            )
        else:
            # Diğerleri için eski standart giriş penceresini aç
            sondaj = self.veri["sondaj"][index]
            VeriGirisPenceresi(
                self.root,
                f"{sondaj.get('no','SK')} - {tur.upper()}",
                cols,
                sondaj[tur],
                on_save=detay_kaydedildi,
                sondaj_derinligi=sondaj.get("der") if tur == "litoloji" else None,
            )
    @perf_tracked("sondaj.log_preview")
    def satir_log_onizle(self, index):
        self.sondaj_verilerini_kaydet(); sondaj_data = self.veri["sondaj"][index]
        win = Toplevel(self.root); self.pencere_hazirla(win, f"Log Önizleme: {sondaj_data.get('no')}", "700x900", (620, 520)); f = Frame(win); f.pack(fill="both", expand=True)
        top_bar = tk.Frame(f, bg="#333", height=40); top_bar.pack(fill="x")
        cv = Canvas(f); sb = Scrollbar(f, command=cv.yview); fr = Frame(cv); cv.create_window((0,0), window=fr, anchor="nw"); cv.configure(yscrollcommand=sb.set); cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y"); fr.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        def on_draw_warning(msg, level="info"): self.root.after(0, lambda: self.set_status(msg, level))
        GeoEngine.reset_warnings(); figs = GeoEngine.ciz_profesyonel_log(sondaj_data, self.sondaj_log_verisi(sondaj_data), log_callback=on_draw_warning)
        for fig in figs: FigureCanvasTkAgg(fig, master=fr).get_tk_widget().pack(pady=10)
        def save_this_log():
            path = filedialog.asksaveasfilename(
                initialfile=f"{sondaj_data.get('no')}_Log.jpg",
                defaultextension=".jpg",
                filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            )
            if path:
                base, ext = os.path.splitext(path)
                fmt = ext.lstrip(".").lower() or "jpg"
                fmt = "jpg" if fmt in ("jpeg", "jpe") else fmt
                for i, fg in enumerate(figs): save_path = f"{base}_Sayfa{i+1}{ext}" if len(figs)>1 else path; fg.savefig(save_path, dpi=DEFAULT_EXPORT_DPI, bbox_inches='tight', format=fmt)
                messagebox.showinfo("Başarılı", "Log kaydedildi.")
        tk.Button(top_bar, text="Bu Logu Kaydet", bg=COLOR_WARNING, fg="white", font=FONT_BOLD, command=save_this_log).pack(pady=5)

    def _guvenli_dosya_adi(self, value, fallback="dosya"):
        text = str(value or "").strip() or fallback
        cleaned = []
        for char in text:
            cleaned.append(char if char.isalnum() or char in ("-", "_", ".") else "_")
        name = "".join(cleaned).strip("._")
        return name or fallback

    @perf_tracked("sondaj.logs_export_dialog")
    def toplu_log_kaydet(self):
        self.sondaj_verilerini_kaydet(silent=True)
        sondajlar = self.veri.get("sondaj", [])
        if not sondajlar:
            messagebox.showwarning("Toplu Log Kaydet", "Kaydedilecek sondaj bulunamadı.")
            return
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("log_export_klasor") or ayarlar.get("varsayilan_cikti_klasor", "")
        fmt_default = str(ayarlar.get("log_export_format", "JPG")).upper()
        if fmt_default not in ("JPG", "PNG", "PDF", "SVG"):
            fmt_default = "JPG"
        dpi_default = str(ayarlar.get("log_export_dpi", "300") or "300")
        prefix_default = ayarlar.get("log_export_prefix", "Log") or "Log"
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Toplu Log Kaydet", "460x245", (430, 230), modal=True)

        folder_var = tk.StringVar(value=initialdir if initialdir and os.path.isdir(initialdir) else "")
        fmt_var = tk.StringVar(value=fmt_default)
        dpi_var = tk.StringVar(value=dpi_default)
        prefix_var = tk.StringVar(value=prefix_default)

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Klasör").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=folder_var).grid(row=0, column=1, sticky="ew", padx=8, pady=5)
        def choose_folder():
            opts = {"initialdir": folder_var.get()} if folder_var.get() and os.path.isdir(folder_var.get()) else {}
            path = filedialog.askdirectory(title="Logların kaydedileceği klasörü seçin", **opts)
            if path:
                folder_var.set(path)
        tk.Button(body, text="Seç", command=choose_folder, bg="#ECF0F1").grid(row=0, column=2, sticky="ew", pady=5)

        ttk.Label(body, text="Format").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(body, textvariable=fmt_var, values=("JPG", "PNG", "PDF", "SVG"), state="readonly", width=12).grid(row=1, column=1, sticky="w", padx=8, pady=5)

        ttk.Label(body, text="DPI").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=dpi_var, width=14).grid(row=2, column=1, sticky="w", padx=8, pady=5)

        ttk.Label(body, text="Ön ad").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=prefix_var, width=18).grid(row=3, column=1, sticky="w", padx=8, pady=5)

        summary_var = tk.StringVar(value=f"{len(sondajlar)} sondaj hazırlanacak.")
        ttk.Label(body, textvariable=summary_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 3))

        btns = ttk.Frame(body)
        btns.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))

        def start_export():
            folder = folder_var.get().strip()
            if not folder:
                messagebox.showwarning("Toplu Log Kaydet", "Lütfen kayıt klasörü seçin.")
                return
            try:
                dpi = int(float(dpi_var.get().replace(",", ".")))
                if dpi < 72 or dpi > 1200:
                    raise ValueError
            except Exception:
                messagebox.showwarning("Toplu Log Kaydet", "DPI değeri 72 ile 1200 arasında bir sayı olmalı.")
                return
            config = {
                "folder": folder,
                "format": fmt_var.get().strip().lower(),
                "dpi": dpi,
                "prefix": self._guvenli_dosya_adi(prefix_var.get(), "Log"),
            }
            ayarlar["log_export_klasor"] = folder
            ayarlar["log_export_format"] = fmt_var.get().strip().upper()
            ayarlar["log_export_dpi"] = str(dpi)
            ayarlar["log_export_prefix"] = config["prefix"]
            if not ayarlar.get("varsayilan_cikti_klasor"):
                ayarlar["varsayilan_cikti_klasor"] = folder
            win.destroy()
            self.toplu_log_kaydet_baslat(copy.deepcopy(sondajlar), config)

        tk.Button(btns, text="Başlat", command=start_export, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=(5, 0))
        tk.Button(btns, text="Vazgeç", command=win.destroy, bg="#ECF0F1").pack(side="right", padx=5)

    def toplu_log_kaydet_baslat(self, sondajlar, config):
        config = dict(config)
        config["veri_snapshot"] = copy.deepcopy(self.veri)
        progress_win = Toplevel(self.root)
        self.pencere_hazirla(progress_win, "Toplu Log Kaydı", "460x170", (430, 160), modal=True)

        total = len(sondajlar)
        status_var = tk.StringVar(value="Hazırlanıyor...")
        detail_var = tk.StringVar(value="0 / 0")
        progress_var = tk.DoubleVar(value=0)
        cancel_state = {"cancelled": False}
        task_handle = {"value": None}

        body = ttk.Frame(progress_win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, textvariable=status_var, font=FONT_BOLD).pack(anchor="w", pady=(0, 8))
        bar = ttk.Progressbar(body, maximum=max(total, 1), variable=progress_var)
        bar.pack(fill="x", pady=6)
        ttk.Label(body, textvariable=detail_var).pack(anchor="w", pady=(4, 10))

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

        cancel_btn = tk.Button(body, text="İptal", command=cancel, bg="#ECF0F1")
        cancel_btn.pack(side="right")

        progress = {
            "window": progress_win,
            "status": status_var,
            "detail": detail_var,
            "value": progress_var,
            "button": cancel_btn,
            "total": total,
        }
        self.set_status(f"Toplu log kaydı başlatıldı: {total} sondaj", level="info")
        task_handle["value"] = self.arka_plan_gorevi_baslat(
            "Toplu Log Kaydet",
            self.toplu_log_kaydet_threaded,
            sondajlar,
            config,
            progress,
            cancel_state,
            with_context=True,
            resource="render",
            status_start="Toplu log kaydı arka planda başlatıldı.",
            status_success="Toplu log kaydı işlemi bitti.",
            status_error="Toplu log kaydı tamamlanamadı: {error}",
            status_cancel="Toplu log kaydı iptal edildi.",
            on_cancel=lambda: self._toplu_log_progress_bitti(
                progress,
                progress.get("cancel_message", "Toplu log kaydı iptal edildi."),
                "warning",
            ),
            on_error=lambda exc: self._toplu_log_progress_bitti(progress, str(exc), "error"),
        )

    def _toplu_log_progress_guncelle(self, progress, done, text):
        if not progress:
            return
        task_context = progress.get("task_context")
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
                progress["detail"].set(f"{done} / {total}")
            except Exception:
                pass
        self.root.after(0, apply_update)

    def _toplu_log_progress_bitti(self, progress, message, level):
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
                messagebox.showinfo("Toplu Log Kaydet", message)
            elif level == "warning":
                messagebox.showwarning("Toplu Log Kaydet", message)
            else:
                messagebox.showerror("Toplu Log Kaydet", message)
        self.root.after(0, apply_finish)

    def toplu_log_ozet_yaz(self, klasor, config, saved_files, errors, cancelled):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = self._guvenli_dosya_adi(config.get("prefix", "Log"), "Log")
        summary_path = os.path.join(klasor, f"{prefix}_kayit_ozeti_{timestamp}.txt")
        lines = [
            "RaporPro Toplu Log Kayıt Özeti",
            f"Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            f"Klasor: {klasor}",
            f"Format: {str(config.get('format', 'jpg')).upper()}",
            f"DPI: {config.get('dpi', '-')}",
            f"Durum: {'Iptal edildi' if cancelled else 'Tamamlandi'}",
            f"Kaydedilen sayfa: {len(saved_files)}",
            f"Hata sayisi: {len(errors)}",
            "",
            "Kaydedilen dosyalar:",
        ]
        if saved_files:
            lines.extend(f"- {path}" for path in saved_files)
        else:
            lines.append("- Yok")
        lines.extend(["", "Hatalar:"])
        if errors:
            lines.extend(f"- {err}" for err in errors)
        else:
            lines.append("- Yok")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return summary_path

    @perf_tracked("sondaj.logs_export_all")
    def toplu_log_kaydet_threaded(self, sondajlar, config, progress=None, cancel_state=None, task_context=None):
        saved_count = 0
        saved_files = []
        errors = []
        plot_lock_acquired = False
        if progress is not None:
            progress["task_context"] = task_context

        def is_cancelled():
            return bool(
                (cancel_state and cancel_state.get("cancelled"))
                or (task_context is not None and task_context.cancelled)
            )

        try:
            GeoEngine.plot_lock.acquire()
            plot_lock_acquired = True
            klasor = config["folder"]
            fmt = config.get("format", "jpg")
            ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
            dpi = config.get("dpi", 300)
            prefix = config.get("prefix", "Log")
            veri_snapshot = config.get("veri_snapshot")
            if not isinstance(veri_snapshot, dict):
                veri_snapshot = copy.deepcopy(self.veri)
            total = len(sondajlar)
            os.makedirs(klasor, exist_ok=True)
            for idx, sondaj in enumerate(sondajlar, start=1):
                if is_cancelled():
                    break
                sondaj_no = sondaj.get("no") or f"SK-{idx}"
                self._toplu_log_progress_guncelle(progress, idx - 1, f"Log hazırlanıyor: {sondaj_no}")
                self.set_status(f"Log hazırlanıyor ({idx}/{total}): {sondaj_no}", level="info")
                figures = []
                try:
                    with perf_timer("sondaj.log_draw", sondaj_no):
                        figures = GeoEngine.ciz_profesyonel_log(
                            sondaj,
                            self.sondaj_log_verisi(sondaj, veri_snapshot),
                        )
                    safe_no = self._guvenli_dosya_adi(sondaj_no, f"SK_{idx}")
                    for page_idx, fig in enumerate(figures, start=1):
                        suffix = f"_Sayfa{page_idx}" if len(figures) > 1 else ""
                        path = os.path.join(klasor, f"{prefix}_{safe_no}{suffix}.{ext}")
                        with perf_timer("sondaj.log_save", os.path.basename(path)):
                            fig.savefig(path, dpi=dpi, bbox_inches="tight", format=ext)
                        saved_count += 1
                        saved_files.append(path)
                    self._toplu_log_progress_guncelle(progress, idx, f"Kaydedildi: {sondaj_no}")
                except Exception as exc:
                    errors.append(f"{sondaj_no}: {exc}")
                    self.set_status(f"Log kaydedilemedi: {sondaj_no} - {exc}", level="error")
                finally:
                    for fig in figures:
                        try:
                            plt.close(fig)
                        except Exception:
                            pass
            cancelled = is_cancelled()
            summary_path = self.toplu_log_ozet_yaz(klasor, config, saved_files, errors, cancelled)
            if cancelled:
                msg = f"Toplu log kaydı iptal edildi.\n\nKaydedilen sayfa: {saved_count}\nKlasör: {klasor}\nÖzet: {summary_path}"
                if progress is not None:
                    progress["cancel_message"] = msg
                raise TaskCancelledError("Toplu log kaydı kullanıcı tarafından iptal edildi.")
            if errors:
                msg = f"{saved_count} log sayfası kaydedildi.\nÖzet: {summary_path}\n\nHata alınan sondajlar:\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += f"\n... ve {len(errors) - 10} hata daha."
                msg += "\n\nSonraki adım: Çıktı Merkezi ile logları, kesiti ve haritaları aynı klasörde toplayabilirsiniz."
                self._toplu_log_progress_bitti(progress, msg, "warning")
                self.set_status(f"Toplu log kaydı tamamlandı: {saved_count} sayfa, {len(errors)} hata.", level="warning")
            else:
                msg = f"Tüm loglar kaydedildi:\n{klasor}\n\nToplam sayfa: {saved_count}\nÖzet: {summary_path}\n\nSonraki adım: Çıktı Merkezi ile logları, kesiti ve haritaları aynı klasörde toplayabilirsiniz."
                self._toplu_log_progress_bitti(progress, msg, "success")
                self.set_status(f"Toplu log kaydı tamamlandı: {saved_count} sayfa.", level="success")
        except TaskCancelledError:
            raise
        except Exception as exc:
            error_text = str(exc)
            self._toplu_log_progress_bitti(progress, error_text, "error")
            self.set_status(f"Toplu log kaydı hatası: {error_text}", level="error")
        finally:
            if plot_lock_acquired:
                GeoEngine.plot_lock.release()

    def sondaj_ekle(self):
        self.sondaj_verilerini_kaydet()
        bugun = datetime.datetime.now()
        bugun_str = bugun.strftime("%d.%m.%Y")
        t2_str = (bugun + datetime.timedelta(days=10)).strftime("%d.%m.%Y")
        self.veri["sondaj"].append({
            "no": f"SK-{len(self.veri['sondaj']) + 1}", "der": "15.0", "y": "", "x": "", "k": "",
            "bas_tar": bugun_str, "bit_tar": bugun_str, "yass_d1": "", "yass_t1": bugun_str, "yass_d2": "", "yass_t2": t2_str, 
            "litoloji": [], "spt": [], "pmt": [], "kaya": [], "numuneler": []
        })
        self._sondaj_secili_index = len(self.veri["sondaj"]) - 1
        self.sondaj_tablosunu_ciz()

    def sondaj_sil(self, index):
        if not messagebox.askyesno("Sil", f"{index+1}. sıradaki sondaj silinsin mi?"):
            return
        del self.veri["sondaj"][index]
        if self.veri["sondaj"]:
            self._sondaj_secili_index = min(index, len(self.veri["sondaj"]) - 1)
        else:
            self._sondaj_secili_index = None
        self.sondaj_tablosunu_ciz()
        


