import re

cases = [
    {"name": "Case 5 (Context + Assignment)", "prompt": "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."},
    {"name": "Case 6 (Context + Status/String)", "prompt": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."},
    {"name": "Fresh Case 1 (Assignment)", "prompt": "URGENT: the retry logic is looping infinitely. in src/utils.py around line 75, if max_retries is not provided, set it to 3 instead of 5."},
    {"name": "Fresh Case 2 (Status Code + String JS)", "prompt": "URGENT: payment endpoint is returning wrong code. in src/routes/api.js at line 90, change the failure response to return 402 with status: 'Payment Required'."},
    {"name": "Fresh Case 3 (String Output Python)", "prompt": "URGENT: logging monitor is missing timeouts. in src/worker.py line 50, change the exception print output to exactly 'Worker Timeout'."}
]

for case in cases:
    prompt = case["prompt"]
    match_type = "None"
    match_val = ""
    line_match = re.search(r'line\s+(\d+)', prompt, re.IGNORECASE)
    if line_match:
        match_type = "Line"
        match_val = line_match.group(1)
    else:
        words = re.findall(r'\b[a-zA-Z_]\w{4,}\b', prompt)
        words = sorted(words, key=len, reverse=True)
        for w in words:
            if w.lower() in ["urgent", "endpoint", "returning", "because", "variable", "undefined", "catch", "status"]:
                continue
            # Assume it matches in file for test purposes
            match_type = "Identifier"
            match_val = w
            break
            
    print(f"{case['name']}: {match_type} ({match_val})")
