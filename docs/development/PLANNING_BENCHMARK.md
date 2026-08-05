# PLANNING BENCHMARK SPECIFICATION

## Overview

The Planning Quality Benchmark evaluates the efficacy of Nexus CLI's planning system across multiple task classes (bug repair, feature implementation, refactoring, migrations, security remediation, dependency upgrades).

---

## Evaluation Metrics

1. **Mandatory Requirement Recall**: Percentage of explicit user requirements captured in `TaskContract`.
2. **Relevant File Recall**: Percentage of ground-truth affected files identified in `MutationScope`.
3. **Relevant Test Recall**: Percentage of relevant test files identified in `VerificationStrategy`.
4. **Critic Defect Detection Rate**: Percentage of injected plan defects (missing callers, circular dependencies, over-broad scope) correctly flagged by `PlanCritic`.
5. **Invalid File Rate**: Percentage of hallucinated or non-existent files in proposed plans.
6. **Unnecessary Scope Rate**: Ratio of unnecessary file modifications proposed compared to reference solution.
7. **Downstream Execution Success**: Rate of successful verified task completion when governed by generated execution contract.
8. **Planning Cost & Latency**: Average token usage and wall-clock execution time per plan.
