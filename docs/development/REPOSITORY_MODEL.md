# Canonical Repository Model Specification — Sprint 5

## 1. Overview

Sprint 5 establishes a canonical typed representation for codebase elements in Nexus CLI. This replaces unstructured strings and regex outputs with deterministic, strongly-typed Python dataclasses.

---

## 2. Model Contracts

### 2.1 `RepositorySnapshot`
Represents a deterministic point-in-time state of the repository:
```python
class RepositorySnapshot:
    repository_id: str
    root: Path
    revision: str | None
    tree_hash: str
    created_at: str
    language_profiles: list[str]
    files: dict[str, RepositoryFile]
    symbols: dict[str, RepositorySymbol]
    relationships: list[Any]
    warnings: list[str]
```

### 2.2 `RepositoryFile`
Represents indexed facts for one repository file:
```python
class RepositoryFile:
    path: str
    language: str | None
    size_bytes: int
    content_hash: str
    mtime_ns: int
    tracked: bool
    generated: bool
    vendored: bool
    binary: bool
    protected: bool
    test_file: bool
    config_file: bool
    migration_file: bool
    risk_level: RiskLevel
    category: str
    imports: list[str]
    exports: list[str]
    references: list[str]
    routes: list[str]
    database_models: list[str]
    symbols: list[RepositorySymbol]
    parse_error: str
```

### 2.3 `RepositorySymbol`
Represents a declared symbol and its attributes:
```python
class RepositorySymbol:
    name: str
    kind: str  # module, class, function, method, interface, type, constant, decorator
    file_path: str
    line: int
    end_line: int
    qualified_name: str
    signature: str
    visibility: str
    parent_symbol: str | None
    docstring: str
    content_hash: str
    imports: list[str]
    references: list[str]
    callers: list[str]
    callees: list[str]
```

### 2.4 `ContextBundle`
Typed container sent to planner and model prompts:
```python
class ContextBundle:
    task_intent: TaskIntent
    repository_tree_hash: str
    files: list[ContextFile]
    symbols: list[ContextSymbol]
    tests: list[TestRelationship]
    constraints: list[ArchitectureBoundary]
    risks: list[RiskAnnotation]
    estimated_tokens: int
    confidence: float
    limitations: list[str]
    omitted_candidates: list[str]
    selection_rationales: dict[str, list[str]]
    created_at: str
```

---

## 3. Freshness Identity & Invalidation

Repository snapshots are tagged with a sha256 `tree_hash` generated from sorted relative file paths, modification times (`st_mtime_ns`), and file sizes (`st_size`).

When files are mutated, `RepositoryIntelligence.update_paths([path])` performs incremental re-indexing, re-calculating `tree_hash`. Any context bundle with a mismatched `repository_tree_hash` is marked stale and discarded.
