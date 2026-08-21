# Dosya: RaporPro/motor_log_kaynak.py
"""
motor_log.py icindeki log cizim uyumlulugu icin kaynak motor.

Bu dosya, gecici pyc koprusunun yerine gecen okunabilir kaynak tabanli
sondaj logu motorunu icerir.
"""

from __future__ import annotations

import math
import re
import textwrap
from functools import lru_cache

import numpy as np
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
import matplotlib.patches as mpatches
from matplotlib.textpath import TextPath

from sabitler import LEJANTLAR
from yardimcilar import safe_float, litoloji_cozumle
from cizim import GeoEngineDraw
from zemin_davranis import KIVAM_N30_TABLOSU, SIKILIK_N30_TABLOSU


@lru_cache(maxsize=4096)
def _log_text_genisligi(text, font_size, font_weight):
    """Tekrarlanan log başlıklarının vektörel genişliğini önbellekten döndür."""
    font_prop = FontProperties(size=float(font_size), weight=str(font_weight))
    return TextPath((0, 0), str(text) or " ", prop=font_prop).get_extents().width


A4_PORTRAIT_SIZE = (8.27, 11.69)
LOG_FIGURE_DPI = 100
LOG_BODY_COLUMN_RATIOS = (4.79, 2.34, 4.79, 6.25, 5.73, 16.0, 8.85, 22.2, 6.67, 18.0, 4.38)
LOG_ZEMIN_PROFILI_START_RATIO = (
    sum(LOG_BODY_COLUMN_RATIOS[:8]) / sum(LOG_BODY_COLUMN_RATIOS)
)


def _log_personel_yazimi_duzelt(value):
    text = str(value or "").strip()
    key = text.casefold().translate(
        str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})
    )
    key = re.sub(r"\s+", " ", key)
    if key == "gokalp dogan":
        return "Gökalp DOĞAN"
    if key == "murat ercelik 3629":
        return "Murat ERÇELİK 3629"
    return text


def log_ornek_derinligi_formatla(value):
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\s*-\s*", text) if p.strip()]
    if not parts:
        return ""
    formatted = []
    for part in parts:
        try:
            formatted.append(f"{float(part):.1f}")
        except Exception:
            return ""
    return "-".join(formatted)


def derinlik_araligi_coz(value):
    text = str(value or "").strip().replace(",", ".")
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) >= 2:
        return safe_float(nums[0]), safe_float(nums[1])
    depth = safe_float(value)
    return depth, depth


def derinlik_baslangic(value):
    return derinlik_araligi_coz(value)[0]


def derinlik_orta(value):
    top, bot = derinlik_araligi_coz(value)
    if bot > top:
        return (top + bot) / 2.0
    return top


class GeoEngineLogMixin:
    @staticmethod
    def ciz_profesyonel_log(sondaj, proje_dict, log_callback=None):
        total_depth = safe_float(sondaj.get("der", 15))
        if total_depth <= 0:
            total_depth = 15.0

        PAGE_CAPACITY = 15.0
        num_pages = max(1, math.ceil(total_depth / PAGE_CAPACITY))
        figures = []

        def val(value, default=""):
            text = "" if value is None else str(value).strip()
            return text if text else default

        def fmt_depth(value, digits=2):
            try:
                return f"{safe_float(value):.{digits}f}"
            except Exception:
                return str(value)

        def spt_values(row):
            values = list(row) + ["", "", "", "", ""]
            return [values[i] for i in range(5)]

        spt_list = sorted(sondaj.get("spt", []) or [], key=lambda x: safe_float(x[0] if x else 0))
        pmt_list = sorted(sondaj.get("pmt", []) or [], key=lambda x: safe_float(x[0] if x else 0))
        rock_list = sorted(sondaj.get("kaya", []) or [], key=lambda x: derinlik_baslangic(x[0] if x else 0))
        lithology_list = sorted(sondaj.get("litoloji", []) or [], key=lambda x: safe_float(x[0] if x else 0))

        auto_samples = []
        test_labels = {}
        for idx, spt in enumerate(spt_list, start=1):
            row = spt_values(spt)
            depth = safe_float(row[0])
            if depth <= 0 and str(row[0]).strip() not in ("0", "0.0", "0.00"):
                continue
            auto_samples.append({
                "top": depth,
                "bot": depth + 0.45,
                "range": f"{depth:.2f}-{depth + 0.45:.2f}",
                "no": f"DS{idx}",
                "type": "",
            })
            test_labels[round(depth, 3)] = "SPT"

        for pmt in pmt_list:
            depth = safe_float(pmt[0] if pmt else 0)
            matched = False
            for existing_depth in list(test_labels.keys()):
                if abs(existing_depth - depth) < 0.1:
                    test_labels[existing_depth] = "SPT/P"
                    matched = True
                    break
            if not matched:
                test_labels[round(depth, 3)] = "P"

        manual_samples = []
        for sample in sondaj.get("numuneler", []) or []:
            try:
                raw_range = str(sample[0]).strip()
                sample_no = str(sample[1]).strip() if len(sample) > 1 else ""
                d_top, d_bot = derinlik_araligi_coz(raw_range)
                if abs(d_bot - d_top) < 1e-9:
                    d_top, d_bot = d_top - 0.225, d_top + 0.225
                display_range = log_ornek_derinligi_formatla(raw_range) or raw_range
                manual_samples.append({
                    "top": d_top,
                    "bot": d_bot,
                    "range": display_range,
                    "no": sample_no,
                    "type": "",
                })
            except Exception:
                pass

        manual_interval_keys = {
            (round(safe_float(item.get("top")), 2), round(safe_float(item.get("bot")), 2))
            for item in manual_samples
        }
        rock_samples = []
        for rock in rock_list:
            try:
                raw_range = str(rock[0]).strip() if rock else ""
                display_range = log_ornek_derinligi_formatla(raw_range)
                if not display_range:
                    continue
                d_top, d_bot = derinlik_araligi_coz(raw_range)
                key = (round(d_top, 2), round(d_bot, 2))
                if key in manual_interval_keys:
                    continue
                rock_samples.append({
                    "top": d_top,
                    "bot": d_bot,
                    "range": display_range,
                    "no": "",
                    "type": "",
                })
            except Exception:
                pass

        kunye = proje_dict.get("kunye", {}) if isinstance(proje_dict, dict) else {}
        ayarlar = proje_dict.get("ayarlar", {}) if isinstance(proje_dict, dict) else {}
        firma_adi = val(ayarlar.get("firma_adi"), "UB ZEMIN MUHENDISLIK")
        log_baslik = val(ayarlar.get("log_baslik"), "SONDAJ LOGU")
        sorumlu_unvan = val(ayarlar.get("sorumlu_muhendis_unvan"), "Sorumlu Jeoloji Muhendisi")
        sorumlu_muhendis = _log_personel_yazimi_duzelt(
            val(ayarlar.get("sorumlu_muhendis"), "Gökalp DOĞAN")
        )
        sondor_belge_baslik = val(ayarlar.get("sondor_belge_baslik"), "Sondor Belge No")
        sondor_belge = _log_personel_yazimi_duzelt(
            val(ayarlar.get("sondor_belge"), "Murat ERÇELİK 3629")
        )
        makine_metodu = val(ayarlar.get("makine_metodu"), "Rotary / Burgusuz")
        spt_sahmerdan = val(ayarlar.get("spt_sahmerdan"), "Otomatik")
        delgi_capi = val(ayarlar.get("delgi_capi"), "76 mm")

        for page_idx in range(num_pages):
            fig = Figure(figsize=A4_PORTRAIT_SIZE, dpi=LOG_FIGURE_DPI)
            ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis("off")

            page_x0, page_x1 = 0.035, 0.965
            page_w = page_x1 - page_x0
            header_top, row_h = 0.965, 0.0195
            col_header_top, body_top, body_bottom = 0.745, 0.675, 0.185
            footer_top, footer_bottom = 0.165, 0.035
            z_start = page_idx * PAGE_CAPACITY
            z_end = (page_idx + 1) * PAGE_CAPACITY

            def draw_cell(
                x,
                y,
                w,
                h,
                text="",
                fs=6.4,
                fw="normal",
                ha="center",
                va="center",
                rotation=0,
                lw=0.55,
                fc="white",
                ec="black",
                clip=True,
                linespacing=0.95,
                fit_text=False,
                min_fs=4.8,
            ):
                rect = mpatches.Rectangle(
                    (x, y),
                    w,
                    h,
                    facecolor=fc,
                    edgecolor=ec,
                    linewidth=lw,
                    zorder=2,
                )
                ax.add_patch(rect)
                if text not in (None, ""):
                    pad = min(0.006, max(w * 0.05, 0.002))
                    if fit_text and rotation == 0:
                        text_lines = str(text).splitlines() or [str(text)]
                        available_w = max(
                            1.0,
                            (w - 2 * pad) * A4_PORTRAIT_SIZE[0] * 0.96 * 72,
                        )
                        available_h = max(
                            1.0,
                            h * A4_PORTRAIT_SIZE[1] * 0.96 * 72 * 0.82,
                        )
                        text_width = max(
                            _log_text_genisligi(line or " ", fs, fw)
                            for line in text_lines
                        )
                        estimated_h = fs * max(1, len(text_lines)) * max(linespacing, 0.9)
                        scale = min(
                            1.0,
                            available_w / max(text_width * 1.04, 1.0),
                            available_h / max(estimated_h, 1.0),
                        )
                        fs = max(min_fs, fs * scale)
                    if ha == "left":
                        tx = x + pad
                    elif ha == "right":
                        tx = x + w - pad
                    else:
                        tx = x + w / 2
                    ty = y + h / 2
                    txt = ax.text(
                        tx,
                        ty,
                        str(text),
                        ha=ha,
                        va=va,
                        fontsize=fs,
                        fontweight=fw,
                        rotation=rotation,
                        zorder=5,
                        linespacing=linespacing,
                    )
                    if clip:
                        txt.set_clip_path(rect)
                    return rect, txt
                return rect, None

            header_label_bonus = 0.60
            header_value_bonus = 1.45

            def draw_label_value(x, y, label_w, value_w, label, value, fs=6.2):
                draw_cell(
                    x,
                    y,
                    label_w,
                    row_h,
                    label,
                    fs=fs + header_label_bonus,
                    fw="bold",
                    ha="left",
                    fc="#F4F4F4",
                    fit_text=True,
                )
                draw_cell(
                    x + label_w,
                    y,
                    value_w,
                    row_h,
                    value,
                    fs=fs + header_value_bonus,
                    ha="left",
                    fit_text=True,
                )

            def d2y(depth):
                return body_top - ((depth - z_start) / PAGE_CAPACITY) * (body_top - body_bottom)

            def clipped_text(x, y, w, h, text, fs=5.4, fw="normal", zorder=9):
                rect = mpatches.Rectangle((x, y), w, h, facecolor="none", edgecolor="none", linewidth=0, zorder=1)
                ax.add_patch(rect)
                txt = ax.text(
                    x + w / 2,
                    y + h / 2,
                    str(text),
                    ha="center",
                    va="center",
                    fontsize=fs,
                    fontweight=fw,
                    zorder=zorder,
                )
                txt.set_clip_path(rect)
                return txt

            def test_row_depth(depth):
                return safe_float(depth) + 0.225

            ax.add_patch(
                mpatches.Rectangle(
                    (page_x0, footer_bottom),
                    page_w,
                    header_top - footer_bottom,
                    facecolor="none",
                    edgecolor="black",
                    linewidth=1.05,
                    zorder=30,
                )
            )

            header_width_gain = (LOG_ZEMIN_PROFILI_START_RATIO - 0.675) / 2
            c1 = 0.12 * page_w
            c2 = (0.225 + header_width_gain) * page_w
            c3 = 0.145 * page_w
            c4 = (0.185 + header_width_gain) * page_w
            c5 = 0.095 * page_w
            c6 = page_w - (c1 + c2 + c3 + c4 + c5)
            hx = [
                page_x0,
                page_x0 + c1,
                page_x0 + c1 + c2,
                page_x0 + c1 + c2 + c3,
                page_x0 + c1 + c2 + c3 + c4,
                page_x0 + c1 + c2 + c3 + c4 + c5,
                page_x1,
            ]

            y = header_top - row_h
            draw_cell(hx[0], y, c1, row_h, "Yüklenici Firma", fs=7.6, fw="bold", ha="left", fc="#F4F4F4", fit_text=True)
            draw_cell(hx[1], y, page_w - c1, row_h, firma_adi, fs=8.8, fw="bold", ha="left", fit_text=True)
            ax.text(
                hx[1] + (page_x1 - hx[1]) / 2,
                y + row_h / 2,
                log_baslik,
                ha="center",
                va="center",
                fontsize=13.0,
                fontweight="bold",
                zorder=8,
            )

            y -= row_h
            draw_cell(hx[0], y, c1, row_h, "Proje Adı", fs=7.6, fw="bold", ha="left", fc="#F4F4F4", fit_text=True)
            draw_cell(hx[1], y, c2 + c3 + c4, row_h, val(kunye.get("sahibi")), fs=8.5, ha="left", fit_text=True)
            draw_cell(hx[4], y, c5, row_h, "Sondaj No", fs=7.6, fw="bold", ha="left", fc="#F4F4F4", fit_text=True)
            draw_cell(hx[5], y, c6, row_h, val(sondaj.get("no"), "SK-1"), fs=8.8, fw="bold", fit_text=True)

            header_rows = [
                ("İl", kunye.get("il", ""), "Sondaj Derinliği (m)", sondaj.get("der", ""), "Sayfa No", f"{page_idx + 1} / {num_pages}"),
                ("İlçe", kunye.get("ilce", ""), "Başlama Tarihi", sondaj.get("bas_tar", ""), "İşveren", ""),
                ("Mahalle/Köy", kunye.get("mah", ""), "Bitiş Tarihi", sondaj.get("bit_tar", ""), sorumlu_unvan, ""),
                ("Pafta", kunye.get("paf", ""), "Makine Tipi/Metodu", makine_metodu, sorumlu_muhendis, ""),
                ("Ada", kunye.get("ada", ""), "SPT Şahmerdan Tipi", spt_sahmerdan, sondor_belge_baslik, ""),
                ("Parsel", kunye.get("par", ""), "Delgi Çapı", delgi_capi, sondor_belge, ""),
                ("Sondaj Kotu", sondaj.get("k", ""), "Yeraltı Suyu (m)", "", "", ""),
            ]
            for idx, row in enumerate(header_rows):
                y -= row_h
                l1, v1, l2, v2, l3, v3 = row
                draw_label_value(hx[0], y, c1, c2, l1, val(v1), fs=6.1)
                if idx < 6:
                    draw_label_value(hx[2], y, c3, c4, l2, val(v2), fs=6.0)
                else:
                    draw_cell(hx[2], y - row_h * 2, c3, row_h * 3, l2, fs=7.2, fw="bold", fc="#F4F4F4")
                    water_w = c4 / 3
                    draw_cell(hx[3], y, water_w, row_h, "Derinlik", fs=6.0, fw="bold", fc="#F4F4F4")
                    draw_cell(hx[3] + water_w, y, water_w, row_h, "Tarih", fs=6.0, fw="bold", fc="#F4F4F4")
                    draw_cell(hx[3] + water_w * 2, y, water_w, row_h, "Açıklama", fs=6.0, fw="bold", fc="#F4F4F4")

                if idx in (2, 3, 4, 5):
                    text = l3 if idx in (2, 4) else (v3 or l3)
                    is_title = idx in (2, 4)
                    fs = 7.8 if is_title else 6.1 + header_value_bonus
                    draw_cell(
                        hx[4],
                        y,
                        c5 + c6,
                        row_h,
                        text,
                        fs=fs,
                        fw="bold" if is_title else "normal",
                        ha="center",
                        fit_text=True,
                    )
                elif idx < 2:
                    draw_label_value(hx[4], y, c5, c6, l3, val(v3), fs=5.9)
                else:
                    draw_cell(hx[4], y, c5 + c6, row_h, "", fs=5.8)

            y -= row_h
            draw_cell(hx[0], y - row_h, c1, row_h * 2, "Koordinatlar", fs=7.4, fw="bold", fc="#F4F4F4")
            coord_label_w = c2 * 0.22
            draw_cell(hx[1], y, coord_label_w, row_h, "X", fs=7.3, fw="bold", fc="#F4F4F4")
            draw_cell(hx[1] + coord_label_w, y, c2 - coord_label_w, row_h, val(sondaj.get("x"), "-"), fs=8.0, ha="left", fit_text=True)
            draw_cell(hx[1], y - row_h, coord_label_w, row_h, "Y", fs=7.3, fw="bold", fc="#F4F4F4")
            draw_cell(hx[1] + coord_label_w, y - row_h, c2 - coord_label_w, row_h, val(sondaj.get("y"), "-"), fs=8.0, ha="left", fit_text=True)
            water_w = c4 / 3
            draw_cell(hx[3], y, water_w, row_h, val(sondaj.get("yass_d1"), "-"), fs=7.2, fit_text=True)
            draw_cell(hx[3] + water_w, y, water_w, row_h, val(sondaj.get("yass_t1"), "-"), fs=6.6, fit_text=True)
            draw_cell(hx[3] + water_w * 2, y, water_w, row_h, "", fs=6.0)
            draw_cell(hx[3], y - row_h, water_w, row_h, val(sondaj.get("yass_d2"), "-"), fs=7.2, fit_text=True)
            draw_cell(hx[3] + water_w, y - row_h, water_w, row_h, val(sondaj.get("yass_t2"), "-"), fs=6.6, fit_text=True)
            draw_cell(hx[3] + water_w * 2, y - row_h, water_w, row_h, "", fs=6.0)
            draw_cell(hx[4], y, c5 + c6, row_h * 2, "", fs=5.8)

            ratios = LOG_BODY_COLUMN_RATIOS
            ratio_sum = sum(ratios)
            widths = [page_w * r / ratio_sum for r in ratios]
            cols = [page_x0]
            for width in widths:
                cols.append(cols[-1] + width)

            draw_cell(page_x0, body_bottom, page_w, col_header_top - body_bottom, "", lw=0.9, fc="none")
            for x in cols[1:-1]:
                ax.plot([x, x], [body_bottom, col_header_top], color="black", linewidth=0.55, zorder=20)
            ax.plot([page_x0, page_x1], [body_top, body_top], color="black", linewidth=0.75, zorder=22)

            header_defs = [
                (0, 1, "Sondaj\nderinliği\n(m)", 90, 5.0),
                (1, 2, "Muhafaza\nborusu", 90, 4.8),
                (2, 3, "Kuyu içi\ndeneyler", 90, 5.0),
                (3, 4, "Örnek\nderinliği\n(m)", 90, 5.0),
                (4, 5, "Örnek türü\nve no", 90, 5.0),
                (8, 9, "Zemin\nprofili", 90, 5.6),
                (9, 10, "Zemin tanımlaması", 0, 7.2),
                (10, 11, "Sondaj\nderinliği\n(m)", 90, 5.0),
            ]
            for c0, c1_idx, title, rot, fs in header_defs:
                draw_cell(cols[c0], body_top, cols[c1_idx] - cols[c0], col_header_top - body_top, title, fs=fs, fw="bold", rotation=rot, fc="#F4F4F4")

            spt_w = (cols[6] - cols[5]) / 4
            draw_cell(cols[5], body_top + (col_header_top - body_top) * 0.5, cols[6] - cols[5], (col_header_top - body_top) * 0.5, "Standart Penetrasyon\nTesti (SPT) / Darbe sayısı", fs=4.8, fw="bold", fc="#F4F4F4")
            for s_idx, title in enumerate(["0-15", "15-30", "30-45", "N"]):
                draw_cell(cols[5] + s_idx * spt_w, body_top, spt_w, (col_header_top - body_top) * 0.5, title, fs=5.5, fw="bold", fc="#F4F4F4")

            pmt_w = (cols[7] - cols[6]) / 2
            draw_cell(cols[6], body_top + (col_header_top - body_top) * 0.5, cols[7] - cols[6], (col_header_top - body_top) * 0.5, "Presiyometre\nDeneyi", fs=4.8, fw="bold", fc="#F4F4F4")
            draw_cell(cols[6], body_top, pmt_w, (col_header_top - body_top) * 0.5, "Em\n(kg/cm2)", fs=4.6, fw="bold", fc="#F4F4F4")
            draw_cell(cols[6] + pmt_w, body_top, pmt_w, (col_header_top - body_top) * 0.5, "Pl\n(kg/cm2)", fs=4.6, fw="bold", fc="#F4F4F4")

            rock_w = (cols[8] - cols[7]) / 6
            draw_cell(cols[7], body_top + (col_header_top - body_top) * 0.5, cols[8] - cols[7], (col_header_top - body_top) * 0.5, "Kaya Özellikleri", fs=6.2, fw="bold", fc="#F4F4F4")
            for r_idx, title in enumerate(["TCR %", "SCR %", "RQD %", "Ayrışma\nDerecesi", "Çatlak\nSıklığı", "Dayanım"]):
                draw_cell(
                    cols[7] + r_idx * rock_w,
                    body_top,
                    rock_w,
                    (col_header_top - body_top) * 0.5,
                    title,
                    fs=4.5,
                    fw="bold",
                    rotation=90 if r_idx >= 3 else 0,
                    fc="#F4F4F4",
                )

            for i in range(1, 4):
                ax.plot([cols[5] + i * spt_w, cols[5] + i * spt_w], [body_bottom, body_top], color="black", linewidth=0.35, zorder=20)
            ax.plot([cols[6] + pmt_w, cols[6] + pmt_w], [body_bottom, body_top], color="black", linewidth=0.35, zorder=20)
            for i in range(1, 6):
                ax.plot([cols[7] + i * rock_w, cols[7] + i * rock_w], [body_bottom, body_top], color="black", linewidth=0.35, zorder=20)

            for depth in np.arange(z_start, z_end + 0.0001, 0.5):
                y_depth = d2y(depth)
                is_meter = abs(depth - round(depth)) < 0.0001
                if is_meter:
                    label = f"{int(round(depth))}"
                    bbox = dict(facecolor="white", edgecolor="none", pad=0.1)
                    ax.text((cols[0] + cols[1]) / 2, y_depth, label, ha="center", va="center", fontsize=6.4, zorder=8, bbox=bbox)
                    ax.text((cols[10] + cols[11]) / 2, y_depth, label, ha="center", va="center", fontsize=6.4, zorder=8, bbox=bbox)
                else:
                    tick = 0.006
                    ax.plot([cols[0], cols[0] + tick], [y_depth, y_depth], color="black", linewidth=0.35, zorder=8)
                    ax.plot([cols[1] - tick, cols[1]], [y_depth, y_depth], color="black", linewidth=0.35, zorder=8)
                    ax.plot([cols[10], cols[10] + tick], [y_depth, y_depth], color="black", linewidth=0.35, zorder=8)
                    ax.plot([cols[11] - tick, cols[11]], [y_depth, y_depth], color="black", linewidth=0.35, zorder=8)

            for layer in lithology_list:
                try:
                    l_top = safe_float(layer[0])
                    l_bot = safe_float(layer[1])
                    desc = str(layer[2]) if len(layer) > 2 else ""
                    draw_top, draw_bot = max(l_top, z_start), min(l_bot, z_end)
                    if draw_top >= draw_bot:
                        continue
                    y_top = d2y(draw_top)
                    y_bot = d2y(draw_bot)
                    code = litoloji_cozumle(desc)
                    style = next((item for item in LEJANTLAR if item.get("kod") == code), LEJANTLAR[-1] if LEJANTLAR else None)
                    profile_rect = mpatches.Rectangle((cols[8], y_bot), cols[9] - cols[8], y_top - y_bot, facecolor="white", edgecolor="black", linewidth=0.6, zorder=3)
                    ax.add_patch(profile_rect)
                    if style:
                        GeoEngineDraw.draw_pattern(
                            ax,
                            None,
                            style.get("desen"),
                            style.get("sembol", "#000000"),
                            bbox=(cols[8], cols[9], y_bot, y_top),
                            density_scale=0.36,
                        )
                    desc_rect = mpatches.Rectangle((cols[9], y_bot), cols[10] - cols[9], y_top - y_bot, facecolor="none", edgecolor="black", linewidth=0.6, zorder=3)
                    ax.add_patch(desc_rect)
                    layer_h = y_top - y_bot
                    if desc and layer_h > 0.01:
                        wrap_chars = 24 if layer_h > 0.035 else 18
                        fs = 7.3 if layer_h > 0.04 else max(5.8, 6.7 - (0.035 - layer_h) * 25)
                        text = "\n".join(textwrap.wrap(desc, wrap_chars)) or desc
                        txt = ax.text(
                            cols[9] + (cols[10] - cols[9]) / 2,
                            (y_top + y_bot) / 2,
                            text,
                            ha="center",
                            va="center",
                            fontsize=fs,
                            linespacing=0.9,
                            zorder=6,
                        )
                        txt.set_clip_path(desc_rect)
                except Exception:
                    pass

            sample_rows = list(auto_samples)
            sample_rows.extend(rock_samples)
            sample_rows.extend(manual_samples)
            for sample in sample_rows:
                d_top = safe_float(sample.get("top"))
                d_bot = safe_float(sample.get("bot"))
                d_mid = (d_top + d_bot) / 2
                if not (z_start <= d_mid < z_end):
                    continue
                y_top = min(body_top, d2y(max(d_top, z_start)))
                y_bot = max(body_bottom, d2y(min(d_bot, z_end)))
                ax.plot([cols[2], cols[6]], [y_top, y_top], color="#777777", linewidth=0.35, zorder=7)
                ax.plot([cols[2], cols[6]], [y_bot, y_bot], color="#777777", linewidth=0.35, zorder=7)
                if sample.get("type"):
                    clipped_text(cols[2], y_bot, cols[3] - cols[2], y_top - y_bot, sample.get("type"), fs=5.3, zorder=8)
                clipped_text(cols[3], y_bot, cols[4] - cols[3], y_top - y_bot, sample.get("range", ""), fs=5.45, zorder=8)
                clipped_text(cols[4], y_bot, cols[5] - cols[4], y_top - y_bot, sample.get("no", ""), fs=5.3, fw="bold", zorder=8)

            for raw_depth, label in test_labels.items():
                d_mid = test_row_depth(raw_depth)
                if not (z_start <= d_mid < z_end):
                    continue
                ax.text((cols[2] + cols[3]) / 2, d2y(d_mid), label, ha="center", va="center", fontsize=5.6, fontweight="bold", zorder=9)

            for spt in spt_list:
                row = spt_values(spt)
                d_start = safe_float(row[0])
                d_mid = d_start + 0.225
                if not (z_start <= d_mid < z_end):
                    continue
                y_mid = d2y(d_mid)
                for idx, value in enumerate(row[1:5]):
                    ax.text(
                        cols[5] + idx * spt_w + spt_w / 2,
                        y_mid,
                        value,
                        ha="center",
                        va="center",
                        fontsize=6.4,
                        fontweight="bold" if idx == 3 else "normal",
                        zorder=9,
                    )

            for pmt in pmt_list:
                try:
                    depth = safe_float(pmt[0])
                    d_mid = test_row_depth(depth)
                    if not (z_start <= d_mid < z_end):
                        continue
                    y_mid = d2y(d_mid)
                    ax.text(cols[6] + pmt_w / 2, y_mid, str(pmt[1] if len(pmt) > 1 else ""), ha="center", va="center", fontsize=6.1, zorder=9)
                    ax.text(cols[6] + pmt_w + pmt_w / 2, y_mid, str(pmt[2] if len(pmt) > 2 else ""), ha="center", va="center", fontsize=6.1, zorder=9)
                except Exception:
                    pass

            for rock in rock_list:
                try:
                    top_depth, bot_depth = derinlik_araligi_coz(rock[0])
                    depth = (top_depth + bot_depth) / 2 if bot_depth > top_depth else derinlik_orta(rock[0])
                    if not (z_start <= depth < z_end):
                        continue
                    y_mid = d2y(depth)
                    y_top = min(body_top, d2y(max(top_depth, z_start)))
                    y_bot = max(body_bottom, d2y(min(bot_depth if bot_depth > top_depth else top_depth + 0.45, z_end)))
                    if y_top <= y_bot:
                        y_top = min(body_top, y_mid + 0.012)
                        y_bot = max(body_bottom, y_mid - 0.012)
                    for idx, value in enumerate(list(rock[1:7])[:6]):
                        clipped_text(cols[7] + idx * rock_w, y_bot, rock_w, y_top - y_bot, value, fs=6.2 if idx < 3 else 5.7, zorder=9)
                except Exception:
                    pass

            footer_cols = 4
            footer_w = page_w / footer_cols

            def footer_cell(x, y0, w, h, text, fs=3.9, fw="normal", ha="center", fc="white"):
                draw_cell(x, y0, w, h, text, fs=fs, fw=fw, ha=ha, fc=fc, lw=0.45, clip=True)

            def draw_footer_table(col_idx, sections):
                x = page_x0 + col_idx * footer_w
                y0 = footer_top
                r_h = 0.0091
                for title, rows in sections:
                    y0 -= r_h
                    footer_cell(x, y0, footer_w, r_h, title, fs=4.1, fw="bold", fc="#F4F4F4")
                    for left, right in rows:
                        y0 -= r_h
                        footer_cell(x, y0, footer_w * 0.32, r_h, left, fs=3.8, fw="bold")
                        footer_cell(x + footer_w * 0.32, y0, footer_w * 0.68, r_h, right, fs=3.8, ha="left")
                if y0 > footer_bottom:
                    footer_cell(x, footer_bottom, footer_w, y0 - footer_bottom, "", fs=3.8)

            draw_footer_table(0, [
                ("Kıvam Durumu (ince daneli)", KIVAM_N30_TABLOSU),
                ("Dayanımlılık", [("I", "Çok zayıf"), ("II", "Zayıf"), ("III", "Orta"), ("IV", "Dayanıklı"), ("V", "Çok dayanıklı")]),
            ])
            draw_footer_table(1, [
                ("Sıkılık (iri daneli)", SIKILIK_N30_TABLOSU),
                ("Ayrışma Derecesi", [("I", "Taze"), ("II", "Az ayrışmış"), ("III", "Orta ayrışmış"), ("IV", "Çok ayrışmış"), ("V", "Tam ayrışmış"), ("VI", "Kalıntı")]),
            ])
            draw_footer_table(2, [
                ("Oranlar", [("0-10 %", "Pek az"), ("10-20 %", "Az"), ("20-35 %", "Çok"), ("35-50 %", "Ve")]),
                ("Kaya Kalitesi Tanımı (RQD)", [("0-25 %", "Çok kötü"), ("25-50 %", "Kötü"), ("50-75 %", "Orta"), ("75-90 %", "İyi"), ("90-100 %", "Çok iyi")]),
            ])
            draw_footer_table(3, [
                ("Kırıklar / 30 cm", [("<1", "Seyrek"), ("1-2", "Orta"), ("2-10", "Sık"), ("10-20", "Çok sık"), (">20", "Parçalı")]),
                ("Kısaltmalar", [("UD", "Örselenmemiş"), ("DS", "Örselenmiş"), ("SPT", "Standart Pen."), ("TCR", "Top. Karot %"), ("SCR", "Çap Koru. %"), ("RQD", "Kaya Kalite %")]),
            ])

            figures.append(fig)
        return figures

    @staticmethod
    def _ciz_strater_stil_log(sondaj, proje_dict, log_callback=None):
        return GeoEngineLogMixin.ciz_profesyonel_log(sondaj, proje_dict, log_callback)

    @staticmethod
    def _ciz_profesyonel_log_eski(sondaj, proje_dict, log_callback=None):
        return GeoEngineLogMixin.ciz_profesyonel_log(sondaj, proje_dict, log_callback)
