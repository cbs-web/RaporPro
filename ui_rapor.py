# Dosya: RaporPro/ui_rapor.py
import os
import threading
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

import matplotlib.pyplot as plt

from sabitler import COLOR_BG, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, DEFAULT_EXPORT_DPI, FONT_BOLD
from performans import perf_tracked
from proje_motoru import hesap_ozeti, proje_saglik_ozeti, rapor_onizleme_metni
from kalite_kontrol import build_preflight_report
from motor import GeoEngine
from raporlama import raporla as rapor_olustur
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


class RaporSekmesiMixin:
    def p_rapor(self, p):
        container = ttk.Frame(p)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=COLOR_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        center_frame = ttk.Frame(canvas, padding=14)
        content_window = canvas.create_window((0, 0), window=center_frame, anchor="n")
        file_labels = []
        drop_targets = []

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_width(event=None):
            width = event.width if event else canvas.winfo_width()
            content_width = max(380, min(width - 26, 920))
            canvas.itemconfigure(content_window, width=content_width)
            canvas.coords(content_window, max(width / 2, content_width / 2), 0)
            for label in file_labels:
                try:
                    label.configure(wraplength=max(260, content_width - 260))
                except Exception:
                    pass

        center_frame.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_width)

        def file_row(parent, title, label_attr, empty_text, button_text, command):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=title, width=20, font=FONT_BOLD).pack(side="left", padx=(0, 8))
            label = ttk.Label(row, text=empty_text, foreground="red", anchor="w", justify="left")
            label.pack(side="left", fill="x", expand=True, padx=(0, 8))
            file_labels.append(label)
            setattr(self, label_attr, label)
            btn = self.modern_button(row, text=button_text, command=command, role="neutral", outline=True, width=18)
            btn.pack(side="right")
            self.tooltip_ekle(btn, f"{title} için dosya seç")
            return row

        def update_drop_label():
            if hasattr(self, "lbl_rapor_drop"):
                self.lbl_rapor_drop.config(text="Dosyaları buraya bırakabilirsiniz", foreground="#2874A6")

        def refresh_report_labels():
            if hasattr(self, "lbl_sab"):
                self.lbl_sab.config(
                    text=os.path.basename(self.word_path) if self.word_path else "Word şablonu seçilmedi",
                    foreground=COLOR_SUCCESS if self.word_path else "red",
                )
            if hasattr(self, "lbl_lab"):
                self.lbl_lab.config(
                    text=os.path.basename(self.lab_excel_path) if self.lab_excel_path else "Laboratuvar Excel seçilmedi",
                    foreground=COLOR_SUCCESS if self.lab_excel_path else "red",
                )
            if hasattr(self, "lbl_jeo_excel"):
                self.lbl_jeo_excel.config(
                    text=os.path.basename(self.jeo_excel_path) if self.jeo_excel_path else "Jeofizik Excel seçilmedi",
                    foreground=COLOR_SUCCESS if self.jeo_excel_path else "red",
                )
            for attr, path in [
                ("lbl_yer", self.img_yer),
                ("lbl_tkgm", self.img_tkgm),
                ("lbl_pga", self.img_pga),
                ("lbl_mjh", self.img_mjh),
            ]:
                if hasattr(self, attr):
                    label = getattr(self, attr)
                    label.config(text=os.path.basename(path) if path else "-", foreground=COLOR_SUCCESS if path else "#555555")
            self.ek_etiketlerini_guncelle()

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
            refresh_report_labels()
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
                update_drop_label()

        header = ttk.Frame(center_frame)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Rapor Hazırlığı", font=("Segoe UI", 15, "bold"), foreground=COLOR_PRIMARY).pack(side="left")
        self.lbl_rapor_drop = ttk.Label(header, text="", foreground="#777777")
        self.lbl_rapor_drop.pack(side="right")

        flow = ttk.LabelFrame(center_frame, text="Ana Akış", padding=12)
        flow.pack(fill="x", pady=(0, 10))
        drop_targets.extend([flow, center_frame, canvas])
        file_row(flow, "Word Şablonu", "lbl_sab", "Word şablonu seçilmedi", "Seç", self.sablon_sec)
        file_row(flow, "Lab Excel", "lbl_lab", "Laboratuvar Excel seçilmedi", "Seç", self.lab_excel_sec)
        file_row(flow, "Jeofizik Excel", "lbl_jeo_excel", "Jeofizik Excel seçilmedi", "Seç", self.jeo_excel_sec)

        f_img = ttk.LabelFrame(center_frame, text="Görseller", padding=12)
        f_img.pack(fill="x", pady=(0, 10))
        drop_targets.append(f_img)
        image_grid = ttk.Frame(f_img)
        image_grid.pack(fill="x")
        image_cards = []
        for k, txt, cmd in [
            ("yer", "Yerbuldurur", lambda: self.resim_sec("yer")),
            ("tkgm", "TKGM", lambda: self.resim_sec("tkgm")),
            ("pga", "PGA", lambda: self.resim_sec("pga")),
            ("mjh", "MJH", lambda: self.resim_sec("mjh")),
        ]:
            card = ttk.Frame(image_grid)
            l = ttk.Label(card, text="-", anchor="w", justify="left")
            l.pack(fill="x", pady=(0, 4))
            file_labels.append(l)
            self.modern_button(card, text=txt, command=cmd, role="neutral", outline=True).pack(fill="x")
            if k == "yer":
                self.lbl_yer = l
            elif k == "tkgm":
                self.lbl_tkgm = l
            elif k == "pga":
                self.lbl_pga = l
            elif k == "mjh":
                self.lbl_mjh = l
            image_cards.append(card)
        self.responsive_widget_grid(image_grid, image_cards, min_width=180, max_cols=4, padx=4, pady=4)

        actions = ttk.LabelFrame(center_frame, text="Rapor İşlemleri", padding=12)
        actions.pack(fill="x", pady=(0, 10))
        primary_row = ttk.Frame(actions)
        primary_row.pack(fill="x")
        self.modern_button(primary_row, text="Ön Kontrol", command=self.rapor_on_kontrol, role="warning").pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.modern_button(primary_row, text="Önizleme", command=self.rapor_onizleme_penceresi, role="accent").pack(side="left", fill="x", expand=True, padx=4)
        self.toolbar_menu(
            primary_row,
            "Gelişmiş",
            [
                ("Final Kontrol", self.final_kontrol_penceresi),
                ("Çıktı Merkezi", self.cikti_merkezi_penceresi),
                ("Sadece Grafikleri Çıkar", self.grafikleri_kaydet),
            ],
            bg="#ECF0F1",
            fg="#111111",
            role="secondary",
            tooltip="Rapor ek işlemleri",
        )

        btn_rapor = self.modern_button(
            center_frame,
            text="Raporu Oluştur",
            role="success",
            pady=10,
            command=self.raporla,
        )
        btn_rapor.pack(fill="x", pady=(0, 12))
        self.tooltip_ekle(btn_rapor, "Ön kontrol uygunsa Word raporunu üretir")
        taahhut = ttk.LabelFrame(center_frame, text="Taahhütnameler", padding=12)
        taahhut.pack(fill="x", pady=(0, 10))
        taahhut_row = ttk.Frame(taahhut)
        taahhut_row.pack(fill="x")
        self.modern_button(taahhut_row, text="Jeoloji", command=lambda: self.taahhutname_kaydet("jeoloji"), role="primary", outline=True).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.modern_button(taahhut_row, text="Jeofizik", command=lambda: self.taahhutname_kaydet("jeofizik"), role="accent", outline=True).pack(side="left", fill="x", expand=True, padx=4)
        self.modern_button(taahhut_row, text="İkisini Oluştur", command=self.taahhutnameleri_kaydet, role="success").pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(
            taahhut,
            text="Yapı adresi ve yapı sahibinin adresi proje künyesindeki Mahalle / İlçe / İl bilgisinden alınır.",
            foreground="#555555",
        ).pack(anchor="w", pady=(8, 0))

        ekler = ttk.LabelFrame(center_frame, text="Ekler", padding=12)
        ekler.pack(fill="x", pady=(0, 10))
        drop_targets.append(ekler)
        ek_action_row = ttk.Frame(ekler)
        ek_action_row.pack(fill="x")
        self.modern_button(ek_action_row, text="Normal Ekler", command=lambda: self.ekler_merkezi_penceresi(EK_SET_NORMAL), role="primary", outline=True).pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.modern_button(ek_action_row, text="Arazi Deneyli Ekler", command=lambda: self.ekler_merkezi_penceresi(EK_SET_ARAZI_DENEYLI), role="accent", outline=True).pack(side="left", fill="x", expand=True, padx=5)
        self.modern_button(ek_action_row, text="Tutanak Oluştur", command=self.tutanaklari_kaydet, role="warning", outline=True).pack(side="left", fill="x", expand=True, padx=5)
        self.modern_button(ek_action_row, text="Ekler PDF Oluştur", command=self.ekler_pdf_kaydet, role="success").pack(side="left", fill="x", expand=True, padx=(5, 0))
        ek_status_row = ttk.Frame(ekler)
        ek_status_row.pack(fill="x", pady=(8, 0))
        self.lbl_ek_durum = ttk.Label(ek_status_row, text="-", foreground="#555555")
        self.lbl_ek_durum.pack(side="left", fill="x", expand=True)
        refresh_report_labels()
        enable_report_drop()
        self.root.after_idle(update_width)

    @perf_tracked("report.preview")
    def rapor_onizleme_penceresi(self):
        self.guncelle_veri_objesi(silent=True)
        health = proje_saglik_ozeti(self.veri, self._dosya_map())
        summary = hesap_ozeti(self.veri)
        text = rapor_onizleme_metni(self.veri, self._dosya_map(), health, summary)
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Rapor Önizleme", "760x620", (680, 460), modal=True)
        txt = tk.Text(win, wrap="word", font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", text)
        txt.config(state="disabled")
        self.modern_button(win, text="Kapat", command=win.destroy, role="primary").pack(pady=(0, 10))

    def sablon_sec(self):
        f = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
        if f:
            self.word_path = f
            self.lbl_sab.config(text=os.path.basename(f), foreground=COLOR_SUCCESS)

    def lab_excel_sec(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if f:
            self.lab_excel_path = f
            self.lbl_lab.config(text=os.path.basename(f), foreground=COLOR_SUCCESS)

    def jeo_excel_sec(self):
        f = filedialog.askopenfilename(filetypes=[("Excel Dosyaları", "*.xlsx;*.xls;*.csv")])
        if f:
            self.jeo_excel_path = f
            self.lbl_jeo_excel.config(text=os.path.basename(f), foreground=COLOR_SUCCESS)

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
        try:
            info = ekler_pdf_olustur(self.veri, path, set_key=set_key)
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
        except Exception as exc:
            self.set_status(f"Ekler PDF oluşturulamadı: {exc}", level="error")
            messagebox.showerror("Ekler", str(exc))

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
        try:
            info = tutanaklari_olustur(self.veri, path, getattr(self, "word_img_sondaj", None))
            self.tutanak_eklere_bagla(path)
            self.set_status(f"Tutanaklar oluşturuldu: {os.path.basename(path)}", level="success")
            messagebox.showinfo(
                "Tutanaklar",
                f"Tutanaklar oluşturuldu:\n{path}\n\n"
                f"Sondaj tutanağı: {info['sondaj_count']}\n"
                f"Jeofizik tutanağı: {info['jeofizik_count']}\n\n"
                "Dosya EK-10 TUTANAKLAR bölümüne bağlandı.",
            )
        except Exception as exc:
            self.set_status(f"Tutanaklar oluşturulamadı: {exc}", level="error")
            messagebox.showerror("Tutanaklar", str(exc))

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
        try:
            taahhutname_olustur(self.veri, tur, path)
            self.set_status(f"Taahhütname oluşturuldu: {os.path.basename(path)}", level="success")
            messagebox.showinfo("Taahhütname", f"Taahhütname oluşturuldu:\n{path}")
        except Exception as exc:
            self.set_status(f"Taahhütname oluşturulamadı: {exc}", level="error")
            messagebox.showerror("Taahhütname", str(exc))

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
        paths = []
        errors = []
        try:
            paths.extend(tum_taahhutnameleri_olustur(self.veri, folder, ext))
        except Exception as exc:
            label = "PDF" if ext == ".pdf" else "Excel"
            errors.append(f"{label}: {exc}")
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
        worker = threading.Thread(target=self.save_figures_threaded, args=(klasor,), daemon=True)
        worker.start()

    @perf_tracked("figures.export_all")
    def save_figures_threaded(self, klasor):
        try:
            for s in self.veri["sondaj"]:
                self.set_status(f"Çizim başlatılıyor: {s['no']}...", level="info")
                figures = GeoEngine.ciz_profesyonel_log(s, self.veri)
                for idx, fig in enumerate(figures):
                    fig.savefig(f"{klasor}/Log_{s['no']}_Sayfa{idx + 1}.jpg", dpi=DEFAULT_EXPORT_DPI, bbox_inches="tight")
                    plt.close(fig)
            self.set_status("Jeolojik Kesit çiziliyor...", level="info")
            fig_k, _ = GeoEngine.kesit_ciz_interaktif(self.veri["sondaj"])
            fig_k.savefig(os.path.join(klasor, "Jeolojik_Kesit.jpg"), dpi=DEFAULT_EXPORT_DPI, bbox_inches="tight")
            plt.close(fig_k)
            self.root.after(0, lambda: messagebox.showinfo("Başarılı", f"Tüm grafikler kaydedildi:\n{klasor}"))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("Hata", str(exc)))

    @perf_tracked("report.preflight")
    def rapor_on_kontrol(self):
        self.guncelle_veri_objesi()
        report = build_preflight_report(self)
        self.last_preflight_report = report
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
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Rapor Ön Kontrol", "760x520", (680, 430), modal=True)
        txt = tk.Text(win, wrap="word", font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        self._insert_clickable_report(txt, report)
        self.modern_button(win, text="Kapat", command=win.destroy, role="primary").pack(pady=(0, 10))

    @perf_tracked("report.generate")
    def raporla(self):
        self.guncelle_veri_objesi()
        report = build_preflight_report(self)
        self.last_preflight_report = report
        self.ozet_yenile(collect=False)
        if report["errors"]:
            self.on_kontrol_penceresi(report)
            self.set_status("Rapor oluşturma durduruldu: ön kontrolde hata var.", level="error")
            messagebox.showerror("Rapor Ön Kontrol", "Hata bulundu. Detayları ön kontrol penceresinde görebilirsiniz.")
            return
        if report["warnings"]:
            self.on_kontrol_penceresi(report)
            devam = messagebox.askyesno("Rapor Ön Kontrol", f"{len(report['warnings'])} uyarı bulundu. Yine de rapor oluşturulsun mu?")
            if not devam:
                self.set_status("Rapor oluşturma kullanıcı tarafından iptal edildi.", level="warning")
                return
        success, msg = rapor_olustur(self)
        level = "success" if success else "error"
        self.set_status(msg, level=level)
        if success:
            messagebox.showinfo("Başarılı", f"{msg}\n\nSonraki adım: Çıktı Merkezi ile log, kesit ve görselleri aynı çıktı klasöründe toplayabilirsiniz.")
        else:
            messagebox.showerror("Hata", msg)
