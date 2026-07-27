import json

with open("eval_results_raw.json", "r") as f:
    results = json.load(f)

md_content = "# Comprehensive Model Evaluation: Nova Intern vs Base Qwen2.5\n\n"
md_content += "This artifact contains the raw, unedited outputs from both the fine-tuned `nova-intern` model and the raw `qwen2.5-coder:1.5b` base model.\n\n"

for tier in results["nova-intern"]:
    md_content += f"## {tier}\n"
    md_content += f"**Prompt:**\n> {results['nova-intern'][tier]['prompt']}\n\n"
    
    # Nova Intern Output
    nova_out = results["nova-intern"][tier]["response"]
    md_content += "### 🟢 Nova Intern (Fine-Tuned)\n"
    md_content += "```text\n" + nova_out.strip() + "\n```\n\n"
    
    # Formatting check
    if "<<THINKING>>" in nova_out and "<<FILES>>" in nova_out:
        md_content += "✅ **Format Check:** Perfect `<<THINKING>>` / `<<FILES>>` adherence.\n\n"
    else:
        md_content += "❌ **Format Check:** Failed strict formatting.\n\n"
        
    # Base Qwen Output
    qwen_out = results["qwen2.5-coder:1.5b"][tier]["response"]
    md_content += "### 🔴 Base Model (Qwen 2.5 Coder 1.5B)\n"
    md_content += "```text\n" + qwen_out.strip() + "\n```\n\n"
    
    md_content += "---\n\n"

with open("/Users/ashishsingh/.gemini/antigravity-ide/brain/9ae935f3-bfe9-4428-9591-569fd45ece19/evaluation_results.md", "w") as f:
    f.write(md_content)

print("Evaluation report generated.")
