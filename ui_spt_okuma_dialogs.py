# Dosya: RaporPro/ui_spt_okuma_dialogs.py
import os
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

from sabitler import COLOR_DANGER, COLOR_SUCCESS, FONT_BOLD
from spt_gorsel import dogal_siralama_anahtari
from spt_okuma_motoru import (
    DEFAULT_REVIZYON_OPENAI_MODEL,
    DEFAULT_SPT_GEMINI_MODEL,
    DEFAULT_SPT_OPENAI_MODEL,
    DEFAULT_SPT_PRO_OPENAI_MODEL,
    DEFAULT_SPT_UST_OPENAI_MODEL,
    SPT_AYARLAR_PATH,
    fotograflardan_spt_oku,
    spt_ayarlarini_kaydet,
    spt_ayarlarini_yukle,
    spt_gecmisi_oku,
    spt_kaynak_raporu_kaydet,
    spt_kirp_kaydet,
)
from ui_spt_okuma_yardimci import collect_image_paths, source_content_key, source_unique_key
from yardimcilar import safe_float


def show_spt_history(app, parent):
    history = spt_gecmisi_oku(limit=500)
    popup = Toplevel(parent)
    app.pencere_hazirla(popup, "SPT Okuma Geçmişi", "960x520", (780, 420), modal=False)
    filter_bar = ttk.Frame(popup, padding=(8, 8, 8, 0))
    filter_bar.pack(fill="x")
    ttk.Label(filter_bar, text="Proje / kaynak ara:").pack(side="left")
    filter_var = tk.StringVar(value="")
    ttk.Entry(filter_bar, textvariable=filter_var, width=36).pack(side="left", padx=6)

    tree_frame = ttk.Frame(popup, padding=8)
    tree_frame.pack(fill="both", expand=True)
    cols = ("tarih", "proje", "islem", "sondaj", "der", "spt", "n30", "guven", "motor", "kaynak")
    hist_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
    scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=hist_tree.yview)
    hist_tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    hist_tree.pack(fill="both", expand=True)
    for key, label, width in [
        ("tarih", "Tarih", 135), ("proje", "Proje", 160), ("islem", "İşlem", 95), ("sondaj", "Sondaj", 75),
        ("der", "Derinlik", 80), ("spt", "SPT", 105), ("n30", "N30", 70),
        ("guven", "Güven", 65), ("motor", "Motor", 110), ("kaynak", "Kaynak", 220),
    ]:
        hist_tree.heading(key, text=label)
        hist_tree.column(key, width=width, stretch=key in ("proje", "kaynak"))

    def render_history(*_args):
        hist_tree.delete(*hist_tree.get_children())
        query = filter_var.get().strip().casefold()
        for item in reversed(history):
            kayit = item.get("kayit", {}) or {}
            raw = kayit.get("raw", {}) or {}
            project = str(raw.get("proje", "") or item.get("detay", {}).get("proje", ""))
            source = str(kayit.get("kaynak", "") or "")
            if query and query not in f"{project} {source}".casefold():
                continue
            hist_tree.insert("", "end", values=(
                item.get("tarih", ""),
                project,
                item.get("islem", ""),
                kayit.get("sondaj_no", ""),
                kayit.get("derinlik", ""),
                "-".join([str(kayit.get(k, "")) for k in ("v15", "v30", "v45") if str(kayit.get(k, "")).strip()]),
                kayit.get("n30", ""),
                kayit.get("guven", ""),
                " / ".join(filter(None, [str(raw.get("motor", "")), str(raw.get("model", ""))])),
                source,
            ))

    filter_var.trace_add("write", render_history)
    render_history()


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
        existing_content = {
            source_content_key(path)
            for path in queued_paths
            if source_content_key(path)
        }
        added = 0
        skipped_duplicate = 0
        skipped_invalid = 0
        for source in paths:
            found = collect_image_paths([source], recursive=recursive_var.get())
            if not found:
                skipped_invalid += 1
            for abs_path in found:
                key = source_unique_key(abs_path)
                content_key = source_content_key(abs_path)
                if key in existing or (content_key and content_key in existing_content):
                    skipped_duplicate += 1
                    continue
                queued_paths.append(os.path.abspath(abs_path))
                existing.add(key)
                if content_key:
                    existing_content.add(content_key)
                added += 1
        queued_paths.sort(key=dogal_siralama_anahtari)
        unique_paths = []
        seen = set()
        seen_content = set()
        for path in queued_paths:
            key = source_unique_key(path)
            content_key = source_content_key(path)
            if key in seen or (content_key and content_key in seen_content):
                skipped_duplicate += 1
                continue
            unique_paths.append(path)
            seen.add(key)
            if content_key:
                seen_content.add(content_key)
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


def open_spt_crop_dialog(app, parent, initial_dir, target_var, project_spt_settings, add_result):
    source_path = filedialog.askopenfilename(
        title="Kırpılacak SPT Fotoğrafını Seç",
        initialdir=initial_dir,
        filetypes=[("Resimler", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG"), ("Tüm Dosyalar", "*.*")],
    )
    if not source_path:
        return
    try:
        from PIL import Image, ImageOps, ImageTk
        image = Image.open(source_path)
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass
    except Exception as exc:
        messagebox.showerror("Fotoğraf Kırp", f"Fotoğraf açılamadı:\n{exc}")
        return

    crop_win = Toplevel(parent)
    app.pencere_hazirla(crop_win, "SPT Fotoğraf Bölgesi Seç", "980x720", (820, 560), modal=True)
    top_note = ttk.Label(crop_win, text="SPT tabelasının olduğu alanı fare ile çerçeveleyin, sonra Oku düğmesine basın.", padding=8)
    top_note.pack(fill="x")
    canvas_frame = ttk.Frame(crop_win)
    canvas_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    canvas = tk.Canvas(canvas_frame, bg="#222222", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    max_w, max_h = 920, 560
    scale = min(max_w / image.width, max_h / image.height, 1.0)
    display_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    display_image = image.resize(display_size)
    tk_image = ImageTk.PhotoImage(display_image)
    canvas.image = tk_image
    canvas.create_image(10, 10, image=tk_image, anchor="nw")
    rect_state = {"start": None, "rect": None}

    def clamp_canvas(x, y):
        return (
            max(10, min(x, 10 + display_size[0])),
            max(10, min(y, 10 + display_size[1])),
        )

    def on_press(event):
        x, y = clamp_canvas(event.x, event.y)
        rect_state["start"] = (x, y)
        if rect_state["rect"]:
            canvas.delete(rect_state["rect"])
        rect_state["rect"] = canvas.create_rectangle(x, y, x, y, outline="#F1C40F", width=3)

    def on_drag(event):
        if not rect_state["start"] or not rect_state["rect"]:
            return
        x, y = clamp_canvas(event.x, event.y)
        x0, y0 = rect_state["start"]
        canvas.coords(rect_state["rect"], x0, y0, x, y)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)

    def read_crop():
        if not rect_state["rect"]:
            messagebox.showwarning("Fotoğraf Kırp", "Önce bir alan seçin.")
            return
        x1, y1, x2, y2 = canvas.coords(rect_state["rect"])
        left, right = sorted([x1 - 10, x2 - 10])
        top, bottom = sorted([y1 - 10, y2 - 10])
        if right - left < 20 or bottom - top < 20:
            messagebox.showwarning("Fotoğraf Kırp", "Seçilen alan çok küçük.")
            return
        crop_box = (left / scale, top / scale, right / scale, bottom / scale)
        try:
            cropped_path = spt_kirp_kaydet(source_path, crop_box)
        except Exception as exc:
            messagebox.showerror("Fotoğraf Kırp", f"Kırpma kaydedilemedi:\n{exc}")
            return
        crop_win.destroy()
        ayarlar = spt_ayarlarini_yukle()
        progress_win = Toplevel(parent)
        app.pencere_hazirla(progress_win, "Kırpılmış SPT Okuma", "460x150", (420, 130), modal=False)
        progress_text = tk.StringVar(value=f"Kırpılmış alan okunuyor. Motor: {ayarlar.get('aktif_motor', '-')}")
        ttk.Label(progress_win, textvariable=progress_text, padding=12).pack(fill="x")
        progress = ttk.Progressbar(progress_win, mode="indeterminate")
        progress.pack(fill="x", padx=12, pady=8)
        progress.start(12)

        def finish(sonuc=None, hata=None):
            if progress_win.winfo_exists():
                progress_win.destroy()
            if hata:
                messagebox.showerror("Kırpılmış SPT Okuma", f"Okuma tamamlanamadı:\n{hata}")
                return
            if not sonuc or not sonuc.kayitlar:
                messagebox.showwarning("Kırpılmış SPT Okuma", "Kırpılmış alandan SPT satırı okunamadı.")
                return
            add_result(sonuc, "Kırpılmış Fotoğraf", append=True)

        def worker():
            return fotograflardan_spt_oku(
                [cropped_path],
                default_sondaj_no=target_var.get(),
                ayarlar=ayarlar,
                auto_pro=project_spt_settings()["auto_pro"],
                guven_esigi=project_spt_settings()["guven_esigi"],
            )

        app.arka_plan_gorevi_baslat(
            "Kırpılmış SPT oku",
            worker,
            status_start="Kırpılmış SPT alanı arka planda okunuyor.",
            status_success="Kırpılmış SPT alanı okundu.",
            status_error="Kırpılmış SPT okuma tamamlanamadı: {error}",
            on_success=lambda sonuc: finish(sonuc=sonuc),
            on_error=lambda exc: finish(hata=exc),
        )

    btns = ttk.Frame(crop_win, padding=8)
    btns.pack(fill="x")
    tk.Button(btns, text="Oku", command=read_crop, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=4)
    tk.Button(btns, text="Kapat", command=crop_win.destroy, bg="#7F8C8D", fg="white", font=FONT_BOLD).pack(side="right", padx=4)


def open_spt_settings_dialog(app, parent, auto_pro_var, refresh_tree, status_var):
    ayarlar = spt_ayarlarini_yukle()
    project = app.veri.setdefault("ayarlar", {})
    popup = Toplevel(parent)
    app.pencere_hazirla(popup, "SPT Okuma Ayarları", "680x640", (600, 560), modal=True)
    try:
        popup.transient(parent)
    except Exception:
        pass
    body = ttk.Frame(popup, padding=12)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Aktif Motor", font=FONT_BOLD).grid(row=0, column=0, sticky="w", pady=5)
    motor_var = tk.StringVar(value=ayarlar.get("aktif_motor", "gemini"))
    ttk.Combobox(body, textvariable=motor_var, values=["gemini", "openai"], state="readonly", width=22).grid(row=0, column=1, sticky="ew", pady=5)
    key_entries = {}
    for row, (label, key) in enumerate([
        ("OpenAI API Key", "openai_api_key"),
        ("Gemini API Key", "gemini_api_key"),
    ], start=1):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ent = ttk.Entry(body, show="*")
        ent.insert(0, ayarlar.get(key, ""))
        ent.grid(row=row, column=1, sticky="ew", pady=5)
        key_entries[key] = ent
    model_entries = {}
    for row, (label, key, default) in enumerate([
        ("Gemini Ana Okuma Modeli", "spt_gemini_model", DEFAULT_SPT_GEMINI_MODEL),
        ("OpenAI İkinci Okuma Modeli", "openai_model", DEFAULT_SPT_OPENAI_MODEL),
        ("OpenAI Pro Modeli", "spt_pro_openai_model", DEFAULT_SPT_PRO_OPENAI_MODEL),
        ("OpenAI En Güçlü Model", "spt_ust_openai_model", DEFAULT_SPT_UST_OPENAI_MODEL),
        ("Rapor Revizyon Modeli", "revizyon_openai_model", DEFAULT_REVIZYON_OPENAI_MODEL),
    ], start=3):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ent = ttk.Entry(body)
        ent.insert(0, ayarlar.get(key, default) or default)
        ent.grid(row=row, column=1, sticky="ew", pady=5)
        model_entries[key] = ent
    ttk.Label(body, text="Düşük Güven Eşiği").grid(row=8, column=0, sticky="w", pady=5)
    guven_entry = ttk.Entry(body, width=10)
    guven_entry.insert(0, project.get("spt_guven_esigi", "90"))
    guven_entry.grid(row=8, column=1, sticky="w", pady=5)
    popup_auto_pro_var = tk.BooleanVar(value=bool(auto_pro_var.get()))
    ttk.Checkbutton(body, text="Düşük güvende OpenAI Luna ile ikinci okuma yap", variable=popup_auto_pro_var).grid(row=9, column=0, columnspan=2, sticky="w", pady=8)
    path_text = f"Ayar dosyası: {SPT_AYARLAR_PATH}"
    ttk.Label(body, text=path_text, foreground="#555555", wraplength=620).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 2))
    state_text = "Anahtar durumu: " + ", ".join(
        f"{name} {'var' if ayarlar.get(key) else 'yok'}"
        for name, key in [("OpenAI", "openai_api_key"), ("Gemini", "gemini_api_key")]
    )
    ttk.Label(body, text=state_text, foreground="#1F618D", wraplength=620).grid(row=11, column=0, columnspan=2, sticky="w", pady=(2, 8))
    body.columnconfigure(1, weight=1)

    def save_settings():
        guven_esigi = safe_float(guven_entry.get())
        if not 1 <= guven_esigi <= 100:
            messagebox.showerror(
                "SPT Ayarları",
                "Düşük güven eşiğini 1 ile 100 arasında girin.",
                parent=popup,
            )
            return
        new_settings = {
            "aktif_motor": motor_var.get().strip(),
            "openai_api_key": key_entries["openai_api_key"].get().strip(),
            "openai_model": model_entries["openai_model"].get().strip() or DEFAULT_SPT_OPENAI_MODEL,
            "spt_pro_openai_model": model_entries["spt_pro_openai_model"].get().strip() or DEFAULT_SPT_PRO_OPENAI_MODEL,
            "spt_ust_openai_model": model_entries["spt_ust_openai_model"].get().strip() or DEFAULT_SPT_UST_OPENAI_MODEL,
            "revizyon_openai_model": model_entries["revizyon_openai_model"].get().strip() or DEFAULT_REVIZYON_OPENAI_MODEL,
            "gemini_api_key": key_entries["gemini_api_key"].get().strip(),
            "spt_gemini_model": model_entries["spt_gemini_model"].get().strip() or DEFAULT_SPT_GEMINI_MODEL,
        }
        try:
            spt_ayarlarini_kaydet(new_settings)
        except Exception as exc:
            messagebox.showerror("SPT Ayarları", f"Ayarlar kaydedilemedi:\n{exc}")
            return
        project["spt_guven_esigi"] = str(int(round(guven_esigi)))
        auto_pro_var.set(bool(popup_auto_pro_var.get()))
        project["spt_auto_pro"] = "1" if auto_pro_var.get() else "0"
        refresh_tree()
        status_var.set("SPT ayarları güncellendi.")
        app.set_status("SPT okuma ayarları güncellendi.", level="success")
        popup.destroy()

    def check_settings():
        motor = motor_var.get().strip() or "gemini"
        key_by_motor = {
            "openai": ("OpenAI", key_entries["openai_api_key"].get().strip()),
            "gemini": ("Gemini", key_entries["gemini_api_key"].get().strip()),
        }
        name, api_key = key_by_motor.get(motor, ("Motor", ""))
        problems = []
        if not api_key:
            problems.append(f"{name} API anahtarı boş.")
        for label, key in (
            ("Gemini ana okuma modeli", "spt_gemini_model"),
            ("OpenAI ikinci okuma modeli", "openai_model"),
            ("OpenAI Pro modeli", "spt_pro_openai_model"),
            ("OpenAI en güçlü model", "spt_ust_openai_model"),
            ("Rapor revizyon modeli", "revizyon_openai_model"),
        ):
            if not model_entries[key].get().strip():
                problems.append(f"{label} boş.")
        if popup_auto_pro_var.get() and not key_entries["openai_api_key"].get().strip():
            problems.append("Otomatik ikinci okuma için OpenAI API anahtarı boş.")
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
    btns.grid(row=12, column=0, columnspan=2, sticky="e", pady=(16, 0))
    tk.Button(btns, text="Kaydet", command=save_settings, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=4)
    tk.Button(btns, text="Ayar Kontrolü", command=check_settings, bg="#D6EAF8", fg="#111", font=FONT_BOLD).pack(side="right", padx=4)
    tk.Button(btns, text="Kapat", command=popup.destroy, bg="#7F8C8D", fg="white", font=FONT_BOLD).pack(side="right", padx=4)
    try:
        popup.grab_set()
        popup.lift()
        popup.focus_force()
        popup.after_idle(lambda: (popup.lift(), popup.focus_force()))
    except Exception:
        pass
    return popup
