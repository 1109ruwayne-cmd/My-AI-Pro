"""Tests for the connectors: health checks, routing, and real streaming against the mocks."""
import json
import sys

import httpx

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import connectors  # noqa: E402

BASE = "http://127.0.0.1:9420"
PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def collect(gen, limit=400):
    out = []
    for i, ev in enumerate(gen):
        out.append(ev)
        if i > limit:
            break
    return out


def text_of(events):
    return "".join(e.get("text", "") for e in events if e["type"] == "delta")


def cfg_with(**engines):
    cfg = {"engines": connectors.engine_defaults(), "auto_route": True,
           "vtuber_audio": True, "context_chars": 60000, "history_messages": 20}
    for eid, patch in engines.items():
        cfg["engines"][eid].update(patch)
    return cfg


HISTORY = [{"role": "user", "content": "hello there"},
           {"role": "assistant", "content": "hi"},
           {"role": "user", "content": "the real question"}]

print("\n== 1. health checks against the mocks ==")
cfg = cfg_with(
    orca={"enabled": True, "url": "http://127.0.0.1:9411/v1", "model": "orca-mini"},
    dify={"enabled": True, "url": "http://127.0.0.1:9412/v1", "key": "app-good-key"},
    openhands={"enabled": True, "url": "http://127.0.0.1:9413", "key": "oh-secret"},
    vtuber={"enabled": True, "url": "http://127.0.0.1:9414"},
)
for eid, expect_models in [("orca", True), ("dify", False), ("openhands", True), ("vtuber", False)]:
    r = connectors.health(cfg, eid, connectors.engine_config(cfg, eid)["key"], timeout=8)
    check(f"{eid} healthy", r["ok"], r.get("detail"))
    if expect_models:
        check(f"{eid} returned models", bool(r.get("models")), r)

r = connectors.health(cfg, "orca", "", timeout=8)
check("ollama-style needs no key", r["ok"], r)

bad2 = cfg_with(orca={"enabled": True, "url": "http://127.0.0.1:9999/v1", "model": "x"})
r = connectors.health(bad2, "orca", "", timeout=4)
check("dead server gives a friendly message", (not r["ok"]) and "Can't reach" in r["detail"], r)

r = connectors.health(cfg, "dify", "wrong-key", timeout=6)
check("dify rejects a bad key", (not r["ok"]) and "key" in r["detail"].lower(), r)

print("\n== 2. OpenHands profile discovery ==")
info = connectors.check_openhands("http://127.0.0.1:9413", "oh-secret")
check("kind is agent-server", info["kind"] == "agent-server", info)
check("profiles found", info["profiles"] == ["demo", "security"], info)
check("version read", info["version"] == "1.31.0", info)
check("model picked from /v1/models",
      connectors._oh_pick_model("http://127.0.0.1:9413", "oh-secret", "") == "openhands_demo")

print("\n== 3. routing ==")
cases = [
    ("Build me a FastAPI app with a login page and tests", "openhands"),
    ("fix the bug in my repo and run the tests", "openhands"),
    ("ask orca-mini for a second opinion", "orca"),
    ("say that out loud with your avatar", "vtuber"),
    ("hello", "vtuber"),
    ("what is a null pointer?", "main"),
    ("size a steel beam for 12 kN/m", "main"),
    ("run this offline with ollama", "ollama" if connectors.engine_ready(cfg, "ollama") else "main"),
]
for q, want in cases:
    got = connectors.auto_route(q, cfg)
    check(f"route {q[:44]!r} -> {want}", got == want, f"got {got}")

cfg_off = cfg_with()
check("nothing enabled routes to main", connectors.auto_route("build me an app", cfg_off) == "main")
cfg_noauto = cfg_with(orca={"enabled": True, "url": "http://x/v1", "model": "orca-mini"})
cfg_noauto["auto_route"] = False
check("auto_route off", connectors.auto_route("use orca", cfg_noauto) == "main")
check("explicit engine beats routing",
      connectors.resolve_engine(cfg, "dify", "explain recursion") == "dify")
check("ready list", connectors.ready_engines(cfg) ==
      ["main", "openhands", "dify", "vtuber", "orca"], connectors.ready_engines(cfg))
check("dify without a key is not ready",
      not connectors.engine_ready(cfg_with(dify={"enabled": True, "url": "http://x/v1"}), "dify"))

print("\n== 4. streaming: orca-mini (OpenAI-compatible) ==")
state = {}
ev = collect(connectors.stream_engine(cfg, "orca", "", HISTORY, "what is 2+2?", state))
body = text_of(ev)
check("orca answered", "orca-mini" in body and "answered" in body, body[:200])
check("no errors", not [e for e in ev if e["type"] == "error"], ev[-1:])
check("got several deltas", len([e for e in ev if e["type"] == "delta"]) > 2)

print("\n== 5. streaming: Dify ==")
state = {}
ev = collect(connectors.stream_engine(cfg, "dify", "app-good-key", HISTORY, "summarise this", state))
body = text_of(ev)
check("dify answered", "Dify here" in body, body[:200])
check("dify question comes first", body.startswith("Dify here. You asked: “summarise this"), body[:200])
check("dify included the recap of the chat", "hello there" in body, body[:400])
cids = [e for e in ev if e.get("conversation_id")]
check("dify conversation id captured", bool(cids), ev[-3:])
check("state remembers the path", state.get("dify_path") == "/chat-messages", state)

print("\n== 6. streaming: OpenHands ==")
state = {}
ev = collect(connectors.stream_engine(cfg, "openhands", "oh-secret", HISTORY, "build the thing", state))
body = text_of(ev)
check("openhands answered", "OpenHands agent" in body and "tests pass" in body, body[:300])
check("status line shown", any(e["type"] == "status" and "OpenHands" in e["text"] for e in ev), ev[:3])
check("no errors", not [e for e in ev if e["type"] == "error"], ev[-1:])

print("\n== 7. streaming: Open-LLM-VTuber (text + voice) ==")
state = {}
ev = collect(connectors.stream_engine(cfg, "vtuber", "", HISTORY, "introduce yourself", state))
body = text_of(ev)
audio = [e for e in ev if e["type"] == "audio"]
check("vtuber answered with text", "VTuber" in body or "Konnichiwa" in body, body[:200])
check("vtuber sent voice", len(audio) >= 2, len(audio))
check("voice is base64 wav", all(e["audio"].startswith("UklGR") for e in audio), audio[:1])
check("sentences not duplicated", body.count("Konnichiwa") == 1, body)
state2 = {}
cfg_noaudio = cfg_with(vtuber={"enabled": True, "url": "http://127.0.0.1:9414"})
cfg_noaudio["vtuber_audio"] = False
ev2 = collect(connectors.stream_engine(cfg_noaudio, "vtuber", "", HISTORY, "hi", state2))
check("voice off means no audio events", not [e for e in ev2 if e["type"] == "audio"])

print("\n== 8. failure handling ==")
dead = cfg_with(orca={"enabled": True, "url": "http://127.0.0.1:9999/v1", "model": "orca-mini"})
ev = collect(connectors.stream_engine(dead, "orca", "", HISTORY, "hi", {}))
errs = [e for e in ev if e["type"] == "error"]
check("dead engine returns an error event", bool(errs), ev)
check("error is friendly", errs and "Can't reach" in errs[0]["message"], errs[:1])

notready = cfg_with()
msg = connectors.engine_error_message(notready, "dify")
check("off engine explains itself", "isn't switched on" in msg and "Connectors" in msg, msg)
nokey = cfg_with(dify={"enabled": True, "url": "http://127.0.0.1:9412/v1"})
msg = connectors.engine_error_message(nokey, "dify")
check("missing dify key explained", "needs an API key" in msg, msg)

print("\n== 9. config safety ==")
cfg["engines"]["dify"]["key"] = "app-secret-value"
pub = connectors.public_engines(cfg)
blob = json.dumps(pub)
check("public config hides keys", "app-secret-value" not in blob, blob[:300])
check("public config says a key exists", pub["dify"]["has_key"] is True)
check("engine defaults are complete",
      set(connectors.engine_defaults()) == set(connectors.ENGINES))

print("\n== 10. server endpoints ==")
with httpx.Client(timeout=60) as c:
    st = c.get(BASE + "/api/status").json()
    check("/api/status exposes engines", "engines" in st and "vtuber" in st["engines"], list(st))
    check("/api/status hides engine keys", "app-secret" not in json.dumps(st))
    check("/api/status lists free providers", len(st.get("free_providers", [])) >= 5)
    check("config has auto_route", st["config"].get("auto_route") is True)

    r = c.post(BASE + "/api/engines/check", json={"engine": "orca", "url": "http://127.0.0.1:9411/v1"})
    check("check endpoint works", r.status_code == 200 and r.json()["ok"], r.text[:200])
    r = c.post(BASE + "/api/engines/check", json={"engine": "nonsense"})
    check("unknown engine rejected", r.status_code == 400, r.status_code)

    # a chat routed to the VTuber
    r = c.post(BASE + "/api/chat", json={"engine": "vtuber",
                                         "messages": [{"role": "user", "content": "hi there"}]})
    raw = r.text
    check("chat with engine=vtuber streams", '"type": "delta"' in raw and '"engine": "vtuber"' in raw,
          raw[:300])
    check("chat sends audio events", '"type": "audio"' in raw, raw[:200])

    r = c.post(BASE + "/api/chat", json={"engine": "orca",
                                         "messages": [{"role": "user", "content": "hi"}]})
    check("chat with engine=orca streams", "orca-mini" in r.text, r.text[:300])

    # not switched on -> helpful message, no crash
    r = c.post(BASE + "/api/chat", json={"engine": "custom2",
                                         "messages": [{"role": "user", "content": "hi"}]})
    check("disabled engine explains itself", "isn't switched on" in r.text, r.text[:300])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
