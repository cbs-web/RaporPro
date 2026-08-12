# Dosya: RaporPro/benchmarks/benchmark_performans.py
"""RaporPro icin tekrarlanabilir, agsiz performans kiyaslamalari.

Kullanim:
    python benchmarks/benchmark_performans.py
    python benchmarks/benchmark_performans.py --output benchmarks/results/baseline.json
    python benchmarks/benchmark_performans.py --case litoloji_korelasyonu --profile litoloji_korelasyonu
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import json
import math
import os
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_VERSION = 1
DEFAULT_REPEATS = 5
DEFAULT_WARMUPS = 1


def _percentile(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _git_value(*args):
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _sondaj(idx, depth=30.0):
    from workbook_motoru import yeni_sondaj_sablonu

    item = yeni_sondaj_sablonu(idx)
    item.update(
        {
            "der": f"{depth:g}",
            "k": f"{110.0 - idx * 0.15:.2f}",
            "x": f"26.{360000 + idx:06d}",
            "y": f"40.{890000 + idx:06d}",
            "litoloji": [
                ["0.00", "1.50", "BITKISEL TOPRAK"],
                ["1.50", f"{depth:g}", "KAHVE RENKLI, KILLI KUM"],
            ],
            "spt": [
                [f"{d:.2f}", "4", str(5 + (idx + int(d)) % 8), "6", str(11 + (idx + int(d)) % 8)]
                for d in (1.5 + 1.5 * step for step in range(int(depth / 1.5)))
                if d < depth
            ],
            "pmt": [["6.00", "120", "8"]] if idx % 4 == 0 else [],
        }
    )
    return item


def _litoloji_verisi(well_count=18, source_well_count=6, depth=30.0):
    codes = ("saClL", "saClM", "clSa", "siSa", "grsiSaP")
    rows = [["Sondaj No", "Numune", "Derinlik (m)", "SINIFLAMA Classification", "PI"]]
    wells = []
    interval_count = int(depth / 1.5)
    for idx in range(well_count):
        well = _sondaj(idx, depth)
        profile = []
        for cell in range(int(depth / 0.5)):
            top = cell * 0.5
            tone = 92 + ((idx * 11 + cell * 3) % 35)
            profile.append(
                {
                    "top": top,
                    "bottom": min(depth, top + 0.5),
                    "rgb": (tone + 22, tone + 8, tone),
                    "hex": f"#{tone + 22:02x}{tone + 8:02x}{tone:02x}",
                }
            )
        well["litoloji_renk_profili"] = profile
        wells.append(well)
        if idx >= source_well_count:
            continue
        for sample in range(interval_count):
            top = sample * 1.5
            bottom = min(depth, top + 1.5)
            rows.append(
                [
                    well["no"],
                    f"UD-{sample + 1}",
                    f"{top:.2f}-{bottom:.2f}",
                    codes[(idx + sample) % len(codes)],
                    str(8 + (idx + sample) % 18),
                ]
            )
    return {"sondaj": wells, "lab_sheet": {"rows": rows}}


def _rapor_verisi():
    from proje_sema import varsayilan_proje_verisi

    data = varsayilan_proje_verisi()
    data["kunye"].update(
        {
            "sahibi": "PERFORMANS KIYAS PROJESI",
            "il": "CANAKKALE",
            "ilce": "MERKEZ",
            "mah": "TEST MAHALLESI",
            "ada": "100",
            "par": "10",
        }
    )
    data["bina"].update({"kul": "Konut", "kat": "5", "ysinif": "ZD", "der": "2.5"})
    data["arazi"].update(
        {
            "kategori": "1",
            "zemin": "ZD",
            "pga": "0.35",
            "alan_y": "40.89",
            "alan_x": "26.36",
        }
    )
    data["sondaj"] = [_sondaj(idx, 30.0) for idx in range(8)]
    return data


class BenchmarkCases:
    def __init__(self, temp_dir):
        self.temp_dir = Path(temp_dir)
        self._litoloji_data = _litoloji_verisi()
        self._report_data = _rapor_verisi()
        self._report_output = self.temp_dir / "benchmark_rapor.docx"
        self._template = ROOT / "sablonlar" / "rapor" / "varsayilan_rapor_sablonu.docx"
        self._spt_path = self.temp_dir / "benchmark_spt.xlsx"
        self._make_spt_workbook(self._spt_path, row_count=5000)

    @staticmethod
    def _make_spt_workbook(path, row_count):
        from openpyxl import Workbook

        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("SPT")
        sheet.append(["Sondaj No", "Derinlik", "15", "30", "45", "N30"])
        for idx in range(row_count):
            well = f"SK-{idx % 25 + 1}"
            depth = 1.5 + 1.5 * (idx % 20)
            v15 = 3 + idx % 7
            v30 = 4 + idx % 9
            v45 = 5 + idx % 11
            sheet.append([well, depth, v15, v30, v45, v30 + v45])
        workbook.save(path)

    def startup_import(self):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONHASHSEED"] = "0"
        completed = subprocess.run(
            [sys.executable, "-c", "import arayuz"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace")[-1000:])
        return True

    def dependency_preflight(self):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONHASHSEED"] = "0"
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from ortam_kontrolu import check_dependencies; "
                    "required, _optional = check_dependencies(); "
                    "assert not required, required"
                ),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace")[-1000:])
        return True

    def litoloji_korelasyonu(self):
        from litoloji_korelasyon import coklu_sondaj_onerileri_olustur

        return coklu_sondaj_onerileri_olustur(self._litoloji_data, adim=0.5)

    def spt_excel_okuma(self):
        from spt_okuma_motoru import excelden_spt_oku

        return excelden_spt_oku(self._spt_path, default_sondaj_no="SK-1")

    def proje_saglik_ozeti(self):
        from proje_motoru import hesap_ozeti, proje_saglik_ozeti

        return proje_saglik_ozeti(self._report_data), hesap_ozeti(self._report_data)

    def rapor_uretimi(self):
        from raporlama import raporla

        app = SimpleNamespace(
            veri=self._report_data,
            word_path=str(self._template),
            lab_excel_path=None,
            jeo_excel_path=None,
            img_yer=None,
            img_tkgm=None,
            img_pga=None,
            img_mjh=None,
            word_img_sondaj=None,
            word_img_jeofizik=None,
            set_status=lambda *_args, **_kwargs: None,
        )
        success, message = raporla(app, final_path=str(self._report_output), autosave=False)
        return success, message, self._report_output.stat().st_size if self._report_output.exists() else 0

    @staticmethod
    def validate(name, value):
        if name in {"startup_import", "dependency_preflight"}:
            return value is True
        if name == "litoloji_korelasyonu":
            return len(value.get("sondajlar", [])) == 18 and sum(
                len(item.get("hucreler", [])) for item in value["sondajlar"]
            ) == 1080
        if name == "spt_excel_okuma":
            return len(value.kayitlar) == 5000
        if name == "proje_saglik_ozeti":
            return isinstance(value[0], dict) and isinstance(value[1], dict)
        if name == "rapor_uretimi":
            return bool(value[0]) and value[2] > 0
        return False


CASE_DEFAULTS = {
    "startup_import": {"repeats": 5, "warmups": 1, "memory": False},
    "dependency_preflight": {"repeats": 5, "warmups": 1, "memory": False},
    "litoloji_korelasyonu": {"repeats": 5, "warmups": 1, "memory": True},
    "spt_excel_okuma": {"repeats": 5, "warmups": 1, "memory": True},
    "proje_saglik_ozeti": {"repeats": 20, "warmups": 2, "memory": True},
    "rapor_uretimi": {"repeats": 3, "warmups": 1, "memory": True},
}


def _measure_case(cases, name, repeat_override=None):
    options = CASE_DEFAULTS[name]
    repeats = int(repeat_override or options["repeats"])
    warmups = int(options["warmups"])
    function = getattr(cases, name)

    for _ in range(warmups):
        value = function()
        if not cases.validate(name, value):
            raise AssertionError(f"{name}: isinma dogrulamasi basarisiz.")

    samples_ms = []
    for _ in range(repeats):
        gc.collect()
        started = time.perf_counter_ns()
        value = function()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        if not cases.validate(name, value):
            raise AssertionError(f"{name}: sonuc dogrulamasi basarisiz.")
        samples_ms.append(elapsed_ms)
        del value

    peak_kib = None
    if options["memory"]:
        gc.collect()
        tracemalloc.start()
        value = function()
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if not cases.validate(name, value):
            raise AssertionError(f"{name}: bellek olcumu dogrulamasi basarisiz.")
        peak_kib = peak_bytes / 1024

    return {
        "samples_ms": [round(value, 3) for value in samples_ms],
        "median_ms": round(statistics.median(samples_ms), 3),
        "min_ms": round(min(samples_ms), 3),
        "p95_ms": round(_percentile(samples_ms, 0.95), 3),
        "peak_kib": round(peak_kib, 1) if peak_kib is not None else None,
        "repeats": repeats,
        "warmups": warmups,
    }


def _profile_case(cases, name, output=None):
    profiler = cProfile.Profile()
    profiler.enable()
    value = getattr(cases, name)()
    profiler.disable()
    if not cases.validate(name, value):
        raise AssertionError(f"{name}: profil dogrulamasi basarisiz.")
    if output:
        profiler.dump_stats(output)
    stats = pstats.Stats(profiler, stream=sys.stderr).strip_dirs().sort_stats("cumulative")
    stats.print_stats(35)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=tuple(CASE_DEFAULTS), help="Yalniz secili testi calistir.")
    parser.add_argument("--repeat", type=int, help="Tum secili testler icin tekrar sayisini degistir.")
    parser.add_argument("--output", help="JSON sonuc dosyasi.")
    parser.add_argument("--profile", choices=tuple(CASE_DEFAULTS), help="Secili testi bir kez cProfile ile calistir.")
    parser.add_argument("--profile-output", help="cProfile .prof dosyasi.")
    args = parser.parse_args(argv)

    import performans

    selected = args.case or list(CASE_DEFAULTS)
    with tempfile.TemporaryDirectory(prefix="raporpro_benchmark_") as temp_dir:
        performans.PERF_LOG_PATH = str(Path(temp_dir) / "performance.log")
        performans.ERROR_LOG_PATH = str(Path(temp_dir) / "error.log")
        cases = BenchmarkCases(temp_dir)
        results = {}
        for name in selected:
            print(f"Olculuyor: {name}", file=sys.stderr, flush=True)
            results[name] = _measure_case(cases, name, args.repeat)
        if args.profile:
            _profile_case(cases, args.profile, args.profile_output)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "standards": {
            "statistic": "steady-state median; p95 is nearest-rank",
            "network": "disabled/not used",
            "correctness": "every sample validates deterministic output invariants",
            "acceptance": "target case median improves >=10%; unrelated medians regress <=5%",
        },
        "results": results,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
