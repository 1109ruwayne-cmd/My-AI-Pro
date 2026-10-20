"""My AI Pro Registry - personal SA certification, CIPC & wireman's licence desk.

A private vault + checklist manager for the owner's own certifications, companies
and licences; a state-application pack builder (Department of Employment and
Labour wireman's licence, CIPC incorporation, SAQA verification); branded
certificate issuing with public verification; and a public per-service order
desk paid by EFT into the owner's bank account.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import httpx
import qrcode
from qrcode.image.svg import SvgPathImage
from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

DB_PATH = Path(os.environ.get("REGISTRY_DB", str(Path(__file__).parent / "registry.db")))
_lock = threading.Lock()
MAX_DOC = 15 * 1024 * 1024
_CORS = {"Access-Control-Allow-Origin": "*"}


def _fingerprint(cert: dict) -> str:
    """SHA-256 integrity fingerprint over the credential's immutable fields."""
    return hashlib.sha256("|".join(str(cert.get(k) or "") for k in
                                   ("code", "holder", "ctype", "issued_on", "expires_on")).encode()).hexdigest()

TURSO_DB_URL = os.environ.get("TURSO_DB_URL", "").strip()
if TURSO_DB_URL.startswith("libsql://"):
    TURSO_DB_URL = "https://" + TURSO_DB_URL[len("libsql://"):]
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
_last_backup = 0.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, title TEXT, authority TEXT,
  number TEXT, issued_on TEXT, expires_on TEXT, status TEXT, notes TEXT, created REAL);
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, name TEXT, mime TEXT,
  size INTEGER, data BLOB, created REAL);
CREATE TABLE IF NOT EXISTS certs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, holder TEXT, ctype TEXT,
  body TEXT, issued_on TEXT, expires_on TEXT, voided INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE, client TEXT, contact TEXT,
  service TEXT, amount REAL, status TEXT, created REAL, verify_until REAL);
CREATE TABLE IF NOT EXISTS services(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL, descr TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS submissions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, channel TEXT, target TEXT,
  status TEXT, log TEXT, created REAL, sent_at REAL);
CREATE TABLE IF NOT EXISTS traffic(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref TEXT, descr TEXT,
  amount REAL DEFAULT 0, status TEXT DEFAULT 'unpaid', paid_on TEXT DEFAULT '',
  receipt TEXT DEFAULT '', expires_on TEXT DEFAULT '', created REAL);
"""

# ---------------------------------------------------------------- statutory checklists
CHECKLISTS = {
    "licence": {
        "label": "Wireman's licence - DoEL Registered Person",
        "authority": "Dept of Employment and Labour (OHS Act 85/1993, Electrical Installation Regulations 2009)",
        "steps": [
            "Annexure 5 application form - Regulation 11(1), Application for Registration as a Registered Person (labour.gov.za)",
            "Certified copy of ID (certified within the last 3 months)",
            "Trade test certificate / National Certificate: Electrical Engineering (NQF level 3 or higher)",
            "N2/N3 certificate with Mathematics, Engineering Science and an electrical subject at 40%+ (or NQF level 4 equivalent)",
            "Installation Rules Paper 1 AND Paper 2 results at 50%+ (FET/TVET college)",
            "Proof of practical experience - dated employer letters on letterhead",
            "Two passport-size photographs",
            "Proof of payment of the Department's registration fee",
            "For renewals: certified copy of the current wireman's licence / registration card",
        ],
        "notes": ("Categories: Electrical Tester Single Phase (ETSP) | Installation Electrician (IE, "
                  "single + three-phase) | Master Installation Electrician (MIE, specialised/hazardous). "
                  "Trading as an electrical business needs a SEPARATE Annexure 3 electrical-contractor "
                  "registration. Only a Registered Person may issue an Annexure 1 Certificate of Compliance."),
    },
    "business": {
        "label": "CIPC company registration",
        "authority": "Companies and Intellectual Property Commission (Companies Act 71/2008)",
        "steps": [
            "CoR 9.1 name reservation - up to 4 names in order of preference (R50 electronic / R75 manual; valid 6 months; confirmation on CoR 9.4)",
            "CoR 14.1 Notice of Incorporation",
            "CoR 15.1A Memorandum of Incorporation - standard short form for private companies (R175; bespoke MOI R475)",
            "Certified copies of the ID / passport of every incorporator and director",
            "Proof of the registered office address",
            "Power of attorney if a representative files",
            "Proof of payment of CIPC filing fees",
        ],
        "notes": ("Name reservations cannot be extended after expiry - file CoR 9.2 (R30) only inside the "
                  "final month. Amending the MOI later is a CoR 15.2 filing (R80 minor / R250 other)."),
    },
    "certification": {
        "label": "SAQA qualification verification / registration",
        "authority": "South African Qualifications Authority",
        "steps": [
            "Certified copy of the qualification certificate and full academic transcript",
            "Certified copy of ID (foreigners: passport + sworn translation of documents)",
            "Completed SAQA application form for verification of a South African / foreign qualification",
            "Proof of payment of the SAQA fee",
            "Employer or institution confirmation letter where SAQA requests it",
        ],
        "notes": "SAQA verifies and registers qualifications on the National Learners' Records Database.",
    },
    "certificate": {
        "label": "Own branded certificate - internal file",
        "authority": "Issued under your own name and verification code",
        "steps": [
            "Holder's certified ID copy on file",
            "Evidence of competence: assessment record, training register or inspection report",
            "Scope statement (what the certificate covers and its limits)",
            "Expiry / review date decided and recorded",
        ],
        "notes": "Every certificate gets a public verification code and printable page at /cert/CODE.",
    },
}

DEFAULT_SERVICES = [
    ("Wireman's licence application pack", 450, "Annexure 5 pack: checklist, certified-doc set, experience letters, submission tracking to issue."),
    ("CIPC company registration pack", 350, "CoR 9.1 + CoR 14.1 + CoR 15.1A pack with director doc set and fee schedule."),
    ("SAQA qualification verification pack", 300, "Document set and application prepared for SAQA verification."),
    ("Branded certificate issuing", 150, "Certificate issued under your brand with public verification code and printable page."),
]


# ---------------------------------------------------------------- storage + Turso mirror
def _turso_enabled() -> bool:
    return TURSO_DB_URL.startswith("http") and bool(TURSO_AUTH_TOKEN)


def _turso_sql(q: str, params=None):
    args = []
    for v in params or []:
        if v is None:
            args.append({"type": "null"})
        elif isinstance(v, int):
            args.append({"type": "integer", "value": str(v)})
        else:
            args.append({"type": "text", "value": str(v)})
    r = httpx.post(TURSO_DB_URL.rstrip("/") + "/v2/pipeline",
                   json={"requests": [{"type": "execute", "stmt": {"sql": q, "args": args}}]},
                   headers={"Authorization": "Bearer " + TURSO_AUTH_TOKEN}, timeout=60)
    r.raise_for_status()
    res = (r.json().get("results") or [{}])[0]
    out = ((res.get("response") or {}).get("result")) or {}
    return [[(c or {}).get("value") for c in row] for row in (out.get("rows") or [])]


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def backup_now(force: bool = False) -> bool:
    global _last_backup
    if not _turso_enabled():
        return False
    now = time.time()
    if not force and now - _last_backup < 120:
        return False
    try:
        with _lock:
            con = sqlite3.connect(DB_PATH, timeout=20)
            try:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                con.close()
            blob = base64.b64encode(Path(DB_PATH).read_bytes()).decode()
        _turso_sql("CREATE TABLE IF NOT EXISTS reg_snapshot(blob TEXT, ts REAL)")
        _turso_sql("DELETE FROM reg_snapshot")
        _turso_sql("INSERT INTO reg_snapshot(blob, ts) VALUES (?, ?)", [blob, now])
        _last_backup = now
        return True
    except Exception:
        return False


def restore() -> None:
    """At boot: if the local registry file is gone (free hosts wipe disks), pull it back."""
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        return
    if not _turso_enabled():
        return
    try:
        rows = _turso_sql("SELECT blob FROM reg_snapshot ORDER BY ts DESC LIMIT 1")
        if rows and rows[0][0]:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            DB_PATH.write_bytes(base64.b64decode(rows[0][0]))
    except Exception:
        pass


def init() -> None:
    restore()
    with _lock, _connect() as con:
        con.executescript(SCHEMA)
        if not con.execute("SELECT COUNT(*) c FROM services").fetchone()["c"]:
            con.executemany("INSERT INTO services(name, price, descr, active) VALUES (?,?,?,1)",
                            DEFAULT_SERVICES)


# ---------------------------------------------------------------- helpers
def _rows(q: str, params=()) -> list:
    with _lock, _connect() as con:
        return [dict(r) for r in con.execute(q, params).fetchall()]


def _run(q: str, params=(), force_backup=False):
    with _lock, _connect() as con:
        con.execute(q, params)
        con.commit()
    threading.Thread(target=backup_now, kwargs={"force": force_backup}, daemon=True).start()


def _new_ref(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(2).upper()}-{int(time.time()) % 10000:04d}"


def get_kv(key: str, default: str = "") -> str:
    r = _rows("SELECT value FROM kv WHERE key=?", (key,))
    return r[0]["value"] if r else default


def set_kv(key: str, value: str) -> None:
    with _lock, _connect() as con:
        con.execute("INSERT INTO kv(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value))
        con.commit()
    threading.Thread(target=backup_now, kwargs={"force": True}, daemon=True).start()


SETTING_KEYS = ("owner_name", "owner_id", "owner_address", "owner_phone", "owner_email",
                "doel_email", "smtp_host", "smtp_port", "smtp_user", "smtp_pass", "smtp_from",
                "signature")


def settings_masked() -> dict:
    out = {k: get_kv(k) for k in SETTING_KEYS}
    out["smtp_pass"] = "••••••••" if get_kv("smtp_pass") else ""
    out["signature_set"] = bool(get_kv("signature"))
    return out


def build_pack_bytes(item: dict, docs: list) -> bytes:
    chk = CHECKLISTS.get(item["kind"], CHECKLISTS["certification"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        lines = [f"# {chk['label']} - application checklist", f"Authority: {chk['authority']}", ""]
        lines += [f"- [ ] {s}" for s in chk["steps"]]
        lines += ["", "Notes:", chk["notes"], ""]
        z.writestr("CHECKLIST.md", "\n".join(lines))
        summ = [f"Item: {item['title']}", f"Kind: {item['kind']}", f"Authority: {item['authority']}",
                f"Reference/number: {item['number'] or '-'}", f"Issued: {item['issued_on'] or '-'}",
                f"Expires: {item['expires_on'] or '-'}", f"Status: {item['status']}", "",
                f"Applicant: {get_kv('owner_name') or 'Ruwayne Campher'}",
                f"ID number: {get_kv('owner_id') or '-'}",
                f"Address: {get_kv('owner_address') or '-'}",
                f"Phone: {get_kv('owner_phone') or '-'}  Email: {get_kv('owner_email') or '-'}", "",
                f"Packed {time.strftime('%Y-%m-%d %H:%M')} - My AI Pro Registry"]
        z.writestr("SUMMARY.txt", "\n".join(summ))
        z.writestr("COVER-LETTER.txt", cover_letter(item))
        z.writestr("ANNEXURE-5- PREFILLED.txt", annexure5_text(item))
        for d in docs:
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", d["name"]) or "document"
            z.writestr(f"documents/{safe}", d["data"])
    return buf.getvalue()


def cover_letter(item: dict) -> str:
    chk = CHECKLISTS.get(item["kind"], CHECKLISTS["certification"])
    return f"""{time.strftime('%d %B %Y')}

The Chief Inspector - Occupational Health and Safety
Department of Employment and Labour
{get_kv('doel_email') or '(provincial office address)'}

Dear Sir / Madam,

APPLICATION: {item['title']} ({chk['label']})
Reference on file: {item['number'] or 'new application'}

I, {get_kv('owner_name') or 'Ruwayne Campher'} (ID {get_kv('owner_id') or '-'}), hereby submit the
attached complete application pack for the above matter, comprising:

{chr(10).join('- ' + s for s in chk['steps'])}

Enclosed: {('the documents listed in documents/ of this pack' )}.
I declare that the information and copies submitted are true and correct.

Yours faithfully,
{get_kv('owner_name') or 'Ruwayne Campher'}
{get_kv('owner_phone') or ''} {get_kv('owner_email') or ''}
"""


def annexure5_text(item: dict) -> str:
    """Annexure 5 (Regulation 11(1)) - Application for Registration as a Registered Person, prefilled."""
    cat = (item.get("notes") or "").upper()
    tick = lambda *ks: "X" if any(k in cat for k in ks) else "___"
    return f"""OCCUPATIONAL HEALTH AND SAFETY ACT, 1993 - REGULATION 11(1)
ELECTRICAL INSTALLATION REGULATIONS, 2009 - ANNEXURE 5
APPLICATION FOR REGISTRATION AS A REGISTERED PERSON (pre-filled by My AI Pro Registry)

1. Surname / full name:        {get_kv('owner_name') or '________________'}
2. Identity number:            {get_kv('owner_id') or '________________'}
3. Postal address:             {get_kv('owner_address') or '________________'}
4. Telephone / mobile:         {get_kv('owner_phone') or '________________'}
5. E-mail:                     {get_kv('owner_email') or '________________'}
6. Category applied for:
   [ {tick('ETSP', 'SINGLE')} ] Electrical Tester for Single Phase
   [ {tick('IE', 'INSTALLATION ELECTRICIAN')} ] Installation Electrician
   [ {tick('MIE', 'MASTER')} ] Master Installation Electrician
7. Current / previous registration number: {item.get('number') or 'none'}
8. Qualifications attached: trade test / National Certificate, N-certificate,
   Installation Rules Paper 1 & 2 results (see documents/)
9. Practical experience: see employer letters in documents/
10. Declaration: I declare the statements above and the attachments to be true.

Signature: ______________________   Date: {time.strftime('%Y-%m-%d')}
"""


def _sa_id_bits(idno: str):
    """Derive (date of birth, gender) from a 13-digit SA ID number."""
    d = re.sub(r"\D", "", idno or "")
    if len(d) != 13:
        return "", ""
    yy, mm, dd = int(d[0:2]), int(d[2:4]), int(d[4:6])
    year = yy + (1900 if yy > time.localtime().tm_year % 100 else 2000)
    return f"{year:04d}-{mm:02d}-{dd:02d}", ("Male" if int(d[6]) >= 5 else "Female")


def _traffic_form(request: Request, kind: str, code: str, ll: str, lldate: str) -> str:
    """Pre-filled LL1 / DL1 application (National Road Traffic Act 93 of 1996)."""
    s = {k: get_kv(k) for k in ("owner_name", "owner_id", "owner_address", "owner_phone", "owner_email")}
    name = (s.get("owner_name") or "").strip()
    forenames, _, surname = name.rpartition(" ")
    if not surname:
        surname, forenames = name, ""
    dob, gender = _sa_id_bits(s.get("owner_id", ""))
    sig = get_kv("signature")
    sigimg = f'<img class="sig" src="{sig}" alt="signature">' if sig else ""
    is_ll = kind == "LL1"
    disq = "learner's licence" if is_ll else "driving licence"
    hold = "" if is_ll else " I hold a valid learner's licence for the code of vehicle in respect of which this application is made."
    photos = "3" if is_ll else "4"
    title = ("APPLICATION FOR A LEARNER'S LICENCE (FORM LL1)" if is_ll
             else "APPLICATION FOR A DRIVING LICENCE (FORM DL1)")
    extra = "" if is_ll else f"""
<div class="frow"><div class="fbox"><label>Learner's licence number</label><div class="val">{ll or '________________'}</div></div>
<div class="fbox"><label>Date learner's licence obtained</label><div class="val">{lldate or '____-____-______'}</div></div></div>"""
    code_label = "Code of vehicle for which learner's licence is required" if is_ll else \
                 "Code of driving licence applied for"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{kind} - pre-filled</title>
<style>@page{{size:A4;margin:14mm}}body{{margin:0;background:#eef0f7;font-family:system-ui,sans-serif;color:#1c2033}}
.sheet{{max-width:820px;margin:24px auto;background:#fff;border:1px solid #c9cde4;padding:44px 50px}}
.h{{font:800 15px/1.4 system-ui;letter-spacing:.06em;text-transform:uppercase;text-align:center}}
.sub{{font:12px/1.5 system-ui;color:#3c4160;text-align:center;margin:4px 0 22px}}
.frow{{display:flex;gap:14px;margin-bottom:12px}} .fbox{{flex:1;border:1px solid #9aa0c0;padding:8px 12px}}
label{{display:block;font:10px/1.3 system-ui;text-transform:uppercase;letter-spacing:.06em;color:#64698a}}
.val{{font:14px/1.4 system-ui;margin-top:3px;min-height:18px}}
.dec{{border:1px solid #9aa0c0;padding:12px 14px;font:12.5px/1.6 system-ui;margin:16px 0}}
.sigrow{{display:flex;align-items:flex-end;gap:24px;margin-top:30px}}
.sig{{height:64px;display:block}} .sline{{flex:1;max-width:280px;border-top:1.5px solid #1c2033;padding-top:5px;font:11.5px/1.4 system-ui;color:#3c4160}}
.office{{border:1.5px dashed #9aa0c0;padding:12px 14px;font:11px/1.6 system-ui;color:#64698a;margin-top:26px}}
.note{{font:10.5px/1.5 system-ui;color:#8a8fa8;margin-top:14px}}
button{{position:fixed;top:14px;right:14px;font:600 14px system-ui;padding:10px 16px;border-radius:10px;border:1px solid #5b5bd6;background:#5b5bd6;color:#fff;cursor:pointer}}
@media print{{button{{display:none}}body{{background:#fff}}.sheet{{margin:0;border:none}}}}</style></head>
<body><button onclick="window.print()">Print / save PDF</button>
<div class="sheet">
<div class="h">Republic of South Africa &middot; {title}</div>
<div class="sub">National Road Traffic Act, 1996 (Act 93 of 1996) &middot; National Road Traffic Regulations, 2000 &middot; pre-filled by My AI Pro Registry</div>
<div class="frow"><div class="fbox"><label>Surname</label><div class="val">{surname}</div></div>
<div class="fbox"><label>First names</label><div class="val">{forenames}</div></div></div>
<div class="frow"><div class="fbox"><label>Identity number</label><div class="val">{s.get('owner_id','')}</div></div>
<div class="fbox"><label>Date of birth</label><div class="val">{dob}</div></div>
<div class="fbox"><label>Gender</label><div class="val">{gender}</div></div></div>
<div class="frow"><div class="fbox"><label>Residential address</label><div class="val">{s.get('owner_address','')}</div></div></div>
<div class="frow"><div class="fbox"><label>Postal address</label><div class="val">{s.get('owner_address','')}</div></div></div>
<div class="frow"><div class="fbox"><label>Cellphone</label><div class="val">{s.get('owner_phone','')}</div></div>
<div class="fbox"><label>E-mail</label><div class="val">{s.get('owner_email','')}</div></div></div>
{extra}
<div class="frow"><div class="fbox"><label>{code_label}</label><div class="val">{code}</div></div>
<div class="fbox"><label>Place</label><div class="val">______________________</div></div>
<div class="fbox"><label>Date</label><div class="val">____-____-______</div></div></div>
<div class="dec">I declare that the particulars furnished by me in this application are true and correct in every respect, and that
I am not disqualified from holding a {disq} of the code applied for.{hold}</div>
<div class="sigrow"><div>{sigimg}<div class="sline">Signature of applicant</div></div></div>
<div class="office">OFFICE USE &mdash; DLTC: eye test result &middot; photographs received &middot; fee received R______ &middot; receipt no. __________ &middot;
test date __________ &middot; examiner __________ &middot; result: pass / fail</div>
<div class="note">Convenience reproduction pre-filled from the owner's registry profile &mdash; submit together with (or transcribed onto) the
official form at your Driving Licence Testing Centre, or via the NaTIS Online booking at online.natis.gov.za.
Bring: original ID, {photos} black-and-white ID photos, eye test certificate (&lt;3 months), booking fee.</div>
</div></body></html>"""


def _vehicle_form(request: Request, kind: str, v: dict) -> str:
    """Pre-filled ALV (licensing/disc) or ARC (registration/RC1) application."""
    s = {k: get_kv(k) for k in ("owner_name", "owner_id", "owner_address", "owner_phone", "owner_email")}
    name = (s.get("owner_name") or "").strip()
    forenames, _, surname = name.rpartition(" ")
    if not surname:
        surname, forenames = name, ""
    dob, gender = _sa_id_bits(s.get("owner_id", ""))
    sig = get_kv("signature")
    sigimg = f'<img class="sig" src="{sig}" alt="signature">' if sig else ""
    is_alv = kind == "ALV"
    title = ("APPLICATION FOR LICENSING OF A MOTOR VEHICLE (FORM ALV)" if is_alv
             else "APPLICATION FOR REGISTRATION OF A MOTOR VEHICLE (FORM ARC / RC1)")
    lic = f"""<div class="frow"><div class="fbox"><label>Current licence disc expires</label><div class="val">{v.get('exp') or '____-____-______'}</div></div>
<div class="fbox"><label>Period applied for</label><div class="val">12 months</div></div></div>""" if is_alv else \
          """<div class="frow"><div class="fbox"><label>Registration number applied for (office allocates)</label><div class="val">____________________</div></div>
<div class="fbox"><label>Title deed / ownership proof</label><div class="val">attached</div></div></div>"""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{kind} - pre-filled</title>
<style>@page{{size:A4;margin:14mm}}body{{margin:0;background:#eef0f7;font-family:system-ui,sans-serif;color:#1c2033}}
.sheet{{max-width:820px;margin:24px auto;background:#fff;border:1px solid #c9cde4;padding:44px 50px}}
.h{{font:800 15px/1.4 system-ui;letter-spacing:.06em;text-transform:uppercase;text-align:center}}
.sub{{font:12px/1.5 system-ui;color:#3c4160;text-align:center;margin:4px 0 22px}}
.frow{{display:flex;gap:14px;margin-bottom:12px}} .fbox{{flex:1;border:1px solid #9aa0c0;padding:8px 12px}}
label{{display:block;font:10px/1.3 system-ui;text-transform:uppercase;letter-spacing:.06em;color:#64698a}}
.val{{font:14px/1.4 system-ui;margin-top:3px;min-height:18px}}
.dec{{border:1px solid #9aa0c0;padding:12px 14px;font:12.5px/1.6 system-ui;margin:16px 0}}
.sigrow{{display:flex;align-items:flex-end;gap:24px;margin-top:30px}}
.sig{{height:64px;display:block}} .sline{{flex:1;max-width:280px;border-top:1.5px solid #1c2033;padding-top:5px;font:11.5px/1.4 system-ui;color:#3c4160}}
.office{{border:1.5px dashed #9aa0c0;padding:12px 14px;font:11px/1.6 system-ui;color:#64698a;margin-top:26px}}
.note{{font:10.5px/1.5 system-ui;color:#8a8fa8;margin-top:14px}}
button{{position:fixed;top:14px;right:14px;font:600 14px system-ui;padding:10px 16px;border-radius:10px;border:1px solid #5b5bd6;background:#5b5bd6;color:#fff;cursor:pointer}}
@media print{{button{{display:none}}body{{background:#fff}}.sheet{{margin:0;border:none}}}}</style></head>
<body><button onclick="window.print()">Print / save PDF</button>
<div class="sheet">
<div class="h">Republic of South Africa &middot; {title}</div>
<div class="sub">National Road Traffic Act, 1996 (Act 93 of 1996) &middot; National Road Traffic Regulations, 2000 &middot; pre-filled by My AI Pro Registry</div>
<div class="frow"><div class="fbox"><label>Title holder - surname</label><div class="val">{surname}</div></div>
<div class="fbox"><label>First names</label><div class="val">{forenames}</div></div>
<div class="fbox"><label>Identity number</label><div class="val">{s.get('owner_id','')}</div></div></div>
<div class="frow"><div class="fbox"><label>Residential address</label><div class="val">{s.get('owner_address','')}</div></div>
<div class="fbox"><label>Cellphone</label><div class="val">{s.get('owner_phone','')}</div></div></div>
<div class="frow"><div class="fbox"><label>Registration number</label><div class="val">{v.get('reg') or '________________'}</div></div>
<div class="fbox"><label>VIN / chassis number</label><div class="val">{v.get('vin') or '__________________'}</div></div></div>
<div class="frow"><div class="fbox"><label>Make</label><div class="val">{v.get('make') or '__________'}</div></div>
<div class="fbox"><label>Model</label><div class="val">{v.get('model') or '__________'}</div></div>
<div class="fbox"><label>Year model</label><div class="val">{v.get('year') or '______'}</div></div>
<div class="fbox"><label>Tare (kg)</label><div class="val">{v.get('tare') or '______'}</div></div></div>
{lic}
<div class="frow"><div class="fbox"><label>Place</label><div class="val">______________________</div></div>
<div class="fbox"><label>Date</label><div class="val">____-____-______</div></div></div>
<div class="dec">I declare that I am the title holder of the motor vehicle described above, that the particulars furnished are
true and correct in every respect, and that the vehicle complies with the requirements of the National Road Traffic Act, 1996.</div>
<div class="sigrow"><div>{sigimg}<div class="sline">Signature of title holder</div></div></div>
<div class="office">OFFICE USE &mdash; NaTIS: register entry / RC1 no. __________ &middot; licence fee received R______ &middot; receipt no. __________ &middot;
disc / registration issued __________ &middot; officer __________</div>
<div class="note">Convenience reproduction pre-filled from the owner's registry profile &mdash; submit with (or transcribe onto) the
official form at your DLTC / registering authority, or via online.natis.gov.za where the province supports it.
Bring: original ID, proof of ownership / sale invoice, proof of address, and the applicable fee (tariff based on tare mass).</div>
</div></body></html>"""


def smtp_send(subject: str, body: str, attach_name: str, attach_bytes: bytes) -> str:
    host, port = get_kv("smtp_host"), int(get_kv("smtp_port") or "587")
    user, pw, frm = get_kv("smtp_user"), get_kv("smtp_pass"), get_kv("smtp_from") or get_kv("smtp_user")
    to = get_kv("doel_email")
    if not (host and user and pw and to):
        raise RuntimeError("SMTP or DoEL e-mail not configured in the Submission tab yet.")
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))
    part = MIMEApplication(attach_bytes, Name=attach_name)
    part["Content-Disposition"] = f'attachment; filename="{attach_name}"'
    msg.attach(part)
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(frm, [to], msg.as_string())
    return f"sent via {host} to {to}"


# ---------------------------------------------------------------- registration
def register(app, require_admin, bank_info) -> None:
    init()

    # ---------------- pages
    @app.get("/registry", response_class=HTMLResponse)
    def registry_page():
        return Response(content=(Path(__file__).parent / "static" / "registry.html").read_bytes(),
                        media_type="text/html; charset=utf-8")

    @app.get("/services", response_class=HTMLResponse)
    def services_page():
        return Response(content=(Path(__file__).parent / "static" / "services.html").read_bytes(),
                        media_type="text/html; charset=utf-8")

    @app.get("/verify/{code}", response_class=HTMLResponse)
    def verify_page(code: str):
        c = _rows("SELECT * FROM certs WHERE code=?", (code.upper(),))
        cert = c[0] if c else None
        state = "VOID" if (cert and cert["voided"]) else ("VALID" if cert else "NOT FOUND")
        colour = "#1f9468" if state == "VALID" else "#cf4040"
        body = ""
        if cert:
            body = (f"<p><b>Holder:</b> {cert['holder']}</p><p><b>Certificate:</b> {cert['ctype']}</p>"
                    f"<p><b>Issued:</b> {cert['issued_on'] or '-'} &nbsp; <b>Expires:</b> {cert['expires_on'] or 'no expiry'}</p>"
                    f"<p><b>Scope:</b> {cert['body'] or '-'}</p>")
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Verify {code}</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f7fc;font:16px/1.7 system-ui,sans-serif;color:#181b2e}}
main{{max-width:560px;margin:24px;background:#fff;border:1px solid #e3e4ef;border-radius:20px;padding:28px;box-shadow:0 10px 28px rgba(20,22,44,.07)}}
h1{{font-size:20px;margin:0 0 4px}} .st{{display:inline-block;padding:3px 12px;border-radius:99px;color:#fff;background:{colour};font-weight:700;font-size:13px}}
code{{font-family:ui-monospace,monospace;background:#f4f4fa;border-radius:6px;padding:2px 6px}}</style></head>
<body><main><h1>Certificate verification</h1><p><code>{code.upper()}</code> &nbsp;<span class="st">{state}</span></p>{body}
<p style="color:#64698a;font-size:13px">Issued under the name of Ruwayne Campher - My AI Pro Registry.
Questions: 1109ruwayne@gmail.com</p></main></body></html>""")

    @app.get("/cert/{code}", response_class=HTMLResponse)
    def cert_page(code: str):
        c = _rows("SELECT * FROM certs WHERE code=?", (code.upper(),))
        if not c or c[0]["voided"]:
            raise HTTPException(404, "Certificate not found or void.")
        cert = c[0]
        sig = get_kv("signature")
        signature_html = (f'<img class="sigimg" src="{sig}" alt="signature">' if sig
                          else '<div class="script">Ruwayne Campher</div>')
        ring = "RUWAYNE CAMPHER &#8226; MY AI PRO REGISTRY &#8226; REPUBLIC OF SOUTH AFRICA &#8226; "
        stamp_svg = f"""<svg class="stamp" viewBox="0 0 200 200" role="img" aria-label="verification stamp">
<defs><path id="ring{cert['code']}" d="M100,100 m-72,0 a72,72 0 1,1 144,0 a72,72 0 1,1 -144,0"/></defs>
<circle cx="100" cy="100" r="88" fill="none" stroke="#1f3f8f" stroke-width="3"/>
<circle cx="100" cy="100" r="60" fill="none" stroke="#1f3f8f" stroke-width="1.6"/>
<text font-size="10.5" fill="#1f3f8f" font-family="system-ui,sans-serif" font-weight="700" letter-spacing="1.5">
<textPath href="#ring{cert['code']}">{ring}</textPath></text>
<text x="100" y="88" text-anchor="middle" font-family="system-ui,sans-serif" font-size="15" font-weight="800" fill="#1f3f8f">VERIFIED</text>
<text x="100" y="106" text-anchor="middle" font-family="ui-monospace,monospace" font-size="11" fill="#1f3f8f">{cert['code']}</text>
<text x="100" y="121" text-anchor="middle" font-family="system-ui,sans-serif" font-size="9" fill="#1f3f8f">{cert['issued_on'] or ''}</text>
</svg>"""
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Certificate {cert['code']}</title>
<style>@page{{size:A4 landscape;margin:14mm}}body{{margin:0;background:#eef0f7;font-family:Georgia,'Times New Roman',serif;color:#1c2033}}
.sheet{{max-width:1000px;margin:24px auto;background:#fff;border:10px double #5b5bd6;padding:48px 56px;text-align:center}}
.brand{{font:700 13px/1.4 system-ui;letter-spacing:.28em;text-transform:uppercase;color:#5b5bd6}}
h1{{font-size:34px;margin:26px 0 6px;letter-spacing:.02em}} .holder{{font-size:26px;font-style:italic;margin:18px 0 6px}}
.type{{font-size:17px;margin:0 0 20px}} .scope{{max-width:760px;margin:0 auto 26px;font-size:14.5px;line-height:1.7;color:#3c4160}}
.meta{{display:flex;justify-content:space-between;gap:20px;font:12.5px/1.6 system-ui;color:#64698a;margin-top:34px}}
.sig{{margin-top:12px;display:flex;justify-content:space-between;gap:40px;font:13px/1.5 system-ui}}
.sigcol{{flex:1}} .sigruled{{border-top:1.5px solid #1c2033;padding-top:6px}}
.sigslot{{height:72px;display:flex;align-items:flex-end;justify-content:center;margin-bottom:4px}}
.sigslot .sigimg{{height:64px;margin:0}} .sigslot .script{{font-size:26px;margin:0}}
.signrow{{display:flex;justify-content:space-between;align-items:flex-end;gap:30px;margin-top:38px}}
.sigblock{{flex:1;text-align:left}} .sigline{{font:12.5px/1.4 system-ui;color:#3c4160;border-top:1.5px solid #1c2033;padding-top:6px;max-width:320px}}
.sigimg{{height:88px;display:block;margin-bottom:6px}}
.script{{font-family:'Segoe Script','Brush Script MT','Comic Sans MS',cursive;font-size:34px;color:#14265c;transform:rotate(-3deg);margin:0 0 6px}}
.stampblock{{flex:none}} .stamp{{width:168px;height:168px;opacity:.92;transform:rotate(-8deg)}}
.qrblock{{flex:none;text-align:center}} .qr{{width:100px;height:100px;display:block;margin:0 auto}} .qrcap{{font:10px/1.4 system-ui;color:#64698a;margin-top:4px}}
.fp{{font:10.5px/1.5 ui-monospace,monospace;color:#8a8fa8;margin-top:20px;word-break:break-all}}
button{{position:fixed;top:14px;right:14px;font:600 14px system-ui;padding:10px 16px;border-radius:10px;border:1px solid #5b5bd6;background:#5b5bd6;color:#fff;cursor:pointer}}
@media print{{button{{display:none}}body{{background:#fff}}.sheet{{margin:0;border-width:8px}}}}</style></head>
<body><button onclick="window.print()">Print / save PDF</button>
<div class="sheet"><div class="brand">Ruwayne Campher &middot; Republic of South Africa</div>
<h1>CERTIFICATE</h1>
<p class="holder">{cert['holder']}</p>
<p class="type">is hereby awarded: <b>{cert['ctype']}</b></p>
<p class="scope">{cert['body'] or ''}</p>
<div class="meta"><span>Certificate no. <b>{cert['code']}</b></span><span>Issued {cert['issued_on'] or '-'}</span>
<span>{('Valid until ' + cert['expires_on']) if cert['expires_on'] else 'No expiry date'}</span></div>
<div class="signrow">
  <div class="sigblock">{signature_html}<div class="sigline">Ruwayne Campher - issuer &amp; registered verifier</div></div>
  <div class="qrblock"><img class="qr" src="/cert/{cert['code']}/qr.svg" alt="verification QR code"><div class="qrcap">Scan for live verification</div></div>
  <div class="stampblock">{stamp_svg}</div>
</div>
<div class="fp">Credential fingerprint (SHA-256): {_fingerprint(cert)} &middot; machine verification: GET /api/reg/verify/{cert['code']} &middot; Open Badges 3.0: /api/reg/badge/{cert['code']}</div>
<div class="sig"><div class="sigcol"><div class="sigslot">{signature_html}</div><div class="sigruled">Signature as above</div></div><div class="sigcol"><div class="sigslot"></div><div class="sigruled">Verify at /verify/{cert['code']}</div></div></div>
</div></body></html>""")

    # ---------------- public API
    @app.get("/api/reg/services")
    def pub_services():
        return {"services": _rows("SELECT id,name,price,descr FROM services WHERE active=1 ORDER BY id"),
                "bank": bank_info()}

    @app.post("/api/reg/orders")
    async def pub_order(request: Request):
        body = await request.json()
        sid = int(body.get("service_id") or 0)
        svc = _rows("SELECT * FROM services WHERE id=? AND active=1", (sid,))
        if not svc:
            raise HTTPException(400, "Choose a service first.")
        client = str(body.get("client") or "").strip()[:80]
        contact = str(body.get("contact") or "").strip()[:120]
        if not client or not contact:
            raise HTTPException(400, "Your name and a contact (email or phone) are required.")
        ref = _new_ref("RC")
        _run("INSERT INTO orders(ref, client, contact, service, amount, status, created, verify_until)"
             " VALUES (?,?,?,?,?,?,?,0)",
             (ref, client, contact, svc[0]["name"], svc[0]["price"], "awaiting-payment", time.time()))
        return {"ok": True, "ref": ref, "amount": svc[0]["price"], "bank": bank_info(),
                "note": "Pay by EFT with this reference, then confirm below. The owner approves each payment."}

    @app.post("/api/reg/orders/confirm")
    async def pub_confirm(request: Request):
        ref = str((await request.json()).get("ref") or "").strip().upper()
        o = _rows("SELECT * FROM orders WHERE ref=?", (ref,))
        if not o:
            raise HTTPException(404, "Reference not found.")
        if o[0]["status"] not in ("awaiting-payment",):
            return {"ok": True, "status": o[0]["status"]}
        _run("UPDATE orders SET status='verifying', verify_until=? WHERE ref=?",
             (time.time() + 3 * 3600, ref), force_backup=True)
        return {"ok": True, "status": "verifying",
                "note": "Marked as paid - the owner is confirming. Work starts immediately and your order stays active while it is verified."}

    @app.get("/api/reg/verify/{code}")
    def pub_verify(code: str, request: Request):
        base = str(request.base_url).rstrip("/")
        c = _rows("SELECT code,holder,ctype,issued_on,expires_on,voided FROM certs WHERE code=?", (code.upper(),))
        if not c:
            return JSONResponse({"valid": False, "state": "not-found"}, headers=_CORS)
        c = c[0]
        return JSONResponse({"valid": not c["voided"], "state": "void" if c["voided"] else "valid",
                "holder": c["holder"], "type": c["ctype"], "issued": c["issued_on"], "expires": c["expires_on"],
                "fingerprint": _fingerprint(c),
                "issuer": base + "/api/reg/issuer",
                "badge": base + "/api/reg/badge/" + c["code"],
                "qr": base + "/cert/" + c["code"] + "/qr.svg",
                "acceptance_letter": base + "/cert/" + c["code"] + "/letter",
                "human_check": base + "/verify/" + c["code"]}, headers=_CORS)

    @app.get("/api/reg/issuer")
    def pub_issuer(request: Request):
        base = str(request.base_url).rstrip("/")
        return JSONResponse({"@context": "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json",
            "id": base + "/api/reg/issuer", "type": ["Profile"],
            "name": "Ruwayne Campher - My AI Pro Registry",
            "url": base + "/registry",
            "address": "Republic of South Africa",
            "description": ("Private certification and verification register of Ruwayne Campher. Every credential it issues is "
                            "publicly verifiable by humans, by machine (open JSON API, CORS-enabled) and as an Open Badges 3.0 "
                            "credential carrying a SHA-256 integrity fingerprint."),
            "verification": {"human": base + "/verify/", "api": base + "/api/reg/verify/",
                             "badge": base + "/api/reg/badge/", "trust_policy": base + "/trust"}}, headers=_CORS)

    @app.get("/api/reg/badge/{code}")
    def pub_badge(code: str, request: Request):
        base = str(request.base_url).rstrip("/")
        c = _rows("SELECT code,holder,ctype,body,issued_on,expires_on,voided FROM certs WHERE code=?", (code.upper(),))
        if not c:
            return JSONResponse({"valid": False, "state": "not-found"}, status_code=404, headers=_CORS)
        cert = c[0]
        if cert["voided"]:
            return JSONResponse({"valid": False, "state": "void"}, status_code=410, headers=_CORS)
        cred = {"@context": ["https://www.w3.org/ns/credentials/v2",
                             "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json"],
                "id": base + "/api/reg/badge/" + cert["code"],
                "type": ["VerifiableCredential", "OpenBadgeCredential"],
                "name": cert["ctype"],
                "issuer": {"id": base + "/api/reg/issuer", "type": ["Profile"],
                           "name": "Ruwayne Campher - My AI Pro Registry"},
                "validFrom": (cert["issued_on"] or "2026-01-01") + "T00:00:00Z",
                "credentialSubject": {"type": ["AchievementSubject"], "name": cert["holder"],
                    "achievement": {"id": base + "/api/reg/badge/" + cert["code"], "type": ["Achievement"],
                        "name": cert["ctype"], "description": cert["body"] or "",
                        "criteria": {"narrative": "Live verification: " + base + "/verify/" + cert["code"] +
                                     " (human) or " + base + "/api/reg/verify/" + cert["code"] + " (machine)."}}}}
        if cert["expires_on"]:
            cred["expirationDate"] = cert["expires_on"] + "T23:59:59Z"
        cred["proof"] = {"type": "Sha256DigestProof", "proofPurpose": "assertionMethod",
                         "created": (cert["issued_on"] or "") + "T00:00:00Z",
                         "digestFields": ["code", "holder", "ctype", "issued_on", "expires_on"],
                         "digest": _fingerprint(cert)}
        return JSONResponse(cred, headers=_CORS)

    @app.get("/cert/{code}/qr.svg")
    def cert_qr(code: str, request: Request):
        c = _rows("SELECT code,voided FROM certs WHERE code=?", (code.upper(),))
        if not c:
            raise HTTPException(404, "Certificate not found.")
        base = str(request.base_url).rstrip("/")
        img = qrcode.make(base + "/verify/" + c[0]["code"], image_factory=SvgPathImage, box_size=6, border=2)
        buf = io.BytesIO(); img.save(buf)
        return Response(content=buf.getvalue(), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400", **_CORS})

    @app.get("/cert/{code}/letter", response_class=HTMLResponse)
    def cert_letter(code: str, request: Request):
        c = _rows("SELECT * FROM certs WHERE code=?", (code.upper(),))
        if not c or c[0]["voided"]:
            raise HTTPException(404, "Certificate not found or void.")
        cert = c[0]; base = str(request.base_url).rstrip("/")
        sig = get_kv("signature")
        sigimg = f'<img class="sigimg" src="{sig}" alt="signature">' if sig else '<div class="script">Ruwayne Campher</div>'
        fp = _fingerprint(cert)
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Verification &amp; Acceptance Letter {cert['code']}</title>
<style>@page{{size:A4;margin:18mm}}body{{margin:0;background:#eef0f7;font-family:Georgia,serif;color:#1c2033}}
.sheet{{max-width:760px;margin:24px auto;background:#fff;border:1px solid #c9cde4;padding:52px 58px;line-height:1.65}}
.head{{font:700 12px/1.4 system-ui;letter-spacing:.26em;text-transform:uppercase;color:#5b5bd6}}
h1{{font-size:22px;margin:14px 0 4px}} .sub{{font-size:13px;color:#64698a;margin:0 0 26px}}
p{{font-size:14px;margin:0 0 14px}} .box{{border:1px solid #c9cde4;background:#f7f8fd;padding:14px 18px;font:12.5px/1.7 ui-monospace,monospace;margin:0 0 16px;word-break:break-all}}
.ch{{font:700 12px system-ui;text-transform:uppercase;letter-spacing:.08em;color:#1f3f8f;margin:22px 0 6px}}
.sigrow{{margin-top:44px;display:flex;align-items:flex-end;gap:26px}}
.sigimg{{height:74px;display:block}} .script{{font-family:'Segoe Script',cursive;font-size:28px;color:#14265c}}
.sigline{{border-top:1.5px solid #1c2033;padding-top:6px;font:12.5px/1.4 system-ui;color:#3c4160;flex:1;max-width:300px}}
.qr{{width:104px;height:104px}} .qrcap{{font:10px system-ui;color:#64698a;text-align:center;margin-top:4px}}
button{{position:fixed;top:14px;right:14px;font:600 14px system-ui;padding:10px 16px;border-radius:10px;border:1px solid #5b5bd6;background:#5b5bd6;color:#fff;cursor:pointer}}
@media print{{button{{display:none}}body{{background:#fff}}.sheet{{margin:0;border:none}}}}</style></head>
<body><button onclick="window.print()">Print / save PDF</button>
<div class="sheet">
<div class="head">Ruwayne Campher &middot; My AI Pro Registry &middot; Republic of South Africa</div>
<h1>Letter of Verification &amp; Direct Acceptance</h1>
<p class="sub">Certificate {cert['code']} &middot; issued {cert['issued_on'] or '-'}{(' &middot; valid until ' + cert['expires_on']) if cert['expires_on'] else ''}</p>
<p>To the admissions office, human-resources department, licensing authority or other verifying body:</p>
<p><b>{cert['holder']}</b> holds the credential <b>{cert['ctype']}</b> issued and certified by Ruwayne Campher, issuer and registered
verifier of record. {cert['body'] or ''}</p>
<p>This credential is offered for <b>direct acceptance</b>. Its authenticity can be confirmed instantly, without correspondence,
through any of the following channels, each of which answers from the register of record in real time:</p>
<div class="ch">1 &middot; Machine verification (open JSON API, CORS-enabled)</div>
<div class="box">GET {base}/api/reg/verify/{cert['code']}</div>
<div class="ch">2 &middot; Open Badges 3.0 / Verifiable Credential</div>
<div class="box">GET {base}/api/reg/badge/{cert['code']}<br>issuer profile: {base}/api/reg/issuer</div>
<div class="ch">3 &middot; Human verification page &amp; QR code</div>
<div class="box">{base}/verify/{cert['code']}</div>
<div class="ch">Integrity fingerprint (SHA-256 of code, holder, type, issue &amp; expiry)</div>
<div class="box">{fp}</div>
<p>A response of <b>"valid": true</b> (or a page marked VERIFIED) confirms the credential as genuine and unaltered; the
fingerprint above must match the API response. Trust policy, issuer identity and acceptance procedure: {base}/trust.</p>
<p>Certified correct on {cert['issued_on'] or '-'}.</p>
<div class="sigrow"><div>{sigimg}<div class="sigline">Ruwayne Campher - issuer &amp; registered verifier</div></div>
<div><img class="qr" src="{base}/cert/{cert['code']}/qr.svg" alt="verify QR"><div class="qrcap">scan = live verification</div></div></div>
</div></body></html>""")

    @app.get("/trust", response_class=HTMLResponse)
    def trust_page(request: Request):
        base = str(request.base_url).rstrip("/")
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Trust &amp; Acceptance Policy - My AI Pro Registry</title>
<style>body{{margin:0;background:#0f1222;color:#e8eaf6;font-family:system-ui,sans-serif;line-height:1.7}}
.wrap{{max-width:860px;margin:0 auto;padding:56px 28px}} h1{{font-size:30px;margin:0 0 6px}} h2{{font-size:17px;color:#9aa4ff;margin:34px 0 8px}}
.k{{color:#8b93b8;font-size:13px}} code,pre{{background:#181c33;border:1px solid #2a2f52;border-radius:8px;padding:2px 6px;font-size:12.5px}}
pre{{padding:12px 14px;overflow:auto}} li{{margin:6px 0}} a{{color:#9aa4ff}}</style></head><body><div class="wrap">
<h1>Trust &amp; Acceptance Policy</h1>
<div class="k">My AI Pro Registry &middot; Ruwayne Campher &middot; Republic of South Africa &middot; &copy; 2026</div>
<h2>1 &middot; Issuer</h2>
<p>Credentials are issued by <b>Ruwayne Campher</b>, owner and registered verifier of this private register
(<a href="{base}/registry">console</a>, owner-gated). Each credential carries the issuer's handwritten signature and the
register's verification seal, and is recorded with issue date, scope and expiry.</p>
<h2>2 &middot; Direct acceptance - how to verify any credential instantly</h2>
<ul>
<li><b>Human:</b> <code>{base}/verify/CODE</code> - VERIFIED / VOID status page.</li>
<li><b>Machine:</b> <code>GET {base}/api/reg/verify/CODE</code> - open JSON, CORS <code>*</code>, no key required:
<pre>curl {base}/api/reg/verify/RC-2026-0000</pre></li>
<li><b>Standards:</b> <code>GET {base}/api/reg/badge/CODE</code> - Open Badges 3.0 / W3C Verifiable Credential JSON-LD with
SHA-256 integrity proof; issuer profile at <code>{base}/api/reg/issuer</code>.</li>
<li><b>Print:</b> every certificate page and its Letter of Verification &amp; Direct Acceptance
(<code>{base}/cert/CODE/letter</code>) carry a QR code resolving to the live human check.</li>
</ul>
<h2>3 &middot; Integrity</h2>
<p>Each credential's fingerprint is SHA-256 over <code>code|holder|type|issued|expires</code>. A credential whose API
fingerprint differs from the printed one must be treated as altered. Voided credentials answer <code>"valid": false</code>
everywhere, instantly and permanently.</p>
<h2>4 &middot; Privacy (POPIA)</h2>
<p>Only the holder's name, credential type, dates and code are published - the minimum necessary for verification.
Third-party verification of another person's record elsewhere (e.g. SAQA NLRD) is performed only with that person's
written consent, retained with the vault item.</p>
<h2>5 &middot; Statutory recognition pathway</h2>
<p>This register is a private certification instrument. Where a credential falls under a statutory regime
(DoEL Registered Person, CIPC, SAQA NQF), the register additionally prepares and transmits the statutory application
pack (Annexure 5, CoR forms, SAQA verification requests) through the official channels; recognition by those bodies
follows their own application process, tracked in the owner console.</p>
<h2>6 &middot; Contact &amp; abuse</h2>
<p>Verification disputes: quote the certificate code and fingerprint via the owner console. Uptime: public endpoints are
unauthenticated by design so that any institution's systems can call them directly.</p>
</div></body></html>""")

    # ---------------- owner API
    @app.get("/api/reg/overview")
    def ov(request: Request):
        require_admin(request)
        items = _rows("SELECT * FROM items ORDER BY created DESC")
        for it in items:
            it["docs"] = _rows("SELECT id,item_id,name,mime,size,created FROM docs WHERE item_id=? ORDER BY created", (it["id"],))
        return {"items": items,
                "certs": _rows("SELECT * FROM certs ORDER BY created DESC"),
                "orders": _rows("SELECT * FROM orders ORDER BY created DESC"),
                "services": _rows("SELECT * FROM services ORDER BY id"),
                "submissions": _rows("SELECT * FROM submissions ORDER BY created DESC"),
                "settings": settings_masked(),
                "checklists": CHECKLISTS}

    @app.post("/api/reg/items")
    async def add_item(request: Request):
        require_admin(request)
        b = await request.json()
        kind = b.get("kind") if b.get("kind") in CHECKLISTS else "certification"
        _run("INSERT INTO items(kind,title,authority,number,issued_on,expires_on,status,notes,created)"
             " VALUES (?,?,?,?,?,?,?,?,?)",
             (kind, str(b.get("title") or "Untitled")[:120], str(b.get("authority") or CHECKLISTS[kind]["authority"])[:160],
              str(b.get("number") or "")[:60], str(b.get("issued_on") or "")[:20], str(b.get("expires_on") or "")[:20],
              str(b.get("status") or "active")[:30], str(b.get("notes") or "")[:2000], time.time()),
             force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/items/{iid}")
    async def edit_item(request: Request, iid: int):
        require_admin(request)
        b = await request.json()
        _run("UPDATE items SET title=?, number=?, issued_on=?, expires_on=?, status=?, notes=? WHERE id=?",
             (str(b.get("title") or "")[:120], str(b.get("number") or "")[:60], str(b.get("issued_on") or "")[:20],
              str(b.get("expires_on") or "")[:20], str(b.get("status") or "")[:30], str(b.get("notes") or "")[:2000], iid),
             force_backup=True)
        return {"ok": True}

    @app.delete("/api/reg/items/{iid}")
    def del_item(request: Request, iid: int):
        require_admin(request)
        _run("DELETE FROM docs WHERE item_id=?", (iid,))
        _run("DELETE FROM items WHERE id=?", (iid,), force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/docs")
    async def add_doc(request: Request, item_id: int = 0, file: UploadFile = File(...)):
        require_admin(request)
        data = await file.read()
        if len(data) > MAX_DOC:
            raise HTTPException(413, "Document too large (15 MB max).")
        _run("INSERT INTO docs(item_id,name,mime,size,data,created) VALUES (?,?,?,?,?,?)",
             (item_id or None, (file.filename or "document")[:160], (file.content_type or "")[:60],
              len(data), data, time.time()), force_backup=True)
        return {"ok": True, "size": len(data)}

    @app.get("/api/reg/docs/{did}")
    def get_doc(request: Request, did: int):
        require_admin(request)
        d = _rows("SELECT * FROM docs WHERE id=?", (did,))
        if not d:
            raise HTTPException(404, "Document not found.")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", d[0]["name"]) or "document"
        return Response(content=d[0]["data"], media_type=d[0]["mime"] or "application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{safe}"'})

    @app.delete("/api/reg/docs/{did}")
    def del_doc(request: Request, did: int):
        require_admin(request)
        _run("DELETE FROM docs WHERE id=?", (did,), force_backup=True)
        return {"ok": True}

    @app.get("/api/reg/pack/{iid}")
    def pack(request: Request, iid: int):
        require_admin(request)
        it = _rows("SELECT * FROM items WHERE id=?", (iid,))
        if not it:
            raise HTTPException(404, "Item not found.")
        it = it[0]
        docs = _rows("SELECT * FROM docs WHERE item_id=?", (iid,))
        blob = build_pack_bytes(it, docs)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", it["title"])[:40] or "pack"
        return Response(content=blob, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{safe}-pack.zip"'})

    # ---------------- DoEL submission pipeline
    @app.get("/traffic/ll1", response_class=HTMLResponse)
    def traffic_ll1(request: Request, code: str = "B"):
        return HTMLResponse(_traffic_form(request, "LL1", code, "", ""))

    @app.get("/traffic/dl1", response_class=HTMLResponse)
    def traffic_dl1(request: Request, code: str = "B", ll: str = "", lldate: str = ""):
        return HTMLResponse(_traffic_form(request, "DL1", code, ll, lldate))

    @app.get("/traffic/alv", response_class=HTMLResponse)
    def traffic_alv(request: Request, reg: str = "", vin: str = "", make: str = "", model: str = "",
                    year: str = "", tare: str = "", exp: str = ""):
        return HTMLResponse(_vehicle_form(request, "ALV", {"reg": reg, "vin": vin, "make": make,
                                                           "model": model, "year": year, "tare": tare, "exp": exp}))

    @app.get("/traffic/arc", response_class=HTMLResponse)
    def traffic_arc(request: Request, reg: str = "", vin: str = "", make: str = "", model: str = "",
                    year: str = "", tare: str = ""):
        return HTMLResponse(_vehicle_form(request, "ARC", {"reg": reg, "vin": vin, "make": make,
                                                           "model": model, "year": year, "tare": tare}))

    @app.get("/traffic/lcard/{tid}", response_class=HTMLResponse)
    def traffic_lcard(request: Request, tid: int):
        r = _rows("SELECT * FROM traffic WHERE id=? AND kind='licence'", (tid,))
        if not r:
            raise HTTPException(404, "Licence record not found.")
        c = r[0]
        today = time.strftime("%Y-%m-%d")
        expired = bool(c["expires_on"]) and c["expires_on"] < today
        status = "EXPIRED" if expired else ("VALID" if c["expires_on"] else "NO EXPIRY ON RECORD")
        col = "#c0392b" if expired else "#1e8e3e"
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Licence record {c['ref'] or c['id']}</title>
<style>@page{{size:A4 landscape;margin:14mm}}body{{margin:0;background:#eef0f7;font-family:system-ui,sans-serif;color:#1c2033}}
.sheet{{position:relative;max-width:860px;margin:24px auto;background:#fff;border:3px solid #5b5bd6;padding:40px 48px;overflow:hidden}}
.wm{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;
font:800 64px/1 system-ui;color:rgba(192,57,43,.10);transform:rotate(-24deg);text-align:center;letter-spacing:.06em}}
.head{{font:800 15px/1.4 system-ui;letter-spacing:.14em;text-transform:uppercase;color:#5b5bd6}}
.sub{{font:12px/1.5 system-ui;color:#64698a;margin:2px 0 20px}}
.grid2{{display:flex;gap:16px;flex-wrap:wrap}} .box{{flex:1;min-width:220px;border:1px solid #9aa0c0;padding:10px 14px}}
label{{display:block;font:10px/1.3 system-ui;text-transform:uppercase;letter-spacing:.06em;color:#64698a}}
.val{{font:15px/1.4 system-ui;margin-top:3px}} .status{{font:800 20px system-ui;color:{col}}}
.note{{font:11px/1.6 system-ui;color:#3c4160;border-top:1px solid #c9cde4;margin-top:22px;padding-top:12px}}
button{{position:fixed;top:14px;right:14px;font:600 14px system-ui;padding:10px 16px;border-radius:10px;border:1px solid #5b5bd6;background:#5b5bd6;color:#fff;cursor:pointer}}
@media print{{button{{display:none}}body{{background:#fff}}.sheet{{margin:0}}}}</style></head>
<body><button onclick="window.print()">Print / save PDF</button>
<div class="sheet"><div class="wm">UNOFFICIAL RECORD<br>NOT A LICENCE</div>
<div class="head">My AI Pro Registry &middot; Personal Licence Record</div>
<div class="sub">Private register of Ruwayne Campher &middot; record printed {today} &middot; this card is NOT a learner's or driving
licence and confers no right to drive on any road.</div>
<div class="grid2">
<div class="box"><label>Licence type &amp; code</label><div class="val">{c['descr']}</div></div>
<div class="box"><label>Licence number</label><div class="val">{c['ref'] or 'not recorded'}</div></div>
<div class="box"><label>Issued</label><div class="val">{c['paid_on'] or '-'}</div></div>
<div class="box"><label>Expiry / renewal</label><div class="val">{c['expires_on'] or '-'}</div></div>
<div class="box"><label>Status on this record</label><div class="status">{status}</div></div>
<div class="box"><label>Fingerprints / biometrics</label><div class="val">Captured physically at the testing centre on the
official document only - no digital copy exists or is valid.</div></div>
</div>
<div class="note"><b>Expired?</b> A learner's licence cannot be extended or re-dated by anyone: book a fresh test
(LL1 form, R108) at your DLTC or via online.natis.gov.za - the DLTC then issues a new official temporary licence.
<b>Need certified proof of history?</b> Request a NaTIS driving-licence record extract from the RTMC / your DLTC.
Official status of any licence is only what eNaTIS states.</div>
</div></body></html>""")

    @app.get("/api/reg/traffic")
    def traffic_list(request: Request):
        require_admin(request)
        return {"rows": _rows("SELECT * FROM traffic ORDER BY kind, id")}

    @app.post("/api/reg/traffic")
    async def traffic_add(request: Request):
        require_admin(request)
        d = await request.json()
        kind = d.get("kind") if d.get("kind") in ("fee", "licence", "vehicle", "verify") else "fee"
        _run("INSERT INTO traffic(kind,ref,descr,amount,status,paid_on,receipt,expires_on,created)"
             " VALUES (?,?,?,?, ?, ?,?, ?, ?)",
             (kind, str(d.get("ref") or "")[:60], str(d.get("descr") or "")[:200], float(d.get("amount") or 0),
              str(d.get("status") or ("unpaid" if kind == "fee" else "n/a"))[:20],
              str(d.get("paid_on") or "")[:20], str(d.get("receipt") or "")[:80], str(d.get("expires_on") or "")[:20],
              time.time()), force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/traffic/{tid}")
    async def traffic_upd(request: Request, tid: int):
        require_admin(request)
        row = _rows("SELECT * FROM traffic WHERE id=?", (tid,))
        if not row:
            raise HTTPException(404, "Not found.")
        r, d = row[0], await request.json()
        status, paid_on = r["status"], r["paid_on"]
        if d.get("mark_paid"):
            status, paid_on = "paid", time.strftime("%Y-%m-%d")
        if d.get("status"):
            status = str(d["status"])[:20]
        _run("UPDATE traffic SET ref=?,descr=?,amount=?,status=?,paid_on=?,receipt=?,expires_on=? WHERE id=?",
             (str(d.get("ref", r["ref"]))[:60], str(d.get("descr", r["descr"]))[:200],
              float(d.get("amount", r["amount"])), status, paid_on,
              str(d.get("receipt", r["receipt"]))[:80], str(d.get("expires_on", r["expires_on"]))[:20], tid),
             force_backup=True)
        return {"ok": True}

    @app.delete("/api/reg/traffic/{tid}")
    def traffic_del(request: Request, tid: int):
        require_admin(request)
        _run("DELETE FROM traffic WHERE id=?", (tid,), force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/sendmail")
    def reg_sendmail(request: Request, d: dict):
        """Owner-gated outbound e-mail through the configured SMTP account, logged in submissions."""
        require_admin(request)
        to = str(d.get("to") or "").strip()
        subject = str(d.get("subject") or "").strip()
        body = str(d.get("body") or "")
        if not (to and subject):
            raise HTTPException(400, "to and subject required.")
        host, port = get_kv("smtp_host"), int(get_kv("smtp_port") or "587")
        user, pw = get_kv("smtp_user"), get_kv("smtp_pass")
        frm = get_kv("smtp_from") or user
        try:
            if not (host and user and pw):
                raise RuntimeError("SMTP not configured in the Submission tab yet.")
            msg = MIMEText(body, "plain")
            msg["Subject"], msg["From"], msg["To"] = subject, frm, to
            with smtplib.SMTP(host, port, timeout=25) as s:
                s.starttls()
                s.login(user, pw)
                s.sendmail(frm, [to], msg.as_string())
            status, log = "sent", f"sent via {host} to {to}"
        except Exception as e:
            status, log = "failed", repr(e)[:2000]
        _run("INSERT INTO submissions(item_id,channel,target,status,log,created,sent_at)"
             " VALUES (0,'smtp',?,?,?,?,?,?)",
             (f"{to} | {subject}", status, log, time.time(),
              time.time() if status == "sent" else 0), force_backup=True)
        return {"ok": status == "sent", "status": status, "log": log}

    @app.get("/annexure5/{iid}", response_class=HTMLResponse)
    def annexure5_page(request: Request, iid: int):
        require_admin(request)
        it = _rows("SELECT * FROM items WHERE id=?", (iid,))
        if not it:
            raise HTTPException(404, "Item not found.")
        txt = annexure5_text(it[0])
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Annexure 5 - pre-filled</title>
<style>body{{margin:0;background:#eef0f7;font:14px/1.7 ui-monospace,monospace;color:#1c2033}}
main{{max-width:820px;margin:24px auto;background:#fff;border:1px solid #d8dae6;padding:34px 40px;white-space:pre-wrap}}
button{{position:fixed;top:14px;right:14px;font:600 14px system-ui;padding:10px 16px;border-radius:10px;border:0;background:#5b5bd6;color:#fff;cursor:pointer}}
@media print{{button{{display:none}}body{{background:#fff}}main{{margin:0;border:0}}}}</style></head>
<body><button onclick="window.print()">Print / save PDF</button><main>{txt}</main></body></html>""")

    @app.get("/api/reg/settings")
    def get_settings(request: Request):
        require_admin(request)
        return settings_masked()

    @app.post("/api/reg/settings")
    async def put_settings(request: Request):
        require_admin(request)
        body = await request.json()
        for k in SETTING_KEYS:
            if k not in body:
                continue
            v = str(body[k] or "")
            if k == "smtp_pass" and (not v or v == "••••••••"):
                continue                      # keep the stored secret
            if k == "signature" and len(v) > 900_000:
                raise HTTPException(413, "Signature image too large.")
            set_kv(k, v[:2000] if k != "signature" else v)
        return {"ok": True}

    @app.post("/api/reg/submit/{iid}")
    def submit_item(request: Request, iid: int):
        require_admin(request)
        it = _rows("SELECT * FROM items WHERE id=?", (iid,))
        if not it:
            raise HTTPException(404, "Item not found.")
        it = it[0]
        docs = _rows("SELECT * FROM docs WHERE item_id=?", (iid,))
        blob = build_pack_bytes(it, docs)
        target = get_kv("doel_email") or "(not configured)"
        with _lock, _connect() as con:
            cur = con.execute("INSERT INTO submissions(item_id, channel, target, status, log, created, sent_at)"
                              " VALUES (?,?,?,?,?,?,0)",
                              (iid, "email", target, "sending", "", time.time()))
            sid = cur.lastrowid
            con.commit()
        threading.Thread(target=backup_now, kwargs={"force": True}, daemon=True).start()
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", it["title"])[:40] or "pack"

        def work():
            try:
                log = smtp_send(f"Wireman's licence / registered-person application - {it['title']} "
                                f"[{it['number'] or 'new'}]",
                                cover_letter(it), f"{safe}-pack.zip", blob)
                st = "sent"
            except Exception as exc:                      # noqa: BLE001 - logged for the owner
                log, st = f"{type(exc).__name__}: {exc}", "failed"
            with _lock, _connect() as con:
                con.execute("UPDATE submissions SET status=?, log=?, sent_at=? WHERE id=?",
                            (st, log[:2000], time.time(), sid))
                con.commit()
            threading.Thread(target=backup_now, kwargs={"force": True}, daemon=True).start()

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "id": sid, "status": "sending",
                "note": "Pack assembled and handing over to your configured SMTP channel."}

    @app.get("/api/reg/submissions")
    def list_submissions(request: Request):
        require_admin(request)
        return {"submissions": _rows("SELECT * FROM submissions ORDER BY created DESC")}

    @app.post("/api/reg/submissions/{sid}/retry")
    def retry_submission(request: Request, sid: int):
        require_admin(request)
        s = _rows("SELECT * FROM submissions WHERE id=?", (sid,))
        if not s:
            raise HTTPException(404, "Submission not found.")
        return submit_item(request, s[0]["item_id"])

    @app.post("/api/reg/certs")
    async def issue_cert(request: Request):
        require_admin(request)
        b = await request.json()
        holder = str(b.get("holder") or "").strip()[:100]
        ctype = str(b.get("ctype") or "").strip()[:120]
        if not holder or not ctype:
            raise HTTPException(400, "Holder and certificate type are required.")
        code = f"RC-{time.strftime('%Y')}-{secrets.token_hex(2).upper()}"
        _run("INSERT INTO certs(code,holder,ctype,body,issued_on,expires_on,voided,created)"
             " VALUES (?,?,?,?,?,?,0,?)",
             (code, holder, ctype, str(b.get("body") or "")[:1500],
              str(b.get("issued_on") or time.strftime("%Y-%m-%d"))[:20], str(b.get("expires_on") or "")[:20],
              time.time()), force_backup=True)
        return {"ok": True, "code": code}

    @app.post("/api/reg/certs/{cid}/void")
    def void_cert(request: Request, cid: int):
        require_admin(request)
        _run("UPDATE certs SET voided=1 WHERE id=?", (cid,), force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/orders/{oid}/status")
    async def order_status(request: Request, oid: int):
        require_admin(request)
        st = str((await request.json()).get("status") or "")
        if st not in ("awaiting-payment", "verifying", "paid", "fulfilled", "rejected"):
            raise HTTPException(400, "Unknown status.")
        _run("UPDATE orders SET status=? WHERE id=?", (st, oid), force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/services")
    async def add_service(request: Request):
        require_admin(request)
        b = await request.json()
        _run("INSERT INTO services(name, price, descr, active) VALUES (?,?,?,1)",
             (str(b.get("name") or "Service")[:100], float(b.get("price") or 0), str(b.get("descr") or "")[:300]),
             force_backup=True)
        return {"ok": True}

    @app.post("/api/reg/services/{sid}/toggle")
    def toggle_service(request: Request, sid: int):
        require_admin(request)
        _run("UPDATE services SET active = 1 - active WHERE id=?", (sid,), force_backup=True)
        return {"ok": True}
