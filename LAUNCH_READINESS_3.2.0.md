# Nexus CLI 3.2.0 Launch Readiness

## Release status

Nexus 3.2.0 is an integration-ready launch candidate for a public beta focused on
verified, reviewable repository engineering. It is not evidence for claiming
unattended Shopify-scale product generation or model-level parity with Claude Code.
Those claims are gated by the live long-horizon release qualification workflow.

## Closed launch blockers

- Workspace-read confinement is enforced through an immutable active RunContext.
- Default command and package `ASK` decisions cannot be bypassed by omitting a
  repository policy file.
- macOS no longer receives global file-read permission; command-capable release
  modes require a verified native sandbox.
- Absolute host paths, home expansion, traversal, symlink escape, interpreter
  literals, SSH/cloud credential targets, and unsafe shell paths are blocked before
  a subprocess is spawned.
- Isolated plugin tools now execute through JSON RPC and receive capability checks.
- Extension and MCP tools must declare security capabilities before exposure.
- The normal full workflow is tested through reproduction, isolated mutation,
  deterministic verification, independent review, and safe source application.
- Existing repository failures can be baselined, but new regressions remain fatal.
- Local Nova validation is reported as deterministic-only assurance, never as an
  independent semantic review.

## Deterministic evidence

- Test suite: 340 passed.
- Byte compilation: passed.
- Wheel build: passed.
- Installed CLI version and command smoke tests: release qualification step.
- Long-horizon live provider gate: configured as release-blocking with three fresh
  trials and 100% required pass rate; not executable without provider credentials.

## Product boundary

Credible launch message:

> Nexus is a model-agnostic coding runtime that plans changes, executes inside
> confined workspaces, verifies outcomes with real tools, and returns evidence-backed
> diffs with rollback and recovery.

Do not claim "build anything from one prompt" until repeated live benchmark
artifacts demonstrate that result across representative repositories and stacks.
