# Dosya: RaporPro/tests/test_rapor_onizleme.py
import os
import tempfile
import time
import unittest
from pathlib import Path

from ui_rapor_onizleme import (
    rapor_onizleme_cache_temizle,
    rapor_onizleme_olcegi,
    rapor_onizleme_parmak_izi,
)


class RaporOnizlemeMotoruTestleri(unittest.TestCase):
    def test_parmak_izi_ayni_veride_kararli(self):
        veri = {"proje": {"adi": "Deneme"}, "sondajlar": [{"no": "SK-1"}]}
        first = rapor_onizleme_parmak_izi(veri)
        second = rapor_onizleme_parmak_izi(veri)
        self.assertEqual(first, second)

    def test_parmak_izi_veri_degisince_degisir(self):
        first = rapor_onizleme_parmak_izi({"proje": {"adi": "A"}})
        second = rapor_onizleme_parmak_izi({"proje": {"adi": "B"}})
        self.assertNotEqual(first, second)

    def test_parmak_izi_kaynak_dosyayi_izler(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "kaynak.txt"
            source.write_text("ilk", encoding="utf-8")
            first = rapor_onizleme_parmak_izi({}, [source])
            source.write_text("daha uzun ikinci içerik", encoding="utf-8")
            second = rapor_onizleme_parmak_izi({}, [source])
            self.assertNotEqual(first, second)

    def test_sayfaya_sigdir_iki_ekseni_de_korur(self):
        scale = rapor_onizleme_olcegi((600, 900), (1200, 700), mode="page")
        self.assertLessEqual(600 * scale, 1200 - 72)
        self.assertLessEqual(900 * scale, 700 - 72)

    def test_gercek_boyut_96_dpi_karsiligidir(self):
        scale = rapor_onizleme_olcegi((600, 900), (1200, 900), mode="actual")
        self.assertAlmostEqual(scale, 96 / 72, places=4)

    def test_cache_temizligi_en_yeni_ciftleri_korur(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            for index in range(3):
                for suffix in (".docx", ".pdf"):
                    path = cache_dir / f"rapor_{index}{suffix}"
                    path.write_bytes(f"{index}-{suffix}".encode("ascii"))
                    stamp = time.time() + index
                    os.utime(path, (stamp, stamp))
            removed = rapor_onizleme_cache_temizle(cache_dir, keep=2)
            self.assertEqual(len(removed), 2)
            self.assertFalse((cache_dir / "rapor_0.docx").exists())
            self.assertFalse((cache_dir / "rapor_0.pdf").exists())
            self.assertTrue((cache_dir / "rapor_1.docx").exists())
            self.assertTrue((cache_dir / "rapor_2.pdf").exists())


if __name__ == "__main__":
    unittest.main()
