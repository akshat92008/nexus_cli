# DIAGNOSIS ENGINE SPECIFICATION — NEXUS CLI

The Diagnosis Engine consumes normalized failure evidence and attempt context to formulate structured hypotheses and recommend targeted recovery strategies.

---

## 1. Hypothesis Life-Cycle

Hypotheses move through six explicit states:

1. `PROPOSED`: Formulated based on normalized failure signatures.
2. `SUPPORTED`: Validated by stack trace analysis or file diff.
3. `CONTRADICTED`: Refuted by evidence.
4. `CONFIRMED`: Verified by targeted test reproduction.
5. `REJECTED`: Disproved by failed patch attempt.
6. `UNRESOLVED`: Insufficient evidence to evaluate.

---

## 2. Structured FailureDiagnosis Schema

```json
{
  "diagnosis_id": "diag-b2c3d4e5",
  "primary_failure": { ... },
  "likely_root_causes": [
    {
      "hypothesis_id": "hyp-001",
      "statement": "Latest code patch broke test assertions or introduced a regression.",
      "confidence": 0.8,
      "cheap_check": "Inspect exact assertion diff and changed symbols",
      "status": "supported"
    }
  ],
  "recommended_strategy": "APPLY_SMALLER_PATCH",
  "rollback_required": false,
  "replan_required": false,
  "context_expansion_required": false,
  "model_escalation_recommended": false,
  "confidence": 0.85
}
```
