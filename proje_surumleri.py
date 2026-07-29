# Dosya: RaporPro/proje_surumleri.py
"""Proje sürümlerini saklar ve iki proje verisini alan bazında karşılaştırır."""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import uuid

from yardimcilar import atomic_json_dump


SURUM_SEMA = 1
VARSAYILAN_SURUM_SINIRI = 40

_UST_BASLIK = {
    "kunye": "Proje Künyesi",
    "bina": "Bina Bilgileri",
    "arazi": "Arazi Bilgileri",
    "sondaj": "Sondajlar",
    "jeofizik": "Jeofizik",
    "lab_sheet": "Laboratuvar Sheet",
    "jeofizik_sheet": "Jeofizik Sheet",
    "harita_cizimleri": "Haritalar",
    "kesit_ayarlari": "Kesit Ayarları",
    "ek_icerikleri": "Ekler",
    "proje_durumu": "Proje Durumu",
    "ayarlar": "Ayarlar",
    "dosyalar": "Dosya Bağlantıları",
}

_ALAN_ADLARI = {
    "sahibi": "Proje adı / sahibi",
    "il": "Il",
    "ilce": "Ilce",
    "mah": "Mahalle",
    "mev": "Mevki",
    "paf": "Pafta",
    "ada": "Ada",
    "par": "Parsel",
    "no": "Numara",
    "der": "Derinlik",
    "kot": "Kot",
    "x": "X koordinati",
    "y": "Y koordinati",
    "bas": "Başlangıç derinliği",
    "bit": "Bitiş derinliği",
    "tanim": "Tanım",
    "litoloji": "Litoloji",
    "spt": "SPT",
    "pmt": "PMT",
    "karot": "Kaya / Karot",
    "numune": "Numune",
    "n30": "N30",
    "v15": "0-15 cm",
    "v30": "15-30 cm",
    "v45": "30-45 cm",
    "tcr": "TCR",
    "scr": "SCR",
    "rqd": "RQD",
    "em": "EM",
    "pl": "PL",
    "tarih": "Tarih",
    "rows": "Satırlar",
    "tur": "Tür",
}

_TOPLU_LISTE_YOLLARI = {
    "lab_sheet.rows": "Laboratuvar çalışma sayfası",
    "jeofizik_sheet.rows": "Jeofizik çalışma sayfası",
}

_LISTE_KIMLIK_ALANLARI = {
    "sondaj": ("no", "sondaj_no", "ad"),
    "sondaj.litoloji": ("bas", "baslangic", "bit", "bitis"),
    "sondaj.spt": ("der", "derinlik", "bas"),
    "sondaj.pmt": ("der", "derinlik", "bas"),
    "sondaj.karot": ("bas", "baslangic", "bit", "bitis", "der"),
    "sondaj.numune": ("der", "derinlik", "bas"),
    "jeofizik.ss_list": ("no", "ad", "serim_no", "name"),
    "jeofizik.mt_list": ("no", "ad", "name"),
    "bina.bloklar": ("blok_adi", "ad", "no"),
}

_SATIR_ALANLARI = {
    "sondaj.litoloji": ("bas", "bit", "tanim"),
    "sondaj.spt": ("der", "v15", "v30", "v45", "n30"),
    "sondaj.pmt": ("der", "em", "pl"),
    "sondaj.kaya": ("der", "tcr", "scr", "rqd"),
    "sondaj.karot": ("der", "tcr", "scr", "rqd"),
    "sondaj.numuneler": ("der", "tur"),
    "sondaj.numune": ("der", "tur"),
}


def _metin(value):
    return "" if value is None else str(value).strip()


def _dolu(value):
    return _metin(value) not in {"", "-", "None", "none", "null"}


def _json_kopya(veri):
    """Snapshot icin JSON ile yazilabilen bagimsiz bir veri kopyasi dondurur."""
    return json.loads(json.dumps(veri, ensure_ascii=False, default=str))


def proje_veri_hash(veri):
    payload = json.dumps(veri, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def _liste(value):
    return value if isinstance(value, list) else []


def proje_ozeti(veri):
    veri = veri if isinstance(veri, dict) else {}
    sondajlar = _liste(veri.get("sondaj"))
    jeofizik = veri.get("jeofizik") if isinstance(veri.get("jeofizik"), dict) else {}
    dosyalar = veri.get("dosyalar") if isinstance(veri.get("dosyalar"), dict) else {}
    return {
        "sondaj": len(sondajlar),
        "litoloji": sum(len(_liste(item.get("litoloji"))) for item in sondajlar if isinstance(item, dict)),
        "spt": sum(len(_liste(item.get("spt"))) for item in sondajlar if isinstance(item, dict)),
        "pmt": sum(len(_liste(item.get("pmt"))) for item in sondajlar if isinstance(item, dict)),
        "kaya": sum(len(_liste(item.get("karot") or item.get("kaya"))) for item in sondajlar if isinstance(item, dict)),
        "lab_satir": len(_liste((veri.get("lab_sheet") or {}).get("rows"))) if isinstance(veri.get("lab_sheet"), dict) else 0,
        "ss": len(_liste(jeofizik.get("ss_list"))),
        "mt": len(_liste(jeofizik.get("mt_list"))),
        "dosya": sum(1 for value in dosyalar.values() if _dolu(value)),
    }


def proje_ozeti_metni(ozet):
    ozet = ozet if isinstance(ozet, dict) else {}
    return (
        f"{ozet.get('sondaj', 0)} sondaj | {ozet.get('litoloji', 0)} litoloji | "
        f"SPT {ozet.get('spt', 0)} | PMT {ozet.get('pmt', 0)} | "
        f"Lab {ozet.get('lab_satir', 0)} satir | SS {ozet.get('ss', 0)} | MT {ozet.get('mt', 0)}"
    )


def _guvenli_ad(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", _metin(value)).strip("._")
    return value or "proje"


def surum_deposu_yolu(project_path):
    project_path = os.path.abspath(os.fspath(project_path))
    project_dir = os.path.dirname(project_path)
    stem = _guvenli_ad(os.path.splitext(os.path.basename(project_path))[0])
    return os.path.join(project_dir, "backups", f"{stem}_surum_gecmisi")


def _index_yolu(project_path):
    return os.path.join(surum_deposu_yolu(project_path), "index.json")


def _bozuk_indeksi_koru(path):
    """Okunamayan indeksi kaybetmeden temiz bir indeks için yer açar."""
    candidate = f"{path}.corrupt"
    counter = 2
    while os.path.exists(candidate):
        candidate = f"{path}.corrupt.{counter}"
        counter += 1
    os.replace(path, candidate)
    return candidate


def _bos_index(project_path):
    return {
        "schema_version": SURUM_SEMA,
        "project_path": os.path.abspath(project_path),
        "next_sequence": 1,
        "legacy_imports": [],
        "versions": [],
    }


def _index_yukle(project_path):
    path = _index_yolu(project_path)
    if not os.path.exists(path):
        return _bos_index(project_path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Sürüm indeksi sözlük değil")
        versions = payload.get("versions")
        if not isinstance(versions, list) or not all(isinstance(item, dict) for item in versions):
            raise ValueError("Sürüm indeksi kayıt listesi geçersiz")
        payload["versions"] = versions
        payload["schema_version"] = SURUM_SEMA
        payload["project_path"] = os.path.abspath(project_path)
        imports = payload.get("legacy_imports")
        if imports is not None and not isinstance(imports, list):
            raise ValueError("Sürüm indeksi eski yedek listesi geçersiz")
        payload["legacy_imports"] = imports or []
        if any(_surum_dosya_yolu(project_path, record) is None for record in payload["versions"]):
            raise ValueError("Sürüm indeksinde güvensiz dosya yolu var")
        try:
            next_sequence = max(1, int(payload.get("next_sequence", 1)))
        except Exception:
            next_sequence = 1
        used_sequences = []
        for record in sorted(payload["versions"], key=_kayit_zamani):
            try:
                sequence = int(record.get("sequence", 0))
            except Exception:
                sequence = 0
            if sequence <= 0 or sequence in used_sequences:
                sequence = max(used_sequences, default=0) + 1
                record["sequence"] = sequence
            used_sequences.append(sequence)
        payload["next_sequence"] = max(next_sequence, max(used_sequences, default=0) + 1)
        return payload
    except Exception:
        try:
            if os.path.exists(path):
                _bozuk_indeksi_koru(path)
        except OSError as preserve_exc:
            raise RuntimeError("Bozuk sürüm indeksi korunamadı; dosya değiştirilmedi") from preserve_exc
        return _bos_index(project_path)


def _index_kaydet(project_path, index):
    os.makedirs(surum_deposu_yolu(project_path), exist_ok=True)
    atomic_json_dump(index, _index_yolu(project_path), indent=2, ensure_ascii=False)


def _surum_dosya_yolu(project_path, record):
    relative = _metin(record.get("file")) if isinstance(record, dict) else ""
    if not relative or os.path.isabs(relative) or os.path.splitdrive(relative)[0]:
        return None
    relative = os.path.normpath(relative.replace("/", os.sep))
    versions_root = os.path.realpath(os.path.join(surum_deposu_yolu(project_path), "versions"))
    candidate = os.path.realpath(os.path.join(surum_deposu_yolu(project_path), relative))
    try:
        if os.path.commonpath([candidate, versions_root]) != versions_root:
            return None
    except (OSError, TypeError, ValueError):
        return None
    if os.path.splitext(candidate)[1].casefold() != ".json":
        return None
    return candidate


def _surum_verisi_oku(project_path, record):
    path = _surum_dosya_yolu(project_path, record)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path or "Sürüm dosyası belirtilmedi")
    with open(path, "r", encoding="utf-8") as handle:
        veri = json.load(handle)
    if not isinstance(veri, dict):
        raise ValueError("Sürüm dosyası geçerli bir proje verisi içermiyor")
    return veri


def _kisa_deger(value, max_length=180):
    if value is None:
        return "-"
    if isinstance(value, list):
        return f"{len(value)} kayit"
    if isinstance(value, dict):
        return f"{len(value)} alan"
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return "-"
    return text if len(text) <= max_length else f"{text[:max_length - 3]}..."


def _kategori(path):
    root = path.split(".", 1)[0].split("[", 1)[0]
    return _UST_BASLIK.get(root, root.replace("_", " ").title())


def _yol_parcalari(path):
    parts = []
    current = []
    bracket_depth = 0
    for char in str(path):
        if char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth:
            bracket_depth -= 1
        if char == "." and bracket_depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _okunabilir_yol(path):
    if path in _TOPLU_LISTE_YOLLARI:
        return _TOPLU_LISTE_YOLLARI[path]
    pieces = []
    for raw in _yol_parcalari(path):
        match = re.match(r"^([^\[]+)(.*)$", raw)
        field = match.group(1) if match else raw
        suffix = match.group(2) if match else ""
        label = _UST_BASLIK.get(field) or _ALAN_ADLARI.get(field) or field.replace("_", " ").title()
        suffix = suffix.replace("[", " [")
        pieces.append(f"{label}{suffix}")
    return " > ".join(pieces)


def _liste_yolu(path):
    return re.sub(r"\[[^\]]*\]", "", path)


def _kimlik_parcalari(item, fields):
    values = []
    for field in fields:
        value = item.get(field)
        if _dolu(value):
            values.append(_metin(value))
        if len(values) >= 2:
            break
    return values


def _liste_kimligi(item, path, index):
    row_fields = _SATIR_ALANLARI.get(_liste_yolu(path))
    if row_fields and isinstance(item, (list, tuple)):
        identity_length = 2 if _liste_yolu(path) == "sondaj.litoloji" else 1
        values = [_metin(value) for value in item[:identity_length] if _dolu(value)]
        return " - ".join(values) if values else f"#{index + 1}"
    if not isinstance(item, dict):
        return None
    fields = _LISTE_KIMLIK_ALANLARI.get(_liste_yolu(path))
    if not fields:
        return None
    values = _kimlik_parcalari(item, fields)
    if not values:
        return f"#{index + 1}"
    return " - ".join(values)


def _degisiklik_ekle(changes, kind, path, old, new, max_changes):
    if len(changes) >= max_changes:
        return
    changes.append({
        "type": kind,
        "category": _kategori(path),
        "path": path,
        "label": _okunabilir_yol(path),
        "old": _kisa_deger(old),
        "new": _kisa_deger(new),
    })


def _karsilastir(old, new, path, changes, max_changes):
    if len(changes) >= max_changes or old == new:
        return

    if isinstance(old, dict) and isinstance(new, dict):
        keys = list(old.keys()) + [key for key in new.keys() if key not in old]
        for key in keys:
            child = f"{path}.{key}" if path else str(key)
            if key not in old:
                _degisiklik_ekle(changes, "added", child, None, new[key], max_changes)
            elif key not in new:
                _degisiklik_ekle(changes, "removed", child, old[key], None, max_changes)
            else:
                _karsilastir(old[key], new[key], child, changes, max_changes)
        return

    if isinstance(old, list) and isinstance(new, list):
        if path in _TOPLU_LISTE_YOLLARI:
            old_text = f"{len(old)} satır"
            new_text = f"{len(new)} satır"
            if len(old) == len(new):
                new_text += " (içerik değişti)"
            _degisiklik_ekle(changes, "changed", path, old_text, new_text, max_changes)
            return

        row_fields = _SATIR_ALANLARI.get(_liste_yolu(path))
        if row_fields and all(not isinstance(item, (dict, list, tuple)) for item in old + new):
            limit = max(len(old), len(new))
            for idx in range(limit):
                field = row_fields[idx] if idx < len(row_fields) else f"alan_{idx + 1}"
                child = f"{path}.{field}"
                if idx >= len(old):
                    _degisiklik_ekle(changes, "added", child, None, new[idx], max_changes)
                elif idx >= len(new):
                    _degisiklik_ekle(changes, "removed", child, old[idx], None, max_changes)
                else:
                    _karsilastir(old[idx], new[idx], child, changes, max_changes)
            return

        old_ids = [_liste_kimligi(item, path, idx) for idx, item in enumerate(old)]
        new_ids = [_liste_kimligi(item, path, idx) for idx, item in enumerate(new)]
        can_match = (
            old_ids or new_ids
        ) and all(item is not None for item in old_ids + new_ids) and len(set(old_ids)) == len(old_ids) and len(set(new_ids)) == len(new_ids)
        if can_match:
            old_map = dict(zip(old_ids, old))
            new_map = dict(zip(new_ids, new))
            identities = old_ids + [item for item in new_ids if item not in old_map]
            for identity in identities:
                child = f"{path}[{identity}]"
                if identity not in old_map:
                    _degisiklik_ekle(changes, "added", child, None, new_map[identity], max_changes)
                elif identity not in new_map:
                    _degisiklik_ekle(changes, "removed", child, old_map[identity], None, max_changes)
                else:
                    _karsilastir(old_map[identity], new_map[identity], child, changes, max_changes)
            return

        if all(not isinstance(item, (dict, list)) for item in old + new):
            _degisiklik_ekle(changes, "changed", path, old, new, max_changes)
            return
        limit = max(len(old), len(new))
        for idx in range(limit):
            child = f"{path}[{idx + 1}]"
            if idx >= len(old):
                _degisiklik_ekle(changes, "added", child, None, new[idx], max_changes)
            elif idx >= len(new):
                _degisiklik_ekle(changes, "removed", child, old[idx], None, max_changes)
            else:
                _karsilastir(old[idx], new[idx], child, changes, max_changes)
        return

    _degisiklik_ekle(changes, "changed", path or "proje", old, new, max_changes)


def proje_verilerini_karsilastir(eski, yeni, max_changes=2000):
    """İki proje verisi arasındaki kullanıcıya gösterilebilir değişiklikleri döndürür."""
    changes = []
    _karsilastir(eski if isinstance(eski, dict) else {}, yeni if isinstance(yeni, dict) else {}, "", changes, max(1, int(max_changes)))
    return changes


def degisiklik_ozeti(changes):
    counts = {"added": 0, "removed": 0, "changed": 0}
    categories = {}
    for item in changes or []:
        kind = item.get("type", "changed")
        counts[kind] = counts.get(kind, 0) + 1
        category = item.get("category", "Diger")
        categories[category] = categories.get(category, 0) + 1
    category_text = ", ".join(
        f"{name}: {count}" for name, count in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))[:4]
    )
    total = sum(counts.values())
    text = f"{total} değişiklik | +{counts['added']}  -{counts['removed']}  ~{counts['changed']}"
    if category_text:
        text += f" | {category_text}"
    return {"total": total, "counts": counts, "categories": categories, "text": text}


def _kayit_zamani(record):
    value = _metin(record.get("created_at"))
    try:
        return _dt.datetime.fromisoformat(value)
    except Exception:
        return _dt.datetime.min


def _surum_kaydi_ekle(project_path, veri, reason, created_at=None, source="manual", keep=VARSAYILAN_SURUM_SINIRI, force=False, dedup_all=False):
    project_path = os.path.abspath(os.fspath(project_path))
    data = _json_kopya(veri)
    data_hash = proje_veri_hash(data)
    index = _index_yukle(project_path)
    records = index["versions"]
    records.sort(key=_kayit_zamani)

    if records:
        hashes = [item.get("hash") for item in records]
        duplicate = data_hash in hashes if dedup_all else records[-1].get("hash") == data_hash
        if duplicate and not force:
            return copy.deepcopy(records[-1]), False

    previous_data = None
    if records:
        try:
            previous_data = _surum_verisi_oku(project_path, records[-1])
        except Exception:
            previous_data = None
    changes = proje_verilerini_karsilastir(previous_data or {}, data) if previous_data is not None else []
    change_summary = degisiklik_ozeti(changes)

    now = created_at or _dt.datetime.now().isoformat(timespec="seconds")
    try:
        stamp = _dt.datetime.fromisoformat(now).strftime("%Y%m%d_%H%M%S")
    except Exception:
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    record_id = f"{stamp}_{data_hash[:8]}_{uuid.uuid4().hex[:4]}"
    filename = f"{record_id}.json"
    relative = os.path.join("versions", filename)
    target = os.path.join(surum_deposu_yolu(project_path), relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    atomic_json_dump(data, target, indent=2, ensure_ascii=False)

    record = {
        "id": record_id,
        "sequence": int(index.get("next_sequence", 1)),
        "created_at": now,
        "reason": _metin(reason) or "Proje kaydı",
        "source": source,
        "file": relative.replace("\\", "/"),
        "hash": data_hash,
        "summary": proje_ozeti(data),
        "change_count": change_summary["total"],
        "change_summary": change_summary["text"],
    }
    index["next_sequence"] = record["sequence"] + 1
    records.append(record)
    records.sort(key=_kayit_zamani)

    keep = max(5, min(int(keep or VARSAYILAN_SURUM_SINIRI), 250))
    removed = records[:-keep]
    index["versions"] = records[-keep:]
    _index_kaydet(project_path, index)
    for old_record in removed:
        old_path = _surum_dosya_yolu(project_path, old_record)
        try:
            if old_path and os.path.isfile(old_path):
                os.remove(old_path)
        except OSError:
            pass
    return copy.deepcopy(record), True


def _yedek_tarihi(path, stem):
    name = os.path.splitext(os.path.basename(path))[0]
    match = re.match(rf"^{re.escape(stem)}_(\d{{8}}_\d{{6}})(?:_\d+)?$", name)
    if match:
        try:
            return _dt.datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            pass
    return _dt.datetime.fromtimestamp(os.path.getmtime(path))


def eski_yedekleri_ice_aktar(project_path, keep=VARSAYILAN_SURUM_SINIRI):
    """Eski backup JSON dosyalarını bir kez okunabilir sürüm kaydına dönüştürür."""
    project_path = os.path.abspath(os.fspath(project_path))
    project_dir = os.path.dirname(project_path)
    stem = os.path.splitext(os.path.basename(project_path))[0]
    backup_dir = os.path.join(project_dir, "backups")
    if not os.path.isdir(backup_dir):
        return 0
    candidates = []
    prefix = f"{stem}_"
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isfile(path) and name.startswith(prefix) and name.lower().endswith(".json"):
            candidates.append(path)
    candidates.sort(key=lambda item: _yedek_tarihi(item, stem))

    index = _index_yukle(project_path)
    processed = set(str(item) for item in index.get("legacy_imports", []))
    newly_processed = []
    imported = 0
    for path in candidates:
        stat = os.stat(path)
        token = f"{os.path.basename(path)}|{stat.st_size}|{stat.st_mtime_ns}"
        if token in processed:
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                continue
            created = _yedek_tarihi(path, stem).isoformat(timespec="seconds")
            _record, was_created = _surum_kaydi_ekle(
                project_path,
                data,
                "Eski proje yedeği",
                created_at=created,
                source="legacy_backup",
                keep=keep,
                force=False,
                dedup_all=True,
            )
            imported += int(was_created)
            newly_processed.append(token)
        except Exception:
            continue
    if newly_processed:
        index = _index_yukle(project_path)
        combined = list(dict.fromkeys(list(index.get("legacy_imports", [])) + newly_processed))
        index["legacy_imports"] = combined[-500:]
        _index_kaydet(project_path, index)
    return imported


def surum_kaydi_olustur(project_path, veri, reason="Proje kaydedildi", keep=VARSAYILAN_SURUM_SINIRI, force=False, source="manual"):
    if not project_path:
        raise ValueError("Sürüm kaydı için önce proje dosyası kaydedilmelidir")
    keep = max(5, min(int(keep or VARSAYILAN_SURUM_SINIRI), 250))
    eski_yedekleri_ice_aktar(project_path, keep=keep)
    return _surum_kaydi_ekle(project_path, veri, reason, source=source, keep=keep, force=force)


def surumleri_listele(project_path, eski_yedekleri_aktar=True, keep=VARSAYILAN_SURUM_SINIRI):
    if not project_path:
        return []
    if eski_yedekleri_aktar:
        eski_yedekleri_ice_aktar(project_path, keep=keep)
    index = _index_yukle(project_path)
    valid = []
    for record in index.get("versions", []):
        if not isinstance(record, dict):
            continue
        path = _surum_dosya_yolu(project_path, record)
        if path and os.path.isfile(path):
            valid.append(copy.deepcopy(record))
    valid.sort(key=_kayit_zamani)
    for number, record in enumerate(valid, start=1):
        record["number"] = record.get("sequence") or number
    return list(reversed(valid))


def surum_verisi_yukle(project_path, version):
    if isinstance(version, str):
        records = surumleri_listele(project_path, eski_yedekleri_aktar=False)
        version = next((item for item in records if item.get("id") == version), None)
    if not isinstance(version, dict):
        raise KeyError("İstenen sürüm bulunamadı")
    return _surum_verisi_oku(project_path, version)


def surum_deposunu_kopyala(source_project_path, target_project_path):
    """Farklı kaydet senaryolarında istenirse sürüm deposunu yeni projeye kopyalar."""
    source = surum_deposu_yolu(source_project_path)
    target = surum_deposu_yolu(target_project_path)
    if not os.path.isdir(source) or os.path.normcase(source) == os.path.normcase(target):
        return False
    if os.path.exists(target):
        return False
    shutil.copytree(source, target)
    index = _index_yukle(target_project_path)
    index["project_path"] = os.path.abspath(target_project_path)
    _index_kaydet(target_project_path, index)
    return True
