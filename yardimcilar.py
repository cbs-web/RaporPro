# Dosya: RaporPro/yardimcilar.py
import json
import os
import re
import math
import string
import difflib
import tempfile
import unicodedata
import pandas as pd
from sabitler import KELIME_HARITASI


def atomic_write_text(path, text, encoding="utf-8"):
    """Metni once ayni klasorde gecici dosyaya yazar, sonra tek hamlede hedefe tasir."""
    target = os.path.abspath(os.fspath(path))
    folder = os.path.dirname(target) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def atomic_json_dump(data, path, *, indent=2, ensure_ascii=False):
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    atomic_write_text(path, text, encoding="utf-8")

def safe_float(val):
    try: return float(str(val).replace(',', '.'))
    except: return 0.0

def temizle_baslik(metin):
    """
    Excel başlıklarını temizler.
    Gama, Fi, Derece gibi sembolleri harfe çevirir.
    """
    if not isinstance(metin, str): return str(metin)
    metin = metin.lower()
    
    # Sembolleri Türkçeleştir/Latinize et
    metin = metin.replace("γ", "g").replace("г", "g") # Gama -> g
    metin = metin.replace("ϕ", "phi").replace("φ", "phi").replace("ø", "phi").replace("Φ", "phi") # Fi -> phi
    metin = metin.replace("°", "derece") # Derece sembolü -> derece kelimesi
    
    # Türkçe karakterler
    metin = metin.replace("ç", "c").replace("ş", "s").replace("ğ", "g").replace("ı", "i").replace("ö", "o").replace("ü", "u")
    
    # Sadece harf ve rakamları bırak (Parantezleri vs temizle)
    return re.sub(r'[^a-z0-9]', '', metin)

_TR_CHAR_MAP = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u",
})

_LITOLOJI_TERIM_GOSTERIM = {
    "bitkisel": "bitkisel",
    "toprak": "toprak",
    "topragi": "toprağı",
    "nebati": "nebati",
    "kil": "kil",
    "killi": "killi",
    "silt": "silt",
    "siltli": "siltli",
    "kum": "kum",
    "kumlu": "kumlu",
    "cakil": "çakıl",
    "cakilli": "çakıllı",
    "moloz": "moloz",
    "molozlu": "molozlu",
    "kiltasi": "kiltaşı",
    "kumtasi": "kumtaşı",
    "cakiltasi": "çakıltaşı",
    "konglomera": "konglomera",
    "bres": "breş",
    "camur": "çamur",
    "tasi": "taşı",
}

_LITOLOJI_BILINEN_TERIMLER = sorted(set(KELIME_HARITASI.keys()) | set(_LITOLOJI_TERIM_GOSTERIM.keys()))


def litoloji_kelime_normalize(metin):
    text = str(metin or "").strip().casefold().translate(_TR_CHAR_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text)


def litoloji_yazim_uyarilari(litoloji_text):
    text = "" if litoloji_text is None else str(litoloji_text).strip()
    if not text:
        return []

    raw_tokens = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", text)
    normalized = [(raw, litoloji_kelime_normalize(raw)) for raw in raw_tokens]
    normalized = [(raw, token) for raw, token in normalized if token and not token.isdigit()]
    if not normalized:
        return []

    warnings = []
    seen = set()
    known_found = False
    for raw, token in normalized:
        if token in _LITOLOJI_BILINEN_TERIMLER:
            known_found = True
            continue
        if len(token) < 3:
            continue
        match = difflib.get_close_matches(token, _LITOLOJI_BILINEN_TERIMLER, n=1, cutoff=0.82)
        if match:
            suggestion = _LITOLOJI_TERIM_GOSTERIM.get(match[0], match[0])
            key = (raw.casefold(), suggestion)
            if key not in seen:
                warnings.append(f"'{raw}' yazımı '{suggestion}' olabilir.")
                seen.add(key)

    if not known_found and litoloji_cozumle(text) == "tanimsiz":
        warnings.append("Litoloji tanımında tanınan ana birim yok.")
    return warnings

def zemin_sinifi_cevir(orijinal_sinif):
    if pd.isna(orijinal_sinif): return "Tanımsız"
    kod = str(orijinal_sinif).strip()
    harita = {
        'GW': 'Çakıl', 'GP': 'Çakıl', 'GrP': 'Çakıl', 'GrW': 'Çakıl', 'GM': 'Siltli Çakıl', 'GC': 'Killi Çakıl',
        'grSaP': 'Çakıllı Kum', 'grSaW': 'Çakıllı Kum', 'grSaM': 'Çakıllı Kum',
        'grclSa': 'Çakıllı Killi Kum',
        'grsiSaP': 'Çakıllı Siltli Kum', 'grsiSaW': 'Çakıllı Siltli Kum', 'grsiSaM': 'Çakıllı Siltli Kum',
        'siSaP': 'Siltli Kum', 'siSaW': 'Siltli Kum', 'siSaM': 'Siltli Kum',
        'SW': 'Kum', 'SP': 'Kum', 'SaP': 'Kum', 'SaW': 'Kum', 'SM': 'Siltli Kum', 'SC': 'Killi Kum', 'siSa': 'Siltli Kum', 'clSa': 'Killi Kum',
        'CL': 'Kil', 'CH': 'Kil', 'CI': 'Kil', 'CIH': 'Kil', 'CIM': 'Kil', 'CIL': 'Kil',
        'saCIL': 'Kumlu Kil', 'saCIM': 'Kumlu Kil', 'saCIH': 'Kumlu Kil', 'saCI': 	'Kumlu Kil',
       	'saClH': 	'Kumlu Kil', 	'saCIH':'Kumlu Kil','saCIM':'Kumlu Kil','saClM':'Kumlu Kil','saClL':'Kumlu Kil',
        'grCl': 'Çakıllı Kil', 'grCL': 'Çakıllı Kil', 'grCH': 'Çakıllı Kil', 'grClH': 'Çakıllı Kil', 'grCIH': 'Çakıllı Kil', 'grCIL': 'Çakıllı Kil', 'grCIM': 'Çakıllı Kil',
        'saSi': 'Kumlu Silt', 'sasiclGr': 'Kumlu Siltli Killi Çakıl', 'saSiClGr': 'Kumlu Siltli Killi Çakıl', 'sasiclgr': 'Kumlu Siltli Killi Çakıl'
    }
    for k, v in harita.items():
        if k.lower() == kod.lower(): return v
    return kod

def haversine_distance(lat1, lon1, lat2, lon2):
    try:
        R = 6371000; phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1); dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))
    except: return 0.0

def litoloji_cozumle(litoloji_text):
    if litoloji_text is None: return "tanimsiz"
    try:
        if isinstance(litoloji_text, float) and math.isnan(litoloji_text): return "tanimsiz"
    except: pass
    
    s = str(litoloji_text).strip()
    if not s or s.lower() in ["nan", "none", "null", "-", ""]: return "tanimsiz"

    lit = s.lower()
    lit = lit.replace("ı", "i").replace("ğ", "g").replace("ş", "s").replace("ç", "c").replace("ö", "o").replace("ü", "u")
    lit = re.sub(r"\s+", " ", lit)

    tokens = re.findall(r"[a-z0-9]+", lit)
    if not tokens: return "tanimsiz"

    phrase_map = {
        ("cakil", "tasi"): "ct",
        ("kum", "tasi"): "kt",
        ("kil", "tasi"): "kit",
        ("silt", "tasi"): "kit",
        ("camur", "tasi"): "kit",
    }

    # Kesit pattern'i sondaj litoloji taniminin sondaki anlamli birimine gore secilir.
    # Ornek: "az killi kum" -> kum; "kumlu kil" -> kil; "kumtasi bloklu kil" -> kil.
    for idx in range(len(tokens) - 1, -1, -1):
        token = tokens[idx].strip(string.punctuation)
        if idx > 0:
            phrase_code = phrase_map.get((tokens[idx - 1], token))
            if phrase_code:
                return phrase_code
        if token in KELIME_HARITASI:
            return KELIME_HARITASI[token]

    return "tanimsiz"
