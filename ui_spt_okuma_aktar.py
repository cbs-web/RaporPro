# Dosya: RaporPro/ui_spt_okuma_aktar.py
from copy import deepcopy
from tkinter import messagebox

from spt_aktarim_motoru import (
    spt_aktarim_bilinmeyen_sondajlar,
    spt_aktarim_plani_olustur,
)
from spt_okuma_motoru import normalize_sondaj_no, spt_gecmis_kaydet


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
    bilinmeyen = spt_aktarim_bilinmeyen_sondajlar(app.veri, kayitlar)
    eksik_sondaj_olustur = False
    if bilinmeyen:
        answer = messagebox.askyesnocancel(
            "Tanımsız Sondajlar",
            "Şu sondajlar projede bulunmuyor:\n\n"
            + ", ".join(bilinmeyen)
            + "\n\nEvet: yeni sondaj olarak oluştur\n"
              "Hayır: bu satırları atla\n"
              "İptal: aktarımı durdur",
        )
        if answer is None:
            return
        eksik_sondaj_olustur = bool(answer)
    bilinmeyen_set = set(bilinmeyen)
    other_errors = [
        record for record in aktarilacak_records
        if record.get("quality", {}).get("level") == "error"
        and normalize_sondaj_no(record["kayit"].sondaj_no) not in bilinmeyen_set
    ]
    if other_errors and not messagebox.askyesno(
        "SPT Merkezi",
        "Hatalı görünen satırlar var. Yine de aktaralım mı?",
    ):
        return

    plan = spt_aktarim_plani_olustur(
        app.veri,
        kayitlar,
        ayni_derinligi_guncelle=bool(update_same_var.get()),
        once_temizle=bool(clear_target_var.get()),
        eksik_sondaj_olustur=eksik_sondaj_olustur,
    )
    stats = plan["stats"]
    if not clear_target_var.get() and not any(
        stats[key] for key in ("created", "added", "updated")
    ):
        messagebox.showinfo(
            "SPT Aktarım Planı",
            "Proje verisini değiştirecek bir SPT işlemi oluşmadı. Seçimler ve aynı derinlik ayarını kontrol edin.",
        )
        return
    summary = (
        f"Yeni SPT: {stats['added']}\n"
        f"Güncellenecek: {stats['updated']}\n"
        f"Atlanacak: {stats['skipped']}\n"
        f"Oluşturulacak sondaj: {stats['created']}"
    )
    if clear_target_var.get():
        summary += "\n\nSeçili sondajların mevcut SPT verileri yeni kayıtlarla değiştirilecek."
    if not messagebox.askyesno("SPT Aktarım Planı", summary + "\n\nBu plan uygulansın mı?"):
        return

    previous_sondajlar = deepcopy(app.veri.setdefault("sondaj", []))
    app.veri["sondaj"][:] = plan["sondajlar"]
    app._spt_son_aktarim_geri_al = previous_sondajlar
    for kayit in kayitlar:
        try:
            spt_gecmis_kaydet(
                "aktarildi",
                kayit,
                {
                    "sondaj": kayit.sondaj_no,
                    "motor": getattr(kayit, "raw", {}).get("motor", ""),
                    "model": getattr(kayit, "raw", {}).get("model", ""),
                },
            )
        except Exception:
            pass

    app.sondaj_tablosunu_ciz()
    app.ozet_yenile(collect=False)
    status = f"SPT aktarıldı: {stats['added']} yeni, {stats['updated']} güncel"
    if stats["skipped"]:
        status += f", {stats['skipped']} atlandı"
    if stats["created"]:
        status += f", {stats['created']} sondaj oluşturuldu"
    app.set_status(status + ".", level="success")
    status_var.set(status + ".")
    if close and window is not None:
        window.destroy()


def undo_last_spt_import(app, status_var=None):
    snapshot = getattr(app, "_spt_son_aktarim_geri_al", None)
    if snapshot is None:
        messagebox.showinfo("SPT Geri Al", "Bu oturumda geri alınabilecek bir SPT aktarımı yok.")
        return False
    if not messagebox.askyesno("SPT Geri Al", "Son SPT aktarımı geri alınsın mı?"):
        return False
    app.veri["sondaj"][:] = deepcopy(snapshot)
    app._spt_son_aktarim_geri_al = None
    app.sondaj_tablosunu_ciz()
    app.ozet_yenile(collect=False)
    app.set_status("Son SPT aktarımı geri alındı.", level="warning")
    if status_var is not None:
        status_var.set("Son SPT aktarımı geri alındı.")
    return True
