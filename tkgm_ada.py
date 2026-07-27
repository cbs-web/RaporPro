# Dosya: RaporPro/tkgm_ada.py
from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from tkgm_kml import (
    TKGM_API_BASE,
    TKGM_IL_LISTE_URL,
    TKGMSorguHatasi,
    _ada_parsel_no_temizle,
    _geometry_ve_properties,
    _json_getir,
    _konum_bul,
    _polygonlar,
    dosya_adi_guvenli,
)


ADA_PARSEL_LIMITI = 200
KOMSU_SORGU_ISCISI = 6
GOOGLE_UYDU_TILE = "https://mt0.google.com/vt/lyrs=s&hl=tr&x={x}&y={y}&z={z}"


def parsel_listesi_ayikla(payload):
    """TKGM parsel listesi cevabindan benzersiz parsel numaralarini ayikla."""
    if isinstance(payload, dict):
        source = payload.get("data") or payload.get("result") or payload.get("items") or []
    elif isinstance(payload, list):
        source = payload
    else:
        source = []

    numbers = []
    seen = set()
    for item in source:
        props = item.get("properties", item) if isinstance(item, dict) else {}
        candidates = (
            props.get("text"),
            props.get("parselNo"),
            props.get("parsel"),
            props.get("value"),
            props.get("id"),
        )
        number = ""
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                number = _ada_parsel_no_temizle(text, default="")
                if number:
                    break
        if number and number not in seen:
            seen.add(number)
            numbers.append(number)
    return sorted(numbers, key=_parsel_siralama_anahtari)


def _parsel_siralama_anahtari(value):
    text = str(value or "").strip()
    try:
        return 0, int(text)
    except (TypeError, ValueError):
        return 1, text.casefold()


def _parsel_kaydi(payload):
    geometry, properties = _geometry_ve_properties(payload)
    if not geometry or not _polygonlar(geometry):
        return None
    properties = properties if isinstance(properties, dict) else {}
    ada = str(properties.get("adaNo") or properties.get("ada") or "").strip()
    parsel = str(properties.get("parselNo") or properties.get("parsel") or "").strip()
    mahalle_id = str(properties.get("mahalleId") or "").strip()
    ozet = str(properties.get("ozet") or "").strip()
    return {
        "geometry": geometry,
        "properties": properties,
        "ada": ada,
        "parsel": parsel,
        "mahalle_id": mahalle_id,
        "ozet": ozet,
    }


def _kayit_anahtari(record):
    if not isinstance(record, dict):
        return ""
    return (
        str(record.get("ozet") or "").strip()
        or f"{record.get('mahalle_id', '')}:{record.get('ada', '')}:{record.get('parsel', '')}"
    )


def _ayni_ada(record, mahalle_id, ada):
    if not isinstance(record, dict):
        return False
    record_ada = _ada_parsel_no_temizle(record.get("ada"), default="")
    record_mahalle = str(record.get("mahalle_id") or "").strip()
    return record_ada == _ada_parsel_no_temizle(ada, default="") and (
        not record_mahalle or record_mahalle == str(mahalle_id)
    )


def _ring_noktalari(ring):
    points = []
    for point in ring or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            continue
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points


def komsu_parsel_noktalari(geometry, offset_m=1.2, max_points=72):
    """Parsel kenarlarinin iki yaninda koordinattan sorgulanacak ornek noktalar uret."""
    samples = []
    seen = set()
    for polygon in _polygonlar(geometry):
        if not polygon:
            continue
        points = _ring_noktalari(polygon[0])
        if len(points) < 2:
            continue
        for idx, first in enumerate(points):
            second = points[(idx + 1) % len(points)]
            mean_lat = (first[1] + second[1]) / 2.0
            meters_per_lon = max(1.0, 111320.0 * math.cos(math.radians(mean_lat)))
            dx_m = (second[0] - first[0]) * meters_per_lon
            dy_m = (second[1] - first[1]) * 110540.0
            edge_length = math.hypot(dx_m, dy_m)
            if edge_length < 0.35:
                continue
            if edge_length >= 35.0:
                fractions = (0.2, 0.5, 0.8)
            elif edge_length >= 15.0:
                fractions = (0.33, 0.67)
            else:
                fractions = (0.5,)
            normal_x = -dy_m / edge_length
            normal_y = dx_m / edge_length
            for fraction in fractions:
                lon = first[0] + (second[0] - first[0]) * fraction
                lat = first[1] + (second[1] - first[1]) * fraction
                for direction in (-1.0, 1.0):
                    sample_lon = lon + direction * normal_x * offset_m / meters_per_lon
                    sample_lat = lat + direction * normal_y * offset_m / 110540.0
                    key = (round(sample_lat, 7), round(sample_lon, 7))
                    if key not in seen:
                        seen.add(key)
                        samples.append((sample_lat, sample_lon))
    if len(samples) <= max_points:
        return samples
    step = len(samples) / float(max_points)
    return [samples[min(len(samples) - 1, int(index * step))] for index in range(max_points)]


def _konum_kimliklerini_bul(kunye, timeout, fetcher):
    il = str(kunye.get("il") or "").strip()
    ilce = str(kunye.get("ilce") or "").strip()
    mahalle = str(kunye.get("mah") or kunye.get("mahalle") or "").strip()
    ada = _ada_parsel_no_temizle(kunye.get("ada"), default="0")
    parsel = _ada_parsel_no_temizle(kunye.get("par") or kunye.get("parsel"), default="")

    missing = []
    if not il:
        missing.append("Il")
    if not ilce:
        missing.append("Ilce")
    if not mahalle:
        missing.append("Mahalle/Koy")
    if not ada or ada == "0":
        missing.append("Ada")
    if not parsel:
        missing.append("Parsel")
    if missing:
        raise TKGMSorguHatasi("Kunye eksik: " + ", ".join(missing))

    il_id, il_label = _konum_bul(fetcher(TKGM_IL_LISTE_URL, timeout=timeout), il, "Il")
    ilce_id, ilce_label = _konum_bul(
        fetcher(f"{TKGM_API_BASE}idariYapi/ilceListe/{il_id}", timeout=timeout),
        ilce,
        "Ilce",
    )
    mahalle_id, mahalle_label = _konum_bul(
        fetcher(f"{TKGM_API_BASE}idariYapi/mahalleListe/{ilce_id}", timeout=timeout),
        mahalle,
        "Mahalle/Koy",
    )
    return {
        "il": il_label,
        "ilce": ilce_label,
        "mahalle": mahalle_label,
        "mahalle_id": mahalle_id,
        "ada": ada,
        "parsel": parsel,
    }


def _dogrudan_parsel_getir(mahalle_id, ada, parsel, timeout, fetcher):
    try:
        payload = fetcher(
            f"{TKGM_API_BASE}parsel/{mahalle_id}/{ada}/{parsel}",
            timeout=timeout,
        )
    except Exception:
        return None
    return _parsel_kaydi(payload)


def _listedeki_parselleri_getir(numbers, mahalle_id, ada, timeout, fetcher):
    records = []
    workers = min(KOMSU_SORGU_ISCISI, max(1, len(numbers)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tkgm-ada") as executor:
        futures = {
            executor.submit(
                _dogrudan_parsel_getir,
                mahalle_id,
                ada,
                number,
                timeout,
                fetcher,
            ): number
            for number in numbers[:ADA_PARSEL_LIMITI]
        }
        for future in as_completed(futures):
            record = future.result()
            if record and _ayni_ada(record, mahalle_id, ada):
                records.append(record)
    return sorted(records, key=lambda item: _parsel_siralama_anahtari(item.get("parsel")))


def _koordinattan_parsel_getir(lat, lon, timeout, fetcher):
    try:
        payload = fetcher(
            f"{TKGM_API_BASE}parsel/{lat:.8f}/{lon:.8f}/",
            timeout=timeout,
        )
    except Exception:
        return None
    return _parsel_kaydi(payload)


def _komsulukla_ada_tara(selected_record, mahalle_id, ada, timeout, fetcher):
    records = {_kayit_anahtari(selected_record): selected_record}
    frontier = [selected_record]
    queried_points = set()

    while frontier and len(records) < ADA_PARSEL_LIMITI:
        samples = []
        for record in frontier:
            for lat, lon in komsu_parsel_noktalari(record.get("geometry")):
                key = (round(lat, 7), round(lon, 7))
                if key not in queried_points:
                    queried_points.add(key)
                    samples.append((lat, lon))
        if not samples:
            break

        discovered = []
        workers = min(KOMSU_SORGU_ISCISI, max(1, len(samples)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tkgm-komsu") as executor:
            futures = [
                executor.submit(_koordinattan_parsel_getir, lat, lon, timeout, fetcher)
                for lat, lon in samples
            ]
            for future in as_completed(futures):
                record = future.result()
                if not _ayni_ada(record, mahalle_id, ada):
                    continue
                key = _kayit_anahtari(record)
                if key and key not in records:
                    records[key] = record
                    discovered.append(record)
                    if len(records) >= ADA_PARSEL_LIMITI:
                        break
        frontier = discovered

    return sorted(records.values(), key=lambda item: _parsel_siralama_anahtari(item.get("parsel")))


def tkgm_ada_parsellerini_getir(kunye, timeout=25, fetcher=_json_getir):
    """Kunyedeki parselin adasina ait baglantili tum parsel geometrilerini getir."""
    if not isinstance(kunye, dict):
        raise TKGMSorguHatasi("Proje kunye bilgisi okunamadi.")

    location = _konum_kimliklerini_bul(kunye, timeout, fetcher)
    selected = _dogrudan_parsel_getir(
        location["mahalle_id"],
        location["ada"],
        location["parsel"],
        timeout,
        fetcher,
    )
    if not selected:
        raise TKGMSorguHatasi(
            f"TKGM parsel geometrisi bulunamadi: {location['ada']}/{location['parsel']}"
        )

    list_error = ""
    numbers = []
    try:
        payload = fetcher(
            f"{TKGM_API_BASE}parselListe/{location['mahalle_id']}/{location['ada']}",
            timeout=min(timeout, 6),
        )
        numbers = parsel_listesi_ayikla(payload)
    except Exception as exc:
        list_error = str(exc)

    if numbers:
        if location["parsel"] not in numbers:
            numbers.append(location["parsel"])
        records = _listedeki_parselleri_getir(
            sorted(set(numbers), key=_parsel_siralama_anahtari),
            location["mahalle_id"],
            location["ada"],
            timeout,
            fetcher,
        )
        source = "parsel_listesi"
    else:
        records = _komsulukla_ada_tara(
            selected,
            location["mahalle_id"],
            location["ada"],
            timeout,
            fetcher,
        )
        source = "komsuluk_taramasi"

    selected_key = _kayit_anahtari(selected)
    if selected_key not in {_kayit_anahtari(record) for record in records}:
        records.append(selected)
        records.sort(key=lambda item: _parsel_siralama_anahtari(item.get("parsel")))

    return {
        **location,
        "records": records,
        "source": source,
        "list_error": list_error,
        "limit_reached": len(records) >= ADA_PARSEL_LIMITI,
    }


def _lonlat_global_pixel(lon, lat, zoom):
    scale = 256.0 * (2**zoom)
    x = (float(lon) + 180.0) / 360.0 * scale
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)) * scale
    return x, y


def _goruntu_zoomu_sec(coords, width, height, max_zoom):
    usable_width = width * 0.78
    usable_height = height * 0.76
    for zoom in range(min(22, int(max_zoom)), 9, -1):
        pixels = [_lonlat_global_pixel(lon, lat, zoom) for lon, lat in coords]
        span_x = max(x for x, _ in pixels) - min(x for x, _ in pixels)
        span_y = max(y for _, y in pixels) - min(y for _, y in pixels)
        if span_x <= usable_width and span_y <= usable_height:
            return zoom
    return 10


def _tile_url_hazirla(template, x, y, zoom):
    values = {
        "x": x,
        "y": y,
        "z": zoom,
        "s": "0",
        "layer": "s",
        "api_key": "",
    }
    try:
        return str(template).format(**values)
    except (KeyError, ValueError) as exc:
        raise TKGMSorguHatasi(f"Harita altligi URL sablonu gecersiz: {exc}") from exc


def _tile_indir(url, headers, timeout):
    try:
        import requests
    except Exception as exc:
        raise TKGMSorguHatasi(f"Harita altligi icin requests yuklenemedi: {exc}") from exc
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    image.load()
    return image.convert("RGB")


def _font_yukle(size, bold=True):
    candidates = []
    windir = os.environ.get("WINDIR", r"C:\Windows")
    if bold:
        candidates.extend(
            [
                os.path.join(windir, "Fonts", "arialbd.ttf"),
                os.path.join(windir, "Fonts", "calibrib.ttf"),
                "DejaVuSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                os.path.join(windir, "Fonts", "arial.ttf"),
                os.path.join(windir, "Fonts", "calibri.ttf"),
                "DejaVuSans.ttf",
            ]
        )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _polygon_centroid(points):
    if len(points) < 3:
        if not points:
            return 0.0, 0.0
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for idx, first in enumerate(points):
        second = points[(idx + 1) % len(points)]
        cross = first[0] * second[1] - second[0] * first[1]
        area2 += cross
        cx += (first[0] + second[0]) * cross
        cy += (first[1] + second[1]) * cross
    if abs(area2) < 1e-9:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    return cx / (3.0 * area2), cy / (3.0 * area2)


def _en_buyuk_dis_ring(geometry):
    candidates = []
    for polygon in _polygonlar(geometry):
        if not polygon:
            continue
        ring = _ring_noktalari(polygon[0])
        if len(ring) >= 3:
            min_lon = min(point[0] for point in ring)
            max_lon = max(point[0] for point in ring)
            min_lat = min(point[1] for point in ring)
            max_lat = max(point[1] for point in ring)
            candidates.append(((max_lon - min_lon) * (max_lat - min_lat), ring))
    return max(candidates, default=(0.0, []), key=lambda item: item[0])[1]


def _etiket_fontu(draw, text, polygon_pixels, preferred_size):
    min_x = min(point[0] for point in polygon_pixels)
    max_x = max(point[0] for point in polygon_pixels)
    min_y = min(point[1] for point in polygon_pixels)
    max_y = max(point[1] for point in polygon_pixels)
    box_width = max(10, max_x - min_x)
    box_height = max(10, max_y - min_y)
    for size in range(preferred_size, 9, -1):
        font = _font_yukle(size, bold=True)
        bounds = draw.textbbox((0, 0), text, font=font, stroke_width=2)
        if bounds[2] - bounds[0] <= box_width * 0.9 and bounds[3] - bounds[1] <= box_height * 0.75:
            return font
    return _font_yukle(10, bold=True)


def ada_gorseli_ciz(
    records,
    output_path,
    tile_provider,
    selected_parsel="",
    width=1800,
    height=1150,
    timeout=20,
    tile_loader=None,
):
    """Ada parsellerini uydu altligi uzerine cizip yuksek cozunurluklu JPEG uret."""
    records = [record for record in records if isinstance(record, dict) and record.get("geometry")]
    coords = []
    for record in records:
        for polygon in _polygonlar(record["geometry"]):
            if polygon:
                coords.extend(_ring_noktalari(polygon[0]))
    if not coords:
        raise TKGMSorguHatasi("Ada gorseli icin cizilebilir parsel geometrisi bulunamadi.")

    tile_provider = tile_provider if isinstance(tile_provider, dict) else {}
    template = tile_provider.get("url") or GOOGLE_UYDU_TILE
    max_zoom = tile_provider.get("max_zoom", 22)
    zoom = _goruntu_zoomu_sec(coords, width, height, max_zoom)
    global_pixels = [_lonlat_global_pixel(lon, lat, zoom) for lon, lat in coords]
    center_x = (min(x for x, _ in global_pixels) + max(x for x, _ in global_pixels)) / 2.0
    center_y = (min(y for _, y in global_pixels) + max(y for _, y in global_pixels)) / 2.0
    origin_x = center_x - width / 2.0
    origin_y = center_y - height / 2.0
    min_tile_x = math.floor(origin_x / 256.0)
    max_tile_x = math.floor((origin_x + width - 1) / 256.0)
    min_tile_y = math.floor(origin_y / 256.0)
    max_tile_y = math.floor((origin_y + height - 1) / 256.0)

    headers = {
        "User-Agent": "RaporPro/1.0 (TKGM Ada Gorseli)",
        "Referer": "https://atlas.harita.gov.tr/" if "harita.gov.tr" in template else "https://maps.google.com/",
    }
    tile_loader = tile_loader or _tile_indir
    tile_specs = [
        (tile_x, tile_y, _tile_url_hazirla(template, tile_x, tile_y, zoom))
        for tile_y in range(min_tile_y, max_tile_y + 1)
        for tile_x in range(min_tile_x, max_tile_x + 1)
    ]
    tiles = {}
    with ThreadPoolExecutor(
        max_workers=min(8, max(1, len(tile_specs))),
        thread_name_prefix="tkgm-tile",
    ) as executor:
        futures = {
            executor.submit(tile_loader, url, headers, timeout): (tile_x, tile_y)
            for tile_x, tile_y, url in tile_specs
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                tile = future.result()
                if tile.size != (256, 256):
                    tile = tile.resize((256, 256), Image.Resampling.LANCZOS)
                tiles[key] = tile.convert("RGB")
            except Exception:
                continue
    if not tiles:
        raise TKGMSorguHatasi("Secilen uydu altligindan goruntu parcasi alinamadi.")

    informative = 0
    for tile in tiles.values():
        extrema = tile.convert("L").getextrema()
        if extrema and extrema[1] - extrema[0] >= 4:
            informative += 1
    if informative == 0:
        raise TKGMSorguHatasi("Secilen uydu altligi bos goruntu dondurdu.")

    mosaic_width = (max_tile_x - min_tile_x + 1) * 256
    mosaic_height = (max_tile_y - min_tile_y + 1) * 256
    mosaic = Image.new("RGB", (mosaic_width, mosaic_height), "#D9DEE2")
    for (tile_x, tile_y), tile in tiles.items():
        mosaic.paste(tile, ((tile_x - min_tile_x) * 256, (tile_y - min_tile_y) * 256))
    crop_left = int(round(origin_x - min_tile_x * 256))
    crop_top = int(round(origin_y - min_tile_y * 256))
    canvas = mosaic.crop((crop_left, crop_top, crop_left + width, crop_top + height))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def to_pixel(point):
        x, y = _lonlat_global_pixel(point[0], point[1], zoom)
        return x - origin_x, y - origin_y

    selected_clean = _ada_parsel_no_temizle(selected_parsel, default="")
    for record in records:
        selected = _ada_parsel_no_temizle(record.get("parsel"), default="") == selected_clean
        fill = (171, 0, 43, 92 if selected else 74)
        outline = (119, 0, 34, 255)
        width_px = 6 if selected else 4
        for polygon in _polygonlar(record["geometry"]):
            if not polygon:
                continue
            outer = [to_pixel(point) for point in _ring_noktalari(polygon[0])]
            if len(outer) < 3:
                continue
            draw.polygon(outer, fill=fill)
            draw.line(outer + [outer[0]], fill=outline, width=width_px, joint="curve")
            for hole in polygon[1:]:
                inner = [to_pixel(point) for point in _ring_noktalari(hole)]
                if len(inner) >= 3:
                    draw.polygon(inner, fill=(0, 0, 0, 0))
                    draw.line(inner + [inner[0]], fill=outline, width=max(2, width_px - 1))

    preferred_font_size = max(18, min(34, int(width / 60)))
    for record in records:
        ring = _en_buyuk_dis_ring(record["geometry"])
        polygon_pixels = [to_pixel(point) for point in ring]
        if len(polygon_pixels) < 3:
            continue
        label = f"{record.get('ada', '')}/{record.get('parsel', '')}".strip("/")
        if not label:
            continue
        center = _polygon_centroid(polygon_pixels)
        font = _etiket_fontu(draw, label, polygon_pixels, preferred_font_size)
        bounds = draw.textbbox((0, 0), label, font=font, stroke_width=3)
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        draw.text(
            (center[0] - text_width / 2.0, center[1] - text_height / 2.0),
            label,
            font=font,
            fill="white",
            stroke_width=3,
            stroke_fill="#3B0A16",
        )

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    footer_height = 28
    footer = Image.new("RGBA", (width, footer_height), (15, 23, 31, 205))
    footer_draw = ImageDraw.Draw(footer)
    footer_font = _font_yukle(14, bold=False)
    footer_draw.text(
        (10, 5),
        "https://parselsorgu.tkgm.gov.tr/",
        font=footer_font,
        fill="white",
    )
    canvas.paste(footer.convert("RGB"), (0, height - footer_height))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path, format="JPEG", quality=95, subsampling=0, optimize=True)
    return {
        "path": output_path,
        "zoom": zoom,
        "tile_count": len(tiles),
        "width": width,
        "height": height,
    }


def tkgm_ada_gorseli_olustur(
    kunye,
    output_dir,
    tile_provider,
    tile_name="Google Uydu",
    fallback_tile_provider=None,
    timeout=25,
):
    """TKGM ada geometrilerini al, uydu altligina ciz ve rapor gorseli uret."""
    result = tkgm_ada_parsellerini_getir(kunye, timeout=timeout)
    os.makedirs(output_dir, exist_ok=True)
    filename = dosya_adi_guvenli(f"TKGM_Ada_{result['ada']}.jpg")
    output_path = os.path.join(output_dir, filename)
    active_tile_name = tile_name
    fallback_used = False
    try:
        render_info = ada_gorseli_ciz(
            result["records"],
            output_path,
            tile_provider,
            selected_parsel=result["parsel"],
            timeout=timeout,
        )
    except Exception:
        if not fallback_tile_provider or fallback_tile_provider == tile_provider:
            raise
        render_info = ada_gorseli_ciz(
            result["records"],
            output_path,
            fallback_tile_provider,
            selected_parsel=result["parsel"],
            timeout=timeout,
        )
        active_tile_name = "Google Uydu"
        fallback_used = True
    return {
        **result,
        **render_info,
        "tile_name": active_tile_name,
        "fallback_used": fallback_used,
        "parcel_count": len(result["records"]),
    }
