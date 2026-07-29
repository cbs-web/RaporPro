# Dosya: RaporPro/proje_klasorleri.py
"""RaporPro proje klasörünün standart dizin yapısını oluşturur."""

from __future__ import annotations

import os
from pathlib import Path


PROJE_ALT_KLASORLERI = (
    "00_Rapor",
    "01_Loglar",
    "02_Kesitler",
    "03_Haritalar",
    "04_Rapor_Gorselleri",
    "05_Taahhutnameler",
    "06_Ekler",
    "EVRAKLAR",
    "LAB",
    "JEOFİZİK",
    "Presiyometre",
    "backups",
)


def proje_alt_klasorlerini_olustur(proje_dosyasi_yolu):
    """Proje dosyasının yanında eksik standart alt klasörleri oluştur."""

    if not proje_dosyasi_yolu:
        raise ValueError("Proje dosyası yolu boş olamaz.")

    project_path = Path(os.fspath(proje_dosyasi_yolu)).expanduser().resolve()
    project_folder = project_path.parent
    created = []
    existing = []
    errors = []
    paths = {}

    for name in PROJE_ALT_KLASORLERI:
        folder = project_folder / name
        paths[name] = str(folder)
        if folder.is_dir():
            existing.append(name)
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            created.append(name)
        except OSError as exc:
            errors.append({"klasor": name, "hata": str(exc)})

    return {
        "proje_klasoru": str(project_folder),
        "olusturulan": created,
        "mevcut": existing,
        "hatalar": errors,
        "yollar": paths,
    }


__all__ = [
    "PROJE_ALT_KLASORLERI",
    "proje_alt_klasorlerini_olustur",
]
