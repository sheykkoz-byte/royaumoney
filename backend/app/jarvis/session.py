"""One question → one directed script, with voice. Picks the brain: Claude when
ANTHROPIC_API_KEY is set (``claude_brain``), otherwise — or if Claude fails — the demo brain."""

import logging

from sqlalchemy.orm import Session

from app.jarvis import claude_brain, demo, scene, voice

log = logging.getLogger(__name__)


def ask(session: Session, question: str, history: list[dict] | None = None) -> dict:
    """``history``: earlier turns of this conversation [{"domanda", "parlato"}]."""
    question = (question or "").strip()
    if not question:
        raise ValueError("domanda vuota")
    script = None
    brain_error = None
    if claude_brain.enabled():
        try:
            script = claude_brain.answer(session, question, history)
        except Exception as e:  # the demo brain takes over, and the UI says so
            log.warning("Claude brain failed: %s", e)
            brain_error = str(e)
    if script is None:
        script = demo.answer(session, question)
    out = scene.direct(session, {"parlato": script["parlato"], "scene": script["scene"]})
    out |= {"domanda": question, "modalita": script.get("modalita", "dimostrativa"),
            "intento": script.get("intento")}
    for k in ("strumenti", "scene_scartate", "modello", "token"):
        if k in script:
            out[k] = script[k]
    if brain_error:
        out["cervello_errore"] = brain_error
    if voice.enabled():
        try:
            audio = voice.synthesize(out["parlato"])
            out["audio"] = audio
            times = voice.cue_times(audio, [c["char_index"] for c in out["scene"]])
            if times is not None:
                out["tempi_voce"] = times
        except Exception as e:  # the browser voice takes over
            log.warning("ElevenLabs failed: %s", e)
            out["voce_errore"] = str(e)
    return out
