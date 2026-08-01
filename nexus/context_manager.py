"""
Context Manager — intelligent context windowing for large codebases.

Manages which information stays in the active context, tracks file relevance,
builds dependency graphs, and manages token budgets to prevent context overflow.

Architecture:
    File Access Tracker → Relevance Scoring → Token Budget → Context Assembly
"""

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from nexus.paths import nexus_home


@dataclass
class FileContext:
    """Tracked context about a file."""

    path: str
    last_accessed: str = ""
    access_count: int = 0
    was_edited: bool = False
    relevance_score: float = 0.0
    summary: str = ""
    line_count: int = 0
    language: str = ""
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    content_sha256: str = ""
    modified_ns: int = 0

    @property
    def basename(self) -> str:
        return Path(self.path).name


@dataclass
class ArchitectureMap:
    """High-level understanding of the project structure."""

    project_root: str = ""
    project_type: str = ""  # python, javascript, rust, go, etc.
    framework: str = ""  # fastapi, next.js, django, etc.
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    test_directories: list[str] = field(default_factory=list)
    source_directories: list[str] = field(default_factory=list)
    modules: dict[str, list[str]] = field(default_factory=dict)  # module_name -> files

    def to_summary(self) -> str:
        lines = [f"Project: {Path(self.project_root).name}"]
        if self.project_type:
            lines.append(f"Type: {self.project_type}")
        if self.framework:
            lines.append(f"Framework: {self.framework}")
        if self.entry_points:
            lines.append(f"Entry points: {', '.join(self.entry_points)}")
        if self.modules:
            lines.append(f"Modules: {', '.join(self.modules.keys())}")
        return " | ".join(lines)


# ── Language Detection ───────────────────────────────────────────────────────

_EXTENSION_LANGUAGE = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".json": "json",
    ".jsonc": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".xml": "xml",
    ".dockerfile": "dockerfile",
}

_PROJECT_TYPE_INDICATORS = {
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "javascript": ["package.json"],
    "typescript": ["tsconfig.json"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
    "dart": ["pubspec.yaml"],
    "elixir": ["mix.exs"],
    "csharp": ["*.csproj", "*.sln"],
}

_FRAMEWORK_INDICATORS = {
    "next.js": ["next.config.js", "next.config.mjs", "next.config.ts"],
    "react": ["package.json"],  # + check for "react" in deps
    "vue": ["vue.config.js", "nuxt.config.js", "nuxt.config.ts"],
    "angular": ["angular.json"],
    "svelte": ["svelte.config.js"],
    "fastapi": [],  # Detected by imports
    "django": ["manage.py"],
    "flask": [],  # Detected by imports
    "express": [],  # Detected by package.json
    "nestjs": ["nest-cli.json"],
    "spring": [],  # Detected by build.gradle/pom.xml
    "rails": ["Gemfile"],  # + check for "rails"
    "laravel": ["artisan"],
    "flutter": ["pubspec.yaml"],  # + check for "flutter"
    "electron": [],  # Detected by package.json
    "tauri": ["tauri.conf.json"],
}

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".next",
    ".venv",
    "venv",
    "dist",
    "build",
    ".cache",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "env",
    ".env",
    ".idea",
    ".vscode",
    "target",
    "coverage",
    ".nexusai",
    ".ruff_cache",
    ".nuxt",
    ".output",
    ".turbo",
    "Library",
    "Applications",
    "Pictures",
    "Music",
    "Movies",
    "Downloads",
    "System",
    "Volumes",
    ".Trash",
    ".DocumentRevisions-V100",
}


class ContextManager:
    """
    Manages the active context for the agent — decides what information to include
    in each API call to maximize relevance while staying within token limits.

    Features:
    - Tracks which files have been accessed and edited
    - Builds a lightweight dependency graph
    - Detects project type and framework
    - Manages token budgets
    - Generates optimized context strings
    """

    def __init__(self, working_dir: str, max_context_tokens: int = 30000):
        self.working_dir = str(Path(working_dir).expanduser().resolve())
        self.max_context_tokens = max_context_tokens
        self._file_contexts: dict[str, FileContext] = {}
        self._architecture: ArchitectureMap | None = None
        self._dependency_graph: dict[str, set[str]] = defaultdict(set)  # file -> depends_on
        self._initialized = False
        workspace_key = hashlib.sha256(self.working_dir.encode("utf-8")).hexdigest()[:20]
        self._cache_path = nexus_home() / "context" / f"{workspace_key}.json"
        self._load_cache()

    def initialize(self) -> str:
        """
        Initialize context by scanning the project.
        Returns a context string for the first interaction.
        """
        if self._initialized:
            return ""
        self._initialized = True

        self._architecture = self._detect_architecture()
        context_parts = []

        # Architecture summary
        if self._architecture:
            context_parts.append(f"[PROJECT] {self._architecture.to_summary()}")

        # Project structure (compact)
        tree = self._get_compact_tree()
        if tree:
            context_parts.append(f"[STRUCTURE]\n{tree}")

        # Git status
        git_info = self._get_git_info()
        if git_info:
            context_parts.append(f"[GIT] {git_info}")

        # Key config files (compact summaries)
        configs = self._get_config_summaries()
        if configs:
            context_parts.append(f"[CONFIG]\n{configs}")

        return "\n\n".join(context_parts) + "\n\n---\n\n" if context_parts else ""

    def track_file_access(self, filepath: str, was_edited: bool = False):
        """Record that a file was accessed or edited."""
        abs_path = self._absolute_path(filepath)
        now = datetime.now().isoformat()

        if abs_path not in self._file_contexts:
            lang = _EXTENSION_LANGUAGE.get(Path(filepath).suffix.lower(), "")
            self._file_contexts[abs_path] = FileContext(
                path=abs_path,
                language=lang,
            )

        ctx = self._file_contexts[abs_path]
        ctx.last_accessed = now
        ctx.access_count += 1
        if was_edited:
            ctx.was_edited = True
        ctx.relevance_score = self._calculate_relevance(ctx)
        candidate = Path(abs_path)
        try:
            if candidate.is_file() and candidate.stat().st_size <= 2_000_000:
                content = candidate.read_text(encoding="utf-8", errors="replace")
                self.summarize_file(abs_path, content)
                self.track_file_imports(abs_path, content)
        except OSError:
            pass
        self._save_cache()

    def track_file_imports(self, filepath: str, content: str):
        """Extract and track import relationships from file content."""
        abs_path = self._absolute_path(filepath)
        if abs_path in self._file_contexts:
            imports = self._extract_imports(content, Path(filepath).suffix.lower())
            self._file_contexts[abs_path].imports = imports
            self._dependency_graph[abs_path].clear()
            for imp in imports:
                resolved = self._resolve_import(abs_path, imp)
                if resolved:
                    self._dependency_graph[abs_path].add(resolved)
        self._save_cache()

    def get_relevant_context(self, user_input: str = "") -> str:
        """
        Build an optimized context string based on current relevance.
        Prioritizes recently accessed and edited files.
        """
        self._refresh_stale_contexts()
        if not self._file_contexts:
            return ""

        # Score all files
        query = user_input.lower()
        scored = sorted(
            self._file_contexts.values(),
            key=lambda item: (
                item.relevance_score
                + (5.0 if item.basename.lower() in query else 0.0)
                + (
                    2.0
                    if item.summary
                    and any(word in item.summary.lower() for word in query.split())
                    else 0.0
                )
            ),
            reverse=True,
        )

        # Build context within token budget
        parts = []
        estimated_tokens = 0
        token_limit = self.max_context_tokens // 2  # Reserve half for new file reads

        for ctx in scored:
            if estimated_tokens >= token_limit:
                break

            entry = f"[{ctx.basename}] "
            if ctx.was_edited:
                entry += "(edited) "
            if ctx.summary:
                entry += ctx.summary
            else:
                entry += f"accessed {ctx.access_count}x"
            if ctx.language:
                entry += f" [{ctx.language}]"

            parts.append(entry)
            estimated_tokens += len(entry) // 3  # Rough token estimate

        if not parts:
            return ""

        return "[ACTIVE FILES]\n" + "\n".join(parts[:20]) + "\n"

    def get_architecture_context(self) -> str:
        """Get the architecture summary for context injection."""
        if self._architecture:
            return self._architecture.to_summary()
        return ""

    def get_dependency_context(self, filepath: str) -> list[str]:
        """Get files that are related to (depend on or depended by) a given file."""
        abs_path = self._absolute_path(filepath)
        related = set()

        # Files this file imports
        related.update(self._dependency_graph.get(abs_path, set()))

        # Files that import this file
        for file_path, deps in self._dependency_graph.items():
            if abs_path in deps:
                related.add(file_path)

        return list(related)

    def summarize_file(self, filepath: str, content: str) -> str:
        """Generate a compact summary of a file for context."""
        lines = content.split("\n")
        line_count = len(lines)
        suffix = Path(filepath).suffix.lower()
        lang = _EXTENSION_LANGUAGE.get(suffix, "")

        parts = [f"{line_count} lines"]
        if lang:
            parts.append(lang)

        # Extract key definitions
        if lang in ("python",):
            classes = re.findall(r"^class\s+(\w+)", content, re.MULTILINE)
            functions = re.findall(r"^def\s+(\w+)", content, re.MULTILINE)
            if classes:
                parts.append(f"classes: {', '.join(classes[:5])}")
            if functions:
                parts.append(f"functions: {', '.join(functions[:8])}")

        elif lang in ("javascript", "typescript"):
            exports = re.findall(
                r"export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)", content
            )
            if exports:
                parts.append(f"exports: {', '.join(exports[:8])}")

        elif lang in ("rust",):
            structs = re.findall(r"pub\s+struct\s+(\w+)", content)
            fns = re.findall(r"pub\s+fn\s+(\w+)", content)
            if structs:
                parts.append(f"structs: {', '.join(structs[:5])}")
            if fns:
                parts.append(f"pub fns: {', '.join(fns[:8])}")

        elif lang in ("go",):
            types = re.findall(r"type\s+(\w+)\s+struct", content)
            funcs = re.findall(r"func\s+(?:\([^)]+\)\s+)?(\w+)", content)
            if types:
                parts.append(f"types: {', '.join(types[:5])}")
            if funcs:
                parts.append(f"funcs: {', '.join(funcs[:8])}")

        summary = " | ".join(parts)

        # Cache the summary
        abs_path = self._absolute_path(filepath)
        if abs_path in self._file_contexts:
            self._file_contexts[abs_path].summary = summary
            self._file_contexts[abs_path].line_count = line_count
            self._file_contexts[abs_path].exports = self._extract_exports(content, lang)
            self._file_contexts[abs_path].content_sha256 = hashlib.sha256(
                content.encode("utf-8", errors="replace")
            ).hexdigest()
            try:
                self._file_contexts[abs_path].modified_ns = Path(abs_path).stat().st_mtime_ns
            except OSError:
                self._file_contexts[abs_path].modified_ns = 0
            self._save_cache()

        return summary

    def get_change_impact_context(self, filepaths: list[str]) -> str:
        """Return persistent summaries for changed files and their dependents."""
        self._refresh_stale_contexts()
        impacted: set[str] = set()
        for filepath in filepaths:
            absolute = self._absolute_path(filepath)
            impacted.add(absolute)
            impacted.update(self.get_dependency_context(absolute))
        entries = []
        for path in sorted(impacted):
            context = self._file_contexts.get(path)
            if context:
                entries.append(f"{path}: {context.summary or 'tracked without summary'}")
        return "[CHANGE IMPACT]\n" + "\n".join(entries) if entries else ""

    # ── Private Methods ──────────────────────────────────────────────────

    def _absolute_path(self, filepath: str) -> str:
        candidate = Path(filepath).expanduser()
        if not candidate.is_absolute():
            candidate = Path(self.working_dir) / candidate
        return str(candidate.resolve())

    def _load_cache(self) -> None:
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if payload.get("workspace") != self.working_dir:
                return
            for item in payload.get("files", []):
                context = FileContext(**{
                    key: value
                    for key, value in item.items()
                    if key in FileContext.__dataclass_fields__
                })
                try:
                    Path(context.path).resolve().relative_to(Path(self.working_dir))
                except (OSError, ValueError):
                    continue
                if Path(context.path).is_file():
                    self._file_contexts[context.path] = context
            for path, dependencies in payload.get("dependencies", {}).items():
                self._dependency_graph[path].update(str(item) for item in dependencies)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return

    def _refresh_stale_contexts(self) -> None:
        changed = False
        for path, context in list(self._file_contexts.items()):
            candidate = Path(path)
            try:
                stat = candidate.stat()
            except OSError:
                self._file_contexts.pop(path, None)
                self._dependency_graph.pop(path, None)
                for dependencies in self._dependency_graph.values():
                    dependencies.discard(path)
                changed = True
                continue
            if stat.st_size > 2_000_000:
                continue
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            if digest != context.content_sha256:
                self.summarize_file(path, content)
                self.track_file_imports(path, content)
            elif stat.st_mtime_ns != context.modified_ns:
                context.modified_ns = stat.st_mtime_ns
                changed = True
        if changed:
            self._save_cache()

    def _save_cache(self) -> None:
        payload = {
            "schema": "nexus.context.v1",
            "workspace": self.working_dir,
            "files": [asdict(item) for item in self._file_contexts.values()],
            "dependencies": {
                path: sorted(dependencies)
                for path, dependencies in self._dependency_graph.items()
            },
        }
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(self._cache_path)
        except OSError:
            pass

    def _resolve_import(self, source: str, imported: str) -> str:
        root = Path(self.working_dir)
        source_path = Path(source)
        source_suffix = source_path.suffix.lower()
        candidates: list[Path] = []
        if source_suffix in (".py", ".pyi", ".pyx") and imported.startswith("."):
            leading_dots = len(imported) - len(imported.lstrip("."))
            base = source_path.parent
            for _ in range(max(0, leading_dots - 1)):
                base = base.parent
            module = imported.lstrip(".").replace(".", "/")
            candidates.extend([base / f"{module}.py", base / module / "__init__.py"])
        elif source_suffix in (".py", ".pyi", ".pyx"):
            module = imported.lstrip(".").replace(".", "/")
            candidates.extend([root / f"{module}.py", root / module / "__init__.py"])
        elif imported.startswith(("./", "../")):
            base = source_path.parent / imported
            candidates.extend(
                [
                    base,
                    *(base.with_suffix(ext) for ext in (".ts", ".tsx", ".js", ".jsx")),
                    *(base / f"index{ext}" for ext in (".ts", ".tsx", ".js", ".jsx")),
                ]
            )
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
                if resolved.is_file():
                    return str(resolved)
            except (OSError, ValueError):
                continue
        return ""

    @staticmethod
    def _extract_exports(content: str, language: str) -> list[str]:
        if language == "python":
            return re.findall(r"^(?:class|def)\s+(\w+)", content, re.MULTILINE)[:100]
        if language in ("javascript", "typescript"):
            return re.findall(
                r"export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)",
                content,
            )[:100]
        return []

    def _calculate_relevance(self, ctx: FileContext) -> float:
        """Calculate a relevance score for a file (0.0 to 10.0)."""
        score = 0.0

        # Edited files are most relevant
        if ctx.was_edited:
            score += 5.0

        # Recent access boosts relevance
        score += min(ctx.access_count * 0.5, 3.0)

        # Config files are important
        if ctx.basename in (
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "tsconfig.json",
            "Dockerfile",
            "docker-compose.yml",
        ):
            score += 2.0

        # Entry points are important
        if ctx.basename in ("main.py", "app.py", "index.ts", "index.js", "main.rs", "main.go"):
            score += 1.5

        return min(score, 10.0)

    def _detect_architecture(self) -> ArchitectureMap:
        """Detect project type, framework, and structure."""
        root = Path(self.working_dir)
        arch = ArchitectureMap(project_root=self.working_dir)

        # Detect project type
        for ptype, indicators in _PROJECT_TYPE_INDICATORS.items():
            for indicator in indicators:
                if "*" in indicator:
                    if list(root.glob(indicator)):
                        arch.project_type = ptype
                        break
                elif (root / indicator).exists():
                    arch.project_type = ptype
                    break
            if arch.project_type:
                break

        # Detect framework
        for framework, indicators in _FRAMEWORK_INDICATORS.items():
            for indicator in indicators:
                if (root / indicator).exists():
                    arch.framework = framework
                    break

        # Detect framework from package.json
        pkg_json = root / "package.json"
        if pkg_json.exists() and not arch.framework:
            try:
                with open(pkg_json) as f:
                    pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    arch.framework = "next.js"
                elif "react" in deps:
                    arch.framework = "react"
                elif "vue" in deps:
                    arch.framework = "vue"
                elif "express" in deps:
                    arch.framework = "express"
                elif "electron" in deps:
                    arch.framework = "electron"
            except (json.JSONDecodeError, OSError):
                pass

        # Find entry points
        entry_candidates = [
            "main.py",
            "app.py",
            "run.py",
            "manage.py",
            "__main__.py",
            "index.js",
            "index.ts",
            "main.js",
            "main.ts",
            "app.js",
            "app.ts",
            "main.rs",
            "main.go",
            "Program.cs",
        ]
        for candidate in entry_candidates:
            if (root / candidate).exists():
                arch.entry_points.append(candidate)
            # Also check src/
            if (root / "src" / candidate).exists():
                arch.entry_points.append(f"src/{candidate}")

        # Find config files
        config_candidates = [
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "tsconfig.json",
            "Dockerfile",
            "docker-compose.yml",
            ".eslintrc.json",
            ".prettierrc",
            "tailwind.config.js",
            "vite.config.ts",
            "next.config.js",
            "webpack.config.js",
        ]
        for cfg in config_candidates:
            if (root / cfg).exists():
                arch.config_files.append(cfg)

        # Find source and test directories
        for d in root.iterdir():
            if d.is_dir() and d.name not in IGNORE_DIRS and not d.name.startswith("."):
                if d.name in ("test", "tests", "__tests__", "spec", "specs"):
                    arch.test_directories.append(d.name)
                elif d.name in ("src", "lib", "app", "core", "pkg", "cmd", "internal"):
                    arch.source_directories.append(d.name)

        # Build module map
        for src_dir in arch.source_directories:
            src_path = root / src_dir
            if src_path.is_dir():
                try:
                    for item in src_path.iterdir():
                        if (
                            item.is_dir()
                            and item.name not in IGNORE_DIRS
                            and not item.name.startswith(".")
                        ):
                            try:
                                files = [
                                    f.name
                                    for f in item.iterdir()
                                    if f.is_file() and f.suffix in _EXTENSION_LANGUAGE
                                ]
                                if files:
                                    arch.modules[item.name] = files[
                                        :10
                                    ]  # Cap at 10 files per module
                            except (PermissionError, OSError):
                                pass
                except (PermissionError, OSError):
                    pass

        return arch

    def _get_compact_tree(self, max_depth: int = 3) -> str:
        """Generate a compact tree view of the project."""
        root = Path(self.working_dir)
        lines = [f"{root.name}/"]

        def _walk(path: Path, prefix: str, depth: int):
            if depth >= max_depth or len(lines) >= 100:
                return
            try:
                raw_entries = list(path.iterdir())
                entries = sorted(raw_entries, key=lambda x: (not x.is_dir(), x.name.lower()))
            except (PermissionError, OSError):
                return

            entries = [
                e for e in entries if e.name not in IGNORE_DIRS and not e.name.startswith(".")
            ]
            for i, entry in enumerate(entries[:30]):
                if len(lines) >= 100:
                    break
                is_last = i == len(entries[:30]) - 1
                connector = "└── " if is_last else "├── "
                if entry.is_dir():
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    ext = "    " if is_last else "│   "
                    _walk(entry, prefix + ext, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{entry.name}")

        _walk(root, "", 0)
        return "\n".join(lines[:100])  # Cap at 100 lines

    def _get_git_info(self) -> str:
        """Get compact git info."""
        import subprocess

        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=self.working_dir,
                timeout=5,
            )
            if branch.returncode != 0:
                return ""

            status = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.working_dir,
                timeout=5,
            )
            changed = len(status.stdout.strip().split("\n")) if status.stdout.strip() else 0

            return f"Branch: {branch.stdout.strip()} | {changed} changed files"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""

    def _get_config_summaries(self) -> str:
        """Get compact summaries of key config files."""
        if not self._architecture:
            return ""

        summaries = []
        root = Path(self.working_dir)

        for cfg_name in self._architecture.config_files[:5]:  # Limit to 5
            cfg_path = root / cfg_name
            try:
                content = cfg_path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 2000:
                    content = content[:2000] + "..."
                summaries.append(f"--- {cfg_name} ---\n{content}")
            except OSError:
                continue

        return "\n\n".join(summaries)

    def _extract_imports(self, content: str, suffix: str) -> list[str]:
        """Extract import statements from file content."""
        imports = []

        if suffix in (".py", ".pyx", ".pyi"):
            # Python imports
            for match in re.finditer(
                r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", content, re.MULTILINE
            ):
                imp = match.group(1) or match.group(2)
                if imp:
                    imports.append(imp)

        elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs"):
            # JS/TS imports
            for match in re.finditer(
                r"(?:import\s+(?:[^'\"]+?\s+from\s+)?|require\s*\(\s*)"
                r"['\"]([^'\"]+)['\"]",
                content,
            ):
                imports.append(match.group(1))

        elif suffix in (".rs",):
            # Rust use statements
            for match in re.finditer(r"^use\s+([\w:]+)", content, re.MULTILINE):
                imports.append(match.group(1))

        elif suffix in (".go",):
            # Go imports
            for match in re.finditer(r'"([^"]+)"', content):
                imports.append(match.group(1))

        return imports[:50]  # Cap at 50 imports

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars for English)."""
        return len(text) // 4
