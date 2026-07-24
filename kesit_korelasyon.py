# Dosya: RaporPro/kesit_korelasyon.py
"""Kesit V2 icin saf litoloji normalizasyonu ve korelasyon yardimcilari."""

from __future__ import annotations

import math
import re
from typing import Any

from yardimcilar import litoloji_cozumle, litoloji_kelime_normalize, safe_float


_DETAIL_DISPLAY = {
    "bitkisel": "Bitkisel",
    "toprak": "Toprak",
    "nebati": "Nebati",
    "kil": "Kil",
    "killi": "Killi",
    "silt": "Silt",
    "siltli": "Siltli",
    "kum": "Kum",
    "kumlu": "Kumlu",
    "cakil": "Çakıl",
    "cakilli": "Çakıllı",
    "moloz": "Moloz",
    "molozlu": "Molozlu",
    "dolgu": "Dolgu",
    "kiltasi": "Kiltaşı",
    "silttasi": "Silttaşı",
    "kumtasi": "Kumtaşı",
    "cakiltasi": "Çakıltaşı",
    "camurtasi": "Çamurtaşı",
    "konglomera": "Konglomera",
    "bres": "Breş",
}

_MAIN_TERMS = {
    "toprak",
    "kil",
    "silt",
    "kum",
    "cakil",
    "moloz",
    "dolgu",
    "kiltasi",
    "silttasi",
    "kumtasi",
    "cakiltasi",
    "camurtasi",
    "konglomera",
    "bres",
}

_MODIFIER_TERMS = {
    "bitkisel",
    "nebati",
    "killi",
    "siltli",
    "kumlu",
    "cakilli",
    "molozlu",
}

_FACIES_FAMILY = {
    "kl": "fine",
    "s": "fine",
    "k": "coarse",
    "c": "coarse",
    "kit": "rock",
    "kt": "rock",
    "ct": "rock",
    "dg": "fill",
    "mlz": "fill",
}


def turkce_buyuk_harf(text: Any) -> str:
    return str(text or "").translate(str.maketrans({"i": "İ", "ı": "I"})).upper()


def _text_tokens(text: Any) -> list[str]:
    raw_tokens = re.findall(r"[^\W_]+", str(text or ""), flags=re.UNICODE)
    return [litoloji_kelime_normalize(token) for token in raw_tokens if litoloji_kelime_normalize(token)]


def _join_compound_terms(tokens: list[str]) -> list[str]:
    compounds = {
        ("kil", "tasi"): "kiltasi",
        ("silt", "tasi"): "silttasi",
        ("kum", "tasi"): "kumtasi",
        ("cakil", "tasi"): "cakiltasi",
        ("camur", "tasi"): "camurtasi",
    }
    joined = []
    idx = 0
    while idx < len(tokens):
        if idx + 1 < len(tokens):
            compound = compounds.get((tokens[idx], tokens[idx + 1]))
            if compound:
                joined.append(compound)
                idx += 2
                continue
        joined.append(tokens[idx])
        idx += 1
    return joined


def litoloji_detay_terimleri(text: Any) -> list[str]:
    """Tanimin sonundaki jeolojik birim ifadesini ayiklar."""
    tokens = _join_compound_terms(_text_tokens(text))
    if not tokens:
        return []

    main_idx = -1
    for idx in range(len(tokens) - 1, -1, -1):
        if tokens[idx] in _MAIN_TERMS:
            main_idx = idx
            break
    if main_idx < 0:
        return []

    start_idx = main_idx
    while start_idx > 0 and tokens[start_idx - 1] in _MODIFIER_TERMS:
        start_idx -= 1
    return tokens[start_idx:main_idx + 1]


def litoloji_detay_adi(text: Any) -> str:
    """Pattern kodundan bagimsiz, kullaniciya gosterilecek birim adini dondurur."""
    terms = litoloji_detay_terimleri(text)
    if not terms:
        raw = re.sub(r"\s+", " ", str(text or "")).strip()
        return raw or "Tanımsız Birim"
    return " ".join(_DETAIL_DISPLAY.get(term, term.title()) for term in terms)


def litoloji_ana_birim_adi(text: Any) -> str:
    """Litoloji taniminin son ana kelimesini kesit birimi olarak dondurur."""
    terms = litoloji_detay_terimleri(text)
    if terms:
        main_term = terms[-1]
        if main_term == "toprak" and any(term in ("bitkisel", "nebati") for term in terms):
            return "Bitkisel Toprak"
        return _DETAIL_DISPLAY.get(main_term, main_term.title())

    code = litoloji_cozumle(text) or "tanimsiz"
    return {
        "bt": "Bitkisel Toprak",
        "kl": "Kil",
        "s": "Silt",
        "k": "Kum",
        "c": "Çakıl",
        "kit": "Kiltaşı",
        "kt": "Kumtaşı",
        "ct": "Çakıltaşı",
        "dg": "Dolgu",
        "mlz": "Moloz",
    }.get(code, "Tanımsız Birim")


def litoloji_korelasyon_anahtari(text: Any) -> str:
    """Kesit korelasyonunu son ana birime/pattern koduna baglar."""
    return litoloji_cozumle(text) or "tanimsiz"


def _row_value(row: Any, index: int, keys: tuple[str, ...], default: Any = "") -> Any:
    if isinstance(row, dict):
        for key in keys:
            if key in row:
                return row.get(key, default)
        return default
    if isinstance(row, (list, tuple)) and index < len(row):
        return row[index]
    return default


def section_layer_id(well_no: Any, layer: dict[str, Any]) -> str:
    source_indices = ",".join(str(item) for item in layer.get("source_indices", []))
    return (
        f"{str(well_no or 'SK').strip()}|"
        f"{safe_float(layer.get('top')):.3f}|{safe_float(layer.get('bot')):.3f}|"
        f"{layer.get('correlation_key') or layer.get('code') or 'tanimsiz'}|{source_indices}"
    )


def correlation_pair_key(left_no: Any, right_no: Any) -> str:
    return f"{str(left_no or 'SK').strip()}::{str(right_no or 'SK').strip()}"


def correlation_relation_id(left_id: Any, right_id: Any) -> str:
    return f"{str(left_id or '').strip()}>>{str(right_id or '').strip()}"


def normalize_section_layers(sondaj: dict[str, Any], merge_same_detail: bool = True) -> list[dict[str, Any]]:
    """Sondaj litolojisini siralar; pattern ve korelasyon kimligini ayri tutar."""
    layers = []
    for source_idx, row in enumerate(sondaj.get("litoloji", []) or []):
        top = safe_float(_row_value(row, 0, ("bas", "baslangic", "top", "from")))
        bot = safe_float(_row_value(row, 1, ("bit", "bitis", "bot", "to")))
        text = str(_row_value(row, 2, ("tanim", "litoloji", "aciklama", "text"), "") or "").strip()
        code = litoloji_cozumle(text) or "tanimsiz"
        detail_name = litoloji_ana_birim_adi(text)
        correlation_key = litoloji_korelasyon_anahtari(text)
        layers.append({
            "top": top,
            "bot": bot,
            "thickness": abs(bot - top),
            "code": code,
            "text": text,
            "detail_name": detail_name,
            "correlation_key": correlation_key,
            "source_indices": [source_idx],
        })

    layers.sort(key=lambda item: (item["top"], item["bot"], item["source_indices"][0]))
    if not merge_same_detail:
        return layers

    merged = []
    for layer in layers:
        if not merged:
            merged.append(dict(layer))
            continue
        previous = merged[-1]
        same_unit = (
            previous.get("code") == layer.get("code")
            and abs(safe_float(previous.get("bot")) - safe_float(layer.get("top"))) < 0.1
        )
        if not same_unit:
            merged.append(dict(layer))
            continue
        previous["bot"] = layer["bot"]
        previous["thickness"] = abs(safe_float(previous.get("bot")) - safe_float(previous.get("top")))
        previous["source_indices"] = list(previous.get("source_indices", [])) + list(layer.get("source_indices", []))
        if layer.get("text") and layer.get("text") not in str(previous.get("text") or ""):
            previous["text"] = f"{previous.get('text', '')} | {layer['text']}".strip(" |")

    return merged


def layer_elevation_info(sondaj: dict[str, Any], layer: dict[str, Any]) -> dict[str, float]:
    elevation = safe_float(sondaj.get("_kot", sondaj.get("k")))
    y_top = elevation - safe_float(layer.get("top"))
    y_bot = elevation - safe_float(layer.get("bot"))
    high = max(y_top, y_bot)
    low = min(y_top, y_bot)
    return {
        "top": high,
        "bot": low,
        "mid": (high + low) / 2,
        "thickness": abs(high - low),
    }


def layer_overlap(info1: dict[str, float], info2: dict[str, float]) -> float:
    return min(info1["top"], info2["top"]) - max(info1["bot"], info2["bot"])


def _match_limit(dx_true: float, options: dict[str, Any]) -> float:
    tolerance = safe_float(options.get("corr_tolerance"))
    if tolerance > 0:
        return tolerance
    return max(3.0, min(8.0, abs(dx_true) * 0.12))


def _exact_candidate(
    s1: dict[str, Any],
    s2: dict[str, Any],
    l1: dict[str, Any],
    l2: dict[str, Any],
    dx_true: float,
    options: dict[str, Any],
) -> tuple[float, float] | None:
    if l1.get("code") != l2.get("code"):
        return None

    info1 = layer_elevation_info(s1, l1)
    info2 = layer_elevation_info(s2, l2)
    overlap = layer_overlap(info1, info2)
    mid_dist = abs(info1["mid"] - info2["mid"])
    boundary_dist = (
        abs(info1["top"] - info2["top"])
        + abs(info1["bot"] - info2["bot"])
    ) / 2
    thickness_diff = abs(info1["thickness"] - info2["thickness"])
    limit = _match_limit(dx_true, options)
    small_overlap = max(0.15, min(info1["thickness"], info2["thickness"]) * 0.10)
    if mid_dist > limit and overlap <= small_overlap:
        return None
    if boundary_dist > limit * 1.8 and overlap <= 0:
        return None

    score = 20.0
    score -= mid_dist * 1.10
    score -= boundary_dist * 0.35
    score -= thickness_diff * 0.20
    score += max(0.0, overlap) * 0.55
    score = max(0.10, score)
    confidence = 1.0 - min(1.0, (mid_dist + boundary_dist * 0.5) / max(limit * 2.0, 0.01))
    return score, max(0.05, min(0.99, confidence))


def _global_exact_matches(
    s1: dict[str, Any],
    s2: dict[str, Any],
    layers1: list[dict[str, Any]],
    layers2: list[dict[str, Any]],
    dx_true: float,
    options: dict[str, Any],
) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
    n, m = len(layers1), len(layers2)
    scores = [[0.0] * (m + 1) for _ in range(n + 1)]
    choices = [[""] * (m + 1) for _ in range(n + 1)]
    candidates = {}
    confidences = {}

    for i, l1 in enumerate(layers1):
        for j, l2 in enumerate(layers2):
            candidate = _exact_candidate(s1, s2, l1, l2, dx_true, options)
            if candidate:
                candidates[(i, j)] = candidate[0]
                confidences[(i, j)] = candidate[1]

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = scores[i - 1][j]
            choice = "up"
            if scores[i][j - 1] > best:
                best = scores[i][j - 1]
                choice = "left"
            candidate_score = candidates.get((i - 1, j - 1))
            if candidate_score is not None:
                diagonal = scores[i - 1][j - 1] + candidate_score
                if diagonal >= best:
                    best = diagonal
                    choice = "diag"
            scores[i][j] = best
            choices[i][j] = choice

    selected = []
    i, j = n, m
    while i > 0 and j > 0:
        choice = choices[i][j]
        if choice == "diag":
            selected.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif choice == "left":
            j -= 1
        else:
            i -= 1
    selected.reverse()
    return selected, confidences


def _facies_compatible(code1: Any, code2: Any) -> bool:
    code1 = str(code1 or "")
    code2 = str(code2 or "")
    if not code1 or not code2 or "tanimsiz" in (code1, code2):
        return False
    if "bt" in (code1, code2):
        return code1 == code2
    return True


def _facies_matches(
    s1: dict[str, Any],
    s2: dict[str, Any],
    layers1: list[dict[str, Any]],
    layers2: list[dict[str, Any]],
    exact_pairs: list[tuple[int, int]],
    options: dict[str, Any],
) -> list[tuple[int, int, float]]:
    used1 = {item[0] for item in exact_pairs}
    used2 = {item[1] for item in exact_pairs}
    min_overlap = safe_float(options.get("facies_overlap_min", 0.1)) or 0.1
    candidates = []

    def crosses_selected(idx1: int, idx2: int, selected: list[tuple[int, int]]) -> bool:
        return any((idx1 - left) * (idx2 - right) < 0 for left, right in selected)

    for idx1, l1 in enumerate(layers1):
        if idx1 in used1:
            continue
        info1 = layer_elevation_info(s1, l1)
        for idx2, l2 in enumerate(layers2):
            if idx2 in used2 or not _facies_compatible(l1.get("code"), l2.get("code")):
                continue
            if crosses_selected(idx1, idx2, exact_pairs):
                continue
            info2 = layer_elevation_info(s2, l2)
            overlap = layer_overlap(info1, info2)
            if overlap <= min_overlap:
                continue
            mid_dist = abs(info1["mid"] - info2["mid"])
            same_pattern_bonus = 2.0 if l1.get("code") == l2.get("code") else 0.0
            family1 = _FACIES_FAMILY.get(str(l1.get("code") or ""))
            family2 = _FACIES_FAMILY.get(str(l2.get("code") or ""))
            same_family_bonus = 0.75 if family1 and family1 == family2 else 0.0
            score = overlap * 4.0 - mid_dist * 0.35 + same_pattern_bonus + same_family_bonus
            confidence = min(0.90, max(0.10, overlap / max(info1["thickness"], info2["thickness"], 0.01)))
            candidates.append((score, idx1, idx2, confidence))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected_pairs = list(exact_pairs)
    selected = []
    for _, idx1, idx2, confidence in candidates:
        if idx1 in used1 or idx2 in used2:
            continue
        if crosses_selected(idx1, idx2, selected_pairs):
            continue
        selected.append((idx1, idx2, confidence))
        selected_pairs.append((idx1, idx2))
        used1.add(idx1)
        used2.add(idx2)
    return selected


def build_pair_correlation(
    s1: dict[str, Any],
    s2: dict[str, Any],
    layers1: list[dict[str, Any]],
    layers2: list[dict[str, Any]],
    dx_true: float,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Iki komsu sondaj arasinda sirayi bozmayan V2 korelasyonunu kurar."""
    options = options or {}
    exact_pairs, confidences = _global_exact_matches(s1, s2, layers1, layers2, dx_true, options)
    facies_pairs = _facies_matches(s1, s2, layers1, layers2, exact_pairs, options)
    relation_sources = {}

    left_no = s1.get("no", "SK")
    right_no = s2.get("no", "SK")
    pair_key = correlation_pair_key(left_no, right_no)
    all_overrides = options.get("correlation_overrides") or {}
    pair_overrides = all_overrides.get(pair_key, {}) if isinstance(all_overrides, dict) else {}
    blocked = set(pair_overrides.get("blocked", []) or []) if isinstance(pair_overrides, dict) else set()
    forced = list(pair_overrides.get("forced", []) or []) if isinstance(pair_overrides, dict) else []

    def relation_id_for_indices(idx1: int, idx2: int) -> str:
        return correlation_relation_id(
            section_layer_id(left_no, layers1[idx1]),
            section_layer_id(right_no, layers2[idx2]),
        )

    exact_pairs = [
        (idx1, idx2)
        for idx1, idx2 in exact_pairs
        if relation_id_for_indices(idx1, idx2) not in blocked
    ]
    facies_pairs = [
        (idx1, idx2, confidence)
        for idx1, idx2, confidence in facies_pairs
        if relation_id_for_indices(idx1, idx2) not in blocked
    ]

    left_index_by_id = {
        section_layer_id(left_no, layer): idx
        for idx, layer in enumerate(layers1)
    }
    right_index_by_id = {
        section_layer_id(right_no, layer): idx
        for idx, layer in enumerate(layers2)
    }
    for override in forced:
        if not isinstance(override, dict):
            continue
        idx1 = left_index_by_id.get(str(override.get("left_id") or ""))
        idx2 = right_index_by_id.get(str(override.get("right_id") or ""))
        if idx1 is None or idx2 is None:
            continue

        exact_pairs = [
            pair for pair in exact_pairs
            if pair[0] != idx1 and pair[1] != idx2
        ]
        facies_pairs = [
            pair for pair in facies_pairs
            if pair[0] != idx1 and pair[1] != idx2
        ]
        requested_kind = str(override.get("kind") or "match").strip().lower()
        same_identity = layers1[idx1].get("code") == layers2[idx2].get("code")
        kind = "match" if requested_kind == "match" and same_identity else "facies"
        relation_id = relation_id_for_indices(idx1, idx2)
        relation_sources[relation_id] = "manual"
        if kind == "match":
            exact_pairs.append((idx1, idx2))
            confidences[(idx1, idx2)] = 1.0
        else:
            facies_pairs.append((idx1, idx2, 1.0))

    exact_pairs.sort()
    facies_pairs.sort(key=lambda item: (item[0], item[1]))

    matches_s1 = {idx1: idx2 for idx1, idx2 in exact_pairs}
    matches_s2 = {idx2: idx1 for idx1, idx2 in exact_pairs}
    facies_s1 = {idx1: idx2 for idx1, idx2, _ in facies_pairs}
    facies_s2 = {idx2: idx1 for idx1, idx2, _ in facies_pairs}
    relations = []

    for idx1, idx2 in exact_pairs:
        relation_id = relation_id_for_indices(idx1, idx2)
        relations.append({
            "relation_id": relation_id,
            "kind": "match",
            "left_index": idx1,
            "right_index": idx2,
            "left_id": section_layer_id(s1.get("no"), layers1[idx1]),
            "right_id": section_layer_id(s2.get("no"), layers2[idx2]),
            "detail_name": layers1[idx1].get("detail_name", ""),
            "confidence": round(confidences.get((idx1, idx2), 0.5), 3),
            "source": relation_sources.get(relation_id, "auto_v2"),
        })
    for idx1, idx2, confidence in facies_pairs:
        relation_id = relation_id_for_indices(idx1, idx2)
        relations.append({
            "relation_id": relation_id,
            "kind": "facies",
            "left_index": idx1,
            "right_index": idx2,
            "left_id": section_layer_id(s1.get("no"), layers1[idx1]),
            "right_id": section_layer_id(s2.get("no"), layers2[idx2]),
            "left_name": layers1[idx1].get("detail_name", ""),
            "right_name": layers2[idx2].get("detail_name", ""),
            "confidence": round(confidence, 3),
            "source": relation_sources.get(relation_id, "auto_v2"),
        })

    return {
        "pair_key": pair_key,
        "matches_s1": matches_s1,
        "matches_s2": matches_s2,
        "facies_s1": facies_s1,
        "facies_s2": facies_s2,
        "relations": relations,
    }


def build_section_correlations(
    sondajlar: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    options = options or {}
    links = []
    for idx in range(max(0, len(sondajlar) - 1)):
        left = sondajlar[idx]
        right = sondajlar[idx + 1]
        layers1 = left.get("merged_layers_v2") or left.get("merged_layers") or []
        layers2 = right.get("merged_layers_v2") or right.get("merged_layers") or []
        dx_true = safe_float(left.get("_true_dist", options.get("dx_default", 25.0))) or 25.0
        link = build_pair_correlation(left, right, layers1, layers2, dx_true, options)
        link["left_no"] = left.get("no", f"SK-{idx + 1}")
        link["right_no"] = right.get("no", f"SK-{idx + 2}")
        link["layers1"] = layers1
        link["layers2"] = layers2
        links.append(link)
    return links


def build_semantic_lens_tracks(
    sondajlar: list[dict[str, Any]],
    pair_links: list[dict[str, Any]],
    max_thickness: float = 2.0,
    include_edge_lenses: bool = True,
) -> list[dict[str, Any]]:
    """V2 korelasyonlarindan coklu sondaj mercek izlerini olusturur."""
    if len(sondajlar) < 2:
        return []

    layers_by_well = [
        sondaj.get("merged_layers_v2") or sondaj.get("merged_layers") or []
        for sondaj in sondajlar
    ]
    predecessor: dict[tuple[int, int], tuple[int, int]] = {}
    successor: dict[tuple[int, int], tuple[int, int]] = {}

    for pair_idx, link in enumerate(pair_links[:len(sondajlar) - 1]):
        for left_idx, right_idx in (link.get("matches_s1") or {}).items():
            left_node = (pair_idx, int(left_idx))
            right_node = (pair_idx + 1, int(right_idx))
            successor[left_node] = right_node
            predecessor[right_node] = left_node

    tracks = []
    visited = set()
    for well_idx, layers in enumerate(layers_by_well):
        for layer_idx, layer in enumerate(layers):
            start_node = (well_idx, layer_idx)
            if start_node in visited or start_node in predecessor:
                continue

            node_keys = []
            current = start_node
            while current not in visited:
                current_well, current_layer = current
                current_layers = layers_by_well[current_well]
                if current_layer < 0 or current_layer >= len(current_layers):
                    break
                visited.add(current)
                node_keys.append(current)
                next_node = successor.get(current)
                if next_node is None:
                    break
                current = next_node

            if not node_keys:
                continue

            first_well_idx, first_layer_idx = node_keys[0]
            last_well_idx, last_layer_idx = node_keys[-1]
            first_layer = layers_by_well[first_well_idx][first_layer_idx]
            code = str(first_layer.get("code") or "")
            correlation_key = code or "tanimsiz"
            if code in ("", "tanimsiz", "bt"):
                continue

            thicknesses = [
                abs(
                    safe_float(layers_by_well[item_well][item_layer].get("bot"))
                    - safe_float(layers_by_well[item_well][item_layer].get("top"))
                )
                for item_well, item_layer in node_keys
            ]
            if any(thickness <= 0.05 for thickness in thicknesses):
                continue
            if max_thickness > 0 and any(thickness > max_thickness for thickness in thicknesses):
                continue

            left_edge = first_well_idx == 0
            right_edge = last_well_idx == len(sondajlar) - 1
            left_transition = (
                not left_edge
                and first_layer_idx
                in (pair_links[first_well_idx - 1].get("facies_s2") or {})
            )
            right_transition = (
                not right_edge
                and last_layer_idx
                in (pair_links[last_well_idx].get("facies_s1") or {})
            )
            if left_transition or right_transition:
                continue

            left_closed = not left_edge
            right_closed = not right_edge
            if not left_closed and not right_closed:
                continue
            edge_lens = left_edge or right_edge
            if edge_lens and not include_edge_lenses:
                continue

            nodes = []
            for item_well, item_layer in node_keys:
                item = layers_by_well[item_well][item_layer]
                nodes.append({
                    "well_index": item_well,
                    "layer_index": item_layer,
                    "well_no": sondajlar[item_well].get("no", f"SK-{item_well + 1}"),
                    "layer": item,
                })

            first_no = str(nodes[0]["well_no"])
            last_no = str(nodes[-1]["well_no"])
            track_id = (
                f"semantic-lens:{first_no}:{last_no}:"
                f"{first_layer_idx}:{last_layer_idx}:{code}:{correlation_key}"
            )
            tracks.append({
                "track_id": track_id,
                "code": code,
                "correlation_key": correlation_key,
                "detail_name": first_layer.get("detail_name", ""),
                "nodes": nodes,
                "node_keys": list(node_keys),
                "start_well_index": first_well_idx,
                "end_well_index": last_well_idx,
                "left_closed": left_closed,
                "right_closed": right_closed,
                "edge_lens": edge_lens,
                "max_thickness": max(thicknesses),
            })

    tracks.sort(
        key=lambda item: (
            item["start_well_index"],
            item["end_well_index"],
            item["nodes"][0]["layer_index"],
        )
    )
    return tracks


def finite_layer_geometry(layer: dict[str, Any]) -> bool:
    values = [safe_float(layer.get("top")), safe_float(layer.get("bot"))]
    return all(math.isfinite(value) for value in values) and values[1] > values[0]
