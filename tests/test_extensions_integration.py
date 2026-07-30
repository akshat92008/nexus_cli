import pytest
from nexus.extensions import ExtensionRegistry

def test_extensions_actual_load():
    # Load actual entry points from the environment
    registry = ExtensionRegistry()
    registry.discover()
    
    # We might not have any installed, but it should not crash
    assert isinstance(registry.loaded("providers"), list)
    assert isinstance(registry.loaded("tools"), list)
    assert isinstance(registry.loaded("policies"), list)
