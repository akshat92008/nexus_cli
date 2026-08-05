import atexit
import contextvars
import fnmatch
import hashlib
import html
import http.client
import json
import mimetypes
import os
import re
import shlex
import signal
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from nexus.paths import nexus_home
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum

class ToolStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    PERMISSION_DENIED = "permission_denied"
    INVALID_INPUT = "invalid_input"
    ENVIRONMENT_UNAVAILABLE = "environment_unavailable"
    PARTIAL = "partial"

class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    permission: PermissionLevel = PermissionLevel.READ
    mutates_workspace: bool = False
    requires_network: bool = False
    default_timeout_seconds: float = 120.0
    handler: Callable | None = None
    
    def to_openai_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            }
        }

class ToolResult:
    status: ToolStatus
    output: str
    evidence: str = ""
    error: str = ""
    duration: float = 0.0
    
    @property
    def success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        
    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        
    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)
        
    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

