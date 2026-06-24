# Dosya: RaporPro/harita_resim_cache.py
import os
from collections import OrderedDict

import matplotlib.image as mpimg
import numpy as np

from performans import perf_log, perf_timer


DISPLAY_IMAGE_MAX_DIM = 2400
IMAGE_PREVIEW_CACHE_LIMIT = 5
_IMAGE_PREVIEW_CACHE = OrderedDict()


def _cache_key(img_path, max_dim):
    stat = os.stat(img_path)
    return (os.path.abspath(img_path), stat.st_mtime_ns, stat.st_size, int(max_dim))


def _cache_get(cache_key):
    cached = _IMAGE_PREVIEW_CACHE.get(cache_key)
    if cached is None:
        return None
    _IMAGE_PREVIEW_CACHE.move_to_end(cache_key)
    perf_log("map.image_preview_cache_hit", detail=os.path.basename(cache_key[0]))
    return cached


def _cache_set(cache_key, image_array, width, height, shape):
    _IMAGE_PREVIEW_CACHE[cache_key] = {
        "array": image_array,
        "width": width,
        "height": height,
        "shape": shape,
    }
    _IMAGE_PREVIEW_CACHE.move_to_end(cache_key)
    while len(_IMAGE_PREVIEW_CACHE) > IMAGE_PREVIEW_CACHE_LIMIT:
        _IMAGE_PREVIEW_CACHE.popitem(last=False)


def display_image_read(img_path, max_dim=DISPLAY_IMAGE_MAX_DIM):
    """Harita altligini ekran icin oku, gerekiyorsa kucult ve onbellekle."""
    cache_key = _cache_key(img_path, max_dim)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached["array"], cached["width"], cached["height"], cached["shape"]

    with perf_timer("map.image_preview_read", os.path.basename(img_path)):
        try:
            from PIL import Image

            with Image.open(img_path) as pil_img:
                width, height = pil_img.size
                try:
                    pil_img.draft("RGB", (max_dim, max_dim))
                except Exception:
                    pass
                if max(pil_img.size) > max_dim:
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    pil_img.thumbnail((max_dim, max_dim), resample)
                if pil_img.mode not in ("RGB", "RGBA"):
                    pil_img = pil_img.convert("RGB")
                image_array = np.asarray(pil_img).copy()
        except Exception:
            image_array = mpimg.imread(img_path)
            height, width = image_array.shape[:2]

    shape = image_array.shape
    _cache_set(cache_key, image_array, width, height, shape)
    return image_array, width, height, shape


def clear_display_image_cache():
    _IMAGE_PREVIEW_CACHE.clear()
