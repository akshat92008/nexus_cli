# NexusAI 3.1 launch-hardening notes

This release concentrates on predictable execution and launch operations rather
than adding another feature layer.

## What changed

- **Nova is optional and off by default for hosted runs.** Use
  `--local-intern auto` to use it only when its Ollama model is available, or
  `--local-intern required` when a run must use the local intern.
- **Any OpenAI-compatible frontier model can be selected explicitly** with
  `--model custom --model-id ...`, `NEXUS_OPENAI_BASE_URL`, and
  `NEXUS_OPENAI_API_KEY`. OpenRouter can be used with `OPENROUTER_API_KEY` and
  the same custom model selection.
- **Backend preflight stops invalid runs early.** Missing credentials, malformed
  custom URLs, unreachable Ollama, and missing local models now produce a
  concrete repair instruction before an agent run starts.
- **Hosted-to-Nova fallback is opt-in.** A hosted failure no longer silently
  drops into the local model unless `--enable-nova-fallback` is supplied.
- **Network fetching is hardened.** `web_fetch` blocks unsafe schemes,
  loopback/private/link-local targets, dangerous redirects, oversized bodies,
  and unsafe content types.
- **Benchmarks preserve the cause of failure.** Results now distinguish
  environment/configuration failures from model, tool, policy, execution, and
  verification failures, with redacted stdout/stderr tails.
- **Budget enforcement remains conservative** when a provider does not return
  token-usage metadata.
- **Plugins are actually wired to the public CLI** through
  `--enable-plugins`; they remain disabled unless explicitly trusted and
  enabled.
- **Web sessions inherit the CLI runtime policy** and serialize operations per
  session to avoid overlapping mutations on one Agent instance.

## Recommended quality-first configuration

```bash
export NEXUS_OPENAI_BASE_URL="https://your-provider.example/v1"
export NEXUS_OPENAI_API_KEY="..."

nexus --model custom \
  --model-id "provider/frontier-coding-model" \
  --local-intern off \
  --permission-mode default \
  "fix the failing tests and show the verified diff"
```

Use `--local-intern auto` only when lowering cost is more important than keeping
all reasoning on the selected hosted model.

## Release checks

```bash
python -m pytest -q
python -m compileall -q nexus tests
python scripts/run_release_gate.py

# Live repeated evaluation with the chosen frontier provider
python scripts/run_release_e2e.py \
  --model custom \
  --model-id "provider/frontier-coding-model"
```

Do not publish a Claude-parity claim from one successful run. Report at least
pass@1, pass@3, median cost, median latency, false-verification rate, and
workspace-damage rate across repeated clean runs.

## Remaining boundary

Version 3.1 removes concrete launch blockers, but code architecture cannot by
itself guarantee Claude Code-level reasoning. That depends on the selected
model and measured end-to-end reliability. A public alpha can ship after the
release gate and live benchmark pass on the exact provider configuration that
will be documented. A broad production claim should wait for repeatable live
results and real-user telemetry.
