# PATCH INTEGRATION AND VERIFICATION

## Overview
Nexus CLI enforces real patch integration and central verification against the exact integrated repository tree.

## Integration Lifecycle
1. **Filtering**: Only worker results with review decision `APPROVE_FOR_INTEGRATION` proceed.
2. **Conflict Detection**:
   - Mechanical / text conflicts (path overlap across workers)
   - Semantic conflicts (conflicting symbol exports, divergent API assumptions, configuration key clashes)
3. **Patch Application**: Applies patch artifacts to a clean integration workspace in deterministic assignment order.
4. **Tree Hash Calculation**: Calculates the integrated repository SHA-256 tree hash.
5. **Central Verification**: Executes `VerificationService` on the exact integrated tree hash.
6. **Rollback**: Full rollback to baseline checkpoint on any verification failure.
