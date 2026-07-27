# NexusAI + Nova 3B v11 integration results

## Outcome

The lower-priority Nexus track is implemented and verified with real hosted Ceiling calls and the real local `nova3b11` Ollama model. No model call in this verification was mocked or replaced.

The five post-fix multi-step CLI requests all completed successfully and the independently executed workspace contract suite passed 6/6. Across ten atomic subtasks, Nova completed six directly and four were caught after one repair attempt and escalated to Ceiling. All four post-fix escalations passed disk verification and were applied through Nexus tools. This is a 40% subtask escalation rate in this small verification sample; it should not be presented as evidence that Nova equals the Ceiling model in reliability.

## Implemented behavior

- `SafetyLevel.DANGEROUS` operations no longer fall through to execution. Nexus stores the exact tool name and arguments under a one-use confirmation ID. `/confirm <id>` executes only that stored call; `/cancel <id>` discards it. Repeating the model tool call does not count as user confirmation.
- Hosted models route coding/workspace tasks through the two-node backend. The selected NVIDIA model performs Ceiling decomposition; `nova3b11` executes each atomic subtask through the existing Nova parser, path checks, constraint/relevance checks, and strict disk gate.
- Nova gets one clean repair attempt. A second guardrail failure escalates only that subtask to Ceiling.
- The CLI prints each decomposition and, for every subtask, the node, attempt count, guardrail verdict, error, and raw model output.
- Every escalation is appended as JSONL to `.nexusai/escalations.jsonl`, including the request, subtask, attempts, guardrail log, raw Nova/Ceiling evidence, final verdict, and proposed tools.
- The deployed Intern default was changed from the older `nova345` tag to the verified `nova3b11` tag.
- User-facing copy now states: “The Ceiling model plans and handles complex or ambiguous work. Nova 3B handles well-specified subtasks fast and free, locally. A guardrail layer automatically catches and either corrects or escalates Nova's known failure modes.”
- `NEXUS_HOME` can isolate Nexus state without repurposing the process HOME, and explicit process environment variables now correctly take precedence over `.env` values.

## Real request evidence

All requests used `--model kimi`, reported `Ceiling: Kimi K2.6`, and reported `Intern: nova3b11` in literal CLI output.

| Request | Ceiling decomposition | Execution and guardrail result | Applied result |
|---:|---|---|---|
| 1 | Modify `src/app.py`; modify `tests/test_app.py` | App: Nova attempt 1 `PASS`. Test: Nova attempts 1–2 failed the constraint branch check, then `CEILING_PASS`. | Both `edit_file` calls succeeded. |
| 2 | Modify `src/config.js`; modify `docs/config.md` | Config: Nova attempt 1 `PASS`. Docs: Nova attempts 1–2 failed filepath/schema checks, then `CEILING_PASS`. | Both `edit_file` calls succeeded. |
| 3 | Implement `slugify` in `src/slug.py`; add assertion in `tests/test_slug.py` | Source: Nova attempt 1 `PASS`. Test: Nova attempts 1–2 failed the constraint branch check, then `CEILING_PASS`. | Both `edit_file` calls succeeded. |
| 4 | Modify timeout branch in `src/worker.py`; update `docs/worker.md` | Source: Nova attempt 1 `PASS`. Docs: Nova failed schema, then tried `CREATE` for an existing file; escalation returned `CEILING_PASS`. | Both `edit_file` calls succeeded. |
| 5 | Modify upload contract in `src/limits.py`; update `tests/test_limits.py` | Both subtasks passed Nova guardrails on attempt 1. No escalation. | Both `edit_file` calls succeeded. |

Independent verification after all writes:

```text
......                                                                   [100%]
6 passed in 0.02s
```

The repository-level Nexus suite also passed after the implementation:

```text
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 2.29s
```

## Failure discovered and fixed during real verification

The first real pre-fix request failed safely. Ceiling descriptions formatted target paths as `src/app.py:` and `tests/test_app.py:`. The path extractor did not accept a colon after a filename, so authoritative file contents were not included in the per-task context. Nova failed both tasks and Ceiling's assumed SEARCH blocks also failed; no tool call or disk write occurred.

The extractor now accepts common Ceiling punctuation (`:`, `;`, and `)`), with a regression test. The unchanged request was rerun after the fix and completed successfully as request 1 above. The complete failed transcript is preserved as `pre_fix_context_bug.log` rather than omitted.

## Raw artifacts and SHA-256

- `request_01.log` — `f0ed45a31244d7086634f2f8dcdb7c726a83d657e8f6c44c789bf9e5576a493c`
- `request_02.log` — `582f05dbfc1dc14c2820d540d14fdb8c7e05497aa72939941ac5c3d849158e54`
- `request_03.log` — `3a8151fef8ddd5da4ac1c95339ad782d65fb6ab2544798bbcd81c1b387fc1b6a`
- `request_04.log` — `c019fcc3ed93e4f9cd10eec185cd068e47fbf528ad1d9d740025550410c98ca3`
- `request_05.log` — `4f8a2ed7e3adc95a2c58a48170a16ba107bdba55b1d5a51640796000690efadf`
- `final_verification.log` — `d5be81bbe49b412357ba177be7fae47b32ba70b563d2a01ec6ee15df362cc215`
- `escalations.jsonl` — `5dd4fa2b63ada95c8653334b981390a17da2e7ab88d633d8b47cb53f1a5d051c`
- `pre_fix_context_bug.log` — `14002f97cadb4dc82c3b460bed9d2fd865c524f864ed2633d633c661e59312ae`

The escalation log has six records: two failed, safely rejected pre-fix escalations and four successful post-fix escalations. The raw evidence directory is `NEXUS_V11_REAL_VERIFICATION_EVIDENCE/`.
