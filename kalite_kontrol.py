import datetime
import os
import re
import shutil

from karot_motoru import derinlik_baslangic
from sondaj_derinlik import sondaj_derinligi_kontrol_sonucu

from docx import Document
from ekler import uygun_ek_sablonu
from jeofizik_sheet_motoru import jeofizik_sheet_rows_to_ss_list, jeofizik_sheet_var_mi


KNOWN_TAGS = {
    "[ADA]", "[ALAN_BOYLAM]", "[ALAN_ENLEM]", "[BINA_BILGILERI]",
    "[EGIM_YONU]", "[EGIM_YUZDE]", "[IL]", "[ILCE]", "[IMAR_ALANI]",
    "[IMAR_DURUMU]", "[JEO_KOOR]", "[JEO_PARAMETRE]", "[JEO_SONUC]",
    "[JEO_TARIH]", "[KATEGORI]", "[KATEGORI_ZEMIN]", "[KAYA_TABLO]",
    "[KOT_MAX]", "[KOT_MIN]", "[KOT_ORT]", "[LAB_FIZIK]",
    "[LAB_MEKANIK]", "[LITOLOJI_DAGILIM]", "[MAHALLE]", "[MASW]",
    "[MEVKI]", "[MT_TABLO]", "[PAFTA]", "[PARSEL]", "[PGA]", "[PMT]",
    "[PROJE_ADI]", "[RESIM:PGA]", "[RESIM:SONDAJ]", "[RESIM:TKGM]",
    "[RESIM:MJH]", "[RESIM_JEOFIZIK]", "[RESIM_MJH]", "[RESIM_SONDAJ]", "[RESIM_YERBULDURUR]",
    "[SAYI_MT]", "[SAYI_SS]", "[SONDAJ_BILGISI]", "[SPT]", "[Sondaj]",
    "[VP]", "[YASS_ONERI]", "[YASS_TABLO]", "[YEREL_ZEMIN]",
    "[ZEMIN_OZET]", "RESIM:MJH", "RESIM:PGA", "RESIM:TKGM",
    "RESIM:Yerbuldurur",
}

PREFIXED_TAG_RE = re.compile(
    r"^\[S[1-5]_(PROJE_ADI|IL|ILCE|MAHALLE|MEVKI|PAFTA|ADA|PARSEL)\]$"
)

IMAGE_TAGS = {
    "[RESIM_YERBULDURUR]": "img_yer",
    "RESIM:Yerbuldurur": "img_yer",
    "[RESIM:PGA]": "img_pga",
    "RESIM:PGA": "img_pga",
    "[RESIM:TKGM]": "img_tkgm",
    "RESIM:TKGM": "img_tkgm",
    "[RESIM_JEOFIZIK]": "word_img_jeofizik",
    "RESIM:MJH": "img_mjh",
    "[RESIM:MJH]": "img_mjh",
    "[RESIM_MJH]": "img_mjh",
    "[RESIM_SONDAJ]": "word_img_sondaj",
    "[RESIM:SONDAJ]": "word_img_sondaj",
}

TAG_DESCRIPTIONS = {
    "[PROJE_ADI]": "Proje sahibi/adi bilgisini yazar.",
    "[IL]": "Il bilgisini yazar.",
    "[ILCE]": "Ilce bilgisini yazar.",
    "[MAHALLE]": "Mahalle bilgisini yazar.",
    "[MEVKI]": "Mevkii bilgisini yazar.",
    "[PAFTA]": "Pafta bilgisini yazar.",
    "[ADA]": "Ada bilgisini yazar.",
    "[PARSEL]": "Parsel bilgisini yazar.",
    "[BINA_BILGILERI]": "Bina bilgileri ve temel yükleri tablosunu ekler.",
    "[KATEGORI]": "Arazi kategori bilgisini yazar.",
    "[KATEGORI_ZEMIN]": "Kategori zemin/aciklama bilgisini yazar.",
    "[PGA]": "PGA degerini yazar.",
    "[JEO_TARIH]": "Jeofizik calisma tarihini yazar.",
    "[SAYI_SS]": "Sismik serim sayisini yazar.",
    "[SAYI_MT]": "Mikrotremor olcu sayisini yazar.",
    "[YEREL_ZEMIN]": "Yerel zemin sinifini yazar.",
    "[KOT_ORT]": "Ortalama kot bilgisini yazar.",
    "[KOT_MAX]": "Maksimum kot bilgisini yazar.",
    "[KOT_MIN]": "Minimum kot bilgisini yazar.",
    "[EGIM_YUZDE]": "Egim yuzdesini yazar.",
    "[EGIM_YONU]": "Egim yonunu yazar.",
    "[IMAR_ALANI]": "Imar alani bilgisini yazar.",
    "[IMAR_DURUMU]": "Imar durumu/aciklamasini yazar.",
    "[ALAN_ENLEM]": "Calisma alani merkez enlemini yazar.",
    "[ALAN_BOYLAM]": "Calisma alani merkez boylamini yazar.",
    "[SONDAJ_BILGISI]": "Sondaj sayısı ve derinlik özet cümlesini yazar.",
    "[Sondaj]": "Sondaj konum, tarih, kot, derinlik ve litoloji tablosunu ekler.",
    "[YASS_TABLO]": "Yeraltisuyu olcumleri tablosunu ekler.",
    "[YASS_ONERI]": "Yeraltısuyu durumuna göre öneri paragrafını yazar.",
    "[LAB_FIZIK]": "Laboratuvar fiziksel deney ozet tablosunu ekler.",
    "[LAB_MEKANIK]": "Laboratuvar mekanik deney ozet tablosunu ekler.",
    "[ZEMIN_OZET]": "Laboratuvar ve SPT verilerine gore zemin ozet metnini yazar.",
    "[LITOLOJI_DAGILIM]": "Litoloji birimlerinin sondajlara gore derinlik dagilimini yazar.",
    "[SPT]": "SPT deney tablosunu ekler.",
    "[PMT]": "Presiyometre deney tablosunu ekler.",
    "[KAYA_TABLO]": "Kaya/karot deney tablosunu ekler.",
    "[JEO_PARAMETRE]": "Jeofizik parametre tablosunu ekler.",
    "[MASW]": "MASW/Vs tablosunu ekler.",
    "[VP]": "Vp tablosunu ekler.",
    "[JEO_KOOR]": "Jeofizik ve mikrotremor koordinat tablosunu ekler.",
    "[MT_TABLO]": "Mikrotremor olcu tablosunu ekler.",
    "[JEO_SONUC]": "Vs30 ve To degerlerinden jeofizik sonuc cumlesi uretir.",
    "[RESIM_YERBULDURUR]": "Yerbuldurur haritası görselini ekler.",
    "RESIM:Yerbuldurur": "Yerbuldurur haritası görselini ekler.",
    "RESIM:TKGM": "TKGM haritası görselini ekler.",
    "[RESIM:TKGM]": "TKGM haritası görselini ekler.",
    "[RESIM:PGA]": "PGA haritası görselini ekler.",
    "RESIM:PGA": "PGA haritası görselini ekler.",
    "[RESIM_JEOFIZIK]": "Jeofizik/serim haritası görselini ekler.",
    "RESIM:MJH": "Mühendislik jeolojisi haritası görselini ekler.",
    "[RESIM:MJH]": "Mühendislik jeolojisi haritası görselini ekler.",
    "[RESIM_MJH]": "Mühendislik jeolojisi haritası görselini ekler.",
    "[RESIM_SONDAJ]": "Sondaj vaziyet planı görselini ekler.",
    "[RESIM:SONDAJ]": "Sondaj vaziyet planı görselini ekler.",
}

RECOMMENDED_TAGS = [
    "[PROJE_ADI]", "[IL]", "[ILCE]", "[MAHALLE]", "[SONDAJ_BILGISI]",
    "[Sondaj]", "[SPT]", "[YASS_TABLO]", "[LAB_FIZIK]", "[JEO_PARAMETRE]",
    "[JEO_KOOR]", "[RESIM_SONDAJ]", "[RESIM_JEOFIZIK]",
]


def is_blank(value):
    return value is None or str(value).strip() in {"", "-", "None", "null"}


def number_or_none(value):
    if is_blank(value):
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None

def image_path_for_tag(app_instance, attr_name):
    return getattr(app_instance, attr_name, None)


def backup_project_file(project_path, keep=10):
    if not project_path or not os.path.exists(project_path):
        return None, None

    try:
        project_dir = os.path.dirname(os.path.abspath(project_path))
        backup_dir = os.path.join(project_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        stem, ext = os.path.splitext(os.path.basename(project_path))
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{stem}_{timestamp}{ext or '.json'}"
        backup_path = os.path.join(backup_dir, backup_name)

        counter = 2
        while os.path.exists(backup_path):
            backup_name = f"{stem}_{timestamp}_{counter}{ext or '.json'}"
            backup_path = os.path.join(backup_dir, backup_name)
            counter += 1

        shutil.copy2(project_path, backup_path)

        backups = [
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if name.startswith(f"{stem}_") and name.endswith(ext or ".json")
        ]
        backups.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        for old_path in backups[keep:]:
            try:
                os.remove(old_path)
            except OSError:
                pass

        return backup_path, None
    except Exception as exc:
        return None, str(exc)


def validate_project_data(veri):
    report = {"errors": [], "warnings": [], "info": []}

    for section in ["kunye", "bina", "arazi", "sondaj", "jeofizik"]:
        if section not in veri:
            report["errors"].append(f"Eksik veri bölümü: {section}")

    kunye = veri.get("kunye", {})
    for key, label in [("sahibi", "Proje adi"), ("il", "Il"), ("ilce", "Ilce")]:
        if is_blank(kunye.get(key)):
            report["warnings"].append(f"{label} bos gorunuyor.")

    sondajlar = veri.get("sondaj", [])
    if not sondajlar:
        report["errors"].append("En az bir sondaj kaydi gerekli.")
    else:
        seen = set()
        for idx, sondaj in enumerate(sondajlar, start=1):
            no = str(sondaj.get("no") or f"SK-{idx}").strip()
            if no in seen:
                report["warnings"].append(f"Tekrarlanan sondaj no: {no}")
            seen.add(no)

            der = number_or_none(sondaj.get("der"))
            if der is None or der <= 0:
                report["errors"].append(f"{no}: sondaj derinligi gecersiz.")
                der = None

            _validate_coordinate_pair(report, f"{no} koordinati", sondaj.get("y"), sondaj.get("x"))

            for yass_key in ["yass_d1", "yass_d2"]:
                yass = number_or_none(sondaj.get(yass_key))
                if yass is not None and der is not None and yass > der:
                    report["warnings"].append(f"{no}: yeraltisuyu derinligi sondaj derinligini asiyor.")

            if is_blank(sondaj.get("k")):
                report["warnings"].append(f"{no}: kuyu kotu girilmemis.")
            _validate_lithology(report, no, der, sondaj.get("litoloji", []))
            _validate_depth_rows(report, no, der, "SPT", sondaj.get("spt", []), 0, sondaj.get("litoloji", []))
            _validate_depth_rows(report, no, der, "PMT", sondaj.get("pmt", []), 0, sondaj.get("litoloji", []))
            _validate_depth_rows(report, no, der, "Kaya", sondaj.get("kaya", []), 0, sondaj.get("litoloji", []))

    _validate_geophysics(report, veri.get("jeofizik", {}))

    try:
        depth_check = sondaj_derinligi_kontrol_sonucu(veri)
        recommended = number_or_none(depth_check.get("onerilen_sondaj_derinligi"))
        if recommended and recommended > 0:
            method = "gerilme %10 hesabi" if depth_check.get("hesap_tipi") == "gerilme_10" else "yonetmelik on kontrolu"
            report["info"].append(f"Sondaj derinligi {method}: onerilen minimum sondaj derinligi {recommended:.2f} m.")
            for item in depth_check.get("eksik_sondajlar", [])[:10]:
                report["warnings"].append(
                    f"{item['sondaj']}: sondaj derinligi onerilen {recommended:.2f} m altinda "
                    f"({item['derinlik']:.2f} m, eksik yaklasik {item['eksik']:.2f} m)."
                )
            for note in depth_check.get("uyarilar", [])[:5]:
                report["warnings"].append(f"Sondaj derinligi hesabi: {note}")
    except Exception as exc:
        report["warnings"].append(f"Sondaj derinligi hesabi calistirilamadi: {exc}")

    if not report["errors"] and not report["warnings"]:
        report["info"].append("Veri dogrulamasinda kritik sorun bulunmadi.")
    return report


def _validate_coordinate_pair(report, label, lat_raw, lon_raw):
    if is_blank(lat_raw) and is_blank(lon_raw):
        report["warnings"].append(f"{label}: koordinat girilmemis.")
        return
    lat = number_or_none(lat_raw)
    lon = number_or_none(lon_raw)
    if lat is None or lon is None:
        report["warnings"].append(f"{label}: koordinat sayisal degil.")
    elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
        report["warnings"].append(f"{label}: enlem/boylam araligi disinda.")


def _validate_lithology(report, sondaj_no, total_depth, litoloji):
    if not litoloji:
        report["warnings"].append(f"{sondaj_no}: litoloji girilmemis.")
        return

    rows = []
    for row_idx, row in enumerate(litoloji, start=1):
        if len(row) < 3:
            report["errors"].append(f"{sondaj_no}: {row_idx}. litoloji satiri eksik.")
            continue
        top = number_or_none(row[0])
        bottom = number_or_none(row[1])
        desc = row[2]
        if top is None or bottom is None:
            report["errors"].append(f"{sondaj_no}: {row_idx}. litoloji derinligi sayisal degil.")
            continue
        if bottom <= top:
            report["errors"].append(f"{sondaj_no}: {row_idx}. litoloji bitisi baslangictan kucuk/esit.")
            continue
        if is_blank(desc):
            report["warnings"].append(f"{sondaj_no}: {row_idx}. litoloji tanimi bos.")
        if total_depth is not None and bottom > total_depth + 0.05:
            report["errors"].append(f"{sondaj_no}: litoloji sondaj derinligini asiyor.")
        rows.append((top, bottom, row_idx))

    if not rows:
        return

    rows.sort()
    if rows[0][0] > 0.05:
        report["warnings"].append(f"{sondaj_no}: litoloji 0.00 m'den baslamiyor.")

    prev_bottom = rows[0][1]
    for top, bottom, row_idx in rows[1:]:
        if top < prev_bottom - 0.05:
            report["errors"].append(f"{sondaj_no}: {row_idx}. litoloji onceki katmanla cakisir.")
        elif top > prev_bottom + 0.05:
            report["warnings"].append(f"{sondaj_no}: litoloji araliginda bosluk var ({prev_bottom:g}-{top:g} m).")
        prev_bottom = max(prev_bottom, bottom)

    if total_depth is not None and prev_bottom < total_depth - 0.05:
        report["warnings"].append(f"{sondaj_no}: litoloji sondaj sonuna kadar inmiyor.")


def _lithology_intervals(litoloji):
    intervals = []
    for row in litoloji or []:
        if len(row) < 2:
            continue
        top = number_or_none(row[0])
        bottom = number_or_none(row[1])
        if top is not None and bottom is not None and bottom > top:
            intervals.append((top, bottom))
    return intervals


def _depth_inside_intervals(depth, intervals):
    return any(top - 0.05 <= depth <= bottom + 0.05 for top, bottom in intervals)


def _validate_depth_rows(report, sondaj_no, total_depth, label, rows, depth_index, litoloji=None):
    intervals = _lithology_intervals(litoloji)
    for row_idx, row in enumerate(rows or [], start=1):
        if len(row) <= depth_index:
            report["warnings"].append(f"{sondaj_no}: {label} {row_idx}. satirinda derinlik yok.")
            continue
        if label == "Kaya":
            depth = derinlik_baslangic(row[depth_index])
            depth = depth if depth > 0 else None
        else:
            depth = number_or_none(row[depth_index])
        if depth is None:
            report["warnings"].append(f"{sondaj_no}: {label} {row_idx}. derinligi sayisal degil.")
        elif total_depth is not None and depth > total_depth + 0.05:
            report["warnings"].append(f"{sondaj_no}: {label} {row_idx}. derinligi sondaj derinligini asiyor.")
        elif intervals and not _depth_inside_intervals(depth, intervals):
            report["warnings"].append(f"{sondaj_no}: {label} {row_idx}. derinligi litoloji araligi disinda.")

        if label == "SPT" and len(row) >= 5:
            n30 = str(row[4]).strip().upper()
            if n30 not in {"", "R"} and number_or_none(n30) is None:
                report["warnings"].append(f"{sondaj_no}: SPT {row_idx}. N30 degeri sayisal degil.")


def _validate_geophysics(report, jeofizik):
    ss_list = jeofizik.get("ss_list", [])
    mt_list = jeofizik.get("mt_list", [])

    if not ss_list:
        report["warnings"].append("Jeofizik SS listesi bos.")

    for idx, ss in enumerate(ss_list, start=1):
        ad = ss.get("ad") or f"SS-{idx}"
        coords = list(ss.get("coords", []))
        if coords:
            while len(coords) < 6:
                coords.append("")
            for i in range(0, 6, 2):
                _validate_coordinate_pair(report, f"{ad} koordinat {i // 2 + 1}", coords[i], coords[i + 1])

        for layer_idx, layer in enumerate(ss.get("layers", []), start=1):
            for key in ["vp", "vs"]:
                val = number_or_none(layer.get(key))
                if val is None or val <= 0:
                    report["warnings"].append(f"{ad}: {layer_idx}. tabaka {key} degeri gecersiz.")
            h = number_or_none(layer.get("h"))
            if layer_idx == 1 and h is None:
                report["warnings"].append(f"{ad}: tabaka kalinligi girilmemis.")

    for idx, mt in enumerate(mt_list, start=1):
        ad = mt.get("no") or f"MT-{idx}"
        _validate_coordinate_pair(report, f"{ad} koordinati", mt.get("y"), mt.get("x"))
        for key in ["freq", "to", "ta", "tb", "hv", "sure"]:
            if not is_blank(mt.get(key)) and number_or_none(mt.get(key)) is None:
                report["warnings"].append(f"{ad}: {key} degeri sayisal degil.")


def read_word_tags(word_path):
    doc = Document(word_path)
    texts = []
    for paragraph in _iter_doc_paragraphs(doc):
        texts.append(paragraph.text or "")
    joined = "\n".join(texts)
    return sorted(set(re.findall(r"\[[^\]]+\]|RESIM:[A-Za-z0-9_:-]+", joined)))


def _iter_doc_paragraphs(doc):
    for paragraph in doc.paragraphs:
        yield paragraph
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph
    for section in doc.sections:
        containers = [
            section.header, section.first_page_header, section.even_page_header,
            section.footer, section.first_page_footer, section.even_page_footer,
        ]
        for container in containers:
            for paragraph in container.paragraphs:
                yield paragraph
            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            yield paragraph


def is_known_tag(tag):
    return tag in KNOWN_TAGS or bool(PREFIXED_TAG_RE.match(tag))


def get_supported_tags():
    tags = set(KNOWN_TAGS) | set(TAG_DESCRIPTIONS)
    items = []
    for tag in sorted(tags, key=lambda value: value.upper()):
        if PREFIXED_TAG_RE.match(tag):
            category = "Sablon kopya"
        elif "RESIM" in tag:
            category = "Gorsel"
        elif tag in {"[Sondaj]", "[SPT]", "[PMT]", "[KAYA_TABLO]", "[LAB_FIZIK]", "[LAB_MEKANIK]", "[JEO_PARAMETRE]", "[MASW]", "[VP]", "[JEO_KOOR]", "[MT_TABLO]", "[YASS_TABLO]", "[BINA_BILGILERI]"}:
            category = "Tablo"
        else:
            category = "Metin"
        items.append({
            "tag": tag,
            "category": category,
            "description": TAG_DESCRIPTIONS.get(tag, "Desteklenen etiket."),
        })
    items.append({
        "tag": "[S1_PROJE_ADI] ... [S5_PARSEL]",
        "category": "Şablon kopya",
        "description": "Aynı proje künye bilgisini farklı şablon bölümlerinde kullanmak için S1_ ile S5_ arası ön ekler desteklenir.",
    })
    return items


def analyze_word_template(word_path):
    result = {
        "path": word_path,
        "tags": [],
        "known": [],
        "unknown": [],
        "missing_recommended": [],
        "error": None,
    }
    if is_blank(word_path):
        result["error"] = "Word şablonu seçilmemiş."
        return result
    if not os.path.exists(word_path):
        result["error"] = f"Word şablonu bulunamadı: {word_path}"
        return result
    try:
        tags = read_word_tags(word_path)
    except Exception as exc:
        result["error"] = f"Word şablonu okunamadı: {exc}"
        return result

    result["tags"] = tags
    result["known"] = [tag for tag in tags if is_known_tag(tag)]
    result["unknown"] = [tag for tag in tags if not is_known_tag(tag)]
    result["missing_recommended"] = [tag for tag in RECOMMENDED_TAGS if tag not in tags]
    return result


def format_template_analysis(analysis):
    lines = ["WORD ETİKET ANALİZİ", "=" * 19, ""]
    if analysis.get("path"):
        lines.append(f"Şablon: {analysis['path']}")
    if analysis.get("error"):
        lines.append(f"Hata: {analysis['error']}")
        return "\n".join(lines)

    lines.append(f"Toplam etiket: {len(analysis['tags'])}")
    lines.append(f"Bilinen etiket: {len(analysis['known'])}")
    lines.append(f"Bilinmeyen etiket: {len(analysis['unknown'])}")
    lines.append("")

    lines.append("BİLİNMEYEN ETİKETLER")
    if analysis["unknown"]:
        lines.extend(f"- {tag}" for tag in analysis["unknown"])
    else:
        lines.append("- Yok")
    lines.append("")

    lines.append("ŞABLONDA BULUNAN ETİKETLER")
    if analysis["tags"]:
        for tag in analysis["tags"]:
            marker = "OK" if is_known_tag(tag) else "UYARI"
            desc = TAG_DESCRIPTIONS.get(tag, "Kod karşılığı bilinmiyor.")
            lines.append(f"- {marker}: {tag} - {desc}")
    else:
        lines.append("- Etiket bulunamadı.")
    lines.append("")

    lines.append("ÖNERİLEN AMA EKSİK OLAN ETİKETLER")
    if analysis["missing_recommended"]:
        for tag in analysis["missing_recommended"]:
            lines.append(f"- {tag}: {TAG_DESCRIPTIONS.get(tag, '')}")
    else:
        lines.append("- Yok")
    return "\n".join(lines)


def build_preflight_report(app_instance):
    report = validate_project_data(app_instance.veri)

    try:
        from kesit_kalite import build_section_quality_report
        sondajlar = app_instance.veri.get("sondaj", [])
        kesit_options = app_instance.veri.get("kesit_ayarlari", {}) or {}
        selected = kesit_options.get("selected_sondajlar") or []
        if selected:
            selected_set = set(selected)
            kesit_sondajlar = [s for s in sondajlar if s.get("no") in selected_set]
        else:
            kesit_sondajlar = sondajlar
        if len(kesit_sondajlar) >= 2:
            section_report = build_section_quality_report(kesit_sondajlar, kesit_options)
            if section_report.get("errors"):
                for item in section_report["errors"][:8]:
                    report["errors"].append(f"Kesit: {item}")
            if section_report.get("warnings"):
                for item in section_report["warnings"][:10]:
                    report["warnings"].append(f"Kesit: {item}")
                if len(section_report["warnings"]) > 10:
                    report["warnings"].append(f"Kesit: {len(section_report['warnings']) - 10} ek uyarı daha var.")
            stats = section_report.get("stats", {})
            report["info"].append(
                f"Kesit kontrolü: {stats.get('well_count', 0)} sondaj, "
                f"{len(section_report.get('errors', []))} hata, {len(section_report.get('warnings', []))} uyarı."
            )
    except Exception as exc:
        report["warnings"].append(f"Kesit kalite kontrol çalıştırılamadı: {exc}")

    word_path = getattr(app_instance, "word_path", None)
    if is_blank(word_path):
        report["errors"].append("Word şablonu seçilmemiş.")
        return report
    if not os.path.exists(word_path):
        report["errors"].append(f"Word şablonu bulunamadı: {word_path}")
        return report

    try:
        tags = read_word_tags(word_path)
    except Exception as exc:
        report["errors"].append(f"Word şablonu okunamadı: {exc}")
        return report

    report["info"].append(f"Word şablonunda {len(tags)} etiket bulundu.")

    unknown_tags = [tag for tag in tags if not is_known_tag(tag)]
    for tag in unknown_tags:
        report["warnings"].append(f"Word şablonunda kod karşılığı bilinmeyen etiket var: {tag}")

    for tag, attr_name in IMAGE_TAGS.items():
        if tag in tags:
            path = image_path_for_tag(app_instance, attr_name)
            if is_blank(path):
                report["warnings"].append(f"{tag} için görsel seçilmemiş.")
            elif not os.path.exists(path):
                report["warnings"].append(f"{tag} görsel dosyası bulunamadı: {path}")

    if any(tag in tags for tag in ["[LAB_FIZIK]", "[LAB_MEKANIK]", "[ZEMIN_OZET]"]):
        path = getattr(app_instance, "lab_excel_path", None)
        lab_rows = app_instance.veri.get("lab_sheet", {}).get("rows", []) if isinstance(getattr(app_instance, "veri", None), dict) else []
        lab_sheet_ready = any(any(str(cell).strip() for cell in row) for row in lab_rows or [])
        if lab_sheet_ready:
            pass
        elif is_blank(path):
            report["warnings"].append("Laboratuvar tabloları için Lab Excel seçilmemiş.")
        elif not os.path.exists(path):
            report["warnings"].append(f"Lab Excel dosyası bulunamadı: {path}")

    if any(tag in tags for tag in ["[JEO_PARAMETRE]", "[MASW]", "[VP]"]):
        path = getattr(app_instance, "jeo_excel_path", None)
        jeo_rows = app_instance.veri.get("jeofizik_sheet", {}).get("rows", []) if isinstance(getattr(app_instance, "veri", None), dict) else []
        jeo_sheet_ready = jeofizik_sheet_var_mi(getattr(app_instance, "veri", {})) and bool(jeofizik_sheet_rows_to_ss_list(jeo_rows))
        has_manual_layers = any(
            ss.get("layers") for ss in app_instance.veri.get("jeofizik", {}).get("ss_list", [])
        )
        if is_blank(path) and not has_manual_layers and not jeo_sheet_ready:
            report["warnings"].append("Jeofizik tabloları için Excel, Sheet veya manuel tabaka verisi yok.")
        elif not is_blank(path) and not os.path.exists(path) and not jeo_sheet_ready:
            report["warnings"].append(f"Jeofizik Excel dosyası bulunamadı: {path}")

    try:
        ek_label, ek_path = uygun_ek_sablonu(app_instance.veri)
        if is_blank(ek_path) or not os.path.exists(ek_path):
            report["warnings"].append(f"{ek_label} ek dosyası bulunamadı: {ek_path}")
        else:
            report["info"].append(f"Ek seçimi: {ek_label} ({os.path.basename(ek_path)})")
    except Exception as exc:
        report["warnings"].append(f"Ek seçimi kontrol edilemedi: {exc}")

    return report


def format_preflight_report(report):
    lines = ["RAPOR ÖN KONTROL", "=" * 18, ""]
    sections = [
        ("HATALAR", report.get("errors", [])),
        ("UYARILAR", report.get("warnings", [])),
        ("BİLGİ", report.get("info", [])),
    ]
    for title, items in sections:
        lines.append(title)
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- Yok")
        lines.append("")
    return "\n".join(lines).strip()
