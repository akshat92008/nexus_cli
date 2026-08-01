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

import asyncio
import json
import os
import secrets
import threading
from pathlib import Path
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from nexus.agent import Agent
from nexus.memory import ConversationMemory
from nexus.models import ALIASES, DEFAULT_MODEL, list_models
from nexus.tools import TOOL_DEFINITIONS

# Global state
_agents: dict[str, Agent] = {}  # session_id -> Agent
_agent_locks: dict[str, threading.RLock] = {}
_api_key: str = ""
_default_model: str = DEFAULT_MODEL
_working_dir: str = ""
_web_token: str = secrets.token_hex(16)
_agent_options: dict[str, object] = {
    "model_id_override": None,
    "local_intern_mode": "off",
    "enable_nova_fallback": False,
    "plugins_enabled": False,
    "tools_enabled": True,
}
MAX_AGENTS = 50  # Evict oldest agents when exceeded
SENSITIVE_FILENAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
SENSITIVE_DIRNAMES = {".aws", ".git", ".nexusai", ".ssh"}


def _workspace_path(raw: str) -> Path:
    """Resolve a web-requested path and reject workspace escapes."""
    root = Path(_working_dir).resolve()
    candidate = Path(raw).expanduser()
    path = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Path is outside the workspace: {path}") from exc
    return path


def _is_sensitive_path(path: Path) -> bool:
    """Return True for common secret-bearing files that the UI must not expose."""
    name = path.name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in SENSITIVE_FILENAMES
        or any(part.lower() in SENSITIVE_DIRNAMES for part in path.parts)
    )


def _is_allowed_web_origin(origin: str | None) -> bool:
    """Allow same-machine browser origins and non-browser clients only."""
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "::1",
        "localhost",
    }


def _get_agent(session_id: str) -> Agent:
    """Get or create an agent for a session."""
    if session_id not in _agents:
        # Evict oldest agents if we exceed the limit
        if len(_agents) >= MAX_AGENTS:
            oldest_key = next(iter(_agents))
            del _agents[oldest_key]
            _agent_locks.pop(oldest_key, None)
        _agents[session_id] = Agent(
            api_key=_api_key,
            model_key=_default_model,
            working_dir=_working_dir,
            workspace_isolation=True,
            model_id_override=_agent_options["model_id_override"],
            local_intern_mode=str(_agent_options["local_intern_mode"]),
            enable_nova_fallback=bool(_agent_options["enable_nova_fallback"]),
            plugins_enabled=bool(_agent_options["plugins_enabled"]),
            tools_enabled=bool(_agent_options["tools_enabled"]),
        )
    _agent_locks.setdefault(session_id, threading.RLock())
    return _agents[session_id]


def _run_agent_locked(session_id: str, agent: Agent, message: str):
    """Serialize mutations for a web session while allowing other sessions to run."""
    lock = _agent_locks.setdefault(session_id, threading.RLock())
    with lock:
        return agent.run_non_interactive(message)


# ─── HTTP Endpoints ──────────────────────────────────────────────────────────


async def index(request):
    """Serve the main web UI."""
    static_dir = Path(__file__).parent / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    html = html.replace(
        "<head>", f'<head>\\n    <script>window.CSRF_TOKEN="{_web_token}";</script>'
    )
    return HTMLResponse(html)


async def api_models(request):
    """List all available models."""
    models = list_models()
    return JSONResponse(
        {
            "models": models,
            "default": _default_model,
            "aliases": ALIASES,
        }
    )


async def api_history(request):
    """List saved conversations."""
    memory = ConversationMemory()
    convs = memory.list_conversations(limit=20)
    return JSONResponse({"conversations": convs})


async def api_files(request):
    """Browse the file system."""
    path = request.query_params.get("path", _working_dir)
    try:
        p = _workspace_path(path)
        if not p.is_dir():
            return JSONResponse({"error": "Not a directory"}, status_code=400)

        items = []
        ignore_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".next",
            "dist",
            "build",
            ".nexusai",
        }

        for entry in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if entry.name.startswith(".") and entry.name != ".gitignore":
                continue
            if _is_sensitive_path(entry):
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

        return JSONResponse(
            {
                "path": str(p),
                "parent": str(p.parent) if str(p) != str(p.parent) else None,
                "items": items,
            }
        )
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_file_content(request):
    """Read a file's content."""
    path = request.query_params.get("path", "")
    if not path:
        return JSONResponse({"error": "No path provided"}, status_code=400)

    try:
        p = _workspace_path(path)
        if _is_sensitive_path(p):
            return JSONResponse({"error": "Sensitive files are not exposed"}, status_code=403)
        if not p.is_file():
            return JSONResponse({"error": "Not a file"}, status_code=400)
        if p.stat().st_size > 2 * 1024 * 1024:
            return JSONResponse({"error": "File too large"}, status_code=400)

        content = p.read_text(encoding="utf-8", errors="replace")
        return JSONResponse(
            {
                "path": str(p),
                "name": p.name,
                "content": content,
                "size": p.stat().st_size,
                "lines": content.count("\n") + 1,
            }
        )
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_chat(request):
    """Non-streaming chat endpoint."""
    token = request.headers.get("X-CSRF-Token")
    if token != _web_token:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

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
        None, _run_agent_locked, session_id, agent, message
    )

    return JSONResponse(
        {
            "content": content,
            "events": events,
            "model": agent.model_cfg["name"],
        }
    )


async def api_tools(request):
    """List all available tools."""
    tools = []
    for td in TOOL_DEFINITIONS:
        fn = td["function"]
        tools.append(
            {
                "name": fn["name"],
                "description": fn["description"],
            }
        )
    return JSONResponse({"tools": tools, "count": len(tools)})


async def api_pending_edits(request):
    session_id = request.query_params.get("session_id", "default")
    agent = _get_agent(session_id)
    return JSONResponse(
        {"summary": agent.pending_edits_summary(), "ids": list(agent._pending_edits)}
    )


async def api_edit_decision(request):
    token = request.headers.get("X-CSRF-Token")
    if token != _web_token:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    session_id = request.path_params["session_id"]
    edit_id = request.path_params["edit_id"]
    action = request.path_params["action"]
    agent = _get_agent(session_id)
    if action == "apply":
        result, success = agent.apply_pending_edit(edit_id)
    elif action == "reject":
        result, success = agent.reject_pending_edit(edit_id)
    else:
        return JSONResponse({"error": "action must be apply or reject"}, status_code=400)
    return JSONResponse({"result": result, "success": success}, status_code=200 if success else 409)


# ─── WebSocket Endpoint ─────────────────────────────────────────────────────


async def ws_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming chat."""
    if not _is_allowed_web_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    session_id = "ws_default"
    authenticated = False

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            msg_type = data.get("type", "chat")

            if msg_type == "authenticate":
                if data.get("token") == _web_token:
                    authenticated = True
                else:
                    await websocket.send_json({"type": "error", "content": "Unauthorized"})
                    await websocket.close(code=1008)
                continue

            if not authenticated:
                await websocket.send_json({"type": "error", "content": "Unauthorized"})
                continue

            if msg_type == "set_session":
                session_id = data.get("session_id", session_id)
                await websocket.send_json({"type": "session_set", "session_id": session_id})
                continue

            if msg_type == "set_model":
                model = data.get("model", "")
                agent = _get_agent(session_id)
                if agent.set_model(model):
                    await websocket.send_json(
                        {
                            "type": "model_set",
                            "model": agent.model_cfg["name"],
                            "model_id": agent.model_cfg["id"],
                        }
                    )
                else:
                    await websocket.send_json(
                        {"type": "error", "content": f"Unknown model: {model}"}
                    )
                continue

            if msg_type == "clear":
                agent = _get_agent(session_id)
                agent.clear_history()
                await websocket.send_json({"type": "cleared"})
                continue

            if msg_type in ("apply_edit", "reject_edit", "pending_edits"):
                agent = _get_agent(session_id)
                if msg_type == "apply_edit":
                    result, success = agent.apply_pending_edit(data.get("edit_id", ""))
                elif msg_type == "reject_edit":
                    result, success = agent.reject_pending_edit(data.get("edit_id", ""))
                else:
                    result, success = agent.pending_edits_summary(), True
                await websocket.send_json(
                    {"type": "edit_decision", "content": result, "success": success}
                )
                continue

            if msg_type == "new_chat":
                # Create a fresh session
                if session_id in _agents:
                    del _agents[session_id]
                    _agent_locks.pop(session_id, None)
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
                    None, _run_agent_locked, session_id, agent, message
                )

                # Send tool events
                for event in events:
                    if event.get("type") == "model_trace":
                        await websocket.send_json(event)
                    else:
                        await websocket.send_json(
                            {
                                "type": "tool_call",
                                "name": event.get("name", "unknown"),
                                "args": event.get("args", {}),
                                "result": event.get("result", ""),
                                "success": event.get("success", False),
                            }
                        )

                # Send final response
                await websocket.send_json(
                    {
                        "type": "response",
                        "content": content,
                        "model": agent.model_cfg["name"],
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


# ─── App Factory ─────────────────────────────────────────────────────────────


def create_app(
    api_key: str,
    model: str = DEFAULT_MODEL,
    working_dir: str | None = None,
    *,
    model_id_override: str | None = None,
    local_intern_mode: str = "off",
    enable_nova_fallback: bool = False,
    plugins_enabled: bool = False,
    tools_enabled: bool = True,
):
    """Create the Starlette application with isolated per-session agents."""
    global _api_key, _default_model, _working_dir, _web_token, _agent_options

    _agents.clear()
    _agent_locks.clear()
    _web_token = secrets.token_hex(16)
    _api_key = api_key
    _default_model = model
    _working_dir = working_dir or os.getcwd()
    _agent_options = {
        "model_id_override": model_id_override,
        "local_intern_mode": local_intern_mode,
        "enable_nova_fallback": enable_nova_fallback,
        "plugins_enabled": plugins_enabled,
        "tools_enabled": tools_enabled,
    }

    static_dir = Path(__file__).parent / "static"

    routes = [
        Route("/", index),
        Route("/api/models", api_models),
        Route("/api/history", api_history),
        Route("/api/files", api_files),
        Route("/api/file", api_file_content),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/tools", api_tools),
        Route("/api/pending-edits", api_pending_edits),
        Route(
            "/api/edits/{session_id:str}/{edit_id:str}/{action:str}",
            api_edit_decision,
            methods=["POST"],
        ),
        WebSocketRoute("/ws", ws_chat),
        Mount("/static", StaticFiles(directory=str(static_dir)), name="static"),
    ]

    app = Starlette(routes=routes)

    # Add CORS middleware for cross-origin access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1",
            "http://localhost",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
