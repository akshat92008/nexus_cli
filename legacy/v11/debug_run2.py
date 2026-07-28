import json
from constraint_checker import ConstraintExtractor, ConstraintVerifier
from pipeline import CeilingNode
from output_parser import NovaOutputParser

ceiling = CeilingNode(provider="mock")
extractor = ConstraintExtractor(ceiling)
verifier = ConstraintVerifier(ceiling)
parser = NovaOutputParser()

prompt = "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."
constraints = extractor.extract(prompt)

with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()
    data = json.loads(lines[2]) # Case 5 Run 2 is index 2

output = data.get('retry_attempts')[-1]['retry_output'] if data.get('retry_attempts') else data['original_output']
parsed = parser.parse(output)

passed, reason = verifier.verify(constraints, parsed.files)
print("Passed?", passed)
print("Reason:", reason)
