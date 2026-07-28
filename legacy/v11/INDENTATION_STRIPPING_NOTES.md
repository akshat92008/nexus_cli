# Technical Notes: 1.5B Model Indentation-Stripping in Diff Search Blocks

## Overview
During baseline testing of the fine-tuned 1.5B model, we observed that code reasoning and problem resolution were correct, but patch application frequently failed with `Search block not found`.

## Root Cause
When generating search blocks (`<<<<<<<` or `<<<<`), the 1.5B model frequently strips leading indentation from the first line of the block.

### Example:
**Target File on Disk (`src/utils.py`):**
```python
    if max_retries is None:
        max_retries = 5
```
*(4 leading spaces on line 1)*

**Model Outputted Search Block:**
```python
<<<<<<<
if max_retries is None:
    max_retries = 5
=======
max_retries = 3 if max_retries is None else max_retries
>>>>>>>
```
*(0 leading spaces on line 1)*

## Impact
- Direct string matching (`original_block in modified_text`) fails because `"if max_retries is None:"` does not equal `"    if max_retries is None:"`.
- The strict disk-verification guardrail correctly catches this failure and prevents invalid or corrupted disk writes.

## Future Mitigation Strategies
1. **Pipeline Fuzzy Matcher Enhancement**: Update `patch.py` / `pipeline.py` search matcher to perform leading-whitespace-agnostic matching on the first line of search blocks.
2. **Dataset Augmentation**: Add fine-tuning dataset examples explicitly demonstrating multi-level indented search blocks within functions and methods.
