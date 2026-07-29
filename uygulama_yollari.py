# Dosya: RaporPro/uygulama_yollari.py
from __future__ import annotations

import os
from pathlib import Path
import shutil
import uuid


APP_NAME = "RaporPro"
SOURCE_DIR = Path(__file__).resolve().parent
_KALICI_KOK_DOSYALARI = (
    "ayarlar.json",
    "harita_ayarlar.json",
    "recent_projects.json",
    "completed_projects.json",
)


def kullanici_veri_dizini(base_dir=None):
    """Kalıcı ve kullanıcıya yazılabilir uygulama dizinini döndür."""
    if base_dir is not None:
        root = Path(base_dir)
    else:
        configured = os.environ.get("RAPORPRO_DATA_DIR", "").strip()
        if configured:
            root = Path(configured).expanduser()
        else:
            local = os.environ.get("LOCALAPPDATA")
            roaming = os.environ.get("APPDATA")
            if local:
                root = Path(local) / APP_NAME
                legacy_root = Path(roaming) / APP_NAME if roaming else None
                try:
                    root.mkdir(parents=True, exist_ok=True)
                except OSError:
                    if legacy_root and legacy_root.exists():
                        return legacy_root
                    raise
                if legacy_root and legacy_root.exists():
                    for name in _KALICI_KOK_DOSYALARI:
                        source = legacy_root / name
                        target = root / name
                        if source.exists() and not target.exists():
                            if not eski_veriyi_kopyala(source, target):
                                # Ayarları görünmez kılmamak için bu oturumda
                                # eski kökü kullan; sonraki açılış yeniden dener.
                                return legacy_root
            else:
                root = Path(roaming) / APP_NAME if roaming else Path.home() / "AppData" / "Local" / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def eski_veriyi_kopyala(eski_yol, yeni_yol):
    """Eski kod dizinindeki kullanıcı verisini yeni dizine güvenle devral."""
    source = Path(eski_yol)
    target = Path(yeni_yol)
    if target.exists() or not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    staged_target = target.parent / f".{target.name}.migration-{uuid.uuid4().hex}"
    try:
        if source.is_dir():
            shutil.copytree(source, staged_target)
        else:
            shutil.copy2(source, staged_target)
        os.replace(staged_target, target)
        return True
    except OSError:
        return False
    finally:
        try:
            if staged_target.is_dir():
                shutil.rmtree(staged_target)
            elif staged_target.exists():
                staged_target.unlink()
        except OSError:
            pass


def kullanici_yolu(*parts, legacy=None, base_dir=None, migrate=True):
    """AppData altındaki yolu üret ve istenirse eski veriyi bir kez kopyala."""
    target = kullanici_veri_dizini(base_dir=base_dir).joinpath(*map(str, parts))
    migration_sources = []
    if migrate and base_dir is None:
        roaming = os.environ.get("APPDATA")
        if roaming:
            migration_sources.append(Path(roaming) / APP_NAME / Path(*map(str, parts)))
    if legacy is not None and migrate:
        legacy_path = Path(legacy)
        if not legacy_path.is_absolute():
            legacy_path = SOURCE_DIR / legacy_path
        migration_sources.append(legacy_path)
    for source in migration_sources:
        if target.exists():
            break
        if not source.exists() or source == target:
            continue
        if eski_veriyi_kopyala(source, target):
            break
        if not target.exists():
            # Başarısız göçte mevcut veriyi bu oturumda görünür tut.
            return source
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
