# Dosya: RaporPro/kesit_motor_ayarlari.py
KESIT_ENGINE_DEFAULT = "v2"
KESIT_ENGINE_V1_LABEL = "V1 (Uyumlu)"
KESIT_ENGINE_V2_LABEL = "V2 (Gelişmiş)"
KESIT_ENGINE_LABELS = (KESIT_ENGINE_V1_LABEL, KESIT_ENGINE_V2_LABEL)


def kesit_motoru_normalize(value):
    normalized = str(value or KESIT_ENGINE_DEFAULT).strip().lower()
    if normalized in ("v2", "2", "yeni", "new"):
        return "v2"
    return "v1"


def kesit_motoru_etiketi(value):
    if kesit_motoru_normalize(value) == "v2":
        return KESIT_ENGINE_V2_LABEL
    return KESIT_ENGINE_V1_LABEL


def kesit_motoru_etiketinden(label):
    return "v2" if str(label or "").strip().startswith("V2") else "v1"
