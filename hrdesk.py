"""Employee trust files - owner-operated HR screening records.

Stores employees, their certificates and SARS tax numbers server-side (hr.db, same
persistence as registry.db). POPIA-conscious: consent is a recorded field, only what is
needed is stored, and NOTHING is ever pulled from SARS or institutions automatically -
verification goes through free official public registers (knowledge/32) with the
employee's recorded consent.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "hr.db"
_LOCK = threading.Lock()

_TAX_INDIVIDUAL_RE = re.compile(r"^[01239]\d{9}$")     # income tax reference (OECD TIN portal)
_TAX_PAYE_RE = re.compile(r"^7\d{9}$")                  # employer PAYE reference (SARS BRS)
_TAX_VAT_RE = re.compile(r"^4\d{9}$")                   # VAT vendor


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS employees(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE COLLATE NOCASE,
        id_number TEXT DEFAULT '', position TEXT DEFAULT '', tax_number TEXT DEFAULT '',
        consent TEXT DEFAULT 'not recorded', notes TEXT DEFAULT '',
        created TEXT DEFAULT '', updated TEXT DEFAULT '')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS certs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL, credential TEXT NOT NULL, body TEXT DEFAULT '',
        number TEXT DEFAULT '', issued TEXT DEFAULT '', expires TEXT DEFAULT '',
        status TEXT DEFAULT 'pending', note TEXT DEFAULT '', created TEXT DEFAULT '')""")
    return conn


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 7200))   # SAST date


def _luhn_ok(n: str) -> bool:
    total, alt = 0, False
    for ch in reversed(n):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def check_tax_number(raw: str):
    """Format-gate a SARS number. Returns (ok, kind, message). Format is only the first
    gate - final proof is the employee's IT150 Notice of Registration or an IRP5."""
    n = re.sub(r"\s", "", raw or "")
    if not n:
        return False, "none", "No tax number recorded yet - ask the employee for it."
    if _TAX_INDIVIDUAL_RE.match(n):
        kind = "individual income tax reference"
    elif _TAX_PAYE_RE.match(n):
        kind = "employer PAYE reference"
    elif _TAX_VAT_RE.match(n):
        return False, "vat", (f"{n} is a VAT number (starts with 4), NOT a personal tax "
                              "number. An employee's income tax reference is 10 digits "
                              "starting 0/1/2/3/9 - it appears on their IRP5 and IT150.")
    else:
        return False, "invalid", (f"{n} does not match any SARS format. SA tax reference "
                                  "numbers are exactly 10 digits: personal = starts "
                                  "0/1/2/3/9, employer PAYE = starts 7.")
    if not _luhn_ok(n):
        return True, kind, (f"Format valid ({kind} number) BUT it fails the modulus-10 "
                            "check digit test SARS applies to reference numbers - likely "
                            "a typo. Confirm against the employee's IT150 or IRP5.")
    return True, kind, f"Format valid: {kind} number, passes the modulus-10 check digit."


def _verify_hint(credential: str, body: str) -> str:
    t = ((credential or "") + " " + (body or "")).lower()
    if "sacpcmp" in t or "project manage" in t or "construction manage" in t:
        return ("SACPCMP Registered Person Search (sacpcmp.org.za) - certificates end in "
                "March; QR must validate live. trust_desk prof_register body=sacpcmp.")
    if "nurs" in t or "sanc" in t or "midwif" in t:
        return ("SANC eRegister (sanc.co.za/eRegister.aspx) by SANC number or SA ID - "
                "trust_desk prof_register body=sanc.")
    if "ahpra" in t or "nmba" in t or "australia" in t:
        return "AHPRA register (ahpra.gov.au - Look up a practitioner). prof_register body=ahpra."
    if "prdp" in t or "driver" in t or "driving" in t:
        return ("PrDP/driving: check the card's validity dates; criminal-record checks need "
                "written consent (POPIA special personal information) via SAPS.")
    if "first aid" in t or "safety officer" in t or "samtrac" in t:
        return ("Confirm with the issuing training provider + check the provider is "
                "accredited (QCTO/SETA) before trusting the certificate.")
    if "tax" in t and "practitioner" in t:
        return ("SARS eFiling Tax Practitioner Query (PR number) - prof_register body=sars.")
    return ("Verify with the issuing body directly; SA qualifications cross-check on "
            "saqa.org.za, professional designations on pbdesig.saqa.org.za. Keep the "
            "employee's written consent on file before screening (POPIA).")


def _exp_warn(expires: str) -> str:
    if not expires:
        return ""
    today = _today()
    if expires < today:
        return " **EXPIRED**"
    try:
        d0 = time.strptime(today, "%Y-%m-%d")
        d1 = time.strptime(expires, "%Y-%m-%d")
        days = int((time.mktime(d1) - time.mktime(d0)) / 86400)
        if days <= 60:
            return f" **expires in {days} days**"
    except ValueError:
        return " (unparseable expiry date)"
    return ""


def add_employee(name: str, id_number: str = "", position: str = "", tax_number: str = "",
                 consent: str = "", notes: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        return {"error": "Employee name is required."}
    today = _today()
    tax_number = re.sub(r"\s", "", tax_number or "")
    given = str(consent).strip().lower() in ("yes", "y", "true", "given", "signed", "recorded")
    consent_v = f"recorded {today}" if given else (str(consent).strip() or "")
    conn = _db()
    try:
        with _LOCK:
            row = conn.execute("SELECT * FROM employees WHERE name=? COLLATE NOCASE", (name,)).fetchone()
            if row:
                conn.execute(
                    """UPDATE employees SET
                       id_number=CASE WHEN ?<>'' THEN ? ELSE id_number END,
                       position=CASE WHEN ?<>'' THEN ? ELSE position END,
                       tax_number=CASE WHEN ?<>'' THEN ? ELSE tax_number END,
                       consent=CASE WHEN ?<>'' THEN ? ELSE consent END,
                       notes=CASE WHEN ?<>'' THEN ? ELSE notes END,
                       updated=? WHERE id=?""",
                    (id_number, id_number, position, position, tax_number, tax_number,
                     consent_v, consent_v, notes, notes, today, row["id"]))
                created = False
            else:
                conn.execute(
                    "INSERT INTO employees(name,id_number,position,tax_number,consent,notes,created,updated)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (name, id_number.strip(), position.strip(), tax_number,
                     consent_v or "not recorded", notes.strip(), today, today))
                created = True
            conn.commit()
            emp = dict(conn.execute("SELECT * FROM employees WHERE name=? COLLATE NOCASE", (name,)).fetchone())
    finally:
        conn.close()
    ok, kind, msg = check_tax_number(emp["tax_number"])
    out = {"created" if created else "updated": name, "position": emp["position"],
           "tax_number_check": msg, "consent": emp["consent"]}
    if not given:
        out["popia_reminder"] = ("Screening consent not recorded. Have the employee sign a "
                                 "consent form first (trust_desk action=consent_form) - ID "
                                 "numbers, tax numbers and criminal checks are special "
                                 "personal information under POPIA.")
    return out


def get_employee(name: str):
    conn = _db()
    try:
        with _LOCK:
            row = conn.execute("SELECT * FROM employees WHERE name=? COLLATE NOCASE",
                               ((name or "").strip(),)).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM employees WHERE name LIKE ? ORDER BY name LIMIT 1",
                                   ("%" + (name or "").strip() + "%",)).fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def add_certificate(employee: str, credential: str, body: str = "", number: str = "",
                    issued: str = "", expires: str = "") -> dict:
    emp = get_employee(employee)
    if not emp:
        return {"error": f"No employee '{employee}'. Add them first (action=add_employee)."}
    if not (credential or "").strip():
        return {"error": "credential is required (e.g. 'SACPCMP Pr.CPM registration')."}
    conn = _db()
    try:
        with _LOCK:
            conn.execute(
                "INSERT INTO certs(employee_id,credential,body,number,issued,expires,status,created)"
                " VALUES(?,?,?,?,?,?,'pending',?)",
                (emp["id"], credential.strip(), body.strip(), number.strip(),
                 issued.strip(), expires.strip(), _today()))
            conn.commit()
    finally:
        conn.close()
    return {"stored": credential.strip(), "for": emp["name"], "status": "pending",
            "verify": _verify_hint(credential, body)}


def set_cert_status(employee: str, credential: str, status: str, note: str = "") -> dict:
    emp = get_employee(employee)
    if not emp:
        return {"error": f"No employee '{employee}'."}
    status = (status or "").strip().lower()
    if status not in ("pending", "verified", "rejected", "expired"):
        return {"error": "status must be pending, verified, rejected or expired."}
    conn = _db()
    try:
        with _LOCK:
            cur = conn.execute(
                "UPDATE certs SET status=?, note=CASE WHEN ?<>'' THEN ? ELSE note END"
                " WHERE employee_id=? AND credential LIKE ?",
                (status, note, note, emp["id"], "%" + (credential or "").strip() + "%"))
            conn.commit()
            n = cur.rowcount
    finally:
        conn.close()
    if not n:
        return {"error": f"No certificate matching '{credential}' for {emp['name']}."}
    return {"updated": n, "employee": emp["name"], "credential": credential, "status": status}


def employee_file(name: str) -> dict:
    emp = get_employee(name)
    if not emp:
        return {"error": f"No employee matching '{name}'. Use action=list to see all files."}
    conn = _db()
    try:
        with _LOCK:
            cs = [dict(r) for r in conn.execute(
                "SELECT * FROM certs WHERE employee_id=? ORDER BY created", (emp["id"],))]
    finally:
        conn.close()
    ok, kind, tax_msg = check_tax_number(emp["tax_number"])
    return {"employee": emp, "tax_ok": ok, "tax_check": tax_msg,
            "certificates": [{**c, "expiry_flag": _exp_warn(c["expires"]),
                              "verify_how": _verify_hint(c["credential"], c["body"])}
                             for c in cs]}


def list_employees() -> list:
    conn = _db()
    try:
        with _LOCK:
            emps = [dict(r) for r in conn.execute("SELECT * FROM employees ORDER BY name")]
            out = []
            for e in emps:
                cs = [dict(r) for r in conn.execute(
                    "SELECT status, credential, expires FROM certs WHERE employee_id=?", (e["id"],))]
                ok, _kind, tax_msg = check_tax_number(e["tax_number"])
                out.append({"name": e["name"], "position": e["position"],
                            "tax_number_ok": ok, "consent": e["consent"],
                            "certificates": len(cs),
                            "pending": sum(1 for c in cs if c["status"] == "pending"),
                            "verified": sum(1 for c in cs if c["status"] == "verified"),
                            "rejected": sum(1 for c in cs if c["status"] == "rejected"),
                            "expiring": [c["credential"] + _exp_warn(c["expires"])
                                         for c in cs if c["expires"] and _exp_warn(c["expires"])]})
            return out
    finally:
        conn.close()


def remove_employee(name: str) -> dict:
    emp = get_employee(name)
    if not emp:
        return {"error": f"No employee matching '{name}'."}
    conn = _db()
    try:
        with _LOCK:
            conn.execute("DELETE FROM certs WHERE employee_id=?", (emp["id"],))
            conn.execute("DELETE FROM employees WHERE id=?", (emp["id"],))
            conn.commit()
    finally:
        conn.close()
    return {"removed": emp["name"], "note": "Employee file and all certificate records deleted."}
