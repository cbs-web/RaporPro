# Dosya: RaporPro/ui_proje_surumleri.py
"""Proje surum gecmisi ve karsilastirma arayuzu."""

from __future__ import annotations

import copy
import datetime
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from performans import log_exception
from proje_surumleri import (
    degisiklik_ozeti,
    proje_ozeti,
    proje_ozeti_metni,
    proje_verilerini_karsilastir,
    surum_kaydi_olustur,
    surum_verisi_yukle,
    surumleri_listele,
)
from sabitler import COLOR_DANGER, COLOR_PRIMARY, FONT_BOLD, FONT_HEADER


_DEGISIKLIK_TURU = {
    "added": "Eklendi",
    "removed": "Silindi",
    "changed": "Değişti",
}

_FILTRE_TURU = {
    "Tümü": None,
    "Eklenenler": "added",
    "Silinenler": "removed",
    "Değişenler": "changed",
}


def _tarih_goster(value):
    try:
        parsed = datetime.datetime.fromisoformat(str(value))
        return parsed.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(value or "-")


def _tarih_sirala(value, current=False):
    if current:
        return datetime.datetime.max
    try:
        return datetime.datetime.fromisoformat(str(value))
    except Exception:
        return datetime.datetime.min


class ProjeSurumleriMixin:
    def _surum_gecmisi_projesini_hazirla(self):
        if self.aktif_dosya_yolu:
            return True
        save_now = messagebox.askyesno(
            "Sürüm Geçmişi",
            "Sürüm geçmişi için projenin önce kaydedilmesi gerekir.\n\nProje şimdi kaydedilsin mi?",
        )
        return bool(save_now and self.proje_farkli_kaydet())

    def _surum_guncel_verisini_al(self):
        try:
            self.guncelle_veri_objesi(silent=True)
        except Exception as exc:
            log_exception("project.version.collect", exc_value=exc)
        return copy.deepcopy(self.veri)

    def proje_surumunu_calisma_alanina_yukle(self, record):
        """Bir surumu kaydetmeden arayuze uygular ve mevcut dosyayi degistirmez."""
        if self.proje_kilitli_mi():
            raise PermissionError("Kilitli projede sürüm geri yüklenemez. Önce proje kilidini kaldırın.")
        current_data = self._surum_guncel_verisini_al()
        surum_kaydi_olustur(
            self.aktif_dosya_yolu,
            current_data,
            reason="Geri yükleme öncesi çalışma kopyası",
            keep=self.get_surum_gecmisi_sayisi(),
            source="restore_guard",
        )
        loaded = surum_verisi_yukle(self.aktif_dosya_yolu, record)
        loaded, _migrasyon = self.proje_verisini_hazirla(loaded)
        self.veri = loaded
        if hasattr(self, "_proje_kontrol_hafizasini_sifirla"):
            self._proje_kontrol_hafizasini_sifirla()
        self.doldur_arayuz()
        self.proje_baslik_guncelle()
        self.set_status(
            f"Sürüm V{record.get('number', '?')} çalışma alanına yüklendi; kalıcılaştırmak için Kaydet'i kullanın.",
            level="warning",
        )
        self.set_save_indicator("Eski sürüm yüklendi: kaydedilmedi", "warning")
        return loaded

    def surum_gecmisi_penceresi(self):
        if not self._surum_gecmisi_projesini_hazirla():
            return
        existing = getattr(self, "_surum_gecmisi_win", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        win = tk.Toplevel(self.root)
        self._surum_gecmisi_win = win
        self.pencere_hazirla(win, "Proje Sürüm Geçmişi", "1320x820", (980, 650), modal=False)

        def close_window_now():
            self._surum_gecmisi_win = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        def close_window():
            self.pencere_kapat(win, callback=close_window_now)

        win.protocol("WM_DELETE_WINDOW", close_window)

        header = ttk.Frame(win, padding=(14, 12, 14, 5))
        header.pack(fill="x")
        ttk.Label(header, text="Proje Sürüm Geçmişi", font=FONT_HEADER).pack(side="left")
        ttk.Label(
            header,
            text=os.path.basename(self.aktif_dosya_yolu),
            foreground="#566573",
        ).pack(side="left", padx=14)
        ttk.Label(
            header,
            text="Geri yüklenen sürüm, Kaydet komutu verilene kadar proje dosyasını değiştirmez.",
            foreground="#566573",
        ).pack(side="right")

        action_frame = ttk.Frame(win, padding=(14, 3, 14, 7))
        action_frame.pack(fill="x")

        version_frame = ttk.LabelFrame(win, text="Sürümler", padding=8)
        version_frame.pack(fill="x", padx=14, pady=(0, 8))
        version_frame.columnconfigure(0, weight=1)
        version_frame.rowconfigure(0, weight=1)

        version_columns = ("no", "date", "reason", "change", "summary")
        version_tree = ttk.Treeview(
            version_frame,
            columns=version_columns,
            show="headings",
            selectmode="extended",
            height=9,
        )
        version_tree.heading("no", text="Sürüm")
        version_tree.heading("date", text="Tarih")
        version_tree.heading("reason", text="Kayıt nedeni")
        version_tree.heading("change", text="Değişiklik")
        version_tree.heading("summary", text="Veri özeti")
        version_tree.column("no", width=85, minwidth=70, anchor="center", stretch=False)
        version_tree.column("date", width=155, minwidth=145, anchor="center", stretch=False)
        version_tree.column("reason", width=235, minwidth=160)
        version_tree.column("change", width=105, minwidth=90, anchor="center", stretch=False)
        version_tree.column("summary", width=590, minwidth=320)
        version_scroll = ttk.Scrollbar(version_frame, orient="vertical", command=version_tree.yview)
        version_tree.configure(yscrollcommand=version_scroll.set)
        version_tree.grid(row=0, column=0, sticky="nsew")
        version_scroll.grid(row=0, column=1, sticky="ns")
        version_tree.tag_configure("current", foreground=COLOR_PRIMARY)
        version_tree.tag_configure("saved", foreground="#263238")
        version_tree.tag_configure("legacy", foreground="#6C5B7B")

        comparison_frame = ttk.LabelFrame(win, text="Sürüm Karşılaştırması", padding=8)
        comparison_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        comparison_tools = ttk.Frame(comparison_frame)
        comparison_tools.pack(fill="x", pady=(0, 7))
        comparison_summary_var = tk.StringVar(value="Karşılaştırmak için bir kayıt seçin.")
        ttk.Label(comparison_tools, textvariable=comparison_summary_var, font=FONT_BOLD).pack(side="left", fill="x", expand=True)
        ttk.Label(comparison_tools, text="Filtre:").pack(side="left", padx=(8, 4))
        filter_var = tk.StringVar(value="Tümü")
        filter_box = ttk.Combobox(
            comparison_tools,
            textvariable=filter_var,
            values=tuple(_FILTRE_TURU),
            state="readonly",
            width=13,
        )
        filter_box.pack(side="left", padx=(0, 8))
        ttk.Label(comparison_tools, text="Ara:").pack(side="left", padx=(4, 4))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(comparison_tools, textvariable=search_var, width=28)
        search_entry.pack(side="left")

        change_columns = ("type", "category", "field", "old", "new")
        change_tree_frame = ttk.Frame(comparison_frame)
        change_tree_frame.pack(fill="both", expand=True)
        change_tree_frame.columnconfigure(0, weight=1)
        change_tree_frame.rowconfigure(0, weight=1)
        change_tree = ttk.Treeview(
            change_tree_frame,
            columns=change_columns,
            show="headings",
            selectmode="browse",
            height=12,
        )
        change_tree.heading("type", text="Tür")
        change_tree.heading("category", text="Bölüm")
        change_tree.heading("field", text="Alan")
        change_tree.heading("old", text="Önce")
        change_tree.heading("new", text="Sonra")
        change_tree.column("type", width=85, minwidth=75, anchor="center", stretch=False)
        change_tree.column("category", width=145, minwidth=110, stretch=False)
        change_tree.column("field", width=330, minwidth=220)
        change_tree.column("old", width=300, minwidth=180)
        change_tree.column("new", width=300, minwidth=180)
        change_y = ttk.Scrollbar(change_tree_frame, orient="vertical", command=change_tree.yview)
        change_x = ttk.Scrollbar(change_tree_frame, orient="horizontal", command=change_tree.xview)
        change_tree.configure(yscrollcommand=change_y.set, xscrollcommand=change_x.set)
        change_tree.grid(row=0, column=0, sticky="nsew")
        change_y.grid(row=0, column=1, sticky="ns")
        change_x.grid(row=1, column=0, sticky="ew")
        change_tree.tag_configure("added", foreground="#167A3E")
        change_tree.tag_configure("removed", foreground=COLOR_DANGER)
        change_tree.tag_configure("changed", foreground="#A65E00")

        detail_var = tk.StringVar(value="Seçilen değişikliğin ayrıntısı burada gösterilir.")
        detail_label = tk.Label(
            comparison_frame,
            textvariable=detail_var,
            justify="left",
            anchor="w",
            bg="#F7F9F9",
            fg="#263238",
            relief="solid",
            bd=1,
            padx=8,
            pady=6,
            wraplength=1220,
        )
        detail_label.pack(fill="x", pady=(7, 0))

        footer = ttk.Frame(win, padding=(14, 0, 14, 12))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text="Sürümler proje klasöründeki backups alanında saklanır. Aynı içerik art arda çoğaltılmaz.",
            foreground="#566573",
        ).pack(side="left")
        self.modern_button(footer, "Kapat", command=close_window, role="neutral", padx=12).pack(side="right")

        state = {
            "records": {},
            "changes": [],
            "visible_changes": [],
            "left": "",
            "right": "",
        }

        def current_data():
            return self._surum_guncel_verisini_al()

        def row_payload(iid):
            if iid == "current":
                return current_data(), {
                    "id": "current",
                    "number": "Güncel",
                    "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "reason": "Güncel çalışma alanı",
                    "summary": proje_ozeti(current_data()),
                    "current": True,
                }
            record = state["records"].get(iid)
            if not record:
                raise KeyError("Seçilen sürüm bulunamadı")
            loaded = surum_verisi_yukle(self.aktif_dosya_yolu, record)
            loaded, _migrasyon = self.proje_verisini_hazirla(loaded)
            return loaded, record

        def render_changes(*_args):
            change_tree.delete(*change_tree.get_children())
            requested_type = _FILTRE_TURU.get(filter_var.get())
            needle = search_var.get().strip().casefold()
            visible = []
            for item in state["changes"]:
                if requested_type and item.get("type") != requested_type:
                    continue
                haystack = " ".join(
                    str(item.get(key, "")) for key in ("category", "label", "old", "new")
                ).casefold()
                if needle and needle not in haystack:
                    continue
                visible.append(item)
                kind = item.get("type", "changed")
                change_tree.insert(
                    "",
                    "end",
                    iid=f"change_{len(visible) - 1}",
                    values=(
                        _DEGISIKLIK_TURU.get(kind, kind),
                        item.get("category", ""),
                        item.get("label", ""),
                        item.get("old", ""),
                        item.get("new", ""),
                    ),
                    tags=(kind,),
                )
            state["visible_changes"] = visible
            if state["changes"] and not visible:
                detail_var.set("Seçili filtreye uyan değişiklik bulunamadı.")

        def show_comparison(left_data, right_data, left_record, right_record):
            changes = proje_verilerini_karsilastir(left_data, right_data)
            summary = degisiklik_ozeti(changes)
            left_name = "Güncel çalışma" if left_record.get("current") else f"V{left_record.get('number', '?')}"
            right_name = "Güncel çalışma" if right_record.get("current") else f"V{right_record.get('number', '?')}"
            state["changes"] = changes
            state["left"] = left_name
            state["right"] = right_name
            comparison_summary_var.set(f"{left_name} → {right_name} | {summary['text']}")
            detail_var.set(
                "Değişiklik satırı seçildiğinde eski ve yeni değerlerin tamamı burada gösterilir."
                if changes else "Seçilen iki sürüm arasında veri farkı bulunamadı."
            )
            render_changes()

        def selected_ids(include_current=True):
            ids = list(version_tree.selection())
            if not include_current:
                ids = [iid for iid in ids if iid != "current"]
            return ids

        def compare_with_current():
            ids = selected_ids(include_current=False)
            if len(ids) != 1:
                messagebox.showinfo("Sürüm Karşılaştırması", "Güncel çalışma ile karşılaştırmak için bir kayıtlı sürüm seçin.", parent=win)
                return
            try:
                old_data, old_record = row_payload(ids[0])
                new_data, new_record = row_payload("current")
                show_comparison(old_data, new_data, old_record, new_record)
            except Exception as exc:
                log_exception("project.version.compare_current", exc_value=exc)
                messagebox.showerror("Sürüm Karşılaştırması", f"Karşılaştırma yapılamadı:\n{exc}", parent=win)

        def compare_selected():
            ids = selected_ids()
            if len(ids) != 2:
                messagebox.showinfo("Sürüm Karşılaştırması", "Karşılaştırmak için tam olarak iki satır seçin.", parent=win)
                return
            try:
                payloads = [row_payload(iid) for iid in ids]
                payloads.sort(
                    key=lambda pair: _tarih_sirala(pair[1].get("created_at"), current=bool(pair[1].get("current")))
                )
                show_comparison(payloads[0][0], payloads[1][0], payloads[0][1], payloads[1][1])
            except Exception as exc:
                log_exception("project.version.compare", exc_value=exc)
                messagebox.showerror("Sürüm Karşılaştırması", f"Karşılaştırma yapılamadı:\n{exc}", parent=win)

        def refresh_versions(select_id=None):
            try:
                records = surumleri_listele(
                    self.aktif_dosya_yolu,
                    eski_yedekleri_aktar=True,
                    keep=self.get_surum_gecmisi_sayisi(),
                )
            except Exception as exc:
                log_exception("project.version.list", exc_value=exc)
                messagebox.showerror("Sürüm Geçmişi", f"Sürümler okunamadı:\n{exc}", parent=win)
                return
            version_tree.delete(*version_tree.get_children())
            current = current_data()
            version_tree.insert(
                "",
                "end",
                iid="current",
                values=("Güncel", "Şimdi", "Çalışma alanı", "-", proje_ozeti_metni(proje_ozeti(current))),
                tags=("current",),
            )
            state["records"] = {}
            for record in records:
                iid = f"version_{record.get('id')}"
                state["records"][iid] = record
                source = record.get("source")
                version_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        f"V{record.get('number', '?')}",
                        _tarih_goster(record.get("created_at")),
                        record.get("reason", "Proje kaydı"),
                        record.get("change_count", 0),
                        proje_ozeti_metni(record.get("summary", {})),
                    ),
                    tags=("legacy" if source == "legacy_backup" else "saved",),
                )
            wanted = select_id if select_id in version_tree.get_children() else "current"
            version_tree.selection_set(wanted)
            version_tree.focus(wanted)
            version_tree.see(wanted)

        def create_checkpoint():
            note = simpledialog.askstring(
                "Kontrol Noktası",
                "Bu sürüm için kısa bir açıklama yazın:",
                initialvalue="Manuel kontrol noktası",
                parent=win,
            )
            if note is None:
                return
            try:
                data = current_data()
                record, created = surum_kaydi_olustur(
                    self.aktif_dosya_yolu,
                    data,
                    reason=note.strip() or "Manuel kontrol noktası",
                    keep=self.get_surum_gecmisi_sayisi(),
                    source="checkpoint",
                )
                if created:
                    self.set_status("Manuel proje sürümü kaydedildi.", level="success")
                    refresh_versions(f"version_{record.get('id')}")
                else:
                    messagebox.showinfo("Kontrol Noktası", "Çalışma alanı son sürümle aynı; yinelenen kopya oluşturulmadı.", parent=win)
            except Exception as exc:
                log_exception("project.version.checkpoint", exc_value=exc)
                messagebox.showerror("Kontrol Noktası", f"Sürüm kaydedilemedi:\n{exc}", parent=win)

        def restore_selected():
            ids = selected_ids(include_current=False)
            if len(ids) != 1:
                messagebox.showinfo("Sürüm Geri Yükleme", "Çalışma alanına yüklemek için bir kayıtlı sürüm seçin.", parent=win)
                return
            record = state["records"].get(ids[0])
            if not record:
                return
            confirmed = messagebox.askyesno(
                "Sürüm Geri Yükleme",
                f"V{record.get('number', '?')} çalışma alanına yüklenecek.\n\n"
                "Mevcut durum önce sürüm geçmişine alınacak. Ana proje dosyası siz Kaydet demeden değişmeyecek. Devam edilsin mi?",
                parent=win,
            )
            if not confirmed:
                return
            try:
                self.proje_surumunu_calisma_alanina_yukle(record)
                refresh_versions("current")
                messagebox.showinfo(
                    "Sürüm Geri Yükleme",
                    "Seçilen sürüm çalışma alanına yüklendi. Sonucu kontrol edip kalıcılaştırmak için Proje > Kaydet komutunu kullanın.",
                    parent=win,
                )
            except Exception as exc:
                log_exception("project.version.restore", exc_value=exc)
                messagebox.showerror("Sürüm Geri Yükleme", str(exc), parent=win)

        def version_selection_changed(_event=None):
            ids = selected_ids()
            if len(ids) != 1:
                return
            iid = ids[0]
            if iid == "current":
                detail_var.set("Güncel çalışma alanı; henüz Kaydet komutu verilmemiş değişiklikleri de içerir.")
                return
            record = state["records"].get(iid, {})
            detail_var.set(
                f"V{record.get('number', '?')} | {_tarih_goster(record.get('created_at'))} | "
                f"{record.get('reason', '-')} | {record.get('change_summary', 'Değişiklik özeti yok')}"
            )

        def change_selection_changed(_event=None):
            selection = change_tree.selection()
            if not selection:
                return
            try:
                idx = int(selection[0].split("_", 1)[1])
                item = state["visible_changes"][idx]
            except Exception:
                return
            detail_var.set(
                f"{item.get('label', '')}\n"
                f"{state['left']}: {item.get('old', '-')}    →    {state['right']}: {item.get('new', '-')}"
            )

        action_buttons = [
            self.modern_button(action_frame, "Yenile", command=refresh_versions, role="secondary", padx=10),
            self.modern_button(action_frame, "Kontrol Noktası Oluştur", command=create_checkpoint, role="primary", padx=10),
            self.modern_button(action_frame, "Güncel ile Karşılaştır", command=compare_with_current, role="accent", padx=10),
            self.modern_button(action_frame, "İki Sürümü Karşılaştır", command=compare_selected, role="accent", padx=10),
            self.modern_button(action_frame, "Seçili Sürümü Çalışma Alanına Yükle", command=restore_selected, role="warning", padx=10),
        ]
        self.responsive_widget_grid(action_frame, action_buttons, min_width=190, max_cols=5, padx=4, pady=3)

        filter_var.trace_add("write", render_changes)
        search_var.trace_add("write", render_changes)
        version_tree.bind("<<TreeviewSelect>>", version_selection_changed)
        version_tree.bind("<Double-Button-1>", lambda _event: compare_with_current())
        change_tree.bind("<<TreeviewSelect>>", change_selection_changed)
        win.bind("<F5>", lambda _event: refresh_versions())
        win.bind("<Escape>", lambda _event: close_window())
        refresh_versions()
        search_entry.focus_set()
