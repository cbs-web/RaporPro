# Dosya: RaporPro/arayuz.py
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Canvas, Scrollbar, Listbox, Toplevel, Frame
import datetime
import json
import os
import threading

from harita_cikti import eski_paylasimli_temp_harita_yolu_mu
from sabitler import *
from yardimcilar import *
from performans import ERROR_LOG_PATH, PERF_LOG_PATH, log_exception, perf_timer, perf_tracked
from proje_motoru import (
    format_hesap_ozeti,
    hesap_ozeti,
    proje_saglik_ozeti,
    rapor_onizleme_metni,
)
from proje_arsiv import (
    arsiv_kaydi_ekle,
    arsiv_kaydi_sil,
    arsiv_kayitlari_yukle,
    biten_isler_kml_yaz,
    proje_merkez_koordinati,
)
from raporlama import raporla
from workbook_motoru import (
    WORKBOOK_SHEET_DEFS,
    build_initial_rows as wb_build_initial_rows,
    yeni_sondaj_sablonu as wb_yeni_sondaj_sablonu,
)
from widgets import UndoRedoEntry

from harita_motoru import TopluHarita
from kalite_kontrol import (
    analyze_word_template,
    backup_project_file,
    build_preflight_report,
    format_preflight_report,
    format_template_analysis,
    get_supported_tags,
)
from ui_cikti import CiktiMerkeziMixin
from ui_haritalar import HaritalarSekmesiMixin
from ui_jeofizik import JeofizikMixin
from ui_karot_tcr import KarotTCRMixin
from ui_kesit import KesitCizimMixin
from ui_kontrol import KontrolPaneliMixin
from ui_rapor import RaporSekmesiMixin
from ui_spt_okuma import SPTOkumaMixin
from ui_sondaj import SondajMixin
from ui_workbook import WorkbookMixin
from arayuz_temel import ArayuzTemelMixin
from arayuz_proje import ArayuzProjeMixin
from arayuz_ozet import ArayuzOzetMixin
from arayuz_araclar import ArayuzAraclarMixin

APP_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOSAVE_DIR = os.path.join(APP_DIR, "autosave")
AUTOSAVE_PATH = os.path.join(AUTOSAVE_DIR, "raporpro_autosave.json")
RECENT_PROJECTS_PATH = os.path.join(APP_DIR, "recent_projects.json")
# ============================================================================
# ÖZEL SPT VERİ GİRİŞ PENCERESİ (OTOMATİK HESAPLAMA VE DERİNLİK ARTIŞI)
class RaporRobotuArayuz(ArayuzTemelMixin, ArayuzProjeMixin, ArayuzOzetMixin, ArayuzAraclarMixin, RaporSekmesiMixin, HaritalarSekmesiMixin, CiktiMerkeziMixin, KontrolPaneliMixin, KesitCizimMixin, WorkbookMixin, SPTOkumaMixin, KarotTCRMixin, SondajMixin, JeofizikMixin):
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
        self.autosave_status_var = tk.StringVar(value="Kayıt durumu: bekleniyor")
        self.recent_projects = self.recent_projects_yukle()
        
        self.root.bind_all("<Button-1>", self.track_focus, add="+")
        self.sondaj_ui_rows = [] 
        self.kur_arayuz()
        self.kur_kisayollar()
        self.doldur_arayuz()
        
        if self.aktif_dosya_yolu:
            self.root.title(f"Zemin Rapor Pro - {os.path.basename(self.aktif_dosya_yolu)}")
            self.set_status(f"Yüklendi: {self.aktif_dosya_yolu}")
        else:
            self.set_status("Yeni Proje (Kaydedilmemiş)")
        if getattr(self, "bootstrap_theme_active", False):
            self.set_status(f"Modern tema etkin: {self.bootstrap_theme_name}", level="success")
        if getattr(self, "_startup_load_error", None):
            self.set_status(f"Varsayılan proje okunamadı: {self._startup_load_error}", level="warning")
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
        self._closing = True
        self.autosave_zamanlayici_iptal()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

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
            self.veri_eksikleri_tamamla(veri, self.varsayilan_veri_olustur())
            self.veri = veri
            self.aktif_dosya_yolu = payload.get("active_path")
            self.doldur_arayuz()
            self.set_status(f"Otomatik kayıt yüklendi: {payload.get('saved_at', '-')}", level="success")
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
            ("Final Kontrol", self.final_kontrol_penceresi),
            ("Rapor Ön Kontrol", self.rapor_on_kontrol),
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

    def p_kunye(self, p):
        f = ttk.LabelFrame(p, text="Proje Künyesi", padding="20")
        f.pack(fill="x", padx=10, pady=10)
        self.e_kunye = {}
        fields = [("Proje Sahibi:", "sahibi"), ("İl:", "il"), ("İlçe:", "ilce"), ("Mahalle:", "mah"), ("Mevkii:", "mev"), ("Pafta:", "paf"), ("Ada:", "ada"), ("Parsel:", "par")]
        for i, (lbl, key) in enumerate(fields):
            r = i // 2; c = (i % 2) * 2
            ttk.Label(f, text=lbl).grid(row=r, column=c, sticky="e", padx=5, pady=8)
            e = UndoRedoEntry(f, width=30); e.grid(row=r, column=c+1, sticky="w", padx=5, pady=8)
            self.e_kunye[key] = e

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
        idx = len(getattr(self, "bina_blok_rows", []))
        if idx < 26:
            return f"{chr(65 + idx)} Blok"
        return f"Blok {idx + 1}"

    def bina_genel_bilgilerinden_blok(self):
        values = {key: entry.get().strip() for key, entry in getattr(self, "e_bina", {}).items()}
        values["blok_adi"] = self.bina_sonraki_blok_adi()
        return values

    def bina_blok_satir_sec(self, row_idx):
        self.bina_blok_secili_idx = row_idx
        for idx, row in enumerate(getattr(self, "bina_blok_rows", [])):
            bg = "#D6EAF8" if idx == row_idx else COLOR_BG
            try:
                row["label"].configure(background=bg)
            except Exception:
                pass

    def bina_blok_scroll_guncelle(self):
        if hasattr(self, "bina_blok_canvas"):
            self.bina_blok_canvas.update_idletasks()
            self.bina_blok_canvas.configure(scrollregion=self.bina_blok_canvas.bbox("all"))

    def bina_blok_modu_guncelle(self):
        enabled = bool(getattr(self, "bina_coklu_blok_var", tk.BooleanVar(value=False)).get())
        state = "normal" if enabled else "disabled"
        for btn in getattr(self, "bina_blok_buttons", []):
            try:
                btn.configure(state=state)
            except Exception:
                pass
        for row in getattr(self, "bina_blok_rows", []):
            for entry in row.get("entries", {}).values():
                try:
                    entry.configure(state=state)
                except Exception:
                    pass
        if enabled and not getattr(self, "bina_blok_rows", []):
            self.bina_blok_satir_ekle(self.bina_genel_bilgilerinden_blok())

    def bina_blok_satir_ekle(self, values=None):
        if not hasattr(self, "bina_blok_frame"):
            return
        values = values or {"blok_adi": self.bina_sonraki_blok_adi()}
        row_idx = len(self.bina_blok_rows)
        grid_row = row_idx + 1
        row_label = ttk.Label(self.bina_blok_frame, text=str(row_idx + 1), width=4, anchor="center")
        row_label.grid(row=grid_row, column=0, padx=1, pady=2, sticky="nsew")
        entries = {}
        widgets = [row_label]
        for col_idx, (_, key, width) in enumerate(self.bina_blok_kolonlari(), start=1):
            entry = UndoRedoEntry(self.bina_blok_frame, width=width)
            entry.insert(0, str(values.get(key, "") or ""))
            entry.grid(row=grid_row, column=col_idx, padx=1, pady=2, sticky="nsew")
            entry.bind("<FocusIn>", lambda event, idx=row_idx: self.bina_blok_satir_sec(idx), add="+")
            entry.bind("<Button-1>", lambda event, idx=row_idx: self.bina_blok_satir_sec(idx), add="+")
            entries[key] = entry
            widgets.append(entry)
        self.bina_blok_rows.append({"entries": entries, "label": row_label, "widgets": widgets})
        self.bina_blok_satir_sec(row_idx)
        self.bina_blok_modu_guncelle()
        self.bina_blok_scroll_guncelle()

    def bina_bloklari_temizle(self):
        for row in getattr(self, "bina_blok_rows", []):
            for widget in row.get("widgets", []):
                try:
                    widget.destroy()
                except Exception:
                    pass
        self.bina_blok_rows = []
        self.bina_blok_secili_idx = None
        self.bina_blok_scroll_guncelle()

    def bina_bloklari_yukle(self, bloklar):
        self.bina_bloklari_temizle()
        for blok in bloklar or []:
            if isinstance(blok, dict):
                self.bina_blok_satir_ekle(blok)
        self.bina_blok_modu_guncelle()

    def bina_bloklari_topla(self):
        bloklar = []
        for idx, row in enumerate(getattr(self, "bina_blok_rows", [])):
            values = {key: entry.get().strip() for key, entry in row.get("entries", {}).items()}
            if not values.get("blok_adi"):
                values["blok_adi"] = f"Blok {idx + 1}"
            if any(str(value).strip() for value in values.values()):
                bloklar.append(values)
        return bloklar

    def bina_blok_secili_satir(self):
        rows = getattr(self, "bina_blok_rows", [])
        if not rows:
            return None, None
        idx = getattr(self, "bina_blok_secili_idx", None)
        if idx is None or idx < 0 or idx >= len(rows):
            idx = len(rows) - 1
        return idx, rows[idx]

    def bina_blok_ekle(self):
        self.bina_blok_satir_ekle({"blok_adi": self.bina_sonraki_blok_adi()})

    def bina_blok_genelden_ekle(self):
        self.bina_blok_satir_ekle(self.bina_genel_bilgilerinden_blok())

    def bina_blok_cogalt(self):
        idx, row = self.bina_blok_secili_satir()
        if row is None:
            self.bina_blok_ekle()
            return
        values = {key: entry.get().strip() for key, entry in row["entries"].items()}
        values["blok_adi"] = self.bina_sonraki_blok_adi()
        self.bina_blok_satir_ekle(values)

    def bina_blok_sil(self):
        idx, row = self.bina_blok_secili_satir()
        if row is None:
            messagebox.showinfo("Blok Sil", "Silinecek blok satırı yok.")
            return
        if not messagebox.askyesno("Blok Sil", "Seçili blok satırı silinsin mi?"):
            return
        bloklar = self.bina_bloklari_topla()
        if idx < len(bloklar):
            del bloklar[idx]
        self.bina_bloklari_yukle(bloklar)

    def p_bina(self, p):
        main_p = ttk.Frame(p); main_p.pack(fill="both", expand=True, padx=10, pady=10)
        self.e_bina = {}
        top_p = ttk.Frame(main_p); top_p.pack(fill="x")
        left_f = ttk.LabelFrame(top_p, text="Yapı Genel Bilgileri", padding="15"); left_f.pack(side="left", fill="both", expand=True, padx=(0,5))
        fields_l = [("Bina Kullanım Amacı", "kul"), ("Bina Kullanım Sınıfı", "sinif"), ("Bina Önem Katsayısı", "onem"), ("Yapı Malzemesi", "malz"), ("Bodrum Kat Adedi", "bod"), ("Toplam Kat Adedi", "kat"), ("Plan Boyutları", "plan"), ("Yapı Yüksekliği (Hn)", "yukseklik"), ("Bina Yükseklik Sınıfı", "yukseklik_sinif")]
        for i, (l, k) in enumerate(fields_l):
            ttk.Label(left_f, text=l).grid(row=i, column=0, sticky="e", padx=5, pady=5)
            e = UndoRedoEntry(left_f, width=25); e.grid(row=i, column=1, sticky="ew", padx=5, pady=5)
            self.e_bina[k] = e
        right_f = ttk.LabelFrame(top_p, text="Alanlar ve Yükler", padding="15"); right_f.pack(side="right", fill="both", expand=True, padx=(5,0))
        fields_r = [
            ("Temel Alanı (m2)", "temel_alan"),
            ("Toplam İnşaat Alanı (m2)", "ins"),
            ("Olası Kazı Derinliği (m)", "der"),
            ("Temel Tipi", "tem"),
            ("Yerel Zemin Sınıfı", "ysinif"),
        ]
        for i, (l, k) in enumerate(fields_r):
            ttk.Label(right_f, text=l).grid(row=i, column=0, sticky="e", padx=5, pady=5)
            e = UndoRedoEntry(right_f, width=25); e.grid(row=i, column=1, sticky="ew", padx=5, pady=5)
            self.e_bina[k] = e
        load_start_row = len(fields_r)
        ttk.Separator(right_f, orient='horizontal').grid(row=load_start_row, column=0, columnspan=2, sticky="ew", pady=15)
        ttk.Label(right_f, text="Binadan Temel Zeminine Aktarılan En Yükler (t/m2)", font=("Arial", 10, "bold")).grid(row=load_start_row + 1, column=0, columnspan=2, pady=(0,10))
        load_frame = ttk.Frame(right_f); load_frame.grid(row=load_start_row + 2, column=0, columnspan=2)
        ttk.Label(load_frame, text="Yük Tipi").grid(row=0, column=0, padx=5); ttk.Label(load_frame, text="Mim").grid(row=0, column=1, padx=5); ttk.Label(load_frame, text="Maks").grid(row=0, column=2, padx=5); ttk.Label(load_frame, text="Ort.").grid(row=0, column=3, padx=5)
        ttk.Label(load_frame, text="(G+Q+E)").grid(row=1, column=0, padx=5, pady=5)
        self.e_bina["gqe_min"] = UndoRedoEntry(load_frame, width=8); self.e_bina["gqe_min"].grid(row=1, column=1, padx=5)
        self.e_bina["gqe_max"] = UndoRedoEntry(load_frame, width=8); self.e_bina["gqe_max"].grid(row=1, column=2, padx=5)
        self.e_bina["gqe_ort"] = UndoRedoEntry(load_frame, width=8); self.e_bina["gqe_ort"].grid(row=1, column=3, padx=5)
        ttk.Label(load_frame, text="1.4G+1.6Q").grid(row=2, column=0, padx=5, pady=5)
        self.e_bina["comb_min"] = UndoRedoEntry(load_frame, width=8); self.e_bina["comb_min"].grid(row=2, column=1, padx=5)
        self.e_bina["comb_max"] = UndoRedoEntry(load_frame, width=8); self.e_bina["comb_max"].grid(row=2, column=2, padx=5)
        self.e_bina["comb_ort"] = UndoRedoEntry(load_frame, width=8); self.e_bina["comb_ort"].grid(row=2, column=3, padx=5)

        blok_f = ttk.LabelFrame(main_p, text="Çoklu Blok Bilgileri", padding="10")
        blok_f.pack(fill="both", expand=True, pady=(10, 0))
        self.bina_coklu_blok_var = tk.BooleanVar(value=False)
        self.bina_blok_rows = []
        self.bina_blok_secili_idx = None
        self.bina_blok_buttons = []

        toolbar = ttk.Frame(blok_f)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(
            toolbar,
            text="Projede birden fazla blok var",
            variable=self.bina_coklu_blok_var,
            command=self.bina_blok_modu_guncelle,
        ).pack(side="left", padx=(0, 12))
        for text, command, color in [
            ("+ Blok", self.bina_blok_ekle, COLOR_ACCENT),
            ("Genelden A Blok", self.bina_blok_genelden_ekle, "#7DCEA0"),
            ("Çoğalt", self.bina_blok_cogalt, "#85C1E9"),
            ("Sil", self.bina_blok_sil, COLOR_DANGER),
        ]:
            btn = tk.Button(toolbar, text=text, command=command, bg=color, fg="white" if color in (COLOR_ACCENT, COLOR_DANGER) else "#111", font=FONT_BOLD)
            btn.pack(side="left", padx=3)
            self.bina_blok_buttons.append(btn)
        ttk.Label(toolbar, text="Kapalıysa raporda tek bina bilgileri kullanılır.").pack(side="left", padx=10)

        table_wrap = ttk.Frame(blok_f)
        table_wrap.pack(fill="both", expand=True)
        self.bina_blok_canvas = Canvas(table_wrap, bg=COLOR_BG, height=185, highlightthickness=0)
        y_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.bina_blok_canvas.yview)
        x_scroll = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.bina_blok_canvas.xview)
        self.bina_blok_frame = ttk.Frame(self.bina_blok_canvas)
        self.bina_blok_canvas.create_window((0, 0), window=self.bina_blok_frame, anchor="nw")
        self.bina_blok_canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.bina_blok_canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_wrap.rowconfigure(0, weight=1)
        table_wrap.columnconfigure(0, weight=1)
        self.bina_blok_frame.bind("<Configure>", lambda e: self.bina_blok_scroll_guncelle())

        ttk.Label(self.bina_blok_frame, text="#", width=4, anchor="center", font=FONT_BOLD).grid(row=0, column=0, padx=1, pady=2, sticky="nsew")
        for col_idx, (label, _, width) in enumerate(self.bina_blok_kolonlari(), start=1):
            ttk.Label(self.bina_blok_frame, text=label, width=width, anchor="center", font=FONT_BOLD).grid(row=0, column=col_idx, padx=1, pady=2, sticky="nsew")
        self.bina_blok_modu_guncelle()

    def p_arazi(self, p):
        f = ttk.LabelFrame(p, text="Arazi Bilgileri", padding="20")
        f.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.e_arazi = {}
        keys = ["yon","egim","min","max","ort","zemin","pga"]
        labels = ["Eğim Yönü", "Eğim Derecesi", "Min Kot", "Max Kot", "Ortalama Kot", "Zemin Grubu (ZA-ZF)", "PGA (g)"]
        row_idx = 0
        for l, k in zip(labels, keys):
            ttk.Label(f, text=l).grid(row=row_idx, column=0, sticky="e", padx=10, pady=8)
            e = UndoRedoEntry(f, width=40); e.grid(row=row_idx, column=1, sticky="w", padx=10, pady=8)
            self.e_arazi[k] = e
            row_idx += 1
            
        ttk.Label(f, text="Proje Alanı Merkezi Enlem (Y)").grid(row=row_idx, column=0, sticky="e", padx=10, pady=8)
        self.e_arazi["alan_y"] = UndoRedoEntry(f, width=40); self.e_arazi["alan_y"].grid(row=row_idx, column=1, sticky="w", padx=10, pady=8)
        row_idx += 1
        ttk.Label(f, text="Proje Alanı Merkezi Boylam (X)").grid(row=row_idx, column=0, sticky="e", padx=10, pady=8)
        self.e_arazi["alan_x"] = UndoRedoEntry(f, width=40); self.e_arazi["alan_x"].grid(row=row_idx, column=1, sticky="w", padx=10, pady=8)
        row_idx += 1

        ttk.Label(f, text="Zemin Etüt Kategorisi").grid(row=row_idx, column=0, sticky="e", padx=10, pady=8)
        self.e_arazi["kategori"] = ttk.Combobox(f, values=["Kategori 1", "Kategori 2", "Kategori 3"], width=38, state="readonly")
        self.e_arazi["kategori"].grid(row=row_idx, column=1, sticky="w", padx=10, pady=8)
        self.e_arazi["kategori"].set("Kategori 2")
        
        frame_imar = ttk.LabelFrame(p, text="İmar Durumu ve Plan Notları", padding=10)
        frame_imar.pack(fill="x", padx=20, pady=10)
        ttk.Label(frame_imar, text="İmar Alanı (Raporda parantez içinde yazılır):").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.e_arazi["imar_alani"] = UndoRedoEntry(frame_imar, width=50)
        self.e_arazi["imar_alani"].grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.e_arazi["imar_alani"].insert(0, "Konut Alanı") 
        ttk.Label(frame_imar, text="İmar Durumu (Önlemli Alanlar):").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        imar_secenekleri = ["Önlemli Alan 1.1 (ÖA-1.1) : Sıvılaşma Tehlikesi Açısından Önlemli Alanlar", "Önlemli Alan 2.1 (Ö.A-2.1) : Önlem Alınabilecek Nitelikte Stabilite Sorunlu Alanlar", "Önlemli Alan 2.2 (Ö.A-2.2) : Önlem Alınabilecek Nitelikte Kaya Düşmesi Sorunlu Alanlar", "Önlemli Alan 2.3 (Ö.A-2.3) : Önlem Alınabilecek Nitelikte Heyelan ve Kaya Düşmesi", "Önlemli Alan 5.1 (ÖA-5.1) : Önlem Alınabilecek Nitelikte Şişme, Oturma Açısından Sorunlu Alanlar"]
        self.e_arazi["imar_durumu"] = ttk.Combobox(frame_imar, values=imar_secenekleri, width=80, state="readonly")
        self.e_arazi["imar_durumu"].grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.e_arazi["imar_durumu"].current(0) 

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
        if hasattr(self, 'lbl_sab'):
            self.lbl_sab.config(text=os.path.basename(self.word_path) if self.word_path else "Henüz seçilmedi...", foreground=COLOR_SUCCESS if self.word_path else "red")
        if hasattr(self, 'lbl_lab'):
            self.lbl_lab.config(text=os.path.basename(self.lab_excel_path) if self.lab_excel_path else "Henüz laboratuvar dosyası seçilmedi", foreground=COLOR_SUCCESS if self.lab_excel_path else "red")
        if hasattr(self, 'lbl_jeo_excel'):
            self.lbl_jeo_excel.config(text=os.path.basename(self.jeo_excel_path) if self.jeo_excel_path else "Henüz jeofizik dosyası seçilmedi", foreground=COLOR_SUCCESS if self.jeo_excel_path else "red")
        if hasattr(self, 'lbl_yer'):
            self.lbl_yer.config(text=os.path.basename(self.img_yer) if self.img_yer else "-", foreground=COLOR_SUCCESS if self.img_yer else "#333")
        if hasattr(self, 'lbl_tkgm'):
            self.lbl_tkgm.config(text=os.path.basename(self.img_tkgm) if self.img_tkgm else "-", foreground=COLOR_SUCCESS if self.img_tkgm else "#333")
        if hasattr(self, 'lbl_pga'):
            self.lbl_pga.config(text=os.path.basename(self.img_pga) if self.img_pga else "-", foreground=COLOR_SUCCESS if self.img_pga else "#333")
        if hasattr(self, 'lbl_mjh'):
            self.lbl_mjh.config(text=os.path.basename(self.img_mjh) if self.img_mjh else "-", foreground=COLOR_SUCCESS if self.img_mjh else "#333")
            
        self.sondaj_tablosunu_ciz(); self.jeo_yenile(); self.mt_yenile()
        self.ozet_yenile(collect=False)

if __name__ == "__main__":
    root = tk.Tk()
    app = RaporRobotuArayuz(root)
    root.mainloop()


