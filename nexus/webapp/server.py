"""
NexusAI Web Server — Starlette + WebSocket for real-time streaming.

Endpoints:
  GET  /                    → Serves the web UI
  GET  /api/models          → List available models
  GET  /api/history         → List saved conversations
  GET  /api/files           → Browse the file system
  POST /api/chat            → Non-streaming chat (returns JSON)
  WS   /ws                  → WebSocket for real-time streaming chat
"""

import json
import os
import asyncio
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.responses import HTMLResponse, JSONResponse, FileResponse
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware

from nexus.agent import Agent
from nexus.models import list_models, MODELS, ALIASES, resolve_model, DEFAULT_MODEL
from nexus.memory import ConversationMemory
from nexus.tools import TOOL_DEFINITIONS


# Global state
_agents: dict[str, Agent] = {}  # session_id -> Agent
_api_key: str = ""
_default_model: str = DEFAULT_MODEL
_working_dir: str = ""
MAX_AGENTS = 50  # Evict oldest agents when exceeded


def _get_agent(session_id: str) -> Agent:
    """Get or create an agent for a session."""
    if session_id not in _agents:
        # Evict oldest agents if we exceed the limit
        if len(_agents) >= MAX_AGENTS:
            oldest_key = next(iter(_agents))
            del _agents[oldest_key]
        _agents[session_id] = Agent(
            api_key=_api_key,
            model_key=_default_model,
            working_dir=_working_dir,
        )
    return _agents[session_id]


# ─── HTTP Endpoints ──────────────────────────────────────────────────────────

async def index(request):
    """Serve the main web UI."""
    static_dir = Path(__file__).parent / "static"
    return FileResponse(static_dir / "index.html")


async def api_models(request):
    """List all available models."""
    models = list_models()
    return JSONResponse({
        "models": models,
        "default": _default_model,
        "aliases": ALIASES,
    })


async def api_history(request):
    """List saved conversations."""
    memory = ConversationMemory()
    convs = memory.list_conversations(limit=20)
    return JSONResponse({"conversations": convs})


async def api_files(request):
    """Browse the file system."""
    path = request.query_params.get("path", _working_dir)
    try:
        p = Path(path).resolve()
        if not p.is_dir():
            return JSONResponse({"error": "Not a directory"}, status_code=400)

        items = []
        ignore_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".next", "dist", "build", ".nexusai"}

        for entry in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if entry.name.startswith(".") and entry.name not in (".env", ".gitignore"):
                continue
            if entry.is_dir() and entry.name in ignore_dirs:
                continue

            item = {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
            }
            if entry.is_file():
                item["size"] = entry.stat().st_size
            items.append(item)

        return JSONResponse({
            "path": str(p),
            "parent": str(p.parent) if str(p) != str(p.parent) else None,
            "items": items,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_file_content(request):
    """Read a file's content."""
    path = request.query_params.get("path", "")
    if not path:
        return JSONResponse({"error": "No path provided"}, status_code=400)

    try:
        p = Path(path).resolve()
        if not p.is_file():
            return JSONResponse({"error": "Not a file"}, status_code=400)
        if p.stat().st_size > 2 * 1024 * 1024:
            return JSONResponse({"error": "File too large"}, status_code=400)

        content = p.read_text(encoding="utf-8", errors="replace")
        return JSONResponse({
            "path": str(p),
            "name": p.name,
            "content": content,
            "size": p.stat().st_size,
            "lines": content.count("\n") + 1,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_chat(request):
    """Non-streaming chat endpoint."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message = body.get("message", "").strip()
    session_id = body.get("session_id", "default")
    model = body.get("model")

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    agent = _get_agent(session_id)

    # Switch model if requested
    if model:
        agent.set_model(model)

    # Run synchronously in a thread
    loop = asyncio.get_event_loop()
    content, events = await loop.run_in_executor(
        None, agent.run_non_interactive, message
    )

    return JSONResponse({
        "content": content,
        "events": events,
        "model": agent.model_cfg["name"],
    })


async def api_tools(request):
    """List all available tools."""
    tools = []
    for td in TOOL_DEFINITIONS:
        fn = td["function"]
        tools.append({
            "name": fn["name"],
            "description": fn["description"],
        })
    return JSONResponse({"tools": tools, "count": len(tools)})


# ─── WebSocket Endpoint ─────────────────────────────────────────────────────

async def ws_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming chat."""
    await websocket.accept()
    session_id = "ws_default"

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            msg_type = data.get("type", "chat")

            if msg_type == "set_session":
                session_id = data.get("session_id", session_id)
                await websocket.send_json({"type": "session_set", "session_id": session_id})
                continue

            if msg_type == "set_model":
                model = data.get("model", "")
                agent = _get_agent(session_id)
                if agent.set_model(model):
                    await websocket.send_json({
                        "type": "model_set",
                        "model": agent.model_cfg["name"],
                        "model_id": agent.model_cfg["id"],
                    })
                else:
                    await websocket.send_json({"type": "error", "content": f"Unknown model: {model}"})
                continue

            if msg_type == "clear":
                agent = _get_agent(session_id)
                agent.clear_history()
                await websocket.send_json({"type": "cleared"})
                continue

            if msg_type == "new_chat":
                # Create a fresh session
                if session_id in _agents:
                    del _agents[session_id]
                import time
                session_id = f"ws_{int(time.time())}"
                await websocket.send_json({"type": "new_session", "session_id": session_id})
                continue

            if msg_type == "chat":
                message = data.get("message", "").strip()
                if not message:
                    continue

                agent = _get_agent(session_id)

                # Send "thinking" indicator
                await websocket.send_json({"type": "thinking"})

                # Run in executor (blocking agent loop)
                loop = asyncio.get_event_loop()
                content, events = await loop.run_in_executor(
                    None, agent.run_non_interactive, message
                )

                # Send tool events
                for event in events:
                    await websocket.send_json({
                        "type": "tool_call",
                        "name": event["name"],
                        "args": event["args"],
                        "result": event["result"],
                        "success": event["success"],
                    })

                # Send final response
                await websocket.send_json({
                    "type": "response",
                    "content": content,
                    "model": agent.model_cfg["name"],
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


# ─── App Factory ─────────────────────────────────────────────────────────────

def create_app(api_key: str, model: str = DEFAULT_MODEL, working_dir: str | None = None):
    """Create the Starlette application."""
    global _api_key, _default_model, _working_dir

    _api_key = api_key
    _default_model = model
    _working_dir = working_dir or os.getcwd()

    static_dir = Path(__file__).parent / "static"

    routes = [
        Route("/", index),
        Route("/api/models", api_models),
        Route("/api/history", api_history),
        Route("/api/files", api_files),
        Route("/api/file", api_file_content),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/tools", api_tools),
        WebSocketRoute("/ws", ws_chat),
        Mount("/static", StaticFiles(directory=str(static_dir)), name="static"),
    ]

    app = Starlette(routes=routes)

    # Add CORS middleware for cross-origin access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
