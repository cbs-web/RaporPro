# Dosya: RaporPro/litoloji_korelasyon.py
"""LAB, SPT ve renk profillerinden çoklu sondaj litoloji önerileri üretir.

Bu modül yalnızca öneri üretir; proje verisini kendiliğinden değiştirmez.
Litoloji tablolarına aktarım, arayüzdeki açık kullanıcı onayından sonra yapılır.
"""

from __future__ import annotations

import copy
import math
import re
import unicodedata
from collections import defaultdict

from karot_motoru import derinlik_araligi_coz
from ui_lab_sheet import laboratuvar_baslik_bilgisi


KIVAM_SIRASI = (
    "Çok yumuşak",
    "Yumuşak",
    "Orta katı",
    "Katı",
    "Çok katı",
    "Sert",
)

SIKILIK_SIRASI = (
    "Çok gevşek",
    "Gevşek",
    "Orta sıkı",
    "Sıkı",
    "Çok sıkı",
)

PLASTISITE_SIRASI = ("L", "M", "H")

PLASTISITE_ADLARI = {
    "L": "DÜŞÜK PLASTİSİTELİ",
    "M": "ORTA PLASTİSİTELİ",
    "H": "YÜKSEK PLASTİSİTELİ",
}

RENK_SECENEKLERI = (
    "Kahve renkli",
    "Kırmızımsı renkli",
    "Bej renkli",
    "Grimsi renkli",
)

_BIRIM_ADLARI = {
    "cl": "Kil",
    "si": "Silt",
    "sa": "Kum",
    "gr": "Çakıl",
    "rk": "Kaya Birimi",
}

_BIRIM_NITELIKLERI = {
    "cl": "Killi",
    "si": "Siltli",
    "sa": "Kumlu",
    "gr": "Çakıllı",
    "rk": "Kaya",
}

_USCS_KODLARI = {
    "gw": ("gr", "", "W"),
    "gp": ("gr", "", "P"),
    "gm": ("gr", "", "M"),
    "gc": ("gr", "", "C"),
    "sw": ("sa", "", "W"),
    "sp": ("sa", "", "P"),
    "sm": ("sa", "", "M"),
    "sc": ("sa", "", "C"),
    "cl": ("cl", "L", ""),
    "ci": ("cl", "M", ""),
    "ch": ("cl", "H", ""),
    "ml": ("si", "L", ""),
    "mi": ("si", "M", ""),
    "mh": ("si", "H", ""),
}


def _metin(value):
    return "" if value is None else str(value).strip()


def _ascii(value):
    text = _metin(value).casefold()
    text = text.replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _anahtar(value):
    return re.sub(r"[^a-z0-9]+", "", _ascii(value))


def _turkce_buyuk(value):
    return _metin(value).translate(str.maketrans({"i": "İ", "ı": "I"})).upper()


def _sayi(value):
    text = _metin(value).replace(" ", "").replace(",", ".")
    if not text or text.casefold() in {"-", "—", "nan", "none", "null"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def sondaj_anahtari(value):
    """SK-1, SK1 ve sk 1 yazımlarını aynı eşleştirme anahtarına dönüştürür."""
    return _anahtar(value)


def n30_kivam_sinifi(n30=None, refused=False):
    """İnce daneli zemin için kullanıcı tarafından onaylanan N30 tablosu."""
    if refused:
        return "Sert"
    number = _sayi(n30)
    if number is None or number < 0:
        return ""
    if number <= 2:
        return "Çok yumuşak"
    if number <= 4:
        return "Yumuşak"
    if number <= 8:
        return "Orta katı"
    if number <= 15:
        return "Katı"
    if number <= 30:
        return "Çok katı"
    return "Sert"


def n30_sikilik_sinifi(n30=None, refused=False):
    """İri daneli zemin için log lejantıyla uyumlu N30 sıkılık tablosu."""
    if refused:
        return "Çok sıkı"
    number = _sayi(n30)
    if number is None or number < 0:
        return ""
    if number <= 4:
        return "Çok gevşek"
    if number <= 10:
        return "Gevşek"
    if number <= 30:
        return "Orta sıkı"
    if number <= 50:
        return "Sıkı"
    return "Çok sıkı"


def siniflar_ardisik_mi(first, second, order):
    """Aynı veya doğrudan komşu iki sınıfın birleştirilebilirliğini döndürür."""
    first = _metin(first)
    second = _metin(second)
    if not first or not second:
        return True
    if first == second:
        return True
    try:
        return abs(order.index(first) - order.index(second)) == 1
    except ValueError:
        return False


def _kod_parcalari(base):
    parts = []
    pos = 0
    while pos < len(base):
        token = base[pos : pos + 2]
        if token not in _BIRIM_ADLARI:
            return []
        parts.append(token)
        pos += 2
    return parts


def _lab_buyuk_i_yazimini_duzelt(candidate):
    """LAB kodundaki ``Cl`` yerine yazılmış ``CI`` bölümünü güvenle düzeltir.

    Düzeltme yalnızca plastisite son ekinden (L/M/H) önceki ana kil kodunda
    uygulanır. Böylece tek başına kullanılan geçerli ``CI`` kodunun anlamı
    değiştirilmez.
    """
    if not candidate.endswith("ci"):
        return candidate, []
    corrected = f"{candidate[:-2]}cl"
    parts = _kod_parcalari(corrected)
    if not parts or parts[-1] != "cl":
        return candidate, []
    return corrected, parts


def _kanonik_iso_kodu(parts, suffix):
    if not parts:
        return ""
    primary = {
        "cl": "Cl",
        "si": "Si",
        "sa": "Sa",
        "gr": "Gr",
        "rk": "Rk",
    }.get(parts[-1], parts[-1])
    return f"{''.join(parts[:-1])}{primary}{suffix}"


def _metinden_birim(text):
    normalized = _ascii(text)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if any(token in {"kaya", "rock", "karot"} for token in tokens):
        return ["rk"]
    primary = ""
    for token in tokens:
        if token in {"kil", "killi"}:
            primary = "cl"
        elif token in {"silt", "siltli"}:
            primary = "si"
        elif token in {"kum", "kumlu"}:
            primary = "sa"
        elif token in {"cakil", "cakilli"}:
            primary = "gr"
    if not primary:
        return None

    modifiers = []
    primary_word = {
        "cl": {"kil", "killi"},
        "si": {"silt", "siltli"},
        "sa": {"kum", "kumlu"},
        "gr": {"cakil", "cakilli"},
    }[primary]
    primary_index = max(
        (idx for idx, token in enumerate(tokens) if token in primary_word),
        default=-1,
    )
    for token in tokens[:primary_index]:
        code = {
            "killi": "cl",
            "kil": "cl",
            "siltli": "si",
            "silt": "si",
            "kumlu": "sa",
            "kum": "sa",
            "cakilli": "gr",
            "cakil": "gr",
        }.get(token)
        if code and code != primary and code not in modifiers:
            modifiers.append(code)
    return modifiers + [primary]


def sinif_kodu_coz(value):
    """ISO/USCS sınıf kodunu malzeme ve sıralı özelliklerine ayırır.

    Bilinmeyen kodlarda tahmin yürütülmez; ``biliniyor`` False döner.
    """
    raw = _metin(value)
    compact = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü0-9]+", "", raw)
    lowered = _anahtar(compact)
    if not lowered:
        return {
            "raw": raw,
            "kod": "",
            "duzeltilmis_kod": "",
            "normalizasyon_notu": "",
            "malzeme_anahtari": "",
            "ana_birim": "",
            "birim_adi": "",
            "plastisite": "",
            "derecelenme": "",
            "biliniyor": False,
        }

    plasticity = ""
    grading = ""
    parts = []
    corrected_code = ""

    if lowered in _USCS_KODLARI and len(compact) <= 3:
        base, plasticity, grading = _USCS_KODLARI[lowered]
        parts = [base]
    else:
        base = lowered
        if len(base) >= 3 and base[-1] in {"l", "m", "h"}:
            candidate = base[:-1]
            candidate_parts = _kod_parcalari(candidate)
            if not candidate_parts:
                candidate, candidate_parts = _lab_buyuk_i_yazimini_duzelt(
                    candidate
                )
                if candidate_parts:
                    corrected_code = _kanonik_iso_kodu(
                        candidate_parts, base[-1].upper()
                    )
            if candidate_parts and candidate_parts[-1] in {"cl", "si"}:
                plasticity = base[-1].upper()
                base = candidate
                parts = candidate_parts
        if not parts and len(base) >= 3 and base[-1] in {"p", "w", "m"}:
            candidate = base[:-1]
            candidate_parts = _kod_parcalari(candidate)
            if candidate_parts and candidate_parts[-1] in {"sa", "gr"}:
                grading = base[-1].upper()
                base = candidate
                parts = candidate_parts
        if not parts:
            parts = _kod_parcalari(base)

    if not parts:
        parts = _metinden_birim(raw) or []

    if not parts:
        return {
            "raw": raw,
            "kod": lowered,
            "duzeltilmis_kod": "",
            "normalizasyon_notu": "",
            "malzeme_anahtari": lowered,
            "ana_birim": "",
            "birim_adi": raw,
            "plastisite": "",
            "derecelenme": "",
            "biliniyor": False,
        }

    primary = parts[-1]
    modifiers = parts[:-1]
    name_parts = [_BIRIM_NITELIKLERI[item] for item in modifiers]
    name_parts.append(_BIRIM_ADLARI[primary])
    base_key = "".join(parts)
    return {
        "raw": raw,
        "kod": lowered,
        "duzeltilmis_kod": corrected_code,
        "normalizasyon_notu": (
            "LAB kodundaki büyük I, küçük l olarak yorumlandı."
            if corrected_code
            else ""
        ),
        "malzeme_anahtari": base_key,
        "ana_birim": primary,
        "birim_adi": " ".join(name_parts),
        "plastisite": plasticity,
        "derecelenme": grading,
        "biliniyor": True,
    }


def zemin_davranis_sinifi(parsed_code, n30=None, refused=False):
    primary = (parsed_code or {}).get("ana_birim", "")
    if primary in {"cl", "si"}:
        return n30_kivam_sinifi(n30, refused=refused)
    if primary in {"sa", "gr"}:
        return n30_sikilik_sinifi(n30, refused=refused)
    return ""


def _sinif_araligi(values, order):
    unique = []
    for value in values or []:
        value = _metin(value)
        if value and value in order and value not in unique:
            unique.append(value)
    if not unique:
        return ""
    indexes = sorted(order.index(value) for value in unique)
    first = order[indexes[0]]
    last = order[indexes[-1]]
    return first if first == last else f"{first}-{last}"


def litoloji_tanimi_olustur(
    parsed_code,
    davranislar=None,
    plastisiteler=None,
    renk=None,
):
    parsed_code = parsed_code or {}
    if not parsed_code.get("biliniyor"):
        return "TANIMSIZ BİRİM - ELLE DÜZENLEYİN"

    primary = parsed_code.get("ana_birim")
    order = KIVAM_SIRASI if primary in {"cl", "si"} else SIKILIK_SIRASI
    behavior = _sinif_araligi(davranislar, order)
    plasticity = _sinif_araligi(
        plastisiteler or [parsed_code.get("plastisite")],
        PLASTISITE_SIRASI,
    )
    prefix_parts = []
    color_text = _metin(renk)
    if color_text:
        prefix_parts.append(_turkce_buyuk(color_text))
    if behavior:
        prefix_parts.append(_turkce_buyuk(behavior))
    material_parts = []
    if plasticity:
        if "-" in plasticity:
            first, last = plasticity.split("-", 1)
            material_parts.append(
                f"{PLASTISITE_ADLARI[first].replace(' PLASTİSİTELİ', '')}-"
                f"{PLASTISITE_ADLARI[last]}"
            )
        else:
            material_parts.append(PLASTISITE_ADLARI[plasticity])
    material_parts.append(_turkce_buyuk(parsed_code.get("birim_adi", "")))
    material_text = " ".join(part for part in material_parts if part)
    return ", ".join(part for part in [*prefix_parts, material_text] if part)


def _derinlik_acik_aralik_mi(raw):
    numbers = re.findall(r"\d+(?:[.,]\d+)?", _metin(raw))
    return len(numbers) >= 2


def laboratuvar_litoloji_kayitlari(rows, sondajlar=None, varsayilan_numune_boyu=1.5):
    """LAB Sheet'teki sınıf ve derinlik kayıtlarını korelasyon girdisine çevirir."""
    info = laboratuvar_baslik_bilgisi(rows)
    class_col = info.get("columns", {}).get("sinif")
    if class_col is None:
        return {
            "records": [],
            "warnings": ["LAB Sheet içinde sınıflama/USCS sütunu bulunamadı."],
            "header_found": bool(info.get("rows")),
        }

    well_col = info["columns"].get("sondaj", 0)
    sample_col = info["columns"].get("numune", 1)
    depth_col = info["columns"].get("derinlik", 2)
    well_depths = {
        sondaj_anahtari(item.get("no")): _sayi(item.get("der"))
        for item in (sondajlar or [])
        if isinstance(item, dict)
    }
    records = []
    warnings = []
    current_well = ""
    # Çok satırlı başlıklarda gerçek veri başlangıcı biçimden biçime değişebilir.
    # Başlık satırından sonra tarayıp, yalnızca geçerli kuyu+derinlik+sınıf üçlüsünü
    # kabul etmek dar veya sade LAB tablolarını da destekler.
    start_row = min(
        len(info.get("rows", [])),
        int(info.get("header_row", 0)) + 1,
    )
    for row_index in range(start_row, len(info.get("rows", []))):
        row = info["rows"][row_index]
        well = _metin(row[well_col] if well_col < len(row) else "")
        if well:
            current_well = well
        raw_depth = _metin(row[depth_col] if depth_col < len(row) else "")
        class_value = _metin(row[class_col] if class_col < len(row) else "")
        sample_value = _metin(row[sample_col] if sample_col < len(row) else "")
        if not class_value and any(
            marker in _anahtar(sample_value)
            for marker in ("karot", "rock", "kaya")
        ):
            # Bu yalnızca LAB numune türünü kaya ankrajı olarak kullanır.
            # TCR/SCR/RQD veya başka karot sayısal değerleri okunmaz.
            class_value = "Kaya"
        if not current_well or not raw_depth or not class_value:
            continue

        explicit_interval = _derinlik_acik_aralik_mi(raw_depth)
        top, bottom = derinlik_araligi_coz(raw_depth)
        if not explicit_interval:
            bottom = top + max(0.5, float(varsayilan_numune_boyu or 1.5))
        total_depth = well_depths.get(sondaj_anahtari(current_well))
        if total_depth is not None and total_depth > 0:
            bottom = min(bottom, total_depth)
        if bottom <= top:
            continue

        parsed = sinif_kodu_coz(class_value)
        if not parsed["biliniyor"]:
            warnings.append(
                f"LAB satır {row_index + 1}: '{class_value}' sınıf kodu tanınmadı; "
                "elle kontrol edilmelidir."
            )
        records.append(
            {
                "row_index": row_index,
                "sondaj": current_well,
                "sondaj_key": sondaj_anahtari(current_well),
                "top": round(float(top), 3),
                "bottom": round(float(bottom), 3),
                "raw_depth": raw_depth,
                "derinlik_turu": "aralik" if explicit_interval else "baslangic",
                "sinif": class_value,
                "parsed": parsed,
                "kaynak": "LAB",
            }
        )

    records_by_well = defaultdict(list)
    for record in records:
        records_by_well[record["sondaj_key"]].append(record)
    for well_key, well_records in records_by_well.items():
        ordered = sorted(
            well_records,
            key=lambda item: (float(item["top"]), int(item["row_index"])),
        )
        total_depth = well_depths.get(well_key)
        for index, record in enumerate(ordered):
            if record.get("derinlik_turu") == "aralik":
                continue
            next_top = next(
                (
                    float(item["top"])
                    for item in ordered[index + 1 :]
                    if float(item["top"]) > float(record["top"]) + 1e-6
                ),
                None,
            )
            inferred_bottom = (
                next_top
                if next_top is not None
                else float(total_depth)
                if total_depth is not None and total_depth > float(record["top"])
                else float(record["bottom"])
            )
            if inferred_bottom > float(record["top"]):
                record["bottom"] = round(inferred_bottom, 3)
    return {
        "records": records,
        "warnings": warnings,
        "header_found": True,
    }


def spt_satirini_coz(row):
    if not isinstance(row, (list, tuple)) or not row:
        return None
    depth = _sayi(row[0])
    if depth is None or depth < 0:
        return None
    values = [_metin(value) for value in row[1:5]]
    lowered = [value.casefold() for value in values]
    refused = any(
        value in {"r", "-"}
        or "refu" in value
        or "50/" in value.replace(" ", "")
        for value in lowered
    )
    n30 = _sayi(row[4]) if len(row) > 4 else None
    if n30 is None and len(row) > 3 and not refused:
        second = _sayi(row[2])
        third = _sayi(row[3])
        if second is not None and third is not None:
            n30 = second + third
    return {
        "depth": float(depth),
        "n30": n30,
        "refused": refused,
    }


def sondaj_spt_kayitlari(sondaj, etki_boyu=1.5, deney_boyu=0.45):
    """SPT kayıtlarını deney ve temsil (etki) aralıklarıyla döndürür.

    SPT deneyi başlangıç derinliğinden itibaren 45 cm sürse de N30 değeri,
    zemin tanımında bir sonraki SPT başlangıcına kadar temsil edici kabul
    edilir. Son kayıtta varsayılan temsil boyu kullanılır ve kuyu sonu aşılmaz.
    """
    result = []
    total_depth = _sayi((sondaj or {}).get("der"))
    for row_index, row in enumerate((sondaj or {}).get("spt", []) or []):
        parsed = spt_satirini_coz(row)
        if not parsed:
            continue
        parsed["row_index"] = row_index
        result.append(parsed)
    result.sort(key=lambda item: (item["depth"], item["row_index"]))

    default_effect = max(0.5, float(etki_boyu or 1.5))
    test_length = max(0.0, float(deney_boyu or 0.45))
    for index, parsed in enumerate(result):
        depth = parsed["depth"]
        next_depth = next(
            (
                item["depth"]
                for item in result[index + 1 :]
                if item["depth"] > depth + 1e-6
            ),
            None,
        )
        bottom = next_depth if next_depth is not None else depth + default_effect
        if total_depth is not None and total_depth > 0:
            bottom = min(bottom, total_depth)
        bottom = max(depth, bottom)
        parsed["deney_top"] = depth
        parsed["deney_bottom"] = min(depth + test_length, bottom)
        parsed["top"] = depth
        parsed["bottom"] = bottom
    return result


def _aralik_degeri(records, depth):
    covering = [
        record
        for record in records or []
        if record.get("top", 0) - 1e-6 <= depth
        and depth < record.get("bottom", 0)
    ]
    if not covering:
        return None
    exact = sorted(
        covering,
        key=lambda item: (
            item.get("bottom", 0) - item.get("top", 0),
            item.get("row_index", 0),
        ),
    )
    return exact[0]


def _profil_kaydi(sondaj, depth):
    photo = (sondaj or {}).get("litoloji_fotografi", {}) or {}
    profile = photo.get("renk_profili", []) or (sondaj or {}).get(
        "litoloji_renk_profili", []
    )
    return _aralik_degeri(profile, depth)


def _rgb_similarity(first, second):
    if not first or not second:
        return None
    try:
        from litoloji_renk_motoru import renk_benzerligi

        return renk_benzerligi(first, second)
    except Exception:
        return None


def _gap_to_interval(depth, record):
    if record["top"] <= depth <= record["bottom"]:
        return 0.0
    return min(abs(depth - record["top"]), abs(depth - record["bottom"]))


def _aligned_distance(target_well, target_depth, source_well, source_record):
    target_elevation = _sayi(target_well.get("k"))
    source_elevation = _sayi(source_well.get("k"))
    source_mid = (source_record["top"] + source_record["bottom"]) / 2
    if target_elevation is not None and source_elevation is not None:
        target_level = target_elevation - target_depth
        source_level = source_elevation - source_mid
        return abs(target_level - source_level), "kot"
    return abs(target_depth - source_mid), "derinlik"


def _n30_for_depth(spt_records, depth):
    return _aralik_degeri(spt_records, depth)


def _candidate_score(
    target_well,
    target_depth,
    target_color,
    source_well,
    record,
    same_well,
):
    source_mid = (record["top"] + record["bottom"]) / 2
    source_color_record = _profil_kaydi(source_well, source_mid)
    color_similarity = _rgb_similarity(
        (target_color or {}).get("rgb"),
        (source_color_record or {}).get("rgb"),
    )
    if same_well:
        distance = _gap_to_interval(target_depth, record)
        if distance > 3.0 and (color_similarity is None or color_similarity < 0.78):
            return None
        if distance <= 3.0:
            score = 4.0 - min(3.0, distance)
        else:
            score = 1.2 - min(0.8, (distance - 3.0) * 0.12)
        alignment = "aynı sondaj"
    else:
        distance, alignment = _aligned_distance(
            target_well, target_depth, source_well, record
        )
        if distance > 1.25 and (
            distance > 4.0
            or color_similarity is None
            or color_similarity < 0.82
        ):
            return None
        if distance <= 1.25:
            score = 4.5 - min(2.5, distance * 1.6)
        else:
            score = 1.0 - min(0.7, (distance - 1.25) * 0.18)
    if color_similarity is not None:
        score += color_similarity * 2.0
    return {
        "score": score,
        "distance": distance,
        "alignment": alignment,
        "color_similarity": color_similarity,
    }


def _cell_mergeable(first, second):
    if first.get("malzeme_anahtari") != second.get("malzeme_anahtari"):
        return False
    if not first.get("malzeme_anahtari"):
        return True

    if not siniflar_ardisik_mi(
        first.get("plastisite"),
        second.get("plastisite"),
        PLASTISITE_SIRASI,
    ):
        return False
    first_grading = first.get("derecelenme", "")
    second_grading = second.get("derecelenme", "")
    if first_grading and second_grading and first_grading != second_grading:
        return False

    primary = first.get("ana_birim")
    order = KIVAM_SIRASI if primary in {"cl", "si"} else SIKILIK_SIRASI
    return siniflar_ardisik_mi(
        first.get("davranis"),
        second.get("davranis"),
        order,
    )


def _group_cell_mergeable(group, cell):
    """Boş özellik hücresinin iki uzak sınıf arasında köprü kurmasını engeller."""
    if not group or not _cell_mergeable(group[-1], cell):
        return False
    if not cell.get("malzeme_anahtari"):
        return True

    known_plasticity = next(
        (item.get("plastisite") for item in reversed(group) if item.get("plastisite")),
        "",
    )
    if cell.get("plastisite") and known_plasticity and not siniflar_ardisik_mi(
        known_plasticity,
        cell.get("plastisite"),
        PLASTISITE_SIRASI,
    ):
        return False

    primary = cell.get("ana_birim")
    order = KIVAM_SIRASI if primary in {"cl", "si"} else SIKILIK_SIRASI
    known_behavior = next(
        (item.get("davranis") for item in reversed(group) if item.get("davranis")),
        "",
    )
    if cell.get("davranis") and known_behavior and not siniflar_ardisik_mi(
        known_behavior,
        cell.get("davranis"),
        order,
    ):
        return False
    return True


def _evidence_segments(cells):
    segments = []
    for cell in cells:
        status = cell.get("kanit_durumu", "bilinmiyor")
        sources = tuple(cell.get("kaynaklar", []))
        if (
            segments
            and segments[-1]["durum"] == status
            and segments[-1]["kaynaklar"] == list(sources)
            and abs(segments[-1]["bottom"] - cell["top"]) < 1e-6
        ):
            segments[-1]["bottom"] = cell["bottom"]
        else:
            segments.append(
                {
                    "top": cell["top"],
                    "bottom": cell["bottom"],
                    "durum": status,
                    "kaynaklar": list(sources),
                }
            )
    return segments


def hucreleri_katmanlara_birlestir(cells):
    """0,50 m hücreleri malzeme ve sıralı özellik kurallarıyla katmanlaştırır."""
    cells = sorted(copy.deepcopy(cells or []), key=lambda item: item["top"])
    if not cells:
        return []
    groups = [[cells[0]]]
    for cell in cells[1:]:
        previous = groups[-1][-1]
        contiguous = abs(previous["bottom"] - cell["top"]) < 1e-6
        if contiguous and _group_cell_mergeable(groups[-1], cell):
            groups[-1].append(cell)
        else:
            groups.append([cell])

    layers = []
    for index, group in enumerate(groups):
        first = group[0]
        parsed = sinif_kodu_coz(first.get("sinif") or first.get("malzeme_anahtari"))
        if first.get("birim_adi"):
            parsed["birim_adi"] = first["birim_adi"]
            parsed["biliniyor"] = bool(first.get("malzeme_anahtari"))
            parsed["ana_birim"] = first.get("ana_birim", parsed.get("ana_birim"))
            parsed["plastisite"] = first.get(
                "plastisite", parsed.get("plastisite", "")
            )
        behaviors = [
            item.get("davranis", "")
            for item in group
            if item.get("davranis")
        ]
        plasticities = [
            item.get("plastisite", "")
            for item in group
            if item.get("plastisite")
        ]
        evidence = _evidence_segments(group)
        statuses = {item["durum"] for item in evidence}
        status = (
            next(iter(statuses))
            if len(statuses) == 1
            else "karma"
        )
        layers.append(
            {
                "id": f"katman-{index + 1}",
                "top": group[0]["top"],
                "bottom": group[-1]["bottom"],
                "sinif": first.get("sinif", ""),
                "malzeme_anahtari": first.get("malzeme_anahtari", ""),
                "ana_birim": first.get("ana_birim", ""),
                "birim_adi": first.get("birim_adi", ""),
                "plastisiteler": list(dict.fromkeys(plasticities)),
                "davranislar": list(dict.fromkeys(behaviors)),
                "renk": first.get("renk", ""),
                "atama_id": first.get("atama_id", ""),
                "lab_row_index": first.get("lab_row_index"),
                "lab_sondaj": first.get("lab_sondaj", ""),
                "lab_derinlik": first.get("lab_derinlik", ""),
                "spt_degerleri": list(
                    dict.fromkeys(
                        item.get("n30")
                        for item in group
                        if item.get("n30") is not None
                    )
                ),
                "kanit_durumu": status,
                "kanit_segmentleri": evidence,
                "tanim": litoloji_tanimi_olustur(
                    parsed,
                    davranislar=behaviors,
                    plastisiteler=plasticities,
                    renk=first.get("renk", ""),
                ),
                "elle_duzenlendi": False,
            }
        )
    return layers


def manuel_lab_katmanlari_olustur(
    sondaj,
    lab_record,
    top,
    bottom,
    renk,
    *,
    adim=0.5,
    atama_id="",
):
    """Kullanıcının işaretlediği LAB birimini SPT destekli katmanlara dönüştürür."""
    if not isinstance(sondaj, dict):
        raise ValueError("Geçerli bir sondaj seçilmelidir.")
    if not isinstance(lab_record, dict):
        raise ValueError("Laboratuvar rehberinden bir kayıt seçilmelidir.")
    parsed = copy.deepcopy(lab_record.get("parsed") or {})
    if not parsed.get("biliniyor"):
        parsed = sinif_kodu_coz(lab_record.get("sinif", ""))
    if not parsed.get("biliniyor"):
        raise ValueError(
            f"'{lab_record.get('sinif', '')}' zemin sınıfı tanınmadı; "
            "LAB kaydını kontrol edin."
        )
    color = _metin(renk)
    if color not in RENK_SECENEKLERI:
        raise ValueError("Hazır renk seçeneklerinden biri seçilmelidir.")

    start = _sayi(top)
    end = _sayi(bottom)
    total_depth = _sayi(sondaj.get("der"))
    if start is None or end is None:
        raise ValueError("Başlangıç ve bitiş derinlikleri sayısal olmalıdır.")
    raw_end = end
    start = round(start * 2) / 2
    end = (
        float(total_depth)
        if total_depth is not None and abs(raw_end - total_depth) <= 1e-6
        else round(end * 2) / 2
    )
    if start < 0 or end <= start:
        raise ValueError("Bitiş derinliği başlangıçtan büyük olmalıdır.")
    if total_depth is not None and total_depth > 0 and end > total_depth + 1e-6:
        raise ValueError("İşaretlenen aralık sondaj derinliğini aşamaz.")

    step = max(0.5, round(float(adim or 0.5) * 2) / 2)
    spt_records = sondaj_spt_kayitlari(sondaj)
    assignment_id = _metin(atama_id) or (
        f"lab-{lab_record.get('row_index', 'x')}-{start:.2f}-{end:.2f}"
    )
    cells = []
    depth = start
    while depth < end - 1e-9:
        cell_bottom = min(end, round(depth + step, 3))
        mid = (depth + cell_bottom) / 2
        spt_record = _n30_for_depth(spt_records, mid)
        behavior = zemin_davranis_sinifi(
            parsed,
            (spt_record or {}).get("n30"),
            refused=bool((spt_record or {}).get("refused")),
        )
        sources = [
            f"Kullanıcı işaretlemesi: {start:.2f}-{end:.2f} m",
            f"LAB satır {int(lab_record.get('row_index', 0)) + 1}: "
            f"{lab_record.get('sinif', '')} "
            f"({lab_record.get('raw_depth', '')} m)",
        ]
        if spt_record:
            n30_text = (
                "refü"
                if spt_record.get("refused")
                else f"N30={spt_record.get('n30'):g}"
                if spt_record.get("n30") is not None
                else "N30 boş"
            )
            sources.append(f"SPT {spt_record['depth']:.2f} m: {n30_text}")
        else:
            sources.append("Bu alt aralıkta eşleşen SPT kaydı yok.")
        cells.append(
            {
                "top": round(depth, 3),
                "bottom": round(cell_bottom, 3),
                "sinif": lab_record.get("sinif", ""),
                "malzeme_anahtari": parsed.get("malzeme_anahtari", ""),
                "ana_birim": parsed.get("ana_birim", ""),
                "birim_adi": parsed.get("birim_adi", ""),
                "plastisite": parsed.get("plastisite", ""),
                "derecelenme": parsed.get("derecelenme", ""),
                "davranis": behavior,
                "renk": color,
                "atama_id": assignment_id,
                "lab_row_index": lab_record.get("row_index"),
                "lab_sondaj": lab_record.get("sondaj", ""),
                "lab_derinlik": lab_record.get("raw_depth", ""),
                "kanit_durumu": "manuel_lab",
                "guven": 1.0,
                "kaynaklar": sources,
                "n30": (spt_record or {}).get("n30"),
            }
        )
        depth = cell_bottom
    return hucreleri_katmanlara_birlestir(cells)


def manuel_atama_cakisiyor(katmanlar, top, bottom, ignore_assignment_id=""):
    start = _sayi(top)
    end = _sayi(bottom)
    if start is None or end is None:
        return True
    ignored = _metin(ignore_assignment_id)
    for layer in katmanlar or []:
        if ignored and _metin(layer.get("atama_id")) == ignored:
            continue
        layer_top = _sayi(layer.get("top"))
        layer_bottom = _sayi(layer.get("bottom"))
        if layer_top is None or layer_bottom is None:
            continue
        if min(end, layer_bottom) - max(start, layer_top) > 1e-6:
            return True
    return False


def manuel_katmanlari_dogrula(katmanlar, sondaj_derinligi, tolerance=0.01):
    """Onay öncesi boşluk, çakışma ve kuyu kapsamı denetimi."""
    depth = _sayi(sondaj_derinligi)
    issues = []
    normalized = []
    for index, layer in enumerate(katmanlar or []):
        top = _sayi(layer.get("top"))
        bottom = _sayi(layer.get("bottom"))
        if top is None or bottom is None or bottom <= top:
            issues.append(f"{index + 1}. katmanın derinlik aralığı geçersiz.")
            continue
        normalized.append((top, bottom, layer))
    normalized.sort(key=lambda item: item[0])
    expected = 0.0
    covered_length = 0.0
    coverage_end = 0.0
    for top, bottom, _layer in normalized:
        if top > expected + tolerance:
            issues.append(f"{expected:.2f}-{top:.2f} m arasında boşluk var.")
        elif top < expected - tolerance:
            issues.append(f"{top:.2f} m başlangıcında katman çakışması var.")
        expected = max(expected, bottom)
        clipped_top = max(0.0, top)
        clipped_bottom = min(bottom, depth) if depth is not None and depth > 0 else bottom
        if clipped_bottom > clipped_top:
            if clipped_top >= coverage_end:
                covered_length += clipped_bottom - clipped_top
            elif clipped_bottom > coverage_end:
                covered_length += clipped_bottom - coverage_end
            coverage_end = max(coverage_end, clipped_bottom)
    if depth is None or depth <= 0:
        issues.append("Sondaj derinliği geçerli değil.")
    else:
        if expected < depth - tolerance:
            issues.append(f"{expected:.2f}-{depth:.2f} m arasında boşluk var.")
        if expected > depth + tolerance:
            issues.append(
                f"Katmanlar sondaj derinliğini {expected - depth:.2f} m aşıyor."
            )
    return {
        "valid": not issues,
        "issues": issues,
        "covered": min(covered_length, depth or covered_length),
        "depth": depth or 0.0,
    }


def coklu_sondaj_onerileri_olustur(
    veri,
    adim=0.5,
    varsayilan_numune_boyu=1.5,
):
    """Tüm sondajlar için güvenli, uygulanmamış litoloji önerisi üretir."""
    source = veri if isinstance(veri, dict) else {}
    sondajlar = [
        item for item in source.get("sondaj", []) or [] if isinstance(item, dict)
    ]
    lab_result = laboratuvar_litoloji_kayitlari(
        (source.get("lab_sheet", {}) or {}).get("rows", []),
        sondajlar=sondajlar,
        varsayilan_numune_boyu=varsayilan_numune_boyu,
    )
    lab_by_well = defaultdict(list)
    for record in lab_result["records"]:
        lab_by_well[record["sondaj_key"]].append(record)

    well_map = {
        sondaj_anahtari(item.get("no")): item
        for item in sondajlar
        if sondaj_anahtari(item.get("no"))
    }
    spt_map = {
        key: sondaj_spt_kayitlari(well)
        for key, well in well_map.items()
    }
    result_wells = []
    warnings = list(lab_result.get("warnings", []))
    step = max(0.5, round(float(adim or 0.5) * 2) / 2)

    for well_index, well in enumerate(sondajlar):
        key = sondaj_anahtari(well.get("no"))
        total_depth = _sayi(well.get("der")) or 0.0
        if total_depth <= 0:
            warnings.append(
                f"{well.get('no') or well_index + 1}: sondaj derinliği olmadığı için öneri üretilmedi."
            )
            result_wells.append(
                {
                    "sondaj_index": well_index,
                    "sondaj_no": well.get("no") or f"SK-{well_index + 1}",
                    "katmanlar": [],
                    "hucreler": [],
                }
            )
            continue

        cells = []
        top = 0.0
        while top < total_depth - 1e-9:
            bottom = min(total_depth, round(top + step, 3))
            mid = (top + bottom) / 2
            lab_record = _aralik_degeri(lab_by_well.get(key, []), mid)
            spt_record = _n30_for_depth(spt_map.get(key, []), mid)
            target_color = _profil_kaydi(well, mid)

            if lab_record:
                parsed = lab_record["parsed"]
                sources = [
                    f"LAB satır {lab_record['row_index'] + 1}: "
                    f"{lab_record['sinif']} ({lab_record['raw_depth']} m)"
                ]
                status = "lab_onayli"
                confidence = 1.0
                class_value = lab_record["sinif"]
            else:
                candidates = []
                for source_key, records in lab_by_well.items():
                    source_well = well_map.get(source_key)
                    if not source_well:
                        continue
                    for record in records:
                        if not record["parsed"].get("biliniyor"):
                            continue
                        scored = _candidate_score(
                            well,
                            mid,
                            target_color,
                            source_well,
                            record,
                            same_well=(source_key == key),
                        )
                        if scored is None:
                            continue
                        candidates.append((scored["score"], record, scored))

                if candidates:
                    candidates.sort(key=lambda item: item[0], reverse=True)
                    score, best, detail = candidates[0]
                    parsed = best["parsed"]
                    class_value = best["sinif"]
                    similarity = detail.get("color_similarity")
                    color_text = (
                        f", renk benzerliği %{similarity * 100:.0f}"
                        if similarity is not None
                        else ""
                    )
                    sources = [
                        f"Korelasyon: {best['sondaj']} LAB satır "
                        f"{best['row_index'] + 1} ({detail['alignment']}, "
                        f"fark {detail['distance']:.2f} m{color_text})"
                    ]
                    status = "korelasyonla_onerildi"
                    confidence = max(0.35, min(0.95, score / 6.5))
                else:
                    parsed = sinif_kodu_coz("")
                    class_value = ""
                    sources = ["Bu aralık için LAB dayanağı bulunamadı."]
                    status = "bilinmiyor"
                    confidence = 0.0

            behavior = zemin_davranis_sinifi(
                parsed,
                (spt_record or {}).get("n30"),
                refused=bool((spt_record or {}).get("refused")),
            )
            if spt_record:
                n30_text = (
                    "refü"
                    if spt_record.get("refused")
                    else f"N30={spt_record.get('n30'):g}"
                    if spt_record.get("n30") is not None
                    else "N30 boş"
                )
                sources.append(f"SPT {spt_record['depth']:.2f} m: {n30_text}")
            if target_color:
                sources.append(
                    f"Fotoğraf rengi: {target_color.get('hex', '') or target_color.get('rgb', '')}"
                )

            cells.append(
                {
                    "top": round(top, 3),
                    "bottom": round(bottom, 3),
                    "sinif": class_value,
                    "malzeme_anahtari": parsed.get("malzeme_anahtari", ""),
                    "ana_birim": parsed.get("ana_birim", ""),
                    "birim_adi": parsed.get("birim_adi", ""),
                    "plastisite": parsed.get("plastisite", ""),
                    "derecelenme": parsed.get("derecelenme", ""),
                    "davranis": behavior,
                    "kanit_durumu": status,
                    "guven": round(confidence, 3),
                    "kaynaklar": sources,
                    "n30": (spt_record or {}).get("n30"),
                    "renk": (target_color or {}).get("hex", ""),
                }
            )
            top = bottom

        layers = hucreleri_katmanlara_birlestir(cells)
        result_wells.append(
            {
                "sondaj_index": well_index,
                "sondaj_no": well.get("no") or f"SK-{well_index + 1}",
                "kot": well.get("k", ""),
                "derinlik": total_depth,
                "katmanlar": layers,
                "hucreler": cells,
            }
        )

    return {
        "sondajlar": result_wells,
        "lab_kayitlari": copy.deepcopy(lab_result["records"]),
        "uyarilar": warnings,
        "adim": step,
        "uygulandi": False,
    }


def onerileri_litoloji_satirlarina_cevir(katmanlar):
    rows = []
    for layer in sorted(katmanlar or [], key=lambda item: float(item.get("top", 0))):
        top = _sayi(layer.get("top"))
        bottom = _sayi(layer.get("bottom"))
        description = _metin(layer.get("tanim"))
        if top is None or bottom is None or bottom <= top or not description:
            continue
        rows.append(
            [
                f"{top:.2f}",
                f"{bottom:.2f}",
                description,
            ]
        )
    return rows


__all__ = [
    "KIVAM_SIRASI",
    "PLASTISITE_SIRASI",
    "RENK_SECENEKLERI",
    "SIKILIK_SIRASI",
    "coklu_sondaj_onerileri_olustur",
    "hucreleri_katmanlara_birlestir",
    "laboratuvar_litoloji_kayitlari",
    "litoloji_tanimi_olustur",
    "manuel_atama_cakisiyor",
    "manuel_katmanlari_dogrula",
    "manuel_lab_katmanlari_olustur",
    "n30_kivam_sinifi",
    "n30_sikilik_sinifi",
    "onerileri_litoloji_satirlarina_cevir",
    "sinif_kodu_coz",
    "siniflar_ardisik_mi",
    "sondaj_anahtari",
    "sondaj_spt_kayitlari",
    "spt_satirini_coz",
    "zemin_davranis_sinifi",
]
