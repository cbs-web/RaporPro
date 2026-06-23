# Dosya: RaporPro/raporlama_litoloji.py
import re
import unicodedata

from yardimcilar import safe_float
from raporlama_deger import clean_val

IRI_DANELILER = ['Killi Kum', 'Kum', 'Kumlu', 'Siltli Killi Çakıl', 'Siltli Kum', 'Çakıllı Killi Kum', 'Çakıllı Kum', 'Çakıllı Siltli Kum', 'Kumlu Siltli Killi Çakıl', 'Çakıl']
INCE_DANELILER = ['Kil', 'Kumlu Kil', 'Çakıllı Kil', 'Siltli Kil', 'Kumlu Silt', 'Silt']
LITOLOJI_DAGILIM_BIRIMLERI = [
    "Çakıl",
    "Siltli Çakıl",
    "Killi Çakıl",
    "Çakıllı Kum",
    "Çakıllı Killi Kum",
    "Çakıllı Siltli Kum",
    "Siltli Kum",
    "Kum",
    "Killi Kum",
    "Kil",
    "Kumlu Kil",
    "Çakıllı Kil",
    "Kumlu Silt",
    "Kumlu Siltli Killi Çakıl",
]

def _normalize_litoloji_text(text):
    value = "" if text is None else str(text).strip()
    if not value:
        return ""
    lowered = value.casefold()
    if any(marker in lowered for marker in ("ã", "ä", "å")):
        try:
            fixed = lowered.encode("latin1").decode("utf-8").casefold()
            if fixed:
                lowered = fixed
        except Exception:
            pass
    replacements = {
        "ı": "i", "İ": "i", "ç": "c", "ğ": "g",
        "ö": "o", "ş": "s", "ü": "u",
    }
    for old, new in replacements.items():
        lowered = lowered.replace(old, new)
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()

def litoloji_dagilim_birimi(tanim):
    normalized = _normalize_litoloji_text(tanim)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        return None

    base_tokens = {"cakil", "kum", "kil", "silt"}
    last_base_idx = -1
    last_base = ""
    for idx, token in enumerate(tokens):
        if token in base_tokens:
            last_base_idx = idx
            last_base = token
    if last_base_idx < 0:
        return None

    modifiers = set(tokens[:last_base_idx])
    has_cakilli = "cakilli" in modifiers or "cakil" in modifiers
    has_kumlu = "kumlu" in modifiers or "kum" in modifiers
    has_killi = "killi" in modifiers or "kil" in modifiers
    has_siltli = "siltli" in modifiers or "silt" in modifiers

    if last_base == "cakil":
        if has_kumlu and has_siltli and has_killi:
            return "Kumlu Siltli Killi Çakıl"
        if has_killi:
            return "Killi Çakıl"
        if has_siltli:
            return "Siltli Çakıl"
        return "Çakıl"

    if last_base == "kum":
        if has_cakilli and has_killi:
            return "Çakıllı Killi Kum"
        if has_cakilli and has_siltli:
            return "Çakıllı Siltli Kum"
        if has_cakilli:
            return "Çakıllı Kum"
        if has_killi:
            return "Killi Kum"
        if has_siltli:
            return "Siltli Kum"
        return "Kum"

    if last_base == "kil":
        if has_cakilli:
            return "Çakıllı Kil"
        if has_kumlu:
            return "Kumlu Kil"
        return "Kil"

    if last_base == "silt" and has_kumlu:
        return "Kumlu Silt"

    return None

def _fmt_litoloji_derinlik(value):
    number = safe_float(value)
    if abs(number - round(number)) < 0.001:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")

def litoloji_dagilim_paragraflari(sondajlar):
    groups = {unit: {} for unit in LITOLOJI_DAGILIM_BIRIMLERI}
    for sondaj in sondajlar or []:
        kuyu_no = clean_val(sondaj.get("no", ""))
        merged_layers = []
        for lit in sondaj.get("litoloji", []) or []:
            if len(lit) < 3:
                continue
            unit_name = litoloji_dagilim_birimi(lit[2])
            if not unit_name:
                continue
            top_val = safe_float(lit[0])
            bot_val = safe_float(lit[1])
            if bot_val < top_val:
                top_val, bot_val = bot_val, top_val
            if merged_layers and merged_layers[-1]["name"] == unit_name and abs(merged_layers[-1]["bot"] - top_val) < 0.05:
                merged_layers[-1]["bot"] = bot_val
            else:
                merged_layers.append({"name": unit_name, "top": top_val, "bot": bot_val})
        for layer in merged_layers:
            groups[layer["name"]].setdefault(kuyu_no, []).append(
                f"{_fmt_litoloji_derinlik(layer['top'])}-{_fmt_litoloji_derinlik(layer['bot'])}"
            )

    paragraphs = []
    for unit_name in LITOLOJI_DAGILIM_BIRIMLERI:
        kuyu_dict = groups.get(unit_name, {})
        parts = []
        for kuyu_no, ranges in kuyu_dict.items():
            parts.append(f"{kuyu_no}'de {', '.join(ranges)}m")
        if parts:
            paragraphs.append(f"{unit_name} birimleri " + ", ".join(parts) + " derinlikleri arasında gözlenmiştir.")
    return paragraphs
