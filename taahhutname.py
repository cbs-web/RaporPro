import datetime
import os
import re
import tempfile

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE_PATH = os.path.join(APP_DIR, "sablonlar", "taahhutname_sablonu.xlsx")
TAAHHUT_SHEET = "tahhütname"
TAAHHUT_METNI = (
    "Yukarıdaki bilgilere sahip projenin müellifliğini üstlenmemde 6235 sayılı Türk Mühendis ve "
    "Mimar Odaları Birliği Kanunu, 3194 sayılı İmar Kanunu ve ilgili mevzuat kapsamında süreli veya "
    "süresiz olarak mesleki faaliyet haklarımda herhangi bir kısıtlılık bulunmadığını ve odama "
    "üyeliğimin devam ettiğini taahhüt ederim.\n\n"
    "Yukarıdaki bilgilere sahip yapıya ilişkin hazırlanacak tüm projelerde, 3194 sayılı Kanun ve "
    "deprem, yangın,enerji verimliliği, asansör gibi ilgili tüm mevzuat hükümlerini eksiksiz "
    "uygulayacağımı taahhüt ederim"
)


def _clean(value, fallback=""):
    text = "" if value is None else str(value).strip()
    return text if text else fallback


def _safe_name(value, fallback="dosya"):
    text = _clean(value, fallback)
    text = re.sub(r"[^\w\-\.]+", "_", text, flags=re.UNICODE).strip("._")
    return text or fallback


def _mahalle_metni(mahalle):
    text = _clean(mahalle)
    if not text:
        return ""
    lowered = text.casefold()
    if "mah" in lowered or "mahalle" in lowered:
        return text
    return f"{text} Mah."


def taahhutname_yapi_adresi(veri):
    kunye = (veri or {}).get("kunye", {})
    parts = [_mahalle_metni(kunye.get("mah")), _clean(kunye.get("ilce")), _clean(kunye.get("il"))]
    return " ".join(part for part in parts if part).strip()


def _ilgili_idare(veri):
    ayarlar = (veri or {}).get("ayarlar", {})
    kunye = (veri or {}).get("kunye", {})
    explicit = _clean(ayarlar.get("taahhut_ilgili_idare"))
    if explicit:
        return explicit
    ilce = _clean(kunye.get("ilce"))
    il = _clean(kunye.get("il"))
    if ilce:
        return f"{ilce} Belediyesi"
    if il:
        return f"{il} Belediyesi"
    return ""


def _taahhut_tarihi(veri):
    ayarlar = (veri or {}).get("ayarlar", {})
    return _clean(ayarlar.get("taahhut_tarih"), datetime.datetime.now().strftime("%d.%m.%Y"))


def _profile(veri, tur):
    ayarlar = (veri or {}).get("ayarlar", {})
    prefix = "taahhut_jeofizik" if tur == "jeofizik" else "taahhut_jeoloji"
    defaults = {
        "jeoloji": {
            "ad": "Gökalp DOĞAN",
            "sicil": "7400",
            "unvan": "JEOLOJİ MÜHENDİSİ",
            "imza_unvan": "Jeoloji Mühendisi",
            "adres": "İsmetpaşa Mh. Hasan Mevsuf Sk. No :4 Da:5",
            "telefon": "0 545 639 90 62",
        },
        "jeofizik": {
            "ad": "Suat ERGİN",
            "sicil": "1982",
            "unvan": "JEOFİZİK MÜHENDİSİ",
            "imza_unvan": "Jeofizik Mühendisi",
            "adres": "İsmetpaşa Mh. Hasan Mevsuf Sk. No :4 Da:5",
            "telefon": "0 532 281 12 95",
        },
    }[tur]
    return {key: _clean(ayarlar.get(f"{prefix}_{key}"), value) for key, value in defaults.items()}


def taahhutname_context(veri, tur):
    tur = "jeofizik" if tur == "jeofizik" else "jeoloji"
    kunye = (veri or {}).get("kunye", {})
    profile = _profile(veri, tur)
    adres = taahhutname_yapi_adresi(veri)
    return {
        "tur": tur,
        "profile": profile,
        "oda_sicil_no": profile["sicil"],
        "unvan": profile["unvan"],
        "muhendis_ad": profile["ad"],
        "muhendis_imza_unvan": profile["imza_unvan"],
        "muhendis_adres": profile["adres"],
        "muhendis_telefon": profile["telefon"],
        "il": _clean(kunye.get("il")),
        "ilce": _clean(kunye.get("ilce")),
        "mahalle": _clean(kunye.get("mah")),
        "mevki": _clean(kunye.get("mev"), "-"),
        "ilgili_idare": _ilgili_idare(veri),
        "pafta": _clean(kunye.get("paf"), "-"),
        "ada": _clean(kunye.get("ada")),
        "parsel": _clean(kunye.get("par")),
        "yapi_adresi": adres,
        "yapi_sahibi": _clean(kunye.get("sahibi")),
        "yapi_sahibi_adresi": adres,
        "proje_turu": "ZEMİN ETÜDÜ RAPORU",
        "tarih": _taahhut_tarihi(veri),
    }


def taahhutname_sablon_path(veri=None):
    ayarlar = (veri or {}).get("ayarlar", {})
    custom = _clean(ayarlar.get("taahhut_excel_sablon_path"))
    if custom and os.path.exists(custom):
        return custom
    return DEFAULT_TEMPLATE_PATH


def _set(ws, cell, value):
    ws[cell] = value


def _fill_ana_sayfa(wb, ctx):
    if "ANA SAYFA" not in wb.sheetnames:
        return
    ws = wb["ANA SAYFA"]
    values = {
        "C2": ctx["yapi_sahibi"],
        "C3": ctx["il"],
        "C4": ctx["ilce"],
        "C5": ctx["mahalle"],
        "C6": ctx["mevki"],
        "C7": ctx["pafta"],
        "C8": ctx["ada"],
        "C9": ctx["parsel"],
        "C11": ctx["ilgili_idare"],
        "C12": ctx["yapi_adresi"],
    }
    for cell, value in values.items():
        _set(ws, cell, value)


def _fill_profile_cells(ws, veri):
    jeofizik = _profile(veri, "jeofizik")
    jeoloji = _profile(veri, "jeoloji")

    ws["A4"] = "Oda Sicil No"
    ws["C4"] = jeofizik["sicil"]
    ws["C5"] = jeofizik["unvan"]
    ws["C6"] = jeofizik["adres"]
    ws["C7"] = jeofizik["telefon"]
    ws["F31"] = jeofizik["ad"]
    ws["F32"] = jeofizik["imza_unvan"]

    ws["J4"] = "Oda Sicil No"
    ws["L4"] = jeoloji["sicil"]
    ws["L5"] = jeoloji["unvan"]
    ws["L6"] = jeoloji["adres"]
    ws["L7"] = jeoloji["telefon"]
    ws["O31"] = jeoloji["ad"]
    ws["O32"] = jeoloji["imza_unvan"]


def _fill_project_cells(ws, ctx):
    jeofizik_values = {
        "D11": ctx["il"],
        "E11": ctx["ilce"],
        "D12": ctx["ilgili_idare"],
        "D13": ctx["pafta"],
        "F13": ctx["ada"],
        "G13": ctx["parsel"],
        "D14": ctx["yapi_adresi"],
        "D15": ctx["yapi_sahibi"],
        "D16": ctx["yapi_sahibi_adresi"],
        "D17": ctx["proje_turu"],
        "F30": ctx["tarih"],
    }
    jeoloji_values = {
        "M11": ctx["il"],
        "N11": ctx["ilce"],
        "M12": ctx["ilgili_idare"],
        "M13": ctx["pafta"],
        "O13": ctx["ada"],
        "P13": ctx["parsel"],
        "M14": ctx["yapi_adresi"],
        "M15": ctx["yapi_sahibi"],
        "M16": ctx["yapi_sahibi_adresi"],
        "M17": ctx["proje_turu"],
        "O30": ctx["tarih"],
    }
    for cell, value in {**jeofizik_values, **jeoloji_values}.items():
        _set(ws, cell, value)


def _range_overlaps(a, b):
    return not (a.max_col < b.min_col or a.min_col > b.max_col or a.max_row < b.min_row or a.min_row > b.max_row)


def _merge_body_text(ws, cell_range):
    from openpyxl.worksheet.cell_range import CellRange

    target = CellRange(cell_range)
    for merged in list(ws.merged_cells.ranges):
        if _range_overlaps(merged, target):
            ws.unmerge_cells(str(merged))
    ws.merge_cells(cell_range)
    cell = ws.cell(target.min_row, target.min_col)
    cell.value = TAAHHUT_METNI
    cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="justify")
    cell.font = Font(name="Arial", size=10)


def _fill_body_text(ws):
    _merge_body_text(ws, "A19:I28")
    _merge_body_text(ws, "J19:R28")


def _configure_workbook_for_type(wb, tur):
    ws = wb[TAAHHUT_SHEET]
    ws.sheet_view.showGridLines = False
    for sheet in wb.worksheets:
        sheet.sheet_state = "hidden"
    ws.sheet_state = "visible"
    wb.active = wb.sheetnames.index(TAAHHUT_SHEET)

    for idx in range(1, 28):
        ws.column_dimensions[get_column_letter(idx)].hidden = False

    if tur == "jeofizik":
        ws.print_area = "A1:I48"
        for idx in range(10, 28):
            ws.column_dimensions[get_column_letter(idx)].hidden = True
        ws.freeze_panes = "A1"
    else:
        ws.print_area = "J1:R48"
        for idx in list(range(1, 10)) + list(range(19, 28)):
            ws.column_dimensions[get_column_letter(idx)].hidden = True
        ws.freeze_panes = "J1"

    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = 9
    try:
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
    except Exception:
        pass
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
    except Exception:
        pass


def _build_workbook(veri, tur):
    template_path = taahhutname_sablon_path(veri)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Taahhütname Excel şablonu bulunamadı: {template_path}")
    wb = load_workbook(template_path)
    if TAAHHUT_SHEET not in wb.sheetnames:
        raise ValueError(f"Şablonda '{TAAHHUT_SHEET}' sayfası bulunamadı.")
    ctx = taahhutname_context(veri, tur)
    _fill_ana_sayfa(wb, ctx)
    ws = wb[TAAHHUT_SHEET]
    _fill_profile_cells(ws, veri)
    _fill_project_cells(ws, ctx)
    _fill_body_text(ws)
    _configure_workbook_for_type(wb, "jeofizik" if tur == "jeofizik" else "jeoloji")
    return wb


def _export_xlsx_to_pdf(xlsx_path, pdf_path):
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError(f"Excel PDF aktarımı için pywin32 bulunamadı: {exc}") from exc

    excel = None
    workbook = None
    pythoncom.CoInitialize()
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Open(os.path.abspath(xlsx_path))
        worksheet = workbook.Worksheets(TAAHHUT_SHEET)
        worksheet.ExportAsFixedFormat(0, os.path.abspath(pdf_path))
    except Exception as exc:
        raise RuntimeError(
            "Taahhütname PDF'e çevrilemedi. XLSX çıktı oluşturulabilir; PDF için Microsoft Excel'in "
            f"bu oturumda çalışabilir olması gerekir. Hata: {exc}"
        ) from exc
    finally:
        if workbook is not None:
            workbook.Close(False)
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def taahhutname_dosya_adi(veri, tur, ext=".xlsx"):
    ctx = taahhutname_context(veri, tur)
    role = "Jeofizik" if ctx["tur"] == "jeofizik" else "Jeoloji"
    owner = _safe_name(ctx["yapi_sahibi"], "Proje")
    ext = ext if str(ext).startswith(".") else f".{ext}"
    return f"{owner}_Taahhutname_{role}{ext}"


def taahhutname_olustur(veri, tur, path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".xlsx", ".pdf"):
        path = f"{path}.xlsx"
        ext = ".xlsx"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb = _build_workbook(veri, tur)
    if ext == ".xlsx":
        wb.save(path)
        return path

    with tempfile.TemporaryDirectory(prefix="raporpro_taahhut_") as tmp_dir:
        xlsx_path = os.path.join(tmp_dir, taahhutname_dosya_adi(veri, tur, ".xlsx"))
        wb.save(xlsx_path)
        _export_xlsx_to_pdf(xlsx_path, path)
    return path


def tum_taahhutnameleri_olustur(veri, folder, ext=".xlsx"):
    os.makedirs(folder, exist_ok=True)
    paths = []
    for tur in ("jeoloji", "jeofizik"):
        path = os.path.join(folder, taahhutname_dosya_adi(veri, tur, ext))
        paths.append(taahhutname_olustur(veri, tur, path))
    return paths
