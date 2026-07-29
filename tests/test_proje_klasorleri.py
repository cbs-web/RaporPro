# Dosya: RaporPro/tests/test_proje_klasorleri.py
from proje_klasorleri import (
    PROJE_ALT_KLASORLERI,
    proje_alt_klasorlerini_olustur,
)


def test_proje_ilk_kaydinda_standart_alt_klasorler_olusturulur(tmp_path):
    project_path = tmp_path / "Ornek Proje.json"

    result = proje_alt_klasorlerini_olustur(project_path)

    assert not result["hatalar"]
    assert set(result["olusturulan"]) == set(PROJE_ALT_KLASORLERI)
    for name in PROJE_ALT_KLASORLERI:
        assert (tmp_path / name).is_dir()


def test_mevcut_klasorler_ve_icerikleri_korunur(tmp_path):
    maps = tmp_path / "03_Haritalar"
    maps.mkdir()
    existing_file = maps / "mevcut_harita.jpg"
    existing_file.write_bytes(b"mevcut")

    first = proje_alt_klasorlerini_olustur(tmp_path / "Proje.json")
    second = proje_alt_klasorlerini_olustur(tmp_path / "Proje.json")

    assert "03_Haritalar" in first["mevcut"]
    assert not second["olusturulan"]
    assert set(second["mevcut"]) == set(PROJE_ALT_KLASORLERI)
    assert existing_file.read_bytes() == b"mevcut"
