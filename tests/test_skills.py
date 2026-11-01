"""Unit tests for the Agent Skills module (skills.py). Run: python3 tests/test_skills.py"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import skills  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


# ---------------------------------------------------------------- calculator
out = skills.run("calculator", json.dumps({"expression": "47*13+8"}))
check("calculator basic", out == "47*13+8 = 619", out)
out = skills.run("calculator", json.dumps({"expression": "(2+3)*4/2"}))
check("calculator parens", out.endswith("= 10"), out)
out = skills.run("calculator", json.dumps({"expression": "sqrt(144)"}))
check("calculator sqrt", out.endswith("= 12"), out)
out = skills.run("calculator", json.dumps({"expression": "round(pi, 4)"}))
check("calculator pi", out.endswith("= 3.1416"), out)
out = skills.run("calculator", json.dumps({"expression": "2**10"}))
check("calculator power", out.endswith("= 1024"), out)
out = skills.run("calculator", json.dumps({"expression": "1/0"}))
check("calculator div0", "Division by zero" in out, out)
# safety: no code execution, no attribute access, no imports
for evil in ["__import__('os').system('id')", "open('/etc/passwd').read()",
             "(1).__class__", "lambda: 1", "[x for x in range(3)]"]:
    out = skills.run("calculator", json.dumps({"expression": evil}))
    check(f"calculator blocks {evil[:22]!r}", "Could not calculate" in out, out)
out = skills.run("calculator", json.dumps({"expression": "9**99999999"}))
check("calculator huge power blocked", "Could not calculate" in out, out)

# ---------------------------------------------------------------- datetime
out = json.loads(skills.run("current_datetime", "{}"))
check("datetime default tz", out["timezone"] == "Africa/Johannesburg", out)
check("datetime has date+time", bool(out["date"]) and bool(out["time"]) and out["unix"] > 1_700_000_000, out)
out = json.loads(skills.run("current_datetime", json.dumps({"timezone": "UTC"})))
check("datetime utc", out["timezone"] == "UTC" and out["utc_offset"] == "+0000", out)
out = json.loads(skills.run("current_datetime", json.dumps({"timezone": "Mars/Olympus"})))
check("datetime bad tz falls back", out["timezone"].startswith("UTC"), out)

# ---------------------------------------------------------------- unit_convert
out = skills.run("unit_convert", json.dumps({"value": 100, "from_unit": "c", "to_unit": "f"}))
check("temp 100C->212F", "212" in out, out)
out = skills.run("unit_convert", json.dumps({"value": 1, "from_unit": "km", "to_unit": "mi"}))
check("km->mi", "0.621371" in out, out)
out = skills.run("unit_convert", json.dumps({"value": 1, "from_unit": "kg", "to_unit": "pounds"}))
check("kg->pounds alias", "2.20462" in out, out)
out = skills.run("unit_convert", json.dumps({"value": 1, "from_unit": "gib", "to_unit": "mb"}))
check("GiB->MB", "1073.741824" in out, out)
out = skills.run("unit_convert", json.dumps({"value": 5, "from_unit": "banana", "to_unit": "m"}))
check("unknown unit lists known", "Unknown unit" in out and "km" in out, out[:80])

# ---------------------------------------------------------------- text_tools
out = json.loads(skills.run("text_tools", json.dumps({"action": "count", "text": "Hello brave world"})))
check("text count", out["words"] == 3 and out["characters"] == 17, out)
out = skills.run("text_tools", json.dumps({"action": "upper", "text": "abc"}))
check("text upper", out == "ABC", out)
out = skills.run("text_tools", json.dumps({"action": "sha256", "text": "abc"}))
check("text sha256", out == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", out)
out = skills.run("text_tools", json.dumps({"action": "base64_encode", "text": "Smash AI"}))
check("text base64 encode", out == "TXkgQUk=", out)
out = skills.run("text_tools", json.dumps({"action": "base64_decode", "text": "TXkgQUk="}))
check("text base64 decode", out == "Smash AI", out)
out = skills.run("text_tools", json.dumps({"action": "slug", "text": "Smash AI Pro — Launch!"}))
check("text slug", out == "my-ai-pro-launch", out)
out = skills.run("text_tools", json.dumps({"action": "teleport", "text": "x"}))
check("text unknown action", "Unknown action" in out, out)

# ---------------------------------------------------------------- random
out = skills.run("random_generator", json.dumps({"action": "number", "minimum": 5, "maximum": 5}))
check("random fixed range", out.strip() == "5", out)
out = skills.run("random_generator", json.dumps({"action": "dice", "sides": 6, "count": 3}))
check("random dice", out.startswith("3d6:") and "total" in out, out)
out = skills.run("random_generator", json.dumps({"action": "coin"}))
check("random coin", out in ("heads", "tails"), out)
out = skills.run("random_generator", json.dumps({"action": "uuid"}))
check("random uuid", len(out) == 36 and out.count("-") == 4, out)
out = skills.run("random_generator", json.dumps({"action": "password", "length": 20}))
check("random password", len(out.split()[0]) == 20, out)

# ---------------------------------------------------------------- registry
defs = skills.tool_defs()
check("tool defs shape", len(defs) == len(skills.SKILLS) >= 6 and all(d["type"] == "function" and
      {"name", "description", "parameters"} <= set(d["function"]) for d in defs))
check("has()", skills.has("calculator") and not skills.has("launch_missiles"))
out = skills.run("launch_missiles", "{}")
check("unknown skill refused", "Unknown skill" in out, out)
out = skills.run("calculator", "not json at all")
check("bad args tolerated", "Could not calculate" in out or "No expression given" in out, out)

# ---------------------------------------------------------------- web_search (network)
t0 = time.time()
out = skills.run("web_search", json.dumps({"query": "Capitec Bank", "max_results": 3}))
if "unreachable or empty" in out:
    print(f"  skip web_search (offline/blocked): {out[:70]}")
else:
    try:
        data = json.loads(out)
        check("web_search returns results", len(data["results"]) >= 1 and
              data.get("engine") in ("duckduckgo", "wikipedia") and
              all(r["url"].startswith("http") for r in data["results"]), out[:120])
    except ValueError:
        check("web_search json", False, out[:120])
print(f"  (web_search took {time.time()-t0:.1f}s)")

# ---------------------------------------------------------------- new skills
out = json.loads(skills.run("finance_calculator", json.dumps(
    {"action": "loan_payment", "amount": 1000000, "annual_rate_percent": 11.75, "years": 20})))
check("finance loan payment", 10800 < out["monthly_payment"] < 10900 and
      out["total_interest"] > 1500000, out)
out = json.loads(skills.run("finance_calculator", json.dumps(
    {"action": "compound", "amount": 10000, "annual_rate_percent": 8, "years": 10})))
check("finance compound", 22000 < out["future_value"] < 22300, out)
out = json.loads(skills.run("finance_calculator", json.dumps(
    {"action": "simple_interest", "amount": 1000, "annual_rate_percent": 10, "years": 5})))
check("finance simple", out["interest"] == 500 and out["total"] == 1500, out)
out = skills.run("finance_calculator", json.dumps({"action": "launch", "amount": 1, "years": 1}))
check("finance unknown action", "Unknown action" in out, out)

out = skills.run("json_tool", json.dumps({"action": "validate", "text": "{\"a\": 1}"}))
check("json valid", out.startswith("Valid JSON"), out)
out = skills.run("json_tool", json.dumps({"action": "validate", "text": "{oops}"}))
check("json invalid", "Invalid JSON" in out, out)
out = skills.run("json_tool", json.dumps({"action": "format", "text": "{\"a\":[1,2]}"}))
check("json format", "\n" in out and "\"a\"" in out, out)
out = skills.run("json_tool", json.dumps({"action": "minify", "text": "{ \"a\": [1, 2] }"}))
check("json minify", out == '{"a":[1,2]}', out)

out = json.loads(skills.run("regex_tester", json.dumps(
    {"pattern": r"(\w+)@(\w+\.\w+)", "text": "mail ruwayne@example.com now"})))
check("regex match+groups", out["total_matches_shown"] == 1 and
      out["matches"][0]["groups"] == ["ruwayne", "example.com"], out)
out = skills.run("regex_tester", json.dumps({"pattern": "([unclosed", "text": "x"}))
check("regex invalid pattern", "Invalid regex" in out, out)

out = skills.run("timezone_convert", json.dumps(
    {"time_str": "2026-10-16 12:00", "from_tz": "Africa/Johannesburg", "to_tz": "UTC"}))
check("tz convert", "10:00" in out and "UTC" in out, out)
out = skills.run("timezone_convert", json.dumps({"time_str": "not a time", "from_tz": "UTC", "to_tz": "UTC"}))
check("tz bad input", "Could not read" in out, out)
out = skills.run("timezone_convert", json.dumps({"from_tz": "Mars/Nowhere", "to_tz": "UTC"}))
check("tz bad zone", "Unknown timezone" in out, out)

out = json.loads(skills.run("url_tool", json.dumps(
    {"action": "parse", "text": "https://x.co.za/a/b?q=1&r=2#top"})))
check("url parse", out["host"] == "x.co.za" and out["query_params"] == {"q": ["1"], "r": ["2"]}
      and out["fragment"] == "top", out)
out = skills.run("url_tool", json.dumps({"action": "encode", "text": "a b&c"}))
check("url encode", out == "a%20b%26c", out)
out = skills.run("url_tool", json.dumps({"action": "decode", "text": "a%20b%26c"}))
check("url decode", out == "a b&c", out)

out = json.loads(skills.run("password_strength", json.dumps({"password": "password"})))
check("pw weak", out["score"] in ("0/4", "1/4") and out["problems"], out)
out = json.loads(skills.run("password_strength", json.dumps({"password": "Tr0ub4dor&3xk9#mQ"})))
check("pw strong", out["score"] in ("3/4", "4/4") and out["verdict"] in ("strong", "very strong"), out)

out = skills.run("qr_code", json.dumps({"text": "https://my-ai-pro-rkxe.onrender.com"}))
check("qr markdown image", out.startswith("![QR code](https://api.qrserver.com/") and
      "my-ai-pro-rkxe" in out, out[:80])
out = skills.run("qr_code", json.dumps({"text": "  "}))
check("qr empty refused", "No text" in out, out)

check("registry now 17", len(skills.SKILLS) == 17 and len(skills.tool_defs()) == 17,
      str(len(skills.SKILLS)))

# network skills: lenient (sandbox may block some endpoints)
for name, args, needles in [
    ("weather", {"location": "Cape Town", "days": 2}, ["temp_c", "forecast"]),
    ("exchange_rates", {"amount": 100, "from_currency": "ZAR", "to_currency": "USD"}, ["="]),
    ("dictionary", {"word": "bank"}, ["meaning"]),
    ("wikipedia_summary", {"topic": "Capitec Bank"}, ["summary"]),
]:
    out = skills.run(name, json.dumps(args))
    if "failed" in out[:60].lower() or "No definition found" in out:
        print(f"  skip {name} (network): {out[:60]}")
    else:
        check(f"{name} live", all(n in out for n in needles), out[:150])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
