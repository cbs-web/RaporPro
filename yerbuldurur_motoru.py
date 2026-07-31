# Dosya: RaporPro/yerbuldurur_motoru.py
import tkinter as tk
from tkinter import messagebox, filedialog
import tkintermapview
import xml.etree.ElementTree as ET
from PIL import ImageGrab
import os

class YerbuldururMotoru(tk.Toplevel):
    def __init__(
        self,
        master,
        kml_path,
        saved_state=None,
        save_callback=None,
        close_callback=None,
    ):
        super().__init__(master)
        self.title("Yerbuldurur Haritası Oluşturucu (Hassas Zoom & KML Destekli)")
        self.geometry("1100x800")
        self.kml_path = kml_path
        self.saved_state = saved_state or {}
        self.save_callback = save_callback
        self.close_callback = close_callback
        self._exported = False
        self.protocol("WM_DELETE_WINDOW", self._kapat)
        
        self.setup_ui()
        self.load_kml_and_state()

    def setup_ui(self):
        # Üst Kontrol Paneli
        top_frame = tk.Frame(self, bg="#2C3E50", height=50)
        top_frame.pack(fill="x")
        
        lbl_zoom = tk.Label(top_frame, text="🔍 Hassas Zoom:", fg="white", bg="#2C3E50", font=("Arial", 11, "bold"))
        lbl_zoom.pack(side="left", padx=(15, 5), pady=15)
        
        # HASSAS ZOOM ÇUBUĞU (SLIDER)
        self.zoom_var = tk.DoubleVar()
        self.zoom_slider = tk.Scale(top_frame, variable=self.zoom_var, from_=5.0, to=22.0, resolution=0.1, 
                                    orient=tk.HORIZONTAL, bg="#2C3E50", fg="white", length=250,
                                    highlightthickness=0, troughcolor="#34495E", activebackground="#E67E22",
                                    command=self.on_slider_zoom)
        self.zoom_slider.pack(side="left", padx=5, pady=5)
        
        lbl_info = tk.Label(top_frame, text="(Fare tekerleği veya kaydırma çubuğunu kullanın)", fg="#BDC3C7", bg="#2C3E50", font=("Arial", 9))
        lbl_info.pack(side="left", padx=10, pady=15)
        
        btn_save = tk.Button(top_frame, text="📸 EKRANI KAYDET VE WORD'E AKTAR", bg="#27AE60", fg="white", font=("Arial", 11, "bold"), command=self.save_and_export)
        btn_save.pack(side="right", padx=15, pady=10)
        
        # Harita Widget'ı
        self.map_widget = tkintermapview.TkinterMapView(self, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}", max_zoom=22)
        
        # Fare tekerleği ile zoom yapıldığında slider'ı senkronize et
        self.map_widget.canvas.bind("<MouseWheel>", self.sync_slider, add="+")
        self.map_widget.canvas.bind("<Button-4>", self.sync_slider, add="+") # Linux scroll up
        self.map_widget.canvas.bind("<Button-5>", self.sync_slider, add="+") # Linux scroll down

    def sync_slider(self, event):
        # Haritanın zoom verisi güncellendikten hemen sonra slider'ı ayarla
        self.after(50, lambda: self.zoom_var.set(round(self.map_widget.zoom, 1)))

    def on_slider_zoom(self, val):
        if hasattr(self, 'map_widget'):
            self.map_widget.set_zoom(float(val))

    def load_kml_and_state(self):
        try:
            # KML'den koordinatları çek
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
                # 1. Kırmızı Dolgulu, Siyah Kenarlı KML Poligonunu Çiz
                self.map_widget.set_polygon(path, outline_color="black", fill_color="red", border_width=3)
                
                # 2. Matematiksel Olarak En Kuzey Noktayı Bul (Enlemi / Y'si en büyük olan nokta)
                en_kuzey_nokta = max(path, key=lambda p: p[0])
                
                # 3. O noktaya işaretçi bırak ve YAZIYI BEYAZ YAP
                self.map_widget.set_marker(en_kuzey_nokta[0], en_kuzey_nokta[1], text="ÇALIŞMA ALANI", text_color="white", marker_color_circle="black", marker_color_outside="#E74C3C")
                
                # 4. Hafızadaki zoom ayarı varsa onu yükle, yoksa tam ortala
                if self.saved_state and "zoom" in self.saved_state:
                    self.map_widget.set_position(self.saved_state["lat"], self.saved_state["lon"])
                    self.zoom_var.set(self.saved_state["zoom"])
                    self.map_widget.set_zoom(self.saved_state["zoom"])
                else:
                    lats = [p[0] for p in path]
                    lons = [p[1] for p in path]
                    self.map_widget.set_position(sum(lats)/len(lats), sum(lons)/len(lons))
                    self.zoom_var.set(15.0)
                    self.map_widget.set_zoom(15.0)
                    
        except Exception as e:
            messagebox.showerror("Hata", f"KML Okunurken Hata Oluştu:\n{str(e)}")

    def save_and_export(self):
        # İşlemlerin bitmesini bekle (Harita pikselleri tam otursun)
        self.update_idletasks()
        self.update()
        
        # Sadece harita widget'ının ekran koordinatlarını al (Üst barı çekmez)
        x = self.map_widget.winfo_rootx()
        y = self.map_widget.winfo_rooty()
        w = self.map_widget.winfo_width()
        h = self.map_widget.winfo_height()
        
        try:
            # Ekran Görüntüsü Al (Screenshot)
            img = ImageGrab.grab(bbox=(x, y, x+w, y+h))
            
            path = filedialog.asksaveasfilename(
                defaultextension=".jpg", 
                initialfile="Yerbuldurur_Haritasi.jpg",
                filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")]
            )
            
            if path:
                img.save(path, quality=95)
                
                # O anki durumu (zoom ve konum) hafıza için kaydet
                state = {
                    "zoom": self.map_widget.zoom,
                    "lat": self.map_widget.get_position()[0],
                    "lon": self.map_widget.get_position()[1],
                    "img_path": path
                }
                
                if self.save_callback:
                    self.save_callback(state, path)
                
                messagebox.showinfo("Başarılı", "Yerbuldurur Haritası başarıyla projeye kaydedildi ve Rapor sekmesine aktarıldı!")
                self._exported = True
                self.destroy()
                
        except Exception as e:
            messagebox.showerror("Hata", f"Ekran görüntüsü alınırken bir sorun oluştu:\n{str(e)}")

    def _kapat(self):
        if self.close_callback:
            self.close_callback(self._exported)
        self.destroy()
