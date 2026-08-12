import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import motor_log_saglik
import ortam_kontrolu


VALID_SOURCE = """
def log_ornek_derinligi_formatla(value):
    return str(value)


class GeoEngineLogMixin:
    @staticmethod
    def ciz_profesyonel_log(sondaj, proje_dict, log_callback=None):
        return None

    @staticmethod
    def _ciz_strater_stil_log(sondaj, proje_dict, log_callback=None):
        return None

    @staticmethod
    def _ciz_profesyonel_log_eski(sondaj, proje_dict, log_callback=None):
        return None
"""


def _kopru_dosyalari_yaz(root, source=VALID_SOURCE, module_name="motor_log_test_source"):
    root = Path(root)
    (root / "motor_log.py").write_text(
        "from "
        f"{module_name} "
        "import GeoEngineLogMixin, log_ornek_derinligi_formatla\n",
        encoding="utf-8",
    )
    (root / f"{module_name}.py").write_text(source, encoding="utf-8")


class MotorLogSaglikTestleri(unittest.TestCase):
    def test_proje_koprusu_modul_calistirilmadan_dogrulanir(self):
        project_root = Path(motor_log_saglik.__file__).resolve().parent
        with mock.patch.object(
            motor_log_saglik,
            "_load_motor_log_module",
            side_effect=AssertionError("statik kontrol dinamik yukleme yapmamali"),
        ):
            self.assertEqual(motor_log_saglik.check_motor_log_bridge(project_root), [])

    def test_statik_kontrol_gecerli_yerel_kopruyu_kabul_eder(self):
        with tempfile.TemporaryDirectory() as tmp:
            _kopru_dosyalari_yaz(tmp)
            self.assertEqual(motor_log_saglik.check_motor_log_bridge(tmp), [])

    def test_statik_kontrol_gercek_fonksiyon_imzasini_denetler(self):
        source = VALID_SOURCE.replace(
            "def log_ornek_derinligi_formatla(value):",
            "def log_ornek_derinligi_formatla(value, default=None):",
        )
        with tempfile.TemporaryDirectory() as tmp:
            _kopru_dosyalari_yaz(tmp, source)
            self.assertIn(
                "log_ornek_derinligi_formatla imzasi beklenenden farkli: (value, default=None)",
                motor_log_saglik.check_motor_log_bridge(tmp),
            )

    def test_statik_kontrol_gercek_sinif_metodu_imzasini_denetler(self):
        source = VALID_SOURCE.replace(
            "def ciz_profesyonel_log(sondaj, proje_dict, log_callback=None):",
            "def ciz_profesyonel_log(self, sondaj, proje_dict, log_callback=None):",
        )
        with tempfile.TemporaryDirectory() as tmp:
            _kopru_dosyalari_yaz(tmp, source)
            self.assertIn(
                "ciz_profesyonel_log imzasi beklenenden farkli: "
                "(self, sondaj, proje_dict, log_callback=None)",
                motor_log_saglik.check_motor_log_bridge(tmp),
            )

    def test_koprudeki_eksik_sinif_ayni_hata_mesajini_korur(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "motor_log.py").write_text(
                "from motor_log_test_source import log_ornek_derinligi_formatla\n",
                encoding="utf-8",
            )
            (root / "motor_log_test_source.py").write_text(VALID_SOURCE, encoding="utf-8")
            self.assertEqual(
                motor_log_saglik.check_motor_log_bridge(tmp),
                ["GeoEngineLogMixin sinifi bulunamadi."],
            )

    def test_tam_dinamik_kontrol_acik_api_olarak_korunur(self):
        module_name = "motor_log_dynamic_test_source"
        with tempfile.TemporaryDirectory() as tmp:
            _kopru_dosyalari_yaz(tmp, module_name=module_name)
            sys.modules.pop(module_name, None)
            try:
                self.assertEqual(motor_log_saglik.check_motor_log_bridge_dynamic(tmp), [])
                self.assertTrue(motor_log_saglik.motor_log_bridge_dynamic_ok(tmp))
            finally:
                sys.modules.pop(module_name, None)

    def test_ortam_kontrolu_motor_log_hatalarini_ayni_yapida_raporlar(self):
        with mock.patch.object(ortam_kontrolu, "_missing_from", side_effect=[[], []]), mock.patch.object(
            ortam_kontrolu,
            "check_motor_log_bridge",
            return_value=["ornek kopru hatasi"],
        ):
            required_missing, optional_missing = ortam_kontrolu.check_dependencies()

        self.assertEqual(optional_missing, [])
        self.assertEqual(
            required_missing,
            [
                {
                    "module": "motor_log",
                    "package": "motor_log.py",
                    "purpose": "Sondaj logu cizim motoru - ornek kopru hatasi",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
