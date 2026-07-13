import os
import tkinter as tk
from tkinter import filedialog, ttk

from motor import GeoEngine
from performans import perf_tracked
from sabitler import COLOR_BG, COLOR_SUCCESS, COLOR_WARNING
from widgets import UndoRedoEntry


class JeofizikMixin:
    def p_jeofizik(self, p):
        # ÜST BAR: Tarih ve Excel Yükleme Butonu
        top = ttk.Frame(p, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Rapor Tarihi:").pack(side="left")
        self.e_jeo_tar = UndoRedoEntry(top)
        jeo_tarih = self.veri.get("jeofizik", {}).get("tarih", "") if hasattr(self, "veri") else ""
        if jeo_tarih:
            self.e_jeo_tar.insert(0, jeo_tarih)
        self.e_jeo_tar.pack(side="left", padx=5)

        # YENİ BUTON: Jeofizik Excel Yükle
        tk.Button(top, text="Jeofizik Excel'den Veri Al", command=self.jeo_excel_yukle_ve_onizle,
                  bg="#34495E", fg="white", font=("Arial", 9, "bold")).pack(side="left", padx=20)
        tk.Button(top, text="Jeofizik Sheet", command=self.jeofizik_sheet_ac,
                  bg="#1F618D", fg="white", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 8))

        # ANA BÖLÜM (Sismik - MT - Detaylar ve Önizleme)
        pan_main = tk.PanedWindow(p, orient=tk.VERTICAL, bg=COLOR_BG, sashwidth=4)
        pan_main.pack(fill="both", expand=True, padx=5, pady=5)

        # Üst Kısım: Listeler ve Detaylar
        pan_lists = tk.PanedWindow(pan_main, orient=tk.HORIZONTAL, bg=COLOR_BG, sashwidth=4)

        # Sismik (Sol)
        left = ttk.LabelFrame(pan_lists, text="Sismik", padding=5)
        pan_lists.add(left, width=220)
        tk.Button(left, text="+ YENİ", command=self.jeo_ekle).pack(fill="x")
        self.jeo_lb = tk.Listbox(left, height=10)
        self.jeo_lb.pack(fill="both", expand=True)
        self.jeo_lb.bind("<<ListboxSelect>>", self.jeo_sec)
        tk.Button(left, text="- SİL", command=self.jeo_sil).pack(fill="x")

        # Mikrotremör (Orta)
        mid = ttk.LabelFrame(pan_lists, text="Mikrotremör", padding=5)
        pan_lists.add(mid, width=220)
        tk.Button(mid, text="+ YENİ", command=self.mt_ekle).pack(fill="x")
        self.mt_lb = tk.Listbox(mid, height=10)
        self.mt_lb.pack(fill="both", expand=True)
        self.mt_lb.bind("<<ListboxSelect>>", self.mt_sec)
        tk.Button(mid, text="- SİL", command=self.mt_sil).pack(fill="x")

        # Detay Paneli (Sağ)
        self.jeo_right = ttk.Frame(pan_lists, padding=10)
        pan_lists.add(self.jeo_right)

        # -- SİSMİK DETAY PANELİ (Geri Getirilen Kısım) --
        self.f_ss_detay = ttk.Frame(self.jeo_right)
        coord_f = ttk.LabelFrame(self.f_ss_detay, text="Koordinatlar (Tablo 3 İçin)", padding=10)
        coord_f.pack(fill="x")
        self.jeo_coords = []
        for i, l in enumerate(["DY","DX","OY","OX","TY","TX"]):
            ttk.Label(coord_f, text=l).pack(side="left")
            e = UndoRedoEntry(coord_f, width=10)
            e.pack(side="left")
            self.jeo_coords.append(e)

        layer_f = ttk.LabelFrame(self.f_ss_detay, text="Tabakalar", padding=10)
        layer_f.pack(fill="both", expand=True)
        self.layer_rows = []
        for i in range(5):
            r = ttk.Frame(layer_f)
            r.pack(fill="x")
            ttk.Label(r, text=f"{i+1}").pack(side="left")
            ents = []
            for _ in range(4):
                e = UndoRedoEntry(r, width=7)
                e.pack(side="left")
                ents.append(e)
            res_lbls = []
            for _ in range(5):
                l = tk.Label(r, text="-", width=7, bg="#ecf0f1")
                l.pack(side="left")
                res_lbls.append(l)
            self.layer_rows.append({"ents": ents, "lbls": res_lbls})
        tk.Button(self.f_ss_detay, text="HESAPLA", command=self.jeo_hesapla, bg=COLOR_WARNING, fg="white").pack(pady=10)

        # -- MİKROTREMÖR DETAY PANELİ (Geri Getirilen Kısım) --
        self.f_mt_detay = ttk.Frame(self.jeo_right)
        mt_cnt = ttk.LabelFrame(self.f_mt_detay, text="Mikrotremör (MT) Veri Girişi", padding=20)
        mt_cnt.pack(fill="x")

        ttk.Label(mt_cnt, text="Enlem (Y):").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.e_mt_y = UndoRedoEntry(mt_cnt, width=15)
        self.e_mt_y.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(mt_cnt, text="Boylam (X):").grid(row=0, column=2, sticky="e", padx=5, pady=5)
        self.e_mt_x = UndoRedoEntry(mt_cnt, width=15)
        self.e_mt_x.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        ttk.Separator(mt_cnt, orient='horizontal').grid(row=1, column=0, columnspan=4, sticky="ew", pady=15)

        self.e_mt_details = {}
        lbls_keys = [("Baskın Frekans (Hz):", "freq"), ("Baskın Periyot To (sn):", "to"), ("Ta (sn):", "ta"), ("Tb (sn):", "tb"), ("H/V Oranı:", "hv"), ("Kayıt Süresi (dk):", "sure")]

        for i, (lbl, k) in enumerate(lbls_keys):
            r = 2 + (i // 2)
            c = (i % 2) * 2
            ttk.Label(mt_cnt, text=lbl).grid(row=r, column=c, sticky="e", padx=5, pady=5)
            e = UndoRedoEntry(mt_cnt, width=15)
            e.grid(row=r, column=c+1, sticky="w", padx=5, pady=5)
            self.e_mt_details[k] = e

        tk.Button(self.f_mt_detay, text="Mikrotremör Verilerini Kaydet", bg=COLOR_SUCCESS, fg="white", font=("Arial", 10, "bold"), command=self.mt_kaydet).pack(pady=15)

        # Alt Kısım: TABLO ÖNİZLEME PANELİ (Yeni)
        self.f_jeo_preview = ttk.LabelFrame(pan_main, text="Rapor Tablo Önizlemeleri (Excel'den Okunan)", padding=10)
        self.nb_preview = ttk.Notebook(self.f_jeo_preview)
        self.nb_preview.pack(fill="both", expand=True)

        self.txt_pre_param = tk.Text(self.nb_preview, height=10, font=("Courier New", 9))
        self.txt_pre_masw = tk.Text(self.nb_preview, height=10, font=("Courier New", 9))
        self.nb_preview.add(self.txt_pre_param, text="Parametreler")
        self.nb_preview.add(self.txt_pre_masw, text="MASW/VP")

        # Panelleri Dikey PanedWindow'a Ekle
        pan_main.add(pan_lists, height=450)
        pan_main.add(self.f_jeo_preview, height=250)

    @perf_tracked("jeofizik.excel_preview")
    def jeo_excel_yukle_ve_onizle(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx;*.xls;*.csv")])
        if not f: return

        self.jeo_excel_path = f
        if hasattr(self, 'lbl_jeo_excel'):
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
                    vals = [str(x) for x in row[2:6] if pd.notna(x)]
                    self.txt_pre_param.insert(tk.END, f"{current_s:<10} | Veriler okundu. Rapor çıktısında tablo olarak basılacaktır.\n")
                    break # Örnek için kısa kestik

            self.txt_pre_param.insert(tk.END, "\n[BİLGİ] Tam tablo yapısı Rapor Oluştur butonuna basınca Word'e işlenecektir.")

        except Exception as e:
            self.set_status(f"Excel Okuma Hatası: {str(e)}", level="error")

    def jeo_ekle(self): self.veri["jeofizik"]["ss_list"].append({"ad": f"SS-{len(self.veri['jeofizik']['ss_list'])+1}", "coords": [""]*6, "layers": []}); self.jeo_yenile()
    def jeo_sil(self):
        if self.jeo_lb.curselection(): del self.veri["jeofizik"]["ss_list"][self.jeo_lb.curselection()[0]]; self.jeo_yenile()
    def jeo_sec(self, e):
        sel = self.jeo_lb.curselection()
        if not sel: return
        self.sel_j_idx = sel[0]; s = self.veri["jeofizik"]["ss_list"][self.sel_j_idx]; self.f_mt_detay.pack_forget(); self.f_ss_detay.pack(fill="both", expand=True)
        for i, v in enumerate(s.get("coords", [])): self.jeo_coords[i].delete(0, tk.END); self.jeo_coords[i].insert(0, v)
        for row in self.layer_rows:
            for ent in row["ents"]: ent.delete(0, tk.END)
            for lbl in row["lbls"]: lbl.config(text="-")
        for i, l in enumerate(s.get("layers", [])):
            if i < 5:
                r = self.layer_rows[i]["ents"]; r[0].insert(0, l.get("vp","")); r[1].insert(0, l.get("vs","")); r[2].insert(0, l.get("h","")); r[3].insert(0, l.get("rho",""))
                lbls = self.layer_rows[i]["lbls"]; lbls[0].config(text=str(l.get("nu","-"))); lbls[1].config(text=str(l.get("E","-"))); lbls[2].config(text=str(l.get("G","-"))); lbls[3].config(text=str(l.get("vs30","-"))); lbls[4].config(text=str(l.get("ratio","-")))
    @perf_tracked("jeofizik.calculate")
    def jeo_hesapla(self):
        if not hasattr(self, 'sel_j_idx'): return
        coords = [e.get() for e in self.jeo_coords]; valid_rows = []; layers = []
        for row in self.layer_rows:
            vp, vs, h, rho = [e.get() for e in row["ents"]]
            if vp and vs: valid_rows.append({"row":row, "vp":vp, "vs":vs, "h":h, "rho":rho})
        for i, item in enumerate(valid_rows):
            res = GeoEngine.hesapla_parametreler(item["vp"], item["vs"], item["h"], item["rho"])
            item["row"]["lbls"][0].config(text=res["nu"]); item["row"]["lbls"][1].config(text=res["E"]); item["row"]["lbls"][2].config(text=res["G"]); item["row"]["lbls"][4].config(text=res["ratio"])
            l_data = {"vp":item["vp"], "vs":item["vs"], "h":item["h"], "rho":res["rho"], "nu":res["nu"], "E":res["E"], "G":res["G"], "K":res["K"], "ratio":res["ratio"]}
            layers.append(l_data)
        if layers: layers[0]["vs30"] = GeoEngine.vs30_hesapla(layers)
        self.veri["jeofizik"]["ss_list"][self.sel_j_idx]["coords"] = coords; self.veri["jeofizik"]["ss_list"][self.sel_j_idx]["layers"] = layers; self.veri_kaydet()

    def mt_ekle(self): self.veri["jeofizik"]["mt_list"].append({"no": f"MT-{len(self.veri['jeofizik']['mt_list'])+1}", "y":"", "x":""}); self.mt_yenile()
    def mt_sil(self):
        if self.mt_lb.curselection(): del self.veri["jeofizik"]["mt_list"][self.mt_lb.curselection()[0]]; self.mt_yenile()

    def mt_sec(self, e):
        sel = self.mt_lb.curselection()
        if not sel: return
        self.sel_mt_idx = sel[0]; m = self.veri["jeofizik"]["mt_list"][self.sel_mt_idx];
        self.f_ss_detay.pack_forget(); self.f_mt_detay.pack(fill="both", expand=True)

        self.e_mt_y.delete(0, tk.END); self.e_mt_y.insert(0, m.get("y", ""))
        self.e_mt_x.delete(0, tk.END); self.e_mt_x.insert(0, m.get("x", ""))

        for k, ent in self.e_mt_details.items():
            ent.delete(0, tk.END)
            ent.insert(0, m.get(k, ""))

    def mt_kaydet(self):
        if hasattr(self, 'sel_mt_idx'):
            m = self.veri["jeofizik"]["mt_list"][self.sel_mt_idx]
            m["y"] = self.e_mt_y.get()
            m["x"] = self.e_mt_x.get()
            for k, ent in self.e_mt_details.items():
                m[k] = ent.get()
            self.veri_kaydet()
            self.set_status(f"{m.get('no')} verileri projeye kaydedildi.", level="success")

    def jeo_yenile(self): self.jeo_lb.delete(0, tk.END); [self.jeo_lb.insert(tk.END, s["ad"]) for s in self.veri["jeofizik"]["ss_list"]]
    def mt_yenile(self): self.mt_lb.delete(0, tk.END); [self.mt_lb.insert(tk.END, m["no"]) for m in self.veri["jeofizik"]["mt_list"]]
