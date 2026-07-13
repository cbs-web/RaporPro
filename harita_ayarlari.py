# Dosya: RaporPro/harita_ayarlari.py
import json
import os
from pathlib import Path

from gizli_depo import gizli_deger_coz, gizli_deger_sakla
from uygulama_yollari import kullanici_yolu
from yardimcilar import atomic_json_dump


HGM_URL_ENV = "RAPORPRO_HGM_ORTOFOTO_URL"
HARITA_AYARLARI_PATH = Path(kullanici_yolu("harita_ayarlar.json"))


def hgm_ortofoto_url_yukle(path=None):
    env_value = os.environ.get(HGM_URL_ENV, "").strip()
    if env_value:
        return env_value
    settings_path = Path(path) if path else HARITA_AYARLARI_PATH
    if not settings_path.exists():
        return ""
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        return gizli_deger_coz(data.get("hgm_ortofoto_url", "")).strip()
    except Exception:
        return ""


def hgm_ortofoto_url_kaydet(url, path=None):
    settings_path = Path(path) if path else HARITA_AYARLARI_PATH
    data = {}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            data = {}
    value = str(url or "").strip()
    data["hgm_ortofoto_url"] = gizli_deger_sakla(value) if value else ""
    atomic_json_dump(data, settings_path, ensure_ascii=False, indent=2)
    return settings_path
