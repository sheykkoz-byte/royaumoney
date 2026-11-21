"""One question → one directed script. Picks the brain: Claude when configured (phase 4,
next step), otherwise the demo brain."""

import logging

from sqlalchemy.orm import Session

from app.jarvis import demo, scene, voice

log = logging.getLogger(__name__)


def ask(session: Session, question: str) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("domanda vuota")
    script = demo.answer(session, question)
    out = scene.direct(session, script)
    out |= {"domanda": question, "modalita": script.get("modalita", "dimostrativa"),
            "intento": script.get("intento")}
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
