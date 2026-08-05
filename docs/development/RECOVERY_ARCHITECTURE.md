# RECOVERY ARCHITECTURE — NEXUS CLI

This document outlines the architecture of the canonical Recovery Subsystem introduced in Sprint 7.

---

## 1. Subsystem Architecture

```
                                  [ RAW FAILURE OUTPUT ]
                                             │
                                             ▼
                                   [ FailureNormalizer ]
                                             │
                                             ▼
                                     [ FailureRecord ]
                                             │
                                             ▼
                                     [ DiagnosisEngine ]
                                             │
                                             ▼
                                   [ FailureDiagnosis ]
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
            [ RollbackDecisionEngine ]                 [ StrategyRegistry ]
                        │                                         │
                        ▼                                         ▼
             [ Verified Rollback ]                   [ RecoveryStrategy ]
                                                                  │
                                                                  ▼
                                                       [ LoopDetector & Budget ]
                                                                  │
                                                                  ▼
                                                      [ Executed Strategy ]
```

---

## 2. Component Directory Structure

- `nexus/recovery/records.py`: Taxonomy enums, `FailureRecord`, `FailureDiagnosis`, `FailureHypothesis`.
- `nexus/recovery/normalizer.py`: Normalization layer converting tool outputs into structured `FailureRecord`s.
- `nexus/recovery/extractor.py`: Signal extraction engine parsing stack traces and assertion diffs.
- `nexus/recovery/baseline.py`: Baseline-aware analyzer classifying inherited vs new regressions.
- `nexus/recovery/diagnosis.py`: Core `DiagnosisEngine` formulating evidence-linked hypotheses.
- `nexus/recovery/diagnosers.py`: Specialized diagnosers for patches, tests, build/type checks, and environment.
- `nexus/recovery/strategies.py`: 18 canonical recovery strategies and catalog registry.
- `nexus/recovery/signatures.py`: Attempt signature generation and loop detection engine.
- `nexus/recovery/budget.py`: Recovery budget manager tracking limits and persistence.
- `nexus/recovery/rollback.py`: Rollback decision and verified execution engine.
- `nexus/recovery/resume.py`: Interruption recovery and session resumption engine.
- `nexus/recovery/intervention.py`: User intervention manager formatting approval requests.
- `nexus/recovery/terminal.py`: Terminal states governance (`VERIFIED`, `BLOCKED`, `FAILED`, etc.).
- `nexus/recovery/events.py`: Structured recovery lifecycle events.
- `nexus/recovery/controller.py`: Authoritative `RecoveryController` coordinating all recovery phases.

---

## 3. Run Artifact Layout

Run artifacts are persisted in `.nexus/runs/<run-id>/`:

```text
.nexus/runs/<run-id>/
    failures/
        failure-001.json
        failure-002.json
    diagnoses/
        diagnosis-001.json
    attempts/
        attempt-001.json
        attempt-002.json
    recovery/
        strategy-001.json
    plans/
        plan-v1.json
```
