import os
import re
import xml.etree.ElementTree as ET

import numpy as np


def ss_harita_etiketi(ad, index):
    """Serim adini haritalarda kullanilan SS-N bicimine donusturur."""
    text = str(ad or "").strip()
    match = re.search(r"(?:serim|ss)\s*[-_:]?\s*(\d+)", text, flags=re.IGNORECASE)
    number = int(match.group(1)) if match else int(index) + 1
    return f"SS-{number}"


def kml_koordinatlari_oku(path, max_points=200):
    if not path or not os.path.exists(path):
        return []
    points = []
    seen = set()
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        for elem in root.iter():
            if "coordinates" not in str(elem.tag):
                continue
            for row in str(elem.text or "").strip().split():
                parts = row.split(",")
                if len(parts) < 2:
                    continue
                try:
                    lon, lat = float(parts[0]), float(parts[1])
                except Exception:
                    continue
                key = (round(lat, 8), round(lon, 8))
                if key in seen:
                    continue
                seen.add(key)
                points.append({"label": f"KML-{len(points) + 1}", "lat": lat, "lon": lon})
                if len(points) >= max_points:
                    return points
    except Exception:
        return []
    return points


def valid_latlon(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return False
    return lat != 0 and lon != 0 and -90 <= lat <= 90 and -180 <= lon <= 180


def affine_from_refs(refs):
    valid = []
    for ref in refs or []:
        coord = ref.get("coord", {})
        pixel = ref.get("pixel", {})
        try:
            lon = float(coord["lon"])
            lat = float(coord["lat"])
            x = float(pixel["x"])
            y = float(pixel["y"])
        except Exception:
            continue
        valid.append((lon, lat, x, y))
    if len(valid) < 3:
        raise ValueError("Otomatik yerleştirme için en az 3 referans noktası gerekir.")

    rows = []
    rhs = []
    for lon, lat, x, y in valid:
        rows.append([lon, lat, 1, 0, 0, 0])
        rhs.append(x)
        rows.append([0, 0, 0, lon, lat, 1])
        rhs.append(y)
    coeff, *_ = np.linalg.lstsq(np.array(rows, dtype=float), np.array(rhs, dtype=float), rcond=None)
    return coeff


def coord_to_pixel(coeff, lat, lon):
    lon = float(lon)
    lat = float(lat)
    return (
        float(coeff[0] * lon + coeff[1] * lat + coeff[2]),
        float(coeff[3] * lon + coeff[4] * lat + coeff[5]),
    )


def pixel_to_coord(coeff, x, y):
    x = float(x)
    y = float(y)
    det = float(coeff[0] * coeff[4] - coeff[1] * coeff[3])
    if abs(det) < 1e-12:
        raise ValueError("Referans dönüşümü çözülemedi. Daha farklı KML köşeleri seçin.")

    rx = x - float(coeff[2])
    ry = y - float(coeff[5])
    lon = (rx * float(coeff[4]) - float(coeff[1]) * ry) / det
    lat = (float(coeff[0]) * ry - rx * float(coeff[3])) / det
    return float(lat), float(lon)
