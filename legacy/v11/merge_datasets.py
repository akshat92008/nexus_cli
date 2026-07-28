import json
import os

files_to_merge = [
    "dataset_nova_intern_v5.jsonl",
    "dataset_expansion/refusal_examples.jsonl",
    "dataset_expansion/multifile_examples.jsonl"
]

output_file = "dataset_nova3b_combined_v6.jsonl"
total_lines = 0

with open(output_file, "w") as outfile:
    for fname in files_to_merge:
        if os.path.exists(fname):
            with open(fname, "r") as infile:
                for line in infile:
                    if line.strip():
                        outfile.write(line)
                        total_lines += 1
            print(f"Merged {fname}")
        else:
            print(f"Warning: {fname} not found!")

print(f"Success! Created {output_file} with {total_lines} examples.")
