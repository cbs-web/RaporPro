import os
from collections import Counter

from yardimcilar import safe_float


def lab_sheet_ready(veri):
    rows = veri.get("lab_sheet", {}).get("rows", []) if isinstance(veri, dict) else []
    return any(any(str(cell).strip() for cell in row) for row in rows or [])


def proje_saglik_ozeti(veri, dosya_durumlari=None):
    dosya_durumlari = dosya_durumlari or {}
    items = []

    def add(label, ok, detail, target="ozet", suggestion=""):
        items.append({
            "label": label,
            "ok": bool(ok),
            "detail": detail,
            "target": target,
            "suggestion": suggestion,
        })

    kunye = veri.get("kunye", {})
    sondajlar = veri.get("sondaj", [])
    jeofizik = veri.get("jeofizik", {})

    def is_blank(value):
        return value is None or str(value).strip() in {"", "-", "None", "null"}

    def litoloji_kapsami_ok(sondaj):
        der = safe_float(sondaj.get("der"))
        rows = []
        for row in sondaj.get("litoloji", []) or []:
            if len(row) < 2:
                continue
            top, bot = safe_float(row[0]), safe_float(row[1])
            if bot > top:
                rows.append((top, bot))
        if der <= 0 or not rows:
            return False
        rows.sort()
        if rows[0][0] > 0.05:
            return False
        prev = rows[0][1]
        for top, bot in rows[1:]:
            if top > prev + 0.05 or top < prev - 0.05:
                return False
            prev = max(prev, bot)
        return prev >= der - 0.05

    def spt_derinlikleri_ok(sondaj):
        der = safe_float(sondaj.get("der"))
        intervals = []
        for row in sondaj.get("litoloji", []) or []:
            if len(row) >= 2:
                top, bot = safe_float(row[0]), safe_float(row[1])
                if bot > top:
                    intervals.append((top, bot))
        for row in sondaj.get("spt", []) or []:
            if not row:
                continue
            depth = safe_float(row[0])
            if depth <= 0 or (der > 0 and depth > der + 0.05):
                return False
            if intervals and not any(top - 0.05 <= depth <= bot + 0.05 for top, bot in intervals):
                return False
        return True

    add("Proje bilgisi", bool(kunye.get("sahibi") and kunye.get("il") and kunye.get("ilce")), "Proje adı, il ve ilçe kontrolü", "kunye", "Künye sekmesinde proje ve konum alanlarını tamamlayın.")
    add("Sondaj kaydı", len(sondajlar) > 0, f"{len(sondajlar)} sondaj", "sondaj", "Sondaj sekmesinden sondaj satırı ekleyin veya workbook kullanın.")
    add("Litoloji", bool(sondajlar) and all(s.get("litoloji") for s in sondajlar), "Her sondajda litoloji beklenir", "sondaj", "Sondaj sekmesinde litoloji detaylarını girin.")
    add("Arazi deneyleri", sum(len(s.get("spt", [])) + len(s.get("pmt", [])) + len(s.get("kaya", [])) for s in sondajlar) > 0, "SPT/PMT/Kaya verisi", "sondaj", "Sondaj sekmesinde SPT/PMT/Kaya verilerini girin.")
    add("Sondaj koordinatları", bool(sondajlar) and all(s.get("y") and s.get("x") for s in sondajlar), "Kesit ve harita için koordinat", "sondaj", "Sondaj koordinatlarını doldurun veya harita aracını kullanın.")
    add("Jeofizik", bool(jeofizik.get("ss_list") or jeofizik.get("mt_list")), "SS veya MT kaydı", "jeofizik", "Jeofizik sekmesinde SS/MT verisi ekleyin.")

    add("Litoloji kapsami", bool(sondajlar) and all(litoloji_kapsami_ok(s) for s in sondajlar), "0.00 m'den kuyu sonuna sureklilik", "sondaj", "Workbook Litoloji sayfasinda bosluk/cakisma ve son derinlikleri kontrol edin.")
    add("SPT derinlikleri", bool(sondajlar) and all(spt_derinlikleri_ok(s) for s in sondajlar), "SPT derinlikleri kuyu/litoloji icinde", "sondaj", "Workbook SPT sayfasinda derinlikleri ve sondaj no alanlarini kontrol edin.")
    add("Sondaj kotlari", bool(sondajlar) and all(not is_blank(s.get("k")) for s in sondajlar), "Kesit baslangic/bitis kotlari icin", "sondaj", "Sondajlar sayfasinda kot alanlarini doldurun.")

    for key, label in [
        ("word_path", "Word şablonu"), ("lab_excel_path", "Lab Excel"), ("jeo_excel_path", "Jeofizik Excel"),
        ("kml_path", "KML sınır"),
        ("img_yer", "Yerbuldurur"), ("img_tkgm", "TKGM"), ("img_pga", "PGA"), ("img_mjh", "MJH"),
        ("word_img_sondaj", "Sondaj haritası"), ("word_img_jeofizik", "Jeofizik haritası"),
    ]:
        path = dosya_durumlari.get(key)
        if key == "lab_excel_path" and lab_sheet_ready(veri):
            add(label, True, "LAB Sheet hazır", "rapor", "Rapor sekmesinden LAB Sheet'i açıp düzenleyebilirsiniz.")
            continue
        if key == "kml_path":
            target = "haritalar"
            suggestion = "Üst araç çubuğundan KML sınır dosyasını seçin."
        elif key == "jeo_excel_path":
            target = "jeofizik"
            suggestion = "Jeofizik sekmesinden Excel dosyasını bağlayın."
        else:
            target = "rapor"
            suggestion = "Rapor sekmesinden ilgili dosyayı veya görseli seçin."
        add(label, bool(path and os.path.exists(path)), os.path.basename(path) if path else "Seçilmedi", target, suggestion)

    ok_count = sum(1 for item in items if item["ok"])
    score = int(round((ok_count / len(items)) * 100)) if items else 0
    if score >= 85:
        state = "RAPORA HAZIR"
    elif score >= 60:
        state = "KONTROL GEREKLİ"
    else:
        state = "EKSİKLER VAR"
    return {"score": score, "state": state, "items": items}


def hesap_ozeti(veri):
    sondajlar = veri.get("sondaj", [])
    total_depth = sum(safe_float(s.get("der")) for s in sondajlar)
    depths = [safe_float(s.get("der")) for s in sondajlar if safe_float(s.get("der")) > 0]
    spt_values = []
    lithology_counter = Counter()
    yass_count = 0

    for sondaj in sondajlar:
        if sondaj.get("yass_d1") or sondaj.get("yass_d2"):
            yass_count += 1
        for row in sondaj.get("spt", []):
            if len(row) > 4:
                val = str(row[4]).strip().upper()
                if val and val != "R":
                    n = safe_float(val)
                    if n > 0:
                        spt_values.append(n)
        for row in sondaj.get("litoloji", []):
            if len(row) >= 3:
                tanim = str(row[2]).strip() or "Tanimsiz"
                thickness = max(0, safe_float(row[1]) - safe_float(row[0]))
                lithology_counter[tanim] += thickness

    avg_depth = sum(depths) / len(depths) if depths else 0
    spt_avg = sum(spt_values) / len(spt_values) if spt_values else 0
    return {
        "sondaj_sayisi": len(sondajlar),
        "toplam_sondaj": total_depth,
        "ortalama_derinlik": avg_depth,
        "spt_sayisi": len(spt_values),
        "spt_min": min(spt_values) if spt_values else 0,
        "spt_max": max(spt_values) if spt_values else 0,
        "spt_ort": spt_avg,
        "yass_olcumlu_sondaj": yass_count,
        "litoloji_dagilimi": lithology_counter.most_common(),
    }


def format_hesap_ozeti(summary):
    lines = [
        f"Sondaj sayisi: {summary['sondaj_sayisi']}",
        f"Toplam sondaj metraji: {summary['toplam_sondaj']:.2f} m",
        f"Ortalama sondaj derinligi: {summary['ortalama_derinlik']:.2f} m",
        f"SPT sayisi: {summary['spt_sayisi']}",
        f"SPT N30 min/ort/max: {summary['spt_min']:.0f} / {summary['spt_ort']:.1f} / {summary['spt_max']:.0f}",
        f"YASS olcumlu sondaj: {summary['yass_olcumlu_sondaj']}",
        "",
        "Litoloji dagilimi:",
    ]
    if summary["litoloji_dagilimi"]:
        for tanim, thickness in summary["litoloji_dagilimi"]:
            lines.append(f"- {tanim}: {thickness:.2f} m")
    else:
        lines.append("- Veri yok")
    return "\n".join(lines)


def rapor_onizleme_metni(veri, dosya_durumlari=None, saglik=None, hesap=None):
    dosya_durumlari = dosya_durumlari or {}
    saglik = saglik or proje_saglik_ozeti(veri, dosya_durumlari)
    hesap = hesap or hesap_ozeti(veri)
    kunye = veri.get("kunye", {})
    lines = [
        "RAPOR ONIZLEME",
        "",
        f"Proje: {kunye.get('sahibi') or '-'}",
        f"Konum: {' / '.join([x for x in [kunye.get('il'), kunye.get('ilce'), kunye.get('mah')] if x]) or '-'}",
        f"Saglik: {saglik['state']} (%{saglik['score']})",
        "",
        format_hesap_ozeti(hesap),
        "",
        "Dosyalar:",
    ]
    for key, label in [
        ("word_path", "Word"), ("lab_excel_path", "Lab Excel"), ("jeo_excel_path", "Jeofizik Excel"),
        ("img_yer", "Yerbuldurur"), ("img_tkgm", "TKGM"), ("img_pga", "PGA"), ("img_mjh", "MJH"),
        ("word_img_sondaj", "Sondaj haritasi"), ("word_img_jeofizik", "Jeofizik haritasi"),
    ]:
        path = dosya_durumlari.get(key)
        if key == "lab_excel_path" and lab_sheet_ready(veri):
            lines.append(f"- {label}: LAB Sheet hazır")
        else:
            lines.append(f"- {label}: {os.path.basename(path) if path else '-'}")
    return "\n".join(lines)
