"""Purify Enterprise On-Premise v2 — identity, editions, approvals, audit.
Local accounts stay as break-glass; Active Directory (Business+) signs staff in
with nested-group role mapping; every sensitive action hits the audit trail."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import ad
import database
import devices
import programs
from ad import ADError
from ad_sync import sync_tenant
from devices import DeviceError
from editions import catalog, entitlements, has_feature, require_feature
from programs import ProgramError
from secretbox import decrypt_secret, encrypt_secret  # noqa: F401  (re-export for ops scripts)

log = logging.getLogger("purify")
logging.basicConfig(level=os.getenv("PURIFY_LOGLEVEL", "INFO"))

VALID_ROLES = {"executive", "finance", "sales", "marketing", "support"}
SESSION_HOURS = 12
SECRET = os.getenv("PURIFY_SECRET_KEY", "")

app = FastAPI(title="Purify Enterprise On-Premise", version="2.2.0",
              docs_url=None, redoc_url=None, openapi_url=None)
database.init_db()


# ------------------------------------------------------------ passwords & tokens

def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000)
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def _b64e(blob: bytes) -> str:
    return base64.urlsafe_b64encode(blob).decode().rstrip("=")


def _b64d(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def create_access_token(user_id: str, username: str, tenant_id: str) -> str:
    payload = json.dumps({"uid": user_id, "u": username, "tid": tenant_id,
                          "exp": int(time.time()) + SESSION_HOURS * 3600}, sort_keys=True).encode()
    sig = hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()
    return f"{_b64e(payload)}.{_b64e(sig)}"


def _parse_token(token: str) -> Optional[dict]:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64d(payload_b64)
        expect = hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64d(sig_b64)):
            return None
        data = json.loads(payload)
        if data["exp"] < time.time():
            return None
        return data
    except Exception:
        return None


def _set_session(response: Response, token: str) -> None:
    response.set_cookie("purify_session", token, httponly=True, samesite="lax",
                        max_age=SESSION_HOURS * 3600)


def get_current_user(request: Request) -> Dict[str, Any]:
    token = request.cookies.get("purify_session") or ""
    auth = request.headers.get("authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
    data = _parse_token(token) if token and SECRET else None
    if not data:
        raise HTTPException(status_code=401, detail="Not signed in.")
    user = database.get_user_by_id(data["uid"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Account disabled or removed.")
    return user


CurrentUser = Depends(get_current_user)


def require_roles(*roles: str):
    def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Role required: {', '.join(roles)}")
        return user
    return _dep


def _enforce_license() -> None:
    ent = entitlements()
    if not ent["valid"]:
        raise HTTPException(status_code=402, detail=f"License invalid: {ent.get('reason')}")


# ------------------------------------------------------------ login rate limit

_LOGIN_HITS: Dict[str, list] = {}


def _rate_limited(key: str) -> bool:
    now = time.time()
    hits = [t for t in _LOGIN_HITS.get(key, []) if now - t < 300]
    hits.append(now)
    _LOGIN_HITS[key] = hits
    return len(hits) > 8


# ------------------------------------------------------------ schemas

class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    tenant_slug: Optional[str] = Field(default=None, max_length=60)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(min_length=2, max_length=20)


class ApprovalCreate(BaseModel):
    target_system: str = Field(min_length=2, max_length=80)
    action_summary: str = Field(min_length=5, max_length=300)
    proposed_payload: dict = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    decision_note: str = Field(default="", max_length=500)


class ADSettingsRequest(BaseModel):
    enabled: bool = False
    server_url: str = Field(min_length=8, max_length=255)
    security: Literal["ldaps", "starttls"] = "ldaps"
    ca_cert_pem: str = Field(default="", max_length=20000)
    base_dn: str = Field(min_length=3, max_length=255)
    bind_dn: str = Field(min_length=3, max_length=255)
    bind_password: str = Field(default="", max_length=256)  # blank keeps the stored password
    group_map: Dict[str, str] = Field(default_factory=dict)  # "group DN" -> role


AD_GUARD = [Depends(require_feature("active_directory"))]
LINK_GUARD = [Depends(require_feature("device_links"))]


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    protocol: Literal["modbus_tcp", "opcua", "rest"] = "modbus_tcp"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    unit_id: int = Field(default=1, ge=0, le=247)   # modbus unit/slave id
    tls: bool = False                                # rest: use https
    path: str = Field(default="", max_length=120)    # opcua endpoint path, e.g. /purify/
    auth: dict = Field(default_factory=dict)         # rest: {"type":...} | opcua: username/policy/certs


class DeviceAction(BaseModel):
    type: Literal["read", "write"]
    register_start: int = Field(default=0, ge=0, le=65535)  # modbus
    count: int = Field(default=1, ge=1, le=125)             # modbus read
    values: list = Field(default_factory=list)              # modbus write
    path: str = Field(default="/", max_length=200)          # rest
    body: dict = Field(default_factory=dict)                # rest write
    node_ids: list = Field(default_factory=list)            # opcua read
    node_id: Optional[str] = Field(default=None, max_length=200)  # opcua write (or single read)
    value: Optional[Any] = None                             # opcua write
    variant_type: Optional[str] = Field(default=None, max_length=20)
    approval_id: Optional[str] = None                       # REQUIRED for writes


class ProgramCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    base_url: str = Field(min_length=8, max_length=255)
    auth_type: Literal["none", "api_key", "basic", "oauth2_cc", "hmac"] = "none"
    auth: dict = Field(default_factory=dict)
    health_path: str = Field(default="/health", max_length=120)


class ProgramInvoke(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE"] = "GET"
    path: str = Field(default="/", max_length=200)
    body: dict = Field(default_factory=dict)
    approval_id: Optional[str] = None  # REQUIRED for POST/PUT/DELETE


# ------------------------------------------------------------ helpers (pasted logic)

def _resolve_tenant(slug: Optional[str]) -> Dict[str, Any]:
    if slug:
        tenant = database.get_tenant_by_slug(slug.strip().lower())
    else:
        tenant = database.get_only_tenant()
        if tenant is None and database.count_tenants() > 1:
            raise HTTPException(status_code=400, detail="Enter your company name to sign in.")
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return tenant


def _ad_login(tenant_id: str, username: str, password: str) -> Optional[Dict[str, Any]]:
    if not has_feature("active_directory"):
        return None
    username = username.strip().lower()
    try:
        cfg = ad.load_config(tenant_id)
        if not cfg or not cfg["enabled"]:
            return None
        principal = ad.resolve_user(cfg, username)
        existing = database.get_user_by_username(username, tenant_id)

        if principal is None or not principal.enabled or principal.role is None:
            if existing and existing["auth_source"] == "ad" and existing["is_active"]:
                database.set_user_active(tenant_id, existing["id"], False)
                database.log_audit(tenant_id=tenant_id, actor=username, user_role="unknown",
                                   action="ad_access_revoked", sphere="identity", status="SUCCESS")
            return None

        if not ad.verify_user_password(cfg, principal.dn, password):
            return None
        return database.upsert_ad_user(tenant_id, username, principal.role, principal.external_id)
    except ValueError:
        return None  # username clashes with a local account
    except ADError:
        log.exception("Directory lookup failed")
        raise HTTPException(status_code=503,
                            detail="Sign-in service temporarily unavailable. Please try again.")


# ------------------------------------------------------------ endpoints

@app.get("/health")
def health():
    return {"status": "ok", "deployment": "on-premise", "version": "2.2.0"}


@app.get("/", include_in_schema=False)
def dashboard_ui():
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html",
                        headers={"Cache-Control": "no-cache"})


@app.post("/api/auth/signup")
async def signup(req: SignupRequest, response: Response):
    slug = "".join(ch for ch in req.company_name.lower() if ch.isalnum()) or "company"
    if database.get_tenant_by_slug(slug):
        slug = slug + secrets.token_hex(2)
    tenant = database.create_tenant(req.company_name.strip(), slug)
    user = database.create_user(tenant["id"], req.username.strip().lower(),
                                hash_password(req.password), "executive")
    if not user:
        raise HTTPException(status_code=409, detail="Username already taken in this company.")
    database.log_audit(tenant_id=tenant["id"], actor=user["username"], user_role="executive",
                       action="tenant_created", sphere="identity", status="SUCCESS",
                       details={"company": req.company_name})
    token = create_access_token(user["id"], user["username"], tenant["id"])
    _set_session(response, token)
    return {"access_token": token, "username": user["username"], "role": user["role"],
            "tenant": tenant["slug"]}


@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    tenant = _resolve_tenant(req.tenant_slug)
    key = f"login:{tenant['id']}:{req.username.strip().lower()}"
    if _rate_limited(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.")

    existing = database.get_user_by_username(req.username.strip().lower(), tenant["id"])
    if existing and existing["auth_source"] == "local":
        ok = existing["is_active"] and verify_password(req.password, existing["password_hash"])
        user = existing if ok else None
    else:
        user = _ad_login(tenant["id"], req.username, req.password)

    if user is None:
        database.log_audit(tenant_id=tenant["id"], actor=req.username, user_role="unknown",
                           action="login", sphere="identity", status="FAILED")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _LOGIN_HITS.pop(key, None)
    database.log_audit(tenant_id=tenant["id"], actor=user["username"], user_role=user["role"],
                       action="login", sphere="identity", status="SUCCESS",
                       details={"source": user.get("auth_source", "local")})
    token = create_access_token(user["id"], user["username"], tenant["id"])
    _set_session(response, token)
    return {"access_token": token, "token_type": "bearer",
            "username": user["username"], "role": user["role"]}


@app.get("/api/me")
async def me(me: Dict[str, Any] = CurrentUser):
    return {"username": me["username"], "role": me["role"], "tenant_id": me["tenant_id"],
            "auth_source": me["auth_source"]}


@app.get("/api/editions")
async def editions_info(me: Dict[str, Any] = CurrentUser):
    return {"current": entitlements(), "catalog": catalog()}


@app.post("/api/admin/users")
async def admin_create_user(req: CreateUserRequest, me: Dict[str, Any] = Depends(require_roles("executive"))):
    _enforce_license()
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(VALID_ROLES)}")
    ent = entitlements()
    if len(database.list_users(me["tenant_id"])) >= ent["max_users"]:
        raise HTTPException(status_code=402,
                            detail=f"The {ent['label']} edition allows {ent['max_users']} users. Upgrade to add more.")
    user = database.create_user(me["tenant_id"], req.username.strip().lower(),
                                hash_password(req.password), req.role)
    if not user:
        raise HTTPException(status_code=409, detail="Username already taken.")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="user_created", sphere="identity", status="SUCCESS",
                       details={"new_username": user["username"], "role": user["role"]})
    return {"status": "created", "username": user["username"], "role": user["role"]}


@app.get("/api/users")
async def list_staff(me: Dict[str, Any] = Depends(require_roles("executive"))):
    return {"users": database.list_users(me["tenant_id"])}


@app.get("/api/admin/ad", dependencies=AD_GUARD)
async def get_ad_settings(me: Dict[str, Any] = Depends(require_roles("executive"))):
    return ad.public_settings(me["tenant_id"])


@app.put("/api/admin/ad", dependencies=AD_GUARD)
async def put_ad_settings(req: ADSettingsRequest, me: Dict[str, Any] = Depends(require_roles("executive"))):
    try:
        ad.save_settings(me["tenant_id"], req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="ad_settings_updated", sphere="identity", status="SUCCESS",
                       details={"enabled": req.enabled, "security": req.security,
                                "roles_mapped": sorted({v.strip().lower() for v in req.group_map.values()})})
    return {"status": "saved"}


@app.post("/api/admin/ad/test", dependencies=AD_GUARD)
async def test_ad(me: Dict[str, Any] = Depends(require_roles("executive"))):
    try:
        return ad.run_connection_test(me["tenant_id"])
    except (ValueError, ADError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/admin/ad/sync", dependencies=AD_GUARD)
async def sync_ad_now(me: Dict[str, Any] = Depends(require_roles("executive"))):
    try:
        cfg = ad.load_config(me["tenant_id"])
    except ADError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not cfg or not cfg["enabled"]:
        raise HTTPException(status_code=400, detail="Directory sign-in is not enabled.")
    stats = sync_tenant(me["tenant_id"], cfg)
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="ad_sync_manual", sphere="identity", status="SUCCESS", details=stats)
    return stats


# ------------------------------------------------- devices & programs (v2.1, Business+)

def _require_approved(tenant_id: str, approval_id: Optional[str], target_name: str) -> Dict[str, Any]:
    """The core promise: side effects only run behind a human-approved, single-use approval."""
    if not approval_id:
        raise HTTPException(status_code=428,
                            detail="Human approval required. Propose the action first and attach its approval_id.")
    row = database.get_approval(tenant_id, approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found in this company.")
    if row["status"] != "approved":
        raise HTTPException(status_code=409,
                            detail=f"Approval status is '{row['status']}' — only 'approved' authorizes an action.")
    if row["target_system"].strip().lower() != target_name.strip().lower():
        raise HTTPException(status_code=409,
                            detail=f"That approval targets '{row['target_system']}', not '{target_name}'.")
    return row


@app.get("/api/devices", dependencies=LINK_GUARD)
async def list_linked_devices(me: Dict[str, Any] = CurrentUser):
    return {"devices": [devices.public_view(d) for d in database.list_devices(me["tenant_id"])]}


@app.post("/api/devices", dependencies=LINK_GUARD)
async def add_device(req: DeviceCreate, me: Dict[str, Any] = Depends(require_roles("executive"))):
    _enforce_license()
    try:
        devices.validate_device(req.protocol, req.host, req.port, req.auth)
        row = database.create_device(me["tenant_id"], {
            "name": req.name.strip(), "protocol": req.protocol, "host": req.host.strip(),
            "port": req.port, "unit_id": req.unit_id, "tls": req.tls,
            "path": req.path.strip(),
            "auth_enc": devices.pack_credentials(req.auth), "enabled": True,
            "updated_at": database.now_iso(),
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not row:
        raise HTTPException(status_code=409, detail="A device with this name already exists.")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="device_linked", sphere="devices", status="SUCCESS",
                       details={"device": row["name"], "protocol": row["protocol"],
                                "host": row["host"], "port": row["port"]})
    return devices.public_view(row)


@app.delete("/api/devices/{device_id}", dependencies=LINK_GUARD)
async def remove_device(device_id: str, me: Dict[str, Any] = Depends(require_roles("executive"))):
    row = database.get_device(me["tenant_id"], device_id)
    if not row or not database.delete_device(me["tenant_id"], device_id):
        raise HTTPException(status_code=404, detail="Device not found.")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="device_unlinked", sphere="devices", status="SUCCESS",
                       details={"device": row["name"]})
    return {"status": "removed", "device": row["name"]}


@app.post("/api/devices/{device_id}/test", dependencies=LINK_GUARD)
async def test_linked_device(device_id: str, me: Dict[str, Any] = Depends(require_roles("executive"))):
    row = database.get_device(me["tenant_id"], device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Device not found.")
    try:
        result = await run_in_threadpool(devices.test_device, row)
    except (DeviceError, ProgramError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="device_tested", sphere="devices",
                       status="SUCCESS" if result.get("ok") else "FAILED",
                       details={"device": row["name"], "ok": result.get("ok")})
    return result


@app.post("/api/devices/{device_id}/action", dependencies=LINK_GUARD)
async def device_action(device_id: str, req: DeviceAction, me: Dict[str, Any] = CurrentUser):
    row = database.get_device(me["tenant_id"], device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Device not found.")
    if not row["enabled"]:
        raise HTTPException(status_code=409, detail="Device is disabled.")
    is_write = (req.type == "write") or (row["protocol"] == "rest" and req.type == "write")
    approval = None
    if is_write:
        approval = _require_approved(me["tenant_id"], req.approval_id, row["name"])
    try:
        result = await run_in_threadpool(devices.run_action, row, req.model_dump())
    except (DeviceError, ProgramError) as exc:
        database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                           action="device_action", sphere="devices", status="FAILED",
                           details={"device": row["name"], "type": req.type, "error": str(exc)[:200]})
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if approval:
        database.mark_approval_consumed(me["tenant_id"], approval["id"],
                                        note=f"executed on device {row['name']}")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="device_action", sphere="devices", status="SUCCESS",
                       details={"device": row["name"], "type": req.type,
                                "approval_id": approval["id"] if approval else None,
                                "result": {k: v for k, v in result.items() if k != "response"}})
    return {"status": "executed", "result": result,
            "approval_consumed": bool(approval)}


@app.get("/api/programs", dependencies=LINK_GUARD)
async def list_linked_programs(me: Dict[str, Any] = CurrentUser):
    return {"programs": [programs.public_view(p) for p in database.list_programs(me["tenant_id"])]}


@app.post("/api/programs", dependencies=LINK_GUARD)
async def link_program(req: ProgramCreate, me: Dict[str, Any] = Depends(require_roles("executive"))):
    _enforce_license()
    try:
        programs.validate_program(req.base_url, req.auth_type, req.auth)
        row = database.create_program(me["tenant_id"], {
            "name": req.name.strip(), "base_url": req.base_url.strip(),
            "auth_type": req.auth_type,
            "auth_enc": encrypt_secret(json.dumps(req.auth)) if req.auth else "",
            "health_path": req.health_path.strip() or "/health", "enabled": True,
            "updated_at": database.now_iso(),
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not row:
        raise HTTPException(status_code=409, detail="A program with this name already exists.")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="program_linked", sphere="integrations", status="SUCCESS",
                       details={"program": row["name"], "auth_type": row["auth_type"],
                                "base_url": row["base_url"]})
    return programs.public_view(row)


@app.delete("/api/programs/{program_id}", dependencies=LINK_GUARD)
async def unlink_program(program_id: str, me: Dict[str, Any] = Depends(require_roles("executive"))):
    row = database.get_program(me["tenant_id"], program_id)
    if not row or not database.delete_program(me["tenant_id"], program_id):
        raise HTTPException(status_code=404, detail="Program not found.")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="program_unlinked", sphere="integrations", status="SUCCESS",
                       details={"program": row["name"]})
    return {"status": "removed", "program": row["name"]}


@app.post("/api/programs/{program_id}/test", dependencies=LINK_GUARD)
async def test_linked_program(program_id: str, me: Dict[str, Any] = Depends(require_roles("executive"))):
    row = database.get_program(me["tenant_id"], program_id)
    if not row:
        raise HTTPException(status_code=404, detail="Program not found.")
    try:
        creds = json.loads(decrypt_secret(row["auth_enc"])) if row["auth_enc"] else {}
        url = programs.join_url(row["base_url"], row["health_path"])
        headers = programs.build_auth_headers(row["auth_type"], creds, method="GET", url=url)
        status, _ = programs.http_request(url, "GET", headers)
    except (ProgramError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    ok = status < 400
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="program_tested", sphere="integrations",
                       status="SUCCESS" if ok else "FAILED",
                       details={"program": row["name"], "http_status": status})
    return {"ok": ok, "status": status,
            "message": "Handshake OK — credentials accepted" if ok else
                       f"Program answered HTTP {status} — check URL/credentials"}


@app.post("/api/programs/{program_id}/invoke", dependencies=LINK_GUARD)
async def invoke_program(program_id: str, req: ProgramInvoke, me: Dict[str, Any] = CurrentUser):
    row = database.get_program(me["tenant_id"], program_id)
    if not row:
        raise HTTPException(status_code=404, detail="Program not found.")
    if not row["enabled"]:
        raise HTTPException(status_code=409, detail="Program is disabled.")
    approval = None
    if req.method != "GET":
        approval = _require_approved(me["tenant_id"], req.approval_id, row["name"])
    try:
        creds = json.loads(decrypt_secret(row["auth_enc"])) if row["auth_enc"] else {}
        url = programs.join_url(row["base_url"], req.path)
        body = json.dumps(req.body).encode() if req.body else None
        headers = programs.build_auth_headers(row["auth_type"], creds, method=req.method,
                                              url=url, body=body or b"")
        headers.setdefault("Accept", "application/json")
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, text = programs.http_request(url, req.method, headers, body)
    except (ProgramError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if approval and status < 400:
        database.mark_approval_consumed(me["tenant_id"], approval["id"],
                                        note=f"executed on program {row['name']}")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="program_invoke", sphere="integrations",
                       status="SUCCESS" if status < 400 else "FAILED",
                       details={"program": row["name"], "method": req.method, "path": req.path,
                                "http_status": status,
                                "approval_id": approval["id"] if approval else None})
    if status >= 400:
        raise HTTPException(status_code=502, detail=f"Program returned HTTP {status}")
    return {"status": status, "response": text[:4000], "approval_consumed": bool(approval)}


@app.post("/api/programs/by-name/{name}/webhook")
async def program_webhook(name: str, request: Request):
    """Inbound: a linked program proposes an action. Authenticated with the shared
    HMAC secret (X-Purify-Timestamp + X-Purify-Signature). Creates a PENDING approval —
    the program can never execute anything itself."""
    if not has_feature("device_links"):
        raise HTTPException(status_code=402, detail="Device & program linking is not in this edition.")
    tenant = database.get_only_tenant()
    if tenant is None:
        if database.count_tenants() == 1:
            tenant = database.list_tenants()[0]
        else:
            raise HTTPException(status_code=400, detail="Multi-company install: use /api/programs/{id}/invoke from a session instead.")
    row = database.get_program_by_name(tenant["id"], name.strip())
    if not row or not row["enabled"] or row["auth_type"] != "hmac":
        raise HTTPException(status_code=404, detail="No such linked webhook program.")
    if _rate_limited(f"webhook:{tenant['id']}:{name}"):
        raise HTTPException(status_code=429, detail="Too many webhook calls. Slow down.")
    body = await request.body()
    secret = json.loads(decrypt_secret(row["auth_enc"]))["secret"] if row["auth_enc"] else ""
    ok = programs.verify_inbound_hmac(
        secret, request.headers.get("x-purify-timestamp", ""), body,
        request.headers.get("x-purify-signature", ""))
    if not ok:
        database.log_audit(tenant_id=tenant["id"], actor=f"program:{name}", user_role="system",
                           action="webhook_rejected", sphere="integrations", status="FAILED")
        raise HTTPException(status_code=401, detail="Signature check failed.")
    try:
        payload = json.loads(body or b"{}")
        summary = str(payload.get("action_summary", ""))[:300]
        if len(summary) < 5:
            raise ValueError("action_summary too short")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400,
                            detail='Body must be JSON: {"action_summary": "...", "proposed_payload": {...}, "target_system": "..."}')
    approval = database.create_approval(
        tenant["id"], f"program:{name}",
        str(payload.get("target_system") or name)[:80], summary,
        payload.get("proposed_payload") or {})
    database.log_audit(tenant_id=tenant["id"], actor=f"program:{name}", user_role="system",
                       action="webhook_approval_created", sphere="integrations", status="SUCCESS",
                       details={"approval_id": approval["id"]})
    return {"status": "pending_approval", "approval_id": approval["id"]}


@app.post("/api/approvals")
async def propose(req: ApprovalCreate, me: Dict[str, Any] = CurrentUser):
    row = database.create_approval(me["tenant_id"], me["username"], req.target_system.strip(),
                                   req.action_summary.strip(), req.proposed_payload)
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action="approval_proposed", sphere="actions", status="SUCCESS",
                       details={"approval_id": row["id"], "target": req.target_system})
    return row


@app.get("/api/approvals")
async def approvals(me: Dict[str, Any] = CurrentUser):
    return {"approvals": database.list_approvals(me["tenant_id"])}


@app.post("/api/approvals/{approval_id}/decide")
async def decide(approval_id: str, req: ApprovalDecision,
                 me: Dict[str, Any] = Depends(require_roles("executive"))):
    row = database.decide_approval(me["tenant_id"], approval_id, req.decision,
                                   me["username"], req.decision_note.strip())
    if not row:
        raise HTTPException(status_code=409, detail="Approval not found or already decided.")
    database.log_audit(tenant_id=me["tenant_id"], actor=me["username"], user_role=me["role"],
                       action=f"approval_{req.decision}", sphere="actions", status="SUCCESS",
                       details={"approval_id": approval_id, "note": req.decision_note})
    return row


@app.get("/api/audit")
async def audit(me: Dict[str, Any] = Depends(require_roles("executive"))):
    return {"audit": database.list_audit(me["tenant_id"])}
