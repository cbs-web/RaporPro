import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from PIL import Image, ImageOps

from karot_motoru import derinlik_araligi_etiketi, derinlik_baslangic, standart_karot_araliklari, tcr_hesapla
from sabitler import COLOR_BG, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD
from widgets import UndoRedoEntry


class KarotTCRMixin:
    def karot_tcr_merkezi_ac(self):
        self.sondaj_verilerini_kaydet(silent=True)
        KarotTCRPenceresi(self)


class KarotTCRPenceresi:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.app.pencere_hazirla(self.win, "Karot TCR Okuma Merkezi", "1360x840", (1060, 680), modal=False)

        self.image_path = None
        self.image_array = None
        self.top_line = []
        self.bottom_line = []
        self.intervals = []
        self.template_intervals = standart_karot_araliklari()
        self.selected_interval = None
        self.action = None
        self.pending_points = []
        self.temp_artist = None
        self.drawn_artists = []

        self.target_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Fotoğraf seçin, ardından üst ve alt 1 m kalibrasyon çizgilerini işaretleyin.")

        self._build_ui()
        self._refresh_target_values()
        self._draw_empty_canvas()

    def _build_ui(self):
        root = ttk.Frame(self.win, padding=8)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="Karot TCR Okuma Merkezi", bg=COLOR_BG, fg=COLOR_PRIMARY, font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="left", padx=18)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        right_outer = ttk.Frame(body, width=390)
        right_outer.pack(side="right", fill="y", padx=(8, 0))
        right_outer.pack_propagate(False)
        right_canvas = tk.Canvas(right_outer, width=365, bg=COLOR_BG, highlightthickness=0)
        right_scroll = ttk.Scrollbar(right_outer, orient="vertical", command=right_canvas.yview)
        right = ttk.Frame(right_canvas)
        right_window = right_canvas.create_window((0, 0), window=right, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_scroll.pack(side="right", fill="y")
        right_canvas.pack(side="left", fill="both", expand=True)

        def update_right_scroll(event=None):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))

        def resize_right_content(event):
            right_canvas.itemconfigure(right_window, width=event.width)

        def wheel_right(event):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        right.bind("<Configure>", update_right_scroll)
        right.bind("<MouseWheel>", wheel_right)
        right_canvas.bind("<Configure>", resize_right_content)
        right_canvas.bind("<MouseWheel>", wheel_right)

        self.fig, self.ax = plt.subplots(figsize=(8.5, 6.5))
        self.fig.patch.set_facecolor("#F4F6F7")
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_canvas_click)

        source_frame = ttk.LabelFrame(right, text="Kaynak", padding=8)
        source_frame.pack(fill="x", pady=(0, 8))
        tk.Button(source_frame, text="Fotoğraf Seç", command=self._select_image, bg="#34495E", fg="white", font=FONT_BOLD).pack(fill="x", pady=2)
        self.lbl_image = ttk.Label(source_frame, text="Fotoğraf seçilmedi", wraplength=320)
        self.lbl_image.pack(fill="x", pady=(4, 0))

        target_frame = ttk.LabelFrame(right, text="Aktarım", padding=8)
        target_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(target_frame, text="Hedef sondaj").pack(anchor="w")
        self.cmb_target = ttk.Combobox(target_frame, textvariable=self.target_var, state="readonly")
        self.cmb_target.pack(fill="x", pady=(2, 6))
        tk.Button(target_frame, text="Kaya Tablosuna Aktar", command=self._aktar, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(fill="x", pady=2)

        results_frame = ttk.LabelFrame(right, text="Seçilen Aralıklar", padding=8)
        results_frame.pack(fill="x", pady=(0, 8))
        columns = ("aralik", "karot", "tcr", "parca")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=7, selectmode="browse")
        for key, label, width in [
            ("aralik", "Aralık", 90),
            ("karot", "Karot", 70),
            ("tcr", "TCR", 60),
            ("parca", "Parça", 50),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        tree_scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="x", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_interval_select)

        calib_frame = ttk.LabelFrame(right, text="Kalibrasyon", padding=8)
        calib_frame.pack(fill="x", pady=(0, 8))
        tk.Button(calib_frame, text="Üst 1.00 m Çizgisi", command=lambda: self._set_action("top"), bg="#D5F5E3", font=FONT_BOLD).pack(fill="x", pady=2)
        tk.Button(calib_frame, text="Alt 1.00 m Çizgisi", command=lambda: self._set_action("bottom"), bg="#D6EAF8", font=FONT_BOLD).pack(fill="x", pady=2)
        tk.Button(calib_frame, text="Kalibrasyonu Temizle", command=self._clear_calibration, bg="#FADBD8", font=FONT_BOLD).pack(fill="x", pady=2)

        interval_frame = ttk.LabelFrame(right, text="Derinlik Aralığı", padding=8)
        interval_frame.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(interval_frame)
        row.pack(fill="x")
        ttk.Label(row, text="Baş.").pack(side="left")
        self.ent_top = UndoRedoEntry(row, width=8)
        self.ent_top.pack(side="left", padx=(4, 8))
        ttk.Label(row, text="Bitiş").pack(side="left")
        self.ent_bot = UndoRedoEntry(row, width=8)
        self.ent_bot.pack(side="left", padx=(4, 0))
        btn_row = ttk.Frame(interval_frame)
        btn_row.pack(fill="x", pady=(6, 0))
        tk.Button(btn_row, text="Aralık Ekle", command=self._add_interval, bg="#F9E79F", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(btn_row, text="Seçili Sil", command=self._delete_interval, bg="#F5B7B1", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=(3, 0))

        template_frame = ttk.LabelFrame(right, text="1.50 m Şablon", padding=8)
        template_frame.pack(fill="x", pady=(0, 8))
        template_list_frame = ttk.Frame(template_frame)
        template_list_frame.pack(fill="x")
        self.template_list = tk.Listbox(template_list_frame, height=4, selectmode="extended", exportselection=False)
        template_scroll = ttk.Scrollbar(template_list_frame, orient="vertical", command=self.template_list.yview)
        self.template_list.configure(yscrollcommand=template_scroll.set)
        self.template_list.pack(side="left", fill="x", expand=True)
        template_scroll.pack(side="right", fill="y")
        for top, bot in self.template_intervals:
            self.template_list.insert(tk.END, derinlik_araligi_etiketi(top, bot))
        self.template_list.bind("<Double-Button-1>", lambda event: self._add_template_intervals())
        tk.Button(template_frame, text="Seçilileri Listeye Ekle", command=self._add_template_intervals, bg="#D5F5E3", font=FONT_BOLD).pack(fill="x", pady=(6, 2))
        tpl_row = ttk.Frame(template_frame)
        tpl_row.pack(fill="x")
        tk.Button(tpl_row, text="Tümünü Ekle", command=self._add_all_template_intervals, bg="#D6EAF8", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(tpl_row, text="Listeyi Temizle", command=self._clear_intervals, bg="#FADBD8", font=FONT_BOLD).pack(side="left", fill="x", expand=True, padx=(3, 0))

        segment_frame = ttk.LabelFrame(right, text="Karot Parçaları", padding=8)
        segment_frame.pack(fill="x", pady=(0, 8))
        tk.Button(segment_frame, text="Karot Parçası İşaretle", command=lambda: self._set_action("segment"), bg="#E8DAEF", font=FONT_BOLD).pack(fill="x", pady=2)
        tk.Button(segment_frame, text="Son Parçayı Sil", command=self._delete_last_segment, bg="#FDEBD0", font=FONT_BOLD).pack(fill="x", pady=2)
        tk.Button(segment_frame, text="Seçili Aralığı Temizle", command=self._clear_selected_segments, bg="#FADBD8", font=FONT_BOLD).pack(fill="x", pady=2)

    def _refresh_target_values(self):
        values = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(self.app.veri.get("sondaj", []))]
        self.cmb_target["values"] = values
        if values and not self.target_var.get():
            self.target_var.set(values[0])

    def _draw_empty_canvas(self):
        self.ax.clear()
        self.ax.axis("off")
        self.ax.text(0.5, 0.5, "Karot sandığı fotoğrafı seçin", ha="center", va="center", transform=self.ax.transAxes, fontsize=13)
        self.canvas.draw()

    def _select_image(self):
        path = filedialog.askopenfilename(
            title="Karot sandığı fotoğrafı seç",
            filetypes=[("Resimler", "*.jpg *.jpeg *.png *.bmp *.webp *.JPG *.JPEG *.PNG"), ("Tüm Dosyalar", "*.*")],
            parent=self.win,
        )
        if not path:
            return
        try:
            image = Image.open(path)
            image = ImageOps.exif_transpose(image).convert("RGB")
            self.image_array = np.asarray(image)
            self.image_path = path
            self.lbl_image.configure(text=os.path.basename(path))
            self._reset_photo_marks()
            self.status_var.set("Yeni fotoğraf yüklendi. Kalibrasyon ve karot işaretlemeleri temizlendi.")
            self._redraw()
        except Exception as exc:
            messagebox.showerror("Karot Fotoğrafı", f"Fotoğraf açılamadı:\n{exc}", parent=self.win)

    def _reset_photo_marks(self):
        self.top_line = []
        self.bottom_line = []
        self.pending_points = []
        self.action = None
        self._remove_temp_artist()
        for interval in self.intervals:
            interval["segments"] = []
        self._refresh_tree(select_index=self.selected_interval)

    def _set_action(self, action):
        if self.image_array is None:
            messagebox.showwarning("Karot TCR", "Önce karot sandığı fotoğrafı seçin.", parent=self.win)
            return
        if action == "segment" and not self._calibration_ready():
            messagebox.showwarning("Karot TCR", "Önce üst ve alt 1.00 m kalibrasyon çizgilerini işaretleyin.", parent=self.win)
            return
        if action == "segment" and self.selected_interval is None:
            messagebox.showwarning("Karot TCR", "Önce bir derinlik aralığı ekleyip seçin.", parent=self.win)
            return
        self.action = action
        self.pending_points = []
        self._remove_temp_artist()
        names = {"top": "Üst 1.00 m çizgisi", "bottom": "Alt 1.00 m çizgisi", "segment": "Karot parçası"}
        self.status_var.set(f"{names[action]} için fotoğraf üzerinde iki nokta tıklayın.")

    def _calibration_ready(self):
        return len(self.top_line) == 2 and len(self.bottom_line) == 2

    def _add_interval(self):
        try:
            top = float(self.ent_top.get().replace(",", "."))
            bot = float(self.ent_bot.get().replace(",", "."))
        except Exception:
            messagebox.showwarning("Derinlik Aralığı", "Başlangıç ve bitiş derinliklerini sayısal girin.", parent=self.win)
            return
        if bot <= top:
            messagebox.showwarning("Derinlik Aralığı", "Bitiş derinliği başlangıçtan büyük olmalı.", parent=self.win)
            return
        new_index = self._append_interval(top, bot)
        self.selected_interval = new_index if new_index is not None else self._find_interval_index(top, bot)
        self.ent_top.delete(0, tk.END)
        self.ent_bot.delete(0, tk.END)
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()

    def _find_interval_index(self, top, bot):
        label = derinlik_araligi_etiketi(top, bot)
        for idx, interval in enumerate(self.intervals):
            if self._interval_label(interval) == label:
                return idx
        return None

    def _append_interval(self, top, bot):
        if bot <= top:
            return None
        if self._find_interval_index(top, bot) is not None:
            return None
        self.intervals.append({"top": float(top), "bot": float(bot), "segments": []})
        return len(self.intervals) - 1

    def _add_template_intervals(self):
        selected = list(self.template_list.curselection())
        if not selected:
            messagebox.showwarning("Karot TCR", "Şablondan en az bir aralık seçin.", parent=self.win)
            return
        first_new = None
        added = 0
        skipped = 0
        for idx in selected:
            top, bot = self.template_intervals[idx]
            new_index = self._append_interval(top, bot)
            if new_index is None:
                skipped += 1
                continue
            if first_new is None:
                first_new = new_index
            added += 1
        if first_new is None and selected:
            top, bot = self.template_intervals[selected[0]]
            first_new = self._find_interval_index(top, bot)
        self.selected_interval = first_new
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()
        self.status_var.set(f"{added} aralık listeye eklendi." + (f" {skipped} tekrar atlandı." if skipped else ""))

    def _add_all_template_intervals(self):
        self.template_list.selection_set(0, tk.END)
        self._add_template_intervals()

    def _clear_intervals(self):
        if not self.intervals:
            return
        if not messagebox.askyesno("Karot TCR", "Listedeki tüm aralıklar ve çizilen parçalar temizlensin mi?", parent=self.win):
            return
        self.intervals.clear()
        self.selected_interval = None
        self.pending_points = []
        self._remove_temp_artist()
        self._refresh_tree()
        self._redraw()
        self.status_var.set("Aralık listesi temizlendi.")

    def _delete_interval(self):
        if self.selected_interval is None or self.selected_interval >= len(self.intervals):
            return
        del self.intervals[self.selected_interval]
        self.selected_interval = min(self.selected_interval, len(self.intervals) - 1) if self.intervals else None
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()

    def _delete_last_segment(self):
        interval = self._current_interval()
        if interval and interval["segments"]:
            interval["segments"].pop()
            self._refresh_tree(select_index=self.selected_interval)
            self._redraw()

    def _clear_selected_segments(self):
        interval = self._current_interval()
        if interval:
            interval["segments"].clear()
            self._refresh_tree(select_index=self.selected_interval)
            self._redraw()

    def _clear_calibration(self):
        self.top_line = []
        self.bottom_line = []
        self.pending_points = []
        self._remove_temp_artist()
        self.status_var.set("Kalibrasyon temizlendi. Üst ve alt 1.00 m çizgilerini yeniden işaretleyin.")
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()

    def _on_interval_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self.selected_interval = None
            return
        try:
            self.selected_interval = int(sel[0])
        except Exception:
            self.selected_interval = None
        self._redraw()

    def _current_interval(self):
        if self.selected_interval is None or self.selected_interval < 0 or self.selected_interval >= len(self.intervals):
            return None
        return self.intervals[self.selected_interval]

    def _on_canvas_click(self, event):
        if event.inaxes != self.ax or self.action is None or event.xdata is None or event.ydata is None:
            return
        point = (float(event.xdata), float(event.ydata))
        self.pending_points.append(point)
        if len(self.pending_points) == 1:
            self._draw_temp_point(point)
            return

        p1, p2 = self.pending_points[:2]
        if self.action == "top":
            self.top_line = [p1, p2]
            self.status_var.set("Üst çizgi alındı. Alt 1.00 m çizgisini işaretleyin.")
            self.action = None
        elif self.action == "bottom":
            self.bottom_line = [p1, p2]
            self.status_var.set("Alt çizgi alındı. Derinlik aralığı ekleyip karot parçalarını işaretleyebilirsiniz.")
            self.action = None
        elif self.action == "segment":
            interval = self._current_interval()
            if interval is not None:
                interval["segments"].append([p1, p2])
                self.status_var.set(f"Karot parçası eklendi: {self._interval_label(interval)}")

        self.pending_points = []
        self._remove_temp_artist()
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()

    def _draw_temp_point(self, point):
        self._remove_temp_artist()
        self.temp_artist = self.ax.plot(point[0], point[1], "yo", markersize=7, markeredgecolor="black")[0]
        self.canvas.draw_idle()

    def _remove_temp_artist(self):
        if self.temp_artist is not None:
            try:
                self.temp_artist.remove()
            except Exception:
                pass
        self.temp_artist = None

    def _interval_label(self, interval):
        return derinlik_araligi_etiketi(interval["top"], interval["bot"])

    def _interval_result(self, interval):
        if not self._calibration_ready():
            return {"ilerleme": interval["bot"] - interval["top"], "karot": 0.0, "tcr": 0.0}
        return tcr_hesapla(interval["top"], interval["bot"], interval["segments"], self.top_line, self.bottom_line)

    def _refresh_tree(self, select_index=None):
        self.tree.delete(*self.tree.get_children())
        for idx, interval in enumerate(self.intervals):
            result = self._interval_result(interval)
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    self._interval_label(interval),
                    f"{result['karot']:.2f} m",
                    f"%{result['tcr']:.0f}",
                    str(len(interval["segments"])),
                ),
            )
        if select_index is not None and 0 <= select_index < len(self.intervals):
            self.tree.selection_set(str(select_index))
            self.tree.focus(str(select_index))
            self.tree.see(str(select_index))

    def _redraw(self):
        self.ax.clear()
        self.ax.axis("off")
        if self.image_array is None:
            self._draw_empty_canvas()
            return
        self.ax.imshow(self.image_array)
        self.ax.set_title("Kalibrasyon ve karot parçaları", fontsize=12, fontweight="bold")
        self._draw_line(self.top_line, "#27AE60", "Üst 1.00 m", lw=2.5)
        self._draw_line(self.bottom_line, "#2980B9", "Alt 1.00 m", lw=2.5)

        colors = ["#E74C3C", "#8E44AD", "#D35400", "#16A085", "#C0392B", "#2C3E50"]
        for idx, interval in enumerate(self.intervals):
            color = colors[idx % len(colors)]
            lw = 3.0 if idx == self.selected_interval else 2.0
            for seg_idx, segment in enumerate(interval["segments"], start=1):
                self._draw_line(segment, color, f"{self._interval_label(interval)} / {seg_idx}", lw=lw)
        self.canvas.draw_idle()

    def _draw_line(self, points, color, label, lw=2.0):
        if len(points) != 2:
            return
        (x1, y1), (x2, y2) = points
        self.ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, marker="o", markeredgecolor="black")
        self.ax.text((x1 + x2) / 2, (y1 + y2) / 2, label, color=color, fontsize=8, fontweight="bold",
                     bbox=dict(facecolor="white", alpha=0.78, edgecolor=color, pad=2))

    def _target_sondaj(self):
        target_no = self.target_var.get()
        for sondaj in self.app.veri.get("sondaj", []):
            if (sondaj.get("no") or "") == target_no:
                return sondaj
        return None

    def _aktar(self):
        if not self.intervals:
            messagebox.showwarning("Karot TCR", "Aktarılacak derinlik aralığı yok.", parent=self.win)
            return
        if not self._calibration_ready():
            messagebox.showwarning("Karot TCR", "Aktarım için üst ve alt 1.00 m kalibrasyon çizgileri gerekli.", parent=self.win)
            return
        sondaj = self._target_sondaj()
        if not sondaj:
            messagebox.showwarning("Karot TCR", "Hedef sondaj bulunamadı.", parent=self.win)
            return

        kaya_rows = sondaj.setdefault("kaya", [])
        by_label = {str(row[0]).strip(): row for row in kaya_rows if row}
        aktarilan = 0
        for interval in self.intervals:
            result = self._interval_result(interval)
            label = self._interval_label(interval)
            tcr = f"{result['tcr']:.0f}"
            if label in by_label:
                row = by_label[label]
                while len(row) < 4:
                    row.append("")
                row[1] = tcr
            else:
                kaya_rows.append([label, tcr, "", ""])
            aktarilan += 1

        kaya_rows.sort(key=lambda row: derinlik_baslangic(row[0] if row else ""))
        self.app.sondaj_tablosunu_ciz()
        self.app.ozet_yenile(collect=False)
        self.app.set_status(f"{sondaj.get('no')}: {aktarilan} karot TCR aralığı kaya tablosuna aktarıldı.", level="success")
        messagebox.showinfo("Karot TCR", f"{aktarilan} aralık {sondaj.get('no')} kaya tablosuna aktarıldı.", parent=self.win)
