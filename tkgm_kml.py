# Dosya: RaporPro/tkgm_kml.py
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from xml.sax.saxutils import escape


TKGM_API_BASE = "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api/"
TKGM_IL_LISTE_URL = "https://parselsorgu.tkgm.gov.tr/app/modules/administrativeQuery/data/ilListe.json"


class TKGMSorguHatasi(RuntimeError):
    """TKGM parsel sorgusu kullaniciya gosterilebilir bir hata ile basarisiz oldu."""


def konum_adi_normalize_et(value):
    text = str(value or "").strip().lower()
    text = text.replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(mahallesi|mahalle|mah\.|mh\.|mh|koyu|köyü|belde|beldesi)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def dosya_adi_guvenli(value, fallback="parsel"):
    text = str(value or "").strip()
    text = re.sub(r"[^\w\-\.]+", "_", text, flags=re.UNICODE).strip("._")
    return text or fallback


def _json_getir(url, timeout=25):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
            "User-Agent": "RaporPro/1.0 (TKGM KML)",
            "Referer": "https://parselsorgu.tkgm.gov.tr/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        detail = f" - {body[:300]}" if body else ""
        raise TKGMSorguHatasi(f"TKGM servisi {exc.code} hatasi verdi{detail}: {url}") from exc
    except urllib.error.URLError as exc:
        raise TKGMSorguHatasi(f"TKGM servisine ulasilamadi: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TKGMSorguHatasi("TKGM servisi zaman asimina ugradi.") from exc

    try:
        return json.loads(raw.decode(charset, errors="replace"))
    except Exception as exc:
        raise TKGMSorguHatasi("TKGM servisi beklenen JSON cevabini dondurmedi.") from exc


def _liste_elemanlari(payload):
    if isinstance(payload, list):
        source = payload
    elif isinstance(payload, dict):
        source = payload.get("features") or payload.get("data") or payload.get("result") or payload.get("items") or []
    else:
        source = []

    items = []
    for item in source:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else item
        items.append({"raw": item, "properties": props})
    return items


def _etiket_al(item):
    props = item.get("properties", {}) if isinstance(item, dict) else {}
    for key in ("text", "ad", "adi", "name", "label", "ilAdi", "ilceAdi", "mahalleAdi", "value"):
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _id_al(item):
    props = item.get("properties", {}) if isinstance(item, dict) else {}
    for key in ("id", "kod", "value", "mahalleId", "ilceId", "ilId"):
        value = props.get(key)
        if value not in (None, ""):
            return value
    raw = item.get("raw", {}) if isinstance(item, dict) else {}
    for key in ("id", "kod"):
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _ada_parsel_no_temizle(value, default="0"):
    text = str(value or "").strip()
    if not text:
        return default
    match = re.search(r"\d+", text)
    return match.group(0) if match else text


def _konum_bul(payload, aranan, alan_adi):
    hedef = konum_adi_normalize_et(aranan)
    if not hedef:
        raise TKGMSorguHatasi(f"{alan_adi} bilgisi bos.")

    items = _liste_elemanlari(payload)
    if not items:
        raise TKGMSorguHatasi(f"TKGM {alan_adi} listesi bos geldi.")

    exact = []
    contains = []
    for item in items:
        label = _etiket_al(item)
        norm = konum_adi_normalize_et(label)
        if norm == hedef:
            exact.append(item)
        elif norm and (hedef in norm or norm in hedef):
            contains.append(item)

    match = (exact or contains or [None])[0]
    if match:
        match_id = _id_al(match)
        if match_id in (None, ""):
            raise TKGMSorguHatasi(f"{alan_adi} icin TKGM id bilgisi bulunamadi: {_etiket_al(match)}")
        return match_id, _etiket_al(match)

    examples = ", ".join(_etiket_al(item) for item in items[:8] if _etiket_al(item))
    if examples:
        raise TKGMSorguHatasi(f"{alan_adi} bulunamadi: {aranan}. TKGM listesinde ornekler: {examples}")
    raise TKGMSorguHatasi(f"{alan_adi} bulunamadi: {aranan}")


def _geometry_ve_properties(payload):
    if isinstance(payload, dict):
        if payload.get("type") == "Feature":
            return payload.get("geometry"), payload.get("properties", {})
        if payload.get("geometry"):
            return payload.get("geometry"), payload.get("properties", {})
        features = payload.get("features")
        if isinstance(features, list):
            for feature in features:
                geometry, properties = _geometry_ve_properties(feature)
                if geometry:
                    return geometry, properties
        for key in ("data", "result", "entity"):
            value = payload.get(key)
            geometry, properties = _geometry_ve_properties(value)
            if geometry:
                return geometry, properties
    elif isinstance(payload, list):
        for item in payload:
            geometry, properties = _geometry_ve_properties(item)
            if geometry:
                return geometry, properties
    return None, {}


def _polygonlar(geometry):
    if not isinstance(geometry, dict):
        return []
    geo_type = str(geometry.get("type") or "").lower()
    coords = geometry.get("coordinates")
    if geo_type == "polygon":
        return [coords]
    if geo_type == "multipolygon":
        return list(coords or [])
    return []


def _ring_kapat(ring):
    temiz = []
    for point in ring or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lon = float(point[0])
            lat = float(point[1])
            alt = float(point[2]) if len(point) > 2 else 0.0
        except Exception:
            continue
        temiz.append((lon, lat, alt))
    if temiz and temiz[0][:2] != temiz[-1][:2]:
        temiz.append(temiz[0])
    return temiz


def _kml_ring(ring):
    coords = _ring_kapat(ring)
    return " ".join(f"{lon:.8f},{lat:.8f},{alt:.2f}" for lon, lat, alt in coords)


def _merkez_hesapla(polygons):
    points = []
    for polygon in polygons:
        if not polygon:
            continue
        for lon, lat, _alt in _ring_kapat(polygon[0]):
            points.append((lat, lon))
    if not points:
        return None
    return sum(lat for lat, _ in points) / len(points), sum(lon for _, lon in points) / len(points)


def geojson_kml_olustur(geometry, name="TKGM Parsel", description=""):
    polygons = _polygonlar(geometry)
    if not polygons:
        raise TKGMSorguHatasi("TKGM parsel geometrisi Polygon/MultiPolygon olarak gelmedi.")

    placemarks = []
    for idx, polygon in enumerate(polygons, start=1):
        if not polygon:
            continue
        outer = _kml_ring(polygon[0])
        if not outer:
            continue
        inner_parts = []
        for ring in polygon[1:]:
            inner = _kml_ring(ring)
            if inner:
                inner_parts.append(
                    "<innerBoundaryIs><LinearRing><coordinates>"
                    + inner
                    + "</coordinates></LinearRing></innerBoundaryIs>"
                )
        placemarks.append(
            "<Placemark>"
            f"<name>{escape(name if len(polygons) == 1 else f'{name} - {idx}')}</name>"
            f"<description>{escape(description)}</description>"
            "<styleUrl>#parselStyle</styleUrl>"
            "<Polygon><tessellate>1</tessellate>"
            f"<outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>"
            + "".join(inner_parts)
            + "</Polygon></Placemark>"
        )

    if not placemarks:
        raise TKGMSorguHatasi("TKGM parsel geometrisinden KML koordinati uretilemedi.")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "<Document>\n"
        f"<name>{escape(name)}</name>\n"
        '<Style id="parselStyle">'
        '<LineStyle><color>ff0000ff</color><width>2</width></LineStyle>'
        '<PolyStyle><color>2600ffff</color></PolyStyle>'
        "</Style>\n"
        + "\n".join(placemarks)
        + "\n</Document>\n</kml>\n"
    )


def tkgm_parsel_kml_olustur(kunye, output_dir, timeout=25):
    if not isinstance(kunye, dict):
        raise TKGMSorguHatasi("Proje kunye bilgisi okunamadi.")

    il = (kunye.get("il") or "").strip()
    ilce = (kunye.get("ilce") or "").strip()
    mahalle = (kunye.get("mah") or kunye.get("mahalle") or "").strip()
    ada = _ada_parsel_no_temizle(kunye.get("ada"), default="0")
    parsel = _ada_parsel_no_temizle(kunye.get("par") or kunye.get("parsel"), default="")

    missing = []
    if not il:
        missing.append("Il")
    if not ilce:
        missing.append("Ilce")
    if not mahalle:
        missing.append("Mahalle/Koy")
    if not parsel:
        missing.append("Parsel")
    if missing:
        raise TKGMSorguHatasi("Kunye eksik: " + ", ".join(missing))

    il_id, il_label = _konum_bul(_json_getir(TKGM_IL_LISTE_URL, timeout=timeout), il, "Il")
    ilce_url = f"{TKGM_API_BASE}idariYapi/ilceListe/{il_id}"
    ilce_id, ilce_label = _konum_bul(_json_getir(ilce_url, timeout=timeout), ilce, "Ilce")
    mahalle_url = f"{TKGM_API_BASE}idariYapi/mahalleListe/{ilce_id}"
    mahalle_id, mahalle_label = _konum_bul(_json_getir(mahalle_url, timeout=timeout), mahalle, "Mahalle/Koy")

    parsel_url = f"{TKGM_API_BASE}parsel/{mahalle_id}/{ada}/{parsel}"
    parsel_payload = _json_getir(parsel_url, timeout=timeout)
    geometry, properties = _geometry_ve_properties(parsel_payload)
    if not geometry:
        raise TKGMSorguHatasi(f"TKGM parsel geometrisi bulunamadi: {ada}/{parsel}")

    label = f"{il_label} {ilce_label} {mahalle_label} {ada}/{parsel}"
    description = "TKGM Parsel Sorgu servisinden RaporPro ile olusturuldu."
    kml_text = geojson_kml_olustur(geometry, name=label, description=description)

    os.makedirs(output_dir, exist_ok=True)
    filename = dosya_adi_guvenli(f"TKGM_{ada}_{parsel}_{int(time.time())}.kml")
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(kml_text)

    polygons = _polygonlar(geometry)
    return {
        "path": path,
        "center": _merkez_hesapla(polygons),
        "label": label,
        "properties": properties,
        "il": il_label,
        "ilce": ilce_label,
        "mahalle": mahalle_label,
        "ada": ada,
        "parsel": parsel,
        "mahalle_id": mahalle_id,
    }
