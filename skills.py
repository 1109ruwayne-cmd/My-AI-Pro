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
