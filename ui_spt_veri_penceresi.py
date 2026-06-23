# Dosya: RaporPro/ui_spt_veri_penceresi.py
import os
import tkinter as tk
from tkinter import Canvas, Toplevel, messagebox, ttk

from performans import log_exception
from yardimcilar import safe_float
from widgets import UndoRedoEntry


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

    def hucreye_git(self, row_dict, col_idx, delta):
        if row_dict not in self.rows:
            return "break"
        row_idx = self.rows.index(row_dict) + delta
        if row_idx >= len(self.rows):
            self.add_empty_row()
        if 0 <= row_idx < len(self.rows):
            ents = self.rows[row_idx]["ents"]
            col_idx = max(0, min(col_idx, len(ents) - 1))
            entry = ents[col_idx]
            entry.focus_set()
            entry.selection_range(0, tk.END)
        return "break"

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
                e.bind("<Tab>", lambda event, r=row_dict: self.sonraki_satira_gec(r))
            e.bind("<Return>", lambda event, r=row_dict, c=i: self.hucreye_git(r, c, 1))
            e.bind("<Down>", lambda event, r=row_dict, c=i: self.hucreye_git(r, c, 1))
            e.bind("<Up>", lambda event, r=row_dict, c=i: self.hucreye_git(r, c, -1))
                
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

