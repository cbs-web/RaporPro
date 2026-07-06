# Dosya: RaporPro/ai_motoru.py
import json
import re
import unicodedata

from raporlama import DUZELTME_ETIKET_ADLARI
from spt_okuma_motoru import openai_model_sec, spt_ayarlarini_yukle


AI_MOTOR_ADLARI = ("otomatik", "openai", "gemini", "gemini_pro", "groq", "kural")

DUZELTME_ETIKET_KURALLARI = [
    {
        "tag": "[BINA_BILGILERI]",
        "label": "Bina bilgileri",
        "keywords": ["bina", "blok", "kat", "temel", "yapi", "yük", "yuk", "insaat"],
        "action": "Bina bilgileri tablosunu ve ilgili proje verisini kontrol et.",
    },
    {
        "tag": "[Sondaj]",
        "label": "Sondaj / litoloji tablosu",
        "keywords": ["sondaj", "kuyu", "sk-", "sk ", "litoloji", "zemin tanim", "zemin tanıml", "derinlik", "sondajlar"],
        "action": "Sondaj, litoloji ve sondaj açıklama bilgilerini kontrol et.",
    },
    {
        "tag": "[YASS_TABLO]",
        "label": "Yeraltı suyu tablosu",
        "keywords": ["yass", "yer alti su", "yeraltı su", "su seviyesi", "yeraltisuyu"],
        "action": "Yeraltı suyu ölçüm tablosunu güncelle.",
    },
    {
        "tag": "[YASS_ONERI]",
        "label": "Yeraltı suyu önerisi",
        "keywords": ["yass", "yer alti su", "yeraltı su", "drenaj", "su oner", "su öner"],
        "action": "Yeraltı suyu değerlendirme ve öneri metnini kontrol et.",
    },
    {
        "tag": "[LAB_FIZIK]",
        "label": "Laboratuvar fiziksel deneyler",
        "keywords": ["laboratuvar", "lab", "elek", "atterberg", "kivam", "kıvam", "su muhtev", "dogal birim hacim", "doğal birim hacim"],
        "action": "Laboratuvar fiziksel deney tablolarını güncelle.",
    },
    {
        "tag": "[LAB_MEKANIK]",
        "label": "Laboratuvar mekanik deneyler",
        "keywords": ["mekanik", "kesme", "uc eksenli", "üç eksenli", "serbest basin", "serbest basın", "konsolidasyon"],
        "action": "Laboratuvar mekanik deney tablolarını güncelle.",
    },
    {
        "tag": "[ZEMIN_OZET]",
        "label": "Zemin parametre özeti",
        "keywords": ["zemin parametre", "parametre", "tasima", "taşıma", "oturma", "zemin ozeti", "zemin özeti"],
        "action": "Zemin parametre özetini yeniden üret.",
    },
    {
        "tag": "[LITOLOJI_DAGILIM]",
        "label": "Litoloji dağılımı",
        "keywords": ["litoloji dagilim", "litoloji dağılım", "birim", "kil", "kum", "cakil", "çakıl", "silt", "moloz", "dolgu"],
        "action": "Litoloji dağılım metnini sondaj litolojisine göre yeniden üret.",
    },
    {
        "tag": "[SPT]",
        "label": "SPT tablosu",
        "keywords": ["spt", "n30", "refu", "refü", "darbe", "vurus", "vuruş"],
        "action": "SPT tablosunu ve N30 değerlerini kontrol et.",
    },
    {
        "tag": "[PMT]",
        "label": "Presiyometre tablosu",
        "keywords": ["pmt", "presiyometre", "em", "pl", "limit basinc", "limit basınç"],
        "action": "Presiyometre tablosunu kontrol et.",
    },
    {
        "tag": "[KAYA_TABLO]",
        "label": "Kaya / karot tablosu",
        "keywords": ["kaya", "karot", "tcr", "scr", "rqd", "karot yüz", "karot yuz"],
        "action": "Kaya/karot tablosunu ve TCR-SCR-RQD değerlerini kontrol et.",
    },
    {
        "tag": "[JEO_PARAMETRE]",
        "label": "Jeofizik parametre tablosu",
        "keywords": ["jeofizik", "vs30", "vp", "vs", "serim", "tabaka", "elastisite", "kayma mod", "bulk"],
        "action": "Jeofizik parametre tablosunu yeniden üret.",
    },
    {
        "tag": "[MASW]",
        "label": "MASW tablosu",
        "keywords": ["masw", "vs30", "sismik", "serim", "vs"],
        "action": "MASW tablosunu kontrol et.",
    },
    {
        "tag": "[VP]",
        "label": "VP tablosu",
        "keywords": ["vp", "p dalga", "p-dalga", "boyuna dalga"],
        "action": "VP tablosunu kontrol et.",
    },
    {
        "tag": "[JEO_KOOR]",
        "label": "Jeofizik koordinatlar",
        "keywords": ["jeofizik koordinat", "ss koordinat", "mt koordinat", "koordinat"],
        "action": "Jeofizik koordinat tablosunu kontrol et.",
    },
    {
        "tag": "[MT_TABLO]",
        "label": "Mikrotremör tablosu",
        "keywords": ["mt", "mikrotremor", "mikrotremör", "h/v", "hvsr"],
        "action": "Mikrotremör tablosunu güncelle.",
    },
    {
        "tag": "[JEO_SONUC]",
        "label": "Jeofizik sonuç",
        "keywords": ["jeofizik sonuc", "jeofizik sonuç", "jeofizik degerlendirme", "jeofizik değerlendirme"],
        "action": "Jeofizik sonuç/değerlendirme metnini kontrol et.",
    },
    {
        "tag": "[RESIM_YERBULDURUR]",
        "label": "Yerbuldurur haritası",
        "keywords": ["yerbuldurur", "yer buldurur", "lokasyon"],
        "action": "Yerbuldurur görselini yeniden ekle.",
    },
    {
        "tag": "RESIM:TKGM",
        "label": "TKGM görseli",
        "keywords": ["tkgm", "parsel", "tapu", "kadastro"],
        "action": "TKGM/parsel görselini yeniden ekle.",
    },
    {
        "tag": "RESIM:PGA",
        "label": "PGA görseli",
        "keywords": ["pga", "deprem", "ivme"],
        "action": "PGA görselini yeniden ekle.",
    },
    {
        "tag": "[RESIM_JEOFIZIK]",
        "label": "Jeofizik lokasyon haritası",
        "keywords": ["jeofizik harita", "ss harita", "mt harita", "jeofizik lokasyon"],
        "action": "Jeofizik lokasyon haritasını yeniden ekle.",
    },
    {
        "tag": "RESIM:MJH",
        "label": "Mühendislik jeolojisi haritası",
        "keywords": ["mjh", "muhendislik jeolojisi", "mühendislik jeolojisi", "jeoloji haritasi", "jeoloji haritası"],
        "action": "Mühendislik jeolojisi haritasını yeniden ekle.",
    },
    {
        "tag": "[RESIM_SONDAJ]",
        "label": "Sondaj lokasyon haritası",
        "keywords": ["sondaj harita", "sondaj lokasyon", "vaziyet", "araştirma nokt", "araştırma nokt"],
        "action": "Sondaj lokasyon/vaziyet haritasını yeniden ekle.",
    },
]

ALLOWED_TAGS = tuple(item["tag"] for item in DUZELTME_ETIKET_KURALLARI)


def _yonlendirme_item(
    item_id,
    title,
    description,
    target="rapor",
    action_key="",
    button_text="İlgili Sekmeye Git",
    priority=50,
    tags=None,
    source_text="",
    matched_keywords=None,
):
    return {
        "id": item_id,
        "title": title,
        "description": description,
        "target": target,
        "action_key": action_key or target,
        "button_text": button_text,
        "priority": int(priority),
        "tags": list(tags or []),
        "source_text": str(source_text or "").strip(),
        "matched_keywords": list(matched_keywords or []),
    }


def _norm_contains_any(norm, keywords):
    return bool(_norm_matched_keywords(norm, keywords))


def _norm_word_contains(norm, keyword):
    keyword = _normalize_text(keyword)
    if not keyword:
        return False
    if len(keyword) <= 3 and re.fullmatch(r"[a-z0-9]+", keyword):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", norm))
    return keyword in norm


def _norm_matched_keywords(norm, keywords):
    hits = []
    for keyword in keywords or []:
        if _norm_word_contains(norm, keyword):
            hits.append(keyword)
    return hits


def _standalone_abbrev(text, abbrev):
    return bool(re.search(rf"(?<![A-Za-zÇĞİÖŞÜçğıöşü0-9]){re.escape(abbrev)}(?![A-Za-zÇĞİÖŞÜçğıöşü0-9])", str(text or ""), flags=re.I))


def _duzeltme_maddeleri(text):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return []
    items = []
    current = []
    for line in lines:
        if re.match(r"^\s*\d+\s*[\-\)\.]", line) and current:
            items.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        items.append(" ".join(current).strip())
    return items or [str(text or "").strip()]


def duzeltme_yonlendirmeleri_olustur(text):
    """Düzeltme notu veri girişi gerektiriyorsa kullanıcıya sonraki işi önerir."""
    text = str(text or "").strip()
    if not text:
        return []
    add_words = ["ek", "ilave", "yeni", "eksik", "tamamla", "tamamlansin", "tamamlansın", "isten", "istendi", "yapil", "yapıl", "eklen", "gerekmektedir"]
    items = []

    for source_text in _duzeltme_maddeleri(text):
        norm = _normalize_text(source_text)
        add_context = _norm_contains_any(norm, add_words)

        sondaj_hits = _norm_matched_keywords(norm, ["ek sondaj", "ilave sondaj", "yeni sondaj", "sondaj isten", "sondaj istendi", "sondaj yapil", "sondaj yapıl", "kuyu ac", "kuyu aç"])
        if sondaj_hits:
            items.append(_yonlendirme_item(
                "ek_sondaj",
                "Ek sondaj verisi gir",
                "Önce Sondaj sekmesinde yeni sondajı, koordinatını, litolojisini ve gerekiyorsa SPT/PMT/Kaya verisini ekle. Sonra raporda sondaj, SPT, litoloji dağılımı ve harita bölümlerini yenile.",
                target="sondaj",
                action_key="sondaj_hizli",
                button_text="Sondaj Hızlı Tablo",
                priority=95,
                tags=["[Sondaj]", "[SPT]", "[LITOLOJI_DAGILIM]", "[RESIM_SONDAJ]"],
                source_text=source_text,
                matched_keywords=sondaj_hits,
            ))

        lab_hits = _norm_matched_keywords(norm, ["laboratuvar", "lab", "deney", "atterberg", "elek", "su muhtev", "kivam", "kıvam", "kesme", "konsolidasyon", "serbest basin", "serbest basın"])
        if lab_hits and (add_context or _norm_contains_any(norm, ["laboratuvar deneyi", "lab deneyi"])):
            action_key = "lab_excel" if _norm_contains_any(norm, ["excel", "dosya", "yukle", "yükle", "aktar"]) else "lab_sheet"
            button_text = "Lab Excel Yükle" if action_key == "lab_excel" else "LAB Sheet Aç"
            items.append(_yonlendirme_item(
                "ek_laboratuvar",
                "Laboratuvar verisini ekle veya yenile",
                "Yeni laboratuvar sonuçlarını Lab Excel dosyasıyla yükle veya LAB Sheet içine yapıştır. Sonra laboratuvar fiziksel/mekanik tablolarını ve zemin parametre özetini yenile.",
                target="rapor",
                action_key=action_key,
                button_text=button_text,
                priority=92,
                tags=["[LAB_FIZIK]", "[LAB_MEKANIK]", "[ZEMIN_OZET]"],
                source_text=source_text,
                matched_keywords=lab_hits,
            ))

        spt_hits = _norm_matched_keywords(norm, ["ek spt", "ilave spt", "yeni spt", "spt istendi", "n30", "darbe"])
        if spt_hits and add_context:
            items.append(_yonlendirme_item(
                "ek_spt",
                "SPT verisini ekle veya kontrol et",
                "SPT Merkezi ile yeni SPT değerlerini yükle/oku, sondaja aktar ve çakışma uyarılarını temizle. Sonra SPT tablosunu ve ilgili sondaj bölümlerini yenile.",
                target="sondaj",
                action_key="spt_merkezi",
                button_text="SPT Merkezi",
                priority=90,
                tags=["[SPT]", "[Sondaj]"],
                source_text=source_text,
                matched_keywords=spt_hits,
            ))

        pmt_hits = _norm_matched_keywords(norm, ["pmt", "presiyometre"])
        if pmt_hits and add_context:
            items.append(_yonlendirme_item(
                "ek_pmt",
                "Presiyometre verisini ekle",
                "PMT verisini Sondaj/Workbook girişlerinden ekle. Sonra PMT tablosunu ve zemin parametre özetini yenile.",
                target="sondaj",
                action_key="workbook",
                button_text="Workbook Aç",
                priority=88,
                tags=["[PMT]", "[ZEMIN_OZET]"],
                source_text=source_text,
                matched_keywords=pmt_hits,
            ))

        jeo_hits = _norm_matched_keywords(norm, ["jeofizik", "masw", "sismik", "mikrotremor", "serim"])
        if _standalone_abbrev(source_text, "MT"):
            jeo_hits.append("MT")
        if jeo_hits and add_context:
            items.append(_yonlendirme_item(
                "ek_jeofizik",
                "Jeofizik verisini ekle veya yenile",
                "Jeofizik sekmesinde yeni SS/MT kayıtlarını ve tabaka bilgilerini tamamla. Sonra jeofizik parametre, MASW/VP/MT ve jeofizik sonuç bölümlerini yenile.",
                target="jeofizik",
                action_key="jeofizik",
                button_text="Jeofizik Sekmesi",
                priority=86,
                tags=["[JEO_PARAMETRE]", "[MASW]", "[VP]", "[MT_TABLO]", "[JEO_SONUC]"],
                source_text=source_text,
                matched_keywords=jeo_hits,
            ))

        harita_hits = _norm_matched_keywords(norm, ["harita", "vaziyet", "lokasyon", "mjh", "muhendislik jeolojisi", "mühendislik jeolojisi", "tkgm", "parsel"])
        if harita_hits and add_context:
            items.append(_yonlendirme_item(
                "harita_yenile",
                "Harita/görsel çıktısını yenile",
                "Haritalar sekmesinde ilgili lokasyon veya mühendislik jeolojisi haritasını yeniden oluşturup Word aktarım görselini güncelle.",
                target="haritalar",
                action_key="haritalar",
                button_text="Haritalar Sekmesi",
                priority=78,
                tags=["[RESIM_SONDAJ]", "[RESIM_JEOFIZIK]", "RESIM:MJH", "RESIM:TKGM"],
                source_text=source_text,
                matched_keywords=harita_hits,
            ))

        bina_hits = _norm_matched_keywords(norm, ["bina", "blok", "kat", "temel", "yapi yuk", "yapı yük", "yuk", "yük"])
        if bina_hits and add_context:
            items.append(_yonlendirme_item(
                "bina_bilgisi",
                "Bina bilgisini kontrol et",
                "Bina sekmesinde blok, kat, temel ve yük bilgilerini tamamla. Sonra bina bilgileri tablosunu yenile.",
                target="bina",
                action_key="bina",
                button_text="Bina Sekmesi",
                priority=72,
                tags=["[BINA_BILGILERI]"],
                source_text=source_text,
                matched_keywords=bina_hits,
            ))

    deduped = []
    seen = set()
    for item in sorted(items, key=lambda value: -value.get("priority", 0)):
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)
    return deduped


def _normalize_text(text):
    text = str(text or "").lower()
    text = text.replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def _json_from_text(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass

    first_obj = raw.find("{")
    last_obj = raw.rfind("}")
    if first_obj >= 0 and last_obj > first_obj:
        try:
            return json.loads(raw[first_obj:last_obj + 1])
        except Exception:
            pass

    first_list = raw.find("[")
    last_list = raw.rfind("]")
    if first_list >= 0 and last_list > first_list:
        return json.loads(raw[first_list:last_list + 1])
    raise ValueError("AI yanıtı JSON olarak okunamadı.")


def _clean_tags(tags):
    cleaned = []
    seen = set()
    allowed = set(ALLOWED_TAGS)
    for tag in tags or []:
        tag = str(tag or "").strip()
        if not tag or tag not in allowed or tag in seen:
            continue
        cleaned.append(tag)
        seen.add(tag)
    return cleaned


def _item_normalize(item, fallback_text=""):
    item = dict(item or {})
    tags = _clean_tags(item.get("tags") or item.get("etiketler") or item.get("tag") or [])
    if isinstance(item.get("tag"), str):
        tags = _clean_tags(tags + [item.get("tag")])
    confidence = item.get("confidence", item.get("guven", 60))
    try:
        confidence = int(round(float(str(confidence).replace(",", "."))))
    except Exception:
        confidence = 60
    confidence = max(0, min(100, confidence))
    return {
        "talep": str(item.get("talep") or item.get("request") or fallback_text or "").strip(),
        "konu": str(item.get("konu") or item.get("topic") or "").strip(),
        "islem": str(item.get("islem") or item.get("action") or "").strip(),
        "sekme": str(item.get("sekme") or item.get("tab") or "").strip(),
        "tags": tags,
        "guven": confidence,
        "kaynak": str(item.get("kaynak") or item.get("source") or "").strip(),
    }


def _result(source, items, warnings=None, raw_response=""):
    normalized = []
    tags = []
    seen_items = set()
    for item in items or []:
        clean = _item_normalize(item)
        if not clean["tags"]:
            continue
        key = (clean["talep"], tuple(clean["tags"]))
        if key in seen_items:
            continue
        seen_items.add(key)
        normalized.append(clean)
        tags.extend(clean["tags"])
    return {
        "source": source,
        "items": normalized,
        "tags": _clean_tags(tags),
        "warnings": list(warnings or []),
        "raw_response": raw_response or "",
    }


def duzeltme_metnini_kural_ile_analiz_et(text):
    text = str(text or "").strip()
    if not text:
        return _result("kural", [], ["Düzeltme metni boş."])

    norm = _normalize_text(text)
    items = []
    matched_tags = set()
    for rule in DUZELTME_ETIKET_KURALLARI:
        hits = [kw for kw in rule["keywords"] if _normalize_text(kw) in norm]
        if not hits:
            continue
        matched_tags.add(rule["tag"])
        confidence = 70 + min(20, len(hits) * 5)
        items.append({
            "talep": text,
            "konu": rule["label"],
            "islem": rule["action"],
            "sekme": _sekme_oner(rule["tag"]),
            "tags": [rule["tag"]],
            "guven": confidence,
            "kaynak": "kural",
        })

    if "[Sondaj]" in matched_tags and "[LITOLOJI_DAGILIM]" in matched_tags:
        items.append({
            "talep": text,
            "konu": "Sondaj ve litoloji birlikte etkilenebilir",
            "islem": "Sondaj litolojisi değiştiyse litoloji dağılım metnini de yenile.",
            "sekme": "Rapor",
            "tags": ["[Sondaj]", "[LITOLOJI_DAGILIM]"],
            "guven": 78,
            "kaynak": "kural",
        })

    warnings = []
    if not items:
        warnings.append("Metinden güvenilir bir rapor etiketi çıkarılamadı. Düzeltme Etiketleri ekranından elle seçim yapılabilir.")
    return _result("kural", items, warnings=warnings)


def _sekme_oner(tag):
    if tag in ("[SPT]", "[PMT]", "[KAYA_TABLO]", "[Sondaj]", "[LITOLOJI_DAGILIM]"):
        return "Sondaj / Rapor"
    if tag in ("[LAB_FIZIK]", "[LAB_MEKANIK]", "[ZEMIN_OZET]"):
        return "Rapor / LAB"
    if tag in ("[JEO_PARAMETRE]", "[MASW]", "[VP]", "[JEO_KOOR]", "[MT_TABLO]", "[JEO_SONUC]"):
        return "Jeofizik / Rapor"
    if "RESIM" in tag or tag.startswith("RESIM:"):
        return "Haritalar / Rapor"
    if tag in ("[YASS_TABLO]", "[YASS_ONERI]"):
        return "Sondaj / Rapor"
    if tag == "[BINA_BILGILERI]":
        return "Bina / Rapor"
    return "Rapor"


def _prompt_olustur(text):
    allowed = "\n".join(f"- {tag}: {DUZELTME_ETIKET_ADLARI.get(tag, tag)}" for tag in ALLOWED_TAGS)
    return f"""Sen Zemin Rapor Pro içinde çalışan bir düzeltme asistanısın.
Belediye/kontrolör düzeltme metnini oku ve hangi rapor bölümlerinin yeniden oluşturulması gerektiğini belirle.
Sadece aşağıdaki etiketleri kullan:
{allowed}

Kesin değilsen tags listesini boş bırakma; en yakın ilgili etiketi öner ama guven değerini düşük tut.
Çıktıyı yalnızca JSON olarak döndür:
{{
  "items": [
    {{
      "talep": "düzeltme maddesinin kısa özeti",
      "konu": "düzeltme konusu",
      "islem": "programda yapılacak güvenli işlem",
      "sekme": "ilgili program sekmesi",
      "tags": ["[SPT]"],
      "guven": 0
    }}
  ]
}}

Düzeltme metni:
{text}"""


def _aktif_motor_sec(ayarlar, motor):
    if motor and motor != "otomatik":
        return motor
    aktif = str((ayarlar or {}).get("aktif_motor") or "openai").strip().lower()
    return aktif if aktif in AI_MOTOR_ADLARI and aktif != "otomatik" else "openai"


def _api_key_kontrol(aktif, ayarlar):
    if aktif == "kural":
        return
    if aktif == "openai" and not ayarlar.get("openai_api_key"):
        raise RuntimeError("OpenAI API anahtarı bulunamadı.")
    if aktif in ("gemini", "gemini_pro") and not ayarlar.get("gemini_api_key"):
        raise RuntimeError("Gemini API anahtarı bulunamadı.")
    if aktif == "groq" and not ayarlar.get("groq_api_key"):
        raise RuntimeError("Groq API anahtarı bulunamadı.")


def _ai_ile_analiz_et(text, ayarlar=None, motor=None, timeout=45):
    try:
        import requests
    except Exception as exc:
        raise RuntimeError(f"requests yüklenemedi: {exc}") from exc

    ayarlar = ayarlar or spt_ayarlarini_yukle()
    aktif = _aktif_motor_sec(ayarlar, motor)
    if aktif not in ("openai", "gemini", "gemini_pro", "groq", "kural"):
        raise RuntimeError(f"Desteklenmeyen AI motoru: {aktif}")
    if aktif == "kural":
        return duzeltme_metnini_kural_ile_analiz_et(text)
    _api_key_kontrol(aktif, ayarlar)

    prompt = _prompt_olustur(text)
    if aktif in ("openai", "groq"):
        is_openai = aktif == "openai"
        url = "https://api.openai.com/v1/chat/completions" if is_openai else "https://api.groq.com/openai/v1/chat/completions"
        api_key = ayarlar["openai_api_key"] if is_openai else ayarlar["groq_api_key"]
        model_name = openai_model_sec(ayarlar, "revizyon") if is_openai else "meta-llama/llama-4-scout-17b-16e-instruct"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"} if is_openai else None,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code != 200:
            raise RuntimeError(f"{aktif.upper()} hata kodu {response.status_code}: {response.text[:500]}")
        raw = response.json()["choices"][0]["message"]["content"]
    else:
        model_id = "gemini-2.5-pro" if aktif == "gemini_pro" else "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={ayarlar['gemini_api_key']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"},
        }
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
        if response.status_code != 200:
            try:
                msg = response.json().get("error", {}).get("message", response.text)
            except Exception:
                msg = response.text
            raise RuntimeError(f"GEMINI hata kodu {response.status_code}: {msg[:500]}")
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]

    parsed = _json_from_text(raw)
    if isinstance(parsed, dict):
        items = parsed.get("items", [])
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []
    result = _result(aktif, items, raw_response=raw)
    if not result["items"]:
        fallback = duzeltme_metnini_kural_ile_analiz_et(text)
        fallback["warnings"].insert(0, "AI yanıtı etiket üretemedi; kural tabanlı sonuç gösteriliyor.")
        fallback["source"] = f"{aktif}+kural"
        fallback["raw_response"] = raw
        return fallback
    return result


def belediye_duzeltme_analiz_et(text, ayarlar=None, motor=None, timeout=45, ai_kullan=True):
    text = str(text or "").strip()
    if not text:
        return duzeltme_metnini_kural_ile_analiz_et(text)
    if not ai_kullan:
        return duzeltme_metnini_kural_ile_analiz_et(text)
    try:
        return _ai_ile_analiz_et(text, ayarlar=ayarlar, motor=motor, timeout=timeout)
    except Exception as exc:
        fallback = duzeltme_metnini_kural_ile_analiz_et(text)
        fallback["warnings"].insert(0, f"AI analizi kullanılamadı, kural tabanlı analiz gösteriliyor: {exc}")
        fallback["source"] = "kural"
        return fallback
