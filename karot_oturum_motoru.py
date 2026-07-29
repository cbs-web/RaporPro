# Dosya: RaporPro/karot_oturum_motoru.py

import copy
import datetime
import os


KAROT_OTURUM_ANAHTARI = "karot_tcr_oturumlari"
KAROT_OTURUM_SURUMU = 2
KAROT_OTURUM_DESTEKLENEN_SURUMLER = (1, 2)


class KarotOturumHatasi(ValueError):
    """Kayitli karot olcum oturumu okunamadiginda kullanilir."""


def _gorsel_boyutu(image_size):
    if not isinstance(image_size, (list, tuple)) or len(image_size) < 2:
        raise KarotOturumHatasi("Kaynak gorsel boyutu bilinmiyor.")
    try:
        width = float(image_size[0])
        height = float(image_size[1])
    except (TypeError, ValueError) as exc:
        raise KarotOturumHatasi("Kaynak gorsel boyutu sayisal degil.") from exc
    if width <= 1 or height <= 1:
        raise KarotOturumHatasi("Kaynak gorsel boyutu gecersiz.")
    return width, height


def _noktayi_oranla(point, image_size):
    width, height = _gorsel_boyutu(image_size)
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise KarotOturumHatasi("Oturumdaki isaret noktasi okunamadi.") from exc
    return [x / (width - 1.0), y / (height - 1.0)]


def _noktayi_buyut(point, image_size):
    width, height = _gorsel_boyutu(image_size)
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise KarotOturumHatasi("Oturumdaki oransal isaret noktasi okunamadi.") from exc
    return [x * (width - 1.0), y * (height - 1.0)]


def _cizgiyi_oranla(line, image_size):
    return [_noktayi_oranla(point, image_size) for point in (line or [])]


def _cizgiyi_buyut(line, image_size):
    return [_noktayi_buyut(point, image_size) for point in (line or [])]


def kaynak_imzasi(image_path):
    path = os.path.abspath(str(image_path or "")) if image_path else ""
    signature = {
        "yol": path,
        "ad": os.path.basename(path) if path else "",
        "boyut": None,
        "degisim_ns": None,
    }
    if path and os.path.isfile(path):
        stat = os.stat(path)
        signature["boyut"] = int(stat.st_size)
        signature["degisim_ns"] = int(
            getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        )
    return signature


def kaynak_anahtari(signature):
    signature = signature or {}
    path = os.path.normcase(os.path.abspath(str(signature.get("yol") or "")))
    return (
        path,
        signature.get("boyut"),
        signature.get("degisim_ns"),
    )


def karot_oturumu_olustur(
    image_path,
    image_size,
    top_line,
    bottom_line,
    intervals,
):
    """Ekrandaki piksel isaretlerini cozunurlukten bagimsiz proje verisine cevirir."""
    width, height = _gorsel_boyutu(image_size)
    serialized_intervals = []
    for interval in intervals or []:
        try:
            top = float(interval["top"])
            bot = float(interval["bot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KarotOturumHatasi("Oturumdaki derinlik araligi okunamadi.") from exc
        serialized_intervals.append(
            {
                "top": top,
                "bot": bot,
                "segments": [
                    _cizgiyi_oranla(segment, (width, height))
                    for segment in (interval.get("segments") or [])
                ],
                "solid_segments": [
                    _cizgiyi_oranla(segment, (width, height))
                    for segment in (interval.get("solid_segments") or [])
                ],
                "quality_assessed": bool(interval.get("quality_assessed", False)),
            }
        )

    signature = kaynak_imzasi(image_path)
    return {
        "surum": KAROT_OTURUM_SURUMU,
        "kaynak": signature,
        "kaydedilme_zamani": datetime.datetime.now().isoformat(timespec="seconds"),
        "gorsel_boyutu": [int(round(width)), int(round(height))],
        "ust_cizgi": _cizgiyi_oranla(top_line, (width, height)),
        "alt_cizgi": _cizgiyi_oranla(bottom_line, (width, height)),
        "araliklar": serialized_intervals,
    }


def karot_oturumunu_coz(session, image_size):
    """Kayitli oransal isaretleri acilan gorselin piksel koordinatlarina dondurur."""
    if not isinstance(session, dict):
        raise KarotOturumHatasi("Karot oturum kaydi okunamadi.")
    try:
        version = int(session.get("surum", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise KarotOturumHatasi("Karot oturum surumu okunamadi.") from exc
    if version not in KAROT_OTURUM_DESTEKLENEN_SURUMLER:
        raise KarotOturumHatasi("Karot oturum surumu desteklenmiyor.")

    intervals = []
    for interval in session.get("araliklar") or []:
        try:
            top = float(interval["top"])
            bot = float(interval["bot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KarotOturumHatasi("Kayitli derinlik araligi okunamadi.") from exc
        intervals.append(
            {
                "top": top,
                "bot": bot,
                "segments": [
                    _cizgiyi_buyut(segment, image_size)
                    for segment in (interval.get("segments") or [])
                ],
                "solid_segments": [
                    _cizgiyi_buyut(segment, image_size)
                    for segment in (interval.get("solid_segments") or [])
                ],
                "quality_assessed": bool(
                    interval.get("quality_assessed", False)
                ),
            }
        )

    return {
        "top_line": _cizgiyi_buyut(session.get("ust_cizgi") or [], image_size),
        "bottom_line": _cizgiyi_buyut(session.get("alt_cizgi") or [], image_size),
        "intervals": intervals,
    }


def karot_oturumunu_kaydet(sondaj, session, max_count=20):
    """Ayni kaynak oturumunu guncelleyerek ilgili sondajda sinirli gecmis tutar."""
    if not isinstance(sondaj, dict) or not isinstance(session, dict):
        raise KarotOturumHatasi("Karot oturumu hedef sondaja kaydedilemedi.")
    sessions = [
        copy.deepcopy(item)
        for item in (sondaj.get(KAROT_OTURUM_ANAHTARI) or [])
        if isinstance(item, dict)
    ]
    new_key = kaynak_anahtari(session.get("kaynak"))
    sessions = [
        item
        for item in sessions
        if kaynak_anahtari(item.get("kaynak")) != new_key
    ]
    sessions.append(copy.deepcopy(session))
    if max_count and len(sessions) > int(max_count):
        sessions = sessions[-int(max_count) :]
    sondaj[KAROT_OTURUM_ANAHTARI] = sessions
    return sessions


def son_karot_oturumu(sondaj):
    sessions = (sondaj or {}).get(KAROT_OTURUM_ANAHTARI) or []
    valid = [item for item in sessions if isinstance(item, dict)]
    return copy.deepcopy(valid[-1]) if valid else None


def kaynak_icin_karot_oturumu(sondaj, image_path):
    expected = kaynak_anahtari(kaynak_imzasi(image_path))
    sessions = (sondaj or {}).get(KAROT_OTURUM_ANAHTARI) or []
    for session in reversed(sessions):
        if isinstance(session, dict) and kaynak_anahtari(session.get("kaynak")) == expected:
            return copy.deepcopy(session)
    return None
