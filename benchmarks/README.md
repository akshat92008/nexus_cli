# Nexus reproducible benchmarks

`nexus benchmark` runs each manifest task in a disposable repository copy and
records deterministic checks, changed files, time, model calls, tokens, cost,
retries, and human-intervention state. Results include the exact Nexus version.

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

Verification commands are JSON argv arrays, never shell strings. A passing
result requires a zero Nexus exit, deterministic checks, permitted file scope,
expected mutations, and a fully `VERIFIED` internal run report. External and
internal outcomes remain separate in the result schema.
Provider-dependent results are not committed as product claims until the
manifest, model configuration, environment, and raw result are published.
