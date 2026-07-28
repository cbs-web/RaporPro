# Dosya: RaporPro/hidrojeoloji_raporu.py
from __future__ import annotations

import copy
import re
import unicodedata

from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph


YASS_DURUM_SECENEKLERI = (
    "Sondajlardan otomatik",
    "Rastlanmadı",
    "Rastlandı",
    "Belirlenemedi",
)
DERE_DURUM_SECENEKLERI = ("Belirtilmedi", "Yok", "Var")
TASKIN_DURUM_SECENEKLERI = ("Belirtilmedi", "Yok", "Var", "Belirsiz")
YON_SECENEKLERI = (
    "",
    "Kuzey",
    "Kuzeydoğu",
    "Doğu",
    "Güneydoğu",
    "Güney",
    "Güneybatı",
    "Batı",
    "Kuzeybatı",
)

HIDROJEOLOJI_DEFAULT = {
    "yass_durumu": YASS_DURUM_SECENEKLERI[0],
    "akar_dere": DERE_DURUM_SECENEKLERI[0],
    "akar_dere_mesafe": "",
    "akar_dere_yon": "",
    "kuru_dere": DERE_DURUM_SECENEKLERI[0],
    "kuru_dere_mesafe": "",
    "kuru_dere_yon": "",
    "taskin_riski": TASKIN_DURUM_SECENEKLERI[0],
    "deniz_mesafe": "",
    "ek_aciklama": "",
}


def hidrojeoloji_varsayilanlari():
    return copy.deepcopy(HIDROJEOLOJI_DEFAULT)


def _text(value):
    return str(value or "").strip()


def _normalized(value):
    text = _text(value).translate(str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
        "ç": "c", "Ç": "C", "ö": "o", "Ö": "O", "ü": "u", "Ü": "U",
        "ý": "i", "Ý": "I", "þ": "s", "Þ": "S", "ð": "g", "Ð": "G",
    }))
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text)


def _number(value):
    text = _text(value).replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _format_distance(value):
    number = _number(value)
    if number is None:
        return ""
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}".replace(",", ".")
    formatted = f"{number:,.1f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_depth(value):
    return f"{float(value):.2f}".replace(".", ",")


def _status(value, allowed, default):
    normalized = _normalized(value)
    for option in allowed:
        if normalized == _normalized(option):
            return option
    return default


def hidrojeoloji_verisini_normalize_et(arazi):
    source = arazi.get("hidrojeoloji", {}) if isinstance(arazi, dict) else {}
    source = source if isinstance(source, dict) else {}
    result = hidrojeoloji_varsayilanlari()
    for key in result:
        if key in source:
            result[key] = _text(source.get(key))
    result["yass_durumu"] = _status(
        result["yass_durumu"],
        YASS_DURUM_SECENEKLERI,
        YASS_DURUM_SECENEKLERI[0],
    )
    result["akar_dere"] = _status(
        result["akar_dere"],
        DERE_DURUM_SECENEKLERI,
        DERE_DURUM_SECENEKLERI[0],
    )
    result["kuru_dere"] = _status(
        result["kuru_dere"],
        DERE_DURUM_SECENEKLERI,
        DERE_DURUM_SECENEKLERI[0],
    )
    result["taskin_riski"] = _status(
        result["taskin_riski"],
        TASKIN_DURUM_SECENEKLERI,
        TASKIN_DURUM_SECENEKLERI[0],
    )
    return result


def sondaj_yass_seviyeleri(sondajlar):
    values = []
    for sondaj in sondajlar or []:
        if not isinstance(sondaj, dict):
            continue
        for key in ("yass_d1", "yass_d2"):
            raw = _text(sondaj.get(key))
            if not raw:
                continue
            number = _number(raw)
            if number is not None:
                values.append(number)
    return sorted(set(round(value, 6) for value in values))


def _konum_ifadesi(distance, direction):
    distance_text = _format_distance(distance)
    direction_key = _normalized(direction)
    direction_text = {
        "kuzey": "kuzeyinde",
        "kuzeydogu": "kuzeydoğusunda",
        "dogu": "doğusunda",
        "guneydogu": "güneydoğusunda",
        "guney": "güneyinde",
        "guneybati": "güneybatısında",
        "bati": "batısında",
        "kuzeybati": "kuzeybatısında",
    }.get(direction_key, "")
    if distance_text and direction_text:
        return f"yaklaşık {distance_text} m {direction_text}"
    if distance_text:
        return f"yaklaşık {distance_text} m mesafede"
    if direction_text:
        return direction_text
    return "yakın çevresinde"


def _dere_var_cumlesi(kind, distance, direction):
    location = _konum_ifadesi(distance, direction)
    subject = "akar dere" if kind == "akar" else "kuru dere yatağı"
    return f"İnceleme alanının {location} {subject} bulunmaktadır."


def _dere_cumleleri(data):
    akar = data["akar_dere"]
    kuru = data["kuru_dere"]
    sentences = []
    if akar == "Yok" and kuru == "Yok":
        return ["İnceleme alanı ve yakın çevresinde akar veya kuru dere bulunmamaktadır."]
    if akar == "Var":
        sentences.append(_dere_var_cumlesi(
            "akar",
            data["akar_dere_mesafe"],
            data["akar_dere_yon"],
        ))
    elif akar == "Yok":
        sentences.append("İnceleme alanı ve yakın çevresinde akar dere bulunmamaktadır.")
    if kuru == "Var":
        sentences.append(_dere_var_cumlesi(
            "kuru",
            data["kuru_dere_mesafe"],
            data["kuru_dere_yon"],
        ))
    elif kuru == "Yok":
        sentences.append("İnceleme alanı ve yakın çevresinde kuru dere bulunmamaktadır.")
    return sentences


def _taskin_cumlesi(status):
    if status == "Yok":
        return (
            "Mevcut veriler ve arazi gözlemleri kapsamında inceleme alanını "
            "etkileyen bir taşkın riski belirlenmemiştir."
        )
    if status == "Var":
        return (
            "İnceleme alanında taşkın riski bulunduğu değerlendirildiğinden, "
            "ilgili kurum görüşleri doğrultusunda gerekli drenaj ve taşkın "
            "önlemleri projelendirilmelidir."
        )
    if status == "Belirsiz":
        return (
            "Mevcut veriler taşkın riskinin kesin olarak değerlendirilmesi için "
            "yeterli olmadığından, ilgili kurum görüşleri ve güncel taşkın "
            "haritaları dikkate alınmalıdır."
        )
    return ""


def _deniz_cumlesi(distance):
    distance_text = _format_distance(distance)
    if not distance_text:
        return ""
    if _number(distance) == 0:
        return "İnceleme alanı denize kıyı konumundadır."
    return f"İnceleme alanı denize yaklaşık {distance_text} m mesafededir."


def _yass_cumlesi(status, levels):
    if status == "Rastlanmadı":
        return "Yapılan sondajlarda yeraltı suyuna rastlanmamıştır."
    if status == "Belirlenemedi":
        return (
            "Yapılan çalışmalar kapsamında yeraltı suyu seviyesi kesin olarak "
            "belirlenememiştir."
        )

    found = status == "Rastlandı" or (status == "Sondajlardan otomatik" and levels)
    if found and levels:
        if len(levels) == 1:
            depth_text = f"{_format_depth(levels[0])} m derinlikte"
        else:
            depth_text = (
                f"{_format_depth(min(levels))}-{_format_depth(max(levels))} m "
                "derinlikleri arasında"
            )
        return f"Yapılan sondajlarda {depth_text} yeraltı suyuna rastlanmıştır."
    if found:
        return "Yapılan sondajlarda yeraltı suyuna rastlanmıştır."
    return "Yapılan sondajlarda yeraltı suyuna rastlanmamıştır."


def _sentence(value):
    text = re.sub(r"\s+", " ", _text(value))
    if not text:
        return ""
    return text if text[-1] in ".!?" else f"{text}."


def hidrojeoloji_durum_metni(arazi, sondajlar):
    """Proje verilerinden rapora hazır hidrojeoloji durum paragrafı üret."""
    data = hidrojeoloji_verisini_normalize_et(arazi)
    levels = sondaj_yass_seviyeleri(sondajlar)
    sentences = _dere_cumleleri(data)

    flood = _taskin_cumlesi(data["taskin_riski"])
    if flood:
        sentences.append(flood)
    sea = _deniz_cumlesi(data["deniz_mesafe"])
    if sea:
        sentences.append(sea)
    sentences.append(_yass_cumlesi(data["yass_durumu"], levels))

    note = _sentence(data["ek_aciklama"])
    if note:
        sentences.append(note)
    return " ".join(sentence for sentence in sentences if sentence)


def _legacy_hidrojeoloji_paragraph(doc):
    paragraphs = list(doc.paragraphs)
    heading_index = None
    for index, paragraph in enumerate(paragraphs):
        if "hidrojeoloji" in _normalized(paragraph.text):
            heading_index = index
            break
    if heading_index is None:
        return None, None

    for paragraph in paragraphs[heading_index + 1: heading_index + 10]:
        normalized = _normalized(paragraph.text)
        if any(token in normalized for token in ("yeraltisuyu", "denize", "akardere", "kurudere")):
            return paragraph, paragraphs[heading_index]
        if re.match(r"^\d+\.\s+", _text(paragraph.text)):
            break
    return None, paragraphs[heading_index]


def hidrojeoloji_word_paragrafini_uygula(doc, paragraph_index, text):
    """Etiketi veya eski sabit paragrafı dinamik hidrojeoloji metniyle değiştir."""
    paragraph = paragraph_index.get("[HIDROJEOLOJI_DURUM]") if paragraph_index else None
    heading = None
    if paragraph is None:
        paragraph, heading = _legacy_hidrojeoloji_paragraph(doc)
    if paragraph is not None:
        paragraph.text = text
        return True
    if heading is None:
        return False

    element = OxmlElement("w:p")
    heading._p.addnext(element)
    paragraph = Paragraph(element, heading._parent)
    paragraph.add_run(text)
    return True


__all__ = [
    "DERE_DURUM_SECENEKLERI",
    "HIDROJEOLOJI_DEFAULT",
    "TASKIN_DURUM_SECENEKLERI",
    "YASS_DURUM_SECENEKLERI",
    "YON_SECENEKLERI",
    "hidrojeoloji_durum_metni",
    "hidrojeoloji_verisini_normalize_et",
    "hidrojeoloji_varsayilanlari",
    "hidrojeoloji_word_paragrafini_uygula",
    "sondaj_yass_seviyeleri",
]
