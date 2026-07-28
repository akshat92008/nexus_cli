from nova_v12.data.adapters import adapt_stack_v1, adapt_stack_v2
from nova_v12.data.licences import allowed_licence, normalise_licence


def test_licence_normalisation_accepts_lists_and_aliases():
    assert normalise_licence(["MIT License", "Apache 2.0"]) == {"mit", "apache-2.0"}
    assert allowed_licence("GPL-3.0 OR MIT")[0] is True


def test_stack_v1_adapter_preserves_multiple_licences():
    record = adapt_stack_v1(
        {
            "repo_name": "org/repo",
            "hexsha": "abc",
            "path": "src/a.py",
            "licenses": ["GPL-3.0", "MIT"],
            "language": "Python",
            "content": "def useful_name(value):\n    return value + 1\n",
        }
    )
    assert record.repository == "org/repo"
    assert allowed_licence(record.licence)[0] is True


def test_stack_v2_requires_hydrated_content():
    try:
        adapt_stack_v2({"blob_id": "x", "detected_licenses": ["MIT"]})
    except ValueError as exc:
        assert "hydrated content" in str(exc)
    else:
        raise AssertionError("missing content must fail closed")
