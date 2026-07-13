# Dosya: RaporPro/tutarlilik_laboratuvar.py
from karot_motoru import derinlik_araligi_coz
from tutarlilik_ortak import (
    bos_mu,
    bulgu_ekle,
    derinlik_aralikta_mi,
    kimlik_anahtari,
    litoloji_araliklari,
    sayi_veya_none,
)


def laboratuvar_kayitlarini_ayikla(rows):
    rows = [list(row) for row in rows or [] if isinstance(row, (list, tuple))]
    if not rows:
        return {"records": [], "header_found": False, "header_row": None}

    header_row = None
    well_col = None
    depth_col = None
    max_cols = max((len(row) for row in rows), default=0)
    for row_idx, row in enumerate(rows[:35]):
        normalized = [kimlik_anahtari(cell) for cell in row]
        for col_idx, cell in enumerate(normalized):
            if "sondajno" in cell or "kuyuno" in cell:
                header_row = row_idx
                well_col = col_idx
                break
        if header_row is not None:
            break
    if header_row is None:
        return {"records": [], "header_found": False, "header_row": None}

    header_end = min(len(rows), header_row + 6)
    signatures = []
    for col_idx in range(max_cols):
        signatures.append(
            " ".join(
                kimlik_anahtari(rows[row_idx][col_idx])
                for row_idx in range(header_row, header_end)
                if col_idx < len(rows[row_idx]) and not bos_mu(rows[row_idx][col_idx])
            )
        )
    for col_idx, signature in enumerate(signatures):
        if col_idx == well_col:
            continue
        if "derinlik" in signature or "derinli" in signature or "numuneder" in signature:
            depth_col = col_idx
            break
    if depth_col is None:
        return {"records": [], "header_found": True, "header_row": header_row}

    records = []
    current_well = ""
    for source_row in range(header_row + 1, len(rows)):
        row = rows[source_row]
        if well_col < len(row) and not bos_mu(row[well_col]):
            current_well = str(row[well_col]).strip()
        if not current_well or depth_col >= len(row) or bos_mu(row[depth_col]):
            continue
        top, bottom = derinlik_araligi_coz(row[depth_col])
        if top <= 0 and bottom <= 0:
            raw_depth = sayi_veya_none(row[depth_col])
            if raw_depth is None:
                continue
            top = raw_depth
            bottom = raw_depth
        records.append({
            "sondaj": current_well,
            "top": top,
            "bottom": bottom,
            "row": source_row,
            "raw_depth": str(row[depth_col]).strip(),
        })
    return {"records": records, "header_found": True, "header_row": header_row}


def laboratuvar_kontrol(report, veri, lab_rows):
    if not lab_rows:
        return
    parsed = laboratuvar_kayitlarini_ayikla(lab_rows)
    if not parsed["header_found"]:
        bulgu_ekle(
            report,
            "lab.baslik",
            "warning",
            "Laboratuvar",
            "LAB başlıkları",
            "Laboratuvar verisinde 'Sondaj No' başlığı bulunamadı; derinlik eşleşmesi denetlenemedi.",
            "rapor",
            "LAB Sheet başlıklarını kaynak Excel ile aynı biçimde yapıştırın.",
        )
        return
    if not parsed["records"]:
        bulgu_ekle(
            report,
            "lab.kayit",
            "warning",
            "Laboratuvar",
            "LAB numune derinlikleri",
            "Laboratuvar başlıkları bulundu ancak sondaj/derinlik kaydı ayıklanamadı.",
            "rapor",
            "Sondaj No ve Örnek Derinliği sütunlarını kontrol edin.",
        )
        return

    sondaj_map = {kimlik_anahtari(item.get("no")): item for item in veri.get("sondaj", []) or []}
    seen = set()
    for record in parsed["records"]:
        key = kimlik_anahtari(record["sondaj"])
        sondaj = sondaj_map.get(key)
        if sondaj is None:
            bulgu_ekle(
                report,
                f"lab.satir.{record['row']}.sondaj",
                "warning",
                "Laboratuvar",
                "LAB sondaj eşleşmesi",
                f"LAB satır {record['row'] + 1}: '{record['sondaj']}' proje sondajlarıyla eşleşmiyor.",
                "rapor",
                "LAB Sheet sondaj numarasını proje ile aynı yazın.",
                entity=record["sondaj"],
            )
            continue
        sondaj_no = sondaj.get("no") or record["sondaj"]
        total_depth = sayi_veya_none(sondaj.get("der"))
        if total_depth is not None and record["bottom"] > total_depth + 0.05:
            bulgu_ekle(
                report,
                f"lab.satir.{record['row']}.derinlik",
                "error",
                "Laboratuvar",
                "LAB numune derinliği",
                f"{sondaj_no}: LAB numunesi sondaj derinliğini aşıyor ({record['raw_depth']}).",
                "rapor",
                "Numune derinliğini veya sondaj eşleşmesini düzeltin.",
                entity=sondaj_no,
            )
        intervals = litoloji_araliklari(sondaj.get("litoloji", []))
        if intervals and not derinlik_aralikta_mi(record["top"], intervals):
            bulgu_ekle(
                report,
                f"lab.satir.{record['row']}.litoloji",
                "warning",
                "Laboratuvar",
                "LAB-litoloji eşleşmesi",
                f"{sondaj_no}: LAB numune derinliği litoloji aralıklarının dışında ({record['raw_depth']}).",
                "workbook",
                "Litoloji kapsamını ve laboratuvar numune derinliğini karşılaştırın.",
                entity=sondaj_no,
                sheet="litoloji",
            )
        duplicate_key = (key, round(record["top"], 3), round(record["bottom"], 3))
        if duplicate_key in seen:
            bulgu_ekle(
                report,
                f"lab.satir.{record['row']}.mukerrer",
                "warning",
                "Laboratuvar",
                "Mükerrer LAB numunesi",
                f"{sondaj_no}: {record['raw_depth']} aralığı LAB verisinde birden fazla kez geçiyor.",
                "rapor",
                "Mükerrer laboratuvar satırlarını kontrol edin.",
                entity=sondaj_no,
            )
        seen.add(duplicate_key)
