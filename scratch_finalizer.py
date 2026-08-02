    def _evaluate_unrelated_files(
        self, criterion: str, plan: Any, changes: list
    ) -> CriterionResult:
        permitted = list(getattr(plan, "permitted_files", []) or [])
        outside = []
        for item in changes:
            changed_path = Path(item["filepath"]).resolve()
            if not _is_relative_to(changed_path, Path(self._agent.working_dir)):
                outside.append(item["filepath"])
                continue
            relative = changed_path.relative_to(Path(self._agent.working_dir).resolve()).as_posix()
            if permitted and not any(
                fnmatch(relative, pattern) or relative == pattern for pattern in permitted
            ):
                outside.append(relative)
        return CriterionResult(
            criterion,
            CriterionStatus.UNSATISFIED if outside else CriterionStatus.SATISFIED,
            detail=(
                "Out-of-scope changes: " + ", ".join(outside)
                if outside
                else (
                    "All recorded changes matched the plan's permitted files."
                    if permitted
                    else "All recorded changes remained inside the authorized workspace."
                )
            ),
        )

    def _evaluate_fingerprinted_mutations(self, criterion: str, evidence: list) -> CriterionResult:
        mutation_records = [item for item in evidence if item.get("kind") == "file_mutation"]
        task_type = get_task_type(self._agent._active_analysis.get("intent", IntentType.UNKNOWN))
        satisfied = (
            (not mutation_records and task_type == TaskType.READ_ONLY)
            or bool(mutation_records)
            and all(item.get("status") == "verified" for item in mutation_records)
        )
        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if satisfied else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in mutation_records],
            detail=(
                "Every recorded mutation passed disk verification."
                if satisfied
                else "No complete verified mutation set was recorded."
            ),
        )

    def _evaluate_objective_implementation(
        self,
        criterion: str,
        verified_mutations: list,
        passing_checks: list,
        passing_behavioral: list,
        approved_reviews: list,
        successful_command_text: set,
    ) -> CriterionResult:
        objective_evidence = [
            *verified_mutations,
            *passing_checks,
            *passing_behavioral,
            *approved_reviews,
        ]
        task_type = get_task_type(self._agent._active_analysis.get("intent", IntentType.UNKNOWN))

        if task_type == TaskType.READ_ONLY:
            objective_satisfied = True
        elif task_type == TaskType.OPERATIONAL:
            objective_satisfied = bool(
                passing_checks or passing_behavioral or successful_command_text
            )
        else:
            review_satisfied = bool(approved_reviews) or (
                self._agent._is_nova_model() and not self._agent.mode_policy.require_review
            )
            objective_satisfied = (
                bool(verified_mutations)
                and bool(passing_checks or passing_behavioral)
                and review_satisfied
            )

        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if objective_satisfied else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in objective_evidence],
            detail=(
                (
                    "Verified mutations and deterministic checks support the objective; "
                    "this local-only run has no independent semantic reviewer."
                    if self._agent._is_nova_model() and not approved_reviews
                    else "Verified mutations, deterministic checks, and independent review "
                    "support the requested objective."
                )
                if objective_satisfied
                else "A mutation alone is insufficient; deterministic checks and the "
                "review assurance required by this mode must be present."
            ),
        )

    def _evaluate_verification_checks(
        self, criterion: str, matched_checks: list
    ) -> CriterionResult:
        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if matched_checks else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in matched_checks],
            detail=(
                "A matching passing project check exists."
                if matched_checks
                else "No matching passing project check was recorded."
            ),
        )

    def _evaluate_security_constraints(
        self, criterion: str, passing_behavioral: list, matched_checks: list
    ) -> CriterionResult:
        security_evidence = [
            item for item in passing_behavioral if item.get("tool") == "security_scan"
        ] + matched_checks
        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if security_evidence else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in security_evidence],
            detail=(
                "A passing bounded security check was recorded."
                if security_evidence
                else "No passing security check was recorded."
            ),
        )

    def _apply_verified_workspace(self) -> tuple[bool, str]:
        """Apply a verified isolated workspace exactly once.

        Automatic application is restricted to modes whose policy explicitly
        grants ``may_apply``. Review/workspace modes continue to return a diff
        for human approval. A failed merge is treated as a failed run rather
        than reporting a false VERIFIED outcome.
        """
        if self._agent._workspace_applied:
            return True, self._agent._workspace_apply_detail or "Workspace already applied."
        if not self._agent.mode_policy.may_apply:
            return True, "Execution mode requires manual workspace application."
        if self._agent.worktree is None or self._agent.worktree.info is None:
            return True, "No isolated workspace needs application."

        try:
            pending_diff = self._agent.worktree.diff()
            if not pending_diff.strip():
                self._agent._workspace_applied = True
                self._agent._workspace_apply_detail = "Verified run produced no workspace diff."
                return True, self._agent._workspace_apply_detail
            self._agent.worktree.apply()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            detail = f"Verified workspace could not be applied safely: {exc}"
            self._agent._workspace_apply_detail = detail
            self._agent.evidence.append(
                kind="workspace_apply",
                claim="apply verified isolated workspace to source repository",
                status="failed",
                raw_output=detail,
                metadata={
                    "source": self._agent.source_working_dir,
                    "workspace": self._agent.working_dir,
                },
            )
            return False, detail

        self._agent._workspace_applied = True
        self._agent._workspace_apply_detail = (
            "Verified isolated workspace was applied to the source repository."
        )
        self._agent._permissions_used.add("workspace: apply verified changes")
        self._agent.evidence.append(
            kind="workspace_apply",
            claim="apply verified isolated workspace to source repository",
            status="verified",
            raw_output=self._agent._workspace_apply_detail,
            metadata={
                "source": self._agent.source_working_dir,
                "workspace": self._agent.working_dir,
                "backend": self._agent.worktree.info.backend,
            },
        )
        return True, self._agent._workspace_apply_detail

    def finish(
        self,
        content: str,
        events: list[dict[str, Any]] | None = None,
        *,
        status_override: RunStatus | None = None,
    ) -> dict[str, Any]:
        """Evaluate evidence and write a machine-readable final report."""
        if not self._agent.run_ledger.turn_dir:
            return {}
        evidence = self._agent.evidence.records()[getattr(self, "_turn_evidence_start", 0) :]
        mutation_records = self._agent._effective_evidence(evidence, "file_mutation")
        verification_records = self._agent._effective_evidence(evidence, "verification_check")
        effective_state_ids = {
            str(item.get("id")) for item in [*mutation_records, *verification_records]
        }
        changes = self._agent.history.changes[self._agent._run_history_start :]
        command_records = [item for item in evidence if item.get("kind") == "command"]
        passing_commands = [
            item
            for item in command_records
            if item.get("status") == "verified" and item.get("exit_code") == 0
        ]
        successful_command_text = {
            item.get("command", "") for item in passing_commands if item.get("command")
        }
        latest_behavioral_status = {
            item.get("tool", ""): item.get("status")
            for item in evidence
            if item.get("kind") == "behavioral_verification"
        }
        failed_evidence = [
            item
            for item in evidence
            if item.get("status") == "failed"
            and item.get("kind") not in {"routing", "independent_review"}
            and (
                item.get("kind") not in {"file_mutation", "verification_check"}
                or str(item.get("id")) in effective_state_ids
            )
            and not (
                item.get("kind") == "command" and item.get("command", "") in successful_command_text
            )
            and not (
                item.get("kind") == "behavioral_verification"
                and latest_behavioral_status.get(item.get("tool", "")) == "verified"
            )
        ]
        verified_mutations = [item for item in mutation_records if item.get("status") == "verified"]
        passing_behavioral = [
            item
            for item in evidence
            if item.get("kind") == "behavioral_verification" and item.get("status") == "verified"
        ]
        approved_reviews = [
            item
            for item in evidence
            if item.get("kind") == "independent_review" and item.get("status") == "verified"
        ]
        passing_checks = [item for item in verification_records if item.get("status") == "verified"]
        reproduction_evidence = [
            item
            for item in command_records
            if item.get("status") == "failed" or item.get("exit_code") not in (None, 0)
        ] + [
            item for item in evidence
            if item.get("kind") == "verification_check" and item.get("status") == "failed"
        ]

        def matching_checks(criterion: str) -> list[dict[str, Any]]:
            lowered = criterion.lower()
            passing_by_type: dict[str, list[dict[str, Any]]] = {}
            for item in passing_checks:
                check_type = str(item.get("metadata", {}).get("check_type", ""))
                passing_by_type.setdefault(check_type, []).append(item)

            if "executable test" in lowered and "build" in lowered:
                target_types = {"test", "build", "browser", "api", "database"}
            elif "lint" in lowered and "type" in lowered:
                # A build is neither a linter nor a type checker. Combined
                # criteria require one passing record of each exact type.
                if not passing_by_type.get("lint") or not passing_by_type.get("type_check"):
                    return []
                return [*passing_by_type["lint"], *passing_by_type["type_check"]]
            elif "lint" in lowered:
                target_types = {"lint"}
            elif "type" in lowered:
                target_types = {"type_check"}
            elif "security" in lowered or "vulnerab" in lowered:
                target_types = {"security"}
            elif "coverage" in lowered:
                target_types = {"coverage"}
            elif "build" in lowered or "compile" in lowered:
                target_types = {"build"}
            elif "test" in lowered or "regression" in lowered:
                target_types = {"test"}
            elif "run the project" in lowered or "works" in lowered or "smoke" in lowered:
                target_types = {"test", "build", "browser", "api", "database"}
            else:
                return []
            return [
                item
                for item in passing_checks
                if item.get("metadata", {}).get("check_type") in target_types
            ]

        plan = self._agent._active_plan
        if plan is not None:
            criteria_text = list(plan.acceptance_criteria)
            self._agent.run_ledger.record_plan(plan)
        else:
            verification = self._agent._applicable_verification(
                self._agent._active_analysis.get("intent", IntentType.UNKNOWN),
                self._agent._active_analysis.get("skills_needed", []),
            )
            criteria_text = self._agent.planner._generate_acceptance_criteria(
                self._agent._active_objective,
                self._agent._active_analysis.get("intent", IntentType.UNKNOWN),
                verification,
            )

        results: list[CriterionResult] = []
        for criterion in criteria_text:
            lowered = criterion.lower()
            if "unrelated files" in lowered:
                results.append(self._evaluate_unrelated_files(criterion, plan, changes))
            elif "fingerprinted" in lowered:
                results.append(self._evaluate_fingerprinted_mutations(criterion, evidence))
            elif "requested objective is implemented" in lowered:
                results.append(
                    self._evaluate_objective_implementation(
                        criterion,
                        verified_mutations,
                        passing_checks,
                        passing_behavioral,
                        approved_reviews,
                        successful_command_text,
                    )
                )
            elif "reported failure is reproduced" in lowered:
                results.append(
                    CriterionResult(
                        criterion,
                        CriterionStatus.SATISFIED
                        if reproduction_evidence
                        else CriterionStatus.UNVERIFIED,
                        evidence_ids=[item["id"] for item in reproduction_evidence],
                        detail=(
                            "A failing command or verification check reproduced the defect before repair."
                            if reproduction_evidence
                            else "No failing reproduction evidence was recorded before the fix."
                        ),
                    )
                )
            elif "security" in lowered or "vulnerab" in lowered:
                results.append(
                    self._evaluate_security_constraints(
                        criterion, passing_behavioral, matching_checks(criterion)
                    )
                )
            elif "verification completed" in lowered or any(
                term in lowered
                for term in (
                    "test",
                    "regression",
                    "build",
                    "lint",
                    "type",
                    "coverage",
                    "smoke check",
                )
            ):
                results.append(
                    self._evaluate_verification_checks(criterion, matching_checks(criterion))
                )
            elif failed_evidence:
                results.append(
                    CriterionResult(
                        criterion,
                        CriterionStatus.UNSATISFIED,
                        evidence_ids=[item["id"] for item in failed_evidence],
                        detail="One or more execution evidence records failed.",
                    )
                )
            else:
                results.append(
                    CriterionResult(
                        criterion,
                        CriterionStatus.UNVERIFIED,
                        detail="The run did not record sufficient deterministic evidence.",
                    )
                )

        # Autonomous execution is iterative: a failed command or edit attempt
        # is not an unresolved run failure when a later call to that tool
        # succeeds and final deterministic verification passes.
        latest_tool_events: dict[str, dict[str, Any]] = {}
        for item in events or []:
            if item.get("type") == "tool_call":
                latest_tool_events[str(item.get("name", "unknown"))] = item
        event_failures = [
            item for item in latest_tool_events.values() if not item.get("success", False)
        ]
        if status_override is not None:
            run_status = status_override
        elif (content or "").strip().upper().startswith("BLOCKED:"):
            run_status = RunStatus.BLOCKED
        elif self._agent._pending_edits or self._agent._pending_confirmations:
            run_status = RunStatus.AWAITING_APPROVAL
        elif failed_evidence or event_failures:
            run_status = (
                RunStatus.PARTIALLY_VERIFIED
                if verified_mutations or passing_checks
                else RunStatus.FAILED
            )
        elif results and all(item.status == CriterionStatus.SATISFIED for item in results):
            run_status = RunStatus.VERIFIED
        elif verified_mutations or passing_checks:
            run_status = RunStatus.PARTIALLY_VERIFIED
        else:
            run_status = RunStatus.UNVERIFIED

        workspace_apply_error = ""
        if run_status == RunStatus.VERIFIED and self._agent.mode_policy.may_apply:
            applied, apply_detail = self._agent._apply_verified_workspace()
            if not applied:
                workspace_apply_error = apply_detail
                run_status = RunStatus.FAILED

        checks = [
            {
                "evidence_id": item.get("id"),
                "command": item.get("command", ""),
                "status": item.get("status"),
                "exit_code": item.get("exit_code"),
            }
            for item in evidence
            if item.get("kind") == "command"
        ]
        risks = []
        if run_status != RunStatus.VERIFIED:
            risks.append("Not every acceptance criterion has passing deterministic evidence.")
        if self._agent._pending_edits:
            risks.append(f"{len(self._agent._pending_edits)} file edit(s) still require approval.")
        if self._agent._pending_confirmations:
            risks.append(
                f"{len(self._agent._pending_confirmations)} protected operation(s) still require approval."
            )
        if workspace_apply_error:
            risks.append(workspace_apply_error)

        if run_status == RunStatus.VERIFIED:
            outcome = "COMPLETED_VERIFIED"
        elif run_status == RunStatus.BLOCKED:
            outcome = "BLOCKED_BY_POLICY"
        elif run_status == RunStatus.AWAITING_APPROVAL:
            outcome = "AWAITING_APPROVAL"
        elif run_status == RunStatus.ROLLED_BACK:
            outcome = "ROLLED_BACK"
        elif run_status == RunStatus.FAILED:
            outcome = "FAILED"
        elif changes:
            outcome = "CHANGES_APPLIED_UNVERIFIED"
        elif run_status == RunStatus.PARTIALLY_VERIFIED:
            outcome = "COMPLETED_PARTIALLY_VERIFIED"
        else:
            outcome = "NO_CHANGES"

        turn_dir = self._agent.run_ledger.turn_dir
        model_call_records, _model_call_corruption = self._agent.run_ledger.read_jsonl("model_calls.jsonl")
        logical_model_calls = [
            item for item in model_call_records if item.get("role") != "provider_attempt"
        ]
        provider_attempt_records = [
            item for item in model_call_records if item.get("role") == "provider_attempt"
        ]

        def jsonl_count(filename: str) -> int:
            if turn_dir is None:
                return 0
            try:
                return sum(
                    1
                    for line in (turn_dir / filename).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            except OSError:
                return 0

        def event_kind_count(kind: str) -> int:
            if turn_dir is None:
                return 0
            try:
                records = [
                    json.loads(line)
                    for line in (turn_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except (OSError, json.JSONDecodeError):
                return 0
            return sum(item.get("kind") == kind for item in records)

        report = self._agent.run_ledger.finalize(
            run_status,
            objective=self._agent._active_objective,
            outcome=outcome,
            criteria=results,
            files_changed=[item["filepath"] for item in changes],
            checks=checks,
            costs=self._agent.budget.snapshot(),
            risks=risks,
            work_completed=[f"Updated {Path(item['filepath']).name}" for item in changes],
            checks_skipped=[
                item.criterion
                for item in results
                if item.status
                in {
                    CriterionStatus.SKIPPED,
                    CriterionStatus.BLOCKED,
                    CriterionStatus.UNVERIFIED,
                }
            ],
            dependencies_added=sorted(
                {
                    (
                        f"{item.get('metadata', {}).get('registry', 'registry')}:"
                        f"{item.get('metadata', {}).get('name', 'unknown')}"
                    )
                    for item in evidence
                    if item.get("kind") == "package_registry"
                    and item.get("status") in {"pass", "warn"}
                }
            ),
            permissions_used=sorted(self._agent._permissions_used),
            network_calls=list(dict.fromkeys(self._agent._network_calls)),
            model_providers=list(
                dict.fromkeys(
                    [
                        self._agent.model_key,
                        *(
                            [self._agent.model_cfg.get("intern_model", "nova_codex")]
                            if self._agent.routing_stats["nova_tasks"]
                            else []
                        ),
                    ]
                )
            ),
            assumptions=[],
            metadata={
                "model": self._agent.model_key,
                "response_excerpt": _redact_runtime_text((content or "")[:2000]),
                "evidence_path": str(self._agent.evidence.path),
                "workspace": self._agent.working_dir,
                "history_start": self._agent._run_history_start,
                "history_end": len(self._agent.history.changes),
                "local_intern_mode": self._agent.local_intern_mode,
                "local_intern_enabled": self._agent.local_intern_enabled,
                "plugins_enabled": self._agent._plugins_enabled,
                "model_calls": len(logical_model_calls),
                "provider_attempts": len(provider_attempt_records),
                "tool_calls": jsonl_count("tool_calls.jsonl"),
                "tests_executed": len(verification_records),
                "criteria_satisfied": sum(
                    item.status == CriterionStatus.SATISFIED for item in results
                ),
                "criteria_unverified": sum(
                    item.status == CriterionStatus.UNVERIFIED for item in results
                ),
                "rollbacks": event_kind_count("rollback"),
                "workspace_applied": self._agent._workspace_applied,
                "workspace_apply_detail": self._agent._workspace_apply_detail,
                "review_assurance": (
                    "independent_semantic"
                    if approved_reviews
                    else ("deterministic_only" if self._agent._is_nova_model() else "none")
                ),
            },
        )
        return report

    def get_run_status(self) -> str:
        """Return the latest durable run and workspace status."""
        summary = self._agent.run_ledger.resume_summary()
        if not summary:
            return "No durable run exists for this session."
        state = summary.get("state", {})
        report = summary.get("final_report", {})
        lines = [
            f"Run: {state.get('turn_id', 'unknown')}",
            f"Status: {report.get('status') or state.get('status', 'unknown')}",
            f"Objective: {report.get('objective') or summary.get('request', {}).get('request', '')}",
            f"Run directory: {self._agent.run_ledger._latest_turn_dir()}",
        ]
        if self._agent.worktree:
            worktree_status = self._agent.worktree.status()
            lines.extend(
                [
                    f"Worktree: {worktree_status.get('path', self._agent.working_dir)}",
                    f"Branch: {worktree_status.get('branch', '')}",
                    worktree_status.get("git_status", ""),
                ]
            )
        checkpoint = summary.get("checkpoint", {})
        if checkpoint:
            lines.append(
                f"Latest checkpoint: {checkpoint.get('checkpoint')} {checkpoint.get('label', '')}"
            )
        return "\n".join(item for item in lines if item)

    def rollback_current_run(self) -> tuple[bool, str]:
        """Atomically roll back every file operation recorded by this run."""
        change_count = len(self._agent.history.changes) - self._agent._run_history_start
        if change_count <= 0:
            return False, "The current run has no applied file changes to roll back."
        success, detail = self._agent.history.undo_changes(change_count)
        if success:
            self._agent.run_ledger.mark_rolled_back(detail)
            try:
                self._agent.repo_graph.build()
            except (OSError, ValueError) as exc:
                logger.debug("Repository graph refresh after rollback failed: %s", exc)
        return success, detail

    def _refresh_final_report_after_approval(self) -> None:
        """Recompute the final status after an approval queue changes."""
        if not self._agent.run_ledger.turn_dir or not self._agent._active_objective:
            return
        prior = self._agent.run_ledger.resume_summary().get("final_report", {})
        content = prior.get("metadata", {}).get("response_excerpt", "")
        self._agent._run_finalizer.finish(content, [])
