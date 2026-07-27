"""Literal constraint extraction and verification for Nova generations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from output_parser import FileAction


@dataclass
class LiteralConstraint:
    type: str
    value: str
    original_text: str
    prompt_text: str = ""


class ConstraintExtractor:
    """Extract only explicit, mechanically checkable prompt literals."""

    def __init__(self, ceiling_node):
        self.ceiling = ceiling_node

    def extract(self, prompt: str) -> list[LiteralConstraint]:
        if self.ceiling.client in {"manual", "mock"}:
            return self._extract_static(prompt)

        system = """Extract explicit, mechanically-checkable literal requirements.
Return a strict JSON array of objects with type, value, and original_text.
Allowed types: status_code, string_output, assignment.
Return exactly NONE when there are no literal constraints. Do not infer requirements."""
        try:
            response = self.ceiling.client.chat.completions.create(
                model=self.ceiling.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            text = response.choices[0].message.content.strip()
            if "NONE" in text and "[" not in text:
                return []
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0]
            data = json.loads(text.strip())
            if isinstance(data, dict):
                data = [data]
            return [
                LiteralConstraint(
                    type=str(item["type"]),
                    value=str(item["value"]),
                    original_text=str(item.get("original_text", "")),
                    prompt_text=prompt,
                )
                for item in data
            ]
        except Exception as exc:
            print(f"   ⚠️  Constraint extraction failed: {exc}")
            return self._extract_static(prompt)

    @staticmethod
    def _extract_static(prompt: str) -> list[LiteralConstraint]:
        found: list[LiteralConstraint] = []

        for match in re.finditer(r"(?:return|status)(?:\s+code)?\s+(\d{3})", prompt, re.I):
            found.append(LiteralConstraint("status_code", match.group(1), match.group(0), prompt))

        # Quoted literals must be close to an output verb. This prevents a
        # later identifier such as '__main__' from being mistaken for the text
        # requested by a much earlier "print" verb.
        quoted = re.compile(
            r"(?:print|output|status:|return|body|emit|write)"
            r"[^\n,;.!?]{0,80}?(['\"])([^'\"\n]+)\1",
            re.I,
        )
        for match in quoted.finditer(prompt):
            found.append(LiteralConstraint("string_output", match.group(2), match.group(0), prompt))

        unquoted = re.compile(
            r"(?:prints?|outputs?|emits?|writes?)\s+exactly\s+"
            r"([A-Za-z0-9_./:+-]+(?: [A-Za-z0-9_./:+-]+)*)",
            re.I,
        )
        for match in unquoted.finditer(prompt):
            value = re.split(r"\s+(?:and|then|with|under)\b", match.group(1), maxsplit=1, flags=re.I)[0]
            found.append(LiteralConstraint("string_output", value.strip(), match.group(0), prompt))

        assignment = re.compile(
            r"set\s+(?:it|[\w_]+)\s+to\s+(?:an?\s+)?"
            r"(empty string|null|true|false|[\w_]+|['\"][^'\"]+['\"])",
            re.I,
        )
        for match in assignment.finditer(prompt):
            value = match.group(1)
            if value.lower() == "empty string":
                value = '""'
            elif value.startswith(("'", '"')):
                value = value[1:-1]
            found.append(LiteralConstraint("assignment", value, match.group(0), prompt))

        unique: dict[tuple[str, str], LiteralConstraint] = {}
        for item in found:
            # A multi-token expected runtime sequence produced by an algorithm
            # (traversal, sorting, calculation, recursion) is not a static
            # source literal. Treating it as one rejects correct programs; it
            # must be proven by an actual behavior test instead.
            if (
                item.type == "string_output"
                and any(char.isspace() for char in item.value)
                and re.search(r"\b(travers|algorithm|sort|calculat|recurs|graph|search)\w*\b", prompt, re.I)
            ):
                continue
            unique[(item.type, item.value)] = item
        return list(unique.values())


class ConstraintVerifier:
    """Verify extracted literals against generated file content."""

    OUTPUT_MARKERS = (
        "print", "return", "status", "body", "send", "json", "console.log",
        "cout", "printf", "println", "fmt.", "write", "emit",
    )

    def __init__(self, ceiling_node):
        self.ceiling = ceiling_node

    def verify_single(self, constraint: LiteralConstraint, code_content: str) -> tuple[bool, str]:
        if self.ceiling.client in {"manual", "mock"}:
            return self._verify_static(constraint, code_content)

        system = """Check whether generated code strictly fulfills the literal constraint
in the correct logical branch. Return strict JSON: {"passed": true/false, "reason": "..."}.
Fail if the exact value is absent or appears only in irrelevant text."""
        prompt = (
            f"Constraint context: {constraint.original_text}\n"
            f"Literal required ({constraint.type}): {constraint.value}\n\n"
            f"Code:\n```\n{code_content}\n```"
        )
        try:
            response = self.ceiling.client.chat.completions.create(
                model=self.ceiling.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            text = response.choices[0].message.content.strip()
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0]
            data = json.loads(text)
            prefix = "Constraint PASSED: " if data["passed"] else "Constraint FAILED: "
            return bool(data["passed"]), prefix + str(data["reason"])
        except Exception:
            return self._verify_static(constraint, code_content)

    def _verify_static(self, constraint: LiteralConstraint, code_content: str) -> tuple[bool, str]:
        if constraint.value not in code_content:
            return False, f"Constraint FAILED: '{constraint.value}' not found anywhere in code."

        relevant_lines = [line.lower() for line in code_content.splitlines() if constraint.value in line]
        if constraint.type == "status_code":
            if not any("status" in line or "return" in line for line in relevant_lines):
                return False, f"Constraint FAILED: '{constraint.value}' is not in a return/status branch."
        elif constraint.type == "string_output":
            if not any(any(marker in line for marker in self.OUTPUT_MARKERS) for line in relevant_lines):
                return False, f"Constraint FAILED: string '{constraint.value}' is not in an output branch."
        return True, f"Constraint PASSED: Found '{constraint.value}' in a valid branch statically."

    def verify(self, constraints: list[LiteralConstraint], files: list[FileAction]) -> tuple[bool, str]:
        code_content = "\n".join(file.content for file in files)
        reasons = []
        for constraint in constraints:
            passed, reason = self.verify_single(constraint, code_content)
            reasons.append(reason)
            if not passed:
                return False, " | ".join(reasons)
        return True, " | ".join(reasons)
