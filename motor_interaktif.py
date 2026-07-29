# Dosya: RaporPro/motor_interaktif.py
import math

from cizim import GeoEngineDraw
from performans import log_exception


# --- İNTERAKTİF MOTOR (SEÇİM, KÖŞE GÖSTERME VE CTRL+TIK KÖŞE EKLEME) ---
class GeoInteractiveTool:
    def __init__(self, fig, ax, snap_x_list, polygons):
        self.fig = fig
        self.ax = ax
        self.snap_x_list = snap_x_list
        self.polygons = polygons
        self.snap_tol = 1.5

        self.edit_mode = False
        self.selected_poly = None # Seçilen poligon hafızası
        self.dragging = False
        self.drag_poly = None
        self.drag_idx = None
        self.drag_before_xy = None
        self.undo_stack = []
        self.redo_stack = []
        self.max_history = 80
        self.history_callback = None

        # Seçilen poligonun köşelerinde çıkacak sarı-kırmızı işaretçiler
        self.vertex_markers, = self.ax.plot([], [], 'o', markerfacecolor='yellow', markeredgecolor='red', markersize=6, zorder=200)

        self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)

        self.info_text = self.ax.text(
            0.99, 0.99, "",
            transform=self.ax.transAxes, ha='right', va='top',
            fontsize=9, color='gray', fontweight='bold', zorder=200,
            bbox=dict(facecolor='white', edgecolor='none', alpha=0.82, pad=0.35)
        )
        self.update_info_text()

    def selected_poly_label(self):
        if self.selected_poly is None:
            return ""
        code = str(getattr(self.selected_poly, "_geo_unit_code", "") or "").strip().upper()
        edit_id = str(getattr(self.selected_poly, "_geo_edit_id", "") or "")
        if code:
            return f"{code} seçili"
        if edit_id:
            return "Polygon seçili"
        return "Seçili polygon"

    def update_info_text(self):
        if self.info_text is None:
            return
        if not self.edit_mode:
            self.info_text.set_text("İZLEME MODU | E: düzenle")
            self.info_text.set_color('gray')
            return
        label = self.selected_poly_label()
        if label:
            self.info_text.set_text(f"DÜZENLEME | {label} | Köşe sürükle | Ctrl+tıkla: köşe ekle")
        else:
            self.info_text.set_text("DÜZENLEME | Polygon seçmek için tıkla")
        self.info_text.set_color('red')

    def set_edit_mode(self, value):
        self.edit_mode = bool(value)
        if not self.edit_mode:
            self.selected_poly = None
            self.dragging = False
            self.drag_poly = None
            self.drag_idx = None
            self.drag_before_xy = None
        self.update_info_text()
        self.draw_markers()

    def select_polygon(self, poly):
        self.selected_poly = poly
        if poly is not None:
            self.edit_mode = True
        self.update_info_text()
        self.draw_markers()

    def refresh_pattern(self, poly):
        try:
            artists = GeoEngineDraw.refresh_pattern(self.ax, poly)
            zorder = getattr(poly, "_geo_pattern_zorder", None)
            visible = poly.get_visible() if hasattr(poly, "get_visible") else True
            for artist in artists or []:
                if zorder is not None:
                    try:
                        artist.set_zorder(zorder)
                    except Exception as exc:
                        log_exception("motor.refresh_pattern.zorder", exc_value=exc)
                try:
                    artist.set_visible(visible)
                except Exception as exc:
                    log_exception("motor.refresh_pattern.visible", exc_value=exc)
        except Exception as exc:
            log_exception("motor.refresh_pattern", exc_value=exc)

    def refresh_same_unit_seams(self):
        if not getattr(self.fig, "_geo_hide_same_unit_seams", True):
            return
        try:
            GeoEngineDraw.hide_same_unit_seams(self.ax, self.polygons)
        except Exception as exc:
            log_exception("motor.refresh_same_unit_seams", exc_value=exc)

    def poly_xy(self, poly):
        try:
            return [[float(x), float(y)] for x, y in poly.get_xy()]
        except Exception:
            return []

    def same_xy(self, first, second):
        if len(first or []) != len(second or []):
            return False
        return all(
            round(a[0], 5) == round(b[0], 5) and round(a[1], 5) == round(b[1], 5)
            for a, b in zip(first, second)
        )

    def set_history_callback(self, callback):
        self.history_callback = callback
        self.notify_history()

    def notify_history(self):
        if self.history_callback:
            try:
                self.history_callback(self)
            except Exception:
                pass

    def record_history(self, poly, before_xy, after_xy=None):
        if poly is None or not before_xy:
            return
        after_xy = after_xy or self.poly_xy(poly)
        if not after_xy or self.same_xy(before_xy, after_xy):
            return
        self.undo_stack.append({"poly": poly, "before": before_xy, "after": after_xy})
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.notify_history()

    def restore_poly_xy(self, poly, xy, notify=True):
        if poly is None or not xy:
            return
        poly.set_xy(xy)
        self.refresh_pattern(poly)
        self.refresh_same_unit_seams()
        if self.selected_poly is poly:
            self.draw_markers()
        else:
            self.fig.canvas.draw_idle()
        if notify:
            self.notify_history()

    def undo(self):
        if not self.undo_stack:
            return False
        action = self.undo_stack.pop()
        self.restore_poly_xy(action["poly"], action["before"], notify=False)
        self.redo_stack.append(action)
        self.notify_history()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        action = self.redo_stack.pop()
        self.restore_poly_xy(action["poly"], action["after"], notify=False)
        self.undo_stack.append(action)
        self.notify_history()
        return True

    def history_counts(self):
        return len(self.undo_stack), len(self.redo_stack)

    def get_snap(self, x):
        if x is None:
            return None
        for sx in self.snap_x_list:
            if abs(x - sx) < self.snap_tol:
                return sx
        return x

    def draw_markers(self):
        """Seçili poligonun köşelerini görünür yapar"""
        if self.selected_poly and self.edit_mode:
            verts = self.selected_poly.get_xy()
            xs, ys = verts[:, 0], verts[:, 1]
            self.vertex_markers.set_data(xs, ys)
        else:
            self.vertex_markers.set_data([], [])
        self.fig.canvas.draw_idle()

    def on_key(self, event):
        if event.key in ['ctrl+z', 'control+z']:
            self.undo()
            return
        if event.key in ['ctrl+y', 'control+y', 'ctrl+shift+z', 'control+shift+z']:
            self.redo()
            return
        if event.key in ['e', 'E']:
            self.set_edit_mode(not self.edit_mode)

    def on_press(self, event):
        if not self.edit_mode or event.inaxes != self.ax or event.button != 1:
            return

        px, py = event.xdata, event.ydata

        # 1. CTRL+TIK MANTIĞI: Seçili poligona yeni köşe ekle
        key_is_ctrl = event.key in ['control', 'ctrl']
        if key_is_ctrl and self.selected_poly is not None:
            before_xy = self.poly_xy(self.selected_poly)
            verts = list(self.selected_poly.get_xy())

            # Tıklanan yere en yakın kenarı (çizgiyi) bul
            min_dist = float('inf')
            insert_idx = -1
            for i in range(len(verts) - 1):
                x1, y1 = verts[i]
                x2, y2 = verts[i + 1]

                # Noktanın doğru parçasına (kenara) olan dik uzaklık hesabı
                l2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
                if l2 == 0:
                    continue
                t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2))
                proj_x = x1 + t * (x2 - x1)
                proj_y = y1 + t * (y2 - y1)
                dist = math.hypot(px - proj_x, py - proj_y)

                if dist < min_dist:
                    min_dist = dist
                    insert_idx = i + 1 # Araya ekle

            if insert_idx != -1:
                verts.insert(insert_idx, [px, py])
                self.selected_poly.set_xy(verts)
                self.refresh_pattern(self.selected_poly)
                self.refresh_same_unit_seams()
                self.record_history(self.selected_poly, before_xy)
                self.draw_markers()
            return

        # 2. SÜRÜKLEME MANTIĞI: Zaten seçili bir poligonun köşesine mi tıkladı?
        if self.selected_poly is not None:
            verts = self.selected_poly.get_xy()
            min_dist = float('inf')
            for i, (vx, vy) in enumerate(verts[:-1]):
                dist = math.hypot(vx - px, vy - py)
                if dist < 2.0 and dist < min_dist: # 2.0 Birimlik yakalama toleransı
                    min_dist = dist
                    self.dragging = True
                    self.drag_poly = self.selected_poly
                    self.drag_idx = i
                    self.drag_before_xy = self.poly_xy(self.selected_poly)

            if self.dragging:
                return # Sürükleme başladıysa işlemi bitir

        # 3. SEÇİM MANTIĞI: Poligonun içine mi tıkladı?
        clicked_any = False
        # Üst üste binenlerde en üsttekini seçmek için listeyi tersten tarıyoruz
        for poly in reversed(self.polygons):
            contains, _ = poly.contains(event)
            if contains:
                self.select_polygon(poly)
                clicked_any = True
                break

        # Boşluğa tıkladıysa seçimi kaldır
        if not clicked_any:
            self.select_polygon(None)

    def on_motion(self, event):
        if not self.dragging or self.drag_poly is None or event.inaxes != self.ax:
            return
        new_x = self.get_snap(event.xdata)
        new_y = event.ydata

        verts = self.drag_poly.get_xy()
        verts[self.drag_idx] = [new_x, new_y]

        # Eğer ilk noktayı çekiştiriyorsa, kapalı poligon olduğu için son noktayı da eşitle
        if self.drag_idx == 0:
            verts[-1] = [new_x, new_y]

        self.drag_poly.set_xy(verts)
        self.refresh_pattern(self.drag_poly)
        self.refresh_same_unit_seams()
        self.draw_markers() # Sürüklerken kırmızı noktaları da anlık güncelle

    def on_release(self, event):
        if event.button == 1:
            if self.dragging and self.drag_poly is not None:
                self.record_history(self.drag_poly, self.drag_before_xy)
            self.dragging = False
            self.drag_poly = None
            self.drag_idx = None
            self.drag_before_xy = None
