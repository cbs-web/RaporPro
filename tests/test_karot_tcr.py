# Dosya: RaporPro/tests/test_karot_tcr.py

import copy
import json
import os
import tempfile
import unittest

from karot_aktarim_motoru import (
    KarotAktarimHatasi,
    karot_aktarim_plani_olustur,
    karot_aktarim_plani_uygula,
    karot_aktarimini_geri_al,
)
from karot_gorunum import gorunum_kaydir, gorunum_yakinlastir, tam_gorunum
from karot_motoru import (
    KarotKalibrasyonHatasi,
    derinlik_araligi_coz,
    homografi_hesapla,
    karot_araliklarini_dogrula,
    karot_kalite_hesapla,
    standart_karot_araliklari,
    tcr_hesapla,
)
from karot_oturum_motoru import (
    KAROT_OTURUM_ANAHTARI,
    karot_oturumu_olustur,
    karot_oturumunu_coz,
    karot_oturumunu_kaydet,
    kaynak_icin_karot_oturumu,
    son_karot_oturumu,
)


TOP_LINE = [(0, 0), (100, 0)]
BOTTOM_LINE = [(0, 100), (100, 100)]


class KarotHesapMotoruTestleri(unittest.TestCase):
    def test_ideal_tcr_hesabi_geriye_donuk_sonuclari_korur(self):
        result = tcr_hesapla(
            10.5,
            13.5,
            [((0, 20), (100, 20)), ((0, 50), (50, 50))],
            TOP_LINE,
            BOTTOM_LINE,
        )
        self.assertTrue(result["gecerli"])
        self.assertAlmostEqual(result["karot"], 1.5)
        self.assertAlmostEqual(result["tcr"], 50.0)
        self.assertEqual(result["hatalar"], [])

    def test_cakisan_kalibrasyon_reddedilir(self):
        with self.assertRaises(KarotKalibrasyonHatasi):
            homografi_hesapla(
                [(0, 0), (100, 100)],
                [(0, 100), (100, 0)],
            )

    def test_cokmus_kalibrasyon_reddedilir(self):
        with self.assertRaises(KarotKalibrasyonHatasi):
            homografi_hesapla(TOP_LINE, TOP_LINE)

    def test_tekrar_parca_tcr_degerini_sisirmez_ve_hata_verir(self):
        result = tcr_hesapla(
            0,
            1.5,
            [((0, 20), (100, 20)), ((0, 20), (100, 20))],
            TOP_LINE,
            BOTTOM_LINE,
        )
        self.assertFalse(result["gecerli"])
        self.assertAlmostEqual(result["karot"], 1.0)
        self.assertAlmostEqual(result["ham_karot"], 2.0)
        self.assertGreater(result["ham_tcr"], 100)
        self.assertTrue(any("tekrari" in text for text in result["hatalar"]))

    def test_kalibrasyon_disina_tasan_parca_aktarilabilir_sayilmaz(self):
        result = tcr_hesapla(
            0,
            1.5,
            [((-50, 20), (150, 20))],
            TOP_LINE,
            BOTTOM_LINE,
        )
        self.assertFalse(result["gecerli"])
        self.assertEqual(result["tcr"], 100.0)
        self.assertGreater(result["ham_tcr"], 100)
        self.assertTrue(any("disina" in text for text in result["hatalar"]))

    def test_derinlik_cozucu_negatif_degeri_gizlemez(self):
        self.assertEqual(derinlik_araligi_coz("-1.5-3.0"), (-1.5, 3.0))
        self.assertEqual(
            derinlik_araligi_coz("D: 12.0 m - 13.5 m"),
            (12.0, 13.5),
        )

    def test_aralik_kontrolu_negatif_cakisma_ve_sondaj_sinirini_bulur(self):
        report = karot_araliklarini_dogrula(
            [
                {"top": -1.5, "bot": 1.5},
                {"top": 1.0, "bot": 3.0},
                {"top": 3.0, "bot": 4.5},
            ],
            total_depth=4.0,
        )
        codes = {item["kod"] for item in report["hatalar"]}
        self.assertFalse(report["gecerli"])
        self.assertIn("negatif_derinlik", codes)
        self.assertIn("cakisan_aralik", codes)
        self.assertIn("sondaj_disinda", codes)

    def test_sifir_sablon_adimi_reddedilir(self):
        with self.assertRaises(ValueError):
            standart_karot_araliklari(step=0)

    def test_scr_ve_rqd_saglam_parcalardan_otomatik_hesaplanir(self):
        result = karot_kalite_hesapla(
            0,
            1.5,
            [
                ((0, 20), (100, 20)),
                ((0, 60), (50, 60)),
            ],
            [
                ((0, 20), (60, 20)),
                ((0, 60), (8, 60)),
                ((10, 60), (40, 60)),
            ],
            TOP_LINE,
            BOTTOM_LINE,
            quality_assessed=True,
        )
        self.assertTrue(result["gecerli"])
        self.assertAlmostEqual(result["tcr"], 100.0)
        self.assertAlmostEqual(result["scr"], (0.98 / 1.5) * 100.0)
        self.assertAlmostEqual(result["rqd"], 60.0)
        self.assertEqual(result["saglam_parca_sayisi"], 3)
        self.assertEqual(result["rqd_parca_sayisi"], 2)

    def test_olculmeyen_scr_rqd_bos_kalir_sifir_sayilmaz(self):
        result = karot_kalite_hesapla(
            0,
            1.5,
            [((0, 20), (75, 20))],
            [],
            TOP_LINE,
            BOTTOM_LINE,
        )
        self.assertTrue(result["gecerli"])
        self.assertTrue(result["kalite_bekliyor"])
        self.assertIsNone(result["scr"])
        self.assertIsNone(result["rqd"])

    def test_scr_tcr_degerini_asamaz(self):
        result = karot_kalite_hesapla(
            0,
            1.5,
            [((0, 20), (50, 20))],
            [((0, 20), (80, 20))],
            TOP_LINE,
            BOTTOM_LINE,
            quality_assessed=True,
        )
        self.assertFalse(result["gecerli"])
        self.assertTrue(
            any("toplam geri kazanilan" in text for text in result["hatalar"])
        )

    def test_rqd_on_santimetrelik_parcayi_dahil_eder(self):
        result = karot_kalite_hesapla(
            0,
            1.0,
            [((0, 20), (100, 20))],
            [((0, 20), (10, 20))],
            TOP_LINE,
            BOTTOM_LINE,
            quality_assessed=True,
        )
        self.assertAlmostEqual(result["scr"], 10.0)
        self.assertAlmostEqual(result["rqd"], 10.0)
        self.assertEqual(result["rqd_parca_sayisi"], 1)


class KarotGorunumTestleri(unittest.TestCase):
    def test_tam_gorunum_matplotlib_resim_sinirlarini_kullanir(self):
        self.assertEqual(
            tam_gorunum((100, 200)),
            ((-0.5, 99.5), (199.5, -0.5)),
        )

    def test_yakinlastirma_fare_konumunu_sabit_tutar(self):
        xlim, ylim = tam_gorunum((100, 200))
        center = (25.0, 75.0)
        zoomed_x, zoomed_y = gorunum_yakinlastir(
            xlim,
            ylim,
            0.5,
            center,
            (100, 200),
        )
        old_x_ratio = (center[0] - xlim[0]) / (xlim[1] - xlim[0])
        new_x_ratio = (center[0] - zoomed_x[0]) / (zoomed_x[1] - zoomed_x[0])
        old_y_ratio = (center[1] - ylim[0]) / (ylim[1] - ylim[0])
        new_y_ratio = (center[1] - zoomed_y[0]) / (zoomed_y[1] - zoomed_y[0])
        self.assertAlmostEqual(old_x_ratio, new_x_ratio)
        self.assertAlmostEqual(old_y_ratio, new_y_ratio)
        self.assertAlmostEqual(abs(zoomed_x[1] - zoomed_x[0]), 50.0)
        self.assertAlmostEqual(abs(zoomed_y[1] - zoomed_y[0]), 100.0)

    def test_tam_gorunumden_daha_fazla_uzaklastirilamaz(self):
        limits = tam_gorunum((100, 200))
        self.assertEqual(
            gorunum_yakinlastir(
                limits[0],
                limits[1],
                1.25,
                (50, 100),
                (100, 200),
            ),
            limits,
        )

    def test_kaydirma_eksen_yonlerini_korur(self):
        xlim, ylim = tam_gorunum((100, 200))
        moved_x, moved_y = gorunum_kaydir(
            xlim,
            ylim,
            (100, 100),
            (1000, 500),
        )
        self.assertEqual(moved_x, (-10.5, 89.5))
        self.assertEqual(moved_y, (239.5, 39.5))


class KarotAktarimMotoruTestleri(unittest.TestCase):
    def test_plan_mevcut_scr_rqd_degerlerini_korur_ve_atomik_uygulanir(self):
        sondaj = {
            "no": "SK-1",
            "kaya": [["12.0-13.5", "40", "35", "20"]],
        }
        original = copy.deepcopy(sondaj)
        plan = karot_aktarim_plani_olustur(
            sondaj,
            [
                {"top": 12.0, "bot": 13.5, "tcr": 55, "gecerli": True},
                {"top": 13.5, "bot": 15.0, "tcr": 60, "gecerli": True},
            ],
        )
        self.assertEqual(sondaj, original)
        self.assertEqual(plan["eklenen"], 1)
        self.assertEqual(plan["guncellenen"], 1)

        karot_aktarim_plani_uygula(sondaj, plan)
        self.assertEqual(sondaj["kaya"][0], ["12.0-13.5", "55", "35", "20"])
        self.assertEqual(sondaj["kaya"][1], ["13.50-15.00", "60", "", ""])

        karot_aktarimini_geri_al(sondaj, plan)
        self.assertEqual(sondaj, original)

    def test_gecersiz_sonuc_plan_uretemez_ve_veriyi_degistirmez(self):
        sondaj = {"no": "SK-1", "kaya": [["1.50-3.00", "50", "", ""]]}
        original = copy.deepcopy(sondaj)
        with self.assertRaises(KarotAktarimHatasi):
            karot_aktarim_plani_olustur(
                sondaj,
                [
                    {
                        "top": 1.5,
                        "bot": 3.0,
                        "tcr": 100,
                        "gecerli": False,
                        "hatalar": ["Kalibrasyon disi parca"],
                    }
                ],
            )
        self.assertEqual(sondaj, original)

    def test_scr_ve_rqd_birlikte_kaya_tablosuna_aktarilir(self):
        sondaj = {
            "no": "SK-1",
            "kaya": [["12.0-13.5", "40", "35", "20"]],
        }
        plan = karot_aktarim_plani_olustur(
            sondaj,
            [
                {
                    "top": 12.0,
                    "bot": 13.5,
                    "tcr": 80,
                    "scr": 60,
                    "rqd": 45,
                    "gecerli": True,
                }
            ],
        )
        karot_aktarim_plani_uygula(sondaj, plan)
        self.assertEqual(sondaj["kaya"][0], ["12.0-13.5", "80", "60", "45"])
        self.assertEqual(plan["kalite_guncellenen"], 1)


class KarotOturumMotoruTestleri(unittest.TestCase):
    def test_oturum_cozunurlukten_bagimsiz_kaydedilip_yuklenir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "karot.jpg")
            with open(path, "wb") as stream:
                stream.write(b"test-image")

            session = karot_oturumu_olustur(
                path,
                (101, 201),
                [(0, 0), (100, 0)],
                [(0, 200), (100, 200)],
                [
                    {
                        "top": 1.5,
                        "bot": 3.0,
                        "segments": [[(10, 50), (80, 50)]],
                    }
                ],
            )
            restored = karot_oturumunu_coz(session, (201, 401))

        self.assertEqual(restored["top_line"], [[0.0, 0.0], [200.0, 0.0]])
        self.assertEqual(restored["bottom_line"], [[0.0, 400.0], [200.0, 400.0]])
        self.assertEqual(restored["intervals"][0]["segments"][0], [[20.0, 100.0], [160.0, 100.0]])

    def test_ayni_kaynak_oturumu_guncellenir_ve_son_oturum_bulunur(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "karot.jpg")
            with open(path, "wb") as stream:
                stream.write(b"test-image")
            first = karot_oturumu_olustur(path, (100, 100), [], [], [])
            second = karot_oturumu_olustur(
                path,
                (100, 100),
                [(0, 0), (99, 0)],
                [],
                [],
            )
            sondaj = {}
            karot_oturumunu_kaydet(sondaj, first)
            karot_oturumunu_kaydet(sondaj, second)
            json.dumps(sondaj, ensure_ascii=False)
            self.assertEqual(len(sondaj[KAROT_OTURUM_ANAHTARI]), 1)
            self.assertEqual(son_karot_oturumu(sondaj)["ust_cizgi"], second["ust_cizgi"])
            self.assertEqual(
                kaynak_icin_karot_oturumu(sondaj, path)["ust_cizgi"],
                second["ust_cizgi"],
            )

    def test_scr_rqd_isaretleri_kaydedilir_eski_oturumlar_acilir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "karot.jpg")
            with open(path, "wb") as stream:
                stream.write(b"test-image")
            session = karot_oturumu_olustur(
                path,
                (101, 201),
                [(0, 0), (100, 0)],
                [(0, 200), (100, 200)],
                [
                    {
                        "top": 1.5,
                        "bot": 3.0,
                        "segments": [[(10, 50), (80, 50)]],
                        "solid_segments": [[(20, 50), (60, 50)]],
                        "quality_assessed": True,
                    }
                ],
            )
            restored = karot_oturumunu_coz(session, (201, 401))
            legacy = copy.deepcopy(session)
            legacy["surum"] = 1
            legacy["araliklar"][0].pop("solid_segments")
            legacy["araliklar"][0].pop("quality_assessed")
            legacy_restored = karot_oturumunu_coz(legacy, (201, 401))

        self.assertTrue(restored["intervals"][0]["quality_assessed"])
        self.assertEqual(
            restored["intervals"][0]["solid_segments"][0],
            [[40.0, 100.0], [120.0, 100.0]],
        )
        self.assertFalse(legacy_restored["intervals"][0]["quality_assessed"])
        self.assertEqual(legacy_restored["intervals"][0]["solid_segments"], [])


if __name__ == "__main__":
    unittest.main()
