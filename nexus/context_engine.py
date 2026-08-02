"""Persistent, incremental repository intelligence for Nexus.

The graph intentionally starts with deterministic parsers available in the
standard library.  Python receives native AST indexing; JavaScript,
TypeScript, Go, Rust, and Java receive conservative import/symbol extraction.
Unknown or malformed files are skipped rather than converted into invented
relationships.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from nexus.paths import nexus_home

GRAPH_SCHEMA_VERSION = "nexus.repograph.v2"
SUPPORTED_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".rb",
    ".php",
    ".cs",
    ".swift",
    ".sql",
    ".graphql",
    ".prisma",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
}
IGNORED_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".nexusai",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
    "coverage",
    "verification_evidence",
    ".venv",
    "venv",
}


@dataclass
class SymbolRecord:
    """One declared symbol and its source location."""

    name: str
    kind: str
    path: str
    line: int
    qualified_name: str = ""


@dataclass
class FileRecord:
    """Indexed facts for one source file."""

    path: str
    language: str
    mtime_ns: int
    size: int
    sha256: str
    imports: list[str] = field(default_factory=list)
    symbols: list[SymbolRecord] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    database_models: list[str] = field(default_factory=list)
    configuration: bool = False
    owners: list[str] = field(default_factory=list)
    is_test: bool = False
    parse_error: str = ""


@dataclass
class IndexStats:
    scanned: int = 0
    indexed: int = 0
    reused: int = 0
    removed: int = 0
    parse_errors: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContextEngine:
    """Incremental repository graph persisted outside the project tree."""

    def __init__(
        self,
        root: str | Path,
        *,
        state_root: str | Path | None = None,
        max_files: int = 5000,
    ):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Repository root does not exist: {self.root}")
        digest = hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()[:16]
        base = Path(state_root).expanduser().resolve() if state_root else nexus_home()
        self.cache_dir = base / "repo-graphs" / digest
        self.cache_path = self.cache_dir / "graph.json"
        self.max_files = max(1, int(max_files))
        self.files: dict[str, FileRecord] = {}
        self.generated_at = ""
        self._load()

    def build(self, *, force: bool = False) -> IndexStats:
        """Index changed files and remove facts for deleted files."""
        candidates = list(self._iter_source_files())
        if len(candidates) > self.max_files:
            candidates = candidates[: self.max_files]

        stats = IndexStats(scanned=len(candidates))
        old = {} if force else dict(self.files)
        updated: dict[str, FileRecord] = {}

        for path in candidates:
            relative = path.relative_to(self.root).as_posix()
            try:
                stat = path.stat()
            except OSError:
                continue
            prior = old.get(relative)
            if prior and prior.mtime_ns == stat.st_mtime_ns and prior.size == stat.st_size:
                updated[relative] = prior
                stats.reused += 1
                continue
            record = self._index_file(path, relative, stat.st_mtime_ns, stat.st_size)
            updated[relative] = record
            stats.indexed += 1
            if record.parse_error:
                stats.parse_errors += 1

        stats.removed = len(set(old) - set(updated))
        self.files = updated
        self.generated_at = _utc_now()
        self._save()
        return stats

    def update_paths(self, paths: Iterable[str | Path]) -> IndexStats:
        """Incrementally refresh paths accepted by a file mutation."""
        stats = IndexStats()
        for raw in paths:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = self.root / path
            path = path.resolve()
            try:
                relative = path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            stats.scanned += 1
            if not path.exists():
                if relative in self.files:
                    self.files.pop(relative)
                    stats.removed += 1
                continue
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            record = self._index_file(path, relative, stat.st_mtime_ns, stat.st_size)
            self.files[relative] = record
            stats.indexed += 1
            if record.parse_error:
                stats.parse_errors += 1
        self.generated_at = _utc_now()
        self._save()
        return stats

    def find_symbols(self, query: str, *, limit: int = 50) -> list[SymbolRecord]:
        """Find declarations by exact, prefix, or substring name."""
        needle = query.strip().lower()
        if not needle:
            return []
        ranked: list[tuple[int, SymbolRecord]] = []
        for record in self.files.values():
            for symbol in record.symbols:
                name = symbol.name.lower()
                qualified = symbol.qualified_name.lower()
                if name == needle or qualified == needle:
                    rank = 0
                elif name.startswith(needle) or qualified.startswith(needle):
                    rank = 1
                elif needle in name or needle in qualified:
                    rank = 2
                else:
                    continue
                ranked.append((rank, symbol))
        ranked.sort(key=lambda item: (item[0], item[1].path, item[1].line))
        return [item[1] for item in ranked[: max(1, limit)]]

    def find_callers(self, symbol: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return files that contain a parsed reference to *symbol*."""
        needle = symbol.strip()
        if not needle:
            return []
        results = []
        for record in self.files.values():
            if needle in record.references:
                results.append(
                    {
                        "path": record.path,
                        "language": record.language,
                        "is_test": record.is_test,
                    }
                )
        return sorted(results, key=lambda item: (not item["is_test"], item["path"]))[
            : max(1, limit)
        ]

    def dependencies(self, path: str | Path) -> dict[str, list[str]]:
        """Return direct imports and reverse importers for a repository path."""
        relative = self._relative_key(path)
        record = self.files.get(relative)
        imports = list(record.imports) if record else []
        stems = self._module_names(relative)
        imported_by = []
        for candidate in self.files.values():
            if candidate.path == relative:
                continue
            if any(self._import_matches(item, relative, stems) for item in candidate.imports):
                imported_by.append(candidate.path)
        return {
            "imports": sorted(dict.fromkeys(imports)),
            "imported_by": sorted(dict.fromkeys(imported_by)),
        }

    def impacted_tests(self, paths: Iterable[str | Path], *, limit: int = 100) -> list[str]:
        """Rank tests directly or transitively connected to changed files."""
        changed = {self._relative_key(path) for path in paths}
        frontier = set(changed)
        impacted = set()
        visited = set(changed)

        for _depth in range(4):
            next_frontier = set()
            for candidate in self.files.values():
                if candidate.path in visited:
                    continue
                deps = self.dependencies(candidate.path)["imports"]
                if any(
                    self._import_matches(dep, target, self._module_names(target))
                    for dep in deps
                    for target in frontier
                ):
                    if candidate.is_test:
                        impacted.add(candidate.path)
                    else:
                        next_frontier.add(candidate.path)
                    visited.add(candidate.path)
            frontier = next_frontier
            if not frontier:
                break

        for path in changed:
            record = self.files.get(path)
            if record and record.is_test:
                impacted.add(path)
        return sorted(impacted)[: max(1, limit)]

    def relevant_files(self, query: str, *, limit: int = 40) -> list[dict[str, Any]]:
        """Rank files using names, symbols, routes, models, tests, and Git changes."""
        terms = {
            term
            for term in re.findall(r"[A-Za-z_][A-Za-z0-9_-]{2,}", query.lower())
            if term
            not in {
                "add",
                "build",
                "create",
                "fix",
                "make",
                "implement",
                "with",
                "from",
                "this",
                "that",
                "the",
                "and",
            }
        }
        changed = set(self.git_changed_files())
        ranked: list[tuple[int, str, list[str]]] = []
        for record in self.files.values():
            haystacks = {
                "path": record.path.lower(),
                "symbols": " ".join(item.name for item in record.symbols).lower(),
                "routes": " ".join(record.routes).lower(),
                "models": " ".join(record.database_models).lower(),
                "imports": " ".join(record.imports).lower(),
            }
            score = 0
            reasons: list[str] = []
            for term in terms:
                if term in haystacks["path"]:
                    score += 8
                    reasons.append(f"path:{term}")
                if term in haystacks["symbols"]:
                    score += 6
                    reasons.append(f"symbol:{term}")
                if term in haystacks["routes"]:
                    score += 7
                    reasons.append(f"route:{term}")
                if term in haystacks["models"]:
                    score += 7
                    reasons.append(f"model:{term}")
                if term in haystacks["imports"]:
                    score += 2
            if record.path in changed:
                score += 2
                reasons.append("recent-git-change")
            if record.is_test and any(
                token in query.lower() for token in ("test", "bug", "fix", "regression")
            ):
                score += 4
                reasons.append("test")
            if score:
                ranked.append((score, record.path, list(dict.fromkeys(reasons))))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            {"path": path, "score": score, "reasons": reasons}
            for score, path, reasons in ranked[: max(1, limit)]
        ]

    def context_bundle(
        self,
        query: str,
        *,
        max_files: int = 12,
        max_chars: int = 36_000,
        lines_per_file: int = 120,
    ) -> str:
        """Return a compact, query-focused repository context bundle.

        The bundle combines ranked files, declaration windows, direct import
        relationships, likely impacted tests, and ownership metadata. It avoids
        dumping whole large files into the model context and gives every excerpt
        stable line numbers so follow-up reads and edits can be surgical.
        """

        if not self.files:
            self.build(force=False)
        ranked = self.relevant_files(query, limit=max(1, max_files * 2))
        selected = [item["path"] for item in ranked[:max_files]]
        if selected:
            for test_path in self.impacted_tests(selected, limit=max(2, max_files // 3)):
                if test_path not in selected:
                    selected.append(test_path)
                if len(selected) >= max_files:
                    break
        if not selected:
            return ""

        terms = {
            token.lower()
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)
        }
        sections = ["[QUERY-FOCUSED REPOSITORY CONTEXT]"]
        consumed = len(sections[0])
        for relative in selected:
            record = self.files.get(relative)
            path = self.root / relative
            if not record or not path.is_file() or record.size > 2_000_000:
                continue
            dependencies = self.dependencies(relative)
            symbol_names = [item.name for item in record.symbols[:20]]
            header = (
                f"\n--- {relative} [{record.language}] "
                f"test={record.is_test} owners={record.owners or ['unassigned']} ---\n"
                f"symbols={symbol_names}\n"
                f"imports={dependencies['imports'][:16]}\n"
                f"imported_by={dependencies['imported_by'][:16]}\n"
            )
            if consumed + len(header) >= max_chars:
                break
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            excerpt = self._focused_excerpt(
                lines,
                record,
                terms,
                max_lines=max(20, lines_per_file),
            )
            section = header + excerpt
            remaining = max_chars - consumed
            if len(section) > remaining:
                section = section[:remaining] + "\n...[context budget reached]"
            sections.append(section)
            consumed += len(section)
            if consumed >= max_chars:
                break
        return "\n".join(sections)

    @staticmethod
    def _focused_excerpt(
        lines: list[str],
        record: FileRecord,
        terms: set[str],
        *,
        max_lines: int,
    ) -> str:
        if not lines:
            return "(empty file)"
        anchors: set[int] = {0}
        for symbol in record.symbols:
            if not terms or any(term in symbol.name.lower() for term in terms):
                anchors.add(max(0, symbol.line - 1))
        if terms:
            for index, line in enumerate(lines):
                lowered = line.lower()
                if any(term in lowered for term in terms):
                    anchors.add(index)
                    if len(anchors) >= 24:
                        break

        chosen: set[int] = set()
        radius = 5
        for anchor in sorted(anchors):
            for index in range(max(0, anchor - radius), min(len(lines), anchor + radius + 1)):
                chosen.add(index)
                if len(chosen) >= max_lines:
                    break
            if len(chosen) >= max_lines:
                break
        if len(chosen) < min(max_lines, 30):
            for index in range(min(len(lines), max_lines - len(chosen))):
                chosen.add(index)

        rendered: list[str] = []
        previous = -2
        for index in sorted(chosen)[:max_lines]:
            if index > previous + 1:
                rendered.append("    ...")
            rendered.append(f"{index + 1:5}: {lines[index]}")
            previous = index
        return "\n".join(rendered)

    def routes(self, query: str = "") -> list[dict[str, Any]]:
        """Return discovered API/UI routes."""
        needle = query.lower().strip()
        results = []
        for record in self.files.values():
            for route in record.routes:
                if needle and needle not in route.lower():
                    continue
                results.append(
                    {
                        "path": record.path,
                        "route": route,
                        "language": record.language,
                    }
                )
        return sorted(results, key=lambda item: (item["route"], item["path"]))

    def models(self, query: str = "") -> list[dict[str, Any]]:
        """Return discovered ORM/schema model declarations."""
        needle = query.lower().strip()
        results = []
        for record in self.files.values():
            for model in record.database_models:
                if needle and needle not in model.lower():
                    continue
                results.append(
                    {
                        "path": record.path,
                        "model": model,
                        "language": record.language,
                    }
                )
        return sorted(results, key=lambda item: (item["model"], item["path"]))

    def ownership(self, path: str | Path) -> list[str]:
        """Return deterministic CODEOWNERS matches for a repository path."""
        relative = self._relative_key(path)
        record = self.files.get(relative)
        return list(record.owners) if record else self._owners_for(relative)

    def git_changed_files(self, *, limit: int = 200) -> list[str]:
        """Return working-tree and recently committed files when Git is available."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                ],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
        except (OSError, subprocess.TimeoutExpired):
            return []
        paths = []
        for line in result.stdout.splitlines():
            raw = line[3:].split(" -> ")[-1].strip()
            if raw:
                paths.append(raw)
        return list(dict.fromkeys(paths))[: max(1, limit)]

    def git_history(self, path: str | Path, *, limit: int = 10) -> list[dict[str, str]]:
        """Return recent commits affecting a file for Git-aware relevance."""
        relative = self._relative_key(path)
        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"-n{max(1, min(int(limit), 100))}",
                    "--format=%H%x09%an%x09%aI%x09%s",
                    "--",
                    relative,
                ],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=8,
            )
            if result.returncode != 0:
                return []
        except (OSError, subprocess.TimeoutExpired):
            return []
        entries = []
        for line in result.stdout.splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                entries.append(
                    {
                        "commit": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": parts[3],
                    }
                )
        return entries

    def summary(self) -> dict[str, Any]:
        """Return compact graph statistics for prompt context and diagnostics."""
        symbols = sum(len(record.symbols) for record in self.files.values())
        imports = sum(len(record.imports) for record in self.files.values())
        tests = sum(1 for record in self.files.values() if record.is_test)
        routes = sum(len(record.routes) for record in self.files.values())
        models = sum(len(record.database_models) for record in self.files.values())
        configurations = sum(1 for record in self.files.values() if record.configuration)
        errors = sum(1 for record in self.files.values() if record.parse_error)
        languages: dict[str, int] = {}
        for record in self.files.values():
            languages[record.language] = languages.get(record.language, 0) + 1
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "root": str(self.root),
            "generated_at": self.generated_at,
            "files": len(self.files),
            "symbols": symbols,
            # Stable aliases retained for planner/backward compatibility.
            "total_files": len(self.files),
            "total_symbols": symbols,
            "imports": imports,
            "tests": tests,
            "routes": routes,
            "database_models": models,
            "configuration_files": configurations,
            "parse_errors": errors,
            "languages": dict(sorted(languages.items())),
            "frameworks": self.frameworks(),
            "git_changed_files": self.git_changed_files(),
            "cache_path": str(self.cache_path),
        }

    def frameworks(self) -> list[str]:
        """Detect common frameworks from indexed imports and config files."""
        imports = {item.lower() for record in self.files.values() for item in record.imports}
        paths = set(self.files)
        detected = []
        mapping = (
            ("fastapi", "FastAPI"),
            ("django", "Django"),
            ("flask", "Flask"),
            ("express", "Express"),
            ("next", "Next.js"),
            ("react", "React"),
            ("vue", "Vue"),
            ("@angular/core", "Angular"),
            ("spring", "Spring"),
        )
        for marker, label in mapping:
            if any(marker in item for item in imports):
                detected.append(label)
        if "next.config.js" in paths or "next.config.mjs" in paths:
            detected.append("Next.js")
        if "prisma/schema.prisma" in paths:
            detected.append("Prisma")
        return list(dict.fromkeys(detected))

    def _iter_source_files(self) -> Iterable[Path]:
        import os
        paths = []
        scanned_files = 0
        for root, dirs, files in os.walk(self.root):
            # Prune ignored directories in-place to avoid traversing them
            dirs[:] = [
                d for d in dirs 
                if d not in IGNORED_PARTS 
                and d not in {"Library", "Applications"}
                and (not d.startswith(".") or d in {".github", ".vscode"})
            ]
            for file in files:
                scanned_files += 1
                if scanned_files > 50000:
                    break
                if file in IGNORED_PARTS:
                    continue
                path = Path(root) / file
                if path.is_symlink() or not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                paths.append(path)
                # Hard limit to avoid unbounded memory usage in massive directories
                if len(paths) >= 20000:
                    break
            if scanned_files > 50000 or len(paths) >= 20000:
                break
        return sorted(paths)

    def _index_file(
        self,
        path: Path,
        relative: str,
        mtime_ns: int,
        size: int,
    ) -> FileRecord:
        try:
            raw = path.read_bytes()
            source = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return FileRecord(
                path=relative,
                language=self._language(path.suffix),
                mtime_ns=mtime_ns,
                size=size,
                sha256="",
                parse_error=str(exc),
                is_test=self._is_test(relative),
            )

        language = self._language(path.suffix)
        imports: list[str] = []
        symbols: list[SymbolRecord] = []
        references: list[str] = []
        routes: list[str] = []
        database_models: list[str] = []
        parse_error = ""

        if path.suffix.lower() in {".py", ".pyi"}:
            try:
                tree = ast.parse(source, filename=relative)
                imports, symbols, references = self._index_python(tree, relative)
                routes, database_models = self._index_python_frameworks(tree)
            except SyntaxError as exc:
                parse_error = f"{exc.msg} at line {exc.lineno}"
        else:
            imports, symbols, references = self._index_generic(source, relative, language)
            if Path(relative).name == "package.json":
                try:
                    package_data = json.loads(source)
                except json.JSONDecodeError:
                    pass
                else:
                    for section in (
                        "dependencies",
                        "devDependencies",
                        "peerDependencies",
                        "optionalDependencies",
                    ):
                        values = package_data.get(section, {})
                        if isinstance(values, dict):
                            imports.extend(str(name) for name in values)
            routes, database_models = self._index_generic_frameworks(
                source,
                relative,
                language,
            )

        return FileRecord(
            path=relative,
            language=language,
            mtime_ns=mtime_ns,
            size=size,
            sha256=hashlib.sha256(raw).hexdigest(),
            imports=sorted(dict.fromkeys(imports)),
            symbols=symbols,
            references=sorted(dict.fromkeys(references)),
            routes=sorted(dict.fromkeys(routes)),
            database_models=sorted(dict.fromkeys(database_models)),
            configuration=self._is_configuration(relative),
            owners=self._owners_for(relative),
            is_test=self._is_test(relative),
            parse_error=parse_error,
        )

    @staticmethod
    def _index_python(
        tree: ast.AST,
        relative: str,
    ) -> tuple[list[str], list[SymbolRecord], list[str]]:
        imports: list[str] = []
        symbols: list[SymbolRecord] = []
        references: list[str] = []
        parents: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_Import(self, node: ast.Import) -> None:
                imports.extend(alias.name for alias in node.names)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                base = "." * node.level + (node.module or "")
                imports.append(base)

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                qualified = ".".join([*parents, node.name])
                symbols.append(SymbolRecord(node.name, "class", relative, node.lineno, qualified))
                parents.append(node.name)
                self.generic_visit(node)
                parents.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                qualified = ".".join([*parents, node.name])
                kind = "method" if parents else "function"
                symbols.append(SymbolRecord(node.name, kind, relative, node.lineno, qualified))
                parents.append(node.name)
                self.generic_visit(node)
                parents.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node: ast.Call) -> None:
                if isinstance(node.func, ast.Name):
                    references.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    references.append(node.func.attr)
                self.generic_visit(node)

        Visitor().visit(tree)
        return imports, symbols, references

    @staticmethod
    def _index_python_frameworks(tree: ast.AST) -> tuple[list[str], list[str]]:
        routes: list[str] = []
        models: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    func = decorator.func
                    method = func.attr.lower() if isinstance(func, ast.Attribute) else ""
                    if method not in {
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                        "route",
                        "websocket",
                    }:
                        continue
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        value = decorator.args[0].value
                        if isinstance(value, str):
                            routes.append(f"{method.upper()} {value}")
            elif isinstance(node, ast.ClassDef):
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(base.attr)
                if any(
                    name in {"Base", "Model", "Document", "DeclarativeBase"} for name in base_names
                ):
                    models.append(node.name)
        return routes, models

    @staticmethod
    def _index_generic(
        source: str,
        relative: str,
        language: str,
    ) -> tuple[list[str], list[SymbolRecord], list[str]]:
        import_patterns = (
            r"\b(?:import|from)\s+(?:[^'\"]*?\s+from\s+)?['\"]([^'\"]+)['\"]",
            r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"^\s*import\s+([A-Za-z0-9_./:-]+)",
            r"^\s*use\s+([A-Za-z0-9_:]+)",
        )
        imports: list[str] = []
        for pattern in import_patterns:
            imports.extend(re.findall(pattern, source, re.MULTILINE))

        declarations = (
            ("class", r"\bclass\s+([A-Za-z_$][\w$]*)"),
            ("function", r"\b(?:function|func|fn)\s+([A-Za-z_$][\w$]*)"),
            (
                "function",
                r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
            ),
        )
        symbols = []
        for kind, pattern in declarations:
            for match in re.finditer(pattern, source):
                line = source.count("\n", 0, match.start()) + 1
                symbols.append(SymbolRecord(match.group(1), kind, relative, line, match.group(1)))

        declared = {item.name for item in symbols}
        call_names = re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", source)
        references = [
            name
            for name in call_names
            if name not in declared
            and name not in {"if", "for", "while", "switch", "catch", "return"}
        ]
        return imports, symbols, references

    @staticmethod
    def _index_generic_frameworks(
        source: str,
        relative: str,
        language: str,
    ) -> tuple[list[str], list[str]]:
        routes = []
        route_patterns = (
            r"\b(?:app|router|server)\.(get|post|put|patch|delete|use)\s*\(\s*['\"]([^'\"]+)",
            r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+['\"]([^'\"]+)['\"]",
        )
        for match in re.finditer(route_patterns[0], source, re.I):
            routes.append(f"{match.group(1).upper()} {match.group(2)}")
        for match in re.finditer(route_patterns[1], source):
            routes.append(match.group(0).strip("'\""))

        models = []
        if Path(relative).suffix.lower() == ".prisma":
            models.extend(re.findall(r"^\s*model\s+([A-Za-z_]\w*)", source, re.MULTILINE))
        if Path(relative).suffix.lower() == ".sql":
            models.extend(
                re.findall(
                    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([A-Za-z_]\w*)",
                    source,
                    re.I,
                )
            )
        if language in {"typescript", "javascript"}:
            models.extend(
                re.findall(
                    r"\b(?:mongoose\.model|sequelize\.define)\s*\(\s*['\"]([^'\"]+)",
                    source,
                )
            )
        return routes, models

    def _relative_key(self, path: str | Path) -> str:
        item = Path(path).expanduser()
        if item.is_absolute():
            try:
                return item.resolve().relative_to(self.root).as_posix()
            except ValueError:
                return item.as_posix()
        return item.as_posix().lstrip("./")

    @staticmethod
    def _module_names(relative: str) -> set[str]:
        path = Path(relative)
        without_suffix = path.with_suffix("").as_posix()
        names = {
            without_suffix,
            without_suffix.replace("/", "."),
            path.stem,
            f"./{without_suffix}",
        }
        if path.stem == "__init__":
            parent = path.parent.as_posix()
            names.update({parent, parent.replace("/", ".")})
        return {name.strip("./") for name in names if name and name != "."}

    @staticmethod
    def _import_matches(import_name: str, target: str, names: set[str]) -> bool:
        cleaned = import_name.removesuffix(".js").removesuffix(".ts").strip("./")
        if cleaned in names:
            return True
        target_path = Path(target)
        return cleaned.endswith("/" + target_path.stem) or cleaned.endswith("." + target_path.stem)

    @staticmethod
    def _language(suffix: str) -> str:
        return {
            ".py": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".swift": "swift",
            ".sql": "sql",
            ".graphql": "graphql",
            ".prisma": "prisma",
            ".json": "configuration",
            ".toml": "configuration",
            ".yaml": "configuration",
            ".yml": "configuration",
            ".xml": "configuration",
        }.get(suffix.lower(), "unknown")

    @staticmethod
    def _is_test(relative: str) -> bool:
        lowered = relative.lower()
        name = Path(relative).name.lower()
        return (
            "/test/" in f"/{lowered}"
            or "/tests/" in f"/{lowered}"
            or name.startswith("test_")
            or name.endswith("_test.py")
            or ".test." in name
            or ".spec." in name
            or name.endswith("_test.go")
        )

    @staticmethod
    def _is_configuration(relative: str) -> bool:
        path = Path(relative)
        lowered = path.name.lower()
        return (
            lowered
            in {
                "package.json",
                "pyproject.toml",
                "cargo.toml",
                "go.mod",
                "pom.xml",
                "build.gradle",
                "dockerfile",
                "makefile",
                "tsconfig.json",
                "vite.config.ts",
                "next.config.js",
                "next.config.mjs",
            }
            or any(part in {".github", ".nexus", "config", "configs"} for part in path.parts)
            or path.suffix.lower() in {".yaml", ".yml", ".toml"}
        )

    def _owners_for(self, relative: str) -> list[str]:
        candidates = (
            self.root / ".github" / "CODEOWNERS",
            self.root / "CODEOWNERS",
            self.root / "docs" / "CODEOWNERS",
        )
        codeowners = next((path for path in candidates if path.is_file()), None)
        if not codeowners:
            return []
        owners: list[str] = []
        try:
            lines = codeowners.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        import fnmatch

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0].lstrip("/")
            normalized = pattern
            if pattern.endswith("/"):
                normalized += "**"
            if fnmatch.fnmatch(relative, normalized) or fnmatch.fnmatch(
                relative,
                f"**/{normalized}",
            ):
                owners = parts[1:]
        return owners

    def _save(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "root": str(self.root),
            "generated_at": self.generated_at,
            "files": {
                path: {
                    **asdict(record),
                    "symbols": [asdict(item) for item in record.symbols],
                }
                for path, record in sorted(self.files.items())
            },
        }
        temporary = self.cache_path.with_name(f".{self.cache_path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.cache_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("schema_version") != GRAPH_SCHEMA_VERSION:
            return
        self.generated_at = str(payload.get("generated_at", ""))
        for path, raw in payload.get("files", {}).items():
            try:
                symbols = [SymbolRecord(**item) for item in raw.get("symbols", [])]
                self.files[path] = FileRecord(
                    **{
                        **raw,
                        "symbols": symbols,
                    }
                )
            except (TypeError, ValueError):
                continue
