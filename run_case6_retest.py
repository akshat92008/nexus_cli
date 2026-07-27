#!/usr/bin/env python3
import os
import tempfile
import json
from pipeline import CeilingInternPipeline

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
    case6_prompt = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."
    app_target = "app.get('/healthcheck', (req, res) => {\n    const connection = db.getConnection();\n    res.status(200).json({ status: 'healthy' });\n});"

    results = []

    for run_i in range(1, 4):
        workspace = tempfile.mkdtemp(prefix=f"case6_run_{run_i}_")
        target_path = os.path.join(workspace, "src", "app.js")
        create_complex_file(target_path, 150, 85, app_target, "js")

        pipeline = CeilingInternPipeline(
            ceiling_provider="mock",
            intern_model="nova_codex",
            workspace_dir=workspace,
            run_tests=False
        )

        print(f"\n" + "="*60)
        print(f"  RUNNING Case 6 (Run {run_i}/3)")
        print("="*60)

        pipeline_result = pipeline.run(case6_prompt)
        print(pipeline_result.summary())
        
        # Verify disk contents
        with open(target_path, "r") as f:
            final_code = f.read()

        has_200 = "200" in final_code
        has_degraded = "'degraded'" in final_code or '"degraded"' in final_code
        
        pipeline_ok = len(pipeline_result.results) > 0 and all(r.response.is_valid for r in pipeline_result.results)
        passed = (pipeline_ok and has_200 and has_degraded)
        status_str = "PASS" if passed else "FAIL"
        
        print(f"\n--- Run {run_i} Final Disk Code Excerpt ---")
        lines = final_code.splitlines()
        for idx, line in enumerate(lines):
            if "healthcheck" in line or "degraded" in line or "try" in line or "db" in line:
                start = max(0, idx - 3)
                end = min(len(lines), idx + 10)
                print("\n".join(f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start+1)))
                break

        print(f"\nRun {run_i} Result: {status_str} (pipeline_ok={pipeline_ok}, 200={has_200}, degraded={has_degraded})")
        
        results.append({
            "run": run_i,
            "status": status_str,
            "pipeline_ok": pipeline_ok,
            "has_200": has_200,
            "has_degraded": has_degraded,
            "raw_output": pipeline_result.results[0].response.raw_text if pipeline_result.results else ""
        })

    print("\n" + "="*60)
    print("  SUMMARY CASE 6 RETEST RESULTS")
    print("="*60)
    for r in results:
        print(f"Run {r['run']}: {r['status']} (Pipeline OK: {r['pipeline_ok']}, 200: {r['has_200']}, degraded: {r['has_degraded']})")

if __name__ == "__main__":
    main()
