"""
Plugin Loader — handles auto-discovery and loading of plugin packages.

Discovers plugins in:
1. project-local `nexus_plugins/`
2. global `~/.nexusai/plugins/`
"""

import importlib.util
import json
from pathlib import Path

from nexus.plugins.base import BasePlugin


class PluginLoader:
    """
    Auto-discovers and registers plugins.
    
    Loads modules, instantiates classes inheriting BasePlugin, and validates metadata.
    """

    def __init__(self, working_dir: str = ""):
        self.working_dir = working_dir
        self.plugins: dict[str, BasePlugin] = {}

    def discover_and_load(self) -> list[BasePlugin]:
        """Scan local and global plugins directories and load found plugins."""
        search_paths = []
        
        # Local project path plugin loading has been removed for security
        # Global home path
        global_plugins = Path.home() / ".nexusai" / "plugins"
        if global_plugins.is_dir():
            search_paths.append(global_plugins)

        loaded_plugins = []
        for path in search_paths:
            for item in path.iterdir():
                if item.is_dir() and not item.name.startswith("_"):
                    plugin = self._load_plugin_dir(item)
                    if plugin:
                        self.plugins[plugin.name] = plugin
                        loaded_plugins.append(plugin)

        return loaded_plugins

    def _load_plugin_dir(self, plugin_dir: Path) -> BasePlugin | None:
        """Load a plugin from directory containing entry point file and plugin.json."""
        manifest_file = plugin_dir / "plugin.json"
        
        # P0-1 FIX: Require explicit manifest for security containment
        if not manifest_file.exists():
            return None
            
        entry_file = plugin_dir / "__init__.py"
        
        if not entry_file.exists():
            # Try to search for main entry python file if specified in plugin.json
            try:
                with open(manifest_file) as f:
                    data = json.load(f)
                entry_point = data.get("entry_point", "main.py")
                entry_file = plugin_dir / entry_point
            except Exception:
                return None

        if not entry_file.exists():
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_dir.name}", str(entry_file)
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Search module attributes for BasePlugin subclass
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin
                    ):
                        plugin_instance = attr()
                        if plugin_instance.setup():
                            return plugin_instance
        except Exception:
            pass

        return None
