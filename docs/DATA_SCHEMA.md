# Data schemas

## Code record

Required fields:

- `source`
- `repository`
- `revision`
- `path`
- `licence`
- `language`
- `content`

The pipeline adds `content_hash`, quality and provenance metadata.

## SFT record

```json
{
  "id": "task-id",
  "mode": "code|fim|edit|debug|agent|review|explain|refactor",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "provenance": {"source": "..."},
  "verification": {"passed": true}
}
```

Execution-sensitive modes (`edit`, `debug`, `agent`) require passing verification evidence.

## DPO record

```json
{
  "id": "pair-id",
  "prompt": "...",
  "chosen": "...",
  "rejected": "...",
  "chosen_evidence": {"passed": true, "score": 1.0},
  "rejected_evidence": {"passed": false, "score": 0.0},
  "repository_snapshot": "sha256-or-commit"
}
```

The chosen candidate must have stronger executable evidence than the rejected candidate.
