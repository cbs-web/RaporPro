# Dosya: RaporPro/raporlama.py
import os
import datetime
import re
import unicodedata
from tkinter import filedialog
import pandas as pd
import traceback
import numpy as np
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from yardimcilar import temizle_baslik, zemin_sinifi_cevir, safe_float
from motor import GeoEngine
from performans import log_exception

IRI_DANELILER = ['Killi Kum', 'Kum', 'Kumlu', 'Siltli Killi Çakıl', 'Siltli Kum', 'Çakıllı Killi Kum', 'Çakıllı Kum', 'Çakıllı Siltli Kum', 'Kumlu Siltli Killi Çakıl', 'Çakıl']
INCE_DANELILER = ['Kil', 'Kumlu Kil', 'Çakıllı Kil', 'Siltli Kil', 'Kumlu Silt', 'Silt']

TABLE_HEADER_FILL = "D9E2F3"
TABLE_LABEL_FILL = "F2F5F9"
TABLE_ALT_FILL = "FAFBFC"
TABLE_BORDER_COLOR = "B7C1CC"
TABLE_TEXT_COLOR = "1F2937"

LITOLOJI_DAGILIM_BIRIMLERI = [
    "Çakıl",
    "Siltli Çakıl",
    "Killi Çakıl",
    "Çakıllı Kum",
    "Çakıllı Killi Kum",
    "Çakıllı Siltli Kum",
    "Siltli Kum",
    "Kum",
    "Killi Kum",
    "Kil",
    "Kumlu Kil",
    "Çakıllı Kil",
    "Kumlu Silt",
    "Kumlu Siltli Killi Çakıl",
]


def _log_silent(name, exc):
    log_exception(f"raporlama.{name}", exc_value=exc)

def _normalize_litoloji_text(text):
    value = "" if text is None else str(text).strip()
    if not value:
        return ""
    lowered = value.casefold()
    if any(marker in lowered for marker in ("ã", "ä", "å")):
        try:
            fixed = lowered.encode("latin1").decode("utf-8").casefold()
            if fixed:
                lowered = fixed
        except Exception:
            pass
    replacements = {
        "ı": "i", "İ": "i", "ç": "c", "ğ": "g",
        "ö": "o", "ş": "s", "ü": "u",
    }
    for old, new in replacements.items():
        lowered = lowered.replace(old, new)
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()

def litoloji_dagilim_birimi(tanim):
    normalized = _normalize_litoloji_text(tanim)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        return None

    base_tokens = {"cakil", "kum", "kil", "silt"}
    last_base_idx = -1
    last_base = ""
    for idx, token in enumerate(tokens):
        if token in base_tokens:
            last_base_idx = idx
            last_base = token
    if last_base_idx < 0:
        return None

    modifiers = set(tokens[:last_base_idx])
    has_cakilli = "cakilli" in modifiers or "cakil" in modifiers
    has_kumlu = "kumlu" in modifiers or "kum" in modifiers
    has_killi = "killi" in modifiers or "kil" in modifiers
    has_siltli = "siltli" in modifiers or "silt" in modifiers

    if last_base == "cakil":
        if has_kumlu and has_siltli and has_killi:
            return "Kumlu Siltli Killi Çakıl"
        if has_killi:
            return "Killi Çakıl"
        if has_siltli:
            return "Siltli Çakıl"
        return "Çakıl"

    if last_base == "kum":
        if has_cakilli and has_killi:
            return "Çakıllı Killi Kum"
        if has_cakilli and has_siltli:
            return "Çakıllı Siltli Kum"
        if has_cakilli:
            return "Çakıllı Kum"
        if has_killi:
            return "Killi Kum"
        if has_siltli:
            return "Siltli Kum"
        return "Kum"

    if last_base == "kil":
        if has_cakilli:
            return "Çakıllı Kil"
        if has_kumlu:
            return "Kumlu Kil"
        return "Kil"

    if last_base == "silt" and has_kumlu:
        return "Kumlu Silt"

    return None

def _fmt_litoloji_derinlik(value):
    number = safe_float(value)
    if abs(number - round(number)) < 0.001:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")

def litoloji_dagilim_paragraflari(sondajlar):
    groups = {unit: {} for unit in LITOLOJI_DAGILIM_BIRIMLERI}
    for sondaj in sondajlar or []:
        kuyu_no = clean_val(sondaj.get("no", ""))
        merged_layers = []
        for lit in sondaj.get("litoloji", []) or []:
            if len(lit) < 3:
                continue
            unit_name = litoloji_dagilim_birimi(lit[2])
            if not unit_name:
                continue
            top_val = safe_float(lit[0])
            bot_val = safe_float(lit[1])
            if bot_val < top_val:
                top_val, bot_val = bot_val, top_val
            if merged_layers and merged_layers[-1]["name"] == unit_name and abs(merged_layers[-1]["bot"] - top_val) < 0.05:
                merged_layers[-1]["bot"] = bot_val
            else:
                merged_layers.append({"name": unit_name, "top": top_val, "bot": bot_val})
        for layer in merged_layers:
            groups[layer["name"]].setdefault(kuyu_no, []).append(
                f"{_fmt_litoloji_derinlik(layer['top'])}-{_fmt_litoloji_derinlik(layer['bot'])}"
            )

    paragraphs = []
    for unit_name in LITOLOJI_DAGILIM_BIRIMLERI:
        kuyu_dict = groups.get(unit_name, {})
        parts = []
        for kuyu_no, ranges in kuyu_dict.items():
            parts.append(f"{kuyu_no}'de {', '.join(ranges)}m")
        if parts:
            paragraphs.append(f"{unit_name} birimleri " + ", ".join(parts) + " derinlikleri arasında gözlenmiştir.")
    return paragraphs

def set_vertical_cell_alignment(cell, align="center"):
    try: tc = cell._tc; tcPr = tc.get_or_add_tcPr(); tcValign = OxmlElement('w:vAlign'); tcValign.set(qn('w:val'), align); tcPr.append(tcValign)
    except Exception as exc: _log_silent("set_vertical_cell_alignment", exc)

def _xml_child(parent, tag):
    child = parent.find(qn(tag))
    if child is None:
        child = OxmlElement(tag)
        parent.append(child)
    return child

def _rgb_from_hex(value):
    value = str(value or "").strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None

def set_cell_shading(cell, fill):
    try:
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = _xml_child(tc_pr, "w:shd")
        shd.set(qn("w:fill"), fill)
    except Exception as exc:
        _log_silent("set_cell_shading", exc)

def set_cell_margins(cell, top=70, left=80, bottom=70, right=80):
    try:
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_mar = _xml_child(tc_pr, "w:tcMar")
        for key, value in {"top": top, "left": left, "bottom": bottom, "right": right}.items():
            node = _xml_child(tc_mar, f"w:{key}")
            node.set(qn("w:w"), str(value))
            node.set(qn("w:type"), "dxa")
    except Exception as exc:
        _log_silent("set_cell_margins", exc)

def set_cell_border(cell, color=TABLE_BORDER_COLOR, size="6"):
    try:
        tc_pr = cell._tc.get_or_add_tcPr()
        borders = _xml_child(tc_pr, "w:tcBorders")
        for edge in ("top", "left", "bottom", "right"):
            node = _xml_child(borders, f"w:{edge}")
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), size)
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), color)
    except Exception as exc:
        _log_silent("set_cell_border", exc)

def set_cell_width(cell, width_cm):
    try:
        if not width_cm:
            return
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_w = _xml_child(tc_pr, "w:tcW")
        tc_w.set(qn("w:w"), str(int(float(width_cm) * 567)))
        tc_w.set(qn("w:type"), "dxa")
    except Exception as exc:
        _log_silent("set_cell_width", exc)

def repeat_table_header(row):
    try:
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:tblHeader")) is None:
            tr_pr.append(OxmlElement("w:tblHeader"))
    except Exception as exc:
        _log_silent("repeat_table_header", exc)

def set_table_fit_to_window(table):
    try:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
    except Exception as exc:
        _log_silent("set_table_fit_to_window.alignment", exc)
    try:
        table.autofit = True
    except Exception as exc:
        _log_silent("set_table_fit_to_window.autofit", exc)
    try:
        tbl = table._tbl
        tbl_pr = tbl.tblPr
        if tbl_pr is None:
            tbl_pr = OxmlElement("w:tblPr")
            tbl.insert(0, tbl_pr)
        tbl_w = _xml_child(tbl_pr, "w:tblW")
        tbl_w.set(qn("w:w"), "5000")
        tbl_w.set(qn("w:type"), "pct")
        layout = _xml_child(tbl_pr, "w:tblLayout")
        layout.set(qn("w:type"), "autofit")
    except Exception as exc:
        _log_silent("set_table_fit_to_window.tblpr", exc)

def style_cell_text(cell, bold=None, font_size=None, font_color=None, alignment=None):
    rgb = _rgb_from_hex(font_color)
    for paragraph in cell.paragraphs:
        if alignment is not None:
            paragraph.alignment = alignment
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1
        for run in paragraph.runs:
            run.font.name = "Times New Roman"
            if bold is not None:
                run.font.bold = bold
            if font_size is not None:
                run.font.size = Pt(font_size)
            if rgb is not None:
                run.font.color.rgb = rgb

def style_report_table_row(row, fill=TABLE_HEADER_FILL, bold=True, font_size=10):
    for cell in row.cells:
        set_cell_shading(cell, fill)
        set_vertical_cell_alignment(cell, "center")
        set_cell_margins(cell)
        set_cell_border(cell)
        style_cell_text(cell, bold=bold, font_size=font_size, font_color=TABLE_TEXT_COLOR, alignment=WD_ALIGN_PARAGRAPH.CENTER)

def apply_report_table_style(table, header_rows=1, label_cols=None, text_cols=None, widths_cm=None):
    label_cols = set(label_cols or [])
    text_cols = set(text_cols or [])
    set_table_fit_to_window(table)
    for row_idx, row in enumerate(table.rows):
        is_header = row_idx < header_rows
        if is_header:
            repeat_table_header(row)
        for col_idx, cell in enumerate(row.cells):
            set_cell_margins(cell)
            set_cell_border(cell)
            set_vertical_cell_alignment(cell, "center")
            if widths_cm and col_idx < len(widths_cm):
                set_cell_width(cell, widths_cm[col_idx])
            alignment = WD_ALIGN_PARAGRAPH.LEFT if (not is_header and col_idx in text_cols) else WD_ALIGN_PARAGRAPH.CENTER
            style_cell_text(cell, bold=None, font_size=10, font_color=TABLE_TEXT_COLOR, alignment=alignment)
            if is_header:
                set_cell_shading(cell, TABLE_HEADER_FILL)
                style_cell_text(cell, bold=True, font_size=10, font_color=TABLE_TEXT_COLOR, alignment=WD_ALIGN_PARAGRAPH.CENTER)
            elif col_idx in label_cols:
                set_cell_shading(cell, TABLE_LABEL_FILL)
                style_cell_text(cell, bold=True, font_size=10, font_color=TABLE_TEXT_COLOR, alignment=alignment)
            elif row_idx % 2 == 0:
                set_cell_shading(cell, TABLE_ALT_FILL)

def clean_val(val):
    if val is None: return "-"
    s = str(val).strip().replace('\n', '').replace('\r', '').replace('\x0b', '').replace('\v', '')
    return s if s else "-"

def fmt_jeo(val):
    if val is None or val == "-" or str(val).strip() == "" or pd.isna(val): return "-"
    try:
        f = float(str(val).replace(",", "."))
        if f == int(f): return str(int(f)) 
        return "{:.2f}".format(f).replace(".", ",") 
    except Exception as exc:
        _log_silent("fmt_jeo", exc)
        return str(val).replace(".", ",")

def jeofizik_vp_layers_sadelestir(layers):
    sade_layers = []
    onceki_vp = None
    for layer in layers or []:
        vp_key = fmt_jeo(layer.get("vp", "-"))
        if vp_key != "-" and vp_key == onceki_vp:
            continue
        sade_layers.append(layer)
        onceki_vp = vp_key if vp_key != "-" else None
    return sade_layers

def read_table_file(path, header=None):
    if str(path).lower().endswith(".csv"):
        return pd.read_csv(path, header=header)
    return pd.read_excel(path, header=header)

def set_cell_text_clean(cell, text, font_name="Times New Roman", font_size=10, bold=False, italic=False, alignment=WD_ALIGN_PARAGRAPH.CENTER):
    if len(cell.paragraphs) > 1:
        for i in range(len(cell.paragraphs) - 1, 0, -1): p_element = cell.paragraphs[i]._element; p_element.getparent().remove(p_element)
    p = cell.paragraphs[0]; p.clear(); p.alignment = alignment
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1
    set_cell_margins(cell); set_cell_border(cell)
    run = p.add_run(clean_val(text)); run.font.name = font_name; run.font.size = Pt(font_size); run.font.bold = bold; run.font.italic = italic
    rgb = _rgb_from_hex(TABLE_TEXT_COLOR)
    if rgb is not None:
        run.font.color.rgb = rgb
    return run

def clean_word_tags(doc):
    for p in iter_all_paragraphs(doc):
        if "AUTO" in p.text:
            if "AUTO :" in p.text: 
                for run in p.runs:
                    if "AUTO :" in run.text:
                        run.text = run.text.replace("AUTO :", "AUTO:")

def iter_all_paragraphs(doc):
    for p in doc.paragraphs: yield p
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs: yield p
    for section in doc.sections:
        for hf in [section.header, section.first_page_header, section.even_page_header, section.footer, section.first_page_footer, section.even_page_footer]:
            if hf:
                for p in hf.paragraphs: yield p
                for table in hf.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            for p in cell.paragraphs: yield p

def create_word_table(doc, headers, data, text_cols=None, widths_cm=None):
    table = doc.add_table(rows=1, cols=len(headers)); table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers): set_cell_text_clean(hdr_cells[i], h, font_size=11, bold=True); set_vertical_cell_alignment(hdr_cells[i], "center")
    for row_data in data:
        row_cells = table.add_row().cells
        for i, val in enumerate(row_data): set_cell_text_clean(row_cells[i], val, font_size=10, bold=False); set_vertical_cell_alignment(row_cells[i], "center")
    apply_report_table_style(table, header_rows=1, text_cols=text_cols, widths_cm=widths_cm)
    return table

BINA_FIELDS_MAP = [
    ("Bina Kullanım Amacı", "kul"),
    ("Bina Kullanım Sınıfı", "sinif"),
    ("Bina Önem Katsayısı", "onem"),
    ("Yapı Malzemesi", "malz"),
    ("Bodrum Kat Adedi", "bod"),
    ("Toplam Kat Adedi", "kat"),
    ("Plan Boyutları", "plan"),
    ("Yapı Yüksekliği (Hn)", "yukseklik"),
    ("Bina Yükseklik Sınıfı", "yukseklik_sinif"),
    ("Temel Alanı", "temel_alan"),
    ("Toplam İnşaat Alanı", "ins"),
    ("Olası Kazı Derinliği", "der"),
    ("Temel Tipi", "tem"),
    ("Yerel Zemin Sınıfı", "ysinif"),
]

def bina_bloklari_rapor(bina):
    if not isinstance(bina, dict) or not bina.get("coklu_blok"):
        return []
    bloklar = []
    for idx, blok in enumerate(bina.get("bloklar", []) or []):
        if not isinstance(blok, dict):
            continue
        row = {key: clean_val(value) for key, value in blok.items()}
        if not any(value != "-" for key, value in row.items() if key != "blok_adi"):
            continue
        if row.get("blok_adi", "-") == "-":
            row["blok_adi"] = f"Blok {idx + 1}"
        bloklar.append(row)
    return bloklar

def bina_bilgileri_tablolari_olustur(doc, bina):
    bloklar = bina_bloklari_rapor(bina)
    if bloklar:
        summary_headers = ["Blok", "Kullanım", "Sınıf", "Malzeme", "Bodrum", "Kat", "Hn", "Temel Alanı", "Temel Tipi", "Kazı Der."]
        summary_rows = [
            [
                blok.get("blok_adi", "-"),
                blok.get("kul", "-"),
                blok.get("sinif", "-"),
                blok.get("malz", "-"),
                blok.get("bod", "-"),
                blok.get("kat", "-"),
                blok.get("yukseklik", "-"),
                blok.get("temel_alan", "-"),
                blok.get("tem", "-"),
                blok.get("der", "-"),
            ]
            for blok in bloklar
        ]
        load_headers = ["Blok", "GQE Min", "GQE Maks", "GQE Ort", "1.4G+1.6Q Min", "1.4G+1.6Q Maks", "1.4G+1.6Q Ort"]
        load_rows = [
            [
                blok.get("blok_adi", "-"),
                blok.get("gqe_min", "-"),
                blok.get("gqe_max", "-"),
                blok.get("gqe_ort", "-"),
                blok.get("comb_min", "-"),
                blok.get("comb_max", "-"),
                blok.get("comb_ort", "-"),
            ]
            for blok in bloklar
        ]
        return [create_word_table(doc, summary_headers, summary_rows), create_word_table(doc, load_headers, load_rows)]

    table = doc.add_table(rows=0, cols=4)
    table.style = 'Table Grid'
    for label, key in BINA_FIELDS_MAP:
        row = table.add_row()
        set_cell_text_clean(row.cells[0], label, bold=True)
        row.cells[1].merge(row.cells[3])
        set_cell_text_clean(row.cells[1], clean_val(bina.get(key, "")), bold=False)
        set_vertical_cell_alignment(row.cells[1], "center")
    header_row = table.add_row()
    headers = ["Binadan Temel Zeminine Aktarılan En Yükler (t/m2)", "Min", "Maks", "Ort."]
    for i, h in enumerate(headers):
        set_cell_text_clean(header_row.cells[i], h, bold=True)
        set_vertical_cell_alignment(header_row.cells[i], "center")
    row_gqe = table.add_row()
    set_cell_text_clean(row_gqe.cells[0], "(G+Q+E)", bold=True)
    set_cell_text_clean(row_gqe.cells[1], clean_val(bina.get("gqe_min", "")))
    set_cell_text_clean(row_gqe.cells[2], clean_val(bina.get("gqe_max", "")))
    set_cell_text_clean(row_gqe.cells[3], clean_val(bina.get("gqe_ort", "")))
    row_comb = table.add_row()
    set_cell_text_clean(row_comb.cells[0], "1.4G+1.6Q", bold=True)
    set_cell_text_clean(row_comb.cells[1], clean_val(bina.get("comb_min", "")))
    set_cell_text_clean(row_comb.cells[2], clean_val(bina.get("comb_max", "")))
    set_cell_text_clean(row_comb.cells[3], clean_val(bina.get("comb_ort", "")))
    for r in [row_gqe, row_comb]:
        for i in range(1, 4):
            set_vertical_cell_alignment(r.cells[i], "center")
    apply_report_table_style(table, header_rows=0, label_cols={0}, widths_cm=[5.2, 2.4, 2.4, 2.4])
    style_report_table_row(header_row)
    return [table]

def replace_text(doc, tag, value):
    val_str = str(value)
    for p in iter_all_paragraphs(doc):
        if tag in p.text:
            replaced = False
            for run in p.runs:
                if tag in run.text:
                    run.text = run.text.replace(tag, val_str)
                    replaced = True
            if not replaced:
                full_text = "".join(r.text for r in p.runs)
                if tag in full_text and p.runs:
                    p.runs[0].text = full_text.replace(tag, val_str)
                    for r in p.runs[1:]:
                        r.text = ""

def islem_tablo_yerlestir(doc, tag, headers, data_list):
    for p in iter_all_paragraphs(doc):
        if tag in p.text: 
            p.text = p.text.replace(tag, "")
            if data_list:
                table = create_word_table(doc, headers, data_list)
                p._p.addnext(table._tbl)
            return

def doc_replace_text_everywhere(doc, old_text, new_text):
    replace_text(doc, old_text, new_text)

def replace_tag_with_paragraphs(doc, tag, text_list):
    for p in iter_all_paragraphs(doc):
        if tag in p.text:
            p.text = p.text.replace(tag, "")
            for text in reversed(text_list):
                if not text or not text.strip(): continue
                new_p = OxmlElement("w:p"); new_r = OxmlElement("w:r"); new_t = OxmlElement("w:t"); new_t.text = text; new_r.append(new_t); new_p.append(new_r); p._p.addnext(new_p)
            return

def doc_replace_img(doc, keyword, img_path):
    if not img_path or not os.path.exists(img_path): return
    for p in iter_all_paragraphs(doc):
        if keyword in p.text: 
            p.text = ""
            run = p.add_run()
            run.add_picture(img_path, width=Cm(16))

def first_existing_path(*paths):
    for path in paths:
        if path and os.path.exists(path):
            return path
    return None

def mjh_resim_yolu(app_instance):
    return first_existing_path(
        getattr(app_instance, 'img_mjh', None),
        getattr(app_instance, 'img_yer', None),
        getattr(app_instance, 'img_tkgm', None),
    )

def raporla(app_instance):
    if not app_instance.word_path: return False, "Lütfen önce bir Word şablonu seçin."
    app_instance.set_status("Rapor oluşturuluyor...", level="warning")
    app_instance.root.update()
    app_instance.veri_kaydet()
    
    try:
        doc = Document(app_instance.word_path)
        clean_word_tags(doc)
        kunye = app_instance.veri["kunye"]
        jeofizik = app_instance.veri["jeofizik"]
        arazi = app_instance.veri["arazi"]
        sondajlar = app_instance.veri["sondaj"]
        
        ss_list = jeofizik.get("ss_list", [])
        mt_list = jeofizik.get("mt_list", [])
        
        jeo_excel_path = getattr(app_instance, 'jeo_excel_path', None)
        param_ss_list = []
        
        if jeo_excel_path:
            try:
                df_jeo = read_table_file(jeo_excel_path, header=None)
                current_serim = None
                for idx, row in df_jeo.iterrows():
                    row_str = [str(x).strip() for x in row if pd.notna(x)]
                    if not row_str: continue
                    if "Sismik Ölçü ve Hesaplarının Sahibi" in str(row.iloc[0]):
                        s_name = "SS"
                        for cell in row_str:
                            if "Serim" in str(cell) or "SS" in str(cell): s_name = str(cell).strip(); break
                        current_serim = {"ad": s_name, "layers": []}
                        param_ss_list.append(current_serim)
                    elif current_serim is not None:
                        r0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                        if "VP =" in r0 or "Boyuna Dalga" in r0: current_serim["raw_vp"] = row.tolist()
                        elif "VS =" in r0 or "Enine Dalga" in r0: current_serim["raw_vs"] = row.tolist()
                        elif "Tabaka Kalınlığı" in r0: current_serim["raw_h"] = row.tolist()
                        elif "Tabaka Yoğunluğu" in r0: current_serim["raw_rho"] = row.tolist()
                        elif "Poisson Oranı" in r0: current_serim["raw_nu"] = row.tolist()
                        elif "Elastisite" in r0 or "Young" in r0: current_serim["raw_E"] = row.tolist()
                        elif "Kayma Modülü" in r0 or "Gmax" in r0: current_serim["raw_G"] = row.tolist()
                        elif "Bulk" in r0 or "Sıkışmazlık" in r0: current_serim["raw_K"] = row.tolist() 
                        elif "Vs30 =" in r0 or "Vs30" in r0: current_serim["raw_vs30"] = row.tolist()
                
                for s in param_ss_list:
                    if "raw_vp" not in s: continue
                    vs30_val = "-"
                    if "raw_vs30" in s:
                        for val in s["raw_vs30"][2:]: 
                            if pd.notna(val) and str(val).strip() != "": vs30_val = val; break
                    for col_idx in range(2, len(s["raw_vp"])):
                        vp_val = s["raw_vp"][col_idx]
                        if pd.isna(vp_val) or str(vp_val).strip() == "": continue
                        layer = {}
                        layer["vp"] = vp_val
                        layer["vs"] = s.get("raw_vs", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_vs", [])) else "-"
                        layer["h"] = s.get("raw_h", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_h", [])) else "-"
                        layer["rho"] = s.get("raw_rho", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_rho", [])) else "-"
                        layer["nu"] = s.get("raw_nu", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_nu", [])) else "-"
                        layer["E"] = s.get("raw_E", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_E", [])) else "-"
                        layer["G"] = s.get("raw_G", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_G", [])) else "-"
                        layer["K"] = s.get("raw_K", [np.nan]*(col_idx+1))[col_idx] if col_idx < len(s.get("raw_K", [])) else "-" 
                        layer["vs30"] = vs30_val if col_idx == 2 else "-"
                        s["layers"].append(layer)
            except Exception as e:
                _log_silent("jeofizik_excel_parse", e)
                traceback.print_exc()
                param_ss_list = ss_list 
        else: param_ss_list = ss_list

        tum_vs30 = []
        for ss in param_ss_list:
            layers = ss.get("layers", [])
            if not layers: continue
            vs30_raw = layers[0].get("vs30", 0)
            try: v = float(str(vs30_raw).replace(",",".")); 
            except Exception as exc:
                _log_silent("vs30_parse", exc)
                v=0
            if v > 0: tum_vs30.append(v)
            
        # MT VERİLERİNDEN T0 (BASKIN PERİYOT) ÇEKİMİ
        tum_t0 = []
        for mt in mt_list:
            to_raw = mt.get("to", "")
            try:
                v_to = float(str(to_raw).replace(",", "."))
                if v_to > 0: tum_t0.append(v_to)
            except Exception as exc:
                _log_silent("mt_t0_parse", exc)
            
        yass_seviyeleri = []
        for s in sondajlar:
            try:
                d1 = safe_float(s.get("yass_d1")); d2 = safe_float(s.get("yass_d2"))
                if d1 > 0: yass_seviyeleri.append(d1)
                if d2 > 0: yass_seviyeleri.append(d2)
            except Exception as exc:
                _log_silent("yass_parse", exc)

        prefixes = ["", "S1_", "S2_", "S3_", "S4_", "S5_"]
        kunye_map = [("sahibi", "PROJE_ADI"), ("il", "IL"), ("ilce", "ILCE"), ("mah", "MAHALLE"), ("mev", "MEVKI"), ("paf", "PAFTA"), ("ada", "ADA"), ("par", "PARSEL")]
        for key, tag_base in kunye_map:
            val = kunye.get(key, "")
            for pre in prefixes: replace_text(doc, f"[{pre}{tag_base}]", val)
        
        replace_text(doc, "[KATEGORI]", arazi.get("kategori", "-"))
        replace_text(doc, "[KATEGORI_ZEMIN]", arazi.get("zemin", "-")) 
        replace_text(doc, "[PGA]", arazi.get("pga", "-"))
        replace_text(doc, "[JEO_TARIH]", jeofizik.get("tarih", "-"))
        replace_text(doc, "[SAYI_SS]", str(len(ss_list)))
        replace_text(doc, "[SAYI_MT]", str(len(mt_list)))
        replace_text(doc, "[YEREL_ZEMIN]", app_instance.veri["bina"].get("ysinif", "-"))
        replace_text(doc, "[KOT_ORT]", arazi.get("ort", "-"))
        replace_text(doc, "[KOT_MAX]", arazi.get("max", "-"))
        replace_text(doc, "[KOT_MIN]", arazi.get("min", "-"))
        replace_text(doc, "[EGIM_YUZDE]", arazi.get("egim", "-"))
        replace_text(doc, "[EGIM_YONU]", arazi.get("yon", "-"))
        
        imar_alani_ham = arazi.get("imar_alani", "").strip(); imar_alani_final = f"({imar_alani_ham})" if imar_alani_ham else "-"
        replace_text(doc, "[IMAR_ALANI]", imar_alani_final)
        replace_text(doc, "[IMAR_DURUMU]", arazi.get("imar_durumu", "-"))

        ay = clean_val(app_instance.veri["arazi"].get("alan_y", "-")); ax = clean_val(app_instance.veri["arazi"].get("alan_x", "-"))
        replace_text(doc, "[ALAN_ENLEM]", ay); replace_text(doc, "[ALAN_BOYLAM]", ax)
        
        if sondajlar:
            ozet_parca = ", ".join([f"{s['no']}: {s['der']}m" for s in sondajlar])
            sondaj_metni = f"Sahada toplam {len(sondajlar)} adet sondaj kuyusu ({ozet_parca}) açılmıştır."
        else: sondaj_metni = "Sahada sondaj çalışması yapılmamıştır."
        replace_text(doc, "[SONDAJ_BILGISI]", sondaj_metni)

        bina = app_instance.veri["bina"]
        for p in iter_all_paragraphs(doc):
            if "[BINA_BILGILERI]" in p.text:
                p.text = p.text.replace("[BINA_BILGILERI]", "")
                tables = bina_bilgileri_tablolari_olustur(doc, bina)
                for table in reversed(tables):
                    p._p.addnext(table._tbl)
                break
        
        for p in iter_all_paragraphs(doc):
            if "[Sondaj]" in p.text:
                p.text = p.text.replace("[Sondaj]", ""); headers = ["Kuyu No", "Başlangıç", "Bitiş", "Enlem", "Boylam", "Kot", "Derinlik", "Litoloji"]; table = doc.add_table(rows=1, cols=len(headers)); table.style = 'Table Grid'
                for i, h in enumerate(headers): set_cell_text_clean(table.rows[0].cells[i], h, bold=True); set_vertical_cell_alignment(table.rows[0].cells[i], "center")
                for s in app_instance.veri["sondaj"]:
                    lits = s.get("litoloji", []); kuyu_no = clean_val(s["no"]); bas_tar = clean_val(s["bas_tar"]); bit_tar = clean_val(s["bit_tar"]); enlem = clean_val(s["y"]); boylam = clean_val(s["x"]); kot = clean_val(s["k"])
                    if not lits: 
                        row = table.add_row(); set_cell_text_clean(row.cells[0], kuyu_no)
                        for i, v in enumerate([bas_tar, bit_tar, enlem, boylam, kot, "-", "-"]): set_cell_text_clean(row.cells[i+1], v)
                        continue
                    start_idx = len(table.rows)
                    for lit in lits:
                        row = table.add_row(); lit_depth = f"{clean_val(lit[0])}-{clean_val(lit[1])}"; set_cell_text_clean(row.cells[6], lit_depth); set_cell_text_clean(row.cells[7], clean_val(lit[2]), alignment=WD_ALIGN_PARAGRAPH.LEFT)
                    end_idx = len(table.rows) - 1; vals = [kuyu_no, bas_tar, bit_tar, enlem, boylam, kot]
                    if end_idx > start_idx:
                        for col_idx, val in enumerate(vals): first = table.rows[start_idx].cells[col_idx]; last = table.rows[end_idx].cells[col_idx]; first.merge(last); set_cell_text_clean(first, val); set_vertical_cell_alignment(first, "center")
                    else:
                        for col_idx, val in enumerate(vals): set_cell_text_clean(table.rows[start_idx].cells[col_idx], val); set_vertical_cell_alignment(table.rows[start_idx].cells[col_idx], "center")
                apply_report_table_style(table, header_rows=1, text_cols={7}, widths_cm=[1.5, 1.8, 1.8, 2.2, 2.2, 1.4, 1.7, 5.4])
                p._p.addnext(table._tbl); break 
        
        yass_data = []
        for s in app_instance.veri["sondaj"]: v1 = f"{clean_val(s.get('yass_d1'))} ({clean_val(s.get('yass_t1'))})" if s.get('yass_d1') else "-"; v2 = f"{clean_val(s.get('yass_d2'))} ({clean_val(s.get('yass_t2'))})" if s.get('yass_d2') else "-"; yass_data.append([s["no"], v1, v2])
        islem_tablo_yerlestir(doc, "[YASS_TABLO]", ["Kuyu No", "1. Ölçüm (Delgi Sonu)", "2. Ölçüm (Statik)"], yass_data)

        lab_fizik_headers = ["Birim", "Değer", "Çakıl (%)", "Kum (%)", "Silt+Kil (%)", "Kil (%)", "LL (%)", "PL (%)", "PI (%)", "Wn (%)", "γn (g/cm³)", "γk (g/cm³)"]
        lab_mekanik_headers = ["Birim", "Değer", "İçsel Sürtünme (ϕ)", "Kohezyon (c)"]
        
        zemin_ozet_yazildi = False
        lab_birim_isimleri = []
        lito_groups = {}
        unit_spt_values = {}

        if app_instance.lab_excel_path:
            try:
                df_lab = pd.read_excel(app_instance.lab_excel_path, header=None)
                h_idx = 0
                for r, row in df_lab.head(30).iterrows():
                    if any("Sondaj No" in str(x) for x in row): h_idx = r; break
                hb = df_lab.iloc[h_idx:h_idx+5].copy().replace(r'^\s*$', np.nan, regex=True); hb.iloc[0] = hb.iloc[0].ffill()
                col_sigs = [" ".join([str(x).strip().upper() for x in hb.iloc[:, c] if pd.notna(x)]) for c in range(hb.shape[1])]
                cols = {}
                candidates_c = []
                for i, s in enumerate(col_sigs):
                    s_clean = temizle_baslik(s)
                    if "siniflama" in s_clean or "uscs" in s_clean or "sinif" in s_clean: cols['sinif']=i
                    if "wn" in s_clean or "su muhtevasi" in s_clean or "nem" in s_clean: cols['Wn']=i
                    if "ll" in s_clean or "likit" in s_clean: cols['LL']=i
                    if "pl" in s_clean or "plastik" in s_clean: cols['PL']=i
                    if "pi" in s_clean or "plastisite" in s_clean: cols['PI']=i
                    if "cakil" in s_clean or "gravel" in s_clean: cols['cakil']=i
                    if "kum" in s_clean or "sand" in s_clean: cols['kum']=i
                    if "kil" in s_clean or "clay" in s_clean: cols['kil']=i
                    if "silt" in s_clean: cols['silt']=i
                    if "dogal" in s_clean or "gn" in s_clean: cols['gn']=i
                    if "kuru" in s_clean or "gk" in s_clean: cols['gk']=i
                    if "direkt" in s_clean and ("c" in s_clean or "kohezyon" in s_clean): candidates_c.append(i)
                if candidates_c:
                    best_c = -1; max_count = -1; data_start = h_idx + 5
                    for cand_idx in candidates_c:
                        count = df_lab.iloc[data_start:, cand_idx].count()
                        if count > max_count: max_count = count; best_c = cand_idx
                    if best_c != -1: cols['c'] = best_c; potential_phi = best_c + 1; 
                    if potential_phi < df_lab.shape[1]: cols['phi'] = potential_phi

                if 'sinif' in cols:
                    data_start = h_idx + 5; df_c = df_lab.iloc[data_start:].copy(); df_c.columns = range(df_c.shape[1])
                    df_c.rename(columns={v:k for k,v in cols.items()}, inplace=True)
                    df_c['GRUP'] = df_c['sinif'].apply(zemin_sinifi_cevir); df_gruplanmis = df_c.groupby('GRUP')

                    for n, _ in df_gruplanmis:
                        if str(n).lower() != "tanımsız":
                            lab_birim_isimleri.append(str(n))
                    lab_birim_isimleri.sort(key=len, reverse=True)

                    lito_groups = {name: {} for name in lab_birim_isimleri}
                    unit_spt_values = {name: [] for name in lab_birim_isimleri}

                    for s in app_instance.veri["sondaj"]:
                        kuyu_no = s["no"]
                        for lit in s.get("litoloji", []):
                            top_val = safe_float(lit[0])
                            bot_val = safe_float(lit[1])
                            desc = str(lit[2]).strip().lower()
                            
                            matched_unit = None
                            for lab_name in lab_birim_isimleri:
                                if lab_name.lower() in desc:
                                    matched_unit = lab_name
                                    break 
                            
                            if matched_unit:
                                if kuyu_no not in lito_groups[matched_unit]: 
                                    lito_groups[matched_unit][kuyu_no] = []
                                lito_groups[matched_unit][kuyu_no].append((top_val, bot_val))

                    for s in app_instance.veri["sondaj"]:
                        kuyu_no = s["no"]
                        for spt in s.get("spt", []):
                            try:
                                spt_depth = safe_float(spt[0])
                                val_str = str(spt[4]).strip().upper()
                                if val_str == "R" or "REF" in val_str: n30 = 51.0
                                else: n30 = float(spt[4])

                                for unit_name, kuyu_dict in lito_groups.items():
                                    if kuyu_no in kuyu_dict:
                                        for (top, bot) in kuyu_dict[kuyu_no]:
                                            if top <= spt_depth < bot:
                                                unit_spt_values[unit_name].append(n30)
                                                break 
                            except Exception as exc:
                                _log_silent("spt_unit_summary", exc)

                    ozet_metinler = []
                    
                    for grup_adi, grup_df in df_gruplanmis:
                        if str(grup_adi).lower() == "tanımsız": continue

                        val_cakil = pd.to_numeric(grup_df.get('cakil', pd.Series()), errors='coerce')
                        ort_cakil = val_cakil.mean() if not val_cakil.empty else 0.0
                        
                        val_kum = pd.to_numeric(grup_df.get('kum', pd.Series()), errors='coerce')
                        ort_kum = val_kum.mean() if not val_kum.empty else 0.0
                        
                        silt_val = pd.to_numeric(grup_df.get('silt', pd.Series()), errors='coerce').fillna(0)
                        kil_val = pd.to_numeric(grup_df.get('kil', pd.Series()), errors='coerce').fillna(0)
                        val_ince = silt_val + kil_val
                        ort_ince = val_ince.mean() if not val_ince.empty else 0.0
                        
                        g_clean = str(grup_adi).strip()
                        is_cohesive = False
                        
                        if g_clean in INCE_DANELILER:
                            is_cohesive = True
                        elif g_clean in IRI_DANELILER:
                            is_cohesive = False
                        else:
                            g_low = g_clean.lower()
                            is_cohesive = True if "kil" in g_low or "silt" in g_low else False
                        
                        found_labels = set()
                        spt_source = unit_spt_values.get(g_clean, []) 

                        if spt_source:
                            for val in spt_source:
                                if is_cohesive:
                                    if val < 2: found_labels.add("çok yumuşak")
                                    elif val < 5: found_labels.add("yumuşak")
                                    elif val < 9: found_labels.add("orta katı")
                                    elif val < 16: found_labels.add("katı")
                                    elif val < 31: found_labels.add("çok katı")
                                    else: found_labels.add("sert")
                                else:
                                    if val < 5: found_labels.add("çok gevşek")
                                    elif val < 11: found_labels.add("gevşek")
                                    elif val < 31: found_labels.add("orta sıkı")
                                    elif val < 51: found_labels.add("sıkı")
                                    else: found_labels.add("çok sıkı")
                            
                            order_map = {"çok yumuşak": 1, "yumuşak": 2, "orta katı": 3, "katı": 4, "çok katı": 5, "sert": 6, "çok gevşek": 1, "gevşek": 2, "orta sıkı": 3, "sıkı": 4, "çok sıkı": 5}
                            sorted_labels = sorted(list(found_labels), key=lambda x: order_map.get(x, 99))
                            durum_text = " - ".join(sorted_labels)
                        else:
                            durum_text = ""

                        if durum_text:
                            if is_cohesive: giris_cumlesi = f"{grup_adi} birimleri {durum_text} olup"
                            else: giris_cumlesi = f"{grup_adi} birimleri sıkılığı {durum_text} olup"
                        else: giris_cumlesi = f"{grup_adi} birimleri"

                        lab_kisim = f"laboratuvar sonuçlarına göre içeriğinde ortalama olarak %{ort_cakil:.2f} Çakıl, %{ort_kum:.2f} Kum ve %{ort_ince:.2f} Silt-Kil barındırmaktadır"
                        ozet_metinler.append(f"{giris_cumlesi}, {lab_kisim}.")
                    
                    if ozet_metinler:
                        doc_replace_text_everywhere(doc, "[ZEMIN_OZET]", " ".join(ozet_metinler))
                        zemin_ozet_yazildi = True

                    for p in iter_all_paragraphs(doc):
                        if "[LAB_FIZIK]" in p.text:
                            p.text = p.text.replace("[LAB_FIZIK]", ""); t = create_word_table(doc, lab_fizik_headers, [])
                            table_has_data = False
                            for n, g in df_gruplanmis:
                                if n == "Tanımsız": continue
                                
                                s_exists = 'silt' in g
                                k_exists = 'kil' in g
                                row_min = t.add_row(); row_max = t.add_row(); row_avg = t.add_row()
                                row_min.cells[0].text = n; row_min.cells[1].text = "Min"; row_max.cells[1].text = "Max"; row_avg.cells[1].text = "Ort"
                                row_min.cells[0].merge(row_avg.cells[0]); set_cell_text_clean(row_min.cells[0], n, bold=False); set_vertical_cell_alignment(row_min.cells[0], "center")
                                set_cell_text_clean(row_min.cells[1], "Min"); set_cell_text_clean(row_max.cells[1], "Max"); set_cell_text_clean(row_avg.cells[1], "Ort")
                                
                                if s_exists or k_exists:
                                    s_val = pd.to_numeric(g['silt'] if s_exists else pd.Series(0, index=g.index), errors='coerce').fillna(0)
                                    k_val = pd.to_numeric(g['kil'] if k_exists else pd.Series(0, index=g.index), errors='coerce').fillna(0)
                                    fines = s_val + k_val
                                    set_cell_text_clean(row_min.cells[4], f"{fines.min():.2f}")
                                    set_cell_text_clean(row_max.cells[4], f"{fines.max():.2f}")
                                    set_cell_text_clean(row_avg.cells[4], f"{fines.mean():.2f}")

                                pmap = [('cakil', 2), ('kum', 3), ('kil', 5), ('LL', 6), ('PL', 7), ('PI', 8), ('Wn', 9), ('gn', 10), ('gk', 11)]
                                for key, ci in pmap:
                                    if key in g:
                                        safe_series = g[key].astype(str).str.replace(',', '.', regex=False)
                                        v = pd.to_numeric(safe_series, errors='coerce').dropna()
                                        v = v[v >= 0]
                                        if not v.empty: 
                                            set_cell_text_clean(row_min.cells[ci], f"{v.min():.2f}"); set_cell_text_clean(row_max.cells[ci], f"{v.max():.2f}"); set_cell_text_clean(row_avg.cells[ci], f"{v.mean():.2f}"); table_has_data = True
                                for r_obj in [row_min, row_max, row_avg]: 
                                    for c_obj in r_obj.cells: set_vertical_cell_alignment(c_obj, "center")
                            if table_has_data:
                                apply_report_table_style(t, header_rows=1, text_cols={0}, widths_cm=[2.1, 1.2, 1.35, 1.35, 1.45, 1.35, 1.2, 1.2, 1.2, 1.25, 1.45, 1.45])
                                p._p.addnext(t._tbl)
                            break
                    
                    for p in iter_all_paragraphs(doc):
                         if "[LAB_MEKANIK]" in p.text:
                            p.text = p.text.replace("[LAB_MEKANIK]", ""); t = create_word_table(doc, lab_mekanik_headers, [])
                            table_has_data = False
                            for n, g in df_gruplanmis:
                                if n == "Tanımsız": continue
                                vals_c = pd.to_numeric(g.get('c', pd.Series()), errors='coerce').dropna()
                                vals_phi = pd.to_numeric(g.get('phi', pd.Series()), errors='coerce').dropna()
                                if vals_c.empty and vals_phi.empty: continue
                                row_min = t.add_row(); row_max = t.add_row(); row_avg = t.add_row()
                                row_min.cells[0].merge(row_avg.cells[0]); set_cell_text_clean(row_min.cells[0], n, bold=False); set_vertical_cell_alignment(row_min.cells[0], "center")
                                set_cell_text_clean(row_min.cells[1], "Min"); set_cell_text_clean(row_max.cells[1], "Max"); set_cell_text_clean(row_avg.cells[1], "Ort")
                                pmap = [('phi', 2), ('c', 3)]
                                for key, ci in pmap:
                                    if key in g:
                                        safe_series = g[key].astype(str).str.replace(',', '.', regex=False)
                                        v = pd.to_numeric(safe_series, errors='coerce').dropna()
                                        v = v[v >= 0]
                                        if not v.empty: 
                                            set_cell_text_clean(row_min.cells[ci], f"{v.min():.2f}"); set_cell_text_clean(row_max.cells[ci], f"{v.max():.2f}"); set_cell_text_clean(row_avg.cells[ci], f"{v.mean():.2f}"); table_has_data = True
                                for r_obj in [row_min, row_max, row_avg]: 
                                    for c_obj in r_obj.cells: set_vertical_cell_alignment(c_obj, "center")
                            if table_has_data:
                                apply_report_table_style(t, header_rows=1, text_cols={0}, widths_cm=[3.0, 1.4, 3.0, 3.0])
                                p._p.addnext(t._tbl)
                            break
            except Exception as exc:
                _log_silent("zemin_ozet_table", exc)

        if not zemin_ozet_yazildi: doc_replace_text_everywhere(doc, "[ZEMIN_OZET]", "Laboratuvar verisi girilmediği için zemin özeti oluşturulamadı.")
        islem_tablo_yerlestir(doc, "[LAB_FIZIK]", lab_fizik_headers, []) 
        islem_tablo_yerlestir(doc, "[LAB_MEKANIK]", lab_mekanik_headers, []) 

        lito_paragraphs = litoloji_dagilim_paragraflari(app_instance.veri.get("sondaj", []))
        replace_tag_with_paragraphs(doc, "[LITOLOJI_DAGILIM]", lito_paragraphs)

        spt_data = []; pmt_data = []; kaya_data = []
        for s in app_instance.veri["sondaj"]:
            for row in s.get("spt", []): 
                if len(row)>=5: spt_data.append([s["no"], row[0], row[1], row[2], row[3], row[4]])
            for row in s.get("pmt", []): 
                if len(row)>=3: pmt_data.append([s["no"], row[0], row[1], row[2]])
            for row in s.get("kaya", []): 
                if len(row)>=4: kaya_data.append([s["no"], row[0], row[1], row[2], row[3]])
        
        for p in iter_all_paragraphs(doc):
            if "[SPT]" in p.text:
                p.text = p.text.replace("[SPT]", ""); headers = ["Kuyu No", "Derinlik", "0-15", "15-30", "30-45", "N30"]; table = create_word_table(doc, headers, [])
                for s in app_instance.veri["sondaj"]:
                    spt_rows = s.get("spt", []); valid_spt = [row for row in spt_rows if len(row) >= 5]
                    if not valid_spt: continue
                    start_idx = len(table.rows)
                    for idx, row in enumerate(valid_spt):
                        r = table.add_row(); kuyu_text = clean_val(s["no"]) if idx == 0 else ""
                        set_cell_text_clean(r.cells[0], kuyu_text); set_cell_text_clean(r.cells[1], clean_val(row[0])); set_cell_text_clean(r.cells[2], clean_val(row[1])); set_cell_text_clean(r.cells[3], clean_val(row[2])); set_cell_text_clean(r.cells[4], clean_val(row[3])); set_cell_text_clean(r.cells[5], clean_val(row[4]))
                        for c in r.cells: set_vertical_cell_alignment(c, "center")
                    end_idx = len(table.rows) - 1
                    if end_idx > start_idx: first = table.rows[start_idx].cells[0]; first.merge(table.rows[end_idx].cells[0]); set_cell_text_clean(first, clean_val(s["no"])); set_vertical_cell_alignment(first, "center")
                apply_report_table_style(table, header_rows=1, widths_cm=[2.0, 2.0, 1.5, 1.5, 1.5, 1.5])
                p._p.addnext(table._tbl); break

        islem_tablo_yerlestir(doc, "[PMT]", ["Kuyu No", "Derinlik", "Em (kg/cm2)", "Pl (kg/cm2)"], pmt_data)
        islem_tablo_yerlestir(doc, "[KAYA_TABLO]", ["Kuyu No", "Derinlik", "TCR (%)", "SCR (%)", "RQD (%)"], kaya_data)
        
        # --- JEO_PARAMETRE ÇİFT BAŞLIKLI DİKEY TABLO (TRANSPOZE) ---
        for p in iter_all_paragraphs(doc):
            if "[JEO_PARAMETRE]" in p.text:
                p.text = p.text.replace("[JEO_PARAMETRE]", "")

                param_etiketleri = [
                    ("Kalınlık (m)", "h"), ("Vp (m/s)", "vp"), ("Vs (m/s)", "vs"), 
                    ("Yoğunluk (g/cm³)", "rho"), ("Poisson Oranı", "nu"), 
                    ("Elastisite Mod. (kg/cm²)", "E"), ("Kayma Mod. (kg/cm²)", "G"), 
                    ("Bulk Mod. (kg/cm²)", "K")
                ]

                def jeo_parametre_tablosu_olustur(serimler):
                    all_layers_flat = []
                    serim_gruplari = []
                    for ss in serimler:
                        layers = ss.get("layers", [])
                        if not layers:
                            continue
                        serim_ad = clean_val(ss.get("ad", "-"))
                        all_layers_flat.extend([(layer, idx == len(layers) - 1) for idx, layer in enumerate(layers)])
                        serim_gruplari.append((serim_ad, len(layers)))

                    total_cols = 1 + len(all_layers_flat)
                    if total_cols <= 1:
                        return None

                    table = doc.add_table(rows=2, cols=total_cols)
                    table.style = 'Table Grid'
                    set_cell_text_clean(table.rows[0].cells[0], "Parametre", bold=True)

                    current_col = 1
                    for serim_ad, layer_count in serim_gruplari:
                        start_cell = table.rows[0].cells[current_col]
                        end_cell = table.rows[0].cells[current_col + layer_count - 1]
                        if layer_count > 1:
                            start_cell.merge(end_cell)
                        set_cell_text_clean(start_cell, serim_ad, bold=True)
                        current_col += layer_count

                    table.rows[0].cells[0].merge(table.rows[1].cells[0])

                    current_col = 1
                    for _, layer_count in serim_gruplari:
                        for layer_idx in range(1, layer_count + 1):
                            set_cell_text_clean(table.rows[1].cells[current_col], f"Tab. {layer_idx}", bold=True)
                            current_col += 1

                    for baslik, anahtar in param_etiketleri:
                        row_cells = table.add_row().cells
                        set_cell_text_clean(row_cells[0], baslik, bold=True)
                        for col_idx, (layer, is_last) in enumerate(all_layers_flat):
                            val = "-" if anahtar == "h" and is_last else fmt_jeo(layer.get(anahtar, "-"))
                            set_cell_text_clean(row_cells[col_idx + 1], val)

                    for row in table.rows:
                        for cell in row.cells:
                            set_vertical_cell_alignment(cell, "center")
                    apply_report_table_style(table, header_rows=2, label_cols={0})
                    return table

                valid_serimler = [ss for ss in param_ss_list if ss.get("layers", [])]
                tables = []
                for start in range(0, len(valid_serimler), 3):
                    table = jeo_parametre_tablosu_olustur(valid_serimler[start:start + 3])
                    if table is not None:
                        tables.append(table)
                if not tables:
                    continue
                for table in reversed(tables):
                    p._p.addnext(table._tbl)
                break

        for p in iter_all_paragraphs(doc):
            if "[MASW]" in p.text:
                p.text = p.text.replace("[MASW]", "")
                masw_headers = ["Serim No", "Ortam No", "Vs(m/sn)", "Kalınlık h (m)", "Vs30(m/sn)"]
                table = create_word_table(doc, masw_headers, [])
                for ss in param_ss_list:
                    layers = ss.get("layers", [])
                    if not layers: continue
                    start_idx = len(table.rows)
                    vs30_val = fmt_jeo(layers[0].get("vs30", "-"))
                    serim_ad = clean_val(ss.get("ad", "-"))
                    
                    for idx, layer in enumerate(layers):
                        r = table.add_row()
                        set_cell_text_clean(r.cells[0], serim_ad if idx == 0 else "")
                        set_cell_text_clean(r.cells[1], str(idx + 1))
                        set_cell_text_clean(r.cells[2], fmt_jeo(layer.get("vs", "-")))
                        h_val = "-" if idx == len(layers) - 1 else fmt_jeo(layer.get("h", "-"))
                        set_cell_text_clean(r.cells[3], h_val)
                        set_cell_text_clean(r.cells[4], vs30_val if idx == 0 else "")
                        for c in r.cells: set_vertical_cell_alignment(c, "center")
                        
                    end_idx = len(table.rows) - 1
                    if end_idx > start_idx:
                        first_c0 = table.rows[start_idx].cells[0]
                        first_c0.merge(table.rows[end_idx].cells[0])
                        set_cell_text_clean(first_c0, serim_ad)
                        set_vertical_cell_alignment(first_c0, "center")
                        
                        first_c4 = table.rows[start_idx].cells[4]
                        first_c4.merge(table.rows[end_idx].cells[4])
                        set_cell_text_clean(first_c4, vs30_val)
                        set_vertical_cell_alignment(first_c4, "center")
                apply_report_table_style(table, header_rows=1, widths_cm=[2.2, 2.0, 2.3, 2.3, 2.3])
                p._p.addnext(table._tbl)
                break

        for p in iter_all_paragraphs(doc):
            if "[VP]" in p.text:
                p.text = p.text.replace("[VP]", "")
                vp_headers = ["Ölçü No", "Ortam No", "Vp (m/sn)"]
                table = create_word_table(doc, vp_headers, [])
                for ss in param_ss_list:
                    layers = jeofizik_vp_layers_sadelestir(ss.get("layers", []))
                    if not layers: continue
                    start_idx = len(table.rows)
                    serim_ad = clean_val(ss.get("ad", "-"))
                    
                    for idx, layer in enumerate(layers):
                        r = table.add_row()
                        set_cell_text_clean(r.cells[0], serim_ad if idx == 0 else "")
                        set_cell_text_clean(r.cells[1], str(idx + 1))
                        set_cell_text_clean(r.cells[2], fmt_jeo(layer.get("vp", "-")))
                        for c in r.cells: set_vertical_cell_alignment(c, "center")
                        
                    end_idx = len(table.rows) - 1
                    if end_idx > start_idx:
                        first_c0 = table.rows[start_idx].cells[0]
                        first_c0.merge(table.rows[end_idx].cells[0])
                        set_cell_text_clean(first_c0, serim_ad)
                        set_vertical_cell_alignment(first_c0, "center")
                apply_report_table_style(table, header_rows=1, widths_cm=[2.8, 2.0, 2.4])
                p._p.addnext(table._tbl)
                break

        for p in iter_all_paragraphs(doc):
            if "[JEO_KOOR]" in p.text:
                p.text = p.text.replace("[JEO_KOOR]", "")
                table = doc.add_table(rows=0, cols=7)
                table.style = 'Table Grid'
                
                def f_coord(v):
                    c = clean_val(v)
                    return f"{c}°" if c != "-" and not c.endswith("°") else c

                r0 = table.add_row()
                r0.cells[1].merge(r0.cells[6])
                set_cell_text_clean(r0.cells[1], "Koordinatlar(WGS84)", bold=True)
                
                r1 = table.add_row()
                r1.cells[1].merge(r1.cells[2]); set_cell_text_clean(r1.cells[1], "Düz Atış", bold=True)
                r1.cells[3].merge(r1.cells[4]); set_cell_text_clean(r1.cells[3], "Orta Atış", bold=True)
                r1.cells[5].merge(r1.cells[6]); set_cell_text_clean(r1.cells[5], "Ters Atış", bold=True)
                
                r2 = table.add_row()
                for idx, txt in enumerate(["", "Enlem", "Boylam", "Enlem", "Boylam", "Enlem", "Boylam"]):
                    if txt: set_cell_text_clean(r2.cells[idx], txt, bold=True)
                
                r0.cells[0].merge(r2.cells[0])
                set_cell_text_clean(r0.cells[0], "Çalışma No", bold=True)
                
                for ss in ss_list: 
                    r = table.add_row()
                    set_cell_text_clean(r.cells[0], clean_val(ss.get("ad", "-")))
                    c_list = ss.get("coords", ["-", "-", "-", "-", "-", "-"])
                    while len(c_list) < 6: c_list.append("-")
                    for i in range(6): set_cell_text_clean(r.cells[i+1], f_coord(c_list[i]))
                
                if mt_list:
                    rmt0 = table.add_row()
                    rmt0.cells[1].merge(rmt0.cells[6])
                    set_cell_text_clean(rmt0.cells[1], "Koordinatlar (WGS84)", bold=True)
                    
                    rmt1 = table.add_row()
                    rmt1.cells[1].merge(rmt1.cells[3]); set_cell_text_clean(rmt1.cells[1], "Enlem", bold=True)
                    rmt1.cells[4].merge(rmt1.cells[6]); set_cell_text_clean(rmt1.cells[4], "Boylam", bold=True)
                    
                    rmt0.cells[0].merge(rmt1.cells[0])
                    set_cell_text_clean(rmt0.cells[0], "Çalışma No", bold=True)
                    
                    for mt in mt_list:
                        r = table.add_row()
                        set_cell_text_clean(r.cells[0], clean_val(mt.get("no", "-")))
                        r.cells[1].merge(r.cells[3])
                        set_cell_text_clean(r.cells[1], f_coord(mt.get("y", "-")))
                        r.cells[4].merge(r.cells[6])
                        set_cell_text_clean(r.cells[4], f_coord(mt.get("x", "-")))

                for row in table.rows:
                    for cell in row.cells: set_vertical_cell_alignment(cell, "center")
                apply_report_table_style(table, header_rows=3, widths_cm=[2.2, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
                p._p.addnext(table._tbl)
                break

        mt_table_data = []; mt_headers = ["Ölçü No", "Baskın Frekans (Hz)", "Baskın Periyot (To) (sn)", "Ta (sn)", "Tb (sn)", "H/V Oranı", "Kayıt Süresi (dk)", "Formasyon"]
        for mt in mt_list:
            row = [mt.get("no", "-"), clean_val(mt.get("freq", "-")), clean_val(mt.get("to", "-")), clean_val(mt.get("ta", "-")), clean_val(mt.get("tb", "-")), clean_val(mt.get("hv", "-")), clean_val(mt.get("sure", "-")), "-"]
            mt_table_data.append(row)
        islem_tablo_yerlestir(doc, "[MT_TABLO]", mt_headers, mt_table_data)

        # DİNAMİK JEOFİZİK SONUÇ CÜMLESİ OLUŞTURMA
        sonuc_parcalari = []
        if tum_vs30:
            vs30_min = int(min(tum_vs30)); vs30_max = int(max(tum_vs30))
            vs30_range_str = f"{vs30_min}-{vs30_max}" if vs30_min != vs30_max else f"{vs30_min}"
            sonuc_parcalari.append(f"Vs30={vs30_range_str} m/sn")
            
        if tum_t0:
            t0_min = min(tum_t0); t0_max = max(tum_t0)
            if t0_min == t0_max:
                t0_str = "{:.2f}".format(t0_min).replace('.', ',')
            else:
                t0_str = "{:.2f}-{:.2f}".format(t0_min, t0_max).replace('.', ',')
            sonuc_parcalari.append(f"zemin hakim titreşim periyodu {t0_str}sn")

        if sonuc_parcalari:
            birlestirilmis = " olarak, ".join(sonuc_parcalari)
            jeo_sonuc_cumlesi = f"Çalışma alanında yapılan jeofizik çalışmalar sonucunda {birlestirilmis} olarak bulunmuştur."
            replace_text(doc, "[JEO_SONUC]", jeo_sonuc_cumlesi)
        else: 
            replace_text(doc, "[JEO_SONUC]", "")
        
        if not yass_seviyeleri:
            yass_oneri = "Yapılan sondaj çalışmaları sonucunda çalışma alanında yeraltı suyuna rastlanmamıştır. Ancak, olası yüzey ve atık sularının yapı temeline ve temelin oturacağı zemine sızarak meydana getirebileceği olumsuz etkiler göz önüne alınarak; su geçirgenliğini önlemek amacıyla standartlara uygun bir yalıtım projelendirilmeli ve suları temelden uzak tutacak etkin bir drenaj sistemi oluşturulmalıdır."
        else:
            min_y = min(yass_seviyeleri)
            max_y = max(yass_seviyeleri)
            if min_y == max_y:
                r_str = f"-{min_y}m derinlikte"
            else:
                r_str = f"-{min_y}m ila -{max_y}m derinlikleri arasında"
            
            yass_oneri = f"Yapılan sondaj çalışmaları sonucunda çalışma alanında {r_str} yeraltı suyuna rastlanmıştır. Yeraltı, yüzey ve atık sularının yapı temeline ve temelin oturacağı zemine sızarak meydana getirebileceği olumsuz etkiler göz önüne alınarak; su geçirgenliğini önlemek amacıyla standartlara uygun bir yalıtım projelendirilmeli ve suları temelden uzak tutacak etkin bir drenaj sistemi oluşturulmalıdır."
            
        replace_text(doc, "[YASS_ONERI]", yass_oneri)

        doc_replace_img(doc, "RESIM:Yerbuldurur", app_instance.img_yer)
        doc_replace_img(doc, "[RESIM_YERBULDURUR]", app_instance.img_yer)
        
        doc_replace_img(doc, "RESIM:TKGM", app_instance.img_tkgm)
        doc_replace_img(doc, "RESIM:PGA", app_instance.img_pga)
        
        doc_replace_img(doc, "[RESIM_JEOFIZIK]", getattr(app_instance, 'word_img_jeofizik', None))
        mjh_path = mjh_resim_yolu(app_instance)
        doc_replace_img(doc, "RESIM:MJH", mjh_path)
        doc_replace_img(doc, "[RESIM_MJH]", mjh_path)
        doc_replace_img(doc, "[RESIM:MJH]", mjh_path)
        doc_replace_img(doc, "[RESIM_SONDAJ]", getattr(app_instance, 'word_img_sondaj', None))
        doc_replace_img(doc, "[RESIM:SONDAJ]", getattr(app_instance, 'word_img_sondaj', None))
        
        cikti_klasor = app_instance.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor", "")
        save_opts = {"defaultextension": ".docx", "filetypes": [("Word Dosyası", "*.docx")]}
        if cikti_klasor and os.path.isdir(cikti_klasor):
            save_opts["initialdir"] = cikti_klasor
        final = filedialog.asksaveasfilename(**save_opts)
        if final:
            doc.save(final)
            return True, "Rapor oluşturuldu!"
        return False, "İptal edildi."

    except Exception as e:
        traceback.print_exc(); return False, f"Hata: {str(e)}"
