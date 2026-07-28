from nova_v12.data.quality import score_code
from nova_v12.data.security import scan_sensitive_text


def test_security_scanner_finds_secret():
    findings = scan_sensitive_text('api_key = "abcdefghijklmnop1234"', flag_pii=False)
    assert any(item.kind == "generic_secret" for item in findings)


def test_security_scanner_allows_example_email():
    assert not scan_sensitive_text("contact = 'person@example.com'")


def test_quality_accepts_parseable_python():
    content = '"""Math helpers."""\n\ndef add_values(left, right):\n    return left + right\n'
    report = score_code(content, "python")
    assert report.syntax_valid
    assert report.accepted


def test_quality_rejects_invalid_python():
    report = score_code("def broken(:\n    pass\n" * 5, "python")
    assert not report.accepted
    assert not report.syntax_valid
