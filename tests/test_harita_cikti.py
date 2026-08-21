# Dosya: RaporPro/tests/test_harita_cikti.py

from harita_cikti import (
    harita_ciktisini_proje_klasorune_kopyala,
    proje_harita_cikti_yolu,
)
from harita_durum import harita_katman_ayarlari
from ui_haritalar import HaritalarSekmesiMixin


def test_word_haritalari_proje_klasorune_kopyalanir(tmp_path):
    project_path = tmp_path / "Ornek Proje.json"
    project_path.write_text("{}", encoding="utf-8")
    source_dir = tmp_path / "appdata"
    source_dir.mkdir()
    sondaj_source = source_dir / "sondaj_lokasyon_123.jpg"
    jeofizik_source = source_dir / "jeofizik_lokasyon_123.jpg"
    sondaj_source.write_bytes(b"sondaj")
    jeofizik_source.write_bytes(b"jeofizik")

    sondaj_result = harita_ciktisini_proje_klasorune_kopyala(
        sondaj_source,
        project_path,
        "sondaj",
    )
    jeofizik_result = harita_ciktisini_proje_klasorune_kopyala(
        jeofizik_source,
        project_path,
        "jeofizik",
    )

    sondaj_target = tmp_path / "03_Haritalar" / "Sondaj_Lokasyon.jpg"
    jeofizik_target = tmp_path / "03_Haritalar" / "Jeofizik_Lokasyon.jpg"
    assert sondaj_result["path"] == str(sondaj_target)
    assert jeofizik_result["path"] == str(jeofizik_target)
    assert sondaj_target.read_bytes() == b"sondaj"
    assert jeofizik_target.read_bytes() == b"jeofizik"
    assert sondaj_source.read_bytes() == b"sondaj"
    assert jeofizik_source.read_bytes() == b"jeofizik"


def test_word_harita_cikti_yolu_deterministiktir(tmp_path):
    project_path = tmp_path / "Proje.json"

    assert proje_harita_cikti_yolu(project_path, "sondaj") == str(
        tmp_path / "03_Haritalar" / "Sondaj_Lokasyon.jpg"
    )
    assert proje_harita_cikti_yolu(project_path, "jeofizik") == str(
        tmp_path / "03_Haritalar" / "Jeofizik_Lokasyon.jpg"
    )


def test_kaydedilmemis_projede_kaynak_yolu_korunur(tmp_path):
    source = tmp_path / "gecici.jpg"
    source.write_bytes(b"harita")

    result = harita_ciktisini_proje_klasorune_kopyala(source, None, "sondaj")

    assert result["path"] == str(source)
    assert result["target"] is None
    assert not result["copied"]
    assert not (tmp_path / "03_Haritalar").exists()


def test_kaynak_zaten_hedefse_same_file_hatasi_olmaz(tmp_path):
    project_path = tmp_path / "Proje.json"
    project_path.write_text("{}", encoding="utf-8")
    target = tmp_path / "03_Haritalar" / "Sondaj_Lokasyon.jpg"
    target.parent.mkdir()
    target.write_bytes(b"harita")

    result = harita_ciktisini_proje_klasorune_kopyala(target, project_path, "sondaj")

    assert result["path"] == str(target)
    assert not result["copied"]
    assert result["error"] is None


def test_kopyalama_hatasi_kaynak_yolu_korur(tmp_path):
    source = tmp_path / "harita.jpg"
    source.write_bytes(b"harita")
    project_path = tmp_path / "Proje.json"
    project_path.write_text("{}", encoding="utf-8")
    maps_as_file = tmp_path / "03_Haritalar"
    maps_as_file.write_bytes(b"klasor degil")

    result = harita_ciktisini_proje_klasorune_kopyala(source, project_path, "sondaj")

    assert result["path"] == str(source)
    assert not result["copied"]
    assert result["error"]
    assert source.read_bytes() == b"harita"


def test_harita_word_aktar_nesne_json_ve_meta_yollarini_gunceller(tmp_path):
    project_path = tmp_path / "Ornek Proje.json"
    project_path.write_text("{}", encoding="utf-8")
    source_dir = tmp_path / "appdata"
    source_dir.mkdir()
    sondaj_source = source_dir / "sondaj.jpg"
    jeofizik_source = source_dir / "jeofizik.jpg"
    sondaj_source.write_bytes(b"sondaj")
    jeofizik_source.write_bytes(b"jeofizik")

    class Harness(HaritalarSekmesiMixin):
        pass

    app = Harness()
    app.aktif_dosya_yolu = str(project_path)
    app.word_img_sondaj = None
    app.word_img_jeofizik = None
    app.veri = {
        "ayarlar": {"harita_katmanlari": harita_katman_ayarlari()},
        "dosyalar": {},
        "sondaj": [],
        "jeofizik": {"ss_list": [], "mt_list": []},
        "jeoloji": {},
        "kunye": {},
        "harita_cizimleri": {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}},
    }
    status_messages = []
    app.harita_durum_yenile = lambda: None
    app.veri_kaydet = lambda: True
    app.set_status = lambda message, **_kwargs: status_messages.append(message)
    app._harita_toplu_adim_bitti = lambda *_args, **_kwargs: None

    HaritalarSekmesiMixin.harita_word_aktar(
        app,
        str(sondaj_source),
        str(jeofizik_source),
    )

    sondaj_target = str(tmp_path / "03_Haritalar" / "Sondaj_Lokasyon.jpg")
    jeofizik_target = str(tmp_path / "03_Haritalar" / "Jeofizik_Lokasyon.jpg")
    assert app.word_img_sondaj == sondaj_target
    assert app.word_img_jeofizik == jeofizik_target
    assert app.veri["dosyalar"]["word_img_sondaj"] == sondaj_target
    assert app.veri["dosyalar"]["word_img_jeofizik"] == jeofizik_target
    assert app.veri["harita_cikti_meta"]["sondaj"]["path"] == sondaj_target
    assert app.veri["harita_cikti_meta"]["jeofizik"]["path"] == jeofizik_target
    assert not any("uyarı" in message.lower() for message in status_messages)
