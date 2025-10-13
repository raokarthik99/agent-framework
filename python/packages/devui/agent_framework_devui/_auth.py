"""Authentication helpers for the DevUI backend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when an incoming request cannot be authenticated."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class AuthenticatedUser:
    """Lightweight representation of the authenticated principal."""

    object_id: str
    tenant_id: str
    name: str | None
    preferred_username: str | None
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    claims: dict[str, Any]


@dataclass(frozen=True)
class EntraAuthSettings:
    """Configuration required to validate Microsoft Entra ID issued tokens."""

    tenant_id: str
    audiences: tuple[str, ...]
    required_scopes: tuple[str, ...] = ()
    required_app_roles: tuple[str, ...] = ()
    authority_host: str = "https://login.microsoftonline.com"
    jwks_cache_ttl_seconds: int = 60 * 60  # Default: 1 hour
    clock_skew_seconds: int = 60

    @classmethod
    def from_env(cls) -> "EntraAuthSettings":
        """Load settings from environment variables."""
        tenant_id = os.environ.get("DEVUI_AZURE_AD_TENANT_ID")
        if not tenant_id:
            raise AuthenticationError("DEVUI_AZURE_AD_TENANT_ID is not configured on the server.", status_code=500)

        raw_audiences = os.environ.get("DEVUI_AZURE_AD_ALLOWED_AUDIENCES")
        if not raw_audiences:
            raise AuthenticationError(
                "DEVUI_AZURE_AD_ALLOWED_AUDIENCES is not configured on the server.",
                status_code=500,
            )

        audiences = tuple(
            audience.strip()
            for audience in raw_audiences.replace(";", ",").split(",")
            if audience.strip()
        )

        if not audiences:
            raise AuthenticationError(
                "DEVUI_AZURE_AD_ALLOWED_AUDIENCES must contain at least one audience value.",
                status_code=500,
            )

        required_scopes = _parse_environment_list(os.environ.get("DEVUI_AZURE_AD_REQUIRED_SCOPES"))
        required_app_roles = _parse_environment_list(os.environ.get("DEVUI_AZURE_AD_REQUIRED_APP_ROLES"))

        authority_host = os.environ.get("DEVUI_AZURE_AD_AUTHORITY_HOST", "https://login.microsoftonline.com")
        skew_seconds = int(os.environ.get("DEVUI_AZURE_AD_CLOCK_SKEW", "60"))
        cache_seconds = int(os.environ.get("DEVUI_AZURE_AD_JWKS_CACHE_TTL", str(60 * 60)))

        return cls(
            tenant_id=tenant_id,
            audiences=audiences,
            required_scopes=required_scopes,
            required_app_roles=required_app_roles,
            authority_host=authority_host.rstrip("/"),
            jwks_cache_ttl_seconds=cache_seconds,
            clock_skew_seconds=skew_seconds,
        )


class EntraTokenValidator:
    """Validates OAuth2 access tokens issued by Microsoft Entra ID."""

    def __init__(self, settings: EntraAuthSettings) -> None:
        self._settings = settings
        self._openid_configuration: dict[str, Any] | None = None
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at: float = 0
        self._lock = asyncio.Lock()

    @property
    def issuer(self) -> str:
        if not self._openid_configuration:
            raise AuthenticationError("OpenID configuration not initialized.", status_code=500)
        return self._openid_configuration["issuer"]

    @property
    def jwks_uri(self) -> str:
        if not self._openid_configuration:
            raise AuthenticationError("OpenID configuration not initialized.", status_code=500)
        return self._openid_configuration["jwks_uri"]

    @property
    def configuration_url(self) -> str:
        return (
            f"{self._settings.authority_host}/{self._settings.tenant_id}/v2.0/.well-known/openid-configuration"
        )

    async def initialize(self) -> None:
        """Ensure that metadata and signing keys are cached before first request."""
        await self._ensure_openid_configuration()
        await self._ensure_jwks()

    async def validate_token(self, token: str) -> AuthenticatedUser:
        """Validate an incoming bearer token and return the authenticated user."""
        await self._ensure_openid_configuration()
        await self._ensure_jwks()

        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Unable to parse token header: {exc}") from exc

        key_id = unverified_header.get("kid")
        if not key_id:
            raise AuthenticationError("Token header missing 'kid' claim.")

        signing_key = self._get_signing_key(key_id)
        if not signing_key:
            # Force refresh of JWKS if key not found, then retry once.
            await self._ensure_jwks(force_refresh=True)
            signing_key = self._get_signing_key(key_id)
            if not signing_key:
                raise AuthenticationError("Signing key not found for token.")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(signing_key))

        try:
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=["RS256"],
                audience=self._settings.audiences,
                issuer=self.issuer,
                leeway=self._settings.clock_skew_seconds,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError("Token audience not accepted.") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError("Token issuer is not trusted.") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Token validation failed: {exc}") from exc

        tenant_id = claims.get("tid")
        if tenant_id and tenant_id.lower() != self._settings.tenant_id.lower():
            raise AuthenticationError("Token tenant does not match configured tenant.", status_code=403)

        object_id = claims.get("oid") or claims.get("sub")
        if not object_id:
            raise AuthenticationError("Token does not contain required subject identifiers.")

        roles = _ensure_tuple(claims.get("roles"))
        scopes = _ensure_tuple(claims.get("scp"), separator=" ")

        if self._settings.required_scopes and not set(scopes).intersection(self._settings.required_scopes):
            raise AuthenticationError("Token missing required scope.", status_code=403)

        if self._settings.required_app_roles and not set(roles).intersection(self._settings.required_app_roles):
            raise AuthenticationError("Token missing required application role.", status_code=403)

        user = AuthenticatedUser(
            object_id=object_id,
            tenant_id=tenant_id or self._settings.tenant_id,
            name=claims.get("name"),
            preferred_username=claims.get("preferred_username") or claims.get("upn"),
            roles=roles,
            scopes=scopes,
            claims=claims,
        )

        return user

    def _get_signing_key(self, key_id: str) -> dict[str, Any] | None:
        if not self._jwks:
            return None

        for key in self._jwks.get("keys", []):
            if key.get("kid") == key_id:
                return key
        return None

    async def _ensure_openid_configuration(self) -> None:
        if self._openid_configuration:
            return

        async with self._lock:
            if self._openid_configuration:
                return

            url = self.configuration_url
            logger.debug("Fetching OpenID configuration from %s", url)
            data = await self._fetch_json(url)
            if not data:
                raise AuthenticationError("Failed to load OpenID configuration.", status_code=500)
            self._openid_configuration = data

    async def _ensure_jwks(self, *, force_refresh: bool = False) -> None:
        now = time.monotonic()
        if self._jwks and not force_refresh and now < self._jwks_expires_at:
            return

        async with self._lock:
            if self._jwks and not force_refresh and now < self._jwks_expires_at:
                return

            url = self.jwks_uri
            logger.debug("Fetching JWKS from %s", url)
            data = await self._fetch_json(url)
            if not data:
                raise AuthenticationError("Failed to load JWKS signing keys.", status_code=500)

            self._jwks = data
            self._jwks_expires_at = now + self._settings.jwks_cache_ttl_seconds

    @staticmethod
    async def _fetch_json(url: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error fetching %s: %s", url, exc)
            raise AuthenticationError(f"Failed to fetch authentication metadata: {exc}") from exc
        except httpx.RequestError as exc:
            logger.error("Network error fetching %s: %s", url, exc)
            raise AuthenticationError(f"Unable to reach authentication metadata endpoint: {exc}") from exc


def _ensure_tuple(value: Any, *, separator: str = ",") -> tuple[str, ...]:
    """Convert JWT claim values to a tuple."""
    if not value:
        return ()

    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item)

    if isinstance(value, str):
        return tuple(segment.strip() for segment in value.split(separator) if segment.strip())

    return (str(value),)


def _parse_environment_list(raw_value: str | None) -> tuple[str, ...]:
    """Parse whitespace/comma/semicolon separated environment variable values."""
    if not raw_value:
        return ()

    # Split on commas, semicolons, or whitespace, collapsing consecutive separators.
    values = re.split(r"[,\s;]+", raw_value.strip())
    return tuple(value for value in values if value)
