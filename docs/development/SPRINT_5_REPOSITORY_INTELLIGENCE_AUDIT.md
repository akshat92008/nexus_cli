# Sprint 5 — Repository Intelligence and Context Engine Audit

## 1. Executive Summary

This audit evaluates the existing repository understanding, context selection, indexing, and dependency tracking mechanisms in Nexus CLI prior to Sprint 5 implementation.

Nexus currently possesses two overlapping context/repository components:
1. `RepoGraph` (`nexus/repo_graph.py`): Incremental repository graph persisted in `~/.nexus/repo-graphs/`. Extracts Python AST declarations/routes/models, basic regex declarations for JS/TS/Go/Rust/Java, computes dependencies, impacted tests, relevant files ranking, and produces a string-formatted context bundle.
2. `ContextManager` (`nexus/context_manager.py`): Session-scoped active file access tracker, project architecture detector, file summary builder, and token-budgeted context string generator.
3. `ContextSelector` (`nexus/context_selector.py`): Unimplemented stub class in production.
4. `LSPClient` (`nexus/language_intelligence.py`): Standalone JSON-RPC 2.0 LSP client (supports Pyright, TS Server, Gopls, Rust-Analyzer) for symbol definitions and document symbols, currently not integrated into prompt/context selection pipelines.

---

## 2. Production Call Paths and Component Audit

### 2.1 Component Overview

| Component | File Path | Responsibilities | Current Usage | Status / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **`RepoGraph`** | `nexus/repo_graph.py` | AST/regex symbol extraction, file indexing, dependencies, test mapping, git status/log, context bundle | Instantiated in `Agent`, `TwoNodeBackend`, `WorkspaceManager`, `ToolExecutor` | Active but lacks typed data contracts, multi-language AST, architectural boundary awareness, and task-intent ranking |
| **`ContextManager`** | `nexus/context_manager.py` | Access tracking, architecture detection, regex import/export summaries | Instantiated in `Agent` (`self.context_mgr`) | Active duplicate path; duplicates file scanning, language detection, and import tracking |
| **`ContextSelector`** | `nexus/context_selector.py` | Stub context gatherer | Instantiated in `Session` | Dead stub; returns hardcoded empty file list |
| **`LanguageIntelligence`** | `nexus/language_intelligence.py` | LSP client wrapper | Called lazily in `tools.py` | Not connected to background indexing or context candidate generation |
| **`ProjectMemory`** | `nexus/project_memory.py` | Stored codebase notes and rules | Called in `pipeline.py` / `agent.py` | Separate text note storage; needs integration with repo snapshot identity |

---

## 3. Data-Flow Analysis

### 3.1 Legacy Context Assembly Flow

```text
Task Input
  ↓
Agent / Pipeline Initialization
  ├─> ContextManager.initialize() -> [STRUCTURE] + [CONFIG] (Regex scanned)
  └─> RepoGraph.build() -> Scans filesystem, writes graph.json
  ↓
Prompt Construction
  ├─> Agent.py calls ContextManager.get_relevant_context()
  ├─> Agent.py / Planner.py calls RepoGraph.context_bundle(query)
  └─> Both strings concatenated into LLM system/user prompt
```

### 3.2 Key Deficiencies Identified

1. **Duplicate System Scans**: `ContextManager` and `RepoGraph` perform separate filesystem walks, separate language detection dictionary lookups, and separate import parsing.
2. **Untyped Context Outputs**: `context_bundle()` returns a concatenated string formatted with pseudo-markdown delimiters (`--- filename ---`) rather than a typed `ContextBundle` data contract.
3. **Regex Degradation on Modern Languages**: Non-Python languages (JavaScript, TypeScript, Go, Rust, Java) fall back to primitive single-line regex patterns for symbol declarations and imports. TypeScript interfaces, type aliases, React components, and re-exports are missing or unreliable.
4. **Opaque Keyword Ranking**: `relevant_files()` uses simple term string matching against path, symbol name, route, and model strings with arbitrary weight constants (+8 for path, +6 for symbol, +7 for route/model, +2 for imports). It lacks task intent classification (e.g., bug fix vs feature vs refactor vs test repair).
5. **No Architectural & Secret Awareness**: Neither `RepoGraph` nor `ContextManager` redacts sensitive credentials/tokens in `.env` or recognizes structural layer boundaries (UI vs Domain vs Verification).
6. **No Context Quality Benchmark**: No oracle-backed benchmark exists to evaluate relevant file recall, precision, test recall, or irrelevant token cost across tasks.

---

## 4. Consolidated Target Data-Flow Architecture

```text
Task & Intent Classification
  ↓
Repository Discovery & Snapshot
  ↓
Incremental Indexing & Dependency Graph (AST + Tree-sitter / Parser)
  ↓
Task-Specific Candidate Generation (Symbols, Error Traces, Imports, Tests, Config, History)
  ↓
Explainable Ranking Engine & Context Budgeting
  ↓
Typed ContextBundle Construction & Model Presentation
```

---

## 5. Audit Validation & Next Steps

This audit confirms that Sprint 5 must unify `RepoGraph`, `ContextManager`, and `ContextSelector` into a canonical **Repository Intelligence and Context Engine**, implementing typed contracts (`RepositorySnapshot`, `RepositoryFile`, `RepositorySymbol`, `ContextBundle`), parser-based multi-language extraction, task-intent ranking, secret redaction, context-selection benchmarks, and end-to-end qualification tests.
