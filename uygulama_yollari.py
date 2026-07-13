# Dosya: RaporPro/uygulama_yollari.py
from __future__ import annotations

import os
from pathlib import Path
import shutil


APP_NAME = "RaporPro"
SOURCE_DIR = Path(__file__).resolve().parent


def kullanici_veri_dizini(base_dir=None):
    """Kalıcı ve kullanıcıya yazılabilir uygulama dizinini döndür."""
    if base_dir is not None:
        root = Path(base_dir)
    else:
        configured = os.environ.get("RAPORPRO_DATA_DIR", "").strip()
        if configured:
            root = Path(configured).expanduser()
        else:
            roaming = os.environ.get("APPDATA")
            root = Path(roaming) / APP_NAME if roaming else Path.home() / "AppData" / "Roaming" / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def eski_veriyi_kopyala(eski_yol, yeni_yol):
    """Eski kod dizinindeki kullanıcı verisini yeni dizine güvenle devral."""
    source = Path(eski_yol)
    target = Path(yeni_yol)
    if target.exists() or not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        return True
    except OSError:
        return False


def kullanici_yolu(*parts, legacy=None, base_dir=None, migrate=True):
    """AppData altındaki yolu üret ve istenirse eski veriyi bir kez kopyala."""
    target = kullanici_veri_dizini(base_dir=base_dir).joinpath(*map(str, parts))
    if legacy is not None and migrate:
        legacy_path = Path(legacy)
        if not legacy_path.is_absolute():
            legacy_path = SOURCE_DIR / legacy_path
        eski_veriyi_kopyala(legacy_path, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
