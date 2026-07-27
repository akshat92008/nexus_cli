import json
from constraint_checker import ConstraintExtractor, ConstraintVerifier
from pipeline import CeilingNode, AtomicTask
from output_parser import NovaOutputParser

def main():
    cases = [
        {
            "name": "Case 5 (Context + Assignment)",
            "prompt": "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."
        },
        {
            "name": "Case 6 (Context + Status/String)",
            "prompt": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."
        },
        {
            "name": "Fresh Case 1 (Assignment)",
            "prompt": "URGENT: the retry logic is looping infinitely. in src/utils.py around line 75, if max_retries is not provided, set it to 3 instead of 5."
        },
        {
            "name": "Fresh Case 2 (Status Code + String JS)",
            "prompt": "URGENT: payment endpoint is returning wrong code. in src/routes/api.js at line 90, change the failure response to return 402 with status: 'Payment Required'."
        },
        {
            "name": "Fresh Case 3 (String Output Python)",
            "prompt": "URGENT: logging monitor is missing timeouts. in src/worker.py line 50, change the exception print output to exactly 'Worker Timeout'."
        }
    ]

    ceiling = CeilingNode(provider="mock")
    extractor = ConstraintExtractor(ceiling)
    verifier = ConstraintVerifier(ceiling)
    parser = NovaOutputParser()

    with open('guardrail_events.jsonl', 'r') as f:
        lines = f.readlines()
        
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break
        data = json.loads(lines[i])
        
        case_idx = (i // 2) // 3
        run_idx = ((i // 2) % 3) + 1
        if case_idx < len(cases):
            case = cases[case_idx]
            constraints = extractor.extract(case['prompt'])
            
            # The model output is in data['original_output'] or if it retried we should check retry_attempts
            output_to_verify = data.get('original_output', '')
            if data.get('retry_attempts'):
                output_to_verify = data['retry_attempts'][-1]['retry_output']
                
            parsed = parser.parse(output_to_verify)
            
            search_blocks = []
            for f in parsed.files:
                if f.action.upper() == "MODIFY":
                    import re
                    pattern = re.compile(r'<+\r?\n(.*?)\r?\n=+\r?\n(.*?)\r?\n>+', re.DOTALL)
                    matches = pattern.findall(f.content)
                    if matches:
                        search_blocks.append("\n".join(m[0] for m in matches))
                    else:
                        print(f"REGEX FAILED! f.content starts with: {repr(f.content[:100])}")
                        search_blocks.append(f.content)
                else:
                    search_blocks.append(f.content)
            search_content = "\n".join(search_blocks)
            print(f"DEBUG: search_content for {case['name']} run {run_idx}: {repr(search_content[:100])}")
            
            passed, reason = verifier.verify(constraints, parsed.files)
            print(f"--- {case['name']} RUN {run_idx} ---")
            print(f"Old Status: {data.get('final_status')}")
            print(f"New Status: {'pass' if passed else 'FAIL'}")
            print(f"New Reason: {reason}")
            print("-" * 50)

if __name__ == "__main__":
    main()
