# Dosya: RaporPro/ui_spt_okuma_pro.py
import os
from tkinter import Toplevel, messagebox, ttk

from spt_okuma_motoru import (
    kayit_normalize_et,
    normalize_sondaj_no,
    spt_gecmis_kaydet,
    spt_ayarlarini_yukle,
    yapay_zeka_ile_spt_oku,
)
from yardimcilar import safe_float


def _reread_selected_with_openai_role(
    app,
    win,
    selected_record,
    update_selected_from_form,
    target_var,
    status_var,
    refresh_tree,
    load_detail,
    *,
    motor_role,
    model_label,
    history_event,
    timeout,
):
    kayit = update_selected_from_form(silent=True)
    record = selected_record()
    if not record or not kayit:
        messagebox.showwarning(model_label, "Önce tekrar okutulacak satırı seçin.")
        return
    source_path = kayit.kaynak_yolu
    if not source_path or not os.path.exists(source_path):
        messagebox.showwarning(model_label, "Bu satırda tekrar okutulacak kaynak fotoğraf yok.")
        return
    if os.path.splitext(source_path)[1].lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        messagebox.showwarning(model_label, "Tekrar okuma için kaynak bir fotoğraf olmalı.")
        return
    ayarlar = spt_ayarlarini_yukle()
    if not ayarlar.get("openai_api_key"):
        messagebox.showwarning(model_label, "OpenAI API anahtarı bulunamadı. SPT Merkezi > Ayarlar kısmını kontrol edin.")
        return
    progress_win = Toplevel(win)
    app.pencere_hazirla(progress_win, model_label, "480x150", (420, 130), modal=False)
    ttk.Label(progress_win, text=f"Seçili satır {model_label} ile tekrar okunuyor...", padding=12).pack(fill="x")
    progress = ttk.Progressbar(progress_win, mode="indeterminate")
    progress.pack(fill="x", padx=12, pady=8)
    progress.start(12)

    def finish(raw_items=None, hata=None):
        if progress_win.winfo_exists():
            progress_win.destroy()
        if hata:
            messagebox.showerror(model_label, f"Tekrar okuma tamamlanamadı:\n{hata}")
            return
        normalized = []
        for item in raw_items or []:
            item = dict(item)
            item["kaynak"] = kayit.kaynak or os.path.basename(source_path)
            item["kaynak_yolu"] = source_path
            normalized.append(kayit_normalize_et(item, kayit.sondaj_no or target_var.get()))
        if not normalized:
            messagebox.showwarning(model_label, f"{model_label} bu fotoğraftan SPT satırı okuyamadı.")
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
        spt_gecmis_kaydet(history_event, chosen, {"onceki": previous})
        refresh_tree()
        load_detail(record)
        status_var.set(f"Seçili satır {model_label} ile tekrar okundu.")

    def worker():
        return yapay_zeka_ile_spt_oku(
            source_path,
            ayarlar=ayarlar,
            motor_zorla=motor_role,
            timeout=timeout,
        )

    app.arka_plan_gorevi_baslat(
        "SPT Pro tekrar oku",
        worker,
        status_start="Seçili SPT satırı Pro ile arka planda okunuyor.",
        status_success="Seçili SPT satırı Pro ile okundu.",
        status_error="SPT Pro tekrar okuma tamamlanamadı: {error}",
        on_success=lambda raw_items: finish(raw_items=raw_items),
        on_error=lambda exc: finish(hata=exc),
    )


def reread_selected_with_pro(app, win, selected_record, update_selected_from_form, target_var, status_var, refresh_tree, load_detail):
    return _reread_selected_with_openai_role(
        app,
        win,
        selected_record,
        update_selected_from_form,
        target_var,
        status_var,
        refresh_tree,
        load_detail,
        motor_role="openai_pro",
        model_label="GPT-5.6 Terra",
        history_event="openai_terra_tekrar_okundu",
        timeout=75,
    )


def reread_selected_with_strongest(app, win, selected_record, update_selected_from_form, target_var, status_var, refresh_tree, load_detail):
    return _reread_selected_with_openai_role(
        app,
        win,
        selected_record,
        update_selected_from_form,
        target_var,
        status_var,
        refresh_tree,
        load_detail,
        motor_role="openai_ust",
        model_label="GPT-5.6 Sol",
        history_event="openai_sol_tekrar_okundu",
        timeout=90,
    )
