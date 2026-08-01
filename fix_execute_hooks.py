import re

with open("new_execute.py", "r") as f:
    content = f.read()

# Replace the broken hooks block
old_hooks_block = """        # ── Fire BEFORE hooks
        hook_ctx = HookContext(
            event=HookEvent.BEFORE_FILE_CREATE if name == "write_file" else HookEvent.BEFORE_FILE_EDIT,
            tool_name=name,
            tool_args=args,
        )
        event_before = None
        event_after = None
        if name in mutation_tools:
            event_before = HookEvent.BEFORE_FILE_CREATE if name == "write_file" else HookEvent.BEFORE_FILE_EDIT
            event_after = HookEvent.AFTER_FILE_CREATE if name == "write_file" else HookEvent.AFTER_FILE_EDIT
        elif name in ("run_command", "run_process", "process_run"):
            event_before, event_after = HookEvent.BEFORE_COMMAND, HookEvent.AFTER_COMMAND
        if event_before:
            hook_ctx.event = event_before
            hook_res = self.hooks.fire(event_before, hook_ctx)
            if not hook_res.allow:
                return "❌ BLOCKED: " + (hook_res.reason or "Dangerous operation blocked by hook"), False
            if hook_res.requires_confirmation and not _user_confirmed:
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=SafetyCheck(
                        level=SafetyLevel.DANGEROUS,
                        operation=f"{name} hook requires confirmation",
                        reason=hook_res.reason or "Plugin requires confirmation",
                        details="",
                        requires_confirmation=True,
                    ),
                    edit_confirmed=_edit_confirmed,
                )
                return "⏸️ PENDING_CONFIRMATION " + f"[{confirmation_id}]: {hook_res.reason}", False"""

new_hooks_block = """        # ── Fire BEFORE hooks
        event_before = None
        event_after = None

        if name in ("write_file",):
            event_before = HookEvent.BEFORE_FILE_CREATE
            event_after = HookEvent.AFTER_FILE_CREATE
        elif name in ("edit_file", "patch_file", "multi_edit"):
            event_before = HookEvent.BEFORE_FILE_EDIT
            event_after = HookEvent.AFTER_FILE_EDIT
        elif name in ("run_command", "run_process", "process_run"):
            event_before = HookEvent.BEFORE_COMMAND
            event_after = HookEvent.AFTER_COMMAND
        elif name == "git_commit":
            event_before = HookEvent.BEFORE_COMMIT
            event_after = HookEvent.AFTER_COMMIT

        hook_ctx = HookContext(
            event=event_before or HookEvent.BEFORE_COMMAND,
            file_path=file_path,
            command=command,
            tool_name=name,
            tool_args=args,
        )

        if event_before:
            hook_ctx.event = event_before
            hook_results = self.hooks.fire(event_before, hook_ctx)
            if any(r.blocked for r in hook_results):
                return "❌ Operation blocked by hook policy.", False
                
        # ── Safety check ──
        safety_check = None
        if name in ("run_command", "run_process", "process_run") and command:
            safety_check = self.safety.check_command(command)
        elif name == "multi_edit":
            for edit in args.get("edits", []):
                check = self.safety.check_file_write(
                    edit.get("path", ""), edit.get("new_text", "")
                )
                if check.level in (SafetyLevel.BLOCKED, SafetyLevel.DANGEROUS):
                    safety_check = check
                    break
        elif name in mutation_tools and file_path:
            content_val = args.get("content", "") or args.get("new_text", "") or args.get("new_content", "")
            safety_check = self.safety.check_file_write(file_path, content_val)
            
        if safety_check and safety_check.level == SafetyLevel.BLOCKED:
            return f"❌ BLOCKED: {safety_check.reason}", False
        elif safety_check and safety_check.level == SafetyLevel.DANGEROUS and not _user_confirmed:
            confirmation_id = self._queue_confirmation(
                name=name,
                args=pending_args,
                safety_check=safety_check,
                edit_confirmed=_edit_confirmed,
            )
            return (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {safety_check.reason}. "
                f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                False,
            )"""

content = content.replace(old_hooks_block, new_hooks_block)

with open("new_execute.py", "w") as f:
    f.write(content)
