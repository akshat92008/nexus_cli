"""
Nova local backend adapter for NexusAI.

Runs the existing CeilingInternPipeline in a temporary verification workspace,
then converts guardrail-passed Nova file actions into Nexus tool calls. The
actual workspace mutation still goes through Agent._execute_tool_with_safety.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any


NOVA_ROOT = Path(__file__).resolve().parents[2]
if str(NOVA_ROOT) not in sys.path:
    sys.path.insert(0, str(NOVA_ROOT))

from pipeline import CeilingInternPipeline  # noqa: E402
from nexus.code_validation import GeneratedCodeValidator  # noqa: E402


PATCH_BLOCK = re.compile(
    r"^<+\s*\r?\n(.*?)^=+\s*\r?\n(.*?)^>+\s*$",
    re.DOTALL | re.MULTILINE,
)
WRAPPED_BLOCK = re.compile(
    r"^<+\s*\r?\n(.*?)^>+\s*$",
    re.DOTALL | re.MULTILINE,
)
PROMPT_PATH = re.compile(
    r"(?:^|\s|`|'|\")([a-zA-Z0-9_\-/]+\.[A-Za-z][A-Za-z0-9]{0,7})(?:$|\s|`|'|\"|\?|\.|,|:|;|\))",
    re.IGNORECASE,
)


@dataclass
class NovaToolProposal:
    """A Nexus tool call proposed by Nova after Nova guardrails passed."""

    name: str
    args: dict[str, Any]
    source_path: str
    guardrail_summary: str


@dataclass
class NovaBackendResult:
    """Result of running Nova through the local pipeline."""

    raw_output: str
    assistant_text: str
    guardrail_output: str
    proposals: list[NovaToolProposal] = field(default_factory=list)


class NovaBackendError(RuntimeError):
    """Raised when the local Nova backend cannot produce guarded actions."""


class NovaPipelineBackend:
    """Thin adapter from Nova pipeline results to Nexus tool proposals."""

    def __init__(self, model: str = "nova_codex", working_dir: str | None = None):
        self.model = model
        self.working_dir = Path(working_dir or os.getcwd()).resolve()

    def run(self, prompt: str, _compiler_repair_attempt: int = 0) -> NovaBackendResult:
        """Run the existing pipeline and return verified Nexus tool proposals."""
        with tempfile.TemporaryDirectory(prefix="nexus_nova_verify_") as tmp:
            verification_dir = Path(tmp)
            self._seed_verification_workspace(prompt, verification_dir)

            pipeline = CeilingInternPipeline(
                ceiling_provider="manual",
                intern_model=self.model,
                workspace_dir=str(verification_dir),
                run_tests=False,
            )

            output_buffer = io.StringIO()
            with contextlib.redirect_stdout(output_buffer):
                pipeline_result = pipeline.run(prompt)
            guardrail_output = output_buffer.getvalue()

            raw_parts: list[str] = []
            response_parts: list[str] = []
            proposals: list[NovaToolProposal] = []

            for task_result in pipeline_result.results:
                response = task_result.response
                if response.raw_text:
                    raw_parts.append(response.raw_text)

                if response.response_text:
                    response_parts.append(response.response_text)
                    continue

                if "<<CLARIFICATION>>" in response.raw_text.upper():
                    response_parts.append(response.raw_text)
                    continue

                if not response.is_valid:
                    response_parts.append(
                        "Nova guardrails rejected the output before Nexus tools ran:\n"
                        + "\n".join(response.parse_errors)
                    )
                    continue

                if response.files and not task_result.files_written:
                    response_parts.append(
                        "Nova guardrails did not accept this file output for application. "
                        "No Nexus file tools were run for it."
                    )
                    continue

                guardrail_summary = self._guardrail_summary_for(task_result, guardrail_output)
                cleaned_proposals: list[NovaToolProposal] = []
                for file_action in response.files:
                    cleaned_proposals.extend(
                        self._file_action_to_tool_calls(file_action, guardrail_summary)
                    )

                # The legacy disk replay intentionally writes Nova's raw patch
                # protocol.  Compile the canonical, marker-free tool proposal
                # that Nexus would actually apply instead.
                clean_dir = verification_dir / "_nexus_clean_candidate"
                clean_dir.mkdir(parents=True, exist_ok=True)
                self._seed_verification_workspace(prompt, clean_dir)
                materialized, materialize_error = self._materialize_proposals(
                    cleaned_proposals, clean_dir
                )
                if materialize_error:
                    response_parts.append(
                        "Nova canonicalization guard rejected the output before Nexus tools ran:\n"
                        + materialize_error
                    )
                    continue

                code_checks = GeneratedCodeValidator(str(clean_dir)).validate(
                    [SimpleNamespace(path=item) for item in materialized],
                    getattr(task_result.task, "description", prompt),
                )
                failed_checks = [check for check in code_checks if not check.passed]
                if failed_checks:
                    failure_text = "\n".join(check.format() for check in failed_checks)
                    if _compiler_repair_attempt == 0:
                        repair_prompt = (
                            f"Original task:\n{prompt}\n\n"
                            "The candidate was rejected by an independent compiler or semantic guard. "
                            "Regenerate a complete solution from the beginning. Correct every reported "
                            "failure without weakening any original requirement.\n\n"
                            f"Verifier output:\n{failure_text}"
                        )
                        repaired = self.run(repair_prompt, _compiler_repair_attempt=1)
                        repaired.raw_output = (
                            "[COMPILER ATTEMPT 1]\n"
                            + "\n\n".join(raw_parts).strip()
                            + "\n\n[COMPILER REPAIR ATTEMPT]\n"
                            + repaired.raw_output
                        ).strip()
                        repaired.guardrail_output = (
                            guardrail_output.strip()
                            + "\n\n[COMPILER REPAIR TRIGGER]\n"
                            + failure_text
                            + "\n\n"
                            + repaired.guardrail_output
                        ).strip()
                        return repaired
                    response_parts.append(
                        "Nova compiler guard rejected the output before Nexus tools ran:\n"
                        + failure_text
                    )
                    continue

                if code_checks:
                    guardrail_summary += "\n" + "\n".join(check.format() for check in code_checks)
                for proposal in cleaned_proposals:
                    proposal.guardrail_summary = guardrail_summary
                    proposal.args["_nova_guardrail"]["summary"] = guardrail_summary
                    proposals.append(proposal)

            assistant_text = "\n\n".join(response_parts).strip()
            if proposals:
                assistant_text = assistant_text or (
                    f"Nova guardrails passed; prepared {len(proposals)} Nexus tool call(s)."
                )
            elif not assistant_text:
                assistant_text = "Nova did not produce any guardrail-approved tool calls."

            return NovaBackendResult(
                raw_output="\n\n".join(raw_parts).strip(),
                assistant_text=assistant_text,
                guardrail_output=guardrail_output.strip(),
                proposals=proposals,
            )

    def _seed_verification_workspace(self, prompt: str, verification_dir: Path):
        """Copy prompt-mentioned existing files so Nova's disk gate can verify MODIFY patches."""
        for rel_path in set(PROMPT_PATH.findall(prompt)):
            source = (self.working_dir / rel_path).resolve()
            try:
                source.relative_to(self.working_dir)
            except ValueError:
                continue
            if not source.is_file():
                continue

            target = verification_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _materialize_proposals(
        proposals: list[NovaToolProposal], candidate_dir: Path
    ) -> tuple[list[str], str]:
        """Replay cleaned proposals in an isolated tree for compiler checks."""
        materialized: list[str] = []
        for proposal in proposals:
            target = (candidate_dir / proposal.source_path.lstrip("/\\")).resolve()
            try:
                target.relative_to(candidate_dir.resolve())
            except ValueError:
                return materialized, f"path escapes candidate workspace: {proposal.source_path}"
            target.parent.mkdir(parents=True, exist_ok=True)
            if proposal.name == "write_file":
                target.write_text(str(proposal.args.get("content", "")), encoding="utf-8")
            elif proposal.name == "edit_file":
                if not target.is_file():
                    return materialized, f"edit target does not exist: {proposal.source_path}"
                original = target.read_text(encoding="utf-8")
                old = str(proposal.args.get("old_text", ""))
                if not old or original.count(old) != 1:
                    return materialized, (
                        f"edit search text occurs {original.count(old)} times in "
                        f"{proposal.source_path}; expected exactly once"
                    )
                target.write_text(
                    original.replace(old, str(proposal.args.get("new_text", "")), 1),
                    encoding="utf-8",
                )
            else:
                return materialized, f"unsupported proposal type: {proposal.name}"
            if proposal.source_path not in materialized:
                materialized.append(proposal.source_path)
        return materialized, ""

    def _guardrail_summary_for(self, task_result, guardrail_output: str) -> str:
        """Extract a compact, human-readable guardrail summary for a task."""
        task_id = getattr(task_result.task, "id", "?")
        lines = []
        for line in guardrail_output.splitlines():
            if (
                f"task {task_id}" in line
                or "GUARDRAIL" in line
                or "CONSTRAINT" in line
                or "PASS | Files:" in line
                or "EXECUTION GATE" in line
            ):
                lines.append(line.strip())
        if not lines:
            status = task_result.test_status or "UNKNOWN"
            files = ", ".join(f.path for f in task_result.response.files) or "none"
            lines.append(f"Nova pipeline status={status}; files={files}")
        return "\n".join(lines[-12:])

    def _file_action_to_tool_calls(
        self,
        file_action,
        guardrail_summary: str,
    ) -> list[NovaToolProposal]:
        """Convert a parsed Nova FileAction into one or more Nexus tool calls."""
        action = file_action.action.upper()
        base_meta = {
            "passed": True,
            "summary": guardrail_summary,
        }

        if action == "MODIFY":
            matches = PATCH_BLOCK.findall(file_action.content)
            if matches:
                proposals = []
                for old_text, new_text in matches:
                    proposals.append(
                        NovaToolProposal(
                            name="edit_file",
                            args={
                                "path": file_action.path,
                                "old_text": old_text,
                                "new_text": new_text,
                                "_nova_guardrail": base_meta,
                            },
                            source_path=file_action.path,
                            guardrail_summary=guardrail_summary,
                        )
                    )
                return proposals
            # If action == "MODIFY" but no patch markers were present (e.g. direct full file emission from Ceiling model),
            # fall through to treat content as a full write_file proposal.

        if action == "DELETE":
            raise NovaBackendError(
                f"Nova emitted DELETE for {file_action.path}; Nexus does not apply Nova deletions automatically."
            )

        content = file_action.content

        # Strip markdown fences if content was wrapped in ``` code blocks
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z0-9_-]*\r?\n", "", content)
            content = re.sub(r"\r?\n```$", "", content)

        # Handle trailing filename label artifacts (e.g. >>>>>># File: task_queue.js \n task_queue.js)
        if ">>>>" in content and ("# File:" in content or "# filepath:" in content):
            content = re.split(r">>>+#\s*File:|>>>+#\s*filepath:|>>>+\s*#", content)[0].strip("\n")

        # Handle repetitive block loops (e.g. repeated "# File:" or "# filepath:")
        if "# File:" in content or "# filepath:" in content:
            parts = re.split(r"(?:#\s*filepath:|#\s*File:)", content)
            if len(parts) > 1:
                block = parts[1]
                if "=======" in block:
                    block = block.split("=======", 1)[1]
                extracted = re.split(r">>>+|#\s*File:|#\s*filepath:", block)[0].strip("\n")
                clean_extracted = extracted.strip()
                target_filename = os.path.basename(file_action.path).strip()
                if clean_extracted and clean_extracted != target_filename and clean_extracted != file_action.path.strip():
                    content = extracted
                elif "=======" in parts[0]:
                    pre_content = parts[0].split("=======", 1)[1]
                    content = re.sub(r">>>+.*$", "", pre_content, flags=re.MULTILINE).strip("\n")

        patch_matches = PATCH_BLOCK.findall(content)
        if patch_matches:
            # Nova's CREATE template sometimes puts the new code before the
            # separator. Prefer the post-separator side, but keep a non-empty
            # pre-separator side instead of writing marker scaffolding.
            chunks = []
            for old_text, new_text in patch_matches:
                chunk = new_text if new_text.strip() else old_text
                chunk = re.split(r"^=+\s*$", chunk, maxsplit=1, flags=re.MULTILINE)[0]
                chunk = re.split(r">>>+|#\s*File:|#\s*filepath:", chunk)[0]
                chunks.append(chunk.strip("\n"))
            content = "\n".join(chunks).strip("\n")
        elif "=======" in content and ("<<<<<<<" in content or content.lstrip().startswith("<<<<<<<")):
            pre_sep, post_sep = content.split("=======", 1)
            post_sep = re.split(r">>>+#\s*File:|>>>+#\s*filepath:|#\s*File:|#\s*filepath:", post_sep)[0]
            clean_post = re.sub(r"^>+\s*$", "", post_sep, flags=re.MULTILINE).strip("\n")
            if clean_post:
                content = clean_post
            else:
                pre_sep = pre_sep.split("<<<<<<<", 1)[-1]
                content = re.sub(r"^<+\s*$", "", pre_sep, flags=re.MULTILINE).strip("\n")
        elif "@@" in content and ("---" in content or "+++" in content):
            diff_proposals = _unified_diff_to_proposals(file_action.path, content, base_meta, guardrail_summary)
            if diff_proposals:
                return diff_proposals
        else:
            wrapped_match = WRAPPED_BLOCK.search(content)
            if wrapped_match:
                content = wrapped_match.group(1).strip("\n")

        if not content.strip():
            raise NovaBackendError(f"Nova emitted 0-byte empty content for {file_action.path}")

        return [
            NovaToolProposal(
                name="write_file",
                args={
                    "path": file_action.path,
                    "content": content,
                    "_nova_guardrail": base_meta,
                },
                source_path=file_action.path,
                guardrail_summary=guardrail_summary,
            )
        ]


def _unified_diff_to_proposals(
    file_path: str, diff_text: str, base_meta: dict, guardrail_summary: str
) -> list[NovaToolProposal]:
    """Parse unified diff hunks into surgical edit_file proposals."""
    hunks = re.split(r"^@@\s*-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s*@@", diff_text, flags=re.MULTILINE)
    if len(hunks) <= 1:
        return []
    proposals = []
    for hunk in hunks[1:]:
        old_lines = []
        new_lines = []
        for line in hunk.splitlines():
            if line.startswith("-"):
                old_lines.append(line[1:])
            elif line.startswith("+"):
                new_lines.append(line[1:])
            elif line.startswith(" ") or line.startswith("\t"):
                old_lines.append(line[1:] if line.startswith(" ") else line)
                new_lines.append(line[1:] if line.startswith(" ") else line)
        old_text = "\n".join(old_lines).strip("\n")
        new_text = "\n".join(new_lines).strip("\n")
        if old_text and new_text:
            proposals.append(
                NovaToolProposal(
                    name="edit_file",
                    args={
                        "path": file_path,
                        "old_text": old_text,
                        "new_text": new_text,
                        "_nova_guardrail": base_meta,
                    },
                    source_path=file_path,
                    guardrail_summary=guardrail_summary,
                )
            )
    return proposals
