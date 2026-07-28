import json

with open('guardrail_events.jsonl') as f:
    lines = f.readlines()

last_lines = lines[-30:]

runs = []
for i in range(0, len(last_lines), 2):
    if i+1 >= len(last_lines): break
    try:
        run_data = json.loads(last_lines[i])
        merged_data = json.loads(last_lines[i+1])
        runs.append((run_data, merged_data))
    except:
        pass

out = []
for idx, (run_data, merged_data) in enumerate(runs):
    out.append(f"## Run {idx+1}\n")
    out.append(f"**Prompt:** {run_data.get('prompt')}\n")
    out.append(f"**Final Status:** {run_data.get('final_status')}\n")
    
    if run_data.get('check_failed'):
        out.append(f"**Guardrail Failure:** {run_data.get('check_failed')}\n")
        
    if run_data.get('retry_attempts'):
        out.append(f"**Retries Attempted:** {len(run_data.get('retry_attempts'))}\n")
        # Just show the first retry prompt to prove injection worked
        out.append(f"**First Retry Prompt Snippet:**\n```\n{run_data['retry_attempts'][0].get('retry_prompt', '')}\n```\n")

    out.append("### Model Output\n```\n")
    out.append(run_data.get('original_output', ''))
    out.append("\n```\n")
    
    out.append("### Merged File on Disk\n```python\n")
    # Truncate the file slightly if it's identical noise to save chat space?
    # No, user asked for full raw content. "merged-file-on-disk for each".
    out.append(merged_data.get('merged_content', ''))
    out.append("\n```\n")
    out.append("---\n")

with open('baseline_final.md', 'w') as f:
    f.writelines(out)

