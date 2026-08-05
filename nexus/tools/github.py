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

def tool_github_list_issues(limit: int = 10) -> str:
    try:
        from nexus.github import GitHubIntegration

        issues = GitHubIntegration.list_issues(limit=limit)
        if not issues:
            return "No open issues found."
        lines = []
        for i in issues:
            lines.append(f"#{i.get('number')} [{i.get('state')}] {i.get('title')}")
        return "\n".join(lines)
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ GitHub Error: {e}"

def tool_github_view_issue(number: str) -> str:
    try:
        from nexus.github import GitHubIntegration

        issue = GitHubIntegration.view_issue(number)
        if not issue:
            return f"❌ Issue #{number} not found."
        comments = "\n".join(
            f"- {item.get('author', {}).get('login', 'unknown')}: {item.get('body', '')}"
            for item in issue.get("comments", [])
        )
        return (
            f"Issue #{issue.get('number')}: {issue.get('title')}\n"
            f"State: {issue.get('state')}\n"
            f"URL: {issue.get('url')}\n\n"
            f"{issue.get('body', '(no body)')}\n\n"
            f"Comments:\n{comments or '(none)'}"
        )
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ GitHub Error: {e}"

def tool_github_create_pr(title: str, body: str, base: str = "") -> str:
    try:
        from nexus.github import GitHubIntegration

        url = GitHubIntegration.create_pull_request(title, body, base)
        return f"✅ Pull request created successfully: {url}"
    except ImportError as e:
        return f"❌ GitHub Error: {e}"

