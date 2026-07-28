import json

with open('train_nova_intern.ipynb', 'r') as f:
    notebook = json.load(f)

for cell in notebook['cells']:
    if cell['cell_type'] == 'code':
        source = cell['source']
        for i, line in enumerate(source):
            if 'dataset_nova_intern_v4.jsonl' in line:
                source[i] = line.replace('dataset_nova_intern_v4.jsonl', 'dataset_nova_intern_v5.jsonl')
            if 'max_steps = 60' in line:
                source[i] = line.replace('max_steps = 60', 'max_steps = 0') # 0 means use epochs
            if '# num_train_epochs = 1' in line:
                source[i] = line.replace('# num_train_epochs = 1', 'num_train_epochs = 1')

with open('train_nova_intern.ipynb', 'w') as f:
    json.dump(notebook, f, indent=1)

print("Notebook updated for 1 epoch and V5 dataset.")
