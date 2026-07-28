import sys
from pipeline import CeilingInternPipeline
from constraint_checker import ConstraintVerifier, ConstraintExtractor, LiteralConstraint
from output_parser import FileAction

prompt = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."

# Part 1: Run 3 times through the pipeline
pipeline = CeilingInternPipeline(
    ceiling_provider="manual",
    intern_model="nova3b",
    run_tests=True,
)

print("=== PART 1: PIPELINE RUNS ===")
for i in range(3):
    print(f"\n--- RUN {i+1} ---")
    result = pipeline.run(prompt)
    if result.results:
        task_res = result.results[0]
        print("\nRAW PIPELINE OUTPUT:")
        print(task_res.response.raw_text)
        print("\nTEST RESULT:")
        print(f"Passed: {task_res.test_status}")
        print(f"Output: {task_res.test_output}")

# Part 2: Manual Mock Verification
print("\n\n=== PART 2: MANUAL MOCK TESTS ===")
class DummyNode:
    client = "manual"

extractor = ConstraintExtractor(DummyNode())
verifier = ConstraintVerifier(DummyNode())

constraints = extractor.extract(prompt)
print(f"Extracted constraints: {[c.value for c in constraints]}")

mock_1 = FileAction(path="app.js", action="MODIFY", content="""
try {
  const x = db.query();
} catch (error) {
  // Wrong string, correct code
  return res.status(200).json({ status: 'unhealthy' });
}
""")

mock_2 = FileAction(path="app.js", action="MODIFY", content="""
try {
  const x = db.query();
} catch (error) {
  // Correct string, wrong code
  return res.status(503).json({ status: 'degraded' });
}
""")

mock_3 = FileAction(path="app.js", action="MODIFY", content="""
try {
  const x = db.query();
} catch (error) {
  // Both correct
  return res.status(200).json({ status: 'degraded' });
}
""")

print("\nMOCK 1 (Right code 200, Wrong string 'unhealthy'):")
passed1, reason1 = verifier.verify(constraints, [mock_1])
print(f"Passed: {passed1}\nReason: {reason1}")

print("\nMOCK 2 (Wrong code 503, Right string 'degraded'):")
passed2, reason2 = verifier.verify(constraints, [mock_2])
print(f"Passed: {passed2}\nReason: {reason2}")

print("\nMOCK 3 (Both correct):")
passed3, reason3 = verifier.verify(constraints, [mock_3])
print(f"Passed: {passed3}\nReason: {reason3}")

