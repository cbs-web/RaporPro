import os
import shutil
import tempfile
import uuid
from datetime import datetime

from uygulama_yollari import SOURCE_DIR, kullanici_yolu


APP_DIR = str(SOURCE_DIR)
MAP_EXPORT_DIR = str(
    kullanici_yolu(
        "harita_ciktilari",
        legacy=SOURCE_DIR / "harita_ciktilari",
    )
)
LEGACY_SHARED_MAP_NAMES = {"rapor_sondaj.jpg", "rapor_jeofizik.jpg", "rapor_mjh.jpg"}
PROJE_HARITA_DOSYA_ADLARI = {
    "sondaj": "Sondaj_Lokasyon.jpg",
    "jeofizik": "Jeofizik_Lokasyon.jpg",
}


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


def proje_harita_cikti_yolu(proje_dosyasi_yolu, cikti_tipi):
    """Kaydedilmis proje icin iki Word haritasinin kalici cikti yolunu uret."""

    dosya_adi = PROJE_HARITA_DOSYA_ADLARI.get(str(cikti_tipi or "").strip().lower())
    if not dosya_adi or not proje_dosyasi_yolu:
        return None
    proje_yolu = os.path.abspath(os.path.expanduser(os.fspath(proje_dosyasi_yolu)))
    return os.path.join(os.path.dirname(proje_yolu), "03_Haritalar", dosya_adi)


def harita_ciktisini_proje_klasorune_kopyala(kaynak_yolu, proje_dosyasi_yolu, cikti_tipi):
    """Harita Word ciktisini proje klasorune guvenli ve atomik olarak kopyala.

    Proje henuz kaydedilmemisse veya kopyalama yapilamazsa kaynak yol korunur.
    Donus degeri UI katmaninin durum ve uyarilari gosterebilmesi icin yalindir.
    """

    kaynak = os.path.abspath(os.path.expanduser(os.fspath(kaynak_yolu))) if kaynak_yolu else None
    hedef = proje_harita_cikti_yolu(proje_dosyasi_yolu, cikti_tipi)
    result = {
        "path": kaynak,
        "target": hedef,
        "copied": False,
        "error": None,
    }
    if not kaynak or not hedef or not os.path.isfile(kaynak):
        if kaynak:
            result["error"] = "Kaynak harita dosyasi bulunamadi."
        return result

    try:
        if os.path.normcase(os.path.realpath(kaynak)) == os.path.normcase(os.path.realpath(hedef)):
            result["path"] = hedef
            return result

        hedef_klasoru = os.path.dirname(hedef)
        os.makedirs(hedef_klasoru, exist_ok=True)
        gecici = f"{hedef}.tmp-{uuid.uuid4().hex}"
        try:
            shutil.copy2(kaynak, gecici)
            os.replace(gecici, hedef)
        finally:
            if os.path.exists(gecici):
                try:
                    os.remove(gecici)
                except OSError:
                    pass
        result["path"] = hedef
        result["copied"] = True
    except (OSError, TypeError, ValueError) as exc:
        result["error"] = str(exc) or exc.__class__.__name__
    return result
