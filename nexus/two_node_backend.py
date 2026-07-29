"""
Two-node Nexus execution backend.

Ceiling: selected NVIDIA API model plans/decomposes and handles escalations.
Intern: local Nova model executes atomic subtasks through the existing Nova
guardrail path.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from nexus.code_validation import GeneratedCodeValidator
from nexus.nova_backend import PROMPT_PATH, NovaPipelineBackend, NovaToolProposal
from nexus.nova_runtime import (
    CEILING_SYSTEM_PROMPT,
    AtomicTask,
    CeilingNode,
    ConstraintExtractor,
    ConstraintVerifier,
    InternNode,
    NovaOutputParser,
    TaskGuardrail,
    TestExecutor,
    extract_prompt_paths,
)


class CeilingCallTimeout(TimeoutError):
    """Raised when a Ceiling API call exceeds Nexus' hard timeout."""


@contextlib.contextmanager
def ceiling_timeout(seconds: int):
    """Hard timeout for blocking Ceiling API calls on Unix-like systems."""
    can_use_alarm = (
        seconds > 0
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not can_use_alarm:
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise CeilingCallTimeout(f"Ceiling API call exceeded {seconds}s")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _run_ceiling_call(call, timeout_seconds: float):
    """Run a blocking provider call with a timeout in CLI and worker threads."""
    if timeout_seconds <= 0:
        return call()
    if (
        hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    ):
        with ceiling_timeout(int(timeout_seconds)):
            return call()

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nexus-ceiling")
    future = executor.submit(call)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise CeilingCallTimeout(
            f"Ceiling API call exceeded {timeout_seconds:g}s"
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


CEILING_DIRECT_SYSTEM = """You are the Ceiling node in a two-node coding agent.
You are executing one atomic subtask directly because Nova failed guardrails.

Return ONLY one JSON object conforming to nova.patch.v1:
{
  "schema": "nova.patch.v1",
  "thinking": "Brief explanation of the solution.",
  "files": [
    {
      "path": "THE_EXACT_PATH_FROM_THE_SUBTASK",
      "action": "CREATE or MODIFY",
      "language": "the real source language",
      "content": "the complete file content"
    }
  ],
  "test_command": ""
}

Do not wrap the JSON in Markdown. Never invent a path, add shell commands, or include prose
outside the JSON object. For CREATE or MODIFY, content must be the complete file."""


@dataclass
class SubtaskExecution:
    """Visible execution record for one two-node subtask."""

    task: AtomicTask
    node: str
    verdict: str
    attempts: int = 0
    raw_output: str = ""
    intern_raw_output: str = ""
    guardrail_log: str = ""
    proposals: list[NovaToolProposal] = field(default_factory=list)
    escalated: bool = False
    error: str = ""
    route_reason: str = ""


@dataclass
class TwoNodeResult:
    """Complete two-node turn result."""

    request: str
    ceiling_model: str
    intern_model: str
    tasks: list[AtomicTask] = field(default_factory=list)
    executions: list[SubtaskExecution] = field(default_factory=list)
    decomposition_raw: str = ""

    @property
    def proposals(self) -> list[NovaToolProposal]:
        all_proposals: list[NovaToolProposal] = []
        for execution in self.executions:
            all_proposals.extend(execution.proposals)
        return all_proposals

    def format_breakdown(self) -> str:
        lines = [
            "Two-node execution breakdown",
            f"Ceiling: {self.ceiling_model}",
            f"Intern: {self.intern_model}",
            "",
            "Decomposition:",
        ]
        if not self.tasks:
            lines.append("  (no subtasks)")
        for task in self.tasks:
            lines.append(
                f"  [{task.id}] scope={task.scope_level} expected_files={task.expected_files} "
                f"deps={task.depends_on} :: {task.description}"
            )

        lines.append("")
        lines.append("Execution:")
        for execution in self.executions:
            marker = "Nova-then-escalated" if execution.escalated else execution.node
            lines.append(
                f"  [{execution.task.id}] node={marker} attempts={execution.attempts} "
                f"verdict={execution.verdict}"
            )
            if execution.route_reason:
                lines.append(f"      route: {execution.route_reason}")
            if execution.error:
                lines.append(f"      error: {execution.error}")
            if execution.guardrail_log:
                for log_line in execution.guardrail_log.splitlines():
                    lines.append(f"      {log_line}")
            if execution.raw_output:
                lines.append("      raw:")
                for raw_line in execution.raw_output.splitlines():
                    lines.append(f"        {raw_line}")
        return "\n".join(lines)


class _NvidiaCompletionsShim:
    """Expose NvidiaClient.chat_sync through the OpenAI shape expected by Nova helpers."""

    def __init__(self, client, model_id: str):
        self._client = client
        self._model_id = model_id

    def create(self, model: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048):
        response = self._client.chat_sync(
            model_id=model or self._model_id,
            messages=messages,
            tools=None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(total_tokens=total_tokens),
        )


class NvidiaCeilingNode:
    """Ceiling node backed by the selected Nexus NVIDIA API model."""

    def __init__(self, client, model_id: str):
        self.nexus_client = client
        self.model_name = model_id
        self.tokens_used = 0
        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=_NvidiaCompletionsShim(client, model_id))
        )
        self._parser_node = CeilingNode(provider="manual")

    def decompose(self, request: str, planner_context: str = "") -> tuple[list[AtomicTask], str]:
        prompt = request
        if planner_context:
            prompt = f"{planner_context}\n\nUser request:\n{request}"
        timeout = int(os.environ.get("NEXUS_CEILING_CALL_TIMEOUT", "60"))
        try:
            response = _run_ceiling_call(
                lambda: self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                CEILING_SYSTEM_PROMPT
                                + "\n\nFor every non-vague task, make the description include: "
                                "target file/path, action CREATE or MODIFY, exact expected file count, "
                                "and any literal constraints such as status codes or required strings. "
                                "Always ensure single-file tasks include a valid executable main entrypoint "
                                "(e.g., func main() in Go, int main() in C++) and deadlock-free concurrency."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2048,
                ),
                timeout,
            )
            text = response.choices[0].message.content or ""
            self.tokens_used += getattr(response.usage, "total_tokens", 0)
            tasks = self._parser_node._parse_tasks(text)
            if tasks:
                return tasks, text
        except Exception:
            # Fallback to single atomic local task when remote API is rate limited or unavailable
            pass

        fallback_task = AtomicTask(
            id=1,
            description=request,
            scope_level="atomic",
            expected_files=1,
            depends_on=[],
        )
        return [fallback_task], f"Decomposition local fallback for: {request}"

    def execute_direct(self, task: AtomicTask, context: str, failure_reason: str) -> str:
        prompt = (
            f"Subtask:\n{task.description}\n\n"
            f"Nova guardrail failure:\n{failure_reason}\n\n"
            f"Workspace context:\n{context or '(none)'}"
        )
        timeout = int(os.environ.get("NEXUS_CEILING_CALL_TIMEOUT", "60"))
        try:
            response = _run_ceiling_call(
                lambda: self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": CEILING_DIRECT_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=4096,
                ),
                timeout,
            )
            self.tokens_used += getattr(response.usage, "total_tokens", 0)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"<<THINKING>>\nCeiling remote call failed ({e}). Proceeding with local resolution.\n\n<<FILES>>\n"


class TwoNodeBackend:
    """Run a Nexus request through Ceiling decomposition and Nova Intern execution."""

    def __init__(
        self,
        client,
        ceiling_model_id: str,
        ceiling_model_name: str,
        working_dir: str,
        intern_model: str = "nova_codex",
    ):
        self.working_dir = Path(working_dir).resolve()
        self.ceiling = NvidiaCeilingNode(client, ceiling_model_id)
        self.ceiling_model_name = ceiling_model_name
        self.intern_model = intern_model
        self.parser = NovaOutputParser()
        self.escalation_log_path = self.working_dir / ".nexusai" / "escalations.jsonl"

    def run(self, request: str, planner_analysis: dict | None = None) -> TwoNodeResult:
        planner_context = self._planner_context(planner_analysis)
        try:
            tasks, raw_decomposition = self.ceiling.decompose(request, planner_context=planner_context)
        except Exception as err:
            tasks = [AtomicTask(id=1, description=request)]
            raw_decomposition = f"Single-task fallback due to decomposition error: {err}"

        result = TwoNodeResult(
            request=request,
            ceiling_model=self.ceiling_model_name,
            intern_model=self.intern_model,
            tasks=tasks,
            decomposition_raw=raw_decomposition,
        )

        with tempfile.TemporaryDirectory(prefix="nexus_two_node_") as tmp:
            verification_dir = Path(tmp)
            self._seed_workspace(request, tasks, verification_dir)
            test_executor = TestExecutor(workspace_dir=str(verification_dir))
            intern = InternNode(model=self.intern_model)
            guardrail = TaskGuardrail(max_reroutes=1)
            manual_constraint_node = CeilingNode(provider="manual")
            constraint_extractor = ConstraintExtractor(manual_constraint_node)
            constraint_verifier = ConstraintVerifier(manual_constraint_node)

            context_accumulator = ""
            converter = NovaPipelineBackend(model=self.intern_model, working_dir=str(self.working_dir))

            for task in tasks:
                route, route_reason = self._route_task(task)
                if route == "ceiling":
                    execution = self._escalate_to_ceiling(
                        task=task,
                        validation_prompt=request,
                        previous=SubtaskExecution(
                            task=task,
                            node="Ceiling directly",
                            verdict="DIRECT_ROUTE",
                            error=route_reason,
                            route_reason=route_reason,
                        ),
                        test_executor=test_executor,
                        converter=converter,
                        context_accumulator=context_accumulator,
                    )
                    execution.route_reason = route_reason
                else:
                    execution = self._execute_with_intern(
                        task=task,
                        validation_prompt=request,
                        intern=intern,
                        guardrail=guardrail,
                        constraint_extractor=constraint_extractor,
                        constraint_verifier=constraint_verifier,
                        test_executor=test_executor,
                        context_accumulator=context_accumulator,
                        converter=converter,
                    )
                    execution.route_reason = route_reason

                if execution.proposals and not execution.escalated:
                    context_accumulator += self._context_from_output(execution.raw_output)

                if not execution.proposals and execution.verdict != "VALIDATED":
                    execution = self._escalate_to_ceiling(
                        task=task,
                        validation_prompt=request,
                        previous=execution,
                        test_executor=test_executor,
                        converter=converter,
                        context_accumulator=context_accumulator,
                    )
                    self._log_escalation(request, execution)

                if execution.proposals:
                    context_accumulator += self._context_from_output(execution.raw_output)

                result.executions.append(execution)

        return result

    def _execute_with_intern(
        self,
        task: AtomicTask,
        validation_prompt: str,
        intern: InternNode,
        guardrail: TaskGuardrail,
        constraint_extractor: ConstraintExtractor,
        constraint_verifier: ConstraintVerifier,
        test_executor: TestExecutor,
        context_accumulator: str,
        converter: NovaPipelineBackend,
    ) -> SubtaskExecution:
        logs: list[str] = []
        pre_verdict = guardrail.pre_check(task)
        logs.append(str(pre_verdict))
        if not pre_verdict.passed:
            return SubtaskExecution(
                task=task,
                node="Nova",
                verdict=pre_verdict.type.value,
                attempts=0,
                guardrail_log="\n".join(logs),
                error=pre_verdict.reason,
            )

        constraints = constraint_extractor.extract(task.description)
        for constraint in constraints:
            logs.append(f"CONSTRAINT {constraint.type}: {constraint.value}")

        task_context = self._task_context(task, test_executor.workspace_dir, context_accumulator)
        override_prompt = ""
        last_raw = ""
        last_failure = ""
        attempts = 0

        for attempt in range(2):
            attempts = attempt + 1
            task_result = intern.execute(task, context=task_context, override_prompt=override_prompt)
            response = task_result.response
            last_raw = response.raw_text
            with tempfile.TemporaryDirectory(prefix="nexus_intern_candidate_") as attempt_tmp:
                shutil.copytree(test_executor.workspace_dir, attempt_tmp, dirs_exist_ok=True)
                attempt_executor = TestExecutor(workspace_dir=attempt_tmp)
                failure = self._check_intern_response(
                    task=task,
                    validation_prompt=validation_prompt,
                    response=response,
                    constraints=constraints,
                    constraint_verifier=constraint_verifier,
                    guardrail=guardrail,
                    test_executor=attempt_executor,
                )

                if not failure:
                    self._promote_candidate_files(response.files, attempt_tmp, test_executor.workspace_dir)
                    proposals: list[NovaToolProposal] = []
                    summary = "\n".join(logs + [f"VALIDATED attempt={attempts}: schema, constraints, disk replay, and compiler checks passed"])
                    for file_action in response.files:
                        proposals.extend(converter._file_action_to_tool_calls(file_action, summary))
                    return SubtaskExecution(
                        task=task,
                        node="Nova",
                        verdict="VALIDATED",
                        attempts=attempts,
                        raw_output=last_raw,
                        guardrail_log=summary,
                        proposals=proposals,
                    )

            last_failure = failure
            logs.append(f"GUARDRAIL FAILED attempt={attempts}: {failure}")
            if attempt == 0:
                override_prompt = self._retry_prompt(task.description, constraints, failure)

        return SubtaskExecution(
            task=task,
            node="Nova",
            verdict="ESCALATE",
            attempts=attempts,
            raw_output=last_raw,
            guardrail_log="\n".join(logs),
            error=last_failure,
        )

    def _check_intern_response(
        self,
        task: AtomicTask,
        validation_prompt: str,
        response,
        constraints,
        constraint_verifier: ConstraintVerifier,
        guardrail: TaskGuardrail,
        test_executor: TestExecutor,
    ) -> str:
        if not response.is_valid:
            return f"Format errors: {response.parse_errors}"

        schema = guardrail.schema_check(task, response.raw_text)
        if not schema.passed:
            return schema.reason

        prompt_paths = extract_prompt_paths(validation_prompt) or list(set(PROMPT_PATH.findall(task.description)))
        if len(prompt_paths) == 1 and len(response.files) == 1:
            expected_path = os.path.normpath(prompt_paths[0].lstrip("/\\"))
            actual_path = os.path.normpath(response.files[0].path.lstrip("/\\"))
            if actual_path != expected_path:
                return f"Path validator failed: output used {actual_path}, requirement is exact path {expected_path}"

        if constraints:
            passed, reason = constraint_verifier.verify(constraints, response.files)
            if not passed:
                return reason

        func_name = guardrail.function_name_check(task, response.raw_text, task.description)
        if not func_name.passed:
            return func_name.reason

        try:
            test_executor.write_files(response.files, strict_verify=True)
        except ValueError as exc:
            return f"Disk verification failed: {exc}"

        post = guardrail.post_check(task, response.raw_text)
        if not post.passed:
            return post.reason

        consistency = guardrail.thinking_files_consistency_check(task, response.raw_text)
        if not consistency.passed:
            return consistency.reason

        code_checks = GeneratedCodeValidator(test_executor.workspace_dir).validate(
            response.files, validation_prompt
        )
        failed = [check for check in code_checks if not check.passed]
        if failed:
            return "Compiler/validator failed: " + " | ".join(check.format() for check in failed)

        return ""

    def _escalate_to_ceiling(
        self,
        task: AtomicTask,
        validation_prompt: str,
        previous: SubtaskExecution,
        test_executor: TestExecutor,
        converter: NovaPipelineBackend,
        context_accumulator: str,
    ) -> SubtaskExecution:
        context = self._task_context(task, test_executor.workspace_dir, context_accumulator)
        logs = [previous.guardrail_log]
        proposals: list[NovaToolProposal] = []
        verdict = "CEILING_FAILED"
        error = previous.error
        raw_attempts: list[str] = []
        parsed = None

        for ceiling_attempt in range(1, 3):
            try:
                raw = self.ceiling.execute_direct(task, context=context, failure_reason=error)
            except Exception as exc:
                error = f"Ceiling execution error: {exc}"
                logs.append(f"ESCALATION attempt={ceiling_attempt}: {error}")
                continue
            raw_attempts.append(raw)
            parsed = self._parse_ceiling_response(raw)

            # Some hosted models omit the wrapper despite being given the
            # strict protocol. Recover file blocks, but never invent metadata.
            if not parsed.is_valid and not parsed.files:
                fallback_errors = []
                extracted_files = self.parser._parse_file_blocks(raw, fallback_errors)
                if extracted_files:
                    parsed.files = extracted_files
                    parsed.thinking = parsed.thinking or "Direct Ceiling execution"
                    parsed.parse_errors = []

            if not parsed.files or parsed.parse_errors:
                error = f"Ceiling direct output parse errors: {parsed.parse_errors}"
                logs.append(f"ESCALATION attempt={ceiling_attempt}: {error}")
                continue

            expected_paths = extract_prompt_paths(validation_prompt) or extract_prompt_paths(task.description)
            actual_paths = [os.path.normpath(item.path.lstrip("/\\")) for item in parsed.files]
            if len(expected_paths) == 1 and actual_paths != [os.path.normpath(expected_paths[0].lstrip("/\\"))]:
                error = f"Ceiling path validator expected {expected_paths[0]}, got {actual_paths}"
                logs.append(f"ESCALATION attempt={ceiling_attempt}: {error}")
                continue

            with tempfile.TemporaryDirectory(prefix="nexus_ceiling_candidate_") as candidate_tmp:
                shutil.copytree(test_executor.workspace_dir, candidate_tmp, dirs_exist_ok=True)
                candidate_executor = TestExecutor(workspace_dir=candidate_tmp)
                try:
                    candidate_executor.write_files(parsed.files, strict_verify=True)
                    code_checks = GeneratedCodeValidator(candidate_tmp).validate(
                        parsed.files, validation_prompt
                    )
                    failed = [check for check in code_checks if not check.passed]
                    if failed:
                        raise ValueError(" | ".join(check.format() for check in failed))
                    manual = CeilingNode(provider="manual")
                    constraints = ConstraintExtractor(manual).extract(task.description)
                    passed, reason = ConstraintVerifier(manual).verify(constraints, parsed.files)
                    if not passed:
                        raise ValueError(reason)
                    self._promote_candidate_files(parsed.files, candidate_tmp, test_executor.workspace_dir)
                except ValueError as exc:
                    error = f"Ceiling direct validation failed: {exc}"
                    logs.append(f"ESCALATION attempt={ceiling_attempt}: {error}")
                    continue

            verdict = "CEILING_PASS"
            error = ""
            logs.append(f"ESCALATION attempt={ceiling_attempt}: Ceiling schema, path, disk, constraint, and compiler validation passed.")
            summary = "\n".join(item for item in logs if item)
            for file_action in parsed.files:
                proposals.extend(converter._file_action_to_tool_calls(file_action, summary))
            break

        raw = "\n\n".join(
            f"[CEILING ATTEMPT {index}]\n{item}" for index, item in enumerate(raw_attempts, 1)
        )

        return SubtaskExecution(
            task=task,
            node="Ceiling directly",
            verdict=verdict,
            attempts=previous.attempts,
            raw_output=raw,
            intern_raw_output=previous.raw_output,
            guardrail_log="\n".join(log for log in logs if log),
            proposals=proposals,
            escalated=True,
            error=error,
        )

    @staticmethod
    def _promote_candidate_files(files, candidate_dir: str, workspace_dir: str) -> None:
        """Copy only validated candidate files into the shared verification tree."""
        candidate_root = Path(candidate_dir).resolve()
        workspace_root = Path(workspace_dir).resolve()
        for file_action in files:
            relative = Path(os.path.normpath(file_action.path.lstrip("/\\")))
            source = (candidate_root / relative).resolve()
            target = (workspace_root / relative).resolve()
            source.relative_to(candidate_root)
            target.relative_to(workspace_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _parse_ceiling_response(self, raw: str):
        """Parse strict output and recover a common accidental nested-fence form."""
        parsed = self.parser.parse(raw)
        if parsed.files and all(item.content.strip() for item in parsed.files):
            return parsed
        nested = re.search(
            r"```language\s*\n"
            r"(?P<headers>(?:#|//)\s*filepath:\s*[^\n]+\n(?:#|//)\s*action:\s*(?:CREATE|MODIFY))\s*\n"
            r"```(?P<language>[A-Za-z0-9_+-]+)\s*\n(?P<code>.*?)```",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        if not nested:
            return parsed
        synthetic = (
            "<<THINKING>>\nRecovered hosted nested-fence response.\n\n<<FILES>>\n"
            f"```{nested.group('language')}\n{nested.group('headers')}\n"
            f"{nested.group('code').rstrip()}\n```"
        )
        recovered = self.parser.parse(synthetic)
        recovered.raw_text = raw
        return recovered

    def _seed_workspace(self, request: str, tasks: list[AtomicTask], verification_dir: Path):
        text = request + "\n" + "\n".join(task.description for task in tasks)
        for raw_path in set(PROMPT_PATH.findall(text)):
            clean_name = raw_path.lstrip("/\\")
            if not clean_name or "." not in clean_name:
                continue
            source = (self.working_dir / clean_name).resolve()
            try:
                source.relative_to(self.working_dir)
            except ValueError:
                continue
            if not source.is_file():
                continue
            try:
                target = verification_dir / clean_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            except Exception:
                pass

    def _task_context(self, task: AtomicTask, workspace_dir: str, context_accumulator: str) -> str:
        chunks = [context_accumulator] if context_accumulator else []
        for raw_path in set(PROMPT_PATH.findall(task.description)):
            clean_name = raw_path.lstrip("/\\")
            if not clean_name or "." not in clean_name:
                continue
            path = Path(workspace_dir) / clean_name
            if path.is_file():
                try:
                    chunks.append(f"# Existing File: {clean_name}\n```\n{path.read_text(encoding='utf-8')}\n```")
                except OSError:
                    pass
        return "\n\n".join(chunks)

    def _retry_prompt(self, task_description: str, constraints, failure: str) -> str:
        required_values = ", ".join(str(item.value) for item in constraints) or "none"
        prompt_paths = sorted(set(PROMPT_PATH.findall(task_description)))
        required_paths = ", ".join(prompt_paths) or "the exact path in the task"
        return (
            "This is the only guardrail repair attempt. Generate a fresh response from the "
            "authoritative file context; do not copy or quote the previous answer.\n\n"
            f"Atomic task:\n{task_description}\n\n"
            f"Guardrail failure to correct:\n{failure}\n\n"
            f"Required path(s): {required_paths}\n"
            f"Required literal value(s): {required_values}\n\n"
            "Required literal values are desired NEW values and may not exist in the file yet. "
            "Locate the old assignment, print, return, or response named by the task and replace it. "
            "Return only the canonical Nova response beginning with <<THINKING>>, then "
            "<<FILES>>. For MODIFY, use an exact short contiguous SEARCH block from the "
            "authoritative file—prefer only the single target line or target statement—followed "
            "by ======= and the replacement. Do not include "
            "unrelated code, excerpt markers, unified diff syntax, or an outer wrapper."
        )

    def _log_escalation(self, request: str, execution: SubtaskExecution):
        """Persist raw escalation evidence as future labeled Nova training data."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "subtask_id": execution.task.id,
            "subtask": execution.task.description,
            "node": "Nova-then-escalated-to-Ceiling",
            "nova_attempts": execution.attempts,
            "final_verdict": execution.verdict,
            "guardrail_failure": execution.error,
            "guardrail_log": execution.guardrail_log,
            "nova_raw_output": execution.intern_raw_output,
            "ceiling_raw_output": execution.raw_output,
            "proposed_tools": [
                {"name": proposal.name, "args": proposal.args}
                for proposal in execution.proposals
            ],
        }
        try:
            self.escalation_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.escalation_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _context_from_output(self, raw_output: str) -> str:
        parsed = self.parser.parse(raw_output)
        chunks = []
        for file_action in parsed.files:
            chunks.append(f"# File: {file_action.path}\n{file_action.content[:1200]}")
        return "\n\n".join(chunks)

    def _planner_context(self, analysis: dict | None) -> str:
        if not analysis:
            return ""
        intent = analysis.get("intent")
        difficulty = analysis.get("difficulty")
        plan_type = analysis.get("plan_type")
        skills = analysis.get("skills_needed", [])
        criteria = analysis.get("acceptance_criteria", [])
        permitted_files = analysis.get("permitted_files", [])
        task_dag = analysis.get("task_dag", [])
        def val(item):
            return item.value if hasattr(item, "value") else str(item)
        context = (
            "Nexus planner analysis:\n"
            f"- intent: {val(intent)}\n"
            f"- difficulty: {val(difficulty)}\n"
            f"- plan_type: {val(plan_type)}\n"
            f"- skills_needed: {', '.join(skills) if skills else 'none'}"
        )
        if permitted_files:
            context += "\n- permitted_files: " + ", ".join(permitted_files)
        if criteria:
            context += "\n- acceptance_criteria:\n" + "\n".join(
                f"  - {item}" for item in criteria
            )
        if task_dag:
            context += "\n- task_dag:\n" + "\n".join(
                f"  - {item.get('id')}: {item.get('title')} "
                f"deps={item.get('depends_on', [])} risk={item.get('risk')}"
                for item in task_dag
            )
        return context

    @staticmethod
    def _route_task(task: AtomicTask) -> tuple[str, str]:
        """Make every Intern/Ceiling routing choice explicit and reproducible."""
        text = task.description.lower()
        if task.scope_level == "vague":
            return "ceiling", "underspecified task; Nova is not allowed to guess"
        if task.expected_files > 1 and ("json" in text or ".json" in text):
            return "ceiling", "multi-file JSON hits Nova's documented filepath-marker weakness"
        high_risk = (
            "concurren", "thread", "async", "broadcast", "tcp", "database", "migration",
            "security", "authentication", "authorization", "architecture", "distributed",
            "merge conflict", "rebase", "package.json", "cargo.toml", "go.mod",
        )
        matched = [term for term in high_risk if term in text]
        if matched:
            return "ceiling", f"complex/high-risk semantics detected: {', '.join(matched[:3])}"
        if len(task.description) > 700:
            return "ceiling", "subtask exceeds the bounded Intern complexity budget"
        return "nova", "atomic, explicit, single-file task within Nova's guarded capability"
