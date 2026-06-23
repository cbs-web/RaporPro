# Dosya: RaporPro/motor.py
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import textwrap

# --- GEREKLİ MODÜL BAĞLANTILARI ---
try:
    from sabitler import (
        A4_LANDSCAPE_SIZE,
        A4_PORTRAIT_SIZE,
        LEJANTLAR,
        LOG_FIGURE_DPI,
        LOG_LEGACY_FIGURE_DPI,
        SECTION_AXES_RECT,
        SECTION_FIGURE_DPI,
    )
    from yardimcilar import safe_float, haversine_distance, litoloji_cozumle
    from karot_motoru import derinlik_araligi_coz, derinlik_baslangic, derinlik_orta
    from cizim import GeoEngineDraw
    from performans import log_exception
except ImportError:
    LEJANTLAR = []
    def safe_float(v): return 0.0
    def haversine_distance(l1,ln1,l2,ln2): return 0.0
    def litoloji_cozumle(t): return "tanimsiz"
    def derinlik_araligi_coz(v): return safe_float(v), safe_float(v)
    def derinlik_baslangic(v): return safe_float(v)
    def derinlik_orta(v): return safe_float(v)
    class GeoEngineDraw:
        @staticmethod
        def draw_pattern(ax, p, s, c, bbox=None, density_scale=1): pass
        @staticmethod
        def hide_same_unit_seams(ax, polygons, tolerance=0.08): return []
    def log_exception(name, exc_type=None, exc_value=None, exc_tb=None): return None
    A4_PORTRAIT_SIZE = (8.27, 11.69)
    A4_LANDSCAPE_SIZE = (11.69, 8.27)
    LOG_FIGURE_DPI = 110
    LOG_LEGACY_FIGURE_DPI = 100
    SECTION_FIGURE_DPI = 100
    SECTION_AXES_RECT = [0.08, 0.05, 0.84, 0.90]


from motor_hesap import GeoEngineHesapMixin
from motor_log import GeoEngineLogMixin, log_ornek_derinligi_formatla
from motor_interaktif import GeoInteractiveTool
from motor_kesit import GeoEngineKesitMixin

# --- ANA MOTOR SINIFI ---
class GeoEngine(GeoEngineHesapMixin, GeoEngineLogMixin, GeoEngineKesitMixin):
    _warned_units = set()

    @staticmethod
    def reset_warnings():
        GeoEngine._warned_units.clear()

