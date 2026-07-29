# Dosya: RaporPro/evrak_okuma.py
"""İmar ve zemin durum belgelerinden proje alanı önerileri üretir."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz
import numpy as np


class EvrakOkumaHatasi(RuntimeError):
    """Evrak klasörü veya PDF içeriği okunamadığında kullanılır."""


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2.0

    @property
    def height(self):
        return max(1.0, self.y1 - self.y0)


@dataclass(frozen=True)
class EvrakAlani:
    bolum: str
    anahtar: str
    etiket: str
    deger: str
    kaynak: str
    belge_turu: str
    guven: float
    alternatifler: tuple[str, ...] = ()


_OCR_READER = None
_OCR_LOCK = threading.Lock()

_FIELD_LABELS = {
    ("kunye", "sahibi"): "Proje adı / sahibi",
    ("kunye", "mah"): "Mahalle / Köy",
    ("kunye", "paf"): "Pafta",
    ("kunye", "ada"): "Ada",
    ("kunye", "par"): "Parsel",
    ("arazi", "imar_alani"): "İmar alanı",
    ("arazi", "imar_durumu"): "İmar durumu",
    ("bina", "kul"): "Kullanım amacı",
    ("bina", "malz"): "Yapı malzemesi",
    ("bina", "yukseklik"): "Yapı yüksekliği (Hn)",
    ("bina", "ins"): "Toplam inşaat alanı (m²)",
    ("jeoloji", "Qal"): "Jeolojik birim",
}

_FIELD_ORDER = {
    key: index
    for index, key in enumerate(
        (
            ("kunye", "sahibi"),
            ("kunye", "mah"),
            ("kunye", "paf"),
            ("kunye", "ada"),
            ("kunye", "par"),
            ("arazi", "imar_alani"),
            ("arazi", "imar_durumu"),
            ("bina", "kul"),
            ("bina", "malz"),
            ("bina", "yukseklik"),
            ("bina", "ins"),
            ("jeoloji", "Qal"),
        )
    )
}

_IMAR_DURUMU_11 = (
    "Önlemli Alan 1.1 (ÖA-1.1) : "
    "Sıvılaşma Tehlikesi Açısından Önlemli Alanlar"
)


def _ascii_key(value):
    text = str(value or "").replace("ı", "i").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _comparison_key(value):
    text = _ascii_key(value)
    text = re.sub(r"\b(anomim|anonim) sirketi\b", "as", text)
    text = re.sub(r"\blimited sirketi\b", "ltd", text)
    text = re.sub(r"\b(sanayi|san)\b", "san", text)
    text = re.sub(r"\b(ticaret|tic)\b", "tic", text)
    return re.sub(r"\s+", "", text)


def _company_name(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" :-")
    if not text:
        return ""
    text = text.upper()
    replacements = {
        "EYLOL": "EYLÜL",
        "GIRISIM": "GİRİŞİM",
        "GIRIŞIM": "GİRİŞİM",
        "GAYRIMENKUL": "GAYRİMENKUL",
        "SANAYI": "SANAYİ",
        "TICARET": "TİCARET",
        "ANONIM": "ANONİM",
        "ŞIRKETI": "ŞİRKETİ",
        "ŞLRKETİ": "ŞİRKETİ",
        "SIRKETI": "ŞİRKETİ",
    }
    for old, new in replacements.items():
        text = re.sub(rf"\b{re.escape(old)}\b", new, text)
    return re.sub(r"\s+", " ", text).strip()


def _title_value(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" :-")
    return text.title() if text else ""


def _number_value(value):
    match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
    return match.group(0).replace(",", ".") if match else ""


def belge_turunu_belirle(path, embedded_text=""):
    haystack = _ascii_key(f"{os.path.basename(os.fspath(path))} {embedded_text}")
    if "zemin durum belgesi" in haystack:
        return "zemin_durumu"
    if "imar durumu" in haystack:
        return "imar_durumu"
    return ""


def _file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _embedded_text(path):
    try:
        with fitz.open(path) as document:
            if document.page_count:
                return document[0].get_text("text") or ""
    except Exception:
        return ""
    return ""


def evrak_pdflerini_bul(folder):
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise EvrakOkumaHatasi(f"Evrak klasörü bulunamadı: {root}")

    belgeler = []
    duplicate_names = []
    seen_hashes = {}
    for path in sorted(root.rglob("*.pdf"), key=lambda item: item.name.casefold()):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= 0 or size > 100 * 1024 * 1024:
            continue
        file_hash = _file_hash(path)
        if file_hash in seen_hashes:
            duplicate_names.append(path.name)
            continue
        seen_hashes[file_hash] = path
        text = _embedded_text(str(path))
        document_type = belge_turunu_belirle(path, text)
        if not document_type:
            continue
        belgeler.append(
            {
                "path": str(path),
                "name": path.name,
                "type": document_type,
                "sha256": file_hash,
                "embedded_text": text,
            }
        )
    return belgeler, duplicate_names


def _ocr_reader():
    global _OCR_READER
    with _OCR_LOCK:
        if _OCR_READER is None:
            try:
                import easyocr
            except ImportError as exc:
                raise EvrakOkumaHatasi(
                    "Evrak OCR motoru bulunamadı. RaporPro_Baslat.bat ile "
                    "easyocr paketini kurup yeniden deneyin."
                ) from exc
            try:
                _OCR_READER = easyocr.Reader(
                    ["tr", "en"],
                    gpu=False,
                    verbose=False,
                )
            except Exception as exc:
                raise EvrakOkumaHatasi(
                    "Evrak OCR modeli hazırlanamadı. İlk kullanımda internet "
                    "bağlantısı gerekebilir."
                ) from exc
        return _OCR_READER


def _ratio_rect(page, x0, y0, x1, y1):
    rect = page.rect
    return fitz.Rect(
        rect.x0 + rect.width * x0,
        rect.y0 + rect.height * y0,
        rect.x0 + rect.width * x1,
        rect.y0 + rect.height * y1,
    )


def _render_clip(page, ratios, scale):
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        clip=_ratio_rect(page, *ratios),
        colorspace=fitz.csRGB,
        alpha=False,
    )
    image = np.frombuffer(pixmap.samples, dtype=np.uint8)
    return image.reshape(pixmap.height, pixmap.width, pixmap.n)


def _ocr_clip(page, ratios, scale=2.5, allowlist=None):
    image = _render_clip(page, ratios, scale)
    reader = _ocr_reader()
    kwargs = {
        "detail": 1,
        "paragraph": False,
        "decoder": "greedy",
        "batch_size": 1,
        "workers": 0,
    }
    if allowlist:
        kwargs["allowlist"] = allowlist
    with _OCR_LOCK:
        raw_tokens = reader.readtext(image, **kwargs)
    tokens = []
    for box, text, confidence in raw_tokens:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        clean = re.sub(r"\s+", " ", str(text or "")).strip()
        if clean:
            tokens.append(
                OcrToken(
                    text=clean,
                    confidence=float(confidence or 0.0),
                    x0=min(xs),
                    y0=min(ys),
                    x1=max(xs),
                    y1=max(ys),
                )
            )
    return tokens


def _find_labels(tokens, aliases):
    aliases = tuple(_ascii_key(alias) for alias in aliases)
    return [
        token
        for token in tokens
        if any(alias in _ascii_key(token.text) for alias in aliases)
    ]


def _right_value(tokens, aliases, validator=None):
    candidates = []
    for label in _find_labels(tokens, aliases):
        for token in tokens:
            if token is label or token.x0 < label.x1 - 5:
                continue
            tolerance = max(18.0, label.height * 1.35, token.height * 1.1)
            if abs(token.cy - label.cy) > tolerance:
                continue
            if validator is not None and not validator(token.text):
                continue
            candidates.append((token.x0 - label.x1, -token.confidence, token))
    if not candidates:
        return "", 0.0
    token = min(candidates, key=lambda item: (item[0], item[1]))[2]
    return token.text, token.confidence


def _owner_value(tokens):
    owner_labels = _find_labels(tokens, ("adı soyadı", "adi soyadi"))
    mahalle_labels = _find_labels(tokens, ("mahalle",))
    if not owner_labels or not mahalle_labels:
        return "", 0.0
    label = min(owner_labels, key=lambda token: token.cy)
    mahalle = min(
        (token for token in mahalle_labels if token.cy > label.cy),
        key=lambda token: token.cy,
        default=None,
    )
    if mahalle is None:
        return "", 0.0
    right_labels = _find_labels(tokens, ("e başvuru", "e basvuru", "evrak tarihi"))
    x_limit = min(
        (
            token.x0
            for token in right_labels
            if abs(token.cy - label.cy) <= max(35.0, label.height * 2.0)
        ),
        default=max(token.x1 for token in tokens) + 1,
    )
    values = [
        token
        for token in tokens
        if token.x0 >= label.x1 - 5
        and token.x1 <= x_limit + 8
        and label.cy - label.height <= token.cy < mahalle.cy - 4
        and _ascii_key(token.text)
        not in {"mal sahibi", "adi soyadi", "e basvuru tarihi no", "evrak tarihi no"}
    ]
    if not values:
        return "", 0.0
    values.sort(key=lambda token: (round(token.cy / 18.0), token.x0))
    return (
        " ".join(token.text for token in values),
        sum(token.confidence for token in values) / len(values),
    )


def _digit_cell(page, document_type):
    ratios = (
        (0.10, 0.258, 0.26, 0.286)
        if document_type == "imar_durumu"
        else (0.15, 0.260, 0.45, 0.286)
    )
    tokens = _ocr_clip(page, ratios, scale=6.0, allowlist="0123456789")
    values = [
        token
        for token in tokens
        if re.fullmatch(r"\d{1,6}", token.text) and token.confidence >= 0.45
    ]
    if not values:
        return "", 0.0
    token = max(values, key=lambda item: item.confidence)
    return token.text, token.confidence


def _filename_ada_parsel(name):
    normalized = _ascii_key(name)
    match = re.search(r"\b(\d+)\s+ada\s+(\d+)\s+parsel\b", normalized)
    return (match.group(1), match.group(2)) if match else ("", "")


def _candidate(section, key, value, source, document_type, confidence):
    value = str(value or "").strip()
    if not value:
        return None
    return EvrakAlani(
        bolum=section,
        anahtar=key,
        etiket=_FIELD_LABELS[(section, key)],
        deger=value,
        kaynak=source,
        belge_turu=document_type,
        guven=max(0.0, min(1.0, float(confidence))),
    )


def _imar_belgesini_oku(path):
    source = os.path.basename(path)
    candidates = []
    with fitz.open(path) as document:
        if not document.page_count:
            raise EvrakOkumaHatasi(f"PDF sayfası bulunamadı: {source}")
        page = document[0]
        tokens = _ocr_clip(page, (0.015, 0.105, 0.525, 0.585), scale=2.6)
        lower_tokens = _ocr_clip(page, (0.015, 0.545, 0.525, 0.835), scale=2.2)

        owner, owner_conf = _owner_value(tokens)
        candidates.append(
            _candidate(
                "kunye",
                "sahibi",
                _company_name(owner),
                source,
                "İmar Durumu",
                owner_conf,
            )
        )

        mahalle, mahalle_conf = _right_value(
            tokens,
            ("mahalle",),
            lambda value: bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", value)),
        )
        candidates.append(
            _candidate(
                "kunye",
                "mah",
                _title_value(mahalle),
                source,
                "İmar Durumu",
                mahalle_conf,
            )
        )

        pafta_tokens = [
            token
            for token in tokens
            if re.fullmatch(r"[A-Za-z]\d{2}[A-Za-z]\d{2}[A-Za-z0-9]+", token.text)
        ]
        if pafta_tokens:
            pafta = max(pafta_tokens, key=lambda token: token.confidence)
            candidates.append(
                _candidate(
                    "kunye",
                    "paf",
                    pafta.text.upper(),
                    source,
                    "İmar Durumu",
                    pafta.confidence,
                )
            )

        ada, ada_conf = _right_value(
            tokens,
            ("ada",),
            lambda value: bool(re.fullmatch(r"\d{2,7}", value.strip())),
        )
        file_ada, file_parsel = _filename_ada_parsel(source)
        if not ada:
            ada, ada_conf = file_ada, 0.72 if file_ada else 0.0
        candidates.append(
            _candidate("kunye", "ada", ada, source, "İmar Durumu", ada_conf)
        )

        parsel, parsel_conf = _right_value(
            tokens,
            ("parsel",),
            lambda value: bool(re.fullmatch(r"\d{1,7}", value.strip())),
        )
        if not parsel:
            parsel, parsel_conf = _digit_cell(page, "imar_durumu")
        if not parsel and file_parsel:
            parsel, parsel_conf = file_parsel, 0.72
        candidates.append(
            _candidate(
                "kunye", "par", parsel, source, "İmar Durumu", parsel_conf
            )
        )

        total_area, total_conf = _right_value(
            tokens,
            ("toplam inşaat alanı", "toplam insaat alani"),
            lambda value: bool(re.search(r"\d", value)),
        )
        candidates.append(
            _candidate(
                "bina",
                "ins",
                _number_value(total_area),
                source,
                "İmar Durumu",
                total_conf,
            )
        )

        height, height_conf = _right_value(
            tokens,
            ("saçak seviyesi", "sacak seviyesi"),
            lambda value: bool(re.search(r"\d", value)),
        )
        candidates.append(
            _candidate(
                "bina",
                "yukseklik",
                _number_value(height),
                source,
                "İmar Durumu",
                height_conf,
            )
        )

        material, material_conf = _right_value(
            tokens,
            ("binanın cinsi", "binanin cinsi"),
            lambda value: "betonarme" in _ascii_key(value),
        )
        candidates.append(
            _candidate(
                "bina",
                "malz",
                "Betonarme" if material else "",
                source,
                "İmar Durumu",
                material_conf,
            )
        )

        lower_text = " ".join(token.text for token in lower_tokens)
        if "konut alani" in _ascii_key(lower_text):
            candidates.extend(
                (
                    _candidate(
                        "arazi",
                        "imar_alani",
                        "Konut Alanı",
                        source,
                        "İmar Durumu",
                        0.92,
                    ),
                    _candidate(
                        "bina",
                        "kul",
                        "Konut",
                        source,
                        "İmar Durumu",
                        0.92,
                    ),
                )
            )
    return [item for item in candidates if item is not None]


def _zemin_belgesini_oku(path):
    source = os.path.basename(path)
    candidates = []
    with fitz.open(path) as document:
        if not document.page_count:
            raise EvrakOkumaHatasi(f"PDF sayfası bulunamadı: {source}")
        page = document[0]
        tokens = _ocr_clip(page, (0.02, 0.105, 0.98, 0.345), scale=2.8)

        owner, owner_conf = _owner_value(tokens)
        candidates.append(
            _candidate(
                "kunye",
                "sahibi",
                _company_name(owner),
                source,
                "Zemin Durum Belgesi",
                owner_conf,
            )
        )

        mahalle, mahalle_conf = _right_value(
            tokens,
            ("mahalle",),
            lambda value: bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", value)),
        )
        candidates.append(
            _candidate(
                "kunye",
                "mah",
                _title_value(mahalle),
                source,
                "Zemin Durum Belgesi",
                mahalle_conf,
            )
        )

        ada, ada_conf = _right_value(
            tokens,
            ("ada",),
            lambda value: bool(re.fullmatch(r"\d{2,7}", value.strip())),
        )
        file_ada, file_parsel = _filename_ada_parsel(source)
        if not ada:
            ada, ada_conf = file_ada, 0.72 if file_ada else 0.0
        candidates.append(
            _candidate(
                "kunye", "ada", ada, source, "Zemin Durum Belgesi", ada_conf
            )
        )

        parsel, parsel_conf = _right_value(
            tokens,
            ("parsel",),
            lambda value: bool(re.fullmatch(r"\d{1,7}", value.strip())),
        )
        if not parsel:
            parsel, parsel_conf = _digit_cell(page, "zemin_durumu")
        if not parsel and file_parsel:
            parsel, parsel_conf = file_parsel, 0.72
        candidates.append(
            _candidate(
                "kunye",
                "par",
                parsel,
                source,
                "Zemin Durum Belgesi",
                parsel_conf,
            )
        )

        prevention, prevention_conf = _right_value(
            tokens,
            ("önlemli alan", "onlemli alan"),
            lambda value: bool(re.search(r"\d+[.,]\d+", value)),
        )
        prevention_number = _number_value(prevention)
        if prevention_number == "1.1":
            candidates.append(
                _candidate(
                    "arazi",
                    "imar_durumu",
                    _IMAR_DURUMU_11,
                    source,
                    "Zemin Durum Belgesi",
                    prevention_conf,
                )
            )

        formation, formation_conf = _right_value(
            tokens,
            ("formasyon",),
            lambda value: bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", value)),
        )
        if "aluvyon" in _ascii_key(formation):
            candidates.append(
                _candidate(
                    "jeoloji",
                    "Qal",
                    "Alüvyon (Qal)",
                    source,
                    "Zemin Durum Belgesi",
                    formation_conf,
                )
            )
    return [item for item in candidates if item is not None]


def _alanlari_birlestir(candidates):
    grouped = {}
    for candidate in candidates:
        grouped.setdefault((candidate.bolum, candidate.anahtar), []).append(candidate)

    result = []
    warnings = []
    for field_key, values in grouped.items():
        by_value = {}
        for candidate in values:
            by_value.setdefault(_comparison_key(candidate.deger), []).append(candidate)
        ranked = sorted(
            by_value.values(),
            key=lambda group: (
                len(group),
                max(item.guven for item in group),
                sum(item.guven for item in group),
            ),
            reverse=True,
        )
        selected_group = ranked[0]
        selected = max(selected_group, key=lambda item: item.guven)
        sources = sorted({item.kaynak for item in selected_group})
        alternatives = tuple(
            group[0].deger
            for group in ranked[1:]
            if group and _comparison_key(group[0].deger) != _comparison_key(selected.deger)
        )
        if alternatives:
            warnings.append(
                f"{selected.etiket} için farklı değerler bulundu: "
                f"{selected.deger}, {', '.join(alternatives)}"
            )
        result.append(
            EvrakAlani(
                bolum=selected.bolum,
                anahtar=selected.anahtar,
                etiket=selected.etiket,
                deger=selected.deger,
                kaynak=", ".join(sources),
                belge_turu=selected.belge_turu,
                guven=max(item.guven for item in selected_group),
                alternatifler=alternatives,
            )
        )
    result.sort(
        key=lambda item: _FIELD_ORDER.get((item.bolum, item.anahtar), 999)
    )
    return result, warnings


def evrak_klasorunu_oku(folder, task_context=None):
    """Evrak klasörünü tarar ve onay ekranında kullanılacak alanları döndürür."""

    documents, duplicates = evrak_pdflerini_bul(folder)
    if not documents:
        raise EvrakOkumaHatasi(
            "Klasörde İmar Durumu veya Zemin Durum Belgesi bulunamadı."
        )

    candidates = []
    warnings = []
    total = len(documents)
    for index, document in enumerate(documents, start=1):
        if task_context is not None:
            task_context.check_cancelled()
            task_context.report(
                index - 1,
                total,
                f"Okunuyor: {document['name']}",
            )
        try:
            if document["type"] == "imar_durumu":
                candidates.extend(_imar_belgesini_oku(document["path"]))
            elif document["type"] == "zemin_durumu":
                candidates.extend(_zemin_belgesini_oku(document["path"]))
        except Exception as exc:
            warnings.append(f"{document['name']}: {exc}")
        if task_context is not None:
            task_context.report(index, total, f"Okundu: {document['name']}")

    fields, merge_warnings = _alanlari_birlestir(candidates)
    warnings.extend(merge_warnings)
    if duplicates:
        warnings.append(
            f"{len(duplicates)} mükerrer PDF atlandı: {', '.join(duplicates)}"
        )
    if not fields:
        detail = "\n".join(warnings)
        raise EvrakOkumaHatasi(
            "Belgeler bulundu ancak aktarılabilecek alan okunamadı."
            + (f"\n\n{detail}" if detail else "")
        )

    return {
        "klasor": str(Path(folder).resolve()),
        "belgeler": [
            {
                "ad": document["name"],
                "tur": document["type"],
                "sha256": document["sha256"],
            }
            for document in documents
        ],
        "alanlar": [asdict(field) for field in fields],
        "uyarilar": warnings,
        "mukerrerler": duplicates,
    }


__all__ = [
    "EvrakAlani",
    "EvrakOkumaHatasi",
    "OcrToken",
    "belge_turunu_belirle",
    "evrak_klasorunu_oku",
    "evrak_pdflerini_bul",
]
