# Dosya: RaporPro/ui_spt_okuma_yardimci.py
import os

from spt_gorsel import dogal_siralama_anahtari, dosya_parmak_izi
from spt_okuma_motoru import normalize_sondaj_no
from yardimcilar import safe_float


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def source_unique_key(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        if os.path.exists(raw):
            return os.path.normcase(os.path.realpath(os.path.abspath(raw)))
    except Exception:
        pass
    return os.path.normcase(raw)


def source_content_key(value):
    raw = str(value or "").strip()
    if not raw or not os.path.isfile(raw):
        return ""
    return dosya_parmak_izi(raw)


def collect_image_paths(sources, recursive=True, image_exts=IMAGE_EXTS):
    found_paths = []
    allowed_exts = tuple(str(ext).lower() for ext in (image_exts or IMAGE_EXTS))
    for source in sources or []:
        if not source:
            continue
        source = os.path.abspath(str(source))
        if os.path.isdir(source):
            if recursive:
                for root_dir, _, files in os.walk(source):
                    for name in files:
                        path = os.path.join(root_dir, name)
                        if os.path.splitext(path)[1].lower() in allowed_exts:
                            found_paths.append(path)
            else:
                try:
                    names = os.listdir(source)
                except Exception:
                    names = []
                for name in names:
                    path = os.path.join(source, name)
                    if os.path.isfile(path) and os.path.splitext(path)[1].lower() in allowed_exts:
                        found_paths.append(path)
        elif os.path.isfile(source) and os.path.splitext(source)[1].lower() in allowed_exts:
            found_paths.append(source)
    return sorted(found_paths, key=dogal_siralama_anahtari)


def n30_numeric(kayit):
    if str(kayit.n30).strip().upper() == "R":
        return None
    value = safe_float(kayit.n30)
    return value if value > 0 else None


def is_refu(kayit):
    return str(kayit.n30).strip().upper() == "R" or any(
        "50/" in str(v) or str(v).strip().upper() == "R"
        for v in (kayit.v15, kayit.v30, kayit.v45)
    )


def context_issues(records):
    issues = {}
    by_no = {}
    for order, record in enumerate(records or []):
        if record.get("record_type") == "queue" or not record.get("include", True):
            continue
        kayit = record["kayit"]
        if not kayit.sondaj_no:
            continue
        by_no.setdefault(kayit.sondaj_no, []).append((order, record))

    for _no, items in by_no.items():
        sorted_items = sorted(items, key=lambda item: safe_float(item[1]["kayit"].derinlik))
        prev_n30 = None
        refu_seen = False
        for _order, record in sorted_items:
            kayit = record["kayit"]
            n30_val = n30_numeric(kayit)
            if is_refu(kayit):
                refu_seen = True
            elif refu_seen and n30_val is not None and n30_val < 50:
                issues.setdefault(id(record), []).append("mühendislik kontrolü: refü sonrası düşük N30")
            if n30_val is not None:
                if n30_val > 80:
                    issues.setdefault(id(record), []).append("mühendislik kontrolü: N30 çok yüksek")
                elif n30_val < 2:
                    issues.setdefault(id(record), []).append("mühendislik kontrolü: N30 çok düşük")
                if prev_n30 is not None and abs(n30_val - prev_n30) >= 25:
                    issues.setdefault(id(record), []).append("mühendislik kontrolü: N30 ani sıçrama yapıyor")
                prev_n30 = n30_val
    return issues


def duplicate_keys(records):
    counts = {}
    for record in records or []:
        if record.get("record_type") == "queue" or not record.get("include", True):
            continue
        kayit = record["kayit"]
        key = (kayit.sondaj_no.strip(), round(safe_float(kayit.derinlik), 2))
        if key[0] and key[1] > 0:
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count > 1}


def record_quality(record, duplicate=False, context_messages=None, current_sondaj_depth=None, valid_sondaj_nolari=None, settings=None):
    if record.get("record_type") == "queue":
        status = record.get("queue_status", "ready")
        message = record.get("queue_message") or "Okumaya hazır"
        if status == "reading":
            return {"level": "reading", "message": message or "Okunuyor", "fields": []}
        if status == "error":
            return {"level": "error", "message": message or "Okunamadı", "fields": ["kaynak"]}
        if status == "skipped":
            return {"level": "warning", "message": message or "Tekrar olduğu için atlandı", "fields": ["kaynak"]}
        return {"level": "queued", "message": message, "fields": []}

    kayit = record["kayit"]
    settings = settings or {}
    valid_sondaj_nolari = valid_sondaj_nolari or set()
    current_sondaj_depth = current_sondaj_depth or (lambda _no: 0)
    guven = safe_float(kayit.guven)
    guven_text = str(kayit.guven or "").strip()
    raw = getattr(kayit, "raw", {}) or {}
    messages = list(context_messages or [])
    fields = set()
    level = "warning" if messages else "ok"
    info_messages = []
    if not record.get("include", True):
        return {"level": "disabled", "message": "Aktarım dışı", "fields": []}
    if not kayit.sondaj_no:
        messages.append("sondaj no eksik")
        fields.add("sondaj_no")
        level = "error"
    elif valid_sondaj_nolari and normalize_sondaj_no(kayit.sondaj_no) not in valid_sondaj_nolari:
        messages.append("sondaj no projede yok")
        fields.add("sondaj_no")
        level = "error"
    if not kayit.derinlik:
        messages.append("derinlik eksik")
        fields.add("derinlik")
        level = "error"
    if not (kayit.v15 or kayit.v30 or kayit.v45 or kayit.n30):
        messages.append("SPT değeri eksik")
        fields.update(("v15", "v30", "v45", "n30"))
        level = "error"
    if duplicate:
        messages.append("aynı derinlik tekrar ediyor")
        fields.add("derinlik")
        if level != "error":
            level = "warning"
    max_depth = current_sondaj_depth(kayit.sondaj_no)
    if max_depth and safe_float(kayit.derinlik) > max_depth + 0.01:
        messages.append("sondaj derinliğini geçiyor")
        fields.add("derinlik")
        if level != "error":
            level = "warning"
    if guven_text and guven < (safe_float(settings.get("guven_esigi", 90)) or 90):
        messages.append(f"düşük güven %{int(guven)}")
        if level != "error":
            level = "warning"
    elif raw.get("motor") and not guven_text:
        messages.append("güven değeri yok")
        if level != "error":
            level = "warning"
    if not kayit.n30:
        messages.append("N30 boş")
        fields.add("n30")
        if level != "error":
            level = "warning"
    if kayit.uyari:
        messages.append(kayit.uyari)
        uyari_lower = str(kayit.uyari).lower()
        if "sondaj" in uyari_lower:
            fields.add("sondaj_no")
        if "derinlik" in uyari_lower:
            fields.add("derinlik")
        if any(token in uyari_lower for token in ("darbe", "spt", "n30")):
            fields.update(("v15", "v30", "v45", "n30"))
        if "okunamadı" in kayit.uyari or "eksik" in kayit.uyari:
            level = "error"
        elif level != "error":
            level = "warning"
    if raw.get("bilgi"):
        info_messages.append(str(raw["bilgi"]))
    okunan = str(raw.get("okunan_derinlik", "") or "")
    hedef = str(raw.get("hedef_derinlik", "") or "")
    if okunan and hedef and okunan != hedef and safe_float(raw.get("derinlik_duzeltme_m")) <= 0.35:
        info_messages.append(f"derinlik {okunan} → {hedef} normalize edildi")
    if level == "ok" and info_messages:
        level = "info"
    all_messages = list(dict.fromkeys(messages + info_messages))
    return {
        "level": level,
        "message": ", ".join(all_messages) or "Hazır",
        "fields": sorted(fields),
    }


def spt_unique_key(kayit, fallback_source="", default_sondaj_no=""):
    source = getattr(kayit, "kaynak_yolu", "") or getattr(kayit, "kaynak", "") or fallback_source
    return (
        source_unique_key(source),
        normalize_sondaj_no(getattr(kayit, "sondaj_no", ""), default_sondaj_no),
        round(safe_float(getattr(kayit, "derinlik", "")), 2),
        str(getattr(kayit, "v15", "") or "").strip(),
        str(getattr(kayit, "v30", "") or "").strip(),
        str(getattr(kayit, "v45", "") or "").strip(),
        str(getattr(kayit, "n30", "") or "").strip(),
    )


def spt_location_key(kayit, default_sondaj_no=""):
    return (
        normalize_sondaj_no(getattr(kayit, "sondaj_no", ""), default_sondaj_no),
        round(safe_float(getattr(kayit, "derinlik", "")), 2),
    )
