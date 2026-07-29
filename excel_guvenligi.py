"""Excel'e yazilan serbest metinleri formül enjeksiyonuna karsi korur."""

from __future__ import annotations

import math
import re


_SAYI_DESENI = re.compile(
    r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$"
)


def _sayisal_metin_mi(metin):
    aday = str(metin).strip()
    if not _SAYI_DESENI.fullmatch(aday):
        return False
    try:
        return math.isfinite(float(aday.replace(",", ".")))
    except (TypeError, ValueError):
        return False


def excel_hucre_degeri(deger):
    """Metni veri olarak saklar; gercek sayi/tarih nesnelerine dokunmaz.

    Excel, kullanici kaynakli ``=``, ``+``, ``-`` ve ``@`` ile baslayan
    metinleri formül olarak yorumlayabilir. Negatif/pozitif sayisal metinler
    muhendislik verisi oldugu icin oldugu gibi birakilir.
    """

    if not isinstance(deger, str) or not deger:
        return deger
    aday = deger.lstrip()
    if not aday:
        return deger
    tehlikeli = aday[0] in ("=", "+", "@", "\t", "\r", "\n")
    tehlikeli = tehlikeli or (
        aday.startswith("-") and aday != "-" and not _sayisal_metin_mi(aday)
    )
    if tehlikeli and not _sayisal_metin_mi(aday):
        return "'" + deger
    return deger


def excel_satiri_guvenli_yap(satir):
    return [excel_hucre_degeri(deger) for deger in satir]
