# Dosya: RaporPro/hidrojeoloji_cevre.py
"""Parsel KML'si icin kiyi ve su yolu on degerlendirme motoru."""

from __future__ import annotations

import hashlib
import math
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


EARTH_RADIUS_M = 6_371_008.8
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
COAST_SEARCH_RADII_M = (25_000, 100_000, 300_000)


class CevreAnaliziHatasi(RuntimeError):
    """Cevre verisi okunamadiginda kullaniciya gosterilebilir hata."""


def _local_name(tag):
    return str(tag or "").rsplit("}", 1)[-1]


def _coordinates_text_to_points(text):
    points = []
    for token in str(text or "").replace("\n", " ").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            points.append((lat, lon))
    return points


def kml_halkalarini_oku(path):
    """KML icindeki sirali poligon halkalarini ``(lat, lon)`` olarak oku."""
    if not path or not os.path.isfile(path):
        raise CevreAnaliziHatasi("Parsel KML dosyasi bulunamadi.")
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        raise CevreAnaliziHatasi(f"Parsel KML dosyasi okunamadi: {exc}") from exc

    rings = []
    for polygon in (elem for elem in root.iter() if _local_name(elem.tag) == "Polygon"):
        for elem in polygon.iter():
            if _local_name(elem.tag) != "coordinates":
                continue
            points = _coordinates_text_to_points(elem.text)
            if len(points) < 3:
                continue
            if points[0] != points[-1]:
                points.append(points[0])
            rings.append(points)

    if not rings:
        for elem in root.iter():
            if _local_name(elem.tag) != "coordinates":
                continue
            points = _coordinates_text_to_points(elem.text)
            if len(points) < 3:
                continue
            if points[0] != points[-1]:
                points.append(points[0])
            rings.append(points)

    if not rings:
        raise CevreAnaliziHatasi("KML dosyasinda parsel siniri bulunamadi.")
    return rings


def kml_kimligi(path):
    """KML degisikligini yakalamak icin tasinabilir bir dosya kimligi uret."""
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(128 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _project(point, origin):
    lat, lon = point
    lat0, lon0 = origin
    x = EARTH_RADIUS_M * math.radians(lon - lon0) * math.cos(math.radians(lat0))
    y = EARTH_RADIUS_M * math.radians(lat - lat0)
    return x, y


def _unproject(point, origin):
    x, y = point
    lat0, lon0 = origin
    lat = lat0 + math.degrees(y / EARTH_RADIUS_M)
    cos_lat = max(1e-9, math.cos(math.radians(lat0)))
    lon = lon0 + math.degrees(x / (EARTH_RADIUS_M * cos_lat))
    return lat, lon


def _closest_point_on_segment(point, first, second):
    px, py = point
    ax, ay = first
    bx, by = second
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-18:
        return first
    ratio = ((px - ax) * dx + (py - ay) * dy) / length_sq
    ratio = min(1.0, max(0.0, ratio))
    return ax + ratio * dx, ay + ratio * dy


def _cross(first, second, third):
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _segment_intersection(first_a, first_b, second_a, second_b):
    r = (first_b[0] - first_a[0], first_b[1] - first_a[1])
    s = (second_b[0] - second_a[0], second_b[1] - second_a[1])
    denominator = r[0] * s[1] - r[1] * s[0]
    if abs(denominator) <= 1e-12:
        return None
    delta = (second_a[0] - first_a[0], second_a[1] - first_a[1])
    t = (delta[0] * s[1] - delta[1] * s[0]) / denominator
    u = (delta[0] * r[1] - delta[1] * r[0]) / denominator
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return first_a[0] + t * r[0], first_a[1] + t * r[1]
    return None


def _segment_distance(first_a, first_b, second_a, second_b):
    intersection = _segment_intersection(first_a, first_b, second_a, second_b)
    if intersection is not None:
        return 0.0, intersection, intersection

    choices = []
    for point in (first_a, first_b):
        nearest = _closest_point_on_segment(point, second_a, second_b)
        choices.append((math.dist(point, nearest), point, nearest))
    for point in (second_a, second_b):
        nearest = _closest_point_on_segment(point, first_a, first_b)
        choices.append((math.dist(point, nearest), nearest, point))
    return min(choices, key=lambda item: item[0])


def _segments(points):
    if len(points) == 1:
        return [(points[0], points[0])]
    return list(zip(points, points[1:]))


def geometri_en_kisa_mesafe(parcel_rings, feature_points):
    """Parsel siniri ile cizgi arasindaki en kisa mesafeyi metre olarak hesapla."""
    parcel_points = [point for ring in parcel_rings for point in ring]
    if not parcel_points or not feature_points:
        raise ValueError("Mesafe hesabi icin koordinat bulunamadi.")
    origin = (
        sum(point[0] for point in parcel_points) / len(parcel_points),
        sum(point[1] for point in parcel_points) / len(parcel_points),
    )
    projected_feature = [_project(point, origin) for point in feature_points]
    feature_segments = _segments(projected_feature)

    best = None
    for ring in parcel_rings:
        projected_ring = [_project(point, origin) for point in ring]
        for parcel_segment in _segments(projected_ring):
            for feature_segment in feature_segments:
                candidate = _segment_distance(
                    parcel_segment[0],
                    parcel_segment[1],
                    feature_segment[0],
                    feature_segment[1],
                )
                if best is None or candidate[0] < best[0]:
                    best = candidate
    if best is None:
        raise ValueError("Mesafe hesabi tamamlanamadi.")
    return {
        "mesafe_m": float(best[0]),
        "parsel_noktasi": _unproject(best[1], origin),
        "hedef_noktasi": _unproject(best[2], origin),
    }


def yon_bul(baslangic, hedef):
    """Iki koordinat arasindaki sekizli pusula yonunu dondur."""
    lat1, lon1 = baslangic
    lat2, lon2 = hedef
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    y = math.radians(lat2 - lat1)
    angle = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
    directions = (
        "Kuzey",
        "Kuzeydoğu",
        "Doğu",
        "Güneydoğu",
        "Güney",
        "Güneybatı",
        "Batı",
        "Kuzeybatı",
    )
    return directions[int((angle + 22.5) // 45.0) % 8]


def _truthy_tag(value):
    return str(value or "").strip().casefold() in {"yes", "true", "1", "seasonal"}


def su_yolu_turunu_belirle(tags):
    """OSM etiketlerinden konservatif akar/kuru/belirsiz siniflandirmasi yap."""
    tags = tags if isinstance(tags, dict) else {}
    waterway = str(tags.get("waterway") or "").strip().casefold()
    intermittent = str(tags.get("intermittent") or "").strip().casefold()
    seasonal = str(tags.get("seasonal") or "").strip().casefold()
    if waterway == "wadi" or _truthy_tag(intermittent) or _truthy_tag(seasonal):
        return "kuru"
    if intermittent in {"no", "false", "0"} or seasonal in {"no", "false", "0"}:
        return "akar"
    if waterway in {"river", "canal"}:
        return "akar"
    return "belirsiz"


def _element_points(element):
    geometry = element.get("geometry") if isinstance(element, dict) else None
    points = []
    for point in geometry or []:
        try:
            points.append((float(point["lat"]), float(point["lon"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not points and isinstance(element, dict):
        try:
            points.append((float(element["lat"]), float(element["lon"])))
        except (KeyError, TypeError, ValueError):
            pass
    return points


def overpass_elemanlarini_ayikla(payload):
    """Overpass JSON cevabini analiz motorunun cizgi kayitlarina donustur."""
    records = []
    for element in (payload or {}).get("elements", []):
        points = _element_points(element)
        if not points:
            continue
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        records.append(
            {
                "id": f"{element.get('type', 'item')}-{element.get('id', len(records) + 1)}",
                "ad": str(tags.get("name") or tags.get("ref") or "").strip(),
                "etiketler": dict(tags),
                "noktalar": points,
            }
        )
    return records


class OverpassVeriSaglayici:
    """OpenStreetMap hidrografya verisini Overpass uzerinden saglar."""

    kaynak_adi = "OpenStreetMap / Overpass"
    kaynak_turu = "Açık veri - kullanıcı doğrulaması gerekli"

    def __init__(self, endpoints=None, timeout=35, post=None):
        self.endpoints = tuple(endpoints or OVERPASS_ENDPOINTS)
        self.timeout = max(5, int(timeout))
        self._post = post

    def _sorgula(self, query, task_context=None):
        if self._post is None:
            try:
                import requests
            except Exception as exc:
                raise CevreAnaliziHatasi(f"requests paketi yüklenemedi: {exc}") from exc
            post = requests.post
        else:
            post = self._post

        errors = []
        for endpoint in self.endpoints:
            if task_context is not None:
                task_context.check_cancelled()
            try:
                response = post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "RaporPro/1.0 (hidrojeoloji cevre analizi)",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")
        raise CevreAnaliziHatasi(
            "Hidrografya açık veri servisine ulaşılamadı. " + " | ".join(errors)
        )

    def kiyi_cizgileri(self, lat, lon, task_context=None):
        for radius in COAST_SEARCH_RADII_M:
            if task_context is not None:
                task_context.report(message=f"Kıyı çizgisi aranıyor ({radius // 1000} km)")
            query = (
                "[out:json][timeout:25];"
                f'way["natural"="coastline"](around:{radius},{lat:.8f},{lon:.8f});'
                "out tags geom;"
            )
            records = overpass_elemanlarini_ayikla(
                self._sorgula(query, task_context=task_context)
            )
            if records:
                return records, radius
        return [], COAST_SEARCH_RADII_M[-1]

    def su_yollari(self, lat, lon, radius_m, task_context=None):
        if task_context is not None:
            task_context.report(message=f"Su yolları aranıyor ({int(radius_m)} m)")
        query = (
            "[out:json][timeout:25];("
            f'way["waterway"~"^(river|stream|canal|drain|ditch|wadi)$"]'
            f"(around:{int(math.ceil(radius_m))},{lat:.8f},{lon:.8f});"
            ");out tags geom;"
        )
        return overpass_elemanlarini_ayikla(
            self._sorgula(query, task_context=task_context)
        )


def _parcel_center_and_radius(rings):
    points = [point for ring in rings for point in ring]
    center = (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )
    projected = [_project(point, center) for point in points]
    radius = max((math.hypot(x, y) for x, y in projected), default=0.0)
    return center, radius


def _candidate_record(record, distance_result):
    tags = record.get("etiketler", {})
    waterway = str(tags.get("waterway") or "su yolu").strip()
    kind = su_yolu_turunu_belirle(tags)
    name = record.get("ad") or waterway.replace("_", " ").title()
    return {
        "id": record.get("id", ""),
        "ad": name,
        "tur": kind,
        "su_yolu_turu": waterway,
        "mesafe_m": round(distance_result["mesafe_m"], 1),
        "yon": yon_bul(distance_result["parsel_noktasi"], distance_result["hedef_noktasi"]),
        "parsel_noktasi": list(distance_result["parsel_noktasi"]),
        "hedef_noktasi": list(distance_result["hedef_noktasi"]),
        "etiketler": tags,
        "noktalar": [list(point) for point in record.get("noktalar", [])],
    }


def cevre_analizi_yap(kml_path, inceleme_yaricapi_m=1000, provider=None, task_context=None):
    """Parsel icin deniz ve yakin su yolu adaylarini belirle."""
    try:
        radius = float(str(inceleme_yaricapi_m).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise CevreAnaliziHatasi("İnceleme yarıçapı sayısal olmalıdır.") from exc
    if not 100 <= radius <= 20_000:
        raise CevreAnaliziHatasi("İnceleme yarıçapı 100-20.000 m arasında olmalıdır.")

    rings = kml_halkalarini_oku(kml_path)
    center, parcel_radius = _parcel_center_and_radius(rings)
    provider = provider or OverpassVeriSaglayici()
    if task_context is not None:
        task_context.report(0, 3, "Parsel sınırı okundu")

    coast_records, coast_search_radius = provider.kiyi_cizgileri(
        center[0], center[1], task_context=task_context
    )
    coast_result = None
    for record in coast_records:
        distance = geometri_en_kisa_mesafe(rings, record["noktalar"])
        if coast_result is None or distance["mesafe_m"] < coast_result["mesafe_m"]:
            coast_result = {
                "bulundu": True,
                "mesafe_m": round(distance["mesafe_m"], 1),
                "yon": yon_bul(distance["parsel_noktasi"], distance["hedef_noktasi"]),
                "parsel_noktasi": list(distance["parsel_noktasi"]),
                "hedef_noktasi": list(distance["hedef_noktasi"]),
                "noktalar": [list(point) for point in record["noktalar"]],
            }
    if task_context is not None:
        task_context.report(1, 3, "Kıyı uzaklığı hesaplandı")

    query_radius = radius + parcel_radius
    water_records = provider.su_yollari(
        center[0], center[1], query_radius, task_context=task_context
    )
    candidates = []
    for record in water_records:
        if task_context is not None:
            task_context.check_cancelled()
        distance = geometri_en_kisa_mesafe(rings, record["noktalar"])
        if distance["mesafe_m"] <= radius + 0.05:
            candidates.append(_candidate_record(record, distance))
    candidates.sort(key=lambda item: (item["mesafe_m"], item["ad"].casefold()))
    if task_context is not None:
        task_context.report(2, 3, "Su yolu adayları değerlendirildi")

    warnings = [
        "Açık veri sonucu ön değerlendirmedir; rapora aktarılmadan önce kullanıcı tarafından doğrulanmalıdır."
    ]
    if coast_result is None:
        warnings.append(
            f"{coast_search_radius // 1000} km arama alanında kıyı çizgisi saptanamadı."
        )
        coast_result = {
            "bulundu": False,
            "arama_yaricapi_m": coast_search_radius,
        }
    else:
        coast_result["arama_yaricapi_m"] = coast_search_radius

    result = {
        "surum": 1,
        "durum": "tamamlandi",
        "kaynak": provider.kaynak_adi,
        "kaynak_turu": provider.kaynak_turu,
        "sorgu_tarihi": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "inceleme_yaricapi_m": int(round(radius)),
        "kml_kimligi": kml_kimligi(kml_path),
        "kml_dosya_adi": os.path.basename(kml_path),
        "parsel_merkezi": list(center),
        "parsel_halkalari": [[list(point) for point in ring] for ring in rings],
        "deniz": coast_result,
        "su_yollari": candidates,
        "uyarilar": warnings,
    }
    if task_context is not None:
        task_context.report(3, 3, "Analiz tamamlandı")
    return result


def cevre_analizi_kayit_ozeti(result):
    """Onizleme geometrilerini cikartarak proje dosyasina kaydedilecek ozeti uret."""
    summary = {
        key: value
        for key, value in (result or {}).items()
        if key not in {"parsel_halkalari"}
    }
    sea = dict(summary.get("deniz") or {})
    sea.pop("noktalar", None)
    summary["deniz"] = sea
    waterways = []
    for candidate in summary.get("su_yollari", []):
        item = dict(candidate)
        item.pop("noktalar", None)
        item.pop("etiketler", None)
        waterways.append(item)
    summary["su_yollari"] = waterways
    return summary


def cevre_analizi_guncel_mi(summary, kml_path):
    if not isinstance(summary, dict) or summary.get("durum") != "tamamlandi":
        return False
    identity = str(summary.get("kml_kimligi") or "")
    return bool(identity and identity == kml_kimligi(kml_path))


__all__ = [
    "COAST_SEARCH_RADII_M",
    "CevreAnaliziHatasi",
    "OverpassVeriSaglayici",
    "cevre_analizi_guncel_mi",
    "cevre_analizi_kayit_ozeti",
    "cevre_analizi_yap",
    "geometri_en_kisa_mesafe",
    "kml_halkalarini_oku",
    "kml_kimligi",
    "overpass_elemanlarini_ayikla",
    "su_yolu_turunu_belirle",
    "yon_bul",
]
