# Dosya: RaporPro/ui_jeoloji_kutuphanesi.py
"""2. JEOLOJİ kütüphanesi için ttk/Tk penceresi."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from jeoloji_kutuphanesi import (
    JeolojiKutuphane,
    eksik_kutuphane_geometrilerini_tamamla,
    jeoloji_adaylarini_tara,
    kayitlari_filtrele,
)
from jeoloji_geometri import (
    HARITA_MOD_SECILI,
    HARITA_MOD_TUMU,
    HARITA_MOD_YAKINDAKILER,
    YAKINDAKILER_DEFAULT_KM,
    eksik_geometrileri_tkgmden_tamamla,
    harita_fit_bounds,
    harita_gorunum_modeli,
    harita_kayitlarini_ayir,
    koordinat_poligon_uyari_metni,
    koordinat_poligon_uyusmazligi,
)
from tkgm_kml import tkgm_parsel_kml_olustur
from ui_jeoloji_adaylari import JeolojiAdayPenceresi
from proje_arsiv import proje_merkez_koordinati
from sabitler import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    FONT_UI_SECTION,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from harita_motoru import DEFAULT_TILE_SERVER, TILE_SERVERS


MAP_SELECTED_OUTLINE = "#087F5B"
MAP_SELECTED_FILL = "#DCEFE7"
MAP_OTHER_OUTLINE = "#96A6AE"
MAP_OTHER_FILL = "#F0F4F3"
MAP_FALLBACK = "#D97706"
MAP_MODE_LABELS = (
    (HARITA_MOD_SECILI, "Seçili"),
    (HARITA_MOD_YAKINDAKILER, "Yakındakiler"),
    (HARITA_MOD_TUMU, "Tümü"),
)


def kayit_konum_metni(record):
    values = [record.get("il", ""), record.get("ilce", ""), record.get("mahalle", "")]
    return " / ".join(str(value).strip() for value in values if str(value or "").strip()) or "Konum yok"


def kayit_ada_parsel_metni(record):
    ada = str(record.get("ada") or "-").strip()
    parsel = str(record.get("parsel") or "-").strip()
    return f"{ada} / {parsel}"


def kayit_koordinat_metni(record):
    lat, lon = record.get("lat"), record.get("lon")
    if lat is None or lon is None:
        return "-"
    return f"{float(lat):.6f}, {float(lon):.6f}"


def kayit_uyari_metni(record, limit=68):
    warnings = record.get("warnings") or record.get("quality_warnings") or []
    warning_values = [str(item).strip() for item in warnings if str(item).strip()]
    coordinate_warning = koordinat_poligon_uyari_metni(record)
    if coordinate_warning:
        warning_values.insert(0, coordinate_warning)
    text = " | ".join(warning_values)
    return text if len(text) <= limit else text[: max(1, limit - 3)].rstrip() + "..."


def kayit_geometri_metni(record):
    source = str((record or {}).get("geometry_source") or "").strip()
    status = str((record or {}).get("geometry_status") or "").strip()
    if not source:
        return "Sınır yok"
    source_label = "TKGM" if source == "tkgm" else "Yerel KML"
    return f"{source_label} · {status or 'hazır'}"


def proje_secili_jeoloji_kaydi(veri, store):
    """Proje seçimindeki id/hash ile kütüphane kaydını, UI kurulumundan önce çöz."""
    selection = (veri or {}).get("jeoloji_kutuphanesi") or {}
    source_id = selection.get("selected_source_id")
    source_hash = str(selection.get("selected_source_hash") or "").strip().lower()
    record = store.get(source_id) if source_id not in (None, "") else None
    if source_hash and (record is None or str(record.get("source_hash") or "").lower() != source_hash):
        record = store.get_by_hash(source_hash)
    return record


def duplicate_adayi_hazirla(candidate, existing):
    """Duplicate adayın yalnız eksik geometriyi yerinde güncellemesini görünür kıl."""
    if not isinstance(existing, dict):
        return candidate
    candidate["duplicate"] = True
    candidate["existing_id"] = existing.get("id")
    existing_geometry = existing.get("geometry_metadata") or {}
    existing_has_geometry = bool(existing_geometry.get("polygons"))
    candidate_has_geometry = isinstance(candidate.get("geometry"), dict)
    candidate["duplicate_geometry_update"] = bool(candidate_has_geometry and not existing_has_geometry)
    candidate["selected"] = bool(candidate["duplicate_geometry_update"])
    if not candidate_has_geometry and existing_has_geometry:
        candidate["geometry"] = dict(existing_geometry)
        candidate["geometry_hash"] = existing.get("geometry_hash", "")
        candidate["geometry_source"] = existing.get("geometry_source", "")
        candidate["geometry_status"] = existing.get("geometry_status", "selected")
        candidate["geometry_label"] = "Mevcut kütüphane sınırı"
    return candidate


class JeolojiKutuphanePenceresi:
    """Kayıt listesi, map marker'ları ve bölüm özeti aynı seçim modelini paylaşır."""

    def __init__(self, owner, on_changed=None):
        self.owner = owner
        self.on_changed = on_changed
        self.root = owner.root
        self.store = JeolojiKutuphane()
        self._all_records = []
        self.records = []
        self.record_map = {}
        selected_record = proje_secili_jeoloji_kaydi(owner.veri, self.store)
        self.selected_id = selected_record.get("id") if selected_record else None
        self.import_active = False
        self.geometry_active = False
        self._records_loading = False
        self._load_generation = 0
        self._task_handles = []
        self._candidate_window = None
        self._closing = False
        self._filter_after_id = None
        self._map_init_after_id = None
        self._map_after_id = None
        self._map_batch_after_id = None
        self._map_fit_requested = False
        self._map_ready = False
        self._map_initializing = False
        self._map_view_signature = None
        self._map_model = None
        self._map_geometry_cache = {}
        self._map_markers = []
        self._map_polygons = []
        self._map_paths = []
        self._map_geometry_drawings = {}
        self._map_project_marker = None
        self._map_pick_mode = False
        self._canvas_marker_ids = []
        self._map_widget = None
        self._map_canvas = None
        self._map_placeholder = None
        self._fallback_icon = None

        self.win = tk.Toplevel(self.root)
        owner.pencere_hazirla(self.win, "2. Jeoloji Kütüphanesi", "1380x860", (980, 640), modal=False)
        self.win.protocol("WM_DELETE_WINDOW", self.kapat)
        self.win.grid_rowconfigure(2, weight=1)
        self.win.grid_columnconfigure(0, weight=1)
        self._ui_kur()
        self.yenile(reload=True)

    def _ui_kur(self):
        toolbar = ttk.Frame(self.win, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(5, weight=1)
        self._import_button = self.owner.modern_button(
            toolbar, "Word Ekle", command=self.word_ekle, role="primary", icon="file"
        )
        self._import_button.grid(row=0, column=0, padx=(0, SPACE_XS))
        self._folder_button = self.owner.modern_button(
            toolbar, "Klasör(ler) Tara", command=self.klasor_tara, role="accent", icon="folder"
        )
        self._folder_button.grid(row=0, column=1, padx=(0, SPACE_XS))
        self._geometry_button = self.owner.modern_button(
            toolbar,
            "Eksik Sınırları Tamamla",
            command=self.eksik_sinirlari_tamamla,
            role="accent",
            outline=True,
            icon="map",
        )
        self._geometry_button.grid(row=0, column=2, padx=(0, SPACE_XS))
        self._refresh_button = self.owner.modern_button(
            toolbar, "Yenile", command=lambda: self.yenile(reload=True), role="secondary", outline=True, icon="refresh"
        )
        self._refresh_button.grid(row=0, column=3, padx=(0, SPACE_XS))
        self.owner.modern_button(
            toolbar, "Seçimi Temizle", command=self.secimi_temizle, role="warning", outline=True, icon="close"
        ).grid(row=0, column=4, padx=(0, SPACE_SM))
        self._status_var = tk.StringVar(value="Kütüphane hazırlanıyor")
        ttk.Label(toolbar, textvariable=self._status_var, style="Muted.TLabel").grid(row=0, column=5, sticky="w")
        self.owner.modern_button(toolbar, "Kapat", command=self.kapat, role="secondary", outline=True).grid(row=0, column=6)

        filters = ttk.LabelFrame(self.win, text="Filtreler", padding=(10, 7))
        filters.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        for column in (1, 3, 5, 7):
            filters.columnconfigure(column, weight=1)
        self.filter_vars = {
            "ilce": tk.StringVar(),
            "mahalle": tk.StringVar(),
            "aranan": tk.StringVar(),
            "yaricap_km": tk.StringVar(),
        }
        for column, (key, label) in enumerate(
            (("ilce", "İlçe"), ("mahalle", "Mahalle/Köy"), ("aranan", "Formasyon / metin"), ("yaricap_km", "Yarıçap (km)")),
        ):
            base = column * 2
            ttk.Label(filters, text=label, font=FONT_UI_BODY_BOLD).grid(row=0, column=base, sticky="w", padx=(0, SPACE_XS))
            entry = ttk.Entry(filters, textvariable=self.filter_vars[key])
            entry.grid(row=0, column=base + 1, sticky="ew", padx=(0, SPACE_MD if column < 3 else 0))
            entry.bind("<KeyRelease>", self._filtre_keyrelease, add="+")

        pane = tk.PanedWindow(self.win, orient=tk.HORIZONTAL, sashwidth=5, bg=COLOR_BORDER, bd=0, relief="flat")
        pane.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        left = ttk.Frame(pane, padding=(0, 0, 8, 0))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        ttk.Label(left, text="Kütüphane kayıtları", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        tree_wrap = ttk.Frame(left)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)
        columns = (
            ("location", "Konum", 185),
            ("parcel", "Ada / Parsel", 100),
            ("source", "Kaynak", 175),
            ("date", "Eklenme", 95),
            ("coord", "Koordinat", 150),
            ("geometry", "Parsel sınırı", 135),
            ("distance", "Uzaklık", 85),
            ("warning", "Uyarı", 210),
        )
        self.tree = ttk.Treeview(tree_wrap, columns=[item[0] for item in columns], show="headings", selectmode="browse")
        for key, title, width in columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=55, anchor="w", stretch=key in {"location", "source", "warning"})
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure("coordinate_mismatch", foreground="#B45309")
        self.tree.bind("<<TreeviewSelect>>", self._liste_secildi)
        pane.add(left, minsize=460, width=700)

        right = tk.PanedWindow(pane, orient=tk.VERTICAL, sashwidth=5, bg=COLOR_BORDER, bd=0, relief="flat")
        preview = ttk.LabelFrame(right, text="Bölüm önizlemesi", padding=(8, 7))
        preview.grid_rowconfigure(1, weight=1)
        preview.grid_columnconfigure(0, weight=1)
        self._preview_title_var = tk.StringVar(value="Kayıt seçin")
        ttk.Label(preview, textvariable=self._preview_title_var, font=FONT_UI_SECTION).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.preview_text = tk.Text(
            preview,
            height=13,
            wrap="word",
            state="disabled",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            relief="solid",
            bd=1,
            highlightthickness=0,
            font=FONT_UI_BODY,
        )
        self.preview_text.grid(row=1, column=0, sticky="nsew")
        preview_actions = ttk.Frame(preview)
        preview_actions.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        self.owner.modern_button(
            preview_actions, "Bu Bölümü Kullan", command=self.bu_bolumu_kullan, role="success", icon="check"
        ).pack(side="left", padx=(0, SPACE_XS))
        self.owner.modern_button(
            preview_actions, "Metadata Düzenle", command=self.metadata_duzenle, role="secondary", outline=True
        ).pack(side="left", padx=(0, SPACE_XS))
        self.owner.modern_button(
            preview_actions, "Haritada Konum Belirle", command=self.haritada_konum_belirle, role="accent", outline=True
        ).pack(side="left", padx=(0, SPACE_XS))
        self.owner.modern_button(
            preview_actions, "Bölüm Word'ünü Aç", command=self.kaynagi_ac, role="secondary", outline=True
        ).pack(side="left")
        right.add(preview, minsize=245, height=330)

        map_frame = ttk.LabelFrame(right, text="WGS84 kaynak konumları", padding=(5, 5))
        map_frame.grid_rowconfigure(1, weight=1)
        map_frame.grid_columnconfigure(0, weight=1)
        mode_bar = ttk.Frame(map_frame)
        mode_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(mode_bar, text="Görünüm", font=FONT_UI_BODY_BOLD).pack(side="left", padx=(2, SPACE_SM))
        self._map_mode_var = tk.StringVar(value=HARITA_MOD_SECILI)
        for mode, label in MAP_MODE_LABELS:
            ttk.Radiobutton(
                mode_bar,
                text=label,
                value=mode,
                variable=self._map_mode_var,
                command=self._harita_modu_degisti,
                style="Toolbutton",
            ).pack(side="left", padx=(0, 2))
        self._map_host = ttk.Frame(map_frame)
        self._map_host.grid(row=1, column=0, sticky="nsew")
        self._map_host.grid_rowconfigure(0, weight=1)
        self._map_host.grid_columnconfigure(0, weight=1)
        self._map_placeholder = ttk.Label(
            self._map_host,
            text="Haritada görmek için bir kayıt seçin",
            style="Muted.TLabel",
            anchor="center",
        )
        self._map_placeholder.grid(row=0, column=0, sticky="nsew")
        self._map_status_var = tk.StringVar(value="Haritada görmek için bir kayıt seçin")
        self._map_status_label = ttk.Label(
            map_frame,
            textvariable=self._map_status_var,
            style="Muted.TLabel",
            justify="left",
        )
        self._map_status_label.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        map_frame.bind(
            "<Configure>",
            lambda event: self._map_status_label.configure(wraplength=max(220, event.width - 18)),
            add="+",
        )
        self._map_frame = map_frame
        right.add(map_frame, minsize=220)
        pane.add(right, minsize=430)

    def _harita_modu_degisti(self):
        if self._map_ready:
            self._harita_ciz_zamanla(fit=True)
        else:
            self._harita_gorunumu_yenile(force=True, user_requested=True)

    def _harita_yuklemeyi_zamanla(self):
        if not self._pencere_acik_mi() or self._map_ready or self._map_initializing:
            return
        mode = self._map_mode_var.get() if hasattr(self, "_map_mode_var") else HARITA_MOD_SECILI
        if self.selected_id is None and mode != HARITA_MOD_TUMU:
            return
        self._map_initializing = True
        self._map_status_var.set("Harita hazırlanıyor...")
        try:
            self._map_init_after_id = self.win.after(1, self._harita_kur)
        except tk.TclError:
            self._map_init_after_id = None
            self._map_initializing = False

    def _harita_kur(self):
        self._map_init_after_id = None
        self._map_initializing = False
        if not self._pencere_acik_mi() or self._map_ready:
            return
        if self._map_placeholder is not None:
            try:
                self._map_placeholder.destroy()
            except tk.TclError:
                pass
            self._map_placeholder = None
        try:
            import tkintermapview

            self._map_widget = tkintermapview.TkinterMapView(self._map_host, corner_radius=0)
            self._map_widget.grid(row=0, column=0, sticky="nsew")
            tile_name = self.owner.veri.get("ayarlar", {}).get("harita_altlik", DEFAULT_TILE_SERVER)
            provider = TILE_SERVERS.get(tile_name) or TILE_SERVERS.get(DEFAULT_TILE_SERVER)
            self._map_widget.set_tile_server(provider["url"], max_zoom=provider.get("max_zoom", 19))
            self._map_widget.add_left_click_map_command(self._harita_tiklandi)
        except Exception as exc:
            self._map_widget = None
            self._map_canvas = tk.Canvas(self._map_host, bg="#F7F9FB", highlightthickness=0)
            self._map_canvas.grid(row=0, column=0, sticky="nsew")
            self._map_canvas.bind("<Button-1>", self._canvas_tiklandi)
            self._map_status_var.set(f"Çevrimdışı grid görünümü: {exc}")
        self._map_ready = True
        self._map_view_signature = None
        self._harita_gorunumu_yenile(force=False)

    def _harita_tiklandi(self, coords):
        try:
            lat, lon = float(coords[0]), float(coords[1])
        except (TypeError, ValueError, IndexError):
            return
        if self._map_pick_mode:
            self._koordinat_kaydet(lat, lon)

    def _canvas_tiklandi(self, _event):
        if self._map_pick_mode:
            self._map_status_var.set("Çevrimdışı gridde konum seçilemiyor; enlem/boylamı Metadata Düzenle'den girin.")

    def _pencere_acik_mi(self):
        if self._closing:
            return False
        try:
            return bool(self.win.winfo_exists())
        except (tk.TclError, AttributeError):
            return False

    def _harita_ciz_zamanla(self, fit=False):
        if not self._pencere_acik_mi():
            return
        if not self._map_ready:
            self._harita_yuklemeyi_zamanla()
            return
        self._map_fit_requested = bool(self._map_fit_requested or fit)
        if self._map_after_id is not None:
            try:
                self.win.after_cancel(self._map_after_id)
            except (tk.TclError, AttributeError):
                pass
        try:
            self._map_after_id = self.win.after(60, self._harita_ciz_callback)
        except tk.TclError:
            self._map_after_id = None

    def _harita_ciz_callback(self):
        self._map_after_id = None
        if not self._pencere_acik_mi():
            return
        fit = self._map_fit_requested
        self._map_fit_requested = False
        self._harita_gorunumu_yenile(force=fit)

    def _iptal_harita_callback(self):
        callback_id = getattr(self, "_map_after_id", None)
        self._map_after_id = None
        self._map_fit_requested = False
        if callback_id is None:
            return
        try:
            self.win.after_cancel(callback_id)
        except (tk.TclError, AttributeError):
            pass

    def _iptal_harita_init_callback(self):
        callback_id = getattr(self, "_map_init_after_id", None)
        self._map_init_after_id = None
        self._map_initializing = False
        if callback_id is None:
            return
        try:
            self.win.after_cancel(callback_id)
        except (tk.TclError, AttributeError):
            pass

    def _iptal_harita_batch_callback(self):
        callback_id = getattr(self, "_map_batch_after_id", None)
        self._map_batch_after_id = None
        if callback_id is None:
            return
        try:
            self.win.after_cancel(callback_id)
        except (tk.TclError, AttributeError):
            pass

    def _harita_temizle(self):
        if self._map_widget is not None:
            drawings = (
                self._map_markers
                + self._map_polygons
                + self._map_paths
                + ([self._map_project_marker] if self._map_project_marker else [])
            )
            for marker in drawings:
                try:
                    marker.delete()
                except Exception:
                    pass
            self._map_markers = []
            self._map_polygons = []
            self._map_paths = []
            self._map_geometry_drawings = {}
            self._map_project_marker = None
            return
        if self._map_canvas is not None:
            self._map_canvas.delete("all")
            self._canvas_marker_ids = []
            self._map_geometry_drawings = {}

    def _harita_yaricapi(self):
        try:
            value = self.filter_vars["yaricap_km"].get()
            return float(value) if str(value).strip() else YAKINDAKILER_DEFAULT_KM
        except (KeyError, TypeError, ValueError, AttributeError):
            return YAKINDAKILER_DEFAULT_KM

    def _harita_modeli(self):
        mode = self._map_mode_var.get() if hasattr(self, "_map_mode_var") else HARITA_MOD_SECILI
        return harita_gorunum_modeli(
            self.records,
            selected_key=self.selected_id,
            mode=mode,
            radius_km=self._harita_yaricapi(),
            cache=self._map_geometry_cache,
        )

    def _harita_gorunumu_yenile(self, force=False, user_requested=False):
        if not self._pencere_acik_mi():
            return
        mode = self._map_mode_var.get() if hasattr(self, "_map_mode_var") else HARITA_MOD_SECILI
        if self.selected_id is None and mode != HARITA_MOD_TUMU:
            if getattr(self, "_map_ready", False):
                self._harita_temizle()
                self._map_view_signature = None
            self._map_status_var.set("Haritada görmek için bir kayıt seçin")
            return
        if not self._map_ready:
            if user_requested or self.selected_id is not None or mode == HARITA_MOD_TUMU:
                self._harita_yuklemeyi_zamanla()
            return
        model = self._harita_modeli()
        set_changed = force or model["set_signature"] != self._map_view_signature
        self._map_model = model
        if set_changed:
            self._map_view_signature = model["set_signature"]
            self._harita_ciz(fit=True, model=model)
        else:
            self._harita_secim_vurgusunu_guncelle()
            self._harita_durumunu_guncelle(model)

    def _fallback_marker_icon(self):
        if self._fallback_icon is not None:
            return self._fallback_icon
        try:
            icon = tk.PhotoImage(master=self.win, width=11, height=11)
            for y, width in enumerate((1, 3, 5, 7, 9, 11, 9, 7, 5, 3, 1)):
                start = (11 - width) // 2
                icon.put(MAP_FALLBACK, to=(start, y, start + width, y + 1))
            self._fallback_icon = icon
        except (tk.TclError, AttributeError):
            self._fallback_icon = None
        return self._fallback_icon

    def _harita_durumunu_guncelle(self, model):
        selected = next((item for item in model.get("items", []) if item.get("selected")), None)
        if selected is not None:
            record = selected["record"]
            parcel = kayit_ada_parsel_metni(record)
            if selected["kind"] == "polygon":
                message = f"{parcel} · Parsel sınırı gösteriliyor"
            else:
                message = f"{parcel} · Parsel sınırı bulunamadı; kayıt koordinatı gösteriliyor"
            warning = koordinat_poligon_uyari_metni(record, cache=self._map_geometry_cache)
            if warning:
                message += f" · UYARI: {warning}"
            if model["mode"] == HARITA_MOD_YAKINDAKILER:
                message += f" · {model['radius_km']:g} km içinde {len(model['items'])} kayıt"
            self._map_status_var.set(message)
            return
        if not model.get("items"):
            self._map_status_var.set("Seçili kayıt için çizilebilir parsel sınırı veya koordinat yok")
            return
        self._map_status_var.set(
            f"Genel görünüm · {model['geometry_count']} parsel sınırı · "
            f"{model['fallback_count']} sınır bulunamayan kayıt"
        )

    def _harita_ciz(self, fit=True, model=None):
        if not self._pencere_acik_mi():
            return
        model = model or self._harita_modeli()
        self._map_model = model
        self._harita_temizle()
        items = list(model.get("items") or [])
        if not items:
            self._harita_durumunu_guncelle(model)
            return
        fit_bounds = harita_fit_bounds(model)
        if self._map_widget is not None:
            if fit and fit_bounds:
                try:
                    min_lat, min_lon, max_lat, max_lon = fit_bounds
                    self._map_widget.fit_bounding_box((max_lat, min_lon), (min_lat, max_lon))
                except Exception:
                    pass
            for item in sorted(items, key=lambda value: value["selected"]):
                record = item["record"]
                selected = item["selected"]
                outline = MAP_SELECTED_OUTLINE if selected else MAP_OTHER_OUTLINE
                fill = MAP_SELECTED_FILL if selected else MAP_OTHER_FILL
                width = 5 if selected else 2
                if item["kind"] == "polygon":
                    for polygon in item["polygons"]:
                        if not polygon:
                            continue
                        drawing = self._map_widget.set_polygon(
                            polygon[0],
                            outline_color=outline,
                            fill_color=fill,
                            border_width=width,
                            command=lambda _polygon, item_id=record["id"]: self._kayit_sec(item_id),
                            name=f"library_{record['id']}",
                        )
                        self._map_polygons.append(drawing)
                        self._map_geometry_drawings.setdefault(record["id"], []).append(("polygon", drawing))
                        for inner in polygon[1:]:
                            path = self._map_widget.set_path(inner, color=outline, width=max(1, width - 1))
                            self._map_paths.append(path)
                            self._map_geometry_drawings.setdefault(record["id"], []).append(("path", path))
                    continue
                marker_kwargs = {
                    "text": "Sınır yok" if selected else None,
                    "command": lambda _marker, item_id=record["id"]: self._kayit_sec(item_id),
                    "marker_color_circle": MAP_FALLBACK,
                    "marker_color_outside": "#FFFFFF",
                }
                icon = self._fallback_marker_icon()
                if icon is not None:
                    marker_kwargs["icon"] = icon
                self._map_markers.append(
                    self._map_widget.set_marker(item["center"][0], item["center"][1], **marker_kwargs)
                )
            self._harita_durumunu_guncelle(model)
            return

        canvas = self._map_canvas
        if canvas is None or fit_bounds is None:
            self._harita_durumunu_guncelle(model)
            return
        canvas.update_idletasks()
        width = max(400, canvas.winfo_width())
        height = max(180, canvas.winfo_height())
        min_lat, min_lon, max_lat, max_lon = fit_bounds
        lat_span = max(1e-9, max_lat - min_lat)
        lon_span = max(1e-9, max_lon - min_lon)
        pad_x, pad_y = 28, 22

        def pixel(lat, lon):
            x = pad_x + (lon - min_lon) / lon_span * (width - 2 * pad_x)
            y = height - pad_y - (lat - min_lat) / lat_span * (height - 2 * pad_y)
            return x, y

        canvas.create_rectangle(pad_x, pad_y, width - pad_x, height - pad_y, outline=COLOR_BORDER)
        for item in sorted(items, key=lambda value: value["selected"]):
            record = item["record"]
            selected = item["selected"]
            outline = MAP_SELECTED_OUTLINE if selected else MAP_OTHER_OUTLINE
            fill = MAP_SELECTED_FILL if selected else MAP_OTHER_FILL
            tag = f"geometry_{record['id']}" if item["kind"] == "polygon" else f"marker_{record['id']}"
            if item["kind"] == "polygon":
                for polygon in item["polygons"]:
                    if not polygon:
                        continue
                    outer = [value for lat, lon in polygon[0] for value in pixel(lat, lon)]
                    canvas.create_polygon(
                        outer,
                        fill=fill,
                        outline=outline,
                        width=4 if selected else 2,
                        tags=(tag,),
                    )
                    for inner in polygon[1:]:
                        hole = [value for lat, lon in inner for value in pixel(lat, lon)]
                        canvas.create_polygon(hole, fill="#F7F9FB", outline=outline, width=1, tags=(tag,))
                if selected:
                    x, y = pixel(*item["center"])
                    canvas.create_text(
                        x,
                        y,
                        text=kayit_ada_parsel_metni(record),
                        fill=COLOR_TEXT,
                        font=FONT_UI_BODY_BOLD,
                        tags=(tag,),
                    )
                canvas.tag_bind(tag, "<Button-1>", lambda _event, item_id=record["id"]: self._kayit_sec(item_id))
                continue
            x, y = pixel(*item["center"])
            canvas.create_polygon(
                x, y - 6, x + 6, y, x, y + 6, x - 6, y,
                fill=MAP_FALLBACK,
                outline="#FFFFFF",
                width=1,
                tags=(tag,),
            )
            if selected:
                canvas.create_text(x + 9, y, text="Sınır yok", anchor="w", fill=MAP_FALLBACK, tags=(tag,))
            canvas.tag_bind(tag, "<Button-1>", lambda _event, item_id=record["id"]: self._kayit_sec(item_id))
        self._harita_durumunu_guncelle(model)

    def _harita_secim_vurgusunu_guncelle(self):
        """Seçimde bütün geometriyi yeniden oluşturmadan yalnız çizim stilini güncelle."""
        if self._map_widget is not None:
            canvas = getattr(self._map_widget, "canvas", None)
            for record_id, drawings in self._map_geometry_drawings.items():
                selected = record_id == self.selected_id
                color, width = (MAP_SELECTED_OUTLINE, 5) if selected else (MAP_OTHER_OUTLINE, 2)
                fill = MAP_SELECTED_FILL if selected else MAP_OTHER_FILL
                for kind, drawing in drawings:
                    try:
                        if kind == "polygon":
                            drawing.outline_color = color
                            drawing.border_width = width
                            drawing.fill_color = fill
                            if canvas is not None and drawing.canvas_polygon is not None:
                                canvas.itemconfigure(drawing.canvas_polygon, outline=color, width=width, fill=fill)
                                if selected:
                                    canvas.tag_raise(drawing.canvas_polygon)
                        else:
                            drawing.path_color = color
                            drawing.width = max(1, width - 1)
                            if canvas is not None and drawing.canvas_line is not None:
                                canvas.itemconfigure(drawing.canvas_line, fill=color, width=drawing.width)
                    except Exception:
                        pass
            return
        canvas = self._map_canvas
        if canvas is None:
            return
        for record, _polygons in harita_kayitlarini_ayir(self.records, cache=self._map_geometry_cache)[0]:
            selected = record.get("id") == self.selected_id
            color = MAP_SELECTED_OUTLINE if selected else MAP_OTHER_OUTLINE
            for item_id in canvas.find_withtag(f"geometry_{record['id']}"):
                try:
                    if canvas.type(item_id) == "polygon":
                        canvas.itemconfigure(
                            item_id,
                            outline=color,
                            width=4 if selected else 2,
                            fill=MAP_SELECTED_FILL if selected else MAP_OTHER_FILL,
                        )
                    elif canvas.type(item_id) == "text":
                        canvas.itemconfigure(item_id, fill=COLOR_TEXT)
                except tk.TclError:
                    pass

    @staticmethod
    def _zoom_for_points(points):
        span = max(max(item[0] for item in points) - min(item[0] for item in points), max(item[1] for item in points) - min(item[1] for item in points))
        if span < 0.003:
            return 17
        if span < 0.01:
            return 15
        if span < 0.05:
            return 13
        if span < 0.2:
            return 11
        return 8

    def _filtreler(self):
        center = proje_merkez_koordinati(self.owner.veri)
        return {
            "ilce": self.filter_vars["ilce"].get(),
            "mahalle": self.filter_vars["mahalle"].get(),
            "aranan": self.filter_vars["aranan"].get(),
            "yaricap_km": self.filter_vars["yaricap_km"].get(),
            "center": center if center[0] is not None else None,
        }

    def _filtre_keyrelease(self, _event=None):
        if self._closing:
            return
        self._iptal_filtre_debounce()
        try:
            self._filter_after_id = self.win.after(180, self._filtre_debounce)
        except tk.TclError:
            self._filter_after_id = None

    def _iptal_filtre_debounce(self):
        callback_id = self._filter_after_id
        self._filter_after_id = None
        if callback_id is None:
            return
        try:
            self.win.after_cancel(callback_id)
        except (tk.TclError, AttributeError):
            pass

    def _filtre_debounce(self):
        self._filter_after_id = None
        if self._closing:
            return
        try:
            if not self.win.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return
        self.yenile(reload=False)

    def yenile(self, reload=True):
        if self._closing:
            return
        if reload:
            self._kayitlari_arka_planda_yukle()
            return
        self._filtreli_listeyi_uygula()

    def _kayitlari_arka_planda_yukle(self):
        if self._records_loading or not self._pencere_acik_mi():
            return
        self._records_loading = True
        self._load_generation += 1
        generation = self._load_generation
        self._status_var.set("Kütüphane kayıtları arka planda okunuyor...")
        self._kontrolleri_guncelle()

        def worker():
            store = JeolojiKutuphane(
                db_path=self.store.db_path,
                cache_dir=self.store.cache_dir,
                geometry_dir=self.store.geometry_dir,
            )
            return store.list_records()

        def success(records):
            if not self._pencere_acik_mi() or generation != self._load_generation:
                return
            self._records_loading = False
            self._all_records = list(records or [])
            if len(self._map_geometry_cache) > 256:
                self._map_geometry_cache.clear()
            self._filtreli_listeyi_uygula()
            self._kontrolleri_guncelle()

        def error(exc):
            if not self._pencere_acik_mi() or generation != self._load_generation:
                return
            self._records_loading = False
            self._kontrolleri_guncelle()
            self._status_var.set(f"Kütüphane okunamadı: {exc}")

        handle = self.owner.arka_plan_gorevi_baslat(
            "2. Jeoloji kütüphane kayıtlarını oku",
            worker,
            resource="jeoloji_kutuphanesi_okuma",
            status_start="2. Jeoloji kütüphanesi okunuyor.",
            status_success="2. Jeoloji kütüphanesi hazır.",
            status_error="2. Jeoloji kütüphanesi okunamadı: {error}",
            on_success=success,
            on_error=error,
        )
        if hasattr(handle, "cancel"):
            self._task_handles.append(handle)

    def _filtreli_listeyi_uygula(self):
        if not self._pencere_acik_mi():
            return
        try:
            self.records = kayitlari_filtrele(self._all_records, **self._filtreler())
        except Exception as exc:
            self._status_var.set(f"Kütüphane okunamadı: {exc}")
            return
        self.record_map = {record["id"]: record for record in self.records}
        for item in self.tree.get_children():
            self.tree.delete(item)
        selected_exists = False
        for record in self.records:
            source = str(record.get("original_filename") or record.get("filename") or "-")
            distance = record.get("distance_km")
            distance_text = f"{distance:.1f} km" if distance is not None else "-"
            iid = str(record["id"])
            coordinate_check = koordinat_poligon_uyusmazligi(record, cache=self._map_geometry_cache)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    kayit_konum_metni(record),
                    kayit_ada_parsel_metni(record),
                    source,
                    str(record.get("added_at", ""))[:10],
                    kayit_koordinat_metni(record),
                    kayit_geometri_metni(record),
                    distance_text,
                    kayit_uyari_metni(record),
                ),
                tags=("coordinate_mismatch",) if coordinate_check["mismatch"] else (),
            )
            selected_exists = selected_exists or self.selected_id == record["id"]
        if selected_exists:
            self.tree.selection_set(str(self.selected_id))
            self.tree.focus(str(self.selected_id))
            self._onizleme_goster(self.record_map[self.selected_id])
        elif self.selected_id not in self.record_map:
            self.selected_id = None
            self._onizleme_temizle()
        self._harita_gorunumu_yenile(force=False)
        self._status_var.set(f"{len(self.records)} kayıt gösteriliyor · Toplam {len(self._all_records)}")

    def _liste_secildi(self, _event=None):
        selection = self.tree.selection()
        if selection:
            source_id = int(selection[0])
            if source_id != self.selected_id:
                self._kayit_sec(source_id)

    def _kayit_sec(self, source_id):
        try:
            source_id = int(source_id)
        except (TypeError, ValueError):
            return
        record = self.record_map.get(source_id)
        if record is None:
            record = next((item for item in self._all_records if item.get("id") == source_id), None)
        if record is None:
            return
        selection_changed = self.selected_id != source_id
        self.selected_id = source_id
        try:
            iid = str(source_id)
            if tuple(self.tree.selection()) != (iid,):
                self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        except tk.TclError:
            pass
        self._onizleme_goster(record)
        if selection_changed:
            if self._map_ready:
                self._harita_ciz_zamanla(fit=False)
            else:
                self._harita_gorunumu_yenile(force=False)

    def _onizleme_temizle(self):
        self._preview_title_var.set("Kayıt seçin")
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled")

    def _onizleme_goster(self, record):
        self._preview_title_var.set(f"{record.get('original_filename') or record.get('filename') or '-'} · {kayit_konum_metni(record)}")
        boundaries = record.get("heading_boundaries") or {}
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        headings = metadata.get("section_heading_tree") if isinstance(metadata.get("section_heading_tree"), list) else []
        warnings = record.get("warnings") or []
        coordinate_warning = koordinat_poligon_uyari_metni(record, cache=self._map_geometry_cache)
        lines = [
            "2. JEOLOJİ bölüm özeti",
            "-" * 56,
            f"Başlangıç: {boundaries.get('start_heading') or '-'}",
            f"Bitiş sınırı: {boundaries.get('end_heading') or 'Gövde sonu'}",
            f"Başlık düzeyi: {boundaries.get('heading_level') or '-'}",
            f"Paragraf: {record.get('paragraph_count', 0)} · Tablo: {record.get('table_count', 0)} · Görsel: {record.get('image_count', 0)}",
            f"Pafta / Ada / Parsel: {record.get('pafta') or '-'} / {record.get('ada') or '-'} / {record.get('parsel') or '-'}",
            f"Parsel sınırı: {kayit_geometri_metni(record)}",
            f"Koordinat: {kayit_koordinat_metni(record)} · Kaynak: {record.get('coordinate_source') or 'yok'}",
            "",
            "Başlık ağacı:",
        ]
        if coordinate_warning:
            lines[9:9] = [f"UYARI: {coordinate_warning}", ""]
        lines.extend(f"  {heading}" for heading in headings[:40])
        lines.extend(["", "Metin özeti:", metadata.get("summary_text", "") or "Özet çıkarılamadı."])
        if warnings:
            lines.extend(["", "Kalite uyarıları:"])
            lines.extend(f"  ! {warning}" for warning in warnings)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", "\n".join(lines))
        self.preview_text.configure(state="disabled")

    def word_ekle(self):
        paths = filedialog.askopenfilenames(
            parent=self.win,
            title="Aday olarak taranacak Word dosyalarını seçin",
            filetypes=[("Word dosyaları", "*.docx *.docm"), ("Tüm dosyalar", "*.*")],
        )
        self._ice_aktar(paths)

    def klasor_tara(self):
        folders = []
        while True:
            folder = filedialog.askdirectory(
                parent=self.win,
                title="Alt klasörleriyle taranacak Word klasörünü seçin",
            )
            if not folder:
                break
            normalized = os.path.normcase(os.path.abspath(folder))
            if normalized not in {os.path.normcase(os.path.abspath(item)) for item in folders}:
                folders.append(folder)
            if not messagebox.askyesno(
                "Klasör Seçimi",
                f"{len(folders)} klasör seçildi. Başka bir klasör daha eklemek ister misiniz?",
                parent=self.win,
            ):
                break
        if folders:
            self._adaylari_tara(folders, recursive=True)

    def _ice_aktar(self, paths):
        paths = list(dict.fromkeys(str(path) for path in (paths or []) if path))
        if paths:
            self._adaylari_tara(paths, recursive=False)

    def _aday_penceresi_acik_mi(self):
        if self._candidate_window is None:
            return False
        try:
            return bool(self._candidate_window.win.winfo_exists())
        except (tk.TclError, AttributeError):
            self._candidate_window = None
            return False

    def _import_kontrolleri(self, active):
        self.import_active = bool(active)
        self._kontrolleri_guncelle()

    def _kontrolleri_guncelle(self):
        busy = self.import_active or self.geometry_active
        state = "disabled" if busy or self._records_loading else "normal"
        for button in (self._import_button, self._folder_button, self._geometry_button):
            try:
                button.configure(state=state)
            except (tk.TclError, AttributeError):
                pass
        try:
            self._refresh_button.configure(state="disabled" if busy or self._records_loading else "normal")
        except (tk.TclError, AttributeError):
            pass

    def _adaylari_tara(self, sources, recursive):
        sources = list(dict.fromkeys(str(path) for path in (sources or []) if path))
        if not sources or self.import_active or self.geometry_active or self._records_loading:
            return
        if self._aday_penceresi_acik_mi():
            self._candidate_window.win.lift()
            self._candidate_window.win.focus_force()
            return
        self._import_kontrolleri(True)

        def worker(task_context=None):
            def progress(index, total, path, _candidate):
                if task_context:
                    task_context.check_cancelled()
                    task_context.report(index, total, f"Word analiz ediliyor: {os.path.basename(path)}")

            def geometry_progress(index, total, candidate, _success, _error):
                if task_context:
                    task_context.check_cancelled()
                    task_context.report(
                        index,
                        total,
                        f"TKGM sınırı sorgulanıyor: {candidate.get('ada') or '-'}/{candidate.get('parsel') or '-'}",
                    )
            candidates = jeoloji_adaylarini_tara(
                sources,
                recursive=recursive,
                progress=progress,
                geometry_resolver=tkgm_parsel_kml_olustur,
                complete_missing=True,
                geometry_progress=geometry_progress,
            )
            lookup_store = JeolojiKutuphane(
                db_path=self.store.db_path,
                cache_dir=self.store.cache_dir,
                geometry_dir=self.store.geometry_dir,
            )
            existing_by_hash = {
                str(record.get("source_hash") or "").lower(): record
                for record in lookup_store.list_records()
            }
            for candidate in candidates:
                existing = existing_by_hash.get(str(candidate.get("source_hash") or "").lower())
                if existing is not None:
                    duplicate_adayi_hazirla(candidate, existing)
            return candidates

        def success(candidates):
            if not self._pencere_acik_mi():
                return
            self._import_kontrolleri(False)
            if not candidates:
                self._status_var.set("Seçilen klasörlerde DOCX/DOCM bulunamadı.")
                self.owner.bildirim_goster(
                    "Seçilen kaynaklarda DOCX/DOCM raporu bulunamadı.",
                    level="warning",
                    title="2. Jeoloji Taraması",
                )
                return
            geometry_errors = {
                (item.get("path"), item.get("error"))
                for candidate in candidates
                for item in (candidate.get("geometry_scan_errors") or [])
            }
            error_suffix = f" · {len(geometry_errors)} KML/KMZ okunamadı" if geometry_errors else ""
            self._status_var.set(
                f"{len(candidates)} aday tarandı; kütüphaneye henüz kayıt eklenmedi{error_suffix}."
            )

            def closed():
                self._candidate_window = None

            self._candidate_window = JeolojiAdayPenceresi(
                self.owner,
                self.win,
                candidates,
                self._secili_adaylari_ekle,
                on_complete_missing=self._eksik_sinirlari_tamamla,
                on_close=closed,
            )

        def error(exc):
            if not self._pencere_acik_mi():
                return
            self._import_kontrolleri(False)
            self._status_var.set(f"Aday tarama hatası: {exc}")

        handle = self.owner.arka_plan_gorevi_baslat(
            "2. Jeoloji adaylarını tara",
            worker,
            with_context=True,
            cancellable=True,
            resource="jeoloji_kutuphanesi",
            status_start="Tam Word raporları alt klasörleriyle taranıyor.",
            status_success="2. Jeoloji aday taraması tamamlandı.",
            status_error="2. Jeoloji adayları taranamadı: {error}",
            on_success=success,
            on_error=error,
        )
        if hasattr(handle, "cancel"):
            self._task_handles.append(handle)

    def eksik_sinirlari_tamamla(self):
        if self.import_active or self.geometry_active or self._records_loading:
            return
        missing_count = sum(
            not bool((record.get("geometry_metadata") or {}).get("polygons"))
            for record in self._all_records
        )
        if not missing_count:
            self._status_var.set("Tüm kütüphane kayıtlarında parsel sınırı hazır.")
            return
        if not messagebox.askyesno(
            "Eksik Parsel Sınırları",
            f"{missing_count} kayıtta sınır eksik. Önce kaynak klasörlerde yerel KML/KMZ aranacak; "
            "bulunamazsa yeterli metadata olan parseller TKGM'den sorgulanacak. Devam edilsin mi?",
            parent=self.win,
        ):
            return
        self.geometry_active = True
        self._kontrolleri_guncelle()
        self._status_var.set(f"{missing_count} eksik parsel sınırı arka planda tamamlanıyor...")

        def worker(task_context=None):
            store = JeolojiKutuphane(
                db_path=self.store.db_path,
                cache_dir=self.store.cache_dir,
                geometry_dir=self.store.geometry_dir,
            )

            def progress(index, total, candidate, _success, _error):
                if task_context:
                    task_context.check_cancelled()
                    task_context.report(
                        index,
                        total,
                        f"Parsel sınırı işleniyor: {candidate.get('ada') or '-'}/{candidate.get('parsel') or '-'}",
                    )

            return eksik_kutuphane_geometrilerini_tamamla(
                store,
                resolver=tkgm_parsel_kml_olustur,
                progress=progress,
            )

        def success(result):
            if not self._pencere_acik_mi():
                return
            self.geometry_active = False
            self._kontrolleri_guncelle()
            message = (
                f"{result.get('updated', 0)}/{result.get('total', 0)} eksik kayıt güncellendi · "
                f"{result.get('reused', 0)} paylaşılan, {result.get('local', 0)} yerel, "
                f"{result.get('tkgm', 0)} TKGM"
            )
            if result.get("failed") or result.get("skipped"):
                message += (
                    f" · {result.get('failed', 0)} başarısız, "
                    f"{result.get('skipped', 0)} metadata eksik"
                )
            self._status_var.set(message)
            self.yenile(reload=True)
            self.owner.bildirim_goster(
                message,
                level="warning" if result.get("failed") else "success",
                title="Parsel Sınırları",
            )

        def error(exc):
            if not self._pencere_acik_mi():
                return
            self.geometry_active = False
            self._kontrolleri_guncelle()
            self._status_var.set(f"Parsel sınırları tamamlanamadı: {exc}")

        def cancelled():
            if not self._pencere_acik_mi():
                return
            self.geometry_active = False
            self._kontrolleri_guncelle()
            self._status_var.set("Parsel sınırı tamamlama iptal edildi.")

        handle = self.owner.arka_plan_gorevi_baslat(
            "Kütüphanedeki eksik parsel sınırlarını tamamla",
            worker,
            with_context=True,
            cancellable=True,
            resource="jeoloji_kutuphanesi",
            status_start="Eksik parsel sınırları yerel KML ve TKGM ile tamamlanıyor.",
            status_success="Eksik parsel sınırı tamamlama bitti.",
            status_error="Eksik parsel sınırları tamamlanamadı: {error}",
            status_cancel="Parsel sınırı tamamlama iptal edildi.",
            on_success=success,
            on_error=error,
            on_cancel=cancelled,
        )
        if hasattr(handle, "cancel"):
            self._task_handles.append(handle)

    def _secili_adaylari_ekle(self, candidates, dialog):
        if not candidates or self.import_active or self.geometry_active:
            return
        self._import_kontrolleri(True)
        dialog.set_busy(True, f"{len(candidates)} seçili bölüm hazırlanıyor...")

        def worker(task_context=None):
            store = JeolojiKutuphane(
                db_path=self.store.db_path,
                cache_dir=self.store.cache_dir,
                geometry_dir=self.store.geometry_dir,
            )
            imported, errors = [], []
            total = len(candidates)
            for index, candidate in enumerate(candidates, start=1):
                if task_context:
                    task_context.check_cancelled()
                try:
                    imported.append(store.import_candidate(candidate))
                except Exception as exc:
                    errors.append({"path": candidate.get("source_path"), "error": str(exc)})
                if task_context:
                    task_context.report(
                        index,
                        total,
                        f"2. JEOLOJİ bölümü hazırlanıyor: {candidate.get('original_filename') or '-'}",
                    )
            return {"imported": imported, "errors": errors}

        def success(result):
            if not self._pencere_acik_mi():
                return
            self._import_kontrolleri(False)
            if dialog.is_alive():
                dialog.set_busy(False)
            self.yenile(reload=True)
            imported = result.get("imported") or []
            duplicate_count = sum(bool(item.get("duplicate")) for item in imported)
            new_count = len(imported) - duplicate_count
            errors = result.get("errors") or []
            message = f"{new_count} bölüm eklendi; {duplicate_count} mevcut hash yeniden indekslendi."
            if errors:
                message += f" {len(errors)} aday eklenemedi."
            self._status_var.set(message)
            self.owner.bildirim_goster(
                message,
                level="warning" if errors else "success",
                title="2. Jeoloji Kütüphanesi",
            )
            if not errors and dialog.is_alive():
                dialog.kapat()

        def error(exc):
            if not self._pencere_acik_mi():
                return
            self._import_kontrolleri(False)
            if dialog.is_alive():
                dialog.set_busy(False, f"Kütüphaneye ekleme hatası: {exc}")

        handle = self.owner.arka_plan_gorevi_baslat(
            "Seçilen 2. Jeoloji bölümlerini ekle",
            worker,
            with_context=True,
            cancellable=True,
            resource="jeoloji_kutuphanesi",
            status_start=f"{len(candidates)} bölüm-only Word hazırlanıyor.",
            status_success="Seçilen 2. Jeoloji bölümleri kütüphaneye eklendi.",
            status_error="2. Jeoloji bölümleri eklenemedi: {error}",
            on_success=success,
            on_error=error,
        )
        if hasattr(handle, "cancel"):
            self._task_handles.append(handle)

    def _eksik_sinirlari_tamamla(self, candidates, dialog):
        if not candidates or self.import_active or self.geometry_active:
            return
        self._import_kontrolleri(True)
        dialog.set_busy(True, "Eksik parsel sınırları TKGM'den tamamlanıyor...")

        def worker(task_context=None):
            def progress(index, total, candidate, _success, _error):
                if task_context:
                    task_context.check_cancelled()
                    task_context.report(
                        index,
                        total,
                        f"TKGM sınırı sorgulanıyor: {candidate.get('ada') or '-'}/{candidate.get('parsel') or '-'}",
                    )
            return eksik_geometrileri_tkgmden_tamamla(
                candidates,
                tkgm_parsel_kml_olustur,
                progress=progress,
            )

        def success(result):
            if not self._pencere_acik_mi():
                return
            self._import_kontrolleri(False)
            if dialog.is_alive():
                dialog.set_busy(False)
                dialog.geometriler_guncellendi()
            message = (
                f"{result.get('completed', 0)} adayın sınırı tamamlandı; "
                f"{result.get('failed', 0)} sorgu başarısız, {result.get('skipped', 0)} aday metadata nedeniyle atlandı."
            )
            self._status_var.set(message)
            self.owner.bildirim_goster(
                message,
                level="warning" if result.get("failed") else "success",
                title="TKGM Parsel Sınırları",
            )

        def error(exc):
            if not self._pencere_acik_mi():
                return
            self._import_kontrolleri(False)
            if dialog.is_alive():
                dialog.set_busy(False, f"TKGM tamamlama hatası: {exc}")

        handle = self.owner.arka_plan_gorevi_baslat(
            "Eksik jeoloji parsel sınırlarını tamamla",
            worker,
            with_context=True,
            cancellable=True,
            resource="jeoloji_kutuphanesi",
            status_start="Eksik parsel sınırları TKGM'den sorgulanıyor.",
            status_success="TKGM parsel sınırı tamamlama bitti.",
            status_error="TKGM parsel sınırları tamamlanamadı: {error}",
            on_success=success,
            on_error=error,
        )
        if hasattr(handle, "cancel"):
            self._task_handles.append(handle)

    def metadata_duzenle(self):
        record = self.record_map.get(self.selected_id) if self.selected_id else None
        if record is None:
            messagebox.showinfo("Metadata", "Önce bir kütüphane kaydı seçin.", parent=self.win)
            return
        win = tk.Toplevel(self.win)
        self.owner.pencere_hazirla(win, "Metadata Düzenle", "520x510", (440, 430), modal=True)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        fields = (("İl", "il"), ("İlçe", "ilce"), ("Mahalle/Köy", "mahalle"), ("Pafta", "pafta"), ("Ada", "ada"), ("Parsel", "parsel"), ("Enlem", "lat"), ("Boylam", "lon"))
        variables = {}
        for row, (label, key) in enumerate(fields):
            ttk.Label(body, text=label, font=FONT_UI_BODY_BOLD).grid(row=row, column=0, sticky="w", padx=(0, SPACE_SM), pady=5)
            variable = tk.StringVar(value=str(record.get(key) if record.get(key) is not None else ""))
            variables[key] = variable
            ttk.Entry(body, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Elle girilen koordinatın kaynağı 'manuel' olarak saklanır.", style="Muted.TLabel", wraplength=400).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 12))

        def save():
            try:
                updated = self.store.update_record(self.selected_id, {key: variable.get() for key, variable in variables.items()})
                if updated is None:
                    raise ValueError("Kayıt bulunamadı.")
            except Exception as exc:
                messagebox.showerror("Metadata", str(exc), parent=win)
                return
            self.owner.pencere_kapat(win)
            self.yenile()
            self._kayit_sec(self.selected_id)

        self.owner.modern_button(body, "Kaydet", command=save, role="primary", icon="save").grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def haritada_konum_belirle(self):
        if self.selected_id is None:
            messagebox.showinfo("Konum", "Önce bir kütüphane kaydı seçin.", parent=self.win)
            return
        if not self._map_ready:
            self._harita_yuklemeyi_zamanla()
            self._map_status_var.set("Harita yükleniyor; hazır olduğunda konum belirlemeyi yeniden seçin.")
            return
        if self._map_widget is None:
            messagebox.showinfo("Konum", "Çevrimdışı grid görünümünde haritadan seçim kullanılamıyor; metadata penceresinden enlem/boylam girin.", parent=self.win)
            return
        self._map_pick_mode = True
        self._map_status_var.set("Konum modu açık: haritada kaydın konumuna tıklayın.")

    def _koordinat_kaydet(self, lat, lon):
        if self.selected_id is None:
            self._map_pick_mode = False
            return
        try:
            self.store.update_record(self.selected_id, {"lat": lat, "lon": lon, "coordinate_source": "manuel"})
        except Exception as exc:
            messagebox.showerror("Konum", str(exc), parent=self.win)
            return
        self._map_pick_mode = False
        self._map_status_var.set(f"Konum kaydedildi: {lat:.6f}, {lon:.6f}")
        self.yenile()
        self._kayit_sec(self.selected_id)

    def kaynagi_ac(self):
        record = self.record_map.get(self.selected_id) if self.selected_id else None
        if not record or not record.get("cache_path"):
            return
        path = str(record["cache_path"])
        if not os.path.isfile(path):
            messagebox.showwarning("Kaynak", "Cache DOCX bulunamadı.", parent=self.win)
            return
        try:
            os.startfile(path)
        except (AttributeError, OSError):
            messagebox.showinfo("Kaynak", path, parent=self.win)

    def bu_bolumu_kullan(self):
        record = self.record_map.get(self.selected_id) if self.selected_id else None
        if record is None:
            messagebox.showinfo("2. Jeoloji", "Önce bir kütüphane kaydı seçin.", parent=self.win)
            return
        warnings = record.get("warnings") or []
        warning_text = "\n".join(f"- {item}" for item in warnings[:6])
        message = (
            "Seçilen kaynak bölüm hedef rapordaki 2. JEOLOJİ bölümünün tamamının yerine aktarılacak.\n\n"
            "Kaynak bölümdeki şekil numaraları, parsel işaretleri, fay tabloları ve eski proje ifadeleri "
            "bu rapora ait olmayabilir. Tam aktarımı açıkça onaylıyor musunuz?"
        )
        if warning_text:
            message += f"\n\nKalite uyarıları:\n{warning_text}"
        if messagebox.askyesno("Tam 2. Jeoloji aktarımı", message, parent=self.win):
            self._secimi_kaydet()

    def secimi_temizle(self):
        self.owner.veri["jeoloji_kutuphanesi"] = {
            "selected_source_id": None,
            "selected_source_hash": "",
            "selected_snapshot": {},
        }
        self.selected_id = None
        try:
            self.tree.selection_remove(self.tree.selection())
        except tk.TclError:
            pass
        self._onizleme_temizle()
        self._harita_gorunumu_yenile(force=True)
        self.owner.set_save_indicator("2. JEOLOJİ kütüphanesi seçimi temizlendi: kaydedilmedi", "warning")
        self.owner.set_status("2. JEOLOJİ kütüphanesi seçimi temizlendi.", level="info")
        if callable(self.on_changed):
            self.on_changed()

    def _secimi_kaydet(self):
        record = self.record_map.get(self.selected_id) if self.selected_id else None
        if record is None:
            return False
        boundaries = record.get("heading_boundaries") or {}
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        self.owner.veri["jeoloji_kutuphanesi"] = {
            "selected_source_id": record.get("id"),
            "selected_source_hash": record.get("source_hash", ""),
            "selected_snapshot": {
                "source_hash": record.get("source_hash", ""),
                "cache_name": Path(record.get("cache_path", "")).name,
                "cache_kind": metadata.get("cache_kind", ""),
                "cache_hash": metadata.get("cache_hash", ""),
                "start_heading": boundaries.get("start_heading", ""),
                "end_heading": boundaries.get("end_heading", ""),
                "start_index": boundaries.get("start_index", -1),
                "end_index": boundaries.get("end_index", -1),
                "heading_level": boundaries.get("heading_level", 1),
                "selected_at": datetime.datetime.now().isoformat(timespec="seconds"),
            },
        }
        self.owner.set_save_indicator("2. JEOLOJİ kütüphanesi seçildi: kaydedilmedi", "warning")
        self.owner.set_status("Seçili 2. JEOLOJİ bölümü raporda tam aktarım için hazır.", level="success")
        if callable(self.on_changed):
            self.on_changed()
        if hasattr(self.owner, "otomatik_kaydet"):
            self.owner.otomatik_kaydet()
        return True

    def kapat(self):
        if self._closing:
            return
        self._closing = True
        self._load_generation = getattr(self, "_load_generation", 0) + 1
        self._iptal_filtre_debounce()
        self._iptal_harita_init_callback()
        self._iptal_harita_callback()
        self._iptal_harita_batch_callback()
        self._map_pick_mode = False
        for handle in list(getattr(self, "_task_handles", [])):
            try:
                handle.cancel()
            except Exception:
                pass
        if hasattr(self, "_task_handles"):
            self._task_handles.clear()
        if getattr(self, "_candidate_window", None) is not None:
            try:
                self._candidate_window.ebeveyn_kapaniyor()
            except Exception:
                pass
        if hasattr(self, "_map_widget"):
            self._harita_temizle()
        if hasattr(self, "_map_geometry_cache"):
            self._map_geometry_cache.clear()
        self.owner.pencere_kapat(self.win, callback=lambda: setattr(self.owner, "_jeoloji_kutuphanesi_window", None))


__all__ = [
    "JeolojiKutuphanePenceresi",
    "kayit_ada_parsel_metni",
    "kayit_koordinat_metni",
    "kayit_geometri_metni",
    "kayit_konum_metni",
    "kayit_uyari_metni",
    "duplicate_adayi_hazirla",
    "proje_secili_jeoloji_kaydi",
]
