import json
import os
import shutil
import tempfile
from pipeline import CeilingInternPipeline

def create_complex_file(path, num_lines, target_line_idx, target_content, language="python"):
    lines = []
    if language == "python":
        lines.append("import os\nimport sys\nimport time\nimport logging\n")
        for i in range(1, num_lines + 1):
            if i == target_line_idx:
                lines.append(target_content + "\n")
            elif i % 10 == 0:
                lines.append(f"def dummy_func_{i}(x, y):\n    '''This is a dummy function to add noise.'''\n    return x + y\n")
            elif i % 10 == 2 or i % 10 == 3 or i % 10 == 4:
                pass # skip to account for multi-line funcs
            else:
                lines.append(f"# noise comment {i}\n")
    elif language == "js":
        lines.append("const express = require('express');\nconst fs = require('fs');\n")
        for i in range(1, num_lines + 1):
            if i == target_line_idx:
                lines.append(target_content + "\n")
            elif i % 10 == 0:
                lines.append(f"function dummyFunc{i}(a, b) {{\n    // Dummy function for noise\n    return a * b;\n}}\n")
            elif i % 10 == 2 or i % 10 == 3 or i % 10 == 4:
                pass
            else:
                lines.append(f"// noise comment {i}\n")
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.writelines(lines)

def main():
    if os.path.exists('guardrail_events.jsonl'):
        os.remove('guardrail_events.jsonl')

    workspace = tempfile.mkdtemp(prefix="amaura_workspace_realistic_")
    
    # Case 5: src/auth.py at line 40
    auth_target = "    # This endpoint crashes if the user has no profile picture\n    profile_pic_url = current_user.profile_pic_url"
    create_complex_file(os.path.join(workspace, "src", "auth.py"), 150, 40, auth_target, "python")
    
    # Case 6: src/app.js at line 85 (approx)
    app_target = "app.get('/healthcheck', (req, res) => {\n    const connection = db.getConnection();\n    res.status(200).json({ status: 'healthy' });\n});"
    create_complex_file(os.path.join(workspace, "src", "app.js"), 150, 85, app_target, "js")
    
    # Fresh Case 1: src/utils.py line 75 (assignment)
    utils_target = "def execute_with_retry(task, max_retries=None):\n    if max_retries is None:\n        max_retries = 5 # BUG: too high"
    create_complex_file(os.path.join(workspace, "src", "utils.py"), 150, 75, utils_target, "python")

    # Fresh Case 2: src/routes/api.js line 90 (status code + string)
    api_target = "router.post('/payment', (req, res) => {\n    if (!req.body.token) {\n        return res.status(200).json({ error: 'failed' });\n    }\n});"
    create_complex_file(os.path.join(workspace, "src", "routes", "api.js"), 150, 90, api_target, "js")

    # Fresh Case 3: src/worker.py line 50 (string output)
    worker_target = "def process_job(job_id):\n    try:\n        do_work(job_id)\n    except TimeoutError:\n        print('Failed')\n"
    create_complex_file(os.path.join(workspace, "src", "worker.py"), 150, 50, worker_target, "python")

    pipeline = CeilingInternPipeline(
        ceiling_provider="mock",
        intern_model="nova_codex",
        workspace_dir=workspace,
        run_tests=False
    )

    cases = [
        {
            "name": "Case 5 (Context + Assignment)",
            "prompt": "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."
        },
        {
            "name": "Case 6 (Context + Status/String)",
            "prompt": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."
        },
        {
            "name": "Fresh Case 1 (Assignment)",
            "prompt": "URGENT: the retry logic is looping infinitely. in src/utils.py around line 75, if max_retries is not provided, set it to 3 instead of 5."
        },
        {
            "name": "Fresh Case 2 (Status Code + String JS)",
            "prompt": "URGENT: payment endpoint is returning wrong code. in src/routes/api.js at line 90, change the failure response to return 402 with status: 'Payment Required'."
        },
        {
            "name": "Fresh Case 3 (String Output Python)",
            "prompt": "URGENT: logging monitor is missing timeouts. in src/worker.py line 50, change the exception print output to exactly 'Worker Timeout'."
        }
    ]

    for case in cases:
        for i in range(1, 4):
            print("\n" + "="*50)
            print(f"  RUNNING {case['name']} (Run {i}/3)")
            print("="*50)
            
            # Reset workspace for this run
            if case['name'].startswith("Case 5"):
                target_path = os.path.join(workspace, "src", "auth.py")
                create_complex_file(target_path, 150, 40, auth_target, "python")
            elif case['name'].startswith("Case 6"):
                target_path = os.path.join(workspace, "src", "app.js")
                create_complex_file(target_path, 150, 85, app_target, "js")
            elif case['name'].startswith("Fresh Case 1"):
                target_path = os.path.join(workspace, "src", "utils.py")
                create_complex_file(target_path, 150, 75, utils_target, "python")
            elif case['name'].startswith("Fresh Case 2"):
                target_path = os.path.join(workspace, "src", "routes", "api.js")
                create_complex_file(target_path, 150, 90, api_target, "js")
            elif case['name'].startswith("Fresh Case 3"):
                target_path = os.path.join(workspace, "src", "worker.py")
                create_complex_file(target_path, 150, 50, worker_target, "python")
            
            pipeline.run(case['prompt'])
            
            if os.path.exists(target_path):
                with open(target_path, 'r') as f:
                    merged_content = f.read()
                # Log merged content so it can be extracted
                with open("guardrail_events.jsonl", "a") as f:
                    f.write(json.dumps({"merged_content": merged_content}) + "\n")


    print("\n" + "="*50)
    print("  VERIFYING LOG SCHEMA (guardrail_events.jsonl)")
    print("="*50)
    if os.path.exists('guardrail_events.jsonl'):
        with open('guardrail_events.jsonl', 'r') as f:
            lines = f.readlines()
            
        for i in range(0, len(lines), 2):
            if i + 1 >= len(lines):
                break
            data = json.loads(lines[i])
            merged_data = json.loads(lines[i+1])
            
            case_idx = (i // 2) // 3
            run_idx = ((i // 2) % 3) + 1
            if case_idx < len(cases):
                print(f"--- {cases[case_idx]['name']} RUN {run_idx} ---")
                print(json.dumps(data, indent=2))
                print("\n[MERGED FILE CONTENT]")
                print(merged_data.get("merged_content", ""))
                print("-" * 50)

if __name__ == "__main__":
    main()
