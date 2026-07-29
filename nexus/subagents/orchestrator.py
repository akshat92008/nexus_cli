"""
Subagent Orchestrator — manages parallel execution of subagents.

Spawns isolated agent instances, executes them (sequentially or parallel),
and aggregates their results into a unified report.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from nexus.subagents.base import BaseSubagent, SubagentResult, SubagentStatus


class SubagentOrchestrator:
    """
    Manages the lifecycle of subagents — spawning, execution, and result aggregation.

    Features:
    - Sequential or parallel execution
    - Result aggregation into unified reports
    - Timeout management
    - Error isolation (one subagent failing doesn't affect others)

    Usage:
        orchestrator = SubagentOrchestrator(api_key="...", model_id="...")

        # Add subagents
        orchestrator.add(SecurityAuditor(task="Scan for XSS"))
        orchestrator.add(TestWriter(task="Write tests for auth.py"))

        # Execute all
        results = orchestrator.run_all()

        # Get aggregated report
        print(orchestrator.format_report(results))
    """

    def __init__(
        self,
        api_key: str,
        model_id: str,
        working_dir: str = "",
        max_workers: int = 3,
        timeout: int = 300,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.working_dir = working_dir
        self.max_workers = max_workers
        self.timeout = timeout
        self._subagents: list[BaseSubagent] = []
        self._results: list[SubagentResult] = []

    def add(self, subagent: BaseSubagent):
        """Add a subagent to the orchestration queue."""
        subagent.working_dir = subagent.working_dir or self.working_dir
        self._subagents.append(subagent)

    def clear(self):
        """Clear all subagents."""
        self._subagents.clear()
        self._results.clear()

    def run_all(self, parallel: bool = True) -> list[SubagentResult]:
        """
        Execute all queued subagents.

        Args:
            parallel: If True, run subagents in parallel using ThreadPoolExecutor.
                      If False, run sequentially.

        Returns:
            List of SubagentResult objects.
        """
        if not self._subagents:
            return []

        if parallel and len(self._subagents) > 1:
            results = self._run_parallel()
        else:
            results = self._run_sequential()

        self._results = results
        return results

    def run_single(self, subagent: BaseSubagent) -> SubagentResult:
        """Execute a single subagent immediately."""
        return self._execute_subagent(subagent)

    def get_results(self) -> list[SubagentResult]:
        """Get the results from the last run."""
        return self._results

    def format_report(self, results: list[SubagentResult] | None = None) -> str:
        """Format a unified report from all subagent results."""
        results = results or self._results
        if not results:
            return "No subagent results available."

        lines = [
            "═══════════════════════════════════════════",
            "  🤖 Subagent Team Report",
            "═══════════════════════════════════════════",
            "",
        ]

        succeeded = sum(1 for r in results if r.succeeded)
        lines.append(f"  Agents: {len(results)} | Passed: {succeeded} | Failed: {len(results) - succeeded}")
        lines.append("")

        for result in results:
            lines.append(result.format_report())
            lines.append("")

        # Aggregate findings
        all_findings = []
        all_errors = []
        all_files = set()
        total_tool_calls = 0

        for r in results:
            all_findings.extend(r.findings)
            all_errors.extend(r.errors)
            all_files.update(r.files_touched)
            total_tool_calls += r.tool_calls_made

        if all_findings:
            lines.append("📋 Combined Findings:")
            for f in all_findings[:20]:
                lines.append(f"  • {f}")

        if all_errors:
            lines.append("")
            lines.append("⚠️ Issues:")
            for e in all_errors[:10]:
                lines.append(f"  ✗ {e}")

        lines.append("")
        lines.append(f"  Total tool calls: {total_tool_calls}")
        lines.append(f"  Files analyzed: {len(all_files)}")
        lines.append("═══════════════════════════════════════════")

        return "\n".join(lines)

    def get_context_for_main_agent(self, results: list[SubagentResult] | None = None) -> str:
        """
        Generate a compact context string for the main agent
        summarizing what subagents found.
        """
        results = results or self._results
        if not results:
            return ""

        parts = ["\n[SUBAGENT REPORTS]"]
        for r in results:
            status = "✅" if r.succeeded else "❌"
            parts.append(f"\n{status} {r.subagent_name}: {r.summary[:500]}")
            if r.findings:
                for f in r.findings[:5]:
                    parts.append(f"  • {f}")
            if r.errors:
                for e in r.errors[:3]:
                    parts.append(f"  ✗ {e}")

        parts.append("[END SUBAGENT REPORTS]\n")
        return "\n".join(parts)

    # ── Private Methods ──────────────────────────────────────────────────

    def _run_sequential(self) -> list[SubagentResult]:
        """Run subagents one at a time."""
        results = []
        for subagent in self._subagents:
            try:
                result = self._execute_subagent(subagent)
                results.append(result)
            except Exception as e:
                results.append(SubagentResult(
                    subagent_name=subagent.name,
                    task=subagent.task,
                    status=SubagentStatus.FAILED,
                    summary=f"Execution error: {e}",
                    errors=[str(e)],
                ))
        return results

    def _run_parallel(self) -> list[SubagentResult]:
        """Run subagents in parallel using threads."""
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_subagent = {
                executor.submit(self._execute_subagent, sa): sa
                for sa in self._subagents
            }

            for future in as_completed(future_to_subagent, timeout=self.timeout):
                subagent = future_to_subagent[future]
                try:
                    result = future.result(timeout=self.timeout)
                    results.append(result)
                except Exception as e:
                    results.append(SubagentResult(
                        subagent_name=subagent.name,
                        task=subagent.task,
                        status=SubagentStatus.FAILED,
                        summary=f"Execution error: {e}",
                        errors=[str(e)],
                    ))

        return results

    def _execute_subagent(self, subagent: BaseSubagent) -> SubagentResult:
        """Execute a single subagent using a fresh Agent instance."""
        start_time = time.monotonic()
        subagent.status = SubagentStatus.RUNNING

        try:
            # Import here to avoid circular imports
            from nexus.agent import Agent

            # Create a fresh, isolated agent for this subagent
            agent = Agent(
                api_key=self.api_key,
                model_key="deepseek-v4",  # Use default model
                working_dir=subagent.working_dir or self.working_dir,
            )

            # Override system prompt with subagent's prompt
            agent.set_system_prompt(subagent.get_system_prompt_full())

            # Disable auto-save for subagents (we don't want to pollute history)
            agent._auto_save_enabled = False

            # Run the subagent's task
            content, events = agent.run_non_interactive(subagent.get_initial_prompt())

            duration = int((time.monotonic() - start_time) * 1000)

            # Process the result
            result = subagent.process_result(content, events)
            result.duration_ms = duration
            result.started_at = datetime.now().isoformat()
            result.completed_at = datetime.now().isoformat()

            subagent.status = SubagentStatus.COMPLETED
            return result

        except Exception as e:
            duration = int((time.monotonic() - start_time) * 1000)
            subagent.status = SubagentStatus.FAILED

            return SubagentResult(
                subagent_name=subagent.name,
                task=subagent.task,
                status=SubagentStatus.FAILED,
                summary=f"Subagent failed: {e}",
                errors=[str(e)],
                duration_ms=duration,
            )

    def list_subagents(self) -> list[dict]:
        """List all queued subagents."""
        return [sa.to_dict() for sa in self._subagents]
