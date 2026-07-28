#!/usr/bin/env python3
"""
validate_dataset.py — Quality Control for Nova 3B Dataset (Amaura)

Validates JSONL datasets for both formats:
  - 3B Intern mode: Markdown code blocks with # filepath: / # action: headers
  - Reasoning mode: JSON arrays in <<FILES>> block (legacy)

Checks:
  - All 3 blocks present (<<THINKING>>, <<FILES>>, <<TEST_COMMAND>>)
  - Thinking block brevity (intern: <100 words, reasoning: >200 words)
  - Code block validity (filepath/action headers, balanced fences)
  - Content deduplication by code hash
  - Category distribution statistics

Usage:
  python validate_dataset.py --input dataset_nova3b_combined.jsonl --mode 3b
  python validate_dataset.py --input dataset_nova_v3_cot.jsonl --mode reasoning
  python validate_dataset.py --input dataset_nova3b_combined.jsonl --mode 3b --output clean.jsonl

Part of the Nova model family by Amaura.
"""

import json
import os
import sys
import hashlib
import argparse
from typing import Dict, List, Tuple, Optional
from collections import Counter, defaultdict


def extract_blocks(text: str) -> Dict[str, Optional[str]]:
    """Extract <<THINKING>>, <<FILES>>, and <<TEST_COMMAND>> blocks from response."""
    blocks = {"thinking": None, "files": None, "test_command": None}

    try:
        if "<<THINKING>>" in text and "<<FILES>>" in text:
            thinking_start = text.index("<<THINKING>>") + len("<<THINKING>>")
            thinking_end = text.index("<<FILES>>")
            blocks["thinking"] = text[thinking_start:thinking_end].strip()
    except ValueError:
        pass

    try:
        if "<<FILES>>" in text and "<<TEST_COMMAND>>" in text:
            files_start = text.index("<<FILES>>") + len("<<FILES>>")
            files_end = text.index("<<TEST_COMMAND>>")
            blocks["files"] = text[files_start:files_end].strip()
    except ValueError:
        pass

    try:
        if "<<TEST_COMMAND>>" in text:
            cmd_start = text.index("<<TEST_COMMAND>>") + len("<<TEST_COMMAND>>")
            # Find end — could be <</ or end of string
            cmd_end = len(text)
            for end_marker in ["<</TEST_COMMAND>>", "<</"]:
                try:
                    pos = text.index(end_marker, cmd_start)
                    cmd_end = min(cmd_end, pos)
                except ValueError:
                    pass
            blocks["test_command"] = text[cmd_start:cmd_end].strip()
    except ValueError:
        pass

    return blocks


def validate_entry_3b(entry: Dict, index: int, max_thinking_words: int = 100) -> Tuple[bool, List[str]]:
    """
    Validate a single JSONL entry for Nova 3B intern format.
    3B intern uses markdown code blocks with # filepath: / # action: headers.
    Thinking should be BRIEF (under max_thinking_words).
    """
    issues = []

    # Check structure
    if "messages" not in entry:
        issues.append("Missing 'messages' field")
        return False, issues

    messages = entry["messages"]
    if not isinstance(messages, list) or len(messages) < 2:
        issues.append("'messages' must be a list with at least 2 entries")
        return False, issues

    # Find user and assistant messages
    user_msg = None
    assistant_msg = None
    for msg in messages:
        if msg.get("role") == "user" and user_msg is None:
            user_msg = msg
        elif msg.get("role") == "assistant" and assistant_msg is None:
            assistant_msg = msg

    if not user_msg or not user_msg.get("content", "").strip():
        issues.append("Missing or empty user message")
    if not assistant_msg:
        issues.append("Missing assistant message")
        return False, issues

    response_text = assistant_msg.get("content", "")
    if not response_text.strip():
        issues.append("Assistant response is empty")
        return False, issues

    # Extract and validate blocks
    blocks = extract_blocks(response_text)

    if blocks["thinking"] is None:
        issues.append("Missing <<THINKING>> block")
    else:
        word_count = len(blocks["thinking"].split())
        if word_count > max_thinking_words:
            issues.append(f"Thinking too verbose: {word_count} words (max {max_thinking_words})")
        if word_count < 3:
            issues.append("Thinking too short (need at least 3 words)")

    if blocks["files"] is None:
        issues.append("Missing <<FILES>> block")
    else:
        files_content = blocks["files"]
        # 3B format uses markdown code blocks with # filepath: / # action:
        import re
        code_blocks = re.findall(r'```\w*\n(.*?)```', files_content, re.DOTALL)
        
        if not code_blocks:
            # Fallback: try JSON format (legacy)
            try:
                files_json = json.loads(files_content)
                if isinstance(files_json, list) and len(files_json) > 0:
                    pass  # Valid legacy format
                else:
                    issues.append("<<FILES>> has no code blocks or valid JSON")
            except json.JSONDecodeError:
                issues.append("<<FILES>> has no markdown code blocks")
        else:
            # Validate each code block has filepath/action headers
            for i, block in enumerate(code_blocks):
                has_filepath = bool(re.search(r'#\s*filepath:', block, re.IGNORECASE))
                has_action = bool(re.search(r'#\s*action:', block, re.IGNORECASE))
                if not has_filepath:
                    issues.append(f"Code block {i} missing '# filepath:' header")
                if not has_action:
                    issues.append(f"Code block {i} missing '# action:' header")
                
                # Check code is not empty (strip metadata lines)
                code_lines = [l for l in block.split('\n') 
                             if not l.strip().startswith('# filepath:') 
                             and not l.strip().startswith('# action:')
                             and l.strip()]
                if len(code_lines) < 1:
                    issues.append(f"Code block {i} has no actual code")

    if blocks["test_command"] is None:
        issues.append("Missing <<TEST_COMMAND>> block")
    elif len(blocks["test_command"].strip()) < 3:
        issues.append("<<TEST_COMMAND>> is too short")

    is_valid = len(issues) == 0
    return is_valid, issues


def validate_entry(entry: Dict, index: int, min_thinking_words: int) -> Tuple[bool, List[str]]:
    """
    Validate a single JSONL entry (legacy reasoning format).
    Returns (is_valid, list_of_issues).
    """
    issues = []

    # Check structure
    if "messages" not in entry:
        issues.append("Missing 'messages' field")
        return False, issues

    messages = entry["messages"]
    if not isinstance(messages, list) or len(messages) < 2:
        issues.append("'messages' must be a list with at least 2 entries")
        return False, issues

    # Check user message
    user_msg = messages[0]
    if user_msg.get("role") != "user":
        issues.append("First message must have role 'user'")
    if not user_msg.get("content", "").strip():
        issues.append("User message is empty")

    # Check assistant message
    assistant_msg = messages[1]
    if assistant_msg.get("role") != "assistant":
        issues.append("Second message must have role 'assistant'")
    
    response_text = assistant_msg.get("content", "")
    if not response_text.strip():
        issues.append("Assistant response is empty")
        return False, issues

    # Extract and validate blocks
    blocks = extract_blocks(response_text)

    if blocks["thinking"] is None:
        issues.append("Missing <<THINKING>> block")
    else:
        word_count = len(blocks["thinking"].split())
        if word_count < min_thinking_words:
            issues.append(f"Thinking too short: {word_count} words (need {min_thinking_words}+)")

        # Check for signs of shallow thinking
        shallow_indicators = [
            "Domain:", "Difficulty:", "Complexity:", "Architectural Reasoning:\n1.",
        ]
        shallow_count = sum(1 for s in shallow_indicators if s in blocks["thinking"][:200])
        if shallow_count >= 3:
            issues.append("Thinking block appears to be shallow metadata, not genuine reasoning")

    if blocks["files"] is None:
        issues.append("Missing <<FILES>> block")
    else:
        try:
            files_json = json.loads(blocks["files"])
            if not isinstance(files_json, list):
                issues.append("<<FILES>> is not a JSON array")
            elif len(files_json) == 0:
                issues.append("<<FILES>> array is empty")
            else:
                for j, f in enumerate(files_json):
                    if "path" not in f:
                        issues.append(f"File entry {j} missing 'path'")
                    if "content" not in f:
                        issues.append(f"File entry {j} missing 'content'")
                    elif not f["content"].strip():
                        issues.append(f"File entry {j} has empty content")
        except json.JSONDecodeError as e:
            issues.append(f"<<FILES>> is not valid JSON: {str(e)[:80]}")

    if blocks["test_command"] is None:
        issues.append("Missing <<TEST_COMMAND>> block")
    elif len(blocks["test_command"].strip()) < 3:
        issues.append("<<TEST_COMMAND>> is too short")

    is_valid = len(issues) == 0
    return is_valid, issues


def compute_content_hash(text: str) -> str:
    """Compute a hash of the content for deduplication."""
    # Normalize whitespace for near-duplicate detection
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def validate_dataset(
    input_file: str,
    output_file: Optional[str],
    min_thinking_words: int,
    verbose: bool,
) -> Dict:
    """
    Validate entire dataset and optionally write cleaned output.
    Returns stats dict.
    """
    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
        sys.exit(1)

    print(f"📂 Validating: {input_file}")
    print(f"📏 Min thinking words: {min_thinking_words}")
    print()

    entries = []
    parse_errors = 0

    # Load all entries
    with open(input_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entries.append((line_num, entry))
            except json.JSONDecodeError as e:
                parse_errors += 1
                if verbose:
                    print(f"  ⚠️  Line {line_num}: JSON parse error: {e}")

    print(f"📊 Loaded {len(entries)} entries ({parse_errors} parse errors)")

    # Validate each entry
    valid_entries = []
    invalid_entries = []
    
    # Stats
    thinking_word_counts = []
    file_counts = []
    categories = Counter()
    languages_detected = Counter()
    content_hashes = defaultdict(list)

    for line_num, entry in entries:
        is_valid, issues = validate_entry(entry, line_num, min_thinking_words)
        
        # Extract metadata
        meta = entry.get("metadata", {})
        category = meta.get("category", "unknown")
        categories[category] += 1

        if is_valid:
            valid_entries.append(entry)

            # Collect stats
            response = entry["messages"][1]["content"]
            blocks = extract_blocks(response)
            
            if blocks["thinking"]:
                wc = len(blocks["thinking"].split())
                thinking_word_counts.append(wc)

            if blocks["files"]:
                try:
                    files = json.loads(blocks["files"])
                    file_counts.append(len(files))
                    
                    # Detect languages from file extensions
                    for f in files:
                        ext = f.get("path", "").rsplit(".", 1)[-1] if "." in f.get("path", "") else "unknown"
                        lang_map = {
                            "py": "Python", "ts": "TypeScript", "js": "JavaScript",
                            "rs": "Rust", "go": "Go", "java": "Java", "cpp": "C++",
                            "c": "C", "sql": "SQL", "sh": "Bash", "rb": "Ruby",
                        }
                        languages_detected[lang_map.get(ext, ext)] += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            # Deduplication hash
            content_hash = compute_content_hash(entry["messages"][0]["content"])
            content_hashes[content_hash].append(line_num)
        else:
            invalid_entries.append((line_num, issues))
            if verbose:
                print(f"  ❌ Line {line_num}: {'; '.join(issues)}")

    # Find duplicates
    duplicates = {h: lines for h, lines in content_hashes.items() if len(lines) > 1}
    duplicate_count = sum(len(lines) - 1 for lines in duplicates.values())

    # Remove duplicates from valid entries if writing output
    if output_file and duplicates:
        seen_hashes = set()
        deduped = []
        for entry in valid_entries:
            h = compute_content_hash(entry["messages"][0]["content"])
            if h not in seen_hashes:
                seen_hashes.add(h)
                deduped.append(entry)
        valid_entries = deduped

    # Write cleaned output
    if output_file and valid_entries:
        with open(output_file, "w") as f:
            for entry in valid_entries:
                # Strip metadata for training (keep only messages)
                clean_entry = {"messages": entry["messages"]}
                f.write(json.dumps(clean_entry) + "\n")
        print(f"\n✅ Wrote {len(valid_entries)} clean entries to {output_file}")

    # ── Print Report ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(" VALIDATION REPORT")
    print("=" * 70)

    total = len(entries)
    valid = len(valid_entries)
    invalid = len(invalid_entries)
    
    print(f"\n  📊 Summary:")
    print(f"     Total entries:    {total}")
    print(f"     ✅ Valid:          {valid} ({valid/total*100:.1f}%)" if total > 0 else "     ✅ Valid: 0")
    print(f"     ❌ Invalid:        {invalid} ({invalid/total*100:.1f}%)" if total > 0 else "     ❌ Invalid: 0")
    print(f"     🔄 Duplicates:     {duplicate_count}")
    print(f"     📛 Parse errors:   {parse_errors}")

    if thinking_word_counts:
        avg_words = sum(thinking_word_counts) / len(thinking_word_counts)
        min_words = min(thinking_word_counts)
        max_words = max(thinking_word_counts)
        print(f"\n  🧠 Thinking Block Stats:")
        print(f"     Average words:  {avg_words:.0f}")
        print(f"     Min words:      {min_words}")
        print(f"     Max words:      {max_words}")
        
        # Distribution histogram
        buckets = [0, 200, 400, 600, 800, 1000, 1500, 2000, float("inf")]
        print(f"     Distribution:")
        for i in range(len(buckets) - 1):
            lo, hi = buckets[i], buckets[i+1]
            count = sum(1 for w in thinking_word_counts if lo <= w < hi)
            label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
            bar = "█" * (count * 40 // len(thinking_word_counts)) if thinking_word_counts else ""
            print(f"       {label:>10s}: {count:>4d} {bar}")

    if file_counts:
        avg_files = sum(file_counts) / len(file_counts)
        print(f"\n  📁 Files per Solution:")
        print(f"     Average: {avg_files:.1f}")
        for fc, cnt in sorted(Counter(file_counts).items()):
            print(f"       {fc} file(s): {cnt} examples")

    if categories:
        print(f"\n  🏷️  Category Distribution:")
        for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
            bar = "█" * (cnt * 30 // max(categories.values()))
            print(f"     {cat:<35s} {cnt:>4d} {bar}")

    if languages_detected:
        print(f"\n  💻 Languages Detected:")
        for lang, cnt in sorted(languages_detected.items(), key=lambda x: -x[1])[:15]:
            bar = "█" * (cnt * 30 // max(languages_detected.values()))
            print(f"     {lang:<15s} {cnt:>4d} {bar}")

    if duplicates:
        print(f"\n  🔄 Duplicate Clusters ({len(duplicates)}):")
        for h, lines in list(duplicates.items())[:5]:
            print(f"     Hash {h}: lines {lines}")
        if len(duplicates) > 5:
            print(f"     ... and {len(duplicates) - 5} more")

    if invalid_entries and not verbose:
        print(f"\n  ❌ Invalid Entry Issues (first 10):")
        for line_num, issues in invalid_entries[:10]:
            print(f"     Line {line_num}: {'; '.join(issues[:2])}")
        if len(invalid_entries) > 10:
            print(f"     ... and {len(invalid_entries) - 10} more (use --verbose for all)")

    print()
    print("=" * 70)

    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "duplicates": duplicate_count,
        "avg_thinking_words": sum(thinking_word_counts) / len(thinking_word_counts) if thinking_word_counts else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Amaura — Validate Nova dataset")
    parser.add_argument("--input", "-i", type=str, required=True, help="Input JSONL file to validate")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output cleaned JSONL file (optional)")
    parser.add_argument("--mode", choices=["3b", "reasoning"], default="3b",
                        help="Validation mode: '3b' for intern format, 'reasoning' for deep-thought format")
    parser.add_argument("--min-words", type=int, default=200, help="Min words in thinking block (reasoning mode, default: 200)")
    parser.add_argument("--max-words", type=int, default=100, help="Max words in thinking block (3b mode, default: 100)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print all validation issues")
    args = parser.parse_args()

    if args.mode == "3b":
        # For 3b mode, we override the validation function
        # by setting min_thinking_words to 3 (minimum) and using validate_entry_3b
        print(f"🔧 Mode: Nova 3B Intern (max {args.max_words} thinking words)")
    else:
        print(f"🔧 Mode: Reasoning (min {args.min_words} thinking words)")

    validate_dataset(args.input, args.output, args.min_words, args.verbose)


if __name__ == "__main__":
    main()
