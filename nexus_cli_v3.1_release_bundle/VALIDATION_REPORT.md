# NexusAI 3.1 validation report

Validation date: 2026-07-31

## Completed checks

- `python -m pytest -q`: **243 passed**.
- `python -m compileall -q nexus tests scripts`: passed.
- Wheel build using the PEP 517 backend through `pip wheel`: passed.
- Wheel target installation without source-tree imports: passed.
- Installed `python -m nexus --version`: `NexusAI 3.1.0`.
- Installed `python -m nexus --help`: passed and exposes the custom provider,
  local-intern, fallback, and plugin controls.
- Installed `python -m nexus --list-models`: passed.
- Installed `python -m nexus --doctor --working-dir /tmp` with a synthetic
  hosted credential: READY; unavailable Ollama is a warning rather than a
  hosted-run blocker.
- Installed benchmark manifest dry run: passed.

## Built artifact

- `nexusai_cli-3.1.0-py3-none-any.whl`
- SHA-256: `4e9eb622ba6128d7657da1a15b21b09547ccd46ed1d2ec2542988fe22076873c`
- Packaged files: 93

## Not completed in this environment

- Ruff could not be executed because the available package index did not
  contain the declared Ruff dependency. The attempt failed before installation;
  no lint-success claim is made.
- A live frontier-model benchmark was not run because no real provider
  credential was supplied. No Claude-parity claim is made from deterministic
  tests alone.
- Native OS sandboxing is unavailable in this container; doctor correctly
  reports the restricted-process fallback and policy-only filesystem/network
  isolation.

## Release interpretation

The deterministic code and packaging gates pass. The repository is suitable as
an alpha launch candidate after maintainers run Ruff and the repeated live E2E
suite on the exact documented provider/model. Production and parity claims must
be based on those live results.
