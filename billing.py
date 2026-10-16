"""
billing.py - free allowance, subscriptions and payments.

Every visitor gets a free allowance (a number of prompts and a number of tokens).
When it runs out the chat shows a paywall: subscribe by card (Stripe or Paystack,
both pay out to a bank account) or by direct bank transfer / EFT that the owner
confirms with one click. Coupon codes work too.

Everything is stored in a small SQLite file (usage.db) next to the app:

    visitors   one row per browser (anonymous id, first/last seen, salted ip hash)
    usage      one row per answered prompt (tokens in/out, estimated)
    subs       one row per visitor: paid-until date
    payments   manual EFT requests and card checkout records
    coupons    codes the owner creates for friends, tests or promos

Nothing personal is collected: no names, no emails unless a visitor types one to
pay by card, and IP addresses are stored only as a salted hash.
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

def _pick_db_path() -> Path:
    """Prefer USAGE_DB; fall back to the system temp dir when the app folder is
    read-only (free Docker hosts)."""
    p = Path(os.environ.get("USAGE_DB", Path(__file__).resolve().parent / "usage.db"))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        probe = p.parent / f".wtest-{os.getpid()}"
        probe.write_text("x")
        probe.unlink()
        return p
    except OSError:
        import tempfile
        alt = Path(tempfile.gettempdir()) / (p.name or "usage.db")
        print(f"[billing] {p.parent} is not writable; using {alt} instead", flush=True)
        return alt


DB_PATH = _pick_db_path()
_lock = threading.Lock()
INTERVAL_DAYS = {"month": 30, "year": 365, "week": 7}

DEFAULT_BILLING = {
    "enabled": True,
    "free_prompts": 15,            # how many questions a new visitor gets
    "free_tokens": 120000,         # and how many tokens (roughly words x 1.35)
    "window": "lifetime",          # "lifetime" or "monthly"
    "plan_name": "My AI Plus",
    "price": "49",                 # in major units, e.g. Rand
    "currency": "ZAR",
    "interval": "month",
    "providers": {"manual": True, "stripe": False, "paystack": False},
    "stripe_secret": "",
    "stripe_webhook_secret": "",
    "stripe_base": "https://api.stripe.com",
    "paystack_secret": "",
    "paystack_base": "https://api.paystack.co",
    "bank": {"bank": "", "account_name": "", "account_number": "", "branch": "", "reference_note": ""},
    "pay_note": "",                # e.g. "WhatsApp me the proof of payment: 082 …"
}

SECRET_FIELDS = ("stripe_secret", "stripe_webhook_secret", "paystack_secret")


# --------------------------------------------------------------------------- storage

# --------------------------------------------------------------------------- persistence
# Free hosts (Render etc.) wipe the disk whenever the service sleeps or redeploys.
# When TURSO_DB_URL + TURSO_AUTH_TOKEN are set, the whole (tiny) SQLite file is
# mirrored into a free Turso database: instantly after every money-relevant write,
# periodically for the counters, and restored at boot when the local file is gone.

TURSO_DB_URL = os.environ.get("TURSO_DB_URL", "").strip()
if TURSO_DB_URL.startswith("libsql://"):
    TURSO_DB_URL = "https://" + TURSO_DB_URL[len("libsql://"):]
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
_last_backup = 0.0


def turso_enabled() -> bool:
    return TURSO_DB_URL.startswith("http") and bool(TURSO_AUTH_TOKEN)


def _turso_sql(q: str, params=None):
    """Run one statement against Turso's HTTP API; returns {"rows": [[val,...],...]}."""
    args = []
    for v in params or []:
        if v is None:
            args.append({"type": "null"})
        elif isinstance(v, bool):
            args.append({"type": "integer", "value": "1" if v else "0"})
        elif isinstance(v, int):
            args.append({"type": "integer", "value": str(v)})
        elif isinstance(v, float):
            args.append({"type": "float", "value": repr(v)})
        else:
            args.append({"type": "text", "value": str(v)})
    body = {"requests": [{"type": "execute",
                          "stmt": {"sql": q, "args": args}, "batch_id": None}]}
    r = httpx.post(TURSO_DB_URL.rstrip("/") + "/v2/pipeline", json=body,
                   headers={"Authorization": "Bearer " + TURSO_AUTH_TOKEN}, timeout=30)
    r.raise_for_status()
    data = r.json()
    results = (data or {}).get("results") or [{}]
    res = results[0]
    if res.get("type") == "error":
        raise RuntimeError(str((res.get("error") or {}).get("message") or res.get("error")))
    out = ((res.get("response") or {}).get("result")) or {}
    rows = [[(c or {}).get("value") for c in row] for row in (out.get("rows") or [])]
    return {"rows": rows}


def backup_now(force: bool = False) -> bool:
    """Mirror usage.db to Turso. Throttled to once per 2 min unless forced."""
    global _last_backup
    if not turso_enabled():
        return False
    now = time.time()
    if not force and now - _last_backup < 120:
        return False
    try:
        with _lock:
            con = sqlite3.connect(DB_PATH, timeout=20)
            try:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                con.close()
            blob = base64.b64encode(Path(DB_PATH).read_bytes()).decode()
        _turso_sql("CREATE TABLE IF NOT EXISTS kv_store(k TEXT PRIMARY KEY, v TEXT)")
        _turso_sql("INSERT INTO kv_store(k, v) VALUES(?1, ?2) "
                   "ON CONFLICT(k) DO UPDATE SET v=excluded.v", ["usage_db", blob])
        _last_backup = time.time()
        return True
    except Exception as e:  # never take the app down over a backup
        print(f"[billing] turso backup failed: {e}", flush=True)
        return False


def restore_from_turso() -> bool:
    """Recreate usage.db from Turso when the local disk came back empty."""
    if not turso_enabled():
        return False
    try:
        if Path(DB_PATH).exists() and Path(DB_PATH).stat().st_size > 0:
            return False
        _turso_sql("CREATE TABLE IF NOT EXISTS kv_store(k TEXT PRIMARY KEY, v TEXT)")
        res = _turso_sql("SELECT v FROM kv_store WHERE k = 'usage_db'")
        rows = res.get("rows") or []
        if rows and rows[0] and rows[0][0]:
            Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
            Path(DB_PATH).write_bytes(base64.b64decode(rows[0][0]))
            print("[billing] restored usage.db from Turso backup", flush=True)
            return True
    except Exception as e:
        print(f"[billing] turso restore failed: {e}", flush=True)
    return False


def _backup_loop() -> None:
    while True:
        time.sleep(120)
        backup_now()


def _bg_backup() -> None:
    """Fire-and-forget mirror after a money-relevant write."""
    if turso_enabled():
        threading.Thread(target=backup_now, args=(True,), daemon=True).start()


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    restore_from_turso()
    with _lock, _connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS visitors(
            id TEXT PRIMARY KEY, first_seen REAL, last_seen REAL, ip_hash TEXT, ua TEXT,
            owner INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT, visitor_id TEXT, ts REAL,
            engine TEXT, tokens_in INTEGER, tokens_out INTEGER, blocked INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS usage_visitor ON usage(visitor_id, ts);
        CREATE TABLE IF NOT EXISTS subs(
            visitor_id TEXT PRIMARY KEY, plan TEXT, provider TEXT, ref TEXT,
            since REAL, until REAL);
        CREATE TABLE IF NOT EXISTS payments(
            id TEXT PRIMARY KEY, visitor_id TEXT, provider TEXT, amount TEXT,
            currency TEXT, status TEXT, ref TEXT, email TEXT, created REAL,
            paid_at REAL, meta TEXT);
        CREATE TABLE IF NOT EXISTS coupons(
            code TEXT PRIMARY KEY, days INTEGER, created REAL, uses INTEGER, max_uses INTEGER);
        """)
        try:   # migration: databases created before the lifetime-owner flag existed
            con.execute("ALTER TABLE visitors ADD COLUMN owner INTEGER DEFAULT 0")
        except Exception:
            pass
    if turso_enabled():
        threading.Thread(target=_backup_loop, daemon=True).start()
        atexit.register(backup_now, True)


def billing_config(cfg: dict) -> dict:
    """The saved billing settings on top of the defaults."""
    out = json.loads(json.dumps(DEFAULT_BILLING))
    saved = cfg.get("billing") or {}
    for k, v in saved.items():
        if k in ("providers", "bank") and isinstance(v, dict):
            out[k].update({a: b for a, b in v.items() if a in out[k] or k == "bank"})
        elif k in out:
            out[k] = v
    return out


def public_billing(cfg: dict) -> dict:
    """What the browser may see: prices and bank details, never keys."""
    b = billing_config(cfg)
    out = {k: v for k, v in b.items() if k not in SECRET_FIELDS and k != "stripe_base"
           and k != "paystack_base"}
    return out


def merge_billing(old: dict, incoming: dict) -> dict:
    """Apply validated Settings-screen changes on top of what is saved.
    Empty secret fields keep the stored key, so the browser never wipes them."""
    out = json.loads(json.dumps(old or DEFAULT_BILLING))
    base = json.loads(json.dumps(DEFAULT_BILLING))
    for k, v in base.items():
        out.setdefault(k, json.loads(json.dumps(v)))
    if not isinstance(incoming, dict):
        return out
    incoming = {k: v for k, v in incoming.items() if k in base}
    for k, v in incoming.items():
        if k in SECRET_FIELDS:
            val = str(v or "").strip()
            if val:
                out[k] = val[:300]
            continue
        if k in ("providers", "bank") and isinstance(v, dict):
            for a, b in v.items():
                if a in out[k]:
                    out[k][a] = (bool(b) if k == "providers" else str(b or "").strip()[:200])
        elif k in out and k not in ("providers", "bank"):
            if k in ("free_prompts", "free_tokens"):
                try:
                    out[k] = max(0, min(int(v), 10_000_000))
                except (TypeError, ValueError):
                    pass
            elif k in ("price",):
                out[k] = str(v or "").strip()[:10]
            elif k == "currency":
                out[k] = str(v or "ZAR").strip().upper()[:3]
            elif k == "interval":
                out[k] = v if v in INTERVAL_DAYS else "month"
            elif k == "window":
                out[k] = v if v in ("lifetime", "monthly") else "lifetime"
            elif k == "enabled":
                out[k] = bool(v)
            elif k in SECRET_FIELDS or k in ("stripe_base", "paystack_base"):
                out[k] = str(v or "").strip()[:300]
            else:
                out[k] = str(v or "").strip()[:400]
    return out


# --------------------------------------------------------------------------- visitors

def mark_owner(vid: str) -> None:
    """Flag this visitor as the owner: activated for life, never metered, no paywall.
    Called the moment a request proves the admin password for this visitor id."""
    if not vid:
        return
    with _lock, _connect() as con:
        con.execute("UPDATE visitors SET owner=1 WHERE id=? AND COALESCE(owner,0)=0", (vid,))


def is_owner(vid: str) -> bool:
    """True when this visitor id was marked as the owner before (lifetime activation)."""
    if not vid:
        return False
    with _lock, _connect() as con:
        row = con.execute("SELECT owner FROM visitors WHERE id=?", (vid,)).fetchone()
    return bool(row and row["owner"])

def visitor_id(request: Request) -> str:
    vid = (request.headers.get("x-visitor") or "").strip()
    if not vid or len(vid) > 64 or not all(c.isalnum() or c in "-_" for c in vid):
        vid = uuid.uuid4().hex
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "").split(",")[0].strip()
    salt = os.environ.get("ADMIN_PASSWORD", "myai")
    ip_hash = hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:16] if ip else ""
    ua = (request.headers.get("user-agent") or "")[:120]
    now = time.time()
    with _lock, _connect() as con:
        row = con.execute("SELECT id FROM visitors WHERE id=?", (vid,)).fetchone()
        if row:
            con.execute("UPDATE visitors SET last_seen=? WHERE id=?", (now, vid))
        else:
            con.execute("INSERT INTO visitors(id, first_seen, last_seen, ip_hash, ua) "
                        "VALUES(?,?,?,?,?)", (vid, now, now, ip_hash, ua))
    return vid


def estimate_tokens(chars: int) -> int:
    return max(1, math.ceil(chars / 4)) if chars else 0


# --------------------------------------------------------------------------- metering

def _window_start(b: dict) -> float:
    if b["window"] == "monthly":
        return time.time() - 30 * 86400
    return 0.0


def sub_for(visitor: str) -> dict | None:
    with _lock, _connect() as con:
        row = con.execute("SELECT * FROM subs WHERE visitor_id=?", (visitor,)).fetchone()
    if not row:
        return None
    return dict(row)


def usage_totals(b: dict, visitor: str) -> dict:
    start = _window_start(b)
    with _lock, _connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS prompts, COALESCE(SUM(tokens_in+tokens_out),0) AS tokens "
            "FROM usage WHERE visitor_id=? AND ts>=? AND blocked=0", (visitor, start)).fetchone()
    return {"prompts": row["prompts"], "tokens": row["tokens"]}


def check_quota(cfg: dict, visitor: str, admin_ok: bool) -> dict:
    """Is this visitor allowed to ask another question? Returns a status dict."""
    b = billing_config(cfg)
    sub = sub_for(visitor)
    active = bool(sub and sub["until"] > time.time())
    if admin_ok or not b["enabled"]:
        return {"allowed": True, "sub": active, "reason": ""}
    if active:
        return {"allowed": True, "sub": True, "reason": ""}
    totals = usage_totals(b, visitor)
    if totals["prompts"] >= b["free_prompts"] > 0:
        return {"allowed": False, "sub": False, "reason": "prompts",
                "used": totals, "sub_row": sub}
    if totals["tokens"] >= b["free_tokens"] > 0:
        return {"allowed": False, "sub": False, "reason": "tokens",
                "used": totals, "sub_row": sub}
    return {"allowed": True, "sub": False, "reason": ""}


def record(cfg: dict, visitor: str, engine: str, chars_in: int, chars_out: int,
           blocked: bool = False) -> None:
    with _lock, _connect() as con:
        con.execute("INSERT INTO usage(visitor_id, ts, engine, tokens_in, tokens_out, blocked) "
                    "VALUES(?,?,?,?,?,?)",
                    (visitor, time.time(), engine, estimate_tokens(chars_in),
                     estimate_tokens(chars_out), 1 if blocked else 0))


def usage_payload(cfg: dict, visitor: str, admin_ok: bool) -> dict:
    b = billing_config(cfg)
    totals = usage_totals(b, visitor)
    sub = sub_for(visitor)
    active = bool(sub and sub["until"] > time.time())
    left_p = max(0, b["free_prompts"] - totals["prompts"]) if b["free_prompts"] else None
    left_t = max(0, b["free_tokens"] - totals["tokens"]) if b["free_tokens"] else None
    return {
        "visitor": visitor,
        "enabled": bool(b["enabled"]) and not admin_ok,
        "admin": admin_ok,
        "prompts_used": totals["prompts"],
        "tokens_used": totals["tokens"],
        "free_prompts": b["free_prompts"],
        "free_tokens": b["free_tokens"],
        "left_prompts": left_p,
        "left_tokens": left_t,
        "window": b["window"],
        "subscribed": active or admin_ok,
        "owner_lifetime": admin_ok and is_owner(visitor),
        "sub_until": sub["until"] if sub else None,
        "plan": b["plan_name"],
        "price": b["price"],
        "currency": b["currency"],
        "interval": b["interval"],
        "providers": {k: bool(v) for k, v in b["providers"].items()},
        "bank": b["bank"],
        "pay_note": b["pay_note"],
    }


# --------------------------------------------------------------------------- paying

def _new_sub(con: sqlite3.Connection, visitor: str, days: int, plan: str, provider: str,
             ref: str) -> float:
    now = time.time()
    row = con.execute("SELECT until FROM subs WHERE visitor_id=?", (visitor,)).fetchone()
    start = max(now, row["until"]) if row and row["until"] > now else now
    until = start + days * 86400
    con.execute("INSERT INTO subs(visitor_id, plan, provider, ref, since, until) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(visitor_id) DO UPDATE SET "
                "plan=excluded.plan, provider=excluded.provider, ref=excluded.ref, "
                "since=excluded.since, until=excluded.until",
                (visitor, plan, provider, ref, now, until))
    return until


def make_manual_payment(cfg: dict, visitor: str) -> dict:
    b = billing_config(cfg)
    ref = f"MA-{visitor[:6].upper()}-{secrets.token_hex(2).upper()}"
    pid = secrets.token_hex(8)
    with _lock, _connect() as con:
        con.execute("INSERT INTO payments(id, visitor_id, provider, amount, currency, status, "
                    "ref, email, created, paid_at, meta) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, visitor, "manual", b["price"], b["currency"], "pending", ref, "",
                     time.time(), None, ""))
    _bg_backup()
    return {"payment_id": pid, "ref": ref, "amount": b["price"], "currency": b["currency"],
            "bank": b["bank"], "pay_note": b["pay_note"]}


def redeem_coupon(cfg: dict, visitor: str, code: str) -> dict:
    code = (code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Type the code first.")
    b = billing_config(cfg)
    with _lock, _connect() as con:
        row = con.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, "That code doesn't exist.")
        if row["max_uses"] and row["uses"] >= row["max_uses"]:
            raise HTTPException(409, "That code has been used up.")
        until = _new_sub(con, visitor, row["days"], b["plan_name"], "coupon", code)
        con.execute("UPDATE coupons SET uses=uses+1 WHERE code=?", (code,))
    _bg_backup()
    return {"ok": True, "until": until, "days": row["days"]}


def create_coupon(days: int, code: str = "", max_uses: int = 1) -> dict:
    code = (code or secrets.token_hex(3)).upper()[:12]
    with _lock, _connect() as con:
        try:
            con.execute("INSERT INTO coupons(code, days, created, uses, max_uses) "
                        "VALUES(?,?,?,?,?)", (code, max(1, days), time.time(), 0, max(0, max_uses)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "That code already exists.")
    _bg_backup()
    return {"code": code, "days": days, "max_uses": max_uses}


def grant_days(visitor: str, days: int, provider: str = "owner") -> dict:
    b_plan = "owner grant"
    with _lock, _connect() as con:
        until = _new_sub(con, visitor, days, b_plan, provider, f"grant-{secrets.token_hex(3)}")
    _bg_backup()
    return {"ok": True, "until": until}


# ---------------------------------------------------------------- card checkouts

def _minor_units(amount: str, currency: str) -> int:
    try:
        major = float(amount)
    except ValueError:
        raise HTTPException(400, "The price in Settings isn't a number.")
    if currency.upper() in ("JPY", "KRW", "VND", "CLP"):
        return int(round(major))
    return int(round(major * 100))


def stripe_checkout(cfg: dict, visitor: str, email: str, success_url: str) -> dict:
    b = billing_config(cfg)
    if not b["stripe_secret"]:
        raise HTTPException(400, "Stripe isn't configured yet (Settings → Plans & payments).")
    data = {
        "mode": "subscription",
        "client_reference_id": visitor,
        "customer_email": email or None,
        "success_url": success_url,
        "cancel_url": success_url,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": b["currency"].lower(),
        "line_items[0][price_data][unit_amount]": str(_minor_units(b["price"], b["currency"])),
        "line_items[0][price_data][recurring][interval]": b["interval"],
        "line_items[0][price_data][product_data][name]": b["plan_name"],
        "subscription_data[metadata][visitor]": visitor,
        "metadata[visitor]": visitor,
    }
    data = {k: v for k, v in data.items() if v is not None}
    r = httpx.post(b["stripe_base"].rstrip("/") + "/v1/checkout/sessions", data=data,
                   auth=(b["stripe_secret"], ""), timeout=30)
    if r.status_code >= 400:
        raise HTTPException(502, f"Stripe said: {r.text[:300]}")
    session = r.json()
    with _lock, _connect() as con:
        con.execute("INSERT INTO payments(id, visitor_id, provider, amount, currency, status, "
                    "ref, email, created, paid_at, meta) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (session["id"], visitor, "stripe", b["price"], b["currency"], "pending",
                     session["id"], email, time.time(), None, ""))
    return {"url": session["url"], "payment_id": session["id"]}


def paystack_checkout(cfg: dict, visitor: str, email: str, success_url: str) -> dict:
    b = billing_config(cfg)
    if not b["paystack_secret"]:
        raise HTTPException(400, "Paystack isn't configured yet (Settings → Plans & payments).")
    if not email or "@" not in email:
        raise HTTPException(400, "Paystack needs your email address for the receipt.")
    data = {
        "email": email,
        "amount": str(_minor_units(b["price"], b["currency"])),
        "currency": b["currency"].upper(),
        "callback_url": success_url,
        "reference": f"PS-{visitor[:8]}-{secrets.token_hex(3)}",
        "metadata": json.dumps({"visitor": visitor}),
    }
    r = httpx.post(b["paystack_base"].rstrip("/") + "/transaction/initialize", data=data,
                   headers={"Authorization": f"Bearer {b['paystack_secret']}"}, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(502, f"Paystack said: {r.text[:300]}")
    body = r.json()
    ref = body["data"]["reference"]
    with _lock, _connect() as con:
        con.execute("INSERT INTO payments(id, visitor_id, provider, amount, currency, status, "
                    "ref, email, created, paid_at, meta) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (ref, visitor, "paystack", b["price"], b["currency"], "pending", ref, email,
                     time.time(), None, ""))
    return {"url": body["data"]["authorization_url"], "payment_id": ref}


def _activate_from_payment(cfg: dict, provider: str, ref: str, meta_visitor: str = "") -> dict:
    b = billing_config(cfg)
    with _lock, _connect() as con:
        row = con.execute("SELECT * FROM payments WHERE ref=? OR id=?", (ref, ref)).fetchone()
        if not row:
            return {"ok": False, "why": "unknown payment"}
        if row["status"] == "paid":
            return {"ok": True, "already": True}
        visitor = meta_visitor or row["visitor_id"]
        until = _new_sub(con, visitor, INTERVAL_DAYS.get(b["interval"], 30), b["plan_name"],
                         provider, ref)
        con.execute("UPDATE payments SET status='paid', paid_at=? WHERE id=?",
                    (time.time(), row["id"]))
    _bg_backup()
    return {"ok": True, "visitor": visitor, "until": until}


def stripe_webhook(cfg: dict, raw: bytes, signature: str) -> dict:
    b = billing_config(cfg)
    secret = b["stripe_webhook_secret"]
    if secret:
        try:
            parts = dict(p.split("=", 1) for p in signature.split(","))
            stamped = parts.get("t", "")
            expect = hmac.new(secret.encode(), f"{stamped}.".encode() + raw, hashlib.sha256) \
                .hexdigest()
            if not hmac.compare_digest(expect, parts.get("v1", "")):
                raise HTTPException(400, "Bad webhook signature.")
        except (ValueError, AttributeError):
            raise HTTPException(400, "Bad webhook signature.")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Not JSON.")
    if event.get("type") != "checkout.session.completed":
        return {"ok": True, "ignored": event.get("type")}
    session = event["data"]["object"]
    visitor = (session.get("metadata") or {}).get("visitor")         or session.get("client_reference_id") or ""
    return _activate_from_payment(cfg, "stripe", session.get("id") or "", visitor)


def paystack_webhook(cfg: dict, event: dict) -> dict:
    b = billing_config(cfg)
    if event.get("event") != "charge.success":
        return {"ok": True, "ignored": event.get("event")}
    ref = (event.get("data") or {}).get("reference")
    if not ref:
        raise HTTPException(400, "No reference in the webhook.")
    r = httpx.get(b["paystack_base"].rstrip("/") + f"/transaction/verify/{ref}",
                  headers={"Authorization": f"Bearer {b['paystack_secret']}"}, timeout=30)
    if r.status_code >= 400 or not r.json().get("status"):
        raise HTTPException(502, "Paystack wouldn't confirm the payment.")
    data = r.json()["data"]
    if data.get("status") != "success":
        return {"ok": False, "why": data.get("status")}
    meta = data.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    return _activate_from_payment(cfg, "paystack", ref, meta.get("visitor", ""))


# --------------------------------------------------------------------------- admin

def admin_stats() -> dict:
    day = time.time() - 86400
    with _lock, _connect() as con:
        visitors = con.execute("SELECT COUNT(*) c FROM visitors").fetchone()["c"]
        new_today = con.execute("SELECT COUNT(*) c FROM visitors WHERE first_seen>=?",
                                (day,)).fetchone()["c"]
        prompts = con.execute("SELECT COUNT(*) c FROM usage WHERE blocked=0").fetchone()["c"]
        prompts_today = con.execute("SELECT COUNT(*) c FROM usage WHERE blocked=0 AND ts>=?",
                                    (day,)).fetchone()["c"]
        tokens = con.execute("SELECT COALESCE(SUM(tokens_in+tokens_out),0) c FROM usage "
                             "WHERE blocked=0").fetchone()["c"]
        blocked = con.execute("SELECT COUNT(*) c FROM usage WHERE blocked=1").fetchone()["c"]
        subs = con.execute("SELECT COUNT(*) c FROM subs WHERE until>?",
                           (time.time(),)).fetchone()["c"]
        paid = con.execute("SELECT currency, COUNT(*) n, SUM(CAST(amount AS REAL)) total "
                           "FROM payments WHERE status='paid' GROUP BY currency").fetchall()
        pending = [dict(r) for r in con.execute(
            "SELECT * FROM payments WHERE status='pending' ORDER BY created DESC LIMIT 50")]
        coupons = [dict(r) for r in con.execute("SELECT * FROM coupons ORDER BY created DESC")]
        recent = [dict(r) for r in con.execute(
            "SELECT visitor_id, plan, provider, until FROM subs ORDER BY until DESC LIMIT 50")]
    return {
        "visitors": visitors, "new_today": new_today,
        "prompts": prompts, "prompts_today": prompts_today, "tokens": tokens,
        "blocked_prompts": blocked, "active_subs": subs,
        "revenue": [{"currency": r["currency"], "payments": r["n"],
                     "total": round(r["total"] or 0, 2)} for r in paid],
        "pending": pending, "coupons": coupons, "subs": recent,
    }


router = APIRouter()


def _require_admin(request: Request) -> None:
    pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    given = request.headers.get("x-admin-password", "")
    if pw and not hmac.compare_digest(given.encode(), pw.encode()):
        raise HTTPException(401, "Admin password required")


@router.get("/api/usage")
async def get_usage(request: Request):
    cfg = _cfg()
    vid = visitor_id(request)
    admin_ok = _is_admin(request)
    if admin_ok:
        mark_owner(vid)                      # proved the password once -> owner for life
    admin_ok = admin_ok or is_owner(vid)
    return JSONResponse(usage_payload(cfg, vid, admin_ok),
                        headers={"X-Visitor-Id": vid})


@router.post("/api/billing/paid")
async def billing_paid(request: Request):
    cfg = _cfg()
    vid = visitor_id(request)
    return make_manual_payment(cfg, vid)


@router.post("/api/billing/coupon")
async def billing_coupon(request: Request):
    cfg = _cfg()
    vid = visitor_id(request)
    body = await request.json()
    return redeem_coupon(cfg, vid, str(body.get("code") or ""))


@router.post("/api/billing/checkout")
async def billing_checkout(request: Request):
    cfg = _cfg()
    vid = visitor_id(request)
    body = await request.json()
    provider = str(body.get("provider") or "")
    email = str(body.get("email") or "").strip()
    success = str(body.get("success_url") or str(request.base_url).rstrip("/")) + "/?paid=1"
    if provider == "stripe":
        return stripe_checkout(cfg, vid, email, success)
    if provider == "paystack":
        return paystack_checkout(cfg, vid, email, success)
    raise HTTPException(400, "Unknown payment provider.")


@router.post("/api/billing/webhook/stripe")
async def webhook_stripe(request: Request):
    raw = await request.body()
    return stripe_webhook(_cfg(), raw, request.headers.get("stripe-signature", ""))


@router.post("/api/billing/webhook/paystack")
async def webhook_paystack(request: Request):
    body = await request.json()
    return paystack_webhook(_cfg(), body)


@router.get("/api/billing/admin")
async def billing_admin(request: Request):
    _require_admin(request)
    return admin_stats()


@router.post("/api/billing/admin/approve")
async def billing_approve(request: Request):
    _require_admin(request)
    body = await request.json()
    pid = str(body.get("payment_id") or "")
    with _lock, _connect() as con:
        row = con.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Payment not found.")
    return _activate_from_payment(_cfg(), row["provider"], row["ref"], row["visitor_id"])


@router.post("/api/billing/admin/reset")
async def billing_reset(request: Request):
    """Owner-only: wipe all visitor/usage/payment/coupon data (e.g. after testing)."""
    _require_admin(request)
    body = await request.json()
    if str(body.get("confirm") or "") != "RESET":
        raise HTTPException(400, "Body must include confirm: 'RESET'.")
    with _lock, _connect() as con:
        for t in ("usage", "payments", "coupons", "subs", "visitors"):
            con.execute(f"DELETE FROM {t}")
    backup_now(force=True)
    return {"ok": True}


@router.post("/api/billing/admin/reject")
async def billing_reject(request: Request):
    _require_admin(request)
    body = await request.json()
    pid = str(body.get("payment_id") or "")
    with _lock, _connect() as con:
        con.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
    _bg_backup()
    return {"ok": True}


@router.post("/api/billing/admin/coupon")
async def billing_new_coupon(request: Request):
    _require_admin(request)
    body = await request.json()
    return create_coupon(int(body.get("days") or 30), str(body.get("code") or ""),
                         int(body.get("max_uses") or 1))


@router.post("/api/billing/admin/grant")
async def billing_grant(request: Request):
    _require_admin(request)
    body = await request.json()
    return grant_days(str(body.get("visitor") or ""), int(body.get("days") or 30),
                      str(body.get("provider") or "owner"))


# Late-bound helpers (app.py injects them so this module stays import-safe).
_cfg = None
_is_admin = None


def bind(get_cfg, is_admin) -> None:
    global _cfg, _is_admin
    _cfg, _is_admin = get_cfg, is_admin
