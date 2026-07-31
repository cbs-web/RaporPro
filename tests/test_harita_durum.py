# Dosya: RaporPro/tests/test_harita_durum.py
import datetime
import os

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from harita_durum import (
    harita_cikti_durumu,
    harita_cikti_meta_olustur,
    harita_formasyon_kodu,
    harita_katman_ayarlari,
)
from harita_etiket import harita_etiketlerini_ayir


def _proje_verisi():
    return {
        "ayarlar": {
            "harita_altlik": "Google Uydu",
            "harita_katmanlari": harita_katman_ayarlari(),
        },
        "dosyalar": {"kml_path": None},
        "sondaj": [{"no": "SK-1", "x": "26.1", "y": "40.1"}],
        "jeofizik": {"ss_list": [], "mt_list": []},
        "jeoloji": {},
        "kunye": {},
        "harita_cizimleri": {"vaziyet": {}, "jeoloji": {}, "yerbuldurur": {}},
    }


def test_harita_katman_ayarlari_eski_kaydi_tamamlar():
    layers = harita_katman_ayarlari({"sondaj": False, "etiketler": False})

    assert layers["sondaj"] is False
    assert layers["etiketler"] is False
    assert layers["ss"] is True
    assert layers["mt"] is True
    assert layers["otomatik_etiket"] is True


def test_harita_formasyonu_proje_ayarindan_alinir():
    veri = _proje_verisi()
    veri["ayarlar"]["harita_formasyon"] = "Tmal"
    veri["harita_cizimleri"]["jeoloji"] = {"formasyon": "Tmçd"}

    assert harita_formasyon_kodu(veri) == "Tmal"


def test_eski_projenin_formasyonu_kayitli_jeoloji_ciziminden_kurtarilir():
    veri = _proje_verisi()
    veri["harita_cizimleri"]["jeoloji"] = {"formasyon": "Tmçd"}

    assert harita_formasyon_kodu(veri) == "Tmçd"


def test_formasyon_ayari_yoksa_proje_jeolojik_birimi_kullanilir():
    veri = _proje_verisi()
    veri["jeoloji"] = {
        "birimler": [
            {
                "kod": "Tmki",
                "konum": "inceleme_alani",
                "durum": "belirtilmedi",
                "aktif": True,
            }
        ]
    }

    assert harita_formasyon_kodu(veri) == "Tmki"


def test_harita_ciktisi_kaynak_degistiginde_eski_olur(tmp_path):
    path = tmp_path / "sondaj.jpg"
    path.write_bytes(b"harita")
    veri = _proje_verisi()
    meta = harita_cikti_meta_olustur(
        veri,
        "sondaj",
        path,
        now=datetime.datetime(2026, 7, 30, 14, 15),
    )

    state, text = harita_cikti_durumu(veri, "sondaj", path, meta)
    assert state == "ok"
    assert "30.07.2026 14:15" in text

    veri["jeofizik"]["mt_list"].append({"no": "MT-1", "x": "26.4", "y": "40.4"})
    state, _text = harita_cikti_durumu(veri, "sondaj", path, meta)
    assert state == "ok"

    veri["sondaj"][0]["x"] = "26.2"
    state, text = harita_cikti_durumu(veri, "sondaj", path, meta)
    assert state == "stale"
    assert text.startswith("Eski çıktı")


def test_eski_projeden_gelen_cikti_dosya_tarihiyle_hazir_sayilir(tmp_path):
    path = tmp_path / "mjh.jpg"
    path.write_bytes(b"harita")
    os.utime(path, (1_700_000_000, 1_700_000_000))

    state, text = harita_cikti_durumu(_proje_verisi(), "mjh", path, None)

    assert state == "ok"
    assert text.startswith("Hazır")


def test_harita_etiketleri_ayni_noktada_birakilmaz():
    fig = Figure(figsize=(5, 4), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    first = ax.text(0.5, 0.5, "SK-1", fontsize=12)
    second = ax.text(0.5, 0.5, "SK-2", fontsize=12)

    moved = harita_etiketlerini_ayir(fig, ax, [first, second])

    assert moved >= 1
    assert first.get_position() != second.get_position()
