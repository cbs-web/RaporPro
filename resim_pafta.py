# Dosya: RaporPro/resim_pafta.py
from tkinter import filedialog, messagebox
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.image as mpimg

from sabitler import DEFAULT_EXPORT_DPI, HARITA_PAFTA_LAYOUT


class ResimPaftaMixin:
    def pafta_basligi(self):
        return "ARAŞTIRMA NOKTALARI VAZİYET PLANI" if self.harita_tipi == "vaziyet" else "MÜHENDİSLİK JEOLOJİSİ HARİTASI"

    def pafta_panel_hazirla(self, ax):
        layout = HARITA_PAFTA_LAYOUT
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor('black')
            spine.set_linewidth(layout["border_width"])

    def pafta_harita_ciz(self, ax_map, respect_visibility=True):
        layout = HARITA_PAFTA_LAYOUT
        ax_map.imshow(mpimg.imread(self.img_path))
        self.pafta_panel_hazirla(ax_map)
        ax_map.set_title(
            self.pafta_basligi(),
            fontsize=layout["title_fontsize"],
            fontweight='bold',
            pad=layout["title_pad"],
        )

        if self.export_mod_gorunur("sondaj", respect_visibility):
            for item_id, (x, y) in self.coords_memory["sondaj"].items():
                ax_map.plot(x, y, 'bo', markersize=8, markeredgecolor='black')
        if self.export_mod_gorunur("ss", respect_visibility):
            for item_id, coords in self.coords_memory["ss"].items():
                ax_map.plot([coords[0][0], coords[1][0]], [coords[0][1], coords[1][1]], 'r--', linewidth=2)
                ax_map.plot(coords[0][0], coords[0][1], 'ro', markersize=4)
                ax_map.plot(coords[1][0], coords[1][1], 'ro', markersize=4)
        if self.export_mod_gorunur("mt", respect_visibility):
            for item_id, (x, y) in self.coords_memory["mt"].items():
                ax_map.plot(x, y, 'rs', markersize=8, markeredgecolor='black')

        for mod, items in self.drawn_objects.items():
            if not self.export_mod_gorunur(mod, respect_visibility):
                continue
            for item_id, elements in items.items():
                for t in elements.get("texts", []):
                    x, y = t.get_position()
                    bbox_props = dict(facecolor='white', alpha=0.8, edgecolor='black', boxstyle='round,pad=0.3') if mod == "formasyon" else None
                    ax_map.text(x, y, t.get_text(), color=t.get_color(), fontsize=t.get_fontsize(), fontweight=t.get_fontweight(), ha=t.get_ha(), va=t.get_va(), bbox=bbox_props)

        if self.kuzey_oku_var.get():
            ax_map.annotate(
                'K',
                xy=(0.95, 0.95),
                xytext=(0.95, 0.85),
                arrowprops=dict(facecolor='black', width=4, headwidth=12),
                ha='center',
                va='center',
                fontsize=layout["title_fontsize"],
                fontweight='bold',
                xycoords='axes fraction',
                textcoords='axes fraction',
            )
        self.export_olcek_ciz(ax_map)

    def pafta_koordinat_satirlari(self, respect_visibility=True):
        coord_lines = []
        if self.export_mod_gorunur("sondaj", respect_visibility):
            for s in self.map_data.get("sondaj", []):
                coord_lines.append(f"{s['no']:<6} Enlem: {s['y']:<10} Boylam: {s['x']}")
        if self.export_mod_gorunur("mt", respect_visibility):
            for m in self.map_data.get("mt", []):
                coord_lines.append(f"{m['no']:<6} Enlem: {m['y']:<10} Boylam: {m['x']}")
        if self.export_mod_gorunur("ss", respect_visibility):
            for ss in self.map_data.get("ss", []):
                c = ss["coords"]
                if len(c) >= 2:
                    coord_lines.append(f"{ss['ad']:<6} Enlem: {c[0]:<10} Boylam: {c[1]}")
        return coord_lines

    def pafta_koordinat_kutusu_ciz(self, ax_coord, respect_visibility=True):
        layout = HARITA_PAFTA_LAYOUT
        self.pafta_panel_hazirla(ax_coord)
        ax_coord.text(
            0.04,
            0.94,
            "KOORDİNAT BİLGİLERİ (WGS84)",
            fontweight='bold',
            fontsize=layout["panel_title_fontsize"],
            transform=ax_coord.transAxes,
            va='top',
        )
        coord_lines = self.pafta_koordinat_satirlari(respect_visibility)
        coord_text = "\n".join(coord_lines) if coord_lines else "Seçilmiş koordinat bulunmamaktadır."
        ax_coord.text(
            0.04,
            0.85,
            coord_text,
            fontsize=layout["coord_fontsize"],
            family='monospace',
            va='top',
            ha='left',
            transform=ax_coord.transAxes,
        )

    def pafta_lejant_ogeleri(self, respect_visibility=True):
        legend_items = []
        if self.export_mod_gorunur("sondaj", respect_visibility):
            legend_items.append(("sondaj", "Sondaj Noktası (SK)"))
        if self.export_mod_gorunur("ss", respect_visibility):
            legend_items.append(("ss", "Sismik Serim (SS)"))
        if self.export_mod_gorunur("mt", respect_visibility):
            legend_items.append(("mt", "Mikrotremör Noktası (MT)"))
        if self.harita_tipi == "jeoloji" and self.formasyon:
            legend_items.append(("formasyon", self.get_formasyon_adi()))
        return legend_items

    def pafta_lejant_ciz(self, ax_leg, respect_visibility=True):
        layout = HARITA_PAFTA_LAYOUT
        self.pafta_panel_hazirla(ax_leg)
        ax_leg.text(
            0.04,
            0.94,
            "AÇIKLAMALAR (LEJANT)",
            fontweight='bold',
            fontsize=layout["panel_title_fontsize"],
            transform=ax_leg.transAxes,
            va='top',
        )

        legend_items = self.pafta_lejant_ogeleri(respect_visibility)
        y_pos = 0.80
        step = 0.18 if len(legend_items) <= 3 else 0.15
        for kind, desc in legend_items:
            rect = patches.Rectangle((0.05, y_pos - 0.05), 0.15, 0.10, fill=True, facecolor='white', edgecolor='black', transform=ax_leg.transAxes)
            ax_leg.add_patch(rect)
            if kind == "sondaj":
                ax_leg.plot(0.125, y_pos, 'bo', markersize=8, markeredgecolor='black', transform=ax_leg.transAxes)
            elif kind == "ss":
                ax_leg.plot([0.07, 0.18], [y_pos, y_pos], 'r--', linewidth=2, transform=ax_leg.transAxes)
            elif kind == "mt":
                ax_leg.plot(0.125, y_pos, 'rs', markersize=8, markeredgecolor='black', transform=ax_leg.transAxes)
            elif kind == "formasyon":
                ax_leg.text(
                    0.125,
                    y_pos,
                    self.formasyon,
                    fontsize=layout["legend_symbol_fontsize"],
                    fontweight='bold',
                    ha='center',
                    va='center',
                    transform=ax_leg.transAxes,
                )
            ax_leg.text(
                0.25,
                y_pos,
                f"-  {desc}",
                fontsize=layout["legend_fontsize"],
                color='black',
                transform=ax_leg.transAxes,
                ha='left',
                va='center',
            )
            y_pos -= step

    def save_a4_pafta(self, path, respect_visibility=True):
        layout = HARITA_PAFTA_LAYOUT
        fig_exp = plt.figure(figsize=layout["figure_size"])
        fig_exp.patch.set_facecolor('white')
        try:
            ax_map = fig_exp.add_axes(layout["map_axes"])
            self.pafta_harita_ciz(ax_map, respect_visibility=respect_visibility)

            ax_coord = fig_exp.add_axes(layout["coord_axes"])
            self.pafta_koordinat_kutusu_ciz(ax_coord, respect_visibility=respect_visibility)

            ax_leg = fig_exp.add_axes(layout["legend_axes"])
            self.pafta_lejant_ciz(ax_leg, respect_visibility=respect_visibility)

            fig_exp.savefig(path, dpi=DEFAULT_EXPORT_DPI, bbox_inches='tight')
        finally:
            plt.close(fig_exp)

    def export_image(self):
        self.trigger_save_state()
        path = filedialog.asksaveasfilename(defaultextension=".jpg", initialfile=f"{self.harita_tipi}_paftasi.jpg", filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")])
        if not path: return
        try:
            self.save_a4_pafta(path, respect_visibility=True)
            messagebox.showinfo("Başarılı", f"A4 Dikey Pafta başarıyla kaydedildi:\n{path}")
        except Exception as e: messagebox.showerror("Hata", f"Pafta kaydedilemedi:\n{e}")
