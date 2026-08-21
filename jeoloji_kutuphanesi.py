# Dosya: RaporPro/jeoloji_kutuphanesi.py
"""Eski Word raporlarındaki 2. JEOLOJİ bölümleri için yerel kütüphane.

Metadata tam kaynak rapordan okunur; cache'e ise yalnız ilişkileri korunmuş
2. JEOLOJİ bölüm Word'ü yazılır. Kaynağın kendisi hiçbir zaman değiştirilmez.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass
from contextlib import contextmanager
import xml.etree.ElementTree as ET

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

from harita_referans import valid_latlon
from jeoloji_geometri import (
    aday_geometrisini_sec,
    adaylari_yerel_geometriyle_eslestir,
    eksik_geometrileri_tkgmden_tamamla,
    geometri_hash_hesapla,
    geometri_katalogu_olustur,
    normalize_kml_yaz,
)
from uygulama_yollari import kullanici_yolu


LIBRARY_DIR_NAME = "jeoloji_kutuphanesi"
LIBRARY_DB_NAME = "kutuphane.sqlite3"
CACHE_DIR_NAME = "cache"
GEOMETRY_DIR_NAME = "geometry"
_DOCX_EXTENSIONS = {".docx", ".docm"}
_NUMBER_RE = r"[-+]?\d{1,3}(?:[.,]\d{1,12})?"
_RELATIONSHIP_ID_RE = re.compile(r"^rId\d+$", re.IGNORECASE)
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_DOCX_MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
_DOCM_MAIN_CONTENT_TYPES = {
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
}
_LOCATION_FIELDS = ("il", "ilce", "mahalle", "pafta", "ada", "parsel")


def kutuphane_veri_dizini(base_dir=None):
    """Kütüphane SQLite/cache kökünü kullanıcı veri dizininde döndür."""
    if base_dir is not None:
        root = Path(base_dir)
    else:
        root = Path(kullanici_yolu(LIBRARY_DIR_NAME))
    root.mkdir(parents=True, exist_ok=True)
    return root


def kutuphane_db_yolu(base_dir=None):
    return kutuphane_veri_dizini(base_dir) / LIBRARY_DB_NAME


def kutuphane_cache_dizini(base_dir=None):
    path = kutuphane_veri_dizini(base_dir) / CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def kutuphane_geometri_dizini(base_dir=None):
    path = kutuphane_veri_dizini(base_dir) / GEOMETRY_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso():
    return _datetime.datetime.now().isoformat(timespec="seconds")


def _text(value):
    return "" if value is None else str(value).strip()


def _fold(value):
    text = unicodedata.normalize("NFKD", _text(value)).replace("ı", "i").replace("İ", "I")
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _clean_space(value):
    return re.sub(r"\s+", " ", _text(value)).strip()


def _parse_number(value):
    text = _text(value).replace("\u00a0", " ")
    text = re.sub(r"[^0-9+\-.,]", "", text)
    if not text:
        return None
    if text.count(",") and text.count("."):
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _valid_coordinate(lat, lon):
    try:
        return bool(valid_latlon(lat, lon))
    except Exception:
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return False
        return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def sha256_dosya(path, chunk_size=1024 * 1024):
    """Büyük DOCX dosyalarını belleğe almadan SHA-256 ile özetle."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(max(4096, int(chunk_size)))
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def word_belgesi_ac(path):
    """DOCX yanında DOCM'i de makro çalıştırmadan python-docx ile salt okunur aç."""
    path = Path(path)
    if path.suffix.lower() != ".docm":
        return Document(str(path))

    output = io.BytesIO()
    with zipfile.ZipFile(path, "r") as source_zip, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for item in source_zip.infolist():
            content = source_zip.read(item.filename)
            if item.filename == "[Content_Types].xml":
                root = ET.fromstring(content)
                for override in root.findall(f"{{{_CONTENT_TYPES_NS}}}Override"):
                    if override.get("PartName") != "/word/document.xml":
                        continue
                    if override.get("ContentType") in _DOCM_MAIN_CONTENT_TYPES:
                        override.set("ContentType", _DOCX_MAIN_CONTENT_TYPE)
                content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target_zip.writestr(item, content)
    output.seek(0)
    return Document(output)


def _local_name(tag):
    return str(tag or "").rsplit("}", 1)[-1]


def _paragraph_style_name(paragraph):
    try:
        return _text(paragraph.style.name)
    except Exception:
        return ""


def baslik_numarasi(text):
    """Başlıktaki 2.1.3 gibi numarayı tuple olarak döndür."""
    match = re.match(
        r"^\s*(\d+(?:\s*\.\s*\d+)*)\s*(?:[.)\-:]\s*)?(?=\S)",
        _text(text),
    )
    if not match:
        return None
    try:
        return tuple(int(part.strip()) for part in match.group(1).split("."))
    except ValueError:
        return None


def baslik_duzeyi(paragraph):
    """Heading stili veya outlineLvl üzerinden Word başlık düzeyini bul."""
    style = _fold(_paragraph_style_name(paragraph))
    match = re.search(r"heading\s*([1-9])", style)
    if match:
        return int(match.group(1))
    try:
        outline = paragraph._p.pPr.find(qn("w:outlineLvl")) if paragraph._p.pPr is not None else None
        if outline is not None:
            return int(outline.get(qn("w:val"), "0")) + 1
    except (AttributeError, TypeError, ValueError):
        pass
    number = baslik_numarasi(paragraph.text)
    return len(number) if number else None


def _body_items(doc):
    items = []
    for index, child in enumerate(doc.element.body.iterchildren()):
        kind = _local_name(child.tag)
        if kind == "p":
            paragraph = Paragraph(child, doc._body)
            items.append(
                {
                    "index": index,
                    "element": child,
                    "kind": "paragraph",
                    "paragraph": paragraph,
                    "text": _clean_space(paragraph.text),
                    "style": _paragraph_style_name(paragraph),
                    "level": baslik_duzeyi(paragraph),
                    "number": baslik_numarasi(paragraph.text),
                }
            )
        elif kind == "tbl":
            table = Table(child, doc._body)
            cells = []
            for row in table.rows:
                cells.append(" | ".join(_clean_space(cell.text) for cell in row.cells))
            items.append(
                {
                    "index": index,
                    "element": child,
                    "kind": "table",
                    "table": table,
                    "text": "\n".join(item for item in cells if item),
                    "style": "",
                    "level": None,
                    "number": None,
                }
            )
        else:
            items.append(
                {
                    "index": index,
                    "element": child,
                    "kind": kind,
                    "text": "",
                    "style": "",
                    "level": None,
                    "number": None,
                }
            )
    return items


def _xml_visible_text(element):
    """Header paragrafı/tablosundaki Word text düğümlerini satırları koruyarak oku."""
    local = _local_name(element.tag)
    if local == "t":
        return element.text or ""
    if local == "tab":
        return "\t"
    if local in {"br", "cr"}:
        return "\n"
    value = "".join(_xml_visible_text(child) for child in element)
    if local == "p":
        return value + "\n"
    if local == "tr":
        return value + "\n"
    if local == "tc":
        return value + " "
    return value


def _normalize_multiline_text(value):
    lines = [_clean_space(line) for line in re.split(r"[\r\n]+", str(value or ""))]
    return "\n".join(line for line in lines if line)


def _header_texts(doc):
    """Tüm benzersiz header/header-table metinlerini döndür; footer'a hiç girme."""
    result = []
    seen = set()
    for section in doc.sections:
        for attribute in ("header", "first_page_header", "even_page_header"):
            try:
                header = getattr(section, attribute)
                root = header._element
            except Exception:
                continue
            blocks = []
            for child in root.iterchildren():
                if _local_name(child.tag) not in {"p", "tbl"}:
                    continue
                text = _normalize_multiline_text(_xml_visible_text(child))
                if text:
                    blocks.append(text)
            text = _normalize_multiline_text("\n".join(blocks))
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


@dataclass(frozen=True)
class BolumSinirlari:
    start_index: int = -1
    end_index: int = -1
    heading_level: int = 1
    start_heading: str = ""
    end_heading: str = ""
    end_found: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def found(self):
        return self.start_index >= 0

    @property
    def paragraph_count(self):
        return 0 if not self.found else max(0, self.end_index - self.start_index)

    def as_dict(self):
        return {
            "found": self.found,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "heading_level": self.heading_level,
            "start_heading": self.start_heading,
            "end_heading": self.end_heading,
            "end_found": self.end_found,
            "warnings": list(self.warnings),
        }


def jeoloji_basligi_mi(text):
    number = baslik_numarasi(text)
    if number != (2,):
        return False
    return "JEOLOJI" in _fold(text).upper()


def bolum_sinirlarini_bul(doc):
    """2. JEOLOJİ dahil, sonraki aynı düzey başlık hariç gövde aralığını bul."""
    items = _body_items(doc)
    start = next((item for item in items if item["kind"] == "paragraph" and jeoloji_basligi_mi(item["text"])), None)
    if start is None:
        return BolumSinirlari(
            warnings=("2. JEOLOJİ ana başlığı bulunamadı; kayıt yalnız kalite uyarısıyla tutuldu.",),
        )

    start_level = start["level"] or 1
    end = None
    fallback_end = None
    for item in items:
        if item["index"] <= start["index"] or item["kind"] != "paragraph":
            continue
        same_level = item["level"] == start_level if item["level"] is not None else False
        number = item["number"]
        if not same_level and item["level"] is None and number:
            same_level = len(number) == len(start["number"] or (2,))
        if not same_level:
            continue
        if fallback_end is None:
            fallback_end = item
        if number and len(number) == 1 and number[0] >= 3:
            end = item
            break

    if end is None:
        end = fallback_end

    body_end = next(
        (item["index"] for item in items if item["kind"] == "sectPr"),
        len(items),
    )
    warnings = []
    if end is None:
        end_index = body_end
        warnings.append("2. JEOLOJİ sonu için aynı düzeyde sonraki başlık bulunamadı; gövde sonuna kadar alındı.")
    else:
        end_index = end["index"]
    if start["level"] is None:
        warnings.append("Başlık düzeyi Word stilinden okunamadı; numaralandırma düzeyi kullanıldı.")
    return BolumSinirlari(
        start_index=start["index"],
        end_index=end_index,
        heading_level=start_level,
        start_heading=start["text"],
        end_heading=end["text"] if end else "",
        end_found=end is not None,
        warnings=tuple(warnings),
    )


def _first_label_value(text, labels):
    alternatives = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"(?:^|[\n;|])\s*(?:{alternatives})\s*(?:no|numarası|numarasi)?\s*[:\-]\s*([^\n;|]+)", re.IGNORECASE)
    for match in pattern.finditer(text):
        value = _clean_space(match.group(1)).strip(" .,")
        if value and "[" not in value and _fold(value) not in {"-", "none", "null"}:
            return value
    return ""


_LOCATION_PATTERNS = {
    "il": re.compile(r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+İli\b", re.IGNORECASE),
    "ilce": re.compile(r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+İlçe(?:si)?\b", re.IGNORECASE),
    "mahalle": re.compile(
        r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+(?:Mahallesi|Mahalle|Köyü|Köy)\b",
        re.IGNORECASE,
    ),
    "pafta": re.compile(r"(?<![\w])(?P<value>[^,\n;|:]+?)\s+Pafta\b", re.IGNORECASE),
    "ada": re.compile(r"(?<![\w])(?P<value>\d+)\s+Ada\b", re.IGNORECASE),
    "parsel": re.compile(r"(?<![\w])(?P<value>\d+)\s+Parsel\b", re.IGNORECASE),
}
_IMAR_BILGILERI_RE = re.compile(r"(?:^|\n|\b)İmar\s+Bilgileri\s*:\s*([^\r\n]+)", re.IGNORECASE)
_FILENAME_PARCEL_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,6})\s*([_-])\s*(\d{1,6})(?![A-Za-z0-9])")


def _location_values(text):
    values = {}
    for key, pattern in _LOCATION_PATTERNS.items():
        match = pattern.search(text or "")
        if not match:
            continue
        value = _clean_space(match.group("value")).strip(" .,")
        if value and _fold(value) not in {"-", "none", "null"}:
            values[key] = value
    return values


def _filename_parcel_values(filename):
    """Yalnız ada-ayraç-parsel biçimini al; yıl-ay gibi tarihlerden kaçın."""
    values = {}
    stem = Path(filename or "").stem
    for match in _FILENAME_PARCEL_RE.finditer(stem):
        ada = match.group(1)
        parsel = match.group(3)
        try:
            if len(ada) == 4 and 1900 <= int(ada) <= 2100:
                continue
        except ValueError:
            continue
        values["ada"] = ada
        values["parsel"] = parsel
    return values


def _extract_metadata(doc, full_text, filename="", header_texts=None):
    explicit = {
        "il": _first_label_value(full_text, ("İl", "Il", "İli", "Ili")),
        "ilce": _first_label_value(full_text, ("İlçesi", "İlçe", "Ilcesi", "Ilce")),
        "mahalle": _first_label_value(
            full_text,
            ("Mahallesi", "Mahalle", "Köyü", "Köy", "Mahallesi/Köy", "Mahalle/Köy"),
        ),
        "pafta": _first_label_value(full_text, ("Pafta No", "Pafta")),
        "ada": _first_label_value(full_text, ("Ada No", "Ada")),
        "parsel": _first_label_value(full_text, ("Parsel No", "Parsel")),
    }
    imar_values = {}
    for match in _IMAR_BILGILERI_RE.finditer(full_text or ""):
        for key, value in _location_values(match.group(1)).items():
            imar_values.setdefault(key, value)
    narrative_values = _location_values(full_text)
    filename_values = _filename_parcel_values(filename)
    metadata = {}
    field_sources = {}
    for key in _LOCATION_FIELDS:
        for source_name, values in (
            ("etiket", explicit),
            ("imar_bilgileri", imar_values),
            ("anlatim", narrative_values),
            ("dosya_adi", filename_values),
        ):
            value = values.get(key, "")
            if value:
                metadata[key] = value
                field_sources[key] = source_name
                break
        else:
            metadata[key] = ""
    metadata["field_sources"] = field_sources
    metadata["header_texts"] = list(header_texts or [])
    try:
        properties = doc.core_properties
        metadata["title"] = _text(properties.title)
        metadata["subject"] = _text(properties.subject)
        metadata["author"] = _text(properties.author)
        metadata["keywords"] = _text(properties.keywords)
        metadata["created"] = properties.created.isoformat() if properties.created else ""
        metadata["modified"] = properties.modified.isoformat() if properties.modified else ""
    except Exception:
        metadata.update({"title": "", "subject": "", "author": "", "keywords": "", "created": "", "modified": ""})

    formations = []
    for match in re.finditer(r"\bT(?:m[cç]k|mki|m[cç]d|mal)|\bQal\b", full_text, re.IGNORECASE):
        value = match.group(0)
        if value not in formations:
            formations.append(value)
    metadata["formasyonlar"] = formations
    return metadata


def _coordinate_pair_from_match(match, reversed_order=False):
    first = _parse_number(match.group(1))
    second = _parse_number(match.group(2))
    if reversed_order:
        first, second = second, first
    if _valid_coordinate(first, second):
        return float(first), float(second)
    return None


def _explicit_coordinate(full_text):
    labelled = (
        re.compile(rf"(?:enlem|latitude|lat)\D{{0,35}}({_NUMBER_RE})\D{{0,35}}(?:boylam|longitude|lon)\D{{0,35}}({_NUMBER_RE})", re.IGNORECASE),
        re.compile(rf"(?:boylam|longitude|lon)\D{{0,35}}({_NUMBER_RE})\D{{0,35}}(?:enlem|latitude|lat)\D{{0,35}}({_NUMBER_RE})", re.IGNORECASE),
    )
    for index, pattern in enumerate(labelled):
        for match in pattern.finditer(full_text):
            pair = _coordinate_pair_from_match(match, reversed_order=index == 1)
            if pair:
                return pair

    wgs_pattern = re.compile(rf"WGS\s*[- ]?84\D{{0,80}}({_NUMBER_RE})\D{{1,30}}({_NUMBER_RE})", re.IGNORECASE)
    for match in wgs_pattern.finditer(full_text):
        pair = _coordinate_pair_from_match(match)
        if pair:
            return pair
    return None


def _table_coordinate_candidates(doc):
    candidates = []
    for item in _body_items(doc):
        if item["kind"] != "table":
            continue
        table = item["table"]
        rows = [[_clean_space(cell.text) for cell in row.cells] for row in table.rows]
        header = None
        for row in rows[:5]:
            folded = [_fold(cell) for cell in row]
            lat_index = next((i for i, cell in enumerate(folded) if any(key in cell for key in ("enlem", "latitude", "lat"))), None)
            lon_index = next((i for i, cell in enumerate(folded) if any(key in cell for key in ("boylam", "longitude", "lon"))), None)
            if lat_index is not None and lon_index is not None:
                header = (lat_index, lon_index)
                break
        if header is None:
            continue
        lat_index, lon_index = header
        for row in rows:
            if len(row) <= max(lat_index, lon_index):
                continue
            lat = _parse_number(row[lat_index])
            lon = _parse_number(row[lon_index])
            if _valid_coordinate(lat, lon):
                candidates.append((float(lat), float(lon)))
    return candidates


def _paragraph_coordinate_candidates(full_text):
    candidates = []
    pattern = re.compile(rf"(?:sondaj|kuyu|sk\s*[- ]?\d+)?.{{0,45}}?({_NUMBER_RE})\s*[,;/ ]\s*({_NUMBER_RE})", re.IGNORECASE)
    for match in pattern.finditer(full_text):
        pair = _coordinate_pair_from_match(match)
        if pair:
            context = _fold(full_text[max(0, match.start() - 50):match.end() + 50])
            if any(key in context for key in ("sondaj", "kuyu", "enlem", "boylam", "wgs84")):
                candidates.append(pair)
    return candidates


def koordinat_cikar(doc, full_text=None):
    """Açık WGS84 > sondaj koordinat ortalaması önceliğiyle merkez bul."""
    full_text = full_text if full_text is not None else "\n".join(item["text"] for item in _body_items(doc) if item["text"])
    explicit = _explicit_coordinate(full_text)
    if explicit:
        return {"lat": explicit[0], "lon": explicit[1], "source": "rapor_wgs84", "count": 1}
    candidates = _table_coordinate_candidates(doc) + _paragraph_coordinate_candidates(full_text)
    if candidates:
        return {
            "lat": sum(item[0] for item in candidates) / len(candidates),
            "lon": sum(item[1] for item in candidates) / len(candidates),
            "source": "sondaj_ortalamasi",
            "count": len(candidates),
        }
    return {"lat": None, "lon": None, "source": "", "count": 0}


def _image_relationship_key(doc, relationship_id):
    """DML/VML referanslarını aynı hedef medya parçası üzerinden tekilleştir."""
    relationship_id = _text(relationship_id)
    if not relationship_id:
        return None
    if doc is not None:
        try:
            relationship = doc.part.rels[relationship_id]
            if relationship.is_external:
                return ("external", relationship.target_ref)
            return ("part", str(relationship.target_part.partname))
        except (KeyError, AttributeError, ValueError):
            pass
    return ("relationship", relationship_id)


def _body_image_count(elements, doc=None):
    """DrawingML blip ve eski VML imagedata görsellerini ilişki bazında say."""
    image_keys = set()
    for element in elements:
        for descendant in element.iter():
            if _local_name(descendant.tag) not in {"blip", "imagedata"}:
                continue
            for attribute, value in descendant.attrib.items():
                if not str(attribute).startswith("{" + REL_NS + "}"):
                    continue
                if _local_name(attribute) not in {"id", "embed", "link"}:
                    continue
                key = _image_relationship_key(doc, value)
                if key is not None:
                    image_keys.add(key)
    return len(image_keys)


def docx_analiz_et(path):
    """DOCX bölüm sınırı, metadata, kalite uyarısı ve koordinatı tek geçişte çıkar."""
    path = Path(path)
    doc = word_belgesi_ac(path)
    items = _body_items(doc)
    boundaries = bolum_sinirlarini_bul(doc)
    body_text = "\n".join(item["text"] for item in items if item["text"])
    header_texts = _header_texts(doc)
    full_text = "\n".join(item for item in [body_text, *header_texts] if item)
    metadata = _extract_metadata(doc, full_text, filename=path.name, header_texts=header_texts)
    coordinates = koordinat_cikar(doc, full_text)
    body_elements = []
    if boundaries.found:
        body_elements = [
            item["element"]
            for item in items
            if boundaries.start_index <= item["index"] < boundaries.end_index
            and item["kind"] != "sectPr"
        ]
    section_text = "\n".join(item["text"] for item in items if boundaries.found and boundaries.start_index <= item["index"] < boundaries.end_index and item["text"])
    section_paragraphs = sum(
        1 for item in items if boundaries.found and boundaries.start_index <= item["index"] < boundaries.end_index and item["kind"] == "paragraph"
    )
    section_tables = sum(
        1 for item in items if boundaries.found and boundaries.start_index <= item["index"] < boundaries.end_index and item["kind"] == "table"
    )
    warnings = list(boundaries.warnings)
    if not metadata.get("il") or not metadata.get("ilce") or not metadata.get("mahalle"):
        warnings.append("İl/ilçe/mahalle metadata satırlarından tam okunamadı; kütüphane kaydı sonradan düzenlenebilir.")
    if not metadata.get("ada") or not metadata.get("parsel"):
        warnings.append("Ada/parsel metadata satırlarından tam okunamadı; kayıt alınmaya devam edildi.")
    if not metadata.get("pafta"):
        warnings.append("Pafta metadata alanı okunamadı; kayıt sonradan düzenlenebilir.")
    if not coordinates["lat"]:
        warnings.append("WGS84 veya sondaj koordinatı bulunamadı; harita konumu sonradan elle belirlenebilir.")
    if boundaries.found and not section_tables:
        warnings.append("2. JEOLOJİ bölümünde tablo bulunamadı; içerik yine de aktarılabilir.")
    if boundaries.found and not _body_image_count(body_elements, doc):
        warnings.append("2. JEOLOJİ bölümünde görsel ilişkisi bulunamadı.")
    if boundaries.found:
        warnings.append("Kaynak bölümdeki şekil numaraları, parsel işaretleri ve fay tabloları eski projeye ait olabilir; tam aktarım öncesi kontrol edin.")
    metadata["summary_text"] = "\n".join(
        item["text"] for item in items if boundaries.found and boundaries.start_index <= item["index"] < boundaries.end_index and item["kind"] == "paragraph" and item["text"]
    )[:6000]
    metadata["source_filename"] = path.name
    metadata["section_heading_tree"] = [
        item["text"]
        for item in items
        if boundaries.found and boundaries.start_index <= item["index"] < boundaries.end_index and item["kind"] == "paragraph" and item["level"] is not None
    ]
    return {
        "boundaries": boundaries.as_dict(),
        "metadata": metadata,
        "il": metadata.get("il", ""),
        "ilce": metadata.get("ilce", ""),
        "mahalle": metadata.get("mahalle", ""),
        "pafta": metadata.get("pafta", ""),
        "ada": metadata.get("ada", ""),
        "parsel": metadata.get("parsel", ""),
        "lat": coordinates["lat"],
        "lon": coordinates["lon"],
        "coordinate_source": coordinates["source"],
        "coordinate_count": coordinates["count"],
        "paragraph_count": section_paragraphs,
        "table_count": section_tables,
        "image_count": _body_image_count(body_elements, doc),
        "section_text": section_text,
        "warnings": warnings,
        "quality_warnings": list(warnings),
    }


def docx_dosyalari_bul(kaynaklar, recursive=True):
    """Dosya/klasör girdilerinden benzersiz DOCX ve DOCM yollarını döndür."""
    if isinstance(kaynaklar, (str, os.PathLike)):
        kaynaklar = [kaynaklar]
    found = {}
    for raw_path in kaynaklar or []:
        path = Path(raw_path)
        if path.is_file():
            candidates = (path,)
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
            try:
                is_file = candidate.is_file()
            except OSError:
                continue
            if not is_file or candidate.name.startswith("~$") or candidate.suffix.lower() not in _DOCX_EXTENSIONS:
                continue
            absolute = Path(os.path.abspath(str(candidate)))
            found.setdefault(os.path.normcase(str(absolute)), absolute)
    return sorted(found.values(), key=lambda item: (_fold(item.name), _fold(str(item))))


def jeoloji_adayi_analiz_et(path):
    """Tek tam raporu DB/cache'e yazmadan aday kaydına dönüştür."""
    source = Path(path)
    candidate = {
        "source_path": str(Path(os.path.abspath(str(source)))),
        "original_path": str(Path(os.path.abspath(str(source)))),
        "original_filename": source.name,
        "filename": source.name,
        "source_hash": "",
        "file_size": 0,
        "mtime_ns": 0,
        "analysis": None,
        "eligible": False,
        "selected": False,
        "status": "Reddedildi",
        "error": "",
        "warnings": [],
    }
    try:
        stat = source.stat()
        candidate["file_size"] = int(stat.st_size)
        candidate["mtime_ns"] = int(getattr(stat, "st_mtime_ns", 0))
        candidate["source_hash"] = sha256_dosya(source)
        analysis = docx_analiz_et(source)
    except Exception as exc:
        candidate["error"] = str(exc)
        candidate["warnings"] = [f"Word dosyası analiz edilemedi: {exc}"]
        candidate["status"] = "Reddedildi: dosya okunamadı"
        return candidate

    candidate["analysis"] = analysis
    for key in (
        "il", "ilce", "mahalle", "pafta", "ada", "parsel", "lat", "lon",
        "coordinate_source", "paragraph_count", "table_count", "image_count",
        "section_text", "metadata", "boundaries",
    ):
        candidate[key] = analysis.get(key)
    warnings = list(analysis.get("warnings") or [])
    boundaries = analysis.get("boundaries") or {}
    found = bool(boundaries.get("found", int(boundaries.get("start_index", -1)) >= 0))
    has_content = bool(
        int(analysis.get("paragraph_count") or 0) > 1
        or int(analysis.get("table_count") or 0) > 0
        or int(analysis.get("image_count") or 0) > 0
    )
    if not found:
        candidate["status"] = "Reddedildi: 2. JEOLOJİ bulunamadı"
    elif not has_content:
        warnings.append("2. JEOLOJİ başlığı bulundu ancak bölüm içeriği boş görünüyor.")
        candidate["status"] = "Reddedildi: bölüm boş"
    else:
        candidate["eligible"] = True
        candidate["selected"] = True
        candidate["status"] = "Uygun" if not warnings else "Uygun, uyarı var"
    candidate["warnings"] = warnings
    candidate["quality_warnings"] = list(warnings)
    return candidate


def jeoloji_adaylarini_tara(
    kaynaklar,
    recursive=True,
    progress=None,
    geometry_resolver=None,
    complete_missing=False,
    geometry_progress=None,
):
    """Klasörleri salt-okunur tara; hiçbir SQLite kaydı veya cache dosyası oluşturma."""
    paths = docx_dosyalari_bul(kaynaklar, recursive=recursive)
    candidates = []
    total = len(paths)
    for index, path in enumerate(paths, start=1):
        candidate = jeoloji_adayi_analiz_et(path)
        candidates.append(candidate)
        if callable(progress):
            progress(index, total, path, candidate)
    catalog = geometri_katalogu_olustur(kaynaklar, recursive=recursive)
    adaylari_yerel_geometriyle_eslestir(candidates, catalog)
    if complete_missing and callable(geometry_resolver):
        eksik_geometrileri_tkgmden_tamamla(
            candidates,
            geometry_resolver,
            progress=geometry_progress,
        )
    for candidate in candidates:
        candidate["geometry_scan_errors"] = list(catalog.get("errors") or [])
    return candidates


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_load(value, fallback):
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return fallback
    return parsed


def _analysis_record_fields(analysis, cache_path, file_size):
    boundaries = analysis.get("boundaries") or {}
    return {
        "metadata_json": _json(dict(analysis.get("metadata") or {})),
        "il": analysis.get("il", ""),
        "ilce": analysis.get("ilce", ""),
        "mahalle": analysis.get("mahalle", ""),
        "pafta": analysis.get("pafta", ""),
        "ada": analysis.get("ada", ""),
        "parsel": analysis.get("parsel", ""),
        "lat": analysis.get("lat"),
        "lon": analysis.get("lon"),
        "coordinate_source": analysis.get("coordinate_source", ""),
        "start_heading": boundaries.get("start_heading", ""),
        "end_heading": boundaries.get("end_heading", ""),
        "start_index": boundaries.get("start_index", -1),
        "end_index": boundaries.get("end_index", -1),
        "heading_level": boundaries.get("heading_level", 1),
        "paragraph_count": analysis.get("paragraph_count", 0),
        "table_count": analysis.get("table_count", 0),
        "image_count": analysis.get("image_count", 0),
        "warning_json": _json(analysis.get("warnings", [])),
        "cache_path": str(cache_path),
        "file_size": int(file_size),
    }


def _preserve_manual_reindex_values(existing, analysis_fields):
    """Reindex sırasında UI ile elle düzeltilen metadata/koordinatı koru."""
    existing_metadata = dict(existing.get("metadata") or {})
    metadata = dict(_json_load(analysis_fields.get("metadata_json"), {}))
    existing_sources = existing_metadata.get("field_sources")
    if not isinstance(existing_sources, dict):
        existing_sources = {}
    field_sources = metadata.get("field_sources")
    if not isinstance(field_sources, dict):
        field_sources = {}

    for key in _LOCATION_FIELDS:
        if existing_sources.get(key) != "manuel":
            continue
        value = existing.get(key)
        metadata_value = existing_metadata.get(key)
        if value in (None, "") and metadata_value not in (None, ""):
            value = metadata_value
        elif value is None:
            value = existing_metadata.get(key, "")
        analysis_fields[key] = value
        metadata[key] = value
        field_sources[key] = "manuel"

    if existing.get("coordinate_source") == "manuel":
        analysis_fields["lat"] = existing.get("lat")
        analysis_fields["lon"] = existing.get("lon")
        analysis_fields["coordinate_source"] = "manuel"
        field_sources["lat"] = "manuel"
        field_sources["lon"] = "manuel"

    metadata["field_sources"] = field_sources
    analysis_fields["metadata_json"] = _json(metadata)
    return analysis_fields


class JeolojiKutuphane:
    """SQLite tabanlı kütüphane; her çağrıda kısa ömürlü bağlantı kullanır."""

    def __init__(self, db_path=None, cache_dir=None, geometry_dir=None, base_dir=None):
        self.db_path = Path(db_path) if db_path else kutuphane_db_yolu(base_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else kutuphane_cache_dizini(base_dir)
        if geometry_dir is not None:
            self.geometry_dir = Path(geometry_dir)
        elif base_dir is not None:
            self.geometry_dir = kutuphane_geometri_dizini(base_dir)
        elif db_path is not None:
            self.geometry_dir = self.db_path.parent / GEOMETRY_DIR_NAME
        else:
            self.geometry_dir = kutuphane_geometri_dizini()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.geometry_dir.mkdir(parents=True, exist_ok=True)
        self._schema_hazirla()

    def _connect(self):
        connection = sqlite3.connect(str(self.db_path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _schema_hazirla(self):
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS geology_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_hash TEXT NOT NULL UNIQUE,
                    original_filename TEXT NOT NULL DEFAULT '',
                    original_path TEXT NOT NULL DEFAULT '',
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    il TEXT NOT NULL DEFAULT '',
                    ilce TEXT NOT NULL DEFAULT '',
                    mahalle TEXT NOT NULL DEFAULT '',
                    pafta TEXT NOT NULL DEFAULT '',
                    ada TEXT NOT NULL DEFAULT '',
                    parsel TEXT NOT NULL DEFAULT '',
                    lat REAL,
                    lon REAL,
                    coordinate_source TEXT NOT NULL DEFAULT '',
                    start_heading TEXT NOT NULL DEFAULT '',
                    end_heading TEXT NOT NULL DEFAULT '',
                    start_index INTEGER NOT NULL DEFAULT -1,
                    end_index INTEGER NOT NULL DEFAULT -1,
                    heading_level INTEGER NOT NULL DEFAULT 1,
                    paragraph_count INTEGER NOT NULL DEFAULT 0,
                    table_count INTEGER NOT NULL DEFAULT 0,
                    image_count INTEGER NOT NULL DEFAULT 0,
                    warning_json TEXT NOT NULL DEFAULT '[]',
                    cache_path TEXT NOT NULL DEFAULT '',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    kml_path TEXT NOT NULL DEFAULT '',
                    geometry_source TEXT NOT NULL DEFAULT '',
                    geometry_hash TEXT NOT NULL DEFAULT '',
                    geometry_status TEXT NOT NULL DEFAULT '',
                    geometry_metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(geology_sources)").fetchall()
            }
            if "pafta" not in columns:
                connection.execute(
                    "ALTER TABLE geology_sources ADD COLUMN pafta TEXT NOT NULL DEFAULT ''"
                )
            geometry_columns = {
                "kml_path": "TEXT NOT NULL DEFAULT ''",
                "geometry_source": "TEXT NOT NULL DEFAULT ''",
                "geometry_hash": "TEXT NOT NULL DEFAULT ''",
                "geometry_status": "TEXT NOT NULL DEFAULT ''",
                "geometry_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            for column, definition in geometry_columns.items():
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE geology_sources ADD COLUMN {column} {definition}"
                    )

    def _row_to_record(self, row):
        if row is None:
            return None
        record = dict(row)
        record["source_id"] = record["id"]
        record["filename"] = record.get("original_filename", "")
        record["source_path"] = record.get("original_path", "")
        record["warnings"] = _json_load(record.pop("warning_json", "[]"), [])
        record["quality_warnings"] = list(record["warnings"])
        record["metadata"] = _json_load(record.pop("metadata_json", "{}"), {})
        record["geometry_metadata"] = _json_load(
            record.pop("geometry_metadata_json", "{}"),
            {},
        )
        record["heading_boundaries"] = {
            "start_index": record.get("start_index", -1),
            "end_index": record.get("end_index", -1),
            "heading_level": record.get("heading_level", 1),
            "start_heading": record.get("start_heading", ""),
            "end_heading": record.get("end_heading", ""),
        }
        record["coordinate"] = {
            "lat": record.get("lat"),
            "lon": record.get("lon"),
            "source": record.get("coordinate_source", ""),
        }
        return record

    def get_by_hash(self, source_hash):
        source_hash = _text(source_hash).lower()
        if not source_hash:
            return None
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM geology_sources WHERE source_hash = ?", (source_hash,)).fetchone()
        return self._row_to_record(row)

    def get(self, source_id):
        try:
            source_id = int(source_id)
        except (TypeError, ValueError):
            return None
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM geology_sources WHERE id = ?", (source_id,)).fetchone()
        return self._row_to_record(row)

    def _geometry_fields_hazirla(self, candidate=None, existing=None):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("geometry"), dict):
            if existing:
                return {
                    "kml_path": existing.get("kml_path", ""),
                    "geometry_source": existing.get("geometry_source", ""),
                    "geometry_hash": existing.get("geometry_hash", ""),
                    "geometry_status": existing.get("geometry_status", ""),
                    "geometry_metadata_json": _json(existing.get("geometry_metadata") or {}),
                }
            return {
                "kml_path": "",
                "geometry_source": "",
                "geometry_hash": "",
                "geometry_status": (candidate or {}).get("geometry_status", "missing"),
                "geometry_metadata_json": "{}",
            }

        geometry = candidate["geometry"]
        copy_geometry = dict(geometry)
        copy_geometry["polygons"] = [
            [[list(point) for point in ring] for ring in polygon]
            for polygon in geometry.get("polygons", [])
        ]
        geometry_hash = geometri_hash_hesapla(copy_geometry.get("polygons"))
        identity = {
            key: candidate.get(key, "")
            for key in ("il", "ilce", "mahalle", "pafta", "ada", "parsel")
        }
        cache_identity = _json(
            {
                "identity": {
                    key: _fold(identity.get(key))
                    for key in ("il", "ilce", "mahalle", "ada", "parsel")
                },
                "geometry_hash": geometry_hash,
            }
        )
        geometry_cache_key = hashlib.sha256(cache_identity.encode("utf-8")).hexdigest()
        target_path = self.geometry_dir / f"{geometry_cache_key}.kml"
        label = " ".join(
            item
            for item in (
                _clean_space(candidate.get("il")),
                _clean_space(candidate.get("ilce")),
                _clean_space(candidate.get("mahalle")),
                f"{_clean_space(candidate.get('ada'))}/{_clean_space(candidate.get('parsel'))}",
            )
            if item and item != "/"
        ) or "Parsel Sınırı"
        if not target_path.is_file():
            normalize_kml_yaz(
                copy_geometry,
                target_path,
                name=label,
                metadata=identity,
            )
        geometry_metadata = dict(candidate.get("geometry_metadata") or {})
        for key in (
            "polygons", "centroid", "bounds", "polygon_count", "ring_count",
            "point_count", "identity", "placemark_name", "description",
            "source_path", "source_type", "match_type", "match_distance_km",
            "word_centroid_distance_km",
        ):
            if copy_geometry.get(key) is not None:
                geometry_metadata[key] = copy_geometry.get(key)
        geometry_metadata["geometry_hash"] = geometry_hash
        geometry_metadata["geometry_cache_key"] = geometry_cache_key
        geometry_metadata["parcel_identity"] = identity
        return {
            "kml_path": str(target_path),
            "geometry_source": candidate.get("geometry_source") or copy_geometry.get("source_type", ""),
            "geometry_hash": geometry_hash,
            "geometry_status": candidate.get("geometry_status", "selected"),
            "geometry_metadata_json": _json(geometry_metadata),
        }

    def import_docx(self, source_path, analysis=None, source_hash=None, geometry_candidate=None):
        source = Path(source_path)
        if source.suffix.lower() not in _DOCX_EXTENSIONS:
            raise ValueError("Yalnız DOCX/DOCM dosyaları kütüphaneye eklenebilir.")
        if not source.is_file():
            raise FileNotFoundError(str(source))
        actual_source_hash = sha256_dosya(source)
        expected_source_hash = _text(source_hash).lower()
        if not isinstance(analysis, dict) or expected_source_hash != actual_source_hash:
            analysis = docx_analiz_et(source)
        else:
            analysis = dict(analysis)
            analysis["metadata"] = dict(analysis.get("metadata") or {})
            analysis["warnings"] = list(analysis.get("warnings") or [])

        boundaries = analysis.get("boundaries") or {}
        section_found = bool(
            boundaries.get("found", int(boundaries.get("start_index", -1)) >= 0)
        )
        has_content = bool(
            int(analysis.get("paragraph_count") or 0) > 1
            or int(analysis.get("table_count") or 0) > 0
            or int(analysis.get("image_count") or 0) > 0
        )
        if not section_found:
            raise ValueError("Kaynak Word dosyasında 2. JEOLOJİ ana bölümü bulunamadı.")
        if not has_content:
            raise ValueError("Kaynak Word dosyasındaki 2. JEOLOJİ bölümü boş görünüyor.")

        existing = self.get_by_hash(actual_source_hash)
        cache_path = self.cache_dir / f"{actual_source_hash}.docx"
        existing_metadata = (
            existing.get("metadata")
            if existing and isinstance(existing.get("metadata"), dict)
            else {}
        )
        cache_hash = ""
        expected_cache_hash = _text(existing_metadata.get("cache_hash")).lower()
        if (
            existing_metadata.get("cache_kind") == "jeoloji_section"
            and expected_cache_hash
            and cache_path.is_file()
        ):
            try:
                if sha256_dosya(cache_path) == expected_cache_hash:
                    cache_hash = expected_cache_hash
            except OSError:
                cache_hash = ""
        if not cache_hash:
            from jeoloji_docx import jeoloji_bolumunu_dosyaya_cikar

            jeoloji_bolumunu_dosyaya_cikar(
                source,
                cache_path,
                source_boundaries=boundaries,
            )
            cache_hash = sha256_dosya(cache_path)
        metadata = dict(analysis.get("metadata") or {})
        metadata.update(
            {
                "cache_kind": "jeoloji_section",
                "cache_hash": cache_hash,
                "full_source_hash": actual_source_hash,
            }
        )
        analysis["metadata"] = metadata
        analysis_fields = _analysis_record_fields(analysis, cache_path, source.stat().st_size)
        geometry_fields = self._geometry_fields_hazirla(geometry_candidate, existing)
        if existing:
            _preserve_manual_reindex_values(existing, analysis_fields)
            now = _now_iso()
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE geology_sources SET
                        original_filename = ?, original_path = ?, updated_at = ?,
                        metadata_json = ?, il = ?, ilce = ?, mahalle = ?, pafta = ?, ada = ?, parsel = ?,
                        lat = ?, lon = ?, coordinate_source = ?, start_heading = ?, end_heading = ?,
                        start_index = ?, end_index = ?, heading_level = ?, paragraph_count = ?,
                        table_count = ?, image_count = ?, warning_json = ?, cache_path = ?, file_size = ?,
                        kml_path = ?, geometry_source = ?, geometry_hash = ?, geometry_status = ?,
                        geometry_metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        source.name,
                        str(source),
                        now,
                        analysis_fields["metadata_json"],
                        analysis_fields["il"],
                        analysis_fields["ilce"],
                        analysis_fields["mahalle"],
                        analysis_fields["pafta"],
                        analysis_fields["ada"],
                        analysis_fields["parsel"],
                        analysis_fields["lat"],
                        analysis_fields["lon"],
                        analysis_fields["coordinate_source"],
                        analysis_fields["start_heading"],
                        analysis_fields["end_heading"],
                        analysis_fields["start_index"],
                        analysis_fields["end_index"],
                        analysis_fields["heading_level"],
                        analysis_fields["paragraph_count"],
                        analysis_fields["table_count"],
                        analysis_fields["image_count"],
                        analysis_fields["warning_json"],
                        analysis_fields["cache_path"],
                        analysis_fields["file_size"],
                        geometry_fields["kml_path"],
                        geometry_fields["geometry_source"],
                        geometry_fields["geometry_hash"],
                        geometry_fields["geometry_status"],
                        geometry_fields["geometry_metadata_json"],
                        existing["id"],
                    ),
                )
            record = self.get(existing["id"])
            return {"record": record, "duplicate": True, "analysis": analysis}

        now = _now_iso()
        values = (
            actual_source_hash,
            source.name,
            str(source),
            now,
            now,
            analysis_fields["metadata_json"],
            analysis_fields["il"],
            analysis_fields["ilce"],
            analysis_fields["mahalle"],
            analysis_fields["pafta"],
            analysis_fields["ada"],
            analysis_fields["parsel"],
            analysis_fields["lat"],
            analysis_fields["lon"],
            analysis_fields["coordinate_source"],
            analysis_fields["start_heading"],
            analysis_fields["end_heading"],
            analysis_fields["start_index"],
            analysis_fields["end_index"],
            analysis_fields["heading_level"],
            analysis_fields["paragraph_count"],
            analysis_fields["table_count"],
            analysis_fields["image_count"],
            analysis_fields["warning_json"],
            analysis_fields["cache_path"],
            analysis_fields["file_size"],
            geometry_fields["kml_path"],
            geometry_fields["geometry_source"],
            geometry_fields["geometry_hash"],
            geometry_fields["geometry_status"],
            geometry_fields["geometry_metadata_json"],
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO geology_sources (
                    source_hash, original_filename, original_path, added_at, updated_at,
                    metadata_json, il, ilce, mahalle, pafta, ada, parsel, lat, lon,
                    coordinate_source, start_heading, end_heading, start_index, end_index,
                    heading_level, paragraph_count, table_count, image_count, warning_json,
                    cache_path, file_size, kml_path, geometry_source, geometry_hash,
                    geometry_status, geometry_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            source_id = cursor.lastrowid
        return {"record": self.get(source_id), "duplicate": False, "analysis": analysis}

    def import_candidate(self, candidate):
        """Önceden taranmış uygun adayı, kaynak değişmediyse analizini yeniden kullanarak ekle."""
        if not isinstance(candidate, dict):
            raise TypeError("Aday kaydı sözlük olmalıdır.")
        if not candidate.get("eligible"):
            raise ValueError(candidate.get("status") or "Bu aday kütüphaneye eklenemez.")
        return self.import_docx(
            candidate.get("source_path") or candidate.get("original_path"),
            analysis=candidate.get("analysis"),
            source_hash=candidate.get("source_hash"),
            geometry_candidate=candidate,
        )

    def add_document(self, source_path):
        """Daha okunur İngilizce alias; import_docx ile aynı sonucu döndürür."""
        return self.import_docx(source_path)

    def list_records(self, filters=None):
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM geology_sources ORDER BY added_at DESC, id DESC").fetchall()
        records = [self._row_to_record(row) for row in rows]
        return kayitlari_filtrele(records, **(filters or {})) if filters else records

    def count(self):
        with self._connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM geology_sources").fetchone()[0])

    def update_record(self, source_id, updates=None, **kwargs):
        updates = dict(updates or {})
        updates.update(kwargs)
        record = self.get(source_id)
        if record is None:
            return None
        allowed = {"il", "ilce", "mahalle", "pafta", "ada", "parsel", "lat", "lon", "coordinate_source"}
        fields = {}
        for key in allowed:
            if key not in updates:
                continue
            value = updates[key]
            if key in {"lat", "lon"}:
                value = _parse_number(value)
                if value is not None and key == "lat" and not -90 <= value <= 90:
                    raise ValueError("Enlem -90 ile 90 arasında olmalıdır.")
                if value is not None and key == "lon" and not -180 <= value <= 180:
                    raise ValueError("Boylam -180 ile 180 arasında olmalıdır.")
            else:
                value = _clean_space(value)
            fields[key] = value
        if "lat" in fields or "lon" in fields:
            lat = fields.get("lat", record.get("lat"))
            lon = fields.get("lon", record.get("lon"))
            if lat is not None and lon is not None and not _valid_coordinate(lat, lon):
                raise ValueError("Geçerli bir WGS84 enlem/boylam çifti girin.")
            fields.setdefault("coordinate_source", "manuel")
        metadata = dict(record.get("metadata") or {})
        field_sources = metadata.get("field_sources")
        if not isinstance(field_sources, dict):
            field_sources = {}
        for key in _LOCATION_FIELDS:
            if key in fields:
                metadata[key] = fields[key]
                field_sources[key] = "manuel"
        if "lat" in fields or "lon" in fields or fields.get("coordinate_source") == "manuel":
            field_sources["lat"] = "manuel"
            field_sources["lon"] = "manuel"
        metadata["field_sources"] = field_sources
        if fields:
            fields["metadata_json"] = _json(metadata)
            fields["updated_at"] = _now_iso()
            sql = ", ".join(f"{key} = ?" for key in fields)
            with self._connection() as connection:
                connection.execute(f"UPDATE geology_sources SET {sql} WHERE id = ?", (*fields.values(), int(source_id)))
        return self.get(source_id)

    def update_geometry(self, source_id, candidate):
        """Mevcut kaydın yalnız geometri alanlarını yerinde ve atomik güncelle."""
        record = self.get(source_id)
        if record is None:
            return None
        geometry_fields = self._geometry_fields_hazirla(candidate, record)
        if not isinstance((candidate or {}).get("geometry"), dict):
            geometry_fields["geometry_status"] = (
                (candidate or {}).get("geometry_status")
                or record.get("geometry_status")
                or "missing"
            )
        assignments = [
            "kml_path = ?", "geometry_source = ?", "geometry_hash = ?",
            "geometry_status = ?", "geometry_metadata_json = ?", "updated_at = ?",
        ]
        values = [
            geometry_fields["kml_path"],
            geometry_fields["geometry_source"],
            geometry_fields["geometry_hash"],
            geometry_fields["geometry_status"],
            geometry_fields["geometry_metadata_json"],
            _now_iso(),
        ]
        if (
            record.get("lat") is None
            and record.get("lon") is None
            and (candidate or {}).get("coordinate_source") == "kml_centroid"
            and _valid_coordinate((candidate or {}).get("lat"), (candidate or {}).get("lon"))
        ):
            assignments.extend(("lat = ?", "lon = ?", "coordinate_source = ?"))
            values.extend((candidate.get("lat"), candidate.get("lon"), "kml_centroid"))
        values.append(int(source_id))
        with self._connection() as connection:
            connection.execute(
                f"UPDATE geology_sources SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
        return self.get(source_id)

    def delete_record(self, source_id):
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM geology_sources WHERE id = ?", (int(source_id),))
        return cursor.rowcount > 0

    def close(self):
        return None


def _kayittan_geometri_adayi(record):
    return {
        "record_id": record.get("id"),
        "source_path": record.get("original_path") or record.get("source_path") or "",
        "original_path": record.get("original_path") or "",
        "original_filename": record.get("original_filename") or record.get("filename") or "",
        "eligible": True,
        "selected": False,
        "il": record.get("il", ""),
        "ilce": record.get("ilce", ""),
        "mahalle": record.get("mahalle", ""),
        "pafta": record.get("pafta", ""),
        "ada": record.get("ada", ""),
        "parsel": record.get("parsel", ""),
        "lat": record.get("lat"),
        "lon": record.get("lon"),
        "coordinate_source": record.get("coordinate_source", ""),
        "geometry": None,
        "geometry_status": record.get("geometry_status") or "missing",
        "warnings": list(record.get("warnings") or []),
        "analysis": {"warnings": list(record.get("warnings") or [])},
    }


def eksik_kutuphane_geometrilerini_tamamla(
    store,
    resolver=None,
    progress=None,
    search_sources=None,
):
    """Eski nokta-only kayıtları yerel KML ve isteğe bağlı TKGM ile yerinde tamamla."""
    records = store.list_records()
    missing_records = [
        record
        for record in records
        if not (record.get("geometry_metadata") or {}).get("polygons")
    ]
    if not missing_records:
        return {
            "total": 0, "updated": 0, "reused": 0, "local": 0,
            "tkgm": 0, "failed": 0, "skipped": 0, "queries": 0,
            "catalog_errors": [],
        }

    candidates = [_kayittan_geometri_adayi(record) for record in missing_records]
    shared = {}
    for record in records:
        metadata = record.get("geometry_metadata") or {}
        key = parsel_kimlik_anahtari(record)
        if metadata.get("polygons") and all(key):
            geometry = dict(metadata)
            geometry.setdefault("geometry_hash", record.get("geometry_hash", ""))
            geometry.setdefault("source_type", record.get("geometry_source", ""))
            shared.setdefault(key, geometry)

    reused = 0
    unresolved = []
    for candidate in candidates:
        key = parsel_kimlik_anahtari(candidate)
        geometry = shared.get(key) if all(key) else None
        if geometry:
            aday_geometrisini_sec(candidate, geometry, status="library_reused")
            candidate["geometry_source"] = geometry.get("source_type") or "library_cache"
            candidate["geometry_label"] = "Kütüphanedeki aynı parsel sınırı"
            reused += 1
        else:
            unresolved.append(candidate)

    sources = list(search_sources or [])
    for record in missing_records:
        original_path = record.get("original_path")
        if original_path:
            sources.append(original_path)
        kml_path = record.get("kml_path")
        if kml_path:
            sources.append(kml_path)
    sources = list(dict.fromkeys(str(path) for path in sources if path))
    catalog = geometri_katalogu_olustur(sources, recursive=False) if sources else {
        "geometries": [], "errors": [], "paths": []
    }
    adaylari_yerel_geometriyle_eslestir(unresolved, catalog)
    local = sum(bool(candidate.get("geometry")) for candidate in unresolved)

    tkgm_result = {"completed": 0, "failed": 0, "skipped": 0, "queries": 0}
    if callable(resolver):
        tkgm_result = eksik_geometrileri_tkgmden_tamamla(
            unresolved,
            resolver,
            progress=progress,
        )

    updated = 0
    for index, candidate in enumerate(candidates, start=1):
        success = isinstance(candidate.get("geometry"), dict)
        store.update_geometry(candidate["record_id"], candidate)
        updated += int(success)
        if callable(progress) and not callable(resolver):
            progress(index, len(candidates), candidate, success, "")
    return {
        "total": len(candidates),
        "updated": updated,
        "reused": reused,
        "local": local,
        "tkgm": int(tkgm_result.get("completed") or 0),
        "failed": int(tkgm_result.get("failed") or 0),
        "skipped": int(tkgm_result.get("skipped") or 0),
        "queries": int(tkgm_result.get("queries") or 0),
        "catalog_errors": list(catalog.get("errors") or []),
    }


def haversine_km(lat1, lon1, lat2, lon2):
    if not all(_valid_coordinate(a, b) for a, b in ((lat1, lon1), (lat2, lon2))):
        return None
    radius = 6371.0088
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def parsel_kimlik_anahtari(record_or_values):
    """Ada/parseli tek başına değil il+ilçe+mahalle ile birlikte kimliklendir."""
    if isinstance(record_or_values, dict):
        values = (
            record_or_values.get("il", ""),
            record_or_values.get("ilce", ""),
            record_or_values.get("mahalle", ""),
            record_or_values.get("ada", ""),
            record_or_values.get("parsel", ""),
        )
    else:
        values = tuple(record_or_values or ())
    values = tuple(_fold(value) for value in values[:5])
    return values + ("",) * max(0, 5 - len(values))


def kayitlari_filtrele(records, ilce="", mahalle="", formasyon="", aranan="", yaricap_km=None, center=None, project_coord=None):
    """UI'dan bağımsız filtreleme ve yakınlık hesaplama yardımcısı."""
    result = []
    query_ilce = _fold(ilce)
    query_mahalle = _fold(mahalle)
    query_formasyon = _fold(formasyon)
    query_text = _fold(aranan)
    if center is None:
        center = project_coord
    try:
        radius = float(yaricap_km) if _text(yaricap_km) else None
    except (TypeError, ValueError):
        radius = None
    for original in records or []:
        record = dict(original)
        if query_ilce and query_ilce not in _fold(record.get("ilce")):
            continue
        if query_mahalle and query_mahalle not in _fold(record.get("mahalle")):
            continue
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        formations = metadata.get("formasyonlar", []) if isinstance(metadata.get("formasyonlar"), list) else []
        search_blob = " ".join(
            [
                record.get("il", ""), record.get("ilce", ""), record.get("mahalle", ""),
                record.get("pafta", ""), record.get("ada", ""), record.get("parsel", ""), record.get("filename", ""),
                metadata.get("summary_text", ""), " ".join(str(item) for item in formations),
            ]
        )
        if query_formasyon and query_formasyon not in _fold(" ".join(str(item) for item in formations) + " " + metadata.get("summary_text", "")):
            continue
        if query_text and query_text not in _fold(search_blob):
            continue
        distance = None
        if center and len(center) >= 2:
            distance = haversine_km(center[0], center[1], record.get("lat"), record.get("lon"))
        record["distance_km"] = distance
        if radius is not None and radius >= 0 and (distance is None or distance > radius):
            continue
        result.append(record)
    if center:
        result.sort(key=lambda item: (item.get("distance_km") is None, item.get("distance_km") or float("inf"), -int(item.get("id") or 0)))
    else:
        result.sort(key=lambda item: (item.get("added_at", ""), int(item.get("id") or 0)), reverse=True)
    return result


def secili_jeoloji_kaydi(veri, store=None, validate_hash=True):
    """Proje seçim snapshot'ından cache kaydını çöz; dosya yolu taşınsa da çalışır."""
    selection = veri.get("jeoloji_kutuphanesi", {}) if isinstance(veri, dict) else {}
    if not isinstance(selection, dict):
        return None
    source_hash = _text(selection.get("selected_source_hash")).lower()
    source_id = selection.get("selected_source_id")
    snapshot = selection.get("selected_snapshot", {})
    if not source_hash and isinstance(snapshot, dict):
        source_hash = _text(snapshot.get("source_hash")).lower()
    store = store or JeolojiKutuphane()
    record = store.get_by_hash(source_hash) if source_hash else store.get(source_id)
    if record is None and source_id:
        record = store.get(source_id)
    if record is None and not source_hash:
        return None
    if record is None:
        record = {
            "id": source_id,
            "source_id": source_id,
            "source_hash": source_hash,
            "cache_path": "",
            "metadata": {},
            "warnings": [],
        }
    record_metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    cache_kind = _text(record_metadata.get("cache_kind") or snapshot.get("cache_kind"))
    cache_hash = _text(record_metadata.get("cache_hash") or snapshot.get("cache_hash")).lower()
    candidates = []
    candidates.extend([snapshot.get("cache_path"), snapshot.get("cache_name")])
    candidates.extend([record.get("cache_path"), f"{source_hash}.docx" if source_hash else ""])
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if not path.is_absolute():
            path = store.cache_dir / path.name
        if path.is_file():
            expected_hash = cache_hash
            if not expected_hash and cache_kind != "jeoloji_section":
                expected_hash = source_hash
            if expected_hash and validate_hash:
                try:
                    if sha256_dosya(path) != expected_hash:
                        continue
                except OSError:
                    continue
            record["cache_path"] = str(path)
            return record
    return None


def kutuphane_kaydi_ekle(source_path, db_path=None, cache_dir=None):
    return JeolojiKutuphane(db_path=db_path, cache_dir=cache_dir).import_docx(source_path)


def kutuphane_kayitlari_listele(db_path=None, cache_dir=None, filters=None):
    return JeolojiKutuphane(db_path=db_path, cache_dir=cache_dir).list_records(filters=filters)


def kutuphane_kaydi_al(source_id, db_path=None, cache_dir=None):
    return JeolojiKutuphane(db_path=db_path, cache_dir=cache_dir).get(source_id)


def kutuphane_kaydi_hash_ile_al(source_hash, db_path=None, cache_dir=None):
    return JeolojiKutuphane(db_path=db_path, cache_dir=cache_dir).get_by_hash(source_hash)


def kutuphane_kaydi_guncelle(source_id, updates=None, db_path=None, cache_dir=None, **kwargs):
    return JeolojiKutuphane(db_path=db_path, cache_dir=cache_dir).update_record(source_id, updates, **kwargs)


def kutuphane_kaydi_sil(source_id, db_path=None, cache_dir=None):
    return JeolojiKutuphane(db_path=db_path, cache_dir=cache_dir).delete_record(source_id)


def docx_bolum_sinirlerini_bul(doc):
    return bolum_sinirlarini_bul(doc)


__all__ = [
    "BolumSinirlari",
    "JeolojiKutuphane",
    "LIBRARY_DB_NAME",
    "CACHE_DIR_NAME",
    "GEOMETRY_DIR_NAME",
    "baslik_duzeyi",
    "baslik_numarasi",
    "bolum_sinirlerini_bul",
    "docx_dosyalari_bul",
    "docx_analiz_et",
    "docx_bolum_sinirlerini_bul",
    "eksik_kutuphane_geometrilerini_tamamla",
    "haversine_km",
    "jeoloji_adayi_analiz_et",
    "jeoloji_adaylarini_tara",
    "kayitlari_filtrele",
    "koordinat_cikar",
    "kutuphane_cache_dizini",
    "kutuphane_db_yolu",
    "kutuphane_geometri_dizini",
    "kutuphane_kaydi_ekle",
    "kutuphane_kaydi_al",
    "kutuphane_kaydi_guncelle",
    "kutuphane_kaydi_hash_ile_al",
    "kutuphane_kayitlari_listele",
    "kutuphane_kaydi_sil",
    "kutuphane_veri_dizini",
    "parsel_kimlik_anahtari",
    "secili_jeoloji_kaydi",
    "sha256_dosya",
    "word_belgesi_ac",
]
