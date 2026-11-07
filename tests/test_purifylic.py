"""Pytest-style tests for the Purify bridge (purifylic) inside Smash AI Pro.

These tests sign their OWN throwaway RSA keypair - the real vendor private key
is never used or referenced here.
Run:  python3 -m pytest tests/test_purifylic.py -q   (from repo root)
"""
import base64
import json
import os
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import purifylic


def b64url(blob: bytes) -> str:
    return base64.urlsafe_b64encode(blob).decode().rstrip("=")


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, pub.decode()


def sign(priv, payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True).encode()
    return f"{b64url(blob)}.{b64url(priv.sign(blob, padding.PKCS1v15(), hashes.SHA256()))}"


def payload(days=365, tier="enterprise", seats=500, expires=None, grace=14):
    today = date.today()
    return {
        "license_id": "test-1",
        "customer": "Test Co",
        "tier": tier,
        "max_users": seats,
        "issued": today.isoformat(),
        "expires": expires or (today + timedelta(days=days)).isoformat(),
        "grace_days": grace,
        "edition": "onprem",
    }


def test_verify_roundtrip(keypair):
    priv, pub = keypair
    data = payload()
    assert purifylic.verify_token(sign(priv, data), pub)["customer"] == "Test Co"


def test_tampered_signature_rejected(keypair):
    priv, pub = keypair
    token = sign(priv, payload())
    head, sig = token.split(".", 1)
    bad = head + "." + sig[:-4] + ("AAAA" if not sig.endswith("AAAA") else "BBBB")
    with pytest.raises(Exception):
        purifylic.verify_token(bad, pub)


def test_status_happy_path(keypair):
    priv, pub = keypair
    st = purifylic.license_status(token=sign(priv, payload()), pem=pub)
    assert st["valid"] is True and st["tier"] == "enterprise"
    assert st["max_users"] == 500 and len(st["features"]) == 10


def test_expired_rejected(keypair):
    priv, pub = keypair
    old = (date.today() - timedelta(days=400)).isoformat()
    st = purifylic.license_status(token=sign(priv, payload(expires=old, grace=14)), pem=pub)
    assert st == {"valid": False, "reason": "expired"}


def test_lifetime_expiry_never_overflows(keypair):
    priv, pub = keypair
    st = purifylic.license_status(token=sign(priv, payload(expires="9999-12-31", grace=30)), pem=pub)
    assert st["valid"] is True and st["expires"] == "9999-12-31"


def test_no_token_means_invalid(monkeypatch):
    monkeypatch.delenv("PURIFY_OWNER_LICENSE", raising=False)
    st = purifylic.license_status()
    assert st["valid"] is False and "no license" in st["reason"]


def test_env_token_used(monkeypatch, keypair):
    priv, pub = keypair
    monkeypatch.setenv("PURIFY_OWNER_LICENSE", sign(priv, payload(tier="business", seats=50)))
    monkeypatch.setattr(purifylic, "PUBLIC_PEM", pub)
    st = purifylic.license_status()
    assert st["valid"] is True and st["tier"] == "business" and st["max_users"] == 50


def test_status_never_echoes_token(keypair):
    priv, pub = keypair
    token = sign(priv, payload())
    st = purifylic.license_status(token=token, pem=pub)
    assert token not in json.dumps(st)


def test_catalog_three_tiers():
    cat = purifylic.catalog()
    assert [c["tier"] for c in cat] == ["starter", "business", "enterprise"]
    assert cat[2]["price_zar_yr"] == 420000 and len(cat[2]["features"]) == 10


def test_unknown_tier_falls_back(keypair):
    priv, pub = keypair
    st = purifylic.license_status(token=sign(priv, payload(tier="galactic")), pem=pub)
    assert st["valid"] is True and st["label"] == "Starter"
