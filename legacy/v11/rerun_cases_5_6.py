import sys
from pipeline import CeilingInternPipeline
from regression_suite import REGRESSION_SUITE

CASES = {
    "Case 5 (D2_messy_authbug)": REGRESSION_SUITE["D2_messy_authbug"]["prompt"],
    "Case 6 (D3_messy_healthcheck)": REGRESSION_SUITE["D3_messy_healthcheck"]["prompt"],
}

pipeline = CeilingInternPipeline(
    ceiling_provider="manual",
    intern_model="nova3b",
    run_tests=True,
)

for case_name, prompt in CASES.items():
    print(f"\n\n==================== {case_name.upper()} ====================")
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

