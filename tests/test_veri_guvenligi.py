import copy
import json
from unittest import mock

import pytest

import arayuz
from arayuz import RaporRobotuArayuz
from arayuz_proje import ArayuzProjeMixin
from proje_sema import (
    PROJE_SEMA_SURUMU,
    ProjeSemaHatasi,
    proje_verisini_migre_et,
    varsayilan_proje_verisi,
)
from tutarlilik_motoru import proje_tutarlilik_raporu
from tutarlilik_ortak import sayi_veya_none
from ui_sondaj import SondajMixin
from yardimcilar import atomic_json_dump, safe_float


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", float("nan"), float("inf")])
def test_sayisal_yardimcilar_sonlu_olmayan_degerleri_reddeder(value):
    assert sayi_veya_none(value) is None
    assert safe_float(value) == 0.0


def test_atomic_json_dump_nan_hatasinda_mevcut_dosyayi_korur(tmp_path):
    target = tmp_path / "proje.json"
    target.write_text('{"guvenli": true}', encoding="utf-8")

    with pytest.raises(ValueError):
        atomic_json_dump({"deger": float("nan")}, target)

    assert target.read_text(encoding="utf-8") == '{"guvenli": true}'


def test_guncel_sema_bozuk_cekirdek_tipleri_onarir():
    veri = varsayilan_proje_verisi()
    veri["schema_version"] = PROJE_SEMA_SURUMU
    veri["sondaj"] = {"beklenmeyen": "nesne"}
    veri["lab_sheet"] = "bozuk"
    veri["jeofizik"]["ss_list"] = "bozuk"

    sonuc, bilgi = proje_verisini_migre_et(veri)

    assert sonuc["sondaj"] == []
    assert sonuc["lab_sheet"] == {"rows": []}
    assert sonuc["jeofizik"]["ss_list"] == []
    assert bilgi.degisti
    assert any("cekirdek proje alani" in not_ for not_ in bilgi.notlar)


def test_sema_bozuk_sondaj_ogesini_ve_nan_degerini_acikca_reddeder():
    bozuk_sondaj = varsayilan_proje_verisi()
    bozuk_sondaj["sondaj"] = [None]
    with pytest.raises(ProjeSemaHatasi, match=r"sondaj\[0\]"):
        proje_verisini_migre_et(bozuk_sondaj)

    nan_veri = varsayilan_proje_verisi()
    nan_veri["bina"]["der"] = float("nan")
    with pytest.raises(ProjeSemaHatasi, match="sonlu olmayan"):
        proje_verisini_migre_et(nan_veri)


def test_varsayilan_proje_fabrikasi_kanonik_ve_bagimsizdir():
    birinci = varsayilan_proje_verisi()
    ikinci = varsayilan_proje_verisi()
    mixin_verisi = ArayuzProjeMixin().varsayilan_veri_olustur()

    assert birinci == ikinci == mixin_verisi
    birinci["kunye"]["sahibi"] = "Değişti"
    assert ikinci["kunye"]["sahibi"] == ""


@pytest.mark.parametrize("value", ["abc", "nan", "inf", "-1"])
def test_yass_canli_dogrulama_gecersiz_degeri_hata_sayar(value):
    state, _message = SondajMixin().sondaj_hucre_durumu("yass_d1", value, True)
    assert state == "error"


def test_yass_merkezi_dogrulama_bos_olmayan_gecersiz_sayiyi_bildirir():
    veri = varsayilan_proje_verisi()
    veri["sondaj"] = [{
        "no": "SK-1",
        "der": "15",
        "y": "40.0",
        "x": "29.0",
        "k": "100",
        "yass_d1": "abc",
        "yass_d2": "",
        "litoloji": [],
        "spt": [],
        "pmt": [],
        "kaya": [],
        "numuneler": [],
    }]

    rapor = proje_tutarlilik_raporu(veri)

    assert any(
        bulgu.get("field") == "yass_d1" and "geçerli bir sayı değil" in bulgu.get("detail", "")
        for bulgu in rapor["findings"]
    )


def test_proje_ui_uygulama_hatasinda_eski_duruma_doner():
    app = ArayuzProjeMixin()
    eski_veri = {"kunye": {"sahibi": "Eski"}}
    app.veri = eski_veri
    app.aktif_dosya_yolu = "eski.json"
    app._son_kayit_imzasi = "eski-imza"
    app.last_preflight_report = {"eski": True}
    app.last_preflight_fingerprint = "parmak-izi"
    app.last_output_quality_report = {"kalite": True}
    app.doldur_arayuz = mock.Mock(side_effect=[RuntimeError("UI uygulanamadı"), None])
    app.proje_baslik_guncelle = mock.Mock()

    with pytest.raises(RuntimeError, match="UI uygulanamadı"):
        app._proje_durumunu_uygula(
            {"kunye": {"sahibi": "Yeni"}},
            "yeni.json",
            kaydedilmemis=True,
        )

    assert app.veri is eski_veri
    assert app.aktif_dosya_yolu == "eski.json"
    assert app._son_kayit_imzasi == "eski-imza"
    assert app.last_preflight_report == {"eski": True}
    assert app.last_preflight_fingerprint == "parmak-izi"
    assert app.last_output_quality_report == {"kalite": True}
    assert app.doldur_arayuz.call_count == 2


def _kilit_test_uygulamasi(*, kilitli, save_result):
    app = ArayuzProjeMixin()
    app.veri = varsayilan_proje_verisi()
    app.veri["proje_durumu"].update({
        "tamamlandi": kilitli,
        "kilitli": kilitli,
        "tamamlanma_tarihi": "2026-01-01T10:00:00" if kilitli else "",
    })
    app.aktif_dosya_yolu = "proje.json"
    app.guncelle_veri_objesi = mock.Mock()
    app.veri_kaydet = mock.Mock(return_value=save_result)
    app.proje_baslik_guncelle = mock.Mock()
    app.set_save_indicator = mock.Mock()
    app.set_status = mock.Mock()
    return app


def test_kilitleme_kayit_basarisizsa_durumu_geri_alir_ve_arsive_dokunmaz():
    app = _kilit_test_uygulamasi(kilitli=False, save_result=False)
    onceki_durum = copy.deepcopy(app.veri["proje_durumu"])

    with (
        mock.patch("arayuz_proje.proje_merkez_koordinati", return_value=(None, None)),
        mock.patch("arayuz_proje.arsiv_kaydi_ekle") as arsiv_ekle,
        mock.patch("arayuz_proje.messagebox.showerror"),
    ):
        sonuc = app.proje_tamamlandi_kilitle()

    assert sonuc is False
    assert app.veri["proje_durumu"] == onceki_durum
    arsiv_ekle.assert_not_called()


def test_kilit_acma_kayit_basarisizsa_durumu_geri_alir_ve_arsive_dokunmaz():
    app = _kilit_test_uygulamasi(kilitli=True, save_result=False)
    onceki_durum = copy.deepcopy(app.veri["proje_durumu"])

    with (
        mock.patch("arayuz_proje.messagebox.askyesno", return_value=True),
        mock.patch("arayuz_proje.messagebox.showerror"),
        mock.patch("arayuz_proje.arsiv_kaydi_sil") as arsiv_sil,
    ):
        sonuc = app.proje_kilidini_kaldir()

    assert sonuc is False
    assert app.veri["proje_durumu"] == onceki_durum
    arsiv_sil.assert_not_called()


def test_kilitleme_arsivi_ancak_disk_kaydindan_sonra_degistirir():
    app = _kilit_test_uygulamasi(kilitli=False, save_result=True)
    olaylar = []
    app.veri_kaydet = mock.Mock(side_effect=lambda: olaylar.append("disk") or True)

    with (
        mock.patch("arayuz_proje.proje_merkez_koordinati", return_value=(40.0, 29.0)),
        mock.patch("arayuz_proje.arsiv_kaydi_ekle", side_effect=lambda *_args, **_kwargs: olaylar.append("arsiv")),
        mock.patch("arayuz_proje.messagebox.showinfo"),
    ):
        sonuc = app.proje_tamamlandi_kilitle()

    assert sonuc is True
    assert olaylar == ["disk", "arsiv"]


def _autosave_test_uygulamasi():
    app = RaporRobotuArayuz.__new__(RaporRobotuArayuz)
    app._autosave_session_id = "yeni-oturum"
    app._autosave_project_token = "yeni-proje"
    app._autosave_recovery_pending = False
    app._autosave_recovered = False
    app._closing = False
    app.aktif_dosya_yolu = None
    app.veri = varsayilan_proje_verisi()
    app.set_status = mock.Mock()
    app.set_save_indicator = mock.Mock()
    app.proje_kilitli_mi = mock.Mock(return_value=False)
    return app


def test_kurtarma_karari_ertelenirse_autosave_uzerine_yazmaz(tmp_path):
    autosave_path = tmp_path / "autosave.json"
    eski_payload = {
        "session_id": "eski-oturum",
        "project_key": "unsaved:eski-proje",
        "saved_at": "2026-07-29T10:00:00",
        "active_path": None,
        "veri": varsayilan_proje_verisi(),
    }
    autosave_path.write_text(json.dumps(eski_payload, ensure_ascii=False), encoding="utf-8")
    onceki_icerik = autosave_path.read_text(encoding="utf-8")
    app = _autosave_test_uygulamasi()

    with (
        mock.patch.object(arayuz, "AUTOSAVE_PATH", str(autosave_path)),
        mock.patch.object(arayuz, "AUTOSAVE_DIR", str(tmp_path)),
        mock.patch("arayuz.messagebox.askyesnocancel", return_value=None),
    ):
        assert app.kurtarma_durumu_bildir() is False
        assert app.otomatik_kaydet() is False

    assert app._autosave_recovery_pending is True
    assert autosave_path.read_text(encoding="utf-8") == onceki_icerik


def test_autosave_restore_ui_hatasinda_eski_projeyi_korur(tmp_path):
    autosave_path = tmp_path / "autosave.json"
    payload = {
        "session_id": "eski-oturum",
        "saved_at": "2026-07-29T10:00:00",
        "active_path": "kurtarilan.json",
        "veri": varsayilan_proje_verisi(),
    }
    autosave_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    app = _autosave_test_uygulamasi()
    eski_veri = app.veri
    app.aktif_dosya_yolu = "eski.json"
    app._son_kayit_imzasi = "eski-imza"
    app.last_preflight_report = {"eski": True}
    app.last_preflight_fingerprint = "eski"
    app.last_output_quality_report = {"eski": True}
    app.doldur_arayuz = mock.Mock(side_effect=[RuntimeError("UI uygulanamadı"), None])
    app.proje_baslik_guncelle = mock.Mock()
    app.proje_kilit_durumunu_goster = mock.Mock()

    with (
        mock.patch.object(arayuz, "AUTOSAVE_PATH", str(autosave_path)),
        mock.patch("arayuz.messagebox.showerror"),
    ):
        sonuc = app.otomatik_kayit_yukle()

    assert sonuc is False
    assert app.veri is eski_veri
    assert app.aktif_dosya_yolu == "eski.json"
    assert app._son_kayit_imzasi == "eski-imza"
    assert autosave_path.exists()


def test_sahipli_autosave_temiz_kayit_yasam_dongusunde_silinir(tmp_path):
    autosave_path = tmp_path / "autosave.json"
    autosave_path.write_text(
        json.dumps({"session_id": "yeni-oturum", "veri": varsayilan_proje_verisi()}),
        encoding="utf-8",
    )
    app = _autosave_test_uygulamasi()

    with mock.patch.object(arayuz, "AUTOSAVE_PATH", str(autosave_path)):
        assert app.otomatik_kayit_temizle() is True

    assert not autosave_path.exists()
