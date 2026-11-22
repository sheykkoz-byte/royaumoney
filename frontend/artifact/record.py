"""Record one answer per demo intent from the running backend (with ElevenLabs audio)."""
import json
import sys
import urllib.request

QUESTIONS = {"greeting": "Ciao Jarvis", "gold": "Come sta l'oro?", "regime": "Qual è il regime?",
             "scenarios": "Cosa dicono gli scenari?", "liquidity": "Liquidità e M2",
             "labour": "Dati sul lavoro", "predictions_intent": "Il mio scenario",
             "fallback": "Che tempo fa?"}

out = {}
for intent, q in QUESTIONS.items():
    req = urllib.request.Request("http://localhost:8000/jarvis/domanda",
                                 json.dumps({"testo": q}).encode(),
                                 {"content-type": "application/json"})
    r = json.load(urllib.request.urlopen(req))
    assert r["intento"] == intent, (intent, r["intento"])
    assert r.get("audio"), f"{intent}: no ElevenLabs audio"
    out[intent] = r | {"tipo": "risposta"}
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, separators=(",", ":"))
print(f"recorded {len(out)} answers")
