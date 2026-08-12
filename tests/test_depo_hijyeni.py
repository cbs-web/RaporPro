# Dosya: RaporPro/tests/test_depo_hijyeni.py
import ast
from pathlib import Path

from ortam_kontrolu import (
    RUNTIME_ASSETS,
    check_runtime_assets,
    format_runtime_asset_message,
)


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STANDALONE_MODULES = {"log_motor_karsilastir"}


def _local_imports(path, module_names):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = (node.module.split(".")[0],)
        else:
            continue
        imports.update(name for name in names if name in module_names)
    return imports


def test_ana_uygulama_zincirinde_baglantisiz_modul_yok():
    modules = {path.stem: path for path in ROOT.glob("*.py")}
    edges = {
        name: _local_imports(path, modules)
        for name, path in modules.items()
    }
    reached = set()
    pending = ["main"]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(edges.get(current, ()))

    assert set(modules) - reached == ALLOWED_STANDALONE_MODULES


def test_yerlesik_sablonlar_mevcut_ve_okunabilir():
    assert check_runtime_assets(ROOT) == []


def test_bozuk_ve_eksik_sablonlar_anlasilir_bildirilir(tmp_path):
    first_path, first_purpose = RUNTIME_ASSETS[0]
    corrupt_path = tmp_path / first_path
    corrupt_path.parent.mkdir(parents=True)
    corrupt_path.write_bytes(b"not-a-valid-office-file")

    problems = check_runtime_assets(tmp_path)
    first_problem = next(item for item in problems if item["purpose"] == first_purpose)
    assert "bozuk" in first_problem["reason"]
    assert len(problems) == len(RUNTIME_ASSETS)

    message = format_runtime_asset_message(problems)
    assert first_purpose in message
    assert "Program açık kalacak" in message


def test_eski_kod_ve_sablon_artiklari_geri_donmedi():
    obsolete_paths = (
        ROOT / "ui_spt_okuma_foto.py",
        ROOT / "sondaj_test.py",
        ROOT / "sablonlar" / "taahhutname_sablonu.xlsx",
        ROOT / "sablonlar" / "ekler" / "EK-Yeni-Sondaj-Tutanakli.doc",
        ROOT / "sablonlar" / "ekler" / "EK-Yeni-Sondaj-Tutanakli-Arazi-Deneyli.doc",
    )
    assert not [path for path in obsolete_paths if path.exists()]


def test_python_kaynaklarinda_yeni_mojibake_yok():
    markers = ("\u00c3", "\u00c4", "\u00c5", "\u00c2", "\u00e2\u20ac")
    allowed_legacy_fragments = ("HazÄ±r", "BulunamadÄ±")
    hits = []
    for path in ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8-sig")
        if path.name == "ui_kontrol.py":
            for fragment in allowed_legacy_fragments:
                text = text.replace(fragment, "")
        if any(marker in text for marker in markers):
            hits.append(path.name)
    assert hits == []
