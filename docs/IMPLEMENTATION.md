# Nova v12 implementation architecture

Nova v12 is a **model-development toolkit**, not a pretrained checkpoint. The repository closes the gaps found in the v12 audit:

1. Model candidates are scored through executable fixtures, not formatting heuristics.
2. Data records are licence-normalised, provenance-preserving, security-scanned, quality-gated and deduplicated.
3. Benchmark contamination scanning recursively inspects every textual field.
4. Mutation records survive only when the original passes, the mutation fails and the restored patch passes.
5. SFT and DPO records fail closed when evidence or schema requirements are missing.
6. Training stages are separate and configuration-driven.

## Release gates

### Gate A — deterministic engineering pipeline

- `pytest` and CI pass.
- Sample tasks execute successfully.
- Dataset builds are resumable and produce manifests.
- Validators reject malformed or unverified records.

### Gate B — foundation bake-off

- Pin model revisions.
- Use candidate-native templates.
- Run the same executable task set and budgets.
- Publish raw generations, execution logs and hardware details.

### Gate C — 1M token smoke run

- Build a small corpus.
- Train a short CPT candidate.
- Export and run inference.
- Compare against the untouched foundation.

### Gate D — 50M token pilot

Scale only when the smoke run improves at least one core metric without major regression.

### Gate E — public model release

A checkpoint is not called Nova v12 flagship until it has reproducible benchmark evidence, a complete model card, licence attribution and quantised validation.

## Security boundary

`SandboxRunner` avoids shell invocation and applies resource limits, but it is not a hardened hostile-code sandbox. Run untrusted repositories inside a container or virtual machine with network disabled and a read-only base image.
