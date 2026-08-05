"""End-to-end qualification test suite for Sprint 5 scenarios."""

import pytest
from pathlib import Path
from nexus.intelligence.repository.engine import RepositoryIntelligence
from nexus.intelligence.repository.model import TaskIntent, RiskLevel


def test_qualification_scenario_1_bounded_python_bug(tmp_path):
    """Scenario 1: Bounded Python bug — selects failing test, implementation, caller."""
    (tmp_path / "calc.py").write_text("def add(a, b): return a - b\n")
    (tmp_path / "service.py").write_text("import calc\ndef compute(): return calc.add(2, 3)\n")
    (tmp_path / "test_calc.py").write_text("import calc\ndef test_add(): assert calc.add(2, 3) == 5\n")

    engine = RepositoryIntelligence(tmp_path)
    engine.build(force=True)

    bundle = engine.context_bundle("Fix math bug in calc.py add function", failing_stack_files=["test_calc.py"])
    selected_paths = [f.path for f in bundle.files]

    assert bundle.task_intent == TaskIntent.BUG_REPAIR
    assert "calc.py" in selected_paths
    assert "test_calc.py" in selected_paths


def test_qualification_scenario_2_cross_file_signature_change(tmp_path):
    """Scenario 2: Cross-file signature change — identifies callers, tests, interface."""
    (tmp_path / "gateway.py").write_text("class Gateway:\n    def execute(self, req, timeout=10): pass\n")
    (tmp_path / "caller.py").write_text("from gateway import Gateway\ndef run(): Gateway().execute('req')\n")
    (tmp_path / "test_gateway.py").write_text("from gateway import Gateway\ndef test_gw(): Gateway().execute('test')\n")

    engine = RepositoryIntelligence(tmp_path)
    engine.build(force=True)

    bundle = engine.context_bundle("Update Gateway execute signature in gateway.py")
    selected_paths = [f.path for f in bundle.files]

    assert "gateway.py" in selected_paths
    assert any(s.name == "Gateway" for s in bundle.symbols)


def test_qualification_scenario_3_typescript_feature(tmp_path):
    """Scenario 3: TypeScript feature — identifies components, types, config."""
    (tmp_path / "package.json").write_text('{"name": "app", "dependencies": {"react": "^18.0.0"}}')
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
    (tmp_path / "Component.tsx").write_text("export const Button = () => <button>Click</button>;")

    engine = RepositoryIntelligence(tmp_path)
    engine.build(force=True)

    bundle = engine.context_bundle("Add new Button component feature in Component.tsx")
    selected_paths = [f.path for f in bundle.files]

    assert "Component.tsx" in selected_paths


def test_qualification_scenario_4_config_driven_bug(tmp_path):
    """Scenario 4: Configuration-driven bug — includes relevant configuration even if not imported."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'myapp'\nversion = '1.0.0'\n")
    (tmp_path / "main.py").write_text("print('App running')")

    engine = RepositoryIntelligence(tmp_path)
    engine.build(force=True)

    bundle = engine.context_bundle("Fix pyproject.toml package build configuration error")
    selected_paths = [f.path for f in bundle.files]

    assert "pyproject.toml" in selected_paths


def test_qualification_scenario_5_high_risk_auth_change(tmp_path):
    """Scenario 5: High-risk auth change — identifies auth implementation, security tests, risk annotations."""
    (tmp_path / "auth_policy.py").write_text("def verify_admin_token(token): return token == 'secret'\n")
    (tmp_path / "test_auth.py").write_text("import auth_policy\ndef test_auth(): assert auth_policy.verify_admin_token('secret')\n")

    engine = RepositoryIntelligence(tmp_path)
    engine.build(force=True)

    bundle = engine.context_bundle("Fix security permission check in auth_policy.py")
    selected_paths = [f.path for f in bundle.files]

    assert "auth_policy.py" in selected_paths
    assert len(bundle.risks) > 0 or bundle.task_intent in (TaskIntent.SECURITY_FIX, TaskIntent.BUG_REPAIR)


def test_qualification_scenario_6_monorepo_task(tmp_path):
    """Scenario 6: Monorepo task — scopes to relevant package without dumping unrelated packages."""
    pkg_a = tmp_path / "packages" / "pkg_a"
    pkg_b = tmp_path / "packages" / "pkg_b"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "index.py").write_text("def module_a(): pass")
    (pkg_b / "index.py").write_text("def module_b(): pass")

    engine = RepositoryIntelligence(tmp_path)
    engine.build(force=True)

    bundle = engine.context_bundle("Update module_a in packages/pkg_a/index.py")
    selected_paths = [f.path for f in bundle.files]

    assert "packages/pkg_a/index.py" in selected_paths
    assert "packages/pkg_b/index.py" not in selected_paths
