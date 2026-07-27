import re
import os
from run_realistic_baseline import create_complex_file

def get_excerpt(file_path, prompt):
    with open(file_path, 'r') as f:
        content = f.read()
        
    lines = content.split('\n')
    target_line_idx = -1
    
    line_match = re.search(r'line\s+(\d+)', prompt, re.IGNORECASE)
    if line_match:
        target_line_idx = int(line_match.group(1)) - 1
    else:
        words = re.findall(r'\b[a-zA-Z_]\w{4,}\b', prompt)
        words = sorted(words, key=len, reverse=True)
        for w in words:
            if w.lower() in ["urgent", "endpoint", "returning", "because", "variable", "undefined", "catch", "status"]:
                continue
            for i, line in enumerate(lines):
                if w in line:
                    target_line_idx = i
                    break
            if target_line_idx != -1:
                break
                
    if target_line_idx != -1:
        window_size = 20
        start = max(0, target_line_idx - window_size)
        end = min(len(lines), target_line_idx + window_size + 1)
        excerpt = []
        for i in range(start, end):
            excerpt.append(lines[i])
        return f"--- EXCERPT (Lines {start+1} to {end}) ---\n" + "\n".join(excerpt) + "\n--- END EXCERPT ---"
    return "NO EXCERPT"

os.makedirs("tmp_files", exist_ok=True)

# Case 5
auth_target = "    # This endpoint crashes if the user has no profile picture\n    profile_pic_url = current_user.profile_pic_url"
create_complex_file("tmp_files/auth.py", 150, 40, auth_target, "python")
c5_prompt = "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing."

# Case 6
app_target = "app.get('/healthcheck', (req, res) => {\n    const connection = db.getConnection();\n    res.status(200).json({ status: 'healthy' });\n});"
create_complex_file("tmp_files/app.js", 150, 85, app_target, "js")
c6_prompt = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."

print("=== CASE 5 EXCERPT ===")
print(get_excerpt("tmp_files/auth.py", c5_prompt))

print("\n=== CASE 6 EXCERPT ===")
print(get_excerpt("tmp_files/app.js", c6_prompt))

