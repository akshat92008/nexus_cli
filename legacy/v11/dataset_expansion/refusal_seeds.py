#!/usr/bin/env python3
"""
dataset_expansion/refusal_seeds.py — Hand-authored Refusal/Clarification Seed Examples

These are the 10 gold-standard seed examples for Category A (Refusal/Clarification).
Each example is a (prompt, response) pair where the CORRECT output is NOT code —
it's a structured <<CLARIFICATION>> block asking for missing specifics.

HUMAN REVIEW REQUIRED:
  These 10 examples define the refusal format. Review them before generating
  the full ~50–75 batch. Once approved, run generate_refusal_examples.py.

Format contract:
  - <<THINKING>> block: short, identifies what's missing
  - <<CLARIFICATION>> block: numbered list of specific, concrete questions
  - <<FILES>>: always "(none — clarification required)"
  - <<TEST_COMMAND>>: always "none"

Part of the Nova model family by Amaura.
"""

# ─── Seed Examples ─────────────────────────────────────────────────────────────
# Each entry: {"prompt": str, "response": str, "missing": [str], "domain": str}

REFUSAL_SEEDS = [

    # ── 1. Backend architecture — missing stack, scale, auth ──────────────────
    {
        "domain": "backend",
        "missing": ["stack", "scale", "auth method"],
        "prompt": "Build a scalable backend for a food delivery app.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: backend stack, scale target, auth method, deployment environment.

<<CLARIFICATION>>
I need more information before writing code:
1. What backend language/framework? (Python/FastAPI, Node/Express, Go/Gin, etc.)
2. What scale? (single-server prototype, or horizontally scalable with load balancer?)
3. Authentication method? (JWT, OAuth2, API key, session-based?)
4. Which specific files should I create? (e.g., routes/orders.py, models/user.py)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 2. ML pipeline — missing data source, model type, target metric ───────
    {
        "domain": "ml",
        "missing": ["data source", "model type", "target metric"],
        "prompt": "Create a machine learning pipeline that predicts customer churn.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: data format, model type, evaluation metric, specific files to create.

<<CLARIFICATION>>
I need more information before writing code:
1. What is the input data format? (CSV with which columns? pandas DataFrame schema?)
2. Which model type? (logistic regression, random forest, XGBoost, neural network?)
3. What evaluation metric matters most? (AUC-ROC, F1, precision at a recall threshold?)
4. What file should I create? (e.g., src/pipeline.py, notebooks/churn_model.ipynb?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 3. Auth system — missing protocol, storage, language ──────────────────
    {
        "domain": "security",
        "missing": ["auth protocol", "token storage", "language"],
        "prompt": "Implement a secure authentication system for our app.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: auth protocol, token storage strategy, target language/framework.

<<CLARIFICATION>>
I need more information before writing code:
1. What auth protocol? (JWT, OAuth2, session cookies, API keys, or SAML?)
2. Where are tokens stored? (Redis, database, in-memory, client-side localStorage?)
3. What language and framework? (Python/FastAPI, Node/Express, Go?)
4. What file(s) should I create? (e.g., src/auth/jwt.py, middleware/auth.go?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 4. Database design — missing entity model, scale, engine ──────────────
    {
        "domain": "database",
        "missing": ["entity model", "scale", "DB engine"],
        "prompt": "Design the database schema for a social network.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: entity relationships, scale target, database engine choice.

<<CLARIFICATION>>
I need more information before writing code:
1. What are the core entities? (Users, Posts, Comments, Likes, Follows — which ones?)
2. What database engine? (PostgreSQL, MySQL, MongoDB, DynamoDB?)
3. What scale? (thousands of users for an MVP, or millions with sharding?)
4. What should I output? (SQL migration file, ORM model file, or ERD diagram?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 5. Microservice architecture — missing service boundary definition ─────
    {
        "domain": "architecture",
        "missing": ["service boundaries", "transport protocol", "specific files"],
        "prompt": "Set up a microservices architecture for an e-commerce platform.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: which services to create, transport protocol, specific file targets.

<<CLARIFICATION>>
I need more information before writing code:
1. Which services do you need? (e.g., user-service, product-service, order-service, payment-service?)
2. How do services communicate? (REST/HTTP, gRPC, message queue like Kafka/RabbitMQ?)
3. What language per service? (all Python, all Go, mixed?)
4. Which specific files should I create first? (e.g., user-service/main.py, docker-compose.yml?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 6. Real-time feature — missing transport, latency SLA, infra ──────────
    {
        "domain": "realtime",
        "missing": ["transport", "latency SLA", "infra target"],
        "prompt": "Add real-time messaging to our platform.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: transport protocol, latency requirement, infrastructure target.

<<CLARIFICATION>>
I need more information before writing code:
1. What transport? (WebSocket, Server-Sent Events, long-polling, or a service like Pusher/Ably?)
2. What latency is acceptable? (< 100ms, < 1s, best-effort?)
3. What's the server environment? (Node.js, Python ASGI, Go?)
4. What file should I create? (e.g., src/websocket_handler.py, routes/chat.js?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 7. Vague refactor — no concrete scope given ────────────────────────────
    {
        "domain": "refactor",
        "missing": ["which module", "target language", "specific files"],
        "prompt": "Refactor the codebase to be more modular.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: which module or file to refactor, target structure, specific files.

<<CLARIFICATION>>
I need more information before writing code:
1. Which specific file or module should I refactor? (e.g., src/app.py, routes/api.js?)
2. What is the target structure? (e.g., split into 3 files: models.py, routes.py, utils.py?)
3. Are there any files I should NOT touch?
4. What language is this? (Python, JavaScript, Go, TypeScript?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 8. Monitoring / observability — missing stack, metrics, storage ────────
    {
        "domain": "infra",
        "missing": ["observability stack", "metrics to collect", "storage backend"],
        "prompt": "Add monitoring and observability to our system.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: observability stack, which metrics to collect, storage backend.

<<CLARIFICATION>>
I need more information before writing code:
1. What observability stack? (Prometheus + Grafana, Datadog, OpenTelemetry, CloudWatch?)
2. What metrics matter? (latency, error rate, throughput, custom business metrics?)
3. What language is the service I should instrument? (Python, Go, Node?)
4. Which file should I modify or create? (e.g., src/metrics.py, middleware/tracing.go?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 9. Messy/urgent but still vague — tone variation ──────────────────────
    {
        "domain": "backend",
        "missing": ["stack", "specific endpoint", "auth"],
        "prompt": "URGENT: we need an API for the mobile app asap. make it secure",
        "response": """\
<<THINKING>>
Task is underspecified despite urgency. Missing: backend stack, which endpoints, auth method.

<<CLARIFICATION>>
I need more information before writing code:
1. What backend language/framework? (Python/FastAPI, Node/Express, Go?)
2. Which endpoint(s) should I implement? (e.g., POST /auth/login, GET /users/{id}?)
3. What auth should I use? (JWT, OAuth2, API key?)
4. What file should I create or modify? (e.g., src/api.py, routes/mobile.js?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

    # ── 10. Blockchain/Web3 — abstract and unscoped ───────────────────────────
    {
        "domain": "web3",
        "missing": ["chain", "contract scope", "language", "files"],
        "prompt": "Create a decentralized authentication system using blockchain.",
        "response": """\
<<THINKING>>
Task is underspecified. Missing: target blockchain, smart contract scope, language, file targets.

<<CLARIFICATION>>
I need more information before writing code:
1. Which blockchain? (Ethereum/Solidity, Solana/Rust, Polygon, or a permissioned chain?)
2. What specifically should the smart contract do? (store identity hashes, verify signatures, issue tokens?)
3. What's the off-chain component? (Node.js backend, Python, Rust CLI?)
4. Which files should I create? (e.g., contracts/Auth.sol, scripts/deploy.js, src/auth_client.py?)

<<FILES>>
(none — clarification required)

<<TEST_COMMAND>>
none""",
    },

]


def to_jsonl_entry(seed: dict) -> dict:
    """Convert a seed to a training JSONL entry in the Nova format."""
    return {
        "messages": [
            {"role": "user", "content": seed["prompt"]},
            {"role": "assistant", "content": seed["response"]},
        ],
        "metadata": {
            "category": "refusal_clarification",
            "domain": seed["domain"],
            "missing_info": seed["missing"],
            "version": "v1_seed",
        }
    }


if __name__ == "__main__":
    import json

    print(f"Refusal Seed Examples ({len(REFUSAL_SEEDS)} total)")
    print("=" * 70)
    for i, seed in enumerate(REFUSAL_SEEDS, 1):
        print(f"\n[{i}] Domain: {seed['domain']} | Missing: {seed['missing']}")
        print(f"PROMPT: {seed['prompt']}")
        print(f"RESPONSE (first 200 chars): {seed['response'][:200]}...")
        print()

    # Emit as JSONL to stdout for preview
    print("\n" + "=" * 70)
    print("JSONL format preview (first 3):")
    for seed in REFUSAL_SEEDS[:3]:
        print(json.dumps(to_jsonl_entry(seed)))
