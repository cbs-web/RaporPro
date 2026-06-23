# Dosya: RaporPro/ui_spt_okuma_aktar.py
import datetime
from tkinter import messagebox

from spt_okuma_motoru import spt_gecmis_kaydet
from workbook_motoru import yeni_sondaj_sablonu
from yardimcilar import safe_float


def apply_spt_import(app, records, update_selected_from_form, update_same_var, clear_target_var, status_var, close=False, window=None):
    update_selected_from_form(silent=True)
    aktarilacak_records = [
        record for record in records
        if record.get("record_type") != "queue" and record.get("include", True)
    ]
    kayitlar = [record["kayit"] for record in aktarilacak_records]
    if not kayitlar:
        messagebox.showwarning("SPT Merkezi", "Aktarılacak seçili SPT satırı yok.")
        return
    if any(record.get("quality", {}).get("level") == "error" and record.get("include", True) for record in aktarilacak_records):
        if not messagebox.askyesno("SPT Merkezi", "Hatalı görünen satırlar var. Yine de aktaralım mı?"):
            return

    by_no = {s.get("no"): s for s in app.veri.setdefault("sondaj", []) if s.get("no")}
    created = added = updated = skipped = 0

    def get_or_create_sondaj(no):
        nonlocal created
        if no in by_no:
            return by_no[no]
        sondaj = yeni_sondaj_sablonu(len(app.veri["sondaj"]))
        sondaj["no"] = no
        app.veri["sondaj"].append(sondaj)
        by_no[no] = sondaj
        created += 1
        return sondaj

    if clear_target_var.get():
        for no in sorted({k.sondaj_no for k in kayitlar if k.sondaj_no}):
            get_or_create_sondaj(no)["spt"] = []

    for kayit in kayitlar:
        if not kayit.sondaj_no or not kayit.derinlik:
            skipped += 1
            continue
        sondaj = get_or_create_sondaj(kayit.sondaj_no)
        spt_list = sondaj.setdefault("spt", [])
        target_depth = safe_float(kayit.derinlik)
        existing_idx = None
        for idx, existing in enumerate(spt_list):
            if existing and abs(safe_float(existing[0]) - target_depth) <= 0.01:
                existing_idx = idx
                break
        if existing_idx is not None:
            if update_same_var.get():
                spt_list[existing_idx] = kayit.spt_satiri()
                updated += 1
            else:
                skipped += 1
                continue
        else:
            spt_list.append(kayit.spt_satiri())
            added += 1
        spt_list.sort(key=lambda item: safe_float(item[0]) if item else 9999)

        kaynaklar = sondaj.setdefault("spt_kaynaklari", [])
        kaynaklar[:] = [item for item in kaynaklar if safe_float(item.get("derinlik")) != target_depth]
        kaynaklar.append({
            "derinlik": kayit.derinlik,
            "kaynak": kayit.kaynak,
            "kaynak_yolu": kayit.kaynak_yolu,
            "guven": kayit.guven,
            "aktarim_tarihi": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        })
        spt_gecmis_kaydet("aktarildi", kayit, {"sondaj": kayit.sondaj_no})

    app.sondaj_tablosunu_ciz()
    app.ozet_yenile(collect=False)
    status = f"SPT aktarıldı: {added} yeni, {updated} güncel"
    if skipped:
        status += f", {skipped} atlandı"
    if created:
        status += f", {created} sondaj oluşturuldu"
    app.set_status(status + ".", level="success")
    status_var.set(status + ".")
    if close and window is not None:
        window.destroy()
