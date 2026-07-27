#!/usr/bin/env python3
"""
generate_noncoding_examples.py — Generate 48 non-coding <<RESPONSE>> training examples

Covers all 10 phrasing patterns (4 missing + 6 existing) with varied structure.
Appends to dataset_nova3b_v8.jsonl to create dataset_nova3b_v9.jsonl.
"""

import json
import shutil

EXAMPLES = [
    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "How does X work" (6 examples) — MISSING PATTERN
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "How does DNS resolution work?",
        "thinking": "This is an explanation request about networking infrastructure.",
        "response": """DNS resolution translates human-readable domain names (like `example.com`) into IP addresses through a multi-step lookup:

1. **Browser cache**: Check if the domain was recently resolved
2. **OS resolver cache**: Check the local system's DNS cache
3. **Recursive resolver**: Your ISP's DNS server queries on your behalf
4. **Root nameserver**: Directs the query to the correct TLD server (`.com`, `.org`)
5. **TLD nameserver**: Points to the authoritative nameserver for the domain
6. **Authoritative nameserver**: Returns the actual IP address for the domain

The resolved IP is cached at multiple levels (with a TTL) so subsequent lookups are near-instant. The entire process typically completes in under 100ms."""
    },
    {
        "user": "How does HTTPS encryption actually work under the hood?",
        "thinking": "This is an explanation request about cryptographic protocols.",
        "response": """HTTPS uses TLS (Transport Layer Security) to encrypt HTTP traffic. The process has two phases:

**1. TLS Handshake (asymmetric encryption):**
- Client sends a "Client Hello" with supported cipher suites and a random number
- Server responds with its SSL certificate (containing its public key) and a random number
- Client verifies the certificate against trusted Certificate Authorities (CAs)
- Client generates a pre-master secret, encrypts it with the server's public key, and sends it
- Both sides derive the same session key from the pre-master secret + random numbers

**2. Data Transfer (symmetric encryption):**
- All subsequent data is encrypted/decrypted with the shared session key (AES-256 typically)
- Symmetric encryption is used because it's ~1000x faster than asymmetric

The handshake uses asymmetric crypto (slow, secure) to negotiate a symmetric key (fast), then switches to symmetric for the actual data transfer."""
    },
    {
        "user": "How does garbage collection work in Go?",
        "thinking": "This is an explanation request about Go runtime internals.",
        "response": """Go uses a **concurrent, tri-color mark-and-sweep** garbage collector:

- **Mark phase**: The GC traverses all reachable objects starting from roots (stack variables, globals). Objects are colored white (unvisited), gray (visited, children not yet scanned), or black (visited, all children scanned).
- **Sweep phase**: All objects still white (unreachable) after marking are freed.
- **Concurrent**: Most GC work runs concurrently with application goroutines, minimizing pause times (typically < 1ms).
- **Write barrier**: A write barrier tracks pointer updates during concurrent marking to prevent missed references.

Go's GC prioritizes low latency over throughput. You can tune it with `GOGC` (default 100 = trigger GC when heap doubles) but cannot disable it entirely."""
    },
    {
        "user": "How does a load balancer distribute traffic?",
        "thinking": "This is an explanation request about infrastructure and networking.",
        "response": """A load balancer sits between clients and a pool of backend servers, distributing incoming requests to prevent any single server from being overwhelmed.

**Common algorithms:**
- **Round-robin**: Requests go to each server in sequence (A → B → C → A → ...)
- **Least connections**: Send to the server with the fewest active connections
- **Weighted**: Servers with more resources get proportionally more traffic
- **IP hash**: Same client IP always routes to the same server (useful for session affinity)

**Layer 4 vs Layer 7:**
- **L4 (transport)**: Routes based on IP/port. Faster but no content awareness.
- **L7 (application)**: Routes based on HTTP headers, URL path, cookies. Slower but enables smarter routing (e.g., `/api/*` to API servers, `/static/*` to CDN).

Health checks continuously probe backend servers and remove unhealthy ones from the pool automatically."""
    },
    {
        "user": "How do database transactions work?",
        "thinking": "This is an explanation request about database concepts.",
        "response": """A database transaction is a sequence of operations that are executed as a single, atomic unit — either all operations succeed, or none of them do.

Transactions follow the **ACID** properties:
- **Atomicity**: All operations in the transaction complete, or the entire transaction is rolled back
- **Consistency**: The database moves from one valid state to another — constraints are never violated
- **Isolation**: Concurrent transactions don't interfere with each other (as if they ran sequentially)
- **Durability**: Once committed, the data survives system crashes (written to disk/WAL)

**Isolation levels** (from weakest to strongest):
1. Read Uncommitted — can see uncommitted changes from other transactions (dirty reads)
2. Read Committed — only sees committed data (default in PostgreSQL)
3. Repeatable Read — same query returns same results within a transaction (default in MySQL InnoDB)
4. Serializable — full isolation, as if transactions ran one at a time (slowest)

Higher isolation = fewer anomalies but more locking overhead."""
    },
    {
        "user": "How does JWT authentication work in web applications?",
        "thinking": "This is an explanation request about authentication mechanisms.",
        "response": """JWT (JSON Web Token) is a stateless authentication mechanism where the server issues a signed token instead of maintaining a session.

**Flow:**
1. Client sends credentials (username/password) to the auth endpoint
2. Server verifies credentials, creates a JWT containing claims (user ID, role, expiry)
3. Server signs the JWT with a secret key (HMAC) or private key (RSA) and returns it
4. Client stores the JWT (usually in localStorage or an httpOnly cookie)
5. Client includes the JWT in the `Authorization: Bearer <token>` header on every request
6. Server verifies the signature and extracts claims — no database lookup needed

**JWT structure** (three Base64-encoded parts separated by dots):
- **Header**: Algorithm and token type (`{"alg": "HS256", "typ": "JWT"}`)
- **Payload**: Claims (user data, expiry, issuer)
- **Signature**: `HMAC(header + payload, secret)` — proves the token wasn't tampered with

**Trade-off**: JWTs can't be revoked before expiry without maintaining a blacklist, which partially defeats the stateless benefit."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "Define" (6 examples) — MISSING PATTERN
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "Define eventual consistency and when it matters.",
        "thinking": "This is a definition request about distributed systems concepts.",
        "response": """**Eventual consistency** is a consistency model where, after a write, all replicas of the data will *eventually* converge to the same value — but reads immediately after the write may return stale data.

It trades real-time accuracy for availability and partition tolerance (the AP side of the CAP theorem).

**When it matters:**
- Social media feeds (a few seconds of stale likes/comments is acceptable)
- DNS propagation (updates take minutes to hours to reach all servers)
- Shopping cart counts (briefly showing the wrong item count won't lose the order)

**When it's NOT acceptable:**
- Bank account balances (double-spending risk)
- Inventory counts for limited-stock items
- Anything requiring exactly-once semantics"""
    },
    {
        "user": "Define the terms 'horizontal scaling' and 'vertical scaling'.",
        "thinking": "This is a definition request comparing two scaling strategies.",
        "response": """**Vertical scaling (scale up):** Adding more resources (CPU, RAM, disk) to a single machine. Simple but has a ceiling — you can't add infinite hardware to one server.

**Horizontal scaling (scale out):** Adding more machines to distribute the workload. More complex (requires load balancing, data partitioning) but has no theoretical ceiling.

| Aspect | Vertical | Horizontal |
|--------|----------|------------|
| Cost curve | Exponential (high-end hardware is disproportionately expensive) | Linear (add commodity machines) |
| Downtime | Usually requires restart | Zero-downtime (add nodes live) |
| Complexity | Low (single machine) | High (distributed state, network) |
| Limit | Physical hardware ceiling | Practically unlimited |

Most production systems use both: vertically scale each node to a sensible size, then horizontally scale the cluster."""
    },
    {
        "user": "Define what a reverse proxy does.",
        "thinking": "This is a definition request about web infrastructure.",
        "response": """A **reverse proxy** is a server that sits in front of backend servers and forwards client requests to them. Unlike a forward proxy (which acts on behalf of clients), a reverse proxy acts on behalf of servers.

**Key functions:**
- **Load balancing**: Distributes requests across multiple backend servers
- **SSL termination**: Handles HTTPS encryption/decryption so backend servers don't need to
- **Caching**: Stores and serves static content without hitting the backend
- **Compression**: Compresses responses (gzip/brotli) before sending to clients
- **Security**: Hides backend server IPs, blocks malicious requests, adds rate limiting

**Common reverse proxies:** Nginx, HAProxy, Caddy, Traefik, AWS ALB.

The client only sees the reverse proxy's IP address — it has no knowledge of the backend servers behind it."""
    },
    {
        "user": "Define idempotency in the context of APIs.",
        "thinking": "This is a definition request about API design concepts.",
        "response": """**Idempotency** means that making the same API request multiple times produces the same result as making it once — no unintended side effects from retries.

**Idempotent HTTP methods:**
- `GET` — Always idempotent (reads don't change state)
- `PUT` — Idempotent (setting a resource to the same value repeatedly is safe)
- `DELETE` — Idempotent (deleting something that's already deleted returns 404, no harm done)

**NOT idempotent by default:**
- `POST` — Creating a resource twice creates two copies
- `PATCH` — Depends on the operation (incrementing a counter is not idempotent)

**Why it matters:** Network failures cause retries. If a payment API isn't idempotent, a timeout + retry could charge the customer twice. Solutions include idempotency keys (a unique ID per request that the server deduplicates) or designing operations as "set to X" instead of "increment by Y"."""
    },
    {
        "user": "Define the concept of database sharding.",
        "thinking": "This is a definition request about database architecture.",
        "response": """**Sharding** is a horizontal partitioning strategy where data is split across multiple independent database instances (shards), each holding a subset of the total data.

**How it works:**
- A **shard key** (e.g., user_id, region) determines which shard stores each record
- Each shard is a fully independent database with its own storage and compute
- A routing layer directs queries to the correct shard based on the shard key

**Benefits:**
- Linear scalability — add more shards to handle more data/traffic
- Smaller indexes per shard — faster queries
- Geographic locality — shard by region for lower latency

**Challenges:**
- Cross-shard queries are expensive (joins across shards require scatter-gather)
- Rebalancing shards when data grows unevenly (hot spots)
- Application complexity — the app must be shard-aware
- No cross-shard transactions without distributed consensus (2PC, Saga)

Good shard keys have high cardinality and even distribution. Bad shard keys (e.g., country) create hot spots."""
    },
    {
        "user": "Define what 'technical debt' means in software engineering.",
        "thinking": "This is a definition request about software engineering concepts.",
        "response": """**Technical debt** is the accumulated cost of shortcuts, workarounds, and deferred improvements in a codebase. Like financial debt, it accrues "interest" — the longer it's left, the more expensive future changes become.

**Types:**
- **Deliberate**: Consciously choosing a quick-and-dirty solution to meet a deadline, with plans to refactor later
- **Accidental**: Debt that accumulates from lack of knowledge, changing requirements, or evolving best practices
- **Bit rot**: Working code that degrades over time as dependencies, standards, and the surrounding codebase change

**Common examples:**
- Duplicated code instead of shared abstractions
- Missing tests that make refactoring risky
- Hardcoded values instead of configuration
- Outdated dependencies with known vulnerabilities

**Managing it:** Track it explicitly (code comments, tickets), allocate a percentage of each sprint to debt reduction, and prioritize debt that blocks current feature work over debt that's merely ugly."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "When should / Why" (6 examples) — MISSING PATTERN
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "When should you use a message queue instead of direct API calls?",
        "thinking": "This is an architecture decision explanation request.",
        "response": """Use a message queue (RabbitMQ, SQS, Kafka) instead of direct API calls when:

1. **Async processing**: The caller doesn't need an immediate result (e.g., sending emails, generating reports)
2. **Load leveling**: Incoming request rate exceeds what the downstream service can handle — the queue acts as a buffer
3. **Decoupling**: Producer and consumer should be independently deployable and scalable
4. **Retry/resilience**: Failed processing should be retried automatically without the caller re-sending
5. **Fan-out**: One event needs to trigger multiple downstream actions

**Stick with direct API calls when:**
- You need a synchronous response (e.g., user login, payment authorization)
- Latency requirements are strict (queues add 10-100ms+ overhead)
- The system is simple enough that adding queue infrastructure isn't justified"""
    },
    {
        "user": "Why is immutability important in functional programming?",
        "thinking": "This is an explanation request about functional programming principles.",
        "response": """Immutability — once created, data cannot be changed — is central to functional programming for three reasons:

1. **No race conditions**: If data never changes, concurrent reads are always safe without locks or synchronization.
2. **Predictable functions**: Pure functions with immutable inputs always produce the same output — no hidden state mutations make debugging easier.
3. **Safe sharing**: Immutable data can be freely passed between functions, threads, or components without defensive copying.

**Trade-off**: Creating new objects instead of mutating existing ones uses more memory and causes more GC pressure. Languages like Clojure and Haskell use structural sharing (persistent data structures) to minimize this cost — new versions share unchanged subtrees with the original."""
    },
    {
        "user": "When should you use WebSockets instead of HTTP polling?",
        "thinking": "This is a comparison/decision explanation about real-time communication.",
        "response": """**Use WebSockets when:**
- You need true real-time, bidirectional communication (chat, live collaboration, multiplayer games)
- Update frequency is high (multiple times per second)
- You need server-initiated messages (push notifications, live dashboards)
- Keeping a persistent connection is acceptable

**Use HTTP polling (or long-polling) when:**
- Updates are infrequent (every 30s+)
- Infrastructure doesn't support WebSockets (some proxies/firewalls block them)
- Stateless architecture is required (WebSockets are stateful connections)
- You need simplicity — polling is just regular HTTP requests

**Consider SSE (Server-Sent Events) as a middle ground** when you only need server→client push (no bidirectional) — it's simpler than WebSockets and works over standard HTTP."""
    },
    {
        "user": "Why do we need database indexes if they slow down writes?",
        "thinking": "This is an explanation request about database performance trade-offs.",
        "response": """Indexes speed up reads dramatically but slow down writes because every INSERT/UPDATE/DELETE must also update the index. The trade-off is almost always worth it because:

1. **Read-heavy workloads**: Most applications read far more than they write (often 10:1 or 100:1). A query that scans 1M rows without an index takes seconds; with an index, it takes milliseconds.
2. **Targeted acceleration**: You only index columns used in WHERE, JOIN, ORDER BY, and GROUP BY clauses — not every column.
3. **Write overhead is small**: Updating a B-tree index on INSERT is O(log n) — negligible for most workloads.

**When to skip indexes:**
- Write-heavy tables with minimal querying (log/event tables)
- Columns with very low cardinality (a boolean `is_active` column with 50/50 distribution)
- Small tables where a full scan is already fast (< 1000 rows)

The right approach is to start with indexes on primary keys and foreign keys, then add more based on actual slow query logs."""
    },
    {
        "user": "When should I use NoSQL instead of a relational database?",
        "thinking": "This is an architecture decision explanation about database selection.",
        "response": """**Use NoSQL when:**
- Your data model is document-oriented, hierarchical, or graph-shaped — not naturally tabular
- You need horizontal scalability across many machines (NoSQL databases are designed for sharding)
- Schema flexibility matters — fields can vary between records without migrations
- You need very high write throughput (append-heavy workloads like IoT, logging, time-series)
- Your access patterns are simple and well-defined (key-value lookups, document retrieval)

**Stick with relational (SQL) when:**
- Data has complex relationships requiring JOINs (e.g., orders → line items → products → categories)
- You need ACID transactions across multiple tables
- Data integrity and constraints (foreign keys, uniqueness, check constraints) are critical
- You need ad-hoc querying and reporting (SQL is far more expressive than most NoSQL query languages)
- Your team already knows SQL and the data fits naturally into tables

**Rule of thumb**: If you're unsure, start with PostgreSQL — it handles JSON documents, full-text search, and scales vertically to very large workloads before you need to consider NoSQL."""
    },
    {
        "user": "Why should you avoid premature optimization?",
        "thinking": "This is an explanation request about software engineering principles.",
        "response": """"Premature optimization is the root of all evil" (Donald Knuth) — but the nuance matters.

**Why it's harmful:**
1. **Wrong target**: Without profiling, developers optimize code that isn't the bottleneck. The slow part is almost never where you think it is.
2. **Increased complexity**: Optimized code is harder to read, debug, and modify. You pay the complexity tax on every future change.
3. **Wasted time**: Time spent optimizing a function called 10 times is time not spent on features or fixing actual performance problems.

**What Knuth actually meant:**
- Don't optimize before you have working, correct code
- Don't optimize without measuring first (profile, benchmark, then optimize the hot path)
- DO think about algorithmic complexity during design (choosing O(n²) when O(n log n) exists is not "premature" — it's a design mistake)

**The right approach**: Write clear, correct code first → measure performance → identify actual bottlenecks → optimize only those."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "Tell me about" (6 examples) — MISSING PATTERN
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "Tell me about the observer design pattern.",
        "thinking": "This is an explanation request about software design patterns.",
        "response": """The **Observer pattern** defines a one-to-many relationship where an object (the *subject*) notifies all registered dependents (*observers*) when its state changes.

**How it works:**
1. Observers register themselves with the subject
2. When the subject's state changes, it calls `notify()` on all registered observers
3. Each observer updates itself based on the new state

**Common uses:**
- Event systems in UI frameworks (click handlers, DOM events)
- Pub/sub messaging (Redis pub/sub, EventEmitter in Node.js)
- Data binding in reactive frameworks (Vue, React state updates)
- MVC architecture (model notifies views of changes)

**Watch out for:**
- Memory leaks from observers that register but never unregister
- Update cascades where one observer's update triggers another notification
- Threading issues if observers are notified from different threads"""
    },
    {
        "user": "Tell me how rate limiting works in web APIs.",
        "thinking": "This is an explanation request about API infrastructure.",
        "response": """Rate limiting restricts how many requests a client can make to an API within a time window to prevent abuse and ensure fair usage.

**Common algorithms:**
- **Fixed window**: Count requests per fixed interval (e.g., 100/minute). Simple but allows bursts at window boundaries.
- **Sliding window**: Smooths the fixed window by weighting the previous window's count. More accurate.
- **Token bucket**: A bucket fills with tokens at a steady rate. Each request consumes one token. Allows controlled bursts.
- **Leaky bucket**: Requests enter a queue and are processed at a fixed rate. Smoothest output but adds latency.

**Implementation:**
- Tracked per API key, IP address, or user ID
- Usually implemented in a reverse proxy (Nginx), API gateway (Kong), or middleware
- State stored in Redis (fast, atomic INCR + EXPIRE) or in-memory
- Returns `429 Too Many Requests` with `Retry-After` header when limit is exceeded"""
    },
    {
        "user": "Tell me about the differences between OAuth and SAML.",
        "thinking": "This is an explanation request comparing authentication/authorization protocols.",
        "response": """**OAuth 2.0** and **SAML** both handle delegated access, but they serve different use cases and work differently.

**OAuth 2.0:**
- **Purpose**: Authorization (granting access to resources, not proving identity)
- **Format**: JSON-based tokens (access tokens, refresh tokens)
- **Transport**: REST APIs over HTTPS
- **Best for**: Mobile apps, SPAs, third-party API access ("Login with Google")
- **Token type**: Bearer tokens (opaque or JWT)

**SAML 2.0:**
- **Purpose**: Authentication + authorization (proving identity and granting access)
- **Format**: XML-based assertions
- **Transport**: Browser redirects with XML payloads
- **Best for**: Enterprise SSO, corporate identity federation
- **Token type**: Signed XML assertions

| Aspect | OAuth 2.0 | SAML 2.0 |
|--------|-----------|----------|
| Data format | JSON | XML |
| Primary use | API authorization | Enterprise SSO |
| Mobile-friendly | Yes | No (XML is verbose for mobile) |
| Complexity | Moderate | High |

**OIDC (OpenID Connect)** adds an identity layer on top of OAuth 2.0, combining the simplicity of OAuth with authentication — making it the modern alternative to SAML for most new applications."""
    },
    {
        "user": "Tell me about containerization vs virtualization.",
        "thinking": "This is an explanation request comparing infrastructure technologies.",
        "response": """Both containerization and virtualization isolate workloads, but they operate at different levels.

**Virtualization (VMs):**
- Each VM runs a complete guest OS on top of a hypervisor
- Full isolation — separate kernel, drivers, file system
- Heavy resource usage (each VM needs its own OS memory, typically 512MB-4GB+)
- Boot time: minutes
- Examples: VMware, VirtualBox, KVM, Hyper-V

**Containerization:**
- Containers share the host OS kernel and isolate at the process level
- Lightweight — only the application and its dependencies, no guest OS
- Resource usage: megabytes (vs. gigabytes for VMs)
- Boot time: seconds (or milliseconds)
- Examples: Docker, Podman, containerd

**When to use VMs:** Strong isolation requirements (multi-tenant hosting, running different OS versions), legacy applications that need a specific OS environment.

**When to use containers:** Microservices, CI/CD pipelines, rapid scaling, dev/prod parity. Most modern applications use containers unless they specifically need VM-level isolation."""
    },
    {
        "user": "Tell me what CI/CD means and why teams use it.",
        "thinking": "This is an explanation request about DevOps practices.",
        "response": """**CI/CD** stands for Continuous Integration and Continuous Delivery (or Deployment). It automates the process of building, testing, and deploying software.

**Continuous Integration (CI):**
- Developers merge code to the main branch frequently (at least daily)
- Every merge triggers an automated build + test pipeline
- Catches integration bugs early — before they compound
- Tools: GitHub Actions, GitLab CI, Jenkins, CircleCI

**Continuous Delivery (CD):**
- Every change that passes CI is automatically deployable to production
- Deployment requires a manual approval step (one-click deploy)
- Ensures the codebase is always in a releasable state

**Continuous Deployment:**
- Same as delivery, but the deployment step is also automated — no human approval
- Every passing commit goes straight to production
- Requires strong test coverage and feature flags to manage risk

**Why teams use it:**
- Faster feedback loops (know within minutes if a change broke something)
- Smaller, safer deployments (10 small deploys vs. 1 big risky release)
- Reduced manual toil (no more "deploy Friday" rituals)
- Higher confidence in releases (if tests pass, it ships)"""
    },
    {
        "user": "Tell me about connection pooling in databases.",
        "thinking": "This is an explanation request about database performance optimization.",
        "response": """**Connection pooling** maintains a cache of reusable database connections instead of opening and closing a new connection for every query.

**Why it matters:**
- Opening a database connection is expensive: TCP handshake, authentication, SSL negotiation, memory allocation (~5-10ms per connection)
- A web server handling 1000 requests/second without pooling would open/close 1000 connections per second — crushing the database
- With a pool of 20 connections, those 1000 requests share and reuse the same 20 connections

**How it works:**
1. At startup, the pool opens N connections to the database
2. When code needs a connection, it borrows one from the pool
3. When done, it returns the connection to the pool (not closed, just released)
4. If all connections are in use, the request waits or fails (configurable)

**Key settings:**
- **min_pool_size**: Connections kept open even when idle
- **max_pool_size**: Hard limit on concurrent connections (often 10-50)
- **max_idle_time**: Close connections idle longer than this
- **connection_timeout**: How long to wait for a free connection before failing

**Common poolers:** PgBouncer (PostgreSQL), HikariCP (Java), SQLAlchemy pool (Python), Prisma pool (Node.js)."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "Explain" (5 examples) — strengthening existing coverage
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "Explain how OAuth 2.0 works in simple terms.",
        "thinking": "This is an explanation request about authentication protocols.",
        "response": """OAuth 2.0 lets a user grant a third-party app limited access to their data on another service — without sharing their password.

**Analogy:** A hotel gives you a key card that opens your room and the pool, but not other rooms or the staff area. OAuth is like that key card — scoped, temporary, and revocable.

**Flow (Authorization Code grant):**
1. You click "Login with Google" on an app
2. The app redirects you to Google's consent screen
3. You approve: "Yes, let this app see my profile and email"
4. Google redirects you back to the app with an authorization code
5. The app exchanges that code for an access token (server-to-server, not visible to you)
6. The app uses the access token to call Google's API on your behalf

**Key concepts:**
- **Access token**: Short-lived credential (minutes to hours) — the actual "key card"
- **Refresh token**: Long-lived credential used to get new access tokens without re-authenticating
- **Scopes**: Define what the app can access (read email, manage calendar, etc.)

OAuth handles authorization (what you can do), not authentication (who you are). OpenID Connect adds authentication on top."""
    },
    {
        "user": "Explain what a container orchestrator like Kubernetes does.",
        "thinking": "This is an explanation request about container infrastructure.",
        "response": """Kubernetes (K8s) automates the deployment, scaling, and management of containerized applications across a cluster of machines.

**Core problems it solves:**
1. **Scheduling**: Decides which machine runs each container based on resource availability
2. **Self-healing**: Automatically restarts crashed containers and replaces unhealthy nodes
3. **Scaling**: Adds or removes container replicas based on CPU/memory usage or custom metrics
4. **Service discovery**: Containers find each other by name, not IP address (IPs change constantly)
5. **Rolling updates**: Deploys new versions gradually, rolling back automatically if health checks fail

**Key abstractions:**
- **Pod**: Smallest unit — one or more containers sharing network/storage
- **Deployment**: Declares the desired state ("run 3 replicas of my API server")
- **Service**: Stable network endpoint that routes traffic to pods
- **Ingress**: Routes external HTTP traffic to services

**When you need it**: Multiple services, multiple machines, frequent deployments, auto-scaling requirements.
**When you don't**: Single application, single server, small team — Docker Compose is simpler."""
    },
    {
        "user": "Explain the publish-subscribe messaging pattern.",
        "thinking": "This is an explanation request about software architecture patterns.",
        "response": """**Publish-subscribe (pub/sub)** is a messaging pattern where senders (publishers) emit messages to a topic without knowing who will receive them, and receivers (subscribers) listen to topics without knowing who sends them.

**How it works:**
1. A publisher sends a message to a named topic (e.g., "order.created")
2. A message broker (Kafka, RabbitMQ, Redis Pub/Sub, SNS) receives and stores the message
3. All subscribers registered to that topic receive a copy of the message
4. Each subscriber processes the message independently

**Key properties:**
- **Decoupling**: Publishers and subscribers don't know about each other — only the topic name connects them
- **Fan-out**: One message can trigger multiple independent actions (send email, update analytics, notify warehouse)
- **Async**: Publishers don't wait for subscribers to process the message

**Pub/Sub vs. Message Queue:**
- Pub/sub delivers messages to ALL subscribers (broadcast)
- A message queue delivers each message to exactly ONE consumer (work distribution)

**Common uses**: Event-driven architectures, microservice communication, real-time notifications, log aggregation."""
    },
    {
        "user": "Explain the difference between authentication and authorization.",
        "thinking": "This is an explanation request about security concepts.",
        "response": """**Authentication (AuthN)** answers: "Who are you?"
**Authorization (AuthZ)** answers: "What are you allowed to do?"

They are separate concerns that happen in sequence:

1. **Authentication** — Verify identity:
   - Username + password
   - OAuth tokens, API keys
   - Biometrics, hardware keys (FIDO2/WebAuthn)
   - Multi-factor authentication (MFA)

2. **Authorization** — Check permissions:
   - Role-based access control (RBAC): "Admins can delete users, viewers can only read"
   - Attribute-based (ABAC): "Users can edit their own posts but not others'"
   - Policy-based: "Requests from VPN can access internal APIs"

**Analogy**: Authentication is showing your ID at a building entrance. Authorization is your badge only opening doors to your floor.

**Common mistake**: Conflating the two. A system that authenticates every request but never checks permissions is wide open — knowing *who* made a request doesn't mean they should be *allowed* to."""
    },
    {
        "user": "Explain what an API gateway is and why you'd use one.",
        "thinking": "This is an explanation request about microservices infrastructure.",
        "response": """An **API gateway** is a single entry point that sits between clients and your backend services, handling cross-cutting concerns so individual services don't have to.

**What it does:**
- **Routing**: Directs `/users/*` to the user service, `/orders/*` to the order service
- **Authentication**: Validates JWT tokens or API keys before the request reaches any service
- **Rate limiting**: Throttles abusive clients at the edge
- **Request/response transformation**: Converts between protocols (REST→gRPC), aggregates responses from multiple services
- **Monitoring**: Centralized logging, metrics, and tracing for all API traffic

**Why use one:**
- Without a gateway, every service must independently implement auth, rate limiting, CORS, SSL, logging — duplicating logic and increasing attack surface
- Clients talk to one endpoint instead of discovering and managing connections to dozens of services

**When to skip it:**
- Monolith architecture (no services to route between)
- Very simple setups where a reverse proxy (Nginx) handles everything you need

**Common gateways**: Kong, AWS API Gateway, Traefik, Envoy, Apigee."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "What is/are" (5 examples) — strengthening existing
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "What is a deadlock and how do you prevent it?",
        "thinking": "This is an explanation request about concurrency concepts.",
        "response": """A **deadlock** occurs when two or more threads are each waiting for a resource held by the other, creating a circular dependency where none can proceed.

**Example:**
- Thread A holds Lock 1, waiting for Lock 2
- Thread B holds Lock 2, waiting for Lock 1
- Neither can continue → deadlock

**Four necessary conditions** (Coffman conditions — ALL must be true):
1. **Mutual exclusion**: Resources can't be shared
2. **Hold and wait**: A thread holds one resource while waiting for another
3. **No preemption**: Resources can't be forcibly taken from a thread
4. **Circular wait**: A circular chain of threads, each waiting for the next

**Prevention** (break any one condition):
- **Lock ordering**: Always acquire locks in the same global order (breaks circular wait)
- **Lock timeout**: Give up and retry if a lock isn't acquired within a deadline (breaks hold and wait)
- **Try-lock**: Attempt to acquire without blocking, back off if unavailable
- **Reduce locking**: Use lock-free data structures, atomic operations, or message passing"""
    },
    {
        "user": "What is the difference between a stack and a heap in memory?",
        "thinking": "This is an explanation request about computer memory management.",
        "response": """The **stack** and **heap** are two regions of memory used for different purposes during program execution.

**Stack:**
- Stores local variables, function parameters, and return addresses
- LIFO (last in, first out) — grows and shrinks as functions are called and return
- Allocation is instant (just move the stack pointer)
- Fixed size (typically 1-8MB per thread) — stack overflow if exceeded
- Automatically freed when the function returns

**Heap:**
- Stores dynamically allocated data (objects, arrays, anything created with `new`/`malloc`)
- No ordering — allocated and freed in any order
- Allocation is slower (must find a free block, update bookkeeping)
- Much larger than the stack (limited only by system memory)
- Must be manually freed (C/C++) or garbage collected (Java, Python, Go)

| Aspect | Stack | Heap |
|--------|-------|------|
| Speed | Very fast | Slower |
| Size | Small, fixed | Large, flexible |
| Lifetime | Tied to function scope | Manual or GC-managed |
| Fragmentation | None | Can fragment over time |
| Thread safety | Each thread has its own | Shared across threads |"""
    },
    {
        "user": "What are design patterns and why do developers use them?",
        "thinking": "This is an explanation request about software engineering concepts.",
        "response": """**Design patterns** are reusable solutions to common problems in software design. They're not code you copy-paste — they're templates for solving a category of problem.

**Why use them:**
1. **Shared vocabulary**: Saying "use a Factory here" communicates a complete design decision in two words
2. **Proven solutions**: Patterns have been refined over decades — they handle edge cases you might miss
3. **Maintainability**: Code structured around known patterns is easier for new team members to understand

**Three categories** (from the Gang of Four book):
- **Creational**: How objects are created (Singleton, Factory, Builder, Prototype)
- **Structural**: How objects are composed (Adapter, Decorator, Facade, Proxy)
- **Behavioral**: How objects interact (Observer, Strategy, Command, Iterator)

**Caveats:**
- Don't force patterns where they don't fit ("pattern-itis")
- Some patterns exist to work around language limitations (Strategy is just a function in Python/JS)
- Modern languages have built-in features that replace some classic patterns (closures, generics, protocols)

Start by learning the 5-6 most common ones (Singleton, Factory, Observer, Strategy, Decorator, Builder) — they cover the majority of real-world use cases."""
    },
    {
        "user": "What is a CDN and when should you use one?",
        "thinking": "This is an explanation request about web infrastructure.",
        "response": """A **Content Delivery Network (CDN)** is a globally distributed network of servers that caches and serves content from locations geographically close to users.

**How it works:**
1. You configure your CDN provider (Cloudflare, CloudFront, Fastly) with your origin server
2. When a user in Tokyo requests your page, the CDN's Tokyo edge server handles it
3. If the edge has a cached copy → serves immediately (cache hit, ~10ms)
4. If not → fetches from your origin server, caches it, then serves (cache miss, slower first time)

**What to put on a CDN:**
- Static assets: images, CSS, JavaScript, fonts, videos
- HTML pages that don't change per-user
- API responses that are cacheable (product catalogs, public data)

**When to use one:**
- Your users are geographically distributed
- You serve static content (images, JS bundles, videos)
- You need DDoS protection (CDNs absorb attack traffic at the edge)
- You want to reduce load on your origin server

**When you don't need one:**
- All users are in one region and your server is nearby
- All content is dynamic and personalized (though CDNs can cache personalized content with edge computing)"""
    },
    {
        "user": "What are environment variables and why are they used?",
        "thinking": "This is an explanation request about software configuration practices.",
        "response": """**Environment variables** are key-value pairs set outside your application code that configure its behavior at runtime.

**Why use them:**
1. **Separate config from code**: Database URLs, API keys, and feature flags change between environments (dev/staging/prod) — hardcoding them means changing code to deploy
2. **Security**: Secrets (passwords, tokens) should never be committed to version control. Environment variables keep them out of the codebase.
3. **12-Factor App compliance**: The Twelve-Factor methodology mandates storing config in the environment, not in files checked into the repo

**How they work:**
- Set in the shell: `export DATABASE_URL=postgres://localhost/mydb`
- Read in code: `os.environ["DATABASE_URL"]` (Python), `process.env.DATABASE_URL` (Node.js)
- Managed by: `.env` files (local dev), Docker `--env`, Kubernetes ConfigMaps/Secrets, cloud provider settings (Heroku, Vercel, AWS Parameter Store)

**Best practices:**
- Never commit `.env` files to git (add to `.gitignore`)
- Use a `.env.example` with placeholder values so new developers know what's needed
- Validate required env vars at startup — fail fast with a clear error, not a cryptic crash 5 minutes later"""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "Summarize" (3 examples) — strengthening existing
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "Summarize how OAuth 2.0 works in simple terms.",
        "thinking": "This is a summarization request about an authentication protocol.",
        "response": """OAuth 2.0 lets users grant apps limited access to their accounts on other services without sharing passwords.

**In simple terms:**
1. App says: "I need access to your Google data"
2. Google asks you: "Do you approve this app seeing your email and profile?"
3. You click "Allow"
4. Google gives the app a temporary access token (not your password)
5. The app uses that token to read your data — it expires, and you can revoke it anytime

**Key points:**
- The app never sees your password
- Tokens are scoped (the app only gets what you approved — email, not your entire drive)
- Tokens expire — even if stolen, they stop working after a short time
- You can revoke access at any time in your Google/GitHub/etc. security settings

OAuth handles **authorization** ("what can this app do?"), not **authentication** ("who is this user?"). OpenID Connect adds the identity layer on top."""
    },
    {
        "user": "Summarize the key differences between TCP and UDP.",
        "thinking": "This is a summarization request comparing network protocols.",
        "response": """**TCP (Transmission Control Protocol):**
- Connection-oriented — establishes a connection before data transfer (three-way handshake)
- Reliable — guarantees delivery, ordering, and error correction
- Slower due to overhead (acknowledgments, retransmissions, flow control)
- Used for: web browsing (HTTP), email (SMTP), file transfer (FTP), SSH

**UDP (User Datagram Protocol):**
- Connectionless — sends packets without establishing a connection
- Unreliable — no delivery guarantee, no ordering, no retransmission
- Faster and lower overhead (no handshake, no state tracking)
- Used for: video streaming, online gaming, DNS lookups, VoIP

**One-line summary:** TCP is a phone call (reliable, ordered, overhead). UDP is a postcard (fast, no guarantee it arrives)."""
    },
    {
        "user": "Summarize the purpose of Kubernetes in three sentences.",
        "thinking": "This is a brief summarization request about container orchestration.",
        "response": """Kubernetes automates the deployment, scaling, and management of containerized applications across clusters of machines. It ensures your applications stay running by automatically restarting failed containers, scaling replicas based on load, and rolling out updates without downtime. Think of it as an operating system for your data center — you declare the desired state ("run 5 copies of my API"), and Kubernetes continuously works to make reality match that declaration."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "Differences between / Compare" (3 examples) — strengthening
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "What are the key differences between SQL and NoSQL databases?",
        "thinking": "This is an explanation request comparing database paradigms.",
        "response": """**SQL (Relational) databases:**
- Structured, tabular data with predefined schemas
- Strong consistency (ACID transactions)
- Powerful query language (SQL) with JOINs, aggregations, subqueries
- Vertical scaling (scale up one machine)
- Examples: PostgreSQL, MySQL, SQLite, SQL Server

**NoSQL databases** (multiple sub-types):
- **Document** (MongoDB, CouchDB): Schema-flexible JSON/BSON documents
- **Key-Value** (Redis, DynamoDB): Simple key→value lookups, extremely fast
- **Wide-Column** (Cassandra, HBase): Column families, optimized for write-heavy workloads
- **Graph** (Neo4j, ArangoDB): Nodes and edges, optimized for relationship traversal

| Aspect | SQL | NoSQL |
|--------|-----|-------|
| Schema | Fixed, enforced | Flexible, schema-on-read |
| Scaling | Vertical | Horizontal |
| Consistency | Strong (ACID) | Often eventual |
| Querying | Rich (SQL) | Limited (varies by type) |
| Best for | Complex relationships, transactions | High scale, flexible data, simple access patterns |"""
    },
    {
        "user": "Compare gRPC and REST APIs.",
        "thinking": "This is an explanation request comparing API paradigms.",
        "response": """**REST:**
- Uses HTTP/1.1 (typically), JSON payloads
- Human-readable — easy to debug with curl or a browser
- Loose contract — documentation-driven (OpenAPI/Swagger)
- Mature ecosystem, universally supported
- Higher latency and bandwidth usage (JSON is verbose, text-based)

**gRPC:**
- Uses HTTP/2, Protocol Buffers (binary serialization)
- Not human-readable — requires tooling to inspect
- Strict contract — `.proto` files define the API schema, auto-generated client/server code
- Built-in streaming (server, client, and bidirectional)
- Lower latency and bandwidth (Protobuf is 3-10x smaller than JSON)

**When to use REST:** Public-facing APIs, browser clients, simple CRUD, when interoperability and developer experience matter most.

**When to use gRPC:** Internal microservice-to-microservice communication, high-throughput systems, real-time streaming, polyglot environments (auto-generated clients in any language from one `.proto` file).

**Hybrid approach**: Many teams use REST for external APIs and gRPC for internal service mesh communication."""
    },
    {
        "user": "What is the difference between concurrency and parallelism?",
        "thinking": "This is an explanation request about computer science concepts.",
        "response": """**Concurrency** is about *dealing with* multiple things at once. **Parallelism** is about *doing* multiple things at once.

**Concurrency:**
- Structuring a program to handle multiple tasks that can make progress independently
- Tasks may not run simultaneously — they can be interleaved on a single CPU core
- Example: A web server handling 1000 connections on one core by switching between them (async I/O)
- Key tool: async/await, goroutines, event loops

**Parallelism:**
- Actually executing multiple tasks at the exact same time on multiple CPU cores
- Requires multiple physical cores or processors
- Example: A video encoder using all 8 cores to process different frames simultaneously
- Key tool: threads, multiprocessing, SIMD instructions

**Analogy:** A single chef juggling three dishes (switching between them) is concurrent. Three chefs each cooking one dish simultaneously is parallel.

**In practice:** Most real systems use both — concurrent design to structure the workload, parallel execution to speed it up. Go is a great example: goroutines (concurrency) are multiplexed onto OS threads (parallelism) by the runtime."""
    },

    # ═══════════════════════════════════════════════════════════════════
    # Pattern: "List/Describe" + "Give me/overview" (4 examples) — strengthening
    # ═══════════════════════════════════════════════════════════════════
    {
        "user": "List the most common HTTP status codes and what they mean.",
        "thinking": "This is a reference/explanation request about HTTP standards.",
        "response": """**2xx — Success:**
- `200 OK` — Request succeeded, response body contains the result
- `201 Created` — Resource was created (typical response to POST)
- `204 No Content` — Success, but no response body (typical for DELETE)

**3xx — Redirection:**
- `301 Moved Permanently` — Resource has a new URL (update your bookmarks)
- `302 Found` — Temporary redirect (keep using the original URL)
- `304 Not Modified` — Cached version is still valid (no body sent)

**4xx — Client Error:**
- `400 Bad Request` — Malformed request (invalid JSON, missing required field)
- `401 Unauthorized` — Authentication required (no valid credentials provided)
- `403 Forbidden` — Authenticated but not authorized (you don't have permission)
- `404 Not Found` — Resource doesn't exist
- `409 Conflict` — Request conflicts with current state (e.g., duplicate resource)
- `429 Too Many Requests` — Rate limited

**5xx — Server Error:**
- `500 Internal Server Error` — Unhandled exception on the server
- `502 Bad Gateway` — Proxy/load balancer got an invalid response from upstream
- `503 Service Unavailable` — Server is overloaded or in maintenance
- `504 Gateway Timeout` — Upstream server didn't respond in time"""
    },
    {
        "user": "Describe the MVC architecture pattern.",
        "thinking": "This is an explanation request about software architecture patterns.",
        "response": """**MVC (Model-View-Controller)** separates an application into three interconnected layers:

**Model:**
- Manages data, business logic, and rules
- Interacts with the database
- Notifies the View when data changes
- Example: A `User` class with methods like `save()`, `validate()`, `find_by_email()`

**View:**
- Presents data to the user (UI)
- Receives data from the Model and renders it
- Contains no business logic — only display logic
- Example: An HTML template that renders a list of users

**Controller:**
- Handles user input (HTTP requests, button clicks)
- Mediates between Model and View
- Receives input → calls Model → selects View → returns response
- Example: A route handler that processes a form submission

**Flow:** User action → Controller → Model (update data) → View (render result) → User sees output

**Variants:**
- **MVP (Model-View-Presenter)**: Presenter replaces Controller, has a direct reference to the View
- **MVVM (Model-View-ViewModel)**: ViewModel exposes data via bindings (used in React, Vue, WPF)

MVC is used in Rails, Django, Spring MVC, Laravel, ASP.NET MVC — virtually every server-side web framework."""
    },
    {
        "user": "Give me a quick overview of how Git branching works.",
        "thinking": "This is an overview/explanation request about version control.",
        "response": """Git branches are lightweight pointers to commits that let you develop features, fixes, and experiments in isolation from the main codebase.

**Core concepts:**
- A **branch** is just a pointer to a specific commit (stored as a 40-char SHA in a file — nearly zero cost to create)
- `main` (or `master`) is the default branch — it's not special, just a convention
- **HEAD** points to your current branch (and therefore your current commit)

**Common workflow:**
1. `git checkout -b feature/login` — Create and switch to a new branch
2. Make commits on the feature branch (main is unaffected)
3. `git checkout main && git merge feature/login` — Merge changes back
4. `git branch -d feature/login` — Delete the branch (it's merged, no longer needed)

**Merge vs. Rebase:**
- **Merge**: Creates a merge commit that combines two branches. Preserves full history.
- **Rebase**: Replays your commits on top of the target branch. Creates a linear history but rewrites commit hashes.

**Branching strategies:**
- **GitHub Flow**: One main branch + short-lived feature branches + pull requests
- **Git Flow**: main + develop + feature + release + hotfix branches (more structured)
- **Trunk-based**: Everyone commits to main, uses feature flags instead of long-lived branches"""
    },
    {
        "user": "Give me a brief explanation of how caching works in web applications.",
        "thinking": "This is an overview/explanation request about web performance optimization.",
        "response": """Caching stores copies of frequently accessed data in faster storage layers so you don't have to recompute or re-fetch it every time.

**Cache layers (from closest to user to farthest):**
1. **Browser cache**: Static assets (CSS, JS, images) cached locally based on `Cache-Control` headers
2. **CDN cache**: Content cached at edge servers geographically close to users
3. **Application cache**: In-memory stores (Redis, Memcached) for computed results, sessions, API responses
4. **Database cache**: Query result cache, buffer pool (InnoDB automatically caches frequently read pages)

**Cache strategies:**
- **Cache-aside (lazy loading)**: Check cache → miss → fetch from DB → write to cache → return. Most common.
- **Write-through**: Write to cache AND database simultaneously. Slower writes, but cache is always current.
- **Write-behind**: Write to cache, asynchronously sync to database. Fast writes, risk of data loss.
- **TTL (Time-to-Live)**: Entries expire after a set time. Simple, but stale data is possible.

**Cache invalidation** ("the two hardest problems in CS"):
- When the underlying data changes, the cached version becomes stale
- Solutions: TTL expiry, event-driven invalidation (publish a "user.updated" event), versioned cache keys"""
    },
]

def build_jsonl_entry(user_prompt, thinking, response):
    return {
        "messages": [
            {"role": "system", "content": "You are Nova, an elite coding assistant."},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": f"<<THINKING>>\n{thinking}\n\n<<RESPONSE>>\n{response}"}
        ]
    }


def main():
    # Read existing dataset
    src = "/Users/ashishsingh/Desktop/nova-1.5b/dataset_nova3b_v8.jsonl"
    dst = "/Users/ashishsingh/Desktop/nova-1.5b/dataset_nova3b_v9.jsonl"

    # Copy v8 → v9
    shutil.copy2(src, dst)
    print(f"Copied {src} → {dst}")

    # Append new examples
    with open(dst, "a") as f:
        for ex in EXAMPLES:
            entry = build_jsonl_entry(ex["user"], ex["thinking"], ex["response"])
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Count results
    total = 0
    files_count = 0
    clarification_count = 0
    response_count = 0

    with open(dst, "r") as f:
        for line in f:
            total += 1
            d = json.loads(line.strip())
            asst = ""
            for m in d.get("messages", []):
                if m["role"] == "assistant":
                    asst = m["content"]
            if "<<RESPONSE>>" in asst:
                response_count += 1
            elif "<<CLARIFICATION>>" in asst:
                clarification_count += 1
            elif "<<FILES>>" in asst:
                files_count += 1

    print(f"\nDataset v9 stats:")
    print(f"  Total examples: {total}")
    print(f"  <<FILES>>:         {files_count} ({files_count/total*100:.1f}%)")
    print(f"  <<CLARIFICATION>>: {clarification_count} ({clarification_count/total*100:.1f}%)")
    print(f"  <<RESPONSE>>:      {response_count} ({response_count/total*100:.1f}%)")
    print(f"  FILES:RESPONSE ratio: {files_count/max(response_count,1):.1f}:1")
    print(f"\n  New examples added: {len(EXAMPLES)}")


if __name__ == "__main__":
    main()
