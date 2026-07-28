from dataclasses import dataclass

from nexus.code_validation import GeneratedCodeValidator
from nexus.two_node_backend import TwoNodeBackend
from pipeline import AtomicTask


@dataclass
class Action:
    path: str
    content: str = ""


def test_python_syntax_failure_is_not_approved(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n    pass\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate([Action("broken.py")], "create broken.py")
    assert len(checks) == 1
    assert not checks[0].passed
    assert checks[0].exit_code == 1


def test_entrypoint_requirement_is_enforced(tmp_path):
    path = tmp_path / "main.go"
    path.write_text("package main\n\nfunc helper() {}\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("main.go")], "Create an executable Go program in main.go"
    )
    assert not checks[0].passed
    assert "entrypoint" in checks[0].output


def test_python_main_must_be_called_by_name_guard(tmp_path):
    path = tmp_path / "main.py"
    path.write_text("def main():\n    print('ok')\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("main.py")], "Create a standalone Python program with a main function"
    )
    assert not checks[0].passed
    assert "__name__" in checks[0].output


def test_nonnegative_boundary_guard_cannot_reject_zero(tmp_path):
    path = tmp_path / "counter.py"
    path.write_text("def count(limit):\n    if limit <= 0:\n        return []\n    return list(range(limit + 1))\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("counter.py")], "nonnegative input includes the limit; negative input returns empty"
    )
    assert not checks[0].passed
    assert "zero" in checks[0].output


def test_recursive_javascript_requirement_needs_self_call(tmp_path):
    path = tmp_path / "walk.js"
    path.write_text("function walk(dir) { return []; }\nwalk('.');\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("walk.js")], "recursively list regular files"
    )
    assert not checks[0].passed
    assert "calls itself" in checks[0].output


def test_recursive_relative_paths_need_stable_base(tmp_path):
    path = tmp_path / "walk.js"
    path.write_text(
        "const path = require('path');\n"
        "function walk(dir) { walk(path.join(dir, 'x')); return path.relative(dir, 'x'); }\n"
    )
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("walk.js")], "recursively print paths relative to the provided directory"
    )
    assert not checks[0].passed
    assert "stable user-provided root" in checks[0].output


def test_javascript_cli_main_must_be_invoked(tmp_path):
    path = tmp_path / "cli.js"
    path.write_text("function main() { console.log('ok'); }\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("cli.js")], "Create a Node.js CLI entrypoint"
    )
    assert not checks[0].passed
    assert "never invoked" in checks[0].output


def test_javascript_builtin_usage_needs_import(tmp_path):
    path = tmp_path / "cli.js"
    path.write_text("function main() { fs.readdirSync('.'); }\nmain();\n")
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("cli.js")], "Create a Node.js CLI"
    )
    assert not checks[0].passed
    assert "does not import" in checks[0].output


def test_cpp_exact_output_rejects_trailing_separator(tmp_path):
    path = tmp_path / "main.cpp"
    path.write_text(
        "#include <iostream>\nint main(){ for(int x: {0,1}) std::cout << x << ' '; }\n"
    )
    checks = GeneratedCodeValidator(str(tmp_path)).validate(
        [Action("main.cpp")], "print exactly '0 1' and a newline"
    )
    assert not checks[0].passed
    assert "trailing space" in checks[0].output


def test_routing_sends_known_nova_weak_spots_to_ceiling():
    task = AtomicTask(
        id=1,
        description="Modify package.json and config.json for an async broadcast server",
        expected_files=2,
        scope_level="multi_file",
    )
    route, reason = TwoNodeBackend._route_task(task)
    assert route == "ceiling"
    assert reason
