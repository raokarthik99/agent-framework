import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from agent_framework_devui._auth import (
    AuthenticationError,
    EntraAuthSettings,
    EntraTokenValidator,
)


def test_auth_settings_require_environment(monkeypatch):
    """Auth settings should raise helpful errors when env vars are missing."""
    monkeypatch.delenv("DEVUI_AZURE_AD_TENANT_ID", raising=False)
    monkeypatch.delenv("DEVUI_AZURE_AD_ALLOWED_AUDIENCES", raising=False)

    with pytest.raises(AuthenticationError) as excinfo:
        EntraAuthSettings.from_env()

    assert "DEVUI_AZURE_AD_TENANT_ID" in str(excinfo.value)


@pytest.mark.asyncio
async def test_token_validator_accepts_valid_token():
    """Validator should accept a well-formed token signed with a known key."""
    settings = EntraAuthSettings(
        tenant_id="test-tenant",
        audiences=("api://app-id",),
        authority_host="https://login.microsoftonline.com",
        jwks_cache_ttl_seconds=3600,
        clock_skew_seconds=0,
    )
    validator = EntraTokenValidator(settings)

    key_id = "test-key"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = key_id

    validator._openid_configuration = {
        "issuer": "https://sts.windows.net/test-tenant/",
        "jwks_uri": "https://example.com/jwks",
    }
    validator._jwks = {"keys": [public_jwk]}
    validator._jwks_expires_at = time.monotonic() + 3600

    now = int(time.time())
    payload = {
        "aud": "api://app-id",
        "iss": "https://sts.windows.net/test-tenant/",
        "tid": "test-tenant",
        "oid": "user-123",
        "sub": "user-123",
        "name": "Test User",
        "preferred_username": "user@example.com",
        "scp": "DevUI.Read Weather.Read",
        "exp": now + 300,
        "iat": now - 10,
        "nbf": now - 10,
    }

    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": key_id})

    user = await validator.validate_token(token)
    assert user.object_id == "user-123"
    assert user.tenant_id == "test-tenant"
    assert "DevUI.Read" in user.scopes
    assert user.name == "Test User"


@pytest.mark.asyncio
async def test_token_validator_rejects_incorrect_audience():
    """Validator should reject tokens that do not target the configured audience."""
    settings = EntraAuthSettings(
        tenant_id="test-tenant",
        audiences=("api://app-id",),
        authority_host="https://login.microsoftonline.com",
        jwks_cache_ttl_seconds=3600,
        clock_skew_seconds=0,
    )
    validator = EntraTokenValidator(settings)

    key_id = "test-key"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = key_id

    validator._openid_configuration = {
        "issuer": "https://sts.windows.net/test-tenant/",
        "jwks_uri": "https://example.com/jwks",
    }
    validator._jwks = {"keys": [public_jwk]}
    validator._jwks_expires_at = time.monotonic() + 3600

    now = int(time.time())
    payload = {
        "aud": "api://other-app",
        "iss": "https://sts.windows.net/test-tenant/",
        "tid": "test-tenant",
        "oid": "user-123",
        "sub": "user-123",
        "name": "Test User",
        "preferred_username": "user@example.com",
        "exp": now + 300,
        "iat": now - 10,
        "nbf": now - 10,
    }

    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": key_id})

    validator._jwks_expires_at = time.monotonic() + 3600
    with pytest.raises(AuthenticationError) as excinfo:
        await validator.validate_token(token)

    assert "audience" in str(excinfo.value).lower()
