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

    for i in range(1, 4):
        print("\n" + "="*50)
        print(f"  RUNNING CASE 5 (Run {i}/3) with fixed extractor")
        print("="*50)
        pipeline.run(prompt5)

    print("\n" + "="*50)
    print("  VERIFYING LOG SCHEMA (guardrail_events.jsonl)")
    print("="*50)
    if os.path.exists('guardrail_events.jsonl'):
        with open('guardrail_events.jsonl', 'r') as f:
            for i, line in enumerate(f):
                data = json.loads(line)
                print(f"--- CASE 5 RUN {i+1} ---")
                print(json.dumps(data, indent=2))
                print("-" * 50)

if __name__ == "__main__":
    main()
