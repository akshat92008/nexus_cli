"""
Conversation Memory — persist and resume conversations across sessions.
"""

import json
from datetime import datetime

from nexus.paths import nexus_home

MEMORY_DIR = nexus_home() / "conversations"


class ConversationMemory:
    """Manages conversation persistence across sessions."""

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def save_conversation(
        self,
        messages: list[dict],
        model_name: str,
        model_id: str,
        working_dir: str,
        conversation_id: str | None = None,
    ) -> str:
        """
        Save a conversation to disk. Returns the conversation ID.
        """
        conv_id = conversation_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        data = {
            "id": conv_id,
            "model_name": model_name,
            "model_id": model_id,
            "working_dir": working_dir,
            "created_at": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": messages,
        }
        filepath = MEMORY_DIR / f"{conv_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return conv_id

    def load_conversation(self, conv_id: str) -> dict | None:
        """Load a conversation by ID."""
        filepath = MEMORY_DIR / f"{conv_id}.json"
        if not filepath.exists():
            # Try partial match
            matches = list(MEMORY_DIR.glob(f"*{conv_id}*.json"))
            if len(matches) == 1:
                filepath = matches[0]
            elif len(matches) > 1:
                return None  # Ambiguous
            else:
                return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_conversations(self, limit: int = 20) -> list[dict]:
        """List recent conversations with metadata (not full messages)."""
        conversations = []
        for filepath in sorted(MEMORY_DIR.glob("*.json"), reverse=True)[:limit]:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Return metadata only
                conversations.append(
                    {
                        "id": data.get("id", filepath.stem),
                        "model_name": data.get("model_name", "unknown"),
                        "working_dir": data.get("working_dir", ""),
                        "created_at": data.get("created_at", ""),
                        "message_count": data.get("message_count", 0),
                        "preview": _get_preview(data.get("messages", [])),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
        return conversations

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation by ID."""
        filepath = MEMORY_DIR / f"{conv_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def auto_save(
        self,
        messages: list[dict],
        model_name: str,
        model_id: str,
        working_dir: str,
        conv_id: str,
    ):
        """Auto-save the current conversation (overwrites existing)."""
        if len(messages) < 2:
            return  # Don't save trivially short conversations
        self.save_conversation(messages, model_name, model_id, working_dir, conv_id)


def _get_preview(messages: list[dict], max_len: int = 80) -> str:
    """Extract a short preview from the first user message."""
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            text = msg["content"].strip()
            if len(text) > max_len:
                return text[:max_len] + "..."
            return text
    return "(empty conversation)"


def compact_messages(messages: list[dict], keep_recent: int = 10) -> list[dict]:
    """
    Compact a long conversation by summarizing old messages.
    Keeps the most recent `keep_recent` messages intact, and collapses
    earlier messages into a summary.
    """
    if len(messages) <= keep_recent + 2:
        return messages  # Nothing to compact

    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Preserve decisions, exact paths, commands and failures. This is deterministic
    # compaction, not a semantic model summary, so it must fail by retaining too much.
    summary_parts: list[str] = []
    per_message_limit = 1_500
    for index, msg in enumerate(old_messages):
        role = str(msg.get("role", "unknown"))
        content = str(msg.get("content", "") or "").strip()
        if not content:
            continue
        tool_id = str(msg.get("tool_call_id", "") or "")
        label = f"{index:04d} {role}"
        if tool_id:
            label += f" tool_call_id={tool_id}"
        excerpt = (
            content
            if len(content) <= per_message_limit
            else content[:per_message_limit] + "\n[…truncated at message boundary…]"
        )
        summary_parts.append(f"## {label}\n{excerpt}")

    summary_text = (
        "[CONVERSATION SUMMARY — STRUCTURED ARCHIVE; exact recent messages follow]\n\n"
        + "\n\n".join(summary_parts[-80:])
        + "\n\n[END STRUCTURED ARCHIVE]"
    )

    compacted = [{"role": "user", "content": summary_text}]
    compacted.append(
        {
            "role": "assistant",
            "content": "Understood. I have the context from our earlier conversation. Let's continue.",
        }
    )
    compacted.extend(recent_messages)

    return compacted
