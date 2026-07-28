# Nova 3B v11 real retrain handoff

This handoff is for one real Google Colab/CUDA run. It uses `dataset_nova3b_v11.jsonl` unchanged.

## Upload exactly these two files

1. `train_nova3b_colab.py`
2. `dataset_nova3b_v11.jsonl`

Expected upload hashes:

- `train_nova3b_colab.py`: `b392b60a665898adbcba8eebba9126dc2d74d4fbf312efb5a513d6deee78dd70`
- `dataset_nova3b_v11.jsonl`: `b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991`

Expected dataset facts:

- Entries: `1288`
- SHA-256: `b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991`
- Composition: the byte-for-byte concatenation of v10_clean (1228), distractor (40), and format (20)

Do not upload or use `nova3b-output/nova3b-q4_k_m.gguf`; it is a 24-byte local stub, not a model.

## Colab runtime

In Colab, select **Runtime → Change runtime type → T4 GPU**. Then execute the cells below in order. Do not change the hyperparameters.

### Cell 1 — prove the GPU is real

```bash
!nvidia-smi
```

Stop if this fails or does not show an NVIDIA GPU.

### Cell 2 — install the current supported Unsloth stack

```bash
!python -m pip install -U unsloth datasets
```

Restart the runtime if Colab asks, re-upload the two files, rerun Cell 1, and continue.

### Cell 3 — record exact package versions

```bash
!python -m pip freeze | tee colab_packages_v11_real.txt
```

### Cell 4 — verify both uploaded files before training

```bash
%%bash
set -euo pipefail
sha256sum train_nova3b_colab.py dataset_nova3b_v11.jsonl
python train_nova3b_colab.py \
  --dataset dataset_nova3b_v11.jsonl \
  --expected-dataset-sha256 b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991 \
  --epochs 2 \
  --rank 32 \
  --alpha 32 \
  --lr 5e-5 \
  --output nova3b-v11-real-output \
  --dry-run
```

The final line must say that validation completed and that no training was attempted. This cell must not create the output directory.

### Cell 5 — run exactly once and preserve literal stdout/stderr

```bash
%%bash
set -euo pipefail
python -u train_nova3b_colab.py \
  --dataset dataset_nova3b_v11.jsonl \
  --expected-dataset-sha256 b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991 \
  --epochs 2 \
  --rank 32 \
  --alpha 32 \
  --lr 5e-5 \
  --output nova3b-v11-real-output \
  2>&1 | tee training_v11_real.log
```

This command uses the requested configuration: learning rate `5e-5`, rank `32`, alpha `32`, and `2` epochs. It evaluates and saves at each epoch so the literal log and `training_evidence.json` contain per-epoch loss records.

The command is successful only if its shell exit code is zero and the final output includes all of these markers:

- `TRAINING_STARTED_AT_UTC=`
- `TRAINING_FINISHED_AT_UTC=`
- `TRAINER_LOG_HISTORY_JSON_BEGIN` and `TRAINER_LOG_HISTORY_JSON_END`
- `BEST_CHECKPOINT=`
- `GGUF verified:` with a real file size and SHA-256
- `TRAINING_EVIDENCE_JSON_BEGIN` and `TRAINING_EVIDENCE_JSON_END`
- `Nova 3B Training Complete!`

Any traceback, nonzero exit, missing marker, CUDA error, training error, export error, missing GGUF magic, or implausibly small GGUF means the run failed. Do not deploy a partial checkpoint or rename it as a success.

### Recovery only — Unsloth reports a completed GGUF, then the script exits during its own post-check

This is the known artifact-discovery issue in the earlier uploaded script. Do **not** rerun training. Run these cells only when the literal log says both `All GGUF conversions completed successfully!` and `Generated files: [...]Q4_K_M.gguf` before the final traceback.

```bash
%%bash
set -euo pipefail
GGUF='nova3b-v11-real-output_gguf/qwen2.5-coder-3b-instruct.Q4_K_M.gguf'
test -s "$GGUF"
test "$(head -c 4 "$GGUF")" = 'GGUF'
stat --printf='%y | %s bytes | %n\n' "$GGUF"
sha256sum "$GGUF" training_v11_real.log
```

```python
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

gguf = Path("nova3b-v11-real-output_gguf/qwen2.5-coder-3b-instruct.Q4_K_M.gguf")
log = Path("training_v11_real.log")

def digest(path):
    value = sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()

evidence = {
    "status": "gguf_export_completed_after_training_script_postcheck_failed",
    "gguf": {
        "path": str(gguf),
        "size_bytes": gguf.stat().st_size,
        "sha256": digest(gguf),
        "mtime_utc": datetime.fromtimestamp(gguf.stat().st_mtime, timezone.utc).isoformat(),
    },
    "training_log": {"path": str(log), "sha256": digest(log)},
}
Path("v11_export_recovery_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(json.dumps(evidence, indent=2))
```

Download the GGUF, generated `Modelfile`, `v11_export_recovery_evidence.json`, `training_v11_real.log`, and `nova3b-v11-real-output/checkpoint-290/trainer_state.json`. Bring them back before deployment.

### Cell 6 — inspect and hash the literal artifacts

```bash
%%bash
set -euo pipefail
find nova3b-v11-real-output nova3b-v11-real-output_gguf -maxdepth 2 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TSZ | %s bytes | %p\n' 2>/dev/null | sort
find nova3b-v11-real-output nova3b-v11-real-output_gguf -type f -name '*.gguf' -print0 2>/dev/null | xargs -0 -r sha256sum
sha256sum nova3b-v11-real-output/training_evidence.json training_v11_real.log colab_packages_v11_real.txt
python - <<'PY'
from pathlib import Path

ggufs = sorted({path for root in (Path("nova3b-v11-real-output"), Path("nova3b-v11-real-output_gguf")) if root.is_dir() for path in root.rglob("*.gguf")})
assert ggufs, "No GGUF produced"
for path in ggufs:
    with path.open("rb") as fh:
        assert fh.read(4) == b"GGUF", f"Bad GGUF magic: {path}"
    assert path.stat().st_size >= 100 * 1024 * 1024, f"Implausibly small GGUF: {path}"
    print(f"VERIFIED_GGUF={path} SIZE={path.stat().st_size}")
PY
```

### Cell 7 — download the evidence and model

```python
from google.colab import files
from pathlib import Path

files.download("training_v11_real.log")
files.download("colab_packages_v11_real.txt")
files.download("nova3b-v11-real-output/training_evidence.json")

ggufs = sorted({path for root in (Path("nova3b-v11-real-output"), Path("nova3b-v11-real-output_gguf")) if root.is_dir() for path in root.rglob("*.gguf")})
assert ggufs, "No GGUF found"
for gguf in ggufs:
    files.download(str(gguf))
```

## Bring back all four artifact types

- The complete, unedited `training_v11_real.log`
- `colab_packages_v11_real.txt`
- `nova3b-v11-real-output/training_evidence.json`
- Every `.gguf` listed in the evidence manifest

Do not run `run_realistic_baseline.py` yet. Deployment and the one permitted 15-case run happen only after these artifacts are cross-checked locally.
