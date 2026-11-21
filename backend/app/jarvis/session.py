"""One question → one directed script. Picks the brain: Claude when configured (phase 4,
next step), otherwise the demo brain."""

from sqlalchemy.orm import Session

from app.jarvis import demo, scene


def ask(session: Session, question: str) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("domanda vuota")
    script = demo.answer(session, question)
    out = scene.direct(session, script)
    return out | {"domanda": question, "modalita": script.get("modalita", "dimostrativa"),
                  "intento": script.get("intento")}
