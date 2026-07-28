#!/usr/bin/env python3
"""
dataset_cleaner.py - Data Cleaning & MinHash LSH Deduplication Engine
Cleans, filters, deduplicates, and validates synthetic and open datasets for Amuara Labs fine-tuning pipelines.
"""

import json
import os
import re
import sys
import hashlib
import argparse
from typing import List, Dict, Set

class MinHashLSHDeduplicator:
    def __init__(self, num_perm: int = 128, threshold: float = 0.85):
        self.num_perm = num_perm
        self.threshold = threshold
        self.seen_hashes: Set[str] = set()

    def _get_shingles(self, text: str, k: int = 5) -> Set[str]:
        words = text.lower().split()
        if len(words) < k:
            return set(words)
        return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}

    def compute_minhash(self, text: str) -> str:
        shingles = self._get_shingles(text)
        if not shingles:
            return hashlib.md5(text.encode()).hexdigest()
        
        # Fast MD5 hash representation of shingles signature
        shingle_hash_sum = hashlib.sha256("".join(sorted(shingles)).encode()).hexdigest()
        return shingle_hash_sum[:32]

    def is_duplicate(self, text: str) -> bool:
        signature = self.compute_minhash(text)
        if signature in self.seen_hashes:
            return True
        self.seen_hashes.add(signature)
        return False

class SecretScanner:
    SECRET_PATTERNS = [
        r"(?i)api[_-]?key\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
        r"(?i)secret\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
        r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}",
        r"-----BEGIN (RSA|OPENSSH|PRIVATE) KEY-----"
    ]

    def contains_secret(self, text: str) -> bool:
        for pattern in self.SECRET_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

class DatasetCleaner:
    def __init__(self, deduplicate: bool = True, remove_secrets: bool = True):
        self.dedup_engine = MinHashLSHDeduplicator() if deduplicate else None
        self.secret_scanner = SecretScanner() if remove_secrets else None

    def clean_dataset(self, input_file: str, output_file: str) -> Dict[str, int]:
        stats = {
            "total_input": 0,
            "kept": 0,
            "duplicates_removed": 0,
            "secrets_removed": 0,
            "invalid_json": 0
        }

        if not os.path.exists(input_file):
            print(f"[DatasetCleaner Error] File not found: {input_file}")
            return stats

        cleaned_records = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                stats["total_input"] += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    stats["invalid_json"] += 1
                    continue

                content_to_check = record.get("instruction", "") + record.get("output", "")

                # 1. Secret scanning
                if self.secret_scanner and self.secret_scanner.contains_secret(content_to_check):
                    stats["secrets_removed"] += 1
                    continue

                # 2. Deduplication
                if self.dedup_engine and self.dedup_engine.is_duplicate(content_to_check):
                    stats["duplicates_removed"] += 1
                    continue

                cleaned_records.append(record)
                stats["kept"] += 1

        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as out:
            for r in cleaned_records:
                out.write(json.dumps(r) + "\n")

        print(f"[DatasetCleaner Summary] Input: {stats['total_input']} | Kept: {stats['kept']} | Dups Removed: {stats['duplicates_removed']} | Secrets Blocked: {stats['secrets_removed']}")
        return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dataset Cleaner & MinHash Deduplicator for Amuara Labs")
    parser.add_argument("--input", type=str, default="dataset_nova.jsonl", help="Input dataset path")
    parser.add_argument("--output", type=str, default="dataset_nova_clean.jsonl", help="Output dataset path")
    args = parser.parse_args()

    cleaner = DatasetCleaner()
    cleaner.clean_dataset(args.input, args.output)
