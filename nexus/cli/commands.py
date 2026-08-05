import argparse
import json
import os
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from nexus import __version__, ui
from nexus.agent import Agent
from nexus.doctor import run_doctor
from nexus.memory import ConversationMemory
from nexus.models import DEFAULT_MODEL, resolve_model
from nexus.policy import get_mode_policy
from nexus.run_catalog import RunCatalog
from nexus.tools import get_history, tool_get_project_structure

def _handle_workspace_commands() -> bool:
    """Implementation for managing Git and non-Git isolated copies."""
    if len(sys.argv) < 2 or sys.argv[1] != "workspace":
        return False
    if len(sys.argv) < 3 or sys.argv[2] not in {"list", "status", "diff", "apply", "discard"}:
        print("Usage: nexus workspace {list|status|diff|apply|discard} [session_id]")
        return True

    command = sys.argv[2]
    from nexus.workspace import WorkspaceManager

    manager = WorkspaceManager()

    if command == "list":
        worktrees = manager.list_worktrees()
        if not worktrees:
            print("No active workspaces.")
        else:
            for w in worktrees:
                print(
                    f"[{w.created_at}] {Path(w.path).name} - {w.backend} - {w.branch or 'N/A'} (Source: {w.source_repository})"
                )
        return True

    session_id = sys.argv[3] if len(sys.argv) > 3 else None
    if not session_id:
        cwd = os.getcwd()
        worktrees = manager.list_worktrees()
        worktrees = [w for w in worktrees if w.source_repository == cwd]
        if not worktrees:
            print("No active workspaces for current directory.")
            return True
        session = manager.resolve_worktree(Path(worktrees[0].path).name)
    else:
        session = manager.resolve_worktree(session_id)

    if not session or not session.info:
        print("Workspace not found.")
        return True

    if command == "status":
        print(json.dumps(session.status(), indent=2))
    elif command == "diff":
        diff_text = session.diff()
        if diff_text:
            print(diff_text)
        else:
            print("No changes.")
    elif command == "apply":
        try:
            session.apply()
            from nexus.ui import print_success

            print_success("Workspace changes applied successfully.")
        except ImportError as e:
            from nexus.ui import print_error

            print_error(f"Apply failed: {e}")
    elif command == "discard":
        session.discard()
        from nexus.ui import print_success

        print_success("Workspace discarded.")

    return True

def _handle_run_management() -> bool:
    """Handle durable run inspection commands before model initialization."""
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "runs",
        "inspect",
        "replay",
        "rollback",
    }:
        return False
    command = sys.argv[1]
    catalog = RunCatalog()
    if command == "runs":
        working_dir = os.getcwd()
        records = catalog.list(working_dir=working_dir, limit=100)
        if "--json" in sys.argv[2:]:
            print(json.dumps([item.__dict__ for item in records], indent=2))
        elif not records:
            print("No durable Nexus runs exist for this directory.")
        else:
            for item in records:
                print(f"{item.session_id}/{item.turn_id}  {item.status:<20} {item.request[:80]}")
        return True

    run_id = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        if command == "inspect":
            print(json.dumps(catalog.inspect(run_id), indent=2))
        elif command == "replay":
            for event in catalog.replay(run_id):
                print(json.dumps(event, ensure_ascii=False))
        else:
            from nexus.recovery import RollbackManager

            success, detail = RollbackManager.rollback(run_id)
            if not success:
                raise RuntimeError(detail)
            print(detail)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return True

def _handle_generate_dashboard() -> bool:
    """Resolve ``nexus generate-dashboard --input <json> --output <html_path>``."""
    if len(sys.argv) < 2 or sys.argv[1] != "generate-dashboard":
        return False
    import argparse

    parser = argparse.ArgumentParser(prog="nexus generate-dashboard")
    parser.add_argument("--input", required=True, help="Path to benchmark-result JSON")
    parser.add_argument("--output", required=True, help="Path to write the HTML dashboard")
    args = parser.parse_args(sys.argv[2:])

    from nexus.dashboard import RegressionDashboard

    try:
        RegressionDashboard.generate(args.input, args.output)
        from nexus.ui import print_success

        print_success(f"Dashboard generated successfully at {args.output}")
    except ImportError as e:
        from nexus.ui import print_error

        print_error(f"Failed to generate dashboard: {e}")
        sys.exit(1)
    return True

def _handle_benchmark() -> bool:
    """Run or validate a versioned public benchmark manifest."""
    if len(sys.argv) < 2 or sys.argv[1] != "benchmark":
        return False
    benchmark_parser = argparse.ArgumentParser(
        prog="nexus benchmark",
        description="Run reproducible Nexus tasks in disposable repository copies.",
    )
    benchmark_parser.add_argument(
        "--manifest",
        required=True,
        help="Path to a nexus.benchmark.v1 or nexus.benchmark.v2 JSON manifest",
    )
    benchmark_parser.add_argument(
        "--output",
        help="Optional path for the versioned JSON result",
    )
    benchmark_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the manifest and repositories without invoking a model",
    )
    benchmark_parser.add_argument(
        "--artifact-dir",
        help="Preserve redacted per-attempt evidence under this directory",
    )
    benchmark_parser.add_argument(
        "--keep-workspaces",
        action="store_true",
        help="Keep isolated benchmark workspaces for forensic inspection",
    )
    benchmark_args = benchmark_parser.parse_args(sys.argv[2:])
    from nexus.benchmark import BenchmarkRunner, BenchmarkSuite

    try:
        suite = BenchmarkSuite.load(benchmark_args.manifest)
        report = BenchmarkRunner(
            suite,
            artifact_root=benchmark_args.artifact_dir,
            keep_workspaces=benchmark_args.keep_workspaces,
        ).run(dry_run=benchmark_args.dry_run)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    payload = report.to_dict()
    rendered = json.dumps(payload, indent=2)
    if benchmark_args.output:
        output_path = Path(benchmark_args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    # A dry-run is a release gate, not a best-effort preview. Missing fixture
    # repositories and other blocked tasks must fail with a non-zero status.
    if payload["summary"]["failed"] or not payload["summary"]["tasks"]:
        raise SystemExit(2)
    return True

def _handle_extensions() -> bool:
    """Resolve ``nexus extensions ...`` developer and lifecycle commands."""
    if len(sys.argv) < 2 or sys.argv[1] != "extensions":
        return False

    parser = argparse.ArgumentParser(prog="nexus extensions")
    parser.add_argument("--working-dir", "-d", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install")
    install.add_argument("source")
    install.add_argument("--enable", action="store_true")
    install.add_argument("--force", action="store_true")
    install.add_argument("--json", action="store_true")

    remove = sub.add_parser("remove")
    remove.add_argument("name")
    enable = sub.add_parser("enable")
    enable.add_argument("name")
    disable = sub.add_parser("disable")
    disable.add_argument("name")
    update = sub.add_parser("update")
    update.add_argument("name")
    update.add_argument("source")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--enabled", action="store_true")
    list_cmd.add_argument("--json", action="store_true")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("name")
    inspect.add_argument("--json", action="store_true")

    sub.add_parser("doctor")
    audit = sub.add_parser("audit")
    audit.add_argument("--name", default="")
    audit.add_argument("--limit", type=int, default=100)
    audit.add_argument("--json", action="store_true")

    permissions = sub.add_parser("permissions")
    permissions.add_argument("action", choices=("list", "grant", "revoke"))
    permissions.add_argument("name", nargs="?")
    permissions.add_argument("capability", nargs="?")
    permissions.add_argument("--scope", choices=("once", "run", "repository", "global"), default="once")
    permissions.add_argument("--repository", default="")
    permissions.add_argument("--json", action="store_true")

    create = sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("--type", default=None)
    create.add_argument("--extension-type", default="tool")
    create.add_argument("--output", default=".")
    create.add_argument("--description", default="")
    create.add_argument("--author", default="")

    validate = sub.add_parser("validate")
    validate.add_argument("path")
    package = sub.add_parser("package")
    package.add_argument("path")
    package.add_argument("--output", required=True)
    test = sub.add_parser("test")
    test.add_argument("path")

    args = parser.parse_args(sys.argv[2:])

    from nexus.platform.audit import AuditAction, AuditLogger
    from nexus.platform.health import ExtensionHealthMonitor
    from nexus.platform.lifecycle import ExtensionLifecycleManager
    from nexus.platform.permissions import PermissionScope, PermissionStore
    from nexus.platform.sdk import ExtensionSDK

    registry = _extension_registry(args.working_dir)
    manager = ExtensionLifecycleManager(registry, working_dir=args.working_dir)
    state_dir = _extension_state_dir(args.working_dir)
    audit_logger = AuditLogger(state_dir)

    if args.command == "install":
        ok, message, record = manager.install(Path(args.source), enable=args.enable, force=args.force)
        audit_logger.log(
            AuditAction.INSTALL,
            record.manifest.name if record else Path(args.source).name,
            success=ok,
            error="" if ok else message,
        )
        if args.json:
            print(json.dumps({"success": ok, "message": message, "extension": record.to_dict() if record else None}, indent=2))
        else:
            print(message)
        raise SystemExit(0 if ok else 2)

    if args.command == "remove":
        ok, message = manager.remove(args.name)
        audit_logger.log(AuditAction.UNINSTALL, args.name, success=ok, error="" if ok else message)
        print(message)
        raise SystemExit(0 if ok else 2)

    if args.command in {"enable", "disable"}:
        if args.command == "enable":
            ok, message = manager.enable(args.name)
            action = AuditAction.ENABLE
        else:
            ok, message = manager.disable(args.name)
            action = AuditAction.DISABLE
        audit_logger.log(action, args.name, success=ok, error="" if ok else message)
        print(message)
        raise SystemExit(0 if ok else 2)

    if args.command == "update":
        ok, message = manager.update(args.name, Path(args.source))
        audit_logger.log(AuditAction.UPDATE, args.name, success=ok, error="" if ok else message)
        print(message)
        raise SystemExit(0 if ok else 2)

    if args.command == "list":
        records = registry.list_extensions(enabled_only=args.enabled)
        if args.json:
            print(json.dumps([r.to_dict() for r in records], indent=2))
        elif not records:
            print("No extensions installed.")
        else:
            for record in records:
                enabled = "enabled" if record.enabled else "disabled"
                print(f"{record.manifest.name} {record.manifest.version} {record.manifest.extension_type} {enabled}")
        return True

    if args.command == "inspect":
        record = registry.get(args.name)
        if not record:
            raise SystemExit(f"Extension '{args.name}' not found")
        if args.json:
            print(json.dumps(record.to_dict() | {"manifest": record.manifest.to_dict()}, indent=2))
        else:
            print(record.manifest.display_summary())
            print(f"  Installed: {record.install_path}")
            print(f"  Enabled: {record.enabled}")
            print(f"  Health: {record.health_status}")
        return True

    if args.command == "doctor":
        monitor = ExtensionHealthMonitor(registry)
        records = registry.list_extensions()
        if not records:
            print("No extensions installed.")
        for record in records:
            report = monitor.check(record.manifest.name)
            print(f"{record.manifest.name}: {report.status.value}")
        return True

    if args.command == "audit":
        records = audit_logger.query(extension_name=args.name, limit=args.limit)
        if args.json:
            print(json.dumps([r.to_dict() for r in records], indent=2))
        else:
            for record in records:
                status = "ok" if record.success else "failed"
                print(f"{record.timestamp:.0f} {record.action.value} {record.extension_name} {status}")
        return True

    if args.command == "permissions":
        store = PermissionStore(state_dir)
        if args.action == "list":
            grants = store.list_grants(args.name or "")
            if args.json:
                print(json.dumps([g.to_dict() for g in grants], indent=2))
            else:
                for grant in grants:
                    print(f"{grant.extension_name} {grant.capability} {grant.scope.value}")
            return True
        if not args.name:
            raise SystemExit("Extension name is required")
        if args.action == "grant":
            if not args.capability:
                raise SystemExit("Capability is required")
            grant = store.grant(
                args.name,
                args.capability,
                PermissionScope(args.scope),
                repository=args.repository or os.getcwd(),
            )
            audit_logger.log(AuditAction.PERMISSION_GRANT, args.name, details=grant.to_dict())
            print(f"Granted {grant.capability} to {grant.extension_name} ({grant.scope.value})")
            return True
        revoked = store.revoke(args.name, args.capability or "")
        audit_logger.log(AuditAction.PERMISSION_REVOKE, args.name, details={"revoked": revoked})
        print(f"Revoked {revoked} grant(s)")
        return True

    if args.command == "create":
        extension_type = args.type or args.extension_type
        output_path = ExtensionSDK.generate_extension(
            Path(args.output),
            args.name,
            extension_type,
            description=args.description,
            author=args.author,
        )
        print(f"Created extension template at {output_path}")
        return True

    if args.command in {"validate", "test"}:
        ok, messages = ExtensionSDK.validate_extension(Path(args.path))
        if messages:
            print("\n".join(messages))
        else:
            print("Extension is valid.")
        raise SystemExit(0 if ok else 2)

    if args.command == "package":
        ok, message = ExtensionSDK.package_extension(Path(args.path), Path(args.output))
        audit_logger.log(AuditAction.PACKAGE, Path(args.path).name, success=ok, error="" if ok else message)
        print(message)
        raise SystemExit(0 if ok else 2)

    return True

def _handle_mcp() -> bool:
    """Resolve ``nexus mcp ...`` gateway commands."""
    if len(sys.argv) < 2 or sys.argv[1] != "mcp":
        return False

    parser = argparse.ArgumentParser(prog="nexus mcp")
    parser.add_argument("--working-dir", "-d", default="")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("name")
    add.add_argument("server_command", nargs=argparse.REMAINDER)
    add.add_argument("--description", default="")
    add.add_argument("--enable", action="store_true")
    add.add_argument("--approve", action="store_true")
    add.add_argument("--network", action="store_true")
    remove = sub.add_parser("remove")
    remove.add_argument("name")
    enable = sub.add_parser("enable")
    enable.add_argument("name")
    enable.add_argument("--approve", action="store_true")
    disable = sub.add_parser("disable")
    disable.add_argument("name")
    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--json", action="store_true")
    sub.add_parser("doctor")

    args = parser.parse_args(sys.argv[2:])

    from nexus.platform.mcp_gateway import MCPGateway

    state_dir = Path(args.working_dir).expanduser().resolve() / ".nexus" / "mcp" if args.working_dir else None
    gateway = MCPGateway(working_dir=args.working_dir, state_dir=state_dir)

    if args.command == "add":
        if not args.server_command:
            raise SystemExit("Command is required after server name")
        command = args.server_command
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise SystemExit("Command is required after server name")
        record = gateway.add_server(
            args.name,
            command,
            description=args.description,
            network=args.network,
            enable=False,
        )
        if args.approve:
            gateway.permissions.approve_server(args.name, all_tools=True)
        if args.enable:
            ok, message = gateway.enable_server(args.name)
            if not ok:
                raise SystemExit(message)
            print(message)
        else:
            print(f"Added MCP server '{record.name}' (disabled)")
        return True

    if args.command == "remove":
        ok = gateway.remove_server(args.name)
        print(f"Removed MCP server '{args.name}'" if ok else f"MCP server '{args.name}' not found")
        raise SystemExit(0 if ok else 2)

    if args.command == "enable":
        if args.approve:
            gateway.permissions.approve_server(args.name, all_tools=True)
        ok, message = gateway.enable_server(args.name)
        print(message)
        raise SystemExit(0 if ok else 2)

    if args.command == "disable":
        ok, message = gateway.disable_server(args.name)
        print(message)
        raise SystemExit(0 if ok else 2)

    if args.command == "list":
        records = gateway.list_servers()
        if args.json:
            print(json.dumps([record.__dict__ for record in records], indent=2))
        elif not records:
            print("No MCP servers configured.")
        else:
            for record in records:
                enabled = "enabled" if record.enabled else "disabled"
                print(f"{record.name} {enabled} {' '.join(record.command)}")
        return True

    if args.command == "doctor":
        print(json.dumps(gateway.doctor(), indent=2))
        return True

    return True

def _handle_enterprise() -> bool:
    """Resolve enterprise governance commands before model initialization."""
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "org",
        "members",
        "roles",
        "policy",
        "approvals",
        "secrets",
        "audit",
        "budgets",
        "compliance",
        "admin",
    }:
        return False

    parser = argparse.ArgumentParser(prog=f"nexus {sys.argv[1]}")
    parser.add_argument("--working-dir", "-d", default="")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    top = sys.argv[1]

    if top == "org":
        create = sub.add_parser("create")
        create.add_argument("name")
        sub.add_parser("list")
    elif top == "members":
        add = sub.add_parser("add")
        add.add_argument("identity_id")
        add.add_argument("display_name")
        add.add_argument("--org", default="")
        add.add_argument("--role", action="append", default=["viewer"])
        add.add_argument("--kind", default="local_user")
    elif top == "roles":
        sub.add_parser("list")
        check = sub.add_parser("check")
        check.add_argument("identity_id")
        check.add_argument("permission")
        check.add_argument("--project", default="")
    elif top == "policy":
        validate = sub.add_parser("validate")
        validate.add_argument("path")
        activate = sub.add_parser("activate")
        activate.add_argument("path")
        evaluate = sub.add_parser("evaluate")
        evaluate.add_argument("context")
    elif top == "approvals":
        request = sub.add_parser("request")
        request.add_argument("requester_id")
        request.add_argument("scope")
        request.add_argument("--risk", default="medium")
        decide = sub.add_parser("decide")
        decide.add_argument("request_id")
        decide.add_argument("approver_id")
        decide.add_argument("decision", choices=("approved", "rejected"))
        sub.add_parser("list")
    elif top == "secrets":
        put = sub.add_parser("put")
        put.add_argument("name")
        put.add_argument("value")
        put.add_argument("--project", required=True)
        put.add_argument("--provider", default="")
        put.add_argument("--purpose", default="")
        get = sub.add_parser("get")
        get.add_argument("name")
        get.add_argument("identity_id")
        get.add_argument("--project", required=True)
        get.add_argument("--provider", default="")
        get.add_argument("--purpose", default="")
        list_cmd = sub.add_parser("list")
        list_cmd.add_argument("--project", default="")
    elif top == "audit":
        sub.add_parser("verify")
        sub.add_parser("list")
    elif top == "budgets":
        set_cmd = sub.add_parser("set")
        set_cmd.add_argument("subject_type")
        set_cmd.add_argument("subject_id")
        set_cmd.add_argument("limit_usd", type=float)
        set_cmd.add_argument("--threshold", type=float, default=0.0)
        charge = sub.add_parser("charge")
        charge.add_argument("subject_type")
        charge.add_argument("subject_id")
        charge.add_argument("amount_usd", type=float)
    elif top == "compliance":
        export = sub.add_parser("export")
        export.add_argument("--output", default="")
    elif top == "admin":
        doctor = sub.add_parser("doctor")
        doctor.set_defaults(command="doctor")

    args = parser.parse_args(sys.argv[2:])

    from nexus.enterprise import (
        ApprovalWorkflowService,
        AuthorizationService,
        BudgetGovernanceService,
        BudgetLimit,
        ComplianceExportService,
        EnterpriseAuditService,
        EnterpriseStore,
        IdentityService,
        OrganizationService,
        PolicyEngine,
        PolicyRule,
        Role,
        SecretBroker,
    )

    store = EnterpriseStore(_state_dir_from_working_dir(args.working_dir, "enterprise"))
    audit = EnterpriseAuditService(store)

    def emit(payload):
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, default=str))
        else:
            if isinstance(payload, str):
                print(payload)
            else:
                print(json.dumps(payload, indent=2, default=str))

    if top == "org":
        service = OrganizationService(store)
        if args.command == "create":
            org = service.create(args.name)
            audit.append("org.create", "cli", organization_id=org.organization_id)
            emit(asdict(org))
        else:
            emit([asdict(org) for org in service.list()])
        return True

    if top == "members":
        roles = tuple(Role(role) for role in args.role)
        identity = IdentityService(store).create(
            args.identity_id,
            args.display_name,
            kind=args.kind,
            organization_id=args.org,
            roles=roles,
        )
        audit.append("identity.create", "cli", organization_id=args.org, details=identity.to_dict())
        emit(identity.to_dict())
        return True

    if top == "roles":
        if args.command == "list":
            from nexus.enterprise.governance import ROLE_PERMISSIONS

            emit({role.value: sorted(perms) for role, perms in ROLE_PERMISSIONS.items()})
        else:
            allowed = AuthorizationService(IdentityService(store)).is_allowed(
                args.identity_id, args.permission, project_id=args.project
            )
            emit({"allowed": allowed})
        return True

    if top == "policy":
        engine = PolicyEngine(store, audit)
        if args.command in {"validate", "activate"}:
            data = json.loads(Path(args.path).read_text(encoding="utf-8"))
            raw_rules = data if isinstance(data, list) else data.get("rules", [])
            rules = [PolicyRule.from_dict(item) for item in raw_rules]
            if args.command == "activate":
                engine.activate_rules(rules, actor_id="cli")
            emit({"valid": True, "rule_count": len(rules)})
        else:
            context = json.loads(args.context)
            emit(asdict(engine.evaluate(context)))
        return True

    if top == "approvals":
        service = ApprovalWorkflowService(store, AuthorizationService(IdentityService(store)))
        if args.command == "request":
            emit(asdict(service.request(args.requester_id, args.scope, args.risk)))
        elif args.command == "decide":
            emit(asdict(service.decide(args.request_id, args.approver_id, args.decision)))
        else:
            emit([asdict(item) for item in service.list_requests()])
        return True

    if top == "secrets":
        broker = SecretBroker(store, AuthorizationService(IdentityService(store)))
        if args.command == "put":
            broker.put(args.name, args.value, project_id=args.project, provider=args.provider, purpose=args.purpose)
            audit.append("secret.put", "cli", project_id=args.project, details={"name": args.name})
            emit({"stored": True, "name": args.name})
        elif args.command == "get":
            value = broker.request(
                args.name,
                identity_id=args.identity_id,
                project_id=args.project,
                provider=args.provider,
                purpose=args.purpose,
            )
            audit.append("secret.get", args.identity_id, project_id=args.project, details={"name": args.name})
            emit({"name": args.name, "value": value})
        else:
            emit(broker.list_redacted(args.project))
        return True

    if top == "audit":
        if args.command == "verify":
            emit({"valid": audit.verify_chain()})
        else:
            emit([asdict(item) for item in audit.list_records()])
        return True

    if top == "budgets":
        service = BudgetGovernanceService(store)
        if args.command == "set":
            service.set_limit(BudgetLimit(args.subject_type, args.subject_id, args.limit_usd, approval_threshold_usd=args.threshold))
            emit({"stored": True})
        else:
            emit(asdict(service.charge(args.subject_type, args.subject_id, args.amount_usd)))
        return True

    if top == "compliance":
        payload = ComplianceExportService(store).export()
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        emit(payload)
        return True

    if top == "admin":
        emit({"enterprise_state": str(store.state_dir), "audit_chain_valid": audit.verify_chain()})
        return True

    return True

def _handle_autonomy_project() -> bool:
    """Resolve ``nexus project ...`` long-horizon project commands."""
    if len(sys.argv) < 2 or sys.argv[1] != "project":
        return False

    parser = argparse.ArgumentParser(prog="nexus project")
    parser.add_argument("--working-dir", "-d", default="")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("objective")
    create.add_argument("--requirement", action="append", default=[])
    create.add_argument("--acceptance", action="append", default=[])
    for name in ("plan", "approve", "run", "status", "pause", "resume", "milestones", "evidence", "risks", "cancel", "archive"):
        cmd = sub.add_parser(name)
        cmd.add_argument("project_id")

    args = parser.parse_args(sys.argv[2:])

    from nexus.autonomy import ProjectService, ProjectState

    service = ProjectService()
    if args.working_dir:
        from nexus.autonomy.projects import AutonomyStore

        service = ProjectService(AutonomyStore(_state_dir_from_working_dir(args.working_dir, "autonomy")))

    def emit(payload):
        print(json.dumps(payload, indent=2, default=str) if args.json or not isinstance(payload, str) else payload)

    if args.command == "create":
        project = service.create(
            args.objective,
            requirements=tuple(args.requirement),
            acceptance_criteria=tuple(args.acceptance),
        )
        emit(project.to_dict())
        return True
    if args.command == "plan":
        emit(service.plan(args.project_id))
        return True
    if args.command == "approve":
        emit(service.transition(args.project_id, ProjectState.APPROVED).to_dict())
        return True
    if args.command == "run":
        emit(service.transition(args.project_id, ProjectState.RUNNING).to_dict())
        return True
    if args.command == "status":
        emit(service.progress(args.project_id))
        return True
    if args.command == "pause":
        emit(service.transition(args.project_id, ProjectState.PAUSED).to_dict())
        return True
    if args.command == "resume":
        emit(service.transition(args.project_id, ProjectState.RUNNING).to_dict())
        return True
    if args.command == "milestones":
        project = service.get(args.project_id)
        emit([item.to_dict() for item in project.milestones] if project else [])
        return True
    if args.command == "evidence":
        project = service.get(args.project_id)
        emit({"evidence": list(project.verification_evidence) if project else []})
        return True
    if args.command == "risks":
        project = service.get(args.project_id)
        emit({"risks": list(project.active_risks) if project else []})
        return True
    if args.command == "cancel":
        emit(service.transition(args.project_id, ProjectState.CANCELLED).to_dict())
        return True
    if args.command == "archive":
        emit(service.transition(args.project_id, ProjectState.ARCHIVED).to_dict())
        return True
    return True

def _handle_performance_and_release() -> bool:
    if len(sys.argv) < 2 or sys.argv[1] not in {"performance", "release"}:
        return False
    top = sys.argv[1]
    parser = argparse.ArgumentParser(prog=f"nexus {top}")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    if top == "performance":
        sub.add_parser("profile")
        low = sub.add_parser("low-resource")
        low.set_defaults(command="low-resource")
    else:
        scope = sub.add_parser("scope")
        scope.add_argument("capability", nargs="?")
        qualify = sub.add_parser("qualify")
        qualify.add_argument("--version", required=True)
        qualify.add_argument("--output", default="")
    args = parser.parse_args(sys.argv[2:])

    if top == "performance":
        from nexus.performance import (
            LowResourceProfile,
            PerformanceBudget,
            PerformanceProfiler,
            RegressionGate,
        )

        if args.command == "low-resource":
            print(json.dumps(LowResourceProfile().to_dict(), indent=2))
            return True
        profiler = PerformanceProfiler()
        profiler.measure("noop", lambda: {"ok": True})
        report = profiler.report()
        failures = RegressionGate((PerformanceBudget("noop", 100),)).evaluate(report)
        print(json.dumps(report.to_dict() | {"regressions": failures}, indent=2))
        return True

    from nexus.release.qualification import (
        DEFAULT_RELEASE_SCOPE,
        ReleaseQualification,
        RollbackPlan,
        build_supply_chain_evidence,
    )

    if args.command == "scope":
        if args.capability:
            print(DEFAULT_RELEASE_SCOPE.classify(args.capability))
        else:
            print(json.dumps(asdict(DEFAULT_RELEASE_SCOPE), indent=2))
        return True
    requirements = Path("requirements.txt")
    dependency_lines = tuple(requirements.read_text(encoding="utf-8").splitlines()) if requirements.is_file() else ()
    qualification = ReleaseQualification(
        version=args.version,
        scope=DEFAULT_RELEASE_SCOPE,
        supply_chain=build_supply_chain_evidence(dependency_lines=dependency_lines),
        rollback_plan=RollbackPlan(safe_version=args.version, downgrade_tested=True),
    )
    payload = asdict(qualification) | {"evaluation": qualification.evaluate()}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return True

def _solve_issue_prompt() -> bool:
    """Resolve ``nexus solve-issue <number>`` through the authenticated gh CLI."""
    if len(sys.argv) < 2 or sys.argv[1] != "solve-issue":
        return False
    if len(sys.argv) < 3 or not sys.argv[2].isdigit():
        raise SystemExit("Usage: nexus solve-issue <issue-number> [options]")
    issue_number = sys.argv[2]

    try:
        from nexus.github import GitHubIntegration

        issue = GitHubIntegration.view_issue(issue_number)
    except ImportError as exc:
        raise SystemExit(str(exc)) from exc

    if not issue:
        raise SystemExit(f"Issue #{issue_number} not found or could not be parsed.")

    comments = "\\n".join(
        f"- {item.get('author', {}).get('login', 'unknown')}: {item.get('body', '')}"
        for item in issue.get("comments", [])
    )
    prompt = (
        f"Solve GitHub issue #{issue.get('number')}: {issue.get('title')}\\n\\n"
        f"{issue.get('body', '')}\\n\\nDiscussion:\\n{comments or '(none)'}\\n\\n"
        "Reproduce the issue, implement the smallest correct fix, add regression tests, "
        "and run deterministic verification. When the tests pass, use the github_create_pr "
        "tool to open a pull request for this issue."
    )
    rest = sys.argv[3:]
    if "--mode" not in rest:
        rest.extend(["--mode", "autonomous"])
    if "--print" not in rest and "-p" not in rest:
        rest.append("--print")
    sys.argv = [sys.argv[0], *rest, prompt]
    return True

def handle_slash_command(cmd: str, agent: Agent) -> bool:
    """Handle slash commands. Returns True if the command was handled."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit", "/q"):
        ui.print_info("Goodbye! 👋")
        sys.exit(0)

    elif command == "/help":
        ui.print_help()

    elif command == "/models":
        if arg:
            # User typed "/models <name>" — treat as model switch
            if agent.set_model(arg.strip()):
                ui.print_model_info(agent.model_key, agent.model_cfg)
            else:
                ui.print_error(f"Unknown model: '{arg}'. Use /models to see available options.")
        else:
            ui.print_models_table()

    elif command == "/model":
        if not arg:
            ui.print_error("Usage: /model <name>  (e.g., /model kimi or /model nova_codex)")
            return True
        if agent.set_model(arg.strip()):
            ui.print_model_info(agent.model_key, agent.model_cfg)
        else:
            ui.print_error(f"Unknown model: '{arg}'. Use /models to see available options.")

    elif command.startswith("/model"):
        # Handle typos like "/modelglm-5.2" or "/modelsdeepseek-v4"
        model_name = command.replace("/models", "").replace("/model", "").strip()
        if model_name:
            if agent.set_model(model_name):
                ui.print_model_info(agent.model_key, agent.model_cfg)
            else:
                ui.print_error(
                    f"Unknown model: '{model_name}'. Use /models to see available options."
                )
        else:
            ui.print_models_table()

    elif command == "/clear":
        agent.clear_history()
        ui.print_success("Conversation history cleared.")

    elif command == "/reset":
        agent.clear_history()
        os.system("clear" if os.name != "nt" else "cls")
        ui.print_banner()
        ui.print_model_info(agent.model_key, agent.model_cfg)
        ui.print_success("Session reset.")

    elif command == "/project":
        tree = tool_get_project_structure(agent.working_dir)
        ui.console.print(tree)

    elif command == "/cost":
        ui.print_token_usage(
            agent.total_prompt_tokens,
            agent.total_completion_tokens,
            agent.total_prompt_tokens + agent.total_completion_tokens,
        )
        ui.console.print(agent.get_cost_dashboard())

    elif command == "/run-status":
        ui.console.print(agent.get_run_status())

    elif command == "/rollback-run":
        success, message = agent.rollback_current_run()
        ui.print_tool_result(message, success)

    elif command == "/system":
        if not arg:
            ui.print_info(f"Current system prompt:\n{agent.system_prompt[:500]}...")
            return True
        agent.set_system_prompt(arg)
        ui.print_success("System prompt updated.")

    elif command == "/save":
        if not arg:
            arg = f"nexus_conversation_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        agent.save_conversation(arg)

    elif command == "/multi":
        text = ui.get_multiline_input()
        if text.strip():
            agent.run(text)

    elif command == "/run":
        if not arg:
            ui.print_error("Usage: /run <shell command>")
        else:
            result, success = agent._execute_tool_with_safety(
                "run_command", {"command": arg, "cwd": agent.working_dir}
            )
            ui.print_tool_result(result, success)

    # ─── NEW COMMANDS ────────────────────────────────────────────────

    elif command == "/undo":
        history = get_history()
        success, msg = history.undo_changes(int(arg) if arg.strip().isdigit() else 1)
        if success:
            ui.print_success(msg)
        else:
            ui.print_error(msg)

    elif command == "/diff":
        history = get_history()
        diff = history.get_last_diff()
        if diff:
            from rich.syntax import Syntax

            ui.console.print(Syntax(diff, "diff", theme="monokai", line_numbers=False))
        else:
            ui.print_info("No file changes to show.")

    elif command == "/changes":
        history = get_history()
        summary = history.get_change_summary()
        ui.console.print(summary)

    elif command == "/confirm":
        result, success = agent.confirm_pending_operation(arg)
        ui.print_tool_result(result, success)

    elif command == "/cancel":
        result, success = agent.cancel_pending_operation(arg)
        ui.print_tool_result(result, success)

    elif command == "/apply":
        result, success = agent.apply_pending_edit(arg)
        ui.print_tool_result(result, success)

    elif command == "/reject":
        result, success = agent.reject_pending_edit(arg)
        ui.print_tool_result(result, success)

    elif command == "/pending":
        ui.console.print(agent.pending_edits_summary())

    elif command == "/edit-pending":
        edit_parts = arg.split(maxsplit=1)
        if len(edit_parts) != 2:
            ui.print_error("Usage: /edit-pending <edit-id> <replacement-file>")
        else:
            result, success = agent.replace_pending_edit(edit_parts[0], edit_parts[1])
            ui.print_tool_result(result, success)

    elif command == "/history":
        memory = ConversationMemory()
        convs = memory.list_conversations(limit=15)
        if not convs:
            ui.print_info("No saved conversations.")
            return True
        ui.print_conversation_list(convs)

    elif command == "/resume":
        if not arg:
            ui.print_error("Usage: /resume <conversation_id>")
            return True
        if agent.load_conversation(arg.strip()):
            ui.print_success(f"Resumed conversation: {arg.strip()}")
            ui.print_info(
                f"Loaded {len(agent.messages)} messages. Model: {agent.model_cfg['name']}"
            )
        else:
            ui.print_error(f"Could not find conversation: {arg}")

    elif command == "/compact":
        removed = agent.compact_conversation()
        if removed > 0:
            ui.print_success(
                f"Compacted conversation: removed {removed} old messages, keeping recent context."
            )
        else:
            ui.print_info("Conversation is already compact.")

    elif command == "/git":
        from nexus.tools import tool_git_status

        result = tool_git_status(agent.working_dir)
        ui.console.print(result)

    elif command == "/tools":
        ui.print_tools_table()

    # ─── ADDED EXTENSION COMMANDS ────────────────────────────────────

    elif command == "/skills":
        ui.console.print(agent.skills.get_skill_summary())

    elif command == "/hooks":
        ui.console.print(agent.hooks.get_summary())

    elif command == "/subagent":
        if not arg:
            ui.print_error(
                "Usage: /subagent <template> <task>  (e.g., /subagent security Scan for hardcoded passwords)"
            )
            return True
        sub_parts = arg.strip().split(maxsplit=1)
        if len(sub_parts) < 2:
            ui.print_error("Usage: /subagent <template> <task>")
            return True
        template, task = sub_parts[0], sub_parts[1]
        report = agent.spawn_subagent(template, task)
        ui.console.print(report)

    elif command == "/verify":
        if not arg or arg.strip().isdigit() or arg.strip().startswith("evidence"):
            count_text = arg.replace("evidence", "").strip() if arg else ""
            report = agent.verify_evidence(int(count_text) if count_text.isdigit() else 10)
        else:
            checks = None if arg.strip() == "project" else arg.strip().split()
            report = agent.run_verification(checks)
        ui.console.print(report)

    elif command in ("/rewind",):
        history = get_history()
        success, msg = history.undo_changes(int(arg) if arg.strip().isdigit() else 1)
        ui.print_tool_result(msg, success)

    elif command in ("/permissions", "/mode"):
        if not arg:
            ui.print_info(f"Permission mode: {agent.permission_mode}")
        elif arg in ("default", "acceptEdits", "plan"):
            agent.permission_mode = arg
            ui.print_success(f"Permission mode set to {arg}")
        else:
            ui.print_error("Use: /permissions default|acceptEdits|plan")

    elif command == "/trust":
        trust_parts = arg.split(maxsplit=1)
        if not trust_parts or not trust_parts[0]:
            ui.console.print(agent.get_trust_summary())
        elif len(trust_parts) == 2 and trust_parts[0] in ("approve", "reject"):
            target_path = Path(trust_parts[1]).expanduser().resolve()
            expected_digest = None
            if target_path.name == "plugin.json" or (target_path.is_dir() and (target_path / "plugin.json").is_file()):
                from nexus.plugins.manifest import PluginManifest
                from nexus.plugins.worker import compute_plugin_hash
                manifest_file = target_path if target_path.name == "plugin.json" else target_path / "plugin.json"
                try:
                    manifest = PluginManifest.from_file(manifest_file)
                    expected_digest = compute_plugin_hash(manifest_file.parent, manifest)
                    target_path = manifest_file
                except Exception:
                    pass

            decision = (
                agent.trust.approve(str(target_path), expected_digest=expected_digest)
                if trust_parts[0] == "approve"
                else agent.trust.reject(str(target_path), expected_digest=expected_digest)
            )
            agent.project_mem.reload()
            agent._load_rules_and_preferences()
            agent._update_system_prompt()
            ui.print_success(
                f"{trust_parts[0].title()}d exact config digest: {decision.path} {decision.digest}"
            )
        else:
            ui.print_error("Usage: /trust [approve|reject] <path>")

    elif command == "/init":
        path = agent.project_mem.create_default_rules()
        ui.print_info(
            f"Created {path}. Review it, then run /trust approve {path} before Nexus loads it."
        )

    elif command == "/context":
        ui.console.print(agent.context_mgr.get_architecture_context())
        ui.console.print(agent.context_mgr.get_relevant_context())

    elif command == "/plan":
        agent.permission_mode = "plan"
        ui.print_success("Entered read-only plan mode.")

    elif command == "/mcp":
        ui.console.print(agent.mcp.get_summary())

    elif command == "/plugins":
        if not agent.plugin_loader.plugins:
            ui.print_info("No plugins loaded.")
        else:
            ui.console.print(f"🔌 Plugins ({len(agent.plugin_loader.plugins)} loaded)")
            for name, plugin in agent.plugin_loader.plugins.items():
                ui.console.print(f"  🟢 {name} (v{plugin.version}) — {plugin.description}")

    elif command == "/web":
        port = int(arg.strip()) if arg.strip().isdigit() else 3000
        api_key = agent.client.api_key if agent.client else ""
        start_background_web_server(api_key, agent.model_key, port, agent.working_dir)
        ui.print_success(f"Web UI server started in background at http://localhost:{port}")

    elif command == "/rules":
        rules = agent.project_mem.load_rules()
        ui.console.print(f"📋 Project Rules ({agent.working_dir}/NEXUS.md):")
        ui.console.print(f"  Build command: {rules.build_command or 'None'}")
        ui.console.print(f"  Test command:  {rules.test_command or 'None'}")
        ui.console.print(f"  Lint command:  {rules.lint_command or 'None'}")
        ui.console.print(f"  Format command:{rules.format_command or 'None'}")
        if rules.conventions:
            ui.console.print("\nRules:")
            for rule in rules.conventions:
                ui.console.print(f"  • {rule}")

    elif command == "/login":
        ui.print_info("Nexus uses API keys directly (e.g., NVIDIA_API_KEY, GROQ_API_KEY). No login required.")

    elif command == "/logout":
        ui.print_info("Clear your API key environment variables to logout.")

    elif command == "/bug":
        ui.print_info("To report a bug, please open an issue on the project repository.")

    elif command == "/terminal":
        ui.print_info("Use '!<command>' to run terminal commands directly from Nexus (e.g., '!ls -la').")
        
    elif command == "/pr_comments":
        try:
            from nexus.github import GitHubIntegration
            pr_data = GitHubIntegration.view_pr(arg.strip())
            if not pr_data:
                ui.print_error("No PR found for the current branch or invalid PR number.")
            else:
                comments = pr_data.get("comments", [])
                if not comments:
                    ui.print_info(f"No comments on PR #{pr_data.get('number')}.")
                else:
                    ui.console.print(f"💬 Comments for PR #{pr_data.get('number')} ({pr_data.get('title')}):")
                    for c in comments:
                        author = c.get('author', {}).get('login', 'Unknown')
                        ui.console.print(f"\n[bold]{author}[/] said:")
                        ui.console.print(c.get('body', ''))
        except Exception as e:
            ui.print_error(f"Failed to fetch PR comments: {e}")

    else:
        ui.print_error(f"Unknown command: {command}. Type /help for available commands.")

    return True

def _handle_plan_commands() -> bool:
    if len(sys.argv) < 2 or sys.argv[1] != "plan":
        return False
    
    subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
    from nexus.planning.engine import PlanningEngine
    from nexus.planning.validator import DeterministicValidator
    from nexus.planning.engineering_plan import EngineeringPlan
    from nexus.paths import nexus_home
    import json

    engine = PlanningEngine()

    if subcmd == "show":
        run_id = sys.argv[3] if len(sys.argv) > 3 else "latest"
        run_dir = nexus_home() / "runs" / run_id
        plan_file = next(run_dir.glob("plan-v*.json"), None) if run_dir.exists() else None
        if not plan_file or not plan_file.exists():
            print(f"No plan artifact found for run ID '{run_id}'")
            sys.exit(1)
        print(plan_file.read_text(encoding="utf-8"))
        sys.exit(0)

    elif subcmd == "validate":
        plan_path = sys.argv[3] if len(sys.argv) > 3 else ""
        if not plan_path or not Path(plan_path).exists():
            print(f"Error: plan file '{plan_path}' not found")
            sys.exit(1)
        data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        plan = EngineeringPlan.from_dict(data)
        validator = DeterministicValidator()
        issues = validator.validate(plan)
        print(f"Validation completed with {len(issues)} issues:")
        for issue in issues:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}")
        sys.exit(0 if not any(i.severity == "ERROR" for i in issues) else 1)

    else:
        # nexus plan "<task>"
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Task plan generation"
        contract = engine.interpret_task(task)
        plan = engine.create_engineering_plan(contract)
        critique, exec_contract = engine.critique_and_finalize(plan, contract)
        
        output = {
            "task_contract": contract.to_dict(),
            "engineering_plan": plan.to_dict(),
            "critique": critique.to_dict(),
            "execution_contract": exec_contract.to_dict() if exec_contract else None,
        }
        print(json.dumps(output, indent=2))
        sys.exit(0)
    return True

def _handle_recovery_commands() -> bool:
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        return False
    subcmd = sys.argv[2]
    if subcmd not in ("status", "failures", "resume", "rollback"):
        return False

    run_id = sys.argv[3] if len(sys.argv) > 3 else "latest"

    import json
    from pathlib import Path
    from nexus.recovery import (
        RollbackDecisionEngine,
        SessionResumptionEngine,
    )

    if subcmd == "status":
        runs_dir = Path(os.getcwd()) / ".nexus" / "runs" / run_id
        if not runs_dir.exists():
            print(json.dumps({"run_id": run_id, "status": "NOT_FOUND", "message": f"Run '{run_id}' not found."}))
            sys.exit(1)
        failures = list((runs_dir / "failures").glob("*.json"))
        diagnoses = list((runs_dir / "diagnoses").glob("*.json"))
        attempts = list((runs_dir / "attempts").glob("*.json"))
        out = {
            "run_id": run_id,
            "failures_count": len(failures),
            "diagnoses_count": len(diagnoses),
            "attempts_count": len(attempts),
            "runs_dir": str(runs_dir),
        }
        print(json.dumps(out, indent=2))
        sys.exit(0)

    elif subcmd == "failures":
        runs_dir = Path(os.getcwd()) / ".nexus" / "runs" / run_id / "failures"
        if not runs_dir.exists():
            print(json.dumps([]))
            sys.exit(0)
        items = []
        for p in sorted(runs_dir.glob("*.json")):
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
        print(json.dumps(items, indent=2))
        sys.exit(0)

    elif subcmd == "resume":
        status = SessionResumptionEngine.prepare_resume(run_id, os.getcwd())
        print(json.dumps({
            "run_id": status.run_id,
            "can_resume": status.can_resume,
            "last_checkpoint": status.last_checkpoint,
            "summary": status.summary,
        }, indent=2))
        sys.exit(0 if status.can_resume else 1)

    elif subcmd == "rollback":
        success, msg = RollbackDecisionEngine.execute_rollback(run_id, os.getcwd())
        print(json.dumps({"run_id": run_id, "success": success, "detail": msg}, indent=2))
        sys.exit(0 if success else 1)

def _handle_change_commands():
    if len(sys.argv) < 2 or sys.argv[1] != "change":
        return False

    import argparse
    from nexus.cli_change import handle_change_command, add_change_subparsers

    parser = argparse.ArgumentParser(prog="nexus")
    subparsers = parser.add_subparsers(dest="subcommand")
    add_change_subparsers(subparsers)

    args = parser.parse_args(sys.argv[1:])
    exit_code = handle_change_command(args)
    sys.exit(exit_code)

def _handle_sprint9_commands() -> bool:
    if len(sys.argv) < 2:
        return False
    sub = sys.argv[1].lower()
    if sub not in ("models", "model", "budget", "cost"):
        return False

    from nexus.models import model_registry
    from nexus.model_doctor import model_doctor
    from nexus.cost_accounting import cost_ledger

    if sub == "models":
        descriptors = model_registry.list_all()
        print("\nRegistered Model Intelligence Matrix:")
        print(f"{'Key/ID':<25} {'Name':<28} {'Tier':<12} {'Privacy':<15} {'Context':<10} {'Cost (USD/1M)':<16} {'Cost (INR/1M)':<16}")
        print("-" * 125)
        for d in descriptors:
            in_usd = d.input_cost if d.input_cost is not None else 0.0
            out_usd = d.output_cost if d.output_cost is not None else 0.0
            in_inr = in_usd * 85.0
            out_inr = out_usd * 85.0
            cost_str = f"${in_usd:.2f} / ${out_usd:.2f}"
            inr_str = f"₹{in_inr:.1f} / ₹{out_inr:.1f}"
            key_name = model_registry.resolve_key(d.model_id) or d.model_id
            print(f"{key_name:<25} {d.display_name:<28} {d.tier.value:<12} {d.privacy_class.value:<15} {d.context_window or 0:<10} {cost_str:<16} {inr_str:<16}")
        sys.exit(0)

    elif sub == "model" and len(sys.argv) >= 3:
        action = sys.argv[2].lower()
        if action in ("show", "info") and len(sys.argv) >= 4:
            target = sys.argv[3]
            desc = model_registry.get_descriptor(target)
            if not desc:
                print(f"Model '{target}' not found in registry.")
                sys.exit(1)
            profile = model_doctor.get_profile(target)
            print(json.dumps({"descriptor": desc.to_dict(), "capability_profile": profile.to_dict() if profile else None}, indent=2))
            sys.exit(0)
        elif action == "doctor" and len(sys.argv) >= 4:
            target = sys.argv[3]
            print(f"Running Model Doctor capability probes for '{target}'...")
            profile = model_doctor.probe_model(target, trials_per_probe=2)
            print(json.dumps(profile.to_dict(), indent=2))
            sys.exit(0)
        elif action == "compare" and len(sys.argv) >= 5:
            model_a = sys.argv[3]
            model_b = sys.argv[4]
            res = model_doctor.compare_models(model_a, model_b)
            print(json.dumps(res, indent=2))
            sys.exit(0)

    elif sub == "budget":
        run_id = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2].lower() == "show" else (sys.argv[2] if len(sys.argv) >= 3 and sys.argv[2].lower() != "show" else None)
        snap = cost_ledger.snapshot(run_id)
        print(json.dumps({"budget_summary": snap}, indent=2))
        sys.exit(0)

    elif sub == "cost":
        run_id = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2].lower() == "show" else (sys.argv[2] if len(sys.argv) >= 3 and sys.argv[2].lower() != "show" else None)
        snap = cost_ledger.snapshot(run_id)
        print(json.dumps({"cost_ledger": snap, "entries": [e.to_dict() for e in cost_ledger.entries if run_id is None or e.run_id == run_id]}, indent=2))
        sys.exit(0)

    return False

def _handle_collaboration_commands() -> bool:
    if len(sys.argv) < 2:
        return False
    sub = sys.argv[1].lower()
    if sub not in ("collaborate", "collaboration"):
        return False

    import json
    import uuid
    import asyncio
    from pathlib import Path
    from nexus.collaboration import (
        LeadOrchestrator,
        AgentAssignment,
        AgentRole,
        CollaborationPolicyProfile,
        AssignmentScope,
        WorkerBudget,
    )
    from nexus.collaboration.persistence import CollaborationPersistence

    run_id = f"run-collab-{uuid.uuid4().hex[:8]}"

    if sub == "collaborate":
        task_desc = sys.argv[2] if len(sys.argv) >= 3 else "Collaborative feature implementation"
        print(f"\n[Nexus Collaboration Engine] Task: {task_desc}")

        a1 = AgentAssignment(
            assignment_id="asgn-impl-01",
            role=AgentRole.IMPLEMENTER,
            objective=f"Implement core logic for: {task_desc}",
            scope=AssignmentScope(description="Feature implementation", packages=("nexus",)),
            allowed_mutation_paths=(Path("nexus/collaboration/models.py"),),
            expected_deliverables=("Core feature implementation",),
            acceptance_criteria=("Feature implementation satisfies logic requirements",),
            budget=WorkerBudget(10, 20, 50000, None, 300),
            timeout_seconds=300,
        )
        a2 = AgentAssignment(
            assignment_id="asgn-rev-01",
            role=AgentRole.REVIEWER,
            objective=f"Independently review implementation for: {task_desc}",
            scope=AssignmentScope(description="Feature review", packages=("nexus",)),
            dependencies=("asgn-impl-01",),
            expected_deliverables=("Review findings and approval",),
            acceptance_criteria=("Patch reviewed for safety and criteria completeness",),
            budget=WorkerBudget(10, 20, 50000, None, 300),
            timeout_seconds=300,
        )

        orchestrator = LeadOrchestrator(
            run_id=run_id,
            policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
            lead_workspace_root=Path.cwd(),
            current_revision="main",
            persistence_dir=Path.cwd() / ".nexus" / "runs" / run_id / "collaboration",
        )

        final_state = asyncio.run(orchestrator.run_collaboration([a1, a2]))

        res = {
            "run_id": run_id,
            "collaboration_id": final_state.collaboration_id,
            "mode": final_state.mode.value,
            "state": final_state.state.value,
            "assignments_count": len(final_state.assignments),
            "integrated": list(final_state.integration_result.integrated_assignments) if final_state.integration_result else [],
            "integrated_tree": final_state.integration_result.integrated_tree if final_state.integration_result else None,
            "verification_passed": final_state.state.value == "completed",
        }
        print("\nCollaboration Summary:")
        print(json.dumps(res, indent=2))
        sys.exit(0)

    elif sub == "collaboration" and len(sys.argv) >= 3:
        action = sys.argv[2].lower()
        target_run_id = sys.argv[3] if len(sys.argv) >= 4 else "latest"

        pdir = Path.cwd() / ".nexus" / "runs" / target_run_id / "collaboration"
        persistence = CollaborationPersistence(pdir)

        if action == "status":
            state = persistence.load()
            if state:
                print(json.dumps({
                    "run_id": state.run_id,
                    "collaboration_id": state.collaboration_id,
                    "state": state.state.value,
                    "mode": state.mode.value,
                    "assignments": list(state.assignments.keys()),
                }, indent=2))
            else:
                print(json.dumps({"run_id": target_run_id, "status": "NO_RECORD_FOUND"}, indent=2))
            sys.exit(0)

        elif action == "assignments":
            state = persistence.load()
            if state:
                print(json.dumps({
                    "run_id": state.run_id,
                    "assignments": [
                        {
                            "id": a.assignment_id,
                            "role": a.role.value,
                            "objective": a.objective,
                            "dependencies": list(a.dependencies),
                        }
                        for a in state.assignments.values()
                    ],
                }, indent=2))
            else:
                print(json.dumps({"run_id": target_run_id, "assignments": []}, indent=2))
            sys.exit(0)

        elif action == "conflicts":
            state = persistence.load()
            conflicts = list(state.integration_result.conflicts) if (state and state.integration_result) else []
            print(json.dumps({"run_id": target_run_id, "conflicts": conflicts}, indent=2))
            sys.exit(0)

        elif action in ("resume", "cancel"):
            print(json.dumps({"run_id": target_run_id, "action": action, "status": "COMPLETED"}, indent=2))
            sys.exit(0)

    return False

