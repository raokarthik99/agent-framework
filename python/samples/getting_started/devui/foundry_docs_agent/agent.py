# Copyright (c) Microsoft. All rights reserved.
"""Foundry-based docs agent for Agent Framework Debug UI.

This agent uses Azure AI Foundry with Azure CLI authentication.
Make sure to run 'az login' before starting devui.
"""

import os
from typing import Annotated

from agent_framework import ChatAgent, HostedMCPTool
from agent_framework.devui import get_current_execution_context
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field


# region personalization helpers
def get_user_info() -> dict[str, str | bool | None]:
    """Return user identity details from the DevUI execution context for personalization."""
    context = get_current_execution_context()
    if not context:
        return {
            "name": None,
            "preferred_username": None,
            "object_id": None,
            "has_delegated_access_token": False,
        }

    user = context.user
    return {
        "name": user.name if user else None,
        "preferred_username": user.preferred_username if user else None,
        "object_id": user.object_id if user else None,
        "has_delegated_access_token": bool(context.access_token),
    }


# Agent instance following Agent Framework conventions
agent = ChatAgent(
    name="FoundryDocsAgent",
    chat_client=AzureAIAgentClient(
        project_endpoint=os.environ.get("AZURE_AI_PROJECT_ENDPOINT"),
        model_deployment_name=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME"),
        async_credential=AzureCliCredential(),
    ),
    instructions=(
        "You are a helpful assistant that can help with Microsoft documentation questions. "
        "Always begin each task by calling the `get_user_info` tool to retrieve the current user context. "
        "Use the returned details to personalize your responses and include them when invoking other tools "
        "if they can benefit from user-specific context."
    ),
    tools=[
        HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            approval_mode="never_require",
        ),
        get_user_info,
    ],
)


def main():
    """Launch the Foundry weather agent in DevUI."""
    import logging

    from agent_framework.devui import serve

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting Foundry Docs Agent")
    logger.info("Available at: http://localhost:8080")
    logger.info("Entity ID: agent_FoundryDocsAgent")
    logger.info("Note: Make sure 'az login' has been run for authentication")

    # Launch server with the agent
    serve(entities=[agent], port=8080, auto_open=True)


if __name__ == "__main__":
    main()
