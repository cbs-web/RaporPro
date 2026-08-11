import os
import threading
import tkinter as tk
from tkinter import Toplevel, filedialog, messagebox, ttk

from sabitler import *
from ui_spt_okuma_aktar import apply_spt_import, undo_last_spt_import
from spt_okuma_motoru import (
    SPTKaydi,
    excelden_spt_oku,
    fotograflardan_spt_oku,
    kayit_normalize_et,
    n30_hesapla,
    spt_gecmis_kaydet,
    spt_ogrenme_kaydet,
    spt_ayarlarini_yukle,
    spt_kayit_puani,
    normalize_sondaj_no,
)
from yardimcilar import safe_float
from ui_spt_okuma_yardimci import (
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
    open_spt_settings_dialog,
    show_spt_history,
)
from ui_spt_okuma_preview import SPTPreviewController
from ui_spt_okuma_pro import (
    reread_selected_with_pro as run_spt_pro_reread,
    reread_selected_with_strongest as run_spt_strongest_reread,
)
from ui_spt_okuma_kuyruk import SPTFotografKuyrugu


def _tree_item_gecerli(tree, tree_items, item_id, record=None):
    if not item_id:
        return False
    try:
        if not tree.exists(item_id):
            return False
    except Exception:
        return False
    mapped = tree_items.get(item_id)
    if mapped is None:
        return False
    return record is None or mapped is record


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
        ayarlar = (getattr(self, "veri", {}) or {}).get("ayarlar", {}) or {}
        aktif_dosya = getattr(self, "aktif_dosya_yolu", None)
        user_dir = os.path.expanduser("~")
        candidates = [
            ayarlar.get("spt_son_klasor"),
            os.path.dirname(os.path.abspath(aktif_dosya)) if aktif_dosya else None,
            os.path.join(user_dir, "Desktop"),
            user_dir,
            os.getcwd(),
        ]
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                return os.path.abspath(candidate)
        return os.getcwd()

    def _spt_son_klasoru_kaydet(self, path):
        raw = str(path or "").strip()
        if not raw:
            return
        folder = raw if os.path.isdir(raw) else os.path.dirname(os.path.abspath(raw))
        if os.path.isdir(folder):
            self.veri.setdefault("ayarlar", {})["spt_son_klasor"] = folder

    def _spt_dis_servis_onayi_al(self, ayarlar=None, parent=None):
        ayarlar = ayarlar or spt_ayarlarini_yukle()
        providers = [str(ayarlar.get("aktif_motor") or "gemini").strip().lower()]
        extra_providers = ayarlar.get("ek_motorlar") or []
        if isinstance(extra_providers, str):
            extra_providers = [extra_providers]
        providers.extend(str(item or "").strip().lower() for item in extra_providers)
        providers = [
            "openai" if provider in ("openai_pro", "openai_ust") else provider
            for provider in providers
        ]
        providers = list(
            dict.fromkeys(
                provider
                for provider in providers
                if provider and provider not in ("yerel", "local", "kapali", "none")
            )
        )
        if not providers:
            return True
        provider_labels = {
            "openai": "OpenAI (GPT-5.6)",
            "gemini": "Google Gemini 3.6 Flash",
        }
        project_settings = self.veri.setdefault("ayarlar", {})
        pending = [
            provider
            for provider in providers
            if str(
                project_settings.get(f"spt_dis_servis_onayi_{provider}", "")
            ).strip().lower()
            not in ("1", "true", "evet")
        ]
        if not pending:
            return True
        provider_label = " ve ".join(
            provider_labels.get(provider, provider)
            for provider in pending
        )
        accepted = messagebox.askyesno(
            "SPT Fotoğrafı Dış Servise Gönderilecek",
            (
                f"SPT fotoğrafı okunmak üzere {provider_label} hizmetine gönderilecektir.\n\n"
                "Fotoğraf içeriği cihazınızdan çıkar ve bu sağlayıcı tarafından işlenir. "
                "Fotoğrafta paylaşılmaması gereken kişisel veya gizli bilgi bulunmadığını "
                "kontrol edin.\n\nDevam etmeyi kabul ediyor musunuz?"
            ),
            parent=parent,
        )
        if accepted:
            for provider in pending:
                project_settings[f"spt_dis_servis_onayi_{provider}"] = "1"
        return bool(accepted)

    def spt_okuma_merkezi_ac(self, baslat=None, initial_source=None, initial_sonuc=None):
        self.sondaj_verilerini_kaydet(silent=True)
        try:
            from tkinterdnd2 import TkinterDnD
            win = TkinterDnD.Toplevel(self.root)
        except Exception:
            win = Toplevel(self.root)
        self.pencere_hazirla(win, "SPT Okuma Merkezi", "1360x840", (1080, 700), modal=False)

        records = []
        queue_records = []
        tree_items = {}
        selected_item = {"id": None}
        preview_image = {"ref": None}
        import_warnings = []
        main_queue_controller = SPTFotografKuyrugu(recursive=True)
        main_queue_paths = main_queue_controller.paths
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
        view_var = tk.StringVar(value="Kuyruk")
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
            status_var.set(
                "Otomatik ikinci okuma açık."
                if auto_pro_var.get()
                else "Otomatik ikinci okuma kapalı."
            )

        header = tk.Frame(win, bg="#FFFFFF", padx=12, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="SPT Okuma Merkezi", bg="#FFFFFF", fg=COLOR_PRIMARY, font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(header, textvariable=status_var, bg="#FFFFFF", fg="#555555", font=("Segoe UI", 9)).pack(side="left", padx=14)

        toolbar = ttk.Frame(win, padding=(8, 8))
        toolbar.pack(fill="x")
        source_group = ttk.LabelFrame(toolbar, text="Fotoğraf Kuyruğu", padding=(5, 3))
        target_group = ttk.LabelFrame(toolbar, text="Aktarım Hedefi", padding=(5, 3))
        advanced_group = ttk.Frame(toolbar)
        source_group.pack(side="left", padx=3)
        target_group.pack(side="left", padx=3)
        advanced_group.pack(side="right", padx=3)

        queue_bar = ttk.Frame(win, padding=(8, 0, 8, 6))
        queue_bar.pack(fill="x")

        bottom = ttk.Frame(win, padding=8)
        bottom.pack(side="bottom", fill="x")

        main = ttk.Panedwindow(win, orient="horizontal")
        main.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=6)
        main.add(right, weight=5)

        view_bar = ttk.Frame(left, padding=(0, 0, 0, 6))
        view_bar.pack(fill="x")
        ttk.Label(view_bar, text="Göster:").pack(side="left", padx=(0, 6))
        for view_name in ("Kuyruk", "Sonuçlar", "Kontrol"):
            ttk.Radiobutton(
                view_bar,
                text=view_name,
                value=view_name,
                variable=view_var,
                style="Toolbutton",
            ).pack(side="left", padx=2)
        ttk.Separator(view_bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(view_bar, text="Ayrıntı:").pack(side="left", padx=(0, 4))
        filter_combo = ttk.Combobox(
            view_bar,
            textvariable=filter_var,
            values=["Tümü", "Aktarılacak", "Hatalı", "Uyarılı", "Bilgi", "Düşük Güven"],
            state="readonly",
            width=13,
        )
        filter_combo.pack(side="left")

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
        tree.tag_configure("ok", background="#FFFFFF")
        tree.tag_configure("warning", background="#FFFFFF")
        tree.tag_configure("error", background="#FFFFFF")
        tree.tag_configure("disabled", foreground="#888888")
        tree.tag_configure("queued", background="#EBF5FB")
        tree.tag_configure("reading", background="#D6EAF8")
        tree.tag_configure("info", background="#FFFFFF")

        right_pane = ttk.Panedwindow(right, orient="vertical")
        right_pane.pack(fill="both", expand=True)
        preview_area = ttk.Frame(right_pane)
        detail_area = ttk.Frame(right_pane)
        right_pane.add(preview_area, weight=6)
        right_pane.add(detail_area, weight=4)

        preview = ttk.LabelFrame(preview_area, text="Kaynak Önizleme", padding=6)
        preview.pack(fill="both", expand=True)
        preview_tools = ttk.Frame(preview)
        preview_tools.pack(fill="x", pady=(0, 5))
        preview_canvas = tk.Canvas(
            preview,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#D5DBDB",
            width=620,
            height=430,
        )
        preview_canvas.pack(fill="both", expand=True)
        preview_controller = SPTPreviewController(win, preview_canvas, preview_image)
        self.modern_button(preview_tools, text="+", command=preview_controller.zoom_in, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(preview_tools, text="-", command=preview_controller.zoom_out, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(preview_tools, text="Döndür", command=preview_controller.rotate, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(preview_tools, text="Sığdır", command=preview_controller.fit, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(preview_tools, text="Orijinali Aç", command=preview_controller.open_original, role="primary", outline=True).pack(side="right", padx=2)

        summary = ttk.LabelFrame(detail_area, text="Kalite Özeti", padding=6)
        summary.pack(fill="x", pady=(0, 6))
        summary_var = tk.StringVar(value="Henüz veri yok.")
        ttk.Label(summary, textvariable=summary_var, justify="left", wraplength=520).pack(anchor="w", fill="x")

        detail_notebook = ttk.Notebook(detail_area)
        detail_notebook.pack(fill="both", expand=True)
        selected_tab = ttk.Frame(detail_notebook)
        issues_tab = ttk.Frame(detail_notebook)
        detail_notebook.add(selected_tab, text="Seçili Satır")
        detail_notebook.add(issues_tab, text="Kontrol Notları")

        detail = ttk.Frame(selected_tab, padding=6)
        detail.pack(fill="both", expand=True)
        detail_entries = {}
        entry_style = ttk.Style(win)
        entry_style.configure("SPT.Normal.TEntry", fieldbackground="#FFFFFF")
        entry_style.configure("SPT.Warning.TEntry", fieldbackground="#FFF3CD")
        entry_style.configure("SPT.Error.TEntry", fieldbackground="#F8D7DA")
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
        normalization_var = tk.StringVar(value="")
        ttk.Label(
            detail,
            textvariable=normalization_var,
            foreground="#2874A6",
            wraplength=500,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(5, 0))
        issues = ttk.Frame(issues_tab, padding=6)
        issues.pack(fill="both", expand=True)
        issue_list = tk.Listbox(issues, height=3)
        issue_list.pack(fill="both", expand=True)

        def current_sondaj_depth(no):
            normalized = normalize_sondaj_no(no)
            for sondaj in self.veri.get("sondaj", []):
                if normalize_sondaj_no(sondaj.get("no")) == normalized:
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
            quality = record.get("quality", {})
            is_queue = record.get("record_type") == "queue"
            active_view = view_var.get()
            if active_view == "Kuyruk" and not is_queue:
                return False
            if active_view == "Sonuçlar" and is_queue:
                return False
            if active_view == "Kontrol" and (
                is_queue or quality.get("level") not in ("warning", "error")
            ):
                return False
            mode = filter_var.get()
            if mode == "Tümü":
                return True
            if mode == "Aktarılacak":
                return record.get("include", True)
            if mode == "Hatalı":
                return quality.get("level") == "error"
            if mode == "Uyarılı":
                return quality.get("level") == "warning"
            if mode == "Bilgi":
                return quality.get("level") == "info"
            if mode == "Düşük Güven":
                if record.get("record_type") == "queue":
                    return False
                return safe_float(record["kayit"].guven) and safe_float(record["kayit"].guven) < project_spt_settings()["guven_esigi"]
            return True

        def refresh_tree(keep_selection=True):
            previous = selected_item["id"] if keep_selection else None
            previous_record = (
                tree_items.get(previous)
                if _tree_item_gecerli(tree, tree_items, previous)
                else None
            )
            for record in records + queue_records:
                record.pop("item_id", None)
            children = tree.get_children()
            if children:
                tree.delete(*children)
            tree_items.clear()
            selected_item["id"] = None
            duplicates = duplicate_keys()
            ok = info = warn = err = included = queue_count = spt_count = 0
            issue_list.delete(0, tk.END)
            context_map = context_issues()
            for idx, record in enumerate(records + queue_records):
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
                elif quality["level"] == "info":
                    info += 1
                elif quality["level"] == "ok":
                    ok += 1
                if quality["level"] in ("error", "warning"):
                    issue_label = kayit.kaynak if is_queue else f"{kayit.sondaj_no or '-'} {kayit.derinlik or '-'}"
                    issue_list.insert(tk.END, f"{issue_label}: {quality['message']}")
                status_prefix = {
                    "ok": "✓",
                    "info": "Bilgi:",
                    "warning": "Kontrol:",
                    "error": "Hata:",
                }.get(quality["level"], "")
                status_message = " ".join(filter(None, [status_prefix, quality["message"]]))
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
                        status_message,
                        kayit.kaynak,
                    )
                else:
                    flagged_fields = set(quality.get("fields") or [])

                    def marked(field, value):
                        return f"! {value or '-'}" if field in flagged_fields else value

                    row_values = (
                        "✓" if record.get("include", True) else "",
                        marked("sondaj_no", kayit.sondaj_no),
                        marked("derinlik", kayit.derinlik),
                        marked("v15", kayit.v15),
                        marked("v30", kayit.v30),
                        marked("v45", kayit.v45),
                        marked("n30", kayit.n30),
                        kayit.guven,
                        status_message,
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
                    selected_item["id"] = item_id
            for msg in import_warnings[-10:]:
                issue_list.insert(tk.END, msg)
            summary_var.set(
                f"SPT: {spt_count} | Kuyruk: {queue_count} | Aktarılacak: {included} | "
                f"Hazır: {ok} | Bilgi: {info} | Kontrol: {warn} | Hata: {err}"
            )
            status_var.set(f"{spt_count} SPT satırı yüklendi. {included} satır aktarım için seçili.")

        def load_detail(record):
            kayit = record["kayit"] if record else None
            for ent in detail_entries.values():
                ent.configure(style="SPT.Normal.TEntry")
                ent.delete(0, tk.END)
            normalization_var.set("")
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
            quality = record.get("quality") or {}
            invalid_style = (
                "SPT.Error.TEntry"
                if quality.get("level") == "error"
                else "SPT.Warning.TEntry"
            )
            for key in quality.get("fields") or []:
                entry = detail_entries.get(key)
                if entry:
                    entry.configure(style=invalid_style)
            raw = getattr(kayit, "raw", {}) or {}
            detail_parts = []
            if raw.get("okunan_derinlik") and raw.get("hedef_derinlik"):
                detail_parts.append(
                    f"Okunan derinlik: {raw['okunan_derinlik']} → Kullanılan: {raw['hedef_derinlik']}"
                )
            if raw.get("motor"):
                detail_parts.append(
                    f"Motor: {raw.get('motor')}"
                    + (f" / {raw.get('model')}" if raw.get("model") else "")
                )
            alternatives = record.get("alternatives") or raw.get("alternatif_okumalar") or []
            if alternatives:
                detail_parts.append(f"Alternatif okuma: {len(alternatives)}")
            normalization_var.set(" | ".join(detail_parts))
            preview_controller.show(kayit)

        preview_canvas.bind("<Configure>", preview_controller.schedule_redraw)
        preview_controller.draw_message("Satır seçildiğinde kaynak burada görünür.")

        def selected_record():
            selection = tree.selection()
            if not selection:
                selected_item["id"] = None
                return None
            item_id = selection[0]
            if not _tree_item_gecerli(tree, tree_items, item_id):
                selected_item["id"] = None
                return None
            selected_item["id"] = item_id
            return tree_items[item_id]

        def select_tree_record(record):
            if not record:
                return
            item_id = record.get("item_id")
            if not _tree_item_gecerli(tree, tree_items, item_id, record):
                refresh_tree(keep_selection=False)
                item_id = record.get("item_id")
            if not _tree_item_gecerli(tree, tree_items, item_id, record):
                return
            selected_item["id"] = item_id
            tree.selection_set(item_id)
            tree.focus(item_id)
            tree.see(item_id)
            load_detail(record)

        def on_select(event=None):
            load_detail(selected_record())

        def select_relative_row(step=1):
            children = list(tree.get_children())
            if not children:
                return "break"
            selection = tree.selection()
            try:
                current_index = children.index(selection[0]) if selection else -1
            except ValueError:
                current_index = -1
            target_index = max(0, min(len(children) - 1, current_index + step))
            target_id = children[target_index]
            if not _tree_item_gecerli(tree, tree_items, target_id):
                return "break"
            tree.selection_set(target_id)
            tree.focus(target_id)
            tree.see(target_id)
            on_select()
            return "break"

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

        def confirm_selected_and_next(event=None):
            record = selected_record()
            if not record:
                return "break"
            if record.get("record_type") != "queue":
                record["include"] = True
                update_selected_from_form(silent=True)
            return select_relative_row(1)

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
                spt_gecmis_kaydet("silindi", kayit, {"kaynak": kayit.kaynak})
            elif record in queue_records:
                queue_records.remove(record)
                remove_from_main_queue(record.get("queue_path", kayit.kaynak_yolu))
            selected_item["id"] = None
            refresh_tree(keep_selection=False)
            load_detail(None)
            status_var.set("Seçili SPT okuması listeden silindi.")
            return "break"

        def reread_selected_with_pro():
            if not self._spt_dis_servis_onayi_al(
                {"aktif_motor": "openai_pro"},
                parent=win,
            ):
                status_var.set("Pro okuma başlatılmadı: dış servis onayı verilmedi.")
                return
            run_spt_pro_reread(
                self,
                win,
                selected_record,
                update_selected_from_form,
                target_var,
                status_var,
                refresh_tree,
                load_detail,
            )

        def reread_selected_with_strongest():
            if not self._spt_dis_servis_onayi_al(
                {"aktif_motor": "openai_ust"},
                parent=win,
            ):
                status_var.set("En güçlü modelle okuma başlatılmadı: dış servis onayı verilmedi.")
                return
            run_spt_strongest_reread(
                self,
                win,
                selected_record,
                update_selected_from_form,
                target_var,
                status_var,
                refresh_tree,
                load_detail,
            )

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

        def use_next_alternative():
            record = selected_record()
            if not record or record.get("record_type") == "queue":
                return
            alternatives = list(record.get("alternatives") or [])
            if not alternatives:
                messagebox.showinfo("Alternatif Okuma", "Bu satır için saklanan alternatif okuma yok.", parent=win)
                return
            current = record["kayit"]
            alternative = alternatives.pop(0)
            values = dict(alternative.get("raw") or {})
            for key in (
                "sondaj_no", "derinlik", "v15", "v30", "v45", "n30",
                "guven", "kaynak", "kaynak_yolu",
            ):
                if key in alternative:
                    values[key] = alternative.get(key)
            chosen = kayit_normalize_et(values, target_var.get())
            alternatives.append(current.to_dict())
            record["kayit"] = chosen
            record["alternatives"] = alternatives
            record["include"] = True
            spt_gecmis_kaydet(
                "alternatif_secildi",
                chosen,
                {"onceki": current.to_dict()},
            )
            refresh_tree()
            load_detail(record)
            status_var.set("Alternatif SPT okuması seçildi.")

        def show_history():
            show_spt_history(self, win)

        def export_source_report():
            export_spt_source_report(self, records)
        def queue_record_for_path(path):
            key = source_unique_key(path)
            for record in queue_records:
                if source_unique_key(record.get("queue_path", "")) == key:
                    return record
            return None

        def ensure_queue_record(path, status="ready", message=None):
            record = queue_record_for_path(path)
            if record is None:
                name = os.path.basename(path)
                content_key = main_queue_controller.content_key(path)
                record = {
                    "include": False,
                    "kayit": SPTKaydi(
                        kaynak=name,
                        kaynak_yolu=path,
                        raw={"kaynak_hash": content_key},
                    ),
                    "source": name,
                    "record_type": "queue",
                    "queue_path": path,
                    "queue_hash": content_key,
                    "queue_status": status,
                    "queue_message": message or "Okumaya hazır",
                }
                queue_records.append(record)
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
            if record in queue_records:
                queue_records.remove(record)
                if _tree_item_gecerli(
                    tree,
                    tree_items,
                    selected_item.get("id"),
                    record,
                ):
                    selected_item["id"] = None
            if refresh:
                refresh_tree(keep_selection=False)

        def clear_queue_records():
            queue_records.clear()
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
            main_queue_controller.remove(path)

        def add_to_main_photo_queue(sources):
            source_list = list(sources or [])
            if source_list:
                self._spt_son_klasoru_kaydet(source_list[0])
            main_queue_controller.recursive = bool(main_queue_recursive_var.get())
            added_paths, skipped_duplicate, found_count = main_queue_controller.add_sources(source_list)
            for path in added_paths:
                ensure_queue_record(path, status="ready", message="Okumaya hazır")
            added = len(added_paths)
            if added:
                view_var.set("Kuyruk")
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
            return added, skipped_duplicate, found_count

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
            main_queue_controller.clear()
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
                spt_location_key(record["kayit"], record.get("source", "")): record
                for record in records
                if record.get("record_type") != "queue"
            }
            skipped_duplicates = 0
            conflict_count = 0
            added_count = 0
            for kayit in sonuc.kayitlar:
                kunye = self.veri.get("kunye", {}) or {}
                project_label = " | ".join(filter(None, [
                    str(kunye.get("sahibi", "") or "").strip(),
                    (
                        f"{kunye.get('ada', '')}/{kunye.get('par', '')}"
                        if kunye.get("ada") or kunye.get("par")
                        else ""
                    ),
                ]))
                kayit.raw.setdefault("proje", project_label)
                kayit.sondaj_no = normalize_sondaj_no(kayit.sondaj_no, target_var.get())
                if not kayit.sondaj_no:
                    kayit.sondaj_no = target_var.get().strip()
                key = spt_unique_key(kayit, source_label)
                loc_key = spt_location_key(kayit, source_label)
                loc_is_valid = bool(loc_key[0] and loc_key[1] > 0)
                if key in existing_keys:
                    skipped_duplicates += 1
                    continue
                if loc_is_valid and loc_key in existing_locations:
                    existing_record = existing_locations[loc_key]
                    existing_kayit = existing_record["kayit"]
                    alternatives = list(existing_record.get("alternatives") or [])
                    if spt_kayit_puani(kayit) > spt_kayit_puani(existing_kayit):
                        alternatives.append(existing_kayit.to_dict())
                        existing_record["kayit"] = kayit
                    else:
                        alternatives.append(kayit.to_dict())
                    existing_record["alternatives"] = alternatives
                    selected = existing_record["kayit"]
                    conflict_note = "Aynı kuyu/derinlik için alternatif okuma var"
                    if conflict_note not in selected.uyari:
                        selected.uyari = ", ".join(filter(None, [selected.uyari, conflict_note]))
                    existing_keys.add(key)
                    skipped_duplicates += 1
                    conflict_count += 1
                    continue
                existing_keys.add(key)
                if loc_is_valid:
                    existing_locations[loc_key] = None
                new_record = {
                    "include": bool(kayit.derinlik and (kayit.v15 or kayit.v30 or kayit.v45 or kayit.n30)),
                    "kayit": kayit,
                    "source": source_label,
                    "alternatives": list((getattr(kayit, "raw", {}) or {}).get("alternatif_okumalar") or []),
                }
                records.append(new_record)
                if loc_is_valid:
                    existing_locations[loc_key] = new_record
                added_count += 1
                spt_gecmis_kaydet("okundu", kayit, {"kaynak": source_label, "aktarildi": False})
            if skipped_duplicates:
                import_warnings.append(f"{skipped_duplicates} tekrar SPT satırı aynı kuyu/derinlik olduğu için atlandı.")
            if conflict_count:
                import_warnings.append(
                    f"{conflict_count} kuyu/derinlik çakışmasında daha güçlü sonuç önerildi; alternatifler satırda saklandı."
                )
            if not main_read_state["active"]:
                view_var.set("Sonuçlar")
            refresh_tree(keep_selection=False)
            if records:
                first = next(iter(tree.get_children()), None)
                if _tree_item_gecerli(tree, tree_items, first):
                    tree.selection_set(first)
                    selected_item["id"] = first
                    on_select()
            return added_count, skipped_duplicates

        def start_main_photo_queue():
            if main_read_state["active"]:
                messagebox.showinfo("SPT Fotoğraf", "Fotoğraf okuma zaten devam ediyor.", parent=win)
                return
            paths = main_queue_controller.deduplicated_paths()
            if len(paths) != len(main_queue_paths):
                main_queue_paths[:] = paths
                status_var.set("SPT fotoğraf kuyruğundaki tekrar dosyalar temizlendi.")
            if not paths:
                messagebox.showwarning("SPT Fotoğraf", "Başlatmak için önce fotoğraf ekleyin.", parent=win)
                refresh_main_queue_status()
                return

            ayarlar = spt_ayarlarini_yukle()
            settings = project_spt_settings()
            consent_settings = dict(ayarlar)
            if settings["auto_pro"]:
                consent_settings["ek_motorlar"] = ["openai"]
            if not self._spt_dis_servis_onayi_al(consent_settings, parent=win):
                status_var.set("SPT fotoğraf okuma başlatılmadı: dış servis onayı verilmedi.")
                refresh_main_queue_status("onay verilmedi")
                return
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
            view_var.set("Kuyruk")
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
                refresh_tree(keep_selection=False)
                has_control = any(
                    (record.get("quality") or {}).get("level") in ("warning", "error")
                    for record in records
                )
                view_var.set("Kontrol" if has_control else "Sonuçlar")

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
                            guven_esigi=settings["guven_esigi"],
                        )
                    except Exception as exc:
                        self.root.after(0, lambda path=path, exc=exc: finish_file(path, hata=exc))
                        continue
                    if stop_event.is_set() and not sonuc.kayitlar:
                        cancelled = True
                        break
                    self.root.after(0, lambda path=path, sonuc=sonuc: finish_file(path, sonuc=sonuc))
                self.root.after(0, lambda cancelled=cancelled or stop_event.is_set(): finish_all(cancelled))

            def worker_failed(exc):
                if not win.winfo_exists():
                    return
                main_read_state["active"] = False
                main_read_state["stop_event"] = None
                refresh_main_queue_status("hata")
                status_var.set(f"SPT fotoğraf okuma durdu: {exc}")
                messagebox.showerror("SPT Fotoğraf", f"Okuma tamamlanamadı:\n{exc}", parent=win)

            self.arka_plan_gorevi_baslat(
                "SPT fotoğraf kuyruğu",
                worker,
                status_start="SPT fotoğraf kuyruğu arka planda başlatıldı.",
                status_success="SPT fotoğraf kuyruğu işlemi bitti.",
                status_error="SPT fotoğraf kuyruğu tamamlanamadı: {error}",
                on_error=worker_failed,
            )

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
            self._spt_son_klasoru_kaydet(path)
            try:
                sonuc = excelden_spt_oku(path, default_sondaj_no=target_var.get())
            except Exception as exc:
                messagebox.showerror("SPT Excel", f"Excel dosyası okunamadı:\n{exc}")
                return
            if not sonuc.kayitlar:
                messagebox.showwarning("SPT Excel", "Dosyada aktarılacak SPT satırı bulunamadı.")
                return
            add_result(sonuc, os.path.basename(path), append=True)

        def import_cropped_photo():
            ayarlar = spt_ayarlarini_yukle()
            consent_settings = dict(ayarlar)
            if project_spt_settings()["auto_pro"]:
                consent_settings["ek_motorlar"] = ["openai"]
            if not self._spt_dis_servis_onayi_al(consent_settings, parent=win):
                status_var.set("Kırpılmış fotoğraf okuma başlatılmadı: dış servis onayı verilmedi.")
                return
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
            try:
                popup = open_spt_settings_dialog(
                    self,
                    win,
                    auto_pro_var,
                    refresh_tree,
                    status_var,
                )
                if popup and popup.winfo_exists():
                    popup.lift()
                    popup.focus_force()
            except Exception as exc:
                messagebox.showerror(
                    "SPT Ayarları",
                    f"Ayar penceresi açılamadı:\n{exc}",
                    parent=win,
                )

        def bounded_sash_position(total, saved, ratio, first_min, second_min):
            total = int(total or 0)
            if total <= 1:
                return 0
            lower = min(int(first_min), max(180, int(total * 0.45)))
            upper = max(lower, total - min(int(second_min), max(180, int(total * 0.42))))
            default = max(lower, min(upper, int(total * ratio)))
            saved = int(saved or 0)
            return saved if lower <= saved <= upper else default

        def save_layout_state(event=None):
            ayarlar = self.veri.setdefault("ayarlar", {})
            try:
                main_width = main.winfo_width()
                main_pos = bounded_sash_position(
                    main_width,
                    main.sashpos(0),
                    0.56,
                    520,
                    460,
                )
                if main_width >= 700:
                    ayarlar["spt_bolucu_ana"] = str(main_pos)
            except Exception:
                pass
            try:
                right_height = right_pane.winfo_height()
                right_pos = bounded_sash_position(
                    right_height,
                    right_pane.sashpos(0),
                    0.48,
                    280,
                    350,
                )
                if right_height >= 480:
                    ayarlar["spt_bolucu_sag"] = str(right_pos)
            except Exception:
                pass

        def restore_layout_state(attempt=0):
            if not win.winfo_exists():
                return
            win.update_idletasks()
            main_width = main.winfo_width()
            right_height = right_pane.winfo_height()
            if (main_width < 700 or right_height < 480) and attempt < 8:
                win.after(150, lambda: restore_layout_state(attempt + 1))
                return
            ayarlar = self.veri.get("ayarlar", {}) or {}
            main_pos = int(safe_float(ayarlar.get("spt_bolucu_ana")))
            right_pos = int(safe_float(ayarlar.get("spt_bolucu_sag")))
            try:
                main.sashpos(
                    0,
                    bounded_sash_position(
                        main_width,
                        main_pos,
                        0.56,
                        520,
                        460,
                    ),
                )
            except Exception:
                pass
            try:
                right_pane.sashpos(
                    0,
                    bounded_sash_position(
                        right_height,
                        right_pos,
                        0.48,
                        280,
                        350,
                    ),
                )
            except Exception:
                pass
            save_layout_state()

        def close_window():
            save_layout_state()
            win.destroy()

        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<space>", toggle_selected)
        tree.bind("<Double-1>", toggle_selected)
        tree.bind("<Return>", confirm_selected_and_next)
        tree.bind("<Delete>", delete_selected_record)
        filter_var.trace_add("write", lambda *_: refresh_tree())
        view_var.trace_add("write", lambda *_: refresh_tree())
        win.bind("<Control-Return>", lambda event: (reread_selected_with_pro(), "break")[1])
        for detail_entry in detail_entries.values():
            detail_entry.bind("<Return>", confirm_selected_and_next)
        preview_canvas.bind(
            "<MouseWheel>",
            lambda event: preview_controller.zoom_in() if event.delta > 0 else preview_controller.zoom_out(),
        )

        self.modern_button(source_group, text="Foto Ekle", command=add_main_photos, role="success").pack(side="left", padx=2)
        self.modern_button(source_group, text="Klasör Ekle", command=add_main_folder, role="success", outline=True).pack(side="left", padx=2)
        main_queue_buttons["start"] = self.modern_button(source_group, text="Başlat", command=start_main_photo_queue, role="success")
        main_queue_buttons["start"].pack(side="left", padx=2)
        main_queue_buttons["stop"] = self.modern_button(source_group, text="Durdur", command=stop_main_photo_queue, role="danger", state="disabled")
        main_queue_buttons["stop"].pack(side="left", padx=2)

        ttk.Label(queue_bar, textvariable=main_queue_status_var, foreground="#2874A6").pack(side="left", fill="x", expand=True)
        self.modern_button(queue_bar, text="Kuyruğu Temizle", command=clear_main_photo_queue, role="neutral", outline=True).pack(side="left", padx=3)
        ttk.Checkbutton(queue_bar, text="Alt klasörleri tara", variable=main_queue_recursive_var).pack(side="left", padx=6)
        ttk.Label(queue_bar, textvariable=main_dnd_status_var, foreground="#555555").pack(side="right", padx=(8, 0))

        ttk.Label(target_group, text="Hedef").pack(side="left", padx=(0, 3))
        ttk.Combobox(target_group, textvariable=target_var, values=sondaj_nolari, width=12).pack(side="left", padx=3)
        self.modern_button(target_group, text="Seçiliye Doldur", command=fill_target_for_selected, role="accent", outline=True).pack(side="left", padx=2)
        ttk.Checkbutton(target_group, text="Aynı derinliği güncelle", variable=update_same_var).pack(side="left", padx=5)
        ttk.Checkbutton(target_group, text="Önce temizle", variable=clear_target_var).pack(side="left", padx=5)

        advanced_menu = tk.Menu(win, tearoff=False)
        advanced_menu.add_command(label="Excel'den Al", command=import_excel)
        advanced_menu.add_command(label="Kırp ve Oku", command=import_cropped_photo)
        advanced_menu.add_separator()
        advanced_menu.add_checkbutton(
            label="Düşük Güvende Otomatik İkinci Okuma",
            variable=auto_pro_var,
            command=save_auto_pro_setting,
        )
        advanced_menu.add_command(label="Seçiliyi Terra ile Oku", command=reread_selected_with_pro, accelerator="Ctrl+Enter")
        advanced_menu.add_command(label="Seçiliyi Sol ile Oku", command=reread_selected_with_strongest)
        advanced_menu.add_separator()
        advanced_menu.add_command(label="N30 Değerlerini Hesapla", command=n30_all)
        advanced_menu.add_command(label="Kaynak Raporu", command=export_source_report)
        advanced_menu.add_command(label="Geçmiş", command=show_history)
        advanced_menu.add_command(label="Ayarlar", command=settings_dialog)
        advanced_menu.add_separator()
        advanced_menu.add_command(
            label="Son Aktarımı Geri Al",
            command=lambda: undo_last_spt_import(self, status_var),
        )
        ttk.Menubutton(advanced_group, text="Diğer İşlemler", menu=advanced_menu).pack(side="right")

        detail_btns = ttk.Frame(detail)
        detail_btns.grid(row=4, column=0, columnspan=4, sticky="e", pady=(8, 0))
        self.modern_button(detail_btns, text="Satırı Güncelle", command=update_selected_from_form, role="accent", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Pro ile Oku", command=reread_selected_with_pro, role="accent", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Al / Alma", command=toggle_selected, role="neutral", outline=True).pack(side="left", padx=2)
        self.modern_button(detail_btns, text="Sil", command=delete_selected_record, role="danger").pack(side="left", padx=2)
        row_menu = tk.Menu(win, tearoff=False)
        row_menu.add_command(label="N30 Hesapla", command=n30_selected)
        row_menu.add_command(label="Doğrusunu Öğret", command=teach_selected)
        row_menu.add_command(label="Alternatif Okumayı Kullan", command=use_next_alternative)
        ttk.Menubutton(detail_btns, text="Satır İşlemleri", menu=row_menu).pack(side="left", padx=2)

        self.modern_button(bottom, text="Aktar", command=lambda: apply_import(False), role="success").pack(side="right", padx=3)
        self.modern_button(bottom, text="Aktar ve Kapat", command=lambda: apply_import(True), role="primary").pack(side="right", padx=3)
        self.modern_button(bottom, text="Kapat", command=close_window, role="secondary").pack(side="right", padx=3)

        enable_main_drag_drop()
        refresh_main_queue_status()
        main.bind("<ButtonRelease-1>", save_layout_state, add="+")
        right_pane.bind("<ButtonRelease-1>", save_layout_state, add="+")
        win.protocol("WM_DELETE_WINDOW", close_window)
        win.after(250, restore_layout_state)

        if initial_sonuc:
            add_result(initial_sonuc, str(initial_source or "SPT"), append=True)
        if baslat == "excel":
            win.after(150, import_excel)
        elif baslat == "foto":
            win.after(150, add_main_photos)
