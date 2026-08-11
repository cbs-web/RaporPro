# Dosya: RaporPro/ui_haritalar.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from harita_durum import (
    HARITA_CIKTI_ANAHTARLARI,
    harita_cikti_durumu,
    harita_cikti_meta_olustur,
    harita_formasyon_kodu,
    harita_katman_ayarlari,
)
from harita_motoru import DEFAULT_TILE_SERVER, TILE_SERVERS
from harita_referans import kml_koordinatlari_oku, ss_harita_etiketi
from harita_resim_cache import display_image_read
from jeoloji_raporu import (
    JEOLOJI_BIRIM_KATALOGU,
    KONUM_HER_IKISI,
    KONUM_INCELEME_ALANI,
    jeoloji_birimleri,
)
from performans import perf_timer, perf_tracked
from resim_isaretleyici import ResimIsaretleyici
from sabitler import (
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_BOLD,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from tkgm_ada import tkgm_ada_gorseli_olustur
from tkgm_kml import tkgm_parsel_kml_olustur
from tutarlilik_ortak import koordinat_durumu
from ui_jeoloji_birimleri import JeolojiBirimleriPenceresi
from uygulama_yollari import kullanici_yolu
from yerbuldurur_motoru import YerbuldururMotoru


class HaritalarSekmesiMixin:
    @staticmethod
    def harita_koordinat_ozeti(veri):
        """Harita için kullanılabilir koordinat kayıtlarının sayısını döndür."""

        def pair_ready(y, x):
            return koordinat_durumu(y, x)[0]

        veri = veri if isinstance(veri, dict) else {}
        arazi = veri.get("arazi", {}) if isinstance(veri.get("arazi"), dict) else {}
        sondajlar = veri.get("sondaj", []) if isinstance(veri.get("sondaj"), list) else []
        jeofizik = veri.get("jeofizik", {}) if isinstance(veri.get("jeofizik"), dict) else {}
        ss_list = jeofizik.get("ss_list", []) if isinstance(jeofizik.get("ss_list"), list) else []
        mt_list = jeofizik.get("mt_list", []) if isinstance(jeofizik.get("mt_list"), list) else []

        sondaj_ready = sum(pair_ready(item.get("y"), item.get("x")) for item in sondajlar if isinstance(item, dict))
        ss_ready = 0
        for item in ss_list:
            coords = item.get("coords", []) if isinstance(item, dict) else []
            if len(coords) >= 6 and all(
                pair_ready(coords[pair_idx * 2], coords[pair_idx * 2 + 1])
                for pair_idx in range(3)
            ):
                ss_ready += 1
        mt_ready = sum(pair_ready(item.get("y"), item.get("x")) for item in mt_list if isinstance(item, dict))
        area_ready = int(pair_ready(arazi.get("alan_y"), arazi.get("alan_x")))

        total = 1 + len(sondajlar) + len(ss_list) + len(mt_list)
        ready = area_ready + sondaj_ready + ss_ready + mt_ready
        return {
            "alan": (area_ready, 1),
            "sondaj": (sondaj_ready, len(sondajlar)),
            "ss": (ss_ready, len(ss_list)),
            "mt": (mt_ready, len(mt_list)),
            "ready": ready,
            "total": total,
        }

    @staticmethod
    def harita_dosya_durumu(path, empty_text="Oluşturulmadı"):
        """Harita dosyasının durum seviyesini ve kısa metnini döndür."""
        if path and os.path.isfile(path):
            return "ok", os.path.basename(path)
        if path:
            return "warning", "Dosya bulunamadı"
        return "empty", empty_text

    def p_haritalar(self, p):
        page, _canvas = self.scrollable_page(p, padding=(16, 12))
        page.columnconfigure(0, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Haritalar", style="PageTitle.TLabel").pack(anchor="w")
        self.harita_durum_var = tk.StringVar(value="Harita hazırlığı kontrol ediliyor")
        self.lbl_harita_durum = ttk.Label(title_area, textvariable=self.harita_durum_var, style="Muted.TLabel")
        self.lbl_harita_durum.pack(anchor="w", pady=(2, 0))
        self.modern_button(
            header,
            "Yenile",
            command=self.harita_durum_yenile,
            role="secondary",
            outline=True,
            padx=8,
            pady=4,
        ).grid(row=0, column=1, sticky="e")

        setup = ttk.LabelFrame(page, text="Altlık ve Sınır", padding=(12, 10))
        setup.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        setup.columnconfigure(1, weight=1)

        ttk.Label(setup, text="KML sınırı", font=FONT_UI_BODY_BOLD).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, SPACE_SM),
            pady=SPACE_XS,
        )
        self.lbl_harita_kml_detay = ttk.Label(setup, text="-", style="Muted.TLabel")
        self.lbl_harita_kml_detay.grid(row=0, column=1, sticky="ew", pady=SPACE_XS)
        kml_actions = ttk.Frame(setup)
        kml_actions.grid(row=0, column=2, sticky="e", pady=SPACE_XS)
        self.modern_button(
            kml_actions,
            "KML Seç",
            command=self.kml_sec,
            role="secondary",
            outline=True,
            padx=7,
            pady=4,
        ).pack(side="left", padx=(0, SPACE_XS))
        self.modern_button(
            kml_actions,
            "TKGM'den Al",
            command=self.tkgm_kml_al,
            role="accent",
            outline=True,
            padx=7,
            pady=4,
        ).pack(side="left", padx=(0, SPACE_XS))
        self.modern_button(
            kml_actions,
            "Ada + Komşular",
            command=self.tkgm_ada_gorseli_al,
            role="primary",
            padx=7,
            pady=4,
        ).pack(side="left")

        option_row = ttk.Frame(setup)
        option_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=SPACE_XS)
        option_row.columnconfigure(1, weight=1)
        option_row.columnconfigure(3, weight=1)
        ttk.Label(option_row, text="Uydu altlığı", font=FONT_UI_BODY_BOLD).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, SPACE_SM),
        )
        current_tile = self.veri.get("ayarlar", {}).get("harita_altlik", DEFAULT_TILE_SERVER)
        if current_tile not in TILE_SERVERS:
            current_tile = DEFAULT_TILE_SERVER
        self.harita_altlik_var = tk.StringVar(value=current_tile)
        self.cmb_harita_altlik = ttk.Combobox(
            option_row,
            textvariable=self.harita_altlik_var,
            values=list(TILE_SERVERS.keys()),
            state="readonly",
            width=28,
        )
        self.cmb_harita_altlik.grid(row=0, column=1, sticky="ew", padx=(0, SPACE_MD))
        self.cmb_harita_altlik.bind("<<ComboboxSelected>>", self.harita_altlik_secildi)
        ttk.Label(option_row, text="Jeoloji formasyonu", font=FONT_UI_BODY_BOLD).grid(
            row=0,
            column=2,
            sticky="w",
            padx=(0, SPACE_SM),
        )
        self.cmb_formasyon = ttk.Combobox(
            option_row,
            values=[
                f"{code} ({info['ad']})"
                for code, info in JEOLOJI_BIRIM_KATALOGU.items()
            ],
            width=30,
            state="readonly",
        )
        self.cmb_formasyon.grid(row=0, column=3, sticky="ew")
        self.cmb_formasyon.bind(
            "<<ComboboxSelected>>",
            self.harita_formasyon_secildi,
        )
        self._harita_formasyon_secimini_yenile()

        ttk.Label(
            option_row,
            text="Rapor birimleri",
            font=FONT_UI_BODY_BOLD,
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, SPACE_SM),
            pady=(SPACE_SM, 0),
        )
        self.lbl_jeoloji_birim_ozet = ttk.Label(
            option_row,
            text="-",
            style="Muted.TLabel",
        )
        self.lbl_jeoloji_birim_ozet.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=(SPACE_SM, 0),
        )
        self.modern_button(
            option_row,
            "Jeolojik Birimleri Yönet",
            command=self.jeolojik_birimler_penceresi_ac,
            role="secondary",
            outline=True,
            padx=7,
            pady=4,
        ).grid(row=1, column=3, sticky="e", pady=(SPACE_SM, 0))

        layer_frame = ttk.LabelFrame(setup, text="Katmanlar", padding=(8, 5))
        layer_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(SPACE_SM, 0),
        )
        for column in range(4):
            layer_frame.columnconfigure(column, weight=1)
        saved_layers = harita_katman_ayarlari(
            self.veri.get("ayarlar", {}).get("harita_katmanlari")
        )
        self.harita_layer_vars = {}
        for index, (key, title) in enumerate(
            (
                ("altlik", "Görsel altlık"),
                ("kml", "KML sınırı"),
                ("sondaj", "Sondajlar"),
                ("ss", "Sismik serimler"),
                ("mt", "Mikrotremör"),
                ("etiketler", "Etiketler"),
                ("otomatik_etiket", "Etiket çakışmasını azalt"),
            )
        ):
            variable = tk.BooleanVar(value=saved_layers[key])
            self.harita_layer_vars[key] = variable
            ttk.Checkbutton(
                layer_frame,
                text=title,
                variable=variable,
                command=self.harita_katmanlari_degisti,
            ).grid(
                row=index // 4,
                column=index % 4,
                sticky="w",
                padx=(0, SPACE_SM),
                pady=2,
            )

        coordinates = ttk.LabelFrame(page, text="Çalışma Noktaları", padding=(12, 10))
        coordinates.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_SM))
        coord_header = ttk.Frame(coordinates)
        coord_header.pack(fill="x", pady=(0, SPACE_XS))
        self.lbl_harita_koordinat_ozet = ttk.Label(coord_header, text="-", font=FONT_UI_BODY_BOLD)
        self.lbl_harita_koordinat_ozet.pack(side="left")
        self.modern_button(
            coord_header,
            "Tüm Koordinatları Seç",
            command=self.toplu_harita_ac,
            role="primary",
            padx=8,
            pady=4,
        ).pack(side="right")

        coord_grid = ttk.Frame(coordinates)
        coord_grid.pack(fill="x")
        self.harita_coord_labels = {}
        coord_cards = []
        for key, title in (
            ("alan", "Çalışma Alanı"),
            ("sondaj", "Sondajlar"),
            ("ss", "Sismik Serimler"),
            ("mt", "Mikrotremör"),
        ):
            card = tk.Frame(
                coord_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_MD,
                pady=SPACE_SM,
            )
            tk.Label(
                card,
                text=title,
                bg=COLOR_SURFACE,
                fg=COLOR_PRIMARY,
                font=FONT_UI_BODY_BOLD,
            ).pack(anchor="w")
            status = tk.Label(
                card,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
            )
            status.pack(anchor="w", pady=(2, 0))
            self.harita_coord_labels[key] = status
            coord_cards.append(card)
        self.responsive_widget_grid(coord_grid, coord_cards, min_width=180, max_cols=4, padx=4, pady=4)

        actions = ttk.LabelFrame(page, text="Harita Çizimi", padding=(12, 10))
        actions.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_SM))
        action_grid = ttk.Frame(actions)
        action_grid.pack(fill="x")

        cards = []
        for title, status_attr, role, command in [
            ("Araştırma Noktaları Vaziyet Planı", "lbl_harita_vaziyet", "accent", lambda: self.harita_cizici_ac("vaziyet")),
            ("Mühendislik Jeolojisi", "lbl_harita_jeoloji", "warning", lambda: self.harita_cizici_ac("jeoloji")),
            ("Yerbuldurur Haritası", "lbl_harita_yerbuldurur", "primary", self.yerbuldurur_ac),
            ("TKGM Ada ve Komşu Parseller", "lbl_harita_tkgm_ada", "success", self.tkgm_ada_gorseli_al),
        ]:
            card = tk.Frame(
                action_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_SM,
                pady=SPACE_SM,
            )
            self.modern_button(card, text=title, role=role, pady=9, command=command).pack(fill="x")
            status = tk.Label(
                card,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
                anchor="center",
            )
            status.pack(fill="x", pady=(6, 0))
            setattr(self, status_attr, status)
            cards.append(card)
        self.responsive_widget_grid(action_grid, cards, min_width=230, max_cols=3, padx=4, pady=4)

        outputs = ttk.LabelFrame(page, text="Rapor Çıktıları", padding=(12, 10))
        outputs.grid(row=4, column=0, sticky="ew")
        output_header = ttk.Frame(outputs)
        output_header.pack(fill="x", pady=(0, SPACE_XS))
        self.lbl_harita_cikti_ozet = ttk.Label(output_header, text="-", font=FONT_UI_BODY_BOLD)
        self.lbl_harita_cikti_ozet.pack(side="left")
        self.modern_button(
            output_header,
            "Rapor Sekmesine Git",
            command=lambda: self.nb.select(self.tab_rapor),
            role="secondary",
            outline=True,
            padx=7,
            pady=4,
        ).pack(side="right")
        self.modern_button(
            output_header,
            "Tüm Rapor Haritalarını Yenile",
            command=self.harita_toplu_yenile,
            role="primary",
            padx=7,
            pady=4,
        ).pack(side="right", padx=(0, SPACE_XS))

        output_grid = ttk.Frame(outputs)
        output_grid.pack(fill="x")
        self.harita_output_labels = {}
        self.harita_output_previews = {}
        self.harita_output_preview_images = {}
        self.harita_output_preview_cache = {}
        self.harita_output_cards = {}
        output_cards = []
        for key, title in (
            ("sondaj", "Sondaj Lokasyon"),
            ("jeofizik", "Jeofizik Lokasyon"),
            ("mjh", "Mühendislik Jeolojisi"),
            ("yer", "Yerbuldurur"),
            ("tkgm", "TKGM Ada Görseli"),
        ):
            card = tk.Frame(
                output_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_MD,
                pady=SPACE_SM,
            )
            tk.Label(
                card,
                text=title,
                bg=COLOR_SURFACE,
                fg=COLOR_PRIMARY,
                font=FONT_UI_BODY_BOLD,
            ).pack(anchor="w")
            preview_wrap = tk.Frame(
                card,
                bg="#F3F5F6",
                width=170,
                height=88,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
            )
            preview_wrap.pack(fill="x", pady=(5, 4))
            preview_wrap.pack_propagate(False)
            preview = tk.Label(
                preview_wrap,
                text="Önizleme yok",
                bg="#F3F5F6",
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
            )
            preview.pack(fill="both", expand=True)
            status = tk.Label(
                card,
                text="-",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=FONT_UI_BODY,
                anchor="w",
                justify="left",
            )
            status.pack(fill="x", pady=(2, 0))
            self.harita_output_labels[key] = status
            self.harita_output_previews[key] = preview
            self.harita_output_cards[key] = card
            output_cards.append(card)
        self.responsive_widget_grid(output_grid, output_cards, min_width=180, max_cols=5, padx=4, pady=4)

        self.harita_durum_yenile()

    def harita_katman_ayarlarini_al(self):
        if hasattr(self, "harita_layer_vars"):
            return harita_katman_ayarlari(
                {
                    key: variable.get()
                    for key, variable in self.harita_layer_vars.items()
                }
            )
        ayarlar = self.veri.get("ayarlar", {}) if isinstance(self.veri, dict) else {}
        return harita_katman_ayarlari(
            ayarlar.get("harita_katmanlari") if isinstance(ayarlar, dict) else None
        )

    def harita_katmanlari_degisti(self):
        layers = self.harita_katman_ayarlarini_al()
        self.veri.setdefault("ayarlar", {})["harita_katmanlari"] = layers
        drawings = self.veri.setdefault(
            "harita_cizimleri",
            {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}},
        )
        visibility = dict(layers)
        visibility["jeofizik"] = layers["ss"] and layers["mt"]
        for drawing_key in ("vaziyet", "jeoloji"):
            drawing = drawings.get(drawing_key)
            if isinstance(drawing, dict) and drawing:
                drawing["visibility"] = dict(visibility)
        if hasattr(self, "set_save_indicator"):
            self.set_save_indicator("Harita katmanları değişti: kaydedilmedi", "warning")
        self.harita_durum_yenile()

    def _harita_output_paths(self):
        return {
            "sondaj": getattr(self, "word_img_sondaj", None),
            "jeofizik": getattr(self, "word_img_jeofizik", None),
            "mjh": getattr(self, "img_mjh", None),
            "yer": getattr(self, "img_yer", None),
            "tkgm": getattr(self, "img_tkgm", None),
        }

    def _harita_cikti_meta_kaydet(self, cikti_tipi, path):
        if cikti_tipi not in HARITA_CIKTI_ANAHTARLARI or not path:
            return
        self.veri.setdefault("harita_cikti_meta", {})[cikti_tipi] = (
            harita_cikti_meta_olustur(self.veri, cikti_tipi, path)
        )

    def _harita_cikti_onizleme_yenile(self, key, path):
        preview = getattr(self, "harita_output_previews", {}).get(key)
        if preview is None:
            return
        if not path or not os.path.isfile(path):
            self.harita_output_preview_images.pop(key, None)
            self.harita_output_preview_cache.pop(key, None)
            preview.configure(image="", text="Önizleme yok", cursor="")
            preview.unbind("<Button-1>")
            return
        try:
            cache_key = (os.path.abspath(path), os.path.getmtime(path), os.path.getsize(path))
        except OSError:
            cache_key = (os.path.abspath(path), None, None)
        if self.harita_output_preview_cache.get(key) == cache_key:
            return
        try:
            with Image.open(path) as source:
                image = source.convert("RGB")
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                image.thumbnail((176, 84), resampling)
            preview_image = ImageTk.PhotoImage(image)
            self.harita_output_preview_images[key] = preview_image
            self.harita_output_preview_cache[key] = cache_key
            preview.configure(image=preview_image, text="", cursor="hand2")
            preview.bind(
                "<Button-1>",
                lambda _event, output_path=path: self._harita_cikti_ac(output_path),
            )
        except Exception:
            self.harita_output_preview_images.pop(key, None)
            self.harita_output_preview_cache.pop(key, None)
            preview.configure(image="", text="Önizleme açılamadı", cursor="")
            preview.unbind("<Button-1>")

    @staticmethod
    def _harita_cikti_ac(path):
        if path and os.path.isfile(path):
            try:
                os.startfile(path)
            except OSError:
                pass

    def _harita_formasyon_secimini_yenile(self):
        if not hasattr(self, "cmb_formasyon"):
            return
        selected_code = harita_formasyon_kodu(self.veri)
        info = JEOLOJI_BIRIM_KATALOGU[selected_code]
        self.cmb_formasyon.set(f"{selected_code} ({info['ad']})")

    def harita_formasyon_secildi(self, _event=None):
        if not hasattr(self, "cmb_formasyon"):
            return
        code = self.cmb_formasyon.get().split(" ", 1)[0].strip()
        if code not in JEOLOJI_BIRIM_KATALOGU:
            return
        self.veri.setdefault("ayarlar", {})["harita_formasyon"] = code
        if hasattr(self, "set_status"):
            self.set_status(
                f"Mühendislik jeolojisi harita etiketi {code} olarak seçildi.",
                level="success",
            )

    def jeolojik_birimler_penceresi_ac(self):
        JeolojiBirimleriPenceresi(
            self,
            on_saved=self.jeolojik_birimler_kaydedildi,
        )

    def jeolojik_birimler_kaydedildi(self):
        records = jeoloji_birimleri(self.veri)
        first_known = next(
            (
                record.get("kod")
                for record in records
                if record.get("konum")
                in {KONUM_INCELEME_ALANI, KONUM_HER_IKISI}
                and record.get("kod") in JEOLOJI_BIRIM_KATALOGU
            ),
            "",
        )
        if first_known:
            self.veri.setdefault("ayarlar", {})[
                "harita_formasyon"
            ] = first_known
        self._harita_formasyon_secimini_yenile()
        self.harita_durum_yenile()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile()

    def harita_durum_yenile(self):
        saved_layers = harita_katman_ayarlari(
            self.veri.get("ayarlar", {}).get("harita_katmanlari")
            if isinstance(self.veri, dict)
            else None
        )
        for key, variable in getattr(self, "harita_layer_vars", {}).items():
            if bool(variable.get()) != saved_layers[key]:
                variable.set(saved_layers[key])

        kml_path = getattr(self, "kml_path", None)
        kml_state, kml_text = self.harita_dosya_durumu(kml_path, "KML seçilmedi")
        status_colors = {
            "ok": COLOR_SUCCESS,
            "stale": COLOR_WARNING,
            "warning": COLOR_WARNING,
            "empty": COLOR_DANGER,
        }
        kml_color = status_colors[kml_state]
        if hasattr(self, "lbl_harita_kml_detay"):
            self.lbl_harita_kml_detay.config(text=kml_text, foreground=kml_color)

        tile_name = self.veri.get("ayarlar", {}).get("harita_altlik", DEFAULT_TILE_SERVER)
        if tile_name not in TILE_SERVERS:
            tile_name = DEFAULT_TILE_SERVER
        if hasattr(self, "harita_altlik_var") and self.harita_altlik_var.get() != tile_name:
            self.harita_altlik_var.set(tile_name)
        if hasattr(self, "lbl_harita_altlik"):
            self.lbl_harita_altlik.config(text=f"Seçili: {tile_name}", foreground=COLOR_SUCCESS)

        records = jeoloji_birimleri(getattr(self, "veri", {}))
        if hasattr(self, "lbl_jeoloji_birim_ozet"):
            if records:
                labels = [
                    f"{record.get('kod') or record.get('ad')}"
                    for record in records
                ]
                self.lbl_jeoloji_birim_ozet.config(
                    text=f"{len(records)} birim: {', '.join(labels)}",
                    foreground=COLOR_SUCCESS,
                )
            else:
                suggestion = (
                    self.veri.get("jeoloji", {}).get(
                        "harita_formasyon_onerisi",
                        "",
                    )
                    if isinstance(self.veri.get("jeoloji"), dict)
                    else ""
                )
                text = (
                    f"Henüz seçilmedi · haritadan öneri: {suggestion}"
                    if suggestion
                    else "Henüz seçilmedi"
                )
                self.lbl_jeoloji_birim_ozet.config(
                    text=text,
                    foreground=COLOR_WARNING,
                )

        coord_summary = self.harita_koordinat_ozeti(getattr(self, "veri", {}))
        coord_ready = coord_summary["ready"]
        coord_total = coord_summary["total"]
        coord_all_ready = bool(coord_total and coord_ready == coord_total)
        if hasattr(self, "lbl_harita_koordinat_ozet"):
            self.lbl_harita_koordinat_ozet.config(
                text=f"Koordinatlar: {coord_ready}/{coord_total} hazır",
                foreground=COLOR_SUCCESS if coord_all_ready else COLOR_WARNING,
            )
        for key, label in getattr(self, "harita_coord_labels", {}).items():
            ready, total = coord_summary[key]
            if total == 0:
                text, color = "Kayıt yok", COLOR_TEXT_MUTED
            else:
                text = f"{ready}/{total} hazır"
                color = COLOR_SUCCESS if ready == total else COLOR_WARNING
            label.config(text=text, foreground=color)

        harita_cizimleri = self.veri.get("harita_cizimleri", {}) if isinstance(self.veri, dict) else {}
        drawing_map = (
            (
                "lbl_harita_vaziyet",
                "vaziyet",
                getattr(self, "word_img_sondaj", None) or getattr(self, "word_img_jeofizik", None),
                "Çizim yok",
            ),
            ("lbl_harita_jeoloji", "jeoloji", getattr(self, "img_mjh", None), "Çizim yok"),
            (
                "lbl_harita_yerbuldurur",
                "yerbuldurur",
                getattr(self, "img_yer", None),
                "KML bekliyor" if kml_state != "ok" else "Çizim yok",
            ),
        )
        for attr, key, output_path, empty_text in drawing_map:
            if not hasattr(self, attr):
                continue
            state = harita_cizimleri.get(key, {}) if isinstance(harita_cizimleri.get(key), dict) else {}
            state_path = state.get("img_path")
            if state_path and os.path.isfile(state_path):
                text, color = "Düzenleme kaydı hazır", COLOR_SUCCESS
            elif output_path and os.path.isfile(output_path):
                text = "Rapor çıktısı hazır" if not state else "Rapor çıktısı hazır · altlık eksik"
                color = COLOR_SUCCESS if not state else COLOR_WARNING
            elif state:
                text, color = "Altlık dosyası bulunamadı", COLOR_WARNING
            else:
                text, color = empty_text, COLOR_WARNING
            getattr(self, attr).config(text=text, foreground=color)

        output_paths = self._harita_output_paths()
        output_meta = (
            self.veri.get("harita_cikti_meta", {})
            if isinstance(self.veri.get("harita_cikti_meta"), dict)
            else {}
        )
        output_ready = 0
        output_stale = 0
        for key, label in getattr(self, "harita_output_labels", {}).items():
            path = output_paths.get(key)
            state, text = harita_cikti_durumu(
                self.veri,
                key,
                path,
                output_meta.get(key),
            )
            if state == "ok":
                output_ready += 1
            elif state == "stale":
                output_stale += 1
            label.config(text=text, foreground=status_colors[state])
            if key == "tkgm" and hasattr(self, "lbl_harita_tkgm_ada"):
                self.lbl_harita_tkgm_ada.config(
                    text=text,
                    foreground=status_colors[state],
                )
            card = getattr(self, "harita_output_cards", {}).get(key)
            if card is not None:
                card.config(
                    highlightbackground=(
                        COLOR_SUCCESS
                        if state == "ok"
                        else COLOR_WARNING
                        if state in {"stale", "warning"}
                        else COLOR_BORDER
                    )
                )
            self._harita_cikti_onizleme_yenile(key, path)
        if hasattr(self, "lbl_harita_cikti_ozet"):
            stale_text = f" · Eski: {output_stale}" if output_stale else ""
            self.lbl_harita_cikti_ozet.config(
                text=f"Word için hazır: {output_ready}/{len(output_paths)}{stale_text}",
                foreground=COLOR_SUCCESS if output_ready == len(output_paths) else COLOR_WARNING,
            )

        if hasattr(self, "harita_durum_var"):
            kml_summary = "KML hazır" if kml_state == "ok" else "KML eksik"
            self.harita_durum_var.set(
                f"{kml_summary} · Koordinatlar {coord_ready}/{coord_total} · Rapor çıktıları {output_ready}/{len(output_paths)}"
            )
            self.lbl_harita_durum.configure(
                foreground=COLOR_SUCCESS
                if kml_state == "ok" and coord_all_ready and output_ready == len(output_paths)
                else COLOR_WARNING
            )

    def harita_toplu_yenile(self):
        self.guncelle_veri_objesi()
        paths = self._harita_output_paths()
        meta = (
            self.veri.get("harita_cikti_meta", {})
            if isinstance(self.veri.get("harita_cikti_meta"), dict)
            else {}
        )
        states = {
            key: harita_cikti_durumu(self.veri, key, paths.get(key), meta.get(key))[0]
            for key in HARITA_CIKTI_ANAHTARLARI
        }
        steps = []
        if states["sondaj"] != "ok" or states["jeofizik"] != "ok":
            steps.append("vaziyet")
        if states["mjh"] != "ok":
            steps.append("jeoloji")
        if states["yer"] != "ok":
            steps.append("yerbuldurur")
        if states["tkgm"] != "ok":
            steps.append("tkgm")

        if not steps:
            if not messagebox.askyesno(
                "Rapor Haritalarını Yenile",
                "Bütün rapor haritaları güncel görünüyor.\n\n"
                "Yine de tamamını yeniden oluşturmak ister misiniz?",
            ):
                return
            steps = ["vaziyet", "jeoloji", "yerbuldurur", "tkgm"]

        if getattr(self, "_harita_yenileme_aktif", False):
            self.bildirim_goster(
                "Harita yenileme akışı zaten devam ediyor.",
                level="warning",
                title="Rapor Haritaları",
            )
            return

        self._harita_yenileme_aktif = True
        self._harita_yenileme_kuyrugu = list(steps)
        self._harita_yenileme_current = None
        self._harita_yenileme_tamamlanan = 0
        self._harita_yenileme_toplam = len(steps)
        self.set_status(
            f"Harita yenileme başladı: {len(steps)} adım.",
            level="info",
        )
        self._harita_toplu_sonraki()

    def _harita_toplu_sonraki(self):
        if not getattr(self, "_harita_yenileme_aktif", False):
            return
        if getattr(self, "_harita_yenileme_current", None):
            return
        queue = getattr(self, "_harita_yenileme_kuyrugu", [])
        if not queue:
            completed = getattr(self, "_harita_yenileme_tamamlanan", 0)
            total = getattr(self, "_harita_yenileme_toplam", completed)
            self._harita_yenileme_aktif = False
            self.harita_durum_yenile()
            self.set_status(
                f"Harita yenileme tamamlandı: {completed}/{total} adım.",
                level="success" if completed == total else "warning",
            )
            self.bildirim_goster(
                f"Harita yenileme akışı tamamlandı. Tamamlanan: {completed}/{total}",
                level="success" if completed == total else "warning",
                title="Rapor Haritaları",
                log=False,
            )
            return

        step = queue.pop(0)
        self._harita_yenileme_current = step
        opened = False
        if step in {"vaziyet", "jeoloji"}:
            opened = bool(self.harita_cizici_ac(step))
        elif step == "yerbuldurur":
            opened = bool(self.yerbuldurur_ac())
        elif step == "tkgm":
            opened = bool(self.tkgm_ada_gorseli_al())
        if not opened:
            self._harita_toplu_adim_bitti(step, success=False)

    def _harita_toplu_adim_bitti(self, step, *, success):
        if not getattr(self, "_harita_yenileme_aktif", False):
            return
        if getattr(self, "_harita_yenileme_current", None) != step:
            return
        if success:
            self._harita_yenileme_tamamlanan = (
                getattr(self, "_harita_yenileme_tamamlanan", 0) + 1
            )
        self._harita_yenileme_current = None
        self.root.after(250, self._harita_toplu_sonraki)

    def _harita_cizici_kapandi(self, harita_tipi, exported):
        if not exported:
            self._harita_toplu_adim_bitti(harita_tipi, success=False)

    def harita_altlik_secildi(self, _event=None):
        self.harita_altlik_kaydet(self.harita_altlik_var.get(), notify=True)

    def harita_altlik_kaydet(self, name, notify=False):
        if name not in TILE_SERVERS:
            name = DEFAULT_TILE_SERVER
        self.veri.setdefault("ayarlar", {})["harita_altlik"] = name
        if hasattr(self, "harita_altlik_var") and self.harita_altlik_var.get() != name:
            self.harita_altlik_var.set(name)
        if hasattr(self, "lbl_harita_altlik"):
            self.lbl_harita_altlik.config(text=f"Seçili: {name}", foreground=COLOR_SUCCESS)
        if notify:
            self.set_status(f"Harita altlığı seçildi: {name}", level="success")

    def tkgm_kml_al(self):
        self.guncelle_veri_objesi()
        kunye = dict(self.veri.get("kunye", {}))
        missing = []
        if not (kunye.get("il") or "").strip():
            missing.append("İl")
        if not (kunye.get("ilce") or "").strip():
            missing.append("İlçe")
        if not (kunye.get("mah") or "").strip():
            missing.append("Mahalle/Köy")
        if not (kunye.get("par") or "").strip():
            missing.append("Parsel")
        if missing:
            messagebox.showwarning(
                "TKGM KML",
                "TKGM'den KML alabilmek için Künye sekmesinde şu alanlar dolu olmalı:\n- "
                + "\n- ".join(missing),
            )
            return

        output_dir = self._tkgm_kml_output_dir()
        progress = tk.Toplevel(self.root)
        self.pencere_hazirla(progress, "TKGM KML", "380x130", (360, 120), modal=False)
        ttk.Label(progress, text="TKGM Parsel Sorgu'dan KML alınıyor...", font=FONT_BOLD).pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(progress, text=f"{kunye.get('il', '')} / {kunye.get('ilce', '')} / {kunye.get('mah', '')}", foreground="#555555").pack(anchor="w", padx=14, pady=(0, 8))
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=14, pady=(0, 12))
        bar.start(12)

        def worker():
            return tkgm_parsel_kml_olustur(kunye, output_dir)

        def success(result):
            if progress.winfo_exists():
                progress.destroy()
            self._tkgm_kml_sonuc_isle(result)

        def error(exc):
            if progress.winfo_exists():
                progress.destroy()
            messagebox.showerror("TKGM KML", f"KML alınamadı:\n{exc}")

        self.arka_plan_gorevi_baslat(
            "TKGM KML al",
            worker,
            status_start="TKGM KML alınıyor.",
            status_success="TKGM KML alındı.",
            status_error="TKGM KML alınamadı: {error}",
            on_success=success,
            on_error=error,
        )

    def _tkgm_kml_output_dir(self):
        active_path = getattr(self, "aktif_dosya_yolu", None)
        if active_path:
            return os.path.join(os.path.dirname(active_path), "03_Haritalar")
        return str(kullanici_yolu("TKGM_KML"))

    def _tkgm_kml_sonuc_isle(self, result):
        path = result.get("path")
        if not path:
            messagebox.showerror("TKGM KML", "TKGM KML dosya yolu oluşturulamadı.")
            return

        self.kml_path = path
        self.veri.setdefault("dosyalar", {})["kml_path"] = path

        center = result.get("center")
        if center and hasattr(self, "e_arazi"):
            lat, lon = center
            for key, value in (("alan_y", lat), ("alan_x", lon)):
                entry = self.e_arazi.get(key)
                if entry is not None and not entry.get().strip():
                    entry.delete(0, tk.END)
                    entry.insert(0, f"{value:.8f}")
                    self.veri.setdefault("arazi", {})[key] = f"{value:.8f}"

        self.kml_etiket_guncelle()
        self.harita_durum_yenile()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        if hasattr(self, "otomatik_kaydet"):
            self.otomatik_kaydet()
        self.set_status(f"TKGM KML bağlandı: {os.path.basename(path)}", level="success")
        self.bildirim_goster(
            f"KML oluşturuldu ve projeye bağlandı: {os.path.basename(path)}",
            level="success",
            title="TKGM KML",
            log=False,
        )

    def tkgm_ada_gorseli_al(self):
        self.guncelle_veri_objesi()
        kunye = dict(self.veri.get("kunye", {}))
        required = (
            ("il", "İl"),
            ("ilce", "İlçe"),
            ("mah", "Mahalle/Köy"),
            ("ada", "Ada"),
            ("par", "Parsel"),
        )
        missing = [label for key, label in required if not str(kunye.get(key) or "").strip()]
        if missing:
            messagebox.showwarning(
                "TKGM Ada Görseli",
                "Ada görseli oluşturmak için Künye sekmesinde şu alanlar dolu olmalı:\n- "
                + "\n- ".join(missing),
            )
            return False

        tile_name = self.harita_altlik_var.get() if hasattr(self, "harita_altlik_var") else DEFAULT_TILE_SERVER
        if tile_name not in TILE_SERVERS:
            tile_name = DEFAULT_TILE_SERVER
        self.harita_altlik_kaydet(tile_name)
        tile_provider = dict(TILE_SERVERS[tile_name])
        fallback_provider = dict(TILE_SERVERS[DEFAULT_TILE_SERVER])
        output_dir = self._tkgm_kml_output_dir()

        progress = tk.Toplevel(self.root)
        self.pencere_hazirla(progress, "TKGM Ada Görseli", "430x150", (400, 135), modal=False)
        ttk.Label(
            progress,
            text=f"{kunye.get('ada', '')} adasındaki parseller hazırlanıyor...",
            font=FONT_BOLD,
        ).pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(
            progress,
            text="Komşu parseller bulunuyor ve uydu görüntüsü çiziliyor.",
            foreground="#555555",
        ).pack(anchor="w", padx=14, pady=(0, 8))
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=14, pady=(0, 12))
        bar.start(12)

        def worker():
            return tkgm_ada_gorseli_olustur(
                kunye,
                output_dir,
                tile_provider,
                tile_name=tile_name,
                fallback_tile_provider=fallback_provider,
            )

        def success(result):
            if progress.winfo_exists():
                progress.destroy()
            path = result.get("path")
            if not path or not os.path.isfile(path):
                messagebox.showerror("TKGM Ada Görseli", "Ada görseli dosyası oluşturulamadı.")
                self._harita_toplu_adim_bitti("tkgm", success=False)
                return
            self.img_tkgm = path
            self.veri.setdefault("dosyalar", {})["img_tkgm"] = path
            self._harita_cikti_meta_kaydet("tkgm", path)
            if hasattr(self, "lbl_tkgm"):
                self.lbl_tkgm.config(text=os.path.basename(path), foreground=COLOR_SUCCESS)
            self.harita_durum_yenile()
            if hasattr(self, "rapor_etiketlerini_guncelle"):
                self.rapor_etiketlerini_guncelle()
            if hasattr(self, "ozet_yenile"):
                self.ozet_yenile(collect=False)
            if hasattr(self, "otomatik_kaydet"):
                self.otomatik_kaydet()
            source_text = (
                "TKGM parsel listesi"
                if result.get("source") == "parsel_listesi"
                else "geometrik komşuluk taraması"
            )
            fallback_text = "\nHGM altlığı alınamadığı için Google Uydu kullanıldı." if result.get("fallback_used") else ""
            limit_text = "\nParsel güvenlik sınırına ulaşıldı; görseli kontrol edin." if result.get("limit_reached") else ""
            self.set_status(
                f"TKGM ada görseli hazır: {result.get('parcel_count', 0)} parsel",
                level="success",
            )
            notice_level = "warning" if fallback_text or limit_text else "success"
            notice_extra = " Görseli kontrol edin." if notice_level == "warning" else ""
            self.bildirim_goster(
                f"{result.get('ada', '')} adasında {result.get('parcel_count', 0)} parsel çizildi. "
                f"Kaynak: {source_text}. RESIM:TKGM etiketine bağlandı.{notice_extra}",
                level=notice_level,
                title="TKGM Ada Görseli",
                duration=8000,
                log=False,
            )
            self._harita_toplu_adim_bitti("tkgm", success=True)

        def error(exc):
            if progress.winfo_exists():
                progress.destroy()
            messagebox.showerror(
                "TKGM Ada Görseli",
                "Ada görseli oluşturulamadı.\n\n"
                f"{exc}\n\n"
                "TKGM servisi geçici olarak yoğun ise kısa bir süre sonra yeniden deneyebilirsiniz.",
            )
            self._harita_toplu_adim_bitti("tkgm", success=False)

        self.arka_plan_gorevi_baslat(
            "TKGM ada görseli",
            worker,
            status_start="TKGM ada parselleri ve uydu görüntüsü hazırlanıyor.",
            status_success="TKGM ada görseli hazırlandı.",
            status_error="TKGM ada görseli hazırlanamadı: {error}",
            on_success=success,
            on_error=error,
        )
        return True

    def harita_cizici_ac(self, harita_tipi):
        with perf_timer("map.image_marker_data_prepare", harita_tipi):
            self.guncelle_veri_objesi()
            map_data = {
                "sondaj": [{"no": s.get("no", ""), "y": s.get("y", "-"), "x": s.get("x", "-")} for s in self.veri["sondaj"]],
                "ss": [
                    {"ad": ss_harita_etiketi(s.get("ad", ""), idx), "coords": s.get("coords", ["-"] * 6)}
                    for idx, s in enumerate(self.veri["jeofizik"]["ss_list"])
                ],
                "mt": [{"no": m.get("no", ""), "y": m.get("y", "-"), "x": m.get("x", "-")} for m in self.veri["jeofizik"]["mt_list"]],
            }
        harita_data = self.veri.get("harita_cizimleri", {}).get(harita_tipi, {})
        img_path = harita_data.get("img_path", "")

        if img_path and os.path.exists(img_path):
            cevap = messagebox.askyesno(
                "Kayıtlı Çizim Bulundu",
                f"Bu proje için daha önceden kaydedilmiş {harita_tipi.upper()} çizimi bulundu.\nKaldığınız yerden devam etmek ister misiniz?",
            )
            if not cevap:
                img_path = filedialog.askopenfilename(title="Yeni Altlık Resmini Seçin", filetypes=[("Resim Dosyaları", "*.jpg;*.png;*.jpeg")])
                harita_data = None
        else:
            img_path = filedialog.askopenfilename(title="Altlık Resmini Seçin", filetypes=[("Resim Dosyaları", "*.jpg;*.png;*.jpeg")])
            harita_data = None

        if img_path:
            formasyon_kod = self.cmb_formasyon.get().split(" ")[0]
            self.harita_altlik_hazirla_ve_ac(harita_tipi, img_path, map_data, formasyon_kod, harita_data)
            return True
        return False

    def harita_altlik_hazirla_ve_ac(self, harita_tipi, img_path, map_data, formasyon_kod, harita_data):
        progress = tk.Toplevel(self.root)
        self.pencere_hazirla(progress, "Harita Altlığı", "360x120", (340, 110), modal=False)
        ttk.Label(progress, text="Harita altlığı hazırlanıyor...", font=FONT_BOLD).pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(progress, text=os.path.basename(img_path), foreground="#555555").pack(anchor="w", padx=14, pady=(0, 8))
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=14, pady=(0, 12))
        bar.start(12)

        def worker():
            display_image_read(img_path)
            with perf_timer("map.kml_reference_read", os.path.basename(str(getattr(self, "kml_path", "") or ""))):
                return kml_koordinatlari_oku(getattr(self, "kml_path", None))

        def open_marker(kml_points):
            if progress.winfo_exists():
                progress.destroy()
            with perf_timer("map.image_marker_window_open", harita_tipi):
                ResimIsaretleyici(
                    self.root,
                    img_path=img_path,
                    map_data=map_data,
                    harita_tipi=harita_tipi,
                    formasyon=formasyon_kod,
                    kml_points=kml_points,
                    word_callback=self.harita_word_aktar,
                    save_callback=lambda data: self.harita_cizim_kaydet(harita_tipi, data),
                    saved_state=harita_data,
                    layer_settings=self.harita_katman_ayarlarini_al(),
                    close_callback=lambda exported: self._harita_cizici_kapandi(
                        harita_tipi,
                        exported,
                    ),
                )

        def show_error(exc):
            if progress.winfo_exists():
                progress.destroy()
            messagebox.showerror("Harita Altlığı", f"Harita altlığı hazırlanamadı:\n{exc}")
            self._harita_toplu_adim_bitti(harita_tipi, success=False)

        self.arka_plan_gorevi_baslat(
            "Harita altlığı hazırla",
            worker,
            status_start="Harita altlığı arka planda hazırlanıyor.",
            status_success="Harita altlığı hazırlandı.",
            status_error="Harita altlığı hazırlanamadı: {error}",
            on_success=open_marker,
            on_error=show_error,
        )

    def harita_cizim_kaydet(self, harita_tipi, data):
        if "harita_cizimleri" not in self.veri:
            self.veri["harita_cizimleri"] = {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}}
        self.veri["harita_cizimleri"][harita_tipi] = data
        if harita_tipi == "jeoloji" and isinstance(data, dict):
            code = str(data.get("formasyon") or "").strip()
            if code in JEOLOJI_BIRIM_KATALOGU:
                self.veri.setdefault("ayarlar", {})["harita_formasyon"] = code
        visibility = data.get("visibility", {}) if isinstance(data, dict) else {}
        if isinstance(visibility, dict):
            layers = harita_katman_ayarlari(visibility)
            self.veri.setdefault("ayarlar", {})["harita_katmanlari"] = layers
            shared_visibility = dict(layers)
            shared_visibility["jeofizik"] = layers["ss"] and layers["mt"]
            for drawing_key in ("vaziyet", "jeoloji"):
                drawing = self.veri["harita_cizimleri"].get(drawing_key)
                if isinstance(drawing, dict) and drawing:
                    drawing["visibility"] = dict(shared_visibility)
            for key, variable in getattr(self, "harita_layer_vars", {}).items():
                variable.set(layers[key])
        self.harita_durum_yenile()
        self.veri_kaydet()
        self.set_status(f"{harita_tipi.upper()} çizim verileri projeye kaydedildi.", level="success")

    def harita_word_aktar(self, path_son=None, path_jeo=None, path_mjh=None, harita_tipi="vaziyet"):
        dosyalar = self.veri.setdefault("dosyalar", {})
        if path_mjh:
            self.img_mjh = path_mjh
            dosyalar["img_mjh"] = path_mjh
            self._harita_cikti_meta_kaydet("mjh", path_mjh)
            if hasattr(self, "lbl_mjh"):
                self.lbl_mjh.config(text=os.path.basename(path_mjh), foreground=COLOR_SUCCESS)
            self.harita_durum_yenile()
            self.veri_kaydet()
            self.set_status("Mühendislik jeolojisi haritası RESIM:MJH için hafızaya alındı.", level="success")
            self._harita_toplu_adim_bitti("jeoloji", success=True)
            return
        if path_son:
            self.word_img_sondaj = path_son
            dosyalar["word_img_sondaj"] = path_son
            self._harita_cikti_meta_kaydet("sondaj", path_son)
        if path_jeo:
            self.word_img_jeofizik = path_jeo
            dosyalar["word_img_jeofizik"] = path_jeo
            self._harita_cikti_meta_kaydet("jeofizik", path_jeo)
        self.harita_durum_yenile()
        self.veri_kaydet()
        self.set_status("Sondaj ve Jeofizik haritaları Word raporu için hafızaya alındı.", level="success")
        self._harita_toplu_adim_bitti("vaziyet", success=True)

    @perf_tracked("map.yerbuldurur_open")
    def yerbuldurur_ac(self):
        if not self.kml_path or not os.path.exists(self.kml_path):
            messagebox.showerror("Hata", "Lütfen önce üst menüden bir KML Sınır Dosyası seçin!")
            return False

        harita_data = self.veri.get("harita_cizimleri", {}).get("yerbuldurur", {})
        YerbuldururMotoru(
            self.root,
            kml_path=self.kml_path,
            saved_state=harita_data,
            save_callback=self.yerbuldurur_kaydet,
            close_callback=lambda exported: (
                None
                if exported
                else self._harita_toplu_adim_bitti("yerbuldurur", success=False)
            ),
        )
        return True

    def yerbuldurur_kaydet(self, state, img_path):
        if "harita_cizimleri" not in self.veri:
            self.veri["harita_cizimleri"] = {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}}
        self.veri["harita_cizimleri"]["yerbuldurur"] = state
        self.img_yer = img_path
        self.veri.setdefault("dosyalar", {})["img_yer"] = img_path
        self._harita_cikti_meta_kaydet("yer", img_path)
        if hasattr(self, "lbl_yer"):
            self.lbl_yer.config(text=os.path.basename(img_path), foreground=COLOR_SUCCESS)
        self.harita_durum_yenile()
        self.veri_kaydet()
        self.set_status("Yerbuldurur haritası projeye kaydedildi ve Rapor sekmesine aktarıldı.", level="success")
        self._harita_toplu_adim_bitti("yerbuldurur", success=True)
