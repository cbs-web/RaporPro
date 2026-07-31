# Dosya: RaporPro/rapor_sablonu.py
"""Dahili ve kullanıcı tarafından seçilen rapor şablonlarını çözümler."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from uygulama_yollari import SOURCE_DIR


DAHILI_SABLON_SURUMU = "2026.08"
DAHILI_SABLON_GORELI_YOLU = Path("sablonlar") / "rapor" / "varsayilan_rapor_sablonu.docx"


def _dahili_sablon_adaylari():
    roots = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(SOURCE_DIR)

    seen = set()
    for root in roots:
        path = (root / DAHILI_SABLON_GORELI_YOLU).resolve()
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            yield path


def dahili_rapor_sablonu_yolu():
    """Kaynak klasörde veya paket içindeki dahili DOCX şablonunu döndür."""
    for path in _dahili_sablon_adaylari():
        if path.is_file():
            return str(path)
    return ""


def rapor_sablonu_durumu(ozel_yol=None):
    """Geçerli özel şablonu, aksi durumda dahili şablonu seç ve durumunu açıkla."""
    custom_path = str(ozel_yol or "").strip()
    if custom_path and os.path.isfile(custom_path):
        return {
            "path": os.path.abspath(custom_path),
            "source": "custom",
            "ready": True,
            "fallback": False,
            "label": f"Özel şablon: {os.path.basename(custom_path)}",
            "version": "",
        }

    builtin_path = dahili_rapor_sablonu_yolu()
    if builtin_path:
        return {
            "path": builtin_path,
            "source": "builtin",
            "ready": True,
            "fallback": bool(custom_path),
            "label": "Dahili şablon hazır",
            "version": DAHILI_SABLON_SURUMU,
        }

    return {
        "path": "",
        "source": "missing",
        "ready": False,
        "fallback": False,
        "label": "Dahili şablon bulunamadı",
        "version": DAHILI_SABLON_SURUMU,
    }


def etkin_rapor_sablonu_yolu(ozel_yol=None):
    """Rapor üretiminde kullanılacak geçerli DOCX yolunu döndür."""
    return rapor_sablonu_durumu(ozel_yol).get("path", "")


def rapor_sablonu_etiketi(ozel_yol=None):
    """Arayüzde gösterilecek kısa şablon durumunu döndür."""
    return rapor_sablonu_durumu(ozel_yol).get("label", "Dahili şablon bulunamadı")
