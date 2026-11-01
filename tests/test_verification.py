"""Tests for the 3-hour verification window and the autonomous internal defence.

Needs: mock AI on 9411 and the app started like this (fresh db every run):

    CONFIG_FILE=/tmp/verify-config.json PORT=9425 HOST=127.0.0.1 \
    KNOWLEDGE_DIR=/tmp/t5/kb USAGE_DB=/tmp/verify-test.db \
    ADMIN_PASSWORD=admin-pw AI_API_KEY=mock-key python3 app.py

Run section 7 (auto-ban) LAST - it bans the test IP until an admin request
lifts it again (which the test also proves).
"""
import json
import sqlite3
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:9425"
DB = "/tmp/verify-test.db"
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


def chat(c, vid, text="hi"):
    r = c.post(BASE + "/api/chat", headers={"X-Visitor": vid},
               json={"messages": [{"role": "user", "content": text}]}, timeout=60)
    types = []
    for line in r.text.splitlines():
        if line.startswith("data: "):
            try:
                types.append(json.loads(line[6:]).get("type"))
            except Exception:
                pass
    return r.status_code, types


def usage(c, vid, headers=None):
    h = {"X-Visitor": vid}
    h.update(headers or {})
    return c.get(BASE + "/api/usage", headers=h).json()


def main():
    tag = uuid.uuid4().hex[:8]
    with httpx.Client() as c:
        print("== 1. payment grants a 3-hour verification window ==")
        vid = f"ver-a-{tag}"
        chat(c, vid)                                  # uses the 1 free prompt
        code, types = chat(c, vid)                    # now blocked
        check("paywall hit before paying", "quota" in types, types)
        r = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": vid})
        pay = r.json()
        vu = pay.get("verify_until")
        check("paid returns verify_until ~3h away",
              bool(vu) and abs(vu - (time.time() + 3 * 3600)) < 120, pay.get("verify_until"))
        u = usage(c, vid)
        check("usage says verifying", u.get("verifying") is True, u)
        code, types = chat(c, vid)
        check("chat allowed during verification", code == 200 and "quota" not in types,
              (code, types))

        print("== 2. window is once per visitor ==")
        r2 = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": vid})
        check("second ref has no new window", r2.json().get("verify_until") is None, r2.text[:150])

        print("== 3. expiry returns the paywall with a waiting note ==")
        con = sqlite3.connect(DB)
        con.execute("UPDATE payments SET verify_expires=? WHERE visitor_id=?",
                    (time.time() - 60, vid))
        con.commit()
        con.close()
        u = usage(c, vid)
        check("verifying is over", u.get("verifying") is False, u)
        check("verify_expired flag set", u.get("verify_expired") is True, u)
        code, types = chat(c, vid)
        check("chat blocked again after expiry", "quota" in types, types)

        print("== 4. owner rejection ends the window immediately ==")
        vid_b = f"ver-b-{tag}"
        chat(c, vid_b)
        pay_b = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": vid_b}).json()
        check("visitor B got a window", bool(pay_b.get("verify_until")), pay_b)
        code, types = chat(c, vid_b)
        check("B can chat while verifying", "quota" not in types, types)
        rj = c.post(BASE + "/api/billing/admin/reject", headers=ADMIN,
                    json={"payment_id": pay_b["payment_id"]})
        check("reject ok", rj.status_code == 200, rj.text[:120])
        code, types = chat(c, vid_b)
        check("B blocked right after rejection", "quota" in types, types)

        print("== 5. owner approval during window -> full 30-day sub ==")
        vid_c = f"ver-c-{tag}"
        chat(c, vid_c)
        pay_c = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": vid_c}).json()
        ap = c.post(BASE + "/api/billing/admin/approve", headers=ADMIN,
                    json={"payment_id": pay_c["payment_id"]})
        check("approve ok", ap.status_code == 200, ap.text[:120])
        u = usage(c, vid_c)
        check("C subscribed ~30 days", u.get("subscribed") is True and
              abs(u.get("sub_until", 0) - (time.time() + 30 * 86400)) < 300, u)

        print("== 6. dashboard + security panel ==")
        d = c.get(BASE + "/api/billing/admin", headers=ADMIN).json()
        check("dashboard counts verifying visitors", isinstance(d.get("verifying"), int), d.get("verifying"))
        pend = [p for p in d.get("pending", []) if p["visitor_id"] == vid]
        check("pending rows carry verify_expires", pend and "verify_expires" in pend[0], pend[:1])
        r = c.get(BASE + "/api/billing/admin/security")
        check("security panel needs the password", r.status_code == 401, r.status_code)
        # trip the chat limiter once so there is an event to show
        vid_s = f"ver-spam-{tag}"
        for _ in range(10):
            chat(c, vid_s)
        r = chat(c, vid_s)
        check("11th rapid chat is 429", r[0] == 429, r)
        sec = c.get(BASE + "/api/billing/admin/security", headers=ADMIN).json()
        kinds = [e["kind"] for e in sec.get("events", [])]
        check("chat_limit event logged", "chat_limit" in kinds, kinds[:8])
        check("events show hashed ip", all(len(e.get("ip") or "") == 16 for e in sec["events"]),
              sec["events"][:2])

        print("== 7. autonomous ban escalation (LAST) ==")
        # 1 block already counted from section 6; add 7 more: 1 paid-limit + 6 coupon-limits
        for _ in range(3):
            c.post(BASE + "/api/billing/paid", headers={"X-Visitor": f"ver-ban0-{tag}"})
        r = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": f"ver-ban0-{tag}"})
        check("paid limiter tripped", r.status_code == 429, r.status_code)
        for i in range(6):
            v = f"ver-cp{i}-{tag}"
            for _ in range(5):
                c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": v}, json={"code": "NOPE"})
            c.post(BASE + "/api/billing/coupon", headers={"X-Visitor": v}, json={"code": "NOPE"})
        r = c.post(BASE + "/api/chat", headers={"X-Visitor": f"ver-innocent-{tag}"},
                   json={"messages": [{"role": "user", "content": "hi"}]}, timeout=30)
        check("whole IP auto-banned after 8 trips", r.status_code == 429 and
              "blocked" in r.text.lower(), (r.status_code, r.text[:120]))
        rp = c.post(BASE + "/api/billing/paid", headers={"X-Visitor": f"ver-banx-{tag}"})
        check("ban also covers billing endpoints", rp.status_code == 429, rp.status_code)
        sec = c.get(BASE + "/api/billing/admin/security", headers=ADMIN).json()
        kinds = [e["kind"] for e in sec.get("events", [])]
        check("auto_ban event logged", "auto_ban" in kinds, kinds[:10])
        # NOTE: this admin-authenticated fetch legitimately lifts the ban on its own IP
        # (owner login = unblock). In production the attacker's IP differs from the
        # owner's and would remain visible here; locally we assert the structure.
        check("panel returns ban list (own-IP ban lifted by this owner login)",
              isinstance(sec.get("bans"), list), sec.get("bans"))
        u = usage(c, f"ver-owner-{tag}", ADMIN)
        check("owner password lifts the ban (admin true)", u.get("admin") is True, u)
        r = c.post(BASE + "/api/chat", headers={"X-Visitor": f"ver-after-{tag}"},
                   json={"messages": [{"role": "user", "content": "hi"}]}, timeout=30)
        check("traffic flows again after owner unlock", r.status_code == 200, r.status_code)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
