"""Purify bridge inside Smash AI Pro: edition catalogue + owner-license verification.

The RSA PUBLIC key below is the same key shipped inside the Purify product
(purify/vendor/public.pem). The PRIVATE signing key never enters this repo or
this service. The owner lifetime license token reaches this service ONLY via
the PURIFY_OWNER_LICENSE environment variable (Render secret) and is NEVER
echoed by any endpoint - endpoints return derived status only.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

PUBLIC_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnw2ghC/wBWQqr81pOBBd
caFogUhW0Mjj9qhu56rRg6GsZySapIzXCb7cKfRvm2xV6bA4M907o0/D6f3M3If2
a+xHiDTSszS62eBOVa8YCQsSeEiN41S9dNF8/bAh/Paf4y8eBs+8wq5q7st81a54
FLhwLNUrFu5KB2asb6YlEgKLFkl9e85bJA69eVeFsq9k2a8jIoDD5I5HFzbJD7pw
ixmwi+HpR2j8XoeN3b9MjCT3DD/xHl8U6khnZY72v/IQBJoTDOBd/kSFjX8Iyzvr
79EaJjdfgkYvhC7PipCZtUS6lnEJDih1bGABA5YJlG4SPHVgwOuggXClP71+OwyQ
ywIDAQAB
-----END PUBLIC KEY-----"""

# Mirrors purify/editions.py EDITIONS (features) + the published rate card.
EDITIONS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "label": "Starter",
        "max_users": 10,
        "features": ["approvals", "audit_trail", "local_accounts"],
        "price_zar_yr": 45000,
        "blurb": "One site, first controlled writes: approvals + immutable audit trail.",
    },
    "business": {
        "label": "Business",
        "max_users": 50,
        "features": ["approvals", "audit_trail", "local_accounts",
                     "active_directory", "local_llm", "device_links"],
        "price_zar_yr": 144000,
        "blurb": "AD group roles, local LLM, device + program links: Modbus TCP, OPC-UA, REST.",
    },
    "enterprise": {
        "label": "Enterprise",
        "max_users": 500,
        "features": ["approvals", "audit_trail", "local_accounts",
                     "active_directory", "local_llm", "device_links",
                     "priority_support", "hybrid_llm", "sso_oidc",
                     "custom_connectors"],
        "price_zar_yr": 420000,
        "blurb": "Priority support + roadmap first: hybrid LLM, SSO OIDC/SAML, custom connectors.",
    },
}

DEFAULT_TIER = "starter"


def _b64url_decode(blob: str) -> bytes:
    return base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))


def verify_token(token: str, pem: str = PUBLIC_PEM) -> dict:
    """Raise on any signature/format problem; return the payload dict on success."""
    payload_b64, sig_b64 = token.split(".", 1)
    payload = _b64url_decode(payload_b64)
    from cryptography.exceptions import InvalidSignature  # noqa: F401
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
    pub.verify(_b64url_decode(sig_b64), payload, padding.PKCS1v15(), hashes.SHA256())
    return json.loads(payload)


def license_status(token: Optional[str] = None, pem: Optional[str] = None) -> Dict[str, Any]:
    """Derived status only - never returns the token itself."""
    pem = pem or PUBLIC_PEM  # resolve at call time so tests can swap the key
    if token is None:
        token = os.getenv("PURIFY_OWNER_LICENSE", "").strip()
    if not token:
        return {"valid": False, "reason": "no license loaded on this node"}
    try:
        data = verify_token(token, pem)
        expires = date.fromisoformat(data["expires"])
    except Exception:
        return {"valid": False, "reason": "license missing or signature invalid"}
    today = date.today()
    try:
        grace_end = expires + timedelta(days=int(data.get("grace_days", 0)))
    except OverflowError:
        grace_end = date.max  # lifetime licenses must never overflow the check
    if today > grace_end:
        return {"valid": False, "reason": "expired"}
    tier = data.get("tier", DEFAULT_TIER)
    spec = EDITIONS.get(tier, EDITIONS[DEFAULT_TIER])
    return {
        "valid": True,
        "customer": data.get("customer", ""),
        "tier": tier,
        "label": spec["label"],
        "max_users": data.get("max_users"),
        "expires": data["expires"],
        "features": spec["features"],
    }


def catalog() -> List[Dict[str, Any]]:
    return [{"tier": key, **spec} for key, spec in EDITIONS.items()]
