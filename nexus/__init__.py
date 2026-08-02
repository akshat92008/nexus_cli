"""NexusAI — model-agnostic, verification-driven software-engineering runtime."""

__version__ = "3.2.1"

def reset_global_state() -> None:
    """Reset shared module-level state for deterministic test isolation."""
    from nexus.sandbox import SandboxRunner
    SandboxRunner._backend_cache = None

    try:
        from nexus.webapp import server
        server._agents.clear()
        server._agent_busy.clear()
        server._agent_locks.clear()
        server._web_token = None
    except ImportError:
        pass

    try:
        from nexus import tools
        tools.stop_all_background_processes()

        for pool in tools._language_service_pools.values():
            if hasattr(pool, "close"):
                try:
                    pool.close()
                except Exception:
                    pass
        tools._language_service_pools.clear()
        tools._tool_working_dir.set(None)
        tools._tool_history.set(None)
        tools._tool_owner.set("")
    except ImportError:
        pass
