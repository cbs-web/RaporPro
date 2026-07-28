# Dosya: RaporPro/proje_sema.py
"""RaporPro proje dosyalari icin surumleme ve geriye donuk migrasyon."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from hidrojeoloji_raporu import hidrojeoloji_varsayilanlari


PROJE_SEMA_SURUMU = 2


class ProjeSemaHatasi(ValueError):
    """Proje dosyasi desteklenmeyen veya gecersiz bir semaya sahipse kullanilir."""


@dataclass(frozen=True)
class ProjeMigrasyonBilgisi:
    onceki_surum: int
    yeni_surum: int
    degisti: bool
    notlar: tuple[str, ...] = ()


_DOSYA_ALANLARI = {
    "kml_path": ("kml_path", "kml", "kml_file", "kml_dosya", "kml_sinir_path", "kml_siniri_path", "kml_sınır_path"),
    "word_path": ("word_path", "word", "word_file", "word_dosya"),
    "lab_excel_path": ("lab_excel_path", "lab_excel", "laboratuvar_excel", "lab_dosya"),
    "jeo_excel_path": ("jeo_excel_path", "jeofizik_excel", "jeo_excel"),
    "img_yer": ("img_yer", "yerbuldurur_img", "yerbuldurur"),
    "img_tkgm": ("img_tkgm", "tkgm_img", "tkgm"),
    "img_pga": ("img_pga", "pga_img", "pga"),
    "img_mjh": ("img_mjh", "mjh_img", "mjh"),
    "word_img_sondaj": ("word_img_sondaj", "img_sondaj", "sondaj_haritasi"),
    "word_img_jeofizik": ("word_img_jeofizik", "img_jeofizik", "jeofizik_haritasi"),
}


def _surum_degeri(value):
    if value in (None, ""):
        return 0
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise ProjeSemaHatasi(f"Gecersiz proje sema surumu: {value!r}") from exc
    if version < 0:
        raise ProjeSemaHatasi(f"Gecersiz proje sema surumu: {version}")
    return version


def _eksikleri_tamamla(hedef, varsayilan):
    for key, value in varsayilan.items():
        if key not in hedef:
            hedef[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(hedef.get(key), dict):
            _eksikleri_tamamla(hedef[key], value)


def _ilk_deger(*kaynaklar):
    for kaynak, aliases in kaynaklar:
        if not isinstance(kaynak, dict):
            continue
        for key in aliases:
            value = kaynak.get(key)
            if value not in (None, "", "None", "none", "null", "-"):
                return value
    return None


def _v0_v1_migrasyonu(veri):
    notlar = []

    dosyalar = veri.get("dosyalar")
    if not isinstance(dosyalar, dict):
        dosyalar = {}
        veri["dosyalar"] = dosyalar
    moved_paths = 0
    for target, aliases in _DOSYA_ALANLARI.items():
        if dosyalar.get(target) not in (None, ""):
            continue
        value = _ilk_deger((dosyalar, aliases), (veri, aliases))
        if value is not None:
            dosyalar[target] = value
            moved_paths += 1
    if moved_paths:
        notlar.append(f"{moved_paths} eski dosya baglantisi standart alana tasindi.")

    sondajlar = veri.get("sondaj")
    if not isinstance(sondajlar, list):
        sondajlar = []
        veri["sondaj"] = sondajlar
        notlar.append("Gecersiz sondaj listesi bos liste olarak onarildi.")
    repaired_boreholes = 0
    for sondaj in sondajlar:
        if not isinstance(sondaj, dict):
            continue
        changed = False
        for key in ("litoloji", "spt", "pmt", "kaya", "numuneler"):
            if not isinstance(sondaj.get(key), list):
                sondaj[key] = []
                changed = True
        if changed:
            repaired_boreholes += 1
    if repaired_boreholes:
        notlar.append(f"{repaired_boreholes} sondajda eksik deney listeleri tamamlandi.")

    jeofizik = veri.get("jeofizik")
    if not isinstance(jeofizik, dict):
        jeofizik = {}
        veri["jeofizik"] = jeofizik
    if not isinstance(jeofizik.get("ss_list"), list):
        legacy_ss = jeofizik.get("ss")
        jeofizik["ss_list"] = copy.deepcopy(legacy_ss) if isinstance(legacy_ss, list) else []
    if not isinstance(jeofizik.get("mt_list"), list):
        legacy_mt = jeofizik.get("mt")
        jeofizik["mt_list"] = copy.deepcopy(legacy_mt) if isinstance(legacy_mt, list) else []
    if "tarih" not in jeofizik:
        jeofizik["tarih"] = veri.get("jeofizik_tarih", "")

    veri["schema_version"] = 1
    notlar.append("Proje veri yapisi surum 1'e yukseltildi.")
    return notlar


def _v1_v2_migrasyonu(veri):
    arazi = veri.get("arazi")
    if not isinstance(arazi, dict):
        arazi = {}
        veri["arazi"] = arazi
    hidrojeoloji = arazi.get("hidrojeoloji")
    if not isinstance(hidrojeoloji, dict):
        hidrojeoloji = {}
        arazi["hidrojeoloji"] = hidrojeoloji
    _eksikleri_tamamla(hidrojeoloji, hidrojeoloji_varsayilanlari())
    veri["schema_version"] = 2
    return ["Hidrojeoloji rapor alanlari proje verisine eklendi."]


def proje_verisini_migre_et(veri, varsayilan=None):
    """Proje verisini kopyalayarak guncel semaya getirir ve migrasyon bilgisini dondurur."""
    if not isinstance(veri, dict):
        raise ProjeSemaHatasi("Proje dosyasinin kok degeri bir JSON nesnesi olmalidir.")

    original = copy.deepcopy(veri)
    sonuc = copy.deepcopy(veri)
    onceki_surum = _surum_degeri(sonuc.get("schema_version"))
    if onceki_surum > PROJE_SEMA_SURUMU:
        raise ProjeSemaHatasi(
            f"Bu proje daha yeni bir RaporPro surumuyle kaydedilmis "
            f"(proje: v{onceki_surum}, program destegi: v{PROJE_SEMA_SURUMU})."
        )

    notlar = []
    surum = onceki_surum
    if surum == 0:
        notlar.extend(_v0_v1_migrasyonu(sonuc))
        surum = 1
    if surum == 1:
        notlar.extend(_v1_v2_migrasyonu(sonuc))
        surum = 2

    if varsayilan is not None:
        if not isinstance(varsayilan, dict):
            raise TypeError("Varsayilan proje verisi bir sozluk olmalidir.")
        onceki = copy.deepcopy(sonuc)
        _eksikleri_tamamla(sonuc, varsayilan)
        if sonuc != onceki:
            notlar.append("Yeni surumdeki eksik proje alanlari varsayilan degerlerle tamamlandi.")

    sonuc["schema_version"] = PROJE_SEMA_SURUMU
    bilgi = ProjeMigrasyonBilgisi(
        onceki_surum=onceki_surum,
        yeni_surum=PROJE_SEMA_SURUMU,
        degisti=sonuc != original,
        notlar=tuple(notlar),
    )
    return sonuc, bilgi


__all__ = [
    "PROJE_SEMA_SURUMU",
    "ProjeMigrasyonBilgisi",
    "ProjeSemaHatasi",
    "proje_verisini_migre_et",
]
