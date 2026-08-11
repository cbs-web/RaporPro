# Dosya: RaporPro/ui_rapor_onizleme.py
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import fitz
from PIL import Image, ImageTk

from performans import perf_tracked
from raporlama import raporla as rapor_olustur
from rapor_sablonu import etkin_rapor_sablonu_yolu, proje_rapor_sablon_profili
from sabitler import (
    COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_PRIMARY, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_MUTED, FONT_UI_BODY, FONT_UI_BODY_BOLD,
    FONT_UI_SECTION,
)
from uygulama_yollari import kullanici_yolu


PREVIEW_BG = "#454B52"
PREVIEW_PANEL_BG = "#E8EDF2"
PREVIEW_SHADOW = "#2F343A"
PREVIEW_CACHE_LIMIT = 4


def rapor_onizleme_parmak_izi(veri, source_paths=()):
    """Rapor verisi ve bağlı kaynaklardan kararlı bir önizleme anahtarı üret."""
    source_info = []
    for source in source_paths or ():
        path = str(source or "").strip()
        if not path:
            continue
        try:
            stat = os.stat(path)
            source_info.append((os.path.abspath(path), stat.st_size, stat.st_mtime_ns))
        except OSError:
            source_info.append((os.path.abspath(path), None, None))
    payload = json.dumps(
        {"veri": veri, "kaynaklar": source_info},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rapor_onizleme_olcegi(page_size, viewport_size, mode="width", zoom=1.0):
    """Sayfayı görüntüleme alanına yerleştirecek güvenli render ölçeğini hesapla."""
    page_width, page_height = (max(1.0, float(value)) for value in page_size)
    view_width, view_height = (max(1.0, float(value)) for value in viewport_size)
    usable_width = max(120.0, view_width - 72.0)
    usable_height = max(120.0, view_height - 72.0)
    if mode == "page":
        scale = min(usable_width / page_width, usable_height / page_height)
    elif mode == "actual":
        scale = 96.0 / 72.0
    else:
        scale = usable_width / page_width
    return max(0.35, min(4.0, scale * max(0.25, float(zoom or 1.0))))


def rapor_onizleme_cache_temizle(cache_dir, keep=PREVIEW_CACHE_LIMIT):
    """En yeni önizleme çiftlerini koruyup eski geçici çıktıları temizle."""
    cache_path = Path(cache_dir)
    if not cache_path.is_dir():
        return []
    groups = {}
    for path in cache_path.glob("rapor_*.*"):
        if path.suffix.lower() not in (".docx", ".pdf"):
            continue
        groups.setdefault(path.stem, []).append(path)
    ordered = sorted(
        groups.items(),
        key=lambda item: max((path.stat().st_mtime for path in item[1]), default=0),
        reverse=True,
    )
    removed = []
    for _stem, paths in ordered[max(1, int(keep or 1)):]:
        for path in paths:
            try:
                path.unlink()
                removed.append(str(path))
            except OSError:
                continue
    return removed


def word_pdf_donustur(docx_path, pdf_path):
    """Word belgesini Microsoft Word'ün kendi motoruyla PDF'e dönüştür."""
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "Profesyonel önizleme için Microsoft Word ve pywin32 paketi gerekiyor."
        ) from exc

    app = None
    document = None
    pythoncom.CoInitialize()
    try:
        app = win32com.client.DispatchEx("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        document = app.Documents.Open(
            os.path.abspath(docx_path), ConfirmConversions=False,
            ReadOnly=True, AddToRecentFiles=False,
        )
        document.ExportAsFixedFormat(
            OutputFileName=os.path.abspath(pdf_path),
            ExportFormat=17, OpenAfterExport=False, OptimizeFor=0,
            Range=0, Item=0, IncludeDocProps=True, KeepIRM=True,
            CreateBookmarks=1, DocStructureTags=True,
            BitmapMissingFonts=True, UseISO19005_1=False,
        )
    except Exception as exc:
        raise RuntimeError(
            "Word raporu PDF önizlemesine dönüştürülemedi. "
            "Microsoft Word'ün kurulu ve kullanılabilir olduğunu kontrol edin."
        ) from exc
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
    if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) <= 0:
        raise RuntimeError("Word PDF dönüşümü tamamlandı ancak önizleme dosyası oluşmadı.")
    return pdf_path


class RaporOnizlemeMixin:
    """Word tabanlı profesyonel rapor önizleme merkezini sağlar."""

    def profesyonel_rapor_onizleme_penceresi(self):
        existing = getattr(self, "_rapor_preview_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return
        except tk.TclError:
            pass

        win = tk.Toplevel(self.root)
        self._rapor_preview_window = win
        self.pencere_hazirla(
            win, "Rapor Önizleme Merkezi", "1400x880", (960, 620), modal=False
        )
        win.configure(bg=COLOR_BG)
        win.grid_rowconfigure(2, weight=1)
        win.grid_columnconfigure(0, weight=1)
        win.protocol("WM_DELETE_WINDOW", self._rapor_onizleme_kapat)

        self._preview_doc = None
        self._preview_docx_path = ""
        self._preview_pdf_path = ""
        self._preview_page_index = 0
        self._preview_page_count = 0
        self._preview_zoom = 1.0
        self._preview_zoom_mode = "width"
        self._preview_render_scale = 1.0
        self._preview_search_results = []
        self._preview_search_index = -1
        self._preview_thumb_buttons = []
        self._preview_thumb_photos = []
        self._preview_thumb_job = None
        self._preview_resize_job = None
        self._preview_stale_job = None
        self._preview_generation_active = False
        self._preview_load_token = 0
        self._preview_fingerprint = ""

        self._rapor_onizleme_komut_cubugu(win)
        self._rapor_onizleme_gorunum_cubugu(win)
        self._rapor_onizleme_calisma_alani(win)

        self._preview_status_var = tk.StringVar(value="Önizleme hazırlanıyor...")
        status = tk.Frame(win, bg=COLOR_SURFACE, highlightthickness=1, highlightbackground=COLOR_BORDER)
        status.grid(row=3, column=0, sticky="ew")
        tk.Label(
            status,
            textvariable=self._preview_status_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=12, pady=6)
        self._preview_quality_label = tk.Label(
            status,
            text="Baskı önizlemesi",
            bg=COLOR_SURFACE,
            fg=COLOR_SUCCESS,
            font=FONT_UI_BODY_BOLD,
        )
        self._preview_quality_label.pack(side="right", padx=12)

        win.bind("<F5>", lambda _event: self.rapor_onizleme_yenile(force=True))
        win.bind("<Control-f>", lambda _event: self._preview_search_entry.focus_set())
        win.bind("<Control-plus>", lambda _event: self._rapor_onizleme_zoom(1.15))
        win.bind("<Control-minus>", lambda _event: self._rapor_onizleme_zoom(1 / 1.15))
        win.bind("<Prior>", lambda _event: self._rapor_onizleme_sayfa_git(self._preview_page_index - 1))
        win.bind("<Next>", lambda _event: self._rapor_onizleme_sayfa_git(self._preview_page_index + 1))
        win.bind("<Escape>", lambda _event: self._rapor_onizleme_kapat())
        try:
            win.after_idle(lambda: win.state("zoomed"))
        except tk.TclError:
            pass
        win.after(80, self.rapor_onizleme_yenile)
        self._preview_stale_job = win.after(1800, self._rapor_onizleme_guncellik_kontrol)

    def _rapor_onizleme_komut_cubugu(self, win):
        toolbar = tk.Frame(win, bg=COLOR_SURFACE, padx=10, pady=7)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        self._preview_refresh_button = self.modern_button(
            toolbar,
            "Önizlemeyi Yenile",
            command=lambda: self.rapor_onizleme_yenile(force=True),
            role="accent",
            icon="refresh",
        )
        self._preview_refresh_button.grid(row=0, column=0, sticky="w")
        self._preview_header_var = tk.StringVar(value="Gerçek Word baskı düzeni hazırlanıyor")
        tk.Label(
            toolbar,
            textvariable=self._preview_header_var,
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=FONT_UI_SECTION,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=14)

        actions = tk.Frame(toolbar, bg=COLOR_SURFACE)
        actions.grid(row=0, column=2, sticky="e")
        self._preview_open_word_button = self.modern_button(
            actions,
            "Word'de Aç",
            command=self._rapor_onizleme_word_ac,
            role="primary",
            outline=True,
            icon="report",
        )
        self._preview_open_word_button.pack(side="left", padx=3)
        self._preview_save_pdf_button = self.modern_button(
            actions,
            "PDF Kaydet",
            command=self._rapor_onizleme_pdf_kaydet,
            role="success",
            icon="save",
        )
        self._preview_save_pdf_button.pack(side="left", padx=3)
        self._preview_open_pdf_button = self.modern_button(
            actions,
            "PDF'de Aç",
            command=self._rapor_onizleme_pdf_ac,
            role="neutral",
            outline=True,
            icon="eye",
        )
        self._preview_open_pdf_button.pack(side="left", padx=3)
        self.modern_button(
            actions,
            "Kapat",
            command=self._rapor_onizleme_kapat,
            role="neutral",
            outline=True,
            icon="close",
        ).pack(side="left", padx=(3, 0))
        self._rapor_onizleme_komut_durumu(False)

    def _rapor_onizleme_gorunum_cubugu(self, win):
        bar = tk.Frame(win, bg=PREVIEW_PANEL_BG, padx=10, pady=6)
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(2, weight=1)

        paging = tk.Frame(bar, bg=PREVIEW_PANEL_BG)
        paging.grid(row=0, column=0, sticky="w")
        self.modern_button(
            paging,
            "Önceki",
            command=lambda: self._rapor_onizleme_sayfa_git(self._preview_page_index - 1),
            role="neutral",
            outline=True,
            padx=8,
            pady=3,
        ).pack(side="left")
        self._preview_page_var = tk.StringVar(value="1")
        self._preview_page_spin = ttk.Spinbox(
            paging,
            from_=1,
            to=1,
            width=5,
            textvariable=self._preview_page_var,
            command=self._rapor_onizleme_sayfa_kutusundan_git,
            justify="center",
        )
        self._preview_page_spin.pack(side="left", padx=(8, 3))
        self._preview_page_spin.bind("<Return>", lambda _event: self._rapor_onizleme_sayfa_kutusundan_git())
        self._preview_page_total_var = tk.StringVar(value="/ 0")
        tk.Label(
            paging,
            textvariable=self._preview_page_total_var,
            bg=PREVIEW_PANEL_BG,
            fg=COLOR_PRIMARY,
            font=FONT_UI_BODY_BOLD,
        ).pack(side="left", padx=(0, 8))
        self.modern_button(
            paging,
            "Sonraki",
            command=lambda: self._rapor_onizleme_sayfa_git(self._preview_page_index + 1),
            role="neutral",
            outline=True,
            padx=8,
            pady=3,
        ).pack(side="left")

        zoom = tk.Frame(bar, bg=PREVIEW_PANEL_BG)
        zoom.grid(row=0, column=1, sticky="w", padx=(18, 0))
        self.modern_button(
            zoom,
            "−",
            command=lambda: self._rapor_onizleme_zoom(1 / 1.15),
            role="neutral",
            outline=True,
            padx=9,
            pady=3,
        ).pack(side="left")
        self._preview_zoom_var = tk.StringVar(value="100%")
        tk.Label(
            zoom,
            textvariable=self._preview_zoom_var,
            bg=PREVIEW_PANEL_BG,
            fg=COLOR_PRIMARY,
            width=7,
            font=FONT_UI_BODY_BOLD,
        ).pack(side="left", padx=3)
        self.modern_button(
            zoom,
            "+",
            command=lambda: self._rapor_onizleme_zoom(1.15),
            role="neutral",
            outline=True,
            padx=9,
            pady=3,
        ).pack(side="left")
        self._preview_fit_var = tk.StringVar(value="Genişliğe Sığdır")
        fit_combo = ttk.Combobox(
            zoom,
            textvariable=self._preview_fit_var,
            values=("Genişliğe Sığdır", "Sayfaya Sığdır", "Gerçek Boyut"),
            state="readonly",
            width=18,
        )
        fit_combo.pack(side="left", padx=(8, 0))
        fit_combo.bind("<<ComboboxSelected>>", self._rapor_onizleme_fit_degisti)

        search = tk.Frame(bar, bg=PREVIEW_PANEL_BG)
        search.grid(row=0, column=3, sticky="e")
        self._preview_search_var = tk.StringVar()
        self._preview_search_entry = ttk.Entry(search, textvariable=self._preview_search_var, width=26)
        self._preview_search_entry.pack(side="left")
        self._preview_search_entry.bind("<Return>", lambda _event: self._rapor_onizleme_ara())
        self.modern_button(
            search,
            "Bul",
            command=self._rapor_onizleme_ara,
            role="neutral",
            outline=True,
            icon="eye",
            padx=8,
            pady=3,
        ).pack(side="left", padx=4)
        self.modern_button(
            search,
            "Sonraki",
            command=self._rapor_onizleme_sonraki_eslesme,
            role="neutral",
            outline=True,
            padx=8,
            pady=3,
        ).pack(side="left")

    def _rapor_onizleme_calisma_alani(self, win):
        paned = tk.PanedWindow(
            win,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            bg=COLOR_BORDER,
            bd=0,
            relief="flat",
        )
        paned.grid(row=2, column=0, sticky="nsew")

        thumb_panel = tk.Frame(paned, bg=PREVIEW_PANEL_BG, width=205)
        thumb_panel.pack_propagate(False)
        tk.Label(
            thumb_panel,
            text="SAYFALAR",
            bg=PREVIEW_PANEL_BG,
            fg=COLOR_PRIMARY,
            font=FONT_UI_BODY_BOLD,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))
        thumb_shell = tk.Frame(thumb_panel, bg=PREVIEW_PANEL_BG)
        thumb_shell.pack(fill="both", expand=True)
        self._preview_thumb_canvas = tk.Canvas(
            thumb_shell,
            bg=PREVIEW_PANEL_BG,
            highlightthickness=0,
            bd=0,
        )
        thumb_scroll = ttk.Scrollbar(
            thumb_shell,
            orient="vertical",
            command=self._preview_thumb_canvas.yview,
        )
        self._preview_thumb_canvas.configure(yscrollcommand=thumb_scroll.set)
        thumb_scroll.pack(side="right", fill="y")
        self._preview_thumb_canvas.pack(side="left", fill="both", expand=True)
        self._preview_thumb_inner = tk.Frame(self._preview_thumb_canvas, bg=PREVIEW_PANEL_BG)
        self._preview_thumb_window = self._preview_thumb_canvas.create_window(
            (0, 0),
            window=self._preview_thumb_inner,
            anchor="nw",
        )
        self._preview_thumb_inner.bind(
            "<Configure>",
            lambda _event: self._preview_thumb_canvas.configure(
                scrollregion=self._preview_thumb_canvas.bbox("all")
            ),
        )
        self._preview_thumb_canvas.bind(
            "<Configure>",
            lambda event: self._preview_thumb_canvas.itemconfigure(
                self._preview_thumb_window,
                width=max(1, event.width),
            ),
        )
        self._preview_thumb_canvas.bind(
            "<MouseWheel>",
            lambda event: self._preview_thumb_canvas.yview_scroll(
                -int(event.delta / 120) if event.delta else 0,
                "units",
            ),
        )

        viewer = tk.Frame(paned, bg=PREVIEW_BG)
        viewer.grid_rowconfigure(0, weight=1)
        viewer.grid_columnconfigure(0, weight=1)
        self._preview_canvas = tk.Canvas(
            viewer,
            bg=PREVIEW_BG,
            highlightthickness=0,
            bd=0,
            xscrollincrement=20,
            yscrollincrement=20,
        )
        v_scroll = ttk.Scrollbar(viewer, orient="vertical", command=self._preview_canvas.yview)
        h_scroll = ttk.Scrollbar(viewer, orient="horizontal", command=self._preview_canvas.xview)
        self._preview_canvas.configure(
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
        )
        self._preview_canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        self._preview_canvas.bind("<Configure>", self._rapor_onizleme_canvas_degisti)
        self._preview_canvas.bind("<MouseWheel>", self._rapor_onizleme_mousewheel)
        self._preview_canvas.bind("<Control-MouseWheel>", self._rapor_onizleme_ctrl_mousewheel)
        self._preview_canvas.bind("<Enter>", lambda _event: self._preview_canvas.focus_set())

        paned.add(thumb_panel, minsize=175, width=205)
        paned.add(viewer, minsize=600)

    def rapor_onizleme_yenile(self, force=False):
        if self._preview_generation_active:
            self._preview_status_var.set("Önizleme üretimi halen devam ediyor.")
            return
        try:
            if not self._rapor_preview_window.winfo_exists():
                return
        except (AttributeError, tk.TclError):
            return

        self.guncelle_veri_objesi(silent=True)
        context = self.rapor_arka_plan_context()
        context.set_status = lambda *_args, **_kwargs: None
        sources = (
            context.word_path,
            context.jeo_excel_path,
            context.lab_excel_path,
            context.img_yer,
            context.img_tkgm,
            context.img_pga,
            context.img_mjh,
            context.word_img_jeofizik,
            context.word_img_sondaj,
        )
        fingerprint = rapor_onizleme_parmak_izi(context.veri, sources)
        cache_dir = Path(kullanici_yolu("cache", "rapor_onizleme", "placeholder")).parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._preview_generation_active = True
        self._preview_refresh_button.configure(state="disabled")
        self._preview_status_var.set("Word raporu arka planda hazırlanıyor...")
        self._preview_header_var.set("Önizleme oluşturuluyor")
        self._preview_quality_label.configure(text="Hazırlanıyor", fg=COLOR_TEXT_MUTED)

        self.arka_plan_gorevi_baslat(
            "Rapor önizleme",
            self.rapor_onizleme_worker,
            context,
            str(cache_dir),
            fingerprint,
            bool(force),
            with_context=True,
            resource="render",
            status_start="Profesyonel rapor önizlemesi hazırlanıyor.",
            status_success="Rapor önizlemesi hazırlandı.",
            status_error="Rapor önizlemesi oluşturulamadı: {error}",
            on_success=self._rapor_onizleme_hazir,
            on_error=self._rapor_onizleme_hata,
            on_done=self._rapor_onizleme_uretim_bitti,
        )

    @perf_tracked("report.preview.generate")
    def rapor_onizleme_worker(
        self,
        context,
        cache_dir,
        fingerprint,
        force=False,
        task_context=None,
    ):
        cache_path = Path(cache_dir)
        prefix = f"rapor_{fingerprint[:20]}"
        if not force:
            cached_pdfs = sorted(
                cache_path.glob(f"{prefix}_*.pdf"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for cached_pdf in cached_pdfs:
                cached_docx = cached_pdf.with_suffix(".docx")
                if not cached_docx.is_file():
                    continue
                try:
                    with fitz.open(cached_pdf) as document:
                        page_count = document.page_count
                except Exception:
                    continue
                if page_count:
                    return {
                        "docx": str(cached_docx),
                        "pdf": str(cached_pdf),
                        "pages": page_count,
                        "cached": True,
                        "fingerprint": fingerprint,
                    }

        base = cache_path / f"{prefix}_{time.time_ns()}"
        docx_path = str(base.with_suffix(".docx"))
        pdf_path = str(base.with_suffix(".pdf"))
        for path in (docx_path, pdf_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        if task_context:
            task_context.report(1, 3, "Word raporu oluşturuluyor")
            task_context.check_cancelled()
        success, message = rapor_olustur(context, final_path=docx_path, autosave=False)
        if not success:
            raise RuntimeError(message or "Geçici Word raporu oluşturulamadı.")
        if task_context:
            task_context.report(2, 3, "Word belgesi PDF'e dönüştürülüyor")
            task_context.check_cancelled()
        word_pdf_donustur(docx_path, pdf_path)
        with fitz.open(pdf_path) as document:
            page_count = document.page_count
        if page_count <= 0:
            raise RuntimeError("Önizleme PDF dosyasında görüntülenecek sayfa bulunamadı.")
        if task_context:
            task_context.report(3, 3, f"{page_count} sayfa hazırlandı")
        rapor_onizleme_cache_temizle(cache_path)
        return {
            "docx": docx_path,
            "pdf": pdf_path,
            "pages": page_count,
            "cached": False,
            "fingerprint": fingerprint,
        }

    def _rapor_onizleme_hazir(self, result):
        try:
            if not self._rapor_preview_window.winfo_exists():
                return
        except (AttributeError, tk.TclError):
            return
        self._rapor_onizleme_pdf_yukle(result["pdf"], result["docx"])
        self._preview_fingerprint = result.get("fingerprint", "")
        cache_text = "Önbellekten açıldı" if result.get("cached") else "Yeni önizleme oluşturuldu"
        self._preview_status_var.set(
            f"{cache_text} · {result['pages']} sayfa · Gerçek Word baskı düzeni"
        )
        self._preview_header_var.set(os.path.basename(result["docx"]))
        self._preview_quality_label.configure(text="Baskıya uygun görünüm", fg=COLOR_SUCCESS)

    def _rapor_onizleme_hata(self, exc):
        try:
            if self._rapor_preview_window.winfo_exists():
                self._preview_status_var.set(str(exc))
                self._preview_header_var.set("Önizleme oluşturulamadı")
                self._preview_quality_label.configure(text="Hata", fg="#C0392B")
        except (AttributeError, tk.TclError):
            return
        messagebox.showerror("Rapor Önizleme", str(exc), parent=self._rapor_preview_window)

    def _rapor_onizleme_uretim_bitti(self):
        self._preview_generation_active = False
        try:
            if self._rapor_preview_window.winfo_exists():
                self._preview_refresh_button.configure(state="normal")
        except (AttributeError, tk.TclError):
            pass

    def _rapor_onizleme_pdf_yukle(self, pdf_path, docx_path):
        self._rapor_onizleme_doc_kapat()
        self._preview_doc = fitz.open(pdf_path)
        self._preview_docx_path = docx_path
        self._preview_pdf_path = pdf_path
        self._preview_page_count = self._preview_doc.page_count
        self._preview_page_index = 0
        self._preview_page_spin.configure(to=max(1, self._preview_page_count))
        self._preview_page_total_var.set(f"/ {self._preview_page_count}")
        self._preview_search_results = []
        self._preview_search_index = -1
        self._rapor_onizleme_komut_durumu(True)
        self._rapor_onizleme_thumbnail_temizle()
        self._preview_load_token += 1
        self._rapor_onizleme_sayfa_git(0)
        self._rapor_onizleme_thumbnail_batch(0, self._preview_load_token)

    def _rapor_onizleme_komut_durumu(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in (
            getattr(self, "_preview_open_word_button", None),
            getattr(self, "_preview_save_pdf_button", None),
            getattr(self, "_preview_open_pdf_button", None),
        ):
            if button is not None:
                button.configure(state=state)

    def _rapor_onizleme_sayfa_git(self, page_index):
        if self._preview_doc is None or self._preview_page_count <= 0:
            return
        page_index = max(0, min(int(page_index), self._preview_page_count - 1))
        self._preview_page_index = page_index
        self._preview_page_var.set(str(page_index + 1))
        self._rapor_onizleme_ana_sayfa_ciz()
        self._rapor_onizleme_thumbnail_secimi()
        self._preview_status_var.set(
            f"Sayfa {page_index + 1} / {self._preview_page_count} · "
            f"Yakınlaştırma {self._preview_zoom_var.get()}"
        )

    def _rapor_onizleme_sayfa_kutusundan_git(self):
        try:
            page_index = int(self._preview_page_var.get()) - 1
        except (TypeError, ValueError):
            page_index = self._preview_page_index
        self._rapor_onizleme_sayfa_git(page_index)

    def _rapor_onizleme_ana_sayfa_ciz(self):
        if self._preview_doc is None:
            return
        page = self._preview_doc.load_page(self._preview_page_index)
        self._preview_canvas.update_idletasks()
        viewport = (
            max(300, self._preview_canvas.winfo_width()),
            max(300, self._preview_canvas.winfo_height()),
        )
        scale = rapor_onizleme_olcegi(
            (page.rect.width, page.rect.height),
            viewport,
            mode=self._preview_zoom_mode,
            zoom=self._preview_zoom,
        )
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        self._preview_main_photo = ImageTk.PhotoImage(image)
        self._preview_render_scale = scale

        canvas = self._preview_canvas
        canvas.delete("all")
        canvas_width = max(viewport[0], pixmap.width + 72)
        canvas_height = max(viewport[1], pixmap.height + 72)
        x = max(36, (canvas_width - pixmap.width) // 2)
        y = 30
        canvas.create_rectangle(
            x + 8,
            y + 8,
            x + pixmap.width + 8,
            y + pixmap.height + 8,
            fill=PREVIEW_SHADOW,
            outline="",
        )
        canvas.create_image(x, y, anchor="nw", image=self._preview_main_photo, tags=("page",))
        self._preview_page_origin = (x, y)
        self._rapor_onizleme_aramayi_vurgula()
        canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
        canvas.xview_moveto(0.0)
        canvas.yview_moveto(0.0)
        self._preview_zoom_var.set(f"{int(round(scale * 75))}%")

    def _rapor_onizleme_thumbnail_batch(self, start, token):
        if token != self._preview_load_token or self._preview_doc is None:
            return
        end = min(start + 3, self._preview_page_count)
        for page_index in range(start, end):
            page = self._preview_doc.load_page(page_index)
            scale = min(0.24, 142.0 / max(1.0, page.rect.width))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            photo = ImageTk.PhotoImage(image)
            self._preview_thumb_photos.append(photo)
            card = tk.Button(
                self._preview_thumb_inner,
                image=photo,
                text=f"Sayfa {page_index + 1}",
                compound="top",
                command=lambda index=page_index: self._rapor_onizleme_sayfa_git(index),
                bg=COLOR_SURFACE,
                activebackground="#D6EAF8",
                fg=COLOR_PRIMARY,
                font=FONT_UI_BODY_BOLD,
                relief="flat",
                bd=1,
                padx=8,
                pady=8,
                cursor="hand2",
            )
            card.pack(fill="x", padx=12, pady=(0, 10))
            self._preview_thumb_buttons.append(card)
        self._rapor_onizleme_thumbnail_secimi()
        if end < self._preview_page_count:
            self._preview_thumb_job = self._rapor_preview_window.after(
                1,
                lambda: self._rapor_onizleme_thumbnail_batch(end, token),
            )

    def _rapor_onizleme_thumbnail_secimi(self):
        for index, button in enumerate(self._preview_thumb_buttons):
            active = index == self._preview_page_index
            button.configure(
                bg="#D6EAF8" if active else COLOR_SURFACE,
                relief="solid" if active else "flat",
                bd=2 if active else 1,
                highlightthickness=1 if active else 0,
                highlightbackground=COLOR_ACCENT,
            )
        if self._preview_page_index < len(self._preview_thumb_buttons):
            button = self._preview_thumb_buttons[self._preview_page_index]
            try:
                self._preview_thumb_canvas.yview_moveto(
                    max(0.0, button.winfo_y() / max(1, self._preview_thumb_inner.winfo_height()))
                )
            except tk.TclError:
                pass

    def _rapor_onizleme_thumbnail_temizle(self):
        if self._preview_thumb_job is not None:
            try:
                self._rapor_preview_window.after_cancel(self._preview_thumb_job)
            except tk.TclError:
                pass
            self._preview_thumb_job = None
        for child in self._preview_thumb_inner.winfo_children():
            child.destroy()
        self._preview_thumb_buttons = []
        self._preview_thumb_photos = []

    def _rapor_onizleme_fit_degisti(self, _event=None):
        value = self._preview_fit_var.get()
        self._preview_zoom_mode = {
            "Sayfaya Sığdır": "page",
            "Gerçek Boyut": "actual",
        }.get(value, "width")
        self._preview_zoom = 1.0
        self._rapor_onizleme_ana_sayfa_ciz()

    def _rapor_onizleme_zoom(self, factor):
        if self._preview_doc is None:
            return
        self._preview_zoom *= float(factor)
        self._preview_zoom = max(0.25, min(4.0, self._preview_zoom))
        self._rapor_onizleme_ana_sayfa_ciz()

    def _rapor_onizleme_canvas_degisti(self, _event=None):
        if self._preview_doc is None or self._preview_zoom_mode == "actual":
            return
        if self._preview_resize_job is not None:
            try:
                self._rapor_preview_window.after_cancel(self._preview_resize_job)
            except tk.TclError:
                pass
        self._preview_resize_job = self._rapor_preview_window.after(
            180,
            self._rapor_onizleme_ana_sayfa_ciz,
        )

    def _rapor_onizleme_mousewheel(self, event):
        if event.delta:
            self._preview_canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _rapor_onizleme_ctrl_mousewheel(self, event):
        self._rapor_onizleme_zoom(1.15 if event.delta > 0 else 1 / 1.15)
        return "break"

    def _rapor_onizleme_ara(self):
        query = self._preview_search_var.get().strip()
        if self._preview_doc is None or not query:
            self._preview_search_results = []
            self._preview_search_index = -1
            self._rapor_onizleme_ana_sayfa_ciz()
            return
        results = []
        self._preview_status_var.set(f"'{query}' raporda aranıyor...")
        self._rapor_preview_window.update_idletasks()
        for page_index in range(self._preview_page_count):
            page = self._preview_doc.load_page(page_index)
            for rect in page.search_for(query):
                results.append((page_index, fitz.Rect(rect)))
        self._preview_search_results = results
        self._preview_search_index = -1
        if not results:
            self._preview_status_var.set(f"'{query}' için eşleşme bulunamadı.")
            self._rapor_onizleme_ana_sayfa_ciz()
            return
        self._rapor_onizleme_sonraki_eslesme()

    def _rapor_onizleme_sonraki_eslesme(self):
        if not self._preview_search_results:
            self._rapor_onizleme_ara()
            return
        self._preview_search_index = (
            self._preview_search_index + 1
        ) % len(self._preview_search_results)
        page_index, _rect = self._preview_search_results[self._preview_search_index]
        self._rapor_onizleme_sayfa_git(page_index)
        self._preview_status_var.set(
            f"Arama sonucu {self._preview_search_index + 1} / "
            f"{len(self._preview_search_results)}"
        )

    def _rapor_onizleme_aramayi_vurgula(self):
        if not self._preview_search_results:
            return
        origin_x, origin_y = self._preview_page_origin
        for result_index, (page_index, rect) in enumerate(self._preview_search_results):
            if page_index != self._preview_page_index:
                continue
            active = result_index == self._preview_search_index
            self._preview_canvas.create_rectangle(
                origin_x + rect.x0 * self._preview_render_scale,
                origin_y + rect.y0 * self._preview_render_scale,
                origin_x + rect.x1 * self._preview_render_scale,
                origin_y + rect.y1 * self._preview_render_scale,
                fill="#FFD54F" if active else "#FFF59D",
                outline="#F39C12",
                width=2 if active else 1,
                stipple="gray50",
                tags=("search-highlight",),
            )

    def _rapor_onizleme_word_ac(self):
        if not self._preview_docx_path or not os.path.isfile(self._preview_docx_path):
            messagebox.showwarning("Rapor Önizleme", "Açılacak Word önizlemesi bulunamadı.")
            return
        try:
            os.startfile(self._preview_docx_path)
        except OSError as exc:
            messagebox.showerror(
                "Rapor Önizleme",
                f"Word önizlemesi açılamadı:\n{exc}",
                parent=self._rapor_preview_window,
            )

    def _rapor_onizleme_pdf_kaydet(self):
        if not self._preview_pdf_path or not os.path.isfile(self._preview_pdf_path):
            messagebox.showwarning("Rapor Önizleme", "Kaydedilecek PDF önizlemesi bulunamadı.")
            return
        project = str(self.veri.get("proje", {}).get("proje_adi", "") or "Rapor").strip()
        safe_name = "".join(char if char.isalnum() or char in " _-" else "_" for char in project)
        output_path = filedialog.asksaveasfilename(
            parent=self._rapor_preview_window,
            title="Önizleme PDF'ini Kaydet",
            initialfile=f"{safe_name[:55] or 'Rapor'}_Onizleme.pdf",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not output_path:
            return
        try:
            shutil.copy2(self._preview_pdf_path, output_path)
        except OSError as exc:
            messagebox.showerror(
                "Rapor Önizleme",
                f"PDF kaydedilemedi:\n{exc}",
                parent=self._rapor_preview_window,
            )
            return
        self._preview_status_var.set(f"PDF kaydedildi: {output_path}")
        self.set_status(f"Rapor önizleme PDF'i kaydedildi: {os.path.basename(output_path)}", level="success")

    def _rapor_onizleme_pdf_ac(self):
        if not self._preview_pdf_path or not os.path.isfile(self._preview_pdf_path):
            messagebox.showwarning("Rapor Önizleme", "Açılacak PDF önizlemesi bulunamadı.")
            return
        try:
            os.startfile(self._preview_pdf_path)
        except OSError as exc:
            messagebox.showerror(
                "Rapor Önizleme",
                f"PDF önizlemesi açılamadı:\n{exc}",
                parent=self._rapor_preview_window,
            )

    def _rapor_onizleme_guncellik_kontrol(self):
        win = getattr(self, "_rapor_preview_window", None)
        try:
            if win is None or not win.winfo_exists():
                return
        except tk.TclError:
            return
        if self._preview_fingerprint and not self._preview_generation_active:
            sources = (
                etkin_rapor_sablonu_yolu(
                    getattr(self, "word_path", None),
                    proje_rapor_sablon_profili(getattr(self, "veri", {})),
                ),
                getattr(self, "jeo_excel_path", None),
                getattr(self, "lab_excel_path", None),
                getattr(self, "img_yer", None),
                getattr(self, "img_tkgm", None),
                getattr(self, "img_pga", None),
                getattr(self, "img_mjh", None),
                getattr(self, "word_img_jeofizik", None),
                getattr(self, "word_img_sondaj", None),
            )
            current = rapor_onizleme_parmak_izi(self.veri, sources)
            if current != self._preview_fingerprint:
                self._preview_quality_label.configure(
                    text="Önizleme güncel değil",
                    fg="#E67E22",
                )
        self._preview_stale_job = win.after(1800, self._rapor_onizleme_guncellik_kontrol)

    def _rapor_onizleme_doc_kapat(self):
        document = getattr(self, "_preview_doc", None)
        if document is not None:
            try:
                document.close()
            except Exception:
                pass
        self._preview_doc = None

    def _rapor_onizleme_kapat(self):
        self._preview_load_token += 1
        for job_name in ("_preview_thumb_job", "_preview_resize_job", "_preview_stale_job"):
            job = getattr(self, job_name, None)
            if job is not None:
                try:
                    self._rapor_preview_window.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)
        self._rapor_onizleme_doc_kapat()
        win = getattr(self, "_rapor_preview_window", None)
        self._rapor_preview_window = None
        try:
            if win is not None and win.winfo_exists():
                win.destroy()
        except tk.TclError:
            pass
