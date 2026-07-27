# Nova 3B v11 — final permitted realistic benchmark

This is the second and final real post-v11 execution of `run_realistic_baseline.py`, run unmodified against Ollama tag `nova3b11`. The deployed model blob was verified as `sha256-b006d313fa085acff9efd51f55f56d6a7588dffdd5d1d815941f71ffe670237d`.

Raw artifacts:

- `realistic_v11_system_fix_once.log` — 2,985 lines; SHA-256 `b7af45e805d8297dfee113e13c08048a16f8dd7fc7a6dcfc9afeb5a38aaa17aa`
- `guardrail_events_v11_final_attempt.jsonl` — 30 lines; SHA-256 `0c1a0cea175ee1cea61a5b37c4eb88b366854e3d6cd6d26d86ba585f2ddaf688`
- `pipeline.py` — SHA-256 `ffe8c7a6205d614e84b77403247f6010ab21aeb422901e1029edfbefee5ea797`
- Unmodified `run_realistic_baseline.py` — SHA-256 `dcbfeab3f538d4fc9e0fbd8fdfa200489a2ccd3cd392e832400f8f6418af844b`

Disk/constraint-gated result: **13/15 passed (86.7%)**.

The briefing contains an arithmetic inconsistency: it names a `>=90%` goal, but defines its stopping band as `13-15/15`. Thirteen of fifteen is 86.7%; fourteen of fifteen is the first score at or above 90%. This run is therefore inside the briefing's explicit 13-15 stopping band but below 90% mathematically. In either interpretation, iteration stops here because this was the single permitted follow-up attempt.

| Run | Case | Raw final status | Repairs | Category | Raw guardrail outcome |
|---:|---|---|---:|---|---|
| 1 | Case 5 — profile picture, run 1 | `pass` | 0 | Success | Patch applied; required empty-string assignment verified on disk. |
| 2 | Case 5 — profile picture, run 2 | `pass` | 0 | Success | Patch applied; required empty-string assignment verified on disk. |
| 3 | Case 5 — profile picture, run 3 | `pass` | 0 | Success | Patch applied; required empty-string assignment verified on disk. |
| 4 | Case 6 — healthcheck, run 1 | `pass` | 1 | Success | Initial SEARCH did not apply; canonical repair applied and verified `200` plus `degraded` on disk. |
| 5 | Case 6 — healthcheck, run 2 | `pass` | 0 | Success | Patch applied; `200` and `degraded` verified together. |
| 6 | Case 6 — healthcheck, run 3 | `pass` | 1 | Success | Initial SEARCH did not apply; canonical repair passed disk and constraint checks. |
| 7 | Fresh Case 1 — retry default, run 1 | `pass` | 1 | Success | Initial SEARCH did not apply; canonical repair set the required assignment to `3`. |
| 8 | Fresh Case 1 — retry default, run 2 | `pass` | 0 | Success | Assignment `3` applied and verified on disk. |
| 9 | Fresh Case 1 — retry default, run 3 | `failed_after_max_retries` | 1 | Top-Grab | Initial and repaired SEARCH blocks did not exist contiguously in `src/utils.py`; no write was accepted. |
| 10 | Fresh Case 2 — payment, run 1 | `pass` | 0 | Success | Required `402` and `Payment Required` branch applied and verified. |
| 11 | Fresh Case 2 — payment, run 2 | `pass` | 1 | Success | Initial output lacked the filepath header; canonical repair applied and verified. |
| 12 | Fresh Case 2 — payment, run 3 | `pass` | 1 | Success | Initial output lacked the filepath header; canonical repair applied and verified. |
| 13 | Fresh Case 3 — worker timeout, run 1 | `pass` | 1 | Success | Initial excerpt-format output was rejected; canonical repair applied exact `Worker Timeout`. |
| 14 | Fresh Case 3 — worker timeout, run 2 | `pass` | 1 | Success | Initial excerpt-format output was rejected; canonical repair applied exact `Worker Timeout`. |
| 15 | Fresh Case 3 — worker timeout, run 3 | `failed_after_max_retries` | 1 | Double-Wrap | Initial output echoed excerpt markers without canonical headers; repair returned `<<ERROR>>`, so no write was accepted. |

Category counts:

- Success: 13
- Top-Grab: 1
- Double-Wrap: 1
- Failed-Relevance: 0

Compared with the first real post-v11 run, the strict result improved from 8/15 (53.3%) to 13/15 (86.7%). Seven of the thirteen passing runs passed without repair and six passed after the single canonical repair. Both failures were safely rejected; neither caused a disk write.

No further benchmark rerun, system tweak, dataset change, or retrain is permitted under the stated stopping rule.
