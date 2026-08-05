# CANONICAL FAILURE TAXONOMY — NEXUS CLI

Sprint 7 introduces a canonical, typed failure taxonomy for Nexus CLI to classify every failure into a structured, evidence-backed record rather than unstructured raw logs.

---

## 1. Failure Categories and Enums

### Task-Understanding Failures
- `AMBIGUOUS_REQUIREMENT`: User prompt lacks necessary execution details.
- `CONFLICTING_REQUIREMENTS`: Multiple instructions contradict each other.
- `UNRESOLVED_ASSUMPTION`: Required implicit assumption failed validation.
- `WRONG_TASK_CLASSIFICATION`: Task wrongly assigned to incorrect execution engine.

### Context Failures
- `MISSING_CONTEXT`: Necessary symbol, file, or contract missing from prompt bundle.
- `STALE_CONTEXT`: File modified externally since index update.
- `IRRELEVANT_CONTEXT`: Token budget wasted on unrelated files.
- `MISSED_CALLER`: Function definition updated without updating calling functions.
- `MISSED_INTERFACE`: Interface change omitted from implementation.
- `MISSED_CONFIGURATION`: Environment or task config file not included in bundle.
- `MISSED_TEST`: Test file for target code not identified.
- `REPOSITORY_PARSE_FAILURE`: Repo graph indexing or parse failure.

### Planning Failures
- `INCORRECT_ROOT_CAUSE`: Plan formulated based on wrong failure hypothesis.
- `INVALID_PLAN`: Step dependencies or ordering invalid.
- `UNDER_SCOPED_PLAN`: Plan missing necessary implementation or verification steps.
- `OVER_SCOPED_PLAN`: Plan includes unnecessary repository rewrites.
- `INVALID_STEP_ORDER`: Dependency cycle or invalid step sequence.
- `MISSING_ACCEPTANCE_CRITERION`: Acceptance criteria missing for step.
- `MISSING_VERIFICATION_STEP`: Plan lacks test or build verification step.
- `UNSAFE_PLAN`: Plan violates safety rules or protected paths.
- `STALE_PLAN`: Plan invalidated by intermediate code edits.

### Model Failures
- `INVALID_STRUCTURED_OUTPUT`: Model produced malformed JSON/YAML.
- `TOOL_CALL_HALLUCINATION`: Non-existent tool invoked.
- `PATH_HALLUCINATION`: Model targeted non-existent file path.
- `INSTRUCTION_FAILURE`: System prompt rule violated.
- `CONTEXT_RETENTION_FAILURE`: Information lost across turns.
- `PATCH_GENERATION_FAILURE`: Edit chunk failed syntax or match.
- `REPEATED_REASONING_FAILURE`: Identical flawed reasoning repeated.
- `MODEL_CAPABILITY_MISMATCH`: Model lacks reasoning capacity for task complexity.

### Tool and Execution Failures
- `TOOL_UNAVAILABLE`: Registered tool failed to load.
- `TOOL_ARGUMENT_INVALID`: Schema mismatch in tool call arguments.
- `EXECUTABLE_NOT_FOUND`: Shell executable missing from environment.
- `COMMAND_FAILED`: Process returned non-zero exit code.
- `COMMAND_TIMEOUT`: Execution exceeded configured timeout limit.
- `COMMAND_CANCELLED`: User or system cancelled execution.
- `PROCESS_CRASHED`: Process terminated by unhandled signal.
- `OUTPUT_TRUNCATED`: Output exceeded maximum capture buffer.
- `SANDBOX_UNAVAILABLE`: Execution sandbox could not initialize.
- `NETWORK_DENIED`: Blocked by network policy.
- `PERMISSION_DENIED`: Blocked by file or process permissions.
- `POLICY_BLOCKED`: Blocked by Nexus mode policy.

### Mutation Failures
- `PATCH_CONFLICT`: Patch hunk failed to apply.
- `PARTIAL_PATCH`: Multi-chunk edit partially applied.
- `STALE_FILE`: File modified since read.
- `OUT_OF_SCOPE_MUTATION`: Mutation touched unapproved file.
- `PROTECTED_PATH`: System file or protected configuration touched.
- `UNEXPECTED_FILE_CHANGE`: Unintended file modification detected.
- `WORKSPACE_CORRUPTION`: Workspace left in unparseable or broken git state.
- `ROLLBACK_FAILED`: FileHistory rollback failed.

### Verification Failures
- `TARGETED_TEST_FAILED`: Narrow target test failed assertion.
- `REGRESSION_INTRODUCED`: Unrelated test failed after patch.
- `BUILD_FAILED`: Compiler or bundler failed.
- `LINT_FAILED`: Linter check failed.
- `TYPE_CHECK_FAILED`: Type checker reported error.
- `NO_TESTS_COLLECTED`: Test suite collected 0 items.
- `VERIFICATION_TIMEOUT`: Verification suite timed out.
- `VERIFIER_UNAVAILABLE`: Verifier executable missing.
- `EVIDENCE_STALE`: Verification evidence out-of-date.
- `EVIDENCE_CORRUPTED`: Evidence record invalid.
- `ACCEPTANCE_CRITERION_FAILED`: Step acceptance criterion failed.

### Environment Failures
- `DEPENDENCY_MISSING`: Python/JS package missing in runtime.
- `DEPENDENCY_CONFLICT`: Package version conflict.
- `RUNTIME_VERSION_MISMATCH`: Incompatible Node/Python runtime.
- `OPERATING_SYSTEM_UNSUPPORTED`: Platform mismatch.
- `EXTERNAL_SERVICE_UNAVAILABLE`: External API unreachable.
- `REPOSITORY_BASELINE_BROKEN`: Baseline tests failing before task start.
- `DISK_OR_MEMORY_LIMIT`: Resource exhaustion.
- `AUTHENTICATION_FAILURE`: Provider credential invalid.
- `QUOTA_EXHAUSTED`: Provider quota reached.

### Resource Failures
- `BUDGET_EXHAUSTED`: Configured recovery budget exhausted.
- `RETRY_LIMIT_REACHED`: Maximum command retries reached.
- `TIME_LIMIT_REACHED`: Execution time limit reached.
- `CONTEXT_LIMIT_REACHED`: Token window exceeded limit.
- `MODEL_ESCALATION_LIMIT_REACHED`: Maximum model escalations reached.

---

## 2. FailureRecord Schema

```json
{
  "failure_id": "fail-a1b2c3d4",
  "run_id": "run-20260805_120000",
  "category": "verification",
  "kind": "targeted_test_failed",
  "source_component": "verifier",
  "phase": "verification",
  "summary": "TARGETED_TEST_FAILED: Test failed: tests/test_calc.py::test_add",
  "evidence": [
    {
      "evidence_id": "ev-001",
      "kind": "raw_output",
      "source": "pytest",
      "summary": "FAILED tests/test_calc.py::test_add - AssertionError"
    }
  ],
  "repository_state": "dirty",
  "plan_version": 1,
  "attempt_number": 1,
  "retryable": true,
  "severity": "medium",
  "user_action_required": false,
  "failing_tests": ["tests/test_calc.py::test_add"],
  "file_paths": ["tests/test_calc.py"],
  "exit_code": 1
}
```
