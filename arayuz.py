# Dosya: RaporPro/arayuz.py
import tkinter as tk
from tkinter import messagebox, ttk
import datetime
import json
import os

from sabitler import *
from yardimcilar import *
from performans import log_exception, perf_tracked
from task_engine import TkTaskEngine
from widgets import UndoRedoEntry

from ui_cikti import CiktiMerkeziMixin
from ui_haritalar import HaritalarSekmesiMixin
from ui_jeofizik import JeofizikMixin
from ui_jeofizik_sheet import JeofizikSheetMixin
from ui_karot_tcr import KarotTCRMixin
from ui_kesit import KesitCizimMixin
from ui_kontrol import KontrolPaneliMixin
from ui_lab_sheet import LabSheetMixin
from ui_rapor import RaporSekmesiMixin
from ui_proje_surumleri import ProjeSurumleriMixin
from ui_sondaj_derinlik import SondajDerinlikHesabiMixin
from ui_spt_okuma import SPTOkumaMixin
from ui_sondaj import SondajMixin
from ui_workbook import WorkbookMixin
from arayuz_temel import ArayuzTemelMixin
from arayuz_proje import ArayuzProjeMixin
from arayuz_ozet import ArayuzOzetMixin
from arayuz_araclar import ArayuzAraclarMixin
from yonetmelik_motoru import varsayilan_yonetmelikleri_hazirla
from uygulama_yollari import SOURCE_DIR, kullanici_yolu

APP_DIR = str(SOURCE_DIR)
AUTOSAVE_PATH = str(
    kullanici_yolu(
        "autosave",
        "raporpro_autosave.json",
        legacy=SOURCE_DIR / "autosave" / "raporpro_autosave.json",
    )
)
AUTOSAVE_DIR = os.path.dirname(AUTOSAVE_PATH)
# ============================================================================
# ÖZEL SPT VERİ GİRİŞ PENCERESİ (OTOMATİK HESAPLAMA VE DERİNLİK ARTIŞI)
class RaporRobotuArayuz(ArayuzTemelMixin, ArayuzProjeMixin, ProjeSurumleriMixin, ArayuzOzetMixin, ArayuzAraclarMixin, SondajDerinlikHesabiMixin, RaporSekmesiMixin, HaritalarSekmesiMixin, CiktiMerkeziMixin, KontrolPaneliMixin, LabSheetMixin, JeofizikSheetMixin, KesitCizimMixin, WorkbookMixin, SPTOkumaMixin, KarotTCRMixin, SondajMixin, JeofizikMixin):
    @perf_tracked("ui.__init__")
    def __init__(self, root):
        self.root = root
        self.root.report_callback_exception = self._tk_exception_handler
        self.setup_styles()
        self.root.title("Zemin Rapor Pro v49.0 - Hızlı MT Veri Girişi")
        self.pencere_ekrana_sigdir(self.root, "1450x950", (1024, 680), width_ratio=0.96, height_ratio=0.92)
        self.root.after_idle(self.ana_pencere_tam_ekran_yap)
        self.root.configure(bg=COLOR_BG)
        
        self.aktif_dosya_yolu = None 
        self.kml_path = None
        
        self.veri = self.veri_yukle()
        self.word_path = None
        self.img_yer = None; self.img_tkgm = None; self.img_pga = None; self.img_mjh = None
        
        self.word_img_sondaj = None
        self.word_img_jeofizik = None
        
        self.lab_excel_path = None
        self.jeo_excel_path = None 
        self.last_focused = None
        self.last_preflight_report = None
        self.autosave_after_id = None
        self._closing = False
        self._kilitli_kayda_izin_ver = False
        self.last_save_time = None
        self._son_kayit_imzasi = None
        self.autosave_status_var = tk.StringVar(value="Kayıt durumu: bekleniyor")
        self.task_status_var = tk.StringVar(value="İşlem: hazır")
        self.task_engine = TkTaskEngine(
            self.root,
            status_callback=self.set_status,
            state_callback=self._task_engine_state_changed,
            max_workers=2,
        )
        self._startup_yonetmelik_error = None
        try:
            varsayilan_yonetmelikleri_hazirla()
        except Exception as exc:
            self._startup_yonetmelik_error = exc
        self.recent_projects = self.recent_projects_yukle()
        
        self.root.bind_all("<Button-1>", self.track_focus, add="+")
        self.sondaj_ui_rows = [] 
        self.kur_arayuz()
        self.kur_kisayollar()
        self.doldur_arayuz()
        self.kayit_imzasi_guncelle(collect=True)
        
        if self.aktif_dosya_yolu:
            self.root.title(f"Zemin Rapor Pro - {os.path.basename(self.aktif_dosya_yolu)}")
            self.set_status(f"Yüklendi: {self.aktif_dosya_yolu}")
        else:
            self.set_status("Yeni Proje (Kaydedilmemiş)")
        if getattr(self, "bootstrap_theme_active", False):
            self.set_status(f"Modern tema etkin: {self.bootstrap_theme_name}", level="success")
        if getattr(self, "_startup_load_error", None):
            self.set_status(f"Varsayılan proje okunamadı: {self._startup_load_error}", level="warning")
        if getattr(self, "_startup_yonetmelik_error", None):
            self.set_status(f"Yerleşik yönetmelik hazırlanamadı: {self._startup_yonetmelik_error}", level="warning")
        self.kurtarma_durumu_bildir()
        self.root.protocol("WM_DELETE_WINDOW", self.uygulamayi_kapat)
        self.start_autosave()

    def _tk_exception_handler(self, exc_type, exc_value, exc_tb):
        log_exception("tk.callback", exc_type, exc_value, exc_tb)
        try:
            self.set_status(f"Hata gunlugune yazildi: {exc_value}", level="error")
        except Exception:
            pass

    def track_focus(self, event):
        w = event.widget
        if isinstance(w, (ttk.Entry, tk.Entry, UndoRedoEntry)): self.last_focused = w

    def start_autosave(self):
        if getattr(self, "_closing", False):
            return
        if self.autosave_after_id:
            try:
                self.root.after_cancel(self.autosave_after_id)
            except Exception:
                pass
            self.autosave_after_id = None
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self.autosave_after_id = self.root.after(90000, self.autosave_tick)

    def autosave_tick(self):
        self.autosave_after_id = None
        if getattr(self, "_closing", False):
            return
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self.otomatik_kaydet()
        self.start_autosave()

    def autosave_zamanlayici_iptal(self):
        after_id = getattr(self, "autosave_after_id", None)
        self.autosave_after_id = None
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass

    def uygulamayi_kapat(self):
        if hasattr(self, "task_engine"):
            active = self.task_engine.snapshot().active_count
            if active:
                if getattr(self, "_gorevlerden_sonra_kapat", False):
                    return
                names = self.task_engine.active_task_names()
                detail = "\n".join(f"- {name}" for name in names[:5])
                if len(names) > 5:
                    detail += f"\n- ... ve {len(names) - 5} görev daha"
                wait_for_tasks = messagebox.askyesno(
                    "Devam Eden İşlemler",
                    f"{active} arka plan işlemi devam ediyor:\n\n{detail}\n\n"
                    "Çıktıların bozulmaması için program işlemler tamamlanınca otomatik kapatılsın mı?",
                )
                if not wait_for_tasks:
                    self.set_status("Kapatma iptal edildi; arka plan işlemleri devam ediyor.", level="warning")
                    return
                self._gorevlerden_sonra_kapat = True
                self.set_status("İşlemler tamamlanınca program kapatılacak.", level="info")
                self.root.after(250, self._gorevler_bittiginde_kapat)
                return
        if not self.kaydedilmemis_degisiklik_onayi():
            return
        self._closing = True
        self.autosave_zamanlayici_iptal()
        try:
            if hasattr(self, "task_engine"):
                self.task_engine.shutdown(wait=False)
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _gorevler_bittiginde_kapat(self):
        if getattr(self, "_closing", False):
            return
        active = self.task_engine.snapshot().active_count if hasattr(self, "task_engine") else 0
        if active:
            self.root.after(250, self._gorevler_bittiginde_kapat)
            return
        self._gorevlerden_sonra_kapat = False
        self.uygulamayi_kapat()

    def otomatik_kaydet(self):
        if getattr(self, "_closing", False):
            return
        try:
            if self.proje_kilitli_mi():
                self.set_save_indicator("Proje kilitli: otomatik kayıt yok", "warning")
                return
            if hasattr(self, "e_kunye"):
                self.guncelle_veri_objesi(silent=True)
            os.makedirs(AUTOSAVE_DIR, exist_ok=True)
            payload = {
                "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "active_path": self.aktif_dosya_yolu,
                "veri": self.veri,
            }
            atomic_json_dump(payload, AUTOSAVE_PATH, indent=2, ensure_ascii=False)
            self.set_save_indicator(f"Otomatik kayıt: {datetime.datetime.now().strftime('%H:%M')}", "info")
        except Exception as exc:
            log_exception("autosave.write", exc_value=exc)
            self.set_save_indicator("Otomatik kayıt hatası", "error")

    def kurtarma_durumu_bildir(self):
        try:
            if not os.path.exists(AUTOSAVE_PATH):
                return
            autosave_time = os.path.getmtime(AUTOSAVE_PATH)
            project_time = os.path.getmtime(self.aktif_dosya_yolu) if self.aktif_dosya_yolu and os.path.exists(self.aktif_dosya_yolu) else 0
            if autosave_time > project_time:
                self.set_status("Kurtarma dosyasi bulundu. Ust menuden 'Kurtar' ile yukleyebilirsiniz.", level="warning")
        except Exception as exc:
            log_exception("autosave.check", exc_value=exc)

    @perf_tracked("project.restore_autosave")
    def otomatik_kayit_yukle(self):
        try:
            with open(AUTOSAVE_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            veri = payload.get("veri", {})
            veri, _migrasyon = self.proje_verisini_hazirla(veri)
            self.veri = veri
            self.aktif_dosya_yolu = payload.get("active_path")
            self.doldur_arayuz()
            self._son_kayit_imzasi = None
            self.set_status(f"Otomatik kayıt yüklendi: {payload.get('saved_at', '-')}", level="success")
            self.set_save_indicator("Kurtarma yüklendi: kaydedilmedi", "warning")
        except Exception as exc:
            log_exception("autosave.restore", exc_value=exc)
            messagebox.showerror("Kurtarma", f"Otomatik kayıt yüklenemedi:\n{exc}")

    @perf_tracked("ui.build")
    def kur_arayuz(self):
        toolbar = tk.Frame(self.root, bg="#E9EEF2", height=44)
        toolbar.pack(fill="x", side="top")

        self.toolbar_menu(toolbar, "Proje", [
            ("Yeni Proje", self.yeni_proje),
            ("Proje Aç", self.proje_ac),
            ("Son Projeler", self.son_projeler_penceresi),
            None,
            ("Kaydet", self.veri_kaydet),
            ("Farklı Kaydet", self.proje_farkli_kaydet),
            ("Kurtarma Kaydını Aç", self.otomatik_kayit_yukle),
            ("Sürüm Geçmişi", self.surum_gecmisi_penceresi),
            None,
            ("Tamamlandı Olarak Kilitle", self.proje_tamamlandi_kilitle),
            ("Proje Kilidini Kaldır", self.proje_kilidini_kaldir),
            ("Biten İşler KML Oluştur", self.biten_isler_kml_olustur),
            None,
            ("Demo Proje", self.ornek_proje_yukle),
        ], bg="#F4F6F7", tooltip="Proje açma, kaydetme ve kurtarma işlemleri", role="primary")
        self.toolbar_menu(toolbar, "Veri", [
            ("Workbook", self.veri_giris_workbook_tksheet_ac),
            ("Sondaj Hızlı Tablo", self.sondaj_hizli_tablo_ac),
            ("Akıllı Tamamla", self.sondaj_akilli_tamamla),
            ("Şablonlar", self.proje_sablon_penceresi),
        ], bg="#D6EAF8", tooltip="Veri girişini hızlandıran araçlar", role="accent")
        self.toolbar_menu(toolbar, "Kontrol", [
            ("Tamamlama Merkezi", self.tamamlama_merkezi_penceresi),
            ("Proje Özeti", lambda: self._workflow_git("ozet")),
            ("Günlükler", self.gunluk_penceresi),
        ], bg="#FADBD8", tooltip="Eksikleri ve rapor hazırlığını kontrol eder", role="warning")
        self.toolbar_menu(toolbar, "Çıktı", [
            ("Çıktı Merkezi", self.cikti_merkezi_penceresi),
            ("Dışa Aktar", self.veri_disari_aktar),
            ("Toplu Log Kaydet", self.toplu_log_kaydet),
            ("Sadece Grafikleri Çıkar", self.grafikleri_kaydet),
        ], bg="#D5F5E3", tooltip="Rapor, log, kesit ve görsel çıktılarını toplar", role="success")
        self.toolbar_menu(toolbar, "Araçlar", [
            ("KML Sınır Seç", self.kml_sec),
            ("Tüm Koordinatları Seç", self.toplu_harita_ac),
            ("Sondaj Derinliği Hesabı", self.sondaj_derinlik_hesabi_penceresi),
            None,
            ("Ayarlar", self.ayarlar_penceresi),
            ("Etiketler", self.etiket_yoneticisi),
            None,
            ("Geri", self.global_undo),
            ("İleri", self.global_redo),
        ], bg="#E8DAEF", tooltip="Harita, ayar ve geri alma araçları", role="secondary")

        tk.Frame(toolbar, width=12, bg="#E9EEF2").pack(side="left")
        self.lbl_kml_top = tk.Label(toolbar, text="KML Sınır: Seçilmedi", bg="#E9EEF2", fg="#333", font=("Arial", 8))
        self.lbl_kml_top.pack(side="left", padx=10)
        self.tooltip_ekle(self.lbl_kml_top, "Seçili KML sınır dosyasının durumunu gösterir")

        self.autosave_status_label = tk.Label(toolbar, textvariable=self.autosave_status_var, bg="#E9EEF2", fg="#333333", font=("Arial", 8, "bold"))
        self.autosave_status_label.pack(side="right", padx=10)
        self.tooltip_ekle(self.autosave_status_label, "Otomatik kayıt ve proje kayıt durumunu gösterir")
        self.task_status_label = tk.Label(toolbar, textvariable=self.task_status_var, bg="#E9EEF2", fg="#333333", font=("Arial", 8, "bold"))
        self.task_status_label.pack(side="right", padx=10)
        self.tooltip_ekle(self.task_status_label, "Arka planda çalışan uzun işlemleri gösterir")
        
        main_splitter = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashwidth=4, bg=COLOR_BG)
        main_splitter.pack(fill="both", expand=True)
        top_frame = ttk.Frame(main_splitter)
        nb = ttk.Notebook(top_frame)
        self.nb = nb
        nb.pack(fill="both", expand=True)
        main_splitter.add(top_frame, height=750)
        
        self.tab_ozet=ttk.Frame(nb); nb.add(self.tab_ozet, text="0. Özet"); self.p_ozet(self.tab_ozet)
        self.tab_kunye=ttk.Frame(nb); nb.add(self.tab_kunye, text="1. Künye"); self.p_kunye(self.tab_kunye)
        self.tab_bina=ttk.Frame(nb); nb.add(self.tab_bina, text="2. Bina"); self.p_bina(self.tab_bina)
        self.tab_arazi=ttk.Frame(nb); nb.add(self.tab_arazi, text="3. Arazi"); self.p_arazi(self.tab_arazi)
        self.tab_sondaj=ttk.Frame(nb); nb.add(self.tab_sondaj, text="4. Sondaj"); self.p_sondaj(self.tab_sondaj)
        self.tab_jeofizik=ttk.Frame(nb); nb.add(self.tab_jeofizik, text="5. Jeofizik"); self.p_jeofizik(self.tab_jeofizik)
        self.tab_haritalar=ttk.Frame(nb); nb.add(self.tab_haritalar, text="6. Haritalar"); self.p_haritalar(self.tab_haritalar)
        self.tab_rapor=ttk.Frame(nb); nb.add(self.tab_rapor, text="7. Rapor"); self.p_rapor(self.tab_rapor)
        nb.bind("<<NotebookTabChanged>>", self.notebook_tab_changed)
        
        log_frame = tk.Frame(main_splitter, bg=COLOR_LOG_BG)
        self.log_text = tk.Text(log_frame, height=8, bg=COLOR_LOG_BG, fg=COLOR_LOG_TEXT, font=FONT_LOG, state="disabled")
        self.log_text.pack(fill="both", expand=True)
        main_splitter.add(log_frame, height=200)
        self.log_text.tag_config("error", foreground=COLOR_DANGER)
        self.log_text.tag_config("success", foreground="#00FF00")
        self.log_text.tag_config("warning", foreground=COLOR_WARNING)
        self.log_text.tag_config("normal", foreground=COLOR_LOG_TEXT)

    def form_klavye_gecisi_ekle(self, widgets):
        """Form alanlarında Enter ve ok tuşlarıyla dikey gezinmeyi standartlaştır."""
        widgets = [widget for widget in widgets if widget is not None]

        def focus_index(index):
            if not widgets:
                return "break"
            index = max(0, min(index, len(widgets) - 1))
            widget = widgets[index]
            try:
                widget.focus_set()
                if hasattr(widget, "selection_range"):
                    widget.selection_range(0, tk.END)
            except Exception:
                pass
            return "break"

        for index, widget in enumerate(widgets):
            widget.bind("<Return>", lambda event, idx=index: focus_index(idx + 1), add="+")
            widget.bind("<Down>", lambda event, idx=index: focus_index(idx + 1), add="+")
            widget.bind("<Up>", lambda event, idx=index: focus_index(idx - 1), add="+")

    @staticmethod
    def _form_sayi_mi(value):
        text = str(value or "").strip().replace(",", ".")
        if not text:
            return False
        try:
            float(text)
            return True
        except (TypeError, ValueError):
            return False

    def form_verilerini_uygula(self, section_name):
        """Açık formları proje verisine uygula ve kurtarma kaydını güncelle."""
        self.guncelle_veri_objesi(silent=True)
        self.otomatik_kaydet()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        self.set_status(f"{section_name} bilgileri projeye uygulandı.", level="success")

    def _form_entry_ekle(self, parent, row, label, key, store, width=28):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=(0, SPACE_SM), pady=SPACE_XS)
        entry = UndoRedoEntry(parent, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=SPACE_XS)
        store[key] = entry
        return entry

    def kunye_durum_guncelle(self, event=None):
        required = ("sahibi", "il", "ilce")
        values = {key: entry.get().strip() for key, entry in self.e_kunye.items()}
        missing = [key for key in required if not values.get(key)]
        for key, entry in self.e_kunye.items():
            entry.configure(style="Warning.TEntry" if key in missing else "Valid.TEntry")
        filled = sum(bool(value) for value in values.values())
        if missing:
            labels = {"sahibi": "Proje adı", "il": "İl", "ilce": "İlçe"}
            self.kunye_durum_var.set(f"{filled}/8 alan dolu · Eksik: {', '.join(labels[key] for key in missing)}")
            self.kunye_durum_label.configure(foreground=COLOR_WARNING)
        else:
            self.kunye_durum_var.set(f"{filled}/8 alan dolu · Temel proje bilgileri hazır")
            self.kunye_durum_label.configure(foreground=COLOR_SUCCESS)

    def p_kunye(self, p):
        page = ttk.Frame(p, padding=(16, 12))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Proje Künyesi", style="PageTitle.TLabel").pack(anchor="w")
        self.kunye_durum_var = tk.StringVar(value="Proje bilgileri bekleniyor")
        self.kunye_durum_label = ttk.Label(title_area, textvariable=self.kunye_durum_var, style="Muted.TLabel")
        self.kunye_durum_label.pack(anchor="w", pady=(2, 0))
        apply_button = self.modern_button(
            header,
            "Uygula",
            command=lambda: self.form_verilerini_uygula("Künye"),
            role="success",
            padx=10,
            pady=5,
        )
        apply_button.grid(row=0, column=1, sticky="e")

        ttk.Separator(page).grid(row=1, column=0, sticky="ew", pady=(0, SPACE_MD))
        body = ttk.Frame(page)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self.e_kunye = {}
        project = ttk.LabelFrame(body, text="Proje", padding=(14, 10))
        project.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, SPACE_SM))
        project.columnconfigure(1, weight=1)
        project_entry = self._form_entry_ekle(project, 0, "Proje adı / sahibi", "sahibi", self.e_kunye, width=60)

        location = ttk.LabelFrame(body, text="Konum", padding=(14, 10))
        location.grid(row=1, column=0, sticky="nsew", padx=(0, SPACE_XS))
        location.columnconfigure(1, weight=1)
        location_fields = [
            ("İl", "il"),
            ("İlçe", "ilce"),
            ("Mahalle / Köy", "mah"),
            ("Mevkii", "mev"),
        ]
        location_entries = [
            self._form_entry_ekle(location, row, label, key, self.e_kunye)
            for row, (label, key) in enumerate(location_fields)
        ]

        cadastral = ttk.LabelFrame(body, text="Kadastro", padding=(14, 10))
        cadastral.grid(row=1, column=1, sticky="nsew", padx=(SPACE_XS, 0))
        cadastral.columnconfigure(1, weight=1)
        cadastral_fields = [("Pafta", "paf"), ("Ada", "ada"), ("Parsel", "par")]
        cadastral_entries = [
            self._form_entry_ekle(cadastral, row, label, key, self.e_kunye)
            for row, (label, key) in enumerate(cadastral_fields)
        ]

        navigation = [project_entry, *location_entries, *cadastral_entries]
        self.form_klavye_gecisi_ekle(navigation)
        for entry in navigation:
            entry.bind("<KeyRelease>", self.kunye_durum_guncelle, add="+")
            entry.bind("<FocusOut>", self.kunye_durum_guncelle, add="+")
        self.kunye_durum_guncelle()

    def bina_blok_kolonlari(self):
        return [
            ("Blok", "blok_adi", 12),
            ("Kullanım", "kul", 18),
            ("Sınıf", "sinif", 14),
            ("Önem", "onem", 10),
            ("Malzeme", "malz", 14),
            ("Bodrum", "bod", 8),
            ("Kat", "kat", 8),
            ("Plan", "plan", 14),
            ("Hn", "yukseklik", 9),
            ("Yük. Sınıfı", "yukseklik_sinif", 12),
            ("Temel Alanı", "temel_alan", 11),
            ("B (m)", "temel_genislik", 8),
            ("İnşaat Alanı", "ins", 12),
            ("Kazı Der.", "der", 9),
            ("Temel Tipi", "tem", 14),
            ("GQE Min", "gqe_min", 9),
            ("GQE Maks", "gqe_max", 9),
            ("GQE Ort", "gqe_ort", 9),
            ("Comb Min", "comb_min", 9),
            ("Comb Maks", "comb_max", 9),
            ("Comb Ort", "comb_ort", 9),
        ]

    def bina_sonraki_blok_adi(self):
        idx = len(getattr(self, "bina_blok_data", []))
        if idx < 26:
            return f"{chr(65 + idx)} Blok"
        return f"Blok {idx + 1}"

    def bina_genel_bilgilerinden_blok(self):
        values = {key: entry.get().strip() for key, entry in getattr(self, "e_bina", {}).items()}
        values["blok_adi"] = self.bina_sonraki_blok_adi()
        return values

    def _bina_blok_secili_kaydet(self):
        idx = getattr(self, "bina_blok_secili_idx", None)
        data = getattr(self, "bina_blok_data", [])
        entries = getattr(self, "bina_blok_entries", {})
        if not isinstance(idx, int) or not 0 <= idx < len(data) or not entries:
            return
        data[idx].update({key: entry.get().strip() for key, entry in entries.items()})
        if not data[idx].get("blok_adi"):
            data[idx]["blok_adi"] = f"Blok {idx + 1}"

    def _bina_blok_listesi_yenile(self):
        if not hasattr(self, "bina_blok_listbox"):
            return
        selected = getattr(self, "bina_blok_secili_idx", None)
        previous_state = str(self.bina_blok_listbox.cget("state"))
        if previous_state == "disabled":
            self.bina_blok_listbox.configure(state="normal")
        self.bina_blok_listbox.delete(0, tk.END)
        for idx, block in enumerate(getattr(self, "bina_blok_data", [])):
            name = str(block.get("blok_adi") or f"Blok {idx + 1}")
            self.bina_blok_listbox.insert(tk.END, name)
        if isinstance(selected, int) and 0 <= selected < self.bina_blok_listbox.size():
            self.bina_blok_listbox.selection_set(selected)
            self.bina_blok_listbox.activate(selected)
        if previous_state == "disabled":
            self.bina_blok_listbox.configure(state="disabled")

    def bina_blok_satir_sec(self, row_idx):
        data = getattr(self, "bina_blok_data", [])
        if not isinstance(row_idx, int) or not 0 <= row_idx < len(data):
            return
        previous = getattr(self, "bina_blok_secili_idx", None)
        if previous != row_idx:
            self._bina_blok_secili_kaydet()
        self.bina_blok_secili_idx = row_idx
        block = data[row_idx]
        for key, entry in getattr(self, "bina_blok_entries", {}).items():
            entry.configure(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, str(block.get(key, "") or ""))
        self._bina_blok_listesi_yenile()
        self.bina_blok_listbox.selection_clear(0, tk.END)
        self.bina_blok_listbox.selection_set(row_idx)
        self.bina_blok_listbox.see(row_idx)
        self.bina_blok_modu_guncelle(create_default=False)
        self.bina_durum_guncelle()

    def bina_blok_listesi_sec(self, event=None):
        selection = self.bina_blok_listbox.curselection()
        if selection:
            self.bina_blok_satir_sec(selection[0])

    def bina_blok_detay_degisti(self, event=None):
        self._bina_blok_secili_kaydet()
        idx = getattr(self, "bina_blok_secili_idx", None)
        if isinstance(idx, int) and hasattr(self, "bina_blok_listbox") and idx < self.bina_blok_listbox.size():
            name = self.bina_blok_data[idx].get("blok_adi") or f"Blok {idx + 1}"
            self.bina_blok_listbox.delete(idx)
            self.bina_blok_listbox.insert(idx, name)
            self.bina_blok_listbox.selection_set(idx)
        self.bina_durum_guncelle()

    def bina_blok_scroll_guncelle(self):
        return

    def bina_blok_modu_guncelle(self, create_default=True):
        enabled = bool(getattr(self, "bina_coklu_blok_var", tk.BooleanVar(value=False)).get())
        state = "normal" if enabled else "disabled"
        for btn in getattr(self, "bina_blok_buttons", []):
            try:
                btn.configure(state=state)
            except Exception:
                pass
        if hasattr(self, "bina_blok_listbox"):
            self.bina_blok_listbox.configure(state=state)
        for entry in getattr(self, "bina_blok_entries", {}).values():
            try:
                entry.configure(state=state)
            except Exception:
                pass
        if enabled and create_default and not getattr(self, "bina_blok_data", []):
            self.bina_blok_satir_ekle(self.bina_genel_bilgilerinden_blok())
        self.bina_durum_guncelle()

    def bina_blok_satir_ekle(self, values=None):
        if not hasattr(self, "bina_blok_data"):
            return
        self._bina_blok_secili_kaydet()
        values = values or {"blok_adi": self.bina_sonraki_blok_adi()}
        block = {key: str(values.get(key, "") or "") for _, key, _ in self.bina_blok_kolonlari()}
        if not block.get("blok_adi"):
            block["blok_adi"] = self.bina_sonraki_blok_adi()
        self.bina_blok_data.append(block)
        self.bina_blok_rows = self.bina_blok_data
        self._bina_blok_listesi_yenile()
        self.bina_blok_satir_sec(len(self.bina_blok_data) - 1)

    def bina_bloklari_temizle(self):
        self.bina_blok_data = []
        self.bina_blok_rows = self.bina_blok_data
        self.bina_blok_secili_idx = None
        self._bina_blok_listesi_yenile()
        for entry in getattr(self, "bina_blok_entries", {}).values():
            entry.configure(state="normal")
            entry.delete(0, tk.END)

    def bina_bloklari_yukle(self, bloklar):
        self.bina_blok_data = [
            {key: str(block.get(key, "") or "") for _, key, _ in self.bina_blok_kolonlari()}
            for block in (bloklar or [])
            if isinstance(block, dict)
        ]
        self.bina_blok_rows = self.bina_blok_data
        self.bina_blok_secili_idx = None
        self._bina_blok_listesi_yenile()
        if self.bina_blok_data:
            self.bina_blok_satir_sec(0)
        else:
            for entry in getattr(self, "bina_blok_entries", {}).values():
                entry.configure(state="normal")
                entry.delete(0, tk.END)
        self.bina_blok_modu_guncelle()

    def bina_bloklari_topla(self):
        self._bina_blok_secili_kaydet()
        blocks = []
        for idx, block in enumerate(getattr(self, "bina_blok_data", [])):
            values = dict(block)
            if not values.get("blok_adi"):
                values["blok_adi"] = f"Blok {idx + 1}"
            if any(str(value).strip() for value in values.values()):
                blocks.append(values)
        return blocks

    def bina_blok_secili_satir(self):
        self._bina_blok_secili_kaydet()
        data = getattr(self, "bina_blok_data", [])
        if not data:
            return None, None
        idx = getattr(self, "bina_blok_secili_idx", None)
        if idx is None or idx < 0 or idx >= len(data):
            idx = len(data) - 1
        return idx, data[idx]

    def bina_blok_ekle(self):
        self.bina_blok_satir_ekle({"blok_adi": self.bina_sonraki_blok_adi()})

    def bina_blok_genelden_ekle(self):
        self.bina_blok_satir_ekle(self.bina_genel_bilgilerinden_blok())

    def bina_blok_cogalt(self):
        idx, block = self.bina_blok_secili_satir()
        if block is None:
            self.bina_blok_ekle()
            return
        values = dict(block)
        values["blok_adi"] = self.bina_sonraki_blok_adi()
        self.bina_blok_satir_ekle(values)

    def bina_blok_sil(self):
        idx, block = self.bina_blok_secili_satir()
        if block is None:
            messagebox.showinfo("Blok Sil", "Silinecek blok satırı yok.")
            return
        if not messagebox.askyesno("Blok Sil", "Seçili blok satırı silinsin mi?"):
            return
        del self.bina_blok_data[idx]
        self.bina_blok_rows = self.bina_blok_data
        self.bina_blok_secili_idx = None
        self._bina_blok_listesi_yenile()
        if self.bina_blok_data:
            self.bina_blok_satir_sec(min(idx, len(self.bina_blok_data) - 1))
        else:
            for entry in self.bina_blok_entries.values():
                entry.configure(state="normal")
                entry.delete(0, tk.END)
            self.bina_blok_modu_guncelle(create_default=False)

    def bina_durum_guncelle(self, event=None):
        general_values = {key: entry.get().strip() for key, entry in getattr(self, "e_bina", {}).items()}
        filled = sum(bool(value) for value in general_values.values())
        multi = bool(getattr(self, "bina_coklu_blok_var", tk.BooleanVar(value=False)).get())
        blocks = getattr(self, "bina_blok_data", [])
        if multi and not blocks:
            text = f"{filled}/{len(general_values)} genel alan dolu · Blok bilgisi eksik"
            color = COLOR_WARNING
        elif multi:
            text = f"{len(blocks)} blok · {filled}/{len(general_values)} genel alan dolu"
            color = COLOR_SUCCESS
        elif filled:
            text = f"Tek yapı · {filled}/{len(general_values)} alan dolu"
            color = COLOR_SUCCESS
        else:
            text = "Bina bilgileri bekleniyor"
            color = COLOR_TEXT_MUTED
        if hasattr(self, "bina_durum_var"):
            self.bina_durum_var.set(text)
            self.bina_durum_label.configure(foreground=color)

    def p_bina(self, p):
        page = ttk.Frame(p, padding=(16, 12))
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Bina Bilgileri", style="PageTitle.TLabel").pack(anchor="w")
        self.bina_durum_var = tk.StringVar(value="Bina bilgileri bekleniyor")
        self.bina_durum_label = ttk.Label(title_area, textvariable=self.bina_durum_var, style="Muted.TLabel")
        self.bina_durum_label.pack(anchor="w", pady=(2, 0))
        self.modern_button(
            header,
            "Uygula",
            command=lambda: self.form_verilerini_uygula("Bina"),
            role="success",
            padx=10,
            pady=5,
        ).grid(row=0, column=1, sticky="e")
        ttk.Separator(page).grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))

        self.bina_notebook = ttk.Notebook(page)
        self.bina_notebook.grid(row=2, column=0, sticky="nsew")
        self.bina_general_tab = ttk.Frame(self.bina_notebook)
        self.bina_blocks_tab = ttk.Frame(self.bina_notebook, padding=(10, 8))
        self.bina_notebook.add(self.bina_general_tab, text="Genel Yapı Bilgileri")
        self.bina_notebook.add(self.bina_blocks_tab, text="Çoklu Bloklar")

        main_p, _ = self.scrollable_page(self.bina_general_tab, padding=(10, 8))
        main_p.columnconfigure(0, weight=1)
        self.e_bina = {}

        def add_general_fields(parent, fields):
            parent.columnconfigure(1, weight=1)
            parent.columnconfigure(3, weight=1)
            entries = []
            for index, (label, key) in enumerate(fields):
                row = index // 2
                col = (index % 2) * 2
                ttk.Label(parent, text=label).grid(
                    row=row,
                    column=col,
                    sticky="e",
                    padx=(SPACE_SM, SPACE_XS),
                    pady=SPACE_XS,
                )
                entry = UndoRedoEntry(parent, width=24)
                entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, SPACE_SM), pady=SPACE_XS)
                self.e_bina[key] = entry
                entries.append(entry)
            return entries

        identity = ttk.LabelFrame(main_p, text="Yapı Tanımı", padding=(10, 8))
        identity.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        identity_fields = [
            ("Kullanım amacı", "kul"),
            ("Kullanım sınıfı", "sinif"),
            ("Önem katsayısı", "onem"),
            ("Yapı malzemesi", "malz"),
            ("Bodrum kat adedi", "bod"),
            ("Toplam kat adedi", "kat"),
        ]
        general_entries = add_general_fields(identity, identity_fields)

        geometry = ttk.LabelFrame(main_p, text="Geometri ve Temel", padding=(10, 8))
        geometry.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        geometry_fields = [
            ("Plan boyutları", "plan"),
            ("Yapı yüksekliği (Hn)", "yukseklik"),
            ("Bina yükseklik sınıfı", "yukseklik_sinif"),
            ("Temel alanı (m²)", "temel_alan"),
            ("Toplam inşaat alanı (m²)", "ins"),
            ("Olası kazı derinliği (m)", "der"),
            ("Temel tipi", "tem"),
            ("Yerel zemin sınıfı", "ysinif"),
            ("Etkili temel genişliği B (m)", "temel_genislik"),
        ]
        general_entries.extend(add_general_fields(geometry, geometry_fields))

        loads = ttk.LabelFrame(main_p, text="Temel Zeminine Aktarılan En Yükler (t/m²)", padding=(10, 8))
        loads.grid(row=2, column=0, sticky="ew")
        load_frame = ttk.Frame(loads)
        load_frame.pack(anchor="center")
        for column, text in enumerate(("Yük tipi", "Min", "Maks", "Ortalama")):
            ttk.Label(load_frame, text=text, font=FONT_UI_BODY_BOLD).grid(row=0, column=column, padx=SPACE_SM)
        load_entries = []
        load_specs = [
            ("G+Q+E", ("gqe_min", "gqe_max", "gqe_ort")),
            ("1.4G+1.6Q", ("comb_min", "comb_max", "comb_ort")),
        ]
        for row, (label, keys) in enumerate(load_specs, start=1):
            ttk.Label(load_frame, text=label).grid(row=row, column=0, padx=SPACE_SM, pady=SPACE_XS)
            for column, key in enumerate(keys, start=1):
                entry = UndoRedoEntry(load_frame, width=12)
                entry.grid(row=row, column=column, padx=SPACE_XS, pady=SPACE_XS)
                self.e_bina[key] = entry
                load_entries.append(entry)
        general_entries.extend(load_entries)
        self.form_klavye_gecisi_ekle(general_entries)
        for entry in general_entries:
            entry.bind("<KeyRelease>", self.bina_durum_guncelle, add="+")
            entry.bind("<FocusOut>", self.bina_durum_guncelle, add="+")

        self.bina_coklu_blok_var = tk.BooleanVar(value=False)
        self.bina_blok_data = []
        self.bina_blok_rows = self.bina_blok_data
        self.bina_blok_secili_idx = None
        self.bina_blok_buttons = []
        self.bina_blok_entries = {}

        block_toolbar = ttk.Frame(self.bina_blocks_tab)
        block_toolbar.pack(fill="x", pady=(0, SPACE_SM))
        ttk.Checkbutton(
            block_toolbar,
            text="Projede birden fazla blok var",
            variable=self.bina_coklu_blok_var,
            command=self.bina_blok_modu_guncelle,
        ).pack(side="left")
        ttk.Label(block_toolbar, textvariable=self.bina_durum_var, style="Muted.TLabel").pack(side="right")

        block_paned = tk.PanedWindow(self.bina_blocks_tab, orient=tk.HORIZONTAL, bg=COLOR_BG, sashwidth=5, bd=0)
        block_paned.pack(fill="both", expand=True)
        list_panel = self.ui_surface_frame(block_paned, padding=SPACE_SM)
        block_paned.add(list_panel, width=230, minsize=190, stretch="never")
        ttk.Label(list_panel, text="Bloklar", font=FONT_UI_SECTION).pack(anchor="w", pady=(0, SPACE_SM))
        self.bina_blok_listbox = tk.Listbox(
            list_panel,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            selectbackground=COLOR_PRIMARY,
            selectforeground="white",
            activestyle="none",
            font=FONT_UI_BODY,
        )
        self.bina_blok_listbox.pack(fill="both", expand=True)
        self.bina_blok_listbox.bind("<<ListboxSelect>>", self.bina_blok_listesi_sec)
        list_actions = tk.Frame(list_panel, bg=COLOR_SURFACE)
        list_actions.pack(fill="x", pady=(SPACE_SM, 0))
        button_specs = [
            ("Yeni", self.bina_blok_ekle, "primary", False),
            ("Genelden", self.bina_blok_genelden_ekle, "secondary", True),
            ("Çoğalt", self.bina_blok_cogalt, "secondary", True),
            ("Sil", self.bina_blok_sil, "danger", True),
        ]
        for index, (text, command, role, outline) in enumerate(button_specs):
            btn = self.modern_button(
                list_actions,
                text,
                command=command,
                role=role,
                outline=outline,
                padx=6,
                pady=4,
            )
            btn.grid(row=index // 2, column=index % 2, sticky="ew", padx=2, pady=2)
            list_actions.columnconfigure(index % 2, weight=1)
            self.bina_blok_buttons.append(btn)

        detail_host = ttk.Frame(block_paned)
        block_paned.add(detail_host, minsize=610, stretch="always")
        detail, _ = self.scrollable_page(detail_host, padding=(12, 8))
        detail.columnconfigure(1, weight=1)
        detail.columnconfigure(3, weight=1)
        ttk.Label(detail, text="Seçili Blok Bilgileri", style="SectionTitle.TLabel").grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(0, SPACE_SM),
        )
        block_navigation = []
        for index, (label, key, width) in enumerate(self.bina_blok_kolonlari()):
            row = 1 + index // 2
            col = (index % 2) * 2
            ttk.Label(detail, text=label).grid(
                row=row,
                column=col,
                sticky="e",
                padx=(SPACE_SM, SPACE_XS),
                pady=SPACE_XS,
            )
            entry = UndoRedoEntry(detail, width=max(12, min(width, 24)))
            entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, SPACE_SM), pady=SPACE_XS)
            entry.bind("<KeyRelease>", self.bina_blok_detay_degisti, add="+")
            entry.bind("<FocusOut>", self.bina_blok_detay_degisti, add="+")
            self.bina_blok_entries[key] = entry
            block_navigation.append(entry)
        self.form_klavye_gecisi_ekle(block_navigation)
        self.bina_blok_modu_guncelle()
        self.bina_durum_guncelle()

    def arazi_durum_guncelle(self, event=None):
        values = {key: widget.get().strip() for key, widget in self.e_arazi.items()}
        warnings = []
        invalid_numeric = []
        for key in ("egim", "min", "max", "ort", "pga"):
            if values.get(key) and not self._form_sayi_mi(values[key]):
                invalid_numeric.append(key)
        if invalid_numeric:
            warnings.append("Sayısal alanları kontrol edin")

        min_value = float(values["min"].replace(",", ".")) if self._form_sayi_mi(values.get("min")) else None
        max_value = float(values["max"].replace(",", ".")) if self._form_sayi_mi(values.get("max")) else None
        avg_value = float(values["ort"].replace(",", ".")) if self._form_sayi_mi(values.get("ort")) else None
        if min_value is not None and max_value is not None and min_value > max_value:
            warnings.append("Min kot, maks kotu aşıyor")
        if avg_value is not None and min_value is not None and max_value is not None and not min_value <= avg_value <= max_value:
            warnings.append("Ortalama kot aralık dışında")
        if bool(values.get("alan_y")) != bool(values.get("alan_x")):
            warnings.append("Merkez koordinatı eksik")

        required_missing = [key for key in ("zemin", "kategori") if not values.get(key)]
        if required_missing:
            warnings.append("Zemin grubu veya kategori eksik")

        for key, widget in self.e_arazi.items():
            if isinstance(widget, UndoRedoEntry):
                warning = key in invalid_numeric or key in required_missing
                widget.configure(style="Warning.TEntry" if warning else "Valid.TEntry")

        filled = sum(bool(value) for value in values.values())
        if warnings:
            self.arazi_durum_var.set(f"{filled}/{len(values)} alan dolu · {warnings[0]}")
            self.arazi_durum_label.configure(foreground=COLOR_WARNING)
        else:
            self.arazi_durum_var.set(f"{filled}/{len(values)} alan dolu · Arazi bilgileri hazır")
            self.arazi_durum_label.configure(foreground=COLOR_SUCCESS)

    def p_arazi(self, p):
        page, _ = self.scrollable_page(p, padding=(16, 12))
        page.columnconfigure(0, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        header.columnconfigure(0, weight=1)
        title_area = ttk.Frame(header)
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text="Arazi Bilgileri", style="PageTitle.TLabel").pack(anchor="w")
        self.arazi_durum_var = tk.StringVar(value="Arazi bilgileri bekleniyor")
        self.arazi_durum_label = ttk.Label(title_area, textvariable=self.arazi_durum_var, style="Muted.TLabel")
        self.arazi_durum_label.pack(anchor="w", pady=(2, 0))
        self.modern_button(
            header,
            "Uygula",
            command=lambda: self.form_verilerini_uygula("Arazi"),
            role="success",
            padx=10,
            pady=5,
        ).grid(row=0, column=1, sticky="e")

        ttk.Separator(page).grid(row=1, column=0, sticky="ew", pady=(0, SPACE_MD))
        body = ttk.Frame(page)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self.e_arazi = {}

        terrain = ttk.LabelFrame(body, text="Arazi ve Kotlar", padding=(14, 10))
        terrain.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_XS))
        terrain.columnconfigure(1, weight=1)
        terrain_fields = [
            ("Eğim yönü", "yon"),
            ("Eğim derecesi", "egim"),
            ("Minimum kot", "min"),
            ("Maksimum kot", "max"),
            ("Ortalama kot", "ort"),
            ("Zemin grubu (ZA-ZF)", "zemin"),
            ("PGA (g)", "pga"),
        ]
        terrain_entries = [
            self._form_entry_ekle(terrain, row, label, key, self.e_arazi)
            for row, (label, key) in enumerate(terrain_fields)
        ]

        project_area = ttk.LabelFrame(body, text="Proje Alanı", padding=(14, 10))
        project_area.grid(row=0, column=1, sticky="nsew", padx=(SPACE_XS, 0))
        project_area.columnconfigure(1, weight=1)
        area_y = self._form_entry_ekle(project_area, 0, "Merkez enlem (Y)", "alan_y", self.e_arazi)
        area_x = self._form_entry_ekle(project_area, 1, "Merkez boylam (X)", "alan_x", self.e_arazi)
        ttk.Label(project_area, text="Zemin etüt kategorisi").grid(
            row=2,
            column=0,
            sticky="e",
            padx=(0, SPACE_SM),
            pady=SPACE_XS,
        )
        self.e_arazi["kategori"] = ttk.Combobox(
            project_area,
            values=["Kategori 1", "Kategori 2", "Kategori 3"],
            state="readonly",
        )
        self.e_arazi["kategori"].grid(row=2, column=1, sticky="ew", pady=SPACE_XS)
        self.e_arazi["kategori"].set("Kategori 2")

        planning = ttk.LabelFrame(body, text="İmar Durumu ve Plan Notları", padding=(14, 10))
        planning.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(SPACE_SM, 0))
        planning.columnconfigure(1, weight=1)
        imar_alani = self._form_entry_ekle(
            planning,
            0,
            "İmar alanı",
            "imar_alani",
            self.e_arazi,
            width=50,
        )
        imar_alani.insert(0, "Konut Alanı")
        ttk.Label(planning, text="İmar durumu").grid(
            row=1,
            column=0,
            sticky="e",
            padx=(0, SPACE_SM),
            pady=SPACE_XS,
        )
        imar_secenekleri = [
            "Önlemli Alan 1.1 (ÖA-1.1) : Sıvılaşma Tehlikesi Açısından Önlemli Alanlar",
            "Önlemli Alan 2.1 (Ö.A-2.1) : Önlem Alınabilecek Nitelikte Stabilite Sorunlu Alanlar",
            "Önlemli Alan 2.2 (Ö.A-2.2) : Önlem Alınabilecek Nitelikte Kaya Düşmesi Sorunlu Alanlar",
            "Önlemli Alan 2.3 (Ö.A-2.3) : Önlem Alınabilecek Nitelikte Heyelan ve Kaya Düşmesi",
            "Önlemli Alan 5.1 (ÖA-5.1) : Önlem Alınabilecek Nitelikte Şişme, Oturma Açısından Sorunlu Alanlar",
        ]
        self.e_arazi["imar_durumu"] = ttk.Combobox(planning, values=imar_secenekleri, state="readonly")
        self.e_arazi["imar_durumu"].grid(row=1, column=1, sticky="ew", pady=SPACE_XS)
        self.e_arazi["imar_durumu"].current(0)

        navigation = [
            *terrain_entries,
            area_y,
            area_x,
            self.e_arazi["kategori"],
            imar_alani,
            self.e_arazi["imar_durumu"],
        ]
        self.form_klavye_gecisi_ekle(navigation)
        for widget in navigation:
            widget.bind("<KeyRelease>", self.arazi_durum_guncelle, add="+")
            widget.bind("<FocusOut>", self.arazi_durum_guncelle, add="+")
            if isinstance(widget, ttk.Combobox):
                widget.bind("<<ComboboxSelected>>", self.arazi_durum_guncelle, add="+")
        self.arazi_durum_guncelle()

    def guncelle_veri_objesi(self, silent=False):
        for k,e in self.e_kunye.items(): self.veri["kunye"][k]=e.get()
        for k,e in self.e_bina.items(): self.veri["bina"][k]=e.get()
        if hasattr(self, "bina_coklu_blok_var"):
            self.veri["bina"]["coklu_blok"] = bool(self.bina_coklu_blok_var.get())
            self.veri["bina"]["bloklar"] = self.bina_bloklari_topla()
        for k,e in self.e_arazi.items():
            if k == "imar_durumu" or k == "kategori": self.veri["arazi"][k] = e.get()
            else: self.veri["arazi"][k] = e.get()
        if "dosyalar" not in self.veri: self.veri["dosyalar"] = {}
        self.veri["dosyalar"]["kml_path"] = getattr(self, 'kml_path', None)
        self.veri["dosyalar"]["word_path"] = getattr(self, 'word_path', None)
        self.veri["dosyalar"]["lab_excel_path"] = getattr(self, 'lab_excel_path', None)
        self.veri["dosyalar"]["jeo_excel_path"] = getattr(self, 'jeo_excel_path', None)
        self.veri["dosyalar"]["img_yer"] = getattr(self, 'img_yer', None)
        self.veri["dosyalar"]["img_tkgm"] = getattr(self, 'img_tkgm', None)
        self.veri["dosyalar"]["img_pga"] = getattr(self, 'img_pga', None)
        self.veri["dosyalar"]["img_mjh"] = self._harita_gorsel_yolu_kaydet(getattr(self, 'img_mjh', None))
        self.veri["dosyalar"]["word_img_sondaj"] = self._harita_gorsel_yolu_kaydet(getattr(self, 'word_img_sondaj', None))
        self.veri["dosyalar"]["word_img_jeofizik"] = self._harita_gorsel_yolu_kaydet(getattr(self, 'word_img_jeofizik', None))
        if hasattr(self, "e_jeo_tar"):
            self.veri.setdefault("jeofizik", {})["tarih"] = self.e_jeo_tar.get().strip()
        self.veri.setdefault("ayarlar", {})["ek_tutanak_path"] = getattr(self, 'ek_tutanak_path', None) or self.veri.get("ayarlar", {}).get("ek_tutanak_path", "")
        self.veri.setdefault("ayarlar", {})["ek_arazi_deneyli_path"] = getattr(self, 'ek_arazi_deneyli_path', None) or self.veri.get("ayarlar", {}).get("ek_arazi_deneyli_path", "")
        self.sondaj_verilerini_kaydet(silent=silent)
    @perf_tracked("ui.fill")
    def doldur_arayuz(self):
        for k,e in self.e_kunye.items(): e.delete(0,'end'); e.insert(0, self.veri["kunye"].get(k,""))
        for k,e in self.e_bina.items(): e.delete(0,'end'); e.insert(0, self.veri["bina"].get(k,""))
        if hasattr(self, "bina_coklu_blok_var"):
            bina = self.veri.setdefault("bina", {})
            self.bina_coklu_blok_var.set(bool(bina.get("coklu_blok", False)))
            self.bina_bloklari_yukle(bina.get("bloklar", []))
        for k,e in self.e_arazi.items():
            if k == "imar_durumu" or k == "kategori": e.set(self.veri["arazi"].get(k,""))
            else: e.delete(0,'end'); e.insert(0, self.veri["arazi"].get(k,""))
        if hasattr(self, "kunye_durum_guncelle"):
            self.kunye_durum_guncelle()
        if hasattr(self, "arazi_durum_guncelle"):
            self.arazi_durum_guncelle()
            
        dosyalar = self.veri.get("dosyalar", {})
        self.kml_path = self._dosya_yolu_al(dosyalar, "kml_path", "kml", "kml_file", "kml_dosya", "kml_sinir_path", "kml_siniri_path", "kml_sınır_path")
        self.word_path = self._dosya_yolu_al(dosyalar, "word_path", "word", "word_file", "word_dosya")
        self.lab_excel_path = self._dosya_yolu_al(dosyalar, "lab_excel_path", "lab_excel", "laboratuvar_excel", "lab_dosya")
        self.jeo_excel_path = self._dosya_yolu_al(dosyalar, "jeo_excel_path", "jeofizik_excel", "jeo_excel")
        self.img_yer = self._dosya_yolu_al(dosyalar, "img_yer", "yerbuldurur_img", "yerbuldurur")
        self.img_tkgm = self._dosya_yolu_al(dosyalar, "img_tkgm", "tkgm_img", "tkgm")
        self.img_pga = self._dosya_yolu_al(dosyalar, "img_pga", "pga_img", "pga")
        self.img_mjh = self._harita_gorsel_yolu_al(dosyalar, "img_mjh", "mjh_img", "mjh")
        self.word_img_sondaj = self._harita_gorsel_yolu_al(dosyalar, "word_img_sondaj", "img_sondaj", "sondaj_haritasi")
        self.word_img_jeofizik = self._harita_gorsel_yolu_al(dosyalar, "word_img_jeofizik", "img_jeofizik", "jeofizik_haritasi")
        self.ek_tutanak_path = self.veri.get("ayarlar", {}).get("ek_tutanak_path")
        self.ek_arazi_deneyli_path = self.veri.get("ayarlar", {}).get("ek_arazi_deneyli_path")
        self.ayarlari_uygula()
        if hasattr(self, "e_jeo_tar"):
            self.e_jeo_tar.delete(0, "end")
            self.e_jeo_tar.insert(0, self.veri.get("jeofizik", {}).get("tarih", ""))
        
        self.kml_etiket_guncelle()
        if hasattr(self, "rapor_sablon_etiketini_guncelle"):
            self.rapor_sablon_etiketini_guncelle()
        if hasattr(self, 'lbl_lab'):
            self.lbl_lab.config(text=os.path.basename(self.lab_excel_path) if self.lab_excel_path else "Henüz laboratuvar dosyası seçilmedi", foreground=COLOR_SUCCESS if self.lab_excel_path else "red")
            if hasattr(self, "_lab_label_guncelle"):
                self._lab_label_guncelle()
        if hasattr(self, 'lbl_jeo_excel'):
            self.lbl_jeo_excel.config(text=os.path.basename(self.jeo_excel_path) if self.jeo_excel_path else "Henüz jeofizik dosyası seçilmedi", foreground=COLOR_SUCCESS if self.jeo_excel_path else "red")
            if hasattr(self, "_jeofizik_label_guncelle"):
                self._jeofizik_label_guncelle()
        if hasattr(self, 'lbl_yer'):
            self.lbl_yer.config(text=os.path.basename(self.img_yer) if self.img_yer else "-", foreground=COLOR_SUCCESS if self.img_yer else "#333")
        if hasattr(self, 'lbl_tkgm'):
            self.lbl_tkgm.config(text=os.path.basename(self.img_tkgm) if self.img_tkgm else "-", foreground=COLOR_SUCCESS if self.img_tkgm else "#333")
        if hasattr(self, 'lbl_pga'):
            self.lbl_pga.config(text=os.path.basename(self.img_pga) if self.img_pga else "-", foreground=COLOR_SUCCESS if self.img_pga else "#333")
        if hasattr(self, 'lbl_mjh'):
            self.lbl_mjh.config(text=os.path.basename(self.img_mjh) if self.img_mjh else "-", foreground=COLOR_SUCCESS if self.img_mjh else "#333")
        if hasattr(self, "rapor_etiketlerini_guncelle"):
            self.rapor_etiketlerini_guncelle()
            
        self.sondaj_tablosunu_ciz(); self.jeo_yenile(); self.mt_yenile()
        self.ozet_yenile(collect=False)

if __name__ == "__main__":
    root = tk.Tk()
    app = RaporRobotuArayuz(root)
    root.mainloop()


