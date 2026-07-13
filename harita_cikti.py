import os
import tempfile
import uuid
from datetime import datetime

from uygulama_yollari import SOURCE_DIR, kullanici_yolu


APP_DIR = str(SOURCE_DIR)
MAP_EXPORT_DIR = str(kullanici_yolu("harita_ciktilari"))
LEGACY_SHARED_MAP_NAMES = {"rapor_sondaj.jpg", "rapor_jeofizik.jpg", "rapor_mjh.jpg"}


def yeni_harita_cikti_yolu(kind, ext=".jpg"):
    os.makedirs(MAP_EXPORT_DIR, exist_ok=True)
    safe_kind = "".join(ch for ch in str(kind or "harita").lower() if ch.isalnum() or ch in {"_", "-"}).strip("_-")
    safe_kind = safe_kind or "harita"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return os.path.join(MAP_EXPORT_DIR, f"{safe_kind}_{timestamp}_{suffix}{ext}")


def eski_paylasimli_temp_harita_yolu_mu(path):
    if not path:
        return False
    try:
        basename = os.path.basename(str(path)).lower()
        if basename not in LEGACY_SHARED_MAP_NAMES:
            return False
        temp_dir = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
        path_dir = os.path.normcase(os.path.abspath(os.path.dirname(str(path))))
        return path_dir == temp_dir
    except Exception:
        return False
