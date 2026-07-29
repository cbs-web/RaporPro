# Dosya: RaporPro/tests/test_kesit_dosya_yolu.py
from pathlib import Path

from ui_kesit_yardimci import benzersiz_kesit_cikti_yolu


def test_kesit_ciktisi_ilk_kez_dogrudan_istenen_adla_kaydedilir(tmp_path):
    result = benzersiz_kesit_cikti_yolu(
        tmp_path / "02_Kesitler",
        "Kesit SK1-SK3",
        ".jpg",
    )

    assert Path(result).name == "Kesit SK1-SK3.jpg"
    assert Path(result).parent.is_dir()


def test_mevcut_kesit_ciktisi_sessizce_ezilmez(tmp_path):
    folder = tmp_path / "02_Kesitler"
    folder.mkdir()
    (folder / "Kesit SK1-SK3.jpg").write_bytes(b"ilk")

    result = benzersiz_kesit_cikti_yolu(folder, "Kesit SK1-SK3", "jpg")

    assert Path(result).name == "Kesit SK1-SK3 (2).jpg"
    assert (folder / "Kesit SK1-SK3.jpg").read_bytes() == b"ilk"


def test_cok_sayfali_kesit_parcalari_da_ad_cakismasi_sayilir(tmp_path):
    folder = tmp_path / "02_Kesitler"
    folder.mkdir()
    (folder / "Kesit SK1-SK8_Sayfa1.png").write_bytes(b"sayfa")

    result = benzersiz_kesit_cikti_yolu(folder, "Kesit SK1-SK8", ".png")

    assert Path(result).name == "Kesit SK1-SK8 (2).png"
