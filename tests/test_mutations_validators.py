from nova_v12.data.mutations import verify_mutation_record
from nova_v12.data.validators import validate_dpo_record, validate_sft_record


def mutation_record():
    return {
        "id": "mut-1",
        "task": "Fix add.",
        "files": [
            {"path": "maths.py", "content": "def add(a, b):\n    return a + b\n"},
            {"path": "check.py", "content": "from maths import add\nassert add(2, 3) == 5\n"},
        ],
        "tests": [{"command": ["python", "check.py"], "timeout_seconds": 5}],
        "mutation": {
            "action": "replace",
            "path": "maths.py",
            "search": "return a + b",
            "replace": "return a - b",
        },
        "provenance": {"source": "unit-test"},
        "repository_snapshot": "abc",
    }


def test_mutation_requires_failure_and_restoration():
    result = verify_mutation_record(mutation_record())
    assert result.verified
    assert result.record["verification"]["passed"] is True


def test_sft_validation_fails_without_execution_evidence():
    record = {
        "id": "x",
        "mode": "debug",
        "messages": [
            {"role": "user", "content": "fix"},
            {"role": "assistant", "content": "patch"},
        ],
        "provenance": {},
    }
    assert not validate_sft_record(record).valid


def test_dpo_validation_compares_evidence():
    record = {
        "id": "p",
        "prompt": "fix",
        "chosen": "good",
        "rejected": "bad",
        "repository_snapshot": "abc",
        "chosen_evidence": {"passed": True, "score": 1.0},
        "rejected_evidence": {"passed": False, "score": 0.0},
    }
    assert validate_dpo_record(record).valid
