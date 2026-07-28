# Nova v12 — Dataset Card Template

## Dataset Details

### Dataset Name
amauralabs/Nova-Code-Training-Data

### Version
v12.0

### Created By
Amaura Labs

### Licence
Derivative of permissively licensed source code (MIT, Apache-2.0, BSD, ISC, Unlicense, CC0-1.0)

---

## Dataset Description

Training data for the Amaura Nova Code model family. Composed of:

1. **Continued pretraining corpus** — Filtered, deduplicated source code
2. **Supervised fine-tuning examples** — Execution-verified coding tasks
3. **Preference pairs** — Execution-ranked DPO training data
4. **Agentic trajectories** — Tool-use workflows with sandbox verification

---

## Data Sources

### Source Code (Continued Pretraining)
- **Origin:** Permissively licensed repositories from The Stack v2
- **Licences allowed:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Unlicense, CC0-1.0
- **Filtering:** AST parse success, quality scoring, deduplication, contamination check

### Supervised Examples
- **Origin:** Teacher-model generation + sandbox verification
- **Verification:** Every example compiled and tested in isolated sandbox
- **Teachers:** [List teacher models used]

### Preference Pairs
- **Origin:** Multiple candidates generated per task, ranked by execution
- **Ranking criteria:** Test pass rate, compilation success, change minimality

### Agentic Trajectories
- **Origin:** Nexus data factory + manual curation
- **Tools:** list_files, search_code, read_file, apply_patch, run_tests

---

## Data Statistics

| Category | Count |
|---|---|
| Total CPT tokens | |
| SFT examples | |
| Verified repository tasks | |
| Preference pairs | |
| Agentic trajectories | |
| Programming languages | 9+ |
| Unique repositories | |

### Language Distribution

| Language | Allocation |
|---|---|
| Python | 25% |
| JavaScript/TypeScript | 25% |
| Java/C++ | 20% |
| Go/Rust | 15% |
| SQL/Bash | 10% |
| Other | 5% |

---

## Data Processing

### Quality Filtering
- AST parse validation
- Comment-to-code ratio check
- Generated-code detection
- Repository maintenance signals
- Complexity scoring

### Deduplication
- Exact: SHA-256 hash on normalised content
- Near: MinHash + LSH (80-85% similarity threshold)
- Semantic: Trivial function detection and removal

### Safety Filtering
- Secret/credential detection
- PII removal
- Malware scanning
- Benchmark contamination check (HumanEval, MBPP, LiveCodeBench, SWE-bench)

---

## Provenance Tracking

Every record includes:
```json
{
  "source_repository": "org/project",
  "source_commit": "abc123",
  "source_path": "src/module.py",
  "source_licence": "Apache-2.0",
  "content_hash": "sha256:...",
  "language": "python",
  "generation_provenance": "teacher_model | human | repository",
  "verification_status": "compiled_and_tested | compiled_only | unverified",
  "dataset_split": "train | eval | held_out"
}
```

---

## Ethical Considerations

- All source code is permissively licensed
- No private or proprietary code included
- Secret detection applied to all content
- PII scanning applied to all content
- Benchmark solutions explicitly excluded to prevent contamination

---

*Amaura Labs — Building verifiable intelligence.*
