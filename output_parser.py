#!/usr/bin/env python3
"""
output_parser.py — Strict Output Format Parser for Nova 3B

Parses the <<THINKING>> / <<FILES>> / <<TEST_COMMAND>> protocol
and the <<THINKING>> / <<RESPONSE>> protocol (for non-code tasks)
used by the Nova intern model into structured Python objects.

Handles edge cases:
  - Missing or malformed block delimiters
  - Extra whitespace and newlines
  - Multiple code blocks in <<FILES>>
  - Mixed markdown fence styles
  - Partial outputs (streaming)
  - Non-code <<RESPONSE>> blocks (explanations, summaries)

Part of the Nova model family by Amaura.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FileAction:
    """A single file operation extracted from <<FILES>> block."""
    path: str
    action: str  # CREATE or MODIFY
    content: str
    language: str = "python"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "action": self.action,
            "content": self.content,
            "language": self.language,
        }


@dataclass
class ParsedResponse:
    """Structured result from parsing a Nova model response."""
    thinking: str = ""
    files: List[FileAction] = field(default_factory=list)
    test_command: str = ""
    response_text: str = ""  # Non-code response (<<RESPONSE>> block)
    parse_errors: List[str] = field(default_factory=list)
    raw_text: str = ""

    @property
    def is_valid(self) -> bool:
        """Response is valid if it has THINKING + (FILES or RESPONSE or CLARIFICATION)."""
        has_thinking = bool(self.thinking.strip())
        has_code = len(self.files) > 0
        has_response = bool(self.response_text.strip())
        has_clarification = '<<CLARIFICATION>>' in self.raw_text
        return (
            has_thinking
            and (has_code or has_response or has_clarification)
            and len(self.parse_errors) == 0
        )

    @property
    def is_partial(self) -> bool:
        """Response has some valid blocks but is incomplete."""
        has_any = bool(self.thinking) or len(self.files) > 0 or bool(self.test_command)
        return has_any and not self.is_valid

    def summary(self) -> str:
        """Human-readable summary of the parsed response."""
        status = "✅ VALID" if self.is_valid else ("⚠️ PARTIAL" if self.is_partial else "❌ INVALID")
        lines = [f"[{status}]"]
        if self.thinking:
            lines.append(f"  Thinking: {self.thinking[:80]}...")
        lines.append(f"  Files: {len(self.files)}")
        for f in self.files:
            lines.append(f"    - [{f.action}] {f.path} ({len(f.content)} chars)")
        if self.test_command:
            lines.append(f"  Test: {self.test_command}")
        if self.parse_errors:
            lines.append(f"  Errors: {self.parse_errors}")
        return "\n".join(lines)


class NovaOutputParser:
    """
    Parser for the Nova <<THINKING>>/<<FILES>>/<<TEST_COMMAND>> protocol.
    
    Usage:
        parser = NovaOutputParser()
        result = parser.parse(model_output_text)
        if result.is_valid:
            for file_action in result.files:
                write_file(file_action.path, file_action.content)
            run_command(result.test_command)
    """

    # Block delimiters (case-insensitive matching)
    THINKING_PATTERN = re.compile(
        r'<<THINKING>>(.*?)(?=<<FILES>>|<<TEST_COMMAND>>|<<CLARIFICATION>>|<<RESPONSE>>|$)',
        re.DOTALL | re.IGNORECASE,
    )
    FILES_PATTERN = re.compile(
        r'<<FILES>>(.*?)(?=<<TEST_COMMAND>>|$)',
        re.DOTALL | re.IGNORECASE,
    )
    TEST_PATTERN = re.compile(
        r'<<TEST_COMMAND>>(.*?)$',
        re.DOTALL | re.IGNORECASE,
    )
    RESPONSE_PATTERN = re.compile(
        r'<<RESPONSE>>(.*?)(?=<<TEST_COMMAND>>|$)',
        re.DOTALL | re.IGNORECASE,
    )

    # Code block extraction — handles ```, ~~~, and language tags
    CODE_BLOCK_PATTERN = re.compile(
        r'(?:```|~~~)(\w*)\n(.*?)(?:```|~~~)',
        re.DOTALL,
    )

    # File metadata from comment headers (supports #, //, <!-- -->, /* */, or loose text)
    FILEPATH_PATTERN = re.compile(
        r'(?:#|//|<!--|\/\*|^|\s)filepath:\s*([^\s\>\*`\'"]+)',
        re.IGNORECASE,
    )
    ACTION_PATTERN = re.compile(
        r'(?:#|//|<!--|\/\*|^|\s)action:\s*(CREATE|MODIFY|DELETE)',
        re.IGNORECASE,
    )

    def parse(self, text: str) -> ParsedResponse:
        """Parse a Nova model response into structured blocks."""
        result = ParsedResponse(raw_text=text)

        if not text or not text.strip():
            result.parse_errors.append("Empty response")
            return result

        # 1. Extract <<THINKING>> block
        thinking_match = self.THINKING_PATTERN.search(text)
        if thinking_match:
            result.thinking = thinking_match.group(1).strip()
        else:
            result.parse_errors.append("Missing <<THINKING>> block")

        # 2. Check for <<RESPONSE>> block (non-code tasks)
        response_match = self.RESPONSE_PATTERN.search(text)
        if response_match:
            result.response_text = response_match.group(1).strip()
            # <<RESPONSE>> is a complete response — no <<FILES>> or <<TEST_COMMAND>> needed
            return result

        # 3. Check for <<CLARIFICATION>> block (refusal)
        if '<<CLARIFICATION>>' in text.upper():
            # Clarification is a complete response — no <<FILES>> needed
            return result

        # 4. Extract <<FILES>> block
        files_match = self.FILES_PATTERN.search(text)
        if files_match:
            files_raw = files_match.group(1).strip()
            result.files = self._parse_file_blocks(files_raw, result.parse_errors)
        else:
            result.parse_errors.append("Missing <<FILES>> block")

        # 5. Extract <<TEST_COMMAND>> block (optional)
        test_match = self.TEST_PATTERN.search(text)
        if test_match:
            result.test_command = self._clean_test_command(test_match.group(1).strip())

        return result

    def _parse_file_blocks(self, files_raw: str, errors: List[str]) -> List[FileAction]:
        """Extract individual file actions from the <<FILES>> content."""
        files = []

        # Try markdown code blocks first
        code_blocks = self.CODE_BLOCK_PATTERN.findall(files_raw)

        if code_blocks:
            for lang_tag, block_content in code_blocks:
                file_action = self._extract_file_metadata(block_content, lang_tag, errors)
                if file_action:
                    files.append(file_action)
        else:
            # Fallback: try to parse as raw code with filepath/action comments
            file_action = self._extract_file_metadata(files_raw, "python", errors)
            if file_action:
                files.append(file_action)
            else:
                errors.append("No code blocks found in <<FILES>>")

        return files

    def _extract_file_metadata(
        self, content: str, default_lang: str, errors: List[str]
    ) -> Optional[FileAction]:
        """Extract filepath and action from code block comments."""
        
        filepath_match = self.FILEPATH_PATTERN.search(content)
        action_match = self.ACTION_PATTERN.search(content)

        if not filepath_match:
            # Inferring a path from arbitrary source text is unsafe: versions
            # such as 1.0 or prose such as Node.js can otherwise become files.
            errors.append("Missing # filepath: in code block")
            return None
        else:
            filepath = filepath_match.group(1).strip().rstrip('-->').rstrip('*/').strip('`\'"')

        # Strip common placeholder or git diff prefixes (e.g. path/to/todo.html, a/todo.html, b/todo.html)
        for prefix in ("path/to/", "a/", "b/"):
            if filepath.startswith(prefix):
                filepath = filepath[len(prefix):]

        if not action_match:
            errors.append("Missing # action: CREATE or MODIFY in code block")
            return None
        action = action_match.group(1).strip().upper()

        # Extract the actual code (everything after metadata comments)
        code_lines = content.split('\n')
        code_start = 0
        for i, line in enumerate(code_lines):
            stripped = line.strip().lower()
            if 'filepath:' in stripped or 'action:' in stripped:
                code_start = i + 1
            elif stripped == '' or stripped in ('<!--', '-->', '/*', '*/'):
                # Skip blank lines or standalone comment delimiters right after metadata
                if i <= code_start:
                    code_start = i + 1
            else:
                break

        code_content = '\n'.join(code_lines[code_start:]).strip()

        # Determine language from file extension or tag
        lang = default_lang or "python"
        ext_match = re.search(r'\.(\w+)$', filepath)
        if ext_match:
            ext_to_lang = {
                "py": "python", "js": "javascript", "ts": "typescript",
                "go": "go", "rs": "rust", "java": "java", "cpp": "cpp",
                "c": "c", "rb": "ruby", "sh": "bash", "sql": "sql",
            }
            lang = ext_to_lang.get(ext_match.group(1), lang)

        return FileAction(
            path=filepath,
            action=action,
            content=code_content,
            language=lang,
        )

    def _clean_test_command(self, cmd: str) -> str:
        """Clean up the test command — remove markdown fences, extra whitespace."""
        # Remove any wrapping code fences
        cmd = re.sub(r'^```\w*\n?', '', cmd)
        cmd = re.sub(r'\n?```$', '', cmd)
        # Take only the first line (ignore multi-line noise)
        first_line = cmd.strip().split('\n')[0].strip()
        return first_line

    @staticmethod
    def count_file_declarations(text: str) -> int:
        """
        Count the number of '# filepath:' markers in a Nova output.

        This is the ground-truth file count used by the guardrail to validate
        that Nova emitted the expected number of files.

        Args:
            text: Raw Nova model output

        Returns:
            Number of '# filepath:' declarations found.
        """
        return len(re.findall(r'^#\s*filepath\s*:', text, re.MULTILINE | re.IGNORECASE))

    @staticmethod
    def is_clarification_response(text: str) -> bool:
        """
        Detect whether Nova returned a structured clarification/refusal response
        (i.e., contains a <<CLARIFICATION>> block instead of code).

        This is the desired behavior for vague/underspecified prompts
        once the model is trained on the new refusal dataset.

        Args:
            text: Raw Nova model output

        Returns:
            True if the response contains <<CLARIFICATION>> marker.
        """
        return bool(re.search(r'<<CLARIFICATION>>', text, re.IGNORECASE))

    def validate_format_strict(self, text: str) -> tuple:
        """
        Strict validation — returns (is_valid: bool, errors: list).
        Used for dataset quality control.
        """
        errors = []
        
        if '<<THINKING>>' not in text:
            errors.append("Missing <<THINKING>> delimiter")

        has_files = '<<FILES>>' in text
        has_clarification = '<<CLARIFICATION>>' in text
        has_response = '<<RESPONSE>>' in text

        if not (has_files or has_clarification or has_response):
            errors.append("Missing <<FILES>>, <<CLARIFICATION>>, or <<RESPONSE>> delimiter")

        if has_files and '<<TEST_COMMAND>>' in text:
            # Check order for code responses if test command exists
            positions = {}
            for tag in ['<<THINKING>>', '<<FILES>>', '<<TEST_COMMAND>>']:
                pos = text.find(tag)
                if pos >= 0:
                    positions[tag] = pos
            
            if len(positions) == 3:
                if not (positions['<<THINKING>>'] < positions['<<FILES>>'] < positions['<<TEST_COMMAND>>']):
                    errors.append("Blocks are out of order (must be THINKING → FILES → TEST_COMMAND)")

        # Check code blocks exist in <<FILES>>
        result = self.parse(text)
        if len(result.files) == 0 and has_files:
            errors.append("<<FILES>> block contains no valid code blocks")

        # Check thinking brevity (intern should be terse)
        if result.thinking:
            word_count = len(result.thinking.split())
            if word_count > 100:
                errors.append(f"<<THINKING>> too verbose ({word_count} words, max 100)")

        return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════════

_parser = NovaOutputParser()


def parse_nova_response(text: str) -> ParsedResponse:
    """Quick-access parser function."""
    return _parser.parse(text)


def is_valid_nova_response(text: str) -> bool:
    """Check if a response follows the Nova protocol."""
    return _parser.parse(text).is_valid


def extract_files(text: str) -> List[FileAction]:
    """Extract file actions from a Nova response."""
    return _parser.parse(text).files


def extract_test_command(text: str) -> str:
    """Extract the test command from a Nova response."""
    return _parser.parse(text).test_command


def count_file_declarations(text: str) -> int:
    """Count # filepath: markers in a Nova response (used by guardrail)."""
    return NovaOutputParser.count_file_declarations(text)


def is_clarification_response(text: str) -> bool:
    """Return True if Nova returned a <<CLARIFICATION>> refusal block."""
    return NovaOutputParser.is_clarification_response(text)


if __name__ == "__main__":
    # Quick test
    sample = """<<THINKING>>
I will create a fibonacci function in src/math.py.

<<FILES>>
```python
# filepath: src/math.py
# action: CREATE

def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
```

<<TEST_COMMAND>>
pytest test_math.py
"""
    result = parse_nova_response(sample)
    print(result.summary())
    print(f"\nValid: {result.is_valid}")
    
    is_strict, strict_errors = _parser.validate_format_strict(sample)
    print(f"Strict: {is_strict}")
    if strict_errors:
        print(f"Strict errors: {strict_errors}")
