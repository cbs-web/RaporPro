import os
import threading
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

from sabitler import *
from ui_spt_okuma_aktar import apply_spt_import
from spt_okuma_motoru import (
    SPTImportSonucu,
    SPTKaydi,
    excelden_spt_oku,
    fotograflardan_spt_oku,
    kayit_normalize_et,
    n30_hesapla,
    spt_gecmis_kaydet,
    spt_ogrenme_kaydet,
    spt_ayarlarini_yukle,
    normalize_sondaj_no,
    yapay_zeka_ile_spt_oku,
)
from yardimcilar import safe_float
from ui_spt_okuma_yardimci import (
    collect_image_paths,
    context_issues as spt_context_issues,
    duplicate_keys as spt_duplicate_keys,
    record_quality as spt_record_quality,
    source_unique_key,
    spt_location_key as build_spt_location_key,
    spt_unique_key as build_spt_unique_key,
)
from ui_spt_okuma_dialogs import (
    export_spt_source_report,
    open_spt_crop_dialog,
    open_spt_photo_queue_dialog,
    open_spt_settings_dialog,
    show_spt_history,
)
from ui_spt_okuma_preview import SPTPreviewController


class SPTOkumaMixin:
    def spt_excel_iceri_al(self):
        self.spt_okuma_merkezi_ac(baslat="excel")

    def spt_fotograf_oku(self):
        self.spt_okuma_merkezi_ac(baslat="foto")

    def spt_aktarma_onizleme_ac(self, path, sonuc):
        self.spt_okuma_merkezi_ac(initial_source=path, initial_sonuc=sonuc)

    def _spt_default_sondaj_no(self):
        sondajlar = self.veri.get("sondaj", [])
        return next((s.get("no") for s in sondajlar if s.get("no")), "SK-1")

    def _spt_initial_dir(self):
        spt_klasor = r"C:\Users\Bugra Senel\Desktop\SPT Okuma"
        return spt_klasor if os.path.isdir(spt_klasor) else os.getcwd()

    def spt_okuma_merkezi_ac(self, baslat=None, initial_source=None, initial_sonuc=None):
        self.sondaj_verilerini_kaydet(silent=True)
        try:
            from tkinterdnd2 import TkinterDnD
            win = TkinterDnD.Toplevel(self.root)
        except Exception:
            win = Toplevel(self.root)
        self.pencere_hazirla(win, "SPT Okuma Merkezi", "1360x840", (1080, 700), modal=False)

        records = []
        tree_items = {}
        selected_item = {"id": None}
        preview_image = {"ref": None}
        import_warnings = []
        main_queue_paths = []
        main_queue_recursive_var = tk.BooleanVar(value=True)
        main_queue_status_var = tk.StringVar(value="Kuyruk boş. Fotoğraf veya klasörü bu ekrana sürükleyebilirsiniz.")
        main_dnd_status_var = tk.StringVar(value="")
        main_queue_buttons = {"start": None, "stop": None}
        main_read_state = {
            "active": False,
            "stop_event": None,
            "total": 0,
            "done": 0,
            "added": 0,
            "skipped": 0,
            "failed": 0,
        }

        sondaj_nolari = [s.get("no") for s in self.veri.get("sondaj", []) if s.get("no")]
        if not sondaj_nolari:
            sondaj_nolari = ["SK-1"]
        valid_sondaj_nolari = {normalize_sondaj_no(no) for no in sondaj_nolari}
        target_var = tk.StringVar(value=self._spt_default_sondaj_no())
        filter_var = tk.StringVar(value="Tümü")
        status_var = tk.StringVar(value="SPT Okuma Merkezi hazır.")
        update_same_var = tk.BooleanVar(value=True)
        clear_target_var = tk.BooleanVar(value=False)
        project_settings = self.veri.setdefault("ayarlar", {})
        auto_pro_var = tk.BooleanVar(value=str(project_settings.get("spt_auto_pro", "1")) != "0")

        def project_spt_settings():
            ayarlar = self.veri.setdefault("ayarlar", {})
            return {
                "guven_esigi": safe_float(ayarlar.get("spt_guven_esigi", "90")) or 90,
                "auto_pro": bool(auto_pro_var.get()),
            }

        def save_auto_pro_setting():
            self.veri.setdefault("ayarlar", {})["spt_auto_pro"] = "1" if auto_pro_var.get() else "0"
            status_var.set("Otomatik Pro açık." if auto_pro_var.get() else "Otomatik Pro kapalı.")

        header = tk.Frame(win, bg="#FFFFFF", padx=12, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="SPT Okuma Merkezi", bg="#FFFFFF", fg=COLOR_PRIMARY, font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(header, textvariable=status_var, bg="#FFFFFF", fg="#555555", font=("Segoe UI", 9)).pack(side="left", padx=14)

        toolbar = ttk.Frame(win, padding=(8, 8))
        toolbar.pack(fill="x")
        source_group = ttk.LabelFrame(toolbar, text="Kaynak", padding=(5, 3))
        target_group = ttk.LabelFrame(toolbar, text="Aktarım", padding=(5, 3))
        filter_group = ttk.LabelFrame(toolbar, text="Görünüm", padding=(5, 3))
        pro_group = ttk.LabelFrame(toolbar, text="Pro", padding=(5, 3))
        source_group.pack(side="left", padx=3)
        target_group.pack(side="left", padx=3)
        filter_group.pack(side="left", padx=3)
        pro_group.pack(side="left", padx=3)

        queue_bar = ttk.Frame(win, padding=(8, 0, 8, 6))
        queue_bar.pack(fill="x")

        bottom = ttk.Frame(win, padding=8)
        bottom.pack(side="bottom", fill="x")

        main = ttk.Panedwindow(win, orient="horizontal")
        main.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=5)
        main.add(right, weight=4)

        table_frame = ttk.Frame(left)
        table_frame.pack(fill="both", expand=True)
        columns = ("al", "sondaj", "der", "v15", "v30", "v45", "n30", "guven", "durum", "kaynak")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", height=20)
        tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)

        headings = [
            ("al", "Al", 42), ("sondaj", "Sondaj", 90), ("der", "Derinlik", 78),
            ("v15", "15", 55), ("v30", "30", 55), ("v45", "45", 55),
            ("n30", "N30", 60), ("guven", "Güven", 65), ("durum", "Durum", 210),
            ("kaynak", "Kaynak", 220),
        ]
        for key, label, width in headings:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=42, stretch=key in ("durum", "kaynak"))
        tree.tag_configure("ok", background="#EAFAF1")
        tree.tag_configure("warning", background="#FCF3CF")
        tree.tag_configure("error", background="#FADBD8")
        tree.tag_configure("disabled", foreground="#888888")
        tree.tag_configure("queued", background="#EBF5FB")
        tree.tag_configure("reading", background="#D6EAF8")

        summary = ttk.LabelFrame(right, text="Kalite Özeti", padding=8)
        summary.pack(fill="x", pady=(0, 8))
        summary_var = tk.StringVar(value="Henüz veri yok.")
        ttk.Label(summary, textvariable=summary_var, justify="left", wraplength=360).pack(anchor="w", fill="x")

        detail = ttk.LabelFrame(right, text="Seçili Satır", padding=8)
        detail.pack(fill="x", pady=(0, 8))
        detail_entries = {}
        detail_specs = [
            ("Sondaj", "sondaj_no", 0, 0), ("Derinlik", "derinlik", 0, 2),
            ("15", "v15", 1, 0), ("30", "v30", 1, 2), ("45", "v45", 2, 0),
            ("N30", "n30", 2, 2),
        ]
        for label, key, row, col in detail_specs:
            ttk.Label(detail, text=label).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=3)
            ent = ttk.Entry(detail, width=14)
            ent.grid(row=row, column=col + 1, sticky="ew", padx=(0, 8), pady=3)
            detail_entries[key] = ent
        detail.columnconfigure(1, weight=1)
        detail.columnconfigure(3, weight=1)
        preview = ttk.LabelFrame(right, text="Kaynak Önizleme", padding=8)
        preview.pack(fill="both", expand=True, pady=(0, 8))
        preview_canvas = tk.Canvas(preview, bg="#FFFFFF", highlightthickness=1, highlightbackground="#D5DBDB", width=560, height=390)
        preview_canvas.pack(fill="both", expand=True)
        preview_controller = SPTPreviewController(win, preview_canvas, preview_image)

        issues = ttk.LabelFrame(right, text="Uyarılar", padding=8)
        issues.pack(fill="x")
        issue_list = tk.Listbox(issues, height=5)
        issue_list.pack(fill="x")

        def current_sondaj_depth(no):
            for sondaj in self.veri.get("sondaj", []):
                if sondaj.get("no") == no:
                    return safe_float(sondaj.get("der"))
            return 0

        def context_issues():
            return spt_context_issues(records)

        def record_quality(record, duplicate=False, context_messages=None):
            return spt_record_quality(
                record,
                duplicate=duplicate,
                context_messages=context_messages,
                current_sondaj_depth=current_sondaj_depth,
                valid_sondaj_nolari=valid_sondaj_nolari,
                settings=project_spt_settings(),
            )

        def duplicate_keys():
            return spt_duplicate_keys(records)

        def visible_by_filter(record):
            mode = filter_var.get()
            quality = record.get("quality", {})
            if mode == "Tümü":
                return True
            if mode == "Aktarılacak":
                return record.get("include", True)
            if mode == "Hatalı":
                return quality.get("level") == "error"
            if mode == "Uyarılı":
                return quality.get("level") == "warning"
            if mode == "Düşük Güven":
                if record.get("record_type") == "queue":
                    return False
                return safe_float(record["kayit"].guven) and safe_float(record["kayit"].guven) < project_spt_settings()["guven_esigi"]
            return True

        def refresh_tree(keep_selection=True):
            previous = selected_item["id"] if keep_selection else None
            previous_record = tree_items.get(previous) if previous else None
            tree.delete(*tree.get_children())
            tree_items.clear()
            duplicates = duplicate_keys()
            ok = warn = err = included = queue_count = spt_count = 0
            issue_list.delete(0, tk.END)
            context_map = context_issues()
            for idx, record in enumerate(records):
                kayit = record["kayit"]
                key = (kayit.sondaj_no.strip(), round(safe_float(kayit.derinlik), 2))
                record["quality"] = record_quality(record, duplicate=key in duplicates, context_messages=context_map.get(id(record), []))
                quality = record["quality"]
                is_queue = record.get("record_type") == "queue"
                if is_queue:
                    queue_count += 1
                else:
                    spt_count += 1
                if record.get("include", True) and not is_queue:
                    included += 1
                if quality["level"] == "error":
                    err += 1
                elif quality["level"] == "warning":
                    warn += 1
                elif quality["level"] == "ok":
                    ok += 1
                if quality["level"] in ("error", "warning"):
                    issue_label = kayit.kaynak if is_queue else f"{kayit.sondaj_no or '-'} {kayit.derinlik or '-'}"
                    issue_list.insert(tk.END, f"{issue_label}: {quality['message']}")
                if not visible_by_filter(record):
                    continue
                tag = quality["level"]
                if is_queue:
                    row_values = (
                        "",
                        "Dosya",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        quality["message"],
                        kayit.kaynak,
                    )
                else:
                    row_values = (
                        "✓" if record.get("include", True) else "",
                        kayit.sondaj_no,
                        kayit.derinlik,
                        kayit.v15,
                        kayit.v30,
                        kayit.v45,
                        kayit.n30,
                        kayit.guven,
                        quality["message"],
                        kayit.kaynak,
                    )
                item_id = tree.insert(
                    "",
                    "end",
                    values=row_values,
                    tags=(tag,),
                )
                tree_items[item_id] = record
                record["item_id"] = item_id
                if previous_record is record:
                    tree.selection_set(item_id)
            for msg in import_warnings[-10:]:
                issue_list.insert(tk.END, msg)
            summary_var.set(f"SPT: {spt_count} | Kuyruk: {queue_count} | Aktarılacak: {included} | Hazır: {ok} | Uyarı: {warn} | Hata: {err}")
            status_var.set(f"{spt_count} SPT satırı yüklendi. {included} satır aktarım için seçili.")

        def load_detail(record):
            kayit = record["kayit"] if record else None
            for ent in detail_entries.values():
                ent.delete(0, tk.END)
            if not kayit:
                preview_controller.draw_message("Satır seçildiğinde kaynak burada görünür.")
                return
            values = {
                "sondaj_no": kayit.sondaj_no,
                "derinlik": kayit.derinlik,
                "v15": kayit.v15,
                "v30": kayit.v30,
                "v45": kayit.v45,
                "n30": kayit.n30,
            }
            for key, value in values.items():
                detail_entries[key].insert(0, value)
            preview_controller.show(kayit)

        preview_canvas.bind("<Configure>", preview_controller.schedule_redraw)
        preview_controller.draw_message("Satır seçildiğinde kaynak burada görünür.")

        def selected_record():
            selection = tree.selection()
            if not selection:
                return None
            selected_item["id"] = selection[0]
            return tree_items.get(selection[0])

        def select_tree_record(record):
            if not record:
                return
            item_id = record.get("item_id")
            if not item_id or item_id not in tree_items:
                refresh_tree(keep_selection=False)
                item_id = record.get("item_id")
            if item_id:
                selected_item["id"] = item_id
                tree.selection_set(item_id)
                tree.focus(item_id)
                tree.see(item_id)
                load_detail(record)

        def on_select(event=None):
            load_detail(selected_record())

        def toggle_selected(event=None):
            record = selected_record()
            if not record:
                return "break"
            if record.get("record_type") == "queue":
                return "break"
            record["include"] = not record.get("include", True)
            refresh_tree()
            load_detail(record)
            return "break"

        def update_selected_from_form(silent=False):
            record = selected_record()
            if not record:
                if not silent:
                    messagebox.showwarning("SPT Merkezi", "Önce bir satır seçin.")
                return None
            if record.get("record_type") == "queue":
                return None
            old = record["kayit"]
            kayit = kayit_normalize_et({
                "sondaj_no": detail_entries["sondaj_no"].get(),
                "derinlik": detail_entries["derinlik"].get(),
                "v15": detail_entries["v15"].get(),
                "v30": detail_entries["v30"].get(),
                "v45": detail_entries["v45"].get(),
                "n30": detail_entries["n30"].get(),
                "guven": old.guven,
                "kaynak": old.kaynak,
                "kaynak_yolu": old.kaynak_yolu,
            }, target_var.get())
            kayit.sondaj_no = normalize_sondaj_no(kayit.sondaj_no, target_var.get())
            record["kayit"] = kayit
            record["include"] = True
            spt_gecmis_kaydet("duzeltildi", kayit, {"onceki": old.to_dict()})
            refresh_tree()
            load_detail(record)
            return kayit

        def n30_selected():
            record = selected_record()
            if not record:
                return
            if record.get("record_type") == "queue":
                return
            entries = detail_entries
            calculated = n30_hesapla(entries["v30"].get(), entries["v45"].get(), "")
            if calculated:
                entries["n30"].delete(0, tk.END)
                entries["n30"].insert(0, calculated)
                update_selected_from_form(silent=True)

        def n30_all():
            for record in records:
                if record.get("record_type") == "queue":
                    continue
                kayit = record["kayit"]
                calculated = n30_hesapla(kayit.v30, kayit.v45, kayit.n30 if kayit.n30 == "R" else "")
                if calculated:
                    kayit.n30 = calculated
            refresh_tree()
            load_detail(selected_record())

        def delete_selected_record(event=None):
            record = selected_record()
            if not record:
                return "break"
            kayit = record["kayit"]
            if record in records:
                records.remove(record)
                if record.get("record_type") == "queue":
                    remove_from_main_queue(record.get("queue_path", kayit.kaynak_yolu))
                else:
                    spt_gecmis_kaydet("silindi", kayit, {"kaynak": kayit.kaynak})
            selected_item["id"] = None
            refresh_tree(keep_selection=False)
            load_detail(None)
            status_var.set("Seçili SPT okuması listeden silindi.")
            return "break"

        def reread_selected_with_pro():
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
            self.pencere_hazirla(progress_win, "Gemini Pro Tekrar Oku", "460x150", (420, 130), modal=False)
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
                    self.root.after(0, lambda: finish(raw_items=raw_items))
                except Exception as exc:
                    self.root.after(0, lambda: finish(hata=exc))

            threading.Thread(target=worker, daemon=True).start()

        def fill_target_for_selected():
            hedef = target_var.get().strip()
            if not hedef:
                return
            for record in records:
                if record.get("record_type") != "queue" and record.get("include", True):
                    record["kayit"].sondaj_no = normalize_sondaj_no(hedef, hedef)
            refresh_tree()
            load_detail(selected_record())

        def teach_selected():
            record = selected_record()
            if not record:
                messagebox.showwarning("Doğrusunu Öğret", "Önce düzeltilmiş bir satır seçin.")
                return
            kayit = update_selected_from_form(silent=True)
            if not kayit:
                return
            corrected = {
                "sondaj_no": kayit.sondaj_no,
                "derinlik": kayit.derinlik,
                "spt": "-".join([v for v in (kayit.v15, kayit.v30, kayit.v45) if v]),
                "n30": kayit.n30,
            }
            try:
                spt_ogrenme_kaydet(kayit, corrected, "RaporPro SPT Merkezi")
                self.set_status("SPT doğrusu öğrenme havuzuna kaydedildi.", level="success")
                status_var.set("Doğrusu öğrenme havuzuna kaydedildi.")
            except Exception as exc:
                messagebox.showerror("Doğrusunu Öğret", f"Öğrenme kaydı oluşturulamadı:\n{exc}")

        def show_history():
            show_spt_history(self, win)

        def export_source_report():
            export_spt_source_report(self, records)
        def queue_record_for_path(path):
            key = source_unique_key(path)
            for record in records:
                if record.get("record_type") == "queue" and source_unique_key(record.get("queue_path", "")) == key:
                    return record
            return None

        def ensure_queue_record(path, status="ready", message=None):
            record = queue_record_for_path(path)
            if record is None:
                name = os.path.basename(path)
                record = {
                    "include": False,
                    "kayit": SPTKaydi(kaynak=name, kaynak_yolu=path),
                    "source": name,
                    "record_type": "queue",
                    "queue_path": path,
                    "queue_status": status,
                    "queue_message": message or "Okumaya hazır",
                }
                records.append(record)
            else:
                record["queue_status"] = status
                record["queue_message"] = message or record.get("queue_message") or "Okumaya hazır"
            return record

        def set_queue_record_status(path, status, message=None, refresh=True):
            record = ensure_queue_record(path, status=status, message=message)
            record["queue_status"] = status
            if message:
                record["queue_message"] = message
            if refresh:
                refresh_tree()
            return record

        def remove_queue_record(path, refresh=False):
            record = queue_record_for_path(path)
            if record in records:
                records.remove(record)
                if selected_item.get("id") and tree_items.get(selected_item["id"]) is record:
                    selected_item["id"] = None
            if refresh:
                refresh_tree(keep_selection=False)

        def clear_queue_records():
            records[:] = [record for record in records if record.get("record_type") != "queue"]
            selected_item["id"] = None
            refresh_tree(keep_selection=False)

        def refresh_main_queue_status(extra=None):
            if main_read_state["active"]:
                text = (
                    f"Okunuyor: {main_read_state['done']}/{main_read_state['total']} dosya | "
                    f"Eklenen satır: {main_read_state['added']} | "
                    f"Tekrar: {main_read_state['skipped']} | "
                    f"Okunamayan: {main_read_state['failed']}"
                )
            else:
                text = f"Kuyruk: {len(main_queue_paths)} fotoğraf"
                if not main_queue_paths:
                    text += " | Fotoğraf veya klasörü bu ekrana sürükleyebilirsiniz."
            if extra:
                text += f" | {extra}"
            main_queue_status_var.set(text)
            start_btn = main_queue_buttons.get("start")
            if start_btn:
                start_btn.configure(state=("disabled" if main_read_state["active"] or not main_queue_paths else "normal"))
            stop_btn = main_queue_buttons.get("stop")
            if stop_btn:
                stop_btn.configure(state=("normal" if main_read_state["active"] else "disabled"))

        def remove_from_main_queue(path):
            key = source_unique_key(path)
            main_queue_paths[:] = [item for item in main_queue_paths if source_unique_key(item) != key]

        def add_to_main_photo_queue(sources):
            found_paths = collect_image_paths(sources, recursive=main_queue_recursive_var.get())
            existing = {source_unique_key(path) for path in main_queue_paths}
            existing.update(
                source_unique_key(record.get("queue_path", ""))
                for record in records
                if record.get("record_type") == "queue"
            )
            added = 0
            skipped_duplicate = 0
            for path in found_paths:
                key = source_unique_key(path)
                if key in existing:
                    skipped_duplicate += 1
                    continue
                main_queue_paths.append(os.path.abspath(path))
                ensure_queue_record(os.path.abspath(path), status="ready", message="Okumaya hazır")
                existing.add(key)
                added += 1
            main_queue_paths.sort(key=lambda item: item.lower())
            if added:
                refresh_tree()
            if added:
                status_var.set(f"SPT kuyruğuna {added} fotoğraf eklendi.")
                refresh_main_queue_status(f"{added} yeni fotoğraf")
            elif skipped_duplicate:
                status_var.set("SPT kuyruğunda tekrar dosyalar atlandı.")
                refresh_main_queue_status("tekrar dosyalar atlandı")
            else:
                status_var.set("Geçerli fotoğraf bulunamadı.")
                refresh_main_queue_status("JPG, PNG, BMP veya WEBP ekleyin")
            return added, skipped_duplicate, len(found_paths)

        def add_main_photos():
            paths = filedialog.askopenfilenames(
                title="SPT Fotoğraflarını Kuyruğa Ekle",
                initialdir=self._spt_initial_dir(),
                filetypes=[("Resimler", "*.jpg *.jpeg *.png *.bmp *.webp *.JPG *.JPEG *.PNG"), ("Tüm Dosyalar", "*.*")],
                parent=win,
            )
            if paths:
                add_to_main_photo_queue(paths)

        def add_main_folder():
            folder = filedialog.askdirectory(title="SPT Fotoğraf Klasörü Seç", initialdir=self._spt_initial_dir(), parent=win)
            if folder:
                add_to_main_photo_queue([folder])

        def clear_main_photo_queue():
            if main_read_state["active"]:
                messagebox.showwarning("SPT Fotoğraf", "Okuma devam ederken kuyruk temizlenemez.", parent=win)
                return
            main_queue_paths.clear()
            clear_queue_records()
            refresh_main_queue_status("kuyruk temizlendi")

        def spt_unique_key(kayit, fallback_source=""):
            return build_spt_unique_key(kayit, fallback_source=fallback_source, default_sondaj_no=target_var.get())

        def spt_location_key(kayit, fallback_source=""):
            return build_spt_location_key(kayit, default_sondaj_no=target_var.get())

        def add_result(sonuc, source_label, append=True):
            if not append:
                records.clear()
                import_warnings.clear()
            import_warnings.extend(sonuc.uyarilar or [])
            existing_keys = {
                spt_unique_key(record["kayit"], record.get("source", ""))
                for record in records
                if record.get("record_type") != "queue"
            }
            existing_locations = {
                spt_location_key(record["kayit"], record.get("source", ""))
                for record in records
                if record.get("record_type") != "queue"
            }
            skipped_duplicates = 0
            added_count = 0
            for kayit in sonuc.kayitlar:
                kayit.sondaj_no = normalize_sondaj_no(kayit.sondaj_no, target_var.get())
                if not kayit.sondaj_no:
                    kayit.sondaj_no = target_var.get().strip()
                key = spt_unique_key(kayit, source_label)
                loc_key = spt_location_key(kayit, source_label)
                loc_is_valid = bool(loc_key[0] and loc_key[1] > 0)
                if key in existing_keys or (loc_is_valid and loc_key in existing_locations):
                    skipped_duplicates += 1
                    continue
                existing_keys.add(key)
                if loc_is_valid:
                    existing_locations.add(loc_key)
                records.append({
                    "include": bool(kayit.derinlik and (kayit.v15 or kayit.v30 or kayit.v45 or kayit.n30)),
                    "kayit": kayit,
                    "source": source_label,
                })
                added_count += 1
                spt_gecmis_kaydet("okundu", kayit, {"kaynak": source_label, "aktarildi": False})
            if skipped_duplicates:
                import_warnings.append(f"{skipped_duplicates} tekrar SPT satırı aynı kuyu/derinlik olduğu için atlandı.")
            refresh_tree(keep_selection=False)
            if records:
                first = next(iter(tree.get_children()), None)
                if first:
                    tree.selection_set(first)
                    on_select()
            return added_count, skipped_duplicates

        def start_main_photo_queue():
            if main_read_state["active"]:
                messagebox.showinfo("SPT Fotoğraf", "Fotoğraf okuma zaten devam ediyor.", parent=win)
                return
            paths = []
            seen = set()
            for path in main_queue_paths:
                key = source_unique_key(path)
                if key in seen:
                    continue
                seen.add(key)
                paths.append(path)
            if len(paths) != len(main_queue_paths):
                main_queue_paths[:] = paths
                status_var.set("SPT fotoğraf kuyruğundaki tekrar dosyalar temizlendi.")
            if not paths:
                messagebox.showwarning("SPT Fotoğraf", "Başlatmak için önce fotoğraf ekleyin.", parent=win)
                refresh_main_queue_status()
                return

            ayarlar = spt_ayarlarini_yukle()
            settings = project_spt_settings()
            target_no = target_var.get()
            stop_event = threading.Event()
            main_read_state.update({
                "active": True,
                "stop_event": stop_event,
                "total": len(paths),
                "done": 0,
                "added": 0,
                "skipped": 0,
                "failed": 0,
            })
            for path in paths:
                set_queue_record_status(path, "ready", "Okumaya hazır", refresh=False)
            refresh_tree()
            refresh_main_queue_status("başladı")
            status_var.set(f"SPT fotoğraf okuma başladı: {len(paths)} dosya.")

            def mark_current_file(path, index):
                if not win.winfo_exists():
                    return
                record = set_queue_record_status(path, "reading", f"Okunuyor ({index}/{len(paths)})", refresh=True)
                select_tree_record(record)
                refresh_main_queue_status(f"{os.path.basename(path)} okunuyor")

            def finish_file(path, sonuc=None, hata=None):
                if not win.winfo_exists():
                    return
                name = os.path.basename(path)
                main_read_state["done"] += 1
                if hata:
                    main_read_state["failed"] += 1
                    import_warnings.append(f"{name}: okunamadı ({hata})")
                    record = set_queue_record_status(path, "error", f"Okunamadı: {hata}", refresh=True)
                    select_tree_record(record)
                    refresh_main_queue_status(f"{name} okunamadı")
                    status_var.set(f"SPT okuma: {main_read_state['done']}/{main_read_state['total']} dosya.")
                    return

                if not sonuc or not sonuc.kayitlar:
                    main_read_state["failed"] += 1
                    reason = "SPT verisi bulunamadı"
                    if sonuc and sonuc.uyarilar:
                        reason = str(sonuc.uyarilar[0])
                    import_warnings.append(f"{name}: {reason}")
                    record = set_queue_record_status(path, "error", reason, refresh=True)
                    select_tree_record(record)
                    refresh_main_queue_status(f"{name} okunamadı")
                    status_var.set(f"SPT okuma: {main_read_state['done']}/{main_read_state['total']} dosya.")
                    return

                added_count, skipped_duplicates = add_result(sonuc, name, append=True)
                if added_count:
                    main_read_state["added"] += added_count
                    remove_from_main_queue(path)
                    remove_queue_record(path, refresh=True)
                elif skipped_duplicates:
                    main_read_state["skipped"] += skipped_duplicates
                    remove_from_main_queue(path)
                    import_warnings.append(f"{name}: okundu, aynı kuyu/derinlik zaten listede olduğu için yeni satır eklenmedi.")
                    record = set_queue_record_status(path, "skipped", "Okundu, aynı kuyu/derinlik zaten listede", refresh=True)
                    select_tree_record(record)
                else:
                    main_read_state["failed"] += 1
                    import_warnings.append(f"{name}: okundu ancak aktarılacak SPT satırı oluşmadı.")
                    record = set_queue_record_status(path, "error", "Okundu ancak aktarılacak SPT satırı oluşmadı", refresh=True)
                    select_tree_record(record)
                refresh_main_queue_status(f"{name} tamamlandı")
                status_var.set(f"SPT okuma: {main_read_state['done']}/{main_read_state['total']} dosya.")

            def finish_all(cancelled=False):
                if not win.winfo_exists():
                    return
                main_read_state["active"] = False
                main_read_state["stop_event"] = None
                if cancelled:
                    refresh_main_queue_status("durduruldu")
                    status_var.set("SPT fotoğraf okuma durduruldu.")
                    return
                if main_read_state["failed"]:
                    refresh_main_queue_status(f"{main_read_state['failed']} dosya kuyrukta kaldı")
                    status_var.set(
                        f"SPT okuma tamamlandı. {main_read_state['failed']} dosyada sonuç bulunamadı; kuyrukta kaldı."
                    )
                    messagebox.showwarning(
                        "SPT Fotoğraf",
                        f"Okuma tamamlandı; {main_read_state['failed']} dosyada SPT satırı bulunamadı veya okunamadı.\n"
                        "Bu dosyalar kuyrukta bırakıldı, isterseniz Pro ile tekrar deneyebilirsiniz.",
                        parent=win,
                    )
                else:
                    refresh_main_queue_status("okuma tamamlandı")
                    status_var.set("SPT fotoğraf okuma tamamlandı.")

            def make_progress_callback(file_index):
                def progress_callback(done, total, name, state):
                    def update():
                        if not win.winfo_exists():
                            return
                        status_var.set(f"SPT okuma: {file_index}/{len(paths)} | {name} | {state}")
                    self.root.after(0, update)
                return progress_callback

            def worker():
                cancelled = False
                for idx, path in enumerate(paths, start=1):
                    if stop_event.is_set():
                        cancelled = True
                        break
                    self.root.after(0, lambda path=path, idx=idx: mark_current_file(path, idx))
                    try:
                        sonuc = fotograflardan_spt_oku(
                            [path],
                            default_sondaj_no=target_no,
                            ayarlar=ayarlar,
                            progress_callback=make_progress_callback(idx),
                            stop_event=stop_event,
                            auto_pro=settings["auto_pro"],
                        )
                    except Exception as exc:
                        self.root.after(0, lambda path=path, exc=exc: finish_file(path, hata=exc))
                        continue
                    if stop_event.is_set() and not sonuc.kayitlar:
                        cancelled = True
                        break
                    self.root.after(0, lambda path=path, sonuc=sonuc: finish_file(path, sonuc=sonuc))
                self.root.after(0, lambda cancelled=cancelled or stop_event.is_set(): finish_all(cancelled))

            threading.Thread(target=worker, daemon=True).start()

        def stop_main_photo_queue():
            stop_event = main_read_state.get("stop_event")
            if stop_event:
                stop_event.set()
                refresh_main_queue_status("durduruluyor")
                status_var.set("SPT fotoğraf okuma durduruluyor...")

        def parse_main_drop_paths(data):
            try:
                return [item for item in win.tk.splitlist(data) if item]
            except Exception:
                return [item for item in str(data or "").split() if item]

        def on_main_drop(event):
            added, skipped_duplicate, found = add_to_main_photo_queue(parse_main_drop_paths(getattr(event, "data", "")))
            if added:
                status_var.set(f"Sürükle-bırak ile {added} fotoğraf eklendi.")
            elif skipped_duplicate:
                status_var.set("Sürükle-bırak: tekrar dosyalar atlandı.")
            elif not found:
                status_var.set("Sürükle-bırak: geçerli fotoğraf bulunamadı.")
            return "break"

        def enable_main_drag_drop():
            try:
                from tkinterdnd2 import DND_FILES
            except Exception:
                main_dnd_status_var.set("Sürükle-bırak için tkinterdnd2 paketi gerekir.")
                return False
            enabled = False
            for target in (win, queue_bar, left, table_frame, tree):
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", on_main_drop)
                    enabled = True
                except Exception:
                    continue
            if enabled:
                main_dnd_status_var.set("Dosyaları buraya bırakabilirsiniz.")
            else:
                main_dnd_status_var.set("Sürükle-bırak bu pencerede etkinleşmedi.")
            return enabled

        def import_excel():
            path = filedialog.askopenfilename(
                title="SPT Okuma Excel Sonucunu Al",
                initialdir=self._spt_initial_dir(),
                filetypes=[("Excel", "*.xlsx *.xlsm"), ("Tüm Dosyalar", "*.*")],
            )
            if not path:
                return
            try:
                sonuc = excelden_spt_oku(path, default_sondaj_no=target_var.get())
            except Exception as exc:
                messagebox.showerror("SPT Excel", f"Excel dosyası okunamadı:\n{exc}")
                return
            if not sonuc.kayitlar:
                messagebox.showwarning("SPT Excel", "Dosyada aktarılacak SPT satırı bulunamadı.")
                return
            add_result(sonuc, os.path.basename(path), append=True)

        def start_photo_reading(paths):
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
            self.pencere_hazirla(progress_win, "SPT Fotoğraf Okuma", "500x170", (460, 150), modal=False)
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
                self.root.after(0, update)

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
                    self.root.after(0, lambda: finish(sonuc=sonuc))
                except Exception as exc:
                    self.root.after(0, lambda: finish(hata=exc))

            threading.Thread(target=worker, daemon=True).start()

        def import_photos():
            open_spt_photo_queue_dialog(
                self,
                win,
                self._spt_initial_dir(),
                add_to_main_photo_queue,
                start_main_photo_queue,
                status_var,
            )
        def import_cropped_photo():
            open_spt_crop_dialog(
                self,
                win,
                self._spt_initial_dir(),
                target_var,
                project_spt_settings,
                add_result,
            )
        def apply_import(close=False):
            apply_spt_import(
                self,
                records,
                update_selected_from_form,
                update_same_var,
                clear_target_var,
                status_var,
                close=close,
                window=win,
            )
        def settings_dialog():
            open_spt_settings_dialog(self, win, auto_pro_var, refresh_tree, status_var)
        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<space>", toggle_selected)
        tree.bind("<Double-1>", toggle_selected)
        tree.bind("<Delete>", delete_selected_record)
        filter_var.trace_add("write", lambda *_: refresh_tree())

        self.modern_button(source_group, text="Excel'den Al", command=import_excel, role="primary").pack(side="left", padx=2)
        self.modern_button(source_group, text="Foto Ekle", command=add_main_photos, role="success").pack(side="left", padx=2)
        main_queue_buttons["start"] = self.modern_button(source_group, text="Başlat", command=start_main_photo_queue, role="success")
        main_queue_buttons["start"].pack(side="left", padx=2)
        self.modern_button(source_group, text="Kırp/Oku", command=import_cropped_photo, role="success").pack(side="left", padx=2)
        self.modern_button(source_group, text="Geçmiş", command=show_history, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(source_group, text="Ayarlar", command=settings_dialog, role="warning").pack(side="left", padx=2)

        ttk.Label(queue_bar, textvariable=main_queue_status_var, foreground="#2874A6").pack(side="left", fill="x", expand=True)
        self.modern_button(queue_bar, text="Klasör Ekle", command=add_main_folder, role="success", outline=True).pack(side="left", padx=3)
        self.modern_button(queue_bar, text="Kuyruğu Temizle", command=clear_main_photo_queue, role="neutral", outline=True).pack(side="left", padx=3)
        main_queue_buttons["stop"] = self.modern_button(queue_bar, text="Durdur", command=stop_main_photo_queue, role="danger", state="disabled")
        main_queue_buttons["stop"].pack(side="left", padx=3)
        ttk.Checkbutton(queue_bar, text="Alt klasörleri tara", variable=main_queue_recursive_var).pack(side="left", padx=6)
        ttk.Label(queue_bar, textvariable=main_dnd_status_var, foreground="#555555").pack(side="right", padx=(8, 0))

        ttk.Checkbutton(pro_group, text="Otomatik Pro", variable=auto_pro_var, command=save_auto_pro_setting).pack(side="left", padx=3)
        self.modern_button(pro_group, text="Seçiliyi Pro ile Oku", command=reread_selected_with_pro, role="accent", outline=True).pack(side="left", padx=2)

        ttk.Label(target_group, text="Hedef").pack(side="left", padx=(0, 3))
        ttk.Combobox(target_group, textvariable=target_var, values=sondaj_nolari, width=12).pack(side="left", padx=3)
        self.modern_button(target_group, text="Seçiliye Doldur", command=fill_target_for_selected, role="accent", outline=True).pack(side="left", padx=2)
        ttk.Checkbutton(target_group, text="Aynı derinliği güncelle", variable=update_same_var).pack(side="left", padx=5)
        ttk.Checkbutton(target_group, text="Önce temizle", variable=clear_target_var).pack(side="left", padx=5)

        ttk.Combobox(filter_group, textvariable=filter_var, values=["Tümü", "Aktarılacak", "Hatalı", "Uyarılı", "Düşük Güven"], state="readonly", width=13).pack(side="left", padx=3)
        self.modern_button(filter_group, text="N30 Tümü", command=n30_all, role="warning", outline=True).pack(side="left", padx=2)
        self.modern_button(filter_group, text="Kaynak Raporu", command=export_source_report, role="success", outline=True).pack(side="left", padx=2)

        detail_btns = ttk.Frame(detail)
        detail_btns.grid(row=3, column=0, columnspan=4, sticky="e", pady=(8, 0))
        self.modern_button(detail_btns, text="N30 Hesapla", command=n30_selected, role="warning", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Satırı Güncelle", command=update_selected_from_form, role="accent", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Pro ile Oku", command=reread_selected_with_pro, role="accent", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Doğrusunu Öğret", command=teach_selected, role="success", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Al / Alma", command=toggle_selected, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Sil", command=delete_selected_record, role="danger").pack(side="left", padx=2)

        self.modern_button(bottom, text="Aktar", command=lambda: apply_import(False), role="success").pack(side="right", padx=3)
        self.modern_button(bottom, text="Aktar ve Kapat", command=lambda: apply_import(True), role="primary").pack(side="right", padx=3)
        self.modern_button(bottom, text="Kapat", command=win.destroy, role="secondary").pack(side="right", padx=3)

        enable_main_drag_drop()
        refresh_main_queue_status()

        if initial_sonuc:
            add_result(initial_sonuc, str(initial_source or "SPT"), append=True)
        if baslat == "excel":
            win.after(150, import_excel)
        elif baslat == "foto":
            win.after(150, add_main_photos)
