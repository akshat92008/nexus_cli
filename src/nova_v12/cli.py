from __future__ import annotations

import argparse
import json
from pathlib import Path

from nova_v12.eval.tasks import validate_tasks
from nova_v12.schemas import load_jsonl, write_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova-v12", description="Amaura Nova v12 engineering toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("validate-tasks", help="Validate executable evaluation tasks")
    command.add_argument("path")

    command = sub.add_parser("run-eval", help="Generate outputs for an evaluation task set")
    command.add_argument("--tasks", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--candidate-id", required=True)
    command.add_argument("--backend", choices=["ollama", "transformers"], required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--revision")
    command.add_argument("--trust-remote-code", action="store_true")
    command.add_argument("--max-tokens", type=int, default=2048)
    command.add_argument("--temperature", type=float, default=0.0)


    command = sub.add_parser("bakeoff", help="Run and score a configured candidate track")
    command.add_argument("--config", required=True)
    command.add_argument("--tasks", required=True)
    command.add_argument("--output-dir", required=True)
    command.add_argument("--track", default="foundation_track")
    command.add_argument("--max-tokens", type=int, default=2048)
    command.add_argument("--temperature", type=float, default=0.0)

    command = sub.add_parser("score-results", help="Execute and score saved model generations")
    command.add_argument("--results", required=True)
    command.add_argument("--output", required=True)


    command = sub.add_parser("split-data", help="Split JSONL by repository or snapshot")
    command.add_argument("--input", required=True)
    command.add_argument("--output-dir", required=True)
    command.add_argument("--key-field", default="repository")
    command.add_argument("--seed", type=int, default=42)
    command.add_argument("--train", type=float, default=0.98)
    command.add_argument("--validation", type=float, default=0.01)
    command.add_argument("--test", type=float, default=0.01)

    command = sub.add_parser("build-data", help="Build a filtered, auditable code corpus")
    command.add_argument("--config", required=True)

    command = sub.add_parser("scan-contamination", help="Recursively scan JSONL records")
    command.add_argument("--input", required=True)
    command.add_argument("--signatures", required=True)
    command.add_argument("--output", required=True)

    command = sub.add_parser("verify-mutations", help="Keep only execution-verified mutations")
    command.add_argument("--input", required=True)
    command.add_argument("--output", required=True)

    for name, validator_help in (
        ("validate-sft", "Validate SFT JSONL records"),
        ("validate-dpo", "Validate DPO JSONL records"),
    ):
        command = sub.add_parser(name, help=validator_help)
        command.add_argument("--input", required=True)
        command.add_argument("--rejected")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-tasks":
        count, errors = validate_tasks(args.path)
        print(json.dumps({"tasks": count, "valid": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 1
    if args.command == "run-eval":
        from nova_v12.eval.backends import OllamaBackend, TransformersBackend
        from nova_v12.eval.runner import run_tasks

        if args.backend == "ollama":
            backend = OllamaBackend(args.model)
        else:
            backend = TransformersBackend(
                args.model, trust_remote_code=args.trust_remote_code, revision=args.revision
            )
        results = run_tasks(
            backend,
            args.candidate_id,
            args.tasks,
            args.output,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        print(json.dumps({"generated": len(results), "output": args.output}, indent=2))
        return 0
    if args.command == "bakeoff":
        from nova_v12.eval.bakeoff import run_bakeoff

        report = run_bakeoff(
            args.config,
            args.tasks,
            args.output_dir,
            track=args.track,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "score-results":
        from nova_v12.eval.scorer import score_results

        scores, summary = score_results(args.results)
        payload = {"summary": summary, "scores": [score.to_dict() for score in scores]}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.command == "split-data":
        from nova_v12.data.split import split_jsonl

        counts = split_jsonl(
            args.input,
            args.output_dir,
            key_field=args.key_field,
            seed=args.seed,
            train=args.train,
            validation=args.validation,
            test=args.test,
        )
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0
    if args.command == "build-data":
        from nova_v12.data.pipeline import build_data

        print(json.dumps(build_data(args.config), indent=2, sort_keys=True))
        return 0
    if args.command == "scan-contamination":
        from nova_v12.data.contamination import ContaminationScanner

        scanner = ContaminationScanner.from_file(args.signatures)
        values = []
        contaminated = 0
        for record in load_jsonl(args.input):
            findings = scanner.scan(record)
            if findings:
                contaminated += 1
            values.append({"record": record, "findings": [item.to_dict() for item in findings]})
        write_jsonl(args.output, values)
        print(json.dumps({"records": len(values), "contaminated": contaminated}, indent=2))
        return 1 if contaminated else 0
    if args.command == "verify-mutations":
        from nova_v12.data.mutations import verify_mutation_file

        accepted, rejected = verify_mutation_file(args.input, args.output)
        print(json.dumps({"accepted": accepted, "rejected": rejected}, indent=2))
        return 0 if accepted else 1
    if args.command in {"validate-sft", "validate-dpo"}:
        from nova_v12.data.validators import validate_dpo_record, validate_sft_record

        validator = validate_sft_record if args.command == "validate-sft" else validate_dpo_record
        accepted = []
        rejected = []
        for record in load_jsonl(args.input):
            report = validator(record)
            if report.valid:
                accepted.append(record)
            else:
                rejected.append({"record": record, "errors": report.errors})
        if args.rejected:
            write_jsonl(args.rejected, rejected)
        print(json.dumps({"valid": len(accepted), "invalid": len(rejected)}, indent=2))
        return 0 if not rejected else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
