# NEXUS CLI — FILESYSTEM SECURITY ARCHITECTURE

## Overview
`FilesystemSecurity` (`nexus/security/filesystem_security.py`) guarantees workspace boundary integrity for all file read and write requests.

## Key Controls
1. **Canonicalization**: Full path resolution via `Path.resolve()`.
2. **Null Byte Rejection**: Immediate `ValueError` if null bytes (`\x00`) are detected in raw paths.
3. **Traversal Prevention**: Blocks path traversal attacks trying to escape the workspace root.
4. **Symlink Escape Detection**: Verifies that symlink targets remain inside approved workspace bounds.
5. **Protected Paths**: Hard deny on `.env`, `.ssh/`, `id_rsa`, `.aws/credentials`, `.gcp/`, `/etc/shadow`, `/etc/passwd`.
