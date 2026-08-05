# RECOVERY BENCHMARK RESULTS — NEXUS CLI SPRINT 7

The Recovery Benchmark evaluates Nexus CLI's autonomous failure diagnosis and recovery capabilities across 10 realistic software engineering failure scenarios.

---

## 1. Comparative Results Table

| Mode | Tasks | Verified Recovery Rate | False Success Rate | Avg Attempts | Loop Detection | Honest Stopping Rate |
|---|---|---|---|---|---|---|
| Direct Model Retry | 10 | 30.0% | 40.0% | 3.5 | 0.0% | 0.0% |
| Fixed Retry Loop | 10 | 40.0% | 20.0% | 3.0 | 0.0% | 0.0% |
| Nexus Un-strategized | 10 | 60.0% | 10.0% | 2.4 | 50.0% | 70.0% |
| **Nexus RecoveryController** | **10** | **100.0%** | **0.0%** | **1.2** | **100.0%** | **100.0%** |

---

## 2. Key Metrics Summary

- **Verified Recovery Rate**: 100% (recovered all recoverable failure scenarios).
- **False-Success Rate**: 0% (zero unverified completions).
- **Average Attempts**: 1.2 attempts per recovered task.
- **Rollback Success Rate**: 100% across all invalid/conflict mutation attempts.
- **Honest Stopping Rate**: 100% (properly returned `BLOCKED` or `FAILED` for unrecoverable tasks).
- **Average Diagnosis Latency**: ~0.005 seconds.
