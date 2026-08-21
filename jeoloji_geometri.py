# Dosya: RaporPro/jeoloji_geometri.py
"""Jeoloji adayları için KML/KMZ ayrıştırma, eşleştirme ve TKGM tamamlama."""

from __future__ import annotations

import copy
from collections import OrderedDict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape


KML_EXTENSIONS = {".kml", ".kmz"}
YAKINLIK_ESIGI_KM = 2.0
KONUM_FARKI_UYARI_KM = 5.0
KOORDINAT_POLIGON_UYUSMAZLIK_KM = 0.25
YAKINDAKILER_DEFAULT_KM = 2.0
HARITA_MOD_SECILI = "selected"
HARITA_MOD_YAKINDAKILER = "nearby"
HARITA_MOD_TUMU = "all"
HARITA_MODLARI = {HARITA_MOD_SECILI, HARITA_MOD_YAKINDAKILER, HARITA_MOD_TUMU}
_MAX_KML_BYTES = 100 * 1024 * 1024
_KML_CACHE_LIMIT = 64
_KML_PARSE_CACHE = OrderedDict()
_KML_PARSE_CACHE_LOCK = threading.Lock()


class JeolojiGeometriHatasi(RuntimeError):
    """KML/KMZ içeriği güvenli bir parsel poligonuna dönüştürülemedi."""


def _text(value):
    return "" if value is None else str(value).strip()


def _clean_space(value):
    return re.sub(r"\s+", " ", _text(value)).strip()


def _fold(value):
    text = unicodedata.normalize("NFKD", _text(value)).replace("ı", "i").replace("İ", "I")
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def konum_normalize_et(value):
    text = _fold(value)
    text = re.sub(
        r"\b(ili|ilcesi|ilce|mahallesi|mahalle|mah|mh|koyu|koy|belde|beldesi)\b",
        " ",
        text,
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _local_name(tag):
    return str(tag or "").rsplit("}", 1)[-1]


def _valid_lon_lat(lon, lat):
    return -180 <= lon <= 180 and -90 <= lat <= 90 and not (lon == 0 and lat == 0)


def _ring_parse(text):
    points = []
    for token in re.split(r"\s+", _text(text)):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except (TypeError, ValueError):
            continue
        if _valid_lon_lat(lon, lat):
            points.append([round(lon, 10), round(lat, 10)])
    if points and points[0] != points[-1]:
        points.append(list(points[0]))
    return points if len(points) >= 4 and len({tuple(item) for item in points[:-1]}) >= 3 else []


def _first_descendant(element, local_name):
    return next((item for item in element.iter() if _local_name(item.tag) == local_name), None)


def _element_text(element, local_name):
    found = _first_descendant(element, local_name)
    return _clean_space("".join(found.itertext())) if found is not None else ""


def _polygon_parse(element):
    outer = None
    inners = []
    for boundary in element.iter():
        local = _local_name(boundary.tag)
        if local not in {"outerBoundaryIs", "innerBoundaryIs"}:
            continue
        coordinates = _first_descendant(boundary, "coordinates")
        ring = _ring_parse(coordinates.text if coordinates is not None else "")
        if not ring:
            continue
        if local == "outerBoundaryIs" and outer is None:
            outer = ring
        elif local == "innerBoundaryIs":
            inners.append(ring)
    return [outer, *inners] if outer else None


def _extended_data_text(placemark):
    values = []
    for element in placemark.iter():
        local = _local_name(element.tag)
        if local not in {"Data", "SimpleData"}:
            continue
        name = _clean_space(element.get("name"))
        value_element = _first_descendant(element, "value") if local == "Data" else element
        value = _clean_space("".join(value_element.itertext())) if value_element is not None else ""
        if value:
            values.append(f"{name}: {value}" if name else value)
    return "\n".join(values)


_SUFFIX_PATTERNS = {
    "il": re.compile(r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+İli\b", re.IGNORECASE),
    "ilce": re.compile(r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+İlçe(?:si)?\b", re.IGNORECASE),
    "mahalle": re.compile(
        r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+(?:Mahallesi|Mahalle|Köyü|Köy)\b",
        re.IGNORECASE,
    ),
    "pafta": re.compile(
        r"(?<![\w])(?P<value>[0-9A-Za-zÇĞİÖŞÜçğıöşü]+(?:\s*[-/]\s*[0-9A-Za-zÇĞİÖŞÜçğıöşü]+){0,3})\s+Pafta\b",
        re.IGNORECASE,
    ),
    "ada": re.compile(r"(?<![\w])(?P<value>\d+)\s+Ada\b", re.IGNORECASE),
    "parsel": re.compile(r"(?<![\w])(?P<value>\d+)\s+Parsel\b", re.IGNORECASE),
}
_LABELS = {
    "il": ("İl", "Il"),
    "ilce": ("İlçe", "Ilce", "İlçesi", "Ilcesi"),
    "mahalle": ("Mahalle", "Mahallesi", "Köy", "Köyü"),
    "pafta": ("Pafta", "Pafta No"),
    "ada": ("Ada", "Ada No"),
    "parsel": ("Parsel", "Parsel No"),
}
_FILENAME_PARCEL_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,6})\s*[_-]\s*(\d{1,6})(?![A-Za-z0-9])")


def _label_value(text, labels):
    alternatives = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(
        rf"(?:^|[\n;,|])\s*(?:{alternatives})\s*(?:no|numarası|numarasi)?\s*[:=\-]\s*([^\n;,|]+)",
        re.IGNORECASE,
    )
    match = pattern.search(text or "")
    return _clean_space(match.group(1)).strip(" .") if match else ""


def kml_kimligi_cikar(text, filename=""):
    """Placemark metninden konum kimliği çıkar; dosya adı yalnız ada/parsel fallback'idir."""
    result = {}
    for key, labels in _LABELS.items():
        value = _label_value(text, labels)
        if not value:
            match = _SUFFIX_PATTERNS[key].search(text or "")
            value = _clean_space(match.group("value")).strip(" .") if match else ""
        if value:
            result[key] = value
    if not result.get("ada") or not result.get("parsel"):
        stem = Path(filename or "").stem
        matches = list(_FILENAME_PARCEL_RE.finditer(stem))
        if matches:
            match = matches[-1]
            ada, parsel = match.group(1), match.group(2)
            if not (len(ada) == 4 and 1900 <= int(ada) <= 2100):
                result.setdefault("ada", ada)
                result.setdefault("parsel", parsel)
    return result


def _canonical_ring(ring):
    points = [tuple(round(float(value), 8) for value in point[:2]) for point in ring or []]
    if points and points[0] == points[-1]:
        points.pop()
    if not points:
        return []
    rotations = []
    for sequence in (points, list(reversed(points))):
        for index in range(len(sequence)):
            rotations.append(tuple(sequence[index:] + sequence[:index]))
    chosen = min(rotations)
    return [list(point) for point in (*chosen, chosen[0])]


def _canonical_polygons(polygons):
    canonical = []
    for polygon in polygons or []:
        if not polygon:
            continue
        outer = _canonical_ring(polygon[0])
        if not outer:
            continue
        inner = sorted((_canonical_ring(ring) for ring in polygon[1:]), key=lambda item: json.dumps(item))
        canonical.append([outer, *[ring for ring in inner if ring]])
    return sorted(canonical, key=lambda item: json.dumps(item, separators=(",", ":")))


def geometri_hash_hesapla(polygons):
    payload = json.dumps(_canonical_polygons(polygons), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def geometri_ozeti(polygons):
    outer_points = []
    weighted_centroids = []
    for polygon in polygons or []:
        if not polygon or not polygon[0]:
            continue
        ring = polygon[0][:-1] if polygon[0][0] == polygon[0][-1] else polygon[0]
        outer_points.extend(ring)
        twice_area = 0.0
        centroid_lon = 0.0
        centroid_lat = 0.0
        for index, point in enumerate(ring):
            following = ring[(index + 1) % len(ring)]
            cross = float(point[0]) * float(following[1]) - float(following[0]) * float(point[1])
            twice_area += cross
            centroid_lon += (float(point[0]) + float(following[0])) * cross
            centroid_lat += (float(point[1]) + float(following[1])) * cross
        if abs(twice_area) > 1e-14:
            weighted_centroids.append(
                (
                    abs(twice_area),
                    centroid_lat / (3.0 * twice_area),
                    centroid_lon / (3.0 * twice_area),
                )
            )
    if not outer_points:
        raise JeolojiGeometriHatasi("KML içinde geçerli Polygon/MultiPolygon sınırı bulunamadı.")
    lons = [float(point[0]) for point in outer_points]
    lats = [float(point[1]) for point in outer_points]
    if weighted_centroids:
        total_weight = sum(item[0] for item in weighted_centroids)
        centroid = [
            sum(weight * lat for weight, lat, _lon in weighted_centroids) / total_weight,
            sum(weight * lon for weight, _lat, lon in weighted_centroids) / total_weight,
        ]
    else:
        centroid = [sum(lats) / len(lats), sum(lons) / len(lons)]
    return {
        "centroid": centroid,
        "bounds": [min(lats), min(lons), max(lats), max(lons)],
        "polygon_count": len(polygons),
        "ring_count": sum(len(polygon) for polygon in polygons),
        "point_count": sum(len(ring) for polygon in polygons for ring in polygon),
    }


def _geometri_kaydi(polygons, path, placemark_name, description, extended_data, index):
    summary = geometri_ozeti(polygons)
    source_text = "\n".join(
        item for item in (placemark_name, description, extended_data, Path(path).stem) if item
    )
    identity = kml_kimligi_cikar(source_text, Path(path).name)
    return {
        "polygons": polygons,
        "geometry_hash": geometri_hash_hesapla(polygons),
        "centroid": summary["centroid"],
        "bounds": summary["bounds"],
        "polygon_count": summary["polygon_count"],
        "ring_count": summary["ring_count"],
        "point_count": summary["point_count"],
        "source_path": str(Path(path).absolute()),
        "source_type": "local_kmz" if Path(path).suffix.lower() == ".kmz" else "local_kml",
        "placemark_name": placemark_name or f"Placemark {index}",
        "description": description,
        "extended_data": extended_data,
        "identity": identity,
    }


def _kml_bytes_oku(path):
    path = Path(path)
    if path.suffix.lower() == ".kml":
        if path.stat().st_size > _MAX_KML_BYTES:
            raise JeolojiGeometriHatasi("KML dosyası güvenli okuma sınırını aşıyor.")
        return path.read_bytes()
    if path.suffix.lower() != ".kmz":
        raise JeolojiGeometriHatasi("Yalnız KML/KMZ dosyaları okunabilir.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = [item for item in archive.infolist() if item.filename.lower().endswith(".kml")]
            if not members:
                raise JeolojiGeometriHatasi("KMZ içinde KML belgesi bulunamadı.")
            members.sort(key=lambda item: (Path(item.filename).name.lower() != "doc.kml", item.filename.lower()))
            member = members[0]
            if member.file_size > _MAX_KML_BYTES:
                raise JeolojiGeometriHatasi("KMZ içindeki KML güvenli okuma sınırını aşıyor.")
            return archive.read(member)
    except zipfile.BadZipFile as exc:
        raise JeolojiGeometriHatasi("KMZ arşivi bozuk veya okunamıyor.") from exc


def _kml_cache_key(path):
    path = Path(path).absolute()
    stat = path.stat()
    return os.path.normcase(str(path)), int(stat.st_mtime_ns), int(stat.st_size)


def kml_onbellegini_temizle():
    with _KML_PARSE_CACHE_LOCK:
        _KML_PARSE_CACHE.clear()


def kml_geometrilerini_oku(path):
    """KML/KMZ içindeki her poligonlu Placemark'i normalize geometri olarak döndür."""
    cache_key = _kml_cache_key(path)
    with _KML_PARSE_CACHE_LOCK:
        cached = _KML_PARSE_CACHE.get(cache_key)
        if cached is not None:
            _KML_PARSE_CACHE.move_to_end(cache_key)
            return copy.deepcopy(cached)
    try:
        root = ET.fromstring(_kml_bytes_oku(path))
    except ET.ParseError as exc:
        raise JeolojiGeometriHatasi(f"KML XML yapısı bozuk: {exc}") from exc

    records = []
    placemarks = [item for item in root.iter() if _local_name(item.tag) == "Placemark"]
    for index, placemark in enumerate(placemarks, start=1):
        polygons = []
        for element in placemark.iter():
            if _local_name(element.tag) != "Polygon":
                continue
            polygon = _polygon_parse(element)
            if polygon:
                polygons.append(polygon)
        if not polygons:
            continue
        records.append(
            _geometri_kaydi(
                polygons,
                path,
                _element_text(placemark, "name"),
                _element_text(placemark, "description"),
                _extended_data_text(placemark),
                index,
            )
        )
    if not records:
        polygons = []
        for element in root.iter():
            if _local_name(element.tag) == "Polygon":
                polygon = _polygon_parse(element)
                if polygon:
                    polygons.append(polygon)
        if polygons:
            records.append(_geometri_kaydi(polygons, path, Path(path).stem, "", "", 1))
    if not records:
        raise JeolojiGeometriHatasi("KML/KMZ içinde çizilebilir Polygon veya MultiPolygon bulunamadı.")
    with _KML_PARSE_CACHE_LOCK:
        _KML_PARSE_CACHE[cache_key] = copy.deepcopy(records)
        _KML_PARSE_CACHE.move_to_end(cache_key)
        while len(_KML_PARSE_CACHE) > _KML_CACHE_LIMIT:
            _KML_PARSE_CACHE.popitem(last=False)
    return records


def geometri_dosyalari_bul(kaynaklar, recursive=True):
    if isinstance(kaynaklar, (str, os.PathLike)):
        kaynaklar = [kaynaklar]
    found = {}
    sibling_dirs = set()
    for raw_path in kaynaklar or []:
        path = Path(raw_path)
        if path.is_file():
            if path.suffix.lower() in KML_EXTENSIONS:
                candidates = (path,)
            else:
                sibling_dirs.add(path.parent)
                candidates = ()
        elif path.is_dir():
            if recursive:
                candidates = (
                    Path(root) / filename
                    for root, _directories, filenames in os.walk(path, followlinks=False)
                    for filename in filenames
                )
            else:
                try:
                    candidates = tuple(path.iterdir())
                except OSError:
                    candidates = ()
        else:
            continue
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in KML_EXTENSIONS:
                absolute = Path(os.path.abspath(str(candidate)))
                found.setdefault(os.path.normcase(str(absolute)), absolute)
    for directory in sibling_dirs:
        try:
            candidates = directory.iterdir()
        except OSError:
            continue
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in KML_EXTENSIONS:
                absolute = Path(os.path.abspath(str(candidate)))
                found.setdefault(os.path.normcase(str(absolute)), absolute)
    return sorted(found.values(), key=lambda item: (_fold(item.name), _fold(str(item))))


def geometri_katalogu_olustur(kaynaklar, recursive=True):
    geometries, errors = [], []
    paths = geometri_dosyalari_bul(kaynaklar, recursive=recursive)
    for path in paths:
        try:
            geometries.extend(kml_geometrilerini_oku(path))
        except (OSError, JeolojiGeometriHatasi) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return {"geometries": geometries, "errors": errors, "paths": [str(path) for path in paths]}


def haversine_km(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _location_conflict(candidate, geometry):
    identity = geometry.get("identity") or {}
    for key in ("il", "ilce", "mahalle"):
        word_value = konum_normalize_et(candidate.get(key))
        geometry_value = konum_normalize_et(identity.get(key))
        if word_value and geometry_value and word_value != geometry_value:
            return key
    return ""


def _path_context_rank(word_path, geometry_path):
    try:
        word_dir = Path(word_path).resolve().parent
        geometry_dir = Path(geometry_path).resolve().parent
    except OSError:
        word_dir = Path(word_path).absolute().parent
        geometry_dir = Path(geometry_path).absolute().parent
    if word_dir == geometry_dir:
        return 100
    if word_dir in geometry_dir.parents:
        return max(70, 90 - (len(geometry_dir.parents) - len(word_dir.parents)) * 5)
    if geometry_dir in word_dir.parents:
        return max(45, 65 - (len(word_dir.parents) - len(geometry_dir.parents)) * 5)
    try:
        common = Path(os.path.commonpath((str(word_dir), str(geometry_dir))))
        word_gap = len(word_dir.relative_to(common).parts)
        geometry_gap = len(geometry_dir.relative_to(common).parts)
        return max(0, 35 - (word_gap + geometry_gap) * 5)
    except (OSError, ValueError):
        return 0


def _warning_add(candidate, message):
    warnings = candidate.setdefault("warnings", [])
    if message not in warnings:
        warnings.append(message)
    analysis = candidate.get("analysis")
    if isinstance(analysis, dict):
        analysis_warnings = analysis.setdefault("warnings", [])
        if message not in analysis_warnings:
            analysis_warnings.append(message)
        analysis["quality_warnings"] = list(analysis_warnings)


def _candidate_coordinate(candidate):
    lat, lon = candidate.get("lat"), candidate.get("lon")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def aday_geometrisini_sec(candidate, geometry, status="local_selected"):
    """Seçili geometriyi adaya bağla; Word kimlik metadatasını değiştirme."""
    selected = copy.deepcopy(geometry)
    candidate["geometry"] = selected
    candidate["geometry_hash"] = selected.get("geometry_hash", "")
    candidate["geometry_source"] = selected.get("source_type", "local_kml")
    candidate["geometry_status"] = status
    candidate["geometry_label"] = selected.get("placemark_name") or Path(selected.get("source_path", "")).name
    candidate["geometry_metadata"] = {
        key: copy.deepcopy(selected.get(key))
        for key in (
            "polygons", "centroid", "bounds", "polygon_count", "ring_count", "point_count",
            "identity", "placemark_name", "description", "source_path", "source_type",
            "match_type", "match_distance_km",
        )
        if selected.get(key) is not None
    }
    coordinate = _candidate_coordinate(candidate)
    centroid = selected.get("centroid") or []
    if coordinate is None and len(centroid) >= 2:
        candidate["lat"], candidate["lon"] = float(centroid[0]), float(centroid[1])
        candidate["coordinate_source"] = "kml_centroid"
        analysis = candidate.get("analysis")
        if isinstance(analysis, dict):
            analysis["lat"], analysis["lon"] = candidate["lat"], candidate["lon"]
            analysis["coordinate_source"] = "kml_centroid"
        _warning_add(candidate, "Word koordinatı bulunamadı; harita merkezi seçilen KML poligon merkezinden tamamlandı.")
    elif coordinate is not None and len(centroid) >= 2:
        distance = haversine_km(coordinate[0], coordinate[1], centroid[0], centroid[1])
        selected["word_centroid_distance_km"] = distance
        candidate["geometry_metadata"]["word_centroid_distance_km"] = distance
        if distance is not None and distance > KONUM_FARKI_UYARI_KM:
            _warning_add(candidate, f"Word koordinatı ile parsel merkezi arasında {distance:.1f} km fark var; sınırı kontrol edin.")
    return candidate


def _auto_option(options):
    if not options:
        return None
    unique_hashes = {item.get("geometry_hash") for item in options}
    if len(unique_hashes) == 1:
        return options[0]
    if len(options) == 1:
        return options[0]
    ranked = sorted(options, key=lambda item: item.get("context_rank", 0), reverse=True)
    if ranked[0].get("context_rank", 0) > ranked[1].get("context_rank", 0):
        return ranked[0]
    return None


def adayi_yerel_geometriyle_eslestir(candidate, geometries, proximity_km=YAKINLIK_ESIGI_KM):
    """Word kimliğini esas alarak yerel KML seçeneklerini eşleştir."""
    candidate["geometry"] = None
    candidate["geometry_options"] = []
    candidate["geometry_source"] = ""
    candidate["geometry_hash"] = ""
    candidate["geometry_status"] = "missing"
    candidate["geometry_label"] = "Sınır bulunamadı"
    if not candidate.get("eligible"):
        candidate["geometry_status"] = "not_applicable"
        candidate["geometry_label"] = "2. JEOLOJİ uygun değil"
        return candidate

    word_ada, word_parsel = _text(candidate.get("ada")), _text(candidate.get("parsel"))
    exact, proximity = [], []
    identity_conflicts = []
    coordinate = _candidate_coordinate(candidate)
    for original in geometries or []:
        geometry = copy.deepcopy(original)
        identity = geometry.get("identity") or {}
        geom_ada, geom_parsel = _text(identity.get("ada")), _text(identity.get("parsel"))
        conflict = _location_conflict(candidate, geometry)
        if word_ada and word_parsel and geom_ada == word_ada and geom_parsel == word_parsel:
            if conflict:
                identity_conflicts.append((geometry, conflict))
                continue
            geometry["match_type"] = "ada_parsel"
            geometry["context_rank"] = _path_context_rank(candidate.get("source_path", ""), geometry.get("source_path", ""))
            if coordinate and geometry.get("centroid"):
                geometry["match_distance_km"] = haversine_km(*coordinate, *geometry["centroid"])
            exact.append(geometry)
            continue
        if geom_ada or geom_parsel or conflict or coordinate is None or int(geometry.get("polygon_count") or 0) != 1:
            continue
        centroid = geometry.get("centroid") or []
        if len(centroid) < 2:
            continue
        distance = haversine_km(*coordinate, centroid[0], centroid[1])
        if distance is not None and distance <= float(proximity_km):
            geometry["match_type"] = "coordinate_proximity"
            geometry["match_distance_km"] = distance
            geometry["context_rank"] = _path_context_rank(candidate.get("source_path", ""), geometry.get("source_path", ""))
            proximity.append(geometry)

    options = exact or proximity
    options.sort(key=lambda item: (-int(item.get("context_rank") or 0), float(item.get("match_distance_km") or 0)))
    candidate["geometry_options"] = options
    selected = _auto_option(options)
    if selected is not None:
        if selected.get("match_type") == "coordinate_proximity":
            status = "local_proximity"
            _warning_add(candidate, "KML kimliği okunamadı; tek poligon Word koordinatına yakınlığıyla yardımcı eşleşti. Sınırı kontrol edin.")
        else:
            status = "local_exact"
        return aday_geometrisini_sec(candidate, selected, status=status)
    if options:
        candidate["geometry_status"] = "ambiguous"
        candidate["geometry_label"] = f"{len(options)} olası KML; kullanıcı seçimi gerekli"
        _warning_add(candidate, "Birden fazla olası parsel KML'si bulundu; otomatik sınır seçilmedi.")
    elif identity_conflicts:
        candidate["geometry_status"] = "location_mismatch"
        candidate["geometry_label"] = "Ada/parsel aynı, konum uyuşmuyor"
        _warning_add(candidate, "Ada/parsel eşleşen KML'nin ilçe veya mahalle bilgisi Word metadata'sıyla uyuşmadı; sınır bağlanmadı.")
    else:
        _warning_add(candidate, "Yerel parsel sınırı bulunamadı; TKGM ile tekrar denenebilir.")
    return candidate


def adaylari_yerel_geometriyle_eslestir(candidates, catalog):
    geometries = catalog.get("geometries", []) if isinstance(catalog, dict) else list(catalog or [])
    for candidate in candidates or []:
        adayi_yerel_geometriyle_eslestir(candidate, geometries)
    return candidates


def aday_tkgm_icin_yeterli(candidate):
    return bool(
        candidate.get("eligible")
        and all(_text(candidate.get(key)) for key in ("il", "ilce", "mahalle", "ada", "parsel"))
    )


def parsel_kimlik_anahtari(candidate):
    return tuple(
        konum_normalize_et(candidate.get(key)) if key in {"il", "ilce", "mahalle"} else _text(candidate.get(key))
        for key in ("il", "ilce", "mahalle", "ada", "parsel")
    )


def _tkgm_geometrisi_getir(candidate, resolver):
    kunye = {
        "il": candidate.get("il", ""),
        "ilce": candidate.get("ilce", ""),
        "mahalle": candidate.get("mahalle", ""),
        "ada": candidate.get("ada", ""),
        "parsel": candidate.get("parsel", ""),
    }
    with tempfile.TemporaryDirectory(prefix="raporpro_jeoloji_tkgm_") as temp_dir:
        result = resolver(kunye, temp_dir)
        if isinstance(result, dict) and isinstance(result.get("geometry"), dict):
            geometry = copy.deepcopy(result["geometry"])
            conflict = _location_conflict(candidate, geometry)
            identity = geometry.get("identity") or {}
            for key in ("ada", "parsel"):
                expected = _text(candidate.get(key))
                actual = _text(identity.get(key))
                if expected and actual and expected != actual:
                    raise JeolojiGeometriHatasi("TKGM sonucu istenen ada/parsel kimliğiyle uyuşmuyor.")
            if conflict:
                raise JeolojiGeometriHatasi("TKGM sonucu istenen il/ilçe/mahalle kimliğiyle uyuşmuyor.")
            geometry.setdefault("source_type", "tkgm")
            return geometry
        path = result.get("path") if isinstance(result, dict) else result
        if not path:
            raise JeolojiGeometriHatasi("TKGM çözümleyicisi KML yolu döndürmedi.")
        entries = kml_geometrilerini_oku(path)
        compatible = []
        identity_free = []
        for entry in entries:
            identity = entry.get("identity") or {}
            mismatch = _location_conflict(candidate, entry)
            for key in ("ada", "parsel"):
                expected = _text(candidate.get(key))
                actual = _text(identity.get(key))
                if expected and actual and expected != actual:
                    mismatch = mismatch or key
            if mismatch:
                continue
            if _text(identity.get("ada")) or _text(identity.get("parsel")):
                compatible.append(entry)
            else:
                identity_free.append(entry)
        selected_entries = compatible or (identity_free if len(entries) == 1 else [])
        if not selected_entries:
            raise JeolojiGeometriHatasi("TKGM KML sonucu istenen parsel kimliğiyle doğrulanamadı.")
        polygons = [polygon for entry in selected_entries for polygon in entry.get("polygons", [])]
        summary = geometri_ozeti(polygons)
        return {
            "polygons": polygons,
            "geometry_hash": geometri_hash_hesapla(polygons),
            "centroid": summary["centroid"],
            "bounds": summary["bounds"],
            "polygon_count": summary["polygon_count"],
            "ring_count": summary["ring_count"],
            "point_count": summary["point_count"],
            "source_path": "",
            "source_type": "tkgm",
            "placemark_name": result.get("label", "TKGM Parsel") if isinstance(result, dict) else "TKGM Parsel",
            "description": "TKGM parsel sorgusundan üretildi.",
            "identity": {key: _text(candidate.get(key)) for key in ("il", "ilce", "mahalle", "ada", "parsel")},
            "match_type": "tkgm",
        }


def eksik_geometrileri_tkgmden_tamamla(candidates, resolver, progress=None):
    """Eksik uygun adayları benzersiz parsel başına tek TKGM çağrısıyla tamamla."""
    groups = {}
    skipped = 0
    for candidate in candidates or []:
        if candidate.get("geometry") or candidate.get("geometry_status") == "ambiguous":
            continue
        if not aday_tkgm_icin_yeterli(candidate):
            if candidate.get("eligible"):
                candidate["geometry_status"] = "insufficient_metadata"
                candidate["geometry_label"] = "TKGM için konum/ada/parsel eksik"
            skipped += 1
            continue
        groups.setdefault(parsel_kimlik_anahtari(candidate), []).append(candidate)

    completed, failed = 0, 0
    items = list(groups.items())
    for index, (_key, grouped_candidates) in enumerate(items, start=1):
        representative = grouped_candidates[0]
        error = ""
        geometry = None
        try:
            geometry = _tkgm_geometrisi_getir(representative, resolver)
        except Exception as exc:
            error = str(exc)
        if geometry is not None:
            for candidate in grouped_candidates:
                aday_geometrisini_sec(candidate, geometry, status="tkgm")
                candidate["geometry_source"] = "tkgm"
                candidate["geometry_label"] = geometry.get("placemark_name") or "TKGM Parsel"
            completed += len(grouped_candidates)
        else:
            for candidate in grouped_candidates:
                candidate["geometry_status"] = "tkgm_error"
                candidate["geometry_label"] = "Sınır bulunamadı / TKGM tekrar denenebilir"
                _warning_add(candidate, f"TKGM parsel sınırı alınamadı: {error}")
            failed += len(grouped_candidates)
        if callable(progress):
            progress(index, len(items), representative, geometry is not None, error)
    return {"completed": completed, "failed": failed, "skipped": skipped, "queries": len(items)}


def _ring_kml(ring):
    return " ".join(f"{float(point[0]):.8f},{float(point[1]):.8f},0" for point in ring or [])


def normalize_kml_metni(geometry, name="Parsel Sınırı", metadata=None):
    polygons = geometry.get("polygons") if isinstance(geometry, dict) else None
    if not polygons:
        raise JeolojiGeometriHatasi("Normalize edilecek parsel poligonu bulunamadı.")
    polygon_parts = []
    for polygon in polygons:
        if not polygon or not polygon[0]:
            continue
        inner_parts = []
        for ring in polygon[1:]:
            inner_parts.append(
                "<innerBoundaryIs><LinearRing><coordinates>"
                + _ring_kml(ring)
                + "</coordinates></LinearRing></innerBoundaryIs>"
            )
        polygon_parts.append(
            "<Polygon><tessellate>1</tessellate>"
            "<outerBoundaryIs><LinearRing><coordinates>"
            + _ring_kml(polygon[0])
            + "</coordinates></LinearRing></outerBoundaryIs>"
            + "".join(inner_parts)
            + "</Polygon>"
        )
    if not polygon_parts:
        raise JeolojiGeometriHatasi("Normalize edilecek geçerli poligon halkası bulunamadı.")
    data_parts = []
    for key, value in (metadata or {}).items():
        if value in (None, ""):
            continue
        data_parts.append(f'<Data name="{escape(str(key))}"><value>{escape(str(value))}</value></Data>')
    geometry_xml = polygon_parts[0] if len(polygon_parts) == 1 else "<MultiGeometry>" + "".join(polygon_parts) + "</MultiGeometry>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        '<Style id="parsel"><LineStyle><color>ffcc5500</color><width>3</width></LineStyle>'
        '<PolyStyle><color>2600aaff</color></PolyStyle></Style>'
        f"<Placemark><name>{escape(name)}</name><styleUrl>#parsel</styleUrl>"
        + ("<ExtendedData>" + "".join(data_parts) + "</ExtendedData>" if data_parts else "")
        + geometry_xml
        + "</Placemark></Document></kml>\n"
    )


def normalize_kml_yaz(geometry, target_path, name="Parsel Sınırı", metadata=None):
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.{os.getpid()}.tmp"
    try:
        staged.write_text(normalize_kml_metni(geometry, name=name, metadata=metadata), encoding="utf-8", newline="\n")
        os.replace(staged, target)
    finally:
        try:
            staged.unlink()
        except OSError:
            pass
    return target


def geometri_harita_halkalari(record_or_geometry):
    geometry = record_or_geometry or {}
    if not geometry.get("polygons"):
        metadata = geometry.get("geometry_metadata") if isinstance(geometry.get("geometry_metadata"), dict) else {}
        geometry = metadata
    return [
        [[float(point[1]), float(point[0])] for point in ring]
        for polygon in geometry.get("polygons", []) or []
        for ring in polygon
        if ring
    ]


def _harita_cache_anahtari(record_or_geometry):
    value = record_or_geometry or {}
    metadata = value.get("geometry_metadata") if isinstance(value, dict) else None
    geometry = metadata if isinstance(metadata, dict) and metadata.get("polygons") else value
    geometry_hash = str(
        geometry.get("geometry_hash")
        or value.get("geometry_hash")
        or ""
    ).strip()
    polygons = geometry.get("polygons") or []
    return ("hash", geometry_hash) if geometry_hash else ("memory", id(polygons))


def geometri_harita_poligonlari(record_or_geometry, cache=None):
    geometry = record_or_geometry or {}
    if not geometry.get("polygons"):
        metadata = geometry.get("geometry_metadata") if isinstance(geometry.get("geometry_metadata"), dict) else {}
        geometry = metadata
    cache_key = _harita_cache_anahtari(record_or_geometry)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    polygons = [
        [
            [[float(point[1]), float(point[0])] for point in ring]
            for ring in polygon
            if ring
        ]
        for polygon in geometry.get("polygons", []) or []
        if polygon
    ]
    if cache is not None:
        cache[cache_key] = polygons
    return polygons


def harita_kayitlarini_ayir(records, cache=None):
    """Poligonlu kayıtları merkez marker fallback listesinden kesin olarak ayır."""
    geometry_records = []
    marker_records = []
    for record in records or []:
        polygons = geometri_harita_poligonlari(record, cache=cache)
        if polygons:
            geometry_records.append((record, polygons))
            continue
        try:
            lat, lon = float(record.get("lat")), float(record.get("lon"))
        except (TypeError, ValueError):
            continue
        marker_records.append((record, lat, lon))
    return geometry_records, marker_records


def _geometri_verisi(record_or_geometry):
    value = record_or_geometry if isinstance(record_or_geometry, dict) else {}
    if value.get("polygons"):
        return value
    selected_geometry = value.get("geometry")
    if isinstance(selected_geometry, dict) and selected_geometry.get("polygons"):
        return selected_geometry
    metadata = value.get("geometry_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _latlon_cifti(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return (lat, lon) if _valid_lon_lat(lon, lat) else None


def kayit_harita_ozeti(record, cache=None):
    """Harita merkezinde poligonu, yalnız sınır yoksa kayıt koordinatını esas al."""
    record = record if isinstance(record, dict) else {}
    geometry = _geometri_verisi(record)
    polygons = geometri_harita_poligonlari(geometry, cache=cache)
    if polygons:
        centroid = geometry.get("centroid") or []
        center = _latlon_cifti(
            centroid[0] if len(centroid) >= 2 else None,
            centroid[1] if len(centroid) >= 2 else None,
        )
        bounds = geometry.get("bounds") or []
        try:
            bounds = tuple(float(value) for value in bounds[:4])
            valid_bounds = len(bounds) == 4 and bounds[0] <= bounds[2] and bounds[1] <= bounds[3]
        except (TypeError, ValueError):
            valid_bounds = False
        if center is None or not valid_bounds:
            points = [point for polygon in polygons for ring in polygon for point in ring]
            if not points:
                return {"kind": "none", "center": None, "bounds": None, "polygons": []}
            lats = [float(point[0]) for point in points]
            lons = [float(point[1]) for point in points]
            if center is None:
                center = (sum(lats) / len(lats), sum(lons) / len(lons))
            if not valid_bounds:
                bounds = (min(lats), min(lons), max(lats), max(lons))
        return {
            "kind": "polygon",
            "center": center,
            "bounds": tuple(bounds),
            "polygons": polygons,
            "geometry_hash": str(geometry.get("geometry_hash") or record.get("geometry_hash") or ""),
        }
    center = _latlon_cifti(record.get("lat"), record.get("lon"))
    return {
        "kind": "fallback" if center else "none",
        "center": center,
        "bounds": (*center, *center) if center else None,
        "polygons": [],
        "geometry_hash": "",
    }


def koordinat_poligon_uyusmazligi(record, esik_km=KOORDINAT_POLIGON_UYUSMAZLIK_KM, cache=None):
    """DB koordinatı ile poligon merkezini karşılaştırır; hiçbir veriyi değiştirmez."""
    map_summary = kayit_harita_ozeti(record, cache=cache)
    record_coordinate = _latlon_cifti((record or {}).get("lat"), (record or {}).get("lon"))
    polygon_centroid = map_summary.get("center") if map_summary.get("kind") == "polygon" else None
    distance = (
        haversine_km(*record_coordinate, *polygon_centroid)
        if record_coordinate and polygon_centroid
        else None
    )
    threshold = max(0.0, float(esik_km))
    return {
        "has_polygon": polygon_centroid is not None,
        "record_coordinate": record_coordinate,
        "polygon_centroid": polygon_centroid,
        "distance_km": distance,
        "threshold_km": threshold,
        "mismatch": bool(distance is not None and distance > threshold),
    }


def koordinat_poligon_uyari_metni(record, esik_km=KOORDINAT_POLIGON_UYUSMAZLIK_KM, cache=None):
    check = koordinat_poligon_uyusmazligi(record, esik_km=esik_km, cache=cache)
    if not check["mismatch"]:
        return ""
    distance_m = check["distance_km"] * 1000.0
    return (
        f"Koordinat/poligon uyuşmazlığı: kayıt koordinatı parsel merkezinden "
        f"{distance_m:.0f} m uzakta; haritada poligon esas alındı."
    )


def _harita_kayit_anahtari(record, index, key_field):
    value = record.get(key_field) if isinstance(record, dict) else None
    return index if value is None else value


def _harita_bounds_birlestir(items):
    bounds = [item.get("bounds") for item in items if item.get("bounds")]
    if not bounds:
        return None
    return (
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    )


def harita_gorunum_modeli(
    records,
    selected_key=None,
    mode=HARITA_MOD_SECILI,
    radius_km=None,
    key_field="id",
    cache=None,
):
    """Tk bağımsız görünür kayıt setini ve fit sınırını üret."""
    mode = mode if mode in HARITA_MODLARI else HARITA_MOD_SECILI
    try:
        radius = float(radius_km) if radius_km not in (None, "") else YAKINDAKILER_DEFAULT_KM
    except (TypeError, ValueError):
        radius = YAKINDAKILER_DEFAULT_KM
    radius = max(0.01, radius)
    all_items = []
    for index, record in enumerate(records or []):
        summary = kayit_harita_ozeti(record, cache=cache)
        if summary["kind"] == "none":
            continue
        key = _harita_kayit_anahtari(record, index, key_field)
        all_items.append(
            {
                "key": key,
                "record": record,
                "kind": summary["kind"],
                "center": summary["center"],
                "bounds": summary["bounds"],
                "polygons": summary["polygons"],
                "geometry_hash": summary.get("geometry_hash", ""),
                "selected": key == selected_key,
                "distance_km": None,
                "coordinate_check": koordinat_poligon_uyusmazligi(record, cache=cache),
            }
        )
    selected_items = [item for item in all_items if item["selected"]]
    if mode == HARITA_MOD_TUMU:
        visible = all_items
    elif not selected_items:
        visible = []
    elif mode == HARITA_MOD_SECILI:
        visible = selected_items
    else:
        selected_center = selected_items[0]["center"]
        visible = []
        for item in all_items:
            distance = haversine_km(*selected_center, *item["center"])
            item["distance_km"] = distance
            if item["selected"] or (distance is not None and distance <= radius):
                visible.append(item)
    tokens = tuple(
        (
            str(item["key"]),
            item["kind"],
            item["geometry_hash"] or tuple(round(value, 7) for value in item["center"]),
        )
        for item in visible
    )
    return {
        "mode": mode,
        "selected_key": selected_key,
        "radius_km": radius,
        "items": visible,
        "geometry_count": sum(item["kind"] == "polygon" for item in visible),
        "fallback_count": sum(item["kind"] == "fallback" for item in visible),
        "bounds": _harita_bounds_birlestir(visible),
        "set_signature": (mode, tokens),
        "has_selection": bool(selected_items),
    }


def harita_fit_bounds(model, padding_ratio=None):
    """Map widget fit'i için görünür sete kontrollü boşluk ekle."""
    bounds = (model or {}).get("bounds")
    items = (model or {}).get("items") or []
    if not bounds:
        return None
    min_lat, min_lon, max_lat, max_lon = map(float, bounds)
    selected_mode = (model or {}).get("mode") == HARITA_MOD_SECILI
    ratio = float(padding_ratio) if padding_ratio is not None else (0.24 if selected_mode else 0.10)
    point_only = len(items) == 1 and items[0].get("kind") == "fallback"
    min_span = 0.004 if point_only else 0.00025
    lat_span = max(min_span, max_lat - min_lat)
    lon_span = max(min_span, max_lon - min_lon)
    lat_center = (min_lat + max_lat) / 2.0
    lon_center = (min_lon + max_lon) / 2.0
    half_lat = lat_span * (0.5 + ratio)
    half_lon = lon_span * (0.5 + ratio)
    return (
        lat_center - half_lat,
        lon_center - half_lon,
        lat_center + half_lat,
        lon_center + half_lon,
    )


__all__ = [
    "JeolojiGeometriHatasi",
    "aday_geometrisini_sec",
    "aday_tkgm_icin_yeterli",
    "adaylari_yerel_geometriyle_eslestir",
    "adayi_yerel_geometriyle_eslestir",
    "eksik_geometrileri_tkgmden_tamamla",
    "geometri_dosyalari_bul",
    "geometri_harita_halkalari",
    "geometri_harita_poligonlari",
    "harita_kayitlarini_ayir",
    "harita_fit_bounds",
    "harita_gorunum_modeli",
    "geometri_hash_hesapla",
    "geometri_katalogu_olustur",
    "geometri_ozeti",
    "haversine_km",
    "kml_geometrilerini_oku",
    "kml_onbellegini_temizle",
    "kml_kimligi_cikar",
    "kayit_harita_ozeti",
    "koordinat_poligon_uyari_metni",
    "koordinat_poligon_uyusmazligi",
    "konum_normalize_et",
    "normalize_kml_metni",
    "normalize_kml_yaz",
    "parsel_kimlik_anahtari",
    "HARITA_MOD_SECILI",
    "HARITA_MOD_TUMU",
    "HARITA_MOD_YAKINDAKILER",
    "KOORDINAT_POLIGON_UYUSMAZLIK_KM",
    "YAKINDAKILER_DEFAULT_KM",
]
