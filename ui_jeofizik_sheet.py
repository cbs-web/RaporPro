# Dosya: RaporPro/ui_jeofizik_sheet.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from jeofizik_sheet_motoru import (
    JEOFIZIK_SHEET_DEFAULT_COLS,
    jeofizik_excel_dosyasi_oku,
    jeofizik_sheet_grid_hazirla,
    jeofizik_sheet_ozeti,
    jeofizik_sheet_rows_temizle,
    jeofizik_sheet_satirlarini_coz,
    jeofizik_sheet_var_mi,
    jeofizik_ss_koordinatlarini_koru,
)
from performans import perf_tracked
from sabitler import COLOR_ACCENT, COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD


class JeofizikSheetMixin:
    def _jeofizik_sheet_ready(self):
        return jeofizik_sheet_var_mi(getattr(self, "veri", {}))

    def _jeofizik_sheet_ozet_text(self):
        summary = jeofizik_sheet_ozeti(getattr(self, "veri", {}))
        if summary.get("ready"):
            return f"Jeofizik Sheet hazir: {summary['serim']} serim / {summary['layers']} tabaka"
        rows = self.veri.get("jeofizik_sheet", {}).get("rows", []) if isinstance(getattr(self, "veri", None), dict) else []
        if any(any(str(cell).strip() for cell in row) for row in rows or []):
            return "Jeofizik Sheet var ama okunabilir serim bulunamadi"
        return ""

    def _jeofizik_label_guncelle(self):
        if not hasattr(self, "lbl_jeo_excel"):
            return
        sheet_text = self._jeofizik_sheet_ozet_text()
        sheet_ready = bool(jeofizik_sheet_ozeti(getattr(self, "veri", {})).get("ready"))
        path = getattr(self, "jeo_excel_path", None)
        if sheet_text:
            suffix = f" + {os.path.basename(path)}" if path else ""
            self.lbl_jeo_excel.config(text=f"{sheet_text}{suffix}", foreground=COLOR_SUCCESS if sheet_ready else COLOR_WARNING)
        elif path:
            self.lbl_jeo_excel.config(text=os.path.basename(path), foreground=COLOR_SUCCESS)
        else:
            self.lbl_jeo_excel.config(text="Jeofizik Excel secilmedi", foreground="red")

    def _jeofizik_sheet_kaydet(self, rows):
        rows = jeofizik_sheet_rows_temizle(rows)
        parsed = jeofizik_sheet_satirlarini_coz(rows)
        ss_list = parsed.get("ss_list", [])
        jeofizik = self.veri.setdefault("jeofizik", {})
        mevcut_ss = jeofizik.get("ss_list", [])
        jeofizik_ss_koordinatlarini_koru(ss_list, mevcut_ss)
        self.veri.setdefault("jeofizik_sheet", {})["rows"] = rows
        if ss_list:
            jeofizik["ss_list"] = ss_list
            jeofizik["ss_source"] = "sheet"
        elif not rows and jeofizik.get("ss_source") == "sheet":
            jeofizik["ss_list"] = []
            jeofizik.pop("ss_source", None)
        if hasattr(self, "jeo_yenile"):
            self.jeo_yenile()
        if hasattr(self, "_jeofizik_label_guncelle"):
            self._jeofizik_label_guncelle()
        if hasattr(self, "ozet_yenile"):
            self.ozet_yenile(collect=False)
        if hasattr(self, "otomatik_kaydet"):
            self.otomatik_kaydet()
        return parsed

    @perf_tracked("jeofizik_sheet.open")
    def jeofizik_sheet_ac(self):
        try:
            from tksheet import Sheet
        except Exception as exc:
            messagebox.showerror(
                "Jeofizik Sheet",
                f"tksheet yuklenemedi:\n{exc}\n\nCozum: Bu Python icin `pip install tksheet` calistirin.",
            )
            return

        self.guncelle_veri_objesi(silent=True)
        win = tk.Toplevel(self.root)
        self.pencere_hazirla(win, "Jeofizik Sheet - Sismik Parametreler", "1180x760", (920, 620), modal=False)

        top = ttk.Frame(win, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Jeofizik Sheet", font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 10))
        info_var = tk.StringVar(value="Sismik parametre Excel tablonuzu buraya yapistirin. Mikrotremor bu ekranda yoktur.")
        ttk.Label(top, textvariable=info_var, foreground="#1F618D").pack(side="left", fill="x", expand=True)

        frame = ttk.Frame(win, padding=(10, 0, 10, 8))
        frame.pack(fill="both", expand=True)
        headers = [f"{idx + 1}" for idx in range(JEOFIZIK_SHEET_DEFAULT_COLS)]
        sheet = Sheet(
            frame,
            headers=headers,
            data=jeofizik_sheet_grid_hazirla(self.veri.get("jeofizik_sheet", {}).get("rows", [])),
            show_row_index=True,
            show_header=True,
            theme="light blue",
            paste_can_expand_y=True,
            paste_can_expand_x=True,
            edit_cell_return="down",
            edit_cell_tab="right",
            default_column_width=118,
            default_row_index_width=52,
            column_drag_and_drop_perform=False,
            row_drag_and_drop_perform=True,
        )
        sheet.pack(fill="both", expand=True)
        sheet.enable_bindings("all")

        def rows_from_sheet():
            return jeofizik_sheet_rows_temizle(sheet.get_sheet_data())

        def refresh_info():
            rows = rows_from_sheet()
            summary = jeofizik_sheet_ozeti(rows)
            if summary.get("ready"):
                warning_text = f" | Uyari: {len(summary['warnings'])}" if summary.get("warnings") else ""
                info_var.set(f"{summary['serim']} serim / {summary['layers']} tabaka kayda hazir.{warning_text}")
            else:
                filled_rows = sum(1 for row in rows if any(str(cell).strip() for cell in row))
                info_var.set(f"{filled_rows} satir var. Serim/SS bloklari henuz okunamadi.")

        def save_sheet(close=False):
            rows = rows_from_sheet()
            parsed = self._jeofizik_sheet_kaydet(rows)
            ss_list = parsed.get("ss_list", [])
            warnings = parsed.get("warnings", [])
            if ss_list:
                layer_count = sum(len(ss.get("layers", [])) for ss in ss_list)
                self.set_status(f"Jeofizik Sheet kaydedildi: {len(ss_list)} serim / {layer_count} tabaka.", level="success")
            else:
                self.set_status("Jeofizik Sheet kaydedildi ama okunabilir serim bulunamadi.", level="warning")
            if warnings:
                info_var.set(" | ".join(warnings[:3]))
            else:
                refresh_info()
            if close:
                win.destroy()

        def clear_sheet():
            if not messagebox.askyesno("Jeofizik Sheet", "Jeofizik Sheet verisi temizlensin mi?"):
                return
            sheet.set_sheet_data(jeofizik_sheet_grid_hazirla([]), reset_col_positions=False, reset_row_positions=True)
            sheet.refresh()
            refresh_info()

        def add_rows(count=20):
            col_count = max(sheet.get_total_columns(), JEOFIZIK_SHEET_DEFAULT_COLS)
            sheet.insert_rows([[""] * col_count for _ in range(count)], idx="end", undo=True)
            refresh_info()

        def import_excel():
            path = filedialog.askopenfilename(
                title="Jeofizik Excel'den Al",
                filetypes=[("Excel/CSV", "*.xlsx;*.xlsm;*.xls;*.csv")],
            )
            if not path:
                return
            try:
                rows = jeofizik_excel_dosyasi_oku(path)
            except Exception as exc:
                messagebox.showerror("Jeofizik Sheet", f"Excel okunamadi:\n{exc}")
                return
            sheet.set_sheet_data(jeofizik_sheet_grid_hazirla(rows), reset_col_positions=False, reset_row_positions=True)
            sheet.refresh()
            refresh_info()
            self.set_status(f"Jeofizik Excel sheet'e alindi: {os.path.basename(path)}", level="success")

        def export_excel():
            try:
                from openpyxl import Workbook
            except Exception as exc:
                messagebox.showerror("Jeofizik Sheet", f"openpyxl yuklenemedi:\n{exc}")
                return
            path = filedialog.asksaveasfilename(
                title="Jeofizik Sheet Excel'e Aktar",
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")],
            )
            if not path:
                return
            try:
                wb = Workbook()
                ws = wb.active
                ws.title = "Jeofizik"
                for row in rows_from_sheet():
                    ws.append(row)
                wb.save(path)
            except Exception as exc:
                messagebox.showerror("Jeofizik Sheet", f"Excel kaydedilemedi:\n{exc}")
                return
            self.set_status(f"Jeofizik Sheet Excel'e aktarildi: {os.path.basename(path)}", level="success")

        def show_context_menu(event=None):
            menu = tk.Menu(win, tearoff=0)
            menu.add_command(label="20 satir ekle", command=lambda: add_rows(20))
            menu.add_command(label="Temizle", command=clear_sheet)
            menu.add_separator()
            menu.add_command(label="Kaydet", command=lambda: save_sheet(False))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        def safe_bind(sequence, func):
            try:
                sheet.bind(sequence, func)
            except tk.TclError:
                pass

        safe_bind("<Button-3>", show_context_menu)
        safe_bind("<Button-2>", show_context_menu)
        sheet.extra_bindings("all_modified_events", lambda event=None: refresh_info())

        buttons = ttk.Frame(win, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        tk.Button(buttons, text="Excel'den Al", command=import_excel, bg="#D6EAF8", font=FONT_BOLD).pack(side="left", padx=(0, 4))
        tk.Button(buttons, text="Excel'e Aktar", command=export_excel, bg="#D5F5E3", font=FONT_BOLD).pack(side="left", padx=4)
        tk.Button(buttons, text="+20 Satir", command=lambda: add_rows(20), bg=COLOR_ACCENT, fg="white", font=FONT_BOLD).pack(side="left", padx=4)
        tk.Button(buttons, text="Temizle", command=clear_sheet, bg=COLOR_DANGER, fg="white", font=FONT_BOLD).pack(side="left", padx=4)
        tk.Button(buttons, text="Kaydet", command=lambda: save_sheet(False), bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="right", padx=(4, 0))
        tk.Button(buttons, text="Kaydet ve Kapat", command=lambda: save_sheet(True), bg="#2C3E50", fg="white", font=FONT_BOLD).pack(side="right", padx=4)

        refresh_info()
