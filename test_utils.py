from src.utils import calculate_metrics
import sys

def run_tests():
    try:
        assert calculate_metrics(None) == [], "None handling failed"
        payload = {"a": 3, "b": {"c": 1, "d": [5, 2]}, "e": 4}
        assert calculate_metrics(payload) == [1, 2, 3, 4, 5], "Nested payload handling failed"
        print("✅ ALL TESTS PASSED: calculate_metrics handles None and extracts nested values perfectly.")
    except Exception as e:
        print("❌ TEST FAILED:", e)
        sys.exit(1)

run_tests()
