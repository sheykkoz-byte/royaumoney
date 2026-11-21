"""Jarvis's voice: ElevenLabs text-to-speech with character timestamps.

Each character of the spoken text gets a start time, so every scene cue (which the scene
director anchors to a character index) fires exactly when its word is pronounced.
In the cloud the network proxy injects the key; locally put ELEVENLABS_API_KEY in .env.
"""

import time

import httpx

from app.config import get_settings

API = "https://api.elevenlabs.io/v1"
OUTPUT_FORMAT = "mp3_44100_128"
PROXY_PLACEHOLDER = "proxy-injected"


class VoiceError(RuntimeError):
    pass


def enabled() -> bool:
    s = get_settings()
    if s.voice == "browser":
        return False
    return s.voice == "elevenlabs" or bool(s.elevenlabs_api_key)


def synthesize(text: str, client: httpx.Client | None = None) -> dict:
    """Audio (base64 MP3) and per-character start/end times, aligned with ``text``."""
    s = get_settings()
    client = client or httpx.Client(timeout=60)
    t0 = time.monotonic()
    r = client.post(
        f"{API}/text-to-speech/{s.elevenlabs_voice_id}/with-timestamps",
        params={"output_format": OUTPUT_FORMAT},
        headers={"xi-api-key": s.elevenlabs_api_key or PROXY_PLACEHOLDER},
        json={"text": text, "model_id": s.elevenlabs_model,
              "voice_settings": {"stability": 0.55, "similarity_boost": 0.75}},
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise VoiceError(f"ElevenLabs HTTP {r.status_code}: {str(detail)[:300]}")
    data = r.json()
    al = data.get("normalized_alignment") or data.get("alignment") or {}
    chars = al.get("characters") or []
    starts = al.get("character_start_times_seconds") or []
    ends = al.get("character_end_times_seconds") or []
    aligned = "".join(chars) == text
    if not aligned:
        al = data.get("alignment") or {}
        chars = al.get("characters") or []
        starts = al.get("character_start_times_seconds") or []
        ends = al.get("character_end_times_seconds") or []
        aligned = "".join(chars) == text
    return {
        "formato": "audio/mpeg",
        "audio_base64": data["audio_base64"],
        "inizio_caratteri": [round(x, 3) for x in starts] if aligned else None,
        "durata": round(ends[-1], 2) if ends else None,
        "allineato": aligned,
        "voce": s.elevenlabs_voice_id,
        "modello": s.elevenlabs_model,
        "latenza_s": round(time.monotonic() - t0, 2),
    }


def cue_times(audio: dict, char_indices: list[int]) -> list[float] | None:
    """Start time of each cue's word, from the character timestamps."""
    starts = audio.get("inizio_caratteri")
    if not starts:
        return None
    last = len(starts) - 1
    return [starts[min(max(i, 0), last)] for i in char_indices]
