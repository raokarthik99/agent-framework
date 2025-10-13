# DevUI Backend

This directory contains the FastAPI server that powers the DevUI experience. It provides an OpenAI-compatible API surface, entity discovery, streaming responses, and now Microsoft Entra-protected endpoints.

## Quick Start

1. **Install dependencies**

   ```bash
   cd python
   uv sync --dev
   source .venv/bin/activate
   cd packages/devui
   ```

2. **Configure environment variables**

   Copy the sample file and fill in your Microsoft Entra values:

   ```bash
   cp agent_framework_devui/.env.example agent_framework_devui/.env
   ```

   | Variable | Description |
   | --- | --- |
   | `DEVUI_AZURE_AD_TENANT_ID` | Tenant GUID that issues access tokens. |
   | `DEVUI_AZURE_AD_ALLOWED_AUDIENCES` | Accepted audience values (application ID URIs or client IDs). Tokens must match at least one entry. |
   | `DEVUI_AZURE_AD_REQUIRED_SCOPES` *(optional)* | Delegated scopes the token must include in `scp`. Any one scope satisfies the check. |
   | `DEVUI_AZURE_AD_REQUIRED_APP_ROLES` *(optional)* | Application roles the token must include in `roles`. Any one role satisfies the check. |
   | `DEVUI_AZURE_AD_AUTHORITY_HOST` *(optional)* | Override for sovereign clouds (defaults to `https://login.microsoftonline.com`). |
   | `DEVUI_AZURE_AD_CLOCK_SKEW` *(optional)* | Allowed clock drift in seconds (default `60`). |
   | `DEVUI_AZURE_AD_JWKS_CACHE_TTL` *(optional)* | JWKS cache lifetime in seconds (default `3600`). |

   The server automatically loads `.env` and `.env.local` from either the repository root or this directory, so you rarely need to export variables manually.

   **Audience tips:** Microsoft Entra issues access tokens with an `aud` claim matching the resource application's identifier URI (e.g. `api://...`). Client credential flows may instead present the app's client ID GUID. List every accepted identifier in `DEVUI_AZURE_AD_ALLOWED_AUDIENCES`, separated by commas, semicolons, or whitespace.

   **Scope and role enforcement:** Set `DEVUI_AZURE_AD_REQUIRED_SCOPES` when issuing delegated tokens (via MSAL public clients or the DevUI frontend). Tokens must contain at least one matching scope in the `scp` claim. For service-to-service scenarios, configure `DEVUI_AZURE_AD_REQUIRED_APP_ROLES` so client credential tokens must carry at least one of the listed app roles in the `roles` claim.

3. **Run the backend**

   ```bash
   uv run devui --port 8080
   ```

   All protected endpoints (`/health`, `/v1/**`) now require an `Authorization: Bearer <token>` header. Use the DevUI frontend (which requests a backend scope) or any client capable of acquiring Microsoft Entra access tokens for the configured audience.

## Testing

```bash
uv run pytest tests/test_auth.py
```

> The default `uv` environment does not install `pytest`. If needed, run `uv pip install pytest` or include the `dev` extras (`uv pip install .[dev]`) before executing the test suite.

## Telemetry

Set the optional variables in `.env` to enable OpenTelemetry export:

```dotenv
ENABLE_OTEL=true
ENABLE_SENSITIVE_DATA=true
OTLP_ENDPOINT=http://localhost:4317
```

These values are only applied when not already defined in your environment.

## Additional Resources

- Frontend setup instructions: `frontend/README.md`
- High-level project overview: `../README.md`
- Developer quick-start guide: `../dev.md`
