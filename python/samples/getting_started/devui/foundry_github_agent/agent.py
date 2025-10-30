"""Foundry-based GitHub agent for Agent Framework Debug UI.

This agent uses Azure AI Foundry with Azure CLI authentication and a hosted
MCP tool for GitHub. Make sure to run 'az login' before starting devui.
"""

import os
from dotenv import load_dotenv
from agent_framework import ChatAgent, HostedMCPTool
from agent_framework.devui import get_current_execution_context
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential


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


# Load environment variables
load_dotenv()

github_pat = os.getenv("GITHUB_MCP_PAT")
if not github_pat:
    raise ValueError("GITHUB_MCP_PAT environment variable is required")

agent = ChatAgent(
    name="FoundryGitHubAgent",
    chat_client=AzureAIAgentClient(async_credential=AzureCliCredential()),
    instructions=(
        "You are a helpful assistant that can help users interact with GitHub via a hosted MCP tool. "
        "Always begin each task by calling the `get_user_info` tool to retrieve the current user context. "
        "Use the returned details to personalize your responses and include them when invoking other tools "
        "if they can benefit from user-specific context."
    ),
    tools=[
        HostedMCPTool(
            name="GitHub MCP",
            url="https://api.githubcopilot.com/mcp",
            approval_mode="never_require",
            headers={"Authorization": f"Bearer {github_pat}"},
        ),
        get_user_info,
    ],
)


def main():
    """Launch the Foundry GitHub agent in DevUI."""
    import logging

    from agent_framework.devui import serve

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting Foundry GitHub Agent")
    logger.info("Available at: http://localhost:8080")
    logger.info("Entity ID: agent_FoundryGitHubAgent")
    logger.info("Note: Make sure 'az login' has been run for authentication")

    serve(entities=[agent], port=8080, auto_open=True)


if __name__ == "__main__":
    main()
