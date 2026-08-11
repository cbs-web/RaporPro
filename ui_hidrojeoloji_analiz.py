# Dosya: RaporPro/ui_hidrojeoloji_analiz.py
"""Hidrojeoloji cevre analizi sonucunu harita ve onay akisi ile gosterir."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


KARAR_VERME = "Karar verme"
SAPTANMADI = "Bu yarıçapta saptanmadı"


def _candidate_label(index, candidate):
    kind = {
        "akar": "akar",
        "kuru": "kuru/mevsimsel",
        "belirsiz": "türü belirsiz",
    }.get(candidate.get("tur"), "belirsiz")
    return (
        f"{index + 1}. {candidate.get('ad') or 'Adsız su yolu'} | "
        f"{candidate.get('mesafe_m', 0):g} m {candidate.get('yon', '')} | {kind}"
    )


class HidrojeolojiAnalizPenceresi(tk.Toplevel):
    def __init__(self, master, result, on_apply):
        super().__init__(master)
        self.result = result
        self.on_apply = on_apply
        self.title("Hidrojeoloji Çevre Analizi")
        self.minsize(1080, 680)
        width = min(1480, max(1080, self.winfo_screenwidth() - 100))
        height = min(900, max(680, self.winfo_screenheight() - 120))
        self.geometry(f"{width}x{height}+35+35")
        self.transient(master)
        self._motion_controller = getattr(master, "_ui_motion_controller", None)
        if self._motion_controller is not None:
            self._motion_controller.ui_motion_prepare_window(self)

        self._candidate_by_label = {}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        if self._motion_controller is not None:
            self._motion_controller.ui_motion_window_close(self)
        else:
            self.destroy()

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        source = (
            f"Kaynak: {self.result.get('kaynak', '-')} | "
            f"{self.result.get('kaynak_turu', '')} | "
            f"Sorgu: {self.result.get('sorgu_tarihi', '-')}"
        )
        ttk.Label(root, text=source, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        map_frame = ttk.Frame(root)
        map_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        map_frame.rowconfigure(1, weight=1)
        map_frame.columnconfigure(0, weight=1)

        map_tools = ttk.Frame(map_frame)
        map_tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(map_tools, text="Görünüm").pack(side="left")
        self.view_var = tk.StringVar(value="Yakın çevre")
        view = ttk.Combobox(
            map_tools,
            textvariable=self.view_var,
            values=("Yakın çevre", "Deniz dahil"),
            state="readonly",
            width=16,
        )
        view.pack(side="left", padx=8)
        view.bind("<<ComboboxSelected>>", lambda _event: self._draw_map())

        self.figure = Figure(figsize=(8, 6), dpi=100, tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=map_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        summary = ttk.LabelFrame(right, text="Analiz Özeti", padding=10)
        summary.grid(row=0, column=0, sticky="ew")
        summary.columnconfigure(1, weight=1)
        self._build_summary(summary)

        candidates_frame = ttk.LabelFrame(right, text="Bulunan Su Yolları", padding=8)
        candidates_frame.grid(row=1, column=0, sticky="nsew", pady=8)
        candidates_frame.rowconfigure(0, weight=1)
        candidates_frame.columnconfigure(0, weight=1)
        self._build_candidate_table(candidates_frame)

        approval = ttk.LabelFrame(right, text="Rapora Aktarılacak Bulgular", padding=10)
        approval.grid(row=2, column=0, sticky="ew")
        approval.columnconfigure(1, weight=1)
        self._build_approval(approval)

        warnings = "\n".join(f"- {item}" for item in self.result.get("uyarilar", []))
        if warnings:
            warning_label = ttk.Label(
                right,
                text=warnings,
                foreground="#A45A00",
                wraplength=520,
                justify="left",
            )
            warning_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        buttons = ttk.Frame(root)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Kapat", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Onaylananları Uygula",
            command=self._apply,
        ).pack(side="right", padx=(0, 8))

        self._draw_map()

    def _build_summary(self, parent):
        sea = self.result.get("deniz") or {}
        if sea.get("bulundu"):
            sea_text = f"{sea.get('mesafe_m', 0):g} m - {sea.get('yon', '')}"
        else:
            search_km = float(sea.get("arama_yaricapi_m") or 0) / 1000.0
            sea_text = f"{search_km:g} km içinde saptanmadı"

        rows = (
            ("İnceleme yarıçapı", f"{self.result.get('inceleme_yaricapi_m', 0)} m"),
            ("Denize uzaklık", sea_text),
            ("Su yolu adayı", str(len(self.result.get("su_yollari", [])))),
            ("Parsel KML", self.result.get("kml_dosya_adi", "-")),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(parent, text=label, font=("Segoe UI", 9, "bold")).grid(
                row=row, column=0, sticky="nw", padx=(0, 10), pady=2
            )
            ttk.Label(parent, text=value, wraplength=360).grid(
                row=row, column=1, sticky="nw", pady=2
            )

    def _build_candidate_table(self, parent):
        columns = ("ad", "tur", "mesafe", "yon")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=9)
        tree.heading("ad", text="Ad")
        tree.heading("tur", text="Sınıf")
        tree.heading("mesafe", text="Mesafe")
        tree.heading("yon", text="Yön")
        tree.column("ad", width=170, stretch=True)
        tree.column("tur", width=95, stretch=False)
        tree.column("mesafe", width=75, anchor="e", stretch=False)
        tree.column("yon", width=100, stretch=False)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        for index, item in enumerate(self.result.get("su_yollari", [])):
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.get("ad", ""),
                    item.get("tur", "belirsiz"),
                    f"{item.get('mesafe_m', 0):g} m",
                    item.get("yon", ""),
                ),
            )
        self.candidate_tree = tree

    def _options_for(self, wanted_kind):
        candidates = self.result.get("su_yollari", [])
        options = [KARAR_VERME, SAPTANMADI]
        explicit = []
        uncertain = []
        for index, candidate in enumerate(candidates):
            if candidate.get("tur") not in {wanted_kind, "belirsiz"}:
                continue
            label = _candidate_label(index, candidate)
            self._candidate_by_label[label] = candidate
            options.append(label)
            if candidate.get("tur") == wanted_kind:
                explicit.append(label)
            else:
                uncertain.append(label)
        if explicit:
            default = explicit[0]
        elif uncertain:
            default = KARAR_VERME
        else:
            default = SAPTANMADI
        return options, default

    def _build_approval(self, parent):
        sea = self.result.get("deniz") or {}
        self.sea_var = tk.BooleanVar(value=bool(sea.get("bulundu")))
        sea_text = "Denize uzaklığı aktar"
        ttk.Checkbutton(parent, text=sea_text, variable=self.sea_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        if not sea.get("bulundu"):
            self.sea_var.set(False)

        flowing_options, flowing_default = self._options_for("akar")
        dry_options, dry_default = self._options_for("kuru")
        self.flowing_var = tk.StringVar(value=flowing_default)
        self.dry_var = tk.StringVar(value=dry_default)

        ttk.Label(parent, text="Akar dere").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=3)
        ttk.Combobox(
            parent,
            textvariable=self.flowing_var,
            values=flowing_options,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(parent, text="Kuru dere").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=3)
        ttk.Combobox(
            parent,
            textvariable=self.dry_var,
            values=dry_options,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=3)

    def _draw_map(self):
        axes = self.axes
        axes.clear()
        all_points = []
        for ring in self.result.get("parsel_halkalari", []):
            if not ring:
                continue
            latitudes = [point[0] for point in ring]
            longitudes = [point[1] for point in ring]
            axes.fill(longitudes, latitudes, color="#E8EEF2", alpha=0.85, zorder=2)
            axes.plot(longitudes, latitudes, color="#1F3A4D", linewidth=2.2, label="Parsel", zorder=3)
            all_points.extend(ring)

        colors = {"akar": "#0077B6", "kuru": "#D97706", "belirsiz": "#6B7280"}
        labels_used = set()
        for candidate in self.result.get("su_yollari", []):
            points = candidate.get("noktalar") or []
            if not points:
                continue
            kind = candidate.get("tur", "belirsiz")
            label = {
                "akar": "Akar dere adayı",
                "kuru": "Kuru/mevsimsel dere adayı",
                "belirsiz": "Türü belirsiz su yolu",
            }.get(kind, "Su yolu")
            plot_label = label if label not in labels_used else "_nolegend_"
            labels_used.add(label)
            axes.plot(
                [point[1] for point in points],
                [point[0] for point in points],
                color=colors.get(kind, "#6B7280"),
                linewidth=2.0,
                label=plot_label,
                zorder=4,
            )
            all_points.extend(points)

        sea = self.result.get("deniz") or {}
        if self.view_var.get() == "Deniz dahil" and sea.get("bulundu"):
            points = sea.get("noktalar") or []
            if points:
                axes.plot(
                    [point[1] for point in points],
                    [point[0] for point in points],
                    color="#00A6C8",
                    linewidth=2.5,
                    label="Kıyı çizgisi",
                    zorder=1,
                )
                all_points.extend(points)

        center = self.result.get("parsel_merkezi") or [0, 0]
        if all_points and center[0]:
            axes.set_aspect(1.0 / max(0.2, math.cos(math.radians(center[0]))))
            lat_values = [point[0] for point in all_points]
            lon_values = [point[1] for point in all_points]
            lat_padding = max(0.00015, (max(lat_values) - min(lat_values)) * 0.08)
            lon_padding = max(0.00015, (max(lon_values) - min(lon_values)) * 0.08)
            axes.set_xlim(min(lon_values) - lon_padding, max(lon_values) + lon_padding)
            axes.set_ylim(min(lat_values) - lat_padding, max(lat_values) + lat_padding)
        axes.set_title("Parsel ve Hidrografya Ön Değerlendirmesi")
        axes.set_xlabel("Boylam")
        axes.set_ylabel("Enlem")
        axes.grid(True, color="#D8DEE3", linewidth=0.6)
        handles, labels = axes.get_legend_handles_labels()
        if handles:
            axes.legend(loc="best", fontsize=8)
        self.canvas.draw_idle()

    def _selected_candidate(self, value):
        return self._candidate_by_label.get(value)

    def _apply(self):
        flowing = self._selected_candidate(self.flowing_var.get())
        dry = self._selected_candidate(self.dry_var.get())
        if flowing is not None and dry is not None and flowing.get("id") == dry.get("id"):
            messagebox.showwarning(
                "Hidrojeoloji",
                "Aynı su yolu hem akar hem kuru dere olarak seçilemez.",
                parent=self,
            )
            return

        selection = {
            "deniz_uygula": bool(self.sea_var.get()),
            "akar_aday": flowing,
            "akar_yok": self.flowing_var.get() == SAPTANMADI,
            "kuru_aday": dry,
            "kuru_yok": self.dry_var.get() == SAPTANMADI,
        }
        self.on_apply(self.result, selection)
        self._close()


__all__ = ["HidrojeolojiAnalizPenceresi", "KARAR_VERME", "SAPTANMADI"]
