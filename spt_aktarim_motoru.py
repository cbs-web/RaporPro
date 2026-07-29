# Dosya: RaporPro/spt_aktarim_motoru.py
from copy import deepcopy
import datetime

from spt_okuma_motoru import normalize_sondaj_no
from workbook_motoru import yeni_sondaj_sablonu
from yardimcilar import safe_float


def spt_aktarim_bilinmeyen_sondajlar(veri, kayitlar):
    mevcut = {
        normalize_sondaj_no(sondaj.get("no"))
        for sondaj in (veri or {}).get("sondaj", [])
        if sondaj.get("no")
    }
    return sorted({
        normalize_sondaj_no(kayit.sondaj_no)
        for kayit in kayitlar or []
        if normalize_sondaj_no(kayit.sondaj_no)
        and normalize_sondaj_no(kayit.sondaj_no) not in mevcut
    })


def spt_aktarim_plani_olustur(
    veri,
    kayitlar,
    ayni_derinligi_guncelle=True,
    once_temizle=False,
    eksik_sondaj_olustur=False,
):
    """SPT aktarimini asil proje verisine dokunmadan kopya uzerinde planla."""
    sondajlar = deepcopy((veri or {}).get("sondaj", []))
    by_no = {
        normalize_sondaj_no(sondaj.get("no")): sondaj
        for sondaj in sondajlar
        if normalize_sondaj_no(sondaj.get("no"))
    }
    stats = {"created": 0, "added": 0, "updated": 0, "skipped": 0}
    islemler = []
    bilinmeyen = []
    gecerli_kayitlar = []

    for kayit in kayitlar or []:
        no = normalize_sondaj_no(getattr(kayit, "sondaj_no", ""))
        depth = safe_float(getattr(kayit, "derinlik", ""))
        if not no or depth <= 0:
            stats["skipped"] += 1
            islemler.append({"islem": "atlandi", "neden": "sondaj veya derinlik eksik"})
            continue
        if no not in by_no:
            if not eksik_sondaj_olustur:
                bilinmeyen.append(no)
                stats["skipped"] += 1
                islemler.append({"islem": "atlandi", "sondaj": no, "neden": "sondaj projede yok"})
                continue
            sondaj = yeni_sondaj_sablonu(len(sondajlar))
            sondaj["no"] = no
            sondajlar.append(sondaj)
            by_no[no] = sondaj
            stats["created"] += 1
            islemler.append({"islem": "sondaj_olusturuldu", "sondaj": no})
        gecerli_kayitlar.append((kayit, no, depth))

    if once_temizle:
        for no in sorted({no for _kayit, no, _depth in gecerli_kayitlar}):
            sondaj = by_no[no]
            sondaj["spt"] = []
            sondaj["spt_kaynaklari"] = []
            islemler.append({"islem": "temizlendi", "sondaj": no})

    for kayit, no, target_depth in gecerli_kayitlar:
        sondaj = by_no[no]
        spt_list = sondaj.setdefault("spt", [])
        existing_idx = next(
            (
                idx for idx, existing in enumerate(spt_list)
                if existing and abs(safe_float(existing[0]) - target_depth) <= 0.01
            ),
            None,
        )
        if existing_idx is not None:
            if not ayni_derinligi_guncelle:
                stats["skipped"] += 1
                islemler.append({
                    "islem": "atlandi",
                    "sondaj": no,
                    "derinlik": kayit.derinlik,
                    "neden": "ayni derinlik mevcut",
                })
                continue
            spt_list[existing_idx] = kayit.spt_satiri()
            stats["updated"] += 1
            islem = "guncellendi"
        else:
            spt_list.append(kayit.spt_satiri())
            stats["added"] += 1
            islem = "eklendi"
        spt_list.sort(key=lambda item: safe_float(item[0]) if item else 9999)

        kaynaklar = sondaj.setdefault("spt_kaynaklari", [])
        kaynaklar[:] = [
            item for item in kaynaklar
            if abs(safe_float(item.get("derinlik")) - target_depth) > 0.01
        ]
        kaynaklar.append({
            "derinlik": kayit.derinlik,
            "kaynak": kayit.kaynak,
            "kaynak_yolu": kayit.kaynak_yolu,
            "guven": kayit.guven,
            "kaynak_hash": str(getattr(kayit, "raw", {}).get("kaynak_hash", "")),
            "motor": str(getattr(kayit, "raw", {}).get("motor", "")),
            "model": str(getattr(kayit, "raw", {}).get("model", "")),
            "aktarim_tarihi": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        })
        islemler.append({"islem": islem, "sondaj": no, "derinlik": kayit.derinlik})

    return {
        "sondajlar": sondajlar,
        "stats": stats,
        "islemler": islemler,
        "bilinmeyen_sondajlar": sorted(set(bilinmeyen)),
    }
