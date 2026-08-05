# Nexus Release Tier Classifications

This document defines the formal criteria governing Nexus CLI launch tier decisions.

---

## Release Tiers & Criteria Matrix

### 1. NO-GO
**Conditions triggering NO-GO**:
- Any fake or placeholder success path in canonical verification.
- Any false `VERIFIED` outcome in mandatory benchmark qualification.
- Unhandled repository corruption during normal execution.
- Unredacted secret leakage in logs, outputs, or artifacts.
- Unsafe command execution or policy bypass.
- Clean installation failure on primary supported platforms.
- Non-deterministic or non-reproducible release evidence.

---

### 2. PRIVATE_ALPHA
**Appropriate when**:
- Core workflows function reliably under developer oversight.
- Minor UX or edge-case limitations exist but safety gates hold.
- Clean installation succeeds in virtual environments.
- benchmark sample size is small but evidence is promising.

---

### 3. PUBLIC_ALPHA
**Appropriate when**:
- Public package installation and CLI entry points work cleanly.
- Baseline task execution and budget enforcement operate correctly.
- Hard safety and secret redaction gates pass 100%.
- User intervention or manual configuration fine-tuning may still be required.

---

### 4. PUBLIC_BETA
**Appropriate when**:
- Primary software engineering task classes (repair, feature, refactor, test, recovery) execute autonomously with verifiable outcomes.
- Zero false success across all false-success test suites.
- Multi-agent collaboration operates safely with isolated workspaces and central verification.
- Installation from wheel/sdist works out-of-the-box on clean platforms.
- Complete documentation, privacy controls, and security policies are active.

---

### 5. RELEASE_CANDIDATE
**Appropriate when**:
- All release gates pass repeatedly across extensive benchmark runs.
- Packaging, versioning, update, and rollback paths are fully verified.
- No known critical or high-severity blockers remain.
- Feature freeze is active and final candidate validation is underway.

---

### 6. STABLE_RELEASE
**Appropriate when**:
- Release candidate validation passes all soak, performance, security, and multi-platform gates repeatedly.
- Operational support, incident procedures, and deprecation policies are established.
- Proven parity evidence demonstrates competitive performance against established benchmarks.

---

## Authoritative Tier Decision Rule

A release tier recommendation MUST be backed by empirical evidence stored in `artifacts/sprint-12-final-release.json`. If ANY mandatory gate fails, the decision falls back automatically to `NO-GO` or the highest strictly qualified lower tier.
