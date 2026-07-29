# Dosya: RaporPro/karot_aktarim_motoru.py

import copy
import math

from karot_motoru import derinlik_araligi_coz, derinlik_araligi_etiketi, derinlik_baslangic


class KarotAktarimHatasi(ValueError):
    """TCR sonuclari kaya tablosuna guvenle aktarilamadiginda kullanilir."""


def _aralik_anahtari(value):
    top, bot = derinlik_araligi_coz(value)
    return round(float(top), 4), round(float(bot), 4)


def _satiri_listeye_cevir(row):
    if isinstance(row, list):
        result = copy.deepcopy(row)
    elif isinstance(row, tuple):
        result = list(copy.deepcopy(row))
    else:
        result = [str(row if row is not None else "")]
    while len(result) < 4:
        result.append("")
    return result


def _sonuc_degerleri(result, index):
    if not isinstance(result, dict):
        raise KarotAktarimHatasi(f"{index + 1}. TCR sonucu okunamadi.")
    if result.get("gecerli") is False:
        details = result.get("hatalar") or []
        detail_text = "; ".join(str(item) for item in details[:3])
        raise KarotAktarimHatasi(
            f"{index + 1}. TCR sonucu kalite kontrolunden gecmedi"
            + (f": {detail_text}" if detail_text else ".")
        )
    try:
        top = float(result["top"])
        bot = float(result["bot"])
        tcr = float(result["tcr"])
    except (KeyError, TypeError, ValueError) as exc:
        raise KarotAktarimHatasi(f"{index + 1}. TCR sonucu eksik veya sayisal degil.") from exc
    if not all(math.isfinite(value) for value in (top, bot, tcr)):
        raise KarotAktarimHatasi(f"{index + 1}. TCR sonucu sonlu sayilardan olusmali.")
    if top < 0 or bot <= top:
        raise KarotAktarimHatasi(
            f"{derinlik_araligi_etiketi(top, bot)} derinlik araligi gecersiz."
        )
    if tcr < 0 or tcr > 100:
        raise KarotAktarimHatasi(
            f"{derinlik_araligi_etiketi(top, bot)} icin TCR 0-100 araliginda olmali."
        )

    scr_value = result.get("scr")
    rqd_value = result.get("rqd")
    if (scr_value is None) != (rqd_value is None):
        raise KarotAktarimHatasi(
            f"{derinlik_araligi_etiketi(top, bot)} icin SCR ve RQD birlikte verilmelidir."
        )
    if scr_value is None:
        return top, bot, tcr, None, None

    try:
        scr = float(scr_value)
        rqd = float(rqd_value)
    except (TypeError, ValueError) as exc:
        raise KarotAktarimHatasi(
            f"{derinlik_araligi_etiketi(top, bot)} icin SCR veya RQD sayisal degil."
        ) from exc
    if not all(math.isfinite(value) for value in (scr, rqd)):
        raise KarotAktarimHatasi(
            f"{derinlik_araligi_etiketi(top, bot)} icin SCR ve RQD sonlu olmali."
        )
    if not (0 <= rqd <= scr <= tcr <= 100):
        raise KarotAktarimHatasi(
            f"{derinlik_araligi_etiketi(top, bot)} icin RQD <= SCR <= TCR kosulu saglanmiyor."
        )
    return top, bot, tcr, scr, rqd


def karot_aktarim_plani_olustur(sondaj, results):
    """Kaya tablosunu degistirmeden once yeni satir listesini ve ozetini uretir."""
    if not isinstance(sondaj, dict):
        raise KarotAktarimHatasi("Hedef sondaj kaydi bulunamadi.")
    if not results:
        raise KarotAktarimHatasi("Aktarilacak TCR sonucu yok.")

    original_rows = copy.deepcopy(sondaj.get("kaya") or [])
    updated_rows = [_satiri_listeye_cevir(row) for row in original_rows]
    row_by_key = {}
    for row in updated_rows:
        if not row or not str(row[0]).strip():
            continue
        row_by_key.setdefault(_aralik_anahtari(row[0]), row)

    added = 0
    updated = 0
    quality_updated = 0
    seen = set()
    changes = []
    for index, result in enumerate(results):
        top, bot, tcr, scr, rqd = _sonuc_degerleri(result, index)
        key = round(top, 4), round(bot, 4)
        if key in seen:
            raise KarotAktarimHatasi(
                f"{derinlik_araligi_etiketi(top, bot)} sonucu birden fazla kez aktarilamaz."
            )
        seen.add(key)
        formatted_tcr = f"{tcr:.0f}"
        formatted_scr = f"{scr:.0f}" if scr is not None else None
        formatted_rqd = f"{rqd:.0f}" if rqd is not None else None
        row = row_by_key.get(key)
        if row is None:
            row = [
                derinlik_araligi_etiketi(top, bot),
                formatted_tcr,
                formatted_scr or "",
                formatted_rqd or "",
            ]
            updated_rows.append(row)
            row_by_key[key] = row
            added += 1
            old_value = ""
            old_scr = ""
            old_rqd = ""
            action = "eklendi"
        else:
            old_value = str(row[1] if len(row) > 1 else "")
            old_scr = str(row[2] if len(row) > 2 else "")
            old_rqd = str(row[3] if len(row) > 3 else "")
            row[1] = formatted_tcr
            updated += 1
            action = "guncellendi"
        if formatted_scr is not None:
            row[2] = formatted_scr
            row[3] = formatted_rqd
            quality_updated += 1
        changes.append(
            {
                "aralik": derinlik_araligi_etiketi(top, bot),
                "onceki_tcr": old_value,
                "yeni_tcr": formatted_tcr,
                "onceki_scr": old_scr,
                "yeni_scr": formatted_scr,
                "onceki_rqd": old_rqd,
                "yeni_rqd": formatted_rqd,
                "islem": action,
            }
        )

    updated_rows.sort(key=lambda row: derinlik_baslangic(row[0] if row else ""))
    return {
        "sondaj_no": str(sondaj.get("no") or ""),
        "onceki_kaya": original_rows,
        "yeni_kaya": updated_rows,
        "eklenen": added,
        "guncellenen": updated,
        "kalite_guncellenen": quality_updated,
        "toplam": len(changes),
        "degisiklikler": changes,
    }


def karot_aktarim_plani_uygula(sondaj, plan):
    """Onceden uretilen plani tek atamada hedef sondaja uygular."""
    if not isinstance(sondaj, dict) or not isinstance(plan, dict):
        raise KarotAktarimHatasi("Karot aktarim plani uygulanamadi.")
    sondaj["kaya"] = copy.deepcopy(plan.get("yeni_kaya") or [])
    return sondaj["kaya"]


def karot_aktarimini_geri_al(sondaj, plan):
    """Uygulanan planin kaya tablosu oncesi goruntusunu geri yukler."""
    if not isinstance(sondaj, dict) or not isinstance(plan, dict):
        raise KarotAktarimHatasi("Geri alinacak karot aktarimi bulunamadi.")
    sondaj["kaya"] = copy.deepcopy(plan.get("onceki_kaya") or [])
    return sondaj["kaya"]
