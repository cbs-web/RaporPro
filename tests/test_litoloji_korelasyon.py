import copy
import os
import tempfile
import unittest

from litoloji_korelasyon import (
    KIVAM_SIRASI,
    PLASTISITE_SIRASI,
    coklu_sondaj_onerileri_olustur,
    hucreleri_katmanlara_birlestir,
    laboratuvar_litoloji_kayitlari,
    manuel_atama_cakisiyor,
    manuel_katmanlari_dogrula,
    manuel_lab_katmanlari_olustur,
    n30_kivam_sinifi,
    sinif_kodu_coz,
    siniflar_ardisik_mi,
    sondaj_spt_kayitlari,
)
from proje_sema import proje_verisini_migre_et, varsayilan_proje_verisi
from ui_lab_sheet import lab_kaynak_satirlari


def _cell(top, code, behavior, status="lab_onayli"):
    parsed = sinif_kodu_coz(code)
    return {
        "top": top,
        "bottom": top + 0.5,
        "sinif": code,
        "malzeme_anahtari": parsed["malzeme_anahtari"],
        "ana_birim": parsed["ana_birim"],
        "birim_adi": parsed["birim_adi"],
        "plastisite": parsed["plastisite"],
        "derecelenme": parsed["derecelenme"],
        "davranis": behavior,
        "kanit_durumu": status,
        "kaynaklar": ["test"],
    }


class LitolojiKurallariTestleri(unittest.TestCase):
    def test_plastisite_komsuluk_kurali(self):
        self.assertTrue(siniflar_ardisik_mi("L", "M", PLASTISITE_SIRASI))
        self.assertTrue(siniflar_ardisik_mi("M", "H", PLASTISITE_SIRASI))
        self.assertFalse(siniflar_ardisik_mi("L", "H", PLASTISITE_SIRASI))

    def test_kivam_sinir_degerleri(self):
        self.assertEqual(n30_kivam_sinifi(2), "Çok yumuşak")
        self.assertEqual(n30_kivam_sinifi(4), "Yumuşak")
        self.assertEqual(n30_kivam_sinifi(5), "Orta katı")
        self.assertEqual(n30_kivam_sinifi(15), "Katı")
        self.assertEqual(n30_kivam_sinifi(30), "Çok katı")
        self.assertEqual(n30_kivam_sinifi(31), "Sert")

    def test_sacl_kodunu_malzeme_ve_plastisiteye_ayirir(self):
        parsed = sinif_kodu_coz("saClL")
        self.assertTrue(parsed["biliniyor"])
        self.assertEqual(parsed["malzeme_anahtari"], "sacl")
        self.assertEqual(parsed["birim_adi"], "Kumlu Kil")
        self.assertEqual(parsed["plastisite"], "L")

    def test_lab_buyuk_i_yazimini_kucuk_l_olarak_tanir(self):
        cases = (
            ("saCIL", "sacl", "Kumlu Kil", "L", "saClL"),
            ("CIH", "cl", "Kil", "H", "ClH"),
            ("CIL", "cl", "Kil", "L", "ClL"),
            ("grCIH", "grcl", "Çakıllı Kil", "H", "grClH"),
            ("grCIL", "grcl", "Çakıllı Kil", "L", "grClL"),
            ("saCIM", "sacl", "Kumlu Kil", "M", "saClM"),
            ("saCIH", "sacl", "Kumlu Kil", "H", "saClH"),
        )
        for raw, key, name, plasticity, corrected in cases:
            with self.subTest(raw=raw):
                parsed = sinif_kodu_coz(raw)
                self.assertTrue(parsed["biliniyor"])
                self.assertEqual(parsed["malzeme_anahtari"], key)
                self.assertEqual(parsed["birim_adi"], name)
                self.assertEqual(parsed["plastisite"], plasticity)
                self.assertEqual(parsed["duzeltilmis_kod"], corrected)

    def test_gecerli_ci_kodunun_anlamini_degistirmez(self):
        parsed = sinif_kodu_coz("CI")
        self.assertTrue(parsed["biliniyor"])
        self.assertEqual(parsed["malzeme_anahtari"], "cl")
        self.assertEqual(parsed["plastisite"], "M")
        self.assertEqual(parsed["duzeltilmis_kod"], "")

    def test_lab_karot_numune_turunu_sayisal_karot_degeri_kullanmadan_kaya_ankraji_yapar(self):
        veri = {
            "lab_sheet": {
                "rows": [
                    ["Sondaj No", "Numune No", "Derinlik", "SINIFLAMA", "qu"],
                    ["SK-1", "KAROT", "4.5", "", "12.4"],
                ]
            },
            "sondaj": [
                {
                    "no": "SK-1",
                    "der": "8",
                    "litoloji": [],
                    "spt": [],
                    "pmt": [["5", "999", "99"]],
                    "kaya": [["4.5", "11", "22", "33"]],
                }
            ],
        }
        result = coklu_sondaj_onerileri_olustur(veri)
        lab_cells = [
            cell
            for cell in result["sondajlar"][0]["hucreler"]
            if 4.5 <= cell["top"] < 6.0
        ]
        self.assertTrue(lab_cells)
        self.assertTrue(all(cell["ana_birim"] == "rk" for cell in lab_cells))
        self.assertTrue(
            all(cell["kanit_durumu"] == "lab_onayli" for cell in lab_cells)
        )

    def test_ardisik_plastisiteyi_birlestirir_uzak_plastisiteyi_ayirir(self):
        adjacent = hucreleri_katmanlara_birlestir(
            [_cell(0, "saClL", "Katı"), _cell(0.5, "saClM", "Katı")]
        )
        separated = hucreleri_katmanlara_birlestir(
            [_cell(0, "saClL", "Katı"), _cell(0.5, "saClH", "Katı")]
        )
        self.assertEqual(len(adjacent), 1)
        self.assertEqual(len(separated), 2)

    def test_ayni_kodda_n30_4_ve_16_kivam_nedeniyle_ayrilir(self):
        layers = hucreleri_katmanlara_birlestir(
            [
                _cell(0, "saClL", "Yumuşak"),
                _cell(0.5, "saClL", "Çok katı"),
            ]
        )
        self.assertEqual(len(layers), 2)
        self.assertIn("YUMUŞAK", layers[0]["tanim"])
        self.assertIn("ÇOK KATI", layers[1]["tanim"])

    def test_ardisik_kivamlar_birlestirilir(self):
        self.assertTrue(siniflar_ardisik_mi("Orta katı", "Katı", KIVAM_SIRASI))
        layers = hucreleri_katmanlara_birlestir(
            [
                _cell(0, "saClL", "Orta katı"),
                _cell(0.5, "saClL", "Katı"),
            ]
        )
        self.assertEqual(len(layers), 1)
        self.assertIn("ORTA KATI-KATI", layers[0]["tanim"])

    def test_farkli_malzeme_her_zaman_ayrilir(self):
        layers = hucreleri_katmanlara_birlestir(
            [_cell(0, "saClL", "Katı"), _cell(0.5, "clSa", "Orta sıkı")]
        )
        self.assertEqual(len(layers), 2)


class KorelasyonMotoruTestleri(unittest.TestCase):
    def _lab_rows(self):
        return [
            ["Sondaj No", "Numune", "Derinlik (m)", "SINIFLAMA Classification", "PI"],
            ["SK-2", "UD-1", "4.5-6.0", "saClL", "12"],
            ["SK-3", "UD-2", "6.0-7.5", "saClL", "11"],
        ]

    def test_eksik_sk3_araligini_korelasyonla_onerir_ve_ham_veriyi_degistirmez(self):
        veri = {
            "lab_sheet": {"rows": self._lab_rows()},
            "sondaj": [
                {"no": "SK-2", "der": "9", "k": "100", "litoloji": [], "spt": []},
                {"no": "SK-3", "der": "9", "k": "100", "litoloji": [], "spt": []},
            ],
        }
        before = copy.deepcopy(veri)
        result = coklu_sondaj_onerileri_olustur(veri)
        sk3 = result["sondajlar"][1]
        target = [
            cell
            for cell in sk3["hucreler"]
            if cell["top"] >= 4.5 and cell["bottom"] <= 6.0
        ]
        self.assertTrue(target)
        self.assertTrue(
            all(cell["malzeme_anahtari"] == "sacl" for cell in target)
        )
        self.assertTrue(
            all(cell["kanit_durumu"] == "korelasyonla_onerildi" for cell in target)
        )
        self.assertEqual(veri, before)

    def test_lab_onayli_ve_tahmini_kanit_ayri_kalir(self):
        veri = {
            "lab_sheet": {"rows": self._lab_rows()},
            "sondaj": [
                {"no": "SK-2", "der": "8", "k": "", "litoloji": [], "spt": []},
                {"no": "SK-3", "der": "8", "k": "", "litoloji": [], "spt": []},
            ],
        }
        result = coklu_sondaj_onerileri_olustur(veri)
        statuses = {
            cell["kanit_durumu"]
            for cell in result["sondajlar"][1]["hucreler"]
            if 4.5 <= cell["top"] < 7.5
        }
        self.assertIn("lab_onayli", statuses)
        self.assertIn("korelasyonla_onerildi", statuses)


class ManuelLabIsaretlemeTestleri(unittest.TestCase):
    def _record(self, code="saClL"):
        return {
            "row_index": 4,
            "sondaj": "SK-1",
            "raw_depth": "1.50",
            "sinif": code,
            "parsed": sinif_kodu_coz(code),
        }

    def test_renk_ve_spt_kivamini_otomatik_tanima_ekler(self):
        well = {
            "no": "SK-1",
            "der": "4.5",
            "spt": [
                ["1.50", "1", "2", "3", "5"],
                ["3.00", "2", "4", "5", "9"],
            ],
        }
        layers = manuel_lab_katmanlari_olustur(
            well,
            self._record(),
            1.5,
            4.5,
            "Kahve renkli",
            atama_id="a1",
        )
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["atama_id"], "a1")
        self.assertEqual(layers[0]["renk"], "Kahve renkli")
        self.assertIn("KAHVE RENKLİ", layers[0]["tanim"])
        self.assertIn("ORTA KATI-KATI", layers[0]["tanim"])
        self.assertIn("DÜŞÜK PLASTİSİTELİ KUMLU KİL", layers[0]["tanim"])

    def test_tek_derinlikli_lab_birimi_sonraki_baslangica_kadar_uzanir(self):
        rows = [
            ["Sondaj No", "Numune", "Derinlik (m)", "SINIFLAMA Classification"],
            ["SK-1", "UD-1", "3.00", "saClL"],
            ["SK-1", "UD-2", "4.50", "saClM"],
            ["SK-1", "UD-3", "7.50", "ClH"],
        ]
        result = laboratuvar_litoloji_kayitlari(
            rows,
            sondajlar=[{"no": "SK-1", "der": "10.0"}],
        )
        self.assertEqual(
            [
                (record["top"], record["bottom"])
                for record in result["records"]
            ],
            [(3.0, 4.5), (4.5, 7.5), (7.5, 10.0)],
        )
        self.assertTrue(
            all(
                record["derinlik_turu"] == "baslangic"
                for record in result["records"]
            )
        )

    def test_acik_lab_araligi_aynen_korunur(self):
        rows = [
            ["Sondaj No", "Numune", "Derinlik (m)", "SINIFLAMA Classification"],
            ["SK-1", "UD-1", "3.00-4.00", "saClL"],
            ["SK-1", "UD-2", "4.50", "saClM"],
        ]
        result = laboratuvar_litoloji_kayitlari(
            rows,
            sondajlar=[{"no": "SK-1", "der": "8.0"}],
        )
        self.assertEqual(
            [
                (record["top"], record["bottom"])
                for record in result["records"]
            ],
            [(3.0, 4.0), (4.5, 8.0)],
        )
        self.assertEqual(result["records"][0]["derinlik_turu"], "aralik")

    def test_spt_degeri_sonraki_spt_baslangicina_kadar_gecerlidir(self):
        well = {
            "no": "SK-1",
            "der": "8.0",
            "spt": [
                ["3.00", "1", "5", "8", "13"],
                ["4.50", "2", "10", "14", "24"],
                ["6.50", "3", "15", "18", "33"],
            ],
        }
        records = sondaj_spt_kayitlari(well)
        self.assertEqual(
            [(item["top"], item["bottom"]) for item in records],
            [(3.0, 4.5), (4.5, 6.5), (6.5, 8.0)],
        )
        self.assertEqual(records[0]["deney_bottom"], 3.45)
        self.assertEqual(records[1]["deney_bottom"], 4.95)

    def test_spt_eslesmesi_etki_araligindaki_birime_uygulanir(self):
        well = {
            "no": "SK-1",
            "der": "4.5",
            "spt": [
                ["1.50", "1", "1", "3", "4"],
                ["3.00", "2", "8", "8", "16"],
            ],
        }
        layers = manuel_lab_katmanlari_olustur(
            well,
            self._record(),
            1.5,
            4.5,
            "Bej renkli",
            atama_id="spt-aralik",
        )
        self.assertEqual(
            [(layer["top"], layer["bottom"]) for layer in layers],
            [(1.5, 3.0), (3.0, 4.5)],
        )
        self.assertEqual(
            [layer["davranislar"] for layer in layers],
            [["Yumuşak"], ["Çok katı"]],
        )

    def test_uzak_kivam_gecisinde_ayni_lab_birimini_iki_alt_katmana_ayirir(self):
        well = {
            "no": "SK-1",
            "der": "4.5",
            "spt": [
                ["1.50", "1", "2", "2", "4"],
                ["3.00", "4", "8", "8", "16"],
            ],
        }
        before = copy.deepcopy(well)
        layers = manuel_lab_katmanlari_olustur(
            well,
            self._record(),
            1.5,
            4.5,
            "Bej renkli",
            atama_id="a2",
        )
        self.assertEqual(len(layers), 2)
        self.assertEqual(
            [layer["davranislar"] for layer in layers],
            [["Yumuşak"], ["Çok katı"]],
        )
        self.assertTrue(all(layer["sinif"] == "saClL" for layer in layers))
        self.assertEqual(well, before)

    def test_bos_spt_hucresi_uzak_kivamlar_arasinda_kopru_kurmaz(self):
        cells = [
            _cell(0.0, "saClL", "Yumuşak"),
            _cell(0.5, "saClL", ""),
            _cell(1.0, "saClL", "Çok katı"),
        ]
        layers = hucreleri_katmanlara_birlestir(cells)
        self.assertEqual(len(layers), 2)

    def test_kapsam_bosluk_ve_cakismalarini_onay_oncesi_yakalar(self):
        gap_layers = [
            {"top": 0.0, "bottom": 1.5},
            {"top": 2.0, "bottom": 3.0},
        ]
        overlap_layers = [
            {"top": 0.0, "bottom": 2.0},
            {"top": 1.5, "bottom": 3.0},
        ]
        complete_layers = [
            {"top": 0.0, "bottom": 1.5},
            {"top": 1.5, "bottom": 3.0},
        ]
        self.assertFalse(manuel_katmanlari_dogrula(gap_layers, 3)["valid"])
        self.assertFalse(manuel_katmanlari_dogrula(overlap_layers, 3)["valid"])
        self.assertTrue(manuel_katmanlari_dogrula(complete_layers, 3)["valid"])
        self.assertTrue(manuel_atama_cakisiyor(complete_layers, 1.0, 2.0))
        self.assertFalse(manuel_atama_cakisiyor(complete_layers, 3.0, 4.0))

    def test_kuyu_sonu_yarim_metre_degilse_son_siniri_gercek_derinlikte_korur(self):
        well = {"no": "SK-1", "der": "3.20", "spt": []}
        layers = manuel_lab_katmanlari_olustur(
            well,
            self._record(),
            0.0,
            3.2,
            "Grimsi renkli",
        )
        self.assertEqual(layers[-1]["bottom"], 3.2)
        self.assertTrue(manuel_katmanlari_dogrula(layers, 3.2)["valid"])


class HedefProgramUyarlamaTestleri(unittest.TestCase):
    def test_lab_sheet_bagli_excelden_once_kullanilir(self):
        rows, source = lab_kaynak_satirlari(
            {
                "lab_sheet": {
                    "rows": [
                        ["Sondaj No", "Numune", "Derinlik", "SINIFLAMA"],
                        ["SK-1", "UD-1", "1.50", "saClL"],
                    ]
                }
            },
            os.path.join("bulunmayan", "lab.xlsx"),
        )
        self.assertEqual(source, "LAB Sheet")
        self.assertEqual(rows[1][0], "SK-1")

    def test_lab_sheet_bossa_bagli_excel_okunur(self):
        from openpyxl import Workbook

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "laboratuvar.xlsx")
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(["Sondaj No", "Numune", "Derinlik", "SINIFLAMA"])
            worksheet.append(["SK-2", "UD-2", 3.0, "ClH"])
            workbook.save(path)
            workbook.close()

            rows, source = lab_kaynak_satirlari(
                {"lab_sheet": {"rows": []}},
                path,
            )

        self.assertEqual(source, "laboratuvar.xlsx")
        self.assertEqual(rows[1][:4], ["SK-2", "UD-2", "3", "ClH"])

    def test_eski_proje_manuel_taslak_alaniyla_tamamlanir(self):
        old_data = varsayilan_proje_verisi()
        old_data.pop("litoloji_manuel_taslak")
        migrated, _info = proje_verisini_migre_et(old_data)
        self.assertEqual(
            migrated["litoloji_manuel_taslak"],
            {"surum": 1, "sondajlar": {}},
        )


if __name__ == "__main__":
    unittest.main()
