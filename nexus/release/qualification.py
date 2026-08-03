"""Stable release qualification and supply-chain evidence helpers."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ReleaseStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_APPROVAL = "needs_approval"


@dataclass(frozen=True)
class ReleaseScope:
    stable: tuple[str, ...]
    beta: tuple[str, ...]
    experimental: tuple[str, ...]
    excluded: tuple[str, ...]

    def classify(self, capability: str) -> str:
        if capability in self.stable:
            return "stable"
        if capability in self.beta:
            return "beta"
        if capability in self.experimental:
            return "experimental"
        return "excluded"


@dataclass(frozen=True)
class ArtifactEvidence:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SupplyChainEvidence:
    generated_at: float
    dependencies: tuple[str, ...]
    licenses: tuple[str, ...]
    artifacts: tuple[ArtifactEvidence, ...]
    secret_scan_passed: bool
    vulnerability_scan_status: str = "not_run"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChannelPolicy:
    stable_allows_beta: bool = False
    beta_allows_experimental: bool = False
    nightly_allows_experimental: bool = True

    def allows(self, channel: str, scope: str) -> bool:
        if scope == "stable":
            return True
        if channel == "stable":
            return self.stable_allows_beta and scope == "beta"
        if channel == "beta":
            return scope == "beta" or (self.beta_allows_experimental and scope == "experimental")
        if channel == "nightly":
            return scope in {"beta", "experimental"} and self.nightly_allows_experimental
        return False


@dataclass(frozen=True)
class RollbackPlan:
    stop_publication: bool = True
    publish_advisory: bool = True
    preserve_user_state: bool = True
    safe_version: str = ""
    downgrade_tested: bool = False
    patch_release_required: bool = True

    def validate(self) -> ReleaseStatus:
        if not (self.stop_publication and self.publish_advisory and self.preserve_user_state):
            return ReleaseStatus.FAIL
        if not self.safe_version or not self.downgrade_tested:
            return ReleaseStatus.NEEDS_APPROVAL
        return ReleaseStatus.PASS


@dataclass(frozen=True)
class ReleaseQualification:
    version: str
    scope: ReleaseScope
    supply_chain: SupplyChainEvidence
    rollback_plan: RollbackPlan
    test_results: dict[str, Any] = field(default_factory=dict)
    security_results: dict[str, Any] = field(default_factory=dict)
    generated_at: float = field(default_factory=time.time)

    def evaluate(self) -> dict[str, Any]:
        failures: list[str] = []
        warnings: list[str] = []
        if not self.version or self.version.count(".") != 2:
            failures.append("version_must_be_semver")
        if not self.supply_chain.secret_scan_passed:
            failures.append("secret_scan_failed")
        if not self.supply_chain.artifacts:
            warnings.append("no_artifacts_recorded")
        if self.rollback_plan.validate() == ReleaseStatus.FAIL:
            failures.append("rollback_plan_invalid")
        elif self.rollback_plan.validate() == ReleaseStatus.NEEDS_APPROVAL:
            warnings.append("rollback_plan_needs_manual_approval")
        for name, result in self.test_results.items():
            if result is False:
                failures.append(f"test_gate_failed:{name}")
        for name, result in self.security_results.items():
            if result == "p0":
                failures.append(f"p0_security_issue:{name}")
        return {
            "status": ReleaseStatus.FAIL.value if failures else ReleaseStatus.PASS.value,
            "failures": failures,
            "warnings": warnings,
            "generated_at": self.generated_at,
        }

    def write(self, path: Path) -> None:
        payload = asdict(self) | {"evaluation": self.evaluate()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def hash_artifact(path: Path) -> ArtifactEvidence:
    content = Path(path).read_bytes()
    return ArtifactEvidence(str(Path(path).resolve()), hashlib.sha256(content).hexdigest(), len(content))


def build_supply_chain_evidence(
    *,
    dependency_lines: tuple[str, ...],
    artifact_paths: tuple[Path, ...] = (),
    secret_scan_passed: bool = True,
) -> SupplyChainEvidence:
    licenses = tuple(sorted({line.split(";", 1)[0].split("==", 1)[0].strip() for line in dependency_lines if line.strip()}))
    return SupplyChainEvidence(
        generated_at=time.time(),
        dependencies=tuple(sorted(line.strip() for line in dependency_lines if line.strip())),
        licenses=licenses,
        artifacts=tuple(hash_artifact(path) for path in artifact_paths),
        secret_scan_passed=secret_scan_passed,
    )


DEFAULT_RELEASE_SCOPE = ReleaseScope(
    stable=(
        "cli_core",
        "workspaces",
        "tool_gateway",
        "verification",
        "evidence_export",
        "benchmark_manifests",
    ),
    beta=("collaboration", "extensions", "mcp", "enterprise_governance", "long_horizon_projects"),
    experimental=("ui_integrations", "automated_release_publishing"),
    excluded=("formal_certification", "unmoderated_marketplace"),
)
