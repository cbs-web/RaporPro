# Dosya: RaporPro/kesit_geometri_kalite.py
import math
from collections import Counter

import numpy as np


def poligon_alani(vertices):
    points = [
        (float(x), float(y))
        for x, y in ([] if vertices is None else vertices)
    ]
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        return 0.0
    return abs(sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )) / 2.0


def _orientation(a, b, c, tolerance=1e-9):
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) <= tolerance:
        return 0
    return 1 if value > 0 else -1


def _on_segment(a, b, p, tolerance=1e-9):
    return (
        min(a[0], b[0]) - tolerance <= p[0] <= max(a[0], b[0]) + tolerance
        and min(a[1], b[1]) - tolerance <= p[1] <= max(a[1], b[1]) + tolerance
    )


def _segments_intersect(a, b, c, d, tolerance=1e-9):
    o1 = _orientation(a, b, c, tolerance)
    o2 = _orientation(a, b, d, tolerance)
    o3 = _orientation(c, d, a, tolerance)
    o4 = _orientation(c, d, b, tolerance)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(a, b, c, tolerance):
        return True
    if o2 == 0 and _on_segment(a, b, d, tolerance):
        return True
    if o3 == 0 and _on_segment(c, d, a, tolerance):
        return True
    if o4 == 0 and _on_segment(c, d, b, tolerance):
        return True
    return False


def poligon_kendiyle_kesisiyor(vertices, tolerance=1e-9):
    points = [
        (float(x), float(y))
        for x, y in ([] if vertices is None else vertices)
    ]
    if len(points) > 1 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    count = len(points)
    if count < 4:
        return False
    for first in range(count):
        a, b = points[first], points[(first + 1) % count]
        for second in range(first + 1, count):
            if second in (first, (first + 1) % count):
                continue
            if first == 0 and second == count - 1:
                continue
            c, d = points[second], points[(second + 1) % count]
            if _segments_intersect(a, b, c, d, tolerance):
                return True
    return False


def kalite_raporlarini_birlestir(*reports):
    merged = {"errors": [], "warnings": [], "info": [], "stats": Counter()}
    for report in reports:
        if not isinstance(report, dict):
            continue
        for key in ("errors", "warnings", "info"):
            merged[key].extend(report.get(key, []) or [])
        merged["stats"].update(report.get("stats", {}) or {})
    return merged


def build_section_geometry_report(fig):
    """Üretilmiş kesit figüründeki gerçek poligon geometrilerini denetler."""
    report = {"errors": [], "warnings": [], "info": [], "stats": Counter()}
    stats = report["stats"]
    tool = getattr(fig, "_geo_tool", None)
    polygons = list(getattr(tool, "polygons", []) or [])
    surface_caps = list(getattr(fig, "_geo_surface_caps", []) or [])
    for cap in surface_caps:
        if cap not in polygons:
            polygons.append(cap)
    stats["geometry_polygons"] = len(polygons)
    stats["surface_caps"] = len(surface_caps)

    for index, polygon in enumerate(polygons, start=1):
        if getattr(polygon, "_geo_hidden", False):
            continue
        if hasattr(polygon, "get_visible") and not polygon.get_visible():
            continue
        try:
            vertices = np.asarray(polygon.get_xy(), dtype=float)
        except Exception:
            report["errors"].append(f"Polygon {index}: köşe koordinatları okunamadı.")
            continue
        if len(vertices) < 3:
            report["errors"].append(f"Polygon {index}: üçten az köşe içeriyor.")
            continue
        if not np.isfinite(vertices).all():
            report["errors"].append(f"Polygon {index}: sonlu olmayan koordinat içeriyor.")
            continue
        area = poligon_alani(vertices)
        if area <= 1e-5:
            stats["zero_area_polygons"] += 1
            report["errors"].append(
                f"Polygon {index}: sıfıra yakın alan ({area:.6f}) oluşturdu."
            )
        if poligon_kendiyle_kesisiyor(vertices):
            stats["self_intersections"] += 1
            edit_id = getattr(polygon, "_geo_edit_id", "") or f"polygon-{index}"
            report["errors"].append(f"{edit_id}: polygon kendi sınırını kesiyor.")

    topography = getattr(fig, "_geo_topography_profile", {}) or {}
    if topography.get("enabled"):
        points = topography.get("points") or []
        stats["topography_points"] = len(points)
        if len(points) < 2:
            report["errors"].append("Topoğrafik profil iki geçerli noktadan az.")
        stations = [
            float(point.get("station"))
            for point in points
            if isinstance(point, dict) and point.get("station") is not None
        ]
        if any(right <= left for left, right in zip(stations, stations[1:])):
            report["errors"].append("Topoğrafik profil station değerleri artan sırada değil.")
        if getattr(fig, "_geo_topography_mask", None) is None:
            report["warnings"].append(
                "Topoğrafya açık ancak yüzey üstü geometrileri temizleyen maske oluşturulmadı."
            )
        expected = int(getattr(fig, "_geo_surface_expected_pair_count", 0) or 0)
        covered = int(getattr(fig, "_geo_surface_covered_pair_count", 0) or 0)
        stats["surface_expected_pairs"] = expected
        stats["surface_covered_pairs"] = covered
        if expected and covered < expected:
            stats["surface_gaps"] = expected - covered
            report["warnings"].append(
                f"Topoğrafik yüzey {expected} sondaj aralığının {covered} tanesinde "
                "üst tabakaya bağlandı; litolojisi 0.00 m'den başlamayan aralık olabilir."
            )
        clamped = int(getattr(fig, "_geo_topography_clamped_count", 0) or 0)
        stats["surface_clamped_points"] = clamped
        if clamped:
            report["warnings"].append(
                f"Topoğrafya {clamped} noktada üst tabakanın alt sınırına yaklaştı; "
                "minimum tabaka kalınlığı uygulandı."
            )
        if surface_caps:
            invalid_curves = 0
            for cap in surface_caps:
                curve = getattr(cap, "_geo_surface_curve", []) or []
                if len(curve) < 2:
                    invalid_curves += 1
                    continue
                if any(
                    not math.isfinite(float(x)) or not math.isfinite(float(y))
                    for x, y in curve
                ):
                    invalid_curves += 1
                    continue
                if any(curve[idx + 1][0] <= curve[idx][0] for idx in range(len(curve) - 1)):
                    invalid_curves += 1
            if invalid_curves:
                stats["invalid_surface_curves"] = invalid_curves
                report["errors"].append(
                    f"{invalid_curves} yüzey tabakası artan station geometrisi oluşturamadı."
                )

    report["info"].append(
        f"Geometri kontrolü: {stats['geometry_polygons']} polygon, "
        f"{stats['surface_caps']} topoğrafik yüzey alanı."
    )
    return report
