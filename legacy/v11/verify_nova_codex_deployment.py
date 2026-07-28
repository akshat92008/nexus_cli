#!/usr/bin/env python3
"""Verify that nova_codex uses the v11 GGUF and downloaded Modelfile semantics."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GGUF = ROOT / "codex_nova"
WORKSPACE_MODELFILE = ROOT / "Modelfile"
V11_MODELFILE = ROOT / "Modelfile.v11"
EXPECTED_GGUF_SHA256 = "b006d313fa085acff9efd51f55f56d6a7588dffdd5d1d815941f71ffe670237d"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def template(text: str) -> str:
    match = re.search(r'TEMPLATE\s+"""(.*?)"""|TEMPLATE\s+"(.*?)"', text, re.DOTALL)
    if not match:
        raise ValueError("TEMPLATE block not found")
    return match.group(1) or match.group(2)


def system_prompt(text: str) -> str:
    triple = re.search(r'SYSTEM """(.*?)"""', text, re.DOTALL)
    if triple:
        return triple.group(1).strip()
    plain = re.search(r"^SYSTEM\s+(.*)$", text, re.MULTILINE)
    if not plain:
        raise ValueError("SYSTEM prompt not found")
    return plain.group(1).strip()


def main() -> int:
    v11_text = V11_MODELFILE.read_text(encoding="utf-8")
    workspace = WORKSPACE_MODELFILE.read_text(encoding="utf-8")
    loaded = subprocess.run(
        ["ollama", "show", "nova_codex", "--modelfile"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    listing = subprocess.run(
        ["ollama", "list"], check=True, capture_output=True, text=True
    ).stdout
    list_line = next(
        (line for line in listing.splitlines() if line.startswith("nova_codex:latest")),
        "MISSING",
    )

    gguf_hash = sha256(GGUF)
    workspace_hash = sha256(WORKSPACE_MODELFILE)
    v11_hash = sha256(V11_MODELFILE)
    loaded_from = re.search(r"^FROM\s+(.+)$", loaded, re.MULTILINE)
    loaded_from_value = loaded_from.group(1).strip() if loaded_from else "MISSING"

    checks = {
        "gguf_sha_matches": gguf_hash == EXPECTED_GGUF_SHA256,
        "workspace_modelfile_matches_v11": workspace == v11_text,
        "loaded_from_matches_gguf_sha": EXPECTED_GGUF_SHA256 in loaded_from_value,
        "loaded_system_matches_v11": system_prompt(loaded) == system_prompt(v11_text),
    }

    print(f"OLLAMA_LIST={list_line}")
    print(f"GGUF_PATH={GGUF}")
    print(f"GGUF_SIZE_BYTES={GGUF.stat().st_size}")
    print(f"GGUF_SHA256={gguf_hash}")
    print(f"WORKSPACE_MODELFILE_SHA256={workspace_hash}")
    print(f"V11_MODELFILE_SHA256={v11_hash}")
    print(f"LOADED_FROM={loaded_from_value}")
    for name, passed in checks.items():
        print(f"{name.upper()}={passed}")
    print(f"SEMANTIC_MODELFILE_DIFF={'NONE' if all(checks.values()) else 'MISMATCH'}")
    return 0 if all(checks.values()) and list_line != "MISSING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
