import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os
from PIL import Image

# -----------------------------------------------------------------------------
# 1. AYARLAR VE SABİTLER
# -----------------------------------------------------------------------------

# Sayfa Yapısı (A4 Dikey)
FIG_W_INCH = 8.27
FIG_H_INCH = 11.69
DPI = 300

# Normalize X Sınırları (Strater'dan alınan veriler)
X_BOUNDS = [
    0.0000, 0.0262, 0.0638, 0.1014, 0.1390, 0.1766, 0.2142, 0.2518,
    0.2894, 0.3270, 0.3645, 0.4397, 0.5149, 0.5518, 0.5901, 0.6277,
    0.6652, 0.7028, 0.7404, 0.8149, 0.9652, 1.0000
]

# Kolon Tanımları (Başlık Metinleri ve İndeksler)
# Format: (Key, Start_Index, End_Index, Title_Text, Rotate_Header?)
COL_DEFS = [
    ("derinlik_sol",      0, 1, "Derinlik\n(m)", False),
    ("muhafaza",          1, 2, "Muhafaza\nBorusu", True),
    ("kuyu_ici",          2, 3, "Kuyu İçi\nDeneyler", True),
    ("ornek_turu",        3, 4, "Örnek\nTürü", True),
    ("ornek_aralik",      4, 5, "Örnek\nAralığı", True),
    ("ornek_no",          5, 6, "Örnek\nNo", True),
    ("spt_0_15",          6, 7, "0-15", False),
    ("spt_15_30",         7, 8, "15-30", False),
    ("spt_30_45",         8, 9, "30-45", False),
    ("spt_N",             9, 10, "N\n(Darbe)", False),
    ("pmt_Em",            10, 11, "Em\n(kg/cm²)", False),
    ("pmt_Pl",            11, 12, "Pl\n(kg/cm²)", False),
    ("kaya_TCR",          12, 13, "TCR\n(%)", False),
    ("kaya_SCR",          13, 14, "SCR\n(%)", False),
    ("kaya_RQD",          14, 15, "RQD\n(%)", False),
    ("kaya_ayrisma",      15, 16, "Ayrışma\nDerecesi", True),
    ("kaya_catlak",       16, 17, "Çatlak\nFrekansı", True),
    ("kaya_dayanim",      17, 18, "Dayanım\nİndeksi", True),
    ("zemin_profili",     18, 19, "Zemin\nProfili", False),
    ("zemin_tanim",       19, 20, "Litolojik Tanımlama", False),
    ("derinlik_sag",      20, 21, "Derinlik\n(m)", False),
]

# Y Blokları (Normalize 0-1, 0=Üst, 1=Alt)
Y_BLOCKS = {
    "meta_top":      0.0000,
    "meta_bottom":   0.1500, # Künye alanı (biraz daralttım sığsın diye)
    "colhdr_top":    0.1500,
    "colhdr_bottom": 0.2300, # Başlık bandı
    "data_top":      0.2300,
    "data_bottom":   0.9000, # Veri alanı
    "footer_top":    0.9000,
    "footer_bottom": 0.9800, # Alt bilgi / Legend
    "page_bottom":   1.0000
}

# Max Derinlik
MAX_DEPTH = 15.0

# -----------------------------------------------------------------------------
# 2. YARDIMCI FONKSİYONLAR
# -----------------------------------------------------------------------------

def map_y(depth):
    """Derinliği (m) sayfadaki Y koordinatına çevirir."""
    # Veri alanı: data_top (0m) -> data_bottom (15m)
    range_span = Y_BLOCKS["data_bottom"] - Y_BLOCKS["data_top"]
    return Y_BLOCKS["data_top"] + (depth / MAX_DEPTH) * range_span

def get_x_center(col_idx_start, col_idx_end):
    """Verilen X_BOUNDS indeksleri arasındaki orta noktayı döner."""
    return (X_BOUNDS[col_idx_start] + X_BOUNDS[col_idx_end]) / 2

# -----------------------------------------------------------------------------
# 3. ÇİZİM MOTORU
# -----------------------------------------------------------------------------

def draw_strater_log():
    # Figür oluştur (A4)
    fig = plt.figure(figsize=(FIG_W_INCH, FIG_H_INCH), dpi=DPI)
    
    # Tüm sayfayı kaplayan tek bir eksen (0,0 -> 1,1)
    # Y eksenini ters çeviriyoruz (0 üstte, 1 altta) ki koordinatlarla çalışmak kolay olsun
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0) # TERS Y EKSENİ (Strater mantığı)
    ax.axis("off") # Eksen çizgilerini kapat

    # --- A) HEADER & GRID ÇİZİMİ ---
    
    # 1. Ana Bölge Çizgileri (Yatay)
    for key in ["meta_bottom", "colhdr_bottom", "data_bottom", "footer_bottom"]:
        y = Y_BLOCKS[key]
        ax.hlines(y, 0, 1, colors="black", linewidth=1)

    # 2. Kolon Çizgileri (Dikey) - Sadece Header ve Data bölgesinde
    top_line = Y_BLOCKS["colhdr_top"]
    btm_line = Y_BLOCKS["data_bottom"]
    
    for x in X_BOUNDS:
        ax.vlines(x, top_line, btm_line, colors="black", linewidth=0.8)

    # 3. Başlık Yazıları
    for key, s_idx, e_idx, title, rotate in COL_DEFS:
        cx = get_x_center(s_idx, e_idx)
        cy = (Y_BLOCKS["colhdr_top"] + Y_BLOCKS["colhdr_bottom"]) / 2
        
        rot_deg = 90 if rotate else 0
        ax.text(cx, cy, title, ha="center", va="center", rotation=rot_deg, 
                fontsize=7, fontweight="bold", wrap=True)

    # 4. Üst Grup Başlıkları (SPT, PMT, KAYA)
    # Bunlar için özel yatay çizgiler ve metinler
    def draw_group_header(text, s_idx, e_idx):
        x1 = X_BOUNDS[s_idx]
        x2 = X_BOUNDS[e_idx]
        y_mid = Y_BLOCKS["colhdr_top"] - 0.015 # Biraz yukarıda
        # Grup çizgisi
        ax.hlines(Y_BLOCKS["colhdr_top"], x1, x2, colors="black", linewidth=1)
        # Grup Adı
        ax.text((x1+x2)/2, (Y_BLOCKS["colhdr_top"] + Y_BLOCKS["meta_bottom"])/2, 
                text, ha="center", va="center", fontsize=8, fontweight="bold")

    # SPT Grubu (idx 6-10)
    draw_group_header("Standart Penetrasyon Testi (SPT)", 6, 10)
    # PMT Grubu (idx 10-12)
    draw_group_header("Presiyometre Deneyi", 10, 12)
    # Kaya Grubu (idx 12-18)
    draw_group_header("Kaya Mekaniği Laboratuvar Deneyleri", 12, 18)

    # --- B) KÜNYE (META) BİLGİLERİ ---
    # Sol üst logo/firma alanı
    ax.text(0.1, 0.05, "UB ZEMİN MÜHENDİSLİK\nSONDAJ LOGU", fontsize=14, fontweight="bold", ha="left")
    
    # Sağ üst proje detayları (Örnek)
    meta_x = 0.6
    meta_y = 0.04
    meta_info = [
        ("Proje Adı:", "Çanakkale Merkez Zemin Etüdü"),
        ("Sondaj No:", "SK-1"),
        ("Derinlik:", "15.00 m"),
        ("Koordinat:", "Y: 462845 - X: 4419778"),
        ("Tarih:", "28.10.2025")
    ]
    for k, v in meta_info:
        ax.text(meta_x, meta_y, f"{k} {v}", fontsize=9, ha="left")
        meta_y += 0.02

    # --- C) VERİ İŞLEME (DATA) ---
    
    # 1. Derinlik Skalası (Sol ve Sağ)
    # Her 1 metrede bir çizgi, her 0.5te bir ince çizgi
    for d in np.arange(0, MAX_DEPTH + 0.1, 0.5):
        y = map_y(d)
        # Ana derinlik çizgileri (Data alanı boyunca)
        lw = 0.5 if d % 1 == 0 else 0.2
        color = "black" if d % 1 == 0 else "gray"
        
        # Sadece Zemin Profili dışındaki alanlara grid atalım (Opsiyonel, burada boydan boya atıyorum)
        ax.hlines(y, 0, 1, colors=color, linewidth=lw, linestyle=":" if d%1!=0 else "-")
        
        # Rakamlar
        if d % 1 == 0:
            # Sol Derinlik
            ax.text(get_x_center(0,1), y, f"{int(d)}", ha="center", va="center", fontsize=8)
            # Sağ Derinlik
            ax.text(get_x_center(20,21), y, f"{int(d)}", ha="center", va="center", fontsize=8)

    # 2. Örnek Veriler (PDF Referanslı)
    
    # --- SPT Verileri ---
    spt_data = [
        (1.5, "2", "3", "4", "7"),
        (3.0, "4", "5", "6", "11"),
        (4.5, "5", "8", "9", "17"),
        (6.0, "50/1", "-", "-", "Ref"), # Refü örneği
        (7.5, "R", "", "", "Ref"),      # R örneği
    ]
    
    for depth, v1, v2, v3, n in spt_data:
        y = map_y(depth)
        # SPT kolon indeksleri: 6, 7, 8, 9
        ax.text(get_x_center(6,7), y, v1, ha="center", va="center", fontsize=7)
        ax.text(get_x_center(7,8), y, v2, ha="center", va="center", fontsize=7)
        ax.text(get_x_center(8,9), y, v3, ha="center", va="center", fontsize=7)
        # N değeri kalın
        ax.text(get_x_center(9,10), y, n, ha="center", va="center", fontsize=8, fontweight="bold", color="red")
        
        # Numune işareti
        ax.text(get_x_center(3,4), y, "SPT", ha="center", va="center", fontsize=6, rotation=90)
        ax.text(get_x_center(5,6), y, f"DS-{int(depth/1.5)}", ha="center", va="center", fontsize=6)

    # --- PMT Verileri ---
    pmt_data = [
        (2.0, "150", "17.02"),
        (5.0, "189", "24.33"),
        (9.0, "259", "21.64"),
        (12.0, "2189", "22.76")
    ]
    for depth, em, pl in pmt_data:
        y = map_y(depth)
        # PMT kolon indeksleri: 10, 11
        ax.text(get_x_center(10,11), y, em, ha="center", va="center", fontsize=7)
        ax.text(get_x_center(11,12), y, pl, ha="center", va="center", fontsize=7)

    # --- Kaya Verileri (TCR/SCR/RQD) ---
    rock_data = [
        (10.0, 11.5, "40", "35", "10"),
        (11.5, 13.0, "66", "66", "25"),
        (13.0, 14.5, "62", "62", "30"),
        (14.5, 15.0, "66", "66", "35")
    ]
    for d_top, d_bot, tcr, scr, rqd in rock_data:
        y_mid = (map_y(d_top) + map_y(d_bot)) / 2
        # Kaya kolonları: 12, 13, 14
        ax.text(get_x_center(12,13), y_mid, tcr, ha="center", va="center", fontsize=7)
        ax.text(get_x_center(13,14), y_mid, scr, ha="center", va="center", fontsize=7)
        ax.text(get_x_center(14,15), y_mid, rqd, ha="center", va="center", fontsize=7)
        
        # Numune Kutusu (Karot)
        y1 = map_y(d_top)
        y2 = map_y(d_bot)
        # Örnek Türü kolonu (3) içine kutu çiz
        rect = patches.Rectangle((X_BOUNDS[3]+0.005, y1), (X_BOUNDS[4]-X_BOUNDS[3])-0.01, y2-y1, 
                                 facecolor="black", edgecolor="black")
        ax.add_patch(rect)

    # --- Litoloji Tanımları ve Kutuları ---
    lithology = [
        (0.0, 1.5, "NEBATİ TOPRAK: Kahverengi, kök parçalı.", "brown"),
        (1.5, 5.0, "YAPAY DOLGU: Tuğla kırıntılı, siltli kumlu çakıl.", "gray"),
        (5.0, 9.5, "KUMLU KİL: Bej renkli, orta katı-katı, düşük plastisiteli.", "orange"),
        (9.5, 15.0, "KİREÇTAŞI: Sarımsı beyaz, orta ayrışmış, çatlaklı kaya ortamı.", "yellow")
    ]
    
    col_prof_idx = 18 # Zemin Profili Kolonu
    col_desc_idx = 19 # Tanımlama Kolonu
    
    for top, bot, desc, color in lithology:
        y1 = map_y(top)
        y2 = map_y(bot)
        h = y2 - y1
        
        # 1. Profil Kutusu (Renkli)
        x_prof_start = X_BOUNDS[col_prof_idx]
        w_prof = X_BOUNDS[col_prof_idx+1] - x_prof_start
        
        rect = patches.Rectangle((x_prof_start, y1), w_prof, h, 
                                 linewidth=0.5, edgecolor="black", facecolor=color, alpha=0.3)
        ax.add_patch(rect)
        
        # 2. Tanımlama Metni
        # Metni dikeyde ortala, soldan hizala
        x_desc = X_BOUNDS[col_desc_idx] + 0.005
        ax.text(x_desc, y1 + 0.015, desc, ha="left", va="top", fontsize=7, wrap=True)
        
        # 3. Alt Çizgi
        ax.hlines(y2, X_BOUNDS[col_prof_idx], X_BOUNDS[col_desc_idx+1], colors="black", linewidth=0.8)

    # --- D) FOOTER (Legend vb.) ---
    # Basit bir açıklama kutusu
    fx = 0.05
    fy = Y_BLOCKS["footer_top"] + 0.02
    ax.text(fx, fy, "AÇIKLAMALAR:\nGW: Yeraltı Suyu Seviyesi\nCR: Karot Yüzdesi\nRQD: Kaya Kalite İndeksi", 
            fontsize=8, va="top")

    # 4. KAYDET (PNG -> JPEG)
    tmp_png = "log_tmp.png"
    plt.savefig(tmp_png, dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    
    # Pillow ile JPEG Dönüşümü (Quality kontrolü için)
    try:
        with Image.open(tmp_png) as img:
            rgb_im = img.convert("RGB")
            rgb_im.save("SONDAJ_LOGU.jpg", "JPEG", quality=95, optimize=True)
        print("✅ Başarılı: SONDAJ_LOGU.jpg oluşturuldu (Strater Formatı).")
    except Exception as e:
        print(f"❌ Hata: {e}")
    finally:
        if os.path.exists(tmp_png):
            os.remove(tmp_png)

# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    draw_strater_log()