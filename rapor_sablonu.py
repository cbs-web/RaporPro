# Dosya: RaporPro/rapor_sablonu.py
"""Dahili ve kullanıcı tarafından seçilen rapor şablonlarını çözümler."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from uygulama_yollari import SOURCE_DIR


DAHILI_SABLON_SURUMU = "2026.08"
DAHILI_SABLON_GORELI_YOLU = Path("sablonlar") / "rapor" / "varsayilan_rapor_sablonu.docx"
RAPOR_SABLON_PROFILI_GENEL = "genel"
RAPOR_SABLON_PROFILI_DARDANOS_CINARLI = "dardanos_cinarli"

RAPOR_SABLON_PROFILLERI = {
    RAPOR_SABLON_PROFILI_GENEL: {
        "label": "Genel dahili şablon",
        "relative_path": DAHILI_SABLON_GORELI_YOLU,
        "version": DAHILI_SABLON_SURUMU,
    },
    RAPOR_SABLON_PROFILI_DARDANOS_CINARLI: {
        "label": "Dardanos-Çınarlı şablonu",
        "relative_path": Path("sablonlar") / "rapor" / "dardanos_cinarli_rapor_sablonu.docx",
        "version": "2026.08-dardanos-cinarli",
    },
}


def rapor_sablon_profili_normalize(profil=None):
    """Kayıtlı veya kullanıcıdan gelen şablon profilini kanonik ada çevir."""
    value = str(profil or "").strip().casefold()
    value = value.replace("ç", "c").replace("ı", "i")
    value = value.replace("-", "_").replace(" ", "_")
    aliases = {
        "": RAPOR_SABLON_PROFILI_GENEL,
        "default": RAPOR_SABLON_PROFILI_GENEL,
        "varsayilan": RAPOR_SABLON_PROFILI_GENEL,
        "dardanos": RAPOR_SABLON_PROFILI_DARDANOS_CINARLI,
        "cinarli": RAPOR_SABLON_PROFILI_DARDANOS_CINARLI,
        "dardanos_cinarli": RAPOR_SABLON_PROFILI_DARDANOS_CINARLI,
    }
    normalized = aliases.get(value, value)
    if normalized not in RAPOR_SABLON_PROFILLERI:
        return RAPOR_SABLON_PROFILI_GENEL
    return normalized


def proje_rapor_sablon_profili(veri=None):
    """Proje verisinde kayıtlı dahili rapor şablonu profilini döndür."""
    try:
        profil = veri.get("ayarlar", {}).get("rapor_sablon_profili")
    except AttributeError:
        profil = None
    return rapor_sablon_profili_normalize(profil)


def _dahili_sablon_adaylari(profil=None):
    profil = rapor_sablon_profili_normalize(profil)
    relative_path = RAPOR_SABLON_PROFILLERI[profil]["relative_path"]
    roots = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(SOURCE_DIR)

    seen = set()
    for root in roots:
        path = (root / relative_path).resolve()
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            yield path


def dahili_rapor_sablonu_yolu(profil=None):
    """Kaynak klasörde veya paket içindeki dahili DOCX şablonunu döndür."""
    for path in _dahili_sablon_adaylari(profil):
        if path.is_file():
            return str(path)
    return ""


def rapor_sablonu_durumu(ozel_yol=None, profil=None):
    """Geçerli özel şablonu, aksi durumda dahili şablonu seç ve durumunu açıkla."""
    profil = rapor_sablon_profili_normalize(profil)
    profil_info = RAPOR_SABLON_PROFILLERI[profil]
    custom_path = str(ozel_yol or "").strip()
    if custom_path and os.path.isfile(custom_path):
        return {
            "path": os.path.abspath(custom_path),
            "source": "custom",
            "ready": True,
            "fallback": False,
            "label": f"Özel şablon: {os.path.basename(custom_path)}",
            "version": "",
            "profile": profil,
        }

    builtin_path = dahili_rapor_sablonu_yolu(profil)
    if builtin_path:
        return {
            "path": builtin_path,
            "source": "builtin",
            "ready": True,
            "fallback": bool(custom_path),
            "label": f"{profil_info['label']} hazır",
            "version": profil_info["version"],
            "profile": profil,
        }

    if profil != RAPOR_SABLON_PROFILI_GENEL:
        builtin_path = dahili_rapor_sablonu_yolu(RAPOR_SABLON_PROFILI_GENEL)
        if builtin_path:
            return {
                "path": builtin_path,
                "source": "builtin",
                "ready": True,
                "fallback": True,
                "label": f"{profil_info['label']} bulunamadı; genel şablon kullanılıyor",
                "version": DAHILI_SABLON_SURUMU,
                "profile": RAPOR_SABLON_PROFILI_GENEL,
            }

    return {
        "path": "",
        "source": "missing",
        "ready": False,
        "fallback": False,
        "label": f"{profil_info['label']} bulunamadı",
        "version": profil_info["version"],
        "profile": profil,
    }


def etkin_rapor_sablonu_yolu(ozel_yol=None, profil=None):
    """Rapor üretiminde kullanılacak geçerli DOCX yolunu döndür."""
    return rapor_sablonu_durumu(ozel_yol, profil).get("path", "")


def rapor_sablonu_etiketi(ozel_yol=None, profil=None):
    """Arayüzde gösterilecek kısa şablon durumunu döndür."""
    return rapor_sablonu_durumu(ozel_yol, profil).get("label", "Dahili şablon bulunamadı")
