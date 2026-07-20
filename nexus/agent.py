"""
Agent — the core agentic loop with tool calling, streaming, auto-context,
auto-fix, conversation compaction, and memory.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from nexus.api import NvidiaClient
from nexus.models import resolve_model, DEFAULT_MODEL, MODELS
from nexus.tools import TOOL_DEFINITIONS, execute_tool, tool_get_project_structure, tool_git_status
from nexus.history import get_history, init_history
from nexus.memory import ConversationMemory, compact_messages
from nexus import ui


SYSTEM_PROMPT = """You are NexusAI, an extremely powerful AI coding agent — a 10x senior engineer with full access to the user's system.
You operate through tool calls that let you read, write, edit, search, execute, and manage code with superhuman speed and precision.

## CORE IDENTITY
- You are decisive and action-oriented. When asked to build something, you BUILD it — completely, production-ready, no shortcuts.
- You proactively explore the codebase before making changes. Read first, understand, then act.
- You fix errors automatically. If your code fails, you diagnose and fix it without being asked.
- You use git to track your changes. Commit frequently with meaningful messages.

## YOUR 20 TOOLS

### File Operations
- `read_file(path, start_line?, end_line?)` — Read file contents with line numbers
- `write_file(path, content)` — Create or overwrite files (auto-creates directories)
- `edit_file(path, old_text, new_text)` — Surgical find-and-replace (old_text must be EXACT and unique)
- `patch_file(path, start_line, end_line, new_content)` — Line-range based editing
- `multi_edit(edits[])` — Batch edits across multiple files in one call
- `file_info(path)` — File metadata (size, type, permissions, line count, MD5)
- `diff_files(file_a, file_b)` — Unified diff between two files

### Code Search
- `search_code(pattern, directory?, file_pattern?)` — Regex search across codebase
- `list_directory(path?, recursive?, max_depth?)` — List directory contents
- `find_files(pattern, directory?)` — Glob-based file finder
- `get_project_structure(path?, max_depth?)` — Tree view of project

### Shell Execution
- `run_command(command, cwd?, timeout?)` — Execute any shell command (blocking)
- `process_run(command, cwd?)` — Start a background process (non-blocking, returns PID)

### Git Operations
- `git_status(cwd?)` — Full repo status (branch, staged, modified, untracked)
- `git_diff(target?, staged?, file_path?, cwd?)` — View diffs (working/staged/commits)
- `git_commit(message, files?, all?, cwd?)` — Stage and commit changes
- `git_log(count?, oneline?, file_path?, cwd?)` — View commit history
- `git_branch(action?, name?, cwd?)` — List/create/switch/delete branches

### Web
- `web_fetch(url, max_length?)` — Fetch and read any URL (strips HTML to text)
- `web_search(query, max_results?)` — Search the web via DuckDuckGo

## WORKFLOW PATTERNS

### Building a New Feature:
1. Read project structure and relevant files to understand the codebase
2. Plan the implementation approach
3. Write/edit files to implement the feature
4. Run the code to verify it works
5. Fix any errors automatically
6. Commit the changes with a meaningful message

### Debugging:
1. Read the error message and relevant code
2. Search for related patterns in the codebase
3. Identify the root cause
4. Apply the fix
5. Run tests to verify
6. If it still fails, iterate

### Code Review / Refactoring:
1. Read the files to understand current state
2. Identify improvements
3. Apply edits surgically using edit_file (NOT write_file for existing files)
4. Run tests to ensure nothing breaks

## RULES
1. **ALWAYS use edit_file for modifications** — never use write_file to modify existing files (you'll lose content you didn't read)
2. **Read before writing** — always read a file before editing it
3. **old_text must be EXACT** — copy the exact text including whitespace and indentation
4. **Run code after changes** — verify your changes work
5. **Handle errors gracefully** — if a tool fails, try a different approach
6. **Be thorough** — add error handling, types, docstrings, and tests
7. **Use modern patterns** — write idiomatic, production-quality code
8. **Multiple tools per turn** — you can call several tools in sequence within one turn
9. **Commit after major changes** — use git_commit to track your work
10. **Search before creating** — check if similar code already exists

## CODE QUALITY STANDARDS
- Python: type hints, docstrings, PEP 8, error handling, pathlib
- JavaScript/TypeScript: JSDoc, error handling, modern ES6+, async/await
- Go: error handling, go doc, gofmt
- Rust: proper error types, documentation, clippy-clean
- All: meaningful variable names, DRY, SOLID principles

When in doubt, ask the user. But when the task is clear, EXECUTE WITHOUT HESITATION."""


class Agent:
    """The core agent — manages conversation, tool calls, streaming, auto-context, and memory."""

    def __init__(
        self,
        api_key: str | None = None,
        model_key: str = DEFAULT_MODEL,
        working_dir: str | None = None,
    ):
        self.client = NvidiaClient(api_key=api_key)
        self.model_key = model_key
        self.model_cfg = resolve_model(model_key) or MODELS[DEFAULT_MODEL]
        self.messages: list[dict] = []
        self.system_prompt = SYSTEM_PROMPT
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.working_dir = working_dir or os.getcwd()

        # New features
        self.memory = ConversationMemory()
        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.history = init_history(self.conversation_id)
        self._context_gathered = False
        self._auto_fix_enabled = True
        self._auto_save_enabled = True

        # Set working directory
        os.chdir(self.working_dir)

    def set_model(self, model_key: str) -> bool:
        """Switch to a different model."""
        cfg = resolve_model(model_key)
        if not cfg:
            return False
        self.model_key = model_key
        self.model_cfg = cfg
        return True

    def set_system_prompt(self, prompt: str):
        """Set a custom system prompt."""
        self.system_prompt = prompt

    def clear_history(self):
        """Clear conversation history."""
        self.messages = []

    def compact_conversation(self) -> int:
        """
        Compact the conversation by summarizing old messages.
        Returns the number of messages removed.
        """
        old_count = len(self.messages)
        self.messages = compact_messages(self.messages, keep_recent=12)
        return old_count - len(self.messages)

    def load_conversation(self, conv_id: str) -> bool:
        """Load a conversation from memory."""
        data = self.memory.load_conversation(conv_id)
        if not data:
            return False
        self.messages = data.get("messages", [])
        self.conversation_id = data.get("id", conv_id)
        # Try to restore model
        model_id = data.get("model_id", "")
        for key, cfg in MODELS.items():
            if cfg["id"] == model_id:
                self.model_key = key
                self.model_cfg = cfg
                break
        return True

    def _gather_context(self) -> str:
        """
        Auto-gather project context on first interaction.
        Returns a context string to prepend to the user's message.
        """
        if self._context_gathered:
            return ""
        self._context_gathered = True

        parts = []

        # 1. Project structure
        try:
            tree = tool_get_project_structure(self.working_dir, max_depth=3)
            if tree and len(tree) > 50:
                parts.append(f"[AUTO-CONTEXT: Project Structure]\n{tree}")
        except Exception:
            pass

        # 2. Git status
        try:
            git_info = tool_git_status(self.working_dir)
            if git_info and "Not a git" not in git_info:
                parts.append(f"[AUTO-CONTEXT: Git Status]\n{git_info}")
        except Exception:
            pass

        # 3. Config files detection
        config_files = [
            "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
            "Makefile", "Dockerfile", "docker-compose.yml", "tsconfig.json",
            ".eslintrc.json", "requirements.txt", "pom.xml", "build.gradle",
        ]
        found_configs = []
        for cf in config_files:
            p = Path(self.working_dir) / cf
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if len(content) > 3000:
                        content = content[:3000] + "... (truncated)"
                    found_configs.append(f"--- {cf} ---\n{content}")
                except OSError:
                    pass

        if found_configs:
            parts.append("[AUTO-CONTEXT: Config Files]\n" + "\n\n".join(found_configs))

        if parts:
            return "\n\n".join(parts) + "\n\n---\n\n"
        return ""

    def _build_messages(self) -> list[dict]:
        """Build the full message list with system prompt."""
        cwd_info = f"\n\nCurrent working directory: {self.working_dir}"
        time_info = f"\nCurrent time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        os_info = f"\nOS: {sys.platform}"
        system = {
            "role": "system",
            "content": self.system_prompt + cwd_info + time_info + os_info,
        }
        return [system] + self.messages

    def _get_tools(self) -> list[dict] | None:
        """Get tool definitions if the model supports them."""
        if self.model_cfg.get("supports_tools"):
            return TOOL_DEFINITIONS
        return None

    def _handle_stream(self, stream) -> tuple[str, list[dict]]:
        """Handle a streaming response, printing tokens as they arrive."""
        full_content = ""
        tool_calls_accum: dict[int, dict] = {}  # index -> {id, name, arguments}
        prompt_tokens = 0
        completion_tokens = 0

        status = ui.console.status(f"[bold {ui.CYAN}]Thinking...[/]", spinner="dots")
        status.start()
        first_chunk = False

        try:
            for chunk in stream:
                if not first_chunk:
                    status.stop()
                    first_chunk = True

                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Stream text content
                if delta.content:
                    ui.console.print(delta.content, end="", style=ui.WHITE, highlight=False)
                    full_content += delta.content

                # Accumulate tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_accum[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accum[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accum[idx]["arguments"] += tc.function.arguments

                # Track token usage from the last chunk (usage is typically on final chunk)
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0
        finally:
            status.stop()

        # Accumulate token counts
        if prompt_tokens:
            self.total_prompt_tokens += prompt_tokens
        if completion_tokens:
            self.total_completion_tokens += completion_tokens

        # Convert accumulated tool calls to list
        tool_calls = []
        for idx in sorted(tool_calls_accum.keys()):
            tc = tool_calls_accum[idx]
            if tc["name"]:
                tool_calls.append(tc)

        if full_content:
            ui.console.print()  # Newline after streamed content

        return full_content, tool_calls

    def _handle_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls and return tool result messages."""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            ui.print_tool_call(name, args)

            # Execute the tool with a spinner
            with ui.console.status(f"[bold {ui.ORANGE}]Executing {name}...[/]", spinner="bouncingBar"):
                result = execute_tool(name, args)
                
            success = not result.startswith("❌")

            ui.print_tool_result(result, success)

            results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        return results

    def _auto_save(self):
        """Auto-save the conversation."""
        if self._auto_save_enabled and len(self.messages) >= 2:
            try:
                self.memory.auto_save(
                    self.messages,
                    self.model_cfg["name"],
                    self.model_cfg["id"],
                    self.working_dir,
                    self.conversation_id,
                )
            except Exception:
                pass  # Don't let auto-save errors break the agent

    def run(self, user_input: str) -> str:
        """Run one turn of the agent loop (may involve multiple API calls for tool use)."""

        # Auto-gather context on first interaction
        context = self._gather_context()
        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        self.messages.append({"role": "user", "content": augmented_input})

        max_iterations = 50  # Increased from 25 for complex multi-step tasks
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                ui.print_streaming_start()
                stream = self.client.chat(
                    model_id=self.model_cfg["id"],
                    messages=self._build_messages(),
                    tools=self._get_tools(),
                    stream=True,
                )

                content, tool_calls = self._handle_stream(stream)

            except Exception as e:
                error_msg = str(e)

                # Check for fallback on auth/rate-limit errors
                if ("401" in error_msg or "429" in error_msg or "Unauthorized" in error_msg or "rate" in error_msg.lower()):
                    if self.client.switch_to_fallback():
                        ui.print_info("Primary API key failed (auth/rate-limit). Retrying with fallback API key...")
                        iteration -= 1  # Don't count this as a failed tool loop iteration
                        continue

                # Handle common API errors gracefully
                if "401" in error_msg or "Unauthorized" in error_msg:
                    ui.print_error("Invalid API key. Check your NVIDIA_API_KEY.")
                elif "429" in error_msg or "rate" in error_msg.lower():
                    ui.print_error("Rate limited. Wait a moment and try again.")
                elif "404" in error_msg:
                    ui.print_error(
                        f"Model '{self.model_cfg['id']}' not found. Try /models to see available options."
                    )
                else:
                    ui.print_error(f"API error: {error_msg}")
                # Remove the failed user message
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return ""

            # If there are tool calls, execute them and loop
            if tool_calls:
                # Add assistant message with tool calls to history
                assistant_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                self.messages.append(assistant_msg)

                # Execute tools and add results
                tool_results = self._handle_tool_calls(tool_calls)
                self.messages.extend(tool_results)

                # Continue the loop — the model will process tool results
                continue

            # No tool calls — we're done
            if content:
                self.messages.append({"role": "assistant", "content": content})

            ui.print_response_complete()

            # Auto-save after each turn
            self._auto_save()

            return content or ""

        ui.print_warning("Reached maximum tool-call iterations (safety limit).")
        self._auto_save()
        return ""

    def run_non_interactive(self, user_input: str) -> tuple[str, list[dict]]:
        """
        Run one turn and return (final_text, all_tool_events).
        Used by the web API to send structured responses.
        """
        events: list[dict] = []

        # Auto-gather context on first interaction
        context = self._gather_context()
        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        self.messages.append({"role": "user", "content": augmented_input})

        max_iterations = 50
        iteration = 0
        final_content = ""

        while iteration < max_iterations:
            iteration += 1

            try:
                response = self.client.chat_sync(
                    model_id=self.model_cfg["id"],
                    messages=self._build_messages(),
                    tools=self._get_tools(),
                )

                choice = response.choices[0]
                content = choice.message.content or ""
                tool_calls_raw = choice.message.tool_calls or []

                # Track token usage
                if hasattr(response, "usage") and response.usage:
                    self.total_prompt_tokens += response.usage.prompt_tokens or 0
                    self.total_completion_tokens += response.usage.completion_tokens or 0

            except Exception as e:
                error_msg = str(e)
                if ("401" in error_msg or "429" in error_msg or "Unauthorized" in error_msg or "rate" in error_msg.lower()):
                    if self.client.switch_to_fallback():
                        iteration -= 1
                        continue
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return f"Error: {error_msg}", events

            # Process tool calls
            if tool_calls_raw:
                tool_calls = []
                for tc in tool_calls_raw:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

                # Add assistant message
                assistant_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_calls
                    ],
                }
                self.messages.append(assistant_msg)

                # Execute tools
                for tc in tool_calls:
                    name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    result = execute_tool(name, args)
                    success = not result.startswith("❌")

                    events.append({
                        "type": "tool_call",
                        "name": name,
                        "args": args,
                        "result": result,
                        "success": success,
                    })

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                continue

            # No tool calls — done
            if content:
                self.messages.append({"role": "assistant", "content": content})

            final_content = content
            self._auto_save()
            break

        return final_content, events

    def save_conversation(self, filepath: str):
        """Save the conversation to a JSON file."""
        data = {
            "model": self.model_cfg["name"],
            "model_id": self.model_cfg["id"],
            "timestamp": datetime.now().isoformat(),
            "messages": self.messages,
        }
        p = Path(filepath).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(data, f, indent=2)
        ui.print_success(f"Conversation saved to {p}")
