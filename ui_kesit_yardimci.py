# Dosya: RaporPro/ui_kesit_yardimci.py
import math
import re
from pathlib import Path

from yardimcilar import safe_float

def _temiz_dosya_adi(text):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r'[<>:"/\\|?*]+', "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Kesit"


def _sondaj_adi_token(no):
    text = re.sub(r"\s+", "", str(no or "").strip())
    match = re.match(r"^([A-Za-zÇĞİÖŞÜçğıöşü]+)[-_]?0*(\d+)$", text)
    if match:
        return f"{match.group(1).upper()}{int(match.group(2))}", match.group(1).upper(), int(match.group(2))
    return _temiz_dosya_adi(text), None, None


def kesit_kayit_dosya_adi(sondajlar):
    names = []
    for item in sondajlar or []:
        if isinstance(item, dict):
            name = item.get("no") or item.get("ad") or ""
        else:
            name = item
        if str(name or "").strip():
            names.append(name)
    if not names:
        return "Kesit"

    parsed = [_sondaj_adi_token(name) for name in names]
    prefixes = {prefix for _, prefix, number in parsed if prefix is not None and number is not None}
    if len(prefixes) == 1 and all(prefix is not None and number is not None for _, prefix, number in parsed):
        prefix = parsed[0][1]
        numbers = [number for _, _, number in parsed]
        unique_numbers = sorted(set(numbers))
        if len(unique_numbers) == len(numbers) and unique_numbers == list(range(unique_numbers[0], unique_numbers[-1] + 1)):
            return _temiz_dosya_adi(f"Kesit {prefix}{unique_numbers[0]}-{unique_numbers[-1]}")
        return _temiz_dosya_adi("Kesit " + "-".join(f"{prefix}{number}" for number in numbers))

    return _temiz_dosya_adi("Kesit " + "-".join(token for token, _, _ in parsed))


def benzersiz_kesit_cikti_yolu(folder, base_name, extension):
    """Kesit çıktısı ve çok sayfalı parçalarıyla çakışmayan dosya yolu üret."""

    output_dir = Path(folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = str(extension or ".jpg").strip()
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    safe_name = _temiz_dosya_adi(base_name)

    def occupied(candidate):
        if candidate.exists():
            return True
        page_prefix = f"{candidate.stem}_Sayfa"
        return any(
            child.is_file()
            and child.suffix.casefold() == candidate.suffix.casefold()
            and child.stem.startswith(page_prefix)
            for child in output_dir.iterdir()
        )

    candidate = output_dir / f"{safe_name}{suffix}"
    counter = 2
    while occupied(candidate):
        candidate = output_dir / f"{safe_name} ({counter}){suffix}"
        counter += 1
    return str(candidate)


def kesit_hatti_sondaj_sirasi(sondajlar, start, end, max_offset=10.0):
    start_y, start_x = safe_float(start[0]), safe_float(start[1])
    end_y, end_x = safe_float(end[0]), safe_float(end[1])
    if not start_y or not start_x or not end_y or not end_x:
        raise ValueError("Kesit hattı başlangıç/bitiş koordinatları geçersiz.")

    lat0_rad = math.radians(start_y)
    meters_per_lat = 111320.0
    meters_per_lon = 111320.0 * math.cos(lat0_rad)

    def to_local(y, x):
        return (x - start_x) * meters_per_lon, (y - start_y) * meters_per_lat

    end_lx, end_ly = to_local(end_y, end_x)
    line_len = math.hypot(end_lx, end_ly)
    if line_len <= 0.01:
        raise ValueError("Kesit hattı başlangıç ve bitiş noktaları aynı olamaz.")
    ux, uy = end_lx / line_len, end_ly / line_len
    tolerance = safe_float(max_offset)

    results = []
    for idx, sondaj in enumerate(sondajlar or []):
        y, x = safe_float(sondaj.get("y")), safe_float(sondaj.get("x"))
        if not y or not x:
            continue
        px, py = to_local(y, x)
        station = px * ux + py * uy
        offset = px * (-uy) + py * ux
        if tolerance > 0:
            if abs(offset) > tolerance:
                continue
            if station < -tolerance or station > line_len + tolerance:
                continue
        results.append({
            "index": idx,
            "no": sondaj.get("no", f"SK-{idx + 1}"),
            "station": station,
            "offset": offset,
        })
    return sorted(results, key=lambda item: (item["station"], item["no"]))

