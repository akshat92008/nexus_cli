import sys
from pipeline import CeilingInternPipeline
from regression_suite import REGRESSION_SUITE

CASES = {
    "Case 5 (D2_messy_authbug)": REGRESSION_SUITE["D2_messy_authbug"]["prompt"],
    "Case 6 (D3_messy_healthcheck)": REGRESSION_SUITE["D3_messy_healthcheck"]["prompt"],
    "Fresh Case 2 (F1_path_fidelity_signup)": REGRESSION_SUITE["F1_path_fidelity_signup"]["prompt"],
    "A1": REGRESSION_SUITE["A1_indist_metrics"]["prompt"],
    "A2": REGRESSION_SUITE["A2_indist_factorial"]["prompt"],
    "A3": REGRESSION_SUITE["A3_indist_flask"]["prompt"],
    "A4": REGRESSION_SUITE["A4_indist_bash"]["prompt"],
    "C1 (messy proven)": REGRESSION_SUITE["C1_messy_go_pinger"]["prompt"],
    "C2 (messy proven)": REGRESSION_SUITE["C2_messy_quicksort"]["prompt"],
}

pipeline = CeilingInternPipeline(
    ceiling_provider="manual", # Manual means it doesn't use API, just passes the prompt as a single task
    intern_model="nova3b",
    run_tests=True, # Enable test execution!
)

for case_name, prompt in CASES.items():
    print(f"\n\n==================== {case_name.upper()} ====================")
    print(f"PROMPT: {prompt}\n")
    result = pipeline.run(prompt)
    if result.results:
        task_res = result.results[0]
        print("\nRAW PIPELINE OUTPUT:")
        print(task_res.response.raw_text)
        print("\nTEST RESULT:")
        print(f"Passed: {task_res.test_status}")
        print(f"Output: {task_res.test_output}")

