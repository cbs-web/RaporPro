# Dosya: RaporPro/proje_paketi.py
"""RaporPro projelerini bagli dosyalariyla tasinabilir bir klasore paketler."""

from __future__ import annotations

import copy
import datetime
import hashlib
import os
import re
import shutil
import uuid

from yardimcilar import atomic_json_dump, atomic_write_text


PAKET_SURUMU = 1
PAKET_META_KEY = "portable_package"
PAKET_MANIFEST_ADI = "RaporPro_Paket_Manifest.json"
PAKET_BILGI_ADI = "PAKET_BILGISI.txt"

_CIKTI_KLASORU_AYARLARI = {
    "varsayilan_cikti_klasor",
    "log_export_klasor",
    "cikti_merkezi_klasor",
}


def _metin(value):
    return "" if value is None else str(value).strip()


def _guvenli_ad(value, fallback="Proje"):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", _metin(value))
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text or fallback


def _norm(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _altinda_mi(path, root):
    try:
        return os.path.commonpath([_norm(path), _norm(root)]) == _norm(root)
    except (TypeError, ValueError, OSError):
        return False


def _veri_yollarini_dolas(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _veri_yollarini_dolas(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _veri_yollarini_dolas(child, path + (index,))
    elif isinstance(value, str):
        yield path, value


def _veri_yoluna_yaz(root, path, value):
    current = root
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def _veri_yolundan_oku(root, path):
    current = root
    for part in path:
        current = current[part]
    return current


def _kaynak_dosya_coz(value, project_dir):
    text = _metin(value).strip('"')
    if not text or text.lower() in {"none", "null"}:
        return None
    expanded = os.path.expandvars(os.path.expanduser(text))
    candidates = [expanded]
    if project_dir and not os.path.isabs(expanded):
        candidates.insert(0, os.path.join(project_dir, expanded))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def _muhtemel_dosya_referansi(path, value):
    if not path or not _metin(value):
        return False
    top = path[0]
    last = str(path[-1]).lower()
    if top == "dosyalar":
        return True
    if top == "ek_icerikleri":
        return isinstance(path[-1], int)
    if top == "harita_cizimleri":
        return any(token in last for token in ("path", "img", "image", "source", "altlik"))
    if top == "ayarlar":
        if last in _CIKTI_KLASORU_AYARLARI:
            return False
        return last.endswith(("_path", "_file", "_dosya")) or "sablon" in last
    return False


def _kategori(path):
    top = path[0] if path else "diger"
    return {
        "dosyalar": "baglantilar",
        "ek_icerikleri": "ekler",
        "harita_cizimleri": "haritalar",
        "ayarlar": "sablonlar",
    }.get(top, "diger")


def _benzersiz_hedef(relative_dir, source, used):
    basename = _guvenli_ad(os.path.basename(source), "dosya")
    stem, ext = os.path.splitext(basename)
    candidate = os.path.join(relative_dir, basename)
    key = os.path.normcase(candidate)
    if key not in used:
        used.add(key)
        return candidate
    digest = hashlib.sha1(_norm(source).encode("utf-8", errors="replace")).hexdigest()[:8]
    candidate = os.path.join(relative_dir, f"{stem}_{digest}{ext}")
    counter = 2
    while os.path.normcase(candidate) in used:
        candidate = os.path.join(relative_dir, f"{stem}_{digest}_{counter}{ext}")
        counter += 1
    used.add(os.path.normcase(candidate))
    return candidate


def paket_hedef_klasoru(parent_dir, project_name):
    base = f"{_guvenli_ad(project_name, 'Proje')[:80]}_RaporPro_Paketi"
    target = os.path.join(os.path.abspath(parent_dir), base)
    if not os.path.exists(target):
        return target
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(os.path.abspath(parent_dir), f"{base}_{stamp}")


def _yarim_paketi_temizle(target_dir, parent_dir):
    """Yalnizca bu islem icin parent altinda olusturulan yarim paketi temizler."""
    if not target_dir or not parent_dir:
        return
    target = os.path.abspath(target_dir)
    parent = os.path.abspath(parent_dir)
    if target == parent or not _altinda_mi(target, parent):
        return
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)


def proje_paketi_olustur(veri, source_project_path, parent_dir, task_context=None):
    """Proje verisinin kopyasini ve bulunan bagli dosyalari yeni pakete yazar."""
    if not isinstance(veri, dict):
        raise TypeError("Proje verisi sozluk olmalidir.")
    if not parent_dir:
        raise ValueError("Paket hedef klasoru secilmedi.")

    source_project_path = os.path.abspath(source_project_path) if source_project_path else ""
    source_dir = os.path.dirname(source_project_path) if source_project_path else ""
    project_name = (veri.get("kunye") or {}).get("sahibi") or (
        os.path.splitext(os.path.basename(source_project_path))[0] if source_project_path else "Proje"
    )
    target_dir = paket_hedef_klasoru(parent_dir, project_name)
    assets_dir = os.path.join(target_dir, "assets")
    os.makedirs(assets_dir, exist_ok=False)

    packaged = copy.deepcopy(veri)
    packaged.pop(PAKET_META_KEY, None)
    references = []
    missing = []
    source_to_relative = {}
    used_targets = set()

    candidates = []
    for data_path, raw_value in _veri_yollarini_dolas(packaged):
        source = _kaynak_dosya_coz(raw_value, source_dir)
        if source:
            candidates.append((data_path, raw_value, source))
        elif _muhtemel_dosya_referansi(data_path, raw_value):
            missing.append({
                "data_path": list(data_path),
                "value": raw_value,
            })

    total = max(1, len(candidates) + 2)
    if task_context:
        task_context.report(0, total, "Paket klasoru hazirlaniyor")

    try:
        for index, (data_path, raw_value, source) in enumerate(candidates, start=1):
            if task_context:
                task_context.check_cancelled()
            source_key = _norm(source)
            relative_path = source_to_relative.get(source_key)
            if relative_path is None:
                relative_dir = os.path.join("assets", _kategori(data_path))
                relative_path = _benzersiz_hedef(relative_dir, source, used_targets)
                target_path = os.path.join(target_dir, relative_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source, target_path)
                source_to_relative[source_key] = relative_path
            portable_value = relative_path.replace(os.sep, "/")
            _veri_yoluna_yaz(packaged, data_path, portable_value)
            references.append({
                "data_path": list(data_path),
                "source_name": os.path.basename(source),
                "relative_path": portable_value,
                "original_value": raw_value,
            })
            if task_context:
                task_context.report(index, total, f"Kopyalandi: {os.path.basename(source)}")
        if task_context:
            task_context.check_cancelled()
    except Exception:
        _yarim_paketi_temizle(target_dir, parent_dir)
        raise

    project_filename = f"{_guvenli_ad(project_name, 'Proje')[:100]}.json"
    project_path = os.path.join(target_dir, project_filename)
    package_id = uuid.uuid4().hex
    packaged[PAKET_META_KEY] = {
        "version": PAKET_SURUMU,
        "package_id": package_id,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "manifest": PAKET_MANIFEST_ADI,
        "references": references,
    }
    try:
        atomic_json_dump(packaged, project_path, indent=4, ensure_ascii=False)
    except Exception:
        _yarim_paketi_temizle(target_dir, parent_dir)
        raise
    if task_context:
        task_context.report(len(candidates) + 1, total, "Proje dosyasi yazildi")

    manifest = {
        "format": "RaporPro Portable Project",
        "version": PAKET_SURUMU,
        "package_id": package_id,
        "created_at": packaged[PAKET_META_KEY]["created_at"],
        "project_file": project_filename,
        "source_project": source_project_path,
        "copied_file_count": len(source_to_relative),
        "reference_count": len(references),
        "missing_count": len(missing),
        "references": references,
        "missing": missing,
    }
    manifest_path = os.path.join(target_dir, PAKET_MANIFEST_ADI)
    readme_path = os.path.join(target_dir, PAKET_BILGI_ADI)
    try:
        atomic_json_dump(manifest, manifest_path, indent=2, ensure_ascii=False)
        atomic_write_text(
            readme_path,
            "\n".join([
                "RaporPro Tasinabilir Proje Paketi",
                "",
                f"Proje dosyasi: {project_filename}",
                f"Kopyalanan dosya: {len(source_to_relative)}",
                f"Eksik baglanti: {len(missing)}",
                "",
                "Paketi baska bir bilgisayara tasirken bu klasorun tamamini birlikte kopyalayin.",
                "Projeyi klasorun icindeki JSON dosyasindan acin.",
            ]),
            encoding="utf-8",
        )
    except Exception:
        _yarim_paketi_temizle(target_dir, parent_dir)
        raise
    if task_context:
        task_context.report(total, total, "Tasinabilir proje paketi hazir")

    return {
        "folder": target_dir,
        "project_path": project_path,
        "manifest_path": manifest_path,
        "readme_path": readme_path,
        "copied_file_count": len(source_to_relative),
        "reference_count": len(references),
        "missing": missing,
    }


def paket_proje_mi(veri):
    meta = veri.get(PAKET_META_KEY) if isinstance(veri, dict) else None
    return isinstance(meta, dict) and int(meta.get("version", 0) or 0) >= 1


def paket_proje_verisini_yukle(veri, project_path):
    """Paket icindeki goreli dosya yollarini calisma sirasinda mutlak yola cevirir."""
    if not paket_proje_mi(veri):
        return veri
    result = copy.deepcopy(veri)
    meta = result.get(PAKET_META_KEY, {})
    project_dir = os.path.dirname(os.path.abspath(project_path))
    for reference in meta.get("references", []) or []:
        data_path = reference.get("data_path")
        relative = _metin(reference.get("relative_path"))
        if not isinstance(data_path, list) or not relative:
            continue
        try:
            candidate = os.path.abspath(os.path.join(project_dir, relative))
            if not _altinda_mi(candidate, project_dir):
                continue
            _veri_yoluna_yaz(result, tuple(data_path), candidate)
        except (KeyError, IndexError, TypeError):
            continue
    result[PAKET_META_KEY]["_runtime_root"] = project_dir
    return result


def paket_proje_verisini_kayda_hazirla(veri, project_path):
    """Paket proje ayni klasore kaydedilirken dosya yollarini yeniden goreli yapar."""
    if not paket_proje_mi(veri):
        return veri
    result = copy.deepcopy(veri)
    meta = result.get(PAKET_META_KEY, {})
    runtime_root = _metin(meta.pop("_runtime_root", ""))
    target_root = os.path.dirname(os.path.abspath(project_path))
    if runtime_root and _norm(runtime_root) != _norm(target_root):
        result.pop(PAKET_META_KEY, None)
        return result

    references = meta.get("references", []) or []
    referenced_paths = {
        tuple(reference.get("data_path") or [])
        for reference in references
        if isinstance(reference, dict)
    }
    for reference in references:
        data_path = reference.get("data_path")
        relative = _metin(reference.get("relative_path"))
        if not isinstance(data_path, list) or not relative:
            continue
        try:
            current = _veri_yolundan_oku(result, tuple(data_path))
        except (KeyError, IndexError, TypeError):
            continue
        if isinstance(current, str) and os.path.isabs(current) and _altinda_mi(current, target_root):
            portable = os.path.relpath(current, target_root).replace(os.sep, "/")
            _veri_yoluna_yaz(result, tuple(data_path), portable)
            reference["relative_path"] = portable
    for data_path, current in list(_veri_yollarini_dolas(result)):
        if data_path and data_path[0] == PAKET_META_KEY:
            continue
        if not os.path.isabs(current) or not os.path.isfile(current) or not _altinda_mi(current, target_root):
            continue
        portable = os.path.relpath(current, target_root).replace(os.sep, "/")
        _veri_yoluna_yaz(result, data_path, portable)
        if data_path not in referenced_paths:
            references.append({
                "data_path": list(data_path),
                "source_name": os.path.basename(current),
                "relative_path": portable,
                "original_value": current,
            })
            referenced_paths.add(data_path)
    return result


__all__ = [
    "PAKET_MANIFEST_ADI",
    "PAKET_META_KEY",
    "paket_hedef_klasoru",
    "paket_proje_mi",
    "paket_proje_verisini_kayda_hazirla",
    "paket_proje_verisini_yukle",
    "proje_paketi_olustur",
]
