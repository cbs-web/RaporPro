# Dosya: RaporPro/harita_durum.py
"""Harita katmanlari ve rapor ciktilarinin guncellik durumunu yonetir."""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import os
from pathlib import Path

from jeoloji_raporu import (
    JEOLOJI_BIRIM_KATALOGU,
    KONUM_HER_IKISI,
    KONUM_INCELEME_ALANI,
    jeoloji_birimleri,
    jeoloji_kodu_normalize,
)


HARITA_KATMAN_VARSAYILANLARI = {
    "altlik": True,
    "kml": True,
    "sondaj": True,
    "ss": True,
    "mt": True,
    "etiketler": True,
    "otomatik_etiket": True,
}

HARITA_CIKTI_ANAHTARLARI = ("sondaj", "jeofizik", "mjh", "yer", "tkgm")


def _bilinen_formasyon_kodu(value):
    code = jeoloji_kodu_normalize(value)
    return code if code in JEOLOJI_BIRIM_KATALOGU else ""


def harita_formasyon_kodu(veri):
    """Projenin harita formasyonunu eski kayıtları da gözeterek belirle."""
    veri = veri if isinstance(veri, dict) else {}
    ayarlar = veri.get("ayarlar", {}) if isinstance(veri.get("ayarlar"), dict) else {}
    code = _bilinen_formasyon_kodu(ayarlar.get("harita_formasyon"))
    if code:
        return code

    cizimler = (
        veri.get("harita_cizimleri", {})
        if isinstance(veri.get("harita_cizimleri"), dict)
        else {}
    )
    jeoloji_cizimi = (
        cizimler.get("jeoloji", {})
        if isinstance(cizimler.get("jeoloji"), dict)
        else {}
    )
    code = _bilinen_formasyon_kodu(jeoloji_cizimi.get("formasyon"))
    if code:
        return code

    for record in jeoloji_birimleri(veri):
        if record.get("konum") in {KONUM_INCELEME_ALANI, KONUM_HER_IKISI}:
            code = _bilinen_formasyon_kodu(record.get("kod"))
            if code:
                return code

    jeoloji = veri.get("jeoloji", {}) if isinstance(veri.get("jeoloji"), dict) else {}
    code = _bilinen_formasyon_kodu(jeoloji.get("harita_formasyon_onerisi"))
    if code:
        return code
    return next(iter(JEOLOJI_BIRIM_KATALOGU))


def harita_katman_ayarlari(value=None):
    """Eksik veya eski katman ayarlarini geriye donuk uyumlu hale getir."""
    result = dict(HARITA_KATMAN_VARSAYILANLARI)
    if isinstance(value, dict):
        for key in result:
            if key in value:
                result[key] = bool(value[key])
    return result


def _dosya_ozeti(path):
    text = str(path or "").strip()
    if not text:
        return {"name": "", "size": None, "mtime_ns": None}
    file_path = Path(text)
    try:
        stat = file_path.stat()
        return {
            "name": file_path.name,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }
    except OSError:
        return {"name": file_path.name, "size": None, "mtime_ns": None}


def _sondaj_ozeti(veri):
    result = []
    for item in veri.get("sondaj", []) if isinstance(veri.get("sondaj"), list) else []:
        if isinstance(item, dict):
            result.append(
                {
                    "no": item.get("no"),
                    "x": item.get("x"),
                    "y": item.get("y"),
                }
            )
    return result


def _jeofizik_ozeti(veri):
    jeofizik = veri.get("jeofizik", {}) if isinstance(veri.get("jeofizik"), dict) else {}
    ss_list = []
    for item in jeofizik.get("ss_list", []) if isinstance(jeofizik.get("ss_list"), list) else []:
        if isinstance(item, dict):
            ss_list.append({"ad": item.get("ad"), "coords": item.get("coords")})
    mt_list = []
    for item in jeofizik.get("mt_list", []) if isinstance(jeofizik.get("mt_list"), list) else []:
        if isinstance(item, dict):
            mt_list.append(
                {
                    "no": item.get("no"),
                    "x": item.get("x"),
                    "y": item.get("y"),
                }
            )
    return {"ss_list": ss_list, "mt_list": mt_list}


def _cizim_ozeti(cizim, mods):
    if not isinstance(cizim, dict):
        return {}
    objects = cizim.get("objects", {}) if isinstance(cizim.get("objects"), dict) else {}
    summary = {
        "img_path": _dosya_ozeti(cizim.get("img_path")),
        "georef_refs": cizim.get("georef_refs", []),
        "objects": {mod: objects.get(mod, {}) for mod in mods},
    }
    if "formasyon" in mods:
        summary["scale"] = cizim.get("scale")
        summary["formasyon"] = cizim.get("formasyon")
    return summary


def _harita_imza_verisi(veri, cikti_tipi):
    veri = veri if isinstance(veri, dict) else {}
    ayarlar = veri.get("ayarlar", {}) if isinstance(veri.get("ayarlar"), dict) else {}
    dosyalar = veri.get("dosyalar", {}) if isinstance(veri.get("dosyalar"), dict) else {}
    cizimler = (
        veri.get("harita_cizimleri", {})
        if isinstance(veri.get("harita_cizimleri"), dict)
        else {}
    )
    layers = harita_katman_ayarlari(ayarlar.get("harita_katmanlari"))
    common = {"version": 1}
    if cikti_tipi == "yer" or (
        cikti_tipi in {"sondaj", "jeofizik", "mjh"} and layers["kml"]
    ):
        common["kml"] = _dosya_ozeti(dosyalar.get("kml_path"))

    if cikti_tipi == "sondaj":
        common.update(
            {
                "katmanlar": {
                    key: layers[key]
                    for key in ("altlik", "kml", "sondaj", "etiketler", "otomatik_etiket")
                },
                "sondaj": _sondaj_ozeti(veri),
                "cizim": _cizim_ozeti(cizimler.get("vaziyet", {}), ("sondaj",)),
            }
        )
    elif cikti_tipi == "jeofizik":
        common.update(
            {
                "katmanlar": {
                    key: layers[key]
                    for key in ("altlik", "kml", "ss", "mt", "etiketler", "otomatik_etiket")
                },
                "jeofizik": _jeofizik_ozeti(veri),
                "cizim": _cizim_ozeti(cizimler.get("vaziyet", {}), ("ss", "mt")),
            }
        )
    elif cikti_tipi == "mjh":
        common.update(
            {
                "katmanlar": layers,
                "sondaj": _sondaj_ozeti(veri),
                "jeofizik": _jeofizik_ozeti(veri),
                "jeoloji": veri.get("jeoloji", {}),
                "formasyon": ayarlar.get("harita_formasyon"),
                "cizim": _cizim_ozeti(
                    cizimler.get("jeoloji", {}),
                    ("sondaj", "ss", "mt", "formasyon"),
                ),
            }
        )
    elif cikti_tipi == "yer":
        common.update({"cizim": cizimler.get("yerbuldurur", {})})
    elif cikti_tipi == "tkgm":
        kunye = veri.get("kunye", {}) if isinstance(veri.get("kunye"), dict) else {}
        common.update(
            {
                "altlik": ayarlar.get("harita_altlik"),
                "kunye": {
                    key: kunye.get(key)
                    for key in ("il", "ilce", "mah", "paf", "ada", "par")
                }
            }
        )
    else:
        common["cikti_tipi"] = cikti_tipi
    return common


def harita_kaynak_imzasi(veri, cikti_tipi):
    """Bir harita ciktisini etkileyen proje verilerinin kararlı imzasini uret."""
    payload = json.dumps(
        _harita_imza_verisi(veri, cikti_tipi),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def harita_cikti_meta_olustur(veri, cikti_tipi, path, now=None):
    """Yeni uretilen harita ciktisi icin proje icinde saklanacak metayi olustur."""
    now = now or _datetime.datetime.now()
    return {
        "path": str(path or ""),
        "created_at": now.isoformat(timespec="seconds"),
        "source_signature": harita_kaynak_imzasi(veri, cikti_tipi),
    }


def _tarih_metni(meta, path):
    created_at = meta.get("created_at") if isinstance(meta, dict) else ""
    if created_at:
        try:
            value = _datetime.datetime.fromisoformat(str(created_at))
            return value.strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            pass
    try:
        value = _datetime.datetime.fromtimestamp(os.path.getmtime(path))
        return value.strftime("%d.%m.%Y %H:%M")
    except (OSError, TypeError, ValueError):
        return ""


def harita_cikti_durumu(veri, cikti_tipi, path, meta=None):
    """Cikti icin ``ok``, ``stale``, ``warning`` veya ``empty`` durumu dondur."""
    if not path:
        return "empty", "Oluşturulmadı"
    if not os.path.isfile(path):
        return "warning", "Dosya bulunamadı"

    meta = meta if isinstance(meta, dict) else {}
    tarih = _tarih_metni(meta, path)
    recorded_signature = str(meta.get("source_signature") or "")
    if recorded_signature:
        current_signature = harita_kaynak_imzasi(veri, cikti_tipi)
        if recorded_signature != current_signature:
            suffix = f" · {tarih}" if tarih else ""
            return "stale", f"Eski çıktı{suffix}"

    suffix = f" · {tarih}" if tarih else ""
    return "ok", f"Hazır{suffix}"
