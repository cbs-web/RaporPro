# Dosya: RaporPro/motor.py
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import textwrap
import threading

# --- GEREKLİ MODÜL BAĞLANTILARI ---
# Bu bağlantılardan biri kurulamazsa başlangıç denetiminin gerçek hatayı
# göstermesi gerekir. Sessiz sahte hesaplar mühendislik çıktısını güvenilmez
# hale getirdiği için burada fallback kullanılmaz.
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


from motor_hesap import GeoEngineHesapMixin
from motor_log import GeoEngineLogMixin, log_ornek_derinligi_formatla
from motor_interaktif import GeoInteractiveTool
from motor_kesit import GeoEngineKesitMixin

# --- ANA MOTOR SINIFI ---
class GeoEngine(GeoEngineHesapMixin, GeoEngineLogMixin, GeoEngineKesitMixin):
    _warned_units = set()
    plot_lock = threading.RLock()

    @staticmethod
    def ciz_profesyonel_log(sondaj, proje_dict, log_callback=None):
        with GeoEngine.plot_lock:
            return GeoEngineLogMixin.ciz_profesyonel_log(sondaj, proje_dict, log_callback=log_callback)

    @staticmethod
    def kesit_ciz_interaktif(sondajlar, log_callback=None, options=None):
        with GeoEngine.plot_lock:
            return GeoEngineKesitMixin.kesit_ciz_interaktif(
                sondajlar,
                log_callback=log_callback,
                options=options,
            )

    @staticmethod
    def reset_warnings():
        GeoEngine._warned_units.clear()

