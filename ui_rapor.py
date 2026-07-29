# Dosya: RaporPro/ui_rapor.py
import copy
import os
import tempfile
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

import matplotlib.pyplot as plt

from ai_motoru import AI_MOTOR_ADLARI, belediye_duzeltme_analiz_et, duzeltme_yonlendirmeleri_olustur
from cikti_kalite import cikti_dosyalari_denetle, kalite_manifestosu_yaz
from jeofizik_sheet_motoru import jeofizik_sheet_rapora_hazir_mi
from rapor_metin_revizyon import metin_revizyon_analiz_et, metin_revizyonlari_uygula
from rapor_revizyon import revizyonlu_rapor_olustur
from rapor_sablonu import etkin_rapor_sablonu_yolu, rapor_sablonu_durumu
from sabitler import (
    COLOR_BG,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    DEFAULT_EXPORT_DPI,
    FONT_BOLD,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    FONT_UI_SECTION,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from performans import perf_tracked
from kalite_kontrol import build_preflight_report
from motor import GeoEngine
from rapor_etiketleri import DUZELTME_ETIKET_GRUPLARI
from raporlama import (
    duzeltme_etiket_ciktisi_olustur,
    rapor_baglami_olustur,
    raporla as rapor_olustur,
)
from taahhutname import taahhutname_dosya_adi, taahhutname_olustur, tum_taahhutnameleri_olustur
from tutanaklar import tutanak_dosya_adi, tutanaklari_olustur
from ekler import (
    EK_SET_ARAZI_DENEYLI,
    EK_SET_LABELS,
    EK_SET_NORMAL,
    ek_basliklari,
    ek_icerik_haritasi,
    ek_pdf_dosya_adi,
    ek_sablon_yollari,
    ekler_pdf_olustur,
    uygun_ek_sablonu,
    uygun_ek_seti,
)
from yonetmelik_motoru import (
    YONETMELIK_DIR,
    duzeltme_yonetmelik_dayanaklari,
    resmi_yonetmelik_indir_ve_ekle,
    resmi_yonetmelik_kaynaklari,
    yonetmelik_ara,
    yonetmelik_ekle,
    yonetmelik_sil,
    yonetmelikleri_listele,
)
from ui_rapor_onizleme import RaporOnizlemeMixin


class RaporSekmesiMixin(RaporOnizlemeMixin):
    def dis_ai_veri_aktarim_onayi(self, motor, veri_turu, parent=None):
        """Dış AI kullanımında sağlayıcı ve gönderilecek veriyi bir kez açıkla."""
        selected = str(motor or "otomatik").strip().lower()
        if selected == "kural":
            return True
        provider = selected
        if provider == "otomatik":
            try:
                from spt_okuma_motoru import spt_ayarlarini_yukle

                provider = str(
                    spt_ayarlarini_yukle().get("aktif_motor") or "openai"
                ).strip().lower()
            except Exception:
                provider = "ayarlarınızda seçili dış sağlayıcı"
        provider_labels = {
            "openai": "OpenAI",
            "gemini": "Google Gemini",
            "gemini_pro": "Google Gemini",
            "groq": "Groq",
        }
        provider_label = provider_labels.get(provider, provider)
        approval_key = (provider, str(veri_turu))
        approvals = getattr(self, "_dis_ai_veri_onaylari", set())
        if approval_key in approvals:
            return True
        approved = messagebox.askyesno(
            "Dış Yapay Zekâ Veri Aktarımı",
            f"Bu işlem {veri_turu} verisini {provider_label} servisine gönderecek.\n\n"
            "Proje/istemci gizliliği açısından gönderme yetkiniz olduğunu doğrulayın. "
            "Veriyi dışarı göndermeden çalışmak için motor olarak 'kural' seçebilirsiniz.\n\n"
            "Devam edilsin mi?",
            parent=parent,
        )
        if approved:
            approvals = set(approvals)
            approvals.add(approval_key)
            self._dis_ai_veri_onaylari = approvals
        return bool(approved)

    @staticmethod
    def rapor_hazirlik_ozeti(template_ready, lab_ready, jeo_ready, visual_ready, visual_total=6):
        """Rapor kaynaklarının kısa durum metnini ve seviyesini döndür."""
        source_ready = sum(bool(value) for value in (template_ready, lab_ready, jeo_ready))
        visual_ready = max(0, min(int(visual_ready or 0), int(visual_total or 0)))
        missing = []
        if not template_ready:
            missing.append("şablon")
        if not lab_ready:
            missing.append("laboratuvar")
        if not jeo_ready:
            missing.append("jeofizik")
        if visual_ready < visual_total:
            missing.append(f"{visual_total - visual_ready} görsel")
        if missing:
            return "warning", f"Kaynaklar {source_ready}/3 · Görseller {visual_ready}/{visual_total} · Eksik: {', '.join(missing)}"
        return "ok", f"Rapor kaynakları hazır · Görseller {visual_ready}/{visual_total}"

    def rapor_durum_guncelle(self):
        def file_ready(path):
            return bool(path and os.path.isfile(path))

        template_ready = bool(rapor_sablonu_durumu(getattr(self, "word_path", None)).get("ready"))
        lab_rows = self.veri.get("lab_sheet", {}).get("rows", []) if isinstance(getattr(self, "veri", None), dict) else []
        lab_sheet_ready = any(any(str(cell).strip() for cell in row) for row in lab_rows or [])
        lab_ready = lab_sheet_ready or file_ready(getattr(self, "lab_excel_path", None))
        jeo_sheet_ready = jeofizik_sheet_rapora_hazir_mi(getattr(self, "veri", {}))
        jeo_ready = jeo_sheet_ready or file_ready(getattr(self, "jeo_excel_path", None))
        visual_attrs = ("img_yer", "img_tkgm", "img_pga", "img_mjh", "word_img_sondaj", "word_img_jeofizik")
        visual_ready = sum(file_ready(getattr(self, attr, None)) for attr in visual_attrs)
        state, text = self.rapor_hazirlik_ozeti(
            template_ready,
            lab_ready,
            jeo_ready,
            visual_ready,
            len(visual_attrs),
        )
        if hasattr(self, "rapor_durum_var"):
            self.rapor_durum_var.set(text)
            self.rapor_durum_label.configure(foreground=COLOR_SUCCESS if state == "ok" else COLOR_WARNING)
        if hasattr(self, "rapor_gorsel_ozet_var"):
            self.rapor_gorsel_ozet_var.set(f"{visual_ready}/{len(visual_attrs)} görsel hazır")
        if hasattr(self, "lbl_sondaj_haritasi"):
            path = getattr(self, "word_img_sondaj", None)
            self.lbl_sondaj_haritasi.config(
                text=os.path.basename(path) if file_ready(path) else ("Dosya bulunamadı" if path else "Hazırlanmadı"),
                foreground=COLOR_SUCCESS if file_ready(path) else COLOR_WARNING,
            )
        if hasattr(self, "lbl_jeofizik_haritasi"):
            path = getattr(self, "word_img_jeofizik", None)
            self.lbl_jeofizik_haritasi.config(
                text=os.path.basename(path) if file_ready(path) else ("Dosya bulunamadı" if path else "Hazırlanmadı"),
                foreground=COLOR_SUCCESS if file_ready(path) else COLOR_WARNING,
            )

    def rapor_etiketlerini_guncelle(self):
        self.rapor_sablon_etiketini_guncelle()
        if hasattr(self, "_lab_label_guncelle"):
            self._lab_label_guncelle()
        elif hasattr(self, "lbl_lab"):
            path = getattr(self, "lab_excel_path", None)
            self.lbl_lab.config(
                text=os.path.basename(path) if path else "Laboratuvar verisi seçilmedi",
                foreground=COLOR_SUCCESS if path else COLOR_DANGER,
            )
        if hasattr(self, "_jeofizik_label_guncelle"):
            self._jeofizik_label_guncelle()
        elif hasattr(self, "lbl_jeo_excel"):
            path = getattr(self, "jeo_excel_path", None)
            self.lbl_jeo_excel.config(
                text=os.path.basename(path) if path else "Jeofizik verisi seçilmedi",
                foreground=COLOR_SUCCESS if path else COLOR_DANGER,
            )
        for attr, path in (
            ("lbl_yer", getattr(self, "img_yer", None)),
            ("lbl_tkgm", getattr(self, "img_tkgm", None)),
            ("lbl_pga", getattr(self, "img_pga", None)),
            ("lbl_mjh", getattr(self, "img_mjh", None)),
        ):
            if hasattr(self, attr):
                ready = bool(path and os.path.isfile(path))
                getattr(self, attr).config(
                    text=os.path.basename(path) if ready else ("Dosya bulunamadı" if path else "Seçilmedi"),
                    foreground=COLOR_SUCCESS if ready else COLOR_WARNING,
                )
        self.ek_etiketlerini_guncelle()
        self.rapor_durum_guncelle()

    def rapor_sablon_etiketini_guncelle(self):
        """Etkin rapor şablonunu arayüzde kaynak türüyle birlikte göster."""
        info = rapor_sablonu_durumu(getattr(self, "word_path", None))
        if hasattr(self, "lbl_sab"):
            text = info.get("label", "Dahili şablon bulunamadı")
            if info.get("fallback"):
                text += " (özel dosya bulunamadı)"
            color = COLOR_WARNING if info.get("fallback") else (COLOR_SUCCESS if info.get("ready") else "red")
            self.lbl_sab.config(text=text, foreground=color)
        if hasattr(self, "rapor_durum_var"):
            self.rapor_durum_guncelle()
        return info

    def dahili_rapor_sablonunu_kullan(self):
        """Projedeki özel şablon seçimini kaldırıp dahili şablona dön."""
        self.word_path = None
        self.veri.setdefault("dosyalar", {})["word_path"] = None
        self.veri.setdefault("ayarlar", {})["varsayilan_word_path"] = ""
        info = self.rapor_sablon_etiketini_guncelle()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        if info.get("ready"):
            self.set_status("Dahili rapor şablonu kullanılacak.", level="success")
        else:
            self.set_status("Dahili rapor şablonu bulunamadı.", level="error")
        self.rapor_etiketlerini_guncelle()

    def p_rapor(self, p):
        page = ttk.Frame(p, padding=(16, 12))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        file_labels = []
        drop_targets = []

        def source_row(parent, title, label_attr, empty_text, buttons):
            row = tk.Frame(
                parent,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_MD,
                pady=SPACE_SM,
            )
            row.pack(fill="x", pady=(0, SPACE_XS))
            row.columnconfigure(1, weight=1)
            tk.Label(
                row,
                text=title,
                bg=COLOR_SURFACE,
                fg=COLOR_PRIMARY,
                font=FONT_UI_BODY_BOLD,
                width=18,
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(0, SPACE_SM))
            label = tk.Label(
                row,
                text=empty_text,
                bg=COLOR_SURFACE,
                fg=COLOR_WARNING,
                font=FONT_UI_BODY,
                anchor="w",
                justify="left",
            )
            label.grid(row=0, column=1, sticky="ew", padx=(0, SPACE_SM))
            file_labels.append(label)
            setattr(self, label_attr, label)
            action_frame = tk.Frame(row, bg=COLOR_SURFACE)
            action_frame.grid(row=0, column=2, sticky="e")
            for text, command, role, outline in buttons:
                self.modern_button(
                    action_frame,
                    text,
                    command=command,
                    role=role,
                    outline=outline,
                    padx=7,
                    pady=4,
                ).pack(side="left", padx=2)
            return row

        def report_tab_select(tab):
            self.rapor_main_notebook.select(tab)

        def assign_dropped_file(path):
            if not path or not os.path.exists(path):
                return None
            name = os.path.basename(path)
            lower_name = name.lower()
            ext = os.path.splitext(path)[1].lower()
            if ext in (".doc", ".pdf") or (ext == ".docx" and any(key in lower_name for key in ("ek", "tutanak", "arazi", "deney"))):
                ayarlar = self.veri.setdefault("ayarlar", {})
                if "arazi" in lower_name or "deney" in lower_name:
                    ayarlar["ek_arazi_deneyli_path"] = path
                    self.ek_arazi_deneyli_path = path
                    return f"Arazi deneyli ek: {name}"
                ayarlar["ek_tutanak_path"] = path
                self.ek_tutanak_path = path
                return f"Normal ek: {name}"
            if ext == ".docx":
                self.word_path = path
                return f"Word şablonu: {name}"
            if ext in (".xlsx", ".xls", ".csv"):
                if any(key in lower_name for key in ("jeo", "jeofizik", "mt", "ss")):
                    self.jeo_excel_path = path
                    return f"Jeofizik Excel: {name}"
                self.lab_excel_path = path
                return f"Lab Excel: {name}"
            if ext in (".jpg", ".jpeg", ".png"):
                image_slots = [
                    ("yer", "img_yer", ("yer", "yerbuldurur", "lokasyon")),
                    ("tkgm", "img_tkgm", ("tkgm", "tapu", "kadastro", "parsel")),
                    ("pga", "img_pga", ("pga", "deprem")),
                    ("mjh", "img_mjh", ("mjh", "jeoloji", "muhendislik")),
                ]
                for _, attr, keywords in image_slots:
                    if any(key in lower_name for key in keywords):
                        setattr(self, attr, path)
                        return f"Görsel: {name}"
                for _, attr, _ in image_slots:
                    if not getattr(self, attr, None):
                        setattr(self, attr, path)
                        return f"Görsel: {name}"
                self.img_mjh = path
                return f"Görsel: {name}"
            return None

        def parse_drop_paths(data):
            try:
                return [item for item in self.root.tk.splitlist(data) if item]
            except Exception:
                return [item for item in str(data or "").split() if item]

        def on_report_drop(event):
            messages = []
            for path in parse_drop_paths(getattr(event, "data", "")):
                message = assign_dropped_file(path)
                if message:
                    messages.append(message)
            self.rapor_etiketlerini_guncelle()
            if messages:
                self.set_status("Rapor dosyaları eklendi: " + ", ".join(messages[:4]), level="success")
            else:
                self.set_status("Sürükle-bırak: desteklenen dosya bulunamadı.", level="warning")
            return "break"

        def enable_report_drop():
            try:
                from tkinterdnd2 import DND_FILES
            except Exception:
                if hasattr(self, "lbl_rapor_drop"):
                    self.lbl_rapor_drop.config(text="Sürükle-bırak için tkinterdnd2 gerekir", foreground="#777777")
                return
            enabled = False
            for target in drop_targets:
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", on_report_drop)
                    enabled = True
                except Exception:
                    continue
            if enabled:
                self.lbl_rapor_drop.config(text="Sürükle-bırak etkin", foreground=COLOR_SUCCESS)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Rapor ve Belgeler", style="PageTitle.TLabel").pack(anchor="w")
        self.rapor_durum_var = tk.StringVar(value="Rapor kaynakları kontrol ediliyor")
        self.rapor_durum_label = ttk.Label(title_area, textvariable=self.rapor_durum_var, style="Muted.TLabel")
        self.rapor_durum_label.pack(anchor="w", pady=(2, 0))
        self.lbl_rapor_drop = ttk.Label(header, text="", style="Muted.TLabel")
        self.lbl_rapor_drop.grid(row=0, column=1, sticky="e")
        ttk.Separator(page).grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))

        self.rapor_main_notebook = ttk.Notebook(page)
        self.rapor_main_notebook.grid(row=2, column=0, sticky="nsew")
        self.rapor_hazirlik_tab = ttk.Frame(self.rapor_main_notebook)
        self.rapor_belgeler_tab = ttk.Frame(self.rapor_main_notebook)
        self.rapor_ekler_tab = ttk.Frame(self.rapor_main_notebook)
        self.rapor_main_notebook.add(self.rapor_hazirlik_tab, text="Rapor Hazırlığı")
        self.rapor_main_notebook.add(self.rapor_belgeler_tab, text="Belgeler")
        self.rapor_main_notebook.add(self.rapor_ekler_tab, text="Ekler")

        preparation, _ = self.scrollable_page(self.rapor_hazirlik_tab, padding=(10, 8))
        preparation.columnconfigure(0, weight=1)
        source_box = ttk.LabelFrame(preparation, text="Veri Kaynakları", padding=(10, 8))
        source_box.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        drop_targets.extend([page, source_box, self.rapor_hazirlik_tab])
        source_row(
            source_box,
            "Rapor şablonu",
            "lbl_sab",
            "Dahili şablon hazırlanıyor",
            [
                ("Özel Seç", self.sablon_sec, "secondary", True),
                ("Dahili Kullan", self.dahili_rapor_sablonunu_kullan, "accent", True),
            ],
        )
        source_row(
            source_box,
            "Laboratuvar",
            "lbl_lab",
            "Laboratuvar verisi seçilmedi",
            [
                ("Excel Seç", self.lab_excel_sec, "secondary", True),
                ("LAB Sheet", self.lab_sheet_ac, "accent", True),
            ],
        )
        source_row(
            source_box,
            "Jeofizik",
            "lbl_jeo_excel",
            "Jeofizik verisi seçilmedi",
            [
                ("Excel Seç", self.jeo_excel_sec, "secondary", True),
                ("Jeofizik Sheet", self.jeofizik_sheet_ac, "accent", True),
            ],
        )

        visuals = ttk.LabelFrame(preparation, text="Rapor Görselleri", padding=(10, 8))
        visuals.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        drop_targets.append(visuals)
        visual_header = ttk.Frame(visuals)
        visual_header.pack(fill="x", pady=(0, SPACE_XS))
        self.rapor_gorsel_ozet_var = tk.StringVar(value="0/6 görsel hazır")
        ttk.Label(visual_header, textvariable=self.rapor_gorsel_ozet_var, style="Muted.TLabel").pack(side="right")
        visual_grid = ttk.Frame(visuals)
        visual_grid.pack(fill="x")
        image_cards = []

        def visual_card(title, label_attr, command, button_text="Seç"):
            card = tk.Frame(
                visual_grid,
                bg=COLOR_SURFACE,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                padx=SPACE_SM,
                pady=SPACE_SM,
            )
            tk.Label(card, text=title, bg=COLOR_SURFACE, fg=COLOR_PRIMARY, font=FONT_UI_BODY_BOLD).pack(anchor="w")
            label = tk.Label(
                card,
                text="Seçilmedi",
                bg=COLOR_SURFACE,
                fg=COLOR_WARNING,
                font=FONT_UI_BODY,
                anchor="w",
            )
            label.pack(fill="x", pady=(2, SPACE_XS))
            setattr(self, label_attr, label)
            file_labels.append(label)
            self.modern_button(
                card,
                button_text,
                command=command,
                role="secondary",
                outline=True,
                padx=6,
                pady=3,
            ).pack(fill="x")
            image_cards.append(card)

        visual_card("Yerbuldurur", "lbl_yer", lambda: self.resim_sec("yer"))
        visual_card("TKGM", "lbl_tkgm", lambda: self.resim_sec("tkgm"))
        visual_card("PGA", "lbl_pga", lambda: self.resim_sec("pga"))
        visual_card("Mühendislik Jeolojisi", "lbl_mjh", lambda: self.resim_sec("mjh"))
        visual_card(
            "Sondaj Haritası",
            "lbl_sondaj_haritasi",
            lambda: self.nb.select(self.tab_haritalar),
            "Haritalara Git",
        )
        visual_card(
            "Jeofizik Haritası",
            "lbl_jeofizik_haritasi",
            lambda: self.nb.select(self.tab_haritalar),
            "Haritalara Git",
        )
        self.responsive_widget_grid(visual_grid, image_cards, min_width=210, max_cols=3, padx=4, pady=4)

        report_actions = ttk.LabelFrame(preparation, text="Rapor İşlemleri", padding=(10, 8))
        report_actions.grid(row=2, column=0, sticky="ew")
        primary_actions = ttk.Frame(report_actions)
        primary_actions.pack(fill="x")
        self.modern_button(
            primary_actions,
            "Tamamlama Merkezi",
            command=self.tamamlama_merkezi_penceresi,
            role="warning",
            outline=True,
        ).pack(side="left", fill="x", expand=True, padx=(0, SPACE_XS))
        self.modern_button(
            primary_actions,
            "Profesyonel Önizleme",
            command=self.rapor_onizleme_penceresi,
            role="accent",
            outline=True,
        ).pack(side="left", fill="x", expand=True, padx=SPACE_XS)
        self.modern_button(
            primary_actions,
            "Raporu Oluştur",
            command=self.raporla,
            role="success",
        ).pack(side="left", fill="x", expand=True, padx=(SPACE_XS, 0))
        secondary_actions = ttk.Frame(report_actions)
        secondary_actions.pack(fill="x", pady=(SPACE_SM, 0))
        self.modern_button(
            secondary_actions,
            "Rapor Revizyon Merkezi",
            command=self.rapor_revizyon_merkezi_birlesik_penceresi,
            role="primary",
            outline=True,
        ).pack(side="left", fill="x", expand=True, padx=(0, SPACE_XS))
        self.modern_button(
            secondary_actions,
            "Yönetmelik Merkezi",
            command=self.yonetmelik_merkezi_penceresi,
            role="secondary",
            outline=True,
        ).pack(side="left", fill="x", expand=True, padx=SPACE_XS)
        self.toolbar_menu(
            secondary_actions,
            "Diğer İşlemler",
            [
                ("Düzeltme Etiketleri", self.duzeltme_etiketleri_penceresi),
                ("Sadece Grafikleri Çıkar", self.grafikleri_kaydet),
                ("Belgeler Sekmesine Git", lambda: report_tab_select(self.rapor_belgeler_tab)),
                ("Ekler Sekmesine Git", lambda: report_tab_select(self.rapor_ekler_tab)),
            ],
            bg="#ECF0F1",
            fg="#111111",
            role="secondary",
            tooltip="Rapor için ek işlemler",
        )

        documents, _ = self.scrollable_page(self.rapor_belgeler_tab, padding=(10, 8))
        documents.columnconfigure(0, weight=1)
        taahhut = ttk.LabelFrame(documents, text="Taahhütnameler", padding=(12, 10))
        taahhut.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        taahhut.columnconfigure((0, 1, 2), weight=1)
        self.modern_button(
            taahhut,
            "Jeoloji Taahhütnamesi",
            command=lambda: self.taahhutname_kaydet("jeoloji"),
            role="primary",
            outline=True,
        ).grid(row=0, column=0, sticky="ew", padx=(0, SPACE_XS))
        self.modern_button(
            taahhut,
            "Jeofizik Taahhütnamesi",
            command=lambda: self.taahhutname_kaydet("jeofizik"),
            role="accent",
            outline=True,
        ).grid(row=0, column=1, sticky="ew", padx=SPACE_XS)
        self.modern_button(
            taahhut,
            "İkisini Oluştur",
            command=self.taahhutnameleri_kaydet,
            role="success",
        ).grid(row=0, column=2, sticky="ew", padx=(SPACE_XS, 0))

        tutanak = ttk.LabelFrame(documents, text="Sondaj Tutanakları", padding=(12, 10))
        tutanak.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        self.modern_button(
            tutanak,
            "Tutanakları Oluştur",
            command=self.tutanaklari_kaydet,
            role="warning",
            outline=True,
        ).pack(fill="x")

        revision = ttk.LabelFrame(documents, text="İdare Düzeltmeleri", padding=(12, 10))
        revision.grid(row=2, column=0, sticky="ew")
        revision.columnconfigure((0, 1, 2), weight=1)
        self.modern_button(
            revision,
            "Revizyon Merkezi",
            command=self.rapor_revizyon_merkezi_birlesik_penceresi,
            role="primary",
        ).grid(row=0, column=0, sticky="ew", padx=(0, SPACE_XS))
        self.modern_button(
            revision,
            "Düzeltme Etiketleri",
            command=self.duzeltme_etiketleri_penceresi,
            role="secondary",
            outline=True,
        ).grid(row=0, column=1, sticky="ew", padx=SPACE_XS)
        self.modern_button(
            revision,
            "Yönetmelik Merkezi",
            command=self.yonetmelik_merkezi_penceresi,
            role="secondary",
            outline=True,
        ).grid(row=0, column=2, sticky="ew", padx=(SPACE_XS, 0))

        annexes, _ = self.scrollable_page(self.rapor_ekler_tab, padding=(10, 8))
        annexes.columnconfigure(0, weight=1)
        drop_targets.append(self.rapor_ekler_tab)
        status_box = tk.Frame(
            annexes,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=SPACE_MD,
            pady=SPACE_MD,
        )
        status_box.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        tk.Label(
            status_box,
            text="Ek Dosyalarının Durumu",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
        ).pack(anchor="w")
        self.lbl_ek_durum = tk.Label(
            status_box,
            text="-",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
            justify="left",
            anchor="w",
        )
        self.lbl_ek_durum.pack(fill="x", pady=(3, 0))

        annex_actions = ttk.LabelFrame(annexes, text="Ek İşlemleri", padding=(12, 10))
        annex_actions.grid(row=1, column=0, sticky="ew")
        annex_actions.columnconfigure((0, 1, 2), weight=1)
        self.modern_button(
            annex_actions,
            "Normal Ekler",
            command=lambda: self.ekler_merkezi_penceresi(EK_SET_NORMAL),
            role="primary",
            outline=True,
        ).grid(row=0, column=0, sticky="ew", padx=(0, SPACE_XS))
        self.modern_button(
            annex_actions,
            "Arazi Deneyli Ekler",
            command=lambda: self.ekler_merkezi_penceresi(EK_SET_ARAZI_DENEYLI),
            role="accent",
            outline=True,
        ).grid(row=0, column=1, sticky="ew", padx=SPACE_XS)
        self.modern_button(
            annex_actions,
            "Ekler PDF Oluştur",
            command=self.ekler_pdf_kaydet,
            role="success",
        ).grid(row=0, column=2, sticky="ew", padx=(SPACE_XS, 0))

        self.rapor_etiketlerini_guncelle()
        enable_report_drop()

    @perf_tracked("report.preview")
    def rapor_onizleme_penceresi(self):
        return self.profesyonel_rapor_onizleme_penceresi()

    def sablon_sec(self):
        f = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
        if f:
            self.word_path = f
            self.veri.setdefault("dosyalar", {})["word_path"] = f
            self.rapor_sablon_etiketini_guncelle()
            self.rapor_durum_guncelle()
            self.set_status(f"Özel rapor şablonu seçildi: {os.path.basename(f)}", level="success")

    def lab_excel_sec(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if f:
            self.lab_excel_path = f
            if hasattr(self, "_lab_label_guncelle"):
                self._lab_label_guncelle()
            else:
                self.lbl_lab.config(text=os.path.basename(f), foreground=COLOR_SUCCESS)
            self.rapor_durum_guncelle()

    def jeo_excel_sec(self):
        f = filedialog.askopenfilename(filetypes=[("Excel Dosyaları", "*.xlsx;*.xls;*.csv")])
        if f:
            self.jeo_excel_path = f
            if hasattr(self, "_jeofizik_label_guncelle"):
                self._jeofizik_label_guncelle()
            else:
                self.lbl_jeo_excel.config(text=os.path.basename(f), foreground=COLOR_SUCCESS)
            self.rapor_durum_guncelle()

    def resim_sec(self, tur):
        f = filedialog.askopenfilename(filetypes=[("Resim", "*.jpg;*.png;*.jpeg")])
        if f:
            t = os.path.basename(f)
            if tur == "yer":
                self.img_yer = f
                self.lbl_yer.config(text=t, foreground=COLOR_SUCCESS)
            elif tur == "tkgm":
                self.img_tkgm = f
                self.lbl_tkgm.config(text=t, foreground=COLOR_SUCCESS)
            elif tur == "pga":
                self.img_pga = f
                self.lbl_pga.config(text=t, foreground=COLOR_SUCCESS)
            elif tur == "mjh":
                self.img_mjh = f
                self.lbl_mjh.config(text=t, foreground=COLOR_SUCCESS)
            self.rapor_durum_guncelle()

    def ek_etiketlerini_guncelle(self):
        if not hasattr(self, "lbl_ek_durum"):
            return
        paths = ek_sablon_yollari(self.veri)
        normal_ok = bool(paths["normal"] and os.path.exists(paths["normal"]))
        arazi_ok = bool(paths["arazi_deneyli"] and os.path.exists(paths["arazi_deneyli"]))
        label, source = uygun_ek_sablonu(self.veri)
        set_key = uygun_ek_seti(self.veri)
        file_count = sum(len(paths or []) for paths in ek_icerik_haritasi(self.veri, set_key).values())
        template_state = "şablonlar hazır" if normal_ok and arazi_ok else "şablon eksik"
        self.lbl_ek_durum.config(
            text=f"Otomatik seçim: {label} ({os.path.basename(source) if source else 'dosya yok'}) - {file_count} bağlı dosya - {template_state}",
            foreground=COLOR_SUCCESS if source and os.path.exists(source) else "red",
        )
        if hasattr(self, "rapor_durum_var"):
            self.rapor_durum_guncelle()

    def ek_dosyasi_sec(self, tur):
        f = filedialog.askopenfilename(filetypes=[("Ek Dosyaları", "*.doc;*.docx;*.pdf"), ("Tüm Dosyalar", "*.*")])
        if not f:
            return
        ayarlar = self.veri.setdefault("ayarlar", {})
        if tur == "arazi_deneyli":
            ayarlar["ek_arazi_deneyli_path"] = f
            self.ek_arazi_deneyli_path = f
        else:
            ayarlar["ek_tutanak_path"] = f
            self.ek_tutanak_path = f
        self.ek_etiketlerini_guncelle()
        self.set_status(f"Ek dosyası seçildi: {os.path.basename(f)}", level="success")

    def ekler_merkezi_penceresi(self, set_key=None):
        self.guncelle_veri_objesi(silent=True)
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Ekler Merkezi", "900x600", (760, 520), modal=True)

        initial_set = set_key if set_key in EK_SET_LABELS else uygun_ek_seti(self.veri)
        set_var = tk.StringVar(value=initial_set)
        state = {"items": [], "selected_no": None}

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Ek seti", font=FONT_BOLD).pack(side="left", padx=(0, 10))
        for key, label in ((EK_SET_NORMAL, "Normal Ekler"), (EK_SET_ARAZI_DENEYLI, "Arazi Deneyli Ekler")):
            ttk.Radiobutton(top, text=label, value=key, variable=set_var, command=lambda: refresh_ek_list()).pack(side="left", padx=8)

        panes = ttk.PanedWindow(body, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=(0, 0, 8, 0))
        right = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(left, weight=1)
        panes.add(right, weight=2)

        ttk.Label(left, text="Ek Başlıkları", font=FONT_BOLD).pack(anchor="w", pady=(0, 6))
        ek_list = tk.Listbox(left, exportselection=False, height=18)
        ek_list.pack(fill="both", expand=True)

        selected_label = ttk.Label(right, text="-", font=FONT_BOLD)
        selected_label.pack(anchor="w", pady=(0, 6))
        file_list = tk.Listbox(right, exportselection=False, selectmode="extended", height=16)
        file_list.pack(fill="both", expand=True)

        file_btns = ttk.Frame(right)
        file_btns.pack(fill="x", pady=(8, 0))

        def current_set():
            return set_var.get() if set_var.get() in EK_SET_LABELS else EK_SET_NORMAL

        def current_files(create=True):
            no = state.get("selected_no")
            if not no:
                return []
            data = ek_icerik_haritasi(self.veri, current_set())
            if create:
                return data.setdefault(str(no), [])
            return data.get(str(no), [])

        def selected_item():
            indices = ek_list.curselection()
            if not indices or not state["items"]:
                return None
            idx = indices[0]
            if idx >= len(state["items"]):
                return None
            return state["items"][idx]

        def refresh_files():
            item = selected_item()
            file_list.delete(0, "end")
            if not item:
                selected_label.config(text="-")
                state["selected_no"] = None
                return
            state["selected_no"] = str(item["no"])
            selected_label.config(text=f"EK-{item['no']}  {item.get('title') or ''}")
            for path in current_files(create=True):
                prefix = "" if path and os.path.exists(path) else "! "
                file_list.insert("end", f"{prefix}{os.path.basename(path)}")

        def refresh_ek_list(select_no=None):
            ek_list.delete(0, "end")
            try:
                state["items"] = ek_basliklari(self.veri, current_set())
            except Exception as exc:
                state["items"] = []
                messagebox.showerror("Ekler", f"Ek başlıkları okunamadı:\n{exc}")
                refresh_files()
                return
            data = ek_icerik_haritasi(self.veri, current_set())
            select_idx = 0
            for idx, item in enumerate(state["items"]):
                no = str(item["no"])
                count = len(data.get(no, []) or [])
                title = item.get("title") or ""
                ek_list.insert("end", f"EK-{no}  {title}  ({count} dosya)")
                if select_no and str(select_no) == no:
                    select_idx = idx
            if state["items"]:
                ek_list.selection_set(select_idx)
                ek_list.activate(select_idx)
            refresh_files()

        def add_files():
            if not state.get("selected_no"):
                return
            paths = filedialog.askopenfilenames(
                title=f"EK-{state['selected_no']} için dosya seç",
                filetypes=[
                    ("Ek Dosyaları", "*.pdf;*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp;*.doc;*.docx;*.xls;*.xlsx"),
                    ("Tüm Dosyalar", "*.*"),
                ],
            )
            if not paths:
                return
            files = current_files(create=True)
            existing = {os.path.normcase(os.path.abspath(path)) for path in files}
            added = 0
            for path in paths:
                key = os.path.normcase(os.path.abspath(path))
                if key not in existing:
                    files.append(path)
                    existing.add(key)
                    added += 1
            refresh_ek_list(select_no=state["selected_no"])
            self.set_status(f"EK-{state['selected_no']} için {added} dosya eklendi.", level="success")

        def remove_files():
            files = current_files(create=True)
            for idx in sorted(file_list.curselection(), reverse=True):
                if 0 <= idx < len(files):
                    files.pop(idx)
            refresh_ek_list(select_no=state["selected_no"])

        def move_file(delta):
            files = current_files(create=True)
            indices = list(file_list.curselection())
            if len(indices) != 1:
                return
            idx = indices[0]
            new_idx = idx + delta
            if new_idx < 0 or new_idx >= len(files):
                return
            files[idx], files[new_idx] = files[new_idx], files[idx]
            refresh_files()
            file_list.selection_set(new_idx)
            file_list.activate(new_idx)

        def clear_files():
            if current_files(create=False) and messagebox.askyesno("Ekler", f"EK-{state['selected_no']} dosya listesi temizlensin mi?"):
                current_files(create=True).clear()
                refresh_ek_list(select_no=state["selected_no"])

        self.modern_button(file_btns, text="Dosya Ekle", command=add_files, role="success").pack(side="left", padx=(0, 5))
        self.modern_button(file_btns, text="Sil", command=remove_files, role="danger").pack(side="left", padx=5)
        self.modern_button(file_btns, text="Yukarı", command=lambda: move_file(-1), role="neutral", outline=True).pack(side="left", padx=5)
        self.modern_button(file_btns, text="Aşağı", command=lambda: move_file(1), role="neutral", outline=True).pack(side="left", padx=5)
        self.modern_button(file_btns, text="Temizle", command=clear_files, role="warning", outline=True).pack(side="left", padx=5)

        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Label(bottom, text="PDF çıktısı seçili ek setindeki kapakları ve dosyaları sırayla birleştirir.", foreground="#555555").pack(side="left")
        self.modern_button(bottom, text="PDF Oluştur", command=lambda: self.ekler_pdf_kaydet(set_key=current_set()), role="success").pack(side="right", padx=(6, 0))
        self.modern_button(bottom, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")

        ek_list.bind("<<ListboxSelect>>", lambda _event: refresh_files())
        refresh_ek_list()

    def ekler_pdf_kaydet(self, set_key=None):
        self.guncelle_veri_objesi(silent=True)
        set_key = set_key if set_key in EK_SET_LABELS else uygun_ek_seti(self.veri)
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("varsayilan_cikti_klasor", "")
        opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
        path = filedialog.asksaveasfilename(
            title="Ekler PDF kaydet",
            initialfile=ek_pdf_dosya_adi(self.veri, set_key),
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            **opts,
        )
        if not path:
            return
        veri = copy.deepcopy(self.veri)
        self.arka_plan_gorevi_baslat(
            "Ekler PDF",
            self.ekler_pdf_kaydet_worker,
            veri,
            path,
            set_key,
            status_start="Ekler PDF arka planda hazırlanıyor.",
            status_success="Ekler PDF hazırlandı.",
            status_error="Ekler PDF oluşturulamadı: {error}",
            on_success=self.ekler_pdf_kaydet_bitti,
            on_error=lambda exc: messagebox.showerror("Ekler", str(exc)),
        )
        return

    @perf_tracked("attachments.pdf.engine")
    def ekler_pdf_kaydet_worker(self, veri, path, set_key):
        info = ekler_pdf_olustur(veri, path, set_key=set_key)
        return path, info

    def ekler_pdf_kaydet_bitti(self, result):
        path, info = result
        self.set_status(f"Ekler PDF hazırlandı: {os.path.basename(path)}", level="success")
        message = (
            f"Ekler PDF hazırlandı:\n{path}\n\n"
            f"Ek kapağı: {info['cover_count']}\n"
            f"Eklenen dosya: {info['attached_count']}"
        )
        if info.get("warnings"):
            message += "\n\nUyarılar:\n" + "\n".join(info["warnings"][:8])
            messagebox.showwarning("Ekler", message)
        else:
            messagebox.showinfo("Ekler", message)

    def tutanak_eklere_bagla(self, path):
        if not path:
            return 0
        added = 0
        abs_path = os.path.abspath(path)
        for set_key in (EK_SET_NORMAL, EK_SET_ARAZI_DENEYLI):
            files = ek_icerik_haritasi(self.veri, set_key).setdefault("10", [])
            existing = {os.path.normcase(os.path.abspath(item)) for item in files if item}
            if os.path.normcase(abs_path) not in existing:
                files.append(path)
                added += 1
        self.ek_etiketlerini_guncelle()
        return added

    def tutanaklari_kaydet(self):
        self.guncelle_veri_objesi(silent=True)
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("varsayilan_cikti_klasor", "")
        opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
        path = filedialog.asksaveasfilename(
            title="Tutanakları kaydet",
            initialfile=tutanak_dosya_adi(self.veri, ".docx"),
            defaultextension=".docx",
            filetypes=[("Word", "*.docx"), ("PDF", "*.pdf")],
            **opts,
        )
        if not path:
            return
        veri = copy.deepcopy(self.veri)
        sondaj_haritasi = getattr(self, "word_img_sondaj", None)
        self.arka_plan_gorevi_baslat(
            "Tutanak oluştur",
            self.tutanaklari_kaydet_worker,
            veri,
            path,
            sondaj_haritasi,
            status_start="Tutanaklar arka planda oluşturuluyor.",
            status_success="Tutanaklar oluşturuldu.",
            status_error="Tutanaklar oluşturulamadı: {error}",
            on_success=self.tutanaklari_kaydet_bitti,
            on_error=lambda exc: messagebox.showerror("Tutanaklar", str(exc)),
        )
        return

    @perf_tracked("minutes.export.engine")
    def tutanaklari_kaydet_worker(self, veri, path, sondaj_haritasi):
        info = tutanaklari_olustur(veri, path, sondaj_haritasi)
        return path, info

    def tutanaklari_kaydet_bitti(self, result):
        path, info = result
        self.tutanak_eklere_bagla(path)
        self.set_status(f"Tutanaklar oluşturuldu: {os.path.basename(path)}", level="success")
        messagebox.showinfo(
            "Tutanaklar",
            f"Tutanaklar oluşturuldu:\n{path}\n\n"
            f"Sondaj tutanağı: {info['sondaj_count']}\n"
            f"Jeofizik tutanağı: {info['jeofizik_count']}\n\n"
            "Dosya EK-10 TUTANAKLAR bölümüne bağlandı.",
        )

    def taahhutname_kaydet(self, tur):
        self.guncelle_veri_objesi(silent=True)
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("varsayilan_cikti_klasor", "")
        opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
        path = filedialog.asksaveasfilename(
            title="Taahhütname kaydet",
            initialfile=taahhutname_dosya_adi(self.veri, tur, ".xlsx"),
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("PDF", "*.pdf")],
            **opts,
        )
        if not path:
            return
        veri = copy.deepcopy(self.veri)
        self.arka_plan_gorevi_baslat(
            "Taahhütname oluştur",
            self.taahhutname_kaydet_worker,
            veri,
            tur,
            path,
            status_start="Taahhütname arka planda oluşturuluyor.",
            status_success="Taahhütname oluşturuldu.",
            status_error="Taahhütname oluşturulamadı: {error}",
            on_success=self.taahhutname_kaydet_bitti,
            on_error=lambda exc: messagebox.showerror("Taahhütname", str(exc)),
        )
        return

    @perf_tracked("commitment.export_one.engine")
    def taahhutname_kaydet_worker(self, veri, tur, path):
        taahhutname_olustur(veri, tur, path)
        return path

    def taahhutname_kaydet_bitti(self, path):
        self.set_status(f"Taahhütname oluşturuldu: {os.path.basename(path)}", level="success")
        messagebox.showinfo("Taahhütname", f"Taahhütname oluşturuldu:\n{path}")

    def taahhutname_format_sec(self):
        result = {"ext": None}
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Taahhütname Formatı", "330x160", (320, 150), modal=True)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="İki taahhütname hangi formatta oluşturulsun?", font=FONT_BOLD).pack(anchor="w", pady=(0, 10))
        fmt_var = tk.StringVar(value=self.veri.get("ayarlar", {}).get("cikti_taahhut_format", "Excel"))
        if fmt_var.get() not in ("Excel", "PDF"):
            fmt_var.set("Excel")
        ttk.Combobox(body, textvariable=fmt_var, values=("Excel", "PDF"), state="readonly", width=14).pack(anchor="w")
        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(16, 0))

        def choose():
            result["ext"] = ".pdf" if fmt_var.get() == "PDF" else ".xlsx"
            self.veri.setdefault("ayarlar", {})["cikti_taahhut_format"] = fmt_var.get()
            win.destroy()

        self.modern_button(btns, text="Devam", command=choose, role="success").pack(side="right")
        self.modern_button(btns, text="Vazgeç", command=win.destroy, role="neutral", outline=True).pack(side="right", padx=(0, 6))
        win.wait_window()
        return result["ext"]

    def taahhutnameleri_kaydet(self):
        self.guncelle_veri_objesi(silent=True)
        ayarlar = self.veri.setdefault("ayarlar", {})
        ext = self.taahhutname_format_sec()
        if not ext:
            return
        initialdir = ayarlar.get("varsayilan_cikti_klasor", "")
        opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
        folder = filedialog.askdirectory(title="Taahhütnamelerin kaydedileceği klasörü seçin", **opts)
        if not folder:
            return
        veri = copy.deepcopy(self.veri)
        self.arka_plan_gorevi_baslat(
            "Toplu taahhütname oluştur",
            self.taahhutnameleri_kaydet_worker,
            veri,
            folder,
            ext,
            status_start="Toplu taahhütname çıktısı arka planda oluşturuluyor.",
            status_success="Toplu taahhütname çıktısı tamamlandı.",
            status_error="Taahhütnameler oluşturulamadı: {error}",
            on_success=self.taahhutnameleri_kaydet_bitti,
            on_error=lambda exc: messagebox.showerror("Taahhütname", str(exc)),
        )
        return

    @perf_tracked("commitment.export_all.engine")
    def taahhutnameleri_kaydet_worker(self, veri, folder, ext):
        paths = []
        errors = []
        try:
            paths.extend(tum_taahhutnameleri_olustur(veri, folder, ext))
        except Exception as exc:
            label = "PDF" if ext == ".pdf" else "Excel"
            errors.append(f"{label}: {exc}")
        return paths, errors

    def taahhutnameleri_kaydet_bitti(self, result):
        paths, errors = result
        if paths:
            level = "warning" if errors else "success"
            self.set_status(f"{len(paths)} taahhütname çıktısı oluşturuldu.", level=level)
            message = "Taahhütname çıktıları oluşturuldu:\n" + "\n".join(paths)
            if errors:
                message += "\n\nUyarılar:\n" + "\n".join(errors)
                messagebox.showwarning("Taahhütname", message)
            else:
                messagebox.showinfo("Taahhütname", message)
        else:
            message = "\n".join(errors) if errors else "Taahhütname çıktısı oluşturulamadı."
            self.set_status(f"Taahhütnameler oluşturulamadı: {message}", level="error")
            messagebox.showerror("Taahhütname", message)

    @perf_tracked("figures.export_dialog")
    def grafikleri_kaydet(self):
        initialdir = self.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor", "")
        opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
        klasor = filedialog.askdirectory(**opts)
        if not klasor:
            return
        veri_snapshot = copy.deepcopy(self.veri)
        self.arka_plan_gorevi_baslat(
            "Grafikleri kaydet",
            self.grafikleri_kaydet_worker,
            klasor,
            veri_snapshot,
            resource="render",
            status_start="Grafik dışa aktarımı arka planda başlatıldı.",
            status_success="Grafik dışa aktarımı tamamlandı.",
            status_error="Grafik dışa aktarımı tamamlanamadı: {error}",
            on_success=lambda path: messagebox.showinfo("Başarılı", f"Tüm grafikler kaydedildi:\n{path}"),
            on_error=lambda exc: messagebox.showerror("Hata", str(exc)),
        )

    def _arka_plan_status(self, message, level="info"):
        try:
            self.root.after(0, lambda msg=message, lvl=level: self.set_status(msg, level=lvl))
        except Exception:
            pass

    @perf_tracked("figures.export_all.engine")
    def grafikleri_kaydet_worker(self, klasor, veri_snapshot):
        with GeoEngine.plot_lock:
            for s in veri_snapshot["sondaj"]:
                self._arka_plan_status(f"Çizim başlatılıyor: {s['no']}...", level="info")
                figures = GeoEngine.ciz_profesyonel_log(s, veri_snapshot)
                try:
                    for idx, fig in enumerate(figures):
                        fig.savefig(
                            f"{klasor}/Log_{s['no']}_Sayfa{idx + 1}.jpg",
                            dpi=DEFAULT_EXPORT_DPI,
                            bbox_inches="tight",
                        )
                finally:
                    for fig in figures:
                        plt.close(fig)
            self._arka_plan_status("Jeolojik Kesit çiziliyor...", level="info")
            fig_k, _ = GeoEngine.kesit_ciz_interaktif(veri_snapshot["sondaj"])
            try:
                fig_k.savefig(os.path.join(klasor, "Jeolojik_Kesit.jpg"), dpi=DEFAULT_EXPORT_DPI, bbox_inches="tight")
            finally:
                plt.close(fig_k)
        return klasor

    @perf_tracked("report.preflight")
    def rapor_on_kontrol(self):
        self.guncelle_veri_objesi()
        report = build_preflight_report(self)
        self.on_kontrol_raporunu_sakla(report)
        self.ozet_yenile(collect=False)
        self.on_kontrol_penceresi(report)
        if report["errors"]:
            self.set_status(f"Ön kontrol {len(report['errors'])} hata buldu.", level="error")
        elif report["warnings"]:
            self.set_status(f"Ön kontrol {len(report['warnings'])} uyarı buldu.", level="warning")
        else:
            self.set_status("Ön kontrol temiz.", level="success")
        return report

    def on_kontrol_penceresi(self, report):
        return self.on_kontrol_merkezi_penceresi(report)

    def rapor_kayit_yolu_sec(self):
        cikti_klasor = self.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor", "")
        save_opts = {
            "defaultextension": ".docx",
            "filetypes": [("Word Dosyası", "*.docx")],
        }
        if cikti_klasor and os.path.isdir(cikti_klasor):
                save_opts["initialdir"] = cikti_klasor
        return filedialog.asksaveasfilename(**save_opts)

    def duzeltme_etiket_cikti_adi(self):
        proje = self.veri.get("kunye", {}).get("proje_adi", "") or "Rapor"
        chars = [ch if ch.isalnum() else "_" for ch in str(proje)]
        safe = "".join(chars).strip("_")
        while "__" in safe:
            safe = safe.replace("__", "_")
        return f"{(safe or 'Rapor')[:45]}_duzeltme_etiketleri.docx"

    def rapor_revizyon_cikti_adi(self, hazir_rapor_path=""):
        base = os.path.splitext(os.path.basename(hazir_rapor_path or ""))[0] or "Rapor"
        chars = [ch if ch.isalnum() else "_" for ch in str(base)]
        safe = "".join(chars).strip("_")
        while "__" in safe:
            safe = safe.replace("__", "_")
        return f"{(safe or 'Rapor')[:50]}_revize.docx"

    def rapor_metin_revizyon_cikti_adi(self, hazir_rapor_path=""):
        base = os.path.splitext(os.path.basename(hazir_rapor_path or ""))[0] or "Rapor"
        chars = [ch if ch.isalnum() else "_" for ch in str(base)]
        safe = "".join(chars).strip("_")
        while "__" in safe:
            safe = safe.replace("__", "_")
        return f"{(safe or 'Rapor')[:50]}_metin_revize.docx"

    def duzeltme_etiket_ciktisi_baslat(self, selected, parent=None):
        selected = [tag for tag in selected or [] if str(tag).strip()]
        if not selected:
            messagebox.showwarning("Düzeltme Etiketleri", "Lütfen en az bir etiket seçin.", parent=parent)
            return False
        self.guncelle_veri_objesi(silent=True)
        ayarlar = self.veri.setdefault("ayarlar", {})
        initialdir = ayarlar.get("varsayilan_cikti_klasor", "")
        opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
        path = filedialog.asksaveasfilename(
            title="Düzeltme etiket çıktısını kaydet",
            initialfile=self.duzeltme_etiket_cikti_adi(),
            defaultextension=".docx",
            filetypes=[("Word Dosyası", "*.docx")],
            parent=parent,
            **opts,
        )
        if not path:
            return False
        self.veri_kaydet()
        context = self.rapor_arka_plan_context()
        self.arka_plan_gorevi_baslat(
            "Düzeltme etiketleri",
            self.duzeltme_etiketleri_worker,
            context,
            selected,
            path,
            status_start="Seçili düzeltme etiketleri arka planda oluşturuluyor.",
            status_success="Düzeltme etiket çıktısı oluşturuldu.",
            status_error="Düzeltme etiket çıktısı oluşturulamadı: {error}",
            on_success=self.duzeltme_etiketleri_bitti,
            on_error=lambda exc: messagebox.showerror("Düzeltme Etiketleri", str(exc), parent=parent),
        )
        return True

    @perf_tracked("report.correction_assistant_dialog")
    def duzeltme_asistani_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Düzeltme Asistanı", "980x700", (760, 520), modal=False)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        top = ttk.Frame(body)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Belediye / kontrolör düzeltme notu", font=FONT_BOLD).pack(side="left")
        motor_var = tk.StringVar(value="otomatik")
        ttk.Label(top, text="Motor").pack(side="right", padx=(8, 4))
        ttk.Combobox(top, textvariable=motor_var, values=AI_MOTOR_ADLARI, state="readonly", width=14).pack(side="right")

        panes = ttk.PanedWindow(body, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=(0, 0, 8, 0))
        right = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        input_text = tk.Text(left, wrap="word", height=11, font=("Segoe UI", 10))
        input_scroll = ttk.Scrollbar(left, orient="vertical", command=input_text.yview)
        input_text.configure(yscrollcommand=input_scroll.set)
        input_scroll.pack(side="right", fill="y")
        input_text.pack(side="left", fill="both", expand=True)

        result_frame = ttk.LabelFrame(right, text="Analiz Sonucu", padding=8)
        result_frame.pack(fill="both", expand=True)
        result_text = tk.Text(result_frame, wrap="word", height=12, font=("Consolas", 9))
        result_text.pack(fill="both", expand=True)
        result_text.insert("1.0", "Henüz analiz yapılmadı.")
        result_text.config(state="disabled")

        tag_frame = ttk.LabelFrame(body, text="Önerilen / seçili etiketler", padding=8)
        tag_frame.pack(fill="x", pady=(10, 0))
        tag_grid = ttk.Frame(tag_frame)
        tag_grid.pack(fill="x")
        tag_vars = {}
        flat_tags = []
        for _group_title, items in DUZELTME_ETIKET_GRUPLARI:
            for tag, label in items:
                flat_tags.append((tag, label))
        for idx, (tag, label) in enumerate(flat_tags):
            var = tk.BooleanVar(value=False)
            tag_vars[tag] = var
            cb = ttk.Checkbutton(tag_grid, text=label, variable=var)
            cb.grid(row=idx // 4, column=idx % 4, sticky="w", padx=6, pady=2)

        status_var = tk.StringVar(value="Düzeltme notunu yapıştırıp Analiz Et butonuna basın.")
        ttk.Label(body, textvariable=status_var, foreground="#555555").pack(anchor="w", pady=(8, 0))

        def set_result_text(text):
            result_text.config(state="normal")
            result_text.delete("1.0", "end")
            result_text.insert("1.0", text)
            result_text.config(state="disabled")

        def set_tags(tags):
            selected = set(tags or [])
            for tag, var in tag_vars.items():
                var.set(tag in selected)

        def result_to_text(result):
            lines = [
                f"Kaynak: {result.get('source', '-')}",
                f"Önerilen etiketler: {', '.join(result.get('tags') or []) or '-'}",
            ]
            warnings = result.get("warnings") or []
            if warnings:
                lines.append("")
                lines.append("Uyarılar:")
                lines.extend(f"- {warning}" for warning in warnings)
            items = result.get("items") or []
            if items:
                lines.append("")
                lines.append("Maddeler:")
            for idx, item in enumerate(items, start=1):
                lines.append(f"{idx}. {item.get('konu') or item.get('talep') or 'Düzeltme'}")
                lines.append(f"   İşlem: {item.get('islem') or '-'}")
                lines.append(f"   Sekme: {item.get('sekme') or '-'}")
                lines.append(f"   Etiket: {', '.join(item.get('tags') or []) or '-'}")
                lines.append(f"   Güven: %{item.get('guven', '-')}")
            if not items:
                lines.append("")
                lines.append("Bu metinden otomatik etiket önerisi çıkarılamadı.")
            return "\n".join(lines)

        def analysis_done(result):
            if not win.winfo_exists():
                return
            set_tags(result.get("tags") or [])
            set_result_text(result_to_text(result))
            source = result.get("source", "-")
            status_var.set(f"Analiz tamamlandı. Kaynak: {source}. {len(result.get('tags') or [])} etiket önerildi.")

        def analyze():
            text = input_text.get("1.0", "end").strip()
            if not text:
                messagebox.showwarning("Düzeltme Asistanı", "Lütfen düzeltme metnini girin.", parent=win)
                return
            motor = motor_var.get()
            if not self.dis_ai_veri_aktarim_onayi(
                motor,
                "belediye/kontrolör düzeltme notu",
                parent=win,
            ):
                return
            set_result_text("Analiz yapılıyor...")
            status_var.set("Düzeltme metni analiz ediliyor.")
            self.arka_plan_gorevi_baslat(
                "Düzeltme asistanı",
                self.duzeltme_asistani_worker,
                text,
                motor,
                status_start="Düzeltme asistanı analiz yapıyor.",
                status_success="Düzeltme analizi tamamlandı.",
                status_error="Düzeltme analizi tamamlanamadı: {error}",
                on_success=analysis_done,
                on_error=lambda exc: messagebox.showerror("Düzeltme Asistanı", str(exc), parent=win),
            )

        def create_output():
            selected = [tag for tag, var in tag_vars.items() if var.get()]
            if self.duzeltme_etiket_ciktisi_baslat(selected, parent=win):
                status_var.set("Düzeltme etiket çıktısı başlatıldı.")

        def set_all(value):
            for var in tag_vars.values():
                var.set(value)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        self.modern_button(btns, text="Analiz Et", command=analyze, role="primary").pack(side="left")
        self.modern_button(btns, text="Tümünü Seç", command=lambda: set_all(True), role="neutral", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Temizle", command=lambda: set_all(False), role="warning", outline=True).pack(side="left")
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")
        self.modern_button(btns, text="Seçili Etiketleri Oluştur", command=create_output, role="success").pack(side="right", padx=(0, 6))

    @perf_tracked("report.correction_assistant.engine")
    def duzeltme_asistani_worker(self, text, motor):
        motor = motor if motor in AI_MOTOR_ADLARI else "otomatik"
        return belediye_duzeltme_analiz_et(text, motor=motor, timeout=45, ai_kullan=motor != "kural")

    @perf_tracked("report.revision_center_dialog")
    def rapor_revizyon_merkezi_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Rapor Revizyon Merkezi", "1040x720", (820, 560), modal=False)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        report_path_var = tk.StringVar(value="")
        status_var = tk.StringVar(value="Revize edilecek Word raporunu seçin.")

        report_row = ttk.LabelFrame(body, text="Hazır rapor", padding=8)
        report_row.pack(fill="x", pady=(0, 8))
        ttk.Label(report_row, textvariable=report_path_var, foreground="#555555").pack(side="left", fill="x", expand=True)

        def select_report():
            initialdir = self.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor", "")
            opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
            path = filedialog.askopenfilename(
                title="Revize edilecek Word raporunu seç",
                filetypes=[("Word Dosyası", "*.docx")],
                parent=win,
                **opts,
            )
            if path:
                report_path_var.set(path)
                status_var.set("Hazır rapor seçildi. Düzeltme notunu analiz edebilir veya etiketleri elle seçebilirsiniz.")

        self.modern_button(report_row, text="Rapor Seç", command=select_report, role="primary", outline=True).pack(side="right", padx=(8, 0))

        top = ttk.Frame(body)
        top.pack(fill="both", expand=True)
        left = ttk.Frame(top, padding=(0, 0, 8, 0))
        right = ttk.Frame(top, padding=(8, 0, 0, 0))
        left.pack(side="left", fill="both", expand=True)
        right.pack(side="right", fill="both", expand=True)

        note_box = ttk.LabelFrame(left, text="Belediye / kontrolör düzeltme notu", padding=8)
        note_box.pack(fill="both", expand=True)
        input_text = tk.Text(note_box, wrap="word", height=11, font=("Segoe UI", 10))
        input_scroll = ttk.Scrollbar(note_box, orient="vertical", command=input_text.yview)
        input_text.configure(yscrollcommand=input_scroll.set)
        input_scroll.pack(side="right", fill="y")
        input_text.pack(side="left", fill="both", expand=True)

        result_box = ttk.LabelFrame(right, text="Analiz sonucu", padding=8)
        result_box.pack(fill="both", expand=True)
        result_text = tk.Text(result_box, wrap="word", height=11, font=("Consolas", 9))
        result_text.pack(fill="both", expand=True)
        result_text.insert("1.0", "Henüz analiz yapılmadı.")
        result_text.config(state="disabled")

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(8, 0))
        motor_var = tk.StringVar(value="otomatik")
        ttk.Label(controls, text="Motor").pack(side="left")
        ttk.Combobox(controls, textvariable=motor_var, values=AI_MOTOR_ADLARI, state="readonly", width=14).pack(side="left", padx=(6, 12))
        ttk.Label(controls, textvariable=status_var, foreground="#555555").pack(side="left", fill="x", expand=True)

        tag_frame = ttk.LabelFrame(body, text="Güncellenecek rapor bölümleri", padding=8)
        tag_frame.pack(fill="x", pady=(8, 0))
        tag_grid = ttk.Frame(tag_frame)
        tag_grid.pack(fill="x")
        tag_vars = {}
        flat_tags = [(tag, label) for _group, items in DUZELTME_ETIKET_GRUPLARI for tag, label in items]
        for idx, (tag, label) in enumerate(flat_tags):
            var = tk.BooleanVar(value=False)
            tag_vars[tag] = var
            ttk.Checkbutton(tag_grid, text=label, variable=var).grid(row=idx // 4, column=idx % 4, sticky="w", padx=6, pady=2)

        def set_result_text(text):
            result_text.config(state="normal")
            result_text.delete("1.0", "end")
            result_text.insert("1.0", text)
            result_text.config(state="disabled")

        def set_tags(tags):
            selected = set(tags or [])
            for tag, var in tag_vars.items():
                var.set(tag in selected)

        def result_to_text(result):
            lines = [
                f"Kaynak: {result.get('source', '-')}",
                f"Önerilen etiketler: {', '.join(result.get('tags') or []) or '-'}",
            ]
            if result.get("warnings"):
                lines.append("")
                lines.append("Uyarılar:")
                lines.extend(f"- {warning}" for warning in result.get("warnings", []))
            items = result.get("items") or []
            if items:
                lines.append("")
                lines.append("Maddeler:")
            for idx, item in enumerate(items, start=1):
                lines.append(f"{idx}. {item.get('konu') or item.get('talep') or 'Düzeltme'}")
                lines.append(f"   İşlem: {item.get('islem') or '-'}")
                lines.append(f"   Sekme: {item.get('sekme') or '-'}")
                lines.append(f"   Etiket: {', '.join(item.get('tags') or []) or '-'}")
                lines.append(f"   Güven: %{item.get('guven', '-')}")
            return "\n".join(lines)

        def analysis_done(result):
            if not win.winfo_exists():
                return
            set_tags(result.get("tags") or [])
            set_result_text(result_to_text(result))
            status_var.set(f"Analiz tamamlandı. {len(result.get('tags') or [])} bölüm önerildi.")

        def analyze():
            text = input_text.get("1.0", "end").strip()
            if not text:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen düzeltme metnini girin.", parent=win)
                return
            motor = motor_var.get()
            if not self.dis_ai_veri_aktarim_onayi(
                motor,
                "belediye/kontrolör düzeltme notu",
                parent=win,
            ):
                return
            set_result_text("Analiz yapılıyor...")
            status_var.set("Düzeltme metni analiz ediliyor.")
            self.arka_plan_gorevi_baslat(
                "Revizyon düzeltme analizi",
                self.duzeltme_asistani_worker,
                text,
                motor,
                status_start="Revizyon düzeltme analizi yapılıyor.",
                status_success="Revizyon düzeltme analizi tamamlandı.",
                status_error="Revizyon analizi tamamlanamadı: {error}",
                on_success=analysis_done,
                on_error=lambda exc: messagebox.showerror("Rapor Revizyon Merkezi", str(exc), parent=win),
            )

        def create_revision():
            report_path = report_path_var.get().strip()
            selected = [tag for tag, var in tag_vars.items() if var.get()]
            if not report_path:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen revize edilecek Word raporunu seçin.", parent=win)
                return
            if not selected:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen güncellenecek en az bir bölüm seçin.", parent=win)
                return
            self.guncelle_veri_objesi(silent=True)
            initialdir = os.path.dirname(report_path)
            path = filedialog.asksaveasfilename(
                title="Revizyonlu raporu kaydet",
                initialdir=initialdir if os.path.isdir(initialdir) else None,
                initialfile=self.rapor_revizyon_cikti_adi(report_path),
                defaultextension=".docx",
                filetypes=[("Word Dosyası", "*.docx")],
                parent=win,
            )
            if not path:
                return
            self.veri_kaydet()
            context = self.rapor_arka_plan_context()
            status_var.set("Revizyonlu kopya hazırlanıyor.")
            self.arka_plan_gorevi_baslat(
                "Rapor revizyonu",
                self.rapor_revizyon_worker,
                context,
                report_path,
                selected,
                path,
                status_start="Revizyonlu rapor arka planda hazırlanıyor.",
                status_success="Revizyonlu rapor hazırlandı.",
                status_error="Revizyonlu rapor oluşturulamadı: {error}",
                on_success=self.rapor_revizyon_bitti,
                on_error=lambda exc: messagebox.showerror("Rapor Revizyon Merkezi", str(exc), parent=win),
            )

        def set_all(value):
            for var in tag_vars.values():
                var.set(value)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        self.modern_button(btns, text="Analiz Et", command=analyze, role="primary").pack(side="left")
        self.modern_button(btns, text="Tümünü Seç", command=lambda: set_all(True), role="neutral", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Temizle", command=lambda: set_all(False), role="warning", outline=True).pack(side="left")
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")
        self.modern_button(btns, text="Revizyonlu Kopya Oluştur", command=create_revision, role="success").pack(side="right", padx=(0, 6))

    @perf_tracked("report.revision.engine")
    def rapor_revizyon_worker(self, context, hazir_rapor_path, tags, output_path):
        return revizyonlu_rapor_olustur(context, hazir_rapor_path, tags, output_path)

    def rapor_revizyon_bitti(self, info):
        level = "success" if info.get("success") else "error"
        self.set_status(info.get("message", "Revizyon işlemi tamamlandı."), level=level)
        if info.get("success"):
            message = (
                f"{info.get('message')}\n\nDosya:\n{info.get('output_path')}\n\n"
                f"Güncellenen: {', '.join(info.get('updated') or [])}"
            )
            if info.get("missing"):
                message += f"\nGüncellenemeyen: {', '.join(info.get('missing') or [])}"
                messagebox.showwarning("Rapor Revizyon Merkezi", message)
            else:
                messagebox.showinfo("Rapor Revizyon Merkezi", message)
        else:
            messagebox.showerror("Rapor Revizyon Merkezi", info.get("message", "Revizyonlu rapor oluşturulamadı."))

    @perf_tracked("report.text_revision_dialog")
    def rapor_metin_revizyon_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Rapor Metin Revizyonu", "1120x760", (860, 560), modal=False)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        report_path_var = tk.StringVar(value="")
        status_var = tk.StringVar(value="Revize edilecek hazır Word raporunu seçin.")
        items_by_iid = {}

        report_row = ttk.LabelFrame(body, text="Hazır Word raporu", padding=8)
        report_row.pack(fill="x", pady=(0, 8))
        ttk.Label(report_row, textvariable=report_path_var, foreground="#555555").pack(side="left", fill="x", expand=True)

        def select_report():
            initialdir = self.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor", "")
            opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
            path = filedialog.askopenfilename(
                title="Metin revizyonu yapılacak Word raporunu seç",
                filetypes=[("Word Dosyası", "*.docx")],
                parent=win,
                **opts,
            )
            if path:
                report_path_var.set(path)
                status_var.set("Word raporu seçildi. Düzeltme notunu girip Analiz Et butonuna basın.")

        self.modern_button(report_row, text="Word Seç", command=select_report, role="primary", outline=True).pack(side="right", padx=(8, 0))

        top = ttk.PanedWindow(body, orient="horizontal")
        top.pack(fill="both", expand=True)
        left = ttk.Frame(top, padding=(0, 0, 8, 0))
        right = ttk.Frame(top, padding=(8, 0, 0, 0))
        top.add(left, weight=2)
        top.add(right, weight=3)

        note_box = ttk.LabelFrame(left, text="Belediye / kontrolör düzeltme notu", padding=8)
        note_box.pack(fill="both", expand=True)
        note_text = tk.Text(note_box, wrap="word", height=12, font=("Segoe UI", 10))
        note_scroll = ttk.Scrollbar(note_box, orient="vertical", command=note_text.yview)
        note_text.configure(yscrollcommand=note_scroll.set)
        note_scroll.pack(side="right", fill="y")
        note_text.pack(side="left", fill="both", expand=True)

        result_box = ttk.LabelFrame(right, text="Bulunan metin düzeltmeleri", padding=8)
        result_box.pack(fill="both", expand=True)
        columns = ("label", "old", "new", "guven", "source")
        tree = ttk.Treeview(result_box, columns=columns, show="headings", selectmode="extended", height=12)
        tree.heading("label", text="Konum")
        tree.heading("old", text="Eski ifade")
        tree.heading("new", text="Yeni ifade")
        tree.heading("guven", text="Güven")
        tree.heading("source", text="Kaynak")
        tree.column("label", width=150, anchor="w")
        tree.column("old", width=230, anchor="w")
        tree.column("new", width=230, anchor="w")
        tree.column("guven", width=70, anchor="center")
        tree.column("source", width=80, anchor="center")
        tree_scroll = ttk.Scrollbar(result_box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        preview_box = ttk.LabelFrame(body, text="Seçili öneri önizlemesi", padding=8)
        preview_box.pack(fill="both", expand=True, pady=(8, 0))
        preview_text = tk.Text(preview_box, wrap="word", height=7, font=("Consolas", 9))
        preview_text.pack(fill="both", expand=True)
        preview_text.insert("1.0", "Henüz öneri seçilmedi.")
        preview_text.config(state="disabled")

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(8, 0))
        motor_var = tk.StringVar(value="otomatik")
        ttk.Label(controls, text="Motor").pack(side="left")
        ttk.Combobox(controls, textvariable=motor_var, values=AI_MOTOR_ADLARI, state="readonly", width=14).pack(side="left", padx=(6, 12))
        ttk.Label(controls, textvariable=status_var, foreground="#555555").pack(side="left", fill="x", expand=True)

        def set_preview(text):
            preview_text.config(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", text)
            preview_text.config(state="disabled")

        def selected_preview(_event=None):
            selected = tree.selection()
            if not selected:
                set_preview("Henüz öneri seçilmedi.")
                return
            item = items_by_iid.get(selected[0])
            if not item:
                return
            lines = [
                f"Konum: {item.get('label', '-')}",
                f"Kaynak: {item.get('source', '-')} | Güven: %{item.get('guven', '-')}",
                f"Neden: {item.get('reason', '-')}",
                "",
                "Mevcut metin:",
                str(item.get("current_text", "")),
                "",
                "Revizyon sonrası:",
                str(item.get("preview_text", "")),
            ]
            set_preview("\n".join(lines))

        tree.bind("<<TreeviewSelect>>", selected_preview)

        def temizle_sonuclar():
            for iid in tree.get_children():
                tree.delete(iid)
            items_by_iid.clear()
            set_preview("Henüz öneri seçilmedi.")

        def analiz_bitti(result):
            if not win.winfo_exists():
                return
            temizle_sonuclar()
            items = result.get("items") or []
            for index, item in enumerate(items, start=1):
                iid = f"r{index}"
                items_by_iid[iid] = item
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        item.get("label", ""),
                        item.get("old_text", ""),
                        item.get("new_text", ""),
                        f"%{item.get('guven', '-')}",
                        item.get("source") or result.get("source", "-"),
                    ),
                )
            if items:
                tree.selection_set(tree.get_children())
                selected_preview()
            warnings = result.get("warnings") or []
            warning_text = f" Uyarı: {warnings[0]}" if warnings else ""
            status_var.set(f"Analiz tamamlandı. {len(items)} öneri bulundu. Kaynak: {result.get('source', '-')}.{warning_text}")
            if not items and warnings:
                set_preview("\n".join(warnings))

        def analiz_et():
            report_path = report_path_var.get().strip()
            note = note_text.get("1.0", "end").strip()
            if not report_path:
                messagebox.showwarning("Rapor Metin Revizyonu", "Lütfen revize edilecek Word raporunu seçin.", parent=win)
                return
            if not note:
                messagebox.showwarning("Rapor Metin Revizyonu", "Lütfen düzeltme notunu girin.", parent=win)
                return
            motor = motor_var.get()
            if not self.dis_ai_veri_aktarim_onayi(
                motor,
                "düzeltme notu ve seçili Word raporunun ilgili metinleri",
                parent=win,
            ):
                return
            temizle_sonuclar()
            set_preview("Rapor okunuyor ve düzeltme önerileri hazırlanıyor...")
            status_var.set("Hazır Word raporu okunuyor ve düzeltme notu analiz ediliyor.")
            self.arka_plan_gorevi_baslat(
                "Rapor metin revizyon analizi",
                self.rapor_metin_revizyon_analiz_worker,
                report_path,
                note,
                motor,
                status_start="Rapor metin revizyon analizi yapılıyor.",
                status_success="Rapor metin revizyon analizi tamamlandı.",
                status_error="Rapor metin revizyon analizi tamamlanamadı: {error}",
                on_success=analiz_bitti,
                on_error=lambda exc: messagebox.showerror("Rapor Metin Revizyonu", str(exc), parent=win),
            )

        def tumunu_sec():
            tree.selection_set(tree.get_children())
            selected_preview()

        def secimi_temizle():
            tree.selection_remove(tree.selection())
            selected_preview()

        def seciliyi_sil():
            for iid in tree.selection():
                tree.delete(iid)
                items_by_iid.pop(iid, None)
            selected_preview()
            status_var.set(f"Listede {len(tree.get_children())} öneri kaldı.")

        def uygulama_bitti(info):
            if not win.winfo_exists():
                return
            level = "success" if info.get("success") else "error"
            self.set_status(info.get("message", "Metin revizyonu tamamlandı."), level=level)
            if info.get("success"):
                messagebox.showinfo(
                    "Rapor Metin Revizyonu",
                    f"{info.get('message')}\n\nDosya:\n{info.get('output_path')}",
                    parent=win,
                )
                status_var.set(info.get("message", "Metin revizyonlu rapor oluşturuldu."))
            else:
                messagebox.showerror("Rapor Metin Revizyonu", info.get("message", "Metin revizyonu uygulanamadı."), parent=win)

        def secili_duzeltmeleri_uygula():
            report_path = report_path_var.get().strip()
            selected_iids = list(tree.selection())
            if not report_path:
                messagebox.showwarning("Rapor Metin Revizyonu", "Lütfen revize edilecek Word raporunu seçin.", parent=win)
                return
            if not selected_iids:
                messagebox.showwarning("Rapor Metin Revizyonu", "Lütfen uygulanacak en az bir düzeltme önerisi seçin.", parent=win)
                return
            selected = [items_by_iid[iid] for iid in selected_iids if iid in items_by_iid]
            initialdir = os.path.dirname(report_path)
            path = filedialog.asksaveasfilename(
                title="Metin revizyonlu raporu kaydet",
                initialdir=initialdir if os.path.isdir(initialdir) else None,
                initialfile=self.rapor_metin_revizyon_cikti_adi(report_path),
                defaultextension=".docx",
                filetypes=[("Word Dosyası", "*.docx")],
                parent=win,
            )
            if not path:
                return
            status_var.set("Seçili metin düzeltmeleri yeni Word kopyasına uygulanıyor.")
            self.arka_plan_gorevi_baslat(
                "Rapor metin revizyonu",
                self.rapor_metin_revizyon_uygula_worker,
                report_path,
                selected,
                path,
                status_start="Metin revizyonlu rapor hazırlanıyor.",
                status_success="Metin revizyonlu rapor hazırlandı.",
                status_error="Metin revizyonu uygulanamadı: {error}",
                on_success=uygulama_bitti,
                on_error=lambda exc: messagebox.showerror("Rapor Metin Revizyonu", str(exc), parent=win),
            )

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        self.modern_button(btns, text="Analiz Et", command=analiz_et, role="primary").pack(side="left")
        self.modern_button(btns, text="Tümünü Seç", command=tumunu_sec, role="neutral", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Seçimi Temizle", command=secimi_temizle, role="warning", outline=True).pack(side="left")
        self.modern_button(btns, text="Seçiliyi Listeden Sil", command=seciliyi_sil, role="danger", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")
        self.modern_button(btns, text="Seçili Düzeltmeleri Uygula", command=secili_duzeltmeleri_uygula, role="success").pack(side="right", padx=(0, 6))

    @perf_tracked("report.text_revision.analyze")
    def rapor_metin_revizyon_analiz_worker(self, report_path, note, motor):
        motor = motor if motor in AI_MOTOR_ADLARI else "otomatik"
        return metin_revizyon_analiz_et(report_path, note, motor=motor, timeout=45, ai_kullan=motor != "kural")

    @perf_tracked("report.text_revision.apply")
    def rapor_metin_revizyon_uygula_worker(self, report_path, revisions, output_path):
        return metin_revizyonlari_uygula(report_path, revisions, output_path)

    @perf_tracked("report.regulation_center_dialog")
    def yonetmelik_merkezi_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Yönetmelik Merkezi", "1060x720", (820, 560), modal=False)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        status_var = tk.StringVar(value=f"Yönetmelik klasörü: {YONETMELIK_DIR}")

        top = ttk.PanedWindow(body, orient="horizontal")
        top.pack(fill="both", expand=True)
        left = ttk.Frame(top, padding=(0, 0, 8, 0))
        right = ttk.Frame(top, padding=(8, 0, 0, 0))
        top.add(left, weight=2)
        top.add(right, weight=3)

        doc_box = ttk.LabelFrame(left, text="Kayıtlı Yönetmelikler", padding=8)
        doc_box.pack(fill="both", expand=True)
        doc_columns = ("title", "chunks", "chars", "added")
        doc_tree = ttk.Treeview(doc_box, columns=doc_columns, show="headings", selectmode="browse", height=14)
        for key, title, width, anchor in [
            ("title", "Ad", 250, "w"),
            ("chunks", "Parça", 60, "center"),
            ("chars", "Karakter", 80, "e"),
            ("added", "Eklenme", 130, "center"),
        ]:
            doc_tree.heading(key, text=title)
            doc_tree.column(key, width=width, anchor=anchor)
        doc_scroll = ttk.Scrollbar(doc_box, orient="vertical", command=doc_tree.yview)
        doc_tree.configure(yscrollcommand=doc_scroll.set)
        doc_scroll.pack(side="right", fill="y")
        doc_tree.pack(side="left", fill="both", expand=True)

        search_box = ttk.LabelFrame(right, text="Yönetmelikte Ara", padding=8)
        search_box.pack(fill="both", expand=True)
        search_row = ttk.Frame(search_box)
        search_row.pack(fill="x", pady=(0, 8))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_row, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True)

        result_columns = ("score", "doc", "section")
        result_tree = ttk.Treeview(search_box, columns=result_columns, show="headings", selectmode="browse", height=8)
        for key, title, width, anchor in [
            ("score", "Skor", 50, "center"),
            ("doc", "Yönetmelik", 190, "w"),
            ("section", "Bölüm/Madde", 240, "w"),
        ]:
            result_tree.heading(key, text=title)
            result_tree.column(key, width=width, anchor=anchor)
        result_tree.pack(fill="x")

        preview = tk.Text(search_box, wrap="word", height=13, font=("Consolas", 9))
        preview.pack(fill="both", expand=True, pady=(8, 0))
        preview.insert("1.0", "Arama sonucunu seçince ilgili yönetmelik parçası burada görünecek.")
        preview.config(state="disabled")

        results_by_iid = {}

        def set_preview(text):
            preview.config(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", text)
            preview.config(state="disabled")

        def refresh_docs():
            for iid in doc_tree.get_children():
                doc_tree.delete(iid)
            for doc in yonetmelikleri_listele():
                doc_tree.insert(
                    "",
                    "end",
                    iid=doc.get("id"),
                    values=(
                        doc.get("title", ""),
                        doc.get("chunk_count", 0),
                        doc.get("char_count", 0),
                        str(doc.get("added_at", ""))[:16],
                    ),
                )
            status_var.set(f"{len(doc_tree.get_children())} yönetmelik kayıtlı. Klasör: {YONETMELIK_DIR}")

        def add_done(records):
            refresh_docs()
            count = len(records or [])
            status_var.set(f"{count} yönetmelik eklendi.")
            self.set_status(f"Yönetmelik Merkezi: {count} dosya eklendi.", level="success")

        def add_files():
            paths = filedialog.askopenfilenames(
                title="Yönetmelik dosyası seç",
                filetypes=[
                    ("Yönetmelik Dosyaları", "*.pdf;*.docx;*.txt;*.md;*.html;*.htm"),
                    ("PDF", "*.pdf"),
                    ("Word", "*.docx"),
                    ("Metin/HTML", "*.txt;*.md;*.html;*.htm"),
                ],
                parent=win,
            )
            if not paths:
                return

            def worker():
                records = []
                for path in paths:
                    records.append(yonetmelik_ekle(path))
                return records

            status_var.set("Yönetmelik dosyaları okunuyor ve indeksleniyor...")
            self.arka_plan_gorevi_baslat(
                "Yönetmelik ekle",
                worker,
                status_start="Yönetmelik dosyaları indeksleniyor.",
                status_success="Yönetmelik dosyaları eklendi.",
                status_error="Yönetmelik eklenemedi: {error}",
                on_success=add_done,
                on_error=lambda exc: messagebox.showerror("Yönetmelik Merkezi", str(exc), parent=win),
            )

        def add_official_source():
            sources = resmi_yonetmelik_kaynaklari()
            if not sources:
                messagebox.showinfo("Yönetmelik Merkezi", "Tanımlı resmi yönetmelik kaynağı yok.", parent=win)
                return
            source = sources[0]

            def worker():
                return resmi_yonetmelik_indir_ve_ekle(source["id"])

            def done(result):
                record = (result or {}).get("record", {})
                refresh_docs()
                if (result or {}).get("already_exists"):
                    messagebox.showinfo(
                        "Yönetmelik Merkezi",
                        f"'{record.get('title', source.get('title'))}' zaten ekli.",
                        parent=win,
                    )
                    status_var.set("Resmi yönetmelik zaten kayıtlı.")
                elif (result or {}).get("embedded_fallback"):
                    status_var.set(f"Yerleşik yönetmelik kaynağı eklendi: {record.get('title', source.get('title'))}")
                    self.set_status("İnternet bağlantısı olmadığı için yerleşik yönetmelik kaynağı eklendi.", level="warning")
                else:
                    status_var.set(f"Resmi yönetmelik eklendi: {record.get('title', source.get('title'))}")
                    self.set_status("Resmi yönetmelik eklendi ve indekslendi.", level="success")

            def failed(exc):
                status_var.set("Resmi yönetmelik indirilemedi. Dosyayı elle ekleyebilirsiniz.")
                messagebox.showerror(
                    "Yönetmelik Merkezi",
                    "Resmi yönetmelik otomatik indirilemedi.\n\n"
                    f"Kaynak: {source.get('page_url', '-')}\n\n"
                    f"Hata: {exc}\n\n"
                    "Bu durumda resmi sayfadaki DOCX/PDF dosyasını indirip 'Yönetmelik Ekle' ile ekleyebilirsiniz.",
                    parent=win,
                )

            status_var.set("Resmi yönetmelik indiriliyor ve indeksleniyor...")
            self.arka_plan_gorevi_baslat(
                "Resmi yönetmelik ekle",
                worker,
                status_start="Resmi yönetmelik indiriliyor.",
                status_success="Resmi yönetmelik eklendi.",
                status_error="Resmi yönetmelik indirilemedi: {error}",
                on_success=done,
                on_error=failed,
            )

        def remove_selected():
            selected = doc_tree.selection()
            if not selected:
                messagebox.showwarning("Yönetmelik Merkezi", "Lütfen silinecek yönetmeliği seçin.", parent=win)
                return
            title = doc_tree.item(selected[0], "values")[0]
            if not messagebox.askyesno("Yönetmelik Merkezi", f"'{title}' kaydı silinsin mi?", parent=win):
                return
            if yonetmelik_sil(selected[0]):
                refresh_docs()
                set_preview("Yönetmelik kaydı silindi.")
                self.set_status("Yönetmelik kaydı silindi.", level="success")

        def search():
            query = search_var.get().strip()
            for iid in result_tree.get_children():
                result_tree.delete(iid)
            results_by_iid.clear()
            if not query:
                set_preview("Aramak için bir ifade yazın.")
                return
            results = yonetmelik_ara(query, limit=12)
            for idx, item in enumerate(results, start=1):
                iid = f"r{idx}"
                results_by_iid[iid] = item
                result_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(item.get("score", 0), item.get("doc_title", ""), item.get("chunk_title", "")),
                )
            if results:
                result_tree.selection_set("r1")
                show_result()
                status_var.set(f"{len(results)} eşleşme bulundu.")
            else:
                set_preview("Eşleşme bulunamadı.")
                status_var.set("Yönetmelik aramasında eşleşme bulunamadı.")

        def show_result(_event=None):
            selected = result_tree.selection()
            if not selected:
                return
            item = results_by_iid.get(selected[0])
            if not item:
                return
            lines = [
                f"Yönetmelik: {item.get('doc_title', '-')}",
                f"Bölüm/Madde: {item.get('chunk_title', '-')}",
                f"Skor: {item.get('score', 0)}",
                "",
                item.get("excerpt", ""),
            ]
            set_preview("\n".join(lines))

        result_tree.bind("<<TreeviewSelect>>", show_result)
        search_entry.bind("<Return>", lambda _event: search())

        self.modern_button(search_row, text="Ara", command=search, role="primary").pack(side="left", padx=(8, 0))

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        self.modern_button(btns, text="Yönetmelik Ekle", command=add_files, role="success").pack(side="left")
        self.modern_button(btns, text="Resmi Zemin Formatını Ekle", command=add_official_source, role="primary", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Seçileni Sil", command=remove_selected, role="danger", outline=True).pack(side="left")
        ttk.Label(btns, textvariable=status_var, foreground="#555555").pack(side="left", fill="x", expand=True, padx=8)
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")

        refresh_docs()

    @perf_tracked("report.unified_revision_dialog")
    def rapor_revizyon_merkezi_birlesik_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Rapor Revizyon Merkezi", "1160x780", (900, 580), modal=False)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        report_path_var = tk.StringVar(value="")
        status_var = tk.StringVar(value="Revize edilecek hazır Word raporunu seçin.")
        text_items_by_iid = {}

        report_row = ttk.LabelFrame(body, text="Hazır Word raporu", padding=8)
        report_row.pack(fill="x", pady=(0, 8))
        ttk.Label(report_row, textvariable=report_path_var, foreground="#555555").pack(side="left", fill="x", expand=True)

        def select_report():
            initialdir = self.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor", "")
            opts = {"initialdir": initialdir} if initialdir and os.path.isdir(initialdir) else {}
            path = filedialog.askopenfilename(
                title="Revize edilecek Word raporunu seç",
                filetypes=[("Word Dosyası", "*.docx")],
                parent=win,
                **opts,
            )
            if path:
                report_path_var.set(path)
                status_var.set("Hazır rapor seçildi. Belediye düzeltme notunu girip Analiz Et butonuna basın.")

        self.modern_button(report_row, text="Rapor Seç", command=select_report, role="primary", outline=True).pack(side="right", padx=(8, 0))

        top = ttk.PanedWindow(body, orient="horizontal")
        top.pack(fill="both", expand=True)
        left = ttk.Frame(top, padding=(0, 0, 8, 0))
        right = ttk.Frame(top, padding=(8, 0, 0, 0))
        top.add(left, weight=2)
        top.add(right, weight=3)

        note_box = ttk.LabelFrame(left, text="Belediye / kontrolör düzeltme notu", padding=8)
        note_box.pack(fill="both", expand=True)
        input_text = tk.Text(note_box, wrap="word", height=13, font=("Segoe UI", 10))
        input_scroll = ttk.Scrollbar(note_box, orient="vertical", command=input_text.yview)
        input_text.configure(yscrollcommand=input_scroll.set)
        input_scroll.pack(side="right", fill="y")
        input_text.pack(side="left", fill="both", expand=True)

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        workflow_tab = ttk.Frame(notebook, padding=8)
        section_tab = ttk.Frame(notebook, padding=8)
        text_tab = ttk.Frame(notebook, padding=8)
        regulation_tab = ttk.Frame(notebook, padding=8)
        notebook.add(workflow_tab, text="Yapılacak İşler")
        notebook.add(section_tab, text="Tablo / Bölüm")
        notebook.add(text_tab, text="Metin / Cümle")
        notebook.add(regulation_tab, text="Yönetmelik Dayanağı")

        workflow_box = ttk.LabelFrame(workflow_tab, text="Veri girişi / işlem yönlendirmesi", padding=8)
        workflow_box.pack(fill="both", expand=True)
        workflow_text = tk.Text(workflow_box, wrap="word", height=12, font=("Consolas", 9))
        workflow_text.pack(fill="both", expand=True)
        workflow_text.insert("1.0", "Henüz yönlendirme yok. Analizden sonra ek sondaj, ek laboratuvar, yeni jeofizik gibi işler burada görünecek.")
        workflow_text.config(state="disabled")
        workflow_buttons = ttk.Frame(workflow_tab)
        workflow_buttons.pack(fill="x", pady=(8, 0))

        summary_box = ttk.LabelFrame(section_tab, text="Programın kararı", padding=8)
        summary_box.pack(fill="both", expand=True)
        summary_text = tk.Text(summary_box, wrap="word", height=8, font=("Consolas", 9))
        summary_text.pack(fill="both", expand=True)
        summary_text.insert("1.0", "Henüz analiz yapılmadı.")
        summary_text.config(state="disabled")

        tag_frame = ttk.LabelFrame(section_tab, text="Güncellenecek rapor bölümleri", padding=8)
        tag_frame.pack(fill="x", pady=(8, 0))
        tag_grid = ttk.Frame(tag_frame)
        tag_grid.pack(fill="x")
        tag_vars = {}
        flat_tags = [(tag, label) for _group, items in DUZELTME_ETIKET_GRUPLARI for tag, label in items]
        for idx, (tag, label) in enumerate(flat_tags):
            var = tk.BooleanVar(value=False)
            tag_vars[tag] = var
            ttk.Checkbutton(tag_grid, text=label, variable=var).grid(row=idx // 4, column=idx % 4, sticky="w", padx=6, pady=2)

        text_result_box = ttk.LabelFrame(text_tab, text="Bulunan metin düzeltmeleri", padding=8)
        text_result_box.pack(fill="both", expand=True)
        columns = ("use", "label", "old", "new", "guven", "source")
        text_tree = ttk.Treeview(text_result_box, columns=columns, show="headings", selectmode="browse", height=10)
        for key, title, width, anchor in [
            ("use", "Tik", 46, "center"),
            ("label", "Konum", 150, "w"),
            ("old", "Eski ifade", 220, "w"),
            ("new", "Yeni ifade", 220, "w"),
            ("guven", "Güven", 70, "center"),
            ("source", "Kaynak", 80, "center"),
        ]:
            text_tree.heading(key, text=title)
            text_tree.column(key, width=width, anchor=anchor)
        text_scroll = ttk.Scrollbar(text_result_box, orient="vertical", command=text_tree.yview)
        text_tree.configure(yscrollcommand=text_scroll.set)
        text_scroll.pack(side="right", fill="y")
        text_tree.pack(side="left", fill="both", expand=True)

        preview_box = ttk.LabelFrame(text_tab, text="Seçili metin önerisi", padding=8)
        preview_box.pack(fill="both", expand=True, pady=(8, 0))
        preview_text = tk.Text(preview_box, wrap="word", height=6, font=("Consolas", 9))
        preview_text.pack(fill="both", expand=True)
        preview_text.insert("1.0", "Henüz öneri seçilmedi.")
        preview_text.config(state="disabled")

        regulation_box = ttk.LabelFrame(regulation_tab, text="Düzeltme talebiyle ilişkili yönetmelik maddeleri", padding=8)
        regulation_box.pack(fill="both", expand=True)
        regulation_text = tk.Text(regulation_box, wrap="word", height=16, font=("Consolas", 9))
        regulation_scroll = ttk.Scrollbar(regulation_box, orient="vertical", command=regulation_text.yview)
        regulation_text.configure(yscrollcommand=regulation_scroll.set)
        regulation_scroll.pack(side="right", fill="y")
        regulation_text.pack(side="left", fill="both", expand=True)
        regulation_text.insert("1.0", "Yönetmelik Merkezi'ne dosya eklerseniz, analizden sonra ilgili dayanaklar burada görünecek.")
        regulation_text.config(state="disabled")

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(8, 0))
        motor_var = tk.StringVar(value="otomatik")
        ttk.Label(controls, text="Motor").pack(side="left")
        ttk.Combobox(controls, textvariable=motor_var, values=AI_MOTOR_ADLARI, state="readonly", width=14).pack(side="left", padx=(6, 12))
        ttk.Label(controls, textvariable=status_var, foreground="#555555").pack(side="left", fill="x", expand=True)

        def set_summary(text):
            summary_text.config(state="normal")
            summary_text.delete("1.0", "end")
            summary_text.insert("1.0", text)
            summary_text.config(state="disabled")

        def set_preview(text):
            preview_text.config(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", text)
            preview_text.config(state="disabled")

        def set_workflow_text(text):
            workflow_text.config(state="normal")
            workflow_text.delete("1.0", "end")
            workflow_text.insert("1.0", text)
            workflow_text.config(state="disabled")

        def set_regulation_text(text):
            regulation_text.config(state="normal")
            regulation_text.delete("1.0", "end")
            regulation_text.insert("1.0", text)
            regulation_text.config(state="disabled")

        def run_guidance_action(action):
            key = (action or {}).get("action_key") or (action or {}).get("target")
            target = (action or {}).get("target")
            try:
                if key == "sondaj_hizli":
                    self._workflow_git("sondaj")
                    self.sondaj_hizli_tablo_ac()
                elif key == "spt_merkezi":
                    self._workflow_git("sondaj")
                    self.spt_okuma_merkezi_ac()
                elif key == "workbook":
                    self.veri_giris_workbook_tksheet_ac()
                elif key == "lab_excel":
                    self._workflow_git("rapor")
                    self.lab_excel_sec()
                elif key == "lab_sheet":
                    self._workflow_git("rapor")
                    self.lab_sheet_ac()
                elif target:
                    self._workflow_git(target)
                self.set_status(f"Yönlendirme açıldı: {(action or {}).get('title', '')}", level="info")
            except Exception as exc:
                messagebox.showerror("Rapor Revizyon Merkezi", f"Yönlendirme açılamadı:\n{exc}", parent=win)

        def set_guidance(actions):
            for child in workflow_buttons.winfo_children():
                child.destroy()
            actions = list(actions or [])
            if not actions:
                set_workflow_text("Bu düzeltme notunda önce veri girişi gerektiren özel bir iş algılanmadı.")
                return
            lines = ["Program önce şu işleri kontrol etmeni öneriyor:", ""]
            for idx, action in enumerate(actions, start=1):
                lines.append(f"{idx}. {action.get('title', 'Yapılacak iş')}")
                lines.append(f"   {action.get('description', '')}")
                if action.get("source_text"):
                    lines.append(f"   Kaynak düzeltme: {action.get('source_text')}")
                if action.get("matched_keywords"):
                    lines.append(f"   Yakalanan ifade: {', '.join(action.get('matched_keywords') or [])}")
                if action.get("tags"):
                    lines.append(f"   Sonra yenilenecek bölümler: {', '.join(action.get('tags') or [])}")
                lines.append("")
            lines.append("Bu işleri tamamladıktan sonra aynı düzeltme notuyla tekrar Analiz Et diyebilirsin.")
            set_workflow_text("\n".join(lines).strip())
            for idx, action in enumerate(actions[:5]):
                btn = self.modern_button(
                    workflow_buttons,
                    text=action.get("button_text") or "İlgili Sekmeye Git",
                    command=lambda item=action: run_guidance_action(item),
                    role="primary" if idx == 0 else "neutral",
                    outline=idx != 0,
                )
                btn.pack(side="left", padx=(0, 6), pady=2)

        def set_regulation_result(result):
            result = result or {}
            items = list(result.get("items") or [])
            warnings = list(result.get("warnings") or [])
            docs = list(result.get("documents") or [])
            lines = []
            if docs:
                lines.append(f"Kayıtlı yönetmelik: {len(docs)}")
            else:
                lines.append("Kayıtlı yönetmelik yok.")
            if warnings:
                lines.append("")
                lines.extend(f"- {warning}" for warning in warnings)
            if items:
                lines.append("")
                lines.append("Bulunan dayanaklar:")
                lines.append("")
                for idx, item in enumerate(items, start=1):
                    lines.append(f"{idx}. {item.get('doc_title', '-')}")
                    lines.append(f"   Bölüm/Madde: {item.get('chunk_title', '-')}")
                    lines.append(f"   Skor: {item.get('score', 0)}")
                    if item.get("source_text"):
                        lines.append(f"   Kaynak düzeltme: {item.get('source_text')}")
                    lines.append("   Alıntı/özet:")
                    lines.append(f"   {item.get('excerpt', '')}")
                    lines.append("")
            elif docs and not warnings:
                lines.append("")
                lines.append("Bu düzeltme metniyle eşleşen yönetmelik maddesi bulunamadı.")
            set_regulation_text("\n".join(lines).strip())

        def set_tags(tags):
            selected = set(tags or [])
            for tag, var in tag_vars.items():
                var.set(tag in selected)

        def set_all_tags(value):
            for var in tag_vars.values():
                var.set(value)

        def clear_text_results():
            for iid in text_tree.get_children():
                text_tree.delete(iid)
            text_items_by_iid.clear()
            set_preview("Henüz öneri seçilmedi.")

        def text_item_checked(item):
            return bool((item or {}).get("_checked", True))

        def text_item_check_symbol(item):
            return "☑" if text_item_checked(item) else "☐"

        def update_text_tree_row(iid):
            item = text_items_by_iid.get(iid)
            if not item:
                return
            text_tree.item(
                iid,
                values=(
                    text_item_check_symbol(item),
                    item.get("label", ""),
                    item.get("old_text", ""),
                    item.get("new_text", ""),
                    f"%{item.get('guven', '-')}",
                    item.get("source") or "-",
                ),
            )

        def set_all_text_checks(value):
            for iid, item in text_items_by_iid.items():
                item["_checked"] = bool(value)
                update_text_tree_row(iid)
            selected_text_preview()

        def toggle_text_check(iid):
            item = text_items_by_iid.get(iid)
            if not item:
                return
            item["_checked"] = not text_item_checked(item)
            update_text_tree_row(iid)
            text_tree.selection_set(iid)
            selected_text_preview()

        def text_tree_click(event):
            if text_tree.identify_region(event.x, event.y) != "cell":
                return
            if text_tree.identify_column(event.x) != "#1":
                return
            iid = text_tree.identify_row(event.y)
            if iid:
                toggle_text_check(iid)
                return "break"

        text_tree.bind("<Button-1>", text_tree_click, add="+")

        def selected_text_preview(_event=None):
            selected = text_tree.selection()
            if not selected:
                set_preview("Henüz öneri seçilmedi.")
                return
            item = text_items_by_iid.get(selected[0])
            if not item:
                return
            lines = [
                f"Konum: {item.get('label', '-')}",
                f"Kaynak: {item.get('source', '-')} | Güven: %{item.get('guven', '-')}",
                f"Neden: {item.get('reason', '-')}",
                "",
                "Mevcut metin:",
                str(item.get("current_text", "")),
                "",
                "Revizyon sonrası:",
                str(item.get("preview_text", "")),
            ]
            set_preview("\n".join(lines))

        text_tree.bind("<<TreeviewSelect>>", selected_text_preview)

        def combined_result_to_text(result):
            tag_result = result.get("tag_result") or {}
            text_result = result.get("text_result") or {}
            guidance = result.get("guidance") or []
            regulation = result.get("regulation_result") or {}
            tags = tag_result.get("tags") or []
            text_items = text_result.get("items") or []
            regulation_items = regulation.get("items") or []
            lines = [
                f"Bölüm/etiket kaynağı: {tag_result.get('source', '-')}",
                f"Metin düzeltme kaynağı: {text_result.get('source', '-')}",
                "",
                f"Önerilen yapılacak iş: {len(guidance)}",
                f"Programın önerdiği bölüm sayısı: {len(tags)}",
                f"Programın bulduğu metin düzeltmesi: {len(text_items)}",
                f"Bulunan yönetmelik dayanağı: {len(regulation_items)}",
            ]
            if guidance:
                lines.append("Karar: Önce veri girişi/güncelleme gerektiren iş olabilir; Yapılacak İşler sekmesini kontrol et.")
            elif tags and text_items:
                lines.append("Karar: Hem tablo/bölüm güncellemesi hem metin düzeltmesi öneriliyor.")
            elif tags:
                lines.append("Karar: Bu talep ağırlıklı olarak tablo/bölüm güncellemesi gibi görünüyor.")
            elif text_items:
                lines.append("Karar: Bu talep ağırlıklı olarak metin/cümle düzeltmesi gibi görünüyor.")
            else:
                lines.append("Karar: Otomatik net düzeltme bulunamadı; bölümleri elle seçebilirsiniz.")
            if guidance:
                lines.append("")
                lines.append("Yapılacak işler:")
                for item in guidance:
                    lines.append(f"- {item.get('title', 'İş')}: {item.get('description', '')}")
                    if item.get("source_text"):
                        lines.append(f"  Kaynak: {item.get('source_text')}")
            if tags:
                lines.append("")
                lines.append("Önerilen bölümler:")
                for tag in tags:
                    lines.append(f"- {tag}")
            warnings = list(tag_result.get("warnings") or []) + list(text_result.get("warnings") or [])
            warnings += list(regulation.get("warnings") or [])
            if warnings:
                lines.append("")
                lines.append("Uyarılar:")
                lines.extend(f"- {warning}" for warning in warnings[:6])
            return "\n".join(lines)

        def analysis_done(result):
            if not win.winfo_exists():
                return
            tag_result = result.get("tag_result") or {}
            text_result = result.get("text_result") or {}
            guidance = result.get("guidance") or []
            regulation_result = result.get("regulation_result") or {}
            set_tags(tag_result.get("tags") or [])
            set_guidance(guidance)
            set_regulation_result(regulation_result)
            clear_text_results()
            text_items = text_result.get("items") or []
            for index, item in enumerate(text_items, start=1):
                iid = f"m{index}"
                item = dict(item)
                item["_checked"] = True
                text_items_by_iid[iid] = item
                text_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        text_item_check_symbol(item),
                        item.get("label", ""),
                        item.get("old_text", ""),
                        item.get("new_text", ""),
                        f"%{item.get('guven', '-')}",
                        item.get("source") or text_result.get("source", "-"),
                    ),
                )
            if text_items:
                first = text_tree.get_children()[0]
                text_tree.selection_set(first)
                selected_text_preview()
            set_summary(combined_result_to_text(result))
            if guidance:
                notebook.select(workflow_tab)
            elif text_items:
                notebook.select(text_tab)
            elif regulation_result.get("items"):
                notebook.select(regulation_tab)
            else:
                notebook.select(section_tab)
            status_var.set(
                f"Analiz tamamlandı. {len(guidance)} iş, {len(tag_result.get('tags') or [])} bölüm, {len(text_items)} metin düzeltmesi, {len(regulation_result.get('items') or [])} yönetmelik dayanağı önerildi."
            )

        def analyze():
            report_path = report_path_var.get().strip()
            text = input_text.get("1.0", "end").strip()
            if not report_path:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen revize edilecek Word raporunu seçin.", parent=win)
                return
            if not text:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen belediye düzeltme notunu girin.", parent=win)
                return
            motor = motor_var.get()
            if not self.dis_ai_veri_aktarim_onayi(
                motor,
                "belediye düzeltme notu ve seçili Word raporunun ilgili metinleri",
                parent=win,
            ):
                return
            set_summary("Analiz yapılıyor...")
            clear_text_results()
            set_guidance([])
            set_regulation_result({"items": [], "documents": yonetmelikleri_listele(), "warnings": ["Analiz yapılıyor..."]})
            status_var.set("Belediye düzeltmesi tek merkezde analiz ediliyor.")
            self.arka_plan_gorevi_baslat(
                "Birleşik rapor revizyon analizi",
                self.rapor_revizyon_birlesik_analiz_worker,
                report_path,
                text,
                motor,
                status_start="Rapor revizyon analizi yapılıyor.",
                status_success="Rapor revizyon analizi tamamlandı.",
                status_error="Rapor revizyon analizi tamamlanamadı: {error}",
                on_success=analysis_done,
                on_error=lambda exc: messagebox.showerror("Rapor Revizyon Merkezi", str(exc), parent=win),
            )

        def apply_done(info):
            if not win.winfo_exists():
                return
            level = "success" if info.get("success") else "error"
            self.set_status(info.get("message", "Revizyon işlemi tamamlandı."), level=level)
            if info.get("success"):
                detail = [
                    info.get("message", "Revizyonlu rapor oluşturuldu."),
                    "",
                    f"Dosya:\n{info.get('output_path')}",
                    "",
                    f"Güncellenen bölüm: {len(info.get('updated') or [])}",
                    f"Uygulanan metin düzeltmesi: {len(info.get('applied') or [])}",
                ]
                if info.get("missing"):
                    detail.append(f"Güncellenemeyen bölüm: {', '.join(info.get('missing') or [])}")
                if info.get("skipped"):
                    detail.append(f"Atlanan metin düzeltmesi: {len(info.get('skipped') or [])}")
                message = "\n".join(detail)
                if info.get("missing") or info.get("skipped"):
                    messagebox.showwarning("Rapor Revizyon Merkezi", message, parent=win)
                else:
                    messagebox.showinfo("Rapor Revizyon Merkezi", message, parent=win)
                status_var.set(info.get("message", "Revizyonlu rapor oluşturuldu."))
            else:
                messagebox.showerror("Rapor Revizyon Merkezi", info.get("message", "Revizyonlu rapor oluşturulamadı."), parent=win)

        def create_revision():
            report_path = report_path_var.get().strip()
            selected_tags = [tag for tag, var in tag_vars.items() if var.get()]
            selected_revisions = [item for item in text_items_by_iid.values() if text_item_checked(item)]
            if not report_path:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen revize edilecek Word raporunu seçin.", parent=win)
                return
            if not selected_tags and not selected_revisions:
                messagebox.showwarning("Rapor Revizyon Merkezi", "Lütfen en az bir bölüm veya metin düzeltmesi seçin.", parent=win)
                return
            initialdir = os.path.dirname(report_path)
            path = filedialog.asksaveasfilename(
                title="Revizyonlu raporu kaydet",
                initialdir=initialdir if os.path.isdir(initialdir) else None,
                initialfile=self.rapor_revizyon_cikti_adi(report_path),
                defaultextension=".docx",
                filetypes=[("Word Dosyası", "*.docx")],
                parent=win,
            )
            if not path:
                return
            context = None
            if selected_tags:
                self.guncelle_veri_objesi(silent=True)
                self.veri_kaydet()
                context = self.rapor_arka_plan_context()
            status_var.set("Seçili bölüm ve metin düzeltmeleri tek çıktıda uygulanıyor.")
            self.arka_plan_gorevi_baslat(
                "Birleşik rapor revizyonu",
                self.rapor_revizyon_birlesik_worker,
                context,
                report_path,
                selected_tags,
                selected_revisions,
                path,
                status_start="Revizyonlu rapor arka planda hazırlanıyor.",
                status_success="Revizyonlu rapor hazırlandı.",
                status_error="Revizyonlu rapor oluşturulamadı: {error}",
                on_success=apply_done,
                on_error=lambda exc: messagebox.showerror("Rapor Revizyon Merkezi", str(exc), parent=win),
            )

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        self.modern_button(btns, text="Analiz Et", command=analyze, role="primary").pack(side="left")
        self.modern_button(btns, text="Bölüm Seç", command=lambda: set_all_tags(True), role="neutral", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Bölüm Temizle", command=lambda: set_all_tags(False), role="warning", outline=True).pack(side="left")
        self.modern_button(btns, text="Metin Tikle", command=lambda: set_all_text_checks(True), role="neutral", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Metin Tiklerini Kaldır", command=lambda: set_all_text_checks(False), role="warning", outline=True).pack(side="left")
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")
        self.modern_button(btns, text="Revizyonlu Kopya Oluştur", command=create_revision, role="success").pack(side="right", padx=(0, 6))

    @perf_tracked("report.unified_revision.analyze")
    def rapor_revizyon_birlesik_analiz_worker(self, report_path, text, motor):
        motor = motor if motor in AI_MOTOR_ADLARI else "otomatik"
        return {
            "tag_result": belediye_duzeltme_analiz_et(text, motor=motor, timeout=45, ai_kullan=motor != "kural"),
            "text_result": metin_revizyon_analiz_et(report_path, text, motor=motor, timeout=45, ai_kullan=motor != "kural"),
            "guidance": duzeltme_yonlendirmeleri_olustur(text),
            "regulation_result": duzeltme_yonetmelik_dayanaklari(text),
        }

    @perf_tracked("report.unified_revision.apply")
    def rapor_revizyon_birlesik_worker(self, context, hazir_rapor_path, tags, text_revisions, output_path):
        tags = list(tags or [])
        text_revisions = list(text_revisions or [])
        if not hazir_rapor_path or not os.path.exists(hazir_rapor_path):
            return {"success": False, "message": "Revize edilecek Word raporu bulunamadı.", "updated": [], "missing": tags, "applied": [], "skipped": []}
        if not output_path:
            return {"success": False, "message": "Kaydedilecek çıktı yolu seçilmedi.", "updated": [], "missing": tags, "applied": [], "skipped": []}
        if os.path.abspath(hazir_rapor_path) == os.path.abspath(output_path):
            return {"success": False, "message": "Güvenlik için orijinal raporun üzerine yazılamaz. Lütfen yeni bir dosya adı seçin.", "updated": [], "missing": tags, "applied": [], "skipped": []}
        if not tags and not text_revisions:
            return {"success": False, "message": "Uygulanacak bölüm veya metin düzeltmesi seçilmedi.", "updated": [], "missing": [], "applied": [], "skipped": []}

        updated = []
        missing = []
        applied = []
        skipped = []
        messages = []

        with tempfile.TemporaryDirectory(prefix="raporpro_revizyon_") as tmp:
            source_path = hazir_rapor_path
            if tags:
                section_output = output_path if not text_revisions else os.path.join(tmp, "bolum_revize.docx")
                section_info = revizyonlu_rapor_olustur(context, hazir_rapor_path, tags, section_output)
                updated = list(section_info.get("updated") or [])
                missing = list(section_info.get("missing") or [])
                if section_info.get("success"):
                    source_path = section_output
                    messages.append(section_info.get("message", "Bölüm revizyonu tamamlandı."))
                elif not text_revisions:
                    return {
                        "success": False,
                        "message": section_info.get("message", "Bölüm revizyonu uygulanamadı."),
                        "updated": updated,
                        "missing": missing or tags,
                        "applied": [],
                        "skipped": [],
                    }
                else:
                    messages.append(f"Bölüm revizyonu uygulanamadı: {section_info.get('message', '')}")

            if text_revisions:
                text_info = metin_revizyonlari_uygula(source_path, text_revisions, output_path)
                applied = list(text_info.get("applied") or [])
                skipped = list(text_info.get("skipped") or [])
                if not text_info.get("success"):
                    return {
                        "success": False,
                        "message": text_info.get("message", "Metin revizyonu uygulanamadı."),
                        "updated": updated,
                        "missing": missing,
                        "applied": applied,
                        "skipped": skipped,
                    }
                messages.append(text_info.get("message", "Metin revizyonu tamamlandı."))

        if not messages:
            messages.append("Revizyonlu rapor oluşturuldu.")
        message = " ".join(msg for msg in messages if msg)
        return {
            "success": True,
            "message": message,
            "updated": updated,
            "missing": missing,
            "applied": applied,
            "skipped": skipped,
            "output_path": output_path,
        }

    @perf_tracked("report.selected_tags_dialog")
    def duzeltme_etiketleri_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Düzeltme Etiketleri", "780x620", (640, 480), modal=True)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text=(
                "İdare düzeltme istediğinde yalnızca seçtiğiniz etiketler güncel verilerle "
                "ayrı bir Word dosyası olarak oluşturulur."
            ),
            wraplength=720,
            justify="left",
        ).pack(fill="x", pady=(0, 10))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def refresh_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def refresh_width(event):
            canvas.itemconfigure(window_id, width=max(420, event.width - 8))

        inner.bind("<Configure>", refresh_scroll)
        canvas.bind("<Configure>", refresh_width)

        tag_vars = []
        for group_title, items in DUZELTME_ETIKET_GRUPLARI:
            group = ttk.LabelFrame(inner, text=group_title, padding=8)
            group.pack(fill="x", pady=(0, 8))
            for tag, label in items:
                var = tk.BooleanVar(value=False)
                cb = ttk.Checkbutton(group, text=f"{label}  ({tag})", variable=var)
                cb.pack(anchor="w", pady=2)
                tag_vars.append((tag, var))

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(12, 0))

        def set_all(value):
            for _tag, var in tag_vars:
                var.set(value)

        def create_selected():
            selected = [tag for tag, var in tag_vars if var.get()]
            if self.duzeltme_etiket_ciktisi_baslat(selected, parent=win):
                win.destroy()

        self.modern_button(btns, text="Tümünü Seç", command=lambda: set_all(True), role="neutral", outline=True).pack(side="left")
        self.modern_button(btns, text="Temizle", command=lambda: set_all(False), role="warning", outline=True).pack(side="left", padx=6)
        self.modern_button(btns, text="Kapat", command=win.destroy, role="neutral", outline=True).pack(side="right")
        self.modern_button(btns, text="Seçili Etiketleri Oluştur", command=create_selected, role="success").pack(side="right", padx=(0, 6))

    @perf_tracked("report.selected_tags.engine")
    def duzeltme_etiketleri_worker(self, context, tags, path):
        success, msg = duzeltme_etiket_ciktisi_olustur(context, tags, path)
        return path, success, msg, list(tags)

    def duzeltme_etiketleri_bitti(self, result):
        path, success, msg, tags = result
        self.set_status(msg, level="success" if success else "error")
        if success:
            messagebox.showinfo(
                "Düzeltme Etiketleri",
                f"{msg}\n\nDosya:\n{path}\n\nOluşturulan etiket sayısı: {len(tags)}",
            )
        else:
            messagebox.showerror("Düzeltme Etiketleri", msg)

    def rapor_arka_plan_context(self):
        return rapor_baglami_olustur(
            self,
            word_path=etkin_rapor_sablonu_yolu(self.word_path),
        )

    @perf_tracked("report.generate.engine")
    def raporla_worker(self, context, path):
        success, msg = rapor_olustur(context, final_path=path, autosave=False)
        quality_report = None
        manifest_path = ""
        if success:
            quality_report = cikti_dosyalari_denetle([path], veri=context.veri)
            manifest_path = os.path.splitext(path)[0] + "_Kalite.json"
            kalite_manifestosu_yaz(manifest_path, quality_report, veri=context.veri)
        return path, success, msg, quality_report, manifest_path

    def raporla_bitti(self, result):
        path, success, msg, quality_report, manifest_path = result
        self.last_output_quality_report = quality_report
        quality_errors = len((quality_report or {}).get("errors", []))
        quality_warnings = len((quality_report or {}).get("warnings", []))
        level = "success" if success and not quality_errors and not quality_warnings else ("warning" if success else "error")
        self.set_status(msg, level=level)
        if success:
            quality_text = f"Kalite denetimi: {quality_errors} hata, {quality_warnings} uyarı"
            message = (
                f"{msg}\n\nDosya:\n{path}\n\n{quality_text}\n"
                f"Kalite manifestosu:\n{manifest_path}\n\n"
                "Sonraki adım: Çıktı Merkezi ile log, kesit ve görselleri aynı çıktı klasöründe toplayabilirsiniz."
            )
            if quality_errors or quality_warnings:
                messagebox.showwarning("Rapor Oluşturuldu - Kalite Bulgusu Var", message)
            else:
                messagebox.showinfo("Başarılı", message)
        else:
            messagebox.showerror("Hata", msg)

    @perf_tracked("report.generate")
    def raporla(self):
        self.guncelle_veri_objesi()
        report = build_preflight_report(self)
        self.on_kontrol_raporunu_sakla(report)
        self.ozet_yenile(collect=False)
        if "blocking" in report:
            blockers = report.get("blocking", [])
        else:
            blockers = [{"detail": detail} for detail in report.get("errors", [])]
        if blockers:
            self.on_kontrol_penceresi(report)
            self.set_status("Rapor oluşturma durduruldu: ön kontrolde hata var.", level="error")
            messagebox.showerror(
                "Çıktı Ön Kontrol",
                f"Raporu etkileyen {len(blockers)} kritik bulgu var. "
                "Detayları Çıktı Ön Kontrol Merkezi'nde görebilirsiniz.",
            )
            return
        if report["warnings"]:
            self.on_kontrol_penceresi(report)
            devam = messagebox.askyesno(
                "Çıktı Ön Kontrol",
                f"{len(report['warnings'])} uyarı bulundu. Yine de rapor oluşturulsun mu?",
            )
            if not devam:
                self.set_status("Rapor oluşturma kullanıcı tarafından iptal edildi.", level="warning")
                return
        path = self.rapor_kayit_yolu_sec()
        if not path:
            self.set_status("Rapor oluşturma kullanıcı tarafından iptal edildi.", level="warning")
            return
        self.veri_kaydet()
        self.arka_plan_gorevi_baslat(
            "Rapor oluştur",
            self.raporla_worker,
            self.rapor_arka_plan_context(),
            path,
            resource="render",
            status_start="Rapor arka planda oluşturuluyor.",
            status_success="Rapor oluşturma işlemi tamamlandı.",
            status_error="Rapor oluşturulamadı: {error}",
            on_success=self.raporla_bitti,
            on_error=lambda exc: messagebox.showerror("Hata", str(exc)),
        )
