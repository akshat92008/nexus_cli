import json
import random

PRIMARY_TEMPLATES = [
    {
        "ext": "py",
        "orig": "for i in range(10):\n    process(i)",
        "new": "for i in range(20):\n    process(i)",
        "prompt": "Increase the loop bound to 20 in {path}.",
        "think": "Modifying loop range in {path}.",
        "cmd": "pytest test_loops.py"
    },
    {
        "ext": "py",
        "orig": "import sys",
        "new": "import sys\nimport os",
        "prompt": "Add the os import to {path}.",
        "think": "Adding missing import os in {path}.",
        "cmd": "pytest test_imports.py"
    },
    {
        "ext": "js",
        "orig": "function handle() {\n    doWork();\n}",
        "new": "function handle() {\n    try {\n        doWork();\n    } catch (e) {\n        console.error(e);\n    }\n}",
        "prompt": "Wrap the doWork call in {path} with a try-catch block.",
        "think": "Adding try-catch wrapper in {path}.",
        "cmd": "npm run test"
    },
    {
        "ext": "py",
        "orig": "class User:\n    def __init__(self, role='guest'):\n        self.role = role",
        "new": "class User:\n    def __init__(self, role='admin'):\n        self.role = role",
        "prompt": "Change the default role for User to 'admin' in {path}.",
        "think": "Updating default argument in {path}.",
        "cmd": "pytest test_user.py"
    },
    {
        "ext": "js",
        "orig": "const Button = () => <button className=\"bg-blue-500\">Click</button>;",
        "new": "const Button = () => <button className=\"bg-red-500\">Click</button>;",
        "prompt": "Change the button color to red in {path}.",
        "think": "Updating tailwind class in {path}.",
        "cmd": "npm run test:ui"
    },
    {
        "ext": "py",
        "orig": "config = {\n    'timeout': 30,\n}",
        "new": "config = {\n    'timeout': 60,\n    'retry': True,\n}",
        "prompt": "Update the config dict in {path}: set timeout to 60 and add retry=True.",
        "think": "Updating config dictionary in {path}.",
        "cmd": "pytest test_config.py"
    },
    {
        "ext": "js",
        "orig": "const regex = /^[a-z]+$/;",
        "new": "const regex = /^[a-zA-Z]+$/;",
        "prompt": "Update the regex in {path} to allow uppercase letters.",
        "think": "Fixing regex pattern in {path}.",
        "cmd": "npm test"
    },
    {
        "ext": "py",
        "orig": "logger.info('Process started')",
        "new": "logger.debug('Process started')",
        "prompt": "Change the log level from info to debug in {path}.",
        "think": "Changing log level in {path}.",
        "cmd": "pytest test_logging.py"
    },
    {
        "ext": "js",
        "orig": "const doubled = items.map(x => x * 2);",
        "new": "const tripled = items.map(x => x * 3);",
        "prompt": "Change the mapping in {path} to triple the values and rename the variable to tripled.",
        "think": "Updating array map callback and variable name in {path}.",
        "cmd": "npm test"
    },
    {
        "ext": "py",
        "orig": "def greet(name):\n    return f'Hello {name}'",
        "new": "def greet(name):\n    return f'Welcome, {name}!'",
        "prompt": "Update the greet string format in {path} to 'Welcome, {name}!'.",
        "think": "Updating f-string format in {path}.",
        "cmd": "pytest test_greet.py"
    }
]

SECONDARY_TEMPLATES = [
    {
        "ext": "py",
        "orig": "timeout = 300\nif not timeout:\n    raise ValueError()",
        "new": "timeout = 60\nif not timeout:\n    raise ValueError()",
        "prompt": "In {path}, lower the default timeout to 60.",
        "think": "Updating timeout in {path} using a targeted patch.",
        "cmd": "pytest test_timeout.py"
    },
    {
        "ext": "js",
        "orig": "const MAX_RETRIES = 5;",
        "new": "const MAX_RETRIES = 3;",
        "prompt": "Reduce MAX_RETRIES to 3 in {path}.",
        "think": "Modifying constant in {path}.",
        "cmd": "npm test"
    },
    {
        "ext": "py",
        "orig": "ENABLE_NEW_UI = False",
        "new": "ENABLE_NEW_UI = True",
        "prompt": "Toggle ENABLE_NEW_UI to True in {path}.",
        "think": "Flipping feature flag in {path}.",
        "cmd": "pytest test_flags.py"
    },
    {
        "ext": "js",
        "orig": "version: '1.0.0',",
        "new": "version: '1.0.1',",
        "prompt": "Bump the hardcoded version to 1.0.1 in {path}.",
        "think": "Bumping version string in {path}.",
        "cmd": "npm test"
    },
    {
        "ext": "py",
        "orig": "DB_PORT = 5432",
        "new": "DB_PORT = 5433",
        "prompt": "Change the DB_PORT to 5433 in {path}.",
        "think": "Updating database port in {path}.",
        "cmd": "pytest test_db.py"
    }
]

def format_example(template, idx, is_large=False):
    ext = template["ext"]
    path = f"src/{'large_' if is_large else ''}component_{idx}.{ext}"
    
    orig_target = template["orig"]
    new_target = template["new"]
    prompt = template["prompt"].replace("{path}", path)
    think = template["think"].replace("{path}", path)
    cmd = template["cmd"]
    
    # Noise generation
    noise_count = random.randint(300, 800) if is_large else random.randint(5, 50)
    comment = "#" if ext == "py" else "//"
    noise_pre = "\n".join([f"{comment} pre-noise context line {i}" for i in range(noise_count)])
    noise_post = "\n".join([f"{comment} post-noise context line {i}" for i in range(noise_count)])
    
    original_file = f"{noise_pre}\n{orig_target}\n{noise_post}"
    
    output = f"""<<THINKING>>
{think}
<<FILES>>
```{ext}
# filepath: {path}
# action: MODIFY
<<<<<<< SEARCH
{orig_target}
=======
{new_target}
>>>>>>> REPLACE
```
<<TEST_COMMAND>>
{cmd}"""

    return {
        "messages": [
            {"role": "system", "content": "You are Nova, an elite coding execution engine..."},
            {"role": "user", "content": prompt + "\\n\\nFile context:\\n" + original_file},
            {"role": "assistant", "content": output}
        ]
    }

dataset = []
for i in range(50):
    t = random.choice(PRIMARY_TEMPLATES)
    dataset.append(format_example(t, i, False))

for i in range(50, 65):
    t = random.choice(SECONDARY_TEMPLATES)
    dataset.append(format_example(t, i, True))

random.shuffle(dataset)

with open('dataset_patch_fidelity.jsonl', 'w') as f:
    for d in dataset:
        f.write(json.dumps(d) + '\n')

with open('sample_10.jsonl', 'w') as f:
    for d in dataset[:10]:
        f.write(json.dumps(d) + '\n')

print("Generated highly diverse dataset_patch_fidelity.jsonl with 65 examples.")
