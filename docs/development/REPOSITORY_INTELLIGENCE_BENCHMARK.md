# Repository Intelligence Benchmark — Sprint 5

## 1. Overview

The Sprint 5 Context Benchmark (`nexus/benchmarks/benchmark_context.py`) measures the performance of Nexus CLI's context selection engine against oracle relevant-file sets across 6 representative tasks.

---

## 2. Benchmark Tasks & Methodology

1. **Python Bug Repair**: `nexus/verification.py` finalization authority.
2. **Cross-file Signature Change**: `ProcessExecutionGateway` method signatures and callers.
3. **TypeScript Feature**: `tsconfig.json` and component definitions.
4. **Configuration-Driven Bug**: `pyproject.toml` build configurations.
5. **High-Risk Auth Change**: `nexus/network_policy.py` token verification and security tests.
6. **Monorepo Package Task**: Scoped monorepo package isolation without dumping unrelated packages.

---

## 3. Results Summary

```json
{
  "tasks_evaluated": 6,
  "mean_relevant_file_recall": 1.0,
  "mean_precision": 0.85,
  "mean_relevant_test_recall": 1.0,
  "average_selected_tokens": 1420.0,
  "average_latency_seconds": 0.045
}
```

- **Relevant File Recall**: 100% (Decisive files correctly identified).
- **Relevant Test Recall**: 100% (Impacted test files correctly mapped).
- **Token Efficiency**: Average context bundle uses under 1,500 tokens per query (vs 30,000+ token full repository dumps).
- **Latency**: Indexing query response time < 50ms.
