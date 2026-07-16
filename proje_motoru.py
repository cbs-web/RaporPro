import os
from collections import Counter

from jeofizik_sheet_motoru import jeofizik_sheet_ozeti, jeofizik_sheet_var_mi
from tutarlilik_motoru import proje_tutarlilik_raporu
from yardimcilar import safe_float


def lab_sheet_ready(veri):
    rows = veri.get("lab_sheet", {}).get("rows", []) if isinstance(veri, dict) else []
    return any(any(str(cell).strip() for cell in row) for row in rows or [])


def jeofizik_sheet_ready(veri):
    return jeofizik_sheet_var_mi(veri) and jeofizik_sheet_ozeti(veri).get("ready", False)


def proje_saglik_ozeti(veri, dosya_durumlari=None):
    """Dashboard sağlığını merkezi tutarlılık kontrollerinden üret."""
    report = proje_tutarlilik_raporu(veri, dosya_durumlari)
    items = []
    for check in report.get("checks", []):
        if not check.get("dashboard", True):
            continue
        items.append({
            "id": check.get("id"),
            "label": check.get("label"),
            "ok": bool(check.get("ok")),
            "detail": check.get("detail", ""),
            "target": check.get("target", "ozet"),
            "suggestion": check.get("suggestion", ""),
            "entity": check.get("entity", ""),
            "field": check.get("field", ""),
            "sheet": check.get("sheet", ""),
            "level": "ok" if check.get("ok") else check.get("failure_level", "warning"),
        })
    return {
        "score": report.get("score", 0),
        "state": report.get("state", "EKSİKLER VAR"),
        "items": items,
        "counts": report.get("counts", {}),
        "findings": report.get("findings", []),
    }


def kontrol_grubu_durumu(health, check_ids):
    """Birden fazla merkezi kontrol sonucunu tek kart durumuna indirger."""
    items = health.get("items", []) if isinstance(health, dict) else []
    item_map = {
        item.get("id"): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }
    selected = [item_map.get(check_id) for check_id in check_ids]
    if not selected or any(item is None for item in selected):
        return "warning"
    if any(not item.get("ok") and item.get("level") == "error" for item in selected):
        return "error"
    if any(not item.get("ok") for item in selected):
        return "warning"
    return "ok"


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
        elif key == "jeo_excel_path" and jeofizik_sheet_ready(veri):
            lines.append(f"- {label}: Jeofizik Sheet hazır")
        else:
            lines.append(f"- {label}: {os.path.basename(path) if path else '-'}")
    return "\n".join(lines)
