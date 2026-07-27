import json

with open("guardrail_events.jsonl", "r") as f:
    lines = [json.loads(line) for line in f]

print("| Run | Case / Category | Final Status | Guardrail Event / Failure Reason |")
print("|---|---|---|---|")

cases = [
    "Case 5 (Auth profile_pic_url)",
    "Case 6 (JS Healthcheck)",
    "Fresh Case 1 (Python Retry Logic)",
    "Fresh Case 2 (JS Payment 402)",
    "Fresh Case 3 (Python Worker Timeout)"
]

for i in range(0, len(lines), 2):
    run_idx = (i // 2) + 1
    case_name = cases[(run_idx - 1) // 3]
    run_in_case = ((run_idx - 1) % 3) + 1
    
    init_ev = lines[i]
    final_ev = lines[i+1] if i+1 < len(lines) else {}
    
    status = final_ev.get("final_status", "failed")
    check_failed = init_ev.get("check_failed") or final_ev.get("check_failed") or "No patch blocks found / format mismatch"
    
    # Clean check_failed string
    check_failed = str(check_failed).replace("\n", " ")
    
    print(f"| Run {run_idx:02d} | {case_name} (Run {run_in_case}) | **{status.upper()}** | {check_failed} |")
