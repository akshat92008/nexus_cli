from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from nova_v12.schemas import load_jsonl, write_jsonl


def split_name(key: str, *, seed: int, train: float, validation: float) -> str:
    if not key:
        raise ValueError("split key cannot be empty")
    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    if value < train:
        return "train"
    if value < train + validation:
        return "validation"
    return "test"


def split_jsonl(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    key_field: str = "repository",
    seed: int = 42,
    train: float = 0.98,
    validation: float = 0.01,
    test: float = 0.01,
) -> dict[str, int]:
    if min(train, validation, test) < 0 or abs(train + validation + test - 1.0) > 1e-9:
        raise ValueError("train, validation and test fractions must be non-negative and sum to 1")
    buckets: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    assignment: dict[str, str] = {}
    for record in load_jsonl(input_path):
        key = str(record.get(key_field) or record.get("repository_snapshot") or "")
        if not key:
            raise ValueError(f"record {record.get('id', '<unknown>')} has no split key")
        selected = assignment.setdefault(
            key,
            split_name(key, seed=seed, train=train, validation=validation),
        )
        buckets[selected].append(record)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, records in buckets.items():
        write_jsonl(root / f"{name}.jsonl", records)
    return {name: len(records) for name, records in buckets.items()}
