# Dosya: RaporPro/cizim.py
import tkinter as tk
from tkinter import Toplevel, Canvas, ttk, Scrollbar, messagebox
import numpy as np
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.legend_handler import HandlerPatch

from yardimcilar import safe_float, litoloji_cozumle, litoloji_yazim_uyarilari
from sabitler import LEJANTLAR, COLOR_BG, COLOR_ACCENT, COLOR_SUCCESS, FONT_BOLD, FONT_MAIN

class GeoEngineDraw:
    """Cizim yardimci fonksiyonlari"""
    @staticmethod
    def _add_line_collection(ax, segments, color, linewidth, clip, zorder, alpha=None, dashes=None):
        if not segments:
            return None
        collection = LineCollection(
            segments,
            colors=color,
            linewidths=linewidth,
            zorder=zorder,
            alpha=alpha,
        )
        if dashes:
            collection.set_linestyle(dashes)
        collection.set_clip_path(clip)
        ax.add_collection(collection)
        return collection

    @staticmethod
    def _add_patch_collection(ax, patches, color, linewidth, clip, zorder):
        if not patches:
            return None
        collection = PatchCollection(
            patches,
            match_original=False,
            facecolors="none",
            edgecolors=color,
            linewidths=linewidth,
            zorder=zorder,
        )
        collection.set_clip_path(clip)
        ax.add_collection(collection)
        return collection

    @staticmethod
    def _shared_segment(a1, a2, b1, b2, tol):
        a1 = np.asarray(a1, dtype=float)
        a2 = np.asarray(a2, dtype=float)
        b1 = np.asarray(b1, dtype=float)
        b2 = np.asarray(b2, dtype=float)
        va = a2 - a1
        vb = b2 - b1
        la = np.hypot(va[0], va[1])
        lb = np.hypot(vb[0], vb[1])
        if la <= tol or lb <= tol:
            return None
        cross = abs(va[0] * vb[1] - va[1] * vb[0])
        if cross > tol * max(la, lb):
            return None

        def point_line_dist(p):
            return abs(va[0] * (p[1] - a1[1]) - va[1] * (p[0] - a1[0])) / la

        if point_line_dist(b1) > tol or point_line_dist(b2) > tol:
            return None

        unit = va / la
        tb1 = float(np.dot(b1 - a1, unit))
        tb2 = float(np.dot(b2 - a1, unit))
        lo = max(0.0, min(tb1, tb2))
        hi = min(la, max(tb1, tb2))
        if hi - lo <= tol:
            return None
        return a1 + unit * lo, a1 + unit * hi

    @staticmethod
    def hide_same_unit_seams(ax, polygons, tolerance=0.08):
        for artist in list(getattr(ax, "_geo_same_unit_seam_masks", [])):
            try:
                artist.remove()
            except Exception:
                pass

        masks = []
        poly_data = []
        for poly in polygons or []:
            if getattr(poly, "_geo_hidden", False):
                continue
            if hasattr(poly, "get_visible") and not poly.get_visible():
                continue
            code = getattr(poly, "_geo_unit_code", None)
            if not code:
                continue
            correlation_key = getattr(poly, "_geo_correlation_key", None) or code
            kind = getattr(poly, "_geo_poly_kind", "section")
            if kind == "well":
                continue
            try:
                xy = np.asarray(poly.get_xy(), dtype=float)
            except Exception:
                continue
            if len(xy) < 3:
                continue
            if np.allclose(xy[0], xy[-1]):
                xy = xy[:-1]
            if len(xy) >= 3:
                poly_data.append((poly, code, correlation_key, kind, xy))

        drawn = set()
        for i, (poly_a, code_a, correlation_a, kind_a, xy_a) in enumerate(poly_data):
            for poly_b, code_b, correlation_b, kind_b, xy_b in poly_data[i + 1:]:
                if code_a != code_b or correlation_a != correlation_b:
                    continue
                color = poly_a.get_facecolor()
                if len(color) == 4:
                    color = (color[0], color[1], color[2], 1.0)
                for idx_a in range(len(xy_a)):
                    a1 = xy_a[idx_a]
                    a2 = xy_a[(idx_a + 1) % len(xy_a)]
                    for idx_b in range(len(xy_b)):
                        b1 = xy_b[idx_b]
                        b2 = xy_b[(idx_b + 1) % len(xy_b)]
                        segment = GeoEngineDraw._shared_segment(a1, a2, b1, b2, tolerance)
                        if not segment:
                            continue
                        p1, p2 = segment
                        key_pts = sorted(((round(float(p1[0]), 2), round(float(p1[1]), 2)), (round(float(p2[0]), 2), round(float(p2[1]), 2))))
                        key = (code_a, correlation_a, key_pts[0], key_pts[1])
                        if key in drawn:
                            continue
                        drawn.add(key)
                        line, = ax.plot(
                            [p1[0], p2[0]], [p1[1], p2[1]],
                            color=color, lw=2.0, solid_capstyle='round',
                            zorder=24.5
                        )
                        masks.append(line)

        ax._geo_same_unit_seam_masks = masks
        return masks

    """Çizim yardımcı fonksiyonları"""
    @staticmethod
    def clear_pattern(patch_obj):
        for artist in list(getattr(patch_obj, "_geo_pattern_artists", [])):
            try:
                artist.remove()
            except Exception:
                pass
        patch_obj._geo_pattern_artists = []

    @staticmethod
    def refresh_pattern(ax, patch_obj):
        info = getattr(patch_obj, "_geo_pattern_info", None)
        if not info:
            return []
        style_code, color, density_scale = info
        return GeoEngineDraw.draw_pattern(ax, patch_obj, style_code, color, density_scale=density_scale)

    @staticmethod
    def draw_pattern(ax, patch_obj, style_code, color, bbox=None, density_scale=1.0):
        if not style_code: return []
        artists = []
        if patch_obj:
            GeoEngineDraw.clear_pattern(patch_obj)
            patch_obj._geo_pattern_info = (style_code, color, density_scale)
            clip = patch_obj
            if not bbox:
                path = patch_obj.get_path(); ext = path.get_extents(); x_min, x_max, y_min, y_max = ext.xmin, ext.xmax, ext.ymin, ext.ymax
            else: x_min, x_max, y_min, y_max = bbox
        else:
            if bbox:
                x_min, x_max, y_min, y_max = bbox
                clip = mpatches.Rectangle((x_min, y_min), x_max-x_min, y_max-y_min, transform=ax.transData, facecolor='none', edgecolor='none', zorder=1)
                ax.add_patch(clip)
            else: return []

        z_pattern = 21
        STEP_X_DOT = max(0.011, 0.025 * density_scale); STEP_Y_DOT = max(0.011, 0.025 * density_scale)
        STEP_X_GRAVEL = max(0.026, 0.05 * density_scale); STEP_Y_GRAVEL = max(0.026, 0.05 * density_scale)
        STEP_Y_LINE = max(0.019, 0.03 * density_scale)

        if style_code == "nokta":
            ys = np.arange(y_min + STEP_Y_DOT * 0.45, y_max, STEP_Y_DOT)
            for row_idx, yy in enumerate(ys):
                offset = STEP_X_DOT * (0.25 if row_idx % 2 else 0.70)
                xs = np.arange(x_min + offset, x_max, STEP_X_DOT * 1.25)
                if not len(xs):
                    continue
                dots, = ax.plot(xs, np.full_like(xs, yy), '.', color=color, markersize=1.2, zorder=z_pattern)
                dots.set_clip_path(clip)
                artists.append(dots)
        elif style_code == "cakil_daire":
            ys = np.arange(y_min + STEP_Y_GRAVEL * 0.50, y_max + STEP_Y_GRAVEL/2, STEP_Y_GRAVEL)
            for row_idx, yy in enumerate(ys):
                offset = STEP_X_GRAVEL * (0.25 if row_idx % 2 else 0.75)
                xs = np.arange(x_min + offset, x_max + STEP_X_GRAVEL/2, STEP_X_GRAVEL * 1.12)
                xs = xs[xs < x_max]
                if not len(xs):
                    continue
                dots, = ax.plot(xs, np.full_like(xs, yy), 'o', color=color, markersize=3.0, fillstyle='none', markeredgewidth=0.5, zorder=z_pattern)
                dots.set_clip_path(clip)
                artists.append(dots)
        elif style_code == "moloz_parca":
            step_x = max(0.012, 0.045 * density_scale)
            step_y = max(0.012, 0.040 * density_scale)
            base_size = max(0.004, min(step_x, step_y) * 0.34)
            xs = np.arange(x_min + step_x * 0.35, x_max, step_x)
            ys = np.arange(y_min + step_y * 0.35, y_max, step_y)
            pieces = []
            for row_idx, yy in enumerate(ys):
                for col_idx, xx in enumerate(xs):
                    if (row_idx + col_idx) % 4 == 0:
                        continue
                    jitter_x = ((row_idx * 17 + col_idx * 7) % 9 - 4) * step_x * 0.035
                    jitter_y = ((row_idx * 11 + col_idx * 5) % 9 - 4) * step_y * 0.035
                    cx = xx + jitter_x
                    cy = yy + jitter_y
                    size = base_size * (0.78 + ((row_idx + col_idx) % 3) * 0.18)
                    if (row_idx + col_idx) % 3 == 0:
                        pts = [(cx - size, cy - size * 0.55), (cx + size * 0.75, cy - size), (cx + size * 0.55, cy + size * 0.85), (cx - size * 0.8, cy + size * 0.65)]
                    elif (row_idx + col_idx) % 3 == 1:
                        pts = [(cx - size * 0.9, cy), (cx - size * 0.1, cy + size), (cx + size, cy + size * 0.2), (cx + size * 0.35, cy - size * 0.85)]
                    else:
                        pts = [(cx - size, cy - size), (cx + size * 0.9, cy - size * 0.25), (cx - size * 0.25, cy + size)]
                    pieces.append(mpatches.Polygon(pts, closed=True))
            collection = GeoEngineDraw._add_patch_collection(ax, pieces, color, 0.55, clip, z_pattern)
            if collection:
                artists.append(collection)
        elif style_code == "kesikli":
            dash_len = max(0.014, 0.040 * density_scale)
            gap_len = max(0.007, 0.018 * density_scale)
            segments = []
            for row_idx, yl in enumerate(np.arange(y_min, y_max, STEP_Y_LINE)):
                start = x_min + (dash_len + gap_len) * (0.55 if row_idx % 2 else 0.05)
                for x0 in np.arange(start, x_max, dash_len + gap_len):
                    x1 = min(x0 + dash_len, x_max)
                    segments.append([(x0, yl), (x1, yl)])
            collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.8, clip, z_pattern)
            if collection:
                artists.append(collection)
        elif style_code == "noktali_kesikli":
            dash_len = max(0.018, 0.045 * density_scale)
            gap_len = max(0.010, 0.024 * density_scale)
            segments = []
            all_dot_xs = []
            all_dot_ys = []
            for row_idx, yl in enumerate(np.arange(y_min, y_max, STEP_Y_LINE)):
                start = x_min + (dash_len + gap_len) * (0.50 if row_idx % 2 else 0.05)
                for x0 in np.arange(start, x_max, dash_len + gap_len):
                    x1 = min(x0 + dash_len, x_max)
                    segments.append([(x0, yl), (x1, yl)])
                    dot_x = x1 + gap_len * 0.45
                    if dot_x < x_max:
                        all_dot_xs.append(dot_x)
                        all_dot_ys.append(yl)
            collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.75, clip, z_pattern)
            if collection:
                artists.append(collection)
            if all_dot_xs:
                dots, = ax.plot(all_dot_xs, all_dot_ys, '.', color=color, markersize=1.0, zorder=z_pattern)
                dots.set_clip_path(clip)
                artists.append(dots)
        elif style_code == "kiltasi_cizgili_noktali":
            segments = [[(x_min, yl), (x_max, yl)] for yl in np.arange(y_min, y_max, STEP_Y_LINE * 0.9)]
            collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.75, clip, z_pattern, dashes=[(0, (5, 2))])
            if collection:
                artists.append(collection)
            xs = np.arange(x_min + STEP_X_DOT, x_max, STEP_X_DOT * 2.2)
            ys = np.arange(y_min + STEP_Y_DOT, y_max, STEP_Y_DOT * 1.8)
            if len(xs) and len(ys):
                gx, gy = np.meshgrid(xs, ys)
                dots, = ax.plot(gx.flatten(), gy.flatten(), '.', color=color, markersize=0.95, zorder=z_pattern)
                dots.set_clip_path(clip)
                artists.append(dots)
        elif style_code == "ot":
            area_factor = 200 / (density_scale**2); num = int((x_max-x_min)*(y_max-y_min)*area_factor)
            if num > 0:
                rx = np.random.uniform(x_min, x_max, num); ry = np.random.uniform(y_min, y_max, num)
                segments = [
                    [
                        (rx[i], ry[i] + 0.015 * density_scale),
                        (rx[i] + 0.01 * density_scale, ry[i]),
                        (rx[i] + 0.02 * density_scale, ry[i] + 0.015 * density_scale),
                    ]
                    for i in range(len(rx))
                ]
                collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.5, clip, z_pattern)
                if collection:
                    artists.append(collection)
        elif style_code == "kumtasi_yatay":
            segments = [[(x_min, yl), (x_max, yl)] for yl in np.arange(y_min, y_max, STEP_Y_LINE)]
            collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.5, clip, z_pattern, alpha=0.7)
            if collection:
                artists.append(collection)
            ys = np.arange(y_min + STEP_Y_DOT, y_max, STEP_Y_DOT * 1.7)
            for row_idx, yy in enumerate(ys):
                offset = STEP_X_DOT * (0.45 if row_idx % 2 else 1.05)
                xs = np.arange(x_min + offset, x_max, STEP_X_DOT * 1.7)
                if not len(xs):
                    continue
                dots, = ax.plot(xs, np.full_like(xs, yy), '.', color=color, markersize=1, zorder=z_pattern)
                dots.set_clip_path(clip)
                artists.append(dots)
        elif style_code == "cakil_oval_cizgili":
            segments = [[(x_min, yl), (x_max, yl)] for yl in np.arange(y_min, y_max, STEP_Y_LINE*2)]
            collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.5, clip, z_pattern, dashes=[(0, (6, 2))])
            if collection:
                artists.append(collection)
            xs = np.arange(x_min + STEP_X_GRAVEL * 0.45, x_max, STEP_X_GRAVEL * 1.25)
            ys = np.arange(y_min + STEP_Y_GRAVEL * 0.55, y_max, STEP_Y_GRAVEL * 1.15)
            for row_idx, yy in enumerate(ys):
                row_offset = (STEP_X_GRAVEL * 0.55) if row_idx % 2 else 0.0
                row_xs = xs + row_offset
                row_xs = row_xs[row_xs < x_max]
                if not len(row_xs):
                    continue
                rings, = ax.plot(
                    row_xs,
                    np.full_like(row_xs, yy),
                    'o',
                    color=color,
                    markersize=3.1,
                    fillstyle='none',
                    markeredgewidth=0.55,
                    zorder=z_pattern
                )
                rings.set_clip_path(clip)
                artists.append(rings)
        elif style_code == "dolgu_karisik":
            diag_step = max(0.015, 0.055 * density_scale)
            span_x = max(abs(x_max - x_min), diag_step)
            span_y = max(abs(y_max - y_min), diag_step)
            segments = []
            for offset in np.arange(y_min - span_y, y_max + span_y, diag_step):
                segments.append([
                    (x_min - span_x * 0.15, offset),
                    (x_max + span_x * 0.15, offset + span_y * 0.65),
                ])
            collection = GeoEngineDraw._add_line_collection(ax, segments, color, 0.55, clip, z_pattern, alpha=0.75)
            if collection:
                artists.append(collection)
            step_x = max(0.018, 0.060 * density_scale)
            step_y = max(0.018, 0.052 * density_scale)
            base_size = max(0.004, min(step_x, step_y) * 0.25)
            xs = np.arange(x_min + step_x * 0.45, x_max, step_x)
            ys = np.arange(y_min + step_y * 0.45, y_max, step_y)
            pieces = []
            for row_idx, yy in enumerate(ys):
                for col_idx, xx in enumerate(xs):
                    if (row_idx + col_idx) % 3 == 0:
                        continue
                    jitter_x = ((row_idx * 13 + col_idx * 5) % 7 - 3) * step_x * 0.045
                    jitter_y = ((row_idx * 7 + col_idx * 11) % 7 - 3) * step_y * 0.045
                    cx = xx + jitter_x
                    cy = yy + jitter_y
                    size = base_size * (0.85 + ((row_idx + col_idx) % 2) * 0.25)
                    pts = [
                        (cx - size, cy - size * 0.35),
                        (cx - size * 0.15, cy + size * 0.9),
                        (cx + size * 0.9, cy + size * 0.2),
                        (cx + size * 0.35, cy - size * 0.8),
                    ]
                    pieces.append(mpatches.Polygon(pts, closed=True))
            collection = GeoEngineDraw._add_patch_collection(ax, pieces, color, 0.5, clip, z_pattern)
            if collection:
                artists.append(collection)

        if patch_obj:
            patch_obj._geo_pattern_artists = artists
        return artists

class VeriGirisPenceresi(Toplevel):
    def __init__(self, parent, baslik, kolonlar, veri_listesi, on_save=None, sondaj_derinligi=None):
        super().__init__(parent)
        self.title(baslik)
        self.geometry("900x600")
        self.configure(bg=COLOR_BG)
        
        self.veri = veri_listesi
        self.kolonlar = kolonlar
        self.satirlar = []
        self.on_save = on_save
        self.litoloji_modu = [str(col).strip().lower() for col in kolonlar[:3]] == ["başlangıç", "bitiş", "tanım"]
        self.sondaj_derinligi = safe_float(sondaj_derinligi)
        self.aktif_hucre = None
        self.litoloji_uyari_var = tk.StringVar(value="")
        if self.litoloji_modu:
            style = ttk.Style(self)
            style.configure(
                "LitolojiNormal.TEntry",
                fieldbackground="white",
                foreground="#1F2933",
            )
            style.configure(
                "LitolojiWarning.TEntry",
                fieldbackground="#FCF3CF",
                foreground="#1F2933",
            )
        
        self.c = Canvas(self, bg=COLOR_BG)
        self.f = ttk.Frame(self.c)
        self.s = ttk.Scrollbar(self, orient="vertical", command=self.c.yview)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.c.configure(yscrollcommand=self.s.set)
        self.c.grid(row=0, column=0, sticky="nsew")
        self.s.grid(row=0, column=1, sticky="ns")
        self._canvas_window = self.c.create_window((0, 0), window=self.f, anchor="nw")
        
        self.f.bind("<Configure>", lambda e: self.c.configure(scrollregion=self.c.bbox("all")))
        if self.litoloji_modu:
            self.f.columnconfigure(0, weight=1, minsize=120)
            self.f.columnconfigure(1, weight=1, minsize=120)
            self.f.columnconfigure(2, weight=3, minsize=300)
            self.c.bind("<Configure>", self._litoloji_tablo_genisligi_guncelle)
        
        for i, col in enumerate(kolonlar):
            ttk.Label(self.f, text=col, font=FONT_BOLD, relief="flat", background="#dfe6e9", anchor="center", padding=5).grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
        
        if self.veri: 
            for v in self.veri: self.satir_ekle(v)
        
        if not self.satirlar: self.satir_ekle()
        
        btn_f = ttk.Frame(self, padding=10)
        btn_f.grid(row=1, column=0, columnspan=2, sticky="ew")
        btn_f.columnconfigure(1, weight=1)
        
        self.btn_satir_ekle = tk.Button(
            btn_f,
            text="+ Satır Ekle",
            command=lambda: self.satir_ekle(),
            bg=COLOR_ACCENT,
            fg="white",
            font=FONT_BOLD,
        )
        self.btn_satir_ekle.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.lbl_litoloji_uyari = ttk.Label(
            btn_f,
            textvariable=self.litoloji_uyari_var,
            foreground="#9A7D0A",
            anchor="w",
            justify="left",
            wraplength=420,
        )
        self.lbl_litoloji_uyari.grid(row=0, column=1, sticky="ew", padx=8)
        self.btn_kaydet_kapat = tk.Button(
            btn_f,
            text="💾 KAYDET VE KAPAT",
            bg=COLOR_SUCCESS,
            fg="white",
            font=FONT_BOLD,
            command=self.kaydet,
        )
        self.btn_kaydet_kapat.grid(row=0, column=2, sticky="e", padx=(10, 0))
        btn_f.bind("<Configure>", self._litoloji_uyari_genisligi_guncelle)
        self.litoloji_yazim_kontrol()

    def _litoloji_tablo_genisligi_guncelle(self, event):
        if not self.litoloji_modu:
            return
        self.c.itemconfigure(self._canvas_window, width=max(1, event.width))

    def _litoloji_uyari_genisligi_guncelle(self, event):
        if not hasattr(self, "lbl_litoloji_uyari"):
            return
        button_width = (
            self.btn_satir_ekle.winfo_reqwidth()
            + self.btn_kaydet_kapat.winfo_reqwidth()
            + 70
        )
        self.lbl_litoloji_uyari.configure(
            wraplength=max(180, event.width - button_width)
        )

    def varsayilan_litoloji_satiri(self):
        if not self.satirlar:
            return ["0.0", "0.5", "Bitkisel toprak"]
        onceki_bitis = self.satirlar[-1][1].get().strip() if len(self.satirlar[-1]) > 1 else ""
        baslangic = onceki_bitis or "0.0"
        return [baslangic, "", ""]

    def satir_ekle(self, vals=None):
        if vals is None and self.litoloji_modu:
            vals = self.varsayilan_litoloji_satiri()
        r_idx = len(self.satirlar) + 1
        row_ents = []
        for i in range(len(self.kolonlar)):
            w = 54 if "Tanım" in self.kolonlar[i] else 18
            e = ttk.Entry(self.f, width=w, font=FONT_MAIN)
            e.grid(row=r_idx, column=i, padx=2, pady=2, sticky="ew")
            if vals and i < len(vals): e.insert(0, vals[i])
            row_ents.append(e)

        for col_idx, entry in enumerate(row_ents):
            entry.bind("<FocusIn>", lambda event, c=col_idx: self.aktif_hucre_ayarla(event.widget, c), add="+")
            entry.bind("<Return>", lambda event, r=row_ents, c=col_idx: self.hucreye_git(r, c, 1))
            entry.bind("<Down>", lambda event, r=row_ents, c=col_idx: self.hucreye_git(r, c, 1))
            entry.bind("<Up>", lambda event, r=row_ents, c=col_idx: self.hucreye_git(r, c, -1))
            entry.bind("<Button-3>", lambda event, r=row_ents, c=col_idx: self.satir_sag_tik(event, r, c), add="+")
            if self.litoloji_modu:
                entry.bind("<KeyRelease>", lambda event: self.litoloji_yazim_kontrol(), add="+")
                entry.bind("<FocusOut>", lambda event: self.litoloji_yazim_kontrol(), add="+")
            if self.litoloji_modu and col_idx == 2:
                entry.configure(style="LitolojiNormal.TEntry")
        
        son_entry = row_ents[-1]
        son_entry.bind("<Tab>", lambda event, r=row_ents: self.tab_basildi(event, r))
        self.satirlar.append(row_ents)
        self.f.update_idletasks()
        self.c.configure(scrollregion=self.c.bbox("all"))
        self.litoloji_yazim_kontrol()
        return row_ents

    def aktif_hucre_ayarla(self, widget, col_idx):
        self.aktif_hucre = (widget, col_idx)

    def hucreye_git(self, row_ents, col_idx, delta):
        if row_ents not in self.satirlar:
            return "break"
        row_idx = self.satirlar.index(row_ents) + delta
        if row_idx >= len(self.satirlar):
            self.satir_ekle()
        if 0 <= row_idx < len(self.satirlar):
            col_idx = max(0, min(col_idx, len(self.satirlar[row_idx]) - 1))
            entry = self.satirlar[row_idx][col_idx]
            entry.focus_set()
            entry.selection_range(0, tk.END)
        return "break"

    def satir_sag_tik(self, event, row_ents, col_idx):
        self.aktif_hucre_ayarla(event.widget, col_idx)
        try:
            event.widget.focus_set()
        except Exception:
            pass
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Seçili satırı sil", command=lambda r=row_ents: self.satir_sil(r))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"

    def satir_sil(self, row_ents):
        if row_ents not in self.satirlar:
            return
        if not messagebox.askyesno("Satırı Sil", "Seçili satır silinsin mi?", parent=self):
            return
        for entry in row_ents:
            entry.destroy()
        self.satirlar.remove(row_ents)
        if not self.satirlar:
            self.satir_ekle()
        else:
            for row_idx, row in enumerate(self.satirlar, start=1):
                for col_idx, entry in enumerate(row):
                    entry.grid_configure(row=row_idx, column=col_idx)
        self.f.update_idletasks()
        self.c.configure(scrollregion=self.c.bbox("all"))
        self.litoloji_yazim_kontrol()

    def litoloji_aralik_uyarilari(self):
        if not self.litoloji_modu:
            return []
        intervals = []
        warnings = []
        for row_idx, row in enumerate(self.satirlar, start=1):
            vals = [entry.get().strip() for entry in row]
            if not any(vals):
                continue
            if len(vals) < 2:
                warnings.append(f"{row_idx}. satırda başlangıç/bitiş eksik.")
                continue
            top, bot = safe_float(vals[0]), safe_float(vals[1])
            if bot <= top:
                warnings.append(f"{row_idx}. satırda başlangıç/bitiş uyumsuz.")
                continue
            intervals.append((top, bot, row_idx))
        if not intervals:
            return warnings
        intervals.sort(key=lambda item: item[0])
        if intervals[0][0] > 0.05:
            warnings.append("Litoloji 0.00 m'den başlamıyor.")
        prev_bot = intervals[0][1]
        for top, bot, row_idx in intervals[1:]:
            if top < prev_bot - 0.01:
                warnings.append(f"{row_idx}. satır önceki tabakayla çakışıyor.")
            elif top > prev_bot + 0.01:
                warnings.append(f"{prev_bot:g}-{top:g} m arasında litoloji boşluğu var.")
            prev_bot = max(prev_bot, bot)
        if self.sondaj_derinligi > 0:
            if prev_bot > self.sondaj_derinligi + 0.05:
                warnings.append("Litoloji sondaj derinliğini geçiyor.")
            elif prev_bot < self.sondaj_derinligi - 0.05:
                warnings.append("Litoloji kuyu sonuna kadar gitmiyor.")
        return warnings

    def litoloji_yazim_kontrol(self):
        if not self.litoloji_modu:
            return
        messages = self.litoloji_aralik_uyarilari()
        for row_idx, row in enumerate(self.satirlar, start=1):
            if len(row) < 3:
                continue
            entry = row[2]
            warnings = litoloji_yazim_uyarilari(entry.get())
            entry.configure(style="LitolojiWarning.TEntry" if warnings else "LitolojiNormal.TEntry")
            if warnings:
                messages.append(f"{row_idx}. satır: {warnings[0]}")
        if hasattr(self, "litoloji_uyari_var"):
            self.litoloji_uyari_var.set(" | ".join(messages[:2]))

    def tab_basildi(self, event, tetikleyen):
        if self.satirlar[-1] == tetikleyen:
            yeni_satir_ents = self.satir_ekle()
            yeni_satir_ents[0].focus_set()
            return "break"
        return None

    def kaydet(self):
        if self.litoloji_modu:
            depth_warnings = self.litoloji_aralik_uyarilari()
            if depth_warnings:
                msg = "\n".join(depth_warnings[:6])
                if len(depth_warnings) > 6:
                    msg += f"\n... ve {len(depth_warnings) - 6} uyarı daha"
                if not messagebox.askyesno("Litoloji Uyarısı", f"{msg}\n\nYine de kaydedilsin mi?", parent=self):
                    self.litoloji_yazim_kontrol()
                    return
        self.veri.clear()
        for row in self.satirlar:
            vals = [e.get().strip() for e in row]
            if any(vals):
                self.veri.append(vals)
        if callable(self.on_save):
            self.on_save()
        self.destroy()

# --- DÜZELTİLMİŞ ETKİLEŞİMLİ ARAÇLAR ---
class AdvancedPolygonInteractor:
    def __init__(self, ax, poly_list):
        self.ax = ax
        self.poly_list = poly_list
        self.canvas = ax.figure.canvas
        self.selected_poly = None
        self.dragging = False
        self.move_active = False # Çakışmayı önlemek için eklendi
        
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('motion_notify_event', self.on_drag)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('key_press_event', self.on_key)
        
    def on_key(self, event):
        if event.key in ['m', 'M']: # M tuşu ile komple Poligon Taşıma aktifleşir
            self.move_active = not self.move_active

    def on_click(self, event):
        if not self.move_active or event.inaxes != self.ax: return
        for poly in self.poly_list:
            contains, _ = poly.contains(event)
            if contains:
                self.selected_poly = poly
                self.dragging = True
                self.start_xy = (event.xdata, event.ydata)
                self.poly_xy = poly.get_xy()
                tool = getattr(self.ax.figure, "_geo_tool", None)
                self.before_xy = tool.poly_xy(poly) if tool is not None and hasattr(tool, "poly_xy") else [[float(x), float(y)] for x, y in poly.get_xy()]
                return

    def on_drag(self, event):
        if self.dragging and self.selected_poly and event.xdata and event.ydata:
            dx = event.xdata - self.start_xy[0]
            dy = event.ydata - self.start_xy[1]
            new_xy = self.poly_xy + [dx, dy]
            self.selected_poly.set_xy(new_xy)
            GeoEngineDraw.refresh_pattern(self.ax, self.selected_poly)
            tool = getattr(self.ax.figure, "_geo_tool", None)
            if tool is not None and hasattr(tool, "refresh_same_unit_seams"):
                tool.refresh_same_unit_seams()
            else:
                GeoEngineDraw.hide_same_unit_seams(self.ax, self.poly_list)
            self.canvas.draw_idle()

    def on_release(self, event):
        if self.dragging and self.selected_poly is not None:
            tool = getattr(self.ax.figure, "_geo_tool", None)
            if tool is not None and hasattr(tool, "record_history"):
                tool.record_history(self.selected_poly, getattr(self, "before_xy", None))
        self.dragging = False
        self.selected_poly = None
        self.before_xy = None

class PolygonDrawerInteractor:
    def __init__(self, ax, master_list, radio_widget=None):
        self.ax = ax
        self.master_list = master_list
        self.canvas = ax.figure.canvas
        self.radio = radio_widget
        self.points = []
        self.line, = ax.plot([], [], 'r--', lw=1.5)
        
        self.drawing_active = False # SORUNUN ÇÖZÜMÜ: Başlangıçta pasif
        
        self.cid_click = self.canvas.mpl_connect('button_press_event', self.on_click)
        self.cid_key = self.canvas.mpl_connect('key_press_event', self.on_key)

    def on_key(self, event):
        if event.key in ['d', 'D']: # Sadece D'ye basıldığında aktifleşir
            self.drawing_active = not self.drawing_active
            self.points = []
            self.line.set_data([], [])
            self.canvas.draw_idle()

    def on_click(self, event):
        if not self.drawing_active: return # Uykudaysa hiçbir şeye tepki verme
        if event.inaxes != self.ax: return
        
        if event.button == 1:
            self.points.append((event.xdata, event.ydata))
            self.line.set_data(*zip(*self.points))
            self.canvas.draw_idle()
        elif event.button == 3 and len(self.points) > 2: # Sağ tık ile bitir
            self.finalize_polygon()
            self.drawing_active = False # Çizim bittikten sonra otomatik uyku moduna geç

    def finalize_polygon(self):
        poly = mpatches.Polygon(self.points, closed=True, facecolor='yellow', edgecolor='black', alpha=0.5)
        self.ax.add_patch(poly)
        if self.radio:
            label = self.radio.value_selected
            stil = next((s for s in LEJANTLAR if s["kod"] == label), None)
            if stil:
                poly.set_facecolor(stil["zemin"])
                GeoEngineDraw.draw_pattern(self.ax, poly, stil["desen"], stil["sembol"], density_scale=6.0)
        
        self.master_list.append(poly)
        self.points = []
        self.line.set_data([], [])
        self.canvas.draw_idle()
