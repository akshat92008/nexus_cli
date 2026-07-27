import re

def narrow_context(prompt, file_content, window_size=20):
    lines = file_content.split('\n')
    target_line_idx = -1
    
    # 1. Try to find a line number in the prompt
    line_match = re.search(r'line\s+(\d+)', prompt, re.IGNORECASE)
    if line_match:
        target_line_idx = int(line_match.group(1)) - 1
    
    # 2. Try to find a function name or key identifier if no line number is found
    else:
        # Extract potential identifiers from prompt (words > 4 chars)
        words = re.findall(r'\b[a-zA-Z_]\w{4,}\b', prompt)
        # Sort by length descending, assuming longer words are more specific identifiers
        words = sorted(words, key=len, reverse=True)
        for w in words:
            # Skip common english words that might be in the prompt
            if w.lower() in ["urgent", "endpoint", "returning", "because", "variable", "undefined", "catch", "status"]:
                continue
            # Search for this word in the file
            for i, line in enumerate(lines):
                if w in line:
                    target_line_idx = i
                    break
            if target_line_idx != -1:
                break
                
    if target_line_idx != -1:
        start = max(0, target_line_idx - window_size)
        end = min(len(lines), target_line_idx + window_size + 1)
        
        # Format the excerpt with original line numbers
        excerpt = []
        for i in range(start, end):
            excerpt.append(f"{i+1}: {lines[i]}")
        return "\n".join(excerpt)
    
    # Fallback to full file if no target found
    return file_content

print("Testing logic:")
print("Case 5:", narrow_context("at line 40", "line1\n"*39 + "target\n" + "line41\n"*40, 2))
