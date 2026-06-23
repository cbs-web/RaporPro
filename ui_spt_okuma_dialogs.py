# Dosya: RaporPro/ui_spt_okuma_dialogs.py
import os
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

from sabitler import COLOR_DANGER, COLOR_SUCCESS, FONT_BOLD
from spt_okuma_motoru import (
    SPT_AYARLAR_PATH,
    spt_ayarlarini_kaydet,
    spt_ayarlarini_yukle,
    spt_gecmisi_oku,
    spt_kaynak_raporu_kaydet,
)
from ui_spt_okuma_yardimci import collect_image_paths, source_unique_key


def show_spt_history(app, parent):
    history = spt_gecmisi_oku(limit=500)
    popup = Toplevel(parent)
    app.pencere_hazirla(popup, "SPT Okuma Geçmişi", "960x520", (780, 420), modal=False)
    cols = ("tarih", "islem", "sondaj", "der", "spt", "n30", "guven", "kaynak")
    hist_tree = ttk.Treeview(popup, columns=cols, show="headings")
    scroll = ttk.Scrollbar(popup, orient="vertical", command=hist_tree.yview)
    hist_tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    hist_tree.pack(fill="both", expand=True, padx=8, pady=8)
    for key, label, width in [
        ("tarih", "Tarih", 145), ("islem", "İşlem", 95), ("sondaj", "Sondaj", 85),
        ("der", "Derinlik", 80), ("spt", "SPT", 105), ("n30", "N30", 70),
        ("guven", "Güven", 70), ("kaynak", "Kaynak", 260),
    ]:
        hist_tree.heading(key, text=label)
        hist_tree.column(key, width=width, stretch=key == "kaynak")
    for item in reversed(history):
        kayit = item.get("kayit", {}) or {}
        hist_tree.insert("", "end", values=(
            item.get("tarih", ""),
            item.get("islem", ""),
            kayit.get("sondaj_no", ""),
            kayit.get("derinlik", ""),
            "-".join([str(kayit.get(k, "")) for k in ("v15", "v30", "v45") if str(kayit.get(k, "")).strip()]),
            kayit.get("n30", ""),
            kayit.get("guven", ""),
            kayit.get("kaynak", ""),
        ))


def export_spt_source_report(app, records):
    kayitlar = [
        record["kayit"]
        for record in records
        if record.get("record_type") != "queue" and record.get("include", True)
    ]
    if not kayitlar:
        messagebox.showwarning("SPT Kaynak Raporu", "Rapora eklenecek seçili SPT satırı yok.")
        return
    path = filedialog.asksaveasfilename(
        title="SPT Kaynak Raporu Kaydet",
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")],
        initialfile="SPT_Kaynak_Raporu.xlsx",
    )
    if not path:
        return
    try:
        spt_kaynak_raporu_kaydet(kayitlar, path)
        app.set_status(f"SPT kaynak raporu kaydedildi: {os.path.basename(path)}", level="success")
    except Exception as exc:
        messagebox.showerror("SPT Kaynak Raporu", f"Rapor kaydedilemedi:\n{exc}")


def open_spt_photo_queue_dialog(app, parent, initial_dir, add_to_main_photo_queue, start_main_photo_queue, status_var):
    try:
        from tkinterdnd2 import TkinterDnD
        queue_win = TkinterDnD.Toplevel(parent)
    except Exception:
        queue_win = Toplevel(parent)
    app.pencere_hazirla(queue_win, "SPT Fotoğraf Kuyruğu", "860x560", (720, 440), modal=False)
    queued_paths = []
    recursive_var = tk.BooleanVar(value=True)
    info_var = tk.StringVar(value="Fotoğraf veya klasörü ekleyin; başlatmadan okuma yapılmayacak.")
    dnd_var = tk.StringVar(value="")

    top = ttk.Frame(queue_win, padding=8)
    top.pack(fill="x")
    ttk.Label(top, textvariable=info_var, foreground="#1F618D").pack(side="left", fill="x", expand=True)
    ttk.Label(top, textvariable=dnd_var, foreground="#555555").pack(side="right")

    list_frame = ttk.Frame(queue_win, padding=(8, 0, 8, 8))
    list_frame.pack(fill="both", expand=True)
    listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED)
    scroll_y = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
    scroll_x = ttk.Scrollbar(list_frame, orient="horizontal", command=listbox.xview)
    listbox.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    scroll_y.pack(side="right", fill="y")
    scroll_x.pack(side="bottom", fill="x")
    listbox.pack(side="left", fill="both", expand=True)

    def refresh_queue():
        listbox.delete(0, tk.END)
        for idx, path in enumerate(queued_paths, start=1):
            listbox.insert(tk.END, f"{idx}. {path}")
        info_var.set(f"{len(queued_paths)} fotoğraf kuyrukta. Başlatılana kadar okuma yapılmayacak.")

    def add_paths(paths):
        existing = {source_unique_key(path) for path in queued_paths}
        added = 0
        skipped_duplicate = 0
        skipped_invalid = 0
        for source in paths:
            found = collect_image_paths([source], recursive=recursive_var.get())
            if not found:
                skipped_invalid += 1
            for abs_path in found:
                key = source_unique_key(abs_path)
                if key in existing:
                    skipped_duplicate += 1
                    continue
                queued_paths.append(os.path.abspath(abs_path))
                existing.add(key)
                added += 1
        queued_paths.sort(key=lambda item: item.lower())
        unique_paths = []
        seen = set()
        for path in queued_paths:
            key = source_unique_key(path)
            if key in seen:
                skipped_duplicate += 1
                continue
            unique_paths.append(path)
            seen.add(key)
        queued_paths[:] = unique_paths
        refresh_queue()
        if added:
            status_var.set(f"SPT kuyruğuna {added} fotoğraf eklendi.")
        if skipped_duplicate:
            info_var.set(f"{len(queued_paths)} fotoğraf kuyrukta. {skipped_duplicate} tekrar dosya atlandı.")
        elif skipped_invalid and not added:
            info_var.set("Geçerli fotoğraf bulunamadı. JPG, PNG, BMP veya WEBP dosyası/klasörü bırakın.")
        return added, skipped_duplicate, skipped_invalid

    def add_photos():
        paths = filedialog.askopenfilenames(
            title="SPT Fotoğraflarını Kuyruğa Ekle",
            initialdir=initial_dir,
            filetypes=[("Resimler", "*.jpg *.jpeg *.png *.bmp *.webp *.JPG *.JPEG *.PNG"), ("Tüm Dosyalar", "*.*")],
            parent=queue_win,
        )
        add_paths(paths)

    def add_folder():
        folder = filedialog.askdirectory(title="SPT Fotoğraf Klasörü Seç", initialdir=initial_dir, parent=queue_win)
        if folder:
            add_paths([folder])

    def remove_selected():
        selected = list(listbox.curselection())
        if not selected:
            return
        for idx in reversed(selected):
            if 0 <= idx < len(queued_paths):
                del queued_paths[idx]
        refresh_queue()

    def clear_queue():
        queued_paths.clear()
        refresh_queue()

    def start_queue():
        if not queued_paths:
            messagebox.showwarning("SPT Fotoğraf Kuyruğu", "Başlatmak için önce fotoğraf ekleyin.", parent=queue_win)
            return
        paths = []
        seen = set()
        for path in queued_paths:
            key = source_unique_key(path)
            if key in seen:
                continue
            paths.append(path)
            seen.add(key)
        if len(paths) != len(queued_paths):
            queued_paths[:] = paths
            refresh_queue()
            status_var.set("SPT fotoğraf kuyruğundaki tekrar dosyalar temizlendi.")
        queue_win.destroy()
        add_to_main_photo_queue(paths)
        start_main_photo_queue()

    def parse_drop_paths(data):
        try:
            return [item for item in queue_win.tk.splitlist(data) if item]
        except Exception:
            return [item for item in str(data or "").split() if item]

    def on_drop(event):
        sources = parse_drop_paths(getattr(event, "data", ""))
        added, skipped_duplicate, skipped_invalid = add_paths(sources)
        if added:
            status_var.set(f"Sürükle-bırak ile {added} fotoğraf eklendi.")
        elif skipped_duplicate:
            status_var.set("Sürükle-bırak: tekrar dosyalar atlandı.")
        elif skipped_invalid:
            status_var.set("Sürükle-bırak: geçerli fotoğraf bulunamadı.")
        return "break"

    def enable_drag_drop():
        try:
            from tkinterdnd2 import DND_FILES
            enabled = False
            targets = [queue_win, listbox]
            for target in targets:
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", on_drop)
                    enabled = True
                except Exception:
                    continue
            if enabled:
                dnd_var.set("Fotoğraf veya klasörü bu pencereye sürükleyip bırakabilirsiniz.")
                return True
        except Exception:
            pass
        dnd_var.set("Sürükle-bırak için tkinterdnd2 paketi gerekir. RaporPro_Baslat.bat ile paket kontrolünden kurabilirsiniz.")
        return False

    buttons = ttk.Frame(queue_win, padding=8)
    buttons.pack(fill="x")
    tk.Button(buttons, text="Fotoğraf Ekle", command=add_photos, bg="#2E86C1", fg="white", font=FONT_BOLD).pack(side="left", padx=3)
    tk.Button(buttons, text="Klasör Ekle", command=add_folder, bg="#117864", fg="white", font=FONT_BOLD).pack(side="left", padx=3)
    ttk.Checkbutton(buttons, text="Alt klasörleri tara", variable=recursive_var).pack(side="left", padx=8)
    tk.Button(buttons, text="Seçileni Sil", command=remove_selected, bg=COLOR_DANGER, fg="white", font=FONT_BOLD).pack(side="left", padx=3)
    tk.Button(buttons, text="Temizle", command=clear_queue, bg="#7F8C8D", fg="white", font=FONT_BOLD).pack(side="left", padx=3)
    tk.Button(buttons, text="Başlat", command=start_queue, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=3)
    tk.Button(buttons, text="Kapat", command=queue_win.destroy, bg="#ECF0F1", fg="#111", font=FONT_BOLD).pack(side="right", padx=3)
    listbox.bind("<Delete>", lambda _event: (remove_selected() or "break"))
    enable_drag_drop()
    refresh_queue()


def open_spt_settings_dialog(app, parent, auto_pro_var, refresh_tree, status_var):
    ayarlar = spt_ayarlarini_yukle()
    project = app.veri.setdefault("ayarlar", {})
    popup = Toplevel(parent)
    app.pencere_hazirla(popup, "SPT Okuma Ayarları", "520x430", (480, 390), modal=True)
    body = ttk.Frame(popup, padding=12)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Aktif Motor", font=FONT_BOLD).grid(row=0, column=0, sticky="w", pady=5)
    motor_var = tk.StringVar(value=ayarlar.get("aktif_motor", "openai"))
    ttk.Combobox(body, textvariable=motor_var, values=["openai", "gemini", "gemini_pro", "groq"], state="readonly", width=22).grid(row=0, column=1, sticky="ew", pady=5)
    key_entries = {}
    for row, (label, key) in enumerate([
        ("OpenAI API Key", "openai_api_key"),
        ("Gemini API Key", "gemini_api_key"),
        ("Groq API Key", "groq_api_key"),
    ], start=1):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ent = ttk.Entry(body, show="*")
        ent.insert(0, ayarlar.get(key, ""))
        ent.grid(row=row, column=1, sticky="ew", pady=5)
        key_entries[key] = ent
    ttk.Label(body, text="Düşük Güven Eşiği").grid(row=4, column=0, sticky="w", pady=5)
    guven_entry = ttk.Entry(body, width=10)
    guven_entry.insert(0, project.get("spt_guven_esigi", "90"))
    guven_entry.grid(row=4, column=1, sticky="w", pady=5)
    popup_auto_pro_var = tk.BooleanVar(value=bool(auto_pro_var.get()))
    ttk.Checkbutton(body, text="Düşük güvende Gemini Pro ile tekrar oku", variable=popup_auto_pro_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=8)
    path_text = f"Ayar dosyası: {SPT_AYARLAR_PATH}"
    ttk.Label(body, text=path_text, foreground="#555555", wraplength=460).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 2))
    state_text = "Anahtar durumu: " + ", ".join(
        f"{name} {'var' if ayarlar.get(key) else 'yok'}"
        for name, key in [("OpenAI", "openai_api_key"), ("Gemini", "gemini_api_key"), ("Groq", "groq_api_key")]
    )
    ttk.Label(body, text=state_text, foreground="#1F618D", wraplength=460).grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 8))
    body.columnconfigure(1, weight=1)

    def save_settings():
        new_settings = {
            "aktif_motor": motor_var.get().strip(),
            "openai_api_key": key_entries["openai_api_key"].get().strip(),
            "gemini_api_key": key_entries["gemini_api_key"].get().strip(),
            "groq_api_key": key_entries["groq_api_key"].get().strip(),
        }
        try:
            spt_ayarlarini_kaydet(new_settings)
        except Exception as exc:
            messagebox.showerror("SPT Ayarları", f"Ayarlar kaydedilemedi:\n{exc}")
            return
        project["spt_guven_esigi"] = guven_entry.get().strip() or "90"
        auto_pro_var.set(bool(popup_auto_pro_var.get()))
        project["spt_auto_pro"] = "1" if auto_pro_var.get() else "0"
        refresh_tree()
        status_var.set("SPT ayarları güncellendi.")
        app.set_status("SPT okuma ayarları güncellendi.", level="success")
        popup.destroy()

    def check_settings():
        motor = motor_var.get().strip() or "openai"
        key_by_motor = {
            "openai": ("OpenAI", key_entries["openai_api_key"].get().strip()),
            "gemini": ("Gemini", key_entries["gemini_api_key"].get().strip()),
            "gemini_pro": ("Gemini", key_entries["gemini_api_key"].get().strip()),
            "groq": ("Groq", key_entries["groq_api_key"].get().strip()),
        }
        name, api_key = key_by_motor.get(motor, ("Motor", ""))
        problems = []
        if not api_key:
            problems.append(f"{name} API anahtarı boş.")
        try:
            import requests  # noqa: F401
        except Exception as exc:
            problems.append(f"requests paketi yüklenemedi: {exc}")
        try:
            SPT_AYARLAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            problems.append(f"Ayar klasörüne erişilemiyor: {exc}")
        if problems:
            messagebox.showwarning("SPT Ayar Kontrolü", "\n".join(problems), parent=popup)
        else:
            messagebox.showinfo(
                "SPT Ayar Kontrolü",
                f"{motor} için temel ayarlar hazır.\nCanlı okuma testi için SPT Merkezi > Foto Ekle + Başlat veya Kırp/Oku kullanın.",
                parent=popup,
            )

    btns = ttk.Frame(body)
    btns.grid(row=8, column=0, columnspan=2, sticky="e", pady=(16, 0))
    tk.Button(btns, text="Kaydet", command=save_settings, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=4)
    tk.Button(btns, text="Ayar Kontrolü", command=check_settings, bg="#D6EAF8", fg="#111", font=FONT_BOLD).pack(side="right", padx=4)
    tk.Button(btns, text="Kapat", command=popup.destroy, bg="#7F8C8D", fg="white", font=FONT_BOLD).pack(side="right", padx=4)
