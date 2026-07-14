# Dosya: RaporPro/tutarlilik_motoru.py
import os

from jeofizik_sheet_motoru import jeofizik_sheet_var_mi
from karot_motoru import derinlik_araligi_coz
from sondaj_derinlik import sondaj_derinligi_kontrol_sonucu
from tutarlilik_jeofizik import jeofizik_kontrol
from tutarlilik_laboratuvar import laboratuvar_kayitlarini_ayikla, laboratuvar_kontrol
from tutarlilik_ortak import (
    bos_mu,
    bulgu_ekle,
    derinlik_aralikta_mi as _derinlik_aralikta_mi,
    kimlik_anahtari,
    kontrol_ekle,
    kontrol_raporunu_tamamla,
    koordinat_durumu as _koordinat_durumu,
    litoloji_araliklari as _litoloji_araliklari,
    refu_mu as _refu_mu,
    sayi_veya_none,
    slug as _slug,
    yeni_kontrol_raporu,
)
from yardimcilar import litoloji_yazim_uyarilari

DOSYA_KONTROLLERI = (
    ("word_path", "Word şablonu", "rapor", "Dahili şablonu kontrol edin veya özel bir Word şablonu seçin.", "error"),
    ("lab_excel_path", "Lab Excel", "rapor", "LAB Sheet doldurun veya Lab Excel bağlayın.", "warning"),
    ("jeo_excel_path", "Jeofizik Excel", "jeofizik", "Jeofizik Sheet doldurun, Excel bağlayın veya manuel veri girin.", "warning"),
    ("kml_path", "KML sınır", "haritalar", "KML sınır dosyasını seçin.", "info"),
    ("img_yer", "Yerbuldurur", "haritalar", "Yerbuldurur haritasını oluşturun.", "info"),
    ("img_tkgm", "TKGM", "haritalar", "TKGM görselini oluşturun veya seçin.", "info"),
    ("img_pga", "PGA", "haritalar", "PGA görselini oluşturun veya seçin.", "info"),
    ("img_mjh", "MJH", "haritalar", "Mühendislik jeolojisi haritasını Word için aktarın.", "info"),
    ("word_img_sondaj", "Sondaj haritası", "haritalar", "Sondaj lokasyon haritasını Word için aktarın.", "info"),
    ("word_img_jeofizik", "Jeofizik haritası", "haritalar", "Jeofizik lokasyon haritasını Word için aktarın.", "info"),
)


def _deney_derinligi_kontrol(
    report,
    sondaj_no,
    total_depth,
    label,
    rows,
    intervals,
    sheet,
):
    depths = []
    problem_count = 0
    for row_idx, row in enumerate(rows or []):
        if not isinstance(row, (list, tuple)) or not row:
            problem_count += 1
            bulgu_ekle(
                report,
                f"sondaj.{_slug(sondaj_no)}.{sheet}.{row_idx}.bos",
                "warning",
                "Arazi deneyleri",
                f"{label} satırı",
                f"{sondaj_no}: {label} {row_idx + 1}. satırında derinlik yok.",
                "workbook",
                f"Workbook {label} sayfasında satırı kontrol edin.",
                entity=sondaj_no,
                field="der",
                sheet=sheet,
                row=row_idx,
            )
            continue
        if sheet == "kaya":
            top, bottom = derinlik_araligi_coz(row[0])
            depth = top if top > 0 or bottom > 0 else None
            if depth is not None and bottom > 0 and total_depth is not None and bottom > total_depth + 0.05:
                problem_count += 1
                bulgu_ekle(
                    report,
                    f"sondaj.{_slug(sondaj_no)}.kaya.{row_idx}.son",
                    "error",
                    "Kaya ve karot",
                    "Karot aralığı",
                    f"{sondaj_no}: Kaya {row_idx + 1}. aralığı sondaj derinliğini aşıyor ({row[0]}).",
                    "workbook",
                    "Karot aralığını kuyu derinliği içinde düzeltin.",
                    entity=sondaj_no,
                    field="der",
                    sheet="kaya",
                    row=row_idx,
                )
        else:
            depth = sayi_veya_none(row[0])

        if depth is None:
            problem_count += 1
            bulgu_ekle(
                report,
                f"sondaj.{_slug(sondaj_no)}.{sheet}.{row_idx}.derinlik",
                "warning",
                "Arazi deneyleri",
                f"{label} derinliği",
                f"{sondaj_no}: {label} {row_idx + 1}. derinliği sayısal değil.",
                "workbook",
                "Deney derinliğini sayısal olarak girin.",
                entity=sondaj_no,
                field="der",
                sheet=sheet,
                row=row_idx,
            )
            continue

        depths.append((round(depth, 3), row_idx))
        if depth < 0 or (total_depth is not None and depth > total_depth + 0.05):
            problem_count += 1
            bulgu_ekle(
                report,
                f"sondaj.{_slug(sondaj_no)}.{sheet}.{row_idx}.kuyu_disi",
                "error",
                "Arazi deneyleri",
                f"{label} derinliği",
                f"{sondaj_no}: {label} {row_idx + 1}. derinliği kuyu aralığının dışında ({depth:g} m).",
                "workbook",
                "Deney derinliğini sondaj derinliğine göre düzeltin.",
                entity=sondaj_no,
                field="der",
                sheet=sheet,
                row=row_idx,
            )
        elif intervals and not _derinlik_aralikta_mi(depth, intervals):
            problem_count += 1
            bulgu_ekle(
                report,
                f"sondaj.{_slug(sondaj_no)}.{sheet}.{row_idx}.litoloji_disi",
                "warning",
                "Arazi deneyleri",
                f"{label} derinliği",
                f"{sondaj_no}: {label} {row_idx + 1}. derinliği litoloji aralıklarının dışında ({depth:g} m).",
                "workbook",
                "Litoloji kapsamını veya deney derinliğini kontrol edin.",
                entity=sondaj_no,
                field="der",
                sheet=sheet,
                row=row_idx,
            )

        if sheet == "spt":
            for col_idx, field in ((1, "v15"), (2, "v30"), (3, "v45")):
                if len(row) <= col_idx or bos_mu(row[col_idx]) or _refu_mu(row[col_idx]):
                    continue
                blow = sayi_veya_none(row[col_idx])
                if blow is None or blow < 0:
                    problem_count += 1
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(sondaj_no)}.spt.{row_idx}.{field}",
                        "warning",
                        "SPT",
                        "SPT darbe sayısı",
                        f"{sondaj_no}: SPT {row_idx + 1}. satırındaki darbe sayısı geçersiz.",
                        "workbook",
                        "SPT darbe sayısını sıfır veya pozitif sayı olarak girin.",
                        entity=sondaj_no,
                        field=field,
                        sheet="spt",
                        row=row_idx,
                    )
            if len(row) >= 5 and not bos_mu(row[4]) and not _refu_mu(row[4]):
                n30 = sayi_veya_none(row[4])
                v30 = sayi_veya_none(row[2]) if len(row) > 2 else None
                v45 = sayi_veya_none(row[3]) if len(row) > 3 else None
                if n30 is None or n30 < 0:
                    problem_count += 1
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(sondaj_no)}.spt.{row_idx}.n30",
                        "warning",
                        "SPT",
                        "N30 değeri",
                        f"{sondaj_no}: SPT {row_idx + 1}. N30 değeri sayısal değil.",
                        "workbook",
                        "N30 değerini kontrol edin veya otomatik hesaplatın.",
                        entity=sondaj_no,
                        field="n30",
                        sheet="spt",
                        row=row_idx,
                    )
                elif v30 is not None and v45 is not None and abs(n30 - (v30 + v45)) > 0.01:
                    problem_count += 1
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(sondaj_no)}.spt.{row_idx}.n30_toplam",
                        "warning",
                        "SPT",
                        "N30 toplamı",
                        f"{sondaj_no}: SPT {row_idx + 1}. N30={n30:g}, 15-30 ve 30-45 toplamı {v30 + v45:g}.",
                        "workbook",
                        "Workbook N30 komutuyla değeri yeniden hesaplayın.",
                        entity=sondaj_no,
                        field="n30",
                        sheet="spt",
                        row=row_idx,
                    )
        elif sheet == "pmt":
            for col_idx, field, title in ((1, "em", "Em"), (2, "pl", "Pl")):
                if len(row) <= col_idx or bos_mu(row[col_idx]):
                    continue
                value = sayi_veya_none(row[col_idx])
                if value is None or value <= 0:
                    problem_count += 1
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(sondaj_no)}.pmt.{row_idx}.{field}",
                        "warning",
                        "Presiyometre",
                        f"PMT {title}",
                        f"{sondaj_no}: PMT {row_idx + 1}. {title} değeri geçersiz.",
                        "workbook",
                        f"{title} değerini pozitif sayı olarak girin.",
                        entity=sondaj_no,
                        field=field,
                        sheet="pmt",
                        row=row_idx,
                    )
        elif sheet == "kaya" and len(row) >= 4:
            values = [sayi_veya_none(row[idx]) for idx in (1, 2, 3)]
            labels = ("TCR", "SCR", "RQD")
            for col_idx, (value, title) in enumerate(zip(values, labels), start=1):
                if value is None or not (0 <= value <= 100):
                    problem_count += 1
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(sondaj_no)}.kaya.{row_idx}.{title.casefold()}",
                        "warning",
                        "Kaya ve karot",
                        title,
                        f"{sondaj_no}: Kaya {row_idx + 1}. {title} değeri 0-100 aralığında değil.",
                        "workbook",
                        f"{title} yüzdesini kontrol edin.",
                        entity=sondaj_no,
                        field=("tcr", "scr", "rqd")[col_idx - 1],
                        sheet="kaya",
                        row=row_idx,
                    )
            if all(value is not None for value in values) and not (values[2] <= values[1] <= values[0]):
                problem_count += 1
                bulgu_ekle(
                    report,
                    f"sondaj.{_slug(sondaj_no)}.kaya.{row_idx}.oran_sirasi",
                    "warning",
                    "Kaya ve karot",
                    "Karot yüzdeleri",
                    f"{sondaj_no}: Kaya {row_idx + 1}. satırında RQD ≤ SCR ≤ TCR koşulu sağlanmıyor.",
                    "workbook",
                    "TCR, SCR ve RQD değerlerini kontrol edin.",
                    entity=sondaj_no,
                    field="tcr",
                    sheet="kaya",
                    row=row_idx,
                )

    seen = {}
    for depth, row_idx in depths:
        if depth in seen:
            problem_count += 1
            bulgu_ekle(
                report,
                f"sondaj.{_slug(sondaj_no)}.{sheet}.{row_idx}.mukerrer",
                "warning",
                "Arazi deneyleri",
                f"Mükerrer {label}",
                f"{sondaj_no}: {depth:g} m derinliğinde birden fazla {label} kaydı var.",
                "workbook",
                "Mükerrer satırları kontrol edin.",
                entity=sondaj_no,
                field="der",
                sheet=sheet,
                row=row_idx,
            )
        else:
            seen[depth] = row_idx
    return problem_count


def _dosya_kontrolleri(report, veri, dosya_durumlari):
    lab_sheet_ready = any(
        any(not bos_mu(cell) for cell in row)
        for row in veri.get("lab_sheet", {}).get("rows", []) or []
        if isinstance(row, (list, tuple))
    )
    jeo_sheet_ready = bool(jeofizik_sheet_var_mi(veri))
    jeofizik = veri.get("jeofizik", {}) or {}
    manual_jeo_ready = bool(jeofizik.get("ss_list") or jeofizik.get("mt_list"))

    for key, label, target, suggestion, failure_level in DOSYA_KONTROLLERI:
        path = dosya_durumlari.get(key)
        if key == "lab_excel_path" and lab_sheet_ready:
            ok = True
            detail = "LAB Sheet hazır."
        elif key == "jeo_excel_path" and (jeo_sheet_ready or manual_jeo_ready):
            ok = True
            detail = "Jeofizik Sheet veya manuel jeofizik verisi hazır."
        else:
            ok = bool(path and os.path.isfile(path))
            if ok:
                detail = os.path.basename(path)
            elif path:
                detail = f"Dosya bulunamadı: {os.path.basename(str(path))}"
            else:
                detail = "Seçilmedi."
        kontrol_ekle(
            report,
            f"dosya.{key}",
            "Dosya bağlantıları",
            label,
            ok,
            detail,
            target,
            suggestion,
            failure_level=failure_level,
            weight=1,
        )

    output_folder = (
        veri.get("ayarlar", {}).get("cikti_merkezi_klasor")
        or veri.get("ayarlar", {}).get("varsayilan_cikti_klasor")
    )
    output_ok = bool(output_folder and os.path.isdir(output_folder) and os.access(output_folder, os.W_OK))
    kontrol_ekle(
        report,
        "dosya.cikti_klasoru",
        "Dosya bağlantıları",
        "Çıktı klasörü",
        output_ok,
        output_folder if output_ok else "Yazılabilir bir çıktı klasörü seçilmedi.",
        "cikti",
        "Çıktı Merkezi'nden yazılabilir ana klasörü seçin.",
        failure_level="warning",
        weight=1,
    )


def proje_tutarlilik_raporu(veri, dosya_durumlari=None, lab_rows=None):
    veri = veri if isinstance(veri, dict) else {}
    report = yeni_kontrol_raporu()
    required_sections = ("kunye", "bina", "arazi", "sondaj", "jeofizik")
    missing_sections = [section for section in required_sections if section not in veri]
    kontrol_ekle(
        report,
        "proje.veri_yapisi",
        "Proje",
        "Proje veri yapısı",
        not missing_sections,
        "Temel proje bölümleri mevcut." if not missing_sections else "Eksik veri bölümleri: " + ", ".join(missing_sections),
        "ozet",
        "Projeyi yeniden açın veya eksik bölümleri varsayılan değerlerle tamamlayın.",
        failure_level="error",
        weight=0,
        dashboard=False,
    )

    kunye = veri.get("kunye", {}) if isinstance(veri.get("kunye", {}), dict) else {}
    missing_project = [
        label
        for key, label in (("sahibi", "proje adı"), ("il", "il"), ("ilce", "ilçe"))
        if bos_mu(kunye.get(key))
    ]
    kontrol_ekle(
        report,
        "proje.kunye",
        "Proje",
        "Proje bilgisi",
        not missing_project,
        "Proje adı, il ve ilçe tamam." if not missing_project else "Eksik alanlar: " + ", ".join(missing_project),
        "kunye",
        "Künye sekmesinde proje ve konum alanlarını tamamlayın.",
        failure_level="warning",
        weight=2,
        field="sahibi" if "proje adı" in missing_project else ("il" if "il" in missing_project else "ilce"),
    )

    sondajlar = veri.get("sondaj", []) if isinstance(veri.get("sondaj", []), list) else []
    kontrol_ekle(
        report,
        "sondaj.kayit",
        "Sondaj",
        "Sondaj kaydı",
        bool(sondajlar),
        f"{len(sondajlar)} sondaj kaydı var." if sondajlar else "En az bir sondaj kaydı gerekli.",
        "sondaj",
        "Sondaj sekmesinden kayıt ekleyin veya Workbook kullanın.",
        failure_level="error",
        weight=3,
    )

    names = []
    valid_depths = True
    coords_ok = bool(sondajlar)
    elevations_ok = bool(sondajlar)
    lithology_exists = bool(sondajlar)
    lithology_coverage_ok = bool(sondajlar)
    tests_exist = False
    tests_ok = True
    for idx, sondaj in enumerate(sondajlar):
        sondaj = sondaj if isinstance(sondaj, dict) else {}
        no = str(sondaj.get("no") or f"SK-{idx + 1}").strip()
        name_key = kimlik_anahtari(no)
        names.append((name_key, no, idx))
        depth = sayi_veya_none(sondaj.get("der"))
        if depth is None or depth <= 0:
            valid_depths = False
            bulgu_ekle(
                report,
                f"sondaj.{_slug(no)}.derinlik",
                "error",
                "Sondaj",
                "Sondaj derinliği",
                f"{no}: sondaj derinliği geçersiz.",
                "workbook",
                "Sondajlar sayfasında derinliği pozitif sayı olarak girin.",
                entity=no,
                field="der",
                sheet="sondajlar",
                row=idx,
            )
            depth = None

        coordinate_ok, coordinate_detail = _koordinat_durumu(sondaj.get("y"), sondaj.get("x"))
        if not coordinate_ok:
            coords_ok = False
            bulgu_ekle(
                report,
                f"sondaj.{_slug(no)}.koordinat",
                "warning",
                "Sondaj",
                "Sondaj koordinatı",
                f"{no}: {coordinate_detail}",
                "workbook",
                "Sondaj koordinatlarını doldurun veya harita aracını kullanın.",
                entity=no,
                field="y",
                sheet="sondajlar",
                row=idx,
            )
        if bos_mu(sondaj.get("k")) or sayi_veya_none(sondaj.get("k")) is None:
            elevations_ok = False
            bulgu_ekle(
                report,
                f"sondaj.{_slug(no)}.kot",
                "warning",
                "Sondaj",
                "Sondaj kotu",
                f"{no}: kuyu başlangıç kotu girilmemiş veya sayısal değil.",
                "workbook",
                "Sondajlar sayfasında kuyu kotunu girin.",
                entity=no,
                field="k",
                sheet="sondajlar",
                row=idx,
            )

        for yass_key, yass_label in (("yass_d1", "YASS 1"), ("yass_d2", "YASS 2")):
            yass = sayi_veya_none(sondaj.get(yass_key))
            if yass is not None and (yass < 0 or (depth is not None and yass > depth + 0.05)):
                bulgu_ekle(
                    report,
                    f"sondaj.{_slug(no)}.{yass_key}",
                    "warning",
                    "Sondaj",
                    "Yeraltı suyu",
                    f"{no}: {yass_label} derinliği kuyu aralığının dışında ({yass:g} m).",
                    "sondaj",
                    "YASS derinliğini kontrol edin.",
                    entity=no,
                    field=yass_key,
                )

        litoloji = sondaj.get("litoloji", []) or []
        if not litoloji:
            lithology_exists = False
            lithology_coverage_ok = False
            bulgu_ekle(
                report,
                f"sondaj.{_slug(no)}.litoloji",
                "warning",
                "Litoloji",
                "Litoloji kaydı",
                f"{no}: litoloji girilmemiş.",
                "workbook",
                "Workbook Litoloji sayfasında katmanları girin.",
                entity=no,
                field="tanim",
                sheet="litoloji",
            )
        else:
            valid_rows = []
            for row_idx, row in enumerate(litoloji):
                if not isinstance(row, (list, tuple)) or len(row) < 3:
                    lithology_coverage_ok = False
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.{row_idx}.eksik",
                        "error",
                        "Litoloji",
                        "Litoloji satırı",
                        f"{no}: {row_idx + 1}. litoloji satırı eksik.",
                        "workbook",
                        "Başlangıç, bitiş ve tanım alanlarını tamamlayın.",
                        entity=no,
                        field="tanim",
                        sheet="litoloji",
                        row=row_idx,
                    )
                    continue
                top = sayi_veya_none(row[0])
                bottom = sayi_veya_none(row[1])
                if top is None or bottom is None or top < 0 or bottom <= top:
                    lithology_coverage_ok = False
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.{row_idx}.derinlik",
                        "error",
                        "Litoloji",
                        "Litoloji derinliği",
                        f"{no}: {row_idx + 1}. litoloji başlangıç/bitiş derinliği geçersiz.",
                        "workbook",
                        "Litoloji başlangıç ve bitiş derinliklerini düzeltin.",
                        entity=no,
                        field="top",
                        sheet="litoloji",
                        row=row_idx,
                    )
                    continue
                if depth is not None and bottom > depth + 0.05:
                    lithology_coverage_ok = False
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.{row_idx}.kuyu_disi",
                        "error",
                        "Litoloji",
                        "Litoloji kapsamı",
                        f"{no}: {row_idx + 1}. litoloji satırı sondaj derinliğini aşıyor ({bottom:g} > {depth:g} m).",
                        "workbook",
                        "Litoloji bitişini sondaj derinliğine göre düzeltin.",
                        entity=no,
                        field="bot",
                        sheet="litoloji",
                        row=row_idx,
                    )
                description = str(row[2] or "").strip()
                if not description:
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.{row_idx}.tanim",
                        "warning",
                        "Litoloji",
                        "Litoloji tanımı",
                        f"{no}: {row_idx + 1}. litoloji tanımı boş.",
                        "workbook",
                        "Litoloji birimini yazın.",
                        entity=no,
                        field="tanim",
                        sheet="litoloji",
                        row=row_idx,
                    )
                for typo_idx, warning in enumerate(litoloji_yazim_uyarilari(description)):
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.{row_idx}.yazim.{typo_idx}",
                        "warning",
                        "Litoloji",
                        "Litoloji yazımı",
                        f"{no}: {warning}",
                        "workbook",
                        "Litoloji tanımındaki yazımı kontrol edin.",
                        entity=no,
                        field="tanim",
                        sheet="litoloji",
                        row=row_idx,
                    )
                valid_rows.append((top, bottom, row_idx))

            valid_rows.sort(key=lambda item: (item[0], item[1]))
            if valid_rows:
                if valid_rows[0][0] > 0.05:
                    lithology_coverage_ok = False
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.baslangic",
                        "warning",
                        "Litoloji",
                        "Litoloji başlangıcı",
                        f"{no}: litoloji 0.00 m'den başlamıyor ({valid_rows[0][0]:g} m).",
                        "workbook",
                        "İlk litoloji başlangıcını kontrol edin.",
                        entity=no,
                        field="top",
                        sheet="litoloji",
                        row=valid_rows[0][2],
                    )
                previous_bottom = valid_rows[0][1]
                for top, bottom, row_idx in valid_rows[1:]:
                    if top < previous_bottom - 0.05:
                        lithology_coverage_ok = False
                        bulgu_ekle(
                            report,
                            f"sondaj.{_slug(no)}.litoloji.{row_idx}.cakisma",
                            "error",
                            "Litoloji",
                            "Litoloji çakışması",
                            f"{no}: litoloji katmanları {top:g} m civarında çakışıyor.",
                            "workbook",
                            "Bitiş ve sonraki başlangıç derinliklerini eşitleyin.",
                            entity=no,
                            field="top",
                            sheet="litoloji",
                            row=row_idx,
                        )
                    elif top > previous_bottom + 0.05:
                        lithology_coverage_ok = False
                        bulgu_ekle(
                            report,
                            f"sondaj.{_slug(no)}.litoloji.{row_idx}.bosluk",
                            "warning",
                            "Litoloji",
                            "Litoloji boşluğu",
                            f"{no}: litolojide {previous_bottom:g}-{top:g} m arasında boşluk var.",
                            "workbook",
                            "Katman sınırlarını kesintisiz hale getirin.",
                            entity=no,
                            field="top",
                            sheet="litoloji",
                            row=row_idx,
                        )
                    previous_bottom = max(previous_bottom, bottom)
                if depth is not None and previous_bottom < depth - 0.05:
                    lithology_coverage_ok = False
                    bulgu_ekle(
                        report,
                        f"sondaj.{_slug(no)}.litoloji.son",
                        "warning",
                        "Litoloji",
                        "Litoloji sonu",
                        f"{no}: litoloji {previous_bottom:g} m'de bitiyor, kuyu derinliği {depth:g} m.",
                        "workbook",
                        "Son litoloji birimini kuyu sonuna kadar tamamlayın.",
                        entity=no,
                        field="bot",
                        sheet="litoloji",
                        row=valid_rows[-1][2],
                    )

        intervals = _litoloji_araliklari(litoloji)
        for label, key, sheet in (("SPT", "spt", "spt"), ("PMT", "pmt", "pmt"), ("Kaya", "kaya", "kaya")):
            rows = sondaj.get(key, []) or []
            tests_exist = tests_exist or bool(rows)
            if _deney_derinligi_kontrol(report, no, depth, label, rows, intervals, sheet):
                tests_ok = False

    duplicates = {}
    for key, no, idx in names:
        if not key:
            continue
        duplicates.setdefault(key, []).append((no, idx))
    duplicate_groups = [items for items in duplicates.values() if len(items) > 1]
    for items in duplicate_groups:
        labels = ", ".join(item[0] for item in items)
        bulgu_ekle(
            report,
            f"sondaj.mukerrer.{_slug(items[0][0])}",
            "error",
            "Sondaj",
            "Mükerrer sondaj numarası",
            f"Aynı sondaj numarası birden fazla kullanılmış: {labels}.",
            "workbook",
            "Sondaj numaralarını benzersiz yapın.",
            entity=items[0][0],
            field="no",
            sheet="sondajlar",
            row=items[1][1],
        )

    kontrol_ekle(
        report,
        "sondaj.numaralar",
        "Sondaj",
        "Sondaj numaraları",
        bool(sondajlar) and not duplicate_groups,
        "Sondaj numaraları benzersiz." if sondajlar and not duplicate_groups else "Mükerrer veya eksik sondaj numarası var.",
        "workbook",
        "Sondajlar sayfasında numaraları kontrol edin.",
        failure_level="error" if duplicate_groups else "warning",
        weight=1,
        sheet="sondajlar",
    )
    kontrol_ekle(
        report,
        "sondaj.derinlikler",
        "Sondaj",
        "Sondaj derinlikleri",
        bool(sondajlar) and valid_depths,
        "Tüm sondaj derinlikleri geçerli." if sondajlar and valid_depths else "Geçersiz veya eksik sondaj derinliği var.",
        "workbook",
        "Sondajlar sayfasında derinlikleri kontrol edin.",
        failure_level="error",
        weight=2,
        sheet="sondajlar",
    )
    kontrol_ekle(
        report,
        "sondaj.koordinatlar",
        "Sondaj",
        "Sondaj koordinatları",
        coords_ok,
        "Tüm sondaj koordinatları geçerli." if coords_ok else "Eksik veya geçersiz sondaj koordinatı var.",
        "workbook",
        "Sondaj koordinatlarını kontrol edin.",
        failure_level="warning",
        weight=1,
        sheet="sondajlar",
    )
    kontrol_ekle(
        report,
        "sondaj.kotlar",
        "Sondaj",
        "Sondaj kotları",
        elevations_ok,
        "Tüm sondaj kotları geçerli." if elevations_ok else "Eksik veya geçersiz kuyu kotu var.",
        "workbook",
        "Sondaj kotlarını kontrol edin.",
        failure_level="warning",
        weight=1,
        sheet="sondajlar",
    )
    kontrol_ekle(
        report,
        "litoloji.kayit",
        "Litoloji",
        "Litoloji",
        lithology_exists,
        "Her sondajda litoloji var." if lithology_exists else "Bir veya daha fazla sondajda litoloji yok.",
        "workbook",
        "Workbook Litoloji sayfasını tamamlayın.",
        failure_level="warning",
        weight=2,
        sheet="litoloji",
    )
    kontrol_ekle(
        report,
        "litoloji.kapsam",
        "Litoloji",
        "Litoloji kapsamı",
        lithology_coverage_ok,
        "Litoloji 0.00 m'den kuyu sonuna kadar kesintisiz." if lithology_coverage_ok else "Litolojide boşluk, çakışma veya derinlik uyumsuzluğu var.",
        "workbook",
        "Litoloji başlangıç ve bitiş derinliklerini kontrol edin.",
        failure_level="warning",
        weight=2,
        sheet="litoloji",
    )
    kontrol_ekle(
        report,
        "deney.kayit",
        "Arazi deneyleri",
        "Arazi deneyleri",
        tests_exist,
        "SPT, PMT veya kaya/karot verisi var." if tests_exist else "SPT, PMT veya kaya/karot verisi yok.",
        "workbook",
        "Workbook üzerinden arazi deneylerini girin.",
        failure_level="warning",
        weight=1,
        sheet="spt",
    )
    kontrol_ekle(
        report,
        "deney.tutarlilik",
        "Arazi deneyleri",
        "Deney derinlikleri",
        tests_exist and tests_ok,
        "Deney derinlikleri ve değerleri tutarlı." if tests_exist and tests_ok else "Deney derinliği veya değerlerinde uyumsuzluk var.",
        "workbook",
        "SPT, PMT ve Kaya bulgularını kontrol edin.",
        failure_level="warning",
        weight=1,
        sheet="spt",
    )

    jeofizik_kontrol(report, veri)

    try:
        depth_check = sondaj_derinligi_kontrol_sonucu(veri)
        recommended = sayi_veya_none(depth_check.get("onerilen_sondaj_derinligi"))
        short = depth_check.get("eksik_sondajlar") or []
        notes = depth_check.get("uyarilar") or []
        depth_ok = bool(sondajlar) and recommended is not None and recommended > 0 and not short and not notes
        method = "Gerilme %10" if depth_check.get("hesap_tipi") == "gerilme_10" else "Yönetmelik ön kontrolü"
        detail = f"{method}: önerilen minimum {recommended:.2f} m." if recommended else "Sondaj derinliği önerisi hesaplanamadı."
        if short:
            detail += f" {len(short)} sondaj önerilen derinliğin altında."
        if notes:
            detail += f" {len(notes)} hesap notu var."
        kontrol_ekle(
            report,
            "sondaj.yonetmelik_derinligi",
            "Sondaj",
            "Yönetmelik sondaj derinliği",
            depth_ok,
            detail,
            "bina",
            "Sondaj Derinliği Hesabı ekranında temel ve zemin girdilerini kontrol edin.",
            failure_level="warning",
            weight=1,
        )
        for item_idx, item in enumerate(short[:20]):
            bulgu_ekle(
                report,
                f"sondaj.yonetmelik_derinligi.{item_idx}",
                "warning",
                "Sondaj",
                "Yetersiz sondaj derinliği",
                f"{item['sondaj']}: {item['derinlik']:.2f} m, önerilen {recommended:.2f} m; yaklaşık {item['eksik']:.2f} m eksik.",
                "bina",
                "Sondaj derinliği hesabını ve proje kararını kontrol edin.",
                entity=item.get("sondaj", ""),
            )
        if recommended:
            bulgu_ekle(
                report,
                "sondaj.yonetmelik_derinligi.bilgi",
                "info",
                "Sondaj",
                "Sondaj derinliği hesabı",
                detail,
                "bina",
                "",
                blocking=False,
            )
    except Exception as exc:
        kontrol_ekle(
            report,
            "sondaj.yonetmelik_derinligi",
            "Sondaj",
            "Yönetmelik sondaj derinliği",
            False,
            f"Sondaj derinliği hesabı çalıştırılamadı: {exc}",
            "bina",
            "Bina ve sondaj derinliği hesabı girdilerini kontrol edin.",
            failure_level="warning",
            weight=1,
        )

    effective_lab_rows = lab_rows
    if effective_lab_rows is None:
        effective_lab_rows = veri.get("lab_sheet", {}).get("rows", [])
    laboratuvar_kontrol(report, veri, effective_lab_rows)

    if dosya_durumlari is not None:
        _dosya_kontrolleri(report, veri, dosya_durumlari)

    report["stats"] = {
        "sondaj": len(sondajlar),
        "spt": sum(len(item.get("spt", []) or []) for item in sondajlar if isinstance(item, dict)),
        "pmt": sum(len(item.get("pmt", []) or []) for item in sondajlar if isinstance(item, dict)),
        "kaya": sum(len(item.get("kaya", []) or []) for item in sondajlar if isinstance(item, dict)),
    }
    return kontrol_raporunu_tamamla(report)
