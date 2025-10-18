# Copyright (c) Microsoft. All rights reserved.
"""Foundry-based weather agent for Agent Framework Debug UI.

This agent uses Azure AI Foundry with Azure CLI authentication.
Make sure to run 'az login' before starting devui.
"""

import os
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.devui import get_current_execution_context
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field


def _format_user_identity() -> str | None:
    """Return a friendly display name for the signed-in user if we have one."""
    context = get_current_execution_context()
    if not context or not context.user:
        return None

    user = context.user
    return user.name or user.preferred_username or user.object_id


def _has_delegated_token() -> bool:
    """Return whether a bearer token is available for delegated calls."""
    context = get_current_execution_context()
    return bool(context and context.access_token)


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = 22

    identity = _format_user_identity()
    personalization = (
        f"{identity}, here's your personalized update. " if identity else ""
    )
    delegated_note = (
        " (delegated access token available for downstream APIs)"
        if _has_delegated_token()
        else ""
    )

    return (
        f"{personalization}"
        f"The weather in {location} is {conditions[0]} with a high of {temperature}°C."
        f"{delegated_note}"
    )


def get_forecast(
    location: Annotated[
        str, Field(description="The location to get the forecast for.")
    ],
    days: Annotated[int, Field(description="Number of days for forecast")] = 3,
) -> str:
    """Get weather forecast for multiple days."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    forecast: list[str] = []

    for day in range(1, days + 1):
        condition = conditions[day % len(conditions)]
        temp = 18 + day
        forecast.append(f"Day {day}: {condition}, {temp}°C")

    identity = _format_user_identity()
    intro = f"{identity}, here's your multi-day forecast:\n" if identity else ""
    delegated_note = (
        "\n\nNote: Delegated access token supplied — call downstream services on behalf of the user."
        if _has_delegated_token()
        else ""
    )

    return (
        intro
        + f"Weather forecast for {location}:\n"
        + "\n".join(forecast)
        + delegated_note
    )


# Agent instance following Agent Framework conventions
agent = ChatAgent(
    name="FoundryWeatherAgent",
    chat_client=AzureAIAgentClient(
        async_credential=AzureCliCredential(),
    ),
    instructions="""
    You are a weather assistant using Azure AI Foundry models. You can provide
    current weather information and forecasts for any location. Always be helpful
    and provide detailed weather information when asked. Personalize answers when
    user details are supplied through the user_context tool argument, and acknowledge
    when a delegated access token is available for downstream calls. Make sure to greet the user by name if the tool response contains it.
    """,
    tools=[get_weather, get_forecast],
)


def main():
    """Launch the Foundry weather agent in DevUI."""
    import logging

    from agent_framework.devui import serve

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting Foundry Weather Agent")
    logger.info("Available at: http://localhost:8080")
    logger.info("Entity ID: agent_FoundryWeatherAgent")
    logger.info("Note: Make sure 'az login' has been run for authentication")

    # Launch server with the agent
    serve(entities=[agent], port=8080, auto_open=True)


if __name__ == "__main__":
    main()
