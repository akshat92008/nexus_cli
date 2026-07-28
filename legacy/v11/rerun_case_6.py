import sys
from pipeline import CeilingInternPipeline
from regression_suite import REGRESSION_SUITE

prompt = REGRESSION_SUITE["D3_messy_healthcheck"]["prompt"]

pipeline = CeilingInternPipeline(
    ceiling_provider="manual",
    intern_model="nova3b",
    run_tests=True,
)

print(f"\n\n==================== CASE 6 ====================")
print(f"PROMPT: {prompt}\n")
for i in range(1, 4):
    print(f"\n\n--- RUN {i} ---")
    result = pipeline.run(prompt)
    if result.results:
        task_res = result.results[0]
        print("\nRAW PIPELINE OUTPUT:")
        print(task_res.response.raw_text)
        print("\nTEST RESULT:")
        print(f"Passed: {task_res.test_status}")
        print(f"Output: {task_res.test_output}")
