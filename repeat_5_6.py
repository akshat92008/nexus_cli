import json
import subprocess
from pipeline import InternNode, AtomicTask
import asyncio

def run_prompt(prompt: str):
    node = InternNode(model="nova3b:latest")
    task = AtomicTask(id=1, description=prompt, expected_files=0)
    result = node.execute(task)
    return result.response.raw_text

case5_prompt = "fix the bug where the user login fails if they dont have a profile pic. i think its in auth.py somewhere around line 40? just make it use a default empty string instead of crashing."
case6_prompt = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."

if __name__ == "__main__":
    print("================ RE-RUNNING CASE 5 (3 TIMES) ================")
    for i in range(3):
        print(f"\n--- Case 5, Run {i+1} ---")
        print(run_prompt(case5_prompt))
        
    print("\n\n================ RE-RUNNING CASE 6 (3 TIMES) ================")
    for i in range(3):
        print(f"\n--- Case 6, Run {i+1} ---")
        print(run_prompt(case6_prompt))
