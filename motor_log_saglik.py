# Dosya: RaporPro/motor_log_saglik.py
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path


EXPECTED_SIGNATURES = {
    "log_ornek_derinligi_formatla": "(value)",
    "ciz_profesyonel_log": "(sondaj, proje_dict, log_callback=None)",
    "_ciz_strater_stil_log": "(sondaj, proje_dict, log_callback=None)",
    "_ciz_profesyonel_log_eski": "(sondaj, proje_dict, log_callback=None)",
}


def _load_motor_log_module(base_dir):
    module_path = Path(base_dir) / "motor_log.py"
    spec = importlib.util.spec_from_file_location("_raporpro_motor_log_health", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"motor_log.py yuklenemedi: {module_path}")
    module = importlib.util.module_from_spec(spec)
    root = str(Path(base_dir).resolve())
    added_path = False
    if root not in sys.path:
        sys.path.insert(0, root)
        added_path = True
    try:
        spec.loader.exec_module(module)
    finally:
        if added_path:
            try:
                sys.path.remove(root)
            except ValueError:
                pass
    return module


def check_motor_log_bridge(base_dir=None):
    """motor_log.py kaynak motorunun calisir ve beklenen imzada oldugunu denetle."""
    root = Path(base_dir or Path(__file__).resolve().parent)
    problems = []

    motor_log_path = root / "motor_log.py"

    if not motor_log_path.exists():
        problems.append(f"motor_log.py bulunamadi: {motor_log_path}")
    if problems:
        return problems

    try:
        module = _load_motor_log_module(root)
    except Exception as exc:
        return [f"motor_log kaynak motoru yuklenemedi: {exc}"]

    func = getattr(module, "log_ornek_derinligi_formatla", None)
    if not callable(func):
        problems.append("log_ornek_derinligi_formatla fonksiyonu yok veya cagrilabilir degil.")
    elif str(inspect.signature(func)) != EXPECTED_SIGNATURES["log_ornek_derinligi_formatla"]:
        problems.append(f"log_ornek_derinligi_formatla imzasi beklenenden farkli: {inspect.signature(func)}")

    mixin = getattr(module, "GeoEngineLogMixin", None)
    if mixin is None:
        problems.append("GeoEngineLogMixin sinifi bulunamadi.")
        return problems

    for method_name in ("ciz_profesyonel_log", "_ciz_strater_stil_log", "_ciz_profesyonel_log_eski"):
        method = getattr(mixin, method_name, None)
        if not callable(method):
            problems.append(f"{method_name} metodu yok veya cagrilabilir degil.")
            continue
        signature = str(inspect.signature(method))
        if signature != EXPECTED_SIGNATURES[method_name]:
            problems.append(f"{method_name} imzasi beklenenden farkli: {signature}")

    return problems


def motor_log_bridge_ok(base_dir=None):
    return not check_motor_log_bridge(base_dir)
