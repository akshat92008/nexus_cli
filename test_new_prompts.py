import sys
from pipeline import CeilingInternPipeline

PROMPTS = [
    "URGENT: the /health endpoint in src/api.py needs to return status 404 if the db is unreachable.",
    "Update the login function in auth.js to print 'unauthorized access' if the password is wrong.",
    "Write a python function is_even(n) in math_utils.py that checks if n is even and must return True if it is."
]

pipeline = CeilingInternPipeline(
    ceiling_provider="manual",
    intern_model="nova3b",
    run_tests=True,
)

for idx, prompt in enumerate(PROMPTS):
    print(f"\n\n==================== PROMPT {idx+1} ====================")
    print(f"PROMPT: {prompt}\n")
    result = pipeline.run(prompt)
    if result.results:
        task_res = result.results[0]
        print("\nRAW PIPELINE OUTPUT:")
        print(task_res.response.raw_text)
        print("\nTEST RESULT:")
        print(f"Passed: {task_res.test_status}")
        print(f"Output: {task_res.test_output}")
