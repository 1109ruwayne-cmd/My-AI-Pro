"""Agent Skills - built-in tools the AI can use automatically while answering.

A skill is a small, safe helper the model may call mid-conversation, exactly
like it calls search_files: it gets the tool definitions, decides when a skill
helps, and the answer of the skill goes back into the conversation.

Skills shipped with this module:
    calculator        safe arithmetic (no code execution)
    current_datetime  today's date / current time in any timezone
    unit_convert      length, mass, volume, area, data, speed, time, temperature
    text_tools        counts, case, reverse, hashes, base64, slug
    random_generator  numbers, dice, coin, uuid, passwords
    web_search        live results from Brave (free key, optional) or
                      DuckDuckGo (no API key needed), Wikipedia fallback
    live_pulse        Grok-style real-time awareness, free: Google News RSS
                      headlines, public Reddit pulse, Google Trends daily
                      (no keys; X/Twitter itself stays paywalled)
    trust_desk        SA Trust Desk - credit rights (NCA s72), dispute/paid-up/
                      POPIA-consent letters, VAT format check, NCR lender & CIPC
                      company register guides, prof_register (verify project
                      managers SACPCMP, nurses SANC/AHPRA-NMBA, SARS tax
                      practitioners - free official public registers)
    hr_file           OWNER-ONLY Employee Trust Files - employees with SARS tax
                      numbers (10-digit format + modulus-10 check, PAYE/VAT
                      discrimination), certificates with verification status &
                      expiry flags, POPIA consent tracking (hrdesk.py -> hr.db).
                      Hidden from visitors: tool_defs(owner=False) omits it and
                      run() refuses non-owner calls.
    weather           forecasts via Open-Meteo (no key)
    exchange_rates    live currency rates
    dictionary        definitions via dictionaryapi.dev
    wikipedia_summary page summaries via the Wikipedia API
    qr_code           QR codes as SVG data URIs
    finance_calculator loans, compound interest, investments
    json_tool         validate / format / minify JSON
    regex_tester      test regular expressions with matches explained
    timezone_convert  convert times between timezones
    url_tool          parse, join and encode URLs
    password_strength audit password strength locally (nothing is transmitted)

Owner can switch the whole module off in Settings (config "skills_enabled").
Owner-only skills (hr_file) are only offered when the request proved the owner
password - see app.py chat() -> stream_answer(owner=...) -> _answer_with_tools.
"""
import ast
import base64
import datetime as _dt
import hashlib
import json
import math
import operator
import os
import re
import secrets
import string
import xml.etree.ElementTree as ET
import zoneinfo

import httpx

import hrdesk

VERSION = 1


def enabled(cfg: dict) -> bool:
    return cfg.get("skills_enabled", True) is not False


# ------------------------------------------------------------------ calculator
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "floor": math.floor,
          "ceil": math.ceil, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
          "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp,
          "min": min, "max": max, "factorial": math.factorial}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _ev(node):
    """Evaluate a parsed arithmetic expression - numbers and known functions only."""
    if isinstance(node, ast.Expression):
        return _ev(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        a, b = _ev(node.left), _ev(node.right)
        if isinstance(node.op, ast.Pow) and (abs(b) > 64 or abs(a) > 1e6):
            raise ValueError("numbers too big")
        if isinstance(node.op, ast.Mod) and b == 0:
            raise ValueError("modulo by zero")
        return _BINOPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_ev(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_ev(a) for a in node.args])
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    raise ValueError("unsupported expression")


def calculator(expression: str = "", **_) -> str:
    expression = str(expression).strip()
    if not expression:
        return "No expression given. Example: (47*13+8)/2 or sqrt(2)*pi."
    try:
        value = _ev(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return "Division by zero."
    except Exception:
        return ("Could not calculate that. Use numbers, + - * / // % ** (), and the functions "
                "sqrt, abs, round, floor, ceil, sin, cos, tan, log, log10, log2, exp, factorial, "
                "min, max and constants pi, e.")
    if isinstance(value, float):
        value = round(value, 12)
        if math.isfinite(value) and value == int(value) and abs(value) < 1e15:
            value = int(value)
    return f"{expression} = {value}"


# -------------------------------------------------------------------- datetime
def current_datetime(timezone: str = "", **_) -> str:
    zone = str(timezone or "Africa/Johannesburg").strip()
    try:
        tz = zoneinfo.ZoneInfo(zone)
    except Exception:
        tz, zone = zoneinfo.ZoneInfo("UTC"), "UTC (timezone not recognised)"
    now = _dt.datetime.now(tz)
    return json.dumps({
        "timezone": zone,
        "date": now.strftime("%A, %d %B %Y"),
        "time": now.strftime("%H:%M:%S"),
        "iso": now.isoformat(timespec="seconds"),
        "unix": int(now.timestamp()),
        "utc_offset": now.strftime("%z"),
    })


# ---------------------------------------------------------------- unit_convert
_UNITS = {
    "length": {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0, "in": 0.0254,
               "ft": 0.3048, "yd": 0.9144, "mi": 1609.344, "nmi": 1852.0},
    "mass": {"mg": 1e-6, "g": 1e-3, "kg": 1.0, "t": 1000.0, "oz": 0.0283495231,
             "lb": 0.45359237},
    "volume": {"ml": 0.001, "l": 1.0, "tsp": 0.00492892, "tbsp": 0.0147868,
               "cup": 0.236588, "pt": 0.473176, "qt": 0.946353, "gal": 3.78541},
    "area": {"m2": 1.0, "km2": 1e6, "ha": 1e4, "acre": 4046.85642, "ft2": 0.09290304},
    "data": {"b": 1.0, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
             "kib": 1024.0, "mib": 1024.0 ** 2, "gib": 1024.0 ** 3, "tib": 1024.0 ** 4},
    "speed": {"kmh": 1.0, "mph": 1.609344, "ms": 3.6, "knot": 1.852, "fts": 1.09728},
    "time": {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0, "day": 86400.0,
             "week": 604800.0, "year": 31557600.0},
}
_TEMP = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}
_ALIAS = {"meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km",
          "kilometers": "km", "kilometre": "km", "kilometres": "km", "centimeter": "cm",
          "centimeters": "cm", "millimeter": "mm", "millimeters": "mm", "inch": "in",
          "inches": "in", "foot": "ft", "feet": "ft", "yard": "yd", "yards": "yd",
          "mile": "mi", "miles": "mi", "gram": "g", "grams": "g", "kilogram": "kg",
          "kilograms": "kg", "pound": "lb", "pounds": "lb", "ounce": "oz", "ounces": "oz",
          "tonne": "t", "tonnes": "t", "liter": "l", "liters": "l", "litre": "l",
          "litres": "l", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml",
          "gallon": "gal", "gallons": "gal", "cup": "cup", "cups": "cup",
          "second": "s", "seconds": "s", "minute": "min", "minutes": "min",
          "hour": "h", "hours": "h", "day": "day", "days": "day", "week": "week",
          "weeks": "week", "byte": "b", "bytes": "b", "celsius": "c", "fahrenheit": "f",
          "kelvin": "k", "km/h": "kmh", "m/s": "ms", "mph": "mph", "knots": "knot",
          "hectare": "ha", "hectares": "ha", "acre": "acre", "acres": "acre"}


def _norm(unit: str) -> str:
    u = str(unit or "").strip().lower().replace(" ", "").replace("°", "")
    return _ALIAS.get(u, u)


def unit_convert(value: float = 0, from_unit: str = "", to_unit: str = "", **_) -> str:
    f, t = _norm(from_unit), _norm(to_unit)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "value must be a number."
    if f in _TEMP and t in _TEMP:                      # temperature: offsets, not factors
        kelvin = {"c": value + 273.15, "f": (value - 32) * 5 / 9 + 273.15, "k": value}[f]
        out = {"c": kelvin - 273.15, "f": (kelvin - 273.15) * 9 / 5 + 32, "k": kelvin}[t]
        return f"{value} {f.upper()} = {round(out, 6)} {t.upper()}"
    for family, table in _UNITS.items():
        if f in table and t in table:
            out = value * table[f] / table[t]
            out = round(out, 10)
            if out == int(out) and abs(out) < 1e15:
                out = int(out)
            return f"{value} {f} = {out} {t} ({family})"
    known = sorted({u for table in _UNITS.values() for u in table} | _TEMP)
    return (f"Unknown unit '{from_unit}' or '{to_unit}'. Known units: "
            f"{', '.join(known)}. Temperatures: c, f, k.")


# ------------------------------------------------------------------ text_tools
def text_tools(action: str = "", text: str = "", **_) -> str:
    action, text = str(action).strip().lower(), str(text)
    if action in ("count", "stats", ""):
        words = len(text.split())
        return json.dumps({"characters": len(text), "characters_no_spaces": len(re.sub(r"\s", "", text)),
                           "words": words, "lines": text.count("\n") + (1 if text else 0),
                           "sentences": len(re.findall(r"[.!?]+(?:\s|$)", text))})
    if action == "upper":
        return text.upper()
    if action == "lower":
        return text.lower()
    if action == "title":
        return text.title()
    if action == "reverse":
        return text[::-1]
    if action == "sha256":
        return hashlib.sha256(text.encode()).hexdigest()
    if action == "md5":
        return hashlib.md5(text.encode()).hexdigest()
    if action == "base64_encode":
        return base64.b64encode(text.encode()).decode()
    if action == "base64_decode":
        try:
            return base64.b64decode(text.strip(), validate=False).decode("utf-8", "replace")
        except Exception:
            return "That is not valid base64."
    if action == "slug":
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug or "(empty slug)"
    return ("Unknown action. Use: count, upper, lower, title, reverse, sha256, md5, "
            "base64_encode, base64_decode, slug.")


# -------------------------------------------------------------- random_generator
def random_generator(action: str = "number", minimum: float = 1, maximum: float = 100,
                     sides: int = 6, count: int = 1, length: int = 16, **_) -> str:
    action = str(action).strip().lower()
    try:
        if action in ("number", ""):
            lo, hi = float(minimum), float(maximum)
            if lo > hi:
                lo, hi = hi, lo
            nums = [round(secrets.randbelow(10 ** 6) / 10 ** 6 * (hi - lo) + lo, 6)
                    for _ in range(max(1, min(int(count), 20)))]
            return ", ".join(str(int(n) if n == int(n) else n) for n in nums)
        if action == "dice":
            sides = max(2, min(int(sides), 1000))
            rolls = [secrets.randbelow(sides) + 1 for _ in range(max(1, min(int(count), 20)))]
            return f"{len(rolls)}d{sides}: {rolls} (total {sum(rolls)})"
        if action == "coin":
            return secrets.choice(["heads", "tails"])
        if action == "uuid":
            import uuid
            return str(uuid.uuid4())
        if action == "password":
            length = max(6, min(int(length), 128))
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
            pw = "".join(secrets.choice(alphabet) for _ in range(length))
            return f"{pw}  ({length} characters, cryptographically secure)"
    except (TypeError, ValueError):
        return "Check the numbers you passed (minimum, maximum, sides, count, length)."
    return "Unknown action. Use: number, dice, coin, uuid, password."


# ------------------------------------------------------------------ web_search
_DDG = "https://html.duckduckgo.com/html/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept-Language": "en-US,en;q=0.9"}


def _clean(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_text)
    return (text.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'")
            .replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").strip())


def _real_url(href: str) -> str:
    if "uddg=" in href:                       # DuckDuckGo redirect wrapper
        from urllib.parse import unquote, urlparse, parse_qs
        q = parse_qs(urlparse(href).query).get("uddg")
        if q:
            return unquote(q[0])
    return href


def _ddg(query: str, max_results: int) -> list:
    """DuckDuckGo HTML results - best when they are served, but cloud IPs get challenged."""
    r = httpx.post(_DDG, data={"q": query}, headers=_HEADERS, timeout=15, follow_redirects=True)
    if r.status_code != 200 or "result__a" not in r.text:
        return []                              # blocked / challenged / no hits
    results = []
    for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
        url, title = _real_url(m.group(1)), _clean(m.group(2))
        snippet = ""
        sm = re.search(re.escape(m.group(0)) + r'.{0,2000}?class="result__snippet"[^>]*>(.*?)</a>',
                       r.text, re.S)
        if sm:
            snippet = _clean(sm.group(1))[:300]
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _wikipedia(query: str, max_results: int) -> list:
    """Wikipedia search API - always available, no key, good for facts and current topics."""
    r = httpx.get("https://en.wikipedia.org/w/api.php",
                  params={"action": "query", "list": "search", "srsearch": query,
                          "srlimit": max_results, "format": "json", "utf8": 1},
                  headers=_HEADERS, timeout=15)
    hits = (r.json().get("query") or {}).get("search") or []
    return [{"title": h["title"],
             "url": f"https://en.wikipedia.org/?curid={h['pageid']}",
             "snippet": _clean(h.get("snippet", ""))[:300]}
            for h in hits]


def _brave(query: str, max_results: int) -> list:
    """Brave Search API - independent web index, free tier 2,000 queries/month.
    Active only when the server env carries BRAVE_API_KEY; otherwise returns []."""
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        return []
    r = httpx.get("https://api.search.brave.com/res/v1/web/search",
                  params={"q": query, "count": max_results},
                  headers={"X-Subscription-Token": key, "Accept": "application/json"},
                  timeout=15)
    r.raise_for_status()
    out = []
    for item in ((r.json().get("web") or {}).get("results") or [])[:max_results]:
        if item.get("title") and item.get("url"):
            out.append({"title": item["title"], "url": item["url"],
                        "snippet": (item.get("description") or "").strip()})
    return out


def web_search(query: str = "", max_results: int = 5, **_) -> str:
    """Live search: Brave (when the owner set a free API key), else DuckDuckGo, with
    Wikipedia as the always-on fallback. No paid calls ever."""
    query = str(query).strip()
    if not query:
        return "No search query given."
    max_results = max(1, min(int(max_results or 5), 10))
    engines = ([("brave", _brave)] if os.environ.get("BRAVE_API_KEY", "").strip() else [])
    engines += [("duckduckgo", _ddg), ("wikipedia", _wikipedia)]
    for engine, fn in engines:
        try:
            results = fn(query, max_results)
        except Exception:
            results = []
        if results:
            return json.dumps({"query": query, "engine": engine, "results": results},
                              ensure_ascii=False)
    return (f"No web results found for '{query}' (search engines unreachable or empty). "
            "Answer from your own knowledge and say it may not be current.")


# ------------------------------------------------------------------ live pulse
_GNEWS_UA = {"User-Agent": "Mozilla/5.0 (compatible; MyAIPro/1.0; +https://my-ai-pro-rkxe.onrender.com)"}


def _google_news(query: str, geo: str = "ZA", max_items: int = 8) -> list:
    """Live headlines via the public Google News RSS - free, no key."""
    params = {"q": query, "hl": f"en-{geo}", "gl": geo, "ceid": f"{geo}:en"}
    r = httpx.get("https://news.google.com/rss/search", params=params,
                  headers=_GNEWS_UA, timeout=15, follow_redirects=True)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        out.append({"title": title,
                    "publisher": (it.findtext("source") or "").strip(),
                    "published": (it.findtext("pubDate") or "").strip(),
                    "url": (it.findtext("link") or "").strip()})
        if len(out) >= max_items:
            break
    return out


def _reddit_pulse(query: str, max_items: int = 8) -> list:
    """Live social pulse via Reddit's public JSON search - free, no key, polite UA."""
    r = httpx.get("https://www.reddit.com/search.json",
                  params={"q": query, "limit": max_items, "sort": "relevance"},
                  headers={"User-Agent": "MyAIPro/1.0 (owner contact 1109ruwayne@gmail.com)"},
                  timeout=15, follow_redirects=True)
    r.raise_for_status()
    out = []
    for ch in (r.json().get("data", {}).get("children") or []):
        p = ch.get("data", {})
        if not p.get("title"):
            continue
        out.append({"title": p.get("title"), "subreddit": "r/" + str(p.get("subreddit", "")),
                    "score": p.get("score", 0), "comments": p.get("num_comments", 0),
                    "url": "https://www.reddit.com" + str(p.get("permalink", ""))})
    return out


def _google_trends(geo: str = "ZA") -> list:
    """What a country is searching right now - Google Trends, free but unofficial.
    Tries three public endpoints in order; datacenter IPs are sometimes blocked, so
    the caller degrades gracefully."""
    last = None
    # 1) dailytrends JSON (with the )]}' guard)
    try:
        r = httpx.get("https://trends.google.com/trends/api/dailytrends",
                      params={"hl": "en", "tz": "-120", "geo": geo},
                      headers=_GNEWS_UA, timeout=15, follow_redirects=True)
        r.raise_for_status()
        payload = json.loads(r.text.split("\n", 1)[-1])
        out = [{"topic": (s.get("title") or {}).get("query", ""), "traffic": s.get("traffic", "")}
               for s in (payload.get("default", {}).get("trendingSearches") or [])[:10]]
        if out:
            return out
    except Exception as exc:
        last = exc
    # 2) trending/json (newer surface)
    try:
        r = httpx.get("https://trends.google.com/trending/json",
                      params={"geo": geo, "hours": 24},
                      headers=_GNEWS_UA, timeout=15, follow_redirects=True)
        r.raise_for_status()
        trends = (r.json().get("trendingNow") or {}).get("trends") or []
        out = [{"topic": t.get("query", ""), "traffic": str(t.get("searchVolume", ""))}
               for t in trends[:10] if t.get("query")]
        if out:
            return out
    except Exception as exc:
        last = exc
    # 3) daily RSS (oldest surface)
    try:
        r = httpx.get("https://trends.google.com/trendingsearches/daily/rss",
                      params={"geo": geo}, headers=_GNEWS_UA, timeout=15, follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = [{"topic": (it.findtext("title") or "").strip(), "traffic": ""}
               for it in root.iter("item") if (it.findtext("title") or "").strip()][:10]
        if out:
            return out
    except Exception as exc:
        last = exc
    if last:
        raise last
    return []


def live_pulse(source: str = "", query: str = "", geo: str = "ZA",
               max_items: int = 8, **_) -> str:
    """Grok-style live awareness without the paywall: real-time news, social pulse and
    trending searches from free public endpoints. No API keys, nothing scraped behind a
    login. X/Twitter itself is NOT reachable for free - use web_search for general pages."""
    s = (source or "").strip().lower().replace(" ", "_")
    geo = (geo or "ZA").strip().upper()[:2] or "ZA"
    max_items = max(1, min(int(max_items or 8), 15))
    if s in ("news", "headlines", "google_news"):
        if not (query or "").strip():
            return "live_pulse news needs a query, e.g. 'South Africa electricity'."
        try:
            items = _google_news(query, geo, max_items)
        except Exception as exc:
            return f"Google News unreachable ({type(exc).__name__}). Try web_search instead."
        if not items:
            return f"No live headlines found for '{query}' (geo {geo})."
        return json.dumps({"source": "google_news", "query": query, "geo": geo,
                           "results": items}, ensure_ascii=False)
    if s in ("reddit", "social"):
        if not (query or "").strip():
            return "live_pulse reddit needs a query topic."
        try:
            items = _reddit_pulse(query, max_items)
        except Exception as exc:
            return (f"Reddit unreachable ({type(exc).__name__}) - it rate-limits shared "
                    "server IPs sometimes. Retry later or use web_search.")
        if not items:
            return f"No Reddit posts found for '{query}'."
        return json.dumps({"source": "reddit_public", "query": query,
                           "results": items}, ensure_ascii=False)
    if s in ("trends", "trending"):
        try:
            items = _google_trends(geo)
        except Exception as exc:
            return (f"Google Trends unreachable ({type(exc).__name__}) - unofficial "
                    "endpoint, may be rate-limited. Try again later.")
        if not items:
            return f"No trending data returned for {geo}."
        return json.dumps({"source": "google_trends_daily", "geo": geo,
                           "trending": items}, ensure_ascii=False)
    return ("live_pulse sources: news (live headlines for a query+country), reddit "
            "(live social pulse for a topic), trends (daily trending searches for a "
            "country, default ZA). All free, no keys. X/Twitter data is paywalled "
            "industry-wide; for general web pages use web_search.")


# --------------------------------------------------------------------- registry
# ------------------------------------------------------------------ trust desk
_SA_VAT_RE = re.compile(r"^4\d{9}$")
_TODAY = lambda: _dt.date.today().strftime("%d %B %Y")


def trust_desk(action: str = "", bureau: str = "", creditor: str = "", account: str = "",
               entry: str = "", grounds: str = "", name: str = "", id_number: str = "",
               address: str = "", contact: str = "", company: str = "",
               company_reg: str = "", purpose: str = "", vat_number: str = "",
               body: str = "") -> str:
    """South African credit & trust helpers - guidance, letters, format checks.
    Lawful and defensive only: no bureau pulls, no register scraping; official
    channels and drafted documents the user sends themselves."""
    a = (action or "").strip().lower()
    if a == "credit_rights":
        return ("SA credit rights summary (National Credit Act 34 of 2005):\n"
                "- ONE FREE credit report every 12 months from EACH bureau "
                "(TransUnion, Experian, Compuscan, XDS) - s72; own checks are soft "
                "enquiries and never lower the score.\n"
                "- Adverse listings/enquiries drop off after 1 year; judgments after "
                "5 years or once paid/rescinded; paid-up write-offs removed under s71A; "
                "prescribed debt (±3y, unacknowledged) may not be listed or collected.\n"
                "- Disputes (s72(3)) are FREE: bureau must investigate in 20 business "
                "days (Reg 17(4)), mask the item while checking (NCR guideline Dec 2025) "
                "and remove what the source cannot verify.\n"
                "- Escalation: National Financial Ombud 0861 662 837 / "
                "ombud@creditombud.org.za, then NCR 0860 627 627 / complaints@ncr.org.za.\n"
                "- Lenders must be NCR-registered (NCRCP number on ncr.org.za).")
    if a == "dispute_letter":
        if not (bureau and name):
            return "dispute_letter needs at least: bureau, name (plus id_number, " \
                   "creditor, entry, grounds, contact for a complete letter)."
        return (f"{_TODAY()}\n\nTo: {bureau} - Disputes Desk\n"
                f"RE: DISPUTE OF INCORRECT INFORMATION - SECTION 72(3), NATIONAL CREDIT ACT 34 OF 2005\n\n"
                f"I, {name} (ID number {id_number or '[ID number]'}), of {address or '[address]'}, "
                f"contactable at {contact or '[contact]'}, dispute the following entry on my "
                f"credit record:\n"
                f"- Credit provider: {creditor or '[creditor]'}\n"
                f"- Account number: {account or '[account number]'}\n"
                f"- Entry disputed: {entry or '[describe the listing]'}\n"
                f"- Grounds: {grounds or '[e.g. settled / paid up / prescribed / not my account]'}\n"
                f"Supporting proof is attached: [paid-up letter / settlement agreement / "
                f"rescission order / statements].\n\n"
                "In terms of s72(3) and Regulation 17(4) you are required to investigate within "
                "20 business days; pending the outcome the disputed item must be masked in line "
                "with the NCR credible-evidence guideline (December 2025). Should the source be "
                "unable to verify the information, it must be removed and I request written "
                "confirmation of the outcome.\n"
                "Should the dispute not be resolved, I will escalate to the National Financial "
                "Ombud and the National Credit Regulator (Form 29).\n\n"
                f"Yours faithfully,\n{name}")
    if a == "paid_up_letter":
        if not (creditor and name):
            return "paid_up_letter needs at least: creditor, name (plus account, id_number, contact)."
        return (f"{_TODAY()}\n\nTo: {creditor} - Accounts Department\n"
                f"RE: REQUEST FOR PAID-UP LETTER / CONFIRMATION OF SETTLEMENT\n\n"
                f"I, {name} (ID number {id_number or '[ID number]'}, contact {contact or '[contact]'}), "
                f"request written confirmation that account {account or '[account number]'} has been "
                "settled in full, stating the settlement date and a zero balance, for use in a "
                "credit-bureau dispute under s72(3) of the National Credit Act and, where "
                "applicable, removal of the listing under s71A.\n"
                "Kindly provide the letter within 10 business days.\n\n"
                f"Yours faithfully,\n{name}")
    if a == "consent_form":
        if not (name and company):
            return "consent_form needs at least: name, company (plus id_number, purpose, company_reg)."
        return ("POPIA CONSENT - CREDIT / RECORDS CHECK\n\n"
                f"I, {name} (ID number {id_number or '[ID number]'}), hereby consent in terms of "
                f"section 11 of the Protection of Personal Information Act 4 of 2013 that "
                f"{company} (registration {company_reg or '[registration number]'}) may obtain and "
                f"process my credit record and related personal information from registered credit "
                f"bureaus and public registers, solely for the purpose of: "
                f"{purpose or '[state the specific lawful purpose]'}.\n"
                "The processing is limited to the minimum information necessary; the information "
                "will not be used for any other purpose nor shared further without my separate "
                "consent, save as required by law. I may withdraw this consent in writing at any "
                "time, and I may request the record of what was processed.\n"
                f"Signed at ____________ on {_TODAY()}.\n\n"
                f"_______________________\n{name} (data subject)\n\n"
                "Accepted for the responsible party:\n_______________________\n"
                f"{company} - representative")
    if a == "ncr_lender":
        return ("How to verify a lender is legal (National Credit Regulator):\n"
                f"- Lender named: {company or '[lender name]'} "
                f"(registration claimed: {company_reg or '[NCRCP number]'}).\n"
                "- Every lawful credit provider carries an NCRCP registration number on adverts "
                "and contracts; verify it on the NCR register at ncr.org.za (Registers).\n"
                "- Red flags: no NCRCP number; cash 'initiation fees' upfront; interest/fees above "
                "NCA caps; no written contract; holding ID books, bank cards or SASSA cards.\n"
                "- Unregistered lending is a criminal matter: NCR 0860 627 627 / "
                "complaints@ncr.org.za; loan-shark conduct also to SAPS.\n"
                "- My AI Pro performs no bureau pull here - register checks are public and free.")
    if a == "cipc_company":
        return ("How to verify a company (CIPC):\n"
                f"- Company named: {company or '[company name]'} "
                f"(registration claimed: {company_reg or '[registration number]'}).\n"
                "- Search the public register at eservices.cipc.co.za (or BizPortal): status must "
                "read Active; note directors and registration date.\n"
                "- Ask the counterparty for a current registration certificate (COR) and match "
                "number, name and directors; invoices should show the same registration number.\n"
                "- Red flags: 'In deregistration' status; number/name mismatch; refused certificate.\n"
                "- Company status is public register data - no consent needed to look.")
    if a == "sars_vat":
        v = re.sub(r"\s", "", vat_number or "")
        ok = bool(_SA_VAT_RE.match(v))
        line = (f"- VAT number supplied: {v or '[none]'} -> format "
                + ("VALID pattern (10 digits starting with 4)." if ok
                   else "INVALID - a genuine SA VAT registration number is 10 digits starting "
                        "with 4. Treat invoices claiming VAT with suspicion.")) if v else \
               "- Supply vat_number to validate the format (10 digits, starts with 4)."
        return ("SARS VAT vendor check:\n" + line + "\n"
                "- Format is only the first gate: final confirmation via SARS (eFiling VAT vendor "
                "search or a VAT registration confirmation letter from the vendor).\n"
                "- A vendor must show name, address, VAT number and tax period on tax invoices; "
                "claiming input VAT on a fake number is a SARS risk for the buyer.")
    if a == "prof_register":
        b = (body or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        if b in ("sacpcmp", "pm", "projectmanager", "projectmanagement", "construction"):
            return ("SACPCMP - SA Council for the Project & Construction Management Professions "
                    "(statutory, Act 48 of 2000):\n"
                    "- FREE public check: sacpcmp.org.za -> 'Registered Person Search' -> "
                    "'Project & Construction Management' (search.mymembership.co.za). Search the "
                    "person's name; a live hit = currently registered and in good standing.\n"
                    "- Categories: Pr.CM / Pr.CPM (professional), Candidate CM / Candidate CPM, "
                    "Professional Construction Mentor. Pr.CPM is a SAQA-recognised designation "
                    "(cross-check at pbdesig.saqa.org.za, designation 498).\n"
                    "- Genuine certificates carry a QR code linking to SACPCMP live validation, "
                    "and validity runs April-March (their financial year). RED FLAG: an end date "
                    "in any month other than March means the certificate is fake.\n"
                    "- Since 1 Aug 2025: Pr.CPM/Pr.CM need NQF 8 (480 credits, SAQA-accredited; "
                    "limited dispensation accepts NQF 7), 4-10 years logged experience, annual CPD "
                    "and fees; qualifications are verified through MIE.\n"
                    "- To REGISTER: mypcm.sacpcmp.org.za portal - certified ID, certified "
                    "qualifications, detailed CV, Annexure A1 (project profile) + A2 (project "
                    "report); annual registration fee, certificate renews each April.\n"
                    "- PMSA (pmsa.org.za) is a voluntary professional body - membership there is "
                    "NOT statutory registration. Foreign PM certs (PMP/PRINCE2) verify via PMI "
                    "(pmi.org Credly badge) or PeopleCert (peoplecert.org verification).")
        if b in ("sanc", "nurse", "nursing", "midwife"):
            return ("SANC - South African Nursing Council (statutory, Nursing Act 33 of 2005):\n"
                    "- FREE public check: sanc.co.za/eRegister.aspx - accept the conditions, "
                    "search by SANC reference number or SA ID number. The eRegister is a legal "
                    "copy of the official register (s35) and is the authoritative check.\n"
                    "- No hit on the eRegister = not registered -> may NOT be employed as a nurse "
                    "(SANC directive; employers must refuse).\n"
                    "- From July 2025 annual practising certificates (APCs) are emailed as "
                    "encrypted PDFs with a QR code; employers MUST verify any APC against the "
                    "eRegister before accepting it.\n"
                    "- 2026 annual fees (gazetted): R870 registered nurse/midwife, R520 enrolled "
                    "nurse/midwife, R370 enrolled nursing auxiliary - normally paid by the "
                    "employer (Resolution 3 of 2019). Restoration of lapsed registration costs "
                    "the fee plus all arrears.\n"
                    "- Need an official written verification/extract? SANC offers it for a fee "
                    "(VERIFEE / EXRFEE codes on sanc.co.za fee list) - the free eRegister check "
                    "is enough for most employment purposes.")
        if b in ("ahpra", "nmba", "australia", "nurseau"):
            return ("AHPRA / NMBA - Australia's national health practitioner register:\n"
                    "- FREE public check: ahpra.gov.au -> 'Look up a practitioner' (Registers of "
                    "Practitioners). Covers nursing & midwifery (NMBA) plus 15 other professions "
                    "(medical, pharmacy, psychology, paramedicine...). Search by name or AHPRA "
                    "registration number.\n"
                    "- Read the WHOLE record: registration status, expiry (nurses/midwives renew "
                    "by 31 May each year), registration type, and any conditions, undertakings "
                    "or endorsements. Not on the register = not registered to practise in "
                    "Australia - no exceptions, and old-style numbers don't work.\n"
                    "- Don't trust a printed entry or PDF certificate: the online register is "
                    "the only current source (AHPRA says so explicitly). Queries: 1300 419 495.\n"
                    "- Internationally qualified nurses (e.g. South Africans moving over) go "
                    "through the IQNM self-check + qualification assessment before applying via "
                    "the AHPRA practitioner portal; a certificate of good standing from the home "
                    "council (SANC for SA) is required.")
        if b in ("sars", "sarstp", "tax", "taxpractitioner"):
            return ("SARS tax practitioner check (Tax Administration Act s240/240A):\n"
                    "- FREE public check: SARS eFiling Tax Practitioner Query - "
                    "https://secure.sarsefiling.co.za/TaxPractitionerQuery.aspx. Ask the person "
                    "for their PR number (always starts with 'PR') and confirm it shows "
                    "registered/active.\n"
                    "- A legal tax practitioner is registered with BOTH a Recognised Controlling "
                    "Body (RCB - e.g. SAIT, SAICA, ACCA, CIMA; official list on sars.gov.za) AND "
                    "SARS. Registration must happen within 21 business days of first giving tax "
                    "advice or completing returns for others.\n"
                    "- Double-check membership on the claimed RCB's own site (e.g. SAIT member "
                    "search) - the two registers must agree.\n"
                    "- RED FLAGS: no PR number, refuses to name an RCB, offers to 'fix' a refund "
                    "for an upfront cash fee, uses an unbranded gmail/hotmail address for "
                    "practice correspondence, or asks you to sign a blank RAV01/ITR12.\n"
                    "- Charged for tax help by an unregistered person? Report to SARS: "
                    "Reportingunprofessionalconduct@sars.gov.za (unregistered practice is an "
                    "offence; SARS issued fresh scam warnings in July 2026).\n"
                    "- To REGISTER as a practitioner: join an RCB first (RCB initiates on "
                    "eFiling), complete the RAV01, select the RCB and submit; SARS validates and "
                    "issues the PR number via eFiling correspondence.")
        return ("prof_register checks professional registrations via free official public "
                "registers. Set body to one of:\n"
                "- sacpcmp: project/construction managers (SA statutory council)\n"
                "- sanc: nurses & midwives (SA)\n"
                "- ahpra: nurses & all health practitioners (Australia, NMBA)\n"
                "- sars: tax practitioners (SA, PR number)\n"
                "Other SA statutory bodies all keep free public registers on their official "
                "sites: ECSA (engineers), SAICA (accountants/auditors), HPCSA (health "
                "professions, iRegister), SACE (educators), PPRA (property practitioners), "
                "FSCA (financial service providers / FSPs), LPC (attorneys), CIDB (construction "
                "contractors), SAQA designations (pbdesig.saqa.org.za). Rule: verify on the "
                "register itself - certificates, screenshots and CV claims are not proof.")
    return ("trust_desk actions: credit_rights, dispute_letter, paid_up_letter, consent_form, "
            "ncr_lender, cipc_company, sars_vat, prof_register.")


# ------------------------------------------------------------- employee files
def hr_file(action: str = "", employee: str = "", name: str = "", id_number: str = "",
            position: str = "", tax_number: str = "", consent: str = "", notes: str = "",
            credential: str = "", body: str = "", number: str = "", issued: str = "",
            expires: str = "", status: str = "", note: str = "") -> str:
    """Owner-only employee trust files (server-side, hr.db). Nothing is pulled from SARS
    or institutions: tax numbers are format-checked and every certificate comes back with
    the free official channel to verify it by hand, with the employee's POPIA consent."""
    a = (action or "").strip().lower().replace(" ", "_")
    who = (employee or name or "").strip()
    if a in ("add_employee", "add", "new_employee", "save_employee"):
        r = hrdesk.add_employee(who, id_number=id_number, position=position,
                                tax_number=tax_number, consent=consent, notes=notes)
    elif a in ("add_certificate", "add_cert", "certificate", "cert", "add_credential"):
        r = hrdesk.add_certificate(who, credential, body=body, number=number,
                                   issued=issued, expires=expires)
    elif a in ("lookup", "file", "get", "retrieve", "show", "employee_file"):
        if not who:
            return "lookup needs the employee name (employee=...). Or use action=list."
        r = hrdesk.employee_file(who)
    elif a in ("list", "all", "employees"):
        r = {"employees": hrdesk.list_employees()}
    elif a in ("update_certificate", "set_status", "status"):
        r = hrdesk.set_cert_status(who, credential, status, note=note)
    elif a in ("remove", "delete", "remove_employee"):
        r = hrdesk.remove_employee(who)
    elif a == "tax_check":
        ok, kind, msg = hrdesk.check_tax_number(tax_number)
        r = {"ok": ok, "kind": kind, "check": msg}
    else:
        return ("hr_file actions: add_employee (name, id_number, position, tax_number, "
                "consent), add_certificate (employee, credential, body, number, issued, "
                "expires), lookup (employee), list, update_certificate (employee, "
                "credential, status=pending|verified|rejected|expired, note), remove "
                "(employee), tax_check (tax_number). Owner-only: employee data stays "
                "server-side and is never shown to visitors.")
    return json.dumps(r, ensure_ascii=False)


SKILLS = {
    "calculator": {
        "label": "Calculator",
        "description": "Do exact arithmetic. Use for any maths: + - * / // % ** (), "
                       "sqrt, sin/cos/tan, log, exp, factorial, min/max, pi, e. "
                       "Always use this instead of mental maths when numbers matter.",
        "parameters": {"type": "object",
                       "properties": {"expression": {"type": "string",
                                                     "description": "e.g. (47*13+8)/2 or sqrt(144)*pi"}},
                       "required": ["expression"]},
        "fn": calculator},
    "current_datetime": {
        "label": "Date & time",
        "description": "Get the current date and time, with weekday and unix timestamp. "
                       "Use whenever 'today', 'now', dates or times matter. Optional IANA "
                       "timezone (default Africa/Johannesburg).",
        "parameters": {"type": "object",
                       "properties": {"timezone": {"type": "string",
                                                   "description": "IANA name, e.g. Africa/Johannesburg, UTC, Europe/London"}},
                       "required": []},
        "fn": current_datetime},
    "unit_convert": {
        "label": "Unit converter",
        "description": "Convert between units: length (mm..mi), mass (mg..lb), volume, area, "
                       "data (b..tib), speed, time and temperature (c/f/k).",
        "parameters": {"type": "object",
                       "properties": {
                           "value": {"type": "number", "description": "The number to convert"},
                           "from_unit": {"type": "string", "description": "Source unit, e.g. km, lb, c"},
                           "to_unit": {"type": "string", "description": "Target unit, e.g. mi, kg, f"}},
                       "required": ["value", "from_unit", "to_unit"]},
        "fn": unit_convert},
    "text_tools": {
        "label": "Text tools",
        "description": "Text utilities: count words/characters/lines, change case "
                       "(upper/lower/title), reverse, sha256, md5, base64_encode, "
                       "base64_decode, slug.",
        "parameters": {"type": "object",
                       "properties": {
                           "action": {"type": "string",
                                      "enum": ["count", "upper", "lower", "title", "reverse",
                                               "sha256", "md5", "base64_encode", "base64_decode", "slug"]},
                           "text": {"type": "string", "description": "The text to work on"}},
                       "required": ["action", "text"]},
        "fn": text_tools},
    "random_generator": {
        "label": "Random generator",
        "description": "Generate random values: number (with minimum/maximum/count), dice "
                       "(sides/count), coin, uuid, password (length). Cryptographically secure.",
        "parameters": {"type": "object",
                       "properties": {
                           "action": {"type": "string", "enum": ["number", "dice", "coin", "uuid", "password"]},
                           "minimum": {"type": "number"}, "maximum": {"type": "number"},
                           "sides": {"type": "integer"}, "count": {"type": "integer"},
                           "length": {"type": "integer"}},
                       "required": ["action"]},
        "fn": random_generator},
    "web_search": {
        "label": "Web search",
        "description": "Search the live web and get titles, URLs and snippets. Uses the "
                       "Brave Search API when the owner configured a free key, otherwise "
                       "DuckDuckGo, with Wikipedia as fallback. "
                       "Use for current events, prices, news, anything after your training "
                       "cut-off, or to verify a fact. Give specific keywords.",
        "parameters": {"type": "object",
                       "properties": {
                           "query": {"type": "string", "description": "Search keywords"},
                           "max_results": {"type": "integer", "description": "1-10, default 5"}},
                       "required": ["query"]},
        "fn": web_search},
    "live_pulse": {
        "label": "Live pulse",
        "description": "Real-time data with no API keys (Grok-style live awareness, free "
                       "sources): source=news -> live Google News headlines for a query and "
                       "country (default ZA); source=reddit -> live public Reddit pulse for "
                       "a topic (scores, comments, subreddit); source=trends -> what a "
                       "country is searching right now (Google Trends daily). Use for 'what "
                       "is happening / in the news / trending right now' questions. X/Twitter "
                       "itself is paywalled everywhere; for ordinary web pages use web_search.",
        "parameters": {"type": "object",
                       "properties": {
                           "source": {"type": "string", "enum": ["news", "reddit", "trends"]},
                           "query": {"type": "string",
                                     "description": "topic for news/reddit, e.g. 'Eskom'"},
                           "geo": {"type": "string",
                                   "description": "2-letter country code for news/trends, default ZA"},
                           "max_items": {"type": "integer", "description": "1-15, default 8"}},
                       "required": ["source"]},
        "fn": live_pulse},
    "trust_desk": {
        "label": "SA Trust Desk",
        "description": "South African credit & trust helpers (lawful, defensive): consumer credit "
                       "rights (free s72 reports, listing clocks, dispute deadlines), draft an NCA "
                       "s72(3) dispute letter, a paid-up letter request or a POPIA consent form, "
                       "validate a SARS VAT number format, and guide official NCR lender / CIPC "
                       "company register checks. Also prof_register: how to verify professional "
                       "registrations on free official public registers - SACPCMP project & "
                       "construction managers, SANC nurses/midwives (SA), AHPRA/NMBA nurses "
                       "(Australia), SARS tax practitioners (PR numbers) - plus registration "
                       "routes, fees and forgery red flags. Use for credit reports, disputes, "
                       "lender legitimacy, company or VAT trust checks, and verifying whether a "
                       "project manager, nurse, accountant or tax practitioner is really "
                       "registered.",
        "parameters": {"type": "object",
                       "properties": {
                           "action": {"type": "string",
                                      "enum": ["credit_rights", "dispute_letter",
                                               "paid_up_letter", "consent_form",
                                               "ncr_lender", "cipc_company", "sars_vat",
                                               "prof_register"]},
                           "body": {"type": "string",
                                    "description": "for prof_register: sacpcmp | sanc | ahpra "
                                                   "(NMBA Australia) | sars (tax practitioner) | "
                                                   "blank for the full register list"},
                           "bureau": {"type": "string", "description": "credit bureau name"},
                           "creditor": {"type": "string"}, "account": {"type": "string"},
                           "entry": {"type": "string", "description": "the disputed listing"},
                           "grounds": {"type": "string", "description": "why it is wrong"},
                           "name": {"type": "string"}, "id_number": {"type": "string"},
                           "address": {"type": "string"}, "contact": {"type": "string"},
                           "company": {"type": "string"}, "company_reg": {"type": "string"},
                           "purpose": {"type": "string", "description": "consent purpose"},
                           "vat_number": {"type": "string"}},
                       "required": ["action"]},
        "fn": trust_desk},
    "hr_file": {
        "label": "Employee Trust Files",
        "owner_only": True,
        "description": "OWNER-ONLY employee records (POPIA-sensitive). Store and retrieve "
                       "employees with their ID numbers, positions, SARS tax numbers "
                       "(auto format-checked: personal tax reference = 10 digits starting "
                       "0/1/2/3/9, employer PAYE = starts with 7, VAT numbers rejected), "
                       "consent status, and every certificate/credential with verification "
                       "status, expiry warnings and the official free channel to verify it "
                       "(SACPCMP, SANC, AHPRA, SARS, SAQA...). Use when the owner wants to "
                       "add an employee, record or retrieve employee certificates, check a "
                       "SARS/tax number, or track verification status and expiries.",
        "parameters": {"type": "object",
                       "properties": {
                           "action": {"type": "string",
                                      "enum": ["add_employee", "add_certificate", "lookup",
                                               "list", "update_certificate", "remove",
                                               "tax_check"]},
                           "employee": {"type": "string", "description": "employee name"},
                           "name": {"type": "string", "description": "alias for employee"},
                           "id_number": {"type": "string"},
                           "position": {"type": "string"},
                           "tax_number": {"type": "string",
                                          "description": "the employee's SARS tax reference"},
                           "consent": {"type": "string",
                                       "description": "'yes' once POPIA screening consent is recorded"},
                           "notes": {"type": "string"},
                           "credential": {"type": "string",
                                          "description": "e.g. 'SACPCMP Pr.CPM registration'"},
                           "body": {"type": "string",
                                    "description": "issuing body: SACPCMP, SANC, iQ Academy..."},
                           "number": {"type": "string",
                                      "description": "certificate/registration number"},
                           "issued": {"type": "string"}, "expires": {"type": "string"},
                           "status": {"type": "string",
                                      "enum": ["pending", "verified", "rejected", "expired"]},
                           "note": {"type": "string", "description": "verification note"}},
                       "required": ["action"]},
        "fn": hr_file},
}


def has(name: str) -> bool:
    return name in SKILLS


def names() -> list:
    return [{"id": k, "label": v["label"]} for k, v in SKILLS.items()]


def tool_defs(owner: bool = False) -> list:
    """OpenAI-format tool definitions for the model. Owner-only skills are hidden from
    visitors so the model can never be talked into leaking employee data."""
    return [{"type": "function",
             "function": {"name": name, "description": sk["description"],
                          "parameters": sk["parameters"]}}
            for name, sk in SKILLS.items() if owner or not sk.get("owner_only")]


def run(name: str, args_json: str, owner: bool = False) -> str:
    """Execute a skill call from the model. Always returns a string for the tool message."""
    sk = SKILLS.get(name)
    if not sk:
        return f"Unknown skill '{name}'."
    if sk.get("owner_only") and not owner:
        return ("This skill is owner-only: it holds employees' private data (ID and tax "
                "numbers) and never answers for visitors.")
    try:
        args = json.loads(args_json) if args_json else {}
        if not isinstance(args, dict):
            args = {}
    except (ValueError, TypeError):
        args = {}
    try:
        out = sk["fn"](**args)
    except TypeError as exc:                   # model passed junk parameters
        out = f"Bad arguments for {name}: {exc}"
    except Exception as exc:
        out = f"Skill {name} failed: {type(exc).__name__}: {exc}"
    out = str(out)
    return out[:8000]                          # keep tool messages compact


# --------------------------------------------------------------------- weather
_WMO = {0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
        55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
        61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
        67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
        77: "snow grains", 80: "light rain showers", 81: "rain showers",
        82: "violent rain showers", 85: "snow showers", 86: "snow showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


def weather(location: str = "", days: int = 3, **_) -> str:
    """Live weather from Open-Meteo - free, no API key."""
    location = str(location or "Cape Town").strip()
    days = max(1, min(int(days or 3), 7))
    try:
        g = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                      params={"name": location, "count": 1, "language": "en"},
                      headers=_HEADERS, timeout=15).json()
        hits = g.get("results") or []
        if not hits:
            return f"No place found called '{location}'."
        place = hits[0]
        f = httpx.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "weather_code,wind_speed_10m,precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max",
            "timezone": "auto", "forecast_days": days}, headers=_HEADERS, timeout=15).json()
        cur = f.get("current") or {}
        out = {"place": f"{place.get('name')}, {place.get('admin1', '')} {place.get('country', '')}".strip(),
               "local_time": cur.get("time"),
               "now": {"condition": _WMO.get(cur.get("weather_code"), "unknown"),
                       "temp_c": cur.get("temperature_2m"),
                       "feels_like_c": cur.get("apparent_temperature"),
                       "humidity_pct": cur.get("relative_humidity_2m"),
                       "wind_kmh": cur.get("wind_speed_10m"),
                       "precipitation_mm": cur.get("precipitation")},
               "forecast": []}
        d = f.get("daily") or {}
        for i, day in enumerate(d.get("time") or []):
            out["forecast"].append({
                "date": day,
                "condition": _WMO.get((d.get("weather_code") or [None])[i], "unknown"),
                "min_c": (d.get("temperature_2m_min") or [None])[i],
                "max_c": (d.get("temperature_2m_max") or [None])[i],
                "rain_chance_pct": (d.get("precipitation_probability_max") or [None])[i]})
        return json.dumps(out, ensure_ascii=False)
    except Exception as exc:
        return f"Weather lookup failed ({type(exc).__name__}). Try again later."


# -------------------------------------------------------------- exchange rates
def exchange_rates(amount: float = 1, from_currency: str = "ZAR", to_currency: str = "", **_) -> str:
    """Live currency rates from open.er-api.com - free, no API key."""
    src = str(from_currency or "ZAR").strip().upper()[:3]
    dst = str(to_currency or "").strip().upper()[:3]
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 1.0
    try:
        r = httpx.get(f"https://open.er-api.com/v6/latest/{src}", headers=_HEADERS, timeout=15)
        data = r.json()
        if data.get("result") != "success":
            return f"No rates found for '{src}'. Use 3-letter codes like ZAR, USD, EUR, GBP."
        rates = data.get("rates") or {}
        updated = data.get("time_last_update_utc", "")
        if dst:
            if dst not in rates:
                return f"Unknown currency '{dst}'. Use 3-letter codes like ZAR, USD, EUR, GBP."
            out = round(amount * rates[dst], 4)
            return (f"{amount} {src} = {out} {dst} (rate 1 {src} = {rates[dst]} {dst}, "
                    f"updated {updated})")
        major = {k: rates[k] for k in ("USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD",
                                       "CHF", "INR", "BWP", "NAD", "ZWL") if k in rates}
        return json.dumps({"base": src, "updated": updated, "major_rates": major,
                           "all_rates_count": len(rates),
                           "note": "Ask again with to_currency for an exact conversion."},
                          ensure_ascii=False)
    except Exception as exc:
        return f"Exchange-rate lookup failed ({type(exc).__name__}). Try again later."


# ------------------------------------------------------------------ dictionary
def dictionary(word: str = "", **_) -> str:
    """Definitions from dictionaryapi.dev - free, no API key."""
    word = str(word).strip()
    if not word:
        return "No word given."
    try:
        r = httpx.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word[:60]}",
                      headers=_HEADERS, timeout=15)
        if r.status_code == 404:
            return f"No definition found for '{word}'."
        r.raise_for_status()
        entry = (r.json() or [{}])[0]
        out = {"word": entry.get("word", word), "phonetic": entry.get("phonetic", "")}
        meanings = []
        for m in (entry.get("meanings") or [])[:3]:
            defs = [d.get("definition", "") for d in (m.get("definitions") or [])[:2]]
            example = next((d.get("example") for d in (m.get("definitions") or [])
                            if d.get("example")), "")
            meanings.append({"part_of_speech": m.get("partOfSpeech", ""),
                             "definitions": defs, "example": example})
        out["meanings"] = meanings
        return json.dumps(out, ensure_ascii=False)
    except Exception as exc:
        return f"Dictionary lookup failed ({type(exc).__name__})."


# ------------------------------------------------------------------- wikipedia
def wikipedia_summary(topic: str = "", **_) -> str:
    """Quick factual summary from Wikipedia - free, no API key."""
    topic = str(topic).strip()
    if not topic:
        return "No topic given."
    try:
        title = topic.replace(" ", "_")[:80]
        r = httpx.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                      headers=_HEADERS, timeout=15)
        if r.status_code == 404:
            found = httpx.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "list": "search", "srsearch": topic[:120],
                "srlimit": 1, "format": "json", "utf8": 1}, headers=_HEADERS, timeout=15).json()
            hits = (found.get("query") or {}).get("search") or []
            if not hits:
                return f"No Wikipedia page found for '{topic}'."
            r = httpx.get("https://en.wikipedia.org/api/rest_v1/page/summary/"
                          f"{hits[0]['title'].replace(' ', '_')}", headers=_HEADERS, timeout=15)
        data = r.json()
        return json.dumps({"title": data.get("title"),
                           "summary": (data.get("extract") or "")[:1500],
                           "url": (data.get("content_urls") or {}).get("desktop", {}).get("page", "")},
                          ensure_ascii=False)
    except Exception as exc:
        return f"Wikipedia lookup failed ({type(exc).__name__})."


# ---------------------------------------------------------------------- qr code
def qr_code(text: str = "", size: int = 300, **_) -> str:
    """QR code as a Markdown image (free qrserver.com renderer, no key)."""
    text = str(text)
    if not text.strip():
        return "No text or URL given for the QR code."
    from urllib.parse import quote
    size = max(100, min(int(size or 300), 1000))
    url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={quote(text[:2000], safe='')}"
    return f"![QR code]({url})\n\nThe QR code encodes: {text[:200]}\nDirect image link: {url}"


# ---------------------------------------------------------- finance calculator
def finance_calculator(action: str = "loan_payment", amount: float = 0,
                       annual_rate_percent: float = 0, years: float = 0,
                       monthly_contribution: float = 0, **_) -> str:
    """Money maths: loan instalments, compound growth, simple interest. Exact formulas."""
    try:
        P, r, t, c = float(amount), float(annual_rate_percent), float(years), float(monthly_contribution or 0)
    except (TypeError, ValueError):
        return "Pass numbers: amount, annual_rate_percent, years (and optional monthly_contribution)."
    if P <= 0 or t <= 0:
        return "amount and years must be positive numbers."
    action = str(action).strip().lower()
    n = int(round(t * 12))
    i = (r / 100) / 12
    try:
        if action in ("loan_payment", "loan", "pmt", "instalment", "installment"):
            pmt = P * i / (1 - (1 + i) ** -n) if i > 0 else P / n
            total = pmt * n
            return json.dumps({"monthly_payment": round(pmt, 2), "total_paid": round(total, 2),
                               "total_interest": round(total - P, 2), "months": n,
                               "note": "Standard reducing-balance loan at the given annual rate."})
        if action in ("compound", "compound_interest", "investment", "future_value", "savings"):
            if i > 0:
                fv = P * (1 + i) ** n + (c * (((1 + i) ** n - 1) / i) if c else 0)
            else:
                fv = P + c * n
            return json.dumps({"future_value": round(fv, 2), "contributed": round(P + c * n, 2),
                               "growth": round(fv - P - c * n, 2), "months": n,
                               "note": "Monthly compounding at the given annual rate."})
        if action in ("simple_interest", "simple"):
            interest = P * (r / 100) * t
            return json.dumps({"interest": round(interest, 2), "total": round(P + interest, 2)})
        return ("Unknown action. Use: loan_payment, compound (with optional "
                "monthly_contribution), simple_interest.")
    except (OverflowError, ZeroDivisionError):
        return "Those numbers overflow - check the rate and years."


# ------------------------------------------------------------------- json tool
def json_tool(action: str = "validate", text: str = "", indent: int = 2, **_) -> str:
    """Validate, pretty-format or minify JSON."""
    text = str(text)
    action = str(action).strip().lower()
    try:
        data = json.loads(text)
    except ValueError as exc:
        return f"Invalid JSON: {exc}"
    if action in ("validate", ""):
        kind = type(data).__name__
        size = len(data) if isinstance(data, (list, dict)) else None
        return f"Valid JSON ({kind}" + (f", {size} items" if size is not None else "") + ")."
    if action in ("format", "pretty", "beautify"):
        return json.dumps(data, indent=max(0, min(int(indent or 2), 8)), ensure_ascii=False)
    if action in ("minify", "compact"):
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return "Unknown action. Use: validate, format, minify."


# ---------------------------------------------------------------- regex tester
def regex_tester(pattern: str = "", text: str = "", ignore_case: bool = False, **_) -> str:
    """Test a regular expression and list the matches with their positions and groups."""
    pattern, text = str(pattern), str(text)[:100000]
    if not pattern:
        return "No pattern given."
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern[:2000], flags)
    except re.error as exc:
        return f"Invalid regex: {exc}"
    matches = []
    for m in list(rx.finditer(text))[:20]:
        item = {"match": m.group(0)[:200], "start": m.start(), "end": m.end()}
        if m.groupdict():
            item["groups"] = {k: (v[:100] if isinstance(v, str) else v)
                              for k, v in m.groupdict().items()}
        elif m.groups():
            item["groups"] = [g[:100] if isinstance(g, str) else g for g in m.groups()]
        matches.append(item)
    return json.dumps({"pattern": pattern, "total_matches_shown": len(matches),
                       "matches": matches}, ensure_ascii=False)


# ------------------------------------------------------------- timezone convert
def timezone_convert(time_str: str = "", from_tz: str = "UTC",
                     to_tz: str = "Africa/Johannesburg", **_) -> str:
    """Convert a date/time between timezones (empty time_str = now)."""
    try:
        src = zoneinfo.ZoneInfo(str(from_tz or "UTC").strip())
        dst = zoneinfo.ZoneInfo(str(to_tz or "Africa/Johannesburg").strip())
    except Exception:
        return "Unknown timezone. Use IANA names like Africa/Johannesburg, UTC, Europe/London."
    time_str = str(time_str).strip()
    if not time_str:
        moment = _dt.datetime.now(src)
    else:
        parsed = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%H:%M"):
            try:
                parsed = _dt.datetime.strptime(time_str.replace("Z", ""), fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return ("Could not read that time. Use formats like 2026-10-16 14:30, "
                    "2026-10-16T14:30:00 or 14:30.")
        moment = parsed.replace(tzinfo=src)
    out = moment.astimezone(dst)
    return (f"{moment.strftime('%A, %d %B %Y %H:%M %Z')} ({from_tz}) = "
            f"{out.strftime('%A, %d %B %Y %H:%M %Z')} ({to_tz})")


# -------------------------------------------------------------------- url tool
def url_tool(action: str = "parse", text: str = "", **_) -> str:
    """Split a URL into its parts, or percent-encode/decode text."""
    from urllib.parse import urlparse, parse_qs, quote, unquote
    text, action = str(text), str(action).strip().lower()
    if not text:
        return "No URL or text given."
    if action in ("encode", "quote"):
        return quote(text, safe="")
    if action in ("decode", "unquote"):
        return unquote(text)
    if action in ("parse", ""):
        u = urlparse(text if "://" in text else "https://" + text)
        return json.dumps({"scheme": u.scheme, "host": u.netloc, "path": u.path,
                           "query_params": {k: v for k, v in parse_qs(u.query).items()},
                           "fragment": u.fragment}, ensure_ascii=False)
    return "Unknown action. Use: parse, encode, decode."


# ------------------------------------------------------------- password audit
_COMMON = {"password", "123456", "12345678", "qwerty", "abc123", "letmein", "admin",
           "welcome", "monkey", "dragon", "football", "iloveyou", "111111", "123123",
           "sunshine", "princess", "passw0rd", "shadow", "superman", "batman",
           "trustno1", "freedom", "whatever", "pass123", "1234567890", "000000",
           "password1", "qwerty123", "zaq12wsx", "qwertyuiop", "asdfgh", "zxcvbn"}


def password_strength(password: str = "", **_) -> str:
    """Audit a password: entropy estimate, patterns and concrete improvements.
    Nothing is stored or sent anywhere - the check runs on the server and forgets."""
    pw = str(password)
    if not pw:
        return "No password given."
    pool = 0
    if re.search(r"[a-z]", pw): pool += 26
    if re.search(r"[A-Z]", pw): pool += 26
    if re.search(r"[0-9]", pw): pool += 10
    if re.search(r"[^a-zA-Z0-9]", pw): pool += 33
    entropy = round(len(pw) * math.log2(pool), 1) if pool else 0
    problems = []
    low = pw.lower()
    if low in _COMMON or any(w in low for w in ("password", "qwerty", "letmein", "admin")):
        problems.append("contains a very common password word")
    if re.search(r"(.){2,}", pw):
        problems.append("repeats a character 3+ times")
    for seq in ("abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiop", "asdfghjkl"):
        if any(seq[i:i + 4] in low or seq[i:i + 4][::-1] in low for i in range(len(seq) - 3)):
            problems.append("contains a keyboard/alphabet sequence")
            break
    if re.fullmatch(r"[0-9]+", pw):
        problems.append("digits only")
    if len(pw) < 8:
        problems.append("shorter than 8 characters")
    score = 4
    if entropy < 28: score = 0
    elif entropy < 40: score = 1
    elif entropy < 60: score = 2
    elif entropy < 80: score = 3
    if problems:
        score = max(0, score - 1)
    verdict = ["very weak", "weak", "fair", "strong", "very strong"][score]
    tips = []
    if len(pw) < 12: tips.append("use at least 12 characters")
    if problems: tips.append("avoid common words, sequences and repeats")
    if score < 3: tips.append("mix upper/lower case, digits and symbols, e.g. a passphrase "
                              "of 4 random words with separators")
    return json.dumps({"length": len(pw), "entropy_bits": entropy, "score": f"{score}/4",
                       "verdict": verdict, "problems": problems or ["none found"],
                       "tips": tips or ["good password - consider a password manager"]},
                      ensure_ascii=False)


# ---------------------------------------------------------------- extra registry
SKILLS.update({
    "weather": {
        "label": "Weather",
        "description": "Live current weather and forecast for any city (Open-Meteo, no key): "
                       "temperature, feels-like, humidity, wind, rain chance, up to 7 days.",
        "parameters": {"type": "object",
                       "properties": {"location": {"type": "string", "description": "City or town, e.g. Cape Town"},
                                      "days": {"type": "integer", "description": "Forecast days 1-7, default 3"}},
                       "required": []},
        "fn": weather},
    "exchange_rates": {
        "label": "Exchange rates",
        "description": "Live currency exchange rates and conversions (ZAR, USD, EUR, GBP, ...). "
                       "Use for any money conversion or 'how much is X in Y' question.",
        "parameters": {"type": "object",
                       "properties": {"amount": {"type": "number"},
                                      "from_currency": {"type": "string", "description": "3-letter code, default ZAR"},
                                      "to_currency": {"type": "string", "description": "3-letter code; omit for a rate table"}},
                       "required": []},
        "fn": exchange_rates},
    "dictionary": {
        "label": "Dictionary",
        "description": "Definitions, part of speech, phonetics and examples for an English word.",
        "parameters": {"type": "object",
                       "properties": {"word": {"type": "string"}},
                       "required": ["word"]},
        "fn": dictionary},
    "wikipedia_summary": {
        "label": "Wikipedia",
        "description": "Factual summary of any topic from Wikipedia with the source URL. Good for "
                       "'what is / who is' questions about companies, people, places and concepts.",
        "parameters": {"type": "object",
                       "properties": {"topic": {"type": "string"}},
                       "required": ["topic"]},
        "fn": wikipedia_summary},
    "qr_code": {
        "label": "QR code",
        "description": "Generate a QR code image for any text, link, WiFi details or payment reference. "
                       "Returns a Markdown image the chat displays.",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string", "description": "Text or URL to encode"},
                                      "size": {"type": "integer", "description": "Pixels, default 300"}},
                       "required": ["text"]},
        "fn": qr_code},
    "finance_calculator": {
        "label": "Finance calculator",
        "description": "Money maths: loan_payment (monthly instalment + total interest), compound "
                       "(future value with optional monthly contributions), simple_interest. "
                       "Use for loans, bonds, investments, savings - amounts in any currency.",
        "parameters": {"type": "object",
                       "properties": {
                           "action": {"type": "string", "enum": ["loan_payment", "compound", "simple_interest"]},
                           "amount": {"type": "number", "description": "Principal amount"},
                           "annual_rate_percent": {"type": "number", "description": "Annual interest rate in %"},
                           "years": {"type": "number"},
                           "monthly_contribution": {"type": "number", "description": "For compound only"}},
                       "required": ["action", "amount", "years"]},
        "fn": finance_calculator},
    "json_tool": {
        "label": "JSON tool",
        "description": "Validate, pretty-format or minify JSON text.",
        "parameters": {"type": "object",
                       "properties": {"action": {"type": "string", "enum": ["validate", "format", "minify"]},
                                      "text": {"type": "string"}, "indent": {"type": "integer"}},
                       "required": ["action", "text"]},
        "fn": json_tool},
    "regex_tester": {
        "label": "Regex tester",
        "description": "Test a regular expression against text: shows every match with positions "
                       "and capture groups.",
        "parameters": {"type": "object",
                       "properties": {"pattern": {"type": "string"}, "text": {"type": "string"},
                                      "ignore_case": {"type": "boolean"}},
                       "required": ["pattern", "text"]},
        "fn": regex_tester},
    "timezone_convert": {
        "label": "Timezone converter",
        "description": "Convert a date/time between timezones (empty time = right now). IANA names, "
                       "e.g. Africa/Johannesburg to Europe/London.",
        "parameters": {"type": "object",
                       "properties": {"time_str": {"type": "string", "description": "e.g. 2026-10-16 14:30 (empty = now)"},
                                      "from_tz": {"type": "string"}, "to_tz": {"type": "string"}},
                       "required": []},
        "fn": timezone_convert},
    "url_tool": {
        "label": "URL tool",
        "description": "Split a URL into scheme/host/path/query params, or percent-encode/decode text.",
        "parameters": {"type": "object",
                       "properties": {"action": {"type": "string", "enum": ["parse", "encode", "decode"]},
                                      "text": {"type": "string"}},
                       "required": ["action", "text"]},
        "fn": url_tool},
    "password_strength": {
        "label": "Password audit",
        "description": "Audit a password's strength: entropy, common-pattern detection and concrete "
                       "improvement tips. Checked on the server and immediately forgotten.",
        "parameters": {"type": "object",
                       "properties": {"password": {"type": "string"}},
                       "required": ["password"]},
        "fn": password_strength},
})
