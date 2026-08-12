# Dosya: RaporPro/litoloji_renk_motoru.py
"""Karot/sandik fotografından yerel ve dusuk maliyetli renk profili cikarir."""

from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageOps


def _dogrula_crop(crop):
    values = list(crop or (0.0, 0.0, 1.0, 1.0))
    if len(values) != 4:
        raise ValueError("Fotograf kirpma alani dort oransal deger icermelidir.")
    left, top, right, bottom = (float(value) for value in values)
    left, top = max(0.0, left), max(0.0, top)
    right, bottom = min(1.0, right), min(1.0, bottom)
    if right - left < 0.02 or bottom - top < 0.02:
        raise ValueError("Fotograf kirpma alani cok kucuk.")
    return left, top, right, bottom


def _gray_world_white_balance(array):
    pixels = array.reshape(-1, 3)
    valid = pixels[(pixels.mean(axis=1) > 20) & (pixels.mean(axis=1) < 245)]
    if len(valid) < 20:
        return array
    channel_means = valid.mean(axis=0)
    target = float(channel_means.mean())
    scales = target / np.maximum(channel_means, 1.0)
    scales = np.clip(scales, 0.72, 1.38)
    return np.clip(array * scales, 0, 255)


def _representative_rgb(array):
    pixels = np.asarray(array, dtype=float).reshape(-1, 3)
    if len(pixels) == 0:
        return (128, 128, 128)
    brightness = pixels.mean(axis=1)
    spread = pixels.max(axis=1) - pixels.min(axis=1)
    valid = (
        (brightness >= 22)
        & (brightness <= 242)
        & ~((brightness > 225) & (spread < 14))
    )
    selected = pixels[valid]
    if len(selected) < max(20, len(pixels) * 0.03):
        selected = pixels[(brightness >= 12) & (brightness <= 250)]
    if len(selected) == 0:
        selected = pixels
    rgb = np.median(selected, axis=0)
    return tuple(int(round(value)) for value in np.clip(rgb, 0, 255))


def _rgb_to_lab(rgb):
    values = np.asarray(rgb, dtype=float) / 255.0
    values = np.where(
        values > 0.04045,
        ((values + 0.055) / 1.055) ** 2.4,
        values / 12.92,
    )
    x, y, z = np.dot(
        values,
        np.array(
            [
                [0.4124564, 0.3575761, 0.1804375],
                [0.2126729, 0.7151522, 0.0721750],
                [0.0193339, 0.1191920, 0.9503041],
            ]
        ).T,
    )
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def f(value):
        delta = 6 / 29
        return value ** (1 / 3) if value > delta**3 else value / (3 * delta**2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return np.array([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)])


def renk_lab_degeri(rgb):
    """Bir RGB rengini tekrar kullanilabilir CIELAB vektorune cevirir."""
    if rgb is None:
        return None
    try:
        return _rgb_to_lab(rgb)
    except Exception:
        return None


def lab_benzerligi(first_lab, second_lab):
    """Onceden hesaplanmis CIELAB vektorleri arasindaki 0..1 benzerlik."""
    if first_lab is None or second_lab is None:
        return 0.0
    try:
        delta = float(np.linalg.norm(first_lab - second_lab))
    except Exception:
        return 0.0
    return max(0.0, min(1.0, math.exp(-delta / 22.0)))


def renk_benzerligi(first_rgb, second_rgb):
    """0..1 arasinda, aydinlik farkina karsi yumusatilmis renk benzerligi."""
    if first_rgb is None or second_rgb is None:
        return 0.0
    return lab_benzerligi(renk_lab_degeri(first_rgb), renk_lab_degeri(second_rgb))


def renk_profili_olustur(path, baslangic, bitis, adim=0.5, crop=None, yon="dikey"):
    """Fotografi derinlige esleyip her 0,50 m icin temsili renk cikarir."""
    path = os.fspath(path) if path else ""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"Fotograf bulunamadi: {path}")
    start = float(baslangic)
    end = float(bitis)
    step = max(0.5, round(float(adim or 0.5) * 2) / 2)
    if end <= start:
        raise ValueError("Fotograf bitis derinligi baslangictan buyuk olmalidir.")
    direction = str(yon or "dikey").strip().casefold()
    if direction not in {"dikey", "yatay"}:
        raise ValueError("Fotograf yonu 'dikey' veya 'yatay' olmalidir.")

    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    max_side = max(image.size)
    if max_side > 1400:
        ratio = 1400.0 / max_side
        image = image.resize(
            (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    left, top, right, bottom = _dogrula_crop(crop)
    box = (
        int(round(left * image.width)),
        int(round(top * image.height)),
        int(round(right * image.width)),
        int(round(bottom * image.height)),
    )
    array = _gray_world_white_balance(np.asarray(image.crop(box), dtype=float))
    axis_length = array.shape[0] if direction == "dikey" else array.shape[1]
    total_depth = end - start
    result = []
    depth = start
    while depth < end - 1e-9:
        depth_end = min(end, round(depth + step, 6))
        first_ratio = (depth - start) / total_depth
        second_ratio = (depth_end - start) / total_depth
        pixel_start = max(0, min(axis_length - 1, int(math.floor(first_ratio * axis_length))))
        pixel_end = max(pixel_start + 1, min(axis_length, int(math.ceil(second_ratio * axis_length))))
        if direction == "dikey":
            segment = array[pixel_start:pixel_end, :, :]
            margin = max(0, int(segment.shape[1] * 0.06))
            if margin and segment.shape[1] > margin * 2:
                segment = segment[:, margin:-margin, :]
        else:
            segment = array[:, pixel_start:pixel_end, :]
            margin = max(0, int(segment.shape[0] * 0.06))
            if margin and segment.shape[0] > margin * 2:
                segment = segment[margin:-margin, :, :]
        rgb = _representative_rgb(segment)
        result.append(
            {
                "top": round(depth, 3),
                "bottom": round(depth_end, 3),
                "rgb": list(rgb),
                "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
            }
        )
        depth = depth_end
    return result


__all__ = [
    "lab_benzerligi",
    "renk_benzerligi",
    "renk_lab_degeri",
    "renk_profili_olustur",
]
