"""Rapor düzeltme akışlarının ortak etiket kayıtları."""


DUZELTME_ETIKET_GRUPLARI = [
    (
        "Jeoloji",
        [
            ("[BOLGESEL_JEOLOJI]", "Bölgesel jeoloji açıklaması"),
            ("[BOLGESEL_JEOLOJI_BIRIMLERI]", "Bölgesel jeoloji birim açıklamaları"),
            ("[MUHENDISLIK_JEOLOJISI]", "Mühendislik jeolojisi açıklaması"),
            ("[JEOLOJIK_KESIT_ACIKLAMA]", "Jeolojik kesit birim açıklaması"),
            ("[JEOLOJI_SONUC]", "Jeoloji sonuç cümlesi"),
            ("[MT_BIRIM_METNI]", "Mikrotremör birim açıklaması"),
        ],
    ),
    (
        "Proje ve arazi",
        [
            ("[BINA_BILGILERI]", "Bina bilgileri"),
            ("[Sondaj]", "Sondaj / litoloji tablosu"),
            ("[YASS_TABLO]", "Yeraltı suyu tablosu"),
            ("[YASS_ONERI]", "Yeraltı suyu önerisi"),
            ("[HIDROJEOLOJI_DURUM]", "Hidrojeoloji durum açıklaması"),
        ],
    ),
    (
        "Laboratuvar ve arazi deneyleri",
        [
            ("[LAB_FIZIK]", "Laboratuvar fiziksel deneyler"),
            ("[LAB_MEKANIK]", "Laboratuvar mekanik deneyler"),
            ("[ZEMIN_OZET]", "Zemin parametre özeti"),
            ("[LITOLOJI_DAGILIM]", "Litoloji dağılımı"),
            ("[SPT]", "SPT tablosu"),
            ("[PMT]", "Presiyometre tablosu"),
            ("[KAYA_TABLO]", "Kaya / karot tablosu"),
        ],
    ),
    (
        "Jeofizik",
        [
            ("[JEO_PARAMETRE]", "Jeofizik parametre tablosu"),
            ("[MASW]", "MASW tablosu"),
            ("[VP]", "VP tablosu"),
            ("[JEO_KOOR]", "Jeofizik koordinatlar"),
            ("[MT_TABLO]", "Mikrotremör tablosu"),
            ("[JEO_SONUC]", "Jeofizik sonuç"),
        ],
    ),
    (
        "Görseller",
        [
            ("[RESIM_YERBULDURUR]", "Yerbuldurur haritası"),
            ("RESIM:TKGM", "TKGM görseli"),
            ("RESIM:PGA", "PGA görseli"),
            ("[RESIM_JEOFIZIK]", "Jeofizik lokasyon haritası"),
            ("[RESIM_MASW]", "MASW hız grafikleri"),
            ("RESIM:MJH", "Mühendislik jeolojisi haritası"),
            ("[RESIM_SONDAJ]", "Sondaj lokasyon haritası"),
        ],
    ),
]


DUZELTME_ETIKET_ADLARI = {
    tag: label
    for _group_title, items in DUZELTME_ETIKET_GRUPLARI
    for tag, label in items
}
