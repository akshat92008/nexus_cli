# WORKSPACE ISOLATION

## Overview
Nexus CLI guarantees that parallel mutating workers execute in isolated environments without corrupting the lead repository workspace or interfering with one another.

## Isolation Mechanisms
1. **READ_ONLY_SHARED_SNAPSHOT**: Used for non-mutating roles (e.g. `INVESTIGATOR`, `REVIEWER`, `SECURITY_REVIEWER`). Shares read-only access to the lead repository root.
2. **ISOLATED_WORKTREE**: Used for mutating workers when Git is present. Creates a dedicated `git worktree` off the baseline revision.
3. **ISOLATED_TEMPORARY_COPY**: Used as a fallback or for isolated workspace copies outside the lead repository root.

## Scope Reservations & Safety Rules
- Mutating paths must be reserved via `ScopeReservationRegistry`.
- Exclusive (`EXCLUSIVE`) reservations cannot overlap.
- Workers cannot mutate files outside their allowed mutation paths.
- Cleanup is guaranteed via `WorkerLifecycleManager.cleanup_all()`, even on failure or cancellation.
