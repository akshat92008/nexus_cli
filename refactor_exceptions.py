import os
import re

def infer_exceptions(try_body_text):
    exc = set()
    if re.search(r'\b(open|read|write|close|stat|mkdir|exists|is_file|is_dir|unlink|remove|rename)\b', try_body_text):
        exc.add('OSError')
    if re.search(r'\b(json\.loads|json\.dumps|int|float|str|split|strip|replace|join|format)\b', try_body_text):
        exc.add('ValueError')
        exc.add('TypeError')
    if re.search(r'\b(subprocess|run_shell|Popen|run)\b', try_body_text):
        exc.add('OSError')
        exc.add('RuntimeError')
    if re.search(r'\[.+\]|\.get\(', try_body_text):
        exc.add('LookupError')
    if re.search(r'\b(httpx|requests|curl|urllib|socket|post|get)\b', try_body_text):
        exc.add('OSError')
        exc.add('RuntimeError')
    if re.search(r'\b(import|importlib)\b', try_body_text):
        exc.add('ImportError')
        
    if not exc:
        exc = {'OSError', 'ValueError'}
    
    exc_str = ', '.join(sorted(exc))
    if len(exc) == 1:
        return list(exc)[0]
    return f"({exc_str})"

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    
    last_try_idx = -1
    modified = False
    for i, line in enumerate(lines):
        if re.match(r'^\s*try:\s*$', line):
            last_try_idx = i
        
        m = re.match(r'^(\s*)except Exception\s*:\s*(.*)$', line)
        m2 = re.match(r'^(\s*)except Exception as ([a-zA-Z0-9_]+)\s*:\s*(.*)$', line)
        
        if m or m2:
            modified = True
            if last_try_idx != -1:
                try_body = '\n'.join(lines[last_try_idx:i])
                inferred = infer_exceptions(try_body)
            else:
                inferred = '(OSError, ValueError, TypeError)'
                
            if m:
                indent = m.group(1)
                rest = m.group(2)
                new_lines.append(f"{indent}except {inferred}:{rest}")
            else:
                indent = m2.group(1)
                name = m2.group(2)
                rest = m2.group(3)
                new_lines.append(f"{indent}except {inferred} as {name}:{rest}")
        else:
            new_lines.append(line)
            
    if modified:
        with open(filepath, 'w') as f:
            f.write('\n'.join(new_lines))

for root, dirs, files in os.walk('nexus'):
    for file in files:
        if file.endswith('.py'):
            process_file(os.path.join(root, file))
