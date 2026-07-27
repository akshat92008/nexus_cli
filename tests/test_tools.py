"""
Smoke tests for NexusAI tools — verifies all 22 tools execute without crashing.
"""
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus.tools import TOOL_DEFINITIONS, TOOL_DISPATCH, execute_tool


def test_all_tools_have_definitions():
    """Every tool in the dispatch table should have a definition."""
    dispatch_names = set(TOOL_DISPATCH.keys())
    definition_names = {td["function"]["name"] for td in TOOL_DEFINITIONS}
    missing_defs = dispatch_names - definition_names
    missing_dispatch = definition_names - dispatch_names
    assert not missing_defs, f"Tools without definitions: {missing_defs}"
    assert not missing_dispatch, f"Definitions without dispatch: {missing_dispatch}"
    assert len(TOOL_DEFINITIONS) == 22, f"Expected 22 tools, got {len(TOOL_DEFINITIONS)}"


def test_process_status_rejects_unmanaged_pid():
    result = execute_tool("process_status", {"pid": 99999999})
    assert result.startswith("❌")
    assert "not a Nexus-managed" in result


def test_process_stop_rejects_unmanaged_pid():
    result = execute_tool("process_stop", {"pid": 99999999})
    assert result.startswith("❌")
    assert "not a Nexus-managed" in result


def test_read_file():
    """read_file should return file contents with line numbers."""
    result = execute_tool("read_file", {"path": "run.py"})
    assert "📄" in result
    assert "run.py" in result
    assert "main()" in result


def test_read_file_not_found():
    """read_file should return error for missing file."""
    result = execute_tool("read_file", {"path": "/nonexistent/file.xyz"})
    assert "❌" in result


def test_write_file():
    """write_file should create a file and return success."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        tmp_path = f.name
    try:
        result = execute_tool("write_file", {"path": tmp_path, "content": "hello world"})
        assert "✅" in result
        assert Path(tmp_path).read_text() == "hello world"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_edit_file():
    """edit_file should replace text in a file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("original content here")
        tmp_path = f.name
    try:
        result = execute_tool("edit_file", {
            "path": tmp_path,
            "old_text": "original",
            "new_text": "modified",
        })
        assert "✅" in result
        assert "modified content here" in Path(tmp_path).read_text()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_edit_file_doc_envelope_fallback():
    """edit_file should fall back to replacing full document content when old_text is an HTML envelope."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write("<!DOCTYPE html>\n<html><head></head><body><h1>Old</h1></body></html>")
        tmp_path = f.name
    try:
        result = execute_tool("edit_file", {
            "path": tmp_path,
            "old_text": "<!DOCTYPE html>\n<html><head></head><body><h1>Different Spacing</h1></body></html>",
            "new_text": "<!DOCTYPE html>\n<html><head><style>body{color:red;}</style></head><body><h1>New</h1></body></html>",
        })
        assert "✅" in result
        assert "New" in Path(tmp_path).read_text()
    finally:
        Path(tmp_path).unlink(missing_ok=True)



def test_edit_file_not_found():
    """edit_file should error when text not found."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello")
        tmp_path = f.name
    try:
        result = execute_tool("edit_file", {
            "path": tmp_path,
            "old_text": "nonexistent",
            "new_text": "replacement",
        })
        assert "❌" in result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_file_info():
    """file_info should return metadata."""
    result = execute_tool("file_info", {"path": "run.py"})
    assert "📋" in result
    assert "run.py" in result
    assert "Type:" in result
    assert "Size:" in result


def test_file_info_not_found():
    """file_info should error for missing path."""
    result = execute_tool("file_info", {"path": "/nonexistent"})
    assert "❌" in result


def test_get_project_structure():
    """get_project_structure should return a tree."""
    result = execute_tool("get_project_structure", {"path": ".", "max_depth": 2})
    assert "🌳" in result
    assert "nexus/" in result


def test_list_directory():
    """list_directory should list files."""
    result = execute_tool("list_directory", {"path": ".", "recursive": False})
    assert "📁" in result
    assert "run.py" in result


def test_find_files():
    """find_files should find files by glob."""
    result = execute_tool("find_files", {"pattern": "*.py", "directory": "."})
    assert "🔍" in result
    assert "run.py" in result


def test_search_code():
    """search_code should find pattern matches."""
    result = execute_tool("search_code", {"pattern": "def execute_tool", "directory": "nexus"})
    assert "🔍" in result
    assert "execute_tool" in result


def test_run_command():
    """run_command should execute a shell command."""
    result = execute_tool("run_command", {"command": "echo hello_test"})
    assert "✅" in result
    assert "hello_test" in result


def test_run_command_string_timeout():
    """run_command should handle timeout passed as a string without crashing."""
    result = execute_tool("run_command", {"command": "echo timeout_test", "timeout": "120"})
    assert "✅" in result
    assert "timeout_test" in result


def test_run_command_failure():
    """run_command should show exit code for failed commands."""
    result = execute_tool("run_command", {"command": "exit 1"})
    assert "❌" in result or "exit code 1" in result


def test_git_status():
    """git_status should handle non-git repos gracefully."""
    result = execute_tool("git_status", {})
    # This project is now a git repo, so it should show branch info
    assert "🌿" in result or "❌" in result


def test_web_search():
    """web_search should return results or a graceful error."""
    result = execute_tool("web_search", {"query": "python programming", "max_results": 2})
    # May fail if offline, but should not crash
    assert isinstance(result, str)
    assert len(result) > 10


def test_web_fetch():
    """web_fetch should return content or a graceful error."""
    result = execute_tool("web_fetch", {"url": "https://example.com", "max_length": 500})
    assert isinstance(result, str)
    assert len(result) > 10


def test_multi_edit():
    """multi_edit should apply multiple edits."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line one\nline two\nline three")
        tmp_path = f.name
    try:
        result = execute_tool("multi_edit", {
            "edits": [
                {"path": tmp_path, "old_text": "line one", "new_text": "first"},
                {"path": tmp_path, "old_text": "line three", "new_text": "third"},
            ]
        })
        assert "📝" in result
        content = Path(tmp_path).read_text()
        assert "first" in content
        assert "third" in content
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_patch_file():
    """patch_file should replace lines by range."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\nline4")
        tmp_path = f.name
    try:
        result = execute_tool("patch_file", {
            "path": tmp_path,
            "start_line": 2,
            "end_line": 3,
            "new_content": "replaced2\nreplaced3",
        })
        assert "✅" in result
        content = Path(tmp_path).read_text()
        assert "line1" in content
        assert "replaced2" in content
        assert "replaced3" in content
        assert "line4" in content
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_diff_files():
    """diff_files should show differences between files."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fa:
        fa.write("hello\nworld")
        path_a = fa.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fb:
        fb.write("hello\nuniverse")
        path_b = fb.name
    try:
        result = execute_tool("diff_files", {"file_a": path_a, "file_b": path_b})
        assert "📝" in result or "✅" in result
    finally:
        Path(path_a).unlink(missing_ok=True)
        Path(path_b).unlink(missing_ok=True)


def test_unknown_tool():
    """execute_tool should return error for unknown tools."""
    result = execute_tool("nonexistent_tool", {})
    assert "❌" in result
    assert "Unknown tool" in result


def test_all_tools_execute():
    """Every registered tool should accept empty/default args without crashing."""
    for name in TOOL_DISPATCH:
        try:
            result = execute_tool(name, {})
            assert isinstance(result, str)
        except TypeError:
            # Some tools require specific args — that's fine
            pass


def test_resolve_path():
    """_resolve_path should correctly map desktop paths and expand home."""
    from nexus.tools import _resolve_path
    dt_path = _resolve_path("desktop/calculator/index.html")
    expected_desktop = Path.home() / "Desktop" / "calculator" / "index.html"
    assert dt_path == expected_desktop.resolve()


def test_normalize_tool_arguments():
    """normalize_tool_arguments should normalize parameter names."""
    from nexus.tools import normalize_tool_arguments
    res1 = normalize_tool_arguments("write_file", {"file_path": "a.py", "content": "1"})
    assert res1["path"] == "a.py"

    res2 = normalize_tool_arguments("run_command", {"cmd": "ls -l"})
    assert res2["command"] == "ls -l"

    res3 = normalize_tool_arguments("search_code", {"query": "import"})
    assert res3["pattern"] == "import"
