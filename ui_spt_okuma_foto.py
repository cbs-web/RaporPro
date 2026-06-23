# Dosya: RaporPro/ui_spt_okuma_foto.py
import threading
import tkinter as tk
from tkinter import Toplevel, messagebox, ttk

from sabitler import COLOR_DANGER, FONT_BOLD
from spt_okuma_motoru import fotograflardan_spt_oku, spt_ayarlarini_yukle
from ui_spt_okuma_yardimci import source_unique_key


def start_photo_reading(app, win, paths, target_var, status_var, project_spt_settings, add_result):
    paths = list(paths or [])
    unique_paths = []
    seen_paths = set()
    for path in paths:
        key = source_unique_key(path)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        unique_paths.append(path)
    if len(unique_paths) != len(paths):
        status_var.set(f"SPT okuma öncesi {len(paths) - len(unique_paths)} tekrar fotoğraf yolu temizlendi.")
    paths = unique_paths
    if not paths:
        messagebox.showwarning("SPT Fotoğraf", "Okunacak fotoğraf seçilmedi.")
        return
    ayarlar = spt_ayarlarini_yukle()
    stop_event = threading.Event()
    progress_win = Toplevel(win)
    app.pencere_hazirla(progress_win, "SPT Fotoğraf Okuma", "500x170", (460, 150), modal=False)
    progress_text = tk.StringVar(value=f"{len(paths)} fotoğraf sıraya alındı. Motor: {ayarlar.get('aktif_motor', '-')}")
    ttk.Label(progress_win, text="Fotoğraflar okunuyor...", font=FONT_BOLD).pack(anchor="w", padx=12, pady=(12, 4))
    ttk.Label(progress_win, textvariable=progress_text, wraplength=460).pack(anchor="w", padx=12, fill="x")
    progress = ttk.Progressbar(progress_win, mode="determinate", maximum=len(paths))
    progress.pack(fill="x", padx=12, pady=8)
    tk.Button(progress_win, text="İptal", command=stop_event.set, bg=COLOR_DANGER, fg="white", font=FONT_BOLD).pack(side="right", padx=12, pady=8)

    def progress_callback(done, total, name, state):
        def update():
            if not progress_win.winfo_exists():
                return
            progress["maximum"] = max(1, total)
            progress["value"] = done
            progress_text.set(f"{done}/{total} | {name} | {state}")
            status_var.set(progress_text.get())
        app.root.after(0, update)

    def finish(sonuc=None, hata=None):
        if progress_win.winfo_exists():
            progress_win.destroy()
        if hata:
            messagebox.showerror("SPT Fotoğraf", f"Fotoğraf okuma tamamlanamadı:\n{hata}")
            return
        if not sonuc or not sonuc.kayitlar:
            msg = "Fotoğraflardan aktarılacak SPT satırı bulunamadı."
            if sonuc and sonuc.uyarilar:
                msg += "\n\n" + "\n".join(sonuc.uyarilar[:10])
            messagebox.showwarning("SPT Fotoğraf", msg)
            return
        add_result(sonuc, "Fotoğraf Okuma", append=True)

    def worker():
        try:
            settings = project_spt_settings()
            sonuc = fotograflardan_spt_oku(
                paths,
                default_sondaj_no=target_var.get(),
                ayarlar=ayarlar,
                progress_callback=progress_callback,
                stop_event=stop_event,
                auto_pro=settings["auto_pro"],
            )
            app.root.after(0, lambda: finish(sonuc=sonuc))
        except Exception as exc:
            app.root.after(0, lambda: finish(hata=exc))

    threading.Thread(target=worker, daemon=True).start()
