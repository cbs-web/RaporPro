# Dosya: RaporPro/ui_jeoloji_adaylari.py
"""Tam rapor taramasından dönen 2. JEOLOJİ adayları için seçim penceresi."""

from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from harita_motoru import DEFAULT_TILE_SERVER, TILE_SERVERS
from jeoloji_geometri import (
    HARITA_MOD_SECILI,
    aday_geometrisini_sec,
    geometri_harita_poligonlari,
    harita_fit_bounds,
    harita_gorunum_modeli,
)
from sabitler import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_UI_BODY,
    FONT_UI_BODY_BOLD,
    SPACE_SM,
    SPACE_XS,
)


ADAY_MAP_SELECTED_OUTLINE = "#087F5B"
ADAY_MAP_SELECTED_FILL = "#DCEFE7"
ADAY_MAP_AMBIGUOUS_OUTLINE = "#B45309"
ADAY_MAP_FALLBACK = "#D97706"


def aday_secilebilir_mi(candidate):
    return bool(
        isinstance(candidate, dict)
        and candidate.get("eligible")
        and not candidate.get("error")
    )


def aday_anahtari(candidate):
    source_hash = str((candidate or {}).get("source_hash") or "").strip().lower()
    if source_hash:
        return ("hash", source_hash)
    path = str(
        (candidate or {}).get("source_path")
        or (candidate or {}).get("original_path")
        or ""
    )
    return ("path", os.path.normcase(os.path.abspath(path)))


def secili_adaylari_filtrele(candidates):
    """Yalnız işaretli/uygun adayları tam kaynak hash'i üzerinden tekilleştir."""
    selected = []
    seen = set()
    for candidate in candidates or []:
        if not aday_secilebilir_mi(candidate) or not candidate.get("selected"):
            continue
        key = aday_anahtari(candidate)
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    return selected


def _konum_metni(candidate):
    values = [candidate.get("il"), candidate.get("ilce"), candidate.get("mahalle")]
    return " / ".join(str(value).strip() for value in values if str(value or "").strip()) or "-"


def _koordinat_metni(candidate):
    lat, lon = candidate.get("lat"), candidate.get("lon")
    if lat is None or lon is None:
        return "-"
    return f"{float(lat):.6f}, {float(lon):.6f}"


def _durum_metni(candidate):
    status = str(candidate.get("status") or "-")
    if candidate.get("duplicate_geometry_update"):
        return f"{status}; mevcut kayıt sınırla güncellenecek"
    if candidate.get("duplicate"):
        return f"{status}; kütüphanede mevcut"
    return status


def aday_geometri_durum_metni(candidate):
    status = str((candidate or {}).get("geometry_status") or "missing")
    labels = {
        "local_exact": "Yerel KML · tam eşleşme",
        "local_proximity": "Yerel KML · yakınlık eşleşmesi",
        "local_selected": "Yerel KML · kullanıcı seçimi",
        "local_user_selected": "Yerel KML · kullanıcı seçimi",
        "library_reused": "Kütüphane cache'i · aynı parsel",
        "tkgm": "TKGM sınırı",
        "ambiguous": "Belirsiz · KML seçimi gerekli",
        "location_mismatch": "Konum uyuşmazlığı · bağlanmadı",
        "insufficient_metadata": "TKGM metadata eksik",
        "tkgm_error": "Sınır yok · TKGM tekrar denenebilir",
        "not_applicable": "2. JEOLOJİ uygun değil",
        "missing": "Sınır bulunamadı",
    }
    return labels.get(status, status or "Sınır bulunamadı")


def aday_harita_geometri_kayitlari(candidates):
    """Harita ile Treeview'in paylaşacağı aday indeksli geometri listesini üret."""
    records = []
    for index, candidate in enumerate(candidates or []):
        geometry = candidate.get("geometry") if isinstance(candidate, dict) else None
        if isinstance(geometry, dict):
            records.append((index, geometry, False))
            continue
        for option in (candidate.get("geometry_options") or []) if isinstance(candidate, dict) else []:
            if isinstance(option, dict):
                records.append((index, option, True))
    return records


class JeolojiAdayPenceresi:
    """Tarama adaylarını önizletir; callback dışında hiçbir kayıt işlemi yapmaz."""

    def __init__(
        self,
        owner,
        parent,
        candidates,
        on_add,
        on_complete_missing=None,
        on_close=None,
    ):
        self.owner = owner
        self.parent = parent
        self.candidates = [dict(candidate) for candidate in candidates or []]
        self.on_add = on_add
        self.on_complete_missing = on_complete_missing
        self.on_close = on_close
        self.busy = False
        self._closing = False
        self._map_widget = None
        self._map_canvas = None
        self._map_drawings = []
        self._map_markers = []
        self._map_geometry_drawings = {}
        self._map_init_after_id = None
        self._map_after_id = None
        self._map_fit_requested = False
        self._map_ready = False
        self._map_initializing = False
        self._map_view_signature = None
        self._map_model = None
        self._map_geometry_cache = {}
        self._map_placeholder = None
        self._fallback_icon = None

        self.win = tk.Toplevel(parent)
        owner.pencere_hazirla(
            self.win,
            "2. Jeoloji Tarama Adayları",
            "1460x820",
            (980, 620),
            modal=False,
        )
        self.win.protocol("WM_DELETE_WINDOW", self.kapat)
        self.win.grid_rowconfigure(1, weight=1)
        self.win.grid_columnconfigure(0, weight=1)
        self._ui_kur()
        self._listeyi_yenile()

    def _ui_kur(self):
        header = ttk.Frame(self.win, padding=(10, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(header, textvariable=self.status_var, font=FONT_UI_BODY_BOLD).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Tarama sonucu · Henüz kütüphaneye eklenmedi",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        pane = tk.PanedWindow(
            self.win,
            orient=tk.VERTICAL,
            sashwidth=5,
            bg=COLOR_BORDER,
            bd=0,
            relief="flat",
        )
        pane.grid(row=1, column=0, sticky="nsew", padx=10)

        table_frame = ttk.Frame(pane)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        columns = (
            ("pick", "Seç", 52),
            ("file", "Dosya adı", 180),
            ("path", "Kaynak yol", 310),
            ("parcel", "Pafta / Ada / Parsel", 165),
            ("location", "Konum", 190),
            ("coord", "WGS84", 155),
            ("counts", "P / T / G", 88),
            ("geometry", "Sınır Kaynağı / Durumu", 190),
            ("status", "Uygunluk / uyarı", 255),
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=[column[0] for column in columns],
            show="headings",
            selectmode="browse",
        )
        for key, title, width in columns:
            self.tree.heading(key, text=title)
            self.tree.column(
                key,
                width=width,
                minwidth=45,
                anchor="center" if key in {"pick", "counts"} else "w",
                stretch=key in {"path", "status"},
            )
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("rejected", foreground=COLOR_DANGER)
        self.tree.bind("<<TreeviewSelect>>", self._satir_secildi)
        self.tree.bind("<Double-1>", self._cift_tiklandi)
        self.tree.bind("<space>", self._bosluk_tusu)
        self.tree.bind("<Button-1>", self._tiklandi, add="+")
        pane.add(table_frame, minsize=260, height=510)

        lower = tk.PanedWindow(
            pane,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            bg=COLOR_BORDER,
            bd=0,
            relief="flat",
        )
        preview_frame = ttk.LabelFrame(lower, text="Aday önizlemesi", padding=(8, 7))
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        self.preview = tk.Text(
            preview_frame,
            height=10,
            wrap="word",
            state="disabled",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            relief="solid",
            bd=1,
            highlightthickness=0,
            font=FONT_UI_BODY,
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        lower.add(preview_frame, minsize=410, width=650)
        map_frame = ttk.LabelFrame(lower, text="Parsel sınırları", padding=(5, 5))
        map_frame.grid_rowconfigure(0, weight=1)
        map_frame.grid_columnconfigure(0, weight=1)
        self._map_host = ttk.Frame(map_frame)
        self._map_host.grid(row=0, column=0, sticky="nsew")
        self._map_host.grid_rowconfigure(0, weight=1)
        self._map_host.grid_columnconfigure(0, weight=1)
        self._map_placeholder = ttk.Label(
            self._map_host,
            text="Haritada görmek için bir aday seçin",
            style="Muted.TLabel",
            anchor="center",
        )
        self._map_placeholder.grid(row=0, column=0, sticky="nsew")
        self.map_status_var = tk.StringVar(value="Haritada görmek için bir aday seçin")
        self._map_status_label = ttk.Label(
            map_frame,
            textvariable=self.map_status_var,
            style="Muted.TLabel",
            justify="left",
        )
        self._map_status_label.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        map_frame.bind(
            "<Configure>",
            lambda event: self._map_status_label.configure(wraplength=max(220, event.width - 18)),
            add="+",
        )
        self._map_frame = map_frame
        lower.add(map_frame, minsize=360)
        pane.add(lower, minsize=220)

        actions = ttk.Frame(self.win, padding=(10, 8))
        actions.grid(row=2, column=0, sticky="ew")
        self.select_all_button = self.owner.modern_button(
            actions, "Uygunların Tümünü Seç", command=self.tumunu_sec, role="secondary", outline=True
        )
        self.select_all_button.pack(side="left", padx=(0, SPACE_XS))
        self.clear_button = self.owner.modern_button(
            actions, "Seçimi Temizle", command=self.secimi_temizle, role="secondary", outline=True
        )
        self.clear_button.pack(side="left", padx=(0, SPACE_SM))
        self.tkgm_button = self.owner.modern_button(
            actions,
            "Eksik Sınırları TKGM'den Tamamla",
            command=self.eksik_sinirlari_tamamla,
            role="accent",
            outline=True,
        )
        self.tkgm_button.pack(side="left", padx=(0, SPACE_XS))
        self.kml_button = self.owner.modern_button(
            actions,
            "Bu KML'yi Seç",
            command=self.kml_sec,
            role="secondary",
            outline=True,
        )
        self.kml_button.pack(side="left", padx=(0, SPACE_SM))
        self.add_button = self.owner.modern_button(
            actions,
            "Seçilenleri Kütüphaneye Ekle",
            command=self.secilenleri_ekle,
            role="success",
            icon="check",
        )
        self.add_button.pack(side="right")
        self.owner.modern_button(
            actions, "Kapat", command=self.kapat, role="secondary", outline=True
        ).pack(side="right", padx=(0, SPACE_XS))

    def _listeyi_yenile(self, focus_index=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        eligible_count = sum(aday_secilebilir_mi(item) for item in self.candidates)
        selected_count = len(secili_adaylari_filtrele(self.candidates))
        rejected_count = len(self.candidates) - eligible_count
        self.status_var.set(
            f"{len(self.candidates)} aday: {eligible_count} uygun, {rejected_count} reddedilmiş, {selected_count} seçili"
        )
        for index, candidate in enumerate(self.candidates):
            parcel = " / ".join(
                str(candidate.get(key) or "-") for key in ("pafta", "ada", "parsel")
            )
            counts = (
                f"{int(candidate.get('paragraph_count') or 0)} / "
                f"{int(candidate.get('table_count') or 0)} / "
                f"{int(candidate.get('image_count') or 0)}"
            )
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "[x]" if candidate.get("selected") and aday_secilebilir_mi(candidate) else "[ ]",
                    candidate.get("original_filename") or candidate.get("filename") or "-",
                    candidate.get("source_path") or "-",
                    parcel,
                    _konum_metni(candidate),
                    _koordinat_metni(candidate),
                    counts,
                    aday_geometri_durum_metni(candidate),
                    _durum_metni(candidate),
                ),
                tags=() if aday_secilebilir_mi(candidate) else ("rejected",),
            )
        if focus_index is not None and 0 <= focus_index < len(self.candidates):
            iid = str(focus_index)
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self._onizleme_goster(self.candidates[focus_index])
        elif self.candidates:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._onizleme_goster(self.candidates[0])
        self._harita_gorunumu_yenile(force=False)

    def _durum_ozeti_guncelle(self):
        eligible_count = sum(aday_secilebilir_mi(item) for item in self.candidates)
        selected_count = len(secili_adaylari_filtrele(self.candidates))
        rejected_count = len(self.candidates) - eligible_count
        self.status_var.set(
            f"{len(self.candidates)} aday: {eligible_count} uygun, {rejected_count} reddedilmiş, {selected_count} seçili"
        )

    def _satir_guncelle(self, index):
        if index is None or not 0 <= index < len(self.candidates):
            return
        candidate = self.candidates[index]
        iid = str(index)
        parcel = " / ".join(str(candidate.get(key) or "-") for key in ("pafta", "ada", "parsel"))
        counts = (
            f"{int(candidate.get('paragraph_count') or 0)} / "
            f"{int(candidate.get('table_count') or 0)} / "
            f"{int(candidate.get('image_count') or 0)}"
        )
        self.tree.item(
            iid,
            values=(
                "[x]" if candidate.get("selected") and aday_secilebilir_mi(candidate) else "[ ]",
                candidate.get("original_filename") or candidate.get("filename") or "-",
                candidate.get("source_path") or "-",
                parcel,
                _konum_metni(candidate),
                _koordinat_metni(candidate),
                counts,
                aday_geometri_durum_metni(candidate),
                _durum_metni(candidate),
            ),
            tags=() if aday_secilebilir_mi(candidate) else ("rejected",),
        )

    def _index(self, iid=None):
        iid = iid if iid not in (None, "") else self.tree.focus()
        try:
            index = int(iid)
        except (TypeError, ValueError):
            return None
        return index if 0 <= index < len(self.candidates) else None

    def _toggle(self, index):
        if self.busy or index is None:
            return
        candidate = self.candidates[index]
        if not aday_secilebilir_mi(candidate):
            return
        candidate["selected"] = not bool(candidate.get("selected"))
        self._satir_guncelle(index)
        self._durum_ozeti_guncelle()
        self._onizleme_goster(candidate)

    def _tiklandi(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) == "#1":
            self._toggle(self._index(self.tree.identify_row(event.y)))

    def _cift_tiklandi(self, event):
        self._toggle(self._index(self.tree.identify_row(event.y)))

    def _bosluk_tusu(self, _event=None):
        self._toggle(self._index())
        return "break"

    def _satir_secildi(self, _event=None):
        index = self._index(next(iter(self.tree.selection()), None))
        if index is not None:
            self._onizleme_goster(self.candidates[index])
            if getattr(self, "_map_ready", False):
                self._harita_ciz_zamanla(fit=False)
            else:
                self._harita_gorunumu_yenile(force=False)

    def _onizleme_goster(self, candidate):
        metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        headings = metadata.get("section_heading_tree") if isinstance(metadata.get("section_heading_tree"), list) else []
        warnings = candidate.get("warnings") or []
        lines = [
            str(candidate.get("source_path") or "-"),
            "",
            f"Durum: {_durum_metni(candidate)}",
            f"Konum: {_konum_metni(candidate)}",
            f"Pafta / Ada / Parsel: {candidate.get('pafta') or '-'} / {candidate.get('ada') or '-'} / {candidate.get('parsel') or '-'}",
            f"Koordinat: {_koordinat_metni(candidate)} ({candidate.get('coordinate_source') or 'kaynak yok'})",
            f"Parsel sınırı: {aday_geometri_durum_metni(candidate)}",
            f"Sınır etiketi: {candidate.get('geometry_label') or '-'}",
            f"Bölüm: {candidate.get('paragraph_count') or 0} paragraf, {candidate.get('table_count') or 0} tablo, {candidate.get('image_count') or 0} görsel",
            "",
            "Başlık ağacı:",
        ]
        lines.extend(f"  {heading}" for heading in headings[:40])
        lines.extend(["", "Metin özeti:", metadata.get("summary_text") or "Özet çıkarılamadı."])
        if warnings:
            lines.extend(["", "Uyarılar:"])
            lines.extend(f"  ! {warning}" for warning in warnings)
        geometry_errors = candidate.get("geometry_scan_errors") or []
        if geometry_errors:
            lines.extend(["", "Okunamayan KML/KMZ dosyaları:"])
            lines.extend(
                f"  ! {item.get('path') or '-'}: {item.get('error') or 'okunamadı'}"
                for item in geometry_errors[:8]
            )
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "\n".join(lines))
        self.preview.configure(state="disabled")

    def _harita_yuklemeyi_zamanla(self):
        if not self.is_alive() or self._map_ready or self._map_initializing:
            return
        if self._index(next(iter(self.tree.selection()), None)) is None:
            return
        self._map_initializing = True
        self.map_status_var.set("Seçili aday haritası hazırlanıyor...")
        try:
            self._map_init_after_id = self.win.after(1, self._harita_kur)
        except tk.TclError:
            self._map_init_after_id = None
            self._map_initializing = False

    def _harita_kur(self):
        self._map_init_after_id = None
        self._map_initializing = False
        if not self.is_alive() or self._map_ready:
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
        except Exception as exc:
            self._map_widget = None
            self._map_canvas = tk.Canvas(
                self._map_host,
                bg=COLOR_SURFACE_ALT,
                highlightthickness=0,
            )
            self._map_canvas.grid(row=0, column=0, sticky="nsew")
            self.map_status_var.set(f"Çevrimdışı poligon görünümü: {exc}")
        self._map_ready = True
        self._map_view_signature = None
        self._harita_gorunumu_yenile(force=True)

    def _harita_kayitlari(self):
        return aday_harita_geometri_kayitlari(self.candidates)

    def is_alive(self):
        if self._closing:
            return False
        try:
            return bool(self.win.winfo_exists())
        except (tk.TclError, AttributeError):
            return False

    def _harita_ciz_zamanla(self, fit=False):
        if not self.is_alive():
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
        if not self.is_alive():
            return
        fit = self._map_fit_requested
        self._map_fit_requested = False
        self._harita_gorunumu_yenile(force=fit)

    def _iptal_harita_callback(self):
        callback_id = self._map_after_id
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

    def _harita_temizle(self):
        if self._map_widget is not None:
            for drawing in self._map_drawings + self._map_markers:
                try:
                    drawing.delete()
                except Exception:
                    pass
            self._map_drawings = []
            self._map_markers = []
            self._map_geometry_drawings = {}
        elif self._map_canvas is not None:
            self._map_canvas.delete("all")
            self._map_geometry_drawings = {}

    def _harita_aday_sec(self, index):
        if index is None or not 0 <= index < len(self.candidates):
            return
        iid = str(index)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._onizleme_goster(self.candidates[index])
        if getattr(self, "_map_ready", False):
            self._harita_ciz_zamanla(fit=False)
        else:
            self._harita_gorunumu_yenile(force=False)

    def _secili_harita_model_kayitlari(self):
        selected_index = self._index(next(iter(self.tree.selection()), None))
        if selected_index is None:
            return [], None
        candidate = self.candidates[selected_index]
        records = []
        geometry = candidate.get("geometry")
        if isinstance(geometry, dict):
            value = dict(candidate)
            value["_map_key"] = selected_index
            value["_map_ambiguous"] = False
            records.append(value)
        else:
            for option in candidate.get("geometry_options") or []:
                if not isinstance(option, dict):
                    continue
                value = dict(candidate)
                value["geometry"] = option
                value["geometry_hash"] = option.get("geometry_hash", "")
                value["_map_key"] = selected_index
                value["_map_ambiguous"] = True
                records.append(value)
        if not records:
            value = dict(candidate)
            value["_map_key"] = selected_index
            value["_map_ambiguous"] = False
            records.append(value)
        return records, selected_index

    def _harita_modeli(self):
        records, selected_index = self._secili_harita_model_kayitlari()
        return harita_gorunum_modeli(
            records,
            selected_key=selected_index,
            mode=HARITA_MOD_SECILI,
            key_field="_map_key",
            cache=self._map_geometry_cache,
        )

    def _harita_gorunumu_yenile(self, force=False):
        if not self.is_alive():
            return
        if self._index(next(iter(self.tree.selection()), None)) is None:
            self.map_status_var.set("Haritada görmek için bir aday seçin")
            return
        if not self._map_ready:
            self._harita_yuklemeyi_zamanla()
            return
        model = self._harita_modeli()
        self._map_model = model
        if force or model["set_signature"] != self._map_view_signature:
            self._map_view_signature = model["set_signature"]
            self._harita_ciz(fit=True, model=model)
        else:
            self._harita_durumunu_guncelle(model)

    def _fallback_marker_icon(self):
        if self._fallback_icon is not None:
            return self._fallback_icon
        try:
            icon = tk.PhotoImage(master=self.win, width=11, height=11)
            for y, width in enumerate((1, 3, 5, 7, 9, 11, 9, 7, 5, 3, 1)):
                start = (11 - width) // 2
                icon.put(ADAY_MAP_FALLBACK, to=(start, y, start + width, y + 1))
            self._fallback_icon = icon
        except (tk.TclError, AttributeError):
            self._fallback_icon = None
        return self._fallback_icon

    def _harita_durumunu_guncelle(self, model):
        if not model.get("items"):
            self.map_status_var.set("Seçili aday için çizilebilir sınır veya koordinat yok")
            return
        item = model["items"][0]
        candidate = item["record"]
        parcel = f"{candidate.get('ada') or '-'}/{candidate.get('parsel') or '-'}"
        if item["kind"] == "polygon":
            suffix = " · olası sınırlar" if len(model["items"]) > 1 else ""
            self.map_status_var.set(f"{parcel} · Seçili aday parsel sınırı{suffix}")
        else:
            self.map_status_var.set(f"{parcel} · Parsel sınırı bulunamadı; kayıt koordinatı gösteriliyor")

    def _harita_ciz(self, fit=True, model=None):
        if not self.is_alive():
            return
        model = model or self._harita_modeli()
        self._map_model = model
        self._harita_temizle()
        items = list(model.get("items") or [])
        fit_bounds = harita_fit_bounds(model)
        if not items or fit_bounds is None:
            self._harita_durumunu_guncelle(model)
            return
        if self._map_widget is not None:
            if fit:
                try:
                    min_lat, min_lon, max_lat, max_lon = fit_bounds
                    self._map_widget.fit_bounding_box((max_lat, min_lon), (min_lat, max_lon))
                except Exception:
                    pass
            for item in items:
                index = item["key"]
                candidate = item["record"]
                ambiguous = bool(candidate.get("_map_ambiguous"))
                outline = ADAY_MAP_AMBIGUOUS_OUTLINE if ambiguous else ADAY_MAP_SELECTED_OUTLINE
                if item["kind"] == "polygon":
                    for polygon in item["polygons"]:
                        if not polygon:
                            continue
                        drawing = self._map_widget.set_polygon(
                            polygon[0],
                            outline_color=outline,
                            fill_color=ADAY_MAP_SELECTED_FILL,
                            border_width=5,
                            command=lambda _polygon, item_index=index: self._harita_aday_sec(item_index),
                            name=f"aday_{index}",
                        )
                        self._map_drawings.append(drawing)
                        self._map_geometry_drawings.setdefault(index, []).append(("polygon", drawing, ambiguous))
                        for inner in polygon[1:]:
                            path = self._map_widget.set_path(inner, color=outline, width=3)
                            self._map_drawings.append(path)
                            self._map_geometry_drawings.setdefault(index, []).append(("path", path, ambiguous))
                    continue
                marker_kwargs = {
                    "text": "Sınır yok",
                    "marker_color_circle": ADAY_MAP_FALLBACK,
                    "marker_color_outside": "#FFFFFF",
                    "command": lambda _marker, item_index=index: self._harita_aday_sec(item_index),
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
        if canvas is None:
            self._harita_durumunu_guncelle(model)
            return
        canvas.update_idletasks()
        width, height = max(360, canvas.winfo_width()), max(190, canvas.winfo_height())
        min_lat, min_lon, max_lat, max_lon = fit_bounds
        lat_span, lon_span = max(1e-9, max_lat - min_lat), max(1e-9, max_lon - min_lon)
        pad_x, pad_y = 28, 22

        def pixel(point):
            lat, lon = point
            x = pad_x + (lon - min_lon) / lon_span * (width - 2 * pad_x)
            y = height - pad_y - (lat - min_lat) / lat_span * (height - 2 * pad_y)
            return x, y

        canvas.create_rectangle(pad_x, pad_y, width - pad_x, height - pad_y, outline=COLOR_BORDER)
        for item in items:
            index = item["key"]
            candidate = item["record"]
            ambiguous = bool(candidate.get("_map_ambiguous"))
            outline = ADAY_MAP_AMBIGUOUS_OUTLINE if ambiguous else ADAY_MAP_SELECTED_OUTLINE
            tag = f"geometry_{index}" if item["kind"] == "polygon" else f"marker_{index}"
            if item["kind"] == "polygon":
                for polygon in item["polygons"]:
                    outer = [coordinate for point in polygon[0] for coordinate in pixel(point)]
                    canvas.create_polygon(
                        outer,
                        fill=ADAY_MAP_SELECTED_FILL,
                        outline=outline,
                        width=4,
                        tags=(tag,),
                    )
                    for inner in polygon[1:]:
                        hole = [coordinate for point in inner for coordinate in pixel(point)]
                        canvas.create_polygon(hole, fill=COLOR_SURFACE_ALT, outline=outline, width=1, tags=(tag,))
                x, y = pixel(item["center"])
                canvas.create_text(
                    x,
                    y,
                    text=f"{candidate.get('ada') or '-'}/{candidate.get('parsel') or '-'}",
                    fill=COLOR_TEXT,
                    font=FONT_UI_BODY_BOLD,
                    tags=(tag,),
                )
            else:
                x, y = pixel(item["center"])
                canvas.create_polygon(
                    x, y - 6, x + 6, y, x, y + 6, x - 6, y,
                    fill=ADAY_MAP_FALLBACK,
                    outline="#FFFFFF",
                    tags=(tag,),
                )
                canvas.create_text(x + 9, y, text="Sınır yok", anchor="w", fill=ADAY_MAP_FALLBACK, tags=(tag,))
            canvas.tag_bind(tag, "<Button-1>", lambda _event, item_index=index: self._harita_aday_sec(item_index))
        self._harita_durumunu_guncelle(model)

    def _harita_secim_vurgusunu_guncelle(self):
        selected_index = self._index(next(iter(self.tree.selection()), None))
        if self._map_widget is not None:
            canvas = getattr(self._map_widget, "canvas", None)
            for index, drawings in self._map_geometry_drawings.items():
                selected = index == selected_index
                for kind, drawing, ambiguous in drawings:
                    outline = COLOR_PRIMARY if selected else (COLOR_DANGER if ambiguous else COLOR_ACCENT)
                    width = 5 if selected else 3
                    try:
                        if kind == "polygon":
                            drawing.outline_color = outline
                            drawing.border_width = width
                            if canvas is not None and drawing.canvas_polygon is not None:
                                canvas.itemconfigure(drawing.canvas_polygon, outline=outline, width=width)
                                if selected:
                                    canvas.tag_raise(drawing.canvas_polygon)
                        else:
                            drawing.path_color = outline
                            drawing.width = max(2, width - 1)
                            if canvas is not None and drawing.canvas_line is not None:
                                canvas.itemconfigure(drawing.canvas_line, fill=outline, width=drawing.width)
                    except Exception:
                        pass
            return
        canvas = self._map_canvas
        if canvas is None:
            return
        ambiguity_by_index = {
            index: ambiguous
            for index, _geometry, ambiguous in self._harita_kayitlari()
        }
        for index in ambiguity_by_index:
            selected = index == selected_index
            outline = COLOR_PRIMARY if selected else (COLOR_DANGER if ambiguity_by_index[index] else COLOR_ACCENT)
            for item_id in canvas.find_withtag(f"geometry_{index}"):
                try:
                    if canvas.type(item_id) == "polygon":
                        canvas.itemconfigure(
                            item_id,
                            outline=outline,
                            width=4 if selected else 2,
                            fill="#DCEAF3" if selected else "#EDF3F6",
                        )
                    elif canvas.type(item_id) == "text":
                        canvas.itemconfigure(item_id, fill=COLOR_TEXT)
                except tk.TclError:
                    pass

    def eksik_sinirlari_tamamla(self):
        if self.busy or not callable(self.on_complete_missing):
            return
        self.on_complete_missing(self.candidates, self)

    def geometriler_guncellendi(self):
        focus_index = self._index(next(iter(self.tree.selection()), None))
        self._map_geometry_cache.clear()
        self._listeyi_yenile(focus_index=focus_index)

    def kml_sec(self):
        index = self._index(next(iter(self.tree.selection()), None))
        if index is None:
            return
        candidate = self.candidates[index]
        options = candidate.get("geometry_options") or []
        if not options:
            messagebox.showinfo(
                "Parsel KML Seçimi",
                "Bu aday için seçilebilecek yerel KML seçeneği yok.",
                parent=self.win,
            )
            return
        chooser = tk.Toplevel(self.win)
        self.owner.pencere_hazirla(chooser, "Parsel KML Seçimi", "900x430", (700, 330), modal=True)
        body = ttk.Frame(chooser, padding=10)
        body.pack(fill="both", expand=True)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        columns = ("source", "name", "identity", "distance")
        tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        for key, title, width in (
            ("source", "KML/KMZ", 300),
            ("name", "Placemark", 220),
            ("identity", "Konum / Ada / Parsel", 250),
            ("distance", "Uzaklık", 90),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, stretch=key in {"source", "name", "identity"})
        tree.grid(row=0, column=0, sticky="nsew")
        for option_index, option in enumerate(options):
            identity = option.get("identity") or {}
            identity_text = " / ".join(
                str(identity.get(key) or "-") for key in ("ilce", "mahalle", "ada", "parsel")
            )
            distance = option.get("match_distance_km")
            tree.insert(
                "",
                "end",
                iid=str(option_index),
                values=(
                    option.get("source_path") or "-",
                    option.get("placemark_name") or "-",
                    identity_text,
                    f"{distance:.2f} km" if distance is not None else "-",
                ),
            )
        tree.selection_set("0")

        def select_option():
            selection = tree.selection()
            if not selection:
                return
            option = options[int(selection[0])]
            aday_geometrisini_sec(candidate, option, status="local_user_selected")
            candidate["geometry_label"] = option.get("placemark_name") or Path(option.get("source_path", "")).name
            self.owner.pencere_kapat(chooser)
            self._listeyi_yenile(focus_index=index)

        self.owner.modern_button(
            body,
            "Bu KML'yi Seç",
            command=select_option,
            role="primary",
            icon="check",
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

    def tumunu_sec(self):
        if self.busy:
            return
        for candidate in self.candidates:
            candidate["selected"] = aday_secilebilir_mi(candidate)
        self._listeyi_yenile()

    def secimi_temizle(self):
        if self.busy:
            return
        for candidate in self.candidates:
            candidate["selected"] = False
        self._listeyi_yenile()

    def set_busy(self, busy, message=""):
        if not self.is_alive():
            return
        self.busy = bool(busy)
        state = "disabled" if self.busy else "normal"
        for button in (
            self.select_all_button,
            self.clear_button,
            self.tkgm_button,
            self.kml_button,
            self.add_button,
        ):
            button.configure(state=state)
        if message:
            self.status_var.set(message)

    def secilenleri_ekle(self):
        selected = secili_adaylari_filtrele(self.candidates)
        if not selected:
            messagebox.showinfo(
                "2. Jeoloji Adayları",
                "Kütüphaneye eklenecek en az bir uygun satırı işaretleyin.",
                parent=self.win,
            )
            return
        if not messagebox.askyesno(
            "Seçilenleri Kütüphaneye Ekle",
            f"{len(selected)} tam raporun yalnız 2. JEOLOJİ bölümü ve seçilmişse normalize parsel KML'si cache'e yazılacak. Devam edilsin mi?",
            parent=self.win,
        ):
            return
        self.on_add(selected, self)

    def kapat(self):
        if self.busy:
            if self.is_alive():
                self.status_var.set("İşlem sürüyor; görev panelinden iptal edebilirsiniz.")
            return
        self._closing = True
        self._iptal_harita_init_callback()
        self._iptal_harita_callback()
        self._harita_temizle()
        self._map_geometry_cache.clear()
        callback = self.on_close
        self.owner.pencere_kapat(self.win, callback=callback)

    def ebeveyn_kapaniyor(self):
        """Ana pencere kapanırken bekleyen Tk callback'lerini sessizce etkisizleştir."""
        self._closing = True
        self.busy = False
        self._iptal_harita_init_callback()
        self._iptal_harita_callback()
        self._harita_temizle()
        self._map_geometry_cache.clear()


__all__ = [
    "JeolojiAdayPenceresi",
    "aday_anahtari",
    "aday_geometri_durum_metni",
    "aday_harita_geometri_kayitlari",
    "aday_secilebilir_mi",
    "secili_adaylari_filtrele",
]
