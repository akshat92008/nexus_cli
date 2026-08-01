#!/usr/bin/env python3
"""Run the deterministic checks required for a Nexus launch candidate."""

from __future__ import annotations

import ast
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
PROVIDER_SECRET_PREFIXES = (
    "NVIDIA_API_KEY",
    "NVIDIA_FALLBACK_API_KEY",
    "GROQ_API_KEY",
    "GROQ_FALLBACK_API_KEY",
    "OPENROUTER_API_KEY",
)
PROVIDER_SECRET_NAMES = {"NEXUS_OPENAI_API_KEY", "NEXUS_OPENAI_BASE_URL"}


def deterministic_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Create an offline environment for deterministic release checks."""
    env = dict(os.environ if base is None else base)
    for name in list(env):
        if name in PROVIDER_SECRET_NAMES or name.startswith(PROVIDER_SECRET_PREFIXES):
            env.pop(name, None)
    env["NEXUS_DISABLE_NETWORK"] = "1"
    env.setdefault("UV_CACHE_DIR", str(Path(tempfile.gettempdir()) / "nexus-uv-cache"))
    env.setdefault("UV_LINK_MODE", "copy")
    return env


def _requirement_name(value: str) -> str:
    """Normalize a simple PEP 508 requirement to its distribution name."""
    name = value.strip().split(";", 1)[0].strip().split("[", 1)[0]
    for separator in ("===", "==", ">=", "<=", "~=", "!=", ">", "<"):
        name = name.split(separator, 1)[0]
    return name.strip().lower().replace("_", "-")


def assert_dependency_mirror(repo: Path = REPO) -> None:
    """Require requirements.txt to mirror canonical project dependencies."""
    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    marker = "dependencies ="
    start = pyproject.find(marker)
    if start < 0:
        raise RuntimeError("pyproject.toml has no project dependencies list")
    list_start = pyproject.find("[", start + len(marker))
    if list_start < 0:
        raise RuntimeError("could not parse pyproject.toml project dependencies")
    dependencies = None
    for index in range(list_start + 1, len(pyproject)):
        if pyproject[index] != "]":
            continue
        try:
            candidate = ast.literal_eval(pyproject[list_start : index + 1])
        except (SyntaxError, ValueError):
            continue
        if isinstance(candidate, list):
            dependencies = candidate
            break
    if dependencies is None:
        raise RuntimeError("could not parse pyproject.toml project dependencies")
    canonical = {
        _requirement_name(item)
        for item in dependencies
    }
    mirrored = {
        _requirement_name(line)
        for line in (repo / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if canonical != mirrored:
        raise RuntimeError(
            "requirements.txt drifted from pyproject.toml: "
            f"missing={sorted(canonical - mirrored)} extra={sorted(mirrored - canonical)}"
        )


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
    offline_env = deterministic_env()
    assert_dependency_mirror()
    run([python, "-m", "ruff", "check", "nexus", "tests", "scripts"], env=offline_env)
    run([python, "-m", "pytest", "-q"], env=offline_env)
    run([python, "-m", "compileall", "-q", "nexus", "tests"], env=offline_env)

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
        # Dependencies were already installed from the lockfile. Reusing that
        # environment keeps the release gate deterministic and prevents an
        # isolated build environment from reaching a package index mid-gate.
        run(
            [python, "-m", "build", "--no-isolation", "--outdir", str(dist)],
            cwd=build_src,
        )

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
        run(
            wheel_install_command(python, installed, wheels[0]),
            cwd=build_src,
            env=offline_env,
        )
        smoke_env = deterministic_env()
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
                str(REPO / "benchmark-manifest.json"),
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
