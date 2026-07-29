# Dosya: RaporPro/spt_gorsel.py
import base64
from functools import lru_cache
import hashlib
from io import BytesIO
import mimetypes
import os
import re


def dogal_siralama_anahtari(value):
    """Dosya adlarini 1, 2, 10 gibi dogal sirada karsilastir."""
    text = str(value or "")
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", text)
    ]


def _dosya_imzasi_girdisi(path):
    abs_path = os.path.realpath(os.path.abspath(str(path)))
    stat = os.stat(abs_path)
    return abs_path, int(stat.st_size), int(stat.st_mtime_ns)


@lru_cache(maxsize=2048)
def _dosya_parmak_izi_cached(abs_path, size, mtime_ns):
    digest = hashlib.sha256()
    with open(abs_path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dosya_parmak_izi(path):
    """Ayni icerige sahip kopya fotograflari taniyan SHA-256 ozeti."""
    try:
        return _dosya_parmak_izi_cached(*_dosya_imzasi_girdisi(path))
    except Exception:
        return ""


def gorsel_api_payload_hazirla(path, maksimum_kenar=2048, jpeg_kalitesi=86):
    """Gorseli EXIF yonu duzeltilmis ve API icin kucultulmus olarak hazirla."""
    abs_path = os.path.realpath(os.path.abspath(str(path)))
    source_hash = dosya_parmak_izi(abs_path)
    original_size = os.path.getsize(abs_path)
    metadata = {
        "kaynak_hash": source_hash,
        "orijinal_bayt": original_size,
        "islenmis_bayt": original_size,
        "orijinal_boyut": "",
        "islenmis_boyut": "",
        "gorsel_on_isleme": False,
    }

    try:
        from PIL import Image, ImageOps

        with Image.open(abs_path) as source:
            try:
                image = ImageOps.exif_transpose(source)
            except Exception:
                image = source.copy()
            image = image.convert("RGB")
            metadata["orijinal_boyut"] = f"{image.width}x{image.height}"
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            if max(image.size) > int(maksimum_kenar):
                image.thumbnail((int(maksimum_kenar), int(maksimum_kenar)), resample)
            metadata["islenmis_boyut"] = f"{image.width}x{image.height}"
            output = BytesIO()
            image.save(output, "JPEG", quality=int(jpeg_kalitesi), optimize=True)
            raw = output.getvalue()
            metadata["islenmis_bayt"] = len(raw)
            metadata["gorsel_on_isleme"] = True
            return base64.b64encode(raw).decode("utf-8"), "image/jpeg", metadata
    except Exception:
        with open(abs_path, "rb") as stream:
            raw = stream.read()
        mime_type = mimetypes.guess_type(abs_path)[0] or "image/jpeg"
        return base64.b64encode(raw).decode("utf-8"), mime_type, metadata
