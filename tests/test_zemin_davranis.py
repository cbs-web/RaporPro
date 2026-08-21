import unittest

from zemin_davranis import (
    KIVAM_SIRASI,
    SIKILIK_SIRASI,
    n30_kivam_sinifi,
    n30_sikilik_sinifi,
)


class ZeminDavranisTestleri(unittest.TestCase):
    def test_kivam_sinirlarinin_iki_tarafi(self):
        cases = (
            (0, "Çok yumuşak"),
            (2, "Çok yumuşak"),
            (2.01, "Yumuşak"),
            (4, "Yumuşak"),
            (4.01, "Orta katı"),
            (8, "Orta katı"),
            (8.01, "Katı"),
            (15, "Katı"),
            (15.01, "Çok katı"),
            (30, "Çok katı"),
            (30.01, "Sert"),
        )
        for n30, expected in cases:
            with self.subTest(n30=n30):
                self.assertEqual(n30_kivam_sinifi(n30), expected)

    def test_sikilik_sinirlarinin_iki_tarafi(self):
        cases = (
            (0, "Çok gevşek"),
            (4, "Çok gevşek"),
            (4.01, "Gevşek"),
            (10, "Gevşek"),
            (10.01, "Orta sıkı"),
            (30, "Orta sıkı"),
            (30.01, "Sıkı"),
            (50, "Sıkı"),
            (50.01, "Çok sıkı"),
        )
        for n30, expected in cases:
            with self.subTest(n30=n30):
                self.assertEqual(n30_sikilik_sinifi(n30), expected)

    def test_refu_siniflari(self):
        self.assertEqual(n30_kivam_sinifi(None, refused=True), "Sert")
        self.assertEqual(n30_sikilik_sinifi(None, refused=True), "Çok sıkı")

    def test_gecersiz_ve_negatif_degerler_bos_sinif_dondurur(self):
        invalid_values = (None, "", "-", "—", "nan", "none", "null", -1, -0.01)
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertEqual(n30_kivam_sinifi(value), "")
                self.assertEqual(n30_sikilik_sinifi(value), "")

    def test_sayisal_girdiler_ve_virgullu_ondaliklar(self):
        self.assertEqual(n30_kivam_sinifi(4.0), "Yumuşak")
        self.assertEqual(n30_kivam_sinifi("4,01"), "Orta katı")
        self.assertEqual(n30_sikilik_sinifi(10.0), "Gevşek")
        self.assertEqual(n30_sikilik_sinifi("10,01"), "Orta sıkı")

    def test_sira_tanimlari_siniflarla_uyumludur(self):
        self.assertEqual(KIVAM_SIRASI, ("Çok yumuşak", "Yumuşak", "Orta katı", "Katı", "Çok katı", "Sert"))
        self.assertEqual(SIKILIK_SIRASI, ("Çok gevşek", "Gevşek", "Orta sıkı", "Sıkı", "Çok sıkı"))


if __name__ == "__main__":
    unittest.main()
