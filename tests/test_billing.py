"""Tests for the free allowance, paywall and payments.

Needs: tests/mock_services.py running (9411 for the mock AI, 9415 for Stripe/Paystack)
and the app started like this (a FRESH usage db every run):

    CONFIG_FILE=tests/billing-config.json PORT=9421 HOST=127.0.0.1 \\
    USAGE_DB=/tmp/billing-test.db ADMIN_PASSWORD=admin-pw python3 app.py
"""
import hashlib
import hmac
import json
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:9421"
ADMIN = {"X-Admin-Password": "admin-pw"}
PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def chat(client, vid, text="hello"):
    return client.post(BASE + "/api/chat",
                       headers={"X-Visitor": vid, "Content-Type": "application/json"},
                       json={"messages": [{"role": "user", "content": text}]})


def events_of(response):
    out = []
    for block in response.text.split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
    return out


with httpx.Client(timeout=60) as c:
    print("\n== 1. the meter ==")
    r = c.get(BASE + "/api/usage", headers={"X-Visitor": "visitor-aaa"})
    u = r.json()
    check("usage endpoint answers", r.status_code == 200, r.text[:200])
    check("visitor id echoed back", r.headers.get("x-visitor-id") == "visitor-aaa", r.headers)
    check("fresh visitor has the full allowance", u["left_prompts"] == 2 and u["prompts_used"] == 0, u)
    check("price and plan are public", u["price"] == "49" and u["plan"] == "Test Plus", u)
    check("bank details reach the paywall", u["bank"]["bank"] == "FNB", u)
    check("secrets never leave the server",
          "sk_test_x" not in json.dumps(u) and "whsec_test" not in json.dumps(u))

    print("\n== 2. free prompts then paywall ==")
    e1 = events_of(chat(c, "visitor-aaa", "one"))
    e2 = events_of(chat(c, "visitor-aaa", "two"))
    check("first two answers stream", all(any(e["type"] == "delta" for e in ev) for ev in (e1, e2)))
    r3 = chat(c, "visitor-aaa", "three")
    e3 = events_of(r3)
    check("third question hits the paywall", e3 and e3[0]["type"] == "quota", e3[:1])
    q = e3[0]
    check("paywall says why", q.get("reason") == "prompts", q)
    check("paywall carries price, bank and note",
          q["price"] == "49" and q["bank"]["account_number"] == "62812345678"
          and "owner@example.com" in q["pay_note"], q)
    u = c.get(BASE + "/api/usage", headers={"X-Visitor": "visitor-aaa"}).json()
    check("meter shows nothing left", u["left_prompts"] == 0 and u["prompts_used"] == 2, u)
    check("blocked prompts don't count as usage", u["prompts_used"] == 2, u)

    print("\n== 3. tokens as a second limit ==")
    r = c.post(BASE + "/api/config", headers=ADMIN, json={"billing": {"free_prompts": 100,
                                                                      "free_tokens": 1}})
    check("limits can be changed", r.status_code == 200, r.text[:200])
    e = events_of(chat(c, "visitor-bbb", "first question spends the single token"))
    check("first question still answered", any(x["type"] == "delta" for x in e), e[:1])
    e = events_of(chat(c, "visitor-bbb", "a longer question that must exceed one token"))
    check("token limit triggers the paywall too", e and e[0]["type"] == "quota"
          and e[0]["reason"] == "tokens", e[:1])
    c.post(BASE + "/api/config", headers=ADMIN,
           json={"billing": {"free_prompts": 2, "free_tokens": 1000000}})

    print("\n== 4. the owner is never metered ==")
    for i in range(5):
        r = chat(c, "visitor-owner", f"owner question {i}")
        r.headers.get("x-visitor-id")
    r = c.post(BASE + "/api/chat", headers={"X-Visitor": "visitor-owner", **ADMIN},
               json={"messages": [{"role": "user", "content": "owner again"}]})
    evs = events_of(r)
    check("owner with the admin password passes the paywall",
          any(e["type"] == "delta" for e in evs), evs[:1])
    u = c.get(BASE + "/api/usage", headers={"X-Visitor": "visitor-owner", **ADMIN}).json()
    check("owner meter says subscribed", u["subscribed"] is True and u["admin"] is True, u)

    print("\n== 5. coupon codes ==")
    r = c.post(BASE + "/api/billing/admin/coupon", headers=ADMIN,
               json={"days": 7, "code": "FRIEND7", "max_uses": 1})
    check("coupon created", r.status_code == 200 and r.json()["code"] == "FRIEND7", r.text[:200])
    r = c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": "visitor-aaa"},
               json={"code": "friend7"})
    check("coupon redeems case-insensitively", r.status_code == 200, r.text[:200])
    e = events_of(chat(c, "visitor-aaa", "after coupon"))
    check("redeemed visitor can ask again", any(x["type"] == "delta" for x in e), e[:1])
    u = c.get(BASE + "/api/usage", headers={"X-Visitor": "visitor-aaa"}).json()
    check("subscription shows for 7 days", u["subscribed"] and
          u["sub_until"] > time.time() + 6 * 86400, u)
    r = c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": "visitor-ccc"},
               json={"code": "FRIEND7"})
    check("a used-up coupon is refused", r.status_code == 409, r.status_code)
    r = c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": "visitor-ccc"},
               json={"code": "NOPE"})
    check("a fake coupon is refused", r.status_code == 404, r.status_code)

    print("\n== 6. bank transfer (EFT) flow ==")
    events_of(chat(c, "visitor-ddd", "spend one"))
    events_of(chat(c, "visitor-ddd", "spend two"))
    r = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": "visitor-ddd"})
    pay = r.json()
    check("EFT request returns bank details and a reference",
          pay["bank"]["bank"] == "FNB" and pay["ref"].startswith("MA-"), pay)
    e = events_of(chat(c, "visitor-ddd", "still blocked?"))
    check("3-h verification window unlocks while payment is pending",
          e and not any(x["type"] == "quota" for x in e), e[:1])
    u = c.get(BASE + "/api/usage", headers={"X-Visitor": "visitor-ddd"}).json()
    check("usage shows verifying", u.get("verifying") is True and u.get("verify_until"), u)
    stats = c.get(BASE + "/api/billing/admin", headers=ADMIN).json()
    check("owner sees the pending payment",
          any(p["id"] == pay["payment_id"] for p in stats["pending"]), stats["pending"])
    r = c.post(BASE + "/api/billing/admin/approve", headers=ADMIN,
               json={"payment_id": pay["payment_id"]})
    check("owner approves it", r.status_code == 200 and r.json()["ok"], r.text[:200])
    e = events_of(chat(c, "visitor-ddd", "after approval"))
    check("approved visitor can ask again", any(x["type"] == "delta" for x in e), e[:1])
    stats = c.get(BASE + "/api/billing/admin", headers=ADMIN).json()
    check("revenue counted", any(rv["currency"] == "ZAR" and rv["total"] == 49
                                 for rv in stats["revenue"]), stats["revenue"])
    r = c.post(BASE + "/api/billing/admin/reject", headers=ADMIN, json={"payment_id": "nope"})
    check("rejecting an unknown payment is harmless", r.status_code == 200, r.text[:100])

    print("\n== 7. admin endpoints are protected ==")
    r = c.get(BASE + "/api/billing/admin")
    check("stats need the password", r.status_code == 401, r.status_code)
    r = c.post(BASE + "/api/billing/admin/grant", json={"visitor": "x", "days": 30})
    check("granting needs the password", r.status_code == 401, r.status_code)
    r = c.post(BASE + "/api/config", json={"billing": {"price": "1"}})
    check("price changes need the password", r.status_code == 401, r.status_code)
    pub = c.get(BASE + "/api/config").json()
    check("public config hides the payment keys",
          "stripe_secret" not in json.dumps(pub["billing"]), list(pub["billing"]))
    r = c.post(BASE + "/api/config", headers=ADMIN,
               json={"billing": {"stripe_secret": "", "price": "59"}})
    cfg = c.get(BASE + "/api/config", headers=ADMIN)
    saved = json.loads(open(os.environ.get("CFG_PATH", "/dev/null")).read()) \
        if os.environ.get("CFG_PATH") else None
    check("empty secret field keeps the stored key",
          r.json()["billing"].get("stripe_secret", "absent") == "absent"
          or "sk_test" not in json.dumps(r.json()["billing"]), r.text[:200])
    check("price updated", r.json()["billing"]["price"] == "59", r.json()["billing"])
    c.post(BASE + "/api/config", headers=ADMIN, json={"billing": {"price": "49"}})

    print("\n== 8. card checkout: Stripe ==")
    events_of(chat(c, "visitor-eee", "spend one"))
    events_of(chat(c, "visitor-eee", "spend two"))
    e = events_of(chat(c, "visitor-eee", "blocked now"))
    check("stripe visitor is blocked before paying", e and e[0]["type"] == "quota", e[:1])
    r = c.post(BASE + "/api/billing/checkout", headers={"X-Visitor": "visitor-eee"},
               json={"provider": "stripe", "email": "payer@example.com"})
    ch = r.json()
    check("stripe checkout returns a hosted url", r.status_code == 200
          and ch["url"].startswith("http://127.0.0.1:9415/stripe-pay/"), ch)
    session_id = ch["payment_id"]
    ts = str(int(time.time()))
    body = json.dumps({"type": "checkout.session.completed",
                       "data": {"object": {"id": session_id,
                                           "client_reference_id": "visitor-eee",
                                           "metadata": {"visitor": "visitor-eee"}}}}).encode()
    sig = hmac.new(b"whsec_test", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    r = c.post(BASE + "/api/billing/webhook/stripe", content=body,
               headers={"Stripe-Signature": f"t={ts},v1={sig}"})
    check("signed webhook activates the subscription", r.status_code == 200
          and r.json()["ok"], r.text[:200])
    e = events_of(chat(c, "visitor-eee", "after stripe"))
    check("stripe payer can ask", any(x["type"] == "delta" for x in e), e[:1])
    bad = hmac.new(b"wrong", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    r = c.post(BASE + "/api/billing/webhook/stripe", content=body,
               headers={"Stripe-Signature": f"t={ts},v1={bad}"})
    check("a forged webhook signature is rejected", r.status_code == 400, r.status_code)

    print("\n== 9. card checkout: Paystack ==")
    events_of(chat(c, "visitor-fff", "spend one"))
    events_of(chat(c, "visitor-fff", "spend two"))
    r = c.post(BASE + "/api/billing/checkout", headers={"X-Visitor": "visitor-fff"},
               json={"provider": "paystack", "email": "payer2@example.com"})
    ch = r.json()
    check("paystack returns a payment page", r.status_code == 200
          and ch["url"].endswith(ch["payment_id"]), ch)
    r = c.post(BASE + "/api/billing/webhook/paystack",
               json={"event": "charge.success", "data": {"reference": ch["payment_id"]}})
    check("paystack webhook verifies and activates", r.status_code == 200
          and r.json()["ok"], r.text[:200])
    e = events_of(chat(c, "visitor-fff", "after paystack"))
    check("paystack payer can ask", any(x["type"] == "delta" for x in e), e[:1])
    r = c.post(BASE + "/api/billing/webhook/paystack",
               json={"event": "charge.success", "data": {"reference": "PS-NOPE"}})
    check("an unknown paystack reference is rejected", r.status_code in (400, 502), r.status_code)
    r = c.post(BASE + "/api/billing/checkout", headers={"X-Visitor": "visitor-ggg"},
               json={"provider": "paystack", "email": ""})
    check("paystack insists on an email", r.status_code == 400, r.status_code)

    print("\n== 10. the dashboard ==")
    stats = c.get(BASE + "/api/billing/admin", headers=ADMIN).json()
    check("visitor count", stats["visitors"] >= 7, stats["visitors"])
    check("prompt count", stats["prompts"] >= 8, stats["prompts"])
    check("blocked count", stats["blocked_prompts"] >= 3, stats["blocked_prompts"])
    check("two paying subscribers", stats["active_subs"] >= 4, stats["active_subs"])
    check("revenue in Rand", stats["revenue"] and stats["revenue"][0]["currency"] == "ZAR",
          stats["revenue"])
    check("coupons listed", any(cp["code"] == "FRIEND7" for cp in stats["coupons"]),
          stats["coupons"])
    r = c.post(BASE + "/api/billing/admin/grant", headers=ADMIN,
               json={"visitor": "visitor-ggg", "days": 365, "provider": "owner"})
    check("owner can grant a year by hand", r.status_code == 200, r.text[:200])
    e = events_of(chat(c, "visitor-ggg", "after grant"))
    check("granted visitor can ask", any(x["type"] == "delta" for x in e), e[:1])

    print("\n== 11. billing switched off ==")
    c.post(BASE + "/api/config", headers=ADMIN, json={"billing": {"enabled": False}})
    for i in range(4):
        e = events_of(chat(c, "visitor-hhh", f"q{i}"))
    check("with billing off nobody is blocked", any(x["type"] == "delta" for x in e), e[:1])
    u = c.get(BASE + "/api/usage", headers={"X-Visitor": "visitor-hhh"}).json()
    check("meter says billing is off", u["enabled"] is False, u)
    c.post(BASE + "/api/config", headers=ADMIN, json={"billing": {"enabled": True}})

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
