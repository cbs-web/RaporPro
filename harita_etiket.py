# Dosya: RaporPro/harita_etiket.py
"""Matplotlib harita etiketleri icin sinirli cakisma azaltma yardimcilari."""

from __future__ import annotations

from matplotlib.transforms import Bbox


def _kaydirilmis_kutu(bbox, dx, dy):
    return Bbox.from_extents(
        bbox.x0 + dx,
        bbox.y0 + dy,
        bbox.x1 + dx,
        bbox.y1 + dy,
    )


def harita_etiketlerini_ayir(fig, ax, texts, *, enabled=True):
    """Etiketleri ilk uygun yakin konuma tasiyarak belirgin cakismalari azalt."""
    texts = [text for text in texts if text is not None and text.get_visible()]
    if not enabled or len(texts) < 2:
        return 0

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_box = ax.get_window_extent(renderer=renderer)
    accepted = []
    moved = 0
    offsets = [
        (0, 0),
        (0, 12),
        (0, -12),
        (16, 0),
        (-16, 0),
        (16, 12),
        (-16, 12),
        (16, -12),
        (-16, -12),
        (0, 24),
        (0, -24),
        (32, 0),
        (-32, 0),
        (32, 18),
        (-32, 18),
        (32, -18),
        (-32, -18),
        (0, 38),
        (0, -38),
        (48, 0),
        (-48, 0),
    ]

    for text in texts:
        original_position = text.get_position()
        original_display = ax.transData.transform(original_position)
        bbox = text.get_window_extent(renderer=renderer).expanded(1.04, 1.12)
        selected = (0, 0)
        selected_box = bbox

        for dx, dy in offsets:
            candidate = _kaydirilmis_kutu(bbox, dx, dy)
            inside = (
                candidate.x0 >= axes_box.x0
                and candidate.x1 <= axes_box.x1
                and candidate.y0 >= axes_box.y0
                and candidate.y1 <= axes_box.y1
            )
            if inside and not any(candidate.overlaps(other) for other in accepted):
                selected = (dx, dy)
                selected_box = candidate
                break

        if selected != (0, 0):
            display_position = (
                original_display[0] + selected[0],
                original_display[1] + selected[1],
            )
            text.set_position(ax.transData.inverted().transform(display_position))
            moved += 1
        accepted.append(selected_box)

    if moved:
        fig.canvas.draw()
    return moved
