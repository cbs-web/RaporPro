# Dosya: RaporPro/sondaj_derinlik.py
import math
import re


def _float(value):
    try:
        return float(str(value or "").strip().replace(",", "."))
    except Exception:
        return 0.0


def _blank(value):
    return value is None or str(value).strip() in {"", "-", "None", "null"}


def _round_up(value, step=1.5):
    value = _float(value)
    step = _float(step) or 1.5
    if value <= 0:
        return 0.0
    return round(math.ceil((value - 1e-9) / step) * step, 2)


def _positive(value):
    value = _float(value)
    return value if value > 0 else 0.0


def _default_su_bha(dogal_bha, doygun_bha):
    return 9.81 if max(_float(dogal_bha), _float(doygun_bha)) > 5 else 1.0


def _kategori_no(kategori):
    text = str(kategori or "").lower()
    match = re.search(r"([123])", text)
    return int(match.group(1)) if match else 2


def _plan_genisligi(plan):
    nums = [_float(item) for item in re.findall(r"\d+(?:[,.]\d+)?", str(plan or ""))]
    nums = [item for item in nums if item > 0]
    return min(nums) if len(nums) >= 2 else 0.0


def temel_genisligi_bul(bina):
    explicit = _float((bina or {}).get("temel_genislik"))
    if explicit > 0:
        return explicit, "Temel genişliği B"
    from_plan = _plan_genisligi((bina or {}).get("plan"))
    if from_plan > 0:
        return from_plan, "Plan boyutlarından küçük kenar"
    area = _float((bina or {}).get("temel_alan"))
    if area > 0:
        return round(math.sqrt(area), 2), "Temel alanından kare eşdeğer"
    return 0.0, "Girilmedi"


def bina_bloklari_al(veri):
    bina = (veri or {}).get("bina", {}) or {}
    bloklar = bina.get("bloklar") if isinstance(bina.get("bloklar"), list) else []
    if bina.get("coklu_blok") and bloklar:
        cleaned = []
        for idx, blok in enumerate(bloklar, start=1):
            if isinstance(blok, dict) and any(str(v or "").strip() for v in blok.values()):
                item = dict(blok)
                item.setdefault("blok_adi", f"Blok {idx}")
                cleaned.append(item)
        if cleaned:
            return cleaned
    item = dict(bina)
    item.setdefault("blok_adi", "Tek Bina")
    return [item]


def gerilme_artisi_2_1(q_net, b, l, z):
    q_net = _positive(q_net)
    b = _positive(b)
    l = _positive(l)
    z = max(0.0, _float(z))
    if not (q_net and b and l):
        return 0.0
    return q_net * b * l / ((b + z) * (l + z))


def boussinesq_katsayisi(m, n):
    m = _positive(m)
    n = _positive(n)
    if not (m and n):
        return 0.0
    kok = math.sqrt(m * m + n * n + 1.0)
    ilk = (2.0 * m * n * kok) / (m * m + n * n + m * m * n * n + 1.0)
    ilk *= (m * m + n * n + 2.0) / (m * m + n * n + 1.0)
    payda = m * m + n * n - m * m * n * n + 1.0
    pay = 2.0 * m * n * kok
    if abs(payda) < 1e-12:
        aci = math.pi / 2.0
    else:
        aci = math.atan(pay / payda)
        if payda < 0:
            aci += math.pi
    return (ilk + aci) / (4.0 * math.pi)


def westergaard_katsayisi(m, n):
    m = _positive(m)
    n = _positive(n)
    if not (m and n):
        return 0.0
    payda = math.sqrt(1.0 + 2.0 * m * m + 2.0 * n * n)
    return math.atan((2.0 * m * n) / payda) / (2.0 * math.pi)


def gerilme_artisi_boussinesq(q_net, b, l, depth):
    q_net = _positive(q_net)
    b = _positive(b)
    l = _positive(l)
    depth = _positive(depth)
    if not (q_net and b and l and depth):
        return 0.0
    m = b / (2.0 * depth)
    n = l / (2.0 * depth)
    return 4.0 * q_net * boussinesq_katsayisi(m, n)


def gerilme_artisi_westergaard(q_net, b, l, depth):
    q_net = _positive(q_net)
    b = _positive(b)
    l = _positive(l)
    depth = _positive(depth)
    if not (q_net and b and l and depth):
        return 0.0
    m = b / (2.0 * depth)
    n = l / (2.0 * depth)
    return 4.0 * q_net * westergaard_katsayisi(m, n)


def _excel_yontem_gerilme_artisi(yontem, q_net, b, l, depth):
    if yontem == "boussinesq":
        return gerilme_artisi_boussinesq(q_net, b, l, depth)
    if yontem == "westergaard":
        return gerilme_artisi_westergaard(q_net, b, l, depth)
    return gerilme_artisi_2_1(q_net, b, l, depth)


def _excel_yontem_adi(yontem):
    return {
        "boussinesq": "Boussinesq",
        "westergaard": "Westergaard",
        "yaklasik": "Yaklaşık Yöntem (1/2)",
        "en_elverissiz": "En elverişsiz sonuç",
    }.get(yontem, str(yontem or ""))


def _surekli_esik_derinligi(ratio_func, start_depth, max_depth, target_ratio):
    """Kademeli Excel taramasını bağımsız ikili aramayla doğrula."""
    start_depth = max(0.0, _float(start_depth))
    max_depth = max(start_depth, _float(max_depth))
    if ratio_func(start_depth) <= target_ratio:
        return start_depth
    if ratio_func(max_depth) > target_ratio:
        return None
    low, high = start_depth, max_depth
    for _ in range(80):
        middle = (low + high) / 2.0
        if ratio_func(middle) <= target_ratio:
            high = middle
        else:
            low = middle
    return high


def efektif_gerilme_yass(depth, yass, dogal_bha, doygun_bha, su_bha=1.0):
    depth = max(0.0, _float(depth))
    yass = max(0.0, _float(yass))
    dogal_bha = _positive(dogal_bha)
    doygun_bha = _positive(doygun_bha)
    su_bha = _positive(su_bha) or 1.0
    if depth <= 0:
        return 0.0
    if depth <= yass:
        return dogal_bha * depth
    ust = dogal_bha * yass
    efektif_doygun = max(0.0, doygun_bha - su_bha)
    alt = efektif_doygun * (depth - yass)
    return ust + alt


def efektif_dusey_gerilme(bha, temel_derinligi, z):
    bha = _positive(bha)
    depth = max(0.0, _float(temel_derinligi) + _float(z))
    return bha * depth if bha else 0.0


def gerilme_orani(q_net, b, l, temel_derinligi, bha, z):
    sigma_vo = efektif_dusey_gerilme(bha, temel_derinligi, z)
    delta_sigma = gerilme_artisi_2_1(q_net, b, l, z)
    if sigma_vo <= 0:
        return float("inf") if delta_sigma > 0 else 0.0
    return delta_sigma / sigma_vo


def gerilme_yuzde_on_derinlik_hesapla(params):
    params = params or {}
    b = _positive(params.get("temel_genisligi") if not _blank(params.get("temel_genisligi")) else params.get("b"))
    l = _positive(params.get("temel_uzunlugu") if not _blank(params.get("temel_uzunlugu")) else params.get("l"))
    temel_derinligi_raw = _float(params.get("temel_derinligi"))
    temel_derinligi = max(0.0, temel_derinligi_raw)
    q_taban = _positive(params.get("temel_taban_gerilmesi"))
    q_net_input = _positive(params.get("q_net"))
    yass = _float(params.get("yass")) if not _blank(params.get("yass")) else None
    dogal_bha = _positive(params.get("dogal_bha"))
    doygun_bha = _positive(params.get("doygun_bha"))
    su_bha = _positive(params.get("su_bha")) or _default_su_bha(dogal_bha, doygun_bha)
    bha = _positive(params.get("bha"))
    target_ratio = _float(params.get("target_ratio")) if not _blank(params.get("target_ratio")) else 0.10
    round_step = _float(params.get("round_step")) if not _blank(params.get("round_step")) else 1.0
    max_depth = _float(params.get("max_depth")) if not _blank(params.get("max_depth")) else 200.0
    secili_yontem = str(params.get("hesap_yontemi") or "en_elverissiz").strip().lower()
    if secili_yontem not in {"boussinesq", "westergaard", "yaklasik", "en_elverissiz"}:
        secili_yontem = "en_elverissiz"
    uses_yass_model = bool(q_taban and yass is not None and dogal_bha and doygun_bha)

    errors = []
    if temel_derinligi_raw < 0:
        errors.append("Temel taban derinliği Df negatif olamaz.")
    if yass is not None and yass < 0:
        errors.append("YASS negatif olamaz; zemin yüzeyinden itibaren metre olarak girilmeli.")
    if not (0 < target_ratio < 1):
        errors.append("Hedef oran 0 ile 1 arasında olmalı (örneğin 0.10).")
    if not (0 < round_step <= 10):
        errors.append("Hesap adımı 0 ile 10 m arasında olmalı.")
    if max_depth <= 0:
        errors.append("Maksimum arama derinliği sıfırdan büyük olmalı.")
    for label, value in [
        ("Temel kısa kenarı B", b),
        ("Temel uzun kenarı L", l),
    ]:
        if value <= 0:
            errors.append(f"{label} sıfırdan büyük olmalı.")
    if uses_yass_model:
        if doygun_bha <= su_bha:
            errors.append("Doygun BHA, suyun BHA değerinden büyük olmalı.")
        if doygun_bha + 1e-9 < dogal_bha:
            errors.append("Doygun BHA, doğal BHA değerinden küçük olamaz.")
        if (dogal_bha <= 5 < doygun_bha) or (doygun_bha <= 5 < dogal_bha):
            errors.append("Doğal ve doygun BHA aynı birim sisteminde girilmeli.")
    else:
        if q_net_input <= 0:
            errors.append("Net temel taban basıncı qnet veya yeni hesap için temel taban gerilmesi girilmeli.")
        if bha <= 0:
            errors.append("Efektif BHA veya yeni hesap için doğal/doygun BHA girilmeli.")
    if l and b and l < b:
        b, l = l, b
    if max_depth <= max(temel_derinligi, round_step):
        errors.append("Maksimum arama derinliği, başlangıç hesap derinliğinden büyük olmalı.")

    if errors:
        return {"ok": False, "errors": errors}

    if uses_yass_model:
        sigma_vo_taban = efektif_gerilme_yass(temel_derinligi, yass, dogal_bha, doygun_bha, su_bha)
        q_net = q_taban - sigma_vo_taban

        def sigma_vo_at(depth):
            return efektif_gerilme_yass(depth, yass, dogal_bha, doygun_bha, su_bha)
    else:
        sigma_vo_taban = efektif_dusey_gerilme(bha, temel_derinligi, 0)
        q_net = q_net_input

        def sigma_vo_at(depth):
            return bha * max(0.0, _float(depth))

    if q_net <= 0:
        return {
            "ok": False,
            "errors": [
                "Hesaplanan qnet sıfır veya negatif çıktı.",
                f"qnet = temel taban gerilmesi - σ'vo(taban) = {q_taban:.3f} - {sigma_vo_taban:.3f} = {q_net:.3f}",
            ],
        }

    def ratio_at(yontem, depth):
        sigma_vo = sigma_vo_at(depth)
        delta_sigma = _excel_yontem_gerilme_artisi(yontem, q_net, b, l, depth)
        if sigma_vo <= 0:
            return float("inf") if delta_sigma > 0 else 0.0
        return delta_sigma / sigma_vo

    yontemler = ["boussinesq", "westergaard", "yaklasik"]
    start_depth = max(temel_derinligi, round_step)
    yontem_sonuclari = {}
    for yontem in yontemler:
        continuous_root = _surekli_esik_derinligi(
            lambda current_depth, method=yontem: ratio_at(method, current_depth),
            start_depth,
            max_depth,
            target_ratio,
        )
        depth = start_depth
        solved = False
        while depth <= max_depth + 1e-9:
            if ratio_at(yontem, depth) <= target_ratio:
                solved = True
                break
            depth += round_step
        if not solved:
            depth = max_depth
        sigma_vo = sigma_vo_at(depth)
        delta_sigma = _excel_yontem_gerilme_artisi(yontem, q_net, b, l, depth)
        if continuous_root is None:
            expected_discrete = None
            verified = not solved
        else:
            step_count = max(0, math.ceil(((continuous_root - start_depth) - 1e-9) / round_step))
            expected_discrete = start_depth + step_count * round_step
            verified = solved and abs(depth - expected_discrete) <= 1e-7
        yontem_sonuclari[yontem] = {
            "yontem": yontem,
            "ad": _excel_yontem_adi(yontem),
            "solved": solved,
            "sondaj_derinligi": round(depth, 3),
            "sondaj_derinligi_yuvarlatilmis": _round_up(depth, round_step),
            "temel_alti_z": round(max(0.0, depth - temel_derinligi), 3),
            "delta_sigma": round(delta_sigma, 3),
            "sigma_vo": round(sigma_vo, 3),
            "oran": delta_sigma / sigma_vo if sigma_vo > 0 else float("inf"),
            "surekli_kok_derinligi": round(continuous_root, 6) if continuous_root is not None else None,
            "beklenen_kademeli_derinlik": round(expected_discrete, 6) if expected_discrete is not None else None,
            "dogrulandi": verified,
        }

    failed_validation = [item["ad"] for item in yontem_sonuclari.values() if not item["dogrulandi"]]
    if failed_validation:
        return {
            "ok": False,
            "errors": ["Sayısal hesap doğrulaması başarısız: " + ", ".join(failed_validation)],
        }

    if secili_yontem == "en_elverissiz":
        governing_key = max(yontem_sonuclari, key=lambda item: yontem_sonuclari[item]["sondaj_derinligi_yuvarlatilmis"])
    else:
        governing_key = secili_yontem
    governing = yontem_sonuclari[governing_key]
    total_depth = governing["sondaj_derinligi"]
    rounded_depth = governing["sondaj_derinligi_yuvarlatilmis"]
    z_solution = max(0.0, total_depth - temel_derinligi)
    solved = governing["solved"]
    rows = []
    table_step = max(0.5, round_step)
    depth = start_depth
    max_solution_depth = max(item["sondaj_derinligi"] for item in yontem_sonuclari.values())
    limit = min(max_depth, max(max_solution_depth + 3 * table_step, start_depth + table_step * 8))
    while depth <= limit + 1e-9:
        sigma_vo = sigma_vo_at(depth)
        deltas = {
            yontem: _excel_yontem_gerilme_artisi(yontem, q_net, b, l, depth)
            for yontem in yontemler
        }
        rows.append({
            "derinlik": round(depth, 2),
            "z": round(max(0.0, depth - temel_derinligi), 2),
            "toplam_derinlik": round(depth, 2),
            "sigma_vo": round(sigma_vo, 3),
            "m": round(b / (2.0 * depth), 4) if depth > 0 else 0.0,
            "n": round(l / (2.0 * depth), 4) if depth > 0 else 0.0,
            "boussinesq_delta": round(deltas["boussinesq"], 3),
            "westergaard_delta": round(deltas["westergaard"], 3),
            "yaklasik_delta": round(deltas["yaklasik"], 3),
            "boussinesq_oran": deltas["boussinesq"] / sigma_vo if sigma_vo > 0 else float("inf"),
            "westergaard_oran": deltas["westergaard"] / sigma_vo if sigma_vo > 0 else float("inf"),
            "yaklasik_oran": deltas["yaklasik"] / sigma_vo if sigma_vo > 0 else float("inf"),
        })
        depth += table_step

    return {
        "ok": True,
        "solved": solved,
        "method": "Excel mantığı: Boussinesq / Westergaard / Yaklaşık",
        "hesap_yontemi": secili_yontem,
        "belirleyici_yontem": governing_key,
        "belirleyici_yontem_adi": _excel_yontem_adi(governing_key),
        "yontem_sonuclari": yontem_sonuclari,
        "uses_yass_model": uses_yass_model,
        "q_taban": q_taban,
        "sigma_vo_taban": round(sigma_vo_taban, 3),
        "q_net": q_net,
        "b": b,
        "l": l,
        "temel_derinligi": temel_derinligi,
        "bha": bha,
        "yass": yass,
        "dogal_bha": dogal_bha,
        "doygun_bha": doygun_bha,
        "su_bha": su_bha,
        "target_ratio": target_ratio,
        "round_step": round_step,
        "max_depth": max_depth,
        "gerilme_birimi": "kPa" if max(dogal_bha, doygun_bha, bha) > 5 else "t/m²",
        "bha_birimi": "kN/m³" if max(dogal_bha, doygun_bha, bha) > 5 else "t/m³",
        "sayisal_dogrulama": {
            "ok": True,
            "yontemler": {key: value["dogrulandi"] for key, value in yontem_sonuclari.items()},
        },
        "z_solution": round(z_solution, 3),
        "temel_alti_z": round(z_solution, 3),
        "sondaj_derinligi": round(total_depth, 3),
        "sondaj_derinligi_yuvarlatilmis": rounded_depth,
        "delta_sigma": governing["delta_sigma"],
        "sigma_vo": governing["sigma_vo"],
        "oran": governing["oran"],
        "rows": rows,
        "errors": [],
    }


def gerilme_yuzde_on_ozet_metni(params):
    result = gerilme_yuzde_on_derinlik_hesapla(params)
    if not result.get("ok"):
        return "Hesap yapılamadı:\n" + "\n".join(f"- {item}" for item in result.get("errors", []))

    def oran_metni(value):
        return "∞" if math.isinf(value) else f"%{value * 100:.2f}"

    lines = [
        "GERİLME ARTIŞINA GÖRE SONDAJ DERİNLİĞİ HESABI",
        "",
        "Koşul: Δσ = 0.10 σ'vo",
        "Yöntem: Excel mantığı - Boussinesq, Westergaard ve Yaklaşık Yöntem",
        "Derinlik hesabında Exceldeki gibi zemin yüzeyinden itibaren derinlik kullanılır.",
        "",
        f"Temel taban gerilmesi: {result['q_taban']:.3f}" if result.get("uses_yass_model") else f"qnet: {result['q_net']:.3f}",
        f"σ'vo(taban): {result['sigma_vo_taban']:.3f}" if result.get("uses_yass_model") else "",
        f"Hesaplanan qnet: {result['q_net']:.3f}" if result.get("uses_yass_model") else "",
        f"B x L: {result['b']:.2f} m x {result['l']:.2f} m",
        f"Temel derinliği Df: {result['temel_derinligi']:.2f} m",
        f"YASS: {result['yass']:.2f} m" if result.get("uses_yass_model") else f"Efektif BHA γ': {result['bha']:.3f}",
        f"Doğal BHA: {result['dogal_bha']:.3f}, Doygun BHA: {result['doygun_bha']:.3f}, Su BHA: {result['su_bha']:.3f}" if result.get("uses_yass_model") else "",
        f"Hedef oran: %{result['target_ratio'] * 100:.1f}",
        f"Birim sistemi: gerilme {result['gerilme_birimi']}, birim hacim ağırlığı {result['bha_birimi']}",
        "Sayısal çapraz doğrulama: BAŞARILI",
        "",
        "Yöntem sonuçları:",
    ]
    for key in ["boussinesq", "westergaard", "yaklasik"]:
        item = result.get("yontem_sonuclari", {}).get(key, {})
        if item:
            lines.append(
                f"- {item['ad']}: {item['sondaj_derinligi_yuvarlatilmis']:.2f} m "
                f"(Δσ={item['delta_sigma']:.3f}, σ'vo={item['sigma_vo']:.3f}, "
                f"oran={oran_metni(item['oran'])})"
            )
    lines.extend([
        "",
        f"Belirleyici yöntem: {result['belirleyici_yontem_adi']}",
        f"Temel tabanı altında kalan Z: {result['temel_alti_z']:.2f} m",
        f"Zemin yüzeyinden gerekli sondaj derinliği: {result['sondaj_derinligi_yuvarlatilmis']:.2f} m",
        f"Kontrol: Δσ={result['delta_sigma']:.3f}, σ'vo={result['sigma_vo']:.3f}, Δσ/σ'vo={oran_metni(result['oran'])}",
        "",
        "Derinlik tablosu:",
        "Der.(m) | Z(m) | m | n | σ'vo | Bouss.Δσ | West.Δσ | Yak.Δσ",
    ])
    for row in result.get("rows", []):
        lines.append(
            f"{row['derinlik']:>7.2f} | {row['z']:>4.2f} | {row['m']:>5.3f} | {row['n']:>5.3f} | "
            f"{row['sigma_vo']:>6.3f} | {row['boussinesq_delta']:>9.3f} | "
            f"{row['westergaard_delta']:>8.3f} | {row['yaklasik_delta']:>7.3f}"
        )
    if not result.get("solved"):
        lines.extend([
            "",
            f"Not: Hedef oran {result['max_depth']:.2f} m arama sınırında da sağlanamadı. Maksimum arama derinliğini artırın veya girdileri kontrol edin.",
        ])
    return "\n".join(lines)


def sondaj_derinligi_hesapla(veri):
    """
    Zemin ve Temel Etüdü uygulama esaslarına uyumlu pratik ön boyutlandırma.

    Bu hesap kesin tasarım yerine, rapor hazırlarken sondajların yeterli minimum
    araştırma derinliğine ulaşıp ulaşmadığını hızlı kontrol etmek içindir.
    """
    veri = veri or {}
    kategori = _kategori_no((veri.get("arazi") or {}).get("kategori"))
    cat_rules = {
        1: {"min_below": 6.0, "b_factor": 1.0, "h_factor": 0.25},
        2: {"min_below": 15.0, "b_factor": 1.5, "h_factor": 0.33},
        3: {"min_below": 20.0, "b_factor": 2.0, "h_factor": 0.50},
    }
    rule = cat_rules.get(kategori, cat_rules[2])

    block_results = []
    warnings = []
    for block in bina_bloklari_al(veri):
        name = str(block.get("blok_adi") or "Bina").strip()
        kazı = _float(block.get("der"))
        height = _float(block.get("yukseklik"))
        floors = _float(block.get("kat"))
        if height <= 0 and floors > 0:
            height = floors * 3.0
        width, width_source = temel_genisligi_bul(block)

        below_candidates = [
            ("Kategori minimumu", rule["min_below"]),
        ]
        if width > 0:
            below_candidates.append((f"{rule['b_factor']:g}B temel genişliği", rule["b_factor"] * width))
        else:
            warnings.append(f"{name}: etkili temel genişliği B girilmedi.")
        if height > 0:
            below_candidates.append((f"{rule['h_factor']:g}Hn yapı yüksekliği", rule["h_factor"] * height))
        else:
            warnings.append(f"{name}: yapı yüksekliği Hn girilmedi.")

        governing_label, below_foundation = max(below_candidates, key=lambda item: item[1])
        total = _round_up(kazı + below_foundation)
        block_results.append({
            "blok_adi": name,
            "kategori": kategori,
            "kazı_derinliği": kazı,
            "temel_genisligi": width,
            "temel_genisligi_kaynagi": width_source,
            "yapi_yuksekligi": height,
            "temel_alti_arastirma": round(below_foundation, 2),
            "belirleyici_kriter": governing_label,
            "onerilen_sondaj_derinligi": total,
        })

    recommended = max((item["onerilen_sondaj_derinligi"] for item in block_results), default=0.0)
    sondajlar = (veri.get("sondaj") or []) if isinstance(veri.get("sondaj"), list) else []
    current_depths = []
    short = []
    for idx, sondaj in enumerate(sondajlar, start=1):
        depth = _float((sondaj or {}).get("der"))
        no = str((sondaj or {}).get("no") or f"SK-{idx}").strip()
        if depth > 0:
            current_depths.append(depth)
            if recommended > 0 and depth + 0.05 < recommended:
                short.append({"sondaj": no, "derinlik": depth, "eksik": round(recommended - depth, 2)})

    return {
        "kategori": kategori,
        "onerilen_sondaj_derinligi": recommended,
        "bloklar": block_results,
        "uyarilar": warnings,
        "mevcut_en_kisa": min(current_depths) if current_depths else 0.0,
        "mevcut_en_derin": max(current_depths) if current_depths else 0.0,
        "mevcut_ortalama": round(sum(current_depths) / len(current_depths), 2) if current_depths else 0.0,
        "eksik_sondajlar": short,
    }


def sondaj_derinligi_kontrol_sonucu(veri):
    veri = veri or {}
    manual = veri.get("sondaj_derinlik_hesabi") or {}
    stress = gerilme_yuzde_on_derinlik_hesapla(manual)
    if stress.get("ok"):
        sondajlar = (veri.get("sondaj") or []) if isinstance(veri.get("sondaj"), list) else []
        current_depths = []
        short = []
        recommended = stress["sondaj_derinligi_yuvarlatilmis"]
        for idx, sondaj in enumerate(sondajlar, start=1):
            depth = _float((sondaj or {}).get("der"))
            no = str((sondaj or {}).get("no") or f"SK-{idx}").strip()
            if depth > 0:
                current_depths.append(depth)
                if depth + 0.05 < recommended:
                    short.append({"sondaj": no, "derinlik": depth, "eksik": round(recommended - depth, 2)})
        return {
            "hesap_tipi": "gerilme_10",
            "kategori": _kategori_no((veri.get("arazi") or {}).get("kategori")),
            "onerilen_sondaj_derinligi": recommended,
            "bloklar": [],
            "uyarilar": [],
            "mevcut_en_kisa": min(current_depths) if current_depths else 0.0,
            "mevcut_en_derin": max(current_depths) if current_depths else 0.0,
            "mevcut_ortalama": round(sum(current_depths) / len(current_depths), 2) if current_depths else 0.0,
            "eksik_sondajlar": short,
            "gerilme_hesabi": stress,
        }
    fallback = sondaj_derinligi_hesapla(veri)
    fallback["hesap_tipi"] = "on_kontrol"
    fallback["gerilme_hesabi_hatalari"] = stress.get("errors", [])
    return fallback


def sondaj_derinligi_ozet_metni(veri):
    result = sondaj_derinligi_hesapla(veri)
    lines = [
        "YÖNETMELİK ESASLI SONDAJ DERİNLİĞİ ÖN KONTROLÜ",
        "",
        f"Zemin etüt kategorisi: Kategori {result['kategori']}",
        f"Önerilen minimum sondaj derinliği: {result['onerilen_sondaj_derinligi']:.2f} m",
        "",
        "Blok hesapları:",
    ]
    for block in result["bloklar"]:
        lines.append(
            "- {blok}: kazı {kazı:.2f} m + temel altı {alt:.2f} m = {toplam:.2f} m "
            "({kriter}; B={b:.2f} m, kaynak: {bk})".format(
                blok=block["blok_adi"],
                kazı=block["kazı_derinliği"],
                alt=block["temel_alti_arastirma"],
                toplam=block["onerilen_sondaj_derinligi"],
                kriter=block["belirleyici_kriter"],
                b=block["temel_genisligi"],
                bk=block["temel_genisligi_kaynagi"],
            )
        )
    if result["eksik_sondajlar"]:
        lines.extend(["", "Önerinin altında kalan sondajlar:"])
        for item in result["eksik_sondajlar"]:
            lines.append(f"- {item['sondaj']}: {item['derinlik']:.2f} m, eksik yaklaşık {item['eksik']:.2f} m")
    else:
        lines.append("")
        lines.append("Mevcut sondajlar önerilen minimum derinliği sağlıyor veya sondaj verisi henüz girilmedi.")
    if result["uyarilar"]:
        lines.extend(["", "Hesap notları:"])
        lines.extend(f"- {item}" for item in result["uyarilar"])
    lines.extend([
        "",
        "Not: Bu sonuç otomatik ön kontroldür; saha jeolojisi, zayıf tabaka, sıvılaşma, kaya seviyesi, kazıklı temel ve idare talebi varsa mühendis kararıyla derinlik artırılmalıdır.",
    ])
    return "\n".join(lines)
