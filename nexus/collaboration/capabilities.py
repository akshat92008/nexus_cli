"""
nexus/collaboration/capabilities.py

Agent capability registry: maps roles to typed capability profiles
and validates assignments before worker launch.
"""

from __future__ import annotations

from typing import Dict, Optional

from nexus.collaboration.models import (
    AgentCapabilityProfile,
    AgentRole,
    ModelTier,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Default capability profiles
# ---------------------------------------------------------------------------

def _default_profiles() -> Dict[AgentRole, AgentCapabilityProfile]:
    return {
        AgentRole.LEAD_ENGINEER: AgentCapabilityProfile(
            role=AgentRole.LEAD_ENGINEER,
            supported_task_types=("planning", "orchestration", "review", "finalization"),
            supported_languages=("*",),
            allowed_tool_capabilities=(
                "read_file", "write_file", "run_command", "search_code",
                "transaction_gateway", "approve", "verify",
            ),
            mutation_allowed=True,
            maximum_risk_level=RiskLevel.CRITICAL,
            preferred_model_tiers=(
                ModelTier.CLOUD_FRONTIER,
                ModelTier.CLOUD_STANDARD,
                ModelTier.LOCAL_LARGE,
            ),
            context_budget=128_000,
            can_request_approval=True,
            can_create_workers=True,
        ),
        AgentRole.REPOSITORY_ANALYST: AgentCapabilityProfile(
            role=AgentRole.REPOSITORY_ANALYST,
            supported_task_types=("analysis", "investigation", "mapping"),
            supported_languages=("*",),
            allowed_tool_capabilities=("read_file", "search_code", "list_directory"),
            mutation_allowed=False,
            maximum_risk_level=RiskLevel.NONE,
            preferred_model_tiers=(
                ModelTier.LOCAL_MEDIUM,
                ModelTier.LOCAL_SMALL,
                ModelTier.CLOUD_LIGHT,
            ),
            context_budget=32_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.IMPLEMENTATION_ENGINEER: AgentCapabilityProfile(
            role=AgentRole.IMPLEMENTATION_ENGINEER,
            supported_task_types=("implementation", "refactoring", "bug_fix"),
            supported_languages=("python", "javascript", "typescript", "go", "rust"),
            allowed_tool_capabilities=(
                "read_file", "write_file", "run_command", "search_code", "transaction_gateway",
            ),
            mutation_allowed=True,
            maximum_risk_level=RiskLevel.HIGH,
            preferred_model_tiers=(
                ModelTier.CLOUD_STANDARD,
                ModelTier.CLOUD_FRONTIER,
                ModelTier.LOCAL_LARGE,
            ),
            context_budget=64_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.TEST_ENGINEER: AgentCapabilityProfile(
            role=AgentRole.TEST_ENGINEER,
            supported_task_types=("test_writing", "test_discovery", "coverage_analysis"),
            supported_languages=("python", "javascript", "typescript"),
            allowed_tool_capabilities=(
                "read_file", "write_file", "run_command", "search_code", "transaction_gateway",
            ),
            mutation_allowed=True,
            maximum_risk_level=RiskLevel.LOW,
            preferred_model_tiers=(
                ModelTier.LOCAL_LARGE,
                ModelTier.CLOUD_STANDARD,
            ),
            context_budget=48_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.DEBUGGER: AgentCapabilityProfile(
            role=AgentRole.DEBUGGER,
            supported_task_types=("debugging", "hypothesis_testing", "trace_analysis"),
            supported_languages=("*",),
            allowed_tool_capabilities=("read_file", "run_command", "search_code"),
            mutation_allowed=False,
            maximum_risk_level=RiskLevel.NONE,
            preferred_model_tiers=(
                ModelTier.CLOUD_STANDARD,
                ModelTier.LOCAL_LARGE,
            ),
            context_budget=48_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.SECURITY_REVIEWER: AgentCapabilityProfile(
            role=AgentRole.SECURITY_REVIEWER,
            supported_task_types=("security_review", "vulnerability_analysis"),
            supported_languages=("*",),
            allowed_tool_capabilities=("read_file", "search_code"),
            mutation_allowed=False,
            maximum_risk_level=RiskLevel.NONE,
            preferred_model_tiers=(
                ModelTier.LOCAL_LARGE,
                ModelTier.CLOUD_STANDARD,
            ),
            context_budget=48_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.ARCHITECTURE_REVIEWER: AgentCapabilityProfile(
            role=AgentRole.ARCHITECTURE_REVIEWER,
            supported_task_types=("architecture_review", "design_analysis"),
            supported_languages=("*",),
            allowed_tool_capabilities=("read_file", "search_code"),
            mutation_allowed=False,
            maximum_risk_level=RiskLevel.NONE,
            preferred_model_tiers=(
                ModelTier.CLOUD_FRONTIER,
                ModelTier.CLOUD_STANDARD,
            ),
            context_budget=64_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.DEPENDENCY_SPECIALIST: AgentCapabilityProfile(
            role=AgentRole.DEPENDENCY_SPECIALIST,
            supported_task_types=("dependency_analysis", "version_compatibility"),
            supported_languages=("*",),
            allowed_tool_capabilities=("read_file", "search_code", "run_command"),
            mutation_allowed=False,
            maximum_risk_level=RiskLevel.LOW,
            preferred_model_tiers=(
                ModelTier.LOCAL_MEDIUM,
                ModelTier.LOCAL_SMALL,
            ),
            context_budget=24_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.DOCUMENTATION_ENGINEER: AgentCapabilityProfile(
            role=AgentRole.DOCUMENTATION_ENGINEER,
            supported_task_types=("documentation", "readme", "api_docs"),
            supported_languages=("markdown", "rst", "python"),
            allowed_tool_capabilities=("read_file", "write_file", "search_code", "transaction_gateway"),
            mutation_allowed=True,
            maximum_risk_level=RiskLevel.LOW,
            preferred_model_tiers=(
                ModelTier.LOCAL_LARGE,
                ModelTier.CLOUD_STANDARD,
            ),
            context_budget=32_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
        AgentRole.INDEPENDENT_VERIFIER: AgentCapabilityProfile(
            role=AgentRole.INDEPENDENT_VERIFIER,
            supported_task_types=("verification", "acceptance_testing", "diff_review"),
            supported_languages=("*",),
            allowed_tool_capabilities=("read_file", "run_command", "search_code"),
            mutation_allowed=False,
            maximum_risk_level=RiskLevel.NONE,
            preferred_model_tiers=(
                ModelTier.LOCAL_LARGE,
                ModelTier.CLOUD_STANDARD,
            ),
            context_budget=32_000,
            can_request_approval=False,
            can_create_workers=False,
        ),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class AgentCapabilityRegistry:
    """
    Stores and validates agent capability profiles.
    Workers may not launch without a registered and validated profile.
    """

    def __init__(self) -> None:
        self._profiles: Dict[AgentRole, AgentCapabilityProfile] = _default_profiles()

    def get_profile(self, role: AgentRole) -> Optional[AgentCapabilityProfile]:
        return self._profiles.get(role)

    def register_profile(self, profile: AgentCapabilityProfile) -> None:
        self._profiles[profile.role] = profile

    def list_roles(self) -> list[AgentRole]:
        return list(self._profiles.keys())

    def validate_tool_access(self, role: AgentRole, tool: str) -> bool:
        profile = self.get_profile(role)
        if not profile:
            return False
        return tool in profile.allowed_tool_capabilities

    def can_mutate(self, role: AgentRole) -> bool:
        profile = self.get_profile(role)
        return bool(profile and profile.mutation_allowed)

    def can_create_workers(self, role: AgentRole) -> bool:
        profile = self.get_profile(role)
        return bool(profile and profile.can_create_workers)

    def validate_assignment_role(
        self,
        role: AgentRole,
        task_type: str,
        requires_mutation: bool,
    ) -> tuple[bool, str]:
        """
        Returns (ok, rejection_reason).
        Rejects if: role not registered, task type unsupported,
        or mutation requested for a non-mutation role.
        """
        profile = self.get_profile(role)
        if not profile:
            return False, f"Role {role.value} is not registered in capability registry."

        if task_type not in profile.supported_task_types and "*" not in profile.supported_task_types:
            return False, (
                f"Role {role.value} does not support task type '{task_type}'. "
                f"Supported: {profile.supported_task_types}"
            )

        if requires_mutation and not profile.mutation_allowed:
            return False, (
                f"Role {role.value} does not allow mutation. "
                "Assign a mutation-capable role."
            )

        return True, ""
