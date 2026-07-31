# Dosya: RaporPro/ui_litoloji_manuel.py
"""LAB rehberli, kullanıcı kontrollü sondaj litoloji işaretleme ekranı."""

from __future__ import annotations

import copy
import colorsys
import datetime
import re
import textwrap
import tkinter as tk
import uuid
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from cizim import GeoEngineDraw
from ui_lab_sheet import lab_kaynak_satirlari
from litoloji_korelasyon import (
    RENK_SECENEKLERI,
    laboratuvar_litoloji_kayitlari,
    manuel_atama_cakisiyor,
    manuel_katmanlari_dogrula,
    manuel_lab_katmanlari_olustur,
    onerileri_litoloji_satirlarina_cevir,
    sinif_kodu_coz,
    sondaj_anahtari,
    sondaj_spt_kayitlari,
    zemin_davranis_sinifi,
)
from sabitler import LEJANTLAR
from yardimcilar import litoloji_cozumle


RENK_DOLGULARI = {
    "Kahve renkli": "#B08B68",
    "Kırmızımsı renkli": "#C98276",
    "Bej renkli": "#DCC9A3",
    "Grimsi renkli": "#B9BEC3",
}

def _sondaj_rehber_renkleri(index):
    """Her sondaj için tekrar etmeyen, okunabilir iki pastel ton üretir."""
    hue = (0.08 + int(index) * 0.61803398875) % 1.0

    def to_hex(saturation, value):
        rgb = colorsys.hsv_to_rgb(hue, saturation, value)
        return "#{:02X}{:02X}{:02X}".format(
            *(round(component * 255) for component in rgb)
        )

    return to_hex(0.13, 0.98), to_hex(0.32, 0.91)


class ManuelLitolojiPenceresi:
    def __init__(self, app):
        self.app = app
        self.app.sondaj_verilerini_kaydet(silent=True)
        self.win = tk.Toplevel(app.root)
        app.pencere_hazirla(
            self.win,
            "LAB Rehberli Litoloji İşaretleme",
            "1520x910",
            (1160, 720),
            modal=False,
        )
        self.win.protocol("WM_DELETE_WINDOW", self._close)

        self.layers_by_well = {}
        self.preview_states_by_well = {}
        self.lab_records = []
        self.lab_warnings = []
        self.lab_source_name = ""
        self.undo_stack = []
        self.current_well_index = None
        self.selected_lab_record = None
        self.selected_assignment_id = ""
        self.range_pick_mode = False
        self.range_pick_points = []
        self.patch_targets = []
        self.preview_patch_targets = []
        self.well_geometries = {}
        self.preview_tree_records = {}
        self.drag_state = None
        self.dirty = False

        self.sample_length_var = tk.StringVar(value="1.50")
        self.status_var = tk.StringVar(
            value="Tüm LAB birimleri önizlenir; düzenlemek için bir birime tıklayın."
        )
        self.selected_lab_var = tk.StringVar(value="LAB kaydı seçilmedi")
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.color_var = tk.StringVar(value=RENK_SECENEKLERI[0])
        self.preview_var = tk.StringVar(value="Atama önizlemesi bekleniyor")
        self.coverage_var = tk.StringVar(value="Kapsam bekleniyor")

        self._load_saved_state()
        self._build_ui()
        self._reload_lab_records()
        wells = self.app.veri.get("sondaj", []) or []
        if wells:
            self._activate_well(0, redraw=False)
            self._draw()
        else:
            self._draw()

    def _build_ui(self):
        root = ttk.Frame(self.win, padding=(10, 8))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        root.grid_propagate(False)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(1, weight=1)
        ttk.Label(
            header,
            text="LAB Rehberli Litoloji İşaretleme",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.status_var,
            foreground="#1F618D",
        ).grid(row=0, column=1, sticky="ew", padx=(18, 0))

        toolbar = ttk.Frame(root)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="Yedek LAB boyu (m)").pack(
            side="left"
        )
        sample_entry = ttk.Entry(
            toolbar, textvariable=self.sample_length_var, width=7
        )
        sample_entry.pack(side="left", padx=(5, 8))
        sample_entry.bind("<FocusOut>", lambda event: self._reload_lab_records())
        ttk.Button(
            toolbar,
            text="LAB Rehberini Yenile",
            command=self._reload_lab_records,
        ).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Geri Al", command=self._undo).pack(
            side="left", padx=3
        )
        ttk.Button(toolbar, text="Taslağı Kaydet", command=self._save_draft).pack(
            side="left", padx=3
        )
        ttk.Button(
            toolbar,
            text="Son Aktarımı Geri Al",
            command=self._restore_last_apply,
        ).pack(side="left", padx=3)
        ttk.Button(
            toolbar,
            text="Seçili Sondajı Temizle",
            command=self._clear_current_well,
        ).pack(side="left", padx=3)
        ttk.Button(
            toolbar,
            text="Onayla ve Litolojiye Aktar",
            command=self._apply,
        ).pack(side="right", padx=3)

        content = ttk.Frame(root)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=7, minsize=620)
        content.columnconfigure(1, weight=3, minsize=310)
        content.rowconfigure(0, weight=1)
        content.grid_propagate(False)

        center = ttk.Frame(content, padding=5)
        right = ttk.Frame(content, padding=6)
        center.grid(row=0, column=0, sticky="nsew")
        right.grid(row=0, column=1, sticky="nsew")

        self._build_center_panel(center)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        ttk.Label(
            parent, text="Sondajlar", font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.well_tree = ttk.Treeview(
            parent,
            columns=("kapsam", "durum"),
            show="tree headings",
            selectmode="browse",
            height=20,
        )
        self.well_tree.heading("#0", text="Sondaj")
        self.well_tree.heading("kapsam", text="%")
        self.well_tree.heading("durum", text="Durum")
        self.well_tree.column("#0", width=82, anchor="w")
        self.well_tree.column("kapsam", width=48, anchor="center")
        self.well_tree.column("durum", width=78, anchor="center")
        self.well_tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            parent, orient="vertical", command=self.well_tree.yview
        )
        scroll.grid(row=1, column=1, sticky="ns")
        self.well_tree.configure(yscrollcommand=scroll.set)
        self.well_tree.bind("<<TreeviewSelect>>", self._well_changed)

        actions = ttk.LabelFrame(parent, text="Sondaj işlemleri", padding=7)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(
            actions,
            text="Profilden Aralık Seç (2 tıklama)",
            command=self._start_range_pick,
        ).pack(fill="x", pady=2)
        ttk.Button(
            actions,
            text="Seçili Sondajı Temizle",
            command=self._clear_current_well,
        ).pack(fill="x", pady=2)
        ttk.Label(
            actions,
            textvariable=self.coverage_var,
            wraplength=220,
            foreground="#566573",
            justify="left",
        ).pack(fill="x", pady=(6, 0))

        help_box = ttk.LabelFrame(parent, text="İş akışı", padding=7)
        help_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(
            help_box,
            text=(
                "1. Sondajı seçin\n"
                "2. Kuyudan veya alttaki tablodan birime tıklayın\n"
                "3. Kuyu içindeki tavan/taban çizgilerini sürükleyin\n"
                "4. Rengi seçip Yeni Atama Ekle'ye basın\n"
                "5. Diğer birimler için tekrarlayıp onaylayın"
            ),
            justify="left",
        ).pack(anchor="w")

    def _build_center_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(2, weight=0)

        figure_frame = ttk.Frame(parent)
        figure_frame.grid(row=0, column=0, sticky="nsew")
        self.figure = Figure(figsize=(6.4, 6.2), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=figure_frame)
        navigation = NavigationToolbar2Tk(
            self.canvas, figure_frame, pack_toolbar=False
        )
        navigation.update()
        navigation.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.canvas.figure.canvas.mpl_connect(
            "button_press_event", self._on_canvas_click
        )
        self.canvas.figure.canvas.mpl_connect(
            "motion_notify_event", self._on_canvas_motion
        )
        self.canvas.figure.canvas.mpl_connect(
            "button_release_event", self._on_canvas_release
        )

        ttk.Label(
            parent,
            text="Litolojiye kaydedilecek / kaydedilmiş satırlar",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(6, 3))
        layer_frame = ttk.Frame(parent)
        layer_frame.grid(row=2, column=0, sticky="ew")
        layer_frame.columnconfigure(0, weight=1)
        self.layer_tree = ttk.Treeview(
            layer_frame,
            columns=("durum", "aralik", "renk", "sinif", "tanim"),
            show="headings",
            selectmode="browse",
            height=4,
        )
        for key, label, width, anchor in (
            ("durum", "Durum", 100, "center"),
            ("aralik", "Aralık", 90, "center"),
            ("renk", "Renk", 95, "w"),
            ("sinif", "LAB Sınıfı", 75, "center"),
            ("tanim", "Litolojiye geçecek tanım", 330, "w"),
        ):
            self.layer_tree.heading(key, text=label)
            self.layer_tree.column(key, width=width, anchor=anchor)
        self.layer_tree.grid(row=0, column=0, sticky="ew")
        self.layer_tree.bind("<<TreeviewSelect>>", self._layer_selected)
        layer_scroll = ttk.Scrollbar(
            layer_frame, orient="vertical", command=self.layer_tree.yview
        )
        layer_scroll.grid(row=0, column=1, sticky="ns")
        self.layer_tree.configure(yscrollcommand=layer_scroll.set)
        layer_buttons = ttk.Frame(layer_frame)
        layer_buttons.grid(row=1, column=0, sticky="e", pady=(4, 0))
        ttk.Button(
            layer_buttons,
            text="Seçili Atamayı Sil",
            command=self._delete_selected_assignment,
        ).pack(side="right", padx=3)

    def _build_right_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0)

        ttk.Label(
            parent,
            text="LAB Birim Rehberi · Tüm Sondajlar",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        lab_frame = ttk.Frame(parent)
        lab_frame.grid(row=1, column=0, sticky="nsew")
        lab_frame.columnconfigure(0, weight=1)
        lab_frame.rowconfigure(0, weight=1)
        self.lab_tree = ttk.Treeview(
            lab_frame,
            columns=("sondaj", "derinlik", "sinif"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        for key, label, width, anchor in (
            ("sondaj", "SK Numarası", 95, "center"),
            ("derinlik", "Derinlik", 90, "center"),
            ("sinif", "Zemin Sınıfı", 125, "center"),
        ):
            self.lab_tree.heading(key, text=label)
            self.lab_tree.column(key, width=width, anchor=anchor)
        self.lab_tree.grid(row=0, column=0, sticky="nsew")
        lab_scroll = ttk.Scrollbar(
            lab_frame, orient="vertical", command=self.lab_tree.yview
        )
        lab_scroll.grid(row=0, column=1, sticky="ns")
        self.lab_tree.configure(yscrollcommand=lab_scroll.set)
        self.lab_tree.bind("<<TreeviewSelect>>", self._lab_selected)
        self.lab_tree.bind("<Double-Button-1>", lambda event: self._start_range_pick())

        assignment = ttk.LabelFrame(
            parent, text="LAB birimini derinliğe ata", padding=8
        )
        assignment.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        assignment.columnconfigure(1, weight=1)
        ttk.Label(
            assignment,
            textvariable=self.selected_lab_var,
            foreground="#1F618D",
            wraplength=340,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(assignment, text="Başlangıç (m)").grid(
            row=1, column=0, sticky="w", pady=3
        )
        start_entry = ttk.Entry(assignment, textvariable=self.start_var)
        start_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(assignment, text="Bitiş (m)").grid(
            row=2, column=0, sticky="w", pady=3
        )
        end_entry = ttk.Entry(assignment, textvariable=self.end_var)
        end_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(assignment, text="Renk").grid(
            row=3, column=0, sticky="w", pady=3
        )
        color_box = ttk.Combobox(
            assignment,
            textvariable=self.color_var,
            values=RENK_SECENEKLERI,
            state="readonly",
        )
        color_box.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)
        button_row = ttk.Frame(assignment)
        button_row.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(7, 4)
        )
        button_row.columnconfigure((0, 1), weight=1)
        ttk.Button(
            button_row,
            text="Yeni Atama Ekle",
            command=lambda: self._save_assignment(update=False),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(
            button_row,
            text="Seçili Atamayı Güncelle",
            command=lambda: self._save_assignment(update=True),
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Label(
            assignment,
            textvariable=self.preview_var,
            wraplength=340,
            justify="left",
            foreground="#566573",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(3, 0))

        for widget in (start_entry, end_entry):
            widget.bind("<KeyRelease>", lambda event: self._form_changed())
            widget.bind("<FocusOut>", lambda event: self._form_changed())
        color_box.bind("<<ComboboxSelected>>", lambda event: self._form_changed())

    def _sample_length(self):
        try:
            return max(0.5, float(self.sample_length_var.get().replace(",", ".")))
        except Exception:
            return 1.5

    def _sync_preview_states(self):
        well_indexes = {
            sondaj_anahtari(well.get("no")): index
            for index, well in enumerate(self.app.veri.get("sondaj", []) or [])
        }
        records_by_index = {}
        for record in self.lab_records:
            well_index = well_indexes.get(record.get("sondaj_key"))
            if well_index is None:
                continue
            records_by_index.setdefault(well_index, []).append(record)
        for well_index, records in records_by_index.items():
            previous = self.preview_states_by_well.get(well_index, {})
            current = {}
            for record in records:
                row_index = record.get("row_index")
                saved = previous.get(row_index, {})
                current[row_index] = {
                    "top": saved.get("top", float(record.get("top", 0))),
                    "bottom": saved.get(
                        "bottom", float(record.get("bottom", 0))
                    ),
                    "renk": saved.get("renk", RENK_SECENEKLERI[0]),
                }
            self.preview_states_by_well[well_index] = current

    def _preview_state_for_record(self, record, well_index=None):
        target_index = (
            self.current_well_index if well_index is None else well_index
        )
        if target_index is None:
            return {
                "top": float(record.get("top", 0)),
                "bottom": float(record.get("bottom", 0)),
                "renk": RENK_SECENEKLERI[0],
            }
        states = self.preview_states_by_well.setdefault(
            target_index, {}
        )
        row_index = record.get("row_index")
        return states.setdefault(
            row_index,
            {
                "top": float(record.get("top", 0)),
                "bottom": float(record.get("bottom", 0)),
                "renk": RENK_SECENEKLERI[0],
            },
        )

    def _store_selected_preview_state(self):
        if (
            self.current_well_index is None
            or not self.selected_lab_record
            or self.selected_assignment_id
        ):
            return
        top, bottom = self._form_numbers()
        if top is None or bottom is None or bottom <= top:
            return
        state = self._preview_state_for_record(self.selected_lab_record)
        state.update(
            {
                "top": top,
                "bottom": bottom,
                "renk": self.color_var.get(),
            }
        )

    def _load_saved_state(self):
        source = self.app.veri.get("litoloji_manuel_taslak", {}) or {}
        saved = source.get("sondajlar", {}) if isinstance(source, dict) else {}
        for index, well in enumerate(self.app.veri.get("sondaj", []) or []):
            key = sondaj_anahtari(well.get("no"))
            layers = saved.get(key)
            if not isinstance(layers, list):
                layers = well.get("litoloji_manuel_katmanlari", [])
            self.layers_by_well[index] = copy.deepcopy(
                layers if isinstance(layers, list) else []
            )

    def _reload_lab_records(self):
        selected_row = (
            self.selected_lab_record.get("row_index")
            if self.selected_lab_record
            else None
        )
        try:
            lab_rows, source_name = lab_kaynak_satirlari(
                self.app.veri,
                getattr(self.app, "lab_excel_path", None),
            )
        except Exception as exc:
            self.lab_records = []
            self.lab_warnings = [f"LAB kaynağı okunamadı: {exc}"]
            self.lab_source_name = ""
            self.selected_lab_record = None
            self._refresh_lab_tree()
            self._refresh_well_tree()
            self.status_var.set(self.lab_warnings[0])
            return
        self.lab_source_name = source_name
        result = laboratuvar_litoloji_kayitlari(
            lab_rows,
            sondajlar=self.app.veri.get("sondaj", []),
            varsayilan_numune_boyu=self._sample_length(),
        )
        self.lab_records = result.get("records", [])
        self.lab_warnings = result.get("warnings", [])
        self._sync_preview_states()
        if selected_row is not None:
            current_key = sondaj_anahtari(self._current_well().get("no"))
            self.selected_lab_record = next(
                (
                    record
                    for record in self.lab_records
                    if record.get("row_index") == selected_row
                    and record.get("sondaj_key") == current_key
                ),
                None,
            )
        self._refresh_lab_tree()
        self._refresh_well_tree()
        if not self.lab_source_name:
            self.status_var.set(
                "LAB Sheet boş ve bağlı bir LAB Excel dosyası bulunamadı."
            )
        elif self.lab_warnings:
            self.status_var.set(
                f"{self.lab_source_name}: {len(self.lab_records)} kayıt · "
                f"{len(self.lab_warnings)} kayıt kontrol bekliyor."
            )
        else:
            self.status_var.set(
                f"{self.lab_source_name}: {len(self.lab_records)} LAB kaydı hazır."
            )

    def _refresh_well_tree(self):
        if not hasattr(self, "well_tree"):
            return
        selected = self.current_well_index
        for item in self.well_tree.get_children():
            self.well_tree.delete(item)
        for index, well in enumerate(self.app.veri.get("sondaj", []) or []):
            validation = manuel_katmanlari_dogrula(
                self.layers_by_well.get(index, []),
                well.get("der"),
            )
            depth = validation["depth"]
            coverage = validation["covered"]
            ratio = int(round((coverage / depth) * 100)) if depth > 0 else 0
            status = "Hazır" if validation["valid"] else "Eksik"
            self.well_tree.insert(
                "",
                "end",
                iid=str(index),
                text=well.get("no") or f"SK-{index + 1}",
                values=(ratio, status),
            )
        if selected is not None and self.well_tree.exists(str(selected)):
            self.well_tree.selection_set(str(selected))

    def _well_changed(self, event=None):
        selected = self.well_tree.selection()
        if not selected:
            return
        try:
            new_index = int(selected[0])
        except (TypeError, ValueError):
            return
        self._activate_well(new_index)

    def _activate_well(self, new_index, redraw=True):
        wells = self.app.veri.get("sondaj", []) or []
        try:
            new_index = int(new_index)
        except (TypeError, ValueError):
            return False
        if not (0 <= new_index < len(wells)):
            return False
        unchanged = new_index == self.current_well_index
        if (
            unchanged
            and self.selected_lab_record
            and self.selected_lab_record.get("sondaj_key")
            == sondaj_anahtari(self._current_well().get("no"))
        ):
            return False
        self.current_well_index = new_index
        self.selected_lab_record = None
        self.selected_assignment_id = ""
        self.range_pick_mode = False
        self.range_pick_points = []
        self.drag_state = None
        self.selected_lab_var.set("LAB kaydı seçilmedi")
        self.start_var.set("")
        self.end_var.set("")
        self._refresh_lab_tree()
        self._refresh_layer_tree()
        self._refresh_coverage_text()
        self._refresh_preview()
        if redraw:
            self._draw()
        return not unchanged

    def _well_at(self, well_index):
        wells = self.app.veri.get("sondaj", []) or []
        if well_index is None:
            return {}
        if 0 <= int(well_index) < len(wells):
            return wells[int(well_index)]
        return {}

    def _current_well(self):
        return self._well_at(self.current_well_index)

    def _layers_for_well(self, well_index):
        if well_index is None:
            return []
        return self.layers_by_well.setdefault(int(well_index), [])

    def _current_layers(self):
        return self._layers_for_well(self.current_well_index)

    def _records_for_well(self, well_index):
        key = sondaj_anahtari(self._well_at(well_index).get("no"))
        if not key:
            return []
        return [
            record
            for record in self.lab_records
            if record.get("sondaj_key") == key
        ]

    def _records_for_current_well(self):
        return self._records_for_well(self.current_well_index)

    def _record_usage_count(self, record, well_index=None):
        target_index = (
            self.current_well_index if well_index is None else well_index
        )
        row_index = record.get("row_index")
        assignment_ids = {
            layer.get("atama_id")
            for layer in self._layers_for_well(target_index)
            if layer.get("lab_row_index") == row_index
        }
        return len({item for item in assignment_ids if item})

    @staticmethod
    def _lab_code_display(record):
        raw_code = str(record.get("sinif", "") or "").strip()
        corrected_code = str(
            (record.get("parsed", {}) or {}).get("duzeltilmis_kod", "") or ""
        ).strip()
        if corrected_code and corrected_code != raw_code:
            return f"{raw_code} \u2192 {corrected_code}"
        return raw_code

    @staticmethod
    def _lab_interval_display(record):
        try:
            return (
                f"{float(record.get('top', 0)):.2f}-"
                f"{float(record.get('bottom', 0)):.2f}"
            )
        except (TypeError, ValueError):
            return str(record.get("raw_depth", "") or "")

    @staticmethod
    def _lab_source_depth_display(record):
        raw_depth = str(record.get("raw_depth", "") or "").strip()
        if not raw_depth:
            return ""
        try:
            return f"{float(raw_depth.replace(',', '.')):.2f}"
        except (TypeError, ValueError):
            return raw_depth

    @staticmethod
    def _sondaj_sort_key(value):
        parts = re.split(r"(\d+)", str(value or "").casefold())
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in parts
            if part != ""
        )

    def _all_lab_records_sorted(self):
        return sorted(
            self.lab_records,
            key=lambda record: (
                self._sondaj_sort_key(record.get("sondaj", "")),
                float(record.get("top", 0)),
                int(record.get("row_index", 0)),
            ),
        )

    def _refresh_lab_tree(self):
        if not hasattr(self, "lab_tree"):
            return
        selected_row = (
            self.selected_lab_record.get("row_index")
            if self.selected_lab_record
            else None
        )
        for item in self.lab_tree.get_children():
            self.lab_tree.delete(item)
        records = self._all_lab_records_sorted()
        well_keys = []
        for record in records:
            key = record.get("sondaj_key") or sondaj_anahtari(
                record.get("sondaj")
            )
            if key not in well_keys:
                well_keys.append(key)
        color_indexes = {key: index for index, key in enumerate(well_keys)}
        current_key = sondaj_anahtari(self._current_well().get("no"))

        for record in records:
            well_key = record.get("sondaj_key") or sondaj_anahtari(
                record.get("sondaj")
            )
            color_index = color_indexes.get(well_key, 0)
            base_color, active_color = _sondaj_rehber_renkleri(color_index)
            is_active = bool(current_key and well_key == current_key)
            tag = f"well-{'active-' if is_active else ''}{color_index}"
            self.lab_tree.tag_configure(
                tag,
                background=active_color if is_active else base_color,
                foreground="#17202A",
                font=(
                    ("Segoe UI", 9, "bold")
                    if is_active
                    else ("Segoe UI", 9)
                ),
            )
            iid = f"lab-{record.get('row_index')}"
            self.lab_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    (
                        f"▨ {record.get('sondaj', '')}"
                        if is_active
                        else record.get("sondaj", "")
                    ),
                    self._lab_source_depth_display(record),
                    self._lab_code_display(record),
                ),
                tags=(tag,),
            )
        target = f"lab-{selected_row}" if selected_row is not None else ""
        if target and self.lab_tree.exists(target):
            self.lab_tree.selection_set(target)

    def _lab_selected(self, event=None):
        selected = self.lab_tree.selection()
        if not selected:
            return
        try:
            row_index = int(str(selected[0]).split("-", 1)[1])
        except (ValueError, IndexError):
            return
        record = next(
            (
                record
                for record in self.lab_records
                if record.get("row_index") == row_index
            ),
            None,
        )
        if not record:
            return
        target_well_index = next(
            (
                index
                for index, well in enumerate(
                    self.app.veri.get("sondaj", []) or []
                )
                if sondaj_anahtari(well.get("no"))
                == record.get("sondaj_key")
            ),
            None,
        )
        well_changed = (
            target_well_index is not None
            and target_well_index != self.current_well_index
        )
        if well_changed:
            self._activate_well(target_well_index, redraw=False)
        self.selected_lab_record = record
        if self.selected_assignment_id:
            selected_group = [
                layer
                for layer in self._current_layers()
                if layer.get("atama_id") == self.selected_assignment_id
            ]
            selected_row = (
                selected_group[0].get("lab_row_index")
                if selected_group
                else None
            )
            if selected_row != row_index:
                self.selected_assignment_id = ""
        parsed = record.get("parsed", {})
        self.selected_lab_var.set(
            f"LAB: {self._lab_interval_display(record)} m · "
            f"{self._lab_code_display(record)} · "
            f"{parsed.get('birim_adi') or 'Tanınmayan sınıf'}"
        )
        if not self.selected_assignment_id:
            state = self._preview_state_for_record(record)
            self.start_var.set(f"{float(state.get('top', 0)):.2f}")
            self.end_var.set(f"{float(state.get('bottom', 0)):.2f}")
            self.color_var.set(state.get("renk") or RENK_SECENEKLERI[0])
        if well_changed:
            self._refresh_well_tree()
            self._refresh_lab_tree()
            self._refresh_coverage_text()
        self._form_changed()
        self._draw()

    def _record_preview_layers(
        self,
        record,
        top,
        bottom,
        color,
        assignment_id="preview",
        well_index=None,
    ):
        if not record or top is None or bottom is None or bottom <= top:
            return []
        target_index = (
            self.current_well_index if well_index is None else well_index
        )
        try:
            return manuel_lab_katmanlari_olustur(
                self._well_at(target_index),
                record,
                top,
                bottom,
                color,
                atama_id=assignment_id,
            )
        except Exception:
            return []

    def _form_preview_layers(self, assignment_id="preview"):
        if not self.selected_lab_record:
            return []
        top, bottom = self._form_numbers()
        return self._record_preview_layers(
            self.selected_lab_record,
            top,
            bottom,
            self.color_var.get(),
            assignment_id=assignment_id,
        )

    def _all_unsaved_preview_groups(self, well_index=None):
        target_index = (
            self.current_well_index if well_index is None else well_index
        )
        groups = []
        for record in self._records_for_well(target_index):
            if self._record_usage_count(record, target_index):
                continue
            state = self._preview_state_for_record(record, target_index)
            layers = self._record_preview_layers(
                record,
                float(state.get("top", record.get("top", 0))),
                float(state.get("bottom", record.get("bottom", 0))),
                state.get("renk") or RENK_SECENEKLERI[0],
                assignment_id=f"preview-{record.get('row_index')}",
                well_index=target_index,
            )
            if layers:
                groups.append((record, layers))
        return groups

    def _selected_form_matches_saved(self):
        if not self.selected_assignment_id or not self.selected_lab_record:
            return False
        group = [
            layer
            for layer in self._current_layers()
            if layer.get("atama_id") == self.selected_assignment_id
        ]
        if not group:
            return False
        top, bottom = self._form_numbers()
        if top is None or bottom is None:
            return False
        saved_top, saved_bottom = self._group_bounds(group)
        return (
            abs(top - saved_top) <= 1e-6
            and abs(bottom - saved_bottom) <= 1e-6
            and self.color_var.get() == group[0].get("renk", "")
            and self.selected_lab_record.get("row_index")
            == group[0].get("lab_row_index")
        )

    def _refresh_layer_tree(self):
        if not hasattr(self, "layer_tree"):
            return
        for item in self.layer_tree.get_children():
            self.layer_tree.delete(item)
        self.preview_tree_records = {}

        selected_preview_layers = (
            self._form_preview_layers(self.selected_assignment_id)
            if self.selected_assignment_id
            else []
        )
        saved_layers = sorted(
            self._current_layers(), key=lambda item: float(item.get("top", 0))
        )
        entries = []
        for index, layer in enumerate(saved_layers):
            if (
                selected_preview_layers
                and self.selected_assignment_id
                and layer.get("atama_id") == self.selected_assignment_id
            ):
                continue
            entries.append(
                {
                    "iid": f"layer-{index}",
                    "layer": layer,
                    "status": "Kaydedildi",
                    "tags": (),
                }
            )
        for index, layer in enumerate(selected_preview_layers):
            entries.append(
                {
                    "iid": f"editing-{index}",
                    "layer": layer,
                    "status": (
                        "Kaydedildi (seçili)"
                        if self._selected_form_matches_saved()
                        else "Canlı düzenleme"
                    ),
                    "tags": ("preview",),
                }
            )
        for record, layers in self._all_unsaved_preview_groups():
            row_index = record.get("row_index")
            for index, layer in enumerate(layers):
                iid = f"preview-{row_index}-{index}"
                self.preview_tree_records[iid] = row_index
                entries.append(
                    {
                        "iid": iid,
                        "layer": layer,
                        "status": "Canlı önizleme",
                        "tags": ("preview",),
                    }
                )

        entries.sort(
            key=lambda item: (
                float(item["layer"].get("top", 0)),
                float(item["layer"].get("bottom", 0)),
                item["status"],
            )
        )
        for entry in entries:
            layer = entry["layer"]
            self.layer_tree.insert(
                "",
                "end",
                iid=entry["iid"],
                values=(
                    entry["status"],
                    f"{float(layer.get('top', 0)):.2f}-"
                    f"{float(layer.get('bottom', 0)):.2f}",
                    layer.get("renk", ""),
                    layer.get("sinif", ""),
                    layer.get("tanim", ""),
                ),
                tags=entry["tags"],
            )
        self.layer_tree.tag_configure(
            "preview", background="#EAF2F8", foreground="#154360"
        )

    def _select_lab_row(self, row_index):
        iid = f"lab-{row_index}"
        if not hasattr(self, "lab_tree") or not self.lab_tree.exists(iid):
            return
        self.lab_tree.selection_set(iid)
        self.lab_tree.see(iid)
        self._lab_selected()

    def _layer_selected(self, event=None):
        selected = self.layer_tree.selection()
        if not selected:
            return
        preview_row = self.preview_tree_records.get(str(selected[0]))
        if preview_row is not None:
            self._select_lab_row(preview_row)
            return
        if not str(selected[0]).startswith("layer-"):
            return
        try:
            sorted_index = int(str(selected[0]).split("-", 1)[1])
        except (ValueError, IndexError):
            return
        layers = sorted(
            self._current_layers(), key=lambda item: float(item.get("top", 0))
        )
        if not (0 <= sorted_index < len(layers)):
            return
        assignment_id = layers[sorted_index].get("atama_id", "")
        self._select_assignment(assignment_id)

    def _select_assignment(self, assignment_id):
        assignment_id = str(assignment_id or "")
        if not assignment_id:
            return
        group = [
            layer
            for layer in self._current_layers()
            if layer.get("atama_id") == assignment_id
        ]
        if not group:
            return
        self.selected_assignment_id = assignment_id
        self.start_var.set(f"{min(float(item['top']) for item in group):.2f}")
        self.end_var.set(f"{max(float(item['bottom']) for item in group):.2f}")
        self.color_var.set(group[0].get("renk") or RENK_SECENEKLERI[0])
        row_index = group[0].get("lab_row_index")
        self.selected_lab_record = next(
            (
                record
                for record in self._records_for_current_well()
                if record.get("row_index") == row_index
            ),
            None,
        )
        if self.selected_lab_record:
            iid = f"lab-{row_index}"
            if self.lab_tree.exists(iid):
                self.lab_tree.selection_set(iid)
                self.lab_tree.see(iid)
            parsed = self.selected_lab_record.get("parsed", {})
            self.selected_lab_var.set(
                f"LAB: {self._lab_interval_display(self.selected_lab_record)} m · "
                f"{self._lab_code_display(self.selected_lab_record)} · "
                f"{parsed.get('birim_adi', '')}"
            )
        self._form_changed()
        self._draw()

    def _start_range_pick(self):
        if self.current_well_index is None:
            return
        if not self.selected_lab_record:
            messagebox.showwarning(
                "Derinlik İşaretleme",
                "Önce Laboratuvar Rehberi'nden bir zemin sınıfı seçin.",
                parent=self.win,
            )
            return
        self.range_pick_mode = True
        self.range_pick_points = []
        self.status_var.set(
            "Profil üzerinde başlangıç ve bitiş derinliğine sırayla tıklayın."
        )
        self._draw()

    @staticmethod
    def _snap_depth(value):
        return max(0.0, round(float(value) * 2) / 2)

    def _snap_canvas_depth(self, value, well_index=None):
        total_depth = self._well_depth(well_index)
        if total_depth <= 0:
            return 0.0
        if float(value) >= total_depth - 0.25:
            return total_depth
        return min(self._snap_depth(value), total_depth)

    def _assignment_groups(self):
        groups = {}
        for layer in self._current_layers():
            assignment_id = str(layer.get("atama_id", "") or "")
            if assignment_id:
                groups.setdefault(assignment_id, []).append(layer)
        return groups

    @staticmethod
    def _group_bounds(group):
        if not group:
            return None, None
        return (
            min(float(item.get("top", 0)) for item in group),
            max(float(item.get("bottom", 0)) for item in group),
        )

    def _well_index_at_x(self, x_value):
        if x_value is None:
            return None
        for well_index, geometry in self.well_geometries.items():
            x0 = geometry["x0"]
            width = geometry["width"]
            if x0 - 0.18 <= float(x_value) <= x0 + width + 0.08:
                return well_index
        return None

    def _boundary_hit(self, event):
        if event.inaxes != self.axes or event.ydata is None or event.x is None:
            return None
        geometry = self.well_geometries.get(self.current_well_index)
        if not geometry or event.xdata is None:
            return None
        x0 = geometry["x0"]
        width = geometry["width"]
        if not (x0 - 0.12 <= event.xdata <= x0 + width + 0.12):
            return None

        candidates = []
        groups = self._assignment_groups()
        ordered_ids = sorted(
            groups,
            key=lambda item: 0 if item == self.selected_assignment_id else 1,
        )
        for assignment_id in ordered_ids:
            top, bottom = self._group_bounds(groups[assignment_id])
            candidates.extend(
                (
                    (assignment_id, "top", top, bottom),
                    (assignment_id, "bottom", top, bottom),
                )
            )

        if self.selected_lab_record and not self.selected_assignment_id:
            top, bottom = self._form_numbers()
            if top is not None and bottom is not None and bottom > top:
                candidates[0:0] = [
                    ("", "top", top, bottom),
                    ("", "bottom", top, bottom),
                ]

        for assignment_id, edge, top, bottom in candidates:
            boundary = top if edge == "top" else bottom
            boundary_y = self.axes.transData.transform(
                (x0 + width / 2, boundary)
            )[1]
            if abs(boundary_y - event.y) <= 9:
                return {
                    "well_index": self.current_well_index,
                    "assignment_id": assignment_id,
                    "edge": edge,
                    "top": top,
                    "bottom": bottom,
                }
        return None

    def _start_boundary_drag(self, event):
        if getattr(event, "button", None) != 1:
            return False
        target = self._boundary_hit(event)
        if not target:
            return False
        assignment_id = target["assignment_id"]
        if assignment_id and assignment_id != self.selected_assignment_id:
            self._select_assignment(assignment_id)
            top, bottom = self._form_numbers()
            target["top"], target["bottom"] = top, bottom
        if not self.selected_lab_record:
            return False
        target["moved"] = False
        self.drag_state = target
        edge_name = "tavan" if target["edge"] == "top" else "taban"
        self.status_var.set(
            f"{edge_name.capitalize()} sınırını 0,50 m kademelerle sürükleyin."
        )
        self._draw()
        return True

    def _on_canvas_click(self, event):
        if (
            event.inaxes != self.axes
            or event.ydata is None
            or event.xdata is None
        ):
            return
        clicked_well_index = self._well_index_at_x(event.xdata)
        if clicked_well_index is None:
            return
        well_changed = clicked_well_index != self.current_well_index
        if well_changed:
            self._activate_well(clicked_well_index, redraw=False)
        if self.range_pick_mode:
            depth = self._snap_canvas_depth(event.ydata, clicked_well_index)
            self.range_pick_points.append(depth)
            if len(self.range_pick_points) == 1:
                self.start_var.set(f"{depth:.2f}")
                self.status_var.set("Şimdi bitiş derinliğine tıklayın.")
            else:
                first, second = self.range_pick_points[:2]
                top, bottom = sorted((first, second))
                if bottom <= top:
                    self.range_pick_points = [first]
                    self.status_var.set(
                        "Bitiş başlangıçtan farklı olmalı; tekrar tıklayın."
                    )
                    self._draw()
                    return
                self.start_var.set(f"{top:.2f}")
                self.end_var.set(f"{bottom:.2f}")
                self.range_pick_mode = False
                self.range_pick_points = []
                self.status_var.set(
                    "Aralık seçildi; rengi kontrol edip atamayı ekleyin."
                )
                self._form_changed()
            self._draw()
            return
        if self._start_boundary_drag(event):
            return
        for patch in reversed(self.patch_targets):
            try:
                if patch.contains(event)[0]:
                    self._activate_well(patch._well_index, redraw=False)
                    self._select_assignment(patch._assignment_id)
                    return
            except Exception:
                pass
        for patch in reversed(self.preview_patch_targets):
            try:
                if patch.contains(event)[0]:
                    self._activate_well(patch._well_index, redraw=False)
                    self._select_lab_row(patch._lab_row_index)
                    return
            except Exception:
                pass
        if well_changed:
            self._draw()

    def _on_canvas_motion(self, event):
        if not self.drag_state or event.inaxes != self.axes or event.ydata is None:
            return
        top, bottom = self._form_numbers()
        if top is None or bottom is None:
            return
        depth = self._snap_canvas_depth(
            event.ydata, self.drag_state.get("well_index")
        )
        if self.drag_state["edge"] == "top":
            depth = min(depth, bottom - 0.5)
            if depth < 0:
                return
            self.start_var.set(f"{depth:.2f}")
        else:
            depth = max(depth, top + 0.5)
            depth = min(depth, self._well_depth())
            if depth <= top:
                return
            self.end_var.set(f"{depth:.2f}")
        self.drag_state["moved"] = True
        self._store_selected_preview_state()
        self._refresh_preview()
        self._refresh_layer_tree()
        self._draw()

    def _on_canvas_release(self, event):
        if not self.drag_state:
            return
        state = self.drag_state
        self.drag_state = None
        if not state.get("moved"):
            self._draw()
            return
        assignment_id = state.get("assignment_id", "")
        if assignment_id:
            if not self._save_assignment(update=True):
                self._select_assignment(assignment_id)
            return
        self.status_var.set(
            "Sınır değiştirildi; rengi kontrol edip Yeni Atama Ekle'ye basın."
        )
        self._refresh_preview()
        self._draw()

    def _well_depth(self, well_index=None):
        target_index = (
            self.current_well_index if well_index is None else well_index
        )
        try:
            return max(
                0.0,
                float(
                    str(self._well_at(target_index).get("der", 0)).replace(
                        ",", "."
                    )
                ),
            )
        except Exception:
            return 0.0

    def _form_numbers(self):
        try:
            raw_top = float(self.start_var.get().replace(",", "."))
            raw_bottom = float(self.end_var.get().replace(",", "."))
            total_depth = self._well_depth()
            top = self._snap_depth(raw_top)
            bottom = (
                total_depth
                if total_depth > 0 and abs(raw_bottom - total_depth) <= 1e-6
                else self._snap_depth(raw_bottom)
            )
            return top, bottom
        except Exception:
            return None, None

    def _form_changed(self):
        self._store_selected_preview_state()
        self._refresh_preview()
        self._refresh_layer_tree()
        if hasattr(self, "canvas"):
            self._draw()

    def _refresh_preview(self):
        if not self.selected_lab_record:
            self.preview_var.set("LAB rehberinden bir zemin sınıfı seçin.")
            return
        top, bottom = self._form_numbers()
        if top is None or bottom is None or bottom <= top:
            self.preview_var.set("Geçerli başlangıç ve bitiş derinliği girin.")
            return
        try:
            layers = manuel_lab_katmanlari_olustur(
                self._current_well(),
                self.selected_lab_record,
                top,
                bottom,
                self.color_var.get(),
                atama_id="preview",
            )
        except Exception as exc:
            self.preview_var.set(str(exc))
            return
        descriptions = list(dict.fromkeys(layer.get("tanim", "") for layer in layers))
        suffix = (
            f" · SPT geçişi nedeniyle {len(layers)} alt katman oluşacak."
            if len(layers) > 1
            else ""
        )
        self.preview_var.set(" / ".join(descriptions) + suffix)

    def _push_undo(self):
        self.undo_stack.append(copy.deepcopy(self.layers_by_well))
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)

    def _save_assignment(self, update=False):
        if self.current_well_index is None or not self.selected_lab_record:
            messagebox.showwarning(
                "LAB Ataması",
                "Sondaj ve LAB kaydı seçilmelidir.",
                parent=self.win,
            )
            return False
        top, bottom = self._form_numbers()
        if top is None or bottom is None or bottom <= top:
            messagebox.showwarning(
                "LAB Ataması",
                "Geçerli başlangıç ve bitiş derinlikleri girin.",
                parent=self.win,
            )
            return False
        ignored = self.selected_assignment_id if update else ""
        if update and not ignored:
            messagebox.showwarning(
                "LAB Ataması",
                "Güncellemek için önce listeden bir atama seçin.",
                parent=self.win,
            )
            return False
        if manuel_atama_cakisiyor(
            self._current_layers(), top, bottom, ignore_assignment_id=ignored
        ):
            messagebox.showwarning(
                "Katman Çakışması",
                "Bu derinlik aralığı mevcut bir atamayla çakışıyor. "
                "Önce mevcut sınırı düzenleyin veya atamayı silin.",
                parent=self.win,
            )
            return False
        assignment_id = ignored or uuid.uuid4().hex
        try:
            new_layers = manuel_lab_katmanlari_olustur(
                self._current_well(),
                self.selected_lab_record,
                top,
                bottom,
                self.color_var.get(),
                atama_id=assignment_id,
            )
        except Exception as exc:
            messagebox.showerror(
                "LAB Ataması", f"Atama oluşturulamadı:\n{exc}", parent=self.win
            )
            return False
        self._push_undo()
        retained = [
            layer
            for layer in self._current_layers()
            if layer.get("atama_id") != ignored
        ]
        retained.extend(new_layers)
        retained.sort(key=lambda item: float(item.get("top", 0)))
        self.layers_by_well[self.current_well_index] = retained
        self.selected_assignment_id = assignment_id
        self.dirty = True
        self.status_var.set(
            f"{self._current_well().get('no')}: {top:.2f}-{bottom:.2f} m "
            f"LAB birimi {'güncellendi' if update else 'eklendi'}."
        )
        self._refresh_all_current()
        return True

    def _delete_selected_assignment(self):
        if not self.selected_assignment_id:
            messagebox.showwarning(
                "Atamayı Sil",
                "Önce işaretlenmiş katman listesinden bir atama seçin.",
                parent=self.win,
            )
            return
        self._push_undo()
        assignment_id = self.selected_assignment_id
        self.layers_by_well[self.current_well_index] = [
            layer
            for layer in self._current_layers()
            if layer.get("atama_id") != assignment_id
        ]
        self.selected_assignment_id = ""
        self.dirty = True
        self.status_var.set("Seçili LAB ataması silindi.")
        self._refresh_all_current()

    def _clear_current_well(self):
        if self.current_well_index is None or not self._current_layers():
            return
        if not messagebox.askyesno(
            "Sondajı Temizle",
            f"{self._current_well().get('no')}: tüm manuel litoloji atamaları silinsin mi?",
            parent=self.win,
        ):
            return
        self._push_undo()
        self.layers_by_well[self.current_well_index] = []
        self.selected_assignment_id = ""
        self.dirty = True
        self._refresh_all_current()

    def _undo(self):
        if not self.undo_stack:
            self.status_var.set("Geri alınacak manuel işlem yok.")
            return
        self.layers_by_well = self.undo_stack.pop()
        self.selected_assignment_id = ""
        self.dirty = True
        self.status_var.set("Son manuel litoloji işlemi geri alındı.")
        self._refresh_all_current()

    def _refresh_all_current(self):
        self._refresh_well_tree()
        self._refresh_lab_tree()
        self._refresh_layer_tree()
        self._refresh_coverage_text()
        self._refresh_preview()
        self._draw()

    def _refresh_coverage_text(self):
        validation = manuel_katmanlari_dogrula(
            self._current_layers(), self._current_well().get("der")
        )
        if validation["valid"]:
            self.coverage_var.set(
                f"{validation['depth']:.2f} m'nin tamamı işaretlendi · Onaya hazır"
            )
        else:
            first = validation["issues"][0] if validation["issues"] else "Eksik"
            self.coverage_var.set(
                f"{validation['covered']:.2f}/{validation['depth']:.2f} m · {first}"
            )

    @staticmethod
    def _layer_pattern_style(layer):
        primary = str(layer.get("ana_birim", "") or "").casefold()
        code = {
            "cl": "kl",
            "si": "s",
            "sa": "k",
            "gr": "c",
            "rk": "kit",
        }.get(primary)
        if not code:
            code = litoloji_cozumle(
                layer.get("tanim")
                or layer.get("birim_adi")
                or layer.get("sinif")
            )
        return next(
            (style for style in LEJANTLAR if style.get("kod") == code),
            next(
                (
                    style
                    for style in LEJANTLAR
                    if style.get("kod") == "tanimsiz"
                ),
                {"kod": "tanimsiz", "desen": "", "sembol": "#566573"},
            ),
        )

    def _display_entries_for_well(self, well_index):
        well = self._well_at(well_index)
        current_layers = list(self._layers_for_well(well_index))
        display_entries = [(layer, False) for layer in current_layers]
        if (
            well_index == self.current_well_index
            and self.drag_state
            and self.drag_state.get("assignment_id")
        ):
            dragged_id = self.drag_state["assignment_id"]
            top, bottom = self._form_numbers()
            preview_layers = self._record_preview_layers(
                self.selected_lab_record,
                top,
                bottom,
                self.color_var.get(),
                assignment_id=dragged_id,
                well_index=well_index,
            )
            if preview_layers:
                display_entries = [
                    (layer, False)
                    for layer in current_layers
                    if layer.get("atama_id") != dragged_id
                ]
                display_entries.extend((layer, False) for layer in preview_layers)
        for _record, preview_layers in self._all_unsaved_preview_groups(
            well_index
        ):
            display_entries.extend((layer, True) for layer in preview_layers)
        return sorted(
            display_entries,
            key=lambda entry: (
                float(entry[0].get("top", 0)),
                1 if entry[1] else 0,
            ),
        )

    def _draw(self):
        ax = self.axes
        ax.clear()
        self.patch_targets = []
        self.preview_patch_targets = []
        self.well_geometries = {}
        wells = self.app.veri.get("sondaj", []) or []
        valid_wells = [
            (index, well, self._well_depth(index))
            for index, well in enumerate(wells)
            if self._well_depth(index) > 0
        ]
        if not valid_wells:
            ax.axis("off")
            ax.text(
                0.5,
                0.5,
                "Geçerli derinliği olan bir sondaj seçin",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            self.canvas.draw_idle()
            return

        well_count = len(valid_wells)
        width = 1.0
        gap = 0.72 if well_count <= 5 else 0.62
        max_depth = max(item[2] for item in valid_wells)
        text_width = 20 if well_count <= 4 else 16
        label_font = max(5.2, 7.4 - max(0, well_count - 3) * 0.28)

        form_top, form_bottom = self._form_numbers()
        for display_index, (well_index, well, depth) in enumerate(valid_wells):
            x0 = display_index * (width + gap)
            active = well_index == self.current_well_index
            self.well_geometries[well_index] = {
                "x0": x0,
                "width": width,
                "depth": depth,
            }
            background = Rectangle(
                (x0, 0),
                width,
                depth,
                facecolor="#FDEDEC",
                edgecolor="#2471A3" if active else "#17202A",
                linewidth=2.4 if active else 1.5,
                zorder=1,
            )
            ax.add_patch(background)

            scale_x = x0 - 0.08
            ax.plot(
                [scale_x, scale_x],
                [0, depth],
                color="#17202A",
                linewidth=0.9,
                zorder=12,
            )
            tick_depth = 0.0
            while tick_depth <= depth + 1e-9:
                is_major = abs(tick_depth - round(tick_depth)) <= 1e-8
                tick_length = 0.07 if is_major else 0.045
                ax.plot(
                    [scale_x - tick_length, scale_x],
                    [tick_depth, tick_depth],
                    color="#17202A",
                    linewidth=0.8,
                    zorder=12,
                )
                show_label = max_depth <= 15.0 or is_major
                if show_label:
                    ax.text(
                        scale_x - tick_length - 0.025,
                        tick_depth,
                        f"{tick_depth:g}",
                        ha="right",
                        va="center",
                        fontsize=5.7,
                        color="#17202A",
                        zorder=12,
                    )
                tick_depth = round(tick_depth + 0.5, 3)
            if abs(depth * 2 - round(depth * 2)) > 1e-8:
                ax.text(
                    scale_x - 0.095,
                    depth,
                    f"{depth:g}",
                    ha="right",
                    va="center",
                    fontsize=5.7,
                    color="#17202A",
                    zorder=12,
                )

            ax.text(
                x0 + width / 2,
                -0.34,
                str(well.get("no") or f"SK-{well_index + 1}"),
                ha="center",
                va="bottom",
                fontsize=9.2,
                fontweight="bold",
                color="#154360" if active else "#17202A",
                zorder=13,
            )

            for layer, is_preview in self._display_entries_for_well(well_index):
                top = max(0.0, float(layer.get("top", 0)))
                bottom = min(depth, float(layer.get("bottom", 0)))
                if bottom <= top:
                    continue
                selected = (
                    active
                    and not is_preview
                    and self.selected_assignment_id
                    and layer.get("atama_id") == self.selected_assignment_id
                )
                patch = Rectangle(
                    (x0, top),
                    width,
                    bottom - top,
                    facecolor=RENK_DOLGULARI.get(
                        layer.get("renk"), "#D5DBDB"
                    ),
                    edgecolor=(
                        "#154360"
                        if selected
                        else "#2471A3"
                        if is_preview
                        else "#17202A"
                    ),
                    linewidth=2.4 if selected else 1.5 if is_preview else 1.1,
                    linestyle="--" if is_preview else "-",
                    alpha=0.52 if is_preview else 0.78,
                    zorder=4,
                )
                patch._assignment_id = layer.get("atama_id", "")
                patch._lab_row_index = layer.get("lab_row_index")
                patch._well_index = well_index
                ax.add_patch(patch)
                if is_preview:
                    self.preview_patch_targets.append(patch)
                else:
                    self.patch_targets.append(patch)

                style = self._layer_pattern_style(layer)
                pattern_artists = GeoEngineDraw.draw_pattern(
                    ax,
                    patch,
                    style.get("desen", ""),
                    style.get("sembol", "#566573"),
                    bbox=(x0, x0 + width, top, bottom),
                    density_scale=5.0,
                )
                for artist in pattern_artists:
                    try:
                        artist.set_zorder(5.5)
                    except Exception:
                        pass

                height = bottom - top
                if height >= 0.35 and layer.get("tanim"):
                    label = "\n".join(
                        textwrap.wrap(
                            str(layer.get("tanim", "")),
                            width=text_width,
                            break_long_words=False,
                        )
                    )
                    label_artist = ax.text(
                        x0 + width / 2,
                        (top + bottom) / 2,
                        label,
                        ha="center",
                        va="center",
                        fontsize=max(
                            4.8,
                            min(label_font, 4.9 + height * 0.30),
                        ),
                        fontweight="bold",
                        color="#17202A",
                        zorder=9,
                        clip_on=True,
                        bbox={
                            "facecolor": "#FFFFFF",
                            "edgecolor": "none",
                            "alpha": 0.38,
                            "pad": 0.5,
                        },
                    )
                    label_artist.set_clip_path(patch)

            for record in sondaj_spt_kayitlari(well):
                n30 = (
                    "R"
                    if record.get("refused")
                    else f"{record.get('n30'):g}"
                    if record.get("n30") is not None
                    else "—"
                )
                ax.text(
                    x0 + width * 0.94,
                    float(record.get("depth", 0)),
                    n30,
                    ha="right",
                    va="center",
                    fontsize=6.3,
                    fontweight="bold",
                    color="#8A4B08",
                    zorder=11,
                    bbox={
                        "facecolor": "#FFFFFF",
                        "edgecolor": "none",
                        "alpha": 0.62,
                        "pad": 0.25,
                    },
                )

            if active and self.selected_lab_record:
                if (
                    form_top is not None
                    and form_bottom is not None
                    and form_bottom > form_top
                ):
                    for boundary in (form_top, form_bottom):
                        ax.plot(
                            [x0, x0 + width],
                            [boundary, boundary],
                            color="#154360",
                            linewidth=2.2,
                            zorder=14,
                        )
                        ax.plot(
                            [x0 + width / 2],
                            [boundary],
                            marker="s",
                            markersize=5.5,
                            markerfacecolor="#FDFEFE",
                            markeredgecolor="#154360",
                            zorder=15,
                        )
            if active and self.range_pick_mode and self.range_pick_points:
                ax.plot(
                    [x0, x0 + width],
                    [self.range_pick_points[0], self.range_pick_points[0]],
                    color="#C0392B",
                    linewidth=1.8,
                    zorder=14,
                )

        last_x = (well_count - 1) * (width + gap) + width
        ax.set_xlim(-0.42, last_x + 0.10)
        ax.set_ylim(max_depth + 0.18, -0.62)
        ax.set_axis_off()
        self.figure.subplots_adjust(
            left=0.025, right=0.99, bottom=0.015, top=0.985
        )
        self.canvas.draw_idle()

    def _behavior_for_depth(self, depth, spt_record):
        layer = next(
            (
                item
                for item in self._current_layers()
                if float(item.get("top", 0)) - 1e-6
                <= depth
                < float(item.get("bottom", 0))
            ),
            None,
        )
        parsed = (
            sinif_kodu_coz(layer.get("sinif", ""))
            if layer
            else (
                self.selected_lab_record.get("parsed", {})
                if self.selected_lab_record
                else {}
            )
        )
        return zemin_davranis_sinifi(
            parsed,
            spt_record.get("n30"),
            refused=bool(spt_record.get("refused")),
        )

    def _draft_payload(self):
        wells = self.app.veri.get("sondaj", []) or []
        return {
            "surum": 1,
            "guncelleme_tarihi": datetime.datetime.now().isoformat(
                timespec="seconds"
            ),
            "sondajlar": {
                sondaj_anahtari(well.get("no")): copy.deepcopy(
                    self.layers_by_well.get(index, [])
                )
                for index, well in enumerate(wells)
            },
        }

    def _save_draft(self, show_message=True):
        self.app.veri["litoloji_manuel_taslak"] = self._draft_payload()
        self.dirty = False
        if hasattr(self.app, "set_save_indicator"):
            self.app.set_save_indicator(
                "Manuel litoloji taslağı: kaydedilmedi", "warning"
            )
        self.status_var.set("Manuel litoloji taslağı proje verisine alındı.")
        if show_message:
            messagebox.showinfo(
                "Taslak Kaydedildi",
                "Manuel litoloji işaretlemeleri proje taslağına kaydedildi. "
                "Kalıcı olması için ana penceredeki Proje Kaydet işlemini kullanın.",
                parent=self.win,
            )

    def _validation_errors(self):
        errors = []
        for index, well in enumerate(self.app.veri.get("sondaj", []) or []):
            result = manuel_katmanlari_dogrula(
                self.layers_by_well.get(index, []), well.get("der")
            )
            if result["valid"]:
                continue
            name = well.get("no") or f"SK-{index + 1}"
            for issue in result["issues"]:
                errors.append(f"{name}: {issue}")
        return errors

    def _apply(self):
        errors = self._validation_errors()
        if errors:
            messagebox.showwarning(
                "Eksik Litoloji Kapsamı",
                "Aktarımdan önce tüm sondajlar 0,00 m'den kuyu sonuna kadar "
                "boşluksuz işaretlenmelidir:\n\n" + "\n".join(errors[:16]),
                parent=self.win,
            )
            return
        if not messagebox.askyesno(
            "Litolojiye Aktar",
            "Manuel LAB atamaları tüm sondajların litoloji tablolarına aktarılsın mı?\n\n"
            "Ham LAB ve SPT kayıtları değiştirilmeyecek; mevcut litoloji tablolarının "
            "geri alma kopyası saklanacaktır.",
            parent=self.win,
        ):
            return
        applied = 0
        for index, well in enumerate(self.app.veri.get("sondaj", []) or []):
            layers = sorted(
                copy.deepcopy(self.layers_by_well.get(index, [])),
                key=lambda item: float(item.get("top", 0)),
            )
            well["litoloji_korelasyon_onceki"] = {
                "tarih": datetime.datetime.now().isoformat(timespec="seconds"),
                "litoloji": copy.deepcopy(well.get("litoloji", [])),
                "kanit": copy.deepcopy(
                    well.get("litoloji_korelasyon_kaniti", [])
                ),
            }
            well["litoloji"] = onerileri_litoloji_satirlarina_cevir(layers)
            well["litoloji_manuel_katmanlari"] = copy.deepcopy(layers)
            well["litoloji_korelasyon_kaniti"] = [
                {
                    "top": layer.get("top"),
                    "bottom": layer.get("bottom"),
                    "sinif": layer.get("sinif", ""),
                    "renk": layer.get("renk", ""),
                    "durum": "kullanici_lab_atamasi",
                    "lab_row_index": layer.get("lab_row_index"),
                    "lab_derinlik": layer.get("lab_derinlik", ""),
                    "spt_degerleri": layer.get("spt_degerleri", []),
                    "segmentler": copy.deepcopy(
                        layer.get("kanit_segmentleri", [])
                    ),
                }
                for layer in layers
            ]
            applied += 1
        self.app.veri["litoloji_manuel_taslak"] = self._draft_payload()
        self.dirty = False
        try:
            self.app.sondaj_tablosunu_ciz()
            self.app.ozet_yenile(collect=False)
        except Exception:
            pass
        if hasattr(self.app, "set_save_indicator"):
            self.app.set_save_indicator(
                "Manuel litoloji: kaydedilmedi", "warning"
            )
        self.status_var.set(f"{applied} sondajın litolojisi güncellendi.")
        messagebox.showinfo(
            "Manuel Litoloji",
            f"{applied} sondajın litoloji tablosu güncellendi.\n\n"
            "LAB ve SPT tabloları korunmuştur. Log, idealize kesit ve rapor "
            "çıktıları bu onaylı litolojileri kullanacaktır.",
            parent=self.win,
        )

    def _restore_last_apply(self):
        wells = [
            well
            for well in self.app.veri.get("sondaj", []) or []
            if isinstance(well.get("litoloji_korelasyon_onceki"), dict)
        ]
        if not wells:
            self.status_var.set("Geri alınabilecek bir litoloji aktarımı yok.")
            return
        if not messagebox.askyesno(
            "Son Aktarımı Geri Al",
            f"{len(wells)} sondajın önceki litoloji tablosu geri yüklensin mi?",
            parent=self.win,
        ):
            return
        for well in wells:
            backup = well.pop("litoloji_korelasyon_onceki")
            well["litoloji"] = copy.deepcopy(backup.get("litoloji", []))
            if backup.get("kanit"):
                well["litoloji_korelasyon_kaniti"] = copy.deepcopy(
                    backup["kanit"]
                )
            else:
                well.pop("litoloji_korelasyon_kaniti", None)
        try:
            self.app.sondaj_tablosunu_ciz()
        except Exception:
            pass
        if hasattr(self.app, "set_save_indicator"):
            self.app.set_save_indicator(
                "Litoloji geri alındı: kaydedilmedi", "warning"
            )
        self.status_var.set("Son litoloji aktarımı geri alındı.")

    def _close(self):
        if self.dirty:
            decision = messagebox.askyesnocancel(
                "Manuel Litoloji Taslağı",
                "Kaydedilmemiş manuel işaretlemeler var.\n\n"
                "Kapatmadan önce taslağı proje verisine kaydetmek ister misiniz?",
                parent=self.win,
            )
            if decision is None:
                return
            if decision:
                self._save_draft(show_message=False)
        self.win.destroy()


__all__ = ["ManuelLitolojiPenceresi"]
