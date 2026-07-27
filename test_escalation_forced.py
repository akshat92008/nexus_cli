import json
import os
import re
from pipeline import CeilingInternPipeline
from output_parser import ParsedResponse, FileAction
from constraint_checker import LiteralConstraint

class MockIntern:
    def __init__(self, mode):
        self.mode = mode
    
    def execute(self, task, context="", override_prompt=""):
        class DummyResponse:
            def __init__(self, mode):
                self.is_valid = True
                self.test_command = "npm test"
                self.parse_errors = []
                
                if mode == "case5_bad":
                    self.raw_text = "Here is app/auth.py"
                    self.files = [FileAction(path="app/auth.py", action="MODIFY", content="code")]
                elif mode == "case6_bad":
                    self.raw_text = "res.status(500).json({status: 'degraded'})"
                    self.files = [FileAction(path="src/app.js", action="MODIFY", content="try {} catch(e) { return res.status(500).json({status: 'degraded'}) }")]
                elif mode == "format_bad":
                    self.is_valid = False
                    self.parse_errors = ["Missing <<FILES>> block"]
                    self.raw_text = "I am a bad format"
                    self.files = []
                
        class DummyTaskResult:
            def __init__(self, mode, task):
                self.task = task
                self.response = DummyResponse(mode)
                self.execution_time_ms = 100
                self.test_status = "UNTESTED"
                self.test_output = ""
                
        return DummyTaskResult(self.mode, task)

def test_forced(mode, prompt):
    print(f"\n{'='*50}\n  RUNNING FORCED FAILURE: {mode}\n{'='*50}")
    
    pipeline = CeilingInternPipeline(ceiling_provider="manual", intern_model="nova3b", run_tests=False)
    pipeline.intern = MockIntern(mode)
    
    pipeline.run(prompt)
    
    print("\n  VERIFYING LOG SCHEMA")
    with open('guardrail_events.jsonl', 'r') as f:
        lines = f.readlines()
        print(json.dumps(json.loads(lines[-1]), indent=2))

if __name__ == "__main__":
    if os.path.exists('guardrail_events.jsonl'):
        os.remove('guardrail_events.jsonl')
        
    prompt5 = "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."
    test_forced("case5_bad", prompt5)
    
    prompt6 = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."
    test_forced("case6_bad", prompt6)

    test_forced("format_bad", "Just write some code")
