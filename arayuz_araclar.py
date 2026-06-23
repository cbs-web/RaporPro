# Dosya: RaporPro/arayuz_araclar.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Toplevel

from sabitler import *
from yardimcilar import *
from performans import perf_tracked
from harita_motoru import TopluHarita
from kalite_kontrol import analyze_word_template, format_template_analysis, get_supported_tags


class ArayuzAraclarMixin:
    def kml_sec(self):
        f = filedialog.askopenfilename(filetypes=[("KML Dosyası", "*.kml")])
        if f: 
            self.kml_path = f
            self.veri.setdefault("dosyalar", {})["kml_path"] = f
            self.kml_etiket_guncelle()
            self.set_status("KML Altlığı Yüklendi.", level="success")

    @perf_tracked("map.bulk_open")
    def toplu_harita_ac(self):
        self.guncelle_veri_objesi()
        def coord_pair(y, x):
            yv, xv = safe_float(y), safe_float(x)
            return (yv, xv) if yv != 0 and xv != 0 else None

        initial = {"alan": None, "sondaj": {}, "ss": {}, "mt": {}}
        initial["alan"] = coord_pair(self.veri.get("arazi", {}).get("alan_y"), self.veri.get("arazi", {}).get("alan_x"))
        for idx, sondaj in enumerate(self.veri.get("sondaj", [])):
            coords = coord_pair(sondaj.get("y"), sondaj.get("x"))
            if coords:
                initial["sondaj"][idx] = coords
        for idx, ss in enumerate(self.veri.get("jeofizik", {}).get("ss_list", [])):
            coords = ss.get("coords", [])
            if len(coords) >= 6:
                parsed = [safe_float(value) for value in coords[:6]]
                if parsed[0] and parsed[1] and parsed[4] and parsed[5]:
                    if not (parsed[2] and parsed[3]):
                        parsed[2] = (parsed[0] + parsed[4]) / 2
                        parsed[3] = (parsed[1] + parsed[5]) / 2
                    initial["ss"][idx] = parsed
        for idx, mt in enumerate(self.veri.get("jeofizik", {}).get("mt_list", [])):
            coords = coord_pair(mt.get("y"), mt.get("x"))
            if coords:
                initial["mt"][idx] = coords

        map_data = {
            "sondaj": [s.get("no", f"SK-{i+1}") for i, s in enumerate(self.veri["sondaj"])],
            "ss": [s.get("ad", f"SS-{i+1}") for i, s in enumerate(self.veri["jeofizik"]["ss_list"])],
            "mt": [m.get("no", f"MT-{i+1}") for i, m in enumerate(self.veri["jeofizik"]["mt_list"])],
            "initial": initial,
        }
        TopluHarita(self.root, kml_path=self.kml_path, map_data=map_data, callback=self.toplu_koordinat_kaydet)

    def toplu_koordinat_kaydet(self, results):
        if results.get("alan"):
            self.veri["arazi"]["alan_y"] = f"{results['alan'][0]:.6f}"
            self.veri["arazi"]["alan_x"] = f"{results['alan'][1]:.6f}"
            
        for idx, coords in results.get("sondaj", {}).items():
            self.veri["sondaj"][idx]["y"] = f"{coords[0]:.6f}"
            self.veri["sondaj"][idx]["x"] = f"{coords[1]:.6f}"
            
        for idx, coords in results.get("ss", {}).items():
            str_coords = [f"{c:.6f}" for c in coords]
            self.veri["jeofizik"]["ss_list"][idx]["coords"] = str_coords
            
        for idx, coords in results.get("mt", {}).items():
            self.veri["jeofizik"]["mt_list"][idx]["y"] = f"{coords[0]:.6f}"
            self.veri["jeofizik"]["mt_list"][idx]["x"] = f"{coords[1]:.6f}"
            
        self.doldur_arayuz()
        self.set_status("Tüm harita koordinatları arayüze aktarıldı!", level="success")

    def global_undo(self):
        widget = self.root.focus_get()
        if not callable(getattr(widget, "undo", None)) and self.last_focused:
            widget = self.last_focused
        if callable(getattr(widget, "undo", None)):
            widget.undo()
    def global_redo(self):
        widget = self.root.focus_get()
        if not callable(getattr(widget, "redo", None)) and self.last_focused:
            widget = self.last_focused
        if callable(getattr(widget, "redo", None)):
            widget.redo()

    def ayarlar_penceresi(self):
        self.veri_eksikleri_tamamla(self.veri, self.varsayilan_veri_olustur())
        ayarlar = self.veri.setdefault("ayarlar", {})
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Ayarlar", "760x560", (680, 480), modal=True)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=12)
        form = ttk.Frame(nb, padding=15)
        taahhut_form = ttk.Frame(nb, padding=15)
        nb.add(form, text="Genel")
        nb.add(taahhut_form, text="Taahhütname")

        fields = [
            ("Firma adı", "firma_adi"),
            ("Log başlığı", "log_baslik"),
            ("Sorumlu unvanı", "sorumlu_muhendis_unvan"),
            ("Sorumlu mühendis", "sorumlu_muhendis"),
            ("Sondör başlığı", "sondor_belge_baslik"),
            ("Sondor / belge", "sondor_belge"),
            ("Makine metodu", "makine_metodu"),
            ("SPT şahmerdan tipi", "spt_sahmerdan"),
            ("Delgi çapı", "delgi_capi"),
            ("Yedek sayısı", "yedek_sayisi"),
        ]

        entries = {}
        for row_idx, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row_idx, column=0, sticky="e", padx=6, pady=5)
            entry = ttk.Entry(form, width=48)
            entry.grid(row=row_idx, column=1, sticky="ew", padx=6, pady=5)
            entry.insert(0, ayarlar.get(key, ""))
            entries[key] = entry

        start_row = len(fields)
        ttk.Label(form, text="Varsayılan Word şablonu").grid(row=start_row, column=0, sticky="e", padx=6, pady=5)
        word_entry = ttk.Entry(form, width=48)
        word_entry.grid(row=start_row, column=1, sticky="ew", padx=6, pady=5)
        word_entry.insert(0, ayarlar.get("varsayilan_word_path", ""))
        entries["varsayilan_word_path"] = word_entry
        tk.Button(form, text="Seç", command=lambda: self._ayar_dosya_sec(word_entry, [("Word", "*.docx")]), bg="#ECF0F1").grid(row=start_row, column=2, padx=6, pady=5)

        out_row = start_row + 1
        ttk.Label(form, text="Varsayılan çıktı klasörü").grid(row=out_row, column=0, sticky="e", padx=6, pady=5)
        out_entry = ttk.Entry(form, width=48)
        out_entry.grid(row=out_row, column=1, sticky="ew", padx=6, pady=5)
        out_entry.insert(0, ayarlar.get("varsayilan_cikti_klasor", ""))
        entries["varsayilan_cikti_klasor"] = out_entry
        tk.Button(form, text="Seç", command=lambda: self._ayar_klasor_sec(out_entry), bg="#ECF0F1").grid(row=out_row, column=2, padx=6, pady=5)

        form.columnconfigure(1, weight=1)

        ttk.Label(taahhut_form, text="İlgili idare").grid(row=0, column=0, sticky="e", padx=6, pady=5)
        idare_entry = ttk.Entry(taahhut_form, width=48)
        idare_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=6, pady=5)
        idare_entry.insert(0, ayarlar.get("taahhut_ilgili_idare", ""))
        entries["taahhut_ilgili_idare"] = idare_entry

        ttk.Label(taahhut_form, text="Tarih").grid(row=1, column=0, sticky="e", padx=6, pady=5)
        tarih_entry = ttk.Entry(taahhut_form, width=18)
        tarih_entry.grid(row=1, column=1, sticky="w", padx=6, pady=5)
        tarih_entry.insert(0, ayarlar.get("taahhut_tarih", ""))
        entries["taahhut_tarih"] = tarih_entry
        ttk.Label(taahhut_form, text="Boşsa bugünün tarihi kullanılır. Yapı adresi ve yapı sahibinin adresi: Mahalle / İlçe / İl.").grid(row=1, column=2, columnspan=2, sticky="w", padx=6, pady=5)

        ttk.Label(taahhut_form, text="Excel şablonu").grid(row=2, column=0, sticky="e", padx=6, pady=5)
        taahhut_template_entry = ttk.Entry(taahhut_form, width=48)
        taahhut_template_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=6, pady=5)
        taahhut_template_entry.insert(0, ayarlar.get("taahhut_excel_sablon_path", ""))
        entries["taahhut_excel_sablon_path"] = taahhut_template_entry
        self.modern_button(
            taahhut_form,
            text="Seç",
            command=lambda: self._ayar_dosya_sec(taahhut_template_entry, [("Excel", "*.xlsx")]),
            role="neutral",
            outline=True,
        ).grid(row=2, column=3, padx=6, pady=5)

        def taahhut_profile_frame(parent, title, prefix, col):
            frame = ttk.LabelFrame(parent, text=title, padding=10)
            frame.grid(row=3, column=col, columnspan=2, sticky="nsew", padx=6, pady=(12, 5))
            specs = [
                ("Ad Soyad", "ad"),
                ("Oda sicil no", "sicil"),
                ("Unvan", "unvan"),
                ("İmza unvanı", "imza_unvan"),
                ("Adres", "adres"),
                ("Telefon", "telefon"),
            ]
            for row_idx, (label, suffix) in enumerate(specs):
                key = f"{prefix}_{suffix}"
                ttk.Label(frame, text=label).grid(row=row_idx, column=0, sticky="e", padx=5, pady=4)
                entry = ttk.Entry(frame, width=28)
                entry.grid(row=row_idx, column=1, sticky="ew", padx=5, pady=4)
                entry.insert(0, ayarlar.get(key, ""))
                entries[key] = entry
            frame.columnconfigure(1, weight=1)

        taahhut_profile_frame(taahhut_form, "Jeoloji Mühendisi", "taahhut_jeoloji", 0)
        taahhut_profile_frame(taahhut_form, "Jeofizik Mühendisi", "taahhut_jeofizik", 2)
        for col in range(4):
            taahhut_form.columnconfigure(col, weight=1)

        def kaydet():
            for key, entry in entries.items():
                ayarlar[key] = entry.get().strip()
            try:
                keep = int(ayarlar.get("yedek_sayisi", "10"))
                ayarlar["yedek_sayisi"] = str(max(1, keep))
            except Exception:
                ayarlar["yedek_sayisi"] = "10"
                messagebox.showwarning("Ayarlar", "Yedek sayısı geçersizdi; 10 olarak ayarlandı.")

            self.ayarlari_uygula()
            self.set_status("Ayarlar güncellendi.", level="success")
            if self.aktif_dosya_yolu:
                self.veri_kaydet()
            win.destroy()

        btns = ttk.Frame(win, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        tk.Button(btns, text="Kaydet", command=kaydet, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=5)
        tk.Button(btns, text="Vazgeç", command=win.destroy, bg="#ECF0F1").pack(side="right", padx=5)

    def _ayar_dosya_sec(self, entry, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _ayar_klasor_sec(self, entry):
        path = filedialog.askdirectory()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def ayarlari_uygula(self):
        ayarlar = self.veri.get("ayarlar", {})
        default_word = ayarlar.get("varsayilan_word_path")
        if not self.word_path and default_word and os.path.exists(default_word):
            self.word_path = default_word
            if hasattr(self, 'lbl_sab'):
                self.lbl_sab.config(text=os.path.basename(self.word_path), foreground=COLOR_SUCCESS)

    def etiket_yoneticisi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Word Etiket Yöneticisi", "980x640", (820, 520), modal=True)

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        tab_supported = ttk.Frame(notebook)
        tab_template = ttk.Frame(notebook)
        notebook.add(tab_supported, text="Desteklenen Etiketler")
        notebook.add(tab_template, text="Şablon Analizi")

        supported = get_supported_tags()
        paned = tk.PanedWindow(tab_supported, orient=tk.HORIZONTAL, sashwidth=4, bg=COLOR_BG)
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=8)
        paned.add(left, width=360)
        paned.add(right, width=580)

        search_var = tk.StringVar()
        ttk.Label(left, text="Ara").pack(anchor="w")
        search_entry = ttk.Entry(left, textvariable=search_var)
        search_entry.pack(fill="x", pady=(0, 6))

        tag_list = tk.Listbox(left, height=24, font=("Consolas", 10))
        tag_list.pack(fill="both", expand=True)

        detail = tk.Text(right, wrap="word", font=("Consolas", 10))
        detail.pack(fill="both", expand=True)

        filtered_items = []

        def refresh_tag_list(*_):
            filtered_items.clear()
            tag_list.delete(0, tk.END)
            query = search_var.get().strip().lower()
            for item in supported:
                haystack = f"{item['tag']} {item['category']} {item['description']}".lower()
                if query and query not in haystack:
                    continue
                filtered_items.append(item)
                tag_list.insert(tk.END, f"{item['tag']}  [{item['category']}]")
            if filtered_items:
                tag_list.selection_set(0)
                show_tag_detail()

        def show_tag_detail(event=None):
            sel = tag_list.curselection()
            if not sel:
                return
            item = filtered_items[sel[0]]
            detail.config(state="normal")
            detail.delete("1.0", tk.END)
            detail.insert(tk.END, f"Etiket: {item['tag']}\n")
            detail.insert(tk.END, f"Tur: {item['category']}\n\n")
            detail.insert(tk.END, item["description"])
            detail.config(state="disabled")

        search_var.trace_add("write", refresh_tag_list)
        tag_list.bind("<<ListboxSelect>>", show_tag_detail)
        refresh_tag_list()

        top = ttk.Frame(tab_template, padding=8)
        top.pack(fill="x")
        selected_path = tk.StringVar(value=self.word_path or "")
        ttk.Label(top, text="Şablon").pack(side="left", padx=(0, 6))
        path_entry = ttk.Entry(top, textvariable=selected_path)
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        analysis_text = tk.Text(tab_template, wrap="word", font=("Consolas", 10))
        analysis_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        def show_analysis(path):
            analysis = analyze_word_template(path)
            analysis_text.config(state="normal")
            analysis_text.delete("1.0", tk.END)
            analysis_text.insert("1.0", format_template_analysis(analysis))
            analysis_text.config(state="disabled")
            if analysis.get("error"):
                self.set_status("Etiket analizi tamamlanamadi.", level="error")
            elif analysis.get("unknown"):
                self.set_status(f"Etiket analizi {len(analysis['unknown'])} bilinmeyen etiket buldu.", level="warning")
            else:
                self.set_status("Etiket analizi tamamlandi.", level="success")

        def choose_and_scan():
            path = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
            if not path:
                return
            selected_path.set(path)
            self.word_path = path
            if hasattr(self, 'lbl_sab'):
                self.lbl_sab.config(text=os.path.basename(path), foreground=COLOR_SUCCESS)
            show_analysis(path)

        def set_default_template():
            path = selected_path.get().strip()
            if not path or not os.path.exists(path):
                messagebox.showwarning("Word", "Varsayılan yapmak için önce geçerli bir Word şablonu seçin.")
                return
            self.word_path = path
            self.veri.setdefault("ayarlar", {})["varsayilan_word_path"] = path
            if hasattr(self, 'lbl_sab'):
                self.lbl_sab.config(text=os.path.basename(path), foreground=COLOR_SUCCESS)
            self.set_status(f"Varsayılan Word şablonu ayarlandı: {os.path.basename(path)}", level="success")

        tk.Button(top, text="Tara", command=lambda: show_analysis(selected_path.get()), bg=COLOR_PRIMARY, fg="white").pack(side="left", padx=3)
        tk.Button(top, text="Word Seç", command=choose_and_scan, bg="#ECF0F1").pack(side="left", padx=3)
        tk.Button(top, text="Varsayılan Yap", command=set_default_template, bg="#D6EAF8").pack(side="left", padx=3)

        if selected_path.get():
            show_analysis(selected_path.get())
        else:
            analysis_text.insert("1.0", "Şablon analizi için önce Word dosyası seçin.")
            analysis_text.config(state="disabled")

    def notebook_tab_changed(self, event):
        if hasattr(self, "tab_ozet") and event.widget.select() == str(self.tab_ozet):
            self.ozet_yenile()
        elif hasattr(self, "tab_haritalar") and event.widget.select() == str(self.tab_haritalar):
            self.kml_etiket_guncelle()
