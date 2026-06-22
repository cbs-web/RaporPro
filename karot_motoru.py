import re

import numpy as np


def derinlik_araligi_coz(value):
    text = str(value if value is not None else "").strip().replace(",", ".")
    if not text:
        return 0.0, 0.0
    parts = re.findall(r"\d+(?:\.\d+)?", text)
    if not parts:
        return 0.0, 0.0
    top = float(parts[0])
    if len(parts) >= 2:
        bot = float(parts[1])
    else:
        bot = top
    if bot < top:
        top, bot = bot, top
    return top, bot


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
    while current + step <= end + 1e-9:
        intervals.append((round(current, 2), round(current + step, 2)))
        current += step
    return intervals


def ilerleme_metresi(top, bot):
    return max(0.0, float(bot) - float(top))


def homografi_hesapla(top_line, bottom_line):
    src = np.array(
        [
            top_line[0],
            top_line[1],
            bottom_line[0],
            bottom_line[1],
        ],
        dtype=float,
    )
    if src.shape != (4, 2):
        raise ValueError("Kalibrasyon icin ust ve alt 1 m cizgileri gereklidir.")

    if src[0, 0] > src[1, 0]:
        src[[0, 1]] = src[[1, 0]]
    if src[2, 0] > src[3, 0]:
        src[[2, 3]] = src[[3, 2]]

    dst = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float)
    rows = []
    rhs = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.append(v)
    coeff = np.linalg.solve(np.array(rows, dtype=float), np.array(rhs, dtype=float))
    return np.array(
        [
            [coeff[0], coeff[1], coeff[2]],
            [coeff[3], coeff[4], coeff[5]],
            [coeff[6], coeff[7], 1.0],
        ],
        dtype=float,
    )


def noktayi_donustur(homography, point):
    x, y = point
    vec = np.array([float(x), float(y), 1.0], dtype=float)
    out = homography.dot(vec)
    if abs(out[2]) < 1e-12:
        return 0.0, 0.0
    return float(out[0] / out[2]), float(out[1] / out[2])


def parca_uzunlugu_metre(homography, segment):
    p1, p2 = segment
    u1, _ = noktayi_donustur(homography, p1)
    u2, _ = noktayi_donustur(homography, p2)
    return abs(u2 - u1)


def tcr_hesapla(top, bot, segments, top_line, bottom_line):
    advance = ilerleme_metresi(top, bot)
    if advance <= 0:
        return {"ilerleme": 0.0, "karot": 0.0, "tcr": 0.0}
    homography = homografi_hesapla(top_line, bottom_line)
    core_length = sum(parca_uzunlugu_metre(homography, segment) for segment in segments or [])
    tcr = max(0.0, min(100.0, (core_length / advance) * 100.0))
    return {"ilerleme": advance, "karot": core_length, "tcr": tcr}
