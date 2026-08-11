import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from PIL import Image, ImageOps

from karot_aktarim_motoru import (
    karot_aktarim_plani_olustur,
    karot_aktarim_plani_uygula,
    karot_aktarimini_geri_al,
)
from karot_gorunum import gorunum_kaydir, gorunum_yakinlastir, tam_gorunum
from karot_motoru import (
    KarotKalibrasyonHatasi,
    derinlik_araligi_etiketi,
    homografi_hesapla,
    kalibrasyon_dogrula,
    karot_araliklarini_dogrula,
    karot_kalite_hesapla,
    parca_uzunlugu_metre,
    standart_karot_araliklari,
)
from karot_oturum_motoru import (
    KarotOturumHatasi,
    karot_oturumu_olustur,
    karot_oturumunu_coz,
    karot_oturumunu_kaydet,
    kaynak_icin_karot_oturumu,
    son_karot_oturumu,
)
from sabitler import COLOR_BG, COLOR_PRIMARY, COLOR_SUCCESS, FONT_BOLD
from widgets import UndoRedoEntry


class KarotTCRMixin:
    def karot_tcr_merkezi_ac(self):
        self.sondaj_verilerini_kaydet(silent=True)
        KarotTCRPenceresi(self)


class KarotTCRPenceresi:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.app.pencere_hazirla(self.win, "Karot TCR / SCR / RQD Merkezi", "1360x840", (1060, 680), modal=False)

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
        self.session_dirty = False
        self._last_interval_error = ""
        self.view_limits = None
        self._editable_artists = []
        self._drag_info = None
        self._pan_info = None

        self.target_var = tk.StringVar()
        self.quality_var = tk.StringVar(
            value="Kalibrasyon ve aralık kalite bilgisi burada görünür."
        )
        self.status_var = tk.StringVar(value="Fotoğraf seçin, ardından üst ve alt 1 m kalibrasyon çizgilerini işaretleyin.")

        self._build_ui()
        self._refresh_target_values()
        self._draw_empty_canvas()
        previous_transfer = getattr(self.app, "_karot_son_aktarim", None)
        if (
            isinstance(previous_transfer, dict)
            and previous_transfer.get("project_marker") == id(self.app.veri)
        ):
            self.btn_undo_transfer.configure(state="normal")
        self.win.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        root = ttk.Frame(self.win, padding=8)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="Karot TCR / SCR / RQD Merkezi", bg=COLOR_BG, fg=COLOR_PRIMARY, font=("Segoe UI", 15, "bold")).pack(side="left")
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

        view_toolbar = ttk.Frame(left)
        view_toolbar.pack(fill="x", pady=(0, 4))
        tk.Button(
            view_toolbar,
            text="+",
            width=4,
            command=lambda: self._zoom_view(0.80),
            font=FONT_BOLD,
        ).pack(side="left", padx=(0, 3))
        tk.Button(
            view_toolbar,
            text="-",
            width=4,
            command=lambda: self._zoom_view(1.25),
            font=FONT_BOLD,
        ).pack(side="left", padx=3)
        tk.Button(
            view_toolbar,
            text="Sığdır",
            command=self._fit_view,
            font=FONT_BOLD,
        ).pack(side="left", padx=3)
        self.btn_pan_mode = tk.Button(
            view_toolbar,
            text="Kaydır",
            command=lambda: self._set_view_mode("pan"),
            font=FONT_BOLD,
        )
        self.btn_pan_mode.pack(side="left", padx=(12, 3))
        self.btn_edit_mode = tk.Button(
            view_toolbar,
            text="Nokta Düzenle",
            command=lambda: self._set_view_mode("edit"),
            font=FONT_BOLD,
        )
        self.btn_edit_mode.pack(side="left", padx=3)

        self.fig, self.ax = plt.subplots(figsize=(8.5, 6.5))
        self.fig.patch.set_facecolor("#F4F6F7")
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_canvas_click)
        self.canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self.canvas.mpl_connect("button_release_event", self._on_canvas_release)
        self.canvas.mpl_connect("scroll_event", self._on_canvas_scroll)

        source_frame = ttk.LabelFrame(right, text="Kaynak", padding=8)
        source_frame.pack(fill="x", pady=(0, 8))
        tk.Button(source_frame, text="Fotoğraf Seç", command=self._select_image, bg="#34495E", fg="white", font=FONT_BOLD).pack(fill="x", pady=2)
        self.lbl_image = ttk.Label(source_frame, text="Fotoğraf seçilmedi", wraplength=320)
        self.lbl_image.pack(fill="x", pady=(4, 0))
        session_row = ttk.Frame(source_frame)
        session_row.pack(fill="x", pady=(6, 0))
        tk.Button(
            session_row,
            text="Oturumu Kaydet",
            command=self._save_session,
            bg="#D5F5E3",
            font=FONT_BOLD,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(
            session_row,
            text="Son Oturumu Aç",
            command=self._load_last_session,
            bg="#D6EAF8",
            font=FONT_BOLD,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        target_frame = ttk.LabelFrame(right, text="Aktarım", padding=8)
        target_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(target_frame, text="Hedef sondaj").pack(anchor="w")
        self.cmb_target = ttk.Combobox(target_frame, textvariable=self.target_var, state="readonly")
        self.cmb_target.pack(fill="x", pady=(2, 6))
        tk.Button(target_frame, text="Kaya Tablosuna Aktar", command=self._aktar, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(fill="x", pady=2)
        self.btn_undo_transfer = tk.Button(
            target_frame,
            text="Son Aktarımı Geri Al",
            command=self._undo_transfer,
            bg="#FDEBD0",
            font=FONT_BOLD,
            state="disabled",
        )
        self.btn_undo_transfer.pack(fill="x", pady=2)

        results_frame = ttk.LabelFrame(right, text="Seçilen Aralıklar", padding=8)
        results_frame.pack(fill="x", pady=(0, 8))
        results_table = ttk.Frame(results_frame)
        results_table.pack(fill="x")
        columns = ("aralik", "tcr", "scr", "rqd", "parca", "durum")
        self.tree = ttk.Treeview(results_table, columns=columns, show="headings", height=7, selectmode="browse")
        for key, label, width in [
            ("aralik", "Aralık", 82),
            ("tcr", "TCR", 44),
            ("scr", "SCR", 44),
            ("rqd", "RQD", 44),
            ("parca", "T/S", 50),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        self.tree.heading("durum", text="Durum")
        self.tree.column("durum", width=70, anchor="center")
        tree_scroll = ttk.Scrollbar(results_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="x", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_interval_select)
        self.tree.tag_configure("ready", foreground="#1E8449")
        self.tree.tag_configure("warning", foreground="#B9770E")
        self.tree.tag_configure("error", foreground="#C0392B")
        self.tree.tag_configure("pending", foreground="#5D6D7E")
        ttk.Label(
            results_frame,
            textvariable=self.quality_var,
            wraplength=315,
            justify="left",
        ).pack(fill="x", pady=(6, 0))

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
        tk.Button(
            segment_frame,
            text="Toplam Karot (TCR) İşaretle",
            command=lambda: self._set_action("segment"),
            bg="#E8DAEF",
            font=FONT_BOLD,
        ).pack(fill="x", pady=2)
        tk.Button(
            segment_frame,
            text="Sağlam Parça (SCR/RQD) İşaretle",
            command=lambda: self._set_action("solid_segment"),
            bg="#D4EFDF",
            font=FONT_BOLD,
        ).pack(fill="x", pady=2)
        delete_row = ttk.Frame(segment_frame)
        delete_row.pack(fill="x")
        tk.Button(
            delete_row,
            text="Son TCR Sil",
            command=self._delete_last_segment,
            bg="#FDEBD0",
            font=FONT_BOLD,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3), pady=2)
        tk.Button(
            delete_row,
            text="Son Sağlam Sil",
            command=self._delete_last_solid_segment,
            bg="#FDEBD0",
            font=FONT_BOLD,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0), pady=2)
        tk.Button(
            segment_frame,
            text="Sağlam Parça Yok (%0)",
            command=self._set_no_solid_core,
            bg="#D6EAF8",
            font=FONT_BOLD,
        ).pack(fill="x", pady=2)
        tk.Button(
            segment_frame,
            text="SCR/RQD Ölçümünü Kaldır",
            command=self._clear_quality_measurement,
            bg="#F4ECF7",
            font=FONT_BOLD,
        ).pack(fill="x", pady=2)
        tk.Button(
            segment_frame,
            text="Seçili Aralığı Temizle",
            command=self._clear_selected_segments,
            bg="#FADBD8",
            font=FONT_BOLD,
        ).pack(fill="x", pady=2)

    def _refresh_target_values(self):
        values = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(self.app.veri.get("sondaj", []))]
        self.cmb_target["values"] = values
        if values and not self.target_var.get():
            selected_index = None
            try:
                selected_index = self.app.sondaj_secili_index()
            except Exception:
                selected_index = None
            if selected_index is not None and 0 <= selected_index < len(values):
                self.target_var.set(values[selected_index])
            else:
                self.target_var.set(values[0])

    def _image_size(self):
        if self.image_array is None:
            return None
        height, width = self.image_array.shape[:2]
        return width, height

    def _mark_dirty(self):
        self.session_dirty = True

    def _confirm_unsaved_session(self):
        if not self.session_dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Karot TCR Oturumu",
            "Kaydedilmemiş kalibrasyon veya karot işaretleri var.\n\n"
            "Fotoğrafı/pencereyi değiştirmeden önce oturum projeye kaydedilsin mi?",
            parent=self.win,
        )
        if answer is None:
            return False
        if answer:
            return self._save_session(show_message=False)
        return True

    def _close(self):
        if not self._confirm_unsaved_session():
            return

        def finish_close():
            try:
                plt.close(self.fig)
            except Exception:
                pass
            try:
                self.win.destroy()
            except tk.TclError:
                pass

        self.app.pencere_kapat(self.win, callback=finish_close)

    def _sync_mode_buttons(self):
        self.btn_pan_mode.configure(relief=tk.SUNKEN if self.action == "pan" else tk.RAISED)
        self.btn_edit_mode.configure(relief=tk.SUNKEN if self.action == "edit" else tk.RAISED)
        cursor = (
            "fleur"
            if self.action == "pan"
            else "crosshair"
            if self.action in ("edit", "top", "bottom", "segment", "solid_segment")
            else ""
        )
        self.canvas.get_tk_widget().configure(cursor=cursor)

    def _set_view_mode(self, mode):
        if self.image_array is None:
            messagebox.showwarning(
                "Karot TCR",
                "Önce karot sandığı fotoğrafı seçin.",
                parent=self.win,
            )
            return
        self.action = None if self.action == mode else mode
        self.pending_points = []
        self._drag_info = None
        self._pan_info = None
        self._remove_temp_artist()
        self._sync_mode_buttons()
        if self.action == "pan":
            self.status_var.set("Kaydırma modu açık. Fotoğrafı fareyle sürükleyin.")
        elif self.action == "edit":
            self.status_var.set(
                "Nokta düzenleme modu açık. Bir çizgi ucunu fareyle sürükleyin."
            )
        else:
            self.status_var.set("Görünüm modu kapatıldı.")

    def _apply_view_limits(self):
        if self.view_limits is None:
            return
        xlim, ylim = self.view_limits
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)

    def _fit_view(self, redraw=True):
        if self.image_array is None:
            return
        height, width = self.image_array.shape[:2]
        self.view_limits = tam_gorunum((width, height))
        if redraw:
            self._apply_view_limits()
            self.canvas.draw_idle()

    def _zoom_view(self, factor, center=None):
        if self.image_array is None:
            return
        if self.view_limits is None:
            self._fit_view(redraw=False)
        xlim, ylim = self.view_limits
        center_x = (xlim[0] + xlim[1]) / 2.0
        center_y = (ylim[0] + ylim[1]) / 2.0
        if center is not None:
            center_x, center_y = center

        height, width = self.image_array.shape[:2]
        self.view_limits = gorunum_yakinlastir(
            xlim,
            ylim,
            factor,
            (center_x, center_y),
            (width, height),
        )
        self._apply_view_limits()
        self.canvas.draw_idle()

    def _on_canvas_scroll(self, event):
        if (
            self.image_array is None
            or event.inaxes != self.ax
            or event.xdata is None
            or event.ydata is None
        ):
            return
        factor = 0.80 if event.step > 0 else 1.25
        self._zoom_view(factor, center=(float(event.xdata), float(event.ydata)))

    def _draw_empty_canvas(self):
        self.view_limits = None
        self._editable_artists = []
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
        if not self._confirm_unsaved_session():
            return
        self._load_image_path(path, restore_matching=True)

    def _load_image_path(self, path, restore_matching=False):
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                self.image_array = np.asarray(image)
            self.image_path = path
            self.view_limits = None
            self.lbl_image.configure(text=os.path.basename(path))
            self._reset_photo_marks()
            restored = False
            if restore_matching:
                session = kaynak_icin_karot_oturumu(self._target_sondaj(), path)
                if session:
                    self._restore_session(session)
                    restored = True
            self.session_dirty = False
            if restored:
                self.status_var.set("Fotoğraf ve bu kaynağa ait kayıtlı ölçüm oturumu yüklendi.")
            else:
                self.status_var.set(
                    "Yeni fotoğraf yüklendi. Kalibrasyon ve karot işaretlemeleri temizlendi."
                )
            self._redraw(preserve_view=False)
            return True
        except Exception as exc:
            messagebox.showerror("Karot Fotoğrafı", f"Fotoğraf açılamadı:\n{exc}", parent=self.win)
            return False

    def _reset_photo_marks(self):
        self.top_line = []
        self.bottom_line = []
        self.pending_points = []
        self.action = None
        self._drag_info = None
        self._pan_info = None
        self._editable_artists = []
        self._remove_temp_artist()
        self._sync_mode_buttons()
        for interval in self.intervals:
            interval["segments"] = []
            interval["solid_segments"] = []
            interval["quality_assessed"] = False
        self._refresh_tree(select_index=self.selected_interval)

    def _save_session(self, show_message=True):
        if self.image_array is None or not self.image_path:
            messagebox.showwarning(
                "Karot TCR Oturumu",
                "Kaydedilecek bir karot sandığı fotoğrafı yok.",
                parent=self.win,
            )
            return False
        sondaj = self._target_sondaj()
        if not sondaj:
            messagebox.showwarning(
                "Karot TCR Oturumu",
                "Oturumun kaydedileceği hedef sondaj bulunamadı.",
                parent=self.win,
            )
            return False
        try:
            session = karot_oturumu_olustur(
                self.image_path,
                self._image_size(),
                self.top_line,
                self.bottom_line,
                self.intervals,
            )
            karot_oturumunu_kaydet(sondaj, session)
        except (KarotOturumHatasi, OSError, ValueError) as exc:
            messagebox.showerror(
                "Karot TCR Oturumu",
                f"Oturum kaydedilemedi:\n{exc}",
                parent=self.win,
            )
            return False
        self.session_dirty = False
        self.status_var.set(
            f"{sondaj.get('no')}: karot ölçüm oturumu proje içine kaydedildi."
        )
        if show_message:
            messagebox.showinfo(
                "Karot TCR Oturumu",
                "Kalibrasyon, aralıklar ve parça işaretleri proje içine kaydedildi.",
                parent=self.win,
            )
        return True

    def _restore_session(self, session):
        restored = karot_oturumunu_coz(session, self._image_size())
        self.top_line = restored["top_line"]
        self.bottom_line = restored["bottom_line"]
        self.intervals = restored["intervals"]
        for interval in self.intervals:
            self._prepare_interval(interval)
        self.selected_interval = 0 if self.intervals else None
        self.pending_points = []
        self.action = None
        self._drag_info = None
        self._pan_info = None
        self._editable_artists = []
        self._sync_mode_buttons()
        self._remove_temp_artist()
        self._refresh_tree(select_index=self.selected_interval)
        self.session_dirty = False

    def _load_last_session(self):
        sondaj = self._target_sondaj()
        session = son_karot_oturumu(sondaj)
        if not session:
            messagebox.showinfo(
                "Karot TCR Oturumu",
                "Seçili sondaj için kayıtlı karot ölçüm oturumu yok.",
                parent=self.win,
            )
            return
        if not self._confirm_unsaved_session():
            return
        path = str((session.get("kaynak") or {}).get("yol") or "")
        if not path or not os.path.isfile(path):
            messagebox.showwarning(
                "Karot TCR Oturumu",
                "Oturum kaydı bulundu ancak kaynak fotoğraf artık bu konumda değil:\n"
                f"{path or '(yol kaydı yok)'}",
                parent=self.win,
            )
            return
        if not self._load_image_path(path, restore_matching=False):
            return
        try:
            self._restore_session(session)
            self.status_var.set("Seçili sondajın son karot ölçüm oturumu açıldı.")
            self._redraw()
        except KarotOturumHatasi as exc:
            messagebox.showerror(
                "Karot TCR Oturumu",
                f"Oturum açılamadı:\n{exc}",
                parent=self.win,
            )

    def _set_action(self, action):
        if self.image_array is None:
            messagebox.showwarning("Karot TCR", "Önce karot sandığı fotoğrafı seçin.", parent=self.win)
            return
        if action in ("segment", "solid_segment") and not self._calibration_ready():
            messagebox.showwarning("Karot TCR", "Önce üst ve alt 1.00 m kalibrasyon çizgilerini işaretleyin.", parent=self.win)
            return
        if action in ("segment", "solid_segment"):
            try:
                kalibrasyon_dogrula(self.top_line, self.bottom_line)
            except KarotKalibrasyonHatasi as exc:
                messagebox.showwarning(
                    "Karot TCR Kalibrasyonu",
                    f"Kalibrasyon güvenilir değil:\n{exc}",
                    parent=self.win,
                )
                return
        if action in ("segment", "solid_segment") and self.selected_interval is None:
            messagebox.showwarning("Karot TCR", "Önce bir derinlik aralığı ekleyip seçin.", parent=self.win)
            return
        self.action = action
        self.pending_points = []
        self._drag_info = None
        self._pan_info = None
        self._remove_temp_artist()
        self._sync_mode_buttons()
        names = {
            "top": "Üst 1.00 m çizgisi",
            "bottom": "Alt 1.00 m çizgisi",
            "segment": "Toplam karot parçası",
            "solid_segment": "Sağlam tam çaplı karot parçası",
        }
        if action == "solid_segment":
            self.status_var.set(
                "Sağlam parçanın iki ucunu seçin; doğal kırıklar arasındaki her parçayı "
                "ayrı işaretleyin. 10 cm ve üzeri parçalar RQD'ye otomatik katılır."
            )
        else:
            self.status_var.set(f"{names[action]} için fotoğraf üzerinde iki nokta tıklayın.")

    def _calibration_ready(self):
        return len(self.top_line) == 2 and len(self.bottom_line) == 2

    def _target_depth(self):
        sondaj = self._target_sondaj()
        if not sondaj:
            return None
        value = str(sondaj.get("der", "") or "").strip().replace(",", ".")
        try:
            depth = float(value)
        except (TypeError, ValueError):
            return None
        return depth if depth > 0 else None

    def _interval_validation(self, intervals=None):
        return karot_araliklarini_dogrula(
            self.intervals if intervals is None else intervals,
            total_depth=self._target_depth(),
        )

    @staticmethod
    def _prepare_interval(interval):
        interval.setdefault("segments", [])
        interval.setdefault("solid_segments", [])
        interval.setdefault("quality_assessed", False)
        return interval

    @classmethod
    def _new_interval(cls, top, bot):
        return cls._prepare_interval(
            {
                "top": float(top),
                "bot": float(bot),
            }
        )

    def _add_interval(self):
        try:
            top = float(self.ent_top.get().replace(",", "."))
            bot = float(self.ent_bot.get().replace(",", "."))
        except Exception:
            messagebox.showwarning("Derinlik Aralığı", "Başlangıç ve bitiş derinliklerini sayısal girin.", parent=self.win)
            return
        new_index = self._append_interval(top, bot)
        if new_index is None:
            messagebox.showwarning(
                "Derinlik Aralığı",
                self._last_interval_error or "Derinlik aralığı eklenemedi.",
                parent=self.win,
            )
            existing = self._find_interval_index(top, bot)
            if existing is not None:
                self.selected_interval = existing
                self._refresh_tree(select_index=existing)
            return
        self.selected_interval = new_index
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
        new_interval = self._new_interval(top, bot)
        candidate = list(self.intervals) + [new_interval]
        report = self._interval_validation(candidate)
        if report["hatalar"]:
            self._last_interval_error = report["hatalar"][0]["mesaj"]
            return None
        self.intervals.append(new_interval)
        self._last_interval_error = ""
        self._mark_dirty()
        return len(self.intervals) - 1

    def _add_template_intervals(self):
        selected = list(self.template_list.curselection())
        if not selected:
            messagebox.showwarning("Karot TCR", "Şablondan en az bir aralık seçin.", parent=self.win)
            return
        first_new = None
        added = 0
        skipped = 0
        skipped_messages = []
        for idx in selected:
            top, bot = self.template_intervals[idx]
            new_index = self._append_interval(top, bot)
            if new_index is None:
                skipped += 1
                if self._last_interval_error:
                    skipped_messages.append(self._last_interval_error)
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
        self.status_var.set(
            f"{added} aralık listeye eklendi."
            + (f" {skipped} uygunsuz veya tekrar aralık atlandı." if skipped else "")
        )
        if not added and skipped_messages:
            messagebox.showwarning(
                "Karot TCR Aralıkları",
                skipped_messages[0],
                parent=self.win,
            )

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
        self._mark_dirty()
        self._refresh_tree()
        self._redraw()
        self.status_var.set("Aralık listesi temizlendi.")

    def _delete_interval(self):
        if self.selected_interval is None or self.selected_interval >= len(self.intervals):
            return
        del self.intervals[self.selected_interval]
        self.selected_interval = min(self.selected_interval, len(self.intervals) - 1) if self.intervals else None
        self._mark_dirty()
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()

    def _delete_last_segment(self):
        interval = self._current_interval()
        if interval and interval["segments"]:
            interval["segments"].pop()
            self._mark_dirty()
            self._refresh_tree(select_index=self.selected_interval)
            self._redraw()

    def _delete_last_solid_segment(self):
        interval = self._current_interval()
        if interval and interval["solid_segments"]:
            interval["solid_segments"].pop()
            interval["quality_assessed"] = True
            self._mark_dirty()
            self._refresh_tree(select_index=self.selected_interval)
            self._redraw()

    def _set_no_solid_core(self):
        interval = self._current_interval()
        if interval is None:
            messagebox.showwarning(
                "Karot TCR / SCR / RQD",
                "Önce bir derinlik aralığı seçin.",
                parent=self.win,
            )
            return
        interval["solid_segments"].clear()
        interval["quality_assessed"] = True
        self._mark_dirty()
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()
        self.status_var.set(
            f"{self._interval_label(interval)}: sağlam parça yok; SCR ve RQD %0 olarak işaretlendi."
        )

    def _clear_quality_measurement(self):
        interval = self._current_interval()
        if interval is None:
            return
        interval["solid_segments"].clear()
        interval["quality_assessed"] = False
        self._mark_dirty()
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()
        self.status_var.set(
            f"{self._interval_label(interval)}: SCR/RQD ölçümü kaldırıldı; aktarımda mevcut değer korunacak."
        )

    def _clear_selected_segments(self):
        interval = self._current_interval()
        if interval:
            interval["segments"].clear()
            interval["solid_segments"].clear()
            interval["quality_assessed"] = False
            self._mark_dirty()
            self._refresh_tree(select_index=self.selected_interval)
            self._redraw()

    def _clear_calibration(self):
        self.top_line = []
        self.bottom_line = []
        self.pending_points = []
        self._remove_temp_artist()
        self._mark_dirty()
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
        self._update_quality_note()
        self._redraw()

    def _current_interval(self):
        if self.selected_interval is None or self.selected_interval < 0 or self.selected_interval >= len(self.intervals):
            return None
        return self._prepare_interval(self.intervals[self.selected_interval])

    def _start_pan(self, event):
        if event.x is None or event.y is None:
            return
        if self.view_limits is None:
            self._fit_view(redraw=False)
        self._pan_info = {
            "x": float(event.x),
            "y": float(event.y),
            "xlim": tuple(self.view_limits[0]),
            "ylim": tuple(self.view_limits[1]),
        }

    def _nearest_editable_point(self, event, max_distance=14.0):
        if event.x is None or event.y is None:
            return None
        nearest = None
        nearest_distance = float(max_distance)
        for entry in self._editable_artists:
            for point_index, point in enumerate(entry["points"]):
                display_x, display_y = self.ax.transData.transform(point)
                distance = (
                    (display_x - float(event.x)) ** 2
                    + (display_y - float(event.y)) ** 2
                ) ** 0.5
                if distance <= nearest_distance:
                    nearest_distance = distance
                    nearest = {
                        "entry": entry,
                        "point_index": point_index,
                        "original": tuple(point),
                        "moved": False,
                    }
        return nearest

    def _start_point_drag(self, event):
        self._drag_info = self._nearest_editable_point(event)
        if self._drag_info is None:
            self.status_var.set(
                "Taşımak için kalibrasyon veya karot çizgisinin uç noktasına yakın tıklayın."
            )
            return
        self.status_var.set(
            f"{self._drag_info['entry']['label']} uç noktası düzenleniyor."
        )

    def _image_point(self, x, y, clamp=False):
        if self.image_array is None:
            return None
        height, width = self.image_array.shape[:2]
        x = float(x)
        y = float(y)
        if clamp:
            return (
                max(0.0, min(width - 1.0, x)),
                max(0.0, min(height - 1.0, y)),
            )
        if 0.0 <= x <= width - 1.0 and 0.0 <= y <= height - 1.0:
            return x, y
        return None

    def _on_canvas_click(self, event):
        if (
            event.inaxes != self.ax
            or self.action is None
            or event.xdata is None
            or event.ydata is None
            or event.button != 1
        ):
            return
        if self.action == "pan":
            self._start_pan(event)
            return
        if self.action == "edit":
            self._start_point_drag(event)
            return
        point = self._image_point(event.xdata, event.ydata)
        if point is None:
            self.status_var.set("İşaret noktası fotoğraf sınırları içinde olmalıdır.")
            return
        self.pending_points.append(point)
        if len(self.pending_points) == 1:
            self._draw_temp_point(point)
            return

        p1, p2 = self.pending_points[:2]
        if self.action == "top":
            self.top_line = [p1, p2]
            self.status_var.set("Üst çizgi alındı. Alt 1.00 m çizgisini işaretleyin.")
            self.action = None
            self._mark_dirty()
        elif self.action == "bottom":
            self.bottom_line = [p1, p2]
            self.status_var.set("Alt çizgi alındı. Derinlik aralığı ekleyip karot parçalarını işaretleyebilirsiniz.")
            self.action = None
            self._mark_dirty()
        elif self.action == "segment":
            interval = self._current_interval()
            if interval is not None:
                interval["segments"].append([p1, p2])
                self.status_var.set(f"TCR parçası eklendi: {self._interval_label(interval)}")
                self._mark_dirty()
        elif self.action == "solid_segment":
            interval = self._current_interval()
            if interval is not None:
                interval["solid_segments"].append([p1, p2])
                interval["quality_assessed"] = True
                self.status_var.set(
                    f"Sağlam SCR/RQD parçası eklendi: {self._interval_label(interval)}"
                )
                self._mark_dirty()

        self.pending_points = []
        self._remove_temp_artist()
        self._sync_mode_buttons()
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()
        if self._calibration_ready():
            try:
                quality = kalibrasyon_dogrula(self.top_line, self.bottom_line)
                if quality["uyarilar"]:
                    self.status_var.set(quality["uyarilar"][0])
            except KarotKalibrasyonHatasi as exc:
                self.status_var.set(f"Kalibrasyon hatası: {exc}")

    def _on_canvas_motion(self, event):
        if self._pan_info is not None and event.x is not None and event.y is not None:
            bbox = self.ax.bbox
            if bbox.width <= 0 or bbox.height <= 0:
                return
            original_xlim = self._pan_info["xlim"]
            original_ylim = self._pan_info["ylim"]
            dx_pixels = float(event.x) - self._pan_info["x"]
            dy_pixels = float(event.y) - self._pan_info["y"]
            self.view_limits = gorunum_kaydir(
                original_xlim,
                original_ylim,
                (dx_pixels, dy_pixels),
                (bbox.width, bbox.height),
            )
            self._apply_view_limits()
            self.canvas.draw_idle()
            return

        if (
            self._drag_info is None
            or event.inaxes != self.ax
            or event.xdata is None
            or event.ydata is None
        ):
            return
        entry = self._drag_info["entry"]
        point_index = self._drag_info["point_index"]
        point = self._image_point(event.xdata, event.ydata, clamp=True)
        if point is None:
            return
        entry["points"][point_index] = point
        (x1, y1), (x2, y2) = entry["points"]
        entry["line_artist"].set_data([x1, x2], [y1, y2])
        entry["text_artist"].set_position(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
        self._drag_info["moved"] = True
        self.canvas.draw_idle()

    def _on_canvas_release(self, event):
        if self._pan_info is not None:
            self._pan_info = None
            return
        if self._drag_info is None:
            return
        moved = self._drag_info.get("moved", False)
        label = self._drag_info["entry"]["label"]
        self._drag_info = None
        if not moved:
            return
        self._mark_dirty()
        self._refresh_tree(select_index=self.selected_interval)
        self._redraw()
        if self._calibration_ready():
            try:
                kalibrasyon_dogrula(self.top_line, self.bottom_line)
            except KarotKalibrasyonHatasi as exc:
                self.status_var.set(f"Nokta güncellendi; kalibrasyon hatası: {exc}")
                return
        interval = self._current_interval()
        result = self._interval_result(interval) if interval is not None else {}
        if result.get("hatalar"):
            self.status_var.set(f"Nokta güncellendi; kontrol gerekli: {result['hatalar'][0]}")
        else:
            self.status_var.set(f"{label} uç noktası güncellendi.")

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
        interval = self._prepare_interval(interval)
        if not self._calibration_ready():
            return {
                "ilerleme": interval["bot"] - interval["top"],
                "karot": 0.0,
                "tcr": 0.0,
                "saglam_karot": None,
                "scr": None,
                "rqd_karot": None,
                "rqd": None,
                "hatalar": [],
                "uyarilar": [],
                "gecerli": False,
                "bekliyor": True,
                "kalite_bekliyor": not interval["quality_assessed"],
            }
        try:
            return karot_kalite_hesapla(
                interval["top"],
                interval["bot"],
                interval["segments"],
                interval["solid_segments"],
                self.top_line,
                self.bottom_line,
                quality_assessed=interval["quality_assessed"],
            )
        except (KarotKalibrasyonHatasi, ValueError) as exc:
            return {
                "ilerleme": interval["bot"] - interval["top"],
                "karot": 0.0,
                "tcr": 0.0,
                "saglam_karot": None,
                "scr": None,
                "rqd_karot": None,
                "rqd": None,
                "hatalar": [str(exc)],
                "uyarilar": [],
                "gecerli": False,
                "kalite_bekliyor": not interval["quality_assessed"],
            }

    @staticmethod
    def _result_status(result):
        if result.get("bekliyor"):
            return "Bekliyor", "pending"
        if result.get("hatalar"):
            return "Hata", "error"
        if result.get("uyarilar"):
            return "Kontrol", "warning"
        if result.get("kalite_bekliyor"):
            return "TCR Hazır", "warning"
        return "Hazır", "ready"

    def _refresh_tree(self, select_index=None):
        self.tree.delete(*self.tree.get_children())
        for idx, interval in enumerate(self.intervals):
            interval = self._prepare_interval(interval)
            result = self._interval_result(interval)
            status, tag = self._result_status(result)
            scr_text = "-" if result.get("scr") is None else f"%{result['scr']:.0f}"
            rqd_text = "-" if result.get("rqd") is None else f"%{result['rqd']:.0f}"
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    self._interval_label(interval),
                    f"%{result['tcr']:.0f}",
                    scr_text,
                    rqd_text,
                    f"{len(interval['segments'])}/{len(interval['solid_segments'])}",
                    status,
                ),
                tags=(tag,),
            )
        if select_index is not None and 0 <= select_index < len(self.intervals):
            self.tree.selection_set(str(select_index))
            self.tree.focus(str(select_index))
            self.tree.see(str(select_index))
        self._update_quality_note()

    def _update_quality_note(self):
        interval = self._current_interval()
        if interval is None:
            self.quality_var.set(
                "Bir aralık seçildiğinde kalibrasyon ve parça kalite bilgisi burada görünür."
            )
            return
        result = self._interval_result(interval)
        if result.get("bekliyor"):
            text = "Bekliyor: üst ve alt 1.00 m kalibrasyon çizgilerini işaretleyin."
        elif result.get("hatalar"):
            text = "Hata: " + str(result["hatalar"][0])
        elif result.get("uyarilar"):
            text = "Kontrol: " + str(result["uyarilar"][0])
        elif result.get("kalite_bekliyor"):
            text = (
                f"TCR hazır: {len(interval['segments'])} parça, "
                f"{result['karot']:.2f} m, TCR %{result['tcr']:.0f}. "
                "SCR/RQD henüz ölçülmedi."
            )
        else:
            text = (
                f"Hazır: TCR {result['karot']:.2f} m (%{result['tcr']:.0f}); "
                f"sağlam {result['saglam_karot']:.2f} m (SCR %{result['scr']:.0f}); "
                f"10 cm+ {result['rqd_karot']:.2f} m "
                f"(RQD %{result['rqd']:.0f}, {result['rqd_parca_sayisi']} parça)."
            )
        self.quality_var.set(text)

    def _redraw(self, preserve_view=True):
        if preserve_view and self.image_array is not None and self.ax.has_data():
            self.view_limits = (tuple(self.ax.get_xlim()), tuple(self.ax.get_ylim()))
        self._editable_artists = []
        self.ax.clear()
        self.ax.axis("off")
        if self.image_array is None:
            self._draw_empty_canvas()
            return
        self.ax.imshow(self.image_array)
        self.ax.set_title("TCR, SCR ve RQD karot parçaları", fontsize=12, fontweight="bold")
        self._draw_line(self.top_line, "#27AE60", "Üst 1.00 m", lw=2.5)
        self._draw_line(self.bottom_line, "#2980B9", "Alt 1.00 m", lw=2.5)

        homography = None
        if self._calibration_ready():
            try:
                homography = homografi_hesapla(self.top_line, self.bottom_line)
            except KarotKalibrasyonHatasi:
                homography = None

        colors = ["#E74C3C", "#8E44AD", "#D35400", "#16A085", "#C0392B", "#2C3E50"]
        for idx, interval in enumerate(self.intervals):
            interval = self._prepare_interval(interval)
            color = colors[idx % len(colors)]
            lw = 3.0 if idx == self.selected_interval else 2.0
            for seg_idx, segment in enumerate(interval["segments"], start=1):
                self._draw_line(
                    segment,
                    color,
                    f"TCR {self._interval_label(interval)} / {seg_idx}",
                    lw=lw,
                )
            solid_lw = 3.5 if idx == self.selected_interval else 2.5
            for seg_idx, segment in enumerate(interval["solid_segments"], start=1):
                length = None
                if homography is not None:
                    try:
                        length = parca_uzunlugu_metre(homography, segment)
                    except (KarotKalibrasyonHatasi, TypeError, ValueError):
                        length = None
                qualifies_rqd = length is not None and length + 1e-9 >= 0.10
                solid_color = "#117A65" if qualifies_rqd else "#B9770E"
                quality_label = "RQD" if qualifies_rqd else "SCR"
                self._draw_line(
                    segment,
                    solid_color,
                    f"{quality_label} {self._interval_label(interval)} / {seg_idx}",
                    lw=solid_lw,
                    linestyle="--",
                    marker="s",
                )
        if self.view_limits is None:
            self._fit_view(redraw=False)
        self._apply_view_limits()
        self.canvas.draw_idle()

    def _draw_line(
        self,
        points,
        color,
        label,
        lw=2.0,
        linestyle="-",
        marker="o",
    ):
        if len(points) != 2:
            return
        (x1, y1), (x2, y2) = points
        line_artist = self.ax.plot(
            [x1, x2],
            [y1, y2],
            color=color,
            linewidth=lw,
            linestyle=linestyle,
            marker=marker,
            markeredgecolor="black",
        )[0]
        text_artist = self.ax.text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            label,
            color=color,
            fontsize=8,
            fontweight="bold",
            bbox=dict(facecolor="white", alpha=0.78, edgecolor=color, pad=2),
        )
        self._editable_artists.append(
            {
                "points": points,
                "line_artist": line_artist,
                "text_artist": text_artist,
                "label": label,
            }
        )

    def _target_sondaj(self):
        target_no = self.target_var.get()
        for index, sondaj in enumerate(self.app.veri.get("sondaj", [])):
            display_no = sondaj.get("no") or f"SK-{index + 1}"
            if display_no == target_no:
                return sondaj
        return None

    def _target_index(self):
        target = self._target_sondaj()
        for index, sondaj in enumerate(self.app.veri.get("sondaj", [])):
            if sondaj is target:
                return index
        return None

    def _refresh_main_ui(self):
        self.app.sondaj_tablosunu_ciz()
        self.app.ozet_yenile(collect=False)

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
        if self._target_depth() is None:
            messagebox.showwarning(
                "Karot TCR",
                "Hedef sondajın toplam derinliği girilmeden aralık sınırı doğrulanamaz. "
                "Önce Sondaj sekmesinde derinliği girin.",
                parent=self.win,
            )
            return

        interval_report = self._interval_validation()
        if not interval_report["gecerli"]:
            details = "\n".join(
                f"- {item['mesaj']}" for item in interval_report["hatalar"][:6]
            )
            messagebox.showerror(
                "Karot TCR Kalite Kontrolü",
                "Derinlik aralıkları aktarım için uygun değil:\n\n" + details,
                parent=self.win,
            )
            return

        transfer_results = []
        errors = []
        warnings = []
        empty_intervals = []
        quality_pending = []
        for interval in self.intervals:
            interval = self._prepare_interval(interval)
            result = self._interval_result(interval)
            label = self._interval_label(interval)
            errors.extend(f"{label}: {text}" for text in result.get("hatalar", []))
            warnings.extend(f"{label}: {text}" for text in result.get("uyarilar", []))
            if not interval.get("segments"):
                empty_intervals.append(label)
            if result.get("kalite_bekliyor"):
                quality_pending.append(label)
            transfer_results.append(
                {
                    "top": interval["top"],
                    "bot": interval["bot"],
                    "tcr": result["tcr"],
                    "scr": result.get("scr"),
                    "rqd": result.get("rqd"),
                    "gecerli": result.get("gecerli", False),
                    "hatalar": result.get("hatalar", []),
                }
            )

        if errors:
            messagebox.showerror(
                "Karot TCR Kalite Kontrolü",
                "Aktarım durduruldu. Önce şu hataları düzeltin:\n\n"
                + "\n".join(f"- {text}" for text in errors[:8]),
                parent=self.win,
            )
            return

        confirmation_sections = []
        if warnings:
            confirmation_sections.append(
                "Kontrol edilmesi gereken ölçümler:\n"
                + "\n".join(f"- {text}" for text in warnings[:6])
            )
        if empty_intervals:
            confirmation_sections.append(
                "TCR parçası olmayan ve TCR %0 aktarılacak aralıklar:\n"
                + "\n".join(f"- {label}" for label in empty_intervals[:8])
            )
        if quality_pending:
            confirmation_sections.append(
                "SCR/RQD ölçülmeyen aralıklar; mevcut değerler korunacak, "
                "yeni satırlarda boş kalacak:\n"
                + "\n".join(f"- {label}" for label in quality_pending[:8])
            )
        if confirmation_sections and not messagebox.askyesno(
            "Karot TCR / SCR / RQD Kalite Kontrolü",
            "\n\n".join(confirmation_sections)
            + "\n\nKontrol ettim, yine de aktarılsın mı?",
            parent=self.win,
        ):
                return

        try:
            self.app.sondaj_verilerini_kaydet(silent=True)
        except Exception:
            pass
        sondaj = self._target_sondaj()
        target_index = self._target_index()
        if not sondaj or target_index is None:
            messagebox.showerror(
                "Karot TCR",
                "Aktarım öncesinde hedef sondaj kaydı yenilenemedi.",
                parent=self.win,
            )
            return
        if not self._save_session(show_message=False):
            return

        try:
            plan = karot_aktarim_plani_olustur(sondaj, transfer_results)
            karot_aktarim_plani_uygula(sondaj, plan)
            try:
                self._refresh_main_ui()
            except Exception:
                karot_aktarimini_geri_al(sondaj, plan)
                try:
                    self._refresh_main_ui()
                except Exception:
                    pass
                raise
        except Exception as exc:
            messagebox.showerror(
                "Karot TCR Aktarımı",
                f"Kaya tablosu değiştirilmedi:\n{exc}",
                parent=self.win,
            )
            return

        self.app._karot_son_aktarim = {
            "target_index": target_index,
            "target_no": sondaj.get("no") or f"SK-{target_index + 1}",
            "project_marker": id(self.app.veri),
            "plan": plan,
        }
        self.btn_undo_transfer.configure(state="normal")
        status = (
            f"{sondaj.get('no') or f'SK-{target_index + 1}'}: "
            f"{plan['toplam']} karot aralığı aktarıldı "
            f"({plan['eklenen']} yeni, {plan['guncellenen']} güncel; "
            f"{plan['kalite_guncellenen']} aralıkta SCR/RQD)."
        )
        self.app.set_status(status, level="success")
        messagebox.showinfo(
            "Karot TCR / SCR / RQD",
            status
            + (
                "\n\nÖlçülmeyen aralıklardaki mevcut SCR/RQD değerleri korundu."
                if quality_pending
                else ""
            ),
            parent=self.win,
        )

    def _undo_transfer(self):
        snapshot = getattr(self.app, "_karot_son_aktarim", None)
        if not isinstance(snapshot, dict):
            self.btn_undo_transfer.configure(state="disabled")
            messagebox.showinfo(
                "Karot TCR",
                "Geri alınacak bir karot aktarımı yok.",
                parent=self.win,
            )
            return
        if snapshot.get("project_marker") != id(self.app.veri):
            self.app._karot_son_aktarim = None
            self.btn_undo_transfer.configure(state="disabled")
            messagebox.showwarning(
                "Karot TCR",
                "Son aktarım başka bir proje oturumuna ait olduğu için geri alınamaz.",
                parent=self.win,
            )
            return
        sondajlar = self.app.veri.get("sondaj", [])
        index = snapshot.get("target_index")
        if not isinstance(index, int) or not (0 <= index < len(sondajlar)):
            messagebox.showerror(
                "Karot TCR",
                "Aktarımın hedef sondajı artık bulunamadığı için geri alınamadı.",
                parent=self.win,
            )
            return
        sondaj = sondajlar[index]
        try:
            karot_aktarimini_geri_al(sondaj, snapshot.get("plan"))
            try:
                self._refresh_main_ui()
            except Exception:
                karot_aktarim_plani_uygula(sondaj, snapshot.get("plan"))
                try:
                    self._refresh_main_ui()
                except Exception:
                    pass
                raise
        except Exception as exc:
            messagebox.showerror(
                "Karot TCR",
                f"Son aktarım geri alınamadı:\n{exc}",
                parent=self.win,
            )
            return
        self.app._karot_son_aktarim = None
        self.btn_undo_transfer.configure(state="disabled")
        target_no = snapshot.get("target_no") or sondaj.get("no") or f"SK-{index + 1}"
        self.app.set_status(
            f"{target_no}: son karot TCR/SCR/RQD aktarımı geri alındı.",
            level="warning",
        )
