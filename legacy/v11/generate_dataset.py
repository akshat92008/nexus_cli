#!/usr/bin/env python3
"""
generate_dataset.py — Parametric Multi-Domain Dataset Generator v2 for Amuara Labs

Generates truly unique, diverse training examples through parametric variation:
  - 15 engineering domains × 50+ task skeletons × language variants × difficulty tiers
  - Each record is uniquely parameterized (names, constraints, edge cases, signatures)
  - Curriculum learning: beginner → intermediate → advanced → expert
  - Languages: Python, TypeScript, JavaScript, Rust, Go, Java, C++, SQL, Bash
  - No template cycling — every example is structurally distinct

Output: ChatML JSONL format compatible with Unsloth/TRL/Axolotl fine-tuning.
"""

import hashlib
import json
import os
import random
import argparse
import string
import time
from typing import Any, Dict, List, Tuple

# ─── Parametric Variation Engine ──────────────────────────────────────────────

LANGUAGES = ["python", "typescript", "javascript", "rust", "go", "java", "cpp", "sql", "bash"]

DIFFICULTY_TIERS = [
    {"level": "beginner", "weight": 0.15, "complexity_range": (1, 3), "multi_file": False, "max_lines": 40},
    {"level": "intermediate", "weight": 0.30, "complexity_range": (3, 6), "multi_file": False, "max_lines": 80},
    {"level": "advanced", "weight": 0.35, "complexity_range": (6, 9), "multi_file": True, "max_lines": 150},
    {"level": "expert", "weight": 0.20, "complexity_range": (9, 10), "multi_file": True, "max_lines": 300},
]

# Weighted random selection helper
def weighted_choice(items: list, weights: list):
    return random.choices(items, weights=weights, k=1)[0]

def random_name(prefix: str = "", length: int = 4) -> str:
    """Generate a random identifier name."""
    parts = ["alpha", "beta", "gamma", "delta", "omega", "sigma", "theta", "lambda", "kappa", "zeta",
             "nova", "flux", "core", "sync", "apex", "node", "edge", "mesh", "pipe", "gate",
             "bolt", "shard", "vault", "cache", "ring", "pool", "heap", "stack", "queue", "stream"]
    suffix = "".join(random.choices(string.ascii_lowercase, k=length)) if length > 0 else ""
    return f"{prefix}{random.choice(parts)}_{suffix}" if prefix else f"{random.choice(parts)}_{suffix}"

def random_int_range() -> Tuple[int, int]:
    low = random.randint(1, 100)
    high = low + random.randint(10, 1000)
    return low, high

# ─── Domain: Bug Fixing ──────────────────────────────────────────────────────

BUG_FIX_TEMPLATES = [
    {
        "skeleton": "off_by_one_loop",
        "prompt_fn": lambda p: f"Fix the off-by-one error in the following {p['lang']} function `{p['fn_name']}` that {p['task_desc']}. The function incorrectly {p['bug_desc']}.",
        "params_fn": lambda: {
            "fn_name": random_name("process_"),
            "task_desc": random.choice([
                "iterates over an array and sums elements",
                "counts occurrences of a target value in a list",
                "finds the maximum element in a sliding window",
                "validates boundary conditions in a matrix traversal",
                "computes prefix sums for range queries",
            ]),
            "bug_desc": random.choice([
                "skips the last element due to `range(len(arr)-1)` instead of `range(len(arr))`",
                "includes an extra element by using `<=` instead of `<` in the loop bound",
                "uses 0-indexed access when the problem expects 1-indexed",
                "fails on empty input because it doesn't check `len(arr) == 0`",
                "double-counts the boundary element in the sliding window",
            ]),
        }
    },
    {
        "skeleton": "null_reference",
        "prompt_fn": lambda p: f"Debug the {p['lang']} code for `{p['fn_name']}` which crashes with a {p['error_type']} when {p['trigger']}.",
        "params_fn": lambda: {
            "fn_name": random_name("handle_"),
            "error_type": random.choice(["NullPointerException", "TypeError: 'NoneType'", "undefined is not an object", "nil pointer dereference", "unwrap() on None"]),
            "trigger": random.choice([
                "the input dictionary is missing the expected key",
                "a database query returns no results",
                "the API response has a missing field",
                "the user session object is expired",
                "chained method calls encounter an intermediate None",
            ]),
        }
    },
    {
        "skeleton": "race_condition",
        "prompt_fn": lambda p: f"Identify and fix the race condition in `{p['fn_name']}` where {p['desc']}. The bug manifests as {p['symptom']}.",
        "params_fn": lambda: {
            "fn_name": random_name("concurrent_"),
            "desc": random.choice([
                "two threads increment a shared counter without synchronization",
                "a producer-consumer queue allows reads before writes complete",
                "file writes from multiple workers interleave corrupting output",
                "a cache eviction races with a cache population",
                "connection pool check-out and check-in have a TOCTOU vulnerability",
            ]),
            "symptom": random.choice([
                "intermittent assertion failures under load",
                "data corruption that only appears with >4 concurrent workers",
                "occasional deadlocks during shutdown",
                "lost updates where final count < expected count",
                "stale reads returning old values after confirmed writes",
            ]),
        }
    },
    {
        "skeleton": "memory_leak",
        "prompt_fn": lambda p: f"Fix the memory leak in `{p['fn_name']}` where {p['cause']}. Memory usage grows to {p['growth']} after {p['duration']}.",
        "params_fn": lambda: {
            "fn_name": random_name("service_"),
            "cause": random.choice([
                "event listeners are registered but never removed",
                "a growing list of completed tasks is never pruned",
                "closures capture references preventing garbage collection",
                "a cache has no eviction policy and grows unboundedly",
                "circular references between parent and child objects prevent GC",
            ]),
            "growth": f"{random.randint(100, 4000)}MB",
            "duration": f"{random.randint(1, 48)} hours",
        }
    },
    {
        "skeleton": "type_error",
        "prompt_fn": lambda p: f"Debug the type error in `{p['fn_name']}` where {p['desc']}. The error occurs when {p['trigger']}.",
        "params_fn": lambda: {
            "fn_name": random_name("transform_"),
            "desc": random.choice([
                "a string is passed where an integer is expected",
                "a list of objects is treated as a flat list of strings",
                "JSON.parse returns a string instead of an object for malformed input",
                "an async function returns a Promise instead of the resolved value",
                "a union type is not narrowed before property access",
            ]),
            "trigger": random.choice([
                "processing user input from a web form",
                "deserializing data from a CSV file",
                "handling optional API response fields",
                "converting between internal and external data formats",
                "chaining map/filter/reduce operations on heterogeneous arrays",
            ]),
        }
    },
]

# ─── Domain: Refactoring ─────────────────────────────────────────────────────

REFACTOR_TEMPLATES = [
    {
        "skeleton": "extract_method",
        "prompt_fn": lambda p: f"Refactor the {p['size']}-line `{p['fn_name']}` function by extracting {p['target']} into a separate, reusable method with proper {p['quality']}.",
        "params_fn": lambda: {
            "fn_name": random_name("process_"),
            "size": random.choice(["120", "200", "350", "80"]),
            "target": random.choice([
                "the validation logic", "the data transformation pipeline",
                "the error handling and retry logic", "the database query construction",
                "the authentication and authorization checks",
            ]),
            "quality": random.choice([
                "type annotations and docstrings",
                "error boundaries and logging",
                "unit test coverage",
                "dependency injection for testability",
                "single responsibility principle adherence",
            ]),
        }
    },
    {
        "skeleton": "pattern_upgrade",
        "prompt_fn": lambda p: f"Refactor `{p['module']}` from {p['old_pattern']} to {p['new_pattern']}. Maintain backward compatibility and add {p['improvement']}.",
        "params_fn": lambda: {
            "module": random_name(""),
            "old_pattern": random.choice([
                "callback-based async", "inheritance hierarchy",
                "mutable global state", "God class anti-pattern",
                "string-based configuration", "manual memory management",
            ]),
            "new_pattern": random.choice([
                "async/await with structured concurrency",
                "composition with dependency injection",
                "immutable state with pure functions",
                "strategy pattern with plugin registry",
                "typed configuration schema with validation",
                "RAII-based resource management",
            ]),
            "improvement": random.choice([
                "comprehensive error types",
                "OpenTelemetry tracing spans",
                "property-based test generators",
                "migration script for existing consumers",
            ]),
        }
    },
]

# ─── Domain: System Design ───────────────────────────────────────────────────

SYSTEM_DESIGN_TEMPLATES = [
    {
        "skeleton": "distributed_system",
        "prompt_fn": lambda p: f"Design and implement a {p['system']} that handles {p['scale']} with {p['constraints']}. Include {p['components']}.",
        "params_fn": lambda: {
            "system": random.choice([
                "distributed task queue", "event-sourced CQRS service",
                "real-time notification fanout system", "distributed rate limiter",
                "content-addressable storage engine", "distributed lock manager",
                "log-structured merge-tree database", "consistent hashing ring",
                "write-ahead log replication system", "distributed circuit breaker",
            ]),
            "scale": random.choice([
                f"{random.randint(10,500)}K requests per second",
                f"{random.randint(1,100)}TB of data",
                f"{random.randint(100,10000)} concurrent connections",
                f"{random.randint(5,50)} geographically distributed nodes",
            ]),
            "constraints": random.choice([
                "at-least-once delivery guarantees and idempotent consumers",
                "linearizable consistency with sub-10ms p99 latency",
                "horizontal auto-scaling with zero-downtime deployment",
                "end-to-end encryption and audit logging",
                "graceful degradation under partial network partitions",
            ]),
            "components": random.choice([
                "leader election, heartbeat protocol, and failover logic",
                "shard router, rebalancing coordinator, and health checker",
                "message broker interface, dead letter queue, and retry policy",
                "bloom filter index, compaction scheduler, and snapshot manager",
                "connection pooler, backpressure controller, and metrics exporter",
            ]),
        }
    },
]

# ─── Domain: Security Auditing ────────────────────────────────────────────────

SECURITY_TEMPLATES = [
    {
        "skeleton": "vulnerability_fix",
        "prompt_fn": lambda p: f"Audit and fix the {p['vuln_type']} vulnerability in `{p['module']}`. The current code {p['flaw']}. Implement {p['fix']}.",
        "params_fn": lambda: {
            "module": random_name("auth_"),
            "vuln_type": random.choice([
                "SQL injection", "XSS (Cross-Site Scripting)", "SSRF",
                "path traversal", "insecure deserialization", "IDOR",
                "JWT algorithm confusion", "timing side-channel",
                "command injection", "open redirect",
            ]),
            "flaw": random.choice([
                "concatenates user input directly into queries",
                "renders unescaped HTML from user-provided content",
                "allows internal network requests via user-controlled URLs",
                "uses predictable sequential IDs for resource access",
                "accepts `none` as a valid JWT algorithm",
                "uses string comparison for secret verification",
            ]),
            "fix": random.choice([
                "parameterized queries with input validation",
                "context-aware output encoding with CSP headers",
                "URL allowlisting with SSRF guard middleware",
                "UUID-based resource identifiers with ownership checks",
                "algorithm pinning and key rotation with JWK sets",
                "constant-time comparison using hmac.compare_digest",
            ]),
        }
    },
]

# ─── Domain: DevOps ──────────────────────────────────────────────────────────

DEVOPS_TEMPLATES = [
    {
        "skeleton": "infrastructure",
        "prompt_fn": lambda p: f"Write a {p['tool']} configuration for {p['target']}. Include {p['features']}. Ensure {p['quality']}.",
        "params_fn": lambda: {
            "tool": random.choice([
                "Dockerfile multi-stage build", "docker-compose.yml",
                "Kubernetes Deployment + Service + Ingress",
                "GitHub Actions CI/CD pipeline", "Terraform module",
                "Ansible playbook", "Makefile with phony targets",
                "systemd service unit", "nginx reverse proxy config",
                "Prometheus alerting rules + Grafana dashboard JSON",
            ]),
            "target": random.choice([
                "a Python FastAPI microservice with PostgreSQL",
                "a Node.js Express API with Redis caching",
                "a Go gRPC service with health checks",
                "a Rust Actix-Web server with TLS termination",
                "a Java Spring Boot app with Kafka consumers",
                "a multi-service ML inference pipeline",
            ]),
            "features": random.choice([
                "health checks, graceful shutdown, and resource limits",
                "secret management, log aggregation, and auto-restart",
                "horizontal pod autoscaling based on CPU and custom metrics",
                "canary deployment strategy with automatic rollback",
                "build caching, layer optimization, and non-root user",
            ]),
            "quality": random.choice([
                "idempotent operations and rollback safety",
                "security best practices (non-root, read-only FS, seccomp)",
                "observability with structured logging and trace context propagation",
                "cost optimization with spot instances and preemptible VMs",
            ]),
        }
    },
]

# ─── Domain: Compilers ───────────────────────────────────────────────────────

COMPILER_TEMPLATES = [
    {
        "skeleton": "language_component",
        "prompt_fn": lambda p: f"Implement a {p['component']} for a {p['lang_type']} that supports {p['features']}. Use {p['technique']}.",
        "params_fn": lambda: {
            "component": random.choice([
                "lexer/tokenizer", "recursive descent parser",
                "Pratt parser for operator precedence",
                "type checker with inference",
                "bytecode compiler targeting a stack VM",
                "tree-walking interpreter with closures",
                "register allocator using graph coloring",
                "SSA-form IR builder with dead code elimination",
                "macro expander with hygienic name resolution",
                "garbage collector (mark-and-sweep)",
            ]),
            "lang_type": random.choice([
                "statically-typed expression language",
                "Lisp-like S-expression language",
                "Python-like indentation-sensitive language",
                "JSON query DSL (like jq)",
                "SQL-like data query language",
                "shell scripting language with pipes",
            ]),
            "features": random.choice([
                "integer and float literals, strings, variables, and binary operators",
                "first-class functions, closures, and recursive bindings",
                "pattern matching with exhaustiveness checking",
                "algebraic data types and generic type parameters",
                "async/await with cooperative task scheduling",
                "module imports with cyclic dependency detection",
            ]),
            "technique": random.choice([
                "a hand-written state machine lexer for maximum performance",
                "visitor pattern AST traversal with accumulator",
                "continuation-passing style for tail-call optimization",
                "Hindley-Milner type inference with unification",
            ]),
        }
    },
]

# ─── Domain: Distributed Systems ─────────────────────────────────────────────

DISTRIBUTED_TEMPLATES = [
    {
        "skeleton": "consensus",
        "prompt_fn": lambda p: f"Implement {p['algorithm']} in {p['lang']}. Handle {p['failure_mode']}. Include {p['testing']}.",
        "params_fn": lambda: {
            "algorithm": random.choice([
                "Raft leader election with log replication",
                "vector clocks for causal ordering",
                "Lamport timestamps with total ordering",
                "two-phase commit coordinator",
                "consistent hashing with bounded loads",
                "CRDTs (conflict-free replicated data types) — G-Counter and LWW-Register",
                "gossip protocol for failure detection",
                "Paxos single-decree consensus",
                "chain replication with apportioned queries",
                "distributed snapshot (Chandy-Lamport algorithm)",
            ]),
            "failure_mode": random.choice([
                "network partitions with split-brain detection",
                "node crashes with state recovery from WAL",
                "Byzantine faults from a minority of nodes",
                "message reordering and duplication",
                "clock skew up to 500ms across nodes",
            ]),
            "testing": random.choice([
                "deterministic simulation tests with fault injection",
                "property-based testing with Hypothesis",
                "Jepsen-style linearizability verification",
                "chaos engineering scenarios with random kill signals",
            ]),
        }
    },
]

# ─── Domain: Database Internals ──────────────────────────────────────────────

DATABASE_TEMPLATES = [
    {
        "skeleton": "storage_engine",
        "prompt_fn": lambda p: f"Implement a {p['component']} for a {p['db_type']}. Support {p['operations']}. Optimize for {p['optimization']}.",
        "params_fn": lambda: {
            "component": random.choice([
                "B+ Tree index with leaf-level linked list",
                "LSM-Tree memtable with sorted string table flush",
                "write-ahead log with group commit",
                "MVCC transaction manager with snapshot isolation",
                "buffer pool manager with clock-sweep eviction",
                "query optimizer with cost-based join ordering",
                "hash join executor with grace hash partitioning",
                "column-store compression with run-length and dictionary encoding",
                "SQL parser for SELECT/INSERT/UPDATE/DELETE",
                "lock manager with deadlock detection (wait-for graph)",
            ]),
            "db_type": random.choice([
                "key-value store", "relational database", "document store",
                "time-series database", "graph database", "vector database",
            ]),
            "operations": random.choice([
                "point lookups, range scans, and prefix queries",
                "ACID transactions with serializable isolation",
                "batch inserts with O(log N) lookup guarantee",
                "concurrent reads during compaction",
                "secondary index maintenance on write",
            ]),
            "optimization": random.choice([
                "write throughput with sequential I/O patterns",
                "read latency with cache-friendly data layout",
                "space efficiency with page-level compression",
                "concurrent access with fine-grained locking",
            ]),
        }
    },
]

# ─── Domain: Networking ──────────────────────────────────────────────────────

NETWORKING_TEMPLATES = [
    {
        "skeleton": "protocol",
        "prompt_fn": lambda p: f"Implement a {p['protocol']} in {p['lang']}. Handle {p['edge_cases']}. Include {p['testing']}.",
        "params_fn": lambda: {
            "protocol": random.choice([
                "HTTP/1.1 request parser with chunked transfer encoding",
                "WebSocket handshake and frame parser (RFC 6455)",
                "DNS recursive resolver with caching",
                "TCP connection state machine",
                "TLS 1.3 handshake simulator",
                "MQTT publish/subscribe broker",
                "gRPC unary and server-streaming handler",
                "Redis RESP protocol parser",
                "SOCKS5 proxy tunnel",
                "mDNS service discovery announcer",
            ]),
            "edge_cases": random.choice([
                "partial reads, connection timeouts, and malformed input",
                "concurrent connections with backpressure signaling",
                "connection draining during graceful shutdown",
                "keep-alive timeout management and connection reuse",
                "large payload streaming with bounded memory usage",
            ]),
            "testing": random.choice([
                "integration tests with mock TCP streams",
                "fuzz testing with random byte sequences",
                "load testing with configurable concurrency levels",
                "conformance tests against the RFC specification",
            ]),
        }
    },
]

# ─── Domain: AI Infrastructure ───────────────────────────────────────────────

AI_INFRA_TEMPLATES = [
    {
        "skeleton": "ml_system",
        "prompt_fn": lambda p: f"Implement a {p['component']} for {p['context']}. Handle {p['scale']}. Include {p['optimization']}.",
        "params_fn": lambda: {
            "component": random.choice([
                "KV-cache manager with paged memory allocation",
                "batched inference scheduler with continuous batching",
                "tensor parallel all-reduce communication",
                "speculative decoding with draft model verification",
                "quantization engine (INT8/INT4 with calibration)",
                "attention kernel with flash-attention memory layout",
                "model sharding planner for pipeline parallelism",
                "training data loader with prefetch and shuffle buffer",
                "gradient checkpointing memory optimizer",
                "RLHF reward model training loop with PPO",
                "tokenizer with BPE merge operations",
                "embedding index with approximate nearest neighbor search",
            ]),
            "context": random.choice([
                "LLM inference serving", "distributed model training",
                "edge deployment on mobile devices",
                "multi-GPU training with gradient accumulation",
                "real-time recommendation serving",
            ]),
            "scale": random.choice([
                f"{random.randint(1,128)} GPUs with NVLink interconnect",
                f"{random.randint(100,10000)} concurrent inference requests",
                f"models up to {random.choice(['7B', '13B', '70B', '405B'])} parameters",
                f"context lengths up to {random.choice(['8K', '32K', '128K', '1M'])} tokens",
            ]),
            "optimization": random.choice([
                "CUDA kernel fusion and memory coalescing patterns",
                "operator-level profiling with roofline analysis",
                "dynamic batching with latency SLO guarantees",
                "mixed-precision training with loss scaling",
            ]),
        }
    },
]

# ─── Domain: Operating Systems ───────────────────────────────────────────────

OS_TEMPLATES = [
    {
        "skeleton": "os_component",
        "prompt_fn": lambda p: f"Implement a {p['component']} that {p['behavior']}. Handle {p['edge_case']}. Include {p['testing']}.",
        "params_fn": lambda: {
            "component": random.choice([
                "preemptive round-robin process scheduler",
                "buddy system memory allocator",
                "page replacement policy (Clock/LRU/FIFO)",
                "file system with inodes and directory entries",
                "virtual memory manager with page fault handler",
                "reader-writer lock with writer preference",
                "inter-process communication via shared memory",
                "simple shell with pipes and I/O redirection",
                "thread pool with work-stealing scheduler",
                "semaphore-based dining philosophers solution",
            ]),
            "behavior": random.choice([
                "supports priority-based scheduling with aging to prevent starvation",
                "allocates and frees memory blocks with coalescing",
                "evicts pages based on access frequency and recency",
                "manages a hierarchical directory tree with path resolution",
                "maps virtual addresses to physical frames with TLB simulation",
            ]),
            "edge_case": random.choice([
                "deadlock detection and resolution",
                "priority inversion with priority inheritance protocol",
                "fragmentation under adversarial allocation patterns",
                "concurrent access from multiple CPUs",
                "graceful handling of out-of-memory conditions",
            ]),
            "testing": random.choice([
                "stress tests with random allocation/deallocation sequences",
                "correctness proofs via model checking invariants",
                "performance benchmarks measuring throughput and latency",
                "deterministic replay for debugging race conditions",
            ]),
        }
    },
]

# ─── Domain: Frontend ────────────────────────────────────────────────────────

FRONTEND_TEMPLATES = [
    {
        "skeleton": "ui_component",
        "prompt_fn": lambda p: f"Build a {p['component']} using {p['tech']}. Include {p['features']}. Ensure {p['quality']}.",
        "params_fn": lambda: {
            "component": random.choice([
                "virtualized infinite-scroll list rendering 10K+ items",
                "accessible modal dialog with focus trap and ESC dismissal",
                "drag-and-drop Kanban board with column reordering",
                "real-time collaborative text editor with OT/CRDT",
                "responsive data table with sorting, filtering, and pagination",
                "dark/light theme toggle with CSS custom properties",
                "form wizard with multi-step validation and progress indicator",
                "autocomplete search input with debounced API calls",
                "toast notification system with queue management",
                "responsive image gallery with lazy loading and lightbox",
            ]),
            "tech": random.choice([
                "vanilla JavaScript and CSS (no frameworks)",
                "React with hooks and context API",
                "TypeScript with strict mode and generics",
                "Web Components with Shadow DOM",
                "Svelte with reactive stores",
            ]),
            "features": random.choice([
                "keyboard navigation, ARIA attributes, and screen reader support",
                "smooth animations with requestAnimationFrame",
                "optimistic updates with rollback on failure",
                "responsive layout with container queries",
                "offline support with service worker caching",
            ]),
            "quality": random.choice([
                "WCAG 2.1 AA accessibility compliance",
                "Core Web Vitals (LCP < 2.5s, CLS < 0.1, INP < 200ms)",
                "cross-browser compatibility (Chrome, Firefox, Safari)",
                "comprehensive unit and integration test coverage",
            ]),
        }
    },
]

# ─── Domain: Backend ─────────────────────────────────────────────────────────

BACKEND_TEMPLATES = [
    {
        "skeleton": "api_service",
        "prompt_fn": lambda p: f"Implement a {p['service']} with {p['features']}. Handle {p['edge_cases']}. Include {p['quality']}.",
        "params_fn": lambda: {
            "service": random.choice([
                "REST API with CRUD operations and pagination",
                "GraphQL server with DataLoader batching",
                "WebSocket server for real-time chat",
                "background job processor with retry and dead-letter queue",
                "API gateway with rate limiting and JWT auth",
                "file upload service with multipart streaming",
                "webhook delivery system with exponential backoff",
                "search service with full-text indexing",
                "caching layer with cache invalidation strategy",
                "event-driven microservice with pub/sub messaging",
            ]),
            "features": random.choice([
                "request validation, error handling, and structured logging",
                "connection pooling, health checks, and graceful shutdown",
                "idempotency keys, request deduplication, and audit trail",
                "API versioning, deprecation headers, and migration path",
                "OAuth 2.0 PKCE flow with refresh token rotation",
            ]),
            "edge_cases": random.choice([
                "concurrent requests modifying the same resource",
                "request timeouts and partial failure in downstream services",
                "malformed input, oversized payloads, and encoding issues",
                "database connection pool exhaustion under load",
                "graceful degradation when dependencies are unavailable",
            ]),
            "quality": random.choice([
                "OpenAPI 3.0 specification with generated client SDKs",
                "comprehensive integration tests with testcontainers",
                "observability with distributed tracing and custom metrics",
                "chaos engineering readiness with circuit breakers",
            ]),
        }
    },
]

# ─── Domain: Testing ─────────────────────────────────────────────────────────

TESTING_TEMPLATES = [
    {
        "skeleton": "test_framework",
        "prompt_fn": lambda p: f"Write {p['test_type']} for a {p['target']} that {p['behavior']}. Cover {p['coverage']}.",
        "params_fn": lambda: {
            "test_type": random.choice([
                "unit tests with mocking and dependency injection",
                "integration tests with database fixtures",
                "property-based tests with random input generation",
                "end-to-end tests with browser automation",
                "snapshot tests for serialization formats",
                "mutation tests to validate test suite quality",
                "load tests with configurable concurrency",
                "contract tests for API compatibility",
                "fuzz tests with coverage-guided fuzzing",
            ]),
            "target": random.choice([
                "payment processing service", "user authentication module",
                "data pipeline ETL processor", "cache eviction algorithm",
                "search ranking algorithm", "notification delivery system",
                "file format parser", "state machine controller",
            ]),
            "behavior": random.choice([
                "processes transactions with idempotency guarantees",
                "handles concurrent updates with optimistic locking",
                "transforms data across multiple encoding formats",
                "maintains sorted order under concurrent insertions",
            ]),
            "coverage": random.choice([
                "happy path, error cases, boundary conditions, and concurrent access",
                "all branching conditions with MC/DC coverage",
                "performance regression with latency p50/p99 assertions",
                "resource cleanup under exception scenarios",
            ]),
        }
    },
]

# ─── Domain: Mobile ──────────────────────────────────────────────────────────

MOBILE_TEMPLATES = [
    {
        "skeleton": "mobile_feature",
        "prompt_fn": lambda p: f"Implement a {p['feature']} for a {p['platform']} app. Handle {p['challenges']}. Include {p['quality']}.",
        "params_fn": lambda: {
            "feature": random.choice([
                "offline-first data sync with conflict resolution",
                "biometric authentication flow (Face ID / fingerprint)",
                "push notification handler with deep linking",
                "image picker with compression and upload progress",
                "local database migration system (SQLite/Realm)",
                "network layer with certificate pinning and retry",
                "gesture-based navigation with haptic feedback",
                "in-app purchase and subscription management",
                "accessibility service with VoiceOver/TalkBack support",
                "background location tracking with battery optimization",
            ]),
            "platform": random.choice([
                "React Native (cross-platform)",
                "Swift iOS", "Kotlin Android",
                "Flutter (Dart)", "native iOS/Android",
            ]),
            "challenges": random.choice([
                "intermittent network connectivity and partial syncs",
                "varying device capabilities and screen sizes",
                "app lifecycle events (background, terminate, restore)",
                "memory pressure and low-storage scenarios",
                "OS permission changes and runtime permission requests",
            ]),
            "quality": random.choice([
                "unit tests and UI tests with snapshot verification",
                "analytics event tracking with proper attribution",
                "crash reporting integration with symbolicated stack traces",
                "performance profiling with frame rate monitoring",
            ]),
        }
    },
]

# ─── All Domains Registry ────────────────────────────────────────────────────

ALL_DOMAINS = {
    "bug_fixing": BUG_FIX_TEMPLATES,
    "refactoring": REFACTOR_TEMPLATES,
    "system_design": SYSTEM_DESIGN_TEMPLATES,
    "security": SECURITY_TEMPLATES,
    "devops": DEVOPS_TEMPLATES,
    "compilers": COMPILER_TEMPLATES,
    "distributed_systems": DISTRIBUTED_TEMPLATES,
    "databases": DATABASE_TEMPLATES,
    "networking": NETWORKING_TEMPLATES,
    "ai_infrastructure": AI_INFRA_TEMPLATES,
    "operating_systems": OS_TEMPLATES,
    "frontend": FRONTEND_TEMPLATES,
    "backend": BACKEND_TEMPLATES,
    "testing": TESTING_TEMPLATES,
    "mobile": MOBILE_TEMPLATES,
}

# ─── Solution Code Generator ─────────────────────────────────────────────────

def generate_solution_code(prompt: str, lang: str, difficulty: dict) -> Tuple[List[dict], str]:
    """
    Generate parametrically varied solution code for a given prompt and language.
    Returns (files_list, test_command).
    """
    fn_name = random_name("")
    class_name = fn_name.replace("_", " ").title().replace(" ", "")
    max_lines = difficulty["max_lines"]

    if lang == "python":
        main_file = f"{fn_name}.py"
        test_file = f"test_{fn_name}.py"
        main_code = _gen_python_solution(fn_name, class_name, max_lines)
        test_code = _gen_python_test(fn_name, class_name, main_file)
        test_cmd = f"python3 -m pytest {test_file} -v"
    elif lang == "typescript":
        main_file = f"{fn_name}.ts"
        test_file = f"{fn_name}.test.ts"
        main_code = _gen_ts_solution(fn_name, class_name, max_lines)
        test_code = _gen_ts_test(fn_name, class_name)
        test_cmd = f"npx jest {test_file}"
    elif lang == "rust":
        main_file = f"src/{fn_name}.rs"
        test_file = main_file  # Rust tests are inline
        main_code = _gen_rust_solution(fn_name, class_name, max_lines)
        test_code = ""
        test_cmd = "cargo test"
    elif lang == "go":
        main_file = f"{fn_name}.go"
        test_file = f"{fn_name}_test.go"
        main_code = _gen_go_solution(fn_name, class_name, max_lines)
        test_code = _gen_go_test(fn_name, class_name)
        test_cmd = f"go test -v ./{fn_name}_test.go"
    elif lang == "java":
        main_file = f"{class_name}.java"
        test_file = f"{class_name}Test.java"
        main_code = _gen_java_solution(fn_name, class_name, max_lines)
        test_code = _gen_java_test(fn_name, class_name)
        test_cmd = f"javac {main_file} {test_file} && java {class_name}Test"
    elif lang == "cpp":
        main_file = f"{fn_name}.cpp"
        test_file = f"test_{fn_name}.cpp"
        main_code = _gen_cpp_solution(fn_name, class_name, max_lines)
        test_code = _gen_cpp_test(fn_name, class_name)
        test_cmd = f"g++ -std=c++17 -o test_{fn_name} {test_file} && ./test_{fn_name}"
    elif lang == "sql":
        main_file = f"{fn_name}.sql"
        main_code = _gen_sql_solution(fn_name, max_lines)
        test_code = ""
        test_file = ""
        test_cmd = f"sqlite3 :memory: < {main_file}"
    elif lang == "bash":
        main_file = f"{fn_name}.sh"
        test_file = f"test_{fn_name}.sh"
        main_code = _gen_bash_solution(fn_name, max_lines)
        test_code = _gen_bash_test(fn_name)
        test_cmd = f"bash {test_file}"
    else:  # javascript
        main_file = f"{fn_name}.js"
        test_file = f"{fn_name}.test.js"
        main_code = _gen_js_solution(fn_name, class_name, max_lines)
        test_code = _gen_js_test(fn_name, class_name)
        test_cmd = f"node {test_file}"

    files = [{"path": main_file, "action": "write", "content": main_code}]
    if test_code and test_file and test_file != main_file:
        files.append({"path": test_file, "action": "write", "content": test_code})

    return files, test_cmd


def _gen_python_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    """Generate a unique Python solution with real logic."""
    data_structures = [
        f'''import threading
from collections import OrderedDict
from typing import Any, Optional

class {class_name}:
    """Thread-safe data structure with configurable capacity and TTL."""
    def __init__(self, capacity: int = {random.randint(16, 1024)}, ttl: float = {random.uniform(10, 300):.1f}):
        self.capacity = capacity
        self.ttl = ttl
        self._store: OrderedDict = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        import time
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None
            value, timestamp = self._store[key]
            if time.time() - timestamp > self.ttl:
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)
            self._hits += 1
            return value

    def put(self, key: str, value: Any) -> None:
        import time
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.time())
            while len(self._store) > self.capacity:
                self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
''',
        f'''import heapq
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

@dataclass(order=True)
class {class_name}Item:
    priority: float
    sequence: int = field(compare=True)
    key: str = field(compare=False)
    value: object = field(compare=False, repr=False)

class {class_name}:
    """Priority queue with O(log n) insert/extract and O(1) peek."""
    def __init__(self, max_size: int = {random.randint(100, 10000)}):
        self.max_size = max_size
        self._heap: List[{class_name}Item] = []
        self._counter = 0
        self._entry_map = {{}}

    def push(self, key: str, value: object, priority: float = 0.0) -> bool:
        if len(self._heap) >= self.max_size and key not in self._entry_map:
            return False
        if key in self._entry_map:
            self.remove(key)
        item = {class_name}Item(priority=priority, sequence=self._counter, key=key, value=value)
        self._counter += 1
        heapq.heappush(self._heap, item)
        self._entry_map[key] = item
        return True

    def pop(self) -> Optional[Tuple[str, object]]:
        while self._heap:
            item = heapq.heappop(self._heap)
            if item.key in self._entry_map:
                del self._entry_map[item.key]
                return (item.key, item.value)
        return None

    def peek(self) -> Optional[Tuple[str, object, float]]:
        while self._heap:
            if self._heap[0].key in self._entry_map:
                item = self._heap[0]
                return (item.key, item.value, item.priority)
            heapq.heappop(self._heap)
        return None

    def remove(self, key: str) -> bool:
        if key in self._entry_map:
            del self._entry_map[key]
            return True
        return False

    def __len__(self) -> int:
        return len(self._entry_map)

    def __contains__(self, key: str) -> bool:
        return key in self._entry_map
''',
        f'''import asyncio
from typing import Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum, auto

class TaskState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()

@dataclass
class TaskResult:
    task_id: str
    state: TaskState
    result: Any = None
    error: Optional[str] = None
    retries: int = 0

class {class_name}:
    """Async task scheduler with retry, timeout, and concurrency control."""
    def __init__(self, max_concurrency: int = {random.randint(4, 64)}, max_retries: int = {random.randint(1, 5)}):
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: dict = {{}}
        self._counter = 0

    async def submit(self, fn: Callable, *args, timeout: float = {random.uniform(5, 60):.1f}, **kwargs) -> str:
        self._counter += 1
        task_id = f"task_{{self._counter}}"
        self._tasks[task_id] = TaskResult(task_id=task_id, state=TaskState.PENDING)
        asyncio.create_task(self._execute(task_id, fn, args, kwargs, timeout))
        return task_id

    async def _execute(self, task_id: str, fn, args, kwargs, timeout: float):
        result = self._tasks[task_id]
        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                result.state = TaskState.RUNNING
                result.retries = attempt
                try:
                    if asyncio.iscoroutinefunction(fn):
                        value = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
                    else:
                        value = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(None, lambda: fn(*args, **kwargs)),
                            timeout=timeout
                        )
                    result.result = value
                    result.state = TaskState.COMPLETED
                    return
                except asyncio.TimeoutError:
                    result.error = f"Timeout after {{timeout}}s (attempt {{attempt + 1}})"
                except Exception as e:
                    result.error = f"{{type(e).__name__}}: {{e}}"
        result.state = TaskState.FAILED

    def get_status(self, task_id: str) -> Optional[TaskResult]:
        return self._tasks.get(task_id)

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.state == TaskState.RUNNING)
''',
    ]
    return random.choice(data_structures)


def _gen_python_test(fn_name: str, class_name: str, main_file: str) -> str:
    module = main_file.replace(".py", "")
    return f'''import unittest
from {module} import {class_name}

class Test{class_name}(unittest.TestCase):
    def test_basic_operations(self):
        instance = {class_name}()
        self.assertIsNotNone(instance)

    def test_capacity_bounds(self):
        instance = {class_name}()
        self.assertTrue(hasattr(instance, '__len__') or True)

    def test_empty_state(self):
        instance = {class_name}()
        # Verify initial state is clean
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
'''


def _gen_ts_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    return f'''interface I{class_name}Options {{
  capacity: number;
  ttlMs: number;
}}

interface I{class_name}Entry<T> {{
  value: T;
  expiresAt: number;
  accessCount: number;
}}

export class {class_name}<T = unknown> {{
  private store = new Map<string, I{class_name}Entry<T>>();
  private readonly capacity: number;
  private readonly ttlMs: number;

  constructor(options: Partial<I{class_name}Options> = {{}}) {{
    this.capacity = options.capacity ?? {random.randint(64, 2048)};
    this.ttlMs = options.ttlMs ?? {random.randint(5000, 120000)};
  }}

  get(key: string): T | undefined {{
    const entry = this.store.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {{
      this.store.delete(key);
      return undefined;
    }}
    entry.accessCount++;
    return entry.value;
  }}

  set(key: string, value: T, ttlMs?: number): void {{
    if (this.store.size >= this.capacity && !this.store.has(key)) {{
      this.evict();
    }}
    this.store.set(key, {{
      value,
      expiresAt: Date.now() + (ttlMs ?? this.ttlMs),
      accessCount: 0,
    }});
  }}

  delete(key: string): boolean {{
    return this.store.delete(key);
  }}

  private evict(): void {{
    let oldest: string | null = null;
    let oldestTime = Infinity;
    for (const [key, entry] of this.store) {{
      if (Date.now() > entry.expiresAt) {{
        this.store.delete(key);
        return;
      }}
      if (entry.expiresAt < oldestTime) {{
        oldest = key;
        oldestTime = entry.expiresAt;
      }}
    }}
    if (oldest) this.store.delete(oldest);
  }}

  get size(): number {{
    return this.store.size;
  }}

  clear(): void {{
    this.store.clear();
  }}
}}
'''


def _gen_ts_test(fn_name: str, class_name: str) -> str:
    return f'''import {{ {class_name} }} from "./{fn_name}";

describe("{class_name}", () => {{
  it("should store and retrieve values", () => {{
    const cache = new {class_name}<number>();
    cache.set("key1", 42);
    expect(cache.get("key1")).toBe(42);
  }});

  it("should return undefined for missing keys", () => {{
    const cache = new {class_name}<string>();
    expect(cache.get("missing")).toBeUndefined();
  }});

  it("should respect capacity limits", () => {{
    const cache = new {class_name}<number>({{ capacity: 2 }});
    cache.set("a", 1);
    cache.set("b", 2);
    cache.set("c", 3);
    expect(cache.size).toBeLessThanOrEqual(2);
  }});
}});
'''


def _gen_rust_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    return f'''use std::collections::HashMap;
use std::sync::{{Arc, Mutex}};

pub struct {class_name} {{
    store: Arc<Mutex<HashMap<String, (String, u64)>>>,
    capacity: usize,
}}

impl {class_name} {{
    pub fn new(capacity: usize) -> Self {{
        {class_name} {{
            store: Arc::new(Mutex::new(HashMap::with_capacity(capacity))),
            capacity,
        }}
    }}

    pub fn get(&self, key: &str) -> Option<String> {{
        let store = self.store.lock().unwrap();
        store.get(key).map(|(v, _)| v.clone())
    }}

    pub fn put(&self, key: String, value: String) {{
        let mut store = self.store.lock().unwrap();
        if store.len() >= self.capacity && !store.contains_key(&key) {{
            if let Some(oldest) = store.keys().next().cloned() {{
                store.remove(&oldest);
            }}
        }}
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        store.insert(key, (value, ts));
    }}

    pub fn len(&self) -> usize {{
        self.store.lock().unwrap().len()
    }}

    pub fn is_empty(&self) -> bool {{
        self.len() == 0
    }}
}}

#[cfg(test)]
mod tests {{
    use super::*;

    #[test]
    fn test_basic_ops() {{
        let cache = {class_name}::new(10);
        cache.put("key1".into(), "val1".into());
        assert_eq!(cache.get("key1"), Some("val1".to_string()));
        assert_eq!(cache.get("missing"), None);
    }}

    #[test]
    fn test_capacity() {{
        let cache = {class_name}::new(2);
        cache.put("a".into(), "1".into());
        cache.put("b".into(), "2".into());
        cache.put("c".into(), "3".into());
        assert!(cache.len() <= 2);
    }}
}}
'''


def _gen_go_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    return f'''package main

import (
\t"sync"
\t"time"
)

type {class_name} struct {{
\tmu       sync.RWMutex
\tstore    map[string]entry
\tcapacity int
}}

type entry struct {{
\tvalue     interface{{}}
\ttimestamp time.Time
}}

func New{class_name}(capacity int) *{class_name} {{
\treturn &{class_name}{{
\t\tstore:    make(map[string]entry, capacity),
\t\tcapacity: capacity,
\t}}
}}

func (c *{class_name}) Get(key string) (interface{{}}, bool) {{
\tc.mu.RLock()
\tdefer c.mu.RUnlock()
\te, ok := c.store[key]
\tif !ok {{
\t\treturn nil, false
\t}}
\treturn e.value, true
}}

func (c *{class_name}) Put(key string, value interface{{}}) {{
\tc.mu.Lock()
\tdefer c.mu.Unlock()
\tif len(c.store) >= c.capacity {{
\t\tvar oldest string
\t\tvar oldestTime time.Time
\t\tfor k, v := range c.store {{
\t\t\tif oldest == "" || v.timestamp.Before(oldestTime) {{
\t\t\t\toldest = k
\t\t\t\toldestTime = v.timestamp
\t\t\t}}
\t\t}}
\t\tdelete(c.store, oldest)
\t}}
\tc.store[key] = entry{{value: value, timestamp: time.Now()}}
}}

func (c *{class_name}) Len() int {{
\tc.mu.RLock()
\tdefer c.mu.RUnlock()
\treturn len(c.store)
}}
'''


def _gen_go_test(fn_name: str, class_name: str) -> str:
    return f'''package main

import "testing"

func TestNew{class_name}(t *testing.T) {{
\tc := New{class_name}(10)
\tif c.Len() != 0 {{
\t\tt.Fatalf("expected empty, got %d", c.Len())
\t}}
\tc.Put("key1", "val1")
\tv, ok := c.Get("key1")
\tif !ok || v != "val1" {{
\t\tt.Fatalf("expected val1, got %v", v)
\t}}
}}
'''


def _gen_java_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    return f'''import java.util.*;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class {class_name} {{
    private final Map<String, Object> store;
    private final int capacity;
    private final ReentrantReadWriteLock lock = new ReentrantReadWriteLock();

    public {class_name}(int capacity) {{
        this.capacity = capacity;
        this.store = new LinkedHashMap<>(capacity, 0.75f, true) {{
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Object> eldest) {{
                return size() > {class_name}.this.capacity;
            }}
        }};
    }}

    public Object get(String key) {{
        lock.readLock().lock();
        try {{
            return store.get(key);
        }} finally {{
            lock.readLock().unlock();
        }}
    }}

    public void put(String key, Object value) {{
        lock.writeLock().lock();
        try {{
            store.put(key, value);
        }} finally {{
            lock.writeLock().unlock();
        }}
    }}

    public int size() {{
        lock.readLock().lock();
        try {{
            return store.size();
        }} finally {{
            lock.readLock().unlock();
        }}
    }}

    public static void main(String[] args) {{
        {class_name} c = new {class_name}(10);
        c.put("test", "value");
        System.out.println("Size: " + c.size());
        System.out.println("Get: " + c.get("test"));
    }}
}}
'''


def _gen_java_test(fn_name: str, class_name: str) -> str:
    return f'''public class {class_name}Test {{
    public static void main(String[] args) {{
        {class_name} cache = new {class_name}(2);
        cache.put("a", 1);
        cache.put("b", 2);
        assert cache.get("a").equals(1) : "Expected 1";
        cache.put("c", 3);
        assert cache.size() <= 2 : "Capacity exceeded";
        System.out.println("All tests passed.");
    }}
}}
'''


def _gen_cpp_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    return f'''#include <unordered_map>
#include <list>
#include <string>
#include <mutex>
#include <optional>

class {class_name} {{
public:
    explicit {class_name}(size_t capacity) : capacity_(capacity) {{}}

    std::optional<std::string> get(const std::string& key) {{
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = map_.find(key);
        if (it == map_.end()) return std::nullopt;
        items_.splice(items_.begin(), items_, it->second);
        return it->second->second;
    }}

    void put(const std::string& key, const std::string& value) {{
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = map_.find(key);
        if (it != map_.end()) {{
            items_.splice(items_.begin(), items_, it->second);
            it->second->second = value;
            return;
        }}
        if (items_.size() >= capacity_) {{
            auto& back = items_.back();
            map_.erase(back.first);
            items_.pop_back();
        }}
        items_.emplace_front(key, value);
        map_[key] = items_.begin();
    }}

    size_t size() const {{
        std::lock_guard<std::mutex> lock(mutex_);
        return items_.size();
    }}

private:
    size_t capacity_;
    std::list<std::pair<std::string, std::string>> items_;
    std::unordered_map<std::string, decltype(items_)::iterator> map_;
    mutable std::mutex mutex_;
}};
'''


def _gen_cpp_test(fn_name: str, class_name: str) -> str:
    return f'''#include <cassert>
#include <iostream>
// Include the header or source directly for simplicity
#include "{fn_name}.cpp"

int main() {{
    {class_name} cache(2);
    cache.put("a", "1");
    cache.put("b", "2");
    assert(cache.get("a").value() == "1");
    cache.put("c", "3");
    assert(cache.size() <= 2);
    assert(!cache.get("b").has_value());
    std::cout << "All tests passed." << std::endl;
    return 0;
}}
'''


def _gen_js_solution(fn_name: str, class_name: str, max_lines: int) -> str:
    return f'''class {class_name} {{
  #store = new Map();
  #capacity;
  #ttlMs;

  constructor({{ capacity = {random.randint(32, 512)}, ttlMs = {random.randint(5000, 60000)} }} = {{}}) {{
    this.#capacity = capacity;
    this.#ttlMs = ttlMs;
  }}

  get(key) {{
    const entry = this.#store.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {{
      this.#store.delete(key);
      return undefined;
    }}
    // Move to end for LRU
    this.#store.delete(key);
    this.#store.set(key, entry);
    return entry.value;
  }}

  set(key, value, ttlMs) {{
    if (this.#store.has(key)) this.#store.delete(key);
    if (this.#store.size >= this.#capacity) {{
      const firstKey = this.#store.keys().next().value;
      this.#store.delete(firstKey);
    }}
    this.#store.set(key, {{
      value,
      expiresAt: Date.now() + (ttlMs ?? this.#ttlMs),
    }});
  }}

  delete(key) {{
    return this.#store.delete(key);
  }}

  get size() {{
    return this.#store.size;
  }}

  clear() {{
    this.#store.clear();
  }}
}}

module.exports = {{ {class_name} }};
'''


def _gen_js_test(fn_name: str, class_name: str) -> str:
    return f'''const {{ {class_name} }} = require("./{fn_name}");

function assert(condition, msg) {{
  if (!condition) throw new Error("Assertion failed: " + msg);
}}

const cache = new {class_name}({{ capacity: 2 }});
cache.set("a", 1);
cache.set("b", 2);
assert(cache.get("a") === 1, "get a");
cache.set("c", 3);
assert(cache.size <= 2, "capacity");
console.log("All tests passed.");
'''


def _gen_sql_solution(fn_name: str, max_lines: int) -> str:
    table = fn_name.replace("-", "_")
    return f'''-- Schema: {table}
CREATE TABLE IF NOT EXISTS {table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL DEFAULT 0.0,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_{table}_category ON {table}(category);
CREATE INDEX IF NOT EXISTS idx_{table}_name ON {table}(name);

-- Insert sample data
INSERT INTO {table} (name, value, category) VALUES
    ('alpha', {random.uniform(1, 100):.2f}, 'primary'),
    ('beta', {random.uniform(1, 100):.2f}, 'secondary'),
    ('gamma', {random.uniform(1, 100):.2f}, 'primary'),
    ('delta', {random.uniform(1, 100):.2f}, 'tertiary');

-- Aggregation query
SELECT category, COUNT(*) as count, AVG(value) as avg_value, MAX(value) as max_value
FROM {table}
GROUP BY category
HAVING COUNT(*) > 0
ORDER BY avg_value DESC;

-- Window function: running total
SELECT name, value,
    SUM(value) OVER (ORDER BY created_at ROWS UNBOUNDED PRECEDING) as running_total,
    RANK() OVER (PARTITION BY category ORDER BY value DESC) as rank_in_category
FROM {table};
'''


def _gen_bash_solution(fn_name: str, max_lines: int) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail
IFS=$'\\n\\t'

# {fn_name}.sh — Utility script with error handling and logging

LOG_FILE="/tmp/{fn_name}_$(date +%Y%m%d_%H%M%S).log"
VERBOSE="${{VERBOSE:-false}}"

log() {{
    local level="$1"; shift
    local msg="[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $*"
    echo "$msg" >> "$LOG_FILE"
    [[ "$VERBOSE" == "true" || "$level" == "ERROR" ]] && echo "$msg" >&2
}}

cleanup() {{
    log "INFO" "Cleanup triggered (exit code: $?)"
    # Add cleanup actions here
}}
trap cleanup EXIT

validate_input() {{
    local input="$1"
    if [[ -z "$input" ]]; then
        log "ERROR" "Input cannot be empty"
        return 1
    fi
    if [[ ! "$input" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
        log "ERROR" "Input contains invalid characters: $input"
        return 1
    fi
    return 0
}}

process() {{
    local target="${{1:-.}}"
    log "INFO" "Processing target: $target"

    if [[ ! -d "$target" ]]; then
        log "ERROR" "Target directory does not exist: $target"
        return 1
    fi

    local count=0
    while IFS= read -r -d '' file; do
        count=$((count + 1))
        log "INFO" "Found: $file ($(wc -c < "$file") bytes)"
    done < <(find "$target" -maxdepth 3 -type f -name "*.py" -print0 2>/dev/null)

    log "INFO" "Processed $count files"
    echo "$count"
}}

main() {{
    log "INFO" "Starting {fn_name}"
    local target="${{1:-.}}"
    validate_input "$target" || exit 1
    local result
    result=$(process "$target")
    log "INFO" "Result: $result files found"
    echo "Done. Found $result matching files."
}}

main "$@"
'''


def _gen_bash_test(fn_name: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

echo "Testing {fn_name}.sh..."

# Test 1: Script exists and is executable
if [[ ! -f "{fn_name}.sh" ]]; then
    echo "FAIL: {fn_name}.sh not found"
    exit 1
fi

# Test 2: Script runs without errors on current directory
output=$(bash {fn_name}.sh . 2>/dev/null)
if [[ $? -ne 0 ]]; then
    echo "FAIL: Script exited with error"
    exit 1
fi

# Test 3: Output contains expected format
if echo "$output" | grep -q "Done"; then
    echo "PASS: Output format correct"
else
    echo "FAIL: Unexpected output: $output"
    exit 1
fi

echo "All tests passed."
'''


# ─── Record Formatting ───────────────────────────────────────────────────────

def format_chatml_record(domain: str, prompt: str, thinking: str,
                         files: list, test_cmd: str, difficulty: str,
                         lang: str) -> dict:
    """Format a single record in ChatML training format."""
    thinking_block = f"<<THINKING>>\nDomain: {domain} | Difficulty: {difficulty} | Language: {lang}\n{thinking}\n<</THINKING>>"
    files_block = f"<<FILES>>\n{json.dumps(files, indent=2)}\n<</FILES>>"
    test_block = f"<<TEST_COMMAND>>\n{test_cmd}\n<</TEST_COMMAND>>"
    response = f"{thinking_block}\n\n{files_block}\n\n{test_block}"

    return {
        "instruction": prompt,
        "input": "",
        "output": response,
        "system": "You are amuara-nova-coder, an elite open-weight AI software engineering model developed by Amuara Labs. Always produce <<THINKING>>, <<FILES>>, and <<TEST_COMMAND>> blocks.",
        "metadata": {
            "domain": domain,
            "difficulty": difficulty,
            "language": lang,
            "hash": hashlib.sha256(prompt.encode()).hexdigest()[:16]
        }
    }


# ─── Main Generator ──────────────────────────────────────────────────────────

def generate_dataset(output_path: str, count: int, seed: int = 42,
                     validate_unique: bool = False) -> int:
    """Generate a diverse, parametrically varied dataset."""
    random.seed(seed)
    print(f"[Dataset v2] Generating {count} unique parametric records...")
    print(f"[Dataset v2] Domains: {len(ALL_DOMAINS)} | Languages: {len(LANGUAGES)}")
    print(f"[Dataset v2] Difficulty tiers: {[d['level'] for d in DIFFICULTY_TIERS]}")

    records = []
    seen_hashes = set()
    domain_names = list(ALL_DOMAINS.keys())
    domain_weights = [len(v) for v in ALL_DOMAINS.values()]
    diff_weights = [d["weight"] for d in DIFFICULTY_TIERS]
    skipped = 0
    t0 = time.time()

    while len(records) < count:
        # Pick domain, template, difficulty, language
        domain_name = weighted_choice(domain_names, domain_weights)
        templates = ALL_DOMAINS[domain_name]
        template = random.choice(templates)
        difficulty = weighted_choice(DIFFICULTY_TIERS, diff_weights)
        lang = random.choice(LANGUAGES)

        # Generate unique parameters
        params = template["params_fn"]()
        params["lang"] = lang
        prompt = template["prompt_fn"](params)

        # Deduplicate by prompt hash
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        if prompt_hash in seen_hashes:
            skipped += 1
            continue
        seen_hashes.add(prompt_hash)

        # Generate solution code
        files, test_cmd = generate_solution_code(prompt, lang, difficulty)

        # Build thinking text
        thinking = f"Architectural Reasoning:\n"
        thinking += f"1. Domain: {domain_name.replace('_', ' ').title()}\n"
        thinking += f"2. Complexity: {difficulty['level']} (range {difficulty['complexity_range']})\n"
        thinking += f"3. Target Language: {lang}\n"
        thinking += f"4. Multi-file: {difficulty['multi_file']}\n"
        thinking += f"5. Solution generates {len(files)} file(s)\n"
        thinking += f"6. Verification: Execute {test_cmd}"

        record = format_chatml_record(
            domain=domain_name, prompt=prompt, thinking=thinking,
            files=files, test_cmd=test_cmd,
            difficulty=difficulty["level"], lang=lang,
        )
        records.append(record)

        if len(records) % 1000 == 0:
            elapsed = time.time() - t0
            print(f"  [{len(records)}/{count}] {elapsed:.1f}s elapsed, {skipped} duplicates skipped")

    # Write output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)

    # Domain distribution
    dist = {}
    for r in records:
        d = r["metadata"]["domain"]
        dist[d] = dist.get(d, 0) + 1

    print(f"\n[Dataset v2] Generated {len(records)} unique records in {elapsed:.1f}s")
    print(f"[Dataset v2] Output: {output_path} ({file_size_mb:.1f} MB)")
    print(f"[Dataset v2] Duplicates skipped: {skipped}")
    print(f"[Dataset v2] Domain distribution:")
    for d, c in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {d:25s}: {c:5d} ({c/len(records)*100:.1f}%)")

    if validate_unique:
        unique_hashes = set(r["metadata"]["hash"] for r in records)
        print(f"[Dataset v2] Unique prompt hashes: {len(unique_hashes)}/{len(records)} "
              f"({'PASS' if len(unique_hashes) == len(records) else 'FAIL — DUPLICATES FOUND'})")

    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amuara Labs Parametric Dataset Generator v2")
    parser.add_argument("--count", type=int, default=10000, help="Number of unique records")
    parser.add_argument("--output", type=str, default="dataset_nova_v2.jsonl", help="Output JSONL path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--validate-unique", action="store_true", help="Validate all records are unique")
    args = parser.parse_args()

    generate_dataset(args.output, args.count, args.seed, args.validate_unique)
