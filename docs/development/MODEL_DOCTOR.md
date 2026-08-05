# Model Doctor Specification

## Overview
`ModelDoctor` (`nexus/model_doctor.py`) runs reproducible capability probes to construct empirical capability scorecards across 16 core dimensions.

## Probe Categories & Dimensions
1. **Protocol**: `INSTRUCTION_FOLLOWING`, `STRUCTURED_OUTPUT`, `TOOL_SELECTION`, `TOOL_ARGUMENTS`.
2. **Repository**: `PATH_DISCIPLINE`, `REPO_CONTEXT_RETENTION`.
3. **Coding**: `SINGLE_FILE_REPAIR`, `TEST_GENERATION`, `PATCH_VALIDITY`.
4. **Reasoning**: `DEBUGGING`, `PLAN_QUALITY`, `PLAN_CRITICISM`.
5. **Multi-File**: `MULTI_FILE_REASONING`, `REFACTORING`.
6. **Safety**: `SECURITY_REASONING`, `RECOVERY_QUALITY`.

## Qualitative Scorecard Bands
- `STRONG`: score >= 0.85
- `SUITABLE`: score >= 0.70
- `CONDITIONAL`: score >= 0.50
- `WEAK`: score >= 0.30
- `UNSUITABLE`: score < 0.30
- `UNKNOWN`: insufficient probe data

## Usage CLI
```bash
nexus model doctor nova3b
nexus model compare nova3b glm-5.2
```
