# NEXUS CLI — MCP SERVER SECURITY ARCHITECTURE

Model Context Protocol (MCP) servers are treated as external trust boundaries.
- Server configuration requires explicit command validation.
- Commands containing `sudo` or `rm -rf` are denied before launch.
- Tool outputs from MCP servers are tagged as untrusted data in model context.
