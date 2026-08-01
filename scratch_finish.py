    def _finish_managed_run(
        self,
        content: str,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate evidence and write a machine-readable final report."""
        if not self.run_ledger.turn_dir:
            return {}
        evidence = self.evidence.records()[getattr(self, "_turn_evidence_start", 0) :]
        changes = self.history.changes[self._run_history_start :]
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
            and not (
                item.get("kind") == "command"
                and item.get("command", "") in successful_command_text
            )
            and not (
                item.get("kind") == "behavioral_verification"
                and latest_behavioral_status.get(item.get("tool", "")) == "verified"
            )
        ]
        verified_mutations = [
            item
            for item in evidence
            if item.get("kind") == "file_mutation" and item.get("status") == "verified"
        ]
        passing_behavioral = [
            item
            for item in evidence
            if item.get("kind") == "behavioral_verification"
            and item.get("status") == "verified"
        ]
        approved_reviews = [
            item
            for item in evidence
            if item.get("kind") == "independent_review"
            and item.get("status") == "verified"
        ]
        verification_records = [
            item for item in evidence if item.get("kind") == "verification_check"
        ]
        passing_checks = [
            item for item in verification_records if item.get("status") == "verified"
        ]

        def matching_checks(criterion: str) -> list[dict[str, Any]]:
            lowered = criterion.lower()
            if "lint" in lowered or "type" in lowered:
                target_types = {"lint", "type_check"}
            elif "security" in lowered or "vulnerab" in lowered:
                target_types = {"security"}
            elif "build" in lowered or "compile" in lowered:
                target_types = {"build"}
            elif "test" in lowered or "regression" in lowered or "coverage" in lowered:
                target_types = {"test", "browser", "database", "api"}
            else:
                return []
            return [
                item
                for item in passing_checks
                if item.get("metadata", {}).get("check_type") in target_types
            ]

        plan = self._active_plan
        if plan is not None:
            criteria_text = list(plan.acceptance_criteria)
            self.run_ledger.record_plan(plan)
        else:
            criteria_text = self.planner._generate_acceptance_criteria(
                self._active_objective,
                self._active_analysis.get("intent", IntentType.UNKNOWN),
                self.planner._generate_verification(
                    self._active_analysis.get("intent", IntentType.UNKNOWN),
                    self._active_analysis.get("skills_needed", []),
                ),
            )

        results: list[CriterionResult] = []
        for criterion in criteria_text:
            lowered = criterion.lower()
            if "unrelated files" in lowered:
                permitted = list(getattr(plan, "permitted_files", []) or [])
                outside = []
                for item in changes:
                    changed_path = Path(item["filepath"]).resolve()
                    if not _is_relative_to(changed_path, Path(self.working_dir)):
                        outside.append(item["filepath"])
                        continue
                    relative = changed_path.relative_to(
                        Path(self.working_dir).resolve()
                    ).as_posix()
                    if permitted and not any(
                        fnmatch(relative, pattern) or relative == pattern
                        for pattern in permitted
                    ):
                        outside.append(relative)
                results.append(
                    CriterionResult(
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
                )
            elif "fingerprinted" in lowered:
                mutation_records = [
                    item for item in evidence if item.get("kind") == "file_mutation"
                ]
                satisfied = bool(mutation_records) and all(
                    item.get("status") == "verified" for item in mutation_records
                )
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if satisfied
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in mutation_records],
                        detail=(
                            "Every recorded mutation passed disk verification."
                            if satisfied
                            else "No complete verified mutation set was recorded."
                        ),
                    )
                )
            elif "requested objective is implemented" in lowered:
                objective_evidence = [
                    *verified_mutations,
                    *passing_checks,
                    *passing_behavioral,
                    *approved_reviews,
                ]
                task_type = get_task_type(self._active_analysis.get("intent", IntentType.UNKNOWN))
                
                if task_type == TaskType.READ_ONLY:
                    objective_satisfied = True
                elif task_type == TaskType.OPERATIONAL:
                    objective_satisfied = bool(passing_checks or passing_behavioral or successful_command_text)
                else:
                    objective_satisfied = bool(verified_mutations) and bool(
                        passing_checks or passing_behavioral
                    ) and bool(approved_reviews or self._is_nova_model())

                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if objective_satisfied
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in objective_evidence],
                        detail=(
                            "Verified mutations, deterministic checks, and worker review "
                            "support the requested objective."
                            if objective_satisfied
                            else "A mutation alone is insufficient; deterministic checks "
                            "and review evidence are required."
                        ),
                    )
                )
            elif "security" in lowered or "vulnerab" in lowered:
                security_evidence = [
                    item
                    for item in passing_behavioral
                    if item.get("tool") == "security_scan"
                ] + matching_checks(criterion)
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if security_evidence
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in security_evidence],
                        detail=(
                            "A passing bounded security check was recorded."
                            if security_evidence
                            else "No passing security check was recorded."
                        ),
                    )
                )
            elif "verification completed" in lowered or any(
                term in lowered for term in ("test", "build", "lint", "smoke check")
            ):
                matched_checks = matching_checks(criterion)
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if matched_checks
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in matched_checks],
                        detail=(
                            "A matching passing project check exists."
                            if matched_checks
                            else "No matching passing project check was recorded."
                        ),
                    )
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

        event_failures = [
            item for item in (events or []) if item.get("type") == "tool_call" and not item.get("success")
        ]
        if (content or "").strip().upper().startswith("BLOCKED:"):
            run_status = RunStatus.BLOCKED
        elif self._pending_edits or self._pending_confirmations:
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
        if self._pending_edits:
            risks.append(f"{len(self._pending_edits)} file edit(s) still require approval.")
        if self._pending_confirmations:
            risks.append(
                f"{len(self._pending_confirmations)} protected operation(s) still require approval."
            )

        report = self.run_ledger.finalize(
            run_status,
            objective=self._active_objective,
            criteria=results,
            files_changed=[item["filepath"] for item in changes],
            checks=checks,
            costs=self.budget.snapshot(),
            risks=risks,
            work_completed=[
                f"Updated {Path(item['filepath']).name}" for item in changes
            ],
            checks_skipped=[
                item.criterion
                for item in results
                if item.status in {
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
            permissions_used=sorted(self._permissions_used),
            network_calls=list(dict.fromkeys(self._network_calls)),
            model_providers=list(
                dict.fromkeys(
                    [
                        self.model_key,
                        *(
                            [self.model_cfg.get("intern_model", "nova_codex")]
                            if self.routing_stats["nova_tasks"]
                            else []
                        ),
                    ]
                )
            ),
            assumptions=[],
            metadata={
                "model": self.model_key,
                "response_excerpt": _redact_runtime_text((content or "")[:2000]),
                "evidence_path": str(self.evidence.path),
                "workspace": self.working_dir,
                "history_start": self._run_history_start,
                "history_end": len(self.history.changes),
                "local_intern_mode": self.local_intern_mode,
                "local_intern_enabled": self.local_intern_enabled,
                "plugins_enabled": self._plugins_enabled,
            },
        )
        return report
