import re

def apply_patch(original_text, patch_content):
    # Regex to find all patch blocks
    pattern = re.compile(r'<<<<\n(.*?)\n====\n(.*?)\n>>>>', re.DOTALL)
    
    modified_text = original_text
    
    matches = pattern.findall(patch_content)
    if not matches:
        print("Warning: no patch blocks found.")
        # Fallback for backward compatibility, if the model outputs full file instead of patch.
        # Check if the patch content looks like a python or js file and doesn't have <<<<
        if "<<<<" not in patch_content:
            return patch_content
        return original_text
        
    for original_block, new_block in matches:
        # Strict exact match first
        if original_block in modified_text:
            modified_text = modified_text.replace(original_block, new_block, 1)
        else:
            # Fallback: try stripping trailing/leading whitespace or just trailing whitespace
            stripped_original = original_block.strip()
            # If we find it, we need to be careful with replacement.
            # A simple heuristic: if it fails, just print a warning. For this prototype, strict match is fine,
            # but models often mess up leading/trailing newlines.
            print(f"Warning: strict patch failed for block. Attempting relaxed patch.")
            
            # Relaxed patch: find the block in modified_text using re.search with whitespace insensitivity?
            # Too complex for this baseline. Let's just try to remove the last newline from original_block.
            if original_block.rstrip() in modified_text:
                 modified_text = modified_text.replace(original_block.rstrip(), new_block.rstrip(), 1)
            else:
                 print(f"Failed to patch block:\n{original_block}")
    return modified_text

original = """line 1
line 2
line 3
line 4
line 5"""

patch = """<<<<
line 2
line 3
====
line 2_new
line 3_new
>>>>"""

print("RESULT:")
print(apply_patch(original, patch))
