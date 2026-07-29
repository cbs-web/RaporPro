import importlib.util
import sys

from motor_log_saglik import check_motor_log_bridge


REQUIRED_DEPENDENCIES = [
    ("matplotlib", "matplotlib", "Grafik ve kesit çizimleri"),
    ("numpy", "numpy", "Hesap ve çizim motoru"),
    ("pandas", "pandas", "Excel/veri okuma"),
    ("docx", "python-docx", "Word raporu üretimi"),
    ("PIL", "Pillow", "Görsel işleme"),
    ("fitz", "PyMuPDF", "Ekler PDF üretimi"),
    ("openpyxl", "openpyxl", "XLSX okuma, yazma ve taahhütname üretimi"),
    ("tkintermapview", "tkintermapview", "Harita ekranları"),
]

OPTIONAL_DEPENDENCIES = [
    ("tksheet", "tksheet", "Excel benzeri workbook ekranı"),
    ("xlrd", "xlrd", "Eski XLS dosyalarını okuma"),
    ("scipy", "scipy", "Gelişmiş hesap modülleri"),
    ("tkinterdnd2", "tkinterdnd2", "SPT fotoğraf kuyruğuna sürükle-bırak dosya ekleme"),
    ("win32com", "pywin32", "Word ve Excel tabanlı PDF önizleme/aktarım"),
    ("requests", "requests", "TKGM ve dış yapay zekâ servisleri"),
    ("easyocr", "easyocr", "İmar ve zemin durum belgesi OCR ile veri aktarımı"),
]


OPTIONAL_DEPENDENCIES.append(("ttkbootstrap", "ttkbootstrap", "Modern ve duz arayuz temasi"))


def _is_available(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _missing_from(dependencies):
    missing = []
    for module_name, package_name, purpose in dependencies:
        if not _is_available(module_name):
            missing.append({
                "module": module_name,
                "package": package_name,
                "purpose": purpose,
            })
    return missing


def check_dependencies():
    required_missing = _missing_from(REQUIRED_DEPENDENCIES)
    optional_missing = _missing_from(OPTIONAL_DEPENDENCIES)
    if not required_missing:
        motor_log_problems = check_motor_log_bridge()
        for problem in motor_log_problems:
            required_missing.append({
                "module": "motor_log",
                "package": "motor_log.py",
                "purpose": f"Sondaj logu cizim motoru - {problem}",
            })
    return required_missing, optional_missing


def install_command(python_executable=None):
    exe = python_executable or sys.executable
    return f'"{exe}" -m pip install -r requirements.txt'


def format_dependency_message(required_missing, optional_missing=None, python_executable=None):
    optional_missing = optional_missing or []
    lines = [
        "Python ortamında eksik paketler bulundu.",
        "",
        f"Python: {python_executable or sys.executable}",
        "",
    ]
    if required_missing:
        lines.append("Zorunlu paketler:")
        for item in required_missing:
            lines.append(f"- {item['package']} ({item['purpose']})")
        lines.append("")
    if optional_missing:
        lines.append("Özellik bazlı paketler:")
        for item in optional_missing:
            lines.append(f"- {item['package']} ({item['purpose']})")
        lines.append("")
    lines.extend([
        "Çözüm:",
        "RaporPro_Baslat.bat ile açın veya şu komutu çalıştırın:",
        install_command(python_executable),
    ])
    return "\n".join(lines)


def print_cli_dependency_report():
    required_missing, optional_missing = check_dependencies()
    if not required_missing and not optional_missing:
        print("Paket kontrolu tamam: eksik paket yok.")
        return 0
    print(format_dependency_message(required_missing, optional_missing))
    return 1
