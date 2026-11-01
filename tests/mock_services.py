"""Mock servers that behave like Ollama / OpenRouter / Dify / OpenHands / Open-LLM-VTuber.

Run:  python tests/mock_services.py     (ports 9411-9414)
"""
import asyncio
import base64
import json
import math
import struct
import threading
import time

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse


def log(*a):
    print("[mock]", *a, flush=True)


# ------------------------------------------------------------------ OpenAI-compatible
oai = FastAPI()
CALLS = {"log": []}


@oai.get("/v1/models")
async def oai_models(request: Request):
    CALLS["log"].append(("models", dict(request.headers)))
    return {"object": "list", "data": [
        {"id": "orca-mini"}, {"id": "llama3.2"}, {"id": "openrouter/auto"},
        {"id": "openhands_demo"}, {"id": "qwen2.5"}]}


@oai.post("/v1/chat/completions")
async def oai_chat(request: Request):
    body = await request.json()
    auth = request.headers.get("authorization", "")
    sess = request.headers.get("x-session-api-key", "")
    CALLS["log"].append(("chat", {"model": body.get("model"), "auth": auth, "session": sess,
                                  "n": len(body.get("messages") or []),
                                  "last": (body.get("messages") or [{}])[-1]}))
    model = body.get("model", "")
    reply = f"[{model}] answered: I got {len(body.get('messages') or [])} messages. " \
            f"Last one was: {str((body.get('messages') or [{}])[-1].get('content'))[:60]}"
    if not body.get("stream"):
        return {"id": "1", "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                             "finish_reason": "stop"}]}

    async def gen():
        for piece in [reply[i:i + 12] for i in range(0, len(reply), 12)]:
            yield "data: " + json.dumps({"object": "chat.completion.chunk", "choices": [
                {"index": 0, "delta": {"content": piece}, "finish_reason": None}]}) + "\n\n"
            await asyncio.sleep(0.005)
        yield "data: " + json.dumps({"object": "chat.completion.chunk", "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------------------------------------------------ Dify
dify = FastAPI()
DIFY = {"conversations": 0, "log": []}


@dify.get("/v1/parameters")
async def dify_params(request: Request):
    if request.headers.get("authorization") != "Bearer app-good-key":
        return JSONResponse({"code": "unauthorized", "message": "bad key"}, status_code=401)
    return {"opening_statement": "Hi! I am the Dify demo bot.", "user_input_form": []}


@dify.post("/v1/chat-messages")
async def dify_chat(request: Request):
    body = await request.json()
    DIFY["log"].append(body)
    if request.headers.get("authorization") != "Bearer app-good-key":
        return JSONResponse({"code": "unauthorized", "message": "invalid api key"}, status_code=401)
    cid = body.get("conversation_id") or f"conv-{DIFY['conversations']}"
    DIFY["conversations"] += 1
    q = body.get("query", "")

    async def gen():
        answer = f"Dify here. You asked: “{q[:400]}”. Conversation {cid}."
        for piece in [answer[i:i + 10] for i in range(0, len(answer), 10)]:
            yield "data: " + json.dumps({"event": "message", "conversation_id": cid,
                                         "message_id": "m1", "answer": piece}) + "\n\n"
            await asyncio.sleep(0.004)
        yield "data: " + json.dumps({"event": "message_end", "conversation_id": cid,
                                     "metadata": {"usage": {"total_tokens": 42}}}) + "\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------------------------------------------------ OpenHands
oh = FastAPI()
OH = {"log": []}


@oh.get("/health")
async def oh_health():
    return {"status": "ok", "version": "1.31.0"}


@oh.get("/api/profiles")
async def oh_profiles(request: Request):
    OH["log"].append(("profiles", request.headers.get("x-session-api-key", "")))
    return {"items": [{"name": "demo"}, {"name": "security"}]}


@oh.get("/v1/models")
async def oh_models(request: Request):
    return {"object": "list", "data": [{"id": "openhands_demo"}, {"id": "openhands_security"}]}


@oh.post("/v1/chat/completions")
async def oh_chat(request: Request):
    body = await request.json()
    OH["log"].append(("chat", body.get("model"), request.headers.get("x-session-api-key", ""),
                      request.headers.get("authorization", "")[:24]))
    last = (body.get("messages") or [{}])[-1]
    text = str(last.get("content"))
    reply = (f"OpenHands agent ({body.get('model')}) finished the job.\n\n"
             f"I read the repo, changed 3 files and the tests pass.\n\nTask was: {text[:80]}")

    async def gen():
        for piece in [reply[i:i + 16] for i in range(0, len(reply), 16)]:
            yield "data: " + json.dumps({"object": "chat.completion.chunk", "choices": [
                {"index": 0, "delta": {"content": piece}, "finish_reason": None}]}) + "\n\n"
            await asyncio.sleep(0.004)
        yield "data: " + json.dumps({"object": "chat.completion.chunk", "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-OpenHands-ServerConversation-ID": "oh-conv-1"})


# ------------------------------------------------------------------ Open-LLM-VTuber
vt = FastAPI()
VT = {"log": []}


def wav_tone(ms=120, freq=440.0, rate=16000):
    """A tiny valid WAV file so the browser can really play it."""
    n = int(rate * ms / 1000)
    frames = b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * freq * i / rate)))
                      for i in range(n))
    hdr = b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt " + \
        struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + \
        b"data" + struct.pack("<I", len(frames))
    return hdr + frames


@vt.get("/live2d-models/info")
async def vt_info():
    return {"models": ["shizuku-local"]}


@vt.websocket("/client-ws")
async def vt_ws(ws: WebSocket):
    await ws.accept()
    await ws.send_text(json.dumps({"type": "full-text", "text": "Connection established"}))
    await ws.send_text(json.dumps({"type": "set-model-and-conf", "model_info": {}, "config": {}}))
    await ws.send_text(json.dumps({"type": "control", "text": "start-mic"}))
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            VT["log"].append(msg.get("type"))
            if msg.get("type") != "text-input":
                continue
            text = msg.get("text", "")
            answer = f"Konnichiwa! You said: {text[:60]}. I am the VTuber."
            sentences = [answer[i:i + 34] for i in range(0, len(answer), 34)]
            for i, piece in enumerate(sentences):
                audio = base64.b64encode(wav_tone(90, 300 + i * 120)).decode()
                await ws.send_text(json.dumps({
                    "type": "audio", "audio": audio, "volumes": [0.5, 1.0, 0.4],
                    "slice_length": 20,
                    "display_text": {"text": piece, "name": "Airi", "avatar": ""},
                    "actions": None, "forwarded": False}))
                await ws.send_text(json.dumps({"type": "backend-synth-complete", "sequence": i}))
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass
    except Exception as exc:                                  # noqa: BLE001
        log("vtuber ws ended:", type(exc).__name__)


# ------------------------------------------------------------------ Stripe + Paystack
pay = FastAPI()
PAY = {"sessions": [], "txns": {}}


@pay.post("/v1/checkout/sessions")
async def stripe_session(request: Request):
    form = await request.form()
    auth = request.headers.get("authorization", "")
    if "Basic" not in auth:
        return JSONResponse({"error": {"message": "no api key"}}, status_code=401)
    sid = "cs_test_" + str(len(PAY["sessions"]) + 1)
    PAY["sessions"].append(dict(form))
    return {"id": sid, "url": f"http://127.0.0.1:9415/stripe-pay/{sid}",
            "object": "checkout.session"}


@pay.get("/stripe-pay/{sid}")
async def stripe_pay_page(sid: str):
    return {"note": "stand-in for the Stripe hosted checkout page", "session": sid}


@pay.post("/transaction/initialize")
async def ps_init(request: Request):
    form = await request.form()
    if not request.headers.get("authorization", "").startswith("Bearer "):
        return JSONResponse({"status": False, "message": "no key"}, status_code=401)
    ref = form.get("reference") or "PS-REF-1"
    PAY["txns"][ref] = {"status": "success", "reference": ref,
                        "metadata": form.get("metadata") or "{}",
                        "amount": form.get("amount")}
    return {"status": True, "data": {"reference": ref,
                                     "authorization_url": f"http://127.0.0.1:9415/ps-pay/{ref}"}}


@pay.get("/transaction/verify/{ref}")
async def ps_verify(ref: str):
    txn = PAY["txns"].get(ref)
    if not txn:
        return JSONResponse({"status": False, "message": "unknown ref"}, status_code=404)
    return {"status": True, "data": txn}


def serve(app, port):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    ports = {"oai": 9411, "dify": 9412, "oh": 9413, "vt": 9414, "pay": 9415}
    for name, port in ports.items():
        threading.Thread(target=serve, args=(globals()[name], port), daemon=True).start()
    log("mocks on", ports)
    time.sleep(1.2)
    while True:
        time.sleep(3600)
