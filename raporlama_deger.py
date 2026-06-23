# Dosya: RaporPro/raporlama_deger.py
import pandas as pd

from performans import log_exception


def _log_silent(name, exc):
    log_exception(f"raporlama_deger.{name}", exc_value=exc)

def clean_val(val):
    if val is None: return "-"
    s = str(val).strip().replace('\n', '').replace('\r', '').replace('\x0b', '').replace('\v', '')
    return s if s else "-"

def fmt_jeo(val):
    if val is None or val == "-" or str(val).strip() == "" or pd.isna(val): return "-"
    try:
        f = float(str(val).replace(",", "."))
        if f == int(f): return str(int(f)) 
        return "{:.2f}".format(f).replace(".", ",") 
    except Exception as exc:
        _log_silent("fmt_jeo", exc)
        return str(val).replace(".", ",")

def jeofizik_vp_layers_sadelestir(layers):
    sade_layers = []
    onceki_vp = None
    for layer in layers or []:
        vp_key = fmt_jeo(layer.get("vp", "-"))
        if vp_key != "-" and vp_key == onceki_vp:
            continue
        sade_layers.append(layer)
        onceki_vp = vp_key if vp_key != "-" else None
    return sade_layers

def read_table_file(path, header=None):
    if str(path).lower().endswith(".csv"):
        return pd.read_csv(path, header=header)
    return pd.read_excel(path, header=header)
