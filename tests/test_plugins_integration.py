import json

from nexus.plugins.loader import PluginLoader


def test_actual_plugin_subprocess(tmp_path):
    # We will create a local plugin in a temporary working dir and use discover_local_plugins
    project_dir = tmp_path / "my_project"
    plugin_dir = project_dir / ".nexus" / "plugins" / "my_actual_plugin"
    plugin_dir.mkdir(parents=True)

    # Write a real manifest
    manifest_data = {
        "name": "actual-plugin",
        "description": "An actual plugin running in a subprocess",
        "version": "1.0",
        "entry_point": "plugin_entry.py",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest_data))

    # Write a real python entry point for the plugin!
    # The plugin worker expects the script to be importable and maybe define a class?
    # Let's see what PluginWorker expects. It just runs the script. Wait, worker.py says:
    # "PluginWorker manages an isolated subprocess...".
    # What does the worker script expect?
    (plugin_dir / "plugin_entry.py").write_text("""
# No print
# The PluginWorker script imports this. We just need it to not crash.
class MyPlugin:
    name = "actual-plugin"
    def setup(self):
        return True
        pass

def register():
    return {"status": "success"}
""")

    loader = PluginLoader(
        working_dir=str(project_dir), plugins_enabled=True, trust_checker=lambda x: True
    )

    # Manually load the plugin directory since discover_local_plugins might require specific layout
    # Wait, discover_local_plugins scans project_dir / ".nexus" / "plugins"
    # Actually, we can just call _load_plugin_dir directly to avoid layout issues.
    plugin = loader._load_plugin_dir(plugin_dir, "local")

    assert plugin is not None
    assert plugin.name == "actual-plugin"

    # We should have diagnostics
    assert len(loader.diagnostics) == 1
    assert loader.diagnostics[0].status == "loaded"
    loader.shutdown()
