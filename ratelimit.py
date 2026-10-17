"""In-memory rate limiting and brute-force lockout.

The free hosts run a single worker process, so counters live in memory; they
reset on restart, which is acceptable - the database stays the source of
truth for money. Nothing here needs dependencies or configuration.

Protections provided:
    hit(key, max_hits, window)  sliding-window limiter for any endpoint
    admin_fail/admin_blocked    lockout against admin-password guessing
"""
import threading
import time

ADMIN_FAIL_MAX = 10        # wrong admin passwords ...
ADMIN_FAIL_WINDOW = 600    # ... within 10 minutes ...
ADMIN_LOCKOUT = 600        # ... lock that IP out for 10 minutes

AUTO_BAN_BLOCKS = 8        # an IP that trips any limiter 8 times ...
AUTO_BAN_WINDOW = 900      # ... within 15 minutes ...
AUTO_BAN_SECONDS = 1800    # ... is banned outright for 30 minutes


class _SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict = {}
        self._lock = threading.Lock()

    def hit(self, key: str, max_hits: int, window: float):
        """Register a hit. Returns (allowed, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(key, ()) if now - t < window]
            if len(recent) >= max_hits:
                self._hits[key] = recent
                return False, int(window - (now - recent[0])) + 1 if recent else int(window)
            recent.append(now)
            self._hits[key] = recent
            if len(self._hits) > 20000:          # keep memory bounded
                for k in list(self._hits):
                    fresh = [t for t in self._hits[k] if now - t < window]
                    if fresh:
                        self._hits[k] = fresh
                    else:
                        del self._hits[k]
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


limiter = _SlidingWindow()


def hit(key: str, max_hits: int, window: float):
    return limiter.hit(key, max_hits, window)


_fails: dict = {}
_locks: dict = {}
_bans: dict = {}
_blockhist: dict = {}
_flock = threading.Lock()


def client_ip(request) -> str:
    """Best-effort client IP behind Render's proxy."""
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip() or "?"
    return (request.client.host if request.client else "") or "?"


def admin_blocked(ip: str) -> bool:
    with _flock:
        return _locks.get(ip, 0) > time.time()


def admin_retry_after(ip: str) -> int:
    with _flock:
        return max(0, int(_locks.get(ip, 0) - time.time()) + 1)


def admin_fail(ip: str) -> None:
    now = time.time()
    with _flock:
        recent = [t for t in _fails.get(ip, ()) if now - t < ADMIN_FAIL_WINDOW]
        recent.append(now)
        if len(recent) >= ADMIN_FAIL_MAX:
            _locks[ip] = now + ADMIN_LOCKOUT
            _fails[ip] = []
        else:
            _fails[ip] = recent


def admin_success(ip: str) -> None:
    with _flock:
        _fails.pop(ip, None)
        _locks.pop(ip, None)
        _bans.pop(ip, None)          # proving the owner password always lifts a ban
        # note: _blockhist stays - owner traffic must not erase an attacker's strikes


# --- autonomous escalation: repeat abusers get banned automatically ---------

def register_block(ip: str) -> bool:
    """Count one limiter trip. Returns True when this trip triggered a ban."""
    now = time.time()
    with _flock:
        hist = [t for t in _blockhist.get(ip, ()) if now - t < AUTO_BAN_WINDOW]
        hist.append(now)
        if len(hist) >= AUTO_BAN_BLOCKS:
            _bans[ip] = now + AUTO_BAN_SECONDS
            _blockhist[ip] = []
            return True
        _blockhist[ip] = hist
        return False


def ip_banned(ip: str) -> bool:
    with _flock:
        return _bans.get(ip, 0) > time.time()


def ban_retry_after(ip: str) -> int:
    with _flock:
        return max(0, int(_bans.get(ip, 0) - time.time()) + 1)


def clear_bans() -> None:
    with _flock:
        _bans.clear()
        _blockhist.clear()


def bans_snapshot() -> list:
    now = time.time()
    with _flock:
        return [{"ip": ip, "seconds_left": int(exp - now)}
                for ip, exp in _bans.items() if exp > now]
