import re

with open("nexus/policy.py", "r") as f:
    content = f.read()

new_get_mode_policy = """def get_mode_policy(mode: str) -> ModePolicy:
    \"\"\"Return the ModePolicy preset for a given mode string.\"\"\"
    if mode == "review":
        return ModePolicy(may_edit=True, may_apply=False, require_review=True, context_depth="deep", verification_level="full")
    elif mode in ("workspace", "default"):
        return ModePolicy(may_edit=True, may_apply=False, require_review=True)
    elif mode in ("autonomous", "acceptEdits"):
        return ModePolicy(may_edit=True, may_apply=True, require_review=False, retry_budget=2)
    elif mode == "quality":
        return ModePolicy(may_edit=True, may_apply=True, require_review=True, context_depth="deep", model_strategy="quality", verification_level="full", retry_budget=3)
    elif mode == "budget":
        return ModePolicy(may_edit=True, may_apply=True, require_review=False, model_strategy="budget", retry_budget=1)
    elif mode == "plan":
        return ModePolicy(may_edit=False, may_apply=False, require_review=True, context_depth="deep")
    elif mode == "local-only":
        return ModePolicy(may_edit=True, may_apply=True, require_review=False, model_strategy="local", retry_budget=2)
    elif mode == "ci":
        return ModePolicy(may_edit=True, may_apply=True, require_review=False, verification_level="full", retry_budget=1)
    return ModePolicy()"""

old_get_mode_policy = re.search(r"def get_mode_policy.*?return ModePolicy\(\)", content, re.DOTALL).group(0)
content = content.replace(old_get_mode_policy, new_get_mode_policy)

with open("nexus/policy.py", "w") as f:
    f.write(content)

print("Fixed policy.py")
