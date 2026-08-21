# Dosya: RaporPro/kurtarma_motoru.py
"""Otomatik kayitlarin guvenli sekilde degerlendirilmesi icin saf yardimcilar."""

from __future__ import annotations

import copy
import datetime as _datetime
import hashlib
import json
import os
from dataclasses import dataclass


_VOLATILE_TOP_LEVEL = {"schema_version", "ayarlar", "proje_durumu"}
_SCAFFOLD_SONDAJ_FIELDS = {
    "no",
    "der",
    "bas_tar",
    "bit_tar",
    "yass_t1",
    "yass_t2",
    "litoloji",
    "spt",
    "pmt",
    "kaya",
    "numuneler",
}

# Eski surumlerde yeni proje sablonunun icine yazilan, proje verisi sayilmayan
# varsayilanlar. Yeni projelerde ayni alanlar kullanilsa bile baska bir proje
# bilgisi yoksa tek basina kurtarma uyarisi olusturmamalidir.
_LEGACY_DEFAULTS = {
    "sismik_cihaz": {"geode"},
    "sismik_kanal_sayisi": {"12"},
    "jeofon_frekansi": {"3,0m - 4,5 hz"},
    "sismik_kaynak": {"balyoz"},
    "imar_alani": {"konut alani"},
    "imar_durumu": {
        "onlemli alan 1.1 (oa-1.1) : sivılasma tehlikesi acisindan onlemli alanlar",
    },
    "kategori": {"kategori 2"},
    "formasyon_secim": {"seçiniz...", "seciniz...", "se�iniz..."},
    "rapor_ortami": {"otomatik"},
    "imar_ek_no": {"ek-8"},
    "laboratuvar_ek_no": {"ek-5"},
    "spt_enerji_orani": {"60"},
    "spt_tij_boyu_m": {"1", "1.0"},
    "zemin_tipi": {"zemin"},
    "izin": {"100"},
    "es_birim": {"kg/cm2"},
    "oturma_zemin_turu": {"kohezyonlu"},
    "oturma_temel_turu": {"radye"},
    "konsolidasyon_tipi": {"yok"},
    "tasima_guncel": {"true"},
}


@dataclass(frozen=True)
class KurtarmaKarari:
    """Kurtarma kaydinin acilis ekraninda nasil ele alinacagini belirtir."""

    durum: str
    neden: str
    temizlenebilir: bool = False


def _metin(value):
    return " ".join(str(value or "").split()).strip()


def _bos_metin(value):
    return _metin(value).casefold() in {"", "-", "none", "null", "nan"}


def _json_imzasi(value):
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        payload = repr(value)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def veri_imzasi(value):
    """Veriyi dosya sirasi ve Python nesnesinden bagimsiz imzalar."""

    return _json_imzasi(value)


def _karsilastirma_verisi(value):
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    result.pop("schema_version", None)
    # Ayarlar proje verisi degildir; eski surumlerdeki varsayilanlar bu alani
    # gereksiz bir fark gibi gosterebiliyordu.
    result.pop("ayarlar", None)
    return result


def veriler_esit_mi(left, right):
    """Iki proje verisinin kurtarma amaciyla ayni icerigi tasiyip tasimadigini bulur."""

    if _json_imzasi(left) == _json_imzasi(right):
        return True
    return _json_imzasi(_karsilastirma_verisi(left)) == _json_imzasi(
        _karsilastirma_verisi(right)
    )


def _legacy_default_mi(path, value):
    if not path:
        return False
    key = str(path[-1]).casefold()
    normalized = _metin(value).casefold()
    if key == "imar_alani" and normalized.startswith("konut alan"):
        return True
    if key == "imar_durumu" and normalized.lstrip("�öiı ").startswith("nlemli alan 1.1"):
        return True
    if key == "spt_numune_alici":
        return "standart numune al" in normalized or "numune al" in normalized
    if key in {"tasima_guncel", "izin_otomatik"}:
        return value is True
    return normalized in _LEGACY_DEFAULTS.get(key, set())


def _eski_tarih_sablonu_sondaji_mi(row):
    """Eski bos proje sihirbazinin otomatik SK-1/15 m iskeletini tanir."""

    if not isinstance(row, dict):
        return False
    no = _metin(row.get("no")).casefold().replace(" ", "")
    derinlik = _metin(row.get("der")).replace(",", ".")
    if no not in {"sk-1", "sk1"} or derinlik not in {"15", "15.0", "15.00"}:
        return False
    if any(not _bos_metin(row.get(key)) for key in ("y", "x", "k", "yass_d1", "yass_d2")):
        return False
    if any(row.get(key) for key in ("litoloji", "spt", "pmt", "kaya", "numuneler")):
        return False
    # Bu dort tarih alanini eski bos kayit otomatik dolduruyordu. Tarihlerin
    # kendisini proje verisi saymiyoruz; gercek bir kullanici kaydinda baska
    # bir alan (koordinat, kot, deney veya litoloji) da bulunacaktir.
    return all(not _bos_metin(row.get(key)) for key in ("bas_tar", "bit_tar", "yass_t1", "yass_t2"))


def _sondaj_satiri_anlamli_mi(row):
    if not isinstance(row, dict):
        return bool(row)
    if _eski_tarih_sablonu_sondaji_mi(row):
        return False
    for key, value in row.items():
        if key in {"bas_tar", "bit_tar", "yass_t1", "yass_t2"}:
            continue
        if key in {"no", "der"} and not _bos_metin(value):
            return True
        if key in _SCAFFOLD_SONDAJ_FIELDS:
            if key in {"litoloji", "spt", "pmt", "kaya", "numuneler"} and value:
                return True
            continue
        if key in {"y", "x", "k", "yass_d1", "yass_d2"} and not _bos_metin(value):
            return True
        if isinstance(value, (list, dict)) and value:
            return True
        if not isinstance(value, (list, dict)) and not _bos_metin(value):
            return True
    return False


def _bolumde_anlamli_veri_var_mi(value, baseline=None, path=()):
    if path == ("sondaj",) and isinstance(value, list):
        return any(_sondaj_satiri_anlamli_mi(row) for row in value)
    if isinstance(value, dict):
        baseline = baseline if isinstance(baseline, dict) else {}
        for key, child in value.items():
            if not path and key in _VOLATILE_TOP_LEVEL:
                continue
            if path == ("rapor_bilgileri",) and key == "tarih":
                continue
            child_path = path + (str(key),)
            if key in baseline and child == baseline[key]:
                continue
            if _legacy_default_mi(child_path, child):
                continue
            child_baseline = baseline.get(key)
            if _bolumde_anlamli_veri_var_mi(child, child_baseline, child_path):
                return True
        return False
    if isinstance(value, list):
        return any(_bolumde_anlamli_veri_var_mi(item, None, path) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return not _bos_metin(value)


def kurtarma_verisi_anlamli_mi(veri, varsayilan_veri=None):
    """Bos proje iskeletini gercek kullanici verisinden ayirir."""

    if not isinstance(veri, dict):
        return False
    baseline = varsayilan_veri if isinstance(varsayilan_veri, dict) else {}
    return _bolumde_anlamli_veri_var_mi(veri, baseline)


def _zaman_coz(value):
    if isinstance(value, _datetime.datetime):
        return value
    text = _metin(value)
    if not text:
        return None
    try:
        return _datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _zaman_damgasi(value):
    if isinstance(value, (int, float)):
        return float(value)
    parsed = _zaman_coz(value)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        return parsed.timestamp()
    return parsed.replace(tzinfo=_datetime.timezone.utc).timestamp()


def _yol_norm(value):
    text = _metin(value)
    if not text:
        return ""
    try:
        return os.path.normcase(os.path.abspath(os.fspath(text)))
    except (TypeError, ValueError):
        return text.casefold()


def kurtarma_kaydini_degerlendir(
    payload,
    *,
    varsayilan_veri=None,
    aktif_veri=None,
    aktif_dosya_yolu=None,
    aktif_dosya_mtime=None,
    kurtarma_dosyasi_mtime=None,
):
    """Kurtarma kaydini acmadan once guvenli bir karar uretir.

    ``empty``, ``same`` ve ``stale`` kararlar kullanici verisi icermedigi veya
    ana proje tarafindan zaten karsilandigi icin sessizce temizlenebilir.
    ``new`` karari ise anlamli ve kurtarilmamis veriyi temsil eder; UI bu durumda
    kullaniciya secenek sunmalidir.
    """

    if not isinstance(payload, dict) or not isinstance(payload.get("veri"), dict):
        return KurtarmaKarari("invalid", "Kurtarma kaydinda proje verisi yok.")

    recovery_veri = payload["veri"]
    if not kurtarma_verisi_anlamli_mi(recovery_veri, varsayilan_veri):
        return KurtarmaKarari("empty", "Kurtarma kaydi bos veya varsayilan proje iskeleti.", True)

    recovery_path = _yol_norm(payload.get("active_path"))
    active_path = _yol_norm(aktif_dosya_yolu) or recovery_path
    if isinstance(aktif_veri, dict) and veriler_esit_mi(recovery_veri, aktif_veri):
        return KurtarmaKarari("same", "Kurtarma kaydi ana proje ile ayni icerikte.", True)

    recovery_time = _zaman_damgasi(payload.get("saved_at"))
    if recovery_time is None:
        recovery_time = kurtarma_dosyasi_mtime
    if (
        isinstance(aktif_veri, dict)
        and recovery_path
        and active_path
        and recovery_path == active_path
        and recovery_time is not None
        and aktif_dosya_mtime is not None
        and recovery_time <= float(aktif_dosya_mtime) + 1.0
    ):
        return KurtarmaKarari("stale", "Kurtarma kaydi ana proje dosyasindan eski.", True)

    return KurtarmaKarari("new", "Anlamli ve daha yeni bir kurtarma kaydi bulundu.")


__all__ = [
    "KurtarmaKarari",
    "kurtarma_kaydini_degerlendir",
    "kurtarma_verisi_anlamli_mi",
    "veri_imzasi",
    "veriler_esit_mi",
]
