#!/usr/bin/env python3
"""Run the deterministic checks required for a Nexus launch candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = REPO, env: dict[str, str] | None = None) -> None:
    """Run one release check and stop immediately on failure."""
    printable = " ".join(command)
    print(f"\n==> {printable}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def wheel_install_command(python: str, target: Path, wheel: Path) -> list[str]:
    """Build a wheel smoke-install command for pip-full and uv-managed venvs."""

    if importlib.util.find_spec("pip") is not None:
        installer = [python, "-m", "pip", "install"]
    elif uv := shutil.which("uv"):
        installer = [uv, "pip", "install", "--python", python]
    else:
        raise RuntimeError("release gate requires pip or uv to smoke-install the wheel")
    return [*installer, "--no-deps", "--target", str(target), str(wheel)]


def main() -> int:
    python = sys.executable
    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    run([python, "-m", "ruff", "check", "nexus", "tests", "scripts"])
    run([python, "-m", "pytest", "-q"])
    run([python, "-m", "compileall", "-q", "nexus", "tests"])

    with tempfile.TemporaryDirectory(prefix="nexus-release-gate-") as temp:
        root = Path(temp)
        # Copy the whole repo to the temp directory so concurrent builds don't collide
        build_src = root / "src_copy"
        shutil.copytree(
            REPO,
            build_src,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                "dist",
                "build",
                "*.egg-info",
                "legacy",
                "verification_evidence",
                "coding_agent",
                "bakeoff",
                "runs",
            ),
        )

        dist = root / "dist"
        run([python, "-m", "build", "--outdir", str(dist)], cwd=build_src)

        wheels = sorted(dist.glob("nexusai_cli-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one nexusai-cli wheel, found: {wheels}")

        expected_members = {
            path.relative_to(build_src).as_posix()
            for path in (build_src / "nexus").rglob("*")
            if path.is_file()
            and (
                path.suffix == ".py"
                or "nexus/webapp/static" in path.relative_to(build_src).as_posix()
            )
        }
        with zipfile.ZipFile(wheels[0]) as archive:
            packaged_members = set(archive.namelist())
        missing_members = sorted(expected_members - packaged_members)
        if missing_members:
            raise RuntimeError(
                "wheel is missing source files from the tested commit: "
                + ", ".join(missing_members)
            )
        wheel_sha256 = hashlib.sha256(wheels[0].read_bytes()).hexdigest()

        installed = root / "installed"
        run(wheel_install_command(python, installed, wheels[0]), cwd=build_src)
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
                    "assert nexus.__version__ == dist.version"
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
        run(
            [
                python,
                "-m",
                "nexus",
                "benchmark",
                "--manifest",
                str(REPO / "benchmarks" / "long_horizon.json"),
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

        print(
            "\nRelease provenance: "
            f"commit={commit_sha} wheel={wheels[0].name} sha256={wheel_sha256} "
            f"packaged_source_files={len(expected_members)}",
            flush=True,
        )

    print("\nNexus release gate passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
