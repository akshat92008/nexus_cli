#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

$PYTHON -m compileall -q src
PYTHONPATH=src $PYTHON -m pytest -q
PYTHONPATH=src $PYTHON -m nova_v12.cli validate-tasks eval/tasks
rm -rf runs/example-data runs/example-mutations.jsonl runs/example-mutations.jsonl.rejected.jsonl
PYTHONPATH=src $PYTHON -m nova_v12.cli build-data --config examples/data_config.yaml
PYTHONPATH=src $PYTHON -m nova_v12.cli verify-mutations \
  --input examples/mutations.jsonl \
  --output runs/example-mutations.jsonl

