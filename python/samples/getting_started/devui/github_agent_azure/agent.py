# Copyright (c) Microsoft. All rights reserved.
"""GitHub agent for Agent Framework Debug UI using MCPStreamableHTTPTool.

This agent uses Azure OpenAI with Azure CLI authentication and connects to GitHub
via MCP (Model Context Protocol) using MCPStreamableHTTPTool.
Make sure to run 'az login' before starting devui and set GITHUB_MCP_PAT environment variable.
"""

import asyncio
import os
import uvicorn
from dotenv import load_dotenv

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_devui import DevServer
from azure.identity import AzureCliCredential

# Load environment variables
load_dotenv()

async def main():
    """Main async function that sets up the GitHub agent with MCP integration."""
    chat_client = AzureOpenAIChatClient(
        credential=AzureCliCredential()
    )

    # Get GitHub PAT token from environment
    github_pat = os.getenv("GITHUB_MCP_PAT")
    if not github_pat:
        raise ValueError("GITHUB_MCP_PAT environment variable is required")

    async with MCPStreamableHTTPTool(
        name="GitHub MCP",
        url="https://api.githubcopilot.com/mcp/",
        headers={"Authorization": f"Bearer {github_pat}"},
        chat_client=chat_client,
    ) as mcp:
        agent = ChatAgent(
            chat_client=chat_client,
            name="GitHubAgentAzure",
            instructions="You are a helpful assistant that can help users interact with GitHub using available MCP tools. Use the GitHub MCP tools to perform various GitHub operations like searching repositories, managing issues, working with pull requests, and more.",
            tools=list(mcp.functions),
        )

        server = DevServer(host="localhost", port=8080, ui_enabled=True)
        server.register_entities([agent])
        app = server.get_app()

        config = uvicorn.Config(app, host="localhost", port=8080, log_level="info", loop="asyncio")
        await uvicorn.Server(config).serve()


def main_sync():
    """Synchronous main function that handles asyncio event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(main())
        else:
            loop.run_until_complete(main())
    except RuntimeError:
        asyncio.run(main())


if __name__ == "__main__":
    main_sync()
