# Dosya: RaporPro/ui_spt_okuma_dialogs.py
import os
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

from sabitler import COLOR_SUCCESS, FONT_BOLD
from spt_okuma_motoru import (
    SPT_AYARLAR_PATH,
    spt_ayarlarini_kaydet,
    spt_ayarlarini_yukle,
    spt_gecmisi_oku,
    spt_kaynak_raporu_kaydet,
)


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
