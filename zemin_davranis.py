"""Zemin davranışını N30 değerinden türeten UI bağımsız domain kuralları."""

from __future__ import annotations

import math


KIVAM_SIRASI = (
    "Çok yumuşak",
    "Yumuşak",
    "Orta katı",
    "Katı",
    "Çok katı",
    "Sert",
)

SIKILIK_SIRASI = (
    "Çok gevşek",
    "Gevşek",
    "Orta sıkı",
    "Sıkı",
    "Çok sıkı",
)

_KIVAM_ESIKLERI = (2, 4, 8, 15, 30)
_SIKILIK_ESIKLERI = (4, 10, 30, 50)
_GEÇERSİZ_N30_METİNLERİ = {"", "-", "—", "nan", "none", "null"}


def _n30_sayiya_cevir(value):
    """N30 girdisini sonlu bir sayıya çevirir; geçersiz girdilerde None döner."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, str):
        text = "".join(value.split()).replace(",", ".")
        if text.casefold() in _GEÇERSİZ_N30_METİNLERİ:
            return None
        value = text

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _gecerli_n30(value):
    number = _n30_sayiya_cevir(value)
    if number is None or number < 0:
        return None
    return number


def _n30_sinifi(number, esikler, sirasi):
    for threshold, label in zip(esikler, sirasi):
        if number <= threshold:
            return label
    return sirasi[-1]


def _n30_lejant_satirlari(esikler, sirasi):
    rows = [("N", "")]
    lower = 0
    for upper, label in zip(esikler, sirasi):
        rows.append((f"{lower:g}-{upper:g}", label))
        lower = upper + 1
    rows.append((f">{esikler[-1]:g}", sirasi[-1]))
    return tuple(rows)


KIVAM_N30_TABLOSU = _n30_lejant_satirlari(_KIVAM_ESIKLERI, KIVAM_SIRASI)
SIKILIK_N30_TABLOSU = _n30_lejant_satirlari(_SIKILIK_ESIKLERI, SIKILIK_SIRASI)


def n30_kivam_sinifi(n30=None, refused=False):
    """İnce daneli zemin için N30 kıvam sınıfını döndürür."""
    if refused:
        return "Sert"

    number = _gecerli_n30(n30)
    if number is None:
        return ""
    return _n30_sinifi(number, _KIVAM_ESIKLERI, KIVAM_SIRASI)


def n30_sikilik_sinifi(n30=None, refused=False):
    """İri daneli zemin için N30 sıkılık sınıfını döndürür."""
    if refused:
        return "Çok sıkı"

    number = _gecerli_n30(n30)
    if number is None:
        return ""
    return _n30_sinifi(number, _SIKILIK_ESIKLERI, SIKILIK_SIRASI)


__all__ = [
    "KIVAM_SIRASI",
    "KIVAM_N30_TABLOSU",
    "SIKILIK_SIRASI",
    "SIKILIK_N30_TABLOSU",
    "n30_kivam_sinifi",
    "n30_sikilik_sinifi",
]
