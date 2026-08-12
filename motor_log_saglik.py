# Dosya: RaporPro/motor_log_saglik.py
from __future__ import annotations

import ast
from pathlib import Path


EXPECTED_SIGNATURES = {
    "log_ornek_derinligi_formatla": "(value)",
    "ciz_profesyonel_log": "(sondaj, proje_dict, log_callback=None)",
    "_ciz_strater_stil_log": "(sondaj, proje_dict, log_callback=None)",
    "_ciz_profesyonel_log_eski": "(sondaj, proje_dict, log_callback=None)",
}


def _python_ast(path):
    """Bir Python dosyasini calistirmadan AST olarak oku."""
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _atanan_adlar(target):
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names = set()
        for item in target.elts:
            names.update(_atanan_adlar(item))
        return names
    return set()


def _kopru_importlari(tree):
    """Koprunun son durumda hangi adi hangi yerel kaynaktan sundugunu bul."""
    expected_names = {"GeoEngineLogMixin", "log_ornek_derinligi_formatla"}
    bindings = {}

    for node in tree.body:
        rebound = set()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rebound.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                rebound.update(_atanan_adlar(target))

        for name in rebound & expected_names:
            bindings.pop(name, None)

        if not isinstance(node, ast.ImportFrom) or node.level != 0 or not node.module:
            continue
        for alias in node.names:
            public_name = alias.asname or alias.name
            if public_name in expected_names:
                bindings[public_name] = (node.module, alias.name)

    return bindings


def _yerel_modul_yolu(root, module_name):
    parts = module_name.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        raise ImportError(f"gecersiz kaynak modul adi: {module_name}")
    module_path = root.joinpath(*parts).with_suffix(".py")
    if not module_path.is_file():
        raise ImportError(f"kaynak modul bulunamadi: {module_path}")
    return module_path


def _ast_imzasi(function_node):
    """inspect.signature ile ayni temel bicimde bir AST fonksiyon imzasi uret."""
    args = function_node.args
    positional = [*args.posonlyargs, *args.args]
    positional_defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)

    def argument_text(argument, default=None, prefix=""):
        text = f"{prefix}{argument.arg}"
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            text += f"={ast.unparse(default)}"
        return text

    items = []
    posonly_count = len(args.posonlyargs)
    for index, (argument, default) in enumerate(zip(positional, positional_defaults), start=1):
        items.append(argument_text(argument, default))
        if posonly_count and index == posonly_count:
            items.append("/")

    if args.vararg is not None:
        items.append(argument_text(args.vararg, prefix="*"))
    elif args.kwonlyargs:
        items.append("*")

    for argument, default in zip(args.kwonlyargs, args.kw_defaults):
        items.append(argument_text(argument, default))

    if args.kwarg is not None:
        items.append(argument_text(args.kwarg, prefix="**"))

    signature = f"({', '.join(items)})"
    if function_node.returns is not None:
        signature += f" -> {ast.unparse(function_node.returns)}"
    return signature


def _ust_seviye_tanim(tree, name, expected_type):
    for node in tree.body:
        if isinstance(node, expected_type) and node.name == name:
            return node
    return None


def _kaynak_ast(root, module_name, cache):
    if module_name not in cache:
        cache[module_name] = _python_ast(_yerel_modul_yolu(root, module_name))
    return cache[module_name]


def _load_motor_log_module(base_dir):
    # Yalniz acikca istenen dinamik saglik kontrolunde kullanilir.
    import importlib.util
    import sys

    module_path = Path(base_dir) / "motor_log.py"
    spec = importlib.util.spec_from_file_location("_raporpro_motor_log_health", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"motor_log.py yuklenemedi: {module_path}")
    module = importlib.util.module_from_spec(spec)
    root = str(Path(base_dir).resolve())
    added_path = False
    if root not in sys.path:
        sys.path.insert(0, root)
        added_path = True
    try:
        spec.loader.exec_module(module)
    finally:
        if added_path:
            try:
                sys.path.remove(root)
            except ValueError:
                pass
    return module


def check_motor_log_bridge(base_dir=None):
    """motor_log koprusunu kaynak dosyalarini calistirmadan denetle."""
    root = Path(base_dir or Path(__file__).resolve().parent)
    problems = []

    motor_log_path = root / "motor_log.py"

    if not motor_log_path.exists():
        problems.append(f"motor_log.py bulunamadi: {motor_log_path}")
    if problems:
        return problems

    try:
        bridge_tree = _python_ast(motor_log_path)
        bindings = _kopru_importlari(bridge_tree)
        source_cache = {}
    except Exception as exc:
        return [f"motor_log kaynak motoru yuklenemedi: {exc}"]

    func_binding = bindings.get("log_ornek_derinligi_formatla")
    if func_binding is None:
        problems.append("log_ornek_derinligi_formatla fonksiyonu yok veya cagrilabilir degil.")
    else:
        try:
            module_name, source_name = func_binding
            source_tree = _kaynak_ast(root, module_name, source_cache)
            func = _ust_seviye_tanim(
                source_tree,
                source_name,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        except Exception as exc:
            return [f"motor_log kaynak motoru yuklenemedi: {exc}"]
        if func is None:
            problems.append("log_ornek_derinligi_formatla fonksiyonu yok veya cagrilabilir degil.")
        else:
            signature = _ast_imzasi(func)
            if signature != EXPECTED_SIGNATURES["log_ornek_derinligi_formatla"]:
                problems.append(f"log_ornek_derinligi_formatla imzasi beklenenden farkli: {signature}")

    mixin_binding = bindings.get("GeoEngineLogMixin")
    if mixin_binding is None:
        problems.append("GeoEngineLogMixin sinifi bulunamadi.")
        return problems

    try:
        module_name, source_name = mixin_binding
        source_tree = _kaynak_ast(root, module_name, source_cache)
        mixin = _ust_seviye_tanim(source_tree, source_name, ast.ClassDef)
    except Exception as exc:
        return [f"motor_log kaynak motoru yuklenemedi: {exc}"]
    if mixin is None:
        problems.append("GeoEngineLogMixin sinifi bulunamadi.")
        return problems

    for method_name in ("ciz_profesyonel_log", "_ciz_strater_stil_log", "_ciz_profesyonel_log_eski"):
        method = next(
            (
                node
                for node in mixin.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
            ),
            None,
        )
        if method is None:
            problems.append(f"{method_name} metodu yok veya cagrilabilir degil.")
            continue
        signature = _ast_imzasi(method)
        if signature != EXPECTED_SIGNATURES[method_name]:
            problems.append(f"{method_name} imzasi beklenenden farkli: {signature}")

    return problems


def check_motor_log_bridge_dynamic(base_dir=None):
    """Kopruyu gercekten yukleyerek tam calisma zamani denetimi yap."""
    import inspect

    root = Path(base_dir or Path(__file__).resolve().parent)
    problems = []
    motor_log_path = root / "motor_log.py"

    if not motor_log_path.exists():
        return [f"motor_log.py bulunamadi: {motor_log_path}"]

    try:
        module = _load_motor_log_module(root)
    except Exception as exc:
        return [f"motor_log kaynak motoru yuklenemedi: {exc}"]

    func = getattr(module, "log_ornek_derinligi_formatla", None)
    if not callable(func):
        problems.append("log_ornek_derinligi_formatla fonksiyonu yok veya cagrilabilir degil.")
    elif str(inspect.signature(func)) != EXPECTED_SIGNATURES["log_ornek_derinligi_formatla"]:
        problems.append(f"log_ornek_derinligi_formatla imzasi beklenenden farkli: {inspect.signature(func)}")

    mixin = getattr(module, "GeoEngineLogMixin", None)
    if mixin is None:
        problems.append("GeoEngineLogMixin sinifi bulunamadi.")
        return problems

    for method_name in ("ciz_profesyonel_log", "_ciz_strater_stil_log", "_ciz_profesyonel_log_eski"):
        method = getattr(mixin, method_name, None)
        if not callable(method):
            problems.append(f"{method_name} metodu yok veya cagrilabilir degil.")
            continue
        signature = str(inspect.signature(method))
        if signature != EXPECTED_SIGNATURES[method_name]:
            problems.append(f"{method_name} imzasi beklenenden farkli: {signature}")

    return problems


def motor_log_bridge_ok(base_dir=None):
    return not check_motor_log_bridge(base_dir)


def motor_log_bridge_dynamic_ok(base_dir=None):
    return not check_motor_log_bridge_dynamic(base_dir)
