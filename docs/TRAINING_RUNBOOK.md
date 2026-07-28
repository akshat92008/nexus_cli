# Training runbook

1. Run `nova-v12 bakeoff` with pinned candidate revisions and executable tasks.
2. Build a one-million-token corpus and manually audit a random sample.
3. Split by repository using `nova-v12 split-data`.
4. Run CPT smoke training with `nova-v12-cpt --config ...`.
5. Export the candidate and rerun the untouched-base evaluation.
6. Generate execution-verified SFT records and validate them.
7. Run `nova-v12-sft`.
8. Generate multiple teacher/student candidates, score them and run
   `nova-v12-distill` to create SFT and DPO records.
9. Validate DPO records and run `nova-v12-dpo`.
10. Merge adapters and produce full-precision and quantised releases.
11. Re-evaluate every released quantisation independently.

Never scale a stage merely because training loss decreases. Advance only when
held-out executable coding metrics improve without unacceptable regressions.
