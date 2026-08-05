# NEXUS CLI — AUDIT LOGGING & PROVENANCE

`AuditLogger` and `AuditIntegrityVerifier` (`nexus/security/audit_logger.py`) maintain append-only, SHA-256 hash-chained security event logs under `.nexus/runs/<run-id>/audit/audit.jsonl`.
- Each event includes `prev_hash` and `event_hash`.
- Tamper detection verifies event order and payload integrity.
- Automatic secret redaction is applied before writing records to disk.
