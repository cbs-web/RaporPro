# Dosya: RaporPro/tutarlilik_jeofizik.py
from jeofizik_sheet_motoru import (
    jeofizik_serim_anahtari,
    jeofizik_sheet_rows_to_ss_list,
    jeofizik_sheet_var_mi,
    jeofizik_ss_koordinatlarini_koru,
)
from tutarlilik_ortak import (
    bos_mu,
    bulgu_ekle,
    kimlik_anahtari,
    kontrol_ekle,
    koordinat_durumu,
    sayi_veya_none,
)


def jeofizik_kontrol(report, veri):
    problem_before = len(report.get("findings", []))
    jeofizik = veri.get("jeofizik", {}) if isinstance(veri.get("jeofizik", {}), dict) else {}
    manual_ss = list(jeofizik.get("ss_list", []) or [])
    sheet_ss = []
    if jeofizik_sheet_var_mi(veri):
        try:
            sheet_ss = jeofizik_sheet_rows_to_ss_list(veri.get("jeofizik_sheet", {}).get("rows", []))
            if sheet_ss and manual_ss:
                sheet_ss = jeofizik_ss_koordinatlarini_koru(sheet_ss, manual_ss)
        except Exception as exc:
            bulgu_ekle(
                report,
                "jeofizik.sheet.okuma",
                "warning",
                "Jeofizik",
                "Jeofizik Sheet",
                f"Jeofizik Sheet okunamadı: {exc}",
                "jeofizik",
                "Jeofizik Sheet başlıklarını ve satırlarını kontrol edin.",
            )
    ss_list = sheet_ss or manual_ss
    mt_list = list(jeofizik.get("mt_list", []) or [])
    has_geophysics = bool(ss_list or mt_list)
    kontrol_ekle(
        report,
        "jeofizik.kayit",
        "Jeofizik",
        "Jeofizik kaydı",
        has_geophysics,
        f"{len(ss_list)} serim, {len(mt_list)} MT kaydı" if has_geophysics else "SS/Serim veya MT kaydı yok.",
        "jeofizik",
        "Jeofizik sekmesinde çalışma verilerini tamamlayın.",
        failure_level="warning",
        weight=1,
    )
    if manual_ss and sheet_ss:
        manual_keys = {jeofizik_serim_anahtari(item.get("ad")) for item in manual_ss}
        sheet_keys = {jeofizik_serim_anahtari(item.get("ad")) for item in sheet_ss}
        if manual_keys != sheet_keys:
            bulgu_ekle(
                report,
                "jeofizik.sheet.manuel_fark",
                "warning",
                "Jeofizik",
                "Sheet-manuel serim eşleşmesi",
                "Jeofizik Sheet ile manuel SS/Serim listesi aynı çalışmaları içermiyor.",
                "jeofizik",
                "Sheet'i uygulayarak serim listesini güncelleyin veya isimleri eşitleyin.",
            )

    seen_ss = set()
    for idx, ss in enumerate(ss_list):
        name = str(ss.get("ad") or f"Serim {idx + 1}").strip()
        key = jeofizik_serim_anahtari(name)
        if key in seen_ss:
            bulgu_ekle(
                report,
                f"jeofizik.ss.{idx}.mukerrer",
                "error",
                "Jeofizik",
                "Mükerrer serim",
                f"Jeofizik listesinde tekrarlanan serim var: {name}.",
                "jeofizik",
                "Serim adlarını benzersiz yapın.",
                entity=name,
            )
        seen_ss.add(key)

        coords = list(ss.get("coords", []) or [])
        if len(coords) < 6:
            bulgu_ekle(
                report,
                f"jeofizik.ss.{idx}.koordinat_sayisi",
                "warning",
                "Jeofizik",
                "Serim koordinatları",
                f"{name}: başlangıç, orta ve bitiş için 3 koordinat çifti bulunmuyor.",
                "jeofizik",
                "Serimin üç koordinat çiftini tamamlayın.",
                entity=name,
            )
        padded = coords + [""] * max(0, 6 - len(coords))
        for pair_idx in range(3):
            ok, detail = koordinat_durumu(padded[pair_idx * 2], padded[pair_idx * 2 + 1])
            if not ok:
                bulgu_ekle(
                    report,
                    f"jeofizik.ss.{idx}.koordinat.{pair_idx}",
                    "warning",
                    "Jeofizik",
                    "Serim koordinatı",
                    f"{name} {pair_idx + 1}. koordinat: {detail}",
                    "jeofizik",
                    "Jeofizik koordinatlarını kontrol edin.",
                    entity=name,
                )

        layers = list(ss.get("layers", []) or [])
        if not layers:
            bulgu_ekle(
                report,
                f"jeofizik.ss.{idx}.tabaka",
                "warning",
                "Jeofizik",
                "Serim tabakaları",
                f"{name}: tabaka parametresi girilmemiş.",
                "jeofizik",
                "Vp, Vs ve tabaka kalınlıklarını girin.",
                entity=name,
            )
        for layer_idx, layer in enumerate(layers):
            vp = sayi_veya_none(layer.get("vp"))
            vs = sayi_veya_none(layer.get("vs"))
            h = sayi_veya_none(layer.get("h"))
            if vp is None or vp <= 0 or vs is None or vs <= 0:
                bulgu_ekle(
                    report,
                    f"jeofizik.ss.{idx}.tabaka.{layer_idx}.hiz",
                    "warning",
                    "Jeofizik",
                    "Vp/Vs değeri",
                    f"{name}: {layer_idx + 1}. tabaka Vp veya Vs değeri geçersiz.",
                    "jeofizik",
                    "Vp ve Vs değerlerini pozitif sayı olarak girin.",
                    entity=name,
                )
            elif vp <= vs:
                bulgu_ekle(
                    report,
                    f"jeofizik.ss.{idx}.tabaka.{layer_idx}.hiz_sirasi",
                    "warning",
                    "Jeofizik",
                    "Vp/Vs ilişkisi",
                    f"{name}: {layer_idx + 1}. tabakada Vp ({vp:g}) ≤ Vs ({vs:g}).",
                    "jeofizik",
                    "Vp ve Vs sütunlarının yerini ve değerlerini kontrol edin.",
                    entity=name,
                )
            if layer_idx < len(layers) - 1 and (h is None or h <= 0):
                bulgu_ekle(
                    report,
                    f"jeofizik.ss.{idx}.tabaka.{layer_idx}.kalinlik",
                    "warning",
                    "Jeofizik",
                    "Tabaka kalınlığı",
                    f"{name}: {layer_idx + 1}. tabaka kalınlığı geçersiz.",
                    "jeofizik",
                    "Son tabaka dışındaki kalınlıkları pozitif sayı olarak girin.",
                    entity=name,
                )

    seen_mt = set()
    for idx, mt in enumerate(mt_list):
        name = str(mt.get("no") or f"MT-{idx + 1}").strip()
        key = kimlik_anahtari(name)
        if key in seen_mt:
            bulgu_ekle(
                report,
                f"jeofizik.mt.{idx}.mukerrer",
                "error",
                "Jeofizik",
                "Mükerrer MT",
                f"Jeofizik listesinde tekrarlanan MT kaydı var: {name}.",
                "jeofizik",
                "MT adlarını benzersiz yapın.",
                entity=name,
            )
        seen_mt.add(key)
        ok, detail = koordinat_durumu(mt.get("y"), mt.get("x"))
        if not ok:
            bulgu_ekle(
                report,
                f"jeofizik.mt.{idx}.koordinat",
                "warning",
                "Jeofizik",
                "MT koordinatı",
                f"{name}: {detail}",
                "jeofizik",
                "MT koordinatını kontrol edin.",
                entity=name,
            )
        detail_fields = (
            ("freq", "Frekans"),
            ("to", "T0"),
            ("ta", "Ta"),
            ("tb", "Tb"),
            ("hv", "H/V"),
            ("sure", "Süre"),
        )
        missing_details = [label for key, label in detail_fields if bos_mu(mt.get(key))]
        if missing_details:
            bulgu_ekle(
                report,
                f"jeofizik.mt.{idx}.olcum_eksik",
                "warning",
                "Jeofizik",
                "MT ölçüm bilgileri",
                f"{name}: eksik ölçüm alanları: {', '.join(missing_details)}.",
                "jeofizik",
                "MT ölçüm bilgilerini tamamlayın.",
                entity=name,
            )
        else:
            invalid_details = [
                label
                for key, label in detail_fields
                if (sayi_veya_none(mt.get(key)) or 0) <= 0
            ]
            if invalid_details:
                bulgu_ekle(
                    report,
                    f"jeofizik.mt.{idx}.olcum_gecersiz",
                    "warning",
                    "Jeofizik",
                    "MT ölçüm değerleri",
                    f"{name}: pozitif sayı olması gereken alanlar: {', '.join(invalid_details)}.",
                    "jeofizik",
                    "MT ölçüm değerlerini pozitif sayı olarak girin.",
                    entity=name,
                )

    geophysics_ok = len(report["findings"]) == problem_before
    kontrol_ekle(
        report,
        "jeofizik.tutarlilik",
        "Jeofizik",
        "Jeofizik tutarlılığı",
        geophysics_ok if has_geophysics else False,
        "Jeofizik kayıtları tutarlı." if geophysics_ok and has_geophysics else "Jeofizik kayıtlarında eksik veya uyumsuz alan var.",
        "jeofizik",
        "Jeofizik bulgularını kontrol edin.",
        failure_level="warning",
        weight=1,
    )
