# Dosya: RaporPro/karot_gorunum.py

import math


def _pozitif_boyutlar(size, label):
    try:
        width = float(size[0])
        height = float(size[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"{label} boyutu okunamadi.") from exc
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise ValueError(f"{label} boyutu sifirdan buyuk ve sonlu olmali.")
    return width, height


def _limitler(limits, label):
    try:
        first = float(limits[0])
        second = float(limits[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"{label} limitleri okunamadi.") from exc
    if not all(math.isfinite(value) for value in (first, second)) or first == second:
        raise ValueError(f"{label} limitleri farkli ve sonlu olmali.")
    return first, second


def tam_gorunum(image_size):
    width, height = _pozitif_boyutlar(image_size, "Gorsel")
    return ((-0.5, width - 0.5), (height - 0.5, -0.5))


def gorunum_yakinlastir(
    xlim,
    ylim,
    factor,
    center,
    image_size,
    minimum_pixels=4.0,
):
    """Fare konumunu sabit tutarak yeni x/y gorunum limitlerini hesaplar."""
    x0, x1 = _limitler(xlim, "X")
    y0, y1 = _limitler(ylim, "Y")
    width, height = _pozitif_boyutlar(image_size, "Gorsel")
    try:
        factor = float(factor)
        center_x, center_y = float(center[0]), float(center[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("Yakinlastirma degerleri okunamadi.") from exc
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("Yakinlastirma katsayisi sifirdan buyuk olmali.")

    current_width = abs(x1 - x0)
    current_height = abs(y1 - y0)
    if factor > 1.0 and current_width >= width and current_height >= height:
        return tam_gorunum((width, height))

    min_width = max(float(minimum_pixels), width / 500.0)
    min_height = max(float(minimum_pixels), height / 500.0)
    new_width = max(min_width, min(width, current_width * factor))
    new_height = max(min_height, min(height, current_height * factor))
    if new_width >= width and new_height >= height:
        return tam_gorunum((width, height))

    x_scale = new_width / current_width
    y_scale = new_height / current_height
    return (
        (
            center_x + (x0 - center_x) * x_scale,
            center_x + (x1 - center_x) * x_scale,
        ),
        (
            center_y + (y0 - center_y) * y_scale,
            center_y + (y1 - center_y) * y_scale,
        ),
    )


def gorunum_kaydir(xlim, ylim, pixel_delta, canvas_size):
    """Ekran piksel hareketini mevcut veri koordinatlarina cevirir."""
    x0, x1 = _limitler(xlim, "X")
    y0, y1 = _limitler(ylim, "Y")
    canvas_width, canvas_height = _pozitif_boyutlar(canvas_size, "Tuval")
    try:
        dx_pixels = float(pixel_delta[0])
        dy_pixels = float(pixel_delta[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("Kaydirma hareketi okunamadi.") from exc

    dx_data = dx_pixels * (x1 - x0) / canvas_width
    dy_data = dy_pixels * (y1 - y0) / canvas_height
    return (
        (x0 - dx_data, x1 - dx_data),
        (y0 - dy_data, y1 - dy_data),
    )
