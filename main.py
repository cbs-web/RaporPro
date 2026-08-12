import sys
from performans import install_exception_logging, log_exception, perf_timer
from ortam_kontrolu import (
    check_dependencies,
    check_runtime_assets,
    format_dependency_message,
    format_runtime_asset_message,
    install_command,
)

install_exception_logging()

required_missing = []
optional_missing = []
runtime_asset_problems = []


def show_windows_message(title, text, icon=16):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, icon)
    except Exception:
        print(title)
        print(text)


with perf_timer("startup.dependency_check"):
    required_missing, optional_missing = check_dependencies()

with perf_timer("startup.asset_check"):
    runtime_asset_problems = check_runtime_assets()

if required_missing:
    message = format_dependency_message(required_missing, optional_missing, sys.executable)
    log_exception("startup.dependency_missing", exc_value=ImportError(message))
    show_windows_message("RaporPro - Başlatma Kontrolü", message)
    sys.exit(1)

# Hata yakalama bloğu ile güvenli import
try:
    # Sınıf ismi RaporRobotuArayuz olarak güncellendi
    with perf_timer("startup.import_arayuz"):
        from arayuz import RaporRobotuArayuz
except ImportError as e:
    log_exception("startup.import_error", exc_value=e)
    missing = getattr(e, "name", "") or str(e)
    install_cmd = install_command(sys.executable)
    # Eger import basarisiz olursa hangi Python'un sorun cikardigini net goster.
    show_windows_message(
        "RaporPro - Kritik Hata",
        "Başlatma Hatası:\n"
        f"{str(e)}\n\n"
        f"Python: {sys.executable}\n"
        f"Eksik paket/modül: {missing}\n\n"
        "Çözüm:\n"
        "1) RaporPro_Baslat.bat dosyasıyla açın.\n"
        "2) Gerekirse şu komutu çalıştırın:\n"
        f"{install_cmd}",
    )
    sys.exit(1)

if __name__ == "__main__":
    try:
        import tkinter as tk
        from tkinter import messagebox
        with perf_timer("startup.tk_root"):
            try:
                from tkinterdnd2 import TkinterDnD
                root = TkinterDnD.Tk()
            except Exception:
                root = tk.Tk()
        # Uygulamayı doğru sınıf ismiyle başlatıyoruz
        with perf_timer("startup.app_init"):
            app = RaporRobotuArayuz(root)
        if optional_missing or runtime_asset_problems:
            def show_startup_warnings():
                messages = []
                if optional_missing:
                    messages.append(
                        format_dependency_message([], optional_missing, sys.executable)
                    )
                if runtime_asset_problems:
                    messages.append(format_runtime_asset_message(runtime_asset_problems))
                messagebox.showwarning(
                    "RaporPro - Başlatma Kontrolü",
                    "\n\n".join(messages),
                )

            root.after(
                600,
                show_startup_warnings,
            )
        root.mainloop()
    except Exception as e:
        log_exception("main.runtime_error", exc_value=e)
        # Çalışma zamanı hataları için
        show_windows_message("RaporPro - Hata", f"Program Hatası:\n{str(e)}")
