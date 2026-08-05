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

class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection whose socket destination is a pre-validated IP."""

    def __init__(self, hostname: str, address: str, port: int, *, timeout: float):
        super().__init__(hostname, port=port, timeout=timeout)
        self._pinned_address = address

    def connect(self):
        self.sock = self._create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to an IP while validating the original hostname."""

    def __init__(self, hostname: str, address: str, port: int, *, timeout: float):
        super().__init__(
            hostname,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_address = address

    def connect(self):
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        server_hostname = self.host
        if self._tunnel_host:
            self._tunnel()
            server_hostname = self._tunnel_host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)

def tool_web_fetch(url: str, max_length: int = 10000) -> str:
    """Fetch public HTTP(S) text while blocking SSRF and unsafe redirects."""
    from nexus.network_policy import NetworkPolicy, network_globally_disabled

    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        return "❌ Network policy blocked URL: URL must contain 1-4096 characters"
    policy = NetworkPolicy(max_response_bytes=500_000)
    # Full resolution happens inside _safe_urlopen immediately before the
    # socket is pinned. Syntax validation here keeps mocked/offline tests free
    # of accidental DNS calls.
    violation = policy.check_url_syntax(url)
    if violation:
        return f"❌ Network policy blocked URL ({violation.category}): {violation.reason}"
    if network_globally_disabled():
        return "❌ Network policy blocked URL (network_disabled): outbound network is disabled"
    try:
        max_length = max(1, min(int(max_length or 10000), 100_000))
    except (TypeError, ValueError):
        return "❌ max_length must be an integer between 1 and 100000"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NexusAI/3.1 (coding-agent)"},
        )
        with _safe_urlopen(req, timeout=15, policy=policy) as resp:
            final_url = getattr(resp, "geturl", lambda: url)()
            redirect_violation = policy.check_url_syntax(final_url)
            if final_url != url and redirect_violation:
                return (
                    "❌ Network policy blocked redirect "
                    f"({redirect_violation.category}): {redirect_violation.reason}"
                )
            content_type = resp.headers.get("Content-Type", "")
            type_violation = policy.check_content_type(content_type)
            if type_violation:
                return f"❌ Network policy blocked response: {type_violation.reason}"
            raw = resp.read(policy.max_response_bytes + 1)
            if len(raw) > policy.max_response_bytes:
                return (
                    "❌ Network policy blocked response: content exceeded "
                    f"{policy.max_response_bytes} bytes"
                )

        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        text = raw.decode(encoding, errors="replace")
        if "html" in content_type.lower():
            text = _strip_html(text)
        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (truncated, {len(text)} total chars)"
        return f"🌐 Fetched {url}\n\n{text}"
    except urllib.error.HTTPError as exc:
        return f"❌ HTTP {exc.code}: {exc.reason} — {url}"
    except urllib.error.URLError as exc:
        return f"❌ URL error: {exc.reason} — {url}"
    except (OSError, ValueError) as exc:
        return f"❌ Error fetching URL: {exc}"

def tool_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML (no API key needed)."""
    from nexus.network_policy import NetworkPolicy, network_globally_disabled

    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return "❌ Search query must contain 1-500 characters"
    try:
        max_results = max(1, min(int(max_results or 5), 20))
    except (TypeError, ValueError):
        return "❌ max_results must be an integer between 1 and 20"
    if network_globally_disabled():
        return "❌ Network policy blocked search (network_disabled): outbound network is disabled"
    try:
        # Use DuckDuckGo HTML search
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        policy = NetworkPolicy(
            allowed_hosts=frozenset({"html.duckduckgo.com"}),
            max_response_bytes=200_000,
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NexusAI/1.0"},
        )
        with _safe_urlopen(req, timeout=10, policy=policy) as resp:
            html_text = resp.read(policy.max_response_bytes).decode("utf-8", errors="replace")

        # Parse results (simple regex extraction)
        results = []
        # DuckDuckGo HTML has results in <a class="result__a"> tags
        result_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        for match in result_pattern.finditer(html_text):
            if len(results) >= max_results:
                break
            link = match.group(1)
            title = _strip_html(match.group(2)).strip()
            snippet = _strip_html(match.group(3)).strip()

            # DuckDuckGo wraps links in a redirect, extract the actual URL
            if "uddg=" in link:
                actual_url = urllib.parse.unquote(link.split("uddg=")[-1].split("&")[0])
            else:
                actual_url = link

            if title and actual_url:
                results.append(
                    f"  {len(results) + 1}. {title}\n     {actual_url}\n     {snippet}\n"
                )

        if not results:
            return f"🔍 No results found for: {query}"

        return f"🔍 Search results for '{query}':\n\n" + "\n".join(results)
    except (LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ Search error: {e}"

