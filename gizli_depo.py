# Dosya: RaporPro/gizli_depo.py
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os


DPAPI_PREFIX = "dpapi:v1:"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _input_blob(data):
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _windows_only():
    if os.name != "nt":
        raise RuntimeError("Güvenli anahtar saklama yalnız Windows DPAPI ile destekleniyor.")


def gizli_deger_mi(value):
    return str(value or "").startswith(DPAPI_PREFIX)


def gizli_deger_sakla(value):
    """Metni mevcut Windows kullanıcısına bağlı DPAPI verisine dönüştür."""
    text = str(value or "")
    if not text or gizli_deger_mi(text):
        return text
    _windows_only()
    input_blob, input_buffer = _input_blob(text.encode("utf-8"))
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "RaporPro güvenli ayarı",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
    return DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")


def gizli_deger_coz(value):
    """DPAPI verisini çözer; eski düz metin değerleri geçiş için aynen döndürür."""
    text = str(value or "")
    if not gizli_deger_mi(text):
        return text
    _windows_only()
    encrypted = base64.b64decode(text[len(DPAPI_PREFIX):].encode("ascii"), validate=True)
    input_blob, input_buffer = _input_blob(encrypted)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        decrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
    return decrypted.decode("utf-8")
