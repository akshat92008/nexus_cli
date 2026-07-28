#!/usr/bin/env python3
"""
rerun_case6_3times.py — Debug inspect SEARCH block in Case 6
"""

import os
import tempfile
import json
import re
from pipeline import CeilingInternPipeline, AtomicTask

def create_complex_file(path, num_lines, target_line_idx, target_content, language="js"):
    lines = []
    lines.append("const express = require('express');\nconst fs = require('fs');\n")
    for i in range(1, num_lines + 1):
        if i == target_line_idx:
            lines.append(target_content + "\n")
        elif i % 10 == 0:
            lines.append(f"function dummyFunc{i}(a, b) {{\n    // Dummy function for noise\n    return a * b;\n}}\n")
        elif i % 10 in (2, 3, 4):
            pass
        else:
            lines.append(f"// noise comment {i}\n")
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.writelines(lines)

def main():
    workspace = tempfile.mkdtemp(prefix="case6_test_")
    app_target = "app.get('/healthcheck', (req, res) => {\n    const connection = db.getConnection();\n    res.status(200).json({ status: 'healthy' });\n});"
    
    pipeline = CeilingInternPipeline(
        ceiling_provider="mock",
        intern_model="nova_codex",
        workspace_dir=workspace,
        run_tests=False
    )

    case6_prompt = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."

    for run_i in range(1, 4):
        target_path = os.path.join(workspace, "src", "app.js")
        create_complex_file(target_path, 150, 85, app_target, "js")
        
        print(f"\n==================================================")
        print(f"  INSPECTING Case 6 (Run {run_i}/3)")
        print("==================================================")
        
        task = AtomicTask(id=run_i, description=case6_prompt)
        res = pipeline.intern.execute(task)
        print("RAW MODEL OUTPUT:")
        print(res.response.raw_text)
        
        if res.response.files:
            file_action = res.response.files[0]
            pattern = re.compile(r'<+\r?\n(.*?)\r?\n=+\r?\n(.*?)\r?\n>+', re.DOTALL)
            matches = pattern.findall(file_action.content)
            print("\nEXTRACTED MATCHES:")
            for orig, new in matches:
                print("--- ORIGINAL (SEARCH) ---")
                print(repr(orig))
                print("--- NEW (REPLACE) ---")
                print(repr(new))
        
        # Check against target file
        with open(target_path, "r") as f:
            file_text = f.read()
        print(f"\nTarget File Context around line 85:")
        file_lines = file_text.splitlines()
        print("\n".join(f"{i+1}: {l}" for i, l in enumerate(file_lines[75:95], 75)))

if __name__ == "__main__":
    main()
