"""Tests for the turn-20 security hardening.

Needs: tests/mock_services.py running (9411) and the app started like this
(fresh usage db every run):

    CONFIG_FILE=/tmp/security-config.json PORT=9424 HOST=127.0.0.1 \
    KNOWLEDGE_DIR=/tmp/t5/kb USAGE_DB=/tmp/security-test.db \
    ADMIN_PASSWORD=admin-pw python3 app.py

Run the brute-force section LAST - it locks the test IP for 10 minutes.
"""
import json
import os
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:9424"
PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def chat(c, vid, text="hello"):
    r = c.post(BASE + "/api/chat", headers={"X-Visitor": vid},
               json={"messages": [{"role": "user", "content": text}]}, timeout=60)
    return r


def main():
    tag = uuid.uuid4().hex[:8]
    with httpx.Client() as c:
        print("== 1. security headers ==")
        r = c.get(BASE + "/")
        h = r.headers
        check("nosniff", h.get("x-content-type-options") == "nosniff", h.get("x-content-type-options"))
        check("frame-ancestors CSP", "frame-ancestors" in (h.get("content-security-policy") or ""),
              h.get("content-security-policy"))
        check("referrer-policy", h.get("referrer-policy") == "same-origin", h.get("referrer-policy"))
        check("permissions-policy", "microphone=()" in (h.get("permissions-policy") or ""),
              h.get("permissions-policy"))
        r2 = c.get(BASE + "/api/usage", headers={"X-Visitor": f"sec-h-{tag}"})
        check("headers on API too", r2.headers.get("x-content-type-options") == "nosniff")

        print("== 2. chat rate limit (10/min, 11th blocked) ==")
        vid = f"sec-chat-{tag}"
        codes = [chat(c, vid).status_code for _ in range(10)]
        check("first 10 chats allowed", all(x == 200 for x in codes), codes)
        r = chat(c, vid)
        check("11th chat is 429", r.status_code == 429, r.status_code)
        check("429 says retry", "again" in r.text.lower(), r.text[:120])
        other = chat(c, f"sec-chat2-{tag}")
        check("other visitor unaffected", other.status_code == 200, other.status_code)
        own = c.post(BASE + "/api/chat", headers={"X-Visitor": f"sec-owner-{tag}",
                                                  "X-Admin-Password": "admin-pw"},
                     json={"messages": [{"role": "user", "content": "hi"}]}, timeout=60)
        check("owner/admin exempt from chat limit", own.status_code == 200, own.status_code)

        print("== 3. payment-request throttle (3 per 15 min) ==")
        vid = f"sec-paid-{tag}"
        codes = [c.post(BASE + "/api/billing/paid", headers={"X-Visitor": vid}).status_code
                 for _ in range(3)]
        check("3 payment refs allowed", all(x == 200 for x in codes), codes)
        r = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": vid})
        check("4th is 429", r.status_code == 429, r.status_code)
        first = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": f"sec-paid2-{tag}"})
        body = first.json() if first.status_code == 200 else {}
        check("payment still carries bank + ref",
              body.get("ref", "").startswith("MA-") and "bank" in body, body)

        print("== 4. pending-payment cap (5 per visitor) ==")
        os.environ.setdefault("USAGE_DB", "/tmp/security-test.db")
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import billing
        billing.bind(lambda: json.load(open("/tmp/security-config.json")), lambda r: False)
        cfg = json.load(open("/tmp/security-config.json"))
        capv = f"sec-cap-{tag}"
        try:
            for i in range(5):
                billing.make_manual_payment(cfg, capv)
            made = "5 pending refs created"
        except Exception as e:  # noqa: BLE001
            made = f"unexpected: {e}"
        check("cap prep: 5 refs ok", made == "5 pending refs created", made)
        try:
            billing.make_manual_payment(cfg, capv)
            blocked = False
        except httpx.HTTPStatusError as e:
            blocked = e.response.status_code == 409
        except Exception as e:  # HTTPException is not HTTPStatusError
            blocked = "409" in str(getattr(e, "status_code", "")) or getattr(e, "status_code", 0) == 409
        check("6th pending ref refused (409)", bool(blocked), blocked)

        print("== 5. coupon guessing throttle (5 per 10 min) ==")
        vid = f"sec-coupon-{tag}"
        codes = [c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": vid},
                        json={"code": "NOPE"}).status_code for _ in range(5)]
        check("5 wrong codes get 4xx", all(x in (400, 404) for x in codes), codes)
        r = c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": vid}, json={"code": "NOPE"})
        check("6th attempt is 429", r.status_code == 429, r.status_code)

        print("== 6. admin brute-force lockout (LAST - locks test IP 10 min) ==")
        codes = [c.post(BASE + "/api/config", headers={"X-Admin-Password": f"wrong{i}"},
                        json={}).status_code for i in range(10)]
        check("10 wrong passwords -> 401", all(x == 401 for x in codes), codes)
        r = c.post(BASE + "/api/config", headers={"X-Admin-Password": "admin-pw"}, json={})
        check("correct password now 429 (locked)", r.status_code == 429, r.status_code)
        r = c.get(BASE + "/api/billing/admin", headers={"X-Admin-Password": "admin-pw"})
        check("lockout covers billing admin too", r.status_code == 429, r.status_code)
        r = c.get(BASE + "/api/usage", headers={"X-Visitor": f"sec-lock-{tag}"})
        check("normal visitors unaffected by lockout", r.status_code == 200, r.status_code)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
