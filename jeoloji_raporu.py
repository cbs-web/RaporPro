# Dosya: RaporPro/jeoloji_raporu.py
"""Proje jeolojik birimlerini ve Word raporu metinlerini yonetir."""

from __future__ import annotations

import re
import unicodedata


KONUM_INCELEME_ALANI = "inceleme_alani"
KONUM_YAKIN_CEVRE = "yakin_cevre"
KONUM_HER_IKISI = "her_ikisi"

DURUM_BELIRTILMEDI = "belirtilmedi"
DURUM_REZIDUEL = "reziduel"
DURUM_ANA_KAYA = "ana_kaya"
DURUM_ALUVYON = "aluvyon"
DURUM_DOLGU = "dolgu"

JEOLOJI_KONUM_SECENEKLERI = {
    KONUM_INCELEME_ALANI: "İnceleme alanı",
    KONUM_YAKIN_CEVRE: "Yakın çevre",
    KONUM_HER_IKISI: "İnceleme alanı ve yakın çevre",
}

JEOLOJI_DURUM_SECENEKLERI = {
    DURUM_BELIRTILMEDI: "Belirtilmedi",
    DURUM_REZIDUEL: "Rezidüel",
    DURUM_ANA_KAYA: "Ana kaya",
    DURUM_ALUVYON: "Alüvyon",
    DURUM_DOLGU: "Dolgu",
}


JEOLOJI_BIRIM_KATALOGU = {
    "Qal": {
        "ad": "Alüvyon",
        "yas": "Kuvaterner",
        "aciklamalar": [
            "Akarsu yataklarında, eski çukurluklar üzerinde ve kıyı kuşaklarındaki "
            "düzlükler üzerinde gelişmiş çakıl, kum ve çamur çökelleridir.",
        ],
    },
    "Tmal": {
        "ad": "Alçıtepe Üyesi",
        "yas": "Geç Miyosen",
        "aciklamalar": [
            "Biga Yarımadası'nda İntepe-Çanakkale arasındaki yükseltilerde, Gelibolu "
            "Yarımadası'nda ise Eceabat güneyinde yüzeylenen ve başlıca "
            "kireçtaşlarından oluşan litoloji topluluğu ilk olarak Druitt (1961) "
            "tarafından Alçıtepe birimi olarak tanımlanmıştır. Bu çalışmada da "
            "Alçıtepe üyesi adı kabul edilmiştir.",
            "Alçıtepe üyesinin tip kesit yeri, Umurbey kasabası güneyindeki "
            "Tekkedere ile Çardakbayırı Tepe arasındadır. Ayrıca Kuzgunkaya Tepe'de "
            "de referans kesiti bulunmaktadır.",
            "Alçıtepe üyesi stromatolit yapılı kireçtaşlarından, oolitlerden, "
            "kalkarenitlerden, fosilli kireçtaşları ile silttaşı ve marnlardan "
            "oluşur. Yaşı Geç Miyosen (orta-geç Panoniyen) olarak saptanmıştır "
            "(Atabey ve diğerleri, 2004). Alçıtepe üyesi gelgit ortamında çökelen "
            "karbonat fasiyeslerini yansıtır.",
        ],
    },
    "Tmçd": {
        "ad": "Çamrakdere Üyesi",
        "yas": "Geç Miyosen",
        "aciklamalar": [
            "Çanakkale Boğazı'nın her iki kıyısında yüzeylenen ve çamurtaşı, "
            "silttaşı, kumtaşı ve çakılcıklı konglomera ile kalkarenitten oluşan "
            "kayaç topluluğu ilk defa Şentürk ve Karaköse (1987) tarafından "
            "Çanakkale formasyonunun Çamrakdere üyesi olarak adlandırılmıştır. Bu "
            "çalışmada da Çanakkale formasyonunun bir üyesi olarak tanımlanan aynı "
            "kayaç toplulukları Çamrakdere üyesi olarak tanımlanmıştır.",
            "Çamrakdere üyesi çamurtaşı, silttaşı, kumtaşı ve çakılcıklı konglomera "
            "ile kalkarenitten oluşmaktadır. Gri-yeşil renkli çamurtaşları, bol "
            "miktarda fosil ya da kırılmış kavkı parçası içerirler. Bunun yanı sıra "
            "kömürleşmiş bitki sap-kök izleri ile kaliş yumruları da çamurtaşları "
            "içinde gözlenmektedir. Çamurtaşları içinde genelde birkaç mm-cm "
            "kalınlıkta lentiküler tabakalı kumtaşları yer almaktadır. Kumtaşları "
            "düzlemsel paralel katmanlı ve ripıl çapraz katmanlı olarak "
            "gözlenmektedir. Bu kumtaşları flaser ve dalgalı çamurtaşları ile "
            "ardalanmalı olarak bulunmaktadır. Bol miktarda kırılmış kavkı parçası "
            "içeren kumtaşları ve çakılcıklı konglomeralar, çamurtaşları ve "
            "kumtaşları üzerinde erozyonal taban yüzeyli olarak düzlemsel eğimli "
            "tabakalanmalar şeklinde dirsek barı çökellerini oluştururlar. Genelde "
            "ince tabakalı olarak gözlenen kalkarenitler, fosil ve kavkı "
            "parçalarınca zengindir.",
            "Çamrakdere üyesi yanal yönde Kirazlı üyesi ve düşey yönde ise "
            "Alçıtepe üyesine ait kayaçlarla geçişlidir. Altında yer alan "
            "Gazhanedere formasyonu ile paralel uyumsuzdur ve üyenin yaşı Geç "
            "Miyosen (orta-geç Panoniyen) olarak saptanmıştır (Atabey ve diğerleri, "
            "2004).",
        ],
    },
    "Tmki": {
        "ad": "Kirazlı Üyesi",
        "yas": "Geç Miyosen",
        "aciklamalar": [
            "Gazhanedere formasyonu üzerinde yer alan ve egemen olarak ufak-kaba "
            "taneli kumtaşı ile daha az oranda çakılcık-ufak çakıllı konglomera, "
            "silttaşı ve çamurtaşından oluşan denizel birim Saltık (1974) tarafından "
            "Kirazlı formasyonu olarak tanımlanmıştır. Benzer fasiyes özelliklerine "
            "sahip olan kayaç toplulukları Biga ve Gelibolu Yarımadaları'nda da "
            "yüzeylenmekte olup Çanakkale formasyonu içinde tanımlanan diğer fasiyes "
            "toplulukları ile ardalanmalı olarak bulunmaktadır. Dolayısıyla "
            "Çanakkale Boğazı kıyısında yüzeylenen sığ denizel kayaçlar bu çalışmada "
            "Çanakkale formasyonunun bir üyesi olarak tanımlanmış ve birimin "
            "tanımlandığı ilk isme atfen Kirazlı üyesi adı kabul edilmiştir.",
            "Kirazlı üyesi Çanakkale güneyinde yaygın olarak Güzelyalı, İntepe, "
            "Kumkale arasındaki kıyı şeridinde, Gelibolu Yarımadası'nda ise Üre Dağı "
            "batısı ile Çamaltı-Palamut Burnu arasında yüzeylenmektedir. Biga "
            "Yarımadası'nda üyenin tip kesit yeri Güzelyalı ile İntepe arasında kalan "
            "karayolu yarmasıdır.",
        ],
    },
    "Tmçk": {
        "ad": "Çanakkale Formasyonu",
        "yas": "Geç Miyosen",
        "aciklamalar": [
            "Biga ve Gelibolu Yarımadaları'nda Çanakkale Boğazı'nın her iki kıyısı "
            "boyunca yüzeylenen Geç Miyosen yaşlı denizel çökeller ilk kez Şentürk "
            "ve Karaköse (1987) tarafından Çanakkale formasyonu olarak "
            "tanımlanmıştır. Çanakkale formasyonu çakıltaşı, kumtaşı, silttaşı, "
            "çamurtaşı, marn, kalkarenit ve oolitik kireçtaşlarından oluşur.",
            "Çanakkale formasyonu olarak adlandırılan Geç Miyosen yaşlı denizel "
            "kayaçlar Trakya ve Gelibolu Yarımadası'nda değişik araştırmacılar "
            "tarafından pek çok farklı ad altında tanımlanmıştır. Çanakkale "
            "formasyonu Holmes (1966)'un Ergene formasyonu; Ünal (1967)'ın Ergene "
            "Grubu, Büyük Anafartalar formasyonu; Kellog (1973)'un Anafartalar ve "
            "Kilitbahir formasyonu; Saltık (1974)'ın Gelibolu formasyonu; Önem "
            "(1974)'in Eceabat formasyonu karşılığıdır.",
        ],
    },
}


def jeoloji_varsayilanlari():
    """Yeni ve eski projeler için güvenli jeoloji veri yapısını döndür."""
    return {
        "birimler": [],
        "harita_formasyon_onerisi": "",
    }


def _ascii_key(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


_KOD_ESLEME = {
    _ascii_key(code): code
    for code in JEOLOJI_BIRIM_KATALOGU
}


def jeoloji_kodu_normalize(value):
    """Bilinen kodların ASCII/Türkçe yazım farklarını tek biçime getir."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    return _KOD_ESLEME.get(_ascii_key(raw), raw)


def _bool_value(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().casefold() not in {"0", "false", "hayır", "hayir", "yok"}


def jeoloji_birim_kaydini_normalize(record):
    """Bir jeolojik birim kaydını katalog bilgileriyle tamamla."""
    if isinstance(record, str):
        record = {"kod": record}
    if not isinstance(record, dict):
        return None

    kod = jeoloji_kodu_normalize(record.get("kod"))
    katalog = JEOLOJI_BIRIM_KATALOGU.get(kod, {})
    ad = str(record.get("ad") or katalog.get("ad") or "").strip()
    if not kod and not ad:
        return None

    konum = str(record.get("konum") or KONUM_INCELEME_ALANI).strip()
    if konum not in JEOLOJI_KONUM_SECENEKLERI:
        konum = KONUM_INCELEME_ALANI

    durum = str(record.get("durum") or DURUM_BELIRTILMEDI).strip()
    if durum not in JEOLOJI_DURUM_SECENEKLERI:
        durum = DURUM_BELIRTILMEDI

    return {
        "kod": kod,
        "ad": ad,
        "yas": str(record.get("yas") or katalog.get("yas") or "").strip(),
        "konum": konum,
        "durum": durum,
        "kesitte_kullan": _bool_value(record.get("kesitte_kullan"), default=True),
        "ozel_aciklama": str(record.get("ozel_aciklama") or "").strip(),
    }


def _konumlari_birlestir(first, second):
    if first == second:
        return first
    if KONUM_HER_IKISI in {first, second}:
        return KONUM_HER_IKISI
    return KONUM_HER_IKISI


def jeoloji_birimleri(veri):
    """Proje veya jeoloji sözlüğündeki birimleri sıralı ve tekrarsız döndür."""
    if not isinstance(veri, dict):
        return []
    jeoloji = veri.get("jeoloji") if isinstance(veri.get("jeoloji"), dict) else veri
    records = jeoloji.get("birimler", []) if isinstance(jeoloji, dict) else []
    result = []
    index_by_key = {}

    for raw in records if isinstance(records, list) else []:
        record = jeoloji_birim_kaydini_normalize(raw)
        if not record:
            continue
        key = _ascii_key(record["kod"] or record["ad"])
        if key in index_by_key:
            current = result[index_by_key[key]]
            current["konum"] = _konumlari_birlestir(current["konum"], record["konum"])
            current["kesitte_kullan"] = (
                current["kesitte_kullan"] or record["kesitte_kullan"]
            )
            if current["durum"] == DURUM_BELIRTILMEDI:
                current["durum"] = record["durum"]
            if not current["ozel_aciklama"]:
                current["ozel_aciklama"] = record["ozel_aciklama"]
            continue
        index_by_key[key] = len(result)
        result.append(record)
    return result


def jeoloji_birim_etiketi(record):
    """Birim adı ve kodunu raporda kullanılacak biçimde döndür."""
    record = jeoloji_birim_kaydini_normalize(record) or {}
    ad = record.get("ad", "")
    kod = record.get("kod", "")
    if ad and kod:
        return f"{ad} ({kod})"
    return ad or kod


def _liste_metni(values):
    clean = [str(value).strip() for value in values if str(value).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} ve {clean[1]}"
    return f"{', '.join(clean[:-1])} ve {clean[-1]}"


def _konum_gruplari(records):
    return {
        "ortak": [r for r in records if r["konum"] == KONUM_HER_IKISI],
        "alan": [r for r in records if r["konum"] == KONUM_INCELEME_ALANI],
        "cevre": [r for r in records if r["konum"] == KONUM_YAKIN_CEVRE],
    }


def _durumlu_birim_ifadesi(record, yas_ekle=False):
    record = jeoloji_birim_kaydini_normalize(record) or {}
    label = jeoloji_birim_etiketi(record)
    durum = record.get("durum")
    if durum == DURUM_REZIDUEL:
        ifade = f"{label} birimine ait rezidüel zeminler"
    elif durum == DURUM_ANA_KAYA:
        ifade = f"{label} ana kaya birimi"
    elif durum == DURUM_ALUVYON:
        ifade = f"{label} çökelleri"
    elif durum == DURUM_DOLGU:
        ifade = f"{label} dolgu birimi"
    else:
        ifade = f"{label} birimi"
    yas = record.get("yas", "")
    return f"{yas} yaşlı {ifade}" if yas_ekle and yas else ifade


def _intro_bloklari(records, bolge_haritasi=False):
    if not records:
        text = "İnceleme alanının literatür jeolojisi proje verilerinde tanımlanmamıştır."
        if bolge_haritasi:
            text += " Bölgenin genel jeoloji haritası Şekil 5'te verilmiştir."
        return [{"tur": "metin", "metin": text}]

    groups = _konum_gruplari(records)
    parts = []
    if groups["ortak"]:
        labels = _liste_metni(
            _durumlu_birim_ifadesi(record, yas_ekle=True)
            for record in groups["ortak"]
        )
        parts.append(
            f"İnceleme alanı ve yakın çevresinde literatür verilerine göre {labels} bulunmaktadır."
        )
    if groups["alan"]:
        labels = _liste_metni(
            _durumlu_birim_ifadesi(record, yas_ekle=True)
            for record in groups["alan"]
        )
        parts.append(
            f"İnceleme alanında literatür verilerine göre {labels} bulunmaktadır."
        )
    if groups["cevre"]:
        labels = _liste_metni(
            _durumlu_birim_ifadesi(record, yas_ekle=True)
            for record in groups["cevre"]
        )
        parts.append(
            f"İnceleme alanının yakın çevresinde literatür verilerine göre {labels} yüzeylenmektedir."
        )
    if bolge_haritasi:
        parts.append("Bölgenin genel jeoloji haritası Şekil 5'te verilmiştir.")
    return [{"tur": "metin", "metin": " ".join(parts)}]


def _birim_aciklama_bloklari(records):
    blocks = []
    for record in records:
        label = jeoloji_birim_etiketi(record)
        if label:
            blocks.append({"tur": "birim_basligi", "metin": label})
        katalog = JEOLOJI_BIRIM_KATALOGU.get(record.get("kod"), {})
        for text in katalog.get("aciklamalar", []):
            blocks.append({"tur": "metin", "metin": text})
        custom = record.get("ozel_aciklama", "")
        for text in re.split(r"\n\s*\n", custom):
            if text.strip():
                blocks.append({"tur": "metin", "metin": text.strip()})
    return blocks


def jeoloji_rapor_bloklari(veri):
    """Raporun jeoloji bölümleri için biçim bilgili metin blokları üret."""
    records = jeoloji_birimleri(veri)
    study_records = [
        record
        for record in records
        if record["konum"] in {KONUM_INCELEME_ALANI, KONUM_HER_IKISI}
    ]
    section_records = [
        record
        for record in study_records
        if record.get("kesitte_kullan", True)
    ]

    bolgesel_giris = _intro_bloklari(records, bolge_haritasi=True)
    bolgesel_birimler = _birim_aciklama_bloklari(records)
    bolgesel = bolgesel_giris + bolgesel_birimler

    muhendislik = _intro_bloklari(records)

    if section_records:
        section_labels = _liste_metni(
            _durumlu_birim_ifadesi(record)
            for record in section_records
        )
        kesit = [
            {
                "tur": "metin",
                "metin": (
                    "Jeolojik kesitin oluşturulmasında çalışma alanında tanımlanan "
                    f"{section_labels} esas alınmıştır."
                ),
            }
        ]
        kesit.extend(_birim_aciklama_bloklari(section_records))
    else:
        kesit = [
            {
                "tur": "metin",
                "metin": (
                    "Jeolojik kesitte kullanılacak literatür birimi proje "
                    "verilerinde tanımlanmamıştır."
                ),
            }
        ]

    if study_records:
        sonuc_labels = _liste_metni(
            _durumlu_birim_ifadesi(record, yas_ekle=True)
            for record in study_records
        )
        sonuc = [
            {
                "tur": "metin",
                "metin": (
                    "İnceleme alanında literatür verilerine göre "
                    f"{sonuc_labels} bulunmaktadır."
                ),
            }
        ]
        mt_labels = _liste_metni(
            jeoloji_birim_etiketi(record)
            for record in study_records
        )
        mt = [
            {
                "tur": "metin",
                "metin": (
                    "İnceleme alanında yapılan mikrotremör ölçümlerinde "
                    f"{mt_labels} için ölçülen değerler Tablo 9'da verilmiştir."
                ),
            }
        ]
    else:
        sonuc = [
            {
                "tur": "metin",
                "metin": (
                    "İnceleme alanının literatür jeolojisi proje verilerinde "
                    "tanımlanmamıştır."
                ),
            }
        ]
        mt = [
            {
                "tur": "metin",
                "metin": (
                    "İnceleme alanında yapılan mikrotremör ölçümlerinden elde "
                    "edilen değerler Tablo 9'da verilmiştir."
                ),
            }
        ]

    return {
        "bolgesel": bolgesel,
        "bolgesel_giris": bolgesel_giris,
        "bolgesel_birimler": bolgesel_birimler,
        "muhendislik": muhendislik,
        "kesit": kesit,
        "sonuc": sonuc,
        "mt": mt,
    }


def jeoloji_rapor_metinleri(veri):
    """Arayüz önizlemesi için rapor bloklarını düz metin listelerine çevir."""
    return {
        key: [block["metin"] for block in blocks if block.get("metin")]
        for key, blocks in jeoloji_rapor_bloklari(veri).items()
    }


def jeoloji_kisa_formasyon_metni(veri):
    """Tablolarda kullanılacak kısa çalışma alanı formasyon bilgisini döndür."""
    records = [
        record
        for record in jeoloji_birimleri(veri)
        if record["konum"] in {KONUM_INCELEME_ALANI, KONUM_HER_IKISI}
    ]
    return _liste_metni(jeoloji_birim_etiketi(record) for record in records)


__all__ = [
    "DURUM_ALUVYON",
    "DURUM_ANA_KAYA",
    "DURUM_BELIRTILMEDI",
    "DURUM_DOLGU",
    "DURUM_REZIDUEL",
    "JEOLOJI_BIRIM_KATALOGU",
    "JEOLOJI_DURUM_SECENEKLERI",
    "JEOLOJI_KONUM_SECENEKLERI",
    "KONUM_HER_IKISI",
    "KONUM_INCELEME_ALANI",
    "KONUM_YAKIN_CEVRE",
    "jeoloji_birim_etiketi",
    "jeoloji_birim_kaydini_normalize",
    "jeoloji_birimleri",
    "jeoloji_kisa_formasyon_metni",
    "jeoloji_kodu_normalize",
    "jeoloji_rapor_bloklari",
    "jeoloji_rapor_metinleri",
    "jeoloji_varsayilanlari",
]
