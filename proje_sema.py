# Dosya: RaporPro/proje_sema.py
"""RaporPro proje dosyalari icin surumleme ve geriye donuk migrasyon."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from hidrojeoloji_raporu import hidrojeoloji_varsayilanlari
from jeoloji_raporu import (
    JEOLOJI_BIRIM_KATALOGU,
    jeoloji_kodu_normalize,
    jeoloji_varsayilanlari,
)
from kesit_motor_ayarlari import KESIT_ENGINE_DEFAULT
from proje_surumleri import VARSAYILAN_SURUM_SINIRI
from rapor_parsel_bilgileri import (
    parsel_tipi_normalize_et,
    rapor_bilgileri_varsayilanlari,
)


PROJE_SEMA_SURUMU = 6


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


def varsayilan_proje_verisi():
    """Yeni proje ve sema onarimi icin tek kanonik veri yapisini dondurur."""
    return {
        "schema_version": PROJE_SEMA_SURUMU,
        "kunye": {"sahibi":"", "il":"", "ilce":"", "mah":"", "mev":"", "paf":"", "ada":"", "par":""},
        "bina": {"kul":"", "sinif":"", "onem":"", "malz":"", "bod":"", "kat":"", "plan":"", "yukseklik":"", "yukseklik_sinif":"", "temel_alan":"", "ins":"", "der":"", "gqe_min":"", "gqe_max":"", "gqe_ort":"", "comb_min":"", "comb_max":"", "comb_ort":"", "ysinif":"", "tem":"", "coklu_blok": False, "bloklar": []},
        "arazi": {
            "kot": "", "yon": "", "egim": "", "min": "", "max": "", "ort": "",
            "imar_alani": "", "imar_durumu": "", "zemin": "", "kategori": "",
            "pga": "", "alan_y": "", "alan_x": "",
            "hidrojeoloji": hidrojeoloji_varsayilanlari(),
        },
        "sondaj": [],
        "jeofizik": {"tarih": "", "ss_list": [], "mt_list": []},
        "jeoloji": jeoloji_varsayilanlari(),
        "jeoloji_kutuphanesi": {
            "selected_source_id": None,
            "selected_source_hash": "",
            "selected_snapshot": {},
        },
        "rapor_bilgileri": rapor_bilgileri_varsayilanlari(),
        "harita_cizimleri": {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}},
        "lab_sheet": {"rows": []},
        "litoloji_manuel_taslak": {"surum": 1, "sondajlar": {}},
        "jeofizik_sheet": {"rows": []},
        "kesit_ayarlari": {
            "section_engine": KESIT_ENGINE_DEFAULT,
            "show_detailed_lithology_labels": False,
        },
        "ek_icerikleri": {"normal": {}, "arazi_deneyli": {}},
        "proje_durumu": {"tamamlandi": False, "kilitli": False, "tamamlanma_tarihi": "", "arsiv_notu": ""},
        "ayarlar": {
            "firma_adi": "UB ZEMIN MUHENDISLIK",
            "log_baslik": "SONDAJ LOGU",
            "sorumlu_muhendis_unvan": "Sorumlu Jeoloji Muhendisi",
            "sorumlu_muhendis": "Gökalp DOĞAN",
            "sondor_belge_baslik": "Sondor Belge No",
            "sondor_belge": "Murat ERÇELİK 3629",
            "makine_metodu": "Rotary / Burgusuz",
            "spt_sahmerdan": "Otomatik",
            "sondaj_turu": "Zemin",
            "delgi_capi": "76mm",
            "varsayilan_word_path": "",
            "rapor_sablon_profili": "genel",
            "varsayilan_cikti_klasor": "",
            "log_export_klasor": "",
            "log_export_format": "JPG",
            "log_export_dpi": "300",
            "log_export_prefix": "Log",
            "cikti_merkezi_klasor": "",
            "cikti_merkezi_format": "JPG",
            "cikti_merkezi_dpi": "300",
            "cikti_merkezi_profili": "Standart Teslim",
            "cikti_merkezi_secimler": {
                "report": True,
                "logs": True,
                "section": True,
                "maps": True,
                "report_images": True,
                "taahhutnameler": True,
                "ekler": True,
                "sondaj_data": False,
                "geophysics_data": False,
                "source_files": False,
            },
            "harita_altlik": "Google Uydu",
            "rapor_buyuk_baslik_yeni_sayfa": "1",
            "taahhut_ilgili_idare": "",
            "taahhut_tarih": "",
            "ek_tutanak_path": "",
            "ek_arazi_deneyli_path": "",
            "tutanak_sablon_path": "",
            "tutanak_sondaj_firma": "Kale Detay Sondaj",
            "tutanak_uygulama_sekli": "Burgusuz/Sulu",
            "tutanak_sondaj_makinesi": "SMK-500",
            "tutanak_jeofizik_cihaz": "GEODE",
            "tutanak_jeofon": "3,0m - 4,5 Hz",
            "tutanak_offset": "3,0m",
            "tutanak_kanal_sayisi": "12",
            "tutanak_kaynak": "Balyoz",
            "taahhut_jeoloji_ad": "Gökalp DOĞAN",
            "taahhut_jeoloji_sicil": "7400",
            "taahhut_jeoloji_unvan": "JEOLOJİ MÜHENDİSİ",
            "taahhut_jeoloji_imza_unvan": "Jeoloji Mühendisi",
            "taahhut_jeoloji_adres": "İsmetpaşa Mh. Hasan Mevsuf Sk. No :4 Da:5",
            "taahhut_jeoloji_telefon": "0 545 639 90 62",
            "taahhut_jeofizik_ad": "Suat ERGİN",
            "taahhut_jeofizik_sicil": "1982",
            "taahhut_jeofizik_unvan": "JEOFİZİK MÜHENDİSİ",
            "taahhut_jeofizik_imza_unvan": "Jeofizik Mühendisi",
            "taahhut_jeofizik_adres": "İsmetpaşa Mh. Hasan Mevsuf Sk. No :4 Da:5",
            "taahhut_jeofizik_telefon": "0 532 281 12 95",
            "yedek_sayisi": "10",
            "surum_gecmisi_sayisi": str(VARSAYILAN_SURUM_SINIRI),
            "ui_animasyon": "1",
            "spt_guven_esigi": "90",
            "spt_auto_pro": "1",
        },
        "dosyalar": {
            "kml_path": None,
            "word_path": None,
            "lab_excel_path": None,
            "jeo_excel_path": None,
            "masw_word_paths": [],
            "img_yer": None,
            "img_tkgm": None,
            "img_pga": None,
            "img_mjh": None,
            "word_img_sondaj": None,
            "word_img_jeofizik": None,
        },
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


def _sonlu_sayilari_dogrula(value, yol="$"):
    if isinstance(value, float) and not math.isfinite(value):
        raise ProjeSemaHatasi(f"{yol} alaninda sonlu olmayan sayi kullanilamaz.")
    if isinstance(value, dict):
        for key, child in value.items():
            _sonlu_sayilari_dogrula(child, f"{yol}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _sonlu_sayilari_dogrula(child, f"{yol}[{index}]")


def _cekirdek_tipleri_onar(hedef, varsayilan, yol="$"):
    onarilanlar = []
    for key, beklenen in varsayilan.items():
        if key not in hedef:
            continue
        mevcut = hedef[key]
        alan_yolu = f"{yol}.{key}"
        if isinstance(beklenen, dict):
            if not isinstance(mevcut, dict):
                hedef[key] = copy.deepcopy(beklenen)
                onarilanlar.append(alan_yolu)
            else:
                onarilanlar.extend(_cekirdek_tipleri_onar(mevcut, beklenen, alan_yolu))
        elif isinstance(beklenen, list) and not isinstance(mevcut, list):
            hedef[key] = copy.deepcopy(beklenen)
            onarilanlar.append(alan_yolu)
    return onarilanlar


def _sondaj_tiplerini_dogrula_ve_onar(veri):
    onarilanlar = []
    for index, sondaj in enumerate(veri.get("sondaj", [])):
        if not isinstance(sondaj, dict):
            raise ProjeSemaHatasi(
                f"$.sondaj[{index}] bir JSON nesnesi olmalidir."
            )
        for key in ("litoloji", "spt", "pmt", "kaya", "numuneler"):
            if not isinstance(sondaj.get(key), list):
                sondaj[key] = []
                onarilanlar.append(f"$.sondaj[{index}].{key}")
    return onarilanlar


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


def _v2_v3_migrasyonu(veri):
    jeoloji = veri.get("jeoloji")
    if not isinstance(jeoloji, dict):
        jeoloji = {}
        veri["jeoloji"] = jeoloji
    _eksikleri_tamamla(jeoloji, jeoloji_varsayilanlari())

    # Eski mühendislik jeolojisi haritasındaki formasyon yalnız öneri olarak
    # taşınır. Kullanıcı onaylamadan rapor birimi kabul edilmez.
    if not jeoloji.get("birimler") and not jeoloji.get("harita_formasyon_onerisi"):
        haritalar = veri.get("harita_cizimleri", {})
        harita_jeoloji = (
            haritalar.get("jeoloji", {})
            if isinstance(haritalar, dict)
            else {}
        )
        eski_kod = (
            harita_jeoloji.get("formasyon")
            if isinstance(harita_jeoloji, dict)
            else ""
        )
        eski_kod = jeoloji_kodu_normalize(eski_kod)
        if eski_kod in JEOLOJI_BIRIM_KATALOGU:
            jeoloji["harita_formasyon_onerisi"] = eski_kod

    veri["schema_version"] = 3
    return ["Jeolojik birim ve dinamik rapor alanlari proje verisine eklendi."]


def _v3_v4_migrasyonu(veri):
    rapor_bilgileri = veri.get("rapor_bilgileri")
    if not isinstance(rapor_bilgileri, dict):
        rapor_bilgileri = {}
        veri["rapor_bilgileri"] = rapor_bilgileri
    _eksikleri_tamamla(rapor_bilgileri, rapor_bilgileri_varsayilanlari())

    kunye = veri.get("kunye") if isinstance(veri.get("kunye"), dict) else {}
    ayarlar = veri.get("ayarlar") if isinstance(veri.get("ayarlar"), dict) else {}
    legacy_name = str(kunye.get("sahibi") or "").strip()
    if legacy_name:
        rapor_bilgileri["proje_adi"] = (
            str(rapor_bilgileri.get("proje_adi") or "").strip() or legacy_name
        )
        rapor_bilgileri["yapi_sahibi"] = (
            str(rapor_bilgileri.get("yapi_sahibi") or "").strip() or legacy_name
        )
    if not str(rapor_bilgileri.get("ilgili_idare") or "").strip():
        rapor_bilgileri["ilgili_idare"] = str(
            ayarlar.get("taahhut_ilgili_idare") or ""
        ).strip()

    for target, source in (
        ("sismik_cihaz", "tutanak_jeofizik_cihaz"),
        ("sismik_kanal_sayisi", "tutanak_kanal_sayisi"),
        ("jeofon_frekansi", "tutanak_jeofon"),
        ("sismik_kaynak", "tutanak_kaynak"),
    ):
        if not str(rapor_bilgileri.get(target) or "").strip():
            rapor_bilgileri[target] = str(ayarlar.get(source) or "").strip()

    veri["schema_version"] = 4
    return ["Parsel bazli Word raporu alanlari proje verisine eklendi."]


def _v4_v5_migrasyonu(veri):
    dosyalar = veri.get("dosyalar")
    if not isinstance(dosyalar, dict):
        dosyalar = {}
        veri["dosyalar"] = dosyalar
    if not isinstance(dosyalar.get("masw_word_paths"), list):
        dosyalar["masw_word_paths"] = []
    veri["schema_version"] = 5
    return ["MASW hiz grafigi Word kaynaklari proje verisine eklendi."]


def _v5_v6_migrasyonu(veri):
    """Imar adasi icin duz alanlari eski projelere guvenle ekler."""
    rapor_bilgileri = veri.get("rapor_bilgileri")
    if not isinstance(rapor_bilgileri, dict):
        rapor_bilgileri = {}
        veri["rapor_bilgileri"] = rapor_bilgileri
    _eksikleri_tamamla(rapor_bilgileri, rapor_bilgileri_varsayilanlari())
    rapor_bilgileri["parsel_tipi"] = parsel_tipi_normalize_et(
        rapor_bilgileri.get("parsel_tipi", "")
    )
    veri["schema_version"] = 6
    return ["Imar adasi saha alanlari ve parsel tipi secenekleri proje verisine eklendi."]


def proje_verisini_migre_et(veri, varsayilan=None):
    """Proje verisini kopyalayarak guncel semaya getirir ve migrasyon bilgisini dondurur."""
    if not isinstance(veri, dict):
        raise ProjeSemaHatasi("Proje dosyasinin kok degeri bir JSON nesnesi olmalidir.")
    _sonlu_sayilari_dogrula(veri)

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
    if surum == 2:
        notlar.extend(_v2_v3_migrasyonu(sonuc))
        surum = 3
    if surum == 3:
        notlar.extend(_v3_v4_migrasyonu(sonuc))
        surum = 4
    if surum == 4:
        notlar.extend(_v4_v5_migrasyonu(sonuc))
        surum = 5
    if surum == 5:
        notlar.extend(_v5_v6_migrasyonu(sonuc))
        surum = 6

    if varsayilan is not None and not isinstance(varsayilan, dict):
        raise TypeError("Varsayilan proje verisi bir sozluk olmalidir.")

    kanonik_varsayilan = varsayilan_proje_verisi()
    onarilanlar = _cekirdek_tipleri_onar(sonuc, kanonik_varsayilan)
    onarilanlar.extend(_sondaj_tiplerini_dogrula_ve_onar(sonuc))
    if onarilanlar:
        notlar.append(
            f"{len(onarilanlar)} cekirdek proje alani gecersiz tipten varsayilana onarildi."
        )

    onceki = copy.deepcopy(sonuc)
    if varsayilan is not None:
        _eksikleri_tamamla(sonuc, varsayilan)
    _eksikleri_tamamla(sonuc, kanonik_varsayilan)
    if sonuc != onceki:
        notlar.append("Yeni surumdeki eksik proje alanlari varsayilan degerlerle tamamlandi.")

    sonuc["schema_version"] = PROJE_SEMA_SURUMU
    _sonlu_sayilari_dogrula(sonuc)
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
    "varsayilan_proje_verisi",
]
