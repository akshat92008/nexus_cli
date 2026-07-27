"""Focused tests for Nexus' Nova adapter."""

from nexus.nova_backend import PROMPT_PATH, NovaPipelineBackend
from nexus.two_node_backend import TwoNodeBackend


def test_prompt_path_accepts_ceiling_punctuation():
    text = "MODIFY src/app.py: then update tests/test_app.py; verify src/worker.py)."
    assert PROMPT_PATH.findall(text) == [
        "src/app.py",
        "tests/test_app.py",
        "src/worker.py",
    ]


def test_verified_model_is_the_backend_default():
    assert NovaPipelineBackend().model == "nova_codex"


def test_file_action_modify_without_patch_blocks_falls_back_to_write_file():
    from output_parser import FileAction
    backend = NovaPipelineBackend()
    action = FileAction(path="src/app.js", action="MODIFY", content="console.log('hello');")
    proposals = backend._file_action_to_tool_calls(action, "test guardrail summary")
    assert len(proposals) == 1
    assert proposals[0].name == "write_file"
    assert proposals[0].args["path"] == "src/app.js"
    assert proposals[0].args["content"] == "console.log('hello');"


def test_file_action_unified_diff_converts_to_edit_file():
    from output_parser import FileAction
    backend = NovaPipelineBackend()
    diff_content = (
        "--- a/todo.html\n"
        "+++ b/todo.html\n"
        "@@ -10,3 +10,4 @@\n"
        " <body>\n"
        "+    <h1>Title</h1>\n"
        " </body>\n"
    )
    action = FileAction(path="todo.html", action="MODIFY", content=diff_content)
    proposals = backend._file_action_to_tool_calls(action, "test summary")
    assert len(proposals) == 1
    assert proposals[0].name == "edit_file"
    assert proposals[0].args["path"] == "todo.html"
    assert proposals[0].args["old_text"] == "<body>\n</body>"
    assert proposals[0].args["new_text"] == "<body>\n    <h1>Title</h1>\n</body>"


def test_file_action_unclosed_create_diff_header_stripping():
    from output_parser import FileAction
    backend = NovaPipelineBackend()
    content = "<<<<<<<\n# \n=======\nclass Node:\n    pass\n"
    action = FileAction(path="lru_cache.py", action="CREATE", content=content)
    proposals = backend._file_action_to_tool_calls(action, "test summary")
    assert len(proposals) == 1
    assert proposals[0].name == "write_file"
    assert proposals[0].args["path"] == "lru_cache.py"
    assert proposals[0].args["content"] == "class Node:\n    pass"


def test_file_action_deduplicates_repetitive_loop_blocks():
    from output_parser import FileAction
    backend = NovaPipelineBackend()
    content = "```python\n# File: api_client.py\n<<<<<<<\n# \n=======\nimport json\nclass APIClient:\n    pass\n>>>>># File: api_client.py\n" * 3
    action = FileAction(path="api_client.py", action="MODIFY", content=content)
    proposals = backend._file_action_to_tool_calls(action, "test summary")
    assert len(proposals) == 1
    assert proposals[0].name == "write_file"
    assert proposals[0].args["path"] == "api_client.py"
    assert proposals[0].args["content"] == "import json\nclass APIClient:\n    pass"


def test_file_action_ignores_trailing_filename_label_artifacts():
    from output_parser import FileAction
    backend = NovaPipelineBackend()
    content = "<<<<<<<\n=======\nconst task = 1;\n>>>>>># File: task_queue.js\n task_queue.js"
    action = FileAction(path="task_queue.js", action="MODIFY", content=content)
    proposals = backend._file_action_to_tool_calls(action, "test summary")
    assert len(proposals) == 1
    assert proposals[0].name == "write_file"
    assert proposals[0].args["path"] == "task_queue.js"
    assert proposals[0].args["content"] == "const task = 1;"


def test_cleaned_protocol_is_materialized_before_compilation(tmp_path):
    from output_parser import FileAction

    backend = NovaPipelineBackend()
    action = FileAction(
        path="hello.py",
        action="CREATE",
        content=(
            "<<<<<<<\n# template placeholder\n=======\n"
            "def main():\n    print('hello')\n\n"
            "if __name__ == '__main__':\n    main()\n>>>>>>>"
        ),
    )
    proposals = backend._file_action_to_tool_calls(action, "guarded")
    paths, error = backend._materialize_proposals(proposals, tmp_path)
    assert not error
    assert paths == ["hello.py"]
    assert (tmp_path / "hello.py").read_text().startswith("def main")


def test_ceiling_nested_language_fence_is_recovered():
    backend = object.__new__(TwoNodeBackend)
    from output_parser import NovaOutputParser

    backend.parser = NovaOutputParser()
    parsed = backend._parse_ceiling_response(
        "```language\n# filepath: path/to/main.cpp\n# action: CREATE\n"
        "```cpp\nint main() { return 0; }\n```"
    )
    assert parsed.is_valid
    assert parsed.files[0].path == "main.cpp"
    assert parsed.files[0].content == "int main() { return 0; }"
