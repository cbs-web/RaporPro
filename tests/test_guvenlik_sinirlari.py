import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

import performans
from ai_motoru import _ai_ile_analiz_et
from cikti_kalite import (
    cikti_dosyalari_denetle,
    kalite_manifestosu_dogrula,
    kalite_manifestosu_yaz,
)
from proje_arsiv import biten_isler_kml_yaz
from proje_paketi import (
    PAKET_META_KEY,
    paket_proje_verisini_kayda_hazirla,
    paket_proje_verisini_yukle,
    proje_paketi_olustur,
)
from proje_surumleri import (
    surum_deposu_yolu,
    surum_kaydi_olustur,
    surum_verisi_yukle,
    surumleri_listele,
)
from rapor_metin_revizyon import _ai_metin_revizyonu
from spt_okuma_motoru import SPTKaydi, spt_kaynak_raporu_kaydet
from spt_saglayicilar import spt_ai_metin_iste


class SurumDeposuGuvenlikTestleri(unittest.TestCase):
    def test_indexteki_klasor_disi_yol_okunmaz_silinmez_ve_index_korunur(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = os.path.join(tmp, "proje.json")
            outside_path = os.path.join(tmp, "outside.json")
            Path(outside_path).write_text('{"gizli": true}', encoding="utf-8")

            store = surum_deposu_yolu(project_path)
            os.makedirs(store)
            index_path = os.path.join(store, "index.json")
            Path(index_path).write_text(
                json.dumps({
                    "schema_version": 1,
                    "next_sequence": 2,
                    "legacy_imports": [],
                    "versions": [{
                        "id": "zararli",
                        "sequence": 1,
                        "created_at": "2026-01-01T00:00:00",
                        "file": "../../outside.json",
                    }],
                }),
                encoding="utf-8",
            )

            with self.assertRaises(FileNotFoundError):
                surum_verisi_yukle(
                    project_path,
                    {"id": "zararli", "file": "../../outside.json"},
                )

            surum_kaydi_olustur(
                project_path,
                {"kunye": {"sahibi": "Güvenli"}},
                keep=5,
            )

            self.assertTrue(os.path.isfile(outside_path))
            corrupt_files = list(Path(store).glob("index.json.corrupt*"))
            self.assertEqual(len(corrupt_files), 1)
            self.assertIn("../../outside.json", corrupt_files[0].read_text(encoding="utf-8"))

    def test_bozuk_json_index_sessizce_ezilmez(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = os.path.join(tmp, "proje.json")
            store = surum_deposu_yolu(project_path)
            os.makedirs(store)
            index_path = Path(store) / "index.json"
            index_path.write_text("{bozuk-json", encoding="utf-8")

            self.assertEqual(
                surumleri_listele(project_path, eski_yedekleri_aktar=False),
                [],
            )

            corrupt_files = list(Path(store).glob("index.json.corrupt*"))
            self.assertEqual(len(corrupt_files), 1)
            self.assertEqual(corrupt_files[0].read_text(encoding="utf-8"), "{bozuk-json")
            self.assertFalse(index_path.exists())


class TasinabilirPaketGuvenlikTestleri(unittest.TestCase):
    def test_yalniz_beyaz_listeli_alanlar_kopyalanir_ve_manifest_yol_sizdirmaz(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = os.path.join(tmp, "kaynak")
            output_dir = os.path.join(tmp, "paketler")
            os.makedirs(source_dir)
            os.makedirs(output_dir)
            allowed = os.path.join(source_dir, "rapor.docx")
            sensitive = os.path.join(source_dir, "gizli.txt")
            Path(allowed).write_bytes(b"rapor")
            Path(sensitive).write_text("gizli", encoding="utf-8")
            source_project = os.path.join(source_dir, "proje.json")
            veri = {
                "kunye": {"sahibi": "Paket", "not": sensitive},
                "dosyalar": {
                    "word_path": allowed,
                    "not_path": sensitive,
                },
                "ayarlar": {},
            }

            info = proje_paketi_olustur(
                veri,
                source_project,
                output_dir,
            )

            self.assertEqual(info["copied_file_count"], 1)
            manifest = json.loads(Path(info["manifest_path"]).read_text(encoding="utf-8"))
            packaged = json.loads(Path(info["project_path"]).read_text(encoding="utf-8"))
            manifest_text = json.dumps(manifest, ensure_ascii=False)
            package_meta_text = json.dumps(packaged[PAKET_META_KEY], ensure_ascii=False)
            self.assertEqual(manifest["source_project"], "proje.json")
            self.assertNotIn(os.path.abspath(tmp), manifest_text)
            self.assertNotIn("original_value", manifest_text)
            self.assertNotIn("original_value", package_meta_text)
            self.assertEqual(packaged["kunye"]["not"], "gizli.txt")
            self.assertEqual(packaged["dosyalar"]["not_path"], "gizli.txt")
            self.assertNotIn(os.path.abspath(tmp), json.dumps(packaged, ensure_ascii=False))

    def test_paket_kaydinda_da_yalniz_beyaz_listeli_yol_goreli_yapilir(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = os.path.join(tmp, "assets")
            os.makedirs(asset_dir)
            asset = os.path.join(asset_dir, "rapor.docx")
            Path(asset).write_bytes(b"rapor")
            project_path = os.path.join(tmp, "proje.json")
            veri = {
                "kunye": {"not": asset},
                "dosyalar": {"word_path": asset, "not_path": asset},
                PAKET_META_KEY: {
                    "version": 1,
                    "_runtime_root": tmp,
                    "references": [
                        {
                            "data_path": ["kunye", "not"],
                            "relative_path": asset,
                            "original_value": asset,
                        },
                        {
                            "data_path": ["dosyalar", "word_path"],
                            "source_name": asset,
                            "relative_path": asset,
                            "original_value": asset,
                        },
                    ],
                },
            }

            result = paket_proje_verisini_kayda_hazirla(veri, project_path)

            self.assertEqual(result["dosyalar"]["word_path"], "assets/rapor.docx")
            self.assertEqual(result["dosyalar"]["not_path"], "rapor.docx")
            self.assertEqual(result["kunye"]["not"], "rapor.docx")
            references = result[PAKET_META_KEY]["references"]
            self.assertEqual(
                [item["data_path"] for item in references],
                [["dosyalar", "word_path"]],
            )
            self.assertTrue(all("original_value" not in item for item in references))
            self.assertTrue(all(not os.path.isabs(item["relative_path"]) for item in references))
            self.assertTrue(all(os.path.basename(item["source_name"]) == item["source_name"] for item in references))

    def test_paket_symlink_uzerinden_kok_disina_cikmaz(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = os.path.join(tmp, "paket")
            assets_dir = os.path.join(package_dir, "assets")
            os.makedirs(assets_dir)
            outside = os.path.join(tmp, "gizli.docx")
            Path(outside).write_bytes(b"gizli")
            link = os.path.join(assets_dir, "bag.docx")
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symlink olusturulamadi: {exc}")
            veri = {
                "dosyalar": {"word_path": "assets/bag.docx"},
                PAKET_META_KEY: {
                    "version": 1,
                    "references": [{
                        "data_path": ["dosyalar", "word_path"],
                        "source_name": "bag.docx",
                        "relative_path": "assets/bag.docx",
                    }],
                },
            }

            result = paket_proje_verisini_yukle(
                veri,
                os.path.join(package_dir, "proje.json"),
            )

            self.assertEqual(result["dosyalar"]["word_path"], "assets/bag.docx")


class GizliBilgiRedaksiyonTestleri(unittest.TestCase):
    def test_merkezi_redaksiyon_url_header_ve_ham_anahtari_maskeler(self):
        secret = "AIzaSuperSecretValue123"
        text = (
            f"https://example.test?key={secret} "
            f"x-goog-api-key: {secret} "
            f'"gemini_api_key": "{secret}"'
        )

        redacted = performans.gizli_bilgileri_maskele(text, (secret,))

        self.assertNotIn(secret, redacted)
        self.assertIn("***", redacted)

    def test_exception_logu_anahtari_yazmaz(self):
        secret = "AIzaSuperSecretValue123"
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "error.log")
            with patch.object(performans, "ERROR_LOG_PATH", log_path):
                try:
                    raise RuntimeError(f"GET https://example.test?key={secret}")
                except RuntimeError as exc:
                    performans.log_exception("api", exc_value=exc)

            content = Path(log_path).read_text(encoding="utf-8")
            self.assertNotIn(secret, content)
            self.assertIn("?key=***", content)

    def test_spt_gemini_anahtari_url_yerine_headerda_ve_hata_metni_maskeli(self):
        secret = "AIzaSuperSecretValue123"

        class Response:
            status_code = 400
            text = f"geçersiz anahtar: {secret}"

            def json(self):
                return {"error": {"message": self.text}}

        with patch("spt_saglayicilar.http_post_with_retry", return_value=Response()) as post:
            with self.assertRaises(RuntimeError) as raised:
                spt_ai_metin_iste(
                    aktif="gemini",
                    ayarlar={"gemini_api_key": secret},
                    prompt="oku",
                    image_b64="AA==",
                    mime_type="image/jpeg",
                    timeout=1,
                )

        url = post.call_args.args[1]
        headers = post.call_args.kwargs["headers"]
        self.assertNotIn(secret, url)
        self.assertNotIn("?key=", url)
        self.assertEqual(headers["x-goog-api-key"], secret)
        self.assertNotIn(secret, str(raised.exception))

    def test_diger_gemini_akislari_da_header_kullanir_ve_hata_maskeler(self):
        secret = "AIzaSuperSecretValue123"
        calls = []

        class Response:
            status_code = 400
            text = f"geçersiz anahtar: {secret}"

            def json(self):
                return {"error": {"message": self.text}}

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        fake_requests = types.SimpleNamespace(post=post)
        settings = {"aktif_motor": "gemini", "gemini_api_key": secret}
        with patch.dict(sys.modules, {"requests": fake_requests}):
            with self.assertRaises(RuntimeError) as ai_error:
                _ai_ile_analiz_et("düzelt", ayarlar=settings, motor="gemini")
            with patch(
                "spt_okuma_motoru.spt_ayarlarini_yukle",
                return_value=settings,
            ):
                with self.assertRaises(RuntimeError) as report_error:
                    _ai_metin_revizyonu(
                        "düzelt",
                        [{"unit_id": "p:0", "label": "Paragraf", "text": "Metin"}],
                        motor="gemini",
                    )

        self.assertEqual(len(calls), 2)
        for url, kwargs in calls:
            self.assertNotIn(secret, url)
            self.assertNotIn("?key=", url)
            self.assertEqual(kwargs["headers"]["x-goog-api-key"], secret)
        self.assertNotIn(secret, str(ai_error.exception))
        self.assertNotIn(secret, str(report_error.exception))


class PaylasilabilirCiktiGuvenlikTestleri(unittest.TestCase):
    def test_kalite_manifestosu_goreli_yol_yazar_ve_dogrular(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "sonuc.txt")
            manifest_path = os.path.join(tmp, "kalite.json")
            Path(output_path).write_text("RaporPro kalite " * 20, encoding="utf-8")
            report = cikti_dosyalari_denetle([output_path])

            kalite_manifestosu_yaz(manifest_path, report)

            manifest_text = Path(manifest_path).read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["files"][0]["path"], "sonuc.txt")
            self.assertNotIn(os.path.abspath(tmp), manifest_text)
            self.assertEqual(kalite_manifestosu_dogrula(manifest_path)["state"], "TEMİZ")

    def test_kalite_manifestosu_mutlak_ve_kok_disi_yollari_okumaz(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_dir = os.path.join(tmp, "manifest")
            os.makedirs(manifest_dir)
            outside = os.path.join(tmp, "gizli.txt")
            Path(outside).write_text("gizli", encoding="utf-8")
            manifest_path = os.path.join(manifest_dir, "kalite.json")
            Path(manifest_path).write_text(
                json.dumps({
                    "files": [
                        {"path": outside, "sha256": "x"},
                        {"path": "../gizli.txt", "sha256": "x"},
                    ],
                }),
                encoding="utf-8",
            )

            with patch("cikti_kalite.dosya_parmak_izi") as digest:
                result = kalite_manifestosu_dogrula(manifest_path)

            digest.assert_not_called()
            self.assertEqual(result["state"], "HATA")

    def test_kml_proje_yolunun_yalniz_dosya_adini_yazar(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = os.path.join(tmp, "gizli", "proje.json")
            output_path = os.path.join(tmp, "biten.kml")
            biten_isler_kml_yaz(
                [{
                    "name": "Proje",
                    "address": "Adres",
                    "ada": "1",
                    "parsel": "2",
                    "completed_at": "2026-01-01",
                    "path": project_path,
                    "lat": 40.0,
                    "lon": 26.0,
                }],
                output_path,
            )

            text = Path(output_path).read_text(encoding="utf-8")
            self.assertIn("Dosya: proje.json", text)
            self.assertNotIn(os.path.abspath(tmp), text)

    def test_spt_excel_yolu_basename_yazar_ve_formul_metinlerini_kacar(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "=foto.jpg")
            output_path = os.path.join(tmp, "spt.xlsx")
            kayit = SPTKaydi(
                sondaj_no="=1+1",
                derinlik="1.50",
                v15="2",
                v30="3",
                v45="4",
                n30="7",
                guven="99",
                uyari="=HYPERLINK(\"https://example.test\")",
                kaynak="@kaynak",
                kaynak_yolu=source_path,
                raw={"motor": "+motor", "model": "-model"},
            )

            spt_kaynak_raporu_kaydet([kayit], output_path)

            workbook = load_workbook(output_path, data_only=False, read_only=True)
            try:
                sheet = workbook.active
                self.assertEqual(sheet["A2"].value, "'=1+1")
                self.assertEqual(sheet["H2"].value, "'=HYPERLINK(\"https://example.test\")")
                self.assertEqual(sheet["K2"].value, "'+motor")
                self.assertEqual(sheet["L2"].value, "'-model")
                self.assertEqual(sheet["O2"].value, "'@kaynak")
                self.assertEqual(sheet["P2"].value, "'=foto.jpg")
                self.assertNotEqual(sheet["A2"].data_type, "f")
                self.assertNotIn(os.path.abspath(tmp), str(sheet["P2"].value))
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()
