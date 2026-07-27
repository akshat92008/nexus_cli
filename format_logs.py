import json

out = []
with open('guardrail_events.jsonl') as f:
    lines = f.readlines()

for i in range(0, len(lines), 2):
    if i+1 >= len(lines): break
    run_data = json.loads(lines[i])
    merged_data = json.loads(lines[i+1])
    
    out.append(f"## Run {(i//2)+1}\n")
    out.append(f"**Prompt:** {run_data['prompt']}\n")
    out.append(f"**Final Status:** {run_data['final_status']}\n")
    
    if run_data.get('check_failed'):
        out.append(f"**Guardrail Failure:** {run_data['check_failed']}\n")
        
    out.append("### Model Output\n```\n")
    out.append(run_data.get('original_output', ''))
    out.append("\n```\n")
    
    # We want a diff. The original file vs merged file.
    # The merged_content is in merged_data.
    out.append("### Merged File on Disk\n```python\n")
    out.append(merged_data.get('merged_content', ''))
    out.append("\n```\n")
    out.append("---\n")

with open('baseline_15_runs.md', 'w') as f:
    f.writelines(out)
