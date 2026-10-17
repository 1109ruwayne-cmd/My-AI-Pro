# My AI Pro source code: skills.py

The Agent Skills module: all 17 built-in tools (calculator, web search, weather, exchange rates, finance maths, QR codes, etc.) and their registry.

This is the assistant's own source code, kept here so it can answer questions about how it works, explain any part of itself, and help its owner debug or extend it. Contains no secrets (passwords and API keys live in environment variables).

~~~~
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
    web_search        live results from DuckDuckGo (no API key needed)

Owner can switch the whole module off in Settings (config "skills_enabled").
"""
import ast
import base64
import datetime as _dt
import hashlib
import json
import math
import operator
import re
import secrets
import string
import zoneinfo

import httpx

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


def web_search(query: str = "", max_results: int = 5, **_) -> str:
    """Live search: DuckDuckGo first, Wikipedia as the always-on fallback. No API keys."""
    query = str(query).strip()
    if not query:
        return "No search query given."
    max_results = max(1, min(int(max_results or 5), 10))
    for engine, fn in (("duckduckgo", _ddg), ("wikipedia", _wikipedia)):
        try:
            results = fn(query, max_results)
        except Exception:
            results = []
        if results:
            return json.dumps({"query": query, "engine": engine, "results": results},
                              ensure_ascii=False)
    return (f"No web results found for '{query}' (search engines unreachable or empty). "
            "Answer from your own knowledge and say it may not be current.")


# --------------------------------------------------------------------- registry
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
        "description": "Search the live web (DuckDuckGo) and get titles, URLs and snippets. "
                       "Use for current events, prices, news, anything after your training "
                       "cut-off, or to verify a fact. Give specific keywords.",
        "parameters": {"type": "object",
                       "properties": {
                           "query": {"type": "string", "description": "Search keywords"},
                           "max_results": {"type": "integer", "description": "1-10, default 5"}},
                       "required": ["query"]},
        "fn": web_search},
}


def has(name: str) -> bool:
    return name in SKILLS


def names() -> list:
    return [{"id": k, "label": v["label"]} for k, v in SKILLS.items()]


def tool_defs() -> list:
    """OpenAI-format tool definitions for the model."""
    return [{"type": "function",
             "function": {"name": name, "description": sk["description"],
                          "parameters": sk["parameters"]}}
            for name, sk in SKILLS.items()]


def run(name: str, args_json: str) -> str:
    """Execute a skill call from the model. Always returns a string for the tool message."""
    sk = SKILLS.get(name)
    if not sk:
        return f"Unknown skill '{name}'."
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
~~~~
