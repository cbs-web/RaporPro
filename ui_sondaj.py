import datetime
import os
import threading
import tkinter as tk
from tkinter import Canvas, Frame, Scrollbar, Toplevel, filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from cizim import VeriGirisPenceresi
from motor import GeoEngine
from performans import log_exception, perf_tracked
from sabitler import *
from karot_motoru import derinlik_baslangic
from yardimcilar import litoloji_yazim_uyarilari, safe_float, temizle_baslik
from widgets import UndoRedoEntry


# ============================================================================
class SPTVeriPenceresi:
    def __init__(self, parent, title, data_list, source_list=None, on_save=None):
        self.top = Toplevel(parent)
        self.top.title(title)
        self.top.geometry("820x600")
        self.top.configure(bg="#f4f6f7")
        self.data_list = data_list
        self.source_list = source_list if source_list is not None else []
        self.on_save = on_save
        self.rows = []
        
        top_bar = tk.Frame(self.top, bg="#ecf0f1", pady=10, padx=10)
        top_bar.pack(fill="x")
        tk.Button(top_bar, text="+ Yeni Satır", command=self.add_empty_row, bg="#3498DB", fg="white", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        tk.Button(top_bar, text="Panodan Yapıştır", command=self.excelden_yapistir, bg="#9B59B6", fg="white", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        tk.Button(top_bar, text="Kaydet", command=self.kaydet_ve_kapat, bg="#2ECC71", fg="white", font=("Arial", 9, "bold")).pack(side="right", padx=5)
        
        container = tk.Frame(self.top, bg="#ffffff", bd=1, relief="solid")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.canvas = Canvas(container, bg="#ffffff")
        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#ffffff")
        
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        headers = ["Derinlik", "15", "30", "45", "N30", "Kaynak", "İşlem"]
        for i, h in enumerate(headers):
            width = 12 if i < 5 else (18 if i == 5 else 8)
            tk.Label(self.scroll_frame, text=h, font=("Arial", 10, "bold"), bg="#ffffff", width=width).grid(row=0, column=i, padx=2, pady=5)
            
        for row_data in self.data_list:
            self.add_row(row_data, self.source_for_row(row_data))
            
        if not self.data_list:
            self.add_empty_row()

    def excelden_yapistir(self):
        try:
            pano_verisi = self.top.clipboard_get()
            satirlar = pano_verisi.split('\n')
            for satir in satirlar:
                hucreler = satir.split('\t')
                if len(hucreler) > 1 or (len(hucreler) == 1 and hucreler[0].strip() != ""):
                    hucreler = [h.strip() for h in hucreler]
                    self.add_row(hucreler)
        except Exception as exc:
            log_exception("ui_sondaj.spt_clipboard_paste", exc_value=exc)

    def add_empty_row(self):
        last_der = 0.0
        if self.rows:
            for row_dict in reversed(self.rows):
                der_str = row_dict["ents"][0].get().replace(',', '.')
                try: 
                    last_der = float(der_str)
                    break
                except Exception as exc:
                    log_exception("ui_sondaj.spt_last_depth_parse", exc_value=exc)
        new_der = f"{last_der + 1.50:.2f}" if last_der > 0 else "1.50"
        self.add_row([new_der, "", "", "", ""])
        
        # YENİ SATIR EKLENDİĞİNDE OTOMATİK OLARAK "15" SÜTUNUNA ODAKLAN
        if self.rows:
            self.rows[-1]["ents"][1].focus_set()

    def sonraki_satira_gec(self, row_dict):
        """Tab veya Enter'a basıldığında çalışır. İmleci akıllıca yönlendirir."""
        try:
            idx = self.rows.index(row_dict)
            # Eğer son satırdaysak yeni satır aç (yeni satır kendi kendine odaklanacak)
            if idx == len(self.rows) - 1:
                self.add_empty_row()
            else:
                # Aradaki bir satırdaysak, bir sonraki satırın "15" sütununa atla
                self.rows[idx + 1]["ents"][1].focus_set()
        except ValueError:
            pass
        return "break" # Tab'ın varsayılan (sağa kayma) hareketini durdurur!

    def source_for_row(self, data):
        if not data:
            return None
        depth = safe_float(data[0] if len(data) > 0 else "")
        if depth <= 0:
            return None
        for item in self.source_list or []:
            if abs(safe_float(item.get("derinlik")) - depth) <= 0.01:
                return dict(item)
        return None

    def source_label(self, source):
        if not source:
            return "-"
        guven = str(source.get("guven", "")).strip()
        if guven:
            return f"Kaynak %{guven}"
        return "Kaynak"

    def source_info_ac(self, row_dict):
        source = row_dict.get("source")
        if not source:
            messagebox.showinfo("SPT Kaynağı", "Bu SPT satırı için kayıtlı kaynak bilgisi yok.", parent=self.top)
            return
        win = Toplevel(self.top)
        win.title("SPT Satır Kaynağı")
        win.geometry("860x700")
        win.minsize(720, 560)
        win.configure(bg="#f4f6f7")
        footer = ttk.Frame(win, padding=8)
        footer.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=10)
        body.pack(side="top", fill="both", expand=True)
        info = {
            "Derinlik": source.get("derinlik", ""),
            "Kaynak": source.get("kaynak", ""),
            "Güven": source.get("guven", ""),
            "Aktarım Tarihi": source.get("aktarim_tarihi", ""),
            "Dosya": source.get("kaynak_yolu", ""),
        }
        for idx, (label, value) in enumerate(info.items()):
            ttk.Label(body, text=label, font=("Arial", 9, "bold")).grid(row=idx, column=0, sticky="nw", padx=(0, 8), pady=4)
            ttk.Label(body, text=str(value or "-"), wraplength=650, justify="left").grid(row=idx, column=1, sticky="nw", pady=4)

        preview_frame = ttk.Frame(body)
        preview_frame.grid(row=len(info), column=0, columnspan=2, sticky="nsew", pady=(10, 6))
        preview = tk.Canvas(preview_frame, bg="#ffffff", highlightthickness=1, highlightbackground="#D5DBDB", width=760, height=460)
        preview.pack(fill="both", expand=True)
        body.rowconfigure(len(info), weight=1)
        body.columnconfigure(1, weight=1)
        path = source.get("kaynak_yolu", "")
        preview_state = {"photo": None, "after_id": None}

        def draw_preview_message(text):
            preview_state["photo"] = None
            preview.delete("all")
            w = max(300, preview.winfo_width())
            h = max(220, preview.winfo_height())
            preview.create_text(
                w / 2,
                h / 2,
                text=text,
                fill="#555555",
                width=max(260, w - 40),
                justify="center",
                font=("Segoe UI", 10),
            )

        def render_preview():
            if not path or not os.path.exists(path):
                draw_preview_message("Önizleme yok")
                return
            if os.path.splitext(path)[1].lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                draw_preview_message(f"Kaynak dosya:\n{path}")
                return
            try:
                from PIL import Image, ImageOps, ImageTk
                image = Image.open(path)
                try:
                    image = ImageOps.exif_transpose(image)
                except Exception:
                    pass
                image = image.convert("RGB")
                preview.update_idletasks()
                max_w = max(520, preview.winfo_width() - 18)
                max_h = max(360, preview.winfo_height() - 18)
                resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
                image.thumbnail((max_w, max_h), resample)
                photo = ImageTk.PhotoImage(image)
                preview_state["photo"] = photo
                preview.delete("all")
                preview.create_image(max(1, preview.winfo_width()) / 2, max(1, preview.winfo_height()) / 2, image=photo, anchor="center")
            except Exception as exc:
                draw_preview_message(f"Önizleme açılamadı:\n{exc}")

        def schedule_render_preview(event=None):
            if preview_state.get("after_id"):
                try:
                    win.after_cancel(preview_state["after_id"])
                except Exception:
                    pass
            preview_state["after_id"] = win.after(120, render_preview)

        if path and os.path.exists(path) and os.path.splitext(path)[1].lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            win.after(100, render_preview)
            preview.bind("<Configure>", schedule_render_preview)
        elif path:
            draw_preview_message(f"Kaynak dosya:\n{path}")
        else:
            draw_preview_message("Önizleme yok")

        def copy_path():
            win.clipboard_clear()
            win.clipboard_append(path or "")
            win.update()

        btns = ttk.Frame(footer)
        btns.pack(side="right")
        tk.Button(btns, text="Dosya Yolunu Kopyala", command=copy_path, bg="#D6EAF8", font=("Arial", 9, "bold")).pack(side="left", padx=4)
        tk.Button(btns, text="Kapat", command=win.destroy, bg="#7F8C8D", fg="white", font=("Arial", 9, "bold")).pack(side="left", padx=4)

    def add_row(self, data, source_info=None):
        r_idx = len(self.rows) + 1
        row_dict = {"ents": [], "source": dict(source_info) if source_info else None}
        for i in range(5):
            e = UndoRedoEntry(self.scroll_frame, width=12)
            val = data[i] if i < len(data) else ""
            e.insert(0, str(val))
            e.grid(row=r_idx, column=i, padx=4, pady=3)
            row_dict["ents"].append(e)
            
            # Dinamik N30 Hesaplama
            if i in [1, 2, 3]: 
                e.bind("<KeyRelease>", lambda event, r=row_dict: self.hesapla_n30(r))
            
            # Enter ve TAB Tuşu Kontrolleri (Artık 45 ve N30 Sütunlarında geçerli)
            # i=3 (45 Sütunu) ve i=4 (N30 Sütunu)
            if i in [3, 4]: 
                e.bind("<Return>", lambda event, r=row_dict: self.sonraki_satira_gec(r))
                e.bind("<Tab>", lambda event, r=row_dict: self.sonraki_satira_gec(r))
                
        btn_src = tk.Button(
            self.scroll_frame,
            text=self.source_label(row_dict["source"]),
            bg="#D6EAF8" if row_dict["source"] else "#ECF0F1",
            fg="#111",
            font=("Arial", 8, "bold"),
            command=lambda r=row_dict: self.source_info_ac(r),
        )
        btn_src.grid(row=r_idx, column=5, padx=4, pady=3, sticky="ew")
        row_dict["btn_src"] = btn_src

        btn_sil = tk.Button(self.scroll_frame, text="SİL", bg="#E74C3C", fg="white", font=("Arial", 8, "bold"), command=lambda r=row_dict: self.sil_satir(r))
        btn_sil.grid(row=r_idx, column=6, padx=4, pady=3)
        row_dict["btn"] = btn_sil
        
        self.rows.append(row_dict)
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)
        
    def sil_satir(self, row_dict):
        for e in row_dict["ents"]: e.destroy()
        row_dict["btn_src"].destroy()
        row_dict["btn"].destroy()
        self.rows.remove(row_dict)

    def hesapla_n30(self, row_dict):
        ents = row_dict["ents"]
        val15 = ents[1].get().strip().replace(' ', '')
        val30 = ents[2].get().strip().replace(' ', '')
        val45 = ents[3].get().strip().replace(' ', '')
        n30_entry = ents[4]
        
        has_refusal = False
        for v in [val15, val30, val45]:
            if "50/" in v or "-" in v:
                has_refusal = True
                break
                
        if has_refusal:
            n30_entry.delete(0, tk.END)
            n30_entry.insert(0, "R")
        else:
            if val30.isdigit() or val45.isdigit():
                v30 = int(val30) if val30.isdigit() else 0
                v45 = int(val45) if val45.isdigit() else 0
                total = v30 + v45
                n30_entry.delete(0, tk.END)
                n30_entry.insert(0, str(total))

    def kaydet_ve_kapat(self):
        self.data_list.clear()
        new_sources = []
        for row_dict in self.rows:
            vals = [e.get().strip() for e in row_dict["ents"]]
            if any(vals):
                self.data_list.append(vals)
                source = row_dict.get("source")
                if source:
                    source["derinlik"] = vals[0]
                    new_sources.append(source)
        if self.source_list is not None:
            self.source_list.clear()
            self.source_list.extend(new_sources)
        if callable(self.on_save):
            self.on_save()
        self.top.destroy()


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
            row_frame.configure(
                highlightbackground="#7FB3D5" if active else getattr(row_frame, "_normal_border", "#D8DEE6"),
                highlightthickness=2 if active else 1,
            )
        except Exception:
            pass

    def p_sondaj(self, p):
        top_bar = ttk.Frame(p, padding=10); top_bar.pack(fill="x")
        self.responsive_button_row(top_bar, [
            ("+ Yeni Sondaj Ekle", self.sondaj_ekle, COLOR_ACCENT, "white", "Yeni bir sondaj satırı oluşturur"),
            ("Workbook", self.veri_giris_workbook_tksheet_ac, "#34495E", "white", "Excel benzeri toplu veri girişini açar"),
            ("SPT Merkezi", self.spt_okuma_merkezi_ac, "#148F77", "white", "Excel ve fotoğraf SPT okuma, kontrol ve aktarım merkezini açar"),
            ("Karot TCR", self.karot_tcr_merkezi_ac, "#7D3C98", "white", "Karot sandığı fotoğrafından kalibrasyonlu TCR hesabı yapar"),
            ("Akıllı Tamamla", self.sondaj_akilli_tamamla, "#7DCEA0", "#111", "Eksik temel sondaj alanlarını otomatik tamamlar"),
            ("Genel Kaydet", self.sondaj_verilerini_kaydet, COLOR_SUCCESS, "white", "Sondaj tablosundaki değişiklikleri belleğe alır"),
            ("Toplu Log Kaydet", self.toplu_log_kaydet, "#F39C12", "white", "Tüm sondaj loglarını toplu kaydeder"),
            ("Kesit Çiz", self.kesit_secim_penceresi, "#5D4037", "white", "Seçili sondajlardan jeolojik kesit hazırlar"),
        ], min_width=150, max_cols=7, padx=3, pady=3)

        container = ttk.Frame(p); container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=COLOR_BG); scrollbar_y = ttk.Scrollbar(container, orient="vertical", command=canvas.yview); scrollbar_x = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        self.sondaj_scroll_frame = ttk.Frame(canvas); self.sondaj_scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sondaj_scroll_frame, anchor="nw"); canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        scrollbar_y.pack(side="right", fill="y"); scrollbar_x.pack(side="bottom", fill="x"); canvas.pack(side="left", fill="both", expand=True)
        self.sondaj_headers = [("Sondaj No", "no"), ("Derinlik", "der"), ("Enlem", "y"), ("Boylam", "x"), ("Kot", "k"), ("Baş. Tarihi", "bas_tar"), ("Bit. Tarihi", "bit_tar"), ("YASS İlk", "yass_d1"), ("YASS T1", "yass_t1"), ("YASS Son", "yass_d2"), ("YASS T2", "yass_t2")]
        self.sondaj_tablosunu_ciz()

    @perf_tracked("sondaj.table_redraw")
    def sondaj_tablosunu_ciz(self):
        self.sondaj_zebra_stillerini_hazirla()
        for widget in self.sondaj_scroll_frame.winfo_children(): widget.destroy()
        self.sondaj_ui_rows = []
        header_frame = tk.Frame(self.sondaj_scroll_frame, bg="#D5DBE3")
        header_frame.pack(fill="x", pady=(2, 4))
        tk.Label(header_frame, text="", width=1, bg="#D5DBE3", font=FONT_BOLD).pack(side="left", padx=(0, 1))
        tk.Label(header_frame, text="#", width=3, bg="#D5DBE3", fg="#2C3E50", font=FONT_BOLD).pack(side="left", padx=1)
        for lbl, key in self.sondaj_headers:
            tk.Label(header_frame, text=lbl, width=12, bg="#D5DBE3", fg="#2C3E50", font=FONT_BOLD).pack(side="left", padx=1)
        tk.Label(header_frame, text="İşlemler", width=42, bg="#D5DBE3", fg="#2C3E50", font=FONT_BOLD).pack(side="left", padx=10)
        
        for idx, s_data in enumerate(self.veri["sondaj"]):
            parity = "odd" if idx % 2 else "even"
            row_bg = "#F3F5F7" if parity == "odd" else "#FFFFFF"
            strip_color = "#AEB6BF" if parity == "odd" else "#D0D5DA"
            row_frame = tk.Frame(
                self.sondaj_scroll_frame,
                bg=row_bg,
                highlightbackground="#D8DEE6",
                highlightthickness=1,
                bd=0,
            )
            row_frame._normal_border = "#D8DEE6"
            row_frame.pack(fill="x", pady=(0, 2), padx=2)
            tk.Frame(row_frame, width=4, bg=strip_color).pack(side="left", fill="y", padx=(0, 2))
            tk.Label(row_frame, text=str(idx+1), width=3, bg=row_bg, fg="#2C3E50", font=FONT_BOLD).pack(side="left", padx=1)
            row_entries = {}
            for lbl, key in self.sondaj_headers:
                e = UndoRedoEntry(row_frame, width=12)
                e._sondaj_parity = parity
                e.insert(0, s_data.get(key, ""))
                e.pack(side="left", padx=1, pady=3)
                e.bind("<FocusIn>", lambda event, rf=row_frame: self.sondaj_satir_vurgula(rf, True), add="+")
                e.bind("<FocusOut>", lambda event, rf=row_frame: self.sondaj_satir_vurgula(rf, False), add="+")
                row_entries[key] = e
            
            row_entries['bit_tar'].bind('<FocusOut>', lambda e, r_ents=row_entries: self.oto_yass_tarih(r_ents))
            row_entries['bit_tar'].bind('<Return>', lambda e, r_ents=row_entries: self.oto_yass_tarih(r_ents))
            for key, ent in row_entries.items():
                ent.bind("<KeyRelease>", lambda event, r_ents=row_entries: self.sondaj_satirini_canli_dogrula(r_ents), add="+")
                ent.bind("<FocusOut>", lambda event, r_ents=row_entries: self.sondaj_satirini_canli_dogrula(r_ents), add="+")
            self.sondaj_satirini_canli_dogrula(row_entries)
            
            btn_f = tk.Frame(row_frame, bg=row_bg)
            btn_f.pack(side="left", padx=10, pady=2)
            button_specs = [
                ("Litoloji", "litoloji", lambda i=idx: self.satir_veri_ac(i, "litoloji", ["Başlangıç", "Bitiş", "Tanım"])),
                ("SPT", "spt", lambda i=idx: self.satir_veri_ac(i, "spt", [])),
                ("Numune", "numuneler", lambda i=idx: self.satir_veri_ac(i, "numuneler", ["Derinlik/Aralık", "Türü/No"])),
                ("PMT", "pmt", lambda i=idx: self.satir_veri_ac(i, "pmt", ["Der", "Em", "Pl"])),
                ("Kaya", "kaya", lambda i=idx: self.satir_veri_ac(i, "kaya", ["Derinlik", "TCR (%)", "SCR (%)", "RQD (%)"])),
                ("LOG", "log", lambda i=idx: self.satir_log_onizle(i)),
            ]
            for text, tur, command in button_specs:
                state, tip = self._sondaj_detay_durum(s_data, tur)
                role = self.sondaj_islem_buton_rolu(state)
                font = ("Arial", 8, "bold") if tur == "log" else ("Arial", 8)
                btn = self.modern_button(
                    btn_f,
                    text=text,
                    command=command,
                    role=role,
                    outline=(state == "empty"),
                    font=font,
                    padx=6,
                    pady=3,
                )
                btn.pack(side="left", padx=1 if tur != "log" else 5)
                self.tooltip_ekle(btn, tip)
            self.modern_button(btn_f, text="SİL", role="danger", font=("Arial", 8, "bold"), command=lambda i=idx: self.sondaj_sil(i), padx=6, pady=3).pack(side="left", padx=5)
            self.sondaj_ui_rows.append(row_entries)

    def sondaj_satirini_canli_dogrula(self, row_entries):
        row_has_data = any(str(ent.get()).strip() for ent in row_entries.values())
        for key, ent in row_entries.items():
            state, message = self.sondaj_hucre_durumu(key, ent.get(), row_has_data)
            try:
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
            self.sondaj_tablosunu_ciz()
            self.set_status("Sondaj verileri hafızaya alındı.")

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
                ent.insert(0, data.get(key, ""))
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
        GeoEngine.reset_warnings(); figs = GeoEngine.ciz_profesyonel_log(sondaj_data, self.veri, log_callback=on_draw_warning)
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
            self.toplu_log_kaydet_baslat(list(sondajlar), config)

        tk.Button(btns, text="Başlat", command=start_export, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=(5, 0))
        tk.Button(btns, text="Vazgeç", command=win.destroy, bg="#ECF0F1").pack(side="right", padx=5)

    def toplu_log_kaydet_baslat(self, sondajlar, config):
        progress_win = Toplevel(self.root)
        self.pencere_hazirla(progress_win, "Toplu Log Kaydı", "460x170", (430, 160), modal=True)

        total = len(sondajlar)
        status_var = tk.StringVar(value="Hazırlanıyor...")
        detail_var = tk.StringVar(value="0 / 0")
        progress_var = tk.DoubleVar(value=0)
        cancel_state = {"cancelled": False}

        body = ttk.Frame(progress_win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, textvariable=status_var, font=FONT_BOLD).pack(anchor="w", pady=(0, 8))
        bar = ttk.Progressbar(body, maximum=max(total, 1), variable=progress_var)
        bar.pack(fill="x", pady=6)
        ttk.Label(body, textvariable=detail_var).pack(anchor="w", pady=(4, 10))

        def cancel():
            cancel_state["cancelled"] = True
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
        worker = threading.Thread(target=self.toplu_log_kaydet_threaded, args=(sondajlar, config, progress, cancel_state), daemon=True)
        worker.start()

    def _toplu_log_progress_guncelle(self, progress, done, text):
        if not progress:
            return
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
    def toplu_log_kaydet_threaded(self, sondajlar, config, progress=None, cancel_state=None):
        saved_count = 0
        saved_files = []
        errors = []
        try:
            klasor = config["folder"]
            fmt = config.get("format", "jpg")
            ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
            dpi = config.get("dpi", 300)
            prefix = config.get("prefix", "Log")
            total = len(sondajlar)
            os.makedirs(klasor, exist_ok=True)
            for idx, sondaj in enumerate(sondajlar, start=1):
                if cancel_state and cancel_state.get("cancelled"):
                    break
                sondaj_no = sondaj.get("no") or f"SK-{idx}"
                self._toplu_log_progress_guncelle(progress, idx - 1, f"Log hazırlanıyor: {sondaj_no}")
                self.set_status(f"Log hazırlanıyor ({idx}/{total}): {sondaj_no}", level="info")
                figures = []
                try:
                    figures = GeoEngine.ciz_profesyonel_log(sondaj, self.veri)
                    safe_no = self._guvenli_dosya_adi(sondaj_no, f"SK_{idx}")
                    for page_idx, fig in enumerate(figures, start=1):
                        suffix = f"_Sayfa{page_idx}" if len(figures) > 1 else ""
                        path = os.path.join(klasor, f"{prefix}_{safe_no}{suffix}.{ext}")
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
            cancelled = bool(cancel_state and cancel_state.get("cancelled"))
            summary_path = self.toplu_log_ozet_yaz(klasor, config, saved_files, errors, cancelled)
            if cancelled:
                msg = f"Toplu log kaydı iptal edildi.\n\nKaydedilen sayfa: {saved_count}\nKlasör: {klasor}\nÖzet: {summary_path}"
                self._toplu_log_progress_bitti(progress, msg, "warning")
                self.set_status(f"Toplu log kaydı iptal edildi: {saved_count} sayfa.", level="warning")
                return
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
        except Exception as exc:
            error_text = str(exc)
            self._toplu_log_progress_bitti(progress, error_text, "error")
            self.set_status(f"Toplu log kaydı hatası: {error_text}", level="error")

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
        self.sondaj_tablosunu_ciz()
    def sondaj_sil(self, index):
        if messagebox.askyesno("Sil", f"{index+1}. sıradaki sondaj silinsin mi?"): del self.veri["sondaj"][index]; self.sondaj_tablosunu_ciz()
        

