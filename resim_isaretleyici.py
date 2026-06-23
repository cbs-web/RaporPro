# Dosya: RaporPro/resim_isaretleyici.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches
import matplotlib.image as mpimg
import math
import numpy as np
import os

from harita_cikti import yeni_harita_cikti_yolu
from harita_referans import affine_from_refs, coord_to_pixel, valid_latlon
from performans import log_exception
from sabitler import DEFAULT_EXPORT_DPI, HARITA_PAFTA_LAYOUT
from resim_pafta import ResimPaftaMixin
from resim_georef import ResimGeorefMixin


DISPLAY_IMAGE_MAX_DIM = 2400
IMAGE_PREVIEW_CACHE = {}
IMAGE_PREVIEW_CACHE_LIMIT = 3


class ResimIsaretleyici(ResimGeorefMixin, ResimPaftaMixin, tk.Toplevel):
    def __init__(self, master, img_path, map_data, harita_tipi="vaziyet", formasyon=None, kml_points=None, word_callback=None, save_callback=None, saved_state=None):
        super().__init__(master)
        
        baslik = "Araştırma Noktaları Vaziyet Planı Çizimi" if harita_tipi == "vaziyet" else "Mühendislik Jeolojisi Haritası Çizimi"
        self.title(f"Manuel Harita İşaretleyici (İnteraktif) - {baslik}")
        self.geometry("1400x850")
        
        self.img_path = img_path
        self.map_data = map_data
        self.harita_tipi = harita_tipi
        self.formasyon = formasyon
        self.kml_points = [p for p in (kml_points or []) if valid_latlon(p.get("lat"), p.get("lon"))]
        self.kml_preview_points = self.kml_points
        self.image_width = None
        self.image_height = None
        self.display_image_shape = None
        
        self.word_callback = word_callback
        self.save_callback = save_callback
        self.saved_state = saved_state
        
        self.active_id = None
        self.active_mod = None
        self.ss_start = None
        self.temp_ss_marker = None
        self.active_ref_index = None
        
        saved_visibility = (saved_state or {}).get("visibility", {}) if isinstance(saved_state, dict) else {}
        saved_scale = str((saved_state or {}).get("scale", "Yok") if isinstance(saved_state, dict) else "Yok")
        if saved_scale not in ("Yok", "1/500", "1/1000"):
            saved_scale = "Yok"
        self.kuzey_oku_var = tk.BooleanVar(value=True)
        self.olcek_var = tk.StringVar(value=saved_scale)
        self.show_sondaj_var = tk.BooleanVar(value=bool(saved_visibility.get("sondaj", True)))
        self.show_jeofizik_var = tk.BooleanVar(value=bool(saved_visibility.get("jeofizik", True)))
        self.olcek_artist = None
        
        self.drawn_objects = {"sondaj": {}, "ss": {}, "mt": {}, "formasyon": {}}
        self.coords_memory = {"sondaj": {}, "ss": {}, "mt": {}, "formasyon": {}}
        self.georef_refs = list((saved_state or {}).get("georef_refs", [])) if isinstance(saved_state, dict) else []
        self.georef_artists = []
        self.kml_preview_canvas = None
        
        self.dragging_text = None
        self.dragging_object = None
        self.drag_offset = (0, 0)
        
        self.setup_ui()
        self.plot_image()

    def setup_ui(self):
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5, bg="#ccc")
        paned.pack(fill="both", expand=True)

        self.map_frame = ttk.Frame(paned)
        paned.add(self.map_frame, width=1050)
        
        info_frame = tk.Frame(self.map_frame, bg="#2C3E50", height=40)
        info_frame.pack(fill="x")
        self.lbl_talimat = tk.Label(info_frame, text="Nokta seçip ekleyin. Yazıları SÜRÜKLEYEREK taşıyabilir, SAĞ TIKLAYARAK formatlayabilirsiniz.", fg="white", bg="#2C3E50", font=("Arial", 11, "bold"))
        self.lbl_talimat.pack(side="left", padx=15, pady=10)
        tk.Button(info_frame, text="A4 PAFTA", bg="#27AE60", fg="white", font=("Arial", 9, "bold"), command=self.export_image).pack(side="right", padx=8, pady=6)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, width=360, minsize=320)
        
        lbl_baslik = tk.Label(right_frame, text="İŞARETLENECEK NOKTALAR", bg="#34495E", fg="white", font=("Arial", 12, "bold"), pady=10)
        lbl_baslik.pack(fill="x")

        action_frame = ttk.Frame(right_frame, padding=(5, 4))
        action_frame.pack(side="bottom", fill="x")

        chk_kuzey = ttk.Checkbutton(action_frame, text="Çıktıya Kuzey Oku Ekle", variable=self.kuzey_oku_var)
        chk_kuzey.pack(fill="x", padx=5, pady=(0, 5))
        if self.harita_tipi == "jeoloji":
            scale_row = ttk.Frame(action_frame)
            scale_row.pack(fill="x", padx=5, pady=(0, 5))
            ttk.Label(scale_row, text="Ölçek", width=10).pack(side="left")
            scale_combo = ttk.Combobox(scale_row, textvariable=self.olcek_var, values=("Yok", "1/500", "1/1000"), state="readonly", width=12)
            scale_combo.pack(side="left", fill="x", expand=True)
            scale_combo.bind("<<ComboboxSelected>>", self.olcek_guncelle)

        btn_sil = tk.Button(action_frame, text="🗑️ Seçileni Temizle", bg="#E74C3C", fg="white", font=("Arial", 10, "bold"), command=self.secileni_sil)
        btn_sil.pack(fill="x", padx=5, pady=2)

        btn_save = tk.Button(action_frame, text="💾 ÇİZİMİ PROJEYE KAYDET", bg="#F39C12", fg="white", font=("Arial", 10, "bold"), pady=5, command=self.trigger_save_state)
        btn_save.pack(fill="x", padx=5, pady=2)

        btn_word = tk.Button(action_frame, text="📄 WORD İÇİN AYIR VE AKTAR", bg="#8E44AD", fg="white", font=("Arial", 11, "bold"), pady=9, command=self.export_for_word)
        btn_word.pack(fill="x", padx=5, pady=4)

        btn_kaydet = tk.Button(action_frame, text="🖨️ PAFTA ÇIKTISI AL (A4)", bg="#27AE60", fg="white", font=("Arial", 11, "bold"), pady=9, command=self.export_image)
        btn_kaydet.pack(fill="x", padx=5, pady=(4, 2))

        scroll_wrap = ttk.Frame(right_frame)
        scroll_wrap.pack(fill="both", expand=True)
        side_canvas = tk.Canvas(scroll_wrap, highlightthickness=0, borderwidth=0)
        side_scroll = ttk.Scrollbar(scroll_wrap, orient="vertical", command=side_canvas.yview)
        side_content = ttk.Frame(side_canvas)
        side_window = side_canvas.create_window((0, 0), window=side_content, anchor="nw")

        def update_scroll_region(event=None):
            side_canvas.configure(scrollregion=side_canvas.bbox("all"))

        def update_content_width(event):
            side_canvas.itemconfigure(side_window, width=event.width)

        def on_side_mousewheel(event):
            if event.delta:
                side_canvas.yview_scroll(-int(event.delta / 120), "units")

        side_content.bind("<Configure>", update_scroll_region)
        side_canvas.bind("<Configure>", update_content_width)
        side_canvas.bind("<Enter>", lambda event: side_canvas.bind_all("<MouseWheel>", on_side_mousewheel))
        side_canvas.bind("<Leave>", lambda event: side_canvas.unbind_all("<MouseWheel>"))
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side_canvas.pack(side="left", fill="both", expand=True)
        side_scroll.pack(side="right", fill="y")

        tree_frame = ttk.Frame(side_content)
        tree_frame.pack(fill="x", padx=5, pady=5)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", height=12)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

        self.tree.insert('', 'end', 'node_sondaj', text='🔵 SONDAJLAR (Mavi Nokta)', open=True)
        for i, s_dict in enumerate(self.map_data.get("sondaj", [])):
            self.tree.insert('node_sondaj', 'end', f'sondaj_{i}', text=s_dict["no"])

        self.tree.insert('', 'end', 'node_ss', text='🔴 SİSMİK SERİMLER (Kesikli Çizgi)', open=True)
        for i, ss_dict in enumerate(self.map_data.get("ss", [])):
            self.tree.insert('node_ss', 'end', f'ss_{i}', text=ss_dict["ad"])

        self.tree.insert('', 'end', 'node_mt', text='🟥 MİKROTREMÖR (Kırmızı Kare)', open=True)
        for i, mt_dict in enumerate(self.map_data.get("mt", [])):
            self.tree.insert('node_mt', 'end', f'mt_{i}', text=mt_dict["no"])

        if self.harita_tipi == "jeoloji" and self.formasyon:
            self.tree.insert('', 'end', 'node_formasyon', text=f'🟡 FORMASYON YAZISI ({self.formasyon})', open=True)
            for i in range(5):
                self.tree.insert('node_formasyon', 'end', f'formasyon_{i}', text=f'{self.formasyon} Yazısı {i+1}')

        ref_frame = ttk.LabelFrame(side_content, text="Koordinattan Yerleştir", padding=6)
        ref_frame.pack(fill="x", padx=5, pady=(2, 5))
        ref_values = [
            f"{idx + 1}: {p.get('lat', 0):.6f}, {p.get('lon', 0):.6f}"
            for idx, p in enumerate(self.kml_points)
        ] or ["KML noktası yok"]
        self.cmb_ref_point = ttk.Combobox(ref_frame, values=ref_values, state="readonly", width=28)
        self.cmb_ref_point.pack(fill="x", pady=(0, 4))
        self.cmb_ref_point.bind("<<ComboboxSelected>>", self.kml_ref_secildi)
        if self.kml_points:
            self.cmb_ref_point.current(0)
        self.lbl_kml_ref = ttk.Label(ref_frame, text="")
        self.lbl_kml_ref.pack(fill="x", pady=(0, 3))
        self.kml_preview_frame = ttk.Frame(ref_frame)
        self.kml_preview_frame.pack(fill="x", pady=(0, 4))
        self.kml_fig = plt.Figure(figsize=(3.1, 1.65), dpi=100)
        self.kml_ax = self.kml_fig.add_subplot(111)
        self.kml_preview_canvas = FigureCanvasTkAgg(self.kml_fig, master=self.kml_preview_frame)
        self.kml_preview_canvas.get_tk_widget().pack(fill="x")
        self.kml_preview_canvas.mpl_connect("button_press_event", self.on_kml_preview_click)
        self.lbl_ref_count = ttk.Label(ref_frame, text="")
        self.lbl_ref_count.pack(fill="x", pady=(0, 3))
        tk.Button(ref_frame, text="Referans Noktası Ekle", bg="#D6EAF8", font=("Arial", 9, "bold"), command=self.georef_ref_modu).pack(fill="x", pady=2)
        tk.Button(ref_frame, text="Noktaları Otomatik Yerleştir", bg="#D5F5E3", font=("Arial", 9, "bold"), command=self.koordinattan_otomatik_yerlestir).pack(fill="x", pady=2)
        tk.Button(ref_frame, text="Mevcutları Otomatik Yenile", bg="#FDEBD0", font=("Arial", 9, "bold"), command=lambda: self.koordinattan_otomatik_yerlestir(overwrite=True)).pack(fill="x", pady=2)
        tk.Button(ref_frame, text="Referansları Temizle", bg="#FADBD8", font=("Arial", 9, "bold"), command=self.georef_refs_temizle).pack(fill="x", pady=2)

        vis_frame = ttk.LabelFrame(side_content, text="Görünürlük", padding=6)
        vis_frame.pack(fill="x", padx=5, pady=(2, 5))
        ttk.Checkbutton(vis_frame, text="Sondajları Göster", variable=self.show_sondaj_var, command=self.gorunurluk_uygula).pack(anchor="w")
        ttk.Checkbutton(vis_frame, text="Jeofizik Ölçümleri Göster", variable=self.show_jeofizik_var, command=self.gorunurluk_uygula).pack(anchor="w")
        self.kml_preview_ciz()

    def plot_image(self):
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.fig.patch.set_facecolor('#ecf0f1')
        
        img = self.display_image_oku()
        self.ax.imshow(img, extent=(0, self.image_width, self.image_height, 0))
        self.ax.set_xlim(0, self.image_width)
        self.ax.set_ylim(self.image_height, 0)
        self.ax.axis('off')
        
        baslik = "ARAŞTIRMA NOKTALARI VAZİYET PLANI" if self.harita_tipi == "vaziyet" else "MÜHENDİSLİK JEOLOJİSİ HARİTASI"
        self.ax.set_title(baslik, fontsize=16, fontweight='bold', pad=15)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.map_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        
        # Eğer kaydedilmiş bir çizim varsa direkt onu geri yükle
        if self.saved_state and "objects" in self.saved_state:
            self.restore_saved_state()
        self.georef_refleri_ciz()
        self.georef_count_guncelle()
        self.gorunurluk_uygula()
        self.olcek_guncelle(redraw=False)

    def olcek_metni(self):
        if self.harita_tipi != "jeoloji":
            return ""
        value = str(self.olcek_var.get() if hasattr(self, "olcek_var") else "Yok").strip()
        if value in ("1/500", "1/1000"):
            return f"ÖLÇEK: {value}"
        return ""

    def olcek_guncelle(self, event=None, redraw=True):
        if not hasattr(self, "ax"):
            return
        if self.olcek_artist is not None:
            try:
                self.olcek_artist.remove()
            except Exception:
                pass
            self.olcek_artist = None
        text = self.olcek_metni()
        if text:
            self.olcek_artist = self.ax.text(
                0.985,
                0.035,
                text,
                transform=self.ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=11,
                fontweight="bold",
                color="black",
                bbox=dict(facecolor="white", alpha=0.88, edgecolor="black", boxstyle="square,pad=0.28"),
                zorder=60,
            )
        if redraw and hasattr(self, "canvas"):
            self.canvas.draw_idle()

    def export_olcek_ciz(self, ax_map):
        text = self.olcek_metni()
        if not text:
            return
        ax_map.text(
            0.985,
            0.035,
            text,
            transform=ax_map.transAxes,
            ha="right",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color="black",
            bbox=dict(facecolor="white", alpha=0.88, edgecolor="black", boxstyle="square,pad=0.28"),
            zorder=60,
        )

    def display_image_oku(self):
        cache_key = None
        try:
            cache_key = (os.path.abspath(self.img_path), os.path.getmtime(self.img_path), os.path.getsize(self.img_path), DISPLAY_IMAGE_MAX_DIM)
            cached = IMAGE_PREVIEW_CACHE.get(cache_key)
            if cached:
                self.image_width = cached["width"]
                self.image_height = cached["height"]
                self.display_image_shape = cached["shape"]
                return cached["array"]
        except Exception:
            cache_key = None

        try:
            from PIL import Image

            with Image.open(self.img_path) as pil_img:
                self.image_width, self.image_height = pil_img.size
                try:
                    pil_img.draft("RGB", (DISPLAY_IMAGE_MAX_DIM, DISPLAY_IMAGE_MAX_DIM))
                except Exception:
                    pass
                if max(pil_img.size) > DISPLAY_IMAGE_MAX_DIM:
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    pil_img.thumbnail((DISPLAY_IMAGE_MAX_DIM, DISPLAY_IMAGE_MAX_DIM), resample)
                if pil_img.mode not in ("RGB", "RGBA"):
                    pil_img = pil_img.convert("RGB")
                arr = np.asarray(pil_img).copy()
                self.display_image_shape = arr.shape
                self._display_image_cache_kaydet(cache_key, arr)
                return arr
        except Exception:
            img = mpimg.imread(self.img_path)
            self.image_height, self.image_width = img.shape[:2]
            self.display_image_shape = img.shape
            self._display_image_cache_kaydet(cache_key, img)
            return img

    def _display_image_cache_kaydet(self, cache_key, arr):
        if not cache_key:
            return
        IMAGE_PREVIEW_CACHE[cache_key] = {
            "array": arr,
            "width": self.image_width,
            "height": self.image_height,
            "shape": self.display_image_shape,
        }
        while len(IMAGE_PREVIEW_CACHE) > IMAGE_PREVIEW_CACHE_LIMIT:
            oldest_key = next(iter(IMAGE_PREVIEW_CACHE))
            IMAGE_PREVIEW_CACHE.pop(oldest_key, None)

    def check_tree_item(self, item_id):
        if self.tree.exists(item_id):
            text = self.tree.item(item_id, 'text')
            if not text.endswith(" (✓)"):
                self.tree.item(item_id, text=text + " (✓)")
    def _point_object_ekle(self, mod, item_id, x, y, isim, overwrite=False):
        if item_id in self.drawn_objects.get(mod, {}) and not overwrite:
            return False
        self.eski_cizimi_sil(mod, item_id)
        if mod == "sondaj":
            marker, = self.ax.plot(x, y, 'bo', markersize=9, markeredgecolor='black')
            txt = self.ax.text(x + 15, y - 15, isim, fontsize=11, fontweight='bold', color='blue')
        else:
            marker, = self.ax.plot(x, y, 'rs', markersize=9, markeredgecolor='black')
            txt = self.ax.text(x + 15, y - 15, isim, fontsize=11, fontweight='bold', color='darkred')
        self.drawn_objects[mod][item_id] = {"markers": [marker], "texts": [txt]}
        self.coords_memory[mod][item_id] = (x, y)
        self.check_tree_item(item_id)
        self.set_mod_visibility(mod, self.mod_gorunur(mod))
        return True

    def _ss_object_ekle(self, item_id, x1, y1, x2, y2, isim, overwrite=False):
        if item_id in self.drawn_objects.get("ss", {}) and not overwrite:
            return False
        self.eski_cizimi_sil("ss", item_id)
        line, = self.ax.plot([x1, x2], [y1, y2], 'r--', linewidth=2.5)
        m2, = self.ax.plot(x2, y2, 'ro', markersize=4)
        m1, = self.ax.plot(x1, y1, 'ro', markersize=4)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length, dx / length
        offset = self.ax.get_xlim()[1] * 0.025
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        txt = self.ax.text(
            mid_x + nx * offset,
            mid_y + ny * offset,
            isim,
            fontsize=11,
            fontweight='bold',
            color='red',
            ha='center',
            va='center',
        )
        self.drawn_objects["ss"][item_id] = {"markers": [m1, line, m2], "texts": [txt]}
        self.coords_memory["ss"][item_id] = [(x1, y1), (x2, y2)]
        self.check_tree_item(item_id)
        self.set_mod_visibility("ss", self.mod_gorunur("ss"))
        return True

    def koordinattan_otomatik_yerlestir(self, overwrite=False):
        try:
            coeff = affine_from_refs(self.georef_refs)
        except Exception as exc:
            messagebox.showwarning("Koordinatlı Yerleştirme", str(exc))
            return

        placed = 0
        skipped = 0
        for idx, item in enumerate(self.map_data.get("sondaj", [])):
            pair = self._as_float_pair(item.get("y"), item.get("x"))
            if not pair:
                continue
            x, y = coord_to_pixel(coeff, pair[0], pair[1])
            isim = item.get("no") or f"SK-{idx + 1}"
            if self._point_object_ekle("sondaj", f"sondaj_{idx}", x, y, isim, overwrite=overwrite):
                placed += 1
            else:
                skipped += 1

        for idx, item in enumerate(self.map_data.get("mt", [])):
            pair = self._as_float_pair(item.get("y"), item.get("x"))
            if not pair:
                continue
            x, y = coord_to_pixel(coeff, pair[0], pair[1])
            isim = item.get("no") or f"MT-{idx + 1}"
            if self._point_object_ekle("mt", f"mt_{idx}", x, y, isim, overwrite=overwrite):
                placed += 1
            else:
                skipped += 1

        for idx, item in enumerate(self.map_data.get("ss", [])):
            coords = item.get("coords", [])
            if len(coords) < 6:
                continue
            start = self._as_float_pair(coords[0], coords[1])
            end = self._as_float_pair(coords[4], coords[5])
            if not start or not end:
                continue
            x1, y1 = coord_to_pixel(coeff, start[0], start[1])
            x2, y2 = coord_to_pixel(coeff, end[0], end[1])
            isim = item.get("ad") or f"SS-{idx + 1}"
            if self._ss_object_ekle(f"ss_{idx}", x1, y1, x2, y2, isim, overwrite=overwrite):
                placed += 1
            else:
                skipped += 1

        self.gorunurluk_uygula(redraw=False)
        self.canvas.draw_idle()
        msg = f"{placed} çalışma noktası otomatik yerleştirildi."
        if skipped:
            msg += f"\n{skipped} mevcut çizim korunarak atlandı."
        self.lbl_talimat.config(text=msg.replace("\n", " "))

    def restore_saved_state(self):
        objs = self.saved_state["objects"]
        for mod in ["sondaj", "mt", "formasyon"]:
            for item_id, props in objs.get(mod, {}).items():
                cx, cy = props["coord_x"], props["coord_y"]
                tx, ty = props["x"], props["y"]
                
                if mod == "sondaj":
                    marker, = self.ax.plot(cx, cy, 'bo', markersize=9, markeredgecolor='black')
                    txt = self.ax.text(tx, ty, props["text"], fontsize=props["fontsize"], fontweight='bold', color=props["color"])
                elif mod == "mt":
                    marker, = self.ax.plot(cx, cy, 'rs', markersize=9, markeredgecolor='black')
                    txt = self.ax.text(tx, ty, props["text"], fontsize=props["fontsize"], fontweight='bold', color=props["color"])
                elif mod == "formasyon":
                    txt = self.ax.text(tx, ty, props["text"], fontsize=props["fontsize"], fontweight='bold', color=props["color"], bbox=dict(facecolor='white', alpha=0.8, edgecolor='black', boxstyle='round,pad=0.3'), ha='center', va='center')
                    marker = None
                
                self.drawn_objects[mod][item_id] = {"markers": [marker] if marker else [], "texts": [txt]}
                self.coords_memory[mod][item_id] = (cx, cy)
                self.check_tree_item(item_id)
        
        for item_id, props in objs.get("ss", {}).items():
            coords = props["coords"]
            x1, y1 = coords[0]; x2, y2 = coords[1]
            tx, ty = props["x"], props["y"]
            
            line, = self.ax.plot([x1, x2], [y1, y2], 'r--', linewidth=2.5)
            m2, = self.ax.plot(x2, y2, 'ro', markersize=4)
            m1, = self.ax.plot(x1, y1, 'ro', markersize=4)
            
            txt = self.ax.text(tx, ty, props["text"], fontsize=props["fontsize"], fontweight='bold', color=props["color"], ha='center', va='center')
            
            self.drawn_objects["ss"][item_id] = {"markers": [m1, line, m2], "texts": [txt]}
            self.coords_memory["ss"][item_id] = coords
            self.check_tree_item(item_id)
            
        self.canvas.draw()

    def get_state_for_save(self):
        state = {
            "img_path": self.img_path,
            "formasyon": self.formasyon,
            "scale": self.olcek_var.get() if hasattr(self, "olcek_var") else "Yok",
            "georef_refs": self.georef_refs,
            "visibility": {"sondaj": self.show_sondaj_var.get(), "jeofizik": self.show_jeofizik_var.get()},
            "objects": {"sondaj": {}, "ss": {}, "mt": {}, "formasyon": {}}
        }
        for mod in ["sondaj", "mt", "formasyon"]:
            for item_id, data in self.drawn_objects[mod].items():
                if not data["texts"]: continue
                t = data["texts"][0]
                tx, ty = t.get_position()
                cx, cy = self.coords_memory[mod][item_id]
                state["objects"][mod][item_id] = {"text": t.get_text(), "x": tx, "y": ty, "color": t.get_color(), "fontsize": t.get_fontsize(), "coord_x": cx, "coord_y": cy}
                
        for item_id, data in self.drawn_objects["ss"].items():
            if not data["texts"]: continue
            t = data["texts"][0]
            tx, ty = t.get_position()
            state["objects"]["ss"][item_id] = {"text": t.get_text(), "x": tx, "y": ty, "color": t.get_color(), "fontsize": t.get_fontsize(), "coords": self.coords_memory["ss"][item_id]}
        return state

    def trigger_save_state(self):
        if self.save_callback:
            self.save_callback(self.get_state_for_save())

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected: return
        item_id = selected[0]
        
        if self.temp_ss_marker:
            try:
                self.temp_ss_marker.remove()
            except Exception as exc:
                log_exception("resim_isaretleyici.temp_ss_marker.remove", exc_value=exc)
            self.canvas.draw()
            
        self.ss_start = None; self.temp_ss_marker = None
        self.active_ref_index = None

        if item_id.startswith("sondaj_") or item_id.startswith("mt_"):
            self.active_mod = item_id.split('_')[0]; self.active_id = item_id
            self.lbl_talimat.config(text=f"{self.tree.item(item_id, 'text').replace(' (✓)','')}: Resim üzerinde tıklayarak yerleştirin.")
        elif item_id.startswith("ss_"):
            self.active_mod = "ss"; self.active_id = item_id
            self.lbl_talimat.config(text=f"{self.tree.item(item_id, 'text').replace(' (✓)','')}: BAŞLANGIÇ ve BİTİŞ noktalarına tıklayın (2 Tık).")
        elif item_id.startswith("formasyon_"):
            self.active_mod = "formasyon"; self.active_id = item_id
            self.lbl_talimat.config(text=f"Haritaya tıklayarak '{self.formasyon}' yazısını yerleştirin.")
        else:
            self.active_mod = None; self.active_id = None

    def get_clicked_text(self, event):
        for mod, items in self.drawn_objects.items():
            for item_id, elements in items.items():
                for t in elements.get("texts", []):
                    cont, _ = t.contains(event)
                    if cont: return t
        return None

    def _hit_radius(self):
        try:
            x0, x1 = self.ax.get_xlim()
            y0, y1 = self.ax.get_ylim()
            return max(8.0, min(abs(x1 - x0), abs(y1 - y0)) * 0.018)
        except Exception:
            return 12.0

    def _dist_to_segment(self, px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        denom = dx * dx + dy * dy
        if denom == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / denom))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def get_clicked_object(self, event):
        if event.xdata is None or event.ydata is None:
            return None
        x, y = event.xdata, event.ydata
        radius = self._hit_radius()
        best = None

        for mod in ["sondaj", "mt"]:
            for item_id, coord in self.coords_memory.get(mod, {}).items():
                if item_id not in self.drawn_objects.get(mod, {}):
                    continue
                try:
                    cx, cy = coord
                    dist = math.hypot(x - cx, y - cy)
                except Exception:
                    continue
                if dist <= radius and (best is None or dist < best["dist"]):
                    best = {"kind": "point", "mod": mod, "item_id": item_id, "dist": dist}

        for item_id, coords in self.coords_memory.get("ss", {}).items():
            if item_id not in self.drawn_objects.get("ss", {}):
                continue
            if len(coords) < 2:
                continue
            try:
                (x1, y1), (x2, y2) = coords
            except Exception:
                continue
            d1 = math.hypot(x - x1, y - y1)
            d2 = math.hypot(x - x2, y - y2)
            dl = self._dist_to_segment(x, y, x1, y1, x2, y2)
            if d1 <= radius and (best is None or d1 < best["dist"]):
                best = {"kind": "ss_endpoint", "item_id": item_id, "endpoint": 0, "dist": d1}
            if d2 <= radius and (best is None or d2 < best["dist"]):
                best = {"kind": "ss_endpoint", "item_id": item_id, "endpoint": 1, "dist": d2}
            if dl <= radius * 0.75 and (best is None or dl < best["dist"]):
                best = {"kind": "ss_line", "item_id": item_id, "dist": dl}

        return best

    def start_object_drag(self, event, target):
        item_id = target["item_id"]
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
        target["last"] = (event.xdata, event.ydata)
        if target["kind"] == "point":
            if item_id not in self.drawn_objects.get(target["mod"], {}):
                return
            coord = self.coords_memory[target["mod"]][item_id]
            elements = self.drawn_objects[target["mod"]][item_id]
            text_offsets = []
            for txt in elements.get("texts", []):
                tx, ty = txt.get_position()
                text_offsets.append((txt, tx - coord[0], ty - coord[1]))
            target["text_offsets"] = text_offsets
        elif target["kind"].startswith("ss"):
            if item_id not in self.drawn_objects.get("ss", {}):
                return
            coords = self.coords_memory["ss"][item_id]
            mid = ((coords[0][0] + coords[1][0]) / 2, (coords[0][1] + coords[1][1]) / 2)
            elements = self.drawn_objects["ss"][item_id]
            text_offsets = []
            for txt in elements.get("texts", []):
                tx, ty = txt.get_position()
                text_offsets.append((txt, tx - mid[0], ty - mid[1]))
            target["text_offsets"] = text_offsets
        self.dragging_object = target
        self.lbl_talimat.config(text="İşaret sürükleniyor. Bıraktığınız yerde manuel düzeltme kaydedilebilir.")

    def update_object_drag(self, event):
        if not self.dragging_object or event.xdata is None or event.ydata is None:
            return
        target = self.dragging_object
        last_x, last_y = target.get("last", (event.xdata, event.ydata))
        dx, dy = event.xdata - last_x, event.ydata - last_y
        target["last"] = (event.xdata, event.ydata)

        if target["kind"] == "point":
            mod = target["mod"]
            item_id = target["item_id"]
            old_x, old_y = self.coords_memory[mod][item_id]
            new_x, new_y = old_x + dx, old_y + dy
            self.coords_memory[mod][item_id] = (new_x, new_y)
            elements = self.drawn_objects[mod][item_id]
            for marker in elements.get("markers", []):
                marker.set_data([new_x], [new_y])
            for txt, off_x, off_y in target.get("text_offsets", []):
                txt.set_position((new_x + off_x, new_y + off_y))

        elif target["kind"] in ("ss_endpoint", "ss_line"):
            item_id = target["item_id"]
            coords = list(self.coords_memory["ss"][item_id])
            if target["kind"] == "ss_endpoint":
                endpoint = target["endpoint"]
                old_x, old_y = coords[endpoint]
                coords[endpoint] = (old_x + dx, old_y + dy)
            else:
                coords = [(x + dx, y + dy) for x, y in coords]
            self.coords_memory["ss"][item_id] = coords
            self._ss_artists_guncelle(item_id, target.get("text_offsets", []))

        self.canvas.draw_idle()

    def _ss_artists_guncelle(self, item_id, text_offsets=None):
        coords = self.coords_memory["ss"][item_id]
        if len(coords) < 2:
            return
        (x1, y1), (x2, y2) = coords
        elements = self.drawn_objects["ss"][item_id]
        markers = elements.get("markers", [])
        if len(markers) >= 3:
            try:
                markers[0].set_data([x1], [y1])
                markers[1].set_data([x1, x2], [y1, y2])
                markers[2].set_data([x2], [y2])
            except Exception:
                pass
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        if text_offsets is None:
            text_offsets = []
        for txt, off_x, off_y in text_offsets:
            txt.set_position((mid[0] + off_x, mid[1] + off_y))

    def get_clicked_text_target(self, event):
        for mod, items in self.drawn_objects.items():
            for item_id, elements in items.items():
                for t in elements.get("texts", []):
                    cont, _ = t.contains(event)
                    if cont:
                        return {"text": t, "mod": mod, "item_id": item_id}
        return None

    def sag_tik_menu_goster(self, event, text_target=None, object_target=None):
        menu = tk.Menu(self, tearoff=0)
        mod = None
        item_id = None
        if object_target:
            if object_target.get("kind") == "point":
                mod = object_target.get("mod")
            elif str(object_target.get("kind", "")).startswith("ss"):
                mod = "ss"
            item_id = object_target.get("item_id")
        elif text_target:
            mod = text_target.get("mod")
            item_id = text_target.get("item_id")
            menu.add_command(label="Yazıyı Düzenle", command=lambda: self.edit_text_format(text_target["text"]))
        if mod and item_id:
            menu.add_command(label="Sil", command=lambda: self.ogeyi_sil(mod, item_id))
            try:
                gui_event = getattr(event, "guiEvent", None)
                x_root = getattr(gui_event, "x_root", self.winfo_pointerx())
                y_root = getattr(gui_event, "y_root", self.winfo_pointery())
                menu.tk_popup(x_root, y_root)
            finally:
                menu.grab_release()

    def on_click(self, event):
        if event.inaxes != self.ax: return

        if self.active_mod == "georef":
            if event.button == 1 and event.xdata is not None and event.ydata is not None:
                self.georef_ref_ekle(event.xdata, event.ydata)
            return

        clicked_text_target = self.get_clicked_text_target(event)
        if clicked_text_target:
            if event.button == 1:
                clicked_text = clicked_text_target["text"]
                self.dragging_text = clicked_text
                x, y = clicked_text.get_position()
                self.drag_offset = (x - event.xdata, y - event.ydata)
            elif event.button == 3:
                self.sag_tik_menu_goster(event, text_target=clicked_text_target)
            return

        clicked_object = self.get_clicked_object(event)
        if clicked_object and event.button == 1:
            self.start_object_drag(event, clicked_object)
            return
        if clicked_object and event.button == 3:
            self.sag_tik_menu_goster(event, object_target=clicked_object)
            return

        if event.button == 1 and self.active_mod:
            x, y = event.xdata, event.ydata
            isim = self.tree.item(self.active_id, 'text').replace(' (✓)', '')

            if self.active_mod in ["sondaj", "mt"]:
                self.eski_cizimi_sil(self.active_mod, self.active_id)
                if self.active_mod == "sondaj":
                    marker, = self.ax.plot(x, y, 'bo', markersize=9, markeredgecolor='black')
                    txt = self.ax.text(x+15, y-15, isim, fontsize=11, fontweight='bold', color='blue')
                else:
                    marker, = self.ax.plot(x, y, 'rs', markersize=9, markeredgecolor='black')
                    txt = self.ax.text(x+15, y-15, isim, fontsize=11, fontweight='bold', color='darkred')
                
                self.drawn_objects[self.active_mod][self.active_id] = {"markers": [marker], "texts": [txt]}
                self.coords_memory[self.active_mod][self.active_id] = (x, y)
                self.check_tree_item(self.active_id)
                self.gorunurluk_uygula(redraw=False)
                self.canvas.draw()

            elif self.active_mod == "ss":
                if self.ss_start is None:
                    self.eski_cizimi_sil(self.active_mod, self.active_id)
                    self.ss_start = (x, y)
                    self.temp_ss_marker, = self.ax.plot(x, y, 'ro', markersize=4)
                    self.temp_ss_marker.set_visible(self.mod_gorunur("ss"))
                    self.canvas.draw()
                else:
                    x1, y1 = self.ss_start; x2, y2 = x, y
                    line, = self.ax.plot([x1, x2], [y1, y2], 'r--', linewidth=2.5)
                    m2, = self.ax.plot(x2, y2, 'ro', markersize=4)
                    m1, = self.ax.plot(x1, y1, 'ro', markersize=4)
                    
                    dx, dy = x2 - x1, y2 - y1; length = math.hypot(dx, dy)
                    if length == 0: length = 1
                    nx, ny = -dy/length, dx/length
                    offset = self.ax.get_xlim()[1] * 0.025
                    mid_x, mid_y = (x1+x2)/2, (y1+y2)/2
                    t2_x, t2_y = mid_x + (nx * offset), mid_y + (ny * offset)
                    
                    txt = self.ax.text(t2_x, t2_y, isim, fontsize=11, fontweight='bold', color='red', ha='center', va='center')
                    
                    self.drawn_objects["ss"][self.active_id] = {"markers": [m1, line, m2], "texts": [txt]}
                    self.coords_memory["ss"][self.active_id] = [(x1,y1), (x2,y2)]
                    self.ss_start = None; self.temp_ss_marker = None
                    self.check_tree_item(self.active_id)
                    self.gorunurluk_uygula(redraw=False)
                    self.canvas.draw()
                    
            elif self.active_mod == "formasyon":
                self.eski_cizimi_sil(self.active_mod, self.active_id)
                txt = self.ax.text(x, y, self.formasyon, fontsize=14, fontweight='bold', color='black',
                                   bbox=dict(facecolor='white', alpha=0.8, edgecolor='black', boxstyle='round,pad=0.3'), ha='center', va='center')
                self.drawn_objects["formasyon"][self.active_id] = {"markers": [], "texts": [txt]}
                self.coords_memory["formasyon"][self.active_id] = (x, y)
                self.check_tree_item(self.active_id)
                self.canvas.draw()

    def on_motion(self, event):
        if self.dragging_object and event.inaxes == self.ax:
            self.update_object_drag(event)
            return
        if self.dragging_text and event.inaxes == self.ax:
            new_x = event.xdata + self.drag_offset[0]
            new_y = event.ydata + self.drag_offset[1]
            self.dragging_text.set_position((new_x, new_y))
            self.canvas.draw_idle()

    def on_release(self, event):
        if event.button == 1:
            self.dragging_text = None
            self.dragging_object = None

    def edit_text_format(self, txt_obj):
        win = tk.Toplevel(self); win.title("Yazı Formatı Düzenle"); win.geometry("250x250"); win.attributes('-topmost', True)
        ttk.Label(win, text="Metin İçeriği:").pack(pady=5); e_text = ttk.Entry(win, width=25); e_text.insert(0, txt_obj.get_text()); e_text.pack()
        ttk.Label(win, text="Punto (Büyüklük):").pack(pady=5); e_size = ttk.Spinbox(win, from_=6, to=48, width=23); e_size.set(int(txt_obj.get_fontsize())); e_size.pack()
        ttk.Label(win, text="Renk:").pack(pady=5); e_color = ttk.Combobox(win, values=["blue", "red", "darkred", "black", "green", "purple"], width=23); e_color.set(txt_obj.get_color()); e_color.pack()
        def save(): txt_obj.set_text(e_text.get()); txt_obj.set_fontsize(int(e_size.get())); txt_obj.set_color(e_color.get()); self.canvas.draw(); win.destroy()
        tk.Button(win, text="UYGULA", bg="#2980B9", fg="white", font=("Arial", 10, "bold"), command=save).pack(pady=15)

    def eski_cizimi_sil(self, mod, item_id):
        if item_id in self.drawn_objects[mod]:
            elements = self.drawn_objects[mod][item_id]
            for m in elements.get("markers", []):
                try:
                    m.remove()
                except Exception as exc:
                    log_exception("resim_isaretleyici.marker.remove", exc_value=exc)
            for t in elements.get("texts", []):
                try:
                    t.remove()
                except Exception as exc:
                    log_exception("resim_isaretleyici.text.remove", exc_value=exc)
            del self.drawn_objects[mod][item_id]
        if item_id in self.coords_memory.get(mod, {}):
            del self.coords_memory[mod][item_id]

    def ogeyi_sil(self, mod, item_id):
        self.eski_cizimi_sil(mod, item_id)
        if self.temp_ss_marker and mod == "ss" and item_id == self.active_id:
            try:
                self.temp_ss_marker.remove()
            except Exception:
                pass
            self.temp_ss_marker = None
            self.ss_start = None
        if self.active_mod == mod and self.active_id == item_id:
            self.active_mod = None
            self.active_id = None
        if hasattr(self, "tree") and self.tree.exists(item_id):
            text = self.tree.item(item_id, 'text')
            if text.endswith(" (✓)"):
                self.tree.item(item_id, text=text.replace(" (✓)", ""))
        if hasattr(self, "canvas"):
            self.canvas.draw_idle()

    def secileni_sil(self):
        if self.active_mod and self.active_id:
            self.ogeyi_sil(self.active_mod, self.active_id)

    def get_formasyon_adi(self):
        formasyon_isimleri = {'Qal': 'Alüvyon (Qal)', 'Tmal': 'Alçıtepe Üyesi (Tmal)', 'Tmçd': 'Çamrakdere Üyesi (Tmçd)', 'Tmki': 'Kirazlı Üyesi (Tmki)', 'Tmçk': 'Çanakkale Formasyonu (Tmçk)'}
        return formasyon_isimleri.get(self.formasyon, self.formasyon)

    def mod_gorunur(self, mod):
        if mod == "sondaj":
            return bool(self.show_sondaj_var.get())
        if mod in ("ss", "mt"):
            return bool(self.show_jeofizik_var.get())
        return True

    def gorunurluk_uygula(self, redraw=True):
        self.set_mod_visibility("sondaj", self.mod_gorunur("sondaj"))
        self.set_mod_visibility("ss", self.mod_gorunur("ss"))
        self.set_mod_visibility("mt", self.mod_gorunur("mt"))
        if self.temp_ss_marker:
            try:
                self.temp_ss_marker.set_visible(self.mod_gorunur("ss"))
            except Exception:
                pass
        if redraw and hasattr(self, "canvas"):
            self.canvas.draw_idle()

    def export_mod_gorunur(self, mod, respect_visibility=True):
        return True if not respect_visibility else self.mod_gorunur(mod)

    def set_mod_visibility(self, mod, visible):
        if mod in self.drawn_objects:
            for item_id, elements in self.drawn_objects[mod].items():
                for m in elements.get("markers", []): m.set_visible(visible)
                for t in elements.get("texts", []): t.set_visible(visible)

    def set_temp_ss_marker_visibility(self, visible):
        if not self.temp_ss_marker:
            return None
        try:
            onceki = self.temp_ss_marker.get_visible()
            self.temp_ss_marker.set_visible(visible)
            return onceki
        except Exception:
            return None

    def export_for_word(self):
        if not self.word_callback: return
        self.trigger_save_state() # Word'e yollarken projeye de otomatik kaydet
        temp_ss_onceki = self.set_temp_ss_marker_visibility(False)
        self.set_georef_visibility(False)
        
        if self.harita_tipi == "jeoloji":
            path_mjh = yeni_harita_cikti_yolu("mjh")
            orig_title = self.ax.get_title()
            self.ax.set_title("")
            self.set_mod_visibility("sondaj", True)
            self.set_mod_visibility("ss", True)
            self.set_mod_visibility("mt", True)
            self.set_mod_visibility("formasyon", True)
            self.canvas.draw()
            self.save_a4_pafta(path_mjh, respect_visibility=False)
            self.ax.set_title(orig_title)
            self.set_georef_visibility(True)
            self.canvas.draw()

            self.word_callback(None, None, path_mjh, harita_tipi=self.harita_tipi)
            messagebox.showinfo("Başarılı", "Mühendislik jeolojisi haritası Word raporu için RESIM:MJH alanına aktarıldı!")
            self.destroy()
            return

        path_jeo = yeni_harita_cikti_yolu("jeofizik_lokasyon")
        path_son = yeni_harita_cikti_yolu("sondaj_lokasyon")

        self.save_filtered_location_image(path_jeo, show_sondaj=False, show_ss=True, show_mt=True)
        self.save_filtered_location_image(path_son, show_sondaj=True, show_ss=False, show_mt=False)

        if temp_ss_onceki is not None:
            self.set_temp_ss_marker_visibility(temp_ss_onceki)
        self.set_georef_visibility(True)
        self.canvas.draw()
        
        self.word_callback(path_son, path_jeo, None, harita_tipi=self.harita_tipi)
        messagebox.showinfo("Başarılı", "Çizimler projeye kaydedildi ve filtrelenmiş haritalar Word raporu için hafızaya alındı!")
        self.destroy()

    def save_filtered_location_image(self, path, show_sondaj=True, show_ss=True, show_mt=True, show_formasyon=False):
        fig_exp = plt.figure(figsize=self.fig.get_size_inches() if hasattr(self, "fig") else (10, 8))
        fig_exp.patch.set_facecolor('#ecf0f1')
        ax_map = fig_exp.add_subplot(111)
        ax_map.imshow(self.display_image_oku(), extent=(0, self.image_width, self.image_height, 0))
        ax_map.set_xlim(0, self.image_width)
        ax_map.set_ylim(self.image_height, 0)
        ax_map.axis('off')

        if show_sondaj:
            for item_id, (x, y) in self.coords_memory["sondaj"].items():
                if item_id in self.drawn_objects.get("sondaj", {}):
                    ax_map.plot(x, y, 'bo', markersize=9, markeredgecolor='black')
        if show_ss:
            for item_id, coords in self.coords_memory["ss"].items():
                if item_id not in self.drawn_objects.get("ss", {}) or len(coords) < 2:
                    continue
                ax_map.plot([coords[0][0], coords[1][0]], [coords[0][1], coords[1][1]], 'r--', linewidth=2.5)
                ax_map.plot(coords[0][0], coords[0][1], 'ro', markersize=4)
                ax_map.plot(coords[1][0], coords[1][1], 'ro', markersize=4)
        if show_mt:
            for item_id, (x, y) in self.coords_memory["mt"].items():
                if item_id in self.drawn_objects.get("mt", {}):
                    ax_map.plot(x, y, 'rs', markersize=9, markeredgecolor='black')

        visible_mods = []
        if show_sondaj:
            visible_mods.append("sondaj")
        if show_ss:
            visible_mods.append("ss")
        if show_mt:
            visible_mods.append("mt")
        if show_formasyon:
            visible_mods.append("formasyon")
        for mod in visible_mods:
            for item_id, elements in self.drawn_objects.get(mod, {}).items():
                for t in elements.get("texts", []):
                    x, y = t.get_position()
                    bbox_props = dict(facecolor='white', alpha=0.8, edgecolor='black', boxstyle='round,pad=0.3') if mod == "formasyon" else None
                    ax_map.text(
                        x, y, t.get_text(),
                        color=t.get_color(),
                        fontsize=t.get_fontsize(),
                        fontweight=t.get_fontweight(),
                        ha=t.get_ha(),
                        va=t.get_va(),
                        bbox=bbox_props,
                    )

        fig_exp.savefig(path, dpi=DEFAULT_EXPORT_DPI, bbox_inches='tight', pad_inches=0.02)
        plt.close(fig_exp)
