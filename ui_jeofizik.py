import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from motor import GeoEngine
from jeofizik_sheet_motoru import jeofizik_sheet_rapora_hazir_mi
from masw_grafik_motoru import (
    masw_word_kaynaklarini_dogrula,
    masw_word_yollari_normalize,
)
from performans import perf_tracked
from sabitler import (
    COLOR_BG,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_BOLD,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    FONT_UI_SECTION,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from tutarlilik_ortak import koordinat_durumu, sayi_veya_none
from widgets import UndoRedoEntry


class JeofizikMixin:
    def p_jeofizik(self, p):
        page = ttk.Frame(p, padding=(12, 10))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        self.jeofizik_ozet_var = tk.StringVar(value="0 sismik serim · 0 mikrotremör")
        self.jeo_secili_ozet_var = tk.StringVar(value="Bir sismik serim seçin")
        self.mt_secili_ozet_var = tk.StringVar(value="Bir mikrotremör kaydı seçin")

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Jeofizik", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(title_area, textvariable=self.jeofizik_ozet_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        date_area = ttk.Frame(header)
        date_area.grid(row=0, column=1, sticky="e")
        ttk.Label(date_area, text="Rapor tarihi", font=FONT_UI_BODY_BOLD).pack(side="left", padx=(0, SPACE_XS))
        self.e_jeo_tar = UndoRedoEntry(date_area, width=13)
        jeo_tarih = self.veri.get("jeofizik", {}).get("tarih", "") if hasattr(self, "veri") else ""
        if jeo_tarih:
            self.e_jeo_tar.insert(0, jeo_tarih)
        self.e_jeo_tar.pack(side="left")

        toolbar_shell = ttk.Frame(page)
        toolbar_shell.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        ttk.Separator(toolbar_shell).pack(fill="x", pady=(0, SPACE_XS))
        toolbar = ttk.Frame(toolbar_shell)
        toolbar.pack(fill="x")
        excel_button = self.modern_button(
            toolbar,
            "Excel'den Veri Al",
            command=self.jeo_excel_yukle_ve_onizle,
            role="secondary",
            outline=True,
            padx=9,
            pady=4,
        )
        excel_button.pack(side="left", padx=(0, SPACE_XS))
        self.tooltip_ekle(excel_button, "Jeofizik Excel dosyasını seçip tablo önizlemesini hazırlar")
        sheet_button = self.modern_button(
            toolbar,
            "Jeofizik Sheet",
            command=self.jeofizik_sheet_ac,
            role="secondary",
            outline=True,
            padx=9,
            pady=4,
        )
        sheet_button.pack(side="left")
        self.tooltip_ekle(sheet_button, "Sismik parametreleri Excel'den kopyalayıp programa yapıştırır")
        masw_button = self.modern_button(
            toolbar,
            "MASW Grafikleri",
            command=self.masw_word_dosyalari_sec,
            role="secondary",
            outline=True,
            padx=9,
            pady=4,
        )
        masw_button.pack(side="left", padx=(SPACE_XS, 0))
        self.tooltip_ekle(
            masw_button,
            "Jeofizik değerlendirme Word'lerinden S-hızı grafiklerini seçer",
        )
        self.jeofizik_kaynak_var = tk.StringVar(value="Manuel veri girişi")
        ttk.Label(toolbar, textvariable=self.jeofizik_kaynak_var, style="Muted.TLabel").pack(side="right")
        ttk.Separator(toolbar_shell).pack(fill="x", pady=(SPACE_XS, 0))

        self.jeofizik_main_notebook = ttk.Notebook(page)
        self.jeofizik_main_notebook.grid(row=2, column=0, sticky="nsew")
        self.jeo_ss_tab = ttk.Frame(self.jeofizik_main_notebook, padding=(8, 8))
        self.jeo_mt_tab = ttk.Frame(self.jeofizik_main_notebook, padding=(8, 8))
        self.jeo_preview_tab = ttk.Frame(self.jeofizik_main_notebook, padding=(8, 8))
        self.jeofizik_main_notebook.add(self.jeo_ss_tab, text="Sismik Serimler")
        self.jeofizik_main_notebook.add(self.jeo_mt_tab, text="Mikrotremör")
        self.jeofizik_main_notebook.add(self.jeo_preview_tab, text="Excel Önizleme")

        # Sismik görünümü: solda kayıt listesi, sağda seçili serimin koordinat ve tabakaları.
        ss_paned = tk.PanedWindow(self.jeo_ss_tab, orient=tk.HORIZONTAL, bg=COLOR_BG, sashwidth=5, bd=0)
        ss_paned.pack(fill="both", expand=True)

        ss_list_panel = tk.Frame(
            ss_paned,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        ss_paned.add(ss_list_panel, width=220, minsize=180, stretch="never")
        ss_list_header = tk.Frame(ss_list_panel, bg=COLOR_SURFACE)
        ss_list_header.pack(fill="x", pady=(0, SPACE_SM))
        tk.Label(
            ss_list_header,
            text="Sismik serimler",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
        ).pack(side="left")
        self.jeo_sayac_var = tk.StringVar(value="0 kayıt")
        tk.Label(
            ss_list_header,
            textvariable=self.jeo_sayac_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
        ).pack(side="right")
        self.jeo_lb = tk.Listbox(
            ss_list_panel,
            height=12,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            selectbackground=COLOR_PRIMARY,
            selectforeground="white",
            activestyle="none",
            font=FONT_UI_BODY,
        )
        self.jeo_lb.pack(fill="both", expand=True)
        self.jeo_lb.bind("<<ListboxSelect>>", self.jeo_sec)
        ss_list_actions = tk.Frame(ss_list_panel, bg=COLOR_SURFACE)
        ss_list_actions.pack(fill="x", pady=(SPACE_SM, 0))
        ss_add = self.modern_button(ss_list_actions, "Yeni Serim", command=self.jeo_ekle, role="primary", padx=7, pady=4)
        ss_add.pack(side="left", fill="x", expand=True, padx=(0, 3))
        ss_delete = self.modern_button(
            ss_list_actions,
            "Sil",
            command=self.jeo_sil,
            role="danger",
            outline=True,
            padx=7,
            pady=4,
        )
        ss_delete.pack(side="left", fill="x", expand=True, padx=(3, 0))

        ss_detail_shell = tk.Frame(
            ss_paned,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        ss_paned.add(ss_detail_shell, minsize=600, stretch="always")
        ss_detail_canvas = tk.Canvas(
            ss_detail_shell,
            bg=COLOR_SURFACE,
            bd=0,
            highlightthickness=0,
        )
        ss_detail_scroll = ttk.Scrollbar(ss_detail_shell, orient="vertical", command=ss_detail_canvas.yview)
        ss_detail_canvas.configure(yscrollcommand=ss_detail_scroll.set)
        ss_detail_scroll.pack(side="right", fill="y")
        ss_detail_canvas.pack(side="left", fill="both", expand=True)
        self.f_ss_detay = tk.Frame(
            ss_detail_canvas,
            bg=COLOR_SURFACE,
            padx=SPACE_MD,
            pady=SPACE_MD,
        )
        ss_detail_window = ss_detail_canvas.create_window((0, 0), window=self.f_ss_detay, anchor="nw")

        def ss_detail_boyutlandir(event=None):
            ss_detail_canvas.configure(scrollregion=ss_detail_canvas.bbox("all"))

        def ss_canvas_boyutlandir(event):
            ss_detail_canvas.itemconfigure(ss_detail_window, width=event.width)

        self.f_ss_detay.bind("<Configure>", ss_detail_boyutlandir)
        ss_detail_canvas.bind("<Configure>", ss_canvas_boyutlandir)
        ss_detail_header = tk.Frame(self.f_ss_detay, bg=COLOR_SURFACE)
        ss_detail_header.pack(fill="x", pady=(0, SPACE_SM))
        ss_detail_header.columnconfigure(0, weight=1)
        self.jeo_secili_baslik_var = tk.StringVar(value="Seçili serim yok")
        tk.Label(
            ss_detail_header,
            textvariable=self.jeo_secili_baslik_var,
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
        ).grid(row=0, column=0, sticky="w")
        self.jeo_secili_ozet_label = tk.Label(
            ss_detail_header,
            textvariable=self.jeo_secili_ozet_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
        )
        self.jeo_secili_ozet_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        coord_f = ttk.LabelFrame(self.f_ss_detay, text="Serim Koordinatları", padding=(10, 8))
        coord_f.pack(fill="x", pady=(0, SPACE_SM))
        coord_f.columnconfigure(1, weight=1)
        coord_f.columnconfigure(2, weight=1)
        ttk.Label(coord_f, text="Nokta", font=FONT_UI_BODY_BOLD).grid(row=0, column=0, padx=4, pady=(0, 4))
        ttk.Label(coord_f, text="Enlem (Y)", font=FONT_UI_BODY_BOLD).grid(row=0, column=1, padx=4, pady=(0, 4))
        ttk.Label(coord_f, text="Boylam (X)", font=FONT_UI_BODY_BOLD).grid(row=0, column=2, padx=4, pady=(0, 4))
        self.jeo_coords = []
        for row_idx, point_name in enumerate(("Başlangıç", "Orta", "Bitiş"), start=1):
            ttk.Label(coord_f, text=point_name).grid(row=row_idx, column=0, sticky="e", padx=4, pady=3)
            for col_idx in (1, 2):
                entry = UndoRedoEntry(coord_f, width=18)
                entry.grid(row=row_idx, column=col_idx, sticky="ew", padx=4, pady=3)
                self.jeo_coords.append(entry)

        layer_f = ttk.LabelFrame(self.f_ss_detay, text="Tabakalar ve Hesaplanan Parametreler", padding=(8, 6))
        layer_f.pack(fill="both", expand=True)
        layer_headers = ("#", "Vp", "Vs", "h", "ρ", "ν", "E", "G", "Vs30", "Vp/Vs")
        for col_idx, label in enumerate(layer_headers):
            ttk.Label(layer_f, text=label, font=FONT_UI_BODY_BOLD, anchor="center").grid(
                row=0,
                column=col_idx,
                padx=2,
                pady=(0, 4),
                sticky="ew",
            )
            layer_f.columnconfigure(col_idx, weight=1 if col_idx else 0)
        self.layer_rows = []
        for row_idx in range(5):
            ttk.Label(layer_f, text=str(row_idx + 1), width=3, anchor="center").grid(
                row=row_idx + 1,
                column=0,
                padx=2,
                pady=3,
            )
            entries = []
            for col_idx in range(1, 5):
                entry = UndoRedoEntry(layer_f, width=6)
                entry.grid(row=row_idx + 1, column=col_idx, padx=2, pady=3, sticky="ew")
                entries.append(entry)
            result_labels = []
            for col_idx in range(5, 10):
                label = tk.Label(
                    layer_f,
                    text="-",
                    bg="#F4F6F7",
                    fg=COLOR_TEXT,
                    width=6,
                    font=FONT_UI_BODY,
                    anchor="center",
                )
                label.grid(row=row_idx + 1, column=col_idx, padx=2, pady=3, sticky="ew")
                result_labels.append(label)
            self.layer_rows.append({"ents": entries, "lbls": result_labels})
        ss_calculate = self.modern_button(
            self.f_ss_detay,
            "Hesapla ve Kaydet",
            command=self.jeo_hesapla,
            role="success",
            padx=10,
            pady=5,
        )
        ss_calculate.pack(anchor="e", pady=(SPACE_SM, 0))
        self.tooltip_ekle(ss_calculate, "Tabaka parametrelerini hesaplar ve seçili serime kaydeder")

        # Mikrotremör görünümü.
        mt_paned = tk.PanedWindow(self.jeo_mt_tab, orient=tk.HORIZONTAL, bg=COLOR_BG, sashwidth=5, bd=0)
        mt_paned.pack(fill="both", expand=True)
        mt_list_panel = tk.Frame(
            mt_paned,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        mt_paned.add(mt_list_panel, width=220, minsize=180, stretch="never")
        mt_list_header = tk.Frame(mt_list_panel, bg=COLOR_SURFACE)
        mt_list_header.pack(fill="x", pady=(0, SPACE_SM))
        tk.Label(
            mt_list_header,
            text="Mikrotremör kayıtları",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
        ).pack(side="left")
        self.mt_sayac_var = tk.StringVar(value="0 kayıt")
        tk.Label(
            mt_list_header,
            textvariable=self.mt_sayac_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
        ).pack(side="right")
        self.mt_lb = tk.Listbox(
            mt_list_panel,
            height=12,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            selectbackground=COLOR_PRIMARY,
            selectforeground="white",
            activestyle="none",
            font=FONT_UI_BODY,
        )
        self.mt_lb.pack(fill="both", expand=True)
        self.mt_lb.bind("<<ListboxSelect>>", self.mt_sec)
        mt_list_actions = tk.Frame(mt_list_panel, bg=COLOR_SURFACE)
        mt_list_actions.pack(fill="x", pady=(SPACE_SM, 0))
        mt_add = self.modern_button(mt_list_actions, "Yeni MT", command=self.mt_ekle, role="primary", padx=7, pady=4)
        mt_add.pack(side="left", fill="x", expand=True, padx=(0, 3))
        mt_delete = self.modern_button(
            mt_list_actions,
            "Sil",
            command=self.mt_sil,
            role="danger",
            outline=True,
            padx=7,
            pady=4,
        )
        mt_delete.pack(side="left", fill="x", expand=True, padx=(3, 0))

        self.f_mt_detay = tk.Frame(
            mt_paned,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=SPACE_LG,
            pady=SPACE_LG,
        )
        mt_paned.add(self.f_mt_detay, minsize=540, stretch="always")
        self.mt_secili_baslik_var = tk.StringVar(value="Seçili mikrotremör kaydı yok")
        tk.Label(
            self.f_mt_detay,
            textvariable=self.mt_secili_baslik_var,
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
        ).pack(anchor="w")
        self.mt_secili_ozet_label = tk.Label(
            self.f_mt_detay,
            textvariable=self.mt_secili_ozet_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
        )
        self.mt_secili_ozet_label.pack(anchor="w", pady=(2, SPACE_MD))

        mt_cnt = ttk.LabelFrame(self.f_mt_detay, text="Ölçüm Bilgileri", padding=(14, 12))
        mt_cnt.pack(fill="x")
        mt_cnt.columnconfigure(1, weight=1)
        mt_cnt.columnconfigure(3, weight=1)
        ttk.Label(mt_cnt, text="Enlem (Y)").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.e_mt_y = UndoRedoEntry(mt_cnt, width=18)
        self.e_mt_y.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(mt_cnt, text="Boylam (X)").grid(row=0, column=2, sticky="e", padx=5, pady=5)
        self.e_mt_x = UndoRedoEntry(mt_cnt, width=18)
        self.e_mt_x.grid(row=0, column=3, sticky="ew", padx=5, pady=5)
        ttk.Separator(mt_cnt, orient="horizontal").grid(row=1, column=0, columnspan=4, sticky="ew", pady=10)
        self.e_mt_details = {}
        lbls_keys = [
            ("Baskın Frekans (Hz)", "freq"),
            ("Baskın Periyot To (sn)", "to"),
            ("Ta (sn)", "ta"),
            ("Tb (sn)", "tb"),
            ("H/V Oranı", "hv"),
            ("Kayıt Süresi (dk)", "sure"),
        ]
        for i, (lbl, k) in enumerate(lbls_keys):
            r = 2 + (i // 2)
            c = (i % 2) * 2
            ttk.Label(mt_cnt, text=lbl).grid(row=r, column=c, sticky="e", padx=5, pady=5)
            entry = UndoRedoEntry(mt_cnt, width=18)
            entry.grid(row=r, column=c + 1, sticky="ew", padx=5, pady=5)
            self.e_mt_details[k] = entry
        mt_save = self.modern_button(
            self.f_mt_detay,
            "Mikrotremör Verilerini Kaydet",
            command=self.mt_kaydet,
            role="success",
            padx=10,
            pady=5,
        )
        mt_save.pack(anchor="e", pady=(SPACE_MD, 0))

        # Excel önizlemesi ayrı görünümde tutulur.
        self.f_jeo_preview = ttk.Frame(self.jeo_preview_tab)
        self.f_jeo_preview.pack(fill="both", expand=True)
        preview_header = ttk.Frame(self.f_jeo_preview)
        preview_header.pack(fill="x", pady=(0, SPACE_SM))
        ttk.Label(preview_header, text="Excel'den Okunan Rapor Tabloları", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            preview_header,
            text="Bu alan yalnızca seçilen Excel dosyasının önizlemesidir.",
            style="Muted.TLabel",
        ).pack(side="right")
        self.nb_preview = ttk.Notebook(self.f_jeo_preview)
        self.nb_preview.pack(fill="both", expand=True)
        self.txt_pre_param = tk.Text(self.nb_preview, height=10, font=("Consolas", 9), wrap="none")
        self.txt_pre_masw = tk.Text(self.nb_preview, height=10, font=("Consolas", 9), wrap="none")
        self.nb_preview.add(self.txt_pre_param, text="Parametreler")
        self.nb_preview.add(self.txt_pre_masw, text="MASW/VP")
        self.jeofizik_ozet_guncelle()

    @staticmethod
    def jeofizik_ss_durum_ozeti(serim):
        """Sismik serim kaydının veri giriş durumunu döndür."""
        serim = serim if isinstance(serim, dict) else {}
        coords = list(serim.get("coords", []) or [])[:6]
        coords.extend([""] * (6 - len(coords)))
        coord_count = sum(bool(str(value).strip()) for value in coords)
        layers = [
            layer
            for layer in (serim.get("layers", []) or [])
            if isinstance(layer, dict)
            and any(str(layer.get(key, "")).strip() for key in ("vp", "vs", "h", "rho"))
        ]

        if coord_count == 0 and not layers:
            return "empty", "Veri girilmemiş"
        if coord_count < 6:
            return "warning", f"Koordinatlar eksik ({coord_count}/6)"
        for pair_idx in range(3):
            ok, detail = koordinat_durumu(coords[pair_idx * 2], coords[pair_idx * 2 + 1])
            if not ok:
                return "warning", f"{pair_idx + 1}. koordinat: {detail}"
        if not layers:
            return "warning", "Tabaka verisi girilmemiş"
        for layer_idx, layer in enumerate(layers):
            vp = sayi_veya_none(layer.get("vp"))
            vs = sayi_veya_none(layer.get("vs"))
            h = sayi_veya_none(layer.get("h"))
            if vp is None or vp <= 0 or vs is None or vs <= 0:
                return "warning", f"{layer_idx + 1}. tabaka Vp/Vs değeri geçersiz"
            if vp <= vs:
                return "warning", f"{layer_idx + 1}. tabakada Vp, Vs'den büyük olmalı"
            if layer_idx < len(layers) - 1 and (h is None or h <= 0):
                return "warning", f"{layer_idx + 1}. tabaka kalınlığı geçersiz"
        return "ok", f"{len(layers)} tabaka · koordinatlar hazır"

    @staticmethod
    def jeofizik_mt_durum_ozeti(kayit):
        """Mikrotremör kaydının veri giriş durumunu döndür."""
        kayit = kayit if isinstance(kayit, dict) else {}
        coord_count = sum(bool(str(kayit.get(key, "")).strip()) for key in ("y", "x"))
        detail_keys = ("freq", "to", "ta", "tb", "hv", "sure")
        detail_count = sum(bool(str(kayit.get(key, "")).strip()) for key in detail_keys)

        if coord_count == 0 and detail_count == 0:
            return "empty", "Veri girilmemiş"
        if coord_count < 2:
            return "warning", "Koordinat eksik"
        coord_ok, coord_detail = koordinat_durumu(kayit.get("y"), kayit.get("x"))
        if not coord_ok:
            return "warning", coord_detail
        if detail_count < len(detail_keys):
            return "warning", f"Ölçüm bilgileri eksik ({detail_count}/{len(detail_keys)})"
        if any((sayi_veya_none(kayit.get(key)) or 0) <= 0 for key in detail_keys):
            return "warning", "Ölçüm bilgileri pozitif sayı olmalı"
        return "ok", "Koordinat ve ölçüm bilgileri hazır"

    @staticmethod
    def jeofizik_durum_rengi(state):
        return {
            "ok": COLOR_SUCCESS,
            "warning": COLOR_WARNING,
            "empty": COLOR_TEXT_MUTED,
        }.get(state, COLOR_TEXT_MUTED)

    def _jeofizik_veri_listeleri(self):
        jeofizik = self.veri.setdefault("jeofizik", {})
        return jeofizik.setdefault("ss_list", []), jeofizik.setdefault("mt_list", [])

    def jeofizik_ozet_guncelle(self):
        """Jeofizik ekranındaki kayıt, kaynak ve seçim özetlerini yenile."""
        ss_list, mt_list = self._jeofizik_veri_listeleri()
        if hasattr(self, "jeofizik_ozet_var"):
            self.jeofizik_ozet_var.set(f"{len(ss_list)} sismik serim · {len(mt_list)} mikrotremör")
        if hasattr(self, "jeo_sayac_var"):
            self.jeo_sayac_var.set(f"{len(ss_list)} kayıt")
        if hasattr(self, "mt_sayac_var"):
            self.mt_sayac_var.set(f"{len(mt_list)} kayıt")

        if hasattr(self, "jeofizik_kaynak_var"):
            if jeofizik_sheet_rapora_hazir_mi(getattr(self, "veri", {})):
                source_text = "Jeofizik Sheet etkin"
            elif getattr(self, "jeo_excel_path", None):
                source_text = os.path.basename(self.jeo_excel_path)
            else:
                source_text = "Manuel veri girişi"
            masw_count = len(getattr(self, "masw_word_paths", []) or [])
            if masw_count:
                source_text += f" · {masw_count} MASW grafik"
            self.jeofizik_kaynak_var.set(source_text)

        selected_ss = getattr(self, "sel_j_idx", None)
        if isinstance(selected_ss, int) and 0 <= selected_ss < len(ss_list):
            serim = ss_list[selected_ss]
            state, summary = self.jeofizik_ss_durum_ozeti(serim)
            if hasattr(self, "jeo_secili_baslik_var"):
                self.jeo_secili_baslik_var.set(str(serim.get("ad") or f"SS-{selected_ss + 1}"))
            if hasattr(self, "jeo_secili_ozet_var"):
                self.jeo_secili_ozet_var.set(summary)
            if hasattr(self, "jeo_secili_ozet_label"):
                self.jeo_secili_ozet_label.config(fg=self.jeofizik_durum_rengi(state))

        selected_mt = getattr(self, "sel_mt_idx", None)
        if isinstance(selected_mt, int) and 0 <= selected_mt < len(mt_list):
            kayit = mt_list[selected_mt]
            state, summary = self.jeofizik_mt_durum_ozeti(kayit)
            if hasattr(self, "mt_secili_baslik_var"):
                self.mt_secili_baslik_var.set(str(kayit.get("no") or f"MT-{selected_mt + 1}"))
            if hasattr(self, "mt_secili_ozet_var"):
                self.mt_secili_ozet_var.set(summary)
            if hasattr(self, "mt_secili_ozet_label"):
                self.mt_secili_ozet_label.config(fg=self.jeofizik_durum_rengi(state))

    def masw_word_etiket_guncelle(self):
        """Secili MASW Word kaynaklarini Jeofizik ve Rapor ekranlarinda goster."""

        paths = masw_word_yollari_normalize(getattr(self, "masw_word_paths", []) or [])
        self.masw_word_paths = paths
        existing_count = sum(os.path.isfile(path) for path in paths)
        missing_count = len(paths) - existing_count
        if not paths:
            text = "MASW hız grafiği Word'leri seçilmedi"
            color = COLOR_WARNING
        elif missing_count:
            text = f"{existing_count}/{len(paths)} Word hazır · {missing_count} dosya bulunamadı"
            color = COLOR_WARNING
        else:
            text = f"{len(paths)} Word · {len(paths)} MASW hız grafiği"
            color = COLOR_SUCCESS
        if hasattr(self, "lbl_masw_word"):
            self.lbl_masw_word.config(text=text, foreground=color)
        self.jeofizik_ozet_guncelle()
        if hasattr(self, "rapor_durum_guncelle"):
            self.rapor_durum_guncelle()

    def masw_word_dosyalari_sec(self):
        """Birden fazla jeofizik Word'unden rapora alinacak MASW grafiklerini sec."""

        paths = filedialog.askopenfilenames(
            title="MASW hız grafiği Word dosyalarını seç",
            filetypes=[("Word belgeleri", "*.docx")],
        )
        if not paths:
            return
        normalized = masw_word_yollari_normalize(paths)
        records, errors = masw_word_kaynaklarini_dogrula(normalized)
        valid_paths = [record.kaynak_yolu for record in records]
        if not valid_paths:
            messagebox.showwarning(
                "MASW Grafikleri",
                "Seçilen Word dosyalarında aktarılabilir MASW hız grafiği bulunamadı.\n\n"
                + "\n".join(errors[:8]),
                parent=self.root,
            )
            return

        self.masw_word_paths = valid_paths
        self.veri.setdefault("dosyalar", {})["masw_word_paths"] = list(valid_paths)
        self.masw_word_etiket_guncelle()
        self.set_status(
            f"{len(valid_paths)} MASW hız grafiği Word kaynağı projeye bağlandı.",
            level="success" if not errors else "warning",
        )
        if errors:
            messagebox.showwarning(
                "MASW Grafikleri",
                f"{len(valid_paths)} dosya eklendi; {len(errors)} dosya atlandı.\n\n"
                + "\n".join(errors[:8]),
                parent=self.root,
            )

    def masw_word_dosyalari_temizle(self):
        """Projedeki MASW Word kaynak baglantilarini kaldir."""

        self.masw_word_paths = []
        self.veri.setdefault("dosyalar", {})["masw_word_paths"] = []
        self.masw_word_etiket_guncelle()
        self.set_status("MASW hız grafiği Word bağlantıları kaldırıldı.", level="warning")

    @perf_tracked("jeofizik.excel_preview")
    def jeo_excel_yukle_ve_onizle(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx;*.xls;*.csv")])
        if not f:
            return

        self.jeo_excel_path = f
        if hasattr(self, "lbl_jeo_excel"):
            self.lbl_jeo_excel.config(text=os.path.basename(f), foreground=COLOR_SUCCESS)
            if hasattr(self, "_jeofizik_label_guncelle"):
                self._jeofizik_label_guncelle()
        self.set_status(f"Jeofizik Excel yüklendi: {os.path.basename(f)}", level="success")

        # raporlama.py'deki mantığı kullanarak veriyi oku (Özet Mantık)
        try:
            import pandas as pd
            # Excel okuma mantığını raporlama.py'den kopyaladık/referans aldık
            if os.path.splitext(f)[1].lower() == ".csv":
                df = pd.read_csv(f, header=None)
            else:
                df = pd.read_excel(f, header=None)

            # Önizleme kutularını temizle
            self.txt_pre_param.delete("1.0", tk.END)
            self.txt_pre_masw.delete("1.0", tk.END)

            self.txt_pre_param.insert(tk.END, f"{'SERİM':<10} | {'TAB.':<5} | {'Vp':<6} | {'Vs':<6} | {'h':<5} | {'E':<8}\n")
            self.txt_pre_param.insert(tk.END, "-"*55 + "\n")

            # Örnek bir veri tarama (raporlama.py'deki s_name/current_serim mantığı)
            current_s = "Bilinmiyor"
            for idx, row in df.iterrows():
                row_str = " ".join([str(x) for x in row if pd.notna(x)])
                if "Serim" in row_str or "SS" in row_str:
                    current_s = row_str.split(":")[-1].strip() if ":" in row_str else "SS-X"

                # Basit bir önizleme satırı oluşturma (Gerçek veriyi fmt_jeo gibi basıyoruz)
                if "VP =" in str(row.iloc[0]):
                    self.txt_pre_param.insert(tk.END, f"{current_s:<10} | Veriler okundu. Rapor çıktısında tablo olarak basılacaktır.\n")
                    break  # Örnek için kısa kestik

            self.txt_pre_param.insert(tk.END, "\n[BİLGİ] Tam tablo yapısı Rapor Oluştur butonuna basınca Word'e işlenecektir.")
            self.jeofizik_main_notebook.select(self.jeo_preview_tab)
            self.jeofizik_ozet_guncelle()

        except Exception as e:
            self.set_status(f"Excel Okuma Hatası: {str(e)}", level="error")

    def jeo_ekle(self):
        ss_list, _ = self._jeofizik_veri_listeleri()
        ss_list.append({"ad": f"SS-{len(ss_list) + 1}", "coords": [""] * 6, "layers": []})
        self.jeofizik_main_notebook.select(self.jeo_ss_tab)
        self.jeo_yenile(select_index=len(ss_list) - 1)
        self.set_status(f"{ss_list[-1]['ad']} veri girişine hazır.", level="info")

    def jeo_sil(self):
        selection = self.jeo_lb.curselection()
        if not selection:
            return
        ss_list, _ = self._jeofizik_veri_listeleri()
        index = selection[0]
        deleted_name = str(ss_list[index].get("ad") or f"SS-{index + 1}")
        del ss_list[index]
        self.sel_j_idx = None
        self.jeo_yenile(select_index=min(index, len(ss_list) - 1))
        self.set_status(f"{deleted_name} silindi.", level="warning")

    def jeo_sec(self, event=None):
        sel = self.jeo_lb.curselection()
        if not sel:
            return
        ss_list, _ = self._jeofizik_veri_listeleri()
        self.sel_j_idx = sel[0]
        s = ss_list[self.sel_j_idx]
        coords = list(s.get("coords", []) or [])[:6]
        coords.extend([""] * (6 - len(coords)))
        for i, value in enumerate(coords):
            self.jeo_coords[i].delete(0, tk.END)
            self.jeo_coords[i].insert(0, value)
        for row in self.layer_rows:
            for ent in row["ents"]:
                ent.delete(0, tk.END)
            for lbl in row["lbls"]:
                lbl.config(text="-")
        for i, l in enumerate(s.get("layers", [])):
            if i < 5:
                entries = self.layer_rows[i]["ents"]
                entries[0].insert(0, l.get("vp", ""))
                entries[1].insert(0, l.get("vs", ""))
                entries[2].insert(0, l.get("h", ""))
                entries[3].insert(0, l.get("rho", ""))
                lbls = self.layer_rows[i]["lbls"]
                lbls[0].config(text=str(l.get("nu", "-")))
                lbls[1].config(text=str(l.get("E", "-")))
                lbls[2].config(text=str(l.get("G", "-")))
                lbls[3].config(text=str(l.get("vs30", "-")))
                lbls[4].config(text=str(l.get("ratio", "-")))
        self.jeofizik_ozet_guncelle()
        if event is not None and self.jeo_coords:
            self.jeo_coords[0].focus_set()

    @perf_tracked("jeofizik.calculate")
    def jeo_hesapla(self):
        ss_list, _ = self._jeofizik_veri_listeleri()
        selected_index = getattr(self, "sel_j_idx", None)
        if not isinstance(selected_index, int) or not 0 <= selected_index < len(ss_list):
            self.set_status("Önce bir sismik serim seçin.", level="warning")
            return
        coords = [entry.get().strip() for entry in self.jeo_coords]
        valid_rows = []
        layers = []
        for row in self.layer_rows:
            vp, vs, h, rho = [e.get() for e in row["ents"]]
            if vp and vs:
                valid_rows.append({"row": row, "vp": vp, "vs": vs, "h": h, "rho": rho})
        for item in valid_rows:
            res = GeoEngine.hesapla_parametreler(item["vp"], item["vs"], item["h"], item["rho"])
            item["row"]["lbls"][0].config(text=res["nu"])
            item["row"]["lbls"][1].config(text=res["E"])
            item["row"]["lbls"][2].config(text=res["G"])
            item["row"]["lbls"][4].config(text=res["ratio"])
            l_data = {
                "vp": item["vp"],
                "vs": item["vs"],
                "h": item["h"],
                "rho": res["rho"],
                "nu": res["nu"],
                "E": res["E"],
                "G": res["G"],
                "K": res["K"],
                "ratio": res["ratio"],
            }
            layers.append(l_data)
        if layers:
            vs30 = GeoEngine.vs30_hesapla(layers)
            layers[0]["vs30"] = vs30
            valid_rows[0]["row"]["lbls"][3].config(text=vs30)
        ss_list[selected_index]["coords"] = coords
        ss_list[selected_index]["layers"] = layers
        self.veri_kaydet()
        self.jeo_yenile(select_index=selected_index)
        self.set_status(f"{ss_list[selected_index].get('ad', 'Sismik serim')} hesaplandı ve kaydedildi.", level="success")

    def mt_ekle(self):
        _, mt_list = self._jeofizik_veri_listeleri()
        mt_list.append({"no": f"MT-{len(mt_list) + 1}", "y": "", "x": ""})
        self.jeofizik_main_notebook.select(self.jeo_mt_tab)
        self.mt_yenile(select_index=len(mt_list) - 1)
        self.set_status(f"{mt_list[-1]['no']} veri girişine hazır.", level="info")

    def mt_sil(self):
        selection = self.mt_lb.curselection()
        if not selection:
            return
        _, mt_list = self._jeofizik_veri_listeleri()
        index = selection[0]
        deleted_name = str(mt_list[index].get("no") or f"MT-{index + 1}")
        del mt_list[index]
        self.sel_mt_idx = None
        self.mt_yenile(select_index=min(index, len(mt_list) - 1))
        self.set_status(f"{deleted_name} silindi.", level="warning")

    def mt_sec(self, event=None):
        sel = self.mt_lb.curselection()
        if not sel:
            return
        _, mt_list = self._jeofizik_veri_listeleri()
        self.sel_mt_idx = sel[0]
        m = mt_list[self.sel_mt_idx]
        self.e_mt_y.delete(0, tk.END)
        self.e_mt_y.insert(0, m.get("y", ""))
        self.e_mt_x.delete(0, tk.END)
        self.e_mt_x.insert(0, m.get("x", ""))

        for k, ent in self.e_mt_details.items():
            ent.delete(0, tk.END)
            ent.insert(0, m.get(k, ""))
        self.jeofizik_ozet_guncelle()
        if event is not None:
            self.e_mt_y.focus_set()

    def mt_kaydet(self):
        _, mt_list = self._jeofizik_veri_listeleri()
        selected_index = getattr(self, "sel_mt_idx", None)
        if not isinstance(selected_index, int) or not 0 <= selected_index < len(mt_list):
            self.set_status("Önce bir mikrotremör kaydı seçin.", level="warning")
            return
        m = mt_list[selected_index]
        m["y"] = self.e_mt_y.get().strip()
        m["x"] = self.e_mt_x.get().strip()
        for k, ent in self.e_mt_details.items():
            m[k] = ent.get().strip()
        self.veri_kaydet()
        self.mt_yenile(select_index=selected_index)
        self.set_status(f"{m.get('no')} verileri projeye kaydedildi.", level="success")

    def jeo_yenile(self, select_index=None):
        ss_list, _ = self._jeofizik_veri_listeleri()
        if select_index is None:
            selection = self.jeo_lb.curselection()
            if selection:
                select_index = selection[0]
            elif isinstance(getattr(self, "sel_j_idx", None), int):
                select_index = self.sel_j_idx
        self.jeo_lb.delete(0, tk.END)
        for index, serim in enumerate(ss_list):
            name = str(serim.get("ad") or f"SS-{index + 1}")
            self.jeo_lb.insert(tk.END, name)
            state, _ = self.jeofizik_ss_durum_ozeti(serim)
            self.jeo_lb.itemconfig(index, fg=self.jeofizik_durum_rengi(state))

        if ss_list:
            select_index = max(0, min(select_index if isinstance(select_index, int) else 0, len(ss_list) - 1))
            self.jeo_lb.selection_set(select_index)
            self.jeo_lb.activate(select_index)
            self.jeo_lb.see(select_index)
            self.jeo_sec()
        else:
            self.sel_j_idx = None
            self.jeo_secili_baslik_var.set("Seçili serim yok")
            self.jeo_secili_ozet_var.set("Yeni Serim ile veri girişine başlayın")
            self.jeo_secili_ozet_label.config(fg=COLOR_TEXT_MUTED)
            for entry in self.jeo_coords:
                entry.delete(0, tk.END)
            for row in self.layer_rows:
                for entry in row["ents"]:
                    entry.delete(0, tk.END)
                for label in row["lbls"]:
                    label.config(text="-")
        self.jeofizik_ozet_guncelle()

    def mt_yenile(self, select_index=None):
        _, mt_list = self._jeofizik_veri_listeleri()
        if select_index is None:
            selection = self.mt_lb.curselection()
            if selection:
                select_index = selection[0]
            elif isinstance(getattr(self, "sel_mt_idx", None), int):
                select_index = self.sel_mt_idx
        self.mt_lb.delete(0, tk.END)
        for index, kayit in enumerate(mt_list):
            name = str(kayit.get("no") or f"MT-{index + 1}")
            self.mt_lb.insert(tk.END, name)
            state, _ = self.jeofizik_mt_durum_ozeti(kayit)
            self.mt_lb.itemconfig(index, fg=self.jeofizik_durum_rengi(state))

        if mt_list:
            select_index = max(0, min(select_index if isinstance(select_index, int) else 0, len(mt_list) - 1))
            self.mt_lb.selection_set(select_index)
            self.mt_lb.activate(select_index)
            self.mt_lb.see(select_index)
            self.mt_sec()
        else:
            self.sel_mt_idx = None
            self.mt_secili_baslik_var.set("Seçili mikrotremör kaydı yok")
            self.mt_secili_ozet_var.set("Yeni MT ile veri girişine başlayın")
            self.mt_secili_ozet_label.config(fg=COLOR_TEXT_MUTED)
            self.e_mt_y.delete(0, tk.END)
            self.e_mt_x.delete(0, tk.END)
            for entry in self.e_mt_details.values():
                entry.delete(0, tk.END)
        self.jeofizik_ozet_guncelle()
