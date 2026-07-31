# Dosya: RaporPro/rapor_parsel_bilgileri.py
"""Parsel bazli Word raporu alanlarini ve guvenli metinlerini uretir."""

from __future__ import annotations

import copy
import datetime as _datetime
import math
import re
import unicodedata


DURUM_SECENEKLERI = ("Belirtilmedi", "Yok", "Var")
PARSEL_TIPI_SECENEKLERI = ("Belirtilmedi", "Ara parsel", "Köşe parsel")
ARASTIRMA_CUKURU_SECENEKLERI = ("Belirtilmedi", "Yapılmadı", "Yapıldı")

RAPOR_BILGILERI_DEFAULT = {
    "proje_adi": "",
    "yapi_sahibi": "",
    "ilgili_idare": "",
    "rapor_tarihi": "",
    "rapor_no": "",
    "parsel_alani_m2": "",
    "parsel_tipi": PARSEL_TIPI_SECENEKLERI[0],
    "yol_cepheleri": "",
    "komsu_parseller": "",
    "mevcut_yapilar": "",
    "mevcut_kullanim": "",
    "bitki_ortusu": "",
    "altyapi_durumu": "",
    "drenaj_durumu": "",
    "ulasim_durumu": "",
    "cevre_ek_aciklama": "",
    "plan_adi": "",
    "plan_onay_tarihi": "",
    "plan_karar_no": "",
    "plan_onay_idaresi": "",
    "afete_maruz_bolge": DURUM_SECENEKLERI[0],
    "yapi_yasagi": DURUM_SECENEKLERI[0],
    "imar_ek_no": "EK-8",
    "imar_ek_aciklama": "",
    "iklim_tipi": "",
    "meteoroloji_istasyonu": "",
    "meteoroloji_periyodu": "",
    "don_derinligi_cm": "",
    "calisilmayan_donemi": "",
    "iklim_kaynagi": "",
    "iklim_tablosu_kullan": False,
    "heyelan_durumu": DURUM_SECENEKLERI[0],
    "kaya_dusmesi_durumu": DURUM_SECENEKLERI[0],
    "cig_durumu": DURUM_SECENEKLERI[0],
    "cokme_durumu": DURUM_SECENEKLERI[0],
    "afet_ek_aciklama": "",
    "aktif_tektonik_aciklama": "",
    "aktif_faylar": [],
    "laboratuvar_adi": "",
    "laboratuvar_yetki_aciklamasi": "",
    "laboratuvar_ek_no": "EK-5",
    "sismik_cihaz": "",
    "sismik_kanal_sayisi": "",
    "jeofon_frekansi": "",
    "sismik_kaynak": "",
    "sismik_vurus_sayisi": "",
    "sismik_kayit_uzunlugu": "",
    "masw_vurus_sayisi": "",
    "masw_kayit_uzunlugu": "",
    "mt_cihaz": "",
    "mt_kayit_suresi_dk": "",
    "mt_degerlendirme_yazilimi": "",
    "spt_enerji_orani": "60",
    "spt_tij_boyu_m": "1",
    "spt_numune_alici": "iç tüpü olmayan standart numune alıcı",
    "arastirma_cukuru_durumu": ARASTIRMA_CUKURU_SECENEKLERI[0],
    "arastirma_cukuru_aciklamasi": "",
    "kazi_sinifi": "",
    "kazi_guclugu": "",
    "kazi_aciklamasi": "",
    "sonuc_ek_aciklama": "",
}

RAPOR_METIN_ETIKETLERI = (
    "[ETUT_AMAC_KAPSAM]",
    "[RAPOR_KAPSAM]",
    "[PARSEL_TANITIM]",
    "[IMAR_PLANI_ACIKLAMA]",
    "[IMAR_ADASI_ACIKLAMA]",
    "[IKLIM_ACIKLAMA]",
    "[DON_DURUM_ACIKLAMA]",
    "[DOGAL_AFET_ACIKLAMA]",
    "[AKTIF_TEKTONIK_ACIKLAMA]",
    "[AKTIF_FAY_GIRIS]",
    "[SONDAJ_ARAZI_GIRIS]",
    "[JEOFIZIK_ARAZI_GIRIS]",
    "[SISMIK_YONTEM_ACIKLAMA]",
    "[VP_ACIKLAMA]",
    "[MASW_YONTEM_ACIKLAMA]",
    "[MASW_SONUC_ACIKLAMA]",
    "[MT_YONTEM_ACIKLAMA]",
    "[MT_DEGERLENDIRME_ACIKLAMA]",
    "[MT_REZONANS_ACIKLAMA]",
    "[ARASTIRMA_CUKURU_ACIKLAMA]",
    "[SONDAJ_BOLUM_GIRIS]",
    "[SPT_GIRIS]",
    "[SPT_TEKNIK_ACIKLAMA]",
    "[LAB_GIRIS]",
    "[LAB_FIZIK_GIRIS]",
    "[LAB_MEKANIK_GIRIS]",
    "[KESIT_GIRIS]",
    "[SONUC_GIRIS]",
    "[SONUC_KONUM]",
    "[SONUC_IMAR]",
    "[SONUC_AFET]",
    "[SONUC_KAZI]",
    "[SONUC_KAZI_ONLEM]",
    "[SONUC_EK_ACIKLAMA]",
)

_AYLAR_TR = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)


def rapor_bilgileri_varsayilanlari():
    return copy.deepcopy(RAPOR_BILGILERI_DEFAULT)


def _text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _present(value):
    return _text(value) not in ("", "-", "None", "none", "nan", "NaN")


def _sentence(value):
    text = _text(value)
    if not text:
        return ""
    return text if text[-1] in ".!?" else f"{text}."


def _number(value):
    text = _text(value).replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format_number(value, decimals=2):
    number = _number(value)
    if number is None:
        return _text(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.{int(decimals)}f}".rstrip("0").rstrip(".").replace(".", ",")


def _status(value, choices, default):
    def comparison_text(raw):
        normalized = unicodedata.normalize("NFKD", _text(raw))
        return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()

    clean = comparison_text(value)
    for choice in choices:
        if clean == comparison_text(choice):
            return choice
    return default


def _bool(value):
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in {"1", "true", "evet", "var", "on"}


def _project_parts(veri):
    veri = veri if isinstance(veri, dict) else {}
    return (
        veri.get("kunye", {}) if isinstance(veri.get("kunye"), dict) else {},
        veri.get("arazi", {}) if isinstance(veri.get("arazi"), dict) else {},
        veri.get("bina", {}) if isinstance(veri.get("bina"), dict) else {},
        veri.get("jeofizik", {}) if isinstance(veri.get("jeofizik"), dict) else {},
        veri.get("ayarlar", {}) if isinstance(veri.get("ayarlar"), dict) else {},
    )


def rapor_bilgilerini_normalize_et(veri):
    veri = veri if isinstance(veri, dict) else {}
    source = veri.get("rapor_bilgileri")
    source = source if isinstance(source, dict) else {}
    result = rapor_bilgileri_varsayilanlari()
    for key, default in result.items():
        if key not in source:
            continue
        value = source.get(key)
        if key == "aktif_faylar":
            result[key] = copy.deepcopy(value) if isinstance(value, list) else []
        elif isinstance(default, bool):
            result[key] = _bool(value)
        else:
            result[key] = _text(value)

    result["parsel_tipi"] = _status(
        result["parsel_tipi"],
        PARSEL_TIPI_SECENEKLERI,
        PARSEL_TIPI_SECENEKLERI[0],
    )
    for key in (
        "afete_maruz_bolge",
        "yapi_yasagi",
        "heyelan_durumu",
        "kaya_dusmesi_durumu",
        "cig_durumu",
        "cokme_durumu",
    ):
        result[key] = _status(result[key], DURUM_SECENEKLERI, DURUM_SECENEKLERI[0])
    result["arastirma_cukuru_durumu"] = _status(
        result["arastirma_cukuru_durumu"],
        ARASTIRMA_CUKURU_SECENEKLERI,
        ARASTIRMA_CUKURU_SECENEKLERI[0],
    )

    kunye, _arazi, _bina, _jeofizik, ayarlar = _project_parts(veri)
    legacy_name = _text(kunye.get("sahibi"))
    if not result["proje_adi"]:
        result["proje_adi"] = legacy_name
    if not result["yapi_sahibi"]:
        result["yapi_sahibi"] = legacy_name
    if not result["ilgili_idare"]:
        result["ilgili_idare"] = _text(ayarlar.get("taahhut_ilgili_idare"))

    fallback_settings = {
        "sismik_cihaz": "tutanak_jeofizik_cihaz",
        "sismik_kanal_sayisi": "tutanak_kanal_sayisi",
        "jeofon_frekansi": "tutanak_jeofon",
        "sismik_kaynak": "tutanak_kaynak",
    }
    for key, setting_key in fallback_settings.items():
        if not result[key]:
            result[key] = _text(ayarlar.get(setting_key))
    return result


def rapor_proje_adi(veri):
    return rapor_bilgilerini_normalize_et(veri).get("proje_adi", "")


def rapor_yapi_sahibi(veri):
    return rapor_bilgilerini_normalize_et(veri).get("yapi_sahibi", "")


def rapor_tarihi(veri, today=None):
    data = rapor_bilgilerini_normalize_et(veri)
    return data.get("rapor_tarihi") or (today or _datetime.date.today()).strftime("%d.%m.%Y")


def rapor_ay_yil(veri, today=None):
    raw = rapor_tarihi(veri, today=today)
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", raw)
    if match:
        month = int(match.group(2))
        if 1 <= month <= 12:
            return f"{_AYLAR_TR[month - 1]} {match.group(3)}"
    return raw


def _konum_ozeti(kunye):
    parts = []
    for key, suffix in (
        ("il", "ili"),
        ("ilce", "ilçesi"),
        ("mah", "Mahallesi"),
        ("ada", "ada"),
        ("par", "parsel"),
    ):
        value = _text(kunye.get(key))
        if value:
            parts.append(f"{value} {suffix}")
    return ", ".join(parts)


def _sondaj_ozeti(sondajlar):
    rows = [row for row in sondajlar or [] if isinstance(row, dict)]
    if not rows:
        return "Sahada sondaj çalışması yapılmamıştır."
    detail = []
    for row in rows:
        name = _text(row.get("no")) or "Sondaj"
        depth = _text(row.get("der"))
        detail.append(f"{name}: {depth} m" if depth else name)
    return f"Sahada toplam {len(rows)} adet sondaj kuyusu ({', '.join(detail)}) açılmıştır."


def _lab_ready(veri):
    rows = veri.get("lab_sheet", {}).get("rows", []) if isinstance(veri, dict) else []
    if any(any(_present(cell) for cell in row) for row in rows or []):
        return True
    files = veri.get("dosyalar", {}) if isinstance(veri, dict) else {}
    return bool(isinstance(files, dict) and _present(files.get("lab_excel_path")))


def rapor_kapsam_metni(veri):
    veri = veri if isinstance(veri, dict) else {}
    sondajlar = veri.get("sondaj", []) or []
    jeofizik = veri.get("jeofizik", {}) or {}
    works = []
    if sondajlar:
        works.append("sondaj çalışmaları")
    if any(s.get("spt") for s in sondajlar if isinstance(s, dict)):
        works.append("SPT deneyleri")
    if any(s.get("pmt") for s in sondajlar if isinstance(s, dict)):
        works.append("presiyometre deneyleri")
    if any(s.get("kaya") for s in sondajlar if isinstance(s, dict)):
        works.append("karot değerlendirmeleri")
    if jeofizik.get("ss_list"):
        works.append("sismik kırılma ve MASW ölçümleri")
    if jeofizik.get("mt_list"):
        works.append("mikrotremör ölçümleri")
    if _lab_ready(veri):
        works.append("laboratuvar deneyleri")
    if not works:
        return (
            "Bu veri raporu, proje kapsamında mevcut arazi ve büro verilerinin "
            "değerlendirilmesi amacıyla hazırlanmıştır."
        )
    if len(works) == 1:
        work_text = works[0]
    else:
        work_text = f"{', '.join(works[:-1])} ve {works[-1]}"
    return (
        f"Bu veri raporu kapsamında {work_text} gerçekleştirilmiş; elde edilen "
        "bulgular parsel bazında değerlendirilmiştir. Arazi, laboratuvar ve büro "
        "çalışmalarının sonuçları ilgili bölüm, tablo ve eklerde sunulmuştur."
    )


def etut_amac_kapsam_metni(veri):
    kunye, _arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    location = _konum_ozeti(kunye)
    project = data["proje_adi"] or "planlanan yapı"
    location_text = f"{location} konumundaki" if location else "inceleme alanındaki"
    return (
        f"Bu çalışma, {location_text} {project} için zemin koşullarının "
        "belirlenmesi ve geoteknik değerlendirmelere esas oluşturacak arazi, "
        "laboratuvar ve jeofizik verilerinin sunulması amacıyla hazırlanmıştır."
    )


def parsel_tanitim_metni(veri):
    kunye, arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    sentences = []
    location = _konum_ozeti(kunye)
    coord_y = _text(arazi.get("alan_y"))
    coord_x = _text(arazi.get("alan_x"))
    first = f"İnceleme alanı {location} sınırlarında yer almaktadır" if location else "İnceleme alanının konum bilgileri proje künyesinde tanımlanmamıştır"
    if coord_y and coord_x:
        first += f" ve merkez koordinatı Enlem: {coord_y}, Boylam: {coord_x} (WGS84) olarak girilmiştir"
    sentences.append(_sentence(first))
    if data["parsel_alani_m2"]:
        sentences.append(f"Parsel alanı yaklaşık {_format_number(data['parsel_alani_m2'])} m²'dir.")
    if _present(arazi.get("ort")):
        sentences.append(f"İnceleme alanının ortalama kotu {_text(arazi.get('ort'))} m'dir.")
    if _present(arazi.get("min")) and _present(arazi.get("max")):
        sentences.append(
            f"En düşük kot {_text(arazi.get('min'))} m, en yüksek kot "
            f"{_text(arazi.get('max'))} m'dir."
        )
    slope_parts = []
    if _present(arazi.get("egim")):
        slope_parts.append(f"eğim {_text(arazi.get('egim'))}")
    if _present(arazi.get("yon")):
        slope_parts.append(f"eğim yönü {_text(arazi.get('yon'))}")
    if slope_parts:
        sentences.append(_sentence("Çalışma alanında " + ", ".join(slope_parts) + " olarak belirlenmiştir"))
    if data["parsel_tipi"] != PARSEL_TIPI_SECENEKLERI[0]:
        sentences.append(f"Parsel {data['parsel_tipi'].casefold()} niteliğindedir.")
    labelled = (
        ("Parselin yol cepheleri", "yol_cepheleri"),
        ("Komşu parsel bilgileri", "komsu_parseller"),
        ("Yakın çevredeki mevcut yapılar", "mevcut_yapilar"),
        ("Parselin mevcut kullanımı", "mevcut_kullanim"),
        ("Bitki örtüsü", "bitki_ortusu"),
        ("Altyapı durumu", "altyapi_durumu"),
        ("Drenaj durumu", "drenaj_durumu"),
        ("Ulaşım durumu", "ulasim_durumu"),
    )
    for label, key in labelled:
        if data[key]:
            sentences.append(_sentence(f"{label}: {data[key]}"))
    if data["cevre_ek_aciklama"]:
        sentences.append(_sentence(data["cevre_ek_aciklama"]))
    sentences.append("İnceleme alanı yer bulduru haritası Şekil 1'de verilmiştir.")
    return " ".join(sentence for sentence in sentences if sentence)


def imar_plani_metni(veri):
    _kunye, arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    sentences = []
    approval = []
    if data["plan_onay_tarihi"]:
        approval.append(f"{data['plan_onay_tarihi']} tarihli")
    if data["plan_karar_no"]:
        approval.append(f"{data['plan_karar_no']} sayılı karar")
    if data["plan_onay_idaresi"]:
        approval.append(f"{data['plan_onay_idaresi']} tarafından onaylanan")
    if data["plan_adi"]:
        approval.append(data["plan_adi"])
    if approval:
        sentences.append(_sentence("İnceleme alanı " + " ".join(approval) + " kapsamında değerlendirilmektedir"))
    elif _present(arazi.get("imar_alani")):
        sentences.append(f"İnceleme alanı {_text(arazi.get('imar_alani'))} içinde bulunmaktadır.")
    if _present(arazi.get("imar_durumu")):
        sentences.append(
            "İmar planına esas jeolojik-jeoteknik etüt kapsamında "
            f"{_text(arazi.get('imar_durumu'))} olarak değerlendirilmiştir."
        )
    status_sentences = {
        ("afete_maruz_bolge", "Yok"): "İnceleme alanı için Afete Maruz Bölge kararı bulunmadığı belirtilmiştir.",
        ("afete_maruz_bolge", "Var"): "İnceleme alanı için Afete Maruz Bölge kararı bulunduğu belirtilmiştir.",
        ("yapi_yasagi", "Yok"): "Proje verilerinde yapı yasağı bulunmadığı belirtilmiştir.",
        ("yapi_yasagi", "Var"): "Proje verilerinde yapı yasağı bulunduğu belirtilmiştir.",
    }
    for (key, status), sentence in status_sentences.items():
        if data[key] == status:
            sentences.append(sentence)
    if data["imar_ek_no"]:
        sentences.append(f"İmar durum belgesi {data['imar_ek_no']}'de verilmiştir.")
    if data["imar_ek_aciklama"]:
        sentences.append(_sentence(data["imar_ek_aciklama"]))
    if not sentences:
        return "İnceleme alanına ait imar ve plan kararı bilgileri proje verilerinde tanımlanmamıştır."
    return " ".join(sentences)


def imar_adasi_metni(veri):
    _kunye, arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    sentences = []
    if _present(arazi.get("imar_alani")):
        sentences.append(f"Çalışma alanı {_text(arazi.get('imar_alani'))} içinde bulunmaktadır.")
    for label, key in (
        ("Yol ve cephe durumu", "yol_cepheleri"),
        ("Komşu parseller", "komsu_parseller"),
        ("Ulaşım", "ulasim_durumu"),
        ("Altyapı", "altyapi_durumu"),
        ("Drenaj", "drenaj_durumu"),
    ):
        if data[key]:
            sentences.append(_sentence(f"{label}: {data[key]}"))
    if not sentences:
        return "İmar adasının yol, komşuluk ve altyapı bilgileri proje verilerinde tanımlanmamıştır."
    return " ".join(sentences)


def iklim_metni(veri):
    kunye, _arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    sentences = []
    place = _text(kunye.get("il")) or "inceleme alanı"
    if data["iklim_tipi"]:
        sentences.append(f"{place} çevresinde {data['iklim_tipi']} özellikleri görülmektedir.")
    if data["meteoroloji_istasyonu"]:
        period = (
            f" ({data['meteoroloji_periyodu']} ölçüm dönemi)"
            if data["meteoroloji_periyodu"]
            else ""
        )
        sentences.append(
            f"İklim değerlendirmesinde {data['meteoroloji_istasyonu']}{period} verileri esas alınmıştır."
        )
    if data["iklim_kaynagi"]:
        sentences.append(_sentence(f"İklim verisi kaynağı: {data['iklim_kaynagi']}"))
    if not sentences:
        return "İnceleme alanına ilişkin iklim verileri proje bilgilerinde tanımlanmamıştır."
    return " ".join(sentences)


def don_durum_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    sentences = []
    if data["don_derinligi_cm"]:
        sentences.append(
            f"Proje alanı için don penetrasyon derinliği "
            f"{_format_number(data['don_derinligi_cm'])} cm olarak alınmıştır."
        )
    if data["calisilmayan_donemi"]:
        sentences.append(
            f"Don koşulları bakımından çalışmaya uygun olmayan dönem "
            f"{data['calisilmayan_donemi']} olarak belirtilmiştir."
        )
    return " ".join(sentences) or "Don derinliği ve çalışma dönemi bilgileri proje verilerinde tanımlanmamıştır."


def _risk_sentence(label, status):
    if status == "Yok":
        return f"Mevcut proje verilerinde {label} belirlenmemiştir."
    if status == "Var":
        return f"Mevcut proje verilerinde {label} bulunduğu belirtilmiştir."
    return ""


def dogal_afet_metni(veri):
    _kunye, arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    sentences = []
    for label, key in (
        ("heyelan tehlikesi", "heyelan_durumu"),
        ("kaya düşmesi tehlikesi", "kaya_dusmesi_durumu"),
        ("çığ tehlikesi", "cig_durumu"),
        ("çökme tehlikesi", "cokme_durumu"),
    ):
        sentence = _risk_sentence(label, data[key])
        if sentence:
            sentences.append(sentence)
    hydro = arazi.get("hidrojeoloji", {}) if isinstance(arazi.get("hidrojeoloji"), dict) else {}
    flood = _text(hydro.get("taskin_riski"))
    if flood == "Yok":
        sentences.append("Mevcut veriler kapsamında inceleme alanını etkileyen taşkın riski belirlenmemiştir.")
    elif flood == "Var":
        sentences.append("İnceleme alanında taşkın riski bulunduğu belirtilmiştir.")
    pga = _text(arazi.get("pga"))
    if pga:
        sentences.append(
            "Türkiye Deprem Tehlike Haritasına göre çalışma alanı için "
            f"PGA475={pga} g olarak alınmıştır."
        )
    if data["afet_ek_aciklama"]:
        sentences.append(_sentence(data["afet_ek_aciklama"]))
    if not sentences:
        return "Doğal afet tehlikelerine ilişkin parsel bazlı değerlendirme proje verilerinde tanımlanmamıştır."
    return " ".join(sentences)


def aktif_fay_satirlari(veri):
    rows = []
    for item in rapor_bilgilerini_normalize_et(veri).get("aktif_faylar", []):
        if not isinstance(item, dict):
            continue
        name = _text(item.get("ad"))
        distance = _text(item.get("uzaklik_km"))
        magnitude = _text(item.get("buyukluk"))
        if name or distance or magnitude:
            rows.append([name or "-", distance or "-", magnitude or "-"])
    return rows


def aktif_tektonik_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    if data["aktif_tektonik_aciklama"]:
        return _sentence(data["aktif_tektonik_aciklama"])
    if aktif_fay_satirlari(veri):
        return (
            "Çalışma alanının aktif tektonik özellikleri güncel diri fay verileri "
            "kullanılarak değerlendirilmiş; yakın faylar aşağıdaki tabloda sunulmuştur."
        )
    return "Aktif tektonik ve yakın diri fay bilgileri proje verilerinde tanımlanmamıştır."


def sondaj_arazi_giris_metni(veri):
    veri = veri if isinstance(veri, dict) else {}
    sondajlar = veri.get("sondaj", []) or []
    sentences = [_sondaj_ozeti(sondajlar)]
    if sondajlar:
        sentences.append("Sondaj çalışmaları TS EN ISO 22475-1 standardı esas alınarak yürütülmüştür.")
    if any(s.get("spt") for s in sondajlar if isinstance(s, dict)):
        sentences.append("SPT deneyleri TS EN ISO 22476-3 standardına göre değerlendirilmiştir.")
    if any(s.get("pmt") for s in sondajlar if isinstance(s, dict)):
        sentences.append("Presiyometre deneyleri ilgili sondaj ve derinliklerde gerçekleştirilmiştir.")
    if any(s.get("kaya") for s in sondajlar if isinstance(s, dict)):
        sentences.append("Karotlu ilerlemelerde TCR, SCR ve RQD değerleri kaydedilmiştir.")
    return " ".join(sentences)


def jeofizik_arazi_giris_metni(veri):
    _kunye, _arazi, _bina, jeofizik, _ayarlar = _project_parts(veri)
    ss_list = jeofizik.get("ss_list", []) or []
    mt_list = jeofizik.get("mt_list", []) or []
    date = _text(jeofizik.get("tarih"))
    methods = []
    if ss_list:
        methods.append(f"{len(ss_list)} sismik serim üzerinde Sismik Kırılma ve MASW")
    if mt_list:
        methods.append(f"{len(mt_list)} noktada Mikrotremör")
    if not methods:
        return "Proje verilerinde jeofizik arazi çalışması kaydı bulunmamaktadır."
    date_text = f"{date} tarihinde " if date else ""
    return (
        f"Jeofizik çalışmalar kapsamında {date_text}{' ve '.join(methods)} ölçümleri "
        "gerçekleştirilmiştir. Ölçüm sonuçları ilgili tablo ve eklerde sunulmuştur."
    )


def _device_text(data, key, fallback=""):
    value = _text(data.get(key))
    return value or fallback


def sismik_yontem_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    device = _device_text(data, "sismik_cihaz", "sismik ölçü sistemi")
    channel = _device_text(data, "sismik_kanal_sayisi")
    channel_text = f" {channel} kanallı" if channel else ""
    source = _device_text(data, "sismik_kaynak")
    source_text = f" Sismik kaynak olarak {source} kullanılmıştır." if source else ""
    return (
        f"Sismik kırılma ölçümleri{channel_text} {device} ile gerçekleştirilmiştir. "
        "Çalışmada tabakaların P dalgası hızlarının ve dinamik özelliklerinin "
        f"belirlenmesi amaçlanmıştır.{source_text} Ölçüm parametreleri ilgili "
        "tabloda verilmiştir."
    )


def masw_yontem_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    device = _device_text(data, "sismik_cihaz", "sismik ölçü sistemi")
    geophone = _device_text(data, "jeofon_frekansi")
    source = _device_text(data, "sismik_kaynak")
    details = []
    if geophone:
        details.append(f"{geophone} jeofonlar")
    if source:
        details.append(source)
    detail_text = f" Veri toplamada {' ve '.join(details)} kullanılmıştır." if details else ""
    return (
        "MASW yöntemi ile Rayleigh dalgası dispersiyon eğrileri elde edilmiş ve "
        f"ters çözüm sonucunda S dalgası hız modeli oluşturulmuştur. Ölçümler {device} "
        f"ile gerçekleştirilmiştir.{detail_text}"
    )


def mt_yontem_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    device = _device_text(data, "mt_cihaz", "üç bileşenli sismometre")
    return (
        f"Mikrotremör ölçümleri {device} kullanılarak, arazi koşullarını temsil "
        "edecek noktalarda gerçekleştirilmiştir."
    )


def mt_degerlendirme_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    duration = _text(data.get("mt_kayit_suresi_dk"))
    software = _text(data.get("mt_degerlendirme_yazilimi"))
    parts = []
    if duration:
        parts.append(f"yaklaşık {duration} dakikalık üç bileşenli kayıtlar alınmış")
    else:
        parts.append("üç bileşenli kayıtlar alınmış")
    if software:
        parts.append(f"kayıtlar {software} yazılımı ile değerlendirilmiştir")
    else:
        parts.append("kayıtlar spektral oran yöntemiyle değerlendirilmiştir")
    return (
        f"Ölçüm noktalarında {parts[0]} ve {parts[1]}. Değerlendirme sonucunda "
        "baskın frekans, baskın periyot ve H/V oranları belirlenmiştir."
    )


def arastirma_cukuru_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    if data["arastirma_cukuru_aciklamasi"]:
        return _sentence(data["arastirma_cukuru_aciklamasi"])
    if data["arastirma_cukuru_durumu"] == "Yapıldı":
        return "Çalışma alanında araştırma çukuru çalışması yapılmıştır."
    if data["arastirma_cukuru_durumu"] == "Yapılmadı":
        return "Çalışma alanında araştırma çukuru kazılmamıştır."
    return "Araştırma çukuru çalışmasına ilişkin bilgi proje verilerinde tanımlanmamıştır."


def sondaj_bolum_giris_metni(veri):
    sondajlar = veri.get("sondaj", []) if isinstance(veri, dict) else []
    if not sondajlar:
        return "Proje verilerinde sondaj kaydı bulunmamaktadır."
    return (
        f"{_sondaj_ozeti(sondajlar)} Sondaj profilleri, koordinatları ve arazi deneyleri "
        "ilgili tablo, şekil ve eklerde sunulmuştur."
    )


def spt_giris_metni(veri):
    sondajlar = veri.get("sondaj", []) if isinstance(veri, dict) else []
    count = sum(len(s.get("spt", []) or []) for s in sondajlar if isinstance(s, dict))
    if not count:
        return "Proje verilerinde SPT deney kaydı bulunmamaktadır."
    return (
        f"Çalışma alanındaki sondajlarda toplam {count} SPT deney kaydı bulunmaktadır. "
        "Deneyler TS EN ISO 22476-3 standardına göre değerlendirilmiş ve sonuçlar "
        "aşağıdaki tabloda verilmiştir."
    )


def spt_teknik_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    _kunye, _arazi, _bina, _jeofizik, settings = _project_parts(veri)
    diameter = _text(settings.get("delgi_capi"))
    hammer = _text(settings.get("spt_sahmerdan"))
    parts = []
    if diameter:
        parts.append(f"sondaj kuyu çapı {diameter}")
    if data["spt_tij_boyu_m"]:
        parts.append(f"kuyu üzerinde kalan tij boyu {data['spt_tij_boyu_m']} m")
    if hammer:
        parts.append(f"deney düzeneği {hammer}")
    if data["spt_enerji_orani"]:
        parts.append(f"enerji oranı %{data['spt_enerji_orani']}")
    if data["spt_numune_alici"]:
        parts.append(data["spt_numune_alici"])
    if not parts:
        return "SPT deney düzeneğinin teknik özellikleri proje verilerinde tanımlanmamıştır."
    return "SPT deneylerinde " + ", ".join(parts) + " kullanılmıştır."


def laboratuvar_giris_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    if not _lab_ready(veri):
        return "Proje verilerinde laboratuvar deney sonucu bulunmamaktadır."
    lab = data["laboratuvar_adi"]
    authority = data["laboratuvar_yetki_aciklamasi"]
    lab_text = f"{lab} laboratuvarında" if lab else "yetkili laboratuvarda"
    sentences = [
        f"Sondajlardan alınan numuneler üzerinde gerekli deneyler {lab_text} gerçekleştirilmiştir."
    ]
    if authority:
        sentences.append(_sentence(authority))
    if data["laboratuvar_ek_no"]:
        sentences.append(f"Laboratuvar sonuçları {data['laboratuvar_ek_no']}'de sunulmuştur.")
    return " ".join(sentences)


def kesit_giris_metni(veri):
    sondajlar = veri.get("sondaj", []) if isinstance(veri, dict) else []
    if len(sondajlar or []) < 2:
        return "Jeolojik kesit oluşturmak için yeterli sayıda sondaj kaydı bulunmamaktadır."
    return (
        "Çalışma alanındaki seçili sondaj noktaları arasında jeolojik kesit "
        "oluşturulmuş ve sondaj profillerinde gözlenen birimler korele edilmiştir."
    )


def sonuc_giris_metni(veri):
    kunye, _arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    data = rapor_bilgilerini_normalize_et(veri)
    location = _konum_ozeti(kunye)
    project = data["proje_adi"] or "proje"
    if location:
        return (
            f"{location} konumundaki {project} için yürütülen zemin ve temel etüdü "
            "veri çalışmalarında elde edilen bulgular aşağıda özetlenmiştir."
        )
    return f"{project} için elde edilen zemin etüdü verileri aşağıda özetlenmiştir."


def sonuc_konum_metni(veri):
    kunye, arazi, _bina, _jeofizik, _ayarlar = _project_parts(veri)
    location = _konum_ozeti(kunye)
    coord_y = _text(arazi.get("alan_y"))
    coord_x = _text(arazi.get("alan_x"))
    text = f"İnceleme alanı {location} sınırlarında yer almaktadır" if location else "İnceleme alanının konum bilgileri tanımlanmamıştır"
    if coord_y and coord_x:
        text += f"; merkez koordinatı Enlem: {coord_y}, Boylam: {coord_x} (WGS84)'tür"
    return _sentence(text)


def sonuc_kazi_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    if not data["kazi_sinifi"] and not data["kazi_guclugu"]:
        return (
            "Kazı sınıfı ve kazı güçlüğü, veri raporundaki bulgular kullanılarak "
            "geoteknik rapor kapsamında değerlendirilmelidir."
        )
    parts = []
    if data["kazi_sinifi"]:
        parts.append(f"kazı sınıfı {data['kazi_sinifi']}")
    if data["kazi_guclugu"]:
        parts.append(f"kazı güçlüğü {data['kazi_guclugu']}")
    return _sentence("Çalışma alanı için " + ", ".join(parts) + " olarak değerlendirilmiştir")


def sonuc_kazi_onlem_metni(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    if data["kazi_aciklamasi"]:
        return _sentence(data["kazi_aciklamasi"])
    return (
        "Kazı destek sistemi, şev güvenliği, drenaj ve komşu parsel önlemleri "
        "geoteknik rapor ve uygulama projesi kapsamında belirlenmelidir."
    )


def rapor_metin_degerleri(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    _kunye, _arazi, bina, jeofizik, _ayarlar = _project_parts(veri)
    ss_var = bool(jeofizik.get("ss_list"))
    mt_var = bool(jeofizik.get("mt_list"))
    return {
        "[ETUT_AMAC_KAPSAM]": etut_amac_kapsam_metni(veri),
        "[RAPOR_KAPSAM]": rapor_kapsam_metni(veri),
        "[PARSEL_TANITIM]": parsel_tanitim_metni(veri),
        "[IMAR_PLANI_ACIKLAMA]": imar_plani_metni(veri),
        "[IMAR_ADASI_ACIKLAMA]": imar_adasi_metni(veri),
        "[IKLIM_ACIKLAMA]": iklim_metni(veri),
        "[DON_DURUM_ACIKLAMA]": don_durum_metni(veri),
        "[DOGAL_AFET_ACIKLAMA]": dogal_afet_metni(veri),
        "[AKTIF_TEKTONIK_ACIKLAMA]": aktif_tektonik_metni(veri),
        "[AKTIF_FAY_GIRIS]": (
            "Çalışma alanına yakın aktif faylara ilişkin proje bazlı bilgiler "
            "aşağıdaki tabloda verilmiştir."
            if aktif_fay_satirlari(veri)
            else "Yakın aktif fay mesafeleri proje verilerinde tanımlanmamıştır."
        ),
        "[SONDAJ_ARAZI_GIRIS]": sondaj_arazi_giris_metni(veri),
        "[JEOFIZIK_ARAZI_GIRIS]": jeofizik_arazi_giris_metni(veri),
        "[SISMIK_YONTEM_ACIKLAMA]": sismik_yontem_metni(veri),
        "[VP_ACIKLAMA]": (
            "Sismik kırılma kayıtlarından belirlenen P dalgası hızları aşağıdaki "
            "tabloda verilmiştir."
        ),
        "[MASW_YONTEM_ACIKLAMA]": masw_yontem_metni(veri),
        "[MASW_SONUC_ACIKLAMA]": (
            "MASW ölçümlerinden elde edilen dispersiyon değerlendirmeleri ve "
            "hesaplanan Vs30 değerleri ilgili şekil, tablo ve eklerde sunulmuştur."
        ),
        "[MT_YONTEM_ACIKLAMA]": mt_yontem_metni(veri),
        "[MT_DEGERLENDIRME_ACIKLAMA]": mt_degerlendirme_metni(veri),
        "[MT_REZONANS_ACIKLAMA]": (
            "Mikrotremör ölçümlerinden belirlenen baskın periyot değerleri, yapı "
            "periyotlarıyla birlikte geoteknik rapor kapsamında değerlendirilmelidir."
        ),
        "[ARASTIRMA_CUKURU_ACIKLAMA]": arastirma_cukuru_metni(veri),
        "[SONDAJ_BOLUM_GIRIS]": sondaj_bolum_giris_metni(veri),
        "[SPT_GIRIS]": spt_giris_metni(veri),
        "[SPT_TEKNIK_ACIKLAMA]": spt_teknik_metni(veri),
        "[LAB_GIRIS]": laboratuvar_giris_metni(veri),
        "[LAB_FIZIK_GIRIS]": (
            "Laboratuvar sonuçlarında bulunan indeks ve fiziksel özellik deneyleri "
            "birim bazında değerlendirilmiştir."
        ),
        "[LAB_MEKANIK_GIRIS]": (
            "Laboratuvar sonuçlarında bulunan mekanik özellik deneyleri birim "
            "bazında değerlendirilmiştir."
        ),
        "[KESIT_GIRIS]": kesit_giris_metni(veri),
        "[SONUC_GIRIS]": sonuc_giris_metni(veri),
        "[SONUC_KONUM]": sonuc_konum_metni(veri),
        "[SONUC_IMAR]": imar_plani_metni(veri),
        "[SONUC_AFET]": dogal_afet_metni(veri),
        "[SONUC_KAZI]": sonuc_kazi_metni(veri),
        "[SONUC_KAZI_ONLEM]": sonuc_kazi_onlem_metni(veri),
        "[SONUC_EK_ACIKLAMA]": _sentence(data["sonuc_ek_aciklama"]),
        "[ILGILI_IDARE]": data["ilgili_idare"] or "-",
        "[RAPOR_TARIHI]": rapor_tarihi(veri),
        "[RAPOR_AY_YIL]": rapor_ay_yil(veri),
        "[RAPOR_NO]": data["rapor_no"] or "-",
        "[YAPI_SAHIBI]": data["yapi_sahibi"] or "-",
        "[PROJE_ADI]": data["proje_adi"] or "-",
        "[S3_PROJE_ADI]": data["proje_adi"] or "-",
        "[MT_VAR]": "1" if mt_var else "0",
        "[SS_VAR]": "1" if ss_var else "0",
        "[BINA_VAR]": "1" if bool(bina) else "0",
    }


def rapor_bilgileri_eksikleri(veri):
    data = rapor_bilgilerini_normalize_et(veri)
    missing = []
    required = (
        ("proje_adi", "Proje adı"),
        ("yapi_sahibi", "Yapı sahibi"),
        ("ilgili_idare", "İlgili idare"),
        ("rapor_tarihi", "Rapor tarihi"),
        ("plan_adi", "İmar planı / plan notu"),
    )
    for key, label in required:
        if not data.get(key):
            missing.append(label)
    if not data.get("yol_cepheleri"):
        missing.append("Yol ve cephe durumu")
    if not data.get("komsu_parseller"):
        missing.append("Komşu parsel bilgileri")
    return missing


__all__ = [
    "ARASTIRMA_CUKURU_SECENEKLERI",
    "DURUM_SECENEKLERI",
    "PARSEL_TIPI_SECENEKLERI",
    "RAPOR_BILGILERI_DEFAULT",
    "RAPOR_METIN_ETIKETLERI",
    "aktif_fay_satirlari",
    "rapor_ay_yil",
    "rapor_bilgileri_eksikleri",
    "rapor_bilgileri_varsayilanlari",
    "rapor_bilgilerini_normalize_et",
    "rapor_metin_degerleri",
    "rapor_proje_adi",
    "rapor_tarihi",
    "rapor_yapi_sahibi",
]
