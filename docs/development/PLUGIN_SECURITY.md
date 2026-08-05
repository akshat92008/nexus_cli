# NEXUS CLI — PLUGIN SECURITY ARCHITECTURE

`PluginMCPGuard` (`nexus/security/plugin_mcp_guard.py`) enforces strict permission declarations, manifest validation, tool-name collision prevention, and isolated execution bounds for plugins.
- Reserved tool names (`read_file`, `run_command`, etc.) cannot be spoofed by plugins.
- Plugin manifests declare allowed paths, network domains, and subprocess requirements.
