# Dosya: RaporPro/tests/test_hidrojeoloji_cevre.py
import os
import tempfile
import unittest

from hidrojeoloji_cevre import (
    cevre_analizi_guncel_mi,
    cevre_analizi_kayit_ozeti,
    cevre_analizi_yap,
    geometri_en_kisa_mesafe,
    kml_halkalarini_oku,
    overpass_elemanlarini_ayikla,
    su_yolu_turunu_belirle,
)


KML_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Placemark>
    <Polygon>
      <outerBoundaryIs>
        <LinearRing>
          <coordinates>
            26.0000,40.0000,0 26.0010,40.0000,0
            26.0010,40.0010,0 26.0000,40.0010,0 26.0000,40.0000,0
          </coordinates>
        </LinearRing>
      </outerBoundaryIs>
    </Polygon>
  </Placemark>
</kml>
"""


class _FakeProvider:
    kaynak_adi = "Test hidrografya"
    kaynak_turu = "Test"

    def kiyi_cizgileri(self, _lat, _lon, task_context=None):
        return [
            {
                "id": "coast-1",
                "ad": "",
                "etiketler": {"natural": "coastline"},
                "noktalar": [(39.9900, 26.0100), (40.0100, 26.0100)],
            }
        ], 25_000

    def su_yollari(self, _lat, _lon, _radius_m, task_context=None):
        return [
            {
                "id": "way-1",
                "ad": "Test Deresi",
                "etiketler": {"waterway": "stream", "intermittent": "yes"},
                "noktalar": [(40.0020, 25.9990), (40.0020, 26.0020)],
            },
            {
                "id": "way-2",
                "ad": "Uzak Dere",
                "etiketler": {"waterway": "river"},
                "noktalar": [(40.0500, 25.9900), (40.0500, 26.0100)],
            },
        ]


class HidrojeolojiCevreTestleri(unittest.TestCase):
    def setUp(self):
        handle, self.kml_path = tempfile.mkstemp(suffix=".kml")
        os.close(handle)
        with open(self.kml_path, "w", encoding="utf-8") as stream:
            stream.write(KML_TEXT)

    def tearDown(self):
        try:
            os.unlink(self.kml_path)
        except OSError:
            pass

    def test_kml_poligon_halkasi_sirali_okunur(self):
        rings = kml_halkalarini_oku(self.kml_path)

        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0][0], rings[0][-1])
        self.assertEqual(rings[0][1], (40.0, 26.001))

    def test_mesafe_parsel_merkezinden_degil_sinirindan_hesaplanir(self):
        rings = kml_halkalarini_oku(self.kml_path)
        line = [(39.999, 26.002), (40.002, 26.002)]

        result = geometri_en_kisa_mesafe(rings, line)

        self.assertGreater(result["mesafe_m"], 80)
        self.assertLess(result["mesafe_m"], 90)

    def test_kesisen_cizginin_mesafesi_sifirdir(self):
        rings = kml_halkalarini_oku(self.kml_path)
        line = [(40.0005, 25.999), (40.0005, 26.002)]

        result = geometri_en_kisa_mesafe(rings, line)

        self.assertAlmostEqual(result["mesafe_m"], 0.0, places=5)

    def test_su_yolu_siniflandirmasi_konservatiftir(self):
        self.assertEqual(
            su_yolu_turunu_belirle({"waterway": "stream", "intermittent": "yes"}),
            "kuru",
        )
        self.assertEqual(
            su_yolu_turunu_belirle({"waterway": "river"}),
            "akar",
        )
        self.assertEqual(
            su_yolu_turunu_belirle({"waterway": "stream"}),
            "belirsiz",
        )

    def test_overpass_geometrisi_ayiklanir(self):
        records = overpass_elemanlarini_ayikla(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 15,
                        "tags": {"waterway": "stream", "name": "Kuru Dere"},
                        "geometry": [
                            {"lat": 40.0, "lon": 26.0},
                            {"lat": 40.1, "lon": 26.1},
                        ],
                    }
                ]
            }
        )

        self.assertEqual(records[0]["id"], "way-15")
        self.assertEqual(records[0]["ad"], "Kuru Dere")
        self.assertEqual(len(records[0]["noktalar"]), 2)

    def test_analiz_sadece_yaricap_icindeki_adayi_dondurur(self):
        result = cevre_analizi_yap(
            self.kml_path,
            inceleme_yaricapi_m=1000,
            provider=_FakeProvider(),
        )

        self.assertTrue(result["deniz"]["bulundu"])
        self.assertEqual(len(result["su_yollari"]), 1)
        self.assertEqual(result["su_yollari"][0]["tur"], "kuru")
        self.assertEqual(result["su_yollari"][0]["ad"], "Test Deresi")

    def test_kayit_ozeti_agir_geometrileri_cikarir_ve_kml_kontrol_edilir(self):
        result = cevre_analizi_yap(
            self.kml_path,
            inceleme_yaricapi_m=1000,
            provider=_FakeProvider(),
        )
        summary = cevre_analizi_kayit_ozeti(result)

        self.assertNotIn("parsel_halkalari", summary)
        self.assertNotIn("noktalar", summary["deniz"])
        self.assertNotIn("noktalar", summary["su_yollari"][0])
        self.assertTrue(cevre_analizi_guncel_mi(summary, self.kml_path))

        with open(self.kml_path, "a", encoding="utf-8") as stream:
            stream.write("\n")
        self.assertFalse(cevre_analizi_guncel_mi(summary, self.kml_path))


if __name__ == "__main__":
    unittest.main()
