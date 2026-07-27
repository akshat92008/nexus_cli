import sys
import re

with open("pipeline.py", "r") as f:
    content = f.read()

# Add imports
if "from constraint_checker" not in content:
    content = content.replace(
        "from guardrail import (",
        "from constraint_checker import ConstraintExtractor, ConstraintVerifier\nfrom guardrail import ("
    )

# Add init
if "self.constraint_extractor =" not in content:
    content = content.replace(
        "self.guardrail = TaskGuardrail(max_reroutes=guardrail_max_reroutes)",
        "self.guardrail = TaskGuardrail(max_reroutes=guardrail_max_reroutes)\n        self.constraint_extractor = ConstraintExtractor()\n        self.constraint_verifier = ConstraintVerifier()"
    )

# Add extraction before execution
exec_block = """
            # ── EXECUTE: send to Nova ────────────────────────────────────────
            task_result = self.intern.execute(task, context=context_accumulator)
"""
new_exec_block = """
            # ── CONSTRAINT EXTRACTION ────────────────────────────────────────
            constraint = self.constraint_extractor.extract(task.description)
            if constraint:
                print(f"   🎯 CONSTRAINT: Found literal constraint -> {constraint.type}: {constraint.value}")

            # ── EXECUTE: send to Nova ────────────────────────────────────────
            task_result = self.intern.execute(task, context=context_accumulator)
"""
content = content.replace(exec_block, new_exec_block)

# Add verification
test_logic = """
                # Run tests if enabled
                if self.run_tests:
"""
new_test_logic = """
                # ── CONSTRAINT VERIFICATION ────────────────────────────────────
                if constraint:
                    passed, reason = self.constraint_verifier.verify(constraint, task_result.response.files)
                    if passed:
                        task_result.test_status = "PASS"
                    else:
                        task_result.test_status = "FAIL"
                    task_result.test_output = reason
                    print(f"   🎯 CONSTRAINT CHECK: {reason}")
                elif self.run_tests:
"""
content = content.replace(test_logic, new_test_logic)

with open("pipeline.py", "w") as f:
    f.write(content)
