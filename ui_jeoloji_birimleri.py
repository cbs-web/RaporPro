# Dosya: RaporPro/ui_jeoloji_birimleri.py
"""Haritalar sekmesindeki proje jeolojik birimleri yöneticisi."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from jeoloji_raporu import (
    JEOLOJI_BIRIM_KATALOGU,
    JEOLOJI_DURUM_SECENEKLERI,
    JEOLOJI_KONUM_SECENEKLERI,
    jeoloji_birim_etiketi,
    jeoloji_birim_kaydini_normalize,
    jeoloji_birimleri,
    jeoloji_rapor_metinleri,
    jeoloji_varsayilanlari,
)


OZEL_BIRIM_SECENEGI = "Özel birim..."


class JeolojiBirimleriPenceresi:
    """Bir projedeki çoklu literatür birimlerini düzenleyen pencere."""

    def __init__(self, app, on_saved=None):
        self.app = app
        self.on_saved = on_saved
        self.records = copy.deepcopy(jeoloji_birimleri(app.veri))
        self.selected_index = None

        self.win = tk.Toplevel(app.root)
        app.pencere_hazirla(
            self.win,
            "Jeolojik Birimler",
            "1120x720",
            (900, 600),
            modal=True,
        )

        self.catalog_values = [
            f"{code} - {info['ad']}"
            for code, info in JEOLOJI_BIRIM_KATALOGU.items()
        ] + [OZEL_BIRIM_SECENEGI]
        self.catalog_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.age_var = tk.StringVar()
        self.location_var = tk.StringVar(
            value=JEOLOJI_KONUM_SECENEKLERI["inceleme_alani"]
        )
        self.condition_var = tk.StringVar(
            value=JEOLOJI_DURUM_SECENEKLERI["belirtilmedi"]
        )
        self.section_var = tk.BooleanVar(value=True)
        self.info_var = tk.StringVar()

        self._build_ui()
        self._refresh_tree()
        self._show_legacy_suggestion()

    def _build_ui(self):
        root = ttk.Frame(self.win, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Proje Jeolojik Birimleri",
            style="PageTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.info_var,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(
            header,
            text="Metin Önizleme",
            command=self._open_preview,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        list_box = ttk.LabelFrame(
            root,
            text="Raporda Kullanılacak Birimler",
            padding=8,
        )
        list_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        list_box.columnconfigure(0, weight=1)
        list_box.rowconfigure(0, weight=1)

        columns = ("kod", "ad", "konum", "durum", "kesit")
        self.tree = ttk.Treeview(
            list_box,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("kod", text="Kod")
        self.tree.heading("ad", text="Birim")
        self.tree.heading("konum", text="Konum")
        self.tree.heading("durum", text="Durum")
        self.tree.heading("kesit", text="Kesit")
        self.tree.column("kod", width=80, anchor="center", stretch=False)
        self.tree.column("ad", width=190, anchor="w")
        self.tree.column("konum", width=180, anchor="w")
        self.tree.column("durum", width=100, anchor="center")
        self.tree.column("kesit", width=60, anchor="center", stretch=False)
        tree_scroll = ttk.Scrollbar(
            list_box,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)
        self.tree.bind("<Delete>", lambda _event: self._remove_selected())

        order_actions = ttk.Frame(list_box)
        order_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(
            order_actions,
            text="Yukarı",
            command=lambda: self._move_selected(-1),
        ).pack(side="left")
        ttk.Button(
            order_actions,
            text="Aşağı",
            command=lambda: self._move_selected(1),
        ).pack(side="left", padx=5)
        ttk.Button(
            order_actions,
            text="Seçileni Kaldır",
            command=self._remove_selected,
        ).pack(side="right")

        form = ttk.LabelFrame(root, text="Birim Bilgisi", padding=12)
        form.grid(row=1, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(7, weight=1)

        ttk.Label(form, text="Katalog").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        catalog = ttk.Combobox(
            form,
            textvariable=self.catalog_var,
            values=self.catalog_values,
            state="readonly",
        )
        catalog.grid(row=0, column=1, sticky="ew", pady=4)
        catalog.bind("<<ComboboxSelected>>", self._catalog_selected)

        self._entry_row(form, 1, "Birim kodu", self.code_var)
        self._entry_row(form, 2, "Birim adı", self.name_var)
        self._entry_row(form, 3, "Jeolojik yaş", self.age_var)

        ttk.Label(form, text="Konum").grid(
            row=4,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        ttk.Combobox(
            form,
            textvariable=self.location_var,
            values=list(JEOLOJI_KONUM_SECENEKLERI.values()),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Saha durumu").grid(
            row=5,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        ttk.Combobox(
            form,
            textvariable=self.condition_var,
            values=list(JEOLOJI_DURUM_SECENEKLERI.values()),
            state="readonly",
        ).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(
            form,
            text="Jeolojik kesit açıklamasına dahil et",
            variable=self.section_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 5))

        ttk.Label(form, text="Projeye özel açıklama").grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="nw",
            pady=(6, 2),
        )
        self.custom_text = scrolledtext.ScrolledText(
            form,
            height=8,
            wrap="word",
            font=("Segoe UI", 9),
        )
        self.custom_text.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(0, 8),
        )
        form.rowconfigure(8, weight=1)

        form_actions = ttk.Frame(form)
        form_actions.grid(row=9, column=0, columnspan=2, sticky="ew")
        ttk.Button(
            form_actions,
            text="Formu Temizle",
            command=self._clear_form,
        ).pack(side="left")
        ttk.Button(
            form_actions,
            text="Birim Ekle",
            command=self._add_record,
        ).pack(side="right")
        ttk.Button(
            form_actions,
            text="Seçileni Güncelle",
            command=self._update_record,
        ).pack(side="right", padx=6)

        footer = ttk.Frame(root)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(
            footer,
            text=(
                "Rapor metinleri yalnız bu listede bulunan birimlerden oluşturulur. "
                "Katalog dışı açıklamalar kullanıcı sorumluluğundadır."
            ),
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(
            footer,
            text="Vazgeç",
            command=self.win.destroy,
        ).pack(side="right")
        ttk.Button(
            footer,
            text="Kaydet",
            command=self._save,
        ).pack(side="right", padx=6)

    @staticmethod
    def _entry_row(parent, row, label, variable):
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=4,
        )

    @staticmethod
    def _key_from_label(options, label, fallback):
        for key, text in options.items():
            if text == label:
                return key
        return fallback

    def _catalog_selected(self, _event=None):
        value = self.catalog_var.get()
        if value == OZEL_BIRIM_SECENEGI:
            self.code_var.set("")
            self.name_var.set("")
            self.age_var.set("")
            return
        code = value.split(" - ", 1)[0].strip()
        info = JEOLOJI_BIRIM_KATALOGU.get(code, {})
        self.code_var.set(code)
        self.name_var.set(info.get("ad", ""))
        self.age_var.set(info.get("yas", ""))

    def _form_record(self):
        record = jeoloji_birim_kaydini_normalize(
            {
                "kod": self.code_var.get(),
                "ad": self.name_var.get(),
                "yas": self.age_var.get(),
                "konum": self._key_from_label(
                    JEOLOJI_KONUM_SECENEKLERI,
                    self.location_var.get(),
                    "inceleme_alani",
                ),
                "durum": self._key_from_label(
                    JEOLOJI_DURUM_SECENEKLERI,
                    self.condition_var.get(),
                    "belirtilmedi",
                ),
                "kesitte_kullan": self.section_var.get(),
                "ozel_aciklama": self.custom_text.get("1.0", "end-1c"),
            }
        )
        if not record:
            messagebox.showwarning(
                "Jeolojik Birimler",
                "Birim kodu veya birim adı girilmelidir.",
                parent=self.win,
            )
        return record

    def _add_record(self):
        record = self._form_record()
        if not record:
            return
        key = (record["kod"] or record["ad"]).casefold()
        if any(
            (item["kod"] or item["ad"]).casefold() == key
            for item in self.records
        ):
            messagebox.showwarning(
                "Jeolojik Birimler",
                "Bu birim listede zaten bulunuyor. Seçileni Güncelle düğmesini kullanın.",
                parent=self.win,
            )
            return
        self.records.append(record)
        self._refresh_tree(select_index=len(self.records) - 1)

    def _update_record(self):
        if self.selected_index is None:
            messagebox.showinfo(
                "Jeolojik Birimler",
                "Önce güncellenecek birimi listeden seçin.",
                parent=self.win,
            )
            return
        record = self._form_record()
        if not record:
            return
        self.records[self.selected_index] = record
        self._refresh_tree(select_index=self.selected_index)

    def _remove_selected(self):
        if self.selected_index is None:
            return
        del self.records[self.selected_index]
        next_index = min(self.selected_index, len(self.records) - 1)
        self.selected_index = None
        self._clear_form()
        self._refresh_tree(select_index=next_index if next_index >= 0 else None)

    def _move_selected(self, delta):
        if self.selected_index is None:
            return
        target = self.selected_index + delta
        if not 0 <= target < len(self.records):
            return
        self.records[self.selected_index], self.records[target] = (
            self.records[target],
            self.records[self.selected_index],
        )
        self._refresh_tree(select_index=target)

    def _refresh_tree(self, select_index=None):
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(self.records):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    record.get("kod", ""),
                    record.get("ad", ""),
                    JEOLOJI_KONUM_SECENEKLERI.get(
                        record.get("konum"),
                        record.get("konum", ""),
                    ),
                    JEOLOJI_DURUM_SECENEKLERI.get(
                        record.get("durum"),
                        record.get("durum", ""),
                    ),
                    "Evet" if record.get("kesitte_kullan", True) else "Hayır",
                ),
            )
        self.info_var.set(
            f"{len(self.records)} birim tanımlı. Sıralama rapordaki açıklama sırasıdır."
        )
        if select_index is not None and 0 <= select_index < len(self.records):
            iid = str(select_index)
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

    def _tree_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            self.selected_index = None
            return
        self.selected_index = int(selection[0])
        record = self.records[self.selected_index]
        catalog_label = next(
            (
                value
                for value in self.catalog_values
                if value.startswith(f"{record.get('kod')} - ")
            ),
            OZEL_BIRIM_SECENEGI,
        )
        self.catalog_var.set(catalog_label)
        self.code_var.set(record.get("kod", ""))
        self.name_var.set(record.get("ad", ""))
        self.age_var.set(record.get("yas", ""))
        self.location_var.set(
            JEOLOJI_KONUM_SECENEKLERI.get(
                record.get("konum"),
                JEOLOJI_KONUM_SECENEKLERI["inceleme_alani"],
            )
        )
        self.condition_var.set(
            JEOLOJI_DURUM_SECENEKLERI.get(
                record.get("durum"),
                JEOLOJI_DURUM_SECENEKLERI["belirtilmedi"],
            )
        )
        self.section_var.set(record.get("kesitte_kullan", True))
        self.custom_text.delete("1.0", "end")
        self.custom_text.insert("1.0", record.get("ozel_aciklama", ""))

    def _clear_form(self):
        self.selected_index = None
        self.tree.selection_remove(self.tree.selection())
        self.catalog_var.set("")
        self.code_var.set("")
        self.name_var.set("")
        self.age_var.set("")
        self.location_var.set(JEOLOJI_KONUM_SECENEKLERI["inceleme_alani"])
        self.condition_var.set(JEOLOJI_DURUM_SECENEKLERI["belirtilmedi"])
        self.section_var.set(True)
        self.custom_text.delete("1.0", "end")

    def _preview_data(self):
        return {"jeoloji": {"birimler": copy.deepcopy(self.records)}}

    def _open_preview(self):
        preview = tk.Toplevel(self.win)
        self.app.pencere_hazirla(
            preview,
            "Jeoloji Rapor Metni Önizleme",
            "920x650",
            (760, 520),
            modal=False,
        )
        notebook = ttk.Notebook(preview)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        texts = jeoloji_rapor_metinleri(self._preview_data())
        tabs = (
            ("bolgesel", "Bölgesel Jeoloji"),
            ("muhendislik", "Mühendislik Jeolojisi"),
            ("kesit", "Jeolojik Kesit"),
            ("sonuc", "Sonuç"),
            ("mt", "Mikrotremör"),
        )
        for key, title in tabs:
            frame = ttk.Frame(notebook, padding=8)
            notebook.add(frame, text=title)
            area = scrolledtext.ScrolledText(
                frame,
                wrap="word",
                font=("Segoe UI", 10),
            )
            area.pack(fill="both", expand=True)
            area.insert("1.0", "\n\n".join(texts[key]))
            area.configure(state="disabled")

    def _show_legacy_suggestion(self):
        if self.records:
            return
        jeoloji = self.app.veri.get("jeoloji", {})
        suggestion = (
            jeoloji.get("harita_formasyon_onerisi", "")
            if isinstance(jeoloji, dict)
            else ""
        )
        if suggestion in JEOLOJI_BIRIM_KATALOGU:
            info = JEOLOJI_BIRIM_KATALOGU[suggestion]
            self.catalog_var.set(f"{suggestion} - {info['ad']}")
            self._catalog_selected()
            self.info_var.set(
                f"Eski mühendislik jeolojisi haritasından öneri: "
                f"{jeoloji_birim_etiketi({'kod': suggestion})}. "
                "Onaylamak için Birim Ekle'yi kullanın."
            )

    def _save(self):
        current = self.app.veri.get("jeoloji")
        if not isinstance(current, dict):
            current = jeoloji_varsayilanlari()
            self.app.veri["jeoloji"] = current
        current["birimler"] = copy.deepcopy(self.records)
        if self.records:
            current["harita_formasyon_onerisi"] = ""
        if callable(self.on_saved):
            self.on_saved()
        if hasattr(self.app, "set_status"):
            self.app.set_status(
                f"{len(self.records)} jeolojik birim proje verisine kaydedildi.",
                level="success",
            )
        self.app.pencere_kapat(self.win)


__all__ = ["JeolojiBirimleriPenceresi"]
