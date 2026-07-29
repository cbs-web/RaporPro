import re

import numpy as np


class KarotKalibrasyonHatasi(ValueError):
    """Karot sandigi kalibrasyonu guvenilir bir homografi uretmediginde kullanilir."""


def derinlik_araligi_coz(value):
    text = str(value if value is not None else "").strip().replace(",", ".")
    if not text:
        return 0.0, 0.0

    text = text.replace("\u2013", "-").replace("\u2014", "-")
    pair = re.fullmatch(
        r"\s*([+-]?\d+(?:\.\d+)?)\s*(?:-|/)\s*([+-]?\d+(?:\.\d+)?)\s*",
        text,
    )
    if pair:
        top = float(pair.group(1))
        bot = float(pair.group(2))
    else:
        single = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*", text)
        if single:
            top = float(single.group(1))
            bot = top
        else:
            # Eski kayitlarda "D: 12.0 m - 13.5 m" gibi aciklamali metinler bulunabilir.
            parts = re.findall(r"\d+(?:\.\d+)?", text)
            if not parts:
                return 0.0, 0.0
            top = float(parts[0])
            bot = float(parts[1]) if len(parts) >= 2 else top

    if bot < top:
        top, bot = bot, top
    return top, bot


def _aralik_degerleri(interval):
    if isinstance(interval, dict):
        try:
            return float(interval.get("top")), float(interval.get("bot"))
        except (TypeError, ValueError):
            return None
    if isinstance(interval, (list, tuple)) and len(interval) >= 2:
        try:
            return float(interval[0]), float(interval[1])
        except (TypeError, ValueError):
            return None
    if isinstance(interval, str):
        top, bot = derinlik_araligi_coz(interval)
        if top == bot == 0.0 and not re.search(r"\d", interval):
            return None
        return top, bot
    return None


def karot_araliklarini_dogrula(intervals, total_depth=None, tolerance=1e-6):
    """Karot araliklarindaki derinlik, tekrar ve cakisma sorunlarini raporlar."""
    errors = []
    warnings = []
    normalized = []

    try:
        depth_limit = None if total_depth in (None, "") else float(total_depth)
    except (TypeError, ValueError):
        depth_limit = None
        warnings.append(
            {
                "kod": "sondaj_derinligi_gecersiz",
                "mesaj": "Sondaj derinligi sayisal olmadigi icin ust sinir kontrol edilemedi.",
            }
        )

    for index, interval in enumerate(intervals or []):
        values = _aralik_degerleri(interval)
        if values is None or not all(np.isfinite(value) for value in values):
            errors.append(
                {
                    "kod": "aralik_gecersiz",
                    "index": index,
                    "mesaj": f"{index + 1}. derinlik araligi okunamadi.",
                }
            )
            continue
        top, bot = values
        normalized.append({"index": index, "top": top, "bot": bot})
        label = derinlik_araligi_etiketi(top, bot)
        if top < -tolerance:
            errors.append(
                {
                    "kod": "negatif_derinlik",
                    "index": index,
                    "mesaj": f"{label}: derinlik sifirdan kucuk olamaz.",
                }
            )
        if bot <= top + tolerance:
            errors.append(
                {
                    "kod": "bos_aralik",
                    "index": index,
                    "mesaj": f"{label}: bitis derinligi baslangictan buyuk olmali.",
                }
            )
        if depth_limit is not None and bot > depth_limit + tolerance:
            errors.append(
                {
                    "kod": "sondaj_disinda",
                    "index": index,
                    "mesaj": (
                        f"{label}: aralik {depth_limit:.2f} m sondaj derinligini asiyor."
                    ),
                }
            )

    ordered = sorted(normalized, key=lambda item: (item["top"], item["bot"]))
    for previous, current in zip(ordered, ordered[1:]):
        previous_label = derinlik_araligi_etiketi(previous["top"], previous["bot"])
        current_label = derinlik_araligi_etiketi(current["top"], current["bot"])
        same = (
            abs(previous["top"] - current["top"]) <= tolerance
            and abs(previous["bot"] - current["bot"]) <= tolerance
        )
        if same:
            errors.append(
                {
                    "kod": "tekrar_aralik",
                    "index": current["index"],
                    "diger_index": previous["index"],
                    "mesaj": f"{current_label}: ayni derinlik araligi birden fazla kez eklenmis.",
                }
            )
        elif current["top"] < previous["bot"] - tolerance:
            errors.append(
                {
                    "kod": "cakisan_aralik",
                    "index": current["index"],
                    "diger_index": previous["index"],
                    "mesaj": f"{previous_label} ile {current_label} birbiriyle cakisiyor.",
                }
            )

    return {
        "gecerli": not errors,
        "hatalar": errors,
        "uyarilar": warnings,
        "araliklar": normalized,
    }


def _nokta(point):
    try:
        values = np.asarray(point, dtype=float)
    except (TypeError, ValueError) as exc:
        raise KarotKalibrasyonHatasi("Kalibrasyon noktalarindan biri okunamadi.") from exc
    if values.shape != (2,) or not np.all(np.isfinite(values)):
        raise KarotKalibrasyonHatasi("Kalibrasyon noktalari iki sonlu koordinattan olusmali.")
    return values


def _cizgi_uzunlugu(p1, p2):
    return float(np.linalg.norm(p2 - p1))


def _yon(a, b, c):
    ab = b - a
    ac = c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _cizgiler_kesisiyor(a, b, c, d, tolerance=1e-9):
    o1 = _yon(a, b, c)
    o2 = _yon(a, b, d)
    o3 = _yon(c, d, a)
    o4 = _yon(c, d, b)
    return (
        ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance))
        and ((o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance))
    )


def _poligon_alani(points):
    x = points[:, 0]
    y = points[:, 1]
    return abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2.0)


def kalibrasyon_dogrula(top_line, bottom_line):
    """Kalibrasyon dortgenini siralar ve geometri kalite bilgisini dondurur."""
    if (
        top_line is None
        or bottom_line is None
        or len(top_line) != 2
        or len(bottom_line) != 2
    ):
        raise KarotKalibrasyonHatasi(
            "Kalibrasyon icin ust ve alt 1.00 m cizgilerinin ikiser noktasi gereklidir."
        )

    top = [_nokta(point) for point in top_line]
    bottom = [_nokta(point) for point in bottom_line]
    top_length = _cizgi_uzunlugu(top[0], top[1])
    bottom_length = _cizgi_uzunlugu(bottom[0], bottom[1])
    coordinate_scale = max(
        1.0,
        *(abs(float(value)) for point in top + bottom for value in point),
    )
    minimum_length = coordinate_scale * 1e-7
    if top_length <= minimum_length or bottom_length <= minimum_length:
        raise KarotKalibrasyonHatasi(
            "Ust veya alt kalibrasyon cizgisi cok kisa. Iki farkli nokta secin."
        )
    if _cizgiler_kesisiyor(top[0], top[1], bottom[0], bottom[1]):
        raise KarotKalibrasyonHatasi(
            "Ust ve alt kalibrasyon cizgileri birbiriyle kesisemez."
        )

    direct = _cizgi_uzunlugu(top[0], bottom[0]) + _cizgi_uzunlugu(top[1], bottom[1])
    crossed = _cizgi_uzunlugu(top[0], bottom[1]) + _cizgi_uzunlugu(top[1], bottom[0])
    if crossed < direct:
        bottom.reverse()

    polygon = np.array([top[0], top[1], bottom[1], bottom[0]], dtype=float)
    cross_values = [
        _yon(polygon[index], polygon[(index + 1) % 4], polygon[(index + 2) % 4])
        for index in range(4)
    ]
    significant = [value for value in cross_values if abs(value) > coordinate_scale**2 * 1e-10]
    if len(significant) < 4 or not (
        all(value > 0 for value in significant) or all(value < 0 for value in significant)
    ):
        raise KarotKalibrasyonHatasi(
            "Kalibrasyon dortgeni capraz veya cok basik. Ust ve alt cizgileri yeniden secin."
        )

    area = _poligon_alani(polygon)
    if area <= coordinate_scale**2 * 1e-8:
        raise KarotKalibrasyonHatasi(
            "Kalibrasyon alani cok dar. Ust ve alt cizgiler birbirinden ayrik olmali."
        )

    warnings = []
    ratio = max(top_length, bottom_length) / min(top_length, bottom_length)
    if ratio > 3.0:
        warnings.append(
            "Ust ve alt 1 m cizgilerinin gorunen uzunluklari cok farkli; perspektif acisini kontrol edin."
        )

    return {
        "src": np.array([top[0], top[1], bottom[0], bottom[1]], dtype=float),
        "uyarilar": warnings,
        "alan": area,
        "ust_uzunluk": top_length,
        "alt_uzunluk": bottom_length,
    }


def _homografi_ve_kalite(top_line, bottom_line):
    quality = kalibrasyon_dogrula(top_line, bottom_line)
    src = quality["src"]
    dst = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float)
    rows = []
    rhs = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.append(v)
    matrix = np.array(rows, dtype=float)
    condition = np.linalg.cond(matrix)
    if not np.isfinite(condition) or condition > 1e12:
        raise KarotKalibrasyonHatasi(
            "Kalibrasyon geometrisi sayisal olarak kararsiz. Noktalari yeniden secin."
        )
    try:
        coeff = np.linalg.solve(matrix, np.array(rhs, dtype=float))
    except np.linalg.LinAlgError as exc:
        raise KarotKalibrasyonHatasi(
            "Kalibrasyon geometrisinden donusum hesaplanamadi."
        ) from exc
    homography = np.array(
        [
            [coeff[0], coeff[1], coeff[2]],
            [coeff[3], coeff[4], coeff[5]],
            [coeff[6], coeff[7], 1.0],
        ],
        dtype=float,
    )
    return homography, quality


def _segment_donusumu(homography, segment):
    if not isinstance(segment, (list, tuple)) or len(segment) != 2:
        raise ValueError("Karot parcasi iki noktadan olusmali.")
    u1, v1 = noktayi_donustur(homography, segment[0])
    u2, v2 = noktayi_donustur(homography, segment[1])
    return {
        "u1": u1,
        "v1": v1,
        "u2": u2,
        "v2": v2,
        "bas": min(u1, u2),
        "son": max(u1, u2),
        "orta_v": (v1 + v2) / 2.0,
        "uzunluk": abs(u2 - u1),
    }


def _ayni_parca(first, second, tolerance=0.01):
    same_direction = (
        abs(first["u1"] - second["u1"]) <= tolerance
        and abs(first["v1"] - second["v1"]) <= tolerance
        and abs(first["u2"] - second["u2"]) <= tolerance
        and abs(first["v2"] - second["v2"]) <= tolerance
    )
    reverse_direction = (
        abs(first["u1"] - second["u2"]) <= tolerance
        and abs(first["v1"] - second["v2"]) <= tolerance
        and abs(first["u2"] - second["u1"]) <= tolerance
        and abs(first["v2"] - second["v1"]) <= tolerance
    )
    return same_direction or reverse_direction


def _parcalar_cakisiyor(first, second, row_tolerance=0.04, length_tolerance=0.01):
    if abs(first["orta_v"] - second["orta_v"]) > row_tolerance:
        return False
    overlap = min(first["son"], second["son"]) - max(first["bas"], second["bas"])
    return overlap > length_tolerance


def _bos_tcr_sonucu(advance=0.0, errors=None, warnings=None):
    errors = list(errors or [])
    warnings = list(warnings or [])
    return {
        "ilerleme": float(advance),
        "karot": 0.0,
        "tcr": 0.0,
        "ham_karot": 0.0,
        "ham_tcr": 0.0,
        "parca_sayisi": 0,
        "gecerli_parca_sayisi": 0,
        "hatalar": errors,
        "uyarilar": warnings,
        "gecerli": not errors,
    }


def derinlik_baslangic(value):
    return derinlik_araligi_coz(value)[0]


def derinlik_orta(value):
    top, bot = derinlik_araligi_coz(value)
    return (top + bot) / 2 if bot > top else top


def derinlik_araligi_etiketi(top, bot):
    return f"{float(top):.2f}-{float(bot):.2f}"


def standart_karot_araliklari(start=1.5, end=30.0, step=1.5):
    intervals = []
    current = float(start)
    end = float(end)
    step = float(step)
    if step <= 0:
        raise ValueError("Karot aralik adimi sifirdan buyuk olmali.")
    if end < current:
        return intervals
    while current + step <= end + 1e-9:
        intervals.append((round(current, 2), round(current + step, 2)))
        current += step
    return intervals


def ilerleme_metresi(top, bot):
    return max(0.0, float(bot) - float(top))


def homografi_hesapla(top_line, bottom_line):
    homography, _quality = _homografi_ve_kalite(top_line, bottom_line)
    return homography


def noktayi_donustur(homography, point):
    x, y = point
    vec = np.array([float(x), float(y), 1.0], dtype=float)
    out = homography.dot(vec)
    if abs(out[2]) < 1e-12:
        raise KarotKalibrasyonHatasi(
            "Secilen nokta kalibrasyon duzlemine guvenilir bicimde donusturulemedi."
        )
    result = float(out[0] / out[2]), float(out[1] / out[2])
    if not all(np.isfinite(value) for value in result):
        raise KarotKalibrasyonHatasi(
            "Secilen noktanin donusturulmus koordinati sonlu degil."
        )
    return result


def parca_uzunlugu_metre(homography, segment):
    return _segment_donusumu(homography, segment)["uzunluk"]


def tcr_hesapla(top, bot, segments, top_line, bottom_line):
    advance = ilerleme_metresi(top, bot)
    if advance <= 0:
        return _bos_tcr_sonucu(
            errors=["Bitiş derinliği başlangıç derinliğinden büyük olmalıdır."]
        )

    homography, calibration_quality = _homografi_ve_kalite(top_line, bottom_line)
    errors = []
    warnings = list(calibration_quality["uyarilar"])
    transformed = []
    accepted = []
    raw_core_length = 0.0

    for index, segment in enumerate(segments or []):
        try:
            item = _segment_donusumu(homography, segment)
        except (TypeError, ValueError, KarotKalibrasyonHatasi) as exc:
            errors.append(f"{index + 1}. karot parcasi okunamadi: {exc}")
            continue
        item["index"] = index
        raw_core_length += item["uzunluk"]

        if item["uzunluk"] <= 1e-6:
            errors.append(f"{index + 1}. karot parcasinin uzunlugu sifir.")
            continue
        if any(
            value < -0.03 or value > 1.03
            for value in (item["u1"], item["u2"], item["v1"], item["v2"])
        ):
            errors.append(
                f"{index + 1}. karot parcasi kalibre edilen sandik alaninin disina tasiyor."
            )
        if abs(item["v1"] - item["v2"]) > 0.12:
            warnings.append(
                f"{index + 1}. karot parcasi belirgin egik; iki ucun ayni sandik sirasinda oldugunu kontrol edin."
            )

        duplicate_of = next(
            (other for other in transformed if _ayni_parca(item, other)),
            None,
        )
        if duplicate_of is not None:
            errors.append(
                f"{index + 1}. karot parcasi {duplicate_of['index'] + 1}. parcanin tekrari."
            )
            transformed.append(item)
            continue

        overlap_with = next(
            (other for other in accepted if _parcalar_cakisiyor(item, other)),
            None,
        )
        if overlap_with is not None:
            errors.append(
                f"{index + 1}. karot parcasi {overlap_with['index'] + 1}. parca ile ayni sirada cakisiyor."
            )

        transformed.append(item)
        accepted.append(item)

    core_length = sum(item["uzunluk"] for item in accepted)
    raw_tcr = (core_length / advance) * 100.0
    input_tcr = (raw_core_length / advance) * 100.0
    if raw_tcr > 100.0 + 0.5:
        errors.append(
            f"Toplam karot uzunlugu ilerleme metresini asiyor (ham TCR %{raw_tcr:.1f})."
        )
    if not segments:
        warnings.append("Bu aralikta karot parcasi isaretlenmedi; TCR %0 kabul edilir.")

    tcr = max(0.0, min(100.0, raw_tcr))
    return {
        "ilerleme": advance,
        "karot": core_length,
        "tcr": tcr,
        "ham_karot": raw_core_length,
        "ham_tcr": input_tcr,
        "parca_sayisi": len(segments or []),
        "gecerli_parca_sayisi": len(accepted),
        "hatalar": errors,
        "uyarilar": warnings,
        "gecerli": not errors,
    }


def _saglam_parcalari_degerlendir(homography, segments):
    errors = []
    warnings = []
    transformed = []
    accepted = []

    for index, segment in enumerate(segments or []):
        try:
            item = _segment_donusumu(homography, segment)
        except (TypeError, ValueError, KarotKalibrasyonHatasi) as exc:
            errors.append(f"{index + 1}. saglam karot parcasi okunamadi: {exc}")
            continue
        item["index"] = index

        if item["uzunluk"] <= 1e-6:
            errors.append(f"{index + 1}. saglam karot parcasinin uzunlugu sifir.")
            continue
        if any(
            value < -0.03 or value > 1.03
            for value in (item["u1"], item["u2"], item["v1"], item["v2"])
        ):
            errors.append(
                f"{index + 1}. saglam karot parcasi kalibre edilen sandik alaninin disina tasiyor."
            )
        if abs(item["v1"] - item["v2"]) > 0.12:
            warnings.append(
                f"{index + 1}. saglam karot parcasi belirgin egik; iki ucun ayni sandik sirasinda oldugunu kontrol edin."
            )

        duplicate_of = next(
            (other for other in transformed if _ayni_parca(item, other)),
            None,
        )
        if duplicate_of is not None:
            errors.append(
                f"{index + 1}. saglam karot parcasi "
                f"{duplicate_of['index'] + 1}. parcanin tekrari."
            )
            transformed.append(item)
            continue

        overlap_with = next(
            (other for other in accepted if _parcalar_cakisiyor(item, other)),
            None,
        )
        if overlap_with is not None:
            errors.append(
                f"{index + 1}. saglam karot parcasi "
                f"{overlap_with['index'] + 1}. parca ile ayni sirada cakisiyor."
            )

        transformed.append(item)
        accepted.append(item)

    return accepted, errors, warnings


def _tcr_parcasi_saglam_parcayi_kapsiyor(
    tcr_item,
    solid_item,
    row_tolerance=0.08,
    length_tolerance=0.03,
):
    return (
        abs(tcr_item["orta_v"] - solid_item["orta_v"]) <= row_tolerance
        and solid_item["bas"] >= tcr_item["bas"] - length_tolerance
        and solid_item["son"] <= tcr_item["son"] + length_tolerance
    )


def karot_kalite_hesapla(
    top,
    bot,
    segments,
    solid_segments,
    top_line,
    bottom_line,
    quality_assessed=False,
    rqd_minimum=0.10,
):
    """TCR, SCR ve RQD degerlerini ayni kalibrasyon geometrisinden hesaplar."""
    result = tcr_hesapla(top, bot, segments, top_line, bottom_line)
    assessed = bool(quality_assessed or solid_segments)
    result.update(
        {
            "saglam_karot": None,
            "scr": None,
            "rqd_karot": None,
            "rqd": None,
            "saglam_parca_sayisi": len(solid_segments or []),
            "rqd_parca_sayisi": 0,
            "kalite_tamam": assessed,
            "kalite_bekliyor": not assessed,
            "rqd_esigi": float(rqd_minimum),
        }
    )
    if not assessed:
        return result

    try:
        threshold = float(rqd_minimum)
    except (TypeError, ValueError) as exc:
        raise ValueError("RQD parca esigi sayisal olmali.") from exc
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("RQD parca esigi sifirdan buyuk olmali.")

    homography, _quality = _homografi_ve_kalite(top_line, bottom_line)
    accepted, solid_errors, solid_warnings = _saglam_parcalari_degerlendir(
        homography,
        solid_segments,
    )
    result["hatalar"].extend(solid_errors)
    result["uyarilar"].extend(solid_warnings)

    transformed_tcr = []
    for segment in segments or []:
        try:
            item = _segment_donusumu(homography, segment)
        except (TypeError, ValueError, KarotKalibrasyonHatasi):
            continue
        if item["uzunluk"] > 1e-6:
            transformed_tcr.append(item)

    for item in accepted:
        if transformed_tcr and not any(
            _tcr_parcasi_saglam_parcayi_kapsiyor(tcr_item, item)
            for tcr_item in transformed_tcr
        ):
            result["uyarilar"].append(
                f"{item['index'] + 1}. saglam parca bir TCR parcasi icinde gorunmuyor."
            )

    solid_length = sum(item["uzunluk"] for item in accepted)
    rqd_items = [
        item
        for item in accepted
        if item["uzunluk"] + 1e-9 >= threshold
    ]
    rqd_length = sum(item["uzunluk"] for item in rqd_items)
    advance = result["ilerleme"]
    raw_scr = (solid_length / advance) * 100.0 if advance > 0 else 0.0
    raw_rqd = (rqd_length / advance) * 100.0 if advance > 0 else 0.0

    if raw_scr > 100.0 + 0.5:
        result["hatalar"].append(
            f"Toplam saglam karot uzunlugu ilerleme metresini asiyor (ham SCR %{raw_scr:.1f})."
        )
    if solid_length > result["karot"] + 0.005:
        result["hatalar"].append(
            "Saglam karot uzunlugu toplam geri kazanilan karot uzunlugunu asamaz."
        )

    scr = max(0.0, min(100.0, raw_scr))
    rqd = max(0.0, min(100.0, raw_rqd))
    if rqd > scr + 1e-6 or scr > result["tcr"] + 0.5:
        result["hatalar"].append("RQD <= SCR <= TCR kosulu saglanmiyor.")

    result.update(
        {
            "saglam_karot": solid_length,
            "scr": scr,
            "rqd_karot": rqd_length,
            "rqd": rqd,
            "saglam_parca_sayisi": len(accepted),
            "rqd_parca_sayisi": len(rqd_items),
            "ham_scr": raw_scr,
            "ham_rqd": raw_rqd,
            "rqd_esigi": threshold,
            "gecerli": not result["hatalar"],
        }
    )
    return result
