# NEXUS CLI — ENTERPRISE POLICY ARCHITECTURE

`PolicyMerger` (`nexus/security/enterprise_policy.py`) provides offline-first, schema-validated enterprise policy controls:
- `OrganizationPolicy`: Top-level org rules, allowed providers, network mode, and mandatory deny actions.
- `ProjectPolicy`: Repository-level settings.
- Precedence merger ensures project or user settings can NEVER weaken an organization DENY.
