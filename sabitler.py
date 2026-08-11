# Dosya: RaporPro/sabitler.py
import os

# --- YOL TANIMLARI ---
# Programın çalıştığı klasörü otomatik bulur ve JSON'ı oraya kaydeder
PROJE_KLASORU = os.path.dirname(os.path.abspath(__file__))
JSON_DOSYA = os.path.join(PROJE_KLASORU, "zemin_proje_data.json")

# --- RENKLER ---
COLOR_BG = "#F4F6F9"
COLOR_PRIMARY = "#2C3E50"
COLOR_ACCENT = "#3498DB"
COLOR_SUCCESS = "#27AE60"
COLOR_WARNING = "#E67E22"
COLOR_DANGER = "#C0392B"
COLOR_LOG_BG = "#F8FAFC"
COLOR_LOG_TEXT = "#52606D"
COLOR_LOG_TIME = "#667085"

# --- ARAYUZ YUZEYLERI / DURUMLAR ---
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_ALT = "#F8FAFC"
COLOR_BORDER = "#D7DEE7"
COLOR_BORDER_STRONG = "#B8C4D1"
COLOR_TEXT = "#263238"
COLOR_TEXT_MUTED = "#667085"
COLOR_SUCCESS_SOFT = "#EFF8F2"
COLOR_WARNING_SOFT = "#FFF7E8"
COLOR_DANGER_SOFT = "#FDEEEE"
COLOR_ACCENT_SOFT = "#EEF6FC"

# --- FONTLAR ---
FONT_MAIN = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_HEADER = ("Segoe UI", 11, "bold")
FONT_LOG = ("Consolas", 9)
FONT_UI_SMALL = ("Segoe UI", 8)
FONT_UI_BODY = ("Segoe UI", 9)
FONT_UI_BODY_BOLD = ("Segoe UI", 9, "bold")
FONT_UI_SECTION = ("Segoe UI", 10, "bold")
FONT_UI_PAGE = ("Segoe UI", 15, "bold")

# --- ORTAK BOSLUKLAR ---
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

# --- ÇIKTI / SAYFA YERLEŞİMİ ---
A4_PORTRAIT_SIZE = (8.27, 11.69)
A4_LANDSCAPE_SIZE = (11.69, 8.27)
A3_LANDSCAPE_SIZE = (16.54, 11.69)
DEFAULT_EXPORT_DPI = 300
LOG_FIGURE_DPI = 110
LOG_LEGACY_FIGURE_DPI = 100
SECTION_FIGURE_DPI = 100
SECTION_AXES_RECT = [0.08, 0.05, 0.84, 0.90]

HARITA_PAFTA_LAYOUT = {
    "figure_size": A4_PORTRAIT_SIZE,
    "map_axes": [0.05, 0.30, 0.90, 0.65],
    "coord_axes": [0.05, 0.05, 0.48, 0.34],
    "legend_axes": [0.55, 0.05, 0.40, 0.34],
    "border_width": 1.5,
    "title_fontsize": 14,
    "title_pad": 10,
    "panel_title_fontsize": 9,
    "coord_fontsize": 8,
    "legend_fontsize": 8,
    "legend_symbol_fontsize": 9,
}

# --- VERİTABANI ---
LEJANTLAR = [
    {"kod": "bt", "ad": "Bitkisel Toprak", "zemin": "#FFFFFF", "sembol": "#111111", "desen": "ot"},
    {"kod": "kl", "ad": "Kil", "zemin": "#FFFFFF", "sembol": "#9A9A9A", "desen": "kesikli"},
    {"kod": "s", "ad": "Silt", "zemin": "#FFFFFF", "sembol": "#6F6F6F", "desen": "noktali_kesikli"},
    {"kod": "kit", "ad": "Kiltaşı", "zemin": "#FFFFFF", "sembol": "#4F4F4F", "desen": "kiltasi_cizgili_noktali"},
    {"kod": "k", "ad": "Kum", "zemin": "#FFFFFF", "sembol": "#D9D400", "desen": "nokta"},
    {"kod": "c", "ad": "Çakıl", "zemin": "#FFFFFF", "sembol": "#D4A000", "desen": "cakil_daire"},
    {"kod": "mlz", "ad": "Moloz", "zemin": "#FFFFFF", "sembol": "#B9955B", "desen": "moloz_parca"},
    {"kod": "kt", "ad": "Kumtaşı", "zemin": "#FFFFFF", "sembol": "#C98A00", "desen": "kumtasi_yatay"},
    {"kod": "ct", "ad": "Çakıltaşı", "zemin": "#FFFFFF", "sembol": "#B36B00", "desen": "cakil_oval_cizgili"},
    {"kod": "dg", "ad": "Dolgu", "zemin": "#FFFFFF", "sembol": "#6E6255", "desen": "dolgu_karisik"},
    {"kod": "tanimsiz", "ad": "Tanımsız Birim", "zemin": "#FFFFFF", "sembol": "#000000", "desen": ""} 
]

KELIME_HARITASI = {
    "toprak": "bt", "topragi": "bt", "nebati": "bt", "bitkisel": "bt",
    "kil": "kl", "killi": "kl", "silt": "s", "siltli": "s",
    "kiltasi": "kit", "kum": "k", "kumlu": "k",
    "cakil": "c", "cakilli": "c",
    "moloz": "mlz", "molozlu": "mlz",
    "dolgu": "dg", "dolgulu": "dg", "dolgusu": "dg",
    "kumtasi": "kt",
    "cakiltasi": "ct", "konglomera": "ct", "bres": "ct"
}
