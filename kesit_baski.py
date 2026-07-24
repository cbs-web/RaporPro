# Dosya: RaporPro/kesit_baski.py
import math

from sabitler import A3_LANDSCAPE_SIZE, A4_LANDSCAPE_SIZE


INCHES_PER_METER = 1000.0 / 25.4
STANDARD_SCALES = (50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000)


def kesit_sayfa_boyutu(page_name):
    """Kesit baskı sayfasının adını ve yatay ölçüsünü inç olarak döndür."""
    normalized = str(page_name or "A4 Yatay").strip().upper()
    if normalized.startswith("A3"):
        return "A3 Yatay", A3_LANDSCAPE_SIZE
    return "A4 Yatay", A4_LANDSCAPE_SIZE


def kesit_dusey_abarti(horizontal_scale, vertical_scale):
    """Yatay ve düşey ölçeklerden düşey abartı katsayısını hesapla."""
    horizontal = max(1.0, float(horizontal_scale or 1.0))
    vertical = max(1.0, float(vertical_scale or 1.0))
    return horizontal / vertical


def kesit_metre_baski_boyu(span_m, scale_denominator):
    """Metre cinsinden uzunluğun belirtilen ölçekte baskıdaki inç karşılığını ver."""
    span = max(0.0, float(span_m or 0.0))
    denominator = max(1.0, float(scale_denominator or 1.0))
    return span * INCHES_PER_METER / denominator


def _ust_standart_olcek(required_scale):
    required = max(1.0, float(required_scale or 1.0))
    for scale in STANDARD_SCALES:
        if scale + 1e-9 >= required:
            return float(scale)
    magnitude = 10 ** max(0, int(math.floor(math.log10(required))) - 1)
    return float(math.ceil(required / magnitude) * magnitude)


def kesit_baski_yerlesimi(
    x_span_m,
    y_span_m,
    page_name="A4 Yatay",
    horizontal_scale=500,
    vertical_scale=100,
    legend_rows=0,
    show_title_block=False,
    auto_fit=True,
):
    """Kesit veri alanını gerçek baskı ölçeğinde sayfaya yerleştir.

    Ölçek sayfaya sığmıyorsa ``auto_fit`` ile yalnızca gerekli eksen ölçeği
    bir üst standart paydaya taşınır. Dönen eksen dikdörtgenleri Matplotlib
    ``add_axes`` / ``set_position`` ile doğrudan kullanılabilir.
    """
    page_label, (page_width, page_height) = kesit_sayfa_boyutu(page_name)
    requested_horizontal = max(1.0, float(horizontal_scale or 500.0))
    requested_vertical = max(1.0, float(vertical_scale or 100.0))
    x_span = max(0.01, float(x_span_m or 0.01))
    y_span = max(0.01, float(y_span_m or 0.01))
    rows = max(0, int(legend_rows or 0))

    left_margin = 0.72
    right_margin = 0.38
    top_margin = 0.72
    bottom_margin = 0.30
    legend_height = 0.0 if rows == 0 else min(2.10, 0.34 + rows * 0.42)
    title_block_height = 1.18 if show_title_block else 0.0
    info_height = max(legend_height, title_block_height)
    info_gap = 0.0 if info_height == 0 else 0.24

    available_width = max(0.25, page_width - left_margin - right_margin)
    available_height = max(
        0.25,
        page_height - top_margin - bottom_margin - info_height - info_gap,
    )
    required_horizontal = x_span * INCHES_PER_METER / available_width
    required_vertical = y_span * INCHES_PER_METER / available_height

    effective_horizontal = requested_horizontal
    effective_vertical = requested_vertical
    requested_fits = (
        required_horizontal <= requested_horizontal + 1e-9
        and required_vertical <= requested_vertical + 1e-9
    )
    if auto_fit:
        if required_horizontal > requested_horizontal:
            effective_horizontal = _ust_standart_olcek(required_horizontal)
        if required_vertical > requested_vertical:
            effective_vertical = _ust_standart_olcek(required_vertical)

    axes_width = kesit_metre_baski_boyu(x_span, effective_horizontal)
    axes_height = kesit_metre_baski_boyu(y_span, effective_vertical)
    effective_fits = (
        axes_width <= available_width + 1e-9
        and axes_height <= available_height + 1e-9
    )

    left = left_margin + max(0.0, (available_width - axes_width) / 2.0)
    bottom_available = bottom_margin + info_height + info_gap
    bottom = bottom_available + max(0.0, (available_height - axes_height) / 2.0)
    axes_rect = [
        left / page_width,
        bottom / page_height,
        min(axes_width, available_width) / page_width,
        min(axes_height, available_height) / page_height,
    ]

    legend_rect = None
    if rows:
        legend_width = available_width
        if show_title_block:
            legend_width = max(0.25, available_width * 0.62)
        legend_rect = [
            left_margin / page_width,
            bottom_margin / page_height,
            legend_width / page_width,
            info_height / page_height,
        ]
    title_block_rect = None
    if show_title_block:
        title_left = left_margin
        title_width = available_width
        if rows:
            title_left += available_width * 0.64
            title_width = available_width * 0.36
        title_block_rect = [
            title_left / page_width,
            bottom_margin / page_height,
            title_width / page_width,
            info_height / page_height,
        ]

    return {
        "enabled": True,
        "page_name": page_label,
        "figure_size": (page_width, page_height),
        "requested_horizontal_scale": requested_horizontal,
        "requested_vertical_scale": requested_vertical,
        "horizontal_scale": effective_horizontal,
        "vertical_scale": effective_vertical,
        "vertical_exaggeration": kesit_dusey_abarti(
            effective_horizontal,
            effective_vertical,
        ),
        "requested_fits": requested_fits,
        "fits": effective_fits,
        "adjusted": (
            effective_horizontal != requested_horizontal
            or effective_vertical != requested_vertical
        ),
        "required_horizontal_scale": required_horizontal,
        "required_vertical_scale": required_vertical,
        "axes_size_inches": (axes_width, axes_height),
        "axes_rect": axes_rect,
        "legend_rect": legend_rect,
        "title_block_rect": title_block_rect,
        "legend_rows": rows,
        "show_title_block": bool(show_title_block),
        "x_span_m": x_span,
        "y_span_m": y_span,
    }
