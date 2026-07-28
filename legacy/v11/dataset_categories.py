#!/usr/bin/env python3
"""
dataset_categories.py — Category definitions for Nova 3B training data.

Defines the task categories, their weights, prompt templates, and
code generation skeletons for the parametric dataset generator.

Part of the Nova model family by Amaura.
"""

import random
from typing import Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class TaskCategory:
    """A category of training tasks with weight and templates."""
    name: str
    weight: float  # Proportion of total dataset
    description: str
    prompt_templates: List[str]
    languages: List[str] = field(default_factory=lambda: ["python"])
    difficulty_range: tuple = (1, 5)
    max_thinking_words: int = 50
    action_type: str = "CREATE"  # CREATE or MODIFY


# ═══════════════════════════════════════════════════════════════════════════════
# Category Registry
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORIES: Dict[str, TaskCategory] = {}


def register(cat: TaskCategory):
    CATEGORIES[cat.name] = cat
    return cat


# ─── 1. Single Function Implementation (35%) ─────────────────────────────────

register(TaskCategory(
    name="single_function",
    weight=0.35,
    description="Implement a single, well-defined function with clear inputs/outputs.",
    languages=["python", "javascript", "typescript", "go", "rust"],
    difficulty_range=(1, 6),
    prompt_templates=[
        "Implement a {lang} function `{func_name}` that takes {args} and returns {returns}.",
        "Write a {lang} function to {task_desc}. Handle {edge_case} gracefully.",
        "Create a utility function `{func_name}` in {lang} that {task_desc}. Include type hints.",
        "Implement `{func_name}({args}) -> {returns}` in {lang}. It should {task_desc}.",
        "Write a pure function in {lang} that {task_desc}. No side effects.",
        "Build a helper function `{func_name}` that {task_desc}. Optimize for {optimization}.",
        "Task: {task_desc}. Please implement a single {lang} function to solve this task.",
        "Can you write a {lang} script for this? {task_desc}.",
        "Here is a coding problem: {task_desc}. Please write a {lang} script.",
        "Hey Nova, I need some help. {task_desc}. Could you write the code?",
        "JIRA-{ticket}: {task_desc}. Write a {lang} function for this.",
        "Our goal is to {task_desc}. Write a {lang} function to achieve this.",
        "Could you implement a {lang} function that does the following? {task_desc}.",
        "Please write a {lang} function for the following problem: {task_desc}.",
    ],
))


# ─── 2. Bug Fixing (20%) ─────────────────────────────────────────────────────

register(TaskCategory(
    name="bug_fix",
    weight=0.20,
    description="Fix a specific bug given a stack trace or error description.",
    languages=["python", "javascript", "typescript"],
    difficulty_range=(2, 7),
    action_type="MODIFY",
    prompt_templates=[
        "Fix the bug in `{file_path}`. The function `{func_name}` throws `{error_type}: {error_msg}` when {trigger}.",
        "Debug: `{func_name}` in `{file_path}` has an off-by-one error. It {bug_desc}. Fix it.",
        "The following code crashes with `{error_type}` on line {line_num}:\n```{lang}\n{buggy_code}\n```\nFix the bug.",
        "Users report that `{func_name}` returns incorrect results when {trigger}. The bug is in `{file_path}`. Fix it.",
        "Stack trace:\n```\n{error_type}: {error_msg}\n  File \"{file_path}\", line {line_num}, in {func_name}\n```\nFix this error.",
        "`{func_name}` silently returns None instead of raising when {trigger}. Fix the error handling in `{file_path}`.",
    ],
))


# ─── 3. Code Refactoring (15%) ───────────────────────────────────────────────

register(TaskCategory(
    name="refactor",
    weight=0.15,
    description="Refactor existing code to improve performance, readability, or structure.",
    languages=["python", "javascript", "typescript"],
    difficulty_range=(3, 7),
    action_type="MODIFY",
    prompt_templates=[
        "Refactor `{func_name}` in `{file_path}` to use a {data_structure} instead of a list for O(1) lookups.",
        "The function `{func_name}` is {loc} lines long. Break it into smaller helper functions.",
        "Convert `{func_name}` from synchronous to async/await pattern. Preserve the same API.",
        "Replace the nested for-loops in `{func_name}` with a more Pythonic approach using {technique}.",
        "Refactor `{file_path}` to use the Strategy pattern instead of the current if/elif chain.",
        "Add proper error handling to `{func_name}` — currently it has bare `except:` clauses.",
        "Extract the {component} logic from `{file_path}` into a separate `{new_file}` module.",
    ],
))


# ─── 4. Multi-File Tasks (10%) ───────────────────────────────────────────────

register(TaskCategory(
    name="multi_file",
    weight=0.10,
    description="Create or modify 2-3 coordinated files (e.g., model + route + test).",
    languages=["python", "typescript"],
    difficulty_range=(5, 9),
    prompt_templates=[
        "Create a REST endpoint `{endpoint}` in `{route_file}`. Add the data model in `{model_file}`. Include a test in `{test_file}`.",
        "Add a new `{class_name}` class in `{file_path}` and update `{import_file}` to export it.",
        "Create `{file_1}` with the {component_1} logic and `{file_2}` with the {component_2} logic. They should work together.",
        "Implement the `{feature}` feature: add the handler in `{handler_file}` and the schema in `{schema_file}`.",
    ],
))


# ─── 5. Test Writing (10%) ────────────────────────────────────────────────────

register(TaskCategory(
    name="test_writing",
    weight=0.10,
    description="Write pytest/jest test functions for a given function or class.",
    languages=["python", "javascript"],
    difficulty_range=(2, 6),
    prompt_templates=[
        "Write a pytest test for `{func_name}` that verifies it {expected_behavior}.",
        "Write 3 test cases for `{func_name}`: normal input, edge case ({edge_case}), and error case ({error_case}).",
        "Write a test function `test_{func_name}_{scenario}` that asserts `{func_name}({test_input})` returns `{expected}`.",
        "Create a test suite for the `{class_name}` class covering {method_1} and {method_2}.",
        "Write a parametrized pytest test for `{func_name}` with at least 5 test cases.",
    ],
))


# ─── 6. Format Recovery (5%) ─────────────────────────────────────────────────

register(TaskCategory(
    name="format_recovery",
    weight=0.05,
    description="Handle messy, poorly-formatted user prompts and still produce clean output.",
    languages=["python"],
    difficulty_range=(1, 4),
    prompt_templates=[
        "hey can u make a function that {task_desc} thx",
        "i need {task_desc} asap pls fix",
        "URGENT: {task_desc} — was working yesterday broke today",
        "{task_desc}\n\ndo this fast dont explain anything",
        "yo nova {task_desc} but make it good",
        "write me code for {task_desc}... im stuck help",
        "can you help with {task_desc}?? need it in python",
        "{task_desc} <-- do this. python. no tests needed but add them anyway",
    ],
))


# ─── 7. Boundary/Refusal (5%) ────────────────────────────────────────────────

register(TaskCategory(
    name="boundary",
    weight=0.05,
    description="Gracefully handle requests that exceed the intern's scope.",
    languages=["python"],
    difficulty_range=(1, 3),
    max_thinking_words=80,
    prompt_templates=[
        "Design a complete microservices architecture for a social media platform with 10M users.",
        "Build a full-stack e-commerce application with payment processing, inventory management, and real-time notifications.",
        "Create a distributed database engine with ACID compliance and horizontal scaling.",
        "Architect a real-time multiplayer game server with matchmaking, leaderboards, and anti-cheat.",
        "Build a complete CI/CD pipeline with blue-green deployments, canary releases, and automated rollbacks.",
        "Implement a custom programming language with lexer, parser, AST, and bytecode compiler.",
    ],
))


# ═══════════════════════════════════════════════════════════════════════════════
# Variable Banks for Parametric Substitution
# ═══════════════════════════════════════════════════════════════════════════════

VARIABLE_BANK: Dict[str, List[str]] = {
    "func_name": [
        "calculate_metrics", "parse_headers", "extract_jwt", "sort_users",
        "validate_schema", "merge_configs", "retry_request", "hash_password",
        "sanitize_input", "connect_db", "flatten_tree", "encode_base64",
        "decode_token", "paginate_results", "rate_limit", "cache_response",
        "compress_data", "normalize_text", "parse_csv", "generate_uuid",
        "validate_email", "format_currency", "convert_timezone", "chunk_array",
        "deep_merge", "throttle_calls", "debounce_input", "serialize_model",
        "deserialize_payload", "compute_checksum", "rotate_keys", "batch_process",
        "filter_duplicates", "aggregate_logs", "transform_records",
    ],
    "args": [
        "a list of dictionaries", "a JWT string", "a config object",
        "two sorted arrays", "a raw byte stream", "a nested JSON payload",
        "a file path and encoding", "a URL string", "an integer and a list",
        "a dataframe-like list of rows", "a tree node", "a matrix (2D list)",
    ],
    "returns": [
        "a boolean", "a parsed dictionary", "a sorted list",
        "a tuple of (status, message)", "a filtered list", "an integer count",
        "a string hash", "a list of tuples", "a generator of chunks",
        "a validated object or raises ValueError",
    ],
    "task_desc": [
        "find the longest common subsequence of two strings",
        "merge two sorted linked lists into one sorted list",
        "find all prime numbers up to n using the Sieve of Eratosthenes",
        "implement binary search on a sorted array",
        "reverse a linked list in-place",
        "detect a cycle in a linked list using Floyd's algorithm",
        "flatten a nested dictionary into dot-notation keys",
        "implement a LRU cache with O(1) get and put",
        "validate an email address using regex",
        "convert a Roman numeral string to an integer",
        "find the kth largest element in an unsorted array",
        "implement a rate limiter using the token bucket algorithm",
        "serialize a binary tree to a string and deserialize it back",
        "find the shortest path in an unweighted graph using BFS",
        "implement a trie (prefix tree) with insert, search, and startsWith",
        "compute the edit distance between two strings",
        "group anagrams from a list of strings",
        "find the maximum subarray sum using Kadane's algorithm",
        "implement a stack that supports push, pop, and getMin in O(1)",
        "check if a string of brackets is balanced",
        "rotate a matrix 90 degrees clockwise in-place",
        "find the intersection of two sorted arrays",
        "implement exponential backoff with jitter for retries",
        "parse a cron expression and return the next run time",
        "compute the moving average of a stream of numbers",
        "implement a thread-safe singleton pattern",
        "convert a number to its English word representation",
        "find all permutations of a given string",
        "implement depth-first search on a graph",
        "build a simple calculator that evaluates arithmetic expressions",
    ],
    "edge_case": [
        "empty inputs", "None/null values", "very large inputs (10^6 elements)",
        "negative numbers", "unicode characters", "duplicate entries",
        "single-element collections", "circular references",
    ],
    "error_type": [
        "KeyError", "ValueError", "TypeError", "IndexError",
        "ConnectionError", "TimeoutError", "AttributeError", "ZeroDivisionError",
    ],
    "error_msg": [
        "'user_id' not found", "cannot unpack non-iterable NoneType",
        "list index out of range", "connection reset by peer",
        "invalid literal for int()", "division by zero",
        "expected str, got NoneType", "'dict' object has no attribute 'append'",
    ],
    "trigger": [
        "the input is an empty list", "a None value is passed",
        "the key doesn't exist in the dictionary", "the connection times out",
        "the input contains special characters", "the array has only one element",
    ],
    "bug_desc": [
        "skips the last element due to range(len(arr)-1)",
        "includes an extra element by using <= instead of <",
        "uses 0-indexed access when 1-indexed is expected",
        "fails silently on empty input instead of raising",
        "double-counts the boundary element",
    ],
    "data_structure": [
        "set", "dictionary", "collections.deque", "heapq",
        "defaultdict", "OrderedDict", "Counter",
    ],
    "technique": [
        "list comprehension", "itertools.chain", "functools.reduce",
        "generator expression", "dictionary comprehension",
    ],
    "optimization": [
        "time complexity", "memory usage", "readability", "cache locality",
    ],
    "file_path": [
        "src/auth.py", "src/database.py", "src/api.py", "src/utils.py",
        "src/models.py", "src/handlers.py", "src/middleware.py", "src/config.py",
        "lib/parser.py", "lib/validator.py", "services/user_service.py",
    ],
    "line_num": ["12", "34", "56", "78", "92", "108", "145", "201"],
    "ticket": [str(random.randint(100, 999)) for _ in range(20)],
    "lang": ["python", "javascript", "typescript", "go", "rust"],
    "endpoint": [
        "GET /api/users", "POST /api/auth/login", "PUT /api/settings",
        "DELETE /api/sessions/{id}", "GET /api/health", "POST /api/upload",
    ],
    "component": [
        "authentication", "caching", "validation", "serialization",
        "rate limiting", "logging", "error handling",
    ],
}


def fill_template(template: str, extra_vars: Dict[str, str] = None) -> str:
    """Fill a prompt template with random variables from the bank."""
    import re
    
    filled = template
    placeholders = re.findall(r'\{(\w+)\}', template)
    
    for ph in placeholders:
        if extra_vars and ph in extra_vars:
            value = extra_vars[ph]
        elif ph in VARIABLE_BANK:
            value = random.choice(VARIABLE_BANK[ph])
        else:
            value = ph  # Leave as-is if not found
        filled = filled.replace("{" + ph + "}", value, 1)
    
    return filled


def get_weighted_category() -> TaskCategory:
    """Select a random category weighted by its proportion."""
    cats = list(CATEGORIES.values())
    weights = [c.weight for c in cats]
    return random.choices(cats, weights=weights, k=1)[0]


def generate_task(category: TaskCategory = None) -> Dict[str, Any]:
    """Generate a single task with filled template."""
    if category is None:
        category = get_weighted_category()
    
    template = random.choice(category.prompt_templates)
    lang = random.choice(category.languages)
    
    prompt = fill_template(template, {"lang": lang})
    
    return {
        "prompt": prompt,
        "category": category.name,
        "language": lang,
        "action_type": category.action_type,
        "difficulty": random.randint(*category.difficulty_range),
        "max_thinking_words": category.max_thinking_words,
    }


if __name__ == "__main__":
    # Demo: generate 5 tasks from each category
    for name, cat in CATEGORIES.items():
        print(f"\n{'='*60}")
        print(f"  {name} (weight: {cat.weight})")
        print(f"{'='*60}")
        for _ in range(3):
            task = generate_task(cat)
            print(f"  [{task['language']}] {task['prompt'][:100]}...")
