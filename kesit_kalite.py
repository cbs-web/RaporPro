# Dosya: RaporPro/kesit_kalite.py
from collections import Counter
import math
import statistics

from sabitler import LEJANTLAR
from yardimcilar import safe_float, haversine_distance, litoloji_cozumle
from kesit_korelasyon import build_pair_correlation, normalize_section_layers


UNIT_NAMES = {item["kod"]: item["ad"] for item in LEJANTLAR}
CONSISTENCY_CODES = {"kl", "s", "k", "c"}


def _is_blank(value):
    return str(value or "").strip() == ""


def _unit_name(code):
    return UNIT_NAMES.get(code, code or "tanimsiz")


def _coords(sondaj):
    y = safe_float(sondaj.get("y"))
    x = safe_float(sondaj.get("x"))
    if y == 0 or x == 0:
        return None
    return y, x


def _row_value(row, index, default="", keys=None):
    try:
        if isinstance(row, dict):
            keys = keys or ()
            return row.get(keys[index], default) if index < len(keys) else default
        return row[index]
    except Exception:
        return default


def _parse_spt(row):
    if not row:
        return None
    spt_keys = ("der", "v15", "v30", "v45", "n30")
    depth = safe_float(_row_value(row, 0, keys=spt_keys))
    if depth <= 0:
        return None
    vals = [str(_row_value(row, i, "", keys=spt_keys)).strip() for i in range(1, 5)]
    vals_lower = [value.lower() for value in vals]
    refused = any(
        value == "r" or value == "-" or "refu" in value or "ref" in value or "50/" in value
        for value in vals_lower
    )
    if refused:
        return {"depth": depth, "n30": None, "refused": True}

    n30_text = vals[3] if len(vals) > 3 else ""
    n30 = safe_float(n30_text)
    if n30 > 0 or n30_text.replace(",", ".") in ("0", "0.0"):
        return {"depth": depth, "n30": n30, "refused": False}

    calculated = safe_float(vals[1] if len(vals) > 1 else "") + safe_float(vals[2] if len(vals) > 2 else "")
    if calculated > 0:
        return {"depth": depth, "n30": calculated, "refused": False}
    return {"depth": depth, "n30": None, "refused": False}


def _normalize_layers(sondaj):
    raw_layers = sondaj.get("litoloji", []) or []
    layers = []
    for idx, row in enumerate(raw_layers):
        lit_keys = ("top", "bot", "tanim")
        top = safe_float(_row_value(row, 0, keys=lit_keys))
        bot = safe_float(_row_value(row, 1, keys=lit_keys))
        text = str(_row_value(row, 2, "", keys=lit_keys) or "").strip()
        code = litoloji_cozumle(text)
        layers.append({
            "index": idx,
            "top": top,
            "bot": bot,
            "text": text,
            "code": code,
            "thickness": abs(bot - top),
        })
    return layers


def _merged_layers(layers):
    merged = []
    for layer in layers:
        if not merged:
            merged.append(dict(layer))
            continue
        previous = merged[-1]
        if previous["code"] == layer["code"] and abs(previous["bot"] - layer["top"]) < 0.1:
            previous["bot"] = layer["bot"]
            previous["thickness"] = abs(previous["bot"] - previous["top"])
            previous["text"] = layer.get("text") or previous.get("text", "")
        else:
            merged.append(dict(layer))
    return merged


def _spt_source_for_layer(sondaj, layer, search_margin=1.5):
    parsed_rows = []
    for row in sondaj.get("spt", []) or []:
        parsed = _parse_spt(row)
        if parsed:
            parsed_rows.append(parsed)
    if not parsed_rows:
        return "none", None

    top = layer["top"]
    bot = layer["bot"]
    mid = (top + bot) / 2
    thickness = abs(bot - top)
    n_values = []
    has_refusal = False
    for parsed in parsed_rows:
        depth = parsed["depth"]
        if top - 0.01 <= depth <= bot + 0.01:
            if parsed["refused"]:
                has_refusal = True
            elif parsed["n30"] is not None:
                n_values.append(parsed["n30"])
    if has_refusal:
        return "refusal", None
    if n_values:
        return "n30", statistics.median(n_values)

    parsed_rows = sorted(parsed_rows, key=lambda item: item["depth"])
    last_spt = parsed_rows[-1]
    if last_spt["refused"] and top >= last_spt["depth"] - 0.01:
        return "refusal_after_last", None

    nearest = None
    nearest_dist = None
    max_dist = max(search_margin, thickness / 2)
    for parsed in parsed_rows:
        dist = abs(parsed["depth"] - mid)
        if dist <= max_dist and (nearest_dist is None or dist < nearest_dist):
            nearest = parsed
            nearest_dist = dist
    if nearest:
        if nearest["refused"]:
            return "nearest_refusal", None
        if nearest["n30"] is not None:
            return "nearest_n30", nearest["n30"]
    return "none", None


def _line_projector(start_y, start_x, end_y, end_x):
    lat0_rad = math.radians(start_y)
    meters_per_lat = 111320.0
    meters_per_lon = 111320.0 * math.cos(lat0_rad)

    def to_local(y, x):
        return (x - start_x) * meters_per_lon, (y - start_y) * meters_per_lat

    end_lx, end_ly = to_local(end_y, end_x)
    line_len = math.hypot(end_lx, end_ly)
    if line_len <= 0.01:
        return None
    ux, uy = end_lx / line_len, end_ly / line_len

    def project(y, x):
        px, py = to_local(y, x)
        station = px * ux + py * uy
        offset = px * (-uy) + py * ux
        return station, offset

    return project


def _check_layer_matching(sondajlar, merged_by_no, report, stats, options):
    tolerance = safe_float(options.get("corr_tolerance", 3.0)) or 3.0
    if tolerance <= 0:
        tolerance = 3.0

    for left, right in zip(sondajlar, sondajlar[1:]):
        left_no = left.get("no", "SK")
        right_no = right.get("no", "SK")
        layers1 = merged_by_no.get(left_no, [])
        layers2 = merged_by_no.get(right_no, [])
        matched_1 = set()
        matched_2 = set()
        last_idx2 = -1

        for idx1, l1 in enumerate(layers1):
            y1mid = safe_float(left.get("k")) - (l1["top"] + l1["bot"]) / 2
            best_idx2 = -1
            best_dist = None
            for idx2 in range(last_idx2 + 1, len(layers2)):
                l2 = layers2[idx2]
                if l2["code"] != l1["code"]:
                    continue
                y2mid = safe_float(right.get("k")) - (l2["top"] + l2["bot"]) / 2
                dist = abs(y1mid - y2mid)
                if dist <= tolerance and (best_dist is None or dist < best_dist):
                    best_dist = dist
                    best_idx2 = idx2
            if best_idx2 != -1:
                matched_1.add(idx1)
                matched_2.add(best_idx2)
                last_idx2 = best_idx2

        for idx1, l1 in enumerate(layers1):
            if idx1 in matched_1:
                continue
            stats["unmatched_layers"] += 1
            report["warnings"].append(
                f"{left_no}-{right_no}: {left_no} {l1['top']:.2f}-{l1['bot']:.2f} m "
                f"{_unit_name(l1['code'])} birimi eşleşmedi; kesitte pinch-out/facies geçişi çizilebilir."
            )
        for idx2, l2 in enumerate(layers2):
            if idx2 in matched_2:
                continue
            stats["unmatched_layers"] += 1
            report["warnings"].append(
                f"{left_no}-{right_no}: {right_no} {l2['top']:.2f}-{l2['bot']:.2f} m "
                f"{_unit_name(l2['code'])} birimi eşleşmedi; kesitte pinch-out/facies geçişi çizilebilir."
            )


def _check_layer_matching_v2(sondajlar, merged_by_no, report, stats, options):
    for left, right in zip(sondajlar, sondajlar[1:]):
        left_no = left.get("no", "SK")
        right_no = right.get("no", "SK")
        layers1 = merged_by_no.get(left_no, [])
        layers2 = merged_by_no.get(right_no, [])
        left_coords = _coords(left)
        right_coords = _coords(right)
        if left_coords and right_coords:
            dx_true = haversine_distance(
                left_coords[0],
                left_coords[1],
                right_coords[0],
                right_coords[1],
            )
        else:
            dx_true = safe_float(options.get("dx_default", 25.0)) or 25.0

        link = build_pair_correlation(left, right, layers1, layers2, dx_true, options)
        matched_1 = set(link.get("matches_s1", {})) | set(link.get("facies_s1", {}))
        matched_2 = set(link.get("matches_s2", {})) | set(link.get("facies_s2", {}))
        stats["exact_matches"] += len(link.get("matches_s1", {}))
        stats["facies_matches"] += len(link.get("facies_s1", {}))

        for relation in link.get("relations", []):
            confidence = safe_float(relation.get("confidence"))
            if confidence >= 0.35:
                continue
            stats["low_confidence_matches"] += 1
            if relation.get("kind") == "facies":
                relation_name = (
                    f"{relation.get('left_name') or '-'} / "
                    f"{relation.get('right_name') or '-'}"
                )
            else:
                relation_name = relation.get("detail_name") or "-"
            report["warnings"].append(
                f"{left_no}-{right_no}: {relation_name} korelasyonu düşük güvenli "
                f"(%{confidence * 100:.0f})."
            )

        for idx1, layer in enumerate(layers1):
            if idx1 in matched_1:
                continue
            stats["unmatched_layers"] += 1
            report["warnings"].append(
                f"{left_no}-{right_no}: {left_no} {layer['top']:.2f}-{layer['bot']:.2f} m "
                f"{layer.get('detail_name') or _unit_name(layer.get('code'))} eşleşmedi; "
                "V2 kesitte pinch-out olarak çizilebilir."
            )
        for idx2, layer in enumerate(layers2):
            if idx2 in matched_2:
                continue
            stats["unmatched_layers"] += 1
            report["warnings"].append(
                f"{left_no}-{right_no}: {right_no} {layer['top']:.2f}-{layer['bot']:.2f} m "
                f"{layer.get('detail_name') or _unit_name(layer.get('code'))} eşleşmedi; "
                "V2 kesitte pinch-out olarak çizilebilir."
            )


def build_section_quality_report(sondajlar, options=None):
    options = options or {}
    sondajlar = list(sondajlar or [])
    report = {"errors": [], "warnings": [], "info": [], "stats": Counter()}
    stats = report["stats"]
    stats["well_count"] = len(sondajlar)

    if len(sondajlar) < 2:
        report["errors"].append("Kesit için en az iki sondaj seçilmeli.")
        return report

    thin_limit = safe_float(options.get("section_qc_thin_layer", 0.30)) or 0.30
    spt_search_margin = safe_float(options.get("spt_label_search_margin", 1.5)) or 1.5
    mode = options.get("mode", "schematic")
    section_engine = str(options.get("section_engine", "v1") or "v1").strip().lower()
    use_correlation_v2 = section_engine in ("v2", "2", "yeni", "new")
    merged_by_no = {}

    if mode in ("true_distance", "line_projection"):
        missing = [s.get("no", "SK") for s in sondajlar if _coords(s) is None]
        for no in missing:
            report["warnings"].append(f"{no}: koordinat eksik; kesit mesafesi/offset varsayılan davranışa düşebilir.")

    if mode == "line_projection":
        start_y = safe_float(options.get("line_start_y"))
        start_x = safe_float(options.get("line_start_x"))
        end_y = safe_float(options.get("line_end_y"))
        end_x = safe_float(options.get("line_end_x"))
        projector = _line_projector(start_y, start_x, end_y, end_x) if start_y and start_x and end_y and end_x else None
        if projector is None:
            report["warnings"].append("Kesit hattı koordinatları eksik/geçersiz; motor şematik aralığa dönebilir.")
        else:
            max_offset = safe_float(options.get("max_offset", 10.0))
            if max_offset > 0:
                for sondaj in sondajlar:
                    coords = _coords(sondaj)
                    if not coords:
                        continue
                    _, offset = projector(coords[0], coords[1])
                    if abs(offset) > max_offset:
                        report["warnings"].append(
                            f"{sondaj.get('no','SK')}: kesit hattından {abs(offset):.1f} m uzakta "
                            f"(limit {max_offset:g} m)."
                        )

    for idx, sondaj in enumerate(sondajlar):
        no = sondaj.get("no") or f"SK-{idx + 1}"
        depth = safe_float(sondaj.get("der"))
        if depth <= 0:
            report["warnings"].append(f"{no}: sondaj derinliği boş/geçersiz.")
        if _is_blank(sondaj.get("k")):
            report["warnings"].append(f"{no}: başlangıç kotu boş.")

        layers = normalize_section_layers(sondaj, merge_same_detail=False) if use_correlation_v2 else _normalize_layers(sondaj)
        stats["layer_count"] += len(layers)
        if not layers:
            report["errors"].append(f"{no}: litoloji satırı yok; kesit bu kuyuda eksik çizilir.")
            merged_by_no[no] = []
            continue

        layers_sorted = sorted(layers, key=lambda item: (item["top"], item["bot"]))
        if use_correlation_v2:
            normalized_sondaj = dict(sondaj)
            normalized_sondaj["litoloji"] = sondaj.get("litoloji", [])
            merged_by_no[no] = normalize_section_layers(normalized_sondaj)
        else:
            merged_by_no[no] = _merged_layers(layers_sorted)
        first = layers_sorted[0]
        if first["top"] > 0.10:
            report["warnings"].append(f"{no}: litoloji 0.00 m yerine {first['top']:.2f} m'den başlıyor.")

        previous = None
        for layer in layers_sorted:
            top, bot = layer["top"], layer["bot"]
            if bot <= top:
                stats["invalid_layers"] += 1
                report["errors"].append(f"{no}: {top:.2f}-{bot:.2f} m litoloji aralığı geçersiz.")
                continue
            if previous:
                gap = top - previous["bot"]
                if gap > 0.10:
                    stats["gaps"] += 1
                    report["warnings"].append(f"{no}: {previous['bot']:.2f}-{top:.2f} m arasında litoloji boşluğu var.")
                elif gap < -0.10:
                    stats["overlaps"] += 1
                    report["warnings"].append(f"{no}: {top:.2f} m seviyesinde litoloji çakışması var.")
            previous = layer

            if layer["thickness"] < thin_limit:
                stats["thin_layers"] += 1
                report["warnings"].append(
                    f"{no}: {top:.2f}-{bot:.2f} m {_unit_name(layer['code'])} tabakası çok ince "
                    f"({layer['thickness']:.2f} m)."
                )
            if layer["code"] == "tanimsiz":
                stats["unknown_units"] += 1
                report["warnings"].append(
                    f"{no}: {top:.2f}-{bot:.2f} m litoloji tanımı pattern'e eşleşmedi: '{layer['text'] or '-'}'."
                )
            if layer["code"] in CONSISTENCY_CODES:
                source, value = _spt_source_for_layer(sondaj, layer, spt_search_margin)
                if source == "none":
                    stats["consistency_missing"] += 1
                    report["warnings"].append(
                        f"{no}: {top:.2f}-{bot:.2f} m {_unit_name(layer['code'])} için SPT yok; "
                        "sıkılık/kıvam etiketi boş kalabilir."
                    )
                elif "refusal" in source:
                    stats["refusal_inferred"] += 1
                    report["info"].append(
                        f"{no}: {top:.2f}-{bot:.2f} m {_unit_name(layer['code'])} sıkılık/kıvam etiketi refüden varsayılacak."
                    )

        if previous and depth > 0:
            if previous["bot"] < depth - 0.10:
                stats["bottom_gaps"] += 1
                report["warnings"].append(f"{no}: litoloji {previous['bot']:.2f} m'de bitiyor, sondaj derinliği {depth:.2f} m.")
            elif previous["bot"] > depth + 0.10:
                stats["depth_exceeded"] += 1
                report["warnings"].append(f"{no}: litoloji {previous['bot']:.2f} m'ye iniyor, sondaj derinliği {depth:.2f} m.")

    if use_correlation_v2:
        _check_layer_matching_v2(sondajlar, merged_by_no, report, stats, options)
        report["info"].append(
            f"V2 korelasyon: {stats.get('exact_matches', 0)} ayrıntılı birim eşleşmesi, "
            f"{stats.get('facies_matches', 0)} kontrollü fasiyes geçişi."
        )
    else:
        _check_layer_matching(sondajlar, merged_by_no, report, stats, options)

    manual_edits = options.get("manual_edits") or {}
    if isinstance(manual_edits, dict) and manual_edits:
        stats["manual_edits"] = len(manual_edits)
        report["info"].append(f"Kayıtlı manuel kesit düzenlemesi: {len(manual_edits)} polygon.")

    report["info"].insert(
        0,
        f"{stats['well_count']} sondaj, {stats['layer_count']} litoloji satırı kontrol edildi."
    )
    return report


def format_section_quality_report(report):
    stats = report.get("stats", {})
    lines = ["KESİT KALİTE KONTROL", "=" * 22, ""]
    lines.append(
        "Özet: "
        f"{len(report.get('errors', []))} hata, "
        f"{len(report.get('warnings', []))} uyarı, "
        f"{len(report.get('info', []))} bilgi"
    )
    if stats:
        stat_parts = [
            f"sondaj={stats.get('well_count', 0)}",
            f"litoloji={stats.get('layer_count', 0)}",
            f"tanımsız={stats.get('unknown_units', 0)}",
            f"ince={stats.get('thin_layers', 0)}",
            f"eşleşmeyen={stats.get('unmatched_layers', 0)}",
            f"v2_tam={stats.get('exact_matches', 0)}",
            f"v2_fasiyes={stats.get('facies_matches', 0)}",
            f"kıvam_boş={stats.get('consistency_missing', 0)}",
            f"refu={stats.get('refusal_inferred', 0)}",
        ]
        lines.append("Sayaçlar: " + ", ".join(stat_parts))
    lines.append("")

    for title, key in (("HATALAR", "errors"), ("UYARILAR", "warnings"), ("BİLGİ", "info")):
        lines.append(title)
        items = report.get(key, [])
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- Yok")
        lines.append("")
    return "\n".join(lines).strip()
