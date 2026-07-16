# Dosya: RaporPro/ui_gorev_merkezi.py
"""Ortak arka plan işlemlerini izleyen ve iptal eden Görev Merkezi arayüzü."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from sabitler import COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_MUTED, COLOR_WARNING, FONT_UI_PAGE, SPACE_MD


_DURUM_ETIKETI = {
    "queued": "Sırada",
    "waiting": "Bekliyor",
    "running": "Çalışıyor",
    "cancelling": "İptal ediliyor",
    "completed": "Tamamlandı",
    "cancelled": "İptal edildi",
    "failed": "Hata",
}


class GorevMerkeziMixin:
    def gorev_merkezi_penceresi(self):
        existing = getattr(self, "_gorev_merkezi_win", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        win = tk.Toplevel(self.root)
        self._gorev_merkezi_win = win
        self.pencere_hazirla(win, "Görev Merkezi", "980x560", (760, 440), modal=False)

        def close():
            self._gorev_merkezi_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close)

        body = ttk.Frame(win, padding=SPACE_MD)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Arka Plan Görevleri", font=FONT_UI_PAGE).pack(anchor="w")
        summary_var = tk.StringVar(value="Görev motoru hazır")
        ttk.Label(body, textvariable=summary_var, foreground=COLOR_TEXT_MUTED).pack(anchor="w", pady=(2, 10))

        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)
        columns = ("id", "name", "state", "progress", "time", "message")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "No",
            "name": "İşlem",
            "state": "Durum",
            "progress": "İlerleme",
            "time": "Süre",
            "message": "Ayrıntı",
        }
        widths = {"id": 55, "name": 210, "state": 110, "progress": 100, "time": 80, "message": 350}
        for key in columns:
            tree.heading(key, text=headings[key])
            tree.column(key, width=widths[key], minwidth=50, stretch=key in {"name", "message"})
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.tag_configure("running", foreground=COLOR_WARNING)
        tree.tag_configure("completed", foreground=COLOR_SUCCESS)
        tree.tag_configure("cancelled", foreground=COLOR_TEXT_MUTED)
        tree.tag_configure("failed", foreground=COLOR_DANGER)

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(
            footer,
            text="Pencere kapatılsa da işlemler arka planda devam eder.",
            foreground=COLOR_TEXT_MUTED,
        ).pack(side="left")

        def selected_task_id():
            selected = tree.selection()
            if not selected:
                return None
            try:
                return int(selected[0])
            except (TypeError, ValueError):
                return None

        def cancel_selected():
            engine = getattr(self, "task_engine", None)
            task_id = selected_task_id()
            if engine is not None and task_id is not None:
                engine.cancel(task_id)

        def cancel_all():
            engine = getattr(self, "task_engine", None)
            if engine is not None:
                engine.cancel_all()

        cancel_btn = self.modern_button(
            footer,
            "Seçili Görevi İptal Et",
            command=cancel_selected,
            role="warning",
            outline=True,
        )
        cancel_btn.pack(side="right", padx=(6, 0))
        self.modern_button(
            footer,
            "Tümünü İptal Et",
            command=cancel_all,
            role="danger",
            outline=True,
        ).pack(side="right")

        def refresh():
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            engine = getattr(self, "task_engine", None)
            tasks = engine.list_tasks(include_finished=True) if engine is not None else []
            selected = tree.selection()
            selected_id = selected[0] if selected else None
            tree.delete(*tree.get_children())
            for task in tasks:
                if task.total > 0:
                    progress = f"{task.completed:g}/{task.total:g}"
                elif task.state in {"completed", "cancelled", "failed"}:
                    progress = "-"
                else:
                    progress = "Çalışıyor"
                tree.insert(
                    "",
                    "end",
                    iid=str(task.task_id),
                    values=(
                        task.task_id,
                        task.name,
                        _DURUM_ETIKETI.get(task.state, task.state),
                        progress,
                        f"{task.elapsed:.1f} sn",
                        task.error or task.message,
                    ),
                    tags=(task.state,),
                )
            if selected_id and tree.exists(selected_id):
                tree.selection_set(selected_id)
            snapshot = engine.snapshot() if engine is not None else None
            active = snapshot.active_count if snapshot is not None else 0
            completed = snapshot.completed_count if snapshot is not None else 0
            failed = snapshot.failed_count if snapshot is not None else 0
            cancelled = snapshot.cancelled_count if snapshot is not None else 0
            summary_var.set(
                f"Çalışan: {active}  |  Tamamlanan: {completed}  |  İptal: {cancelled}  |  Hata: {failed}"
            )
            selected_task = next((task for task in tasks if str(task.task_id) == selected_id), None)
            cancel_btn.configure(
                state="normal" if selected_task is not None and selected_task.cancellable else "disabled"
            )
            win.after(500, refresh)

        refresh()


__all__ = ["GorevMerkeziMixin"]
