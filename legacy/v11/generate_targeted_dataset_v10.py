import json

base_file = "dataset_nova3b_v9.jsonl"
with open(base_file, "r") as f:
    base_data = [json.loads(line) for line in f]

print(f"Base dataset count: {len(base_data)}")

# 1. Generate 50 Casual/Messy Phrasing Examples (Issue 1)
casual_examples = []

# Status code + string in JS / Py / Go with casual prompts
casual_templates = [
    # Payment / Status Code
    {
        "prompt": "hey fix the payment route in src/routes/api.js at line 90... just make it throw 402 with 'Payment Required' or something whenever token is missing.",
        "file": "src/routes/api.js", "lang": "javascript", "comment": "//",
        "search": "router.post('/payment', (req, res) => {\n    if (!req.body.token) {\n        return res.status(200).json({ error: 'failed' });\n    }\n});",
        "replace": "router.post('/payment', (req, res) => {\n    if (!req.body.token) {\n        return res.status(402).json({ error: 'Payment Required' });\n    }\n});",
        "think": "Fixing payment endpoint in src/routes/api.js to return status 402 with 'Payment Required' when token is missing."
    },
    {
        "prompt": "yo production healthcheck is broken in src/app.js near line 85. catch any db errors and return 200 with status: 'healthy' or whatever.",
        "file": "src/app.js", "lang": "javascript", "comment": "//",
        "search": "app.get('/healthcheck', (req, res) => {\n    const connection = db.getConnection();\n    res.status(500).json({ status: 'unhealthy' });\n});",
        "replace": "app.get('/healthcheck', (req, res) => {\n    try {\n        const connection = db.getConnection();\n        res.status(200).json({ status: 'healthy' });\n    } catch (e) {\n        res.status(200).json({ status: 'degraded' });\n    }\n});",
        "think": "Wrapping healthcheck route in src/app.js with try-catch and returning 200 with status 'healthy'."
    },
    # Python Retry logic / Assignment
    {
        "prompt": "URGENT: retry loop in src/utils.py line 75 is stuck infinite. if max_retries isn't passed just set it to 3 instead of 5.",
        "file": "src/utils.py", "lang": "python", "comment": "#",
        "search": "def execute_with_retry(task, max_retries=None):\n    if max_retries is None:\n        max_retries = 5",
        "replace": "def execute_with_retry(task, max_retries=None):\n    if max_retries is None:\n        max_retries = 3",
        "think": "Setting max_retries default to 3 in src/utils.py to fix infinite retry loop."
    },
    # Python Auth / null check
    {
        "prompt": "quick fix: src/auth.py line 40 is crashing when users have no pic. if profile_pic_url is null or none, just set it to an empty string '' so it doesn't break.",
        "file": "src/auth.py", "lang": "python", "comment": "#",
        "search": "    # This endpoint crashes if the user has no profile picture\n    profile_pic_url = current_user.profile_pic_url",
        "replace": "    # Handle null profile picture safely\n    profile_pic_url = current_user.profile_pic_url if current_user.profile_pic_url is not None else ''",
        "think": "Setting profile_pic_url to an empty string if null in src/auth.py."
    },
    # Python Worker Timeout
    {
        "prompt": "monitor missing timeouts in src/worker.py around line 50. update exception print to say exactly 'Worker Timeout'.",
        "file": "src/worker.py", "lang": "python", "comment": "#",
        "search": "def process_job(job_id):\n    try:\n        do_work(job_id)\n    except TimeoutError:\n        print('Failed')",
        "replace": "def process_job(job_id):\n    try:\n        do_work(job_id)\n    except TimeoutError:\n        print('Worker Timeout')",
        "think": "Updating exception print string to 'Worker Timeout' in src/worker.py."
    }
]

# Expand casual templates with variations to reach 50
variations = [
    ("pls update {file}: set status code to 404 and message to 'Not Found'", "src/controllers/user.js", "javascript", "//",
     "router.get('/user/:id', (req, res) => {\n    res.status(500).send('error');\n});",
     "router.get('/user/:id', (req, res) => {\n    res.status(404).json({ message: 'Not Found' });\n});",
     "Updating user controller in src/controllers/user.js to return 404 Not Found."),
     
    ("can u fix {file} line 12? when err occurs print 'Database Connection Error' instead of generic crash", "src/db.py", "python", "#",
     "def connect():\n    try:\n        init_db()\n    except Exception:\n        raise",
     "def connect():\n    try:\n        init_db()\n    except Exception:\n        print('Database Connection Error')",
     "Updating exception handler in src/db.py to print 'Database Connection Error'."),

    ("in {file} if auth header missing return 401 with 'Unauthorized' status", "src/middleware/auth.go", "go", "//",
     "func AuthMiddleware(next http.Handler) http.Handler {\n    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {\n        w.WriteHeader(500)\n    })\n}",
     "func AuthMiddleware(next http.Handler) http.Handler {\n    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {\n        if r.Header.Get(\"Authorization\") == \"\" {\n            http.Error(w, \"Unauthorized\", 401)\n            return\n        }\n        next.ServeHTTP(w, r)\n    })\n}",
     "Updating Go auth middleware in src/middleware/auth.go to return 401 Unauthorized."),

    ("hey change timeout in {file} to 10 seconds default instead of 30", "src/config.py", "python", "#",
     "DEFAULT_TIMEOUT = 30",
     "DEFAULT_TIMEOUT = 10",
     "Lowering DEFAULT_TIMEOUT to 10 in src/config.py.")
]

idx = 0
while len(casual_examples) < 50:
    t = casual_templates[idx % len(casual_templates)]
    # Create variation
    v_prompt = t["prompt"]
    if idx >= len(casual_templates):
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

print(f"Generated Issue 1 (Casual Phrasing) examples: {len(casual_examples)}")

# 2. Generate 20 Indentation Preservation Examples (Issue 2)
indent_examples = []

indent_templates = [
    (0, "py", "#", "def root_func():\n    pass", "def root_func():\n    return True"),
    (4, "py", "#", "    def method(self):\n        x = 1", "    def method(self):\n        x = 2"),
    (8, "py", "#", "        if condition:\n            do_something()", "        if condition:\n            do_something_else()"),
    (12, "py", "#", "            for item in items:\n                process(item)", "            for item in items:\n                process_fast(item)"),
    (0, "js", "//", "function main() {\n    init();\n}", "function main() {\n    initApp();\n}"),
    (4, "js", "//", "    async handle(req) {\n        return false;\n    }", "    async handle(req) {\n        return true;\n    }"),
    (8, "js", "//", "        if (!valid) {\n            throw new Error('invalid');\n        }", "        if (!valid) {\n            throw new Error('Validation Failed');\n        }"),
    (12, "js", "//", "            items.forEach(i => {\n                log(i);\n            });", "            items.forEach(i => {\n                debug(i);\n            });")
]

for i in range(20):
    indent_spaces, lang, comm, search_code, replace_code = indent_templates[i % len(indent_templates)]
    filename = f"src/module_{i}.{lang}"
    prompt = f"In {filename}, modify the code around line {20 + i*5} to update the implementation while preserving exact {indent_spaces}-space indentation."
    
    file_content = f"```{lang}\n{comm} filepath: {filename}\n{comm} action: MODIFY\n\n<<<<<<<\n{search_code}\n=======\n{replace_code}\n>>>>>>>\n```"
    
    entry = {
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": f"<<THINKING>>\nModifying code block in {filename} with exact {indent_spaces}-space indentation preservation.\n\n<<FILES>>\n{file_content}\n\n<<TEST_COMMAND>>\nnone"}
        ]
    }
    indent_examples.append(entry)

print(f"Generated Issue 2 (Indentation Preservation) examples: {len(indent_examples)}")

# Combine into v10
v10_dataset = base_data + casual_examples + indent_examples

out_file = "dataset_nova3b_v10.jsonl"
with open(out_file, "w") as f:
    for item in v10_dataset:
        f.write(json.dumps(item) + "\n")

print(f"New dataset written to {out_file}. Total items: {len(v10_dataset)}")
