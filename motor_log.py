# Dosya: RaporPro/motor_log.py
"""
Guncel log cizim metodlari icin gecici uyumluluk koprusu.

Bu dosya, motor.py log bloğu ayrılırken oluşan ara durumda programın mevcut
davranışını korumak için, log bloğu kaldırılmadan hemen önce derlenen pyc
dosyasından metodları yükler. Kaynak tabanlı kalıcı bölme için bu dosya daha
sonra gerçek GeoEngineLogMixin kaynağıyla değiştirilmelidir.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cached_motor_module():
    cache_path = Path(__file__).with_name("motor_log_cache.cpython-311.pyc")
    if not cache_path.exists():
        raise ImportError(f"Guncel motor log onbellegi bulunamadi: {cache_path}")
    spec = importlib.util.spec_from_file_location("_raporpro_cached_motor_for_log", cache_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Motor log onbellegi yuklenemedi: {cache_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_cached_motor = _load_cached_motor_module()
log_ornek_derinligi_formatla = _cached_motor.log_ornek_derinligi_formatla


class GeoEngineLogMixin:
    ciz_profesyonel_log = staticmethod(_cached_motor.GeoEngine.ciz_profesyonel_log)
    _ciz_strater_stil_log = staticmethod(_cached_motor.GeoEngine._ciz_strater_stil_log)
    _ciz_profesyonel_log_eski = staticmethod(_cached_motor.GeoEngine._ciz_profesyonel_log_eski)
