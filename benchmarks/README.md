# Nexus reproducible benchmarks

`nexus benchmark` runs each manifest task in a disposable repository copy and
records deterministic checks, changed files, time, model calls, tokens, cost,
retries, checkpoints, resumptions, quality gates, and human-intervention state.
Results include the exact Nexus version.

Validate the bundled manifest without invoking a model:

```bash
nexus benchmark --manifest benchmarks/core.json --dry-run
```

Run it and preserve the result:

```bash
nexus benchmark \
  --manifest benchmarks/core.json \
  --output benchmarks/results/nexus-3.1.1.json
```

The v2 long-horizon suite contains independent commerce-control-plane and
operations-ERP projects. It can automatically resume the same original prompt
after a process interruption or bounded turn budget. It never converts a failed
check into a pass and never sends a new product prompt:

```bash
nexus benchmark \
  --manifest benchmarks/long_horizon.json \
  --artifact-dir verification_evidence/long-horizon \
  --keep-workspaces
```

Real-provider execution is deliberately separate because it can spend money:

```bash
python scripts/run_live_provider_gate.py --allow-cost \
  --manifest benchmarks/long_horizon.json \
  --trials 3 --required-pass-rate 1.0
```

The live gate requires hosted credentials, runs every trial in a fresh
workspace, preserves redacted evidence, and fails unless every result is both
externally accepted and internally `VERIFIED`. The GitHub workflow is manual;
it is never triggered by an untrusted pull request or schedule.

Verification commands are JSON argv arrays, never shell strings. A passing
result requires a zero Nexus exit, deterministic checks, permitted file scope,
expected mutations, required artifacts, minimum test depth, placeholder checks,
and a fully `VERIFIED` internal run report. External and internal outcomes
remain separate in the result schema.
Provider-dependent results are not committed as product claims until the
manifest, model configuration, environment, and raw result are published.
