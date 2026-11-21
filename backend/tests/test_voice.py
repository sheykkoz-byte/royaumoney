import httpx
import pytest

from app.jarvis import voice


def fake_client(text: str, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/with-timestamps")
        assert "xi-api-key" in request.headers
        if status != 200:
            return httpx.Response(status, json={"detail": {"message": "invalid key"}})
        starts = [i * 0.1 for i in range(len(text))]
        return httpx.Response(200, json={
            "audio_base64": "QUJD",
            "alignment": {"characters": list(text), "character_start_times_seconds": starts,
                          "character_end_times_seconds": [s + 0.1 for s in starts]},
        })
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_synthesize_returns_aligned_timestamps():
    text = "L'oro sale."
    a = voice.synthesize(text, client=fake_client(text))
    assert a["allineato"] and a["inizio_caratteri"][2] == pytest.approx(0.2)
    assert a["durata"] == pytest.approx(1.1)
    assert voice.cue_times(a, [2, 6, 999]) == [0.2, 0.6, a["inizio_caratteri"][-1]]


def test_synthesize_error_is_reported():
    with pytest.raises(voice.VoiceError, match="401"):
        voice.synthesize("ciao", client=fake_client("ciao", status=401))


def test_cue_times_without_alignment():
    assert voice.cue_times({"inizio_caratteri": None}, [1, 2]) is None


def test_enabled_modes(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    for mode, key, expected in [("browser", "k", False), ("elevenlabs", "", True),
                                ("auto", "", False), ("auto", "k", True)]:
        monkeypatch.setattr(s, "voice", mode)
        monkeypatch.setattr(s, "elevenlabs_api_key", key)
        assert voice.enabled() is expected
