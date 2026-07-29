# Dosya: RaporPro/tests/test_evrak_okuma.py
import shutil

import fitz

from evrak_okuma import (
    EvrakAlani,
    _alanlari_birlestir,
    _filename_ada_parsel,
    belge_turunu_belirle,
    evrak_pdflerini_bul,
)
from proje_sema import proje_verisini_migre_et, varsayilan_proje_verisi
from ui_evrak_okuma import _deger_anahtari


def _pdf_olustur(path, text):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_turkce_dosya_adindan_belge_turu_bulunur():
    assert (
        belge_turunu_belirle("eimza8740_İmar Durumu Belgesi.pdf")
        == "imar_durumu"
    )
    assert (
        belge_turunu_belirle(
            "zemin durum belgesi_1109 ada 1 parsel zemin durum belgesi_22309.pdf"
        )
        == "zemin_durumu"
    )


def test_dosya_adindan_ada_ve_parsel_okunur():
    assert _filename_ada_parsel(
        "zemin durum belgesi_1109 ada 1 parsel.pdf"
    ) == ("1109", "1")


def test_ayni_pdf_yalniz_bir_kez_taranir(tmp_path):
    original = tmp_path / "İmar Durumu Belgesi.pdf"
    duplicate = tmp_path / "İmar Durumu Belgesi kopya.pdf"
    _pdf_olustur(original, "IMAR DURUMU")
    shutil.copyfile(original, duplicate)

    documents, duplicates = evrak_pdflerini_bul(tmp_path)

    assert len(documents) == 1
    assert len(duplicates) == 1
    assert documents[0]["type"] == "imar_durumu"


def test_ayni_alan_birden_fazla_belgeden_birlestirilir():
    fields, warnings = _alanlari_birlestir(
        [
            EvrakAlani(
                "kunye",
                "ada",
                "Ada",
                "1109",
                "İmar.pdf",
                "İmar Durumu",
                0.82,
            ),
            EvrakAlani(
                "kunye",
                "ada",
                "Ada",
                "1109",
                "Zemin.pdf",
                "Zemin Durum Belgesi",
                0.96,
            ),
        ]
    )

    assert not warnings
    assert fields[0].deger == "1109"
    assert fields[0].kaynak == "Zemin.pdf, İmar.pdf"
    assert fields[0].guven == 0.96


def test_celiskili_pafta_alternatif_olarak_korunur():
    fields, warnings = _alanlari_birlestir(
        [
            EvrakAlani(
                "kunye",
                "paf",
                "Pafta",
                "H16C14B2B",
                "İmar.pdf",
                "İmar Durumu",
                0.95,
            ),
            EvrakAlani(
                "kunye",
                "paf",
                "Pafta",
                "32M-4-C",
                "Başka.pdf",
                "Zemin Durum Belgesi",
                0.70,
            ),
        ]
    )

    assert fields[0].deger == "H16C14B2B"
    assert fields[0].alternatifler == ("32M-4-C",)
    assert warnings


def test_dolu_alan_karsilastirmasi_turkce_harfleri_tolere_eder():
    assert _deger_anahtari("Alüvyon (Qal)") == _deger_anahtari("ALUVYON Qal")
    assert _deger_anahtari("H16C14B2B") != _deger_anahtari("32M-4-C")


def test_evrak_aktarim_kaydi_proje_migrasyonunda_korunur():
    project = varsayilan_proje_verisi()
    project["evrak_aktarimi"] = {
        "son_klasor": r"C:\Proje\EVRAKLAR",
        "uygulanan_alanlar": [{"bolum": "kunye", "anahtar": "ada", "deger": "1109"}],
    }

    migrated, _info = proje_verisini_migre_et(project)

    assert migrated["evrak_aktarimi"] == project["evrak_aktarimi"]
