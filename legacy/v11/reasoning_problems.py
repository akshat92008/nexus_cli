#!/usr/bin/env python3
"""
reasoning_problems.py — Curated Problem Bank for Nova 1.5B Reasoning Distillation

Generates 1,000+ unique, diverse, and genuinely hard software engineering problems
designed to elicit deep chain-of-thought reasoning from a frontier model.

Three sources:
  1. 100 hand-crafted "killer" problems requiring multi-step reasoning
  2. 800+ parametrically generated problems from 15 engineering domains
  3. 50+ multi-language variants (same problem in Python, Rust, Go)

Usage:
  python reasoning_problems.py                    # Print stats
  python reasoning_problems.py --export problems.json  # Export all problems
"""

import json
import random
import hashlib
import argparse
from typing import List, Dict

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Hand-Crafted "Killer" Problems (100)
# These require genuine multi-step reasoning, architecture debates, and
# edge-case anticipation. A frontier model MUST think deeply to solve them.
# ═══════════════════════════════════════════════════════════════════════════════

KILLER_PROBLEMS = [
    # ── Concurrency & Synchronization ─────────────────────────────────────
    "Design and implement a completely local, thread-safe rate limiter in Python that handles concurrent API requests using a Token Bucket algorithm. It must support per-client rate limits, burst allowance, and graceful degradation under contention. Include comprehensive tests proving thread-safety under 100 concurrent threads.",

    "Implement a lock-free concurrent skip list in Python that supports O(log n) insert, delete, and search operations. Use atomic CAS operations simulated via threading primitives. Compare your approach against a mutex-based implementation with benchmarks.",

    "Build a producer-consumer system with exactly-once processing semantics in Python. Use multiple producer threads and consumer threads sharing a bounded queue. Handle poison pills for graceful shutdown, and prove no messages are lost or duplicated under random thread scheduling.",

    "Create a read-write lock implementation in Python from scratch (no threading.RLock) that prevents writer starvation. Include a test demonstrating that 50 concurrent readers don't indefinitely block a waiting writer.",

    "Implement a concurrent hash map in Go with fine-grained locking (lock striping). Support atomic compound operations like 'compute-if-absent' and 'replace-if-equal'. Benchmark against sync.Map for various read/write ratios.",

    # ── Algorithm Design (Non-Trivial) ────────────────────────────────────
    "Implement an LRU cache in Python that supports O(1) get, put, and delete operations, with a max capacity. When the cache is full and a new key is inserted, evict the least recently used item. Include edge cases: capacity=1, capacity=0, duplicate puts, and concurrent access from multiple threads.",

    "Write a function that solves the N-Queens problem using bitwise operations for O(1) column/diagonal conflict checking. Support boards up to N=15. Return all valid solutions. Optimize memory usage by representing the board state as three integers (columns, left-diag, right-diag).",

    "Implement Dijkstra's shortest path algorithm with a Fibonacci heap for O(V log V + E) time complexity. Compare against a binary heap implementation. Generate random weighted graphs with 10,000 nodes and benchmark both implementations.",

    "Design a suffix array construction algorithm (SA-IS or DC3) for a text search engine. Support O(m log n) pattern matching where m is pattern length and n is text length. Include LCP array computation for finding longest repeated substrings.",

    "Implement the Aho-Corasick string matching algorithm for simultaneously searching multiple patterns in a text. Build the failure function using BFS. Handle overlapping matches. Use it to build a simple content filter that checks text against 1000+ banned phrases.",

    "Write a Bloom filter implementation with configurable false positive rate. Include: optimal hash function count calculation, bit array sizing, and a count-min sketch extension for approximate frequency counting. Test with 1M insertions and verify the actual false positive rate matches the theoretical one.",

    "Implement a B+ Tree with leaf-level linked list for range scans. Support insert, delete, search, and range query operations. Handle node splits, merges, and rebalancing. Visualize the tree structure for debugging. Test with 100K random insertions and deletions.",

    "Create a Trie-based autocomplete engine that supports: prefix search with top-K results ranked by frequency, fuzzy matching with edit distance ≤ 2, and incremental updates. Handle Unicode input and test with a dictionary of 50K+ words.",

    # ── System Design & Architecture ──────────────────────────────────────
    "Design and implement a complete event sourcing system in Python. Include: an event store with append-only log, aggregate root with command handlers, event replay for state reconstruction, snapshots for performance, and a projection that maintains a read-model. Handle concurrent commands with optimistic locking.",

    "Build a circuit breaker pattern implementation in Python with three states (Closed, Open, Half-Open). Support configurable failure threshold, timeout duration, and success threshold. Include a sliding window for failure rate calculation and metrics export. Test with a flaky HTTP service mock.",

    "Implement a complete SAGA pattern orchestrator for distributed transactions. Support compensating actions for rollback, timeout handling for stuck steps, and idempotent step execution. Model a real e-commerce flow: reserve inventory → charge payment → create shipment, with proper rollback on any failure.",

    "Create a plugin architecture in Python that supports: hot-reloading of plugins at runtime, dependency resolution between plugins, sandboxed execution with resource limits, and a pub/sub event bus for inter-plugin communication. Include versioning and backward compatibility checks.",

    "Design a feature flag system that supports: boolean, percentage-based, and user-segment targeting rules. Implement sticky bucketing so users see consistent behavior. Include an in-memory cache with configurable TTL and a fallback to default values on evaluation errors.",

    # ── Database & Storage ────────────────────────────────────────────────
    "Implement a write-ahead log (WAL) in Python for crash recovery. Support: log record formatting with LSN, force-write for commit records, group commit for batching, checkpoint creation, and crash recovery by replaying the log from the last checkpoint. Simulate crashes mid-transaction and verify recovery correctness.",

    "Build a simple columnar storage engine that supports: dictionary encoding, run-length encoding, and delta encoding for integer columns. Implement a vectorized scan operator that processes data in batches of 1024 values. Benchmark against a row-oriented scan for analytical queries.",

    "Create a connection pool in Python that supports: min/max pool size, idle connection timeout, health checks with configurable interval, connection draining for graceful shutdown, and fair queuing when all connections are busy. Handle connection leaks by tracking checkout duration.",

    "Implement a simple SQL parser that handles SELECT, INSERT, UPDATE, DELETE with WHERE clauses, JOINs (INNER, LEFT), GROUP BY, ORDER BY, and LIMIT. Build an AST and a query planner that chooses between sequential scan and index scan based on selectivity estimation.",

    "Design a time-series database storage engine optimized for append-heavy workloads. Implement: time-based partitioning, downsampling/aggregation, out-of-order write handling, and efficient range queries. Support retention policies that automatically delete old data.",

    # ── Networking & Protocols ────────────────────────────────────────────
    "Implement an HTTP/1.1 server from scratch in Python using only the socket library. Support: GET and POST methods, chunked transfer encoding, keep-alive connections, proper header parsing, static file serving with MIME type detection, and graceful shutdown. Handle malformed requests without crashing.",

    "Build a WebSocket server (RFC 6455) from scratch. Handle: the upgrade handshake, frame parsing (text, binary, ping, pong, close), message fragmentation, masking/unmasking, and connection lifecycle. Support broadcasting messages to all connected clients.",

    "Create a DNS resolver that handles recursive resolution from root servers. Implement: query construction and response parsing, caching with TTL, CNAME following, A and AAAA record types, and UDP with TCP fallback for large responses. Handle NXDOMAIN and SERVFAIL gracefully.",

    "Implement a simple TCP congestion control algorithm (Reno or Cubic) simulator. Model: slow start, congestion avoidance, fast retransmit, and fast recovery. Simulate packet loss and visualize the congestion window over time. Compare Reno vs Cubic under various loss rates.",

    "Build a SOCKS5 proxy server in Python. Support: authentication negotiation, CONNECT command for TCP tunneling, UDP ASSOCIATE for UDP relay, DNS resolution modes (local vs remote), and concurrent client handling with asyncio.",

    # ── Security & Cryptography ───────────────────────────────────────────
    "Implement a JWT library from scratch in Python. Support: HS256, HS384, and RS256 algorithms. Handle: token creation with claims (exp, iat, iss, sub), signature verification, expiration validation, and proper error handling for malformed/expired/invalid tokens. Do NOT use any JWT library — implement the base64url encoding, HMAC, and RSA signature verification yourself.",

    "Build a password hashing system using Argon2id (implement the core algorithm or use a binding). Include: configurable memory cost, time cost, and parallelism. Implement rate limiting on verification attempts. Compare against bcrypt and scrypt with benchmarks. Handle timing-safe comparison.",

    "Create a secure file encryption tool using AES-256-GCM. Implement: key derivation from password using PBKDF2 with random salt, authenticated encryption with associated data, proper nonce management (never reuse), and streaming encryption for large files. Include integrity verification on decryption.",

    "Audit and fix a deliberately vulnerable Python web application. The app contains: SQL injection in the login endpoint, XSS in the comment display, CSRF in the password change form, path traversal in the file download endpoint, and insecure deserialization in the session handler. Fix each vulnerability and explain why the original code was dangerous.",

    "Implement a capability-based access control system. Support: capability tokens with restricted operations, delegation chains with attenuation (each delegation can only narrow, not widen, permissions), revocation, and time-limited capabilities. Compare against traditional ACL-based access control.",

    # ── DevOps & Infrastructure ───────────────────────────────────────────
    "Write a Dockerfile for a Python FastAPI application that follows all security best practices: multi-stage build, non-root user, read-only filesystem, no shell, pinned base image digest, health check endpoint, proper signal handling for graceful shutdown, and minimal attack surface. Include docker-compose.yml with PostgreSQL and Redis.",

    "Create a GitHub Actions CI/CD pipeline for a Python monorepo with 5 microservices. Support: parallel test execution per service, only build/deploy changed services, semantic versioning from commit messages, canary deployment to Kubernetes with automatic rollback on health check failure, and Slack notifications.",

    "Implement a blue-green deployment orchestrator in Python. Support: health check verification before traffic switch, automatic rollback on failure, database migration coordination (backward-compatible only), connection draining with configurable timeout, and metrics comparison between blue and green.",

    "Build a log aggregation pipeline: collect logs from multiple sources (files, syslog, HTTP), parse and structure them, buffer in memory with disk spillover, batch-send to a storage backend, and handle backpressure. Support configurable filters, field extraction with regex, and JSON parsing.",

    # ── Frontend & UI ─────────────────────────────────────────────────────
    "Build a virtualized list component in vanilla JavaScript that efficiently renders 100,000 items. Implement: dynamic row heights, smooth scrolling with requestAnimationFrame, keyboard navigation (up/down/page up/page down/home/end), ARIA attributes for accessibility, and selection with shift+click for ranges. No frameworks.",

    "Create a drag-and-drop Kanban board using vanilla JavaScript. Support: column reordering, card reordering within and across columns, touch events for mobile, undo/redo with a command pattern, keyboard-accessible drag (Escape to cancel), and localStorage persistence. Animate transitions smoothly.",

    "Implement a real-time collaborative text editor using Operational Transformation (OT) in JavaScript. Support: concurrent edits from multiple users, conflict resolution, cursor position tracking for all users, undo/redo per user, and a simple WebSocket-based sync protocol. Handle network partitions gracefully.",

    "Build an accessible modal dialog system following WAI-ARIA best practices. Support: focus trapping, ESC to close, click-outside to close (configurable), return focus to trigger element on close, nested modals, scroll locking on the body, and animated open/close transitions. Test with a screen reader.",

    # ── Testing & Quality ─────────────────────────────────────────────────
    "Write a property-based testing framework from scratch in Python. Support: generators for basic types (int, str, list, dict), shrinking on failure (find minimal failing input), configurable number of trials, seed reproducibility, and composite generators. Test it by finding bugs in a deliberately broken sorting algorithm.",

    "Create a mutation testing tool in Python. It should: parse Python AST, apply mutations (replace operators, negate conditions, remove statements), run the test suite against each mutant, report mutation score and surviving mutants, and support configurable mutation operators. Handle timeout for infinite loops caused by mutations.",

    "Implement a test doubles library (mocks, stubs, spies, fakes) from scratch in Python without using unittest.mock. Support: method call verification with exact/any argument matchers, call count assertions, ordered call verification, and automatic spec adherence (reject calls to non-existent methods). Include a context manager for scope management.",

    "Build a code coverage tool in Python using sys.settrace. Track: line coverage, branch coverage, and function coverage. Generate an HTML report with source code highlighting (green for covered, red for uncovered). Support combining coverage from multiple test runs.",

    # ── Compilers & Language Design ───────────────────────────────────────
    "Implement a complete interpreter for a subset of Python that supports: variables, arithmetic expressions, comparison operators, if/elif/else, while loops, for loops over ranges, function definitions with closures, recursion, lists, dictionaries, string operations, and print. Use a recursive descent parser and tree-walking interpreter.",

    "Build a Pratt parser for mathematical expressions that handles: operator precedence, left and right associativity, unary operators (prefix and postfix), parenthesized grouping, function calls with multiple arguments, array indexing, and ternary operator. Generate an AST and implement an evaluator.",

    "Create a simple regex engine that supports: literal characters, dot (any char), star (zero or more), plus (one or more), question mark (optional), character classes [a-z], alternation (|), grouping with parentheses, anchors (^ and $), and escape sequences. Use Thompson's NFA construction. Benchmark against Python's re module.",

    "Implement a type checker for a simple statically-typed language with: integer, float, string, boolean, array, and function types. Support type inference for variable declarations, function return type inference, generic functions, and union types. Report all type errors with line numbers and suggestions.",

    "Write a bytecode compiler and virtual machine for a stack-based language. Support: arithmetic, comparison, local variables, function calls with arguments and return values, closures, and a simple garbage collector (mark-and-sweep). Include a disassembler for debugging.",

    # ── Distributed Systems ───────────────────────────────────────────────
    "Implement the Raft consensus algorithm in Python. Include: leader election with randomized timeouts, log replication with consistency checks, commit index advancement, cluster membership changes, and a persistent state store. Simulate a 5-node cluster with configurable network delays and partitions.",

    "Build a distributed key-value store using consistent hashing. Support: virtual nodes for load balancing, node addition/removal with minimal data migration, replication factor configuration, read/write quorum semantics, and vector clocks for conflict detection. Test with simulated node failures.",

    "Implement a gossip protocol for failure detection in a distributed system. Support: configurable suspicion timeout, protocol period, and fanout. Implement SWIM protocol extensions: suspicion mechanism, compound messages for efficiency, and protocol period adjustment based on cluster size.",

    "Create a distributed lock manager using the Redlock algorithm. Handle: clock skew between nodes, partial failures, lock extension/renewal, fencing tokens for correctness, and automatic lock release on client crash. Prove correctness under various failure scenarios.",

    "Build a CRDTs (Conflict-free Replicated Data Types) library with: G-Counter, PN-Counter, G-Set, OR-Set, LWW-Register, and LWW-Map. Implement merge operations and prove convergence. Test with simulated network partitions where replicas diverge and then re-merge.",

    # ── API Design & Microservices ────────────────────────────────────────
    "Build a complete REST API for a task management system using FastAPI. Include: JWT authentication with refresh tokens, role-based access control, pagination with cursor-based and offset-based options, filtering, sorting, rate limiting, request validation, comprehensive error responses following RFC 7807, OpenAPI documentation, and health/readiness endpoints.",

    "Implement an API gateway in Python that handles: request routing based on path prefixes, JWT validation and claims extraction, rate limiting per API key, request/response transformation, circuit breaker for downstream services, request logging and distributed tracing headers, and graceful degradation with fallback responses.",

    "Create a webhook delivery system with: at-least-once delivery guarantee, exponential backoff with jitter, dead letter queue for persistently failing endpoints, payload signing (HMAC-SHA256) for verification, delivery status tracking, and manual retry endpoint. Support batching for high-throughput scenarios.",

    "Design and implement a GraphQL server with: query resolution with DataLoader batching (N+1 prevention), mutation with input validation, subscription via WebSocket, schema stitching from multiple microservices, query complexity analysis and depth limiting, and caching with cache-control directives.",

    # ── Performance & Optimization ────────────────────────────────────────
    "Profile and optimize a deliberately slow Python function that processes a 10MB CSV file. The original takes 60 seconds. Apply step-by-step optimizations: replace csv.reader with pandas, then use numpy vectorization, then use chunked processing for memory efficiency, then add multiprocessing. Document each optimization's impact with benchmarks. Target: under 2 seconds.",

    "Implement a memory-efficient data pipeline in Python that processes a 50GB file without loading it into memory. Use: generators, itertools, memory-mapped files where appropriate, chunked reading, and multiprocessing for CPU-bound transformations. Track peak memory usage and ensure it stays under 500MB.",

    "Build a caching system with multiple eviction policies: LRU, LFU, ARC (Adaptive Replacement Cache), and FIFO. Implement a unified interface and benchmark each policy on different access patterns (zipf, sequential, random, temporal). Visualize hit rates and make a recommendation.",

    "Optimize a recursive Fibonacci implementation from O(2^n) to O(n) using memoization, then to O(log n) using matrix exponentiation. Implement all three versions, benchmark for n=10, 100, 1000, 10000, and handle arbitrary-precision integers. Visualize the performance comparison.",

    # ── AI/ML Engineering ─────────────────────────────────────────────────
    "Implement a BPE (Byte Pair Encoding) tokenizer from scratch. Support: vocabulary building from a corpus, encoding text to token IDs, decoding token IDs back to text, special tokens (PAD, BOS, EOS, UNK), and saving/loading vocabulary. Compare against tiktoken on a sample corpus.",

    "Build a KV-cache for transformer inference. Implement: pre-allocation of cache buffers, support for multi-head attention, cache rotation for fixed-size context windows, and memory usage tracking. Simulate inference with a mock attention computation and measure memory savings vs. recomputation.",

    "Create a simple RAG (Retrieval-Augmented Generation) pipeline. Implement: document chunking with overlap, TF-IDF and BM25 ranking, a vector store with cosine similarity search (using numpy, no external vector DBs), reranking, and context window management. Test with a set of technical documents and measure retrieval precision.",

    "Implement a training data deduplication pipeline using MinHash and LSH (Locality-Sensitive Hashing). Support: configurable similarity threshold, shingle size, and number of hash functions. Process a JSONL dataset and output deduplicated results with duplication statistics.",

    # ── CLI Tools & Automation ────────────────────────────────────────────
    "Build a complete CLI application in Python using argparse (no click/typer) that manages a local SQLite task database. Support: add, list, update, delete, search, tags, priorities, due dates, recurring tasks, export to JSON/CSV, and import from JSON. Include colored output, table formatting, and shell completions.",

    "Create a file synchronization tool in Python that watches a directory and mirrors changes to a target. Support: bidirectional sync, conflict detection and resolution strategies (newest wins, ask user, keep both), exclude patterns, .gitignore-style ignore files, dry-run mode, and detailed logging.",

    "Implement a simple static site generator in Python. Support: Markdown to HTML conversion, Jinja2 templates, front matter parsing, automatic table of contents, syntax highlighting for code blocks, RSS feed generation, sitemap.xml, and incremental builds (only rebuild changed files).",

    "Build a database migration tool in Python. Support: up/down migrations with SQL files, migration versioning and ordering, dependency tracking, dry-run mode, rollback to specific version, migration status reporting, and idempotent migrations. Handle partial failures gracefully.",

    # ── Data Structures (Advanced) ────────────────────────────────────────
    "Implement a persistent (immutable) balanced binary search tree (red-black tree or AVL). Support structural sharing for memory efficiency. Operations (insert, delete, lookup) should return new tree versions without modifying the original. Include versioned history traversal.",

    "Build a spatial index using an R-tree in Python. Support: insertion of 2D rectangles, range queries (find all rectangles intersecting a given rectangle), nearest-neighbor queries, bulk loading with Sort-Tile-Recursive, and visualization of the tree structure.",

    "Implement a rope data structure for efficient string manipulation in a text editor. Support: insert, delete, charAt, substring, concatenation, and split. All operations should be O(log n). Compare performance against Python strings for 1M character documents with random edits.",

    "Create a Merkle tree implementation for data integrity verification. Support: tree construction from a list of data blocks, proof generation for any leaf, proof verification, tree comparison to find differing blocks, and serialization. Use it to implement a simple file integrity checker.",

    # ── Error Handling & Resilience ───────────────────────────────────────
    "Design a comprehensive error handling system for a Python microservice. Implement: a typed error hierarchy, error codes with HTTP status mapping, structured error responses (RFC 7807), automatic retry with exponential backoff and jitter, error aggregation for batch operations, circuit breaker integration, and error reporting to a mock monitoring service.",

    "Build a chaos engineering framework in Python. Support: random latency injection, error injection (exceptions, HTTP errors), resource exhaustion simulation (memory, CPU, disk), network partition simulation, and clock skew simulation. Include a scheduler for automated chaos experiments and a report generator.",

    "Implement a bulkhead pattern in Python for resource isolation. Support: thread pool bulkheads, semaphore bulkheads, and async bulkheads. Include monitoring with rejection counters and queue depth. Test by simulating a slow downstream dependency that should not affect other callers.",

    # ── Multi-Step Debugging ──────────────────────────────────────────────
    "Debug this performance issue: A Python web scraper using asyncio and aiohttp is only achieving 10 requests/second when it should handle 100+. The bottleneck is NOT the network or the target server. Find and fix the issue. (Hint: it involves improper use of asyncio primitives that serializes what should be concurrent work.)",

    "Debug this data corruption issue: A multi-threaded Python application writes to a shared dictionary. Occasionally, keys disappear or values are from the wrong key. The code uses a lock, but the bug persists. Find the subtle issue (lock scope, TOCTOU, or dict resize during iteration) and fix it with proper synchronization.",

    "Debug this memory leak: A long-running Python service's memory grows 50MB/hour. The service processes messages from a queue and stores results in a cache with TTL-based eviction. Profile the application, identify the leak source (hint: closures capturing references, callback registrations, or cache eviction not firing), and fix it.",

    "Debug this deadlock: A Python application with two threads occasionally hangs. Thread A acquires lock_1 then needs lock_2. Thread B acquires lock_2 then needs lock_1. The deadlock only occurs under heavy load. Implement detection, prevention (lock ordering), and recovery. Include a monitoring thread that detects deadlocks and breaks them.",

    # ── Cross-Cutting Concerns ────────────────────────────────────────────
    "Implement a complete observability stack for a Python application: structured logging (JSON format with correlation IDs), metrics collection (counters, gauges, histograms), distributed tracing (W3C Trace Context), health checks (liveness + readiness), and a /debug endpoint that shows recent traces and metrics. All from scratch, no OpenTelemetry.",

    "Build a configuration management system for a Python application. Support: multiple sources (env vars, YAML files, command line, remote config), layered overrides with priority, type validation, hot-reloading with change notifications, secret masking in logs, and feature flags with targeting rules.",

    "Create an event-driven architecture framework in Python. Support: typed event definitions, sync and async handlers, handler ordering with priorities, event filtering, dead letter queue for failed handlers, event replay from a persistent store, and handler circuit breakers.",

    "Implement a job scheduler in Python (like cron but in-process). Support: cron expressions, one-time scheduled jobs, recurring jobs with configurable intervals, job dependencies (run B after A completes), max concurrent jobs, job timeout with cancellation, missed job detection, and persistent job state across restarts.",

    # ── Tricky Edge Cases ─────────────────────────────────────────────────
    "Implement a URL shortener service that handles: base62 encoding of a 64-bit counter, custom alias support, collision detection, expiry dates, click tracking with analytics (country, device, referrer), rate limiting per user, and redirect with proper HTTP status codes (301 vs 302). Handle the edge case where the counter overflows.",

    "Build a markdown parser that correctly handles: headers, bold, italic, code blocks (fenced and indented), inline code, links, images, ordered and unordered lists (nested), blockquotes (nested), horizontal rules, tables (GFM), task lists, and escaped characters. Handle all the weird edge cases (bold inside code, nested formatting, etc.).",

    "Create a JSON parser from scratch (no json library). Handle: all JSON types (null, bool, number, string, array, object), Unicode escape sequences (\\uXXXX including surrogate pairs), deeply nested structures (handle stack overflow), number edge cases (leading zeros, exponents, negative zero), and strict mode vs lenient mode.",

    "Implement a cron expression parser and scheduler that handles: minute, hour, day-of-month, month, day-of-week fields, wildcards (*), ranges (1-5), steps (*/5), lists (1,3,5), and special strings (@yearly, @monthly, @weekly, @daily, @hourly). Calculate the next N execution times from a given start time. Handle DST transitions correctly.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Parametric Problem Generator (800+)
# Reuses the domain-specific template engine from generate_dataset.py but
# generates ONLY the problem prompts (not solutions — the frontier model
# will generate those).
# ═══════════════════════════════════════════════════════════════════════════════

def _random_name(prefix: str = "", length: int = 0) -> str:
    """Generate a contextual name (no random suffix for cleaner prompts)."""
    parts = [
        "rate_limiter", "cache_manager", "task_scheduler", "event_bus",
        "connection_pool", "message_broker", "auth_service", "data_pipeline",
        "search_engine", "config_manager", "log_aggregator", "metrics_collector",
        "session_handler", "file_processor", "notification_service",
        "payment_gateway", "inventory_tracker", "user_registry",
        "health_checker", "load_balancer"
    ]
    return f"{prefix}{random.choice(parts)}" if prefix else random.choice(parts)


PARAMETRIC_TEMPLATES = {
    "concurrency": [
        lambda: f"Implement a thread-safe {random.choice(['bounded blocking queue', 'work-stealing deque', 'read-copy-update (RCU) data structure', 'hazard pointer system', 'lock-free stack'])} in {random.choice(['Python', 'Rust', 'Go', 'Java', 'C++'])} that supports {random.randint(4, 64)} concurrent workers. Handle {random.choice(['priority inversion', 'ABA problem', 'false sharing on cache lines', 'thundering herd on wakeup', 'memory ordering constraints'])}. Include stress tests with {random.randint(100, 10000)} operations across {random.randint(4, 32)} threads.",
        lambda: f"Build a {random.choice(['fork-join', 'work-stealing', 'thread-per-core', 'event-loop based', 'coroutine-based'])} task executor in {random.choice(['Python', 'Rust', 'Go'])} with a pool of {random.randint(2, 16)} workers. Support {random.choice(['task cancellation with cleanup', 'task dependencies forming a DAG', 'priority-based scheduling with aging', 'cooperative cancellation via context', 'task timeout with resource cleanup'])}. Benchmark throughput under {random.choice(['CPU-bound', 'I/O-bound', 'mixed CPU/IO', 'bursty', 'steady-state'])} workloads.",
    ],

    "algorithms": [
        lambda: f"Implement {random.choice(['A* pathfinding', 'Bellman-Ford with negative cycle detection', 'Floyd-Warshall all-pairs shortest path', 'Johnsons algorithm', 'bidirectional BFS'])} on a {random.choice(['2D grid with dynamic obstacles', 'weighted directed graph with 10K nodes', 'sparse graph represented as adjacency list', 'graph with negative edge weights', 'graph stored as compressed sparse row (CSR)'])}. Optimize for {random.choice(['memory usage (keep under 50MB)', 'cache-friendly access patterns', 'early termination when target is found', 'parallel exploration of the search space', 'incremental re-computation when edges change'])}.",
        lambda: f"Implement {random.choice(['merge sort', 'quicksort', 'radix sort', 'timsort', 'introsort'])} with {random.choice(['three-way partitioning for duplicates', 'insertion sort fallback for small subarrays', 'iterative (non-recursive) implementation', 'external sorting for files larger than RAM', 'stable sorting with O(1) extra space'])} in {random.choice(['Python', 'Rust', 'C++', 'Go'])}. Handle arrays of {random.choice(['1 million integers', '10 million strings', '100K custom objects with composite keys', 'floating-point numbers with NaN handling', 'variable-length records from a binary file'])}. Benchmark against the standard library sort.",
        lambda: f"Implement {random.choice(['a Fenwick tree (Binary Indexed Tree)', 'a segment tree with lazy propagation', 'a sparse table for range minimum queries', 'a heavy-light decomposition for tree paths', 'a centroid decomposition for tree queries'])} in {random.choice(['Python', 'Rust', 'C++'])}. Support {random.choice(['range sum queries and point updates', 'range minimum queries and range updates', 'k-th smallest element in a range', 'count of distinct elements in a range', 'range GCD queries with point updates'])}. Test with {random.randint(100000, 1000000)} elements and {random.randint(50000, 500000)} queries.",
    ],

    "web_backend": [
        lambda: f"Build a {random.choice(['REST', 'GraphQL', 'gRPC'])} API for a {random.choice(['real-time chat application', 'e-commerce product catalog', 'social media feed', 'file storage service', 'IoT device management platform'])} using {random.choice(['FastAPI', 'Flask', 'Express.js', 'Go net/http', 'Rust Actix-web'])}. Include {random.choice(['JWT auth with refresh token rotation', 'OAuth 2.0 PKCE flow', 'API key authentication with rate limiting', 'session-based auth with CSRF protection', 'mutual TLS (mTLS) authentication'])}. Handle {random.choice(['pagination with cursor-based navigation', 'file uploads with streaming and progress', 'WebSocket connections for real-time updates', 'long-polling with timeout management', 'server-sent events (SSE) for notifications'])}.",
        lambda: f"Implement a {random.choice(['reverse proxy', 'API gateway', 'load balancer', 'service mesh sidecar', 'request router'])} in {random.choice(['Python asyncio', 'Go', 'Rust', 'Node.js'])} that handles {random.randint(100, 10000)} concurrent connections. Support {random.choice(['health-check-based routing', 'weighted round-robin with slow-start', 'consistent hashing for session affinity', 'least-connections routing', 'header-based routing with regex'])}. Include {random.choice(['circuit breaker with half-open probing', 'retry with exponential backoff and jitter', 'request timeout with context propagation', 'rate limiting with sliding window', 'request/response compression'])}.",
    ],

    "databases": [
        lambda: f"Implement a {random.choice(['LSM-tree storage engine', 'B-tree index', 'hash index with linear probing', 'skip list index', 'radix tree (Patricia trie) index'])} for a {random.choice(['key-value store', 'document database', 'time-series database', 'graph database', 'column-oriented store'])}. Support {random.choice(['ACID transactions with WAL', 'snapshot isolation with MVCC', 'serializable isolation with 2PL', 'optimistic concurrency control', 'eventual consistency with last-writer-wins'])}. Optimize for {random.choice(['write-heavy workloads (10:1 write:read)', 'read-heavy workloads (100:1 read:write)', 'range scans over sorted data', 'point lookups with O(1) average case', 'mixed workloads with adaptive tuning'])}.",
        lambda: f"Write a complex SQL query that {random.choice(['finds the top 10 customers by revenue with year-over-year growth rate', 'detects fraudulent transactions using self-joins and window functions', 'computes a running average of sales with a 7-day sliding window', 'performs gap analysis on time-series data to find missing periods', 'generates a recursive bill-of-materials with cost rollup'])}. Then optimize it: write the EXPLAIN ANALYZE breakdown, identify bottlenecks, add appropriate indexes, and rewrite the query. Show before/after execution plans and timing.",
    ],

    "security": [
        lambda: f"Audit and fix {random.choice(['SQL injection', 'XSS (stored, reflected, and DOM-based)', 'SSRF with internal network scanning', 'authentication bypass via JWT algorithm confusion', 'insecure deserialization leading to RCE'])} vulnerabilities in a {random.choice(['Python Flask', 'Node.js Express', 'Java Spring', 'Go', 'PHP Laravel'])} application. Implement {random.choice(['parameterized queries with input validation', 'Content Security Policy with nonce-based script execution', 'URL allowlisting with DNS rebinding protection', 'algorithm pinning with key rotation', 'type-safe deserialization with allowlisting'])}. Write exploit proof-of-concept tests and verify the fix prevents them.",
        lambda: f"Implement a {random.choice(['TOTP (Time-based One-Time Password)', 'WebAuthn/FIDO2 registration and authentication', 'OAuth 2.0 authorization server', 'certificate-based mutual TLS', 'zero-knowledge proof authentication'])} system in {random.choice(['Python', 'TypeScript', 'Go', 'Rust'])}. Handle {random.choice(['clock skew between client and server', 'credential storage with hardware security modules', 'token revocation with bloom filter', 'brute-force protection with progressive delays', 'account recovery with backup codes'])}. Include comprehensive security tests.",
    ],

    "devops": [
        lambda: f"Write a {random.choice(['Dockerfile (multi-stage)', 'Kubernetes Deployment + Service + Ingress', 'Terraform module', 'Ansible playbook', 'GitHub Actions workflow'])} for a {random.choice(['Python ML inference service with GPU support', 'Node.js app with Redis and PostgreSQL', 'Go microservice with gRPC and health checks', 'Java Spring Boot with Kafka', 'Rust API server with TLS termination'])}. Include {random.choice(['horizontal pod autoscaling on custom metrics', 'canary deployment with Istio traffic splitting', 'secret rotation with Vault integration', 'distributed tracing with Jaeger sidecar', 'chaos testing with Litmus or Chaos Monkey'])}. Ensure {random.choice(['zero-downtime rolling updates', 'rollback on failed health checks', 'resource limits preventing noisy neighbor', 'security scanning in CI pipeline', 'cost optimization with spot/preemptible instances'])}.",
    ],

    "compilers": [
        lambda: f"Implement a {random.choice(['lexer with DFA-based tokenization', 'recursive descent parser', 'Pratt parser for expressions', 'LR(1) parser generator', 'PEG parser with packrat memoization'])} for a {random.choice(['statically-typed expression language with type inference', 'Lisp dialect with macros and tail-call optimization', 'Python-like language with significant whitespace', 'SQL-like query DSL', 'shell-like scripting language with pipes'])}. Support {random.choice(['operator precedence and associativity', 'pattern matching with exhaustiveness checking', 'algebraic data types and generics', 'first-class functions and closures', 'module imports with cycle detection'])}. Include {random.choice(['comprehensive error recovery with diagnostic messages', 'source location tracking for error reporting', 'incremental parsing for IDE integration', 'syntax highlighting token stream', 'pretty-printer for AST'])}.",
        lambda: f"Build a {random.choice(['tree-walking interpreter', 'bytecode compiler + stack VM', 'register-based VM', 'CPS (continuation-passing style) interpreter', 'JIT compiler using basic blocks'])} for a language that supports {random.choice(['integers, floats, strings, booleans, and nil', 'first-class functions, closures, and recursion', 'classes with single inheritance and method dispatch', 'algebraic data types with pattern matching', 'coroutines/generators with yield'])}. Implement {random.choice(['a mark-and-sweep garbage collector', 'reference counting with cycle detection', 'a simple stack-based call convention', 'tail-call optimization', 'constant folding and dead code elimination'])}.",
    ],

    "distributed": [
        lambda: f"Implement {random.choice(['Paxos single-decree consensus', 'Raft with log compaction', 'PBFT (Practical Byzantine Fault Tolerance)', 'chain replication', 'Viewstamped Replication'])} in {random.choice(['Python', 'Go', 'Rust'])}. Handle {random.choice(['network partitions with split-brain detection', 'leader failures with automatic re-election', 'message reordering and duplication', 'Byzantine nodes sending conflicting messages', 'clock skew up to 500ms between nodes'])}. Test with {random.choice(['deterministic simulation with fault injection', 'Jepsen-style linearizability checking', 'chaos scenarios with random process kills', 'slow network simulation with configurable latency', 'asymmetric partitions (A can reach B but not C)'])}.",
    ],

    "os_systems": [
        lambda: f"Implement a {random.choice(['preemptive priority scheduler', 'completely fair scheduler (CFS)', 'multi-level feedback queue', 'earliest deadline first (EDF) scheduler', 'lottery scheduler'])} in {random.choice(['Python', 'Rust', 'C'])}. Support {random.choice(['process priorities with aging to prevent starvation', 'time quantum adjustment based on process behavior', 'multi-core scheduling with load balancing', 'real-time constraints with deadline guarantees', 'energy-aware scheduling for mobile devices'])}. Simulate {random.randint(10, 100)} processes with {random.choice(['mixed CPU-bound and I/O-bound workloads', 'periodic tasks with varying periods', 'bursty arrival patterns', 'priority inversion scenarios', 'convoy effect conditions'])}.",
        lambda: f"Implement a {random.choice(['buddy system allocator', 'slab allocator', 'arena allocator', 'free-list allocator with coalescing', 'TLSF (Two-Level Segregated Fit) allocator'])} in {random.choice(['Python', 'Rust', 'C', 'C++'])}. Handle {random.choice(['external fragmentation with compaction', 'internal fragmentation analysis', 'thread-safe allocation without global lock', 'alignment requirements for SIMD operations', 'out-of-memory conditions with fallback strategies'])}. Benchmark with {random.choice(['random allocation/deallocation patterns', 'object pooling for fixed-size allocations', 'realistic browser memory access patterns', 'server request processing memory patterns', 'adversarial allocation sequences that maximize fragmentation'])}.",
    ],

    "networking": [
        lambda: f"Implement a {random.choice(['HTTP/2 frame parser', 'QUIC connection handshake', 'MQTT v5 broker', 'Redis RESP3 protocol parser', 'WebRTC signaling server'])} in {random.choice(['Python', 'Go', 'Rust', 'TypeScript'])}. Handle {random.choice(['flow control with window updates', 'connection multiplexing with stream prioritization', 'TLS 1.3 integration', 'connection migration across network changes', 'zero-RTT connection resumption'])}. Include {random.choice(['fuzz testing with random byte sequences', 'conformance tests against the RFC', 'load testing with 1000 concurrent connections', 'graceful degradation under memory pressure', 'connection draining for rolling deployments'])}.",
    ],

    "ml_engineering": [
        lambda: f"Implement a {random.choice(['mini-batch gradient descent optimizer with momentum', 'learning rate scheduler (cosine annealing with warm restarts)', 'data augmentation pipeline for images', 'distributed training coordinator using all-reduce', 'model checkpoint manager with best-k tracking'])} in {random.choice(['Python with NumPy only', 'Python with PyTorch', 'Rust', 'Go'])}. Handle {random.choice(['gradient clipping for training stability', 'mixed-precision computation', 'out-of-core datasets larger than RAM', 'checkpoint recovery after crash', 'early stopping with patience'])}. Benchmark on {random.choice(['MNIST classification', 'a synthetic regression problem', 'time-series forecasting', 'text classification with bag-of-words', 'collaborative filtering for recommendations'])}.",
    ],

    "frontend": [
        lambda: f"Build a {random.choice(['spreadsheet with formula evaluation', 'code editor with syntax highlighting', 'drawing canvas with undo/redo', 'interactive data visualization dashboard', 'markdown WYSIWYG editor'])} using {random.choice(['vanilla JavaScript (no frameworks)', 'React with hooks', 'Svelte', 'Web Components with Shadow DOM', 'TypeScript with strict mode'])}. Include {random.choice(['keyboard shortcuts and command palette', 'touch/gesture support for mobile', 'collaborative editing via WebSocket', 'offline support with service worker', 'accessibility (WCAG 2.1 AA)'])}. Optimize for {random.choice(['60fps smooth scrolling', 'initial load under 100KB', 'rendering 10K+ elements', 'instant response to user input (<16ms)', 'memory usage under 50MB for large documents'])}.",
    ],

    "testing": [
        lambda: f"Write {random.choice(['property-based tests', 'contract tests', 'integration tests with test containers', 'end-to-end tests with browser automation', 'snapshot tests for serialization'])} for a {random.choice(['payment processing service with Stripe integration', 'user authentication system with MFA', 'data pipeline with schema evolution', 'real-time chat server', 'file storage service with encryption'])}. Cover {random.choice(['happy path, error cases, and boundary conditions', 'concurrent access patterns with race condition detection', 'failure modes in downstream dependencies', 'data migration and backward compatibility', 'performance regression with latency assertions'])}. Include {random.choice(['test fixtures with database seeding', 'mock service with configurable failure modes', 'deterministic time control for time-dependent logic', 'test data generators for random valid inputs', 'coverage reporting with branch coverage'])}.",
    ],

    "mobile": [
        lambda: f"Implement {random.choice(['offline-first sync with conflict resolution', 'biometric auth flow with fallback', 'push notification handler with deep linking', 'in-app purchase with receipt validation', 'background data sync with battery optimization'])} for a {random.choice(['React Native', 'Flutter', 'Swift iOS', 'Kotlin Android'])} app. Handle {random.choice(['intermittent network with retry and queue', 'app lifecycle (background, terminate, restore)', 'keychain/keystore secure storage', 'OS permission changes at runtime', 'memory pressure and low-storage'])}. Include {random.choice(['unit and widget tests', 'integration tests with mocked APIs', 'accessibility testing with screen reader', 'performance profiling', 'crash reporting setup'])}.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Multi-Language Variants
# Same logical problem, different languages — teaches language-agnostic reasoning
# ═══════════════════════════════════════════════════════════════════════════════

MULTI_LANGUAGE_PROBLEMS_BASE = [
    "Implement a thread-safe LRU cache with O(1) get/put operations and configurable max capacity.",
    "Build a rate limiter using the sliding window log algorithm with per-client tracking.",
    "Create a DAG-based task scheduler that detects cycles and executes tasks in topological order.",
    "Implement a pub/sub event system with typed events, async handlers, and dead letter queue.",
    "Write a concurrent web crawler that respects robots.txt, handles rate limiting, and stores results.",
    "Build a simple key-value store with WAL for durability and snapshot-based recovery.",
    "Implement a consistent hashing ring with virtual nodes and support for node addition/removal.",
    "Create a retry mechanism with exponential backoff, jitter, and circuit breaker integration.",
    "Build a stream processing pipeline with windowed aggregation and watermark-based late data handling.",
    "Implement a state machine framework with typed states, transitions, guards, and action hooks.",
]

MULTI_LANGUAGES = ["Python", "Rust", "Go", "TypeScript", "Java"]


def generate_multi_language_problems() -> List[str]:
    """Generate the same problem across multiple languages."""
    problems = []
    for base_problem in MULTI_LANGUAGE_PROBLEMS_BASE:
        for lang in MULTI_LANGUAGES:
            problems.append(f"[{lang}] {base_problem} Write the complete implementation in {lang} with tests.")
    return problems


def generate_parametric_problems(count_per_category: int = 60) -> List[str]:
    """Generate parametric problems from all domain templates."""
    problems = []
    for category, generators in PARAMETRIC_TEMPLATES.items():
        for _ in range(count_per_category):
            gen = random.choice(generators)
            problems.append(gen())
    return problems


def generate_all_problems(
    parametric_per_category: int = 60,
    include_killer: bool = True,
    include_multi_lang: bool = True,
    seed: int = 42,
) -> List[Dict]:
    """
    Generate all problems with metadata.
    
    Returns a list of dicts with:
      - problem: The problem text
      - category: The category (killer, parametric_<domain>, multi_lang)
      - hash: SHA256 hash for deduplication
    """
    random.seed(seed)
    all_problems = []

    # 1. Killer problems
    if include_killer:
        for p in KILLER_PROBLEMS:
            all_problems.append({
                "problem": p,
                "category": "killer",
                "hash": hashlib.sha256(p.encode()).hexdigest()[:16],
            })

    # 2. Parametric problems
    for category, generators in PARAMETRIC_TEMPLATES.items():
        for _ in range(parametric_per_category):
            gen = random.choice(generators)
            problem_text = gen()
            all_problems.append({
                "problem": problem_text,
                "category": f"parametric_{category}",
                "hash": hashlib.sha256(problem_text.encode()).hexdigest()[:16],
            })

    # 3. Multi-language variants
    if include_multi_lang:
        for p in generate_multi_language_problems():
            all_problems.append({
                "problem": p,
                "category": "multi_lang",
                "hash": hashlib.sha256(p.encode()).hexdigest()[:16],
            })

    # Deduplicate by hash
    seen = set()
    unique = []
    for p in all_problems:
        if p["hash"] not in seen:
            seen.add(p["hash"])
            unique.append(p)

    random.shuffle(unique)
    return unique


def print_stats(problems: List[Dict]) -> None:
    """Print distribution statistics."""
    from collections import Counter
    categories = Counter(p["category"] for p in problems)
    
    print("=" * 60)
    print(f" PROBLEM BANK STATISTICS — Total: {len(problems)} problems")
    print("=" * 60)
    
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        bar = "█" * (count // 5)
        print(f"  {cat:<30s} {count:>4d}  {bar}")
    
    print("-" * 60)
    
    # Sample problems
    print("\n📋 Sample problems (first 3):\n")
    for i, p in enumerate(problems[:3]):
        print(f"  [{i+1}] [{p['category']}]")
        print(f"      {p['problem'][:120]}...")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nova 1.5B Problem Bank Generator")
    parser.add_argument("--export", type=str, help="Export problems to JSON file")
    parser.add_argument("--count", type=int, default=60, help="Parametric problems per category (default: 60)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-killer", action="store_true", help="Exclude hand-crafted killer problems")
    parser.add_argument("--no-multi-lang", action="store_true", help="Exclude multi-language variants")
    args = parser.parse_args()

    problems = generate_all_problems(
        parametric_per_category=args.count,
        include_killer=not args.no_killer,
        include_multi_lang=not args.no_multi_lang,
        seed=args.seed,
    )

    print_stats(problems)

    if args.export:
        with open(args.export, "w") as f:
            json.dump(problems, f, indent=2)
        print(f"\n✅ Exported {len(problems)} problems to {args.export}")
