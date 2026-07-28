import re

# Patch constraint_checker.py
with open("constraint_checker.py", "r") as f:
    cc = f.read()

cc = cc.replace("def extract(self, prompt: str) -> Optional[LiteralConstraint]:", "def extract(self, prompt: str) -> list[LiteralConstraint]:")

old_system = """If there is a literal constraint, output a strict JSON object with 'type', 'value', and 'original_text' (the context).
'type' must be one of: 'status_code', 'string_output'.
'value' must be the exact literal value (e.g. '200', 'degraded').
'original_text' must be the full instruction that contained the constraint.

If there are multiple constraints, pick the most important one (like a status code).
If no explicit literal constraint exists, output exactly the word 'NONE'."""

new_system = """If there are literal constraints, output a strict JSON array of objects, each with 'type', 'value', and 'original_text' (the context).
'type' must be one of: 'status_code', 'string_output'.
'value' must be the exact literal value (e.g. '200', 'degraded').
'original_text' must be the full instruction that contained the constraint.

If no explicit literal constraint exists, output exactly the word 'NONE'."""

cc = cc.replace(old_system, new_system)

old_manual = """
                # Generic fallback heuristic
                # Check for status codes
                match = re.search(r'(?:return|status)\s+(?:code\s+)?(\d{3})', prompt, re.IGNORECASE)
                if match:
                    return LiteralConstraint(type='status_code', value=match.group(1), original_text=match.group(0))
                
                # Check for string outputs
                match = re.search(r'(?:print|output|status:|return|body)[^\'"]*([\'"])([^\'"]+)\1', prompt, re.IGNORECASE)
                if match:
                    return LiteralConstraint(type='string_output', value=match.group(2), original_text=match.group(0))
                
                return None
"""

new_manual = """
                # Generic fallback heuristic
                constraints = []
                # Check for status codes
                match = re.search(r'(?:return|status)\s+(?:code\s+)?(\d{3})', prompt, re.IGNORECASE)
                if match:
                    constraints.append(LiteralConstraint(type='status_code', value=match.group(1), original_text=match.group(0)))
                
                # Check for string outputs
                match = re.search(r'(?:print|output|status:|return|body)[^\'"]*([\'"])([^\'"]+)\1', prompt, re.IGNORECASE)
                if match:
                    constraints.append(LiteralConstraint(type='string_output', value=match.group(2), original_text=match.group(0)))
                
                return constraints
"""
cc = cc.replace(old_manual, new_manual)

old_ceiling = """
            if "NONE" in text and "{" not in text:
                return None
            
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
                
            data = json.loads(text.strip())
            return LiteralConstraint(type=data['type'], value=str(data['value']), original_text=data.get('original_text', ''))
        except Exception as e:
            print(f"   ⚠️  Constraint extraction failed: {e}")
            return None
"""
new_ceiling = """
            if "NONE" in text and "[" not in text:
                return []
            
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
                
            data = json.loads(text.strip())
            if isinstance(data, dict): data = [data]
            return [LiteralConstraint(type=d['type'], value=str(d['value']), original_text=d.get('original_text', '')) for d in data]
        except Exception as e:
            print(f"   ⚠️  Constraint extraction failed: {e}")
            return []
"""
cc = cc.replace(old_ceiling, new_ceiling)

old_verify = """
    def verify(self, constraint: LiteralConstraint, files: list[FileAction]) -> tuple[bool, str]:
        code_content = "\n".join(f.content for f in files)
"""

new_verify = """
    def verify_single(self, constraint: LiteralConstraint, code_content: str) -> tuple[bool, str]:
        system = \"\"\"You are a constraint verification tool. Your job is to check if the generated code strictly fulfills a literal constraint in the correct logical branch.
You must output a strict JSON object: {"passed": true/false, "reason": "short explanation"}
Be extremely strict. If the exact literal value isn't used in the correct scenario, it fails.\"\"\"
        
        prompt = f\"\"\"Constraint context: {constraint.original_text}
Literal required ({constraint.type}): {constraint.value}

Does the following code fulfill this constraint correctly?

```
{code_content}
```\"\"\"
        try:
            if self.ceiling.client == "manual":
                # Generalized fallback static check
                if constraint.value not in code_content:
                    return False, f"Constraint FAILED: '{constraint.value}' not found anywhere in code."
                    
                # To be slightly smarter than just "is it in the file", we check if it's on a line with a return/status/print
                if constraint.type == 'status_code':
                    if not any(constraint.value in line and ('status' in line or 'return' in line) for line in code_content.split('\\n')):
                        return False, f"Constraint FAILED: '{constraint.value}' not found in a valid return/status branch."
                elif constraint.type == 'string_output':
                    if not any(constraint.value in line and ('print' in line or 'return' in line or 'status' in line or 'body' in line or 'send' in line or 'json' in line or 'console.log' in line) for line in code_content.split('\\n')):
                        return False, f"Constraint FAILED: string '{constraint.value}' not found in a valid output branch."
                
                return True, f"Constraint PASSED: Found '{constraint.value}' in valid branch statically."

            response = self.ceiling.client.chat.completions.create(
                model=self.ceiling.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
            )
            text = response.choices[0].message.content.strip()
            
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
                
            data = json.loads(text.strip())
            return data["passed"], ("Constraint PASSED: " if data["passed"] else "Constraint FAILED: ") + data["reason"]
        except Exception as e:
            # Fallback to naive check if API fails
            if constraint.value in code_content:
                return True, f"Constraint PASSED (fallback): Found '{constraint.value}' statically in code."
            return False, f"Constraint FAILED (fallback): '{constraint.value}' not found in code."

    def verify(self, constraints: list[LiteralConstraint], files: list[FileAction]) -> tuple[bool, str]:
        code_content = "\\n".join(f.content for f in files)
        reasons = []
        for c in constraints:
            passed, reason = self.verify_single(c, code_content)
            reasons.append(reason)
            if not passed:
                return False, " | ".join(reasons)
        return True, " | ".join(reasons)
"""

# Replace everything from `def verify` to the end
cc = cc[:cc.find("    def verify(self")] + new_verify

with open("constraint_checker.py", "w") as f:
    f.write(cc)

# Patch pipeline.py
with open("pipeline.py", "r") as f:
    pp = f.read()

old_ext = """            # ── CONSTRAINT EXTRACTION ────────────────────────────────────────
            constraint = self.constraint_extractor.extract(task.description)
            if constraint:
                print(f"   🎯 CONSTRAINT: Found literal constraint -> {constraint.type}: {constraint.value}")"""

new_ext = """            # ── CONSTRAINT EXTRACTION ────────────────────────────────────────
            constraints = self.constraint_extractor.extract(task.description)
            if constraints:
                for c in constraints:
                    print(f"   🎯 CONSTRAINT: Found literal constraint -> {c.type}: {c.value}")"""

pp = pp.replace(old_ext, new_ext)

old_ver = """                # ── CONSTRAINT VERIFICATION ────────────────────────────────────
                if constraint:
                    passed, reason = self.constraint_verifier.verify(constraint, task_result.response.files)"""

new_ver = """                # ── CONSTRAINT VERIFICATION ────────────────────────────────────
                if constraints:
                    passed, reason = self.constraint_verifier.verify(constraints, task_result.response.files)"""

pp = pp.replace(old_ver, new_ver)

with open("pipeline.py", "w") as f:
    f.write(pp)
