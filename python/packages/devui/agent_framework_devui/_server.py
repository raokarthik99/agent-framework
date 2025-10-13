# Copyright (c) Microsoft. All rights reserved.

"""FastAPI server implementation."""

import inspect
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ._auth import AuthenticatedUser, AuthenticationError, EntraAuthSettings, EntraTokenValidator
from ._discovery import EntityDiscovery
from ._executor import AgentFrameworkExecutor
from ._mapper import MessageMapper
from .models import AgentFrameworkRequest, OpenAIError
from .models._discovery_models import DiscoveryResponse, EntityInfo

logger = logging.getLogger(__name__)

_env_candidates = [
    Path(".env"),
    Path(".env.local"),
]

_package_dir = Path(__file__).resolve().parent
_env_candidates.extend(
    [
        _package_dir / ".env",
        _package_dir / ".env.local",
    ]
)

_loaded_env_files: list[str] = []
for candidate in _env_candidates:
    try:
        loaded = load_dotenv(dotenv_path=str(candidate), override=False)
    except OSError:
        loaded = False
    if loaded:
        _loaded_env_files.append(str(candidate))

if _loaded_env_files:
    logger.debug("Loaded environment variables from %s", ", ".join(_loaded_env_files))


class DevServer:
    """Development Server - OpenAI compatible API server for debugging agents."""

    def __init__(
        self,
        entities_dir: str | None = None,
        port: int = 8080,
        host: str = "127.0.0.1",
        cors_origins: list[str] | None = None,
        ui_enabled: bool = True,
    ) -> None:
        """Initialize the development server.

        Args:
            entities_dir: Directory to scan for entities
            port: Port to run server on
            host: Host to bind server to
            cors_origins: List of allowed CORS origins
            ui_enabled: Whether to enable the UI
        """
        self.entities_dir = entities_dir
        self.port = port
        self.host = host
        self.cors_origins = cors_origins or ["*"]
        self.ui_enabled = ui_enabled
        self.executor: AgentFrameworkExecutor | None = None
        self._app: FastAPI | None = None
        self._pending_entities: list[Any] | None = None

    async def _ensure_executor(self) -> AgentFrameworkExecutor:
        """Ensure executor is initialized."""
        if self.executor is None:
            logger.info("Initializing Agent Framework executor...")

            # Create components directly
            entity_discovery = EntityDiscovery(self.entities_dir)
            message_mapper = MessageMapper()
            self.executor = AgentFrameworkExecutor(entity_discovery, message_mapper)

            # Discover entities from directory
            discovered_entities = await self.executor.discover_entities()
            logger.info(f"Discovered {len(discovered_entities)} entities from directory")

            # Register any pending in-memory entities
            if self._pending_entities:
                discovery = self.executor.entity_discovery
                for entity in self._pending_entities:
                    try:
                        entity_info = await discovery.create_entity_info_from_object(entity, source="in-memory")
                        discovery.register_entity(entity_info.id, entity_info, entity)
                        logger.info(f"Registered in-memory entity: {entity_info.id}")
                    except Exception as e:
                        logger.error(f"Failed to register in-memory entity: {e}")
                self._pending_entities = None  # Clear after registration

            # Get the final entity count after all registration
            all_entities = self.executor.entity_discovery.list_entities()
            logger.info(f"Total entities available: {len(all_entities)}")

        return self.executor

    async def _cleanup_entities(self) -> None:
        """Cleanup entity resources (close clients, credentials, etc.)."""
        if not self.executor:
            return

        logger.info("Cleaning up entity resources...")
        entities = self.executor.entity_discovery.list_entities()
        closed_count = 0

        for entity_info in entities:
            try:
                entity_obj = self.executor.entity_discovery.get_entity_object(entity_info.id)
                if entity_obj and hasattr(entity_obj, "chat_client"):
                    client = entity_obj.chat_client
                    if hasattr(client, "close") and callable(client.close):
                        if inspect.iscoroutinefunction(client.close):
                            await client.close()
                        else:
                            client.close()
                        closed_count += 1
                        logger.debug(f"Closed client for entity: {entity_info.id}")
            except Exception as e:
                logger.warning(f"Error closing entity {entity_info.id}: {e}")

        if closed_count > 0:
            logger.info(f"Closed {closed_count} entity client(s)")

    def create_app(self) -> FastAPI:
        """Create the FastAPI application."""

        try:
            auth_settings = EntraAuthSettings.from_env()
        except AuthenticationError as exc:
            logger.error("Authentication configuration error: %s", exc.message)
            raise RuntimeError(exc.message) from exc

        token_validator = EntraTokenValidator(auth_settings)
        protected_prefixes = ("/v1",)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            # Startup
            logger.info("Starting Agent Framework Server")
            await self._ensure_executor()
            try:
                await token_validator.initialize()
            except AuthenticationError as exc:
                logger.error("Failed to initialize authentication: %s", exc.message)
                raise RuntimeError(exc.message) from exc

            app.state.token_validator = token_validator
            app.state.auth_settings = auth_settings
            yield
            # Shutdown
            logger.info("Shutting down Agent Framework Server")

            # Cleanup entity resources (e.g., close credentials, clients)
            if self.executor:
                await self._cleanup_entities()

        app = FastAPI(
            title="Agent Framework Server",
            description="OpenAI-compatible API server for Agent Framework and other AI frameworks",
            version="1.0.0",
            lifespan=lifespan,
        )

        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.middleware("http")
        async def enforce_authentication(request: Request, call_next):
            if request.method == "OPTIONS":
                return await call_next(request)

            endpoint = request.scope.get("endpoint")
            if endpoint is None:
                route = request.scope.get("route")
                endpoint = getattr(route, "endpoint", None) if route else None

            if endpoint and getattr(endpoint, "_allow_anonymous", False):
                return await call_next(request)

            path = request.url.path
            is_protected = any(
                path == prefix or path.startswith(f"{prefix}/") for prefix in protected_prefixes
            )
            if not is_protected:
                return await call_next(request)

            authorization = request.headers.get("Authorization")
            if not authorization:
                return JSONResponse(status_code=401, content={"detail": "Authorization header missing."})

            scheme, _, credentials = authorization.partition(" ")
            if scheme.lower() != "bearer" or not credentials.strip():
                return JSONResponse(status_code=401, content={"detail": "Bearer token required."})

            token = credentials.strip()
            try:
                user: AuthenticatedUser = await token_validator.validate_token(token)
            except AuthenticationError as exc:
                logger.warning("Authentication failed for %s: %s", path, exc.message)
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

            request.state.user = user
            return await call_next(request)

        self._register_routes(app)
        self._mount_ui(app)

        return app

    def _register_routes(self, app: FastAPI) -> None:
        """Register API routes."""

        def allow_anonymous(handler):
            """Mark an endpoint as not requiring authentication."""
            setattr(handler, "_allow_anonymous", True)
            return handler

        @app.get("/health")
        @allow_anonymous
        async def health_check() -> dict[str, Any]:
            """Health check endpoint."""
            executor = await self._ensure_executor()
            # Use list_entities() to avoid re-discovering and re-registering entities
            entities = executor.entity_discovery.list_entities()

            return {"status": "healthy", "entities_count": len(entities), "framework": "agent_framework"}

        @app.get("/v1/entities", response_model=DiscoveryResponse)
        async def discover_entities() -> DiscoveryResponse:
            """List all registered entities."""
            try:
                executor = await self._ensure_executor()
                # Use list_entities() instead of discover_entities() to get already-registered entities
                entities = executor.entity_discovery.list_entities()
                return DiscoveryResponse(entities=entities)
            except Exception as e:
                logger.error(f"Error listing entities: {e}")
                raise HTTPException(status_code=500, detail=f"Entity listing failed: {e!s}") from e

        @app.get("/v1/entities/{entity_id}/info", response_model=EntityInfo)
        async def get_entity_info(entity_id: str) -> EntityInfo:
            """Get detailed information about a specific entity."""
            try:
                executor = await self._ensure_executor()
                entity_info = executor.get_entity_info(entity_id)

                if not entity_info:
                    raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

                # For workflows, populate additional detailed information
                if entity_info.type == "workflow":
                    entity_obj = executor.entity_discovery.get_entity_object(entity_id)
                    if entity_obj:
                        # Get workflow structure
                        workflow_dump = None
                        if hasattr(entity_obj, "to_dict") and callable(getattr(entity_obj, "to_dict", None)):
                            try:
                                workflow_dump = entity_obj.to_dict()  # type: ignore[attr-defined]
                            except Exception:
                                workflow_dump = None
                        elif hasattr(entity_obj, "to_json") and callable(getattr(entity_obj, "to_json", None)):
                            try:
                                raw_dump = entity_obj.to_json()  # type: ignore[attr-defined]
                            except Exception:
                                workflow_dump = None
                            else:
                                if isinstance(raw_dump, (bytes, bytearray)):
                                    try:
                                        raw_dump = raw_dump.decode()
                                    except Exception:
                                        raw_dump = raw_dump.decode(errors="replace")
                                if isinstance(raw_dump, str):
                                    try:
                                        parsed_dump = json.loads(raw_dump)
                                    except Exception:
                                        workflow_dump = raw_dump
                                    else:
                                        workflow_dump = parsed_dump if isinstance(parsed_dump, dict) else raw_dump
                                else:
                                    workflow_dump = raw_dump
                        elif hasattr(entity_obj, "__dict__"):
                            workflow_dump = {k: v for k, v in entity_obj.__dict__.items() if not k.startswith("_")}

                        # Get input schema information
                        input_schema = {}
                        input_type_name = "Unknown"
                        start_executor_id = ""

                        try:
                            from ._utils import (
                                extract_executor_message_types,
                                generate_input_schema,
                                select_primary_input_type,
                            )

                            start_executor = entity_obj.get_start_executor()
                        except Exception as e:
                            logger.debug(f"Could not extract input info for workflow {entity_id}: {e}")
                        else:
                            if start_executor:
                                start_executor_id = getattr(start_executor, "executor_id", "") or getattr(
                                    start_executor, "id", ""
                                )

                                message_types = extract_executor_message_types(start_executor)
                                input_type = select_primary_input_type(message_types)

                                if input_type:
                                    input_type_name = getattr(input_type, "__name__", str(input_type))

                                    # Generate schema using comprehensive schema generation
                                    input_schema = generate_input_schema(input_type)

                        if not input_schema:
                            input_schema = {"type": "string"}
                            if input_type_name == "Unknown":
                                input_type_name = "string"

                        # Get executor list
                        executor_list = []
                        if hasattr(entity_obj, "executors") and entity_obj.executors:
                            executor_list = [getattr(ex, "executor_id", str(ex)) for ex in entity_obj.executors]

                        # Create copy of entity info and populate workflow-specific fields
                        update_payload: dict[str, Any] = {
                            "workflow_dump": workflow_dump,
                            "input_schema": input_schema,
                            "input_type_name": input_type_name,
                            "start_executor_id": start_executor_id,
                        }
                        if executor_list:
                            update_payload["executors"] = executor_list
                        return entity_info.model_copy(update=update_payload)

                # For non-workflow entities, return as-is
                return entity_info

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting entity info for {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get entity info: {e!s}") from e

        @app.post("/v1/entities/add")
        async def add_entity(request: dict[str, Any]) -> dict[str, Any]:
            """Add entity from URL."""
            try:
                url = request.get("url")
                metadata = request.get("metadata", {})

                if not url:
                    raise HTTPException(status_code=400, detail="URL is required")

                logger.info(f"Attempting to add entity from URL: {url}")
                executor = await self._ensure_executor()
                entity_info, error_msg = await executor.entity_discovery.fetch_remote_entity(url, metadata)

                if not entity_info:
                    # Sanitize error message - only return safe, user-friendly errors
                    logger.error(f"Failed to fetch or validate entity from {url}: {error_msg}")
                    safe_error = error_msg if error_msg else "Failed to fetch or validate entity"
                    raise HTTPException(status_code=400, detail=safe_error)

                logger.info(f"Successfully added entity: {entity_info.id}")
                return {"success": True, "entity": entity_info.model_dump()}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error adding entity: {e}", exc_info=True)
                # Don't expose internal error details to client
                raise HTTPException(
                    status_code=500, detail="An unexpected error occurred while adding the entity"
                ) from e

        @app.delete("/v1/entities/{entity_id}")
        async def remove_entity(entity_id: str) -> dict[str, Any]:
            """Remove entity by ID."""
            try:
                executor = await self._ensure_executor()

                # Cleanup entity resources before removal
                try:
                    entity_obj = executor.entity_discovery.get_entity_object(entity_id)
                    if entity_obj and hasattr(entity_obj, "chat_client"):
                        client = entity_obj.chat_client
                        if hasattr(client, "close") and callable(client.close):
                            if inspect.iscoroutinefunction(client.close):
                                await client.close()
                            else:
                                client.close()
                            logger.info(f"Closed client for entity: {entity_id}")
                except Exception as e:
                    logger.warning(f"Error closing entity {entity_id} during removal: {e}")

                # Remove entity from registry
                success = executor.entity_discovery.remove_remote_entity(entity_id)

                if success:
                    return {"success": True}
                raise HTTPException(status_code=404, detail="Entity not found or cannot be removed")

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error removing entity {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to remove entity: {e!s}") from e

        @app.post("/v1/responses")
        async def create_response(request: AgentFrameworkRequest, raw_request: Request) -> Any:
            """OpenAI Responses API endpoint."""
            try:
                raw_body = await raw_request.body()
                logger.info(f"Raw request body: {raw_body.decode()}")
                logger.info(f"Parsed request: model={request.model}, extra_body={request.extra_body}")

                # Get entity_id using the new method
                entity_id = request.get_entity_id()
                logger.info(f"Extracted entity_id: {entity_id}")

                if not entity_id:
                    error = OpenAIError.create(f"Missing entity_id. Request extra_body: {request.extra_body}")
                    return JSONResponse(status_code=400, content=error.to_dict())

                # Get executor and validate entity exists
                executor = await self._ensure_executor()
                try:
                    entity_info = executor.get_entity_info(entity_id)
                    logger.info(f"Found entity: {entity_info.name} ({entity_info.type})")
                except Exception:
                    error = OpenAIError.create(f"Entity not found: {entity_id}")
                    return JSONResponse(status_code=404, content=error.to_dict())

                # Execute request
                if request.stream:
                    return StreamingResponse(
                        self._stream_execution(executor, request),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "Access-Control-Allow-Origin": "*",
                        },
                    )
                return await executor.execute_sync(request)

            except Exception as e:
                logger.error(f"Error executing request: {e}")
                error = OpenAIError.create(f"Execution failed: {e!s}")
                return JSONResponse(status_code=500, content=error.to_dict())

        # ========================================
        # OpenAI Conversations API (Standard)
        # ========================================

        @app.post("/v1/conversations")
        async def create_conversation(request_data: dict[str, Any]) -> dict[str, Any]:
            """Create a new conversation - OpenAI standard."""
            try:
                metadata = request_data.get("metadata")
                executor = await self._ensure_executor()
                conversation = executor.conversation_store.create_conversation(metadata=metadata)
                return conversation.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error creating conversation: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create conversation: {e!s}") from e

        @app.get("/v1/conversations")
        async def list_conversations(agent_id: str | None = None) -> dict[str, Any]:
            """List conversations, optionally filtered by agent_id."""
            try:
                executor = await self._ensure_executor()

                if agent_id:
                    # Filter by agent_id metadata
                    conversations = executor.conversation_store.list_conversations_by_metadata({"agent_id": agent_id})
                else:
                    # Return all conversations (for InMemoryStore, list all)
                    # Note: This assumes list_conversations_by_metadata({}) returns all
                    conversations = executor.conversation_store.list_conversations_by_metadata({})

                return {
                    "object": "list",
                    "data": [conv.model_dump() for conv in conversations],
                    "has_more": False,
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error listing conversations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list conversations: {e!s}") from e

        @app.get("/v1/conversations/{conversation_id}")
        async def retrieve_conversation(conversation_id: str) -> dict[str, Any]:
            """Get conversation - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                conversation = executor.conversation_store.get_conversation(conversation_id)
                if not conversation:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                return conversation.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get conversation: {e!s}") from e

        @app.post("/v1/conversations/{conversation_id}")
        async def update_conversation(conversation_id: str, request_data: dict[str, Any]) -> dict[str, Any]:
            """Update conversation metadata - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                metadata = request_data.get("metadata", {})
                conversation = executor.conversation_store.update_conversation(conversation_id, metadata=metadata)
                return conversation.model_dump()
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update conversation: {e!s}") from e

        @app.delete("/v1/conversations/{conversation_id}")
        async def delete_conversation(conversation_id: str) -> dict[str, Any]:
            """Delete conversation - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                result = executor.conversation_store.delete_conversation(conversation_id)
                return result.model_dump()
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete conversation: {e!s}") from e

        @app.post("/v1/conversations/{conversation_id}/items")
        async def create_conversation_items(conversation_id: str, request_data: dict[str, Any]) -> dict[str, Any]:
            """Add items to conversation - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                items = request_data.get("items", [])
                conv_items = await executor.conversation_store.add_items(conversation_id, items=items)
                return {"object": "list", "data": [item.model_dump() for item in conv_items]}
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error adding items to conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add items: {e!s}") from e

        @app.get("/v1/conversations/{conversation_id}/items")
        async def list_conversation_items(
            conversation_id: str, limit: int = 100, after: str | None = None, order: str = "asc"
        ) -> dict[str, Any]:
            """List conversation items - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                items, has_more = await executor.conversation_store.list_items(
                    conversation_id, limit=limit, after=after, order=order
                )
                return {
                    "object": "list",
                    "data": [item.model_dump() for item in items],
                    "has_more": has_more,
                }
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error listing items for conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list items: {e!s}") from e

        @app.get("/v1/conversations/{conversation_id}/items/{item_id}")
        async def retrieve_conversation_item(conversation_id: str, item_id: str) -> dict[str, Any]:
            """Get specific conversation item - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                item = executor.conversation_store.get_item(conversation_id, item_id)
                if not item:
                    raise HTTPException(status_code=404, detail="Item not found")
                return item.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting item {item_id} from conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get item: {e!s}") from e

    async def _stream_execution(
        self, executor: AgentFrameworkExecutor, request: AgentFrameworkRequest
    ) -> AsyncGenerator[str, None]:
        """Stream execution directly through executor."""
        try:
            # Collect events for final response.completed event
            events = []

            # Stream all events
            async for event in executor.execute_streaming(request):
                events.append(event)

                # IMPORTANT: Check model_dump_json FIRST because to_json() can have newlines (pretty-printing)
                # which breaks SSE format. model_dump_json() returns single-line JSON.
                if hasattr(event, "model_dump_json"):
                    payload = event.model_dump_json()  # type: ignore[attr-defined]
                elif hasattr(event, "to_json") and callable(getattr(event, "to_json", None)):
                    payload = event.to_json()  # type: ignore[attr-defined]
                    # Strip newlines from pretty-printed JSON for SSE compatibility
                    payload = payload.replace("\n", "").replace("\r", "")
                elif isinstance(event, dict):
                    # Handle plain dict events (e.g., error events from executor)
                    payload = json.dumps(event)
                elif hasattr(event, "to_dict") and callable(getattr(event, "to_dict", None)):
                    payload = json.dumps(event.to_dict())  # type: ignore[attr-defined]
                else:
                    payload = json.dumps(str(event))
                yield f"data: {payload}\n\n"

            # Aggregate to final response and emit response.completed event (OpenAI standard)
            from .models import ResponseCompletedEvent

            final_response = await executor.message_mapper.aggregate_to_response(events, request)
            completed_event = ResponseCompletedEvent(
                type="response.completed",
                response=final_response,
                sequence_number=len(events),
            )
            yield f"data: {completed_event.model_dump_json()}\n\n"

            # Send final done event
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in streaming execution: {e}")
            error_event = {"id": "error", "object": "error", "error": {"message": str(e), "type": "execution_error"}}
            yield f"data: {json.dumps(error_event)}\n\n"

    def _mount_ui(self, app: FastAPI) -> None:
        """Mount the UI as static files."""
        from pathlib import Path

        ui_dir = Path(__file__).parent / "ui"
        if ui_dir.exists() and ui_dir.is_dir() and self.ui_enabled:
            app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    def register_entities(self, entities: list[Any]) -> None:
        """Register entities to be discovered when server starts.

        Args:
            entities: List of entity objects to register
        """
        if self._pending_entities is None:
            self._pending_entities = []
        self._pending_entities.extend(entities)

    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        if self._app is None:
            self._app = self.create_app()
        return self._app
