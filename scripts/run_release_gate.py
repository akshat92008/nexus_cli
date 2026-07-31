#!/usr/bin/env python3
"""Run the deterministic checks required for a Nexus launch candidate."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = REPO, env: dict[str, str] | None = None) -> None:
    """Run one release check and stop immediately on failure."""
    printable = " ".join(command)
    print(f"\n==> {printable}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    python = sys.executable
    run([python, "-m", "ruff", "check", "nexus", "tests"])
    run([python, "-m", "pytest", "-q"])
    run([python, "-m", "compileall", "-q", "nexus", "tests"])

    with tempfile.TemporaryDirectory(prefix="nexus-release-gate-") as temp:
        root = Path(temp)
        import shutil
        # Copy the whole repo to the temp directory so concurrent builds don't collide
        build_src = root / "src_copy"
        shutil.copytree(REPO, build_src, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "dist", "build", "*.egg-info", "legacy", "verification_evidence", "coding_agent", "bakeoff", "runs"))
        
        dist = root / "dist"
        run([python, "-m", "build", "--outdir", str(dist)], cwd=build_src)

        wheels = sorted(dist.glob("nexusai_cli-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one nexusai-cli wheel, found: {wheels}")

        installed = root / "installed"
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(installed),
                str(wheels[0]),
            ],
            cwd=build_src
        )
        smoke_env = dict(os.environ)
        smoke_env["PYTHONPATH"] = str(installed)
        run(
            [
                python,
                "-c",
                (
                    "import importlib.metadata; import nexus; import nexus.nova_backend; "
                    "import nexus.two_node_backend; import nexus.behavioral; "
                    "import nexus.benchmark; import nexus.execution; "
                    "import nexus.extensions; import nexus.language_intelligence; "
                    "import nexus.policy; import nexus.run_catalog; import nexus.sandbox; "
                    "from nexus.webapp.server import create_app; "
                    "assert create_app('release-smoke').routes; "
                    "dist = importlib.metadata.distribution('nexusai-cli'); "
                    "assert any(ep.name == 'nexus' for ep in dist.entry_points); "
                    "assert nexus.__version__ == '3.1.0'"
                ),
            ],
            cwd=root,
            env=smoke_env,
        )
        run([python, "-m", "nexus", "--version"], cwd=root, env=smoke_env)
        run(
            [
                python,
                "-m",
                "nexus",
                "benchmark",
                "--manifest",
                str(REPO / "benchmarks" / "core.json"),
                "--dry-run",
            ],
            cwd=root,
            env=smoke_env,
        )

        doctor_env = dict(smoke_env)
        doctor_env["NVIDIA_API_KEY"] = "nvapi-release-smoke"
        doctor_env.pop("GROQ_API_KEY", None)
        doctor_env.pop("OPENROUTER_API_KEY", None)
        run(
            [
                python,
                "-m",
                "nexus",
                "--doctor",
                "--working-dir",
                str(root / "workspace"),
            ],
            cwd=root,
            env=doctor_env,
        )

    print("\nNexus release gate passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
