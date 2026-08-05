"""Authoritative Repository Intelligence Engine for Nexus CLI — Sprint 5."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from nexus.paths import nexus_home
from nexus.intelligence.repository.model import (
    ArchitectureBoundary,
    ContextBundle,
    ContextCandidate,
    ContextRelationship,
    ContextSymbol,
    RepositoryFile,
    RepositorySnapshot,
    RepositorySymbol,
    RiskAnnotation,
    RiskLevel,
    TaskIntent,
    TestRelationship,
)
from nexus.intelligence.repository.discovery import RepositoryDiscovery
from nexus.intelligence.repository.classification import FileClassifier
from nexus.intelligence.repository.extraction import LanguageExtractor
from nexus.intelligence.repository.ranking import ExplainableContextRanker, TaskIntentClassifier
from nexus.intelligence.repository.budget import ContextBudgetManager
from nexus.intelligence.repository.secrets import SecretProtector

GRAPH_SCHEMA_VERSION = "nexus.repograph.v5"


class RepositoryIntelligence:
    """Canonical repository intelligence system managing graph indexing and context selection."""

    def __init__(
        self,
        root: str | Path,
        *,
        state_root: str | Path | None = None,
        max_files: int = 10000,
    ):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Repository root does not exist: {self.root}")

        digest = hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()[:16]
        base = Path(state_root).expanduser().resolve() if state_root else nexus_home()
        self.cache_dir = base / "repo-graphs" / digest
        self.cache_path = self.cache_dir / "graph.json"
        self.max_files = max_files

        self.discovery = RepositoryDiscovery(self.root)
        self.extractor = LanguageExtractor()
        self.ranker = ExplainableContextRanker()
        self.budget_manager = ContextBudgetManager()

        self.files: dict[str, RepositoryFile] = {}
        self.tree_hash: str = ""
        self.generated_at: str = ""
        self._load_cache()

    def build(self, force: bool = False) -> dict[str, Any]:
        """Discover and index files incrementally or forcefully."""
        discovered_paths = self.discovery.discover_files(self.max_files)
        new_tree_hash = self.discovery.calculate_tree_hash(discovered_paths)

        if not force and self.tree_hash == new_tree_hash and self.files:
            return {"indexed": 0, "reused": len(self.files), "tree_hash": self.tree_hash}

        updated_files: dict[str, RepositoryFile] = {}
        indexed_count = 0
        reused_count = 0

        for path in discovered_paths:
            try:
                rel_path = path.relative_to(self.root).as_posix()
                stat = path.stat()
            except (ValueError, OSError):
                continue

            prior = self.files.get(rel_path) if not force else None
            if prior and prior.mtime_ns == stat.st_mtime_ns and prior.size_bytes == stat.st_size:
                updated_files[rel_path] = prior
                reused_count += 1
                continue

            record = self._index_single_file(path, rel_path, stat)
            updated_files[rel_path] = record
            indexed_count += 1

        self.files = updated_files
        self.tree_hash = new_tree_hash
        self.generated_at = datetime.now(timezone.utc).isoformat()
        self._save_cache()

        return {
            "indexed": indexed_count,
            "reused": reused_count,
            "total": len(self.files),
            "tree_hash": self.tree_hash,
        }

    def update_paths(self, paths: Iterable[str | Path]) -> None:
        """Refresh index for specific mutated or added files."""
        for raw in paths:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = self.root / path
            path = path.resolve()

            try:
                rel_path = path.relative_to(self.root).as_posix()
            except ValueError:
                continue

            if not path.exists() or not path.is_file():
                self.files.pop(rel_path, None)
                continue

            try:
                stat = path.stat()
                record = self._index_single_file(path, rel_path, stat)
                self.files[rel_path] = record
            except OSError:
                continue

        self.tree_hash = self.discovery.calculate_tree_hash([self.root / p for p in self.files])
        self.generated_at = datetime.now(timezone.utc).isoformat()
        self._save_cache()

    def context_bundle(
        self,
        query: str,
        *,
        explicit_files: list[str] | None = None,
        failing_stack_files: list[str] | None = None,
        max_files: int = 12,
        max_total_tokens: int = 24000,
    ) -> ContextBundle:
        """Assemble a typed, explainable ContextBundle for model consumption."""
        if not self.files:
            self.build(force=False)

        task_intent = TaskIntentClassifier.classify(query)
        changed_git = self.git_changed_files()

        # Candidate generation and explainable ranking
        candidates = self.ranker.rank_candidates(
            query,
            self.files,
            changed_git,
            explicit_user_files=explicit_files,
            failing_stack_files=failing_stack_files,
            limit=max_files * 2,
        )

        # Filter low-relevance candidates if decisive candidates exist
        if candidates and candidates[0].score >= 20.0:
            top_score = candidates[0].score
            candidates = [c for c in candidates if c.score >= top_score * 0.3]

        search_terms = {
            t.lower() for t in query.split() if len(t) > 2
        }

        # Budget assembly
        self.budget_manager.max_files = max_files
        self.budget_manager.max_total_tokens = max_total_tokens

        selected_files, omitted_candidates, token_count = self.budget_manager.assemble_context_files(
            candidates, self.files, self.root, search_terms
        )

        # Related tests, symbols, and architecture constraints
        test_rels = self._build_test_relationships([f.path for f in selected_files])
        symbols = self._extract_context_symbols(selected_files)
        boundaries = self._infer_architecture_boundaries()
        risks = self._collect_risk_annotations(selected_files)

        rationales = {
            f.path: [f.selection_reason] for f in selected_files
        }

        return ContextBundle(
            task_intent=task_intent,
            repository_tree_hash=self.tree_hash,
            files=selected_files,
            symbols=symbols,
            tests=test_rels,
            constraints=boundaries,
            risks=risks,
            estimated_tokens=token_count,
            confidence=0.9 if selected_files else 0.4,
            omitted_candidates=omitted_candidates,
            selection_rationales=rationales,
        )

    def expand_context(
        self,
        bundle: ContextBundle,
        reason: str,
        additional_files: list[str] | None = None,
    ) -> ContextBundle:
        """Evidence-driven context expansion loop when dependencies are missing."""
        expanded_explicit = [f.path for f in bundle.files]
        if additional_files:
            for f in additional_files:
                if f not in expanded_explicit:
                    expanded_explicit.append(f)

        new_bundle = self.context_bundle(
            query=f"{bundle.task_intent.value} expansion: {reason}",
            explicit_files=expanded_explicit,
            max_files=min(24, bundle.files.__len__() + 6),
            max_total_tokens=bundle.estimated_tokens + 8000,
        )
        new_bundle.limitations.append(f"Expanded due to: {reason}")
        return new_bundle

    def find_symbols(self, query: str, limit: int = 50) -> list[RepositorySymbol]:
        needle = query.strip().lower()
        if not needle:
            return []
        matches: list[RepositorySymbol] = []
        for file_record in self.files.values():
            for symbol in file_record.symbols:
                if needle in symbol.name.lower() or needle in symbol.qualified_name.lower():
                    matches.append(symbol)
        return matches[:limit]

    def find_callers(self, symbol_name: str, limit: int = 100) -> list[dict[str, Any]]:
        needle = symbol_name.strip()
        if not needle:
            return []
        results = []
        for file_record in self.files.values():
            if needle in file_record.references:
                results.append(
                    {
                        "path": file_record.path,
                        "language": file_record.language,
                        "is_test": file_record.is_test,
                    }
                )
        return sorted(results, key=lambda item: (not item["is_test"], item["path"]))[: max(1, limit)]

    def impacted_tests(self, paths: Iterable[str | Path], limit: int = 100) -> list[str]:
        changed = {self._relative_key(path) for path in paths}
        frontier = set(changed)
        impacted = set()
        visited = set(changed)

        for _depth in range(4):
            next_frontier = set()
            frontier_stems = {Path(p).stem for p in frontier}
            for candidate in self.files.values():
                if candidate.path in visited:
                    continue
                deps = candidate.imports
                if any(target in deps or any(target in dep for dep in deps) for target in frontier_stems):
                    if candidate.test_file or getattr(candidate, "is_test", False):
                        impacted.add(candidate.path)
                    else:
                        next_frontier.add(candidate.path)
                    visited.add(candidate.path)
            frontier = next_frontier
            if not frontier:
                break

        for path in changed:
            record = self.files.get(path)
            if record and (record.test_file or getattr(record, "is_test", False)):
                impacted.add(path)
        return sorted(impacted)[: max(1, limit)]

    def ownership(self, path: str | Path) -> list[str]:
        rel = self._relative_key(path)
        return self._owners_for(rel)

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
            if (
                fnmatch.fnmatch(relative, normalized)
                or fnmatch.fnmatch(relative, f"**/{normalized}")
                or fnmatch.fnmatch(f"/{relative}", pattern)
                or fnmatch.fnmatch(relative, pattern)
            ):
                owners = parts[1:]
        return owners

    def git_changed_files(self) -> list[str]:
        try:
            # SECURITY CLASSIFICATION: INTERNAL_GIT_OP
            res = subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                return []
            paths = []
            for line in res.stdout.splitlines():
                raw = line[3:].split(" -> ")[-1].strip()
                if raw:
                    paths.append(raw)
            return paths
        except (OSError, subprocess.TimeoutExpired):
            return []

    def summary(self) -> dict[str, Any]:
        total_symbols = sum(len(f.symbols) for f in self.files.values())
        tests_count = sum(1 for f in self.files.values() if f.is_test)
        configs_count = sum(1 for f in self.files.values() if f.config_file)
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "tree_hash": self.tree_hash,
            "root": str(self.root),
            "files_count": len(self.files),
            "symbols_count": total_symbols,
            "tests_count": tests_count,
            "configs_count": configs_count,
        }

    # ── Internal Helpers ──

    def _index_single_file(self, full_path: Path, rel_path: str, stat: os.stat_result) -> RepositoryFile:
        classification = FileClassifier.classify(rel_path)
        
        try:
            source = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            source = ""
            classification["parse_error"] = str(exc)

        extracted = self.extractor.extract(rel_path, source) if source else {
            "imports": [], "symbols": [], "references": [], "routes": [], "database_models": [], "parse_error": ""
        }

        # Check for secrets
        _, has_secrets = SecretProtector.sanitize(source, rel_path)
        if has_secrets:
            classification["is_protected"] = True
            classification["risk_level"] = RiskLevel.HIGH

        return RepositoryFile(
            path=rel_path,
            language=classification.get("category"),
            size_bytes=stat.st_size,
            content_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            mtime_ns=stat.st_mtime_ns,
            tracked=True,
            generated=classification["is_generated"],
            vendored=classification["is_vendored"],
            binary=classification["is_binary"],
            protected=classification["is_protected"],
            test_file=classification["is_test"],
            config_file=classification["is_config"],
            migration_file=classification["is_migration"],
            risk_level=classification["risk_level"],
            category=classification["category"],
            imports=extracted["imports"],
            exports=[s.name for s in extracted["symbols"] if s.kind in {"class", "function", "interface"}],
            references=extracted.get("references", []),
            routes=extracted.get("routes", []),
            database_models=extracted.get("database_models", []),
            symbols=extracted["symbols"],
            parse_error=extracted["parse_error"] or classification.get("parse_error", ""),
        )

    def _build_test_relationships(self, selected_paths: list[str]) -> list[TestRelationship]:
        rels: list[TestRelationship] = []
        for path in selected_paths:
            for test_path in self.impacted_tests([path], limit=5):
                rels.append(
                    TestRelationship(
                        source_file=path,
                        test_file=test_path,
                        relationship_type="DIRECT_IMPORT",
                        confidence=0.9,
                        reason=f"{test_path} exercises {path}",
                    )
                )
        return rels

    def _extract_context_symbols(self, selected_files: Any) -> list[ContextSymbol]:
        ctx_symbols = []
        for ctx_file in selected_files:
            repo_file = self.files.get(ctx_file.path)
            if repo_file:
                for symbol in repo_file.symbols[:6]:
                    ctx_symbols.append(
                        ContextSymbol(
                            name=symbol.name,
                            kind=symbol.kind,
                            file_path=symbol.file_path,
                            line=symbol.line,
                            signature=symbol.signature,
                            relevance_reason=ctx_file.selection_reason,
                        )
                    )
        return ctx_symbols

    def _infer_architecture_boundaries(self) -> list[ArchitectureBoundary]:
        boundaries = [
            ArchitectureBoundary(layer_name="verification", files=[p for p in self.files if "verification" in p]),
            ArchitectureBoundary(layer_name="provider", files=[p for p in self.files if "providers/" in p]),
            ArchitectureBoundary(layer_name="execution", files=[p for p in self.files if "execution/" in p]),
        ]
        return [b for b in boundaries if b.files]

    def _collect_risk_annotations(self, selected_files: Any) -> list[RiskAnnotation]:
        annotations = []
        for ctx_file in selected_files:
            repo_file = self.files.get(ctx_file.path)
            if repo_file and repo_file.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                annotations.append(
                    RiskAnnotation(
                        path=ctx_file.path,
                        risk_level=repo_file.risk_level,
                        reasons=[f"High-risk component ({repo_file.category})"],
                    )
                )
        return annotations

    def _relative_key(self, path: str | Path) -> str:
        item = Path(path).expanduser()
        if item.is_absolute():
            try:
                return item.resolve().relative_to(self.root).as_posix()
            except ValueError:
                return item.as_posix()
        return item.as_posix().lstrip("./")

    def _save_cache(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "tree_hash": self.tree_hash,
            "root": str(self.root),
            "generated_at": self.generated_at,
            "files": {
                p: {
                    **asdict(r),
                    "symbols": [asdict(s) for s in r.symbols],
                    "risk_level": r.risk_level.value if isinstance(r.risk_level, RiskLevel) else r.risk_level,
                }
                for p, r in sorted(self.files.items())
            },
        }
        tmp = self.cache_path.with_name(f".{self.cache_path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.cache_path)
        finally:
            tmp.unlink(missing_ok=True)

    def _load_cache(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("schema_version") != GRAPH_SCHEMA_VERSION:
            return
        self.tree_hash = str(payload.get("tree_hash", ""))
        self.generated_at = str(payload.get("generated_at", ""))
        for p, raw in payload.get("files", {}).items():
            try:
                symbols = [RepositorySymbol(**s) for s in raw.get("symbols", [])]
                risk = RiskLevel(raw.get("risk_level", "low"))
                raw_clean = {k: v for k, v in raw.items() if k not in {"symbols", "risk_level"}}
                self.files[p] = RepositoryFile(
                    symbols=symbols,
                    risk_level=risk,
                    **raw_clean,
                )
            except (TypeError, ValueError):
                continue
