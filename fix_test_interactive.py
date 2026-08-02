import re

with open("tests/test_cli_coverage.py", "r") as f:
    code = f.read()

code = re.sub(r"def test_handle_benchmark_valid\(\):.*?def test_run_interactive_commands\(\):.*?run_interactive\(agent\)", "", code, flags=re.DOTALL)

tests = """
def test_handle_benchmark_valid():
    from nexus.cli import _handle_benchmark
    with patch.object(sys, "argv", ["nexus", "benchmark", "--manifest", "nonexistent.json"]):
        with patch("nexus.benchmark.BenchmarkSuite.load") as MockLoad:
            with patch("nexus.benchmark.BenchmarkRunner") as MockRunner:
                from types import SimpleNamespace
                MockRunner.return_value.run.return_value = SimpleNamespace(to_dict=lambda: {"summary": {"failed": 0}})
                assert _handle_benchmark() is True

def test_handle_generate_dashboard_valid():
    from nexus.cli import _handle_generate_dashboard
    with patch.object(sys, "argv", ["nexus", "generate-dashboard", "--input", "in.json", "--output", "out.html"]):
        with patch("nexus.dashboard.RegressionDashboard.generate") as mock_gen:
            assert _handle_generate_dashboard() is True

def test_main_cli_doctor():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch.object(sys, "argv", ["nexus", "--doctor"]):
            with patch("nexus.cli.run_doctor") as mock_run:
                mock_run.return_value = (True, "OK")
                with pytest.raises(SystemExit) as excinfo:
                    main()
                assert excinfo.value.code == 0

def test_run_interactive_slash_commands():
    from nexus.cli import handle_slash_command
    with patch("nexus.cli.Agent") as MockAgent:
        agent = MockAgent.return_value
        agent.model_key = "test"
        agent.model_cfg = {"name": "Test", "id": "test", "description": "desc", "context": 10000, "supports_tools": True}
        
        with pytest.raises(SystemExit):
            handle_slash_command("/quit", agent)
        
        assert handle_slash_command("/help", agent) is True
        
        # Test /models arg
        agent.set_model.return_value = True
        assert handle_slash_command("/models gpt-4", agent) is True
        agent.set_model.return_value = False
        assert handle_slash_command("/models gpt-fake", agent) is True
        
        # Test /models
        assert handle_slash_command("/models", agent) is True
        
        # Test /model arg
        agent.set_model.return_value = True
        assert handle_slash_command("/model gpt-4", agent) is True
        agent.set_model.return_value = False
        assert handle_slash_command("/model gpt-fake", agent) is True
        assert handle_slash_command("/model", agent) is True

def test_run_interactive_loop():
    from nexus.cli import run_interactive
    with patch("nexus.cli.Agent") as MockAgent:
        agent = MockAgent.return_value
        agent.model_key = "test"
        agent.model_cfg = {"name": "Test", "id": "test", "description": "desc", "context": 10000, "supports_tools": True}
        agent.working_dir = "/tmp"
        agent.mode_policy.label = "autonomous"
        agent.memory.summary = lambda: "memory"
        
        with patch("rich.console.Console.input", side_effect=["/quit"]):
            with pytest.raises(SystemExit):
                run_interactive(agent)
"""

code += "\n" + tests

with open("tests/test_cli_coverage.py", "w") as f:
    f.write(code)
