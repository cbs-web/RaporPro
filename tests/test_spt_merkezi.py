# Dosya: RaporPro/tests/test_spt_merkezi.py
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import spt_okuma_motoru as motor
from spt_aktarim_motoru import (
    spt_aktarim_bilinmeyen_sondajlar,
    spt_aktarim_plani_olustur,
)
from spt_gorsel import (
    dogal_siralama_anahtari,
    dosya_parmak_izi,
    gorsel_api_payload_hazirla,
)
from spt_okuma_motoru import (
    SPTKaydi,
    _path_unique_key,
    _select_spt_records_for_batch,
    fotograflardan_spt_oku,
    hedef_derinlige_yuvarla,
    kayit_normalize_et,
)
from spt_saglayicilar import http_post_with_retry
from ui_spt_okuma_yardimci import record_quality
from ui_spt_okuma_kuyruk import SPTFotografKuyrugu


class SPTMerkeziGuvenilirlikTestleri(unittest.TestCase):
    def test_tek_fotograftan_yalnizca_bir_aday_secilir(self):
        path = r"C:\tmp\DSCF0001.JPG"
        records = [
            kayit_normalize_et({
                "sondaj_no": "SK-1",
                "derinlik": "1.50",
                "spt": "2-3-4",
                "guven": "70",
            }),
            kayit_normalize_et({
                "sondaj_no": "SK-1",
                "derinlik": "3.00",
                "spt": "5-6-7",
                "guven": "95",
            }),
        ]

        selected, removed, merged = _select_spt_records_for_batch(
            [(_path_unique_key(path), records)],
            [path],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].derinlik, "3.00")
        self.assertEqual(removed, 1)
        self.assertEqual(merged, 0)
        self.assertEqual(len(selected[0].raw["alternatif_okumalar"]), 1)

    def test_hedef_disindaki_derinlik_sessizce_son_hedefe_dusmez(self):
        self.assertEqual(hedef_derinlige_yuvarla("31.50"), "")
        kayit = kayit_normalize_et({
            "sondaj_no": "SK-1",
            "derinlik": "4.10",
            "spt": "2-3-4",
        })
        self.assertEqual(kayit.derinlik, "4.50")
        self.assertIn("4.10 -> 4.50", kayit.uyari)

    def test_refu_hata_degil_bilgi_seviyesidir(self):
        kayit = kayit_normalize_et({
            "sondaj_no": "SK-1",
            "derinlik": "3.00",
            "v15": "20",
            "v30": "50/10",
            "v45": "-",
        })
        quality = record_quality(
            {"kayit": kayit, "include": True},
            valid_sondaj_nolari={"SK-1"},
            current_sondaj_depth=lambda _no: 15,
            settings={"guven_esigi": 90},
        )
        self.assertEqual(kayit.n30, "R")
        self.assertEqual(quality["level"], "info")
        self.assertIn("Refü", quality["message"])

    def test_projedia_olmayan_sondaj_hata_seviyesidir(self):
        kayit = kayit_normalize_et({
            "sondaj_no": "SK-9",
            "derinlik": "1.50",
            "spt": "2-3-4",
        })
        quality = record_quality(
            {"kayit": kayit, "include": True},
            valid_sondaj_nolari={"SK-1"},
            current_sondaj_depth=lambda _no: 15,
        )
        self.assertEqual(quality["level"], "error")
        self.assertIn("sondaj no projede yok", quality["message"])
        self.assertIn("sondaj_no", quality["fields"])

    def test_eksik_derinlik_ve_darbe_alanlari_hucre_bazinda_isaretlenir(self):
        quality = record_quality(
            {"kayit": SPTKaydi(sondaj_no="SK-1"), "include": True},
            valid_sondaj_nolari={"SK-1"},
            current_sondaj_depth=lambda _no: 15,
        )

        self.assertEqual(quality["level"], "error")
        self.assertIn("derinlik", quality["fields"])
        self.assertTrue({"v15", "v30", "v45", "n30"}.issubset(quality["fields"]))

    def test_dosya_adlari_dogal_sirada_dizilir(self):
        names = ["SPT10.jpg", "SPT2.jpg", "SPT1.jpg"]
        self.assertEqual(
            sorted(names, key=dogal_siralama_anahtari),
            ["SPT1.jpg", "SPT2.jpg", "SPT10.jpg"],
        )

    def test_ayni_icerigin_farkli_adlari_ayni_parmak_izini_verir(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "bir.jpg"
            second = Path(tmp) / "iki.jpg"
            first.write_bytes(b"ayni-fotograf-icerigi")
            second.write_bytes(b"ayni-fotograf-icerigi")
            self.assertEqual(dosya_parmak_izi(first), dosya_parmak_izi(second))

    def test_kuyruk_ayni_icerigi_ikinci_kez_eklemez(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "SPT10.jpg"
            second = Path(tmp) / "SPT2.jpg"
            third = Path(tmp) / "SPT1.jpg"
            first.write_bytes(b"on")
            second.write_bytes(b"iki")
            third.write_bytes(b"iki")
            queue = SPTFotografKuyrugu()

            added, skipped, found = queue.add_sources([tmp])

        self.assertEqual(found, 3)
        self.assertEqual(len(added), 2)
        self.assertEqual(skipped, 1)
        self.assertEqual([Path(path).name for path in queue.paths], ["SPT1.jpg", "SPT10.jpg"])

    def test_api_gorseli_exif_uyumlu_ve_kucultulmus_hazirlanir(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "buyuk.bmp"
            Image.new("RGB", (3200, 1200), "white").save(path)

            payload, mime_type, metadata = gorsel_api_payload_hazirla(path)

        self.assertTrue(payload)
        self.assertEqual(mime_type, "image/jpeg")
        self.assertEqual(metadata["orijinal_boyut"], "3200x1200")
        self.assertEqual(metadata["islenmis_boyut"], "2048x768")
        self.assertLess(metadata["islenmis_bayt"], metadata["orijinal_bayt"])

    def test_tanimsiz_sondaj_acik_izin_olmadan_olusturulmaz(self):
        veri = {"sondaj": [{"no": "SK-1", "spt": []}]}
        original = deepcopy(veri)
        kayit = SPTKaydi(
            sondaj_no="SK-9",
            derinlik="1.50",
            v15="2",
            v30="3",
            v45="4",
            n30="7",
        )

        self.assertEqual(spt_aktarim_bilinmeyen_sondajlar(veri, [kayit]), ["SK-9"])
        plan = spt_aktarim_plani_olustur(veri, [kayit], eksik_sondaj_olustur=False)

        self.assertEqual(veri, original)
        self.assertEqual(len(plan["sondajlar"]), 1)
        self.assertEqual(plan["stats"]["skipped"], 1)

    def test_aktarim_plani_once_temizlemeyi_kopyada_yapar(self):
        veri = {
            "sondaj": [{
                "no": "SK-1",
                "spt": [["1.50", "1", "2", "3", "5"]],
                "spt_kaynaklari": [{"derinlik": "1.50", "kaynak": "eski"}],
            }]
        }
        original = deepcopy(veri)
        kayit = SPTKaydi(
            sondaj_no="SK-1",
            derinlik="3.00",
            v15="4",
            v30="5",
            v45="6",
            n30="11",
        )

        plan = spt_aktarim_plani_olustur(
            veri,
            [kayit],
            once_temizle=True,
        )

        self.assertEqual(veri, original)
        self.assertEqual(plan["sondajlar"][0]["spt"], [["3.00", "4", "5", "6", "11"]])
        self.assertEqual(len(plan["sondajlar"][0]["spt_kaynaklari"]), 1)

    def test_auto_pro_bos_donerse_ilk_gecerli_sonuc_korunur(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SK-1_test.jpg")
            Path(path).write_bytes(b"test")
            first = [{
                "sondaj_no": "SK-1",
                "derinlik": "1.50",
                "spt": "2-3-4",
                "guven": 60,
                "_motor": "openai",
            }]
            with patch.object(
                motor,
                "yapay_zeka_ile_spt_oku",
                side_effect=[first, []],
            ) as reader:
                result = fotograflardan_spt_oku(
                    [path],
                    ayarlar={
                        "aktif_motor": "openai",
                        "gemini_api_key": "test",
                    },
                    auto_pro=True,
                    guven_esigi=80,
                )

        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(result.kayitlar), 1)
        self.assertEqual(result.kayitlar[0].n30, "7")
        self.assertTrue(result.kayitlar[0].raw["_pro_sonucu_kullanilmadi"])

    def test_auto_pro_proje_guven_esigine_uyar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SK-1_test.jpg")
            Path(path).write_bytes(b"test")
            first = [{
                "sondaj_no": "SK-1",
                "derinlik": "1.50",
                "spt": "2-3-4",
                "guven": 60,
            }]
            with patch.object(
                motor,
                "yapay_zeka_ile_spt_oku",
                return_value=first,
            ) as reader:
                result = fotograflardan_spt_oku(
                    [path],
                    ayarlar={
                        "aktif_motor": "openai",
                        "gemini_api_key": "test",
                    },
                    auto_pro=True,
                    guven_esigi=50,
                )

        self.assertEqual(reader.call_count, 1)
        self.assertEqual(result.kayitlar[0].n30, "7")

    def test_auto_pro_ilk_motor_bosken_tekrar_dener(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SK-1_test.jpg")
            Path(path).write_bytes(b"test")
            pro = [{
                "sondaj_no": "SK-1",
                "derinlik": "1.50",
                "spt": "2-3-4",
                "guven": 95,
                "_motor": "gemini_pro",
            }]
            with patch.object(
                motor,
                "yapay_zeka_ile_spt_oku",
                side_effect=[[], pro],
            ) as reader:
                result = fotograflardan_spt_oku(
                    [path],
                    ayarlar={
                        "aktif_motor": "openai",
                        "gemini_api_key": "test",
                    },
                    auto_pro=True,
                    guven_esigi=80,
                )

        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(result.kayitlar), 1)
        self.assertEqual(result.kayitlar[0].n30, "7")

    def test_gecici_api_hatasi_yeniden_denenir(self):
        class Response:
            def __init__(self, status):
                self.status_code = status
                self.headers = {}

        class Requests:
            def __init__(self):
                self.responses = [Response(429), Response(200)]

            def post(self, *_args, **_kwargs):
                return self.responses.pop(0)

        requests_module = Requests()
        with patch("spt_saglayicilar.time.sleep"):
            response = http_post_with_retry(
                requests_module,
                "https://example.test",
                headers={},
                payload={},
                timeout=1,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(requests_module.responses, [])

    def test_ogretilen_ayni_fotograf_icin_yerel_dogru_bulunur(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "foto.jpg"
            image_path.write_bytes(b"ogrenilecek-fotograf")
            learning_dir = Path(tmp) / "learning"
            log_dir = Path(tmp) / "logs"
            history_path = log_dir / "history.jsonl"
            kayit = SPTKaydi(
                sondaj_no="SK-1",
                derinlik="1.50",
                v15="2",
                v30="3",
                v45="4",
                n30="7",
                kaynak_yolu=str(image_path),
            )
            with (
                patch.object(motor, "SPT_OGRENME_DIR", learning_dir),
                patch.object(motor, "SPT_LOG_DIR", log_dir),
                patch.object(motor, "SPT_GECMIS_PATH", history_path),
            ):
                motor.spt_ogrenme_kaydet(
                    kayit,
                    {"sondaj_no": "SK-1", "derinlik": "1.50", "spt": "2-3-4"},
                )
                learned = motor.spt_ogrenme_eslesmesi_bul(str(image_path))
                with patch.object(motor, "yapay_zeka_ile_spt_oku") as reader:
                    result = motor.fotograflardan_spt_oku(
                        [str(image_path)],
                        ayarlar={"aktif_motor": "openai"},
                    )

        self.assertIsNotNone(learned)
        self.assertEqual(learned["spt"], "2-3-4")
        reader.assert_not_called()
        self.assertEqual(result.kayitlar[0].raw["motor"], "yerel_ogrenme")


if __name__ == "__main__":
    unittest.main()
