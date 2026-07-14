# Dosya: RaporPro/ui_icons.py
from __future__ import annotations

import unicodedata


TR_TRANSLATION = str.maketrans(
    {
        "\u0130": "I",
        "\u0131": "i",
        "\u015e": "S",
        "\u015f": "s",
        "\u011e": "G",
        "\u011f": "g",
        "\u00dc": "U",
        "\u00fc": "u",
        "\u00d6": "O",
        "\u00f6": "o",
        "\u00c7": "C",
        "\u00e7": "c",
    }
)


def normalized_text(value):
    text = str(value or "").translate(TR_TRANSLATION).lower()
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


class IconManager:
    """Small Tk PhotoImage icon factory with safe text-based lookup."""

    def __init__(self, master=None, default_size=16):
        self.master = master
        self.default_size = default_size
        self._cache = {}

    def guess_key(self, text):
        t = normalized_text(text)
        checks = [
            (("kurtar", "yenile", "guncelle"), "refresh"),
            (("yeni", "ekle", "+"), "plus"),
            (("sil", "temizle", "kaldir"), "trash"),
            (("kaydet",), "save"),
            (("ayar", "arac"), "settings"),
            (("ac", "klasor", "dosya sec"), "folder"),
            (("kilit",), "lock"),
            (("workbook", "excel", "tablo"), "table"),
            (("spt", "foto", "kamera", "kirp"), "camera"),
            (("sondaj",), "borehole"),
            (("karot", "tcr", "scr", "rqd", "kaya"), "core"),
            (("akilli", "tamamla", "ogret"), "spark"),
            (("litoloji", "jeoloji", "birim"), "layers"),
            (("pmt", "presiyometre"), "gauge"),
            (("numune", "ornek"), "sample"),
            (("log", "grafik"), "chart"),
            (("kesit",), "section"),
            (("rapor", "word"), "report"),
            (("pdf", "cikti", "disa", "aktar"), "export"),
            (("kontrol", "hazir", "onay"), "check"),
            (("onizleme", "gorunum"), "eye"),
            (("harita", "kml", "koordinat", "yer", "tkgm", "pga", "mjh"), "map"),
            (("etiket", "sablon"), "tag"),
            (("geri", "undo"), "undo"),
            (("ileri", "redo"), "redo"),
            (("baslat", "devam"), "play"),
            (("durdur", "vazgec", "kapat"), "close"),
            (("n30", "hesap"), "calculator"),
            (("gecmis", "son proje"), "history"),
            (("proje", "ozet"), "project"),
        ]
        for needles, key in checks:
            if any(needle in t for needle in needles):
                return key
        return None

    def get(self, key, color="#111111", size=None):
        if not key:
            return None
        size = int(size or self.default_size)
        cache_key = (key, color, size)
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            import tkinter as tk

            img = tk.PhotoImage(master=self.master, width=size, height=size)
            self._draw_icon(img, key, color, size)
            self._cache[cache_key] = img
            return img
        except Exception:
            return None

    def _pixel(self, img, x, y, color, size):
        if 0 <= x < size and 0 <= y < size:
            img.put(color, to=(x, y, x + 1, y + 1))

    def _rect(self, img, x1, y1, x2, y2, color, size):
        x1 = max(0, min(size, int(x1)))
        y1 = max(0, min(size, int(y1)))
        x2 = max(0, min(size, int(x2)))
        y2 = max(0, min(size, int(y2)))
        if x2 > x1 and y2 > y1:
            img.put(color, to=(x1, y1, x2, y2))

    def _line(self, img, x1, y1, x2, y2, color, size, width=1):
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        x, y = x1, y1
        while True:
            for ox in range(-(width // 2), width // 2 + 1):
                for oy in range(-(width // 2), width // 2 + 1):
                    self._pixel(img, x + ox, y + oy, color, size)
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def _outline_rect(self, img, x1, y1, x2, y2, color, size, width=1):
        self._line(img, x1, y1, x2, y1, color, size, width)
        self._line(img, x2, y1, x2, y2, color, size, width)
        self._line(img, x2, y2, x1, y2, color, size, width)
        self._line(img, x1, y2, x1, y1, color, size, width)

    def _circle(self, img, cx, cy, radius, color, size, width=1):
        r2 = radius * radius
        inner = max(0, radius - width)
        inner2 = inner * inner
        for y in range(int(cy - radius - 1), int(cy + radius + 2)):
            for x in range(int(cx - radius - 1), int(cx + radius + 2)):
                d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy)
                if inner2 <= d2 <= r2:
                    self._pixel(img, x, y, color, size)

    def _draw_icon(self, img, key, color, size):
        s = size
        if key == "plus":
            self._line(img, s // 2, 3, s // 2, s - 4, color, s, 2)
            self._line(img, 3, s // 2, s - 4, s // 2, color, s, 2)
        elif key == "trash":
            self._line(img, 4, 5, s - 5, 5, color, s, 1)
            self._line(img, 6, 3, s - 7, 3, color, s, 1)
            self._outline_rect(img, 5, 6, s - 6, s - 3, color, s, 1)
            self._line(img, 7, 8, 7, s - 5, color, s, 1)
            self._line(img, s - 8, 8, s - 8, s - 5, color, s, 1)
        elif key == "save":
            self._outline_rect(img, 3, 3, s - 4, s - 4, color, s, 1)
            self._rect(img, 5, 4, s - 7, 7, color, s)
            self._outline_rect(img, 6, s - 8, s - 7, s - 4, color, s, 1)
        elif key == "folder":
            self._line(img, 2, 6, 6, 6, color, s, 1)
            self._line(img, 6, 5, 9, 5, color, s, 1)
            self._outline_rect(img, 2, 7, s - 3, s - 4, color, s, 1)
        elif key == "refresh":
            self._circle(img, s / 2, s / 2, s / 2 - 4, color, s, 1)
            self._line(img, s - 5, 4, s - 2, 4, color, s, 1)
            self._line(img, s - 5, 4, s - 5, 7, color, s, 1)
        elif key == "lock":
            self._outline_rect(img, 4, 8, s - 5, s - 3, color, s, 1)
            self._line(img, 6, 8, 6, 6, color, s, 1)
            self._line(img, 6, 6, s - 7, 6, color, s, 1)
            self._line(img, s - 7, 6, s - 7, 8, color, s, 1)
        elif key == "table":
            self._outline_rect(img, 2, 3, s - 3, s - 3, color, s, 1)
            self._line(img, 2, 7, s - 3, 7, color, s, 1)
            self._line(img, 2, 11, s - 3, 11, color, s, 1)
            self._line(img, 7, 3, 7, s - 3, color, s, 1)
            self._line(img, 11, 3, 11, s - 3, color, s, 1)
        elif key == "camera":
            self._outline_rect(img, 3, 6, s - 4, s - 4, color, s, 1)
            self._line(img, 6, 5, 9, 5, color, s, 1)
            self._circle(img, s / 2, 10, 3, color, s, 1)
        elif key == "borehole":
            self._circle(img, s / 2, 5, 3, color, s, 1)
            self._line(img, s / 2, 8, s / 2, s - 3, color, s, 2)
        elif key == "core":
            self._outline_rect(img, 3, 5, s - 4, 8, color, s, 1)
            self._outline_rect(img, 3, 10, s - 4, 13, color, s, 1)
            self._line(img, 6, 5, 9, 8, color, s, 1)
            self._line(img, 6, 10, 9, 13, color, s, 1)
        elif key == "spark":
            self._line(img, 8, 2, 8, 14, color, s, 1)
            self._line(img, 2, 8, 14, 8, color, s, 1)
            self._line(img, 4, 4, 12, 12, color, s, 1)
            self._line(img, 12, 4, 4, 12, color, s, 1)
        elif key == "layers":
            self._line(img, 8, 2, 14, 6, color, s, 1)
            self._line(img, 14, 6, 8, 10, color, s, 1)
            self._line(img, 8, 10, 2, 6, color, s, 1)
            self._line(img, 2, 6, 8, 2, color, s, 1)
            self._line(img, 3, 10, 8, 13, color, s, 1)
            self._line(img, 8, 13, 13, 10, color, s, 1)
        elif key == "gauge":
            self._circle(img, s / 2, 10, 5, color, s, 1)
            self._line(img, s / 2, 10, 12, 6, color, s, 1)
        elif key == "sample":
            self._outline_rect(img, 5, 3, s - 6, s - 3, color, s, 1)
            self._line(img, 5, 6, s - 6, 6, color, s, 1)
            self._line(img, 7, 9, s - 8, 9, color, s, 1)
        elif key == "chart":
            self._line(img, 3, s - 3, s - 3, s - 3, color, s, 1)
            self._line(img, 3, s - 3, 3, 3, color, s, 1)
            self._rect(img, 5, 9, 7, s - 4, color, s)
            self._rect(img, 9, 6, 11, s - 4, color, s)
            self._rect(img, 13, 4, 15, s - 4, color, s)
        elif key == "section":
            self._line(img, 2, 12, 6, 8, color, s, 1)
            self._line(img, 6, 8, 10, 10, color, s, 1)
            self._line(img, 10, 10, 14, 5, color, s, 1)
            self._line(img, 4, 4, 4, 13, color, s, 1)
            self._line(img, 12, 3, 12, 13, color, s, 1)
        elif key == "report":
            self._outline_rect(img, 4, 2, s - 5, s - 3, color, s, 1)
            self._line(img, 6, 6, s - 7, 6, color, s, 1)
            self._line(img, 6, 9, s - 7, 9, color, s, 1)
            self._line(img, 6, 12, s - 8, 12, color, s, 1)
        elif key == "export":
            self._outline_rect(img, 3, 5, s - 4, s - 3, color, s, 1)
            self._line(img, s // 2, 2, s // 2, 10, color, s, 1)
            self._line(img, s // 2, 2, s - 5, 6, color, s, 1)
            self._line(img, s // 2, 2, 5, 6, color, s, 1)
        elif key == "check":
            self._line(img, 3, 9, 7, 13, color, s, 2)
            self._line(img, 7, 13, 14, 4, color, s, 2)
        elif key == "eye":
            self._line(img, 2, 8, 6, 5, color, s, 1)
            self._line(img, 6, 5, 10, 5, color, s, 1)
            self._line(img, 10, 5, 14, 8, color, s, 1)
            self._line(img, 14, 8, 10, 11, color, s, 1)
            self._line(img, 10, 11, 6, 11, color, s, 1)
            self._line(img, 6, 11, 2, 8, color, s, 1)
            self._circle(img, 8, 8, 2, color, s, 1)
        elif key == "map":
            self._outline_rect(img, 3, 4, s - 4, s - 4, color, s, 1)
            self._line(img, 7, 4, 7, s - 4, color, s, 1)
            self._line(img, 11, 4, 11, s - 4, color, s, 1)
            self._circle(img, 8, 7, 2, color, s, 1)
        elif key == "settings":
            self._circle(img, s / 2, s / 2, 5, color, s, 1)
            self._circle(img, s / 2, s / 2, 2, color, s, 1)
            self._line(img, 8, 2, 8, 5, color, s, 1)
            self._line(img, 8, 11, 8, 14, color, s, 1)
            self._line(img, 2, 8, 5, 8, color, s, 1)
            self._line(img, 11, 8, 14, 8, color, s, 1)
        elif key == "tag":
            self._line(img, 3, 4, 10, 4, color, s, 1)
            self._line(img, 10, 4, 14, 8, color, s, 1)
            self._line(img, 14, 8, 8, 14, color, s, 1)
            self._line(img, 8, 14, 3, 9, color, s, 1)
            self._line(img, 3, 9, 3, 4, color, s, 1)
            self._pixel(img, 6, 6, color, s)
        elif key == "undo":
            self._line(img, 5, 5, 2, 8, color, s, 1)
            self._line(img, 2, 8, 5, 11, color, s, 1)
            self._line(img, 3, 8, 12, 8, color, s, 1)
        elif key == "redo":
            self._line(img, 11, 5, 14, 8, color, s, 1)
            self._line(img, 14, 8, 11, 11, color, s, 1)
            self._line(img, 3, 8, 13, 8, color, s, 1)
        elif key == "play":
            self._line(img, 5, 3, 12, 8, color, s, 2)
            self._line(img, 12, 8, 5, 13, color, s, 2)
            self._line(img, 5, 13, 5, 3, color, s, 2)
        elif key == "close":
            self._line(img, 4, 4, 12, 12, color, s, 2)
            self._line(img, 12, 4, 4, 12, color, s, 2)
        elif key == "calculator":
            self._outline_rect(img, 4, 2, s - 5, s - 3, color, s, 1)
            self._rect(img, 6, 4, s - 7, 6, color, s)
            for x in (6, 9, 12):
                for y in (8, 11):
                    self._pixel(img, x, y, color, s)
        elif key == "history":
            self._circle(img, s / 2, s / 2, 5, color, s, 1)
            self._line(img, 8, 8, 8, 5, color, s, 1)
            self._line(img, 8, 8, 11, 9, color, s, 1)
            self._line(img, 4, 5, 2, 5, color, s, 1)
        elif key == "project":
            self._outline_rect(img, 3, 4, s - 4, s - 4, color, s, 1)
            self._line(img, 5, 7, s - 6, 7, color, s, 1)
            self._line(img, 5, 10, s - 7, 10, color, s, 1)
        else:
            self._circle(img, s / 2, s / 2, 4, color, s, 1)
