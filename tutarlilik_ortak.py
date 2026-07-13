# Dosya: RaporPro/tutarlilik_ortak.py
import re
import unicodedata


SEVIYE_SIRASI = {"error": 0, "warning": 1, "info": 2, "ok": 3}


def bos_mu(value):
    return value is None or str(value).strip() in {"", "-", "None", "none", "null"}


def sayi_veya_none(value):
    if bos_mu(value):
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def kimlik_anahtari(value):
    text = str(value or "").strip().casefold().translate(str.maketrans({
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    }))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text)


def slug(value):
    return kimlik_anahtari(value) or "kayit"


def yeni_kontrol_raporu():
    return {
        "checks": [],
        "findings": [],
        "errors": [],
        "warnings": [],
        "info": [],
        "blocking": [],
        "counts": {"error": 0, "warning": 0, "info": 0, "ok": 0},
        "score": 0,
        "state": "EKSİKLER VAR",
        "stats": {},
    }


def bulgu_ekle(
    report,
    finding_id,
    level,
    category,
    label,
    detail,
    target="ozet",
    suggestion="",
    *,
    entity="",
    field="",
    sheet="",
    row=None,
    blocking=None,
):
    level = level if level in SEVIYE_SIRASI else "info"
    finding = {
        "id": str(finding_id),
        "level": level,
        "category": category,
        "label": label,
        "detail": str(detail),
        "target": target,
        "suggestion": suggestion,
        "entity": str(entity or ""),
        "field": str(field or ""),
        "sheet": str(sheet or ""),
        "row": row,
        "blocking": bool(level == "error" if blocking is None else blocking),
    }
    duplicate = next(
        (
            item
            for item in report.setdefault("findings", [])
            if item.get("id") == finding["id"] and item.get("detail") == finding["detail"]
        ),
        None,
    )
    if duplicate is None:
        report["findings"].append(finding)
    return finding


def kontrol_ekle(
    report,
    check_id,
    category,
    label,
    ok,
    detail,
    target="ozet",
    suggestion="",
    *,
    failure_level="warning",
    weight=1,
    dashboard=True,
    entity="",
    field="",
    sheet="",
):
    check = {
        "id": str(check_id),
        "category": category,
        "label": label,
        "ok": bool(ok),
        "detail": str(detail),
        "target": target,
        "suggestion": suggestion,
        "failure_level": failure_level,
        "weight": max(0.0, float(weight)),
        "dashboard": bool(dashboard),
        "entity": str(entity or ""),
        "field": str(field or ""),
        "sheet": str(sheet or ""),
    }
    current = next((item for item in report.setdefault("checks", []) if item.get("id") == check["id"]), None)
    if current is None:
        report["checks"].append(check)
    else:
        current.update(check)
    if not ok:
        bulgu_ekle(
            report,
            check_id,
            failure_level,
            category,
            label,
            detail,
            target,
            suggestion,
            entity=entity,
            field=field,
            sheet=sheet,
        )
    return check


def kontrol_raporunu_tamamla(report):
    findings = sorted(
        report.get("findings", []),
        key=lambda item: (
            SEVIYE_SIRASI.get(item.get("level"), 9),
            str(item.get("category", "")),
            str(item.get("entity", "")),
            str(item.get("label", "")),
        ),
    )
    report["findings"] = findings
    report["errors"] = [item["detail"] for item in findings if item.get("level") == "error"]
    report["warnings"] = [item["detail"] for item in findings if item.get("level") == "warning"]
    report["info"] = [item["detail"] for item in findings if item.get("level") == "info"]
    report["blocking"] = [item for item in findings if item.get("blocking")]
    report["counts"] = {
        level: sum(1 for item in findings if item.get("level") == level)
        for level in ("error", "warning", "info", "ok")
    }

    weighted = [item for item in report.get("checks", []) if item.get("weight", 0) > 0]
    total_weight = sum(item["weight"] for item in weighted)
    ok_weight = sum(item["weight"] for item in weighted if item.get("ok"))
    report["score"] = int(round(100 * ok_weight / total_weight)) if total_weight else 0
    if report["errors"]:
        report["state"] = "EKSİKLER VAR"
    elif report["warnings"]:
        report["state"] = "KONTROL GEREKLİ"
    elif report["score"] >= 85:
        report["state"] = "RAPORA HAZIR"
    else:
        report["state"] = "KONTROL GEREKLİ"
    return report


def koordinat_durumu(lat_raw, lon_raw):
    if bos_mu(lat_raw) and bos_mu(lon_raw):
        return False, "Koordinat girilmemiş."
    lat = sayi_veya_none(lat_raw)
    lon = sayi_veya_none(lon_raw)
    if lat is None or lon is None:
        return False, "Koordinat çifti sayısal değil veya tek değer eksik."
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False, "Enlem veya boylam geçerli coğrafi aralığın dışında."
    return True, "Koordinat geçerli."


def litoloji_araliklari(litoloji):
    intervals = []
    for row in litoloji or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        top = sayi_veya_none(row[0])
        bottom = sayi_veya_none(row[1])
        if top is not None and bottom is not None and bottom > top:
            intervals.append((top, bottom))
    return intervals


def derinlik_aralikta_mi(depth, intervals):
    return any(top - 0.05 <= depth <= bottom + 0.05 for top, bottom in intervals)


def refu_mu(value):
    text = str(value or "").strip().casefold()
    return text in {"r", "ref", "refü", "refu"} or "refü" in text or "refu" in text
