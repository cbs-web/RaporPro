# Dosya: RaporPro/resim_georef.py
from tkinter import messagebox

from harita_referans import affine_from_refs, coord_to_pixel, valid_latlon


class ResimGeorefMixin:
    def kml_ref_secildi(self, event=None):
        self.active_ref_index = self.cmb_ref_point.current() if hasattr(self, "cmb_ref_point") else None
        if hasattr(self, "lbl_kml_ref"):
            if self.active_ref_index is not None and 0 <= self.active_ref_index < len(self.kml_points):
                point = self.kml_points[self.active_ref_index]
                self.lbl_kml_ref.config(text=f"Seçili köşe: {self.active_ref_index + 1}  ({float(point.get('lat')):.6f}, {float(point.get('lon')):.6f})")
            else:
                self.lbl_kml_ref.config(text="KML köşe noktası seçilemedi.")
        self.kml_preview_ciz()

    def kml_preview_ciz(self):
        if not hasattr(self, "kml_ax"):
            return
        self.kml_ax.clear()
        self.kml_ax.set_xticks([])
        self.kml_ax.set_yticks([])
        self.kml_ax.set_facecolor("#F8F9FA")
        for spine in self.kml_ax.spines.values():
            spine.set_edgecolor("#BFC9CA")
            spine.set_linewidth(0.8)

        if not self.kml_preview_points:
            self.kml_ax.text(0.5, 0.5, "KML yok", ha="center", va="center", fontsize=9, transform=self.kml_ax.transAxes)
            if hasattr(self, "lbl_kml_ref"):
                self.lbl_kml_ref.config(text="KML sınırı bulunamadı.")
            self.kml_fig.tight_layout(pad=0.15)
            self.kml_preview_canvas.draw_idle()
            return

        lons = [float(p["lon"]) for p in self.kml_preview_points]
        lats = [float(p["lat"]) for p in self.kml_preview_points]
        closed_lons = lons + ([lons[0]] if len(lons) > 2 else [])
        closed_lats = lats + ([lats[0]] if len(lats) > 2 else [])
        self.kml_ax.plot(closed_lons, closed_lats, color="#566573", linewidth=1.2, zorder=1)
        self.kml_ax.scatter(lons, lats, s=26, c="#2471A3", edgecolors="white", linewidths=0.7, zorder=3)

        selected = self.cmb_ref_point.current() if hasattr(self, "cmb_ref_point") else -1
        if 0 <= selected < len(self.kml_preview_points):
            self.kml_ax.scatter(
                [lons[selected]],
                [lats[selected]],
                s=86,
                c="#F1C40F",
                edgecolors="#7D6608",
                linewidths=1.3,
                zorder=5,
            )

        label_limit = 80
        for idx, (lon, lat) in enumerate(zip(lons, lats)):
            if len(lons) <= label_limit or idx == selected:
                self.kml_ax.text(
                    lon,
                    lat,
                    str(idx + 1),
                    color="#1B2631",
                    fontsize=6 if len(lons) <= 50 else 5,
                    ha="center",
                    va="center",
                    zorder=6,
                )

        lon_span = max(lons) - min(lons)
        lat_span = max(lats) - min(lats)
        lon_pad = lon_span * 0.08 or 0.0001
        lat_pad = lat_span * 0.08 or 0.0001
        self.kml_ax.set_xlim(min(lons) - lon_pad, max(lons) + lon_pad)
        self.kml_ax.set_ylim(min(lats) - lat_pad, max(lats) + lat_pad)
        self.kml_ax.set_aspect("equal", adjustable="box")
        self.kml_ax.set_title("KML sınırı - köşeye tıklayın", fontsize=8, pad=2)
        if hasattr(self, "lbl_kml_ref") and 0 <= selected < len(self.kml_preview_points):
            point = self.kml_preview_points[selected]
            self.lbl_kml_ref.config(text=f"Seçili köşe: {selected + 1}  ({float(point.get('lat')):.6f}, {float(point.get('lon')):.6f})")
        self.kml_fig.tight_layout(pad=0.15)
        self.kml_preview_canvas.draw_idle()

    def on_kml_preview_click(self, event):
        if event.inaxes != getattr(self, "kml_ax", None) or event.xdata is None or event.ydata is None:
            return
        idx = self._nearest_kml_preview_index(event.xdata, event.ydata)
        if idx is None:
            return
        self.cmb_ref_point.current(idx)
        self.kml_ref_secildi()
        self.georef_ref_modu()

    def _nearest_kml_preview_index(self, lon, lat):
        if not self.kml_preview_points:
            return None
        lons = [float(p["lon"]) for p in self.kml_preview_points]
        lats = [float(p["lat"]) for p in self.kml_preview_points]
        lon_span = max(lons) - min(lons) or 1.0
        lat_span = max(lats) - min(lats) or 1.0
        best_idx = None
        best_dist = None
        for idx, point in enumerate(self.kml_preview_points):
            dist = ((float(point["lon"]) - lon) / lon_span) ** 2 + ((float(point["lat"]) - lat) / lat_span) ** 2
            if best_dist is None or dist < best_dist:
                best_idx = idx
                best_dist = dist
        return best_idx

    def georef_count_guncelle(self):
        if hasattr(self, "lbl_ref_count"):
            self.lbl_ref_count.config(text=f"Referans: {len(self.georef_refs)} / en az 3")

    def georef_ref_modu(self):
        if not self.kml_points:
            messagebox.showwarning("Koordinatlı Yerleştirme", "KML noktası bulunamadı. Önce KML sınır seçin.")
            return
        idx = self.cmb_ref_point.current() if hasattr(self, "cmb_ref_point") else -1
        if idx < 0 or idx >= len(self.kml_points):
            messagebox.showwarning("Koordinatlı Yerleştirme", "Referans alınacak KML noktasını seçin.")
            return
        self.active_mod = "georef"
        self.active_id = None
        self.active_ref_index = idx
        point = self.kml_points[idx]
        self.lbl_talimat.config(text=f"{point.get('label', f'KML-{idx + 1}')} noktasının resimdeki karşılığını tıklayın.")

    def georef_refs_temizle(self):
        self.georef_refs = []
        self.georef_refleri_ciz()
        self.georef_count_guncelle()
        self.lbl_talimat.config(text="Referanslar temizlendi. En az 3 KML noktası için resimde karşılık tıklayın.")
        self.canvas.draw_idle()

    def georef_refleri_ciz(self):
        for artist in self.georef_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self.georef_artists = []
        if not hasattr(self, "ax"):
            return
        for idx, ref in enumerate(self.georef_refs, start=1):
            pixel = ref.get("pixel", {})
            try:
                x, y = float(pixel["x"]), float(pixel["y"])
            except Exception:
                continue
            marker, = self.ax.plot(x, y, marker="x", color="#F1C40F", markersize=9, markeredgewidth=2.0, zorder=20)
            text = self.ax.text(
                x + 8,
                y + 8,
                f"REF-{idx}",
                color="#7D6608",
                fontsize=8,
                fontweight="bold",
                bbox=dict(facecolor="white", alpha=0.78, edgecolor="#F1C40F", pad=2),
                zorder=20,
            )
            self.georef_artists.extend([marker, text])
        self.kml_layer_ciz()

    def kml_pixel_noktalari(self):
        if len(getattr(self, "georef_refs", [])) < 3:
            return []
        try:
            coeff = affine_from_refs(self.georef_refs)
        except Exception:
            return []
        points = []
        for point in getattr(self, "kml_points", []):
            if not valid_latlon(point.get("lat"), point.get("lon")):
                continue
            try:
                x, y = coord_to_pixel(
                    coeff,
                    float(point["lat"]),
                    float(point["lon"]),
                )
            except (TypeError, ValueError):
                continue
            points.append((x, y))
        if len(points) > 2 and points[0] != points[-1]:
            points.append(points[0])
        return points

    def kml_layer_ciz(self):
        for artist in getattr(self, "kml_layer_artists", []):
            try:
                artist.remove()
            except Exception:
                pass
        self.kml_layer_artists = []
        if not hasattr(self, "ax"):
            return
        points = self.kml_pixel_noktalari()
        if len(points) < 2:
            return
        line, = self.ax.plot(
            [point[0] for point in points],
            [point[1] for point in points],
            color="#148F77",
            linewidth=1.8,
            linestyle="-",
            alpha=0.95,
            zorder=14,
        )
        self.kml_layer_artists = [line]
        self.set_kml_layer_visibility(
            bool(self.show_kml_var.get()) if hasattr(self, "show_kml_var") else True
        )

    def set_kml_layer_visibility(self, visible):
        for artist in getattr(self, "kml_layer_artists", []):
            try:
                artist.set_visible(visible)
            except Exception:
                pass

    def harita_kml_export_ciz(self, ax_map):
        points = self.kml_pixel_noktalari()
        if len(points) < 2:
            return
        ax_map.plot(
            [point[0] for point in points],
            [point[1] for point in points],
            color="#148F77",
            linewidth=1.6,
            linestyle="-",
            alpha=0.95,
            zorder=14,
        )

    def set_georef_visibility(self, visible):
        for artist in self.georef_artists:
            try:
                artist.set_visible(visible)
            except Exception:
                pass

    def georef_ref_ekle(self, x, y):
        idx = self.active_ref_index
        if idx is None or idx < 0 or idx >= len(self.kml_points):
            return
        point = self.kml_points[idx]
        label = point.get("label") or f"KML-{idx + 1}"
        yeni_ref = {
            "label": label,
            "coord": {"lat": point.get("lat"), "lon": point.get("lon")},
            "pixel": {"x": float(x), "y": float(y)},
        }
        self.georef_refs = [ref for ref in self.georef_refs if ref.get("label") != label]
        self.georef_refs.append(yeni_ref)
        self.active_mod = None
        self.active_ref_index = None
        self.georef_refleri_ciz()
        self.georef_count_guncelle()
        self.lbl_talimat.config(text=f"{label} referansı eklendi. En az 3 referans sonrası otomatik yerleştirebilirsiniz.")
        self.canvas.draw_idle()

    def _as_float_pair(self, lat, lon):
        if not valid_latlon(lat, lon):
            return None
        return float(lat), float(lon)
