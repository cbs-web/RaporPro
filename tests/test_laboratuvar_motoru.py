import unittest

from laboratuvar_motoru import laboratuvar_baslik_bilgisi
from ui_lab_sheet import laboratuvar_baslik_bilgisi as ui_laboratuvar_baslik_bilgisi


class LaboratuvarMotoruTestleri(unittest.TestCase):
    def test_tek_satirli_turkce_baslik(self):
        rows = [
            ["Sondaj No", "Numune No", "Derinlik", "Siniflama"],
            ["SK-01", "1", "1,50", "CL"],
        ]

        bilgi = laboratuvar_baslik_bilgisi(rows)

        self.assertEqual(bilgi["header_row"], 0)
        self.assertEqual(bilgi["data_start"], 1)
        self.assertEqual(
            bilgi["columns"],
            {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": 3},
        )
        self.assertEqual(bilgi["signatures"], ["Sondaj No", "Numune No", "Derinlik", "Siniflama"])

    def test_baslik_varyasyonlari(self):
        cases = [
            (
                ["Sondaj No", "Numune No", "Derinlik", "Siniflama"],
                {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": 3},
            ),
            (
                ["Kuyu No", "Sample No", "Depth", "Classification"],
                {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": 3},
            ),
            (
                ["Boring No", "Sample No", "Depth", "USCS"],
                {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": 3},
            ),
        ]

        for headers, expected_columns in cases:
            with self.subTest(headers=headers):
                bilgi = laboratuvar_baslik_bilgisi(
                    [headers, ["SK-01", "1", "1.50", "CL"]]
                )
                self.assertEqual(bilgi["header_row"], 0)
                self.assertEqual(bilgi["data_start"], 1)
                self.assertEqual(bilgi["columns"], expected_columns)

    def test_cok_satirli_gercek_sablona_benzeyen_baslik(self):
        rows = [
            ["Proje", "RaporPro", "", "", "", ""],
            ["Sondaj No", "Numune No", "Derinlik", "Siniflama", "Deney", ""],
            ["", "No", "(m)", "USCS", "Sonuç", "Birim"],
            ["SK-01", "1", "1,25", "CL", "Atterberg", "%"],
            ["SK-01", "2", "2.50", "ML", "Atterberg", "%"],
        ]

        bilgi = laboratuvar_baslik_bilgisi(rows)

        self.assertEqual(bilgi["header_row"], 1)
        self.assertEqual(bilgi["data_start"], 3)
        self.assertEqual(
            bilgi["signatures"],
            [
                "Sondaj No",
                "Numune No / No",
                "Derinlik / (m)",
                "Siniflama / USCS",
                "Deney / Sonuç",
                "Deney / Birim",
            ],
        )
        self.assertEqual(
            bilgi["columns"],
            {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": 3},
        )

    def test_bos_veri(self):
        expected = {
            "rows": [],
            "header_row": 0,
            "data_start": 0,
            "signatures": [],
            "keys": [],
            "columns": {},
        }

        self.assertEqual(laboratuvar_baslik_bilgisi(None), expected)
        self.assertEqual(laboratuvar_baslik_bilgisi([]), expected)

    def test_eksik_siniflama_kolonu(self):
        bilgi = laboratuvar_baslik_bilgisi(
            [
                ["Sondaj No", "Numune No", "Derinlik"],
                ["SK-01", "1", "1.50"],
            ]
        )

        self.assertEqual(
            bilgi["columns"],
            {"sondaj": 0, "numune": 1, "derinlik": 2, "sinif": None},
        )

    def test_ui_importu_geriye_donuk_uyumludur(self):
        self.assertIs(ui_laboratuvar_baslik_bilgisi, laboratuvar_baslik_bilgisi)

        rows = [
            ["Kuyu No", "Sample No", "Depth", "Classification"],
            ["K-1", "1", "3.25", "SM"],
        ]
        self.assertEqual(
            ui_laboratuvar_baslik_bilgisi(rows),
            laboratuvar_baslik_bilgisi(rows),
        )


if __name__ == "__main__":
    unittest.main()
