import json
import os
from pipeline import CeilingInternPipeline

def main():
    if os.path.exists('guardrail_events.jsonl'):
        os.remove('guardrail_events.jsonl')

    pipeline = CeilingInternPipeline(
        ceiling_provider="manual",
        intern_model="nova3b",
        run_tests=False
    )

    prompt5 = "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."
    prompt6 = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."

    for i in range(1, 4):
        print("\n" + "="*50)
        print(f"  RUNNING CASE 5 (Run {i}/3)")
        print("="*50)
        pipeline.run(prompt5)

    for i in range(1, 4):
        print("\n" + "="*50)
        print(f"  RUNNING CASE 6 (Run {i}/3)")
        print("="*50)
        pipeline.run(prompt6)

    print("\n" + "="*50)
    print("  VERIFYING LOG SCHEMA (guardrail_events.jsonl)")
    print("="*50)
    if os.path.exists('guardrail_events.jsonl'):
        with open('guardrail_events.jsonl', 'r') as f:
            for i, line in enumerate(f):
                data = json.loads(line)
                case_num = 5 if i < 3 else 6
                run_num = (i % 3) + 1
                print(f"--- CASE {case_num} RUN {run_num} ---")
                print(json.dumps(data, indent=2))
                print("-" * 50)

if __name__ == "__main__":
    main()
