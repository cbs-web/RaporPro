# Dosya: RaporPro/cizim.py
import tkinter as tk
from tkinter import Toplevel, Canvas, ttk, Scrollbar, messagebox
import numpy as np
import matplotlib.patches as mpatches
from matplotlib.legend_handler import HandlerPatch

from yardimcilar import safe_float, litoloji_cozumle, litoloji_yazim_uyarilari
from sabitler import LEJANTLAR, COLOR_BG, COLOR_ACCENT, COLOR_SUCCESS, FONT_BOLD, FONT_MAIN

class GeoEngineDraw:
    """Cizim yardimci fonksiyonlari"""
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
                poly_data.append((poly, code, kind, xy))

        drawn = set()
        for i, (poly_a, code_a, kind_a, xy_a) in enumerate(poly_data):
            for poly_b, code_b, kind_b, xy_b in poly_data[i + 1:]:
                if code_a != code_b:
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
                        key = (code_a, key_pts[0], key_pts[1])
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
        STEP_X_DOT = 0.025 * density_scale; STEP_Y_DOT = 0.025 * density_scale
        STEP_X_GRAVEL = 0.05 * density_scale; STEP_Y_GRAVEL = 0.05 * density_scale
        STEP_Y_LINE = 0.03 * density_scale

        if style_code == "nokta":
            xs = np.arange(x_min, x_max, STEP_X_DOT); ys = np.arange(y_min, y_max, STEP_Y_DOT)
            gx, gy = np.meshgrid(xs, ys)
            dots, = ax.plot(gx.flatten(), gy.flatten(), '.', color=color, markersize=1.2, zorder=z_pattern); dots.set_clip_path(clip); artists.append(dots)
        elif style_code == "cakil_daire":
            xs = np.arange(x_min, x_max + STEP_X_GRAVEL/2, STEP_X_GRAVEL); ys = np.arange(y_min, y_max + STEP_Y_GRAVEL/2, STEP_Y_GRAVEL)
            gx, gy = np.meshgrid(xs, ys)
            dots, = ax.plot(gx.flatten(), gy.flatten(), 'o', color=color, markersize=3.0, fillstyle='none', markeredgewidth=0.5, zorder=z_pattern); dots.set_clip_path(clip); artists.append(dots)
        elif style_code == "moloz_parca":
            step_x = max(0.012, 0.045 * density_scale)
            step_y = max(0.012, 0.040 * density_scale)
            base_size = max(0.004, min(step_x, step_y) * 0.34)
            xs = np.arange(x_min + step_x * 0.35, x_max, step_x)
            ys = np.arange(y_min + step_y * 0.35, y_max, step_y)
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
                    piece = mpatches.Polygon(pts, closed=True, facecolor='none', edgecolor=color, linewidth=0.55, zorder=z_pattern)
                    piece.set_clip_path(clip)
                    ax.add_patch(piece)
                    artists.append(piece)
        elif style_code == "kesikli":
            for yl in np.arange(y_min, y_max, STEP_Y_LINE):
                line, = ax.plot([x_min, x_max], [yl, yl], color=color, lw=0.8, zorder=z_pattern); line.set_dashes([3, 2]); line.set_clip_path(clip); artists.append(line)
        elif style_code == "noktali_kesikli":
            for yl in np.arange(y_min, y_max, STEP_Y_LINE):
                line, = ax.plot([x_min, x_max], [yl, yl], color=color, lw=0.8, zorder=z_pattern); line.set_dashes([3, 2, 1, 2]); line.set_clip_path(clip); artists.append(line)
        elif style_code == "ot":
            area_factor = 200 / (density_scale**2); num = int((x_max-x_min)*(y_max-y_min)*area_factor)
            if num > 0:
                rx = np.random.uniform(x_min, x_max, num); ry = np.random.uniform(y_min, y_max, num)
                for i in range(len(rx)):
                    line, = ax.plot([rx[i], rx[i]+0.01*density_scale, rx[i]+0.02*density_scale], [ry[i]+0.015*density_scale, ry[i], ry[i]+0.015*density_scale], color=color, lw=0.5, zorder=z_pattern); line.set_clip_path(clip); artists.append(line)
        elif style_code == "kumtasi_yatay":
            for yl in np.arange(y_min, y_max, STEP_Y_LINE):
                line, = ax.plot([x_min, x_max], [yl, yl], color=color, lw=0.5, alpha=0.7, zorder=z_pattern); line.set_clip_path(clip); artists.append(line)
            xs = np.arange(x_min, x_max, STEP_X_DOT*1.5); ys = np.arange(y_min, y_max, STEP_Y_DOT*1.5)
            gx, gy = np.meshgrid(xs, ys)
            dots, = ax.plot(gx.flatten(), gy.flatten(), '.', color=color, markersize=1, zorder=z_pattern); dots.set_clip_path(clip); artists.append(dots)
        elif style_code == "cakil_oval_cizgili":
            for yl in np.arange(y_min, y_max, STEP_Y_LINE*2):
                line, = ax.plot([x_min, x_max], [yl, yl], color=color, lw=0.5, zorder=z_pattern); line.set_dashes([6, 2]); line.set_clip_path(clip); artists.append(line)

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
            style.configure("LitolojiNormal.TEntry", fieldbackground="white")
            style.configure("LitolojiWarning.TEntry", fieldbackground="#FCF3CF")
        
        self.c = Canvas(self, bg=COLOR_BG)
        self.f = ttk.Frame(self.c)
        self.s = ttk.Scrollbar(self, orient="vertical", command=self.c.yview)
        
        self.c.configure(yscrollcommand=self.s.set)
        self.s.pack(side="right", fill="y")
        self.c.pack(side="left", fill="both", expand=True)
        self.c.create_window((0, 0), window=self.f, anchor="nw")
        
        self.f.bind("<Configure>", lambda e: self.c.configure(scrollregion=self.c.bbox("all")))
        
        for i, col in enumerate(kolonlar):
            ttk.Label(self.f, text=col, font=FONT_BOLD, relief="flat", background="#dfe6e9", anchor="center", padding=5).grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
        
        if self.veri: 
            for v in self.veri: self.satir_ekle(v)
        
        if not self.satirlar: self.satir_ekle()
        
        btn_f = ttk.Frame(self, padding=10)
        btn_f.pack(fill="x", side="bottom")
        
        tk.Button(btn_f, text="+ Satır Ekle", command=lambda: self.satir_ekle(), bg=COLOR_ACCENT, fg="white", font=FONT_BOLD).pack(side="left", padx=10)
        ttk.Label(btn_f, textvariable=self.litoloji_uyari_var, foreground="#B7950B").pack(side="left", padx=8)
        tk.Button(btn_f, text="💾 KAYDET VE KAPAT", bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD, command=self.kaydet).pack(side="right", padx=10)
        self.litoloji_yazim_kontrol()

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
