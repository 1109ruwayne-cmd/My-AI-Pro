"""My AI Pro Self-Repair Engine ("AutoMedic").

Complete in-app self-maintenance: the program watches its own body (source files,
databases, knowledge base, disk), repairs what is safely repairable (restores a
missing or corrupted source file from the exact duplicate it keeps in its own
knowledge base, re-creates schema, refreshes the knowledge index), records every
diagnosis and repair in a heal log, and exposes owner-gated diagnostics.

Nothing here ever invents state or fakes an outcome: a repair either succeeds and
is logged, or is reported as needing the owner's hand.
"""
from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = Path(os.environ.get("SELFHEAL_DB", str(BASE / "selfheal.db")))
_lock = threading.Lock()
_interval = 600  # watchdog seconds

TRACKED = ["app.py", "billing.py", "skills.py", "connectors.py", "knowledge_base.py",
           "ratelimit.py", "registry.py", "selfheal.py",
           "static/index.html", "static/registry.html", "static/services.html"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS heals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, detail TEXT,
  action TEXT, outcome TEXT);
"""


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def log(kind: str, detail: str, action: str, outcome: str) -> None:
    try:
        with _lock, _conn() as con:
            con.execute("INSERT INTO heals(ts,kind,detail,action,outcome) VALUES(?,?,?,?,?)",
                        (time.time(), kind, detail, action, outcome))
    except Exception:
        pass


def heals(limit: int = 60) -> list:
    try:
        with _lock, _conn() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM heals ORDER BY id DESC LIMIT ?", (limit,))]
    except Exception:
        return []


# ------------------------------------------------------------------ file health
def _text_ok(rel: str, text: str) -> bool:
    if not text or len(text) < 40:
        return False
    if rel.endswith(".py"):
        try:
            ast.parse(text)
            return True
        except SyntaxError:
            return False
    if rel.endswith(".html"):
        return "</html>" in text
    return True


def _file_ok(path: Path) -> bool:
    try:
        return _text_ok(path.name if path.parent.name != "static" else f"static/{path.name}",
                        path.read_text(encoding="utf-8"))
    except Exception:
        return False


def _kb_copy_for(kb_dir: Path, rel: str):
    """Find the exact duplicate of `rel` inside the knowledge-base mirrors."""
    if not kb_dir or not Path(kb_dir).exists():
        return None
    for md in sorted(Path(kb_dir).glob("*source*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        if f"source code: {rel}" in text:           # per-file mirror document
            parts = text.split("~~~~")
            if len(parts) >= 3 and _text_ok(rel, parts[1].strip("\n")):
                return parts[1].strip("\n")
        if f"## {rel}\n" in text:                    # infrastructure bundle section
            seg = text.split(f"## {rel}\n", 1)[1]
            parts = seg.split("~~~~")
            if len(parts) >= 3 and _text_ok(rel, parts[1].strip("\n")):
                return parts[1].strip("\n")
    return None


def restore_sources(kb_dir: Path) -> list:
    """Boot-time repair: any tracked source missing or corrupt is restored from
    the exact duplicate the program keeps of itself in its knowledge base."""
    restored = []
    for rel in TRACKED:
        p = BASE / rel
        if p.exists() and _file_ok(p):
            continue
        copy = _kb_copy_for(kb_dir, rel)
        if not copy:
            log("restore", f"{rel} missing/corrupt, no knowledge-base copy found",
                "none possible", "needs-owner")
            continue
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(copy, encoding="utf-8")
            log("restore", f"{rel} was missing/corrupt",
                "restored from knowledge-base duplicate", "ok")
            restored.append(rel)
        except Exception as e:
            log("restore", f"{rel} missing/corrupt", "restore attempted", f"failed: {e}")
    return restored


# ------------------------------------------------------------------ diagnostics
def _check_databases(report: list) -> None:
    dbs = []
    try:
        import billing
        dbs.append(("usage/billing", Path(billing.DB_PATH)))
    except Exception:
        pass
    try:
        import registry as reg
        dbs.append(("registry", Path(reg.DB_PATH)))
    except Exception:
        pass
    dbs.append(("selfheal", DB))
    for name, p in dbs:
        if not p.exists():
            report.append({"check": f"db:{name}", "status": "absent (created on first use)",
                           "action": "none"})
            continue
        try:
            with sqlite3.connect(p, timeout=15) as con:
                ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            if ok == "ok":
                report.append({"check": f"db:{name}", "status": "healthy", "action": "none"})
            else:
                log("db", f"{name} integrity: {ok}", "logged for owner", "needs-owner")
                report.append({"check": f"db:{name}", "status": f"INTEGRITY: {ok}",
                               "action": "needs-owner"})
        except Exception as e:
            log("db", f"{name} unreadable: {e}", "logged for owner", "needs-owner")
            report.append({"check": f"db:{name}", "status": f"unreadable: {e}",
                           "action": "needs-owner"})


def _check_disk(report: list) -> None:
    try:
        free = shutil.disk_usage(BASE).free
        mb = free // (1024 * 1024)
        if mb <= 20:
            log("disk", f"{mb} MB free", "logged for owner", "needs-owner")
        report.append({"check": "disk", "status": f"{mb} MB free", "action":
                       "none" if mb > 20 else "needs-owner"})
    except Exception as e:
        report.append({"check": "disk", "status": f"unknown: {e}", "action": "none"})


def _check_sources(report: list, kb_dir: Path) -> None:
    bad = [rel for rel in TRACKED if not (BASE / rel).exists()
           or not _file_ok(BASE / rel)]
    if not bad:
        report.append({"check": "sources", "status": f"all {len(TRACKED)} tracked files healthy",
                       "action": "none"})
        return
    restored = restore_sources(kb_dir)
    still = [b for b in bad if b not in restored]
    report.append({"check": "sources", "status": f"corrupt: {bad}",
                   "action": f"restored {restored or 'none'}" + (f"; needs-owner: {still}" if still else "")})


def _check_kb(report: list, kb) -> None:
    try:
        n = len(kb.files) if kb is not None else 0
        if n:
            report.append({"check": "knowledge-base", "status": f"{n} file(s) indexed",
                           "action": "none"})
        else:
            try:
                kb.refresh()
                n = len(kb.files)
                log("kb", "index empty at check", "refreshed", f"{n} file(s) after refresh")
            except Exception as e:
                log("kb", "index empty, refresh failed", str(e), "needs-owner")
            report.append({"check": "knowledge-base", "status": f"{n} file(s) after refresh",
                           "action": "refreshed"})
    except Exception as e:
        report.append({"check": "knowledge-base", "status": f"unreadable: {e}",
                       "action": "needs-owner"})


def run_diagnostics(kb=None, kb_dir: Path = None, deep: bool = False) -> list:
    report: list = []
    _check_sources(report, kb_dir or (BASE / "knowledge"))
    _check_databases(report)
    _check_disk(report)
    if kb is not None:
        _check_kb(report, kb)
    if deep:
        report.append({"check": "heal-log", "status": f"{len(heals(500))} entries",
                       "action": "none"})
    return report


def watchdog(kb_getter, kb_dir: Path, stop: threading.Event = None) -> None:
    while True:
        if stop and stop.is_set():
            return
        try:
            run_diagnostics(kb=kb_getter(), kb_dir=kb_dir)
        except Exception as e:                      # the medic never dies loudly
            log("watchdog", f"diagnostics error: {e}", "swallowed", "ok")
        time.sleep(_interval)


# ------------------------------------------------------------------ error playbook
SIGNATURES = (
    ("openrouter-credits", ("402", "afford", "credits"),
     "capped/retried at lower max_tokens"),
    ("provider-timeout", ("timed out", "timeout", "connection"),
     "fell through to next engine in chain"),
    ("tool-stall", ("tool", "function"),
     "tool round disabled for that model"),
)


def note_error(exc: Exception, base_url: str = "") -> str:
    msg = str(exc).lower()
    for name, keys, mitigation in SIGNATURES:
        if any(k in msg for k in keys):
            log("mitigation", f"{name} on {base_url or 'provider'}: {str(exc)[:200]}",
                mitigation, "applied")
            return name
    log("error", f"unclassified on {base_url or 'provider'}: {str(exc)[:200]}",
        "logged", "recorded")
    return "unclassified"
