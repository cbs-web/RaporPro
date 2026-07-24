# Dosya: RaporPro/kesit_topografya_editor.py
from kesit_topografya import (
    TopografyaProfilDuzenleyiciModel,
    topografya_profili_ornekle,
)


class TopografyaProfilEditor:
    """Matplotlib kesit önizlemesinde topoğrafya noktalarını düzenler."""

    def __init__(self, fig, ax, profile_info, on_change=None, on_status=None):
        self.fig = fig
        self.ax = ax
        self.on_change = on_change
        self.on_status = on_status
        self.active = False
        self.drag_index = None
        self._event_ids = []
        profile_info = dict(profile_info or {})
        self.model = TopografyaProfilDuzenleyiciModel(
            profile_info.get("points") or [],
            borehole_points=profile_info.get("borehole_points") or [],
            station_scale=profile_info.get("station_scale", 1.0),
        )
        self.surface_line = self._find_surface_line()
        if self.surface_line is None:
            self.surface_line, = ax.plot(
                [],
                [],
                color="#202020",
                linestyle="-",
                linewidth=1.8,
                zorder=30,
            )
            self.surface_line._geo_live_group = "topography"
        self.editable_markers, = ax.plot(
            [],
            [],
            linestyle="none",
            marker="s",
            markersize=6,
            markerfacecolor="#F39C12",
            markeredgecolor="#7E5109",
            zorder=80,
            visible=False,
        )
        self.locked_markers, = ax.plot(
            [],
            [],
            linestyle="none",
            marker="o",
            markersize=6,
            markerfacecolor="#2471A3",
            markeredgecolor="white",
            markeredgewidth=0.8,
            zorder=81,
            visible=False,
        )
        self.editable_markers._geo_export_group = "topography_editor"
        self.locked_markers._geo_export_group = "topography_editor"
        self._connect()
        self._refresh()

    @property
    def dirty(self):
        return bool(self.model.changed)

    def _find_surface_line(self):
        for line in self.ax.lines:
            if getattr(line, "_geo_live_group", None) == "topography":
                return line
        return None

    def _connect(self):
        canvas = self.fig.canvas
        self._event_ids = [
            canvas.mpl_connect("button_press_event", self._on_press),
            canvas.mpl_connect("motion_notify_event", self._on_motion),
            canvas.mpl_connect("button_release_event", self._on_release),
        ]

    def disconnect(self):
        canvas = self.fig.canvas
        for event_id in self._event_ids:
            try:
                canvas.mpl_disconnect(event_id)
            except Exception:
                pass
        self._event_ids = []

    def set_active(self, active):
        self.active = bool(active)
        self.editable_markers.set_visible(self.active)
        self.locked_markers.set_visible(self.active)
        self._refresh()
        self._status(
            "Topoğrafya düzenleme açık: çift tıkla ekle, sürükle, sağ tıkla sil."
            if self.active
            else "Topoğrafya düzenleme kapatıldı."
        )
        return self.active

    def toggle(self):
        return self.set_active(not self.active)

    def reset_to_boreholes(self):
        self.model.reset_to_boreholes()
        self._refresh()
        self._changed()

    def manual_points(self):
        return self.model.manual_points()

    def _status(self, message):
        if callable(self.on_status):
            self.on_status(message)

    def _changed(self):
        if callable(self.on_change):
            self.on_change(self.manual_points())

    def _refresh(self):
        x_values, y_values = topografya_profili_ornekle(self.model.points)
        self.surface_line.set_data(x_values, y_values)
        editable_x, editable_y = [], []
        locked_x, locked_y = [], []
        for index, point in enumerate(self.model.points):
            target_x, target_y = (
                (locked_x, locked_y)
                if self.model.is_locked_index(index)
                else (editable_x, editable_y)
            )
            target_x.append(point["station"])
            target_y.append(point["elevation"])
        self.editable_markers.set_data(editable_x, editable_y)
        self.locked_markers.set_data(locked_x, locked_y)
        try:
            self.fig.canvas.draw_idle()
        except Exception:
            pass

    def _nearest_index(self, event, pixel_limit=12.0):
        if event.inaxes is not self.ax or event.x is None or event.y is None:
            return None
        nearest = None
        nearest_distance = None
        for index, point in enumerate(self.model.points):
            px, py = self.ax.transData.transform((point["station"], point["elevation"]))
            distance = ((px - event.x) ** 2 + (py - event.y) ** 2) ** 0.5
            if nearest_distance is None or distance < nearest_distance:
                nearest = index
                nearest_distance = distance
        return nearest if nearest_distance is not None and nearest_distance <= pixel_limit else None

    def _on_press(self, event):
        if not self.active or event.inaxes is not self.ax:
            return
        nearest = self._nearest_index(event)
        if event.button == 3:
            if nearest is None:
                return
            if self.model.delete_point(nearest):
                self._refresh()
                self._changed()
                self._status("Topoğrafya noktası silindi; uygulamak için yeniden çizin.")
            else:
                self._status("Sondaj ağız kotu referans noktası silinemez.")
            return
        if event.button != 1:
            return
        if getattr(event, "dblclick", False) and nearest is None:
            if self.model.add_point(event.xdata, event.ydata):
                self._refresh()
                self._changed()
                self._status("Topoğrafya noktası eklendi; uygulamak için yeniden çizin.")
            return
        if nearest is not None and not self.model.is_locked_index(nearest):
            self.drag_index = nearest
        elif nearest is not None:
            self._status("Mavi sondaj kotu noktaları kilitlidir.")

    def _on_motion(self, event):
        if (
            not self.active
            or self.drag_index is None
            or event.inaxes is not self.ax
            or event.xdata is None
            or event.ydata is None
        ):
            return
        if self.model.move_point(self.drag_index, event.xdata, event.ydata):
            new_station = self.model.points[self.drag_index]["station"]
            self.drag_index = min(
                range(len(self.model.points)),
                key=lambda idx: abs(self.model.points[idx]["station"] - new_station),
            )
            self._refresh()

    def _on_release(self, event):
        if self.drag_index is None:
            return
        self.drag_index = None
        self._changed()
        self._status("Topoğrafya noktası taşındı; uygulamak için yeniden çizin.")
