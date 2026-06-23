# Dosya: RaporPro/ui_spt_okuma_pro.py
import os
import threading
from tkinter import Toplevel, messagebox, ttk

from spt_okuma_motoru import (
    kayit_normalize_et,
    normalize_sondaj_no,
    spt_gecmis_kaydet,
    spt_ayarlarini_yukle,
    yapay_zeka_ile_spt_oku,
)
from yardimcilar import safe_float


def reread_selected_with_pro(app, win, selected_record, update_selected_from_form, target_var, status_var, refresh_tree, load_detail):
    kayit = update_selected_from_form(silent=True)
    record = selected_record()
    if not record or not kayit:
        messagebox.showwarning("Gemini Pro Tekrar Oku", "Önce tekrar okutulacak satırı seçin.")
        return
    source_path = kayit.kaynak_yolu
    if not source_path or not os.path.exists(source_path):
        messagebox.showwarning("Gemini Pro Tekrar Oku", "Bu satırda tekrar okutulacak kaynak fotoğraf yok.")
        return
    if os.path.splitext(source_path)[1].lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        messagebox.showwarning("Gemini Pro Tekrar Oku", "Tekrar okuma için kaynak bir fotoğraf olmalı.")
        return
    ayarlar = spt_ayarlarini_yukle()
    if not ayarlar.get("gemini_api_key"):
        messagebox.showwarning("Gemini Pro Tekrar Oku", "Gemini API anahtarı bulunamadı. SPT Merkezi > Ayarlar kısmını kontrol edin.")
        return
    progress_win = Toplevel(win)
    app.pencere_hazirla(progress_win, "Gemini Pro Tekrar Oku", "460x150", (420, 130), modal=False)
    ttk.Label(progress_win, text="Seçili satır Gemini Pro ile tekrar okunuyor...", padding=12).pack(fill="x")
    progress = ttk.Progressbar(progress_win, mode="indeterminate")
    progress.pack(fill="x", padx=12, pady=8)
    progress.start(12)

    def finish(raw_items=None, hata=None):
        if progress_win.winfo_exists():
            progress_win.destroy()
        if hata:
            messagebox.showerror("Gemini Pro Tekrar Oku", f"Tekrar okuma tamamlanamadı:\n{hata}")
            return
        normalized = []
        for item in raw_items or []:
            item = dict(item)
            item["kaynak"] = kayit.kaynak or os.path.basename(source_path)
            item["kaynak_yolu"] = source_path
            normalized.append(kayit_normalize_et(item, kayit.sondaj_no or target_var.get()))
        if not normalized:
            messagebox.showwarning("Gemini Pro Tekrar Oku", "Gemini Pro bu fotoğraftan SPT satırı okuyamadı.")
            return
        old_depth = safe_float(kayit.derinlik)
        if old_depth > 0:
            chosen = min(normalized, key=lambda item: abs(safe_float(item.derinlik) - old_depth) if safe_float(item.derinlik) > 0 else 9999)
        else:
            chosen = normalized[0]
        chosen.sondaj_no = chosen.sondaj_no or kayit.sondaj_no or target_var.get()
        chosen.sondaj_no = normalize_sondaj_no(chosen.sondaj_no, target_var.get())
        chosen.kaynak = kayit.kaynak or chosen.kaynak
        chosen.kaynak_yolu = source_path
        previous = kayit.to_dict()
        record["kayit"] = chosen
        record["include"] = True
        spt_gecmis_kaydet("gemini_pro_tekrar_okundu", chosen, {"onceki": previous})
        refresh_tree()
        load_detail(record)
        status_var.set("Seçili satır Gemini Pro ile tekrar okundu.")

    def worker():
        try:
            raw_items = yapay_zeka_ile_spt_oku(source_path, ayarlar=ayarlar, motor_zorla="gemini_pro", timeout=60)
            app.root.after(0, lambda: finish(raw_items=raw_items))
        except Exception as exc:
            app.root.after(0, lambda: finish(hata=exc))

    threading.Thread(target=worker, daemon=True).start()
