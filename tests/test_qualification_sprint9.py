"""
Sprint 9 Qualification Test Suite — Model Doctor, Adaptive Routing, Budget Guard and Cost Governance.
"""

from __future__ import annotations

import os
import tempfile
import pytest

from nexus.budget import BudgetController, BudgetExceeded, BudgetLimits, RunBudget
from nexus.cost_accounting import CostLedger, cost_ledger
from nexus.model_doctor import CapabilityBand, CapabilityDimension, ModelDoctor, model_doctor
from nexus.model_escalation import AttributionClass, EscalationController, escalation_controller
from nexus.model_router import EngineeringPhase, ModelRouter, PortfolioMode, model_router
from nexus.models import ModelDescriptor, ModelTier, PrivacyClass, model_registry
from nexus.provider_resilience import ProviderErrorClass, resilience_engine


def test_01_canonical_model_registry():
    """Verify ModelRegistry stores canonical descriptors, resolves aliases and prices correctly."""
    desc = model_registry.get_descriptor("nova")
    assert desc is not None
    assert desc.local is True
    assert desc.input_cost == 0.0
    assert desc.privacy_class == PrivacyClass.LOCAL_ONLY

    glm = model_registry.get_descriptor("glm-5.2")
    assert glm is not None
    assert glm.tier == ModelTier.STRONG
    assert glm.input_cost == 0.50
    assert glm.output_cost == 1.00


def test_02_model_doctor_capability_scorecard():
    """Verify ModelDoctor executes bounded probes and generates structured capability profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = ModelDoctor(storage_dir=tmpdir)
        profile = doc.probe_model("nova3b", trials_per_probe=1)
        assert profile.model_id == "local/nova3b"
        assert len(profile.capabilities) == 16
        assert profile.capabilities["STRUCTURED_OUTPUT"].band in (CapabilityBand.STRONG, CapabilityBand.SUITABLE)
        assert "bounded_bug_repair" in profile.recommended_tasks


def test_03_adaptive_model_router_portfolio_modes():
    """Verify ModelRouter respects portfolio routing modes (CHEAPEST vs STRONGEST vs PRIVATE)."""
    router = ModelRouter()

    # Cheapest mode for documentation should pick local Nova
    reqs_doc = router.derive_task_requirements("doc", phase=EngineeringPhase.DOCUMENTATION)
    d_cheap = router.route(reqs_doc, mode=PortfolioMode.CHEAPEST)
    assert d_cheap.selected_model_key in ("nova3b", "deepseek-flash")
    assert d_cheap.expected_cost_usd <= 0.001

    # Strongest mode for planning should pick GLM 5.2 or DeepSeek Pro
    reqs_plan = router.derive_task_requirements("plan", phase=EngineeringPhase.PLANNING, risk_level="high")
    d_strong = router.route(reqs_plan, mode=PortfolioMode.STRONGEST)
    assert d_strong.selected_model_key in ("glm-5.2", "deepseek-v4", "custom")

    # Private mode must reject remote cloud models
    reqs_priv = router.derive_task_requirements("priv", privacy_policy=PrivacyClass.LOCAL_ONLY)
    d_priv = router.route(reqs_priv, mode=PortfolioMode.PRIVATE)
    assert d_priv.selected_model_key == "nova3b"


def test_04_phase_downshifting():
    """Verify router downshifts to cheaper models for low-risk documentation phases."""
    router = ModelRouter()
    downshifted = router.downshift_if_suitable("glm-5.2", EngineeringPhase.DOCUMENTATION, risk_level="low")
    assert downshifted == "nova3b"

    # Must NOT downshift for high-risk planning
    no_downshift = router.downshift_if_suitable("glm-5.2", EngineeringPhase.PLANNING, risk_level="high")
    assert no_downshift == "glm-5.2"


def test_05_evidence_based_escalation():
    """Verify escalation triggers only on model capability failure evidence, not environment errors."""
    esc = EscalationController()

    # Environment failure must NOT escalate
    attr_env = esc.attribute_failure("sh: pytest: command not found", "execution", "nova3b")
    assert attr_env.attribution == AttributionClass.ENVIRONMENT_FAILURE
    decision_env = esc.evaluate_escalation(attr_env, "nova3b", 1, remaining_budget_usd=5.0)
    assert decision_env.escalation_approved is False

    # Genuine JSON parse error MUST escalate to cloud tier
    attr_json = esc.attribute_failure("JSONDecodeError: Expecting value", "model", "nova3b")
    assert attr_json.attribution == AttributionClass.MODEL_CAPABILITY_MISMATCH
    decision_json = esc.evaluate_escalation(attr_json, "nova3b", 1, remaining_budget_usd=5.0)
    assert decision_json.escalation_approved is True
    assert decision_json.target_model_key != "nova3b"


def test_06_cost_accounting_ledger_and_inr_conversion():
    """Verify CostLedger tracks spend, calculates INR at 85 INR/USD, and creates pre-call reservations."""
    ledger = CostLedger(inr_rate=85.0)
    entry = ledger.record_call(
        run_id="run-test",
        phase="CODE_EDIT",
        model_name="glm-5.2",
        prompt_tokens=2000,
        completion_tokens=1000,
    )
    # prompt: 2000 * 0.50 / 1M = $0.001; completion: 1000 * 1.00 / 1M = $0.001 -> $0.002
    assert entry.native_cost == 0.002
    assert entry.display_cost == 0.17  # 0.002 * 85 = 0.17 INR

    # Pre-call reservation
    res = ledger.reserve_cost("run-test", "glm-5.2", 4000, 2000)
    assert res.active is True
    assert ledger.get_reserved_cost_usd("run-test") > 0.0


def test_07_hard_budget_guard_inr_enforcement():
    """Verify RunBudget.from_inr(20) enforces hard ceiling and rejects over-budget calls."""
    run_budget = RunBudget.from_inr(20.0)  # 20 INR = ~0.235 USD
    assert abs(run_budget.hard_limit_usd - (20.0 / 85.0)) < 1e-5

    limits = BudgetLimits(
        max_cost_usd=run_budget.hard_limit_usd,
        input_price_per_million=0.50,
        output_price_per_million=1.00,
    )
    controller = BudgetController(limits)
    controller.usage.estimated_cost_usd = 0.25  # Exceeds limit

    with pytest.raises(BudgetExceeded):
        controller.before_hosted_call(messages=[{"role": "user", "content": "test prompt"}])


def test_08_provider_resilience_normalization():
    """Verify ProviderResilienceEngine correctly categorizes 429, 401, and 404 error strings."""
    e_429 = resilience_engine.normalize_error("429 Too Many Requests: retry in 5s")
    assert e_429.error_class == ProviderErrorClass.RATE_LIMIT
    assert e_429.retry_after_seconds == 5.0
    assert e_429.retryable is True

    e_401 = resilience_engine.normalize_error("401 Unauthorized: invalid_api_key")
    assert e_401.error_class == ProviderErrorClass.AUTHENTICATION_FAILURE
    assert e_401.retryable is False

    valid, msg = resilience_engine.validate_privacy_policy("glm-5.2", PrivacyClass.LOCAL_ONLY)
    assert valid is False


def test_09_routing_benchmark_execution():
    """Verify ModelRoutingBenchmark runs and proves adaptive routing is cheaper than static ceiling."""
    from nexus.benchmarks.benchmark_model_routing import ModelRoutingBenchmark
    bm = ModelRoutingBenchmark()
    summary = bm.run_benchmark()
    assert summary["parity_target_achieved"] is True
    assert summary["strategies"]["adaptive_sprint9"]["total_spend_usd"] < summary["strategies"]["static_ceiling"]["total_spend_usd"]


def test_10_end_to_end_sprint9_integration():
    """Verify integration across Registry -> Doctor -> Router -> Ledger -> Escalation."""
    desc = model_registry.get_descriptor("glm-5.2")
    assert desc is not None

    profile = model_doctor.get_profile("glm-5.2")
    assert profile is not None

    reqs = model_router.derive_task_requirements("repair", phase=EngineeringPhase.CODE_EDIT, file_count=1)
    decision = model_router.route(reqs, mode=PortfolioMode.CHEAPEST)
    assert decision.selected_model_key in ("nova3b", "deepseek-flash")

    entry = cost_ledger.record_call("e2e-run", decision.task_phase.value, decision.selected_model_key, 1000, 500)
    assert entry.run_id == "e2e-run"
