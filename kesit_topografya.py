# Dosya: RaporPro/kesit_topografya.py
import math
import re
import xml.etree.ElementTree as ET
from bisect import bisect_right


def _float_value(value):
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value or "").strip().replace(" ", "")
        if not text:
            raise ValueError("bos sayisal deger")
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        result = float(text)
    if not math.isfinite(result):
        raise ValueError("sonlu olmayan sayisal deger")
    return result


def topografya_noktalari_normalize(points):
    """Station/kot noktalarını sıralar ve aynı station kayıtlarını tekilleştirir."""
    normalized = {}
    for item in points or []:
        if isinstance(item, dict):
            station = next(
                (item.get(key) for key in ("station", "sta", "mesafe", "x") if item.get(key) not in (None, "")),
                None,
            )
            elevation = next(
                (item.get(key) for key in ("elevation", "kot", "z", "alt", "altitude") if item.get(key) not in (None, "")),
                None,
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            station, elevation = item[0], item[1]
        else:
            continue
        try:
            station = _float_value(station)
            elevation = _float_value(elevation)
        except (TypeError, ValueError):
            continue
        normalized[round(station, 6)] = {
            "station": station,
            "elevation": elevation,
        }
    return [normalized[key] for key in sorted(normalized)]


def topografya_metnini_oku(text):
    """Excel'den yapıştırılan iki sütunlu station/kot metnini okur."""
    points = []
    invalid_lines = []
    for line_no, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line or ";" in line:
            parts = [part.strip() for part in re.split(r"[\t;]+", line) if part.strip()]
        else:
            parts = [part.strip() for part in re.split(r"\s+", line) if part.strip()]
        if len(parts) < 2:
            invalid_lines.append(line_no)
            continue
        try:
            points.append((_float_value(parts[0]), _float_value(parts[1])))
        except (TypeError, ValueError):
            # Başlık satırları kullanıcı hatası sayılmaz.
            if not any(token in line.casefold() for token in ("station", "sta", "mesafe", "kot", "elevation")):
                invalid_lines.append(line_no)
    return topografya_noktalari_normalize(points), invalid_lines


def kml_yukseklik_noktalari_oku(path, max_points=2000):
    """KML koordinatlarının üçüncü bileşenindeki yükseklikleri okur."""
    if not path:
        return []
    root = ET.parse(path).getroot()
    points = []
    for node in root.iter():
        if not str(node.tag).endswith("coordinates") or not node.text:
            continue
        for token in node.text.replace("\n", " ").split():
            parts = token.split(",")
            if len(parts) < 3:
                continue
            try:
                lon = _float_value(parts[0])
                lat = _float_value(parts[1])
                elevation = _float_value(parts[2])
            except (TypeError, ValueError):
                continue
            points.append({"lat": lat, "lon": lon, "elevation": elevation})
            if len(points) >= max(2, int(max_points or 2000)):
                return points
    return points


def koordinat_noktalarini_profille(points, project_to_line, station_scale=1.0):
    """Koordinat/kot noktalarını kesit hattına izdüşürerek station/kot listesi üretir."""
    if not callable(project_to_line):
        return []
    projected = []
    scale = _float_value(station_scale)
    for item in points or []:
        if not isinstance(item, dict):
            continue
        try:
            lat = _float_value(item.get("lat"))
            lon = _float_value(item.get("lon"))
            elevation = _float_value(item.get("elevation", item.get("alt")))
            station, _offset = project_to_line(lat, lon)
        except (TypeError, ValueError):
            continue
        projected.append({
            "station": float(station) * scale,
            "elevation": elevation,
        })
    return topografya_noktalari_normalize(projected)


def sondaj_noktalarini_profile_ekle(profile, borehole_points, station_tolerance=0.05):
    """Profilin seçili sondaj kotlarından geçmesini garanti eder."""
    merged = topografya_noktalari_normalize(profile)
    tolerance = max(0.0, float(station_tolerance or 0.0))
    for borehole in topografya_noktalari_normalize(borehole_points):
        station = borehole["station"]
        merged = [
            point for point in merged
            if abs(point["station"] - station) > tolerance
        ]
        merged.append(dict(borehole))
    return topografya_noktalari_normalize(merged)


def topografya_profili_hazirla(
    source,
    manual_points,
    coordinate_points,
    borehole_points,
    project_to_line=None,
    station_scale=1.0,
):
    """Seçilen kaynaktan profil üretir; yetersiz veride sondaj kotlarına döner."""
    source = str(source or "sondaj").strip().lower()
    boreholes = topografya_noktalari_normalize(borehole_points)
    warning = ""

    if source == "manual":
        profile = [
            {
                "station": point["station"] * float(station_scale),
                "elevation": point["elevation"],
            }
            for point in topografya_noktalari_normalize(manual_points)
        ]
    elif source == "kml":
        elevations = []
        for point in coordinate_points or []:
            try:
                elevations.append(_float_value(point.get("elevation", point.get("alt"))))
            except (AttributeError, TypeError, ValueError):
                continue
        if not elevations or max(abs(value) for value in elevations) < 0.001:
            profile = []
            warning = "KML dosyasında kullanılabilir yükseklik değeri bulunamadı."
        else:
            profile = koordinat_noktalarini_profille(
                coordinate_points,
                project_to_line,
                station_scale=station_scale,
            )
            if not profile:
                warning = "KML yükseklikleri kesit hattına izdüşürülemedi."
    else:
        profile = list(boreholes)
        source = "sondaj"

    if boreholes:
        low = boreholes[0]["station"]
        high = boreholes[-1]["station"]
        profile = [
            point for point in topografya_noktalari_normalize(profile)
            if low - 0.001 <= point["station"] <= high + 0.001
        ]
    if len(profile) < 2:
        profile = list(boreholes)
        if source != "sondaj" and not warning:
            warning = "Topoğrafik profil için en az iki geçerli nokta gerekli; sondaj kotları kullanıldı."
        source = "sondaj"

    profile = sondaj_noktalarini_profile_ekle(profile, boreholes)
    return {
        "points": profile,
        "source": source,
        "warning": warning,
    }


def topografya_profili_ornekle(points, sample_count=240):
    """Profili doğrusal enterpolasyonla çizime uygun yoğunlukta örnekler."""
    normalized = topografya_noktalari_normalize(points)
    if len(normalized) < 2:
        return (
            [point["station"] for point in normalized],
            [point["elevation"] for point in normalized],
        )
    count = max(len(normalized), int(sample_count or 240))
    x_min = normalized[0]["station"]
    x_max = normalized[-1]["station"]
    if abs(x_max - x_min) < 1e-9:
        return [x_min], [normalized[-1]["elevation"]]

    stations = [point["station"] for point in normalized]
    elevations = [point["elevation"] for point in normalized]
    sample_x = [x_min + (x_max - x_min) * index / (count - 1) for index in range(count)]
    sample_y = []
    for station in sample_x:
        right = min(max(1, bisect_right(stations, station)), len(stations) - 1)
        left = right - 1
        x1, x2 = stations[left], stations[right]
        y1, y2 = elevations[left], elevations[right]
        ratio = 0.0 if abs(x2 - x1) < 1e-12 else (station - x1) / (x2 - x1)
        sample_y.append(y1 + (y2 - y1) * ratio)
    return sample_x, sample_y
