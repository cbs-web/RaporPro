import datetime
import json
import os
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from harita_referans import valid_latlon
from yardimcilar import atomic_json_dump, atomic_write_text, safe_float
from uygulama_yollari import SOURCE_DIR, kullanici_yolu


APP_DIR = str(SOURCE_DIR)
COMPLETED_PROJECTS_PATH = str(
    kullanici_yolu("completed_projects.json", legacy=SOURCE_DIR / "completed_projects.json")
)


def _today_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _clean_text(value, default="-"):
    text = "" if value is None else str(value).strip()
    return text or default


def _project_key(project_path):
    if not project_path:
        return ""
    return os.path.normcase(os.path.abspath(str(project_path)))


def proje_adi(veri):
    kunye = veri.get("kunye", {}) if isinstance(veri, dict) else {}
    parts = [
        kunye.get("sahibi", ""),
        kunye.get("mah", ""),
        kunye.get("ada", ""),
        kunye.get("par", ""),
    ]
    text = " ".join(str(item).strip() for item in parts if str(item or "").strip())
    return text or "Adsız proje"


def proje_adresi(veri):
    kunye = veri.get("kunye", {}) if isinstance(veri, dict) else {}
    parts = [
        kunye.get("mah", ""),
        kunye.get("ilce", ""),
        kunye.get("il", ""),
    ]
    return " / ".join(str(item).strip() for item in parts if str(item or "").strip()) or "-"


def _ortalama_koordinat(items):
    coords = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        lat = item.get("y")
        lon = item.get("x")
        if valid_latlon(lat, lon):
            coords.append((float(lat), float(lon)))
    if not coords:
        return None, None
    return (
        sum(lat for lat, _ in coords) / len(coords),
        sum(lon for _, lon in coords) / len(coords),
    )


def _koordinat_listesi_merkezi(points):
    coords = []
    for point in points or []:
        if not isinstance(point, dict):
            continue
        lat = point.get("lat")
        lon = point.get("lon")
        if valid_latlon(lat, lon):
            coords.append((float(lat), float(lon)))
    if not coords:
        return None, None
    return (
        sum(lat for lat, _ in coords) / len(coords),
        sum(lon for _, lon in coords) / len(coords),
    )


def _kml_koordinat_satiri_coz(text):
    points = []
    for row in str(text or "").strip().split():
        parts = row.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except Exception:
            continue
        if valid_latlon(lat, lon):
            points.append({"lat": lat, "lon": lon})
    if len(points) > 1:
        first = points[0]
        last = points[-1]
        if abs(first["lat"] - last["lat"]) < 1e-8 and abs(first["lon"] - last["lon"]) < 1e-8:
            points.pop()
    return points


def kml_sinir_koordinatlari_oku(kml_path):
    if not kml_path or not os.path.exists(kml_path):
        return []
    try:
        root = ET.parse(kml_path).getroot()
    except Exception:
        return []

    candidates = []
    for elem in root.iter():
        if "coordinates" not in str(elem.tag):
            continue
        points = _kml_koordinat_satiri_coz(elem.text)
        if len(points) >= 3:
            candidates.append(points)
    if not candidates:
        return []
    return max(candidates, key=len)


def proje_merkez_koordinati(veri):
    if not isinstance(veri, dict):
        return None, None
    arazi = veri.get("arazi", {}) or {}
    lat = arazi.get("alan_y")
    lon = arazi.get("alan_x")
    if valid_latlon(lat, lon):
        return float(lat), float(lon)

    lat, lon = _ortalama_koordinat(veri.get("sondaj", []))
    if valid_latlon(lat, lon):
        return lat, lon

    jeofizik = veri.get("jeofizik", {}) or {}
    lat, lon = _ortalama_koordinat(jeofizik.get("mt_list", []))
    if valid_latlon(lat, lon):
        return lat, lon
    return None, None


def tamamlanmis_proje_kaydi(veri, project_path=None, kml_path=None):
    kunye = veri.get("kunye", {}) if isinstance(veri, dict) else {}
    durum = veri.get("proje_durumu", {}) if isinstance(veri, dict) else {}
    dosyalar = veri.get("dosyalar", {}) if isinstance(veri, dict) else {}
    source_kml = kml_path or dosyalar.get("kml_path")
    boundary = kml_sinir_koordinatlari_oku(source_kml)
    lat, lon = proje_merkez_koordinati(veri)
    if not valid_latlon(lat, lon) and boundary:
        lat, lon = _koordinat_listesi_merkezi(boundary)
    return {
        "path": os.path.abspath(project_path) if project_path else "",
        "name": proje_adi(veri),
        "address": proje_adresi(veri),
        "il": _clean_text(kunye.get("il")),
        "ilce": _clean_text(kunye.get("ilce")),
        "mahalle": _clean_text(kunye.get("mah")),
        "ada": _clean_text(kunye.get("ada")),
        "parsel": _clean_text(kunye.get("par")),
        "lat": lat,
        "lon": lon,
        "boundary": boundary,
        "boundary_source": os.path.abspath(source_kml) if source_kml else "",
        "completed_at": _clean_text(durum.get("tamamlanma_tarihi"), _today_iso()),
        "updated_at": _today_iso(),
    }


def arsiv_kayitlari_yukle(index_path=COMPLETED_PROJECTS_PATH):
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        records = payload.get("projects", payload) if isinstance(payload, dict) else payload
        return records if isinstance(records, list) else []
    except Exception:
        return []


def arsiv_kayitlari_kaydet(records, index_path=COMPLETED_PROJECTS_PATH):
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    atomic_json_dump({"projects": records}, index_path, indent=2, ensure_ascii=False)


def arsiv_kaydi_ekle(veri, project_path, index_path=COMPLETED_PROJECTS_PATH, kml_path=None):
    record = tamamlanmis_proje_kaydi(veri, project_path, kml_path=kml_path)
    key = _project_key(project_path)
    records = [
        item for item in arsiv_kayitlari_yukle(index_path)
        if _project_key(item.get("path")) != key
    ]
    records.append(record)
    records.sort(key=lambda item: str(item.get("completed_at", "")), reverse=True)
    arsiv_kayitlari_kaydet(records, index_path)
    return record


def arsiv_kaydi_sil(project_path, index_path=COMPLETED_PROJECTS_PATH):
    key = _project_key(project_path)
    if not key:
        return 0
    old_records = arsiv_kayitlari_yukle(index_path)
    records = [item for item in old_records if _project_key(item.get("path")) != key]
    arsiv_kayitlari_kaydet(records, index_path)
    return len(old_records) - len(records)


def _kml_description(record):
    project_name = os.path.basename(str(record.get("path") or "").replace("\\", "/"))
    lines = [
        f"Adres: {_clean_text(record.get('address'))}",
        f"Ada/Parsel: {_clean_text(record.get('ada'))}/{_clean_text(record.get('parsel'))}",
        f"Tamamlanma: {_clean_text(record.get('completed_at'))}",
        f"Dosya: {_clean_text(project_name)}",
    ]
    return "<br/>".join(escape(line) for line in lines)


def _kml_point_xml(lat, lon, indent="      "):
    return (
        f"{indent}<Point>\n"
        f"{indent}  <coordinates>{float(lon):.8f},{float(lat):.8f},0</coordinates>\n"
        f"{indent}</Point>\n"
    )


def _kml_polygon_xml(points, indent="      "):
    coords = [
        f"{float(point['lon']):.8f},{float(point['lat']):.8f},0"
        for point in points
        if isinstance(point, dict) and valid_latlon(point.get("lat"), point.get("lon"))
    ]
    if len(coords) < 3:
        return ""
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    coord_text = " ".join(coords)
    return (
        f"{indent}<Polygon>\n"
        f"{indent}  <outerBoundaryIs>\n"
        f"{indent}    <LinearRing>\n"
        f"{indent}      <coordinates>{coord_text}</coordinates>\n"
        f"{indent}    </LinearRing>\n"
        f"{indent}  </outerBoundaryIs>\n"
        f"{indent}</Polygon>\n"
    )


def biten_isler_kml_yaz(records, output_path):
    placemarks = []
    skipped = 0
    for record in records or []:
        boundary = [
            point for point in (record.get("boundary") or [])
            if isinstance(point, dict) and valid_latlon(point.get("lat"), point.get("lon"))
        ]
        lat = record.get("lat")
        lon = record.get("lon")
        if not valid_latlon(lat, lon) and boundary:
            lat, lon = _koordinat_listesi_merkezi(boundary)
        if not valid_latlon(lat, lon) and not boundary:
            skipped += 1
            continue
        name = escape(_clean_text(record.get("name"), "Biten iş"))
        description = _kml_description(record)
        geometry = ""
        if boundary:
            geometry = (
                "      <MultiGeometry>\n"
                + _kml_polygon_xml(boundary, indent="        ")
                + (_kml_point_xml(lat, lon, indent="        ") if valid_latlon(lat, lon) else "")
                + "      </MultiGeometry>\n"
            )
        else:
            geometry = _kml_point_xml(lat, lon)
        placemarks.append(
            "    <Placemark>\n"
            f"      <name>{name}</name>\n"
            f"      <description>{description}</description>\n"
            "      <styleUrl>#completedProject</styleUrl>\n"
            f"{geometry}"
            "    </Placemark>"
        )

    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        '  <Document>\n'
        '    <name>RaporPro Biten İşler</name>\n'
        '    <Style id="completedProject">\n'
        '      <IconStyle>\n'
        '        <color>ff1abc9c</color>\n'
        '        <scale>1.1</scale>\n'
        '        <Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href></Icon>\n'
        '      </IconStyle>\n'
        '      <LineStyle><color>ff1abc9c</color><width>2</width></LineStyle>\n'
        '      <PolyStyle><color>661abc9c</color></PolyStyle>\n'
        '    </Style>\n'
        + ("\n".join(placemarks) + "\n" if placemarks else "")
        + '  </Document>\n'
        '</kml>\n'
    )
    atomic_write_text(output_path, kml, encoding="utf-8")
    return {"written": len(placemarks), "skipped": skipped, "path": output_path}
