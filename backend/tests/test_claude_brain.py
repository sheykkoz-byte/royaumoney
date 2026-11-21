import json
from types import SimpleNamespace as NS

import pytest

from app.jarvis import claude_brain


class FakeClient:
    """Plays back scripted responses and records the requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        return self.responses.pop(0)


def tool_use(name, args, id_="t1"):
    return NS(type="tool_use", name=name, input=args, id=id_)


def text(obj):
    return NS(type="text", text=json.dumps(obj, ensure_ascii=False))


def resp(content, stop="end_turn"):
    return NS(content=content, stop_reason=stop, model="claude-opus-5-5",
              usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


@pytest.fixture
def fake_tools(monkeypatch):
    calls = []

    def call(session, name, args):
        calls.append((name, args))
        return {"id": "GOLD", "ultimo": {"valore": 3533.28, "data": "2026-11-20"},
                "massimo": {"valore": 5318.0}}
    monkeypatch.setattr(claude_brain.tools, "call", call)
    return calls


def test_tool_loop_then_script(fake_tools):
    final = {"parlato": "L'oro ha chiuso a 3.533 dollari, lontano dal massimo di 5.318.",
             "scene": [{"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD"},
                       {"alla_parola": "massimo", "azione": "mostra_livello", "su": "GOLD",
                        "valore": 5318, "etichetta": "Massimo"}]}
    client = FakeClient([
        resp([tool_use("query_serie", {"id": "GOLD"})], stop="tool_use"),
        resp([text(final)]),
    ])
    out = claude_brain.answer(None, "Come sta l'oro?", client=client)
    assert fake_tools == [("query_serie", {"id": "GOLD"})]
    assert out["parlato"] == final["parlato"] and len(out["scene"]) == 2
    assert out["strumenti"] == ["query_serie"] and out["scene_scartate"] == []
    # The second request carries the tool result for the right tool_use id
    last_user = client.requests[1]["messages"][-1]
    assert last_user["content"][0]["tool_use_id"] == "t1"
    # System prompt is cached; final answer constrained by the schema
    req = client.requests[0]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"]["format"]["schema"] == claude_brain.SCRIPT_SCHEMA


def test_invented_number_in_a_cue_is_dropped(fake_tools):
    final = {"parlato": "L'oro può salire a 4.200.",
             "scene": [{"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD"},
                       {"alla_parola": "salire", "azione": "mostra_livello", "su": "GOLD",
                        "valore": 4200}]}
    client = FakeClient([resp([tool_use("query_serie", {"id": "GOLD"})], stop="tool_use"),
                         resp([text(final)])])
    out = claude_brain.answer(None, "E l'oro?", client=client)
    assert [c["azione"] for c in out["scene"]] == ["apri_grafico"]
    assert "4200" in out["scene_scartate"][0]


def test_history_is_sent_before_the_question(fake_tools):
    client = FakeClient([resp([text({"parlato": "Sì.", "scene": []})])])
    claude_brain.answer(None, "Confermo", history=[{"domanda": "Registra", "parlato": "Ok?"}],
                        client=client)
    msgs = client.requests[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"].endswith("Confermo")


def test_refusal_raises(fake_tools):
    client = FakeClient([resp([], stop="refusal")])
    with pytest.raises(claude_brain.BrainError):
        claude_brain.answer(None, "x", client=client)


def test_session_falls_back_to_demo_when_claude_fails(session, monkeypatch):
    from app.jarvis import session as jarvis

    monkeypatch.setattr(jarvis.claude_brain, "enabled", lambda: True)
    monkeypatch.setattr(jarvis.claude_brain, "answer",
                        lambda *a, **k: (_ for _ in ()).throw(claude_brain.BrainError("boom")))
    monkeypatch.setattr(jarvis.voice, "enabled", lambda: False)
    out = jarvis.ask(session, "Qual è il regime?")
    assert out["modalita"] == "dimostrativa" and out["cervello_errore"] == "boom"
