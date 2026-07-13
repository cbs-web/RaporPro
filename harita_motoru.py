# Dosya: RaporPro/harita_motoru.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkintermapview
import tkintermapview.map_widget as tkintermapview_map_widget
import math
import os

from harita_ayarlari import hgm_ortofoto_url_yukle
from harita_referans import affine_from_refs, coord_to_pixel, kml_koordinatlari_oku, pixel_to_coord, valid_latlon
from performans import log_exception

DEFAULT_TILE_SERVER = "Google Uydu"
GOOGLE_SATELLITE_TILE_URL = "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}"
HGM_ORTOFOTO_TILE_URL = hgm_ortofoto_url_yukle()
HGM_ORTOFOTO_URL_MARKER = "atlas.harita.gov.tr/webservis/ortofoto/"

TILE_SERVERS = {
    "Google Uydu": {"url": GOOGLE_SATELLITE_TILE_URL, "max_zoom": 22},
}
if HGM_ORTOFOTO_TILE_URL:
    TILE_SERVERS["HGM Ortofoto"] = {"url": HGM_ORTOFOTO_TILE_URL, "max_zoom": 22}


def ensure_hgm_tile_headers():
    requests_module = getattr(tkintermapview_map_widget, "requests", None)
    if requests_module is None or getattr(requests_module.get, "_raporpro_hgm_headers", False):
        return
    original_get = requests_module.get

    def get_with_hgm_headers(url, *args, **kwargs):
        if isinstance(url, str) and HGM_ORTOFOTO_URL_MARKER in url:
            headers = dict(kwargs.get("headers") or {})
            headers["Referer"] = "https://atlas.harita.gov.tr/"
            kwargs["headers"] = headers
        return original_get(url, *args, **kwargs)

    get_with_hgm_headers._raporpro_hgm_headers = True
    get_with_hgm_headers._raporpro_original_get = original_get
    requests_module.get = get_with_hgm_headers


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
        tile_frame = tk.Frame(info_frame, bg="#34495E")
        tile_frame.pack(side="right", padx=(8, 12), pady=7)
        tk.Label(tile_frame, text="Altlık", fg="white", bg="#34495E", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 5))
        self.tile_server_var = tk.StringVar(value=DEFAULT_TILE_SERVER)
        self.cmb_tile_server = ttk.Combobox(
            tile_frame,
            textvariable=self.tile_server_var,
            values=list(TILE_SERVERS.keys()),
            state="readonly",
            width=14,
        )
        self.cmb_tile_server.pack(side="left")
        self.cmb_tile_server.bind("<<ComboboxSelected>>", self.altlik_degistir)
        self.lbl_mesafe = tk.Label(info_frame, text="", fg="#F1C40F", bg="#34495E", font=("Arial", 11, "bold"))
        self.lbl_mesafe.pack(side="right", padx=15, pady=10)

        self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.altlik_uygula(DEFAULT_TILE_SERVER, show_status=False)
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

    def altlik_uygula(self, name, show_status=True):
        provider = TILE_SERVERS.get(name) or TILE_SERVERS[DEFAULT_TILE_SERVER]
        url = provider.get("url", "")
        if not url:
            name = DEFAULT_TILE_SERVER
            provider = TILE_SERVERS[DEFAULT_TILE_SERVER]
            url = provider["url"]
        try:
            if HGM_ORTOFOTO_URL_MARKER in url:
                ensure_hgm_tile_headers()
            self.map_widget.set_tile_server(url, max_zoom=provider.get("max_zoom", 19))
            self.active_tile_server = name
            if hasattr(self, "tile_server_var"):
                self.tile_server_var.set(name)
            if show_status:
                self.lbl_talimat.config(text=f"{name} altlığı seçildi. Harita üzerinde işaretlemeye devam edebilirsiniz.")
        except Exception as exc:
            log_exception("map.tile_server", exc_value=exc)
            if name != DEFAULT_TILE_SERVER:
                messagebox.showwarning(
                    "Harita Altlığı",
                    f"{name} altlığı uygulanamadı. Google Uydu altlığına dönülüyor.",
                )
                self.altlik_uygula(DEFAULT_TILE_SERVER, show_status=show_status)
            else:
                messagebox.showerror("Harita Altlığı", f"Harita altlığı uygulanamadı:\n{exc}")

    def altlik_degistir(self, event=None):
        self.altlik_uygula(self.tile_server_var.get())

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

from harita_gorsel_bindirme import TopluHaritaGorselBindirme
