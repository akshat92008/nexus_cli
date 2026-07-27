#!/usr/bin/env python3
"""
intern_problems.py — Narrow-Scope Task Generator

Generates surgical, single-function coding tasks and bug-fixes.
This prevents the model from hallucinating massive architectures.
"""

import random
from typing import List, Dict

# ═══════════════════════════════════════════════════════════════════════════════
# Base Templates for Narrow Tasks
# ═══════════════════════════════════════════════════════════════════════════════

TEMPLATES = [
    # 1. Single Function Implementation
    "Implement the `{func_name}` function in Python. It takes {args} and returns {returns}. Ensure proper type hints and handle {edge_case}.",
    
    # 2. Bug Fix (Stack Trace)
    "A user reported a bug in `{file_name}`. When calling `{func_name}`, it throws `{error_type}: {error_msg}` on line {line_num}. Provide the corrected file.",
    
    # 3. Code Refactor / Small Diff
    "Refactor the `{func_name}` function in `{file_name}` to use a {data_structure} instead of a list to improve lookup time from O(N) to O(1).",
    
    # 4. Adding a specific unit test
    "Write a single pytest test function `test_{func_name}_{scenario}` that verifies `{func_name}` raises a `{error_type}` when given {invalid_input}.",
    
    # 5. Missing Helper Function
    "The main class relies on a missing helper `def {func_name}(self, {args}) -> {returns}:`. Implement this helper method to perform {action}."
]

VARS = {
    "func_name": ["calculate_metrics", "parse_headers", "extract_jwt", "sort_users", "validate_schema", "merge_configs", "retry_request", "hash_password", "sanitize_input", "connect_db"],
    "args": ["a list of dictionaries", "a JWT string", "a configuration object", "two integers", "a raw byte stream", "a nested JSON payload"],
    "returns": ["a boolean", "a parsed dictionary", "a sorted list", "a tuple of (status, message)", "a compiled regex pattern", "a database connection"],
    "edge_case": ["empty inputs", "None values", "invalid JSON syntax", "network timeouts", "missing keys", "divide by zero"],
    "file_name": ["auth_utils.py", "database.py", "config_parser.py", "api_client.py", "schema_validator.py", "worker.py", "router.py"],
    "error_type": ["KeyError", "ValueError", "TypeError", "IndexError", "ConnectionError", "TimeoutError"],
    "error_msg": ["'user_id' not found", "cannot unpack non-iterable NoneType object", "list index out of range", "connection reset by peer", "invalid literal for int()"],
    "line_num": ["12", "45", "108", "33", "201", "76", "14"],
    "data_structure": ["set", "dictionary", "collections.deque", "heapq", "frozenset"],
    "scenario": ["empty_input", "invalid_type", "timeout", "success_case", "boundary_value"],
    "invalid_input": ["a negative number", "an empty string", "a missing dict key", "a totally malformed object"],
    "action": ["exponential backoff", "dictionary merging", "string sanitization", "password hashing", "URL encoding"]
}

def generate_intern_problems(count: int, seed: int = 42) -> List[Dict[str, str]]:
    """
    Generates `count` narrow, specific coding problems.
    """
    random.seed(seed)
    problems = []
    
    for _ in range(count):
        template = random.choice(TEMPLATES)
        
        # Format the template by randomly picking from VARS
        kwargs = {}
        import re
        keys = re.findall(r'\{(.*?)\}', template)
        for k in keys:
            if k in VARS:
                kwargs[k] = random.choice(VARS[k])
            else:
                kwargs[k] = "X"
                
        problem_text = template.format(**kwargs)
        
        problems.append({
            "problem": problem_text,
            "category": "narrow_execution"
        })
        
    return problems

if __name__ == "__main__":
    probs = generate_intern_problems(5)
    for p in probs:
        print(f"- {p['problem']}")
