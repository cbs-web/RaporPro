import unittest

from matplotlib.figure import Figure

from litoloji_korelasyon import sinif_kodu_coz
from ui_litoloji_manuel import ManuelLitolojiPenceresi


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Tree:
    def __init__(self):
        self.rows = {}
        self.order = []
        self.tag_options = {}

    def get_children(self):
        return tuple(self.order)

    def delete(self, item):
        self.rows.pop(item, None)
        if item in self.order:
            self.order.remove(item)

    def insert(self, parent, position, iid, values, tags=()):
        self.order.append(iid)
        self.rows[iid] = {"values": values, "tags": tags}

    def tag_configure(self, *args, **kwargs):
        if args:
            self.tag_options[args[0]] = kwargs


class _App:
    veri = {
        "sondaj": [
            {
                "no": "SK-1",
                "der": "7.5",
                "spt": [
                    ["1.50", "1", "2", "3", "5"],
                    ["3.00", "2", "6", "7", "13"],
                    ["4.50", "3", "10", "14", "24"],
                    ["6.00", "2", "4", "5", "9"],
                ],
            },
            {"no": "SK-2", "der": "7.5", "spt": []},
            {"no": "SK-10", "der": "7.5", "spt": []},
        ]
    }


class _Canvas:
    def __init__(self):
        self.draw_count = 0

    def draw_idle(self):
        self.draw_count += 1


class ManuelLitolojiCanliOnizlemeTestleri(unittest.TestCase):
    @staticmethod
    def _records():
        records = []
        for row_index, (top, bottom, code) in enumerate(
            (
                (1.5, 3.0, "grsiSaP"),
                (3.0, 4.5, "sasiGrP"),
                (4.5, 7.5, "saClL"),
            ),
            start=1,
        ):
            records.append(
                {
                    "row_index": row_index,
                    "sondaj": "SK-1",
                    "sondaj_key": "sk1",
                    "raw_depth": str(top),
                    "top": top,
                    "bottom": bottom,
                    "sinif": code,
                    "parsed": sinif_kodu_coz(code),
                }
            )
        return records

    def _window(self):
        window = ManuelLitolojiPenceresi.__new__(ManuelLitolojiPenceresi)
        window.app = _App()
        window.current_well_index = 0
        window.layers_by_well = {0: []}
        window.preview_states_by_well = {}
        window.lab_records = self._records()
        window.selected_lab_record = None
        window.selected_assignment_id = ""
        window.start_var = _Var()
        window.end_var = _Var()
        window.color_var = _Var("Kahve renkli")
        window.layer_tree = _Tree()
        window.preview_tree_records = {}
        window.drag_state = None
        window.range_pick_mode = False
        window.range_pick_points = []
        window.patch_targets = []
        window.preview_patch_targets = []
        window.well_geometries = {}
        return window

    def test_tum_lab_derinliklerini_alt_alta_onizler(self):
        window = self._window()
        window._sync_preview_states()
        window._refresh_layer_tree()

        rows = [
            window.layer_tree.rows[item]["values"]
            for item in window.layer_tree.order
        ]
        self.assertEqual(
            [row[1] for row in rows],
            ["1.50-3.00", "3.00-4.50", "4.50-7.50"],
        )
        self.assertTrue(all(row[0] == "Canlı önizleme" for row in rows))
        self.assertEqual(
            set(window.preview_tree_records.values()),
            {1, 2, 3},
        )

    def test_rehberi_once_dogal_sk_sonra_derinlige_gore_siralar(self):
        window = self._window()
        window.lab_tree = _Tree()
        window.lab_records = [
            {
                "row_index": 10,
                "sondaj": "SK-10",
                "sondaj_key": "sk10",
                "raw_depth": "1.50",
                "top": 1.5,
                "bottom": 3.0,
                "sinif": "ClH",
                "parsed": sinif_kodu_coz("ClH"),
            },
            {
                "row_index": 4,
                "sondaj": "SK-2",
                "sondaj_key": "sk2",
                "raw_depth": "3.00",
                "top": 3.0,
                "bottom": 4.5,
                "sinif": "saClL",
                "parsed": sinif_kodu_coz("saClL"),
            },
            {
                "row_index": 3,
                "sondaj": "SK-2",
                "sondaj_key": "sk2",
                "raw_depth": "1.50",
                "top": 1.5,
                "bottom": 3.0,
                "sinif": "siSa",
                "parsed": sinif_kodu_coz("siSa"),
            },
            {
                "row_index": 2,
                "sondaj": "SK-1",
                "sondaj_key": "sk1",
                "raw_depth": "3.00",
                "top": 3.0,
                "bottom": 7.5,
                "sinif": "grsiSaP",
                "parsed": sinif_kodu_coz("grsiSaP"),
            },
        ]
        window._refresh_lab_tree()
        values = [
            window.lab_tree.rows[item]["values"]
            for item in window.lab_tree.order
        ]
        self.assertEqual(
            [row[0].replace("▨ ", "") for row in values],
            ["SK-1", "SK-2", "SK-2", "SK-10"],
        )
        self.assertEqual(
            [row[1] for row in values],
            ["3.00", "1.50", "3.00", "1.50"],
        )
        self.assertTrue(values[0][0].startswith("▨ "))
        tags = [
            window.lab_tree.rows[item]["tags"][0]
            for item in window.lab_tree.order
        ]
        self.assertEqual(tags[1], tags[2])
        self.assertEqual(len({tags[0], tags[1], tags[3]}), 3)
        self.assertIn(
            "background",
            window.lab_tree.tag_options[tags[0]],
        )

    def test_tum_sondajlari_yan_yana_ve_kuyu_ici_bilgilerle_cizer(self):
        window = self._window()
        window.lab_records.append(
            {
                "row_index": 20,
                "sondaj": "SK-2",
                "sondaj_key": "sk2",
                "raw_depth": "1.50",
                "top": 1.5,
                "bottom": 7.5,
                "sinif": "ClH",
                "parsed": sinif_kodu_coz("ClH"),
            }
        )
        window.figure = Figure(figsize=(8, 6), dpi=100)
        window.axes = window.figure.add_subplot(111)
        window.canvas = _Canvas()
        window._sync_preview_states()

        window._draw()

        self.assertEqual(set(window.well_geometries), {0, 1, 2})
        self.assertGreater(window.well_geometries[1]["x0"], 1.0)
        all_text = [artist.get_text() for artist in window.axes.texts]
        self.assertIn("SK-1", all_text)
        self.assertIn("SK-2", all_text)
        self.assertIn("SK-10", all_text)
        self.assertTrue(
            any(
                "ÇAKILLI SİLTLİ KUM" in text.replace("\n", " ")
                for text in all_text
            )
        )
        lithology_texts = [
            artist
            for artist in window.axes.texts
            if "ÇAKILLI SİLTLİ KUM"
            in artist.get_text().replace("\n", " ")
        ]
        self.assertTrue(
            all(artist.get_fontsize() >= 5.0 for artist in lithology_texts)
        )
        self.assertIn("13", all_text)
        self.assertFalse(any("N30=" in text for text in all_text))
        self.assertFalse(any(text == "grsiSaP" for text in all_text))
        self.assertTrue(
            all(hasattr(patch, "_well_index") for patch in window.preview_patch_targets)
        )
        self.assertEqual(window.canvas.draw_count, 1)

    def test_lab_rehberinde_yalniz_kaynak_derinlik_gosterilir(self):
        record = {
            "raw_depth": "7,50",
            "top": 7.5,
            "bottom": 12.0,
        }
        self.assertEqual(
            ManuelLitolojiPenceresi._lab_source_depth_display(record),
            "7.50",
        )
        self.assertEqual(
            ManuelLitolojiPenceresi._lab_interval_display(record),
            "7.50-12.00",
        )

    def test_kuyu_deseni_ana_zemin_birimine_gore_seciliyor(self):
        self.assertEqual(
            ManuelLitolojiPenceresi._layer_pattern_style(
                {"ana_birim": "cl"}
            )["desen"],
            "kesikli",
        )
        self.assertEqual(
            ManuelLitolojiPenceresi._layer_pattern_style(
                {"ana_birim": "sa"}
            )["desen"],
            "nokta",
        )
        self.assertEqual(
            ManuelLitolojiPenceresi._layer_pattern_style(
                {"ana_birim": "gr"}
            )["desen"],
            "cakil_daire",
        )


if __name__ == "__main__":
    unittest.main()
