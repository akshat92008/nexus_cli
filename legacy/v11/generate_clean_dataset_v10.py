import json

base_file = "dataset_nova3b_v9.jsonl"
with open(base_file, "r") as f:
    base_data = [json.loads(line) for line in f]

print(f"Base dataset count (v9): {len(base_data)}")

# 50 Out-of-Distribution Casual Phrasing + Constraint Examples (Issue 1)
# Zero overlap with: auth profile_pic, healthcheck, retry logic, payment 402, worker timeout
ood_templates = [
    # Domain 1: Rate Limiting (JS / Express)
    {
        "prompt": "hey quick fix on rate limiter in src/middleware/rate_limit.js around line 45. if client hits limit, make it return 429 status code with message 'Rate Limit Exceeded'.",
        "file": "src/middleware/rate_limit.js", "lang": "javascript", "comment": "//",
        "search": "if (requests > MAX_REQUESTS) {\n    return res.status(500).json({ error: 'error' });\n}",
        "replace": "if (requests > MAX_REQUESTS) {\n    return res.status(429).json({ error: 'Rate Limit Exceeded' });\n}",
        "think": "Updating rate limiter in src/middleware/rate_limit.js to return 429 with 'Rate Limit Exceeded'."
    },
    # Domain 2: Session Validation (Python / FastAPI)
    {
        "prompt": "session check in src/auth/session.py line 60 is broken. if session token is expired, return 401 status and detail 'Session Expired'.",
        "file": "src/auth/session.py", "lang": "python", "comment": "#",
        "search": "def validate_session(session):\n    if session.is_expired():\n        raise HTTPException(status_code=500, detail='invalid')",
        "replace": "def validate_session(session):\n    if session.is_expired():\n        raise HTTPException(status_code=401, detail='Session Expired')",
        "think": "Updating session validator in src/auth/session.py to return 401 with 'Session Expired'."
    },
    # Domain 3: Database Connection Pool (Go)
    {
        "prompt": "fix db pool error in src/db/connection.go at line 30. when pool exhaustion happens print 'Max Connections Reached' and return err.",
        "file": "src/db/connection.go", "lang": "go", "comment": "//",
        "search": "if pool.Active >= pool.Max {\n    return errors.New(\"failed\")\n}",
        "replace": "if pool.Active >= pool.Max {\n    log.Println(\"Max Connections Reached\")\n    return errors.New(\"Max Connections Reached\")\n}",
        "think": "Updating Go db pool error handling in src/db/connection.go to log and return 'Max Connections Reached'."
    },
    # Domain 4: Cache Invalidation (Python / Redis)
    {
        "prompt": "cache helper in src/cache/redis.py line 80 needs logging. on cache miss print 'Cache Miss' before fetching from DB.",
        "file": "src/cache/redis.py", "lang": "python", "comment": "#",
        "search": "def get_user_cache(user_id):\n    data = redis.get(f'user:{user_id}')\n    if not data:\n        return fetch_from_db(user_id)",
        "replace": "def get_user_cache(user_id):\n    data = redis.get(f'user:{user_id}')\n    if not data:\n        print('Cache Miss')\n        return fetch_from_db(user_id)",
        "think": "Adding 'Cache Miss' print output in src/cache/redis.py when cache key is absent."
    },
    # Domain 5: File Upload Validation (JS / Node)
    {
        "prompt": "upload middleware src/upload/validator.js line 110: if file size > 10MB reject with 413 code and error 'File Too Large'.",
        "file": "src/upload/validator.js", "lang": "javascript", "comment": "//",
        "search": "if (file.size > MAX_SIZE) {\n    return res.status(400).send('bad file');\n}",
        "replace": "if (file.size > MAX_SIZE) {\n    return res.status(413).json({ error: 'File Too Large' });\n}",
        "think": "Updating file upload validator in src/upload/validator.js to return 413 'File Too Large'."
    },
    # Domain 6: SQL Pagination Default (Python / SQLAlchemy)
    {
        "prompt": "in src/api/pagination.py line 25, if page_size is not specified or invalid, set default page_size to 20.",
        "file": "src/api/pagination.py", "lang": "python", "comment": "#",
        "search": "def get_pagination_params(req):\n    page_size = req.args.get('page_size')\n    if not page_size:\n        page_size = 100",
        "replace": "def get_pagination_params(req):\n    page_size = req.args.get('page_size')\n    if not page_size:\n        page_size = 20",
        "think": "Updating default page_size parameter to 20 in src/api/pagination.py."
    }
]

casual_examples = []
idx = 0
while len(casual_examples) < 50:
    t = ood_templates[idx % len(ood_templates)]
    v_prompt = t["prompt"]
    if idx >= len(ood_templates):
        v_prompt = f"[{idx}] " + v_prompt
    
    file_content = f"```{t['lang']}\n{t['comment']} filepath: {t['file']}\n{t['comment']} action: MODIFY\n\n<<<<<<<\n{t['search']}\n=======\n{t['replace']}\n>>>>>>>\n```"
    
    entry = {
        "messages": [
            {"role": "user", "content": v_prompt},
            {"role": "assistant", "content": f"<<THINKING>>\n{t['think']}\n\n<<FILES>>\n{file_content}\n\n<<TEST_COMMAND>>\nnone"}
        ]
    }
    casual_examples.append(entry)
    idx += 1

print(f"Generated Issue 1 (Out-of-Distribution Casual) examples: {len(casual_examples)}")

# 20 Indentation Preservation Examples across 0, 4, 8, 12 spaces (Issue 2)
indent_templates = [
    (0, "py", "#", "def connect_db():\n    pass", "def connect_db():\n    return create_engine()"),
    (4, "py", "#", "    def handle_request(self, req):\n        status = 200", "    def handle_request(self, req):\n        status = 200\n        log_request(req)"),
    (8, "py", "#", "        if self.is_authenticated:\n            return self.user", "        if self.is_authenticated:\n            return self.user.to_dict()"),
    (12, "py", "#", "            for record in records:\n                record.save()", "            for record in records:\n                record.save_async()"),
    (0, "js", "//", "function clearCache() {\n    redis.flush();\n}", "function clearCache() {\n    redis.flushall();\n}"),
    (4, "js", "//", "    async validateToken(token) {\n        return jwt.verify(token);\n    }", "    async validateToken(token) {\n        return jwt.verify(token, SECRET);\n    }"),
    (8, "js", "//", "        if (err) {\n            console.error(err);\n        }", "        if (err) {\n            logger.error('Token Error', err);\n        }"),
    (12, "js", "//", "            rows.map(r => {\n                return r.id;\n            });", "            rows.map(r => {\n                return r.uuid;\n            });")
]

indent_examples = []
for i in range(20):
    indent_spaces, lang, comm, search_code, replace_code = indent_templates[i % len(indent_templates)]
    filename = f"src/services/service_{i}.{lang}"
    prompt = f"In {filename}, modify the code around line {30 + i*4} to update implementation with exact {indent_spaces}-space indentation preservation."
    
    file_content = f"```{lang}\n{comm} filepath: {filename}\n{comm} action: MODIFY\n\n<<<<<<<\n{search_code}\n=======\n{replace_code}\n>>>>>>>\n```"
    
    entry = {
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": f"<<THINKING>>\nModifying code block in {filename} preserving exact {indent_spaces}-space indentation.\n\n<<FILES>>\n{file_content}\n\n<<TEST_COMMAND>>\nnone"}
        ]
    }
    indent_examples.append(entry)

print(f"Generated Issue 2 (Indentation Preservation) examples: {len(indent_examples)}")

# Combine into v10_clean
clean_v10_dataset = base_data + casual_examples + indent_examples

out_file = "dataset_nova3b_v10_clean.jsonl"
with open(out_file, "w") as f:
    for item in clean_v10_dataset:
        f.write(json.dumps(item) + "\n")

print(f"Clean V10 Dataset created: {out_file} (Total: {len(clean_v10_dataset)} entries)")
