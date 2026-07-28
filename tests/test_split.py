import json

from nova_v12.data.split import split_jsonl


def test_repository_split_keeps_repository_together(tmp_path):
    input_path = tmp_path / "records.jsonl"
    records = [
        {"id": "a1", "repository": "org/a"},
        {"id": "a2", "repository": "org/a"},
        {"id": "b1", "repository": "org/b"},
    ]
    input_path.write_text("".join(json.dumps(item) + "\n" for item in records))
    output = tmp_path / "splits"
    counts = split_jsonl(input_path, output, train=0.5, validation=0.25, test=0.25)
    assert sum(counts.values()) == 3
    locations = {}
    for split in ("train", "validation", "test"):
        for line in (output / f"{split}.jsonl").read_text().splitlines():
            item = json.loads(line)
            locations.setdefault(item["repository"], set()).add(split)
    assert all(len(value) == 1 for value in locations.values())
