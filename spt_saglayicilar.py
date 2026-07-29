# Dosya: RaporPro/spt_saglayicilar.py
import time

from performans import gizli_bilgileri_maskele
from yardimcilar import safe_float


def http_post_with_retry(
    requests_module,
    url,
    *,
    headers,
    payload,
    timeout,
    max_attempts=3,
    stop_event=None,
):
    """Gecici API hatalarini sinirli ve kontrollu bicimde yeniden dene."""
    last_response = None
    last_error = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("SPT okuma durduruldu.")
        try:
            response = requests_module.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            last_response = response
            if response.status_code not in (408, 409, 429) and response.status_code < 500:
                return response
            if attempt >= max_attempts:
                return response
            headers_map = getattr(response, "headers", {}) or {}
            retry_after = safe_float(headers_map.get("Retry-After", ""))
            time.sleep(retry_after if retry_after > 0 else min(0.7 * (2 ** (attempt - 1)), 3.0))
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise
            time.sleep(min(0.7 * (2 ** (attempt - 1)), 3.0))
    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise RuntimeError("API istegi tamamlanamadi.")


def spt_ai_metin_iste(
    *,
    aktif,
    ayarlar,
    prompt,
    image_b64,
    mime_type,
    timeout,
    stop_event=None,
    openai_model="gpt-4o-mini",
):
    """Secili saglayiciya SPT gorsel istegini gonder ve ham metni dondur."""
    try:
        import requests
    except Exception as exc:
        raise RuntimeError(f"requests yüklenemedi: {exc}") from exc

    if aktif in ("openai", "groq"):
        is_openai = aktif == "openai"
        url = "https://api.openai.com/v1/chat/completions" if is_openai else "https://api.groq.com/openai/v1/chat/completions"
        api_key = ayarlar["openai_api_key"] if is_openai else ayarlar["groq_api_key"]
        model_name = openai_model if is_openai else "meta-llama/llama-4-scout-17b-16e-instruct"
        payload = {
            "model": model_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            }],
            "temperature": 0.1,
        }
        response = http_post_with_retry(
            requests,
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload,
            timeout=timeout,
            stop_event=stop_event,
        )
        if response.status_code != 200:
            detail = gizli_bilgileri_maskele(response.text[:500], (api_key,))
            raise RuntimeError(f"{aktif.upper()} hata kodu {response.status_code}: {detail}")
        try:
            text_response = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(f"{aktif.upper()} yaniti beklenen bicimde degil.") from exc
        return text_response, model_name

    model_name = "gemini-2.5-pro" if aktif == "gemini_pro" else "gemini-2.5-flash"
    api_key = ayarlar["gemini_api_key"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": image_b64}}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    response = http_post_with_retry(
        requests,
        url,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        payload=payload,
        timeout=timeout,
        stop_event=stop_event,
    )
    if response.status_code != 200:
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except Exception:
            message = response.text
        detail = gizli_bilgileri_maskele(str(message)[:500], (api_key,))
        raise RuntimeError(f"GEMINI hata kodu {response.status_code}: {detail}")
    try:
        text_response = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("GEMINI yaniti bos veya beklenen bicimde degil.") from exc
    return text_response, model_name
