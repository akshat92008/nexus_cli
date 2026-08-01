    def _enforce_tool_policy(
        self,
        name: str,
        args: dict,
        command: str,
        scope_paths: list[str],
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
        read_tools: set,
    ) -> tuple[bool, str, tuple[str, bool]]:
        if name in self.disallowed_tools:
            return False, "", (f"❌ BLOCKED: {name} is denied by the active permission rules.", False)
        if self.allowed_tools and name not in self.allowed_tools:
            return False, "", (f"❌ BLOCKED: {name} is not in the active tool allowlist.", False)
        if not self.mode_policy.may_edit and (
            name in mutation_tools
            or name in ("run_command", "run_process", "process_run")
            or name.startswith("git_")
        ):
            return False, "", ("❌ BLOCKED: Current mode is read-only. Switch mode before executing changes.", False)

        policy_capability = ""
        policy_targets: list[str] = []
        if name in mutation_tools:
            policy_capability = "write"
            policy_targets = scope_paths
        elif name in ("run_command", "run_process", "process_run"):
            normalized_command = command.lower()
            if re.search(r"\bgit\s+push\b", normalized_command):
                policy_capability = "git_push"
            elif re.search(
                r"\b(?:pip|pip3|uv)\s+(?:pip\s+)?install\b"
                r"|\b(?:npm|pnpm|yarn)\s+(?:add|install)\b"
                r"|\bcargo\s+add\b|\bgo\s+get\b",
                normalized_command,
            ):
                policy_capability = "package_install"
            elif re.search(
                r"\b(?:kubectl\s+(?:apply|delete)|helm\s+(?:install|upgrade)|"
                r"terraform\s+apply|vercel\s+deploy)\b",
                normalized_command,
            ):
                policy_capability = "deployment"
            else:
                policy_capability = "command"
            policy_targets = [command]
        elif name.startswith("git_"):
            policy_capability = "command"
            policy_targets = [name]
        elif name in read_tools:
            policy_capability = "read"
            policy_targets = scope_paths or [name]
        elif name in ("web_fetch", "web_search", "api_check", "browser_check"):
            policy_capability = "network_access"
            policy_targets = [str(args.get("url") or args.get("query") or "")]

        if policy_capability:
            approval_targets = []
            for policy_target in policy_targets or [name]:
                policy_decision = self.policy.decide(
                    policy_capability,
                    policy_target,
                )
                extension_asked = False
                for provider in self.extensions.loaded("policies"):
                    external = str(
                        provider.decide(
                            policy_capability,
                            policy_target,
                            ToolContext(
                                working_dir=self.working_dir,
                                session_id=self.conversation_id,
                                permission_mode=self.permission_mode,
                            ),
                        )
                    ).lower()
                    if external == PermissionDecision.DENY.value:
                        policy_decision = PermissionDecision.DENY
                        break
                    if external == PermissionDecision.ASK.value:
                        policy_decision = PermissionDecision.ASK
                        extension_asked = True
                if policy_decision == PermissionDecision.DENY:
                    return False, "", (
                        f"❌ BLOCKED: repository policy denies {policy_capability} "
                        f"for {policy_target or name}.",
                        False,
                    )
                if policy_decision == PermissionDecision.ASK and (
                    self.policy.source or extension_asked
                ):
                    approval_targets.append(policy_target or name)
            policy_requires_approval = (
                approval_targets and not _user_confirmed
            )
            if policy_requires_approval:
                policy_target = ", ".join(approval_targets)
                policy_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{policy_capability}: {policy_target or name}",
                    reason=f"Repository policy requires approval for {policy_capability}",
                    details=policy_target or name,
                    requires_confirmation=True,
                )
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=policy_check,
                    edit_confirmed=_edit_confirmed,
                )
                return False, "", (
                    "⏸️ PENDING_CONFIRMATION "
                    f"[{confirmation_id}]: {policy_check.reason}. "
                    f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                    False,
                )
        return True, policy_capability, ("", False)

    def _enforce_network_safety(
        self,
        name: str,
        args: dict,
        command: str,
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
    ) -> tuple[bool, tuple[str, bool]]:
        requests_network = bool(args.get("network")) or bool(args.get("allow_external"))
        if requests_network and not _user_confirmed:
            network_check = SafetyCheck(
                level=SafetyLevel.DANGEROUS,
                operation=f"{name} network access",
                reason="Network access is disabled by default",
                details=command or str(args.get("url", "")),
                requires_confirmation=True,
            )
            confirmation_id = self._queue_confirmation(
                name=name,
                args=pending_args,
                safety_check=network_check,
                edit_confirmed=_edit_confirmed,
            )
            return False, (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {network_check.reason}. "
                f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                False,
            )
        return True, ("", False)

    def _enforce_package_safety(
        self,
        name: str,
        args: dict,
        command: str,
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
    ) -> tuple[bool, str, tuple[str, bool]]:
        package_checks = []
        package_warning_text = ""
        if name in mutation_tools:
            for package_path, proposed_content in self._dependency_candidates(name, args):
                package_checks.extend(self.package_guard.check_file_change(package_path, proposed_content))
        elif name in ("run_command", "run_process", "process_run") and command:
            package_checks = self.package_guard.check_command(command)
        if package_checks:
            for check in package_checks:
                self.evidence.append(
                    kind="package_registry",
                    claim=f"registry check for {check.registry}:{check.name}",
                    status=check.status,
                    tool=name,
                    raw_output=check.reason,
                    metadata={
                        "registry": check.registry,
                        "name": check.name,
                        "registry_url": check.url,
                    },
                )
            blocked = [check for check in package_checks if check.blocked]
            if blocked:
                details = "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}" for check in blocked
                )
                return False, "", (f"❌ BLOCKED by anti-slopsquatting guard:\n{details}", False)
            unverified = [
                check for check in package_checks if check.requires_confirmation
            ]
            if unverified and not _user_confirmed:
                details = "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}"
                    for check in unverified
                )
                uncertainty_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{name} with unverified package metadata",
                    reason=(
                        "The package registry could not be verified. This is not "
                        "treated as proof of a malicious package, but continuing "
                        "requires explicit approval"
                    ),
                    details=details,
                    requires_confirmation=True,
                )
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=uncertainty_check,
                    edit_confirmed=_edit_confirmed,
                )
                return False, "", (
                    "⏸️ PENDING_CONFIRMATION "
                    f"[{confirmation_id}]: {uncertainty_check.reason}. "
                    "This operation was not executed. Review the exact operation, then "
                    f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                    f"{details}",
                    False,
                )
            warnings = [check for check in package_checks if check.status == "warn"]
            if warnings:
                package_warning_text = "⚠️ PACKAGE RISK WARNING:\n" + "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}" for check in warnings
                )
        return True, package_warning_text, ("", False)

    def _prepare_mutation_diff(
        self,
        name: str,
        args: dict,
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
    ) -> tuple[bool, str, tuple[str, bool]]:
        mutation_diff = ""
        if name in mutation_tools:
            ok, mutation_diff = preview_mutation(name, args, self.working_dir)
            if not ok:
                return False, "", (f"❌ Cannot create a safe diff preview: {mutation_diff}", False)
            if self.mode_policy.require_review and not _edit_confirmed:
                confirmation_id = self._queue_edit(name, pending_args, mutation_diff)
                return False, "", (
                    "⏸️ PENDING_EDIT_CONFIRMATION "
                    f"[{confirmation_id}]: The file edit has been queued for review.\n"
                    f"Enter `/apply {confirmation_id}` or `/reject {confirmation_id}`.\n"
                    f"Diff preview:\n```diff\n{mutation_diff}\n```",
                    False,
                )
        return True, mutation_diff, ("", False)

    def _dispatch_tool_execution(
        self,
        name: str,
        args: dict,
    ) -> str:
        # Check plugin tool dispatch first
        plugin_handled = False
        for plugin in self.plugin_loader.plugins.values():
            dispatch = plugin.get_tool_dispatch()
            if name in dispatch:
                try:
                    return dispatch[name](**args)
                except Exception as e:
                    return f"❌ Plugin tool error: {e}"

        for extension_tool in self.extensions.loaded("tools"):
            if extension_tool.name != name:
                continue
            try:
                extension_result = extension_tool.invoke(
                    args,
                    ToolContext(
                        working_dir=self.working_dir,
                        session_id=self.conversation_id,
                        task_id=(
                            str(self._active_plan.current_step)
                            if self._active_plan is not None
                            else ""
                        ),
                        permission_mode=self.permission_mode,
                    ),
                )
                return (
                    extension_result
                    if isinstance(extension_result, str)
                    else json.dumps(extension_result, ensure_ascii=False)
                )
            except Exception as exc:
                return f"❌ Extension tool error: {exc}"

        if self.mcp.is_mcp_tool(name):
            return self.mcp.call_tool(name, args)
        else:
            return execute_tool(name, args)

    def _execute_tool_with_safety_impl(
        self,
        name: str,
        args: dict,
        *,
        _user_confirmed: bool = False,
        _edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        """
        Execute a tool with full safety checks, hooks, and context tracking.

        Pipeline: Before Hooks → Safety Check → Execute → Context Track → After Hooks → Reflection
        """
        from nexus.tools import normalize_tool_arguments
        args = normalize_tool_arguments(name, args)
        pending_args = dict(args)
        nova_guardrail = args.pop("_nova_guardrail", None)
        file_path = args.get("path", "") or args.get("file_path", "")
        command = args.get("command", "")
        if name == "run_process":
            raw_argv = args.get("argv", [])
            command = shlex.join(str(item) for item in raw_argv) if raw_argv else ""
        if name in {"run_command", "run_process", "process_run"} and re.search(
            r"\b(?:curl|wget|ssh|scp|sftp|ftp|rsync|gh)\b"
            r"|\bgit\s+(?:clone|fetch|pull|push)\b"
            r"|\b(?:pip|pip3|uv)\s+(?:pip\s+)?install\b"
            r"|\b(?:npm|pnpm|yarn)\s+(?:add|install|publish)\b"
            r"|\b(?:docker|podman)\s+(?:pull|push)\b"
            r"|\bcargo\s+(?:add|install)\b|\bgo\s+get\b",
            command.lower(),
        ) or name == "github_create_pr":
            args["network"] = True
            pending_args["network"] = True
        mutation_tools = ("write_file", "edit_file", "patch_file", "multi_edit")
        read_tools = {
            "read_file", "file_info", "diff_files", "search_code",
            "list_directory", "find_files", "get_project_structure",
            "repo_index", "repo_symbols", "repo_impact", "repo_context",
            "repo_routes", "repo_models", "repo_navigate",
            "database_check", "security_scan",
        }

        scope_paths = []
        if name == "multi_edit":
            scope_paths.extend(str(item.get("path", "")) for item in args.get("edits", []))
        elif file_path:
            scope_paths.append(str(file_path))
        if name == "diff_files":
            scope_paths.extend(str(args.get(key, "")) for key in ("file_a", "file_b"))
        elif name in {"search_code", "find_files"}:
            scope_paths.append(str(args.get("directory", "")))
        elif name in {"run_command", "run_process", "process_run"}:
            scope_paths.append(str(args.get("cwd", "")))
        elif name == "repo_impact":
            scope_paths.extend(str(item) for item in args.get("paths", []))
        elif name == "security_scan":
            scope_paths.extend(str(item) for item in args.get("paths", []) or [])
        elif name == "browser_check":
            scope_paths.append(str(args.get("screenshot_path", "")))
        scope_paths = list(dict.fromkeys(item for item in scope_paths if item))

        # ── 1. Enforce Tool Policy
        ok, policy_capability, err_res = self._enforce_tool_policy(
            name, args, command, scope_paths, pending_args, _user_confirmed, _edit_confirmed, mutation_tools, read_tools
        )
        if not ok: return err_res

        # ── 2. Enforce Network Safety
        ok, err_res = self._enforce_network_safety(name, args, command, pending_args, _user_confirmed, _edit_confirmed)
        if not ok: return err_res

        # Nova Guardrail checks for mutations
        if name in mutation_tools:
            if nova_guardrail is not None and not nova_guardrail.get("passed"):
                return "❌ BLOCKED: Nova guardrail metadata was present but did not pass.", False
            if self._is_nova_model() and (not nova_guardrail or not nova_guardrail.get("passed")):
                return (
                    "❌ BLOCKED: Nova file edit reached Nexus without a passing Nova "
                    "guardrail verdict (path validation, constraint verification, and disk gate).",
                    False,
                )
            early_edits = args.get("edits", []) if name == "multi_edit" else [args]
            for early_edit in early_edits:
                early_path = early_edit.get("path", "")
                early_content = (
                    early_edit.get("content", "")
                    or early_edit.get("new_text", "")
                    or early_edit.get("new_content", "")
                )
                early_check = self.safety.check_file_write(early_path, early_content)
                if early_check.level == SafetyLevel.BLOCKED:
                    return f"❌ BLOCKED: {early_check.reason}", False

        # Resolve scope outside workspace
        for scoped_path in (item for item in scope_paths if item):
            resolved_file = Path(scoped_path).expanduser()
            if not resolved_file.is_absolute():
                resolved_file = Path(self.working_dir) / resolved_file
            resolved_file = resolved_file.resolve()
            roots = [Path(self.working_dir), *(Path(item) for item in self.additional_dirs)]
            if any(_is_relative_to(resolved_file, root) for root in roots):
                continue
            if not _user_confirmed:
                scope_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{name} outside workspace",
                    reason="File access is outside the current workspace",
                    details=str(resolved_file),
                    requires_confirmation=True,
                )
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=scope_check,
                    edit_confirmed=_edit_confirmed,
                )
                return (
                    "⏸️ PENDING_CONFIRMATION "
                    f"[{confirmation_id}]: {scope_check.reason}. "
                    "This operation was not executed. Review the exact operation, then "
                    f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                    f"{scope_check.details}",
                    False,
                )

        # ── 3. Enforce Package Safety
        ok, package_warning_text, err_res = self._enforce_package_safety(
            name, args, command, pending_args, _user_confirmed, _edit_confirmed, mutation_tools
        )
        if not ok: return err_res

        # ── 4. File diff approval gate
        ok, mutation_diff, err_res = self._prepare_mutation_diff(
            name, args, pending_args, _user_confirmed, _edit_confirmed, mutation_tools
        )
        if not ok: return err_res

        # ── Fire BEFORE hooks
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
                "This operation was not executed. Review the exact operation, then "
                f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                f"{safety_check.details}",
                False,
            )

        # ── 5. Execute
        result = self._dispatch_tool_execution(name, args)

        success = not result.startswith(("❌", "⏰", "⏸️"))
        if name in ("api_check", "database_check", "browser_check", "security_scan"):
            try:
                success = json.loads(result).get("status") == "passed"
            except (AttributeError, TypeError, json.JSONDecodeError):
                success = False

        if package_warning_text:
            result = package_warning_text + "\n" + result

        # ── Verified-completion evidence
        if success and name in mutation_tools:
            verified, detail, artifacts = verify_mutation(name, args, self.working_dir)
            code_failures = []
            if verified:
                candidate_actions = []
                raw_paths = [edit.get("path", "") for edit in args.get("edits", [])] if name == "multi_edit" else [args.get("path", "")]
                for raw_path in raw_paths:
                    try:
                        target = Path(raw_path).expanduser()
                        if not target.is_absolute():
                            target = Path(self.working_dir) / target
                        relative = target.resolve().relative_to(Path(self.working_dir))
                        candidate_actions.append(SimpleNamespace(path=str(relative)))
                    except ValueError:
                        continue
                code_checks = GeneratedCodeValidator(self.working_dir).validate(candidate_actions)
                code_failures = [check for check in code_checks if not check.passed]
                if code_failures:
                    verified = False
                    detail = "compiler validation failed: " + " | ".join(check.format() for check in code_failures)
                    undo_count = len(args.get("edits", [])) if name == "multi_edit" else 1
                    rollback_ok, rollback_output = self.history.undo_changes(max(1, undo_count))
                    detail += f" | rollback={'succeeded' if rollback_ok else 'failed'}: {rollback_output}"
            self.evidence.append(
                kind="file_mutation",
                claim=f"{name} persisted the requested change",
                status="verified" if verified else "failed",
                tool=name,
                artifacts=artifacts,
                raw_output=result,
                metadata={"verification": detail},
            )
            if not verified:
                return f"❌ WRITE VERIFICATION FAILED: {detail}\nRaw tool output:\n{result}", False
            if self.run_ledger.turn_dir and mutation_diff:
                self.run_ledger.store_artifact(
                    "patches",
                    f"{name}-{len(self.history.changes):04d}.diff",
                    mutation_diff,
                )
            result += f"\n🔎 VERIFIED: {detail}\nEvidence: {self.evidence.path}"
        elif name in ("run_command", "run_process", "process_run"):
            exit_code = command_exit_code(result) if name in ("run_command", "run_process") else None
            status = "verified" if success and (exit_code == 0 or name == "process_run") else "failed"
            self.evidence.append(
                kind="command",
                claim=f"executed command: {command}",
                status=status,
                tool=name,
                command=command,
                exit_code=exit_code,
                raw_output=result,
            )
        elif name in ("api_check", "database_check", "browser_check", "security_scan"):
            probe_status = ""
            try:
                probe_status = str(json.loads(result).get("status", ""))
            except (TypeError, json.JSONDecodeError):
                pass
            self.evidence.append(
                kind="behavioral_verification",
                claim=f"executed {name}",
                status="verified" if success and probe_status == "passed" else "failed",
                tool=name,
                raw_output=result,
                metadata={"probe_status": probe_status},
            )
        elif name.startswith("git_"):
            self.evidence.append(
                kind="git_operation",
                claim=f"executed {name}",
                status="verified" if success else "failed",
                tool=name,
                raw_output=result,
                metadata={"arguments": args},
            )

        # ── 6. Track file access in context manager
        if file_path:
            was_edited = name in ("write_file", "edit_file", "patch_file", "multi_edit")
            self.context_mgr.track_file_access(file_path, was_edited=was_edited)
            if success and name == "read_file" and result:
                self.context_mgr.track_file_imports(file_path, result)
                self.context_mgr.summarize_file(file_path, result)

        # ── 7. Fire AFTER hooks
        if event_after:
            hook_ctx.event = event_after
            hook_ctx.tool_result = result
            self.hooks.fire(event_after, hook_ctx)

        # ── 8. Fire error hook on failure
        if not success:
            self.hooks.fire(HookEvent.ON_ERROR, HookContext(
                event=HookEvent.ON_ERROR,
                error_message=result[:500],
                tool_name=name,
                tool_args=args,
            ))

        return result, success
