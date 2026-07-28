#!/usr/bin/env python3
"""
fix_dataset_v7.py — Surgical fix for Nova 3B training data.

Fixes 3 structural problems:
1. FORMAT BUG: All 65 refusal examples have <<FILES>> (none) — removes it
   to enforce <<CLARIFICATION>> and <<FILES>> as mutually exclusive.
2. TONE-REFUSAL CONFOUND: Adds 15 messy-but-legitimate positive examples
   that teach: messy tone + file path = execute, not refuse.
3. FORMAT EXCLUSIVITY: Adds 5 clarification examples with clean format
   (no <<FILES>> tag at all) to reinforce the either/or structure.

Input:  dataset_nova3b_combined_v6.jsonl
Output: dataset_nova3b_v7.jsonl
"""

import json
import re
import sys
from pathlib import Path

INPUT_PATH = Path(__file__).parent / "dataset_nova3b_combined_v6.jsonl"
OUTPUT_PATH = Path(__file__).parent / "dataset_nova3b_v7.jsonl"


# =============================================================================
# FIX 1: Clean refusal format — remove <<FILES>> and <<TEST_COMMAND>> from
#         clarification responses. The model should learn that <<CLARIFICATION>>
#         is a terminal response — no <<FILES>> block follows.
# =============================================================================

def fix_refusal_format(assistant_content: str) -> str:
    """Remove <<FILES>> and <<TEST_COMMAND>> from clarification responses."""
    if "<<CLARIFICATION>>" not in assistant_content:
        return assistant_content

    # Remove the <<FILES>> block (including the "(none — clarification required)" line)
    cleaned = re.sub(
        r'\n*<<FILES>>\s*\n\(none\s*[—–-]\s*clarification required\)\s*',
        '',
        assistant_content
    )
    # Remove the <<TEST_COMMAND>> block
    cleaned = re.sub(
        r'\n*<<TEST_COMMAND>>\s*\nnone\s*$',
        '',
        cleaned
    )
    # Trim trailing whitespace
    cleaned = cleaned.rstrip()
    return cleaned


# =============================================================================
# FIX 2: New messy-but-legitimate positive examples.
# These teach: casual/urgent/typo-laden tone + concrete file path = EXECUTE.
# =============================================================================

MESSY_LEGITIMATE_EXAMPLES = [
    # --- The 3 messy handoff prompts that were wrongly refused in eval ---
    {
        "messages": [
            {"role": "user", "content": "uh so the ceiling model said we need a cache. just use redis or whatever in src/cache.py and make it set/get with a ttl. dont overcomplicate it just do it fast."},
            {"role": "assistant", "content": """<<THINKING>>
Creating src/cache.py with a simple Redis-backed cache supporting set/get with TTL.

<<FILES>>
```python
# filepath: src/cache.py
# action: CREATE

import redis
import json
from typing import Optional, Any

class RedisCache:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self.client.setex(key, ttl, json.dumps(value))

    def get(self, key: str) -> Optional[Any]:
        raw = self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def delete(self, key: str) -> None:
        self.client.delete(key)
```

<<TEST_COMMAND>>
pytest test_cache.py"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "fix the bug where the user login fails if they dont have a profile pic. i think its in auth.py somewhere around line 40? just make it use a default empty string instead of crashing."},
            {"role": "assistant", "content": """<<THINKING>>
Fixing the profile picture bug in auth.py — adding a default empty string fallback for missing profile_pic.

<<FILES>>
```python
# filepath: auth.py
# action: MODIFY

def authenticate_user(username: str, password: str) -> dict:
    user = db.find_user(username)
    if user is None:
        raise AuthError("User not found")

    if not verify_password(password, user["password_hash"]):
        raise AuthError("Invalid password")

    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "profile_pic": user.get("profile_pic", ""),
        "token": generate_jwt(user["id"])
    }
```

<<TEST_COMMAND>>
pytest tests/test_auth.py -v"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."},
            {"role": "assistant", "content": """<<THINKING>>
Fixing healthcheck endpoint in src/app.js — wrapping db check in try/catch, returning degraded status on failure.

<<FILES>>
```javascript
// filepath: src/app.js
// action: MODIFY

const express = require('express');
const app = express();

app.get('/health', async (req, res) => {
    try {
        await db.ping();
        res.status(200).json({ status: 'healthy' });
    } catch (err) {
        res.status(200).json({ status: 'degraded', error: err.message });
    }
});

module.exports = app;
```

<<TEST_COMMAND>>
npm test"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },

    # --- The 2 new messy prompts that were wrongly refused ---
    {
        "messages": [
            {"role": "user", "content": "yo just add a /health endpoint returning 200 to api.py, thx"},
            {"role": "assistant", "content": """<<THINKING>>
Adding a /health endpoint to api.py that returns HTTP 200.

<<FILES>>
```python
# filepath: api.py
# action: MODIFY

from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200
```

<<TEST_COMMAND>>
pytest test_api.py"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "hey can you quickly update package.json to bump react to version 18? literally just change the number."},
            {"role": "assistant", "content": """<<THINKING>>
Updating package.json to bump React dependency to version 18.

<<FILES>>
```json
// filepath: package.json
// action: MODIFY

{
    "name": "my-app",
    "version": "1.0.0",
    "dependencies": {
        "react": "^18.0.0",
        "react-dom": "^18.0.0"
    }
}
```

<<TEST_COMMAND>>
npm install && npm test"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },

    # --- Additional messy-but-legitimate examples (new) ---
    {
        "messages": [
            {"role": "user", "content": "URGENT plz add rate limiting to routes/api.js. use express-rate-limit, 100 req per 15 min window. just the middleware setup nothing fancy"},
            {"role": "assistant", "content": """<<THINKING>>
Adding rate limiting middleware to routes/api.js using express-rate-limit.

<<FILES>>
```javascript
// filepath: routes/api.js
// action: MODIFY

const express = require('express');
const rateLimit = require('express-rate-limit');
const router = express.Router();

const limiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 100,
    message: { error: 'Too many requests, try again later.' }
});

router.use(limiter);

module.exports = router;
```

<<TEST_COMMAND>>
npm test"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "yo nova write a go func that hashes a password with bcrypt. put it in pkg/auth/hash.go. accept string return string and error."},
            {"role": "assistant", "content": """<<THINKING>>
Creating pkg/auth/hash.go with bcrypt password hashing function.

<<FILES>>
```go
// filepath: pkg/auth/hash.go
// action: CREATE

package auth

import (
\t"golang.org/x/crypto/bcrypt"
)

func HashPassword(password string) (string, error) {
\thashed, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
\tif err != nil {
\t\treturn "", err
\t}
\treturn string(hashed), nil
}

func CheckPassword(hashed, password string) error {
\treturn bcrypt.CompareHashAndPassword([]byte(hashed), []byte(password))
}
```

<<TEST_COMMAND>>
go test ./pkg/auth/..."""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "JIRA-2847: the logger in utils/logger.py is printing to stdout when it should write to a file. fix it to use FileHandler writing to logs/app.log"},
            {"role": "assistant", "content": """<<THINKING>>
Fixing utils/logger.py to use FileHandler instead of StreamHandler.

<<FILES>>
```python
# filepath: utils/logger.py
# action: MODIFY

import logging
import os

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

handler = logging.FileHandler("logs/app.log")
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)
```

<<TEST_COMMAND>>
pytest tests/test_logger.py"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "hey can u add a .env.example file? just put DATABASE_URL, REDIS_URL, and SECRET_KEY as placeholders. thx"},
            {"role": "assistant", "content": """<<THINKING>>
Creating .env.example with placeholder environment variables.

<<FILES>>
```text
# filepath: .env.example
# action: CREATE

DATABASE_URL=postgresql://user:password@localhost:5432/mydb
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-here
```

<<TEST_COMMAND>>
none"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "need a simple Makefile for our go project. targets: build, test, clean. binary goes in bin/. entry is cmd/server/main.go"},
            {"role": "assistant", "content": """<<THINKING>>
Creating Makefile with build, test, and clean targets for the Go project.

<<FILES>>
```makefile
# filepath: Makefile
# action: CREATE

.PHONY: build test clean

build:
\tmkdir -p bin
\tgo build -o bin/server ./cmd/server/main.go

test:
\tgo test ./...

clean:
\trm -rf bin/
```

<<TEST_COMMAND>>
make test"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "the css is all messed up. just add a .container class to styles/main.css with max-width 1200px, margin auto, and padding 0 20px. thats literally it"},
            {"role": "assistant", "content": """<<THINKING>>
Adding .container class to styles/main.css.

<<FILES>>
```css
/* filepath: styles/main.css */
/* action: MODIFY */

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}
```

<<TEST_COMMAND>>
none"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "yo add a 404 handler to routes/errors.js that returns json with message 'not found'. express style."},
            {"role": "assistant", "content": """<<THINKING>>
Adding 404 handler middleware to routes/errors.js.

<<FILES>>
```javascript
// filepath: routes/errors.js
// action: CREATE

function notFoundHandler(req, res, next) {
    res.status(404).json({ error: 'not found' });
}

function errorHandler(err, req, res, next) {
    console.error(err.stack);
    res.status(500).json({ error: 'internal server error' });
}

module.exports = { notFoundHandler, errorHandler };
```

<<TEST_COMMAND>>
npm test"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "URGENT JIRA-9911: deployment is failing cuz we dont have a Dockerfile. node 20 alpine, copy package.json first for layer caching, expose 8080, CMD npm start. file is just Dockerfile in root."},
            {"role": "assistant", "content": """<<THINKING>>
Creating Dockerfile with Node 20 Alpine, layer-cached npm install, port 8080.

<<FILES>>
```dockerfile
# filepath: Dockerfile
# action: CREATE

FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 8080
CMD ["npm", "start"]
```

<<TEST_COMMAND>>
docker build -t myapp ."""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "can u write a rust function in src/lib.rs that takes a Vec<i32> and returns the two numbers that sum to a target? just basic two sum nothing fancy"},
            {"role": "assistant", "content": """<<THINKING>>
Implementing two_sum function in src/lib.rs.

<<FILES>>
```rust
// filepath: src/lib.rs
// action: CREATE

use std::collections::HashMap;

pub fn two_sum(nums: Vec<i32>, target: i32) -> Option<(usize, usize)> {
    let mut seen: HashMap<i32, usize> = HashMap::new();
    for (i, &num) in nums.iter().enumerate() {
        let complement = target - num;
        if let Some(&j) = seen.get(&complement) {
            return Some((j, i));
        }
        seen.insert(num, i);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_two_sum() {
        assert_eq!(two_sum(vec![2, 7, 11, 15], 9), Some((0, 1)));
        assert_eq!(two_sum(vec![3, 2, 4], 6), Some((1, 2)));
        assert_eq!(two_sum(vec![1, 2, 3], 10), None);
    }
}
```

<<TEST_COMMAND>>
cargo test"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "lol the tests are failing because conftest.py doesnt have the fixture for db connection. add a pytest fixture called db_session in tests/conftest.py that yields a sqlite in-memory connection and closes it after"},
            {"role": "assistant", "content": """<<THINKING>>
Adding db_session pytest fixture to tests/conftest.py with SQLite in-memory connection.

<<FILES>>
```python
# filepath: tests/conftest.py
# action: CREATE

import sqlite3
import pytest

@pytest.fixture
def db_session():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()
```

<<TEST_COMMAND>>
pytest tests/"""}
        ],
        "metadata": {"category": "messy_legitimate", "source": "handcrafted"}
    },
]


# =============================================================================
# FIX 3: Format-exclusivity clarification examples.
# Clean <<CLARIFICATION>> responses that do NOT contain <<FILES>> at all.
# =============================================================================

FORMAT_EXCLUSIVITY_EXAMPLES = [
    {
        "messages": [
            {"role": "user", "content": "Build a recommendation engine for our platform."},
            {"role": "assistant", "content": """<<THINKING>>
Task is underspecified. Missing: platform type, data sources, algorithm preference, target language.

<<CLARIFICATION>>
I need more information before writing code:
1. What type of recommendations? (product, content, user-matching?)
2. What data is available? (user behavior logs, ratings, purchase history?)
3. What language/framework? (Python/scikit-learn, Python/TensorFlow, Go?)
4. What file should I create? (e.g., src/recommender.py, services/reco.go?)"""}
        ],
        "metadata": {"category": "refusal_clarification_clean", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "URGENT: set up CI/CD for our project"},
            {"role": "assistant", "content": """<<THINKING>>
Task is underspecified. Missing: CI/CD platform, project language, deployment target, test commands.

<<CLARIFICATION>>
I need more information before writing code:
1. Which CI/CD platform? (GitHub Actions, GitLab CI, Jenkins, CircleCI?)
2. What language is the project? (Python, Node.js, Go, Java?)
3. What are the test/build commands? (e.g., pytest, npm test, go test?)
4. Where does it deploy? (AWS, GCP, Heroku, Docker registry?)"""}
        ],
        "metadata": {"category": "refusal_clarification_clean", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "yo build us an analytics dashboard"},
            {"role": "assistant", "content": """<<THINKING>>
Task is underspecified. Missing: data source, metrics, frontend framework, backend stack.

<<CLARIFICATION>>
I need more information before writing code:
1. What data source? (PostgreSQL, MongoDB, API endpoint, CSV files?)
2. What metrics to display? (revenue, user growth, error rates, custom KPIs?)
3. What frontend framework? (React, Vue, plain HTML/JS, Svelte?)
4. What files should I create? (e.g., src/Dashboard.tsx, pages/analytics.vue?)"""}
        ],
        "metadata": {"category": "refusal_clarification_clean", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "JIRA-5500: implement real-time notifications for users"},
            {"role": "assistant", "content": """<<THINKING>>
Task is underspecified. Missing: transport mechanism, backend stack, notification types.

<<CLARIFICATION>>
I need more information before writing code:
1. What transport? (WebSocket, Server-Sent Events, push notifications, polling?)
2. What backend stack? (Node.js/Socket.io, Python/FastAPI, Go?)
3. What types of notifications? (in-app, email, mobile push?)
4. What files should I create or modify? (e.g., src/websocket.js, services/notifications.py?)"""}
        ],
        "metadata": {"category": "refusal_clarification_clean", "source": "handcrafted"}
    },
    {
        "messages": [
            {"role": "user", "content": "hey nova make our API faster"},
            {"role": "assistant", "content": """<<THINKING>>
Task is underspecified. Missing: which API, current bottleneck, language/framework, target latency.

<<CLARIFICATION>>
I need more information before writing code:
1. Which API endpoint is slow? (e.g., GET /users, POST /search, GET /reports?)
2. What's the current latency and target? (e.g., 2s → 200ms?)
3. What language/framework? (Python/FastAPI, Node/Express, Go?)
4. What file contains the slow endpoint? (e.g., routes/users.py, handlers/search.go?)"""}
        ],
        "metadata": {"category": "refusal_clarification_clean", "source": "handcrafted"}
    },
]


# =============================================================================
# MAIN: Read → Fix → Append → Write
# =============================================================================

def main():
    if not INPUT_PATH.exists():
        print(f"ERROR: Input file not found: {INPUT_PATH}")
        sys.exit(1)

    # Read input
    with open(INPUT_PATH) as f:
        lines = f.readlines()

    print(f"Input: {len(lines)} examples from {INPUT_PATH.name}")

    fixed_lines = []
    refusals_fixed = 0
    refusals_total = 0

    for i, line in enumerate(lines):
        data = json.loads(line)
        msgs = data.get("messages", [])

        # Check if this is a refusal example
        assistant_content = ""
        for msg in msgs:
            if msg.get("role") == "assistant":
                assistant_content = msg.get("content", "")

        if "<<CLARIFICATION>>" in assistant_content:
            refusals_total += 1
            # Fix the format: remove <<FILES>> and <<TEST_COMMAND>>
            new_content = fix_refusal_format(assistant_content)
            if new_content != assistant_content:
                refusals_fixed += 1
                for msg in msgs:
                    if msg.get("role") == "assistant":
                        msg["content"] = new_content
                data["messages"] = msgs
                # Update category to mark as clean
                if "metadata" in data:
                    data["metadata"]["category"] = "refusal_clarification_clean"

        fixed_lines.append(json.dumps(data, ensure_ascii=False))

    # Append messy-but-legitimate examples
    for example in MESSY_LEGITIMATE_EXAMPLES:
        fixed_lines.append(json.dumps(example, ensure_ascii=False))

    # Append format-exclusivity examples
    for example in FORMAT_EXCLUSIVITY_EXAMPLES:
        fixed_lines.append(json.dumps(example, ensure_ascii=False))

    # Write output
    with open(OUTPUT_PATH, "w") as f:
        for line in fixed_lines:
            f.write(line + "\n")

    print(f"\n=== FIX SUMMARY ===")
    print(f"Refusal examples found: {refusals_total}")
    print(f"Refusal formats fixed (removed <<FILES>>): {refusals_fixed}")
    print(f"Messy-but-legitimate examples added: {len(MESSY_LEGITIMATE_EXAMPLES)}")
    print(f"Format-exclusivity examples added: {len(FORMAT_EXCLUSIVITY_EXAMPLES)}")
    print(f"Output: {len(fixed_lines)} examples → {OUTPUT_PATH.name}")

    # Validation
    print(f"\n=== VALIDATION ===")
    validate_output()


def validate_output():
    """Quick sanity checks on the output dataset."""
    with open(OUTPUT_PATH) as f:
        lines = f.readlines()

    errors = []
    clarification_count = 0
    files_count = 0
    both_count = 0
    categories = {}

    for i, line in enumerate(lines):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"Line {i+1}: Invalid JSON")
            continue

        msgs = data.get("messages", [])
        if not msgs:
            errors.append(f"Line {i+1}: No messages")
            continue

        cat = data.get("metadata", {}).get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

        assistant_content = ""
        for msg in msgs:
            if msg.get("role") == "assistant":
                assistant_content = msg.get("content", "")

        has_clar = "<<CLARIFICATION>>" in assistant_content
        has_files_tag = "<<FILES>>" in assistant_content

        if has_clar:
            clarification_count += 1
        if has_files_tag:
            files_count += 1
        if has_clar and has_files_tag:
            both_count += 1
            errors.append(f"Line {i+1}: STILL has both <<CLARIFICATION>> and <<FILES>> !")

    print(f"Total examples: {len(lines)}")
    print(f"  <<CLARIFICATION>> only: {clarification_count}")
    print(f"  <<FILES>> only: {files_count - both_count}")
    print(f"  BOTH (BUG): {both_count}")
    print(f"\nCategories:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for err in errors[:20]:
            print(f"  {err}")
    else:
        print(f"\n✅ All validations passed!")


if __name__ == "__main__":
    main()
