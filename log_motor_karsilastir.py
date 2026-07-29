# Dosya: RaporPro/log_motor_karsilastir.py
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

from motor_log_kaynak import GeoEngineLogMixin as CandidateLog


def _load_cached_log_engine(cache_path):
    cache_path = Path(cache_path)
    if not cache_path.is_file():
        raise FileNotFoundError(f"Log motoru karsilastirma tabani bulunamadi: {cache_path}")
    spec = importlib.util.spec_from_file_location("_raporpro_cached_motor_for_log_compare", cache_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Motor log onbellegi yuklenemedi: {cache_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GeoEngine


def _spt_rows(depths):
    rows = []
    for idx, depth in enumerate(depths, start=1):
        n15 = idx + 1
        n30 = idx + 2
        n45 = idx + 3
        rows.append([f"{depth:.2f}", str(n15), str(n30), str(n45), str(n30 + n45)])
    return rows


def build_scenarios():
    base_project = {
        "kunye": {
            "sahibi": "Deneme Proje",
            "il": "Canakkale",
            "ilce": "Merkez",
            "mah": "Arslanca",
            "ada": "1109",
            "par": "1",
        },
        "ayarlar": {
            "firma_adi": "UB ZEMIN MUHENDISLIK",
            "log_baslik": "SONDAJ LOGU",
            "sorumlu_muhendis": "GOKALP DOGAN",
            "sorumlu_muhendis_unvan": "Sorumlu Jeoloji Muhendisi",
            "sondor_belge": "Murat Ercelik 3629",
            "delgi_capi": "89mm",
        },
    }
    return [
        {
            "name": "zemin_spt",
            "project": base_project,
            "sondaj": {
                "no": "SK-1",
                "der": "7.50",
                "k": "12.30",
                "bas_tar": "01.01.2026",
                "bit_tar": "02.01.2026",
                "x": "26.447050",
                "y": "40.148435",
                "litoloji": [["0", "0.5", "Bitkisel Toprak"], ["0.5", "7.5", "Killi Kum"]],
                "spt": _spt_rows([1.5, 3.0, 4.5, 6.0, 7.5]),
                "pmt": [],
                "kaya": [],
                "numuneler": [],
            },
        },
        {
            "name": "spt_pmt_ayni_derinlik",
            "project": base_project,
            "sondaj": {
                "no": "SK-2",
                "der": "12.00",
                "k": "14.10",
                "bas_tar": "03.01.2026",
                "bit_tar": "04.01.2026",
                "x": "26.447249",
                "y": "40.148521",
                "yass_d1": "3.00",
                "yass_t1": "04.01.2026",
                "litoloji": [["0", "0.5", "Bitkisel Toprak"], ["0.5", "6.0", "Kumlu Kil"], ["6.0", "12.0", "Cakilli Kum"]],
                "spt": _spt_rows([1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0]),
                "pmt": [["3.00", "120", "8.5"], ["7.50", "180", "11.0"]],
                "kaya": [],
                "numuneler": [],
            },
        },
        {
            "name": "kaya_karot",
            "project": base_project,
            "sondaj": {
                "no": "SK-3",
                "der": "18.00",
                "k": "16.20",
                "bas_tar": "05.01.2026",
                "bit_tar": "06.01.2026",
                "x": "26.447434",
                "y": "40.148480",
                "litoloji": [["0", "2.0", "Killi Kum"], ["2.0", "10.5", "Siltli Kil"], ["10.5", "18.0", "Kireçtasi"]],
                "spt": _spt_rows([1.5, 3.0, 4.5, 6.0, 7.5, 9.0]),
                "pmt": [["6.00", "150", "10.0"]],
                "kaya": [["10.50-12.00", "92", "81", "63", "Orta"], ["12.00-13.50", "88", "70", "55", "Orta"], ["13.50-15.00", "75", "62", "48", "Zayif"]],
                "numuneler": [["10.50-12.00", "KR-1"], ["12.00-13.50", "KR-2"], ["13.50-15.00", "KR-3"]],
            },
        },
        {
            "name": "cok_sayfali",
            "project": base_project,
            "sondaj": {
                "no": "SK-4",
                "der": "31.50",
                "k": "18.60",
                "bas_tar": "07.01.2026",
                "bit_tar": "09.01.2026",
                "x": "26.447809",
                "y": "40.148467",
                "litoloji": [
                    ["0", "0.5", "Bitkisel Toprak"],
                    ["0.5", "6.0", "Killi Kum"],
                    ["6.0", "15.0", "Siltli Kil"],
                    ["15.0", "22.5", "Cakilli Kum"],
                    ["22.5", "31.5", "Kaya"],
                ],
                "spt": _spt_rows([1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0, 16.5, 18.0, 19.5, 21.0, 22.5, 24.0, 25.5, 27.0, 28.5, 30.0]),
                "pmt": [["9.00", "170", "10.0"], ["18.00", "210", "14.0"]],
                "kaya": [["22.50-24.00", "85", "72", "58", "Orta"], ["24.00-25.50", "78", "61", "42", "Zayif"], ["25.50-27.00", "91", "82", "66", "Iyi"]],
                "numuneler": [["22.50-24.00", "KR-1"], ["24.00-25.50", "KR-2"], ["25.50-27.00", "KR-3"]],
            },
        },
    ]


def _figure_text_counter(fig):
    texts = []
    for ax in fig.axes:
        texts.extend(t.get_text() for t in ax.texts if t.get_text())
    return Counter(texts)


def _save_figures(figures, output_dir, scenario_name, engine_name):
    paths = []
    for idx, fig in enumerate(figures, start=1):
        path = output_dir / f"{scenario_name}_{engine_name}_sayfa_{idx:02d}.png"
        fig.savefig(path, dpi=120, facecolor="white")
        paths.append(path)
        plt.close(fig)
    return paths


def _image_metrics(current_path, candidate_path, diff_path):
    with Image.open(current_path) as img_current, Image.open(candidate_path) as img_candidate:
        current = img_current.convert("RGB")
        candidate = img_candidate.convert("RGB")
        same_size = current.size == candidate.size
        if not same_size:
            max_width = max(current.width, candidate.width)
            max_height = max(current.height, candidate.height)
            canvas_current = Image.new("RGB", (max_width, max_height), "white")
            canvas_candidate = Image.new("RGB", (max_width, max_height), "white")
            canvas_current.paste(current, (0, 0))
            canvas_candidate.paste(candidate, (0, 0))
            current = canvas_current
            candidate = canvas_candidate

        arr_current = np.asarray(current, dtype=np.int16)
        arr_candidate = np.asarray(candidate, dtype=np.int16)
        diff = np.abs(arr_current - arr_candidate)
        changed = np.any(diff > 8, axis=2)
        changed_pixels = int(changed.sum())
        total_pixels = int(changed.size)
        diff_boost = np.clip(diff * 4, 0, 255).astype(np.uint8)
        Image.fromarray(diff_boost).save(diff_path)
        return {
            "same_size": same_size,
            "size": list(current.size),
            "mean_abs_diff": round(float(diff.mean()), 4),
            "max_abs_diff": int(diff.max()),
            "changed_pixels": changed_pixels,
            "changed_percent": round(changed_pixels / total_pixels * 100.0, 4) if total_pixels else 0.0,
        }


def _make_contact_sheet(page_results, output_dir, scenario_name):
    if not page_results:
        return None
    rows = []
    label_height = 28
    thumb_width = 420
    for page in page_results:
        images = []
        for key, label in (("pyc", "PYC"), ("aday", "ADAY"), ("diff", "FARK")):
            with Image.open(output_dir / page[key]) as img:
                rgb = img.convert("RGB")
                scale = thumb_width / rgb.width
                thumb_height = max(1, int(rgb.height * scale))
                thumb = rgb.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (thumb_width, thumb_height + label_height), "white")
            draw = ImageDraw.Draw(tile)
            draw.text((8, 7), f"{label} - sayfa {page['page']}", fill="black")
            tile.paste(thumb, (0, label_height))
            images.append(tile)
        row_width = sum(img.width for img in images)
        row_height = max(img.height for img in images)
        row = Image.new("RGB", (row_width, row_height), "white")
        x = 0
        for img in images:
            row.paste(img, (x, 0))
            x += img.width
        rows.append(row)

    sheet_width = max(row.width for row in rows)
    sheet_height = sum(row.height for row in rows)
    sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    path = output_dir / f"{scenario_name}_kontakt.png"
    sheet.save(path)
    return path


def compare_scenario(scenario, output_dir, baseline_log):
    warnings_current = []
    warnings_candidate = []
    current_figs = baseline_log.ciz_profesyonel_log(
        scenario["sondaj"],
        scenario["project"],
        log_callback=lambda message, level="info": warnings_current.append({"level": level, "message": message}),
    )
    candidate_figs = CandidateLog.ciz_profesyonel_log(
        scenario["sondaj"],
        scenario["project"],
        log_callback=lambda message, level="info": warnings_candidate.append({"level": level, "message": message}),
    )
    current_texts = Counter()
    candidate_texts = Counter()
    for fig in current_figs:
        current_texts.update(_figure_text_counter(fig))
    for fig in candidate_figs:
        candidate_texts.update(_figure_text_counter(fig))

    current_paths = _save_figures(current_figs, output_dir, scenario["name"], "pyc")
    candidate_paths = _save_figures(candidate_figs, output_dir, scenario["name"], "aday")

    page_results = []
    for idx, (current_path, candidate_path) in enumerate(zip(current_paths, candidate_paths), start=1):
        diff_path = output_dir / f"{scenario['name']}_diff_sayfa_{idx:02d}.png"
        metrics = _image_metrics(current_path, candidate_path, diff_path)
        page_results.append({
            "page": idx,
            "pyc": current_path.name,
            "aday": candidate_path.name,
            "diff": diff_path.name,
            **metrics,
        })
    contact_sheet = _make_contact_sheet(page_results, output_dir, scenario["name"])

    return {
        "scenario": scenario["name"],
        "pyc_pages": len(current_paths),
        "aday_pages": len(candidate_paths),
        "text_missing": list((current_texts - candidate_texts).elements())[:80],
        "text_extra": list((candidate_texts - current_texts).elements())[:80],
        "warnings_pyc": warnings_current,
        "warnings_aday": warnings_candidate,
        "contact_sheet": contact_sheet.name if contact_sheet else None,
        "pages": page_results,
    }


def write_text_summary(results, output_dir):
    lines = ["Log motoru karsilastirma ozeti", ""]
    for result in results:
        lines.append(f"[{result['scenario']}] pyc={result['pyc_pages']} aday={result['aday_pages']}")
        lines.append(f"  text_missing={len(result['text_missing'])} text_extra={len(result['text_extra'])}")
        for page in result["pages"]:
            lines.append(
                "  page {page}: changed={changed_percent:.4f}% mean={mean_abs_diff:.4f} max={max_abs_diff} diff={diff}".format(**page)
            )
        if result.get("contact_sheet"):
            lines.append(f"  contact={result['contact_sheet']}")
        if result["warnings_pyc"] or result["warnings_aday"]:
            lines.append(f"  warnings_pyc={result['warnings_pyc']}")
            lines.append(f"  warnings_aday={result['warnings_aday']}")
        lines.append("")
    (output_dir / "ozet.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Arsivlenmis bir log motoru ile kaynak log motorunu karsilastirir."
    )
    parser.add_argument(
        "--baseline-pyc",
        required=True,
        help="Kullanici tarafindan saklanan CPython 3.11 PYC karsilastirma tabani.",
    )
    parser.add_argument("--output", default=None, help="Cikti klasoru. Varsayilan: _log_analiz/log_motor_karsilastirma/<timestamp>")
    args = parser.parse_args()
    baseline_log = _load_cached_log_engine(args.baseline_pyc)

    if args.output:
        output_dir = Path(args.output)
    else:
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("_log_analiz") / "log_motor_karsilastirma" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [
        compare_scenario(scenario, output_dir, baseline_log)
        for scenario in build_scenarios()
    ]
    (output_dir / "ozet.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_text_summary(results, output_dir)
    print(output_dir)
    print((output_dir / "ozet.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
