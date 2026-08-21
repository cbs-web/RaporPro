"""UI'dan bağımsız laboratuvar başlık ve kolon çözümleme yardımcıları."""

import re
import unicodedata


def _lab_metin(value):
    return "" if value is None else str(value).strip()


def _lab_anahtar(value):
    text = _lab_metin(value).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text)


def _lab_sayi(value):
    text = _lab_metin(value).replace(" ", "").replace(",", ".")
    if not text or text in {"-", "—"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def laboratuvar_baslik_bilgisi(rows):
    """Çok satırlı LAB başlığını ve gerekli litoloji sütunlarını belirle."""
    clean_rows = [
        ["" if cell is None else str(cell).strip() for cell in row]
        for row in (rows or [])
        if isinstance(row, (list, tuple))
    ]
    if not clean_rows:
        return {
            "rows": [],
            "header_row": 0,
            "data_start": 0,
            "signatures": [],
            "keys": [],
            "columns": {},
        }

    max_cols = max((len(row) for row in clean_rows), default=0)
    for row in clean_rows:
        row.extend([""] * (max_cols - len(row)))

    header_row = 0
    for row_index, row in enumerate(clean_rows[:35]):
        if any(
            "sondajno" in _lab_anahtar(cell)
            or "kuyuno" in _lab_anahtar(cell)
            or "boringno" in _lab_anahtar(cell)
            for cell in row
        ):
            header_row = row_index
            break

    data_start = len(clean_rows)
    for row_index in range(header_row + 1, len(clean_rows)):
        row = clean_rows[row_index]
        first = _lab_metin(row[0] if row else "")
        depth = _lab_sayi(row[2] if len(row) > 2 else "")
        numeric_count = sum(_lab_sayi(cell) is not None for cell in row)
        if first and depth is not None and numeric_count >= 2:
            data_start = row_index
            break
    if data_start == len(clean_rows):
        data_start = min(len(clean_rows), header_row + 5)

    header_rows = [list(row) for row in clean_rows[header_row:data_start]]
    if header_rows:
        current = ""
        for column_index, value in enumerate(header_rows[0]):
            if _lab_metin(value):
                current = _lab_metin(value)
            elif current:
                header_rows[0][column_index] = current

    signatures = []
    keys = []
    for column_index in range(max_cols):
        parts = []
        for row in header_rows:
            value = _lab_metin(row[column_index] if column_index < len(row) else "")
            if value and value not in parts:
                parts.append(value)
        signature = " / ".join(parts)
        signatures.append(signature)
        keys.append(_lab_anahtar(signature))

    columns = {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": None}
    for index, key in enumerate(keys):
        if "sondajno" in key or "kuyuno" in key or "boringno" in key:
            columns["sondaj"] = index
        elif "numuneno" in key or "sampleno" in key:
            columns["numune"] = index
        elif "derinlik" in key or "depth" in key:
            columns["derinlik"] = index
        elif "siniflama" in key or "classification" in key or "uscs" in key:
            columns["sinif"] = index

    return {
        "rows": clean_rows,
        "header_row": header_row,
        "data_start": data_start,
        "signatures": signatures,
        "keys": keys,
        "columns": columns,
    }
