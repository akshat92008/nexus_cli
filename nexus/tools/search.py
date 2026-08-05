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

def tool_search_code(
    pattern: str, directory: str | None = None, file_pattern: str | None = None
) -> str:
    """Search for a pattern across files."""
    try:
        search_dir = _resolve_path(directory or _tool_working_dir.get() or os.getcwd())
        if not search_dir.is_dir():
            return f"❌ Not a directory: {search_dir}"

        matches = []
        max_matches = 50
        regex = re.compile(pattern, re.IGNORECASE)

        for root, dirs, files in os.walk(search_dir):
            # Filter ignored dirs
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

            for fname in files:
                if file_pattern and not fnmatch.fnmatch(fname, file_pattern):
                    continue
                fpath = Path(root) / fname
                if _should_ignore(fpath):
                    continue

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                rel = fpath.relative_to(search_dir)
                                matches.append(f"  {rel}:{i}  │ {line.rstrip()}")
                                if len(matches) >= max_matches:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue

                if len(matches) >= max_matches:
                    break
            if len(matches) >= max_matches:
                break

        if not matches:
            return f"🔍 No matches for /{pattern}/ in {search_dir}"

        header = f"🔍 Found {len(matches)} matches for /{pattern}/:"
        if len(matches) == max_matches:
            header += f" (capped at {max_matches})"
        return header + "\n" + "\n".join(matches)
    except (OSError, TypeError, ValueError) as e:
        return f"❌ Error searching: {e}"

def tool_repo_index(force: bool = False) -> str:
    """Build the persistent repository graph for the active working directory."""
    try:
        from nexus.repo_graph import RepoGraph

        graph = RepoGraph(_tool_working_dir.get() or os.getcwd())
        stats = graph.build(force=bool(force))
        return "🧭 Repository graph refreshed\n" + json.dumps(
            {
                "stats": {
                    "scanned": stats.scanned,
                    "indexed": stats.indexed,
                    "reused": stats.reused,
                    "removed": stats.removed,
                    "parse_errors": stats.parse_errors,
                },
                "graph": graph.summary(),
            },
            indent=2,
        )
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return f"❌ Repository graph indexing failed: {exc}"

def tool_repo_symbols(
    query: str,
    include_callers: bool = True,
    limit: int = 50,
) -> str:
    """Find declarations and callers in the active repository graph."""
    try:
        from nexus.repo_graph import RepoGraph

        graph = RepoGraph(_tool_working_dir.get() or os.getcwd())
        graph.build()
        declarations = [asdict(item) for item in graph.find_symbols(query, limit=limit)]
        callers = graph.find_callers(query, limit=limit) if include_callers else []
        return "🧭 Repository symbol lookup\n" + json.dumps(
            {
                "query": query,
                "declarations": declarations,
                "callers": callers,
            },
            indent=2,
        )
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return f"❌ Repository symbol lookup failed: {exc}"

def tool_repo_impact(paths: list[str]) -> str:
    """Find imports, reverse importers, and tests affected by changed files."""
    try:
        from nexus.repo_graph import RepoGraph

        graph = RepoGraph(_tool_working_dir.get() or os.getcwd())
        graph.build()
        dependencies = {str(path): graph.dependencies(path) for path in paths}
        return "🧭 Repository impact analysis\n" + json.dumps(
            {
                "paths": paths,
                "dependencies": dependencies,
                "impacted_tests": graph.impacted_tests(paths),
            },
            indent=2,
        )
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return f"❌ Repository impact analysis failed: {exc}"

def tool_repo_context(query: str, limit: int = 40) -> str:
    """Return relevance-ranked repository context."""
    try:
        graph = _built_graph()
        return json.dumps(
            {
                "query": query,
                "results": graph.relevant_files(query, limit=max(1, int(limit))),
                "frameworks": graph.frameworks(),
                "summary": graph.summary(),
            },
            indent=2,
        )
    except (TypeError, ValueError) as exc:
        return f"❌ Repository context selection failed: {exc}"

def tool_repo_routes(query: str = "") -> str:
    """Return indexed routes."""
    try:
        return json.dumps(_built_graph().routes(query), indent=2)
    except (TypeError, ValueError) as exc:
        return f"❌ Repository route discovery failed: {exc}"

def tool_repo_models(query: str = "") -> str:
    """Return indexed database models."""
    try:
        return json.dumps(_built_graph().models(query), indent=2)
    except (TypeError, ValueError) as exc:
        return f"❌ Repository model discovery failed: {exc}"

def tool_repo_navigate(
    path: str,
    language: str,
    operation: str,
    line: int = 0,
    character: int = 0,
) -> str:
    """Navigate symbols through LSP with deterministic fallbacks."""
    from nexus.language_intelligence import (
        LanguageServicePool,
        LSPError,
        TreeSitterAdapter,
    )

    root = str(Path(_tool_working_dir.get() or os.getcwd()).resolve())
    pool = _language_service_pools.get(root)
    if pool is None:
        pool = LanguageServicePool(root)
        _language_service_pools[root] = pool
    try:
        client = pool.client(language)
        if operation == "symbols":
            result = client.document_symbols(path)
        elif operation == "definition":
            result = client.definition(path, int(line), int(character))
        elif operation == "references":
            result = client.references(path, int(line), int(character))
        else:
            return f"❌ Unsupported navigation operation: {operation}"
        return json.dumps(
            {"engine": "lsp", "operation": operation, "result": result},
            indent=2,
        )
    except LSPError as lsp_error:
        if operation != "symbols":
            return json.dumps(
                {
                    "engine": "unavailable",
                    "operation": operation,
                    "error": str(lsp_error),
                    "guidance": (f"Install a {language} language server for precise {operation}."),
                },
                indent=2,
            )
        target = _resolve_path(path)
        try:
            source = target.read_text(encoding="utf-8")
            adapter = TreeSitterAdapter()
            if adapter.available:
                return json.dumps(
                    {
                        "engine": "tree-sitter",
                        "operation": "symbols",
                        "result": adapter.symbols(source, language),
                    },
                    indent=2,
                )
        except (OSError, UnicodeDecodeError, LSPError):
            pass
        graph = _built_graph()
        relative = target.resolve().relative_to(Path(root)).as_posix()
        record = graph.files.get(relative)
        return json.dumps(
            {
                "engine": "repograph",
                "operation": "symbols",
                "lsp_error": str(lsp_error),
                "result": [asdict(item) for item in record.symbols] if record else [],
            },
            indent=2,
        )

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

