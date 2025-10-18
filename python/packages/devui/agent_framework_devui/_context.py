# Copyright (c) Microsoft. All rights reserved.

"""Execution context utilities for passing authenticated user data to agents."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from ._auth import AuthenticatedUser


EXECUTION_CONTEXT_SHARED_STATE_KEY = "af.devui.execution_context"
EXECUTION_CONTEXT_ATTR = "_devui_execution_context"
_current_execution_context: ContextVar[ExecutionContext | None] = ContextVar(
    "agent_framework_devui_execution_context",
    default=None,
)


@dataclass(slots=True)
class ExecutionContext:
    """Lightweight container for per-request execution context."""

    user: AuthenticatedUser | None = None
    access_token: str | None = None

    def user_identifier(self) -> str | None:
        """Return a stable identifier for downstream attribution."""
        if not self.user:
            return None
        return self.user.preferred_username or self.user.object_id

    def to_metadata(self) -> dict[str, Any]:
        """Convert context to safe metadata for agent/chat providers."""
        if not self.user:
            return {}

        metadata = {
            "user_object_id": self.user.object_id,
            "user_tenant_id": self.user.tenant_id,
            "user_roles": list(self.user.roles),
            "user_scopes": list(self.user.scopes),
        }

        if self.user.name:
            metadata["user_name"] = self.user.name
        if self.user.preferred_username:
            metadata["user_principal_name"] = self.user.preferred_username

        return metadata

    def to_tool_kwargs(self) -> dict[str, Any]:
        """Return kwargs that can be forwarded to agent tools."""
        payload: dict[str, Any] = {}

        if self.user:
            payload["user_context"] = {
                "object_id": self.user.object_id,
                "tenant_id": self.user.tenant_id,
                "name": self.user.name,
                "preferred_username": self.user.preferred_username,
                "roles": list(self.user.roles),
                "scopes": list(self.user.scopes),
                "claims": dict(self.user.claims),
            }

        if self.access_token:
            payload["user_access_token"] = self.access_token

        return payload


def set_current_execution_context(context: ExecutionContext | None) -> Token:
    """Set current execution context for the running task."""
    return _current_execution_context.set(context)


def reset_current_execution_context(token: Token) -> None:
    """Reset execution context to previous value."""
    _current_execution_context.reset(token)


def get_current_execution_context() -> ExecutionContext | None:
    """Return the execution context associated with the running task."""
    return _current_execution_context.get()


def get_current_user_context() -> dict[str, Any] | None:
    """Return sanitized user context for convenience."""
    context = get_current_execution_context()
    if not context:
        return None
    return context.to_tool_kwargs().get("user_context")


def get_current_user_access_token() -> str | None:
    """Return the current user's bearer token, if available."""
    context = get_current_execution_context()
    if not context:
        return None
    return context.access_token
