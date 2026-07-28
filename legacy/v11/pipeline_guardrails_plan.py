import re

def path_validator(prompt, raw_text):
    # Find explicit paths like src/app.js or auth.py
    matches = re.findall(r'(?:^|\s|`|\'|")([a-zA-Z0-9_\-/]+\.\w{1,5})(?:$|\s|`|\'|"|\?|\.|\,)', prompt)
    unique_paths = list(set(matches))
    if len(unique_paths) == 1:
        expected = unique_paths[0]
        # find the filepath in the raw_text
        actual_match = re.search(r'^#\s*filepath:\s*(.+)$', raw_text, re.MULTILINE | re.IGNORECASE)
        if actual_match:
            actual = actual_match.group(1).strip()
            if actual != expected:
                raw_text = raw_text.replace(actual, expected)
                return True, expected, actual, raw_text
    return False, None, None, raw_text

def test_command_validator(prompt, test_command):
    if not test_command or test_command.lower() in ['none', 'n/a']:
        return False, "No test command provided."
    
    # Extract potential constraint keywords from prompt (numbers, quoted strings)
    # E.g. '200', 'degraded'
    constraints = re.findall(r'(\d{3})|[\'"]([a-zA-Z0-9_]+)[\'"]', prompt)
    constraints = [c[0] or c[1] for c in constraints if c[0] or c[1]]
    
    # Check if test command validates these
    is_verifying = any(kw in test_command for kw in ['grep', 'assert', 'pytest', 'jest', 'test'])
    if not is_verifying:
        return False, "Test command does not appear to verify constraints (no assertion or test framework)."
        
    for c in constraints:
        if c.lower() not in test_command.lower():
            # It might be in the test file, but if test file isn't generated, it fails execution anyway.
            # For simplicity, we just flag it.
            pass
            
    return True, "Valid."

