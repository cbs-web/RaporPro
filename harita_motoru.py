# Dosya: RaporPro/harita_motoru.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkintermapview
import math
import os

from harita_referans import affine_from_refs, coord_to_pixel, kml_koordinatlari_oku, pixel_to_coord, valid_latlon
from performans import log_exception

class TopluHarita(tk.Toplevel):
    def __init__(self, master, kml_path=None, map_data=None, callback=None):
        super().__init__(master)
        self.title("CBS - Toplu Koordinat ve Serim Seçimi")
        self.geometry("1300x800")
        self.kml_path = kml_path
        self.map_data = map_data or {"sondaj": [], "ss": [], "mt": []}
        self.initial_results = self.map_data.get("initial", {})
        self.callback = callback
        
        self.active_id = None
        self.active_mod = None
        self.click_count = 0
        self.start_coord = None
        self.temp_path = None
        
        self.results = {"alan": None, "sondaj": {}, "ss": {}, "mt": {}}
        self.drawn_objects = {}
        self.marker_styles = {
            "alan": {
                "marker_color_circle": "#F4D03F",
                "marker_color_outside": "#111111",
                "text_color": "#F7DC6F",
                "font": ("Arial", 12, "bold"),
            },
            "sondaj": {
                "marker_color_circle": "#E74C3C",
                "marker_color_outside": "#FFFFFF",
                "text_color": "#FFFFFF",
                "font": ("Arial", 12, "bold"),
            },
            "ss": {
                "marker_color_circle": "#00AEEF",
                "marker_color_outside": "#FFFFFF",
                "text_color": "#EAF7FF",
                "font": ("Arial", 12, "bold"),
            },
            "mt": {
                "marker_color_circle": "#2ECC71",
                "marker_color_outside": "#0B3D2E",
                "text_color": "#D5F5E3",
                "font": ("Arial", 12, "bold"),
            },
        }

        self.setup_ui()
        if self.kml_path and os.path.exists(self.kml_path):
            self.kml_yukle()
        self.yuklu_noktalari_ciz()

    def setup_ui(self):
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5, bg="#ccc")
        paned.pack(fill="both", expand=True)

        map_frame = ttk.Frame(paned)
        paned.add(map_frame, width=950)
        
        info_frame = tk.Frame(map_frame, bg="#34495E", height=40)
        info_frame.pack(fill="x")
        self.lbl_talimat = tk.Label(info_frame, text="Lütfen sağdaki listeden işlem yapmak istediğiniz noktayı seçin.", fg="white", bg="#34495E", font=("Arial", 11, "bold"))
        self.lbl_talimat.pack(side="left", padx=15, pady=10)
        self.lbl_mesafe = tk.Label(info_frame, text="", fg="#F1C40F", bg="#34495E", font=("Arial", 11, "bold"))
        self.lbl_mesafe.pack(side="right", padx=15, pady=10)

        self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}", max_zoom=22)
        self.map_widget.set_position(39.9334, 32.8597) 
        self.map_widget.set_zoom(6)
        self.map_widget.add_left_click_map_command(self.on_map_click)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, width=300)
        
        lbl_baslik = tk.Label(right_frame, text="ARAŞTIRMA NOKTALARI", bg="#2C3E50", fg="white", font=("Arial", 12, "bold"), pady=10)
        lbl_baslik.pack(fill="x")

        legend = tk.Frame(right_frame, bg="#F4F6F7")
        legend.pack(fill="x", padx=5, pady=(5, 0))
        for label, color, detail in [
            ("SK", "#E74C3C", "Sondaj"),
            ("SS", "#00AEEF", "Serim başlangıcı"),
            ("MT", "#2ECC71", "Mikrotremör"),
            ("KML", "#F1C40F", "Sınır"),
        ]:
            item = tk.Frame(legend, bg="#F4F6F7")
            item.pack(side="left", padx=3, pady=4)
            tk.Label(item, text=label, bg=color, fg="#111111" if color in ("#F1C40F", "#2ECC71") else "white", font=("Arial", 8, "bold"), padx=4).pack(side="left")
            tk.Label(item, text=detail, bg="#F4F6F7", fg="#333333", font=("Arial", 8)).pack(side="left", padx=(2, 0))

        mode_frame = ttk.LabelFrame(right_frame, text="Seçim Modu", padding=(6, 5))
        mode_frame.pack(fill="x", padx=5, pady=(6, 2))
        tk.Button(
            mode_frame,
            text="Vaziyet Planı Görseliyle Seç",
            bg="#D6EAF8",
            fg="#1B4F72",
            font=("Arial", 9, "bold"),
            command=self.gorsel_bindirme_ac,
        ).pack(fill="x")
        ttk.Label(
            mode_frame,
            text="Görsel yoksa bu harita üzerinden doğrudan işaretlemeye devam edebilirsiniz.",
            wraplength=260,
            foreground="#566573",
        ).pack(fill="x", pady=(4, 0))

        self.tree = ttk.Treeview(right_frame, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

        self.tree.insert('', 'end', 'node_alan', text='📍 ÇALIŞMA ALANI', open=True)
        self.tree.insert('node_alan', 'end', 'alan_0', text='Merkez Koordinat')

        self.tree.insert('', 'end', 'node_sondaj', text='🔴 SONDAJLAR', open=True)
        for i, no in enumerate(self.map_data.get("sondaj", [])):
            self.tree.insert('node_sondaj', 'end', f'sondaj_{i}', text=no)

        self.tree.insert('', 'end', 'node_ss', text='🟦 SİSMİK SERİMLER', open=True)
        for i, ad in enumerate(self.map_data.get("ss", [])):
            self.tree.insert('node_ss', 'end', f'ss_{i}', text=ad)

        self.tree.insert('', 'end', 'node_mt', text='🟩 MİKROTREMÖR', open=True)
        for i, no in enumerate(self.map_data.get("mt", [])):
            self.tree.insert('node_mt', 'end', f'mt_{i}', text=no)

        btn_kaydet = tk.Button(right_frame, text="💾 KAYDET VE AKTAR", bg="#27AE60", fg="white", font=("Arial", 12, "bold"), pady=10, command=self.kaydet_ve_kapat)
        btn_kaydet.pack(fill="x", padx=5, pady=10)

    def gorsel_bindirme_ac(self):
        if not self.kml_path or not os.path.exists(self.kml_path):
            messagebox.showwarning("Görüntü Bindirme", "Görüntü bindirmek için önce KML sınır dosyası seçilmiş olmalı.")
            return
        img_path = filedialog.askopenfilename(
            title="Bindirilecek vaziyet planı görselini seç",
            filetypes=[
                ("Görsel Dosyaları", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"),
                ("Tüm Dosyalar", "*.*"),
            ],
        )
        if not img_path:
            return
        TopluHaritaGorselBindirme(
            self,
            img_path=img_path,
            kml_path=self.kml_path,
            map_data=self.map_data,
            initial_results=self.results,
            callback=self.sonuclari_yukle,
        )

    def _sonuclari_kopyala(self, results):
        copied = {"alan": None, "sondaj": {}, "ss": {}, "mt": {}}
        if results.get("alan"):
            copied["alan"] = tuple(results["alan"])
        for group in ("sondaj", "mt"):
            for key, value in (results.get(group) or {}).items():
                copied[group][int(key)] = tuple(value)
        for key, value in (results.get("ss") or {}).items():
            copied["ss"][int(key)] = list(value)
        return copied

    def _tum_cizimleri_sil(self):
        for item_id in list(self.drawn_objects.keys()):
            self._drawn_sil(item_id)
        self.drawn_objects = {}
        if self.temp_path:
            try:
                self.temp_path.delete()
            except Exception:
                pass
            self.temp_path = None

    def _tum_isaretleri_temizle(self):
        for item_id in self.tree.get_children(""):
            for child_id in self.tree.get_children(item_id):
                text = self.tree.item(child_id, "text")
                if text.endswith(" (✓)"):
                    self.tree.item(child_id, text=text[:-4])

    def sonuclari_yukle(self, results):
        self.results = self._sonuclari_kopyala(results)
        self.initial_results = self.results
        self.click_count = 0
        self.start_coord = None
        self.map_widget.canvas.unbind("<Motion>")
        self.lbl_mesafe.config(text="")
        self._tum_cizimleri_sil()
        self._tum_isaretleri_temizle()
        self.yuklu_noktalari_ciz()
        self.lbl_talimat.config(text="Bindirmeli görselden gelen koordinatlar haritaya aktarıldı.")

    def kml_yukle(self):
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(self.kml_path)
            root = tree.getroot()
            path = []
            for elem in root.iter():
                if 'coordinates' in str(elem.tag):
                    coords_str = str(elem.text)
                    temp_path = []
                    for row in coords_str.strip().split():
                        if row.strip():
                            parts = row.split(',')
                            if len(parts) >= 2:
                                lon, lat = float(parts[0]), float(parts[1])
                                temp_path.append((lat, lon))
                    if len(temp_path) > 2:
                        path = temp_path
                        break 
            
            if path:
                self.map_widget.set_polygon(path, outline_color="#F1C40F", fill_color=None, border_width=4, name="Çalışma Alanı")
                lats = [p[0] for p in path]; lons = [p[1] for p in path]
                self.map_widget.set_position(sum(lats)/len(lats), sum(lons)/len(lons))
                self.map_widget.set_zoom(17)
        except Exception as e:
            print("KML Yükleme Hatası:", e)

    def haversine_distance(self, coord1, coord2):
        R = 6371000 
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        c = 2 * math.atan2(math.sqrt(math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2), math.sqrt(1 - (math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)))
        return R * c

    def get_midpoint(self, coord1, coord2):
        return ((coord1[0] + coord2[0]) / 2, (coord1[1] + coord2[1]) / 2)

    def isareti_guncelle(self):
        text = self.tree.item(self.active_id, 'text')
        if not text.endswith(" (✓)"):
            self.tree.item(self.active_id, text=text + " (✓)")

    def _isareti_isaretle(self, item_id):
        try:
            if not self.tree.exists(item_id):
                return
            text = self.tree.item(item_id, 'text')
            if not text.endswith(" (✓)"):
                self.tree.item(item_id, text=text + " (✓)")
        except Exception:
            pass

    def _item_text(self, item_id, default=""):
        try:
            return self.tree.item(item_id, 'text').replace(' (✓)', '')
        except Exception:
            return default

    def _marker_ekle(self, kind, lat, lon, text):
        style = dict(self.marker_styles.get(kind, {}))
        return self.map_widget.set_marker(lat, lon, text=text, **style)

    def _path_ekle(self, points, color="#00AEEF", width=4, shadow=True):
        objects = []
        if shadow:
            objects.append(self.map_widget.set_path(points, color="#FFFFFF", width=width + 4))
        objects.append(self.map_widget.set_path(points, color=color, width=width))
        return objects

    def _drawn_sil(self, item_id):
        objects = self.drawn_objects.get(item_id)
        if not objects:
            return
        if not isinstance(objects, (list, tuple)):
            objects = [objects]
        for obj in objects:
            try:
                obj.delete()
            except Exception:
                pass
        self.drawn_objects.pop(item_id, None)

    def _as_coord_pair(self, value):
        if not value or len(value) < 2:
            return None
        try:
            y, x = float(value[0]), float(value[1])
        except Exception:
            return None
        return (y, x) if y != 0 and x != 0 else None

    def _iter_indexed(self, mapping):
        if not isinstance(mapping, dict):
            return []
        items = []
        for key, value in mapping.items():
            try:
                idx = int(key)
            except Exception:
                continue
            items.append((idx, value))
        return sorted(items, key=lambda item: item[0])

    def _zoom_for_points(self, points):
        if len(points) <= 1:
            return 17
        lat_span = max(p[0] for p in points) - min(p[0] for p in points)
        lon_span = max(p[1] for p in points) - min(p[1] for p in points)
        span = max(lat_span, lon_span)
        if span < 0.003:
            return 18
        if span < 0.01:
            return 17
        if span < 0.03:
            return 15
        if span < 0.08:
            return 13
        return 11

    def yuklu_noktalari_ciz(self):
        points = []
        initial = self.initial_results or {}

        alan = self._as_coord_pair(initial.get("alan") or [])
        if alan:
            marker = self._marker_ekle("alan", alan[0], alan[1], "Merkez Koordinat")
            self.drawn_objects["alan_0"] = marker
            self.results["alan"] = alan
            self._isareti_isaretle("alan_0")
            points.append(alan)

        for idx, coords in self._iter_indexed(initial.get("sondaj", {})):
            item_id = f"sondaj_{idx}"
            pair = self._as_coord_pair(coords)
            if not pair or not self.tree.exists(item_id):
                continue
            marker = self._marker_ekle("sondaj", pair[0], pair[1], self._item_text(item_id, f"SK-{idx + 1}"))
            self.drawn_objects[item_id] = marker
            self.results["sondaj"][idx] = pair
            self._isareti_isaretle(item_id)
            points.append(pair)

        for idx, coords in self._iter_indexed(initial.get("mt", {})):
            item_id = f"mt_{idx}"
            pair = self._as_coord_pair(coords)
            if not pair or not self.tree.exists(item_id):
                continue
            marker = self._marker_ekle("mt", pair[0], pair[1], self._item_text(item_id, f"MT-{idx + 1}"))
            self.drawn_objects[item_id] = marker
            self.results["mt"][idx] = pair
            self._isareti_isaretle(item_id)
            points.append(pair)

        for idx, coords in self._iter_indexed(initial.get("ss", {})):
            item_id = f"ss_{idx}"
            if not coords or len(coords) < 6 or not self.tree.exists(item_id):
                continue
            try:
                vals = [float(value) for value in coords[:6]]
            except Exception:
                continue
            start = (vals[0], vals[1])
            mid = (vals[2], vals[3])
            end = (vals[4], vals[5])
            if not self._as_coord_pair(start) or not self._as_coord_pair(end):
                continue
            isim = self._item_text(item_id, f"SS-{idx + 1}")
            paths = self._path_ekle([start, end], color="#00AEEF", width=4, shadow=True)
            m_start = self._marker_ekle("ss", start[0], start[1], f"{isim}-Baş")
            self.drawn_objects[item_id] = [m_start] + paths
            self.results["ss"][idx] = vals
            self._isareti_isaretle(item_id)
            points.extend([start, end])

        if points:
            center_y = sum(p[0] for p in points) / len(points)
            center_x = sum(p[1] for p in points) / len(points)
            self.map_widget.set_position(center_y, center_x)
            self.map_widget.set_zoom(self._zoom_for_points(points))

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected: return
        item_id = selected[0]

        self.click_count = 0
        self.start_coord = None
        if self.temp_path:
            self.temp_path.delete()
            self.temp_path = None
        self.map_widget.canvas.unbind("<Motion>")
        self.lbl_mesafe.config(text="")

        if item_id.startswith("alan_"):
            self.active_mod = "alan"; self.active_id = item_id
            self.lbl_talimat.config(text="MERKEZ KOORDİNAT: Haritaya tek tıklayın.")
        elif item_id.startswith("sondaj_"):
            self.active_mod = "sondaj"; self.active_id = item_id
            self.lbl_talimat.config(text=f"{self.tree.item(item_id, 'text').replace(' (✓)','')}: Haritaya tek tıklayın.")
        elif item_id.startswith("mt_"):
            self.active_mod = "mt"; self.active_id = item_id
            self.lbl_talimat.config(text=f"{self.tree.item(item_id, 'text').replace(' (✓)','')}: Haritaya tek tıklayın.")
        elif item_id.startswith("ss_"):
            self.active_mod = "ss"; self.active_id = item_id
            self.lbl_talimat.config(text=f"{self.tree.item(item_id, 'text').replace(' (✓)','')}: BAŞLANGIÇ ve BİTİŞ noktalarına tıklayın.")
        else:
            self.active_mod = None; self.active_id = None
            self.lbl_talimat.config(text="Lütfen bir alt öğe seçin.")

    def on_map_click(self, coords):
        if not self.active_mod: return

        isim = self.tree.item(self.active_id, 'text').replace(' (✓)','')

        if self.active_mod in ["alan", "sondaj", "mt"]:
            self._drawn_sil(self.active_id)
            
            marker = self._marker_ekle(self.active_mod, coords[0], coords[1], isim)
            self.drawn_objects[self.active_id] = marker
            
            if self.active_mod == "alan":
                self.results["alan"] = coords
            else:
                idx = int(self.active_id.split('_')[1])
                self.results[self.active_mod][idx] = coords
                
            self.isareti_guncelle()

        elif self.active_mod == "ss":
            self.click_count += 1
            if self.click_count == 1:
                self._drawn_sil(self.active_id)
                
                self.start_coord = coords
                m_start = self._marker_ekle("ss", coords[0], coords[1], f"{isim}-Baş")
                self.drawn_objects[self.active_id] = [m_start]
                self.map_widget.canvas.bind("<Motion>", self.update_distance_ui)
            
            elif self.click_count == 2:
                self.map_widget.canvas.unbind("<Motion>")
                mid = self.get_midpoint(self.start_coord, coords)
                
                if self.temp_path: self.temp_path.delete()
                
                paths = self._path_ekle([self.start_coord, coords], color="#00AEEF", width=4, shadow=True)
                self.drawn_objects[self.active_id].extend(paths)
                
                idx = int(self.active_id.split('_')[1])
                self.results["ss"][idx] = [self.start_coord[0], self.start_coord[1], mid[0], mid[1], coords[0], coords[1]]
                
                dist = self.haversine_distance(self.start_coord, coords)
                self.lbl_mesafe.config(text=f"Tamamlandı: {dist:.2f} m")
                self.isareti_guncelle()

    def update_distance_ui(self, event):
        if self.start_coord:
            try:
                curr_coords = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
                dist = self.haversine_distance(self.start_coord, curr_coords)
                self.lbl_mesafe.config(text=f"Mesafe: {dist:.2f} m")
                
                if self.temp_path: self.temp_path.delete()
                self.temp_path = self.map_widget.set_path([self.start_coord, curr_coords], color="yellow", width=2)
            except Exception as exc:
                log_exception("harita_motoru.update_distance_ui", exc_value=exc)

    def kaydet_ve_kapat(self):
        if self.callback:
            self.callback(self.results)
        self.destroy()


class TopluHaritaGorselBindirme(tk.Toplevel):
    def __init__(self, master, img_path, kml_path, map_data=None, initial_results=None, callback=None):
        super().__init__(master)
        self.title("Vaziyet Planı Görüntü Bindirme ile Koordinat Seçimi")
        self.geometry("1450x860")
        self.img_path = img_path
        self.kml_path = kml_path
        self.map_data = map_data or {"sondaj": [], "ss": [], "mt": []}
        self.kml_points = [p for p in kml_koordinatlari_oku(kml_path, max_points=800) if valid_latlon(p.get("lat"), p.get("lon"))]
        self.callback = callback

        self.results = self._sonuclari_kopyala(initial_results or {})
        self.active_id = None
        self.active_mod = None
        self.active_ref_index = None
        self.click_count = 0
        self.ss_start_pixel = None
        self.ss_start_coord = None
        self.coeff = None
        self.georef_refs = []
        self.drawn_objects = {}
        self.ref_artists = []
        self.kml_artists = []
        self.temp_artists = []

        self.alpha_var = tk.DoubleVar(value=0.72)
        self.kml_visible_var = tk.BooleanVar(value=True)

        self.setup_ui()
        self.plot_image()
        if not self.kml_points:
            messagebox.showwarning("Görüntü Bindirme", "KML içinde köşe noktası okunamadı. Referans eşleme yapılamaz.")

    def _sonuclari_kopyala(self, results):
        copied = {"alan": None, "sondaj": {}, "ss": {}, "mt": {}}
        if results.get("alan"):
            copied["alan"] = tuple(results["alan"])
        for group in ("sondaj", "mt"):
            for key, value in (results.get(group) or {}).items():
                copied[group][int(key)] = tuple(value)
        for key, value in (results.get("ss") or {}).items():
            copied["ss"][int(key)] = list(value)
        return copied

    def setup_ui(self):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        self.FigureCanvasTkAgg = FigureCanvasTkAgg
        self.Figure = Figure

        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5, bg="#ccc")
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, width=1040)

        info_frame = tk.Frame(left_frame, bg="#2C3E50", height=42)
        info_frame.pack(fill="x")
        self.lbl_talimat = tk.Label(
            info_frame,
            text="Önce sağdan KML köşesi seçip görselde karşılığını işaretleyin. En az 3 referanstan sonra çalışma noktalarını tıklayın.",
            fg="white",
            bg="#2C3E50",
            font=("Arial", 10, "bold"),
        )
        self.lbl_talimat.pack(side="left", padx=12, pady=10)
        tk.Button(
            info_frame,
            text="Kaydet ve Programa Aktar",
            bg="#27AE60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.kaydet_ve_kapat,
        ).pack(side="right", padx=10, pady=6)

        self.fig = Figure(figsize=(10, 8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=left_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.fig.canvas.mpl_connect("button_press_event", self.on_image_click)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, width=380, minsize=340)

        title = tk.Label(right_frame, text="BİNDİRMELİ SEÇİM", bg="#34495E", fg="white", font=("Arial", 12, "bold"), pady=10)
        title.pack(fill="x")

        settings = ttk.LabelFrame(right_frame, text="Görsel / KML", padding=6)
        settings.pack(fill="x", padx=6, pady=(6, 4))
        ttk.Label(settings, text=os.path.basename(self.img_path), foreground="#566573", wraplength=330).pack(fill="x", pady=(0, 4))
        alpha_row = ttk.Frame(settings)
        alpha_row.pack(fill="x", pady=(2, 2))
        ttk.Label(alpha_row, text="Görsel saydamlığı", width=17).pack(side="left")
        ttk.Scale(alpha_row, from_=0.25, to=1.0, variable=self.alpha_var, command=self.alpha_guncelle).pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(settings, text="KML sınırını göster", variable=self.kml_visible_var, command=self.kml_gorunurluk_guncelle).pack(anchor="w", pady=(2, 0))

        ref_frame = ttk.LabelFrame(right_frame, text="Referans Eşleme", padding=6)
        ref_frame.pack(fill="x", padx=6, pady=4)
        values = [
            f"{idx + 1}: {float(p.get('lat')):.6f}, {float(p.get('lon')):.6f}"
            for idx, p in enumerate(self.kml_points)
        ] or ["KML noktası yok"]
        self.cmb_ref_point = ttk.Combobox(ref_frame, values=values, state="readonly", width=30)
        self.cmb_ref_point.pack(fill="x", pady=(0, 4))
        if self.kml_points:
            self.cmb_ref_point.current(0)
        self.cmb_ref_point.bind("<<ComboboxSelected>>", self.kml_ref_secildi)
        self.lbl_kml_ref = ttk.Label(ref_frame, text="")
        self.lbl_kml_ref.pack(fill="x", pady=(0, 3))

        self.kml_fig = self.Figure(figsize=(3.25, 1.75), dpi=100)
        self.kml_ax = self.kml_fig.add_subplot(111)
        self.kml_preview_canvas = self.FigureCanvasTkAgg(self.kml_fig, master=ref_frame)
        self.kml_preview_canvas.get_tk_widget().pack(fill="x", pady=(0, 4))
        self.kml_preview_canvas.mpl_connect("button_press_event", self.on_kml_preview_click)

        self.lbl_ref_count = ttk.Label(ref_frame, text="")
        self.lbl_ref_count.pack(fill="x", pady=(0, 3))
        tk.Button(ref_frame, text="KML Köşe Referansı Ekle", bg="#D6EAF8", font=("Arial", 9, "bold"), command=self.referans_modu).pack(fill="x", pady=2)
        tk.Button(ref_frame, text="Referansları Temizle", bg="#FADBD8", font=("Arial", 9, "bold"), command=self.referanslari_temizle).pack(fill="x", pady=2)

        button_frame = ttk.Frame(right_frame, padding=6)
        button_frame.pack(side="bottom", fill="x")
        tk.Button(button_frame, text="Seçileni Temizle", bg="#E74C3C", fg="white", font=("Arial", 10, "bold"), command=self.secileni_temizle).pack(fill="x", pady=2)
        tk.Button(button_frame, text="Kaydet ve Programa Aktar", bg="#27AE60", fg="white", font=("Arial", 11, "bold"), pady=8, command=self.kaydet_ve_kapat).pack(fill="x", pady=(5, 2))

        tree_frame = ttk.LabelFrame(right_frame, text="İşaretlenecek Noktalar", padding=4)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", height=13)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self._tree_doldur()

        self.kml_ref_secildi()
        self.georef_count_guncelle()
        self.kml_preview_ciz()

    def _tree_doldur(self):
        self.tree.insert("", "end", "node_alan", text="ÇALIŞMA ALANI", open=True)
        self.tree.insert("node_alan", "end", "alan_0", text="Merkez Koordinat")

        self.tree.insert("", "end", "node_sondaj", text="SONDAJLAR", open=True)
        for i, no in enumerate(self.map_data.get("sondaj", [])):
            self.tree.insert("node_sondaj", "end", f"sondaj_{i}", text=no)

        self.tree.insert("", "end", "node_ss", text="SİSMİK SERİMLER", open=True)
        for i, ad in enumerate(self.map_data.get("ss", [])):
            self.tree.insert("node_ss", "end", f"ss_{i}", text=ad)

        self.tree.insert("", "end", "node_mt", text="MİKROTREMÖR", open=True)
        for i, no in enumerate(self.map_data.get("mt", [])):
            self.tree.insert("node_mt", "end", f"mt_{i}", text=no)

        if self.results.get("alan"):
            self._isareti_isaretle("alan_0")
        for group in ("sondaj", "ss", "mt"):
            for idx in (self.results.get(group) or {}):
                self._isareti_isaretle(f"{group}_{idx}")

    def plot_image(self):
        import matplotlib.image as mpimg
        from PIL import Image

        with Image.open(self.img_path) as pil_img:
            self.image_width, self.image_height = pil_img.size
        img = mpimg.imread(self.img_path)
        self.ax.clear()
        self.ax.set_facecolor("#FFFFFF")
        self.image_artist = self.ax.imshow(img, extent=(0, self.image_width, self.image_height, 0), alpha=self.alpha_var.get())
        self.ax.set_xlim(0, self.image_width)
        self.ax.set_ylim(self.image_height, 0)
        self.ax.axis("off")
        self.canvas.draw_idle()

    def alpha_guncelle(self, value=None):
        if getattr(self, "image_artist", None) is not None:
            self.image_artist.set_alpha(float(self.alpha_var.get()))
            self.canvas.draw_idle()

    def kml_ref_secildi(self, event=None):
        idx = self.cmb_ref_point.current() if hasattr(self, "cmb_ref_point") else -1
        self.active_ref_index = idx if 0 <= idx < len(self.kml_points) else None
        if self.active_ref_index is None:
            self.lbl_kml_ref.config(text="KML köşe noktası seçilemedi.")
        else:
            point = self.kml_points[self.active_ref_index]
            self.lbl_kml_ref.config(text=f"Seçili köşe: {self.active_ref_index + 1} ({float(point.get('lat')):.6f}, {float(point.get('lon')):.6f})")
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

        if not self.kml_points:
            self.kml_ax.text(0.5, 0.5, "KML yok", ha="center", va="center", transform=self.kml_ax.transAxes, fontsize=9)
            self.kml_preview_canvas.draw_idle()
            return

        lons = [float(p["lon"]) for p in self.kml_points]
        lats = [float(p["lat"]) for p in self.kml_points]
        self.kml_ax.plot(lons + [lons[0]], lats + [lats[0]], color="#566573", linewidth=1.2)
        self.kml_ax.scatter(lons, lats, s=25, c="#2471A3", edgecolors="white", linewidths=0.7, zorder=3)

        selected = self.cmb_ref_point.current() if hasattr(self, "cmb_ref_point") else -1
        if 0 <= selected < len(self.kml_points):
            self.kml_ax.scatter([lons[selected]], [lats[selected]], s=82, c="#F1C40F", edgecolors="#7D6608", linewidths=1.3, zorder=5)

        for idx, (lon, lat) in enumerate(zip(lons, lats)):
            if len(lons) <= 80 or idx == selected:
                self.kml_ax.text(lon, lat, str(idx + 1), color="#1B2631", fontsize=6, ha="center", va="center", zorder=6)

        lon_span = max(lons) - min(lons)
        lat_span = max(lats) - min(lats)
        self.kml_ax.set_xlim(min(lons) - (lon_span * 0.08 or 0.0001), max(lons) + (lon_span * 0.08 or 0.0001))
        self.kml_ax.set_ylim(min(lats) - (lat_span * 0.08 or 0.0001), max(lats) + (lat_span * 0.08 or 0.0001))
        self.kml_ax.set_aspect("equal", adjustable="box")
        self.kml_ax.set_title("KML köşesi seç", fontsize=8, pad=2)
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
        self.referans_modu()

    def _nearest_kml_preview_index(self, lon, lat):
        if not self.kml_points:
            return None
        lons = [float(p["lon"]) for p in self.kml_points]
        lats = [float(p["lat"]) for p in self.kml_points]
        lon_span = max(lons) - min(lons) or 1.0
        lat_span = max(lats) - min(lats) or 1.0
        best_idx = None
        best_dist = None
        for idx, point in enumerate(self.kml_points):
            dist = ((float(point["lon"]) - lon) / lon_span) ** 2 + ((float(point["lat"]) - lat) / lat_span) ** 2
            if best_dist is None or dist < best_dist:
                best_idx = idx
                best_dist = dist
        return best_idx

    def referans_modu(self):
        if not self.kml_points:
            messagebox.showwarning("Görüntü Bindirme", "Referans alınacak KML noktası bulunamadı.")
            return
        idx = self.cmb_ref_point.current() if hasattr(self, "cmb_ref_point") else -1
        if idx < 0 or idx >= len(self.kml_points):
            messagebox.showwarning("Görüntü Bindirme", "Referans alınacak KML köşesini seçin.")
            return
        self.active_mod = "georef"
        self.active_id = None
        self.active_ref_index = idx
        point = self.kml_points[idx]
        self.lbl_talimat.config(text=f"{point.get('label', f'KML-{idx + 1}')} köşesinin vaziyet planındaki karşılığını tıklayın.")

    def referanslari_temizle(self):
        self.georef_refs = []
        self.coeff = None
        self._artist_list_sil(self.ref_artists)
        self.ref_artists = []
        self._artist_list_sil(self.kml_artists)
        self.kml_artists = []
        self._tum_nokta_cizimlerini_sil()
        self.georef_count_guncelle()
        self.lbl_talimat.config(text="Referanslar temizlendi. En az 3 KML köşesi eşleyin.")
        self.canvas.draw_idle()

    def georef_count_guncelle(self):
        if hasattr(self, "lbl_ref_count"):
            durum = "hazır" if len(self.georef_refs) >= 3 else "bekliyor"
            self.lbl_ref_count.config(text=f"Referans: {len(self.georef_refs)} / en az 3 ({durum})")

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
        self.referanslari_ciz()
        self.georef_count_guncelle()
        try:
            self.coeff = affine_from_refs(self.georef_refs)
            self.kml_siniri_ciz()
            self.sonuclari_ciz()
            self.lbl_talimat.config(text=f"{label} referansı eklendi. KML sınırı bindirildi, artık noktaları işaretleyebilirsiniz.")
        except Exception:
            self.coeff = None
            self.lbl_talimat.config(text=f"{label} referansı eklendi. Nokta seçimi için en az 3 referans gerekir.")
        self.canvas.draw_idle()

    def referanslari_ciz(self):
        self._artist_list_sil(self.ref_artists)
        self.ref_artists = []
        for idx, ref in enumerate(self.georef_refs, start=1):
            pixel = ref.get("pixel", {})
            try:
                x, y = float(pixel["x"]), float(pixel["y"])
            except Exception:
                continue
            marker, = self.ax.plot(x, y, marker="x", color="#F1C40F", markersize=10, markeredgewidth=2.2, zorder=30)
            text = self.ax.text(
                x + 8,
                y + 8,
                f"REF-{idx}",
                color="#7D6608",
                fontsize=8,
                fontweight="bold",
                bbox=dict(facecolor="white", alpha=0.82, edgecolor="#F1C40F", pad=2),
                zorder=31,
            )
            self.ref_artists.extend([marker, text])

    def _coeff_al(self):
        if self.coeff is not None:
            return self.coeff
        try:
            self.coeff = affine_from_refs(self.georef_refs)
            return self.coeff
        except Exception as exc:
            messagebox.showwarning("Görüntü Bindirme", str(exc))
            return None

    def kml_siniri_ciz(self):
        self._artist_list_sil(self.kml_artists)
        self.kml_artists = []
        coeff = self._coeff_al()
        if coeff is None or not self.kml_points:
            return
        pts = []
        for point in self.kml_points:
            try:
                pts.append(coord_to_pixel(coeff, point.get("lat"), point.get("lon")))
            except Exception:
                continue
        if len(pts) < 2:
            return
        closed = pts + [pts[0]]
        xs = [p[0] for p in closed]
        ys = [p[1] for p in closed]
        line, = self.ax.plot(xs, ys, color="#F39C12", linewidth=2.2, zorder=18)
        shadow, = self.ax.plot(xs, ys, color="white", linewidth=4.5, alpha=0.75, zorder=17)
        self.kml_artists.extend([shadow, line])
        for idx, (x, y) in enumerate(pts[:80], start=1):
            dot, = self.ax.plot(x, y, marker="o", markersize=3.5, color="#F39C12", markeredgecolor="white", zorder=19)
            self.kml_artists.append(dot)
        self.kml_gorunurluk_guncelle(redraw=False)

    def kml_gorunurluk_guncelle(self, redraw=True):
        visible = bool(self.kml_visible_var.get())
        for artist in self.kml_artists:
            try:
                artist.set_visible(visible)
            except Exception:
                pass
        if redraw:
            self.canvas.draw_idle()

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        self.click_count = 0
        self.ss_start_pixel = None
        self.ss_start_coord = None
        self._temp_sil()
        if item_id.startswith("alan_"):
            self.active_mod = "alan"
            self.active_id = item_id
            self.lbl_talimat.config(text="MERKEZ KOORDİNAT: Görsel üzerinde tek tıklayın.")
        elif item_id.startswith("sondaj_"):
            self.active_mod = "sondaj"
            self.active_id = item_id
            self.lbl_talimat.config(text=f"{self._item_text(item_id)}: Görsel üzerinde tek tıklayın.")
        elif item_id.startswith("mt_"):
            self.active_mod = "mt"
            self.active_id = item_id
            self.lbl_talimat.config(text=f"{self._item_text(item_id)}: Görsel üzerinde tek tıklayın.")
        elif item_id.startswith("ss_"):
            self.active_mod = "ss"
            self.active_id = item_id
            self.lbl_talimat.config(text=f"{self._item_text(item_id)}: Başlangıç ve bitiş noktalarına tıklayın.")
        else:
            self.active_mod = None
            self.active_id = None
            self.lbl_talimat.config(text="Bir alt nokta seçin veya referans eşleyin.")

    def on_image_click(self, event):
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return
        x, y = float(event.xdata), float(event.ydata)
        if self.active_mod == "georef":
            self.georef_ref_ekle(x, y)
            return
        if not self.active_mod:
            return

        coeff = self._coeff_al()
        if coeff is None:
            return
        try:
            lat, lon = pixel_to_coord(coeff, x, y)
        except Exception as exc:
            messagebox.showwarning("Görüntü Bindirme", str(exc))
            return

        isim = self._item_text(self.active_id)
        if self.active_mod in ("alan", "sondaj", "mt"):
            self._drawn_sil(self.active_id)
            self._tek_nokta_ciz(self.active_mod, self.active_id, x, y, isim)
            if self.active_mod == "alan":
                self.results["alan"] = (lat, lon)
            else:
                idx = int(self.active_id.split("_")[1])
                self.results[self.active_mod][idx] = (lat, lon)
            self._isareti_isaretle(self.active_id)
            self.lbl_talimat.config(text=f"{isim} koordinatı işaretlendi.")

        elif self.active_mod == "ss":
            self.click_count += 1
            if self.click_count == 1:
                self._drawn_sil(self.active_id)
                self._temp_sil()
                self.ss_start_pixel = (x, y)
                self.ss_start_coord = (lat, lon)
                marker, = self.ax.plot(x, y, marker="s", markersize=8, color="#00AEEF", markeredgecolor="white", zorder=25)
                label = self.ax.text(x + 10, y - 10, f"{isim}-Baş", color="#006C8F", fontsize=9, fontweight="bold", bbox=dict(facecolor="white", alpha=0.78, edgecolor="#00AEEF", pad=2), zorder=26)
                self.temp_artists = [marker, label]
                self.lbl_talimat.config(text=f"{isim}: Şimdi bitiş noktasını tıklayın.")
            elif self.click_count == 2:
                start_lat, start_lon = self.ss_start_coord
                mid = ((start_lat + lat) / 2, (start_lon + lon) / 2)
                idx = int(self.active_id.split("_")[1])
                self.results["ss"][idx] = [start_lat, start_lon, mid[0], mid[1], lat, lon]
                self._temp_sil()
                self._ss_ciz(self.active_id, self.ss_start_pixel[0], self.ss_start_pixel[1], x, y, isim)
                self._isareti_isaretle(self.active_id)
                self.click_count = 0
                self.ss_start_pixel = None
                self.ss_start_coord = None
                self.lbl_talimat.config(text=f"{isim} başlangıç ve bitiş koordinatı işaretlendi.")
        self.canvas.draw_idle()

    def _item_text(self, item_id, default=""):
        try:
            return self.tree.item(item_id, "text").replace(" (✓)", "")
        except Exception:
            return default

    def _isareti_isaretle(self, item_id):
        try:
            if not self.tree.exists(item_id):
                return
            text = self.tree.item(item_id, "text")
            if not text.endswith(" (✓)"):
                self.tree.item(item_id, text=text + " (✓)")
        except Exception:
            pass

    def _isareti_temizle(self, item_id):
        try:
            text = self.tree.item(item_id, "text")
            if text.endswith(" (✓)"):
                self.tree.item(item_id, text=text[:-4])
        except Exception:
            pass

    def _renk(self, mod):
        return {
            "alan": ("#F1C40F", "#7D6608"),
            "sondaj": ("#E74C3C", "#922B21"),
            "ss": ("#00AEEF", "#006C8F"),
            "mt": ("#2ECC71", "#0B5345"),
        }.get(mod, ("#34495E", "#17202A"))

    def _tek_nokta_ciz(self, mod, item_id, x, y, text):
        fill, edge = self._renk(mod)
        marker, = self.ax.plot(x, y, marker="o" if mod != "mt" else "s", markersize=9, color=fill, markeredgecolor="white", markeredgewidth=1.2, zorder=24)
        label = self.ax.text(x + 10, y - 10, text, color=edge, fontsize=10, fontweight="bold", bbox=dict(facecolor="white", alpha=0.78, edgecolor=fill, pad=2), zorder=25)
        self.drawn_objects[item_id] = [marker, label]

    def _ss_ciz(self, item_id, x1, y1, x2, y2, text):
        line_shadow, = self.ax.plot([x1, x2], [y1, y2], color="white", linewidth=5.0, alpha=0.82, zorder=22)
        line, = self.ax.plot([x1, x2], [y1, y2], color="#00AEEF", linewidth=2.6, zorder=23)
        start, = self.ax.plot(x1, y1, marker="s", markersize=9, color="#00AEEF", markeredgecolor="white", markeredgewidth=1.2, zorder=24)
        label = self.ax.text(x1 + 10, y1 - 10, text, color="#006C8F", fontsize=10, fontweight="bold", bbox=dict(facecolor="white", alpha=0.78, edgecolor="#00AEEF", pad=2), zorder=25)
        self.drawn_objects[item_id] = [line_shadow, line, start, label]

    def sonuclari_ciz(self):
        coeff = self._coeff_al()
        if coeff is None:
            return
        self._tum_nokta_cizimlerini_sil()

        alan = self.results.get("alan")
        if alan:
            try:
                x, y = coord_to_pixel(coeff, alan[0], alan[1])
                self._tek_nokta_ciz("alan", "alan_0", x, y, "Merkez Koordinat")
            except Exception:
                pass

        for group in ("sondaj", "mt"):
            for idx, coord in (self.results.get(group) or {}).items():
                try:
                    item_id = f"{group}_{idx}"
                    x, y = coord_to_pixel(coeff, coord[0], coord[1])
                    self._tek_nokta_ciz(group, item_id, x, y, self._item_text(item_id, f"{group.upper()}-{idx + 1}"))
                except Exception:
                    continue

        for idx, coords in (self.results.get("ss") or {}).items():
            if len(coords) < 6:
                continue
            try:
                item_id = f"ss_{idx}"
                x1, y1 = coord_to_pixel(coeff, coords[0], coords[1])
                x2, y2 = coord_to_pixel(coeff, coords[4], coords[5])
                self._ss_ciz(item_id, x1, y1, x2, y2, self._item_text(item_id, f"SS-{idx + 1}"))
            except Exception:
                continue

    def _artist_list_sil(self, artists):
        for artist in artists:
            try:
                artist.remove()
            except Exception:
                pass

    def _drawn_sil(self, item_id):
        artists = self.drawn_objects.pop(item_id, [])
        self._artist_list_sil(artists)

    def _tum_nokta_cizimlerini_sil(self):
        for item_id in list(self.drawn_objects.keys()):
            self._drawn_sil(item_id)
        self._temp_sil()

    def _temp_sil(self):
        self._artist_list_sil(self.temp_artists)
        self.temp_artists = []

    def secileni_temizle(self):
        selected = self.tree.selection()
        item_id = selected[0] if selected else self.active_id
        if not item_id or "_" not in item_id:
            messagebox.showinfo("Görüntü Bindirme", "Temizlemek için bir çalışma noktası seçin.")
            return
        if item_id.startswith("alan_"):
            self.results["alan"] = None
        elif item_id.startswith("sondaj_"):
            self.results["sondaj"].pop(int(item_id.split("_")[1]), None)
        elif item_id.startswith("mt_"):
            self.results["mt"].pop(int(item_id.split("_")[1]), None)
        elif item_id.startswith("ss_"):
            self.results["ss"].pop(int(item_id.split("_")[1]), None)
        else:
            return
        self._drawn_sil(item_id)
        self._isareti_temizle(item_id)
        self.lbl_talimat.config(text=f"{self._item_text(item_id)} temizlendi.")
        self.canvas.draw_idle()

    def kaydet_ve_kapat(self):
        if self.callback:
            self.callback(self.results)
        self.destroy()
