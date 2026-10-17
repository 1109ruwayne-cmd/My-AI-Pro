# My AI Pro source code: connectors.py

The connector engines module: the other AIs it can use (Dify, Ollama, Open-LLM-VTuber and more), auto-routing of questions, and their streaming adapters.

This is the assistant's own source code, kept here so it can answer questions about how it works, explain any part of itself, and help its owner debug or extend it. Contains no secrets (passwords and API keys live in environment variables).

~~~~
"""
connectors.py - the other AIs your AI can talk to.

Your AI has its own brain (the provider in config.json). On top of that it can hand
work to other systems you run:

  * Ollama      free local models, including orca-mini          (OpenAI-compatible)
  * free        free API tiers: OpenRouter, Groq, Hugging Face, NVIDIA NIM, Mistral
  * openhands   the OpenHands agent - builds and fixes whole projects for you
  * dify        a Dify chat app, agent or workflow you built
  * vtuber      Open-LLM-VTuber - answers with a Live2D avatar and voice
  * custom      any other OpenAI-compatible server you want to add

Each one is optional. If it isn't switched on, or the server isn't running, your AI
simply answers by itself - nothing breaks.

Every stream function is a generator that yields small dicts:

    {"type": "status", "text": "..."}          progress line shown above the answer
    {"type": "delta",  "text": "..."}          part of the answer
    {"type": "audio",  "audio": "<base64>"}    voice (Open-LLM-VTuber only)
    {"type": "meta",   "conversation_id": ...} remember the other side's session
    {"type": "error",  "message": "..."}       something went wrong
"""
from __future__ import annotations

import json
import os
import re
import time

import httpx
from openai import OpenAI

# --------------------------------------------------------------------------- the list

# "kind" decides how we talk to it; "profile" adds free-model defaults for OpenAI-style ones.
ENGINES = {
    "main": {
        "label": "My AI",
        "short": "My AI",
        "icon": "🧠",
        "kind": "main",
        "blurb": "Your AI's own brain, with your files. Coding, engineering, maths and cybersecurity.",
    },
    "openhands": {
        "label": "OpenHands agent",
        "short": "OpenHands",
        "icon": "🤖",
        "kind": "openhands",
        "blurb": "An AI software engineer that works in a real sandbox: it reads, writes, runs and "
                 "tests whole projects. Best for bigger jobs than a single answer.",
        "url_hint": "http://127.0.0.1:8000",
        "docs": "https://docs.openhands.dev/sdk/guides/agent-server/local-server",
    },
    "dify": {
        "label": "Dify app or workflow",
        "short": "Dify",
        "icon": "🧩",
        "kind": "dify",
        "blurb": "Hand the question to a chatbot, agent or workflow you built in Dify.",
        "url_hint": "http://127.0.0.1/v1",
        "docs": "https://docs.dify.ai/en/guides/application-publishing/developing-with-apis",
    },
    "vtuber": {
        "label": "Open-LLM-VTuber",
        "short": "VTuber",
        "icon": "🎭",
        "kind": "vtuber",
        "blurb": "Answers out loud with the Live2D avatar: voice replies you can hear in the chat.",
        "url_hint": "http://127.0.0.1:12393",
        "docs": "https://open-llm-vtuber.github.io/",
    },
    "ollama": {
        "label": "Ollama (free, offline)",
        "short": "Ollama",
        "icon": "🦙",
        "kind": "openai",
        "profile": "ollama",
        "blurb": "Models running free on your own computer. Great when the internet is down or you "
                 "don't want a question leaving the house.",
        "url_hint": "http://127.0.0.1:11434/v1",
        "docs": "https://ollama.com/download",
    },
    "orca": {
        "label": "orca-mini (Ollama)",
        "short": "orca-mini",
        "icon": "🐋",
        "kind": "openai",
        "profile": "orca",
        "blurb": "The small, fast orca-mini model through Ollama. A quick second opinion that costs "
                 "nothing.",
        "url_hint": "http://127.0.0.1:11434/v1",
        "docs": "https://ollama.com/library/orca-mini",
    },
    "free": {
        "label": "Free model APIs",
        "short": "Free",
        "icon": "🆓",
        "kind": "openai",
        "profile": "free",
        "blurb": "Free tiers from OpenRouter, Groq, Hugging Face, NVIDIA and Mistral. One key, "
                 "hundreds of open models.",
        "url_hint": "https://openrouter.ai/api/v1",
        "docs": "https://openrouter.ai/models?max_price=0",
    },
    "custom2": {
        "label": "Another OpenAI-compatible server",
        "short": "Custom",
        "icon": "🔌",
        "kind": "openai",
        "profile": "custom",
        "blurb": "Anything else that speaks the OpenAI API: LM Studio, vLLM, llama.cpp server, "
                 "LocalAI, text-generation-webui, LiteLLM…",
    },
}

ORDER = ["main", "openhands", "dify", "vtuber", "ollama", "orca", "free", "custom2"]

# Defaults offered in the model box for each OpenAI-style engine.
DEFAULTS = {
    "ollama": ("", "llama3.2", "qwen2.5", "mistral"),
    "orca": ("orca-mini", "orca-mini:3b", "orca-mini:7b", "orca-mini:13b"),
    "free": ("openrouter/auto", "openai/gpt-oss-120b", "qwen/qwen3.8-27b",
             "meta-llama/llama-3.3-70b-instruct:free"),
    "custom": ("",),
}

# Free and open providers, with what you need to start. Shown in Settings → Connectors.
FREE_PROVIDERS = [
    {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "model": "openrouter/auto",
     "key_url": "https://openrouter.ai/keys", "free": "Every model ending in :free · 20 requests/min, 50/day"},
    {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b",
     "key_url": "https://console.groq.com/keys", "free": "30 requests/min, 1,000/day per model"},
    {"name": "Hugging Face", "base_url": "https://api-inference.huggingface.co/v1/", "model": "",
     "key_url": "https://huggingface.co/settings/tokens", "free": "Free inference for many open models"},
    {"name": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1", "model": "",
     "key_url": "https://build.nvidia.com/", "free": "Generous free daily requests, no card"},
    {"name": "Mistral", "base_url": "https://api.mistral.ai/v1", "model": "",
     "key_url": "https://console.mistral.ai/api-keys", "free": "Free experiment tier"},
    {"name": "Ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "orca-mini",
     "key_url": "https://ollama.com/download", "free": "Completely free, offline, no key needed"},
]

# Where an engine's key comes from, in order of preference.
ENV_KEYS = {
    "ollama": ("OLLAMA_API_KEY",),
    "orca": ("OLLAMA_API_KEY",),
    "free": ("OPENROUTER_API_KEY", "GROQ_API_KEY", "HF_TOKEN", "HUGGINGFACE_TOKEN",
             "NVIDIA_API_KEY", "MISTRAL_API_KEY"),
    "custom2": ("CUSTOM_API_KEY",),
    "openhands": ("OPENHANDS_API_KEY", "OH_SESSION_API_KEYS_0", "SESSION_API_KEY"),
    "dify": ("DIFY_API_KEY",),
    "vtuber": (),
}

# Which other engines can answer on their own (i.e. everything except "main").
SECONDARY = [e for e in ORDER if e != "main"]

DEFAULT_ENGINE = {"enabled": False, "url": "", "model": "", "key": "", "extra": {}}


def engine_defaults() -> dict:
    """A blank set of engine settings, ready to merge into config.json."""
    out = {}
    for eid in ORDER:
        item = dict(DEFAULT_ENGINE)
        item["extra"] = {}
        hints = ENGINES[eid].get("url_hint")
        if hints:
            item["url"] = hints
        if eid == "orca":
            item["model"] = "orca-mini"
        if eid == "free":
            item["model"] = "openrouter/auto"
        if eid == "dify":
            item["extra"] = {"user": "my-ai", "inputs": {}, "conversation_id": ""}
        out[eid] = item
    return out


def engine_config(cfg: dict, eid: str) -> dict:
    """This engine's settings, with defaults filled in."""
    saved = (cfg.get("engines") or {}).get(eid) or {}
    base = engine_defaults().get(eid, dict(DEFAULT_ENGINE, extra={}))
    out = dict(base)
    if "enabled" in saved:
        out["enabled"] = bool(saved["enabled"])
    for k in ("url", "model", "key"):
        if k in saved:
            out[k] = saved[k]
    if isinstance(saved.get("extra"), dict):
        out["extra"] = {**base["extra"], **saved["extra"]}
    out["url"] = str(out["url"] or "").strip().rstrip("/")
    return out


def public_engines(cfg: dict) -> dict:
    """Engine settings safe to send to the browser (never the real keys)."""
    out = {}
    for eid in ORDER:
        e = engine_config(cfg, eid)
        out[eid] = {
            "enabled": bool(e["enabled"]),
            "url": e["url"],
            "model": e["model"],
            "has_key": bool(e["key"]) or bool(_env_key(eid)),
            "extra": {k: v for k, v in e["extra"].items() if k != "api_key"},
        }
    return out


def _env_key(eid: str) -> str:
    for name in ENV_KEYS.get(eid, ()):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def credentials(cfg: dict, eid: str, request=None) -> str:
    """The key for one engine: what the browser sent, then config.json, then the environment."""
    if request is not None:
        sent = request.headers.get(f"x-key-{eid}", "").strip()
        if sent:
            return sent
        stored = request.headers.get("x-engine-keys", "").strip()
        if stored:
            try:
                blob = json.loads(stored)
                if isinstance(blob, dict) and str(blob.get(eid, "")).strip():
                    return str(blob[eid]).strip()
            except ValueError:
                pass
    e = engine_config(cfg, eid)
    return str(e["key"] or "").strip() or _env_key(eid)


# --------------------------------------------------------------------------- helpers

def _clean_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def _ws_url(url: str, path: str) -> str:
    """http://host:12393 -> ws://host:12393/path"""
    u = _clean_url(url)
    if u.startswith("https://"):
        u = "wss://" + u[len("https://"):]
    elif u.startswith("http://"):
        u = "ws://" + u[len("http://"):]
    elif u.startswith("ws://") or u.startswith("wss://"):
        pass
    else:
        u = "ws://" + u
    u = u.rstrip("/")
    if u.endswith(path):
        return u
    return u + path


def _http_url(url: str, path: str = "") -> str:
    u = _clean_url(url)
    if not u:
        return ""
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "http://" + u
    if u.startswith("ws://"):
        u = "http://" + u[len("ws://"):]
    elif u.startswith("wss://"):
        u = "https://" + u[len("wss://"):]
    return (u.rstrip("/") + path) if path else u.rstrip("/")


def history_text(history: list, turns: int = 4, limit: int = 4000) -> str:
    """A short recap of the chat, for engines that take one message instead of a history."""
    msgs = [m for m in history[:-1] if m.get("content")][-turns * 2:]
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        who = "User" if m["role"] == "user" else "Assistant"
        body = re.sub(r"\s+", " ", m["content"]).strip()
        if len(body) > 600:
            body = body[:600].rsplit(" ", 1)[0] + "…"
        lines.append(f"{who}: {body}")
    text = "\n".join(lines)
    return text[:limit]


def friendly(exc: Exception, label: str, url: str) -> str:
    """Turn a connection error into something a person can act on."""
    text = str(exc)
    low = text.lower()
    where = f" ({url})" if url else ""
    if isinstance(exc, httpx.TimeoutException) or "timed out" in low or "timeout" in low:
        return f"{label} didn't answer in time{where}. It may be busy, or the address may be wrong."
    if "401" in text or "403" in text or "unauthorized" in low or "forbidden" in low:
        return f"{label} rejected the API key{where}. Check the key in ⚙️ Settings → Connectors."
    if "404" in text or "not found" in low:
        return (f"{label} is reachable{where} but doesn't have that endpoint or model. "
                "Check the address and the model name in ⚙️ Settings → Connectors.")
    if "422" in text or "400" in text:
        return f"{label} didn't understand the request{where}: {text[:300]}"
    if any(w in low for w in ("connection refused", "connection error", "connection reset",
                              "connect error", "connecterror", "apiconnectionerror",
                              "actively refused", "no route", "name or service not known",
                              "getaddrinfo", "handshake", "connection aborted", "broken pipe",
                              "server disconnected", "failed to establish a new connection")):
        return (f"Can't reach {label}{where}. Is it running? Start it, then check the address "
                "in ⚙️ Settings → Connectors.")
    if "429" in text or "rate" in low:
        return f"{label} is rate-limiting you{where}. Wait a minute and try again."
    return f"{label} error{where}: {text[:400]}"


def _parse_sse_lines(text: str):
    """Split an SSE chunk into (data strings, leftover)."""
    events, leftover = [], ""
    blocks = text.split("\n\n")
    leftover = blocks.pop()
    for block in blocks:
        data = [ln[5:].lstrip() for ln in block.splitlines() if ln.startswith("data:")]
        if data:
            events.append("\n".join(data))
    return events, leftover


# --------------------------------------------------------------------------- health

def check_openai(url: str, key: str, timeout: float = 12.0):
    """Ask an OpenAI-compatible server which models it has."""
    base = _http_url(url)
    client = OpenAI(api_key=key or "not-needed", base_url=base, timeout=timeout, max_retries=0)
    ids = [m.id for m in client.models.list()]
    return sorted({i.removeprefix("models/") for i in ids if i})


def check_dify(url: str, key: str, timeout: float = 12.0) -> dict:
    base = _http_url(url)
    if not base.endswith("/v1"):
        base += "/v1"
    r = httpx.get(base + "/parameters", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    r.raise_for_status()
    data = r.json() if r.content else {}
    return {"opening": data.get("opening_statement") or "", "ok": True}


def check_openhands(url: str, key: str, timeout: float = 10.0) -> dict:
    """Work out which OpenHands server this is, and which agent profiles it offers."""
    base = _http_url(url)
    headers = {"X-Session-API-Key": key} if key else {}
    found = {"ok": False, "kind": "", "profiles": [], "version": ""}
    for path in ("/health", "/alive", "/api/health"):
        try:
            r = httpx.get(base + path, headers=headers, timeout=timeout)
            if r.status_code < 400:
                found["ok"] = True
                found["kind"] = "agent-server"
                try:
                    body = r.json()
                    found["version"] = str(body.get("version", ""))[:40]
                except ValueError:
                    pass
                break
        except httpx.HTTPError:
            continue
    if not found["ok"]:
        # The older all-in-one OpenHands GUI/runtime answers on /api/options/models
        try:
            r = httpx.get(base + "/api/options/models",
                          headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=timeout)
            if r.status_code < 400:
                found.update(ok=True, kind="gui")
                return found
        except httpx.HTTPError:
            pass
    if not found["ok"]:
        raise httpx.ConnectError(f"Nothing is answering at {base}")
    try:
        r = httpx.get(base + "/api/profiles", headers=headers, timeout=timeout)
        if r.status_code < 400:
            body = r.json()
            items = body.get("items", body) if isinstance(body, dict) else body
            for p in items or []:
                if isinstance(p, dict):
                    name = p.get("name") or p.get("id") or ""
                    if name:
                        found["profiles"].append(str(name))
                elif isinstance(p, str):
                    found["profiles"].append(p)
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return found


def check_vtuber(url: str, timeout: float = 6.0) -> dict:
    """Open-LLM-VTuber only talks WebSocket, so we try /client-ws and then plain HTTP."""
    base = _http_url(url)
    try:
        from websockets.sync.client import connect as ws_connect
        with ws_connect(_ws_url(base, "/client-ws"), open_timeout=timeout, close_timeout=1,
                        max_size=None) as ws:
            first = json.loads(ws.recv(timeout=timeout))
            return {"ok": True, "hello": first.get("type", "")}
    except Exception:
        pass
    r = httpx.get(base + "/live2d-models/info", timeout=timeout)
    r.raise_for_status()
    return {"ok": True, "hello": "http"}


def health(cfg: dict, eid: str, key: str, timeout: float = 12.0) -> dict:
    """Can we reach this engine? Returns {ok, detail, models?} and never raises."""
    e = engine_config(cfg, eid)
    kind = ENGINES[eid]["kind"]
    url = e["url"]
    if not url:
        return {"ok": False, "detail": "No address set."}
    try:
        if kind == "dify":
            info = check_dify(url, key, timeout)
            detail = "Connected." + (f" It starts with: “{info['opening'][:120]}”" if info["opening"] else "")
            return {"ok": True, "detail": detail}
        if kind == "openhands":
            info = check_openhands(url, key, timeout)
            if info["kind"] == "gui":
                return {"ok": True, "detail": "Connected (older OpenHands GUI - limited).",
                        "profiles": []}
            profiles = info["profiles"]
            detail = "Connected."
            if info.get("version"):
                detail += f" Version {info['version']}."
            if profiles:
                detail += " Agents: " + ", ".join(f"openhands_{p}" for p in profiles[:8]) + "."
            else:
                detail += (" No agent profile yet. Create one on the OpenHands server with "
                           "POST /api/profiles/<name>, then pick openhands_<name> as the model.")
            return {"ok": True, "detail": detail,
                    "models": [f"openhands_{p}" for p in profiles]}
        if kind == "vtuber":
            check_vtuber(url, timeout)
            return {"ok": True, "detail": "Connected - ready to talk."}
        models = check_openai(url, key, timeout)
        return {"ok": True, "detail": f"Connected · {len(models)} model(s).", "models": models}
    except Exception as exc:                                   # noqa: BLE001 - reported to the user
        return {"ok": False, "detail": friendly(exc, ENGINES[eid]["short"], url)}


# --------------------------------------------------------------------------- openai style

def _oai_messages(engine: dict, history: list, system: str) -> list:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    for m in history:
        if not m.get("content"):
            continue
        if isinstance(m["content"], str):
            msgs.append({"role": m["role"], "content": m["content"]})
        else:                                    # pictures etc: flatten to text for small models
            flat = " ".join(p.get("text", "") for p in m["content"] if isinstance(p, dict))
            msgs.append({"role": m["role"], "content": flat or "(attachment)"})
    return msgs


def stream_openai_engine(eid: str, engine: dict, key: str, history: list, system: str = "",
                         extra_headers: dict | None = None, label: str = ""):
    """Any OpenAI-compatible engine: Ollama, orca-mini, OpenRouter, Groq, LM Studio…"""
    name = label or ENGINES[eid]["short"]
    url, model = engine["url"], engine["model"]
    try:
        client = OpenAI(api_key=key or "not-needed", base_url=_http_url(url),
                        timeout=240, max_retries=1, default_headers=extra_headers or None)
        kwargs = {"model": model, "messages": _oai_messages(engine, history, system), "stream": True}
        got = False
        for event in client.chat.completions.create(**kwargs):
            choices = getattr(event, "choices", None)
            if not choices:
                continue
            piece = getattr(choices[0].delta, "content", None)
            if piece:
                got = True
                yield {"type": "delta", "text": piece}
        if not got:
            yield {"type": "delta", "text": f"_({name} sent back an empty answer.)_"}
    except Exception as exc:                                     # noqa: BLE001
        yield {"type": "error", "message": friendly(exc, name, url)}


def stream_ollama(eid: str, cfg: dict, key: str, history: list, query: str):
    engine = engine_config(cfg, eid)
    return stream_openai_engine(eid, engine, key or "ollama", history, system=_ROUTER_SYSTEM)


# --------------------------------------------------------------------------- dify

DIFY_PATHS = ("/chat-messages", "/chatflow/chat-messages", "/completion-messages")


def stream_dify(cfg: dict, key: str, history: list, query: str, state: dict):
    """POST {base}/chat-messages with response_mode=streaming."""
    engine = engine_config(cfg, "dify")
    base = _http_url(engine["url"])
    if not base.endswith("/v1"):
        base += "/v1"
    extra = engine["extra"] or {}
    user = str(extra.get("user") or "my-ai")[:64]
    inputs = extra.get("inputs") if isinstance(extra.get("inputs"), dict) else {}
    # Dify remembers its own conversation, so a recap is only needed for the very first message,
    # and the question itself must always come first.
    continuing = bool(str(extra.get("conversation_id") or "").strip())
    recap = "" if continuing else history_text(history, turns=3, limit=1800)
    text = query
    if recap:
        text = f"{query}\n\n(Earlier in this conversation:\n{recap})"
    payload = {"inputs": inputs, "query": text[:12000], "response_mode": "streaming",
               "user": user, "conversation_id": str(extra.get("conversation_id") or "")}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    path = state.get("dify_path") or DIFY_PATHS[0]
    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0)) as client:
            last_error = None
            for attempt, path in enumerate([path] + [p for p in DIFY_PATHS if p != path]):
                got = False
                buffer = ""
                thought = False
                with client.stream("POST", base + path, json=payload, headers=headers) as r:
                    if r.status_code == 404 and attempt < len(DIFY_PATHS) - 1:
                        last_error = "that endpoint doesn't exist"
                        continue
                    if r.status_code >= 400:
                        body = r.read().decode("utf-8", "replace")[:400]
                        raise RuntimeError(f"HTTP {r.status_code}: {body}")
                    for chunk in r.iter_text():
                        buffer += chunk
                        events, buffer = _parse_sse_lines(buffer)
                        for raw in events:
                            if raw.strip() == "[DONE]":
                                continue
                            try:
                                ev = json.loads(raw)
                            except ValueError:
                                continue
                            kind = ev.get("event")
                            if kind in ("message", "agent_message", "message_replace"):
                                piece = ev.get("answer") or ""
                                if piece:
                                    got = True
                                    yield {"type": "delta", "text": piece}
                            elif kind == "agent_thought":
                                tool = ev.get("tool") or ""
                                if tool and not thought:
                                    thought = True
                                    yield {"type": "status", "text": f"Dify is using {tool}…"}
                            elif kind == "message_file":
                                link = ev.get("url") or ""
                                if link:
                                    yield {"type": "delta", "text": f"\n\n📎 {link}\n"}
                            elif kind in ("message_end", "message"):
                                cid = ev.get("conversation_id")
                                if cid:
                                    yield {"type": "meta", "conversation_id": cid}
                            elif kind == "error":
                                raise RuntimeError(ev.get("message") or "Dify returned an error")
                if got:
                    state["dify_path"] = path
                    return
                last_error = last_error or "the app sent back no text"
            raise RuntimeError(f"No answer from Dify: {last_error}. Check that the API key is for a "
                               "Chat, Agent or Chatflow app.")
    except Exception as exc:                                     # noqa: BLE001
        yield {"type": "error", "message": friendly(exc, "Dify", base)}


# --------------------------------------------------------------------------- openhands

def _oh_headers(key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if key:
        h["X-Session-API-Key"] = key
        h["Authorization"] = f"Bearer {key}"
    return h


def _oh_pick_model(base: str, key: str, wanted: str) -> str:
    """Find an openhands_<profile> model to use."""
    try:
        r = httpx.get(base + "/v1/models", headers=_oh_headers(key), timeout=15)
        if r.status_code < 400:
            ids = [m.get("id", "") for m in r.json().get("data", [])]
            ids = [i for i in ids if i]
            if wanted and wanted in ids:
                return wanted
            opens = [i for i in ids if i.startswith("openhands_")]
            if opens:
                return opens[0]
            if ids:
                return ids[0]
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return wanted or "openhands_default"


def stream_openhands_native(base: str, key: str, history: list, query: str, state: dict,
                            timeout: float = 900.0):
    """Older / SDK-native agent server: create a conversation, then follow its events."""
    headers = _oh_headers(key)
    recap = history_text(history, turns=2, limit=1500)
    task = f"{recap}\n\nNow do this: {query}" if recap else query
    body = {"initial_message": {"role": "user",
                                "content": [{"type": "text", "text": task[:16000]}]}}
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        cid = state.get("openhands_conversation")
        if not cid:
            r = client.post(base + "/api/conversations", json=body, headers=headers)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            cid = str(data.get("id") or data.get("conversation_id") or "")
            if not cid:
                raise RuntimeError("OpenHands started a conversation but didn't return its id.")
            state["openhands_conversation"] = cid
            yield {"type": "meta", "openhands_conversation": cid}
            yield {"type": "status", "text": "OpenHands is working on it…"}
        else:
            r = client.post(f"{base}/api/conversations/{cid}/events",
                            json={"role": "user", "content": [{"type": "text", "text": query[:16000]}]},
                            headers=headers)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            yield {"type": "status", "text": "OpenHands is working on it…"}

        seen = 0
        started = time.time()
        answer = []
        while time.time() - started < timeout:
            time.sleep(1.2)
            try:
                r = client.get(f"{base}/api/conversations/{cid}/events/search",
                               params={"limit": 200}, headers=headers)
                if r.status_code >= 400:
                    continue
                body = r.json()
            except (httpx.HTTPError, ValueError):
                continue
            items = body.get("items", body) if isinstance(body, dict) else body
            items = items or []
            for ev in items[seen:]:
                seen += 1
                if not isinstance(ev, dict):
                    continue
                kind = (ev.get("kind") or ev.get("type") or "").lower()
                if "message" in kind and ev.get("role", "assistant") in ("assistant", ""):
                    for part in ev.get("content") or []:
                        piece = part.get("text") if isinstance(part, dict) else str(part)
                        if piece:
                            answer.append(piece)
                            yield {"type": "delta", "text": piece}
                elif "agentfinish" in kind or "finish" in kind:
                    if answer:
                        return
            try:
                r = client.get(f"{base}/api/conversations/{cid}", headers=headers)
                status = (r.json().get("status") or "").lower() if r.status_code < 400 else ""
            except (httpx.HTTPError, ValueError):
                status = ""
            if status in ("finished", "completed", "done", "error", "paused") and answer:
                return
            if status == "error" and not answer:
                raise RuntimeError("The OpenHands agent reported an error.")
        if not answer:
            raise RuntimeError("OpenHands didn't finish in time. Try a smaller task.")


def stream_openhands(cfg: dict, key: str, history: list, query: str, state: dict):
    """OpenHands agent-server. Prefers its OpenAI-compatible gateway (/v1/chat/completions)."""
    engine = engine_config(cfg, "openhands")
    base = _http_url(engine["url"])
    model = engine["model"]
    try:
        with httpx.Client(timeout=20) as client:
            kind = "agent-server"
            try:
                r = client.get(base + "/v1/models", headers=_oh_headers(key))
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}")
                model = _oh_pick_model(base, key, model)
            except Exception:                                    # noqa: BLE001 - try the older API
                try:
                    r = client.get(base + "/api/options/models", timeout=15)
                    kind = "gui" if r.status_code < 400 else "agent-server"
                except httpx.HTTPError:
                    kind = "agent-server"
        if kind == "gui":
            yield {"type": "error",
                   "message": "That looks like the older OpenHands GUI, which has no supported "
                              "message API. Run the agent server instead:\n\n```bash\n"
                              "pip install -U openhands-agent-server openhands-sdk openhands-tools\n"
                              "python -m openhands.agent_server --host 127.0.0.1 --port 8000\n```"}
            return
        yield {"type": "status", "text": f"OpenHands ({model}) is working on it…"}
        yield from stream_openai_engine(
            "openhands", dict(engine, url=base + "/v1", model=model), key, history,
            system=_AGENT_SYSTEM, extra_headers=_oh_headers(key), label="OpenHands")
    except Exception as exc:                                     # noqa: BLE001
        yield {"type": "error", "message": friendly(exc, "OpenHands", base)}


# --------------------------------------------------------------------------- vtuber

def stream_vtuber(cfg: dict, key: str, history: list, query: str, state: dict,
                  with_audio: bool = True, timeout: float = 240.0):
    """Talk to Open-LLM-VTuber over its WebSocket and collect what it says (and its voice)."""
    engine = engine_config(cfg, "vtuber")
    url = _ws_url(engine["url"], "/client-ws")
    try:
        from websockets.sync.client import connect as ws_connect
    except ImportError:
        yield {"type": "error",
               "message": "The websockets library is missing. Run: pip install -r requirements.txt"}
        return
    try:
        with ws_connect(url, open_timeout=15, close_timeout=1, max_size=None) as ws:
            # The server greets us with "full-text" + "set-model-and-conf" + a mic control frame.
            try:
                ws.recv(timeout=8)
            except Exception:                                    # noqa: BLE001
                pass
            ws.send(json.dumps({"type": "text-input", "text": query[:8000]}))
            yield {"type": "status", "text": "VTuber is thinking…"}

            deadline = time.time() + timeout
            heard = False
            last_text = ""
            # The avatar answers sentence by sentence. When nothing arrives for a few seconds
            # after it has started, it has finished.
            quiet_for = 90.0
            while True:
                now = time.time()
                if now > deadline:
                    break
                wait = min(deadline - now, quiet_for)
                try:
                    raw = ws.recv(timeout=wait)
                except TimeoutError:
                    break
                except Exception:                                  # noqa: BLE001
                    break
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                kind = msg.get("type")
                if kind == "audio":
                    quiet_for = 4.0 if heard else quiet_for
                    heard = True
                    disp = msg.get("display_text") or {}
                    piece = (disp.get("text") or "").strip() if isinstance(disp, dict) else str(disp)
                    if piece and piece != last_text:
                        last_text = piece
                        yield {"type": "delta", "text": piece + "\n\n"}
                    if with_audio and msg.get("audio"):
                        yield {"type": "audio", "audio": msg["audio"], "mime": "audio/wav",
                               "text": piece}
                elif kind == "full-text":
                    heard = True
                    quiet_for = 4.0
                    piece = (msg.get("text") or "").strip()
                    if piece and piece.lower() not in ("thinking...", "connection established"):
                        yield {"type": "delta", "text": piece + "\n\n"}
                elif kind == "control":
                    if msg.get("text") == "interrupt":
                        break
                elif kind == "backend-synth-complete":
                    quiet_for = 3.0
                elif kind == "error":
                    raise RuntimeError(msg.get("message") or "Open-LLM-VTuber reported an error")
            if not heard:
                yield {"type": "delta",
                       "text": "_(Open-LLM-VTuber sent nothing back. Check that a model and voice "
                               "are configured in its conf.yaml, or open its own window with the "
                               "🎭 button.)_"}
    except Exception as exc:                                       # noqa: BLE001
        yield {"type": "error", "message": friendly(exc, "Open-LLM-VTuber", url)}


# --------------------------------------------------------------------------- routing

_ROUTER_SYSTEM = (
    "You are a helpful AI assistant. Answer the user's question directly, completely and in their "
    "language. Write code in fenced blocks tagged with the language. Show your working for maths "
    "and engineering. Don't mention that you are a fallback or a smaller model."
)

_AGENT_SYSTEM = (
    "You are an expert software engineer with a real workspace. Do the task properly: read the "
    "files you need, make the changes, run the tests or the program, and fix what breaks. When you "
    "are done, report what you changed, how to run it, and anything the user should know."
)

RULES = [
    ("openhands", (
        r"\b(build|create|make|write|implement|develop|scaffold|generate)\b.{0,40}"
        r"\b(app|application|website|site|api|backend|frontend|service|project|repo|repository|"
        r"dashboard|tool|script|program|game|bot|clone)\b",
        r"\b(fix|debug|repair|resolve|refactor|rewrite|migrate|upgrade|optimise|optimize)\b.{0,40}"
        r"\b(bug|error|issue|test|tests|repo|repository|project|codebase|code)\b",
        r"\b(run|execute)\b.{0,20}\b(the tests?|test suite|pytest|npm test)\b",
        r"\b(pull request|\bPR\b|commit|branch|deploy|release)\b",
        r"\b(whole|entire|full)\s+(project|codebase|repo|repository|app)\b",
    ), 3),
    ("dify", (
        r"\b(dify|workflow|chatflow|agent flow|rag pipeline|knowledge base app|llm app)\b",
        r"\b(my|the) (chatbot|bot|assistant|agent)\b.{0,30}\b(in|from|on|built with)\b",
        r"\b(automation|automate)\b.{0,30}\b(flow|pipeline|sequence|chain)\b",
    ), 3),
    ("vtuber", (
        r"\b(vtuber|avatar|live2d|anime character)\b",
        r"\b(say it|speak|talk to me|read it (out|aloud)|out loud|voice|audio)\b.{0,20}"
        r"\b(reply|answer|response|it|this|that|to me)?\b",
        r"^\s*(hi|hey|hello|good (morning|afternoon|evening))\b.{0,30}$",
    ), 2),
    ("free", (
        r"\b(free|no cost|without paying|cheap)\b.{0,20}\b(model|api|llm|answer|option)\b",
        r"\b(second opinion|another model|different model|compare models)\b",
    ), 2),
    ("orca", (
        r"\b(orca[- ]?mini|orca)\b",
        r"\b(tiny|small|little)\s+(local\s+)?model\b",
    ), 3),
    ("ollama", (
        r"\b(ollama|locally|offline|on my (pc|computer|machine|laptop)|without internet|"
        r"private(ly)?|no internet)\b",
        r"\b(llama|qwen|mistral|gemma|deepseek|gpt-oss)\b.{0,20}\b(model|local|ollama)?\b",
    ), 2),
]
_COMPILED = [(eid, [re.compile(p, re.I) for p in pats], weight) for eid, pats, weight in RULES]


def auto_route(query: str, cfg: dict) -> str:
    """Pick the engine that fits the question best. Returns "main" when nothing else does."""
    if not cfg.get("auto_route", True):
        return "main"
    text = (query or "")[:1200]
    if not text.strip():
        return "main"
    scores: dict[str, int] = {}
    for eid, patterns, weight in _COMPILED:
        if not engine_ready(cfg, eid):
            continue
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            scores[eid] = scores.get(eid, 0) + hits * weight
    if not scores:
        return "main"
    best = max(scores.items(), key=lambda kv: (kv[1], -ORDER.index(kv[0])))
    return best[0] if best[1] >= 2 else "main"


def engine_ready(cfg: dict, eid: str) -> bool:
    """Is this engine switched on and configured enough to be used?"""
    if eid == "main":
        return True
    e = engine_config(cfg, eid)
    if not e["enabled"] or not e["url"]:
        return False
    kind = ENGINES[eid]["kind"]
    if kind == "openai" and not e["model"]:
        return False
    if kind == "dify" and not (e["key"] or _env_key(eid)):
        return False
    if kind == "vtuber":
        return True
    return True


def ready_engines(cfg: dict) -> list:
    """Every engine that can answer right now, in display order."""
    return [e for e in ORDER if engine_ready(cfg, e)]


def resolve_engine(cfg: dict, requested: str, query: str) -> str:
    """The engine for this message: an explicit button beats automatic routing."""
    requested = (requested or "").strip().lower()
    if requested in ENGINES:
        if requested == "main":
            return "main"
        if engine_ready(cfg, requested):
            return requested
        return requested          # let it fail with a clear message instead of silently switching
    if requested and requested != "auto":
        return "main"
    return auto_route(query, cfg)


# --------------------------------------------------------------------------- dispatch

def stream_engine(cfg: dict, eid: str, key: str, history: list, query: str, state: dict):
    """Run one engine and yield its events."""
    kind = ENGINES[eid]["kind"]
    if kind == "dify":
        yield from stream_dify(cfg, key, history, query, state)
    elif kind == "openhands":
        yield from stream_openhands(cfg, key, history, query, state)
    elif kind == "vtuber":
        yield from stream_vtuber(cfg, key, history, query, state,
                                 with_audio=bool(cfg.get("vtuber_audio", True)))
    elif kind == "openai":
        yield from stream_ollama(eid, cfg, key, history, query)
    else:
        yield {"type": "error", "message": f"I don't know how to talk to “{eid}”."}


def engine_error_message(cfg: dict, eid: str) -> str:
    """Why an engine can't be used - shown instead of a failed answer."""
    e = engine_config(cfg, eid)
    name = ENGINES[eid]["label"]
    if not e["enabled"]:
        return (f"**{name} isn't switched on yet.**\n\nOpen ⚙️ Settings → Connectors, switch on "
                f"{ENGINES[eid]['short']}, put in its address"
                + (" and API key," if ENGINES[eid]["kind"] in ("dify", "openhands", "openai") else ",")
                + " then click **Test**.\n\n"
                + (f"Docs: {e.get('docs') or ENGINES[eid].get('docs', '')}" if ENGINES[eid].get("docs") else ""))
    if not e["url"]:
        return f"**{name} has no address.** Set it in ⚙️ Settings → Connectors " \
               f"(for example `{ENGINES[eid].get('url_hint', 'http://127.0.0.1')}`)."
    if ENGINES[eid]["kind"] == "openai" and not e["model"]:
        return f"**{name} has no model.** Set one in ⚙️ Settings → Connectors " \
               f"(for example `{(DEFAULTS.get(ENGINES[eid]['profile'], ('',))[0] or 'your-model')}`)."
    if ENGINES[eid]["kind"] == "dify" and not (e["key"] or _env_key(eid)):
        return f"**{name} needs an API key.** In Dify open your app → API Access → create a key, " \
               "then paste it into ⚙️ Settings → Connectors."
    return f"**{name} isn't ready.** Check its settings in ⚙️ Settings → Connectors."


def describe_routing(eid: str, cfg: dict) -> str:
    """The little line shown above an answer, so you can see who answered."""
    if eid == "main":
        return ""
    e = engine_config(cfg, eid)
    what = ENGINES[eid]["label"]
    if ENGINES[eid]["kind"] == "openai" and e["model"]:
        return f"{ENGINES[eid]['icon']} Answered by {what} · {e['model']}"
    return f"{ENGINES[eid]['icon']} Answered by {what}"


__all__ = [
    "ENGINES", "ORDER", "SECONDARY", "DEFAULTS", "FREE_PROVIDERS",
    "engine_defaults", "engine_config", "public_engines", "credentials",
    "health", "check_openai", "check_dify", "check_openhands", "check_vtuber",
    "auto_route", "ready_engines", "resolve_engine", "stream_engine",
    "engine_error_message", "describe_routing", "history_text",
    "engine_ready", "friendly",
]
~~~~
