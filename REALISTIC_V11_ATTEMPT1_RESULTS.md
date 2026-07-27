# Nova 3B v11 — realistic baseline attempt 1

This is the first real post-v11 run of `run_realistic_baseline.py`. The script was run once, unmodified, against the deployed Ollama tag `nova3b11`, whose model blob was verified as `sha256-b006d313fa085acff9efd51f55f56d6a7588dffdd5d1d815941f71ffe670237d`.

Raw artifacts:

- `realistic_v11_once.log` — 3,012 lines; SHA-256 `dac4199ed68a13bf6fd62505a48362eb6c6824a28b2f8ee4a6de5fd2eb093a48`
- `guardrail_events_v11_attempt1.jsonl` — 30 lines; SHA-256 `2b35e5b7d5d396845fa0d40f1492ee0cfd3a9017583f0f069e4b4ba25ab49d47`

Disk-gated result: **8/15 passed (53.3%)**.

| Run | Case | Raw final status | Retries | Category | Raw guardrail outcome |
|---:|---|---|---:|---|---|
| 1 | Case 5 — profile picture, run 1 | `pass` | 0 | Success | Patch applied; required empty-string assignment verified on disk. |
| 2 | Case 5 — profile picture, run 2 | `pass` | 0 | Success | Patch applied; required empty-string assignment verified on disk. |
| 3 | Case 5 — profile picture, run 3 | `pass` | 0 | Success | Patch applied; required empty-string assignment verified on disk. |
| 4 | Case 6 — healthcheck, run 1 | `pass` | 0 | Success | Patch applied; `200` and `degraded` verified together. |
| 5 | Case 6 — healthcheck, run 2 | `escalated` | 0 | Failed-Relevance | `Constraint FAILED: Constraints were found, but not together in the same logical branch.` Final code used status 500 in the degraded branch instead of required 200. |
| 6 | Case 6 — healthcheck, run 3 | `failed_after_max_retries` | 2 | Top-Grab | `Patch failed to apply for src/app.js. Search block not found.` The broad SEARCH block grabbed dummy functions and omitted intervening source lines. |
| 7 | Fresh Case 1 — retry default, run 1 | `failed_after_max_retries` | 2 | Double-Wrap | `Patch failed to apply for src/utils.py. Search block not found.` Final response wrapped the entire Nova response in an extra code fence. |
| 8 | Fresh Case 1 — retry default, run 2 | `failed_after_max_retries` | 2 | Top-Grab | `Patch failed to apply for src/utils.py. Search block not found.` SEARCH grabbed a preceding noise line in the wrong source order. |
| 9 | Fresh Case 1 — retry default, run 3 | `pass` | 0 | Success | Patch applied; assignment `3` verified on disk. |
| 10 | Fresh Case 2 — payment, run 1 | `failed_after_max_retries` | 2 | Double-Wrap | `Missing # filepath: in code block`; final output echoed excerpt markers and unified-diff syntax. |
| 11 | Fresh Case 2 — payment, run 2 | `failed_after_max_retries` | 2 | Double-Wrap | `Missing # filepath: in code block`; final output echoed excerpt markers and unified-diff syntax. |
| 12 | Fresh Case 2 — payment, run 3 | `failed_after_max_retries` | 2 | Double-Wrap | `Missing # filepath: in code block`; final output echoed excerpt markers and unified-diff syntax. |
| 13 | Fresh Case 3 — worker timeout, run 1 | `pass` | 0 | Success | Patch applied; exact `Worker Timeout` string verified on disk. |
| 14 | Fresh Case 3 — worker timeout, run 2 | `pass` | 0 | Success | Patch applied; exact `Worker Timeout` string verified on disk. |
| 15 | Fresh Case 3 — worker timeout, run 3 | `pass` | 0 | Success | Patch applied; exact `Worker Timeout` string verified on disk. |

Category counts:

- Success: 8
- Top-Grab: 2
- Double-Wrap: 4
- Failed-Relevance: 1

The legacy `evaluate_15_runs.py` heuristic is not used for the pass score because it labels a disk-verified patch as `Top-Grab` whenever the response merely contains the text `dummy_func`, and can label an unapplied patch as `Success`. The score above uses the pipeline's actual strict write/constraint gate recorded in `final_status`.

The one allowed narrow follow-up fix is limited to the guardrail retry path: retain authoritative narrowed context, omit the malformed prior response, provide a canonical patch skeleton, and allow exactly one repair before escalation.
