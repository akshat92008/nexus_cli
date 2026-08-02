# Security policy

## Supported versions

Security fixes are applied to the latest release line. Pre-release branches
and historical checkouts may not receive fixes.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's
**Security** tab and choose **Report a vulnerability** to send a private
advisory to the maintainers.

Include:

- affected Nexus version or commit;
- operating system and Python version;
- a minimal reproduction;
- expected and observed behavior;
- impact, including whether data, credentials, or code execution are involved.

Do not include real API keys, personal data, or private repository contents.
Use synthetic values in reproductions.

## Execution boundary

Nexus can read files, write code, run commands, access model providers, and use
the network when those capabilities are enabled. Treat model output as
untrusted input. Keep the default approval mode for unfamiliar repositories,
review every proposed diff and dangerous-operation confirmation, and use
read-only `plan` mode when no mutation is intended.

The safety layer reduces risk, but is not a bulletproof sandbox. Note the following limitations:
- **Restricted-Process Mode is not full isolation**: The `restricted-process` mode filters environment variables and uses basic controls, but it is **not equivalent to container or native kernel isolation**. It lacks strong CPU, memory, and process-count limits.
- **Windows Support**: Windows does not have a native kernel sandbox isolation implementation in Nexus.
Run Nexus with the least filesystem and credential access needed for the task.
